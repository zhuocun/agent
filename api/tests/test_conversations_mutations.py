"""Conversation mutation tests (M2).

Covers:
- PATCH rename (title only)
- PATCH pin/unpin (pinned only)
- PATCH both fields at once
- PATCH with empty body -> 400 INVALID_INPUT
- PATCH not-owned -> 404
- DELETE owned -> 204, row gone (cascade ok)
- DELETE not-owned -> 204 (idempotent — see route docstring)
- DELETE twice on the same id -> 204 both times (idempotency)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User

pytestmark = pytest.mark.asyncio


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object | None = None,
    title: str = "Original title",
    pinned: bool = False,
) -> tuple[str, str]:
    """Create a user (if no user_id given) + an owned conversation with one message.

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
            title=title,
            selected_tier_id="smart",
            pinned=pinned,
        )
        session.add(conversation)
        await session.flush()

        m_user = Message(
            conversation_id=conversation.id,
            role="user",
            parts=[{"type": "text", "text": "hello"}],
            status=None,
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        session.add(m_user)
        await session.commit()
        return str(user_id), str(conversation.id)


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
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    """Bootstrap as the current client, then return the only owned user id."""
    await client.get("/api/bootstrap")
    async with session_factory() as s:
        user = (await s.execute(select(User))).scalar_one()
        return user.id


# -- PATCH --------------------------------------------------------------------


async def test_patch_renames_conversation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.patch(
        f"/api/conversations/{conv_id}", json={"title": "Renamed"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == conv_id
    assert body["title"] == "Renamed"
    # The full body is returned so the FE avoids a refetch.
    assert isinstance(body["messages"], list)
    assert body["selectedTierId"] == "smart"


async def test_patch_pins_conversation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.patch(
        f"/api/conversations/{conv_id}", json={"pinned": True}
    )
    assert response.status_code == 200
    # Sidebar listing should reflect the pin on next bootstrap.
    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    summaries = boot.json()["conversations"]
    pinned_entry = next(c for c in summaries if c["id"] == conv_id)
    assert pinned_entry["pinned"] is True


async def test_patch_both_fields(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "Both changed", "pinned": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Both changed"


async def test_patch_empty_body_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.patch(f"/api/conversations/{conv_id}", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_patch_not_owned_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    other_user_id = await _make_other_user(session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=other_user_id)

    response = await client.patch(
        f"/api/conversations/{conv_id}", json={"title": "Hacked"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_patch_missing_returns_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.patch(
        f"/api/conversations/{uuid4()}", json={"title": "Nope"}
    )
    assert response.status_code == 404


# -- DELETE -------------------------------------------------------------------


async def test_delete_owned_removes_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.delete(f"/api/conversations/{conv_id}")
    assert response.status_code == 204
    # GET now 404s.
    follow_up = await client.get(f"/api/conversations/{conv_id}")
    assert follow_up.status_code == 404
    # Messages cascaded away.
    async with session_factory() as s:
        from uuid import UUID as _UUID

        msgs = (
            await s.execute(
                select(Message).where(Message.conversation_id == _UUID(conv_id))
            )
        ).scalars().all()
        assert msgs == []


async def test_delete_not_owned_returns_204_idempotent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Per the route's idempotency policy, DELETE on a not-owned id returns 204
    (not 404). The row stays put — ownership keeps it safe."""
    await client.get("/api/bootstrap")
    other_user_id = await _make_other_user(session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=other_user_id)

    response = await client.delete(f"/api/conversations/{conv_id}")
    assert response.status_code == 204
    # Owner's row is intact.
    async with session_factory() as s:
        from uuid import UUID as _UUID

        row = (
            await s.execute(select(Conversation).where(Conversation.id == _UUID(conv_id)))
        ).scalar_one()
        assert row.title == "Original title"


async def test_delete_idempotent_twice(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    _, conv_id = await _seed_conversation(session_factory, user_id=user_id)

    first = await client.delete(f"/api/conversations/{conv_id}")
    assert first.status_code == 204
    second = await client.delete(f"/api/conversations/{conv_id}")
    # Same id, already gone — still 204 (per the idempotency choice).
    assert second.status_code == 204


async def test_delete_missing_returns_204(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.delete(f"/api/conversations/{uuid4()}")
    assert response.status_code == 204
