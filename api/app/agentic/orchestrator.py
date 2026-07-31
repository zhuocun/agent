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
import contextlib
import hashlib
import json
import re
import secrets
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

import structlog

from app.agentic import aggregate, budget, clarify, planner, verifier
from app.agentic.aggregate import WorkerOutput
from app.agentic.continuation import (
    AgenticContinuation,
    CompletedWorkerState,
    serialize_continuation,
    usage_to_wire,
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
from app.runtime.run_receipt import (
    CostLedger,
    ReceiptBoundary,
    RunReceipt,
    UsageTotals,
)
from app.schemas.common import SubstitutionReasonCode
from app.search.protocol import SourceItem
from app.streaming.constants import EMPTY_REPLY_FALLBACK, main_answer_is_empty
from app.tools.agent_loop import (
    TOOL_CALL_ID_NAMESPACE_SEP,
    MakeStream,
    run_agent_loop,
)

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


def _verifier_degraded(result: verifier.VerifyResult | None) -> bool:
    """True when a verifier ran but did not fully succeed (FL-08).

    `unavailable` / `failed` / `partial` / `budget_halted` are all text-only
    degrades today; they must also raise `RunCost.partial`.
    """
    return result is not None and result.outcome != "succeeded"


def _verification_degraded(
    result: verifier.VerifyResult | None,
    outcome: Literal["succeeded", "failed"],
) -> bool:
    """True when the verification did not fully succeed, judge crashes included.

    A wire `outcome` of "failed" with a `None` result is precisely the
    crashed-judge case `_verifier_degraded` cannot see: the exception handler
    drops the result, so result-only inspection reports a clean run while the
    verifier span says failed and the answer body carries a failure caveat.
    """
    return outcome == "failed" or _verifier_degraded(result)

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


@dataclass(frozen=True)
class _WorkerSubstituted:
    """Internal queue marker: this worker's route flipped to the fallback (FL-22).

    NOT a `ProviderEvent` — it never escapes the orchestrator. Enqueued the moment
    ``used_fallback`` flips, i.e. ahead of every event the fallback stream will
    put, so the mid-flight kill gate prices this worker's provisional samples on
    the binding that actually serves them. Deriving that from a relayed
    ``Complete.substitution`` alone leaves the bare ``UsageUpdate`` samples that
    precede the terminal priced at the primary rate.
    """

    subagent_id: str


# Single source with the agent loop's settlement guard, which must de-namespace
# seeded ids to match a provider reissue (FL-15).
_TOOL_CALL_NS_SEP = TOOL_CALL_ID_NAMESPACE_SEP


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
    # B6: pause served on fallback — price + resume pin on that route.
    used_fallback: bool = False


def _has_nonzero_usage(u: UsageUpdate) -> bool:
    return bool(
        u.input_tokens
        or u.output_tokens
        or u.reasoning_tokens
        or u.cached_input_tokens
    )


def _event_shows_external_progress(event: ProviderEvent) -> bool:
    """True when an event was (or will be) visible outside the worker (B16).

    Transparent fallback is only safe before any client-visible progress —
    reasoning/status/sources/tools count, not just answer text / usage.
    """
    return isinstance(
        event,
        (
            AnswerDelta,
            ReasoningDelta,
            StatusUpdate,
            Sources,
            ToolCall,
            ToolResult,
            AwaitingApproval,
        ),
    )


# Bound the worker fan-out → consumer queue so a slow drain cannot buffer an
# unbounded number of worker events in process memory (B23). ``await put``
# applies backpressure; teardown uses non-blocking put with drop-oldest.
_FANOUT_QUEUE_MAXSIZE = 256


# Trailing incomplete citation opener: `[` or `[` + digits without a closing `]`.
_INCOMPLETE_CITATION_TAIL_RE = re.compile(r"\[\d*$")


class _SourceIdRemapper:
    """Globally renumber worker-local ``Sources`` ordinals mid-fan-out (B12).

    A single remapper instance owns the run's global citation space. Mid-stream
    remapping is the only mapping step — do not call
    ``aggregate.remap_worker_source_ids`` again at the synthesis sink (that
    reordered by worker-plan order and diverged from event-arrival globals).

    AnswerDelta rewriting is chunk-safe: a marker split across deltas
    (``"See ["`` + ``"1]."``) is held in a per-subagent carry until complete.
    """

    def __init__(self, *, start: int = 1) -> None:
        self._next = max(1, start)
        self._map: dict[tuple[str, int], int] = {}
        # Global-id → remapped SourceItem (merged catalog for the aggregator).
        self._catalog: dict[int, SourceItem] = {}
        # Per-subagent unfinished citation fragment from the prior AnswerDelta.
        self._answer_carry: dict[str, str] = {}

    def seed_catalog(self, items: Sequence[SourceItem]) -> None:
        """Pre-load a persisted catalog (resume) and advance the next id."""
        for item in items:
            gid = int(item.id)
            self._catalog[gid] = item
            if gid >= self._next:
                self._next = gid + 1

    def merged_items(self) -> list[SourceItem]:
        """Return the merged global catalog in ascending citation id order."""
        return [self._catalog[i] for i in sorted(self._catalog)]

    def _global_id(self, subagent_id: str, local: int) -> int:
        """Global id for a worker-local ordinal, allocating on first sight (FL-16-a).

        Every citation surface routes through here — ``Sources`` remap, both
        AnswerDelta rewrites and ``mapped_ids_for`` — so a marker cited BEFORE its
        own ``Sources`` event can never fall through to the raw local ordinal.
        Falling through resolved the marker against whichever worker happened to
        own that global id, silently misattributing a claim (FE-1).
        """
        key = (subagent_id, local)
        gid = self._map.get(key)
        if gid is None:
            gid = self._next
            self._map[key] = gid
            self._next += 1
        return gid

    def remap_sources(self, event: Sources, subagent_id: str) -> Sources:
        new_items: list[SourceItem] = []
        for item in event.items:
            gid = self._global_id(subagent_id, int(item.id))
            remapped = item.model_copy(update={"id": gid})
            self._catalog[gid] = remapped
            new_items.append(remapped)
        return replace(event, items=new_items)

    def rewrite_answer_text(self, text: str, subagent_id: str) -> str:
        """Rewrite ``[n]`` markers using this subagent's local→global map.

        Incomplete trailing ``[`` / ``[12`` fragments are held until the next
        chunk (or ``flush_answer_carry``) so split markers remapped correctly.
        """
        combined = self._answer_carry.get(subagent_id, "") + text
        hold = ""
        process = combined
        incomplete = _INCOMPLETE_CITATION_TAIL_RE.search(combined)
        if incomplete is not None:
            hold = combined[incomplete.start() :]
            process = combined[: incomplete.start()]
        self._answer_carry[subagent_id] = hold

        if not process:
            return ""

        def _sub(match: re.Match[str]) -> str:
            return f"[{self._global_id(subagent_id, int(match.group(1)))}]"

        return aggregate._CITATION_MARKER_RE.sub(_sub, process)

    def flush_answer_carry(self, subagent_id: str) -> str:
        """Emit any held fragment at worker end, rewriting complete markers."""
        hold = self._answer_carry.pop(subagent_id, "")
        if not hold:
            return ""

        def _sub(match: re.Match[str]) -> str:
            return f"[{self._global_id(subagent_id, int(match.group(1)))}]"

        return aggregate._CITATION_MARKER_RE.sub(_sub, hold)

    def mapped_ids_for(self, subagent_id: str, local_ids: list[str]) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for sid in local_ids:
            try:
                local_int = int(sid)
            except ValueError:
                if sid not in seen:
                    out.append(sid)
                    seen.add(sid)
                continue
            # Source emitted only via the WorkerOutput path — allocate now.
            token = str(self._global_id(subagent_id, local_int))
            if token not in seen:
                out.append(token)
                seen.add(token)
        return tuple(out)


def _max_source_id(ids: Iterable[str]) -> int:
    """Largest integer citation id in ``ids`` (non-numeric ignored)."""
    max_id = 0
    for sid in ids:
        try:
            max_id = max(max_id, int(sid))
        except (TypeError, ValueError):
            continue
    return max_id


def _queue_item_is_protected(item: object) -> bool:
    """Teardown must not drop completion control messages (B23)."""
    return isinstance(item, (_WorkerSentinel, SubagentDone, _WorkerPause))


def _queue_put_nowait_drop_oldest(
    queue: asyncio.Queue[Any], item: object
) -> None:
    """Enqueue ``item`` without awaiting; drop oldest *unprotected* if full (B23).

    Used on cancellation / sentinel paths so teardown cannot block forever on a
    full fan-out queue when the consumer has already stopped draining.

    Never drops ``_WorkerSentinel`` / ``SubagentDone`` / ``_WorkerPause`` already
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
        planner_usage is not None and _has_nonzero_usage(planner_usage)
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


def _verifier_phase_estimate(
    *,
    settings: Settings,
    cost_for_usage: CostForUsage,
    sample_count: int | None = None,
) -> float:
    """USD estimate for ``sample_count`` judge samples (default: configured N).

    One composition for BOTH phase gates (FL-17): reasoning multiplier only,
    matching the aggregator gate in `_run_deep_research`. The fan-out multiplier
    models whole-run multi-agent burn and belongs to `estimate_run_cost` (which
    keeps both) — folding it into a single-phase call made this gate ~15x stricter
    than the aggregator gate for an identical one-shot judge request.
    """
    if not settings.agentic_verifier:
        return 0.0
    n = max(1, sample_count if sample_count is not None else settings.agentic_verifier_n)
    expected = budget.expected_subagent_usage(settings)
    return cost_for_usage(expected) * settings.agentic_reasoning_token_multiplier * n


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

    ``outcome`` is consumed VERBATIM (FL-20). `_apply_verifier_result` owns the
    single VerifyOutcome → wire mapping; re-deriving it here contradicted that
    mapping for `unavailable` and left the returned value silently overridden.
    """
    if result is None and outcome == "succeeded":
        return
    usage = result.usage if result is not None else UsageUpdate()
    cost = _verifier_cost(result, cost_for_usage)
    wire_outcome: Literal["succeeded", "failed"] = outcome
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
        or _verification_degraded(verifier_result, verifier_outcome)
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
    superseded: int = 0,
    budget_headroom_usd: float | None = None,
    scaffolded: bool = False,
    artifacts: list[aggregate.WorkerArtifact] | None = None,
    verifier_cost_for_usage: CostForUsage | None = None,
    clarifications: list[dict[str, str]] | None = None,
    merged_sources: Sequence[SourceItem] | None = None,
    ledger: CostLedger | None = None,
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
    ):
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
                    yield _tag(
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
        except Exception:
            # B8: never raise to the generic handler error path — fall back to
            # deterministic synthesize() over completed workers and emit a failed
            # aggregator receipt with whatever usage was observed.
            _log.exception("agentic.aggregator_failed")
            aggregator_failed = True
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
                # FL-19-b: disclose the judge failure instead of shipping a bare
                # draft that reads as verified. Same caveat the verifier module
                # composes for its own no-samples path (FL-02-a).
                final_answer = verifier.compose_verified_answer(
                    draft, verdict="pass", report="", incomplete_samples=True
                )
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
    agg_outcome: Literal["succeeded", "failed", "budget_cancelled"]
    if aggregator_failed:
        agg_outcome = "failed"
    elif agg_budget_halted:
        agg_outcome = "budget_cancelled"
    else:
        agg_outcome = "succeeded"
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
        verifier_cost = _verifier_cost(verifier_result, verifier_pricer)
    elif verifier_started and verifier_outcome == "failed":
        pass  # zero cost already; bracket closed above
    total_usage = _sum_usages([*worker_usages, aggregator_usage, v_usage])
    total_cost = worker_total_cost + aggregator_cost + verifier_cost
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
        or _verification_degraded(verifier_result, verifier_outcome)
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
            # Planner quiet-collect parses answer text into a plan; an empty-retry
            # nudge answer would corrupt that. Keep it out of the retry (the empty
            # terminal still injects the static fallback text, unchanged).
            allow_empty_retry=False,
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


async def run_single(
    *,
    make_stream_for: StreamFactory,
    settings: Settings,
    user_text: str,
    cost_for_usage: CostForUsage,
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
        ledger.settle(subagent_id, role="primary", cost_usd=0.0, outcome="failed")
        yield _boundary_run_cost(
            ledger, cap_usd=cap, partial=True, budget_halted=True
        )
        return

    prior_usage = prior_run_usage or UsageUpdate()
    prior_cost = max(0.0, float(prior_run_cost_usd or 0.0))
    if prior_cost <= 0.0 and _has_nonzero_usage(prior_usage):
        prior_cost = cost_for_usage(prior_usage)
    if prior_receipt is None and (prior_cost > 0.0 or _has_nonzero_usage(prior_usage)):
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

    # FL-12: admission above prices only the FRESH estimate, so a resume whose
    # seeded ledger is already over the cap used to open another provider stream
    # and overrun by a whole primary turn. Refuse before `make_stream_for`, and
    # degrade to a labeled `done` rather than an error (invariant 8).
    if prior_cost > 0.0 and budget.exceeds_cap(
        actual_usd=prior_cost, cap_usd=cap, headroom_usd=budget_headroom_usd
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
        if prior_receipt is None:
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
        subtotal_usd=prior_cost,
        cap_usd=cap,
        confidence="estimate" if prior_cost <= 0.0 else "exact",
        phase="plan",
    )
    # B5: track this session's usage separately from pre-pause seed so
    # `_fold_usage` replace semantics cannot erase prior spend from the ledger.
    session_usage = UsageUpdate()
    answer_parts: list[str] = []
    budget_halted = False
    pending_tool_name = "unknown"
    pending_tool_label: str | None = None
    with invoke_agent_span(subagent_id=subagent_id, role="primary", label=_PRIMARY_LABEL):
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
            session_usage = _fold_usage(event, session_usage)
            session_cost = cost_for_usage(session_usage)
            if not budget_halted and budget.exceeds_cap(
                actual_usd=prior_cost + session_cost,
                cap_usd=cap,
                headroom_usd=budget_headroom_usd,
            ):
                budget_halted = True
            if isinstance(event, AwaitingApproval):
                if budget_halted:
                    # FL-12: the cap is already breached, so an actionable card
                    # would only buy a resume that must immediately refuse. Cancel
                    # the pending call (AR-004 shape) and fall through to the
                    # labeled budget tail.
                    yield _tag(
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
                pause_usage = _sum_usages([prior_usage, session_usage])
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
                yield _tag(event, subagent_id)
                return
            yield _tag(event, subagent_id)
            if budget_halted and isinstance(event, (Complete, UsageUpdate)):
                break
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
    cumulative_usage = _sum_usages([prior_usage, session_usage])
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
    ledger_usd = float(continuation.actual_cost_usd or 0.0)
    if ledger_usd <= 0.0:
        ledger_usd = (
            sum(w.cost_usd for w in continuation.completed_workers)
            + planner_cost
            + float(continuation.paused_worker_cost_usd or 0.0)
        )

    # AC-02: one owner for this resumed run's money and tokens — there is no
    # second per-phase dictionary. The pause receipt (or, for a legacy row, the
    # checkpoint's own ledger total) is the already-billed floor, so every phase
    # below re-enters the run WITHOUT being charged a second time.
    ledger = CostLedger.restore(prior_receipt)
    if prior_receipt is None:
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
    # B12: one remapper for the resume session. Seed from the pause-turn catalog
    # (and max known ids) so new local ordinals cannot collide with pre-pause
    # globals; mid-stream remap is the only mapping step.
    source_remapper = _SourceIdRemapper()
    if continuation.source_catalog:
        source_remapper.seed_catalog(continuation.source_catalog)
    else:
        seed_max = _max_source_id(continuation.source_ids)
        for out in results.values():
            seed_max = max(seed_max, _max_source_id(out.source_ids))
        if seed_max > 0:
            source_remapper = _SourceIdRemapper(start=seed_max + 1)

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
        ordered_usages.append(planner_usage)
        worker_total_cost = ledger.cumulative_cost_usd
        completed_count = len(ordered_outputs)
        synthesis = aggregate.synthesize(
            ordered_outputs,
            planned=len(sub_questions),
            budget_halted=halted,
            failed=failed_workers,
            clarifications=resume_clarification_answers,
        )
        merged_sources = source_remapper.merged_items()
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

    answer_parts: list[str] = []
    source_ids: list[str] = list(continuation.source_ids)
    # H-010: mutable checkpoint state across nested pauses on the same resume.
    reasoning_parts: list[str] = (
        [continuation.partial_reasoning] if continuation.partial_reasoning else []
    )
    tool_transcript: list[dict[str, Any]] = [
        dict(part) for part in continuation.tool_transcript
    ]
    # B2: keep pre-pause usage immutable; fold resume-only usage separately so
    # `_fold_usage` replace semantics cannot erase pause spend from the ledger.
    pre_pause_usage = continuation.paused_worker_usage or UsageUpdate()
    pre_pause_cost = float(continuation.paused_worker_cost_usd or 0.0)
    if pre_pause_cost <= 0.0 and _has_nonzero_usage(pre_pause_usage):
        # Prefer the durable pause pricer: if the pause was on fallback, the
        # stored paused_worker_cost_usd should already be set; otherwise price
        # on primary (legacy blobs).
        if continuation.paused_worker_used_fallback and fallback_cost_for_usage is not None:
            pre_pause_cost = fallback_cost_for_usage(pre_pause_usage)
        else:
            pre_pause_cost = cost_for_usage(pre_pause_usage)
    resume_usage = UsageUpdate()
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

    # B6: pin resume onto the served route from the pause turn.
    used_fallback = bool(continuation.paused_worker_used_fallback)
    sub_code: SubstitutionReasonCode | None = (
        "provider_fallback" if used_fallback else None
    )
    sub_provider: str | None = None
    sub_model: str | None = None
    sub_label: str | None = None
    worker_failed = False
    # B16: any externally visible progress on this resume attempt.
    visible_progress = False

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

    if used_fallback:
        _stamp_fallback_route()

    def _cumulative_usage() -> UsageUpdate:
        return _sum_usages([pre_pause_usage, resume_usage])

    def _cumulative_cost() -> float:
        return pre_pause_cost + _price(resume_usage)

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
            # Ledger already includes pre_pause; add resume spend only.
            actual_cost_usd=ledger_usd + _price(resume_usage),
            paused_worker_index=index,
            paused_sub_question=sub_question,
            partial_answer=partial,
            partial_reasoning="".join(reasoning_parts),
            source_ids=tuple(source_ids),
            source_catalog=tuple(source_remapper.merged_items()),
            tool_transcript=tuple(tool_transcript),
            emitted_answer_chars=max(
                continuation.emitted_answer_chars, len(partial)
            ),
            clarifications=continuation.clarifications,
            orchestration_mode=continuation.orchestration_mode,
            tier_id=continuation.tier_id,
            provider_id=continuation.provider_id,
            model_id=continuation.model_id,
            paused_worker_usage=_cumulative_usage(),
            paused_worker_cost_usd=_cumulative_cost(),
            paused_worker_used_fallback=used_fallback,
        )

    async def _drain(make_stream: MakeStream) -> AsyncIterator[ProviderEvent | Literal["paused"]]:
        nonlocal resume_usage, budget_halted, sub_code, sub_provider, sub_model, sub_label
        nonlocal visible_progress
        async for event in run_agent_loop(
            make_stream=make_stream,
            settings=settings,
            allowed_tools=_WORKER_ALLOWED_TOOLS,
            server_approved_call_ids=server_approved_call_ids,
            initial_tool_results=initial,
            # Worker subagents never spend the empty-reply retry (amendment B):
            # synthesis / the deterministic aggregate is the recovery here.
            allow_empty_retry=False,
            # FL-04: nor may they ship static filler as a research finding —
            # `"(no answer)"` in synthesis is the honest degrade.
            inject_empty_fallback=False,
        ):
            if _event_shows_external_progress(event):
                visible_progress = True
            if isinstance(event, AnswerDelta):
                text = source_remapper.rewrite_answer_text(event.text, paused_id)
                answer_parts.append(text)
                if text != event.text:
                    event = replace(event, text=text)
            if isinstance(event, Sources):
                event = source_remapper.remap_sources(event, paused_id)
                for item in event.items:
                    source_ids.append(str(item.id))
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
            resume_usage = _fold_usage(event, resume_usage)
            if isinstance(event, AwaitingApproval):
                tail = source_remapper.flush_answer_carry(paused_id)
                if tail:
                    answer_parts.append(tail)
                    yield _tag(AnswerDelta(text=tail, subagent_id=paused_id), paused_id)
                # AC-02: a nested pause is a persistable boundary too, so it
                # carries the receipt for the spend banked up to it.
                ledger.settle(
                    paused_id,
                    role="worker",
                    usage=_cumulative_usage(),
                    cost_usd=_cumulative_cost(),
                )
                yield _boundary_run_cost(
                    ledger,
                    cap_usd=cap,
                    boundary="pause",
                    partial=True,
                    budget_halted=budget_halted,
                    failed_worker_count=failed_workers,
                )
                yield _tag(
                    replace(
                        event, continuation=serialize_continuation(_nested_continuation())
                    ),
                    paused_id,
                )
                yield "paused"
                return
            # B2/B3: ledger already holds pre_pause; add full resume cost only.
            if not budget_halted and budget.exceeds_cap(
                actual_usd=ledger_usd + _price(resume_usage),
                cap_usd=cap,
                headroom_usd=budget_headroom_usd,
            ):
                budget_halted = True
            yield _tag(event, paused_id)
            # B3: mirror `run_single` — stop draining once the cap is breached.
            if budget_halted and isinstance(event, (Complete, UsageUpdate)):
                break
        # B12: flush held citation fragment after the resume stream ends.
        tail = source_remapper.flush_answer_carry(paused_id)
        if tail:
            answer_parts.append(tail)
            yield _tag(AnswerDelta(text=tail, subagent_id=paused_id), paused_id)

    with invoke_agent_span(subagent_id=paused_id, role="worker", label=label):
        yield SubagentStarted(subagent_id=paused_id, label=label, role="worker")
        # H-010: restore pre-pause text into the local buffer for synthesis, but
        # do NOT re-emit AnswerDelta — that text was already delivered on the
        # paused turn and persisted on the awaiting_approval assistant.
        if continuation.partial_answer:
            answer_parts.append(continuation.partial_answer)

        nested_paused = False

        def _primary_make() -> MakeStream:
            # B6: when the pause was on fallback, skip primary and pin resume.
            if used_fallback and fallback_make_stream_for is not None:
                return fallback_make_stream_for(
                    prompt, allowed_tools=_WORKER_ALLOWED_TOOLS
                )
            return make_stream_for(prompt, allowed_tools=_WORKER_ALLOWED_TOOLS)

        try:
            async for item in _drain(_primary_make()):
                if item == "paused":
                    nested_paused = True
                    break
                yield item
        except asyncio.CancelledError:
            # AR-005: Stop/shutdown must not become an ordinary worker failure.
            raise
        except Exception as exc:
            # B16: refuse transparent fallback after any externally visible event.
            # FL-23: also refuse once usage has been BANKED — the retry replaces
            # `resume_usage` rather than summing, so retrying after a bare
            # `UsageUpdate` would drop the primary's tokens from the roll-up.
            if (
                not visible_progress
                and not _has_nonzero_usage(resume_usage)
                and not used_fallback
                and fallback_make_stream_for is not None
                and is_retryable(exc)
            ):
                fb_factory = fallback_make_stream_for
                if isinstance(exc, AppError) and exc.envelope.code == "RATE_LIMITED":
                    sub_code = "rate_limited"
                else:
                    sub_code = "provider_fallback"
                used_fallback = True
                _stamp_fallback_route()
                try:
                    async for item in _drain(
                        fb_factory(prompt, allowed_tools=_WORKER_ALLOWED_TOOLS)
                    ):
                        if item == "paused":
                            nested_paused = True
                            break
                        yield item
                    _stamp_fallback_route()
                except asyncio.CancelledError:
                    raise
                except Exception as retry_exc:
                    _log.warning(
                        "agentic.resume_worker_fallback_failed",
                        subagent_id=paused_id,
                        error=str(retry_exc),
                    )
                    worker_failed = True
            else:
                _log.warning(
                    "agentic.resume_worker_failed",
                    subagent_id=paused_id,
                    error=str(exc),
                )
                worker_failed = True

        if nested_paused:
            return

        resume_cost = _price(resume_usage)
        cumulative_usage = _cumulative_usage()
        cumulative_cost = pre_pause_cost + resume_cost
        # B2: add FULL resume cost to the logical ledger (pre_pause already in it).
        ledger_usd = ledger_usd + resume_cost

        if worker_failed:
            failed_workers += 1
            yield SubagentDone(
                subagent_id=paused_id,
                label=label,
                role="worker",
                usage=cumulative_usage,
                cost_usd=cumulative_cost,
                outcome="failed",
                substitution=sub_code,
                substituted_provider=sub_provider,
                substituted_model=sub_model,
                substituted_display_label=sub_label,
            )
            ledger.settle(
                paused_id,
                role="worker",
                usage=cumulative_usage,
                cost_usd=cumulative_cost,
                outcome="failed",
            )
        else:
            yield SubagentDone(
                subagent_id=paused_id,
                label=label,
                role="worker",
                usage=cumulative_usage,
                cost_usd=cumulative_cost,
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
            ledger.settle(
                paused_id,
                role="worker",
                usage=cumulative_usage,
                cost_usd=cumulative_cost,
                outcome="budget_cancelled" if budget_halted else "succeeded",
            )

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
    if seeded_planner_cost <= 0.0 and _has_nonzero_usage(seeded_planner_usage):
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
    if plan_approved is True:
        # B4: seed ledger with pause-turn planner spend; do not re-bill (keep
        # live planner_usage empty so `_emit_planner_receipt` stays quiet).
        planner_cost = seeded_planner_cost
        if prior_receipt is None:
            # Legacy pause row: the B4 seed is the only record of the spend the
            # pause terminal already charged.
            ledger.hold_billed_floor(planner_cost)
    ledger.settle(
        _PLANNER_ID,
        role="orchestrator",
        usage=seeded_planner_usage if plan_approved is True else planner_usage,
        cost_usd=planner_cost,
        already_billed=plan_approved is True,
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
        # Declined on resume: no fan-out, a labeled (non-error) synthesis.
        # Include any planner usage from a prior real-provider plan pass.
        async for event in _planner_receipt():
            yield event
        async for event in _finalize_synthesis(
            synthesis=(
                "Synthesis: the research plan was declined; no sub-agents were run."
            ),
            worker_usages=[planner_usage],
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
    decision = _admit(
        estimate_usd=estimate, settings=settings, budget_headroom_usd=budget_headroom_usd
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
    queue: asyncio.Queue[
        ProviderEvent | _WorkerSentinel | _WorkerPause | _WorkerSubstituted
    ] = asyncio.Queue(maxsize=_FANOUT_QUEUE_MAXSIZE)
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
    source_remapper = _SourceIdRemapper()

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
        # B16: any externally visible progress blocks transparent fallback.
        visible_progress = False

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
            nonlocal visible_progress
            last_tool_name = "unknown"
            last_tool_label: str | None = None
            reasoning_parts: list[str] = []
            tool_transcript: list[dict[str, Any]] = []
            async for event in run_agent_loop(
                make_stream=make_stream,
                settings=settings,
                allowed_tools=_WORKER_ALLOWED_TOOLS,
                # Worker subagents never spend the empty-reply retry (amendment
                # B): synthesis / the deterministic aggregate is the recovery.
                allow_empty_retry=False,
                # FL-04: nor may a worker ship static filler as a finding. With
                # the filler suppressed `answer_parts` comes back genuinely
                # empty, which is what FL-05 marks as failed.
                inject_empty_fallback=False,
            ):
                if _event_shows_external_progress(event):
                    visible_progress = True
                if isinstance(event, AnswerDelta):
                    text = source_remapper.rewrite_answer_text(event.text, subagent_id)
                    answer_parts.append(text)
                    if text != event.text:
                        event = replace(event, text=text)
                if isinstance(event, Sources):
                    event = source_remapper.remap_sources(event, subagent_id)
                    for item in event.items:
                        source_ids.append(str(item.id))
                if isinstance(event, Complete):
                    if event.substitution is not None:
                        sub_code = event.substitution
                        sub_provider = event.substituted_provider
                        sub_model = event.substituted_model
                        sub_label = event.substituted_display_label
                    elif used_fallback:
                        # FL-22: stamp the served route onto the relayed Complete.
                        # The mid-flight kill gate derives its pricer from this
                        # field, so without it the provisional ledger sampled a
                        # fallback-served worker at the primary rate.
                        _stamp_fallback_route()
                        event = replace(
                            event,
                            substitution=sub_code or "provider_fallback",
                            substituted_provider=sub_provider,
                            substituted_model=sub_model,
                            substituted_display_label=sub_label,
                        )
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
                    # B12: flush any held citation fragment into the partial.
                    tail = source_remapper.flush_answer_carry(subagent_id)
                    if tail:
                        answer_parts.append(tail)
                        await queue.put(
                            _tag(AnswerDelta(text=tail, subagent_id=subagent_id), subagent_id)
                        )
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
                            used_fallback=used_fallback,
                        )
                    )
                    return True
                await queue.put(_tag(event, subagent_id))
            # B12: flush held citation fragment after the provider stream ends.
            tail = source_remapper.flush_answer_carry(subagent_id)
            if tail:
                answer_parts.append(tail)
                await queue.put(
                    _tag(AnswerDelta(text=tail, subagent_id=subagent_id), subagent_id)
                )
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
                        # SAF-008 / BE-024 / B16: never retry after any externally
                        # visible progress — that concatenates two attempts and
                        # drops primary spend from the roll-up.
                        # FL-23: also refuse once usage has been BANKED. The retry
                        # REPLACES `usage` rather than summing it, so soundness
                        # must rest on the ledger, not on an adapter emitting a
                        # visible event before its first `UsageUpdate`.
                        if (
                            not visible_progress
                            and not _has_nonzero_usage(usage)
                            and fallback_make_stream_for is not None
                            and is_retryable(exc)
                        ):
                            if isinstance(exc, AppError) and exc.envelope.code == "RATE_LIMITED":
                                sub_code = "rate_limited"
                            else:
                                sub_code = "provider_fallback"
                            used_fallback = True
                            _stamp_fallback_route()
                            # FL-22: tell the kill gate before the fallback stream
                            # puts anything, so its provisional samples price on
                            # the route that serves them.
                            await queue.put(_WorkerSubstituted(subagent_id))
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
                    if not worker_failed and main_answer_is_empty(
                        "".join(answer_parts)
                    ):
                        # FL-05: a worker that wrote no prose produced no finding.
                        # Reporting it `succeeded` inflated the completed count and
                        # left `partial` False on a run that lost a whole step.
                        # Reuses the existing `failed` literal deliberately — a
                        # sixth SubagentOutcome would fail open on the live FE.
                        _log.warning(
                            "agentic.worker_no_prose", subagent_id=subagent_id
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
                        ledger.settle(
                            subagent_id,
                            role="worker",
                            usage=usage,
                            cost_usd=failed_cost,
                            outcome="failed",
                        )
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
                        ledger.settle(
                            subagent_id, role="worker", usage=usage, cost_usd=cost
                        )
        except asyncio.CancelledError:
            # Budget mid-flight kill (or outer teardown): emit a terminal done
            # for every started worker so the FE never shows a green check for
            # a cancelled row (FE-002). Snapshot usage into the run ledger so
            # already-reported spend survives into the final Complete (SAF-005).
            # Non-budget cancels (stop/disconnect/teardown) use outcome="stopped"
            # so failures stay distinguishable from budget_cancelled.
            # B23: non-blocking put — consumer may have stopped draining.
            if worker_started:
                cancel_cost = _price(usage) if _has_nonzero_usage(usage) else 0.0
                _queue_put_nowait_drop_oldest(
                    queue,
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
                    ),
                )
                ledger.settle(
                    subagent_id,
                    role="worker",
                    usage=usage,
                    cost_usd=cancel_cost,
                    outcome="budget_cancelled" if budget_halted else "stopped",
                )
            raise
        finally:
            # B23: sentinel must not block teardown on a full queue.
            _queue_put_nowait_drop_oldest(queue, _WorkerSentinel(subagent_id))

    tasks = [
        asyncio.create_task(_run_worker(index, subagent_id, label, sub_question))
        for index, subagent_id, label, sub_question in worker_meta
    ]
    # Mid-flight kill (T5 / B3): the ledger already holds planner actuals
    # (BE-014), takes provisional UsageUpdate/Complete samples mid-flight, and
    # settles on each worker's `SubagentDone`; on a cap breach, cancel remaining
    # workers. `actual_cost` is the high-water mark of that total: an exact
    # settlement can come in BELOW its provisional sample, and the durable
    # checkpoint's cap floor must not fall when it does.
    actual_cost = planner_cost
    budget_halted = False
    # BE-005: at most one worker tool-HITL pause per fan-out (first wins).
    # Sibling policy = wait for others to finish before surfacing AwaitingApproval.
    worker_pause: _WorkerPause | None = None
    # AR-008: workers that already substituted use the fallback pricer for
    # provisional mid-flight ledger samples.
    fallback_priced_workers: set[str] = set()
    # AR-023: sibling pauses cancelled as superseded — not "succeeded".
    superseded_worker_ids: set[str] = set()

    def _price_pause(pause: _WorkerPause) -> float:
        if pause.used_fallback and fallback_cost_for_usage is not None:
            return fallback_cost_for_usage(pause.usage)
        return cost_for_usage(pause.usage)

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
            if isinstance(item, _WorkerSubstituted):
                # FL-22: internal marker only — never relayed to the client.
                fallback_priced_workers.add(item.subagent_id)
                continue
            if isinstance(item, _WorkerPause):
                pause_cost = _price_pause(item)
                if worker_pause is None:
                    worker_pause = item
                    # Settle the partial into the ledger so the pause cost is
                    # billed and the boundary receipt below accounts for it.
                    ledger.settle(
                        item.subagent_id,
                        role="worker",
                        usage=item.usage,
                        cost_usd=pause_cost,
                        outcome="stopped",
                    )
                    _maybe_budget_kill()
                else:
                    # H-003 / O-007 / B24: cancel orphaned sibling pauses.
                    # Track as superseded (not failed) so failed_worker_count
                    # stays honest; include partial_answer in synthesis.
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
                    # FL-09: close the row. Without a terminal the FE spins
                    # forever and the handler defaults the outcome to `succeeded`;
                    # without `substitution` it also prices and attributes a
                    # fallback-served loser on the PRIMARY binding (invariant 13).
                    yield SubagentDone(
                        subagent_id=item.subagent_id,
                        label=f"Worker {item.index + 1}",
                        role="worker",
                        usage=item.usage,
                        cost_usd=pause_cost,
                        outcome="cancelled",
                        substitution=(
                            "provider_fallback" if item.used_fallback else None
                        ),
                        substituted_provider=(
                            fallback_provider_id if item.used_fallback else None
                        ),
                        substituted_model=(
                            fallback_model_id if item.used_fallback else None
                        ),
                        substituted_display_label=(
                            fallback_display_label if item.used_fallback else None
                        ),
                    )
                    ledger.settle(
                        item.subagent_id,
                        role="worker",
                        usage=item.usage,
                        cost_usd=pause_cost,
                        outcome="cancelled",
                    )
                    superseded_workers += 1
                    superseded_worker_ids.add(item.subagent_id)
                    if item.partial_answer.strip():
                        results[item.subagent_id] = WorkerOutput(
                            subagent_id=item.subagent_id,
                            sub_question=item.sub_question,
                            answer=item.partial_answer,
                            source_ids=item.source_ids,
                        )
                    _maybe_budget_kill()
                continue
            # B3 / AR-008: provisional mid-flight ledger from tagged usage samples.
            # Prefer the fallback pricer once a worker has substituted.
            if isinstance(item, (UsageUpdate, Complete)) and item.subagent_id:
                sample = item.usage if isinstance(item, Complete) else item
                if (
                    isinstance(item, Complete)
                    and item.substitution is not None
                ):
                    fallback_priced_workers.add(item.subagent_id)
                pricer = (
                    fallback_cost_for_usage
                    if (
                        item.subagent_id in fallback_priced_workers
                        and fallback_cost_for_usage is not None
                    )
                    else cost_for_usage
                )
                # SAF-005: the sample also snapshots usage, so a mid-flight kill
                # still rolls this worker's tokens up even if its CancelledError
                # path loses the race. `observe` never downgrades a settled phase.
                ledger.observe(
                    item.subagent_id,
                    role="worker",
                    usage=sample,
                    cost_usd=pricer(sample),
                )
                _maybe_budget_kill()
            yield item
            if isinstance(item, SubagentDone) and item.role == "worker":
                ledger.settle(
                    item.subagent_id,
                    role="worker",
                    usage=item.usage,
                    cost_usd=(
                        item.cost_usd
                        if item.cost_usd is not None
                        else ledger.cost_of(item.subagent_id)
                    ),
                    outcome=item.outcome,
                )
                # Mid-run meter tick (estimate + mid + final; FE-011 / FE-012).
                # A display tick, so it carries no receipt (AC-02) and shows only
                # EXACTLY settled spend — never a provisional sibling sample.
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
            subagent_id=worker_pause.subagent_id,
        )
        # FL-10: attribute the pause unconditionally. Hanging the ledger write
        # off the partial-answer guard silently dropped a blank-partial pause's
        # tokens from the run total.
        pause_cost = ledger.cost_of(
            worker_pause.subagent_id, _price_pause(worker_pause)
        )
        ledger.settle(
            worker_pause.subagent_id,
            role="worker",
            usage=worker_pause.usage,
            cost_usd=pause_cost,
            outcome="budget_cancelled",
        )
        # FL-10: this worker is never resumed, so it needs its own terminal — the
        # handler only repairs unfinished rows on stop / pause, and this turn ends
        # `done`, leaving the row on the `succeeded` default.
        yield SubagentDone(
            subagent_id=worker_pause.subagent_id,
            label=f"Worker {worker_pause.index + 1}",
            role="worker",
            usage=worker_pause.usage,
            cost_usd=pause_cost,
            outcome="budget_cancelled",
            substitution=(
                "provider_fallback" if worker_pause.used_fallback else None
            ),
            substituted_provider=(
                fallback_provider_id if worker_pause.used_fallback else None
            ),
            substituted_model=(
                fallback_model_id if worker_pause.used_fallback else None
            ),
            substituted_display_label=(
                fallback_display_label if worker_pause.used_fallback else None
            ),
        )
        if worker_pause.partial_answer.strip():
            results[worker_pause.subagent_id] = WorkerOutput(
                subagent_id=worker_pause.subagent_id,
                sub_question=worker_pause.sub_question,
                answer=worker_pause.partial_answer,
                source_ids=worker_pause.source_ids,
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
        cont = AgenticContinuation(
            phase="worker",
            paused_subagent_id=worker_pause.subagent_id,
            user_text=effective_user_text,
            plan=tuple(sub_questions),
            completed_workers=tuple(completed_states),
            planner_usage=(
                seeded_planner_usage
                if plan_approved is True and _has_nonzero_usage(seeded_planner_usage)
                else planner_usage
            ),
            planner_cost_usd=planner_cost,
            budget_halted=budget_halted,
            failed_workers=failed_workers,
            actual_cost_usd=actual_cost,
            paused_worker_index=worker_pause.index,
            paused_sub_question=worker_pause.sub_question,
            partial_answer=worker_pause.partial_answer,
            partial_reasoning=worker_pause.partial_reasoning,
            source_ids=worker_pause.source_ids,
            source_catalog=tuple(source_remapper.merged_items()),
            tool_transcript=worker_pause.tool_transcript,
            emitted_answer_chars=worker_pause.emitted_answer_chars,
            clarifications=tuple(bound_records),
            orchestration_mode="deep_research",
            paused_worker_usage=worker_pause.usage,
            paused_worker_cost_usd=ledger.cost_of(
                worker_pause.subagent_id, _price_pause(worker_pause)
            ),
            paused_worker_used_fallback=worker_pause.used_fallback,
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
            subagent_id=worker_pause.subagent_id,
            continuation=serialize_continuation(cont),
        )
        return

    ordered_outputs = [results[sid] for _, sid, _, _ in worker_meta if sid in results]
    # Mid-stream remapper already assigned global citation ids (B12) — do not
    # remap again in worker-plan order (that swapped ownership vs live markers).
    merged_sources = source_remapper.merged_items()
    # In-turn structured artifact refs (plan 02) — handed to the aggregator as
    # schema-shaped DATA rather than raw telephone stuffing.
    ordered_artifacts = aggregate.build_artifacts(
        ordered_outputs, max_artifacts=settings.agentic_max_workers
    )
    # Fold planner into run totals. On plan-approved resume, live planner_usage
    # is empty — fold seeded pause-turn usage for Complete roll-up (B4).
    ledger_planner_usage = (
        seeded_planner_usage
        if plan_approved is True and _has_nonzero_usage(seeded_planner_usage)
        else planner_usage
    )
    ordered_usages = [
        _restored_usage(ledger.usage_of(sid))
        for _, sid, _, _ in worker_meta
        if ledger.phase(sid) is not None
    ]
    ordered_usages.append(ledger_planner_usage)
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
                # Sibling of FL-19-b on the deterministic-synthesis path: a judge
                # crash must be disclosed rather than shipping a bare draft that
                # reads as verified.
                synthesis = verifier.compose_verified_answer(
                    draft, verdict="pass", report="", incomplete_samples=True
                )
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
                or _verification_degraded(verifier_result, verifier_outcome)
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
