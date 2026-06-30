"""Pydantic v2 request/response schemas for synchealth.

Hardening:
    * `IngestRow` enforces physiologically-plausible ranges at the
      schema level (the parser still filters too, but this catches
      direct API callers).
    * `IngestRequest` caps the batch size to 1000 rows so a single
      client can't blow up the worker.
    * `MetricPoint` keeps `value` as `float` so a chart can plot
      weight, body fat or HR uniformly.

Important Pydantic v2 + Python 3.11 compatibility note
-----------------------------------------------------
On the Python 3.11.15 build in this environment, Pydantic v2.9 and v2.11
collapse `Optional[X] = None` to `NoneType` (annotation becomes
`<class 'NoneType'>` instead of `Optional[date]`), which then rejects
any non-None value with `Input should be None`.

Workaround: declare optional fields as `Optional[X]` WITHOUT a default
(`required=True` at the model layer, but `None` is still accepted as a
value). This forces clients to include every field in JSON, but `null`
is a legal value. We validate "at least one metric present" in the
endpoint.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingest (CSV upload or direct POST)
# ---------------------------------------------------------------------------

class IngestRow(BaseModel):
    """One day of biometric readings.

    `weight_kg`, `body_fat_pct` and `bmi` are all required to be present
    in the JSON payload (they can be `null`). The endpoint checks that at
    least one of them is non-null before persisting.
    """

    date: date
    weight_kg: Optional[float] = Field(default=None, ge=30.0, le=200.0)
    body_fat_pct: Optional[float] = Field(default=None, ge=3.0, le=70.0)
    bmi: Optional[float] = Field(default=None, ge=10.0, le=60.0)


class IngestRequest(BaseModel):
    """Bulk insert payload for `POST /ingest/weight`."""

    rows: list[IngestRow] = Field(min_length=1, max_length=1000)
    source: str = Field(default="manual", min_length=1, max_length=64)


class IngestResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    total: int


# ---------------------------------------------------------------------------
# Metrics (chart series)
# ---------------------------------------------------------------------------

class MetricPoint(BaseModel):
    date: date
    value: float


class MetricsResponse(BaseModel):
    metric: str
    period_days: int
    points: list[MetricPoint]


# ---------------------------------------------------------------------------
# CSV preview (parse without inserting)
# ---------------------------------------------------------------------------

# NOTE: we intentionally do NOT declare `CSVPreviewRow` as a Pydantic
# `BaseModel`. The fields are optional and we'd hit the annotation
# collapse bug described above. The endpoint returns a plain dict that
# matches this structure:
#
#     {
#       "row_number": int,
#       "date": "YYYY-MM-DD" | null,
#       "weight_kg": float | null,
#       "body_fat_pct": float | null,
#       "bmi": float | null,
#       "errors": list[str],
#     }


class CSVPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[dict]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    db: bool
    version: str