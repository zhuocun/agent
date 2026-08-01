"""Unit tests for BE-007 claim/settle CAS and AC-01 fail-closed foreign claims."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.db.models import Conversation, Message, User
from app.tools import approval_settlement, builtin
from app.tools.approval_settlement import (
    APPROVAL_CLAIM_ID_KEY,
    ApprovalDecisionConflict,
    ApprovalSettlementIncomplete,
    _replace_tool_call,
    claim_and_settle_approval,
    claim_and_settle_approval_outcome,
    load_paused_assistant_for_resume,
    settle_pseudo_tool_approval,
    settle_pseudo_tool_approval_outcome,
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


async def _durable_snapshot(
    session_factory: async_sessionmaker[AsyncSession], message_id: Any
) -> tuple[int, list[Any]]:
    """``(parts_version, parts)`` from a fresh session — the durable truth."""
    async with session_factory() as session:
        row = await session.get(Message, message_id)
        assert row is not None
        await session.refresh(row)
        return int(row.parts_version or 0), deepcopy(list(row.parts or []))


def _durable_tool_results(parts: list[Any], tool_call_id: str) -> list[dict[str, Any]]:
    return [
        p
        for p in parts
        if isinstance(p, dict)
        and p.get("type") == "tool_result"
        and p.get("toolCallId") == tool_call_id
    ]


@asynccontextmanager
async def _second_service_instance(
    db_path: Path,
) -> AsyncIterator[tuple[Any, async_sessionmaker[AsyncSession]]]:
    """A second service instance: its own engine **and** its own module globals.

    Two things separate instance B from the fixture's instance A. Its engine is a
    second connection pool and identity map over the same database file, so the
    only thing they share is durable state. Its settlement module is a private
    copy loaded from the same spec and never registered in ``sys.modules``, so B
    holds none of A's in-memory state.

    The second half is what makes these tests falsifiable. The deleted design
    decided whether a claim was recoverable by consulting a process-local map, so
    a second engine alone would have shared that map and hidden the very bug
    AC-01 is about. Yields ``(settlement_module, session_factory)``; B's
    exception classes are its own objects, so callers raise-match on
    ``module.ApprovalSettlementIncomplete``.
    """
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    spec = importlib.util.find_spec("app.tools.approval_settlement")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Instance B coordinates with A only through the database.
    module._bypass_claim_locks = True
    try:
        yield module, async_sessionmaker(
            bind=engine, expire_on_commit=False, autoflush=False
        )
    finally:
        await engine.dispose()


async def _approve_from(
    factory: async_sessionmaker[AsyncSession],
    *,
    message_id: Any,
    tool_call_id: str,
    claim_id: str | None = None,
    decision: str = "approve",
    settlement: Any = approval_settlement,
) -> ToolExecutionResult:
    """Run one claim/settle attempt on ``factory``, via ``settlement``'s module."""
    async with factory() as session:
        row = await session.get(Message, message_id)
        assert row is not None
        result: ToolExecutionResult = await settlement.claim_and_settle_approval(
            session,
            paused_message=row,
            tool_call_id=tool_call_id,
            decision=decision,
            effective_input={"title": "Planning review"},
            label="Create calendar event",
            claim_id=claim_id,
        )
        return result


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


def _no_execute_calendar_spec(
    monkeypatch: pytest.MonkeyPatch, *, exec_count: dict[str, int]
) -> None:
    """Swap in a calendar executor that fails the test if it is ever called."""
    original = TOOL_REGISTRY["calendar_create_event"]

    async def _boom(_call: ToolCallRequest) -> ToolExecutionResult:
        exec_count["n"] += 1
        raise AssertionError("fail-closed must not re-run the side effect")

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


async def test_foreign_claimed_without_result_always_fails_closed(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: a claim this invocation does not own neither executes nor writes.

    The seeded row is what every unsettled claim looks like from the outside:
    ``approved`` / ``running`` / a claim id / no ``tool_result``. Nothing readable
    from here says whether the claiming machine is still running the side effect,
    so the only safe answer is ``ApprovalSettlementIncomplete`` with the row left
    untouched. This test previously asserted a ``failed`` replay was *returned*,
    and its FL-31 sibling asserted that failure was *written* — both are gone,
    because either one can overwrite a side effect that is still in flight.
    """
    tool_call_id = "cal_claimed"
    parts = _pending_calendar_parts(tool_call_id=tool_call_id)
    parts[0]["approvalState"] = "approved"
    parts[0]["status"] = "running"
    parts[0][APPROVAL_CLAIM_ID_KEY] = "claim-prior"
    msg = await _seed_paused_message(session_factory, parts=parts)
    baseline = await _durable_snapshot(session_factory, msg.id)

    exec_count = {"n": 0}
    _no_execute_calendar_spec(monkeypatch, exec_count=exec_count)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        with pytest.raises(ApprovalSettlementIncomplete) as raised:
            await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision="approve",
                effective_input={"title": "Planning review"},
                label="Create calendar event",
            )
    assert raised.value.tool_call_id == tool_call_id
    assert exec_count["n"] == 0
    assert await _durable_snapshot(session_factory, msg.id) == baseline


@pytest.mark.parametrize(
    ("claimed_approval", "claimed_status", "decision"),
    [
        ("approved", "running", "approve"),
        ("approved", "running", "deny"),
        ("rejected", "cancelled", "deny"),
        ("rejected", "cancelled", "approve"),
    ],
)
async def test_foreign_claim_is_incomplete_for_either_decision(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    claimed_approval: str,
    claimed_status: str,
    decision: str,
) -> None:
    """AC-01: the requested decision cannot change a foreign claim's answer.

    Every combination of what the row records and what this request asks for
    lands on ``ApprovalSettlementIncomplete``. The opposite-decision rows are the
    point: an earlier revision reported ``ApprovalDecisionConflict`` for those,
    which asserts a durable decision the caller cannot actually see. A claim
    without a ``tool_result`` records a *provisional* decision — its owner may
    still settle succeeded, failed, or cancelled — so reading it as settled truth
    is exactly the inference AC-01 removes, and it would hand a foreign caller a
    branch that varies with someone else's in-flight side effect.
    ``ApprovalDecisionConflict`` is reserved for a settled result (H-006), proven
    separately by ``test_settled_decision_conflict_raises``.
    """
    tool_call_id = f"cal_foreign_{claimed_approval}_{decision}"
    parts = _pending_calendar_parts(tool_call_id=tool_call_id)
    parts[0]["approvalState"] = claimed_approval
    parts[0]["status"] = claimed_status
    parts[0][APPROVAL_CLAIM_ID_KEY] = "claim-prior"
    msg = await _seed_paused_message(session_factory, parts=parts)
    baseline = await _durable_snapshot(session_factory, msg.id)

    exec_count = {"n": 0}
    _no_execute_calendar_spec(monkeypatch, exec_count=exec_count)

    async with session_factory() as session:
        row = await session.get(Message, msg.id)
        assert row is not None
        # ApprovalDecisionConflict is not a subclass, so this also asserts the
        # conflict branch is gone from the registry path.
        with pytest.raises(ApprovalSettlementIncomplete) as raised:
            await claim_and_settle_approval(
                session,
                paused_message=row,
                tool_call_id=tool_call_id,
                decision=decision,
                effective_input={"title": "Planning review"},
                label="Create calendar event",
            )
    assert raised.value.tool_call_id == tool_call_id
    assert exec_count["n"] == 0
    assert await _durable_snapshot(session_factory, msg.id) == baseline


async def test_registry_claim_path_has_no_decision_conflict_branch() -> None:
    """Static guard: only the pseudo-tool helper may raise Conflict on a claim.

    ``_raise_foreign_claim_incomplete`` takes no ``decision`` argument, so the
    registry exits cannot reintroduce a decision-dependent answer without this
    failing. Conflict remains reachable from settled-``tool_result`` comparisons
    and from the pseudo-tool helper, and nowhere else.
    """
    registry_exit = approval_settlement._raise_foreign_claim_incomplete
    # co_names, not the source, so the docstring's prose cannot satisfy this.
    assert "ApprovalDecisionConflict" not in registry_exit.__code__.co_names
    assert "decision" not in inspect.signature(registry_exit).parameters

    claim_source = inspect.getsource(approval_settlement._claim_pending_locked)
    assert "_raise_pseudo_incomplete_or_conflict" not in claim_source
    # The surviving Conflict raises in the registry claim path all sit behind a
    # durable settled result; none is on a claimed-without-result exit.
    conflict_sites = claim_source.split("raise ApprovalDecisionConflict")[:-1]
    assert conflict_sites, "expected the settled-result conflict checks to remain"
    for preceding in conflict_sites:
        assert "find_settled_tool_result" in preceding


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
    """AC-01: a retry inside the live execute window defers instead of clobbering.

    Execute deliberately runs outside the claim lock (H-007), so the row a
    concurrent retry reads mid-flight — ``approved`` / ``running`` / a claim id /
    no ``tool_result`` — is byte-for-byte what a crashed claim leaves behind.
    Since the retry does not own the claim it raises
    ``ApprovalSettlementIncomplete`` ("retry after the winning settlement
    commits", 409) and leaves the row untouched until the winner's real result
    lands.
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
    winner's settled result or, when nothing durable exists yet, defers with
    ``ApprovalSettlementIncomplete``. What it must never do is settle a ``failed``
    result on the winner's behalf, so the assertion is on the durable row rather
    than on which of the two branches the loser happened to take.
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

    The loser either replays a settlement that already landed or defers with
    ``ApprovalSettlementIncomplete``. Either branch keeps the single-execution
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
    conflicts, so adoption never launders a contradictory decision. Registry
    tools get no equivalent: adoption is safe here only because pseudo-tool
    settlement replays no external side effect (AC-01).
    """
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


async def test_two_instance_deny_race_fails_closed_for_the_retry(
    sqlite_db_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: the deny path claims and settles too, so it needs the same guard.

    Deny never calls ``execute_tool``, but it still commits a
    ``rejected``/``cancelled`` claim and only then settles, so a retry landing in
    that window reads the same crashed-claim shape and would write a ``failed``
    ``tool_result`` over the winner's ``cancelled`` one. The retry comes from a
    second service instance with the in-process lock bypassed, so only durable
    state is available to distinguish the two.
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

    async with _second_service_instance(sqlite_db_path) as (other, other_factory):
        winner_task = asyncio.create_task(
            _approve_from(
                session_factory,
                message_id=msg.id,
                tool_call_id=tool_call_id,
                claim_id="claim-deny-winner",
                decision="deny",
            )
        )
        await asyncio.wait_for(settle_entered.wait(), timeout=5.0)
        claimed = await _durable_snapshot(other_factory, msg.id)
        assert _durable_tool_results(claimed[1], tool_call_id) == []

        with pytest.raises(other.ApprovalSettlementIncomplete) as raised:
            await _approve_from(
                other_factory,
                message_id=msg.id,
                tool_call_id=tool_call_id,
                claim_id="claim-deny-retry",
                decision="deny",
                settlement=other,
            )
        assert raised.value.tool_call_id == tool_call_id
        assert await _durable_snapshot(other_factory, msg.id) == claimed

        release.set()
        winner = await winner_task

    assert winner.status == "cancelled"
    version, parts = await _durable_snapshot(session_factory, msg.id)
    results = _durable_tool_results(parts, tool_call_id)
    assert len(results) == 1
    assert version == claimed[0] + 1
    assert results[0].get("status") == winner.status
    assert results[0].get("approvalState") == "rejected"


async def test_restart_does_not_authorize_recovery_of_an_orphaned_claim(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01 replaces FL-31 registry-tool recovery: a restart recovers nothing.

    A restarted process has no in-memory state at all — which used to be read as
    proof the claiming process died, licensing a ``failed`` recovery write. It is
    no such proof: the row looks identical whether the claimant died or is another
    machine mid-side-effect, so the write is a coin flip on real user data. The
    claim now stays outstanding until its owner settles it, and terminalizing a
    genuinely orphaned one is deferred to executor idempotency/fencing or an
    explicit administrative operation.
    """
    tool_call_id = "cal_orphan_after_restart"
    parts = _pending_calendar_parts(tool_call_id=tool_call_id)
    parts[0]["approvalState"] = "approved"
    parts[0]["status"] = "running"
    parts[0][APPROVAL_CLAIM_ID_KEY] = "claim-from-dead-process"
    msg = await _seed_paused_message(session_factory, parts=parts)
    baseline = await _durable_snapshot(session_factory, msg.id)

    exec_count = {"n": 0}
    _no_execute_calendar_spec(monkeypatch, exec_count=exec_count)

    # Nothing process-local survives a restart, so clear what there is.
    approval_settlement._claim_locks.clear()
    for attempt in range(3):
        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            with pytest.raises(ApprovalSettlementIncomplete):
                await claim_and_settle_approval_outcome(
                    session,
                    paused_message=row,
                    tool_call_id=tool_call_id,
                    decision="approve",
                    effective_input={"title": "Planning review"},
                    label="Create calendar event",
                )
        assert exec_count["n"] == 0
        assert await _durable_snapshot(session_factory, msg.id) == baseline, (
            f"attempt {attempt} mutated the row"
        )


async def test_no_process_local_liveness_or_expiry_branch_remains() -> None:
    """AC-01 static guard: no liveness registry and no clock in the safety path.

    The deleted design inferred "the owner died" from an empty in-process map;
    the tempting replacement is a lease keyed on elapsed time. Both are the same
    mistake — neither observes the executor — so the module must reach for no
    process-local claim state and no clock at all. This fails loudly if either
    reappears.
    """
    source = inspect.getsource(approval_settlement)
    for banned in ("_live_claims", "_LiveClaimTicket", "_is_live_claim"):
        assert banned not in source, f"{banned} came back"
    for clock in (
        "import time",
        "time.monotonic",
        "time.time(",
        "datetime.now",
        "utcnow",
        "monotonic()",
    ):
        assert clock not in source, f"claim safety must not consult a clock: {clock}"


async def test_owner_recovers_only_its_own_claim_after_settle_cas_loss(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ownership is what authorizes the one remaining recovery write.

    The owner executed, then lost the settle CAS. It may still write the terminal
    failure because it writes under the claim id *it minted* — a settlement by the
    claim's owner, not recovery of someone else's. ``_settle_under_claim`` re-locks
    and matches that id, so the write is a no-op if the row has moved on.
    """
    tool_call_id = "cal_self_recovery"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    real_settle = approval_settlement._settle_under_claim
    settle_calls: list[str] = []

    async def _fail_first_settle(db: Any, **kwargs: Any) -> bool:
        settle_calls.append(str(kwargs["minted_claim"]))
        if len(settle_calls) == 1:
            return False
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

    # Both the real settle and the recovery write went out under our own claim.
    assert settle_calls == ["claim-self-recover", "claim-self-recover"]
    assert outcome.result.status == "failed"
    assert outcome.claim_id == "claim-self-recover"
    settled = await _durable_tool_result(session_factory, msg.id, tool_call_id)
    assert settled is not None
    assert settled.get("status") == "failed"


async def test_bypass_claim_locks_race_defers_loser_to_live_winner(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: with no in-process help at all, the loser still defers.

    ``_bypass_claim_locks`` exists to prove the ``parts_version`` CAS carries
    correctness on its own. Both racers hit the pending→claimed CAS with the lock
    bypassed and the winner parks inside execute, so the loser cannot find a
    settled result to replay: under the old code it wrote a failure over the
    running side effect.
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


async def test_two_instances_foreign_claim_fails_closed_and_winner_settles_once(
    sqlite_db_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01 closure: two service instances, exactly one durable settlement.

    Instance A claims and parks inside the side effect. Instance B is a second
    engine over the same database — its own pool and identity map, sharing no
    memory with A, which is what a second Fly machine sees — and the in-process
    claim lock is bypassed so nothing but durable state coordinates them. Every
    loser attempt, from either instance, raises ``ApprovalSettlementIncomplete``
    and leaves ``parts`` and ``parts_version`` byte-identical. Only once A is
    released does a ``tool_result`` appear: exactly one, equal to the result A
    returned to its own caller.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "cal_two_instance"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    entered = asyncio.Event()
    release = asyncio.Event()
    _gated_calendar_spec(
        monkeypatch, exec_count=exec_count, entered=entered, release=release
    )

    async with _second_service_instance(sqlite_db_path) as (other, other_factory):
        winner_task = asyncio.create_task(
            _approve_from(
                session_factory,
                message_id=msg.id,
                tool_call_id=tool_call_id,
                claim_id="claim-instance-a",
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=5.0)

        # Claim committed, side effect in flight: both instances read the very
        # shape a crashed claim leaves behind.
        claimed = await _durable_snapshot(other_factory, msg.id)
        assert _durable_tool_results(claimed[1], tool_call_id) == []
        assert await _durable_snapshot(session_factory, msg.id) == claimed

        # The third loser contradicts the winner's decision: that must read the
        # same as any other loser, not as a decision conflict.
        losers = (
            (other, other_factory, "approve"),
            (approval_settlement, session_factory, "approve"),
            (other, other_factory, "deny"),
        )
        for i, (module, loser_factory, loser_decision) in enumerate(losers):
            with pytest.raises(module.ApprovalSettlementIncomplete) as raised:
                await _approve_from(
                    loser_factory,
                    message_id=msg.id,
                    tool_call_id=tool_call_id,
                    claim_id=f"claim-loser-{i}",
                    decision=loser_decision,
                    settlement=module,
                )
            assert raised.value.tool_call_id == tool_call_id
            assert await _durable_snapshot(other_factory, msg.id) == claimed
            assert await _durable_snapshot(session_factory, msg.id) == claimed

        release.set()
        winner = await winner_task

    assert exec_count["n"] == 1
    assert winner.status == "succeeded"
    version, parts = await _durable_snapshot(session_factory, msg.id)
    results = _durable_tool_results(parts, tool_call_id)
    assert len(results) == 1
    # One write total, so no loser slipped a version bump past the assertions.
    assert version == claimed[0] + 1
    settled = results[0]
    assert settled.get("status") == winner.status
    assert settled.get("output") == winner.output
    assert settled.get("approvalState") == winner.approval_state
    assert settled.get("summary") == winner.summary


async def test_winner_held_past_the_tool_timeout_keeps_sole_ownership(
    sqlite_db_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: passing the only deadline the system enforces authorizes nothing.

    The per-tool timeout is that deadline, so this shrinks it to 50 ms and lets it
    fire: the gated executor never returns, ``execute_tool`` gives up, and the
    winner arrives at settlement holding a timed-out result. It then sits there
    while real time accrues past ten timeouts — where a lease-based recovery
    would have handed the row to someone else. The second instance keeps getting
    ``ApprovalSettlementIncomplete`` instead, and the winner's own result is the
    single durable settlement.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_timeout = 0.05
    monkeypatch.setattr(
        builtin,
        "get_settings",
        lambda: Settings(TOOL_TIMEOUT_SECONDS=tool_timeout),  # type: ignore[call-arg]
    )
    tool_call_id = "cal_past_timeout"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    entered = asyncio.Event()
    never_released = asyncio.Event()
    _gated_calendar_spec(
        monkeypatch, exec_count=exec_count, entered=entered, release=never_released
    )

    real_settle = approval_settlement._settle_under_claim
    settle_entered = asyncio.Event()
    release_settle = asyncio.Event()
    settle_calls = {"n": 0}

    async def _gated_settle(db: Any, **kwargs: Any) -> bool:
        settle_calls["n"] += 1
        if settle_calls["n"] == 1:
            settle_entered.set()
            await release_settle.wait()
        return await real_settle(db, **kwargs)

    monkeypatch.setattr(approval_settlement, "_settle_under_claim", _gated_settle)

    async with _second_service_instance(sqlite_db_path) as (other, other_factory):
        started = time.monotonic()
        winner_task = asyncio.create_task(
            _approve_from(
                session_factory,
                message_id=msg.id,
                tool_call_id=tool_call_id,
                claim_id="claim-slow-winner",
            )
        )
        await asyncio.wait_for(settle_entered.wait(), timeout=5.0)
        claimed = await _durable_snapshot(other_factory, msg.id)
        assert _durable_tool_results(claimed[1], tool_call_id) == []

        while time.monotonic() - started < tool_timeout * 10:
            await asyncio.sleep(tool_timeout)
        for i in range(2):
            with pytest.raises(other.ApprovalSettlementIncomplete):
                await _approve_from(
                    other_factory,
                    message_id=msg.id,
                    tool_call_id=tool_call_id,
                    claim_id=f"claim-late-loser-{i}",
                    settlement=other,
                )
            assert await _durable_snapshot(other_factory, msg.id) == claimed
        assert time.monotonic() - started > tool_timeout * 10

        release_settle.set()
        winner = await winner_task

    assert exec_count["n"] == 1
    assert winner.status == "failed"
    assert "timed out" in (winner.error or "").lower()
    version, parts = await _durable_snapshot(session_factory, msg.id)
    results = _durable_tool_results(parts, tool_call_id)
    assert len(results) == 1
    assert version == claimed[0] + 1
    assert results[0].get("status") == winner.status
    assert results[0].get("error") == winner.error


async def test_cancelled_winner_settles_its_own_claim_and_loser_fails_closed(
    sqlite_db_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H-007 under AC-01: cancellation is reported by the owner, not by a retry.

    Only the invocation that ran the side effect knows it was abandoned, so it
    settles ``cancelled`` under its own claim on the way out. A second instance
    racing that window still fails closed; afterwards the durable ``cancelled``
    result is what a retry replays, with no second execution.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "cal_cancelled_winner"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )

    exec_count = {"n": 0}
    entered = asyncio.Event()
    release = asyncio.Event()
    _gated_calendar_spec(
        monkeypatch, exec_count=exec_count, entered=entered, release=release
    )

    async with _second_service_instance(sqlite_db_path) as (other, other_factory):
        winner_task = asyncio.create_task(
            _approve_from(
                session_factory,
                message_id=msg.id,
                tool_call_id=tool_call_id,
                claim_id="claim-cancelled-winner",
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=5.0)
        claimed = await _durable_snapshot(other_factory, msg.id)

        with pytest.raises(other.ApprovalSettlementIncomplete):
            await _approve_from(
                other_factory,
                message_id=msg.id,
                tool_call_id=tool_call_id,
                claim_id="claim-cancel-window-loser",
                settlement=other,
            )
        assert await _durable_snapshot(other_factory, msg.id) == claimed

        winner_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await winner_task

        version, parts = await _durable_snapshot(other_factory, msg.id)
        results = _durable_tool_results(parts, tool_call_id)
        assert len(results) == 1
        assert results[0].get("status") == "cancelled"
        assert version == claimed[0] + 1

        replay = await _approve_from(
            other_factory,
            message_id=msg.id,
            tool_call_id=tool_call_id,
            claim_id="claim-after-cancel",
            settlement=other,
        )

    assert exec_count["n"] == 1
    assert replay.status == "cancelled"


async def test_claim_cas_loss_rereads_and_never_settles_for_the_winner(
    sqlite_db_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: a lost claim CAS re-reads durable state and stops there.

    That exit used to write a ``failed`` ``tool_result`` under the *winner's*
    claim id, settling on behalf of an invocation on another machine whose side
    effect had only just begun. The winner's claim lands here on the second
    instance's connection while this caller is mid-write, so the CAS loss is the
    real thing rather than an injected boolean.
    """
    monkeypatch.setattr(approval_settlement, "_bypass_claim_locks", True)
    tool_call_id = "cal_cas_loss_foreign"
    msg = await _seed_paused_message(
        session_factory, parts=_pending_calendar_parts(tool_call_id=tool_call_id)
    )
    baseline_version, baseline_parts = await _durable_snapshot(session_factory, msg.id)

    exec_count = {"n": 0}
    _no_execute_calendar_spec(monkeypatch, exec_count=exec_count)

    async with _second_service_instance(sqlite_db_path) as (_other, other_factory):
        real_cas = approval_settlement._cas_persist_parts

        async def _foreign_writer_wins(
            db: Any, *, message_id: Any, parts: list[Any], expected_version: int
        ) -> bool:
            foreign = deepcopy(baseline_parts)
            foreign[0]["approvalState"] = "approved"
            foreign[0]["status"] = "running"
            foreign[0][APPROVAL_CLAIM_ID_KEY] = "claim-foreign-winner"
            async with other_factory() as writer:
                won = await real_cas(
                    writer,
                    message_id=message_id,
                    parts=foreign,
                    expected_version=expected_version,
                )
            assert won, "the foreign winner should have taken the version"
            await db.rollback()
            return False

        monkeypatch.setattr(
            approval_settlement, "_cas_persist_parts", _foreign_writer_wins
        )

        async with session_factory() as session:
            row = await session.get(Message, msg.id)
            assert row is not None
            with pytest.raises(ApprovalSettlementIncomplete):
                await claim_and_settle_approval(
                    session,
                    paused_message=row,
                    tool_call_id=tool_call_id,
                    decision="approve",
                    effective_input={"title": "Planning review"},
                    label="Create calendar event",
                    claim_id="claim-cas-loser",
                )

    assert exec_count["n"] == 0
    version, parts = await _durable_snapshot(session_factory, msg.id)
    # Only the foreign winner wrote; the loser added neither a result nor a bump.
    assert version == baseline_version + 1
    call = approval_settlement.find_tool_call_part(parts, tool_call_id)
    assert call is not None
    assert call.get(APPROVAL_CLAIM_ID_KEY) == "claim-foreign-winner"
    assert _durable_tool_results(parts, tool_call_id) == []
