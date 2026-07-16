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

M3 hooks (`_admit`, `_maybe_plan_approval`, verifier via `_run_verifier_if_enabled`)
are live control-flow gates (admission / plan-approval pause / verifier), each
gated by its setting.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import structlog
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

from app.agentic import aggregate, budget, clarify, planner, verifier
from app.agentic.aggregate import WorkerOutput
from app.agentic.continuation import (
    AgenticContinuation,
    CompletedWorkerState,
    serialize_continuation,
)
from app.agentic.retry import is_retryable_provider_error
from app.config import Settings
from app.errors import AppError
from app.observability.tracing import invoke_agent_span
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    RunCost,
    Sources,
    StatusUpdate,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.schemas.common import SubstitutionReasonCode
from app.streaming.constants import EMPTY_REPLY_FALLBACK
from app.tools.agent_loop import MakeStream, run_agent_loop

_log = structlog.get_logger(__name__)

# Event types that carry an optional `subagent_id` and so can be stamped by
# `_tag`. Orchestrator-only `SubagentStarted` / `SubagentDone` / `RunCost` are
# deliberately absent — the agent loop never emits those.
_TAGGABLE = (
    ReasoningDelta,
    ReasoningDone,
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

# Build a per-subagent `MakeStream` for the given user prompt. Optional keyword
# ``allowed_tools`` scopes which registry tools are advertised (and should match
# the agent-loop execute allowlist). ``None`` = full turn set; empty = none.
StreamFactory = Callable[..., MakeStream]

# Computes the USD cost of an accumulated usage for the active binding.
CostForUsage = Callable[[UsageUpdate], float]

# Optional per-worker fallback stream factory and retry predicate (M4).
IsRetryable = Callable[[BaseException], bool]

_PRIMARY_LABEL = "Agent"
_AGGREGATOR_ID = "aggregator"
_AGGREGATOR_LABEL = "Synthesis"
_PLANNER_ID = "planner"
_PLANNER_LABEL = "Planner"
_VERIFIER_ID = verifier.VERIFIER_ID
_VERIFIER_LABEL = verifier.VERIFIER_LABEL

# Deep-research workers are flat (AGENTIC_MAX_DEPTH == 1 by construction): each
# worker runs one `run_agent_loop` and never re-enters the orchestrator.
# Provider-internal web_search remains available via the handler flag.
#
# Worker HITL allowlist (O-010):
# - ``request_user_confirmation`` — prod_safe gated tool real providers can be
#   offered (native advertisement ∩ allowlist is non-empty).
# - ``calendar_create_event`` — fake-only fixture for FakeProvider TOOL_APPROVE
#   markers (prod_safe=False ⇒ never advertised live). Kept in the execute
#   allowlist so scaffolded tests can still pause/resume.
_WORKER_PROD_HITL_TOOLS: frozenset[str] = frozenset({"request_user_confirmation"})
_WORKER_FAKE_HITL_TOOLS: frozenset[str] = frozenset({"calendar_create_event"})
_WORKER_ALLOWED_TOOLS: frozenset[str] = _WORKER_PROD_HITL_TOOLS | _WORKER_FAKE_HITL_TOOLS

# Aggregator: no registry tools and no provider-native web_search (O-006 / O-011 /
# H-011). Aggregator HITL continuation is not implemented — an empty allowlist
# makes gated pauses unreachable rather than advertising a dead resume path.
_AGGREGATOR_ALLOWED_TOOLS: frozenset[str] = frozenset()
# Back-compat alias for quiet-collect call sites.
_AGGREGATOR_QUIET_ALLOWED_TOOLS: frozenset[str] = _AGGREGATOR_ALLOWED_TOOLS

# Quiet planner: judgment/decomposition only — empty registry allowlist so a
# planner ToolCall/HITL pause cannot be swallowed into an empty plan (O-009).
_PLANNER_ALLOWED_TOOLS: frozenset[str] = frozenset()

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


_TOOL_CALL_NS_SEP = "::"


def namespace_tool_call_id(subagent_id: str, call_id: str) -> str:
    """Bind a provider-issued call id to a subagent (H-004).

    Independent provider sessions can reuse call ids; namespacing prevents
    cross-worker confused-deputy approve/replace.
    """
    if not subagent_id or not call_id:
        return call_id
    prefix = f"{subagent_id}{_TOOL_CALL_NS_SEP}"
    if call_id.startswith(prefix):
        return call_id
    # Already namespaced under another subagent — leave untouched.
    if _TOOL_CALL_NS_SEP in call_id:
        return call_id
    return f"{prefix}{call_id}"


@dataclass(frozen=True)
class _WorkerPause:
    """Internal: a worker paused for tool HITL (BE-005).

    Sibling policy: wait for other workers to finish, then surface
    ``AwaitingApproval`` with a continuation blob. NOT a ProviderEvent.
    Concurrent extra pauses are cancelled (H-003 / O-007) so they are not
    left pending without a continuation.
    """

    subagent_id: str
    index: int
    sub_question: str
    tool_call_id: str
    tool_name: str
    usage: UsageUpdate
    partial_answer: str
    tool_label: str | None = None
    # H-010: worker-local checkpoint (sources + tool transcript + reasoning).
    source_ids: tuple[str, ...] = ()
    tool_transcript: tuple[dict[str, Any], ...] = ()
    partial_reasoning: str = ""
    emitted_answer_chars: int = 0


def _tag(event: ProviderEvent, subagent_id: str) -> ProviderEvent:
    """Stamp `subagent_id` onto a subagent's event.

    ToolCall / ToolResult / AwaitingApproval ids are namespaced per subagent
    (H-004) so colliding provider-issued ids cannot cross workers.
    """
    if isinstance(event, ToolCall):
        return replace(
            event,
            subagent_id=subagent_id,
            id=namespace_tool_call_id(subagent_id, event.id),
        )
    if isinstance(event, ToolResult):
        return replace(
            event,
            subagent_id=subagent_id,
            tool_call_id=namespace_tool_call_id(subagent_id, event.tool_call_id),
        )
    if isinstance(event, AwaitingApproval):
        return replace(
            event,
            subagent_id=subagent_id,
            tool_call_id=namespace_tool_call_id(subagent_id, event.tool_call_id),
        )
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


async def _emit_planner_receipt(
    *,
    planner_usage: UsageUpdate,
    cost_for_usage: CostForUsage,
    cap_usd: float,
    ledger_usd: float,
    open_bracket: bool = False,
) -> AsyncIterator[ProviderEvent]:
    """Surface planner spend as a planner SubagentDone + mid-run RunCost tick.

    Used on pause / decline / admit-reject / post-plan so planner tokens are
    never discarded from the run ledger (BE-015 / BE-014). ``ledger_usd`` is the
    run subtotal *including* ``planner_usage``.

    ``open_bracket`` forces a ``SubagentStarted`` even when usage is empty (plan-
    approval pause needs the planner section for the HITL tool). Otherwise the
    bracket opens only when there is real planner usage (fake/scaffolded path
    stays quiet).
    """
    planner_cost = cost_for_usage(planner_usage)
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


async def _maybe_clarify_before_plan(
    settings: Settings,
    *,
    user_text: str,
    scaffolded: bool,
    call_id: str | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Clarify-before-plan HITL gate — async generator of pause events.

    When `AGENTIC_CLARIFY_BEFORE_PLAN` is on and the ambiguity / marker check
    fires, surfaces 1-3 clarifying questions on a planner pseudo-tool and
    PAUSES with `awaiting_approval` BEFORE planning / admission / fan-out.
    Yields nothing when the flag is off or clarify is not needed.
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
    )
    plan_call_id = call_id or mint_plan_approval_call_id()
    plan_list = list(sub_questions)
    plan_input: dict[str, object] = {
        "plan": plan_list,
        "planHash": hash_plan(plan_list),
        "estimatedCostUsd": estimate_usd,
        "capUsd": cap_usd,
    }
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


def _verifier_phase_estimate(
    *,
    settings: Settings,
    cost_for_usage: CostForUsage,
    sample_count: int | None = None,
) -> float:
    """USD estimate for ``sample_count`` judge samples (default: configured N).

    Matches admission methodology: reasoning x fan-out multipliers (FR-26g).
    """
    if not settings.agentic_verifier:
        return 0.0
    n = max(1, sample_count if sample_count is not None else settings.agentic_verifier_n)
    expected = budget._expected_subagent_usage(settings)
    return (
        cost_for_usage(expected)
        * settings.agentic_reasoning_token_multiplier
        * settings.agentic_fanout_token_multiplier
        * n
    )


def _can_fund_verifier(
    *,
    ledger_usd: float,
    settings: Settings,
    cost_for_usage: CostForUsage,
    cap_usd: float,
    budget_headroom_usd: float | None,
    sample_count: int | None = None,
) -> bool:
    """True when ledger + estimated judge sample(s) still fit the effective cap."""
    if not settings.agentic_verifier:
        return False
    estimate = _verifier_phase_estimate(
        settings=settings,
        cost_for_usage=cost_for_usage,
        sample_count=sample_count,
    )
    return not budget.exceeds_cap(
        actual_usd=ledger_usd + estimate,
        cap_usd=cap_usd,
        headroom_usd=budget_headroom_usd,
    )


async def _run_verifier_if_enabled(
    *,
    settings: Settings,
    draft: str,
    make_stream_for: StreamFactory,
    user_text: str,
    outputs: list[WorkerOutput],
    scaffolded: bool,
    cost_for_usage: CostForUsage | None = None,
    ledger_usd: float = 0.0,
    cap_usd: float = 0.0,
    budget_headroom_usd: float | None = None,
) -> verifier.VerifyResult | None:
    """Fresh-context judge when `AGENTIC_VERIFIER` is on and budget allows.

    Returns ``None`` when the flag is off or the first judge sample cannot fit
    the remaining run cap (skip / degrade without a Verification claim).

    Post-sample actual-cost is enforced inside ``run_verifier`` via
    ``actual_within_cap`` so an over-estimate overrun cannot finish as a
    successful verified pass while erasing the budget-halted signal.
    """
    if not settings.agentic_verifier:
        return None
    if cost_for_usage is not None and not _can_fund_verifier(
        ledger_usd=ledger_usd,
        settings=settings,
        cost_for_usage=cost_for_usage,
        cap_usd=cap_usd,
        budget_headroom_usd=budget_headroom_usd,
        sample_count=1,
    ):
        return None

    pricer = cost_for_usage

    def _can_afford_next(_usage_so_far: UsageUpdate, spent_usd: float) -> bool:
        # Prefer authoritative per-sample sum — never reprice collapsed usage.
        assert pricer is not None
        return _can_fund_verifier(
            ledger_usd=ledger_usd + spent_usd,
            settings=settings,
            cost_for_usage=pricer,
            cap_usd=cap_usd,
            budget_headroom_usd=budget_headroom_usd,
            sample_count=1,
        )

    def _actual_within_cap(_usage_so_far: UsageUpdate, spent_usd: float) -> bool:
        return not budget.exceeds_cap(
            actual_usd=ledger_usd + spent_usd,
            cap_usd=cap_usd,
            headroom_usd=budget_headroom_usd,
        )

    return await verifier.run_verifier(
        make_stream_for=make_stream_for,
        settings=settings,
        user_text=user_text,
        draft=draft,
        outputs=outputs,
        scaffolded=scaffolded,
        can_afford_next_sample=_can_afford_next if pricer is not None else None,
        actual_within_cap=_actual_within_cap if pricer is not None else None,
        cost_for_usage=pricer,
    )


def _verifier_cost(
    result: verifier.VerifyResult | None,
    cost_for_usage: CostForUsage,
) -> float:
    """Prefer stored per-sample sum; fall back to pricing sample_usages or usage."""
    if result is None:
        return 0.0
    if result.sample_usages:
        # cost_usd is the authoritative sum of per-request prices.
        return result.cost_usd
    return cost_for_usage(result.usage)


async def _emit_verifier_receipt(
    *,
    result: verifier.VerifyResult | None,
    cost_for_usage: CostForUsage,
    ledger_usd: float,
    cap_usd: float,
    outcome: Literal["succeeded", "failed"] = "succeeded",
    emit_started: bool = True,
) -> AsyncIterator[ProviderEvent]:
    """Emit verifier SubagentStarted/Done + mid-run RunCost for attribution.

    Always bills observed usage when present — including failed / partial /
    budget-halted outcomes so already-consumed judge tokens are never erased.
    Uses per-sample cost from ``VerifyResult.cost_usd`` when sample usages were
    recorded (V-011).

    When ``emit_started`` is False, the caller already yielded ``SubagentStarted``
    before awaiting the judge (V-009 lifecycle order).
    """
    if result is None and outcome == "succeeded":
        return
    usage = result.usage if result is not None else UsageUpdate()
    cost = _verifier_cost(result, cost_for_usage)
    wire_outcome: Literal["succeeded", "failed"] = (
        "succeeded" if outcome == "succeeded" and result is not None
        and result.outcome == "succeeded"
        else "failed"
        if outcome == "failed"
        or (result is not None and result.outcome in {"failed", "unavailable"})
        else "succeeded"
    )
    # Partial / budget_halted still surface as succeeded bracket with usage —
    # the final RunCost carries partial/budget_halted. Only hard failures use
    # failed.
    if (
        result is not None
        and result.outcome in {"partial", "budget_halted"}
        and outcome != "failed"
    ):
        wire_outcome = "succeeded"
    if emit_started:
        yield SubagentStarted(
            subagent_id=_VERIFIER_ID, label=_VERIFIER_LABEL, role="verifier"
        )
    yield Complete(usage=usage, subagent_id=_VERIFIER_ID)
    yield SubagentDone(
        subagent_id=_VERIFIER_ID,
        label=_VERIFIER_LABEL,
        role="verifier",
        usage=usage,
        cost_usd=cost,
        outcome=wire_outcome,
    )
    yield RunCost(
        subtotal_usd=ledger_usd + cost,
        cap_usd=cap_usd,
        confidence="exact",
        phase="progress",
    )


def _apply_verifier_result(
    draft: str,
    result: verifier.VerifyResult | None,
) -> tuple[str, Literal["succeeded", "failed"], bool]:
    """Map a VerifyResult onto (final_answer, wire_outcome, budget_halted).

    Only a full successful verification may rewrite the draft with a pass/fail
    note. Failed / unavailable / partial results preserve the draft body (the
    result.answer already carries an honest caveat when applicable) and keep
    billable usage on the result object for the receipt.
    """
    if result is None:
        return draft, "succeeded", False
    budget_halted = result.budget_halted
    if result.outcome == "succeeded":
        return result.answer, "succeeded", budget_halted
    if result.outcome in {"partial", "budget_halted", "unavailable"}:
        # answer already has incomplete/unavailable caveat when samples existed
        return result.answer if result.answer else draft, "succeeded", budget_halted
    # failed — keep caveat answer if present, else draft; wire as failed
    return (result.answer if result.answer else draft), "failed", budget_halted


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
    planned_workers: int = 0,
    completed_workers: int = 0,
    verifier_result: verifier.VerifyResult | None = None,
    verifier_outcome: Literal["succeeded", "failed"] = "succeeded",
    emit_verifier_bracket: bool = False,
) -> AsyncIterator[ProviderEvent]:
    """Emit the `aggregator` subagent + optional verifier receipt + run totals.

    Shared by the normal fan-out tail AND the early-exit paths (over-budget,
    plan-declined) so they all persist a clean `done` turn with the same shape:
    aggregator subagent → (verifier) → run-total `Complete` → `run_cost`.
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
        outcome="succeeded",
    )
    verifier_cost = 0.0
    v_usage = UsageUpdate()
    verifier_budget_halted = False
    if emit_verifier_bracket:
        async for event in _emit_verifier_receipt(
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
        verifier_cost = _verifier_cost(verifier_result, cost_for_usage)
        verifier_budget_halted = verifier_result.budget_halted
    total_usage = _sum_usages([*worker_usages, aggregator_usage, v_usage])
    total_cost = worker_total_cost + aggregator_cost + verifier_cost
    # Final untagged `Complete`: the handler's "last Complete wins" fold makes
    # this the turn's terminal usage, so the terminal attribution cost is the SUM
    # of every subagent's cost.
    yield Complete(usage=total_usage)
    effective_budget_halted = budget_halted or verifier_budget_halted
    partial = effective_budget_halted or failed_worker_count > 0
    yield RunCost(
        subtotal_usd=total_cost,
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
    budget_headroom_usd: float | None = None,
    scaffolded: bool = False,
    artifacts: list[aggregate.WorkerArtifact] | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
    clarifications: list[dict[str, str]] | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Stream a MODEL-WRITTEN synthesis as the `aggregator` subagent (real providers).

    When ``AGENTIC_VERIFIER`` is off, relays aggregator AnswerDeltas live.
    When on, collects the aggregator draft quietly under the aggregator span,
    then opens the verifier as a **sibling** subagent (Started → await judge →
    Done) before emitting the manager's final answer — so N-sample latency is
    visible and the verifier span is not a child of the aggregator (V-009).

    Mid-aggregator (BE-014): if accumulated aggregator spend pushes the run over
    the cap, stop the stream early and label the partial.
    """
    yield SubagentStarted(
        subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
    )
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
    # Aggregator OTel span covers only aggregator work — never the verifier.
    with invoke_agent_span(
        subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
    ):
        async for event in run_agent_loop(
            make_stream=agg_make,
            settings=settings,
            allowed_tools=agg_allowed,
        ):
            if verify_after and isinstance(event, AwaitingApproval):
                # Typed failure: no aggregator continuation to attach (O-011).
                yield _tag(event, _AGGREGATOR_ID)
                return
            if verify_after and isinstance(
                event, (ToolCall, ToolResult, Sources, StatusUpdate)
            ):
                yield _tag(event, _AGGREGATOR_ID)
                quiet_provenance = True
                aggregator_usage = _fold_usage(event, aggregator_usage)
                continue
            if isinstance(event, AnswerDelta):
                answer_parts.append(event.text)
                if not verify_after:
                    yield _tag(event, _AGGREGATOR_ID)
            elif isinstance(event, AwaitingApproval):
                # Non-verify path: also impossible under empty allowlist; treat as
                # terminal failure rather than a resumable pause without state.
                yield _tag(event, _AGGREGATOR_ID)
                return
            elif not verify_after:
                yield _tag(event, _AGGREGATOR_ID)
            aggregator_usage = _fold_usage(event, aggregator_usage)
            if not agg_budget_halted and budget.exceeds_cap(
                actual_usd=worker_total_cost + cost_for_usage(aggregator_usage),
                cap_usd=cap_usd,
                headroom_usd=budget_headroom_usd,
            ):
                agg_budget_halted = True
                break
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
    if not streamed.strip():
        draft = aggregate.synthesize(
            outputs, planned=planned, budget_halted=budget_halted, failed=failed
        )
    elif suffix:
        draft = streamed + suffix

    verifier_result: verifier.VerifyResult | None = None
    verifier_outcome: Literal["succeeded", "failed"] = "succeeded"
    final_answer = draft
    verifier_budget_halted = False
    verifier_started = False
    # Skip verify when quiet-collect saw tool/search provenance — the draft may
    # incorporate hidden work; surface events already yielded above.
    if verify_after and not quiet_provenance:
        aggregator_cost_so_far = cost_for_usage(aggregator_usage)
        # Funding gate before opening the verifier bracket so we never emit a
        # Started with no matching Done on a budget skip.
        will_run = _can_fund_verifier(
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
                verifier_result = await _run_verifier_if_enabled(
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
                )
            except Exception:
                _log.exception("agentic.verifier_failed")
                verifier_outcome = "failed"
                verifier_result = None
                final_answer = draft
            else:
                final_answer, verifier_outcome, verifier_budget_halted = (
                    _apply_verifier_result(draft, verifier_result)
                )
            if verifier_result is None and verifier_outcome == "succeeded":
                verifier_outcome = "failed"
            # Receipt (Complete/Done) before finalizing the manager answer (V-009).
            async for event in _emit_verifier_receipt(
                result=verifier_result,
                cost_for_usage=verifier_pricer,
                ledger_usd=worker_total_cost + aggregator_cost_so_far,
                cap_usd=cap_usd,
                outcome=verifier_outcome,
                emit_started=False,
            ):
                yield event
        yield AnswerDelta(text=final_answer, subagent_id=_AGGREGATOR_ID)
    elif (verify_after and quiet_provenance) or not streamed.strip():
        yield AnswerDelta(text=draft, subagent_id=_AGGREGATOR_ID)
    elif suffix:
        yield AnswerDelta(text=suffix, subagent_id=_AGGREGATOR_ID)

    aggregator_cost = cost_for_usage(aggregator_usage)
    yield Complete(usage=aggregator_usage, subagent_id=_AGGREGATOR_ID)
    yield SubagentDone(
        subagent_id=_AGGREGATOR_ID,
        label=_AGGREGATOR_LABEL,
        role="aggregator",
        usage=aggregator_usage,
        cost_usd=aggregator_cost,
        outcome="budget_cancelled" if agg_budget_halted else "succeeded",
    )
    verifier_cost = 0.0
    v_usage = UsageUpdate()
    if verifier_started and verifier_result is not None:
        v_usage = verifier_result.usage
        verifier_cost = _verifier_cost(verifier_result, verifier_pricer)
    elif verifier_started and verifier_outcome == "failed":
        pass  # zero cost already; bracket closed above
    total_usage = _sum_usages([*worker_usages, aggregator_usage, v_usage])
    total_cost = worker_total_cost + aggregator_cost + verifier_cost
    yield Complete(usage=total_usage)
    effective_budget_halted = budget_halted or verifier_budget_halted
    partial = effective_budget_halted or failed > 0
    yield RunCost(
        subtotal_usd=total_cost,
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
    """
    answer_parts: list[str] = []
    usage = UsageUpdate()
    with invoke_agent_span(
        subagent_id=_PLANNER_ID, role="orchestrator", label=_PLANNER_LABEL
    ):
        async for event in run_agent_loop(
            make_stream=make_stream_for(
                prompt,
                allowed_tools=_PLANNER_ALLOWED_TOOLS,
                web_search=False,
            ),
            settings=settings,
            allowed_tools=_PLANNER_ALLOWED_TOOLS,
        ):
            if isinstance(
                event, (AwaitingApproval, ToolCall, ToolResult, Sources, StatusUpdate)
            ):
                raise RuntimeError(
                    f"planner quiet-collect saw unexpected {type(event).__name__}"
                )
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
    budget_headroom_usd: float | None = None,
    server_approved_call_ids: set[str] | None = None,
    initial_tool_results: list[ToolResult] | None = None,
) -> AsyncIterator[ProviderEvent]:
    """One agent loop wrapped as the `primary` subagent.

    Enforces the same per-run cap as deep research (BE-020): pre-admit against a
    one-primary worst-case estimate, and mid-flight check against the effective
    cap composed with headroom.
    """
    subagent_id = "primary"
    cap = settings.agentic_run_budget_usd
    expected = budget._expected_subagent_usage(settings)
    estimate = (
        cost_for_usage(expected)
        * settings.agentic_reasoning_token_multiplier
        * settings.agentic_fanout_token_multiplier
    )
    decision = _admit(
        estimate_usd=estimate, settings=settings, budget_headroom_usd=budget_headroom_usd
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
        yield RunCost(
            subtotal_usd=0.0,
            cap_usd=cap,
            confidence="exact",
            phase="final",
            partial=True,
            budget_halted=True,
        )
        return

    yield SubagentStarted(subagent_id=subagent_id, label=_PRIMARY_LABEL, role="primary")
    yield RunCost(
        subtotal_usd=0.0,
        cap_usd=cap,
        confidence="estimate",
        phase="plan",
    )
    usage = UsageUpdate()
    answer_parts: list[str] = []
    budget_halted = False
    with invoke_agent_span(subagent_id=subagent_id, role="primary", label=_PRIMARY_LABEL):
        async for event in run_agent_loop(
            make_stream=make_stream_for(user_text),
            settings=settings,
            server_approved_call_ids=server_approved_call_ids,
            initial_tool_results=initial_tool_results,
        ):
            if isinstance(event, AnswerDelta):
                answer_parts.append(event.text)
            usage = _fold_usage(event, usage)
            if not budget_halted and budget.exceeds_cap(
                actual_usd=cost_for_usage(usage),
                cap_usd=cap,
                headroom_usd=budget_headroom_usd,
            ):
                budget_halted = True
            yield _tag(event, subagent_id)
            if isinstance(event, AwaitingApproval):
                # Primary tool HITL: end the subagent here; handler parks the turn.
                return
            if budget_halted and isinstance(event, (Complete, UsageUpdate)):
                break
    if not "".join(answer_parts).strip():
        yield AnswerDelta(text=EMPTY_REPLY_FALLBACK, subagent_id=subagent_id)
    elif budget_halted:
        yield AnswerDelta(
            text=(
                "\n\n[Partial answer: stopped early to stay within the run budget.]"
            ),
            subagent_id=subagent_id,
        )
    cost = cost_for_usage(usage)
    yield SubagentDone(
        subagent_id=subagent_id,
        label=_PRIMARY_LABEL,
        role="primary",
        usage=usage,
        cost_usd=cost,
        outcome="budget_cancelled" if budget_halted else "succeeded",
    )
    yield RunCost(
        subtotal_usd=cost,
        cap_usd=cap,
        confidence="exact",
        phase="final",
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
    budget_headroom_usd: float | None = None,
    fallback_make_stream_for: StreamFactory | None = None,
    fallback_cost_for_usage: CostForUsage | None = None,
    fallback_provider_id: str | None = None,
    fallback_model_id: str | None = None,
    fallback_display_label: str | None = None,
    is_retryable: IsRetryable = is_retryable_provider_error,
    verifier_make_stream_for: StreamFactory | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Continue a paused worker then synthesize (BE-005).

    Restores completed sibling results from the continuation blob, re-runs only
    the paused worker with validated tool feedback / server-approved call ids,
    then runs the normal aggregator path.

    H-009 / O-002: restores the pre-pause ledger and refuses further provider
    spend when already budget-halted or over cap. O-008: uses the same fallback
    path as fresh workers on retryable primary failure.
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
            answer=w.answer,
            source_ids=w.source_ids,
        )
        for w in continuation.completed_workers
    }
    usages: dict[str, UsageUpdate] = {
        w.subagent_id: w.usage for w in continuation.completed_workers
    }
    costs: dict[str, float] = {
        w.subagent_id: w.cost_usd for w in continuation.completed_workers
    }
    failed_workers = continuation.failed_workers
    budget_halted = continuation.budget_halted
    planner_usage = continuation.planner_usage
    # Prefer durable planner cost from the checkpoint (H-009).
    planner_cost = continuation.planner_cost_usd
    ledger_usd = float(continuation.actual_cost_usd or 0.0)
    if ledger_usd <= 0.0:
        ledger_usd = (
            sum(costs.values())
            + planner_cost
            + float(continuation.paused_worker_cost_usd or 0.0)
        )

    worker_meta = [
        (i, f"worker-{i}", f"Worker {i + 1}", sq)
        for i, sq in enumerate(sub_questions)
    ]
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
        ordered_usages = [usages[sid] for _, sid, _, _ in worker_meta if sid in usages]
        ordered_usages.append(planner_usage)
        worker_total_cost = max(
            sum(costs.get(sid, 0.0) for _, sid, _, _ in worker_meta) + planner_cost,
            ledger_usd,
        )
        completed_count = len(ordered_outputs)
        synthesis = aggregate.synthesize(
            ordered_outputs,
            planned=len(sub_questions),
            budget_halted=halted,
            failed=failed_workers,
            clarifications=resume_clarification_answers,
        )
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
                budget_headroom_usd=budget_headroom_usd,
                scaffolded=scaffolded,
                artifacts=ordered_artifacts,
                clarifications=synth_clarify,
            ):
                yield event
            return
        with invoke_agent_span(
            subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
        ):
            async for event in _finalize_synthesis(
                synthesis=synthesis,
                worker_usages=ordered_usages,
                worker_total_cost=worker_total_cost,
                cost_for_usage=cost_for_usage,
                cap_usd=cap,
                budget_halted=halted,
                failed_worker_count=failed_workers,
                planned_workers=len(sub_questions),
                completed_workers=completed_count,
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

    answer_parts: list[str] = []
    source_ids: list[str] = list(continuation.source_ids)
    # H-010: mutable checkpoint state across nested pauses on the same resume.
    reasoning_parts: list[str] = (
        [continuation.partial_reasoning] if continuation.partial_reasoning else []
    )
    tool_transcript: list[dict[str, Any]] = [
        dict(part) for part in continuation.tool_transcript
    ]
    # O-002: restore pre-pause usage so finals include pause spend.
    usage = continuation.paused_worker_usage or UsageUpdate()
    pre_pause_cost = float(continuation.paused_worker_cost_usd or 0.0)
    if pre_pause_cost <= 0.0 and continuation.paused_worker_usage is not None:
        pre_pause_cost = cost_for_usage(continuation.paused_worker_usage)
    # H-010: seed prior tool results from the checkpoint, then the resume settle.
    prior_results: list[ToolResult] = []
    for part in continuation.tool_transcript:
        if part.get("type") != "tool_result":
            continue
        prior_results.append(
            ToolResult(
                tool_call_id=str(part.get("toolCallId") or ""),
                name=str(part.get("name") or ""),
                label=str(part["label"]) if isinstance(part.get("label"), str) else None,
                status=(
                    part["status"]
                    if part.get("status")
                    in ("running", "succeeded", "failed", "cancelled", "awaiting_approval")
                    else "succeeded"
                ),
                approval_state=(
                    part["approvalState"]
                    if part.get("approvalState")
                    in ("not_required", "pending", "approved", "rejected")
                    else "not_required"
                ),
                summary=(
                    str(part["summary"]) if isinstance(part.get("summary"), str) else None
                ),
                output=dict(part.get("output") or {})
                if isinstance(part.get("output"), dict)
                else {},
                error=str(part["error"]) if isinstance(part.get("error"), str) else None,
                subagent_id=paused_id,
            )
        )
    initial = [*prior_results]
    if resume_tool_result is not None:
        initial.append(resume_tool_result)
        # Include the settled resume result in the durable transcript so a
        # second nested pause does not drop the first approval's tool_result.
        tool_transcript.append(
            {
                "type": "tool_result",
                "toolCallId": namespace_tool_call_id(
                    paused_id, resume_tool_result.tool_call_id
                ),
                "name": resume_tool_result.name,
                "label": resume_tool_result.label,
                "status": resume_tool_result.status,
                "approvalState": resume_tool_result.approval_state,
                "summary": resume_tool_result.summary,
                "output": dict(resume_tool_result.output or {}),
                "error": resume_tool_result.error,
                "subagentId": paused_id,
            }
        )
    prompt = clarify.with_clarifications(
        planner.worker_prompt(index, sub_question, scaffolded=scaffolded),
        resume_records,
        phase="worker",
    )

    used_fallback = False
    sub_code: SubstitutionReasonCode | None = None
    sub_provider: str | None = None
    sub_model: str | None = None
    sub_label: str | None = None
    worker_failed = False

    def _has_usage(u: UsageUpdate) -> bool:
        return bool(
            u.input_tokens
            or u.output_tokens
            or u.reasoning_tokens
            or u.cached_input_tokens
        )

    def _price(u: UsageUpdate) -> float:
        if used_fallback and fallback_cost_for_usage is not None:
            return fallback_cost_for_usage(u)
        return cost_for_usage(u)

    def _stamp_fallback_route() -> None:
        nonlocal sub_provider, sub_model, sub_label
        if sub_provider is None and fallback_provider_id is not None:
            sub_provider = fallback_provider_id
        if sub_model is None and fallback_model_id is not None:
            sub_model = fallback_model_id
        if sub_label is None and fallback_display_label is not None:
            sub_label = fallback_display_label

    def _nested_continuation() -> AgenticContinuation:
        partial = "".join(answer_parts)
        return AgenticContinuation(
            phase="worker",
            paused_subagent_id=paused_id,
            user_text=effective_user_text,
            plan=tuple(sub_questions),
            completed_workers=tuple(continuation.completed_workers),
            planner_usage=planner_usage,
            planner_cost_usd=planner_cost,
            budget_halted=budget_halted,
            failed_workers=failed_workers,
            actual_cost_usd=ledger_usd,
            paused_worker_index=index,
            paused_sub_question=sub_question,
            partial_answer=partial,
            partial_reasoning="".join(reasoning_parts),
            source_ids=tuple(source_ids),
            tool_transcript=tuple(tool_transcript),
            emitted_answer_chars=max(
                continuation.emitted_answer_chars, len(partial)
            ),
            clarifications=continuation.clarifications,
            orchestration_mode=continuation.orchestration_mode,
            tier_id=continuation.tier_id,
            provider_id=continuation.provider_id,
            model_id=continuation.model_id,
            paused_worker_usage=usage,
            paused_worker_cost_usd=_price(usage),
        )

    async def _drain(make_stream: MakeStream) -> AsyncIterator[ProviderEvent | Literal["paused"]]:
        nonlocal usage, budget_halted, sub_code, sub_provider, sub_model, sub_label
        async for event in run_agent_loop(
            make_stream=make_stream,
            settings=settings,
            allowed_tools=_WORKER_ALLOWED_TOOLS,
            server_approved_call_ids=server_approved_call_ids,
            initial_tool_results=initial,
        ):
            if isinstance(event, AnswerDelta):
                answer_parts.append(event.text)
            if isinstance(event, Sources):
                for item in event.items:
                    sid = getattr(item, "id", None)
                    if sid is not None:
                        source_ids.append(str(sid))
            if isinstance(event, Complete) and event.substitution is not None:
                sub_code = event.substitution
                sub_provider = event.substituted_provider
                sub_model = event.substituted_model
                sub_label = event.substituted_display_label
            if isinstance(event, ToolCall):
                tool_transcript.append(
                    {
                        "type": "tool_call",
                        "id": namespace_tool_call_id(paused_id, event.id),
                        "name": event.name,
                        "label": event.label,
                        "status": event.status,
                        "approvalState": event.approval_state,
                        "input": dict(event.input or {}),
                        "subagentId": paused_id,
                    }
                )
            if isinstance(event, ToolResult):
                tool_transcript.append(
                    {
                        "type": "tool_result",
                        "toolCallId": namespace_tool_call_id(
                            paused_id, event.tool_call_id
                        ),
                        "name": event.name,
                        "label": event.label,
                        "status": event.status,
                        "approvalState": event.approval_state,
                        "summary": event.summary,
                        "output": dict(event.output or {}),
                        "error": event.error,
                        "subagentId": paused_id,
                    }
                )
            if isinstance(event, ReasoningDelta):
                reasoning_parts.append(event.text)
            usage = _fold_usage(event, usage)
            if isinstance(event, AwaitingApproval):
                yield _tag(
                    replace(
                        event, continuation=serialize_continuation(_nested_continuation())
                    ),
                    paused_id,
                )
                yield "paused"
                return
            if not budget_halted and budget.exceeds_cap(
                actual_usd=ledger_usd - pre_pause_cost + _price(usage),
                cap_usd=cap,
                headroom_usd=budget_headroom_usd,
            ):
                budget_halted = True
            yield _tag(event, paused_id)

    with invoke_agent_span(subagent_id=paused_id, role="worker", label=label):
        yield SubagentStarted(subagent_id=paused_id, label=label, role="worker")
        # H-010: restore pre-pause text into the local buffer for synthesis, but
        # do NOT re-emit AnswerDelta — that text was already delivered on the
        # paused turn and persisted on the awaiting_approval assistant.
        if continuation.partial_answer:
            answer_parts.append(continuation.partial_answer)

        nested_paused = False
        try:
            async for item in _drain(
                make_stream_for(prompt, allowed_tools=_WORKER_ALLOWED_TOOLS)
            ):
                if item == "paused":
                    nested_paused = True
                    break
                yield item
        except BaseException as exc:
            prior_partial = (
                [continuation.partial_answer] if continuation.partial_answer else []
            )
            had_partial = (
                bool(answer_parts) and answer_parts != prior_partial
            ) or _has_usage(usage)
            # Treat only newly streamed text/usage as partial for fallback gate.
            streamed_new = (
                ("".join(answer_parts) != (continuation.partial_answer or ""))
                or (
                    _has_usage(usage)
                    and usage != (continuation.paused_worker_usage or UsageUpdate())
                )
            )
            if (
                not streamed_new
                and fallback_make_stream_for is not None
                and is_retryable(exc)
            ):
                if isinstance(exc, AppError) and exc.envelope.code == "RATE_LIMITED":
                    sub_code = "rate_limited"
                else:
                    sub_code = "provider_fallback"
                used_fallback = True
                _stamp_fallback_route()
                try:
                    async for item in _drain(
                        fallback_make_stream_for(
                            prompt, allowed_tools=_WORKER_ALLOWED_TOOLS
                        )
                    ):
                        if item == "paused":
                            nested_paused = True
                            break
                        yield item
                    _stamp_fallback_route()
                except BaseException as retry_exc:
                    _log.warning(
                        "agentic.resume_worker_fallback_failed",
                        subagent_id=paused_id,
                        error=str(retry_exc),
                    )
                    worker_failed = True
            else:
                _ = had_partial
                _log.warning(
                    "agentic.resume_worker_failed",
                    subagent_id=paused_id,
                    error=str(exc),
                )
                worker_failed = True

        if nested_paused:
            return

        if worker_failed:
            failed_workers += 1
            failed_cost = _price(usage)
            yield SubagentDone(
                subagent_id=paused_id,
                label=label,
                role="worker",
                usage=usage,
                cost_usd=failed_cost,
                outcome="failed",
                substitution=sub_code,
                substituted_provider=sub_provider,
                substituted_model=sub_model,
                substituted_display_label=sub_label,
            )
            usages[paused_id] = usage
            costs[paused_id] = failed_cost
            ledger_usd = ledger_usd - pre_pause_cost + failed_cost
        else:
            cost = _price(usage)
            post_delta = max(0.0, cost - pre_pause_cost)
            ledger_usd = ledger_usd + post_delta
            yield SubagentDone(
                subagent_id=paused_id,
                label=label,
                role="worker",
                usage=usage,
                cost_usd=cost,
                outcome="budget_cancelled" if budget_halted else "succeeded",
                substitution=sub_code,
                substituted_provider=sub_provider,
                substituted_model=sub_model,
                substituted_display_label=sub_label,
            )
            results[paused_id] = WorkerOutput(
                subagent_id=paused_id,
                sub_question=sub_question,
                answer="".join(answer_parts),
                source_ids=tuple(dict.fromkeys(source_ids)),
            )
            usages[paused_id] = usage
            costs[paused_id] = cost

    async for event in _emit_synthesis(halted=budget_halted):
        yield event




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
            budget_headroom_usd=budget_headroom_usd,
            fallback_make_stream_for=fallback_make_stream_for,
            fallback_cost_for_usage=fallback_cost_for_usage,
            fallback_provider_id=fallback_provider_id,
            fallback_model_id=fallback_model_id,
            fallback_display_label=fallback_display_label,
            is_retryable=is_retryable,
            verifier_make_stream_for=verifier_make_stream_for,
            verifier_cost_for_usage=verifier_pricer,
        ):
            yield event
        return

    scaffolded = settings.provider_backend == "fake"

    # Clarify-before-plan HITL (plan 02). Runs BEFORE planning so we do not spend
    # planner tokens / commit the ~15x budget on an ambiguous brief. Decline
    # short-circuits with a labeled synthesis (no plan, no workers). Only on a
    # fresh run (`plan_approved is None`) - a plan-approval resume has already
    # passed this gate.
    if clarify_answered is None and plan_approved is None:
        clarify_paused = False
        async for event in _maybe_clarify_before_plan(
            settings, user_text=user_text, scaffolded=scaffolded
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
    ):
        # Deterministic decomposition: the fake provider, an explicit
        # `DEEP_RESEARCH:` opt-in, or a decline (sub-questions go unused — no
        # fan-out — so skip the model planner call entirely). Uses plan_text
        # only so clarifications never enter the pipe-split.
        sub_questions = planner.decompose(plan_text, max_workers=max_workers)
    else:
        # Real-provider planner: a bounded model pass decomposes the prompt into
        # sub-questions so a plain request fans out without the user typing the
        # `DEEP_RESEARCH:` marker. Clarifications ride as trailing DATA.
        plan_reply, planner_usage = await _collect_answer(
            make_stream_for,
            settings,
            planner.build_planner_prompt(effective_user_text, max_workers=max_workers),
        )
        sub_questions = planner.parse_plan(
            plan_reply, max_workers=max_workers, fallback=plan_text
        )
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
    planner_cost = cost_for_usage(planner_usage)
    if plan_approved is None:
        if settings.agentic_plan_approval:
            async for event in _emit_planner_receipt(
                planner_usage=planner_usage,
                cost_for_usage=cost_for_usage,
                cap_usd=cap,
                ledger_usd=planner_cost,
                open_bracket=True,
            ):
                yield event
            async for event in _maybe_plan_approval(
                settings,
                sub_questions,
                estimate_usd=estimate,
                cap_usd=cap,
                skip_started=True,
                clarifications=bound_records,
            ):
                yield event
            return
    elif plan_approved is False:
        # Declined on resume: no fan-out, a labeled (non-error) synthesis.
        # Include any planner usage from a prior real-provider plan pass.
        async for event in _emit_planner_receipt(
            planner_usage=planner_usage,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
            ledger_usd=planner_cost,
        ):
            yield event
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the research plan was declined; no sub-agents were run."
            ),
            worker_usages=[planner_usage],
            worker_total_cost=planner_cost,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
        ):
            yield event
        return

    # Pre-spawn admission (T5). If the worst-case estimate already exceeds the
    # effective cap (run cap composed with user/platform headroom), don't spawn —
    # degrade gracefully to a labeled, explained synthesis (never a silent
    # overrun, never an error). Fold planner spend into the reject exit (BE-015).
    decision = _admit(
        estimate_usd=estimate, settings=settings, budget_headroom_usd=budget_headroom_usd
    )
    if not decision.admitted:
        async for event in _emit_planner_receipt(
            planner_usage=planner_usage,
            cost_for_usage=cost_for_usage,
            cap_usd=cap,
            ledger_usd=planner_cost,
        ):
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
        ):
            yield event
        return

    # Seed the run ledger with planner actuals before fan-out (BE-014 / SAF-004).
    async for event in _emit_planner_receipt(
        planner_usage=planner_usage,
        cost_for_usage=cost_for_usage,
        cap_usd=cap,
        ledger_usd=planner_cost,
    ):
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
        ):
            yield event
        return

    semaphore = asyncio.Semaphore(max(1, settings.agentic_max_concurrency))
    queue: asyncio.Queue[ProviderEvent | _WorkerSentinel | _WorkerPause] = asyncio.Queue()
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
        source_ids: list[str] = []
        usage = UsageUpdate()
        worker_failed = False
        worker_started = False
        used_fallback = False
        sub_code: SubstitutionReasonCode | None = None
        sub_provider: str | None = None
        sub_model: str | None = None
        sub_label: str | None = None

        def _has_usage(u: UsageUpdate) -> bool:
            return bool(
                u.input_tokens
                or u.output_tokens
                or u.reasoning_tokens
                or u.cached_input_tokens
            )

        def _price(u: UsageUpdate) -> float:
            if used_fallback and fallback_cost_for_usage is not None:
                return fallback_cost_for_usage(u)
            return cost_for_usage(u)

        def _stamp_fallback_route() -> None:
            nonlocal sub_provider, sub_model, sub_label
            if sub_provider is None and fallback_provider_id is not None:
                sub_provider = fallback_provider_id
            if sub_model is None and fallback_model_id is not None:
                sub_model = fallback_model_id
            if sub_label is None and fallback_display_label is not None:
                sub_label = fallback_display_label

        async def _consume(make_stream: MakeStream) -> bool:
            """Drain one worker loop. Returns True when paused for tool HITL."""
            nonlocal usage, sub_code, sub_provider, sub_model, sub_label
            last_tool_name = "unknown"
            last_tool_label: str | None = None
            reasoning_parts: list[str] = []
            tool_transcript: list[dict[str, Any]] = []
            async for event in run_agent_loop(
                make_stream=make_stream,
                settings=settings,
                allowed_tools=_WORKER_ALLOWED_TOOLS,
            ):
                if isinstance(event, AnswerDelta):
                    answer_parts.append(event.text)
                if isinstance(event, Sources):
                    for item in event.items:
                        sid = getattr(item, "id", None)
                        if sid is not None:
                            source_ids.append(str(sid))
                if isinstance(event, Complete) and event.substitution is not None:
                    sub_code = event.substitution
                    sub_provider = event.substituted_provider
                    sub_model = event.substituted_model
                    sub_label = event.substituted_display_label
                if isinstance(event, ToolCall):
                    last_tool_name = event.name
                    last_tool_label = event.label
                    tool_transcript.append(
                        {
                            "type": "tool_call",
                            "id": namespace_tool_call_id(subagent_id, event.id),
                            "name": event.name,
                            "label": event.label,
                            "status": event.status,
                            "approvalState": event.approval_state,
                            "input": dict(event.input or {}),
                            "subagentId": subagent_id,
                        }
                    )
                if isinstance(event, ToolResult):
                    tool_transcript.append(
                        {
                            "type": "tool_result",
                            "toolCallId": namespace_tool_call_id(
                                subagent_id, event.tool_call_id
                            ),
                            "name": event.name,
                            "label": event.label,
                            "status": event.status,
                            "approvalState": event.approval_state,
                            "summary": event.summary,
                            "output": dict(event.output or {}),
                            "error": event.error,
                            "subagentId": subagent_id,
                        }
                    )
                if isinstance(event, ReasoningDelta):
                    reasoning_parts.append(event.text)
                usage = _fold_usage(event, usage)
                if isinstance(event, AwaitingApproval):
                    # BE-005: relay was already done for the pending ToolCall.
                    # Stash pause; siblings keep running (wait policy).
                    # H-004: namespace call id to this subagent before pause.
                    namespaced_id = namespace_tool_call_id(
                        subagent_id, event.tool_call_id
                    )
                    partial = "".join(answer_parts)
                    await queue.put(
                        _WorkerPause(
                            subagent_id=subagent_id,
                            index=index,
                            sub_question=sub_question,
                            tool_call_id=namespaced_id,
                            tool_name=last_tool_name,
                            usage=usage,
                            partial_answer=partial,
                            tool_label=last_tool_label,
                            source_ids=tuple(source_ids),
                            tool_transcript=tuple(tool_transcript),
                            partial_reasoning="".join(reasoning_parts),
                            emitted_answer_chars=len(partial),
                        )
                    )
                    return True
                await queue.put(_tag(event, subagent_id))
            return False

        try:
            async with semaphore:
                with invoke_agent_span(subagent_id=subagent_id, role="worker", label=label):
                    await queue.put(
                        SubagentStarted(subagent_id=subagent_id, label=label, role="worker")
                    )
                    worker_started = True
                    prompt = clarify.with_clarifications(
                        planner.worker_prompt(
                            index, sub_question, scaffolded=scaffolded
                        ),
                        bound_records,
                        phase="worker",
                    )
                    try:
                        paused = await _consume(
                            make_stream_for(prompt, allowed_tools=_WORKER_ALLOWED_TOOLS)
                        )
                        if paused:
                            # Leave without SubagentDone — resume continues this worker.
                            return
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:
                        # SAF-008 / BE-024: never retry after visible partial
                        # output or usage — that concatenates two attempts and
                        # drops primary spend from the roll-up.
                        had_partial = bool(answer_parts) or _has_usage(usage)
                        if (
                            not had_partial
                            and fallback_make_stream_for is not None
                            and is_retryable(exc)
                        ):
                            if isinstance(exc, AppError) and exc.envelope.code == "RATE_LIMITED":
                                sub_code = "rate_limited"
                            else:
                                sub_code = "provider_fallback"
                            used_fallback = True
                            _stamp_fallback_route()
                            try:
                                paused = await _consume(
                                    fallback_make_stream_for(
                                        prompt, allowed_tools=_WORKER_ALLOWED_TOOLS
                                    )
                                )
                                _stamp_fallback_route()
                                if paused:
                                    return
                            except asyncio.CancelledError:
                                raise
                            except BaseException as retry_exc:
                                _log.warning(
                                    "agentic.worker_fallback_failed",
                                    subagent_id=subagent_id,
                                    error=str(retry_exc),
                                )
                                worker_failed = True
                        else:
                            _log.warning(
                                "agentic.worker_failed",
                                subagent_id=subagent_id,
                                error=str(exc),
                            )
                            worker_failed = True
                    if worker_failed:
                        failed_workers += 1
                        # Bill any partial primary/fallback usage even when the
                        # worker fails (or when post-partial retry is refused).
                        failed_cost = _price(usage)
                        await queue.put(
                            SubagentDone(
                                subagent_id=subagent_id,
                                label=label,
                                role="worker",
                                usage=usage,
                                cost_usd=failed_cost,
                                outcome="failed",
                                substitution=sub_code,
                                substituted_provider=sub_provider,
                                substituted_model=sub_model,
                                substituted_display_label=sub_label,
                            )
                        )
                        # Always record usage for the final Complete roll-up
                        # (SAF-005) — even a zero-token failure is a closed row.
                        usages[subagent_id] = usage
                        costs[subagent_id] = failed_cost
                    else:
                        # Price on the binding that actually served (FE-009 /
                        # BE-023 / SAF-006).
                        cost = _price(usage)
                        await queue.put(
                            SubagentDone(
                                subagent_id=subagent_id,
                                label=label,
                                role="worker",
                                usage=usage,
                                cost_usd=cost,
                                outcome="succeeded",
                                substitution=sub_code,
                                substituted_provider=sub_provider,
                                substituted_model=sub_model,
                                substituted_display_label=sub_label,
                            )
                        )
                        output = WorkerOutput(
                            subagent_id=subagent_id,
                            sub_question=sub_question,
                            answer="".join(answer_parts),
                            source_ids=tuple(source_ids),
                        )
                        results[subagent_id] = output
                        usages[subagent_id] = usage
                        costs[subagent_id] = cost
        except asyncio.CancelledError:
            # Budget mid-flight kill (or outer teardown): emit a terminal done
            # for every started worker so the FE never shows a green check for
            # a cancelled row (FE-002). Snapshot usage into the run ledger so
            # already-reported spend survives into the final Complete (SAF-005).
            # Non-budget cancels (stop/disconnect/teardown) use outcome="stopped"
            # so failures stay distinguishable from budget_cancelled.
            if worker_started:
                cancel_cost = _price(usage) if _has_usage(usage) else 0.0
                await queue.put(
                    SubagentDone(
                        subagent_id=subagent_id,
                        label=label,
                        role="worker",
                        usage=usage,
                        cost_usd=cancel_cost,
                        outcome=(
                            "budget_cancelled" if budget_halted else "stopped"
                        ),
                        substitution=sub_code,
                        substituted_provider=sub_provider,
                        substituted_model=sub_model,
                        substituted_display_label=sub_label,
                    )
                )
                usages[subagent_id] = usage
                costs[subagent_id] = cancel_cost
            raise
        finally:
            await queue.put(_WorkerSentinel(subagent_id))

    tasks = [
        asyncio.create_task(_run_worker(index, subagent_id, label, sub_question))
        for index, subagent_id, label, sub_question in worker_meta
    ]
    # Mid-flight kill (T5): ledger starts with planner actuals (BE-014), then
    # accumulates each worker's `SubagentDone` cost; on a cap breach, cancel the
    # remaining workers and aggregate whatever completed — a labeled partial
    # synthesis rather than a silent overrun.
    actual_cost = planner_cost
    budget_halted = False
    # BE-005: at most one worker tool-HITL pause per fan-out (first wins).
    # Sibling policy = wait for others to finish before surfacing AwaitingApproval.
    worker_pause: _WorkerPause | None = None
    try:
        remaining = len(tasks)
        while remaining > 0:
            item = await queue.get()
            if isinstance(item, _WorkerSentinel):
                remaining -= 1
                continue
            if isinstance(item, _WorkerPause):
                if worker_pause is None:
                    worker_pause = item
                    # Snapshot partial usage into the ledger so pause cost is billed.
                    usages[item.subagent_id] = item.usage
                    costs[item.subagent_id] = cost_for_usage(item.usage)
                    actual_cost += costs[item.subagent_id]
                else:
                    # H-003 / O-007: cancel orphaned sibling pauses so they are
                    # not left pending without a continuation. The handler flips
                    # the matching tool_call's approvalState to rejected when it
                    # applies this result (never leave pending+cancelled).
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
                        subagent_id=item.subagent_id,
                    )
                    # Bill partial usage for the cancelled pause.
                    usages[item.subagent_id] = item.usage
                    costs[item.subagent_id] = cost_for_usage(item.usage)
                    actual_cost += costs[item.subagent_id]
                    failed_workers += 1
                continue
            yield item
            if isinstance(item, SubagentDone) and item.role == "worker":
                actual_cost += item.cost_usd or 0.0
                # Mid-run meter tick (estimate + mid + final; FE-011 / FE-012).
                yield RunCost(
                    subtotal_usd=actual_cost,
                    cap_usd=cap,
                    confidence="exact",
                    phase="progress",
                )
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
                    usage=usages.get(sid, UsageUpdate()),
                    cost_usd=costs.get(sid, 0.0),
                    outcome="succeeded",
                    source_ids=out.source_ids,
                )
            )
        cont = AgenticContinuation(
            phase="worker",
            paused_subagent_id=worker_pause.subagent_id,
            user_text=effective_user_text,
            plan=tuple(sub_questions),
            completed_workers=tuple(completed_states),
            planner_usage=planner_usage,
            planner_cost_usd=planner_cost,
            budget_halted=budget_halted,
            failed_workers=failed_workers,
            actual_cost_usd=actual_cost,
            paused_worker_index=worker_pause.index,
            paused_sub_question=worker_pause.sub_question,
            partial_answer=worker_pause.partial_answer,
            partial_reasoning=worker_pause.partial_reasoning,
            source_ids=worker_pause.source_ids,
            tool_transcript=worker_pause.tool_transcript,
            emitted_answer_chars=worker_pause.emitted_answer_chars,
            clarifications=tuple(bound_records),
            orchestration_mode="deep_research",
            paused_worker_usage=worker_pause.usage,
            paused_worker_cost_usd=costs.get(
                worker_pause.subagent_id, cost_for_usage(worker_pause.usage)
            ),
        )
        yield AwaitingApproval(
            tool_call_id=worker_pause.tool_call_id,
            subagent_id=worker_pause.subagent_id,
            continuation=serialize_continuation(cont),
        )
        return

    ordered_outputs = [results[sid] for _, sid, _, _ in worker_meta if sid in results]
    # In-turn structured artifact refs (plan 02) — handed to the aggregator as
    # schema-shaped DATA rather than raw telephone stuffing.
    ordered_artifacts = aggregate.build_artifacts(
        ordered_outputs, max_artifacts=settings.agentic_max_workers
    )
    # Fold the (real-provider) planner pass into the run totals so its tokens are
    # billed honestly. `planner_usage` is the zero default on the scaffolded /
    # explicit-marker path, so the fake-provider totals are unchanged.
    ordered_usages = [usages[sid] for _, sid, _, _ in worker_meta if sid in usages]
    ordered_usages.append(planner_usage)
    worker_total_cost = sum(
        costs.get(sid, 0.0) for _, sid, _, _ in worker_meta
    ) + cost_for_usage(planner_usage)

    # BE-014 residual: before starting the aggregator, refuse a model synthesis
    # call when the ledger already exceeds the cap or the aggregator phase
    # estimate cannot fit. Degrade to deterministic (zero-token) synthesis.
    # Verifier funding is a SEPARATE gate after the aggregator draft exists —
    # do not fold N judge slots into this check.
    expected_agg = budget._expected_subagent_usage(settings)
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
        verifier_result: verifier.VerifyResult | None = None
        verifier_outcome: Literal["succeeded", "failed"] = "succeeded"
        synthesis = draft
        # Open aggregator first so the UI sees synthesis ownership, then run the
        # verifier as a sibling (Started before await; Done before final answer).
        yield SubagentStarted(
            subagent_id=_AGGREGATOR_ID, label=_AGGREGATOR_LABEL, role="aggregator"
        )
        if settings.agentic_verifier and _can_fund_verifier(
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
                verifier_result = await _run_verifier_if_enabled(
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
                )
            except Exception:
                _log.exception("agentic.verifier_failed")
                verifier_outcome = "failed"
                verifier_result = None
            else:
                synthesis, verifier_outcome, v_budget_halted = (
                    _apply_verifier_result(draft, verifier_result)
                )
                if v_budget_halted:
                    budget_halted = True
            if verifier_result is None and verifier_outcome == "succeeded":
                verifier_outcome = "failed"
            async for event in _emit_verifier_receipt(
                result=verifier_result,
                cost_for_usage=verifier_pricer,
                ledger_usd=worker_total_cost,
                cap_usd=cap,
                outcome=verifier_outcome,
                emit_started=False,
            ):
                yield event
        with invoke_agent_span(
            subagent_id=_AGGREGATOR_ID, role="aggregator", label=_AGGREGATOR_LABEL
        ):
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
                outcome="succeeded",
            )
        v_usage = (
            verifier_result.usage if verifier_result is not None else UsageUpdate()
        )
        verifier_cost = _verifier_cost(verifier_result, verifier_pricer)
        verifier_budget_halted = (
            verifier_result.budget_halted if verifier_result is not None else False
        )
        total_usage = _sum_usages([*ordered_usages, aggregator_usage, v_usage])
        total_cost = worker_total_cost + aggregator_cost + verifier_cost
        yield Complete(usage=total_usage)
        effective_budget_halted = budget_halted or verifier_budget_halted
        yield RunCost(
            subtotal_usd=total_cost,
            cap_usd=cap,
            confidence="exact",
            phase="final",
            partial=effective_budget_halted or failed_workers > 0,
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
            budget_headroom_usd=budget_headroom_usd,
            scaffolded=scaffolded,
            artifacts=ordered_artifacts,
            clarifications=synth_clarify,
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
        ):
            yield event
    else:
        async for event in _run_single(
            make_stream_for=make_stream_for,
            settings=settings,
            user_text=user_text,
            cost_for_usage=cost_for_usage,
            budget_headroom_usd=budget_headroom_usd,
            server_approved_call_ids=server_approved_call_ids,
            initial_tool_results=(
                [resume_tool_result] if resume_tool_result is not None else None
            ),
        ):
            yield event
