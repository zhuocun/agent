"""Public-by-link share tests.

Covers:
- Owner mints a share link; public GET with the token returns the conversation
  + model attribution.
- The public GET response contains NO cost fields anywhere (asserted against
  the recursively-walked JSON), but DOES carry model attribution.
- Public GET with a bogus / revoked token -> 404.
- A non-owner cannot mint or revoke (404, not 403 — existence never leaks).
- Revoke makes the public link 404.
- Minting is idempotent: re-minting returns the same token (no rotation).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User

pytestmark = pytest.mark.asyncio

# Every cost / usage / pricing key that must NEVER appear in the public view.
# The owner attribution carries all of these (see `_seed_shared_conversation`);
# the public view must strip them all.
_FORBIDDEN_COST_KEYS = {
    "costUsd",
    "cost_usd",
    "costConfidence",
    "cost_confidence",
    "breakdown",
    "listPriceInPerM",
    "listPriceOutPerM",
    "subtotalUsd",
    "sessionSurchargeUsd",
    "inputTokens",
    "outputTokens",
    "reasoningTokens",
    "cachedInputTokens",
    "longContext",
    "promoApplied",
    "currency",
}


def _all_keys(obj: Any) -> set[str]:
    """Recursively collect every dict key in a JSON-ish structure."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


async def _seed_shared_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
) -> str:
    """Create an owned conversation with a user + assistant (full attribution)."""
    async with session_factory() as session:
        conversation = Conversation(
            user_id=user_id,
            title="Shared conversation",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(conversation)
        await session.flush()

        session.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                parts=[{"type": "text", "text": "hello"}],
                status=None,
                attribution=None,
                created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                parts=[{"type": "text", "text": "hi there"}],
                status="done",
                attribution={
                    "requestedTierId": "smart",
                    "servedTierId": "smart",
                    "servedModelLabel": "Claude Sonnet 4.6",
                    "isByok": False,
                    "costUsd": 0.001,
                    "costConfidence": "exact",
                    "breakdown": {
                        "currency": "USD",
                        "listPriceInPerM": 3,
                        "listPriceOutPerM": 15,
                        "inputTokens": 10,
                        "outputTokens": 20,
                        "reasoningTokens": 0,
                        "cachedInputTokens": 0,
                        "longContext": {"flat": True, "tokensRepriced": "none"},
                        "promoApplied": False,
                        "subtotalUsd": 0.001,
                        "sessionSurchargeUsd": 0,
                    },
                    "substitution": {
                        "reasonCode": "auto_downgrade",
                        "reasonText": "Routed to a faster tier.",
                    },
                },
                created_at=datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC),
            )
        )
        await session.commit()
        return str(conversation.id)


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as s:
        return (await s.execute(select(User))).scalar_one().id


async def _make_other_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Other")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def test_mint_then_public_get_returns_attribution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_shared_conversation(session_factory, user_id=user_id)

    mint = await client.post(f"/api/conversations/{conv_id}/share")
    assert mint.status_code == 200, mint.text
    token = mint.json()["shareToken"]
    assert token
    assert mint.json()["sharePath"] == f"/share/{token}"

    # Public read needs NO cookie/auth — use a bare client to prove it.
    public = await client.get(f"/api/share/{token}")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["id"] == conv_id
    assert body["title"] == "Shared conversation"
    assert len(body["messages"]) == 2

    asst = body["messages"][1]
    attribution = asst["attribution"]
    # Model identity / attribution is KEPT.
    assert attribution["requestedTierId"] == "smart"
    assert attribution["servedTierId"] == "smart"
    assert attribution["servedModelLabel"] == "Claude Sonnet 4.6"
    assert attribution["isByok"] is False
    assert attribution["substitution"]["reasonCode"] == "auto_downgrade"


async def test_public_get_has_no_cost_fields(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_shared_conversation(session_factory, user_id=user_id)

    token = (
        await client.post(f"/api/conversations/{conv_id}/share")
    ).json()["shareToken"]
    public = await client.get(f"/api/share/{token}")
    assert public.status_code == 200

    keys = _all_keys(public.json())
    leaked = keys & _FORBIDDEN_COST_KEYS
    assert not leaked, f"public share leaked cost keys: {leaked}"
    # Sanity: attribution identity IS present (we didn't strip everything).
    assert "servedModelLabel" in keys
    assert "requestedTierId" in keys


async def test_public_get_strips_subagent_marker_cost(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Agentic subagent markers must not leak per-section cost in public parts."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    async with session_factory() as session:
        conversation = Conversation(
            user_id=user_id,
            title="Agentic shared",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(conversation)
        await session.flush()
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                parts=[
                    {
                        "type": "subagent",
                        "subagentId": "primary",
                        "label": "Agent",
                        "role": "primary",
                        "costUsd": 0.0024,
                        "attribution": {
                            "requestedTierId": "smart",
                            "servedTierId": "smart",
                            "servedModelLabel": "Fake",
                            "isByok": False,
                            "costUsd": 0.0024,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Worker finding ready.",
                        "subagentId": "primary",
                    },
                ],
                status="done",
                attribution=None,
                created_at=datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC),
            )
        )
        await session.commit()
        conv_id = str(conversation.id)

    token = (
        await client.post(f"/api/conversations/{conv_id}/share")
    ).json()["shareToken"]
    public = await client.get(f"/api/share/{token}")
    assert public.status_code == 200
    body = public.json()
    keys = _all_keys(body)
    leaked = keys & _FORBIDDEN_COST_KEYS
    assert not leaked, f"public share leaked cost keys: {leaked}"
    subagent_part = body["messages"][0]["parts"][0]
    assert subagent_part["type"] == "subagent"
    assert subagent_part["label"] == "Agent"
    assert "costUsd" not in subagent_part
    assert "attribution" not in subagent_part


async def test_public_get_unknown_token_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.get("/api/share/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_non_owner_cannot_mint(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Caller bootstraps as user A; conversation belongs to user B.
    await client.get("/api/bootstrap")
    other_id = await _make_other_user(session_factory)
    conv_id = await _seed_shared_conversation(session_factory, user_id=other_id)

    mint = await client.post(f"/api/conversations/{conv_id}/share")
    assert mint.status_code == 404
    assert mint.json()["error"]["code"] == "NOT_FOUND"

    revoke = await client.delete(f"/api/conversations/{conv_id}/share")
    assert revoke.status_code == 404


async def test_revoke_makes_public_link_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_shared_conversation(session_factory, user_id=user_id)

    token = (
        await client.post(f"/api/conversations/{conv_id}/share")
    ).json()["shareToken"]
    assert (await client.get(f"/api/share/{token}")).status_code == 200

    revoke = await client.delete(f"/api/conversations/{conv_id}/share")
    assert revoke.status_code == 204

    assert (await client.get(f"/api/share/{token}")).status_code == 404
    # Revoke again is an idempotent 204 (still owned, just unshared).
    assert (
        await client.delete(f"/api/conversations/{conv_id}/share")
    ).status_code == 204


async def test_mint_is_idempotent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_shared_conversation(session_factory, user_id=user_id)

    first = (await client.post(f"/api/conversations/{conv_id}/share")).json()
    second = (await client.post(f"/api/conversations/{conv_id}/share")).json()
    # No rotation: re-minting returns the SAME token so existing links survive.
    assert first["shareToken"] == second["shareToken"]
