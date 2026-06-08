"""Stream lifecycle + dedicated stop endpoint tests (PRD 04 §5.1).

Covers the durable `stream` row lifecycle and the `POST /{id}/stop` endpoint.

Mid-stream stop can't be driven through the httpx ASGI transport (it doesn't
expose a clean mid-stream disconnect — see the xfail in
`tests/test_messages_stream.py`), so the route-level stop is verified via the
durable `stream` row + the in-process signal, and the generator's stop-path
teardown is verified by a DIRECT unit test of `stream_and_persist` (mirroring
`tests/test_usage.py::test_stopped_flush_increments_usage`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, Stream, User
from app.db.repositories import streams as streams_repo
from app.providers.protocol import AnswerDelta, ChatMessage, ProviderEvent
from app.streaming.stop_registry import (
    clear_stop,
    is_stop_requested,
    request_stop,
)

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> str:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id=tier_id,
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


async def _drain_sse(client: AsyncClient, url: str, body: dict[str, object]) -> None:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        async for _ in resp.aiter_text():
            pass


# Lifecycle via the route ------------------------------------------------------


async def test_non_temp_turn_creates_then_marks_stream_done(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A non-temporary turn creates an `active` stream row that transitions to
    `done` after the turn completes, pointing at the persisted assistant row."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _drain_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hello"},
    )

    async with session_factory() as session:
        stream = (await session.execute(select(Stream))).scalar_one()
        assert stream.status == "done"
        # The done transition links the persisted assistant row.
        assert stream.message_id is not None
        assistant = (
            await session.execute(
                select(Message).where(Message.id == stream.message_id)
            )
        ).scalar_one()
        assert assistant.role == "assistant"
        assert assistant.status == "done"


async def test_temporary_turn_creates_no_stream_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Temporary chats persist nothing -> no stream row."""
    await client.get("/api/bootstrap")

    # Create a temporary conversation (synthetic id, no DB row).
    resp = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": True},
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]

    await _drain_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hello",
            "isTemporary": True,
        },
    )

    async with session_factory() as session:
        rows = (await session.execute(select(Stream))).scalars().all()
        assert rows == []


# Stop endpoint ----------------------------------------------------------------


async def test_stop_signals_without_releasing_active_guard(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """POST /{id}/stop on a conversation with an active stream -> 204 and the
    stream row remains `active` until the producer persists its terminal state."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Seed an active stream row directly (simulates an in-flight turn).
    async with session_factory() as session:
        stream = await streams_repo.create_stream(
            session, conversation_id=UUID(conv_id)
        )
        stream_id = stream.id
        await session.commit()

    resp = await client.post(f"/api/conversations/{conv_id}/stop")
    assert resp.status_code == 204

    async with session_factory() as session:
        row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        assert row.status == "active"

    second = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "second turn",
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "STREAM_IN_PROGRESS"

    # The in-process live signal was set for that stream id.
    assert is_stop_requested(stream_id) is True
    clear_stop(stream_id)


async def test_send_message_with_active_stream_is_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second turn while one is already streaming is rejected with 409
    STREAM_IN_PROGRESS (the single-in-flight-per-conversation guard), and no
    second stream row is created."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Seed an active stream row directly (simulates an in-flight turn).
    async with session_factory() as session:
        await streams_repo.create_stream(session, conversation_id=UUID(conv_id))
        await session.commit()

    resp = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hi"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STREAM_IN_PROGRESS"

    # The guard rejected before creating a second stream row.
    async with session_factory() as session:
        rows = (await session.execute(select(Stream))).scalars().all()
        assert len(rows) == 1


async def test_stop_no_active_stream_is_idempotent_204(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Stop with no active stream returns 204 (no-op)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    resp = await client.post(f"/api/conversations/{conv_id}/stop")
    assert resp.status_code == 204

    async with session_factory() as session:
        rows = (await session.execute(select(Stream))).scalars().all()
        assert rows == []


async def test_stop_on_unowned_conversation_is_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Stop on a conversation owned by another user -> 404."""
    await client.get("/api/bootstrap")

    # A conversation owned by a DIFFERENT user.
    async with session_factory() as session:
        other = User(is_anonymous=True, name="Other")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_id = other.id
    conv_id = await _seed_conversation(session_factory, user_id=other_id)

    resp = await client.post(f"/api/conversations/{conv_id}/stop")
    assert resp.status_code == 404


# Direct handler unit test -----------------------------------------------------


async def test_handler_stop_signal_persists_stopped_and_clears(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Pre-seed a stop request, then drive `stream_and_persist` directly.

    Asserts the handler honors the in-process stop signal: the assistant row
    persists with status=stopped, the durable stream row is `stopped`, and the
    live signal is cleared afterwards.
    """
    from app.providers.factory import build_provider
    from app.providers.tiers import get_binding
    from app.streaming.handler import stream_and_persist

    binding = get_binding("smart")
    assert binding is not None

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
        stream = await streams_repo.create_stream(session, conversation_id=convo.id)
        await session.commit()
        user_id = user.id
        conv_id = convo.id
        stream_id = stream.id

    # Request stop BEFORE invoking the handler so its first poll fires the
    # stop-path teardown. The stub request is never disconnected — the stop
    # signal is what triggers teardown here.
    request_stop(stream_id)

    class _StubRequest:
        async def is_disconnected(self) -> bool:
            return False

    async with session_factory() as session:
        provider = build_provider()
        gen = stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=provider,
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
        async for _ in gen:
            pass

    async with session_factory() as session:
        assistant = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        assert assistant.status == "stopped"

        stream_row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        assert stream_row.status == "stopped"

    # The handler clears the live signal once the turn is torn down.
    assert is_stop_requested(stream_id) is False


class _BlockingProvider:
    """Provider that emits one delta then blocks forever.

    Lets the test cancel the consuming task while `stream_and_persist` is
    parked on `queue.get()` mid-stream — exercising the handler's hard-cancel
    (`asyncio.CancelledError`) cleanup branch.
    """

    def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[object] | None = None,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
        web_search: bool = False,
        supports_vision: bool = True,
        response_format: object | None = None,
        system_prefix: str | None = None,
        tools: list[object] | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text="partial")
            # Never terminate — the consumer task gets cancelled while parked.
            await asyncio.Event().wait()

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


async def test_handler_hard_cancel_closes_stream_and_clears_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A hard `CancelledError` mid-stream propagates, but the handler closes out
    the durable `stream` row as `stopped` and clears the live stop signal first.

    Mirrors worker shutdown / deploy / ASGI task cancel: the consuming task is
    cancelled while `stream_and_persist` is parked mid-iteration. Driving real
    cancellation through httpx is infeasible (same reason as the xfail in
    `tests/test_messages_stream.py`), so we cancel a task wrapping the consume
    loop directly.
    """
    from app.providers.tiers import get_binding
    from app.streaming.handler import stream_and_persist

    binding = get_binding("smart")
    assert binding is not None

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
        stream = await streams_repo.create_stream(session, conversation_id=convo.id)
        await session.commit()
        user_id = user.id
        conv_id = convo.id
        stream_id = stream.id

    class _StubRequest:
        async def is_disconnected(self) -> bool:
            return False

    started = asyncio.Event()

    async def _consume() -> None:
        async with session_factory() as session:
            gen = stream_and_persist(
                request=_StubRequest(),  # type: ignore[arg-type]
                db=session,
                provider=_BlockingProvider(),  # type: ignore[arg-type]
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
            async for _ in gen:
                # Signal once we've received the first wire event so the test
                # cancels only after the generator is actively iterating.
                started.set()

    task = asyncio.create_task(_consume())
    await asyncio.wait_for(started.wait(), timeout=5.0)
    # Give the generator a moment to park on the queue mid-stream.
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # The durable stream row was closed out (not left `active`).
    async with session_factory() as session:
        stream_row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        assert stream_row.status == "stopped"

    # The live stop signal does not leak after a hard cancel.
    assert is_stop_requested(stream_id) is False
