"""Conversation route tests.

Covers:
- GET an owned conversation returns the full body (camelCase, with messages)
- GET a conversation owned by another user returns 404 (not 403)
- GET a non-existent conversation returns 404
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User
from app.db.repositories import conversations as conversations_repo

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


async def test_create_conversation_rejects_unavailable_provider_before_insert(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _bootstrap_user_id(client, session_factory)

    response = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "providerId": "openai"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    async with session_factory() as session:
        rows = (await session.execute(select(Conversation))).scalars().all()
        assert rows == []


async def test_search_conversations_matches_owned_title(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _bootstrap_user_id(client, session_factory)
    _, conv_id = await _seed_search_conversation(
        session_factory,
        user_id=user_id,
        title="Quarterly planning notes",
        user_text="ordinary setup",
    )

    response = await client.get("/api/conversations/search", params={"q": "quarterly"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body] == [conv_id]
    assert body[0]["title"] == "Quarterly planning notes"
    assert body[0]["matchSnippet"] == "Quarterly planning notes"
    assert body[0]["matchedMessageId"] is None


async def test_search_conversations_matches_message_content(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _bootstrap_user_id(client, session_factory)
    message_id, conv_id = await _seed_search_conversation(
        session_factory,
        user_id=user_id,
        title="Unrelated title",
        user_text="Please compare the billing export edge cases before launch.",
    )

    response = await client.get("/api/conversations/search", params={"q": "billing export"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body] == [conv_id]
    assert "billing export" in body[0]["matchSnippet"]
    assert body[0]["matchedMessageId"] == message_id


async def test_search_conversations_is_scoped_to_owner(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _bootstrap_user_id(client, session_factory)
    other_user_id = await _make_other_user(session_factory)
    await _seed_search_conversation(
        session_factory,
        user_id=other_user_id,
        title="Private roadmap",
        user_text="needle-owned-by-someone-else",
    )

    response = await client.get(
        "/api/conversations/search", params={"q": "needle-owned-by-someone-else"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_search_conversations_returns_compact_message_snippet(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _bootstrap_user_id(client, session_factory)
    _, conv_id = await _seed_search_conversation(
        session_factory,
        user_id=user_id,
        title="Unrelated title",
        user_text=(
            "a" * 90
            + " target phrase with surrounding message content "
            + "z" * 90
        ),
    )

    response = await client.get("/api/conversations/search", params={"q": "target phrase"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body] == [conv_id]
    snippet = body[0]["matchSnippet"]
    assert snippet.startswith("... ")
    assert snippet.endswith(" ...")
    assert "target phrase" in snippet
    assert '"type"' not in snippet


async def test_search_conversations_does_not_match_part_discriminator(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _bootstrap_user_id(client, session_factory)
    await _seed_search_conversation(
        session_factory,
        user_id=user_id,
        title="Unrelated title",
        user_text="ordinary setup",
    )

    response = await client.get("/api/conversations/search", params={"q": "text"})

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_search_conversations_filters_false_positive_candidates_before_limit(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversations_repo, "_SEARCH_PAGE_SIZE", 2)
    user_id = await _bootstrap_user_id(client, session_factory)
    for day in range(6, 1, -1):
        await _seed_search_conversation(
            session_factory,
            user_id=user_id,
            title=f"False positive {day}",
            user_text="ordinary setup",
            updated_at=datetime(2026, 1, day, 12, 0, 0, tzinfo=UTC),
        )
    _, real_conv_id = await _seed_search_conversation(
        session_factory,
        user_id=user_id,
        title="Older real match",
        user_text="The text appears in actual message content.",
        updated_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )

    response = await client.get(
        "/api/conversations/search", params={"q": "text", "limit": 1}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body] == [real_conv_id]
    assert body[0]["matchSnippet"] == "The text appears in actual message content."


async def _bootstrap_user_id(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    bootstrap = await client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    async with session_factory() as session:
        return (await session.execute(select(User.id))).scalar_one()


async def _seed_search_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    title: str,
    user_text: str,
    updated_at: datetime | None = None,
    parts: list[dict[str, object]] | None = None,
) -> tuple[str, str]:
    async with session_factory() as session:
        conversation = Conversation(
            user_id=user_id,
            title=title,
            selected_tier_id="smart",
            pinned=False,
        )
        if updated_at is not None:
            conversation.updated_at = updated_at
        session.add(conversation)
        await session.flush()

        message = Message(
            conversation_id=conversation.id,
            role="user",
            parts=parts if parts is not None else [{"type": "text", "text": user_text}],
            status=None,
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        session.add(message)
        await session.commit()
        return str(message.id), str(conversation.id)


async def _make_other_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Other")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id
