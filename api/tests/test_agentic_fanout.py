"""Agentic orchestrator end-to-end: single loop (M1) + deep-research fan-out (M2).

Drives the FAKE provider behind `TOOLS_ENABLED=true` AND `AGENTIC_ENABLED=true`.
Covers:
- `single` mode: one `primary` subagent, bracketed by `subagent_started` /
  `subagent_done`, a `run_cost` frame, and a subagent-grouped persisted
  transcript.
- `deep_research` mode: the planner splits a `DEEP_RESEARCH:` prompt into
  sub-questions, parallel `worker` subagents answer them, and an `aggregator`
  synthesizes the final answer — all surfaced on the wire and persisted grouped
  by subagent.
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
def agentic_env() -> Iterator[None]:
    """Turn BOTH the tool-calling and agentic flags ON for the test."""
    prior_tools = os.environ.get("TOOLS_ENABLED")
    prior_agentic = os.environ.get("AGENTIC_ENABLED")
    os.environ["TOOLS_ENABLED"] = "true"
    os.environ["AGENTIC_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, prior in (
            ("TOOLS_ENABLED", prior_tools),
            ("AGENTIC_ENABLED", prior_agentic),
        ):
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
        get_settings.cache_clear()


@pytest.fixture
def agentic_app(
    agentic_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
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
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
async def agentic_client(agentic_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=agentic_app)
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
    return "".join(str(d.get("text", "")) for n, d in frames if n == "answer_delta")


def _parts(message: Message) -> list[dict[str, object]]:
    raw = message.parts
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, dict)]


# 1. Single mode ---------------------------------------------------------------


async def test_single_mode_wraps_one_primary_subagent(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert get_settings().agentic_enabled is True

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "30000000-0000-0000-0000-000000000001",
         "tierId": "smart", "text": "explain agentic mode", "agenticMode": "single"},
    )
    names = _names(frames)
    assert "subagent_started" in names
    assert "subagent_done" in names
    assert "run_cost" in names
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    started = [d for n, d in frames if n == "subagent_started"]
    assert len(started) == 1
    assert started[0]["subagentId"] == "primary"
    assert started[0]["role"] == "primary"

    # Every content delta is tagged with the primary subagent id.
    answer_deltas = [d for n, d in frames if n == "answer_delta"]
    assert answer_deltas
    assert all(d.get("subagentId") == "primary" for d in answer_deltas)

    run_cost = next(d for n, d in frames if n == "run_cost")
    assert run_cost["capUsd"] == get_settings().agentic_run_budget_usd
    assert float(run_cost["subtotalUsd"]) >= 0.0

    # Persisted transcript opens with a `subagent` marker, then primary-tagged
    # reasoning + text.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    parts = _parts(assistant[0])
    assert parts[0]["type"] == "subagent"
    assert parts[0]["subagentId"] == "primary"
    assert parts[0]["role"] == "primary"
    types = [p["type"] for p in parts]
    assert "text" in types
    text_part = next(p for p in parts if p["type"] == "text")
    assert text_part["subagentId"] == "primary"
    assert assistant[0].status == "done"


# 2. Deep research fan-out -----------------------------------------------------


async def test_deep_research_fans_out_workers_and_aggregates(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "40000000-0000-0000-0000-000000000001",
         "tierId": "smart",
         "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
         "agenticMode": "deep_research"},
    )
    names = _names(frames)
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    assert "run_cost" in names

    started_ids = {
        str(d["subagentId"]) for n, d in frames if n == "subagent_started"
    }
    assert started_ids == {"worker-0", "worker-1", "aggregator"}
    done_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_done"}
    assert done_ids == {"worker-0", "worker-1", "aggregator"}

    # The aggregator answer synthesizes the two worker findings.
    full_answer = _answer(frames)
    assert "Synthesis of 2 findings" in full_answer
    assert "causes of inflation" in full_answer
    assert "effects on housing" in full_answer
    aggregator_answer = "".join(
        str(d.get("text", ""))
        for n, d in frames
        if n == "answer_delta" and d.get("subagentId") == "aggregator"
    )
    assert "Synthesis of 2 findings" in aggregator_answer

    # Persisted transcript carries a `subagent` marker per subagent, each with a
    # subagent-tagged text part.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    parts = _parts(assistant[0])
    marker_ids = [p["subagentId"] for p in parts if p["type"] == "subagent"]
    assert marker_ids == ["worker-0", "worker-1", "aggregator"]
    text_subagents = {p["subagentId"] for p in parts if p["type"] == "text"}
    assert text_subagents == {"worker-0", "worker-1", "aggregator"}
    assert assistant[0].status == "done"


async def test_deep_research_without_marker_runs_single_worker(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # A deep-research turn whose prompt has no `DEEP_RESEARCH:` marker still
    # produces a valid fan-out of exactly one worker + the aggregator.
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "50000000-0000-0000-0000-000000000001",
         "tierId": "smart", "text": "a single research question",
         "agenticMode": "deep_research"},
    )
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert started_ids == {"worker-0", "aggregator"}
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    assert "Synthesis of 1 findings" in _answer(frames)
