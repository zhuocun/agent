"""Unit tests for BE-007 claim/settle CAS and claimed-without-result recovery."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, User
from app.tools import approval_settlement
from app.tools.approval_settlement import (
    APPROVAL_CLAIM_ID_KEY,
    ApprovalSettlementIncomplete,
    claim_and_settle_approval,
    claim_and_settle_approval_outcome,
    settle_pseudo_tool_approval,
)
from app.tools.builtin import TOOL_REGISTRY, ToolSpec
from app.tools.protocol import ToolCallRequest, ToolExecutionResult

pytestmark = pytest.mark.asyncio


async def _seed_paused_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    parts: list[dict[str, Any]],
) -> Message:
    async with session_factory() as session:
        user = User(is_anonymous=True)
        session.add(user)
        await session.flush()
        convo = Conversation(
            user_id=user.id,
            title="claim test",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.flush()
        msg = Message(
            conversation_id=convo.id,
            role="assistant",
            parts=parts,
            status="awaiting_approval",
            attribution={},
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg


def _pending_calendar_parts(*, tool_call_id: str = "cal_1") -> list[dict[str, Any]]:
    return [
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": "calendar_create_event",
            "label": "Create calendar event",
            "status": "awaiting_approval",
            "approvalState": "pending",
            "input": {"title": "Planning review"},
        }
    ]


def _assert_race_outcomes_never_clobber(results: list[Any]) -> None:
    """Exactly one winner succeeds; every other racer defers or replays it."""
    succeeded = [
        r
        for r in results
        if isinstance(r, ToolExecutionResult) and r.status == "succeeded"
    ]
    assert succeeded, f"no racer produced a succeeded result: {results!r}"
    for r in results:
        if isinstance(r, ToolExecutionResult):
            assert r.status == "succeeded", f"racer clobbered the winner: {r!r}"
        else:
            assert isinstance(r, ApprovalSettlementIncomplete), repr(r)


async def _durable_tool_result(
    session_factory: async_sessionmaker[AsyncSession],
    message_id: Any,
    tool_call_id: str,
) -> dict[str, Any] | None:
    """Read the persisted ``tool_result`` for a call, from a fresh session."""
    async with session_factory() as session:
        row = await session.get(Message, message_id)
        assert row is not None
        await session.refresh(row)
        return approval_settlement.find_settled_tool_result(row.parts, tool_call_id)


def _gated_calendar_spec(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exec_count: dict[str, int],
    entered: asyncio.Event,
    release: asyncio.Event,
) -> None:
    """Swap in a calendar executor that parks mid-execution until released."""
    original = TOOL_REGISTRY["calendar_create_event"]
    real = original.executor

    async def _gated(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        entered.set()
        await release.wait()
        return await real(call)

    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_gated,
            prod_safe=original.prod_safe,
        ),
    )


async def test_claimed_without_result_does_not_reexecute(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crash after claim / before settle → retry must not run the executor."""
    tool_call_id = "cal_claimed"
    parts = _pending_calendar_parts(tool_call_id=tool_call_id)
    # Simulate prior claim commit with no tool_result.
    parts[0]["approvalState"] = "approved"
    parts[0]["status"] = "running"
    parts[0][APPROVAL_CLAIM_ID_KEY] = "claim-prior"
    msg = await _seed_paused_message(session_factory, parts=parts)

    exec_count = {"n": 0}

    async def _boom(_call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        raise AssertionError("executor must not run on claimed-without-result")

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_boom,
            prod_safe=original.prod_safe,
        ),
    )

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        result = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
        )

    assert exec_count["n"] == 0
    assert result.status == "failed"
    assert "refusing to re-execute" in (result.error or "")


async def test_cas_second_claim_does_not_reexecute(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only pending→approved CAS wins; a second claim reuses settlement."""
    tool_call_id = "cal_cas"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    real = TOOL_REGISTRY["calendar_create_event"].executor

    async def _counting(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real(call)

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_counting,
            prod_safe=original.prod_safe,
        ),
    )

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        first = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-a",
        )
    assert first.status == "succeeded"
    assert exec_count["n"] == 1
    first_output = deepcopy(first.output)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        second = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-b",
        )
    assert exec_count["n"] == 1
    assert second.status == "succeeded"
    assert second.output == first_output


async def test_claim_commits_before_execute(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After claim flush/commit, the row is no longer pending even if execute fails."""
    tool_call_id = "cal_precommit"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    async def _fail(_call: ToolCallRequest) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            name="calendar_create_event",
            status="failed",
            error="simulated executor failure",
            approval_state="approved",
        )

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_fail,
            prod_safe=original.prod_safe,
        ),
    )

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        result = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-pre",
        )
    assert result.status == "failed"

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        call = approval_settlement.find_tool_call_part(row.parts, tool_call_id)
        assert call is not None
        assert call.get("approvalState") == "approved"
        assert call.get(APPROVAL_CLAIM_ID_KEY) == "claim-pre"
        settled = approval_settlement.find_settled_tool_result(row.parts, tool_call_id)
        assert settled is not None


async def test_concurrent_claims_only_one_executes(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W1: a retry inside the live execute window defers instead of clobbering.

    Execute deliberately runs outside the claim lock (H-007), so the row a
    concurrent retry reads mid-flight — ``approved`` / ``running`` / a claim id /
    no ``tool_result`` — is byte-for-byte what a crashed claim leaves behind.
    This test previously asserted the retry got a ``failed`` result, which meant
    FL-31 recovery had *written* that failure over a side effect that was still
    running: the winner then returned its real success to its caller while the
    durable row said failed. The live-claim registry makes the two cases
    distinguishable, so the retry now raises ``ApprovalSettlementIncomplete``
    ("retry after the winning settlement commits", 409) and leaves the row
    untouched until the winner's real result lands.
    """
    tool_call_id = "cal_race"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    entered = asyncio.Event()
    release = asyncio.Event()
    real = TOOL_REGISTRY["calendar_create_event"].executor

    async def _gated(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        entered.set()
        await release.wait()
        return await real(call)

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_gated,
            prod_safe=original.prod_safe,
        ),
    )

    async def _approve(claim: str) -> ToolExecutionResult:
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            return await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
                claim_id=claim,
            )

    first_task = asyncio.create_task(_approve("claim-first"))
    await asyncio.wait_for(entered.wait(), timeout=5.0)
    assert await _durable_tool_result(session_factory, msg.id, tool_call_id) is None

    # First claim committed and is inside execute; second must neither re-run it
    # nor settle on its behalf.
    with pytest.raises(ApprovalSettlementIncomplete) as raised:
        await _approve("claim-second")
    assert raised.value.tool_call_id == tool_call_id
    assert await _durable_tool_result(session_factory, msg.id, tool_call_id) is None

    release.set()
    first = await first_task

    assert exec_count["n"] == 1
    assert first.status == "succeeded"
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "succeeded"
    assert settled.get("output") == first.output


async def test_simultaneous_preloaded_claims_only_one_executes(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-005: truly simultaneous SQLite claims — only one executor runs.

    The loser's shape depends on how far the winner got: it either replays the
    winner's settled result or, when the winner is still live, defers with
    ``ApprovalSettlementIncomplete`` (W1). What it must never do is settle a
    ``failed`` result on the winner's behalf, so the assertion is on the durable
    row rather than on which of the two branches the loser happened to take.
    """
    tool_call_id = "cal_simultaneous"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    real = TOOL_REGISTRY["calendar_create_event"].executor
    gate = asyncio.Event()
    both_ready = asyncio.Event()
    ready_count = {"n": 0}

    async def _counting(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real(call)

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_counting,
            prod_safe=original.prod_safe,
        ),
    )

    async def _approve(claim: str) -> ToolExecutionResult:
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            ready_count["n"] += 1
            if ready_count["n"] >= 2:
                both_ready.set()
            await both_ready.wait()
            await gate.wait()
            return await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
                claim_id=claim,
            )

    t1 = asyncio.create_task(_approve("claim-a"))
    t2 = asyncio.create_task(_approve("claim-b"))
    await asyncio.wait_for(both_ready.wait(), timeout=5.0)
    gate.set()
    results = await asyncio.gather(t1, t2, return_exceptions=True)
    assert exec_count["n"] == 1
    _assert_race_outcomes_never_clobber(results)
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "succeeded"


async def test_settled_decision_conflict_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-006: retrying with the opposite decision must not rewrite settlement."""
    from app.tools.approval_settlement import (
        ApprovalDecisionConflict,
        claim_and_settle_approval_outcome,
    )

    tool_call_id = "cal_conflict"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        denied = await claim_and_settle_approval_outcome(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="deny",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
        )
    assert denied.decision == "deny"
    assert denied.result.status == "cancelled"

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        with pytest.raises(ApprovalDecisionConflict):
            await claim_and_settle_approval_outcome(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
            )


async def test_replace_tool_call_is_subagent_scoped() -> None:
    """H-004: colliding provider ids across workers do not cross-replace."""
    from app.tools.approval_settlement import _replace_tool_call

    parts = [
        {
            "type": "tool_call",
            "id": "same",
            "name": "calendar_create_event",
            "subagentId": "worker-0",
            "approvalState": "pending",
            "status": "awaiting_approval",
        },
        {
            "type": "tool_call",
            "id": "same",
            "name": "calendar_create_event",
            "subagentId": "worker-1",
            "approvalState": "pending",
            "status": "awaiting_approval",
        },
    ]
    replacement = {
        **parts[0],
        "approvalState": "approved",
        "status": "running",
    }
    out = _replace_tool_call(parts, "same", replacement, subagent_id="worker-0")
    assert out[0]["approvalState"] == "approved"
    assert out[1]["approvalState"] == "pending"


async def test_load_paused_assistant_skips_later_stopped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """H-008: resume lookup finds awaiting_approval behind a later stopped row."""
    from app.tools.approval_settlement import load_paused_assistant_for_resume

    async with session_factory() as session:
        user = User(is_anonymous=True)
        session.add(user)
        await session.flush()
        convo = Conversation(
            user_id=user.id,
            title="shadow test",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.flush()
        paused = Message(
            conversation_id=convo.id,
            role="assistant",
            parts=_pending_calendar_parts(tool_call_id="cal_shadow"),
            status="awaiting_approval",
            attribution={},
        )
        session.add(paused)
        await session.flush()
        stopped = Message(
            conversation_id=convo.id,
            role="assistant",
            parts=[{"type": "text", "text": "partial"}],
            status="stopped",
            attribution={},
        )
        session.add(stopped)
        await session.commit()
        conv_id = convo.id
        paused_id = paused.id

    async with session_factory() as session:
        found = await load_paused_assistant_for_resume(session, conv_id)
        assert found is not None
        assert found.id == paused_id
        assert found.status == "awaiting_approval"


async def test_cas_race_without_process_lock_only_one_executes(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-005 / H-013: version CAS wins with in-process locks bypassed.

    The registry is deliberately *not* disabled by ``_bypass_claim_locks``, so
    the loser here may defer with ``ApprovalSettlementIncomplete`` rather than
    return a failed replay (W1). Either branch keeps the single-execution
    guarantee this test exists for; the durable row is the assertion of record.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "cal_cas_nolock"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    real = TOOL_REGISTRY["calendar_create_event"].executor
    both_ready = asyncio.Event()
    gate = asyncio.Event()
    ready_count = {"n": 0}

    async def _counting(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real(call)

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_counting,
            prod_safe=original.prod_safe,
        ),
    )

    async def _approve(claim: str) -> ToolExecutionResult:
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            ready_count["n"] += 1
            if ready_count["n"] >= 2:
                both_ready.set()
            await both_ready.wait()
            await gate.wait()
            return await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
                claim_id=claim,
            )

    t1 = asyncio.create_task(_approve("claim-a"))
    t2 = asyncio.create_task(_approve("claim-b"))
    await asyncio.wait_for(both_ready.wait(), timeout=5.0)
    gate.set()
    results = await asyncio.gather(t1, t2, return_exceptions=True)
    assert exec_count["n"] == 1
    _assert_race_outcomes_never_clobber(results)
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "succeeded"


async def test_consumed_claim_id_replay_does_not_reexecute(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-013: after settle, a third claim with a new claim id still does not exec."""
    tool_call_id = "cal_consumed"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )
    exec_count = {"n": 0}
    real = TOOL_REGISTRY["calendar_create_event"].executor

    async def _counting(call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        return await real(call)

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_counting,
            prod_safe=original.prod_safe,
        ),
    )

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        first = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-1",
        )
    assert first.status == "succeeded"
    assert exec_count["n"] == 1

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        third = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-fresh-nonce",
        )
    assert exec_count["n"] == 1
    assert third.status == "succeeded"
    assert third.output == first.output


async def test_settle_cas_failure_does_not_report_success(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settle CAS loss must not return a succeeded result as durable."""
    tool_call_id = "cal_settle_cas"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    real_cas = approval_settlement._cas_persist_parts
    claim_writes = {"n": 0}

    async def _cas_fail_settle(
        db: Any,
        *,
        message_id: Any,
        parts: list[Any],
        expected_version: int,
    ) -> bool:
        # Let the claim write succeed; fail subsequent settle writes.
        has_result = any(
            isinstance(p, dict) and p.get("type") == "tool_result" for p in parts
        )
        if has_result:
            await db.rollback()
            return False
        claim_writes["n"] += 1
        return await real_cas(
            db,
            message_id=message_id,
            parts=parts,
            expected_version=expected_version,
        )

    monkeypatch.setattr(approval_settlement, "_cas_persist_parts", _cas_fail_settle)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        result = await claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-settle-fail",
        )

    assert claim_writes["n"] == 1
    assert result.status == "failed"
    assert "no settled result" in (result.error or "").lower()

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        parts = list(row.parts or [])
        assert not any(
            isinstance(p, dict) and p.get("type") == "tool_result" for p in parts
        )


async def test_pseudo_tool_claim_cas_loss_does_not_stale_overwrite(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pseudo-tool claim CAS loss re-reads; never unconditionally overwrites."""
    from app.tools.approval_settlement import ApprovalSettlementIncomplete

    tool_call_id = "plan_clarify_1"
    parts = [
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": "agentic_plan_clarify",
            "label": "Clarify plan",
            "status": "awaiting_approval",
            "approvalState": "pending",
            "input": {"questions": ["Scope?"]},
        }
    ]
    msg = await _seed_paused_message(session_factory, parts=parts)
    baseline_version = int(msg.parts_version or 0)

    async def _cas_always_lose(
        db: Any,
        *,
        message_id: Any,
        parts: list[Any],
        expected_version: int,
    ) -> bool:
        await db.rollback()
        return False

    monkeypatch.setattr(approval_settlement, "_cas_persist_parts", _cas_always_lose)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        with pytest.raises(ApprovalSettlementIncomplete):
            await settle_pseudo_tool_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                output={"answers": ["narrow"]},
                claim_id="claim-loser",
            )

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        call = next(p for p in (row.parts or []) if p.get("type") == "tool_call")
        # Loser must not have force-written its claim onto the row.
        assert call.get("approvalState") == "pending"
        assert APPROVAL_CLAIM_ID_KEY not in call
        assert int(row.parts_version or 0) == baseline_version
        assert not any(
            isinstance(p, dict) and p.get("type") == "tool_result" for p in (row.parts or [])
        )


async def test_pseudo_tool_settle_cas_loss_raises_incomplete(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settle CAS loss with no durable result must not return a resume-ready result."""
    from app.tools.approval_settlement import (
        ApprovalSettlementIncomplete,
        settle_pseudo_tool_approval_outcome,
    )

    tool_call_id = "plan_clarify_settle_fail"
    parts = [
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": "agentic_plan_clarify",
            "label": "Clarify plan",
            "status": "awaiting_approval",
            "approvalState": "pending",
            "input": {"questions": ["Scope?"]},
        }
    ]
    msg = await _seed_paused_message(session_factory, parts=parts)
    real_cas = approval_settlement._cas_persist_parts
    claim_writes = {"n": 0}

    async def _cas_fail_settle(
        db: Any,
        *,
        message_id: Any,
        parts: list[Any],
        expected_version: int,
    ) -> bool:
        has_result = any(
            isinstance(p, dict) and p.get("type") == "tool_result" for p in parts
        )
        if has_result:
            await db.rollback()
            return False
        claim_writes["n"] += 1
        return await real_cas(
            db,
            message_id=message_id,
            parts=parts,
            expected_version=expected_version,
        )

    monkeypatch.setattr(approval_settlement, "_cas_persist_parts", _cas_fail_settle)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        with pytest.raises(ApprovalSettlementIncomplete):
            await settle_pseudo_tool_approval_outcome(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                output={"decision": "approve"},
                claim_id="claim-settle-fail",
            )

    assert claim_writes["n"] == 1
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        assert not any(
            isinstance(p, dict) and p.get("type") == "tool_result" for p in (row.parts or [])
        )


async def test_pseudo_tool_opposite_decision_after_settle_conflicts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Durable settle decision is authoritative; opposite retry conflicts."""
    from app.tools.approval_settlement import (
        ApprovalDecisionConflict,
        settle_pseudo_tool_approval_outcome,
    )

    tool_call_id = "plan_approval_conflict"
    parts = [
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": "agentic_plan_approval",
            "label": "Approve plan",
            "status": "awaiting_approval",
            "approvalState": "pending",
            "input": {"plan": ["a", "b"]},
        }
    ]
    msg = await _seed_paused_message(session_factory, parts=parts)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        first = await settle_pseudo_tool_approval_outcome(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="deny",
            output={"decision": "deny"},
        )
    assert first.decision == "deny"
    assert first.result.status == "cancelled"

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        with pytest.raises(ApprovalDecisionConflict):
            await settle_pseudo_tool_approval_outcome(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                output={"decision": "approve"},
            )


def _pending_plan_parts(*, tool_call_id: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": "agentic_plan_approval",
            "label": "Approve plan",
            "status": "awaiting_approval",
            "approvalState": "pending",
            "input": {"plan": ["a", "b"]},
        }
    ]


async def test_pseudo_tool_same_decision_retry_adopts_an_orphaned_claim(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-29: a crash between pseudo-tool claim and settle must not strand the card.

    Proves the straight-line exit: the first attempt commits the claim and then
    dies before settling, and the same-decision retry adopts the row's own claim
    and reaches a durable ``tool_result`` instead of raising
    ``APPROVAL_SETTLEMENT_INCOMPLETE`` forever. An opposite-decision retry still
    conflicts, so adoption never launders a contradictory decision.
    """
    from app.tools.approval_settlement import (
        ApprovalDecisionConflict,
        settle_pseudo_tool_approval_outcome,
    )

    tool_call_id = "plan_approval_orphan"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_plan_parts(tool_call_id=tool_call_id)
    )

    async def _crash_after_claim(_db: Any, **_kwargs: Any) -> bool:
        raise RuntimeError("simulated crash between claim and settle")

    monkeypatch.setattr(
        approval_settlement, "_settle_under_claim", _crash_after_claim
    )
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        with pytest.raises(RuntimeError):
            await settle_pseudo_tool_approval_outcome(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                output={"decision": "approve"},
                claim_id="claim-orphaned",
            )

    # The claim is committed and terminal, but nothing settled it.
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        call = approval_settlement.find_tool_call_part(row.parts, tool_call_id)
        assert call is not None
        assert call.get("approvalState") == "approved"
        assert call.get(APPROVAL_CLAIM_ID_KEY) == "claim-orphaned"
        assert (
            approval_settlement.find_settled_tool_result(row.parts, tool_call_id)
            is None
        )

    monkeypatch.undo()
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        retry = await settle_pseudo_tool_approval_outcome(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            output={"decision": "approve"},
        )
    assert retry.decision == "approve"
    assert retry.result.status == "succeeded"
    # Adopted the orphaned claim rather than minting a new one.
    assert retry.claim_id == "claim-orphaned"

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        settled = approval_settlement.find_settled_tool_result(row.parts, tool_call_id)
        assert settled is not None
        assert settled.get("status") == "succeeded"
        with pytest.raises(ApprovalDecisionConflict):
            await settle_pseudo_tool_approval_outcome(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="deny",
                output={"decision": "deny"},
            )


async def test_pseudo_tool_claim_cas_loser_adopts_the_winners_claim(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-29: the claim-CAS-loss exit adopts too, so no live window strands.

    Two same-decision resumes race the pending→claimed CAS with the in-process
    lock bypassed; the settle of whichever wins is held open. Fixing only the
    straight-line exit would leave the loser raising incomplete against a claim
    that is about to settle.
    """
    from app.tools.approval_settlement import settle_pseudo_tool_approval_outcome

    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "plan_approval_cas_orphan"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_plan_parts(tool_call_id=tool_call_id)
    )

    real_settle = approval_settlement._settle_under_claim
    settle_calls = {"n": 0}
    first_entered = asyncio.Event()
    release = asyncio.Event()

    async def _gated_settle(db: Any, **kwargs: Any) -> bool:
        settle_calls["n"] += 1
        if settle_calls["n"] == 1:
            first_entered.set()
            await release.wait()
        return await real_settle(db, **kwargs)

    monkeypatch.setattr(approval_settlement, "_settle_under_claim", _gated_settle)

    both_ready = asyncio.Event()
    ready = {"n": 0}

    async def _approve(claim: str) -> Any:
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            ready["n"] += 1
            if ready["n"] >= 2:
                both_ready.set()
            await both_ready.wait()
            return await settle_pseudo_tool_approval_outcome(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                output={"decision": "approve"},
                claim_id=claim,
            )

    t1 = asyncio.create_task(_approve("claim-race-a"))
    t2 = asyncio.create_task(_approve("claim-race-b"))
    await asyncio.wait_for(first_entered.wait(), timeout=5.0)
    release.set()
    outcomes = await asyncio.gather(t1, t2)

    # Neither resume is stranded and the row carries exactly one settlement.
    assert all(o.result.status == "succeeded" for o in outcomes)
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        results = [
            p
            for p in (row.parts or [])
            if isinstance(p, dict) and p.get("type") == "tool_result"
        ]
        assert len(results) == 1


async def test_claimed_without_result_persists_a_terminal_failure(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-31: a claimed-but-unsettled registry approval becomes terminal on the row.

    The safety half of BE-007 was already met — the executor never runs — but the
    row stayed ``approved`` / ``running`` with no ``tool_result``, so refetch kept
    rendering the card as in flight and no retry could resolve it. Asserts the
    persisted ``failed`` result plus the explicit zero-execution guarantee.
    """
    from app.tools.approval_settlement import claim_and_settle_approval_outcome

    tool_call_id = "cal_terminal_failure"
    parts = _pending_calendar_parts(tool_call_id=tool_call_id)
    parts[0]["approvalState"] = "approved"
    parts[0]["status"] = "running"
    parts[0][APPROVAL_CLAIM_ID_KEY] = "claim-crashed"
    msg = await _seed_paused_message(session_factory, parts=parts)

    exec_count = {"n": 0}

    async def _boom(_call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        raise AssertionError("fail-closed must not re-run the side effect")

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_boom,
            prod_safe=original.prod_safe,
        ),
    )

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        outcome = await claim_and_settle_approval_outcome(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
        )

    assert exec_count["n"] == 0
    assert outcome.result.status == "failed"

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        settled = approval_settlement.find_settled_tool_result(row.parts, tool_call_id)
        assert settled is not None
        assert settled.get("status") == "failed"
        call = approval_settlement.find_tool_call_part(row.parts, tool_call_id)
        assert call is not None
        # The card no longer renders approved/running on refetch.
        assert call.get("status") == "failed"


async def test_deny_race_defers_the_retry_to_the_live_claim(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W1: the deny path claims and settles too, so it needs the same guard.

    Deny never calls ``execute_tool``, but it still commits a
    ``rejected``/``cancelled`` claim and only then settles, so a retry landing in
    that window reads the same crashed-claim shape and would write a ``failed``
    ``tool_result`` over the winner's ``cancelled`` one. The window is short
    enough that the in-process claim lock hides it within a single process, so
    this test bypasses that lock — which is exactly the cross-process shape the
    registry is there to cover — and parks the winner inside ``_settle_under_claim``.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "cal_deny_race"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    real_settle = approval_settlement._settle_under_claim
    settle_entered = asyncio.Event()
    release = asyncio.Event()
    settle_calls = {"n": 0}

    async def _gated_settle(db: Any, **kwargs: Any) -> bool:
        settle_calls["n"] += 1
        if settle_calls["n"] == 1:
            settle_entered.set()
            await release.wait()
        return await real_settle(db, **kwargs)

    monkeypatch.setattr(approval_settlement, "_settle_under_claim", _gated_settle)

    async def _deny(claim: str) -> ToolExecutionResult:
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            return await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="deny",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
                claim_id=claim,
            )

    winner_task = asyncio.create_task(_deny("claim-deny-winner"))
    await asyncio.wait_for(settle_entered.wait(), timeout=5.0)
    assert await _durable_tool_result(session_factory, msg.id, tool_call_id) is None

    with pytest.raises(ApprovalSettlementIncomplete) as raised:
        await _deny("claim-deny-retry")
    assert raised.value.tool_call_id == tool_call_id
    assert await _durable_tool_result(session_factory, msg.id, tool_call_id) is None

    release.set()
    winner = await winner_task
    assert winner.status == "cancelled"

    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "cancelled"
    assert settled.get("approvalState") == "rejected"


async def test_crash_recovery_terminalizes_when_no_claim_is_live(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W1 must not regress FL-31: an empty registry still recovers a dead claim.

    A restarted process has no live-claim entries, which is the registry's
    designed false negative: the retry falls straight through to the FL-31
    recovery write and the stranded ``approved``/``running`` card becomes
    terminal, exactly as before.
    """
    monkeypatch.setattr(approval_settlement, "_live_claims", {})
    tool_call_id = "cal_crash_recovery"
    parts = _pending_calendar_parts(tool_call_id=tool_call_id)
    parts[0]["approvalState"] = "approved"
    parts[0]["status"] = "running"
    parts[0][APPROVAL_CLAIM_ID_KEY] = "claim-from-dead-process"
    msg = await _seed_paused_message(session_factory, parts=parts)

    exec_count = {"n": 0}

    async def _boom(_call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        raise AssertionError("crash recovery must not re-run the side effect")

    original = TOOL_REGISTRY["calendar_create_event"]
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "calendar_create_event",
        ToolSpec(
            name=original.name,
            label=original.label,
            needs_approval=True,
            schema=original.schema,
            executor=_boom,
            prod_safe=original.prod_safe,
        ),
    )

    assert approval_settlement._live_claims == {}
    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        outcome = await claim_and_settle_approval_outcome(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
        )

    assert exec_count["n"] == 0
    assert outcome.result.status == "failed"
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "failed"


async def test_self_recovery_writes_under_its_own_live_claim(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W1 ownership is explicit: the winner may recover its own live claim.

    Suppression keys on *foreign* liveness. The FL-31 self-recovery inside
    ``claim_and_settle_approval_outcome`` runs while this invocation's own claim
    is still registered — the ``finally`` has not fired yet — so it must be
    allowed through, which is why ownership travels in
    ``_persist_claimed_without_result``'s signature instead of being inferred
    from call order.
    """
    tool_call_id = "cal_self_recovery"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    real_settle = approval_settlement._settle_under_claim
    settle_calls = {"n": 0}
    live_at_recovery: dict[str, Any] = {}

    async def _fail_first_settle(db: Any, **kwargs: Any) -> bool:
        settle_calls["n"] += 1
        if settle_calls["n"] == 1:
            return False
        live_at_recovery["claim"] = approval_settlement._live_claims.get(
            (str(msg.id), tool_call_id)
        )
        return await real_settle(db, **kwargs)

    monkeypatch.setattr(approval_settlement, "_settle_under_claim", _fail_first_settle)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        outcome = await claim_and_settle_approval_outcome(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision="approve",
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id="claim-self-recover",
        )

    assert settle_calls["n"] == 2
    # The recovery write happened while our own claim was still registered.
    assert live_at_recovery["claim"] == "claim-self-recover"
    assert outcome.result.status == "failed"
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "failed"
    # Liveness is scoped to the invocation, so nothing leaks past its finally.
    assert (str(msg.id), tool_call_id) not in approval_settlement._live_claims


async def test_bypass_claim_locks_race_defers_loser_to_live_winner(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W1: the version CAS and the liveness registry are independent gates.

    ``_bypass_claim_locks`` exists to prove the ``parts_version`` CAS carries
    correctness with no in-process help, so it must not switch off the registry,
    which answers a different question — is this claim in flight *here*? Both
    racers hit the pending→claimed CAS with the lock bypassed and the winner
    parks inside execute, so the loser cannot find a settled result to replay:
    under the old code it wrote a failure over the running side effect.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "cal_bypass_live"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    entered = asyncio.Event()
    release = asyncio.Event()
    _gated_calendar_spec(
        monkeypatch, exec_count=exec_count, entered=entered, release=release
    )

    both_ready = asyncio.Event()
    ready = {"n": 0}

    async def _approve(claim: str) -> ToolExecutionResult:
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            ready["n"] += 1
            if ready["n"] >= 2:
                both_ready.set()
            await both_ready.wait()
            return await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
                claim_id=claim,
            )

    t1 = asyncio.create_task(_approve("claim-bypass-a"))
    t2 = asyncio.create_task(_approve("claim-bypass-b"))
    await asyncio.wait_for(entered.wait(), timeout=5.0)
    assert await _durable_tool_result(session_factory, msg.id, tool_call_id) is None

    release.set()
    results = await asyncio.gather(t1, t2, return_exceptions=True)

    assert exec_count["n"] == 1
    _assert_race_outcomes_never_clobber(results)
    deferred = [r for r in results if isinstance(r, ApprovalSettlementIncomplete)]
    assert len(deferred) == 1, f"loser did not defer to the live winner: {results!r}"
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "succeeded"


async def test_claim_locks_do_not_grow_unbounded_across_settlements(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B19: idle in-process claim locks are pruned after terminal settlement."""
    # Ensure we exercise the shared map (not the bypass path used by race tests).
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", False)
    approval_settlement._claim_locks.clear()

    for i in range(40):
        tool_call_id = f"cal_lock_{i}"
        msg = await _seed_paused_message(
            session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
        )
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="deny",
                effective_input={"title": "x"},
                label=None,
            )

    # After each settlement the idle lock entry is dropped — map stays tiny.
    assert len(approval_settlement._claim_locks) == 0
