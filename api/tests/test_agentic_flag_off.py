"""Agentic flag-off byte-identity invariant.

The critical safety property of agentic mode: when `AGENTIC_ENABLED` is off, an
`agenticMode` on the send request is IGNORED entirely — the streaming turn is
byte-for-byte the pre-agentic behavior. These tests pin that against both
config shapes a flag-off server can take (tools on, tools off): a request
carrying `agenticMode` produces the same SSE frame sequence + answer as one
without it, never emits the agentic `subagent_*` / `run_cost` frames, and never
persists a `subagent` part or a `subagentId`-tagged part.

Reuses the per-test env-rebuild pattern from `test_tool_loop_approval.py`.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.session import get_db

pytestmark = pytest.mark.asyncio


# Fixtures ---------------------------------------------------------------------


@pytest.fixture
def tools_on_agentic_off_env() -> Iterator[None]:
    """Tools ON, agentic OFF — the orchestrator must stay dormant."""
    prior_tools = os.environ.get("TOOLS_ENABLED")
    prior_agentic = os.environ.get("AGENTIC_ENABLED")
    os.environ["TOOLS_ENABLED"] = "true"
    os.environ.pop("AGENTIC_ENABLED", None)
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior_tools is None:
            os.environ.pop("TOOLS_ENABLED", None)
        else:
            os.environ["TOOLS_ENABLED"] = prior_tools
        if prior_agentic is not None:
            os.environ["AGENTIC_ENABLED"] = prior_agentic
        get_settings.cache_clear()


def _build_app(session_factory: async_sessionmaker[AsyncSession]):  # type: ignore[no-untyped-def]
    from fastapi import FastAPI

    from app.main import create_app
    from app.middleware.ratelimit import limiter
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

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
    return app_


@pytest.fixture
def tools_on_agentic_off_app(
    tools_on_agentic_off_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    yield _build_app(session_factory)


@pytest.fixture
async def tools_on_agentic_off_client(
    tools_on_agentic_off_app,
) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=tools_on_agentic_off_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


# Helpers ----------------------------------------------------------------------


def _parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
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


async def _current_user_id(session_factory: async_sessionmaker[AsyncSession]) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _load_messages(
    session_factory: async_sessionmaker[AsyncSession], conv_id: str
) -> list[Message]:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


def _names(frames: list[tuple[str, dict[str, object]]]) -> list[str]:
    return [name for name, _ in frames]


def _answer(frames: list[tuple[str, dict[str, object]]]) -> str:
    return "".join(
        str(d.get("text", "")) for n, d in frames if n == "answer_delta"
    )


_AGENTIC_FRAMES = {"subagent_started", "subagent_done", "run_cost"}


def _has_subagent_tag(parts: object) -> bool:
    if not isinstance(parts, list):
        return False
    return any(
        isinstance(p, dict) and ("subagentId" in p or p.get("type") == "subagent")
        for p in parts
    )


# Tests ------------------------------------------------------------------------


async def test_agentic_mode_ignored_when_flag_off_tools_on(
    tools_on_agentic_off_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = tools_on_agentic_off_client
    assert get_settings().agentic_enabled is False
    assert get_settings().tools_enabled is True

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)

    baseline_conv = await _seed_conversation(session_factory, user_id=user_id)
    agentic_conv = await _seed_conversation(session_factory, user_id=user_id)

    baseline = await _collect_sse(
        client,
        f"/api/conversations/{baseline_conv}/messages",
        {"clientMessageId": "10000000-0000-0000-0000-000000000001",
         "tierId": "smart", "text": "agentic flag-off parity"},
    )
    agentic = await _collect_sse(
        client,
        f"/api/conversations/{agentic_conv}/messages",
        {"clientMessageId": "10000000-0000-0000-0000-000000000002",
         "tierId": "smart", "text": "agentic flag-off parity",
         "agenticMode": "deep_research"},
    )

    # Identical frame-name sequence and answer text: the mode was ignored.
    assert _names(baseline) == _names(agentic)
    assert _answer(baseline) == _answer(agentic)
    # No agentic frames in either stream.
    assert _AGENTIC_FRAMES.isdisjoint(set(_names(agentic)))
    assert _AGENTIC_FRAMES.isdisjoint(set(_names(baseline)))
    assert _names(agentic)[-1] == "terminal"
    assert agentic[-1][1]["status"] == "done"

    # No subagent part / subagentId tag persisted on the agentic-mode turn.
    msgs = await _load_messages(session_factory, agentic_conv)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert not _has_subagent_tag(assistant[0].parts)


async def test_agentic_mode_ignored_when_flag_off_tools_off(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The default fixtures run with TOOLS_ENABLED + AGENTIC_ENABLED both off.
    assert get_settings().agentic_enabled is False
    assert get_settings().tools_enabled is False

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "20000000-0000-0000-0000-000000000001",
         "tierId": "smart", "text": "hello", "agenticMode": "single"},
    )
    names = _names(frames)
    assert _AGENTIC_FRAMES.isdisjoint(set(names))
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    assert _answer(frames)  # a non-empty normal answer streamed

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert not _has_subagent_tag(assistant[0].parts)
