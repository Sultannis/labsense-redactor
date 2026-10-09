"""Unlabeled person names, found by spaCy's named-entity models for English and Russian, run on
the server (LabSense Lab Results → 4a step 2). Each segment of a line goes to the model of its
alphabet. A name needs two or more name-like words (`Anna Example`, `Петров И.И.`), so a single
capitalized word in a table, such as a test name, is never taken for one.
"""

import re
from collections.abc import Iterator
from typing import Any

import spacy

from ..document import Word
from .lines import Line, Segment
from .text import is_cyrillic, norm
from .vocabulary import STOPWORDS, TITLES

_NAME_WORD = re.compile(r"^(?:[A-ZА-ЯЁ][\w'’\-]*\.?|(?:[A-ZА-ЯЁ]\.){1,3})[,;]?$")
_PERSON = {"PERSON", "PER"}
#: spaCy's pipelines without the parts NER doesn't use.
_EXCLUDE = ["parser", "lemmatizer", "tagger", "attribute_ruler", "senter", "morphologizer"]


class NameFinder:
    def __init__(self, english: Any, russian: Any) -> None:
        self._models = {"en": english, "ru": russian}

    @classmethod
    def load(cls) -> "NameFinder":
        return cls(
            spacy.load("en_core_web_md", exclude=_EXCLUDE),
            spacy.load("ru_core_news_md", exclude=_EXCLUDE),
        )

    def find(self, lines: list[Line]) -> Iterator[list[Word]]:
        batches: dict[str, list[Segment]] = {"en": [], "ru": []}
        for line in lines:
            for segment in line.segments:
                if _worth_reading(segment):
                    batches["ru" if is_cyrillic(segment.text) else "en"].append(segment)
        for language, segments in batches.items():
            if not segments:
                continue
            docs = self._models[language].pipe(s.text for s in segments)
            for segment, doc in zip(segments, docs, strict=True):
                yield from _names(segment, doc)


def _worth_reading(segment: Segment) -> bool:
    """Two capitalized words at least: anything less can't hold a name we'd keep."""
    return sum(1 for w in segment.words if w.text[:1].isupper()) >= 2


def _is_name_word(word: Word, all_caps: bool) -> bool:
    text = word.text
    key = norm(text)
    if key in STOPWORDS or key in TITLES or any(ch.isdigit() for ch in text):
        return False
    if not _NAME_WORD.match(text):
        return False
    letters = [ch for ch in text if ch.isalpha()]
    # A short all-caps word is an abbreviation (TSH, АЛТ), unless the whole name is in caps.
    return all_caps or not (len(letters) <= 5 and len(letters) > 1 and all(ch.isupper() for ch in letters))


def _names(segment: Segment, doc: Any) -> Iterator[list[Word]]:
    # The Russian model sometimes splits `Иванова Анна Петровна` in two: adjacent entities merge.
    spans: list[list[int]] = []
    for ent in doc.ents:
        if ent.label_ not in _PERSON:
            continue
        if spans and segment.text[spans[-1][1] : ent.start_char].strip() == "":
            spans[-1][1] = ent.end_char
        else:
            spans.append([ent.start_char, ent.end_char])
    for start, end in spans:
        words = segment.words_in(start, end)
        all_caps = all(w.text.upper() == w.text for w in words)
        run: list[Word] = []
        best: list[Word] = []
        for word in words:
            if _is_name_word(word, all_caps):
                run.append(word)
                if len(run) > len(best):
                    best = list(run)
            else:
                run = []
        if len(best) >= 2:
            yield best
