"""Direct unit tests for the message-tree helpers in messages_repo.

These helpers (`truncate_from`, `delete_trailing_assistants`,
`get_last_user_message`, `count_assistant_messages`) carry the boundary logic
that drives edit / regenerate / title-autogen. They are exercised indirectly
via the streaming routes, but the boundary behavior is subtle enough to test in
isolation here. Each test seeds messages with CONTROLLED `created_at` values so
ordering is deterministic (no reliance on insert wall-clock).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User
from app.db.repositories import messages as messages_repo

pytestmark = pytest.mark.asyncio

_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _seed_user_and_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    """Create an anonymous user + an owned conversation. Returns conversation id."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.flush()
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return convo.id


async def _add_message(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    role: str,
    text: str,
    offset_seconds: int,
) -> Message:
    """Insert a message with an explicit `created_at = _BASE + offset_seconds`."""
    msg = Message(
        conversation_id=conversation_id,
        client_message_id=None,
        role=role,
        parts=[{"type": "text", "text": text}],
        status="done" if role == "assistant" else None,
        attribution=None,
        created_at=_BASE + timedelta(seconds=offset_seconds),
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg


async def _all_message_ids(
    session_factory: async_sessionmaker[AsyncSession],
    conversation_id: UUID,
) -> list[UUID]:
    async with session_factory() as session:
        stmt = (
            select(Message.id)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return list((await session.execute(stmt)).scalars().all())


# -- truncate_from ------------------------------------------------------------


async def test_truncate_from_deletes_anchor_and_everything_after(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The anchor row AND every later row are deleted; earlier rows survive."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        # u0 a0 u1(anchor) a1 u2 -- distinct, increasing timestamps.
        u0 = await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        a0 = await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        anchor = await _add_message(
            session, conversation_id=conv_id, role="user", text="u1", offset_seconds=2
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a1",
            offset_seconds=3,
        )
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u2", offset_seconds=4
        )
        await session.commit()
        anchor_id = anchor.id
        u0_id, a0_id = u0.id, a0.id

    async with session_factory() as session:
        removed = await messages_repo.truncate_from(
            session, conversation_id=conv_id, message_id=anchor_id
        )
        await session.commit()
        # anchor (u1) + a1 + u2 -> 3 rows removed.
        assert removed == 3

    remaining = await _all_message_ids(session_factory, conv_id)
    # Only the two rows strictly before the anchor survive.
    assert remaining == [u0_id, a0_id]


async def test_truncate_from_unknown_message_is_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An id not in the conversation deletes nothing and returns 0."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        await session.commit()

    async with session_factory() as session:
        removed = await messages_repo.truncate_from(
            session,
            conversation_id=conv_id,
            message_id=UUID("00000000-0000-0000-0000-000000000000"),
        )
        await session.commit()
        assert removed == 0

    assert len(await _all_message_ids(session_factory, conv_id)) == 1


async def test_truncate_from_anchor_is_first_message_deletes_all(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Anchoring on the very first message wipes the whole transcript."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        first = await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        await session.commit()
        first_id = first.id

    async with session_factory() as session:
        removed = await messages_repo.truncate_from(
            session, conversation_id=conv_id, message_id=first_id
        )
        await session.commit()
        assert removed == 2

    assert await _all_message_ids(session_factory, conv_id) == []


# -- delete_trailing_assistants -----------------------------------------------


async def test_delete_trailing_assistants_alternating_transcript(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Assistants at/after the last user message go; earlier ones survive."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        # u0 a0 u1 a1 -- the last user is u1, so only a1 is trailing.
        u0 = await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        a0 = await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        u1 = await _add_message(
            session, conversation_id=conv_id, role="user", text="u1", offset_seconds=2
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a1",
            offset_seconds=3,
        )
        await session.commit()
        u0_id, a0_id, u1_id = u0.id, a0.id, u1.id

    async with session_factory() as session:
        removed = await messages_repo.delete_trailing_assistants(
            session, conversation_id=conv_id
        )
        await session.commit()
        # Only a1 (after the last user u1) is removed.
        assert removed == 1

    remaining = await _all_message_ids(session_factory, conv_id)
    # The earlier turn's assistant (a0) survives, plus both user messages.
    assert remaining == [u0_id, a0_id, u1_id]


async def test_delete_trailing_assistants_multiple_after_last_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """All assistants after the last user are dropped (not just one)."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        u0 = await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a1",
            offset_seconds=2,
        )
        await session.commit()
        u0_id = u0.id

    async with session_factory() as session:
        removed = await messages_repo.delete_trailing_assistants(
            session, conversation_id=conv_id
        )
        await session.commit()
        assert removed == 2

    assert await _all_message_ids(session_factory, conv_id) == [u0_id]


async def test_delete_trailing_assistants_no_user_is_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No user message -> nothing to anchor on -> 0 removed, rows untouched."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="orphan",
            offset_seconds=0,
        )
        await session.commit()

    async with session_factory() as session:
        removed = await messages_repo.delete_trailing_assistants(
            session, conversation_id=conv_id
        )
        await session.commit()
        assert removed == 0

    assert len(await _all_message_ids(session_factory, conv_id)) == 1


async def test_delete_trailing_assistants_last_message_is_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """If the last message is already a user message, nothing is removed."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u1", offset_seconds=2
        )
        await session.commit()

    async with session_factory() as session:
        removed = await messages_repo.delete_trailing_assistants(
            session, conversation_id=conv_id
        )
        await session.commit()
        assert removed == 0

    assert len(await _all_message_ids(session_factory, conv_id)) == 3


# -- get_last_user_message ----------------------------------------------------


async def test_get_last_user_message_returns_most_recent_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session, conversation_id=conv_id, role="user", text="first", offset_seconds=0
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        last_user = await _add_message(
            session, conversation_id=conv_id, role="user", text="latest", offset_seconds=2
        )
        # An assistant lands AFTER the last user -- must not be returned.
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a1",
            offset_seconds=3,
        )
        await session.commit()
        last_user_id = last_user.id

    async with session_factory() as session:
        row = await messages_repo.get_last_user_message(session, conv_id)
        assert row is not None
        assert row.id == last_user_id
        parts: list[dict[str, Any]] = row.parts  # type: ignore[assignment]
        assert parts[0]["text"] == "latest"


async def test_get_last_user_message_none_when_no_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=0,
        )
        await session.commit()

    async with session_factory() as session:
        row = await messages_repo.get_last_user_message(session, conv_id)
        assert row is None


# -- count_assistant_messages -------------------------------------------------


async def test_count_assistant_messages_zero_when_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        await session.commit()

    async with session_factory() as session:
        assert await messages_repo.count_assistant_messages(session, conv_id) == 0


async def test_count_assistant_messages_counts_only_assistants(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u0", offset_seconds=0
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a0",
            offset_seconds=1,
        )
        await _add_message(
            session, conversation_id=conv_id, role="user", text="u1", offset_seconds=2
        )
        await _add_message(
            session,
            conversation_id=conv_id,
            role="assistant",
            text="a1",
            offset_seconds=3,
        )
        await session.commit()

    async with session_factory() as session:
        assert await messages_repo.count_assistant_messages(session, conv_id) == 2
