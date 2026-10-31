"""Resume and single-mode budget holds must match what the run actually admits.

The route reserves a residual (or one primary phase). Admission and receipt-less
stop billing were still using the full-run estimate and the already-billed floor.
These tests use ``Settings(_env_file=None)`` and the fast binding as the oracle:

- full estimate for one sub-question is 0.2016 (three phases)
- residual hold, one remaining worker, planner excluded, is 0.1344
- one primary phase is 0.0672
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, replace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic import budget
from app.agentic.clarify import ClarificationRecord, clarification_extra_input_tokens
from app.agentic.continuation import AgenticContinuation
from app.agentic.orchestrator import _resume_worker_continuation, run_orchestrator
from app.config import Settings, get_settings
from app.db.models import Conversation, User
from app.db.session import get_db
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    RunCost,
    SubagentStarted,
    ToolResult,
    UsageUpdate,
)
from app.providers.tiers import get_binding
from app.runtime.run_receipt import PhaseReceipt, RunReceipt
from app.streaming.turn_money import TurnMoney
from app.streaming.turn_reducer import TurnState

_FULL_N1 = 0.2016
_RESIDUAL_ONE_WORKER = 0.1344
_ONE_PHASE = 0.0672
_LEDGER_UNDER_CAP = 0.20
_NEW_LEG = 0.04
_PRIOR_FLOOR = 0.50


def _oracle_settings(**overrides: object) -> Settings:
    """Defaults the orchestrator recomputed, plus explicit test overrides.

    ``Settings`` populates from env aliases, so overrides use those names.
    """
    values: dict[str, object] = {
        "PROVIDER_BACKEND": "fake",
        "AGENTIC_ENABLED": True,
        "TOOLS_ENABLED": True,
        "AGENTIC_VERIFIER": False,
        "AGENTIC_PLAN_APPROVAL": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _fast_binding(settings: Settings):
    binding = get_binding("fast", settings=settings)
    assert binding is not None
    return binding


def _price(binding, usage: UsageUpdate) -> float:
    return compute_cost_breakdown(usage=usage, binding=binding, image_count=0).subtotal_usd


def _assert_oracle(settings: Settings) -> None:
    binding = _fast_binding(settings)
    full = budget.estimate_run_cost(sub_question_count=1, binding=binding, settings=settings)
    residual = budget.estimate_residual_run_cost(
        remaining_workers=1,
        binding=binding,
        settings=settings,
        include_planner=False,
    )
    phase = (
        _price(binding, budget.expected_subagent_usage(settings))
        * settings.agentic_reasoning_token_multiplier
        * settings.agentic_fanout_token_multiplier
    )
    assert budget._subagent_count(1, settings) == 3
    assert full == pytest.approx(_FULL_N1)
    assert residual == pytest.approx(_RESIDUAL_ONE_WORKER)
    assert phase == pytest.approx(_ONE_PHASE)
    assert full <= settings.agentic_run_budget_usd
    assert not full <= residual
    assert budget.exceeds_cap(
        actual_usd=_LEDGER_UNDER_CAP,
        cap_usd=settings.agentic_run_budget_usd,
        headroom_usd=residual,
    )


def _stream_factory(text: str) -> tuple[list[str], object]:
    prompts: list[str] = []

    def _make_stream_for(prompt: str, **_kwargs: object):
        prompts.append(prompt)

        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text=text)
                usage = UsageUpdate(input_tokens=1, output_tokens=1)
                yield usage
                yield Complete(usage=usage)

            return _gen()

        return _make

    return prompts, _make_stream_for


def _answer_text(events: list[ProviderEvent]) -> str:
    return "".join(event.text for event in events if isinstance(event, AnswerDelta))


async def _plan_resume_events(
    *,
    settings: Settings,
    headroom_usd: float,
    prior_planner_cost_usd: float = 0.0,
    clarify_records: list[ClarificationRecord] | None = None,
) -> tuple[list[str], list[ProviderEvent]]:
    binding = _fast_binding(settings)
    prompts, make_stream_for = _stream_factory("worker finding")

    def _full_estimate(sub_question_count: int) -> float:
        # Handler wires this to the full turn estimate, not the residual hold.
        return budget.estimate_run_cost(
            sub_question_count=sub_question_count,
            binding=binding,
            settings=settings,
        )

    events = [
        event
        async for event in run_orchestrator(
            make_stream_for=make_stream_for,
            settings=settings,
            mode="deep_research",
            user_text="compare the two cases",
            cost_for_usage=lambda usage: _price(binding, usage),
            estimate_cost=_full_estimate,
            budget_headroom_usd=headroom_usd,
            plan_approved=True,
            approved_plan=["the one approved question"],
            prior_planner_cost_usd=prior_planner_cost_usd,
            clarify_records=clarify_records,
        )
    ]
    return prompts, events


def _worker_continuation(*, ledger_usd: float) -> AgenticContinuation:
    return AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha",
        plan=("alpha",),
        completed_workers=(),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.0,
        budget_halted=False,
        actual_cost_usd=ledger_usd,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="partial ",
        orchestration_mode="deep_research",
        paused_worker_usage=UsageUpdate(input_tokens=2, output_tokens=1),
        paused_worker_cost_usd=0.0,
    )


def _resume_tool() -> ToolResult:
    return ToolResult(
        tool_call_id="worker-0::call",
        name="request_user_confirmation",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )


async def _worker_resume_events(
    *,
    settings: Settings,
    ledger_usd: float,
    headroom_usd: float,
) -> tuple[list[str], list[ProviderEvent]]:
    binding = _fast_binding(settings)
    prompts, make_stream_for = _stream_factory("resumed-ok")
    events = [
        event
        async for event in _resume_worker_continuation(
            make_stream_for=make_stream_for,
            settings=settings,
            cost_for_usage=lambda usage: _price(binding, usage),
            continuation=_worker_continuation(ledger_usd=ledger_usd),
            resume_tool_result=_resume_tool(),
            server_approved_call_ids={"worker-0::call"},
            budget_headroom_usd=headroom_usd,
        )
    ]
    return prompts, events


@dataclass
class _MoneySeed:
    prior_run_cost_usd: float = 0.0
    prior_receipt: RunReceipt | None = None
    agentic_continuation: object = None


def _billable_for_stop(
    *,
    seed: _MoneySeed | None,
    state: TurnState,
    binding,
) -> float:
    money = TurnMoney(
        settings=_oracle_settings(),
        binding=binding,
        fallback_binding=None,
        image_attachment_count=0,
        state=state,
        agentic_active=True,
        resume_seed=seed,
    )
    _breakdown, _cumulative, billable = money.boundary_money()
    return billable


def _usage_priced_at(binding, usd: float) -> UsageUpdate:
    """Input tokens that price to ``usd`` on a $1 / million binding."""
    tokens = round(usd * 1_000_000)
    usage = UsageUpdate(input_tokens=tokens)
    assert _price(binding, usage) == pytest.approx(usd)
    return usage


def _priced_binding(settings: Settings):
    fast = _fast_binding(settings)
    return replace(
        fast,
        list_price_in_per_m=1.0,
        list_price_out_per_m=1.0,
        cache_read_per_m=0.1,
        long_context_flat=True,
        session_multiplier=None,
        pricing_tiers=(),
    )


def test_fast_binding_oracle_matches_the_confirmed_figures() -> None:
    _assert_oracle(_oracle_settings())


@pytest.mark.asyncio
async def test_plan_resume_admits_residual_hold_when_full_estimate_fits_the_cap() -> None:
    """Full 0.2016 against hold 0.1344 admits when the run cap covers 0.2016.

    The route already reserved the residual. Remaining platform balance above
    the full estimate is what let that reservation succeed. Admission must use
    the same residual, so a plan that fits the run cap is not refused.
    """
    settings = _oracle_settings()
    _assert_oracle(settings)
    prompts, events = await _plan_resume_events(
        settings=settings,
        headroom_usd=_RESIDUAL_ONE_WORKER,
    )
    assert prompts, "the approved plan must reach a worker"
    assert any(isinstance(event, SubagentStarted) and event.role == "worker" for event in events)
    assert "not started" not in _answer_text(events).lower()
    finals = [event for event in events if isinstance(event, RunCost) and event.phase == "final"]
    assert finals
    assert finals[-1].budget_halted is False


@pytest.mark.asyncio
async def test_plan_resume_still_admits_when_billed_ledger_exceeds_the_hold() -> None:
    """Already-billed 0.20 is under the run cap and must not consume the hold."""
    settings = _oracle_settings()
    prompts, events = await _plan_resume_events(
        settings=settings,
        headroom_usd=_RESIDUAL_ONE_WORKER,
        prior_planner_cost_usd=_LEDGER_UNDER_CAP,
    )
    assert prompts
    assert "not started" not in _answer_text(events).lower()
    finals = [event for event in events if isinstance(event, RunCost) and event.phase == "final"]
    assert finals
    assert finals[-1].budget_halted is False


@pytest.mark.asyncio
async def test_plan_resume_refuses_when_residual_exceeds_the_hold() -> None:
    settings = _oracle_settings()
    hold = 0.10
    assert hold < _RESIDUAL_ONE_WORKER
    prompts, events = await _plan_resume_events(settings=settings, headroom_usd=hold)
    text = _answer_text(events)
    assert prompts == []
    assert "not started" in text.lower()
    assert f"{_RESIDUAL_ONE_WORKER:.4f}" in text
    assert f"{_FULL_N1:.4f}" not in text


@pytest.mark.asyncio
async def test_plan_resume_refuses_when_ledger_exceeds_the_run_cap() -> None:
    cap = 0.15
    assert _RESIDUAL_ONE_WORKER <= cap < _LEDGER_UNDER_CAP
    settings = _oracle_settings(AGENTIC_RUN_BUDGET_USD=cap)
    prompts, events = await _plan_resume_events(
        settings=settings,
        headroom_usd=_RESIDUAL_ONE_WORKER,
        prior_planner_cost_usd=_LEDGER_UNDER_CAP,
    )
    text = _answer_text(events)
    assert prompts == []
    assert "planner spend already exceeds" in text


@pytest.mark.asyncio
async def test_plan_resume_admits_the_same_clarify_uplift_the_hold_includes() -> None:
    """Clarify tokens ride on the residual, on the reservation and on admission."""
    settings = _oracle_settings()
    binding = _fast_binding(settings)
    records = [
        ClarificationRecord(
            question_id="0",
            question="What region should the research cover?",
            answer="North Atlantic " * 80,
        )
    ]
    extra = clarification_extra_input_tokens(records, worker_count=1)
    assert extra > 0
    residual = budget.estimate_residual_run_cost(
        remaining_workers=1,
        binding=binding,
        settings=settings,
        include_planner=False,
    )
    uplift = _price(binding, UsageUpdate(input_tokens=extra))
    hold = residual + uplift
    assert f"{hold:.4f}" != f"{residual:.4f}"
    assert f"{hold:.4f}" != f"{_FULL_N1:.4f}"
    prompts, events = await _plan_resume_events(
        settings=settings,
        headroom_usd=hold,
        clarify_records=records,
    )
    assert prompts
    assert "not started" not in _answer_text(events).lower()
    bare_prompts, bare_events = await _plan_resume_events(
        settings=settings,
        headroom_usd=residual,
        clarify_records=records,
    )
    bare_text = _answer_text(bare_events)
    assert bare_prompts == []
    assert f"{hold:.4f}" in bare_text
    assert f"{_FULL_N1:.4f}" not in bare_text


@pytest.mark.asyncio
async def test_worker_resume_does_not_halt_before_the_provider_call() -> None:
    """Ledger 0.20 against hold 0.1344 must still open the continuation."""
    settings = _oracle_settings()
    _assert_oracle(settings)
    prompts, events = await _worker_resume_events(
        settings=settings,
        ledger_usd=_LEDGER_UNDER_CAP,
        headroom_usd=_RESIDUAL_ONE_WORKER,
    )
    assert prompts, "the continuation must call the provider"
    assert "resumed-ok" in _answer_text(events)


@pytest.mark.asyncio
async def test_worker_resume_halts_when_ledger_exceeds_the_run_cap() -> None:
    cap = 0.15
    assert _RESIDUAL_ONE_WORKER <= cap < _LEDGER_UNDER_CAP
    settings = _oracle_settings(AGENTIC_RUN_BUDGET_USD=cap)
    prompts, events = await _worker_resume_events(
        settings=settings,
        ledger_usd=_LEDGER_UNDER_CAP,
        headroom_usd=1.0,
    )
    assert prompts == []
    finals = [event for event in events if isinstance(event, RunCost) and event.budget_halted]
    assert finals


def test_receiptless_stop_bills_this_leg_not_the_run_floor() -> None:
    """Prior floor 0.50 and new in-flight usage 0.04 bills 0.04.

    Cancel precedes SubagentDone, so the scope has this invocation's usage and
    ``cost_usd is None``. A settled phase subtracts that phase's already-billed
    amount, not the run-wide floor.
    """
    settings = _oracle_settings()
    binding = _priced_binding(settings)
    usage = _usage_priced_at(binding, _NEW_LEG)

    fresh = TurnState(agentic=True)
    fresh_scope = fresh.scope("worker-0", label="Worker 1", role="worker")
    fresh_scope.usage = usage
    assert _billable_for_stop(seed=None, state=fresh, binding=binding) == pytest.approx(_NEW_LEG)

    resumed = TurnState(agentic=True)
    resumed_scope = resumed.scope("worker-0", label="Worker 1", role="worker")
    resumed_scope.usage = usage
    resumed_billable = _billable_for_stop(
        seed=_MoneySeed(prior_run_cost_usd=_PRIOR_FLOOR),
        state=resumed,
        binding=binding,
    )
    assert resumed_billable == pytest.approx(_NEW_LEG)
    assert resumed_billable != pytest.approx(max(0.0, _NEW_LEG - _PRIOR_FLOOR))

    settled = TurnState(agentic=True)
    settled_scope = settled.scope("worker-0", label="Worker 1", role="worker")
    settled_scope.cost_usd = 0.24
    phase_billed = 0.20
    receipt = RunReceipt(
        cumulative_cost_usd=_PRIOR_FLOOR,
        already_billed_cost_usd=_PRIOR_FLOOR,
        phases=(
            PhaseReceipt(
                phase_id="worker-0",
                role="worker",
                cost_usd=phase_billed,
                already_billed=True,
            ),
        ),
    )
    settled_billable = _billable_for_stop(
        seed=_MoneySeed(prior_receipt=receipt),
        state=settled,
        binding=binding,
    )
    assert settled_billable == pytest.approx(0.24 - phase_billed)


def test_receiptless_stop_subtracts_prior_phase_when_already_billed_is_false() -> None:
    """A worker pause settles the phase with already_billed false.

    Resume Done cost is that partial plus this session. Prior phase 0.20 and
    scope cost 0.24 bill 0.04.
    """
    settings = _oracle_settings()
    binding = _priced_binding(settings)
    receipt = RunReceipt(
        cumulative_cost_usd=_PRIOR_FLOOR,
        already_billed_cost_usd=_PRIOR_FLOOR,
        phases=(
            PhaseReceipt(
                phase_id="worker-0",
                role="worker",
                cost_usd=0.20,
                already_billed=False,
            ),
        ),
    )
    state = TurnState(agentic=True)
    scope = state.scope("worker-0", label="Worker 1", role="worker")
    scope.cost_usd = 0.24
    billable = _billable_for_stop(
        seed=_MoneySeed(prior_receipt=receipt),
        state=state,
        binding=binding,
    )
    assert billable == pytest.approx(0.04)


def test_receipt_bearing_done_bills_only_newly_billable_cost() -> None:
    settings = _oracle_settings()
    binding = _priced_binding(settings)
    receipt = RunReceipt(
        cumulative_cost_usd=_PRIOR_FLOOR + _NEW_LEG,
        already_billed_cost_usd=_PRIOR_FLOOR,
    )
    assert receipt.newly_billable_cost_usd == pytest.approx(_NEW_LEG)
    state = TurnState(agentic=True)
    scope = state.scope("worker-0", label="Worker 1", role="worker")
    scope.cost_usd = 9.0
    state.receipt = receipt
    billable = _billable_for_stop(
        seed=_MoneySeed(prior_run_cost_usd=_PRIOR_FLOOR, prior_receipt=receipt),
        state=state,
        binding=binding,
    )
    assert billable == pytest.approx(receipt.newly_billable_cost_usd)


# --- single-mode reservation through the send route --------------------------


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


@pytest.fixture
def single_mode_budget_env() -> Iterator[None]:
    keys = ("TOOLS_ENABLED", "AGENTIC_ENABLED", "USAGE_BUDGET_USD")
    prior = {key: os.environ.get(key) for key in keys}
    os.environ["TOOLS_ENABLED"] = "true"
    os.environ["AGENTIC_ENABLED"] = "true"
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
def single_mode_app(
    single_mode_budget_env: None,
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
async def single_mode_client(single_mode_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=single_mode_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


async def _seed_fast_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    async with session_factory() as session:
        user_id = (await session.execute(select(User))).scalar_one().id
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id="fast",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


async def _send_single(
    client: AsyncClient,
    conv_id: str,
    *,
    client_message_id: str,
) -> tuple[int, str]:
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": client_message_id,
            "tierId": "fast",
            "text": "hello from single mode",
            "agenticMode": "single",
        },
        timeout=30.0,
    ) as response:
        chunks: list[str] = []
        async for chunk in response.aiter_text():
            chunks.append(chunk)
        return response.status_code, "".join(chunks)


@pytest.mark.asyncio
async def test_single_mode_remaining_0_10_reserves_and_admits(
    single_mode_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remaining 0.10 fits one phase (0.0672) and does not fit three (0.2016)."""
    monkeypatch.setenv("USAGE_BUDGET_USD", "0.10")
    get_settings.cache_clear()
    settings = get_settings()
    binding = _fast_binding(settings)
    full = budget.estimate_run_cost(sub_question_count=1, binding=binding, settings=settings)
    phase = full / budget._subagent_count(1, settings)
    assert full == pytest.approx(_FULL_N1)
    assert phase == pytest.approx(_ONE_PHASE)
    assert phase <= 0.10 < full

    await single_mode_client.get("/api/bootstrap")
    conv_id = await _seed_fast_conversation(session_factory)
    status_code, body = await _send_single(
        single_mode_client,
        conv_id,
        client_message_id="50000000-0000-4000-8000-000000000010",
    )
    assert status_code == 200, body
    frames = _parse_sse(body)
    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["status"] == "done"
    started = [data for name, data in frames if name == "subagent_started"]
    assert any(data.get("role") == "primary" for data in started)
    answer = "".join(str(data.get("text", "")) for name, data in frames if name == "answer_delta")
    assert "not started" not in answer.lower()


@pytest.mark.asyncio
async def test_single_mode_remaining_0_05_raises_budget_error(
    single_mode_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One phase is 0.0672, so remaining 0.05 still refuses before the provider."""
    monkeypatch.setenv("USAGE_BUDGET_USD", "0.05")
    get_settings.cache_clear()
    await single_mode_client.get("/api/bootstrap")
    conv_id = await _seed_fast_conversation(session_factory)
    response = await single_mode_client.post(
        f"/api/conversations/{UUID(conv_id)}/messages",
        json={
            "clientMessageId": "50000000-0000-4000-8000-000000000005",
            "tierId": "fast",
            "text": "hello from single mode",
            "agenticMode": "single",
        },
    )
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "PLATFORM_BUDGET_EXCEEDED"
