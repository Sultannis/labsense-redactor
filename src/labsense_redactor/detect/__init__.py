"""`/detect`: the personal details of a digital PDF as regions and a summary (LabSense Lab
Results → 4a steps 1–2).

Each word takes the type of the first finder that claims it, in this order: the account's known
details, labeled fields, dates in a birth year, shapes, then the name model. A detail found once
is then hidden wherever the same words recur (a name in every page header). Words a detail spans
on one line make one region. Kept on purpose: report and sample dates, the lab's name, sex, age
and every biomarker row.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

import pymupdf

from ..contract import DetectResponse, Known, Region
from ..document import PageGeometry, Word, page_words
from . import known as known_details
from . import labels, patterns
from .lines import Line, build_lines
from .names import NameFinder
from .scanned import is_scan
from .text import norm
from .vocabulary import STOPWORDS

_INITIALS = re.compile(r"^(?:[A-ZА-ЯЁ]\.){1,3}[,;]?$")
#: Horizontal padding of a block, in points: glyphs can overhang their box slightly.
_PAD_X = 0.5


@dataclass
class _Page:
    geometry: PageGeometry
    words: list[Word]
    lines: list[Line]
    #: word index → (type, key)
    claims: dict[int, tuple[str, str]]

    def claim(self, type_: str, words: Iterable[Word], key: str | None = None) -> None:
        words = list(words)
        if not words:
            return
        # One detail keeps one key: a labeled name that's also a known name counts once.
        existing = next(
            (self.claims[w.index][1] for w in words if self.claims.get(w.index, ("", ""))[0] == type_),
            None,
        )
        key = existing or key or f"{type_}:{' '.join(norm(w.text) for w in words)}"
        for word in words:
            self.claims.setdefault(word.index, (type_, key))


def detect(doc: pymupdf.Document, known: Known, names: NameFinder | None) -> DetectResponse:
    pages: list[_Page] = []
    for page in doc:
        geometry = PageGeometry(page)
        words = page_words(page, geometry)
        pages.append(_Page(geometry, words, build_lines(words), {}))

    profiles = known_details.known_names(known.names)
    for page in pages:
        for key, words in known_details.find_emails(page.lines, known.emails):
            page.claim("email", words, key)
        for key, words in known_details.find_names(page.lines, profiles):
            page.claim("name", words, key)
        for type_, words in labels.find(page.lines):
            page.claim(type_, words)
        for words in known_details.find_birth_dates(page.lines, known.birth_years):
            page.claim("date_of_birth", words)
        for line in page.lines:
            for segment in line.segments:
                for match in patterns.find(segment):
                    page.claim(match.type, segment.words_in(match.start, match.end))
        if names is not None:
            for words in names.find(page.lines):
                page.claim("name", words)
        _initials(page)
        _name_before_birth_date(page)
    _repeat(pages)

    if any(is_scan(page) for page in doc):
        # The user paints over the pages instead; nothing found here would be used.
        return DetectResponse(regions=[], summary={}, scanned=True)
    regions = [region for number, page in enumerate(pages, 1) for region in _regions(number, page)]
    keys: dict[str, set[str]] = {}
    for page in pages:
        for type_, key in page.claims.values():
            keys.setdefault(type_, set()).add(key)
    return DetectResponse(
        regions=regions,
        summary={type_: len(found) for type_, found in sorted(keys.items())},
        scanned=False,
    )


def _initials(page: _Page) -> None:
    """Initials beside a hidden name belong to it (`Иванова А.П.`, `A. Example`)."""
    for line in page.lines:
        for segment in line.segments:
            words = segment.words
            for i, word in enumerate(words):
                if word.index in page.claims or not _INITIALS.match(word.text):
                    continue
                for j in (i - 1, i + 1):
                    if 0 <= j < len(words) and page.claims.get(words[j].index, ("", ""))[0] == "name":
                        page.claim("name", [word], page.claims[words[j].index][1])
                        break


def _name_before_birth_date(page: _Page) -> None:
    """Name-like words right before a hidden birth date are the patient's name (`Иванов И.И.,
    1980 г.р.`, `Anna Example (14.03.1988)`)."""
    for line in page.lines:
        for segment in line.segments:
            words = segment.words
            for i, word in enumerate(words):
                claim = page.claims.get(word.index)
                if claim is None or claim[0] != "date_of_birth":
                    continue
                if i > 0 and page.claims.get(words[i - 1].index, ("",))[0] == "date_of_birth":
                    continue
                run = _name_run_before(words[:i])
                if len(run) >= 2:
                    page.claim("name", run)


def _name_run_before(words: list[Word]) -> list[Word]:
    """Up to four name-like words ending right before the given position, stopping at a comma
    that separates them from what comes before."""
    run: list[Word] = []
    for word in reversed(words[-4:]):
        text = word.text
        if run and text.endswith((",", ";", ":")):
            break
        if norm(text) in STOPWORDS or not labels.NAME_TOKEN.match(text):
            break
        run.insert(0, word)
    return run


def _repeat(pages: list[_Page]) -> None:
    """Hide every other occurrence of a detail's words, on every page."""
    details: dict[tuple[str, ...], tuple[str, str]] = {}
    for page in pages:
        for line in page.lines:
            run: list[Word] = []
            for word in [*line.words, None]:
                claim = page.claims.get(word.index) if word else None
                if run and (claim is None or claim != page.claims[run[0].index]):
                    sequence = tuple(norm(w.text) for w in run)
                    if sum(len(t) for t in sequence) >= 4:
                        details.setdefault(sequence, page.claims[run[0].index])
                    run = []
                if word is not None and claim is not None:
                    run.append(word)
    for page in pages:
        for line in page.lines:
            texts = [norm(w.text) for w in line.words]
            for sequence, (type_, key) in details.items():
                n = len(sequence)
                for i in range(len(texts) - n + 1):
                    if tuple(texts[i : i + n]) == sequence:
                        page.claim(type_, line.words[i : i + n], key)


def _regions(number: int, page: _Page) -> Iterable[Region]:
    for line in page.lines:
        run: list[Word] = []
        for word in [*line.words, None]:
            claim = page.claims.get(word.index) if word else None
            if run and claim != page.claims[run[0].index]:
                region = _region(number, page, run)
                if region is not None:
                    yield region
                run = []
            if word is not None and claim is not None:
                run.append(word)


def _region(number: int, page: _Page, words: list[Word]) -> Region | None:
    box = pymupdf.Rect(words[0].disp)
    for word in words[1:]:
        box |= word.disp
    box = pymupdf.Rect(box.x0 - _PAD_X, box.y0, box.x1 + _PAD_X, box.y1)
    fractions = page.geometry.fractions(box)
    if fractions is None:
        return None
    x0, y0, x1, y1 = fractions
    type_ = page.claims[words[0].index][0]
    return Region(page=number, x0=x0, y0=y0, x1=x1, y1=y1, type=type_)  # type: ignore[arg-type]
