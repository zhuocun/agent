"""One worker adapter over `run_agent_loop` (AC-09).

A deep-research worker used to be TWO lifecycle engines: a fresh worker ran under
`orchestrator._run_worker._consume`, a resumed one under
`_resume_worker_continuation._drain`. Each carried its own copy of the same seven
concerns — event tagging, citation rewriting, transcript capture, retryable
fallback, usage folding, pricing on the route that actually served, and terminal
classification — and they had already drifted: only the fresh one stamped the
served route onto its relayed `Complete`, only the fresh one failed a worker that
wrote no prose, and each did its own cost arithmetic.

`WorkerRunner` is that one engine, and everything that differs between a fresh
worker and a resumed one lives in which seed it is handed (see `FreshWorkerSeed`
and `ResumedWorkerSeed`).

Two boundaries the runner deliberately does NOT cross:

1. **Scheduling.** The bounded queue, the semaphore, task creation and
   cancellation stay in the orchestrator. The runner is one worker's stream.
2. **Terminals.** `WorkerOutcome.done_event` carries the `SubagentDone` rather
   than the runner yielding it, because a cancelled worker still owes the wire a
   terminal and that put must not block on a queue nobody is draining. Likewise
   the runner produces a pause's FACTS and the phase owner produces its
   `AwaitingApproval`, since only the phase owner can serialize a continuation.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Collection, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Literal, cast

import structlog

from app.agentic.budget import BudgetGate
from app.agentic.retry import is_retryable_provider_error
from app.agentic.sources import SourceNamespace
from app.config import Settings
from app.errors import AppError
from app.observability.tracing import SpanSettlement, invoke_agent_span
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    Sources,
    StatusUpdate,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.runtime.answer_policy import main_answer_is_empty
from app.runtime.bounds import RunTripwire
from app.runtime.context import ServedRoute
from app.runtime.loop_state import StopReason
from app.runtime.run_receipt import CostLedger, UsageTotals
from app.schemas.common import SubstitutionReasonCode
from app.tools.agent_loop import (
    TOOL_CALL_ID_NAMESPACE_SEP,
    MakeStream,
    run_agent_loop,
)
from app.tools.protocol import ToolApprovalState, ToolRunStatus

_log = structlog.get_logger(__name__)

# Build a per-subagent `MakeStream` for the given user prompt. Optional keyword
# ``allowed_tools`` scopes which registry tools are advertised (and should match
# the agent-loop execute allowlist). ``None`` = full turn set; empty = none.
StreamFactory = Callable[..., MakeStream]

# Computes the USD cost of an accumulated usage for the active binding.
CostForUsage = Callable[[UsageUpdate], float]

# Whether a provider exception is worth one fallback-route retry.
IsRetryable = Callable[[BaseException], bool]

WORKER_ROLE = "worker"

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
WORKER_PROD_HITL_TOOLS: frozenset[str] = frozenset({"request_user_confirmation"})
WORKER_FAKE_HITL_TOOLS: frozenset[str] = frozenset({"calendar_create_event"})
WORKER_ALLOWED_TOOLS: frozenset[str] = WORKER_PROD_HITL_TOOLS | WORKER_FAKE_HITL_TOOLS

# Event types that carry an optional `subagent_id` and so can be stamped by
# `tag_event`. Orchestrator-only `SubagentStarted` / `SubagentDone` / `RunCost`
# are deliberately absent — the agent loop never emits those.
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


def tag_event(event: ProviderEvent, subagent_id: str) -> ProviderEvent:
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
    if isinstance(event, (ToolResult, AwaitingApproval)):
        return replace(
            event,
            subagent_id=subagent_id,
            tool_call_id=namespace_tool_call_id(subagent_id, event.tool_call_id),
        )
    if isinstance(event, _TAGGABLE):
        return replace(event, subagent_id=subagent_id)
    return event


def sum_usages(usages: Sequence[UsageUpdate]) -> UsageUpdate:
    """Field-wise sum of usages → the run total (untagged final `Complete`)."""
    return UsageUpdate(
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        reasoning_tokens=sum(u.reasoning_tokens for u in usages),
        cached_input_tokens=sum(u.cached_input_tokens for u in usages),
    )


def fold_usage(event: ProviderEvent, current: UsageUpdate) -> UsageUpdate:
    """Track a subagent's latest usage as its stream advances.

    REPLACE, not accumulate: the provider reports a running total, so a retry on
    another route replaces this attempt's counts rather than adding to them —
    which is why banked usage refuses a fallback retry (FL-23).
    """
    if isinstance(event, Complete):
        return event.usage
    if isinstance(event, UsageUpdate):
        return event
    return current


def has_nonzero_usage(usage: UsageUpdate) -> bool:
    return bool(
        usage.input_tokens
        or usage.output_tokens
        or usage.reasoning_tokens
        or usage.cached_input_tokens
    )


def event_shows_external_progress(event: ProviderEvent) -> bool:
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


def tool_transcript_part(
    event: ToolCall | ToolResult, subagent_id: str
) -> dict[str, Any]:
    """Durable transcript row for one worker tool event (H-010 checkpoint).

    `tool_results_from_transcript` below is the inverse; the pair is one codec,
    and both halves share this module's `namespace_tool_call_id`.
    """
    common = {
        "name": event.name,
        "label": event.label,
        "status": event.status,
        "approvalState": event.approval_state,
        "subagentId": subagent_id,
    }
    if isinstance(event, ToolCall):
        return {
            "type": "tool_call",
            "id": namespace_tool_call_id(subagent_id, event.id),
            "input": dict(event.input or {}),
            **common,
        }
    return {
        "type": "tool_result",
        "toolCallId": namespace_tool_call_id(subagent_id, event.tool_call_id),
        "summary": event.summary,
        "output": dict(event.output or {}),
        "error": event.error,
        **common,
    }


_TOOL_RUN_STATUSES: frozenset[str] = frozenset(
    {"running", "succeeded", "failed", "cancelled", "awaiting_approval"}
)
_TOOL_APPROVAL_STATES: frozenset[str] = frozenset(
    {"not_required", "pending", "approved", "rejected"}
)


def _str_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def tool_results_from_transcript(
    transcript: Sequence[dict[str, Any]], *, subagent_id: str
) -> list[ToolResult]:
    """Read the settled tool results back out of a durable transcript (H-010).

    The inverse of `tool_transcript_part`, and the reason a resumed worker can
    hand the agent loop every tool result the pause turn already settled instead
    of re-running those calls. Rows are dicts decoded from JSON, so unknown
    status / approval values fall back to the neutral defaults rather than
    widening `ToolResult`'s literals.
    """
    results: list[ToolResult] = []
    for part in transcript:
        if part.get("type") != "tool_result":
            continue
        status = part.get("status")
        approval = part.get("approvalState")
        output = part.get("output")
        results.append(
            ToolResult(
                tool_call_id=str(part.get("toolCallId") or ""),
                name=str(part.get("name") or ""),
                label=_str_or_none(part.get("label")),
                status=cast(
                    ToolRunStatus,
                    status if status in _TOOL_RUN_STATUSES else "succeeded",
                ),
                approval_state=cast(
                    ToolApprovalState,
                    approval if approval in _TOOL_APPROVAL_STATES else "not_required",
                ),
                summary=_str_or_none(part.get("summary")),
                output=dict(output) if isinstance(output, dict) else {},
                error=_str_or_none(part.get("error")),
                subagent_id=subagent_id,
            )
        )
    return results


# --- seeds --------------------------------------------------------------------


@dataclass(frozen=True)
class FreshWorkerSeed:
    """A worker that has not run yet: an identity and a prompt, nothing restored.

    The `prior_*` class variables are the empty restore state, so the runner reads
    one set of names for either seed instead of branching on which it got.

    `fail_on_empty_prose` is True here because a fresh worker that wrote nothing
    produced no finding (FL-05); reporting it `succeeded` inflated the completed
    count and left `partial` False on a run that lost a whole step.
    """

    index: int
    subagent_id: str
    label: str
    sub_question: str
    prompt: str

    fail_on_empty_prose: ClassVar[bool] = True
    log_prefix: ClassVar[str] = "agentic.worker"
    prior_answer: ClassVar[str] = ""
    prior_reasoning: ClassVar[str] = ""
    prior_source_ids: ClassVar[tuple[str, ...]] = ()
    prior_tool_transcript: ClassVar[tuple[dict[str, Any], ...]] = ()
    prior_tool_results: ClassVar[tuple[ToolResult, ...]] = ()
    prior_usage: ClassVar[UsageUpdate] = UsageUpdate()
    prior_cost_usd: ClassVar[float] = 0.0
    prior_emitted_answer_chars: ClassVar[int] = 0
    pinned_to_fallback: ClassVar[bool] = False
    approved_call_ids: ClassVar[Collection[str] | None] = None


@dataclass(frozen=True)
class ResumedWorkerSeed:
    """The same worker, continued after a tool-approval pause (BE-005).

    Everything the pause turn durably recorded comes back here: the partial answer
    and reasoning, the citations it published, its tool transcript (including the
    settled resume result), and the usage and cost it was already billed for.
    `pinned_to_fallback` (B6) is the route that served the pause — a resume must
    not silently switch bindings mid-worker.

    `fail_on_empty_prose` is False: `prior_answer` already reached the user on the
    paused turn, so an empty resume increment is not a worker without a finding.
    """

    index: int
    subagent_id: str
    label: str
    sub_question: str
    prompt: str
    server_approved_call_ids: frozenset[str] = frozenset()
    prior_tool_results: tuple[ToolResult, ...] = ()
    prior_answer: str = ""
    prior_reasoning: str = ""
    prior_source_ids: tuple[str, ...] = ()
    prior_tool_transcript: tuple[dict[str, Any], ...] = ()
    prior_usage: UsageUpdate = field(default_factory=UsageUpdate)
    prior_cost_usd: float = 0.0
    prior_emitted_answer_chars: int = 0
    pinned_to_fallback: bool = False

    fail_on_empty_prose: ClassVar[bool] = False
    log_prefix: ClassVar[str] = "agentic.resume_worker"

    @property
    def approved_call_ids(self) -> Collection[str] | None:
        return set(self.server_approved_call_ids)


WorkerSeed = FreshWorkerSeed | ResumedWorkerSeed


# --- routes and budget gate ---------------------------------------------------


@dataclass(frozen=True)
class WorkerRoutes:
    """The primary route, the optional fallback, and how to price either one.

    Both engines used to answer "which binding served, so which pricer and which
    attribution?" with their own copy of the same four-way conditional. This is
    that answer, once: `price()` for the money and `served()` for the identity,
    both keyed on the same `used_fallback` the runner tracks.
    """

    make_stream_for: StreamFactory
    cost_for_usage: CostForUsage
    primary: ServedRoute | None = None
    fallback_make_stream_for: StreamFactory | None = None
    fallback_cost_for_usage: CostForUsage | None = None
    fallback_provider_id: str | None = None
    fallback_model_id: str | None = None
    fallback_display_label: str | None = None
    is_retryable: IsRetryable = is_retryable_provider_error

    @property
    def has_fallback(self) -> bool:
        return self.fallback_make_stream_for is not None

    def price(self, usage: UsageUpdate, *, used_fallback: bool) -> float:
        """Price on the binding that actually served (FE-009 / BE-023 / SAF-006)."""
        if used_fallback and self.fallback_cost_for_usage is not None:
            return self.fallback_cost_for_usage(usage)
        return self.cost_for_usage(usage)

    def served(
        self,
        *,
        substitution: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> ServedRoute | None:
        """The route that served, as ONE derived route carrying its reason.

        `None` when the caller supplied no primary route (direct unit calls).
        """
        if self.primary is None:
            return None
        if substitution is None:
            return self.primary
        return self.primary.substituted(
            provider_id=provider_id or self.fallback_provider_id or "",
            model_id=model_id or self.fallback_model_id or "",
            reason=substitution,
        )


# --- outcomes -----------------------------------------------------------------


@dataclass(frozen=True)
class WorkerResult:
    """What one worker's stream produced and spent, whatever its outcome.

    `usage` / `cost_usd` are CUMULATIVE (a resumed worker's prior spend plus this
    session's), priced on the route that served; `session_usage` is this
    invocation alone, which is what a resume's incremental cap check needs.
    """

    subagent_id: str
    index: int
    label: str
    sub_question: str
    answer: str
    reasoning: str
    source_ids: tuple[str, ...]
    tool_transcript: tuple[dict[str, Any], ...]
    usage: UsageUpdate
    cost_usd: float
    session_usage: UsageUpdate
    session_cost_usd: float
    route: ServedRoute | None
    used_fallback: bool
    substitution: SubstitutionReasonCode | None
    substituted_provider: str | None
    substituted_model: str | None
    substituted_display_label: str | None
    budget_halted: bool
    emitted_answer_chars: int


@dataclass(frozen=True)
class WorkerCompleted:
    """The worker finished its stream. `outcome` is `budget_cancelled` when its
    own gate halted it mid-stream, `succeeded` otherwise."""

    result: WorkerResult
    done_event: SubagentDone
    outcome: Literal["succeeded", "budget_cancelled"] = "succeeded"


@dataclass(frozen=True)
class WorkerPaused:
    """The worker stopped at a tool-approval gate.

    `done_event` is None: a paused worker is deliberately non-terminal, so the FE
    row stays open and `mark_unfinished_subagents_paused` can claim it (B15). The
    pause's `AwaitingApproval` belongs to the phase owner, the only layer that can
    serialize the continuation it must carry.
    """

    result: WorkerResult
    tool_call_id: str
    tool_name: str
    tool_label: str | None = None
    done_event: None = None


@dataclass(frozen=True)
class WorkerFailed:
    """The worker raised (on both routes, or on one it could not retry), or wrote
    no prose at all (FL-05). Partial usage is still billed."""

    result: WorkerResult
    done_event: SubagentDone
    outcome: Literal["failed"] = "failed"


@dataclass(frozen=True)
class WorkerCancelled:
    """The worker was cancelled — by the budget kill, a run-bound trip, a Stop,
    or teardown.

    `done_event` exists so a cancelled row still reaches a terminal (FE-002), but
    the caller must enqueue it WITHOUT awaiting: the consumer may already have
    stopped draining.
    """

    result: WorkerResult
    done_event: SubagentDone
    outcome: Literal["budget_cancelled", "cancelled", "stopped"] = "stopped"


WorkerOutcome = WorkerCompleted | WorkerPaused | WorkerFailed | WorkerCancelled

# Every label a worker row can close with.
WorkerOutcomeLabel = Literal[
    "succeeded", "failed", "cancelled", "budget_cancelled", "stopped"
]

# WHY a worker's loop ended, per closing label (`loop_state.StopReason`). The
# wire label says what the row is; the stop reason says what ended it, and only
# the reason names the counted event a trace consumer can tune a bound against.
# `cancelled` is absent because it is the one label whose reason is not implied
# by the label — see `_worker_stop_reason`.
_LABEL_STOP_REASONS: dict[WorkerOutcomeLabel, StopReason] = {
    # A loop that ran to its own final message. Acceptance is decided elsewhere
    # (doc §1.3 decision 2), which is exactly what `protocol_stop` means.
    "succeeded": "protocol_stop",
    "failed": "provider_error",
    "budget_cancelled": "usd_cap_exceeded",
    "stopped": "user_stopped",
}


def _worker_stop_reason(
    label: WorkerOutcomeLabel, tripped: StopReason | None
) -> StopReason:
    """The stop reason this worker's span reports for `label`.

    `cancelled` is the label `_finish_cancelled` picks precisely BECAUSE a run
    bound tripped, so the latch names which bound — the whole point of recording
    a reason instead of a label. Every other label implies its own reason, and
    the run's latch is deliberately NOT consulted for them: a worker that
    finished before a sibling tripped the run did not stop for that trip.
    """
    if label == "cancelled":
        return tripped or "user_stopped"
    return _LABEL_STOP_REASONS[label]


@dataclass
class _WorkerState:
    """Mutable working state for one worker invocation."""

    answer_parts: list[str]
    reasoning_parts: list[str]
    source_ids: list[str]
    tool_transcript: list[dict[str, Any]]
    used_fallback: bool
    substitution: SubstitutionReasonCode | None
    # This invocation's usage only. Pre-pause spend stays immutable on the seed so
    # `fold_usage`'s replace semantics cannot erase it (B2).
    session_usage: UsageUpdate = field(default_factory=UsageUpdate)
    substituted_provider: str | None = None
    substituted_model: str | None = None
    substituted_display_label: str | None = None
    visible_progress: bool = False
    budget_halted: bool = False
    failed: bool = False
    # (namespaced tool_call_id, tool name, tool label) once a pause is recorded.
    paused: tuple[str, str, str | None] | None = None
    last_tool_name: str = "unknown"
    last_tool_label: str | None = None

    @classmethod
    def restored(cls, seed: WorkerSeed) -> _WorkerState:
        """H-010: the pause turn's answer, reasoning, citations and transcript come
        back so a nested pause checkpoints the whole worker rather than only its
        increment. The answer text is NOT re-emitted — it already reached the user
        on the paused turn and is persisted on that row.
        """
        return cls(
            answer_parts=[seed.prior_answer] if seed.prior_answer else [],
            reasoning_parts=[seed.prior_reasoning] if seed.prior_reasoning else [],
            source_ids=list(seed.prior_source_ids),
            tool_transcript=[dict(part) for part in seed.prior_tool_transcript],
            # B6: a resume stays on the binding that served the pause.
            used_fallback=seed.pinned_to_fallback,
            substitution="provider_fallback" if seed.pinned_to_fallback else None,
        )


class WorkerRunner:
    """The sole fresh/resumed worker adapter over `run_agent_loop`.

    One instance drives ONE worker: `run(seed)` yields that worker's events, and
    once the iterator is exhausted `outcome` is the typed fact the phase owner
    acts on. `outcome` stays None when `run` was cancelled before it started,
    which is exactly when a worker owes the wire no terminal.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        routes: WorkerRoutes,
        sources: SourceNamespace,
        ledger: CostLedger,
        budget_gate: BudgetGate | None = None,
        allowed_tools: Collection[str] = WORKER_ALLOWED_TOOLS,
        is_run_budget_halted: Callable[[], bool] = lambda: False,
        tripwire: RunTripwire | None = None,
    ) -> None:
        self._settings = settings
        self._routes = routes
        self._sources = sources
        self._ledger = ledger
        self._budget_gate = budget_gate
        self._allowed_tools = allowed_tools
        self._is_run_budget_halted = is_run_budget_halted
        # This worker's handle on the RUN's trip conditions (doc §11.8). Passed
        # straight through to the agent loop, which owns the degrade; the runner
        # only reads the latch to label a cancelled row honestly. None = the run
        # set no bounds, so nothing changes.
        self._tripwire = tripwire
        self._outcome: WorkerOutcome | None = None
        self._seed: WorkerSeed | None = None
        self._state = _WorkerState.restored(FreshWorkerSeed(0, "", "", "", ""))
        # A handle over no span until `run` opens one; settling it is a no-op.
        self._span = SpanSettlement()

    @property
    def outcome(self) -> WorkerOutcome | None:
        """This worker's typed outcome, or None if `run` never started."""
        return self._outcome

    async def run(self, seed: WorkerSeed) -> AsyncGenerator[ProviderEvent, None]:
        """Yield this worker's `SubagentStarted` and its tagged stream events.

        The terminal `SubagentDone` is NOT yielded — it rides on
        `outcome.done_event` so cancellation and completion have one emit owner.

        Typed as the async GENERATOR it is (an `AsyncIterator[ProviderEvent]`,
        narrowed) so a caller can `aclosing` it and get the cancelled settlement
        deterministically instead of whenever the loop finalizes the generator.
        """
        self._seed = seed
        self._state = _WorkerState.restored(seed)
        with invoke_agent_span(
            subagent_id=seed.subagent_id, role=WORKER_ROLE, label=seed.label
        ) as span:
            self._span = span
            try:
                # Inside the guard: a stop delivered while this very event is in
                # flight has already OPENED the row, so that row owes the wire a
                # terminal exactly as a mid-stream cancel does. `outcome` stays
                # None only when `run` never started at all.
                yield SubagentStarted(
                    subagent_id=seed.subagent_id, label=seed.label, role=WORKER_ROLE
                )
                async for event in self._attempt():
                    yield event
            except (asyncio.CancelledError, GeneratorExit):
                # AR-005: Stop/shutdown is not an ordinary worker failure. The row
                # still owes a terminal, so settle it, then propagate.
                self._outcome = self._finish_cancelled()
                raise
            self._outcome = self._finish()

    # --- execution ------------------------------------------------------------

    async def _attempt(self) -> AsyncIterator[ProviderEvent]:
        """Drive the primary route, then at most one fallback route (M4 / O-008)."""
        seed, state = self._require_seed(), self._state
        fallback = self._routes.fallback_make_stream_for
        try:
            async for event in self._relay(self._first_stream()):
                yield event
            return
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except BaseException as exc:
            if fallback is None or not self._may_fall_back(exc):
                _log.warning(
                    f"{seed.log_prefix}_failed",
                    subagent_id=seed.subagent_id,
                    error=str(exc),
                )
                state.failed = True
                return
            state.used_fallback = True
            state.substitution = (
                "rate_limited"
                if isinstance(exc, AppError) and exc.envelope.code == "RATE_LIMITED"
                else "provider_fallback"
            )
        try:
            async for event in self._relay(
                fallback(seed.prompt, allowed_tools=self._allowed_tools)
            ):
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except BaseException as retry_exc:
            _log.warning(
                f"{seed.log_prefix}_fallback_failed",
                subagent_id=seed.subagent_id,
                error=str(retry_exc),
            )
            state.failed = True

    def _first_stream(self) -> MakeStream:
        """B6: a resume pinned to the fallback skips the primary entirely."""
        seed, routes = self._require_seed(), self._routes
        if self._state.used_fallback and routes.fallback_make_stream_for is not None:
            factory = routes.fallback_make_stream_for
        else:
            factory = routes.make_stream_for
        return factory(seed.prompt, allowed_tools=self._allowed_tools)

    def _may_fall_back(self, exc: BaseException) -> bool:
        """Whether this failure may be retried transparently on the other route.

        SAF-008 / BE-024 / B16: never after externally visible progress — that
        concatenates two attempts into one answer. FL-23: never after usage has
        been BANKED either, because the retry REPLACES this attempt's counts
        rather than summing them, so soundness rests on the ledger and not on an
        adapter happening to emit a visible event before its first `UsageUpdate`.
        """
        state = self._state
        return (
            not state.visible_progress
            and not has_nonzero_usage(state.session_usage)
            and not state.used_fallback
            and self._routes.has_fallback
            and self._routes.is_retryable(exc)
        )

    async def _relay(self, make_stream: MakeStream) -> AsyncIterator[ProviderEvent]:
        """Relay one agent loop, capturing everything that outlives it."""
        seed, state = self._require_seed(), self._state
        sid = seed.subagent_id
        async for event in run_agent_loop(
            make_stream=make_stream,
            settings=self._settings,
            allowed_tools=self._allowed_tools,
            server_approved_call_ids=seed.approved_call_ids,
            initial_tool_results=list(seed.prior_tool_results) or None,
            # Worker subagents never spend the empty-reply retry (amendment B):
            # synthesis / the deterministic aggregate is the recovery here.
            allow_empty_retry=False,
            # FL-04: nor may a worker ship static filler as a research finding.
            # With the filler suppressed the answer comes back genuinely empty,
            # which is what FL-05 marks as failed.
            inject_empty_fallback=False,
            tripwire=self._tripwire,
        ):
            if event_shows_external_progress(event):
                state.visible_progress = True
            if isinstance(event, AnswerDelta):
                text = self._sources.rewrite_answer_text(event.text, sid)
                state.answer_parts.append(text)
                if text != event.text:
                    event = replace(event, text=text)
            if isinstance(event, Sources):
                event = self._sources.remap_sources(event, sid)
                state.source_ids.extend(str(item.id) for item in event.items)
            if isinstance(event, Complete):
                event = self._stamp_route(event)
            if isinstance(event, ToolCall):
                state.last_tool_name = event.name
                state.last_tool_label = event.label
            if isinstance(event, (ToolCall, ToolResult)):
                state.tool_transcript.append(tool_transcript_part(event, sid))
            if isinstance(event, ReasoningDelta):
                state.reasoning_parts.append(event.text)
            state.session_usage = fold_usage(event, state.session_usage)
            if isinstance(event, (UsageUpdate, Complete)):
                # B3 / AR-008 / SAF-005: a provisional sample priced on the route
                # serving it, so the run's kill gate sees this worker's spend
                # before it settles and a mid-flight kill still rolls its tokens
                # up. `observe` never downgrades an already-settled phase.
                self._ledger.observe(
                    sid,
                    role=WORKER_ROLE,
                    usage=sum_usages([seed.prior_usage, state.session_usage]),
                    cost_usd=seed.prior_cost_usd + self._session_cost(),
                )
            if isinstance(event, AwaitingApproval):
                # BE-005: the pending ToolCall was already relayed. Record the
                # pause and stop — the phase owner surfaces the terminal.
                for held in self._flush_citation_tail(sid):
                    yield held
                state.paused = (
                    namespace_tool_call_id(sid, event.tool_call_id),
                    state.last_tool_name,
                    state.last_tool_label,
                )
                return
            if self._budget_gate is not None and not state.budget_halted:
                state.budget_halted = self._budget_gate.breached(self._session_cost())
            yield tag_event(event, sid)
            # B3: mirror `run_single` — stop draining once the cap is breached.
            if state.budget_halted and isinstance(event, (Complete, UsageUpdate)):
                break
        for held in self._flush_citation_tail(sid):
            yield held

    def _flush_citation_tail(self, sid: str) -> list[ProviderEvent]:
        """B12: a citation marker split across deltas is held until it completes,
        so whatever is still held at a pause or at end of stream has to be emitted
        and folded into the partial answer."""
        tail = self._sources.flush_answer_carry(sid)
        if not tail:
            return []
        self._state.answer_parts.append(tail)
        return [tag_event(AnswerDelta(text=tail), sid)]

    def _stamp_route(self, event: Complete) -> Complete:
        """Keep the relayed terminal honest about which binding served (FL-22).

        A provider that substituted on its own wins — it knows the served triple.
        Otherwise, when THIS runner fell back, stamp our own route: consumers (the
        kill gate's pricer, the handler's attribution) read the served route off
        this event, so leaving it bare priced and reported the primary.
        """
        state = self._state
        if event.substitution is not None:
            state.substitution = event.substitution
            state.substituted_provider = event.substituted_provider
            state.substituted_model = event.substituted_model
            state.substituted_display_label = event.substituted_display_label
            return event
        if not state.used_fallback:
            return event
        self._stamp_fallback_identity()
        return replace(
            event,
            substitution=state.substitution or "provider_fallback",
            substituted_provider=state.substituted_provider,
            substituted_model=state.substituted_model,
            substituted_display_label=state.substituted_display_label,
        )

    def _stamp_fallback_identity(self) -> None:
        """Fill any unknown served-route part from the configured fallback."""
        state, routes = self._state, self._routes
        if state.substituted_provider is None:
            state.substituted_provider = routes.fallback_provider_id
        if state.substituted_model is None:
            state.substituted_model = routes.fallback_model_id
        if state.substituted_display_label is None:
            state.substituted_display_label = routes.fallback_display_label

    # --- settlement -----------------------------------------------------------

    def _require_seed(self) -> WorkerSeed:
        assert self._seed is not None, "WorkerRunner.run() owns the seed"
        return self._seed

    def _session_cost(self) -> float:
        return self._routes.price(
            self._state.session_usage, used_fallback=self._state.used_fallback
        )

    def _result(self) -> WorkerResult:
        seed, state = self._require_seed(), self._state
        if state.used_fallback:
            self._stamp_fallback_identity()
        answer = "".join(state.answer_parts)
        session_cost = self._session_cost()
        return WorkerResult(
            subagent_id=seed.subagent_id,
            index=seed.index,
            label=seed.label,
            sub_question=seed.sub_question,
            answer=answer,
            reasoning="".join(state.reasoning_parts),
            # Deduplicated: a worker can publish the same global id twice, and
            # this tuple is a resume's citation floor, not an event log.
            source_ids=tuple(dict.fromkeys(state.source_ids)),
            tool_transcript=tuple(state.tool_transcript),
            usage=sum_usages([seed.prior_usage, state.session_usage]),
            cost_usd=seed.prior_cost_usd + session_cost,
            session_usage=state.session_usage,
            session_cost_usd=session_cost,
            route=self._routes.served(
                substitution=state.substitution,
                provider_id=state.substituted_provider,
                model_id=state.substituted_model,
            ),
            used_fallback=state.used_fallback,
            substitution=state.substitution,
            substituted_provider=state.substituted_provider,
            substituted_model=state.substituted_model,
            substituted_display_label=state.substituted_display_label,
            budget_halted=state.budget_halted,
            emitted_answer_chars=max(seed.prior_emitted_answer_chars, len(answer)),
        )

    def _close(self, result: WorkerResult, label: WorkerOutcomeLabel) -> SubagentDone:
        """Settle this phase and its span, and mint the row's terminal event.

        Usage is recorded for every label, failures included: partial primary or
        fallback spend is real money, and even a zero-token failure is a closed
        row the final roll-up must see (SAF-005).
        """
        self._ledger.settle(
            result.subagent_id,
            role=WORKER_ROLE,
            usage=result.usage,
            cost_usd=result.cost_usd,
            outcome=label,
        )
        self._span.settle(
            route=result.route,
            usage=UsageTotals.copy_from(result.usage),
            cost_usd=result.cost_usd,
            outcome=label,
            stop_reason=_worker_stop_reason(
                label, None if self._tripwire is None else self._tripwire.tripped
            ),
        )
        return SubagentDone(
            subagent_id=result.subagent_id,
            label=result.label,
            role=WORKER_ROLE,
            usage=result.usage,
            cost_usd=result.cost_usd,
            outcome=label,
            substitution=result.substitution,
            substituted_provider=result.substituted_provider,
            substituted_model=result.substituted_model,
            substituted_display_label=result.substituted_display_label,
        )

    def _finish(self) -> WorkerOutcome:
        """Classify a worker whose stream ended on its own terms."""
        seed, state = self._require_seed(), self._state
        result = self._result()
        if state.paused is not None:
            call_id, tool_name, tool_label = state.paused
            # The PHASE OWNER settles a pause: only it knows whether this pause
            # won the run's one continuation, was superseded by a sibling, or
            # arrived after the cap was already breached. The span closes now
            # either way — the trace should not lose a paused phase.
            self._span.settle(
                route=result.route,
                usage=UsageTotals.copy_from(result.usage),
                cost_usd=result.cost_usd,
                outcome="paused",
                stop_reason="awaiting_approval",
            )
            return WorkerPaused(result, call_id, tool_name, tool_label)
        if state.failed or (
            seed.fail_on_empty_prose and main_answer_is_empty(result.answer)
        ):
            if not state.failed:
                _log.warning("agentic.worker_no_prose", subagent_id=seed.subagent_id)
            return WorkerFailed(result, self._close(result, "failed"))
        label: Literal["succeeded", "budget_cancelled"] = (
            "budget_cancelled" if state.budget_halted else "succeeded"
        )
        return WorkerCompleted(result, self._close(result, label), outcome=label)

    def _finish_cancelled(self) -> WorkerCancelled:
        """Close a cancelled worker. A budget kill, a bound trip and a Stop stay
        distinguishable (FE-002), and either way its reported spend survives into
        the roll-up."""
        result = self._result()
        if not has_nonzero_usage(result.usage):
            result = replace(result, cost_usd=0.0)
        label: Literal["budget_cancelled", "cancelled", "stopped"]
        if self._state.budget_halted or self._is_run_budget_halted():
            label = "budget_cancelled"
        elif self._tripwire is not None and self._tripwire.tripped is not None:
            # A run bound cancelled this worker. Not `budget_cancelled` (no cap
            # was breached) and not `stopped` (nobody pressed Stop) — reusing
            # either would report one degrade channel as another.
            label = "cancelled"
        else:
            label = "stopped"
        return WorkerCancelled(result, self._close(result, label), outcome=label)
