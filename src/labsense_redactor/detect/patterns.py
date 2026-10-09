"""Personal details recognized by their shape alone (LabSense Lab Results → 4a step 2): emails,
phone numbers, national ID and insurance numbers, long identifiers and postal addresses. Dates
are never hidden by their shape: only a labeled birth date, or one in a profile's birth year.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from .lines import Segment
from .text import digit_count

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
#: Russian SNILS (individual insurance account number): 123-456-789 01.
SNILS = re.compile(r"(?<![\d\-])\d{3}-\d{3}-\d{3}[\s\-]\d{2}(?![\d\-])")
#: US Social Security number.
SSN = re.compile(r"(?<![\d\-])\d{3}-\d{2}-\d{4}(?![\d\-])")
#: The unified Russian OMS policy: 16 digits, sometimes in groups of four.
OMS = re.compile(r"(?<![\d\-])\d{4}\s?\d{4}\s?\d{4}\s?\d{4}(?![\d\-])")
PHONE = re.compile(r"(?<![\w+\-.,/(])\+?\(?\d[\d \-–()]{6,}\d(?![\w\-.,/])")
#: A run of 9 or more digits: a Kazakh IIN or Russian INN (12), a sample barcode, a record number.
LONG_NUMBER = re.compile(r"(?<![\w.,\-])\d{9,}(?![\w.,\-])")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}")

_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r"|янв\w*|фев\w*|мар\w*|апр\w*|ма[йя]|июн\w*|июл\w*|авг\w*|сен\w*|окт\w*|ноя\w*|дек\w*)"
)
#: Full dates, with the year in group `year` (and `yy` for a two-digit one).
DATES = [
    re.compile(r"(?<![\d.])\d{1,2}[./\-]\d{1,2}[./\-](?P<year>\d{4})(?![\d.])"),
    re.compile(r"(?<![\d.])\d{1,2}[./\-]\d{1,2}[./\-](?P<yy>\d{2})(?![\d./\-])"),
    re.compile(r"(?<![\d.])(?P<year>\d{4})[\-./]\d{2}[\-./]\d{2}(?![\d.])"),
    re.compile(rf"(?<!\d)\d{{1,2}}\s+{_MONTHS}\.?,?\s+(?P<year>\d{{4}})(?!\d)", re.IGNORECASE),
    re.compile(rf"(?<!\w){_MONTHS}\.?\s+\d{{1,2}},?\s+(?P<year>\d{{4}})(?!\d)", re.IGNORECASE),
]
YEAR = re.compile(r"(?<![\d.])(?P<year>19\d{2}|20\d{2})(?![\d.])")

# Russian and Kazakh street words and house parts; English street types.
_RU_STREET = (
    r"(?<!\w)(?:ул|улица|пр-т|пр-кт|просп|проспект|пер|переулок|ш|шоссе|б-р|бульвар|наб|"
    r"набережная|пл|площадь|мкр|мкрн|микрорайон|проезд|тупик|аллея|кв-л|квартал|тракт)\.?(?!\w)"
)
_RU_HOUSE = r"(?<!\w)(?:д|дом|кв|квартира|корп|корпус|стр|строение)\.?\s*\d"
_RU_PLACE = r"(?<!\w)(?:г|город|пос|поселок|с|село|обл|область|р-н|район|респ|республика)\.\s*[А-ЯЁ]"
_EN_STREET = (
    r"(?<!\w)\d{1,6}[A-Za-z]?\s+(?:[A-Z][\w'.\-]*\s+){0,4}(?:Street|St|Avenue|Ave|Road|Rd|"
    r"Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl|Square|Sq|Parkway|Pkwy|Highway|Hwy|"
    r"Terrace|Ter|Circle|Cir)\b\.?"
)
_POSTCODE = (
    r"(?<!\d)\d{6},\s*(?:г\.|город|[А-ЯЁ])"  # a Russian or Kazakh index before the place
    r"|\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"  # a US state and ZIP code
    r"|\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b"  # a UK postcode
)
ADDRESS_MARKERS = re.compile(
    "|".join(f"(?:{p})" for p in (_RU_STREET, _RU_HOUSE, _RU_PLACE, _EN_STREET, _POSTCODE))
)
#: An address needs a street or a postcode, not only a place name ("г. Москва").
_ADDRESS_ANCHOR = re.compile("|".join(f"(?:{p})" for p in (_RU_STREET, _EN_STREET, _POSTCODE)))


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    type: str


def _phone(text: str) -> bool:
    if _ISO_DATE.search(text):
        return False
    digits = digit_count(text)
    if not 10 <= digits <= 15:
        return False
    separators = len(re.findall(r"[ \-–]+", text.strip()))
    plain = text.replace(" ", "").replace("-", "").replace("–", "")
    russian_mobile = plain.isdigit() and digits == 11 and plain[0] in "78"
    return "+" in text or "(" in text or separators >= 2 or russian_mobile


def find(segment: Segment) -> Iterator[Match]:
    """Shape matches in one segment that don't overlap: the most specific shape wins."""
    taken: list[Match] = []
    for match in _candidates(segment):
        if not any(match.start < t.end and t.start < match.end for t in taken):
            taken.append(match)
            yield match


def _candidates(segment: Segment) -> Iterator[Match]:
    text = segment.text
    for m in EMAIL.finditer(text):
        yield Match(m.start(), m.end(), "email")
    for m in SNILS.finditer(text):
        yield Match(m.start(), m.end(), "id_number")
    for m in SSN.finditer(text):
        yield Match(m.start(), m.end(), "id_number")
    for m in OMS.finditer(text):
        yield Match(m.start(), m.end(), "policy_number")
    for m in PHONE.finditer(text):
        if _phone(m.group()):
            yield Match(m.start(), m.end(), "phone")
    for m in LONG_NUMBER.finditer(text):
        yield Match(m.start(), m.end(), "id_number")
    yield from addresses(segment)


def addresses(segment: Segment, until: int | None = None) -> Iterator[Match]:
    """A postal address: from its first marker (index, place, street, house) to the end of the
    segment, or to `until` (where a label of another field starts)."""
    text = segment.text if until is None else segment.text[:until]
    if not _ADDRESS_ANCHOR.search(text):
        return
    markers = list(ADDRESS_MARKERS.finditer(text))
    if markers and any(ch.isdigit() for ch in text[markers[0].start() :]):
        yield Match(markers[0].start(), len(text.rstrip()), "address")
