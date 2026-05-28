"""Auth dependency tests.

Covers:
- signed cookie roundtrip (set, then read back -> same user)
- malformed cookie is silently discarded; a fresh user is created
- expired session row creates a fresh user
- signout clears the cookie and revokes the session row
- /api/auth/upgrade returns 501
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.cookies import build_signer, dump_session_id
from app.config import get_settings
from app.db.models import Session as DbSession
from app.db.models import User

pytestmark = pytest.mark.asyncio


async def test_signed_cookie_roundtrip_keeps_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    r1 = await client.get("/api/bootstrap")
    assert r1.status_code == 200
    user_count_1 = await _user_count(session_factory)
    # Second hit reuses the cookie set by the AsyncClient cookie jar.
    r2 = await client.get("/api/bootstrap")
    assert r2.status_code == 200
    user_count_2 = await _user_count(session_factory)
    assert user_count_1 == user_count_2 == 1


async def test_malformed_cookie_is_discarded(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.get(
        "/api/bootstrap",
        cookies={"sid": "not-a-valid-signed-token"},
    )
    assert response.status_code == 200
    # New user created in place of the missing/invalid cookie.
    assert await _user_count(session_factory) == 1
    # A fresh cookie was set.
    set_cookie = response.headers.get("set-cookie", "")
    assert "sid=" in set_cookie


async def test_well_signed_but_unknown_session_id_is_discarded(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = get_settings()
    signer = build_signer(settings.session_secret)
    bogus_token = dump_session_id(signer, str(uuid4()))

    response = await client.get(
        "/api/bootstrap",
        cookies={"sid": bogus_token},
    )
    assert response.status_code == 200
    # No matching DB session -> create a new user.
    assert await _user_count(session_factory) == 1


async def test_expired_session_creates_fresh_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Seed an expired session for a known user.
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.flush()
        db_session = DbSession(
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        session.add(db_session)
        await session.commit()
        await session.refresh(db_session)
        expired_session_id = db_session.id

    settings = get_settings()
    signer = build_signer(settings.session_secret)
    cookie_value = dump_session_id(signer, str(expired_session_id))

    response = await client.get(
        "/api/bootstrap",
        cookies={"sid": cookie_value},
    )
    assert response.status_code == 200
    # The expired session led to a NEW user + session pair.
    assert await _user_count(session_factory) == 2
    assert await _session_count(session_factory) == 2


async def test_signout_revokes_session_and_clears_cookie(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    r = await client.get("/api/bootstrap")
    assert r.status_code == 200
    assert await _session_count(session_factory) == 1

    out = await client.post("/api/auth/signout")
    assert out.status_code == 204
    assert await _session_count(session_factory) == 0
    # The clear-cookie header should be on the response. Verify the cookie was
    # actually cleared (Max-Age=0 or empty value), not rotated to a fresh
    # session id — otherwise this test would pass on a regression where signout
    # silently issued a new cookie instead of clearing it.
    set_cookie = out.headers.get("set-cookie", "").lower()
    assert "sid=" in set_cookie
    assert "max-age=0" in set_cookie or 'sid=""' in set_cookie or "sid=;" in set_cookie


async def test_upgrade_returns_501(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.post("/api/auth/upgrade", json={})
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"


# Helpers ----------------------------------------------------------------------


async def _user_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as s:
        return int(
            (await s.execute(select(func.count()).select_from(User))).scalar_one()
        )


async def _session_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as s:
        return int(
            (
                await s.execute(select(func.count()).select_from(DbSession))
            ).scalar_one()
        )
