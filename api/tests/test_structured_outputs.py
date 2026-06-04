"""Structured-outputs (JSON mode) end-to-end tests against the fake provider.

Exercises the LOCKED wire contract: `responseFormat` on the send request, and
the additive `outputFormat` / `outputValid` fields on the terminal attribution.
The fake provider emits a deterministic JSON answer when a `response_format` is
requested (`{"ok": true, "items": [1, 2, 3]}`, or non-JSON for a `BADJSON:`
prompt), so the handler's boundary validation has something to parse/validate.

Reuses the SSE-parsing + seeding helpers from `test_messages_stream` so the
parsing logic stays single-sourced.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Message

from .test_messages_stream import (
    _collect_sse,
    _current_user_id,
    _seed_conversation,
)

pytestmark = pytest.mark.asyncio


async def _setup_conversation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    return await _seed_conversation(session_factory, user_id=user_id)


async def _assistant_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    async with session_factory() as session:
        rows = (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalars().all()
        assert len(rows) == 1
        text_parts = [p["text"] for p in rows[0].parts if p["type"] == "text"]
        return "".join(text_parts)


async def test_json_object_turn_valid(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """json_object turn → attribution outputFormat=json_object, outputValid=true."""
    conv_id = await _setup_conversation(client, session_factory)
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "give me json",
            "responseFormat": {"type": "json_object"},
        },
    )
    terminal = frames[-1][1]
    assert terminal["status"] == "done"
    attribution = terminal["attribution"]
    assert attribution["outputFormat"] == "json_object"
    assert attribution["outputValid"] is True
    # Persisted assistant text is the deterministic JSON object.
    assert await _assistant_text(session_factory) == '{"ok": true, "items": [1, 2, 3]}'


async def test_json_object_turn_invalid_is_still_done(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """BADJSON: prompt → outputValid=false, but the turn still completes `done`."""
    conv_id = await _setup_conversation(client, session_factory)
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "BADJSON: give me bad json",
            "responseFormat": {"type": "json_object"},
        },
    )
    terminal = frames[-1][1]
    # Invalid output never hard-fails the turn.
    assert terminal["status"] == "done"
    attribution = terminal["attribution"]
    assert attribution["outputFormat"] == "json_object"
    assert attribution["outputValid"] is False
    # The raw (non-JSON) text is preserved.
    assert await _assistant_text(session_factory) == "this is not valid json"


async def test_json_schema_turn_satisfied(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """json_schema the fake output satisfies → outputValid=true."""
    conv_id = await _setup_conversation(client, session_factory)
    # `{"ok": true, "items": [1, 2, 3]}` satisfies this schema.
    schema = {
        "type": "object",
        "required": ["ok", "items"],
        "properties": {
            "ok": {"type": "boolean"},
            "items": {"type": "array", "items": {"type": "integer"}},
        },
    }
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "give me json",
            "responseFormat": {"type": "json_schema", "schema": schema},
        },
    )
    terminal = frames[-1][1]
    assert terminal["status"] == "done"
    attribution = terminal["attribution"]
    assert attribution["outputFormat"] == "json_schema"
    assert attribution["outputValid"] is True


async def test_json_schema_turn_violated(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """json_schema the fake output violates → outputValid=false, status done."""
    conv_id = await _setup_conversation(client, session_factory)
    # `{"ok": true, ...}` violates `ok: {type: string}`.
    schema = {
        "type": "object",
        "required": ["ok"],
        "properties": {"ok": {"type": "string"}},
    }
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "give me json",
            "responseFormat": {"type": "json_schema", "schema": schema},
        },
    )
    terminal = frames[-1][1]
    assert terminal["status"] == "done"
    attribution = terminal["attribution"]
    assert attribution["outputFormat"] == "json_schema"
    assert attribution["outputValid"] is False


async def test_json_schema_without_schema_is_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`responseFormat: {type: json_schema}` with NO schema → 400 INVALID_INPUT."""
    conv_id = await _setup_conversation(client, session_factory)
    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
            "responseFormat": {"type": "json_schema"},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_normal_turn_has_no_output_fields(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A turn with NO responseFormat → attribution carries no output* fields."""
    conv_id = await _setup_conversation(client, session_factory)
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hello world",
        },
    )
    terminal = frames[-1][1]
    assert terminal["status"] == "done"
    attribution = terminal["attribution"]
    # exclude_none strips both fields from the wire when unset.
    assert "outputFormat" not in attribution
    assert "outputValid" not in attribution
