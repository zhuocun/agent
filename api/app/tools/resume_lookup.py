"""Which stored `tool_call` an approval decision or a resume may act on.

The read-side half of the approval domain. `approval_settlement` owns the durable
side: claim, execute, owner-settle, and the version CAS that makes exactly one of
those win. This module owns the question a route asks *before* any claim exists —
given a persisted row, is this call still actionable at all? It is pure: no
database, no locks, no side effects, so it stays a predicate over parts rather
than a step in the settlement protocol.

It reads persisted parts but is deliberately not part of `messages.projection`,
whose responsibility is what a finished turn SAID (provider history and canonical
replay). Eligibility to resume is policy about what a parked turn may still DO —
H-003 in particular turns on the stored call's own `subagentId`, which is why the
rule lives beside the parts it reads instead of in a route.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.agentic.continuation import resolve_continuation


def _tool_calls(parts: object) -> Iterator[dict[str, Any]]:
    """Every dict-shaped `tool_call` part, tolerating a NULL or malformed column."""
    if not isinstance(parts, list):
        return
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "tool_call":
            yield part


def _find_pending_tool_call(parts: object, tool_call_id: str) -> dict[str, Any] | None:
    """The pending, approval-awaiting `tool_call` with this id, if the row has one."""
    for part in _tool_calls(parts):
        if (
            part.get("id") == tool_call_id
            and part.get("status") == "awaiting_approval"
            and part.get("approvalState") == "pending"
        ):
            return part
    return None


def find_resumable_tool_call(
    parts: object,
    tool_call_id: str,
    *,
    server_state: object = None,
) -> dict[str, Any] | None:
    """Find a tool_call for resume: pending OR already settled (BE-007 retry).

    H-003: a worker call cancelled as a concurrent-pause sibling is
    `approvalState=rejected` without a continuation, and those are not resumable —
    only a continuation-bearing pause (or a primary HITL call) may be
    approved/denied.
    """
    pending = _find_pending_tool_call(parts, tool_call_id)
    if pending is not None:
        return pending
    for part in _tool_calls(parts):
        settled = part.get("approvalState") in ("approved", "rejected")
        if part.get("id") != tool_call_id or not settled:
            continue
        subagent_id = part.get("subagentId")
        if isinstance(subagent_id, str) and subagent_id.startswith("worker-"):
            _, continuation = resolve_continuation(
                server_state=server_state,
                tool_input=part.get("input"),
                tool_call_id=tool_call_id,
            )
            if continuation is None and part.get("approvalState") == "rejected":
                return None
        return part
    return None


def find_any_resumable_tool_call(
    parts: object,
    *,
    server_state: object = None,
) -> dict[str, Any] | None:
    """Return the first still-pending approval-gated `tool_call` (A-7 Stop)."""
    for part in _tool_calls(parts):
        call_id = part.get("id")
        if not isinstance(call_id, str) or not call_id:
            continue
        found = find_resumable_tool_call(parts, call_id, server_state=server_state)
        if found is not None and found.get("approvalState") == "pending":
            return found
    return None
