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

from app.config import Settings
from app.db.models import ApiKey, User
from app.db.models import Session as DbSession
from app.db.repositories import api_keys as api_keys_repo
from app.db.repositories import usage as usage_repo
from app.routes import bootstrap as bootstrap_routes

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
        "retentionDays",
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
        for key in (
            "id",
            "label",
            "description",
            "speedHint",
            "costHint",
            "contextHint",
            "modelLabel",
            "supportsWebSearch",
            "supportsAttachments",
            "providerId",
            "providerLabel",
            "providerRouteStatus",
            "defaultRouteEligible",
            "dataPolicy",
            "providerOptions",
        ):
            assert key in tier
    # The picker discloses each tier's model (friendly label, never a raw id);
    # `auto` is blank because its served model varies per message.
    by_id = {t["id"]: t for t in tiers}
    assert by_id["fast"]["modelLabel"] == "DeepSeek V4 Flash"
    assert by_id["pro"]["modelLabel"] == "DeepSeek V4 Pro"
    assert by_id["auto"]["modelLabel"] == ""
    assert by_id["fast"]["providerId"] == "fake"
    assert by_id["fast"]["providerLabel"] == "Fake"
    assert by_id["fast"]["providerRouteStatus"] == "available"
    assert by_id["fast"]["defaultRouteEligible"] is False
    assert by_id["fast"]["dataPolicy"]["policyLabel"] == "Local deterministic test route"
    options = {option["providerId"]: option for option in by_id["fast"]["providerOptions"]}
    assert set(options) == {"deepseek", "anthropic", "openai", "gemini", "fake"}
    assert options["deepseek"]["label"] == "DeepSeek"
    assert options["deepseek"]["status"] == "unavailable"
    assert options["deepseek"]["modelLabel"] == "DeepSeek V4 Flash"
    assert options["anthropic"]["status"] == "unavailable"
    assert options["anthropic"]["modelLabel"] == "Claude Haiku 4.5"
    assert options["openai"]["status"] == "unavailable"
    assert options["openai"]["modelLabel"] == "gpt-4o-mini"
    assert options["fake"]["status"] == "available"
    assert options["fake"]["modelLabel"] == "Fake"
    assert options["gemini"]["status"] == "pending"
    assert options["gemini"]["supportsWebSearch"] is False
    assert options["gemini"]["supportsAttachments"] is False
    # Test config sets SEARCH_BACKEND=fake, so search is enabled and every real
    # tier (including `auto`, whose binding supports search via the tool loop)
    # reports the capability. The wire flag = binding.supports_web_search AND
    # search_enabled(settings); with the fake backend that's True for all.
    for tier_id in ("auto", "fast", "smart", "pro"):
        assert by_id[tier_id]["supportsWebSearch"] is True
        assert by_id[tier_id]["supportsAttachments"] is True

    suggestions = body["suggestions"]
    assert isinstance(suggestions, list) and len(suggestions) >= 1
    for s in suggestions:
        for key in ("id", "icon", "title", "prompt"):
            assert key in s

    assert body["conversations"] == []


async def test_bootstrap_ignores_corrupt_byok_for_provider_availability(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    upgrade = await client.post(
        "/api/auth/upgrade",
        json={"email": "u@example.com", "password": "hunter2hunter2"},
    )
    assert upgrade.status_code == 200
    put = await client.put(
        "/api/account/byok",
        json={"provider": "openai", "apiKey": "sk-openai-fake-12345678"},
    )
    assert put.status_code == 200

    async with session_factory() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        row.ciphertext = "not-valid-base64!!!"
        await session.commit()

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    fast = next(tier for tier in boot.json()["modelTiers"] if tier["id"] == "fast")
    options = {option["providerId"]: option for option in fast["providerOptions"]}
    assert options["openai"]["status"] == "unavailable"


async def test_bootstrap_active_byok_state_requires_decryptable_key(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    upgrade = await client.post(
        "/api/auth/upgrade",
        json={"email": "u@example.com", "password": "hunter2hunter2"},
    )
    assert upgrade.status_code == 200
    put = await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "sk-deepseek-fake-12345678"},
    )
    assert put.status_code == 200

    async with session_factory() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        row.ciphertext = "not-valid-base64!!!"
        await session.commit()

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    account = boot.json()["account"]
    assert account["byokEnabled"] is False
    assert account.get("byokMaskedKey") is None
    assert account["byokKeys"] == [
        {
            "providerId": "deepseek",
            "providerLabel": "DeepSeek",
            "maskedKey": "sk-...5678",
            "usable": False,
        }
    ]
    assert boot.json()["usage"]["isByok"] is False


async def test_bootstrap_does_not_mark_fake_byok_available_in_production(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await client.get("/api/bootstrap")
    upgrade = await client.post(
        "/api/auth/upgrade",
        json={"email": "u@example.com", "password": "hunter2hunter2"},
    )
    assert upgrade.status_code == 200

    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        await api_keys_repo.upsert(
            session,
            user_id=user.id,
            provider="fake",
            raw_api_key="fake-key-12345678",
        )
        await session.commit()

    monkeypatch.setattr(
        bootstrap_routes,
        "get_settings",
        lambda: Settings(
            provider_backend="deepseek",
            deepseek_api_key="k",
            env="production",
        ),
    )

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    fast = next(tier for tier in boot.json()["modelTiers"] if tier["id"] == "fast")
    options = {option["providerId"]: option for option in fast["providerOptions"]}
    assert options["deepseek"]["status"] == "available"
    assert options["fake"]["status"] == "unavailable"


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


async def test_bootstrap_exposes_credit_balance_and_recent_ledger(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        await usage_repo.grant_credits(
            session,
            user_id=user.id,
            amount_usd=7.5,
            description="Test grant",
        )
        await session.commit()

    response = await client.get("/api/bootstrap")
    assert response.status_code == 200
    usage = response.json()["usage"]
    assert usage["creditBalanceUsd"] == pytest.approx(7.5)
    assert usage["recentLedgerEntries"][0]["entryType"] == "grant"
    assert usage["recentLedgerEntries"][0]["amountUsd"] == pytest.approx(7.5)
    assert usage["recentLedgerEntries"][0]["description"] == "Test grant"
