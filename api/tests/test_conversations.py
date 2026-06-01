"""Conversation route tests.

Covers:
- GET an owned conversation returns the full body (camelCase, with messages)
- GET a conversation owned by another user returns 404 (not 403)
- GET a non-existent conversation returns 404
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User

pytestmark = pytest.mark.asyncio


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object | None = None,
) -> tuple[str, str]:
    """Create a user (if no user_id given) + an owned conversation with two messages.

    Returns (user_id_str, conversation_id_str).
    """
    async with session_factory() as session:
        if user_id is None:
            user = User(is_anonymous=True, name="Guest")
            session.add(user)
            await session.flush()
            user_id = user.id

        conversation = Conversation(
            user_id=user_id,
            title="Test conversation",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(conversation)
        await session.flush()

        # User message.
        m_user = Message(
            conversation_id=conversation.id,
            role="user",
            parts=[
                {"type": "text", "text": "hello"},
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "diagram.png",
                    "mediaType": "image",
                    "mimeType": "image/png",
                    "sizeBytes": 1234,
                },
            ],
            status=None,
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        session.add(m_user)
        # Assistant message with a complete attribution.
        m_asst = Message(
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
            },
            created_at=datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC),
        )
        session.add(m_asst)
        await session.commit()
        return str(user_id), str(conversation.id)


async def test_get_owned_conversation_returns_body(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # First hit creates the anonymous user.
    bootstrap = await client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    # Find the user that was just created.
    async with session_factory() as s:
        from sqlalchemy import select

        user = (await s.execute(select(User))).scalar_one()

    _, conv_id = await _seed_conversation(session_factory, user_id=user.id)

    response = await client.get(f"/api/conversations/{conv_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == conv_id
    assert body["title"] == "Test conversation"
    assert body["selectedTierId"] == "smart"
    assert body["isTemporary"] is False
    assert isinstance(body["messages"], list)
    assert len(body["messages"]) == 2

    user_msg, asst_msg = body["messages"]
    assert user_msg["role"] == "user"
    assert user_msg["parts"][0]["type"] == "text"
    assert user_msg["parts"][1] == {
        "type": "attachment",
        "id": "att-1",
        "name": "diagram.png",
        "mediaType": "image",
        "mimeType": "image/png",
        "sizeBytes": 1234,
    }
    assert asst_msg["role"] == "assistant"
    assert asst_msg["status"] == "done"
    # camelCase nested objects round-trip from the JSON column unchanged.
    attribution = asst_msg["attribution"]
    assert attribution["requestedTierId"] == "smart"
    assert attribution["breakdown"]["listPriceInPerM"] == 3
    assert attribution["breakdown"]["longContext"]["flat"] is True


async def test_get_others_conversation_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Bootstrap as user A.
    await client.get("/api/bootstrap")
    # Create a separate user B with their own conversation.
    other_user_id = await _make_other_user(session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=other_user_id)

    response = await client.get(f"/api/conversations/{conv_id}")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"


async def test_get_nonexistent_conversation_returns_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.get(f"/api/conversations/{uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"


async def test_get_invalid_uuid_returns_400(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.get("/api/conversations/not-a-uuid")
    # FastAPI path parsing -> RequestValidationError -> 400 envelope.
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


async def _make_other_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Other")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id
