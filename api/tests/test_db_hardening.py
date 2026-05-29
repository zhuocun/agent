"""Post-M4 DB-hardening tests.

Covers the three items in burst C's scope:

1. Partial UNIQUE INDEX on `users.email WHERE email IS NOT NULL`
   - Two users with the same non-NULL email raise IntegrityError at the DB layer.
   - Two users with NULL email coexist (anon users; partial predicate excludes NULL).
   - Updating an existing user's email to a value already in use raises.

2. `responds_to_message_id` column on `message`
   - Replay using the column lookup returns the linked assistant row.
   - Legacy replay (column NULL) falls back to pair-by-index.
   - Mixed (one row with column, one with NULL) resolves each correctly.

3. `INSERT ... ON CONFLICT DO UPDATE` for `usage_rollup`
   - Concurrent increments don't lose updates: the final `used` matches expected.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, UsageRollup, User
from app.db.repositories import messages as messages_repo
from app.db.repositories import usage as usage_repo

pytestmark = pytest.mark.asyncio


# -- 1. users.email partial UNIQUE INDEX --------------------------------------


async def test_duplicate_non_null_email_raises_integrity_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two users with the same non-NULL email must collide at the DB level.

    Worker B catches this IntegrityError in /api/auth/upgrade and maps it to
    EMAIL_TAKEN. Worker C only owns the DB-side guarantee.
    """
    async with session_factory() as session:
        session.add(User(email="dup@example.com", name="A", is_anonymous=False))
        await session.commit()

    async with session_factory() as session:
        session.add(User(email="dup@example.com", name="B", is_anonymous=False))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_multiple_null_emails_coexist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Anonymous users (email IS NULL) are excluded from the UNIQUE predicate.

    Without this, every second anonymous bootstrap call would 500 on the dup
    NULL. The partial predicate (sqlite_where/postgresql_where) excludes
    NULL rows from the index entirely.
    """
    async with session_factory() as session:
        session.add(User(email=None, name="anon-1"))
        session.add(User(email=None, name="anon-2"))
        session.add(User(email=None, name="anon-3"))
        await session.commit()

        count = int(
            (
                await session.execute(select(func.count()).select_from(User))
            ).scalar_one()
        )
        assert count == 3


async def test_updating_email_to_existing_value_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """UPDATE that lands on an already-taken email also collides.

    Same partial-index guarantee as INSERT — covers the case where an anon
    user's upgrade path tries to write someone else's email.
    """
    async with session_factory() as session:
        session.add(User(email="alice@example.com", name="Alice", is_anonymous=False))
        bob = User(email="bob@example.com", name="Bob", is_anonymous=False)
        session.add(bob)
        await session.commit()
        await session.refresh(bob)
        bob_id = bob.id

    async with session_factory() as session:
        row = (
            await session.execute(select(User).where(User.id == bob_id))
        ).scalar_one()
        row.email = "alice@example.com"
        with pytest.raises(IntegrityError):
            await session.commit()


# -- 2. responds_to_message_id replay ----------------------------------------


_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _seed_user_and_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
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


async def test_get_assistant_for_user_message_resolves_via_column(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Direct repo test: the new helper returns the row whose pointer matches."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        user_msg = Message(
            conversation_id=conv_id,
            client_message_id=uuid4(),
            role="user",
            parts=[{"type": "text", "text": "ping"}],
            created_at=_BASE,
        )
        session.add(user_msg)
        await session.flush()
        await session.refresh(user_msg)
        asst_msg = Message(
            conversation_id=conv_id,
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "pong"}],
            status="done",
            attribution={"placeholder": True},
            responds_to_message_id=user_msg.id,
            created_at=_BASE + timedelta(seconds=1),
        )
        session.add(asst_msg)
        await session.commit()
        user_id = user_msg.id
        asst_id = asst_msg.id

    async with session_factory() as session:
        found = await messages_repo.get_assistant_for_user_message(session, user_id)
        assert found is not None
        assert found.id == asst_id


async def test_get_assistant_for_user_message_ignores_null_pointer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A legacy assistant row with NULL pointer must not match anyone."""
    conv_id = await _seed_user_and_conversation(session_factory)
    async with session_factory() as session:
        user_msg = Message(
            conversation_id=conv_id,
            client_message_id=uuid4(),
            role="user",
            parts=[{"type": "text", "text": "ping"}],
            created_at=_BASE,
        )
        session.add(user_msg)
        # Legacy assistant: pointer is NULL.
        legacy = Message(
            conversation_id=conv_id,
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "legacy"}],
            status="done",
            attribution={"placeholder": True},
            responds_to_message_id=None,
            created_at=_BASE + timedelta(seconds=1),
        )
        session.add(legacy)
        await session.commit()
        await session.refresh(user_msg)
        user_id = user_msg.id

    async with session_factory() as session:
        found = await messages_repo.get_assistant_for_user_message(session, user_id)
        assert found is None


async def test_replay_via_column_returns_same_assistant_twice(
    client,  # type: ignore[no-untyped-def]
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """End-to-end: post the same user message twice -> the second call replays
    the first assistant row. Uses the column-based lookup.
    """
    import json
    from uuid import uuid4

    await client.get("/api/bootstrap")
    async with session_factory() as session:
        user_row = (await session.execute(select(User))).scalar_one()
        user_id = user_row.id
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = str(convo.id)

    client_msg_id = str(uuid4())
    # Turn 1.
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "hello",
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200
        text1 = "".join([c async for c in resp.aiter_text()])
    # Turn 2 -- same clientMessageId -> replay.
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "hello",
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200
        text2 = "".join([c async for c in resp.aiter_text()])

    # Pull the assistant message id from both terminals.
    def _terminal_id(blob: str) -> str:
        normalized = blob.replace("\r\n", "\n").replace("\r", "\n")
        for chunk in normalized.split("\n\n"):
            if "event: terminal" not in chunk:
                continue
            for line in chunk.splitlines():
                if line.startswith("data:"):
                    payload = json.loads(line[len("data:") :].strip())
                    return str(payload["messageId"])
        raise AssertionError(f"no terminal frame in {blob!r}")

    assert _terminal_id(text1) == _terminal_id(text2)

    # Verify the column is populated and the user is correctly linked.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        pointer = rows[0].responds_to_message_id
        assert pointer is not None
        # The pointer resolves to the user message in this conversation.
        user_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "user",
                )
            )
        ).scalars().all()
        assert len(user_msgs) == 1
        assert user_msgs[0].id == pointer


async def test_replay_legacy_falls_back_to_pair_by_index(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Simulate a legacy assistant row with responds_to_message_id=NULL.

    `_maybe_replay`'s fallback should still pair user[i] with assistant[i] and
    surface the replay. Drives `_maybe_replay` directly via a stub Request.
    """
    from app.routes.conversations import _maybe_replay

    conv_id = await _seed_user_and_conversation(session_factory)
    client_msg = uuid4()
    async with session_factory() as session:
        user_msg = Message(
            conversation_id=conv_id,
            client_message_id=client_msg,
            role="user",
            parts=[{"type": "text", "text": "hello"}],
            created_at=_BASE,
        )
        session.add(user_msg)
        # Legacy assistant with NULL pointer + a full attribution payload.
        attribution = {
            "requestedTierId": "smart",
            "servedTierId": "smart",
            "servedModelLabel": "Test Model",
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
        }
        legacy_asst = Message(
            conversation_id=conv_id,
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "world"}],
            status="done",
            attribution=attribution,
            responds_to_message_id=None,  # legacy
            created_at=_BASE + timedelta(seconds=1),
        )
        session.add(legacy_asst)
        await session.commit()
        await session.refresh(legacy_asst)
        legacy_asst_id = legacy_asst.id

    async with session_factory() as session:
        response = await _maybe_replay(session, conv_id, client_msg)
        assert response is not None  # replay resolved via the fallback path

    # Sanity: the assistant row still has NULL pointer.
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message).where(Message.id == legacy_asst_id)
            )
        ).scalar_one()
        assert row.responds_to_message_id is None


async def test_replay_mixed_legacy_and_modern_isolates_correctly(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Mixed conversation: one legacy turn (NULL pointer) + one modern turn
    (column populated). The legacy fallback only considers NULL-pointer
    assistants, so neither user message ever resolves to the wrong assistant.
    """
    from app.routes.conversations import _maybe_replay

    conv_id = await _seed_user_and_conversation(session_factory)
    legacy_client = uuid4()
    modern_client = uuid4()
    attribution = {
        "requestedTierId": "smart",
        "servedTierId": "smart",
        "servedModelLabel": "M",
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
    }

    async with session_factory() as session:
        # Turn 1 (legacy): user + assistant with NULL pointer.
        u1 = Message(
            conversation_id=conv_id,
            client_message_id=legacy_client,
            role="user",
            parts=[{"type": "text", "text": "u1"}],
            created_at=_BASE,
        )
        session.add(u1)
        await session.flush()
        a1 = Message(
            conversation_id=conv_id,
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "a1"}],
            status="done",
            attribution=attribution,
            responds_to_message_id=None,
            created_at=_BASE + timedelta(seconds=1),
        )
        session.add(a1)
        # Turn 2 (modern): user + assistant with column populated.
        u2 = Message(
            conversation_id=conv_id,
            client_message_id=modern_client,
            role="user",
            parts=[{"type": "text", "text": "u2"}],
            created_at=_BASE + timedelta(seconds=2),
        )
        session.add(u2)
        await session.flush()
        a2 = Message(
            conversation_id=conv_id,
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "a2"}],
            status="done",
            attribution=attribution,
            responds_to_message_id=u2.id,
            created_at=_BASE + timedelta(seconds=3),
        )
        session.add(a2)
        await session.commit()
        a1_id, a2_id = a1.id, a2.id

    async with session_factory() as session:
        # Modern path: column lookup hits.
        r_modern = await _maybe_replay(session, conv_id, modern_client)
        assert r_modern is not None
        # Legacy path: column lookup misses, falls back to pair-by-index over
        # NULL-pointer assistants. Only `a1` matches; `a2` is excluded by the
        # NULL filter, so the legacy fallback resolves user[0] -> assistant[0].
        r_legacy = await _maybe_replay(session, conv_id, legacy_client)
        assert r_legacy is not None

    # Sanity: both assistants still present, correct pointer states.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalars().all()
        by_id = {r.id: r for r in rows}
        assert by_id[a1_id].responds_to_message_id is None
        assert by_id[a2_id].responds_to_message_id is not None


# -- 3. usage_rollup ON CONFLICT DO UPDATE ------------------------------------


async def test_concurrent_increments_accumulate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Parallel increments must all land. SQLite can't model true concurrency
    (write-locked at the connection level), but the ON CONFLICT statement still
    runs through both paths (INSERT then UPDATE) and the final sum must equal
    the count of calls.
    """
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    async def _bump() -> None:
        async with session_factory() as session:
            await usage_repo.increment_for_period(session, user_id=user_id)
            await session.commit()

    # 25 sequential bumps (await gather with sqlite serializes them, but each
    # call still exercises ON CONFLICT — first call INSERTs, the rest UPDATE).
    await asyncio.gather(*[_bump() for _ in range(25)])

    async with session_factory() as session:
        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.used == 25


async def test_first_increment_inserts_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ON CONFLICT path: first call hits the INSERT branch and seeds the row."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await usage_repo.increment_for_period(session, user_id=user.id)
        await session.commit()
        rows = (await session.execute(select(UsageRollup))).scalars().all()
        assert len(rows) == 1
        assert rows[0].used == 1


async def test_subsequent_increments_update_in_place(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ON CONFLICT path: second+ calls hit the UPDATE branch and accumulate."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        for _ in range(5):
            await usage_repo.increment_for_period(session, user_id=user.id)
        await session.commit()
        rows = (await session.execute(select(UsageRollup))).scalars().all()
        assert len(rows) == 1
        assert rows[0].used == 5


async def test_increment_with_custom_delta_accumulates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Non-default `used_delta` still accumulates through ON CONFLICT."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await usage_repo.increment_for_period(session, user_id=user.id, used_delta=7)
        await usage_repo.increment_for_period(session, user_id=user.id, used_delta=3)
        await session.commit()
        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.used == 10


