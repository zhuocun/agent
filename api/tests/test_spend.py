"""Spend-analytics dashboard + per-conversation budget cap tests (D27).

Covers the longitudinal spend endpoint (`GET /api/account/spend`) and the
per-conversation budget gate layered over the existing monthly gate:

- The endpoint returns both honest cost bases (cumulative meter vs surviving
  messages), zero-filled daily buckets, by-model grouping (incl. the
  "Stopped/uncosted" bucket for attribution-less rows), and top-N
  by-conversation buckets.
- `days` is clamped (1..365) and old messages fall outside the window.
- The per-conversation cap refuses the next platform-key turn once the
  conversation's accumulated surviving-assistant cost reaches the cap, while a
  fresh conversation is unaffected.
- Preferences round-trip the new `perConversationBudgetUsd` field.

Uses the fake provider (env defaults to `PROVIDER_BACKEND=fake`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
    normalized = response_text.replace("\r\n", "\n").replace("\r", "\n")
    frames: list[tuple[str, dict[str, object]]] = []
    for chunk in normalized.split("\n\n"):
        if not chunk.strip():
            continue
        event_name: str | None = None
        data_payload: str | None = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                fragment = line[len("data:") :].strip()
                data_payload = fragment if data_payload is None else data_payload + fragment
        if event_name is None or data_payload is None:
            continue
        try:
            parsed = json.loads(data_payload)
        except json.JSONDecodeError:
            parsed = {}
        frames.append((event_name, parsed))
    return frames


async def _collect_sse(
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


def _send_body() -> dict[str, object]:
    return {
        "clientMessageId": str(uuid4()),
        "tierId": "smart",
        "text": "hello world",
    }


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    title: str = "New chat",
) -> str:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title=title,
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


def _attribution(label: str, tier_id: str = "smart") -> dict[str, object]:
    return {
        "requestedTierId": tier_id,
        "servedTierId": tier_id,
        "servedModelLabel": label,
        "providerId": "deepseek",
        "providerLabel": "DeepSeek",
        "isByok": False,
        "costUsd": 0.0,
        "costConfidence": "exact",
        "breakdown": {
            "currency": "USD",
            "listPriceInPerM": 0.14,
            "listPriceOutPerM": 0.28,
            "inputTokens": 10,
            "outputTokens": 10,
            "reasoningTokens": 0,
            "cachedInputTokens": 0,
            "longContext": {"flat": True},
            "promoApplied": False,
            "subtotalUsd": 0.0,
            "sessionSurchargeUsd": 0.0,
        },
    }


async def _seed_assistant_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conversation_id: str,
    cost_usd: float | None,
    attribution: dict[str, object] | None,
    created_at: datetime,
) -> None:
    from uuid import UUID

    async with session_factory() as session:
        msg = Message(
            conversation_id=UUID(conversation_id),
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "answer"}],
            status="done",
            attribution=attribution,
            cost_usd=cost_usd,
            created_at=created_at,
        )
        session.add(msg)
        await session.commit()


# Spend endpoint ---------------------------------------------------------------


async def test_spend_endpoint_buckets_and_totals(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)

    now = datetime.now(UTC)
    conv_a = await _seed_conversation(session_factory, user_id=user_id, title="Alpha")
    conv_b = await _seed_conversation(session_factory, user_id=user_id, title="Beta")

    # conv_a: two priced turns by "DeepSeek V4 Flash" + one uncosted (no attr).
    await _seed_assistant_message(
        session_factory,
        conversation_id=conv_a,
        cost_usd=0.10,
        attribution=_attribution("DeepSeek V4 Flash"),
        created_at=now - timedelta(days=1, hours=1),
    )
    await _seed_assistant_message(
        session_factory,
        conversation_id=conv_a,
        cost_usd=0.20,
        attribution=_attribution("DeepSeek V4 Flash"),
        created_at=now - timedelta(hours=2),
    )
    await _seed_assistant_message(
        session_factory,
        conversation_id=conv_a,
        cost_usd=None,
        attribution=None,
        created_at=now - timedelta(hours=1),
    )
    # conv_b: one pricier turn by "DeepSeek V4 Pro".
    await _seed_assistant_message(
        session_factory,
        conversation_id=conv_b,
        cost_usd=0.50,
        attribution=_attribution("DeepSeek V4 Pro", tier_id="pro"),
        created_at=now - timedelta(hours=3),
    )
    # An OLD message outside a 7-day window (should be excluded when days=7).
    await _seed_assistant_message(
        session_factory,
        conversation_id=conv_b,
        cost_usd=9.99,
        attribution=_attribution("DeepSeek V4 Flash"),
        created_at=now - timedelta(days=40),
    )

    resp = await client.get("/api/account/spend?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["rangeDays"] == 7
    assert body["currency"] == "USD"
    # Surviving messages within the window: 0.10 + 0.20 + 0.00 (uncosted) + 0.50.
    assert body["survivingMessagesUsd"] == pytest.approx(0.80)

    # daily is zero-filled and ascending; the last day's date == today (UTC).
    daily = body["daily"]
    assert isinstance(daily, list) and len(daily) >= 7
    dates = [d["date"] for d in daily]
    assert dates == sorted(dates)
    assert dates[-1] == now.date().isoformat()
    # Sum of daily costs equals the surviving total.
    assert sum(d["costUsd"] for d in daily) == pytest.approx(0.80)

    # by_model: Pro (0.50) leads, then Flash (0.30), then the uncosted bucket.
    by_model = {b["label"]: b for b in body["byModel"]}
    assert by_model["DeepSeek V4 Pro"]["costUsd"] == pytest.approx(0.50)
    assert by_model["DeepSeek V4 Pro"]["tierId"] == "pro"
    assert by_model["DeepSeek V4 Flash"]["costUsd"] == pytest.approx(0.30)
    assert by_model["DeepSeek V4 Flash"]["messageCount"] == 2
    assert "Stopped/uncosted" in by_model
    assert by_model["Stopped/uncosted"]["messageCount"] == 1
    # Sorted by cost desc.
    assert body["byModel"][0]["label"] == "DeepSeek V4 Pro"

    # by_conversation: Beta (0.50) leads Alpha (0.30); the old 9.99 excluded.
    by_convo = body["byConversation"]
    assert by_convo[0]["title"] == "Beta"
    assert by_convo[0]["costUsd"] == pytest.approx(0.50)
    titles = {c["title"]: c for c in by_convo}
    assert titles["Alpha"]["costUsd"] == pytest.approx(0.30)
    assert titles["Alpha"]["messageCount"] == 3


async def test_spend_endpoint_allows_anonymous_and_clamps_days(
    client: AsyncClient,
) -> None:
    # Anonymous (bootstrap mints a guest) can read their own spend.
    await client.get("/api/bootstrap")
    resp = await client.get("/api/account/spend")
    assert resp.status_code == 200
    assert resp.json()["rangeDays"] == 30  # default

    # Out-of-range days are clamped (not rejected) to 1..365.
    too_big = await client.get("/api/account/spend?days=1000")
    assert too_big.status_code == 200
    assert too_big.json()["rangeDays"] == 365
    too_small = await client.get("/api/account/spend?days=0")
    assert too_small.status_code == 200
    assert too_small.json()["rangeDays"] == 1


# Per-conversation budget cap --------------------------------------------------


async def _set_per_conversation_budget(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    cap: float | None,
) -> None:
    from app.db.repositories import preferences as preferences_repo

    async with session_factory() as session:
        prefs = await preferences_repo.get_or_default(session, user_id)  # type: ignore[arg-type]
        updated = prefs.model_copy(update={"per_conversation_budget_usd": cap})
        await preferences_repo.upsert(session, user_id, updated)  # type: ignore[arg-type]
        await session.commit()


async def test_per_conversation_cap_blocks_once_reached(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The per-conversation cap refuses the next platform-key turn once the
    conversation's accumulated cost crosses the tiny cap; a fresh conversation
    is unaffected (the cap is per-conversation)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Tiny cap; one fake turn's cost exceeds it.
    await _set_per_conversation_budget(
        session_factory, user_id=user_id, cap=0.0000001
    )

    # Turn 1 passes (accumulated cost starts at 0 < cap) and writes a cost over
    # the cap.
    await _collect_sse(client, f"/api/conversations/{conv_id}/messages", _send_body())

    # Turn 2 in the SAME conversation: pre-flight gate sees accumulated cost >=
    # cap -> 429 CONVERSATION_BUDGET_EXCEEDED.
    resp = await client.post(
        f"/api/conversations/{conv_id}/messages", json=_send_body()
    )
    assert resp.status_code == 429, resp.text
    payload = resp.json()
    assert payload["error"]["code"] == "CONVERSATION_BUDGET_EXCEEDED"
    assert payload["error"]["severity"] == "warning"
    assert payload["error"]["actions"][0]["kind"] == "open_settings"

    # A DIFFERENT conversation is not blocked — the cap is per-conversation.
    other_id = await _seed_conversation(session_factory, user_id=user_id)
    frames = await _collect_sse(
        client, f"/api/conversations/{other_id}/messages", _send_body()
    )
    assert frames[-1][0] == "terminal"


async def test_per_conversation_cap_byok_exempt(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A BYOK turn bypasses the per-conversation cap — the user pays their own
    provider."""
    from app.db.repositories import api_keys as api_keys_repo
    from app.providers.tiers import get_binding
    from tests.test_budget import _session_cookie_for

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=False, name="Upgraded", email="byok-convcap@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await api_keys_repo.upsert(
            session,
            user_id=user.id,
            provider=binding.provider_id,
            raw_api_key="sk-test-byok-convcap-0001",
        )
        await session.commit()
        byok_user_id = user.id

    await _set_per_conversation_budget(
        session_factory, user_id=byok_user_id, cap=0.0000001
    )
    # Seed an over-cap assistant message so the gate WOULD fire if consulted.
    conv_id = await _seed_conversation(session_factory, user_id=byok_user_id)
    await _seed_assistant_message(
        session_factory,
        conversation_id=conv_id,
        cost_usd=1.0,
        attribution=_attribution("DeepSeek V4 Flash"),
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    cookie_name, cookie_value = await _session_cookie_for(session_factory, byok_user_id)
    client.cookies.set(cookie_name, cookie_value)

    frames = await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", _send_body()
    )
    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["attribution"]["isByok"] is True


# Project-scoped per-conversation budget sub-cap (D20) -------------------------


async def test_project_budget_overrides_pref_cap(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A Project's `perConversationBudgetUsd` OVERRIDES the user-pref cap for a
    conversation filed under it (D20): a tiny project sub-cap blocks the next
    turn even though the user pref cap is generous (here, unset)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)

    # Project with a tiny sub-cap; user pref cap stays unset (generous).
    project = await client.post(
        "/api/projects", json={"name": "Capped", "perConversationBudgetUsd": 0.0000001}
    )
    project_id = project.json()["id"]
    created = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False, "projectId": project_id},
    )
    conv_id = created.json()["id"]

    # Turn 1 passes (accumulated cost starts at 0 < sub-cap) and writes a cost
    # over the sub-cap.
    await _collect_sse(client, f"/api/conversations/{conv_id}/messages", _send_body())

    # Turn 2 in the SAME conversation: the project sub-cap refuses it.
    resp = await client.post(
        f"/api/conversations/{conv_id}/messages", json=_send_body()
    )
    assert resp.status_code == 429, resp.text
    assert resp.json()["error"]["code"] == "CONVERSATION_BUDGET_EXCEEDED"

    # A conversation NOT filed under the project is unaffected by the sub-cap
    # (and the user has no pref cap), so it streams freely.
    other_id = await _seed_conversation(session_factory, user_id=user_id)
    frames = await _collect_sse(
        client, f"/api/conversations/{other_id}/messages", _send_body()
    )
    assert frames[-1][0] == "terminal"


async def test_project_budget_overrides_even_a_large_pref_cap(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The project sub-cap wins even when the user pref cap is LARGE: the
    override is "project if set, else pref", not "min of the two"."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)

    # Generous user pref cap that on its own would never block a fake turn.
    await _set_per_conversation_budget(session_factory, user_id=user_id, cap=1000.0)

    project = await client.post(
        "/api/projects", json={"name": "Tight", "perConversationBudgetUsd": 0.0000001}
    )
    project_id = project.json()["id"]
    created = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False, "projectId": project_id},
    )
    conv_id = created.json()["id"]

    await _collect_sse(client, f"/api/conversations/{conv_id}/messages", _send_body())
    resp = await client.post(
        f"/api/conversations/{conv_id}/messages", json=_send_body()
    )
    # The tiny project sub-cap fires despite the huge pref cap.
    assert resp.status_code == 429, resp.text
    assert resp.json()["error"]["code"] == "CONVERSATION_BUDGET_EXCEEDED"


async def test_preferences_round_trip_per_conversation_budget(
    client: AsyncClient,
) -> None:
    """`perConversationBudgetUsd` round-trips through PUT + bootstrap."""
    await client.get("/api/bootstrap")
    body = {
        "defaultTierId": "smart",
        "temporaryByDefault": False,
        "trainingOptIn": False,
        "sendOnEnter": True,
        "autoExpandReasoning": False,
        "telemetryEnabled": True,
        "customInstructions": "",
        "retentionDays": None,
        "monthlyBudgetUsd": None,
        "perConversationBudgetUsd": 2.5,
    }
    put = await client.put("/api/preferences", json=body)
    assert put.status_code == 204

    boot = await client.get("/api/bootstrap")
    prefs = boot.json()["preferences"]
    assert prefs["perConversationBudgetUsd"] == pytest.approx(2.5)

    # Clearing it (null) round-trips too.
    body["perConversationBudgetUsd"] = None
    assert (await client.put("/api/preferences", json=body)).status_code == 204
    boot2 = await client.get("/api/bootstrap")
    assert boot2.json()["preferences"]["perConversationBudgetUsd"] is None
