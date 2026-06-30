"""Tolerant CSV parser for Zepp Life exports.

Zepp Life exports a CSV with the following columns (real-world format
confirmed against several exports):

    Date, Weight (kg), BMI, Body Fat (%), Muscle Mass (kg),
    Body Water (%), Bone Mass (kg), Visceral Fat, Basal Metabolism (kcal)

The parser must tolerate:
    * UTF-8 BOM at the start of the file
    * CRLF line endings (Windows exports)
    * Different column orders
    * Missing columns (e.g. BMI absent in older exports)
    * Empty cells (treated as missing, not invalid)
    * Whitespace around values

It must NOT crash on:
    * Unparseable dates
    * Non-numeric values in numeric columns
    * Completely empty lines

Invalid rows are surfaced with a structured error; valid rows are
returned alongside so the endpoint can still insert the good ones.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import IO, Iterable

from .validate import RANGES


# ---------------------------------------------------------------------------
# Column synonyms
# ---------------------------------------------------------------------------

# Lower-cased normalised header -> canonical field name.
_HEADER_MAP: dict[str, str] = {
    "date": "date",
    "fecha": "date",
    "weight (kg)": "weight_kg",
    "weight_kg": "weight_kg",
    "weight": "weight_kg",
    "peso (kg)": "weight_kg",
    "peso": "weight_kg",
    "bmi": "bmi",
    "imc": "bmi",
    "body fat (%)": "body_fat_pct",
    "body_fat_pct": "body_fat_pct",
    "body fat": "body_fat_pct",
    "grasa corporal (%)": "body_fat_pct",
    "grasa (%)": "body_fat_pct",
    "muscle mass (kg)": "muscle_mass_kg",
    "body water (%)": "body_water_pct",
    "bone mass (kg)": "bone_mass_kg",
    "visceral fat": "visceral_fat",
    "basal metabolism (kcal)": "basal_metabolism_kcal",
}


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ParsedRow:
    """A single parsed CSV row (one per day of biometric readings)."""

    row_number: int
    date: date | None = None
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    bmi: float | None = None
    muscle_mass_kg: float | None = None
    body_water_pct: float | None = None
    bone_mass_kg: float | None = None
    visceral_fat: float | None = None
    basal_metabolism_kcal: int | None = None
    errors: list[str] = field(default_factory=list)

    def has_any_metric(self) -> bool:
        return any(
            getattr(self, f) is not None
            for f in ("weight_kg", "body_fat_pct", "bmi")
        )

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "weight_kg": self.weight_kg,
            "body_fat_pct": self.body_fat_pct,
            "bmi": self.bmi,
        }


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    valid_rows: list[ParsedRow]
    invalid_rows: list[ParsedRow]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def valid_count(self) -> int:
        return len(self.valid_rows)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_bom(text: str) -> str:
    if text and text[0] == "\ufeff":
        return text[1:]
    return text


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    # ISO 8601 YYYY-MM-DD (Zepp uses this).
    if _ISO_DATE_RE.match(raw):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None
    # Fallback: accept DD/MM/YYYY (some Zepp regional exports).
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    # Normalise "89,4" -> "89.4" for users with non-EN locale exports.
    raw = raw.replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    # Reject NaN and Inf: they pass float() but poison downstream aggregations.
    if not (value == value):  # NaN != NaN
        return None
    if value in (float("inf"), float("-inf")):
        return None
    return value


def _normalise_header(header: str) -> str:
    return header.strip().lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_csv(text: str) -> ParseResult:
    """Parse a CSV string (as produced by Zepp Life export).

    Returns a `ParseResult` with every row (including invalid ones) so
    callers can surface a useful error report.
    """
    text = _strip_bom(text)
    reader = csv.reader(io.StringIO(text))
    rows_iter: Iterable[list[str]] = list(reader)

    if not rows_iter:
        return ParseResult([], [], [])

    header = [_normalise_header(c) for c in rows_iter[0]]
    body = rows_iter[1:]

    parsed_rows: list[ParsedRow] = []
    valid_rows: list[ParsedRow] = []
    invalid_rows: list[ParsedRow] = []

    for idx, raw in enumerate(body, start=2):
        row = ParsedRow(row_number=idx)
        if not raw or all((c or "").strip() == "" for c in raw):
            # Skip totally empty lines silently.
            continue

        for col_idx, cell in enumerate(raw):
            if col_idx >= len(header):
                break
            canonical = _HEADER_MAP.get(header[col_idx])
            if canonical is None:
                continue
            if canonical == "date":
                row.date = _parse_date(cell)
            else:
                value = _parse_number(cell)
                setattr(row, canonical, value)

        _validate_row(row)
        parsed_rows.append(row)
        if row.errors or not row.has_any_metric():
            invalid_rows.append(row)
        else:
            valid_rows.append(row)

    return ParseResult(rows=parsed_rows, valid_rows=valid_rows, invalid_rows=invalid_rows)


def parse_csv_stream(stream: IO[bytes] | IO[str]) -> ParseResult:
    """Parse a CSV from an open file-like object."""
    if hasattr(stream, "read"):
        data = stream.read()
    else:
        data = stream  # type: ignore[assignment]
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig", errors="replace")
    return parse_csv(data)


# ---------------------------------------------------------------------------
# Internal validation
# ---------------------------------------------------------------------------

def _validate_row(row: ParsedRow) -> None:
    if row.date is None:
        row.errors.append("missing or unparseable date")
    for field_name in ("weight_kg", "body_fat_pct", "bmi"):
        value = getattr(row, field_name)
        if value is None:
            continue
        lo, hi = RANGES[field_name]
        if not (lo <= value <= hi):
            row.errors.append(
                f"{field_name}={value} out of range [{lo}, {hi}]"
            )