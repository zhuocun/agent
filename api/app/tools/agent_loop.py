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
  - Provider-internal / unknown name (not in ``TOOL_REGISTRY``, e.g.
    ``web_search``) → relay the ``ToolCall`` immediately so the FE can form
    live panels before later ``StatusUpdate`` / ``ToolResult`` frames, then
    either accept the provider's own ``ToolResult`` or synthesize a failed
    result for true unknowns.
  - APPROVAL-GATED and not yet approved → emit a server-normalized
    ``ToolCall(status="awaiting_approval", approval_state="pending")`` then an
    ``AwaitingApproval`` sentinel and STOP. The handler turns this into the
    paused terminal; a resume POST applies the decision. (Registry ToolCalls
    are NOT relayed raw — only the normalized pending/running shapes.)
  - Otherwise (auto / already-approved) → emit ``ToolCall(status="running")``,
    execute it (``execute_tool`` is timeout-wrapped), emit the ``ToolResult``,
    feed it back, and continue to the next round.
  - Not-in-allowlist registry tool → synthesize a failed ``ToolResult`` and
    feed it back (the model can recover next round); never execute.
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
from typing import Any, Protocol

import structlog

from app.config import DEFAULT_TOOL_RESULT_MAX_CHARS, Settings
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
from app.runtime.answer_policy import EMPTY_REPLY_FALLBACK, main_answer_is_empty
from app.runtime.bounds import (
    RunTripwire,
    allows_final_answer_pass,
    bound_tool_result_payload,
    bound_tool_result_text,
)
from app.runtime.loop_state import StopReason
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolApprovalState, ToolCallRequest, ToolExecutionResult

_log = structlog.get_logger(__name__)

# Separator the orchestrator's `namespace_tool_call_id` uses to bind a provider
# call id to a subagent (`worker-0::abc`). This loop is provider-scoped, so a
# seeded namespaced id must ALSO consume the raw id the provider will reissue —
# otherwise the settlement guard is inert in both agentic modes (FL-15 / H-002).
TOOL_CALL_ID_NAMESPACE_SEP = "::"


def _raw_tool_call_id(call_id: str) -> str:
    """Provider-scoped call id for a possibly `<subagent>::<id>` namespaced id."""
    _, sep, tail = call_id.partition(TOOL_CALL_ID_NAMESPACE_SEP)
    return tail if sep and tail else call_id


# Factory: given the tool results gathered so far and whether tools should be
# suppressed on the provider, build a fresh provider event stream for the next
# round. The handler supplies this so the loop stays provider-agnostic and the
# `Provider.stream` Protocol gains no tool params.
#
# `suppress_tools` is True ONLY for the compelled final pass and the empty-reply
# retry pass (see `run_agent_loop`): the factory must then advertise NO tools to
# the provider (`tools=None`) so a greedy provider that would otherwise keep
# requesting tools is forced to emit its final answer instead of returning a
# blank turn.
#
# `answer_nudge` (keyword-only) opts the pass into an extra answer-eliciting
# system nudge (empty-reply retry only). It is a `Protocol` — not a bare
# `Callable` alias — so the keyword-only parameter is part of the type and every
# closure the handler supplies (`_build_raw_stream`, the agentic `_make`
# closures) must accept it; positional call sites like `make_stream(feedback,
# True)` stay valid because the default is False.
class MakeStream(Protocol):
    def __call__(
        self,
        tool_feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]: ...


def make_usage_folder(
    tripwire: RunTripwire | None = None,
) -> tuple[
    Callable[[ProviderEvent], ProviderEvent],
    Callable[[], None],
    Callable[[], UsageUpdate],
]:
    """Shared per-stream usage folder (agent loop + plain-chat empty-retry).

    Returns ``(fold, reset, get_cumulative)``. The closure owns BOTH the
    cumulative accumulator (across every stream this turn) AND the per-round XOR
    latch that counts each round's usage exactly once (a round reports usage via
    EITHER a ``UsageUpdate`` OR the ``Complete.usage``, never both). ``fold``
    folds one event and returns the cumulative-usage variant of
    ``UsageUpdate``/``Complete`` (other events pass through unchanged); ``reset``
    clears the per-round latch and MUST be called before each new stream;
    ``get_cumulative`` reads the running total (e.g. for a synthesized terminal
    ``Complete``). Both `run_agent_loop` and `run_chat_with_empty_retry` use this
    so the XOR fold is identical across the two empty-retry paths.

    ``tripwire``: fed this loop's cumulative token total on every usage-bearing
    event. Feeding it HERE rather than at each call site is what keeps the run's
    token count exact — the fold is already the one place every provider usage
    sample passes through. ``None`` (plain chat) counts nothing.
    """
    accumulated = UsageUpdate()
    round_usage_folded = False

    def _note(usage: UsageUpdate) -> None:
        if tripwire is not None:
            tripwire.note_usage(usage)

    def _fold(event: ProviderEvent) -> ProviderEvent:
        nonlocal accumulated, round_usage_folded
        if isinstance(event, UsageUpdate):
            accumulated = _add_usage(accumulated, event)
            round_usage_folded = True
            _note(accumulated)
            return UsageUpdate(
                input_tokens=accumulated.input_tokens,
                output_tokens=accumulated.output_tokens,
                reasoning_tokens=accumulated.reasoning_tokens,
                cached_input_tokens=accumulated.cached_input_tokens,
                subagent_id=event.subagent_id,
            )
        if isinstance(event, Complete):
            if not round_usage_folded:
                accumulated = _add_usage(accumulated, event.usage)
            _note(accumulated)
            return replace(event, usage=accumulated)
        return event

    def _reset() -> None:
        nonlocal round_usage_folded
        round_usage_folded = False

    def _get_cumulative() -> UsageUpdate:
        return accumulated

    return _fold, _reset, _get_cumulative

# Sentinel prefixing the synthetic history turn that carries tool results back to
# the provider for the next round. The handler builds these turns via
# `tool_feedback_to_history`; the FAKE provider detects this prefix to know the
# tool has run and it should now answer (a real provider would instead receive a
# structured `role="tool"` message — that wiring is out of scope for the
# fake-only v1). Tool output remains untrusted: it is carried ONLY as this data
# turn, never spliced into instructions.
TOOL_FEEDBACK_SENTINEL = "[tool-results]"


def tool_feedback_to_history(
    results: list[ToolResult],
    *,
    max_chars: int = DEFAULT_TOOL_RESULT_MAX_CHARS,
) -> list[ChatMessage]:
    """Encode accumulated tool results as appended chat-history turns.

    One sentinel-prefixed assistant turn carrying the JSON results. Empty list
    when there are no results yet (round 1), so the first provider pass sees the
    unmodified history.

    This is where a tool result becomes model-visible, so it is also where each
    result's payload and error text are bounded to ``max_chars`` by construction
    (`runtime.bounds`): a result under the limit is passed through byte-for-byte,
    an over-size one is truncated with a visible marker rather than reaching the
    provider unbounded. ``max_chars <= 0`` disables the bound.
    """
    if not results:
        return []
    result_dicts = [
        {
            "toolCallId": r.tool_call_id,
            "name": r.name,
            "status": r.status,
            "output": bound_tool_result_payload(r.output, max_chars=max_chars),
            "error": (
                bound_tool_result_text(r.error, max_chars=max_chars)
                if r.error is not None
                else None
            ),
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
    server_approved_call_ids: Collection[str] | None = None,
    initial_tool_results: list[ToolResult] | None = None,
    allow_empty_retry: bool = True,
    inject_empty_fallback: bool = True,
    tripwire: RunTripwire | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Drive a bounded tool-calling loop over a provider event stream.

    Yields the same ``ProviderEvent`` union the handler already consumes, so the
    handler's accumulation / persistence is unchanged. Stops on: a round with no
    tool calls (relayed answer), an ``AwaitingApproval`` pause, or the
    ``tool_max_rounds`` bound (total provider invocations, including any
    suppress-tools final pass).

    ``allow_empty_retry``: whether this loop may spend the one-shot empty-reply
    retry at a genuinely-empty terminal. True (the default) for plain/tools chat,
    the agentic ``primary`` (`run_single`), and the aggregator synthesis draft.
    Deep-research WORKER subagents (and the quiet planner collect) pass False so a
    worker never burns an extra provider round — synthesis / the deterministic
    aggregate is the recovery there. The retry is ALSO gated by
    ``settings.empty_reply_retry_enabled`` (kill-switch) and the one-shot
    ``empty_retry_spent`` latch + ``invocations < tool_max_rounds`` budget; when
    it cannot fire, the terminal injects the static ``EMPTY_REPLY_FALLBACK`` as
    before. The reserved suppress-tools force-final pass is UNCONDITIONAL and
    nudge-free — it is NOT an empty retry (see below).

    ``inject_empty_fallback`` (FL-04 / ORCH-1): whether a genuinely-empty terminal
    may inject the static ``EMPTY_REPLY_FALLBACK`` text. True for callers whose
    loop output IS the user-facing answer (plain/tools chat, the agentic
    ``primary``). Deep-research workers and the aggregator pass False because they
    own their own recovery (``aggregate.synthesize`` / ``"(no answer)"``), and the
    non-blank filler would otherwise make their answer look non-empty — masking
    the degrade and shipping filler as a research finding. The terminal
    ``Complete`` is emitted either way, so the wire still sees exactly one
    terminal.

    ``allowed_tools``: when set, only those registry tool names may execute;
    others fail closed as unknown. ``None`` = full registry. Deep-research
    workers pass an empty collection (registry tools denied; provider-internal
    ``web_search`` is unaffected).

    ``server_approved_call_ids``: opaque call ids the *server* has authorized
    for gated-tool execution (pre-settlement resume capability). Each id is
    **single-use**: consuming it to execute removes it from the set. Provider-
    emitted ``approval_state="approved"`` is never trusted on its own.

    ``tripwire`` (doc §11.8): the run's plural trip conditions — wall clock,
    cumulative tokens, repeated tool calls, tool-failure breaker. ``None`` (the
    default) means no extra bounds, so every existing caller behaves exactly as
    before; the agentic orchestrator passes one handle per loop. When a bound
    fires the loop follows the degrade ladder: it stops opening new ACTION
    rounds, keeps everything already produced, and exits through the SAME
    terminal path as any other stop, so the wire still sees exactly one terminal
    ``Complete``. It never raises. A trip bounds SCHEDULING — the provider stream
    already in flight is drained normally rather than cut mid-event.

    The reserved final pass is the one exception, and only for the behavioral
    trips (`runtime.bounds.allows_final_answer_pass`): it advertises no tools, so
    it can neither loop nor extend the run, and it is what forces a grounded
    answer instead of the empty-reply fallback. A physical bound — the deadline,
    the token cap — refuses even that.

    ``initial_tool_results`` (BE-005): pre-seeded results from a HITL resume so
    the loop continues the same subagent with validated tool feedback instead of
    re-requesting the gated tool. Empty/None on every fresh run. Call ids that
    already appear here are treated as **consumed** (H-001 / O-001): a later
    provider reissue of the same id is rejected as a duplicate and never
    re-executed, even if also listed in ``server_approved_call_ids``.
    """
    tool_feedback: list[ToolResult] = list(initial_tool_results or [])
    max_rounds = max(1, settings.tool_max_rounds)
    # Reserve the last provider slot for a suppress-tools final pass when N>1.
    # With N=1 there is no reserved final — a tool request on that sole round
    # ends without an extra provider call (defensive empty fallback if needed).
    action_rounds = max_rounds if max_rounds == 1 else max_rounds - 1
    answer_emitted = False
    # One-shot empty-reply retry budget (turn-wide for this loop invocation).
    empty_retry_spent = False
    # Total provider streams opened this loop (action rounds + reserved pass +
    # any empty-retry pass). The empty retry may fire only while
    # `invocations < max_rounds`, so it can never stack on the reserved pass
    # (which consumes the last slot) or on N=1 (the sole round exhausts it).
    invocations = 0
    fold_usage, reset_usage, get_cumulative = make_usage_folder(tripwire)
    allowed: set[str] | None = None if allowed_tools is None else set(allowed_tools)
    approved_ids: set[str] = (
        set(server_approved_call_ids) if server_approved_call_ids is not None else set()
    )
    # Settled / seeded results consume their call ids permanently for this loop.
    # FL-15: seeds arrive namespaced from the orchestrator (`worker-0::abc`) while
    # the provider reissues the raw id, so consume BOTH spellings.
    consumed_ids: set[str] = set()
    for seeded in tool_feedback:
        if not seeded.tool_call_id:
            continue
        consumed_ids.add(seeded.tool_call_id)
        consumed_ids.add(_raw_tool_call_id(seeded.tool_call_id))
    approved_ids -= consumed_ids

    def _note_answer(delta: AnswerDelta) -> None:
        nonlocal answer_emitted
        # Markup-aware: a delta that strips to empty (leaked tool-call markup or
        # whitespace) is NOT a written answer, so the terminal fallback still
        # fires. Shared with the handler guard via `main_answer_is_empty`.
        if not main_answer_is_empty(delta.text):
            answer_emitted = True

    def _can_retry() -> bool:
        """Whether the one-shot empty-reply retry may fire at an empty terminal."""
        return (
            settings.empty_reply_retry_enabled
            and allow_empty_retry
            and not empty_retry_spent
            and invocations < max_rounds
            # A tripped run may not open another provider stream, and the retry
            # is one: the empty terminal falls straight to the static fallback.
            and (tripwire is None or tripwire.tripped is None)
        )

    async def _emit_empty_terminal() -> AsyncIterator[ProviderEvent]:
        """Genuinely-empty terminal: retry once (if allowed) else static fallback.

        Precondition: no written answer has been emitted this turn. When a retry
        is allowed it runs ONE suppress-tools, answer-eliciting pass (nudge on)
        over the same history + accumulated tool feedback, folding its usage and
        applying the markup-drop rule; its own ``Complete`` is suppressed so the
        wire sees exactly one terminal ``Complete`` — synthesized here carrying
        the ``empty_retry`` / ``empty_retry_recovered`` markers. If the retry is
        disallowed / still empty, the static ``EMPTY_REPLY_FALLBACK`` is injected
        exactly once as before — unless ``inject_empty_fallback`` is False, in
        which case the terminal ``Complete`` ships with no answer text (FL-04).
        """
        nonlocal answer_emitted, empty_retry_spent, invocations
        if _can_retry():
            empty_retry_spent = True
            invocations += 1
            if tripwire is not None:
                tripwire.note_invocation()
            reset_usage()
            retry_stream = make_stream(list(tool_feedback), True, answer_nudge=True)
            async for event in retry_stream:
                if isinstance(event, AnswerDelta):
                    _note_answer(event)
                    # Same markup-drop as the action rounds: a markup-only /
                    # whitespace delta ahead of the fallback would be wiped by
                    # the FE truncate-from-first-marker scrub, so drop it while
                    # no real answer has been emitted.
                    if main_answer_is_empty(event.text) and not answer_emitted:
                        continue
                    yield event
                    continue
                if isinstance(event, Complete):
                    # Fold usage but suppress the retry's Complete — the single
                    # terminal Complete is emitted below with the markers.
                    fold_usage(event)
                    continue
                yield fold_usage(event)
            if answer_emitted:
                yield Complete(
                    usage=get_cumulative(),
                    empty_retry=True,
                    empty_retry_recovered=True,
                )
                return
            if inject_empty_fallback:
                yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
            answer_emitted = True
            yield Complete(
                usage=get_cumulative(),
                empty_retry=True,
                empty_retry_recovered=False,
            )
            return
        # Retry not allowed (kill-switch off, worker, spent, or budget
        # exhausted) → static fallback exactly once, as before.
        if inject_empty_fallback:
            yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
        answer_emitted = True
        yield Complete(usage=get_cumulative())

    for _round in range(action_rounds):
        stream = make_stream(list(tool_feedback), False)
        invocations += 1
        if tripwire is not None:
            tripwire.note_invocation()
        reset_usage()

        pending_calls: list[ToolCall] = []
        provider_resolved: set[str] = set()
        relayed_terminal = False
        # Narrower than `relayed_terminal` (which an AnswerDelta also raises):
        # whether THIS round already put a `Complete` on the wire. Only a trip
        # reads it, to decide whether the degrade still owes the wire a terminal.
        complete_relayed = False
        round_reasoning_parts: list[str] = []
        paused_by_provider = False
        async for event in stream:
            if isinstance(event, ToolCall):
                pending_calls.append(event)
                # Provider-internal tools (not in TOOL_REGISTRY) self-resolve
                # in the same stream — typically ToolCall → StatusUpdate →
                # ToolResult. Relay immediately so the FE can show live
                # web-search status; registry tools are emitted later in
                # server-normalized running / awaiting_approval form (BE-004).
                if event.name not in TOOL_REGISTRY:
                    yield event
                continue
            if isinstance(event, ReasoningDelta):
                round_reasoning_parts.append(event.text)
            elif isinstance(event, ToolResult):
                # FL-26 / ORCH-9: a provider-supplied result NEVER resolves a
                # REGISTRY tool — honoring it would bypass the approval gate and
                # the server executor (untrusted-output rule 2). Registry calls
                # stay `unresolved` so the gate decides; the provider's result is
                # neither relayed nor fed back.
                resolved_call = next(
                    (c for c in pending_calls if c.id == event.tool_call_id), None
                )
                if resolved_call is not None and resolved_call.name in TOOL_REGISTRY:
                    _log.warning(
                        "agent_loop.provider_result_for_registry_tool_ignored",
                        tool_call_id=event.tool_call_id,
                        name=resolved_call.name,
                    )
                    continue
                provider_resolved.add(event.tool_call_id)
            elif isinstance(event, AwaitingApproval):
                # Provider-emitted pause (e.g. fake TOOL_APPROVE): emit a
                # server-normalized pending ToolCall for the matching buffered
                # call so resume can find status=awaiting_approval (BE-004).
                matched = next(
                    (c for c in pending_calls if c.id == event.tool_call_id),
                    None,
                )
                if matched is None:
                    # FL-27 / ORCH-8: never park a pause on a call the provider
                    # did not request this round — the id has no persisted
                    # `tool_call` part, so resume could never settle it. Fail the
                    # unmatched id and keep draining instead.
                    _log.warning(
                        "agent_loop.unmatched_provider_pause_id",
                        tool_call_id=event.tool_call_id,
                    )
                    yield ToolResult(
                        tool_call_id=event.tool_call_id,
                        name="unknown",
                        status="failed",
                        approval_state="not_required",
                        summary="Unmatched approval request.",
                        error=(
                            "The provider requested approval for a tool call id "
                            "that was not issued this round; it was not executed."
                        ),
                    )
                    continue
                yield _pending_approval_call(matched)
                yield fold_usage(event)
                paused_by_provider = True
                break
            elif isinstance(event, AnswerDelta):
                _note_answer(event)
                # Drop a markup-only / whitespace delta ONLY when no written
                # answer has been emitted yet (`answer_emitted` still False):
                # such a turn strips to empty for the FE and the terminal
                # fallback will fire, so relaying the raw markup ahead of it
                # would wipe the fallback under the FE truncate-from-first-marker
                # scrub. Once real prose HAS been emitted (prose + trailing
                # markup, e.g. a stubborn provider dumping tool tokens after a
                # real answer) the markup is kept and relayed: the answer is
                # non-empty, no fallback fires, and the raw markup must persist
                # so the FE render-time scrub is what hides it on reload/share.
                if main_answer_is_empty(event.text) and not answer_emitted:
                    continue
                relayed_terminal = True
            elif isinstance(event, Complete):
                if not answer_emitted:
                    # Defer a blank Complete: fold its usage but do NOT relay it —
                    # the post-stream terminal decision runs retry-or-static and
                    # emits the single terminal Complete (carrying the empty-retry
                    # markers) so the wire never sees a premature blank Complete.
                    fold_usage(event)
                    continue
                relayed_terminal = True
                complete_relayed = True
            yield fold_usage(event)
        if paused_by_provider:
            return

        unresolved = [c for c in pending_calls if c.id not in provider_resolved]
        if not unresolved:
            # Genuinely-empty terminal (no tool calls this round): a blank
            # Complete deferred above, or a stream that ended with no written
            # answer. Route through the single retry-or-static decision.
            if not answer_emitted:
                async for terminal_event in _emit_empty_terminal():
                    yield terminal_event
            return

        round_results: list[ToolResult] = []
        round_reasoning = "".join(round_reasoning_parts) or None
        max_calls = max(1, settings.tool_max_calls_per_round)
        for i, call in enumerate(unresolved):
            if tripwire is not None:
                # Every call the provider asked for, whether it goes on to
                # execute or is refused: a model that keeps re-requesting a
                # denied tool is exactly the cheap loop this detects.
                tripwire.note_tool_call(call.name, call.input)
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
            # approval_state="approved" is NEVER authority — only a server-
            # issued capability (`server_approved_call_ids`) authorizes a gated
            # tool, and only once. Already-settled ids (initial_tool_results)
            # are never re-executable (H-001 / O-001).
            if call.id in consumed_ids and spec.needs_approval:
                exec_result = ToolExecutionResult(
                    tool_call_id=call.id,
                    name=call.name,
                    status="failed",
                    output={},
                    summary="Duplicate tool call after settlement.",
                    error=(
                        "This tool call id was already settled and cannot be "
                        "executed again; refusing duplicate side effect."
                    ),
                    approval_state="rejected",
                )
                result_event = _to_result_event(call=call, exec_result=exec_result)
                if i == 0 and round_reasoning is not None:
                    result_event = replace(result_event, round_reasoning=round_reasoning)
                yield result_event
                round_results.append(result_event)
                continue

            server_approved = call.id in approved_ids
            if spec.needs_approval and not server_approved:
                # Emit exactly one server-normalized pending call, then pause
                # (BE-004). Do not relay the provider's running/not_required
                # shape — resume requires awaiting_approval + pending.
                yield _pending_approval_call(call)
                yield AwaitingApproval(tool_call_id=call.id)
                return

            if server_approved:
                # Single-use capability: consume before execute so a later
                # provider reissue in this loop cannot re-run the side effect.
                approved_ids.discard(call.id)
                consumed_ids.add(call.id)

            yield ToolCall(
                id=call.id,
                name=call.name,
                label=call.label or spec.label,
                status="running",
                approval_state="approved" if server_approved else "not_required",
                input=dict(call.input or {}),
                subagent_id=call.subagent_id,
            )
            approval_state: ToolApprovalState = (
                "approved" if server_approved else "not_required"
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
            if spec.needs_approval:
                consumed_ids.add(call.id)

        tool_feedback.extend(round_results)

        tripped: StopReason | None = None
        if tripwire is not None:
            for settled in round_results:
                tripwire.note_tool_result(settled.status)
            tripped = tripwire.check()

        is_last_action = _round == action_rounds - 1
        # Whether a tool-suppressed pass is still available to force an answer.
        # `max_rounds == 1` reserves none, so there is nothing for a trip to fall
        # through to.
        has_final_pass = max_rounds > action_rounds
        if tripped is not None and not (
            has_final_pass and allows_final_answer_pass(tripped)
        ):
            # Degrade ladder (doc §11.8): stop scheduling new actions — no further
            # action round and, for a PHYSICAL bound, not even the reserved pass —
            # keep the partials already produced, and end through the same terminal
            # decision every other stop uses, so the wire sees exactly one terminal
            # Complete. The trip is NAMED in the tripwire's log line and, for an
            # agentic run, on the run summary's partial label.
            if not answer_emitted:
                async for terminal_event in _emit_empty_terminal():
                    yield terminal_event
            elif not complete_relayed:
                yield Complete(usage=get_cumulative())
            return

        # A behavioral trip falls THROUGH to the reserved pass below, from
        # whichever round it fired on: that pass advertises no tools, so it cannot
        # repeat the call that tripped or open a further round, and skipping it
        # would trade the grounded answer it exists to force for no safety at all
        # (it is also the degrade `tool_rounds_exhausted` already gets, and both
        # reasons share the `partial_limit` outcome).
        if (is_last_action or tripped is not None) and has_final_pass:
            # Reserved final provider slot: suppress tools and force an answer.
            # UNCONDITIONAL force-final on tool exhaustion — NOT an empty retry:
            # it is nudge-free (`make_stream(..., True)` with no `answer_nudge`)
            # and fires regardless of `empty_reply_retry_enabled`. If it ends
            # empty the invocation budget is exhausted (`invocations ==
            # max_rounds`) so the terminal goes straight to static, never a
            # second compelled pass.
            final_stream = make_stream(list(tool_feedback), True)
            invocations += 1
            if tripwire is not None:
                tripwire.note_invocation()
            reset_usage()
            relayed_terminal = False
            async for event in final_stream:
                if isinstance(event, AnswerDelta):
                    _note_answer(event)
                    # Drop a markup-only / whitespace delta ONLY when no written
                    # answer has been emitted yet (see the action-round loop):
                    # then the fallback fires and the raw markup must not precede
                    # it. After real prose, trailing markup is kept and relayed
                    # so the prose + raw markup persists for the FE scrub.
                    if main_answer_is_empty(event.text) and not answer_emitted:
                        continue
                    relayed_terminal = True
                elif isinstance(event, Complete):
                    if not answer_emitted:
                        if inject_empty_fallback:
                            yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                        # Latch the terminal decision either way so a suppressed
                        # fallback cannot be re-decided below (FL-04).
                        answer_emitted = True
                    relayed_terminal = True
                yield fold_usage(event)
            if not answer_emitted:
                if inject_empty_fallback:
                    yield AnswerDelta(text=EMPTY_REPLY_FALLBACK)
                answer_emitted = True
                if not relayed_terminal:
                    yield Complete(usage=get_cumulative())
            return
        if is_last_action:
            # N=1: no reserved final pass. This is a genuinely-empty terminal
            # after a tool round; route it through the single retry-or-static
            # decision. With N=1 the budget (`invocations < max_rounds`) is
            # already spent, so it falls straight to the static fallback.
            if not answer_emitted:
                async for terminal_event in _emit_empty_terminal():
                    yield terminal_event
            return
