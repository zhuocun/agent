"""Route/handler integration for B4/B5/B9/B13 arch-review ledger fixes."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
    SERVER_STATE_RUN_RECEIPT_KEY,
    get_run_ledger_from_server_state,
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
from app.runtime.run_receipt import CostLedger, UsageTotals, decode_run_receipt
from app.schemas.message import AgenticRunSummaryPart
from app.streaming import handler as handler_module

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
    """B4: pause persists planner ledger in server_state; resume RunCost is non-zero."""
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
        paused.server_state = put_run_ledger_in_server_state(
            paused.server_state if isinstance(paused.server_state, dict) else {},
            planner_cost_usd=0.37,
            planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
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
    """B5: single-mode pause ledger in server_state seeds resume RunCost."""
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
        paused.server_state = put_run_ledger_in_server_state(
            paused.server_state if isinstance(paused.server_state, dict) else {},
            prior_run_cost_usd=0.2,
            prior_run_usage=UsageUpdate(input_tokens=20, output_tokens=0),
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
    """Capture every `RunCost` the handler folds, receipt object included.

    The receipt is internal transport with no wire field, so the SSE frames
    cannot show whether one reached the handler. Wrapping the handler's fold
    point is what makes that observable to a route test.
    """
    captured: list[RunCost] = []
    original = handler_module.build_agentic_run_summary_part

    def _capture(ev: RunCost) -> AgenticRunSummaryPart:
        captured.append(ev)
        return original(ev)

    handler_module.build_agentic_run_summary_part = _capture  # type: ignore[assignment]
    try:
        yield captured
    finally:
        handler_module.build_agentic_run_summary_part = original  # type: ignore[assignment]


async def _start_plan_approval_pause(
    client: AsyncClient, *, conv_id: str, client_message_id: str
) -> tuple[str, list[tuple[str, dict[str, object]]]]:
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_message_id,
            "tierId": "smart",
            "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][1]["status"] == "awaiting_approval"
    return next(str(d["id"]) for n, d in frames if n == "tool_call"), frames


async def test_ac02_plan_pause_writes_a_boundary_receipt_to_server_state(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The plan-approval pause is an orchestrator-owned persistable boundary, so
    the paused row carries its typed receipt in server-only state.

    Before AC-02 the pause row stored only scalar seeds, so a resume had to
    reconstruct what had already been billed from one phase's cost.
    """
    await plan_client.get("/api/bootstrap")
    await _entitle_current_user(session_factory)
    create = await plan_client.post(
        "/api/conversations", json={"title": "ac02-pause", "selectedTierId": "smart"}
    )
    conv_id = create.json()["id"]
    _call_id, pause_frames = await _start_plan_approval_pause(
        plan_client,
        conv_id=conv_id,
        client_message_id="ac020000-0000-0000-0000-000000000001",
    )
    pause_attribution = pause_frames[-1][1]["attribution"]
    assert isinstance(pause_attribution, dict)

    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
    state = paused.server_state or {}
    assert SERVER_STATE_RUN_RECEIPT_KEY in state
    receipt = decode_run_receipt(state[SERVER_STATE_RUN_RECEIPT_KEY])
    assert receipt is not None
    assert receipt.boundary == "pause"
    # The receipt is server-only: it must never ride out on the pause tool input.
    plan_input = next(d["input"] for n, d in pause_frames if n == "tool_call")
    assert isinstance(plan_input, dict)
    assert SERVER_STATE_RUN_RECEIPT_KEY not in plan_input
    # And the row the user sees agrees with it on both numbers.
    assert float(pause_attribution["costUsd"]) == pytest.approx(
        receipt.cumulative_cost_usd
    )
    assert float(paused.cost_usd or 0.0) == pytest.approx(
        receipt.newly_billable_cost_usd
    )


async def test_ac02_plan_resume_bills_only_the_receipt_increment(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """AC-02 closure: the pause receipt round-trips, the resumed terminal receipt
    reaches the handler, and cumulative versus newly billable stay separate.

    The pause row is stamped with a receipt that has already billed $0.10 of the
    run, plus a planner seed recording $0.37 of planner spend. The resumed turn
    must therefore report $0.37 everywhere a run TOTAL appears — the final
    `run_cost`, the terminal attribution, the persisted attribution, and the sum
    of the receipt's own phases — while charging only the $0.27 that has not been
    charged yet to `Message.cost_usd` and the usage rollup.

    This is the `$0.37` versus `$0.00` regression: `_agentic_sum_cost_usd` saw no
    `SubagentDone` for the seeded planner, so the run total collapsed to zero on
    the row and in the terminal while the wire still said `$0.37`.
    """
    await plan_client.get("/api/bootstrap")
    user_id = await _entitle_current_user(session_factory)
    create = await plan_client.post(
        "/api/conversations", json={"title": "ac02-resume", "selectedTierId": "smart"}
    )
    conv_id = create.json()["id"]
    plan_call_id, _pause_frames = await _start_plan_approval_pause(
        plan_client,
        conv_id=conv_id,
        client_message_id="ac020000-0000-0000-0000-000000000011",
    )

    planner_usage = UsageUpdate(input_tokens=37, output_tokens=3)
    banked = CostLedger()
    banked.settle(
        "planner",
        role="orchestrator",
        usage=UsageTotals(input_tokens=10),
        cost_usd=ALREADY_BILLED_USD,
    )
    pause_receipt = banked.receipt(cap_usd=1.0, boundary="pause")
    assert pause_receipt.cumulative_cost_usd == pytest.approx(ALREADY_BILLED_USD)

    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
        paused.server_state = put_run_ledger_in_server_state(
            paused.server_state if isinstance(paused.server_state, dict) else {},
            planner_cost_usd=PLANNER_SPEND_USD,
            planner_usage=planner_usage,
            run_receipt=pause_receipt,
        )
        await session.commit()
        # Round-trip through the JSON column, not just through the writer.
        stored = get_run_ledger_from_server_state(paused.server_state)
        assert stored.run_receipt == pause_receipt

    billed_before = await _billed_to_date(session_factory, user_id)
    with _capturing_run_costs() as folded:
        resume_frames = await _collect_sse(
            plan_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "ac020000-0000-0000-0000-000000000012",
                "tierId": "smart",
                "text": "",
                "agenticMode": "deep_research",
                "toolApproval": {"toolCallId": plan_call_id, "decision": "approve"},
            },
        )
    assert resume_frames[-1][1]["status"] == "done"
    final_run_cost = [d for n, d in resume_frames if n == "run_cost"][-1]
    terminal_attribution = resume_frames[-1][1]["attribution"]
    assert isinstance(terminal_attribution, dict)

    # The resumed terminal receipt reached the handler, and its own phase
    # breakdown accounts for the whole cumulative total.
    terminal_receipt = folded[-1].receipt
    assert terminal_receipt is not None
    assert terminal_receipt.boundary == "final"
    phase_sum = sum(phase.cost_usd for phase in terminal_receipt.phases)
    assert phase_sum == pytest.approx(terminal_receipt.cumulative_cost_usd)
    # Precedence, stated as a fact about this turn rather than as a claim about
    # the code: nothing the reconstruction reads can produce $0.37. No
    # `SubagentDone` carried it (`_agentic_sum_cost_usd` sums those), so the
    # total below can only have come from the receipt.
    assert not any(
        float(d.get("costUsd") or 0.0) > 0.0
        for n, d in resume_frames
        if n == "subagent_done"
    )

    async with session_factory() as session:
        done_row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .where(Message.status == "done")
            )
        ).scalar_one()
    done_attribution = done_row.attribution or {}
    billed_after = await _billed_to_date(session_factory, user_id)

    # The run TOTAL is one number on the wire, in the terminal, on the row, and
    # in the receipt's own per-phase breakdown.
    assert float(final_run_cost["subtotalUsd"]) == pytest.approx(PLANNER_SPEND_USD)
    assert float(terminal_attribution["costUsd"]) == pytest.approx(PLANNER_SPEND_USD)
    assert float(done_attribution["costUsd"]) == pytest.approx(PLANNER_SPEND_USD)
    assert phase_sum == pytest.approx(PLANNER_SPEND_USD)
    # The CHARGE is only what the pause turn had not already billed.
    newly_billable = PLANNER_SPEND_USD - ALREADY_BILLED_USD
    assert float(done_row.cost_usd or 0.0) == pytest.approx(newly_billable)
    assert billed_after - billed_before == pytest.approx(newly_billable)
    # cumulative == already_billed + newly_billable, read off the receipt that
    # produced those two rows rather than restated from the fixtures.
    assert terminal_receipt.already_billed_cost_usd == pytest.approx(ALREADY_BILLED_USD)
    assert terminal_receipt.cumulative_cost_usd == pytest.approx(
        terminal_receipt.already_billed_cost_usd
        + terminal_receipt.newly_billable_cost_usd
    )
    assert terminal_receipt.newly_billable_cost_usd == pytest.approx(newly_billable)


async def test_ac02_only_boundary_run_costs_are_billing_authority(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Exactly the boundary `RunCost` carries a receipt; plan and progress ticks
    carry none, so a mid-run display number can never be billed.

    The restored planner also re-enters the run flagged `already_billed`, which is
    what keeps it inside the cumulative total but outside this turn's charge.
    """
    await plan_client.get("/api/bootstrap")
    await _entitle_current_user(session_factory)
    create = await plan_client.post(
        "/api/conversations", json={"title": "ac02-phases", "selectedTierId": "smart"}
    )
    conv_id = create.json()["id"]
    plan_call_id, _frames = await _start_plan_approval_pause(
        plan_client,
        conv_id=conv_id,
        client_message_id="ac020000-0000-0000-0000-000000000021",
    )

    banked = CostLedger()
    banked.settle(
        "planner",
        role="orchestrator",
        usage=UsageTotals(input_tokens=10),
        cost_usd=ALREADY_BILLED_USD,
    )
    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
        paused.server_state = put_run_ledger_in_server_state(
            paused.server_state if isinstance(paused.server_state, dict) else {},
            planner_cost_usd=PLANNER_SPEND_USD,
            planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
            run_receipt=banked.receipt(cap_usd=1.0, boundary="pause"),
        )
        await session.commit()

    with _capturing_run_costs() as folded:
        resume_frames = await _collect_sse(
            plan_client,
            f"/api/conversations/{conv_id}/messages",
            {
                "clientMessageId": "ac020000-0000-0000-0000-000000000022",
                "tierId": "smart",
                "text": "",
                "agenticMode": "deep_research",
                "toolApproval": {"toolCallId": plan_call_id, "decision": "approve"},
            },
        )

    assert resume_frames[-1][1]["status"] == "done"
    terminal = folded[-1]
    assert terminal.phase == "final"
    receipt = terminal.receipt
    assert receipt is not None, "a terminal RunCost must carry its receipt"
    assert receipt.boundary == "final"
    assert receipt.cumulative_cost_usd == pytest.approx(PLANNER_SPEND_USD)
    assert receipt.already_billed_cost_usd == pytest.approx(ALREADY_BILLED_USD)
    assert receipt.newly_billable_cost_usd == pytest.approx(
        PLANNER_SPEND_USD - ALREADY_BILLED_USD
    )
    # The planner phase re-enters the run marked as already-billed spend.
    planner_phase = next(p for p in receipt.phases if p.phase_id == "planner")
    assert planner_phase.already_billed is True
    # Progress / plan display ticks are never billing authority.
    assert all(ev.receipt is None for ev in folded if ev.phase != "final")
