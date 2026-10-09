"""Text normalization and transliteration for matching details across spellings."""

import re
import unicodedata

_EDGE_PUNCT = re.compile(r"^[^\w@+]+|[^\w]+$")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_LATIN = re.compile(r"[A-Za-z]")


def norm(text: str) -> str:
    """Lowercase, `ё` as `е`, compatibility forms folded, edge punctuation dropped."""
    text = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    return _EDGE_PUNCT.sub("", text)


def letters(text: str) -> str:
    return "".join(ch for ch in norm(text) if ch.isalpha())


def is_cyrillic(text: str) -> bool:
    return len(_CYRILLIC.findall(text)) > len(_LATIN.findall(text))


def has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def digit_count(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


# Russian ↔ Latin, close to the passport (ICAO) scheme, plus the common informal variants.
_RU_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "iu", "я": "ia",
    "і": "i", "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h",
}  # fmt: skip
_LAT_TO_RU = [
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"),
    ("sh", "ш"), ("yu", "ю"), ("iu", "ю"), ("ya", "я"), ("ia", "я"), ("yo", "е"),
    ("ye", "е"), ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"),
    ("g", "г"), ("h", "х"), ("i", "и"), ("j", "й"), ("k", "к"), ("l", "л"), ("m", "м"),
    ("n", "н"), ("o", "о"), ("p", "п"), ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"),
    ("u", "у"), ("v", "в"), ("w", "в"), ("x", "кс"), ("y", "й"), ("z", "з"),
]  # fmt: skip


def to_latin(word: str) -> str:
    return "".join(_RU_TO_LAT.get(ch, ch) for ch in word)


def to_cyrillic(word: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(word):
        for latin, cyrillic in _LAT_TO_RU:
            if word.startswith(latin, i):
                out.append(cyrillic)
                i += len(latin)
                break
        else:
            out.append(word[i])
            i += 1
    result = "".join(out)
    # A final `-ий` / `-ия` is usually spelled `-iy` / `-iya`, which the greedy map reads as `-ий`.
    return result


def edit_distance_at_most_one(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    edited = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if edited:
            return False
        edited = True
        if len(a) == len(b):
            i += 1
        j += 1
    return True
