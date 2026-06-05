"""Citation transparency contract tests (D24, PRD 07 §4.3 / §6.4).

Source-side of the transparency contract:

- A turn is GROUNDED iff it carries a non-empty sources list. When web search
  was effective but ZERO usable sources resolved, the turn persists + emits an
  empty `sources` part/frame with `requested=True` so the FE can mark it
  "Answered without live sources" (honesty rule) instead of letting an
  ungrounded answer look cited.
- Each source carries a `provenance` origin (default `web`).
- `requested` + `provenance` round-trip through reload (GET conversation),
  idempotent replay, and the public-by-link share.

Uses the deterministic fake provider + fake search backend (conftest defaults
PROVIDER_BACKEND=fake / SEARCH_BACKEND=fake). The zero-sources case overrides
the fake search backend to return `[]`.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.search.fake as fake_search
from app.db.models import Conversation, Message, User

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


def _parse_sse(response_text: str) -> list[tuple[str, dict[str, object]]]:
    normalized = response_text.replace("\r\n", "\n").replace("\r", "\n")
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


async def _collect_sse(
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return _parse_sse("".join(chunks))


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


async def _assistant_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> Message:
    async with session_factory() as session:
        return (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalar_one()


# Ungrounded (zero usable sources) ---------------------------------------------


async def test_web_search_zero_sources_marks_ungrounded(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """web search effective but ZERO sources -> empty `sources` part/frame with
    `requested=True` (the ungrounded honesty marker), surviving reload."""

    async def _empty_search(self, query: str, *, max_results: int = 5):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(fake_search.FakeSearchProvider, "search", _empty_search)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            "webSearch": True,
        },
    )

    # A `sources` frame is emitted with empty items + requested:true so the live
    # turn is visibly ungrounded rather than silently cited.
    sources_frames = [p for n, p in frames if n == "sources"]
    assert sources_frames, "expected a sources frame even with zero sources"
    last_sources = sources_frames[-1]
    assert last_sources["items"] == []
    assert last_sources["requested"] is True

    # Persisted assistant carries the empty, requested sources part.
    asst = await _assistant_row(session_factory)
    sources_part = next(p for p in asst.parts if p["type"] == "sources")
    assert sources_part["items"] == []
    assert sources_part["requested"] is True

    # Reload (GET conversation) round-trips the ungrounded marker.
    body = (await client.get(f"/api/conversations/{conv_id}")).json()
    asst_msg = next(m for m in body["messages"] if m["role"] == "assistant")
    sources_wire = next(p for p in asst_msg["parts"] if p["type"] == "sources")
    assert sources_wire["items"] == []
    assert sources_wire["requested"] is True


async def test_web_search_no_sources_event_synthesizes_ungrounded(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider emits NO `Sources` event at all but web search was effective ->
    the handler's done-path synthesizes the empty `requested=True` sources
    part/frame (distinct from the provider-emitted `Sources([])` path)."""
    from app.providers import fake as fake_provider
    from app.providers.protocol import Sources

    original_stream = fake_provider.FakeProvider.stream

    async def _stream_without_sources(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        async for event in original_stream(self, *args, **kwargs):
            if isinstance(event, Sources):
                continue
            yield event

    monkeypatch.setattr(fake_provider.FakeProvider, "stream", _stream_without_sources)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            "webSearch": True,
        },
    )

    sources_frames = [p for n, p in frames if n == "sources"]
    assert sources_frames, "expected a synthesized sources frame with no provider event"
    assert sources_frames[-1]["items"] == []
    assert sources_frames[-1]["requested"] is True

    asst = await _assistant_row(session_factory)
    sources_part = next(p for p in asst.parts if p["type"] == "sources")
    assert sources_part["items"] == []
    assert sources_part["requested"] is True


# Grounded (provenance + requested) --------------------------------------------


async def test_web_search_grounded_carries_provenance_and_requested(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A grounded turn persists items with provenance=web + requested=true, and
    both survive reload (GET conversation)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            "webSearch": True,
        },
    )

    # Live `sources` frame: grounded items, each tagged provenance=web, requested.
    sources_payload = next(p for n, p in frames if n == "sources")
    items = sources_payload["items"]
    assert [it["id"] for it in items] == [1, 2, 3]
    assert all(it["provenance"] == "web" for it in items)
    assert sources_payload["requested"] is True

    # Persisted part keeps provenance + requested.
    asst = await _assistant_row(session_factory)
    sources_part = next(p for p in asst.parts if p["type"] == "sources")
    assert sources_part["requested"] is True
    assert all(it["provenance"] == "web" for it in sources_part["items"])

    # Reload round-trips provenance + requested through the wire schema.
    body = (await client.get(f"/api/conversations/{conv_id}")).json()
    asst_msg = next(m for m in body["messages"] if m["role"] == "assistant")
    sources_wire = next(p for p in asst_msg["parts"] if p["type"] == "sources")
    assert sources_wire["requested"] is True
    assert all(it["provenance"] == "web" for it in sources_wire["items"])


# Public share asymmetry -------------------------------------------------------


async def test_web_sources_retained_on_public_share(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A web source's title/url/domain/snippet + provenance + requested are
    RETAINED on the public-by-link share (model-identity-class data, not cost)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            "webSearch": True,
        },
    )

    token = (
        await client.post(f"/api/conversations/{conv_id}/share")
    ).json()["shareToken"]
    public = await client.get(f"/api/share/{token}")
    assert public.status_code == 200, public.text

    asst_msg = next(m for m in public.json()["messages"] if m["role"] == "assistant")
    sources_wire = next(p for p in asst_msg["parts"] if p["type"] == "sources")
    assert sources_wire["requested"] is True
    items = sources_wire["items"]
    assert [it["id"] for it in items] == [1, 2, 3]
    for it in items:
        # Web-source identity data is retained on the public surface.
        assert it["provenance"] == "web"
        assert isinstance(it["title"], str) and it["title"]
        assert isinstance(it["url"], str) and it["url"]
        assert isinstance(it["domain"], str) and it["domain"]
        assert isinstance(it["snippet"], str) and it["snippet"]

    # ...but cost/token data is structurally absent from the public surface.
    assert "costUsd" not in asst_msg
    assert "breakdown" not in (asst_msg.get("attribution") or {})
