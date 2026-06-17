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

M3 hooks (`_admit`, `_maybe_plan_approval`, `_maybe_verify`) are live control-flow
gates (admission / plan-approval pause / verifier), each gated by its setting.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Literal, cast

from app.agentic import aggregate, budget, planner, verifier
from app.agentic.aggregate import WorkerOutput
from app.agentic.retry import is_retryable_provider_error
from app.config import Settings
from app.errors import AppError
from app.schemas.common import SubstitutionReasonCode
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

_log = logging.getLogger(__name__)

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

# Computes the USD cost of an accumulated usage for the active binding.
CostForUsage = Callable[[UsageUpdate], float]

# Optional per-worker fallback stream factory and retry predicate (M4).
IsRetryable = Callable[[BaseException], bool]

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


async def _maybe_verify(settings: Settings, answer: str) -> str:
    """Answer verifier (M3): bounded N-pass self-consistency review.

    No-op (returns the answer unchanged) unless `AGENTIC_VERIFIER` is on; then it
    runs `AGENTIC_VERIFIER_N` passes and appends a content-free verification note
    (see `app/agentic/verifier.py`).
    """
    if not settings.agentic_verifier:
        return answer
    return verifier.verify(answer, n=settings.agentic_verifier_n)


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
    async for event in run_agent_loop(make_stream=make_stream_for(prompt), settings=settings):
        if isinstance(event, AnswerDelta):
            answer_parts.append(event.text)
        aggregator_usage = _fold_usage(event, aggregator_usage)
        yield _tag(event, _AGGREGATOR_ID)
    streamed = "".join(answer_parts)
    if not streamed.strip():
        # Model produced no usable synthesis — fall back to the deterministic
        # composition (already includes the budget/verifier notes) so the turn
        # never ends with an empty aggregator answer.
        fallback = aggregate.synthesize(
            outputs, planned=planned, budget_halted=budget_halted, failed=failed
        )
        fallback = await _maybe_verify(settings, fallback)
        yield AnswerDelta(text=fallback, subagent_id=_AGGREGATOR_ID)
    else:
        # Re-apply the labeled-partial (budget) note and the verifier note the
        # deterministic path appends, as trailing deltas over the streamed answer.
        suffix = ""
        if budget_halted:
            suffix += (
                "\n\n[Partial answer: stopped early to stay within the run budget; "
                f"answered {len(outputs)} of {planned} planned steps.]"
            )
        if failed > 0:
            suffix += (
                f"\n\n[{failed} sub-agent(s) failed and were omitted from this answer.]"
            )
        verified = await _maybe_verify(settings, streamed + suffix)
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
    total_usage = _sum_usages([*worker_usages, aggregator_usage])
    total_cost = worker_total_cost + aggregator_cost
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
    async for event in run_agent_loop(make_stream=make_stream_for(prompt), settings=settings):
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
    fallback_make_stream_for: StreamFactory | None = None,
    is_retryable: IsRetryable = is_retryable_provider_error,
) -> AsyncIterator[ProviderEvent]:
    """Plan → (approve) → admit → parallel fan-out → (verify) → synthesis.

    `plan_approved` carries the plan-approval HITL decision across the resume:
    None on a fresh run (pause if the flag is on), True/False on the resume
    (fan out / decline). `estimate_cost` + `budget_headroom_usd` drive the
    pre-spawn reservation and the mid-flight kill.
    """
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
    failed_workers = 0

    async def _run_worker(index: int, subagent_id: str, label: str, sub_question: str) -> None:
        nonlocal failed_workers
        answer_parts: list[str] = []
        usage = UsageUpdate()
        worker_failed = False
        sub_code: SubstitutionReasonCode | None = None
        sub_provider: str | None = None
        sub_model: str | None = None
        sub_label: str | None = None

        async def _consume(make_stream: MakeStream) -> None:
            nonlocal usage, sub_code, sub_provider, sub_model, sub_label
            async for event in run_agent_loop(make_stream=make_stream, settings=settings):
                if isinstance(event, AnswerDelta):
                    answer_parts.append(event.text)
                if isinstance(event, Complete) and event.substitution is not None:
                    sub_code = event.substitution
                    sub_provider = event.substituted_provider
                    sub_model = event.substituted_model
                    sub_label = event.substituted_display_label
                usage = _fold_usage(event, usage)
                await queue.put(_tag(event, subagent_id))

        try:
            async with semaphore:
                with invoke_agent_span(subagent_id=subagent_id, role="worker", label=label):
                    await queue.put(
                        SubagentStarted(subagent_id=subagent_id, label=label, role="worker")
                    )
                    prompt = planner.worker_prompt(index, sub_question, scaffolded=scaffolded)
                    try:
                        await _consume(make_stream_for(prompt))
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:
                        if (
                            fallback_make_stream_for is not None
                            and is_retryable(exc)
                        ):
                            if isinstance(exc, AppError) and exc.envelope.code == "RATE_LIMITED":
                                sub_code = "rate_limited"
                            else:
                                sub_code = "provider_fallback"
                            try:
                                await _consume(fallback_make_stream_for(prompt))
                            except asyncio.CancelledError:
                                raise
                            except BaseException as retry_exc:
                                _log.warning(
                                    "agentic.worker_fallback_failed",
                                    extra={
                                        "subagent_id": subagent_id,
                                        "error": str(retry_exc),
                                    },
                                )
                                worker_failed = True
                        else:
                            _log.warning(
                                "agentic.worker_failed",
                                extra={"subagent_id": subagent_id, "error": str(exc)},
                            )
                            worker_failed = True
                    if worker_failed:
                        failed_workers += 1
                        await queue.put(
                            SubagentDone(
                                subagent_id=subagent_id,
                                label=label,
                                role="worker",
                                usage=UsageUpdate(),
                                cost_usd=0.0,
                            )
                        )
                    else:
                        cost = cost_for_usage(usage)
                        await queue.put(
                            SubagentDone(
                                subagent_id=subagent_id,
                                label=label,
                                role="worker",
                                usage=usage,
                                cost_usd=cost,
                                substitution=cast(SubstitutionReasonCode | None, sub_code),
                                substituted_provider=sub_provider,
                                substituted_model=sub_model,
                                substituted_display_label=sub_label,
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
        # Tolerate task cancellations from the budget kill. Worker failures are
        # degraded inside `_run_worker` and must not fail the whole run.
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in gathered:
            if isinstance(outcome, BaseException) and not isinstance(
                outcome, asyncio.CancelledError
            ):
                _log.error(
                    "agentic.unexpected_worker_task_error",
                    exc_info=outcome,
                )
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
                failed=failed_workers,
            )
            synthesis = await _maybe_verify(settings, synthesis)
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
                failed=failed_workers,
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
    fallback_make_stream_for: StreamFactory | None = None,
    is_retryable: IsRetryable = is_retryable_provider_error,
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
    """
    if mode == "deep_research":
        async for event in _run_deep_research(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
            estimate_cost=estimate_cost,
            budget_headroom_usd=budget_headroom_usd,
            plan_approved=plan_approved,
            fallback_make_stream_for=fallback_make_stream_for,
            is_retryable=is_retryable,
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
