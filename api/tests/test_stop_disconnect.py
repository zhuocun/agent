"""Stop over the real SSE transport: a client disconnect terminalizes the turn.

The Stop button aborts the fetch (and fires `POST /stop`). sse-starlette answers
the disconnect by cancelling its task group, and that cancel used to land inside
`stream_and_persist`, whose cleanup awaits were cancelled by the same scope: no
stopped partial was persisted and the `stream` row stayed `active`, so every
later send got 409 STREAM_IN_PROGRESS.

httpx's ASGITransport cannot disconnect mid-stream, so these tests drive the
app at the ASGI level with a `receive` that delivers `http.disconnect` after a
few answer deltas have gone out — the same message uvicorn delivers.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Message, Stream


async def _start_conversation(client: AsyncClient) -> str:
    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    created = await client.post("/api/conversations", json={"selectedTierId": "fast"})
    assert created.status_code in (200, 201), created.text
    return str(created.json()["id"])


def _cookie_header(client: AsyncClient) -> bytes:
    return "; ".join(f"{k}={v}" for k, v in client.cookies.items()).encode()


async def _send_then_disconnect(
    app: FastAPI,
    client: AsyncClient,
    conversation_id: str,
    *,
    deltas_before_disconnect: int,
    before_disconnect: Any = None,
) -> asyncio.Task[None]:
    """Start a SLOW turn over raw ASGI; disconnect after N answer deltas.

    Returns the ASGI call's task once the disconnect has been delivered, so the
    caller decides whether to wait for the teardown or race it.
    """
    body = json.dumps(
        {
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "SLOW: a long story to stop part way",
        }
    ).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": f"/api/conversations/{conversation_id}/messages",
        "raw_path": f"/api/conversations/{conversation_id}/messages".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"cookie", _cookie_header(client)),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    disconnect = asyncio.Event()
    body_sent = False
    deltas = 0

    async def receive() -> dict[str, Any]:
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal deltas
        if message["type"] == "http.response.body":
            deltas += message.get("body", b"").count(b"event: answer_delta")
            if deltas >= deltas_before_disconnect and not disconnect.is_set():
                if before_disconnect is not None:
                    await before_disconnect()
                disconnect.set()

    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(disconnect.wait(), timeout=10)
    return task


async def _stream_rows(
    session_factory: async_sessionmaker[AsyncSession], conversation_id: str
) -> list[Stream]:
    async with session_factory() as session:
        return list(
            (
                await session.execute(
                    select(Stream).where(Stream.conversation_id == UUID(conversation_id))
                )
            ).scalars()
        )


async def test_disconnect_persists_stopped_partial_and_releases_guard(
    app: FastAPI,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conversation_id = await _start_conversation(client)
    task = await _send_then_disconnect(
        app, client, conversation_id, deltas_before_disconnect=3
    )
    await asyncio.wait_for(task, timeout=10)

    rows = await _stream_rows(session_factory, conversation_id)
    assert [row.status for row in rows] == ["stopped"]

    async with session_factory() as session:
        assistants = list(
            (
                await session.execute(
                    select(Message).where(
                        Message.conversation_id == UUID(conversation_id),
                        Message.role == "assistant",
                    )
                )
            ).scalars()
        )
    assert len(assistants) == 1
    stopped = assistants[0]
    assert stopped.status == "stopped"
    answer = "".join(
        str(part.get("text", "")) for part in stopped.parts if part.get("type") == "text"
    )
    assert answer.startswith("part 0"), stopped.parts

    # The conversation is usable again: the next send streams normally.
    again = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"clientMessageId": str(uuid4()), "tierId": "fast", "text": "hello again"},
    )
    assert again.status_code == 200, again.text
    assert "event: terminal" in again.text


async def test_send_right_after_stop_waits_for_teardown_instead_of_409(
    app: FastAPI,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The FE's Stop: `POST /stop`, abort the fetch, then the user sends again.

    The re-send races the old turn's teardown; it must wait for the stopped
    turn to release the guard rather than bounce with 409.
    """
    conversation_id = await _start_conversation(client)

    async def _post_stop() -> None:
        stopped = await client.post(f"/api/conversations/{conversation_id}/stop")
        assert stopped.status_code == 204

    task = await _send_then_disconnect(
        app,
        client,
        conversation_id,
        deltas_before_disconnect=3,
        before_disconnect=_post_stop,
    )
    # Deliberately NOT awaiting the old turn's teardown before re-sending.
    again = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"clientMessageId": str(uuid4()), "tierId": "fast", "text": "hello again"},
    )
    assert again.status_code == 200, again.text
    await asyncio.wait_for(task, timeout=10)

    statuses = sorted(row.status for row in await _stream_rows(session_factory, conversation_id))
    assert statuses == ["done", "stopped"]


class _NeverDisconnected:
    async def is_disconnected(self) -> bool:
        return False


async def test_inline_driver_is_cancelled_when_the_stop_grace_runs_out(
    monkeypatch: Any,
) -> None:
    """A handler that never reaches its disconnect poll (e.g. stuck in setup)
    must not outlive the request: past the grace it is cancelled and joined."""
    from sse_starlette import ServerSentEvent

    from app.streaming import handler as handler_mod

    cancelled = asyncio.Event()

    async def _stuck_handler(**_kwargs: Any) -> Any:
        yield ServerSentEvent(data="{}", event="submitted")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(handler_mod, "stream_and_persist", _stuck_handler)
    monkeypatch.setattr(handler_mod, "_INLINE_STOP_GRACE_SECONDS", 0.2)

    body = handler_mod.stream_inline_turn(request=_NeverDisconnected())  # type: ignore[arg-type]
    first = await body.__anext__()
    assert first.event == "submitted"
    await asyncio.wait_for(body.aclose(), timeout=5)  # the client went away

    assert cancelled.is_set()
    assert not handler_mod._INLINE_TURN_TASKS


async def test_inline_driver_is_paced_by_the_consumer(monkeypatch: Any) -> None:
    """Backpressure: the handler must not run ahead of what the client read,
    or a stopped partial could hold text the client was never sent."""
    from sse_starlette import ServerSentEvent

    from app.streaming import handler as handler_mod

    produced = 0

    async def _chatty_handler(**_kwargs: Any) -> Any:
        nonlocal produced
        for i in range(50):
            produced += 1
            yield ServerSentEvent(data=str(i), event="answer_delta")

    monkeypatch.setattr(handler_mod, "stream_and_persist", _chatty_handler)
    body = handler_mod.stream_inline_turn(request=_NeverDisconnected())  # type: ignore[arg-type]
    await body.__anext__()
    await asyncio.sleep(0.1)
    # One frame read, at most one queued and one in hand at the handler.
    assert produced <= 3
    await body.aclose()
