"""Pinning tests for agentic architecture review fixes (B2-B16/B24)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.agentic.aggregate import WorkerOutput, remap_worker_source_ids
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
from app.config import Settings
from app.providers.protocol import (
    AnswerDelta,
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


def test_b12_remap_worker_source_ids_globally() -> None:
    """B12 offline helper: worker-local citation ordinals remapped in list order."""
    outputs = [
        WorkerOutput(
            subagent_id="worker-0",
            sub_question="a",
            answer="See [1] and [2].",
            source_ids=("1", "2"),
        ),
        WorkerOutput(
            subagent_id="worker-1",
            sub_question="b",
            answer="Also [1].",
            source_ids=("1",),
        ),
    ]
    remapped = remap_worker_source_ids(outputs)
    assert remapped[0].source_ids == ("1", "2")
    assert remapped[1].source_ids == ("3",)
    assert "[1]" in remapped[0].answer and "[2]" in remapped[0].answer
    assert "[3]" in remapped[1].answer
    assert "[1]" not in remapped[1].answer or remapped[1].answer.count("[1]") == 0


def test_b12_source_item_type_still_int() -> None:
    """SourceItem.id remains int — remapper must keep wire-compatible ints."""
    item = SourceItem(id=1, title="t", url="https://example.com")
    assert isinstance(item.id, int)


def test_b12_midstream_remapper_arrival_order_and_catalog() -> None:
    """B12: mid-stream remapper assigns globals in event order and builds catalog."""
    from app.agentic.orchestrator import _SourceIdRemapper

    remapper = _SourceIdRemapper()
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
    from app.agentic.orchestrator import _SourceIdRemapper

    remapper = _SourceIdRemapper()
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
    from app.agentic.orchestrator import _SourceIdRemapper

    prior = [
        SourceItem(id=1, title="old", url="https://old.example"),
        SourceItem(id=2, title="old2", url="https://old2.example"),
    ]
    remapper = _SourceIdRemapper()
    remapper.seed_catalog(prior)
    # Resume-session local id 1 must become global 3, not collide with 1.
    remapped = remapper.remap_sources(
        Sources(items=[SourceItem(id=1, title="new", url="https://new.example")]),
        "worker-0",
    )
    assert remapped.items[0].id == 3
    assert [i.id for i in remapper.merged_items()] == [1, 2, 3]


def test_b12_continuation_roundtrips_source_catalog() -> None:
    """B12: pause continuation persists the merged source catalog."""
    catalog = (
        SourceItem(id=1, title="one", url="https://one.example"),
        SourceItem(id=2, title="two", url="https://two.example"),
    )
    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="q",
        plan=("a", "b"),
        completed_workers=(),
        planner_usage=UsageUpdate(),
        planner_cost_usd=0.0,
        source_catalog=catalog,
    )
    blob = serialize_continuation(cont)
    assert "sourceCatalog" in blob
    assert len(blob["sourceCatalog"]) == 2
    parsed = parse_continuation(blob)
    assert parsed is not None
    assert len(parsed.source_catalog) == 2
    assert parsed.source_catalog[0].id == 1
    assert parsed.source_catalog[1].title == "two"


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

