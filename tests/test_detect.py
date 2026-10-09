import pymupdf
import pytest

from labsense_redactor.contract import Known
from labsense_redactor.detect import detect
from labsense_redactor.detect.names import NameFinder
from labsense_redactor.document import open_pdf

from . import reports
from .conftest import occurrences


def _detect(report: reports.Report, names: NameFinder | None):
    known = Known(names=report.names, emails=report.emails, birth_years=report.birth_years)
    return detect(open_pdf(report.pdf, None), known, names)


@pytest.mark.parametrize("build", [reports.english, reports.russian, reports.kazakh])
def test_every_made_up_detail_is_hidden_and_the_results_stay(build, names: NameFinder) -> None:
    report = build()
    result = _detect(report, names)
    seen: dict[str, list[str | None]] = {}
    for text, hit in occurrences(report.pdf, result.regions):
        seen.setdefault(text, []).append(hit)
    missed = {w: t for w, t in report.hidden.items() if w not in seen or None in seen[w]}
    assert not missed, f"visible details: {missed}"
    wrong = {w: (t, seen[w]) for w, t in report.hidden.items() if t not in seen[w]}
    assert not wrong, f"details hidden as another type: {wrong}"
    hidden_kept = [w for w in report.kept if w in seen and any(seen[w])]
    assert not hidden_kept, f"kept words hidden: {hidden_kept}"
    assert not result.scanned
    assert all(r.type != "manual" for r in result.regions)


def test_the_summary_counts_each_detail_once(names: NameFinder) -> None:
    result = _detect(reports.english(), names)
    # Anna Example's name is on both pages' headers and footers, and still one name.
    assert result.summary == {
        "address": 1,
        "date_of_birth": 1,
        "email": 1,
        "id_number": 2,
        "name": 3,
        "phone": 1,
        "policy_number": 1,
    }
    assert sum(1 for r in result.regions if r.type == "name") > result.summary["name"]


def test_without_the_name_model_labels_and_known_details_still_hide_the_patient() -> None:
    report = reports.english()
    result = _detect(report, None)
    seen = {text: hit for text, hit in occurrences(report.pdf, result.regions) if hit}
    assert {"Anna", "Example", "John", "Smith", "03/14/1988"} <= seen.keys()
    assert "Maria" not in seen  # unlabeled and unknown: only the model finds it


def test_a_birth_date_needs_a_label_or_a_birth_year(names: NameFinder) -> None:
    report = reports.kazakh()
    report.birth_years = []
    result = _detect(report, names)
    seen = dict(occurrences(report.pdf, result.regions))
    assert seen["(14.03.1988)"] is None
    assert seen["21.09.2026"] is None


def test_known_names_match_across_alphabets_and_case_forms() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_htmlbox(
        pymupdf.Rect(40, 40, 555, 300),
        "<p>Выдано: Ивановой Анне</p><p>Copy for Anna Ivanova</p><p>Гемоглобин 132</p>",
    )
    result = detect(open_pdf(doc.tobytes(), None), Known(names=["Анна Иванова"]), None)
    hidden = {text for text, hit in occurrences(doc.tobytes(), result.regions) if hit}
    assert hidden == {"Ивановой", "Анне", "Anna", "Ivanova"}
    assert result.summary == {"name": 1}


def test_running_text_and_headings_are_not_labels(names: NameFinder) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_htmlbox(
        pymupdf.Rect(40, 40, 555, 400),
        "<p>Please consult your doctor About these results.</p>"
        "<table><tr><th>Name</th><th>Result</th><th>Units</th></tr>"
        "<tr><td>Hemoglobin</td><td>132</td><td>g/L</td></tr></table>"
        "<p>Patient Information</p><p>Sample collected 21.09.2026, time 08:30</p>"
        "<p>Provider: Alpha Dev Diagnostics</p><p>Client: Springfield Family Clinic</p>"
        "<p>Reference range 4.5 - 11.0, count 4 500 000</p>",
    )
    result = detect(open_pdf(doc.tobytes(), None), Known(), names)
    assert result.regions == []


def test_a_scan_under_an_ocr_layer_is_flagged(names: NameFinder) -> None:
    result = detect(open_pdf(reports.scanned(), None), Known(), names)
    assert result.scanned
    assert (result.regions, result.summary) == ([], {})


def test_a_digital_report_over_a_letterhead_picture_is_not_a_scan(names: NameFinder) -> None:
    result = detect(open_pdf(reports.letterhead(), None), Known(), names)
    assert not result.scanned
    assert result.summary == {"name": 1}


def test_text_that_cant_be_read_back_counts_as_a_scan() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_htmlbox(pymupdf.Rect(40, 40, 555, 300), "<p>" + "�" * 40 + " ab</p>")
    result = detect(open_pdf(doc.tobytes(), None), Known(), None)
    assert result.scanned


def test_a_rotated_page_gets_boxes_as_displayed() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "Patient: Anna Example", fontname="helv", fontsize=11)
    page.set_rotation(90)
    result = detect(open_pdf(doc.tobytes(), None), Known(), None)
    [region] = result.regions
    # Displayed landscape: the text, near the unrotated top-left, now sits at the top right.
    assert region.x0 > 0.8 and region.y0 < 0.3
    assert region.y1 - region.y0 > region.x1 - region.x0
