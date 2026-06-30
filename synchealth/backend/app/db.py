"""Async SQLAlchemy engine + session factory for synchealth.

We expose a `get_session` async generator that yields an `AsyncSession`
bound to the application engine. Tests override the engine via
`set_engine` so they can use an in-memory SQLite with `StaticPool`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from .config import get_settings
from .models import Base


# ---------------------------------------------------------------------------
# Engine management
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_engine(database_url: str, *, in_memory: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    For tests we pass `in_memory=True` so a `StaticPool` keeps a single
    shared connection (required for SQLite `:memory:` + multiple async
    sessions).
    """
    if in_memory:
        return create_async_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_async_engine(database_url, future=True)


def init_engine(database_url: str | None = None, *, in_memory: bool = False) -> AsyncEngine:
    """Initialise the global engine (called from `main.lifespan`).

    Passing `database_url=None` uses the settings default; tests pass
    `sqlite+aiosqlite:///:memory:` directly.
    """
    global _engine, _sessionmaker
    if database_url is None:
        database_url = get_settings().database_url
    _engine = build_engine(database_url, in_memory=in_memory)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def set_engine(engine: AsyncEngine) -> None:
    """Replace the engine + sessionmaker (used by tests)."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialised; call init_engine() first")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Sessionmaker not initialised; call init_engine() first")
    return _sessionmaker


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

async def create_all() -> None:
    """Create all tables. Idempotent; safe to call on every boot."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# Session dependency (FastAPI)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an `AsyncSession`. Used both by FastAPI deps and tests."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise