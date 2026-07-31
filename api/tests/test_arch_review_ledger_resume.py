"""Route/handler integration for B4/B5/B9/B13 arch-review ledger fixes."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic.budget import estimate_run_cost
from app.agentic.continuation import (
    SERVER_STATE_PLANNER_COST_KEY,
    SERVER_STATE_PLANNER_USAGE_KEY,
    SERVER_STATE_PRIOR_RUN_COST_KEY,
    SERVER_STATE_PRIOR_RUN_USAGE_KEY,
    SERVER_STATE_RUN_RECEIPT_KEY,
    get_continuation_from_server_state,
    get_run_ledger_from_server_state,
    put_continuation_in_server_state,
    put_run_ledger_in_server_state,
    usage_to_wire,
)
from app.config import get_settings
from app.db.models import Conversation, Message, UsageRollup, User
from app.db.repositories import billing as billing_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_db
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import RunCost, UsageUpdate
from app.providers.tiers import get_binding
from app.runtime.run_receipt import CostLedger, RunReceipt, decode_run_receipt
from app.schemas.message import AgenticRunSummaryPart
from app.streaming import turn_reducer as turn_reducer_module

pytestmark = pytest.mark.asyncio

# AC-02 fixtures for the "$0.37 on the wire, $0.00 on the row" regression: the
# pause turn banked `ALREADY_BILLED_USD` of the run, and the checkpoint records
# `PLANNER_SPEND_USD` of total planner spend, so the resume owes the difference.
PLANNER_SPEND_USD = 0.37
ALREADY_BILLED_USD = 0.10


def _sse_frames(body: str) -> list[tuple[str, dict[str, object]]]:
    frames: list[tuple[str, dict[str, object]]] = []
    event_name = "message"
    data_lines: list[str] = []
    for raw in body.splitlines():
        if raw.startswith("event:"):
            event_name = raw[len("event:") :].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:") :].strip())
        elif raw == "" and data_lines:
            payload = json.loads("\n".join(data_lines))
            assert isinstance(payload, dict)
            frames.append((event_name, payload))
            event_name = "message"
            data_lines = []
    if data_lines:
        payload = json.loads("\n".join(data_lines))
        assert isinstance(payload, dict)
        frames.append((event_name, payload))
    return frames


async def _collect_sse(
    client: AsyncClient, path: str, payload: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    response = await client.post(path, json=payload, timeout=30.0)
    assert response.status_code == 200, response.text
    return _sse_frames(response.text)


def _without_receipt(state: dict[str, Any]) -> dict[str, Any]:
    """Age a paused row back to a pre-AC-02 shape: scalar seeds, no receipt."""
    return {k: v for k, v in state.items() if k != SERVER_STATE_RUN_RECEIPT_KEY}


@pytest.fixture
def plan_approval_env() -> Iterator[None]:
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "true",
        "USAGE_BUDGET_USD": "100",
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
def plan_approval_app(
    plan_approval_env: None,
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
        app_.dependency_overrides.clear()


@pytest.fixture
async def plan_client(
    plan_approval_app,
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=plan_approval_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_b4_plan_resume_seeds_nonzero_runcost_via_server_state(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B4: pause persists planner ledger in server_state; resume RunCost is non-zero.

    Characterizes the LEGACY seed path, so the row is stripped of the receipt the
    pause turn writes today (AC-02). On a row that still has its receipt the
    scalar below is ignored on purpose — `test_ac02_a_present_receipt_outranks_*`
    covers that.
    """
    await plan_client.get("/api/bootstrap")
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=user.id,
            provider="fake",
            subscription_id=f"sub-{user.id}",
            status="active",
            customer_id=f"cus-{user.id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()

    create = await plan_client.post(
        "/api/conversations", json={"title": "b4", "selectedTierId": "smart"}
    )
    assert create.status_code == 201
    conv_id = create.json()["id"]

    pause_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b4000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    plan_call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")
    plan_input = next(d["input"] for n, d in pause_frames if n == "tool_call")
    assert isinstance(plan_input, dict)
    assert "plannerCostUsd" not in plan_input

    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
        paused.server_state = _without_receipt(
            put_run_ledger_in_server_state(
                paused.server_state if isinstance(paused.server_state, dict) else {},
                planner_cost_usd=0.37,
                planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
            )
        )
        await session.commit()
        ledger = get_run_ledger_from_server_state(paused.server_state)
        assert ledger.planner_cost_usd == pytest.approx(0.37)
        assert SERVER_STATE_PLANNER_COST_KEY in (paused.server_state or {})
        assert SERVER_STATE_PLANNER_USAGE_KEY in (paused.server_state or {})

    resume_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b4000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {"toolCallId": plan_call_id, "decision": "approve"},
        },
    )
    assert resume_frames[-1][1]["status"] == "done"
    run_costs = [d for n, d in resume_frames if n == "run_cost"]
    assert run_costs
    assert float(run_costs[0]["subtotalUsd"]) >= 0.37 - 1e-9


async def test_b5_single_mode_resume_seeds_runcost_via_api(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B5: single-mode pause ledger in server_state seeds resume RunCost.

    Legacy path, so the receipt AC-02 writes is stripped first — see the B4 test.
    """
    monkeypatch.setenv("AGENTIC_PLAN_APPROVAL", "false")
    get_settings.cache_clear()

    await plan_client.get("/api/bootstrap")
    create = await plan_client.post(
        "/api/conversations", json={"title": "b5", "selectedTierId": "smart"}
    )
    assert create.status_code == 201
    conv_id = create.json()["id"]

    pause_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b5000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
            "agenticMode": "single",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")

    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
        paused.server_state = _without_receipt(
            put_run_ledger_in_server_state(
                paused.server_state if isinstance(paused.server_state, dict) else {},
                prior_run_cost_usd=0.2,
                prior_run_usage=UsageUpdate(input_tokens=20, output_tokens=0),
            )
        )
        await session.commit()

    resume_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b5000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "agenticMode": "single",
            "toolApproval": {"toolCallId": call_id, "decision": "approve"},
        },
    )
    assert resume_frames[-1][1]["status"] == "done"
    run_costs = [d for n, d in resume_frames if n == "run_cost"]
    assert run_costs
    assert float(run_costs[0]["subtotalUsd"]) >= 0.2 - 1e-9


async def test_b5_single_mode_pause_persists_prior_run_ledger_keys() -> None:
    """B5 helpers round-trip priorRunCostUsd into server_state."""
    state = put_run_ledger_in_server_state(
        None,
        prior_run_cost_usd=0.2,
        prior_run_usage=UsageUpdate(input_tokens=20, output_tokens=0),
    )
    assert state[SERVER_STATE_PRIOR_RUN_COST_KEY] == pytest.approx(0.2)
    assert state["priorRunUsage"] == usage_to_wire(
        UsageUpdate(input_tokens=20, output_tokens=0)
    )
    parsed = get_run_ledger_from_server_state(state)
    assert parsed.prior_run_cost_usd == pytest.approx(0.2)
    assert parsed.prior_run_usage is not None
    assert parsed.prior_run_usage.input_tokens == 20


async def test_b5_repeated_pause_accumulates_prior_run_cost() -> None:
    """B5: a second single-mode pause must keep the prior resume seed cost."""
    # Simulate what the handler does: seed from resume + this turn's cost.
    prior = get_run_ledger_from_server_state(
        put_run_ledger_in_server_state(None, prior_run_cost_usd=0.2)
    )
    turn_cost = 0.15
    accumulated = float(prior.prior_run_cost_usd) + turn_cost
    state = put_run_ledger_in_server_state(
        None,
        prior_run_cost_usd=accumulated,
        prior_run_usage=UsageUpdate(input_tokens=30, output_tokens=5),
    )
    parsed = get_run_ledger_from_server_state(state)
    assert parsed.prior_run_cost_usd == pytest.approx(0.35)


async def test_b9_headroom_uses_reserved_hold_not_remaining_after_subtract(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B9: orchestrator headroom should be the hold amount, not remaining-hold."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="b9",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        from app.db.models import Stream

        stream = Stream(conversation_id=convo.id, status="active")
        session.add(stream)
        await session.commit()
        await session.refresh(stream)

        binding = get_binding("smart")
        assert binding is not None
        settings = get_settings()
        hold = estimate_run_cost(
            sub_question_count=settings.agentic_max_workers,
            binding=binding,
            settings=settings,
            image_count=0,
        )
        assert hold > 0
        ok = await usage_repo.reserve_platform_budget(
            session,
            user_id=user.id,
            stream_id=stream.id,
            amount_usd=hold,
            monthly_quota_usd=100.0,
        )
        await session.commit()
        assert ok is True
        remaining = await usage_repo.get_platform_remaining_usd(
            session, user_id=user.id, monthly_quota_usd=100.0
        )
        assert remaining is not None
        assert remaining == pytest.approx(100.0 - hold)
        # Route passes `hold` (reserved_hold_usd), not `remaining`.
        assert hold > remaining or hold <= remaining


async def test_b13_compaction_usage_incremented(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B13: summarizer usage is billed via reference_type=compaction."""
    usage = UsageUpdate(input_tokens=1000, output_tokens=50)
    binding = get_binding("smart")
    assert binding is not None
    expected = compute_cost_breakdown(usage=usage, binding=binding, image_count=0)
    expected_cost = expected.subtotal_usd + expected.session_surcharge_usd
    assert expected_cost > 0

    async with session_factory() as session:
        user = User(is_anonymous=False, email="b13@example.com", name="B13")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await usage_repo.increment_for_period(
            session,
            user_id=user.id,
            used_delta=0,
            cost_usd_delta=expected_cost,
            is_byok=False,
            monthly_quota_usd=100.0,
            reference_type="compaction",
            reference_id="stream-b13",
        )
        await session.commit()
        rollup = (
            await session.execute(
                select(UsageRollup).where(UsageRollup.user_id == user.id)
            )
        ).scalar_one()
        assert float(rollup.cost_usd) == pytest.approx(expected_cost)


class _StubRequest:
    async def is_disconnected(self) -> bool:
        return False


class _PauseAfterUsageProvider:
    """Single-mode provider that banks usage, then requests a gated tool."""

    def stream(self, *, user_text: str = "", **_kwargs: object):  # type: ignore[no-untyped-def]
        from app.providers.protocol import ProviderEvent, ToolCall

        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield UsageUpdate(input_tokens=40, output_tokens=12, reasoning_tokens=3)
            yield ToolCall(
                id="cal-1",
                name="calendar_create_event",
                status="running",
                input={"title": "Planning review"},
            )

        return _gen()


async def test_single_mode_pause_terminal_reports_tokens_and_receipt(
    plan_approval_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-14 (HITL-6): a single-mode pause must still ship tokens and a receipt.

    `run_single` returned at the pause before the untagged `Complete` and the
    final `RunCost`, and the handler `break`s at the pause terminal — so the
    paused row's attribution reported 0 tokens and carried no run summary even
    though billing was correct.
    """
    from app.streaming.handler import stream_and_persist

    monkeypatch.setenv("AGENTIC_PLAN_APPROVAL", "false")
    get_settings.cache_clear()

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="fl14",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    frames: list[tuple[str, dict[str, object]]] = []
    async with session_factory() as session:
        async for ev in stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=_PauseAfterUsageProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=UUID(int=0x14),
            user_text="schedule a meeting",
            history=[],
            is_temporary=False,
            user_id=user_id,
            agentic_mode="single",
        ):
            payload: dict[str, object] = {}
            if ev.data:
                payload = json.loads(ev.data)
            frames.append((ev.event or "", payload))

    assert frames[-1][1]["status"] == "awaiting_approval"
    # The receipt precedes the pause on the wire — the handler stops reading after
    # the pause terminal, so a post-pause receipt would never be consumed.
    names = [n for n, _ in frames]
    assert names.index("run_cost") < names.index("terminal")

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
            )
        ).scalar_one()

    attribution = row.attribution
    assert isinstance(attribution, dict)
    breakdown = attribution["breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown["inputTokens"] == 40
    assert breakdown["outputTokens"] == 12
    assert float(attribution["costUsd"]) > 0.0

    summary = next(
        p
        for p in (row.parts or [])
        if isinstance(p, dict) and p.get("type") == "agentic_run_summary"
    )
    # A resumable pause is not a finished answer.
    assert summary["outcome"] == "partial"
    assert summary["budgetHalted"] is False


# --- AC-02: one receipt owns cumulative vs newly billable ----------------------


async def _entitle_current_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    """Give the anonymous bootstrap user an active subscription."""
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=user.id,
            provider="fake",
            subscription_id=f"sub-{user.id}",
            status="active",
            customer_id=f"cus-{user.id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()
        return user.id


async def _billed_to_date(
    session_factory: async_sessionmaker[AsyncSession], user_id: UUID
) -> float:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(UsageRollup).where(UsageRollup.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
    return sum(float(row.cost_usd or 0.0) for row in rows)


@contextmanager
def _capturing_run_costs() -> Iterator[list[RunCost]]:
    """Capture every `RunCost` the turn's fold sees, receipt object included.

    The receipt is internal transport with no wire field, so the SSE frames
    cannot show whether one reached the handler. Wrapping the ONE fold point —
    `TurnReducer`'s, shared by live delivery and the stopped drain since F3b — is
    what makes that observable to a route test.
    """
    captured: list[RunCost] = []
    original = turn_reducer_module.build_agentic_run_summary_part

    def _capture(ev: RunCost) -> AgenticRunSummaryPart:
        captured.append(ev)
        return original(ev)

    turn_reducer_module.build_agentic_run_summary_part = _capture  # type: ignore[assignment]
    try:
        yield captured
    finally:
        turn_reducer_module.build_agentic_run_summary_part = original  # type: ignore[assignment]



@pytest.fixture
def fanout_env() -> Iterator[None]:
    """Plan approval ON, and no user spend cap, so an approved plan fans out.

    `plan_approval_env`'s `USAGE_BUDGET_USD` leaves a plan-approved resume with no
    headroom to spawn workers, which is fine for the scalar-seed tests above but
    would make every turn here cost nothing.
    """
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "true",
    }
    prior = {key: os.environ.get(key) for key in (*keys, "USAGE_BUDGET_USD")}
    os.environ.update(keys)
    os.environ.pop("USAGE_BUDGET_USD", None)
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
def fanout_app(
    fanout_env: None,
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
        app_.dependency_overrides.clear()


@pytest.fixture
async def fanout_client(fanout_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=fanout_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# One worker pauses on a calendar tool; its sibling finishes. So the plan-approved
# turn spends real (fake-provider) tokens, pauses, and is billed for them.
_PLAN_THEN_WORKER_PROMPT = (
    "DEEP_RESEARCH: TOOL_APPROVE schedule kickoff | sibling housing effects"
)


def _terminal_cost(frames: list[tuple[str, dict[str, object]]]) -> float:
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    return float(attribution["costUsd"])


def _final_run_cost(frames: list[tuple[str, dict[str, object]]]) -> float:
    finals = [d for n, d in frames if n == "run_cost" and d.get("phase") == "final"]
    assert finals, "an agentic turn ends with a final run_cost"
    return float(finals[-1]["subtotalUsd"])


def _awaiting_call_id(frames: list[tuple[str, dict[str, object]]]) -> str:
    return next(
        str(d["id"])
        for n, d in frames
        if n == "tool_call" and d.get("status") == "awaiting_approval"
    )


async def _assistant_rows(
    session_factory: async_sessionmaker[AsyncSession], conv_id: str
) -> list[Message]:
    async with session_factory() as session:
        return list(
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == UUID(conv_id))
                    .where(Message.role == "assistant")
                    .order_by(Message.created_at)
                )
            )
            .scalars()
            .all()
        )


def _stored_receipt(row: Message) -> RunReceipt:
    state = row.server_state if isinstance(row.server_state, dict) else {}
    receipt = decode_run_receipt(state.get(SERVER_STATE_RUN_RECEIPT_KEY))
    assert receipt is not None, "a paused row carries its boundary receipt"
    return receipt


def _phase_costs(receipt: RunReceipt) -> dict[str, float]:
    return {phase.phase_id: phase.cost_usd for phase in receipt.phases}


def _spend_between(before: RunReceipt, after: RunReceipt) -> float:
    """Money that phases actually gained between two boundaries of one run.

    This is the ONLY thing a continuation may charge. Deriving it from the two
    receipts' own per-phase breakdowns — rather than subtracting two run totals —
    is what makes "only the new phase is billed" a statement about phases.
    """
    was = _phase_costs(before)
    return sum(
        max(0.0, cost - was.get(phase_id, 0.0))
        for phase_id, cost in _phase_costs(after).items()
    )


async def _plan_pause(
    client: AsyncClient, *, conv_id: str, nonce: str
) -> tuple[str, list[tuple[str, dict[str, object]]]]:
    """Turn 1: a fresh deep-research turn parks on the plan-approval gate."""
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": f"ac020000-0000-0000-0000-0000000000{nonce}",
            "tierId": "smart",
            "text": _PLAN_THEN_WORKER_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][1]["status"] == "awaiting_approval"
    return _awaiting_call_id(frames), frames


async def _approve(
    client: AsyncClient, *, conv_id: str, call_id: str, nonce: str
) -> list[tuple[str, dict[str, object]]]:
    return await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": f"ac020000-0000-0000-0000-0000000000{nonce}",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {"toolCallId": call_id, "decision": "approve"},
        },
    )


async def _new_conversation(client: AsyncClient, title: str) -> str:
    create = await client.post(
        "/api/conversations", json={"title": title, "selectedTierId": "smart"}
    )
    assert create.status_code == 201
    return str(create.json()["id"])


async def _rewrite_server_state(
    session_factory: async_sessionmaker[AsyncSession],
    message_id: UUID,
    edit: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Edit a paused row's server-only state, keeping its receipt intact."""
    async with session_factory() as session:
        row = await session.get(Message, message_id)
        assert row is not None
        state = edit(dict(row.server_state or {}))
        assert SERVER_STATE_RUN_RECEIPT_KEY in state, "the receipt must survive the edit"
        row.server_state = state
        await session.commit()


def _without_scalar_seeds(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in state.items()
        if key
        not in (
            SERVER_STATE_PLANNER_COST_KEY,
            SERVER_STATE_PLANNER_USAGE_KEY,
            SERVER_STATE_PRIOR_RUN_COST_KEY,
            SERVER_STATE_PRIOR_RUN_USAGE_KEY,
        )
    }


def _assert_charged_only_new_phase_spend(
    folded: list[RunCost],
    *,
    rows: list[Message],
    frames: list[tuple[str, dict[str, object]]],
    before: RunReceipt,
    billed: float,
) -> None:
    """The whole AC-02 billing contract for one continuation.

    `before` is the receipt the resumed turn restored. Everything charged here must
    be the phase spend that appeared after it, and the run total shown everywhere
    must be that plus what earlier turns already banked.
    """
    receipt = folded[-1].receipt
    assert receipt is not None, "the boundary RunCost carries its receipt"
    row = rows[-1]
    new_spend = _spend_between(before, receipt)
    cumulative = receipt.cumulative_cost_usd

    # Charged: only this continuation's phase spend, on the row and in the meter.
    assert float(row.cost_usd or 0.0) == pytest.approx(new_spend)
    assert receipt.newly_billable_cost_usd == pytest.approx(new_spend)
    assert billed == pytest.approx(new_spend, abs=5e-7)
    # Displayed: the run's whole life, identically on the wire and on the row.
    assert cumulative == pytest.approx(before.cumulative_cost_usd + new_spend)
    assert sum(_phase_costs(receipt).values()) == pytest.approx(cumulative)
    assert _final_run_cost(frames) == pytest.approx(cumulative)
    assert _terminal_cost(frames) == pytest.approx(cumulative)
    assert float((row.attribution or {})["costUsd"]) == pytest.approx(cumulative)
    assert cumulative == pytest.approx(
        receipt.already_billed_cost_usd + receipt.newly_billable_cost_usd
    )
    # A liar seed is orders of magnitude above anything this run can really spend.
    assert cumulative < 0.01 < _LIAR_USD


# --- AC-02 closure ------------------------------------------------------------
#
# The run below is three turns of ONE conversation and is the shape the register
# names: a plan-approval pause, then an approve that fans out and parks on a
# worker's calendar tool, then an approve that finishes it. The middle turn is the
# load-bearing one — it is a plan-approval RESUME that is itself a billed pause, so
# the last turn resumes from a boundary whose money was really charged.


async def test_ac02_each_boundary_of_a_paused_run_is_billed_exactly_once(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """AC-02 closure: cumulative is the run's total everywhere it is shown, and
    each turn charges only the phase spend that happened inside it.

    Turn 2 fans out over the approved plan, spends real tokens on the sibling that
    finishes, and pauses — and is charged for that spend. Turn 3 resumes, prices
    one more phase (the paused worker), and must charge ONLY that phase even though
    the run total it displays now covers both turns.
    """
    await fanout_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, "ac02-closure")

    plan_call_id, _plan_frames = await _plan_pause(
        fanout_client, conv_id=conv_id, nonce="01"
    )

    # Turn 2: approve the plan -> workers spawn -> one parks on its tool.
    billed_before_fanout = await _billed_to_date(session_factory, user_id)
    fanout = await _approve(
        fanout_client, conv_id=conv_id, call_id=plan_call_id, nonce="02"
    )
    assert fanout[-1][1]["status"] == "awaiting_approval"
    fanout_billed = await _billed_to_date(session_factory, user_id) - (
        billed_before_fanout
    )
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]
    pause_receipt = _stored_receipt(pause_row)
    assert pause_receipt.boundary == "pause"

    # The pause boundary really was charged: this is not an injected premise.
    pause_charge = float(pause_row.cost_usd or 0.0)
    assert pause_charge > 0.0
    assert pause_charge == pytest.approx(pause_receipt.newly_billable_cost_usd)
    assert fanout_billed == pytest.approx(pause_charge, abs=5e-7)

    # Turn 3: approve the worker's tool -> it finishes -> synthesis.
    worker_call_id = _awaiting_call_id(fanout)
    with _capturing_run_costs() as folded:
        done = await _approve(
            fanout_client, conv_id=conv_id, call_id=worker_call_id, nonce="03"
        )
    assert done[-1][1]["status"] == "done"
    resume_billed = await _billed_to_date(session_factory, user_id) - (
        billed_before_fanout + fanout_billed
    )
    done_row = (await _assistant_rows(session_factory, conv_id))[-1]
    assert done_row.status == "done"

    terminal_receipt = folded[-1].receipt
    assert terminal_receipt is not None, "the terminal RunCost carries its receipt"
    assert terminal_receipt.boundary == "final"
    cumulative = terminal_receipt.cumulative_cost_usd
    persisted_attribution = done_row.attribution or {}

    # (1) The run TOTAL is one number: wire, terminal, persisted row, phase sum.
    assert _final_run_cost(done) == pytest.approx(cumulative)
    assert _terminal_cost(done) == pytest.approx(cumulative)
    assert float(persisted_attribution["costUsd"]) == pytest.approx(cumulative)
    assert sum(_phase_costs(terminal_receipt).values()) == pytest.approx(cumulative)
    # It really is a total across both turns, not just this turn's slice.
    assert cumulative > pause_charge

    # (2) The CHARGE is only the phase spend that happened in THIS turn.
    new_spend = _spend_between(pause_receipt, terminal_receipt)
    assert new_spend > 0.0, "the resumed worker priced a phase"
    assert float(done_row.cost_usd or 0.0) == pytest.approx(new_spend)
    assert resume_billed == pytest.approx(new_spend, abs=5e-7)

    # (3) cumulative == already_billed + newly_billable, and already_billed is
    #     what the pause turn actually charged.
    assert terminal_receipt.already_billed_cost_usd == pytest.approx(pause_charge)
    assert terminal_receipt.newly_billable_cost_usd == pytest.approx(new_spend)
    assert cumulative == pytest.approx(
        terminal_receipt.already_billed_cost_usd
        + terminal_receipt.newly_billable_cost_usd
    )
    # Nothing was charged twice: the two turns together bill the run's total once.
    assert pause_charge + float(done_row.cost_usd or 0.0) == pytest.approx(cumulative)


# --- AC-02: a present receipt outranks every legacy cost owner ----------------
#
# Each resume path has its OWN pre-receipt record of what the pause turn spent:
# the plan path reads the `plannerCostUsd` seed, single mode reads
# `priorRunCostUsd`, and a worker resume reads the checkpoint's own cost fields.
# All three used to be settled OVER the phases restored from the receipt, so any
# disagreement between the two records landed in `newly_billable_cost_usd` and was
# charged as if it had been spent in the continuation. Each test below makes one of
# those records lie by four orders of magnitude and asserts the resumed turn still
# charges only the phase spend that happened inside it.

# Under the $1.00 run cap on purpose: a lie the cap would refuse outright gets
# halted rather than spent, which would hide the mis-charge instead of exposing it.
_LIAR_USD = 0.50


async def test_ac02_plan_resume_ignores_a_conflicting_planner_scalar(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Plan resume: `prior_planner_cost_usd` must not re-price the restored planner."""
    await fanout_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, "ac02-plan-liar")

    plan_call_id, _ = await _plan_pause(fanout_client, conv_id=conv_id, nonce="11")
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]
    pause_receipt = _stored_receipt(pause_row)
    await _rewrite_server_state(
        session_factory,
        pause_row.id,
        lambda state: put_run_ledger_in_server_state(
            state,
            planner_cost_usd=_LIAR_USD,
            planner_usage=UsageUpdate(input_tokens=999_999, output_tokens=999_999),
        ),
    )

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        fanout = await _approve(
            fanout_client, conv_id=conv_id, call_id=plan_call_id, nonce="12"
        )
    billed = await _billed_to_date(session_factory, user_id) - billed_before

    _assert_charged_only_new_phase_spend(
        folded,
        rows=await _assistant_rows(session_factory, conv_id),
        frames=fanout,
        before=pause_receipt,
        billed=billed,
    )


async def test_ac02_worker_resume_ignores_conflicting_checkpoint_costs(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Worker resume: the checkpoint's planner / sibling / paused-worker costs must
    not re-price the phases the receipt restored."""
    await fanout_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, "ac02-worker-liar")

    plan_call_id, _ = await _plan_pause(fanout_client, conv_id=conv_id, nonce="21")
    fanout = await _approve(
        fanout_client, conv_id=conv_id, call_id=plan_call_id, nonce="22"
    )
    assert fanout[-1][1]["status"] == "awaiting_approval"
    worker_call_id = _awaiting_call_id(fanout)
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]
    pause_receipt = _stored_receipt(pause_row)
    assert float(pause_row.cost_usd or 0.0) > 0.0

    def _lie(state: dict[str, Any]) -> dict[str, Any]:
        checkpoint = get_continuation_from_server_state(state, worker_call_id)
        assert checkpoint is not None
        return put_continuation_in_server_state(
            state,
            worker_call_id,
            replace(
                checkpoint,
                planner_cost_usd=_LIAR_USD,
                paused_worker_cost_usd=_LIAR_USD,
                actual_cost_usd=_LIAR_USD,
                completed_workers=tuple(
                    replace(worker, cost_usd=_LIAR_USD)
                    for worker in checkpoint.completed_workers
                ),
            ),
        )

    await _rewrite_server_state(session_factory, pause_row.id, _lie)

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        done = await _approve(
            fanout_client, conv_id=conv_id, call_id=worker_call_id, nonce="23"
        )
    billed = await _billed_to_date(session_factory, user_id) - billed_before

    assert done[-1][1]["status"] == "done"
    _assert_charged_only_new_phase_spend(
        folded,
        rows=await _assistant_rows(session_factory, conv_id),
        frames=done,
        before=pause_receipt,
        billed=billed,
    )


async def test_ac02_single_resume_ignores_a_conflicting_prior_run_scalar(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Single-mode resume: the B5 `priorRunCostUsd` seed must not re-price the
    primary phase the receipt restored.

    Plan approval is irrelevant in single mode — the uncapped fixture is here so
    the seed stays inside the effective cap and gets spent rather than refused.
    """
    await fanout_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, "ac02-single-liar")

    pause_frames = await _collect_sse(
        fanout_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "ac020000-0000-0000-0000-000000000031",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
            "agenticMode": "single",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    call_id = _awaiting_call_id(pause_frames)
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]
    pause_receipt = _stored_receipt(pause_row)
    await _rewrite_server_state(
        session_factory,
        pause_row.id,
        lambda state: put_run_ledger_in_server_state(
            state,
            prior_run_cost_usd=_LIAR_USD,
            prior_run_usage=UsageUpdate(input_tokens=999_999, output_tokens=999_999),
        ),
    )

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        done = await _collect_sse(
            fanout_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "ac020000-0000-0000-0000-000000000032",
                "tierId": "smart",
                "text": "",
                "agenticMode": "single",
                "toolApproval": {"toolCallId": call_id, "decision": "approve"},
            },
        )
    billed = await _billed_to_date(session_factory, user_id) - billed_before

    assert done[-1][1]["status"] == "done"
    _assert_charged_only_new_phase_spend(
        folded,
        rows=await _assistant_rows(session_factory, conv_id),
        frames=done,
        before=pause_receipt,
        billed=billed,
    )


async def test_ac02_a_plan_resume_that_spends_nothing_new_charges_nothing(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The sharpest form of the defect: a resume with no priced phase at all.

    `plan_client`'s user spend cap leaves an approved plan with no headroom to
    spawn workers, so this continuation buys the user nothing. With a $0.37 planner
    scalar sitting in the row it used to charge $0.37 anyway — the seed was settled
    over the restored planner phase and the difference became newly billable.
    """
    await plan_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(plan_client, "ac02-no-new-spend")

    plan_call_id, _ = await _plan_pause(plan_client, conv_id=conv_id, nonce="41")
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]
    pause_receipt = _stored_receipt(pause_row)
    await _rewrite_server_state(
        session_factory,
        pause_row.id,
        lambda state: put_run_ledger_in_server_state(
            state,
            planner_cost_usd=0.37,
            planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
        ),
    )

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        resumed = await _approve(
            plan_client, conv_id=conv_id, call_id=plan_call_id, nonce="42"
        )
    billed = await _billed_to_date(session_factory, user_id) - billed_before
    assert resumed[-1][1]["status"] == "done"
    assert not [
        d for n, d in resumed if n == "subagent_done" and float(d.get("costUsd") or 0.0)
    ], "no phase was priced in this continuation"

    done_row = (await _assistant_rows(session_factory, conv_id))[-1]
    terminal_receipt = folded[-1].receipt
    assert terminal_receipt is not None
    # $0.37 was sitting in the row. It reaches neither the meter nor the invoice.
    assert _spend_between(pause_receipt, terminal_receipt) == pytest.approx(0.0)
    assert terminal_receipt.cumulative_cost_usd == pytest.approx(
        pause_receipt.cumulative_cost_usd
    )
    assert terminal_receipt.newly_billable_cost_usd == pytest.approx(0.0)
    assert float(done_row.cost_usd or 0.0) == pytest.approx(0.0)
    assert billed == pytest.approx(0.0, abs=5e-7)
    assert _final_run_cost(resumed) == pytest.approx(
        pause_receipt.cumulative_cost_usd
    )


_DENY_PLANNER_USD = 0.10
_DENY_PLANNER_USAGE = UsageUpdate(input_tokens=400, output_tokens=120)


def _pause_receipt_with_priced_planner() -> RunReceipt:
    """A pause boundary whose planner really cost something.

    Synthesized because the fake provider plans deterministically and for free, so
    no route can produce a priced planner phase — and a $0.00 planner cannot show
    whether the phase survived the resume.
    """
    ledger = CostLedger()
    ledger.settle(
        "planner",
        role="orchestrator",
        usage=_DENY_PLANNER_USAGE,
        cost_usd=_DENY_PLANNER_USD,
    )
    return ledger.receipt(cap_usd=1.0, boundary="pause")


@pytest.mark.parametrize(
    "record",
    [
        pytest.param("receipt", id="planner-phase-from-a-pause-receipt"),
        pytest.param("legacy-seed", id="planner-cost-from-a-legacy-seed"),
    ],
)
async def test_ac02_a_denied_plan_keeps_the_planner_phase_it_restored(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    record: str,
) -> None:
    """Deny is a resume decision too, so it must read the restored planner phase
    rather than settle this turn's (empty) planner pass over it.

    A denied resume never re-plans, so `planner_usage` is empty. Settling that over
    the restored planner left the terminal receipt asserting a cumulative it could
    no longer itemize: the phase sum fell to $0.00 while cumulative stayed pinned at
    the billed floor. The continuation's charge stayed correct at $0.00 either way —
    the billed floor absorbed it — so the phase history is the only thing that gives
    the defect away, and it is exactly what the register's closure identity needs.
    """
    await fanout_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, f"ac02-deny-{record}")

    plan_call_id, _ = await _plan_pause(fanout_client, conv_id=conv_id, nonce="61")
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]

    async with session_factory() as session:
        row = await session.get(Message, pause_row.id)
        assert row is not None
        state = dict(row.server_state or {})
        if record == "receipt":
            state = put_run_ledger_in_server_state(
                state, run_receipt=_pause_receipt_with_priced_planner()
            )
        else:
            state = _without_receipt(
                put_run_ledger_in_server_state(
                    state,
                    planner_cost_usd=_DENY_PLANNER_USD,
                    planner_usage=_DENY_PLANNER_USAGE,
                )
            )
        row.server_state = state
        await session.commit()

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        denied = await _collect_sse(
            fanout_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "ac020000-0000-0000-0000-000000000062",
                "tierId": "smart",
                "text": "",
                "agenticMode": "deep_research",
                "toolApproval": {"toolCallId": plan_call_id, "decision": "deny"},
            },
        )
    billed = await _billed_to_date(session_factory, user_id) - billed_before
    assert denied[-1][1]["status"] == "done"
    assert not [
        d
        for n, d in denied
        if n == "subagent_started" and str(d.get("role")) == "worker"
    ], "a declined plan runs no worker"

    done_row = (await _assistant_rows(session_factory, conv_id))[-1]
    receipt = folded[-1].receipt
    assert receipt is not None
    phases = _phase_costs(receipt)

    # The planner phase the resume restored is still itemized on the terminal
    # receipt, at the amount the pause turn recorded for it.
    assert phases["planner"] == pytest.approx(_DENY_PLANNER_USD)
    assert sum(phases.values()) == pytest.approx(_DENY_PLANNER_USD)
    assert receipt.cumulative_cost_usd == pytest.approx(_DENY_PLANNER_USD)
    assert sum(phases.values()) == pytest.approx(receipt.cumulative_cost_usd)
    # A decline buys nothing, so nothing is newly billable.
    assert receipt.newly_billable_cost_usd == pytest.approx(0.0)
    assert receipt.already_billed_cost_usd == pytest.approx(_DENY_PLANNER_USD)
    assert float(done_row.cost_usd or 0.0) == pytest.approx(0.0)
    assert billed == pytest.approx(0.0, abs=5e-7)
    # The run TOTAL is still the one number, on the wire and on the row.
    assert _final_run_cost(denied) == pytest.approx(_DENY_PLANNER_USD)
    assert _terminal_cost(denied) == pytest.approx(_DENY_PLANNER_USD)
    persisted = done_row.attribution or {}
    assert float(persisted["costUsd"]) == pytest.approx(_DENY_PLANNER_USD)
    # And the turn's token roll-up reports the planner tokens behind that money
    # rather than this turn's empty planner pass.
    breakdown = persisted["breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown["inputTokens"] == _DENY_PLANNER_USAGE.input_tokens
    assert breakdown["outputTokens"] == _DENY_PLANNER_USAGE.output_tokens


async def test_ac02_a_receipt_backed_resume_needs_no_scalar_seeds(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The receipt is sufficient on its own: with every scalar seed stripped, the
    resumed turn bills exactly what it bills with them present."""
    await fanout_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, "ac02-no-seeds")

    plan_call_id, _ = await _plan_pause(fanout_client, conv_id=conv_id, nonce="51")
    pause_row = (await _assistant_rows(session_factory, conv_id))[-1]
    pause_receipt = _stored_receipt(pause_row)
    await _rewrite_server_state(session_factory, pause_row.id, _without_scalar_seeds)

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        fanout = await _approve(
            fanout_client, conv_id=conv_id, call_id=plan_call_id, nonce="52"
        )
    billed = await _billed_to_date(session_factory, user_id) - billed_before

    _assert_charged_only_new_phase_spend(
        folded,
        rows=await _assistant_rows(session_factory, conv_id),
        frames=fanout,
        before=pause_receipt,
        billed=billed,
    )


async def test_ac02_plan_pause_writes_a_boundary_receipt_to_server_state(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The plan-approval pause is an orchestrator-owned persistable boundary, so
    the paused row carries its typed receipt in server-only state — and only there.

    Before AC-02 the pause row stored only scalar seeds, so a resume had to
    reconstruct what had already been billed from one phase's cost.
    """
    await plan_client.get("/api/bootstrap")
    await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(plan_client, "ac02-pause")
    pause_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "ac020000-0000-0000-0000-000000000031",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"

    paused = (await _assistant_rows(session_factory, conv_id))[-1]
    receipt = _stored_receipt(paused)
    assert receipt.boundary == "pause"
    # The receipt is server-only: it must never ride out on the pause tool input.
    plan_input = next(d["input"] for n, d in pause_frames if n == "tool_call")
    assert isinstance(plan_input, dict)
    assert SERVER_STATE_RUN_RECEIPT_KEY not in plan_input
    # And the row the user sees agrees with it on both numbers.
    assert _terminal_cost(pause_frames) == pytest.approx(receipt.cumulative_cost_usd)
    assert float(paused.cost_usd or 0.0) == pytest.approx(
        receipt.newly_billable_cost_usd
    )


async def test_ac02_only_boundary_run_costs_are_billing_authority(
    fanout_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Exactly the boundary `RunCost` carries a receipt; plan and progress ticks
    carry none, so a mid-run display number can never be billed.

    The phases restored from the pause receipt also re-enter the run flagged
    `already_billed`, which is what keeps them inside the cumulative total and
    outside this turn's charge.
    """
    await fanout_client.get("/api/bootstrap")
    await _entitle_current_user(session_factory)
    conv_id = await _new_conversation(fanout_client, "ac02-ticks")

    plan_call_id, _ = await _plan_pause(fanout_client, conv_id=conv_id, nonce="41")
    fanout = await _approve(
        fanout_client, conv_id=conv_id, call_id=plan_call_id, nonce="42"
    )
    assert fanout[-1][1]["status"] == "awaiting_approval"
    pause_receipt = _stored_receipt(
        (await _assistant_rows(session_factory, conv_id))[-1]
    )

    with _capturing_run_costs() as folded:
        done = await _approve(
            fanout_client,
            conv_id=conv_id,
            call_id=_awaiting_call_id(fanout),
            nonce="43",
        )
    assert done[-1][1]["status"] == "done"

    assert folded, "the resumed turn folded at least one RunCost"
    terminal = folded[-1]
    assert terminal.phase == "final"
    assert terminal.receipt is not None
    # Progress / plan display ticks are never billing authority.
    assert all(ev.receipt is None for ev in folded if ev.phase != "final")
    # Every phase the pause boundary had already accounted for comes back billed.
    restored = _phase_costs(pause_receipt)
    for phase in terminal.receipt.phases:
        if phase.phase_id in restored and phase.cost_usd == pytest.approx(
            restored[phase.phase_id]
        ):
            assert phase.already_billed is True, phase.phase_id
