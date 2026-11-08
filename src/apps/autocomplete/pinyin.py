"""Literal, abbreviated and mixed pinyin matching for candidate selectors."""

from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from pypinyin import Style, pinyin

_BIDIRECTIONAL = (
    ("sh", "s"), ("ch", "c"), ("zh", "z"), ("u", "v"),
    ("ang", "an"), ("eng", "en"), ("ing", "in"),
)
_ONE_WAY = (
    ("an", "a"), ("ang", "a"), ("ai", "a"), ("ao", "a"),
    ("ou", "o"), ("ong", "o"), ("en", "e"), ("eng", "e"),
    ("ei", "e"), ("er", "e"), ("er", "r"), ("ui", "u"),
    ("un", "u"), ("vn", "v"),
)
_RULES = _ONE_WAY + _BIDIRECTIONAL + tuple((b, a) for a, b in _BIDIRECTIONAL)


@dataclass(frozen=True)
class TextUnit:
    literal: str
    readings: tuple[tuple[str, str], ...]


PreparedText = tuple[TextUnit, ...]


def prepare_text(text: str) -> PreparedText:
    units = []
    for char in text.lower():
        readings = []
        for reading in pinyin(char, style=Style.NORMAL, heteronym=True)[0]:
            if reading == char:
                continue
            reading = reading.replace("ü", "v")
            split = 0
            if reading[0] not in "aeiouv":
                split = 2 if reading.startswith(("zh", "ch", "sh")) else 1
            readings.append((reading[:split], reading[split:]))
        units.append(TextUnit(char, tuple(dict.fromkeys(readings))))
    return tuple(units)


def _variants(phoneme: str) -> set[str]:
    # Each rule acts once on the original phoneme, never on another rule's output.
    return {phoneme} | {
        phoneme.replace(source, target, 1)
        for source, target in _RULES if source in phoneme
    }


def _forms(unit: TextUnit) -> set[str]:
    forms = {unit.literal}
    for initial, final in unit.readings:
        initials, finals = _variants(initial), _variants(final)
        forms.update(a + b for a, b in product(initials, finals))
        if initial:
            forms.update(initials)
    return forms


def contains(text: PreparedText, query: str) -> bool:
    """Match contiguous source characters; only the query's end may be partial."""
    if not query:
        return True
    forms = tuple(_forms(unit) for unit in text)

    @lru_cache(maxsize=None)
    def match(position: int, offset: int) -> bool:
        if offset == len(query):
            return True
        if position == len(text):
            return False
        remaining = query[offset:]
        for form in forms[position]:
            if form.startswith(remaining):
                return True
            if query.startswith(form, offset) and match(
                position + 1, offset + len(form)
            ):
                return True
        return False

    return any(match(start, 0) for start in range(len(text)))
