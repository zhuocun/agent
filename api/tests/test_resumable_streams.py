"""Resumable-stream replay tests (PRD 04 §5.1 P1; flag ON).

Exercises the in-process replay spine gated behind
`Settings.resumable_streams_enabled`:

- the `ReplayBuffer` / `ReplaySubscription` primitives (ordering, multi-
  subscriber fan-out, missed-wakeup safety, TTL eviction),
- the detached producer (`run_detached_producer`) persisting exactly once with
  the correct final content while a "disconnected" original subscriber and a
  reconnect both tail the same buffer,
- the route surface: the reconnect GET endpoint's ownership / 404 semantics and
  the flag-OFF disablement.

Disconnect is driven by the same `Request.is_disconnected()` patching pattern
the existing stop-path tests use; TTL is driven by injecting the monotonic
clock (`now=`) so there are no wall-clock waits.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, Stream, User
from app.db.repositories import streams as streams_repo
from app.db.session import get_db
from app.providers.fake import FakeProvider
from app.providers.protocol import AnswerDelta, ChatMessage, ProviderEvent
from app.providers.tiers import get_binding
from app.schemas.stream_events import AnswerDeltaEvent, SubmittedEvent
from app.streaming import replay_registry
from app.streaming.handler import run_detached_producer
from app.streaming.replay_registry import ReplayBuffer
from app.streaming.sse import encode_answer_delta, encode_submitted
from app.streaming.stop_registry import request_stop

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _seed_user_and_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tier_id: str = "smart",
) -> tuple[UUID, UUID]:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id=tier_id,
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return user.id, convo.id


async def _seed_stream(
    session_factory: async_sessionmaker[AsyncSession], *, conversation_id: UUID
) -> UUID:
    async with session_factory() as session:
        stream = await streams_repo.create_stream(
            session, conversation_id=conversation_id
        )
        await session.commit()
        return stream.id


def _event_names(events: list[object]) -> list[str]:
    return [getattr(e, "event", None) or "" for e in events]


# ReplayBuffer primitives ------------------------------------------------------


async def test_buffer_replays_buffered_then_tails_to_done() -> None:
    """A subscriber that joins mid-flight replays all buffered events from 0,
    then tails new events until `done`, in order, exactly once."""
    buf = ReplayBuffer()
    await buf.append(encode_submitted(SubmittedEvent(message_id="u")))
    await buf.append(encode_answer_delta(AnswerDeltaEvent(text="a")))

    sub = await buf.subscribe()
    collected: list[object] = []

    async def _consume() -> None:
        async for ev in sub.events():
            collected.append(ev)

    task = asyncio.create_task(_consume())
    await asyncio.sleep(0)  # let it drain the two buffered events

    await buf.append(encode_answer_delta(AnswerDeltaEvent(text="b")))
    await buf.mark_done(terminal_kind="done")
    await asyncio.wait_for(task, timeout=2.0)

    assert _event_names(collected) == [
        "submitted",
        "answer_delta",
        "answer_delta",
    ]
    assert buf.done is True
    assert buf.terminal_kind == "done"


async def test_two_concurrent_subscribers_both_get_full_sequence() -> None:
    """Two subscribers on the same live buffer each receive the COMPLETE ordered
    sequence (no interleaving corruption, no lost final event)."""
    buf = ReplayBuffer()
    sub_a = await buf.subscribe()
    sub_b = await buf.subscribe()
    out_a: list[str] = []
    out_b: list[str] = []

    async def _consume(sub: object, out: list[str]) -> None:
        async for ev in sub.events():  # type: ignore[attr-defined]
            out.append(ev.event or "")

    ta = asyncio.create_task(_consume(sub_a, out_a))
    tb = asyncio.create_task(_consume(sub_b, out_b))
    await asyncio.sleep(0)

    for i in range(5):
        await buf.append(encode_answer_delta(AnswerDeltaEvent(text=str(i))))
        await asyncio.sleep(0)
    await buf.mark_done(terminal_kind="done")

    await asyncio.wait_for(asyncio.gather(ta, tb), timeout=2.0)
    assert out_a == ["answer_delta"] * 5
    assert out_b == ["answer_delta"] * 5


async def test_subscriber_after_done_replays_full_sequence_then_closes() -> None:
    """A subscriber that joins AFTER the producer finished still replays the
    full buffered sequence then closes cleanly (within-TTL reconnect)."""
    buf = ReplayBuffer()
    await buf.append(encode_submitted(SubmittedEvent(message_id="u")))
    await buf.append(encode_answer_delta(AnswerDeltaEvent(text="final")))
    await buf.mark_done(terminal_kind="done")

    sub = await buf.subscribe()
    collected = [ev async for ev in sub.events()]
    assert _event_names(collected) == ["submitted", "answer_delta"]


async def test_ttl_eviction_is_lazy_and_clock_injectable() -> None:
    """A done buffer is retained within TTL and evicted past it; reconnect after
    eviction returns None. Driven by an injected clock — no wall-clock wait."""
    sid = uuid4()
    buf = replay_registry.create(sid, ttl_seconds=60.0, now=0.0)
    await buf.mark_done(terminal_kind="done", now=0.0)

    # Within TTL: still retrievable.
    assert replay_registry.get(sid, ttl_seconds=60.0, now=30.0) is buf
    # Past TTL: swept on access → None.
    assert replay_registry.get(sid, ttl_seconds=60.0, now=61.0) is None
    # And it's gone from the map.
    assert replay_registry.get(sid, ttl_seconds=60.0, now=61.0) is None


# Detached producer ------------------------------------------------------------


async def test_disconnect_then_reconnect_replays_and_persists_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The original subscriber 'disconnects' mid-stream; a reconnect replays
    everything already produced AND continues to the terminal. The assistant row
    persists ONCE with the full final content (status=done), never `stopped`.

    The producer is detached, so the original subscriber abandoning the buffer
    does NOT stop production — exactly the semantics inversion.
    """
    user_id, conv_id = await _seed_user_and_conversation(session_factory)
    stream_id = await _seed_stream(session_factory, conversation_id=conv_id)
    binding = get_binding("smart")
    assert binding is not None

    buffer = replay_registry.create(stream_id, ttl_seconds=60.0)

    # A slow-ish fake provider so the original subscriber can read a couple of
    # events and abandon while production is still in flight.
    producer = asyncio.create_task(
        run_detached_producer(
            buffer=buffer,
            session_factory=session_factory,
            provider=FakeProvider(delay_ms=10),
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello world",
            history=[],
            is_temporary=False,
            user_id=user_id,
            stream_id=stream_id,
        )
    )

    # Original subscriber: read the first two events, then abandon (simulating a
    # client disconnect — the route would just stop tailing).
    sub1 = await buffer.subscribe()
    first_two: list[str] = []
    gen1 = sub1.events()
    async for ev in gen1:
        first_two.append(ev.event or "")
        if len(first_two) >= 2:
            break
    await gen1.aclose()
    assert first_two[0] == "submitted"

    # Reconnect subscriber joins and tails to completion. It must REPLAY from 0.
    sub2 = await buffer.subscribe()
    replayed = [ev.event or "" async for ev in sub2.events()]

    await asyncio.wait_for(producer, timeout=5.0)

    # Reconnect saw the full ordered sequence including the terminal.
    assert replayed[0] == "submitted"
    assert replayed[-1] == "terminal"
    assert "reasoning_done" in replayed
    assert "answer_delta" in replayed

    # Persisted EXACTLY ONCE, status=done, with the full answer text.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalars().all()
        assert len(rows) == 1
        asst = rows[0]
        assert asst.status == "done"
        assert asst.attribution is not None
        assert asst.attribution["costConfidence"] == "exact"
        text = "".join(
            p.get("text", "") for p in asst.parts if p.get("type") == "text"
        )
        assert len(text) > 0

        # Stream row transitioned to done, linked to the assistant row.
        stream_row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        assert stream_row.status == "done"
        assert stream_row.message_id == asst.id

    # Buffer marked done with the terminal kind so subscribers drained + closed.
    assert buffer.done is True
    assert buffer.terminal_kind == "done"


async def test_stop_during_resumable_persists_stopped_and_marks_done(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Stop during a resumable stream → the detached producer persists
    `stopped`, marks the buffer done, and subscribers close cleanly."""

    class _BlockAfterDelta:
        """Emit one answer delta then block — until the stop signal tears it
        down via the handler's `is_stop_requested` poll."""

        def stream(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            api_key: str | None = None,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="partial")
                await asyncio.Event().wait()  # block forever

            return _gen()

        async def complete(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            api_key: str | None = None,
        ) -> str:
            return "unused"

    user_id, conv_id = await _seed_user_and_conversation(session_factory)
    stream_id = await _seed_stream(session_factory, conversation_id=conv_id)
    binding = get_binding("smart")
    assert binding is not None

    buffer = replay_registry.create(stream_id, ttl_seconds=60.0)
    producer = asyncio.create_task(
        run_detached_producer(
            buffer=buffer,
            session_factory=session_factory,
            provider=_BlockAfterDelta(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
            stream_id=stream_id,
        )
    )

    # Subscriber tails the buffer to close.
    sub = await buffer.subscribe()
    collected: list[str] = []

    async def _consume() -> None:
        async for ev in sub.events():
            collected.append(ev.event or "")

    consumer = asyncio.create_task(_consume())

    # Let the producer emit `submitted` + the first delta, then request a stop.
    await asyncio.sleep(0.05)
    request_stop(stream_id)

    await asyncio.wait_for(producer, timeout=5.0)
    await asyncio.wait_for(consumer, timeout=5.0)

    # Subscriber drained + closed (no terminal frame on a stop).
    assert "submitted" in collected
    assert "terminal" not in collected
    assert buffer.done is True

    # Producer persisted the assistant row as stopped + the stream row stopped.
    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        assert asst.status == "stopped"
        assert asst.attribution["costConfidence"] == "estimate"
        stream_row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        assert stream_row.status == "stopped"


# Route surface: reconnect endpoint -------------------------------------------


@pytest.fixture
def resumable_env() -> Iterator[None]:
    """Turn the resumable-stream flag ON for the duration of the test."""
    prior = os.environ.get("RESUMABLE_STREAMS_ENABLED")
    os.environ["RESUMABLE_STREAMS_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("RESUMABLE_STREAMS_ENABLED", None)
        else:
            os.environ["RESUMABLE_STREAMS_ENABLED"] = prior
        get_settings.cache_clear()


@pytest.fixture
def resumable_app(
    resumable_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_db_path: Path,
):  # type: ignore[no-untyped-def]
    from fastapi import FastAPI

    from app.main import create_app
    from app.middleware.ratelimit import limiter
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import stop_registry

    _TEMP_IDS.clear()
    stop_registry._STOP_REQUESTS.clear()
    replay_registry._BUFFERS.clear()
    storage = limiter._storage
    if hasattr(storage, "storage"):
        storage.storage.clear()
    if hasattr(storage, "expirations"):
        storage.expirations.clear()

    app_: FastAPI = create_app()

    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app_.dependency_overrides[get_db] = _get_db_override
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
async def resumable_client(resumable_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=resumable_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client_:
        yield client_


async def _drain_post_stream(
    client: AsyncClient, url: str, body: dict[str, object]
) -> None:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        async for _ in resp.aiter_text():
            pass


async def test_post_creates_resumable_stream_and_reconnect_after_done_replays(
    resumable_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Flag ON: a POST drives a detached producer; after it finishes the buffer
    is retained within TTL, so a reconnect GET replays the full final sequence
    then closes. After eviction the reconnect 404s."""
    await resumable_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id, title="New chat", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = str(convo.id)

    await _drain_post_stream(
        resumable_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hello"},
    )

    # The detached producer created a stream row; find it.
    async with session_factory() as session:
        stream_row = (await session.execute(select(Stream))).scalar_one()
        stream_id = str(stream_row.id)
        assert stream_row.status == "done"

    # Reconnect within TTL: replays the full final sequence then closes.
    async with resumable_client.stream(
        "GET", f"/api/conversations/{conv_id}/stream/{stream_id}", timeout=10.0
    ) as resp:
        assert resp.status_code == 200
        body = "".join([chunk async for chunk in resp.aiter_text()])
    assert "event: submitted" in body
    assert "event: terminal" in body

    # Evict (simulate TTL expiry) → reconnect 404s.
    replay_registry.evict(UUID(stream_id))
    resp2 = await resumable_client.get(
        f"/api/conversations/{conv_id}/stream/{stream_id}"
    )
    assert resp2.status_code == 404


async def test_reconnect_unknown_stream_is_404(
    resumable_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Flag ON: reconnect to a stream id that doesn't exist → 404."""
    await resumable_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id, title="New chat", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = str(convo.id)

    resp = await resumable_client.get(
        f"/api/conversations/{conv_id}/stream/{uuid4()}"
    )
    assert resp.status_code == 404


async def test_reconnect_non_owner_is_404(
    resumable_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Flag ON: reconnect on a conversation owned by ANOTHER user → 404 (IDOR
    protection — never 403, never leak existence)."""
    await resumable_client.get("/api/bootstrap")

    # Another user's conversation + stream + live buffer.
    _other_user_id, other_conv_id = await _seed_user_and_conversation(session_factory)
    other_stream_id = await _seed_stream(
        session_factory, conversation_id=other_conv_id
    )
    replay_registry.create(other_stream_id, ttl_seconds=60.0)

    resp = await resumable_client.get(
        f"/api/conversations/{other_conv_id}/stream/{other_stream_id}"
    )
    assert resp.status_code == 404


async def test_reconnect_stream_for_other_conversation_is_404(
    resumable_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Flag ON: a stream id that exists but belongs to a DIFFERENT conversation
    of the SAME user must not replay under the wrong conversation → 404."""
    await resumable_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    async with session_factory() as session:
        c1 = Conversation(
            user_id=user_id, title="c1", selected_tier_id="smart", pinned=False
        )
        c2 = Conversation(
            user_id=user_id, title="c2", selected_tier_id="smart", pinned=False
        )
        session.add_all([c1, c2])
        await session.commit()
        await session.refresh(c1)
        await session.refresh(c2)
        c1_id, c2_id = str(c1.id), c2.id
    stream_for_c2 = await _seed_stream(session_factory, conversation_id=c2_id)
    replay_registry.create(stream_for_c2, ttl_seconds=60.0)

    # Ask for c2's stream under c1 → 404 (cross-conversation).
    resp = await resumable_client.get(
        f"/api/conversations/{c1_id}/stream/{stream_for_c2}"
    )
    assert resp.status_code == 404


# Flag OFF ---------------------------------------------------------------------


async def test_flag_off_reconnect_endpoint_404s_and_post_is_unchanged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Flag OFF (default): the reconnect endpoint 404s (feature disabled) and a
    POST behaves exactly as before — no buffer is created, no detached producer
    runs, the stream row goes straight to `done` on the inline path."""
    assert get_settings().resumable_streams_enabled is False

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id, title="New chat", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = str(convo.id)

    await _drain_post_stream(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hello"},
    )

    async with session_factory() as session:
        stream_row = (await session.execute(select(Stream))).scalar_one()
        assert stream_row.status == "done"
        stream_id = str(stream_row.id)

    # No buffer was created on the flag-off path.
    assert replay_registry.get(UUID(stream_id), ttl_seconds=60.0) is None

    # Reconnect endpoint is disabled → 404.
    resp = await client.get(f"/api/conversations/{conv_id}/stream/{stream_id}")
    assert resp.status_code == 404
