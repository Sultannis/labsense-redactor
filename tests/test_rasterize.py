import pymupdf

from labsense_redactor.contract import Region
from labsense_redactor.rasterize import render


def test_pages_are_jpegs_with_the_regions_painted() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "Patient: Anna Example", fontname="helv", fontsize=11)
    region = Region(page=1, x0=0.2, y0=0.05, x1=0.5, y1=0.15, type="name")
    [jpeg] = render(doc.tobytes(), [region], [1]).values()
    image = pymupdf.Pixmap(jpeg)
    assert jpeg[:2] == b"\xff\xd8"
    assert abs(image.width - 595 * 150 / 72) <= 1 and abs(image.height - 842 * 150 / 72) <= 1
    assert image.pixel(int(0.35 * image.width), int(0.1 * image.height)) == (0, 0, 0)
    assert image.pixel(int(0.8 * image.width), int(0.8 * image.height)) == (255, 255, 255)


def test_a_rotated_page_is_drawn_as_displayed() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.set_rotation(90)
    [jpeg] = render(doc.tobytes(), [], [1]).values()
    image = pymupdf.Pixmap(jpeg)
    assert image.width > image.height
