"""Pages whose text layer can't be trusted: a scan under an invisible OCR layer, whose picture
may show details the OCR misread, or text that can't be read back. One such page sends the whole
upload to painting, as a mixed PDF takes the image path (LabSense Lab Results → 3).
"""

import unicodedata

import pymupdf

#: An image covering this share of the page makes it a scan when its text is invisible.
_SCAN_IMAGE_SHARE = 0.5
_INVISIBLE_SHARE = 0.5
_UNREADABLE_SHARE = 0.2
#: Vector paths on a page with no text: text drawn as outlines, which can't be read.
_OUTLINED_TEXT_PATHS = 50
_REPLACEMENT = 0xFFFD

#: The scripts and signs of an English, Russian or Kazakh lab report. A text layer without a
#: Unicode map comes out as glyph numbers: replacement and control characters, IPA letters.
_READABLE = (
    (0x20, 0x7E),  # ASCII
    (0xA0, 0x24F),  # Latin-1, Latin Extended-A and -B
    (0x370, 0x3FF),  # Greek (µ, α)
    (0x400, 0x52F),  # Cyrillic and its supplement (Kazakh letters)
    (0x2000, 0x22FF),  # punctuation, super- and subscripts, currency, №, ℃, arrows, ≤ ≥
    (0x2460, 0x27BF),  # enclosed numbers, shapes, symbols, check marks
    (0xFB00, 0xFB06),  # Latin ligatures
)


def _unreadable(code: int) -> bool:
    if code == _REPLACEMENT or unicodedata.category(chr(code)) in ("Co", "Cn", "Cc"):
        return True
    return not any(low <= code <= high for low, high in _READABLE)


def is_scan(page: pymupdf.Page) -> bool:
    area = page.rect * page.derotation_matrix
    page_area = abs(area)
    big_image = any(
        abs(pymupdf.Rect(info["bbox"]) & area) >= _SCAN_IMAGE_SHARE * page_area
        for info in page.get_image_info()
    )
    total = invisible = unreadable = 0
    for span in page.get_texttrace():
        codes = [char[0] for char in span["chars"] if not chr(char[0]).isspace()]
        total += len(codes)
        unreadable += sum(_unreadable(code) for code in codes)
        if span["type"] == 3 or span.get("opacity", 1) == 0:
            invisible += len(codes)
    if total == 0:
        return big_image or len(page.get_cdrawings()) >= _OUTLINED_TEXT_PATHS
    if unreadable / total >= _UNREADABLE_SHARE:
        return True
    return big_image and invisible / total >= _INVISIBLE_SHARE
