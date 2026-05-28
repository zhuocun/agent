"""Async SQLAlchemy engine + session factory + FastAPI dependency.

A single engine is created lazily from `settings.database_url` on first use.
Lazy construction keeps tests in control: until something actually calls
`get_engine()` / `get_session_factory()`, no real engine is bound, so a test
that overrides `get_db` (or rebinds settings via `cache_clear`) cannot be
poisoned by an import-time engine built off the dev DB. The dependency yields
a transactional session: commit on clean exit, rollback on exception.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    # SQLite needs check_same_thread=False even on the async driver when sessions
    # cross task boundaries; the URL is already aiosqlite-prefixed in tests.
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, building it on first call."""
    return _build_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory, building on first call."""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a transactional session.

    The session is committed if the request handler returns cleanly, rolled
    back otherwise. Either way the session is closed.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
