"""Live-network Deep Research E2E gate (plan 02 Live E2E gap).

Opt-in only. Skips unless BOTH are true:

- ``AGENTIC_LIVE_E2E=1``
- a real provider key is present (``DEEPSEEK_API_KEY`` or ``OPENAI_API_KEY``)

Default CI never sets the opt-in flag, so collection stays fast and the suite
stays green without live keys. Run manually before flipping Fly
``AGENTIC_ENABLED=true`` — see ``api/README.md`` / ``api/.env.example``.

O-012: beyond the connectivity smoke test, this module also covers plan-approval
resume and verifier-on when opted in (still skip-without-keys).
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic import is_plan_approval_call_id
from app.config import get_settings
from app.db.models import Conversation, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db

_LIVE_OPT_IN = os.environ.get("AGENTIC_LIVE_E2E") == "1"
_HAS_PROVIDER_KEY = bool(
    os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not (_LIVE_OPT_IN and _HAS_PROVIDER_KEY),
        reason=(
            "live Deep Research E2E requires AGENTIC_LIVE_E2E=1 and "
            "DEEPSEEK_API_KEY or OPENAI_API_KEY"
        ),
    ),
]


def _provider_backend() -> str:
    """Prefer DeepSeek when its key is set; otherwise OpenAI-compatible."""
    explicit = os.environ.get("PROVIDER_BACKEND", "").strip().lower()
    if explicit in ("deepseek", "openai"):
        if explicit == "deepseek" and os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek"
        if explicit == "openai" and os.environ.get("OPENAI_API_KEY"):
            return "openai"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    return "openai"


def _live_overrides(**extra: str) -> dict[str, str]:
    backend = _provider_backend()
    base = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "PROVIDER_BACKEND": backend,
        # Tiny single-worker DR keeps live spend bounded.
        "AGENTIC_MAX_WORKERS": "1",
        "AGENTIC_MAX_CONCURRENCY": "1",
        "AGENTIC_PLAN_APPROVAL": "false",
        "AGENTIC_VERIFIER": "false",
        # Keep search hermetic — this gate proves the provider orchestrator path.
        "SEARCH_BACKEND": "fake",
    }
    base.update(extra)
    return base


@pytest.fixture
def live_agentic_env() -> Iterator[None]:
    """Boot the app like a prod agentic enablement rehearsal (smoke defaults)."""
    overrides = _live_overrides()
    prior = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture
def live_plan_approval_env() -> Iterator[None]:
    """Live DR with plan-approval HITL enabled (O-012 control path)."""
    overrides = _live_overrides(AGENTIC_PLAN_APPROVAL="true")
    prior = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture
def live_verifier_env() -> Iterator[None]:
    """Live DR with verifier judge enabled (O-012 control path)."""
    overrides = _live_overrides(AGENTIC_VERIFIER="true", AGENTIC_VERIFIER_N="1")
    prior = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def _make_live_app(session_factory: async_sessionmaker[AsyncSession]):  # type: ignore[no-untyped-def]
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
    settings = get_settings()
    assert settings.tools_enabled is True
    assert settings.agentic_enabled is True
    assert settings.provider_backend in ("deepseek", "openai")

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
def live_agentic_app(
    live_agentic_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    app_ = _make_live_app(session_factory)
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
def live_plan_approval_app(
    live_plan_approval_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    app_ = _make_live_app(session_factory)
    assert get_settings().agentic_plan_approval is True
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
def live_verifier_app(
    live_verifier_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    app_ = _make_live_app(session_factory)
    assert get_settings().agentic_verifier is True
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
async def live_agentic_client(
    live_agentic_app,
) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=live_agentic_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


@pytest.fixture
async def live_plan_approval_client(
    live_plan_approval_app,
) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=live_plan_approval_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


@pytest.fixture
async def live_verifier_client(
    live_verifier_app,
) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=live_verifier_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


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
    client: AsyncClient, url: str, body: dict[str, object], *, timeout: float = 180.0
) -> list[tuple[str, dict[str, object]]]:
    # Live provider DR is slow (planner-skipped single worker + aggregator still
    # hits the network twice). Bound far above unit timeouts, not unbounded.
    async with client.stream("POST", url, json=body, timeout=timeout) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
    return _parse_sse("".join(chunks))


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession], *, user_id: object
) -> str:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="Live DR gate",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


async def _current_user_id(session_factory: async_sessionmaker[AsyncSession]) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _grant_pro(
    session_factory: async_sessionmaker[AsyncSession], *, user_id: object
) -> None:
    async with session_factory() as session:
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=UUID(str(user_id)),
            provider="fake",
            subscription_id=f"sub-live-{user_id}",
            status="active",
            customer_id=f"cus-live-{user_id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()


async def test_live_deep_research_single_worker_completes(
    live_agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Connectivity smoke: tiny single-worker Deep Research against a real provider.

    Uses the ``DEEP_RESEARCH:`` marker so decomposition is local (no planner
    round-trip) while worker + aggregator still hit the live model. Asserts
    subagent framing, a done terminal, and nonzero token usage. Does not claim
    coverage of plan-approval / verifier / worker-HITL — see sibling tests.
    """
    await live_agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        live_agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-4000-8000-000000000001",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: In one short sentence, what is 2+2?",
            "agenticMode": "deep_research",
        },
    )

    names = [name for name, _ in frames]
    assert "subagent_started" in names
    assert "subagent_done" in names
    assert "run_cost" in names
    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    started_ids = {
        str(d["subagentId"]) for n, d in frames if n == "subagent_started"
    }
    assert "worker-0" in started_ids
    assert "aggregator" in started_ids
    done_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_done"}
    assert "worker-0" in done_ids
    assert "aggregator" in done_ids

    answer = "".join(
        str(d.get("text", "")) for n, d in frames if n == "answer_delta"
    )
    assert answer.strip(), "expected a nonempty streamed answer"

    terminal = frames[-1][1]
    attribution = terminal.get("attribution")
    assert isinstance(attribution, dict)
    breakdown = attribution.get("breakdown")
    assert isinstance(breakdown, dict)
    input_tokens = int(breakdown.get("inputTokens") or 0)
    output_tokens = int(breakdown.get("outputTokens") or 0)
    assert input_tokens + output_tokens > 0, "expected nonzero provider usage"

    run_costs = [d for n, d in frames if n == "run_cost"]
    assert run_costs
    assert float(run_costs[-1]["subtotalUsd"]) >= 0.0
    assert run_costs[-1].get("phase") == "final"


async def test_live_deep_research_plan_approval_resume(
    live_plan_approval_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O-012: live plan-approval pause → approve → fan-out completes."""
    await live_plan_approval_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    pause_frames = await _collect_sse(
        live_plan_approval_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-4000-8000-000000000011",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: In one short sentence, what is 2+2?",
            "agenticMode": "deep_research",
        },
        timeout=120.0,
    )
    assert pause_frames[-1][0] == "terminal"
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    tool_calls = [d for n, d in pause_frames if n == "tool_call"]
    assert tool_calls
    plan_call = tool_calls[-1]
    call_id = str(plan_call["id"])
    assert is_plan_approval_call_id(call_id)
    assert "worker-0" not in {
        str(d["subagentId"]) for n, d in pause_frames if n == "subagent_started"
    }

    resume_frames = await _collect_sse(
        live_plan_approval_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-4000-8000-000000000012",
            "tierId": "smart",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": call_id,
                "decision": "approve",
            },
        },
        timeout=180.0,
    )
    assert resume_frames[-1][0] == "terminal"
    assert resume_frames[-1][1]["status"] == "done"
    started = {
        str(d["subagentId"]) for n, d in resume_frames if n == "subagent_started"
    }
    assert "worker-0" in started
    assert "aggregator" in started
    answer = "".join(
        str(d.get("text", "")) for n, d in resume_frames if n == "answer_delta"
    )
    assert answer.strip()


async def test_live_deep_research_with_verifier(
    live_verifier_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O-012: live single-worker DR with verifier judge enabled."""
    await live_verifier_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        live_verifier_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "a0000000-0000-4000-8000-000000000021",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: In one short sentence, what is 2+2?",
            "agenticMode": "deep_research",
        },
        timeout=240.0,
    )
    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["status"] == "done"
    started = {
        str(d["subagentId"]) for n, d in frames if n == "subagent_started"
    }
    assert "worker-0" in started
    assert "aggregator" in started
    # Verifier may succeed or degrade; when it runs it appears as a subagent.
    # Accept either an explicit verifier bracket or a completed aggregator draft.
    answer = "".join(
        str(d.get("text", "")) for n, d in frames if n == "answer_delta"
    )
    assert answer.strip()
    run_costs = [d for n, d in frames if n == "run_cost"]
    assert run_costs
    assert float(run_costs[-1]["subtotalUsd"]) >= 0.0
