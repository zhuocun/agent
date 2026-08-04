"""One owner for a run's PLURAL trip conditions.

`docs/research/2026-08-03/agent-architecture-state-of-the-art.md` §11.8: "Trips
must be plural — token count alone misses cheap endless loops, step count alone
misses few-but-expensive calls — so combine token, USD, step, failure and time
trips with loop detection on a hash of recent tool calls, every stop writing a
structured log because unlogged breakers cannot be tuned". §17 supplies the
starting values (10 min per task, 50k tokens per run, 3 failures in 5 attempts,
loop detection always on) and §7 supplies the rule that a tool result is
"bound[ed] by construction" — a 10K → 80K token response costs 7-91% answer
retrieval, so the payload is truncated rather than trusted to be small.

What already existed before this module, and stays where it is: the invocation
bound (`TOOL_MAX_ROUNDS` in `app/tools/agent_loop.py`), the per-round call bound
(`TOOL_MAX_CALLS_PER_ROUND`), the per-tool timeout (`TOOL_TIMEOUT_SECONDS` in
`app/tools/builtin.py`) and the USD cap (`app/agentic/budget.py`). This module
adds the four that were missing — wall clock, cumulative tokens, repeated tool
calls, tool-failure breaker — and the result-size bound. It deliberately does NOT
re-implement the USD cap: `usd_cap_exceeded` stays `budget.py`'s to report, so a
cap breach and a trip can never be relabeled as each other.

Three properties this module encodes:

- **One decider.** `note_*` only records; `check()` is the only function that
  decides a run has tripped, in a fixed order, and it latches the first reason.
  A trip therefore has exactly one stop reason for the whole run.
- **One log line per trip.** The latch means `check()` can be called on every
  event and still write exactly one `agent_loop.tripped` / `agentic.tripped`
  event, carrying the `StopReason`, its counted event (§3.1: "every bound must
  name its counted event"), the observed value and the limit. Tuning a breaker
  needs all four.
- **Bounds are code, not prompt text** (§17). Nothing here is ever rendered into
  an instruction; a model cannot negotiate with a `deque`.

Every stop reason raised here is already a `loop_state.StopReason` member, so the
`assert_never` totality in `outcome_for` / `counted_event_for` covers this
module's call sites without widening the alias.

Scope: the tripwire bounds a run's *scheduling* decisions — it stops the next
provider round, the next worker. It cannot interrupt a provider stream already in
flight; that is the transport's own timeout to own.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from app.config import DEFAULT_TOOL_RESULT_MAX_CHARS, Settings
from app.runtime.loop_state import StopReason, counted_event_for, outcome_for
from app.runtime.run_receipt import UsageTotals

_log = structlog.get_logger(__name__)

# Which log prefix a trip writes under. Both are the prefixes AGENTS.md tells an
# operator to grep (`agent_loop.` for per-loop events, `agentic.` for run-level
# degrades), so the debugging guidance keeps working unchanged.
TripChannel = Literal["agent_loop", "agentic"]

# A window has to be WIDER than the threshold it feeds or a single interleaved
# call resets detection: with a 3-repeat threshold, `A A B A` must still trip.
# 4x keeps a 3-in-window repeat detectable while twelve genuinely varied recent
# calls cannot accumulate three identical hashes.
_REPEAT_WINDOW_MULTIPLE = 4

# Marker left in place of dropped characters. Explicit and visible: the model
# should be able to act on "this was cut" (§7 "return tokens the model can act
# on"), and an operator reading a transcript should not have to guess why a
# payload ends mid-object.
_TRUNCATION_MARKER = "…[truncated: {dropped} of {total} characters omitted]"

# Key a bounded tool payload is republished under. A truncated JSON dump is no
# longer parseable as the original object, so it rides as one string field rather
# than corrupting the result envelope the provider adapters rebuild from
# (`parse_tool_feedback_history`).
TRUNCATED_OUTPUT_KEY = "truncatedOutput"


def _truncation_marker(*, dropped: int, total: int) -> str:
    return _TRUNCATION_MARKER.format(dropped=dropped, total=total)


def bound_tool_result_text(
    text: str, *, max_chars: int = DEFAULT_TOOL_RESULT_MAX_CHARS
) -> str:
    """Truncate `text` to `max_chars`, leaving a visible marker (doc §7).

    The RESULT is bounded, marker included, so the caller gets a size guarantee
    rather than a hope: `len(...) <= max_chars` whenever `max_chars` is at least
    the marker's own length (below that the marker alone is returned, because
    silently dropping the disclosure would be worse than overshooting a
    pathological limit). `max_chars <= 0` disables truncation.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    marker = _truncation_marker(dropped=len(text) - max_chars, total=len(text))
    head = max(0, max_chars - len(marker))
    return text[:head] + marker


def bound_tool_result_payload(
    output: Mapping[str, Any] | None,
    *,
    max_chars: int = DEFAULT_TOOL_RESULT_MAX_CHARS,
) -> dict[str, Any] | None:
    """Bound one tool result's structured payload by construction (doc §7).

    Under the limit the payload is returned unchanged, so a healthy tool result
    is byte-identical to a pre-bound build. Over it, the JSON dump is truncated
    and republished under `TRUNCATED_OUTPUT_KEY` — the envelope stays valid JSON
    (a provider adapter rebuilds native tool messages from it) while the model
    sees an explicitly-marked prefix instead of an unbounded dump.
    """
    if output is None:
        return None
    encoded = json.dumps(output, separators=(",", ":"), default=str)
    if max_chars <= 0 or len(encoded) <= max_chars:
        return dict(output)
    return {TRUNCATED_OUTPUT_KEY: bound_tool_result_text(encoded, max_chars=max_chars)}


def tool_call_digest(name: str, tool_input: Mapping[str, Any] | None) -> str:
    """Stable hash of one (tool, arguments) pair — the loop-detection key (§17).

    Canonical JSON (sorted keys, no incidental whitespace) so two calls that
    differ only in key order hash the same; `default=str` keeps a non-JSON
    argument hashable instead of raising inside a bound.
    """
    canonical = json.dumps(
        dict(tool_input or {}), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(f"{name}\x00{canonical}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RunBounds:
    """The bounds one run is held to, resolved once from settings.

    Every field defaults to its disabled value, so `RunBounds()` is "no extra
    bounds" and a test can enable exactly one of them.
    """

    wall_clock_seconds: float = 0.0
    max_run_tokens: int = 0
    max_consecutive_tool_failures: int = 0
    tool_failure_window: int = 1
    loop_detection_enabled: bool = False
    repeated_tool_call_threshold: int = 0
    tool_result_max_chars: int = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> RunBounds:
        """The one place settings become bounds."""
        return cls(
            wall_clock_seconds=max(0.0, float(settings.run_wall_clock_seconds)),
            max_run_tokens=max(0, settings.run_max_tokens),
            max_consecutive_tool_failures=max(
                0, settings.run_max_consecutive_tool_failures
            ),
            tool_failure_window=max(1, settings.run_tool_failure_window),
            loop_detection_enabled=settings.loop_detection_enabled,
            repeated_tool_call_threshold=max(0, settings.repeated_tool_call_threshold),
            tool_result_max_chars=max(0, settings.tool_result_max_chars),
        )

    @property
    def repeats_tripped_at(self) -> int:
        """Repeat count that trips, or 0 when loop detection is off."""
        if not self.loop_detection_enabled or self.repeated_tool_call_threshold < 1:
            return 0
        return self.repeated_tool_call_threshold

    @property
    def repeated_tool_call_window(self) -> int:
        """How many recent calls loop detection remembers."""
        return max(1, self.repeats_tripped_at * _REPEAT_WINDOW_MULTIPLE)


@dataclass
class _RunCounters:
    """State shared by every handle on ONE run.

    The latch lives here, which is what makes a trip a property of the run rather
    than of whichever handle happened to notice it: a worker's loop detection
    stops the orchestrator, and the orchestrator's wall clock stops the workers.
    """

    started_monotonic: float
    tripped: StopReason | None = None
    invocations: int = 0
    # Keyed by scope because a provider reports a RUNNING TOTAL per stream: each
    # scope's latest reading REPLACES its own (mirroring `worker.fold_usage`)
    # while the run's total is the sum across scopes.
    tokens_by_scope: dict[str, int] = field(default_factory=dict)


class RunTripwire:
    """The mutable side of `RunBounds`: fed by a run, consulted by one `check()`.

    A run builds one of these (`from_settings`) and hands each agent loop its own
    `loop_handle(scope)`. Handles share the deadline, the token ledger and the
    trip latch; each keeps its OWN loop-detection and failure windows, because a
    repeated call is a property of one loop's behavior and two workers that
    happen to issue the same call are not a loop.
    """

    def __init__(
        self,
        bounds: RunBounds,
        *,
        channel: TripChannel = "agentic",
        scope: str = "",
    ) -> None:
        self._bounds = bounds
        self._channel = channel
        self._scope = scope
        self._counters = _RunCounters(started_monotonic=time.monotonic())
        self._recent_calls: deque[str] = deque(
            maxlen=bounds.repeated_tool_call_window
        )
        self._recent_failures: deque[bool] = deque(maxlen=bounds.tool_failure_window)

    @classmethod
    def from_settings(
        cls, settings: Settings, *, channel: TripChannel = "agentic"
    ) -> RunTripwire:
        return cls(RunBounds.from_settings(settings), channel=channel)

    def loop_handle(self, scope: str) -> RunTripwire:
        """One agent loop's view of this run's bounds.

        Shares the run's clock, tokens and latch; reports under the
        `agent_loop.` prefix because that is the layer that observed the trip.
        """
        handle = RunTripwire(self._bounds, channel="agent_loop", scope=scope)
        handle._counters = self._counters
        return handle

    @property
    def bounds(self) -> RunBounds:
        return self._bounds

    @property
    def tripped(self) -> StopReason | None:
        """The latched reason, without evaluating the bounds again."""
        return self._counters.tripped

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._counters.started_monotonic

    @property
    def run_tokens(self) -> int:
        return sum(self._counters.tokens_by_scope.values())

    # --- feeds (record only; they never decide) -------------------------------

    def note_invocation(self) -> None:
        """One provider stream was opened under this run."""
        self._counters.invocations += 1

    def note_usage(self, usage: object) -> None:
        """Record this scope's CUMULATIVE usage so far.

        Duck-typed through `UsageTotals.copy_from` so `app/runtime` stays
        provider-independent, as `run_receipt` already is. All four counts are
        summed: cached input reads bill additively in `pricing.py`, so they are
        tokens the run really spent.
        """
        totals = UsageTotals.copy_from(usage)
        self._counters.tokens_by_scope[self._scope] = (
            totals.input_tokens
            + totals.output_tokens
            + totals.reasoning_tokens
            + totals.cached_input_tokens
        )

    def note_tool_call(self, name: str, tool_input: Mapping[str, Any] | None) -> None:
        """Record one (tool, arguments) pair for loop detection (§17)."""
        if self._bounds.repeats_tripped_at < 1:
            return
        self._recent_calls.append(tool_call_digest(name, tool_input))

    def note_tool_result(self, status: str) -> None:
        """Record one tool attempt's outcome for the failure breaker.

        Only `failed` counts. A `cancelled` result is the run degrading on
        purpose (a budget kill, a superseded pause) and must not also read as the
        tool being broken.
        """
        if self._bounds.max_consecutive_tool_failures < 1:
            return
        self._recent_failures.append(status == "failed")

    # --- the one decision -----------------------------------------------------

    def check(self) -> StopReason | None:
        """The single place a run is declared tripped.

        Returns the latched reason (`None` while healthy). Evaluation order is
        fixed so two bounds breaching in the same instant always report the same
        one: the run-level physical limits first (a deadline and a token budget
        are facts about the run), then the behavioral ones.
        """
        latched = self._counters.tripped
        if latched is not None:
            return latched
        bounds = self._bounds
        wall_clock = bounds.wall_clock_seconds
        if wall_clock > 0:
            elapsed = self.elapsed_seconds
            if elapsed >= wall_clock:
                return self._trip(
                    "wall_clock_exceeded", observed=round(elapsed, 3), limit=wall_clock
                )
        if bounds.max_run_tokens > 0:
            tokens = self.run_tokens
            if tokens >= bounds.max_run_tokens:
                return self._trip(
                    "token_cap_exceeded", observed=tokens, limit=bounds.max_run_tokens
                )
        repeats_at = bounds.repeats_tripped_at
        if repeats_at > 0 and self._recent_calls:
            digest, count = Counter(self._recent_calls).most_common(1)[0]
            if count >= repeats_at:
                return self._trip(
                    "repeated_tool_calls",
                    observed=count,
                    limit=repeats_at,
                    tool_call_hash=digest,
                )
        failures_at = bounds.max_consecutive_tool_failures
        if failures_at > 0:
            failures = sum(self._recent_failures)
            if failures >= failures_at:
                return self._trip(
                    "consecutive_tool_failures",
                    observed=failures,
                    limit=failures_at,
                    attempt_window=len(self._recent_failures),
                )
        return None

    def _trip(
        self,
        reason: StopReason,
        *,
        observed: float | int,
        limit: float | int,
        **extra: object,
    ) -> StopReason:
        """Latch the run's stop reason and write its ONE structured log line.

        The latch is what keeps this to one line per run: `check()` is cheap to
        call on every event precisely because the second call cannot log again.
        """
        self._counters.tripped = reason
        _log.warning(
            f"{self._channel}.tripped",
            stop_reason=reason,
            counted_event=counted_event_for(reason),
            outcome=outcome_for(reason),
            observed=observed,
            limit=limit,
            scope=self._scope or None,
            elapsed_seconds=round(self.elapsed_seconds, 3),
            run_tokens=self.run_tokens,
            invocations=self._counters.invocations,
            **extra,
        )
        return reason
