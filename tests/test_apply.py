import pymupdf
import pytest

from labsense_redactor import redact
from labsense_redactor.contract import Known, Region
from labsense_redactor.detect import detect
from labsense_redactor.detect.names import NameFinder
from labsense_redactor.document import open_pdf

from . import reports
from .conftest import text_of


def _redact(pdf: bytes, known: Known, names: NameFinder | None) -> tuple[list[Region], redact.Redacted]:
    regions = detect(open_pdf(pdf, None), known, names).regions
    return regions, redact.apply(pdf, regions)


@pytest.mark.parametrize("build", [reports.english, reports.russian, reports.kazakh])
def test_the_copy_is_verified_and_keeps_the_results(build, names: NameFinder) -> None:
    report = build()
    known = Known(names=report.names, emails=report.emails, birth_years=report.birth_years)
    _, redacted = _redact(report.pdf, known, names)
    assert redacted.verified
    words = text_of(redacted.pdf).split()
    assert not [w for w in report.hidden if w in words]
    assert not [w for w in report.kept if w not in words]
    assert pymupdf.open(stream=redacted.pdf).page_count == pymupdf.open(stream=report.pdf).page_count


def test_everything_else_that_could_hold_a_detail_is_stripped(names: NameFinder) -> None:
    pdf = reports.with_extras(reports.english().pdf)
    assert reports.holds(pdf, "Zelda Oldversion")  # the earlier saved version is in the input
    _, redacted = _redact(pdf, Known(names=["Anna Example"]), names)
    assert redacted.verified
    doc = pymupdf.open(stream=redacted.pdf)
    assert not any(v for k, v in doc.metadata.items() if k not in ("format", "encryption"))
    assert not doc.get_xml_metadata()
    assert doc.embfile_count() == 0
    assert doc.get_toc() == []
    for page in doc:
        assert page.first_annot is None and page.first_widget is None
        assert page.get_links() == []
        assert page.get_images(full=True) == [] and page.get_image_info() == []
    for detail in ("Anna Example", "Zelda Oldversion", "anna-example", "03/14/1988", "Anna", "Zelda"):
        assert not reports.holds(redacted.pdf, detail), detail


def test_the_line_below_survives_tight_line_spacing() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Patient: Anna Example", fontname="helv", fontsize=12)
    page.insert_text((100, 110), "Ferritin 18 ng/mL", fontname="helv", fontsize=12)
    regions, redacted = _redact(doc.tobytes(), Known(), None)
    assert [r.type for r in regions] == ["name"]
    assert redacted.verified
    assert text_of(redacted.pdf).split() == ["Patient:", "Ferritin", "18", "ng/mL"]


def test_a_rotated_page_is_redacted_where_the_user_saw_the_block() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 80), "Patient: Anna Example", fontname="helv", fontsize=11)
    page.insert_text((60, 120), "Ferritin 18", fontname="helv", fontsize=11)
    page.set_rotation(270)
    _, redacted = _redact(doc.tobytes(), Known(), None)
    assert redacted.verified
    assert text_of(redacted.pdf).split() == ["Patient:", "Ferritin", "18"]


def test_a_manual_block_is_redacted_too() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((100, 100), "Hemoglobin 132 Secretword", fontname="helv", fontsize=12)
    word = next(w for w in page.get_text("words") if w[4] == "Secretword")
    box = Region(
        page=1, x0=word[0] / 600, y0=word[1] / 800, x1=word[2] / 600, y1=word[3] / 800, type="manual"
    )
    redacted = redact.apply(doc.tobytes(), [box])
    assert redacted.verified
    assert text_of(redacted.pdf).split() == ["Hemoglobin", "132"]


def test_a_copy_that_still_shows_a_hidden_word_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Patient: Anna Example", fontname="helv", fontsize=12)
    regions = detect(open_pdf(doc.tobytes(), None), Known(), None).regions
    # As if MuPDF had left the text in place.
    monkeypatch.setattr(redact, "_clear_of", lambda rect, keep: pymupdf.Rect())
    assert not redact.apply(doc.tobytes(), regions).verified


def test_a_hidden_word_shown_elsewhere_on_purpose_passes() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((100, 100), "Anna", fontname="helv", fontsize=12)
    page.insert_text((100, 200), "Anna", fontname="helv", fontsize=12)
    first = page.get_text("words")[0]
    box = Region(
        page=1, x0=first[0] / 600, y0=first[1] / 800, x1=first[2] / 600, y1=first[3] / 800, type="name"
    )
    redacted = redact.apply(doc.tobytes(), [box])
    assert redacted.verified
    assert text_of(redacted.pdf).split() == ["Anna"]
