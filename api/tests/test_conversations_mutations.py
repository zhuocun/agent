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

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, UsageRollup, User
from app.db.repositories import conversations as conversations_repo

pytestmark = pytest.mark.asyncio


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a raw SSE body into `(event_name, payload)` tuples."""
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


async def _send_message(
    client: AsyncClient,
    conv_id: str,
    *,
    text: str = "hello",
    client_message_id: str | None = None,
) -> list[tuple[str, dict[str, object]]]:
    """Drive the SSE send endpoint and return the parsed frames."""
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": client_message_id or str(uuid4()),
            "tierId": "smart",
            "text": text,
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


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


async def _seed_branch_source(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
) -> tuple[str, list[str]]:
    async with session_factory() as session:
        conversation = Conversation(
            user_id=user_id,
            title="Branchable chat",
            selected_tier_id="smart",
            pinned=True,
            created_at=datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC),
        )
        session.add(conversation)
        await session.flush()

        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        user_1_id = uuid4()
        assistant_1_id = uuid4()
        user_2_id = uuid4()
        assistant_2_id = uuid4()
        rows = [
            Message(
                id=user_1_id,
                conversation_id=conversation.id,
                client_message_id=uuid4(),
                role="user",
                parts=[{"type": "text", "text": "first prompt"}],
                status=None,
                attribution=None,
                created_at=base,
            ),
            Message(
                id=assistant_1_id,
                conversation_id=conversation.id,
                client_message_id=None,
                role="assistant",
                parts=[{"type": "text", "text": "first answer"}],
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
                cost_usd=0.001,
                responds_to_message_id=user_1_id,
                created_at=base + timedelta(seconds=1),
            ),
            Message(
                id=user_2_id,
                conversation_id=conversation.id,
                client_message_id=uuid4(),
                role="user",
                parts=[{"type": "text", "text": "second prompt"}],
                status=None,
                attribution=None,
                created_at=base + timedelta(seconds=2),
            ),
            Message(
                id=assistant_2_id,
                conversation_id=conversation.id,
                client_message_id=None,
                role="assistant",
                parts=[{"type": "text", "text": "second answer"}],
                status="done",
                attribution={
                    "requestedTierId": "smart",
                    "servedTierId": "smart",
                    "servedModelLabel": "Claude Sonnet 4.6",
                    "isByok": False,
                    "costUsd": 0.002,
                    "costConfidence": "exact",
                    "breakdown": {
                        "currency": "USD",
                        "listPriceInPerM": 3,
                        "listPriceOutPerM": 15,
                        "inputTokens": 11,
                        "outputTokens": 21,
                        "reasoningTokens": 0,
                        "cachedInputTokens": 0,
                        "longContext": {"flat": True, "tokensRepriced": "none"},
                        "promoApplied": False,
                        "subtotalUsd": 0.002,
                        "sessionSurchargeUsd": 0,
                    },
                },
                cost_usd=0.002,
                responds_to_message_id=user_2_id,
                created_at=base + timedelta(seconds=3),
            ),
        ]
        session.add_all(rows)
        session.add(
            UsageRollup(
                user_id=user_id,
                period_start=datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC),
                used=7,
                cost_usd=1.23,
                limit_value=1000,
                is_byok=False,
            )
        )
        await session.commit()
        return str(conversation.id), [str(row.id) for row in rows]


async def _current_user_id(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    """Bootstrap as the current client, then return the only owned user id."""
    await client.get("/api/bootstrap")
    async with session_factory() as s:
        user = (await s.execute(select(User))).scalar_one()
        return user.id


# -- BRANCH -------------------------------------------------------------------


async def test_branch_conversation_copies_messages_through_selected_message(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from uuid import UUID as _UUID

    user_id = await _current_user_id(client, session_factory)
    source_id, message_ids = await _seed_branch_source(
        session_factory, user_id=user_id
    )

    response = await client.post(
        f"/api/conversations/{source_id}/branch",
        json={"messageId": message_ids[2]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != source_id
    assert body["title"] == "Branchable chat"
    assert body["selectedTierId"] == "smart"
    assert body["isTemporary"] is False
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert [m["parts"][0]["text"] for m in body["messages"]] == [
        "first prompt",
        "first answer",
        "second prompt",
    ]
    assert body["messages"][1]["attribution"]["costUsd"] == 0.001

    async with session_factory() as session:
        branch_messages = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == _UUID(body["id"]))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert len(branch_messages) == 3
        assert all(message.cost_usd is None for message in branch_messages)
        assert all(message.client_message_id is None for message in branch_messages)
        assert branch_messages[1].responds_to_message_id == branch_messages[0].id
        assert branch_messages[1].responds_to_message_id != _UUID(message_ids[0])

        source_assistants = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == _UUID(source_id))
                .where(Message.role == "assistant")
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert [message.cost_usd for message in source_assistants] == [0.001, 0.002]

        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        assert rollup.used == 7
        assert rollup.cost_usd == 1.23


async def test_branch_conversation_not_owned_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    other_user_id = await _make_other_user(session_factory)
    source_id, message_ids = await _seed_branch_source(
        session_factory, user_id=other_user_id
    )

    response = await client.post(
        f"/api/conversations/{source_id}/branch",
        json={"messageId": message_ids[0]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_branch_conversation_unknown_message_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    source_id, _ = await _seed_branch_source(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{source_id}/branch",
        json={"messageId": str(uuid4())},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_branch_conversation_invalid_message_id_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    source_id, _ = await _seed_branch_source(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{source_id}/branch",
        json={"messageId": "not-a-uuid"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


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


# -- updated_at bump on a new turn (sidebar ordering) -------------------------


async def _seed_owned_conversation_at(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    title: str,
    updated_at: datetime,
) -> str:
    """Create an owned conversation with an explicit `updated_at`. Returns id."""
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title=title,
            selected_tier_id="smart",
            pinned=False,
            created_at=updated_at,
            updated_at=updated_at,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


async def _conversation_updated_at(
    session_factory: async_sessionmaker[AsyncSession],
    conv_id: str,
) -> datetime:
    from uuid import UUID as _UUID

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == _UUID(conv_id))
            )
        ).scalar_one()
        return row.updated_at


async def test_sending_message_bumps_updated_at_and_reorders_sidebar(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A new turn on the OLDER conversation lifts it to the top of the sidebar.

    Sidebar order is `pinned desc, updated_at desc`. Seed two unpinned convos
    with distinct `updated_at`; the newer one sorts first initially. After a
    send to the older one, it must sort first and its `updated_at` must advance.
    """
    user_id = await _current_user_id(client, session_factory)
    older = await _seed_owned_conversation_at(
        session_factory,
        user_id=user_id,
        title="Older",
        updated_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
    newer = await _seed_owned_conversation_at(
        session_factory,
        user_id=user_id,
        title="Newer",
        updated_at=datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC),
    )

    # Initial order: newer first.
    boot0 = await client.get("/api/bootstrap")
    ids0 = [c["id"] for c in boot0.json()["conversations"]]
    assert ids0.index(newer) < ids0.index(older)

    before = await _conversation_updated_at(session_factory, older)
    frames = await _send_message(client, older, text="bump me")
    assert frames[-1][0] == "terminal"

    # updated_at advanced past the seeded value.
    after = await _conversation_updated_at(session_factory, older)
    assert after > before

    # Sidebar now lists the (formerly) older conversation first.
    boot1 = await client.get("/api/bootstrap")
    ids1 = [c["id"] for c in boot1.json()["conversations"]]
    assert ids1.index(older) < ids1.index(newer)


async def test_idempotent_replay_does_not_rebump_updated_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Replaying the same clientMessageId does not advance `updated_at` again.

    The replay path returns the prior terminal without starting a turn, so it
    must not bump. We assert the timestamp is unchanged across the replay (and
    that the replay itself succeeds without error).
    """
    user_id = await _current_user_id(client, session_factory)
    conv_id = await _seed_owned_conversation_at(
        session_factory,
        user_id=user_id,
        title="Convo",
        updated_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )

    cmid = str(uuid4())
    first = await _send_message(client, conv_id, text="hi", client_message_id=cmid)
    assert first[-1][0] == "terminal"
    after_send = await _conversation_updated_at(session_factory, conv_id)

    # Replay the SAME clientMessageId — reattaches to the prior terminal.
    replay = await _send_message(client, conv_id, text="hi", client_message_id=cmid)
    assert replay[-1][0] == "terminal"
    after_replay = await _conversation_updated_at(session_factory, conv_id)

    # No further bump from the replay.
    assert after_replay == after_send


async def test_idempotent_replay_rejects_same_client_id_with_changed_body(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _current_user_id(client, session_factory)
    conv_id = await _seed_owned_conversation_at(
        session_factory,
        user_id=user_id,
        title="Convo",
        updated_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )

    cmid = str(uuid4())
    first = await _send_message(client, conv_id, text="original", client_message_id=cmid)
    assert first[-1][0] == "terminal"

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": cmid,
            "tierId": "smart",
            "text": "changed",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    async with session_factory() as session:
        user_rows = (
            await session.execute(
                select(Message).where(
                    Message.role == "user",
                    Message.conversation_id == UUID(conv_id),
                )
            )
        ).scalars().all()
        assert len(user_rows) == 1
        user_row = user_rows[0]
        assert user_row.client_message_id == UUID(cmid)
        assert set(user_row.request_fingerprint or {}) == {"v", "sha256"}
        assert "original" not in str(user_row.request_fingerprint)


async def test_touch_updated_at_advances_and_is_noop_when_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Direct repo test for the helper: advances an existing row, no-ops a gone one."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.flush()
        seeded = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        convo = Conversation(
            user_id=user.id,
            title="Convo",
            selected_tier_id="smart",
            pinned=False,
            created_at=seeded,
            updated_at=seeded,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = convo.id

    # Read the seeded value back from the DB so we compare like-for-like
    # (SQLite returns naive datetimes; the tz-aware literal would not compare).
    before = await _conversation_updated_at(session_factory, str(conv_id))

    async with session_factory() as session:
        await conversations_repo.touch_updated_at(session, conv_id)
        await session.commit()

    after = await _conversation_updated_at(session_factory, str(conv_id))
    assert after > before

    # Missing row -> silent no-op (no raise).
    async with session_factory() as session:
        await conversations_repo.touch_updated_at(session, uuid4())
        await session.commit()


# -- replay defends against a null-attribution done row -----------------------


async def test_replay_null_attribution_done_row_does_not_500(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A done assistant row with attribution=NULL must not crash the replay.

    `_maybe_replay` falls through to a fresh insert when attribution is None.
    Because the user message already holds this clientMessageId, the insert
    collides on the unique constraint and resolves to 409 DUPLICATE_IN_FLIGHT
    (re-replay still finds the null-attribution row and falls through), never a
    500. We assert the non-500 outcome — the defensive guard's contract.
    """
    from uuid import UUID as _UUID

    user_id = await _current_user_id(client, session_factory)
    conv_id = await _seed_owned_conversation_at(
        session_factory,
        user_id=user_id,
        title="Convo",
        updated_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
    cmid = uuid4()

    # Seed a user message + a done assistant row whose attribution IS NULL
    # (e.g. a partially-migrated / manually-seeded row).
    async with session_factory() as session:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        session.add(
            Message(
                conversation_id=_UUID(conv_id),
                client_message_id=cmid,
                role="user",
                parts=[{"type": "text", "text": "hi"}],
                status=None,
                attribution=None,
                created_at=base,
            )
        )
        session.add(
            Message(
                conversation_id=_UUID(conv_id),
                client_message_id=None,
                role="assistant",
                parts=[{"type": "text", "text": "answer"}],
                status="done",
                attribution=None,  # the boundary the guard defends.
                created_at=base + timedelta(seconds=1),
            )
        )
        await session.commit()

    # POST with the SAME clientMessageId -> replay path inspects the done row.
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(cmid),
            "tierId": "smart",
            "text": "hi",
        },
        timeout=10.0,
    ) as resp:
        body = await resp.aread()
        # The defensive guard prevents a 500. The collision on the existing
        # clientMessageId resolves to a 409 (not a crash inside model_validate).
        assert resp.status_code != 500, body
        assert resp.status_code == 409, body
        assert json.loads(body)["error"]["code"] == "DUPLICATE_IN_FLIGHT"
