"""The finders' rules on small inputs."""

from datetime import date

import pymupdf
import pytest

from labsense_redactor.contract import Known
from labsense_redactor.detect import detect, known, patterns
from labsense_redactor.detect.lines import Segment, build_lines
from labsense_redactor.detect.names import NameFinder
from labsense_redactor.detect.text import norm, to_cyrillic, to_latin
from labsense_redactor.document import Word, open_pdf, page_words

from .conftest import occurrences


def _segment(text: str) -> Segment:
    words = []
    for i, token in enumerate(text.split()):
        rect = pymupdf.Rect(i * 50, 0, i * 50 + 40, 10)
        words.append(Word(i, token, rect, rect, rect))
    return Segment(words)


def _found(text: str) -> list[tuple[str, str]]:
    segment = _segment(text)
    return [(m.type, segment.text[m.start : m.end]) for m in patterns.find(segment)]


@pytest.mark.parametrize(
    ("text", "type_"),
    [
        ("+7 (916) 123-45-67", "phone"),
        ("8 800 555-35-35", "phone"),
        ("89161234567", "phone"),
        ("+1 555 013 2468", "phone"),
        ("(555) 013-2468", "phone"),
        ("123-456-789 01", "id_number"),
        ("123-45-6789", "id_number"),
        ("7700 1234 5678 9012", "policy_number"),
        ("7700123456789012", "policy_number"),
        ("880314400123", "id_number"),
        ("2026092112345", "id_number"),
        ("anna.example@example.com", "email"),
    ],
)
def test_shapes(text: str, type_: str) -> None:
    assert _found(text) == [(type_, text)]


@pytest.mark.parametrize(
    "text",
    [
        "21.09.2026",
        "2026-09-21 08:30",
        "120 - 150",
        "3,9 - 5,5",
        "0.4-4.0",
        "4 500 000",
        "15/09/2026",
        "132 g/L",
        "1:160",
        "12345678",
    ],
)
def test_results_are_not_shapes(text: str) -> None:
    assert _found(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("г. Москва, ул. Примерная, д. 5, кв. 12", "г. Москва, ул. Примерная, д. 5, кв. 12"),
        ("Лаборатория Альфа, 123456, г. Москва, Ленинский пр-т, 5", "123456, г. Москва, Ленинский пр-т, 5"),
        ("742 Evergreen Terrace, Springfield, IL 62704", "742 Evergreen Terrace, Springfield, IL 62704"),
    ],
)
def test_addresses_run_from_their_first_marker(text: str, expected: str) -> None:
    assert _found(text) == [("address", expected)]


def test_a_city_alone_is_not_an_address() -> None:
    assert _found("г. Москва") == []
    assert _found("Alpha Dev Diagnostics, Springfield") == []


def test_transliteration() -> None:
    assert to_cyrillic("ivanova") == "иванова"
    assert to_cyrillic("shchukina") == "щукина"
    assert to_latin("щукина") == "shchukina"
    assert norm("Ёлкина,") == "елкина"


def test_known_name_forms() -> None:
    [name] = known.known_names(["Анна Иванова"])
    forms = name.tokens[1].forms
    assert {"иванова", "ивановой", "иванову", "ivanova"} <= forms
    assert {"анна", "анны", "анне", "анну", "anna"} <= name.tokens[0].forms


def test_birth_dates_in_a_known_year() -> None:
    page = pymupdf.open().new_page()
    page.insert_text((50, 50), "12.03.1988 / 12.03.88 / 21.09.2026 / 14 March 1988 / 1988", fontname="helv")
    lines = build_lines(page_words(page))
    found = [[w.text for w in words] for words in known.find_birth_dates(lines, [1988], date(2026, 10, 9))]
    assert found == [["12.03.1988"], ["12.03.88"], ["14", "March", "1988"]]


def test_a_two_digit_year_that_could_be_recent_is_not_a_birth_date() -> None:
    page = pymupdf.open().new_page()
    page.insert_text((50, 50), "12.03.20", fontname="helv")
    lines = build_lines(page_words(page))
    assert list(known.find_birth_dates(lines, [2020], date(2026, 10, 9))) == []


def _hidden(html: str, names: NameFinder | None, **known_details: list) -> set[str]:
    doc = pymupdf.open()
    doc.new_page().insert_htmlbox(pymupdf.Rect(40, 40, 555, 800), html)
    pdf = doc.tobytes()
    result = detect(open_pdf(pdf, None), Known(**known_details), names)
    return {text for text, hit in occurrences(pdf, result.regions) if hit}


def test_a_label_heading_a_column_hides_the_value_under_it(names: NameFinder) -> None:
    html = (
        "<table><tr><th>ФИО</th><th>Дата рождения</th><th>Пол</th></tr>"
        "<tr><td>Иванова Анна Петровна</td><td>14.03.1988</td><td>Ж</td></tr></table>"
    )
    assert _hidden(html, names) == {"Иванова", "Анна", "Петровна", "14.03.1988"}


def test_names_in_capitals(names: NameFinder) -> None:
    assert _hidden("<p>PATIENT: IVANOVA ANNA</p><p>TSH 2.1 mIU/L</p>", names) == {"IVANOVA", "ANNA"}


def test_labels_in_other_forms(names: NameFinder) -> None:
    html = (
        "<p>Ф.И.О.: Сидоров Пётр</p><p>Д.р.: 01.02.1975</p><p>Иванов И.И., 1980 г.р.</p>"
        "<p>Specimen ID: AB 123456</p><p>Номер заказа: 556677</p><p>№ медкарты 4411</p>"
        "<p>Тел.: 8 (727) 300-10-20</p>"
    )
    assert _hidden(html, names) == {
        "Сидоров", "Пётр", "01.02.1975", "Иванов", "И.И.,", "1980", "AB", "123456", "556677",
        "4411", "8", "(727)", "300-10-20",
    }  # fmt: skip


@pytest.fixture
def results_only() -> str:
    rows_en = [
        ("Hemoglobin", "132", "g/L", "120 - 150"), ("Red Blood Cells", "4.5", "x10^12/L", "3.8 - 5.1"),
        ("White Blood Cells", "6.2", "x10^9/L", "4.0 - 10.0"), ("Platelets", "250", "x10^9/L", "150 - 400"),
        ("Mean Corpuscular Volume", "88", "fL", "80 - 100"), ("Ferritin", "18", "ng/mL", "15 - 150"),
        ("Vitamin D, 25-Hydroxy", "32", "ng/mL", "30 - 100"), ("Thyroid Stimulating Hormone", "2.1", "mIU/L", "0.4 - 4.0"),
        ("Free T4", "15.2", "pmol/L", "12 - 22"), ("Alanine Aminotransferase", "21", "U/L", "< 33"),
        ("Aspartate Aminotransferase", "19", "U/L", "< 32"), ("C-Reactive Protein", "1.2", "mg/L", "< 5"),
        ("Hemoglobin A1c", "5.4", "%", "4.0 - 5.6"), ("LDL Cholesterol", "2.9", "mmol/L", "< 3.0"),
        ("Antinuclear Antibodies", "1:160", "titer", "< 1:80"), ("Epstein-Barr Virus IgG", "Positive", "", "Negative"),
        ("Anti-Mullerian Hormone", "2.3", "ng/mL", "1.0 - 3.5"), ("Helicobacter Pylori IgG", "Negative", "", "Negative"),
    ]  # fmt: skip
    rows_ru = [
        ("Гемоглобин", "132", "г/л", "120 - 150"), ("Эритроциты", "4,5", "10^12/л", "3,8 - 5,1"),
        ("Лейкоциты", "6,2", "10^9/л", "4,0 - 10,0"), ("Скорость оседания эритроцитов", "8", "мм/ч", "2 - 20"),
        ("Ферритин", "18", "нг/мл", "15 - 150"), ("Витамин B12 (цианокобаламин)", "412", "пг/мл", "197 - 771"),
        ("Тиреотропный гормон", "2,1", "мЕд/л", "0,4 - 4,0"), ("Антитела к тиреопероксидазе", "12", "МЕ/мл", "< 34"),
        ("Аланинаминотрансфераза (АЛТ)", "21", "Ед/л", "< 33"), ("Глюкоза, кровь", "5,1", "ммоль/л", "3,9 - 5,5"),
        ("Холестерин общий", "4,8", "ммоль/л", "< 5,2"), ("Антимюллеров гормон", "2,3", "нг/мл", "1,0 - 3,5"),
        ("Вирус Эпштейна-Барр, IgG", "положительно", "", "отрицательно"), ("Мочевая кислота", "310", "мкмоль/л", "150 - 350"),
    ]  # fmt: skip
    table = "<table><tr><th>Test</th><th>Result</th><th>Units</th><th>Reference</th></tr>"
    for row in [*rows_en, *rows_ru]:
        table += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    return (
        "<h1>Alpha Dev Diagnostics / Лаборатория Альфа-Дев</h1><p>Sex: Female. Age: 38. Пол: Ж. Возраст: 38 лет</p>"
        "<p>Collected 21.09.2026 08:30, reported 22.09.2026. Дата взятия 21.09.2026</p>"
        f"{table}<p>Method: Chemiluminescence immunoassay. Метод: ИХЛА.</p>"
        "<p>Results are not a diagnosis. Consult your doctor. Результаты не являются диагнозом.</p>"
    )


def test_a_report_without_personal_details_keeps_everything(names: NameFinder, results_only: str) -> None:
    assert _hidden(results_only, names, birth_years=[1988]) == set()
