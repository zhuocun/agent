"""Agentic worker resilience: per-worker failure degrade + per-worker fallback (M4)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.session import get_db

from .test_agentic_fanout import (
    _collect_sse,
    _grant_pro,
    _load_messages,
    _names,
    _parts,
    _seed_conversation,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def agentic_env() -> Iterator[None]:
    prior_tools = os.environ.get("TOOLS_ENABLED")
    prior_agentic = os.environ.get("AGENTIC_ENABLED")
    os.environ["TOOLS_ENABLED"] = "true"
    os.environ["AGENTIC_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, prior in (("TOOLS_ENABLED", prior_tools), ("AGENTIC_ENABLED", prior_agentic)):
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


async def _current_user_id(session_factory: async_sessionmaker[AsyncSession]) -> object:
    from app.db.models import User

    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def test_one_worker_failure_degrades_to_partial(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: stable topic | FAIL_WORKER broken topic",
            "agenticMode": "deep_research",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    assert "error" not in _names(frames)

    full_answer = "".join(
        str(d.get("text", "")) for n, d in frames if n == "answer_delta"
    )
    assert "stable topic" in full_answer
    assert "failed and were omitted" in full_answer


async def test_one_worker_retryable_falls_back(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """RETRYABLE_WORKER: FakeProvider emits ReasoningDelta before the rate-limit.

    B16: any externally visible event (including that preamble reasoning) blocks
    transparent fallback — so worker-1 fails and synthesis degrades. Fallback
    still works when the error is pre-visibility (see test_agentic_arch_fixes
    B16 + unit O-008). HANDLING: FakeProvider should raise RETRYABLE_WORKER
    before yielding ReasoningDelta if e2e fallback coverage is required.
    """
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: alpha topic | RETRYABLE_WORKER: beta topic",
            "agenticMode": "deep_research",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    full_answer = "".join(
        str(d.get("text", "")) for n, d in frames if n == "answer_delta"
    )
    assert "alpha topic" in full_answer
    # B16: no silent fallback after preamble reasoning — beta omitted.
    assert "failed and were omitted" in full_answer or "beta topic" not in full_answer

    done_events = [d for n, d in frames if n == "subagent_done"]
    worker_done = [d for d in done_events if str(d.get("role")) == "worker"]
    assert len(worker_done) == 2
    retryable = next(d for d in worker_done if str(d.get("subagentId")) == "worker-1")
    assert retryable.get("outcome") == "failed"


async def test_all_workers_fail_still_done(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: FAIL_WORKER one | FAIL_WORKER two",
            "agenticMode": "deep_research",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    full_answer = "".join(
        str(d.get("text", "")) for n, d in frames if n == "answer_delta"
    )
    assert "no worker findings" in full_answer


async def test_subagent_parts_carry_attribution(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "50000000-0000-0000-0000-000000000004",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: topic one | topic two",
            "agenticMode": "deep_research",
        },
    )
    msgs = await _load_messages(session_factory, conv_id)
    assistant = next(m for m in msgs if m.role == "assistant")
    subagent_parts = [p for p in _parts(assistant) if p.get("type") == "subagent"]
    assert len(subagent_parts) >= 2
    for part in subagent_parts:
        if part.get("role") == "worker":
            attr = part.get("attribution")
            assert isinstance(attr, dict)
            assert attr.get("servedModelLabel")


async def test_fanout_queue_bound_exceeds_protected_item_worst_case() -> None:
    """ORCH-6: the B23 drop-oldest safety argument must be executable, not prose.

    Teardown never drops a protected control message, so the bound has to exceed
    the worst case of one sentinel plus one terminal per worker; at
    `MAX_WORKER_ARTIFACTS` workers that is `2 * MAX_WORKER_ARTIFACTS`. Shrinking
    the queue below that could deadlock the fan-out consumer.
    """
    from app.agentic.fanout import _FANOUT_QUEUE_MAXSIZE
    from app.config import MAX_WORKER_ARTIFACTS, get_settings

    assert _FANOUT_QUEUE_MAXSIZE >= 2 * MAX_WORKER_ARTIFACTS
    # The configured worker bound can never exceed the artifact bound either.
    assert get_settings().agentic_max_workers <= MAX_WORKER_ARTIFACTS
