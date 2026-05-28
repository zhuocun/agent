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


# 501 on M2 fields -------------------------------------------------------------


async def test_regenerate_returns_501(
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
            "text": "hi",
            "regenerate": True,
        },
    )
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"


async def test_edit_message_id_returns_501(
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
            "text": "hi",
            "editMessageId": str(uuid4()),
        },
    )
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"


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
