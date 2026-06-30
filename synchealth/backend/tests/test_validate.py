"""Tests for the range validators in `app.ingest.validate`."""

from __future__ import annotations

import pytest

from app.ingest.validate import RANGES, reject_out_of_range, validate


# ---------------------------------------------------------------------------
# Per-range happy path + boundary tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("weight_kg", 30.0, True),
        ("weight_kg", 200.0, True),
        ("weight_kg", 89.5, True),
        ("weight_kg", 29.9, False),
        ("weight_kg", 200.1, False),
        ("body_fat_pct", 3.0, True),
        ("body_fat_pct", 70.0, True),
        ("body_fat_pct", 25.0, True),
        ("body_fat_pct", 2.9, False),
        ("body_fat_pct", 70.1, False),
        ("bmi", 10.0, True),
        ("bmi", 60.0, True),
        ("bmi", 22.5, True),
        ("bmi", 9.9, False),
        ("bmi", 60.1, False),
        ("resting_hr", 30, True),
        ("resting_hr", 120, True),
        ("resting_hr", 60, True),
        ("resting_hr", 29, False),
        ("resting_hr", 121, False),
    ],
)
def test_validate_boundaries(name: str, value: float | int, expected: bool):
    assert validate(value, name) is expected


def test_validate_none_is_treated_as_missing():
    """None means "no value provided"; it should NOT be marked invalid."""
    assert validate(None, "weight_kg") is True
    assert validate(None, "body_fat_pct") is True
    assert validate(None, "bmi") is True


def test_validate_unknown_key_raises():
    with pytest.raises(KeyError):
        validate(50.0, "no_such_metric")


def test_validate_negative_value_rejected():
    assert validate(-1.0, "weight_kg") is False
    assert validate(-5.0, "body_fat_pct") is False


def test_ranges_dict_is_complete():
    expected = {"weight_kg", "body_fat_pct", "bmi", "resting_hr"}
    assert expected.issubset(set(RANGES.keys()))


# ---------------------------------------------------------------------------
# reject_out_of_range
# ---------------------------------------------------------------------------

def test_reject_out_of_range_drops_bad_rows():
    rows = [
        {"date": "2025-05-01", "weight_kg": 89.0, "bmi": 28.0},
        {"date": "2025-05-02", "weight_kg": 500.0, "bmi": 28.0},
        {"date": "2025-05-03", "weight_kg": 88.5, "bmi": 28.0},
    ]
    cleaned = reject_out_of_range(rows)
    assert len(cleaned) == 2
    assert cleaned[0]["date"] == "2025-05-01"
    assert cleaned[1]["date"] == "2025-05-03"


def test_reject_out_of_range_keeps_rows_with_only_missing_fields():
    rows = [
        {"date": "2025-05-01"},
        {"date": "2025-05-02", "weight_kg": 90.0},
    ]
    cleaned = reject_out_of_range(rows)
    assert len(cleaned) == 2


def test_reject_out_of_range_empty_input():
    assert reject_out_of_range([]) == []


def test_reject_out_of_range_bmi_failure():
    rows = [
        {"date": "2025-05-01", "weight_kg": 90.0, "bmi": 80.0},
    ]
    cleaned = reject_out_of_range(rows)
    assert cleaned == []