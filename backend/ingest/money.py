"""Money helpers. Internally money is always integer centavos; never floats."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class MoneyError(ValueError):
    pass


def php_to_centavos(value: str | int | float | Decimal, *, strict: bool = False) -> int:
    """Convert a peso amount ("89.75", "₱1,299.00", 345.0) to integer centavos.

    Floats (from JSON) are converted through their string form, so 89.75 stays exact.
    With ``strict=True`` more than 2 decimal places is an error instead of being rounded.
    """
    text = str(value).strip()
    for token in ("₱", "PHP", "Php", "php", ","):
        text = text.replace(token, "")
    text = text.strip()
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError(f"Not a valid amount: {value!r}") from exc
    if not amount.is_finite():
        raise MoneyError(f"Not a valid amount: {value!r}")
    if amount < 0:
        raise MoneyError(f"Negative amount: {value!r}")
    if strict and amount.as_tuple().exponent < -2:
        raise MoneyError(f"At most 2 decimal places allowed: {value!r}")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def centavos_to_php(centavos: int) -> str:
    """12345 -> "123.45" (API edge format)."""
    return f"{centavos // 100}.{centavos % 100:02d}"


def format_php(centavos: int) -> str:
    """12345 -> "₱123.45"; 129900 -> "₱1,299.00"."""
    return f"₱{centavos // 100:,}.{centavos % 100:02d}"
