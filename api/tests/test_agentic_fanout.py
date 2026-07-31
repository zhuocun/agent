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
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    UsageUpdate,
)

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


async def _grant_pro(
    session_factory: async_sessionmaker[AsyncSession], *, user_id: object
) -> None:
    """Grant the test user an active Pro entitlement.

    Deep Research no longer requires Pro; fan-out tests here skip this grant.
    Kept as a shared helper for sibling modules (`test_agentic_resilience`,
    `test_empty_reply_fallback`) that still import it.
    """
    async with session_factory() as session:
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=UUID(str(user_id)),
            provider="fake",
            subscription_id=f"sub-{user_id}",
            status="active",
            customer_id=f"cus-{user_id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()


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


# Handler-driven real-provider fan-out ----------------------------------------
#
# `PROVIDER_BACKEND=fake` forces `scaffolded=True`, which takes the
# deterministic-synthesis path. The degrade paths below live in the
# MODEL-WRITTEN synthesis (`_finalize_synthesis_streamed`), so they need a
# non-fake backend plus a stub provider — driven through `stream_and_persist`
# so both the wire AND the persisted transcript are observable.


class _StubRequest:
    async def is_disconnected(self) -> bool:
        return False


class _ScriptedProvider:
    """Provider stub that branches on the prompt each subagent phase sends."""

    def __init__(
        self,
        *,
        worker: Callable[[str], AsyncIterator[ProviderEvent]],
        aggregator: Callable[[str], AsyncIterator[ProviderEvent]],
        plan: tuple[str, ...] = ("alpha", "beta"),
    ) -> None:
        self._worker = worker
        self._aggregator = aggregator
        self._plan = plan
        self.prompts: list[str] = []

    def stream(  # type: ignore[no-untyped-def]
        self, *, user_text: str = "", **_kwargs: object
    ):
        self.prompts.append(user_text)
        if "synthesizer for a deep-research run" in user_text:
            return self._aggregator(user_text)
        if "planner for a deep-research run" in user_text:
            return self._plan_stream()
        return self._worker(user_text)

    def _plan_stream(self) -> AsyncIterator[ProviderEvent]:
        plan = self._plan

        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(
                text="\n".join(f"{i + 1}. {q}" for i, q in enumerate(plan))
            )
            usage = UsageUpdate(input_tokens=1, output_tokens=1)
            yield usage
            yield Complete(usage=usage)

        return _gen()


async def _drive_deep_research_handler(
    session_factory: async_sessionmaker[AsyncSession],
    provider: _ScriptedProvider,
    *,
    user_text: str = "compare alpha | beta",
) -> tuple[list[tuple[str, dict[str, object]]], list[dict[str, object]]]:
    """Run one deep-research turn over `provider`; return (frames, persisted parts)."""
    from app.providers.tiers import get_binding
    from app.streaming.handler import stream_and_persist

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    frames: list[tuple[str, dict[str, object]]] = []
    async with session_factory() as session:
        async for ev in stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=provider,  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text=user_text,
            history=[],
            is_temporary=False,
            user_id=user_id,
            agentic_mode="deep_research",
        ):
            payload: dict[str, object] = {}
            if ev.data:
                try:
                    payload = json.loads(ev.data)
                except json.JSONDecodeError:
                    payload = {}
            frames.append((ev.event or "", payload))

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        ).scalars().first()
    assert row is not None
    return frames, _parts(row)


def _plain_worker(prompt: str) -> AsyncIterator[ProviderEvent]:
    async def _gen() -> AsyncIterator[ProviderEvent]:
        yield AnswerDelta(text=f"finding for {prompt[-12:]}")
        usage = UsageUpdate(input_tokens=1, output_tokens=1)
        yield usage
        yield Complete(usage=usage)

    return _gen()


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

    run_costs = [d for n, d in frames if n == "run_cost"]
    assert run_costs
    run_cost = run_costs[-1]
    assert run_cost["capUsd"] == get_settings().agentic_run_budget_usd
    assert float(run_cost["subtotalUsd"]) >= 0.0
    assert run_cost.get("confidence") == "exact"
    assert run_cost.get("phase") == "final"

    done = [d for n, d in frames if n == "subagent_done"]
    assert done
    assert done[0].get("outcome") == "succeeded"
    assert "attribution" in done[0] or done[0].get("costUsd") is not None

    # Persisted transcript opens with a `subagent` marker, then primary-tagged
    # reasoning + text.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    parts = _parts(assistant[0])
    assert parts[0]["type"] == "subagent"
    assert parts[0]["subagentId"] == "primary"
    assert parts[0]["role"] == "primary"
    assert parts[0].get("outcome") == "succeeded"
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


async def test_deep_research_without_pro_uses_platform_key_and_fans_out(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Platform key is enough: no Pro grant, no BYOK. Deep research must NOT
    # coerce to `single` / primary-only — same fan-out shape as the entitled path.
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": "60000000-0000-0000-0000-000000000001",
         "tierId": "smart",
         "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
         "agenticMode": "deep_research"},
    )
    names = _names(frames)
    assert names[0] == "submitted"
    submitted = frames[0][1]
    assert submitted.get("requestedAgenticMode") == "deep_research"
    assert submitted.get("effectiveAgenticMode") == "deep_research"
    assert submitted.get("agenticCoercionReason") is None

    assert names[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    started_ids = {
        str(d["subagentId"]) for n, d in frames if n == "subagent_started"
    }
    assert started_ids == {"worker-0", "worker-1", "aggregator"}
    done_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_done"}
    assert done_ids == {"worker-0", "worker-1", "aggregator"}
    # Must not have degraded to a single primary agent.
    assert "primary" not in started_ids

    full_answer = _answer(frames)
    assert "Synthesis of 2 findings" in full_answer
    assert "causes of inflation" in full_answer
    assert "effects on housing" in full_answer


# 3. Degrade labels and terminal outcomes (F1) ---------------------------------


@pytest.fixture
def real_backend_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Non-fake backend so the MODEL-WRITTEN synthesis path is exercised."""
    monkeypatch.setenv("PROVIDER_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TOOLS_ENABLED", "true")
    monkeypatch.setenv("AGENTIC_ENABLED", "true")
    monkeypatch.setenv("AGENTIC_VERIFIER", "false")
    monkeypatch.setenv("AGENTIC_RUN_BUDGET_USD", "10.0")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


_BUDGET_LABEL = "stay within the run budget"
_SYNTHESIS_FAILED_LABEL = "synthesis failed"


async def test_aggregator_exception_labels_synthesis_failure_not_budget_halt(
    real_backend_env: None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FL-06 (GAP-1): a provider crash in synthesis is not a budget halt.

    `budget_halted=budget_halted or aggregator_failed` used to hand the
    budget-halt copy to `aggregate.synthesize` while `RunCost.budget_halted`
    stayed False — copy and flag disagreed on the same frame.
    """

    def _aggregator(_prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            raise RuntimeError("aggregator boom")
            yield AnswerDelta(text="never")  # pragma: no cover

        return _gen()

    provider = _ScriptedProvider(worker=_plain_worker, aggregator=_aggregator)
    frames, parts = await _drive_deep_research_handler(session_factory, provider)

    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["status"] == "done"
    answer = _answer(frames)
    assert _SYNTHESIS_FAILED_LABEL in answer
    assert _BUDGET_LABEL not in answer
    # Every worker finding still reaches the user.
    assert "finding for" in answer

    run_costs = [d for n, d in frames if n == "run_cost"]
    final = run_costs[-1]
    assert final.get("partial") is True
    assert final.get("budgetHalted") is False
    assert final.get("failedWorkerCount") == 0

    summary = next(p for p in parts if p.get("type") == "agentic_run_summary")
    assert summary["outcome"] == "partial"
    assert summary["budgetHalted"] is False


async def test_genuine_budget_halt_keeps_the_budget_label(
    real_backend_env: None,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FL-06 twin: a real cap breach still gets the budget label + flag.

    Pins the two label channels apart: this one comes from
    `aggregate.synthesize(budget_halted=True)` and must keep agreeing with
    `RunCost.budget_halted`.
    """
    # High enough to be admitted (the pre-flight estimate is ~$7.2), low enough
    # that the first worker's actual usage breaches it mid-flight.
    monkeypatch.setenv("AGENTIC_RUN_BUDGET_USD", "8.0")
    get_settings.cache_clear()

    def _big_usage() -> UsageUpdate:
        return UsageUpdate(input_tokens=5_000_000, output_tokens=5_000_000)

    def _worker(prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text="finding for a worker")
            yield _big_usage()
            yield Complete(usage=_big_usage())

        return _gen()

    def _aggregator(_prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text="model draft")
            yield _big_usage()
            yield Complete(usage=_big_usage())

        return _gen()

    provider = _ScriptedProvider(worker=_worker, aggregator=_aggregator)
    frames, _persisted = await _drive_deep_research_handler(session_factory, provider)

    assert frames[-1][1]["status"] == "done"
    answer = _answer(frames)
    assert _BUDGET_LABEL in answer
    assert _SYNTHESIS_FAILED_LABEL not in answer
    run_costs = [d for n, d in frames if n == "run_cost"]
    assert run_costs[-1].get("budgetHalted") is True
    assert run_costs[-1].get("partial") is True


async def test_relayed_aggregator_draft_is_not_re_emitted_through_the_handler(
    real_backend_env: None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FL-07 (C-1) at integration level: relayed synthesis prose ships once.

    The FL-06 twin above raises before yielding anything, so it never covered
    the duplication arm. Here the aggregator relays a delta and *then* crashes:
    the degrade branch used to prepend that already-streamed text to the
    deterministic fallback, delivering the same prose twice — live and on
    reload. Driven through `stream_and_persist` so both the wire and the
    persisted transcript are checked, which the fake-provider SSE tests cannot
    do (`PROVIDER_BACKEND=fake` forces `scaffolded=True` and never enters
    `_finalize_synthesis_streamed`).
    """
    marker = "PARTIAL-DRAFT-MARKER"

    def _aggregator(_prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text=marker)
            raise RuntimeError("aggregator boom after relaying prose")

        return _gen()

    provider = _ScriptedProvider(worker=_plain_worker, aggregator=_aggregator)
    frames, parts = await _drive_deep_research_handler(session_factory, provider)

    assert frames[-1][0] == "terminal"
    assert frames[-1][1]["status"] == "done"

    assert _answer(frames).count(marker) == 1

    text_parts = [p for p in parts if p.get("type") == "text"]
    assert text_parts
    assert "".join(str(p.get("text", "")) for p in text_parts).count(marker) == 1

    # FL-06 stays honest on this path too: a crash is not a budget event.
    answer = _answer(frames)
    assert _SYNTHESIS_FAILED_LABEL in answer
    assert _BUDGET_LABEL not in answer
    run_costs = [d for n, d in frames if n == "run_cost"]
    assert run_costs[-1].get("partial") is True
    assert run_costs[-1].get("budgetHalted") is False


async def test_worker_with_no_prose_is_marked_failed_and_omitted(
    real_backend_env: None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """FL-05 (with FL-04): a silent worker is `failed`, not a successful finding.

    The static `EMPTY_REPLY_FALLBACK` used to make `answer_parts` look written,
    so a lost research step was reported `succeeded` with `partial=False`.
    """
    from app.runtime.answer_policy import EMPTY_REPLY_FALLBACK

    def _worker(prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            if "beta" in prompt:
                yield UsageUpdate(input_tokens=1, output_tokens=0)
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=0))
                return
            yield AnswerDelta(text="alpha finding text")
            usage = UsageUpdate(input_tokens=1, output_tokens=1)
            yield usage
            yield Complete(usage=usage)

        return _gen()

    def _aggregator(_prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text="synthesis over completed work")
            usage = UsageUpdate(input_tokens=1, output_tokens=1)
            yield usage
            yield Complete(usage=usage)

        return _gen()

    provider = _ScriptedProvider(worker=_worker, aggregator=_aggregator)
    frames, parts = await _drive_deep_research_handler(
        session_factory, provider, user_text="alpha | beta"
    )

    assert frames[-1][1]["status"] == "done"
    worker_dones = [
        d
        for n, d in frames
        if n == "subagent_done" and str(d.get("subagentId", "")).startswith("worker")
    ]
    assert len(worker_dones) == 2
    assert sum(1 for d in worker_dones if d.get("outcome") == "failed") == 1
    run_costs = [d for n, d in frames if n == "run_cost"]
    assert run_costs[-1].get("failedWorkerCount") == 1
    assert run_costs[-1].get("partial") is True

    # The filler never ships as a finding — neither to the user nor into the
    # DATA envelope handed to the aggregator.
    answer = _answer(frames)
    assert EMPTY_REPLY_FALLBACK not in answer
    assert all(
        EMPTY_REPLY_FALLBACK not in str(p.get("text", ""))
        for p in parts
        if p.get("type") == "text"
    )
    assert all(EMPTY_REPLY_FALLBACK not in p for p in provider.prompts)


# Cross-cutting terminal-outcome invariant (F1 definition of done) --------------


_DoDStreams = Callable[[], "tuple[object, object, dict[str, object]]"]


def _dod_settings(**kwargs: object):  # type: ignore[no-untyped-def]
    from app.config import Settings

    base: dict[str, object] = {
        "AGENTIC_ENABLED": True,
        "TOOLS_ENABLED": True,
        "AGENTIC_PLAN_APPROVAL": False,
        "AGENTIC_VERIFIER": False,
        "AGENTIC_MAX_WORKERS": 2,
        "AGENTIC_MAX_CONCURRENCY": 2,
        "AGENTIC_RUN_BUDGET_USD": 10.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _dod_healthy() -> tuple[object, dict[str, object], dict[str, str]]:
    """Both workers answer; aggregator synthesizes."""

    def _factory(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[object],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="finding")
                usage = UsageUpdate(input_tokens=2, output_tokens=1)
                yield usage
                yield Complete(usage=usage)

            return _gen()

        return _make

    return _factory, {}, {"worker-0": "succeeded", "worker-1": "succeeded"}


def _dod_failed_worker() -> tuple[object, dict[str, object], dict[str, str]]:
    """One worker raises non-retryably; the run still finishes."""

    def _factory(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[object],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _boom() -> AsyncIterator[ProviderEvent]:
                raise RuntimeError("worker boom")
                yield AnswerDelta(text="never")  # pragma: no cover

            async def _ok() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="finding")
                usage = UsageUpdate(input_tokens=2, output_tokens=1)
                yield usage
                yield Complete(usage=usage)

            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _boom()
            return _ok()

        return _make

    return (
        _factory,
        {"is_retryable": lambda _exc: False},
        {"worker-0": "succeeded", "worker-1": "failed"},
    )


def _dod_superseded_pause() -> tuple[object, dict[str, object], dict[str, str]]:
    """Two concurrent pauses: the loser must be closed as cancelled."""
    import asyncio as _asyncio

    from app.providers.protocol import AwaitingApproval, ToolCall

    first_paused = _asyncio.Event()

    def _pause(index: str, *, wait: bool) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            if wait:
                await first_paused.wait()
                # Let the winner's pause reach the fan-out queue first so this
                # sibling is deterministically the superseded one.
                await _asyncio.sleep(0.05)
            yield AnswerDelta(text=f"partial from {index}")
            yield UsageUpdate(input_tokens=2, output_tokens=0)
            yield ToolCall(
                id=f"cal-{index}",
                name="calendar_create_event",
                label="Create calendar event",
                status="awaiting_approval",
                approval_state="pending",
                input={"title": index},
            )
            if not wait:
                first_paused.set()
            yield AwaitingApproval(tool_call_id=f"cal-{index}")

        return _gen()

    def _factory(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[object],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _pause("w0", wait=False)
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _pause("w1", wait=True)

            async def _agg() -> AsyncIterator[ProviderEvent]:  # pragma: no cover
                yield AnswerDelta(text="agg")
                yield Complete(usage=UsageUpdate())

            return _agg()

        return _make

    return _factory, {}, {"worker-1": "cancelled"}


def _dod_budget_cancelled_pause() -> tuple[object, dict[str, object], dict[str, str]]:
    """A parked pause the cap invalidates must close as budget_cancelled."""
    from app.providers.protocol import AwaitingApproval, ToolCall

    def _factory(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[object],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _pause() -> AsyncIterator[ProviderEvent]:
                yield UsageUpdate(input_tokens=10, output_tokens=0)
                yield ToolCall(
                    id="cal-0",
                    name="calendar_create_event",
                    label="Create calendar event",
                    status="awaiting_approval",
                    approval_state="pending",
                    input={"title": "alpha"},
                )
                yield AwaitingApproval(tool_call_id="cal-0")

            async def _breach() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="beta finding")
                usage = UsageUpdate(input_tokens=5_000_000, output_tokens=0)
                yield usage
                yield Complete(usage=usage)

            async def _agg() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="agg")
                yield Complete(usage=UsageUpdate())

            if "DEEP_RESEARCH_WORKER:0:" in prompt:
                return _pause()
            if "DEEP_RESEARCH_WORKER:1:" in prompt:
                return _breach()
            return _agg()

        return _make

    return (
        _factory,
        {
            "settings": _dod_settings(AGENTIC_RUN_BUDGET_USD=1.0),
            "cost_for_usage": lambda u: 1e-6 * float(u.input_tokens),
        },
        {"worker-0": "budget_cancelled"},
    )


@pytest.mark.parametrize(
    "scenario",
    [
        _dod_healthy,
        _dod_failed_worker,
        _dod_superseded_pause,
        _dod_budget_cancelled_pause,
    ],
    ids=["healthy", "failed_worker", "superseded_pause", "budget_cancelled_pause"],
)
async def test_every_started_subagent_reaches_a_terminal_outcome(
    scenario: Callable[[], tuple[object, dict[str, object], dict[str, str]]],
) -> None:
    """F1 DoD 3: no started subagent may be left on the `succeeded` default.

    Every started subagent must reach a REAL terminal outcome on the wire, with
    exactly one deliberate exception: the parked HITL pause, which the handler's
    `mark_unfinished_subagents_paused` repair owns (B15).
    """
    from app.agentic.orchestrator import run_orchestrator
    from app.providers.protocol import AwaitingApproval, SubagentDone, SubagentStarted

    factory, overrides, expected = scenario()
    kwargs: dict[str, object] = {
        "make_stream_for": factory,
        "settings": _dod_settings(),
        "mode": "deep_research",
        "user_text": "DEEP_RESEARCH: alpha | beta",
        "cost_for_usage": lambda u: 0.001 * float(u.input_tokens),
    }
    kwargs.update(overrides)
    events = [ev async for ev in run_orchestrator(**kwargs)]  # type: ignore[arg-type]

    started = {
        e.subagent_id for e in events if isinstance(e, SubagentStarted)
    }
    dones = {
        e.subagent_id: e.outcome for e in events if isinstance(e, SubagentDone)
    }
    parked = {
        e.subagent_id for e in events if isinstance(e, AwaitingApproval) and e.subagent_id
    }
    assert started
    unterminated = started - set(dones) - parked
    assert not unterminated, f"no terminal outcome for {sorted(unterminated)}"
    for subagent_id, outcome in expected.items():
        assert dones.get(subagent_id) == outcome, (
            f"{subagent_id} reported {dones.get(subagent_id)!r}, want {outcome!r}"
        )


class _DisconnectAfterStarted:
    """Request stub that disconnects once the fan-out is underway (stop path)."""

    def __init__(self, *, after: int = 6) -> None:
        self._polls = 0
        self._after = after

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > self._after


async def test_every_started_subagent_reaches_a_terminal_outcome_on_stop(
    real_backend_env: None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """F1 DoD 3, stop path: the terminal arrives PERSISTED, not streamed.

    Stop / disconnect `aclose`s the orchestrator generator, so a
    `SubagentDone(stopped)` enqueued by a cancelled worker can never be yielded
    (`orchestrator.py` teardown note). `mark_unfinished_subagents_stopped` is the
    contract there — this pins that no row survives on the `succeeded` default.
    """
    import asyncio as _asyncio

    from app.providers.tiers import get_binding
    from app.streaming.handler import stream_and_persist

    def _slow_worker(_prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text="partial ")
            yield UsageUpdate(input_tokens=3, output_tokens=1)
            await _asyncio.sleep(30)
            yield Complete(usage=UsageUpdate(input_tokens=3, output_tokens=1))

        return _gen()

    def _unused_aggregator(_prompt: str) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:  # pragma: no cover
            yield AnswerDelta(text="agg")
            yield Complete(usage=UsageUpdate())

        return _gen()

    provider = _ScriptedProvider(worker=_slow_worker, aggregator=_unused_aggregator)
    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id, title="dod-stop", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    async with session_factory() as session:
        async for _ev in stream_and_persist(
            request=_DisconnectAfterStarted(),  # type: ignore[arg-type]
            db=session,
            provider=provider,  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="compare alpha | beta",
            history=[],
            is_temporary=False,
            user_id=user_id,
            agentic_mode="deep_research",
        ):
            pass

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        ).scalars().first()
    assert row is not None
    assert row.status == "stopped"
    subagents = [p for p in _parts(row) if p.get("type") == "subagent"]
    assert subagents, "stop path must still persist the started subagents"
    outcomes = {str(p.get("subagentId")): p.get("outcome") for p in subagents}
    # Both workers were mid-stream when the disconnect landed.
    assert outcomes["worker-0"] == "stopped"
    assert outcomes["worker-1"] == "stopped"
    # The planner had already streamed its own terminal, so `succeeded` here is a
    # real outcome rather than the persist-time default.
    assert outcomes["planner"] == "succeeded"
    assert "aggregator" not in outcomes


# FL-35: a grounded agentic turn must not end with an "ungrounded" frame --------


class _NoDisconnect:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectAfterFirstFrame:
    """Disconnect after one yielded frame, so the rest is folded by the drain."""

    def __init__(self) -> None:
        self._polls = 0

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > 1


class _UnusedProvider:
    def stream(self, **_kwargs: object):  # type: ignore[no-untyped-def]
        raise AssertionError("the stubbed orchestrator replaces the provider")


@pytest.mark.parametrize("path", ["live", "drain"])
async def test_grounded_agentic_turn_emits_no_ungrounded_sources_frame(
    agentic_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    """FL-35 (FE-5): tagged sources still ground the turn.

    `saw_sources_event` was only set in the untagged arm of the `Sources`
    handler, so a fully subagent-tagged agentic turn fell through to the
    ungrounded honesty frame (`items=[]`, `requested=True`) — telling a
    frame-reading consumer the cited answer had no live sources.

    The `drain` arm pins the stopped-drain twin: only the success path can emit
    the honesty frame, so what the drain has to guarantee is that a stopped turn
    folds the tagged sources identically rather than dropping them.
    """
    import asyncio as _asyncio

    from app.providers.protocol import Sources, SubagentStarted
    from app.providers.tiers import get_binding
    from app.search.protocol import SourceItem
    from app.streaming import handler as handler_mod

    items = [
        SourceItem(id=1, title="Alpha source", url="https://example.test/alpha"),
        SourceItem(id=2, title="Beta source", url="https://example.test/beta"),
    ]
    events: list[ProviderEvent] = [
        SubagentStarted(subagent_id="worker-0", label="Alpha", role="worker"),
        Sources(items=items, subagent_id="worker-0"),
        AnswerDelta(text="grounded finding [1][2]", subagent_id="worker-0"),
        UsageUpdate(input_tokens=8, output_tokens=4, subagent_id="worker-0"),
    ]
    if path == "live":
        events.append(Complete(usage=UsageUpdate(input_tokens=8, output_tokens=4)))

    def _fake_run_orchestrator(**_kwargs: object) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            for ev in events:
                yield ev
            if path == "drain":
                await _asyncio.sleep(30)

        return _gen()

    monkeypatch.setattr(handler_mod, "run_orchestrator", _fake_run_orchestrator)

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id, title="fl35", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    frames: list[tuple[str, dict[str, object]]] = []
    request_stub: object = (
        _NoDisconnect() if path == "live" else _DisconnectAfterFirstFrame()
    )
    async with session_factory() as session:
        async for ev in handler_mod.stream_and_persist(
            request=request_stub,  # type: ignore[arg-type]
            db=session,
            provider=_UnusedProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="compare alpha | beta",
            history=[],
            is_temporary=False,
            user_id=user_id,
            web_search=True,
            agentic_mode="deep_research",
        ):
            payload: dict[str, object] = {}
            if ev.data:
                try:
                    payload = json.loads(ev.data)
                except json.JSONDecodeError:
                    payload = {}
            frames.append((ev.event or "", payload))

    sources_frames = [d for n, d in frames if n == "sources"]
    assert not any(
        d.get("items") == [] and d.get("requested") is True for d in sources_frames
    ), "grounded turn emitted the ungrounded honesty frame"

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    sources_parts = [p for p in _parts(assistant[0]) if p.get("type") == "sources"]
    assert sources_parts, "the tagged sources must persist"
    assert all(p.get("items") for p in sources_parts)
