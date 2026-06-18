"""Transparent long-term memory v1 tests (D19).

Covers:
- CRUD on `/api/account/memory` (list / add / edit / delete), caller-scoped.
- Audit events emitted for each mutation (`memory.fact_added` / `_edited` /
  `_deleted`).
- Ownership isolation: a forged id can't edit/delete another user's fact (404).
- Opt-in gating: facts are injected into a turn ONLY when `memoryEnabled` is on.
- Memory off ⇒ no injection, no `memoryApplied` on the attribution.
- Temporary turns skip injection even when memory is enabled.
- The injected-fact count rides on the assistant attribution + persists.
- The account export includes the caller's memory ledger.

The injection tests use a capture provider (mirroring
`test_custom_instructions_are_provider_only`) so we can assert the exact
`user_text` the provider saw.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, Conversation, MemoryFact, Message, User
from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDone,
    UsageUpdate,
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
) -> str:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


def _prefs_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "defaultTierId": "smart",
        "temporaryByDefault": False,
        "trainingOptIn": False,
        "sendOnEnter": True,
        "autoExpandReasoning": False,
        "telemetryEnabled": True,
        "customInstructions": "",
        "retentionDays": None,
    }
    body.update(overrides)
    return body


async def _audit_types(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).order_by(AuditEvent.created_at.asc())
            )
        ).scalars().all()
        return [r.event_type for r in rows]


class _CaptureProvider:
    """Records the `user_text` + `system_prefix` it streams so tests can assert
    prompt assembly (memory rides the cache-stable system prefix, T20)."""

    def __init__(
        self,
        sink: list[str],
        prefix_sink: list[str | None] | None = None,
    ) -> None:
        self._sink = sink
        self._prefix_sink = prefix_sink

    async def stream(
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
        self._sink.append(user_text)
        if self._prefix_sink is not None:
            self._prefix_sink.append(system_prefix)
        yield ReasoningDone()
        yield AnswerDelta(text="ok")
        yield Complete(
            usage=UsageUpdate(
                input_tokens=10,
                output_tokens=2,
                reasoning_tokens=0,
                cached_input_tokens=0,
            )
        )

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
        system_prefix: str | None = None,
    ) -> str:
        return "Memory Test"


async def _collect_sse(
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
    normalized = "".join(chunks).replace("\r\n", "\n").replace("\r", "\n")
    frames: list[tuple[str, dict[str, object]]] = []
    for chunk in normalized.split("\n\n"):
        if not chunk.strip():
            continue
        event_name: str | None = None
        data_payload: str | None = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                fragment = line[len("data:") :].strip()
                data_payload = fragment if data_payload is None else data_payload + fragment
        if event_name is None or data_payload is None:
            continue
        try:
            parsed = json.loads(data_payload)
        except json.JSONDecodeError:
            parsed = {}
        frames.append((event_name, parsed))
    return frames


# CRUD -------------------------------------------------------------------------


async def test_memory_crud_lifecycle(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # List is empty initially.
    listed = await client.get("/api/account/memory")
    assert listed.status_code == 200
    assert listed.json() == []

    # Add a fact.
    created = await client.post(
        "/api/account/memory", json={"content": "  I prefer metric units.  "}
    )
    assert created.status_code == 201
    fact = created.json()
    assert fact["content"] == "I prefer metric units."  # trimmed
    assert fact["source"] == "manual"
    assert fact["sourceConversationId"] is None
    fact_id = fact["id"]

    # List now returns it.
    listed = await client.get("/api/account/memory")
    assert [f["id"] for f in listed.json()] == [fact_id]

    # Edit it.
    edited = await client.patch(
        f"/api/account/memory/{fact_id}", json={"content": "I prefer imperial units."}
    )
    assert edited.status_code == 200
    assert edited.json()["content"] == "I prefer imperial units."

    # Delete it.
    deleted = await client.delete(f"/api/account/memory/{fact_id}")
    assert deleted.status_code == 204

    listed = await client.get("/api/account/memory")
    assert listed.json() == []

    # Audit trail recorded one of each.
    types = await _audit_types(session_factory)
    assert "memory.fact_added" in types
    assert "memory.fact_edited" in types
    assert "memory.fact_deleted" in types


async def test_memory_add_rejects_empty_content(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post("/api/account/memory", json={"content": "   "})
    # min_length=1 on the trimmed-by-schema content -> validation 400.
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_memory_edit_missing_fact_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.patch(
        f"/api/account/memory/{uuid4()}", json={"content": "nope"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_memory_delete_missing_fact_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.delete(f"/api/account/memory/{uuid4()}")
    assert resp.status_code == 404


async def test_memory_is_caller_scoped(
    app: object,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second user cannot read, edit, or delete the first user's facts."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/account/memory", json={"content": "User A secret fact."}
    )
    fact_id = created.json()["id"]

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        # B's list never contains A's fact.
        listed_b = await client_b.get("/api/account/memory")
        assert listed_b.json() == []
        # B cannot edit or delete A's fact (404, never 403).
        assert (
            await client_b.patch(
                f"/api/account/memory/{fact_id}", json={"content": "hijack"}
            )
        ).status_code == 404
        assert (
            await client_b.delete(f"/api/account/memory/{fact_id}")
        ).status_code == 404

    # A's fact is untouched.
    listed_a = await client.get("/api/account/memory")
    assert [f["id"] for f in listed_a.json()] == [fact_id]
    assert listed_a.json()[0]["content"] == "User A secret fact."


# Injection gating -------------------------------------------------------------


async def test_memory_injected_when_enabled(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await client.get("/api/bootstrap")
    await client.put("/api/preferences", json=_prefs_body(memoryEnabled=True))
    await client.post("/api/account/memory", json={"content": "I am a pilot."})
    await client.post("/api/account/memory", json={"content": "I live in Tokyo."})

    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    seen: list[str] = []
    seen_prefixes: list[str | None] = []
    from app.routes import conversations as conversation_routes

    monkeypatch.setattr(
        conversation_routes,
        "build_provider",
        lambda *a, **k: _CaptureProvider(seen, seen_prefixes),
    )

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "Where am I?"},
    )

    assert seen
    # Memory rides the cache-stable system prefix (T20), NOT the user turn.
    prefix = seen_prefixes[0]
    assert prefix is not None
    assert "I am a pilot." in prefix
    assert "I live in Tokyo." in prefix
    assert "<memory>" in prefix
    # The user turn stays the verbatim message.
    assert seen[0] == "Where am I?"

    # The turn-level count + fact ids ride on the attribution + persist.
    terminal = frames[-1]
    assert terminal[0] == "terminal"
    attribution = terminal[1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["memoryApplied"] == 2
    assert isinstance(attribution["memoryFactIds"], list)
    assert len(attribution["memoryFactIds"]) == 2

    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        assert asst.attribution is not None
        assert asst.attribution["memoryApplied"] == 2
        assert len(asst.attribution["memoryFactIds"]) == 2


async def test_memory_not_injected_when_disabled(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await client.get("/api/bootstrap")
    # memoryEnabled defaults to False; add a fact anyway.
    await client.put("/api/preferences", json=_prefs_body(memoryEnabled=False))
    await client.post("/api/account/memory", json={"content": "I am a pilot."})

    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    seen: list[str] = []
    seen_prefixes: list[str | None] = []
    from app.routes import conversations as conversation_routes

    monkeypatch.setattr(
        conversation_routes,
        "build_provider",
        lambda *a, **k: _CaptureProvider(seen, seen_prefixes),
    )

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "Where am I?"},
    )

    assert seen
    prompt = seen[0]
    assert prompt == "Where am I?"  # byte-for-byte the pre-memory prompt
    # Memory off ⇒ no memory block, but the datetime block always leads the
    # prefix, so it is non-None and carries a UTC marker without a <memory> tag.
    prefix = seen_prefixes[0]
    assert prefix is not None
    assert "UTC" in prefix
    assert "<memory>" not in prefix

    # No `memoryApplied` on the wire (exclude_none strips the 0/None).
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert "memoryApplied" not in attribution
    assert "memoryFactIds" not in attribution


async def test_memory_not_injected_for_temporary_turn(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with memory enabled, a temporary chat skips injection."""
    await client.get("/api/bootstrap")
    await client.put("/api/preferences", json=_prefs_body(memoryEnabled=True))
    await client.post("/api/account/memory", json={"content": "I am a pilot."})

    seen: list[str] = []
    seen_prefixes: list[str | None] = []
    from app.routes import conversations as conversation_routes

    monkeypatch.setattr(
        conversation_routes,
        "build_provider",
        lambda *a, **k: _CaptureProvider(seen, seen_prefixes),
    )

    # Create a temporary conversation via the API so `is_temporary` is set.
    created = await client.post(
        "/api/conversations", json={"selectedTierId": "smart", "isTemporary": True}
    )
    assert created.status_code == 201
    conv_id = created.json()["id"]

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "Where am I?"},
    )

    assert seen
    assert seen[0] == "Where am I?"
    # Temporary turn skips memory injection, but the datetime block always leads
    # the prefix, so it is non-None with a UTC marker and no <memory> tag.
    prefix = seen_prefixes[0]
    assert prefix is not None
    assert "UTC" in prefix
    assert "<memory>" not in prefix
    attribution = frames[-1][1]["attribution"]
    assert "memoryApplied" not in attribution
    assert "memoryFactIds" not in attribution


# Export -----------------------------------------------------------------------


async def test_export_includes_memory_facts(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/account/memory", json={"content": "Export me."})

    resp = await client.get("/api/account/export")
    assert resp.status_code == 200
    payload = resp.json()
    assert "memoryFacts" in payload
    contents = [f["content"] for f in payload["memoryFacts"]]
    assert "Export me." in contents


async def test_delete_account_erases_memory_facts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/account/memory", json={"content": "Erase me."})

    async with session_factory() as session:
        before = (
            await session.execute(select(MemoryFact))
        ).scalars().all()
        assert len(before) == 1
        user = (await session.execute(select(User))).scalar_one()
        confirmation = user.email or "DELETE"

    resp = await client.request(
        "DELETE", "/api/account", json={"confirmation": confirmation}
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        after = (await session.execute(select(MemoryFact))).scalars().all()
        assert after == []
