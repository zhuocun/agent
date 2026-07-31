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

M3 hooks (`_admit`, `_maybe_plan_approval`, `verifier.run_if_enabled`) are live
control-flow gates (admission / plan-approval pause / verifier), each gated by
its setting.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog

from app.agentic import aggregate, budget, clarify, planner, verifier
from app.agentic.aggregate import WorkerOutput
from app.agentic.continuation import (
    AgenticContinuation,
    CompletedWorkerState,
    serialize_continuation,
    tool_results_from_transcript,
    usage_to_wire,
)
from app.agentic.retry import is_retryable_provider_error
from app.agentic.sources import SourceNamespace
from app.agentic.worker import (
    WORKER_ALLOWED_TOOLS,
    WORKER_FAKE_HITL_TOOLS,
    WORKER_PROD_HITL_TOOLS,
    CostForUsage,
    FreshWorkerSeed,
    IsRetryable,
    ResumedWorkerSeed,
    StreamFactory,
    WorkerPaused,
    WorkerResult,
    WorkerRoutes,
    WorkerRunner,
    fold_usage,
    has_nonzero_usage,
    sum_usages,
    tag_event,
    tool_transcript_part,
)
from app.config import Settings
from app.observability.tracing import invoke_agent_span
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    RunCost,
    Sources,
    StatusUpdate,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.runtime.answer_policy import EMPTY_REPLY_FALLBACK, main_answer_is_empty
from app.runtime.context import ServedRoute
from app.runtime.run_receipt import (
    CostLedger,
    ReceiptBoundary,
    RunReceipt,
    UsageTotals,
)
from app.search.protocol import SourceItem
from app.tools.agent_loop import run_agent_loop

_log = structlog.get_logger(__name__)

AgenticMode = Literal["single", "deep_research"]

_PRIMARY_LABEL = "Agent"
_AGGREGATOR_ID = "aggregator"
_AGGREGATOR_LABEL = "Synthesis"
_PLANNER_ID = "planner"
_PLANNER_LABEL = "Planner"
_VERIFIER_ID = verifier.VERIFIER_ID
_VERIFIER_LABEL = verifier.VERIFIER_LABEL

# Re-exports for importers that predate two moves out of this module: the worker
# HITL allowlist (O-010) went to `agentic.worker` with the lifecycle it scopes
# (AC-09), and the verifier's phase gates went to `agentic.verifier` (AC-10).
_WORKER_PROD_HITL_TOOLS = WORKER_PROD_HITL_TOOLS
_WORKER_FAKE_HITL_TOOLS = WORKER_FAKE_HITL_TOOLS
_WORKER_ALLOWED_TOOLS = WORKER_ALLOWED_TOOLS
_verifier_phase_estimate = verifier.phase_estimate_usd

# Aggregator: no registry tools and no provider-native web_search (O-006 / O-011 /
# H-011). Aggregator HITL continuation is not implemented — an empty allowlist
# makes gated pauses unreachable rather than advertising a dead resume path.
_AGGREGATOR_ALLOWED_TOOLS: frozenset[str] = frozenset()

# Quiet planner: judgment/decomposition only — empty registry allowlist so a
# planner ToolCall/HITL pause cannot be swallowed into an empty plan (O-009).
_PLANNER_ALLOWED_TOOLS: frozenset[str] = frozenset()

# --- degrade labels (orchestrator-local) --------------------------------------
#
# Each degrade path owns a DISTINCT label channel so the copy on the wire always
# agrees with the flag on the wire. `aggregate.synthesize` owns the budget-halt
# and failed-worker clauses; the three below are the ones it cannot express.

# FL-06: an aggregator crash is a synthesis failure, not a budget event. Folding
# it into `synthesize(budget_halted=...)` claimed a budget halt on a provider
# crash while `RunCost.budget_halted` stayed False.
_AGGREGATOR_FAILED_LABEL = (
    "\n\n[Partial answer: synthesis failed; composed from completed sub-agents.]"
)

# FL-13: single-mode budget halt. Additive with `EMPTY_REPLY_FALLBACK` so a halt
# before any prose is labeled a budget stop, not a blank turn.
_SINGLE_BUDGET_HALT_LABEL = (
    "\n\n[Partial answer: stopped early to stay within the run budget.]"
)

# FL-09: a sibling cancelled because another worker already holds the run's one
# HITL continuation. Neither `failed` nor a budget event.
_TRUNCATED_PARTIAL_SUFFIX = (
    " […partial: this sub-agent was cancelled before finishing.]"
)


def _superseded_label(count: int) -> str:
    """Suffix for workers cancelled as superseded (FL-09); empty when none."""
    if count <= 0:
        return ""
    return (
        f"\n\n[{count} sub-agent(s) were cancelled while another awaited "
        "approval; their partial findings are included.]"
    )


def _fold_completed_answer(state: CompletedWorkerState) -> str:
    """Restored sibling answer, marked truncated when it was cancelled (FL-09).

    Reads the `outcome` the pause turn persisted so a superseded worker's partial
    is never re-presented as a finished finding on the resume.
    """
    if state.outcome == "cancelled" and state.answer.strip():
        return state.answer + _TRUNCATED_PARTIAL_SUFFIX
    return state.answer


# Plan-approval HITL (M3). The plan pause reuses the shipped tool-approval
# terminal: the orchestrator emits a pseudo `tool_call` whose name is this
# sentinel (NOT a real registry tool) plus the standard `AwaitingApproval`
# pause. The resume route (`_prepare_resume_tool`) recognizes this name and
# short-circuits the registry/`needs_approval` checks, threading the decision
# back as `plan_approved` + the immutable approved plan instead of executing a
# tool. Each pause mints a unique call id under ``PLAN_APPROVAL_CALL_ID_PREFIX``
# so a stale approve cannot authorize a later plan (BE-040 / SAF-010).
PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval"
PLAN_APPROVAL_CALL_ID_PREFIX = "plan-approval-"
# Legacy constant kept for importers; new pauses never reuse this exact id.
PLAN_APPROVAL_CALL_ID = "plan-approval"

# Clarify-before-plan HITL (plan 02). Same awaiting_approval / toolApproval
# surface as plan approval; pseudo-tool carries 1-3 questions. Resume approve
# may include ``edited_input.answers``; then the orchestrator proceeds to
# plan → (plan approval) → admit → fan-out.
PLAN_CLARIFY_TOOL_NAME = "agentic_plan_clarify"
PLAN_CLARIFY_CALL_ID_PREFIX = "plan-clarify-"
PLAN_CLARIFY_CALL_ID = "plan-clarify"


def mint_plan_approval_call_id() -> str:
    """Opaque per-pause plan-approval tool-call id (server-issued)."""
    return f"{PLAN_APPROVAL_CALL_ID_PREFIX}{secrets.token_urlsafe(12)}"


def is_plan_approval_call_id(tool_call_id: str) -> bool:
    """True when ``tool_call_id`` is a (legacy or minted) plan-approval id."""
    return (
        tool_call_id == PLAN_APPROVAL_CALL_ID
        or tool_call_id.startswith(PLAN_APPROVAL_CALL_ID_PREFIX)
    )


def mint_plan_clarify_call_id() -> str:
    """Opaque per-pause clarify tool-call id (server-issued)."""
    return f"{PLAN_CLARIFY_CALL_ID_PREFIX}{secrets.token_urlsafe(12)}"


def is_plan_clarify_call_id(tool_call_id: str) -> bool:
    """True when ``tool_call_id`` is a (legacy or minted) clarify id."""
    return (
        tool_call_id == PLAN_CLARIFY_CALL_ID
        or tool_call_id.startswith(PLAN_CLARIFY_CALL_ID_PREFIX)
    )


def hash_plan(sub_questions: list[str]) -> str:
    """Stable SHA-256 of the normalized plan list (BE-040 identity bind)."""
    canonical = json.dumps(list(sub_questions), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _WorkerSentinel:
    """Internal queue marker: a worker has put its last event and finished.

    NOT a `ProviderEvent` — it never escapes the orchestrator; it only lets the
    fan-out merge loop know when every worker has drained so it can stop reading
    the shared queue.
    """

    subagent_id: str


AggregatorOutcome = Literal["succeeded", "failed", "budget_cancelled"]


def _aggregator_outcome(*, failed: bool, budget_halted: bool) -> AggregatorOutcome:
    """One label for the aggregator phase, read by its span and its terminal."""
    if failed:
        return "failed"
    return "budget_cancelled" if budget_halted else "succeeded"


def _substituted_route(
    primary: ServedRoute | None,
    *,
    provider_id: str | None,
    model_id: str | None,
    reason: str = "provider_fallback",
) -> ServedRoute | None:
    """The fallback route as ONE derived route carrying its reason (AC-10).

    A fallback is never a second set of span attributes: it overrides the served
    triple on the same phase span, keeping the bound tier. `None` in, `None` out,
    so a caller with no primary route (direct unit calls) settles no route.
    """
    if primary is None:
        return None
    return primary.substituted(
        provider_id=provider_id or "", model_id=model_id or "", reason=reason
    )


def _worker_output(result: WorkerResult) -> WorkerOutput:
    """The synthesis view of one worker's finding."""
    return WorkerOutput(
        subagent_id=result.subagent_id,
        sub_question=result.sub_question,
        answer=result.answer,
        source_ids=result.source_ids,
    )


def _abandoned_pause_done(
    pause: WorkerPaused, outcome: Literal["cancelled", "budget_cancelled"]
) -> SubagentDone:
    """Terminal for a pause this run will never resume (FL-09 / FL-10).

    Without a terminal the FE row spins forever and the handler defaults the
    outcome to `succeeded`; without the served-route fields it also prices and
    attributes a fallback-served loser on the PRIMARY binding (invariant 13).
    """
    result = pause.result
    return SubagentDone(
        subagent_id=result.subagent_id,
        label=result.label,
        role="worker",
        usage=result.usage,
        cost_usd=result.cost_usd,
        outcome=outcome,
        substitution=result.substitution,
        substituted_provider=result.substituted_provider,
        substituted_model=result.substituted_model,
        substituted_display_label=result.substituted_display_label,
    )


# Bound the worker fan-out → consumer queue so a slow drain cannot buffer an
# unbounded number of worker events in process memory (B23). ``await put``
# applies backpressure; teardown uses non-blocking put with drop-oldest.
_FANOUT_QUEUE_MAXSIZE = 256


def _queue_item_is_protected(item: object) -> bool:
    """Teardown must not drop completion control messages (B23)."""
    return isinstance(item, (_WorkerSentinel, SubagentDone, WorkerPaused))


def _queue_put_nowait_drop_oldest(
    queue: asyncio.Queue[Any], item: object
) -> None:
    """Enqueue ``item`` without awaiting; drop oldest *unprotected* if full (B23).

    Used on cancellation / sentinel paths so teardown cannot block forever on a
    full fan-out queue when the consumer has already stopped draining.

    Never drops ``_WorkerSentinel`` / ``SubagentDone`` / ``WorkerPaused`` already
    queued — losing a sentinel can hang the fan-out consumer forever.
    """
    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            held_protected: list[object] = []
            dropped = False
            while True:
                try:
                    old = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not dropped and not _queue_item_is_protected(old):
                    dropped = True
                    continue
                held_protected.append(old)
            for old in held_protected:
                try:
                    queue.put_nowait(old)
                except asyncio.QueueFull:
                    # Only protected items remain and the queue is saturated.
                    # maxsize (>=256) exceeds max workers, so this is unreachable
                    # in production; keep protected items and retry put.
                    break
            if not dropped:
                # Queue holds only protected control messages. If we are
                # inserting another sentinel that is already present, skip;
                # otherwise force one unprotected-style slot by refusing to
                # discard sentinels and relying on maxsize >> worker count.
                if isinstance(item, _WorkerSentinel):
                    # Deduplicate: if an identical sentinel is already queued, done.
                    # (We cannot peek easily after re-queue; treat as success if
                    # put still fails after a no-drop cycle — consumer will drain.)
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(item)
                    return
                # Non-sentinel teardown item with a protected-only full queue:
                # drop nothing further; best-effort put and return.
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(item)
                return


# --- run-accounting adapters (AC-02) ------------------------------------------
#
# `runtime.run_receipt` is provider-independent by construction (the carrier lives
# on `RunCost`), so the token counts are copied across the seam here rather than
# by importing either module into the other.


def _restored_usage(totals: UsageTotals) -> UsageUpdate:
    """Neutral run-accounting totals -> a provider usage event."""
    return UsageUpdate(
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        reasoning_tokens=totals.reasoning_tokens,
        cached_input_tokens=totals.cached_input_tokens,
    )


def _boundary_run_cost(
    ledger: CostLedger,
    *,
    cap_usd: float,
    phase: Literal["plan", "progress", "final"] = "final",
    boundary: ReceiptBoundary = "final",
    partial: bool = False,
    budget_halted: bool = False,
    failed_worker_count: int = 0,
) -> RunCost:
    """The ONE receipt-bearing `RunCost` for a persistable boundary (AC-02).

    `subtotal_usd` is read off the same receipt the handler bills from, so the
    live meter and the persisted total cannot disagree. `phase` / `confidence`
    stay wire UI state; the typed payload is the accounting truth.
    """
    receipt = ledger.receipt(cap_usd=cap_usd, boundary=boundary)
    return RunCost(
        subtotal_usd=receipt.cumulative_cost_usd,
        cap_usd=cap_usd,
        confidence="exact",
        phase=phase,
        partial=partial,
        budget_halted=budget_halted,
        failed_worker_count=failed_worker_count,
        receipt=receipt,
    )


# --- cost estimation seam -----------------------------------------------------

# Given the planner's sub-question COUNT, estimate the run's worst-case USD
# cost. The handler supplies this (closing over the binding + image count) so
# the orchestrator never reaches into pricing/tiers directly. None disables the
# pre-spawn reservation (estimate treated as 0 ⇒ always admitted).
CostEstimator = Callable[[int], float]


async def _emit_planner_receipt(
    *,
    planner_usage: UsageUpdate,
    cost_for_usage: CostForUsage,
    cap_usd: float,
    ledger_usd: float,
    open_bracket: bool = False,
    used_fallback: bool = False,
    fallback_cost_for_usage: CostForUsage | None = None,
    fallback_provider_id: str | None = None,
    fallback_model_id: str | None = None,
    fallback_display_label: str | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Surface planner spend as a planner SubagentDone + mid-run RunCost tick.

    Used on pause / decline / admit-reject / post-plan so planner tokens are
    never discarded from the run ledger (BE-015 / BE-014). ``ledger_usd`` is the
    run subtotal *including* ``planner_usage``.

    ``open_bracket`` forces a ``SubagentStarted`` even when usage is empty (plan-
    approval pause needs the planner section for the HITL tool). Otherwise the
    bracket opens only when there is real planner usage (fake/scaffolded path
    stays quiet).

    ``used_fallback`` (FL-11): the planner's A-5 retry was served on the fallback
    route, so it must be priced AND attributed on that binding — a primary price
    permanently under-bills and reports a model the run never used (invariant 13).
    """
    pricer = (
        fallback_cost_for_usage
        if used_fallback and fallback_cost_for_usage is not None
        else cost_for_usage
    )
    planner_cost = pricer(planner_usage)
    has_usage = bool(
        planner_usage.input_tokens
        or planner_usage.output_tokens
        or planner_usage.reasoning_tokens
        or planner_usage.cached_input_tokens
    )
    if open_bracket or has_usage:
        yield SubagentStarted(
            subagent_id=_PLANNER_ID, label=_PLANNER_LABEL, role="orchestrator"
        )
    if has_usage:
        yield Complete(usage=planner_usage, subagent_id=_PLANNER_ID)
        yield SubagentDone(
            subagent_id=_PLANNER_ID,
            label=_PLANNER_LABEL,
            role="orchestrator",
            usage=planner_usage,
            cost_usd=planner_cost,
            outcome="succeeded",
            substitution="provider_fallback" if used_fallback else None,
            substituted_provider=fallback_provider_id if used_fallback else None,
            substituted_model=fallback_model_id if used_fallback else None,
            substituted_display_label=(
                fallback_display_label if used_fallback else None
            ),
        )
    # Skip a zero progress tick so plan-approval's estimate RunCost remains the
    # first meter event the FE/tests see on a scaffolded pause.
    if has_usage or ledger_usd > 0:
        yield RunCost(
            subtotal_usd=ledger_usd,
            cap_usd=cap_usd,
            confidence="exact",
            phase="progress",
        )


# --- M3 hooks: plan approval, verifier ----------------------------------------


async def _maybe_clarify_before_plan(
    settings: Settings,
    *,
    user_text: str,
    scaffolded: bool,
    call_id: str | None = None,
    ledger: CostLedger | None = None,
    cap_usd: float = 0.0,
) -> AsyncIterator[ProviderEvent]:
    """Clarify-before-plan HITL gate — async generator of pause events.

    When `AGENTIC_CLARIFY_BEFORE_PLAN` is on and the ambiguity / marker check
    fires, surfaces 1-3 clarifying questions on a planner pseudo-tool and
    PAUSES with `awaiting_approval` BEFORE planning / admission / fan-out.
    Yields nothing when the flag is off or clarify is not needed.

    A clarify pause is a persistable boundary, so it carries the run's receipt
    (AC-02) even though it precedes every priced phase: without one, reload
    re-derived the paused row's meter from nothing.
    """
    if not settings.agentic_clarify_before_plan:
        return
    if not clarify.needs_clarify(user_text=user_text, scaffolded=scaffolded):
        return
    questions = clarify.build_clarify_questions(
        user_text=user_text, scaffolded=scaffolded
    )
    if not questions:
        return
    yield SubagentStarted(
        subagent_id=_PLANNER_ID, label=_PLANNER_LABEL, role="orchestrator"
    )
    if ledger is not None:
        yield _boundary_run_cost(
            ledger, cap_usd=cap_usd, phase="plan", boundary="pause", partial=True
        )
    clarify_call_id = call_id or mint_plan_clarify_call_id()
    yield ToolCall(
        id=clarify_call_id,
        name=PLAN_CLARIFY_TOOL_NAME,
        label="Clarify before research",
        status="awaiting_approval",
        approval_state="pending",
        input={"questions": list(questions)},
        subagent_id=_PLANNER_ID,
    )
    yield AwaitingApproval(tool_call_id=clarify_call_id, subagent_id=_PLANNER_ID)


async def _maybe_plan_approval(
    settings: Settings,
    sub_questions: list[str],
    *,
    estimate_usd: float,
    cap_usd: float,
    skip_started: bool = False,
    call_id: str | None = None,
    clarifications: list[str] | list[clarify.ClarificationRecord] | None = None,
    planner_cost_usd: float = 0.0,
    planner_usage: UsageUpdate | None = None,
    ledger: CostLedger | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Plan-approval HITL gate (M3) — async generator of pause events.

    When `AGENTIC_PLAN_APPROVAL` is on, surfaces the plan decomposition + the
    estimated cost as a `planner` subagent and PAUSES the run with the shipped
    `awaiting_approval` terminal (a pseudo `tool_call` + `AwaitingApproval`)
    BEFORE any fan-out. A `toolApproval` resume matching the minted call id
    continues (approve) or declines (deny) the run. Yields nothing when the flag
    is off, so the caller falls straight through to admission + fan-out.

    ``skip_started`` is True when the caller already opened the planner bracket
    (e.g. after emitting a planner usage receipt) so we do not double-start.
    ``clarifications`` (optional) are prior clarify-before-plan answers persisted
    on the pause tool input so a later plan-approval resume can re-attach them.

    ``planner_cost_usd`` / ``planner_usage`` (B4) are server-only fields stamped
    onto the pause tool input (stripped by ``RESERVED_CONTROL_KEYS``) so a
    plan-approved resume can seed the run-cap ledger without re-billing.

    ``ledger`` (AC-02) makes this pause's `RunCost` the boundary receipt carrier.
    The wire fields keep describing UI state — the plan card shows the run's
    ESTIMATE, labelled `estimate`/`plan` — while the typed payload carries the
    exact planner spend the pause row must persist and bill.
    """
    if not settings.agentic_plan_approval:
        return
    if not skip_started:
        yield SubagentStarted(
            subagent_id=_PLANNER_ID, label=_PLANNER_LABEL, role="orchestrator"
        )
    # Surface the estimate on the live cost meter so the FE can render it in the
    # pause card alongside the plan.
    yield RunCost(
        subtotal_usd=estimate_usd,
        cap_usd=cap_usd,
        confidence="estimate",
        phase="plan",
        receipt=(
            None
            if ledger is None
            else ledger.receipt(cap_usd=cap_usd, boundary="pause")
        ),
    )
    plan_call_id = call_id or mint_plan_approval_call_id()
    plan_list = list(sub_questions)
    plan_input: dict[str, object] = {
        "plan": plan_list,
        "planHash": hash_plan(plan_list),
        "estimatedCostUsd": estimate_usd,
        "capUsd": cap_usd,
    }
    # B4: persist actual planner spend for resume ledger seeding (H-012 stripped).
    if planner_cost_usd > 0.0 or (
        planner_usage is not None and has_nonzero_usage(planner_usage)
    ):
        plan_input["plannerCostUsd"] = planner_cost_usd
        if planner_usage is not None:
            plan_input["plannerUsage"] = usage_to_wire(planner_usage)
    if clarifications:
        if isinstance(clarifications[0], clarify.ClarificationRecord):
            cleaned_records = [
                r for r in clarifications if isinstance(r, clarify.ClarificationRecord)
            ]
        else:
            cleaned_records = clarify.records_from_questions_and_answers(
                [],
                [a for a in clarifications if isinstance(a, str)],
            )
        if any(r.answer.strip() for r in cleaned_records):
            plan_input["clarifications"] = clarify.serialize_clarification_records(
                cleaned_records
            )
    yield ToolCall(
        id=plan_call_id,
        name=PLAN_APPROVAL_TOOL_NAME,
        label="Review research plan",
        status="awaiting_approval",
        approval_state="pending",
        input=plan_input,
        subagent_id=_PLANNER_ID,
    )
    yield AwaitingApproval(tool_call_id=plan_call_id, subagent_id=_PLANNER_ID)


# --- shared finalize ----------------------------------------------------------


async def _finalize_synthesis(
    *,
    synthesis: str,
    worker_usages: list[UsageUpdate],
    worker_total_cost: float,
    cost_for_usage: CostForUsage,
    cap_usd: float,
    budget_halted: bool = False,
    failed_worker_count: int = 0,
    superseded_worker_count: int = 0,
    planned_workers: int = 0,
    completed_workers: int = 0,
    verifier_result: verifier.VerifyResult | None = None,
    verifier_outcome: Literal["succeeded", "failed"] = "succeeded",
    emit_verifier_bracket: bool = False,
    merged_sources: Sequence[SourceItem] | None = None,
    ledger: CostLedger | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Emit the `aggregator` subagent + optional verifier receipt + run totals.

    Shared by the normal fan-out tail AND the early-exit paths (over-budget,
    plan-declined) so they all persist a clean `done` turn with the same shape:
    aggregator subagent → (verifier) → run-total `Complete` → `run_cost`.

    When ``merged_sources`` is provided, emit a single aggregator-tagged
    ``Sources`` event before the synthesis answer so main-answer ``[n]``
    citations resolve against the global catalog (B12).

    ``superseded_worker_count`` (FL-09) labels siblings cancelled to keep one HITL
    continuation; `aggregate.synthesize` cannot express that clause, so it is
    appended here and raises `partial`.

    ``ledger`` (AC-02) is the run's accounting owner: the aggregator and verifier
    phases settle into it and the terminal `RunCost` carries its receipt. Without
    one (direct unit calls) the terminal keeps the scalar-only shape.
    """
    yield SubagentStarted(
        subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
    )
    if merged_sources:
        yield Sources(items=list(merged_sources), subagent_id=_AGGREGATOR_ID)
    yield AnswerDelta(
        text=synthesis + _superseded_label(superseded_worker_count),
        subagent_id=_AGGREGATOR_ID,
    )
    aggregator_usage = UsageUpdate()
    aggregator_cost = cost_for_usage(aggregator_usage)
    yield Complete(usage=aggregator_usage, subagent_id=_AGGREGATOR_ID)
    yield SubagentDone(
        subagent_id=_AGGREGATOR_ID,
        label=_AGGREGATOR_LABEL,
        role="aggregator",
        usage=aggregator_usage,
        cost_usd=aggregator_cost,
        outcome="succeeded",
    )
    verifier_cost = 0.0
    v_usage = UsageUpdate()
    verifier_budget_halted = False
    if emit_verifier_bracket:
        async for event in verifier.receipt_events(
            result=verifier_result,
            cost_for_usage=cost_for_usage,
            ledger_usd=worker_total_cost + aggregator_cost,
            cap_usd=cap_usd,
            outcome=verifier_outcome,
        ):
            yield event
    # Fold billable verifier usage whether the bracket was emitted here or
    # earlier (lifecycle-aware Started→await→Done before the aggregator
    # answer — V-009).
    if verifier_result is not None:
        v_usage = verifier_result.usage
        verifier_cost = verifier.result_cost_usd(verifier_result, cost_for_usage)
        verifier_budget_halted = verifier_result.budget_halted
    total_usage = sum_usages([*worker_usages, aggregator_usage, v_usage])
    if ledger is not None:
        ledger.settle(
            _AGGREGATOR_ID,
            role="aggregator",
            usage=aggregator_usage,
            cost_usd=aggregator_cost,
        )
        if verifier_result is not None or verifier_outcome == "failed":
            ledger.settle(
                _VERIFIER_ID,
                role="verifier",
                usage=v_usage,
                cost_usd=verifier_cost,
                outcome=verifier_outcome,
            )
    # Final untagged `Complete`: the handler's "last Complete wins" fold makes
    # this the turn's terminal usage, so the terminal attribution cost is the SUM
    # of every subagent's cost.
    yield Complete(usage=total_usage)
    effective_budget_halted = budget_halted or verifier_budget_halted
    partial = (
        effective_budget_halted
        or failed_worker_count > 0
        # FL-09 / FL-08: a cancelled sibling or a degraded verification is a
        # partial answer even when no worker failed and no cap was hit.
        or superseded_worker_count > 0
        or verifier.verification_degraded(verifier_result, verifier_outcome)
    )
    if ledger is not None:
        yield _boundary_run_cost(
            ledger,
            cap_usd=cap_usd,
            partial=partial,
            budget_halted=effective_budget_halted,
            failed_worker_count=failed_worker_count,
        )
    else:
        # No ledger: re-derive the total from the scalars (direct unit calls only).
        yield RunCost(
            subtotal_usd=worker_total_cost + aggregator_cost + verifier_cost,
            cap_usd=cap_usd,
            confidence="exact",
            phase="final",
            partial=partial,
            budget_halted=effective_budget_halted,
            failed_worker_count=failed_worker_count,
        )
    # planned/completed are unused on the wire today but kept in the signature
    # so call sites can pass them for future persistence without another signature
    # churn; reference to keep linters quiet.
    _ = (planned_workers, completed_workers)


async def _finalize_synthesis_streamed(
    *,
    make_stream_for: StreamFactory,
    verifier_make_stream_for: StreamFactory | None = None,
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
    superseded: int = 0,
    budget_headroom_usd: float | None = None,
    scaffolded: bool = False,
    artifacts: list[aggregate.WorkerArtifact] | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
    clarifications: list[dict[str, str]] | None = None,
    merged_sources: Sequence[SourceItem] | None = None,
    ledger: CostLedger | None = None,
    served_route: ServedRoute | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Stream a MODEL-WRITTEN synthesis as the `aggregator` subagent (real providers).

    When ``AGENTIC_VERIFIER`` is off, relays aggregator AnswerDeltas live.
    When on, collects the aggregator draft quietly under the aggregator span,
    then opens the verifier as a **sibling** subagent (Started → await judge →
    Done) before emitting the manager's final answer — so N-sample latency is
    visible and the verifier span is not a child of the aggregator (V-009).

    Mid-aggregator (BE-014): if accumulated aggregator spend pushes the run over
    the cap, stop the stream early and label the partial.

    ``merged_sources`` (B12): global catalog emitted after Started and before
    any synthesis AnswerDelta so main-answer citations resolve.

    Every degrade here keeps its own label channel and its own flag (FL-06): an
    aggregator crash labels a synthesis failure with `budget_halted=False`, a cap
    breach labels a budget halt with `budget_halted=True`, and a degraded
    verification caveats the answer and raises `partial`.

    ``ledger`` (AC-02): aggregator / verifier phases settle into the run's one
    accounting owner and the terminal `RunCost` carries its receipt.
    """
    yield SubagentStarted(
        subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
    )
    if merged_sources:
        yield Sources(items=list(merged_sources), subagent_id=_AGGREGATOR_ID)
    prompt = aggregate.build_synthesis_prompt(
        user_text,
        outputs,
        artifacts=artifacts,
        clarifications=clarifications,
    )
    aggregator_usage = UsageUpdate()
    answer_parts: list[str] = []
    agg_budget_halted = False
    verify_after = settings.agentic_verifier
    judge_factory = verifier_make_stream_for or make_stream_for
    verifier_pricer = verifier_cost_for_usage or cost_for_usage

    # When verify_after is on we quiet-collect the draft. Always advertise+execute
    # an empty tool allowlist and force web_search=False (O-011 / H-011) — aggregator
    # HITL continuation is not implemented, so gated tools must be unreachable.
    # Defense in depth: if AwaitingApproval / ToolCall / Sources / StatusUpdate
    # still appear under quiet-collect, yield them and do not run the verifier.
    agg_allowed = _AGGREGATOR_ALLOWED_TOOLS
    agg_make = make_stream_for(
        prompt, allowed_tools=agg_allowed, web_search=False
    )
    quiet_provenance = False
    aggregator_failed = False
    agg_pending_tool_name = "unknown"
    agg_pending_tool_label: str | None = None
    # Aggregator OTel span covers only aggregator work — never the verifier.
    with invoke_agent_span(
        subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
    ) as agg_span:

        def _settle_aggregator(outcome: str) -> None:
            agg_span.settle(
                route=served_route,
                usage=UsageTotals.copy_from(aggregator_usage),
                cost_usd=cost_for_usage(aggregator_usage),
                outcome=outcome,
            )

        try:
            async for event in run_agent_loop(
                make_stream=agg_make,
                settings=settings,
                allowed_tools=agg_allowed,
                # FL-04: the aggregator owns its recovery (`aggregate.synthesize`
                # below), so static filler must not make an empty draft look
                # written and shadow the degrade.
                inject_empty_fallback=False,
            ):
                if isinstance(event, ToolCall):
                    agg_pending_tool_name = event.name
                    agg_pending_tool_label = event.label
                if isinstance(event, AwaitingApproval):
                    # FL-24 / ORCH-7: aggregator HITL continuation does not exist
                    # (O-011), so this pause can never be resumed. Returning here
                    # ended the turn with no terminal, no RunCost and no
                    # SubagentDone, and left an actionable card whose approval
                    # would re-run the whole paid fan-out. Cancel the pending call
                    # and degrade through the deterministic tail instead.
                    yield tag_event(
                        ToolResult(
                            tool_call_id=event.tool_call_id,
                            name=agg_pending_tool_name,
                            label=agg_pending_tool_label,
                            status="cancelled",
                            approval_state="rejected",
                            summary="Cancelled: synthesis cannot pause for approval.",
                            error=(
                                "The synthesis step has no approval continuation; "
                                "the pending tool call was cancelled and the "
                                "answer was composed from completed sub-agents."
                            ),
                        ),
                        _AGGREGATOR_ID,
                    )
                    aggregator_failed = True
                    break
                # Fold BEFORE handing the event outward, as `run_single` and the
                # worker relay do. A consumer close lands `GeneratorExit` on the
                # yield this generator is suspended at, so a fold placed after it
                # never runs and the cancel arm settles the span on the previous
                # sample — under-reporting tokens already delivered.
                aggregator_usage = fold_usage(event, aggregator_usage)
                if verify_after and isinstance(
                    event, (ToolCall, ToolResult, Sources, StatusUpdate)
                ):
                    quiet_provenance = True
                    yield tag_event(event, _AGGREGATOR_ID)
                    continue
                if isinstance(event, AnswerDelta):
                    answer_parts.append(event.text)
                    if not verify_after:
                        yield tag_event(event, _AGGREGATOR_ID)
                elif not verify_after:
                    yield tag_event(event, _AGGREGATOR_ID)
                if not agg_budget_halted and budget.exceeds_cap(
                    actual_usd=worker_total_cost + cost_for_usage(aggregator_usage),
                    cap_usd=cap_usd,
                    headroom_usd=budget_headroom_usd,
                ):
                    agg_budget_halted = True
                    break
        except (asyncio.CancelledError, GeneratorExit):
            # AR-005: a Stop, or a consumer that closed this generator, is NOT a
            # synthesis failure — degrading it through the deterministic tail
            # would compose an answer nobody is waiting for and label the turn as
            # a failed aggregator. Close the span on what it spent and propagate.
            _settle_aggregator("stopped")
            raise
        except Exception:
            # B8: never raise to the generic handler error path — fall back to
            # deterministic synthesize() over completed workers and emit a failed
            # aggregator receipt with whatever usage was observed.
            _log.exception("agentic.aggregator_failed")
            aggregator_failed = True
        # AC-10: settle INSIDE the scope. The verifier is a sibling that runs
        # after this span closes, and the draft composition below spends nothing,
        # so everything the span reports is already known here.
        _settle_aggregator(
            _aggregator_outcome(
                failed=aggregator_failed, budget_halted=agg_budget_halted
            )
        )
    if agg_budget_halted:
        budget_halted = True
    streamed = "".join(answer_parts)
    draft = streamed
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
    suffix += _superseded_label(superseded)
    if aggregator_failed or main_answer_is_empty(streamed):
        draft = aggregate.synthesize(
            outputs,
            planned=planned,
            # FL-06: only a real cap breach may claim the budget label here.
            budget_halted=budget_halted,
            failed=failed,
        )
        draft += _superseded_label(superseded)
        if aggregator_failed:
            draft += _AGGREGATOR_FAILED_LABEL
            if verify_after and not main_answer_is_empty(streamed):
                # FL-07: only quiet-collect relayed nothing, so only it may put
                # the partial model text back on the wire. On the live-relay path
                # `streamed` already reached the user, and prepending it here
                # delivered the same prose twice.
                draft = streamed + "\n\n" + draft
    elif suffix:
        draft = streamed + suffix

    verifier_result: verifier.VerifyResult | None = None
    verifier_outcome: Literal["succeeded", "failed"] = "succeeded"
    final_answer = draft
    verifier_budget_halted = False
    verifier_started = False
    # Skip verify when quiet-collect saw tool/search provenance — the draft may
    # incorporate hidden work; surface events already yielded above.
    # Also skip when the aggregator itself failed (B8) — draft is deterministic.
    if verify_after and not quiet_provenance and not aggregator_failed:
        aggregator_cost_so_far = cost_for_usage(aggregator_usage)
        # Funding gate before opening the verifier bracket so we never emit a
        # Started with no matching Done on a budget skip.
        will_run = verifier.can_fund(
            ledger_usd=worker_total_cost + aggregator_cost_so_far,
            settings=settings,
            cost_for_usage=verifier_pricer,
            cap_usd=cap_usd,
            budget_headroom_usd=budget_headroom_usd,
            sample_count=1,
        )
        if will_run:
            yield SubagentStarted(
                subagent_id=_VERIFIER_ID, label=_VERIFIER_LABEL, role="verifier"
            )
            verifier_started = True
            try:
                verifier_result = await verifier.run_if_enabled(
                    settings=settings,
                    draft=draft,
                    make_stream_for=judge_factory,
                    user_text=user_text,
                    outputs=outputs,
                    scaffolded=scaffolded,
                    cost_for_usage=verifier_pricer,
                    ledger_usd=worker_total_cost + aggregator_cost_so_far,
                    cap_usd=cap_usd,
                    budget_headroom_usd=budget_headroom_usd,
                    served_route=served_route,
                )
            except Exception:
                _log.exception("agentic.verifier_failed")
                verifier_outcome = "failed"
                verifier_result = None
                # FL-19-b: disclose the judge failure instead of shipping a bare
                # draft that reads as verified. Same caveat the verifier module
                # composes for its own no-samples path (FL-02-a).
                final_answer = verifier.compose_verified_answer(
                    draft, verdict="pass", report="", incomplete_samples=True
                )
            else:
                final_answer, verifier_outcome, verifier_budget_halted = (
                    verifier.apply_result(draft, verifier_result)
                )
            if verifier_result is None and verifier_outcome == "succeeded":
                verifier_outcome = "failed"
            # Receipt (Complete/Done) before finalizing the manager answer (V-009).
            async for event in verifier.receipt_events(
                result=verifier_result,
                cost_for_usage=verifier_pricer,
                ledger_usd=worker_total_cost + aggregator_cost_so_far,
                cap_usd=cap_usd,
                outcome=verifier_outcome,
                emit_started=False,
            ):
                yield event
        else:
            # FL-18: a verifier skipped for budget must say so and flag the
            # receipt (spec `02-agent-architecture.md:255`). Silence shipped an
            # unverified answer that looked verified.
            final_answer = verifier.compose_verified_answer(
                draft, verdict="pass", report="", budget_halted=True
            )
            verifier_budget_halted = True
        yield AnswerDelta(text=final_answer, subagent_id=_AGGREGATOR_ID)
    elif (
        aggregator_failed
        or (verify_after and quiet_provenance)
        or main_answer_is_empty(streamed)
    ):
        yield AnswerDelta(text=draft, subagent_id=_AGGREGATOR_ID)
    elif suffix:
        yield AnswerDelta(text=suffix, subagent_id=_AGGREGATOR_ID)

    aggregator_cost = cost_for_usage(aggregator_usage)
    yield Complete(usage=aggregator_usage, subagent_id=_AGGREGATOR_ID)
    agg_outcome = _aggregator_outcome(
        failed=aggregator_failed, budget_halted=agg_budget_halted
    )
    yield SubagentDone(
        subagent_id=_AGGREGATOR_ID,
        label=_AGGREGATOR_LABEL,
        role="aggregator",
        usage=aggregator_usage,
        cost_usd=aggregator_cost,
        outcome=agg_outcome,
    )
    verifier_cost = 0.0
    v_usage = UsageUpdate()
    if verifier_started and verifier_result is not None:
        v_usage = verifier_result.usage
        verifier_cost = verifier.result_cost_usd(verifier_result, verifier_pricer)
    elif verifier_started and verifier_outcome == "failed":
        pass  # zero cost already; bracket closed above
    total_usage = sum_usages([*worker_usages, aggregator_usage, v_usage])
    if ledger is not None:
        ledger.settle(
            _AGGREGATOR_ID,
            role="aggregator",
            usage=aggregator_usage,
            cost_usd=aggregator_cost,
            outcome=agg_outcome,
        )
        if verifier_started:
            ledger.settle(
                _VERIFIER_ID,
                role="verifier",
                usage=v_usage,
                cost_usd=verifier_cost,
                outcome=verifier_outcome,
            )
    yield Complete(usage=total_usage)
    effective_budget_halted = budget_halted or verifier_budget_halted
    partial = (
        effective_budget_halted
        or failed > 0
        or aggregator_failed
        # FL-09 / FL-08: a cancelled sibling or a degraded verification is a
        # partial answer even when no worker failed and no cap was hit.
        or superseded > 0
        or verifier.verification_degraded(verifier_result, verifier_outcome)
    )
    if ledger is not None:
        yield _boundary_run_cost(
            ledger,
            cap_usd=cap_usd,
            partial=partial,
            budget_halted=effective_budget_halted,
            failed_worker_count=failed,
        )
    else:
        # No ledger: re-derive the total from the scalars (direct unit calls only).
        yield RunCost(
            subtotal_usd=worker_total_cost + aggregator_cost + verifier_cost,
            cap_usd=cap_usd,
            confidence="exact",
            phase="final",
            partial=partial,
            budget_halted=effective_budget_halted,
            failed_worker_count=failed,
        )


async def _collect_answer(
    make_stream_for: StreamFactory,
    settings: Settings,
    prompt: str,
    *,
    route: ServedRoute | None = None,
    cost_for_usage: CostForUsage | None = None,
) -> tuple[str, UsageUpdate]:
    """Run a bounded agent loop QUIETLY and return its (answer_text, usage).

    Used for the real-provider planner pass: the planner's reply is parsed into
    sub-questions, so its events are NOT surfaced as a subagent during the pass —
    only the answer text and accumulated usage matter. A later
    ``_emit_planner_receipt`` folds the usage into the run ledger.

    Least privilege (O-009): empty registry allowlist + ``web_search=False`` so
    the planner cannot execute turn tools or hidden provider search. An
    unexpected ``AwaitingApproval`` / tool / sources event raises rather than
    being reduced to empty plan text.

    ``route`` / ``cost_for_usage`` are what this pass's span closes with (AC-10).
    The A-5 fallback retry is a second call, so it opens and settles its own span
    with the fallback route rather than overwriting the failed primary's.
    """
    answer_parts: list[str] = []
    usage = UsageUpdate()
    with invoke_agent_span(
        subagent_id=_PLANNER_ID, role="orchestrator", label=_PLANNER_LABEL
    ) as span:

        def _settle(outcome: str) -> None:
            span.settle(
                route=route,
                usage=UsageTotals.copy_from(usage),
                cost_usd=None if cost_for_usage is None else cost_for_usage(usage),
                outcome=outcome,
            )

        try:
            async for event in run_agent_loop(
                make_stream=make_stream_for(
                    prompt,
                    allowed_tools=_PLANNER_ALLOWED_TOOLS,
                    web_search=False,
                ),
                settings=settings,
                allowed_tools=_PLANNER_ALLOWED_TOOLS,
                # Planner quiet-collect parses answer text into a plan; an
                # empty-retry nudge answer would corrupt that. Keep it out of the
                # retry (the empty terminal still injects the static fallback
                # text, unchanged).
                allow_empty_retry=False,
            ):
                if isinstance(
                    event,
                    (AwaitingApproval, ToolCall, ToolResult, Sources, StatusUpdate),
                ):
                    raise RuntimeError(
                        f"planner quiet-collect saw unexpected {type(event).__name__}"
                    )
                if isinstance(event, AnswerDelta):
                    answer_parts.append(event.text)
                usage = fold_usage(event, usage)
        except BaseException:
            # A planner pass that raised still spent whatever it streamed, and
            # the caller may retry on the fallback; the trace keeps both.
            _settle("failed")
            raise
        _settle("succeeded")
    return "".join(answer_parts), usage


# --- single mode (M1) ---------------------------------------------------------


async def run_single(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    cost_for_usage: CostForUsage,
    served_route: ServedRoute | None = None,
    budget_headroom_usd: float | None = None,
    server_approved_call_ids: set[str] | None = None,
    initial_tool_results: list[ToolResult] | None = None,
    prior_run_cost_usd: float = 0.0,
    prior_run_usage: UsageUpdate | None = None,
    prior_receipt: RunReceipt | None = None,
) -> AsyncIterator[ProviderEvent]:
    """One agent loop wrapped as the `primary` subagent.

    Enforces the same per-run cap as deep research (BE-020): pre-admit against a
    one-primary worst-case estimate, and mid-flight check against the effective
    cap composed with headroom.

    H-011: primary HITL continuation phase is not implemented. On tool-approval
    resume the handler must pass ``prior_run_cost_usd`` / ``prior_run_usage``
    (B5) so the per-run cap ledger is not reset. Pause-turn user billing stays
    with the handler; these seeds only affect the orchestrator cap ledger +
    cumulative attribution.

    ``prior_receipt`` (AC-02) is the preferred seed: restoring the pause turn's
    boundary receipt makes the resumed run's already-billed floor exact instead
    of reconstructed, so only this continuation's increment is billed again.
    """
    subagent_id = "primary"
    cap = settings.agentic_run_budget_usd
    # AC-02: one owner for this run's money for every exit below.
    ledger = CostLedger.restore(prior_receipt)
    expected = budget.expected_subagent_usage(settings)
    estimate = (
        cost_for_usage(expected)
        * settings.agentic_reasoning_token_multiplier
        * settings.agentic_fanout_token_multiplier
    )
    decision = budget.admit_run(
        estimate_usd=estimate, settings=settings, headroom_usd=budget_headroom_usd
    )
    if not decision.admitted:
        yield SubagentStarted(subagent_id=subagent_id, label=_PRIMARY_LABEL, role="primary")
        msg = (
            "The run was not started — estimated cost "
            f"${estimate:.4f} exceeds the ${decision.effective_cap_usd:.4f} run "
            "budget."
        )
        yield AnswerDelta(text=msg, subagent_id=subagent_id)
        empty = UsageUpdate()
        yield Complete(usage=empty, subagent_id=subagent_id)
        yield SubagentDone(
            subagent_id=subagent_id,
            label=_PRIMARY_LABEL,
            role="primary",
            usage=empty,
            cost_usd=0.0,
            outcome="failed",
        )
        yield Complete(usage=empty)
        ledger.settle(subagent_id, role="primary", cost_usd=0.0, outcome="failed")
        yield _boundary_run_cost(
            ledger, cap_usd=cap, partial=True, budget_halted=True
        )
        return

    if prior_receipt is not None:
        # AC-02: a present receipt is the SOLE restore authority. The B5 scalars
        # reconstruct the same pause spend from one row, so reading them here
        # would bill their disagreement with the receipt as spend in THIS turn.
        prior_usage = _restored_usage(ledger.usage_of(subagent_id))
        prior_cost = ledger.cost_of(subagent_id)
    else:
        prior_usage = prior_run_usage or UsageUpdate()
        prior_cost = max(0.0, float(prior_run_cost_usd or 0.0))
        if prior_cost <= 0.0 and has_nonzero_usage(prior_usage):
            prior_cost = cost_for_usage(prior_usage)
        if prior_cost > 0.0 or has_nonzero_usage(prior_usage):
            # Legacy pause row (no persisted receipt): the B5 seeds are the only
            # record of what the pause turn already charged.
            ledger.hold_billed_floor(prior_cost)
            ledger.settle(
                subagent_id,
                role="primary",
                usage=prior_usage,
                cost_usd=prior_cost,
                already_billed=True,
            )
    # The run's total before this session's tokens. `prior_cost` above is the
    # PRIMARY PHASE's share of it; these coincide in single mode but the cap and
    # the meter are run-level questions, so read them off the ledger.
    restored_run_cost = ledger.cumulative_cost_usd

    # FL-12: admission above prices only the FRESH estimate, so a resume whose
    # seeded ledger is already over the cap used to open another provider stream
    # and overrun by a whole primary turn. Refuse before `make_stream_for`, and
    # degrade to a labeled `done` rather than an error (invariant 8).
    if restored_run_cost > 0.0 and budget.exceeds_cap(
        actual_usd=restored_run_cost, cap_usd=cap, headroom_usd=budget_headroom_usd
    ):
        yield SubagentStarted(
            subagent_id=subagent_id, label=_PRIMARY_LABEL, role="primary"
        )
        yield AnswerDelta(
            text=EMPTY_REPLY_FALLBACK + _SINGLE_BUDGET_HALT_LABEL,
            subagent_id=subagent_id,
        )
        yield Complete(usage=prior_usage, subagent_id=subagent_id)
        yield SubagentDone(
            subagent_id=subagent_id,
            label=_PRIMARY_LABEL,
            role="primary",
            usage=prior_usage,
            cost_usd=prior_cost,
            outcome="budget_cancelled",
        )
        yield Complete(usage=prior_usage)
        # Re-stamps the phase's outcome; the money is whatever the branch above
        # put on the books, so this cannot move the total under either input.
        ledger.settle(
            subagent_id,
            role="primary",
            usage=prior_usage,
            cost_usd=prior_cost,
            outcome="budget_cancelled",
            already_billed=True,
        )
        yield _boundary_run_cost(
            ledger, cap_usd=cap, partial=True, budget_halted=True
        )
        return

    yield SubagentStarted(subagent_id=subagent_id, label=_PRIMARY_LABEL, role="primary")
    yield RunCost(
        subtotal_usd=restored_run_cost,
        cap_usd=cap,
        confidence="estimate" if restored_run_cost <= 0.0 else "exact",
        phase="plan",
    )
    # B5: track this session's usage separately from pre-pause seed so
    # `fold_usage` replace semantics cannot erase prior spend from the ledger.
    session_usage = UsageUpdate()
    answer_parts: list[str] = []
    budget_halted = False
    pending_tool_name = "unknown"
    pending_tool_label: str | None = None
    with invoke_agent_span(
        subagent_id=subagent_id, role="primary", label=_PRIMARY_LABEL
    ) as span:

        def _settle_primary(outcome: str) -> None:
            """AC-10: close the primary span with what actually served and spent.

            Called inside the span on EVERY exit — the pause `return`, the normal
            fall-through, a provider raise, and a Stop — because a span that has
            already ended cannot take attributes. Usage is whatever this session
            folded before the exit, so a failed or stopped turn still reports the
            tokens it really burned rather than nothing at all.
            """
            span.settle(
                route=served_route,
                usage=UsageTotals.copy_from(sum_usages([prior_usage, session_usage])),
                cost_usd=prior_cost + cost_for_usage(session_usage),
                outcome=outcome,
            )

        try:
            async for event in run_agent_loop(
                make_stream=make_stream_for(user_text),
                settings=settings,
                server_approved_call_ids=server_approved_call_ids,
                initial_tool_results=initial_tool_results,
            ):
                if isinstance(event, AnswerDelta):
                    answer_parts.append(event.text)
                if isinstance(event, ToolCall):
                    pending_tool_name = event.name
                    pending_tool_label = event.label
                session_usage = fold_usage(event, session_usage)
                session_cost = cost_for_usage(session_usage)
                if not budget_halted and budget.exceeds_cap(
                    actual_usd=restored_run_cost + session_cost,
                    cap_usd=cap,
                    headroom_usd=budget_headroom_usd,
                ):
                    budget_halted = True
                if isinstance(event, AwaitingApproval):
                    if budget_halted:
                        # FL-12: the cap is already breached, so an actionable card
                        # would only buy a resume that must immediately refuse.
                        # Cancel the pending call (AR-004 shape) and fall through
                        # to the labeled budget tail.
                        yield tag_event(
                            ToolResult(
                                tool_call_id=event.tool_call_id,
                                name=pending_tool_name,
                                label=pending_tool_label,
                                status="cancelled",
                                approval_state="rejected",
                                summary="Cancelled: run budget already exhausted.",
                                error=(
                                    "The run reached its budget cap before this "
                                    "approval could be shown."
                                ),
                            ),
                            subagent_id,
                        )
                        break
                    # FL-14: the handler `break`s at the pause terminal and never
                    # consumes post-pause events, so the untagged Complete (turn
                    # token roll-up) and the final RunCost receipt must precede the
                    # tagged pause. `SubagentDone` stays suppressed —
                    # `mark_unfinished_subagents_paused` deliberately keeps the
                    # primary non-terminal on a pause (B15). `partial=True` because
                    # the turn is resumable, not finished.
                    pause_usage = sum_usages([prior_usage, session_usage])
                    yield Complete(usage=pause_usage)
                    ledger.settle(
                        subagent_id,
                        role="primary",
                        usage=pause_usage,
                        cost_usd=prior_cost + cost_for_usage(session_usage),
                    )
                    yield _boundary_run_cost(
                        ledger, cap_usd=cap, boundary="pause", partial=True
                    )
                    _settle_primary("paused")
                    yield tag_event(event, subagent_id)
                    return
                yield tag_event(event, subagent_id)
                if budget_halted and isinstance(event, (Complete, UsageUpdate)):
                    break
        except (asyncio.CancelledError, GeneratorExit):
            # AR-005: a Stop or a closed consumer is not a provider failure. The
            # cap kill is still distinguishable, because reaching the cap is what
            # cancels this turn in the first place.
            _settle_primary("budget_cancelled" if budget_halted else "stopped")
            raise
        except BaseException:
            # Single mode has no fallback tail: the raise reaches the handler and
            # becomes the turn's error. The span closes on the way past so a
            # failed provider call is still attributable to a route and a spend.
            _settle_primary("failed")
            raise
        _settle_primary("budget_cancelled" if budget_halted else "succeeded")
    # FL-13: additive, not exclusive. A halt before any prose is a budget stop —
    # `main_answer_is_empty` winning here labeled it "didn't produce a written
    # reply" and dropped the budget label the flag on the wire claims.
    if budget_halted:
        prefix = (
            EMPTY_REPLY_FALLBACK
            if main_answer_is_empty("".join(answer_parts))
            else ""
        )
        yield AnswerDelta(
            text=prefix + _SINGLE_BUDGET_HALT_LABEL, subagent_id=subagent_id
        )
    elif main_answer_is_empty("".join(answer_parts)):
        yield AnswerDelta(text=EMPTY_REPLY_FALLBACK, subagent_id=subagent_id)
    cumulative_usage = sum_usages([prior_usage, session_usage])
    cost = prior_cost + cost_for_usage(session_usage)
    yield SubagentDone(
        subagent_id=subagent_id,
        label=_PRIMARY_LABEL,
        role="primary",
        usage=cumulative_usage,
        cost_usd=cost,
        outcome="budget_cancelled" if budget_halted else "succeeded",
    )
    # B14: untagged final Complete so the handler's "last Complete wins" fold
    # captures top-level turn tokens (mirrors deep research).
    yield Complete(usage=cumulative_usage)
    ledger.settle(
        subagent_id,
        role="primary",
        usage=cumulative_usage,
        cost_usd=cost,
        outcome="budget_cancelled" if budget_halted else "succeeded",
    )
    yield _boundary_run_cost(
        ledger,
        cap_usd=cap,
        partial=budget_halted,
        budget_halted=budget_halted,
    )


async def _resume_worker_continuation(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    cost_for_usage: CostForUsage,
    continuation: AgenticContinuation,
    resume_tool_result: ToolResult | None,
    server_approved_call_ids: set[str],
    served_route: ServedRoute | None = None,
    budget_headroom_usd: float | None = None,
    fallback_make_stream_for: StreamFactory | None = None,
    fallback_cost_for_usage: CostForUsage | None = None,
    fallback_provider_id: str | None = None,
    fallback_model_id: str | None = None,
    fallback_display_label: str | None = None,
    is_retryable: IsRetryable = is_retryable_provider_error,
    verifier_make_stream_for: StreamFactory | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
    prior_receipt: RunReceipt | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Continue a paused worker then synthesize (BE-005).

    Restores completed sibling results from the continuation blob, re-runs only
    the paused worker with validated tool feedback / server-approved call ids,
    then runs the normal aggregator path.

    H-009 / O-002: restores the pre-pause ledger and refuses further provider
    spend when already budget-halted or over cap. O-008: uses the same fallback
    path as fresh workers on retryable primary failure.

    ``prior_receipt`` (AC-02): the pause turn's boundary receipt. Restoring it
    makes the already-billed floor exact, so the resumed terminal charges only
    this continuation's increment rather than re-charging the whole pre-pause
    fan-out.
    """
    scaffolded = settings.provider_backend == "fake"
    cap = settings.agentic_run_budget_usd
    sub_questions = list(continuation.plan)
    effective_user_text = continuation.user_text
    paused_id = continuation.paused_subagent_id
    index = continuation.paused_worker_index or 0
    sub_question = continuation.paused_sub_question or (
        sub_questions[index] if index < len(sub_questions) else effective_user_text
    )
    label = f"Worker {index + 1}"

    results: dict[str, WorkerOutput] = {
        w.subagent_id: WorkerOutput(
            subagent_id=w.subagent_id,
            sub_question=w.sub_question,
            # FL-09: honor the persisted `outcome` — a superseded sibling's text
            # is a truncated partial, not a finished finding.
            answer=_fold_completed_answer(w),
            source_ids=w.source_ids,
        )
        for w in continuation.completed_workers
    }
    restored_superseded = sum(
        1 for w in continuation.completed_workers if w.outcome == "cancelled"
    )
    failed_workers = continuation.failed_workers
    budget_halted = continuation.budget_halted
    planner_usage = continuation.planner_usage
    # Prefer durable planner cost from the checkpoint (H-009).
    planner_cost = continuation.planner_cost_usd

    # AC-02: one owner for this resumed run's money and tokens — there is no
    # second per-phase dictionary. The pause receipt is the already-billed floor
    # AND the phase history, so every phase re-enters the run without being
    # charged a second time.
    ledger = CostLedger.restore(prior_receipt)
    if prior_receipt is not None:
        # A present receipt is the SOLE restore authority: the checkpoint's
        # `planner_cost_usd`, per-worker `cost_usd` and `actual_cost_usd` describe
        # the same pause spend less exactly, and replaying them over the restored
        # phases would bill the difference as spend in THIS continuation.
        ledger_usd = ledger.cumulative_cost_usd
    else:
        # Legacy checkpoint (written before receipts): its own cost fields are the
        # only record of the pause turn's spend, so replay them as billed phases.
        ledger_usd = float(continuation.actual_cost_usd or 0.0)
        if ledger_usd <= 0.0:
            ledger_usd = (
                sum(w.cost_usd for w in continuation.completed_workers)
                + planner_cost
                + float(continuation.paused_worker_cost_usd or 0.0)
            )
        ledger.hold_billed_floor(ledger_usd)
        ledger.settle(
            _PLANNER_ID,
            role="orchestrator",
            usage=planner_usage,
            cost_usd=planner_cost,
            already_billed=True,
        )
        for restored in continuation.completed_workers:
            ledger.settle(
                restored.subagent_id,
                role="worker",
                usage=restored.usage,
                cost_usd=restored.cost_usd,
                outcome=restored.outcome,
                already_billed=True,
            )

    worker_meta = [
        (i, f"worker-{i}", f"Worker {i + 1}", sq)
        for i, sq in enumerate(sub_questions)
    ]
    # B12: one namespace for the resume session, reopened over the allocator
    # state the pause turn published; mid-stream remap is the only mapping step.
    source_namespace = SourceNamespace.restored(
        catalog=continuation.source_catalog,
        allocations=continuation.source_allocations,
        next_id=continuation.source_next_id,
        prior_id_groups=[
            continuation.source_ids,
            *(out.source_ids for out in results.values()),
        ],
        # Legacy blobs carry no allocator state; every citation the pause turn
        # left in surviving answer text is a global it already rendered.
        prior_texts=[
            continuation.partial_answer,
            *(out.answer for out in results.values()),
        ],
    )

    if continuation.clarifications:
        # C-002: keep full Q&A records — do not collapse to non-blank answers
        # (that drops question text and re-shifts blank positions).
        resume_records = list(continuation.clarifications)
    else:
        # Legacy blobs: recover answers from prompt text only.
        parsed = clarify.parse_clarification_answers(effective_user_text)
        resume_records = clarify.records_from_questions_and_answers([], parsed)
    resume_clarification_answers = clarify.nonblank_answers(resume_records)
    verifier_pricer = verifier_cost_for_usage or cost_for_usage

    async def _emit_synthesis(*, halted: bool) -> AsyncIterator[ProviderEvent]:
        ordered_outputs = [
            results[sid] for _, sid, _, _ in worker_meta if sid in results
        ]
        ordered_artifacts = aggregate.build_artifacts(
            ordered_outputs, max_artifacts=settings.agentic_max_workers
        )
        # AC-02: the ledger already holds planner + restored siblings + the
        # resumed worker, and its cumulative can never drop below the pause
        # turn's durable total.
        ordered_usages = [
            _restored_usage(ledger.usage_of(sid))
            for _, sid, _, _ in worker_meta
            if ledger.phase(sid) is not None
        ]
        ordered_usages.append(_restored_usage(ledger.usage_of(_PLANNER_ID)))
        worker_total_cost = ledger.cumulative_cost_usd
        completed_count = len(ordered_outputs)
        synthesis = aggregate.synthesize(
            ordered_outputs,
            planned=len(sub_questions),
            budget_halted=halted,
            failed=failed_workers,
            clarifications=resume_clarification_answers,
        )
        merged_sources = source_namespace.merged_items()
        # Streamed finalize owns aggregator (+ sibling verifier) spans — do not
        # nest them under an outer resume aggregator span (V-009 / Sol).
        if not scaffolded and ordered_outputs and not halted:
            synth_clarify = clarify.clarification_payload_for_phase(
                resume_records, phase="synthesis"
            ) or None
            async for event in _finalize_synthesis_streamed(
                make_stream_for=make_stream_for,
                verifier_make_stream_for=verifier_make_stream_for,
                settings=settings,
                user_text=clarify.strip_clarification_footer(effective_user_text),
                outputs=ordered_outputs,
                planned=len(sub_questions),
                worker_usages=ordered_usages,
                worker_total_cost=worker_total_cost,
                cost_for_usage=cost_for_usage,
                verifier_cost_for_usage=verifier_pricer,
                cap_usd=cap,
                budget_halted=halted,
                failed=failed_workers,
                superseded=restored_superseded,
                budget_headroom_usd=budget_headroom_usd,
                scaffolded=scaffolded,
                artifacts=ordered_artifacts,
                clarifications=synth_clarify,
                merged_sources=merged_sources or None,
                ledger=ledger,
                served_route=served_route,
            ):
                yield event
            return
        with invoke_agent_span(
            subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
        ) as agg_span:
            # A deterministic resume synthesis spends nothing of its own; the
            # span records the route it would have used and a zero-token close.
            agg_span.settle(
                route=served_route,
                usage=UsageTotals(),
                cost_usd=0.0,
                outcome="succeeded",
            )
            async for event in _finalize_synthesis(
                synthesis=synthesis,
                worker_usages=ordered_usages,
                worker_total_cost=worker_total_cost,
                cost_for_usage=cost_for_usage,
                cap_usd=cap,
                budget_halted=halted,
                failed_worker_count=failed_workers,
                superseded_worker_count=restored_superseded,
                planned_workers=len(sub_questions),
                completed_workers=completed_count,
                merged_sources=merged_sources or None,
                ledger=ledger,
            ):
                yield event

    # H-009: halt without another provider call when the durable ledger is
    # already exhausted / flagged budget_halted.
    if budget_halted or budget.exceeds_cap(
        actual_usd=ledger_usd, cap_usd=cap, headroom_usd=budget_headroom_usd
    ):
        budget_halted = True
        yield RunCost(
            subtotal_usd=ledger_usd,
            cap_usd=cap,
            confidence="exact",
            phase="progress",
            partial=True,
            budget_halted=True,
        )
        async for event in _emit_synthesis(halted=True):
            yield event
        return

    # B2: pre-pause usage stays immutable on the seed, so the runner's fold
    # (which REPLACES the provider's running total) cannot erase pause spend.
    if prior_receipt is not None:
        # AC-02: the restored phase for this worker is what the pause turn
        # actually billed; the checkpoint's own numbers are the legacy input.
        pre_pause_usage = _restored_usage(ledger.usage_of(paused_id))
        pre_pause_cost = ledger.cost_of(paused_id)
    else:
        pre_pause_usage = continuation.paused_worker_usage or UsageUpdate()
        pre_pause_cost = float(continuation.paused_worker_cost_usd or 0.0)
        if pre_pause_cost <= 0.0 and has_nonzero_usage(pre_pause_usage):
            # Prefer the durable pause pricer: if the pause was on fallback, the
            # stored paused_worker_cost_usd should already be set; otherwise price
            # on primary (legacy blobs).
            if (
                continuation.paused_worker_used_fallback
                and fallback_cost_for_usage is not None
            ):
                pre_pause_cost = fallback_cost_for_usage(pre_pause_usage)
            else:
                pre_pause_cost = cost_for_usage(pre_pause_usage)
    # H-010: everything the pause turn durably recorded is restored onto ONE
    # seed — its partial prose and reasoning, the citations it published, its
    # transcript, the tool results it already settled, and the spend it was
    # billed for. The runner reads a resumed seed exactly as it reads a fresh
    # one, which is why there is no second execution engine here (AC-09).
    tool_transcript = [dict(part) for part in continuation.tool_transcript]
    prior_tool_results = tool_results_from_transcript(
        continuation.tool_transcript, subagent_id=paused_id
    )
    if resume_tool_result is not None:
        prior_tool_results.append(resume_tool_result)
        # Include the settled resume result in the durable transcript so a
        # second nested pause does not drop the first approval's tool_result.
        tool_transcript.append(tool_transcript_part(resume_tool_result, paused_id))

    runner = WorkerRunner(
        settings=settings,
        routes=WorkerRoutes(
            make_stream_for=make_stream_for,
            cost_for_usage=cost_for_usage,
            primary=served_route,
            fallback_make_stream_for=fallback_make_stream_for,
            fallback_cost_for_usage=fallback_cost_for_usage,
            fallback_provider_id=fallback_provider_id,
            fallback_model_id=fallback_model_id,
            fallback_display_label=fallback_display_label,
            is_retryable=is_retryable,
        ),
        sources=source_namespace,
        ledger=ledger,
        # B3: a resume has no sibling fan-out and no consumer to cancel it, so
        # the cap is enforced on this worker's own stream. The baseline is what
        # the run had already banked before this continuation.
        budget_gate=budget.BudgetGate(
            baseline_usd=ledger_usd,
            cap_usd=cap,
            headroom_usd=budget_headroom_usd,
        ),
    )
    seed = ResumedWorkerSeed(
        index=index,
        subagent_id=paused_id,
        label=label,
        sub_question=sub_question,
        prompt=clarify.with_clarifications(
            planner.worker_prompt(index, sub_question, scaffolded=scaffolded),
            resume_records,
            phase="worker",
        ),
        server_approved_call_ids=frozenset(server_approved_call_ids),
        prior_tool_results=tuple(prior_tool_results),
        prior_answer=continuation.partial_answer,
        prior_reasoning=continuation.partial_reasoning,
        prior_source_ids=tuple(continuation.source_ids),
        prior_tool_transcript=tuple(tool_transcript),
        prior_usage=pre_pause_usage,
        prior_cost_usd=pre_pause_cost,
        prior_emitted_answer_chars=continuation.emitted_answer_chars,
        # B6: pin the resume onto the route that served the pause.
        pinned_to_fallback=bool(continuation.paused_worker_used_fallback),
    )

    def _nested_continuation(
        paused: WorkerResult, *, halted: bool
    ) -> AgenticContinuation:
        """Checkpoint a pause nested inside this resume (H-010).

        The whole worker is re-checkpointed, not just this continuation's
        increment, so the next resume restores the same complete seed.
        """
        return AgenticContinuation(
            phase="worker",
            paused_subagent_id=paused_id,
            user_text=effective_user_text,
            plan=tuple(sub_questions),
            completed_workers=tuple(continuation.completed_workers),
            planner_usage=planner_usage,
            planner_cost_usd=planner_cost,
            budget_halted=halted,
            failed_workers=failed_workers,
            # The ledger floor already includes pre-pause spend; add only what
            # this continuation's session put on top of it.
            actual_cost_usd=ledger_usd + paused.session_cost_usd,
            paused_worker_index=index,
            paused_sub_question=sub_question,
            partial_answer=paused.answer,
            partial_reasoning=paused.reasoning,
            source_ids=paused.source_ids,
            source_catalog=tuple(source_namespace.merged_items()),
            source_allocations=source_namespace.allocations(),
            source_next_id=source_namespace.next_id,
            tool_transcript=paused.tool_transcript,
            emitted_answer_chars=paused.emitted_answer_chars,
            clarifications=continuation.clarifications,
            orchestration_mode=continuation.orchestration_mode,
            tier_id=continuation.tier_id,
            provider_id=continuation.provider_id,
            model_id=continuation.model_id,
            paused_worker_usage=paused.usage,
            paused_worker_cost_usd=paused.cost_usd,
            paused_worker_used_fallback=paused.used_fallback,
        )

    # `aclosing` so a stop delivered mid-relay still runs the runner's cancelled
    # settlement rather than leaving the row for the event loop to finalize.
    async with contextlib.aclosing(runner.run(seed)) as stream:
        async for event in stream:
            yield event
    outcome = runner.outcome
    if outcome is None:  # pragma: no cover - `run` always settles an outcome
        return
    budget_halted = budget_halted or outcome.result.budget_halted

    if isinstance(outcome, WorkerPaused):
        paused = outcome.result
        # AC-02: a nested pause is a persistable boundary too, so it carries the
        # receipt for the spend banked up to it. The runner leaves the pause
        # unsettled because only the phase owner knows what it is worth.
        ledger.settle(
            paused_id,
            role="worker",
            usage=paused.usage,
            cost_usd=paused.cost_usd,
            outcome="stopped",
        )
        yield _boundary_run_cost(
            ledger,
            cap_usd=cap,
            boundary="pause",
            partial=True,
            budget_halted=budget_halted,
            failed_worker_count=failed_workers,
        )
        yield AwaitingApproval(
            tool_call_id=outcome.tool_call_id,
            subagent_id=paused_id,
            continuation=serialize_continuation(
                _nested_continuation(paused, halted=budget_halted)
            ),
        )
        return

    if outcome.outcome == "failed":
        failed_workers += 1
    else:
        results[paused_id] = _worker_output(outcome.result)
    yield outcome.done_event

    # Mid-stream remapper already assigned global ids — do not remap again.
    async for event in _emit_synthesis(halted=budget_halted):
        yield event


# --- deep_research mode (M2 + M3 budget/approval/verify) ----------------------


async def _run_deep_research(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    cost_for_usage: CostForUsage,
    served_route: ServedRoute | None = None,
    estimate_cost: CostEstimator | None = None,
    budget_headroom_usd: float | None = None,
    plan_approved: bool | None = None,
    approved_plan: list[str] | None = None,
    clarify_answered: bool | None = None,
    clarify_answers: list[str] | None = None,
    clarify_records: list[clarify.ClarificationRecord] | None = None,
    agentic_continuation: AgenticContinuation | None = None,
    resume_tool_result: ToolResult | None = None,
    server_approved_call_ids: set[str] | None = None,
    fallback_make_stream_for: StreamFactory | None = None,
    fallback_cost_for_usage: CostForUsage | None = None,
    fallback_provider_id: str | None = None,
    fallback_model_id: str | None = None,
    fallback_display_label: str | None = None,
    is_retryable: IsRetryable = is_retryable_provider_error,
    verifier_make_stream_for: StreamFactory | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
    prior_planner_cost_usd: float = 0.0,
    prior_planner_usage: UsageUpdate | None = None,
    prior_receipt: RunReceipt | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Clarify? → plan → (approve) → admit → parallel fan-out → (verify) → synthesis.

    `clarify_answered` carries the clarify-before-plan HITL decision across the
    resume: None on a fresh run (pause if the flag + heuristic/marker fire),
    True/False on the resume (continue with answers / decline). `plan_approved`
    carries the plan-approval HITL decision: None on a fresh run (pause if the
    flag is on), True/False on the resume (fan out / decline). When True,
    ``approved_plan`` is the immutable plan the user approved (BE-039) — never
    re-planned. `estimate_cost` + `budget_headroom_usd` drive the pre-spawn
    reservation and the mid-flight kill.

    ``verifier_cost_for_usage`` is the phase pricer for the fresh-context judge
    (attachments=None → image_count=0). Defaults to ``cost_for_usage``.

    ``prior_planner_cost_usd`` / ``prior_planner_usage`` (B4): on plan-approved
    resume, seed the run-cap ledger with planner spend from the pause turn
    without re-emitting a planner receipt (handler already billed pause turn).

    ``prior_receipt`` (AC-02) supersedes those seeds when the pause row carries
    one: the resumed run's already-billed floor is then the pause boundary's own
    cumulative total rather than a reconstruction of it.
    """
    verifier_pricer = verifier_cost_for_usage or cost_for_usage
    # Provider-backend split: the FAKE provider keys on the deterministic
    # `DEEP_RESEARCH_WORKER:`/`DEEP_RESEARCH:` scaffolding (the test contract), so
    # it always uses the marker-based `decompose` + scaffolded worker prompts. A
    # REAL provider must never see scaffolding: it gets a model-driven plan (so a
    # plain prompt fans out WITHOUT the `DEEP_RESEARCH:` marker) and clean worker
    # prompts, then a streamed model-written synthesis.
    # BE-005: resume a paused worker without re-planning (O-011: aggregator
    # continuation is intentionally unsupported).
    if agentic_continuation is not None and agentic_continuation.phase == "worker":
        async for event in _resume_worker_continuation(
            make_stream_for=make_stream_for,
            settings=settings,
            cost_for_usage=cost_for_usage,
            continuation=agentic_continuation,
            resume_tool_result=resume_tool_result,
            server_approved_call_ids=server_approved_call_ids or set(),
            served_route=served_route,
            budget_headroom_usd=budget_headroom_usd,
            fallback_make_stream_for=fallback_make_stream_for,
            fallback_cost_for_usage=fallback_cost_for_usage,
            fallback_provider_id=fallback_provider_id,
            fallback_model_id=fallback_model_id,
            fallback_display_label=fallback_display_label,
            is_retryable=is_retryable,
            verifier_make_stream_for=verifier_make_stream_for,
            verifier_cost_for_usage=verifier_pricer,
            prior_receipt=prior_receipt,
        ):
            yield event
        return

    scaffolded = settings.provider_backend == "fake"
    # AC-02: one owner for this run's money and tokens, from the first gate to the
    # terminal receipt. A resume restores the pause boundary's receipt so its
    # spend counts toward the cumulative total but is never billed twice.
    ledger = CostLedger.restore(prior_receipt)

    # Clarify-before-plan HITL (plan 02). Runs BEFORE planning so we do not spend
    # planner tokens / commit the ~15x budget on an ambiguous brief. Decline
    # short-circuits with a labeled synthesis (no plan, no workers). Only on a
    # fresh run (`plan_approved is None`) - a plan-approval resume has already
    # passed this gate.
    if clarify_answered is None and plan_approved is None:
        clarify_paused = False
        async for event in _maybe_clarify_before_plan(
            settings,
            user_text=user_text,
            scaffolded=scaffolded,
            ledger=ledger,
            cap_usd=settings.agentic_run_budget_usd,
        ):
            clarify_paused = True
            yield event
        if clarify_paused:
            return
    elif clarify_answered is False:
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: clarifying questions were skipped; no research plan "
                "was started."
            ),
            worker_usages=[],
            worker_total_cost=0.0,
            cost_for_usage=cost_for_usage,
            cap_usd=settings.agentic_run_budget_usd,
            ledger=ledger,
        ):
            yield event
        return

    # Fold clarifications as SEPARATE DATA — never into the DEEP_RESEARCH
    # scaffold that ``decompose`` pipe-splits. Strip the CLARIFY: marker only
    # when the clarify flag is on AND the path is scaffolded (C-004) so real
    # requests and flag-off paths stay byte-preserving.
    plan_text = clarify.strip_clarify_marker(
        user_text,
        allow_strip=scaffolded and settings.agentic_clarify_before_plan,
    )
    # Prefer full Q&A records from the resume seed (C-002). Falling back to
    # answer-only lists loses question text — only for legacy callers.
    if clarify_records is not None:
        bound_records = list(clarify_records)
    else:
        bound_records = clarify.records_from_questions_and_answers(
            [], list(clarify_answers) if clarify_answers is not None else None
        )
    answers = clarify.nonblank_answers(bound_records)
    # Context for planner / synthesis: plan text + clarification DATA (planner
    # phase ceiling). Workers attach a tighter copy separately (O-014).
    effective_user_text = clarify.with_clarifications(
        plan_text, bound_records, phase="planner"
    )

    planner_usage = UsageUpdate()
    # FL-11: True once the A-5 retry was served on the fallback route.
    planner_used_fallback = False
    # B4: durable planner spend from the plan-approval pause (resume only).
    seeded_planner_cost = max(0.0, float(prior_planner_cost_usd or 0.0))
    seeded_planner_usage = prior_planner_usage or UsageUpdate()
    if seeded_planner_cost <= 0.0 and has_nonzero_usage(seeded_planner_usage):
        seeded_planner_cost = cost_for_usage(seeded_planner_usage)
    max_workers = settings.agentic_max_workers
    if plan_approved is True and approved_plan is not None:
        # Resume after approve: execute the exact persisted plan (BE-039).
        # Planner spend was already billed on the pause turn — do not re-plan.
        sub_questions = [q for q in approved_plan if isinstance(q, str) and q.strip()][
            :max_workers
        ]
        if not sub_questions:
            sub_questions = [plan_text]
    elif (
        scaffolded
        or plan_text.startswith(planner.DEEP_RESEARCH_PREFIX)
        or plan_approved is False
        # FL-25: an APPROVED resume must never reach the model planner, even when
        # the persisted plan is missing or malformed (a corrupted or pre-BE-039
        # row). Re-planning would spend planner tokens on, and fan out over, a
        # plan the user never saw — breaking the BE-039 contract above.
        or plan_approved is True
    ):
        # Deterministic decomposition: the fake provider, an explicit
        # `DEEP_RESEARCH:` opt-in, a decline (sub-questions go unused — no
        # fan-out — so skip the model planner call entirely), or an approved
        # resume with an unusable plan. Uses plan_text only so clarifications
        # never enter the pipe-split.
        sub_questions = planner.decompose(plan_text, max_workers=max_workers)
    else:
        # Real-provider planner: a bounded model pass decomposes the prompt into
        # sub-questions so a plain request fans out without the user typing the
        # `DEEP_RESEARCH:` marker. Clarifications ride as trailing DATA.
        # A-5: retry once on a fallback route; last resort is deterministic
        # decompose so a transient planner outage does not kill the whole run.
        planner_prompt = planner.build_planner_prompt(
            effective_user_text, max_workers=max_workers
        )
        try:
            plan_reply, planner_usage = await _collect_answer(
                make_stream_for,
                settings,
                planner_prompt,
                route=served_route,
                cost_for_usage=cost_for_usage,
            )
        except asyncio.CancelledError:
            raise
        except Exception as plan_exc:
            if fallback_make_stream_for is not None and is_retryable(plan_exc):
                try:
                    plan_reply, planner_usage = await _collect_answer(
                        fallback_make_stream_for,
                        settings,
                        planner_prompt,
                        route=_substituted_route(
                            served_route,
                            provider_id=fallback_provider_id,
                            model_id=fallback_model_id,
                        ),
                        cost_for_usage=fallback_cost_for_usage or cost_for_usage,
                    )
                    # FL-11: which factory answered decides the pricer AND the
                    # attribution; discarding it under-billed the planner and
                    # reported a primary model the run never used.
                    planner_used_fallback = True
                except asyncio.CancelledError:
                    raise
                except Exception as fallback_exc:
                    _log.warning(
                        "agentic.planner_fallback_failed",
                        error=str(fallback_exc),
                    )
                    plan_reply = ""
                    planner_usage = UsageUpdate()
            else:
                _log.warning("agentic.planner_failed", error=str(plan_exc))
                plan_reply = ""
                planner_usage = UsageUpdate()
        sub_questions = planner.parse_plan(
            plan_reply, max_workers=max_workers, fallback=plan_text
        )
        if not sub_questions:
            sub_questions = planner.decompose(plan_text, max_workers=max_workers)
    cap = settings.agentic_run_budget_usd
    estimate = estimate_cost(len(sub_questions)) if estimate_cost is not None else 0.0
    # O-014: fold amplified clarification prompt chars into admission so a
    # max-size clarify block cannot understate worst-case spend across phases.
    extra_clarify_tokens = clarify.clarification_extra_input_tokens(
        bound_records, worker_count=len(sub_questions)
    )
    if extra_clarify_tokens > 0:
        estimate += cost_for_usage(UsageUpdate(input_tokens=extra_clarify_tokens))

    # Plan-approval HITL gate (T6). On a fresh run with the flag on, pause for a
    # human decision BEFORE any fan-out. The resume re-enters here with
    # `plan_approved` set. Fold real planner spend BEFORE AwaitingApproval so the
    # handler persists it when the pause terminal stops the stream (BE-015).
    def _price_planner(u: UsageUpdate) -> float:
        # FL-11: price on the binding that actually served the planner.
        if planner_used_fallback and fallback_cost_for_usage is not None:
            return fallback_cost_for_usage(u)
        return cost_for_usage(u)

    def _planner_receipt(*, open_bracket: bool = False) -> AsyncIterator[ProviderEvent]:
        """Planner receipt stamped with the route that actually served (FL-11)."""
        return _emit_planner_receipt(
            planner_usage=planner_usage,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
            ledger_usd=ledger.cumulative_cost_usd,
            open_bracket=open_bracket,
            used_fallback=planner_used_fallback,
            fallback_cost_for_usage=fallback_cost_for_usage,
            fallback_provider_id=fallback_provider_id,
            fallback_model_id=fallback_model_id,
            fallback_display_label=fallback_display_label,
        )

    planner_cost = _price_planner(planner_usage)
    if plan_approved is None:
        # Fresh run: the planner pass this turn just made (empty on the
        # deterministic decompose path) is the phase.
        ledger.settle(
            _PLANNER_ID,
            role="orchestrator",
            usage=planner_usage,
            cost_usd=planner_cost,
        )
    elif prior_receipt is not None:
        # AC-02: approve or deny, a resume never re-plans, so the planner spend on
        # the books belongs to the pause turn and a present receipt is its SOLE
        # restore authority. `restore()` already put that phase back with the
        # amount the pause terminal billed — read it, never settle over it. The B4
        # scalar would bill its disagreement with the receipt as spend in THIS
        # turn, and this turn's empty planner pass would erase the phase history
        # the receipt owns, leaving the terminal receipt's phase sum below its own
        # cumulative even though the billed floor keeps the charge at zero.
        planner_cost = ledger.cost_of(_PLANNER_ID)
    else:
        # Legacy pause row: the B4 seed is the only record of the spend the pause
        # terminal already charged. Live `planner_usage` is empty on either resume
        # decision — the plan was not re-planned — so `_emit_planner_receipt`
        # stays quiet.
        planner_cost = seeded_planner_cost
        ledger.hold_billed_floor(planner_cost)
        ledger.settle(
            _PLANNER_ID,
            role="orchestrator",
            usage=seeded_planner_usage,
            cost_usd=planner_cost,
            already_billed=True,
        )
    if plan_approved is None:
        if settings.agentic_plan_approval:
            async for event in _planner_receipt(open_bracket=True):
                yield event
            async for event in _maybe_plan_approval(
                settings,
                sub_questions,
                estimate_usd=estimate,
                cap_usd=cap,
                skip_started=True,
                clarifications=bound_records,
                planner_cost_usd=planner_cost,
                planner_usage=planner_usage,
                ledger=ledger,
            ):
                yield event
            return
    elif plan_approved is False:
        # Declined on resume: no fan-out, a labeled (non-error) synthesis. The
        # planner tokens of the paused run still belong in the turn's roll-up, and
        # the ledger's planner phase is where they live (from the receipt, or from
        # the B4 seed for a legacy row).
        async for event in _planner_receipt():
            yield event
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the research plan was declined; no sub-agents were run."
            ),
            worker_usages=[_restored_usage(ledger.usage_of(_PLANNER_ID))],
            worker_total_cost=planner_cost,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
            ledger=ledger,
        ):
            yield event
        return

    # Pre-spawn admission (T5). If the worst-case estimate already exceeds the
    # effective cap (run cap composed with user/platform headroom), don't spawn —
    # degrade gracefully to a labeled, explained synthesis (never a silent
    # overrun, never an error). Fold planner spend into the reject exit (BE-015).
    decision = budget.admit_run(
        estimate_usd=estimate, settings=settings, headroom_usd=budget_headroom_usd
    )
    if not decision.admitted:
        async for event in _planner_receipt():
            yield event
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the run was not started — estimated cost "
                f"${estimate:.4f} exceeds the ${decision.effective_cap_usd:.4f} run "
                "budget. No sub-agents were spawned."
            ),
            worker_usages=[planner_usage],
            worker_total_cost=planner_cost,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
            # FL-21: an admit-reject IS a budget refusal. Reporting it with
            # default flags made this the only refusal that looked like a clean
            # run, unlike its twins at the single-mode and planner-spend gates.
            budget_halted=True,
            ledger=ledger,
        ):
            yield event
        return

    # Seed the run ledger with planner actuals before fan-out (BE-014 / SAF-004).
    async for event in _planner_receipt():
        yield event
    if budget.exceeds_cap(
        actual_usd=planner_cost, cap_usd=cap, headroom_usd=budget_headroom_usd
    ):
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the run was not started — planner spend already "
                f"exceeds the ${decision.effective_cap_usd:.4f} run budget. "
                "No sub-agents were spawned."
            ),
            worker_usages=[planner_usage],
            worker_total_cost=planner_cost,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
            budget_halted=True,
            ledger=ledger,
        ):
            yield event
        return

    semaphore = asyncio.Semaphore(max(1, settings.agentic_max_concurrency))
    queue: asyncio.Queue[ProviderEvent | _WorkerSentinel | WorkerPaused] = asyncio.Queue(
        maxsize=_FANOUT_QUEUE_MAXSIZE
    )
    # Worker bookkeeping, keyed by subagent_id and ordered by `worker_meta` so the
    # synthesis (and per-subagent totals) preserve sub-question order regardless
    # of the nondeterministic completion order of the parallel workers.
    worker_meta = [
        (index, f"worker-{index}", f"Worker {index + 1}", sub_question)
        for index, sub_question in enumerate(sub_questions)
    ]
    results: dict[str, WorkerOutput] = {}
    failed_workers = 0
    superseded_workers = 0
    source_namespace = SourceNamespace()
    worker_routes = WorkerRoutes(
        make_stream_for=make_stream_for,
        cost_for_usage=cost_for_usage,
        primary=served_route,
        fallback_make_stream_for=fallback_make_stream_for,
        fallback_cost_for_usage=fallback_cost_for_usage,
        fallback_provider_id=fallback_provider_id,
        fallback_model_id=fallback_model_id,
        fallback_display_label=fallback_display_label,
        is_retryable=is_retryable,
    )
    # Mid-flight kill (T5 / B3): the ledger already holds planner actuals
    # (BE-014), takes provisional UsageUpdate/Complete samples from each running
    # worker, and is settled by the runner on that worker's terminal; on a cap
    # breach, cancel the remaining workers.
    budget_halted = False

    async def _run_worker(seed: FreshWorkerSeed) -> None:
        """Schedule ONE worker and relay its stream onto the fan-out queue.

        Everything about the worker's own lifecycle — event tagging, citation
        rewriting, transcript capture, the fallback route, pricing on the binding
        that served, ledger settlement and the terminal classification — belongs
        to `WorkerRunner` (AC-09). This function owns only what the orchestrator
        must own: the semaphore, the queue, and cancellation.
        """
        nonlocal failed_workers
        runner = WorkerRunner(
            settings=settings,
            routes=worker_routes,
            sources=source_namespace,
            ledger=ledger,
            # A fresh worker does not halt itself: the consumer below cancels the
            # fan-out on a cap breach, so the gate is the run's, not the row's.
            is_run_budget_halted=lambda: budget_halted,
        )
        try:
            async with semaphore:
                # `aclosing` so a cancel delivered while putting onto a full queue
                # still runs the runner's cancelled settlement — leaving the
                # generator for the loop to finalize later would lose the row.
                async with contextlib.aclosing(runner.run(seed)) as stream:
                    async for event in stream:
                        await queue.put(event)
                outcome = runner.outcome
                if isinstance(outcome, WorkerPaused):
                    # BE-005: leave WITHOUT a terminal — a resume continues this
                    # worker. Siblings keep running (wait policy); the consumer
                    # keeps the first pause and cancels the rest.
                    await queue.put(outcome)
                    return
                if outcome is None:
                    return
                if outcome.outcome == "failed":
                    failed_workers += 1
                else:
                    results[seed.subagent_id] = _worker_output(outcome.result)
                await queue.put(outcome.done_event)
        except asyncio.CancelledError:
            # Budget mid-flight kill (or outer teardown): a row that opened still
            # owes the wire a terminal so the FE never shows a green check for a
            # cancelled worker (FE-002), and its snapshot spend survives into the
            # final `Complete` (SAF-005). `runner.outcome` is None exactly when
            # the row never opened (cancelled while queued on the semaphore).
            # B23: non-blocking put — the consumer may have stopped draining.
            cancelled = runner.outcome
            if cancelled is not None and cancelled.done_event is not None:
                _queue_put_nowait_drop_oldest(queue, cancelled.done_event)
            raise
        finally:
            # B23: sentinel must not block teardown on a full queue.
            _queue_put_nowait_drop_oldest(queue, _WorkerSentinel(seed.subagent_id))

    tasks = [
        asyncio.create_task(
            _run_worker(
                FreshWorkerSeed(
                    index=index,
                    subagent_id=subagent_id,
                    label=label,
                    sub_question=sub_question,
                    prompt=clarify.with_clarifications(
                        planner.worker_prompt(
                            index, sub_question, scaffolded=scaffolded
                        ),
                        bound_records,
                        phase="worker",
                    ),
                )
            )
        )
        for index, subagent_id, label, sub_question in worker_meta
    ]
    # `actual_cost` is the high-water mark of the ledger's total: an exact
    # settlement can come in BELOW its provisional sample, and the durable
    # checkpoint's cap floor must not fall when it does.
    actual_cost = planner_cost
    # BE-005: at most one worker tool-HITL pause per fan-out (first wins).
    # Sibling policy = wait for others to finish before surfacing AwaitingApproval.
    worker_pause: WorkerPaused | None = None
    # AR-023: sibling pauses cancelled as superseded — not "succeeded".
    superseded_worker_ids: set[str] = set()

    def _maybe_budget_kill() -> None:
        nonlocal budget_halted, actual_cost
        actual_cost = max(actual_cost, ledger.cumulative_cost_usd)
        if not budget_halted and budget.exceeds_cap(
            actual_usd=actual_cost, cap_usd=cap, headroom_usd=budget_headroom_usd
        ):
            budget_halted = True
            for task in tasks:
                if not task.done():
                    task.cancel()

    try:
        remaining = len(tasks)
        while remaining > 0:
            item = await queue.get()
            if isinstance(item, _WorkerSentinel):
                remaining -= 1
                continue
            if isinstance(item, WorkerPaused):
                paused = item.result
                if worker_pause is None:
                    worker_pause = item
                    # The runner leaves a pause unsettled because only the phase
                    # owner knows what it is worth. This one won the run's
                    # continuation, so bank its partial for the boundary receipt.
                    ledger.settle(
                        paused.subagent_id,
                        role="worker",
                        usage=paused.usage,
                        cost_usd=paused.cost_usd,
                        outcome="stopped",
                    )
                    _maybe_budget_kill()
                else:
                    # H-003 / O-007 / B24: cancel orphaned sibling pauses.
                    # Track as superseded (not failed) so failed_worker_count
                    # stays honest; include the partial answer in synthesis.
                    yield ToolResult(
                        tool_call_id=item.tool_call_id,
                        name=item.tool_name,
                        label=item.tool_label,
                        status="cancelled",
                        approval_state="rejected",
                        summary="Superseded by another worker's pending approval.",
                        error=(
                            "Concurrent worker pause cancelled; only one "
                            "HITL continuation is kept per fan-out."
                        ),
                        subagent_id=paused.subagent_id,
                    )
                    yield _abandoned_pause_done(item, "cancelled")
                    ledger.settle(
                        paused.subagent_id,
                        role="worker",
                        usage=paused.usage,
                        cost_usd=paused.cost_usd,
                        outcome="cancelled",
                    )
                    superseded_workers += 1
                    superseded_worker_ids.add(paused.subagent_id)
                    if paused.answer.strip():
                        results[paused.subagent_id] = _worker_output(paused)
                    _maybe_budget_kill()
                continue
            # B3 / AR-008 / SAF-005: the runner already observed this sample into
            # the ledger, priced on the route serving it, so the kill gate only
            # has to read the total back.
            if isinstance(item, (UsageUpdate, Complete)) and item.subagent_id:
                _maybe_budget_kill()
            yield item
            if isinstance(item, SubagentDone) and item.role == "worker":
                # Mid-run meter tick (estimate + mid + final; FE-011 / FE-012).
                # A display tick, so it carries no receipt (AC-02) and shows only
                # EXACTLY settled spend — never a provisional sibling sample. The
                # runner settled this phase before minting the terminal above.
                yield RunCost(
                    subtotal_usd=ledger.settled_cost_usd,
                    cap_usd=cap,
                    confidence="exact",
                    phase="progress",
                )
                _maybe_budget_kill()
        # Tolerate task cancellations from the budget kill. Worker failures are
        # degraded inside `_run_worker` and must not fail the whole run.
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in gathered:
            if isinstance(outcome, BaseException) and not isinstance(
                outcome, asyncio.CancelledError
            ):
                _log.error(
                    "agentic.unexpected_worker_task_error",
                    error=str(outcome),
                    exc_info=outcome,
                )
    finally:
        # BE-025: cancel AND join so workers cannot outlive the turn.
        # Note: on stop/disconnect the pump acloses this generator (GeneratorExit),
        # so SubagentDone(stopped) enqueued by cancelled workers here cannot be
        # yielded — the handler stop path marks unfinished accumulators stopped.
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # BE-005: after siblings finish, surface the worker tool pause with continuation.
    # AR-004: if the run already breached the cap while parking the pause, do NOT
    # expose an executable HITL card — cancel the pending call and synthesize.
    if worker_pause is not None and budget_halted:
        yield ToolResult(
            tool_call_id=worker_pause.tool_call_id,
            name=worker_pause.tool_name,
            label=worker_pause.tool_label,
            status="cancelled",
            approval_state="rejected",
            summary="Cancelled: run budget already exhausted.",
            error=(
                "The run reached its budget cap before this approval could be "
                "shown. Partial synthesis continues without the gated tool."
            ),
            subagent_id=worker_pause.result.subagent_id,
        )
        # FL-10: attribute the pause unconditionally. Hanging the ledger write
        # off the partial-answer guard silently dropped a blank-partial pause's
        # tokens from the run total.
        ledger.settle(
            worker_pause.result.subagent_id,
            role="worker",
            usage=worker_pause.result.usage,
            cost_usd=worker_pause.result.cost_usd,
            outcome="budget_cancelled",
        )
        # FL-10: this worker is never resumed, so it needs its own terminal — the
        # handler only repairs unfinished rows on stop / pause, and this turn ends
        # `done`, leaving the row on the `succeeded` default.
        yield _abandoned_pause_done(worker_pause, "budget_cancelled")
        if worker_pause.result.answer.strip():
            results[worker_pause.result.subagent_id] = _worker_output(
                worker_pause.result
            )
        worker_pause = None

    if worker_pause is not None:
        completed_states: list[CompletedWorkerState] = []
        for _index, sid, _label, sq in worker_meta:
            if sid not in results:
                continue
            out = results[sid]
            completed_states.append(
                CompletedWorkerState(
                    subagent_id=sid,
                    sub_question=sq,
                    answer=out.answer,
                    usage=_restored_usage(ledger.usage_of(sid)),
                    cost_usd=ledger.cost_of(sid),
                    outcome=(
                        "cancelled" if sid in superseded_worker_ids else "succeeded"
                    ),
                    source_ids=out.source_ids,
                )
            )
        paused = worker_pause.result
        cont = AgenticContinuation(
            phase="worker",
            paused_subagent_id=paused.subagent_id,
            user_text=effective_user_text,
            plan=tuple(sub_questions),
            completed_workers=tuple(completed_states),
            planner_usage=(
                seeded_planner_usage
                if plan_approved is True and has_nonzero_usage(seeded_planner_usage)
                else planner_usage
            ),
            planner_cost_usd=planner_cost,
            budget_halted=budget_halted,
            failed_workers=failed_workers,
            actual_cost_usd=actual_cost,
            paused_worker_index=paused.index,
            paused_sub_question=paused.sub_question,
            partial_answer=paused.answer,
            partial_reasoning=paused.reasoning,
            source_ids=paused.source_ids,
            source_catalog=tuple(source_namespace.merged_items()),
            source_allocations=source_namespace.allocations(),
            source_next_id=source_namespace.next_id,
            tool_transcript=paused.tool_transcript,
            emitted_answer_chars=paused.emitted_answer_chars,
            clarifications=tuple(bound_records),
            orchestration_mode="deep_research",
            paused_worker_usage=paused.usage,
            paused_worker_cost_usd=paused.cost_usd,
            paused_worker_used_fallback=paused.used_fallback,
        )
        # AC-02: a worker approval pause is an orchestrator-owned persistable
        # boundary, so exactly one receipt-bearing `RunCost` precedes it. The
        # handler `break`s at the pause terminal, so it has to come first.
        yield _boundary_run_cost(
            ledger,
            cap_usd=cap,
            boundary="pause",
            partial=True,
            budget_halted=budget_halted,
            failed_worker_count=failed_workers,
        )
        yield AwaitingApproval(
            tool_call_id=worker_pause.tool_call_id,
            subagent_id=paused.subagent_id,
            continuation=serialize_continuation(cont),
        )
        return

    ordered_outputs = [results[sid] for _, sid, _, _ in worker_meta if sid in results]
    # Mid-stream remapper already assigned global citation ids (B12) — do not
    # remap again in worker-plan order (that swapped ownership vs live markers).
    merged_sources = source_namespace.merged_items()
    # In-turn structured artifact refs (plan 02) — handed to the aggregator as
    # schema-shaped DATA rather than raw telephone stuffing.
    ordered_artifacts = aggregate.build_artifacts(
        ordered_outputs, max_artifacts=settings.agentic_max_workers
    )
    # Fold planner into run totals. On a plan-approved resume live `planner_usage`
    # is empty and the pause-turn tokens come back off the ledger's planner phase
    # (from the receipt, or from the B4 seed for a legacy row).
    ordered_usages = [
        _restored_usage(ledger.usage_of(sid))
        for _, sid, _, _ in worker_meta
        if ledger.phase(sid) is not None
    ]
    ordered_usages.append(_restored_usage(ledger.usage_of(_PLANNER_ID)))
    worker_total_cost = ledger.cumulative_cost_usd

    # BE-014 residual: before starting the aggregator, refuse a model synthesis
    # call when the ledger already exceeds the cap or the aggregator phase
    # estimate cannot fit. Degrade to deterministic (zero-token) synthesis.
    # Verifier funding is a SEPARATE gate after the aggregator draft exists —
    # do not fold N judge slots into this check.
    expected_agg = budget.expected_subagent_usage(settings)
    aggregator_estimate = (
        cost_for_usage(expected_agg)
        * settings.agentic_reasoning_token_multiplier
    )
    cannot_fund_aggregator = budget.exceeds_cap(
        actual_usd=worker_total_cost + aggregator_estimate,
        cap_usd=cap,
        headroom_usd=budget_headroom_usd,
    ) or budget.exceeds_cap(
        actual_usd=worker_total_cost,
        cap_usd=cap,
        headroom_usd=budget_headroom_usd,
    )
    if cannot_fund_aggregator:
        budget_halted = True

    judge_factory = verifier_make_stream_for or make_stream_for

    if scaffolded or not ordered_outputs or cannot_fund_aggregator:
        # Deterministic synthesis: the fake-provider / test contract, the
        # safety fallback when no worker produced output, and the
        # budget-degrade path when the aggregator model call cannot fit.
        # Verifier runs as a sibling under the workflow — never nested inside
        # the aggregator OTel span (V-009).
        draft = aggregate.synthesize(
            ordered_outputs,
            planned=len(sub_questions),
            budget_halted=budget_halted,
            failed=failed_workers,
            clarifications=answers,
        )
        # FL-09: `aggregate.synthesize` (F3) owns only the budget-halt and
        # failed-worker clauses, so the superseded clause is appended here.
        draft += _superseded_label(superseded_workers)
        verifier_result: verifier.VerifyResult | None = None
        verifier_outcome: Literal["succeeded", "failed"] = "succeeded"
        synthesis = draft
        # Open aggregator first so the UI sees synthesis ownership, then run the
        # verifier as a sibling (Started before await; Done before final answer).
        yield SubagentStarted(
            subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
        )
        if merged_sources:
            yield Sources(items=list(merged_sources), subagent_id=_AGGREGATOR_ID)
        if settings.agentic_verifier and verifier.can_fund(
            ledger_usd=worker_total_cost,
            settings=settings,
            cost_for_usage=verifier_pricer,
            cap_usd=cap,
            budget_headroom_usd=budget_headroom_usd,
            sample_count=1,
        ):
            yield SubagentStarted(
                subagent_id=_VERIFIER_ID,
                label=_VERIFIER_LABEL,
                role="verifier",
            )
            try:
                verifier_result = await verifier.run_if_enabled(
                    settings=settings,
                    draft=draft,
                    make_stream_for=judge_factory,
                    user_text=effective_user_text,
                    outputs=ordered_outputs,
                    scaffolded=scaffolded,
                    cost_for_usage=verifier_pricer,
                    ledger_usd=worker_total_cost,
                    cap_usd=cap,
                    budget_headroom_usd=budget_headroom_usd,
                    served_route=served_route,
                )
            except Exception:
                _log.exception("agentic.verifier_failed")
                verifier_outcome = "failed"
                verifier_result = None
                # Sibling of FL-19-b on the deterministic-synthesis path: a judge
                # crash must be disclosed rather than shipping a bare draft that
                # reads as verified.
                synthesis = verifier.compose_verified_answer(
                    draft, verdict="pass", report="", incomplete_samples=True
                )
            else:
                synthesis, verifier_outcome, v_budget_halted = (
                    verifier.apply_result(draft, verifier_result)
                )
                if v_budget_halted:
                    budget_halted = True
            if verifier_result is None and verifier_outcome == "succeeded":
                verifier_outcome = "failed"
            async for event in verifier.receipt_events(
                result=verifier_result,
                cost_for_usage=verifier_pricer,
                ledger_usd=worker_total_cost,
                cap_usd=cap,
                outcome=verifier_outcome,
                emit_started=False,
            ):
                yield event
        elif settings.agentic_verifier:
            # FL-18: the verifier is on but unfundable. Skipping silently shipped
            # an unverified answer that read as verified; caveat it and flag the
            # receipt so the copy matches `budget_halted` on the wire.
            synthesis = verifier.compose_verified_answer(
                draft, verdict="pass", report="", budget_halted=True
            )
            budget_halted = True
        with invoke_agent_span(
            subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
        ) as agg_span:
            # A deterministic synthesis makes no provider call, so this phase is
            # genuinely zero-token and every fact the span reports is known before
            # anything is emitted. Settling first also shrinks the window in which
            # a consumer close could end the span unsettled to nothing.
            aggregator_usage = UsageUpdate()
            aggregator_cost = cost_for_usage(aggregator_usage)
            agg_span.settle(
                route=served_route,
                usage=UsageTotals.copy_from(aggregator_usage),
                cost_usd=aggregator_cost,
                outcome="succeeded",
            )
            yield AnswerDelta(text=synthesis, subagent_id=_AGGREGATOR_ID)
            yield Complete(usage=aggregator_usage, subagent_id=_AGGREGATOR_ID)
            yield SubagentDone(
                subagent_id=_AGGREGATOR_ID,
                label=_AGGREGATOR_LABEL,
                role="aggregator",
                usage=aggregator_usage,
                cost_usd=aggregator_cost,
                outcome="succeeded",
            )
        v_usage = (
            verifier_result.usage if verifier_result is not None else UsageUpdate()
        )
        verifier_cost = verifier.result_cost_usd(verifier_result, verifier_pricer)
        verifier_budget_halted = (
            verifier_result.budget_halted if verifier_result is not None else False
        )
        total_usage = sum_usages([*ordered_usages, aggregator_usage, v_usage])
        ledger.settle(
            _AGGREGATOR_ID,
            role="aggregator",
            usage=aggregator_usage,
            cost_usd=aggregator_cost,
        )
        if verifier_result is not None or verifier_outcome == "failed":
            ledger.settle(
                _VERIFIER_ID,
                role="verifier",
                usage=v_usage,
                cost_usd=verifier_cost,
                outcome=verifier_outcome,
            )
        yield Complete(usage=total_usage)
        effective_budget_halted = budget_halted or verifier_budget_halted
        yield _boundary_run_cost(
            ledger,
            cap_usd=cap,
            partial=(
                effective_budget_halted
                or failed_workers > 0
                # FL-09 / FL-08: a cancelled sibling or a degraded verification is
                # a partial answer even with no failures and no cap breach.
                or superseded_workers > 0
                or verifier.verification_degraded(verifier_result, verifier_outcome)
            ),
            budget_halted=effective_budget_halted,
            failed_worker_count=failed_workers,
        )
    else:
        # Real provider: stream a model-written synthesis from structured
        # worker artifact refs (untrusted DATA envelope). Aggregator span lives
        # inside `_finalize_synthesis_streamed` around quiet-collect only.
        # Clarifications ride once as structured envelope fields — not as a
        # text footer inside original_request (O-014 double-encode fix).
        synth_clarify = clarify.clarification_payload_for_phase(
            bound_records, phase="synthesis"
        ) or None
        async for event in _finalize_synthesis_streamed(
            make_stream_for=make_stream_for,
            verifier_make_stream_for=judge_factory,
            settings=settings,
            user_text=plan_text,
            outputs=ordered_outputs,
            planned=len(sub_questions),
            worker_usages=ordered_usages,
            worker_total_cost=worker_total_cost,
            cost_for_usage=cost_for_usage,
            verifier_cost_for_usage=verifier_pricer,
            cap_usd=cap,
            budget_halted=budget_halted,
            failed=failed_workers,
            superseded=superseded_workers,
            budget_headroom_usd=budget_headroom_usd,
            scaffolded=scaffolded,
            artifacts=ordered_artifacts,
            clarifications=synth_clarify,
            merged_sources=merged_sources or None,
            ledger=ledger,
            served_route=served_route,
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
    served_route: ServedRoute | None = None,
    estimate_cost: CostEstimator | None = None,
    budget_headroom_usd: float | None = None,
    plan_approved: bool | None = None,
    approved_plan: list[str] | None = None,
    clarify_answered: bool | None = None,
    clarify_answers: list[str] | None = None,
    clarify_records: list[clarify.ClarificationRecord] | None = None,
    agentic_continuation: AgenticContinuation | None = None,
    resume_tool_result: ToolResult | None = None,
    server_approved_call_ids: set[str] | None = None,
    fallback_make_stream_for: StreamFactory | None = None,
    fallback_cost_for_usage: CostForUsage | None = None,
    fallback_provider_id: str | None = None,
    fallback_model_id: str | None = None,
    fallback_display_label: str | None = None,
    is_retryable: IsRetryable = is_retryable_provider_error,
    verifier_make_stream_for: StreamFactory | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
    prior_planner_cost_usd: float = 0.0,
    prior_planner_usage: UsageUpdate | None = None,
    prior_run_cost_usd: float = 0.0,
    prior_run_usage: UsageUpdate | None = None,
    prior_receipt: RunReceipt | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Drive an agentic turn, yielding the handler's `ProviderEvent` union.

    `make_stream_for(user_text)` builds the per-subagent provider stream the agent
    loop drives; `cost_for_usage` prices an accumulated usage for the active
    binding. The handler routes here ONLY when agentic mode is active, so the
    flag-off path never constructs this generator.

    M3 params (all optional):
    - `estimate_cost` — prices the worst-case run for pre-spawn admission
      (deep_research).
    - `budget_headroom_usd` — the caller's remaining user/platform (and
      per-conversation) budget, composed with the per-run cap for both
      `single` and `deep_research`.
    - `plan_approved` — the plan-approval HITL decision carried across a resume
      (None = fresh run, True = approved, False = declined).
    - `approved_plan` — immutable sub-questions from the paused tool input when
      `plan_approved` is True (BE-039); ignored otherwise.
    - `clarify_answered` / `clarify_records` / `clarify_answers` — clarify-before-plan
      HITL resume (None = fresh; True + records = proceed to plan with bound Q&A;
      False = decline). ``clarify_records`` carries question text; ``clarify_answers``
      is a legacy answer-only fallback.
    - `verifier_make_stream_for` — fresh-context factory for the verifier judge
      (empty history / no memory / no web_search). Falls back to
      ``make_stream_for`` when omitted (tests).
    - `verifier_cost_for_usage` — phase pricer for the judge (image_count=0);
      defaults to ``cost_for_usage``.
    - `fallback_make_stream_for` / `fallback_cost_for_usage` — per-worker
      fallback route + pricer when the primary binding fails retryably (FE-009).
    - `fallback_provider_id` / `fallback_model_id` / `fallback_display_label` —
      served-route identity stamped onto substituted workers (BE-023 / SAF-006).
    - `prior_planner_cost_usd` / `prior_planner_usage` — B4 plan-approval resume
      ledger seed (from reserved pause tool-input fields; do not re-bill).
    - `prior_run_cost_usd` / `prior_run_usage` — B5 single-mode HITL resume
      ledger seed (H-011: no primary continuation phase; handler must pass).
    - `prior_receipt` — AC-02 boundary receipt from the paused row's server-only
      state. When present it SUPERSEDES the scalar seeds above as the resumed
      run's already-billed floor: those seeds reconstruct one phase's spend,
      while the receipt is the exact total the pause turn actually charged.
    - `served_route` (AC-10) — the tier/provider/model the handler bound for this
      turn. Every phase span closes with it, or with the fallback route derived
      from it when a phase was substituted; omitted, the spans simply carry no
      route (direct unit calls).
    """
    if mode == "deep_research":
        async for event in _run_deep_research(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
            served_route=served_route,
            estimate_cost=estimate_cost,
            budget_headroom_usd=budget_headroom_usd,
            plan_approved=plan_approved,
            approved_plan=approved_plan,
            clarify_answered=clarify_answered,
            clarify_answers=clarify_answers,
            clarify_records=clarify_records,
            agentic_continuation=agentic_continuation,
            resume_tool_result=resume_tool_result,
            server_approved_call_ids=server_approved_call_ids,
            fallback_make_stream_for=fallback_make_stream_for,
            fallback_cost_for_usage=fallback_cost_for_usage,
            fallback_provider_id=fallback_provider_id,
            fallback_model_id=fallback_model_id,
            fallback_display_label=fallback_display_label,
            is_retryable=is_retryable,
            verifier_make_stream_for=verifier_make_stream_for,
            verifier_cost_for_usage=verifier_cost_for_usage,
            prior_planner_cost_usd=prior_planner_cost_usd,
            prior_planner_usage=prior_planner_usage,
            prior_receipt=prior_receipt,
        ):
            yield event
    else:
        async for event in run_single(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
            served_route=served_route,
            budget_headroom_usd=budget_headroom_usd,
            server_approved_call_ids=server_approved_call_ids,
            initial_tool_results=(
                [resume_tool_result] if resume_tool_result is not None else None
            ),
            prior_run_cost_usd=prior_run_cost_usd,
            prior_run_usage=prior_run_usage,
            prior_receipt=prior_receipt,
        ):
            yield event
