"""Durable message parts to the reads that derive from them (AC-05).

Persisted parts are the only record a later request has of a finished turn, and two
consumers read them. Both used to do it by hand: `load_history` concatenated every
`text` part into one provider message, and the idempotency route rebuilt an SSE
stream from its own buckets. On an agentic turn both were wrong the same way — every
part is tagged with the subagent that produced it, so flattening promoted planner
prompts and worker notes into the manager's answer while dropping the subagent
lifecycle, per-worker attribution and run receipt entirely.

This module is the one owner of what a durable part means: which parts are the
turn's answer, how a stored row replays, and which stored `tool_call` a resume may
act on. It is pure — no database, no clock, no delivery. Semantic replay is
deliberately NOT a re-run of the original stream: chunk boundaries, interleaving
and progress ticks were never persisted, so they are not invented, and
`ReplayLogBuffer` still owns exact buffered replay.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import ValidationError
from sse_starlette import ServerSentEvent

from app.agentic.continuation import resolve_continuation, sanitize_message_parts_for_api
from app.providers.protocol import ChatMessage as ProviderChatMessage
from app.schemas import stream_events as events
from app.schemas.message import AgenticRunSummaryPart, ModelAttribution, SubagentPart
from app.search.protocol import SourceItem
from app.streaming import sse

# The orchestration roles whose prose IS the manager's answer: `primary` is the
# single-agent agentic turn, `aggregator` the deep-research synthesis. Everything
# else (planner, worker, verifier) is working material that stays in its section.
MANAGER_SCOPE_ROLES: frozenset[str] = frozenset({"primary", "aggregator"})


def _dict_parts(parts: object) -> list[dict[str, Any]]:
    """Every dict-shaped part, tolerating a NULL or malformed `parts` column."""
    return [p for p in parts if isinstance(p, dict)] if isinstance(parts, list) else []


def _manager_scope_ids(parts: list[dict[str, Any]]) -> frozenset[str]:
    """Subagent ids whose `subagent` marker claims a manager-owned role."""
    return frozenset(
        str(part["subagentId"])
        for part in parts
        if part.get("type") == "subagent"
        and part.get("role") in MANAGER_SCOPE_ROLES
        and isinstance(part.get("subagentId"), str)
    )


def parts_to_provider_history(parts: object, *, role: str) -> ProviderChatMessage | None:
    """Project one persisted row into the provider's view of that turn.

    Untagged content plus the manager-owned scopes only, so None comes back when the
    row gives a provider nothing to consume: a non-chat role, an unreadable `parts`
    column, or an agentic turn whose only prose belongs to the planner and its
    workers. Dropping that row is the point of AC-05 — a worker's scratch notes are
    not what the assistant said. Reasoning is projected separately because DeepSeek
    thinking mode wants prior assistant reasoning echoed back.
    """
    if role not in ("user", "assistant"):
        return None
    parts_list = _dict_parts(parts)
    owned = _manager_scope_ids(parts_list)
    text: list[str] = []
    reasoning: list[str] = []
    for part in parts_list:
        part_type = part.get("type")
        if part_type not in ("text", "reasoning"):
            continue
        owner = part.get("subagentId")
        if owner is not None and not (isinstance(owner, str) and owner in owned):
            continue
        bucket = text if part_type == "text" else reasoning
        bucket.append(str(part.get("text", "")))
    if not text and not reasoning:
        return None
    return ProviderChatMessage(
        role=cast(Literal["user", "assistant"], role),
        text="".join(text),
        reasoning_content="".join(reasoning) if reasoning else None,
    )


@dataclass
class _Section:
    """One replayable group: a subagent's section, or the untagged turn itself."""

    subagent_id: str | None
    marker: dict[str, Any] | None = None
    reasoning: list[str] = field(default_factory=list)
    tool_parts: list[dict[str, Any]] = field(default_factory=list)
    status: dict[str, Any] | None = None
    sources: dict[str, Any] | None = None
    answer: list[str] = field(default_factory=list)
    # Whether the stored `text` part came before `sources`. A flat turn stores
    # [text][sources] and an agentic section [sources][text], so replay follows
    # the row rather than reshuffling one of them.
    answer_before_sources: bool = True


def _sections(parts: list[dict[str, Any]]) -> list[_Section]:
    """Group parts by owning subagent, keyed on `subagentId` and not on position,
    so a row whose marker and content were stored out of order still replays as one
    section rather than as two half-sections."""
    # Insertion-ordered, which IS first-seen order.
    sections: dict[str | None, _Section] = {}

    def section_for(key: str | None) -> _Section:
        if key not in sections:
            sections[key] = _Section(subagent_id=key)
        return sections[key]

    for part in parts:
        part_type = part.get("type")
        owner = part.get("subagentId")
        if part_type == "subagent":
            if isinstance(owner, str):
                section_for(owner).marker = part
            continue
        if part_type == "agentic_run_summary":
            continue
        section = section_for(owner if isinstance(owner, str) else None)
        if part_type == "reasoning":
            section.reasoning.append(str(part.get("text", "")))
        elif part_type == "text":
            if not section.answer:
                section.answer_before_sources = section.sources is None
            section.answer.append(str(part.get("text", "")))
        elif part_type in ("tool_call", "tool_result"):
            section.tool_parts.append(part)
        elif part_type == "status":
            section.status = part
        elif part_type == "sources":
            section.sources = part
    return list(sections.values())


def _sources_frame(section: _Section) -> ServerSentEvent | None:
    """The stored `sources` part, ungrounded marker included: an empty `items` with
    `requested=True` is the honest "answered without live sources" state (PRD 07
    §4.3), so it replays instead of being dropped."""
    part = section.sources
    if part is None:
        return None
    raw = part.get("items")
    items = [SourceItem.model_validate(it) for it in (raw if isinstance(raw, list) else [])]
    requested = bool(part.get("requested", False))
    if not items and not requested:
        return None
    return sse.encode_sources(
        events.SourcesEvent(items=items, requested=requested, subagent_id=section.subagent_id)
    )


def _section_frames(section: _Section) -> Iterator[ServerSentEvent]:
    """Emit one section: `SubagentStarted`, its stored content, `SubagentDone`.

    Every frame carries the section's `subagentId`, so a reload groups as the live
    turn did, and a section with no readable marker emits no lifecycle frames rather
    than invented ones. One deliberate substitution: the untagged section always
    emits its `answer_delta` even for empty text, because that is the flat wire
    sequence non-agentic clients already replay.
    """
    scope = section.subagent_id
    marker: SubagentPart | None = None
    if section.marker is not None:
        with contextlib.suppress(ValidationError):
            marker = SubagentPart.model_validate(section.marker)
    if marker is not None:
        started = events.SubagentStartedEvent(
            subagent_id=marker.subagent_id, label=marker.label, role=marker.role
        )
        yield sse.encode_subagent_started(started)
    text = "".join(section.reasoning)
    if text:
        yield sse.encode_reasoning_delta(events.ReasoningDeltaEvent(text=text, subagent_id=scope))
        yield sse.encode_reasoning_done(events.ReasoningDoneEvent(subagent_id=scope))
    for part in section.tool_parts:
        if part.get("type") == "tool_call":
            yield sse.encode_tool_call(events.ToolCallEvent.model_validate(part))
        else:
            yield sse.encode_tool_result(events.ToolResultEvent.model_validate(part))
    status = section.status
    if status is not None:
        yield sse.encode_status(
            events.StatusEvent(
                label=str(status.get("label", "")),
                state="active" if status.get("state") == "active" else "done",
                subagent_id=scope,
            )
        )
    answer = "".join(section.answer)
    tail: tuple[ServerSentEvent | None, ...] = (
        sse.encode_answer_delta(events.AnswerDeltaEvent(text=answer, subagent_id=scope))
        if scope is None or answer
        else None,
        _sources_frame(section),
    )
    for frame in tail if section.answer_before_sources else tuple(reversed(tail)):
        if frame is not None:
            yield frame
    if marker is not None:
        yield sse.encode_subagent_done(_subagent_done(marker))


def _subagent_done(marker: SubagentPart) -> events.SubagentDoneEvent:
    """The section's terminal outcome, from durable marker fields only. The
    substituted provider/model/label triple was never stored beside the reason, so
    only the reason code carried by the stored attribution replays."""
    substitution = marker.attribution.substitution if marker.attribution else None
    return events.SubagentDoneEvent(
        subagent_id=marker.subagent_id,
        label=marker.label,
        role=marker.role,
        cost_usd=marker.cost_usd,
        outcome=marker.outcome,
        attribution=marker.attribution,
        substitution=substitution.reason_code if substitution is not None else None,
    )


def _run_cost_frame(parts: list[dict[str, Any]]) -> ServerSentEvent | None:
    """Replay the stored run receipt, or nothing when the row has none.
    `subtotalUsd` / `capUsd` are required on the wire but optional on the part
    (rows predating AR-012 carry neither), so a receipt missing either is omitted
    rather than replayed as a confident $0.00."""
    summary: AgenticRunSummaryPart | None = None
    for part in parts:
        if part.get("type") == "agentic_run_summary":
            with contextlib.suppress(ValidationError):
                summary = AgenticRunSummaryPart.model_validate(part)
    if summary is None or summary.subtotal_usd is None or summary.cap_usd is None:
        return None
    receipt = events.RunCostEvent(
        subtotal_usd=summary.subtotal_usd,
        cap_usd=summary.cap_usd,
        confidence=summary.cost_confidence or "exact",
        phase=summary.cost_phase or "final",
        partial=summary.outcome == "partial",
        budget_halted=summary.budget_halted,
        failed_worker_count=summary.failed_workers,
    )
    return sse.encode_run_cost(receipt)


def parts_to_semantic_replay(
    parts: object,
    attribution: ModelAttribution | dict[str, Any],
    *,
    user_message_id: UUID | str,
    assistant_message_id: UUID | str,
) -> list[ServerSentEvent]:
    """Project a stored assistant row into its canonical semantic replay.

    Deterministic for a given row: `submitted`, each section in stored order, the
    stored run receipt, then `terminal` with the stored attribution. A flat
    non-agentic row has exactly one untagged section — a contentless row included,
    which is why an empty part list still falls back to one — so its frame sequence
    is the one clients have always replayed. `streaming.sse` stays the only owner
    of the wire format, so a replayed frame cannot drift from a live one, and reserved
    control keys are stripped from the tool transcript here (H-012) so neither
    consumer can forget to. Raises `pydantic.ValidationError` when `attribution` is
    not a valid terminal attribution; the caller decides whether such a row is
    replayable at all.
    """
    parts_list = sanitize_message_parts_for_api(_dict_parts(parts))
    frames = [sse.encode_submitted(events.SubmittedEvent(message_id=str(user_message_id)))]
    for section in _sections(parts_list) or [_Section(subagent_id=None)]:
        frames.extend(_section_frames(section))
    run_cost = _run_cost_frame(parts_list)
    if run_cost is not None:
        frames.append(run_cost)
    terminal = events.TerminalEvent(
        message_id=str(assistant_message_id),
        attribution=ModelAttribution.model_validate(attribution),
    )
    frames.append(sse.encode_terminal(terminal))
    return frames


def find_pending_tool_call(parts: object, tool_call_id: str) -> dict[str, Any] | None:
    """Find a pending, approval-awaiting `tool_call` part by id."""
    for part in _dict_parts(parts):
        if (
            part.get("type") == "tool_call"
            and part.get("id") == tool_call_id
            and part.get("status") == "awaiting_approval"
            and part.get("approvalState") == "pending"
        ):
            return part
    return None


def find_resumable_tool_call(
    parts: object,
    tool_call_id: str,
    *,
    server_state: object = None,
) -> dict[str, Any] | None:
    """Find a tool_call for resume: pending OR already settled (BE-007 retry).

    H-003: a worker call cancelled as a concurrent-pause sibling is
    `approvalState=rejected` without a continuation, and those are not resumable —
    only a continuation-bearing pause (or a primary HITL call) may be
    approved/denied. That decision reads the part's `subagentId`, which is why it
    is here and not in a route.
    """
    pending = find_pending_tool_call(parts, tool_call_id)
    if pending is not None:
        return pending
    for part in _dict_parts(parts):
        settled = part.get("approvalState") in ("approved", "rejected")
        if part.get("type") != "tool_call" or part.get("id") != tool_call_id or not settled:
            continue
        subagent_id = part.get("subagentId")
        if isinstance(subagent_id, str) and subagent_id.startswith("worker-"):
            _, continuation = resolve_continuation(
                server_state=server_state,
                tool_input=part.get("input"),
                tool_call_id=tool_call_id,
            )
            if continuation is None and part.get("approvalState") == "rejected":
                return None
        return part
    return None


def find_any_resumable_tool_call(
    parts: object,
    *,
    server_state: object = None,
) -> dict[str, Any] | None:
    """Return the first still-pending approval-gated `tool_call` (A-7 Stop)."""
    for part in _dict_parts(parts):
        call_id = part.get("id")
        if part.get("type") != "tool_call" or not isinstance(call_id, str) or not call_id:
            continue
        found = find_resumable_tool_call(parts, call_id, server_state=server_state)
        if found is not None and found.get("approvalState") == "pending":
            return found
    return None
