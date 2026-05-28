"""Shared pytest fixtures.

Each test gets its own SQLite database (file-backed for cross-task safety) and
its own FastAPI app instance with the engine + session factory swapped to that
database. We use ASGI transport so requests reach the app without a network
hop and cookies persist via `httpx.AsyncClient`'s cookie jar.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

# Configure env BEFORE importing app modules — pydantic-settings reads env at
# the moment `get_settings()` is first called.
os.environ.setdefault("ENV", "test")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-fixed-and-long-enough")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("COOKIE_SAMESITE", "lax")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture
def sqlite_db_path() -> AsyncIterator[Path]:
    """Per-test sqlite file. File-backed so multiple sessions see each other."""
    fd, path = tempfile.mkstemp(prefix="api-test-", suffix=".sqlite3")
    os.close(fd)
    p = Path(path)
    try:
        yield p
    finally:
        p.unlink(missing_ok=True)


@pytest.fixture
async def engine(sqlite_db_path: Path) -> AsyncIterator[AsyncEngine]:
    """Async engine pointed at the per-test sqlite file, schema created."""
    url = f"sqlite+aiosqlite:///{sqlite_db_path}"
    eng = create_async_engine(url, connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
def app(session_factory: async_sessionmaker[AsyncSession]) -> Iterator[FastAPI]:
    """Build a fresh FastAPI app with our test session factory wired in."""
    # Reset settings cache so any env tweaks land.
    get_settings.cache_clear()
    from app.main import create_app
    from app.routes.conversations import _TEMP_IDS

    # Module-level state is shared across tests; clear it before AND after
    # yield so a flaky prior test cannot leak temp ids into this one.
    _TEMP_IDS.clear()

    app_ = create_app()

    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app_.dependency_overrides[get_db] = _get_db_override
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client_:
        yield client_
