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
- ``deep_research``: plan → bounded parallel ``worker`` fan-out (under a
  semaphore) → ``aggregator`` synthesis from the workers' untrusted outputs.
  Provider-backend split: the FAKE provider uses the deterministic scaffolding
  (marker-based plan, ``DEEP_RESEARCH_WORKER:`` worker prompts, string-composed
  synthesis) so the test contract is stable; a REAL provider gets a model-driven
  plan (fan-out without the ``DEEP_RESEARCH:`` marker), clean marker-free worker
  prompts, and a streamed model-written synthesis — no scaffolding ever reaches
  the provider or the user-visible answer.

M3 hooks (`_admit`, `_maybe_plan_approval`, `_maybe_verify`) are wired into the
control flow as no-ops so the budget/approval/verifier milestone can land
without re-threading the orchestrator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Literal

from app.agentic import aggregate, budget, planner, verifier
from app.agentic.aggregate import WorkerOutput
from app.config import Settings
from app.errors import AppError
from app.observability.tracing import invoke_agent_span
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

# Provider error codes a worker may retry ONCE on a fallback route before
# degrading: a rate limit or a transient upstream failure. Mirrors the handler's
# `_RETRYABLE_CODES` (the typed `AppError`s the real provider adapters raise);
# duplicated here rather than imported to avoid a handler↔orchestrator import
# cycle.
_RETRYABLE_CODES = {"RATE_LIMITED", "PROVIDER_UPSTREAM"}


def _is_retryable(exc: BaseException) -> bool:
    """Whether a provider exception qualifies for a one-shot fallback retry."""
    return isinstance(exc, AppError) and exc.envelope.code in _RETRYABLE_CODES

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
_PLANNER_ID = "planner"
_PLANNER_LABEL = "Planner"

# Plan-approval HITL (M3). The plan pause reuses the shipped tool-approval
# terminal: the orchestrator emits a pseudo `tool_call` whose name is this
# sentinel (NOT a real registry tool) plus the standard `AwaitingApproval`
# pause. The resume route (`_prepare_resume_tool`) recognizes this name and
# short-circuits the registry/`needs_approval` checks, threading the decision
# back as `plan_approved` instead of executing a tool. `PLAN_APPROVAL_CALL_ID`
# is the stable id the resume `toolApproval.toolCallId` must match.
PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval"
PLAN_APPROVAL_CALL_ID = "plan-approval"


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


# --- cost estimation seam -----------------------------------------------------

# Given the planner's sub-question COUNT, estimate the run's worst-case USD
# cost. The handler supplies this (closing over the binding + image count) so
# the orchestrator never reaches into pricing/tiers directly. None disables the
# pre-spawn reservation (estimate treated as 0 ⇒ always admitted).
CostEstimator = Callable[[int], float]


# --- M3 hooks: budget admission, plan approval, verifier ----------------------


def _admit(
    *,
    estimate_usd: float,
    settings: Settings,
    budget_headroom_usd: float | None,
) -> budget.BudgetDecision:
    """Pre-spawn budget admission (M3).

    Reserves the worst-case `estimate_usd` against the per-run cap composed with
    the caller's remaining user/platform headroom. The orchestrator only fans
    out when the returned decision is `admitted`.
    """
    return budget.admit(
        estimated_usd=estimate_usd,
        cap_usd=settings.agentic_run_budget_usd,
        headroom_usd=budget_headroom_usd,
    )


async def _maybe_plan_approval(
    settings: Settings,
    sub_questions: list[str],
    *,
    estimate_usd: float,
    cap_usd: float,
) -> AsyncIterator[ProviderEvent]:
    """Plan-approval HITL gate (M3) — async generator of pause events.

    When `AGENTIC_PLAN_APPROVAL` is on, surfaces the plan decomposition + the
    estimated cost as a `planner` subagent and PAUSES the run with the shipped
    `awaiting_approval` terminal (a pseudo `tool_call` + `AwaitingApproval`)
    BEFORE any fan-out. A `toolApproval` resume carrying `PLAN_APPROVAL_CALL_ID`
    continues (approve) or declines (deny) the run. Yields nothing when the flag
    is off, so the caller falls straight through to admission + fan-out.
    """
    if not settings.agentic_plan_approval:
        return
    yield SubagentStarted(subagent_id=_PLANNER_ID, label=_PLANNER_LABEL, role="orchestrator")
    # Surface the estimate on the live cost meter so the FE can render it in the
    # pause card alongside the plan.
    yield RunCost(subtotal_usd=estimate_usd, cap_usd=cap_usd)
    yield ToolCall(
        id=PLAN_APPROVAL_CALL_ID,
        name=PLAN_APPROVAL_TOOL_NAME,
        label="Review research plan",
        status="awaiting_approval",
        approval_state="pending",
        input={
            "plan": list(sub_questions),
            "estimatedCostUsd": estimate_usd,
            "capUsd": cap_usd,
        },
        subagent_id=_PLANNER_ID,
    )
    yield AwaitingApproval(tool_call_id=PLAN_APPROVAL_CALL_ID, subagent_id=_PLANNER_ID)


async def _maybe_verify(
    settings: Settings,
    answer: str,
    *,
    make_stream_for: StreamFactory,
) -> tuple[str, UsageUpdate]:
    """Answer verifier (M3): bounded N-pass self-consistency review.

    No-op (returns the answer unchanged + zero usage) unless `AGENTIC_VERIFIER`
    is on; then it runs `AGENTIC_VERIFIER_N` passes and appends a content-free
    verification note (see `app/agentic/verifier.py`). On a REAL provider the
    review is a bounded `run_agent_loop` pass whose token usage is returned so
    the caller can fold the verifier's spend into the run totals; on the FAKE
    provider it stays the deterministic, zero-cost stub.
    """
    if not settings.agentic_verifier:
        return answer, UsageUpdate()
    return await verifier.verify_streamed(
        make_stream_for=make_stream_for,
        settings=settings,
        synthesis=answer,
        n=settings.agentic_verifier_n,
    )


# --- shared finalize ----------------------------------------------------------


async def _finalize_synthesis(
    *,
    synthesis: str,
    worker_usages: list[UsageUpdate],
    worker_total_cost: float,
    cost_for_usage: CostForUsage,
    cap_usd: float,
) -> AsyncIterator[ProviderEvent]:
    """Emit the `aggregator` subagent + the run's summed totals.

    Shared by the normal fan-out tail AND the early-exit paths (over-budget,
    plan-declined) so they all persist a clean `done` turn with the same shape:
    aggregator subagent → run-total `Complete` → `run_cost`.
    """
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
    total_usage = _sum_usages([*worker_usages, aggregator_usage])
    total_cost = worker_total_cost + aggregator_cost
    # Final untagged `Complete`: the handler's "last Complete wins" fold makes
    # this the turn's terminal usage, so the terminal attribution cost is the SUM
    # of every subagent's cost.
    yield Complete(usage=total_usage)
    yield RunCost(subtotal_usd=total_cost, cap_usd=cap_usd)


async def _finalize_synthesis_streamed(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    outputs: list[WorkerOutput],
    planned: int,
    worker_usages: list[UsageUpdate],
    worker_total_cost: float,
    cost_for_usage: CostForUsage,
    cap_usd: float,
    budget_halted: bool,
    failed: int = 0,
) -> AsyncIterator[ProviderEvent]:
    """Stream a MODEL-WRITTEN synthesis as the `aggregator` subagent (real providers).

    Drives a bounded `run_agent_loop` over the synthesis prompt built from the
    workers' (untrusted) findings and relays its content TAGGED to the aggregator,
    so the FE renders a streamed, model-authored answer instead of the
    deterministic string composition. Closes with the run's summed totals exactly
    like `_finalize_synthesis`. Falls back to the deterministic synthesis when the
    model streams nothing, so the turn never ends with an empty aggregator answer.
    The graceful-degrade (budget) + verifier notes the deterministic path appends
    are re-applied here as trailing deltas so behavior is consistent across paths.
    """
    yield SubagentStarted(
        subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
    )
    prompt = aggregate.build_synthesis_prompt(user_text, outputs)
    aggregator_usage = UsageUpdate()
    answer_parts: list[str] = []
    async for event in run_agent_loop(
        make_stream=make_stream_for(prompt), settings=settings, subagent_id=_AGGREGATOR_ID
    ):
        if isinstance(event, AnswerDelta):
            answer_parts.append(event.text)
        aggregator_usage = _fold_usage(event, aggregator_usage)
        yield _tag(event, _AGGREGATOR_ID)
    streamed = "".join(answer_parts)
    # The verifier's reviewer-pass usage (zero on the fake/off path); folded into
    # the run totals below so a provider-backed verifier's spend is billed.
    verifier_usage = UsageUpdate()
    if not streamed.strip():
        # Model produced no usable synthesis — fall back to the deterministic
        # composition (already includes the budget/verifier notes) so the turn
        # never ends with an empty aggregator answer.
        fallback = aggregate.synthesize(
            outputs, planned=planned, budget_halted=budget_halted, failed=failed
        )
        fallback, verifier_usage = await _maybe_verify(
            settings, fallback, make_stream_for=make_stream_for
        )
        yield AnswerDelta(text=fallback, subagent_id=_AGGREGATOR_ID)
    else:
        # Re-apply the labeled-partial (budget / failed-worker) notes and the
        # verifier note the deterministic path appends, as trailing deltas over
        # the streamed answer.
        suffix = ""
        if budget_halted:
            suffix += (
                "\n\n[Partial answer: stopped early to stay within the run budget; "
                f"answered {len(outputs)} of {planned} planned steps.]"
            )
        if failed:
            suffix += (
                f"\n\n[Partial answer: {failed} of {planned} sub-agents failed; "
                f"answered {len(outputs)} of {planned} planned steps.]"
            )
        verified, verifier_usage = await _maybe_verify(
            settings, streamed + suffix, make_stream_for=make_stream_for
        )
        extra = verified[len(streamed) :]
        if extra:
            yield AnswerDelta(text=extra, subagent_id=_AGGREGATOR_ID)
    aggregator_cost = cost_for_usage(aggregator_usage)
    yield Complete(usage=aggregator_usage, subagent_id=_AGGREGATOR_ID)
    yield SubagentDone(
        subagent_id=_AGGREGATOR_ID,
        label=_AGGREGATOR_LABEL,
        role="aggregator",
        usage=aggregator_usage,
        cost_usd=aggregator_cost,
    )
    total_usage = _sum_usages([*worker_usages, aggregator_usage, verifier_usage])
    total_cost = worker_total_cost + aggregator_cost + cost_for_usage(verifier_usage)
    yield Complete(usage=total_usage)
    yield RunCost(subtotal_usd=total_cost, cap_usd=cap_usd)


async def _collect_answer(
    make_stream_for: StreamFactory,
    settings: Settings,
    prompt: str,
) -> tuple[str, UsageUpdate]:
    """Run a bounded agent loop QUIETLY and return its (answer_text, usage).

    Used for the real-provider planner pass: the planner's reply is parsed into
    sub-questions, so its events are NOT surfaced as a subagent — only the answer
    text and accumulated usage matter. Tool output (if the planner calls a tool)
    stays untrusted DATA carried back through the loop's feedback channel.
    """
    answer_parts: list[str] = []
    usage = UsageUpdate()
    async for event in run_agent_loop(
        make_stream=make_stream_for(prompt), settings=settings, subagent_id=_PLANNER_ID
    ):
        if isinstance(event, AnswerDelta):
            answer_parts.append(event.text)
        usage = _fold_usage(event, usage)
    return "".join(answer_parts), usage


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
    with invoke_agent_span(subagent_id=subagent_id, role="primary", label=_PRIMARY_LABEL):
        async for event in run_agent_loop(
            make_stream=make_stream_for(user_text), settings=settings, subagent_id=subagent_id
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


# --- deep_research mode (M2 + M3 budget/approval/verify) ----------------------


async def _run_deep_research(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    cost_for_usage: CostForUsage,
    estimate_cost: CostEstimator | None = None,
    budget_headroom_usd: float | None = None,
    plan_approved: bool | None = None,
    make_worker_stream_for: StreamFactory | None = None,
    fallback_make_worker_stream_for: StreamFactory | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Plan → (approve) → admit → parallel fan-out → (verify) → synthesis.

    `plan_approved` carries the plan-approval HITL decision across the resume:
    None on a fresh run (pause if the flag is on), True/False on the resume
    (fan out / decline). `estimate_cost` + `budget_headroom_usd` drive the
    pre-spawn reservation and the mid-flight kill.

    `make_worker_stream_for` builds the per-WORKER stream (a least-privilege tool
    subset, SR-2); it defaults to `make_stream_for` (the full-tool factory the
    planner/aggregator use) when the handler doesn't scope worker tools.
    `fallback_make_worker_stream_for` builds the same worker stream over the
    ALTERNATE route; when set, a worker that hits a retryable provider error
    (429/5xx) BEFORE emitting any content retries once on the fallback route
    before degrading (PRD 08 graceful-degrade). None disables the retry.
    """
    worker_stream_for = make_worker_stream_for or make_stream_for
    # Provider-backend split: the FAKE provider keys on the deterministic
    # `DEEP_RESEARCH_WORKER:`/`DEEP_RESEARCH:` scaffolding (the test contract), so
    # it always uses the marker-based `decompose` + scaffolded worker prompts. A
    # REAL provider must never see scaffolding: it gets a model-driven plan (so a
    # plain prompt fans out WITHOUT the `DEEP_RESEARCH:` marker) and clean worker
    # prompts, then a streamed model-written synthesis.
    scaffolded = settings.provider_backend == "fake"
    planner_usage = UsageUpdate()
    if (
        scaffolded
        or user_text.startswith(planner.DEEP_RESEARCH_PREFIX)
        or plan_approved is False
    ):
        # Deterministic decomposition: the fake provider, an explicit
        # `DEEP_RESEARCH:` opt-in, or a decline (sub-questions go unused — no
        # fan-out — so skip the model planner call entirely).
        sub_questions = planner.decompose(user_text, max_workers=settings.agentic_max_workers)
    else:
        # Real-provider planner: a bounded model pass decomposes the prompt into
        # sub-questions so a plain request fans out without the user typing the
        # `DEEP_RESEARCH:` marker. Degrades to a single sub-question (the whole
        # request) when the planner yields nothing.
        plan_reply, planner_usage = await _collect_answer(
            make_stream_for,
            settings,
            planner.build_planner_prompt(user_text, max_workers=settings.agentic_max_workers),
        )
        sub_questions = planner.parse_plan(
            plan_reply, max_workers=settings.agentic_max_workers, fallback=user_text
        )
    cap = settings.agentic_run_budget_usd
    estimate = estimate_cost(len(sub_questions)) if estimate_cost is not None else 0.0

    # Plan-approval HITL gate (T6). On a fresh run with the flag on, pause for a
    # human decision BEFORE any fan-out. The resume re-enters here with
    # `plan_approved` set.
    if plan_approved is None:
        async for event in _maybe_plan_approval(
            settings, sub_questions, estimate_usd=estimate, cap_usd=cap
        ):
            yield event
        if settings.agentic_plan_approval:
            return
    elif plan_approved is False:
        # Declined on resume: no fan-out, a labeled (non-error) synthesis.
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the research plan was declined; no sub-agents were run."
            ),
            worker_usages=[],
            worker_total_cost=0.0,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
        ):
            yield event
        return

    # Pre-spawn admission (T5). If the worst-case estimate already exceeds the
    # effective cap (run cap composed with user/platform headroom), don't spawn —
    # degrade gracefully to a labeled, explained synthesis (never a silent
    # overrun, never an error).
    decision = _admit(
        estimate_usd=estimate, settings=settings, budget_headroom_usd=budget_headroom_usd
    )
    if not decision.admitted:
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the run was not started — estimated cost "
                f"${estimate:.4f} exceeds the ${decision.effective_cap_usd:.4f} run "
                "budget. No sub-agents were spawned."
            ),
            worker_usages=[],
            worker_total_cost=0.0,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
        ):
            yield event
        return

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
    # Workers that raised mid-stream (provider error / exhausted retries). They
    # are dropped from the synthesis and counted so the answer can be labeled a
    # partial — a worker failure degrades the run, never fails it (PRD 08).
    failed_workers: set[str] = set()

    async def _run_worker(index: int, subagent_id: str, label: str, sub_question: str) -> None:
        answer_parts: list[str] = []
        usage = UsageUpdate()
        try:
            async with semaphore:
                # One `invoke_agent` span per worker (no-op when OTel is off),
                # nested under the turn's request span.
                with invoke_agent_span(subagent_id=subagent_id, role="worker", label=label):
                    await queue.put(
                        SubagentStarted(subagent_id=subagent_id, label=label, role="worker")
                    )
                    prompt = planner.worker_prompt(index, sub_question, scaffolded=scaffolded)
                    # One-shot fallback: try the primary worker route, then (only
                    # if it errored retryably BEFORE emitting anything) the
                    # fallback route. `emitted` gates the retry so a mid-stream
                    # failure NEVER double-emits a worker's content — it degrades.
                    emitted = False
                    for attempt, factory in enumerate(
                        (worker_stream_for, fallback_make_worker_stream_for)
                    ):
                        if factory is None:
                            continue
                        try:
                            make_stream = factory(prompt)
                            async for event in run_agent_loop(
                                make_stream=make_stream,
                                settings=settings,
                                subagent_id=subagent_id,
                            ):
                                if isinstance(event, AnswerDelta):
                                    answer_parts.append(event.text)
                                usage = _fold_usage(event, usage)
                                await queue.put(_tag(event, subagent_id))
                                emitted = True
                            break
                        except Exception as exc:
                            # Retry on the fallback route only when the error is
                            # retryable, nothing was emitted yet, and a fallback
                            # factory remains; otherwise propagate to the degrade
                            # path below.
                            if (
                                _is_retryable(exc)
                                and not emitted
                                and attempt == 0
                                and fallback_make_worker_stream_for is not None
                            ):
                                answer_parts = []
                                usage = UsageUpdate()
                                continue
                            raise
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
        except asyncio.CancelledError:
            # Mid-flight budget kill cancels in-flight workers; propagate so the
            # `gather` below sees a CancelledError (tolerated) rather than a
            # degraded worker — a budget halt is labeled separately.
            raise
        except Exception:
            # Per-worker provider-failure degrade (M4 / PRD 08 / FR-26g): a single
            # worker's error must NOT fail the whole run. Mark it failed and emit a
            # zero-cost `SubagentDone` so its transcript section still closes; the
            # run aggregates the surviving workers and labels the answer partial.
            failed_workers.add(subagent_id)
            await queue.put(
                SubagentDone(
                    subagent_id=subagent_id,
                    label=label,
                    role="worker",
                    usage=UsageUpdate(),
                    cost_usd=0.0,
                )
            )
        finally:
            # Always signal completion so the merge loop can never deadlock on a
            # worker that errored OR was cancelled (mid-flight budget kill) before
            # reaching its `SubagentDone`.
            await queue.put(_WorkerSentinel(subagent_id))

    tasks = [
        asyncio.create_task(_run_worker(index, subagent_id, label, sub_question))
        for index, subagent_id, label, sub_question in worker_meta
    ]
    # Mid-flight kill (T5): accumulate ACTUAL per-worker cost as each
    # `SubagentDone` lands; on a cap breach, cancel the remaining (un-started AND
    # in-flight) workers and aggregate whatever completed — a labeled partial
    # synthesis rather than a silent overrun.
    actual_cost = 0.0
    budget_halted = False
    try:
        remaining = len(tasks)
        while remaining > 0:
            item = await queue.get()
            if isinstance(item, _WorkerSentinel):
                remaining -= 1
                continue
            yield item
            if isinstance(item, SubagentDone) and item.role == "worker":
                actual_cost += item.cost_usd or 0.0
                if not budget_halted and budget.exceeds_cap(
                    actual_usd=actual_cost, cap_usd=cap, headroom_usd=budget_headroom_usd
                ):
                    budget_halted = True
                    for task in tasks:
                        if not task.done():
                            task.cancel()
        # Tolerate the cancellations we issued for the budget kill; surface any
        # GENUINE worker exception (the sentinel `finally` guarantees we reached
        # here without deadlocking even if a worker raised).
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in gathered:
            if isinstance(outcome, BaseException) and not isinstance(
                outcome, asyncio.CancelledError
            ):
                raise outcome
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    ordered_outputs = [results[sid] for _, sid, _, _ in worker_meta if sid in results]
    # Fold the (real-provider) planner pass into the run totals so its tokens are
    # billed honestly. `planner_usage` is the zero default on the scaffolded /
    # explicit-marker path, so the fake-provider totals are unchanged.
    ordered_usages = [usages[sid] for _, sid, _, _ in worker_meta if sid in usages]
    ordered_usages.append(planner_usage)
    worker_total_cost = sum(
        costs.get(sid, 0.0) for _, sid, _, _ in worker_meta
    ) + cost_for_usage(planner_usage)
    with invoke_agent_span(
        subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
    ):
        if scaffolded or not ordered_outputs:
            # Deterministic synthesis: the fake-provider / test contract, and the
            # safety fallback when no worker produced output (a streamed synthesis
            # over zero findings would be meaningless).
            synthesis = aggregate.synthesize(
                ordered_outputs,
                planned=len(sub_questions),
                budget_halted=budget_halted,
                failed=len(failed_workers),
            )
            synthesis, verifier_usage = await _maybe_verify(
                settings, synthesis, make_stream_for=make_stream_for
            )
            # Fold the verifier's reviewer-pass spend (zero on the fake/off path)
            # into the run totals alongside the planner pass.
            ordered_usages.append(verifier_usage)
            worker_total_cost += cost_for_usage(verifier_usage)
            async for event in _finalize_synthesis(
                synthesis=synthesis,
                worker_usages=ordered_usages,
                worker_total_cost=worker_total_cost,
                cost_for_usage=cost_for_usage,
                cap_usd=cap,
            ):
                yield event
        else:
            # Real provider: stream a model-written synthesis from the workers'
            # (untrusted) findings.
            async for event in _finalize_synthesis_streamed(
                make_stream_for=make_stream_for,
                settings=settings,
                user_text=user_text,
                outputs=ordered_outputs,
                planned=len(sub_questions),
                worker_usages=ordered_usages,
                worker_total_cost=worker_total_cost,
                cost_for_usage=cost_for_usage,
                cap_usd=cap,
                budget_halted=budget_halted,
                failed=len(failed_workers),
            ):
                yield event


# --- entry point --------------------------------------------------------------


async def run_orchestrator(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    mode: AgenticMode,
    user_text: str,
    cost_for_usage: CostForUsage,
    estimate_cost: CostEstimator | None = None,
    budget_headroom_usd: float | None = None,
    plan_approved: bool | None = None,
    make_worker_stream_for: StreamFactory | None = None,
    fallback_make_worker_stream_for: StreamFactory | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Drive an agentic turn, yielding the handler's `ProviderEvent` union.

    `make_stream_for(user_text)` builds the per-subagent provider stream the agent
    loop drives; `cost_for_usage` prices an accumulated usage for the active
    binding. The handler routes here ONLY when agentic mode is active, so the
    flag-off path never constructs this generator.

    M3 params (all optional; inert for `single` mode):
    - `estimate_cost` — prices the worst-case run for pre-spawn admission.
    - `budget_headroom_usd` — the caller's remaining user/platform budget,
      composed with the per-run cap.
    - `plan_approved` — the plan-approval HITL decision carried across a resume
      (None = fresh run, True = approved, False = declined).
    - `make_worker_stream_for` — the least-privilege per-worker factory (worker
      tool subset, SR-2); defaults to `make_stream_for` when unset.
    - `fallback_make_worker_stream_for` — the worker factory over the alternate
      route, enabling a one-shot per-worker 429/5xx fallback before degrading.
    """
    # Runtime depth enforcement (T7). A single orchestrated turn is depth 1:
    # workers drive `run_agent_loop` directly and NEVER re-enter
    # `run_orchestrator`, so a `deep_research` fan-out can't recurse into another
    # fan-out. `agentic_max_depth` must be >= 1 for any orchestration to run;
    # `assert_prod_safe()` refuses < 1 at boot, and this is the matching runtime
    # guard (a non-stripped `if`, unlike `assert`) for a misconfigured runtime.
    if settings.agentic_max_depth < 1:
        raise ValueError(
            "agentic_max_depth must be >= 1 to run the orchestrator, got "
            f"{settings.agentic_max_depth}"
        )
    if mode == "deep_research":
        async for event in _run_deep_research(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
            estimate_cost=estimate_cost,
            budget_headroom_usd=budget_headroom_usd,
            plan_approved=plan_approved,
            make_worker_stream_for=make_worker_stream_for,
            fallback_make_worker_stream_for=fallback_make_worker_stream_for,
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
