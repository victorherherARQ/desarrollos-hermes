"""Application settings loaded from environment variables.

Uses pydantic-settings so values are validated at startup. Secrets
(`ZEPP_API_TOKEN`, `GARMIN_OAUTH_TOKEN`) are read from the environment
but must NOT be hard-coded here.

Hardening:
    * `DB_PATH` defaults to `/app/data/synchealth.db` so the SQLite
      file survives container restarts (Docker volume).
    * `BACKEND_PORT` defaults to `8790` to match the compose file.
    * `TESTING=true` short-circuits external credential checks so the
      test suite can run without a real Zepp or Garmin token.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the synchealth backend."""

    # ---- Persistence -------------------------------------------------------
    DB_PATH: str = "/app/data/synchealth.db"

    # ---- External integrations (MVP 1.1 / 1.2) ----------------------------
    # Kept here so the Settings model is stable; the values are not used
    # in MVP 1.0.
    ZEPP_CSV_PATH: str = ""
    ZEPP_API_TOKEN: str = ""
    GARMIN_OAUTH_TOKEN: str = ""

    # ---- HTTP server -------------------------------------------------------
    BACKEND_PORT: int = 8790

    # ---- Misc --------------------------------------------------------------
    APP_VERSION: str = "0.1.0"
    TESTING: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """SQLAlchemy async URL for the configured SQLite file."""
        return f"sqlite+aiosqlite:///{self.DB_PATH}"

    @property
    def db_path(self) -> Path:
        """Filesystem path to the SQLite file (for `init_db` mkdir -p)."""
        return Path(self.DB_PATH)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor (same pattern as adr-generator)."""
    return Settings()