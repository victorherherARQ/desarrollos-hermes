"""Pydantic schemas for the ADR Generator API.

`AdrRequest` is the user-facing payload accepted by `POST /generate`.
`AdrResponse` is what the endpoint returns once the ADR has been
written to the local Git repo (and optionally pushed as a PR).

Hardening (rework):
    * `context` / `preliminary_decision` / `technologies` /
      `options_to_evaluate` have explicit `max_length` / `max_items`
      so a single client can't blow up the worker or fill the disk.
    * `date` is validated against `YYYY-MM-DD`; invalid values are
      dropped (and the handler falls back to today).
"""

from __future__ import annotations

import re
from datetime import date as _date_cls
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

AdrStatus = Literal[
    "proposed", "accepted", "rejected", "deprecated", "superseded"
]


# Accept strict ISO 8601 calendar dates: YYYY-MM-DD.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AdrRequest(BaseModel):
    """Input form for generating a new ADR."""

    title: str = Field(..., min_length=5, max_length=200)
    context: str = Field(..., min_length=20, max_length=5000)
    technologies: List[str] = Field(..., min_length=1, max_length=50)
    preliminary_decision: str = Field(..., min_length=5, max_length=500)
    options_to_evaluate: List[str] = Field(default_factory=list, max_length=50)
    status: AdrStatus = "proposed"
    deciders: List[str] = Field(
        default_factory=lambda: ["Architecture Committee"]
    )
    # Optional ISO date (YYYY-MM-DD). If missing or invalid, the handler
    # falls back to today.
    date: Optional[str] = None

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: Optional[str]) -> Optional[str]:
        """Accept only strict ISO dates; silently drop anything else.

        We don't raise here because the user-facing API contract is
        "missing/invalid date → use today". Raising would force every
        client to send a perfectly formatted date even when they
        explicitly want the default.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value:
            return None
        if not _ISO_DATE_RE.match(value):
            return None
        try:
            # Catch impossible dates like "2026-02-31".
            _date_cls.fromisoformat(value)
        except ValueError:
            return None
        return value


class AdrResponse(BaseModel):
    """Output of `POST /generate`."""

    adr_number: int
    filename: str
    content: str
    branch: str
    commit_sha: Optional[str] = None
    pr_url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    model: str
    github_enabled: bool


class AdrListItem(BaseModel):
    number: int
    filename: str
    status: Optional[str] = None
    title: Optional[str] = None


class AdrListResponse(BaseModel):
    adrs: List[AdrListItem]