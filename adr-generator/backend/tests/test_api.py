"""Integration tests for the FastAPI app.

These use `fastapi.testclient.TestClient`. The LLM client and GitHub
HTTP layer are monkeypatched so the suite makes no external calls.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Sample LLM output
# ---------------------------------------------------------------------------

_SAMPLE_MARKDOWN = """---
title: "Use PostgreSQL as primary database"
status: "accepted"
date: "2026-04-12"
deciders:
  - "Architecture Committee"
consulted: []
informed: []
technologies:
  - "PostgreSQL"
---

# Use PostgreSQL as primary database

## Context and Problem Statement

We need a transactional relational database that supports semi-structured
JSON and full-text search without bringing in a new on-prem provider.

## Decision Drivers

* Predictable operating cost.
* Team familiarity.

## Considered Options

1. Managed PostgreSQL.
2. MySQL 8.

## Decision Outcome

Chosen option: "Managed PostgreSQL", because the team already knows the engine.

## Pros and Cons of the Options

### Managed PostgreSQL

**Bueno**, porque el equipo ya conoce el motor.

**Malo**, porque el costo mensual es mayor.

## Links

* [MADR](https://adr.github.io/madr/)
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_repo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point ADR_REPO_PATH at a fresh temp directory."""
    tmp = Path(tempfile.mkdtemp(prefix="adr-api-test-"))
    monkeypatch.setenv("ADR_REPO_PATH", str(tmp))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Disable GitHub for these tests.
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setenv("GITHUB_REPO", "")
    # Reset cached settings.
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield tmp
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def client(temp_repo: Path) -> Iterator[TestClient]:
    from app.main import app

    # Force re-import after env vars are set so @on_event uses fresh settings.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def patched_llm(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Patch `app.main.generate_adr` so the endpoint returns our sample."""
    from app import main as main_mod

    def fake_generate(form_data: dict, *, client: Any = None) -> str:
        return _SAMPLE_MARKDOWN

    monkeypatch.setattr(main_mod, "generate_adr", fake_generate)
    return fake_generate


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_returns_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "model" in body
    assert body["github_enabled"] is False


def test_generate_endpoint_returns_full_adr(client: TestClient, patched_llm: Any):
    payload = {
        "title": "Use PostgreSQL as primary database",
        "context": (
            "We need a transactional relational database that supports "
            "semi-structured JSON and full-text search."
        ),
        "technologies": ["PostgreSQL", "Python"],
        "preliminary_decision": "Managed PostgreSQL",
        "options_to_evaluate": ["Managed PostgreSQL", "MySQL 8"],
        "status": "accepted",
        "deciders": ["Architecture Committee"],
    }
    resp = client.post("/generate", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["adr_number"] >= 1
    assert body["filename"].endswith(".md")
    assert body["filename"].startswith(f"{body['adr_number']:04d}-")
    assert body["content"].startswith("---"), "Rendered ADR must start with frontmatter"
    assert body["branch"].startswith("adr/")
    assert body["commit_sha"] is not None
    assert len(body["commit_sha"]) == 40  # full git SHA


def test_generate_endpoint_validates_payload(client: TestClient):
    # title too short
    resp = client.post("/generate", json={
        "title": "no",
        "context": "x" * 30,
        "technologies": ["x"],
        "preliminary_decision": "y",
    })
    assert resp.status_code == 422


def test_generate_endpoint_requires_technologies(client: TestClient):
    resp = client.post("/generate", json={
        "title": "Valid title here",
        "context": "x" * 30,
        "technologies": [],
        "preliminary_decision": "y",
    })
    assert resp.status_code == 422


def test_generate_endpoint_writes_file_on_disk(client: TestClient,
                                                patched_llm: Any,
                                                temp_repo: Path):
    payload = {
        "title": "Use PostgreSQL as primary database",
        "context": "We need a transactional relational database.",
        "technologies": ["PostgreSQL"],
        "preliminary_decision": "Managed PostgreSQL",
    }
    resp = client.post("/generate", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    adr_dir = temp_repo / "docs" / "adr"
    written = list(adr_dir.glob("*.md"))
    assert len(written) == 1
    on_disk = written[0].read_text(encoding="utf-8")
    assert on_disk.startswith("---")


def test_adrs_endpoint_lists_committed(client: TestClient, patched_llm: Any):
    # First, generate one.
    payload = {
        "title": "Use PostgreSQL as primary database",
        "context": "We need a transactional relational database.",
        "technologies": ["PostgreSQL"],
        "preliminary_decision": "Managed PostgreSQL",
    }
    r = client.post("/generate", json=payload)
    assert r.status_code == 200

    resp = client.get("/adrs")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["adrs"], list)
    assert len(body["adrs"]) >= 1
    item = body["adrs"][0]
    assert "number" in item
    assert "filename" in item
    assert "status" in item


def test_generate_endpoint_no_api_key_returns_503(
    temp_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    """When OPENAI_API_KEY is missing, /generate should refuse cleanly.

    Rework note (H7): the Settings validator now refuses to boot with an
    empty API key unless `TESTING=true` is set. We set it so we can
    construct a Settings with an empty key and exercise the runtime
    503 branch in the endpoint.
    """
    import os
    from app.config import Settings
    from app.main import app

    # 1. Remove the env var that temp_repo set.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # 2. Allow the validator to pass with an empty key (TESTING=true).
    monkeypatch.setenv("TESTING", "true")

    # 3. Build an EmptyKeySettings with env_file=None so pydantic-settings
    #    doesn't fall back to the project's .env file.
    class EmptyKeySettings(Settings):
        OPENAI_API_KEY: str = ""
        TESTING: bool = True

        model_config = Settings.model_config.copy()  # type: ignore[attr-defined]
        model_config["env_file"] = None

    # 4. Patch both `app.config.get_settings` and `app.main`'s cached
    #    reference (FastAPI may have captured the original at import).
    monkeypatch.setattr("app.config.get_settings", lambda: EmptyKeySettings())
    from app import config as config_mod
    monkeypatch.setattr(config_mod, "get_settings", lambda: EmptyKeySettings())
    from app import main as main_mod
    monkeypatch.setattr(main_mod, "get_settings", lambda: EmptyKeySettings())

    with TestClient(app) as c:
        resp = c.post("/generate", json={
            "title": "Valid title here",
            "context": "x" * 30,
            "technologies": ["x"],
            "preliminary_decision": "Use something else",
        })
        assert resp.status_code == 503, resp.text