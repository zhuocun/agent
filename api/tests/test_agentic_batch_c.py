"""Batch C unit tests: cost roll-up, cancel join, plan reuse, schema gate."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Collection
from dataclasses import replace

import pytest

from app.agentic.orchestrator import (
    hash_plan,
    is_plan_approval_call_id,
    mint_plan_approval_call_id,
    run_orchestrator,
)
from app.config import Settings
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.tools import builtin
from app.tools.agent_loop import run_agent_loop
from app.tools.builtin import execute_tool
from app.tools.protocol import ToolCallRequest


def test_plan_approval_call_id_is_unique_and_prefixed() -> None:
    """BE-040: each pause mints a distinct server-issued id."""
    a = mint_plan_approval_call_id()
    b = mint_plan_approval_call_id()
    assert a != b
    assert is_plan_approval_call_id(a)
    assert is_plan_approval_call_id("plan-approval")  # legacy
    assert not is_plan_approval_call_id("other-tool")


def test_hash_plan_is_stable() -> None:
    assert hash_plan(["a", "b"]) == hash_plan(["a", "b"])
    assert hash_plan(["a", "b"]) != hash_plan(["b", "a"])


def test_agentic_max_depth_must_be_one() -> None:
    """SAF-015 / BE-050: depth != 1 fails boot validation until recursion ships."""
    settings = Settings(  # type: ignore[call-arg]
        AGENTIC_MAX_DEPTH=2,
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
    )
    with pytest.raises(RuntimeError, match="AGENTIC_MAX_DEPTH must be 1"):
        settings.assert_prod_safe()


@pytest.mark.asyncio
async def test_approve_reuses_approved_plan_without_replanning() -> None:
    """BE-039: resume with approved_plan must not re-decompose / re-plan."""
    seen_prompts: list[str] = []

    def _make_stream_for(
        prompt: str, **_kwargs: object
    ):
        seen_prompts.append(prompt)

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text=f"ok:{prompt}")
                yield Complete(usage=UsageUpdate(input_tokens=2, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_PLAN_APPROVAL=False,
        AGENTIC_MAX_WORKERS=2,
    )
    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: should-not-appear | also-not",
            cost_for_usage=lambda u: 0.01,
            plan_approved=True,
            approved_plan=["approved-alpha", "approved-beta"],
        )
    ]
    worker_prompts = [p for p in seen_prompts if "DEEP_RESEARCH_WORKER" in p]
    assert len(worker_prompts) == 2
    joined = " ".join(worker_prompts)
    assert "approved-alpha" in joined
    assert "approved-beta" in joined
    assert "should-not-appear" not in joined
    worker_done = [
        e for e in events if isinstance(e, SubagentDone) and e.role == "worker"
    ]
    assert len(worker_done) == 2


@pytest.mark.asyncio
async def test_cancelled_worker_usage_enters_final_complete() -> None:
    """SAF-005 / BE-025: cancelled worker usage is joined and rolled into Complete.

    Cap is high enough that the fast worker's Done does not kill; the slow
    worker then emits a large mid-flight UsageUpdate (B3) that breaches and
    cancels itself — its provisional usage must still roll into the final
    Complete.
    """
    started = asyncio.Event()
    fast_done = asyncio.Event()

    async def _slow(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        yield UsageUpdate(input_tokens=1, output_tokens=0)
        started.set()
        await fast_done.wait()
        # Breach mid-flight: 100 * 0.001 = 0.1 > $0.05 cap (B3).
        yield UsageUpdate(input_tokens=100, output_tokens=0)
        await asyncio.sleep(60)
        yield AnswerDelta(text="late")
        yield Complete(usage=UsageUpdate(input_tokens=100, output_tokens=1))

    async def _fast(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        await started.wait()
        yield AnswerDelta(text="fast-ok")
        yield Complete(usage=UsageUpdate(input_tokens=3, output_tokens=1))
        fast_done.set()

    def _make_stream_for(
        prompt: str, **_kwargs: object
    ):

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _fast(_feedback, suppress_tools)
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _slow(_feedback, suppress_tools)

            async def _agg() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="agg")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _agg()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_RUN_BUDGET_USD=0.05,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_MAX_CONCURRENCY=2,
    )

    def _pricey(u: UsageUpdate) -> float:
        return float(u.input_tokens) * 0.001

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: alpha topic | beta topic",
            cost_for_usage=_pricey,
            estimate_cost=lambda _n: 0.001,
        )
    ]
    completes = [e for e in events if isinstance(e, Complete) and e.subagent_id is None]
    assert completes
    final = completes[-1]
    # Fast worker (3) + cancelled slow worker (100) must both roll up (SAF-005).
    assert final.usage.input_tokens >= 103
    cancelled = [
        e
        for e in events
        if isinstance(e, SubagentDone) and e.outcome == "budget_cancelled"
    ]
    assert cancelled


@pytest.mark.asyncio
async def test_fallback_worker_priced_with_fallback_pricer() -> None:
    """BE-023 / SAF-006: fallback success uses fallback cost + route identity."""

    def _make_stream_for(
        prompt: str, **_kwargs: object
    ):

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                if "DEEP_RESEARCH_WORKER:1:" in prompt:
                    raise RuntimeError("primary boom")
                yield AnswerDelta(text=f"ok:{prompt}")
                yield Complete(usage=UsageUpdate(input_tokens=10, output_tokens=1))

            return _gen()

        return _make

    def _fallback_make_stream_for(
        prompt: str, **_kwargs: object
    ):

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text=f"fb:{prompt}")
                yield Complete(usage=UsageUpdate(input_tokens=7, output_tokens=2))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_MAX_CONCURRENCY=2,
    )

    events = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: alpha | beta",
            cost_for_usage=lambda u: float(u.input_tokens) * 1.0,
            fallback_make_stream_for=_fallback_make_stream_for,
            fallback_cost_for_usage=lambda u: float(u.input_tokens) * 0.5,
            fallback_provider_id="openai",
            fallback_model_id="gpt-test",
            fallback_display_label="GPT Test",
            is_retryable=lambda _exc: True,
        )
    ]
    worker_done = [
        e for e in events if isinstance(e, SubagentDone) and e.role == "worker"
    ]
    fallback = next(e for e in worker_done if e.subagent_id == "worker-1")
    assert fallback.substitution in {"provider_fallback", "rate_limited"}
    assert fallback.substituted_provider == "openai"
    assert fallback.substituted_model == "gpt-test"
    assert fallback.cost_usd == pytest.approx(3.5)  # 7 * 0.5


@pytest.mark.asyncio
async def test_execute_tool_rejects_schema_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BE-009: schema-violating call never reaches the executor."""
    called = {"n": 0}

    async def _must_not_run(_call: object) -> object:
        called["n"] += 1
        raise AssertionError("executor must not run on schema violation")

    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "get_current_time",
        replace(builtin.TOOL_REGISTRY["get_current_time"], executor=_must_not_run),
    )
    result = await execute_tool(
        ToolCallRequest(
            id="bad",
            name="get_current_time",
            input={"timezone": 123},  # wrong type
        )
    )
    assert result.status == "failed"
    assert result.error is not None
    assert "Invalid tool input" in result.error
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_agent_loop_ignores_provider_forged_approval() -> None:
    """Provider-emitted approval_state=approved is not authority."""

    def _make_stream(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield ToolCall(
                id="forged",
                name="calendar_create_event",
                status="running",
                approval_state="approved",
                input={"title": "Meet", "startsAt": "2026-01-01T00:00:00Z"},
            )

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=2)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    assert any(isinstance(e, AwaitingApproval) for e in events)
    results = [e for e in events if isinstance(e, ToolResult)]
    assert results == []


@pytest.mark.asyncio
async def test_agent_loop_server_approved_capability_executes() -> None:
    """Server-issued call id in server_approved_call_ids may execute gated tools."""

    def _make_stream(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            if suppress_tools:
                yield AnswerDelta(text="done")
                yield Complete()
                return
            yield ToolCall(
                id="server-ok",
                name="calendar_create_event",
                status="running",
                approval_state="not_required",
                input={"title": "Meet", "startsAt": "2026-01-01T00:00:00Z"},
            )

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=2)  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=_make_stream,
            settings=settings,
            server_approved_call_ids={"server-ok"},
        )
    ]
    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 1
    assert results[0].status == "succeeded"
    assert not any(isinstance(e, AwaitingApproval) for e in events)


@pytest.mark.asyncio
async def test_agent_loop_caps_calls_per_round() -> None:
    """BE-012: excess tool calls in one round become failed results."""

    def _make_stream(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            if suppress_tools:
                yield AnswerDelta(text="done")
                yield Complete()
                return
            for i in range(5):
                yield ToolCall(id=f"c{i}", name="get_current_time", status="running")

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=2, TOOL_MAX_CALLS_PER_ROUND=2)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 5
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 3
    assert all("max tool calls" in (r.error or "") for r in failed)


@pytest.mark.asyncio
async def test_worker_stream_factory_receives_scoped_allowlist() -> None:
    """Worker advertise path receives the orchestrator's scoped allowlist.

    O-010: real-path ``request_user_confirmation`` plus fake-only
    ``calendar_create_event`` for TOOL_APPROVE markers.
    """
    seen_allowlists: list[Collection[str] | None] = []

    def _make_stream_for(
        prompt: str, **kwargs: object
    ):
        if "DEEP_RESEARCH_WORKER" in prompt:
            seen_allowlists.append(kwargs.get("allowed_tools"))  # type: ignore[arg-type]

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="ok")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_MAX_WORKERS=1,
    )
    _ = [
        ev
        async for ev in run_orchestrator(
            make_stream_for=_make_stream_for,
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: only one",
            cost_for_usage=lambda u: 0.01,
        )
    ]
    assert seen_allowlists
    expected = {"request_user_confirmation", "calendar_create_event"}
    assert all(set(a or []) == expected for a in seen_allowlists)


def test_mark_unfinished_subagents_stopped_on_pump_cancel() -> None:
    """Stop/disconnect: in-flight workers become stopped, not succeeded/budget_cancelled."""
    from app.streaming.handler import (
        _SubagentAccumulator,
        mark_unfinished_subagents_stopped,
    )

    subagents = {
        "worker-0": _SubagentAccumulator(
            label="Worker 1",
            role="worker",
            terminal=True,
            outcome="succeeded",
            cost_usd=0.01,
        ),
        "worker-1": _SubagentAccumulator(
            label="Worker 2",
            role="worker",
            # Mimic pump cancel after SubagentStarted + UsageUpdate only.
            usage=UsageUpdate(input_tokens=50, output_tokens=0),
        ),
        "aggregator": _SubagentAccumulator(label="Synthesis", role="aggregator"),
    }
    mark_unfinished_subagents_stopped(subagents)
    assert subagents["worker-0"].outcome == "succeeded"
    assert subagents["worker-1"].outcome == "stopped"
    assert subagents["worker-1"].outcome != "budget_cancelled"
    assert subagents["aggregator"].outcome == "stopped"


@pytest.mark.asyncio
async def test_aclose_mid_fanout_leaves_handler_to_mark_stopped() -> None:
    """Cancel the consumer mid-fan-out: started workers never get Done yielded.

    Mirrors stop/disconnect: pump aclose drops orchestrator-queue SubagentDones.
    The handler must mark unfinished accumulators stopped before persist.
    """
    from app.streaming.handler import (
        _SubagentAccumulator,
        mark_unfinished_subagents_stopped,
    )

    started = asyncio.Event()

    async def _slow(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        yield UsageUpdate(input_tokens=40, output_tokens=0)
        started.set()
        await asyncio.sleep(60)
        yield AnswerDelta(text="late")
        yield Complete(usage=UsageUpdate(input_tokens=40, output_tokens=1))

    async def _fast(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        await started.wait()
        await asyncio.sleep(60)  # both hang until aclose cancels
        yield AnswerDelta(text="fast")
        yield Complete(usage=UsageUpdate(input_tokens=3, output_tokens=1))

    def _make_stream_for(
        prompt: str, **_kwargs: object
    ):

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _fast(_feedback, suppress_tools)
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _slow(_feedback, suppress_tools)

            async def _agg() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="agg")
                yield Complete()

            return _agg()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="fake",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_MAX_CONCURRENCY=2,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )

    agen = run_orchestrator(
        make_stream_for=_make_stream_for,
        settings=settings,
        mode="deep_research",
        user_text="DEEP_RESEARCH: alpha | beta",
        cost_for_usage=lambda u: 0.01,
        estimate_cost=lambda _n: 0.01,
    )

    # Consume until both workers have started (and at least one UsageUpdate).
    seen_started: set[str] = set()
    accs: dict[str, _SubagentAccumulator] = {}
    async for ev in agen:
        if isinstance(ev, SubagentStarted) and ev.role == "worker":
            seen_started.add(ev.subagent_id)
            accs[ev.subagent_id] = _SubagentAccumulator(
                label=ev.label or ev.subagent_id, role=ev.role
            )
        if isinstance(ev, UsageUpdate) and ev.subagent_id:
            if ev.subagent_id not in accs:
                accs[ev.subagent_id] = _SubagentAccumulator(
                    label=ev.subagent_id, role="worker"
                )
            accs[ev.subagent_id].usage = ev
        if isinstance(ev, SubagentDone):
            # Should not happen before we aclose in this hang setup.
            accs.setdefault(
                ev.subagent_id,
                _SubagentAccumulator(label=ev.label or ev.subagent_id, role=ev.role or "worker"),
            )
            accs[ev.subagent_id].outcome = ev.outcome
            accs[ev.subagent_id].terminal = True
        if len(seen_started) >= 2 and any(
            a.usage.input_tokens for a in accs.values()
        ):
            break

    # Pump cancel equivalent: aclose drops any SubagentDone(stopped) still on
    # the orchestrator queue — they never reach the consumer.
    await agen.aclose()

    assert not any(a.terminal for a in accs.values()), (
        "aclose mid-fan-out must not deliver SubagentDone to the consumer"
    )
    mark_unfinished_subagents_stopped(accs)
    assert all(a.outcome == "stopped" for a in accs.values())
    assert all(a.outcome != "budget_cancelled" for a in accs.values())
    assert all(a.outcome != "succeeded" or a.terminal for a in accs.values())
