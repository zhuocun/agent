"""The loop-state vocabulary's two mappings must be total and must name a unit.

`app/runtime/loop_state.py` is the typed phase / outcome / stop-reason vocabulary
from `docs/research/2026-08-03/agent-architecture-state-of-the-art.md` §1.3
decision 1 and §3.1. These tests pin the properties the rest of the runtime will
lean on once it is wired up:

- **Total.** Every `StopReason` member resolves to exactly one `RunOutcome` and
  exactly one `CountedEvent`, and every result is a declared member of its alias.
- **Every bound names its counted event.** No member returns an empty or missing
  label; `"none"` is a deliberate answer for the stops where no bound fired.
- **The exhaustiveness guard fires.** An unmapped reason raises rather than
  falling through to a plausible-looking default, which is what makes adding a
  member without a mapping a hard failure instead of silent mislabeling.
- **A protocol stop is not acceptance** (§1.3 decision 2): it is `completed` as a
  loop outcome and counts nothing.
"""

from __future__ import annotations

from typing import cast

import pytest

from app.runtime.loop_state import (
    COUNTED_EVENTS,
    LOOP_PHASES,
    RUN_OUTCOMES,
    STOP_REASONS,
    CountedEvent,
    LoopPhase,
    RunOutcome,
    StopReason,
    counted_event_for,
    outcome_for,
)

EXPECTED_PHASES = {
    "sampling",
    "awaiting_tool",
    "executing_tool",
    "awaiting_approval",
    "terminal",
}

EXPECTED_OUTCOMES = {
    "completed",
    "partial_limit",
    "interrupted",
    "failed",
    "awaiting_input",
}

EXPECTED_MAPPING: dict[StopReason, tuple[RunOutcome, CountedEvent]] = {
    "protocol_stop": ("completed", "none"),
    "tool_rounds_exhausted": ("partial_limit", "provider_invocations"),
    "wall_clock_exceeded": ("partial_limit", "seconds"),
    "token_cap_exceeded": ("partial_limit", "tokens"),
    "usd_cap_exceeded": ("partial_limit", "usd"),
    "repeated_tool_calls": ("partial_limit", "tool_call_hash"),
    "consecutive_tool_failures": ("partial_limit", "tool_failures"),
    "awaiting_approval": ("awaiting_input", "human"),
    "user_stopped": ("interrupted", "human"),
    "provider_error": ("failed", "none"),
}


def test_vocabulary_matches_the_documented_sets() -> None:
    assert LOOP_PHASES == EXPECTED_PHASES
    assert RUN_OUTCOMES == EXPECTED_OUTCOMES
    assert set(EXPECTED_MAPPING) == STOP_REASONS


def test_outcome_mapping_is_total_over_every_stop_reason() -> None:
    for stop_reason in STOP_REASONS:
        outcome = outcome_for(stop_reason)
        assert outcome in RUN_OUTCOMES
        assert outcome == EXPECTED_MAPPING[stop_reason][0]


def test_every_stop_reason_names_a_non_empty_counted_event() -> None:
    for stop_reason in STOP_REASONS:
        counted = counted_event_for(stop_reason)
        assert counted
        assert counted in COUNTED_EVENTS
        assert counted == EXPECTED_MAPPING[stop_reason][1]


def test_bound_stops_name_the_unit_they_counted() -> None:
    """A `partial_limit` is only readable if it says what filled up."""
    bounded = [r for r in STOP_REASONS if outcome_for(r) == "partial_limit"]
    assert bounded
    for stop_reason in bounded:
        assert counted_event_for(stop_reason) != "none"


def test_protocol_stop_is_a_loop_outcome_and_counts_nothing() -> None:
    assert outcome_for("protocol_stop") == "completed"
    assert counted_event_for("protocol_stop") == "none"


@pytest.mark.parametrize("unmapped", ["", "invented_reason", "PROTOCOL_STOP"])
def test_exhaustiveness_guard_fires_for_an_unmapped_reason(unmapped: str) -> None:
    stop_reason = cast(StopReason, unmapped)
    with pytest.raises(AssertionError):
        outcome_for(stop_reason)
    with pytest.raises(AssertionError):
        counted_event_for(stop_reason)


def test_phase_alias_accepts_only_declared_phases() -> None:
    terminal: LoopPhase = "terminal"
    assert terminal in LOOP_PHASES
    assert cast(LoopPhase, "paused") not in LOOP_PHASES
