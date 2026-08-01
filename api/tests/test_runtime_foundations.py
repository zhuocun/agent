"""Unit-level closure for the neutral runtime primitives (AC-04, AC-02).

AC-04 closure: one immutable `RuntimeContext` owns every lifecycle session.

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

AC-02: the `CostLedger` algebra and the totality of every `RunReceipt` decoder,
tested directly rather than only through the pause/resume route (that identity
chain lives in `test_arch_review_ledger_resume.py`).

AC-07: the import direction. `app.providers`, `app.tools` and `app.agentic` used
to reach UP into `app.streaming` for the shared answer/markup policy, making the
delivery layer a dependency of the engines that feed it. The policy now lives in
`app.runtime.answer_policy` and this file asserts the direction statically; the
behavioral markup/empty/nudge/fallback coverage stays in
`test_empty_reply_fallback.py` and `test_tool_markup_sanitizer.py`, which now
exercise that one neutral module.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import importlib
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
from app.providers.protocol import AnswerDelta, ProviderEvent, UsageUpdate
from app.providers.tiers import get_binding
from app.runtime import answer_policy as answer_policy_mod
from app.runtime import run_receipt as run_receipt_mod
from app.runtime.context import RuntimeContext, derive_session_factory
from app.runtime.run_receipt import (
    CostLedger,
    PhaseReceipt,
    RunReceipt,
    UsageTotals,
    decode_run_receipt,
)
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


# AC-02 — the ledger algebra and the totality of every receipt decoder ----------


def _app_imports(path: Path) -> set[str]:
    """Every `app.*` module `path` imports, read statically (never executed)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return {name for name in imported if name.startswith("app.")}


def test_receipt_module_does_not_import_the_provider_protocol() -> None:
    """`providers.protocol.RunCost` imports `RunReceipt` as its carrier, so an
    import back the other way would close a cycle at module load."""
    assert run_receipt_mod.__file__
    imported = _app_imports(Path(run_receipt_mod.__file__))
    assert imported == set(), imported


def test_usage_totals_copies_counts_off_a_provider_usage_event() -> None:
    """The adapter seam: `UsageUpdate` crosses into the neutral module by value,
    which is what lets the module stay provider-independent."""
    totals = UsageTotals.copy_from(
        UsageUpdate(
            input_tokens=11,
            output_tokens=7,
            reasoning_tokens=3,
            cached_input_tokens=5,
            subagent_id="worker-1",
        )
    )
    assert totals == UsageTotals(
        input_tokens=11, output_tokens=7, reasoning_tokens=3, cached_input_tokens=5
    )
    # Nothing provider-shaped rides along, and a missing source is empty, not a
    # crash — `copy_from` runs on paths where usage may never have arrived.
    assert not hasattr(totals, "subagent_id")
    assert UsageTotals.copy_from(None).is_empty


def test_settle_replaces_a_provisional_sample_and_is_not_downgraded() -> None:
    """A phase's exact amount wins over its own mid-flight estimate, and a late
    `observe` for an already-settled phase cannot reintroduce the estimate."""
    ledger = CostLedger()
    ledger.observe("worker-1", role="worker", cost_usd=0.20)
    assert ledger.cumulative_cost_usd == pytest.approx(0.20)
    assert ledger.settled_cost_usd == pytest.approx(0.0)

    ledger.settle("worker-1", role="worker", cost_usd=0.05)
    assert ledger.cumulative_cost_usd == pytest.approx(0.05)
    assert ledger.settled_cost_usd == pytest.approx(0.05)

    ledger.observe("worker-1", role="worker", cost_usd=0.99)
    assert ledger.cumulative_cost_usd == pytest.approx(0.05)


def test_restore_turns_prior_spend_into_an_already_billed_floor() -> None:
    """A resume owes only its own increment: everything the prior boundary
    receipt accounted for counts toward cumulative but not toward the charge."""
    first = CostLedger()
    first.settle(
        "planner",
        role="orchestrator",
        usage=UsageTotals(input_tokens=100),
        cost_usd=0.10,
    )
    pause = first.receipt(cap_usd=1.0, boundary="pause")
    assert pause.newly_billable_cost_usd == pytest.approx(0.10)

    resumed = CostLedger.restore(pause)
    assert resumed.cumulative_cost_usd == pytest.approx(0.10)
    assert resumed.newly_billable_cost_usd == pytest.approx(0.0)
    restored_planner = resumed.phase("planner")
    assert restored_planner is not None
    assert restored_planner.already_billed is True

    resumed.settle(
        "worker-1", role="worker", usage=UsageTotals(output_tokens=40), cost_usd=0.25
    )
    final = resumed.receipt(cap_usd=1.0, boundary="final")
    assert final.cumulative_cost_usd == pytest.approx(0.35)
    assert final.already_billed_cost_usd == pytest.approx(0.10)
    assert final.newly_billable_cost_usd == pytest.approx(0.25)
    # The identity holds by construction, not by convention.
    assert final.cumulative_cost_usd == pytest.approx(
        final.already_billed_cost_usd + final.newly_billable_cost_usd
    )
    # Usage accumulates across the boundary too.
    assert final.cumulative_usage == UsageTotals(input_tokens=100, output_tokens=40)


def test_cumulative_cost_never_falls_below_the_billed_floor() -> None:
    """A checkpoint can record spend no surviving phase re-derives (the legacy
    scalar seed case). Cumulative must not shrink below it and hand the user a
    refund the run never earned."""
    ledger = CostLedger()
    ledger.hold_billed_floor(0.42)
    assert ledger.cumulative_cost_usd == pytest.approx(0.42)
    assert ledger.newly_billable_cost_usd == pytest.approx(0.0)

    ledger.settle("worker-1", role="worker", cost_usd=0.01)
    assert ledger.cumulative_cost_usd == pytest.approx(0.42)
    # The floor only ever rises.
    ledger.hold_billed_floor(0.10)
    assert ledger.already_billed_cost_usd == pytest.approx(0.42)
    # And the receipt says so: phases cannot account for the whole total here.
    receipt = ledger.receipt(boundary="final")
    assert sum(p.cost_usd for p in receipt.phases) < receipt.cumulative_cost_usd


def test_receipt_round_trips_through_its_wire_form() -> None:
    ledger = CostLedger.restore(
        RunReceipt(
            cumulative_cost_usd=0.10,
            already_billed_cost_usd=0.10,
            cumulative_usage=UsageTotals(input_tokens=9),
            phases=(PhaseReceipt(phase_id="planner", role="orchestrator", cost_usd=0.10),),
        )
    )
    ledger.settle(
        "worker-1",
        role="worker",
        usage=UsageTotals(output_tokens=4),
        cost_usd=0.25,
        outcome="failed",
    )
    original = ledger.receipt(cap_usd=2.0, confidence="estimate", boundary="stop")
    assert decode_run_receipt(original.to_wire()) == original
    # Derived, so a reader that only has the JSON still sees the charge.
    assert original.to_wire()["newlyBillableCostUsd"] == pytest.approx(0.25)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "0.37",
        42,
        [],
        {"version": 999},
        {"version": True},
        {"version": "1"},
    ],
    ids=[
        "none",
        "string",
        "number",
        "list",
        "unsupported-version",
        "bool-version",
        "string-version",
    ],
)
def test_decode_run_receipt_refuses_unusable_input(raw: object) -> None:
    """A receipt is read out of a JSON column. Unusable input reads as "no
    receipt" so the caller keeps its legacy seeds, and an unknown version is
    refused rather than reinterpreted with this build's field meanings."""
    assert decode_run_receipt(raw) is None


def test_decode_run_receipt_sanitizes_impossible_amounts() -> None:
    """Nonsense inside an otherwise-readable receipt resolves to a safe zero
    rather than raising inside a row read."""
    decoded = decode_run_receipt(
        {
            "cumulativeCostUsd": float("inf"),
            "alreadyBilledCostUsd": -5.0,
            "capUsd": True,
            "cumulativeUsage": {"inputTokens": -3, "outputTokens": True},
            "confidence": "vibes",
            "boundary": "elsewhere",
            "phases": [
                None,
                {"role": "worker"},  # no phase id: not a phase
                {"phaseId": "worker-1", "costUsd": "free"},
            ],
        }
    )
    assert decoded is not None
    assert decoded.cumulative_cost_usd == pytest.approx(0.0)
    assert decoded.already_billed_cost_usd == pytest.approx(0.0)
    assert decoded.cap_usd == pytest.approx(0.0)
    assert decoded.cumulative_usage.is_empty
    assert decoded.confidence == "exact"
    assert decoded.boundary == "final"
    assert [p.phase_id for p in decoded.phases] == ["worker-1"]
    assert decoded.phases[0].cost_usd == pytest.approx(0.0)


def test_decode_run_receipt_clamps_billed_above_cumulative() -> None:
    """A stored already-billed amount above the run's own total would otherwise
    read as a negative increment — a credit — on the next boundary."""
    decoded = decode_run_receipt(
        {"cumulativeCostUsd": 0.10, "alreadyBilledCostUsd": 0.99}
    )
    assert decoded is not None
    assert decoded.already_billed_cost_usd == pytest.approx(0.10)
    assert decoded.newly_billable_cost_usd == pytest.approx(0.0)


# AC-07 — one neutral answer policy, imported downward only ---------------------


@pytest.mark.parametrize("package", ["providers", "tools", "agentic"])
def test_engine_packages_do_not_import_the_streaming_layer(package: str) -> None:
    """AC-07 closure: the delivery layer is not a dependency of its engines.

    Providers, the tool loop and the orchestrator all needed the shared
    answer/markup policy, and all three used to import it from
    `app.streaming.constants`. The policy is neutral runtime code now, so nothing
    in these packages may name `app.streaming` at all.
    """
    assert answer_policy_mod.__file__
    package_root = Path(answer_policy_mod.__file__).parent.parent / package
    offenders = {
        path.name: sorted(
            name
            for name in _app_imports(path)
            if name == "app.streaming" or name.startswith("app.streaming.")
        )
        for path in sorted(package_root.rglob("*.py"))
    }
    assert {name: hits for name, hits in offenders.items() if hits} == {}


def test_answer_policy_imports_nothing_it_serves() -> None:
    """The policy is the shared leaf: it cannot import a consumer back."""
    assert answer_policy_mod.__file__
    imported = _app_imports(Path(answer_policy_mod.__file__))
    assert imported == set(), imported


@pytest.mark.parametrize(
    "module", ["app.streaming.constants", "app.providers._tool_markup"]
)
def test_the_superseded_policy_owners_are_gone(module: str) -> None:
    """Both previous owners are deleted, not shimmed: a re-export would leave two
    import paths to one policy and let the upward dependency grow back."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)
