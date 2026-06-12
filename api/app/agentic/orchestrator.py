"""Agentic orchestrator: drive a multi-agent turn as a single provider stream.

`run_orchestrator` is a drop-in replacement for the bare agent loop in the
streaming handler (`_build_provider_iter`'s third branch): it yields the same
`ProviderEvent` union the handler already consumes, so the handler's pump /
relay machinery is unchanged. Every content/usage event a subagent produces is
TAGGED with a `subagent_id` and bracketed by a `SubagentStarted` /
`SubagentDone` pair; a final untagged `Complete` carries the run's SUMMED usage
(so the handler's existing "last Complete wins" fold yields the correct turn
total) and a `RunCost` reports the running cost subtotal against the configured
cap.

Two modes:
- ``single`` (M1): one `run_agent_loop` wrapped as the ``primary`` subagent.
- ``deep_research`` (M2): plan → bounded parallel ``worker`` fan-out (under a
  semaphore) → ``aggregator`` synthesis from the workers' untrusted outputs.

M3 hooks (`_admit`, `_maybe_plan_approval`, `_maybe_verify`) are wired into the
control flow as no-ops so the budget/approval/verifier milestone can land
without re-threading the orchestrator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Literal

from app.agentic import aggregate, planner
from app.agentic.aggregate import WorkerOutput
from app.config import Settings
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    RunCost,
    Sources,
    StatusUpdate,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.tools.agent_loop import MakeStream, run_agent_loop

# Event types that carry an optional `subagent_id` and so can be stamped by
# `_tag`. `ReasoningDone` (no payload) and the orchestrator-only
# `SubagentStarted` / `SubagentDone` / `RunCost` are deliberately absent — the
# agent loop never emits the latter, and `ReasoningDone` relays unchanged.
_TAGGABLE = (
    ReasoningDelta,
    AnswerDelta,
    StatusUpdate,
    Sources,
    ToolCall,
    ToolResult,
    UsageUpdate,
    AwaitingApproval,
    Complete,
)

AgenticMode = Literal["single", "deep_research"]

# Given a per-subagent user prompt, build the `MakeStream` the agent loop drives
# for that subagent. The handler supplies this so the orchestrator stays
# provider-agnostic: it captures the active route/binding/history and only varies
# the user text per worker.
StreamFactory = Callable[[str], MakeStream]

# Computes the USD cost of an accumulated usage for the active binding. Supplied
# by the handler (which closes over the binding + image count) so the
# orchestrator never reaches into pricing.
CostForUsage = Callable[[UsageUpdate], float]

_PRIMARY_LABEL = "Agent"
_AGGREGATOR_ID = "aggregator"
_AGGREGATOR_LABEL = "Synthesis"


@dataclass(frozen=True)
class _WorkerSentinel:
    """Internal queue marker: a worker has put its last event and finished.

    NOT a `ProviderEvent` — it never escapes the orchestrator; it only lets the
    fan-out merge loop know when every worker has drained so it can stop reading
    the shared queue.
    """

    subagent_id: str


def _tag(event: ProviderEvent, subagent_id: str) -> ProviderEvent:
    """Stamp `subagent_id` onto a subagent's event (no-op for `ReasoningDone`).

    `ReasoningDone` carries no `subagent_id` field (it has no payload to
    attribute), so it relays unchanged; every other event the agent loop can emit
    has the optional field and is rewritten via `dataclasses.replace`.
    """
    if isinstance(event, _TAGGABLE):
        return replace(event, subagent_id=subagent_id)
    return event


def _sum_usages(usages: list[UsageUpdate]) -> UsageUpdate:
    """Field-wise sum of usages → the run total (untagged final `Complete`)."""
    return UsageUpdate(
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        reasoning_tokens=sum(u.reasoning_tokens for u in usages),
        cached_input_tokens=sum(u.cached_input_tokens for u in usages),
    )


def _fold_usage(event: ProviderEvent, current: UsageUpdate) -> UsageUpdate:
    """Track a subagent's latest usage as its stream advances."""
    if isinstance(event, Complete):
        return event.usage
    if isinstance(event, UsageUpdate):
        return event
    return current


# --- M3 scaffold hooks (no-ops for M1/M2) ------------------------------------


async def _admit(settings: Settings) -> None:
    """Budget admission control (M3). No-op scaffold for now."""
    return None


async def _maybe_plan_approval(settings: Settings, sub_questions: list[str]) -> None:
    """Plan-approval gate (M3). No-op scaffold for now."""
    return None


async def _maybe_verify(settings: Settings, answer: str) -> str:
    """Answer verifier (M3). No-op scaffold — returns the answer unchanged."""
    return answer


# --- single mode (M1) ---------------------------------------------------------


async def _run_single(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    cost_for_usage: CostForUsage,
) -> AsyncIterator[ProviderEvent]:
    """One agent loop wrapped as the `primary` subagent."""
    subagent_id = "primary"
    yield SubagentStarted(subagent_id=subagent_id, label=_PRIMARY_LABEL, role="primary")
    usage = UsageUpdate()
    async for event in run_agent_loop(
        make_stream=make_stream_for(user_text), settings=settings
    ):
        usage = _fold_usage(event, usage)
        yield _tag(event, subagent_id)
    cost = cost_for_usage(usage)
    yield SubagentDone(
        subagent_id=subagent_id,
        label=_PRIMARY_LABEL,
        role="primary",
        usage=usage,
        cost_usd=cost,
    )
    yield RunCost(subtotal_usd=cost, cap_usd=settings.agentic_run_budget_usd)


# --- deep_research mode (M2) --------------------------------------------------


async def _run_deep_research(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    cost_for_usage: CostForUsage,
) -> AsyncIterator[ProviderEvent]:
    """Plan → parallel worker fan-out → aggregator synthesis."""
    sub_questions = planner.decompose(user_text, max_workers=settings.agentic_max_workers)
    await _maybe_plan_approval(settings, sub_questions)

    semaphore = asyncio.Semaphore(max(1, settings.agentic_max_concurrency))
    queue: asyncio.Queue[ProviderEvent | _WorkerSentinel] = asyncio.Queue()
    # Worker bookkeeping, keyed by subagent_id and ordered by `worker_meta` so the
    # synthesis (and per-subagent totals) preserve sub-question order regardless
    # of the nondeterministic completion order of the parallel workers.
    worker_meta = [
        (index, f"worker-{index}", f"Worker {index + 1}", sub_question)
        for index, sub_question in enumerate(sub_questions)
    ]
    results: dict[str, WorkerOutput] = {}
    usages: dict[str, UsageUpdate] = {}
    costs: dict[str, float] = {}

    async def _run_worker(index: int, subagent_id: str, label: str, sub_question: str) -> None:
        answer_parts: list[str] = []
        usage = UsageUpdate()
        try:
            async with semaphore:
                await queue.put(
                    SubagentStarted(subagent_id=subagent_id, label=label, role="worker")
                )
                make_stream = make_stream_for(planner.worker_prompt(index, sub_question))
                async for event in run_agent_loop(make_stream=make_stream, settings=settings):
                    if isinstance(event, AnswerDelta):
                        answer_parts.append(event.text)
                    usage = _fold_usage(event, usage)
                    await queue.put(_tag(event, subagent_id))
                cost = cost_for_usage(usage)
                await queue.put(
                    SubagentDone(
                        subagent_id=subagent_id,
                        label=label,
                        role="worker",
                        usage=usage,
                        cost_usd=cost,
                    )
                )
                results[subagent_id] = WorkerOutput(
                    subagent_id=subagent_id,
                    sub_question=sub_question,
                    answer="".join(answer_parts),
                )
                usages[subagent_id] = usage
                costs[subagent_id] = cost
        finally:
            # Always signal completion so the merge loop can never deadlock on a
            # worker that errored before reaching its `SubagentDone`.
            await queue.put(_WorkerSentinel(subagent_id))

    tasks = [
        asyncio.create_task(_run_worker(index, subagent_id, label, sub_question))
        for index, subagent_id, label, sub_question in worker_meta
    ]
    try:
        remaining = len(tasks)
        while remaining > 0:
            item = await queue.get()
            if isinstance(item, _WorkerSentinel):
                remaining -= 1
                continue
            yield item
        # Surface any worker exception (the sentinel `finally` guarantees we got
        # here without deadlocking even if a worker raised).
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    ordered_outputs = [results[sid] for _, sid, _, _ in worker_meta if sid in results]
    synthesis = aggregate.synthesize(ordered_outputs)
    synthesis = await _maybe_verify(settings, synthesis)

    yield SubagentStarted(
        subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
    )
    yield AnswerDelta(text=synthesis, subagent_id=_AGGREGATOR_ID)
    aggregator_usage = UsageUpdate()
    aggregator_cost = cost_for_usage(aggregator_usage)
    yield Complete(usage=aggregator_usage, subagent_id=_AGGREGATOR_ID)
    yield SubagentDone(
        subagent_id=_AGGREGATOR_ID,
        label=_AGGREGATOR_LABEL,
        role="aggregator",
        usage=aggregator_usage,
        cost_usd=aggregator_cost,
    )

    total_usage = _sum_usages(
        [usages[sid] for _, sid, _, _ in worker_meta if sid in usages] + [aggregator_usage]
    )
    total_cost = sum(costs.get(sid, 0.0) for _, sid, _, _ in worker_meta) + aggregator_cost
    # Final untagged `Complete`: the handler's "last Complete wins" fold makes
    # this the turn's terminal usage, so the terminal attribution cost is the SUM
    # of every subagent's cost.
    yield Complete(usage=total_usage)
    yield RunCost(subtotal_usd=total_cost, cap_usd=settings.agentic_run_budget_usd)


# --- entry point --------------------------------------------------------------


async def run_orchestrator(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    mode: AgenticMode,
    user_text: str,
    cost_for_usage: CostForUsage,
) -> AsyncIterator[ProviderEvent]:
    """Drive an agentic turn, yielding the handler's `ProviderEvent` union.

    `make_stream_for(user_text)` builds the per-subagent provider stream the agent
    loop drives; `cost_for_usage` prices an accumulated usage for the active
    binding. The handler routes here ONLY when agentic mode is active, so the
    flag-off path never constructs this generator.
    """
    await _admit(settings)
    if mode == "deep_research":
        async for event in _run_deep_research(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
        ):
            yield event
    else:
        async for event in _run_single(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
        ):
            yield event
