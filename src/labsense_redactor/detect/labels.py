"""Labeled fields (LabSense Lab Results → 4a step 2): `Patient`, `DOB`, `ФИО`, `Полис` and the
like, with the value that follows them on the same line, in the next cell, or under the label
when the label heads a column. Each type checks that the value has its shape, so a heading like
`Name  Result  Units` hides nothing.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from ..document import Word
from .lines import Line, Segment
from .patterns import DATES, YEAR
from .text import digit_count, has_digit, norm
from .vocabulary import STOPWORDS, TITLES

# (type, strong, alternatives). A weak label needs a colon, `№` or `#` after it, since the word
# alone is too common (`Name` heads a column of test names).
_LABELS: list[tuple[str, bool, str]] = [
    ("name", True, (
     r"patient(?:'s)?\s+name|name\s+of\s+(?:the\s+)?patient|patient|full\s+name|"
     r"surname|family\s+name|last\s+name|first\s+name|given\s+names?|middle\s+name|"
     r"(?:ordering|referring|requesting|attending)\s+(?:physician|doctor|provider|clinician)|"
     r"physician|doctor|collected\s+by|validated\s+by|verified\s+by|"
     r"approved\s+by|reported\s+by|signed\s+by|"
     r"ф\.?\s?и\.?\s?о\.?(?:\s+пациента)?|фамилия(?:\s+имя\s+отчество)?|отчество|пациент(?:ка)?|"
     r"(?:лечащий|направивший|ответственный)\s+врач|врач(?:-\w+)?|доктор|исполнитель|"
     r"выполнил[аи]?|проверил[аи]?|одобрил[аи]?|валидировал[аи]?|медсестра|"
     r"взятие\s+(?:биоматериала\s+)?(?:произвел[аи]?|выполнил[аи]?)"
    )),
    # `Provider` and `Client` alone often name the lab or the clinic, which stays visible.
    ("name", False, r"name|имя"),
    ("date_of_birth", True, (
     r"date\s+of\s+birth|birth\s*date|d\.?\s?o\.?\s?b\.?|"
     r"дата\s+рождения|д\.\s?р\.|д/р|год\s+рождения|г\.\s?р\."
    )),
    ("date_of_birth", False, r"born|рожд\.?"),
    ("address", True, (
     r"(?:home\s+|patient\s+|mailing\s+)?address|"
     r"адрес(?:\s+(?:проживания|регистрации|места\s+жительства|пациента))?|место\s+жительства|"
     r"проживает"
    )),
    ("phone", True, (
     r"(?:mobile|cell|home|work|contact)?\s*(?:phone|tel\.?|telephone)(?:\s+(?:number|no\.?))?|"
     r"mobile|cell|(?:контактный\s+|мобильный\s+)?телефон|тел\.|моб\.(?:\s*тел\.)?"
    )),
    ("email", True, r"e-?mail(?:\s+address)?|эл\.?\s*почта|электронная\s+почта|e-mail"),
    ("id_number", True, (
     r"patient\s+id|mrn|medical\s+record(?:\s+(?:number|no\.?))?|"
     r"(?:record|chart|case)\s+(?:number|no\.?)|passport(?:\s+(?:number|no\.?))?|national\s+id|"
     r"ssn|social\s+security(?:\s+number)?|(?:order|requisition|accession|specimen|sample|lab)\s+"
     r"(?:id|number|no\.?|#)|requisition|accession|barcode|"
     r"паспорт|снилс|иин|инн|инз|"
     r"(?:номер|№)\s+(?:заказа|пробы|образца|направления|заявки|карты|медкарты|истории\s+болезни)|"
     r"(?:заказ|проба|образец|направление|заявка)\s+№|"
     r"(?:медицинская|амбулаторная|мед\.)\s*карта|история\s+болезни|"
     r"(?:код|id|идентификатор)\s+пациента|штрих-?код"
    )),
    ("id_number", False, r"id|order|sample|specimen|record|заказ|проба|карта"),
    ("policy_number", True, (
     r"(?:insurance\s+)?policy(?:\s+(?:number|no\.?))?|"
     r"insurance(?:\s+(?:number|no\.?|id))?|member\s+id|subscriber\s+id|"
     r"(?:страховой\s+)?полис(?:\s+(?:омс|дмс))?|№\s+полиса|номер\s+полиса"
    )),
]  # fmt: skip

_WEAK_SEP = r"\s*(?:[:：]|№|#)"
_STRONG_SEP = r"\s*[:：]?"


def _compile(alternatives: str, strong: bool) -> re.Pattern[str]:
    sep = _STRONG_SEP if strong else _WEAK_SEP
    return re.compile(rf"(?<![\w\-])(?:{alternatives})(?![\w\-]){sep}", re.IGNORECASE)


LABELS = [(type_, _compile(alts, strong)) for type_, strong, alts in _LABELS]

NAME_TOKEN = re.compile(r"^(?:[A-ZА-ЯЁ][\w'’\-]*\.?|(?:[A-ZА-ЯЁ]\.){1,3})[,;]?$")
_PARTICLES = frozenset(
    [
        "van",
        "von",
        "der",
        "den",
        "de",
        "da",
        "di",
        "del",
        "la",
        "le",
        "bin",
        "ibn",
        "al",
        "el",
        "оглы",
        "кызы",
        "улы",
    ]
)
_NUMBER_SIGNS = frozenset(["№", "#", "no", "nr", "n", "n°"])
_PHONE_TOKEN = re.compile(r"^[+\d()\-–.]+[,;]?$")
_CODE_TOKEN = re.compile(r"^[A-ZА-ЯЁ]{1,4}-?$")


@dataclass(frozen=True)
class LabelHit:
    start: int
    end: int
    type: str


def label_hits(segment: Segment) -> list[LabelHit]:
    """Every label in a segment; where two overlap, the longer one (`Patient ID` over `Patient`)."""
    hits = [
        LabelHit(m.start(), m.end(), type_)
        for type_, pattern in LABELS
        for m in pattern.finditer(segment.text)
    ]
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    kept: list[LabelHit] = []
    for hit in hits:
        if kept and hit.start < kept[-1].end:
            continue
        kept.append(hit)
    return kept


def name_value(words: list[Word]) -> list[Word]:
    value: list[Word] = []
    for word in words:
        text = word.text
        key = norm(text)
        if not value and key in TITLES:
            continue
        if text.endswith(":") or key in STOPWORDS:
            break
        if NAME_TOKEN.match(text) or (value and key in _PARTICLES):
            value.append(word)
            if text.endswith((",", ";")) or len(value) == 5:
                break
        else:
            break
    while value and norm(value[-1].text) in _PARTICLES:
        value.pop()
    return value


def date_of_birth_value(words: list[Word]) -> list[Word]:
    segment = Segment(words[:6])
    for pattern in DATES:
        m = pattern.search(segment.text)
        if m and segment.first_word_at(m.start()) <= 3:
            return segment.words_in(m.start(), m.end())
    m = YEAR.search(segment.text)
    if m and segment.first_word_at(m.start()) <= 1:
        return segment.words_in(m.start(), m.end())
    return []


def address_value(words: list[Word]) -> list[Word]:
    value: list[Word] = []
    for word in words[:25]:
        if word.text.endswith(":") and value:
            break
        value.append(word)
    return value if any(any(ch.isalnum() for ch in w.text) for w in value) else []


def phone_value(words: list[Word]) -> list[Word]:
    value: list[Word] = []
    for word in words[:8]:
        if not _PHONE_TOKEN.match(word.text):
            break
        value.append(word)
    return value if digit_count("".join(w.text for w in value)) >= 7 else []


def email_value(words: list[Word]) -> list[Word]:
    return [w for w in words[:2] if "@" in w.text][:1]


def number_value(words: list[Word]) -> list[Word]:
    rest = list(words)
    while rest and (norm(rest[0].text) in _NUMBER_SIGNS or norm(rest[0].text) in ("омс", "дмс")):
        rest.pop(0)
    value: list[Word] = []
    for i, word in enumerate(rest[:5]):
        follows_digit = i + 1 < len(rest) and has_digit(rest[i + 1].text)
        if has_digit(word.text) or (_CODE_TOKEN.match(word.text) and follows_digit):
            value.append(word)
        else:
            break
    return value if digit_count("".join(w.text for w in value)) >= 3 else []


_VALUES = {
    "name": name_value,
    "date_of_birth": date_of_birth_value,
    "address": address_value,
    "phone": phone_value,
    "email": email_value,
    "id_number": number_value,
    "policy_number": number_value,
}


def _value_below(lines: list[Line], line_index: int, label: list[Word]) -> list[Word]:
    """The value under a label that heads a column: the segment of the next line that sits
    under it."""
    line = lines[line_index]
    x0 = min(w.frame.x0 for w in label) - line.height
    x1 = max(w.frame.x1 for w in label) + 3 * line.height
    for below in lines[line_index + 1 : line_index + 3]:
        if below.top - line.bottom > 1.5 * line.height:
            break
        for segment in below.segments:
            if segment.words[0].frame.x0 < x1 and segment.words[-1].frame.x1 > x0:
                hits = label_hits(segment)
                end = segment.first_word_at(hits[0].start) if hits else len(segment.words)
                return segment.words[:end]
    return []


#: A date followed by `г.р.` (`12.03.1988 г.р.`): the label comes after the birth date.
_BORN_SUFFIX = re.compile(r"\s*(?:г\.?\s?р\.?|года\s+рождения)(?![\w])", re.IGNORECASE)


def _suffixed_birth_dates(segment: Segment) -> Iterator[list[Word]]:
    for pattern in [*DATES, YEAR]:
        for m in pattern.finditer(segment.text):
            if _BORN_SUFFIX.match(segment.text, m.end()):
                yield segment.words_in(m.start(), m.end())


def _accepted(segment: Segment, hit: LabelHit) -> bool:
    """A name or address label must look like one: capitalized, or followed by a colon (`the
    patient`, `your doctor` in running text aren't labels). The other types' values need a
    date, digits or an `@`, which running text rarely has."""
    if hit.type not in ("name", "address"):
        return True
    return segment.text[hit.start].isupper() or ":" in segment.text[hit.start : hit.end]


def find(lines: list[Line]) -> Iterator[tuple[str, list[Word]]]:
    """(type, words) of each labeled value on a page."""
    for line_index, line in enumerate(lines):
        for seg_index, segment in enumerate(line.segments):
            for words in _suffixed_birth_dates(segment):
                yield "date_of_birth", words
            hits = label_hits(segment)
            for hit_index, hit in enumerate(hits):
                if not _accepted(segment, hit):
                    continue
                start = segment.first_word_at(hit.end)
                end_offset = hits[hit_index + 1].start if hit_index + 1 < len(hits) else None
                end = segment.first_word_at(end_offset) if end_offset is not None else len(segment.words)
                extract = _VALUES[hit.type]
                value = extract(segment.words[start:end])
                if not value:
                    # The value is in the next cell, or under the label heading a column.
                    if end == len(segment.words) and seg_index + 1 < len(line.segments):
                        following = line.segments[seg_index + 1]
                        next_hits = label_hits(following)
                        stop = (
                            following.first_word_at(next_hits[0].start) if next_hits else len(following.words)
                        )
                        value = extract(following.words[:stop])
                    if not value:
                        label = segment.words_in(hit.start, hit.end)
                        value = extract(_value_below(lines, line_index, label))
                if value:
                    yield hit.type, value
