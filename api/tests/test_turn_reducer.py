"""AC-03 closure: one durable fold, two drivers (`TurnReducer`).

`stream_and_persist` used to carry two independent mutation trees over the same
`ProviderEvent` union — the inline delivery loop and `_apply_event`, the
stop/disconnect drain. They had already drifted (a drained sibling cancel
persisted `pending` + `cancelled` where the live fold wrote `rejected`), and
nothing structural stopped the next divergence.

These tests pin the replacement shut from three directions:

1. **Equivalence.** A table of EVERY `ProviderEvent` variant, tagged and
   untagged, replayed through the live driver and through the stopped drain,
   must produce identical typed state (`TurnState.snapshot()`) and identical
   persisted parts.
2. **Single ownership.** The reducer instance sees every event both drivers
   handle, in FIFO order, so no event can reach persistence around it.
3. **Receipt carriage.** A receipt-less display tick cannot disturb accounting
   banked by a boundary receipt, and the abrupt-stop estimate never outranks
   one.

Plus the driver invariants that live BESIDE the fold and must survive it:
Stop precedence over a queued pause and a queued provider error, seeded result
order, and the non-agentic `reasoning_done` exactly-once gate.

Billing consequences of the banked receipt (done/pause rows, resume seeding,
server_state round-trip) are covered by `test_arch_review_ledger_resume.py`;
inline disconnect, detached Stop, and flag-off identity by
`test_messages_stream.py`, `test_resumable_streams.py`, and
`test_agentic_flag_off.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    RunCost,
    Sources,
    StatusUpdate,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.providers.tiers import get_binding
from app.runtime.run_receipt import PhaseReceipt, RunReceipt, UsageTotals
from app.search.protocol import SourceItem
from app.streaming import handler as handler_mod
from app.streaming.handler import ResumeToolSeed
from app.streaming.turn_reducer import TurnReducer, TurnState

# No module-level `asyncio` mark: `asyncio_mode = "auto"` already collects the
# coroutine tests, and the pure-fold tests below are deliberately synchronous.


# Harness ----------------------------------------------------------------------


class _NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectAfterFirstFrame:
    """First poll False, every later poll True — so all but event #1 drains.

    The False poll parks the consumer on an empty queue, which hands control to
    the pump. `asyncio.Queue.put` does not suspend below the bound and the stub
    stream has no awaits between yields, so the pump lands the WHOLE table in
    the queue in one go and only event #1 is consumed live. The next poll
    cancels the pump with the rest still queued: the drain.
    """

    def __init__(self) -> None:
        self._polls = 0

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > 1


class _StubProvider:
    def __init__(self, make_events: Callable[[], AsyncIterator[ProviderEvent]]) -> None:
        self._make_events = make_events

    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
        return self._make_events()


class _UnusedProvider:
    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
        raise AssertionError("the stubbed orchestrator replaces the provider")


class _SpyReducer(TurnReducer):
    """The real fold, plus a record of what reached it and the state it wrote."""

    seen: ClassVar[list[ProviderEvent]] = []
    states: ClassVar[list[TurnState]] = []

    def reduce(self, state: TurnState, event: ProviderEvent, now: float) -> TurnState:
        _SpyReducer.seen.append(event)
        if state not in _SpyReducer.states:
            _SpyReducer.states.append(state)
        return super().reduce(state, event, now)

    @classmethod
    def reset(cls) -> None:
        cls.seen = []
        cls.states = []


@pytest.fixture
def settings_cache_reset() -> Iterator[None]:
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
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
        return user.id, convo.id


async def _assistant_row(
    session_factory: async_sessionmaker[AsyncSession], conversation_id: UUID
) -> Message:
    async with session_factory() as session:
        row = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .where(Message.role == "assistant")
                    .order_by(Message.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
    assert row is not None
    return row


async def _drive_turn(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[ProviderEvent],
    agentic: bool,
    live: bool,
    resume_seed: ResumeToolSeed | None = None,
) -> tuple[list[str], Message]:
    """Drive one turn over `events`; return (frame names, persisted row).

    `live=True` lets the stream exhaust so the inline delivery loop folds every
    event. `live=False` holds the stub stream open and disconnects after the
    first frame, so everything but event #1 is folded by the stopped drain.
    """
    monkeypatch.setenv("TOOLS_ENABLED", "true" if agentic else "false")
    monkeypatch.setenv("AGENTIC_ENABLED", "true" if agentic else "false")
    get_settings.cache_clear()
    monkeypatch.setattr(handler_mod, "TurnReducer", _SpyReducer)
    _SpyReducer.reset()

    binding = get_binding("smart")
    assert binding is not None

    def _make_events() -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            for ev in events:
                yield ev
            if not live:
                # A drained turn must end on the disconnect, not on exhaustion.
                await asyncio.sleep(30)

        return _gen()

    provider: Any
    if agentic:
        monkeypatch.setattr(
            handler_mod, "run_orchestrator", lambda **_kwargs: _make_events()
        )
        provider = _UnusedProvider()
    else:
        provider = _StubProvider(_make_events)

    user_id, conv_id = await _seed_conversation(session_factory)
    request_stub: Any = _NeverDisconnected() if live else _DisconnectAfterFirstFrame()
    frames: list[str] = []
    async with session_factory() as session:
        async for frame in handler_mod.stream_and_persist(
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
            resume_seed=resume_seed,
            agentic_mode="deep_research" if agentic else None,
        ):
            frames.append(frame.event or "")
    return frames, await _assistant_row(session_factory, conv_id)


def _parts(row: Message) -> list[dict[str, Any]]:
    raw = row.parts if isinstance(row.parts, list) else []
    return [p for p in raw if isinstance(p, dict)]


def _clock_free(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parts with measured wall-clock reduced to "was it measured".

    `ReasoningPart.durationSec` is a real duration, so two runs of the same
    table never produce the same float. Everything else must match exactly.
    """
    normalized: list[dict[str, Any]] = []
    for part in parts:
        copied = dict(part)
        if "durationSec" in copied:
            copied["durationSec"] = copied["durationSec"] is not None
        normalized.append(copied)
    return normalized


# The event table --------------------------------------------------------------
#
# Every `ProviderEvent` variant a turn can fold, including the `pending ->
# rejected` gate that exposed the original drift and a receipt-bearing boundary
# `RunCost`. `AwaitingApproval` is deliberately absent here: it is a pause HINT
# the stopped drain must DISCARD, so it belongs to the precedence tests below
# rather than to an equivalence table.

_GATED_CALL_ID = "gated-call-1"
_SOURCE = SourceItem(id=1, title="Docs", url="https://example.test/docs")
_RECEIPT = RunReceipt(
    cumulative_cost_usd=0.42,
    already_billed_cost_usd=0.12,
    cumulative_usage=UsageTotals(input_tokens=120, output_tokens=60),
    phases=(
        PhaseReceipt(
            phase_id="worker-0",
            role="worker",
            usage=UsageTotals(input_tokens=80, output_tokens=40),
            cost_usd=0.30,
        ),
    ),
    cap_usd=5.0,
)


def _tool_trace(subagent_id: str | None) -> list[ProviderEvent]:
    return [
        ToolCall(
            id="call-1",
            name="web_search",
            label="Search the web",
            status="running",
            input={"query": "kickoff agenda"},
            subagent_id=subagent_id,
        ),
        ToolResult(
            tool_call_id="call-1",
            name="web_search",
            label="Search the web",
            status="succeeded",
            summary="2 results",
            output={"hits": 2},
            subagent_id=subagent_id,
        ),
        ToolCall(
            id=_GATED_CALL_ID,
            name="calendar_create_event",
            label="Create event",
            status="awaiting_approval",
            approval_state="pending",
            input={"title": "kickoff"},
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


def _untagged_table() -> list[ProviderEvent]:
    return [
        ReasoningDelta(text="weighing "),
        ReasoningDelta(text="options"),
        ReasoningDone(),
        StatusUpdate(label="Searching the web", state="active"),
        Sources(items=[_SOURCE]),
        StatusUpdate(label="Searching the web", state="done"),
        *_tool_trace(None),
        AnswerDelta(text="Here is "),
        AnswerDelta(text="the plan."),
        # The non-agentic source is `run_agent_loop`, which relays usage through
        # its own cumulative XOR fold (a round reports usage via EITHER an
        # `UsageUpdate` OR `Complete.usage`) and rebuilds the terminal `Complete`
        # around the total. Both numbers are the round's single total, so what the
        # reducer sees is value-identical to this table and the identity assertion
        # is about the fold rather than about the loop's accounting.
        UsageUpdate(input_tokens=120, output_tokens=60),
        Complete(
            usage=UsageUpdate(input_tokens=120, output_tokens=60),
            substitution="provider_fallback",
            substituted_provider="anthropic",
            substituted_model="claude-x",
            substituted_display_label="Claude X",
            empty_retry=True,
            empty_retry_recovered=True,
        ),
    ]


def _tagged_table() -> list[ProviderEvent]:
    return [
        SubagentStarted(subagent_id="worker-0", label="Alpha", role="worker"),
        ReasoningDelta(text="worker thinking", subagent_id="worker-0"),
        ReasoningDone(subagent_id="worker-0"),
        StatusUpdate(label="Searching the web", state="active", subagent_id="worker-0"),
        Sources(items=[_SOURCE], subagent_id="worker-0"),
        *_tool_trace("worker-0"),
        AnswerDelta(text="worker findings", subagent_id="worker-0"),
        UsageUpdate(input_tokens=80, output_tokens=40, subagent_id="worker-0"),
        SubagentDone(
            subagent_id="worker-0",
            label="Alpha",
            role="worker",
            usage=UsageUpdate(input_tokens=80, output_tokens=40),
            cost_usd=0.30,
            outcome="succeeded",
        ),
        SubagentStarted(subagent_id="aggregator", label="Synthesis", role="aggregator"),
        AnswerDelta(text="Final synthesis.", subagent_id="aggregator"),
        SubagentDone(
            subagent_id="aggregator",
            label="Synthesis",
            role="aggregator",
            usage=UsageUpdate(input_tokens=40, output_tokens=20),
            cost_usd=0.12,
            outcome="succeeded",
        ),
        RunCost(subtotal_usd=0.42, cap_usd=5.0, phase="final", receipt=_RECEIPT),
        Complete(usage=UsageUpdate(input_tokens=120, output_tokens=60)),
    ]


# 1. Equivalence ---------------------------------------------------------------


@pytest.mark.parametrize("agentic", [False, True], ids=["untagged", "tagged"])
async def test_every_event_variant_reduces_the_same_live_and_drained(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    agentic: bool,
) -> None:
    """AC-03: identical typed state AND persisted parts from both drivers."""
    table = _tagged_table() if agentic else _untagged_table()

    _live_frames, live_row = await _drive_turn(
        session_factory, monkeypatch, events=table, agentic=agentic, live=True
    )
    live_state = _SpyReducer.states[-1].snapshot()

    _drain_frames, drain_row = await _drive_turn(
        session_factory, monkeypatch, events=table, agentic=agentic, live=False
    )
    drain_state = _SpyReducer.states[-1].snapshot()

    # The two drivers took different exits — that is the whole point of the
    # comparison: only the outcome differs, never the durable fold.
    assert live_row.status == "done"
    assert drain_row.status == "stopped"
    assert drain_state == live_state
    assert _clock_free(_parts(drain_row)) == _clock_free(_parts(live_row))
    # And the fold that produced them settled the gate the drain used to split.
    calls = [
        p
        for p in _parts(live_row)
        if p.get("type") == "tool_call" and p.get("id") == _GATED_CALL_ID
    ]
    assert calls and calls[0]["status"] == "cancelled"
    assert calls[0]["approvalState"] == "rejected"


# 2. Single ownership ----------------------------------------------------------


@pytest.mark.parametrize("live", [True, False], ids=["live", "drain"])
@pytest.mark.parametrize("agentic", [False, True], ids=["untagged", "tagged"])
async def test_one_reducer_instance_sees_every_event_in_order(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    agentic: bool,
    live: bool,
) -> None:
    """AC-03: both drivers fold through ONE instance, and the drain is FIFO."""
    table = _tagged_table() if agentic else _untagged_table()
    await _drive_turn(
        session_factory, monkeypatch, events=table, agentic=agentic, live=live
    )
    assert _SpyReducer.seen == table
    assert len(_SpyReducer.states) == 1


# 3. Receipt carriage ---------------------------------------------------------


def test_a_receiptless_display_tick_cannot_disturb_banked_accounting() -> None:
    """AC-02 via the fold: only a receipt-bearing boundary sets the authority."""
    state = TurnState(agentic=True)
    reducer = TurnReducer()

    reducer.reduce(state, RunCost(subtotal_usd=0.1, cap_usd=5.0, phase="plan"), 0.0)
    assert state.receipt is None
    assert state.run_summary is not None
    assert state.run_summary.cost_phase == "plan"

    reducer.reduce(
        state,
        RunCost(subtotal_usd=0.42, cap_usd=5.0, phase="final", receipt=_RECEIPT),
        1.0,
    )
    assert state.receipt is _RECEIPT

    # A later progress tick refreshes the wire summary and NOTHING else.
    reducer.reduce(
        state, RunCost(subtotal_usd=99.0, cap_usd=5.0, phase="progress"), 2.0
    )
    assert state.receipt is _RECEIPT
    assert state.run_summary.cost_phase == "progress"


async def test_a_stop_estimate_never_replaces_a_banked_receipt(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The abrupt-stop estimator is a fallback, not a competitor.

    The table's `SubagentDone` costs sum to `0.42` cumulative with `0.30 + 0.12`
    of worker spend, but the receipt says `0.12` of that was already billed on an
    earlier pause. A stopped turn that banked the receipt must charge the
    receipt's `newlyBillable`, not the estimator's full reconstruction.
    """
    _frames, row = await _drive_turn(
        session_factory,
        monkeypatch,
        events=_tagged_table(),
        agentic=True,
        live=False,
    )
    assert row.status == "stopped"
    assert row.cost_usd == pytest.approx(_RECEIPT.newly_billable_cost_usd)
    attribution = row.attribution if isinstance(row.attribution, dict) else {}
    assert attribution.get("costUsd") == pytest.approx(_RECEIPT.cumulative_cost_usd)


# 4. Driver invariants beside the fold ----------------------------------------


async def test_stop_wins_over_a_queued_pause(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued `AwaitingApproval` is a pause hint the drain discards."""
    events: list[ProviderEvent] = [
        AnswerDelta(text="one moment"),
        ToolCall(
            id="gate-2",
            name="calendar_create_event",
            label="Create event",
            status="awaiting_approval",
            approval_state="pending",
            input={"title": "kickoff"},
        ),
        AwaitingApproval(tool_call_id="gate-2"),
    ]
    frames, row = await _drive_turn(
        session_factory, monkeypatch, events=events, agentic=False, live=False
    )
    assert row.status == "stopped"
    # No terminal frame at all on a disconnect, least of all a pause terminal.
    assert "terminal" not in frames
    # The gated call still persists exactly as it was folded.
    calls = [p for p in _parts(row) if p.get("type") == "tool_call"]
    assert calls and calls[0]["approvalState"] == "pending"


async def test_stop_wins_over_a_queued_provider_error(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `_PumpError` behind the stop is dropped: `stopped`, not `error`."""
    binding = get_binding("smart")
    assert binding is not None
    monkeypatch.setenv("TOOLS_ENABLED", "false")
    monkeypatch.setenv("AGENTIC_ENABLED", "false")
    get_settings.cache_clear()

    async def _gen() -> AsyncIterator[ProviderEvent]:
        yield AnswerDelta(text="partial")
        yield AnswerDelta(text=" answer")
        raise RuntimeError("provider blew up after the stop was queued")

    user_id, conv_id = await _seed_conversation(session_factory)
    frames: list[str] = []
    async with session_factory() as session:
        async for frame in handler_mod.stream_and_persist(
            request=_DisconnectAfterFirstFrame(),  # type: ignore[arg-type]
            db=session,
            provider=_StubProvider(_gen),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        ):
            frames.append(frame.event or "")

    row = await _assistant_row(session_factory, conv_id)
    assert row.status == "stopped"
    assert "error" not in frames
    texts = [p for p in _parts(row) if p.get("type") == "text"]
    assert texts and texts[0]["text"] == "partial answer"


async def test_a_seeded_result_precedes_every_provider_event(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resumed approval's `tool_result` leads, on the wire and in the row."""

    class _Settled:
        tool_call_id = "resumed-call"
        name = "calendar_create_event"
        status = "succeeded"
        approval_state = "approved"
        summary = "Created."
        output: ClassVar[dict[str, str]] = {"eventId": "evt-1"}
        error = None

    seed = ResumeToolSeed(
        tool_call_id="resumed-call",
        name="calendar_create_event",
        label="Create event",
        decision="approve",
        input={"title": "kickoff"},
        settled_result=_Settled(),
    )
    frames, row = await _drive_turn(
        session_factory,
        monkeypatch,
        events=[AnswerDelta(text="Booked it."), Complete(usage=UsageUpdate())],
        agentic=False,
        live=True,
        resume_seed=seed,
    )
    assert frames[:2] == ["submitted", "tool_result"]
    assert frames.index("tool_result") < frames.index("answer_delta")
    part_types = [p.get("type") for p in _parts(row)]
    assert part_types[0] == "tool_result"


@pytest.mark.parametrize(
    ("events", "case"),
    [
        (
            [
                ReasoningDelta(text="hmm"),
                ReasoningDone(),
                AnswerDelta(text="answer"),
                Complete(usage=UsageUpdate()),
            ],
            "explicit",
        ),
        (
            [
                ReasoningDelta(text="hmm"),
                AnswerDelta(text="answer"),
                Complete(usage=UsageUpdate()),
            ],
            "synthesized",
        ),
    ],
    ids=["explicit-done", "synthesized-done"],
)
async def test_non_agentic_reasoning_done_is_emitted_once_before_the_answer(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    events: list[ProviderEvent],
    case: str,
) -> None:
    """Explicit or synthesized, the wire gate stays exactly-once and ordered."""
    frames, _row = await _drive_turn(
        session_factory, monkeypatch, events=events, agentic=False, live=True
    )
    assert frames.count("reasoning_done") == 1
    assert frames.index("reasoning_done") < frames.index("answer_delta")


async def test_a_second_reasoning_done_is_not_relayed(
    settings_cache_reset: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that repeats `ReasoningDone` still yields one wire frame."""
    frames, _row = await _drive_turn(
        session_factory,
        monkeypatch,
        events=[
            ReasoningDelta(text="hmm"),
            ReasoningDone(),
            ReasoningDone(),
            AnswerDelta(text="answer"),
            Complete(usage=UsageUpdate()),
        ],
        agentic=False,
        live=True,
    )
    assert frames.count("reasoning_done") == 1


# 5. The fold itself ----------------------------------------------------------


def test_reduce_reads_no_clock_of_its_own() -> None:
    """`now` is injected, so the same inputs always produce the same state."""
    reducer = TurnReducer()
    first = TurnState(started_at=100.0)
    second = TurnState(started_at=100.0)
    for state in (first, second):
        reducer.reduce(state, ReasoningDelta(text="think"), 100.5)
        reducer.reduce(state, ReasoningDone(), 101.5)
        reducer.reduce(state, AnswerDelta(text="answer"), 102.0)
    assert first.snapshot() == second.snapshot()
    assert first.first_answer_ms == 2000
    assert first.reasoning_duration_sec == pytest.approx(1.0)


def test_reduce_returns_the_same_state_it_was_given() -> None:
    """The fold is an accumulator, not a factory: one state per turn."""
    reducer = TurnReducer()
    state = TurnState()
    assert reducer.reduce(state, AnswerDelta(text="hi"), 1.0) is state


def test_an_untagged_event_on_an_agentic_turn_folds_flat() -> None:
    """Scope routing keys off the tag, not the mode."""
    reducer = TurnReducer()
    state = TurnState(agentic=True)
    reducer.reduce(state, AnswerDelta(text="untagged"), 1.0)
    reducer.reduce(state, AnswerDelta(text="tagged", subagent_id="worker-0"), 1.0)
    assert "".join(state.answer) == "untagged"
    assert "".join(state.scopes["worker-0"].answer) == "tagged"


def test_a_complete_without_substitution_keeps_the_router_seed() -> None:
    """The silent-downgrade-leak invariant, inside the fold."""
    reducer = TurnReducer()
    state = TurnState(substitution="auto_downgrade")
    reducer.reduce(state, Complete(usage=UsageUpdate(input_tokens=3)), 1.0)
    assert state.substitution == "auto_downgrade"
    assert state.usage.input_tokens == 3
