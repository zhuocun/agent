"""Feedback route tests (M2).

Covers:
- POST {"feedback": "up"} -> 204, row written
- POST {"feedback": "down"} -> 204, row written
- POST replace: up -> down updates the existing row
- POST {"feedback": null} -> 204, row cleared
- POST on a message owned by another user -> 404
- POST on a non-existent message -> 404
- Idempotency: posting the same feedback twice in a row is a no-op
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User, Vote

pytestmark = pytest.mark.asyncio


async def _seed_assistant_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
) -> str:
    """Create a conversation for `user_id` with one assistant message.

    Returns the assistant message id (str).
    """
    async with session_factory() as session:
        conversation = Conversation(
            user_id=user_id,
            title="conv",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(conversation)
        await session.flush()
        msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            parts=[{"type": "text", "text": "answer"}],
            status="done",
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return str(msg.id)


async def _make_other_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Other")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _current_user_id(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> object:
    await client.get("/api/bootstrap")
    async with session_factory() as s:
        user = (await s.execute(select(User))).scalar_one()
        return user.id


async def _vote_for(
    session_factory: async_sessionmaker[AsyncSession], message_id: str
) -> Vote | None:
    async with session_factory() as s:
        return (
            await s.execute(select(Vote).where(Vote.message_id == UUID(message_id)))
        ).scalar_one_or_none()


# -- upvote / downvote --------------------------------------------------------


async def test_upvote_writes_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": "up"}
    )
    assert response.status_code == 204
    vote = await _vote_for(session_factory, msg_id)
    assert vote is not None
    assert vote.feedback == "up"


async def test_downvote_writes_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": "down"}
    )
    assert response.status_code == 204
    vote = await _vote_for(session_factory, msg_id)
    assert vote is not None
    assert vote.feedback == "down"


async def test_replace_upvote_with_downvote(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    r1 = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": "up"}
    )
    assert r1.status_code == 204
    r2 = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": "down"}
    )
    assert r2.status_code == 204

    vote = await _vote_for(session_factory, msg_id)
    assert vote is not None
    assert vote.feedback == "down"

    # Still exactly one vote row.
    async with session_factory() as s:
        rows = (
            await s.execute(select(Vote).where(Vote.message_id == UUID(msg_id)))
        ).scalars().all()
        assert len(rows) == 1


async def test_clear_vote(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    await client.post(f"/api/messages/{msg_id}/feedback", json={"feedback": "up"})
    response = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": None}
    )
    assert response.status_code == 204

    vote = await _vote_for(session_factory, msg_id)
    assert vote is None


async def test_clear_vote_when_no_existing_is_noop(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": None}
    )
    assert response.status_code == 204
    vote = await _vote_for(session_factory, msg_id)
    assert vote is None


# -- ownership / not-found ----------------------------------------------------


async def test_feedback_on_others_message_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    other_user_id = await _make_other_user(session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=other_user_id)

    response = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": "up"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_feedback_on_missing_message_returns_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        f"/api/messages/{uuid4()}/feedback", json={"feedback": "up"}
    )
    assert response.status_code == 404


async def test_feedback_idempotent_same_value(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    for _ in range(3):
        response = await client.post(
            f"/api/messages/{msg_id}/feedback", json={"feedback": "up"}
        )
        assert response.status_code == 204

    async with session_factory() as s:
        rows = (
            await s.execute(select(Vote).where(Vote.message_id == UUID(msg_id)))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].feedback == "up"


async def test_feedback_invalid_value_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    msg_id = await _seed_assistant_message(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/messages/{msg_id}/feedback", json={"feedback": "sideways"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
