"""Pack-size parsing: "Lucky Me Pancit Canton Original 60g x 6" -> 60 g, pack of 6.

Pure functions, no Django. See tests/test_packsize.py for the supported shapes.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

MEASURE_UNITS = {
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gr": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "mg": "mg",
    "ml": "ml",
    "cl": "cl",
    "l": "L",
    "ltr": "L",
    "ltrs": "L",
    "liter": "L",
    "liters": "L",
    "litre": "L",
    "litres": "L",
    "oz": "oz",
}

COUNT_UNITS = {
    "pc": "pcs",
    "pcs": "pcs",
    "piece": "pcs",
    "pieces": "pcs",
    "s": "pcs",
    "pack": "pack",
    "packs": "pack",
    "pk": "pack",
    "pks": "pack",
    "sachet": "sachet",
    "sachets": "sachet",
    "tie-pack": "tie-pack",
    "tie-packs": "tie-pack",
    "roll": "roll",
    "rolls": "roll",
    "sheet": "sheet",
    "sheets": "sheet",
    "tablet": "tablet",
    "tablets": "tablet",
    "tabs": "tablet",
    "capsule": "capsule",
    "capsules": "capsule",
    "can": "can",
    "cans": "can",
    "bottle": "bottle",
    "bottles": "bottle",
    "bag": "bag",
    "bags": "bag",
}


def _alternation(words: dict[str, str]) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


_MU = _alternation(MEASURE_UNITS)
_CU = _alternation(COUNT_UNITS)
_NUM = r"\d+(?:\.\d+)?"
# "x" is allowed next to numbers/units so that "60gx6" and "6x60g" work.
_LB = r"(?<![a-wyz0-9.])"
_RB = r"(?![a-wyz])"

_MEASURE = rf"{_LB}(?P<num>{_NUM})\s*(?P<unit>{_MU}){_RB}"
MEASURE_RE = re.compile(_MEASURE)
COUNT_RE = re.compile(rf"{_LB}(?P<num>\d+)\s*(?P<unit>{_CU}){_RB}")
PACK_OF_RE = re.compile(r"\bpack\s+of\s+(?P<num>\d+)\b")
PLUS_RE = re.compile(rf"{_LB}(?P<a>\d+)\s*\+\s*(?P<b>\d+)\s*(?P<unit>{_CU})?{_RB}")
RANGE_RE = re.compile(rf"{_LB}(?P<num>{_NUM})\s*(?:{_MU})?\s*-\s*{_NUM}\s*(?P<unit>{_MU}){_RB}")
# "6 x 60g", "5 sachets x 20g"
MULT_BEFORE_RE = re.compile(
    rf"{_LB}(?P<mult>\d+)\s*(?:{_CU})?\s*x\s*(?P<num>{_NUM})\s*(?P<unit>{_MU}){_RB}"
)
# "60g x 6", "330ml x 24pcs", "60gx6"
MULT_AFTER_RE = re.compile(
    rf"{_LB}(?P<num>{_NUM})\s*(?P<unit>{_MU})\s*x\s*(?P<mult>\d+)(?!\.\d|\s*(?:{_MU}){_RB})"
)


@dataclass(frozen=True)
class PackSize:
    size_value: Decimal | None
    size_unit: str
    pack_count: int

    @property
    def size_text(self) -> str:
        if self.size_value is None:
            return ""
        value = format(self.size_value.normalize(), "f")
        text = f"{value}{self.size_unit}"
        if self.pack_count > 1:
            text += f" x {self.pack_count}"
        return text


EMPTY = PackSize(None, "", 1)


def _normalize(text: str) -> str:
    s = text.lower().replace("×", "x")
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)  # 1,000g -> 1000g
    s = re.sub(r"\btie\s*-?\s*packs?\b", "tie-pack", s)
    return s


def _measure(num: str, unit: str) -> tuple[Decimal, str]:
    return Decimal(num), MEASURE_UNITS[unit]


def parse_pack_size(text: str) -> PackSize:
    """Extract (size_value, size_unit, pack_count) from a product name or size string."""
    if not text:
        return EMPTY
    s = _normalize(text)

    for regex in (MULT_BEFORE_RE, MULT_AFTER_RE):
        m = regex.search(s)
        if m:
            value, unit = _measure(m["num"], m["unit"])
            return PackSize(value, unit, max(int(m["mult"]), 1))

    range_match = RANGE_RE.search(s)
    measure = MEASURE_RE.search(s)
    plus = PLUS_RE.search(s)
    count = PACK_OF_RE.search(s) or COUNT_RE.search(s)

    if range_match:  # variable weight, e.g. "1000g-1500g": use the lower bound
        value, unit = _measure(range_match["num"], range_match["unit"])
        return PackSize(value, unit, 1)

    if measure:
        value, unit = _measure(measure["num"], measure["unit"])
        if plus:
            pack = int(plus["a"]) + int(plus["b"])
        elif count:
            pack = int(count["num"])
        else:
            pack = 1
        return PackSize(value, unit, max(pack, 1))

    if plus:  # "6+1pcs" promo packs
        unit = COUNT_UNITS[plus["unit"]] if plus["unit"] else "pcs"
        return PackSize(Decimal(int(plus["a"]) + int(plus["b"])), unit, 1)

    if count:
        unit = COUNT_UNITS.get(count.groupdict().get("unit") or "pack", "pack")
        return PackSize(Decimal(count["num"]), unit, 1)

    return EMPTY
