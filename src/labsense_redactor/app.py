"""The HTTP service: four POST endpoints behind a service token, and `GET /health`.

It's internal: only the LabSense backend's api and worker reach it, inside the private network.
It keeps no state: each call reads the PDF from the bucket by key and writes its outputs to the
keys it's given.
"""

import hashlib
import hmac
import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import rasterize as rasterizer
from . import redact
from .config import Settings, load_settings
from .contract import (
    ApplyRequest,
    ApplyResponse,
    DetectRequest,
    DetectResponse,
    PageWords,
    RasterizeRequest,
    RasterizeResponse,
    RasterPage,
    Word,
    WordsRequest,
    WordsResponse,
)
from .detect import detect as detect_details
from .detect.lines import build_lines
from .detect.names import NameFinder
from .document import PageGeometry, open_pdf, page_words, pdf_lock
from .errors import Unprocessable
from .storage import S3Storage, Storage

log = logging.getLogger("labsense_redactor")


def _owner(key: str) -> str:
    """The key's first two parts (`acc/{account}/`, `ops/check/`): outputs stay beside the input."""
    return "/".join(key.split("/")[:2])


def _written(storage: Storage, key: str, body: bytes, content_type: str) -> tuple[int, str]:
    storage.write(key, body, content_type)
    return len(body), hashlib.sha256(body).hexdigest()


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
    names: NameFinder | None = None,
    load_names: bool = True,
) -> FastAPI:
    settings = settings or load_settings()
    storage = storage or S3Storage(settings)
    if names is None and load_names:
        names = NameFinder.load()
    expected = f"Bearer {settings.token}".encode()

    app = FastAPI(title="labsense-redactor", docs_url=None, redoc_url=None, openapi_url=None)

    def authorized(authorization: str = Header(default="")) -> None:
        if not hmac.compare_digest(authorization.encode(), expected):
            raise _Unauthorized()

    @app.exception_handler(_Unauthorized)
    async def _unauthorized(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, __: Exception) -> JSONResponse:
        # FastAPI's default answer echoes the input, which may hold known details.
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    @app.exception_handler(Unprocessable)
    async def _unprocessable(_: Request, error: Exception) -> JSONResponse:
        code = error.code if isinstance(error, Unprocessable) else "unprocessable"
        return JSONResponse({"error": code}, status_code=422)

    def timed(endpoint: str, work: Callable[[dict[str, Any]], Any]) -> Any:
        started = time.monotonic()
        facts: dict[str, Any] = {"endpoint": endpoint}
        try:
            result = work(facts)
        except Unprocessable as error:
            log.info(
                "request refused", extra={**facts, "status": 422, "reason": error.code, "ms": _ms(started)}
            )
            raise
        except Exception as error:
            log.error(
                "request failed",
                extra={**facts, "status": 500, "error": type(error).__name__, "ms": _ms(started)},
            )
            raise
        log.info("request", extra={**facts, "status": 200, "ms": _ms(started)})
        return result

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/detect",
        dependencies=[Depends(authorized)],
        response_model=DetectResponse,
        response_model_by_alias=True,
    )
    def detect(request: DetectRequest) -> DetectResponse:
        def work(facts: dict[str, Any]) -> DetectResponse:
            data = storage.read(request.key, settings.max_bytes)
            with pdf_lock():
                doc = open_pdf(data, request.page_count, settings.max_pages)
                result = detect_details(doc, request.known, names)
            facts.update(
                pages=request.page_count,
                regions=len(result.regions),
                types=result.summary,
                scanned=result.scanned,
            )
            return result

        return timed("detect", work)  # type: ignore[no-any-return]

    @app.post(
        "/words",
        dependencies=[Depends(authorized)],
        response_model=WordsResponse,
        response_model_by_alias=True,
    )
    def words(request: WordsRequest) -> WordsResponse:
        def work(facts: dict[str, Any]) -> WordsResponse:
            data = storage.read(request.key, settings.max_bytes)
            pages: list[PageWords] = []
            with pdf_lock():
                doc = open_pdf(data, request.page_count, settings.max_pages)
                for number, page in enumerate(doc, 1):
                    geometry = PageGeometry(page)
                    out: list[Word] = []
                    for line in build_lines(page_words(page, geometry)):
                        for word in line.words:
                            box = geometry.fractions(word.disp)
                            if box is not None:
                                x0, y0, x1, y1 = box
                                out.append(Word(text=word.text, x0=x0, y0=y0, x1=x1, y1=y1))
                    pages.append(PageWords(page=number, words=out))
            facts.update(pages=request.page_count)
            return WordsResponse(pages=pages)

        return timed("words", work)  # type: ignore[no-any-return]

    @app.post(
        "/apply",
        dependencies=[Depends(authorized)],
        response_model=ApplyResponse,
        response_model_by_alias=True,
    )
    def apply(request: ApplyRequest) -> ApplyResponse:
        def work(facts: dict[str, Any]) -> ApplyResponse:
            if _owner(request.output_key) != _owner(request.key):
                raise Unprocessable("output_key_elsewhere")
            data = storage.read(request.key, settings.max_bytes)
            with pdf_lock():
                redacted = redact.apply(data, request.regions, settings.max_pages)
            size, digest = _written(storage, request.output_key, redacted.pdf, "application/pdf")
            facts.update(regions=len(request.regions), verified=redacted.verified)
            return ApplyResponse(verified=redacted.verified, byte_size=size, sha256=digest)

        return timed("apply", work)  # type: ignore[no-any-return]

    @app.post(
        "/rasterize",
        dependencies=[Depends(authorized)],
        response_model=RasterizeResponse,
        response_model_by_alias=True,
    )
    def rasterize(request: RasterizeRequest) -> RasterizeResponse:
        def work(facts: dict[str, Any]) -> RasterizeResponse:
            if any(_owner(o.key) != _owner(request.key) for o in request.outputs):
                raise Unprocessable("output_key_elsewhere")
            data = storage.read(request.key, settings.max_bytes)
            with pdf_lock():
                images = rasterizer.render(
                    data, request.regions, [o.page for o in request.outputs], settings.max_pages
                )
            pages = []
            for output in request.outputs:
                size, digest = _written(storage, output.key, images[output.page], "image/jpeg")
                pages.append(RasterPage(page=output.page, byte_size=size, sha256=digest))
            facts.update(pages=len(pages), regions=len(request.regions))
            return RasterizeResponse(pages=pages)

        return timed("rasterize", work)  # type: ignore[no-any-return]

    return app


class _Unauthorized(Exception):
    pass


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
