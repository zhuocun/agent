"""BE-005 worker HITL resume + BE-007 approval side-effect idempotency.

- Worker tool pause mid-fan-out waits for siblings, persists continuation, and
  on approve continues that worker then synthesizes (includes the paused worker).
- Double-resume after settle must not re-execute the gated tool.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic.continuation import (
    CONTINUATION_INPUT_KEY,
    SERVER_STATE_CONTINUATIONS_KEY,
    get_continuation_from_server_state,
    get_run_ledger_from_server_state,
)
from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.repositories import api_keys as api_keys_repo
from app.db.repositories import billing as billing_repo
from app.db.repositories import messages as messages_repo
from app.db.session import get_db
from app.errors import AppError
from app.providers.router import route_auto
from app.providers.tiers import TierBinding, get_binding
from app.routes import conversations as conversations_route
from app.streaming import handler as handler_mod
from app.streaming.handler import ResumeToolSeed
from app.tools import approval_settlement
from app.tools.approval_settlement import ApprovalSettlementIncomplete
from app.tools.protocol import ToolCallRequest, ToolExecutionResult

pytestmark = pytest.mark.asyncio


@pytest.fixture
def agentic_env() -> Iterator[None]:
    """Tools + agentic ON; plan-approval OFF so workers can hit tool HITL."""
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "false",
    }
    prior = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture
def agentic_app(
    agentic_env: None,
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
async def agentic_client(agentic_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=agentic_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


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
    async with client.stream("POST", url, json=body, timeout=15.0) as resp:
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


async def _grant_pro(
    session_factory: async_sessionmaker[AsyncSession], *, user_id: object
) -> None:
    async with session_factory() as session:
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=UUID(str(user_id)),
            provider="fake",
            subscription_id=f"sub-{user_id}",
            status="active",
            customer_id=f"cus-{user_id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()


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


def _answer(frames: list[tuple[str, dict[str, object]]]) -> str:
    return "".join(str(d.get("text", "")) for n, d in frames if n == "answer_delta")


_WORKER_HITL_PROMPT = (
    "DEEP_RESEARCH: TOOL_APPROVE schedule kickoff | sibling housing effects"
)


async def test_worker_hitl_pause_waits_for_siblings_then_approves(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """BE-005: pause mid-worker → approve → same worker continues → synthesis."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][0] == "terminal"
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    started = {str(d["subagentId"]) for n, d in pause_frames if n == "subagent_started"}
    done = {str(d["subagentId"]) for n, d in pause_frames if n == "subagent_done"}
    assert "worker-0" in started
    assert "worker-1" in started
    assert "worker-1" in done
    assert "worker-0" not in done
    assert "aggregator" not in started

    tool_calls = [d for n, d in pause_frames if n == "tool_call"]
    cal = next(c for c in tool_calls if c.get("name") == "calendar_create_event")
    assert cal["status"] == "awaiting_approval"
    assert cal["id"] == "worker-0::fake_worker_cal_0"
    assert cal.get("subagentId") == "worker-0"

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(m for m in msgs if m.role == "assistant")
    parts = [p for p in (paused.parts or []) if isinstance(p, dict)]
    cal_part = next(
        p
        for p in parts
        if p.get("type") == "tool_call" and p.get("id") == "worker-0::fake_worker_cal_0"
    )
    # H-012: continuation is server-only — not in tool input.
    assert CONTINUATION_INPUT_KEY not in (cal_part.get("input") or {})
    cont_obj = get_continuation_from_server_state(
        paused.server_state, "worker-0::fake_worker_cal_0"
    )
    assert cont_obj is not None
    cont = {
        "phase": cont_obj.phase,
        "pausedSubagentId": cont_obj.paused_subagent_id,
        "orchestrationMode": cont_obj.orchestration_mode,
        "completedWorkers": [
            {"subagentId": w.subagent_id} for w in cont_obj.completed_workers
        ],
        "partialAnswer": cont_obj.partial_answer,
        "sourceIds": list(cont_obj.source_ids),
    }
    assert cont["phase"] == "worker"
    assert cont["pausedSubagentId"] == "worker-0"
    assert cont.get("orchestrationMode") == "deep_research"
    assert any(w["subagentId"] == "worker-1" for w in cont["completedWorkers"])
    # H-010: pre-pause draft text captured; sources restored when web_search on.
    assert "drafting calendar pause" in (cont.get("partialAnswer") or "")

    resume_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            # H-002: omit agenticMode — resume must pin deep_research from checkpoint.
            "toolApproval": {
                "toolCallId": "worker-0::fake_worker_cal_0",
                "decision": "approve",
            },
        },
    )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"

    resume_started = {
        str(d["subagentId"]) for n, d in resume_frames if n == "subagent_started"
    }
    resume_done = {
        str(d["subagentId"]) for n, d in resume_frames if n == "subagent_done"
    }
    assert "worker-0" in resume_started
    assert "worker-0" in resume_done
    assert "aggregator" in resume_started

    answer = _answer(resume_frames)
    assert (
        "Worker 0" in answer
        or "kickoff" in answer.lower()
        or "finding" in answer.lower()
    )
    assert "Worker 1" in answer or "housing" in answer.lower()
    assert "Synthesis" in answer or "finding" in answer.lower()
    # H-010: pre-pause draft must not be re-emitted as worker AnswerDelta on resume.
    # (Synthesis may still include it in the composed worker answer — that is correct.)
    draft = "drafting calendar pause"
    pause_answer = _answer(pause_frames)
    assert draft in pause_answer
    resume_worker0 = "".join(
        str(d.get("text", ""))
        for n, d in resume_frames
        if n == "answer_delta" and d.get("subagentId") == "worker-0"
    )
    assert draft not in resume_worker0


async def test_approval_idempotent_double_resume_does_not_reexecute(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BE-007: settle-before-stream; second resume reuses stored result."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
        },
    )

    from app.tools import builtin

    exec_count = {"n": 0}
    real_exec = builtin._execute_calendar_create_event

    async def _counting_exec(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real_exec(call)

    original_spec = builtin.TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "calendar_create_event",
        builtin.ToolSpec(
            name=original_spec.name,
            label=original_spec.label,
            needs_approval=original_spec.needs_approval,
            schema=original_spec.schema,
            executor=_counting_exec,
            prod_safe=original_spec.prod_safe,
        ),
    )

    frames1 = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert frames1[-1][1]["status"] == "done"
    assert exec_count["n"] == 1

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval")
    settled = approval_settlement.find_settled_tool_result(paused.parts, "fake_cal_1")
    assert settled is not None
    assert settled.get("approvalState") == "approved"
    first_output = settled.get("output")

    done_rows = [m for m in msgs if m.role == "assistant" and m.status == "done"]
    async with session_factory() as session:
        for row in done_rows:
            db_row = await session.get(Message, row.id)
            if db_row is not None:
                await session.delete(db_row)
        await session.commit()

    frames2 = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert frames2[-1][1]["status"] == "done"
    assert exec_count["n"] == 1

    msgs2 = await _load_messages(session_factory, conv_id)
    paused2 = next(
        m for m in msgs2 if m.role == "assistant" and m.status == "awaiting_approval"
    )
    settled2 = approval_settlement.find_settled_tool_result(paused2.parts, "fake_cal_1")
    assert settled2 is not None
    assert settled2.get("output") == first_output


async def test_settled_id_reissue_does_not_reexecute(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-001 / O-001: provider repeating a settled call id must not re-run."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "d0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
        },
    )

    from app.tools import builtin

    exec_count = {"n": 0}
    real_exec = builtin._execute_calendar_create_event

    async def _counting_exec(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real_exec(call)

    original_spec = builtin.TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "calendar_create_event",
        builtin.ToolSpec(
            name=original_spec.name,
            label=original_spec.label,
            needs_approval=original_spec.needs_approval,
            schema=original_spec.schema,
            executor=_counting_exec,
            prod_safe=original_spec.prod_safe,
        ),
    )

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "d0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert frames[-1][1]["status"] == "done"
    assert exec_count["n"] == 1

    # Deny-then-reissue path: seed a denied settlement and ensure a model
    # reissue cannot authorize via the old id (unit-level via agent_loop).
    from app.config import get_settings
    from app.providers.protocol import Complete, ToolCall, ToolResult, UsageUpdate
    from app.tools.agent_loop import run_agent_loop

    settings = get_settings()
    events: list[object] = []
    round_n = {"n": 0}

    async def _make_stream(feedback, suppress_tools=False, *, answer_nudge=False):  # type: ignore[no-untyped-def]
        round_n["n"] += 1
        if round_n["n"] == 1:
            # First provider pass after seeding: reissue the settled id.
            yield ToolCall(
                id="fake_cal_1",
                name="calendar_create_event",
                status="running",
                approval_state="approved",
                input={"title": "replay"},
            )
            yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))
            return
        yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

    async for ev in run_agent_loop(
        make_stream=_make_stream,
        settings=settings,
        server_approved_call_ids={"fake_cal_1"},  # adversarial: capability still listed
        initial_tool_results=[
            ToolResult(
                tool_call_id="fake_cal_1",
                name="calendar_create_event",
                status="cancelled",
                approval_state="rejected",
                summary="User denied the tool call.",
                error="User denied the tool call.",
            )
        ],
    ):
        events.append(ev)

    assert exec_count["n"] == 1
    results = [e for e in events if isinstance(e, ToolResult)]
    assert results
    assert results[0].status == "failed"
    assert "already settled" in (results[0].error or "").lower() or "Duplicate" in (
        results[0].summary or ""
    )


async def test_conflicting_decision_returns_409(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-006: approve after a durable deny is rejected with 409."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "e0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
        },
    )
    deny_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "e0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "deny"},
        },
    )
    assert deny_frames[-1][1]["status"] == "done"

    # Remove the post-deny assistant so resume can target the paused row again.
    msgs = await _load_messages(session_factory, conv_id)
    done_rows = [m for m in msgs if m.role == "assistant" and m.status == "done"]
    async with session_factory() as session:
        for row in done_rows:
            db_row = await session.get(Message, row.id)
            if db_row is not None:
                await session.delete(db_row)
        await session.commit()

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "e0000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "APPROVAL_DECISION_CONFLICT"


_TWO_WORKER_HITL_PROMPT = (
    "DEEP_RESEARCH: TOOL_APPROVE schedule alpha | TOOL_APPROVE schedule beta"
)


async def test_h002_resume_pins_mode_when_client_changes_to_single(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-002: client agenticMode=single must not drop a deep_research continuation."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    resume_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            # Client tries to coerce away from the pinned agentic continuation.
            "agenticMode": "single",
            "toolApproval": {
                "toolCallId": "worker-0::fake_worker_cal_0",
                "decision": "approve",
            },
        },
    )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"
    resume_started = {
        str(d["subagentId"]) for n, d in resume_frames if n == "subagent_started"
    }
    assert "worker-0" in resume_started
    assert "aggregator" in resume_started


async def test_h003_concurrent_worker_pauses_reject_sibling(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-003: second worker pause is rejected; only continuation-bearing id resumes."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000011",
            "tierId": "smart",
            "text": _TWO_WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    tool_calls = [d for n, d in pause_frames if n == "tool_call"]
    cal_calls = [c for c in tool_calls if c.get("name") == "calendar_create_event"]
    assert len(cal_calls) >= 2

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval")
    parts = [p for p in (paused.parts or []) if isinstance(p, dict)]
    worker_calls = [
        p
        for p in parts
        if p.get("type") == "tool_call" and p.get("name") == "calendar_create_event"
    ]
    with_cont = []
    without_cont = []
    for p in worker_calls:
        # H-012: continuation lives in server_state, not tool input.
        assert CONTINUATION_INPUT_KEY not in (p.get("input") or {})
        cid = str(p.get("id") or "")
        cont = get_continuation_from_server_state(paused.server_state, cid)
        if cont is not None:
            with_cont.append(p)
        else:
            without_cont.append(p)
    assert len(with_cont) == 1
    assert len(without_cont) >= 1
    sibling = without_cont[0]
    assert sibling.get("approvalState") == "rejected"
    assert sibling.get("status") == "cancelled"

    # Approving the orphaned sibling must fail — not resumable without continuation.
    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "f0000000-0000-0000-0000-000000000012",
            "tierId": "smart",
            "text": "",
            "toolApproval": {
                "toolCallId": sibling["id"],
                "decision": "approve",
            },
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"

    # Sibling deny must not leave an active stream claim (H-003 re-review).
    from app.db.models import Stream

    async with session_factory() as session:
        active = (
            await session.execute(
                select(Stream).where(
                    Stream.conversation_id == UUID(conv_id),
                    Stream.status == "active",
                )
            )
        ).scalars().all()
    assert active == []

    winner_id = str(with_cont[0]["id"])
    resume_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000013",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": winner_id, "decision": "approve"},
        },
    )
    assert resume_frames[-1][1]["status"] == "done"


async def test_h003_superseded_sibling_emits_subagent_done_and_attribution(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FL-09 (GAP-2): the superseded loser is CLOSED on the wire, not left open.

    The cancelled `ToolResult` shipped without a `SubagentDone`, so the FE row
    spun forever and the handler defaulted the outcome to `succeeded`.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000031",
            "tierId": "smart",
            "text": _TWO_WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][1]["status"] == "awaiting_approval"

    superseded_result = next(
        d
        for n, d in frames
        if n == "tool_result" and d.get("status") == "cancelled"
    )
    loser_id = str(superseded_result["subagentId"])
    dones = {str(d["subagentId"]): d for n, d in frames if n == "subagent_done"}
    assert loser_id in dones, "superseded sibling never reached a terminal outcome"
    assert dones[loser_id]["outcome"] == "cancelled"
    # A cancelled sibling is not a failure — `failed_worker_count` stays honest.
    run_costs = [d for n, d in frames if n == "run_cost"]
    assert all(d.get("failedWorkerCount", 0) == 0 for d in run_costs)

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(
        m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval"
    )
    parts = [p for p in (paused.parts or []) if isinstance(p, dict)]
    loser_part = next(
        p
        for p in parts
        if p.get("type") == "subagent" and p.get("subagentId") == loser_id
    )
    assert loser_part.get("outcome") == "cancelled"

    # The continuation's stored outcome must match the streamed one so the
    # resume can fold the loser's text back as a truncated partial.
    winner_call = next(
        p
        for p in parts
        if p.get("type") == "tool_call"
        and get_continuation_from_server_state(
            paused.server_state, str(p.get("id") or "")
        )
        is not None
    )
    cont = get_continuation_from_server_state(
        paused.server_state, str(winner_call["id"])
    )
    assert cont is not None
    loser_state = next(
        w for w in cont.completed_workers if w.subagent_id == loser_id
    )
    assert loser_state.outcome == "cancelled"
    # Its partial findings are preserved for synthesis, not discarded.
    assert loser_state.answer.strip()


async def test_h003_superseded_fallback_sibling_is_priced_on_fallback_binding() -> None:
    """FL-09 / COST-2: a fallback-served loser is billed and attributed there.

    With no `substitution` on the wire the handler priced `acc.usage` on the
    PRIMARY binding and persisted a primary `ModelAttribution` — a silent
    downgrade plus an unbilled delta (invariant 13).
    """
    import asyncio
    from collections.abc import AsyncIterator as _AsyncIterator

    from app.agentic.orchestrator import run_orchestrator
    from app.config import Settings
    from app.providers.protocol import (
        AnswerDelta,
        AwaitingApproval,
        ProviderEvent,
        RunCost,
        SubagentDone,
        ToolCall,
        ToolResult,
        UsageUpdate,
    )

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_PLAN_APPROVAL=False,
        AGENTIC_VERIFIER=False,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    first_paused = asyncio.Event()

    def _pause_stream(index: str, *, wait: bool) -> _AsyncIterator[ProviderEvent]:
        async def _gen() -> _AsyncIterator[ProviderEvent]:
            if wait:
                await first_paused.wait()
                # Let the winner's pause reach the fan-out queue first so this
                # sibling is deterministically the superseded one.
                await asyncio.sleep(0.05)
            yield AnswerDelta(text=f"partial from {index}")
            yield UsageUpdate(input_tokens=2, output_tokens=0)
            yield ToolCall(
                id=f"cal-{index}",
                name="calendar_create_event",
                label="Create calendar event",
                status="awaiting_approval",
                approval_state="pending",
                input={"title": index},
            )
            if not wait:
                # Release the sibling BEFORE the pause: the loop breaks on
                # AwaitingApproval, so nothing after it ever runs.
                first_paused.set()
            yield AwaitingApproval(tool_call_id=f"cal-{index}")

        return _gen()

    def _primary(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> _AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _pause_stream("w0", wait=False)
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                # Retryable before any visible event: the loser is fallback-served.
                async def _boom() -> _AsyncIterator[ProviderEvent]:
                    raise RuntimeError("retryable")
                    yield AnswerDelta(text="x")  # pragma: no cover

                return _boom()

            async def _agg() -> _AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="agg")
                yield Complete(usage=UsageUpdate())

            return _agg()

        return _make

    def _fallback(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> _AsyncIterator[ProviderEvent]:
            return _pause_stream("w1", wait=True)

        return _make

    from app.providers.protocol import Complete

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_primary,
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: alpha | beta",
            cost_for_usage=lambda u: 0.01 * float(u.input_tokens),
            fallback_make_stream_for=_fallback,
            fallback_cost_for_usage=lambda u: 0.5 * float(u.input_tokens),
            fallback_provider_id="openai",
            fallback_model_id="gpt-test",
            fallback_display_label="GPT Test",
            is_retryable=lambda _exc: True,
        )
    ]
    cancelled = [
        e for e in events if isinstance(e, ToolResult) and e.status == "cancelled"
    ]
    assert cancelled
    loser_id = str(cancelled[0].subagent_id)
    assert loser_id == "worker-1"
    loser_done = next(
        e
        for e in events
        if isinstance(e, SubagentDone) and e.subagent_id == loser_id
    )
    assert loser_done.outcome == "cancelled"
    # Priced and attributed on the route that actually served it.
    assert loser_done.substitution == "provider_fallback"
    assert loser_done.substituted_provider == "openai"
    assert loser_done.substituted_model == "gpt-test"
    assert loser_done.cost_usd == pytest.approx(0.5 * 2)
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert all(f.failed_worker_count == 0 for f in finals)


async def test_h008_continue_turn_refuses_agentic_checkpoint(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-008: continueTurn refuses agentic awaiting_approval; use toolApproval."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000021",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    # Shadow the checkpoint with a later stopped assistant (stop-during-resume case).
    msgs = await _load_messages(session_factory, conv_id)
    paused = next(m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval")
    async with session_factory() as session:
        shadow = Message(
            conversation_id=paused.conversation_id,
            role="assistant",
            status="stopped",
            parts=[{"type": "text", "text": "partial"}],
            responds_to_message_id=paused.responds_to_message_id,
            created_at=paused.created_at + timedelta(seconds=1),
        )
        session.add(shadow)
        await session.commit()

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "f0000000-0000-0000-0000-000000000022",
            "tierId": "smart",
            "text": "ignored",
            "continueTurn": True,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "AGENTIC_CHECKPOINT_PENDING"


async def test_h009_budget_halted_resume_skips_provider() -> None:
    """H-009: budget_halted continuation synthesizes without another provider call."""
    from app.agentic.continuation import AgenticContinuation, CompletedWorkerState
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import AnswerDelta, Complete, ToolResult, UsageUpdate

    calls = {"n": 0}

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                calls["n"] += 1
                yield AnswerDelta(text="should-not-run")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_RUN_BUDGET_USD=1.0,
    )
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.1,
        budget_halted=True,
        actual_cost_usd=0.95,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="partial",
        orchestration_mode="deep_research",
    )
    seed = ToolResult(
        tool_call_id="worker-0::x",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )
    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=settings,
            cost_for_usage=lambda u: 0.01,
            continuation=cont,
            resume_tool_result=seed,
            server_approved_call_ids=set(),
        )
    ]
    assert calls["n"] == 0
    texts = "".join(
        getattr(e, "text", "") for e in events if getattr(e, "text", None)
    )
    assert "beta" in texts.lower() or "synthesis" in texts.lower() or texts


async def test_o008_resume_uses_fallback_on_retryable_failure() -> None:
    """O-008: resumed worker uses fallback_make_stream_for on retryable primary fail."""
    from app.agentic.continuation import AgenticContinuation, CompletedWorkerState
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import AnswerDelta, Complete, SubagentDone, ToolResult, UsageUpdate

    primary_calls = {"n": 0}
    fallback_calls = {"n": 0}

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                primary_calls["n"] += 1
                raise RuntimeError("primary boom")
                yield AnswerDelta(text="unreachable")  # make this an async generator

            return _gen()

        return _make

    def _fallback_make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                fallback_calls["n"] += 1
                yield AnswerDelta(text="fallback answer")
                yield Complete(usage=UsageUpdate(input_tokens=3, output_tokens=2))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.1,
        budget_halted=False,
        actual_cost_usd=0.3,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="",
        orchestration_mode="deep_research",
    )
    seed = ToolResult(
        tool_call_id="worker-0::x",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )
    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=settings,
            cost_for_usage=lambda u: float(u.input_tokens) * 0.01,
            continuation=cont,
            resume_tool_result=seed,
            server_approved_call_ids=set(),
            fallback_make_stream_for=_fallback_make_stream_for,
            fallback_cost_for_usage=lambda u: float(u.input_tokens) * 0.5,
            fallback_provider_id="openai",
            fallback_model_id="gpt-test",
            fallback_display_label="GPT Test",
            is_retryable=lambda _exc: True,
        )
    ]
    assert primary_calls["n"] >= 1
    assert fallback_calls["n"] >= 1
    done = next(
        e
        for e in events
        if isinstance(e, SubagentDone) and e.subagent_id == "worker-0"
    )
    assert done.substitution in {"provider_fallback", "rate_limited"}
    assert done.substituted_provider == "openai"


async def test_c002_resume_worker_prompt_keeps_clarification_questions() -> None:
    """C-002: worker-HITL resume must pass full Q&A records into the prompt.

    Collapsing ``continuation.clarifications`` to non-blank answer strings drops
    question text and re-shifts blank positions before ``with_clarifications``.
    """
    from app.agentic.clarify import CLARIFICATIONS_HEADER, ClarificationRecord
    from app.agentic.continuation import AgenticContinuation, CompletedWorkerState
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import AnswerDelta, Complete, ToolResult, UsageUpdate

    captured: list[str] = []

    def _make_stream_for(prompt: str, **_kwargs: object):
        captured.append(prompt)

        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                yield AnswerDelta(text="alpha finding")
                yield Complete(usage=UsageUpdate(input_tokens=2, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    question_text = "What specific aspect should the research prioritize?"
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.1,
        budget_halted=False,
        actual_cost_usd=0.3,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="",
        clarifications=(
            ClarificationRecord(
                question_id="0",
                question=question_text,
                answer="",
            ),
            ClarificationRecord(
                question_id="1",
                question="Any constraints to apply?",
                answer="US, last 5 years",
            ),
        ),
        orchestration_mode="deep_research",
    )
    seed = ToolResult(
        tool_call_id="worker-0::x",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )
    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=settings,
            cost_for_usage=lambda u: 0.01,
            continuation=cont,
            resume_tool_result=seed,
            server_approved_call_ids=set(),
        )
    ]
    assert captured, "resumed worker must invoke the provider with a prompt"
    prompt = captured[0]
    assert CLARIFICATIONS_HEADER in prompt
    assert question_text in prompt
    assert "Any constraints to apply?" in prompt
    # Blank first answer must not shift the second answer onto question 0.
    assert '"questionId": "0"' in prompt or '"questionId":"0"' in prompt
    assert "US, last 5 years" in prompt
    texts = "".join(
        getattr(e, "text", "") for e in events if getattr(e, "text", None)
    )
    assert "alpha finding" in texts or "synthesis" in texts.lower() or texts



async def test_h007_stop_before_deferred_execute(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-007: stop observed before deferred settle must not execute the tool."""
    from app.db.models import Stream
    from app.tools import builtin

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000031",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
        },
    )

    exec_count = {"n": 0}
    real_exec = builtin._execute_calendar_create_event

    async def _counting_exec(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real_exec(call)

    original_spec = builtin.TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "calendar_create_event",
        builtin.ToolSpec(
            name=original_spec.name,
            label=original_spec.label,
            needs_approval=original_spec.needs_approval,
            schema=original_spec.schema,
            executor=_counting_exec,
            prod_safe=original_spec.prod_safe,
        ),
    )

    async def _always_stop(_stream_id: object) -> bool:
        return True

    monkeypatch.setattr(
        "app.streaming.handler.is_stop_requested_async",
        _always_stop,
    )

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000032",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert exec_count["n"] == 0
    # Stream ends without a provider pass; no active claim left behind.
    async with session_factory() as session:
        active = (
            await session.execute(
                select(Stream).where(
                    Stream.conversation_id == UUID(conv_id),
                    Stream.status == "active",
                )
            )
        ).scalars().all()
    assert active == []
    # No done terminal from a successful resume.
    terminals = [d for n, d in frames if n == "terminal"]
    assert not any(t.get("status") == "done" for t in terminals)


async def test_h007_stop_cancels_in_flight_execute(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-007: mid-execute stop cancels settle and does not leave a succeeded result."""
    import asyncio

    from app.db.models import Stream
    from app.tools import builtin

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000041",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
        },
    )

    entered = asyncio.Event()
    exec_count = {"n": 0}

    async def _blocking_exec(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        entered.set()
        # Block until the settle task is cancelled by the stop watcher.
        await asyncio.sleep(30)
        raise AssertionError("execute should have been cancelled")

    original_spec = builtin.TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "calendar_create_event",
        builtin.ToolSpec(
            name=original_spec.name,
            label=original_spec.label,
            needs_approval=original_spec.needs_approval,
            schema=original_spec.schema,
            executor=_blocking_exec,
            prod_safe=original_spec.prod_safe,
        ),
    )

    async def _resume() -> list[tuple[str, dict[str, object]]]:
        return await _collect_sse(
            agentic_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "f0000000-0000-0000-0000-000000000042",
                "tierId": "smart",
                "text": "",
                "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
            },
        )

    resume_task = asyncio.create_task(_resume())
    await asyncio.wait_for(entered.wait(), timeout=5.0)

    stop_resp = await agentic_client.post(f"/api/conversations/{conv_id}/stop")
    assert stop_resp.status_code == 204

    frames = await asyncio.wait_for(resume_task, timeout=5.0)
    assert exec_count["n"] == 1
    terminals = [d for n, d in frames if n == "terminal"]
    assert not any(t.get("status") == "done" for t in terminals)

    async with session_factory() as session:
        active = (
            await session.execute(
                select(Stream).where(
                    Stream.conversation_id == UUID(conv_id),
                    Stream.status == "active",
                )
            )
        ).scalars().all()
    assert active == []

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(
        m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval"
    )
    parts = [p for p in (paused.parts or []) if isinstance(p, dict)]
    results = [
        p
        for p in parts
        if p.get("type") == "tool_result" and p.get("toolCallId") == "fake_cal_1"
    ]
    if results:
        assert results[-1].get("status") != "succeeded"


async def test_h010_resume_does_not_reemit_partial_answer() -> None:
    """H-010: structured checkpoint restores text without AnswerDelta replay."""
    from app.agentic.continuation import AgenticContinuation, CompletedWorkerState
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import AnswerDelta, Complete, ToolResult, UsageUpdate

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                yield AnswerDelta(text=" post-resume finding")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
                source_ids=("s1",),
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.1,
        actual_cost_usd=0.3,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="already delivered draft",
        source_ids=("src-pre",),
        emitted_answer_chars=len("already delivered draft"),
        orchestration_mode="deep_research",
        paused_worker_usage=UsageUpdate(input_tokens=3, output_tokens=2),
        paused_worker_cost_usd=0.05,
    )
    seed = ToolResult(
        tool_call_id="worker-0::x",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        output={"ok": True},
    )
    events: list[object] = []
    async for ev in _resume_worker_continuation(
        make_stream_for=_make_stream_for,
        settings=settings,
        cost_for_usage=lambda u: 0.01,
        continuation=cont,
        resume_tool_result=seed,
        server_approved_call_ids=set(),
    ):
        events.append(ev)

    answer_deltas = [
        e
        for e in events
        if isinstance(e, AnswerDelta) and getattr(e, "subagent_id", None) == "worker-0"
    ]
    texts = [e.text for e in answer_deltas]
    assert "already delivered draft" not in "".join(texts)
    assert any("post-resume" in t for t in texts)


async def test_resume_does_not_re_pause_on_an_already_settled_id() -> None:
    """FL-15 / H-002: the resumed worker must not re-pause on the settled id.

    The seed arrives namespaced (`worker-0::…`) while the provider reissues the
    raw id, so the settlement guard never matched and the run surfaced a second
    approval card for a call the user had already decided.
    """
    from app.agentic.continuation import AgenticContinuation, CompletedWorkerState
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import (
        AnswerDelta,
        AwaitingApproval,
        Complete,
        ToolCall,
        ToolResult,
        UsageUpdate,
    )

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                if suppress_tools:
                    yield AnswerDelta(text="finishing without the tool")
                    yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))
                    return
                # Reissue the RAW id the pause turn already settled.
                yield ToolCall(
                    id="fake_cal_1",
                    name="calendar_create_event",
                    status="running",
                    input={"title": "again"},
                )

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_VERIFIER=False,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.1,
        actual_cost_usd=0.3,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="",
        orchestration_mode="deep_research",
    )
    seed = ToolResult(
        tool_call_id="worker-0::fake_cal_1",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )
    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=settings,
            cost_for_usage=lambda _u: 0.01,
            continuation=cont,
            resume_tool_result=seed,
            server_approved_call_ids=set(),
        )
    ]
    assert not any(isinstance(e, AwaitingApproval) for e in events)
    refusals = [
        e
        for e in events
        if isinstance(e, ToolResult)
        and str(e.tool_call_id).endswith("fake_cal_1")
        and e.summary == "Duplicate tool call after settlement."
    ]
    assert refusals


async def test_resume_folds_a_cancelled_sibling_as_a_truncated_partial() -> None:
    """FL-09: the resume READS `CompletedWorkerState.outcome` (write-only before).

    A superseded sibling's text is a truncated partial, so the resume must mark it
    and keep `RunCost.partial` True instead of re-presenting it as finished work.
    """
    from app.agentic.continuation import AgenticContinuation, CompletedWorkerState
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import (
        AnswerDelta,
        Complete,
        RunCost,
        ToolResult,
        UsageUpdate,
    )

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[object]:
            async def _gen() -> AsyncIterator[object]:
                yield AnswerDelta(text="alpha resumed finding")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_VERIFIER=False,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta partial text",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
                outcome="cancelled",
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.1,
        actual_cost_usd=0.3,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="",
        orchestration_mode="deep_research",
    )
    seed = ToolResult(
        tool_call_id="worker-0::x",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )
    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=settings,
            cost_for_usage=lambda _u: 0.01,
            continuation=cont,
            resume_tool_result=seed,
            server_approved_call_ids=set(),
        )
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert "beta partial text" in answer
    assert "cancelled before finishing" in answer
    assert "were cancelled while another awaited approval" in answer
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].partial is True
    assert finals[-1].budget_halted is False


async def test_h013_conflicting_decision_on_worker_resume(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-013: deny then approve on the same settled call is refused (409)."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000031",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    call_id = "worker-0::fake_worker_cal_0"

    deny_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000032",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": call_id, "decision": "deny"},
        },
    )
    assert deny_frames[-1][0] == "terminal"

    conflict = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "f0000000-0000-0000-0000-000000000033",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": call_id, "decision": "approve"},
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "APPROVAL_DECISION_CONFLICT"


_WORKER_HITL_TWICE_PROMPT = (
    "DEEP_RESEARCH: TOOL_APPROVE_TWICE schedule kickoff | sibling housing effects"
)


async def test_h010_two_consecutive_worker_approvals_keep_transcript(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-010: second nested worker pause retains reasoning + prior tool transcript."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause1 = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000041",
            "tierId": "smart",
            "text": _WORKER_HITL_TWICE_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause1[-1][1]["status"] == "awaiting_approval"
    call1 = next(
        d
        for n, d in pause1
        if n == "tool_call" and d.get("name") == "calendar_create_event"
    )
    call1_id = str(call1["id"])
    assert call1_id.endswith("_0")

    resume1 = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000042",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": call1_id, "decision": "approve"},
        },
    )
    assert resume1[-1][1]["status"] == "awaiting_approval"
    call2 = next(
        d
        for n, d in resume1
        if n == "tool_call" and d.get("name") == "calendar_create_event"
    )
    call2_id = str(call2["id"])
    assert call2_id != call1_id
    assert call2_id.endswith("_1")

    msgs = await _load_messages(session_factory, conv_id)
    paused_rows = [
        m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval"
    ]
    assert paused_rows
    paused = paused_rows[-1]
    cont = get_continuation_from_server_state(paused.server_state, call2_id)
    assert cont is not None
    # First-pass reasoning plus nested-pause reasoning must both survive.
    assert "Let me think" in cont.partial_reasoning
    assert "second approval" in cont.partial_reasoning
    transcript_types = [p.get("type") for p in cont.tool_transcript]
    assert "tool_call" in transcript_types
    assert "tool_result" in transcript_types
    # Settled first approval + pending second call.
    result_ids = {
        str(p.get("toolCallId"))
        for p in cont.tool_transcript
        if p.get("type") == "tool_result"
    }
    call_ids = {
        str(p.get("id")) for p in cont.tool_transcript if p.get("type") == "tool_call"
    }
    assert call1_id in result_ids or any(call1_id in rid for rid in result_ids)
    assert call2_id in call_ids

    resume2 = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000043",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": call2_id, "decision": "approve"},
        },
    )
    assert resume2[-1][0] == "terminal"
    assert resume2[-1][1]["status"] == "done"


async def test_worker_pause_pins_served_route_identity(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FL-32 (HITL-5): the AR-006 route pin has to actually reach the checkpoint.

    `serialize_continuation` emits `tierId` / `providerId` / `modelId`
    unconditionally, as `None` — so the handler's `cont_blob.setdefault(...)`
    never fired and all three stayed null. That left the three route guards in
    `send_message` dead: a resume could silently move a settled continuation to
    a different tier, provider, or model.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "f0000000-0000-0000-0000-000000000051",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(
        m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval"
    )
    call_id = "worker-0::fake_worker_cal_0"
    cont = get_continuation_from_server_state(paused.server_state, call_id)
    assert cont is not None
    assert cont.tier_id == "smart"
    assert cont.provider_id
    assert cont.model_id
    # FL-28's companion pin: the mode is recorded for the resume too.
    assert cont.orchestration_mode == "deep_research"

    # With the pin populated, the dead guard rejects a cross-tier resume.
    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "f0000000-0000-0000-0000-000000000052",
            "tierId": "fast",
            "text": "",
            "toolApproval": {"toolCallId": call_id, "decision": "approve"},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


class _NoDisconnect:
    async def is_disconnected(self) -> bool:
        return False


class _UnusedProvider:
    def stream(self, **_kwargs: object):  # type: ignore[no-untyped-def]
        raise AssertionError("the stubbed orchestrator replaces the provider")


async def test_paused_fallback_worker_is_billed_and_attributed_on_the_fallback_binding(
    agentic_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-30 (COST-2, live-pause arm): the pause must pay the fallback price.

    A live HITL pause stays non-terminal (B15), so the paused worker never gets a
    `SubagentDone` to carry `substitution`. The handler therefore priced its
    banked usage on the PRIMARY binding and persisted a primary attribution — a
    silent downgrade plus a permanently unbilled remainder, since
    `_billable_cost_delta` later subtracts the larger orchestrator-side
    `pausedWorkerCostUsd`.

    The orchestrator is stubbed so the fan-out shape (paused fallback worker +
    completed primary sibling) and the reported `RunCost` are exact.
    """
    from uuid import uuid4

    from app.providers.pricing import compute_cost_breakdown
    from app.providers.protocol import (
        AnswerDelta,
        AwaitingApproval,
        ProviderEvent,
        RunCost,
        SubagentDone,
        SubagentStarted,
        ToolCall,
        UsageUpdate,
    )
    from app.providers.tiers import get_binding
    from app.streaming import handler as handler_mod

    binding = get_binding("smart")
    fallback_binding = get_binding("pro")
    assert binding is not None and fallback_binding is not None
    assert fallback_binding.model_id != binding.model_id

    paused_usage = UsageUpdate(input_tokens=900, output_tokens=400)
    # What the orchestrator banked for the paused worker: the FALLBACK price.
    paused_cost = compute_cost_breakdown(
        usage=paused_usage, binding=fallback_binding, image_count=0
    ).subtotal_usd
    primary_cost = compute_cost_breakdown(
        usage=paused_usage, binding=binding, image_count=0
    ).subtotal_usd
    assert paused_cost > primary_cost  # otherwise the arm proves nothing
    sibling_cost = 0.011
    run_subtotal = paused_cost + sibling_cost

    call_id = "worker-0::cal-1"
    events: list[ProviderEvent] = [
        SubagentStarted(subagent_id="worker-0", label="Alpha", role="worker"),
        SubagentStarted(subagent_id="worker-1", label="Beta", role="worker"),
        AnswerDelta(text="beta done", subagent_id="worker-1"),
        SubagentDone(
            subagent_id="worker-1",
            label="Beta",
            role="worker",
            usage=UsageUpdate(input_tokens=20, output_tokens=8),
            cost_usd=sibling_cost,
            outcome="succeeded",
        ),
        AnswerDelta(text="alpha partial", subagent_id="worker-0"),
        UsageUpdate(
            input_tokens=paused_usage.input_tokens,
            output_tokens=paused_usage.output_tokens,
            subagent_id="worker-0",
        ),
        ToolCall(
            id=call_id,
            name="calendar_create_event",
            label="Create calendar event",
            status="awaiting_approval",
            approval_state="pending",
            input={"title": "kickoff"},
            subagent_id="worker-0",
        ),
        # FL-14: the receipt precedes the pause terminal on the wire.
        RunCost(
            subtotal_usd=run_subtotal,
            cap_usd=10.0,
            confidence="exact",
            phase="final",
            partial=True,
        ),
        AwaitingApproval(
            tool_call_id=call_id,
            subagent_id="worker-0",
            continuation={
                "phase": "worker",
                "pausedSubagentId": "worker-0",
                "userText": "compare alpha | beta",
                "plan": ["alpha", "beta"],
                "pausedWorkerIndex": 0,
                "pausedSubQuestion": "alpha",
                "pausedWorkerUsedFallback": True,
                "pausedWorkerCostUsd": paused_cost,
                "actualCostUsd": run_subtotal,
            },
        ),
    ]

    def _fake_run_orchestrator(**_kwargs: object) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            for ev in events:
                yield ev

        return _gen()

    monkeypatch.setattr(handler_mod, "run_orchestrator", _fake_run_orchestrator)

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id, title="fl30", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    async with session_factory() as session:
        async for _ev in handler_mod.stream_and_persist(
            request=_NoDisconnect(),  # type: ignore[arg-type]
            db=session,
            provider=_UnusedProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="compare alpha | beta",
            history=[],
            is_temporary=False,
            user_id=user_id,
            fallback_binding=fallback_binding,
            fallback_provider_id="openai",
            fallback_substitution="provider_fallback",
            agentic_mode="deep_research",
        ):
            pass

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        ).scalars().first()
    assert row is not None
    assert row.status == "awaiting_approval"

    # F2 DoD 5: the billed amount IS the orchestrator's reported subtotal.
    assert float(row.cost_usd or 0.0) == pytest.approx(run_subtotal)
    attribution = row.attribution
    assert isinstance(attribution, dict)
    assert float(attribution["costUsd"]) == pytest.approx(run_subtotal)

    parts = [p for p in (row.parts or []) if isinstance(p, dict)]
    paused_part = next(
        p
        for p in parts
        if p.get("type") == "subagent" and p.get("subagentId") == "worker-0"
    )
    part_attr = paused_part.get("attribution")
    assert isinstance(part_attr, dict)
    # Attributed to the route that actually served, with the disclosure reason.
    assert part_attr["servedTierId"] == fallback_binding.tier.id
    assert part_attr["servedModelLabel"] == fallback_binding.model_label
    assert part_attr["providerId"] == "openai"
    substitution = part_attr.get("substitution")
    assert isinstance(substitution, dict)
    assert substitution["reasonCode"] == "provider_fallback"
    assert float(part_attr["costUsd"]) == pytest.approx(paused_cost)


# --- served-route resume guards (W5 findings 3 + 4) ---------------------------

_WORKER_CALL_ID = "worker-0::fake_worker_cal_0"

# Same worker-HITL prompt, plus one math cue (`probability`) so `route_auto`
# scores it 1 — below the `smart` threshold of 2. Paused on a 7-message thread it
# routes `fast`; on resume the thread has crossed the 8-message `deep_history`
# line, the score reaches 2, and a re-derived route would say `smart`. That drift
# is exactly what the pin has to override.
_WORKER_HITL_PROMPT_DEEP_HISTORY_DRIFT = (
    "DEEP_RESEARCH: TOOL_APPROVE schedule kickoff | sibling housing effects probability"
)
_PRIOR_TURNS_BELOW_DEEP_HISTORY = 7


@contextmanager
def _agentic_disabled() -> Iterator[None]:
    """Kill-switch agentic mid-test; `send_message` reads settings per request."""
    prior = os.environ.get("AGENTIC_ENABLED")
    os.environ["AGENTIC_ENABLED"] = "false"
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("AGENTIC_ENABLED", None)
        else:
            os.environ["AGENTIC_ENABLED"] = prior
        get_settings.cache_clear()


async def _paused_assistant(
    session_factory: async_sessionmaker[AsyncSession], conv_id: str
) -> Message:
    msgs = await _load_messages(session_factory, conv_id)
    return next(
        m for m in msgs if m.role == "assistant" and m.status == "awaiting_approval"
    )


async def _repin_continuation_route(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    message_id: object,
    tool_call_id: str,
    provider_id: str,
    model_id: str,
    tier_id: str | None = None,
    used_fallback: bool | None = None,
) -> None:
    """Rewrite the checkpoint's pinned route identity (and fallback flag).

    This is byte-for-byte what `handler.py` persists when a worker pauses
    (`pausedWorkerUsedFallback` → the fallback binding's tier/provider/model,
    otherwise the primary binding's). The fake provider never actually falls
    back mid-worker, so the durable shape is written directly. `tier_id` /
    `used_fallback` are optional so a checkpoint can be repinned to a whole
    coherent triple — or to a deliberately incoherent one.
    """
    async with session_factory() as session:
        row = await session.get(Message, message_id)
        assert row is not None
        state = dict(row.server_state or {})
        conts = dict(state.get(SERVER_STATE_CONTINUATIONS_KEY) or {})
        blob = dict(conts[tool_call_id])
        blob["providerId"] = provider_id
        blob["modelId"] = model_id
        if tier_id is not None:
            blob["tierId"] = tier_id
        if used_fallback is not None:
            blob["pausedWorkerUsedFallback"] = used_fallback
        conts[tool_call_id] = blob
        state[SERVER_STATE_CONTINUATIONS_KEY] = conts
        row.server_state = state
        await session.commit()


async def _register_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    byok_provider: str | None = None,
) -> None:
    """Turn the bootstrap guest into a registered user, optionally with BYOK.

    `_select_fallback_route` only considers a non-platform provider when the
    caller holds a stored key for it, and it skips BYOK lookup entirely for
    anonymous users.
    """
    async with session_factory() as session:
        row = await session.get(User, user_id)
        assert row is not None
        row.is_anonymous = False
        row.email = f"user-{user_id}@example.test"
        if byok_provider is not None:
            await api_keys_repo.upsert(
                session,
                user_id=UUID(str(user_id)),
                provider=byok_provider,
                raw_api_key=f"sk-test-{byok_provider}-key-000000",
            )
        await session.commit()


async def _resolved_fallback_route(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
    primary_provider_id: str = "fake",
) -> tuple[TierBinding, str] | None:
    """The `(binding, providerId)` a fallback would actually resolve to.

    The fallback binding is not `get_binding(...)`: the `fake` self-fallback
    swaps in `model_id="fake-fallback"`. Tests derive the pinned identity from
    here so they never hardcode a model string.
    """
    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        route = await conversations_route._select_fallback_route(
            tier_id,  # type: ignore[arg-type]
            primary_provider_id,
            get_settings(),
            user=user,
            db=session,
            resolved_api_key=None,
        )
    return None if route is None else (route[0], route[1])


async def _resolved_fallback_provider(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
    primary_provider_id: str = "fake",
) -> str | None:
    route = await _resolved_fallback_route(
        session_factory,
        user_id=user_id,
        tier_id=tier_id,
        primary_provider_id=primary_provider_id,
    )
    return None if route is None else route[1]


async def _pause_worker_run(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conv_id: str,
    client_message_id: str,
    tier_id: str = "smart",
    text: str = _WORKER_HITL_PROMPT,
) -> Message:
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_message_id,
            "tierId": tier_id,
            "text": text,
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][1]["status"] == "awaiting_approval"
    return await _paused_assistant(session_factory, conv_id)


async def _seed_prior_turns(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conv_id: str,
    count: int,
) -> None:
    """Insert `count` plain prior messages so the thread is already deep.

    `created_at` is set explicitly and in the past: SQLite's `CURRENT_TIMESTAMP`
    only has second resolution, so relying on the server default would leave the
    seeds and the real turn tied and order them by random uuid.
    """
    base = datetime.now(UTC) - timedelta(hours=1)
    async with session_factory() as session:
        for index in range(count):
            session.add(
                Message(
                    conversation_id=conv_id,
                    role="user" if index % 2 == 0 else "assistant",
                    parts=[{"type": "text", "text": f"prior turn {index}"}],
                    created_at=base + timedelta(seconds=index),
                )
            )
        await session.commit()


async def test_auto_tier_resume_accepts_the_router_resolved_pin(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """W5/finding 3: an `auto` run pins the CONCRETE tier the router served.

    The guard compared that pin against `body.tierId`, so re-sending `auto` on
    resume — the only thing an Auto-tier client can send — was rejected 400.
    Every auto-tier agentic resume was blocked.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a1000000-0000-0000-0000-000000000001",
        tier_id="auto",
    )
    cont = get_continuation_from_server_state(paused.server_state, _WORKER_CALL_ID)
    assert cont is not None
    # The router resolved `auto` to a concrete tier; that is what got pinned.
    assert cont.tier_id in {"fast", "smart", "pro"}

    resume_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a1000000-0000-0000-0000-000000000002",
            "tierId": "auto",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"


async def test_auto_tier_resume_survives_router_drift_across_the_pause(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """W5/finding 3: `route_auto` is not stable across a pause, the pin is.

    Re-deriving the served route on resume is wrong because the router reads
    conversation depth: a run that paused just under the `deep_history` line
    resumes above it and re-routes one tier up. Comparing the pin against that
    re-derived route 400s a resume nothing is wrong with, so the pin — not a
    fresh routing pass — decides the route for an `auto` resume.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")
    await _seed_prior_turns(
        session_factory, conv_id=conv_id, count=_PRIOR_TURNS_BELOW_DEEP_HISTORY
    )

    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a7000000-0000-0000-0000-000000000001",
        tier_id="auto",
        text=_WORKER_HITL_PROMPT_DEEP_HISTORY_DRIFT,
    )
    cont = get_continuation_from_server_state(paused.server_state, _WORKER_CALL_ID)
    assert cont is not None
    assert cont.tier_id == "fast"

    # The drift this test exists for: with the pause turn on the thread, the
    # router now resolves the same text to a different tier. If a router change
    # ever removes the drift, this assertion fails rather than letting the test
    # quietly stop covering the regression.
    async with session_factory() as session:
        resume_history = await messages_repo.load_history(session, UUID(conv_id))
    assert route_auto(cont.user_text, resume_history).tier_id != cont.tier_id

    resume_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a7000000-0000-0000-0000-000000000002",
            "tierId": "auto",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"
    # Served on the pinned tier, not the re-derived one, and on the PRIMARY
    # route of that tier: the pause was not fallback-flagged, so no fallback
    # binding may have served the resume.
    pinned_binding = get_binding(cont.tier_id)  # type: ignore[arg-type]
    assert pinned_binding is not None
    attribution = resume_frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["servedTierId"] == cont.tier_id
    assert attribution["providerId"] == pinned_binding.provider_id
    assert attribution["servedModelLabel"] == (
        pinned_binding.model_label or pinned_binding.model_id
    )
    # The fake backend serves the canonical DeepSeek binding, so the pinned
    # provider (the selected backend) and the binding's provider are two names
    # for the same primary route.
    assert cont.provider_id in {
        pinned_binding.provider_id,
        get_settings().provider_backend,
    }
    assert cont.model_id == pinned_binding.model_id
    assert attribution.get("substitution") is None


async def test_post_fallback_resume_accepts_the_pinned_fallback_provider(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """W5/finding 3: a worker that paused on fallback pins the FALLBACK provider.

    The resume carries the caller's primary provider preference, so comparing
    the pin against `body.providerId` rejected 400 and blocked every
    post-fallback resume. The pin is a served-route identity, and for a
    fallback-flagged checkpoint the fallback route is the one that serves —
    `_primary_make` hands the worker straight to `fallback_make_stream_for`, so
    the resumed worker's served attribution must name the fallback binding.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    # No BYOK: `fake` is its own fallback with a distinct `fake-fallback` model,
    # so the resume streams deterministically instead of dialing a real provider.
    fallback_route = await _resolved_fallback_route(session_factory, user_id=user_id)
    assert fallback_route is not None
    fallback_binding, fallback_provider = fallback_route
    primary_binding = get_binding("smart", provider_id="fake")
    assert primary_binding is not None
    assert fallback_binding.model_id != primary_binding.model_id

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a2000000-0000-0000-0000-000000000001",
    )
    await _repin_continuation_route(
        session_factory,
        message_id=paused.id,
        tool_call_id=_WORKER_CALL_ID,
        tier_id=fallback_binding.tier.id,
        provider_id=fallback_provider,
        model_id=fallback_binding.model_id,
        used_fallback=True,
    )

    resume_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a2000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            # The caller's primary preference — NOT the route that served the pause.
            "providerId": "fake",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"

    # The terminal frame's top-level attribution names the request's binding; the
    # per-worker attribution on the persisted row is what discloses the route the
    # resumed worker actually streamed on.
    resumed = (await _load_messages(session_factory, conv_id))[-1]
    worker_part = next(
        p
        for p in (resumed.parts or [])
        if isinstance(p, dict)
        and p.get("type") == "subagent"
        and p.get("subagentId") == "worker-0"
    )
    part_attr = worker_part["attribution"]
    assert isinstance(part_attr, dict)
    assert part_attr["servedTierId"] == fallback_binding.tier.id
    assert part_attr["providerId"] == fallback_provider
    assert part_attr["servedModelLabel"] == (
        fallback_binding.model_label or fallback_binding.model_id
    )
    # Only a worker served by `fallback_make_stream_for` carries this disclosure.
    substitution = part_attr.get("substitution")
    assert isinstance(substitution, dict)
    assert substitution["reasonCode"] == "provider_fallback"


async def test_resume_rejects_a_pin_whose_fields_span_two_routes(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A pin is only valid against the route that will actually serve it.

    The pin is one coherent served-route triple, so it has to be matched as one.
    Checking tier, provider and model against three independent sets (primary
    union fallback) let a checkpoint pinned to route A pass once the client
    forced route B and A merely became B's fallback — while
    `paused_worker_used_fallback` (unset here) sent the resume down the PRIMARY
    stream on B.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    # The BYOK key makes `openai` a usable primary route for this caller.
    await _register_user(session_factory, user_id=user_id, byok_provider="openai")
    primary_binding = get_binding("smart", provider_id="openai")
    assert primary_binding is not None
    fallback_route = await _resolved_fallback_route(
        session_factory, user_id=user_id, primary_provider_id="openai"
    )
    assert fallback_route is not None
    fallback_binding, fallback_provider = fallback_route
    # The two routes must genuinely differ, or the mix proves nothing.
    assert fallback_provider != "openai"
    assert fallback_binding.model_id != primary_binding.model_id

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a4000000-0000-0000-0000-000000000001",
    )
    # A checkpoint that says "the FALLBACK route served me" in every field but
    # the flag that decides which stream a resume runs on.
    await _repin_continuation_route(
        session_factory,
        message_id=paused.id,
        tool_call_id=_WORKER_CALL_ID,
        tier_id=fallback_binding.tier.id,
        provider_id=fallback_provider,
        model_id=fallback_binding.model_id,
        used_fallback=False,
    )

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "a4000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "providerId": "openai",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["body"] == (
        "Resume providerId does not match the paused run checkpoint."
    )


async def test_fallback_flagged_resume_rejects_a_primary_route_pin(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The inverse mix: a fallback-served pause cannot resume on a primary pin.

    `paused_worker_used_fallback` sends the resumed worker to
    `fallback_make_stream_for`, so the fallback route — not the primary the
    client asked for — is what the pin has to name.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    await _register_user(session_factory, user_id=user_id, byok_provider="openai")
    primary_binding = get_binding("smart", provider_id="fake")
    assert primary_binding is not None
    # With `fake` as the primary, the BYOK key makes `openai` the fallback.
    assert (
        await _resolved_fallback_provider(session_factory, user_id=user_id) == "openai"
    )

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a5000000-0000-0000-0000-000000000001",
    )
    await _repin_continuation_route(
        session_factory,
        message_id=paused.id,
        tool_call_id=_WORKER_CALL_ID,
        tier_id=primary_binding.tier.id,
        provider_id=primary_binding.provider_id,
        model_id=primary_binding.model_id,
        used_fallback=True,
    )

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "a5000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "providerId": "fake",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["body"] == (
        "Resume providerId does not match the paused run checkpoint."
    )


async def test_resume_rejects_a_model_only_cross_route_mix(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The narrowest cross-route mix: only `model_id` comes from the other route.

    Under `PROVIDER_BACKEND=fake` the primary and its self-fallback share tier
    AND provider and differ in nothing but `model_id` (`fake-fallback`), so the
    tier and provider guards cannot catch this pin — only the model guard can.
    The old set-based check accepted it, because `fake-fallback` was a member of
    `{primary.model_id, fallback.model_id}`; with `paused_worker_used_fallback`
    unset the resume then streamed the PRIMARY model against a checkpoint
    written by the fallback.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    # No BYOK, so the only alternate route is `fake`'s self-fallback.
    fallback_route = await _resolved_fallback_route(session_factory, user_id=user_id)
    assert fallback_route is not None
    fallback_binding, fallback_provider = fallback_route
    primary_binding = get_binding("smart", provider_id="fake")
    assert primary_binding is not None
    # The premise: same tier, same provider, different model.
    assert fallback_binding.tier.id == primary_binding.tier.id
    assert fallback_provider == "fake"
    assert fallback_binding.model_id != primary_binding.model_id

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a6000000-0000-0000-0000-000000000001",
    )
    await _repin_continuation_route(
        session_factory,
        message_id=paused.id,
        tool_call_id=_WORKER_CALL_ID,
        tier_id=fallback_binding.tier.id,
        provider_id=fallback_provider,
        model_id=fallback_binding.model_id,
        used_fallback=False,
    )

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "a6000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "providerId": "fake",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["body"] == (
        "Resume model does not match the paused run checkpoint."
    )


async def test_resume_still_rejects_a_provider_the_served_route_cannot_reach(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """W5/finding 3: a genuine route mismatch still gets 400.

    Same checkpoint as the accepted case, minus the BYOK key that made `openai`
    a reachable fallback. The forced `fake` route resolves to a binding the pin
    does not name, so the resume must stay rejected.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    assert await _resolved_fallback_provider(session_factory, user_id=user_id) != "openai"
    openai_binding = get_binding("smart", provider_id="openai")
    assert openai_binding is not None

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    paused = await _pause_worker_run(
        agentic_client,
        session_factory,
        conv_id=conv_id,
        client_message_id="a3000000-0000-0000-0000-000000000001",
    )
    await _repin_continuation_route(
        session_factory,
        message_id=paused.id,
        tool_call_id=_WORKER_CALL_ID,
        provider_id="openai",
        model_id=openai_binding.model_id,
    )

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "a3000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "providerId": "fake",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["body"] == (
        "Resume providerId does not match the paused run checkpoint."
    )


async def test_agentic_disabled_refuses_a_single_mode_pause(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """W5/finding 4: a single-mode agentic pause is still an agentic pause.

    FL-28 stamps `orchestrationMode` on a single-mode run's pause ledger, but
    that pause carries no worker continuation and is neither a plan nor a
    clarify pause — the three shapes the kill-switch guard looked for. With
    agentic switched off mid-run, the resume slipped past the guard and
    half-ran as a plain tool resume.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a4000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
            "agenticMode": "single",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    paused = await _paused_assistant(session_factory, conv_id)
    call_id = next(
        str(p["id"])
        for p in (paused.parts or [])
        if isinstance(p, dict) and p.get("type") == "tool_call"
    )
    # The pause shape the guard used to miss: mode stamped, nothing else.
    assert get_run_ledger_from_server_state(paused.server_state).orchestration_mode == (
        "single"
    )
    assert get_continuation_from_server_state(paused.server_state, call_id) is None

    with _agentic_disabled():
        resp = await agentic_client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "clientMessageId": "a4000000-0000-0000-0000-000000000002",
                "tierId": "smart",
                "text": "",
                "toolApproval": {"toolCallId": call_id, "decision": "approve"},
            },
        )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "AGENTIC_DISABLED"


async def test_agentic_disabled_still_resumes_a_plain_tool_approval(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """W5 regression guard: the widened kill-switch must not catch plain HITL.

    Tools on, agentic off, no agentic run ever — the pause ledger carries no
    `orchestrationMode` stamp, so the resume has to go through untouched.
    """
    with _agentic_disabled():
        await agentic_client.get("/api/bootstrap")
        user_id = await _current_user_id(session_factory)
        conv_id = await _seed_conversation(session_factory, user_id=user_id)

        pause_frames = await _collect_sse(
            agentic_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "a5000000-0000-0000-0000-000000000001",
                "tierId": "smart",
                "text": "TOOL_APPROVE: schedule a meeting",
            },
        )
        assert pause_frames[-1][1]["status"] == "awaiting_approval"

        paused = await _paused_assistant(session_factory, conv_id)
        ledger = get_run_ledger_from_server_state(paused.server_state)
        assert ledger.orchestration_mode is None

        resume_frames = await _collect_sse(
            agentic_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "a5000000-0000-0000-0000-000000000002",
                "tierId": "smart",
                "text": "",
                "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
            },
        )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"


async def test_registry_settlement_incomplete_surfaces_as_409(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W1's route catch: an incomplete settlement is a 409, never a 500.

    `approval_settlement` raises `ApprovalSettlementIncomplete` when a retry
    arrives while another in-process claim is still executing. The registry
    settle site caught only `ApprovalDecisionConflict`, so that raise escaped as
    an unhandled 500. The raise is forced here so the mapping is verified
    independently of the settlement-side change.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a6000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
        },
    )
    # Settle the approval so the retry reaches the registry settle call site
    # (a still-pending approval defers settlement to the producer instead).
    approve_frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a6000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert approve_frames[-1][1]["status"] == "done"

    # Drop the continuation row so the paused turn is resumable again.
    msgs = await _load_messages(session_factory, conv_id)
    async with session_factory() as session:
        for row in [m for m in msgs if m.role == "assistant" and m.status == "done"]:
            db_row = await session.get(Message, row.id)
            if db_row is not None:
                await session.delete(db_row)
        await session.commit()

    async def _raise_incomplete(*_args: object, **kwargs: object) -> object:
        raise ApprovalSettlementIncomplete(
            tool_call_id=str(kwargs.get("tool_call_id") or "fake_cal_1")
        )

    monkeypatch.setattr(
        conversations_route, "claim_and_settle_approval_outcome", _raise_incomplete
    )

    resp = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "a6000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": "fake_cal_1", "decision": "approve"},
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "APPROVAL_SETTLEMENT_INCOMPLETE"


async def test_producer_settlement_incomplete_surfaces_as_409(
    agentic_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The producer-side twin of the route catch.

    H-007 defers claim/settle for a still-pending approval into
    `stream_and_persist`, so the live-claim registry can raise
    `ApprovalSettlementIncomplete` from there too. Both producer settle sites
    caught only `ApprovalDecisionConflict`, so that raise escaped as an
    unhandled error instead of the 409 the route path returns.
    """
    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="settle",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_msg = Message(
            id=uuid4(),
            conversation_id=convo.id,
            role="user",
            parts=[{"type": "text", "text": "schedule a meeting"}],
            status="done",
        )
        session.add(user_msg)
        await session.flush()
        paused = Message(
            id=uuid4(),
            conversation_id=convo.id,
            role="assistant",
            parts=[
                {
                    "type": "tool_call",
                    "toolCallId": "fake_cal_1",
                    "name": "calendar_create_event",
                    "status": "awaiting_approval",
                    "approvalState": "pending",
                    "input": {"title": "kickoff"},
                }
            ],
            status="awaiting_approval",
            responds_to_message_id=user_msg.id,
        )
        session.add(paused)
        await session.commit()
        user_id = user.id
        conv_id = convo.id
        paused_id = paused.id
        user_msg_id = user_msg.id

    async def _raise_incomplete(*_args: object, **kwargs: object) -> object:
        raise ApprovalSettlementIncomplete(
            tool_call_id=str(kwargs.get("tool_call_id") or "fake_cal_1")
        )

    monkeypatch.setattr(
        handler_mod, "claim_and_settle_approval_outcome", _raise_incomplete
    )

    seed = ResumeToolSeed(
        tool_call_id="fake_cal_1",
        name="calendar_create_event",
        label="Create calendar event",
        decision="approve",
        input={"title": "kickoff"},
        paused_message_id=paused_id,
        pending_settle=True,
    )

    with pytest.raises(AppError) as excinfo:
        async with session_factory() as session:
            async for _ev in handler_mod.stream_and_persist(
                request=_NoDisconnect(),  # type: ignore[arg-type]
                db=session,
                provider=_UnusedProvider(),  # type: ignore[arg-type]
                binding=binding,
                requested_tier_id="smart",
                conversation_id=conv_id,
                user_message_id=user_msg_id,
                user_text="Tool approved: calendar_create_event",
                history=[],
                is_temporary=False,
                user_id=user_id,
                resume_seed=seed,
            ):
                pass

    assert excinfo.value.status_code == 409
    assert excinfo.value.envelope.code == "APPROVAL_SETTLEMENT_INCOMPLETE"


async def test_ac08_resume_does_not_reissue_a_published_citation_id() -> None:
    """AC-08: a citation-only global above the catalog maximum survives the pause.

    Worker 0 published catalog id 1. Worker 1 then wrote `[1]` before its own
    `Sources` arrived, so the allocator handed that marker global 2 and the user
    read `[2]` — an id with no catalog row. The checkpoint carried only the
    catalog, so the resumed namespace reopened at 2 and gave it to the paused
    worker's next new source: the `[2]` already on screen silently changed which
    source it meant, and the pause-turn mapping came back as a different id.
    """
    import asyncio
    from collections.abc import AsyncIterator as _AsyncIterator

    from app.agentic.continuation import parse_continuation
    from app.agentic.orchestrator import _resume_worker_continuation, run_orchestrator
    from app.config import Settings
    from app.providers.protocol import (
        AnswerDelta,
        AwaitingApproval,
        Complete,
        ProviderEvent,
        Sources,
        ToolCall,
        ToolResult,
        UsageUpdate,
    )
    from app.search.protocol import SourceItem

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_PLAN_APPROVAL=False,
        AGENTIC_VERIFIER=False,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    worker0_sourced = asyncio.Event()

    def _pause_turn(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> _AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:

                async def _w0() -> _AsyncIterator[ProviderEvent]:
                    yield Sources(
                        items=[
                            SourceItem(
                                id=1, title="alpha source", url="https://alpha.example"
                            )
                        ]
                    )
                    # The remap runs as the worker consumes this stream, so the
                    # gate below releases worker 1 only once global 1 is taken.
                    worker0_sourced.set()
                    yield AnswerDelta(text="alpha rests on [1].")
                    yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

                return _w0()
            if "DEEP_RESEARCH_WORKER:1:" in prompt:

                async def _w1() -> _AsyncIterator[ProviderEvent]:
                    await worker0_sourced.wait()
                    # Cites before its own Sources event: citation-only global.
                    yield AnswerDelta(text="beta leans on [1].")
                    yield UsageUpdate(input_tokens=1, output_tokens=1)
                    yield ToolCall(
                        id="cal-w1",
                        name="calendar_create_event",
                        label="Create calendar event",
                        status="awaiting_approval",
                        approval_state="pending",
                        input={"title": "beta"},
                    )
                    yield AwaitingApproval(tool_call_id="cal-w1")

                return _w1()

            async def _agg() -> _AsyncIterator[ProviderEvent]:  # pragma: no cover
                yield AnswerDelta(text="agg")
                yield Complete(usage=UsageUpdate())

            return _agg()

        return _make

    pause_events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_pause_turn,
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: alpha | beta",
            cost_for_usage=lambda u: 0.01,
        )
    ]
    pause = next(e for e in pause_events if isinstance(e, AwaitingApproval))
    beta_text = "".join(
        e.text
        for e in pause_events
        if isinstance(e, AnswerDelta) and e.subagent_id == "worker-1"
    )
    # What the user has already read: a citation above every catalog id.
    assert beta_text == "beta leans on [2]."
    assert pause.continuation is not None
    checkpoint = parse_continuation(pause.continuation)
    assert checkpoint is not None
    assert [item.id for item in checkpoint.source_catalog] == [1]
    assert checkpoint.source_next_id == 3

    def _resume_turn(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> _AsyncIterator[ProviderEvent]:
            async def _gen() -> _AsyncIterator[ProviderEvent]:
                # A source the paused worker had not published before: a NEW
                # local ordinal, which must not take the id `[2]` already means.
                yield Sources(
                    items=[
                        SourceItem(
                            id=2, title="beta follow-up", url="https://beta2.example"
                        )
                    ]
                )
                yield AnswerDelta(text=" Now [1] and [2] agree.")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    resumed = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_resume_turn,
            settings=settings,
            cost_for_usage=lambda u: 0.01,
            continuation=checkpoint,
            resume_tool_result=ToolResult(
                tool_call_id="cal-w1",
                name="calendar_create_event",
                status="succeeded",
                approval_state="approved",
                output={"ok": True},
            ),
            server_approved_call_ids=set(),
        )
    ]
    worker_sources = next(
        e for e in resumed if isinstance(e, Sources) and e.subagent_id == "worker-1"
    )
    assert [(i.id, i.title) for i in worker_sources.items] == [(3, "beta follow-up")]
    resumed_text = "".join(
        e.text
        for e in resumed
        if isinstance(e, AnswerDelta) and e.subagent_id == "worker-1"
    )
    # `[1]` still means the global the pause turn rendered; the new local gets 3.
    assert resumed_text == " Now [2] and [3] agree."
    merged = next(
        e for e in resumed if isinstance(e, Sources) and e.subagent_id != "worker-1"
    )
    assert [(i.id, i.title) for i in merged.items] == [
        (1, "alpha source"),
        (3, "beta follow-up"),
    ]


async def test_ac08_v1_checkpoint_restores_above_citations_in_surviving_answers() -> None:
    """AC-08: a v1 pause row still holds its rendered citations.

    The allocator state ships in v2 blobs, but v1 is a supported version and
    decodes with those fields empty — so the rendered-but-uncataloged citation is
    back. Probed directly: a v1 blob with catalog id 1 and `partialAnswer`
    `"orphan [2]"` decoded fine and then handed id 2 to the resumed worker's new
    source, retargeting the `[2]` the user had already read. Surviving answer text
    is the only remaining record of those ids, so it sets the floor — the paused
    draft AND the finished siblings' answers, since a sibling's citations were
    rendered on the pause turn too.
    """
    from collections.abc import AsyncIterator as _AsyncIterator
    from typing import Any as _Any

    from app.agentic.continuation import parse_continuation
    from app.agentic.orchestrator import _resume_worker_continuation
    from app.config import Settings
    from app.providers.protocol import (
        AnswerDelta,
        Complete,
        ProviderEvent,
        Sources,
        ToolResult,
        UsageUpdate,
    )
    from app.search.protocol import SourceItem

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_PLAN_APPROVAL=False,
        AGENTIC_VERIFIER=False,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )

    def _v1_blob(*, partial_answer: str, sibling_answer: str) -> dict[str, _Any]:
        """A pause row as older builds wrote it: no `version`, no allocator state."""
        return {
            "phase": "worker",
            "pausedSubagentId": "worker-1",
            "userText": "DEEP_RESEARCH: alpha | beta",
            "plan": ["alpha", "beta"],
            "completedWorkers": [
                {
                    "subagentId": "worker-0",
                    "subQuestion": "alpha",
                    "answer": sibling_answer,
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                    "costUsd": 0.01,
                    "outcome": "succeeded",
                    "sourceIds": ["1"],
                }
            ],
            "plannerUsage": {"inputTokens": 1, "outputTokens": 1},
            "plannerCostUsd": 0.01,
            "pausedWorkerIndex": 1,
            "pausedSubQuestion": "beta",
            "partialAnswer": partial_answer,
            "emittedAnswerChars": len(partial_answer),
            # Ids `int()` cannot read at all — a digit by `str.isdigit()` and an
            # over-long digit string — decode as valid and must not raise the resume.
            "sourceIds": ["²", "9" * 4400],
            "sourceCatalog": [
                {"id": 1, "title": "alpha source", "url": "https://alpha.example"}
            ],
            "orchestrationMode": "deep_research",
        }

    def _resume_turn(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> _AsyncIterator[ProviderEvent]:
            async def _gen() -> _AsyncIterator[ProviderEvent]:
                yield Sources(
                    items=[
                        SourceItem(
                            id=1, title="beta follow-up", url="https://beta2.example"
                        )
                    ]
                )
                yield AnswerDelta(text=" done.")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    async def _resumed_source_ids(blob: dict[str, _Any]) -> list[tuple[int, str]]:
        checkpoint = parse_continuation(blob)
        assert checkpoint is not None
        # The v1 shape is exactly what makes this hard: no allocator state.
        assert checkpoint.source_allocations == ()
        assert checkpoint.source_next_id == 0
        events = [
            ev
            async for ev in _resume_worker_continuation(
                make_stream_for=_resume_turn,
                settings=settings,
                cost_for_usage=lambda u: 0.01,
                continuation=checkpoint,
                resume_tool_result=ToolResult(
                    tool_call_id="cal-w1",
                    name="calendar_create_event",
                    status="succeeded",
                    approval_state="approved",
                    output={"ok": True},
                ),
                server_approved_call_ids=set(),
            )
        ]
        worker_sources = next(
            e for e in events if isinstance(e, Sources) and e.subagent_id == "worker-1"
        )
        return [(item.id, item.title) for item in worker_sources.items]

    # The reported probe: the paused draft carries the citation-only `[2]`.
    assert await _resumed_source_ids(
        _v1_blob(partial_answer="orphan [2]", sibling_answer="alpha rests on [1].")
    ) == [(3, "beta follow-up")]
    # And a finished sibling's answer counts the same — its `[4]` was rendered too.
    assert await _resumed_source_ids(
        _v1_blob(partial_answer="orphan [2]", sibling_answer="alpha also cites [4].")
    ) == [(5, "beta follow-up")]
