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
    claim_and_settle_approval,
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
    """Two overlapping approve calls: only the CAS winner runs the executor."""
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
    # First claim committed and is inside execute; second must not re-run.
    second = await _approve("claim-second")
    release.set()
    first = await first_task

    assert exec_count["n"] == 1
    assert first.status == "succeeded"
    assert second.status == "failed"
    assert "refusing to re-execute" in (second.error or "")
