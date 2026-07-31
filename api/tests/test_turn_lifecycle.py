"""AC-11 closure: one durable envelope for a turn's generator AND its sink.

`stream_and_persist` used to guard its own lifecycle with a `finally` the sink
could not see, which left two escapes:

1. Fallible setup after the `submitted` frame — approval settlement, the
   prior-row load, source resolution, pump creation, seeded execution — ran
   BEFORE that guard, so a failure there returned with the durable `stream` row
   still `active` and the platform-budget reservation still held.
2. `run_detached_producer`'s `buffer.append()` is the turn's real sink. It
   caught its own append failure and left the generator suspended at a `yield`,
   so the generator's `finally` never ran: the pump kept pulling from the
   provider and the reservation stayed held.

`TurnLifecycle` closes both. These tests inject a failure at every source, setup
and sink point AC-11 names and assert the shared latch selects exactly ONE
outcome:

- **pre-commit** — cancel and join registered work, mark the stream `error`,
  release the reservation, clear the stop signal, persist NO assistant row, and
  close delivery as an error;
- **post-commit** — the committed result stands: no status rewrite, no second
  charge.

Plus the identity assertion that makes all of it meaningful: the wrapper and the
generator hold the SAME object, so a sink failure and a source failure cannot be
reported to two different latches.

Reduction of the events themselves is `test_turn_reducer.py` (AC-03); the
resumable disconnect/stop semantics these failures interleave with are
`test_resumable_streams.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    Conversation,
    Message,
    PlatformBudgetReservation,
    Stream,
    UsageRollup,
    User,
)
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.errors import AppError
from app.providers.fake import FakeProvider
from app.providers.protocol import AnswerDelta, ProviderEvent
from app.providers.tiers import get_binding
from app.runtime.context import RuntimeContext
from app.streaming import handler as handler_mod
from app.streaming import stop_registry
from app.streaming.handler import ResumeToolSeed, run_detached_producer
from app.streaming.stop_registry import is_stop_requested_async, request_stop_async
from app.streaming.turn_lifecycle import TurnLifecycle
from app.tools.approval_settlement import ApprovalDecisionConflict

# `asyncio_mode = "auto"` collects the coroutine tests; the latch has synchronous
# surface too, so no module-level mark.

_QUOTA_USD = 5.0
_RESERVED_USD = 0.25


class _InjectedError(RuntimeError):
    """A failure planted at one named seam, distinguishable from a real bug."""


# Harness ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_stop_registry() -> Iterator[None]:
    """The stop registry is process-wide; these tests plant signals in it."""
    stop_registry._STOP_REQUESTS.clear()
    try:
        yield
    finally:
        stop_registry._STOP_REQUESTS.clear()


class _NoDisconnect:
    async def is_disconnected(self) -> bool:
        return False


class _UnusedProvider:
    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
        raise AssertionError("the turn must fail before the provider is read")


class _RecordingLifecycle(TurnLifecycle):
    """The real latch, plus who called it — construction site included.

    Patched over `handler.TurnLifecycle` so BOTH construction sites (the
    detached wrapper's, and the generator's `lifecycle or TurnLifecycle(...)`
    fallback) land in `instances`. Exactly one instance for a detached turn IS
    the shared-lifecycle assertion.
    """

    instances: ClassVar[list[_RecordingLifecycle]] = []

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.calls: list[str] = []
        _RecordingLifecycle.instances.append(self)

    def register_producer(self, task: asyncio.Task[Any]) -> None:
        self.calls.append("register_producer")
        super().register_producer(task)

    def record_commit(self, outcome: Any) -> None:
        self.calls.append(f"record_commit:{outcome}")
        super().record_commit(outcome)

    async def source_failed(self, exc: BaseException) -> None:
        self.calls.append("source_failed")
        await super().source_failed(exc)

    async def delivery_failed(self, exc: BaseException) -> None:
        self.calls.append("delivery_failed")
        await super().delivery_failed(exc)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


class _FailingSink:
    """A `ReplayLogBuffer` whose `append` raises at one chosen frame.

    The generator is suspended at that `yield` when the raise happens — which is
    precisely the state that used to leave the pump pulling forever.
    """

    def __init__(self, *, fail_on: str) -> None:
        self._fail_on = fail_on
        self.appended: list[str] = []
        self.done = False
        self.terminal_kind: str | None = None

    async def append(self, event: Any) -> None:
        name = event.event or ""
        if name == self._fail_on:
            raise _InjectedError(f"sink failed on {name!r}")
        self.appended.append(name)

    async def mark_done(self, *, terminal_kind: str, now: float | None = None) -> None:
        self.done = True
        self.terminal_kind = terminal_kind


@dataclass
class _Turn:
    user_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    paused_message_id: UUID
    stream_id: UUID


async def _seed_turn(session_factory: async_sessionmaker[AsyncSession]) -> _Turn:
    """A user, a conversation, an active stream row and a held reservation.

    The reservation and the durable `stream` row are the two resources a
    pre-commit failure has to give back, so every test starts holding both.
    """
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id, title="ac11", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_msg = Message(
            id=uuid4(),
            conversation_id=convo.id,
            role="user",
            parts=[{"type": "text", "text": "schedule a meeting"}],
            status="done",
        )
        session.add(user_msg)
        await session.flush()
        paused = Message(
            id=uuid4(),
            conversation_id=convo.id,
            role="assistant",
            parts=[
                {
                    "type": "tool_call",
                    "toolCallId": "fake_cal_1",
                    "name": "calendar_create_event",
                    "status": "awaiting_approval",
                    "approvalState": "pending",
                    "input": {"title": "kickoff"},
                }
            ],
            status="awaiting_approval",
            responds_to_message_id=user_msg.id,
        )
        session.add(paused)
        stream = await streams_repo.create_stream(session, conversation_id=convo.id)
        await session.flush()
        reserved = await usage_repo.reserve_platform_budget(
            session,
            user_id=user.id,
            stream_id=stream.id,
            amount_usd=_RESERVED_USD,
            monthly_quota_usd=_QUOTA_USD,
        )
        assert reserved is True
        await session.commit()
        return _Turn(
            user_id=user.id,
            conversation_id=convo.id,
            user_message_id=user_msg.id,
            paused_message_id=paused.id,
            stream_id=stream.id,
        )


async def _stream_status(
    session_factory: async_sessionmaker[AsyncSession], stream_id: UUID
) -> str:
    async with session_factory() as session:
        row = await session.get(Stream, stream_id)
    assert row is not None
    return row.status


async def _reservation_held(
    session_factory: async_sessionmaker[AsyncSession], stream_id: UUID
) -> bool:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(PlatformBudgetReservation).where(
                    PlatformBudgetReservation.stream_id == stream_id
                )
            )
        ).scalar_one_or_none()
    return row is not None


async def _assistant_rows(
    session_factory: async_sessionmaker[AsyncSession], conversation_id: UUID
) -> list[Message]:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .where(Message.role == "assistant")
                    .where(Message.status != "awaiting_approval")
                    .order_by(Message.created_at)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


async def _rollup(
    session_factory: async_sessionmaker[AsyncSession],
) -> UsageRollup | None:
    async with session_factory() as session:
        return (
            await session.execute(select(UsageRollup))
        ).scalar_one_or_none()


# 1. The latch itself ----------------------------------------------------------


async def test_a_precommit_source_failure_releases_every_resource(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One `source_failed` marks error, joins the work, and gives it all back."""
    turn = await _seed_turn(session_factory)
    await request_stop_async(turn.stream_id)
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )

    async def _forever() -> None:
        await asyncio.sleep(300)

    pump = asyncio.create_task(_forever())
    lifecycle.register_producer(pump)

    await lifecycle.source_failed(_InjectedError("source blew up"))

    assert lifecycle.outcome == "error"
    assert lifecycle.failure_stage == "source"
    assert lifecycle.committed is False
    assert lifecycle.closed is True
    assert pump.done() is True
    assert await _stream_status(session_factory, turn.stream_id) == "error"
    assert await _reservation_held(session_factory, turn.stream_id) is False
    assert await is_stop_requested_async(turn.stream_id) is False


async def test_a_postcommit_delivery_failure_keeps_the_committed_outcome(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """After the commit the latch reports, it does not re-decide.

    The generator commits `done` and marks the durable row before the terminal
    frame goes out. A sink failure on that frame must leave both alone — the
    turn happened, only its last frame did not arrive.
    """
    turn = await _seed_turn(session_factory)
    async with session_factory() as session:
        await streams_repo.mark_status(session, stream_id=turn.stream_id, status="done")
        await session.commit()
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )
    lifecycle.record_commit("done")

    await lifecycle.delivery_failed(_InjectedError("sink blew up"))

    assert lifecycle.outcome == "done"
    assert lifecycle.committed is True
    assert lifecycle.failure_stage == "delivery"
    assert await _stream_status(session_factory, turn.stream_id) == "done"
    # A post-commit failure does not close the turn by itself — the generator's
    # `finally` still owns that, and it is what releases the hold.
    assert lifecycle.closed is False
    assert await _reservation_held(session_factory, turn.stream_id) is True
    await lifecycle.close()
    assert await _reservation_held(session_factory, turn.stream_id) is False
    assert await _stream_status(session_factory, turn.stream_id) == "done"


async def test_the_first_outcome_wins_and_the_latch_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Generator `finally`, wrapper handler and `aclose()` all reach this."""
    turn = await _seed_turn(session_factory)
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )
    lifecycle.record_commit("paused")
    lifecycle.record_commit("stopped")
    assert lifecycle.outcome == "paused"

    first = _InjectedError("first")
    await lifecycle.delivery_failed(first)
    await lifecycle.source_failed(_InjectedError("second"))
    assert lifecycle.failure is first
    assert lifecycle.failure_stage == "delivery"
    assert lifecycle.outcome == "paused"

    await lifecycle.close()
    await lifecycle.close()
    assert await _reservation_held(session_factory, turn.stream_id) is False


async def test_a_hard_cancel_before_the_commit_terminalizes_the_stream_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Worker shutdown mid-turn: `stopped`, guard released, not left `active`."""
    turn = await _seed_turn(session_factory)
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )

    await lifecycle.hard_cancelled()

    assert lifecycle.outcome == "stopped"
    assert await _stream_status(session_factory, turn.stream_id) == "stopped"


async def test_a_hard_cancel_after_the_commit_does_not_rewrite_the_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The terminal frame is delivered AFTER the commit, so this is post-commit.

    A cancel landing on that yield used to rewrite the durable row from `done`
    (message id and all) to `stopped`, leaving the stream disagreeing with the
    assistant row it points at.
    """
    turn = await _seed_turn(session_factory)
    message_id = uuid4()
    async with session_factory() as session:
        await streams_repo.mark_status(
            session, stream_id=turn.stream_id, status="done", message_id=message_id
        )
        await session.commit()
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )
    lifecycle.record_commit("done")

    await lifecycle.hard_cancelled()

    assert lifecycle.outcome == "done"
    assert await _stream_status(session_factory, turn.stream_id) == "done"


async def test_cancel_registered_joins_a_failing_pump_without_raising(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The pump forwards provider errors through its queue, never on await."""
    lifecycle = TurnLifecycle(runtime=RuntimeContext.from_factory(session_factory))

    async def _raises() -> None:
        raise _InjectedError("pump died")

    async def _forever() -> None:
        await asyncio.sleep(300)

    failing = asyncio.create_task(_raises())
    hanging = asyncio.create_task(_forever())
    lifecycle.register_producer(failing)
    lifecycle.register_producer(hanging)
    # A fallback retry re-registers; the duplicate must not double-cancel.
    lifecycle.register_producer(hanging)
    await asyncio.sleep(0)

    await lifecycle.cancel_registered()
    await lifecycle.cancel_registered()

    assert failing.done() and hanging.cancelled()


# 2. Failure injection at every setup seam ------------------------------------


@dataclass(frozen=True)
class _Seam:
    """One planted setup failure and what the generator should raise."""

    seed: ResumeToolSeed | None
    expected: type[BaseException]
    # A pre-planted stop signal proves the latch clears it. Settlement reads the
    # signal as a real stop (returning cleanly instead of raising), so that one
    # seam runs without it.
    pre_stop: bool = True


def _approval_settlement(monkeypatch: pytest.MonkeyPatch, paused_id: UUID) -> _Seam:
    async def _conflict(*_args: object, **_kwargs: object) -> object:
        raise ApprovalDecisionConflict(
            stored_decision="deny", requested_decision="approve"
        )

    monkeypatch.setattr(handler_mod, "claim_and_settle_approval_outcome", _conflict)
    return _Seam(
        seed=ResumeToolSeed(
            tool_call_id="fake_cal_1",
            name="calendar_create_event",
            label="Create event",
            decision="approve",
            input={"title": "kickoff"},
            paused_message_id=paused_id,
            pending_settle=True,
        ),
        expected=AppError,
        pre_stop=False,
    )


def _prior_row_load(monkeypatch: pytest.MonkeyPatch, paused_id: UUID) -> _Seam:
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise _InjectedError("prior-row parse failed")

    monkeypatch.setattr(handler_mod, "tool_results_from_message_parts", _boom)
    return _Seam(
        seed=ResumeToolSeed(
            tool_call_id="fake_cal_1",
            name="calendar_create_event",
            label="Create event",
            decision="approve",
            input={"title": "kickoff"},
            paused_message_id=paused_id,
            settled_result=_SettledResult(),
        ),
        expected=_InjectedError,
    )


def _source_resolution(monkeypatch: pytest.MonkeyPatch, _paused_id: UUID) -> _Seam:
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise _InjectedError("source resolution failed")

    monkeypatch.setattr(handler_mod, "run_chat_with_empty_retry", _boom)
    return _Seam(seed=None, expected=_InjectedError)


def _pump_creation(monkeypatch: pytest.MonkeyPatch, _paused_id: UUID) -> _Seam:
    real_create_task = asyncio.create_task

    def _fail_pump(coro: Any, **kwargs: Any) -> Any:
        # Only the pump: everything else this turn (and the test harness) still
        # needs real tasks, so delegate by coroutine name.
        if getattr(coro, "__name__", "") == "_pump":
            coro.close()
            raise _InjectedError("pump creation failed")
        return real_create_task(coro, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", _fail_pump)
    return _Seam(seed=None, expected=_InjectedError)


def _seeded_execution(monkeypatch: pytest.MonkeyPatch, _paused_id: UUID) -> _Seam:
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise _InjectedError("seeded tool execution failed")

    monkeypatch.setattr(handler_mod, "execute_tool", _boom)
    return _Seam(
        seed=ResumeToolSeed(
            tool_call_id="fake_cal_1",
            name="calendar_create_event",
            label="Create event",
            decision="approve",
            input={"title": "kickoff"},
        ),
        expected=_InjectedError,
    )


class _SettledResult:
    """A route-settled approval outcome (BE-007), enough for the seed."""

    tool_call_id = "fake_cal_1"
    name = "calendar_create_event"
    status = "succeeded"
    approval_state = "approved"
    summary = "Created."
    output: ClassVar[dict[str, str]] = {"eventId": "evt-1"}
    error = None


_SEAMS: dict[str, Callable[[pytest.MonkeyPatch, UUID], _Seam]] = {
    "approval-settlement": _approval_settlement,
    "prior-row-load": _prior_row_load,
    "source-resolution": _source_resolution,
    "pump-creation": _pump_creation,
    "seeded-execution": _seeded_execution,
}


@pytest.mark.parametrize("seam_name", list(_SEAMS))
async def test_every_setup_seam_failure_is_one_precommit_outcome(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    seam_name: str,
) -> None:
    """AC-11: post-`submitted` setup failures all land in the same envelope.

    Each of these used to run outside any guard: the failure propagated to the
    route while the durable `stream` row sat at `active` and the platform hold
    stayed charged against the user's headroom until the reaper swept it.
    """
    turn = await _seed_turn(session_factory)
    seam = _SEAMS[seam_name](monkeypatch, turn.paused_message_id)
    if seam.pre_stop:
        await request_stop_async(turn.stream_id)
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )

    frames: list[str] = []
    with pytest.raises(seam.expected):
        async with session_factory() as session:
            async for frame in handler_mod.stream_and_persist(
                request=_NoDisconnect(),  # type: ignore[arg-type]
                db=session,
                lifecycle=lifecycle,
                provider=_UnusedProvider(),  # type: ignore[arg-type]
                binding=_binding(),
                requested_tier_id="smart",
                conversation_id=turn.conversation_id,
                user_message_id=turn.user_message_id,
                user_text="Tool approved: calendar_create_event",
                history=[],
                is_temporary=False,
                user_id=turn.user_id,
                stream_id=turn.stream_id,
                resume_seed=seam.seed,
            ):
                frames.append(frame.event or "")

    # The failure is post-`submitted` — which is exactly why the guard had to
    # exist — and it never reached a terminal frame.
    assert frames and frames[0] == "submitted"
    assert "terminal" not in frames
    # Exactly one outcome, on the pre-commit side of the line.
    assert lifecycle.outcome == "error"
    assert lifecycle.failure_stage == "source"
    assert lifecycle.committed is False
    assert lifecycle.closed is True
    # Registered work joined, not left pulling from the provider.
    assert all(task.done() for task in lifecycle._registered)
    # And every resource handed back.
    assert await _stream_status(session_factory, turn.stream_id) == "error"
    assert await _reservation_held(session_factory, turn.stream_id) is False
    if seam.pre_stop:
        assert await is_stop_requested_async(turn.stream_id) is False
    # An errored turn persists no assistant row (the paused row it resumes from
    # is excluded by `_assistant_rows`).
    assert await _assistant_rows(session_factory, turn.conversation_id) == []
    assert await _rollup(session_factory) is None


def _binding() -> Any:
    binding = get_binding("smart")
    assert binding is not None
    return binding


# 3. The inline delivery seam at the early yields ------------------------------


class _StallingProvider:
    """A provider whose stream never yields, so a registered pump stays live."""

    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            await asyncio.sleep(300)
            yield AnswerDelta(text="unreachable")

        return _gen()


def _record_terminalizations(
    monkeypatch: pytest.MonkeyPatch, stream_id: UUID
) -> list[str]:
    """Every durable `stream` status written for `stream_id`, in order.

    The list is how "terminalized exactly once" is asserted: one entry, not a
    second write from a path that also thought it owned the row.
    """
    real = streams_repo.mark_status
    written: list[str] = []

    async def _spy(db: Any, *, status: str, **kwargs: Any) -> None:
        if kwargs.get("stream_id") == stream_id:
            written.append(status)
        await real(db, status=status, **kwargs)

    monkeypatch.setattr(streams_repo, "mark_status", _spy)
    return written


def _early_yield_seed(paused_id: UUID) -> ResumeToolSeed:
    """A resume whose settled approval makes the generator emit a seeded frame."""
    return ResumeToolSeed(
        tool_call_id="fake_cal_1",
        name="calendar_create_event",
        label="Create event",
        decision="approve",
        input={"title": "kickoff"},
        paused_message_id=paused_id,
        settled_result=_SettledResult(),
    )


@pytest.mark.parametrize("close_at", ["submitted", "tool_result"])
async def test_closing_the_consumer_at_an_early_yield_unwinds_the_turn(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    close_at: str,
) -> None:
    """AC-11: the inline sink reports at the frames the main guard cannot cover.

    `submitted` and the seeded `tool_result` are delivered before the generator's
    own `try`/`finally` opens, so an `aclose()` landing on either used to raise
    `GeneratorExit` straight out with nothing releasing anything. At the seeded
    frame the pump is already registered, which made it a live task draining the
    provider for a turn no one was reading, with the reservation still held and
    the durable row still `active`.
    """
    turn = await _seed_turn(session_factory)
    await request_stop_async(turn.stream_id)
    written = _record_terminalizations(monkeypatch, turn.stream_id)
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )

    frames: list[str] = []
    async with session_factory() as session:
        producer = handler_mod.stream_and_persist(
            request=_NoDisconnect(),  # type: ignore[arg-type]
            db=session,
            lifecycle=lifecycle,
            provider=_StallingProvider(),  # type: ignore[arg-type]
            binding=_binding(),
            requested_tier_id="smart",
            conversation_id=turn.conversation_id,
            user_message_id=turn.user_message_id,
            user_text="Tool approved: calendar_create_event",
            history=[],
            is_temporary=False,
            user_id=turn.user_id,
            stream_id=turn.stream_id,
            resume_seed=(
                None if close_at == "submitted" else _early_yield_seed(turn.paused_message_id)
            ),
        )
        async for frame in producer:
            frames.append(frame.event or "")
            if frames[-1] == close_at:
                break
        # The generator is suspended AT that yield right now; this is what the
        # inline route's consumer does when it stops reading.
        await producer.aclose()

    assert frames[-1] == close_at
    # One outcome, selected by the sink's report rather than by nothing at all.
    assert lifecycle.outcome == "error"
    assert lifecycle.failure_stage == "delivery"
    assert isinstance(lifecycle.failure, GeneratorExit)
    assert lifecycle.closed is True
    # The pump exists only once setup got that far, and is joined either way.
    assert len(lifecycle._registered) == (1 if close_at == "tool_result" else 0)
    assert all(task.done() for task in lifecycle._registered)
    assert await _reservation_held(session_factory, turn.stream_id) is False
    assert await is_stop_requested_async(turn.stream_id) is False
    assert written == ["error"]
    assert await _stream_status(session_factory, turn.stream_id) == "error"
    assert await _assistant_rows(session_factory, turn.conversation_id) == []
    assert await _rollup(session_factory) is None


async def test_a_cancel_at_an_early_yield_terminalizes_as_stopped(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same seam, cancel semantics: an interruption is `stopped`, not `error`.

    A worker shutdown lands `CancelledError` on whichever yield the generator is
    suspended at, and the early ones are no exception — they just had no guard to
    route it through. The status matches the in-loop hard-cancel branch so the
    frame it happened to land on cannot change what the row says.
    """
    turn = await _seed_turn(session_factory)
    await request_stop_async(turn.stream_id)
    written = _record_terminalizations(monkeypatch, turn.stream_id)
    lifecycle = TurnLifecycle(
        runtime=RuntimeContext.from_factory(session_factory),
        stream_id=turn.stream_id,
        user_id=turn.user_id,
    )

    async with session_factory() as session:
        producer = handler_mod.stream_and_persist(
            request=_NoDisconnect(),  # type: ignore[arg-type]
            db=session,
            lifecycle=lifecycle,
            provider=_StallingProvider(),  # type: ignore[arg-type]
            binding=_binding(),
            requested_tier_id="smart",
            conversation_id=turn.conversation_id,
            user_message_id=turn.user_message_id,
            user_text="hello world",
            history=[],
            is_temporary=False,
            user_id=turn.user_id,
            stream_id=turn.stream_id,
        )
        first = await producer.__anext__()
        assert (first.event or "") == "submitted"
        with pytest.raises(asyncio.CancelledError):
            await producer.athrow(asyncio.CancelledError())

    assert lifecycle.outcome == "stopped"
    assert lifecycle.closed is True
    assert written == ["stopped"]
    assert await _stream_status(session_factory, turn.stream_id) == "stopped"
    assert await _reservation_held(session_factory, turn.stream_id) is False
    assert await is_stop_requested_async(turn.stream_id) is False
    assert await _assistant_rows(session_factory, turn.conversation_id) == []


# 4. Failure injection at the detached sink -----------------------------------


async def test_a_preterminal_sink_failure_unwinds_the_turn(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`buffer.append()` failing mid-stream is a pre-commit failure.

    The wrapper used to swallow this and leave the generator parked at its
    `yield`, so nothing ran the generator's teardown: the pump kept draining the
    provider and the reservation stayed held for the buffer's whole TTL.
    """
    # No pre-planted stop signal here: the detached generator polls the registry
    # each iteration, so a planted stop would take the stop path before the
    # answer frames and never reach the sink. Stop clearing is asserted by the
    # latch tests and the setup-seam matrix.
    turn = await _seed_turn(session_factory)
    _RecordingLifecycle.reset()
    monkeypatch.setattr(handler_mod, "TurnLifecycle", _RecordingLifecycle)
    sink = _FailingSink(fail_on="answer_delta")

    await run_detached_producer(
        buffer=sink,  # type: ignore[arg-type]
        session_factory=session_factory,
        provider=FakeProvider(delay_ms=0),
        binding=_binding(),
        requested_tier_id="smart",
        conversation_id=turn.conversation_id,
        user_message_id=turn.user_message_id,
        user_text="hello world",
        history=[],
        is_temporary=False,
        user_id=turn.user_id,
        stream_id=turn.stream_id,
    )

    assert len(_RecordingLifecycle.instances) == 1
    lifecycle = _RecordingLifecycle.instances[0]
    assert "delivery_failed" in lifecycle.calls
    assert lifecycle.outcome == "error"
    assert lifecycle.failure_stage == "delivery"
    assert lifecycle.committed is False
    assert lifecycle.closed is True
    assert all(task.done() for task in lifecycle._registered)
    assert await _stream_status(session_factory, turn.stream_id) == "error"
    assert await _reservation_held(session_factory, turn.stream_id) is False
    assert await _assistant_rows(session_factory, turn.conversation_id) == []
    assert await _rollup(session_factory) is None
    # Delivery closes as an error so every subscriber drains instead of hanging.
    assert sink.done is True
    assert sink.terminal_kind == "error"


async def test_a_terminal_frame_sink_failure_preserves_the_committed_turn(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same seam, one frame later, is a POST-commit failure.

    `record_commit` runs with the assistant row, the meter bump and the stream
    row in one commit, before the terminal frame is delivered. So a terminal
    append failure may not rewrite the status or charge a second time — the only
    thing lost is the last frame, which a reconnect replays.
    """
    turn = await _seed_turn(session_factory)
    _RecordingLifecycle.reset()
    monkeypatch.setattr(handler_mod, "TurnLifecycle", _RecordingLifecycle)
    sink = _FailingSink(fail_on="terminal")

    await run_detached_producer(
        buffer=sink,  # type: ignore[arg-type]
        session_factory=session_factory,
        provider=FakeProvider(delay_ms=0),
        binding=_binding(),
        requested_tier_id="smart",
        conversation_id=turn.conversation_id,
        user_message_id=turn.user_message_id,
        user_text="hello world",
        history=[],
        is_temporary=False,
        user_id=turn.user_id,
        stream_id=turn.stream_id,
    )

    assert len(_RecordingLifecycle.instances) == 1
    lifecycle = _RecordingLifecycle.instances[0]
    assert lifecycle.calls.count("record_commit:done") == 1
    assert "delivery_failed" in lifecycle.calls
    # The committed result stands, and the failure is recorded as delivery only.
    assert lifecycle.outcome == "done"
    assert lifecycle.committed is True
    assert lifecycle.failure_stage == "delivery"
    assert await _stream_status(session_factory, turn.stream_id) == "done"
    rows = await _assistant_rows(session_factory, turn.conversation_id)
    assert len(rows) == 1
    assert rows[0].status == "done"
    # Charged exactly once: one meter increment, matching the persisted row.
    rollup = await _rollup(session_factory)
    assert rollup is not None
    assert rollup.used == 1
    assert rollup.cost_usd == pytest.approx(rows[0].cost_usd or 0.0, abs=1e-6)
    # Teardown still ran, so the hold is released even though the turn stood.
    assert lifecycle.closed is True
    assert await _reservation_held(session_factory, turn.stream_id) is False
    assert sink.terminal_kind == "error"


async def test_the_wrapper_and_the_generator_share_one_lifecycle(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-11 identity: one latch per turn, built by the wrapper, used by both.

    The generator falls back to building its own only when the caller supplies
    none, so a second construction here would mean the sink's failures and the
    generator's commits were being reported to different objects.
    """
    turn = await _seed_turn(session_factory)
    _RecordingLifecycle.reset()
    monkeypatch.setattr(handler_mod, "TurnLifecycle", _RecordingLifecycle)
    sink = _FailingSink(fail_on="__never__")

    await run_detached_producer(
        buffer=sink,  # type: ignore[arg-type]
        session_factory=session_factory,
        provider=FakeProvider(delay_ms=0),
        binding=_binding(),
        requested_tier_id="smart",
        conversation_id=turn.conversation_id,
        user_message_id=turn.user_message_id,
        user_text="hello world",
        history=[],
        is_temporary=False,
        user_id=turn.user_id,
        stream_id=turn.stream_id,
    )

    assert len(_RecordingLifecycle.instances) == 1
    lifecycle = _RecordingLifecycle.instances[0]
    # The generator registered its pump AND committed on the wrapper's object.
    assert "register_producer" in lifecycle.calls
    assert "record_commit:done" in lifecycle.calls
    assert lifecycle.outcome == "done"
    assert lifecycle.closed is True
    assert sink.appended[-1] == "terminal"
    assert sink.terminal_kind == "done"
    assert await _reservation_held(session_factory, turn.stream_id) is False
