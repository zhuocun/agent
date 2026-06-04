"""Backend tool-calling + human-in-the-loop (HITL) approval tests.

Drives the FAKE provider behind `TOOLS_ENABLED=true` (a per-test env fixture that
rebuilds the app so `get_settings()` picks up the flag). Covers the auto tool
path, the approval pause terminal, resume→approve / resume→deny, the
gate-is-the-trust-boundary invariant, the loop/timeout guards, and the flag-off
no-op invariant.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, Stream, User
from app.db.repositories import streams as streams_repo
from app.db.session import get_db

pytestmark = pytest.mark.asyncio


# Fixtures ---------------------------------------------------------------------


@pytest.fixture
def tools_env() -> Iterator[None]:
    """Turn the tool-calling flag ON for the duration of the test."""
    prior = os.environ.get("TOOLS_ENABLED")
    os.environ["TOOLS_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("TOOLS_ENABLED", None)
        else:
            os.environ["TOOLS_ENABLED"] = prior
        get_settings.cache_clear()


@pytest.fixture
def tools_app(
    tools_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from fastapi import FastAPI

    from app.main import create_app
    from app.middleware.ratelimit import limiter
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    _TEMP_IDS.clear()
    stop_registry._STOP_REQUESTS.clear()
    replay_registry._BUFFERS.clear()
    storage = limiter._storage
    if hasattr(storage, "storage"):
        storage.storage.clear()
    if hasattr(storage, "expirations"):
        storage.expirations.clear()

    app_: FastAPI = create_app()

    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app_.dependency_overrides[get_db] = _get_db_override
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
async def tools_client(tools_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=tools_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


# Helpers ----------------------------------------------------------------------


def _parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
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


async def _collect_sse(
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
    return _parse_sse("".join(chunks))


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> str:
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


async def _current_user_id(session_factory: async_sessionmaker[AsyncSession]) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _load_messages(
    session_factory: async_sessionmaker[AsyncSession], conv_id: str
) -> list[Message]:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


def _part_types(parts: object) -> list[str]:
    if not isinstance(parts, list):
        return []
    return [str(p.get("type")) for p in parts if isinstance(p, dict)]


# 1. Auto tool path ------------------------------------------------------------


async def test_auto_tool_streams_call_result_and_terminal_done(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "11111111-1111-1111-1111-111111111111",
         "tierId": "smart", "text": "TOOL_TIME: what time is it?"},
    )
    names = [n for n, _ in frames]
    assert "tool_call" in names
    assert "tool_result" in names
    assert names[-1] == "terminal"

    tool_call = next(d for n, d in frames if n == "tool_call")
    assert tool_call["name"] == "get_current_time"
    assert tool_call["status"] == "running"
    tool_result = next(d for n, d in frames if n == "tool_result")
    assert tool_result["status"] == "succeeded"
    assert frames[-1][1]["status"] == "done"

    # Persisted row carries both tool parts then text.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    types = _part_types(assistant[0].parts)
    assert types.index("tool_call") < types.index("tool_result") < types.index("text")
    assert assistant[0].status == "done"


# 2. Approval pause ------------------------------------------------------------


async def test_approval_gated_tool_pauses_turn(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "22222222-2222-2222-2222-222222222222",
         "tierId": "smart", "text": "TOOL_APPROVE: schedule a meeting"},
    )
    names = [n for n, _ in frames]
    # Ends with a pending tool_call then an awaiting_approval terminal.
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "awaiting_approval"
    tool_call = next(d for n, d in frames if n == "tool_call")
    assert tool_call["name"] == "calendar_create_event"
    assert tool_call["status"] == "awaiting_approval"
    assert tool_call["approvalState"] == "pending"

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].status == "awaiting_approval"

    # Durable stream row is awaiting_approval with a message_id pointing at the
    # paused assistant, and NO active stream remains (the guard was released so a
    # resume can open its own).
    async with session_factory() as session:
        active = await streams_repo.get_active_for_conversation(
            session, conversation_id=assistant[0].conversation_id
        )
        assert active is None
        stream_rows = (
            (
                await session.execute(
                    select(Stream).where(Stream.conversation_id == assistant[0].conversation_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(stream_rows) == 1
        assert stream_rows[0].status == "awaiting_approval"
        assert stream_rows[0].message_id == assistant[0].id

    # Wire round-trip: the paused turn must serialize through GET (StreamStatus
    # has to accept "awaiting_approval") so a reload can rehydrate the approval
    # card. Without it the read 500s on a paused conversation.
    resp = await tools_client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 200, resp.text
    wire_assistant = [m for m in resp.json()["messages"] if m["role"] == "assistant"]
    assert len(wire_assistant) == 1
    assert wire_assistant[0]["status"] == "awaiting_approval"


# 3. Resume → approve ----------------------------------------------------------


async def test_resume_approve_creates_new_assistant_and_executes_tool(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "33333333-3333-3333-3333-333333333333",
         "tierId": "smart", "text": "TOOL_APPROVE: schedule a meeting"},
    )
    before = await _load_messages(session_factory, conv_id)
    paused_assistant = next(m for m in before if m.role == "assistant")

    frames = await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "33333333-3333-3333-3333-333333333334",
         "tierId": "smart", "text": "",
         "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"}},
    )
    names = [n for n, _ in frames]
    assert "tool_result" in names
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    tool_result = next(d for n, d in frames if n == "tool_result")
    assert tool_result["status"] == "succeeded"
    assert tool_result["approvalState"] == "approved"
    answer = "".join(d.get("text", "") for n, d in frames if n == "answer_delta")  # type: ignore[arg-type]
    assert "approved" in answer

    msgs = await _load_messages(session_factory, conv_id)
    users = [m for m in msgs if m.role == "user"]
    assistants = [m for m in msgs if m.role == "assistant"]
    assert len(users) == 1
    assert len(assistants) == 2
    # Paused row untouched.
    paused_now = next(m for m in assistants if m.id == paused_assistant.id)
    assert paused_now.status == "awaiting_approval"
    # New row linked to the same user message; parts = [tool_result, text].
    new_row = next(m for m in assistants if m.id != paused_assistant.id)
    assert new_row.status == "done"
    assert new_row.responds_to_message_id == users[0].id
    types = _part_types(new_row.parts)
    assert types.index("tool_result") < types.index("text")
    assert "tool_call" not in types

    # No double-bill: the paused turn is metered once and the resume once — two
    # turns, two increments. Re-billing the paused row on resume would show 3.
    from app.db.models import UsageRollup

    async with session_factory() as session:
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        assert rollup.used == 2


# 4. Resume → deny -------------------------------------------------------------


async def test_resume_deny_cancels_without_executing(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "44444444-4444-4444-4444-444444444444",
         "tierId": "smart", "text": "TOOL_APPROVE: schedule a meeting"},
    )

    # The denied tool's executor must NEVER run — patch it to fail loudly.
    # ToolSpec is frozen, so swap the whole registry entry (dataclasses.replace).
    from dataclasses import replace

    from app.tools import builtin

    async def _boom(call: object) -> object:  # pragma: no cover - must not be called
        raise AssertionError("denied tool executor must not be invoked")

    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "calendar_create_event",
        replace(builtin.TOOL_REGISTRY["calendar_create_event"], executor=_boom),
    )

    frames = await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "44444444-4444-4444-4444-444444444445",
         "tierId": "smart", "text": "",
         "toolApproval": {"toolCallId": "fake_cal_1", "decision": "deny"}},
    )
    names = [n for n, _ in frames]
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    tool_result = next(d for n, d in frames if n == "tool_result")
    assert tool_result["status"] == "cancelled"
    assert tool_result["approvalState"] == "rejected"
    answer = "".join(d.get("text", "") for n, d in frames if n == "answer_delta")  # type: ignore[arg-type]
    assert "denied" in answer

    msgs = await _load_messages(session_factory, conv_id)
    assert len([m for m in msgs if m.role == "assistant"]) == 2


# 5. Gate is the trust boundary ------------------------------------------------


async def test_forged_approval_for_unknown_tool_is_rejected(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Pause first so the trailing assistant IS awaiting_approval.
    await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "55555555-5555-5555-5555-555555555555",
         "tierId": "smart", "text": "TOOL_APPROVE: schedule a meeting"},
    )

    # Forged toolCallId that does not match the pending call → INVALID_INPUT.
    resp = await tools_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"clientMessageId": "55555555-5555-5555-5555-555555555556",
              "tierId": "smart", "text": "",
              "toolApproval": {"toolCallId": "does_not_exist", "decision": "approve"}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"

    # The paused turn is untouched and no extra assistant row was created.
    msgs = await _load_messages(session_factory, conv_id)
    assert len([m for m in msgs if m.role == "assistant"]) == 1


async def test_resume_without_pending_pause_is_nothing_to_resume(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # A normal (non-paused) turn first.
    await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "66666666-6666-6666-6666-666666666666",
         "tierId": "smart", "text": "hello"},
    )
    resp = await tools_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"clientMessageId": "66666666-6666-6666-6666-666666666667",
              "tierId": "smart", "text": "",
              "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NOTHING_TO_RESUME"


# 6. Guards: bounded loop + executor timeout -----------------------------------


async def test_agent_loop_is_bounded_by_max_rounds() -> None:
    """A provider that requests a tool every round must still terminate."""
    from collections.abc import AsyncIterator as _AsyncIterator

    from app.config import Settings
    from app.providers.protocol import ProviderEvent, ToolCall, ToolResult
    from app.tools.agent_loop import run_agent_loop

    rounds_seen = 0

    def _make_stream(_feedback: list[ToolResult]) -> _AsyncIterator[ProviderEvent]:
        nonlocal rounds_seen
        rounds_seen += 1

        async def _gen() -> _AsyncIterator[ProviderEvent]:
            # Always re-request the auto tool → would loop forever unbounded.
            yield ToolCall(id=f"c{rounds_seen}", name="get_current_time", status="running")

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=2)  # type: ignore[call-arg]
    # The key invariant: the loop terminates (the comprehension completes) and is
    # bounded by max_rounds + the single compelled final pass.
    _ = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    assert rounds_seen <= settings.tool_max_rounds + 1


async def test_execute_tool_times_out_to_failed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from dataclasses import replace

    from app.config import Settings
    from app.tools import builtin
    from app.tools.builtin import execute_tool
    from app.tools.protocol import ToolCallRequest

    async def _slow(call: object) -> object:
        await asyncio.sleep(5)
        raise AssertionError("should have timed out")  # pragma: no cover

    # Swap the (frozen) registry entry's executor for a hanging one.
    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "get_current_time",
        replace(builtin.TOOL_REGISTRY["get_current_time"], executor=_slow),
    )
    # Force a tiny per-tool timeout.
    monkeypatch.setattr(
        builtin,
        "get_settings",
        lambda: Settings(TOOL_TIMEOUT_SECONDS=0.01),  # type: ignore[call-arg]
    )
    result = await execute_tool(ToolCallRequest(id="t1", name="get_current_time", input={}))
    assert result.status == "failed"
    assert result.error is not None


# 7. Flag-off no-op invariant --------------------------------------------------


async def test_tools_disabled_streams_normal_answer_no_tool_parts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The default `client`/`app` fixtures run with TOOLS_ENABLED unset (False).
    assert get_settings().tools_enabled is False
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "77777777-7777-7777-7777-777777777777",
         "tierId": "smart", "text": "TOOL_TIME: what time is it?"},
    )
    names = [n for n, _ in frames]
    assert "tool_call" not in names
    assert "tool_result" not in names
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert "tool_call" not in _part_types(assistant[0].parts)
