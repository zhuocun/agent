"""Provider-agnostic, bounded agent loop for backend-side tool calling (HITL).

Generalizes the shape of the provider-internal web_search loop (see
``app/providers/openai.py``) into a standalone orchestrator that drives ANY
provider's ``ToolCall`` events through the built-in tool registry — including
the human-in-the-loop (HITL) approval gate. ``web_search`` stays
provider-internal and UNTOUCHED; this loop is additive and, in v1, drives only
the FAKE provider.

Round model (mirrors ``_MAX_SEARCH_ROUNDS``): one round = one provider stream.
``TOOL_MAX_ROUNDS`` is a hard upper bound on TOTAL provider invocations,
including the compelled suppress-tools final pass. With N>1 the loop runs at
most N-1 action rounds (tools advertised) and reserves the last slot for a
suppress-tools final answer when tools were still requested; with N=1 there is
no reserved final pass (a greedy tool request ends with a defensive fallback if
no answer was produced).

``make_stream(tool_feedback, suppress_tools)`` returns a fresh provider event
iterator given the tool results accumulated so far (the handler threads them back
via ``history``, since the ``Provider.stream`` Protocol intentionally carries no
tool params) and whether tools should be advertised to the provider this round.
For each round:

- Relay every non-``ToolCall`` event (reasoning / answer / status / sources /
  usage / complete) straight through. Usage/Complete from every provider
  invocation are SUMMED into one cumulative terminal ``Complete``.
- For each ``ToolCall`` the provider requests:
  - UNKNOWN / not-in-allowlist tool → synthesize a failed ``ToolResult`` and
    feed it back (the model can recover next round); never execute.
  - APPROVAL-GATED and not yet approved → emit a server-normalized
    ``ToolCall(status="awaiting_approval", approval_state="pending")`` then an
    ``AwaitingApproval`` sentinel and STOP. The handler turns this into the
    paused terminal; a resume POST applies the decision.
  - Otherwise (auto / already-approved) → emit ``ToolCall(status="running")``,
    execute it (``execute_tool`` is timeout-wrapped), emit the ``ToolResult``,
    feed it back, and continue to the next round.
- A round that requests NO tool calls is terminal: its content was the final
  answer; relay it and stop.

Optional ``allowed_tools`` scopes which registry tools this loop may fulfill
(least-privilege for deep-research workers: empty set ⇒ registry tools denied;
provider-internal ``web_search`` is unaffected). ``None`` means the full
registry.

SECURITY: tool output is untrusted (a prompt-injection surface). It is fed back
ONLY as structured tool data via ``make_stream``'s feedback channel, never spliced
into instructions. The approval gate is enforced here AND re-checked inside
``execute_tool`` and at the resume route — a forged approval cannot reach a
non-gated/unknown tool.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Collection
from dataclasses import replace
from typing import Any

from app.config import Settings
from app.observability.tracing import execute_tool_span
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.streaming.constants import EMPTY_REPLY_FALLBACK
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolApprovalState, ToolCallRequest, ToolExecutionResult

# Factory: given the tool results gathered so far and whether tools should be
# suppressed on the provider, build a fresh provider event stream for the next
# round. The handler supplies this so the loop stays provider-agnostic and the
# `Provider.stream` Protocol gains no tool params.
#
# `suppress_tools` is True ONLY for the compelled final pass (see
# `run_agent_loop`): the factory must then advertise NO tools to the provider
# (`tools=None`) so a greedy provider that would otherwise keep requesting tools
# is forced to emit its final answer instead of returning a blank turn.
MakeStream = Callable[[list[ToolResult], bool], AsyncIterator[ProviderEvent]]

# Sentinel prefixing the synthetic history turn that carries tool results back to
# the provider for the next round. The handler builds these turns via
# `tool_feedback_to_history`; the FAKE provider detects this prefix to know the
# tool has run and it should now answer (a real provider would instead receive a
# structured `role="tool"` message — that wiring is out of scope for the
# fake-only v1). Tool output remains untrusted: it is carried ONLY as this data
# turn, never spliced into instructions.
TOOL_FEEDBACK_SENTINEL = "[tool-results]"


def tool_feedback_to_history(results: list[ToolResult]) -> list[ChatMessage]:
    """Encode accumulated tool results as appended chat-history turns.

    One sentinel-prefixed assistant turn carrying the JSON results. Empty list
    when there are no results yet (round 1), so the first provider pass sees the
    unmodified history.
    """
    if not results:
        return []
    result_dicts = [
        {
            "toolCallId": r.tool_call_id,
            "name": r.name,
            "status": r.status,
            "output": r.output,
            "error": r.error,
        }
        for r in results
    ]
    assistant_reasoning = next(
        (r.round_reasoning for r in results if r.round_reasoning is not None),
        None,
    )
    payload_obj: dict[str, Any] | list[dict[str, Any]]
    if assistant_reasoning is not None:
        payload_obj = {
            "results": result_dicts,
            "assistantReasoning": assistant_reasoning,
        }
    else:
        payload_obj = result_dicts
    payload = json.dumps(payload_obj, separators=(",", ":"))
    return [ChatMessage(role="assistant", text=f"{TOOL_FEEDBACK_SENTINEL} {payload}")]


def parse_tool_feedback_history(
    history: list[ChatMessage],
) -> tuple[list[ChatMessage], list[dict[str, object]], str | None]:
    """Split sentinel-prefixed tool-feedback turns out of `history`.

    The inverse of ``tool_feedback_to_history``: a real provider adapter calls
    this to recover the structured tool results the loop fed back so it can
    rebuild them as NATIVE tool messages (OpenAI `role="tool"` / Anthropic
    `tool_result` blocks) instead of leaving them as the opaque assistant text
    turn the FAKE provider keys on. Returns ``(clean_history, results)`` where
    ``clean_history`` is the history with every sentinel turn removed and
    ``results`` is the flattened list of result dicts (keys: ``toolCallId``,
    ``name``, ``status``, ``output``, ``error``) in feed-back order. A malformed
    payload is skipped (its turn is still dropped) so a bad turn can't crash the
    real-provider path.
    """
    clean: list[ChatMessage] = []
    results: list[dict[str, object]] = []
    assistant_reasoning: str | None = None
    for message in history:
        if message.role == "assistant" and message.text.startswith(TOOL_FEEDBACK_SENTINEL):
            payload = message.text[len(TOOL_FEEDBACK_SENTINEL) :].strip()
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                results.extend(
                    item for item in parsed["results"] if isinstance(item, dict)
                )
                raw_reasoning = parsed.get("assistantReasoning")
                if raw_reasoning is not None:
                    assistant_reasoning = str(raw_reasoning)
            elif isinstance(parsed, list):
                results.extend(item for item in parsed if isinstance(item, dict))
            continue
        clean.append(message)
    return clean, results, assistant_reasoning


def _add_usage(left: UsageUpdate, right: UsageUpdate) -> UsageUpdate:
    """Field-wise sum of two usage snapshots (run-cost roll-up)."""
    return UsageUpdate(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        reasoning_tokens=left.reasoning_tokens + right.reasoning_tokens,
        cached_input_tokens=left.cached_input_tokens + right.cached_input_tokens,
        subagent_id=right.subagent_id or left.subagent_id,
    )


def _to_result_event(*, call: ToolCall, exec_result: ToolExecutionResult) -> ToolResult:
    """Build a wire ``ToolResult`` event from a ``ToolExecutionResult``."""
    spec = TOOL_REGISTRY.get(call.name)
    label = call.label or (spec.label if spec is not None else None)
    return ToolResult(
        tool_call_id=exec_result.tool_call_id,
        name=exec_result.name,
        label=label,
        status=exec_result.status,
        approval_state=exec_result.approval_state,
        summary=exec_result.summary,
        output=exec_result.output or None,
        error=exec_result.error,
    )


def _pending_approval_call(call: ToolCall) -> ToolCall:
    """Server-normalized pending ToolCall for a resumable HITL pause."""
    spec = TOOL_REGISTRY.get(call.name)
    return ToolCall(
        id=call.id,
        name=call.name,
        label=call.label or (spec.label if spec is not None else None),
        status="awaiting_approval",
        approval_state="pending",
        input=dict(call.input or {}),
        subagent_id=call.subagent_id,
    )


async def run_agent_loop(
    *,
    make_stream: MakeStream,
    settings: Settings,
    allowed_tools: Collection[str] | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Drive a bounded tool-calling loop over a provider event stream.

    Yields the same ``ProviderEvent`` union the handler already consumes, so the
    handler's accumulation / persistence is unchanged. Stops on: a round with no
    tool calls (relayed answer), an ``AwaitingApproval`` pause, or the
    ``tool_max_rounds`` bound (total provider invocations, including any
    suppress-tools final pass).

    ``allowed_tools``: when set, only those registry tool names may execute;
    others fail closed as unknown. ``None`` = full registry. Deep-research
    workers pass an empty collection (registry tools denied; provider-internal
    ``web_search`` is unaffected).
    """
    tool_feedback: list[ToolResult] = []
    max_rounds = max(1, settings.tool_max_rounds)
    # Reserve the last provider slot for a suppress-tools final pass when N>1.
    # With N=1 there is no reserved final — a tool request on that sole round
    # ends without an extra provider call (defensive empty fallback if needed).
    action_rounds = max_rounds if max_rounds == 1 else max_rounds - 1
    answer_emitted = False
    tools_ran = False
    accumulated_usage = UsageUpdate()
    allowed: set[str] | None = None if allowed_tools is None else set(allowed_tools)

    def _note_answer(delta: AnswerDelta) -> None:
        nonlocal answer_emitted
        if delta.text.strip():
            answer_emitted = True

    def _make_usage_folder() -> tuple[
        Callable[[ProviderEvent], ProviderEvent], Callable[[], None]
    ]:
        """Per-stream usage folder: count each round once (UsageUpdate XOR Complete)."""
        round_usage_folded = False

        def _fold(event: ProviderEvent) -> ProviderEvent:
            nonlocal accumulated_usage, round_usage_folded
            if isinstance(event, UsageUpdate):
                accumulated_usage = _add_usage(accumulated_usage, event)
                round_usage_folded = True
                return UsageUpdate(
                    input_tokens=accumulated_usage.input_tokens,
                    output_tokens=accumulated_usage.output_tokens,
                    reasoning_tokens=accumulated_usage.reasoning_tokens,
                    cached_input_tokens=accumulated_usage.cached_input_tokens,
                    subagent_id=event.subagent_id,
                )
            if isinstance(event, Complete):
                if not round_usage_folded:
                    accumulated_usage = _add_usage(accumulated_usage, event.usage)
                return replace(event, usage=accumulated_usage)
            return event

        def _reset() -> None:
            nonlocal round_usage_folded
            round_usage_folded = False

        return _fold, _reset

    for _round in range(action_rounds):
        stream = make_stream(list(tool_feedback), False)
        fold_usage, reset_usage = _make_usage_folder()
        reset_usage()

        pending_calls: list[ToolCall] = []
        provider_resolved: set[str] = set()
        relayed_terminal = False
        round_reasoning_parts: list[str] = []
        paused_by_provider = False
        async for event in stream:
            if isinstance(event, ToolCall):
                pending_calls.append(event)
                continue
            if isinstance(event, ReasoningDelta):
                round_reasoning_parts.append(event.text)
            elif isinstance(event, ToolResult):
                provider_resolved.add(event.tool_call_id)
            elif isinstance(event, AwaitingApproval):
                # Provider-emitted pause (e.g. fake TOOL_APPROVE): emit a
                # server-normalized pending ToolCall for the matching buffered
                # call so resume can find status=awaiting_approval (BE-004).
                matched = next(
                    (c for c in pending_calls if c.id == event.tool_call_id),
                    None,
                )
                if matched is None and pending_calls:
                    matched = pending_calls[0]
                if matched is not None:
                    yield _pending_approval_call(matched)
                yield fold_usage(event)
                paused_by_provider = True
                break
            elif isinstance(event, AnswerDelta):
                _note_answer(event)
                relayed_terminal = True
            elif isinstance(event, Complete):
                if tools_ran and not answer_emitted:
                    yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                    answer_emitted = True
                relayed_terminal = True
            yield fold_usage(event)
        if paused_by_provider:
            return

        unresolved = [c for c in pending_calls if c.id not in provider_resolved]
        if not unresolved:
            if tools_ran and not answer_emitted:
                yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                answer_emitted = True
                if not relayed_terminal:
                    yield Complete(usage=accumulated_usage)
            return

        round_results: list[ToolResult] = []
        round_reasoning = "".join(round_reasoning_parts) or None
        max_calls = max(1, settings.tool_max_calls_per_round)
        for i, call in enumerate(unresolved):
            # BE-012: reject excess calls in this round as failed results.
            if i >= max_calls:
                exec_result = ToolExecutionResult(
                    tool_call_id=call.id,
                    name=call.name,
                    status="failed",
                    output={},
                    error=(
                        f"Exceeded max tool calls per round ({max_calls}); "
                        "call was not executed."
                    ),
                    approval_state="not_required",
                )
                result_event = _to_result_event(call=call, exec_result=exec_result)
                if i == 0 and round_reasoning is not None:
                    result_event = replace(result_event, round_reasoning=round_reasoning)
                yield result_event
                round_results.append(result_event)
                continue
            spec = TOOL_REGISTRY.get(call.name)
            not_allowed = allowed is not None and call.name not in allowed
            if spec is None or not_allowed:
                if not_allowed and spec is not None:
                    exec_result = ToolExecutionResult(
                        tool_call_id=call.id,
                        name=call.name,
                        status="failed",
                        output={},
                        error=f"Tool {call.name!r} is not allowed in this context.",
                        approval_state="not_required",
                    )
                else:
                    with execute_tool_span(tool_name=call.name):
                        exec_result = await execute_tool(
                            ToolCallRequest(
                                id=call.id, name=call.name, input=call.input or {}
                            ),
                            timeout_seconds=settings.tool_timeout_seconds,
                        )
                result_event = _to_result_event(call=call, exec_result=exec_result)
                if i == 0 and round_reasoning is not None:
                    result_event = replace(result_event, round_reasoning=round_reasoning)
                yield result_event
                round_results.append(result_event)
                continue

            # Server-validated approval only. Provider-emitted
            # approval_state="approved" is NOT trusted here for execution —
            # execute_tool re-checks needs_approval. For the HITL pause path we
            # only treat an already-approved call as approved when the *server*
            # resume path seeded it; the loop still accepts the field for the
            # approved-resume seam, while execute_tool fails closed on gated
            # tools without approval_state="approved".
            already_approved = call.approval_state == "approved"
            if spec.needs_approval and not already_approved:
                # Emit exactly one server-normalized pending call, then pause
                # (BE-004). Do not relay the provider's running/not_required
                # shape — resume requires awaiting_approval + pending.
                yield _pending_approval_call(call)
                yield AwaitingApproval(tool_call_id=call.id)
                return

            yield ToolCall(
                id=call.id,
                name=call.name,
                label=call.label or spec.label,
                status="running",
                approval_state="not_required" if not already_approved else "approved",
                input=dict(call.input or {}),
                subagent_id=call.subagent_id,
            )
            approval_state: ToolApprovalState = (
                "approved" if already_approved else "not_required"
            )
            with execute_tool_span(tool_name=call.name):
                exec_result = await execute_tool(
                    ToolCallRequest(
                        id=call.id,
                        name=call.name,
                        input=call.input or {},
                        approval_state=approval_state,
                    ),
                    timeout_seconds=settings.tool_timeout_seconds,
                )
            result_event = _to_result_event(call=call, exec_result=exec_result)
            if i == 0 and round_reasoning is not None:
                result_event = replace(result_event, round_reasoning=round_reasoning)
            yield result_event
            round_results.append(result_event)

        tool_feedback.extend(round_results)
        tools_ran = True

        is_last_action = _round == action_rounds - 1
        if is_last_action and max_rounds > action_rounds:
            # Reserved final provider slot: suppress tools and force an answer.
            final_stream = make_stream(list(tool_feedback), True)
            fold_final, reset_final = _make_usage_folder()
            reset_final()
            relayed_terminal = False
            async for event in final_stream:
                if isinstance(event, AnswerDelta):
                    _note_answer(event)
                    relayed_terminal = True
                elif isinstance(event, Complete):
                    if tools_ran and not answer_emitted:
                        yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                        answer_emitted = True
                    relayed_terminal = True
                yield fold_final(event)
            if tools_ran and not answer_emitted:
                yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                answer_emitted = True
                if not relayed_terminal:
                    yield Complete(usage=accumulated_usage)
            return
        if is_last_action:
            # N=1: no reserved final pass. End with defensive fallback if needed.
            if tools_ran and not answer_emitted:
                yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                answer_emitted = True
                yield Complete(usage=accumulated_usage)
            return
