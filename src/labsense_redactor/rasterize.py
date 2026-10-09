"""`/rasterize`: page images with the regions painted black, for the fallback to the image path
(LabSense Lab Results → 3b step 4). The user paints over whatever else is left."""

import pymupdf

from .contract import Region
from .document import open_pdf
from .errors import Unprocessable

#: Sharp enough for the AI to read small print, small enough for the phone.
_DPI = 150
_MAX_SIDE_PX = 2400
_JPEG_QUALITY = 85


def render(data: bytes, regions: list[Region], pages: list[int], max_pages: int = 50) -> dict[int, bytes]:
    doc = open_pdf(data, None, max_pages)
    page_count = doc.page_count
    out: dict[int, bytes] = {}
    for number in pages:
        if not 1 <= number <= page_count:
            raise Unprocessable("page_outside_document")
        page = doc[number - 1]
        longest = max(page.rect.width, page.rect.height)
        zoom = min(_DPI / 72, _MAX_SIDE_PX / longest)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB)
        for region in regions:
            if region.page != number:
                continue
            box = pymupdf.IRect(
                int(region.x0 * pix.width),
                int(region.y0 * pix.height),
                int(region.x1 * pix.width + 0.999),
                int(region.y1 * pix.height + 0.999),
            )
            pix.set_rect(box, (0, 0, 0))
        out[number] = pix.tobytes("jpeg", jpg_quality=_JPEG_QUALITY)
    return out
