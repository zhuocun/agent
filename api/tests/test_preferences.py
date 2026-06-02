"""User preferences route tests (M2).

Covers:
- Bootstrap returns the defaults when no preferences row exists.
- PUT replaces the row; subsequent bootstrap reflects the new values.
- PUT validates: an unknown `defaultTierId` is rejected as INVALID_INPUT.
- PUT requires all original fields; `telemetryEnabled` may be omitted.
- Anonymous users can PUT preferences.
- PUT twice with different bodies persists the second body (replacement).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Preferences, User

pytestmark = pytest.mark.asyncio


_VALID_BODY = {
    "defaultTierId": "smart",
    "temporaryByDefault": True,
    "trainingOptIn": True,
    "sendOnEnter": False,
    "autoExpandReasoning": True,
    "telemetryEnabled": True,
    "customInstructions": "Answer tersely and use bullets.",
    "retentionDays": 90,
}


async def _row_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as s:
        return int((await s.execute(select(func.count()).select_from(Preferences))).scalar_one())


async def test_bootstrap_returns_defaults_when_no_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.get("/api/bootstrap")
    assert response.status_code == 200
    prefs = response.json()["preferences"]
    # Mirrors web/src/lib/mock-data.ts:MOCK_PREFERENCES.
    assert prefs == {
        "defaultTierId": "auto",
        "temporaryByDefault": False,
        "trainingOptIn": False,
        "sendOnEnter": True,
        "autoExpandReasoning": False,
        "telemetryEnabled": True,
        "customInstructions": "",
        "retentionDays": None,
    }
    # Bootstrap should NOT silently insert a row.
    assert await _row_count(session_factory) == 0


async def test_put_then_bootstrap_returns_new_values(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Bootstrap creates the user; subsequent PUT stores prefs for that user.
    await client.get("/api/bootstrap")

    put = await client.put("/api/preferences", json=_VALID_BODY)
    assert put.status_code == 204
    assert await _row_count(session_factory) == 1

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    assert boot.json()["preferences"] == _VALID_BODY


async def test_put_accepts_retention_forever(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    body = dict(_VALID_BODY)
    body["retentionDays"] = None

    put = await client.put("/api/preferences", json=body)
    assert put.status_code == 204

    boot = await client.get("/api/bootstrap")
    assert boot.json()["preferences"]["retentionDays"] is None


async def test_put_omitted_telemetry_preserves_existing_opt_out(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    opted_out = dict(_VALID_BODY)
    opted_out["telemetryEnabled"] = False
    assert (await client.put("/api/preferences", json=opted_out)).status_code == 204

    stale_client_body = dict(_VALID_BODY)
    stale_client_body.pop("telemetryEnabled")
    stale_client_body["defaultTierId"] = "fast"
    response = await client.put("/api/preferences", json=stale_client_body)
    assert response.status_code == 204

    boot = await client.get("/api/bootstrap")
    prefs = boot.json()["preferences"]
    assert prefs["defaultTierId"] == "fast"
    assert prefs["telemetryEnabled"] is False


async def test_put_omitted_custom_instructions_preserves_existing(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    first = dict(_VALID_BODY)
    first["customInstructions"] = "Prefer concise answers."
    assert (await client.put("/api/preferences", json=first)).status_code == 204

    stale_client_body = dict(_VALID_BODY)
    stale_client_body.pop("customInstructions")
    stale_client_body["defaultTierId"] = "fast"
    response = await client.put("/api/preferences", json=stale_client_body)
    assert response.status_code == 204

    boot = await client.get("/api/bootstrap")
    prefs = boot.json()["preferences"]
    assert prefs["defaultTierId"] == "fast"
    assert prefs["customInstructions"] == "Prefer concise answers."


async def test_put_finite_retention_erases_expired_conversations(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    now = datetime.now(UTC)
    async with session_factory() as s:
        user = (await s.execute(select(User))).scalar_one()
        old = Conversation(
            user_id=user.id,
            title="old",
            selected_tier_id="smart",
            pinned=False,
            updated_at=now - timedelta(days=40),
        )
        fresh = Conversation(
            user_id=user.id,
            title="fresh",
            selected_tier_id="smart",
            pinned=False,
            updated_at=now - timedelta(days=5),
        )
        s.add_all([old, fresh])
        await s.commit()
        fresh_id = fresh.id

    body = dict(_VALID_BODY)
    body["retentionDays"] = 30
    response = await client.put("/api/preferences", json=body)
    assert response.status_code == 204

    async with session_factory() as s:
        rows = (await s.execute(select(Conversation))).scalars().all()
        assert [row.id for row in rows] == [fresh_id]


async def test_put_rejects_unknown_retention_days(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    bad = dict(_VALID_BODY)
    bad["retentionDays"] = 7

    response = await client.put("/api/preferences", json=bad)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_put_rejects_unknown_tier(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    bad = dict(_VALID_BODY)
    bad["defaultTierId"] = "giant"

    response = await client.put("/api/preferences", json=bad)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_put_rejects_missing_fields(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    partial = {"defaultTierId": "smart"}
    response = await client.put("/api/preferences", json=partial)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_put_rejects_too_long_custom_instructions(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    bad = dict(_VALID_BODY)
    bad["customInstructions"] = "x" * 4001

    response = await client.put("/api/preferences", json=bad)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_put_rejects_blocklisted_custom_instructions(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("SAFETY_BACKEND", "local")
    monkeypatch.setenv("SAFETY_BLOCKLIST", "do-not-save")
    get_settings.cache_clear()
    try:
        await client.get("/api/bootstrap")
        bad = dict(_VALID_BODY)
        bad["customInstructions"] = "Always do-not-save in replies."

        response = await client.put("/api/preferences", json=bad)

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "SAFETY_BLOCKED"
        assert error["meta"]["source"] == "custom_instructions"
        assert await _row_count(session_factory) == 0
    finally:
        get_settings.cache_clear()


async def test_anonymous_user_can_put_preferences(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No prior bootstrap -- PUT itself triggers anonymous-user creation."""
    response = await client.put("/api/preferences", json=_VALID_BODY)
    assert response.status_code == 204

    async with session_factory() as s:
        users = (await s.execute(select(User))).scalars().all()
        prefs = (await s.execute(select(Preferences))).scalars().all()
        assert len(users) == 1
        assert users[0].is_anonymous is True
        assert len(prefs) == 1
        assert prefs[0].user_id == users[0].id
        assert prefs[0].custom_instructions == _VALID_BODY["customInstructions"]


async def test_put_replaces_existing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    # First PUT — store one set.
    first_body = dict(_VALID_BODY)
    first_body["defaultTierId"] = "fast"
    r1 = await client.put("/api/preferences", json=first_body)
    assert r1.status_code == 204
    # Second PUT — overwrite with a different set.
    second_body = dict(_VALID_BODY)
    second_body["defaultTierId"] = "pro"
    second_body["sendOnEnter"] = True
    r2 = await client.put("/api/preferences", json=second_body)
    assert r2.status_code == 204

    # Still exactly one row, holding the second body.
    async with session_factory() as s:
        rows = (await s.execute(select(Preferences))).scalars().all()
        assert len(rows) == 1
        assert rows[0].default_tier_id == "pro"
        assert rows[0].send_on_enter is True

    boot = await client.get("/api/bootstrap")
    assert boot.json()["preferences"] == second_body


async def test_put_persists_per_user(
    app: FastAPI,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two clients (separate cookie jars) get their own preferences rows."""
    # Client A — the existing fixture client.
    await client.get("/api/bootstrap")
    body_a = dict(_VALID_BODY)
    body_a["defaultTierId"] = "fast"
    await client.put("/api/preferences", json=body_a)

    # Client B — fresh cookie jar on the same FastAPI app.
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        body_b = dict(_VALID_BODY)
        body_b["defaultTierId"] = "pro"
        await client_b.put("/api/preferences", json=body_b)

        boot_b = await client_b.get("/api/bootstrap")
        assert boot_b.json()["preferences"]["defaultTierId"] == "pro"

    # Client A still sees the fast tier.
    boot_a = await client.get("/api/bootstrap")
    assert boot_a.json()["preferences"]["defaultTierId"] == "fast"

    # Two users, two preferences rows.
    async with session_factory() as s:
        n_users = int((await s.execute(select(func.count()).select_from(User))).scalar_one())
        n_prefs = int((await s.execute(select(func.count()).select_from(Preferences))).scalar_one())
        assert n_users == 2
        assert n_prefs == 2


async def test_put_with_unused_extra_field_is_accepted(
    client: AsyncClient,
) -> None:
    """Pydantic by default ignores unknown fields. Confirm the route still 204s."""
    await client.get("/api/bootstrap")
    body = dict(_VALID_BODY)
    body["extraField"] = "ignored"
    response = await client.put("/api/preferences", json=body)
    assert response.status_code == 204


async def test_preferences_row_has_user_fk(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await client.put("/api/preferences", json=_VALID_BODY)

    async with session_factory() as s:
        user = (await s.execute(select(User))).scalar_one()
        prefs = (await s.execute(select(Preferences))).scalar_one()
        assert isinstance(prefs.user_id, UUID)
        assert prefs.user_id == user.id
