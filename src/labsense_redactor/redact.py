"""`/apply`: true redaction, then the check (LabSense Lab Results → 4a steps 3 and 5).

Under each region the text is removed (not covered), and so are images and the drawings it fully
covers; a black block marks the place. Every image is then removed from the copy: the AI reads
the text, and an image's pixels (a QR code, a stamp, a signature) can't be checked. Metadata,
XMP, form fields, annotations, links, attachments, JavaScript, bookmarks and earlier saved
versions go too.

The check opens the written copy again and fails when any of these remain: text inside a region,
more copies of a hidden word than were left visible on purpose, an image, an annotation, a form
field, a link, an attachment, metadata, or a different page count.
"""

import logging
from collections import Counter
from dataclasses import dataclass

import pymupdf

from .contract import Region
from .detect.text import norm
from .document import PageGeometry, Word, open_pdf, page_words
from .errors import Unprocessable

log = logging.getLogger(__name__)

_BLACK = (0, 0, 0)
#: How far a block's removal area keeps from a word that stays visible, in points.
_CLEARANCE = 0.01


@dataclass(frozen=True)
class Redacted:
    pdf: bytes
    verified: bool


def _region_rect(geometry: PageGeometry, region: Region) -> pymupdf.Rect:
    return geometry.from_fractions(region.x0, region.y0, region.x1, region.y1)


def _center_in(word: Word, rect: pymupdf.Rect) -> bool:
    x = (word.disp.x0 + word.disp.x1) / 2
    y = (word.disp.y0 + word.disp.y1) / 2
    return bool(rect.x0 <= x <= rect.x1 and rect.y0 <= y <= rect.y1)


def _clear_of(rect: pymupdf.Rect, keep: list[pymupdf.Rect]) -> pymupdf.Rect:
    """The removal area pulled back from words that stay visible. MuPDF removes every character
    whose box touches the area, and with tight line spacing the boxes of two lines overlap."""
    rect = pymupdf.Rect(rect)
    for other in keep:
        if not rect.intersects(other):
            continue
        center = (rect.y0 + rect.y1) / 2
        if (other.y0 + other.y1) / 2 > center and other.y0 > rect.y0:
            rect.y1 = min(rect.y1, other.y0 - _CLEARANCE)
        elif (other.y0 + other.y1) / 2 < center and other.y1 < rect.y1:
            rect.y0 = max(rect.y0, other.y1 + _CLEARANCE)
        elif (other.x0 + other.x1) / 2 > (rect.x0 + rect.x1) / 2:
            rect.x1 = min(rect.x1, other.x0 - _CLEARANCE)
        else:
            rect.x0 = max(rect.x0, other.x1 + _CLEARANCE)
    return rect


def apply(data: bytes, regions: list[Region], max_pages: int = 50) -> Redacted:
    doc = open_pdf(data, None, max_pages)
    page_count = doc.page_count
    before: list[list[Word]] = []
    hidden: list[list[Word]] = []
    by_page: dict[int, list[Region]] = {}
    for region in regions:
        if region.page > page_count:
            raise Unprocessable("region_outside_document")
        by_page.setdefault(region.page, []).append(region)

    for number, page in enumerate(doc, 1):
        geometry = PageGeometry(page)
        words = page_words(page, geometry)
        boxes = [_region_rect(geometry, r) for r in by_page.get(number, [])]
        under = [w for w in words if any(_center_in(w, box) for box in boxes)]
        before.append(words)
        hidden.append(under)
        under_ids = {w.index for w in under}
        keep = [w.rect for w in words if w.index not in under_ids]
        for box in boxes:
            area = _clear_of(geometry.to_unrotated(box), keep)
            if area.is_empty:
                continue
            page.add_redact_annot(area, fill=_BLACK, cross_out=False)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        _remove_images(page)
        _remove_annotations(page)

    doc.scrub(
        attached_files=True,
        clean_pages=True,
        embedded_files=True,
        # An OCR layer is the text the AI reads; it was checked like any other text.
        hidden_text=False,
        javascript=True,
        metadata=True,
        redactions=True,
        redact_images=0,
        remove_links=True,
        reset_fields=True,
        reset_responses=True,
        thumbnails=True,
        xml_metadata=True,
    )
    doc.set_metadata({})
    doc.del_xml_metadata()
    doc.set_toc([])
    # A full rewrite: unreferenced objects (earlier saved versions among them) are dropped.
    pdf = doc.tobytes(garbage=4, deflate=True, clean=True)
    failure = verify(pdf, page_count, by_page, before, hidden)
    if failure:
        log.info("redaction not verified", extra={"reason": failure})
    return Redacted(pdf=pdf, verified=failure is None)


def _remove_images(page: pymupdf.Page) -> None:
    """Every image, inline ones too, without touching the text over it."""
    area = page.rect * page.derotation_matrix
    found = False
    for info in page.get_image_info():
        bbox = pymupdf.Rect(info["bbox"]) & area
        if not bbox.is_empty:
            page.add_redact_annot(bbox, fill=False, cross_out=False)
            found = True
    if found:
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_NONE,
        )


def _remove_annotations(page: pymupdf.Page) -> None:
    # By xref: an Annot object goes stale once another one on the page is deleted.
    for xref in [widget.xref for widget in page.widgets()]:
        page.delete_widget(page.load_widget(xref))
    for xref in [annot.xref for annot in page.annots()]:
        page.delete_annot(page.load_annot(xref))
    for link in page.get_links():
        page.delete_link(link)


def verify(
    pdf: bytes,
    page_count: int,
    regions: dict[int, list[Region]],
    before: list[list[Word]],
    hidden: list[list[Word]],
) -> str | None:
    """None when the copy passes; otherwise the reason, a fixed word (never document text)."""
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
    except (RuntimeError, ValueError):
        return "unreadable"
    if doc.page_count != page_count:
        return "page_count"
    if any(value for key, value in doc.metadata.items() if key not in ("format", "encryption")):
        return "metadata"
    if doc.get_xml_metadata() or doc.embfile_count():
        return "metadata"
    hidden_words = Counter(norm(w.text) for page in hidden for w in page if norm(w.text))
    hidden_ids = [{w.index for w in page} for page in hidden]
    visible = Counter(
        norm(w.text)
        for words, ids in zip(before, hidden_ids, strict=True)
        for w in words
        if w.index not in ids
    )
    after: Counter[str] = Counter()
    for number, page in enumerate(doc, 1):
        if page.first_annot is not None or page.first_widget is not None or page.get_links():
            return "annotations"
        if page.get_images(full=True) or page.get_image_info():
            return "images"
        geometry = PageGeometry(page)
        words = page_words(page, geometry)
        boxes = [_region_rect(geometry, r) for r in regions.get(number, [])]
        if any(_center_in(w, box) for w in words for box in boxes):
            return "text_in_region"
        after.update(norm(w.text) for w in words)
    if any(after[word] > visible[word] for word in hidden_words):
        return "hidden_text"
    return None
