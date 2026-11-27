"""Product name cleanup: remove promo noise, keep brand + variant + size."""

import re

_PROMO_PATTERNS = [
    r"[\(\[]\s*new\s*[\)\]]",  # (NEW) / [NEW]
    r"\bnew\s*!+",  # NEW!
    r"\bbuy\s*\d+\s*take\s*\d+\b",  # BUY 1 TAKE 1
    r"\bb\d+t\d+\b",  # B1T1
    r"\blimited\s+edition\s*!*",
    r"\bpromo\s*pack\b",
    r"\bsale\s*!+",
]
_PROMO_RE = re.compile("|".join(_PROMO_PATTERNS), re.IGNORECASE)


def clean_name(name: str) -> str:
    """'NEW! Lucky Me Pancit Canton BUY 1 TAKE 1' -> 'Lucky Me Pancit Canton'."""
    cleaned = _PROMO_RE.sub(" ", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -|,;:")


def split_size_suffix(name: str) -> tuple[str, str]:
    """SM Markets names put the size after a pipe: 'Pantene ... Repair | 300ml'."""
    if "|" in name:
        base, _, size = name.rpartition("|")
        return base.strip(), size.strip()
    return name.strip(), ""
