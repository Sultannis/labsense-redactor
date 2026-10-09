"""Opening PDFs, their words, and the page geometry shared by every endpoint.

PyMuPDF reports text in the page's unrotated coordinates, measured from the visible area's
(CropBox's) top-left corner. The contract speaks in fractions of the page as displayed, so each
page converts both ways through its rotation matrices.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pymupdf

from .errors import Unprocessable

#: MuPDF isn't safe across threads: every use of a document happens under this lock.
_LOCK = threading.Lock()


@contextmanager
def pdf_lock() -> Iterator[None]:
    with _LOCK:
        yield


pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def open_pdf(data: bytes, page_count: int | None, max_pages: int = 50) -> pymupdf.Document:
    """The PDF, checked against the backend's page count where the request has one (`/detect`,
    `/words`): every page is processed, so a page the backend doesn't know about would reach the
    AI unchecked."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (RuntimeError, ValueError):
        raise Unprocessable("unreadable") from None
    if doc.needs_pass:
        raise Unprocessable("encrypted")
    if not doc.is_pdf:
        raise Unprocessable("not_pdf")
    if doc.page_count > max_pages:
        raise Unprocessable("too_many_pages")
    if page_count is not None and doc.page_count != page_count:
        raise Unprocessable("page_count_mismatch")
    return doc


@dataclass(frozen=True)
class Word:
    """A word of the text layer. `rect` is in unrotated page points, `disp` as displayed, and
    `frame` whichever of the two the page's text reads horizontally in: lines are found there."""

    index: int
    text: str
    rect: pymupdf.Rect
    disp: pymupdf.Rect
    frame: pymupdf.Rect


class PageGeometry:
    def __init__(self, page: pymupdf.Page) -> None:
        self.width: float = page.rect.width
        self.height: float = page.rect.height
        self._rotate = page.rotation_matrix
        self._derotate = page.derotation_matrix

    def to_display(self, rect: pymupdf.Rect) -> pymupdf.Rect:
        return pymupdf.Rect(rect) * self._rotate

    def to_unrotated(self, rect: pymupdf.Rect) -> pymupdf.Rect:
        return pymupdf.Rect(rect) * self._derotate

    def fractions(self, disp: pymupdf.Rect) -> tuple[float, float, float, float] | None:
        """A displayed rectangle as page fractions, clipped to the page; None when nothing of
        it is on the page."""
        x0 = round(max(0.0, disp.x0 / self.width), 6)
        y0 = round(max(0.0, disp.y0 / self.height), 6)
        x1 = round(min(1.0, disp.x1 / self.width), 6)
        y1 = round(min(1.0, disp.y1 / self.height), 6)
        if not (x0 < x1 and y0 < y1):
            return None
        return (x0, y0, x1, y1)

    def from_fractions(self, x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
        """A displayed rectangle in points."""
        return pymupdf.Rect(x0 * self.width, y0 * self.height, x1 * self.width, y1 * self.height)


#: Ligatures come out as their letters (`ﬁ` as `fi`), so words match as typed.
_WORD_FLAGS = pymupdf.TEXTFLAGS_WORDS & ~pymupdf.TEXT_PRESERVE_LIGATURES


def _wide(rects: list[pymupdf.Rect]) -> int:
    return sum(1 for r in rects if r.width > r.height)


def page_words(page: pymupdf.Page, geometry: PageGeometry | None = None) -> list[Word]:
    """Every word with its box. Words with no visible extent are left out."""
    geometry = geometry or PageGeometry(page)
    found: list[tuple[str, pymupdf.Rect]] = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words", sort=False, flags=_WORD_FLAGS):
        text = text.strip()
        rect = pymupdf.Rect(x0, y0, x1, y1)
        if text and not rect.is_empty:
            found.append((text, rect))
    displayed = [geometry.to_display(rect) for _, rect in found]
    # Text drawn upright on a page that's displayed rotated reads horizontally unrotated.
    unrotated = _wide([rect for _, rect in found]) > _wide(displayed)
    return [
        Word(i, text, rect, disp, rect if unrotated else disp)
        for i, ((text, rect), disp) in enumerate(zip(found, displayed, strict=True))
    ]
