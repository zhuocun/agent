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

Retry / crash recovery (AC-01, fail closed):
- Settled ``tool_result`` present → return it (no re-execute) when the client
  decision matches the durable approval; conflicting decisions raise
  ``ApprovalDecisionConflict``.
- Claimed (``approved``/``running``) **without** ``tool_result`` → the claim
  belongs to another invocation, so this one **always** raises
  ``ApprovalSettlementIncomplete``, whichever way it decided: it neither
  re-executes nor writes, and it does not report a decision conflict, because an
  unsettled claim's recorded decision is provisional and not this caller's to
  read as durable truth (``ApprovalDecisionConflict`` needs a settled
  ``tool_result`` — H-006). Execute runs outside the claim lock, so a live
  winner's row is byte-for-byte what a crashed claim leaves behind, and nothing
  observable from here distinguishes them — a second Fly machine cannot see
  whether the claiming machine is still running the side effect, and elapsed
  time does not prove it stopped. Writing a failed replay there would clobber a
  side effect that may still succeed, so the row stays claimed until its owner
  settles it. Terminalizing a genuinely orphaned claim requires executor
  idempotency/fencing or an explicit administrative reconciliation; neither
  exists, and no timeout/expiry branch substitutes for them.
- **Only the invocation that minted a claim may settle under it.** That includes
  the one recovery write that remains: when the owner executed but lost the
  settle CAS, it writes the failed replay under *its own* claim id.
- Pseudo tools (plan approval / clarify) are separate: settlement replays no
  external side effect, so a same-decision retry may adopt an orphaned claim and
  finish the interrupted write (``_adoptable_claim``).

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
from typing import Any, NoReturn
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


class ApprovalSettlementIncomplete(Exception):  # noqa: N818
    """Claim exists but no durable tool_result — caller must not resume."""

    def __init__(self, *, tool_call_id: str, detail: str | None = None):
        self.tool_call_id = tool_call_id
        super().__init__(
            detail
            or (
                "Tool approval claim has no durable settled result yet; "
                "retry after the winning settlement commits."
            )
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


async def _release_claim_lock_if_idle(message_id: UUID, tool_call_id: str) -> None:
    """Drop an idle in-process claim lock so ``_claim_locks`` cannot grow forever.

    Only removes the entry when the lock is unlocked and has no waiters — safe
    after a terminal settlement returns and the ``async with lock`` block has
    exited. Concurrent getters re-create the lock on demand.
    """
    if _bypass_claim_locks:
        return
    key = _lock_key(message_id, tool_call_id)
    async with _claim_locks_guard:
        lock = _claim_locks.get(key)
        if lock is None:
            return
        if lock.locked():
            return
        waiters = getattr(lock, "_waiters", None)
        if waiters:
            return
        del _claim_locks[key]


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
    """Terminal replay for a claim **this invocation owns** but could not settle.

    Only reachable from the owner's post-execute recovery write. A foreign claim
    fails closed instead (see the module docstring).
    """
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


def _outcome_from_settled_part(
    existing: dict[str, Any],
    *,
    tool_call_id: str,
    tool_name: str,
    decision: str,
    call_part: dict[str, Any] | None,
    already_settled: bool,
) -> SettlementOutcome:
    """Build an outcome from a durable tool_result, enforcing decision match."""
    stored = _decision_from_approval_state(
        str(existing.get("approvalState") or existing.get("approval_state") or "")
    )
    if stored and stored != decision:
        raise ApprovalDecisionConflict(
            stored_decision=stored, requested_decision=decision
        )
    result = tool_result_dict_to_execution(
        existing, tool_call_id=tool_call_id, name=tool_name
    )
    claim = None
    if isinstance(call_part, dict) and call_part.get(APPROVAL_CLAIM_ID_KEY) is not None:
        claim = str(call_part.get(APPROVAL_CLAIM_ID_KEY))
    return SettlementOutcome(
        result=result,
        decision=stored or decision,
        claim_id=claim,
        already_settled=already_settled,
    )


def _adoptable_claim(call_part: dict[str, Any], decision: str) -> str | None:
    """FL-29: the row's own claim id when a pseudo-tool claim never settled.

    A crash (or a Fly machine restart) between the claim commit and the settle
    write leaves the ``tool_call`` terminal-but-unsettled, which
    ``_raise_pseudo_incomplete_or_conflict`` turns into a permanent 409 — the pause card
    can never be resolved again and the whole turn is stranded. Pseudo-tool
    settlement never calls ``execute_tool``
    (``settle_pseudo_tool_approval_outcome``), so re-entering under the existing
    claim replays no side effect: it only finishes the write that was
    interrupted. Returns None for an absent claim or a decision the row does not
    already record, so an opposite decision still conflicts. The registry path
    (``claim_and_settle_approval_outcome``) keeps failing closed — BE-007.
    """
    approval_state = str(call_part.get("approvalState") or "")
    if approval_state not in ("approved", "rejected"):
        return None
    if _decision_from_approval_state(approval_state) != decision:
        return None
    existing = call_part.get(APPROVAL_CLAIM_ID_KEY)
    return str(existing) if existing is not None else None


def _raise_foreign_claim_incomplete(*, tool_call_id: str) -> NoReturn:
    """The one exit for a registry claim this invocation does not own.

    Unconditionally incomplete — the requested decision is not consulted, so an
    opposite-decision retry gets the same answer as a matching one. A claimed but
    unsettled row records a decision that is still *provisional*: the claim window
    is exactly the stretch where ``approvalState`` says ``approved`` while no
    ``tool_result`` exists, and the owner may yet settle it succeeded, failed, or
    cancelled. Answering ``ApprovalDecisionConflict`` there would assert a durable
    decision this caller cannot see, and it would hand a foreign caller a branch
    that varies with the claim's contents — the first step back toward acting on
    someone else's in-flight side effect. ``ApprovalDecisionConflict`` stays
    reserved for a genuinely settled ``tool_result`` (H-006).

    Never returns and never writes, so no caller can turn a foreign claim into a
    durable outcome regardless of how long it has been outstanding.
    """
    raise ApprovalSettlementIncomplete(tool_call_id=tool_call_id)


def _raise_pseudo_incomplete_or_conflict(
    *,
    tool_call_id: str,
    decision: str,
    approval_state: str,
) -> NoReturn:
    """Pseudo-tool claimed-without-result: conflict on opposite decision.

    Pseudo-tool only — the registry path uses
    ``_raise_foreign_claim_incomplete`` and never reports a conflict from an
    unsettled claim. A pseudo claim carries no external side effect, so its
    recorded decision is the whole outcome and contradicting it is a real
    conflict rather than a guess about work in flight; that is the same asymmetry
    that lets ``_adoptable_claim`` finish a same-decision write here and nowhere
    else.
    """
    if approval_state in ("approved", "rejected"):
        claimed_decision = _decision_from_approval_state(approval_state)
        if claimed_decision != decision:
            raise ApprovalDecisionConflict(
                stored_decision=claimed_decision, requested_decision=decision
            )
    raise ApprovalSettlementIncomplete(tool_call_id=tool_call_id)


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
    """Claim + settle a pseudo-tool; prefer ``settle_pseudo_tool_approval_outcome``."""
    outcome = await settle_pseudo_tool_approval_outcome(
        db,
        paused_message=paused_message,
        tool_call_id=tool_call_id,
        decision=decision,
        output=output,
        label=label,
        summary=summary,
        claim_id=claim_id,
    )
    return outcome.result


async def settle_pseudo_tool_approval_outcome(
    db: AsyncSession,
    *,
    paused_message: Message,
    tool_call_id: str,
    decision: str,
    output: dict[str, Any] | None = None,
    label: str | None = None,
    summary: str | None = None,
    claim_id: str | None = None,
) -> SettlementOutcome:
    """Claim + settle a non-registry pseudo-tool (plan clarify / plan approval).

    Unlike ``claim_and_settle_approval``, this never invokes ``execute_tool``.
    It flips the paused ``tool_call`` to a terminal approval state and appends a
    ``tool_result`` carrying a bounded decision payload so reload no longer
    shows a permanently pending HITL card.

    Uses parts_version CAS for claim and settle — never an unconditional
    overwrite on CAS loss (H-005). Returns only after a durable ``tool_result``
    exists; the stored decision is authoritative. Callers must not build a
    resume seed from the request decision when this raises
    ``ApprovalSettlementIncomplete`` or ``ApprovalDecisionConflict``.
    """
    message_id = paused_message.id
    try:
        lock = await _get_claim_lock(message_id, tool_call_id)
        async with lock:
            locked = await _lock_message(db, message_id)
            parts: list[Any] = list(locked.parts or [])
            existing = find_settled_tool_result(parts, tool_call_id)
            call_part = find_tool_call_part(parts, tool_call_id)
            tool_name = str((call_part or {}).get("name") or "")

            if existing is not None:
                return _outcome_from_settled_part(
                    existing,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    decision=decision,
                    call_part=call_part,
                    already_settled=True,
                )

            if call_part is None:
                raise ApprovalSettlementIncomplete(
                    tool_call_id=tool_call_id,
                    detail="No matching tool call to settle.",
                )

            approval_state = str(call_part.get("approvalState") or "")
            # FL-29: adopt an orphaned claim instead of stranding the card.
            adopted_claim = _adoptable_claim(call_part, decision)
            minted_claim = adopted_claim or claim_id or f"claim-{secrets.token_urlsafe(12)}"
            if adopted_claim is None:
                if approval_state != "pending":
                    _raise_pseudo_incomplete_or_conflict(
                        tool_call_id=tool_call_id,
                        decision=decision,
                        approval_state=approval_state,
                    )

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
                        return _outcome_from_settled_part(
                            existing,
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            decision=decision,
                            call_part=call_part,
                            already_settled=True,
                        )
                    if call_part is None:
                        raise ApprovalSettlementIncomplete(
                            tool_call_id=tool_call_id,
                            detail="No matching tool call to settle.",
                        )
                    # FL-29: the CAS winner may itself be an unsettled
                    # same-decision claim. Fixing only the straight-line exit
                    # above would leave this window stranding the card.
                    adopted_claim = _adoptable_claim(call_part, decision)
                    if adopted_claim is None:
                        _raise_pseudo_incomplete_or_conflict(
                            tool_call_id=tool_call_id,
                            decision=decision,
                            approval_state=str(
                                call_part.get("approvalState") or "approved"
                            ),
                        )
                    minted_claim = str(adopted_claim)

            locked = await _lock_message(db, message_id)
            parts_after = list(locked.parts or [])
            call_after = find_tool_call_part(parts_after, tool_call_id)
            settled_after = find_settled_tool_result(parts_after, tool_call_id)
            if settled_after is not None:
                return _outcome_from_settled_part(
                    settled_after,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    decision=decision,
                    call_part=call_after,
                    already_settled=True,
                )
            if call_after is None:
                raise ApprovalSettlementIncomplete(
                    tool_call_id=tool_call_id,
                    detail="Tool call disappeared after claim.",
                )
            if call_after.get(APPROVAL_CLAIM_ID_KEY) != minted_claim:
                _raise_pseudo_incomplete_or_conflict(
                    tool_call_id=tool_call_id,
                    decision=decision,
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
            # Re-read durable state — never resume from the request decision alone.
            locked = await _lock_message(db, message_id)
            parts_final = list(locked.parts or [])
            durable = find_settled_tool_result(parts_final, tool_call_id)
            call_final = find_tool_call_part(parts_final, tool_call_id)
            tool_name = str((call_final or {}).get("name") or tool_name)
            if durable is None:
                if not settled:
                    _raise_pseudo_incomplete_or_conflict(
                        tool_call_id=tool_call_id,
                        decision=decision,
                        approval_state=(
                            "approved" if decision == "approve" else "rejected"
                        ),
                    )
                raise ApprovalSettlementIncomplete(tool_call_id=tool_call_id)
            return _outcome_from_settled_part(
                durable,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                decision=decision,
                call_part=call_final,
                already_settled=False,
            )
    finally:
        await _release_claim_lock_if_idle(message_id, tool_call_id)


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
    final settle write). Execute runs *outside* the lock so concurrent losers can
    observe the committed claim without deadlocking behind a slow tool. Those
    losers do not own the claim, so they raise ``ApprovalSettlementIncomplete``
    rather than settle on the winner's behalf (AC-01) — the winner's real result
    is the only thing that ever lands on the row.
    """
    message_id = paused_message.id
    try:
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
            # treat an unpersisted side effect as durable success. FL-31: write
            # that failure under the claim *we* minted so the row does not strand
            # at approved/running. ``_settle_under_claim`` no-ops if the row has
            # moved on, so this can never overwrite anyone else's settlement.
            failed = _claimed_without_result_failure(
                tool_call_id=tool_call_id,
                name=tool_name,
                approval_state="approved" if decision == "approve" else "rejected",
            )
            async with lock:
                await _settle_under_claim(
                    db,
                    message_id=message_id,
                    tool_call_id=tool_call_id,
                    minted_claim=minted_claim,
                    result=failed,
                    label=label,
                    subagent_id=part_subagent,
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
    finally:
        # B19: prune idle lock entries after terminal settlement (or early return).
        await _release_claim_lock_if_idle(message_id, tool_call_id)


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
        # AC-01: the claim is someone else's and no durable result exists. Fail
        # closed — never re-execute, and never write a terminal failure that
        # could clobber a side effect still running under that claim, whether it
        # was claimed a millisecond or a week ago and whichever way this request
        # decided.
        _raise_foreign_claim_incomplete(tool_call_id=tool_call_id)

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
        # Lost the version race — re-read durable state. Never synthesize the
        # winner's settlement from our own request (AC-01).
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
        # The winner holds the claim and has not settled yet: fail closed.
        _raise_foreign_claim_incomplete(tool_call_id=tool_call_id)

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
        # Our claim id was replaced between commit and re-lock, so this
        # invocation is no longer the owner and may not settle under it.
        _raise_foreign_claim_incomplete(tool_call_id=tool_call_id)

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
