"""Approval side-effect claim/settle (BE-007).

Approved tool side effects must not re-run when a resume stream fails after
execution. The pending ``tool_call`` on the paused assistant row is the claim
record:

1. **Claim** — atomically flip ``approvalState`` from ``pending`` →
   ``approved``/``rejected`` (and ``status`` to ``running`` / ``cancelled``).
2. **Execute** (approve only) — run the tool once.
3. **Settle** — append a ``tool_result`` part on the *paused* message and mark
   the tool_call terminal (``succeeded`` / ``failed`` / ``cancelled``), then
   commit — independent of whether the post-approval model stream completes.

A later resume for the same ``toolCallId`` finds the settled result and returns
it without invoking the executor again.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.db.repositories import messages as messages_repo
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolCallRequest, ToolExecutionResult


def find_tool_call_part(
    parts: object, tool_call_id: str
) -> dict[str, Any] | None:
    """Locate a ``tool_call`` part by id (any approval/status)."""
    if not isinstance(parts, list):
        return None
    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("type") == "tool_call"
            and part.get("id") == tool_call_id
        ):
            return part
    return None


def find_settled_tool_result(
    parts: object, tool_call_id: str
) -> dict[str, Any] | None:
    """Return a persisted ``tool_result`` for ``tool_call_id`` when present."""
    if not isinstance(parts, list):
        return None
    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("type") == "tool_result"
            and part.get("toolCallId") == tool_call_id
        ):
            return part
    return None


def tool_result_dict_to_execution(
    part: dict[str, Any], *, tool_call_id: str, name: str
) -> ToolExecutionResult:
    """Rebuild a ``ToolExecutionResult`` from a persisted tool_result part."""
    status = part.get("status")
    run_status = (
        status
        if status in ("succeeded", "failed", "cancelled", "running", "pending")
        else "succeeded"
    )
    approval = part.get("approvalState") or part.get("approval_state") or "approved"
    output = part.get("output")
    return ToolExecutionResult(
        tool_call_id=tool_call_id,
        name=name,
        status=run_status,  # type: ignore[arg-type]
        output=output if isinstance(output, dict) else {},
        summary=str(part["summary"]) if isinstance(part.get("summary"), str) else None,
        error=str(part["error"]) if isinstance(part.get("error"), str) else None,
        approval_state=approval,  # type: ignore[arg-type]
    )


def execution_to_tool_result_part(
    result: ToolExecutionResult,
    *,
    label: str | None,
    subagent_id: str | None = None,
) -> dict[str, Any]:
    """Wire-shaped tool_result part (camelCase) for persistence."""
    part: dict[str, Any] = {
        "type": "tool_result",
        "toolCallId": result.tool_call_id,
        "name": result.name,
        "status": result.status,
        "approvalState": result.approval_state,
        "output": result.output or {},
    }
    if label is not None:
        part["label"] = label
    if result.summary is not None:
        part["summary"] = result.summary
    if result.error is not None:
        part["error"] = result.error
    if subagent_id is not None:
        part["subagentId"] = subagent_id
    return part


async def claim_and_settle_approval(
    db: AsyncSession,
    *,
    paused_message: Message,
    tool_call_id: str,
    decision: str,
    effective_input: dict[str, Any],
    label: str | None,
) -> ToolExecutionResult:
    """Claim the pending approval, execute (if approve), settle on the paused row.

    Idempotent: when a settled ``tool_result`` already exists for ``tool_call_id``,
    returns that result without re-executing.
    """
    parts: list[Any] = list(paused_message.parts or [])
    existing = find_settled_tool_result(parts, tool_call_id)
    call_part = find_tool_call_part(parts, tool_call_id)
    tool_name = str((call_part or {}).get("name") or "")
    if existing is not None:
        return tool_result_dict_to_execution(
            existing, tool_call_id=tool_call_id, name=tool_name
        )

    if call_part is None:
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name or "unknown",
            status="failed",
            error="No matching tool call to settle.",
            approval_state="rejected",
        )

    # Claim: flip pending → approved/rejected before any side effect.
    claimed = deepcopy(call_part)
    if decision == "approve":
        claimed["approvalState"] = "approved"
        claimed["status"] = "running"
    else:
        claimed["approvalState"] = "rejected"
        claimed["status"] = "cancelled"
    new_parts = [
        claimed if (isinstance(p, dict) and p.get("type") == "tool_call" and p.get("id") == tool_call_id) else p
        for p in parts
    ]
    paused_message.parts = new_parts
    await db.flush()

    subagent_id = call_part.get("subagentId")
    subagent_str = str(subagent_id) if isinstance(subagent_id, str) else None

    if decision != "approve":
        result = ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name,
            status="cancelled",
            output={},
            summary="User denied the tool call.",
            error="User denied the tool call.",
            approval_state="rejected",
        )
    else:
        # Re-check registry gate at the settlement boundary.
        spec = TOOL_REGISTRY.get(tool_name)
        if spec is None or not spec.needs_approval:
            result = ToolExecutionResult(
                tool_call_id=tool_call_id,
                name=tool_name,
                status="failed",
                output={},
                error="Approved tool is not an approval-gated tool.",
                approval_state="approved",
            )
        else:
            result = await execute_tool(
                ToolCallRequest(
                    id=tool_call_id,
                    name=tool_name,
                    input=effective_input,
                    approval_state="approved",
                )
            )
            # Force approval_state on the settled record.
            result = ToolExecutionResult(
                tool_call_id=result.tool_call_id,
                name=result.name,
                status=result.status,
                output=result.output,
                summary=result.summary,
                error=result.error,
                approval_state="approved",
            )

    # Settle: append tool_result + mark tool_call terminal on the paused row.
    settled_call = deepcopy(claimed)
    settled_call["status"] = result.status
    settled_call["approvalState"] = result.approval_state
    settled_parts: list[Any] = []
    for p in new_parts:
        if (
            isinstance(p, dict)
            and p.get("type") == "tool_call"
            and p.get("id") == tool_call_id
        ):
            settled_parts.append(settled_call)
        else:
            settled_parts.append(p)
    settled_parts.append(
        execution_to_tool_result_part(
            result, label=label, subagent_id=subagent_str
        )
    )
    paused_message.parts = settled_parts
    await db.flush()
    await db.commit()
    await db.refresh(paused_message)
    return result


async def load_paused_assistant_for_resume(
    db: AsyncSession, conversation_id: UUID
) -> Message | None:
    """Return the trailing awaiting_approval assistant, if any."""
    last = await messages_repo.get_last_assistant_message(db, conversation_id)
    if last is None or last.status != "awaiting_approval":
        return None
    return last
