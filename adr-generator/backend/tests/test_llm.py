"""Unit tests for the LLM client.

The OpenAI SDK is monkeypatched at the module level so no real HTTP
call happens during the test run.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, List

import pytest

from app import llm as llm_mod
from app.config import get_settings
from app.llm import (
    SYSTEM_PROMPT,
    build_user_prompt,
    extract_considered_options,
    extract_pros_cons,
    generate_adr,
    parse_adr_sections,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    def create(self, *args: Any, **kwargs: Any):  # noqa: D401
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content)
                )
            ]
        )


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeOpenAI:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)
        self.kwargs: dict = {}

    def __call__(self, *args: Any, **kwargs: Any) -> "_FakeOpenAI":
        self.kwargs = kwargs
        return self


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeOpenAI:
    """Replace `openai_chat_factory` with a fake OpenAI client.

    Returns a wrapper that records both the factory function and the
    captured kwargs so tests can introspect what was passed in.
    """
    captured_kwargs: List[dict] = []

    def factory(*args: Any, **kwargs: Any) -> _FakeOpenAI:
        captured_kwargs.append(kwargs)
        return _FakeOpenAI(_SAMPLE_MARKDOWN)

    wrapper = SimpleNamespace(factory=factory, captured=captured_kwargs)
    monkeypatch.setattr(llm_mod, "openai_chat_factory", factory)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield wrapper
    get_settings.cache_clear()  # type: ignore[attr-defined]


_SAMPLE_MARKDOWN = """---
title: "Use PostgreSQL as primary database"
status: "accepted"
date: "2026-04-12"
deciders:
  - "Architecture Committee"
---

# Use PostgreSQL as primary database

## Context and Problem Statement

We need a transactional relational database.

## Decision Drivers

* Cost predictability.

## Considered Options

1. Managed PostgreSQL.
2. MySQL 8.

## Decision Outcome

Chosen option: "Managed PostgreSQL", because it matches the team's skill set.

## Pros and Cons of the Options

### Managed PostgreSQL

**Bueno**, porque el equipo ya lo conoce.

**Malo**, porque el costo mensual es mayor.

## Links

* [MADR](https://adr.github.io/madr/)
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_adr_uses_system_prompt(fake_client):
    body = generate_adr({"title": "Anything", "context": "x" * 30,
                          "technologies": ["Go"],
                          "preliminary_decision": "Use Go"})
    assert body == _SAMPLE_MARKDOWN
    # The factory must have been called with the correct base_url / api_key.
    assert fake_client.captured, "factory was never invoked"
    factory_kwargs = fake_client.captured[-1]
    assert factory_kwargs["base_url"] == get_settings().OPENAI_BASE_URL
    assert factory_kwargs["api_key"] == "test-key"


def test_generate_adr_retries_on_rate_limit_then_succeeds(monkeypatch):
    """A transient RateLimitError must be retried by tenacity (H5)."""
    from openai import RateLimitError

    from app import llm as llm_mod
    from app.config import get_settings

    calls: List[int] = []

    class _RetryCompletions:
        def create(self, *args: Any, **kwargs: Any):
            calls.append(1)
            if len(calls) < 3:
                # Simulate two consecutive 429s, then succeed.
                raise RateLimitError(
                    "rate limited",
                    response=httpx_response_429(),
                    body=None,
                )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=_SAMPLE_MARKDOWN))
                ]
            )

    class _RetryChat:
        def __init__(self) -> None:
            self.completions = _RetryCompletions()

    class _RetryOpenAI:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.chat = _RetryChat()
            self.kwargs = kw

    monkeypatch.setattr(llm_mod, "openai_chat_factory", lambda *a, **kw: _RetryOpenAI())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    body = llm_mod.generate_adr(
        {"title": "Anything", "context": "x" * 30, "technologies": ["Go"],
         "preliminary_decision": "Use Go"}
    )
    assert body == _SAMPLE_MARKDOWN
    assert len(calls) == 3, "tenacity should retry until the 3rd attempt succeeds"


def test_generate_adr_retries_on_connection_error(monkeypatch):
    """A transient APIConnectionError must be retried by tenacity (H5)."""
    from openai import APIConnectionError

    from app import llm as llm_mod
    from app.config import get_settings

    calls: List[int] = []

    class _ConnCompletions:
        def create(self, *args: Any, **kwargs: Any):
            calls.append(1)
            if len(calls) < 2:
                raise APIConnectionError(request=httpx_request())
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=_SAMPLE_MARKDOWN))]
            )

    class _ConnChat:
        def __init__(self) -> None:
            self.completions = _ConnCompletions()

    class _ConnOpenAI:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.chat = _ConnChat()

    monkeypatch.setattr(llm_mod, "openai_chat_factory", lambda *a, **kw: _ConnOpenAI())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    body = llm_mod.generate_adr(
        {"title": "Anything", "context": "x" * 30, "technologies": ["Go"],
         "preliminary_decision": "Use Go"}
    )
    assert body == _SAMPLE_MARKDOWN
    assert len(calls) == 2


# --- httpx fakes used by retry tests ----------------------------------------

def httpx_response_429():
    try:
        import httpx
        return httpx.Response(429, request=httpx.Request("POST", "http://x"))
    except Exception:  # pragma: no cover
        return None


def httpx_request():
    try:
        import httpx
        return httpx.Request("POST", "http://x")
    except Exception:  # pragma: no cover
        return None


def test_generate_adr_passes_correct_messages(fake_client, monkeypatch):
    """The system prompt and user payload must be in the right order."""
    sent_messages: List[dict] = []

    class _SpyCompletions:
        def create(self, *, model: str, messages: List[dict], **kwargs: Any):
            sent_messages.extend(messages)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=_SAMPLE_MARKDOWN))]
            )

    class _SpyChat:
        def __init__(self) -> None:
            self.completions = _SpyCompletions()

    class _SpyOpenAI:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.chat = _SpyChat()

    monkeypatch.setattr(llm_mod, "openai_chat_factory", lambda *a, **kw: _SpyOpenAI())
    get_settings.cache_clear()  # type: ignore[attr-defined]

    form_data = {"title": "Use Go for the new service",
                 "context": "We need a fast compiled language.",
                 "technologies": ["Go"],
                 "preliminary_decision": "Use Go"}
    generate_adr(form_data)

    assert len(sent_messages) == 2
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == SYSTEM_PROMPT
    assert sent_messages[1]["role"] == "user"
    # User payload must be JSON-serialisable.
    parsed = json.loads(sent_messages[1]["content"])
    assert parsed["title"] == form_data["title"]


def test_generate_adr_raises_on_empty_content(monkeypatch):
    class _EmptyCompletions:
        def create(self, *a: Any, **kw: Any):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
            )

    class _EmptyChat:
        def __init__(self) -> None:
            self.completions = _EmptyCompletions()

    class _EmptyOpenAI:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.chat = _EmptyChat()

    monkeypatch.setattr(llm_mod, "openai_chat_factory", lambda *a, **kw: _EmptyOpenAI())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="empty ADR body"):
        generate_adr({"title": "Anything", "context": "x" * 30,
                      "technologies": ["Go"],
                      "preliminary_decision": "Use Go"})


def test_build_user_prompt_is_valid_json():
    payload = build_user_prompt({"title": "T", "context": "C"})
    json.loads(payload)  # must parse


def test_extract_considered_options():
    section = extract_considered_options(_SAMPLE_MARKDOWN)
    assert "Managed PostgreSQL." in section
    assert "MySQL 8." in section
    # Must NOT bleed into the next section.
    assert "Decision Outcome" not in section


def test_extract_pros_cons():
    section = extract_pros_cons(_SAMPLE_MARKDOWN)
    assert "Managed PostgreSQL" in section
    assert "**Bueno**" in section
    assert "**Malo**" in section
    assert "Links" not in section


def test_parse_adr_sections_returns_dict():
    sections = parse_adr_sections(_SAMPLE_MARKDOWN)
    assert "Context and Problem Statement" in sections
    assert "Decision Outcome" in sections
    assert sections["Context and Problem Statement"].startswith(
        "We need a transactional"
    )