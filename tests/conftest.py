from collections.abc import Iterator

import pymupdf
import pytest

from labsense_redactor.contract import Region
from labsense_redactor.detect.names import NameFinder
from labsense_redactor.document import PageGeometry, page_words


@pytest.fixture(scope="session")
def names() -> NameFinder:
    return NameFinder.load()


def occurrences(pdf: bytes, regions: list[Region]) -> Iterator[tuple[str, str | None]]:
    """Each word of the PDF with the type of the region its center falls in (None: visible)."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    for number, page in enumerate(doc, 1):
        geometry = PageGeometry(page)
        for word in page_words(page, geometry):
            x = (word.disp.x0 + word.disp.x1) / 2 / geometry.width
            y = (word.disp.y0 + word.disp.y1) / 2 / geometry.height
            hit = next(
                (r.type for r in regions if r.page == number and r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1),
                None,
            )
            yield word.text, hit


def text_of(pdf: bytes) -> str:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)
