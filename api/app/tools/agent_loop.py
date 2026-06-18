"""Provider-agnostic, bounded agent loop for backend-side tool calling (HITL).

Generalizes the shape of the provider-internal web_search loop (see
``app/providers/openai.py``) into a standalone orchestrator that drives ANY
provider's ``ToolCall`` events through the built-in tool registry — including
the human-in-the-loop (HITL) approval gate. ``web_search`` stays
provider-internal and UNTOUCHED; this loop is additive and, in v1, drives only
the FAKE provider.

Round model (mirrors ``_MAX_SEARCH_ROUNDS``): one round = one provider stream.
``make_stream(tool_feedback, suppress_tools)`` returns a fresh provider event
iterator given the tool results accumulated so far (the handler threads them back
via ``history``, since the ``Provider.stream`` Protocol intentionally carries no
tool params) and whether tools should be advertised to the provider this round.
For each round:

- Relay every non-``ToolCall`` event (reasoning / answer / status / sources /
  usage / complete) straight through.
- For each ``ToolCall`` the provider requests:
  - UNKNOWN tool → synthesize a failed ``ToolResult`` and feed it back (the
    model can recover next round); never execute.
  - APPROVAL-GATED and not yet approved → emit
    ``ToolCall(status="awaiting_approval", approval_state="pending")`` then an
    ``AwaitingApproval`` sentinel and STOP. The handler turns this into the
    paused terminal; a resume POST applies the decision.
  - Otherwise (auto / already-approved) → emit ``ToolCall(status="running")``,
    execute it (``execute_tool`` is timeout-wrapped), emit the ``ToolResult``,
    feed it back, and continue to the next round.
- A round that requests NO tool calls is terminal: its content was the final
  answer; relay it and stop.

The loop is hard-bounded by ``settings.tool_max_rounds`` so it can never spin
forever even if the provider keeps requesting tools.

SECURITY: tool output is untrusted (a prompt-injection surface). It is fed back
ONLY as structured tool data via ``make_stream``'s feedback channel, never spliced
into instructions. The approval gate is enforced here AND re-checked at the
resume route — a forged approval cannot reach a non-gated/unknown tool.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable

from app.config import Settings
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    ChatMessage,
    Complete,
    ProviderEvent,
    ToolCall,
    ToolResult,
)
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolApprovalState, ToolCallRequest

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
    payload = json.dumps(
        [
            {
                "toolCallId": r.tool_call_id,
                "name": r.name,
                "status": r.status,
                "output": r.output,
                "error": r.error,
            }
            for r in results
        ],
        separators=(",", ":"),
    )
    return [ChatMessage(role="assistant", text=f"{TOOL_FEEDBACK_SENTINEL} {payload}")]


def parse_tool_feedback_history(
    history: list[ChatMessage],
) -> tuple[list[ChatMessage], list[dict[str, object]]]:
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
    for message in history:
        if message.role == "assistant" and message.text.startswith(TOOL_FEEDBACK_SENTINEL):
            payload = message.text[len(TOOL_FEEDBACK_SENTINEL) :].strip()
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, list):
                results.extend(item for item in parsed if isinstance(item, dict))
            continue
        clean.append(message)
    return clean, results


def _to_result_event(*, call: ToolCall, exec_result: object) -> ToolResult:
    """Build a wire ``ToolResult`` event from a ``ToolExecutionResult``."""
    from app.tools.protocol import ToolExecutionResult

    assert isinstance(exec_result, ToolExecutionResult)
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


async def run_agent_loop(
    *,
    make_stream: MakeStream,
    settings: Settings,
) -> AsyncIterator[ProviderEvent]:
    """Drive a bounded tool-calling loop over a provider event stream.

    Yields the same ``ProviderEvent`` union the handler already consumes, so the
    handler's accumulation / persistence is unchanged. Stops on: a round with no
    tool calls (relayed answer), an ``AwaitingApproval`` pause, or the
    ``tool_max_rounds`` bound.
    """
    tool_feedback: list[ToolResult] = []
    max_rounds = max(1, settings.tool_max_rounds)

    for _round in range(max_rounds):
        is_final_round = _round == max_rounds - 1
        stream = make_stream(list(tool_feedback), False)

        # Every provider event is RELAYED as-is (the provider's own ToolCall IS
        # the request — the loop fulfills it, it never re-emits it). We buffer the
        # calls that still need fulfilling and the ids the provider self-resolved
        # this round (a provider may emit its own ToolResult, e.g. an internal
        # tool); those are skipped so we never double-execute. We also track
        # whether this round relayed any terminal content (answer / Complete) so
        # the compelled final pass never ends the turn blank.
        pending_calls: list[ToolCall] = []
        provider_resolved: set[str] = set()
        relayed_terminal = False
        async for event in stream:
            if isinstance(event, ToolCall):
                pending_calls.append(event)
            elif isinstance(event, ToolResult):
                provider_resolved.add(event.tool_call_id)
            elif isinstance(event, AwaitingApproval):
                # The provider itself decided to pause (it emitted the gated
                # ToolCall before this). Relay and stop — do NOT execute.
                yield event
                return
            elif isinstance(event, (AnswerDelta, Complete)):
                relayed_terminal = True
            yield event

        # Calls the loop must still fulfill this round.
        unresolved = [c for c in pending_calls if c.id not in provider_resolved]
        if not unresolved:
            # No tool work left → the relayed content WAS the final answer.
            return

        round_results: list[ToolResult] = []
        for call in unresolved:
            spec = TOOL_REGISTRY.get(call.name)
            if spec is None:
                # Unknown tool: synthesize a failed result and feed it back so a
                # later round can recover. Never execute.
                exec_result = await execute_tool(
                    ToolCallRequest(id=call.id, name=call.name, input=call.input or {})
                )
                result_event = _to_result_event(call=call, exec_result=exec_result)
                yield result_event
                round_results.append(result_event)
                continue

            already_approved = call.approval_state == "approved"
            if spec.needs_approval and not already_approved:
                # HITL gate, loop-synthesized (the provider requested a gated tool
                # without pausing itself). The pending ToolCall was already
                # relayed above; emit the AwaitingApproval sentinel to end the
                # turn. The handler turns this into the paused terminal.
                yield AwaitingApproval(tool_call_id=call.id)
                return

            # Auto / already-approved tool: run it (timeout-wrapped) and emit the
            # result. The request ToolCall was already relayed by the provider.
            approval_state: ToolApprovalState = (
                "approved" if already_approved else "not_required"
            )
            exec_result = await execute_tool(
                ToolCallRequest(
                    id=call.id,
                    name=call.name,
                    input=call.input or {},
                    approval_state=approval_state,
                )
            )
            result_event = _to_result_event(call=call, exec_result=exec_result)
            yield result_event
            round_results.append(result_event)

        tool_feedback.extend(round_results)

        if is_final_round:
            # Loop bound reached with tools still being requested. Do one final
            # provider pass with the results fed back AND tools SUPPRESSED at the
            # provider (`suppress_tools=True` → the factory advertises no tools),
            # so a greedy provider that would otherwise keep emitting ToolCalls
            # (and no answer) is forced to produce its final answer. Events relay
            # straight through — no ToolCall filtering — because suppression
            # prevents them at the source.
            final_stream = make_stream(list(tool_feedback), True)
            async for event in final_stream:
                if isinstance(event, (AnswerDelta, Complete)):
                    relayed_terminal = True
                yield event
            if not relayed_terminal:
                # Defensive backstop: even with tools suppressed the provider
                # produced no answer / Complete (a pathologically greedy or empty
                # provider). NEVER end the turn blank — emit a minimal answer and
                # a Complete so the handler commits a non-empty, terminated turn.
                yield AnswerDelta(
                    text=(
                        "I wasn't able to finish using the tools, but here's the "
                        "best answer I can give based on what I gathered."
                    )
                )
                yield Complete()
            return
