from decimal import Decimal

import pytest

from ingest.money import MoneyError, centavos_to_php, format_php, php_to_centavos
from ingest.names import clean_name, split_size_suffix


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("89.75", 8975),
        ("₱1,299.00", 129900),
        ("PHP 45", 4500),
        (345.0, 34500),
        (89.75, 8975),  # float from JSON stays exact
        (0.1 + 0.2, 30),  # 0.30000000000000004 rounds to 30 centavos
        (Decimal("12.345"), 1235),  # half-up rounding when not strict
        (100, 10000),
    ],
)
def test_php_to_centavos(value, expected):
    assert php_to_centavos(value) == expected


@pytest.mark.parametrize("value", ["abc", "", "-5", "NaN", "Infinity"])
def test_php_to_centavos_rejects_bad_input(value):
    with pytest.raises(MoneyError):
        php_to_centavos(value)


def test_strict_rejects_more_than_two_decimals():
    with pytest.raises(MoneyError):
        php_to_centavos("12.345", strict=True)
    assert php_to_centavos("12.34", strict=True) == 1234


def test_formatting():
    assert centavos_to_php(8975) == "89.75"
    assert centavos_to_php(5) == "0.05"
    assert format_php(129900) == "₱1,299.00"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NEW! Lucky Me Pancit Canton 60g", "Lucky Me Pancit Canton 60g"),
        ("Oishi Prawn Crackers BUY 1 TAKE 1", "Oishi Prawn Crackers"),
        ("Fudgee Barr B1T1", "Fudgee Barr"),
        ("(NEW) Piattos Cheese", "Piattos Cheese"),
        ("New Zealand Creamery Butter", "New Zealand Creamery Butter"),
        ("  Coke   Zero  ", "Coke Zero"),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


def test_split_size_suffix():
    assert split_size_suffix("Pantene Conditioner | 300ml") == ("Pantene Conditioner", "300ml")
    assert split_size_suffix("No Size Here") == ("No Size Here", "")
