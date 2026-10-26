from datetime import date
from decimal import Decimal

import pytest

from reconiq.normalize import (
    canonical_key,
    endorsement_parent,
    insurer_similarity,
    key_variants,
    money_close,
    name_similarity,
    parse_date,
    parse_money,
    parse_percent,
    to_aed,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AED 1,250.00", Decimal("1250.00")),
        ("(250.00)", Decimal("-250.00")),
        ("12 500.50 Dr", Decimal("-12500.50")),
        ("1,234,567.89", Decimal("1234567.89")),
        ("AED -99.90", Decimal("-99.90")),
        (1250.5, Decimal("1250.50")),
        ("USD 4,901.29", Decimal("4901.29")),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["", "-", "n/a", None, "TBC"])
def test_parse_money_blank(raw):
    assert parse_money(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12.5%", Decimal("12.50")),
        ("12.5", Decimal("12.50")),
        (0.125, Decimal("12.50")),
        ("0.125", Decimal("12.50")),
        (0.1, Decimal("10.00")),
        ("15 %", Decimal("15.00")),
    ],
)
def test_parse_percent_does_not_lose_precision(raw, expected):
    assert parse_percent(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("01/03/2026", date(2026, 3, 1)),
        ("2026-03-01", date(2026, 3, 1)),
        ("15-Mar-2026", date(2026, 3, 15)),
        ("1 Mar 2026", date(2026, 3, 1)),
        (date(2026, 5, 4), date(2026, 5, 4)),
    ],
)
def test_parse_date_day_first(raw, expected):
    assert parse_date(raw) == expected


def test_key_variants_absorb_zero_padding_but_not_typos():
    padded = key_variants(canonical_key("GIG/2026/000451"))
    compact = key_variants(canonical_key("GIG-2026-451"))
    assert padded & compact

    typo_a = key_variants(canonical_key("OIC/MOT/2026/4508"))
    typo_b = key_variants(canonical_key("OIC/MOT/2026/4580"))
    assert not (typo_a & typo_b), "a transposed digit must not be treated as formatting"


def test_endorsement_parent_returns_canonical_parent():
    assert endorsement_parent("GIG/2026/000312/E1") == canonical_key("GIG/2026/000312")
    assert endorsement_parent("GIG/2026/000312") is None


def test_insurer_similarity_ignores_generic_words():
    assert insurer_similarity("Sukoon Insurance", "Orient Insurance PJSC") < 0.3
    assert insurer_similarity("GIG Gulf", "GIG Gulf") == 1.0
    assert insurer_similarity("Orient Insurance PJSC", "Orient Ins. PJSC") > 0.8


def test_name_similarity_tolerates_legal_suffixes():
    assert name_similarity("Emirates Logistics LLC", "Emirates Logistics L.L.C.") == 1.0
    assert name_similarity("Al Habtoor Engineering LLC", "Oasis Medical Centre") < 0.4


def test_money_close_uses_both_tolerances():
    assert money_close(Decimal("1000"), Decimal("1000.50"), Decimal("1"), Decimal("0.1"))
    assert not money_close(Decimal("1000"), Decimal("1010"), Decimal("1"), Decimal("0.5"))


def test_to_aed_uses_rate_table():
    assert to_aed(Decimal("100"), "USD") == Decimal("367.25")
    assert to_aed(Decimal("100"), "AED") == Decimal("100.00")
    assert to_aed(None, "AED") is None
