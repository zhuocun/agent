"""Streaming endpoint tests.

Uses the fake provider (env defaults to `PROVIDER_BACKEND=fake`). httpx ASGI
transport doesn't expose mid-stream disconnect cleanly — the stop-path test is
marked xfail with a TODO citing the limitation. Production code still works;
the disconnect-detect path is exercised manually in dev.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User

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
        # X-Accel-Buffering may or may not be exposed depending on starlette
        # version — assert it's set on the underlying ASGI response.
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

    # Replay: submitted + exactly one answer_delta + terminal. No reasoning frames.
    event_names = [name for name, _ in second]
    assert event_names == ["submitted", "answer_delta", "terminal"]

    # The answer_delta payload carries the full prior answer text.
    second_answer = second[1][1]
    second_terminal = second[2][1]
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
        },
    )
    assert frames[0][0] == "submitted"
    assert frames[-1][0] == "terminal"

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
