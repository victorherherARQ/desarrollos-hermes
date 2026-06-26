"""Tests for the request/response schemas (M2 / M3 hardening)."""

from __future__ import annotations

from datetime import date as _date_cls

import pytest
from pydantic import ValidationError

from app.models import AdrRequest


def _valid_kwargs(**overrides) -> dict:
    base = {
        "title": "Use PostgreSQL as primary database",
        "context": "We need a transactional relational database.",
        "technologies": ["PostgreSQL"],
        "preliminary_decision": "Managed PostgreSQL",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# max_length / max_items (M2)
# ---------------------------------------------------------------------------

def test_context_max_length_enforced():
    with pytest.raises(ValidationError):
        AdrRequest(**_valid_kwargs(context="a" * 5001))


def test_context_min_length_still_enforced():
    with pytest.raises(ValidationError):
        AdrRequest(**_valid_kwargs(context="too short"))


def test_preliminary_decision_max_length_enforced():
    long = "x" * 501
    with pytest.raises(ValidationError):
        AdrRequest(**_valid_kwargs(preliminary_decision=long))


def test_technologies_max_items_enforced():
    too_many = [f"tech-{i}" for i in range(51)]
    with pytest.raises(ValidationError):
        AdrRequest(**_valid_kwargs(technologies=too_many))


def test_options_to_evaluate_max_items_enforced():
    too_many = [f"opt-{i}" for i in range(51)]
    with pytest.raises(ValidationError):
        AdrRequest(**_valid_kwargs(options_to_evaluate=too_many))


def test_valid_payload_passes_at_boundaries():
    req = AdrRequest(
        **_valid_kwargs(
            context="a" * 5000,
            preliminary_decision="x" * 500,
            technologies=[f"tech-{i}" for i in range(50)],
            options_to_evaluate=[f"opt-{i}" for i in range(50)],
        )
    )
    assert len(req.context) == 5000
    assert len(req.preliminary_decision) == 500
    assert len(req.technologies) == 50
    assert len(req.options_to_evaluate) == 50


# ---------------------------------------------------------------------------
# date validation (M3)
# ---------------------------------------------------------------------------

def test_date_iso_passes():
    req = AdrRequest(**_valid_kwargs(date="2026-04-12"))
    assert req.date == "2026-04-12"


def test_date_invalid_format_dropped():
    """Invalid ISO formats are silently normalised to None."""
    req = AdrRequest(**_valid_kwargs(date="12/04/2026"))
    assert req.date is None


def test_date_impossible_value_dropped():
    req = AdrRequest(**_valid_kwargs(date="2026-02-31"))
    assert req.date is None


def test_date_non_string_dropped():
    # Pydantic will already coerce int to ValidationError, but strings
    # that aren't dates should drop to None.
    req = AdrRequest(**_valid_kwargs(date="not-a-date"))
    assert req.date is None


def test_date_empty_string_dropped():
    req = AdrRequest(**_valid_kwargs(date=""))
    assert req.date is None


def test_date_omitted_is_none():
    req = AdrRequest(**_valid_kwargs())
    assert req.date is None