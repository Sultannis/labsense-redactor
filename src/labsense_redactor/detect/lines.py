"""Visual lines: the words that sit on one line of the displayed page, left to right, split into
segments where a wide gap separates columns (a table's cells, a header's fields)."""

import statistics
from dataclasses import dataclass, field
from itertools import pairwise

from ..document import Word


@dataclass
class Segment:
    words: list[Word]
    #: The words joined by single spaces, and each word's span in that text.
    text: str = ""
    spans: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        parts: list[str] = []
        offset = 0
        for word in self.words:
            self.spans.append((offset, offset + len(word.text)))
            parts.append(word.text)
            offset += len(word.text) + 1
        self.text = " ".join(parts)

    def words_in(self, start: int, end: int) -> list[Word]:
        """The words a character range touches."""
        return [w for w, (s, e) in zip(self.words, self.spans, strict=True) if s < end and e > start]

    def first_word_at(self, offset: int) -> int:
        """The index of the first word that starts at or after `offset`."""
        for i, (start, _) in enumerate(self.spans):
            if start >= offset:
                return i
        return len(self.words)


@dataclass
class Line:
    words: list[Word]
    segments: list[Segment]
    top: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def build_lines(words: list[Word]) -> list[Line]:
    rows: list[list[Word]] = []
    bounds: list[tuple[float, float]] = []
    for word in sorted(words, key=lambda w: (w.frame.y0 + w.frame.y1) / 2):
        best = -1
        best_overlap = 0.0
        for i, (top, bottom) in enumerate(bounds):
            overlap = _overlap(top, bottom, word.frame.y0, word.frame.y1)
            if overlap >= 0.5 * min(bottom - top, word.frame.height) and overlap > best_overlap:
                best, best_overlap = i, overlap
        if best < 0:
            rows.append([word])
            bounds.append((word.frame.y0, word.frame.y1))
        else:
            rows[best].append(word)
    lines: list[Line] = []
    for row in rows:
        row.sort(key=lambda w: w.frame.x0)
        height = statistics.median(w.frame.height for w in row)
        segments: list[list[Word]] = [[row[0]]]
        for prev, word in pairwise(row):
            if word.frame.x0 - prev.frame.x1 > 0.8 * height:
                segments.append([word])
            else:
                segments[-1].append(word)
        lines.append(
            Line(
                words=row,
                segments=[Segment(s) for s in segments],
                top=min(w.frame.y0 for w in row),
                bottom=max(w.frame.y1 for w in row),
            )
        )
    lines.sort(key=lambda line: line.top)
    return lines
