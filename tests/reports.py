"""Synthetic lab reports with made-up personal details. Never real documents: this repository is
public. Each report lists the words that must be hidden and the words that must stay.
"""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

CSS = """
* { font-family: sans-serif; font-size: 10px; }
h1 { font-size: 14px; margin: 0 0 6px 0; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
td, th { padding: 2px 6px; text-align: left; }
p { margin: 2px 0; }
"""


@dataclass
class Report:
    pdf: bytes
    #: Words (as extracted) that must be under a region, with their type.
    hidden: dict[str, str]
    #: Words that must stay visible.
    kept: list[str]
    names: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    birth_years: list[int] = field(default_factory=list)


def _page(doc: pymupdf.Document, html: str, footer: str | None = None) -> pymupdf.Page:
    page = doc.new_page(width=595, height=842)
    page.insert_htmlbox(pymupdf.Rect(40, 40, 555, 760), html, css=CSS)
    if footer:
        page.insert_htmlbox(pymupdf.Rect(40, 790, 555, 820), f"<p>{footer}</p>", css=CSS)
    return page


def _table(header: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def english() -> Report:
    doc = pymupdf.open()
    header = """
    <h1>Alpha Dev Diagnostics</h1>
    <table>
      <tr><td>Patient: Anna Example</td><td>DOB: 03/14/1988</td><td>Sex: Female</td><td>Age: 38</td></tr>
      <tr><td>MRN: 00451278</td><td>Order #: 8812-3371</td><td colspan="2">Insurance policy: XQ-55102938</td></tr>
    </table>
    <p>Address: 742 Evergreen Terrace, Springfield, IL 62704</p>
    <p>Phone: +1 (555) 013-2468</p>
    <p>Email: anna.example@example.com</p>
    <p>Ordering physician: Dr. John Smith</p>
    <p>Collected: 09/21/2026 08:30</p>
    <p>Reported: 09/22/2026</p>
    """
    _page(
        doc,
        header
        + _table(
            ["Test", "Result", "Units", "Reference range"],
            [
                ["Hemoglobin", "132", "g/L", "120 - 150"],
                ["Ferritin", "18", "ng/mL", "15 - 150"],
                ["TSH", "2.1", "mIU/L", "0.4 - 4.0"],
                ["Glucose", "5.1", "mmol/L", "3.9 - 5.5"],
            ],
        ),
        footer="Anna Example · Page 1 of 2",
    )
    _page(
        doc,
        "<h1>Alpha Dev Diagnostics</h1><p>Patient: Anna Example</p>"
        + _table(
            ["Test", "Result", "Units", "Reference range"],
            [["Vitamin B12", "412", "pg/mL", "200 - 900"], ["Creatinine", "71", "umol/L", "45 - 84"]],
        )
        + "<p>Results reviewed and released by Maria Lopez on 09/22/2026.</p>",
        footer="Anna Example · Page 2 of 2",
    )
    return Report(
        pdf=doc.tobytes(),
        hidden={
            "Anna": "name",
            "Example": "name",
            "03/14/1988": "date_of_birth",
            "00451278": "id_number",
            "8812-3371": "id_number",
            "XQ-55102938": "policy_number",
            "Evergreen": "address",
            "Springfield,": "address",
            "62704": "address",
            "013-2468": "phone",
            "anna.example@example.com": "email",
            "John": "name",
            "Smith": "name",
            "Maria": "name",
            "Lopez": "name",
        },
        kept=[
            "Alpha",
            "Diagnostics",
            "Female",
            "38",
            "Hemoglobin",
            "132",
            "Ferritin",
            "18",
            "TSH",
            "2.1",
            "Glucose",
            "5.1",
            "09/21/2026",
            "09/22/2026",
            "Result",
            "Reference",
            "Vitamin",
            "412",
            "Creatinine",
            "71",
            "Dr.",
        ],
        names=["Anna Example"],
        emails=["anna.example@example.com"],
        birth_years=[1988],
    )


def russian() -> Report:
    doc = pymupdf.open()
    header = """
    <h1>ООО «Лаборатория Альфа-Дев»</h1>
    <table>
      <tr><td>Пациент: Иванова Анна Петровна</td><td>Пол: Ж</td><td>Возраст: 38 лет</td></tr>
      <tr><td>Дата рождения: 14.03.1988</td><td colspan="2">ИНЗ: 2026092112345</td></tr>
      <tr><td>Полис ОМС: 7700 1234 5678 9012</td><td colspan="2">СНИЛС: 123-456-789 01</td></tr>
    </table>
    <p>Адрес: г. Москва, ул. Примерная, д. 5, кв. 12</p>
    <p>Телефон: +7 (916) 123-45-67</p>
    <p>Эл. почта: anna.ivanova@example.ru</p>
    <p>Врач: Петров И.И.</p>
    <p>Дата взятия биоматериала: 21.09.2026</p>
    """
    _page(
        doc,
        header
        + _table(
            ["Исследование", "Результат", "Единицы", "Референсные значения"],
            [
                ["Гемоглобин", "132", "г/л", "120 - 150"],
                ["Ферритин", "18", "нг/мл", "15 - 150"],
                ["ТТГ", "2,1", "мЕд/л", "0,4 - 4,0"],
            ],
        )
        + "<p>Результаты проверены и одобрены: Сидорова Мария Ивановна</p>",
        footer="Иванова А.П., 14.03.1988 г.р. · стр. 1 из 1",
    )
    return Report(
        pdf=doc.tobytes(),
        hidden={
            "Иванова": "name",
            "Анна": "name",
            "Петровна": "name",
            "14.03.1988": "date_of_birth",
            "2026092112345": "id_number",
            "7700": "policy_number",
            "9012": "policy_number",
            "123-456-789": "id_number",
            "Примерная,": "address",
            "(916)": "phone",
            "123-45-67": "phone",
            "anna.ivanova@example.ru": "email",
            "Петров": "name",
            "И.И.": "name",
            "Сидорова": "name",
            "Мария": "name",
            "Ивановна": "name",
            "А.П.,": "name",
        },
        kept=[
            "«Лаборатория",
            "Ж",
            "38",
            "лет",
            "21.09.2026",
            "Гемоглобин",
            "132",
            "Ферритин",
            "18",
            "ТТГ",
            "2,1",
            "Результат",
            "Референсные",
        ],
        names=["Анна Иванова"],
        emails=["anna.ivanova@example.ru"],
        birth_years=[1988],
    )


def kazakh() -> Report:
    """A Kazakh lab's Russian report: an IIN, a profile name typed in Latin letters, and a birth
    date with no label."""
    doc = pymupdf.open()
    _page(
        doc,
        """
        <h1>ТОО «Бета Дев Лаб», Алматы</h1>
        <p>Сапарова Айгерим (14.03.1988)</p>
        <p>ИИН 880314400123</p>
        <p>Дата исследования: 21.09.2026</p>
        """
        + _table(
            ["Показатель", "Результат", "Норма"],
            [["Глюкоза", "5,1", "3,9 - 5,5"], ["Холестерин общий", "4,8", "до 5,2"]],
        ),
    )
    return Report(
        pdf=doc.tobytes(),
        hidden={
            "Сапарова": "name",
            "Айгерим": "name",
            "(14.03.1988)": "date_of_birth",
            "880314400123": "id_number",
        },
        kept=["«Бета", "Алматы", "21.09.2026", "Глюкоза", "5,1", "Холестерин", "4,8"],
        names=["Aigerim Saparova", "Daniyar"],
        emails=[],
        birth_years=[1988, 2015],
    )


def scanned() -> bytes:
    """A scan: a page-sized picture under invisible OCR text, as scanner apps save it."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 85), False)
    pix.clear_with(235)
    page.insert_image(page.rect, pixmap=pix)
    page.insert_text((50, 80), "Patient: Anna Example", fontname="helv", fontsize=11, render_mode=3)
    page.insert_text((50, 100), "Ferritin 18 ng/mL 15 - 150", fontname="helv", fontsize=11, render_mode=3)
    return doc.tobytes()


def letterhead() -> bytes:
    """A digital report printed over a page-sized letterhead picture: not a scan."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 85), False)
    pix.clear_with(250)
    page.insert_image(page.rect, pixmap=pix)
    page.insert_text((50, 80), "Patient: Anna Example", fontname="helv", fontsize=11)
    page.insert_text((50, 100), "Ferritin 18 ng/mL 15 - 150", fontname="helv", fontsize=11)
    return doc.tobytes()


def with_extras(pdf: bytes) -> bytes:
    """The report with what /apply must strip: metadata, an earlier saved version, an image,
    a note, a form field, a link, an attachment and bookmarks, each holding a made-up detail."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    doc.set_metadata({"author": "Anna Example", "title": "Results of Anna Example", "subject": "DOB 1988"})
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf>Anna Example</rdf></x:xmpmeta>")
    page = doc[0]
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.clear_with(20)
    page.insert_image(pymupdf.Rect(480, 40, 550, 110), pixmap=pix)
    page.add_text_annot((300, 60), "Call Anna Example back")
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_name = "patient"
    widget.field_value = "Anna Example"
    widget.rect = pymupdf.Rect(300, 700, 500, 720)
    page.add_widget(widget)
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(40, 40, 200, 60),
            "uri": "https://example.com/r/anna-example",
        }
    )
    doc.embfile_add("notes.txt", b"Anna Example, 03/14/1988")
    doc.set_toc([[1, "Anna Example", 1]])
    doc.insert_page(-1, text="Previous owner: Zelda Oldversion", fontname="helv", fontsize=8)
    return _incremental_without_last_page(doc.tobytes())


def _incremental_without_last_page(pdf: bytes) -> bytes:
    """The PDF with its last page deleted by an incremental update: the page, and the detail on
    it, stay in the file as an earlier saved version."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(pdf)
        doc = pymupdf.open(path)
        doc.delete_page(-1)
        doc.saveIncr()
        doc.close()
        return path.read_bytes()


def raw_contents(pdf: bytes) -> bytes:
    """Every byte of the file with each stream inflated where it can be: what's left in the file,
    earlier saved versions included, whatever a reader shows."""
    import re
    import zlib

    parts = [pdf]
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.DOTALL):
        try:
            parts.append(zlib.decompress(m.group(1)))
        except zlib.error:
            continue
    return b"\n".join(parts)


def holds(pdf: bytes, text: str) -> bool:
    """Whether the file still carries `text` anywhere, as plain or hex-encoded string bytes."""
    raw = raw_contents(pdf).lower()
    encoded = text.encode("latin-1", errors="ignore")
    return encoded.lower() in raw or encoded.hex().encode() in raw
