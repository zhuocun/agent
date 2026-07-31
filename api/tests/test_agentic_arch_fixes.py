"""Pinning tests for agentic architecture review fixes (B2-B16/B24)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from app.agentic import aggregate
from app.agentic import orchestrator as orchestrator_mod
from app.agentic import sources as sources_mod
from app.agentic.aggregate import WorkerOutput
from app.agentic.continuation import (
    RESERVED_CONTROL_KEYS,
    AgenticContinuation,
    CompletedWorkerState,
    parse_continuation,
    serialize_continuation,
)
from app.agentic.orchestrator import (
    _finalize_synthesis_streamed,
    _maybe_plan_approval,
    _resume_worker_continuation,
    run_orchestrator,
)
from app.agentic.sources import CitationAllocation, SourceNamespace
from app.config import Settings
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    RunCost,
    Sources,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.search.protocol import SourceItem


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "PROVIDER_BACKEND": "fake",
        "AGENTIC_ENABLED": True,
        "TOOLS_ENABLED": True,
        "AGENTIC_PLAN_APPROVAL": False,
        "AGENTIC_VERIFIER": False,
        "AGENTIC_MAX_WORKERS": 2,
        "AGENTIC_RUN_BUDGET_USD": 10.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _cont(**kwargs: object) -> AgenticContinuation:
    defaults: dict[str, object] = {
        "phase": "worker",
        "paused_subagent_id": "worker-0",
        "user_text": "DEEP_RESEARCH: alpha | beta",
        "plan": ("alpha", "beta"),
        "completed_workers": (
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=2, output_tokens=1),
                cost_usd=0.2,
            ),
        ),
        "planner_usage": UsageUpdate(input_tokens=1, output_tokens=1),
        "planner_cost_usd": 0.1,
        "budget_halted": False,
        "actual_cost_usd": 0.5,
        "paused_worker_index": 0,
        "paused_sub_question": "alpha",
        "partial_answer": "pre ",
        "orchestration_mode": "deep_research",
        "paused_worker_usage": UsageUpdate(input_tokens=10, output_tokens=5),
        "paused_worker_cost_usd": 0.2,
    }
    defaults.update(kwargs)
    return AgenticContinuation(**defaults)  # type: ignore[arg-type]


def _seed() -> ToolResult:
    return ToolResult(
        tool_call_id="worker-0::x",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )


@pytest.mark.asyncio
async def test_b2_resume_ledger_adds_full_resume_cost() -> None:
    """B2: post-resume usage must not be double-subtracted against pre_pause."""

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="post")
                # Resume-only usage (does NOT include pre-pause tokens).
                yield Complete(usage=UsageUpdate(input_tokens=4, output_tokens=2))

            return _gen()

        return _make

    # $0.01 per input token.
    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=_settings(),
            cost_for_usage=lambda u: float(u.input_tokens) * 0.01,
            continuation=_cont(
                actual_cost_usd=0.5,  # already includes pre_pause 0.2
                paused_worker_usage=UsageUpdate(input_tokens=10, output_tokens=5),
                paused_worker_cost_usd=0.2,
            ),
            resume_tool_result=_seed(),
            server_approved_call_ids=set(),
        )
    ]
    done = next(
        e for e in events if isinstance(e, SubagentDone) and e.subagent_id == "worker-0"
    )
    # Cumulative attribution: stored pre_pause cost (0.2) + resume (4 * 0.01).
    assert done.usage.input_tokens == 14
    assert done.cost_usd == pytest.approx(0.24)
    final_costs = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert final_costs
    # Ledger: 0.5 pre + 0.04 resume = 0.54 (+ aggregator ~0).
    assert final_costs[-1].subtotal_usd >= 0.54 - 1e-9


@pytest.mark.asyncio
async def test_b3_resume_breaks_drain_when_budget_halted() -> None:
    """B3: resume drain stops after cap breach (mirrors _run_single)."""
    yielded: list[str] = []

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield UsageUpdate(input_tokens=100, output_tokens=0)
                yielded.append("usage")
                yield AnswerDelta(text="should-not-matter")
                yielded.append("answer")
                yield Complete(usage=UsageUpdate(input_tokens=100, output_tokens=1))
                yielded.append("complete")
                yield AnswerDelta(text="after-complete-should-not-run")
                yielded.append("after")

            return _gen()

        return _make

    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=_settings(AGENTIC_RUN_BUDGET_USD=0.05),
            cost_for_usage=lambda u: float(u.input_tokens) * 0.01,
            continuation=_cont(
                actual_cost_usd=0.01,
                paused_worker_usage=UsageUpdate(),
                paused_worker_cost_usd=0.0,
                partial_answer="",
            ),
            resume_tool_result=_seed(),
            server_approved_call_ids=set(),
        )
    ]
    assert "after" not in yielded
    assert any(
        isinstance(e, SubagentDone) and e.outcome == "budget_cancelled" for e in events
    )


@pytest.mark.asyncio
async def test_b3_fanout_provisional_usage_cancels_workers() -> None:
    """B3: mid-flight UsageUpdate can breach the cap before SubagentDone."""
    started = asyncio.Event()
    cancelled = {"slow": False}

    async def _fast(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        yield UsageUpdate(input_tokens=80, output_tokens=0)
        started.set()
        yield AnswerDelta(text="fast")
        yield Complete(usage=UsageUpdate(input_tokens=80, output_tokens=1))

    async def _slow(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        await started.wait()
        try:
            await asyncio.sleep(60)
            yield AnswerDelta(text="late")
            yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))
        except asyncio.CancelledError:
            cancelled["slow"] = True
            raise

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _fast(_feedback, suppress_tools)
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _slow(_feedback, suppress_tools)

            async def _agg() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="agg")
                yield Complete(usage=UsageUpdate())

            return _agg()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(AGENTIC_RUN_BUDGET_USD=0.5),
            mode="deep_research",
            user_text="DEEP_RESEARCH: a | b",
            # 80 tokens * 0.01 = 0.8 > 0.5 cap mid-flight.
            cost_for_usage=lambda u: float(u.input_tokens) * 0.01,
        )
    ]
    assert cancelled["slow"] is True
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].budget_halted is True


@pytest.mark.asyncio
async def test_b4_plan_approval_persists_planner_cost_and_seeds_ledger() -> None:
    """B4: pause stamps plannerCostUsd; resume seeds actual_cost without re-bill."""
    settings = _settings(AGENTIC_PLAN_APPROVAL=True, PROVIDER_BACKEND="openai", OPENAI_API_KEY="sk")
    pause_events = [
        ev
        async for ev in _maybe_plan_approval(
            settings,
            ["q1", "q2"],
            estimate_usd=1.0,
            cap_usd=5.0,
            planner_cost_usd=0.37,
            planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
        )
    ]
    tool = next(e for e in pause_events if isinstance(e, ToolCall))
    assert tool.input is not None
    assert tool.input.get("plannerCostUsd") == 0.37
    assert "plannerCostUsd" in RESERVED_CONTROL_KEYS
    assert "plannerUsage" in RESERVED_CONTROL_KEYS

    seen_prompts: list[str] = []

    def _make_stream_for(prompt: str, **_kwargs: object):
        seen_prompts.append(prompt)

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="ok")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(),
            mode="deep_research",
            user_text="ignored",
            cost_for_usage=lambda u: float(u.input_tokens) * 0.01,
            plan_approved=True,
            approved_plan=["alpha", "beta"],
            prior_planner_cost_usd=0.37,
            prior_planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
        )
    ]
    # No planner receipt Complete (empty live planner_usage).
    planner_completes = [
        e
        for e in events
        if isinstance(e, Complete) and getattr(e, "subagent_id", None) == "planner"
    ]
    assert planner_completes == []
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals
    # Seeded 0.37 + two workers (0.01 each) + agg 0.
    assert finals[-1].subtotal_usd >= 0.37


@pytest.mark.asyncio
async def test_b5_single_mode_prior_run_cost_seeds_ledger() -> None:
    """B5: single-mode resume can seed prior_run_cost without resetting the cap."""

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="hello")
                yield Complete(usage=UsageUpdate(input_tokens=5, output_tokens=1))

            return _gen()

        return _make

    # Tiny unit price so pre-admit estimate still fits the run cap.
    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(AGENTIC_RUN_BUDGET_USD=100.0),
            mode="single",
            user_text="hi",
            cost_for_usage=lambda u: 1e-6 * float(u.input_tokens + u.output_tokens),
            prior_run_cost_usd=0.2,
            prior_run_usage=UsageUpdate(input_tokens=20, output_tokens=0),
        )
    ]
    done = next(e for e in events if isinstance(e, SubagentDone) and e.role == "primary")
    assert done.outcome == "succeeded"
    assert done.usage.input_tokens == 25  # 20 prior + 5 session
    assert done.cost_usd == pytest.approx(0.2 + 1e-6 * 6)
    untagged = [
        e for e in events if isinstance(e, Complete) and e.subagent_id is None
    ]
    assert untagged and untagged[-1].usage.input_tokens == 25


@pytest.mark.asyncio
async def test_b6_fallback_pause_flag_round_trips_and_prices() -> None:
    """B6: used_fallback persists on continuation and prices via fallback pricer."""
    cont = _cont(
        paused_worker_used_fallback=True,
        paused_worker_usage=UsageUpdate(input_tokens=2, output_tokens=0),
        paused_worker_cost_usd=1.0,  # fallback-priced
    )
    blob = serialize_continuation(cont)
    assert blob["pausedWorkerUsedFallback"] is True
    parsed = parse_continuation(blob)
    assert parsed is not None
    assert parsed.paused_worker_used_fallback is True

    primary_calls = {"n": 0}
    fallback_calls = {"n": 0}

    def _primary(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                primary_calls["n"] += 1
                raise AssertionError("must pin to fallback")
                yield AnswerDelta(text="x")  # pragma: no cover

            return _gen()

        return _make

    def _fallback(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                fallback_calls["n"] += 1
                yield AnswerDelta(text="fb")
                yield Complete(usage=UsageUpdate(input_tokens=3, output_tokens=1))

            return _gen()

        return _make

    events = [
        ev
        async for ev in _resume_worker_continuation(
            make_stream_for=_primary,
            settings=_settings(),
            cost_for_usage=lambda u: float(u.input_tokens) * 0.01,
            continuation=cont,
            resume_tool_result=_seed(),
            server_approved_call_ids=set(),
            fallback_make_stream_for=_fallback,
            fallback_cost_for_usage=lambda u: float(u.input_tokens) * 0.5,
            fallback_provider_id="openai",
            fallback_model_id="gpt-test",
            fallback_display_label="GPT Test",
        )
    ]
    assert primary_calls["n"] == 0
    assert fallback_calls["n"] >= 1
    done = next(
        e for e in events if isinstance(e, SubagentDone) and e.subagent_id == "worker-0"
    )
    # pre 2*0.5=1.0 stored; resume 3*0.5=1.5; cumulative cost = 1.0+1.5=2.5
    assert done.cost_usd == pytest.approx(2.5)
    assert done.substituted_provider == "openai"


@pytest.mark.asyncio
async def test_b8_aggregator_exception_falls_back_to_synthesize() -> None:
    """B8: aggregator failure emits failed receipt + deterministic synthesis."""

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                raise RuntimeError("aggregator boom")
                yield AnswerDelta(text="x")  # pragma: no cover

            return _gen()

        return _make

    outputs = [
        WorkerOutput(subagent_id="worker-0", sub_question="q", answer="finding-a"),
    ]
    events = [
        ev
        async for ev in _finalize_synthesis_streamed(
            make_stream_for=_make_stream_for,
            settings=_settings(PROVIDER_BACKEND="openai", OPENAI_API_KEY="sk"),
            user_text="original",
            outputs=outputs,
            planned=1,
            worker_usages=[UsageUpdate(input_tokens=1)],
            worker_total_cost=0.01,
            cost_for_usage=lambda u: 0.01,
            cap_usd=1.0,
            budget_halted=False,
            scaffolded=False,
        )
    ]
    texts = "".join(
        getattr(e, "text", "") for e in events if isinstance(e, AnswerDelta)
    )
    assert "finding-a" in texts
    done = next(e for e in events if isinstance(e, SubagentDone) and e.role == "aggregator")
    assert done.outcome == "failed"
    assert any(isinstance(e, Complete) and e.subagent_id is None for e in events)
    assert any(isinstance(e, RunCost) and e.partial for e in events)


@pytest.mark.asyncio
async def test_c1_aggregator_partial_draft_is_not_re_emitted() -> None:
    """FL-07 (C-1): live-relayed aggregator text must not be prepended again.

    On the verifier-off path the partial draft was already streamed to the user;
    prepending it to the deterministic fallback delivered the same prose twice,
    live and on reload.
    """

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="PARTIAL-DRAFT-MARKER")
                raise RuntimeError("aggregator boom")

            return _gen()

        return _make

    events = [
        ev
        async for ev in _finalize_synthesis_streamed(
            make_stream_for=_make_stream_for,
            settings=_settings(PROVIDER_BACKEND="openai", OPENAI_API_KEY="sk"),
            user_text="original",
            outputs=[
                WorkerOutput(subagent_id="worker-0", sub_question="q", answer="finding-a")
            ],
            planned=1,
            worker_usages=[UsageUpdate(input_tokens=1)],
            worker_total_cost=0.01,
            cost_for_usage=lambda _u: 0.0,
            cap_usd=1.0,
            budget_halted=False,
            scaffolded=False,
        )
    ]
    texts = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert texts.count("PARTIAL-DRAFT-MARKER") == 1
    # FL-06: the degrade label names a synthesis failure, and the flag agrees.
    assert "synthesis failed" in texts
    assert "run budget" not in texts
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].partial is True
    assert finals[-1].budget_halted is False


@pytest.mark.asyncio
async def test_c1_quiet_collect_still_prepends_its_unrelayed_draft() -> None:
    """FL-07 twin: quiet-collect relayed nothing, so it MUST still prepend."""

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="QUIET-DRAFT-MARKER")
                raise RuntimeError("aggregator boom")

            return _gen()

        return _make

    events = [
        ev
        async for ev in _finalize_synthesis_streamed(
            make_stream_for=_make_stream_for,
            settings=_settings(
                PROVIDER_BACKEND="openai", OPENAI_API_KEY="sk", AGENTIC_VERIFIER=True
            ),
            user_text="original",
            outputs=[
                WorkerOutput(subagent_id="worker-0", sub_question="q", answer="finding-a")
            ],
            planned=1,
            worker_usages=[UsageUpdate(input_tokens=1)],
            worker_total_cost=0.01,
            cost_for_usage=lambda _u: 0.0,
            cap_usd=1.0,
            budget_halted=False,
            scaffolded=False,
        )
    ]
    texts = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert texts.count("QUIET-DRAFT-MARKER") == 1


@pytest.mark.asyncio
async def test_b5_single_mode_over_cap_seed_halts_before_provider_call() -> None:
    """FL-12 (ORCH-2): a seeded ledger already over cap must not open a stream.

    Admission prices only the FRESH estimate, so a resume whose prior spend is
    already over the cap used to overrun by a whole primary turn.
    """
    invocations = {"n": 0}

    def _make_stream_for(prompt: str, **_kwargs: object):
        invocations["n"] += 1

        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:  # pragma: no cover
                # Would park an actionable approval card if the stream opened.
                yield ToolCall(
                    id="c1",
                    name="calendar_create_event",
                    status="running",
                    input={"title": "x"},
                )
                yield Complete(usage=UsageUpdate(input_tokens=1))

            return _gen()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(AGENTIC_RUN_BUDGET_USD=1.0),
            mode="single",
            user_text="hi",
            cost_for_usage=lambda u: 1e-9 * float(u.input_tokens),
            prior_run_cost_usd=5.0,
            prior_run_usage=UsageUpdate(input_tokens=10, output_tokens=5),
        )
    ]
    assert invocations["n"] == 0
    assert not any(isinstance(e, AwaitingApproval) for e in events)
    texts = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert "stay within the run budget" in texts
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].budget_halted is True
    assert finals[-1].partial is True
    # Still a labeled `done`, never an error or a hang.
    done = next(e for e in events if isinstance(e, SubagentDone) and e.role == "primary")
    assert done.outcome == "budget_cancelled"
    assert any(isinstance(e, Complete) and e.subagent_id is None for e in events)


@pytest.mark.asyncio
async def test_b5_single_mode_midflight_halt_parks_no_approval_card() -> None:
    """FL-12: a mid-flight halt must not hand the user an actionable card.

    The gated tool is requested only after the cap-breaching `UsageUpdate`, so
    the halt has to win over the pause. The turn still ends as a labeled `done`
    (invariant 8) rather than an error or a parked approval.
    """

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield UsageUpdate(input_tokens=1_000_000)
                yield ToolCall(
                    id="c1",
                    name="calendar_create_event",
                    status="running",
                    input={"title": "x"},
                )

            return _gen()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(AGENTIC_RUN_BUDGET_USD=0.5),
            mode="single",
            user_text="hi",
            cost_for_usage=lambda u: 1e-6 * float(u.input_tokens),
        )
    ]
    assert not any(isinstance(e, AwaitingApproval) for e in events)
    assert not any(
        isinstance(e, ToolCall) and e.status == "awaiting_approval" for e in events
    )
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].budget_halted is True
    assert finals[-1].partial is True
    texts = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert "stay within the run budget" in texts
    done = next(e for e in events if isinstance(e, SubagentDone) and e.role == "primary")
    assert done.outcome == "budget_cancelled"


def test_b12_cite_before_sources_never_yields_a_foreign_global_id() -> None:
    """FL-16-a (FE-1 / GAP-7): an unmapped marker must not resolve elsewhere.

    Returning the raw local ordinal let worker-1's `[1]` render as whichever
    source happened to own global id 1 — silent factual misattribution.
    """
    remapper = SourceNamespace()
    worker0 = remapper.remap_sources(
        Sources(
            items=[
                SourceItem(id=1, title="A1", url="https://a1.example"),
                SourceItem(id=2, title="A2", url="https://a2.example"),
            ]
        ),
        "worker-0",
    )
    worker0_ids = {str(item.id) for item in worker0.items}
    assert worker0_ids == {"1", "2"}

    # worker-1 cites before emitting its own Sources event.
    rewritten = remapper.rewrite_answer_text("Also see [1].", "worker-1")
    cited = re.findall(r"\[(\d+)\]", rewritten)
    assert cited
    assert not (set(cited) & worker0_ids)
    # The allocation is stable and unique — a later Sources event agrees.
    worker1 = remapper.remap_sources(
        Sources(items=[SourceItem(id=1, title="B", url="https://b.example")]),
        "worker-1",
    )
    assert str(worker1.items[0].id) == cited[0]


def test_b12_empty_map_marker_is_allocated_not_passed_through() -> None:
    """FL-16-a: the `if not self._map` early return took the same unsafe path."""
    remapper = SourceNamespace()
    remapper.seed_catalog(
        [SourceItem(id=1, title="prior", url="https://prior.example")]
    )
    # No live mappings yet; a cited marker must still allocate past the seed.
    assert remapper.rewrite_answer_text("See [1].", "worker-0") == "See [2]."


@pytest.mark.asyncio
async def test_b14_single_mode_emits_untagged_complete() -> None:
    """B14: single mode must emit untagged Complete for handler final_usage."""

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="hi")
                yield Complete(usage=UsageUpdate(input_tokens=7, output_tokens=3))

            return _gen()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(AGENTIC_RUN_BUDGET_USD=100.0),
            mode="single",
            user_text="hi",
            cost_for_usage=lambda u: 1e-6 * float(u.input_tokens + u.output_tokens),
        )
    ]
    untagged = [
        e for e in events if isinstance(e, Complete) and e.subagent_id is None
    ]
    assert len(untagged) >= 1
    assert untagged[-1].usage.input_tokens == 7


@pytest.mark.asyncio
async def test_b16_reasoning_delta_blocks_transparent_fallback() -> None:
    """B16: visible ReasoningDelta prohibits silent fallback retry."""
    fallback_calls = {"n": 0}

    def _primary(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield ReasoningDelta(text="thinking…")
                raise RuntimeError("retryable after reasoning")

            return _gen()

        return _make

    def _fallback(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                fallback_calls["n"] += 1
                yield AnswerDelta(text="fb")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_primary,
            settings=_settings(),
            mode="deep_research",
            user_text="DEEP_RESEARCH: only-one",
            cost_for_usage=lambda u: 0.01,
            fallback_make_stream_for=_fallback,
            fallback_cost_for_usage=lambda u: 0.01,
            is_retryable=lambda _exc: True,
        )
    ]
    assert fallback_calls["n"] == 0
    assert any(
        isinstance(e, SubagentDone) and e.role == "worker" and e.outcome == "failed"
        for e in events
    )


def test_b12_one_source_allocator_owns_the_run() -> None:
    """AC-08: `SourceNamespace` is the only source-ID allocator left.

    A second, list-ordered remapper in `aggregate` renumbered the same ordinals
    again in worker-plan order at the synthesis sink, so an offline caller could
    produce ids that disagreed with the arrival-ordered globals the live stream
    had already shown the user. Two static reads prove neither it nor the
    orchestrator-private class it shadowed grew back: only one module allocates a
    global id, and only one compiles the citation-marker pattern a rewriter needs.
    """
    app_root = Path(orchestrator_mod.__file__ or "").parent.parent
    owner = Path(sources_mod.__file__ or "").relative_to(app_root).as_posix()
    sources_by_marker = {
        path.relative_to(app_root).as_posix(): text
        for path in sorted(app_root.rglob("*.py"))
        for text in [path.read_text(encoding="utf-8")]
    }
    allocators = {name for name, text in sources_by_marker.items() if "_global_id" in text}
    rewriters = {
        name for name, text in sources_by_marker.items() if r"\[(\d+)\]" in text
    }
    assert allocators == {owner}
    assert rewriters == {owner}
    assert not [name for name in dir(aggregate) if "remap" in name]


def test_b12_source_item_type_still_int() -> None:
    """SourceItem.id remains int — remapper must keep wire-compatible ints."""
    item = SourceItem(id=1, title="t", url="https://example.com")
    assert isinstance(item.id, int)


def test_b12_midstream_remapper_arrival_order_and_catalog() -> None:
    """B12: mid-stream remapper assigns globals in event order and builds catalog."""
    remapper = SourceNamespace()
    # worker-1 finishes first (out of plan order) with local [1].
    s1 = remapper.remap_sources(
        Sources(
            items=[SourceItem(id=1, title="B", url="https://b.example")],
        ),
        "worker-1",
    )
    assert s1.items[0].id == 1
    # worker-0 finishes second with local [1, 2].
    s0 = remapper.remap_sources(
        Sources(
            items=[
                SourceItem(id=1, title="A1", url="https://a1.example"),
                SourceItem(id=2, title="A2", url="https://a2.example"),
            ],
        ),
        "worker-0",
    )
    assert [i.id for i in s0.items] == [2, 3]
    assert remapper.rewrite_answer_text("See [1] and [2].", "worker-0") == "See [2] and [3]."
    assert remapper.rewrite_answer_text("Also [1].", "worker-1") == "Also [1]."
    catalog = remapper.merged_items()
    assert [i.id for i in catalog] == [1, 2, 3]
    assert catalog[0].title == "B"
    assert catalog[1].title == "A1"


def test_b12_rewrite_is_chunk_safe_across_answer_deltas() -> None:
    """B12: markers split across AnswerDelta chunks still remap."""
    remapper = SourceNamespace()
    remapper.remap_sources(
        Sources(items=[SourceItem(id=1, title="B", url="https://b.example")]),
        "worker-1",
    )
    remapper.remap_sources(
        Sources(items=[SourceItem(id=1, title="A", url="https://a.example")]),
        "worker-0",
    )
    # worker-0 local [1] → global [2]; split "See [1]." across two deltas.
    part1 = remapper.rewrite_answer_text("See [", "worker-0")
    part2 = remapper.rewrite_answer_text("1].", "worker-0")
    assert part1 == "See "
    assert part2 == "[2]."
    assert remapper.flush_answer_carry("worker-0") == ""


def test_b12_resume_remapper_seeds_catalog_without_collision() -> None:
    """B12: resume remapper continues after seeded catalog ids."""
    prior = [
        SourceItem(id=1, title="old", url="https://old.example"),
        SourceItem(id=2, title="old2", url="https://old2.example"),
    ]
    remapper = SourceNamespace()
    remapper.seed_catalog(prior)
    # Resume-session local id 1 must become global 3, not collide with 1.
    remapped = remapper.remap_sources(
        Sources(items=[SourceItem(id=1, title="new", url="https://new.example")]),
        "worker-0",
    )
    assert remapped.items[0].id == 3
    assert [i.id for i in remapper.merged_items()] == [1, 2, 3]


def test_b12_restore_does_not_reissue_a_citation_only_global() -> None:
    """AC-08: a citation-only id above the catalog maximum stays taken on resume.

    Worker 0 published catalog id 1; worker 1 then cited `[1]` before its own
    `Sources` arrived, which allocated global 2 and rendered it to the user.
    Global 2 has no catalog row, so restoring from the catalog alone left the
    high-water mark at 2 and handed that id to the resumed worker's first new
    source — the reader's `[2]` then pointed at unrelated content.
    """
    live = SourceNamespace()
    live.remap_sources(
        Sources(items=[SourceItem(id=1, title="A", url="https://a.example")]), "worker-0"
    )
    published = live.rewrite_answer_text("Also see [1].", "worker-1")
    assert published == "Also see [2]."
    assert max(item.id for item in live.merged_items()) == 1

    resumed = SourceNamespace.restored(
        catalog=tuple(live.merged_items()),
        allocations=live.allocations(),
        next_id=live.next_id,
    )
    fresh = resumed.remap_sources(
        Sources(items=[SourceItem(id=9, title="new", url="https://new.example")]),
        "worker-2",
    )
    assert fresh.items[0].id == 3
    # The paused worker's own marker still resolves to the id already rendered.
    assert resumed.rewrite_answer_text("Still [1].", "worker-1") == "Still [2]."
    assert [item.id for item in resumed.merged_items()] == [1, 3]


def test_b12_continuation_roundtrips_the_source_allocator_state() -> None:
    """B12/AC-08: the checkpoint carries the catalog AND the allocator state.

    The allocator state is what makes a citation-only global survive the pause,
    so it has to cross the JSON column with the catalog rather than be inferred
    from it on the way back.
    """
    live = SourceNamespace()
    live.remap_sources(
        Sources(items=[SourceItem(id=1, title="one", url="https://one.example")]),
        "worker-0",
    )
    live.remap_sources(
        Sources(items=[SourceItem(id=1, title="two", url="https://two.example")]),
        "worker-1",
    )
    assert live.rewrite_answer_text("cite [7].", "worker-1") == "cite [3]."
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="q",
        plan=("a", "b"),
        completed_workers=(),
        planner_usage=UsageUpdate(),
        planner_cost_usd=0.0,
        source_catalog=tuple(live.merged_items()),
        source_allocations=live.allocations(),
        source_next_id=live.next_id,
    )
    blob = serialize_continuation(cont)
    assert len(blob["sourceCatalog"]) == 2
    assert blob["sourceNextId"] == 4
    assert {"subagentId": "worker-1", "localId": 7, "globalId": 3} in blob[
        "sourceAllocations"
    ]
    parsed = parse_continuation(blob)
    assert parsed is not None
    assert len(parsed.source_catalog) == 2
    assert parsed.source_catalog[0].id == 1
    assert parsed.source_catalog[1].title == "two"
    assert parsed.source_next_id == 4
    assert CitationAllocation(subagent_id="worker-1", local_id=7, global_id=3) in (
        parsed.source_allocations
    )
    restored = SourceNamespace.restored(
        catalog=parsed.source_catalog,
        allocations=parsed.source_allocations,
        next_id=parsed.source_next_id,
    )
    assert restored.rewrite_answer_text("cite [7].", "worker-1") == "cite [3]."
    assert restored.next_id == 4


def test_b12_legacy_checkpoint_without_allocator_state_still_clears_cited_ids() -> None:
    """A checkpoint written before the allocator state was persisted has only the
    ids its surviving rows cite; allocation must resume above the highest."""
    restored = SourceNamespace.restored(
        catalog=(),
        prior_id_groups=[("1", "not-a-number"), ("4", "2")],
    )
    remapped = restored.remap_sources(
        Sources(items=[SourceItem(id=1, title="new", url="https://new.example")]),
        "worker-0",
    )
    assert remapped.items[0].id == 5
    # Nothing published yet: allocation starts at 1 rather than skipping an id.
    fresh = SourceNamespace.restored(catalog=(), prior_id_groups=[(), ("",)])
    assert fresh.rewrite_answer_text("See [1].", "worker-0") == "See [1]."
    # A persisted catalog is a precise record and wins over the cited floor.
    seeded = SourceNamespace.restored(
        catalog=(SourceItem(id=7, title="old", url="https://old.example"),),
        prior_id_groups=[("2",)],
    )
    assert seeded.rewrite_answer_text("See [1].", "worker-0") == "See [8]."
    assert [i.id for i in seeded.merged_items()] == [7]


@pytest.mark.asyncio
async def test_b12_fanout_emits_aggregator_merged_sources() -> None:
    """B12: synthesis emits one aggregator-tagged Sources before AnswerDelta."""

    def _make_stream_for(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                # Workers: emit local Sources then answer.
                if "DEEP_RESEARCH_WORKER:" in prompt:
                    suffix = "w0" if "alpha" in prompt else "w1"
                    yield Sources(
                        items=[
                            SourceItem(
                                id=1,
                                title=f"t-{suffix}",
                                url=f"https://{suffix}.example",
                            )
                        ]
                    )
                    yield AnswerDelta(text=f"finding [{1}] from {suffix}")
                else:
                    yield AnswerDelta(text="ok")
                usage = UsageUpdate(input_tokens=1, output_tokens=1)
                yield usage
                yield Complete(usage=usage)

            return _gen()

        return _make

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=_settings(),
            mode="deep_research",
            user_text="DEEP_RESEARCH: alpha | beta",
            cost_for_usage=lambda u: 0.01,
        )
    ]
    agg_started = next(
        i
        for i, e in enumerate(events)
        if isinstance(e, SubagentStarted) and e.subagent_id == "aggregator"
    )
    agg_sources = [
        (i, e)
        for i, e in enumerate(events)
        if isinstance(e, Sources) and e.subagent_id == "aggregator"
    ]
    assert agg_sources, "expected merged Sources tagged aggregator"
    src_idx, src_ev = agg_sources[0]
    assert src_idx > agg_started
    first_agg_answer = next(
        i
        for i, e in enumerate(events)
        if isinstance(e, AnswerDelta) and e.subagent_id == "aggregator"
    )
    assert src_idx < first_agg_answer
    assert len(src_ev.items) == 2
    assert [item.id for item in src_ev.items] == [1, 2]
    titles = {item.title for item in src_ev.items}
    assert titles == {"t-w0", "t-w1"}


def test_b23_fanout_queue_bound_is_documented() -> None:
    from app.agentic.orchestrator import _FANOUT_QUEUE_MAXSIZE

    assert _FANOUT_QUEUE_MAXSIZE == 256


def test_b23_queue_put_nowait_drop_oldest() -> None:
    """B23: teardown put drops oldest unprotected events instead of blocking."""
    import asyncio

    from app.agentic.orchestrator import _queue_put_nowait_drop_oldest

    queue: asyncio.Queue[object] = asyncio.Queue(maxsize=2)
    queue.put_nowait(1)
    queue.put_nowait(2)
    _queue_put_nowait_drop_oldest(queue, 3)
    assert queue.qsize() == 2
    assert queue.get_nowait() == 2
    assert queue.get_nowait() == 3


def test_b23_queue_put_never_drops_sentinels() -> None:
    """B23: a queued worker sentinel must survive a full-queue teardown put."""
    import asyncio

    from app.agentic.orchestrator import (
        _queue_put_nowait_drop_oldest,
        _WorkerSentinel,
    )

    queue: asyncio.Queue[object] = asyncio.Queue(maxsize=2)
    queue.put_nowait(_WorkerSentinel(subagent_id="worker-a"))
    queue.put_nowait("event-1")
    _queue_put_nowait_drop_oldest(queue, _WorkerSentinel(subagent_id="worker-b"))
    items = [queue.get_nowait(), queue.get_nowait()]
    assert any(
        isinstance(i, _WorkerSentinel) and i.subagent_id == "worker-a" for i in items
    )
    assert any(
        isinstance(i, _WorkerSentinel) and i.subagent_id == "worker-b" for i in items
    )


# FL-33-a: run-summary persist gate ------------------------------------------
#
# Both gates live in `stream_and_persist` closures, so the only way to observe
# them is through the handler. The orchestrator is stubbed out so the test owns
# the exact `RunCost` shape each arm emits.


@pytest.fixture
def handler_agentic_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Both flags on, so `stream_and_persist` takes the agentic path."""
    from app.config import get_settings

    monkeypatch.setenv("TOOLS_ENABLED", "true")
    monkeypatch.setenv("AGENTIC_ENABLED", "true")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


class _NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectAfterFirstFrame:
    """Disconnect once one frame has been yielded, so the rest is DRAINED.

    The first poll returns False, which parks the consumer on an empty queue —
    that hands control to the pump, which enqueues the whole (await-free) stub
    stream in one go. The second poll then cancels the pump with the remaining
    events already queued, which is exactly the `_apply_event` drain path.
    """

    def __init__(self) -> None:
        self._polls = 0

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > 1


class _UnusedProvider:
    def stream(self, **_kwargs: object):  # type: ignore[no-untyped-def]
        raise AssertionError("the stubbed orchestrator replaces the provider")


async def _drive_stubbed_orchestrator(
    session_factory: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[ProviderEvent],
    *,
    request_stub: object,
    hold_open: bool = False,
    web_search: bool = False,
) -> list[dict[str, object]]:
    """Run one deep-research turn over `events`; return the persisted parts."""
    import asyncio as _asyncio
    from uuid import uuid4

    from sqlalchemy import select

    from app.db.models import Conversation, Message, User
    from app.providers.tiers import get_binding
    from app.streaming import handler as handler_mod

    def _fake_run_orchestrator(**_kwargs: object) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            for ev in events:
                yield ev
            if hold_open:
                # A drained turn must not end on its own: the disconnect, not
                # exhaustion, has to be what ends it.
                await _asyncio.sleep(30)

        return _gen()

    monkeypatch.setattr(handler_mod, "run_orchestrator", _fake_run_orchestrator)

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:  # type: ignore[operator]
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id, title="fl33a", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    async with session_factory() as session:  # type: ignore[operator]
        async for _ev in handler_mod.stream_and_persist(
            request=request_stub,  # type: ignore[arg-type]
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
            web_search=web_search,
            agentic_mode="deep_research",
        ):
            pass

    async with session_factory() as session:  # type: ignore[operator]
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        ).scalars().first()
    assert row is not None
    raw = row.parts if isinstance(row.parts, list) else []
    return [p for p in raw if isinstance(p, dict)]


_GATE_MATRIX = [
    # phase, partial, expected persisted outcome
    ("plan", True, "partial"),
    ("plan", False, "partial"),
    ("progress", True, "partial"),
    ("progress", False, "partial"),
    ("final", True, "partial"),
    ("final", False, "complete"),
]


@pytest.mark.parametrize(("phase", "partial", "expected_outcome"), _GATE_MATRIX)
@pytest.mark.parametrize("path", ["live", "drain"])
async def test_run_summary_persist_gate_matrix(
    handler_agentic_env: None,
    session_factory: object,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    partial: bool,
    expected_outcome: str,
    path: str,
) -> None:
    """FL-33-a (FE-3 / GAP-3): every receipt persists, with the emitted labels.

    The old gate (`phase == "final" or partial or budget_halted or
    failed_worker_count > 0`) dropped a plan pause's and a worker-HITL pause's
    receipt, so reload re-derived a meter that showed a different number AND
    claimed exact/final while the plan card above it still said "(estimate)".
    A non-final phase is never a finished run, so it persists as `partial`.

    The identical table runs through the live gate and the `_apply_event` drain
    twin, so the two can no longer drift (F2 DoD 6).
    """
    confidence = "exact" if phase == "final" else "estimate"
    events: list[ProviderEvent] = [
        SubagentStarted(subagent_id="worker-0", label="Alpha", role="worker"),
        AnswerDelta(text="alpha finding", subagent_id="worker-0"),
        UsageUpdate(input_tokens=6, output_tokens=3, subagent_id="worker-0"),
        RunCost(
            subtotal_usd=0.25,
            cap_usd=10.0,
            partial=partial,
            phase=phase,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
        ),
    ]
    request_stub: object
    if path == "live":
        events.append(Complete(usage=UsageUpdate(input_tokens=6, output_tokens=3)))
        request_stub = _NeverDisconnected()
    else:
        request_stub = _DisconnectAfterFirstFrame()

    parts = await _drive_stubbed_orchestrator(
        session_factory,
        monkeypatch,
        events,
        request_stub=request_stub,
        hold_open=path == "drain",
    )
    summaries = [p for p in parts if p.get("type") == "agentic_run_summary"]
    assert len(summaries) == 1, f"{path}/{phase}/{partial} persisted no receipt"
    summary = summaries[0]
    assert summary["outcome"] == expected_outcome
    assert summary["subtotalUsd"] == pytest.approx(0.25)
    # The honesty labels are the ones the backend emitted, never re-derived.
    assert summary["costConfidence"] == confidence
    assert summary["costPhase"] == phase

