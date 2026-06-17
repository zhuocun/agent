"""Agentic M4 hardening: per-worker failure degrade, per-subagent attribution,
`execute_tool` spans, and the least-privilege worker tool subset.

Drives the FAKE provider behind `TOOLS_ENABLED=true` + `AGENTIC_ENABLED=true`.
Covers the "Remaining gaps" items being closed:

- PER-WORKER DEGRADE (PRD 08 / FR-26g): a single worker raising mid-stream must
  NOT fail the whole run — it drops out, the run synthesizes the surviving
  workers, and the answer is LABELED a partial (graceful degrade), terminating
  `done`. Uses the fake provider's `FAIL_WORKER` sub-question marker.
- PER-SUBAGENT ATTRIBUTION: a reloaded agentic transcript carries a
  `ModelAttribution` on every `subagent` marker part (priced from that
  subagent's own usage), not only the turn-level roll-up.
- `execute_tool` OTEL SPANS: the agent loop emits an `execute_tool` span per
  executed tool (name only, no content), nested under the owning subagent's
  `invoke_agent` span, when a tracer provider is configured.
- WORKER TOOL SUBSET (SR-2 least privilege): an autonomous worker is offered
  only the non-approval-gated prod-safe tools — an approval-gated tool (which a
  worker could never pause to resolve) is withheld.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db
from app.tools.builtin import TOOL_REGISTRY, advertised_tool_specs, worker_tool_specs

# `asyncio_mode = "auto"` (pyproject) marks the async tests; the one sync unit
# test below must stay unmarked, so we do NOT set a module-level asyncio mark.


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
    """Grant the test user an active Pro entitlement (deep_research is gated)."""
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


async def _bootstrap_pro_convo(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    return await _seed_conversation(session_factory, user_id=user_id)


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


def _started_ids(frames: list[tuple[str, dict[str, object]]]) -> set[str]:
    return {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}


def _done_ids(frames: list[tuple[str, dict[str, object]]]) -> set[str]:
    return {str(d["subagentId"]) for n, d in frames if n == "subagent_done"}


def _parts(message: Message) -> list[dict[str, object]]:
    raw = message.parts
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, dict)]


# 1. Per-worker failure degrades the run instead of failing it ------------------


async def test_agentic_worker_degrade(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One worker raising mid-stream drops out; the run still ends `done`.

    The `FAIL_WORKER` sub-question makes worker-1 raise; worker-0 succeeds. The
    orchestrator must aggregate worker-0's finding, label the answer a partial,
    and terminate `done` — never propagate the worker exception into an `error`.
    """
    conv_id = await _bootstrap_pro_convo(agentic_client, session_factory)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: healthy topic | FAIL_WORKER doomed topic",
            "agenticMode": "deep_research",
        },
    )

    # The run degrades gracefully: terminal is `done`, NOT an `error` frame.
    assert "error" not in _names(frames)
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    # Both workers STARTED (the failing one started before it raised) and both
    # report a `subagent_done` (the failed worker closes its section too), plus
    # the aggregator.
    assert _started_ids(frames) == {"worker-0", "worker-1", "aggregator"}
    assert _done_ids(frames) == {"worker-0", "worker-1", "aggregator"}

    # Only the surviving worker's finding makes it into the synthesis, and the
    # answer is LABELED partial (a failed sub-agent), not silently truncated.
    full_answer = _answer(frames)
    assert "Synthesis of 1 findings" in full_answer
    assert "healthy topic" in full_answer
    assert "doomed topic" not in full_answer
    assert "sub-agents failed" in full_answer
    assert "1 of 2" in full_answer

    # Persisted as a clean `done` turn.
    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].status == "done"


async def test_agentic_all_workers_fail_still_done(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Even when EVERY worker fails, the run finalizes a non-error synthesis."""
    conv_id = await _bootstrap_pro_convo(agentic_client, session_factory)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: FAIL_WORKER one | FAIL_WORKER two",
            "agenticMode": "deep_research",
        },
    )

    assert "error" not in _names(frames)
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    # No findings survived: the aggregator emits the stable "no findings" line.
    assert "no worker findings were produced" in _answer(frames).lower()


# 2. Per-subagent attribution persists on reload -------------------------------


async def test_agentic_subagent_attribution(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Every persisted `subagent` marker carries a per-subagent ModelAttribution."""
    conv_id = await _bootstrap_pro_convo(agentic_client, session_factory)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
            "agenticMode": "deep_research",
        },
    )

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    parts = _parts(assistant[0])

    subagent_parts = [p for p in parts if p.get("type") == "subagent"]
    # worker-0, worker-1, aggregator each open a section.
    assert [p["subagentId"] for p in subagent_parts] == ["worker-0", "worker-1", "aggregator"]

    for part in subagent_parts:
        attribution = part.get("attribution")
        assert isinstance(attribution, dict), f"missing attribution on {part['subagentId']}"
        # The wire-shape contract: a per-subagent attribution carries the
        # requested/served tier, served model label, cost + confidence, and the
        # token breakdown — same shape the turn-level attribution uses.
        for key in (
            "requestedTierId",
            "servedTierId",
            "servedModelLabel",
            "costUsd",
            "costConfidence",
            "breakdown",
        ):
            assert key in attribution, f"{key} missing on {part['subagentId']} attribution"
        assert attribution["costConfidence"] == "exact"
        assert attribution["requestedTierId"] == "smart"
        assert isinstance(attribution["breakdown"], dict)
        assert float(attribution["costUsd"]) >= 0.0


async def test_agentic_single_subagent_attribution(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Single mode's lone `primary` subagent also carries attribution on reload."""
    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000004",
            "tierId": "smart",
            "text": "explain agentic mode",
            "agenticMode": "single",
        },
    )

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    parts = _parts(assistant[0])
    marker = parts[0]
    assert marker["type"] == "subagent"
    assert marker["subagentId"] == "primary"
    attribution = marker.get("attribution")
    assert isinstance(attribution, dict)
    assert attribution["costConfidence"] == "exact"
    assert attribution["servedModelLabel"]


# 3. `execute_tool` OTel spans emitted by the agent loop -----------------------


async def test_agentic_execute_tool_spans(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An agentic turn that runs a tool emits an `execute_tool` span (name only).

    Attaches an in-memory exporter to the active (or a fresh) SDK tracer provider
    so manual agentic spans funnel into it regardless of test ordering, then
    drives a `single`-mode turn whose fake-provider `TOOL_TIME:` marker makes the
    agent loop auto-execute `get_current_time`. The loop's `execute_tool` span
    must appear (nested under the subagent's `invoke_agent` span), carrying the
    tool name ONLY — never tool input/output content.
    """
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    exporter.clear()

    await agentic_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        agentic_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000005",
            "tierId": "smart",
            "text": "TOOL_TIME: what time is it?",
            "agenticMode": "single",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    # The tool actually ran (its result was relayed on the wire).
    tool_results = [d for n, d in frames if n == "tool_result"]
    assert any(d.get("name") == "get_current_time" for d in tool_results)

    spans = exporter.get_finished_spans()
    by_name: dict[str, list[object]] = {}
    for span in spans:
        by_name.setdefault(span.name, []).append(span)
    assert "execute_tool" in by_name, f"no execute_tool span; saw {sorted(by_name)}"
    assert "invoke_agent" in by_name

    tool_spans = by_name["execute_tool"]
    assert any(
        s.attributes is not None and s.attributes.get("tool.name") == "get_current_time"
        for s in tool_spans
    )
    # Discipline: an execute_tool span carries the tool name (+ optional subagent
    # id) ONLY — never tool input/output content.
    for s in tool_spans:
        assert s.attributes is not None
        for key in s.attributes:
            assert key in {"tool.name", "agentic.subagent_id"}


# 4. Workers get a least-privilege tool subset ---------------------------------


def test_agentic_worker_tools_subset() -> None:
    """A worker is offered only non-approval-gated prod-safe tools (SR-2).

    The registry MUST contain at least one approval-gated tool for this contract
    to be meaningful; that tool is present in the full registry but withheld from
    the worker subset (a worker can't pause for HITL approval mid-fan-out). The
    worker subset is a strict subset of `advertised_tool_specs()`.
    """
    gated = [name for name, spec in TOOL_REGISTRY.items() if spec.needs_approval]
    assert gated, "expected at least one approval-gated tool in the registry"

    worker_names = {spec.name for spec in worker_tool_specs()}
    advertised_names = {spec.name for spec in advertised_tool_specs()}

    # Least privilege: no approval-gated tool is offered to a worker.
    assert all(not spec.needs_approval for spec in worker_tool_specs())
    for name in gated:
        assert name not in worker_names

    # Subset of what's advertised to a real provider at all, and the auto
    # `get_current_time` tool survives the filter (workers can still tell time).
    assert worker_names <= advertised_names
    assert "get_current_time" in worker_names
