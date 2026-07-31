"""AC-04 closure: one immutable `RuntimeContext` owns every lifecycle session.

`stream_and_persist` used to open its heartbeat and its budget-reservation
release sessions from the process-wide session factory. Under test that factory
is bound to the env `DATABASE_URL`, not the per-test database the request
session is bound to, so both writes went to the wrong engine (or failed
outright) while the route test still went green — the "green tests with failed
cleanup" blind spot.

These tests drive the real send-message route against the dependency-overridden
database and assert, for done / awaiting_approval / error / stop in both the
inline and detached (resumable) shapes:

- a heartbeat actually touched the stream row in THAT database,
- the reservation release ran on that database and found the live hold,
- no reservation row survives the turn, and
- neither `stream.heartbeat.failed` nor `budget.reservation_release.failed` was
  logged.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, PlatformBudgetReservation, Stream, User
from app.db.repositories import billing as billing_repo
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_db
from app.providers.protocol import AnswerDelta, ProviderEvent
from app.providers.tiers import get_binding
from app.runtime.context import RuntimeContext, derive_session_factory
from app.streaming import handler as handler_mod
from app.streaming import replay_registry

# Probing helpers --------------------------------------------------------------


def _bind_url(db: AsyncSession) -> str:
    bind = db.bind
    url = getattr(bind, "url", None)
    return str(url) if url is not None else ""


@dataclass
class _LifecycleProbe:
    """Records which database each lifecycle session actually talked to."""

    # (engine url, whether a stream row was really touched)
    heartbeats: list[tuple[str, bool]] = field(default_factory=list)
    # (engine url, number of reservation rows visible to that session)
    releases: list[tuple[str, int]] = field(default_factory=list)
    reservations: list[bool] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _RecordingLog:
    """Proxy around the handler's stdlib logger that records warning events."""

    def __init__(self, real: Any, sink: list[str]) -> None:
        self._real = real
        self._sink = sink

    def warning(self, event: str, *args: Any, **kwargs: Any) -> None:
        self._sink.append(str(event))
        self._real.warning(event, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _install_probe(monkeypatch: pytest.MonkeyPatch) -> _LifecycleProbe:
    """Wrap the three lifecycle repo calls and force heartbeats every poll."""
    probe = _LifecycleProbe()
    real_heartbeat = streams_repo.heartbeat
    real_release = usage_repo.release_platform_budget
    real_reserve = usage_repo.reserve_platform_budget

    async def _heartbeat(db: AsyncSession, *, stream_id: Any) -> bool:
        touched = await real_heartbeat(db, stream_id=stream_id)
        probe.heartbeats.append((_bind_url(db), touched))
        return touched

    async def _release(db: AsyncSession, *, stream_id: Any) -> None:
        visible = (
            (
                await db.execute(
                    select(PlatformBudgetReservation).where(
                        PlatformBudgetReservation.stream_id == stream_id
                    )
                )
            )
            .scalars()
            .all()
        )
        probe.releases.append((_bind_url(db), len(visible)))
        await real_release(db, stream_id=stream_id)

    async def _reserve(db: AsyncSession, **kwargs: Any) -> bool:
        ok = await real_reserve(db, **kwargs)
        probe.reservations.append(ok)
        return ok

    monkeypatch.setattr(streams_repo, "heartbeat", _heartbeat)
    monkeypatch.setattr(usage_repo, "release_platform_budget", _release)
    monkeypatch.setattr(usage_repo, "reserve_platform_budget", _reserve)
    # The real interval is 60s; a turn never lives that long in a test.
    monkeypatch.setattr(handler_mod, "_STREAM_HEARTBEAT_INTERVAL_S", 0.0)
    monkeypatch.setattr(
        handler_mod, "log", _RecordingLog(handler_mod.log, probe.warnings)
    )
    return probe


# App / client harness ---------------------------------------------------------


@contextmanager
def _agentic_env(*, resumable: bool) -> Iterator[None]:
    """Tools + agentic ON (so the route holds a budget reservation)."""
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "false",
        "RESUMABLE_STREAMS_ENABLED": "true" if resumable else "false",
        # A positive operator quota is what makes the route hold (and therefore
        # have to release) a platform-budget reservation for an agentic run.
        "USAGE_BUDGET_USD": "50",
    }
    prior = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
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


@asynccontextmanager
async def _route_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
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

    app_ = create_app()

    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app_.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app_)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


async def _seed_user_and_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Grant Pro to the bootstrapped guest and open a conversation for it."""
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalars().first()
        assert user is not None, "bootstrap must have minted the anonymous user"
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=user.id,
            provider="fake",
            subscription_id=f"sub-{user.id}",
            status="active",
            customer_id=f"cus-{user.id}",
            current_period_end=None,
            event_created_at=None,
        )
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


_DEEP_RESEARCH_PROMPT = "DEEP_RESEARCH: causes of inflation | effects on housing"
_WORKER_HITL_PROMPT = (
    "DEEP_RESEARCH: TOOL_APPROVE schedule kickoff | sibling housing effects"
)


def _stub_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    make_events: Any,
) -> None:
    monkeypatch.setattr(handler_mod, "run_orchestrator", lambda **_kw: make_events())


# AC-04 route-level closure ----------------------------------------------------


@pytest.mark.parametrize("resumable", [False, True], ids=["inline", "detached"])
@pytest.mark.parametrize("outcome", ["done", "pause", "error", "stop"])
async def test_lifecycle_sessions_use_the_request_database(
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    resumable: bool,
) -> None:
    """AC-04: heartbeat + reservation release land in the overridden test DB."""
    expected_url = str(engine.url)
    probe = _install_probe(monkeypatch)

    with _agentic_env(resumable=resumable):
        async with _route_client(session_factory) as client:
            await client.get("/api/bootstrap")
            conv_id = await _seed_user_and_conversation(session_factory)

            entered = asyncio.Event()
            if outcome == "error":

                def _erroring() -> AsyncIterator[ProviderEvent]:
                    async def _gen() -> AsyncIterator[ProviderEvent]:
                        yield AnswerDelta(text="partial")
                        raise RuntimeError("orchestrator exploded")

                    return _gen()

                _stub_orchestrator(monkeypatch, _erroring)
            elif outcome == "stop":

                def _blocking() -> AsyncIterator[ProviderEvent]:
                    async def _gen() -> AsyncIterator[ProviderEvent]:
                        yield AnswerDelta(text="partial")
                        entered.set()
                        await asyncio.Event().wait()

                    return _gen()

                _stub_orchestrator(monkeypatch, _blocking)

            body = {
                "clientMessageId": str(uuid4()),
                "tierId": "smart",
                "text": (
                    _WORKER_HITL_PROMPT if outcome == "pause" else _DEEP_RESEARCH_PROMPT
                ),
                "agenticMode": "deep_research",
            }
            url = f"/api/conversations/{conv_id}/messages"

            async def _drain() -> None:
                async with client.stream("POST", url, json=body, timeout=20.0) as resp:
                    assert resp.status_code == 200, await resp.aread()
                    async for _chunk in resp.aiter_text():
                        pass

            if outcome == "stop":
                turn = asyncio.create_task(_drain())
                await asyncio.wait_for(entered.wait(), timeout=10.0)
                stop_resp = await client.post(f"/api/conversations/{conv_id}/stop")
                assert stop_resp.status_code == 204
                await asyncio.wait_for(turn, timeout=20.0)
            else:
                await asyncio.wait_for(_drain(), timeout=20.0)

    # The route really held a platform-budget reservation for this turn.
    assert probe.reservations, "the route never reserved platform budget"
    assert all(probe.reservations), probe.reservations

    # Heartbeat: at least one call touched a row, and every call ran against the
    # request-derived engine (never the process-wide one).
    assert probe.heartbeats, "the turn never heartbeated its stream"
    assert {url for url, _ in probe.heartbeats} == {expected_url}
    assert any(touched for _, touched in probe.heartbeats), probe.heartbeats

    # Release: ran on the request-derived engine AND saw the live hold there.
    assert probe.releases, "the turn never released its reservation"
    assert {url for url, _ in probe.releases} == {expected_url}
    assert any(seen > 0 for _, seen in probe.releases), probe.releases

    assert "stream.heartbeat.failed" not in probe.warnings
    assert "budget.reservation_release.failed" not in probe.warnings

    async with session_factory() as session:
        holds = (
            (await session.execute(select(PlatformBudgetReservation))).scalars().all()
        )
        assert holds == [], "a budget reservation survived the turn"
        active = (
            (
                await session.execute(
                    select(Stream).where(Stream.status == "active")
                )
            )
            .scalars()
            .all()
        )
        assert active == [], "the stream row never left `active`"


# RuntimeContext unit contracts ------------------------------------------------


async def test_runtime_context_is_frozen_and_binds_the_request_engine(
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> None:
    """The context is immutable and its factory targets the session's engine."""
    async with session_factory() as session:
        context = RuntimeContext.from_session(session)
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.session_factory = session_factory  # type: ignore[misc]
    async with context.session_factory() as fresh:
        assert _bind_url(fresh) == str(engine.url)
    assert (
        RuntimeContext.from_factory(session_factory).session_factory is session_factory
    )


async def test_derive_session_factory_falls_back_when_unbound() -> None:
    """An unbound session cannot derive an engine — fall back, never crash."""
    factory = derive_session_factory(AsyncSession())
    assert isinstance(factory, async_sessionmaker)


async def test_detached_producer_threads_the_caller_session_factory(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-04: the detached producer hands its own factory to the turn context."""
    captured: list[RuntimeContext] = []

    def _fake_stream_and_persist(**kwargs: Any) -> AsyncIterator[Any]:
        runtime = kwargs["runtime"]
        assert isinstance(runtime, RuntimeContext)
        captured.append(runtime)

        async def _gen() -> AsyncIterator[Any]:
            if False:  # pragma: no cover - typed empty async generator
                yield None

        return _gen()

    monkeypatch.setattr(handler_mod, "stream_and_persist", _fake_stream_and_persist)
    binding = get_binding("smart")
    assert binding is not None
    buffer = replay_registry.ReplayBuffer()
    await handler_mod.run_detached_producer(
        buffer=buffer,
        session_factory=session_factory,
        provider=object(),  # type: ignore[arg-type]
        binding=binding,
        requested_tier_id="smart",
        conversation_id=None,
        user_message_id=uuid4(),
        user_text="hi",
        history=[],
        is_temporary=True,
    )
    assert len(captured) == 1
    assert captured[0].session_factory is session_factory


def test_handler_has_no_process_wide_session_factory_lookup() -> None:
    """Final-gate grep as a test: no global factory lookup in the handler."""
    source = (
        Path(handler_mod.__file__).read_text(encoding="utf-8")
        if handler_mod.__file__
        else ""
    )
    assert "get_session_factory" not in source
