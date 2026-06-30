"""Shared pytest fixtures for synchealth backend tests.

* `client` — `TestClient` wrapping the FastAPI app with a per-test
  SQLite file.
* `session` — async SQLAlchemy session bound to the same DB.
* `sample_csv_path` / `sample_csv_bytes` — fixture CSV for tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# CSV fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_csv_path() -> Path:
    return FIXTURES_DIR / "zepp_sample.csv"


@pytest.fixture
def sample_csv_bytes(sample_csv_path: Path) -> bytes:
    return sample_csv_path.read_bytes()


# ---------------------------------------------------------------------------
# Async engine + session (for tests that hit the DB directly)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator:
    """Standalone async session backed by a fresh SQLite file."""
    db_file = tmp_path / "models_test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("TESTING", "true")

    from app.config import get_settings
    from app.db import create_all, get_sessionmaker, init_engine

    get_settings.cache_clear()  # type: ignore[attr-defined]
    init_engine(f"sqlite+aiosqlite:///{db_file}", in_memory=False)
    await create_all()

    sm = get_sessionmaker()
    async with sm() as s:
        try:
            yield s
        finally:
            pass

    get_settings.cache_clear()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """A `TestClient` whose DB is an isolated file under `tmp_path`."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("TESTING", "true")

    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Reload db + main so they pick up the fresh settings + lifespan.
    import importlib
    from app import db as db_mod
    from app import main as main_mod

    importlib.reload(db_mod)
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        yield c

    get_settings.cache_clear()  # type: ignore[attr-defined]