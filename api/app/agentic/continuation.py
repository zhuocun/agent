"""Agentic HITL continuation state for worker/aggregator tool pauses (BE-005).

When a deep-research worker (or aggregator) pauses for tool approval, the
orchestrator waits for sibling workers to finish, then persists enough state on
the pending ``tool_call`` part so a later ``toolApproval`` resume continues
**that** subagent — not a full re-plan.

Sibling policy (simpler correct design): **wait** for incomplete siblings to
finish before surfacing ``AwaitingApproval``. Completed worker results are kept;
the paused subagent is resumed in place. We do not cancel siblings.

The blob lives under the reserved input key ``_agenticContinuation`` on the
pending tool call. It is stripped before ``execute_tool`` / schema validation so
it never reaches a tool executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.agentic.aggregate import WorkerOutput
from app.providers.protocol import UsageUpdate

# Reserved key on pending tool_call.input. Must not collide with any tool's
# advertised JSON Schema properties (builtins use title/startsAt/timezone).
CONTINUATION_INPUT_KEY = "_agenticContinuation"

ContinuationPhase = Literal["worker", "aggregator", "primary"]


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
    """Durable fan-out continuation for a mid-subagent tool HITL pause."""

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
    # Pre-tool worker text accumulated before the HITL pause (BE-005).
    partial_answer: str = ""
    version: int = 1


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
    """CamelCase JSON-ready dict for embedding in tool_call.input."""
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
    }


def parse_continuation(raw: object) -> AgenticContinuation | None:
    """Parse a continuation blob; None when missing or malformed."""
    if not isinstance(raw, dict):
        return None
    phase = raw.get("phase")
    paused_id = raw.get("pausedSubagentId") or raw.get("paused_subagent_id")
    user_text = raw.get("userText") or raw.get("user_text")
    plan_raw = raw.get("plan")
    if phase not in ("worker", "aggregator", "primary"):
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
    return AgenticContinuation(
        version=int(raw.get("version") or 1),
        phase=phase,
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
    )


def extract_continuation_from_tool_input(
    tool_input: object,
) -> tuple[dict[str, Any], AgenticContinuation | None]:
    """Split tool input into (executor_input, continuation).

    Always returns a shallow copy of the executor-facing input with the reserved
    continuation key removed.
    """
    if not isinstance(tool_input, dict):
        return {}, None
    cleaned = {k: v for k, v in tool_input.items() if k != CONTINUATION_INPUT_KEY}
    continuation = parse_continuation(tool_input.get(CONTINUATION_INPUT_KEY))
    return cleaned, continuation


def attach_continuation_to_tool_input(
    tool_input: dict[str, Any] | None,
    state: AgenticContinuation,
) -> dict[str, Any]:
    """Return tool input with the continuation blob attached."""
    base = dict(tool_input or {})
    base[CONTINUATION_INPUT_KEY] = serialize_continuation(state)
    return base


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
