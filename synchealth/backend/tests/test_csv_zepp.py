"""Tests for the Zepp Life CSV parser.

Coverage:
    * canonical (English-header) CSV
    * BOM-prefixed file
    * CRLF line endings
    * missing BMI column
    * column order shuffled
    * out-of-range weight / body fat / BMI
    * invalid date string
    * DD/MM/YYYY fallback date
    * empty rows silently skipped
    * Spanish headers (peso / IMC / grasa)
"""

from __future__ import annotations

from datetime import date


from app.ingest.csv_zepp import parse_csv, parse_csv_stream


CANONICAL = """Date,Weight (kg),BMI,Body Fat (%)
2025-05-01,89.4,28.5,25.2
2025-05-02,89.2,28.4,25.1
2025-05-03,89.0,28.3,25.0
"""


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_parse_canonical_csv():
    result = parse_csv(CANONICAL)
    assert result.total == 3
    assert result.valid_count == 3
    assert result.invalid_count == 0
    assert result.valid_rows[0].date == date(2025, 5, 1)
    assert result.valid_rows[0].weight_kg == 89.4
    assert result.valid_rows[0].body_fat_pct == 25.2
    assert result.valid_rows[0].bmi == 28.5


def test_parse_bom_prefixed_csv():
    text = "\ufeff" + CANONICAL
    result = parse_csv(text)
    assert result.valid_count == 3
    assert result.valid_rows[0].weight_kg == 89.4


def test_parse_crlf_line_endings():
    text = CANONICAL.replace("\n", "\r\n")
    result = parse_csv(text)
    assert result.valid_count == 3
    assert result.valid_rows[2].weight_kg == 89.0


def test_parse_missing_bmi_column():
    text = """Date,Weight (kg),Body Fat (%)
2025-05-01,89.4,25.2
2025-05-02,89.2,25.1
"""
    result = parse_csv(text)
    assert result.valid_count == 2
    assert result.valid_rows[0].bmi is None
    assert result.valid_rows[0].weight_kg == 89.4


def test_parse_shuffled_columns():
    text = """Body Fat (%),BMI,Date,Weight (kg)
25.2,28.5,2025-05-01,89.4
25.1,28.4,2025-05-02,89.2
"""
    result = parse_csv(text)
    assert result.valid_count == 2
    assert result.valid_rows[0].weight_kg == 89.4
    assert result.valid_rows[0].body_fat_pct == 25.2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_parse_empty_rows_skipped():
    text = CANONICAL + "\n\n2025-05-04,88.8,28.2,24.9\n"
    result = parse_csv(text)
    assert result.total == 4  # 3 + 1 (empty rows not counted)
    assert result.valid_count == 4


def test_parse_invalid_date_marked_invalid():
    text = """Date,Weight (kg),BMI,Body Fat (%)
not-a-date,89.4,28.5,25.2
2025-05-02,89.2,28.4,25.1
"""
    result = parse_csv(text)
    assert result.valid_count == 1
    assert result.invalid_count == 1
    assert "date" in result.invalid_rows[0].errors[0]


def test_parse_out_of_range_weight_marked_invalid():
    text = """Date,Weight (kg),BMI,Body Fat (%)
2025-05-01,500.0,28.5,25.2
2025-05-02,89.2,28.4,25.1
"""
    result = parse_csv(text)
    assert result.valid_count == 1
    assert result.invalid_count == 1
    assert "weight_kg" in result.invalid_rows[0].errors[0]


def test_parse_dd_mm_yyyy_date_fallback():
    text = """Date,Weight (kg),BMI,Body Fat (%)
01/05/2025,89.4,28.5,25.2
"""
    result = parse_csv(text)
    assert result.valid_count == 1
    assert result.valid_rows[0].date == date(2025, 5, 1)





def test_parse_spanish_headers():
    text = """Fecha,Peso (kg),IMC,Grasa Corporal (%)
2025-05-01,89.4,28.5,25.2
"""
    result = parse_csv(text)
    assert result.valid_count == 1
    assert result.valid_rows[0].weight_kg == 89.4
    assert result.valid_rows[0].bmi == 28.5
    assert result.valid_rows[0].body_fat_pct == 25.2


def test_parse_stream_accepts_bytes():
    raw = CANONICAL.encode("utf-8-sig")
    result = parse_csv_stream(raw)
    assert result.valid_count == 3


def test_parse_empty_input():
    result = parse_csv("")
    assert result.total == 0
    assert result.valid_count == 0


def test_parse_header_only_input():
    result = parse_csv("Date,Weight (kg),BMI,Body Fat (%)\n")
    assert result.total == 0


def test_parse_out_of_range_body_fat():
    text = """Date,Weight (kg),BMI,Body Fat (%)
2025-05-01,89.4,28.5,99.0
"""
    result = parse_csv(text)
    assert result.valid_count == 0
    assert result.invalid_count == 1
    assert "body_fat_pct" in result.invalid_rows[0].errors[0]

def test_parse_number_rejects_nan():
    """NaN must NOT pass _parse_number — would poison aggregations downstream."""
    from app.ingest.csv_zepp import _parse_number
    assert _parse_number("NaN") is None
    assert _parse_number("nan") is None
    assert _parse_number("NAN") is None


def test_parse_number_rejects_inf():
    """Inf must NOT pass _parse_number."""
    from app.ingest.csv_zepp import _parse_number
    assert _parse_number("Inf") is None
    assert _parse_number("Infinity") is None
    assert _parse_number("-Infinity") is None


def test_csv_with_nan_weight_rejected_as_invalid_row():
    """A row with weight=NaN does NOT store weight_kg (preserves BMI/body_fat)."""
    text = """Date,Weight (kg),BMI,Body Fat (%)
2025-05-01,89.4,28.5,25.2
2025-05-02,NaN,28.4,25.1
"""
    result = parse_csv(text)
    # Row 2 is still valid (BMI/body_fat OK), but weight_kg must be None.
    assert result.valid_count == 2
    assert result.valid_rows[0].weight_kg == 89.4
    assert result.valid_rows[1].weight_kg is None  # NaN discarded
    assert result.valid_rows[1].bmi == 28.4  # other fields preserved
