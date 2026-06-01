"""Streaming endpoint tests.

Uses the fake provider (env defaults to `PROVIDER_BACKEND=fake`). httpx ASGI
transport doesn't expose mid-stream disconnect cleanly — the stop-path test is
marked xfail with a TODO citing the limitation. Production code still works;
the disconnect-detect path is exercised manually in dev.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User
from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a captured SSE response body into (event, data-dict) tuples.

    sse-starlette emits frames with `\r\n` line endings; normalize first so we
    can split on the canonical SSE blank-line separator (`\n\n`).
    """
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
                # sse-starlette may emit multiple data: lines per frame; join.
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
    """POST `body` and return the parsed SSE frames."""
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        # Verify required headers.
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        assert resp.headers.get("cache-control") == "no-store"
        # Defeats nginx/CDN buffering (set in routes/conversations.py).
        assert resp.headers.get("x-accel-buffering") == "no"
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> str:
    """Create an owned conversation for the given user, return its id."""
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id=tier_id,
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


# Happy path -------------------------------------------------------------------


async def test_send_message_happy_path_streams_and_persists(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Bootstrap creates the anonymous user.
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "hello world",
        },
    )

    # Event order: submitted -> reasoning_delta* -> reasoning_done -> answer_delta* -> terminal.
    event_names = [name for name, _ in frames]
    assert event_names[0] == "submitted"
    assert "reasoning_done" in event_names
    assert event_names[-1] == "terminal"

    # reasoning_done precedes any answer_delta.
    done_idx = event_names.index("reasoning_done")
    first_answer_idx = event_names.index("answer_delta")
    assert done_idx < first_answer_idx

    # Terminal payload assertions.
    terminal_payload = frames[-1][1]
    assert terminal_payload["status"] == "done"
    assert isinstance(terminal_payload["messageId"], str)
    attribution = terminal_payload["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["costConfidence"] == "exact"
    # The request asked for tier "smart"; the attribution must echo that
    # tier id and a non-empty model label (defended against silent breakage
    # of the tier-binding lookup).
    assert attribution["requestedTierId"] == "smart"
    assert isinstance(attribution.get("servedModelLabel"), str)
    assert attribution["servedModelLabel"] != ""
    breakdown = attribution["breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown["inputTokens"] > 0
    assert breakdown["outputTokens"] > 0
    assert breakdown["subtotalUsd"] > 0
    assert breakdown["longContext"]["flat"] is True
    # `exclude_none=True` strips substitution=None from the wire; M1 has no
    # fallback logic yet (M4), so its absence is the expected shape.
    assert attribution.get("substitution") is None

    # Confirm both messages persisted.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role.in_(["user", "assistant"]))
            )
        ).scalars().all()
        assert len(rows) == 2
        user_msg = next(r for r in rows if r.role == "user")
        asst_msg = next(r for r in rows if r.role == "assistant")
        assert user_msg.parts[0]["text"] == "hello world"
        # Assistant parts should include reasoning + text.
        types = [p["type"] for p in asst_msg.parts]
        assert "reasoning" in types
        assert "text" in types
        assert asst_msg.status == "done"
        assert asst_msg.attribution is not None

    # GET the conversation: both messages come back.
    get_resp = await client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert len(body["messages"]) == 2


async def test_send_message_with_attachment_streams_persists_metadata_only(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )

    event_names = [name for name, _ in frames]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"
    answer = "".join(
        str(payload.get("text", ""))
        for name, payload in frames
        if name == "answer_delta"
    )
    assert "Received attachments: paper.pdf." in answer

    async with session_factory() as session:
        user_msg = (
            await session.execute(select(Message).where(Message.role == "user"))
        ).scalar_one()
        assert user_msg.parts == [
            {"type": "text", "text": "please read this"},
            {
                "type": "attachment",
                "id": "att-1",
                "name": "paper.pdf",
                "mediaType": "pdf",
                "mimeType": "application/pdf",
                "sizeBytes": 5,
            },
        ]


async def test_attachment_idempotent_replay_accepts_metadata_only_retry(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )
    first_terminal = next(payload for name, payload in first if name == "terminal")

    second = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                }
            ],
        },
    )

    assert [name for name, _ in second] == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "answer_delta",
        "terminal",
    ]
    assert second[-1][1]["messageId"] == first_terminal["messageId"]
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert len(rows) == 2


async def test_send_message_with_attachment_rejects_mismatched_payload_size(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 6,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_ATTACHMENT"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


# Idempotency ------------------------------------------------------------------


async def test_idempotent_replay_returns_prior_terminal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())

    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "ping",
        },
    )
    # Pull the terminal data so we can compare.
    first_terminal = next(payload for name, payload in first if name == "terminal")

    second = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "ping",
        },
    )

    # Replay reconstructs persisted reasoning before the final answer.
    event_names = [name for name, _ in second]
    assert event_names == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "answer_delta",
        "terminal",
    ]

    # The answer_delta payload carries the full prior answer text.
    second_answer = next(payload for name, payload in second if name == "answer_delta")
    second_terminal = next(payload for name, payload in second if name == "terminal")
    assert isinstance(second_answer.get("text"), str)
    assert len(second_answer["text"]) > 0
    # Terminal message id matches the persisted assistant message id (replay).
    assert second_terminal["messageId"] == first_terminal["messageId"]

    # No new rows.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role.in_(["user", "assistant"]))
            )
        ).scalars().all()
        assert len(rows) == 2


# Temporary chats --------------------------------------------------------------


async def test_temporary_conversation_streams_but_persists_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # Create a temporary conversation.
    create_resp = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": True},
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["isTemporary"] is True
    synthetic_id = body["id"]

    # GET on a temporary id returns 404.
    get_resp = await client.get(f"/api/conversations/{synthetic_id}")
    assert get_resp.status_code == 404

    # POST messages still works.
    frames = await _collect_sse(
        client,
        f"/api/conversations/{synthetic_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "temp hello",
            "isTemporary": True,
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-temp",
                    "name": "sketch.png",
                    "mediaType": "image",
                    "mimeType": "image/png",
                    "sizeBytes": 5,
                    "dataUrl": "data:image/png;base64,aGVsbG8=",
                }
            ],
        },
    )
    assert frames[0][0] == "submitted"
    assert frames[-1][0] == "terminal"
    answer = "".join(
        str(payload.get("text", ""))
        for name, payload in frames
        if name == "answer_delta"
    )
    assert "Received attachments: sketch.png." in answer

    # Confirm NO conversation or message rows.
    async with session_factory() as session:
        convos = (await session.execute(select(Conversation))).scalars().all()
        msgs = (await session.execute(select(Message))).scalars().all()
        assert convos == []
        assert msgs == []


# Ownership --------------------------------------------------------------------


async def test_send_message_to_other_users_conversation_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # Create a separate user B's conversation.
    async with session_factory() as session:
        other = User(is_anonymous=True, name="Other")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_user_id = other.id

    other_conv_id = await _seed_conversation(session_factory, user_id=other_user_id)

    response = await client.post(
        f"/api/conversations/{other_conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"

    # Ensure no Message rows were created in the other user's conversation.
    # A leak here would mean the ownership check ran AFTER the user-message
    # INSERT, which is a privacy hazard.
    from uuid import UUID

    async with session_factory() as session:
        leaked = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(other_conv_id)
                )
            )
        ).scalars().all()
        assert leaked == []


# Unknown tier -----------------------------------------------------------------


async def test_unknown_tier_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "bogus",
            "text": "hi",
        },
    )
    # 400 from request validation (Pydantic literal mismatch) or our explicit
    # INVALID_TIER envelope — either is acceptable per the spec.
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] in ("INVALID_INPUT", "INVALID_TIER")


# M2: regenerate path ---------------------------------------------------------


async def test_regenerate_drops_trailing_assistant_and_re_streams(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A regen drops the prior assistant, keeps the user message id, re-streams."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1.
    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hello",
        },
    )
    first_submitted = next(p for n, p in first if n == "submitted")
    first_terminal = next(p for n, p in first if n == "terminal")
    user_msg_id_1 = first_submitted["messageId"]
    assistant_msg_id_1 = first_terminal["messageId"]

    # Snapshot DB.
    from uuid import UUID

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        # SQLite same-second timestamps may sort assistant before user when
        # `created_at` ties. Assert role membership, not order.
        assert len(rows) == 2
        roles = {r.role for r in rows}
        assert roles == {"user", "assistant"}

    # Regen (fresh clientMessageId — FE mints one).
    regen = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ignored on regen",  # body.text ignored; original is reused
            "regenerate": True,
        },
    )
    regen_submitted = next(p for n, p in regen if n == "submitted")
    regen_terminal = next(p for n, p in regen if n == "terminal")

    # User message id reused; assistant id is fresh.
    assert regen_submitted["messageId"] == user_msg_id_1
    assert regen_terminal["messageId"] != assistant_msg_id_1
    # Event ordering same as a fresh send.
    event_names = [n for n, _ in regen]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"

    # DB: original assistant gone, new assistant present, user unchanged.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert len(rows) == 2
        user_row = next(r for r in rows if r.role == "user")
        asst_row = next(r for r in rows if r.role == "assistant")
        assert str(user_row.id) == user_msg_id_1
        assert str(asst_row.id) != assistant_msg_id_1
        assert str(asst_row.id) == regen_terminal["messageId"]


async def test_regenerate_with_no_trailing_assistant_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regen on a fresh (no user message) conversation -> 400 INVALID_INPUT."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
            "regenerate": True,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


# M2: edit path ---------------------------------------------------------------


async def test_edit_truncates_and_re_streams(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Edit truncates from the target inclusive, inserts new user, re-streams."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1.
    t1 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "turn 1"},
    )
    t1_user_id = next(p for n, p in t1 if n == "submitted")["messageId"]
    # Turn 2.
    t2 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "turn 2"},
    )
    t2_user_id = next(p for n, p in t2 if n == "submitted")["messageId"]
    # Turn 3.
    t3 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "turn 3"},
    )
    t3_user_id = next(p for n, p in t3 if n == "submitted")["messageId"]
    t3_assistant_id = next(p for n, p in t3 if n == "terminal")["messageId"]

    from uuid import UUID

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert len(rows) == 6  # 3 user + 3 assistant

    # Edit turn-2 user message: truncate it + everything after.
    edit_resp = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "edited turn 2",
            "editMessageId": t2_user_id,
        },
    )
    edit_user_id = next(p for n, p in edit_resp if n == "submitted")["messageId"]
    edit_assistant_id = next(p for n, p in edit_resp if n == "terminal")["messageId"]

    # submitted carries a NEW user message id (not the edited one).
    assert edit_user_id != t2_user_id
    # Event ordering same as a fresh send.
    event_names = [n for n, _ in edit_resp]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"

    # DB shape: turn 1 (user + assistant) preserved; turn 2 user gone; turn 3
    # gone; new user + assistant inserted at the truncation point.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        ids = {str(r.id) for r in rows}
        # Turn 1 preserved.
        assert t1_user_id in ids
        # Old turn-2 user, turn-3 user + assistant all gone.
        assert t2_user_id not in ids
        assert t3_user_id not in ids
        assert t3_assistant_id not in ids
        # New rows present.
        assert edit_user_id in ids
        assert edit_assistant_id in ids
        # Confirm the new user message has the edited text.
        new_user = next(r for r in rows if str(r.id) == edit_user_id)
        assert new_user.parts[0]["text"] == "edited turn 2"


async def test_edit_with_unknown_message_id_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """editMessageId pointing to a uuid not in this conversation -> 400."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
            "editMessageId": str(uuid4()),
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


async def test_edit_with_assistant_message_id_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """editMessageId pointing to an assistant row -> 400."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Build turn 1 to get an assistant message id.
    t1 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hi"},
    )
    assistant_id = next(p for n, p in t1 if n == "terminal")["messageId"]

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "bad edit",
            "editMessageId": assistant_id,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


# M2: title autogen -----------------------------------------------------------


async def test_title_autogen_updates_title_on_first_terminal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """First terminal -> detached task updates conversation.title.

    Timing: the fake provider's `complete()` returns synchronously (no
    sleeps). The detached task runs against a fresh session and should
    finish within a few hundred ms. Poll with a 2s ceiling.
    """
    import asyncio
    from uuid import UUID

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "ping"},
    )

    # Poll until the title flips off "New chat" or we hit the timeout.
    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    final_title: str = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            final_title = row.title
        if final_title and final_title != "New chat":
            break
        await asyncio.sleep(interval)
        elapsed += interval

    assert final_title != "New chat"
    assert final_title.strip() != ""


async def test_title_autogen_does_not_re_fire_on_second_terminal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Second turn must NOT overwrite the title (first-terminal gate)."""
    import asyncio
    from uuid import UUID

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1 fires autogen.
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "first"},
    )
    # Wait for the title to flip.
    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    first_title = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            first_title = row.title
        if first_title and first_title != "New chat":
            break
        await asyncio.sleep(interval)
        elapsed += interval
    assert first_title != "New chat"

    # Manually rename to a sentinel so we can detect any overwrite.
    sentinel = "Manually renamed title"
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        row.title = sentinel
        await session.commit()

    # Turn 2 must NOT overwrite the sentinel.
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "second"},
    )
    # Give any rogue autogen task a chance to overwrite.
    await asyncio.sleep(0.4)
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        assert row.title == sentinel


async def test_regenerate_does_not_re_fire_title_autogen(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regen of the first turn deletes the prior assistant, leaving the
    assistant-count at 0 immediately before the new assistant persists. Without
    the `is_initial` gate, this would re-fire title autogen and clobber a
    user-renamed title. Confirm the gate keeps the user-set title intact.
    """
    import asyncio
    from uuid import UUID

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1 fires autogen; wait for the title to flip off "New chat".
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "first"},
    )
    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    first_title = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            first_title = row.title
        if first_title and first_title != "New chat":
            break
        await asyncio.sleep(interval)
        elapsed += interval
    assert first_title != "New chat"

    # User manually renames the conversation.
    sentinel = "User picked this title"
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        row.title = sentinel
        await session.commit()

    # Regen the (now sole) turn. This drops the trailing assistant, so the
    # assistant-count is 0 before the new assistant persists. The `is_initial`
    # gate must prevent autogen from overwriting the user's title.
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ignored on regen",
            "regenerate": True,
        },
    )
    await asyncio.sleep(0.4)
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        assert row.title == sentinel


# POST /api/conversations creation --------------------------------------------


async def test_post_conversation_creates_persisted_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "New chat"
    assert body["isTemporary"] is False
    assert body["messages"] == []
    assert body["selectedTierId"] == "smart"

    # Persisted in DB.
    async with session_factory() as session:
        rows = (await session.execute(select(Conversation))).scalars().all()
        assert len(rows) == 1


async def test_post_conversation_with_unknown_tier_returns_400(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/conversations",
        json={"selectedTierId": "bogus", "isTemporary": False},
    )
    assert response.status_code == 400


# M4: forced provider fallback ------------------------------------------------


async def test_forced_fallback_emits_substitution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_FALLBACK:` user_text marker → fake provider emits Complete with
    `substitution="provider_fallback"`; the terminal frame's attribution
    carries `substitution.reasonCode="provider_fallback"`.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_FALLBACK: please answer",
        },
    )
    terminal_payload = next(p for n, p in frames if n == "terminal")
    attribution = terminal_payload["attribution"]
    assert isinstance(attribution, dict)
    sub = attribution.get("substitution")
    assert sub is not None, "expected substitution on forced-fallback turn"
    assert isinstance(sub, dict)
    assert sub["reasonCode"] == "provider_fallback"
    # reason_text is canonical-from-builder; assert it's non-empty.
    assert isinstance(sub["reasonText"], str)
    assert len(sub["reasonText"]) > 0
    # Sanity: requested vs served tier ids round-trip unchanged.
    assert attribution["requestedTierId"] == "smart"
    assert attribution["servedTierId"] == "smart"


async def test_happy_path_substitution_is_none(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Without the FORCE_FALLBACK marker, attribution.substitution is absent."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ordinary turn",
        },
    )
    terminal_payload = next(p for n, p in frames if n == "terminal")
    attribution = terminal_payload["attribution"]
    # `exclude_none=True` on the JSON dump means absence on the wire.
    assert attribution.get("substitution") is None


# Stop path --------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "httpx ASGITransport does not expose mid-stream client disconnect. "
        "The stop-path is implemented in handler.py (polling "
        "request.is_disconnected() between yields + cancelling the provider "
        "task) and exercised manually in dev; an integration test would "
        "require a real uvicorn server + abortable HTTP client."
    ),
    strict=False,
)
async def test_stop_path_persists_with_status_stopped(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    _ = await _seed_conversation(session_factory, user_id=user_id)

    # Intentionally fail — see xfail reason above.
    assert False, "stop-path test requires real HTTP transport"


# Deterministic stop path (no real server) -------------------------------------


async def test_stop_path_atomic_persist_and_usage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Drive `stream_and_persist` with a Request stub that reports connected
    for the first poll then disconnected, against the controlled fake
    provider. The now-atomic stop path must:

    - persist the assistant row with status="stopped" and an estimate
      attribution, and
    - increment the usage meter in the SAME commit,
    - WITHOUT emitting a `terminal` frame (socket already closed).

    Complements the route-level xfail above by exercising the disconnect
    branch directly (httpx ASGITransport can't surface mid-stream disconnect).
    """
    from app.db.models import UsageRollup
    from app.providers.fake import FakeProvider
    from app.providers.tiers import get_binding
    from app.streaming.handler import stream_and_persist

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    class _DisconnectAfterFirstPoll:
        """is_disconnected(): connected for the first poll, then disconnected.

        Letting one poll return False allows `submitted` to be yielded and the
        provider to start streaming before the disconnect is detected, so the
        accumulators carry partial parts on the stopped row.
        """

        def __init__(self) -> None:
            self._polls = 0

        async def is_disconnected(self) -> bool:
            self._polls += 1
            return self._polls > 1

    event_names: list[str] = []
    async with session_factory() as session:
        # delay_ms=0 keeps the fake fast; the disconnect fires on poll #2.
        provider = FakeProvider(delay_ms=0)
        gen = stream_and_persist(
            request=_DisconnectAfterFirstPoll(),  # type: ignore[arg-type]
            db=session,
            provider=provider,
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        )
        async for ev in gen:
            event_names.append(ev.event or "")

    # No terminal on disconnect; submitted is allowed (sent before the loop).
    assert "terminal" not in event_names
    assert event_names[0] == "submitted"

    # Assistant row persisted as stopped with an estimate attribution.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalars().all()
        assert len(rows) == 1
        asst = rows[0]
        assert asst.status == "stopped"
        assert asst.attribution is not None
        assert asst.attribution["costConfidence"] == "estimate"

        # Atomic: the usage meter incremented in the same commit.
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        assert rollup.used == 1


# Mid-stream provider error ----------------------------------------------------


async def test_mid_stream_error_emits_error_frame_and_persists_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_ERROR:` makes the fake provider raise mid-stream. The client
    must receive an SSE `error` frame (an ErrorEnvelope) and NO `terminal`,
    and NO assistant row may be persisted/committed for the turn (the
    provider error is not a successful turn).
    """
    from app.streaming.handler import _BG_TASKS

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_ERROR: blow up mid-stream",
        },
    )
    event_names = [name for name, _ in frames]
    # An `error` frame terminates the stream; no `terminal` on failure.
    assert event_names[-1] == "error"
    assert "terminal" not in event_names

    # The error frame is a well-formed ErrorEnvelope.
    error_payload = frames[-1][1]
    assert error_payload["code"] == "PROVIDER_UPSTREAM"
    assert error_payload["severity"] == "error"
    assert isinstance(error_payload["title"], str)
    assert isinstance(error_payload["body"], str)

    # Some answer text streamed before the raise (a couple of deltas).
    assert "answer_delta" in event_names

    # No assistant row persisted; the user row may exist (persisted on submit).
    async with session_factory() as session:
        assistants = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalars().all()
        assert assistants == []

    # No leaked background task: title autogen only fires on a successful
    # terminal, so the error turn must not have scheduled one.
    assert all(t.done() for t in _BG_TASKS)


async def test_mid_stream_rate_limit_surfaces_typed_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_RATE_LIMIT:` makes the fake provider raise a typed
    AppError(RATE_LIMITED) mid-stream. The handler must surface that envelope
    verbatim — code RATE_LIMITED with retryAfterMs — rather than flattening it
    to a generic PROVIDER_UPSTREAM, and persist no assistant row.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_RATE_LIMIT: slow down",
        },
    )
    event_names = [name for name, _ in frames]
    assert event_names[-1] == "error"
    assert "terminal" not in event_names

    error_payload = frames[-1][1]
    assert error_payload["code"] == "RATE_LIMITED"
    assert error_payload["retryAfterMs"] == 4200

    async with session_factory() as session:
        assistants = (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalars().all()
        assert assistants == []


# Web search ------------------------------------------------------------------


async def test_web_search_emits_status_sources_and_persists_parts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`webSearch=true` -> status/sources plus persisted tool transcript parts."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            "webSearch": True,
        },
    )
    event_names = [name for name, _ in frames]
    # Search/tool wire events appear in the right relative order.
    assert "tool_call" in event_names
    assert "tool_result" in event_names
    assert "status" in event_names
    assert "sources" in event_names
    tool_call_idx = event_names.index("tool_call")
    status_idx = event_names.index("status")
    sources_idx = event_names.index("sources")
    tool_result_idx = event_names.index("tool_result")
    first_answer_idx = event_names.index("answer_delta")
    terminal_idx = event_names.index("terminal")
    # LIVE wire order follows the provider emission: tool call -> status ->
    # sources/result -> answer, all before terminal.
    assert tool_call_idx < status_idx
    assert status_idx < sources_idx
    assert sources_idx < tool_result_idx
    assert tool_result_idx < first_answer_idx
    assert sources_idx < first_answer_idx
    assert first_answer_idx < terminal_idx

    tool_call_payload = next(p for n, p in frames if n == "tool_call")
    assert tool_call_payload["name"] == "web_search"
    assert tool_call_payload["status"] == "running"
    assert tool_call_payload["input"]["query"] == "what is rust"

    tool_result_payload = next(p for n, p in frames if n == "tool_result")
    assert tool_result_payload["toolCallId"] == tool_call_payload["id"]
    assert tool_result_payload["status"] == "succeeded"
    assert tool_result_payload["output"]["results"]

    # The `sources` payload carries the deterministic fake citations (ids 1..3).
    sources_payload = next(p for n, p in frames if n == "sources")
    items = sources_payload["items"]
    assert isinstance(items, list)
    assert [it["id"] for it in items] == [1, 2, 3]
    for it in items:
        assert isinstance(it["title"], str)
        assert isinstance(it["url"], str)

    # The `status` payload's final state is `done`.
    status_payloads = [p for n, p in frames if n == "status"]
    assert status_payloads[-1]["state"] == "done"

    # Persisted assistant parts include the durable tool transcript.
    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        part_types = [p["type"] for p in asst.parts]
        assert part_types == [
            "reasoning",
            "tool_call",
            "tool_result",
            "status",
            "text",
            "sources",
        ]
        tool_call_part = next(p for p in asst.parts if p["type"] == "tool_call")
        assert tool_call_part["input"]["query"] == "what is rust"
        tool_result_part = next(p for p in asst.parts if p["type"] == "tool_result")
        assert tool_result_part["toolCallId"] == tool_call_part["id"]
        status_part = next(p for p in asst.parts if p["type"] == "status")
        assert status_part["state"] == "done"
        sources_part = next(p for p in asst.parts if p["type"] == "sources")
        assert [it["id"] for it in sources_part["items"]] == [1, 2, 3]

    # GET round-trips the new parts through the wire schema (validates the union).
    get_resp = await client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    asst_msg = next(m for m in body["messages"] if m["role"] == "assistant")
    wire_types = [p["type"] for p in asst_msg["parts"]]
    assert "status" in wire_types
    assert "sources" in wire_types
    assert "tool_call" in wire_types
    assert "tool_result" in wire_types


async def test_web_search_omitted_is_byte_for_byte_unchanged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`webSearch` omitted/false -> NO status/sources frames or parts (no-op).

    Regression-critical: the non-search turn must be identical to the historical
    stream — no `status`, no `sources`, and the persisted parts stay
    [reasoning] [text].
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            # webSearch intentionally omitted (defaults False).
        },
    )
    event_names = [name for name, _ in frames]
    assert "status" not in event_names
    assert "sources" not in event_names
    assert "tool_call" not in event_names
    assert "tool_result" not in event_names
    # The classic shape is intact.
    assert event_names[0] == "submitted"
    assert "reasoning_done" in event_names
    assert "answer_delta" in event_names
    assert event_names[-1] == "terminal"

    # Persisted parts unchanged: [reasoning] [text], no status/sources/tools.
    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        part_types = [p["type"] for p in asst.parts]
        assert part_types == ["reasoning", "text"]


async def test_web_search_replay_reconstructs_status_and_sources(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An idempotent re-POST of a web-search turn replays the persisted parts
    back into `status` + `sources` frames so a reconnecting client still sees
    the grounded turn's citations."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    body = {
        "clientMessageId": client_msg_id,
        "tierId": "smart",
        "text": "what is rust",
        "webSearch": True,
    }
    await _collect_sse(client, f"/api/conversations/{conv_id}/messages", body)

    # Re-POST the SAME clientMessageId -> idempotent replay from persisted parts.
    replay = await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", body
    )
    replay_names = [name for name, _ in replay]
    # Replay sequence mirrors persisted part ordering:
    # reasoning -> tools -> status -> answer -> sources -> terminal.
    assert replay_names == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "tool_call",
        "tool_result",
        "status",
        "answer_delta",
        "sources",
        "terminal",
    ]
    replay_tool_call = next(p for n, p in replay if n == "tool_call")
    replay_tool_result = next(p for n, p in replay if n == "tool_result")
    assert replay_tool_result["toolCallId"] == replay_tool_call["id"]
    replay_sources = next(p for n, p in replay if n == "sources")
    assert [it["id"] for it in replay_sources["items"]] == [1, 2, 3]
    replay_status = next(p for n, p in replay if n == "status")
    assert replay_status["state"] == "done"


# Auto-tier routing ------------------------------------------------------------


async def test_auto_route_downgrade_surfaces_substitution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`auto` + a short, signal-free prompt routes to `fast` and surfaces the
    `auto_downgrade` substitution honestly (never silent)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "hi",
        },
    )
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    # Requested stays `auto`; served is the routed concrete tier (`fast`).
    assert attribution["requestedTierId"] == "auto"
    assert attribution["servedTierId"] == "fast"
    sub = attribution.get("substitution")
    assert isinstance(sub, dict)
    assert sub["reasonCode"] == "auto_downgrade"


async def test_auto_route_to_baseline_emits_no_substitution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`auto` + a code fence routes to the `smart` baseline -> no substitution
    (routing to the baseline is not a downgrade)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "Review this:\n```python\nprint('x')\n```",
        },
    )
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["requestedTierId"] == "auto"
    assert attribution["servedTierId"] == "smart"
    assert attribution.get("substitution") is None


# Auto-routing x stop / provider-fallback interplay ---------------------------


class _NoSubstitutionThenBlockProvider:
    """Streams a normal turn, then a `Complete` carrying NO substitution.

    Used by the stop-path test. After the terminal `Complete` is yielded (and
    thus enqueued by the handler's pump), the generator sets `done` so the test
    can tell the handler to tear the turn down. The closing `finally` therefore
    runs only after `Complete` is on the queue — guaranteeing the drain path
    sees a `substitution=None` `Complete`, which is exactly the event that must
    NOT clobber the router's `auto_downgrade` seed.
    """

    def __init__(self, done: asyncio.Event) -> None:
        self._done = done

    async def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[object] | None = None,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
        web_search: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        try:
            yield ReasoningDelta(text="thinking")
            yield ReasoningDone()
            yield AnswerDelta(text="partial answer")
            usage = UsageUpdate(
                input_tokens=20,
                output_tokens=5,
                reasoning_tokens=2,
                cached_input_tokens=0,
            )
            yield UsageUpdate(
                input_tokens=20,
                output_tokens=5,
                reasoning_tokens=2,
                cached_input_tokens=0,
            )
            # Terminal Complete with NO provider substitution. On the stop/drain
            # path this is the event that, pre-fix, clobbered the auto_downgrade
            # seed with None.
            yield Complete(usage=usage)
        finally:
            # Runs after `Complete` has been pulled by the pump and enqueued, so
            # signalling `done` here means the queue already holds the Complete
            # the drain branch must fold without clobbering the seed.
            self._done.set()

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        return "title"


async def test_stop_path_preserves_auto_downgrade_seed_in_persisted_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STOP an `auto`→`fast` turn mid-stream; the PERSISTED stopped assistant
    row must still carry `substitution.reasonCode == "auto_downgrade"`.

    Catches the silent-downgrade leak: the disconnect/stop drain folds a
    trailing `Complete(substitution=None)` into the running sub state. Without
    the `_fold_complete_substitution` guard that None overwrites the router's
    `auto_downgrade` seed, and the stopped row — re-served on reload — loses its
    downgrade disclosure. We assert against the durable DB row, not an in-flight
    frame.
    """
    from app.routes import conversations as conv_routes

    provider_done = asyncio.Event()

    monkeypatch.setattr(
        conv_routes,
        "build_provider",
        lambda *a, **k: _NoSubstitutionThenBlockProvider(provider_done),
    )

    # Drive the stop via the handler's `request.is_disconnected()` poll. The
    # first poll BLOCKS until the provider has fully streamed (Complete enqueued
    # + terminal None), then reports disconnected. This makes the handler take
    # the drain path with the un-substituted Complete already in the queue —
    # deterministic, no timing race.
    from starlette.requests import Request

    async def _fake_is_disconnected(self: Request) -> bool:
        await provider_done.wait()
        return True

    monkeypatch.setattr(Request, "is_disconnected", _fake_is_disconnected)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    # `"hi"` is the short, signal-free prompt that routes auto→fast (downgrade),
    # seeding router_substitution="auto_downgrade" before the provider call.
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "hi",
        },
    )
    # Stop/disconnect path emits no terminal frame (socket closed semantics);
    # the proof is the persisted row, asserted below.
    assert all(name != "terminal" for name, _ in frames)

    # Reload the durable stopped assistant row and assert its attribution still
    # discloses the auto downgrade.
    async with session_factory() as session:
        assistant = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        assert assistant.status == "stopped"
        attribution = assistant.attribution
        assert isinstance(attribution, dict)
        assert attribution["requestedTierId"] == "auto"
        assert attribution["servedTierId"] == "fast"
        sub = attribution.get("substitution")
        assert isinstance(sub, dict), "stopped auto→fast row lost its substitution"
        assert sub["reasonCode"] == "auto_downgrade"


async def test_auto_route_provider_fallback_wins_over_downgrade_seed(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`auto`→`fast` (downgrade-seeded) turn whose provider ALSO force-falls-back:
    the provider substitution WINS over the router seed.

    Precedence claim: a real provider `Complete(substitution="provider_fallback")`
    overwrites the router-side `auto_downgrade` seed AND brings the served model
    label with it. The terminal attribution must read `provider_fallback`, not
    `auto_downgrade`, and the served model label must reflect the fallback model.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    # `FORCE_FALLBACK:` flips the fake provider's terminal Complete into the
    # provider_fallback shape; the leading short text still routes auto→fast,
    # so the router seeds `auto_downgrade` first — the provider must override it.
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "FORCE_FALLBACK: hi",
        },
    )
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["requestedTierId"] == "auto"
    # Routed to the concrete fast tier before the provider fallback fired.
    assert attribution["servedTierId"] == "fast"
    sub = attribution.get("substitution")
    assert isinstance(sub, dict)
    # Provider fallback wins precedence over the auto_downgrade seed.
    assert sub["reasonCode"] == "provider_fallback"
    # The served label reflects the provider's substituted model, not the
    # routed tier's default label.
    assert attribution["servedModelLabel"] == "Fallback Model"
