"""Approval side-effect claim/settle (BE-007).

Approved tool side effects must not re-run when a resume stream fails after
execution. The pending ``tool_call`` on the paused assistant row is the claim
record:

1. **Claim** — only if ``approvalState == "pending"``, flip to
   ``approved``/``rejected`` + ``running``/``cancelled``, stamp a unique
   ``_approvalClaimId``, and **commit** before any executor call.
2. **Execute** (approve only) — run the tool once under that claim.
3. **Settle** — append a ``tool_result`` part and mark the tool_call terminal,
   then commit — independent of whether the post-approval model stream
   completes. Settlement is a **claim-owner conditional write**: it re-locks,
   requires matching ``_approvalClaimId``, and refuses to overwrite unless the
   call is still in the claimed ``approved``/``rejected`` +
   ``running``/``cancelled`` window.

Retry / crash recovery:
- Settled ``tool_result`` present → return it (no re-execute) when the client
  decision matches the durable approval; conflicting decisions raise
  ``ApprovalDecisionConflict``.
- Claimed (``approved``/``running``) **without** ``tool_result`` → do **not**
  re-execute; return a failed replay so the side effect is not doubled
  (covers kill between execute and settle, and stop/disconnect after claim).

Concurrency (H-005 / CAS): correctness is a **dialect-safe version CAS** on
``Message.parts_version`` — ``UPDATE … SET parts=…, parts_version=v+1 WHERE
id=? AND parts_version=v``. SQLite ignores ``SELECT FOR UPDATE``; the version
predicate still admits only one winner across sessions/processes. An optional
in-process ``asyncio`` lock reduces same-process contention but is **not** the
safety gate (tests race with the lock bypassed).
"""

from __future__ import annotations

import asyncio
import secrets
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.db.repositories import messages as messages_repo
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolCallRequest, ToolExecutionResult

# Reserved key on the tool_call part (not tool input) identifying the claim.
APPROVAL_CLAIM_ID_KEY = "_approvalClaimId"

# In-process claim locks: optional contention reducer. Correctness is the
# parts_version CAS below — do not treat this lock as cross-process safety.
_claim_locks: dict[tuple[str, str], asyncio.Lock] = {}
_claim_locks_guard = asyncio.Lock()
# When True, claim/settle skip the in-process lock (tests prove version CAS).
_bypass_claim_locks: bool = False


class ApprovalDecisionConflict(Exception):  # noqa: N818
    """Client decision contradicts a durable settled approval."""

    def __init__(self, *, stored_decision: str, requested_decision: str):
        self.stored_decision = stored_decision
        self.requested_decision = requested_decision
        super().__init__(
            f"Approval already settled as {stored_decision!r}; "
            f"cannot retry with {requested_decision!r}."
        )


@dataclass(frozen=True)
class SettlementOutcome:
    """Authoritative settlement plus the durable human decision."""

    result: ToolExecutionResult
    decision: str  # "approve" | "deny"
    claim_id: str | None = None
    already_settled: bool = False


def _decision_from_approval_state(approval_state: str) -> str:
    if approval_state == "rejected":
        return "deny"
    return "approve"


def _lock_key(message_id: UUID, tool_call_id: str) -> tuple[str, str]:
    return (str(message_id), tool_call_id)


async def _get_claim_lock(message_id: UUID, tool_call_id: str) -> asyncio.Lock:
    """Return a shared per-call lock, or a fresh unshared lock when bypassed."""
    if _bypass_claim_locks:
        return asyncio.Lock()
    key = _lock_key(message_id, tool_call_id)
    async with _claim_locks_guard:
        lock = _claim_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _claim_locks[key] = lock
        return lock


def find_tool_call_part(
    parts: object,
    tool_call_id: str,
    *,
    subagent_id: str | None = None,
) -> dict[str, Any] | None:
    """Locate a ``tool_call`` part by id (and optional subagent).

    When ``subagent_id`` is set, only that worker's call matches — prevents
    cross-worker confused-deputy replacement on colliding provider ids.
    """
    if not isinstance(parts, list):
        return None
    matches: list[dict[str, Any]] = []
    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("type") == "tool_call"
            and part.get("id") == tool_call_id
        ):
            if subagent_id is not None and part.get("subagentId") != subagent_id:
                continue
            matches.append(part)
    if not matches:
        return None
    return matches[0]


def find_settled_tool_result(
    parts: object,
    tool_call_id: str,
    *,
    subagent_id: str | None = None,
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
            if subagent_id is not None and part.get("subagentId") != subagent_id:
                continue
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
    parts: list[Any],
    tool_call_id: str,
    replacement: dict[str, Any],
    *,
    subagent_id: str | None = None,
) -> list[Any]:
    """Replace exactly one matching tool_call (id + optional subagent)."""
    replaced = False
    out: list[Any] = []
    for p in parts:
        if (
            not replaced
            and isinstance(p, dict)
            and p.get("type") == "tool_call"
            and p.get("id") == tool_call_id
            and (subagent_id is None or p.get("subagentId") == subagent_id)
        ):
            out.append(replacement)
            replaced = True
        else:
            out.append(p)
    return out


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


async def _cas_persist_parts(
    db: AsyncSession,
    *,
    message_id: UUID,
    parts: list[Any],
    expected_version: int,
) -> bool:
    """Atomic parts write gated on ``parts_version`` (SQLite + Postgres).

    Returns True when this session won the CAS (rowcount == 1).
    On loss, the session is rolled back — caller must re-read fresh state.
    """
    result = await db.execute(
        update(Message)
        .where(
            Message.id == message_id,
            Message.parts_version == expected_version,
        )
        .values(parts=parts, parts_version=expected_version + 1)
    )
    rowcount = getattr(result, "rowcount", None)
    if rowcount != 1:
        await db.rollback()
        return False
    await db.commit()
    return True


async def _lock_message(db: AsyncSession, message_id: UUID) -> Message:
    """Row-lock with populate_existing so identity-map stale parts cannot win."""
    locked = (
        await db.execute(
            select(Message)
            .where(Message.id == message_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    await db.refresh(locked)
    return locked


def _pseudo_settled_result(
    *,
    tool_call_id: str,
    tool_name: str,
    decision: str,
    output: dict[str, Any] | None,
    summary: str | None,
) -> ToolExecutionResult:
    safe_output = dict(output or {})
    if decision == "approve":
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name,
            status="succeeded",
            output=safe_output,
            summary=summary or "Clarifications recorded.",
            approval_state="approved",
        )
    return ToolExecutionResult(
        tool_call_id=tool_call_id,
        name=tool_name,
        status="cancelled",
        output=safe_output,
        summary=summary or "User skipped clarifying questions.",
        error="User denied the clarification pause.",
        approval_state="rejected",
    )


async def settle_pseudo_tool_approval(
    db: AsyncSession,
    *,
    paused_message: Message,
    tool_call_id: str,
    decision: str,
    output: dict[str, Any] | None = None,
    label: str | None = None,
    summary: str | None = None,
    claim_id: str | None = None,
) -> ToolExecutionResult:
    """Claim + settle a non-registry pseudo-tool (plan clarify / plan approval).

    Unlike ``claim_and_settle_approval``, this never invokes ``execute_tool``.
    It flips the paused ``tool_call`` to a terminal approval state and appends a
    ``tool_result`` carrying a bounded decision payload so reload no longer
    shows a permanently pending HITL card.

    Uses parts_version CAS for claim and settle — never an unconditional
    overwrite on CAS loss (H-005).
    """
    message_id = paused_message.id
    lock = await _get_claim_lock(message_id, tool_call_id)
    async with lock:
        locked = await _lock_message(db, message_id)
        parts: list[Any] = list(locked.parts or [])
        existing = find_settled_tool_result(parts, tool_call_id)
        call_part = find_tool_call_part(parts, tool_call_id)
        tool_name = str((call_part or {}).get("name") or "")

        if existing is not None:
            stored = _decision_from_approval_state(
                str(existing.get("approvalState") or existing.get("approval_state") or "")
            )
            if stored and stored != decision:
                raise ApprovalDecisionConflict(
                    stored_decision=stored, requested_decision=decision
                )
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
        if approval_state != "pending":
            return _claimed_without_result_failure(
                tool_call_id=tool_call_id,
                name=tool_name,
                approval_state=approval_state,
            )

        minted_claim = claim_id or f"claim-{secrets.token_urlsafe(12)}"
        claimed = deepcopy(call_part)
        if decision == "approve":
            claimed["approvalState"] = "approved"
            claimed["status"] = "running"
        else:
            claimed["approvalState"] = "rejected"
            claimed["status"] = "cancelled"
        claimed[APPROVAL_CLAIM_ID_KEY] = minted_claim
        expected_version = int(getattr(locked, "parts_version", 0) or 0)
        won = await _cas_persist_parts(
            db,
            message_id=message_id,
            parts=_replace_tool_call(parts, tool_call_id, claimed),
            expected_version=expected_version,
        )
        if not won:
            # Lost claim CAS — re-read; never stale-overwrite.
            locked = await _lock_message(db, message_id)
            parts = list(locked.parts or [])
            existing = find_settled_tool_result(parts, tool_call_id)
            call_part = find_tool_call_part(parts, tool_call_id)
            tool_name = str((call_part or {}).get("name") or tool_name)
            if existing is not None:
                stored = _decision_from_approval_state(
                    str(
                        existing.get("approvalState")
                        or existing.get("approval_state")
                        or ""
                    )
                )
                if stored and stored != decision:
                    raise ApprovalDecisionConflict(
                        stored_decision=stored, requested_decision=decision
                    )
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
            return _claimed_without_result_failure(
                tool_call_id=tool_call_id,
                name=tool_name,
                approval_state=str(call_part.get("approvalState") or "approved"),
            )

        locked = await _lock_message(db, message_id)
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
        if call_after.get(APPROVAL_CLAIM_ID_KEY) != minted_claim:
            return _claimed_without_result_failure(
                tool_call_id=tool_call_id,
                name=tool_name,
                approval_state=str(call_after.get("approvalState") or "approved"),
            )

        subagent_id = call_after.get("subagentId")
        subagent_str = str(subagent_id) if isinstance(subagent_id, str) else None
        result = _pseudo_settled_result(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            decision=decision,
            output=output,
            summary=summary,
        )

        settled = await _settle_under_claim(
            db,
            message_id=message_id,
            tool_call_id=tool_call_id,
            minted_claim=minted_claim,
            result=result,
            label=label,
            subagent_id=subagent_str,
        )
        if not settled:
            # Settle CAS lost and no durable result — fail closed.
            return _claimed_without_result_failure(
                tool_call_id=tool_call_id,
                name=tool_name,
                approval_state="approved" if decision == "approve" else "rejected",
            )
        return result


async def claim_and_settle_approval(
    db: AsyncSession,
    *,
    paused_message: Message,
    tool_call_id: str,
    decision: str,
    effective_input: dict[str, Any],
    label: str | None,
    claim_id: str | None = None,
    subagent_id: str | None = None,
) -> ToolExecutionResult:
    """Claim the pending approval (CAS), execute (if approve), settle on the row.

    See module docstring. Prefer ``claim_and_settle_approval_outcome`` when the
    caller needs the authoritative durable decision (H-006).
    """
    outcome = await claim_and_settle_approval_outcome(
        db,
        paused_message=paused_message,
        tool_call_id=tool_call_id,
        decision=decision,
        effective_input=effective_input,
        label=label,
        claim_id=claim_id,
        subagent_id=subagent_id,
    )
    return outcome.result


async def claim_and_settle_approval_outcome(
    db: AsyncSession,
    *,
    paused_message: Message,
    tool_call_id: str,
    decision: str,
    effective_input: dict[str, Any],
    label: str | None,
    claim_id: str | None = None,
    subagent_id: str | None = None,
) -> SettlementOutcome:
    """CAS claim/settle returning the durable decision for resume wiring.

    The in-process lock covers only the pending→claimed transition (and the
    final settle write). Execute runs *outside* the lock so concurrent losers
    can observe the committed claim without deadlocking behind a slow tool.
    """
    message_id = paused_message.id
    lock = await _get_claim_lock(message_id, tool_call_id)
    async with lock:
        claimed = await _claim_pending_locked(
            db,
            message_id=message_id,
            tool_call_id=tool_call_id,
            decision=decision,
            claim_id=claim_id,
            subagent_id=subagent_id,
        )
        if isinstance(claimed, SettlementOutcome):
            return claimed
        minted_claim, tool_name, part_subagent = claimed

    # Execute outside the claim lock (H-007 cancel cleanup still settles).
    try:
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
    except asyncio.CancelledError:
        cancel_result = ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name,
            status="cancelled",
            output={},
            summary="Approval execution cancelled before settle.",
            error="Approval execution was cancelled; side effect not settled.",
            approval_state="approved" if decision == "approve" else "rejected",
        )
        async with lock:
            await _settle_under_claim(
                db,
                message_id=message_id,
                tool_call_id=tool_call_id,
                minted_claim=minted_claim,
                result=cancel_result,
                label=label,
                subagent_id=part_subagent,
            )
        raise

    async with lock:
        settled_ok = await _settle_under_claim(
            db,
            message_id=message_id,
            tool_call_id=tool_call_id,
            minted_claim=minted_claim,
            result=result,
            label=label,
            subagent_id=part_subagent,
        )
    if not settled_ok:
        # Executed but settlement did not land — fail closed so callers do not
        # treat an unpersisted side effect as durable success.
        failed = _claimed_without_result_failure(
            tool_call_id=tool_call_id,
            name=tool_name,
            approval_state="approved" if decision == "approve" else "rejected",
        )
        return SettlementOutcome(
            result=failed,
            decision=_decision_from_approval_state(failed.approval_state),
            claim_id=minted_claim,
            already_settled=False,
        )
    return SettlementOutcome(
        result=result,
        decision=decision,
        claim_id=minted_claim,
        already_settled=False,
    )


async def _claim_pending_locked(
    db: AsyncSession,
    *,
    message_id: UUID,
    tool_call_id: str,
    decision: str,
    claim_id: str | None,
    subagent_id: str | None,
) -> SettlementOutcome | tuple[str, str, str | None]:
    locked = await _lock_message(db, message_id)
    parts: list[Any] = list(locked.parts or [])
    existing = find_settled_tool_result(
        parts, tool_call_id, subagent_id=subagent_id
    )
    call_part = find_tool_call_part(parts, tool_call_id, subagent_id=subagent_id)
    tool_name = str((call_part or {}).get("name") or "")
    part_subagent = (
        str(call_part.get("subagentId"))
        if isinstance(call_part, dict) and isinstance(call_part.get("subagentId"), str)
        else subagent_id
    )

    if existing is not None:
        stored_decision = _decision_from_approval_state(
            str(existing.get("approvalState") or existing.get("approval_state") or "")
        )
        if stored_decision != decision:
            raise ApprovalDecisionConflict(
                stored_decision=stored_decision,
                requested_decision=decision,
            )
        result = tool_result_dict_to_execution(
            existing, tool_call_id=tool_call_id, name=tool_name
        )
        return SettlementOutcome(
            result=result,
            decision=stored_decision,
            claim_id=(
                str(call_part.get(APPROVAL_CLAIM_ID_KEY))
                if isinstance(call_part, dict)
                and call_part.get(APPROVAL_CLAIM_ID_KEY) is not None
                else None
            ),
            already_settled=True,
        )

    if call_part is None:
        result = ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name or "unknown",
            status="failed",
            error="No matching tool call to settle.",
            approval_state="rejected",
        )
        return SettlementOutcome(result=result, decision="deny", already_settled=False)

    approval_state = str(call_part.get("approvalState") or "")
    if approval_state != "pending":
        # Already claimed without a result: fail closed (never re-execute).
        result = _claimed_without_result_failure(
            tool_call_id=tool_call_id,
            name=tool_name,
            approval_state=approval_state,
        )
        return SettlementOutcome(
            result=result,
            decision=_decision_from_approval_state(result.approval_state),
            claim_id=(
                str(call_part.get(APPROVAL_CLAIM_ID_KEY))
                if call_part.get(APPROVAL_CLAIM_ID_KEY) is not None
                else None
            ),
            already_settled=False,
        )

    # CAS claim: only pending → approved/rejected. Commit BEFORE execute.
    # Dialect-safe: UPDATE … WHERE parts_version=expected (H-005).
    minted_claim = claim_id or f"claim-{secrets.token_urlsafe(12)}"
    claimed = deepcopy(call_part)
    if decision == "approve":
        claimed["approvalState"] = "approved"
        claimed["status"] = "running"
    else:
        claimed["approvalState"] = "rejected"
        claimed["status"] = "cancelled"
    claimed[APPROVAL_CLAIM_ID_KEY] = minted_claim
    claimed_parts = _replace_tool_call(
        parts, tool_call_id, claimed, subagent_id=part_subagent
    )
    expected_version = int(getattr(locked, "parts_version", 0) or 0)
    won = await _cas_persist_parts(
        db,
        message_id=message_id,
        parts=claimed_parts,
        expected_version=expected_version,
    )
    if not won:
        # Lost the version race — re-read and take settled / claimed-without-result.
        locked = await _lock_message(db, message_id)
        parts = list(locked.parts or [])
        existing = find_settled_tool_result(
            parts, tool_call_id, subagent_id=subagent_id
        )
        call_part = find_tool_call_part(parts, tool_call_id, subagent_id=subagent_id)
        tool_name = str((call_part or {}).get("name") or tool_name)
        if existing is not None:
            stored_decision = _decision_from_approval_state(
                str(
                    existing.get("approvalState")
                    or existing.get("approval_state")
                    or ""
                )
            )
            if stored_decision != decision:
                raise ApprovalDecisionConflict(
                    stored_decision=stored_decision,
                    requested_decision=decision,
                )
            result = tool_result_dict_to_execution(
                existing, tool_call_id=tool_call_id, name=tool_name
            )
            return SettlementOutcome(
                result=result,
                decision=stored_decision,
                claim_id=(
                    str(call_part.get(APPROVAL_CLAIM_ID_KEY))
                    if isinstance(call_part, dict)
                    and call_part.get(APPROVAL_CLAIM_ID_KEY) is not None
                    else None
                ),
                already_settled=True,
            )
        if call_part is None:
            result = ToolExecutionResult(
                tool_call_id=tool_call_id,
                name=tool_name or "unknown",
                status="failed",
                error="No matching tool call to settle.",
                approval_state="rejected",
            )
            return SettlementOutcome(
                result=result, decision="deny", already_settled=False
            )
        result = _claimed_without_result_failure(
            tool_call_id=tool_call_id,
            name=tool_name,
            approval_state=str(call_part.get("approvalState") or "approved"),
        )
        return SettlementOutcome(
            result=result,
            decision=_decision_from_approval_state(result.approval_state),
            claim_id=(
                str(call_part.get(APPROVAL_CLAIM_ID_KEY))
                if call_part.get(APPROVAL_CLAIM_ID_KEY) is not None
                else None
            ),
            already_settled=False,
        )

    # Re-lock after commit; confirm we still own the claim (true CAS).
    locked = await _lock_message(db, message_id)
    parts_after = list(locked.parts or [])
    call_after = find_tool_call_part(
        parts_after, tool_call_id, subagent_id=part_subagent
    )
    settled_after = find_settled_tool_result(
        parts_after, tool_call_id, subagent_id=part_subagent
    )
    if settled_after is not None:
        stored_decision = _decision_from_approval_state(
            str(
                settled_after.get("approvalState")
                or settled_after.get("approval_state")
                or ""
            )
        )
        if stored_decision != decision:
            raise ApprovalDecisionConflict(
                stored_decision=stored_decision,
                requested_decision=decision,
            )
        result = tool_result_dict_to_execution(
            settled_after, tool_call_id=tool_call_id, name=tool_name
        )
        return SettlementOutcome(
            result=result,
            decision=stored_decision,
            claim_id=minted_claim,
            already_settled=True,
        )
    if call_after is None:
        result = ToolExecutionResult(
            tool_call_id=tool_call_id,
            name=tool_name or "unknown",
            status="failed",
            error="Tool call disappeared after claim.",
            approval_state="rejected",
        )
        return SettlementOutcome(result=result, decision="deny", claim_id=minted_claim)

    winner_claim = call_after.get(APPROVAL_CLAIM_ID_KEY)
    if winner_claim != minted_claim:
        result = _claimed_without_result_failure(
            tool_call_id=tool_call_id,
            name=tool_name,
            approval_state=str(call_after.get("approvalState") or "approved"),
        )
        return SettlementOutcome(
            result=result,
            decision=_decision_from_approval_state(result.approval_state),
            claim_id=str(winner_claim) if winner_claim is not None else None,
        )

    return minted_claim, tool_name, part_subagent



async def _settle_under_claim(
    db: AsyncSession,
    *,
    message_id: UUID,
    tool_call_id: str,
    minted_claim: str,
    result: ToolExecutionResult,
    label: str | None,
    subagent_id: str | None,
) -> bool:
    """Settle only when this claim still owns the running/rejected call.

    Claim-owner conditional write (H-005): refuse unless ``_approvalClaimId``
    matches **and** the call is still in the claimed approval/status window.
    Uses parts_version CAS so a concurrent writer cannot clobber settlement.

    Returns True when settlement is durable (already settled or this write won).
    On CAS loss, retries once from fresh state; never silently reports success
    after a failed write.
    """
    for _attempt in range(2):
        locked = await _lock_message(db, message_id)
        fresh_parts = list(locked.parts or [])
        if find_settled_tool_result(fresh_parts, tool_call_id, subagent_id=subagent_id):
            return True
        call_fresh = find_tool_call_part(
            fresh_parts, tool_call_id, subagent_id=subagent_id
        )
        if call_fresh is None:
            return False
        if call_fresh.get(APPROVAL_CLAIM_ID_KEY) != minted_claim:
            return False
        approval = str(
            call_fresh.get("approvalState") or call_fresh.get("approval_state") or ""
        )
        status = str(call_fresh.get("status") or "")
        if approval not in ("approved", "rejected"):
            return False
        if status not in ("running", "cancelled"):
            return False
        settled_call = deepcopy(call_fresh)
        settled_call["status"] = result.status
        settled_call["approvalState"] = result.approval_state
        settled_call[APPROVAL_CLAIM_ID_KEY] = minted_claim
        settled_parts = _replace_tool_call(
            fresh_parts, tool_call_id, settled_call, subagent_id=subagent_id
        )
        settled_parts.append(
            execution_to_tool_result_part(
                result, label=label, subagent_id=subagent_id
            )
        )
        expected_version = int(getattr(locked, "parts_version", 0) or 0)
        won = await _cas_persist_parts(
            db,
            message_id=message_id,
            parts=settled_parts,
            expected_version=expected_version,
        )
        if won:
            return True
        # CAS lost — retry from fresh state once; never overwrite unconditionally.
    # Final check: another writer may have settled while we lost the race.
    locked = await _lock_message(db, message_id)
    fresh_parts = list(locked.parts or [])
    return (
        find_settled_tool_result(fresh_parts, tool_call_id, subagent_id=subagent_id)
        is not None
    )


async def load_paused_assistant_for_resume(
    db: AsyncSession, conversation_id: UUID
) -> Message | None:
    """Return the latest awaiting_approval assistant, skipping later stopped rows.

    H-008: a stop/disconnect after resume persists a newer ``stopped`` assistant;
    resume must still find the original ``awaiting_approval`` checkpoint.
    """
    return await messages_repo.get_latest_assistant_with_status(
        db, conversation_id, status="awaiting_approval"
    )
