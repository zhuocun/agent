"""Plan-approval HITL for deep-research (M3, T6).

Drives the FAKE provider behind `TOOLS_ENABLED=true`, `AGENTIC_ENABLED=true`,
and `AGENTIC_PLAN_APPROVAL=true`. Covers:
- A fresh `deep_research` turn PAUSES before any fan-out, surfacing the plan +
  estimate on a pseudo `agentic_plan_approval` tool call and ending the turn in
  the `awaiting_approval` terminal (no workers spawned yet).
- A `toolApproval` resume that APPROVES the plan re-runs the orchestrator and
  fans out workers + aggregator to a `done` terminal.
- A `toolApproval` resume that DENIES the plan skips the fan-out entirely and
  finalizes a labeled (non-error) "declined" synthesis.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic import PLAN_APPROVAL_CALL_ID, PLAN_APPROVAL_TOOL_NAME
from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db

pytestmark = pytest.mark.asyncio


# Fixtures ---------------------------------------------------------------------


@pytest.fixture
def agentic_env() -> Iterator[None]:
    """Tool-calling + agentic + plan-approval flags ON for the test."""
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "true",
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


async def _grant_pro(
    session_factory: async_sessionmaker[AsyncSession], *, user_id: object
) -> None:
    """Grant the test user an active Pro entitlement (deep_research is gated)."""
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


def _names(frames: list[tuple[str, dict[str, object]]]) -> list[str]:
    return [name for name, _ in frames]


def _answer(frames: list[tuple[str, dict[str, object]]]) -> str:
    return "".join(str(d.get("text", "")) for n, d in frames if n == "answer_delta")


_PROMPT = "DEEP_RESEARCH: causes of inflation | effects on housing"


async def _pause_on_plan(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, list[tuple[str, dict[str, object]]]]:
    """Drive a fresh deep-research turn to the plan-approval pause; return convo + frames."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": _PROMPT,
            "agenticMode": "deep_research",
        },
    )
    return conv_id, frames


# 1. Pause before fan-out ------------------------------------------------------


async def test_plan_approval_pauses_before_fanout(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert get_settings().agentic_plan_approval is True
    conv_id, frames = await _pause_on_plan(agentic_client, session_factory)

    names = _names(frames)
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "awaiting_approval"

    # The planner subagent paused the run; NO worker fan-out happened yet.
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert started_ids == {"planner"}
    assert not any(sid.startswith("worker-") for sid in started_ids)
    assert "aggregator" not in started_ids

    # The plan + estimate are surfaced on the pseudo plan-approval tool call.
    tool_calls = [d for n, d in frames if n == "tool_call"]
    assert len(tool_calls) == 1
    plan_call = tool_calls[0]
    assert plan_call["id"] == PLAN_APPROVAL_CALL_ID
    assert plan_call["name"] == PLAN_APPROVAL_TOOL_NAME
    assert plan_call["status"] == "awaiting_approval"
    assert plan_call["approvalState"] == "pending"
    plan_input = plan_call["input"]
    assert isinstance(plan_input, dict)
    assert plan_input["plan"] == ["causes of inflation", "effects on housing"]
    assert float(plan_input["estimatedCostUsd"]) > 0.0

    # The live cost meter carries the estimate against the cap.
    run_cost = next(d for n, d in frames if n == "run_cost")
    assert float(run_cost["subtotalUsd"]) > 0.0
    assert run_cost["capUsd"] == get_settings().agentic_run_budget_usd

    # The terminal attribution is an ESTIMATE (no Complete fired before the pause).
    terminal = frames[-1][1]
    attribution = terminal["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["costConfidence"] == "estimate"

    # The paused assistant row persists the pending plan tool_call so the resume
    # route can re-validate it.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].status == "awaiting_approval"
    parts = [p for p in assistant[0].parts if isinstance(p, dict)]
    plan_part = next(
        p for p in parts if p.get("type") == "tool_call" and p.get("id") == PLAN_APPROVAL_CALL_ID
    )
    assert plan_part["status"] == "awaiting_approval"
    assert plan_part["approvalState"] == "pending"


# 2. Approve resumes the fan-out ----------------------------------------------


async def test_plan_approval_approve_resumes_fanout(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id, _ = await _pause_on_plan(agentic_client, session_factory)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": PLAN_APPROVAL_CALL_ID,
                "decision": "approve",
            },
        },
    )

    names = _names(frames)
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    # Approval fans out to the workers + aggregator and synthesizes.
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert started_ids == {"worker-0", "worker-1", "aggregator"}
    full_answer = _answer(frames)
    assert "Synthesis of 2 findings" in full_answer
    assert "causes of inflation" in full_answer
    assert "effects on housing" in full_answer

    # A second assistant row (done) now follows the paused one.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 2
    assert assistant[0].status == "awaiting_approval"
    assert assistant[1].status == "done"


# 3. Deny declines the run -----------------------------------------------------


async def test_plan_approval_deny_declines_run(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id, _ = await _pause_on_plan(agentic_client, session_factory)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": PLAN_APPROVAL_CALL_ID,
                "decision": "deny",
            },
        },
    )

    names = _names(frames)
    assert names[-1] == "terminal"
    # A decline is a graceful, non-error terminal.
    assert frames[-1][1]["status"] == "done"

    # No workers ran; only the aggregator finalized a labeled declined synthesis.
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert started_ids == {"aggregator"}
    assert not any(sid.startswith("worker-") for sid in started_ids)
    full_answer = _answer(frames)
    assert "declined" in full_answer.lower()
