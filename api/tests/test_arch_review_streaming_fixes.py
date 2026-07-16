"""Tests for arch-review streaming / budget fixes (B7, B9, B10, B11, B15, B23)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, PlatformBudgetReservation, Stream, User
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.providers.protocol import ToolResult
from app.streaming import replay_registry
from app.streaming.handler import (
    _PROVIDER_QUEUE_MAXSIZE,
    _SubagentAccumulator,
    mark_unfinished_subagents_paused,
    tool_results_from_message_parts,
)
from app.streaming.reaper import reap_once, stream_orphaned_envelope


async def _seed_user_and_stream(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        stream = Stream(conversation_id=convo.id, status="active")
        session.add(stream)
        await session.commit()
        await session.refresh(stream)
        return user.id, stream.id


def test_tool_results_from_message_parts_collects_same_round() -> None:
    parts = [
        {"type": "tool_call", "id": "a", "name": "web_search"},
        {
            "type": "tool_result",
            "toolCallId": "a",
            "name": "web_search",
            "status": "succeeded",
            "approvalState": "not_required",
            "output": {"ok": True},
        },
        {
            "type": "tool_call",
            "id": "b",
            "name": "gated",
            "status": "awaiting_approval",
        },
        {
            "type": "tool_result",
            "toolCallId": "b",
            "name": "gated",
            "status": "succeeded",
            "approvalState": "approved",
            "summary": "done",
        },
    ]
    results = tool_results_from_message_parts(parts)
    assert [r.tool_call_id for r in results] == ["a", "b"]
    assert results[0].output == {"ok": True}
    assert isinstance(results[0], ToolResult)


def test_provider_queue_bound_is_documented() -> None:
    assert _PROVIDER_QUEUE_MAXSIZE == 256


def test_mark_unfinished_subagents_paused_sets_non_success() -> None:
    subagents = {
        "primary": _SubagentAccumulator(label="Primary", role="primary"),
        "done": _SubagentAccumulator(label="Done", role="worker"),
    }
    subagents["done"].terminal = True
    subagents["done"].outcome = "succeeded"
    mark_unfinished_subagents_paused(subagents)
    assert subagents["primary"].outcome == "stopped"
    assert subagents["done"].outcome == "succeeded"


async def test_reserve_and_release_platform_budget(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, stream_id = await _seed_user_and_stream(session_factory)
    async with session_factory() as session:
        ok = await usage_repo.reserve_platform_budget(
            session,
            user_id=user_id,
            stream_id=stream_id,
            amount_usd=1.5,
            monthly_quota_usd=10.0,
        )
        await session.commit()
        assert ok is True
        remaining = await usage_repo.get_platform_remaining_usd(
            session, user_id=user_id, monthly_quota_usd=10.0
        )
        assert remaining == pytest.approx(8.5)
        await usage_repo.release_platform_budget(session, stream_id=stream_id)
        await session.commit()
        remaining2 = await usage_repo.get_platform_remaining_usd(
            session, user_id=user_id, monthly_quota_usd=10.0
        )
        assert remaining2 == pytest.approx(10.0)


async def test_reserve_rejects_when_headroom_insufficient(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, stream_a = await _seed_user_and_stream(session_factory)
    _, stream_b = await _seed_user_and_stream(session_factory)
    # Re-bind stream_b to the same user for concurrent-hold simulation.
    async with session_factory() as session:
        row_b = (
            await session.execute(select(Stream).where(Stream.id == stream_b))
        ).scalar_one()
        convo_b = (
            await session.execute(
                select(Conversation).where(Conversation.id == row_b.conversation_id)
            )
        ).scalar_one()
        convo_b.user_id = user_id
        await session.commit()

    async with session_factory() as session:
        assert await usage_repo.reserve_platform_budget(
            session,
            user_id=user_id,
            stream_id=stream_a,
            amount_usd=7.0,
            monthly_quota_usd=10.0,
        )
        await session.commit()
        assert (
            await usage_repo.reserve_platform_budget(
                session,
                user_id=user_id,
                stream_id=stream_b,
                amount_usd=4.0,
                monthly_quota_usd=10.0,
            )
            is False
        )


async def test_heartbeat_bumps_active_stream(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _user_id, stream_id = await _seed_user_and_stream(session_factory)
    async with session_factory() as session:
        row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        row.updated_at = datetime.now(UTC) - timedelta(minutes=5)
        await session.commit()
        before = row.updated_at
        if before.tzinfo is None:
            before = before.replace(tzinfo=UTC)

    async with session_factory() as session:
        touched = await streams_repo.heartbeat(session, stream_id=stream_id)
        await session.commit()
        assert touched is True
        row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        after = row.updated_at
        if after.tzinfo is None:
            after = after.replace(tzinfo=UTC)
        assert after > before


async def test_reaper_terminalizes_replay_buffer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _user_id, stream_id = await _seed_user_and_stream(session_factory)
    async with session_factory() as session:
        row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        row.updated_at = datetime.now(UTC) - timedelta(hours=1)
        session.add(
            PlatformBudgetReservation(
                user_id=_user_id, stream_id=stream_id, amount_usd=1.0
            )
        )
        await session.commit()

    buffer = await replay_registry.create_async(stream_id, ttl_seconds=60.0)
    assert buffer.done is False

    reaped = await reap_once(session_factory, older_than=timedelta(minutes=15))
    assert reaped == 1
    assert buffer.done is True
    assert buffer.terminal_kind == "error"
    assert stream_orphaned_envelope().code == "STREAM_ORPHANED"

    async with session_factory() as session:
        holds = (
            await session.execute(
                select(PlatformBudgetReservation).where(
                    PlatformBudgetReservation.stream_id == stream_id
                )
            )
        ).scalars().all()
        assert holds == []
