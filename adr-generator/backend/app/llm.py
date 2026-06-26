"""LLM client — OpenAI-compatible wrapper for MiniMax M3.

Exposes a single `generate_adr(form_data)` function. The actual
network call is encapsulated so tests can monkeypatch it.

Hardening (rework):
    * The OpenAI client is constructed with `timeout=60.0` and
      `max_retries=2` so a slow upstream can't hang the worker.
    * `chat.completions.create` is wrapped with `tenacity` to apply
      exponential backoff on transient `RateLimitError` and
      `APIConnectionError`.
    * `_find_next_header` no longer mis-anchors when the very first
      line of `text` starts with `## `.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from openai import APIConnectionError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import get_settings
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

# Public so tests can monkeypatch it cleanly.
openai_chat_factory: Callable[..., Any] = OpenAI

# Cap each chat-completions call at 60s. Combined with tenacity's
# retry budget (max 3 attempts × ~4s backoff) the whole request is
# bounded to a couple of minutes worst-case.
_OPENAI_TIMEOUT_SECONDS = 60.0
_OPENAI_MAX_RETRIES = 2

# How many total attempts tenacity will make (1 initial + N retries).
_TENACITY_ATTEMPTS = 3
# Initial backoff before the first retry; subsequent retries double.
_TENACITY_INITIAL_BACKOFF = 1.0
_TENACITY_MAX_BACKOFF = 8.0


def _make_client() -> OpenAI:
    settings = get_settings()
    return openai_chat_factory(
        base_url=settings.OPENAI_BASE_URL,
        api_key=settings.OPENAI_API_KEY,
        timeout=_OPENAI_TIMEOUT_SECONDS,
        max_retries=_OPENAI_MAX_RETRIES,
    )


def _chat_with_retry(client: Any, **kwargs: Any) -> Any:
    """Call `client.chat.completions.create(**kwargs)` with tenacity retry.

    Exponential backoff (1s → 2s → 4s) on transient transport/limit
    errors. Real network failures and 4xx that aren't rate-limit still
    propagate so callers (and the FastAPI error handler) see them.
    """
    retry_decorator = retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        wait=wait_exponential(
            multiplier=_TENACITY_INITIAL_BACKOFF,
            max=_TENACITY_MAX_BACKOFF,
        ),
        stop=stop_after_attempt(_TENACITY_ATTEMPTS),
        reraise=True,
    )
    return retry_decorator(client.chat.completions.create)(**kwargs)


def generate_adr(form_data: Dict[str, Any], *, client: Optional[Any] = None) -> str:
    """Generate a MADR 4.0 ADR body from a structured form payload.

    Returns the raw markdown string emitted by the LLM. If the model
    returns an empty completion the function raises `RuntimeError`.
    """
    if client is None:
        client = _make_client()

    settings = get_settings()
    response = _chat_with_retry(
        client,
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(form_data)},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError, KeyError) as exc:
        raise RuntimeError(f"Unexpected LLM response shape: {exc}") from exc

    if not content.strip():
        raise RuntimeError("LLM returned an empty ADR body.")

    # Strip stray code fences the model sometimes wraps the doc in.
    content = _strip_code_fences(content)
    return content


def _strip_code_fences(text: str) -> str:
    """Strip ```markdown fences if (and only if) the LLM wrapped them.

    When there is no fence we return the input untouched, so a perfectly
    formatted Markdown doc preserves its trailing newline.
    """
    if not text.lstrip().startswith("```"):
        return text
    text = text.strip()
    first_newline = text.find("\n")
    if first_newline != -1:
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text


def extract_considered_options(markdown: str) -> str:
    """Pull the `## Considered Options` section out of the LLM output."""
    return _extract_section(markdown, "## Considered Options")


def extract_pros_cons(markdown: str) -> str:
    """Pull the `## Pros and Cons of the Options` section out."""
    return _extract_section(markdown, "## Pros and Cons of the Options")


def _extract_section(markdown: str, header: str) -> str:
    if header not in markdown:
        return ""
    start = markdown.index(header) + len(header)
    rest = markdown[start:]
    next_header_idx = _find_next_header(rest)
    if next_header_idx == -1:
        return rest.strip()
    return rest[:next_header_idx].strip()


def _find_next_header(text: str, start: int = 0) -> int:
    """Return the char offset of the next line starting with `## `.

    Reworked so the boundary case `i == 0` (first line begins with
    `## `) is no longer returned as `len(text)` (which used to mis-
    extract the next section). Now we always anchor against `start`,
    so callers can scan past the section they already consumed.
    """
    for line in text.splitlines():
        try:
            offset = text.index(line, start)
        except ValueError:
            # Same line appears earlier; keep searching.
            continue
        if offset >= start and line.startswith("## "):
            return offset
    return -1


def parse_adr_sections(markdown: str) -> Dict[str, str]:
    """Convenience helper — return a dict of {section_name: body}."""
    sections: Dict[str, str] = {}
    lines = markdown.splitlines()
    current: Optional[str] = None
    buf: list[str] = []
    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


__all__ = [
    "generate_adr",
    "extract_considered_options",
    "extract_pros_cons",
    "parse_adr_sections",
    "openai_chat_factory",
    "SYSTEM_PROMPT",
    "build_user_prompt",
]