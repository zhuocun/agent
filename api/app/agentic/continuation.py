"""Agentic HITL continuation state for worker tool pauses (BE-005).

When a deep-research worker pauses for tool approval, the orchestrator waits
for sibling workers to finish, then persists enough state so a later
``toolApproval`` resume continues **that** subagent — not a full re-plan.

Sibling policy (simpler correct design): **wait** for incomplete siblings to
finish before surfacing ``AwaitingApproval``. Completed worker results are kept;
the paused subagent is resumed in place. We do not cancel siblings.

**H-011 design choice:** aggregator / primary HITL continuation is *not*
implemented. ``ContinuationPhase`` is ``"worker"`` only. The aggregator always
runs with an empty registry tool allowlist so approval-gated tools cannot pause
there. Re-introduce ``aggregator`` / ``primary`` phases only with a real
checkpoint + resume path.

**H-012:** The continuation blob lives in ``Message.server_state`` (server-only),
keyed by tool-call id. Legacy rows may still embed ``_agenticContinuation`` on
``tool_call.input``; serializers strip that key (and claim/cost keys) before
any private or public API projection. The reserved input key is also stripped
before ``execute_tool`` / schema validation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from app.agentic.aggregate import WorkerOutput
from app.agentic.clarify import (
    ClarificationRecord,
    parse_clarification_records,
    serialize_clarification_records,
)
from app.providers.protocol import UsageUpdate

# Reserved key on pending tool_call.input (legacy). Must not collide with any
# tool's advertised JSON Schema properties.
CONTINUATION_INPUT_KEY = "_agenticContinuation"

# Claim id stamped on tool_call parts during settle (not tool input).
APPROVAL_CLAIM_INPUT_KEY = "_approvalClaimId"

# Keys stripped from every outbound tool_call / tool_result projection (H-012).
RESERVED_CONTROL_KEYS: frozenset[str] = frozenset(
    {
        CONTINUATION_INPUT_KEY,
        APPROVAL_CLAIM_INPUT_KEY,
        "plannerCostUsd",
        "planner_cost_usd",
        "actualCostUsd",
        "actual_cost_usd",
        "pausedWorkerCostUsd",
        "paused_worker_cost_usd",
    }
)

# H-011: only worker checkpoints are real; aggregator/primary removed until
# a full resume path ships.
ContinuationPhase = Literal["worker"]

# server_state JSON shape: {"continuations": {toolCallId: <blob>}}
SERVER_STATE_CONTINUATIONS_KEY = "continuations"


@dataclass(frozen=True)
class CompletedWorkerState:
    """One finished sibling (or prior) worker snapshot for resume synthesis."""

    subagent_id: str
    sub_question: str
    answer: str
    usage: UsageUpdate
    cost_usd: float
    outcome: str = "succeeded"
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgenticContinuation:
    """Durable fan-out continuation for a mid-worker tool HITL pause."""

    phase: ContinuationPhase
    paused_subagent_id: str
    user_text: str
    plan: tuple[str, ...]
    completed_workers: tuple[CompletedWorkerState, ...]
    planner_usage: UsageUpdate
    planner_cost_usd: float
    budget_halted: bool = False
    failed_workers: int = 0
    actual_cost_usd: float = 0.0
    paused_worker_index: int | None = None
    paused_sub_question: str | None = None
    # Pre-tool worker text accumulated before the HITL pause (BE-005 / H-010).
    # Restored into the worker answer buffer for synthesis; NOT re-emitted as
    # AnswerDelta on resume (already delivered on the paused turn).
    partial_answer: str = ""
    # H-010: worker-local checkpoint fidelity.
    partial_reasoning: str = ""
    source_ids: tuple[str, ...] = ()
    # Wire-shaped tool_call / tool_result dicts from before the pause.
    tool_transcript: tuple[dict[str, Any], ...] = ()
    # Cursor: number of answer chars already streamed to the client.
    emitted_answer_chars: int = 0
    # Structured clarify-before-plan answers (C-003).
    clarifications: tuple[ClarificationRecord, ...] = ()
    # H-002 / O-003: pin orchestration routing on resume.
    orchestration_mode: Literal["single", "deep_research"] | None = None
    tier_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    # Pre-pause usage for the paused worker (O-002 / H-009).
    paused_worker_usage: UsageUpdate | None = None
    paused_worker_cost_usd: float = 0.0
    version: int = 2


def _usage_to_dict(usage: UsageUpdate) -> dict[str, int]:
    return {
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "reasoningTokens": usage.reasoning_tokens,
        "cachedInputTokens": usage.cached_input_tokens,
    }


def _usage_from_dict(raw: object) -> UsageUpdate:
    if not isinstance(raw, dict):
        return UsageUpdate()
    return UsageUpdate(
        input_tokens=int(raw.get("inputTokens") or raw.get("input_tokens") or 0),
        output_tokens=int(raw.get("outputTokens") or raw.get("output_tokens") or 0),
        reasoning_tokens=int(
            raw.get("reasoningTokens") or raw.get("reasoning_tokens") or 0
        ),
        cached_input_tokens=int(
            raw.get("cachedInputTokens") or raw.get("cached_input_tokens") or 0
        ),
    )


def serialize_continuation(state: AgenticContinuation) -> dict[str, Any]:
    """CamelCase JSON-ready dict for server_state (not client tool input)."""
    return {
        "version": state.version,
        "phase": state.phase,
        "pausedSubagentId": state.paused_subagent_id,
        "userText": state.user_text,
        "plan": list(state.plan),
        "completedWorkers": [
            {
                "subagentId": w.subagent_id,
                "subQuestion": w.sub_question,
                "answer": w.answer,
                "usage": _usage_to_dict(w.usage),
                "costUsd": w.cost_usd,
                "outcome": w.outcome,
                "sourceIds": list(w.source_ids),
            }
            for w in state.completed_workers
        ],
        "plannerUsage": _usage_to_dict(state.planner_usage),
        "plannerCostUsd": state.planner_cost_usd,
        "budgetHalted": state.budget_halted,
        "failedWorkers": state.failed_workers,
        "actualCostUsd": state.actual_cost_usd,
        "pausedWorkerIndex": state.paused_worker_index,
        "pausedSubQuestion": state.paused_sub_question,
        "partialAnswer": state.partial_answer,
        "partialReasoning": state.partial_reasoning,
        "sourceIds": list(state.source_ids),
        "toolTranscript": [dict(p) for p in state.tool_transcript],
        "emittedAnswerChars": state.emitted_answer_chars,
        "clarifications": serialize_clarification_records(state.clarifications),
        "orchestrationMode": state.orchestration_mode,
        "tierId": state.tier_id,
        "providerId": state.provider_id,
        "modelId": state.model_id,
        "pausedWorkerUsage": (
            _usage_to_dict(state.paused_worker_usage)
            if state.paused_worker_usage is not None
            else None
        ),
        "pausedWorkerCostUsd": state.paused_worker_cost_usd,
    }


def parse_continuation(raw: object) -> AgenticContinuation | None:
    """Parse a continuation blob; None when missing or malformed.

    Legacy blobs with ``phase`` in {aggregator, primary} are rejected — those
    phases were never resumable (H-011).
    """
    if not isinstance(raw, dict):
        return None
    phase = raw.get("phase")
    paused_id = raw.get("pausedSubagentId") or raw.get("paused_subagent_id")
    user_text = raw.get("userText") or raw.get("user_text")
    plan_raw = raw.get("plan")
    if phase != "worker":
        return None
    if not isinstance(paused_id, str) or not paused_id:
        return None
    if not isinstance(user_text, str):
        return None
    if not isinstance(plan_raw, list):
        return None
    plan = tuple(str(item) for item in plan_raw if isinstance(item, str))
    completed_raw = raw.get("completedWorkers") or raw.get("completed_workers") or []
    completed: list[CompletedWorkerState] = []
    if isinstance(completed_raw, list):
        for item in completed_raw:
            if not isinstance(item, dict):
                continue
            sid = item.get("subagentId") or item.get("subagent_id")
            sq = item.get("subQuestion") or item.get("sub_question")
            answer = item.get("answer")
            if not isinstance(sid, str) or not isinstance(sq, str):
                continue
            raw_sources = item.get("sourceIds") or item.get("source_ids") or []
            source_ids: tuple[str, ...] = ()
            if isinstance(raw_sources, list):
                source_ids = tuple(str(s) for s in raw_sources if s is not None)
            completed.append(
                CompletedWorkerState(
                    subagent_id=sid,
                    sub_question=sq,
                    answer=str(answer) if answer is not None else "",
                    usage=_usage_from_dict(item.get("usage")),
                    cost_usd=float(item.get("costUsd") or item.get("cost_usd") or 0.0),
                    outcome=str(item.get("outcome") or "succeeded"),
                    source_ids=source_ids,
                )
            )
    idx_raw = raw.get("pausedWorkerIndex", raw.get("paused_worker_index"))
    paused_index = int(idx_raw) if isinstance(idx_raw, int) else None
    paused_sq = raw.get("pausedSubQuestion") or raw.get("paused_sub_question")
    partial_raw = raw.get("partialAnswer") or raw.get("partial_answer") or ""
    reasoning_raw = raw.get("partialReasoning") or raw.get("partial_reasoning") or ""
    self_sources_raw = raw.get("sourceIds") or raw.get("source_ids") or []
    self_sources: tuple[str, ...] = ()
    if isinstance(self_sources_raw, list):
        self_sources = tuple(str(s) for s in self_sources_raw if s is not None)
    transcript_raw = raw.get("toolTranscript") or raw.get("tool_transcript") or []
    tool_transcript: list[dict[str, Any]] = []
    if isinstance(transcript_raw, list):
        for item in transcript_raw:
            if isinstance(item, dict):
                tool_transcript.append(dict(item))
    emitted_raw = raw.get("emittedAnswerChars", raw.get("emitted_answer_chars"))
    emitted_chars = int(emitted_raw) if isinstance(emitted_raw, int) else 0
    if emitted_chars <= 0 and isinstance(partial_raw, str) and partial_raw:
        # Legacy blobs: treat full partial_answer as already-emitted.
        emitted_chars = len(partial_raw)
    clarifications = tuple(
        parse_clarification_records(
            raw.get("clarifications") or raw.get("clarification_records") or []
        )
    )
    mode_raw = raw.get("orchestrationMode") or raw.get("orchestration_mode")
    orchestration_mode: Literal["single", "deep_research"] | None = (
        mode_raw if mode_raw in ("single", "deep_research") else None
    )
    tier_raw = raw.get("tierId") or raw.get("tier_id")
    provider_raw = raw.get("providerId") or raw.get("provider_id")
    model_raw = raw.get("modelId") or raw.get("model_id")
    paused_usage_raw = raw.get("pausedWorkerUsage") or raw.get("paused_worker_usage")
    paused_cost_raw = raw.get("pausedWorkerCostUsd") or raw.get(
        "paused_worker_cost_usd"
    )
    return AgenticContinuation(
        version=int(raw.get("version") or 1),
        phase="worker",
        paused_subagent_id=paused_id,
        user_text=user_text,
        plan=plan,
        completed_workers=tuple(completed),
        planner_usage=_usage_from_dict(
            raw.get("plannerUsage") or raw.get("planner_usage")
        ),
        planner_cost_usd=float(
            raw.get("plannerCostUsd") or raw.get("planner_cost_usd") or 0.0
        ),
        budget_halted=bool(raw.get("budgetHalted") or raw.get("budget_halted")),
        failed_workers=int(raw.get("failedWorkers") or raw.get("failed_workers") or 0),
        actual_cost_usd=float(
            raw.get("actualCostUsd") or raw.get("actual_cost_usd") or 0.0
        ),
        paused_worker_index=paused_index,
        paused_sub_question=str(paused_sq) if isinstance(paused_sq, str) else None,
        partial_answer=str(partial_raw) if partial_raw is not None else "",
        partial_reasoning=str(reasoning_raw) if reasoning_raw is not None else "",
        source_ids=self_sources,
        tool_transcript=tuple(tool_transcript),
        emitted_answer_chars=emitted_chars,
        clarifications=clarifications,
        orchestration_mode=orchestration_mode,
        tier_id=str(tier_raw) if isinstance(tier_raw, str) else None,
        provider_id=str(provider_raw) if isinstance(provider_raw, str) else None,
        model_id=str(model_raw) if isinstance(model_raw, str) else None,
        paused_worker_usage=(
            _usage_from_dict(paused_usage_raw)
            if isinstance(paused_usage_raw, dict)
            else None
        ),
        paused_worker_cost_usd=float(paused_cost_raw or 0.0),
    )


def extract_continuation_from_tool_input(
    tool_input: object,
) -> tuple[dict[str, Any], AgenticContinuation | None]:
    """Split tool input into (executor_input, continuation).

    Always returns a shallow copy of the executor-facing input with reserved
    control keys removed.
    """
    if not isinstance(tool_input, dict):
        return {}, None
    cleaned = {
        k: v for k, v in tool_input.items() if k not in RESERVED_CONTROL_KEYS
    }
    continuation = parse_continuation(tool_input.get(CONTINUATION_INPUT_KEY))
    return cleaned, continuation


def attach_continuation_to_tool_input(
    tool_input: dict[str, Any] | None,
    state: AgenticContinuation,
) -> dict[str, Any]:
    """Legacy helper: attach continuation onto tool input.

    Prefer ``put_continuation_in_server_state`` for new writes (H-012). Kept for
    tests that construct wire-shaped parts directly.
    """
    base = dict(tool_input or {})
    base[CONTINUATION_INPUT_KEY] = serialize_continuation(state)
    return base


def put_continuation_in_server_state(
    server_state: dict[str, Any] | None,
    tool_call_id: str,
    state: AgenticContinuation | dict[str, Any],
) -> dict[str, Any]:
    """Return a new server_state with the continuation stored under tool_call_id."""
    out = dict(server_state or {})
    conts = dict(out.get(SERVER_STATE_CONTINUATIONS_KEY) or {})
    blob = (
        serialize_continuation(state)
        if isinstance(state, AgenticContinuation)
        else dict(state)
    )
    conts[tool_call_id] = blob
    out[SERVER_STATE_CONTINUATIONS_KEY] = conts
    return out


def get_continuation_from_server_state(
    server_state: object,
    tool_call_id: str,
) -> AgenticContinuation | None:
    """Load a continuation from Message.server_state."""
    if not isinstance(server_state, dict):
        return None
    conts = server_state.get(SERVER_STATE_CONTINUATIONS_KEY)
    if not isinstance(conts, dict):
        return None
    return parse_continuation(conts.get(tool_call_id))


def resolve_continuation(
    *,
    server_state: object = None,
    tool_input: object = None,
    tool_call_id: str | None = None,
) -> tuple[dict[str, Any], AgenticContinuation | None]:
    """Prefer server_state, fall back to legacy tool-input embedding."""
    cleaned, legacy = extract_continuation_from_tool_input(tool_input)
    if tool_call_id:
        from_state = get_continuation_from_server_state(server_state, tool_call_id)
        if from_state is not None:
            return cleaned, from_state
    return cleaned, legacy


def strip_reserved_keys(value: object) -> object:
    """Recursively drop reserved control / internal cost keys (H-012)."""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, child in value.items():
            if key in RESERVED_CONTROL_KEYS:
                continue
            out[key] = strip_reserved_keys(child)
        return out
    if isinstance(value, list):
        return [strip_reserved_keys(item) for item in value]
    return value


def sanitize_message_parts_for_api(
    parts: list[Any] | None,
) -> list[dict[str, Any]]:
    """Strip reserved keys from tool parts for private/public API responses."""
    if not parts:
        return []
    sanitized: list[dict[str, Any]] = []
    for part in parts:
        raw = (
            deepcopy(part)
            if isinstance(part, dict)
            else part.model_dump(by_alias=True)
        )
        if raw.get("type") in {"tool_call", "tool_result"}:
            stripped = strip_reserved_keys(raw)
            assert isinstance(stripped, dict)
            raw = stripped
            # Also strip from top-level part (claim id lives beside input).
            for key in list(raw.keys()):
                if key in RESERVED_CONTROL_KEYS:
                    del raw[key]
        sanitized.append(raw)
    return sanitized


def completed_to_worker_outputs(
    completed: tuple[CompletedWorkerState, ...] | list[CompletedWorkerState],
) -> list[WorkerOutput]:
    """Map completed snapshots into aggregator ``WorkerOutput`` rows."""
    return [
        WorkerOutput(
            subagent_id=w.subagent_id,
            sub_question=w.sub_question,
            answer=w.answer,
            source_ids=w.source_ids,
        )
        for w in completed
    ]
