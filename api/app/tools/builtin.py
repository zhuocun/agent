"""Built-in tool registry for the backend-side agent loop (HITL).

Two tools ship in v1, both driven only by the FAKE provider behind the
`TOOLS_ENABLED` flag (default OFF):

- ``get_current_time`` — side-effect-free, no secret/dependency,
  ``needs_approval=False``. Returns the current UTC time (optionally in a named
  timezone). Auto-executes inside the loop.
- ``calendar_create_event`` — ``needs_approval=True``. A STUB that performs NO
  real side effect: it synthesizes a ``{eventId, title, startsAt}`` payload so
  the human-in-the-loop approval seam can be exercised end-to-end without a real
  calendar integration. Because it is approval-gated, the agent loop pauses
  before it runs until a resume POST approves it.

SECURITY: tool OUTPUT is UNTRUSTED. A tool result is a prompt-injection surface
(a real calendar/email/web tool can return attacker-influenced content). The
agent loop feeds results back to the model as a JSON ``tool`` message ONLY — it
is never interpolated into instructions/system text. Each executor also
validates ``call.input`` against a tight key/type allowlist (unknown keys are
rejected, string lengths clamped) so a forged/oversized input can't reach the
stub, and execution is wrapped in ``asyncio.wait_for(...)`` so a hung tool fails
the call instead of the turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings
from app.tools.protocol import (
    ToolApprovalState,
    ToolCallRequest,
    ToolExecutionResult,
)

# Clamp bound for any free-text tool input value. Tool inputs are tiny by
# design (a timezone name, an event title); a value longer than this is
# rejected rather than truncated so a runaway/forged input can't smuggle a
# large payload past validation.
_MAX_INPUT_STR_LEN = 200

ToolExecutorFn = Callable[[ToolCallRequest], Awaitable[ToolExecutionResult]]


class ToolInputError(ValueError):
    """A tool input failed the tight key/type allowlist for its tool."""


def _failed_result(
    call: ToolCallRequest,
    *,
    name: str,
    error: str,
    approval_state: ToolApprovalState = "not_required",
) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_call_id=call.id,
        name=name,
        status="failed",
        output={},
        summary=None,
        error=error,
        approval_state=approval_state,
    )


def _validate_allowlisted_input(
    raw: dict[str, Any] | None,
    *,
    allowed: dict[str, type],
) -> dict[str, Any]:
    """Validate ``raw`` against a tight ``{key: type}`` allowlist.

    Rejects unknown keys, wrong-typed values, and over-long strings. Missing
    keys are allowed (every allowlisted key is optional in v1); the caller
    supplies defaults. Raises ``ToolInputError`` on any violation so the executor
    can return a failed result and the loop keeps going.
    """
    data = raw or {}
    if not isinstance(data, dict):
        raise ToolInputError("Tool input must be an object.")
    unknown = set(data) - set(allowed)
    if unknown:
        raise ToolInputError(f"Unknown input key(s): {', '.join(sorted(unknown))}.")
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        expected = allowed[key]
        # bool is a subclass of int — guard against it slipping through an int
        # allowlist entry (and vice versa) so types stay exact.
        if not isinstance(value, expected) or isinstance(value, bool) is not (expected is bool):
            raise ToolInputError(f"Input {key!r} must be of type {expected.__name__}.")
        if isinstance(value, str) and len(value) > _MAX_INPUT_STR_LEN:
            raise ToolInputError(f"Input {key!r} is too long.")
        cleaned[key] = value
    return cleaned


# Per-tool input allowlists. Single source of truth shared by the executors AND
# the resume route's `edited_input` re-validation (the approval gate is the trust
# boundary, so an edited input is validated server-side before it can run).
_INPUT_ALLOWLIST: dict[str, dict[str, type]] = {
    "get_current_time": {"timezone": str},
    "calendar_create_event": {"title": str, "startsAt": str},
}


def validate_tool_input(name: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Validate a tool's input against its allowlist (route-side re-validation).

    Raises ``ToolInputError`` for an unknown tool or a violating input. Used by
    the resume route to re-check a client-supplied ``edited_input`` before it can
    reach an executor — never trust the client past the approval gate.
    """
    allowed = _INPUT_ALLOWLIST.get(name)
    if allowed is None:
        raise ToolInputError(f"Unknown tool {name!r}.")
    return _validate_allowlisted_input(raw, allowed=allowed)


async def _execute_get_current_time(call: ToolCallRequest) -> ToolExecutionResult:
    """Return the current time, optionally in a requested IANA timezone.

    Side-effect-free. Validates an optional ``timezone`` string via ``zoneinfo``;
    an unknown zone is a failed result (not a 500). Defaults to UTC.
    """
    try:
        cleaned = _validate_allowlisted_input(
            call.input, allowed=_INPUT_ALLOWLIST["get_current_time"]
        )
    except ToolInputError as exc:
        return _failed_result(call, name="get_current_time", error=str(exc))

    tz_name = cleaned.get("timezone")
    tz: Any = UTC
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            return _failed_result(
                call,
                name="get_current_time",
                error=f"Unknown timezone {tz_name!r}.",
            )
    now = datetime.now(tz)
    return ToolExecutionResult(
        tool_call_id=call.id,
        name="get_current_time",
        status="succeeded",
        output={
            "iso8601": now.isoformat(),
            "timezone": tz_name or "UTC",
        },
        summary=f"Current time in {tz_name or 'UTC'}",
    )


async def _execute_calendar_create_event(call: ToolCallRequest) -> ToolExecutionResult:
    """STUB calendar create. Performs NO real side effect.

    Validates the input allowlist, then synthesizes a deterministic-shaped
    ``{eventId, title, startsAt}`` payload. The ``approval_state`` is threaded
    from the call (the loop sets it to ``approved`` once the human approves) so
    the persisted ``tool_result`` records that the gate was cleared.
    """
    try:
        cleaned = _validate_allowlisted_input(
            call.input,
            allowed=_INPUT_ALLOWLIST["calendar_create_event"],
        )
    except ToolInputError as exc:
        return _failed_result(
            call,
            name="calendar_create_event",
            error=str(exc),
            approval_state=call.approval_state,
        )

    title = cleaned.get("title") or "Untitled event"
    starts_at = cleaned.get("startsAt") or datetime.now(UTC).isoformat()
    return ToolExecutionResult(
        tool_call_id=call.id,
        name="calendar_create_event",
        status="succeeded",
        output={
            # Synthesized id — NOT a real calendar event. The stub never touches
            # an external system.
            "eventId": f"evt_{call.id}",
            "title": title,
            "startsAt": starts_at,
        },
        summary=f"Created event: {title}",
        approval_state=call.approval_state,
    )


@dataclass(frozen=True)
class ToolSpec:
    """One registered tool the agent loop may run.

    ``needs_approval`` is the safety boundary: a True tool may NOT execute until a
    human approves it (the loop pauses; a resume POST applies the decision).
    ``schema`` is a JSON-Schema dict describing the tool's input (advertised to
    the model in a real wiring; informational for the fake-only v1).

    ``prod_safe`` gates NATIVE advertisement to a REAL provider. A True tool
    performs a genuine, prod-ready action and is safe to offer to a live model;
    a False tool is a STUB or fake-only fixture that exists to exercise the seam
    (e.g. ``calendar_create_event`` synthesizes a payload with no real side
    effect) and so must NOT be advertised to a real provider — advertising it
    would invite a tool call that resolves to nothing. It stays in the registry
    regardless so the FAKE provider can still drive it via its ``TOOL_*`` markers
    and the resume gate can still execute an already-approved call. Defaults to
    False so a newly added tool is opt-in to prod advertisement.
    """

    name: str
    label: str
    needs_approval: bool
    schema: dict[str, Any] = field(default_factory=dict)
    executor: ToolExecutorFn = field(default=_execute_get_current_time)
    prod_safe: bool = False


_TIME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "timezone": {
            "type": "string",
            "description": "Optional IANA timezone name, e.g. 'America/New_York'. Defaults to UTC.",
            "maxLength": _MAX_INPUT_STR_LEN,
        }
    },
    "additionalProperties": False,
}

_CALENDAR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Event title.",
            "maxLength": _MAX_INPUT_STR_LEN,
        },
        "startsAt": {
            "type": "string",
            "description": "ISO-8601 start timestamp.",
            "maxLength": _MAX_INPUT_STR_LEN,
        },
    },
    "additionalProperties": False,
}


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "get_current_time": ToolSpec(
        name="get_current_time",
        label="Get current time",
        needs_approval=False,
        schema=_TIME_SCHEMA,
        executor=_execute_get_current_time,
        # Side-effect-free and dependency-free — safe to offer a live model.
        prod_safe=True,
    ),
    "calendar_create_event": ToolSpec(
        name="calendar_create_event",
        label="Create calendar event",
        needs_approval=True,
        schema=_CALENDAR_SCHEMA,
        executor=_execute_calendar_create_event,
        # A STUB with no real calendar integration. Kept in the registry so the
        # FAKE provider can exercise the HITL approval seam via TOOL_APPROVE
        # markers, but NOT advertised to a real provider (it would resolve to a
        # synthesized payload, never a real event).
        prod_safe=False,
    ),
}


def advertised_tool_specs() -> list[ToolSpec]:
    """ToolSpecs safe to advertise NATIVELY to a real provider.

    The full ``TOOL_REGISTRY`` still backs the agent loop, the FAKE provider's
    marker-driven calls, and the resume gate's execution of an approved call;
    this filtered view is ONLY what the handler hands a real provider as native
    tool definitions. Stub / fake-only fixtures (``prod_safe=False``) are
    withheld so a live model is never offered a tool that performs no real work.
    """
    return [spec for spec in TOOL_REGISTRY.values() if spec.prod_safe]


def worker_tool_specs() -> list[ToolSpec]:
    """ToolSpecs offered to an autonomous deep-research WORKER subagent.

    A worker runs unattended inside a fan-out — it has no way to surface a
    human-in-the-loop approval pause and wait for a decision mid-run (the plan
    pause is the orchestration-level HITL surface; a worker pausing would strand
    the whole fan-out). So a worker is offered only the least-privilege subset:
    the prod-safe tools that are NOT approval-gated (``needs_approval=False``).
    This is the SR-2 least-privilege default — an approval-gated tool is withheld
    from workers even though it stays available to the single-loop / primary
    path (which CAN pause). Built off ``advertised_tool_specs()`` so a
    fake-only / stub tool is never offered to a worker either.
    """
    return [spec for spec in advertised_tool_specs() if not spec.needs_approval]


async def execute_tool(call: ToolCallRequest) -> ToolExecutionResult:
    """Execute one tool call by name, bounded by the per-tool timeout.

    Unknown tool → failed result (never raises). The executor itself is wrapped
    in ``asyncio.wait_for(...)`` using ``settings.tool_timeout_seconds`` so a
    hung tool is cancelled and reported as a failed result rather than stalling
    the turn.
    """
    spec = TOOL_REGISTRY.get(call.name)
    if spec is None:
        return _failed_result(call, name=call.name, error=f"Unknown tool {call.name!r}.")
    timeout = get_settings().tool_timeout_seconds
    try:
        return await asyncio.wait_for(spec.executor(call), timeout=timeout)
    except TimeoutError:
        return _failed_result(
            call,
            name=spec.name,
            error="Tool execution timed out.",
            approval_state=call.approval_state,
        )
