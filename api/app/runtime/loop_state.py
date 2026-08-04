"""The typed loop-state and stop vocabulary for one bounded run.

`docs/research/2026-08-03/agent-architecture-state-of-the-art.md` §1.3 decision 1
asks for "one typed bounded loop; explicit `sampling / awaiting_tool /
executing_tool / awaiting_approval / terminal`; one writer", and §3.1 asks for the
outcomes `completed`, `partial_limit`, `interrupted`, `failed`, `awaiting_input`
plus the rule that "every bound must name its counted event". `LoopPhase`,
`RunOutcome` and `StopReason` are that vocabulary, and `outcome_for` /
`counted_event_for` are the only readings of it: a stop reason resolves to exactly
one outcome and names exactly one counted event, so a log line or span attribute
can always say what was counted rather than reporting a bare limit.

Two invariants this module encodes:

- **A protocol stop is NOT acceptance** (§1.3 decision 2). `protocol_stop` means
  the model emitted a valid final message and the model-directed loop ended; it
  resolves to `completed` as a *loop* outcome only. Whether the answer is good is
  decided separately, afterwards, by acceptance/verification — never by this
  mapping.
- **Every mapping is total.** `outcome_for` and `counted_event_for` narrow over
  the whole `StopReason` alias and end in `assert_never`, so a new member with no
  mapping fails mypy statically and raises at runtime instead of defaulting to a
  plausible-looking outcome.

`counted_event_for` returns `"none"` for the reasons that end a run without a
bound firing (a protocol stop, a provider error): those name no counted unit, and
saying so is different from omitting the label.

This module holds pure types and pure functions only, with no imports from the
provider, streaming, tools or agentic layers. `app/runtime/bounds.py` is its
first consumer: the run's trip conditions latch one of these `StopReason`
members and read both mappings to log what they counted. Wiring the vocabulary
into the SSE schemas and tracing is still separate work.
"""

from __future__ import annotations

from typing import Literal, assert_never, get_args

# The explicit phases of the bounded loop (§1.3 decision 1). `awaiting_tool` is
# the model having requested a call; `executing_tool` is the server running it;
# `awaiting_approval` is a human gate parked between the two; `terminal` is the
# single exit.
LoopPhase = Literal[
    "sampling",
    "awaiting_tool",
    "executing_tool",
    "awaiting_approval",
    "terminal",
]

# How a run ENDED, as reported (§3.1). `partial_limit` is a labeled partial, not a
# failure: a bound fired and whatever was produced still stands.
RunOutcome = Literal[
    "completed",
    "partial_limit",
    "interrupted",
    "failed",
    "awaiting_input",
]

# WHY a run ended. One reason per stop, each naming its counted event.
StopReason = Literal[
    "protocol_stop",
    "tool_rounds_exhausted",
    "wall_clock_exceeded",
    "token_cap_exceeded",
    "usd_cap_exceeded",
    "repeated_tool_calls",
    "consecutive_tool_failures",
    "awaiting_approval",
    "user_stopped",
    "provider_error",
]

# The unit a bound counted. Short machine strings, safe as a span attribute or a
# structlog field value.
CountedEvent = Literal[
    "provider_invocations",
    "seconds",
    "tokens",
    "usd",
    "tool_call_hash",
    "tool_failures",
    "human",
    "none",
]

LOOP_PHASES: frozenset[LoopPhase] = frozenset(get_args(LoopPhase))
RUN_OUTCOMES: frozenset[RunOutcome] = frozenset(get_args(RunOutcome))
STOP_REASONS: frozenset[StopReason] = frozenset(get_args(StopReason))
COUNTED_EVENTS: frozenset[CountedEvent] = frozenset(get_args(CountedEvent))


def outcome_for(stop_reason: StopReason) -> RunOutcome:
    """The one outcome a stop reason resolves to (§3.1).

    Total over `StopReason`. `protocol_stop` resolves to `completed` as a loop
    outcome and says nothing about acceptance (§1.3 decision 2).
    """
    match stop_reason:
        case "protocol_stop":
            return "completed"
        case (
            "tool_rounds_exhausted"
            | "wall_clock_exceeded"
            | "token_cap_exceeded"
            | "usd_cap_exceeded"
            | "repeated_tool_calls"
            | "consecutive_tool_failures"
        ):
            return "partial_limit"
        case "awaiting_approval":
            return "awaiting_input"
        case "user_stopped":
            return "interrupted"
        case "provider_error":
            return "failed"
    assert_never(stop_reason)


def counted_event_for(stop_reason: StopReason) -> CountedEvent:
    """The unit this stop reason counted (§3.1: "every bound must name its
    counted event").

    Total over `StopReason`. `"none"` is an answer, not a gap: a protocol stop and
    a provider error end the run without any bound firing.
    """
    match stop_reason:
        case "tool_rounds_exhausted":
            return "provider_invocations"
        case "wall_clock_exceeded":
            return "seconds"
        case "token_cap_exceeded":
            return "tokens"
        case "usd_cap_exceeded":
            return "usd"
        case "repeated_tool_calls":
            return "tool_call_hash"
        case "consecutive_tool_failures":
            return "tool_failures"
        case "awaiting_approval" | "user_stopped":
            return "human"
        case "protocol_stop" | "provider_error":
            return "none"
    assert_never(stop_reason)
