"""One durable fold for a turn's provider events (AC-03).

Live delivery and the stopped/disconnect drain used to carry two independent
mutation trees over the same `ProviderEvent` union. They had already drifted:
the drain left a cancelled sibling's `tool_call` part at
`pending` + `cancelled` while the live gate flipped it to `rejected`. This module
is the single owner of that fold, so the two drivers cannot disagree again.

What belongs here: durable mutation only — reasoning, answer, status, sources,
tool transcript, subagent lifecycle, usage, `Complete` substitution, and the
latest receipt-bearing `RunCost`. `reduce` is pure in the sense that matters for
a fold: no I/O, no SSE, no control flow, no clock of its own (the caller injects
`now`), so the same `(state, event, now)` always produces the same state.

What does NOT belong here: delivery. SSE encoding, the reasoning wire gates,
planner-seed harvesting off reserved tool input, continuation pinning, pause
selection, and attribution projection stay with the live driver — a stopped
drain has no outbound frames and takes no pause hints, and that asymmetry is
exactly why they cannot be folded together.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.providers.protocol import (
    AnswerDelta,
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
from app.runtime.run_receipt import RunReceipt
from app.schemas.common import SubagentOutcome, SubstitutionReasonCode
from app.schemas.message import AgenticRunSummaryPart, ToolCallPart, ToolResultPart
from app.search.protocol import SourceItem


@dataclass
class ScopeState:
    """Accumulated durable content for one tagged scope (an agentic subagent).

    Mirrors the untagged single-stream accumulators but scoped to one subagent so
    the persisted parts can be grouped under a `subagent` marker. `cost_usd` /
    `usage` are filled from the matching `SubagentDone`.
    """

    label: str
    role: str
    reasoning: list[str] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    tool_parts: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    usage: UsageUpdate = field(default_factory=UsageUpdate)
    outcome: SubagentOutcome = "succeeded"
    # True once a `SubagentDone` has been folded in. Stop/disconnect uses this to
    # distinguish finished workers from ones that were still in flight when the
    # pump was cancelled (the orchestrator may have enqueued
    # `SubagentDone(stopped)` on its internal queue, but those never arrive).
    terminal: bool = False
    substitution: SubstitutionReasonCode | None = None
    substituted_provider: str | None = None
    substituted_model: str | None = None
    substituted_display_label: str | None = None
    # Per-worker web-search status/sources (FE-001).
    latest_status: tuple[str, str] | None = None
    search_items: list[Any] = field(default_factory=list)
    saw_sources: bool = False
    # FL-37: per-scope reasoning wall-clock (monotonic start, closed seconds).
    reasoning_started_at: float | None = None
    reasoning_duration_sec: float | None = None


@dataclass
class TurnState:
    """Every durable fact one turn's event fold produces.

    `agentic` decides whether a tagged event lands in its scope or in the flat
    untagged buffers; it is fixed for the turn. `started_at` is the monotonic
    base `first_answer_ms` and the reasoning clocks are measured against, so the
    reducer never reads a clock itself.
    """

    started_at: float = field(default_factory=time.monotonic)
    agentic: bool = False
    reasoning: list[str] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    tool_parts: list[dict[str, Any]] = field(default_factory=list)
    usage: UsageUpdate = field(default_factory=UsageUpdate)
    latest_status: tuple[str, str] | None = None
    search_items: list[SourceItem] = field(default_factory=list)
    # Whether a `Sources` event arrived at all — distinct from `search_items`
    # being empty, because the honesty rule (PRD 07 §4.3) still needs to know
    # that web search RAN. Set by a tagged event too (FL-35).
    saw_sources: bool = False
    first_answer_ms: int | None = None
    reasoning_started_at: float | None = None
    reasoning_duration_sec: float | None = None
    # Substitution metadata for `build_attribution`. `substitution` is seeded
    # from the router-side `auto_downgrade`; a provider-side `Complete` fallback
    # outranks it and brings the served-model triple with it.
    substitution: str | None = None
    substituted_provider: str | None = None
    substituted_model: str | None = None
    substituted_display_label: str | None = None
    # Tagged scopes in first-seen order so the persisted transcript groups
    # subagents deterministically.
    scope_order: list[str] = field(default_factory=list)
    scopes: dict[str, ScopeState] = field(default_factory=dict)
    run_summary: AgenticRunSummaryPart | None = None
    # The latest receipt-bearing `RunCost` (AC-02). The orchestrator emits
    # exactly one before each persistable boundary, so whichever one is banked
    # here at the terminal IS the run's accounting truth.
    receipt: RunReceipt | None = None
    # Internal, non-wire empty-reply retry analytics read off `Complete`.
    empty_retry: bool = False
    empty_retry_recovered: bool = False

    def scope(
        self, subagent_id: str, *, label: str | None = None, role: str | None = None
    ) -> ScopeState:
        """Fetch (or open) the scope for `subagent_id`.

        `SubagentStarted` always precedes a subagent's tagged content, so opening
        on miss is defensive — but it is the SAME defence on both drivers, which
        is the point.
        """
        existing = self.scopes.get(subagent_id)
        if existing is not None:
            return existing
        opened = ScopeState(label=label or subagent_id, role=role or "subagent")
        self.scopes[subagent_id] = opened
        self.scope_order.append(subagent_id)
        return opened

    def snapshot(self) -> dict[str, Any]:
        """A comparable projection of the durable facts, free of wall-clock.

        Two drivers folding the same events must land here identically. Measured
        durations are reported as "was it measured" rather than as seconds, so an
        equivalence assertion is about the fold and not about scheduling.
        """
        return {
            "reasoning": "".join(self.reasoning),
            "answer": "".join(self.answer),
            "toolParts": list(self.tool_parts),
            "usage": self.usage,
            "latestStatus": self.latest_status,
            "searchItems": list(self.search_items),
            "sawSources": self.saw_sources,
            "answered": self.first_answer_ms is not None,
            "reasoningMeasured": self.reasoning_duration_sec is not None,
            "substitution": (
                self.substitution,
                self.substituted_provider,
                self.substituted_model,
                self.substituted_display_label,
            ),
            "scopeOrder": list(self.scope_order),
            "scopes": {
                subagent_id: {
                    "label": scope.label,
                    "role": scope.role,
                    "reasoning": "".join(scope.reasoning),
                    "answer": "".join(scope.answer),
                    "toolParts": list(scope.tool_parts),
                    "costUsd": scope.cost_usd,
                    "usage": scope.usage,
                    "outcome": scope.outcome,
                    "terminal": scope.terminal,
                    "substitution": (
                        scope.substitution,
                        scope.substituted_provider,
                        scope.substituted_model,
                        scope.substituted_display_label,
                    ),
                    "latestStatus": scope.latest_status,
                    "searchItems": list(scope.search_items),
                    "sawSources": scope.saw_sources,
                    "reasoningMeasured": scope.reasoning_duration_sec is not None,
                }
                for subagent_id, scope in self.scopes.items()
            },
            "runSummary": self.run_summary,
            "receipt": self.receipt,
            "emptyRetry": (self.empty_retry, self.empty_retry_recovered),
        }


def tool_call_part(ev: ToolCall) -> ToolCallPart:
    return ToolCallPart(
        id=ev.id,
        name=ev.name,
        label=ev.label,
        status=ev.status,
        approval_state=ev.approval_state,
        input=ev.input,
        subagent_id=ev.subagent_id,
    )


def tool_result_part(ev: ToolResult) -> ToolResultPart:
    return ToolResultPart(
        tool_call_id=ev.tool_call_id,
        name=ev.name,
        label=ev.label,
        status=ev.status,
        approval_state=ev.approval_state,
        summary=ev.summary,
        output=ev.output,
        error=ev.error,
        subagent_id=ev.subagent_id,
    )


def build_agentic_run_summary_part(ev: RunCost) -> AgenticRunSummaryPart:
    """Fold a ``RunCost`` into the persisted receipt part (FL-33-a).

    Every receipt persists, including a plan pause and a worker-HITL pause: the
    old gate (``phase == "final" or partial or budget_halted or
    failed_worker_count > 0``) dropped a paused run's receipt entirely, so reload
    re-derived a meter that both showed a different number and claimed
    exact/final while the plan card above it still said "(estimate)".

    A non-final phase is by definition not a finished run, so it folds to
    ``partial`` regardless of the flags — a resumable pause must never read as a
    completed receipt.
    """
    return AgenticRunSummaryPart(
        outcome=(
            "partial"
            if (
                ev.partial
                or ev.budget_halted
                or ev.failed_worker_count > 0
                or ev.phase != "final"
            )
            else "complete"
        ),
        budget_halted=ev.budget_halted,
        failed_workers=ev.failed_worker_count,
        subtotal_usd=ev.subtotal_usd,
        cap_usd=ev.cap_usd,
        cost_confidence=ev.confidence,
        cost_phase=ev.phase,
    )


def fold_complete_substitution(
    ev: Complete,
    current: tuple[str | None, str | None, str | None, str | None],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Fold a `Complete` event's substitution into the running sub state.

    `current` is the `(sub_code, sub_provider, sub_model, sub_label)` tuple
    accumulated so far — it may already hold a router-side `auto_downgrade`
    seed. A provider-side fallback WINS precedence and overwrites the seed,
    bringing the real served-model triple with it. But this only happens when
    the provider ACTUALLY substituted: a `Complete` with `substitution is None`
    means "no provider fallback" and MUST NOT clobber the router seed (the
    silent-downgrade-leak invariant). In that case `current` is returned
    unchanged.
    """
    if ev.substitution is None:
        return current
    return (
        ev.substitution,
        ev.substituted_provider,
        ev.substituted_model,
        ev.substituted_display_label,
    )


def mark_unfinished_scopes_stopped(scopes: dict[str, ScopeState]) -> None:
    """Rewrite in-flight scope outcomes to ``stopped`` on stop/disconnect.

    Pump cancel acloses the orchestrator before worker ``SubagentDone(stopped)``
    events can be yielded onto the handler queue. Scopes that never received a
    Done would otherwise persist with the default ``succeeded``.
    """
    for scope in scopes.values():
        if not scope.terminal:
            scope.outcome = "stopped"


class TurnReducer:
    """The one durable fold over `ProviderEvent`, shared by both drivers.

    Stateless: every fact lives on the `TurnState` passed in, which is mutated in
    place and returned. Instantiated once per turn so a test can substitute a
    spy and prove no event reaches persistence without passing through here.
    """

    def reduce(self, state: TurnState, event: ProviderEvent, now: float) -> TurnState:
        """Fold one event into `state`. No I/O, no delivery, no control flow."""
        if isinstance(event, ReasoningDone):
            # FL-37: a done closes the reasoning block for its scope and carries
            # no content, so it is otherwise inert here — the wire gate that
            # decides whether to relay it belongs to the live driver.
            self._close_reasoning(state, event.subagent_id, now)
            return state

        if isinstance(event, SubagentStarted):
            state.scope(event.subagent_id, label=event.label, role=event.role)
            return state

        if isinstance(event, SubagentDone):
            self._settle_scope(state, event)
            return state

        if isinstance(event, RunCost):
            state.run_summary = build_agentic_run_summary_part(event)
            # AC-02: a receipt-bearing boundary event replaces the run's
            # accounting truth; a receipt-less display tick only refreshes the
            # wire summary and must never blank a receipt already banked.
            if event.receipt is not None:
                state.receipt = event.receipt
            return state

        # A tagged event only enters its own scope on an agentic turn; anything
        # else (including agentic-mode untagged content) folds flat.
        scope: ScopeState | None = None
        subagent_id = getattr(event, "subagent_id", None)
        if state.agentic and subagent_id is not None:
            scope = state.scope(subagent_id)

        if isinstance(event, ReasoningDelta):
            self._open_reasoning(state, scope, now)
            (state.reasoning if scope is None else scope.reasoning).append(event.text)
        elif isinstance(event, AnswerDelta):
            self._close_reasoning(state, subagent_id, now)
            if state.first_answer_ms is None:
                state.first_answer_ms = int((now - state.started_at) * 1000)
            (state.answer if scope is None else scope.answer).append(event.text)
        elif isinstance(event, StatusUpdate):
            if scope is None:
                state.latest_status = (event.label, event.state)
            else:
                scope.latest_status = (event.label, event.state)
        elif isinstance(event, Sources):
            # FL-35: the turn is grounded whoever produced the sources.
            state.saw_sources = True
            if scope is None:
                state.search_items = list(event.items)
            else:
                scope.search_items = list(event.items)
                scope.saw_sources = True
        elif isinstance(event, ToolCall):
            target = state.tool_parts if scope is None else scope.tool_parts
            target.append(tool_call_part(event).model_dump(by_alias=True, exclude_none=True))
        elif isinstance(event, ToolResult):
            self._fold_tool_result(
                state.tool_parts if scope is None else scope.tool_parts, event
            )
        elif isinstance(event, UsageUpdate):
            if scope is None:
                state.usage = event
            else:
                scope.usage = event
        elif isinstance(event, Complete):
            state.empty_retry = state.empty_retry or event.empty_retry
            state.empty_retry_recovered = (
                state.empty_retry_recovered or event.empty_retry_recovered
            )
            if scope is None:
                state.usage = event.usage
                (
                    state.substitution,
                    state.substituted_provider,
                    state.substituted_model,
                    state.substituted_display_label,
                ) = fold_complete_substitution(
                    event,
                    (
                        state.substitution,
                        state.substituted_provider,
                        state.substituted_model,
                        state.substituted_display_label,
                    ),
                )
            else:
                scope.usage = event.usage
        # `AwaitingApproval` carries no durable content. It is a pause HINT, and
        # a stopped drain deliberately discards those, so the live driver owns it.
        return state

    def _settle_scope(self, state: TurnState, event: SubagentDone) -> None:
        scope = state.scope(event.subagent_id, label=event.label, role=event.role)
        scope.cost_usd = event.cost_usd
        scope.usage = event.usage
        scope.outcome = event.outcome
        scope.terminal = True
        scope.substitution = event.substitution
        scope.substituted_provider = event.substituted_provider
        scope.substituted_model = event.substituted_model
        scope.substituted_display_label = event.substituted_display_label

    def _fold_tool_result(
        self, target: list[dict[str, Any]], event: ToolResult
    ) -> None:
        """Append the result and settle the `tool_call` part it answers.

        H-003 / AC-03: a sibling cancel must flip the call from
        `pending` + `awaiting_approval` to `rejected` + `cancelled`, never leave
        `pending` beside a cancelled result. The drain fold used to update only
        `status`, which is the parity defect this owner exists to prevent.
        """
        for part in target:
            if part.get("type") == "tool_call" and part.get("id") == event.tool_call_id:
                part["status"] = event.status
                if event.approval_state is not None:
                    part["approvalState"] = event.approval_state
                break
        target.append(
            tool_result_part(event).model_dump(by_alias=True, exclude_none=True)
        )

    def _open_reasoning(
        self, state: TurnState, scope: ScopeState | None, now: float
    ) -> None:
        """FL-37: start the reasoning clock on the first delta for this scope."""
        if scope is not None:
            if scope.reasoning_started_at is None:
                scope.reasoning_started_at = now
            return
        if state.reasoning_started_at is None:
            state.reasoning_started_at = now

    def _close_reasoning(
        self, state: TurnState, subagent_id: str | None, now: float
    ) -> None:
        """FL-37: close the reasoning clock at ReasoningDone / first AnswerDelta.

        Idempotent, and a no-op when the scope emitted no reasoning, so a turn
        without reasoning records no duration at all.
        """
        if state.agentic and subagent_id is not None:
            # `get`, not `scope()`: a stray tagged done must not open a section.
            scope = state.scopes.get(subagent_id)
            if (
                scope is not None
                and scope.reasoning_started_at is not None
                and scope.reasoning_duration_sec is None
            ):
                scope.reasoning_duration_sec = max(0.0, now - scope.reasoning_started_at)
            return
        if state.reasoning_started_at is not None and state.reasoning_duration_sec is None:
            state.reasoning_duration_sec = max(0.0, now - state.reasoning_started_at)
