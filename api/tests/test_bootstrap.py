"""Bootstrap route tests.

Covers:
- first hit creates an anonymous user + session and sets the cookie
- second hit with the same cookie returns the same user
- missing cookie still returns 200 (with a fresh user+cookie)
- response envelope is camelCase and shapes line up with the FE
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Session as DbSession
from app.db.models import User

pytestmark = pytest.mark.asyncio


async def _user_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as s:
        result = await s.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())


async def _session_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as s:
        result = await s.execute(select(func.count()).select_from(DbSession))
        return int(result.scalar_one())


async def test_bootstrap_first_hit_creates_anonymous_user_and_session(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert await _user_count(session_factory) == 0
    assert await _session_count(session_factory) == 0

    response = await client.get("/api/bootstrap")
    assert response.status_code == 200, response.text

    assert await _user_count(session_factory) == 1
    assert await _session_count(session_factory) == 1

    # Cookie set on the response.
    set_cookie = response.headers.get("set-cookie", "")
    assert "sid=" in set_cookie
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()
    assert "Path=/" in set_cookie

    body = response.json()
    # camelCase envelope.
    for key in ("account", "preferences", "usage", "modelTiers", "suggestions", "conversations"):
        assert key in body, f"missing top-level key {key!r}"

    account = body["account"]
    assert account["name"] == "Guest"
    assert account["email"] == ""
    assert account["planLabel"] == "Free"
    assert account["byokEnabled"] is False
    # Anonymous: byokMaskedKey omitted.
    assert "byokMaskedKey" not in account or account["byokMaskedKey"] is None

    prefs = body["preferences"]
    for key in (
        "defaultTierId",
        "temporaryByDefault",
        "trainingOptIn",
        "sendOnEnter",
        "autoExpandReasoning",
    ):
        assert key in prefs

    usage = body["usage"]
    for key in ("used", "limit", "periodLabel", "isByok"):
        assert key in usage
    assert usage["isByok"] is False  # no api_key rows in M0

    tiers = body["modelTiers"]
    assert isinstance(tiers, list) and len(tiers) >= 4
    tier_ids = {t["id"] for t in tiers}
    assert {"auto", "fast", "smart", "pro"}.issubset(tier_ids)
    for tier in tiers:
        for key in ("id", "label", "description", "speedHint", "costHint", "contextHint"):
            assert key in tier

    suggestions = body["suggestions"]
    assert isinstance(suggestions, list) and len(suggestions) >= 1
    for s in suggestions:
        for key in ("id", "icon", "title", "prompt"):
            assert key in s

    assert body["conversations"] == []


async def test_bootstrap_second_hit_returns_same_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    r1 = await client.get("/api/bootstrap")
    assert r1.status_code == 200
    # AsyncClient carries the cookie automatically.
    r2 = await client.get("/api/bootstrap")
    assert r2.status_code == 200

    assert await _user_count(session_factory) == 1
    assert await _session_count(session_factory) == 1

    # No new set-cookie on a successful reuse.
    assert "set-cookie" not in {k.lower() for k in r2.headers}


async def test_bootstrap_missing_cookie_returns_200_with_fresh_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.get("/api/bootstrap", cookies={})
    assert response.status_code == 200
    assert "set-cookie" in {k.lower() for k in response.headers}
    assert await _user_count(session_factory) == 1
