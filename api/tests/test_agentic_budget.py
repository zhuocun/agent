"""Per-run budget admission + mid-flight kill (M3, T5).

Drives the FAKE provider behind `TOOLS_ENABLED=true` + `AGENTIC_ENABLED=true`.
Covers:
- Pre-spawn reservation: when the worst-case estimate exceeds the effective
  cap, workers are NOT spawned and the turn ends in a labeled `done` synthesis
  (never `error`).
- Mid-flight kill: when actual accumulated worker cost breaches the cap, the
  run cancels remaining workers and synthesizes a partial answer labeled as
  budget-halted.
- `run_cost` ticks surface the configured cap on the wire.
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

from app.agentic import budget
from app.config import get_settings
from app.db.models import Conversation, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import UsageUpdate
from app.providers.tiers import get_binding

# Fixtures ---------------------------------------------------------------------


@pytest.fixture
def agentic_env() -> Iterator[None]:
    """Tool-calling + agentic flags ON; per-test budget knobs via monkeypatch."""
    prior_tools = os.environ.get("TOOLS_ENABLED")
    prior_agentic = os.environ.get("AGENTIC_ENABLED")
    prior_budget = os.environ.get("AGENTIC_RUN_BUDGET_USD")
    os.environ["TOOLS_ENABLED"] = "true"
    os.environ["AGENTIC_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, prior in (
            ("TOOLS_ENABLED", prior_tools),
            ("AGENTIC_ENABLED", prior_agentic),
            ("AGENTIC_RUN_BUDGET_USD", prior_budget),
        ):
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
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


def _names(frames: list[tuple[str, dict[str, object]]]) -> list[str]:
    return [name for name, _ in frames]


def _answer(frames: list[tuple[str, dict[str, object]]]) -> str:
    return "".join(str(d.get("text", "")) for n, d in frames if n == "answer_delta")


def _fake_worker_cost() -> float:
    """USD cost of one fake deep-research worker completion (smart tier)."""
    binding = get_binding("smart")
    usage = UsageUpdate(input_tokens=50, output_tokens=100, reasoning_tokens=10)
    breakdown = compute_cost_breakdown(usage=usage, binding=binding)
    return breakdown.subtotal_usd + breakdown.session_surcharge_usd


# Unit-level budget math -------------------------------------------------------


def test_effective_cap_composes_headroom() -> None:
    assert budget.effective_cap(cap_usd=1.0, headroom_usd=0.25) == 0.25
    assert budget.effective_cap(cap_usd=0.25, headroom_usd=1.0) == 0.25
    # BYOK / unlimited headroom: cap only.
    assert budget.effective_cap(cap_usd=1.0, headroom_usd=None) == 1.0
    # SAF-003 / BE-018: numeric 0 means ZERO remaining, not unlimited.
    assert budget.effective_cap(cap_usd=1.0, headroom_usd=0.0) == 0.0
    assert budget.effective_cap(cap_usd=1.0, headroom_usd=-5.0) == 0.0


def test_admit_rejects_zero_headroom() -> None:
    decision = budget.admit(estimated_usd=0.01, cap_usd=1.0, headroom_usd=0.0)
    assert decision.admitted is False
    assert decision.effective_cap_usd == 0.0


def test_compose_headroom_mins_finite_sources() -> None:
    assert budget.compose_headroom(None, None) is None
    assert budget.compose_headroom(1.0, None) == 1.0
    assert budget.compose_headroom(1.0, 0.25) == 0.25
    assert budget.compose_headroom(0.0, 5.0) == 0.0


def test_admit_rejects_over_estimate() -> None:
    decision = budget.admit(estimated_usd=2.0, cap_usd=1.0, headroom_usd=None)
    assert decision.admitted is False
    assert decision.effective_cap_usd == 1.0


# Integration ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_spawn_estimate_exceeds_cap_no_workers_spawned(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the estimate cannot fit the cap, fan-out never starts."""
    monkeypatch.setenv("AGENTIC_RUN_BUDGET_USD", "0.000001")
    get_settings.cache_clear()

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: topic a | topic b",
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["status"] == "done"

    started = [d for n, d in frames if n == "subagent_started"]
    worker_started = [d for d in started if d.get("role") == "worker"]
    assert worker_started == []

    answer = _answer(frames)
    assert "not started" in answer.lower() or "exceeds" in answer.lower()

    run_cost = next((d for n, d in frames if n == "run_cost"), None)
    assert run_cost is not None
    assert run_cost["capUsd"] == pytest.approx(0.000001)


@pytest.mark.asyncio
async def test_mid_flight_cap_halts_partial_synthesis(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actual cost breach cancels remaining workers and labels a partial answer."""
    worker_cost = _fake_worker_cost()
    # The FR-26g worst-case estimate dwarfs fake-provider actuals, so patch the
    # estimator down for this test: admit the run, then let the mid-flight
    # actual-cost check fire after the first worker's `SubagentDone`.
    cap = worker_cost * 1.5
    monkeypatch.setenv("AGENTIC_RUN_BUDGET_USD", str(cap))

    def _low_estimate(**_kwargs: object) -> float:
        return worker_cost * 0.5

    monkeypatch.setattr(budget, "estimate_run_cost", _low_estimate)
    get_settings.cache_clear()

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: topic a | topic b",
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["status"] == "done"

    answer = _answer(frames)
    assert "Partial answer" in answer or "partial" in answer.lower()

    started = [d for n, d in frames if n == "subagent_started" and d.get("role") == "worker"]
    # At least one worker started; budget kill should prevent both from completing
    # when the cap only fits ~1 worker.
    assert 1 <= len(started) <= 2


def test_estimate_cost_defaults_unchanged() -> None:
    settings = get_settings()
    binding = get_binding("smart")
    estimate = budget.estimate_run_cost(
        sub_question_count=2,
        binding=binding,
        settings=settings,
    )
    per_subagent = budget._expected_subagent_usage(settings)
    breakdown = compute_cost_breakdown(usage=per_subagent, binding=binding)
    base = breakdown.subtotal_usd + breakdown.session_surcharge_usd
    # BE-016: planner + workers + aggregator (verifier off adds 0).
    subagents = 1 + 2 + 1
    expected = (
        base
        * subagents
        * settings.agentic_reasoning_token_multiplier
        * settings.agentic_fanout_token_multiplier
    )
    assert estimate == pytest.approx(expected)


def test_subagent_count_reserves_verifier_judge_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTIC_VERIFIER", "true")
    monkeypatch.setenv("AGENTIC_VERIFIER_N", "5")
    get_settings.cache_clear()
    settings = get_settings()
    # Real verifier reserves N judge samples (not N phantom full workers beyond).
    assert budget._subagent_count(2, settings) == 1 + 2 + 1 + 5
    get_settings.cache_clear()


def test_subagent_count_verifier_off_excludes_n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTIC_VERIFIER", "false")
    monkeypatch.setenv("AGENTIC_VERIFIER_N", "5")
    get_settings.cache_clear()
    settings = get_settings()
    assert budget._subagent_count(2, settings) == 1 + 2 + 1
    get_settings.cache_clear()


def test_assert_prod_safe_rejects_nonpositive_multiplier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTIC_REASONING_TOKEN_MULTIPLIER", "0")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="AGENTIC_REASONING_TOKEN_MULTIPLIER"):
        get_settings().assert_prod_safe()
    get_settings.cache_clear()


def test_phase_gates_use_the_same_composition() -> None:
    """FL-17 (COST-4): one composition for both single-phase funding gates.

    The verifier gate multiplied in the FAN-OUT multiplier as well, making it
    ~15x stricter than the aggregator gate for an identical one-shot call. The
    fan-out multiplier models whole-run burn and stays in `estimate_run_cost`.
    """
    from app.agentic.orchestrator import _verifier_phase_estimate

    monkey_settings = get_settings()
    binding = get_binding("smart")

    def _price(usage: UsageUpdate) -> float:
        breakdown = compute_cost_breakdown(usage=usage, binding=binding)
        return breakdown.subtotal_usd + breakdown.session_surcharge_usd

    expected = budget._expected_subagent_usage(monkey_settings)
    aggregator_estimate = (
        _price(expected) * monkey_settings.agentic_reasoning_token_multiplier
    )
    # The verifier gate is only reachable with the flag on; the composition is
    # what this pins, so read it off a verifier-enabled copy of the settings.
    verifier_settings = monkey_settings.model_copy(update={"agentic_verifier": True})
    assert _verifier_phase_estimate(
        settings=verifier_settings, cost_for_usage=_price, sample_count=1
    ) == pytest.approx(aggregator_estimate)
    # N samples scale linearly off that same single-phase base.
    assert _verifier_phase_estimate(
        settings=verifier_settings, cost_for_usage=_price, sample_count=3
    ) == pytest.approx(aggregator_estimate * 3)
    # Whole-run estimation still keeps BOTH multipliers (guards the pin above).
    assert monkey_settings.agentic_fanout_token_multiplier > 1.0
    run_estimate = budget.estimate_run_cost(
        sub_question_count=2, binding=binding, settings=monkey_settings
    )
    assert run_estimate == pytest.approx(
        _price(expected)
        * (1 + 2 + 1)
        * monkey_settings.agentic_reasoning_token_multiplier
        * monkey_settings.agentic_fanout_token_multiplier
    )


@pytest.mark.asyncio
async def test_single_mode_budget_halt_with_no_prose_is_labeled() -> None:
    """FL-13 (ORCH-4): a halt before any prose is a budget stop, not a blank turn.

    `main_answer_is_empty` was tested first and short-circuited the budget label,
    so the delivered text said the model "didn't produce a written reply" while
    the wire flag claimed a budget halt.
    """
    from collections.abc import AsyncIterator as _AsyncIterator

    from app.agentic.orchestrator import run_orchestrator
    from app.config import Settings
    from app.providers.protocol import (
        ProviderEvent,
        ReasoningDelta,
        RunCost,
        ToolResult,
    )
    from app.streaming.constants import EMPTY_REPLY_FALLBACK

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> _AsyncIterator[ProviderEvent]:
            async def _gen() -> _AsyncIterator[ProviderEvent]:
                yield ReasoningDelta(text="thinking hard")
                yield UsageUpdate(input_tokens=1_000_000, output_tokens=0)

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_PLAN_APPROVAL=False,
        AGENTIC_VERIFIER=False,
        AGENTIC_RUN_BUDGET_USD=0.5,
    )
    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=settings,
            mode="single",
            user_text="hi",
            cost_for_usage=lambda u: 1e-6 * float(u.input_tokens),
        )
    ]
    answer = "".join(
        e.text for e in events if type(e).__name__ == "AnswerDelta"
    )
    assert "stay within the run budget" in answer
    # The no-written-reply copy may still prefix it — it must not REPLACE it.
    assert answer.startswith(EMPTY_REPLY_FALLBACK)
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].partial is True
    assert finals[-1].budget_halted is True


@pytest.mark.asyncio
async def test_deep_research_admit_reject_reports_budget_halted(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-21 (COST-6): the admit-reject was the only refusal reporting a clean run.

    Every other budget refusal flags `budget_halted`; this one shipped default
    flags, so the receipt and the persisted run summary read as a complete answer.
    """
    from app.db.models import Message

    monkeypatch.setenv("AGENTIC_RUN_BUDGET_USD", "0.000001")
    get_settings.cache_clear()

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: topic a | topic b",
            "agenticMode": "deep_research",
        },
    )
    assert frames[-1][1]["status"] == "done"
    started = [d for n, d in frames if n == "subagent_started"]
    assert [d for d in started if d.get("role") == "worker"] == []

    finals = [
        d for n, d in frames if n == "run_cost" and d.get("phase") == "final"
    ]
    assert finals, "admit-reject must still emit a final receipt"
    assert finals[-1]["partial"] is True
    assert finals[-1]["budgetHalted"] is True

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Message).where(Message.conversation_id == UUID(str(conv_id)))
                )
            )
            .scalars()
            .all()
        )
    assistant = next(m for m in rows if m.role == "assistant")
    summary = next(
        p
        for p in (assistant.parts or [])
        if isinstance(p, dict) and p.get("type") == "agentic_run_summary"
    )
    assert summary["outcome"] == "partial"
    assert summary["budgetHalted"] is True
