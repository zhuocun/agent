"""Rate limit tests for `POST /api/conversations/:id/messages`.

Covers:
- The configured `rate_limit_messages` budget enforces 429 once exceeded.
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers
  are emitted on both 200 and 429 responses.
- A `RATE_LIMIT_MESSAGES` env override (with `get_settings` cache cleared)
  changes the budget at app-build time, so a fresh `2/minute` budget tips
  the third request into 429.

The limiter is in-process; tests reset the storage between runs by minting a
fresh `Limiter` on each `create_app()` call (slowapi keys by route and the
configured `get_remote_address` which is `testclient`'s loopback). To keep
tests independent we monkeypatch the module-level singleton's storage to a
clean `MemoryStorage` per test via the `app.state.limiter` handle.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, User
from app.db.session import get_db

pytestmark = pytest.mark.asyncio


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> str:
    """Seed an owned conversation; return id as str."""
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id=tier_id,
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


def _build_send_body() -> dict[str, object]:
    """Fresh body with a new client_message_id so idempotent replay is skipped."""
    return {
        "clientMessageId": str(uuid4()),
        "tierId": "smart",
        "text": "hello world",
    }


def _reset_limiter_storage(app: FastAPI) -> None:
    """Clear the limiter's in-memory storage so prior tests don't carry over."""
    # `Limiter._storage` holds the `MemoryStorage` keyed by limit string + ip.
    storage = app.state.limiter._storage
    if hasattr(storage, "storage"):
        storage.storage.clear()
    if hasattr(storage, "expirations"):
        storage.expirations.clear()


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    from sqlalchemy import select

    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


@pytest.fixture
def rate_limited_app_env() -> Iterator[None]:
    """Override `RATE_LIMIT_MESSAGES=2/minute` for the duration of the test."""
    prior = os.environ.get("RATE_LIMIT_MESSAGES")
    os.environ["RATE_LIMIT_MESSAGES"] = "2/minute"
    # Settings is `@lru_cache`d -- bust it so the new env is read on next call.
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("RATE_LIMIT_MESSAGES", None)
        else:
            os.environ["RATE_LIMIT_MESSAGES"] = prior
        get_settings.cache_clear()


@pytest.fixture
def rate_limited_app(
    rate_limited_app_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_db_path: Path,
) -> Iterator[FastAPI]:
    """Build a fresh app under the `2/minute` override, reusing the test DB."""
    from app.main import create_app
    from app.routes.conversations import _TEMP_IDS

    _TEMP_IDS.clear()
    app_ = create_app()
    _reset_limiter_storage(app_)

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
async def rate_limited_client(rate_limited_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=rate_limited_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client_:
        yield client_


async def test_send_message_emits_rate_limit_headers_on_success(
    app: FastAPI,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A 200 response carries `X-RateLimit-*` headers (slowapi headers_enabled)."""
    _reset_limiter_storage(app)
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json=_build_send_body(),
        timeout=10.0,
    ) as resp:
        # Drain the body so the connection closes cleanly.
        async for _ in resp.aiter_bytes():
            pass
        assert resp.status_code == 200, resp.headers
        # Slowapi emits these on every limited response when headers_enabled=True.
        # Pin "exactly one" emission — the RateLimitMiddleware override guards
        # against double-injection (decorator + middleware) on dynamic limits.
        assert resp.headers.get_list("x-ratelimit-limit") == ["30"]
        assert len(resp.headers.get_list("x-ratelimit-remaining")) == 1
        assert len(resp.headers.get_list("x-ratelimit-reset")) == 1


async def test_send_message_rate_limit_override_returns_429_on_third_call(
    rate_limited_app: FastAPI,
    rate_limited_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`RATE_LIMIT_MESSAGES=2/minute` => calls 1 & 2 pass, call 3 hits 429."""
    # The rate_limited_app is built after the env override is in effect.
    await rate_limited_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Drain each streaming response so the connection finishes before the next.
    async def _post_send() -> tuple[int, dict[str, str]]:
        async with rate_limited_client.stream(
            "POST",
            f"/api/conversations/{conv_id}/messages",
            json=_build_send_body(),
            timeout=10.0,
        ) as resp:
            async for _ in resp.aiter_bytes():
                pass
            return resp.status_code, dict(resp.headers)

    s1, h1 = await _post_send()
    assert s1 == 200, h1
    s2, h2 = await _post_send()
    assert s2 == 200, h2

    # Third call must be rate-limited.
    s3, h3 = await _post_send()
    assert s3 == 429, h3
    # The 429 response must carry the standard limit headers from the
    # _rate_limit_exceeded_handler path.
    # Slowapi names the header `x-ratelimit-limit`; clients/tests see it
    # lower-cased through httpx.
    assert h3.get("x-ratelimit-limit") == "2"
    assert h3.get("x-ratelimit-remaining") == "0"
    assert "retry-after" in h3
