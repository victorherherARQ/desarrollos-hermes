"""Application settings loaded from environment variables.

Uses pydantic-settings so values are validated at startup. Secrets
(`OPENAI_API_KEY`, `GITHUB_TOKEN`) are read from the environment but
must NOT be hard-coded here.

Hardening (rework):
    * `ADR_REPO_PATH` defaults to `/app/data` so ADRs survive container
      restarts (Docker volume `adr-data:/app/data`).
    * The resolved path must exist and be writable — we fail fast at
      boot if it's not.
    * `OPENAI_API_KEY` cannot be empty unless `TESTING=true` (so unit
      tests can run without a real key).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the ADR generator backend."""

    # ---- LLM / MiniMax M3 (OpenAI-compatible) -------------------------------
    OPENAI_BASE_URL: str = "https://api.minimax.io/v1"
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "MiniMax-M3"

    # ---- Git repository where ADRs are stored -------------------------------
    # NOTE: `/app/data` matches the docker-compose volume so ADRs persist
    # across container restarts. `/tmp` is volatile.
    ADR_REPO_PATH: str = "/app/data"
    ADR_BRANCH_PREFIX: str = "adr/"

    # ---- Optional GitHub PR creation ----------------------------------------
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = ""  # format: "owner/repo"

    # ---- HTTP server ---------------------------------------------------------
    BACKEND_PORT: int = 8000

    # ---- Misc ---------------------------------------------------------------
    TESTING: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------ validators

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def _openai_key_must_be_set(cls, value: str, info: Any) -> str:
        """Refuse to boot without an API key (unless TESTING=true).

        Doing this at construction time means the very first import that
        resolves settings will fail loudly instead of waiting for the
        first /generate call.
        """
        testing = bool(info.data.get("TESTING")) if info.data else False
        if not value and not testing and not os.environ.get("TESTING"):
            raise ValueError(
                "OPENAI_API_KEY is not set. Provide it via env var or "
                "backend/.env, or set TESTING=true for unit tests."
            )
        return value

    @field_validator("ADR_REPO_PATH")
    @classmethod
    def _adr_repo_path_must_be_writable(cls, value: str) -> str:
        """Fail fast if the configured path isn't usable.

        We don't require the directory to exist (the app bootstraps it
        on first run), but the parent must be writable so `ensure_repo`
        can `mkdir(parents=True)`.
        """
        if not value or not value.strip():
            raise ValueError("ADR_REPO_PATH must not be empty.")
        path = Path(value).expanduser().resolve()
        # Create the directory if missing — this matches `ensure_repo`'s
        # behaviour and surfaces permission issues at startup.
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(
                f"ADR_REPO_PATH={value!r} is not writable: {exc}"
            ) from exc
        # Probe writability with a no-op file removal.
        probe = path / ".adr-write-probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise ValueError(
                f"ADR_REPO_PATH={value!r} is not writable: {exc}"
            ) from exc
        return value

    # ------------------------------------------------------------------ properties

    @property
    def github_enabled(self) -> bool:
        return bool(self.GITHUB_TOKEN and self.GITHUB_REPO)

    @property
    def adr_repo_path(self) -> Path:
        return Path(self.ADR_REPO_PATH)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()