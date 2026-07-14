"""Batch C unit tests: cost roll-up, cancel join, plan reuse, schema gate."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

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
    Complete,
    ProviderEvent,
    SubagentDone,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
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


@pytest.mark.asyncio
async def test_approve_reuses_approved_plan_without_replanning() -> None:
    """BE-039: resume with approved_plan must not re-decompose / re-plan."""
    seen_prompts: list[str] = []

    def _make_stream_for(prompt: str):
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
    """SAF-005 / BE-025: cancelled worker usage is joined and rolled into Complete."""
    started = asyncio.Event()

    async def _slow(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        yield UsageUpdate(input_tokens=100, output_tokens=0)
        started.set()
        await asyncio.sleep(60)
        yield AnswerDelta(text="late")
        yield Complete(usage=UsageUpdate(input_tokens=100, output_tokens=1))

    async def _fast(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        await started.wait()
        yield AnswerDelta(text="fast-ok")
        yield Complete(usage=UsageUpdate(input_tokens=3, output_tokens=1))

    def _make_stream_for(prompt: str):
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
        AGENTIC_RUN_BUDGET_USD=0.002,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_MAX_CONCURRENCY=2,
    )

    def _pricey(u: UsageUpdate) -> float:
        return float(u.input_tokens) * 0.001

    # Admit with a low estimate so mid-flight kill (not admission) fires.
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


@pytest.mark.asyncio
async def test_fallback_worker_priced_with_fallback_pricer() -> None:
    """BE-023 / SAF-006: fallback success uses fallback cost + route identity."""

    def _make_stream_for(prompt: str):
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

    def _fallback_make_stream_for(prompt: str):
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
async def test_execute_tool_rejects_schema_invalid_input() -> None:
    """BE-009: central JSON Schema gate before executor dispatch."""
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
