"""Approval side-effect claim/settle (BE-007).

Approved tool side effects must not re-run when a resume stream fails after
execution. The pending ``tool_call`` on the paused assistant row is the claim
record:

1. **Claim (CAS)** — only if ``approvalState == "pending"``, flip to
   ``approved``/``rejected`` + ``running``/``cancelled``, stamp a unique
   ``_approvalClaimId``, and **commit** before any executor call.
2. **Execute** (approve only) — run the tool once under that claim.
3. **Settle** — append a ``tool_result`` part and mark the tool_call terminal,
   then commit — independent of whether the post-approval model stream
   completes.

Retry / crash recovery:
- Settled ``tool_result`` present → return it (no re-execute).
- Claimed (``approved``/``running``) **without** ``tool_result`` → do **not**
  re-execute; return a failed replay so the side effect is not doubled
  (covers kill between execute and settle, and stop/disconnect after claim).
- Second concurrent claim loses the CAS and takes the same paths above.
"""

from __future__ import annotations

import secrets
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Message
from app.db.repositories import messages as messages_repo
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolCallRequest, ToolExecutionResult

# Reserved key on the tool_call part (not tool input) identifying the claim.
APPROVAL_CLAIM_ID_KEY = "_approvalClaimId"


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


def _replace_tool_call(
    parts: list[Any], tool_call_id: str, replacement: dict[str, Any]
) -> list[Any]:
    return [
        (
            replacement
            if (
                isinstance(p, dict)
                and p.get("type") == "tool_call"
                and p.get("id") == tool_call_id
            )
            else p
        )
        for p in parts
    ]


def _claimed_without_result_failure(
    *, tool_call_id: str, name: str, approval_state: str
) -> ToolExecutionResult:
    """Safe replay when a prior claim committed but settle never landed."""
    settled_approval = "approved" if approval_state == "approved" else "rejected"
    return ToolExecutionResult(
        tool_call_id=tool_call_id,
        name=name or "unknown",
        status="failed",
        output={},
        summary="Prior approval claim has no settled result.",
        error=(
            "Tool approval was already claimed but no settled result is "
            "available; refusing to re-execute the side effect."
        ),
        approval_state=settled_approval,  # type: ignore[arg-type]
    )


async def _persist_parts(db: AsyncSession, message: Message, parts: list[Any]) -> None:
    message.parts = parts
    flag_modified(message, "parts")
    await db.flush()
    await db.commit()
    await db.refresh(message)


async def claim_and_settle_approval(
    db: AsyncSession,
    *,
    paused_message: Message,
    tool_call_id: str,
    decision: str,
    effective_input: dict[str, Any],
    label: str | None,
    claim_id: str | None = None,
) -> ToolExecutionResult:
    """Claim the pending approval (CAS), execute (if approve), settle on the row.

    ``claim_id`` is an optional caller-supplied idempotency key; when omitted a
    server token is minted. Same ``claim_id`` against an already-settled row
    returns the stored result. A claim without a settled result never re-runs
    the executor.

    Claim uses ``SELECT … FOR UPDATE`` so concurrent approve requests serialize:
    only the first pending→approved/rejected transition wins; losers see
    settled-or-claimed-without-result and never double-execute.
    """
    message_id = paused_message.id
    # Row lock serializes concurrent claims on the same paused assistant.
    locked = (
        await db.execute(
            select(Message).where(Message.id == message_id).with_for_update()
        )
    ).scalar_one()
    parts: list[Any] = list(locked.parts or [])
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

    approval_state = str(call_part.get("approvalState") or "")
    # Already claimed (or settled status without a result row yet): never
    # re-execute. Prefer returning a stored result; otherwise fail closed.
    if approval_state != "pending":
        return _claimed_without_result_failure(
            tool_call_id=tool_call_id,
            name=tool_name,
            approval_state=approval_state,
        )

    # CAS claim: only pending → approved/rejected. Commit BEFORE execute so a
    # crash after side-effect-start cannot leave the row re-claimable, and so
    # the row lock is released before the (potentially slow) executor runs.
    minted_claim = claim_id or f"claim-{secrets.token_urlsafe(12)}"
    claimed = deepcopy(call_part)
    if decision == "approve":
        claimed["approvalState"] = "approved"
        claimed["status"] = "running"
    else:
        claimed["approvalState"] = "rejected"
        claimed["status"] = "cancelled"
    claimed[APPROVAL_CLAIM_ID_KEY] = minted_claim
    claimed_parts = _replace_tool_call(parts, tool_call_id, claimed)
    await _persist_parts(db, locked, claimed_parts)

    # Re-read after commit (lock released). Confirm we still own the claim.
    await db.refresh(locked)
    parts_after = list(locked.parts or [])
    call_after = find_tool_call_part(parts_after, tool_call_id)
    settled_after = find_settled_tool_result(parts_after, tool_call_id)
    if settled_after is not None:
        return tool_result_dict_to_execution(
            settled_after, tool_call_id=tool_call_id, name=tool_name
        )
    if call_after is None:
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name or "unknown",
            status="failed",
            error="Tool call disappeared after claim.",
            approval_state="rejected",
        )
    winner_claim = call_after.get(APPROVAL_CLAIM_ID_KEY)
    if winner_claim != minted_claim:
        # Lost CAS — do not execute; return settled if present else fail closed.
        return _claimed_without_result_failure(
            tool_call_id=tool_call_id,
            name=tool_name,
            approval_state=str(call_after.get("approvalState") or "approved"),
        )

    subagent_id = call_after.get("subagentId")
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
            result = ToolExecutionResult(
                tool_call_id=result.tool_call_id,
                name=result.name,
                status=result.status,
                output=result.output,
                summary=result.summary,
                error=result.error,
                approval_state="approved",
            )

    # Settle under the same claim id.
    settled_call = deepcopy(call_after)
    settled_call["status"] = result.status
    settled_call["approvalState"] = result.approval_state
    settled_call[APPROVAL_CLAIM_ID_KEY] = minted_claim
    settled_parts = _replace_tool_call(parts_after, tool_call_id, settled_call)
    settled_parts.append(
        execution_to_tool_result_part(
            result, label=label, subagent_id=subagent_str
        )
    )
    await _persist_parts(db, locked, settled_parts)
    return result


async def load_paused_assistant_for_resume(
    db: AsyncSession, conversation_id: UUID
) -> Message | None:
    """Return the trailing awaiting_approval assistant, if any."""
    last = await messages_repo.get_last_assistant_message(db, conversation_id)
    if last is None or last.status != "awaiting_approval":
        return None
    return last
