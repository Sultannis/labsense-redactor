"""The account's known details (LabSense Lab Results → 4a step 2): the profile names, the sign-in
email and the profiles' birth years. A profile name matches in either alphabet (`Anna` / `Анна`),
in Russian case forms (`Ивановой`), and with one typo in longer names; every match of one profile
counts as one detail. A full date in a birth year is a date of birth, labeled or not.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

from ..document import Word
from .lines import Line
from .patterns import DATES
from .text import (
    edit_distance_at_most_one,
    is_cyrillic,
    letters,
    norm,
    to_cyrillic,
    to_latin,
)

#: Russian noun and adjective endings a name takes in other cases.
_ENDINGS = (
    "",
    "а",
    "я",
    "ы",
    "и",
    "е",
    "у",
    "ю",
    "ой",
    "ей",
    "ом",
    "ем",
    "ою",
    "ею",
    "ым",
    "им",
    "ая",
    "ую",
    "ого",
    "ему",
    "ой",
)
_STEM_DROPS = ("а", "я", "й", "ь", "ий", "ый", "ой", "ая", "яя")


@dataclass(frozen=True)
class KnownName:
    key: str
    tokens: tuple["NameToken", ...]


@dataclass(frozen=True)
class NameToken:
    #: The token in both alphabets: a word one typo away from one of these matches too.
    spellings: frozenset[str]
    #: Every exact form: the spellings and the Russian case forms.
    forms: frozenset[str]


def _token(token: str) -> NameToken:
    cyrillic = token if is_cyrillic(token) else to_cyrillic(token)
    spellings = frozenset({token, cyrillic, to_latin(cyrillic)})
    stems = {cyrillic} | {
        cyrillic[: -len(d)] for d in _STEM_DROPS if cyrillic.endswith(d) and len(cyrillic) - len(d) >= 3
    }
    forms = spellings | {stem + ending for stem in stems for ending in _ENDINGS}
    return NameToken(spellings, frozenset(forms))


def known_names(names: list[str]) -> list[KnownName]:
    known: list[KnownName] = []
    for name in names:
        tokens = [letters(t) for t in re.split(r"[\s\-]+", name)]
        tokens = [t for t in tokens if len(t) >= 2]
        if tokens:
            known.append(KnownName(key="known:" + " ".join(tokens), tokens=tuple(_token(t) for t in tokens)))
    return known


def _matches(word: Word, token: NameToken) -> bool:
    text = letters(word.text)
    if len(text) < 2:
        return False
    if len(text) < 4 and not word.text[:1].isupper():
        return False
    if text in token.forms:
        return True
    return len(text) >= 5 and any(len(s) >= 5 and edit_distance_at_most_one(text, s) for s in token.spellings)


def find_names(lines: list[Line], names: list[KnownName]) -> Iterator[tuple[str, list[Word]]]:
    """(key, words) of each word that spells a token of a known name."""
    for line in lines:
        for word in line.words:
            for name in names:
                if any(_matches(word, token) for token in name.tokens):
                    yield name.key, [word]
                    break


def find_emails(lines: list[Line], emails: list[str]) -> Iterator[tuple[str, list[Word]]]:
    wanted = {norm(e) for e in emails if "@" in e}
    for line in lines:
        for word in line.words:
            text = norm(word.text)
            for email in wanted:
                if email in text:
                    yield "known:" + email, [word]
                    break


def find_birth_dates(lines: list[Line], years: list[int], today: date | None = None) -> Iterator[list[Word]]:
    """Full dates in a profile's birth year. A two-digit year counts only when it can't be a
    recent date (`12.03.88`, not `12.03.24`)."""
    if not years:
        return
    this_year = (today or datetime.now(UTC).date()).year
    full = set(years)
    short = {y % 100 for y in years if y <= this_year - 10}
    for line in lines:
        for segment in line.segments:
            for pattern in DATES:
                for m in pattern.finditer(segment.text):
                    groups = m.groupdict()
                    if (groups.get("year") and int(groups["year"]) in full) or (
                        groups.get("yy") and int(groups["yy"]) in short
                    ):
                        yield segment.words_in(m.start(), m.end())
