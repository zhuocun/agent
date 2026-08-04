"""Tests for arch-review streaming / budget fixes (B7, B9, B10, B11, B15, B23)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, PlatformBudgetReservation, Stream, User
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.providers.tiers import get_binding
from app.streaming import handler as handler_mod
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


def test_fanout_queue_bound_matches_provider_bound() -> None:
    from app.agentic.fanout import _FANOUT_QUEUE_MAXSIZE

    assert _FANOUT_QUEUE_MAXSIZE == 256
    assert _FANOUT_QUEUE_MAXSIZE == _PROVIDER_QUEUE_MAXSIZE


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


# AC-03: live vs stopped-drain ToolResult fold parity ---------------------------
#
# `stream_and_persist` used to fold provider events twice: inline while
# delivering, and again in a private `_apply_event` tree when a stop/disconnect
# drained whatever the pump already queued. The drain twin synced only `status`
# onto the open `tool_call` part, so a `pending` gate closed by a
# `cancelled`/`rejected` result persisted as `cancelled` + `pending` — a state
# the live fold can never produce. Both drivers now fold through
# `TurnReducer`; these tests pin them together for the tagged (per-subagent) and
# untagged (flat) tool transcripts.

_GATED_CALL_ID = "gated-call-1"


def _gated_call_and_rejection(subagent_id: str | None) -> list[ProviderEvent]:
    """A pending approval gate, then the sibling-cancel rejection that closes it."""
    return [
        ToolCall(
            id=_GATED_CALL_ID,
            name="calendar_create_event",
            label="Create event",
            status="awaiting_approval",
            approval_state="pending",
            subagent_id=subagent_id,
        ),
        ToolResult(
            tool_call_id=_GATED_CALL_ID,
            name="calendar_create_event",
            label="Create event",
            status="cancelled",
            approval_state="rejected",
            error="Cancelled alongside a rejected sibling call.",
            subagent_id=subagent_id,
        ),
    ]


class _NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectAfterFirstFrame:
    """First poll False, every later poll True — so all but event #1 is drained.

    The False poll parks the consumer on an empty queue, which hands control to
    the pump; the await-free stub stream lands in the queue in one go and only
    its first event is consumed live. The next poll cancels the pump with the
    rest still queued, which is exactly the stopped FIFO drain.
    """

    def __init__(self) -> None:
        self._polls = 0

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > 1


class _StubProvider:
    """Non-agentic provider that replays a canned event list."""

    def __init__(self, make_events: Callable[[], AsyncIterator[ProviderEvent]]) -> None:
        self._make_events = make_events

    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
        return self._make_events()


class _UnusedProvider:
    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
        raise AssertionError("the stubbed orchestrator replaces the provider")


@pytest.fixture
def settings_cache_reset() -> Iterator[None]:
    """Drop the cached `Settings` so per-test flag env lands, and again after."""
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


async def _persisted_parts_for_turn(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[ProviderEvent],
    agentic: bool,
    live: bool,
) -> list[dict[str, Any]]:
    """Drive one turn over `events` and return the persisted assistant parts.

    `live=True` appends a terminal `Complete` and never disconnects, so every
    event is folded by the inline delivery loop. `live=False` holds the stub
    stream open and disconnects after the first frame, so everything but event
    #1 is folded by the drain instead.

    `agentic=True` drives a stubbed orchestrator (tagged transcript, grouped by
    subagent); `agentic=False` keeps both flags off so the plain-chat path folds
    into the flat, untagged transcript.
    """
    monkeypatch.setenv("TOOLS_ENABLED", "true" if agentic else "false")
    monkeypatch.setenv("AGENTIC_ENABLED", "true" if agentic else "false")
    get_settings.cache_clear()

    binding = get_binding("smart")
    assert binding is not None

    tail: list[ProviderEvent] = list(events)
    if live:
        tail.append(Complete(usage=UsageUpdate(input_tokens=4, output_tokens=2)))

    def _make_events() -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            for ev in tail:
                yield ev
            if not live:
                # A drained turn must end on the disconnect, not on exhaustion.
                await asyncio.sleep(30)

        return _gen()

    provider: Any
    if agentic:
        monkeypatch.setattr(
            handler_mod,
            "run_orchestrator",
            lambda **_kwargs: _make_events(),
        )
        provider = _UnusedProvider()
    else:
        provider = _StubProvider(_make_events)

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id, title="ac03", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    request_stub: Any = _NeverDisconnected() if live else _DisconnectAfterFirstFrame()

    async with session_factory() as session:
        async for _frame in handler_mod.stream_and_persist(
            request=request_stub,
            db=session,
            provider=provider,
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="schedule a meeting",
            history=[],
            is_temporary=False,
            user_id=user_id,
            agentic_mode="deep_research" if agentic else None,
        ):
            pass

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        ).scalars().first()
    assert row is not None
    raw = row.parts if isinstance(row.parts, list) else []
    return [p for p in raw if isinstance(p, dict)]


def _tool_transcript(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in parts if p.get("type") in ("tool_call", "tool_result")]


def _assert_gate_settled_as_rejected(parts: list[dict[str, Any]]) -> None:
    transcript = _tool_transcript(parts)
    calls = [p for p in transcript if p.get("type") == "tool_call"]
    results = [p for p in transcript if p.get("type") == "tool_result"]
    assert len(calls) == 1, transcript
    assert len(results) == 1, transcript
    assert calls[0]["id"] == _GATED_CALL_ID
    assert calls[0]["status"] == "cancelled"
    # `cancelled` + `pending` is the split state this pins shut.
    assert calls[0]["approvalState"] == "rejected"
    assert results[0]["toolCallId"] == _GATED_CALL_ID
    assert results[0]["status"] == "cancelled"
    assert results[0]["approvalState"] == "rejected"


@pytest.mark.parametrize("live", [True, False], ids=["live", "drain"])
async def test_tagged_tool_result_syncs_approval_state(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    live: bool,
) -> None:
    """AC-03: a tagged `pending -> rejected` trace settles the same either way."""
    events: list[ProviderEvent] = [
        SubagentStarted(subagent_id="worker-0", label="Alpha", role="worker"),
        *_gated_call_and_rejection("worker-0"),
    ]
    parts = await _persisted_parts_for_turn(
        session_factory, monkeypatch, events=events, agentic=True, live=live
    )
    _assert_gate_settled_as_rejected(parts)


@pytest.mark.parametrize("live", [True, False], ids=["live", "drain"])
async def test_untagged_tool_result_syncs_approval_state(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    live: bool,
) -> None:
    """AC-03: same invariant for the flat, non-agentic tool transcript."""
    events: list[ProviderEvent] = [
        AnswerDelta(text="working on it"),
        *_gated_call_and_rejection(None),
    ]
    parts = await _persisted_parts_for_turn(
        session_factory, monkeypatch, events=events, agentic=False, live=live
    )
    _assert_gate_settled_as_rejected(parts)


@pytest.mark.parametrize("agentic", [True, False], ids=["tagged", "untagged"])
async def test_live_and_drain_tool_transcripts_are_identical(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    agentic: bool,
) -> None:
    """AC-03 parity: the two folds produce byte-identical tool transcripts."""
    events: list[ProviderEvent] = (
        [
            SubagentStarted(subagent_id="worker-0", label="Alpha", role="worker"),
            *_gated_call_and_rejection("worker-0"),
        ]
        if agentic
        else [AnswerDelta(text="working on it"), *_gated_call_and_rejection(None)]
    )
    live_parts = await _persisted_parts_for_turn(
        session_factory, monkeypatch, events=events, agentic=agentic, live=True
    )
    drain_parts = await _persisted_parts_for_turn(
        session_factory, monkeypatch, events=events, agentic=agentic, live=False
    )
    assert _tool_transcript(live_parts) == _tool_transcript(drain_parts)
    _assert_gate_settled_as_rejected(live_parts)
