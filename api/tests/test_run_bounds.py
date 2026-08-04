"""The run's PLURAL trip conditions, and the one place they are decided.

`app/runtime/bounds.py` implements
`docs/research/2026-08-03/agent-architecture-state-of-the-art.md` §11.8 ("trips
must be plural … every stop writing a structured log because unlogged breakers
cannot be tuned"), §17 (the starting values) and §7 (bound a tool result by
construction). These tests pin the properties the runtime leans on:

- **Each trip fires at its boundary and not before.** A bound that fires early
  converts healthy turns into labeled partials; one that fires late is not a
  bound. Every wall-clock assertion runs on a hand-advanced clock so the
  boundary is exact rather than timing-dependent.
- **Exactly one decider, exactly one log line.** `check()` latches the first
  reason, so it can be called on every event and still write one
  `agent_loop.tripped` / `agentic.tripped` warning naming the stop reason, its
  counted event, the observed value and the limit.
- **The `loop_state` mappings are total against these real call sites.** Every
  reason the tripwire can latch resolves through `outcome_for` /
  `counted_event_for` to a `partial_limit` that names its unit.
- **Default-safe.** A loop driven with no tripwire and the same loop driven with
  an all-disabled one emit the identical event sequence.
- **The degrade ladder holds** (§11.8): a trip stops new provider rounds, keeps
  the work already produced, names what tripped, and still leaves the wire with
  exactly one terminal `Complete`.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import pytest
import structlog

from app.agentic.orchestrator import run_orchestrator
from app.config import DEFAULT_TOOL_RESULT_MAX_CHARS, Settings
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    RunCost,
    SubagentDone,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.runtime import bounds as bounds_mod
from app.runtime.answer_policy import EMPTY_REPLY_FALLBACK
from app.runtime.bounds import (
    TRUNCATED_OUTPUT_KEY,
    RunBounds,
    RunTripwire,
    allows_final_answer_pass,
    bound_tool_result_payload,
    bound_tool_result_text,
    tool_call_digest,
)
from app.runtime.loop_state import STOP_REASONS, counted_event_for, outcome_for
from app.tools import builtin
from app.tools.agent_loop import run_agent_loop, tool_feedback_to_history
from app.tools.protocol import ToolCallRequest, ToolExecutionResult

# The four reasons this module's `check()` can latch. Kept explicit so a fifth
# one cannot be added without deciding what it counts and how it degrades.
TRIPWIRE_REASONS = (
    "wall_clock_exceeded",
    "token_cap_exceeded",
    "repeated_tool_calls",
    "consecutive_tool_failures",
)


class _FakeClock:
    """A monotonic clock the test advances by hand.

    Wall-clock assertions have to be exact at the boundary, which a real clock
    cannot give: `sleep`-based tests either flake or only ever prove the trip
    fires eventually.
    """

    def __init__(self, now: float = 1_000.0) -> None:
        self._now = now

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    """Swap the bounds module's clock. Install BEFORE building a tripwire —
    the start instant is read in `__init__`."""
    fake = _FakeClock()
    monkeypatch.setattr(bounds_mod, "time", fake)
    return fake


@pytest.fixture
def frozen_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `get_current_time` return a fixed payload.

    The identity comparison below is only meaningful if the tool's own output is
    stable — a real clock reading differs between the two runs regardless of the
    tripwire.
    """

    async def _fixed(call: ToolCallRequest) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_call_id=call.id,
            name=call.name,
            status="succeeded",
            output={"iso": "2026-08-04T00:00:00Z"},
        )

    monkeypatch.setitem(
        builtin.TOOL_REGISTRY,
        "get_current_time",
        replace(builtin.TOOL_REGISTRY["get_current_time"], executor=_fixed),
    )


def _wire(**kwargs: Any) -> RunTripwire:
    """A run-level tripwire with exactly the bounds a test names."""
    return RunTripwire(RunBounds(**kwargs))


def _usage(tokens: int) -> UsageUpdate:
    return UsageUpdate(input_tokens=tokens)


# --- bounds resolution --------------------------------------------------------


def test_settings_defaults_resolve_to_the_documented_starting_values() -> None:
    resolved = RunBounds.from_settings(Settings())  # type: ignore[call-arg]
    assert resolved.wall_clock_seconds == 600.0
    # Ships OFF: 50k is a per-task-class calibration, not a default.
    assert resolved.max_run_tokens == 0
    assert resolved.max_consecutive_tool_failures == 3
    assert resolved.tool_failure_window == 5
    assert resolved.loop_detection_enabled is True
    assert resolved.repeated_tool_call_threshold == 3
    assert resolved.tool_result_max_chars == DEFAULT_TOOL_RESULT_MAX_CHARS


def test_a_tuned_payload_limit_reaches_the_resolved_bounds() -> None:
    """`RunBounds` is the single owner of the limit the handler truncates with, so
    an operator's `TOOL_RESULT_MAX_CHARS` has to survive the resolution."""
    resolved = RunBounds.from_settings(Settings(TOOL_RESULT_MAX_CHARS=1_234))  # type: ignore[call-arg]
    assert resolved.tool_result_max_chars == 1_234


def test_bare_bounds_are_every_trip_disabled() -> None:
    """`RunBounds()` is the "no extra bounds" value a test builds up from."""
    bare = RunBounds()
    assert bare.repeats_tripped_at == 0
    assert bare.max_run_tokens == 0
    assert bare.wall_clock_seconds == 0.0
    assert bare.max_consecutive_tool_failures == 0


def test_loop_detection_flag_off_disables_the_repeat_bound() -> None:
    """The flag wins over the threshold: off is off, not "off with a 3"."""
    off = RunBounds(loop_detection_enabled=False, repeated_tool_call_threshold=3)
    assert off.repeats_tripped_at == 0


def test_repeat_window_is_wider_than_the_threshold_it_feeds() -> None:
    """A window as narrow as the threshold makes one interleaved call reset
    detection, so `A A B A` would never trip."""
    on = RunBounds(loop_detection_enabled=True, repeated_tool_call_threshold=3)
    assert on.repeated_tool_call_window > on.repeats_tripped_at


# --- wall clock ---------------------------------------------------------------


def test_wall_clock_trips_at_the_boundary_and_not_before(clock: _FakeClock) -> None:
    wire = _wire(wall_clock_seconds=10.0)
    clock.advance(9.999)
    assert wire.check() is None
    clock.advance(0.001)
    assert wire.check() == "wall_clock_exceeded"


def test_wall_clock_zero_disables_the_deadline(clock: _FakeClock) -> None:
    wire = _wire(wall_clock_seconds=0.0)
    clock.advance(10_000.0)
    assert wire.check() is None


# --- token cap ----------------------------------------------------------------


def test_token_cap_trips_at_the_boundary_and_not_before() -> None:
    wire = _wire(max_run_tokens=100)
    wire.note_usage(_usage(99))
    assert wire.check() is None
    wire.note_usage(_usage(100))
    assert wire.check() == "token_cap_exceeded"


def test_token_cap_counts_every_billed_field() -> None:
    """Cached input reads bill additively in `pricing.py`, so they are tokens the
    run really spent — counting only input+output would under-report the cap."""
    wire = _wire(max_run_tokens=40)
    wire.note_usage(
        UsageUpdate(
            input_tokens=10,
            output_tokens=10,
            reasoning_tokens=10,
            cached_input_tokens=10,
        )
    )
    assert wire.run_tokens == 40
    assert wire.check() == "token_cap_exceeded"


def test_a_scope_usage_sample_replaces_its_own_running_total() -> None:
    """A provider reports a CUMULATIVE total per stream: adding successive
    samples from one scope would double-count its way to a phantom trip."""
    wire = _wire(max_run_tokens=100)
    loop = wire.loop_handle("worker-0")
    for cumulative in (10, 30, 60):
        loop.note_usage(_usage(cumulative))
    assert wire.run_tokens == 60
    assert wire.check() is None


def test_the_run_token_total_is_the_sum_across_scopes() -> None:
    """Two workers each under the cap can still exhaust the RUN's budget."""
    wire = _wire(max_run_tokens=100)
    wire.loop_handle("worker-0").note_usage(_usage(60))
    wire.loop_handle("worker-1").note_usage(_usage(40))
    assert wire.run_tokens == 100
    assert wire.check() == "token_cap_exceeded"


# --- loop detection -----------------------------------------------------------


def test_repeated_identical_call_trips_at_the_threshold() -> None:
    wire = _wire(loop_detection_enabled=True, repeated_tool_call_threshold=3)
    for _ in range(2):
        wire.note_tool_call("web_search", {"query": "same"})
        assert wire.check() is None
    wire.note_tool_call("web_search", {"query": "same"})
    assert wire.check() == "repeated_tool_calls"


def test_interleaved_call_does_not_reset_loop_detection() -> None:
    """`A A B A` is still a loop: a model that varies one call in three has not
    made progress, and a window as narrow as the threshold would forgive it."""
    wire = _wire(loop_detection_enabled=True, repeated_tool_call_threshold=3)
    for name in ("A", "A", "B"):
        wire.note_tool_call(name, {})
    assert wire.check() is None
    wire.note_tool_call("A", {})
    assert wire.check() == "repeated_tool_calls"


def test_distinct_calls_never_trip_loop_detection() -> None:
    """Progress looks like different arguments; twelve of them must be fine."""
    wire = _wire(loop_detection_enabled=True, repeated_tool_call_threshold=3)
    for i in range(12):
        wire.note_tool_call("web_search", {"query": f"q{i}"})
        assert wire.check() is None


def test_digest_ignores_argument_key_order_but_not_values() -> None:
    """Providers do not promise key order; two identical calls must hash the
    same, and two different ones must not."""
    assert tool_call_digest("t", {"a": 1, "b": 2}) == tool_call_digest("t", {"b": 2, "a": 1})
    assert tool_call_digest("t", {"a": 1}) != tool_call_digest("t", {"a": 2})
    assert tool_call_digest("t", None) == tool_call_digest("t", {})
    assert tool_call_digest("t", {}) != tool_call_digest("u", {})


def test_unserializable_argument_still_hashes_inside_a_bound() -> None:
    """A bound that raises on an odd argument is worse than no bound."""
    assert tool_call_digest("t", {"when": object()})


def test_loop_detection_off_records_nothing() -> None:
    wire = _wire(loop_detection_enabled=False, repeated_tool_call_threshold=3)
    for _ in range(20):
        wire.note_tool_call("web_search", {"query": "same"})
    assert wire.check() is None


# --- tool-failure breaker -----------------------------------------------------


def test_failure_breaker_trips_on_n_failures_in_the_window() -> None:
    wire = _wire(max_consecutive_tool_failures=3, tool_failure_window=5)
    for _ in range(2):
        wire.note_tool_result("failed")
        assert wire.check() is None
    wire.note_tool_result("failed")
    assert wire.check() == "consecutive_tool_failures"


def test_failures_need_not_be_adjacent_within_the_window() -> None:
    """3-in-5, not 3-in-a-row: a tool failing two times out of three is broken
    even when a success lands between the failures."""
    wire = _wire(max_consecutive_tool_failures=3, tool_failure_window=5)
    for status in ("failed", "succeeded", "failed", "succeeded"):
        wire.note_tool_result(status)
    assert wire.check() is None
    wire.note_tool_result("failed")
    assert wire.check() == "consecutive_tool_failures"


def test_failures_older_than_the_window_are_forgotten() -> None:
    """Otherwise the breaker is a lifetime counter and every long run trips."""
    wire = _wire(max_consecutive_tool_failures=3, tool_failure_window=5)
    wire.note_tool_result("failed")
    wire.note_tool_result("failed")
    for _ in range(5):
        wire.note_tool_result("succeeded")
    wire.note_tool_result("failed")
    wire.note_tool_result("failed")
    assert wire.check() is None


def test_only_a_failed_result_feeds_the_breaker() -> None:
    """A cancelled result is the run degrading on purpose (a budget kill, a
    superseded pause) and must not also read as the tool being broken."""
    wire = _wire(max_consecutive_tool_failures=3, tool_failure_window=5)
    for status in ("cancelled", "cancelled", "cancelled"):
        wire.note_tool_result(status)
    assert wire.check() is None


def test_failure_breaker_off_records_nothing() -> None:
    wire = _wire(max_consecutive_tool_failures=0, tool_failure_window=5)
    for _ in range(20):
        wire.note_tool_result("failed")
    assert wire.check() is None


# --- one decider, one latch, one log line -------------------------------------


def test_check_latches_the_first_reason(clock: _FakeClock) -> None:
    """A run has ONE stop reason. Once the clock has run out, a later token
    breach cannot relabel the stop."""
    wire = _wire(wall_clock_seconds=10.0, max_run_tokens=100)
    clock.advance(10.0)
    assert wire.check() == "wall_clock_exceeded"
    wire.note_usage(_usage(500))
    assert wire.check() == "wall_clock_exceeded"
    assert wire.tripped == "wall_clock_exceeded"


def test_tripped_reads_the_latch_without_evaluating_bounds(clock: _FakeClock) -> None:
    wire = _wire(wall_clock_seconds=10.0)
    clock.advance(10.0)
    assert wire.tripped is None
    assert wire.check() == "wall_clock_exceeded"
    assert wire.tripped == "wall_clock_exceeded"


@pytest.mark.parametrize(
    ("reason", "build", "feed"),
    [
        (
            "wall_clock_exceeded",
            {"wall_clock_seconds": 5.0},
            lambda wire, clock: clock.advance(5.0),
        ),
        (
            "token_cap_exceeded",
            {"max_run_tokens": 10},
            lambda wire, clock: wire.note_usage(_usage(10)),
        ),
        (
            "repeated_tool_calls",
            {"loop_detection_enabled": True, "repeated_tool_call_threshold": 2},
            lambda wire, clock: [wire.note_tool_call("t", {}) for _ in range(2)],
        ),
        (
            "consecutive_tool_failures",
            {"max_consecutive_tool_failures": 2, "tool_failure_window": 3},
            lambda wire, clock: [wire.note_tool_result("failed") for _ in range(2)],
        ),
    ],
)
def test_every_trip_writes_exactly_one_tunable_log_line(
    clock: _FakeClock,
    reason: str,
    build: dict[str, Any],
    feed: Any,
) -> None:
    """An unlogged breaker cannot be tuned, and a breaker logging on every
    subsequent event cannot be read. Tuning needs all four fields."""
    wire = _wire(**build)
    feed(wire, clock)
    with structlog.testing.capture_logs() as captured:
        assert wire.check() == reason
        # `check()` is called on every event, so the latch — not the caller —
        # has to be what keeps this to one line.
        for _ in range(5):
            assert wire.check() == reason
    tripped = [e for e in captured if e.get("event") == "agentic.tripped"]
    assert len(tripped) == 1
    line = tripped[0]
    assert line["log_level"] == "warning"
    assert line["stop_reason"] == reason
    assert line["counted_event"] == counted_event_for(reason)  # type: ignore[arg-type]
    assert line["outcome"] == "partial_limit"
    assert line["observed"] >= line["limit"]


def test_a_loop_trip_logs_under_the_loop_prefix(clock: _FakeClock) -> None:
    """AGENTS.md tells an operator to grep `agent_loop.` for per-loop events and
    `agentic.` for run-level degrades; a trip reports from the layer that saw
    it, naming the scope."""
    wire = _wire(wall_clock_seconds=5.0)
    loop = wire.loop_handle("worker-3")
    clock.advance(5.0)
    with structlog.testing.capture_logs() as captured:
        assert loop.check() == "wall_clock_exceeded"
    line = next(e for e in captured if e.get("event") == "agent_loop.tripped")
    assert line["scope"] == "worker-3"
    assert not [e for e in captured if e.get("event") == "agentic.tripped"]


def test_repeated_call_trip_logs_the_hash_it_counted() -> None:
    """`tool_call_hash` is the counted event, so the log has to carry one."""
    wire = _wire(loop_detection_enabled=True, repeated_tool_call_threshold=2)
    for _ in range(2):
        wire.note_tool_call("web_search", {"query": "same"})
    with structlog.testing.capture_logs() as captured:
        assert wire.check() == "repeated_tool_calls"
    line = next(e for e in captured if e.get("event") == "agentic.tripped")
    assert line["tool_call_hash"] == tool_call_digest("web_search", {"query": "same"})


# --- handles share the run, not each other's behavior -------------------------


def test_a_handle_trip_stops_the_whole_run(clock: _FakeClock) -> None:
    """The latch is a property of the RUN: one worker's trip stops its siblings,
    and the run's deadline stops every worker."""
    wire = _wire(wall_clock_seconds=5.0)
    first = wire.loop_handle("worker-0")
    second = wire.loop_handle("worker-1")
    clock.advance(5.0)
    assert first.check() == "wall_clock_exceeded"
    assert wire.tripped == "wall_clock_exceeded"
    assert second.tripped == "wall_clock_exceeded"


def test_loop_detection_stays_per_handle() -> None:
    """Two workers issuing the same call are not a loop — a repeated call is a
    property of ONE loop's behavior."""
    wire = _wire(loop_detection_enabled=True, repeated_tool_call_threshold=3)
    first = wire.loop_handle("worker-0")
    second = wire.loop_handle("worker-1")
    for handle in (first, second, first, second):
        handle.note_tool_call("web_search", {"query": "same"})
    assert wire.check() is None
    assert first.check() is None
    first.note_tool_call("web_search", {"query": "same"})
    assert first.check() == "repeated_tool_calls"


def test_failure_windows_stay_per_handle() -> None:
    wire = _wire(max_consecutive_tool_failures=3, tool_failure_window=5)
    first = wire.loop_handle("worker-0")
    second = wire.loop_handle("worker-1")
    for handle in (first, second, first, second):
        handle.note_tool_result("failed")
    assert first.check() is None
    assert second.check() is None


def test_invocations_accumulate_across_handles(clock: _FakeClock) -> None:
    wire = _wire(wall_clock_seconds=5.0)
    wire.loop_handle("worker-0").note_invocation()
    wire.loop_handle("worker-1").note_invocation()
    clock.advance(5.0)
    with structlog.testing.capture_logs() as captured:
        wire.check()
    line = next(e for e in captured if e.get("event") == "agentic.tripped")
    assert line["invocations"] == 2


# --- totality against the real call sites (S3's `assert_never`) ---------------


def test_every_tripwire_reason_is_a_declared_stop_reason() -> None:
    """`loop_state` shipped with no importers; these are its first real call
    sites, so this is where the alias is proven to cover them."""
    for reason in TRIPWIRE_REASONS:
        assert reason in STOP_REASONS


def test_every_tripwire_reason_degrades_to_a_named_partial() -> None:
    """A trip is a labeled partial that says what filled up — never a failure
    and never an unlabeled stop."""
    for reason in TRIPWIRE_REASONS:
        assert outcome_for(reason) == "partial_limit"  # type: ignore[arg-type]
        assert counted_event_for(reason) != "none"  # type: ignore[arg-type]


def test_only_behavioral_trips_permit_the_tool_suppressed_final_pass() -> None:
    """A pass that advertises no tools cannot loop, so a behavioral trip has
    nothing to gain by refusing it. A physical bound does: when the deadline or
    the token budget ran out, one more stream is what there is no room for."""
    assert allows_final_answer_pass("repeated_tool_calls") is True
    assert allows_final_answer_pass("consecutive_tool_failures") is True
    assert allows_final_answer_pass("wall_clock_exceeded") is False
    assert allows_final_answer_pass("token_cap_exceeded") is False
    # No trip at all trivially permits it — that is the untripped loop's path.
    assert allows_final_answer_pass(None) is True


def test_an_unclassified_stop_reason_is_refused_the_final_pass() -> None:
    """The safe direction for a bound: a reason added to the alias later is
    refused until someone decides, rather than silently inheriting a pass."""
    for reason in STOP_REASONS - {"repeated_tool_calls", "consecutive_tool_failures"}:
        assert allows_final_answer_pass(reason) is False


def test_the_usd_cap_is_not_the_tripwire_s_to_report() -> None:
    """One degrade label per channel: `usd_cap_exceeded` stays `budget.py`'s, so
    a cap breach and a trip can never be relabeled as each other."""
    assert "usd_cap_exceeded" not in TRIPWIRE_REASONS


# --- bounding a tool result by construction (§7) ------------------------------


def test_text_under_the_limit_is_returned_unchanged() -> None:
    assert bound_tool_result_text("small", max_chars=100) == "small"


def test_text_at_the_limit_is_returned_unchanged() -> None:
    exact = "x" * 100
    assert bound_tool_result_text(exact, max_chars=100) == exact


def test_oversize_text_is_truncated_and_visibly_marked() -> None:
    """A response growing 10K → 80K tokens costs 7-91% answer retrieval, so the
    payload is bounded by construction — and the model is told it was cut."""
    bounded = bound_tool_result_text("y" * 5_000, max_chars=200)
    assert len(bounded) <= 200
    assert bounded.startswith("yyy")
    assert "truncated" in bounded
    assert "5000" in bounded


@pytest.mark.parametrize("max_chars", [60, 200, 1_000, 4_321])
def test_the_marker_reports_exactly_how_much_was_dropped(max_chars: int) -> None:
    """The marker occupies part of the budget, so the characters it displaces are
    dropped too: reporting `total - max_chars` under-stated the cut by the
    marker's own length. Kept + dropped must equal the original."""
    total = 9_000
    bounded = bound_tool_result_text("k" * total, max_chars=max_chars)
    reported = re.search(r"truncated: (\d+) of (\d+) characters", bounded)
    assert reported is not None
    dropped, said_total = int(reported.group(1)), int(reported.group(2))
    assert said_total == total
    assert bounded.count("k") + dropped == total
    assert len(bounded) <= max_chars


def test_truncation_is_disabled_by_a_nonpositive_limit() -> None:
    huge = "z" * 10_000
    assert bound_tool_result_text(huge, max_chars=0) == huge
    assert bound_tool_result_text(huge, max_chars=-1) == huge


def test_a_pathological_limit_still_discloses_the_truncation() -> None:
    """Below the marker's own length the marker alone is returned: silently
    dropping the disclosure would be worse than overshooting the limit."""
    bounded = bound_tool_result_text("q" * 500, max_chars=5)
    assert "truncated" in bounded
    assert "q" not in bounded


def test_payload_under_the_limit_is_byte_identical() -> None:
    payload = {"results": [{"title": "t", "url": "u"}]}
    assert bound_tool_result_payload(payload, max_chars=1_000) == payload
    assert bound_tool_result_payload(None, max_chars=1_000) is None


def test_oversize_payload_stays_valid_json_under_one_marked_key() -> None:
    """A truncated JSON dump no longer parses as the original object, so it
    rides as one string field rather than corrupting the result envelope the
    provider adapters rebuild from."""
    bounded = bound_tool_result_payload({"blob": "w" * 5_000}, max_chars=300)
    assert bounded is not None
    assert list(bounded) == [TRUNCATED_OUTPUT_KEY]
    assert len(bounded[TRUNCATED_OUTPUT_KEY]) <= 300
    assert "truncated" in bounded[TRUNCATED_OUTPUT_KEY]


def test_tool_feedback_history_bounds_both_payload_and_error() -> None:
    """This is where a tool result becomes model-visible, so this is where the
    size guarantee has to hold."""
    results = [
        ToolResult(
            tool_call_id="c1",
            name="web_search",
            status="failed",
            output={"blob": "w" * 5_000},
            error="e" * 5_000,
        )
    ]
    encoded = tool_feedback_to_history(results, max_chars=300)[0].text or ""
    assert "truncated" in encoded
    assert "w" * 400 not in encoded
    assert "e" * 400 not in encoded


def test_tool_feedback_history_leaves_a_small_result_alone() -> None:
    results = [
        ToolResult(
            tool_call_id="c1",
            name="get_current_time",
            status="succeeded",
            output={"iso": "2026-08-04T00:00:00Z"},
        )
    ]
    bound = tool_feedback_to_history(results, max_chars=8_000)
    unbound = tool_feedback_to_history(results, max_chars=0)
    assert bound == unbound
    assert "truncated" not in (bound[0].text or "")


# --- the loop's degrade ladder ------------------------------------------------


def _loop_settings(**kwargs: Any) -> Settings:
    base: dict[str, Any] = {"TOOL_MAX_ROUNDS": 8}
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _greedy_stream_factory(
    *, on_round: Any = None, tool_input: dict[str, Any] | None = None
) -> tuple[Any, list[bool]]:
    """A provider that answers a little and re-requests the SAME tool forever.

    The realistic shape of a cheap endless loop: every round produces prose (so
    there is work to keep) and one identical tool call (so nothing progresses).
    Answers once the loop suppresses tools — the greedy-provider recovery the
    reserved final pass exists to compel.

    Returns the stream factory and the `suppress_tools` flag of every stream it
    opened, so a test can see both how many rounds ran and whether the reserved
    pass was among them.
    """
    streams: list[bool] = []

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        streams.append(suppress_tools)
        index = len(streams)
        if on_round is not None:
            on_round(index)

        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text=f"finding {index}. ")
            if suppress_tools:
                yield Complete(usage=UsageUpdate(input_tokens=10))
                return
            yield ToolCall(
                id=f"c{index}",
                name="get_current_time",
                status="running",
                input=tool_input if tool_input is not None else {},
            )

        return _gen()

    return _make_stream, streams


async def test_a_behavioral_trip_still_runs_the_tool_suppressed_final_pass() -> None:
    """Degrade ladder (§11.8): stop scheduling new ACTIONS, keep the partials
    already produced, and leave the wire exactly one terminal Complete.

    The reserved final pass is not a new action: `suppress_tools=True` advertises
    no tools, so it cannot repeat the call that tripped or open a further round.
    Skipping it would cost the grounded answer it exists to compel and buy no
    safety — and would make this degrade harsher than `tool_rounds_exhausted`,
    which shares its `partial_limit` outcome.
    """
    make_stream, streams = _greedy_stream_factory()
    wire = RunTripwire(
        RunBounds(loop_detection_enabled=True, repeated_tool_call_threshold=3)
    )
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=make_stream,
            settings=_loop_settings(),
            tripwire=wire.loop_handle("primary"),
        )
    ]
    assert wire.tripped == "repeated_tool_calls"
    # Three action rounds, then the tool-suppressed rescue — and nothing after
    # it, rather than burning TOOL_MAX_ROUNDS on more action rounds.
    assert streams == [False, False, False, True]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer == "finding 1. finding 2. finding 3. finding 4. "
    assert len([e for e in events if isinstance(e, Complete)]) == 1
    assert isinstance(events[-1], Complete)


async def test_a_behavioral_trip_with_no_reserved_pass_degrades() -> None:
    """`TOOL_MAX_ROUNDS=1` reserves no final pass, so there is nothing to fall
    through to and the trip degrades on the spot."""
    make_stream, streams = _greedy_stream_factory()
    wire = RunTripwire(
        RunBounds(loop_detection_enabled=True, repeated_tool_call_threshold=1)
    )
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=make_stream,
            settings=_loop_settings(TOOL_MAX_ROUNDS=1),
            tripwire=wire.loop_handle("primary"),
        )
    ]
    assert wire.tripped == "repeated_tool_calls"
    assert streams == [False]
    assert len([e for e in events if isinstance(e, Complete)]) == 1


async def test_loop_trips_on_the_wall_clock_rather_than_running_on(
    clock: _FakeClock,
) -> None:
    """A run that outlives its deadline degrades — it does not hang, it does not
    keep opening rounds, and unlike a behavioral trip it does not get the rescue
    pass: when the deadline is what ran out, one more stream is the one thing
    there is no room for."""
    # Loop detection stays OFF, so the clock is the only bound in play even
    # though every round repeats the same call.
    wire = RunTripwire(RunBounds(wall_clock_seconds=10.0))
    make_stream, streams = _greedy_stream_factory(on_round=lambda _index: clock.advance(4.0))
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=make_stream,
            settings=_loop_settings(),
            tripwire=wire.loop_handle("primary"),
        )
    ]
    assert wire.tripped == "wall_clock_exceeded"
    # 4s + 4s stayed under the 10s deadline; the third round crossed it. No
    # tool-suppressed pass followed.
    assert streams == [False, False, False]
    assert "finding 3. " in "".join(
        e.text for e in events if isinstance(e, AnswerDelta)
    )
    assert len([e for e in events if isinstance(e, Complete)]) == 1


async def test_a_physical_trip_with_no_prose_still_ends_through_the_terminal_path(
    clock: _FakeClock,
) -> None:
    """The loop must never end a turn blank. A physical trip before any answer
    routes through the SAME empty-terminal decision every other stop uses — and
    may not spend the empty-reply retry, because that would open another provider
    stream on a run whose deadline is what stopped it."""
    streams: list[bool] = []

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        streams.append(suppress_tools)
        index = len(streams)
        clock.advance(6.0)

        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield ToolCall(id=f"c{index}", name="get_current_time", status="running")

        return _gen()

    wire = RunTripwire(RunBounds(wall_clock_seconds=10.0))
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=_make_stream,
            settings=_loop_settings(EMPTY_REPLY_RETRY_ENABLED=True),
            tripwire=wire.loop_handle("primary"),
        )
    ]
    assert wire.tripped == "wall_clock_exceeded"
    assert streams == [False, False]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer.strip() == EMPTY_REPLY_FALLBACK
    completes = [e for e in events if isinstance(e, Complete)]
    assert len(completes) == 1
    assert completes[0].empty_retry is False


async def test_a_disabled_tripwire_leaves_the_loop_identical(frozen_tool: None) -> None:
    """Additive and default-safe: a healthy turn behaves as it did before. The
    all-disabled tripwire is fed everything and decides nothing."""

    def _events_for(wire: RunTripwire | None) -> Any:
        make_stream, _ = _greedy_stream_factory()
        return run_agent_loop(
            make_stream=make_stream,
            settings=_loop_settings(TOOL_MAX_ROUNDS=3),
            tripwire=wire,
        )

    without = [ev async for ev in _events_for(None)]
    with_disabled = [ev async for ev in _events_for(RunTripwire(RunBounds()))]
    assert without == with_disabled
    assert [e for e in without if isinstance(e, Complete)]


# --- the orchestrator treats a trip like the cap breach it mirrors ------------


def _agentic_settings(**kwargs: Any) -> Settings:
    base: dict[str, Any] = {
        "PROVIDER_BACKEND": "fake",
        "AGENTIC_ENABLED": True,
        "TOOLS_ENABLED": True,
        "AGENTIC_PLAN_APPROVAL": False,
        "AGENTIC_VERIFIER": False,
        "AGENTIC_MAX_WORKERS": 2,
        "AGENTIC_RUN_BUDGET_USD": 100.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


async def test_default_bounds_still_deliver_a_grounded_answer_to_a_greedy_provider() -> None:
    """The shipped defaults collide by construction, so this drives the real
    orchestrator with the run bounds left untouched.

    `TOOL_MAX_ROUNDS=4` leaves three action rounds and
    `REPEATED_TOOL_CALL_THRESHOLD=3` means a greedy provider can only trip on the
    LAST of them — precisely where the reserved final pass was about to force a
    grounded answer, and not tunable away (with three action rounds a provider
    cannot make a third identical call any earlier). Refusing that pass replaced
    the grounded answer with the empty-reply fallback, regressing the invariant
    `test_tool_loop_approval` pins for this exact provider shape; that test kept
    passing because it drives the plain-chat path, which gets no tripwire.
    """
    settings = _agentic_settings()
    # The collision above is what makes this the default-path case, so fail
    # loudly if either default moves rather than testing a shape prod never sees.
    assert settings.tool_max_rounds == 4
    assert settings.repeated_tool_call_threshold == 3
    assert settings.loop_detection_enabled is True
    streams: list[bool] = []

    def _make_stream_for(prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            streams.append(suppress_tools)

            async def _gen() -> AsyncIterator[ProviderEvent]:
                if suppress_tools:
                    yield AnswerDelta(
                        text="After several tool calls, here is the grounded final answer."
                    )
                    yield Complete(usage=UsageUpdate(input_tokens=10))
                    return
                # Stay greedy: re-request the identical call every round.
                yield ToolCall(
                    id=f"c{len(streams)}",
                    name="get_current_time",
                    status="running",
                    input={},
                )

            return _gen()

        return _make

    with structlog.testing.capture_logs() as captured:
        events = [
            ev
            async for ev in run_orchestrator(
                make_stream_for=_make_stream_for,
                settings=settings,
                mode="single",
                user_text="hi",
                cost_for_usage=lambda u: 1e-9 * float(u.input_tokens),
            )
        ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert "grounded final answer" in answer
    # The rescue pass ran, so the turn is a labeled partial carrying a real
    # answer — not the fallback claiming findings that were never produced.
    assert EMPTY_REPLY_FALLBACK not in answer
    assert streams == [False, False, False, True]
    tripped = [e for e in captured if str(e.get("event", "")).endswith(".tripped")]
    assert len(tripped) == 1
    assert tripped[0]["stop_reason"] == "repeated_tool_calls"
    # Still a partial, and still on the trip's own channel.
    assert "the same tool call kept repeating" in answer
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].partial is True
    assert finals[-1].budget_halted is False


async def test_single_mode_token_cap_trip_reports_a_partial_not_a_budget_halt() -> None:
    """A trip raises `partial` through the same field a cap breach does and
    leaves `budget_halted` alone: one degrade label per channel.

    A token cap is a PHYSICAL bound, so unlike the behavioral trip above it
    refuses even the tool-suppressed pass — there is no token room for it.
    """
    suppressed_streams = 0

    def _make_stream_for(prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            nonlocal suppressed_streams
            if suppress_tools:
                suppressed_streams += 1

            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="partial finding")
                yield UsageUpdate(input_tokens=5_000)
                if not suppress_tools:
                    yield ToolCall(
                        id="c1", name="get_current_time", status="running", input={}
                    )
                    return
                yield Complete(usage=UsageUpdate(input_tokens=5_000))

            return _gen()

        return _make

    with structlog.testing.capture_logs() as captured:
        events = [
            ev
            async for ev in run_orchestrator(
                make_stream_for=_make_stream_for,
                settings=_agentic_settings(RUN_MAX_TOKENS=1_000, TOOL_MAX_ROUNDS=8),
                mode="single",
                user_text="hi",
                cost_for_usage=lambda u: 1e-9 * float(u.input_tokens),
            )
        ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert "partial finding" in answer
    assert "token limit" in answer
    # The USD cap's copy and its flag stay untouched by a trip.
    assert "run budget" not in answer
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].partial is True
    assert finals[-1].budget_halted is False
    tripped = [e for e in captured if str(e.get("event", "")).endswith(".tripped")]
    assert len(tripped) == 1
    assert tripped[0]["stop_reason"] == "token_cap_exceeded"
    assert suppressed_streams == 0


async def test_deep_research_trip_cancels_workers_and_keeps_survivors(
    clock: _FakeClock,
) -> None:
    """A trip mid-fan-out behaves exactly like the mid-flight cap breach: cancel
    the unfinished workers, keep what the finished ones produced, label the
    partial with what tripped, and finish `done`."""
    first_done = asyncio.Event()
    cancelled = {"slow": False}

    async def _fast(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        yield UsageUpdate(input_tokens=10)
        # The run outlives its deadline while this worker finishes, so the kill
        # gate sees the breach when this worker's terminal arrives.
        clock.advance(20.0)
        first_done.set()
        yield AnswerDelta(text="alpha finding")
        yield Complete(usage=UsageUpdate(input_tokens=10, output_tokens=1))

    async def _slow(
        _feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        await first_done.wait()
        try:
            await asyncio.sleep(60)
            yield AnswerDelta(text="never arrives")
        except asyncio.CancelledError:
            cancelled["slow"] = True
            raise

    def _make_stream_for(prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _fast(_feedback, suppress_tools)
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _slow(_feedback, suppress_tools)

            async def _agg() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="synthesis over alpha finding")
                yield Complete(usage=UsageUpdate())

            return _agg()

        return _make

    with structlog.testing.capture_logs() as captured:
        events = [
            ev
            async for ev in run_orchestrator(
                make_stream_for=_make_stream_for,
                settings=_agentic_settings(RUN_WALL_CLOCK_SECONDS=10.0),
                mode="deep_research",
                user_text="DEEP_RESEARCH: alpha | beta",
                cost_for_usage=lambda u: 1e-9 * float(u.input_tokens),
            )
        ]
    assert cancelled["slow"] is True
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    # Never discard completed work, and name what tripped.
    assert "alpha finding" in answer
    assert "time limit" in answer
    assert "run budget" not in answer
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].partial is True
    assert finals[-1].budget_halted is False
    # A trip-cancelled worker is neither a budget kill nor a user Stop.
    outcomes = {
        e.subagent_id: e.outcome
        for e in events
        if isinstance(e, SubagentDone) and e.role == "worker"
    }
    assert outcomes.get("worker-1") == "cancelled"
    tripped = [e for e in captured if str(e.get("event", "")).endswith(".tripped")]
    assert len(tripped) == 1
    assert tripped[0]["event"] == "agentic.tripped"
    assert tripped[0]["stop_reason"] == "wall_clock_exceeded"
