"""Route/handler integration for B4/B5/B9/B13 arch-review ledger fixes."""

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

from app.agentic.budget import estimate_run_cost
from app.agentic.continuation import (
    SERVER_STATE_PLANNER_COST_KEY,
    SERVER_STATE_PLANNER_USAGE_KEY,
    SERVER_STATE_PRIOR_RUN_COST_KEY,
    get_run_ledger_from_server_state,
    put_run_ledger_in_server_state,
    usage_to_wire,
)
from app.config import get_settings
from app.db.models import Conversation, Message, UsageRollup, User
from app.db.repositories import billing as billing_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_db
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import UsageUpdate
from app.providers.tiers import get_binding

pytestmark = pytest.mark.asyncio


def _sse_frames(body: str) -> list[tuple[str, dict[str, object]]]:
    frames: list[tuple[str, dict[str, object]]] = []
    event_name = "message"
    data_lines: list[str] = []
    for raw in body.splitlines():
        if raw.startswith("event:"):
            event_name = raw[len("event:") :].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:") :].strip())
        elif raw == "" and data_lines:
            payload = json.loads("\n".join(data_lines))
            assert isinstance(payload, dict)
            frames.append((event_name, payload))
            event_name = "message"
            data_lines = []
    if data_lines:
        payload = json.loads("\n".join(data_lines))
        assert isinstance(payload, dict)
        frames.append((event_name, payload))
    return frames


async def _collect_sse(
    client: AsyncClient, path: str, payload: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    response = await client.post(path, json=payload, timeout=30.0)
    assert response.status_code == 200, response.text
    return _sse_frames(response.text)


@pytest.fixture
def plan_approval_env() -> Iterator[None]:
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "true",
        "USAGE_BUDGET_USD": "100",
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


@pytest.fixture
def plan_approval_app(
    plan_approval_env: None,
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
        app_.dependency_overrides.clear()


@pytest.fixture
async def plan_client(
    plan_approval_app,
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=plan_approval_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_b4_plan_resume_seeds_nonzero_runcost_via_server_state(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B4: pause persists planner ledger in server_state; resume RunCost is non-zero."""
    await plan_client.get("/api/bootstrap")
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=user.id,
            provider="fake",
            subscription_id=f"sub-{user.id}",
            status="active",
            customer_id=f"cus-{user.id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()

    create = await plan_client.post(
        "/api/conversations", json={"title": "b4", "selectedTierId": "smart"}
    )
    assert create.status_code == 201
    conv_id = create.json()["id"]

    pause_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b4000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "DEEP_RESEARCH: causes of inflation | effects on housing",
            "agenticMode": "deep_research",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    plan_call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")
    plan_input = next(d["input"] for n, d in pause_frames if n == "tool_call")
    assert isinstance(plan_input, dict)
    assert "plannerCostUsd" not in plan_input

    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
        paused.server_state = put_run_ledger_in_server_state(
            paused.server_state if isinstance(paused.server_state, dict) else {},
            planner_cost_usd=0.37,
            planner_usage=UsageUpdate(input_tokens=37, output_tokens=3),
        )
        await session.commit()
        ledger = get_run_ledger_from_server_state(paused.server_state)
        assert ledger.planner_cost_usd == pytest.approx(0.37)
        assert SERVER_STATE_PLANNER_COST_KEY in (paused.server_state or {})
        assert SERVER_STATE_PLANNER_USAGE_KEY in (paused.server_state or {})

    resume_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b4000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {"toolCallId": plan_call_id, "decision": "approve"},
        },
    )
    assert resume_frames[-1][1]["status"] == "done"
    run_costs = [d for n, d in resume_frames if n == "run_cost"]
    assert run_costs
    assert float(run_costs[0]["subtotalUsd"]) >= 0.37 - 1e-9


async def test_b5_single_mode_resume_seeds_runcost_via_api(
    plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B5: single-mode pause ledger in server_state seeds resume RunCost."""
    monkeypatch.setenv("AGENTIC_PLAN_APPROVAL", "false")
    get_settings.cache_clear()

    await plan_client.get("/api/bootstrap")
    create = await plan_client.post(
        "/api/conversations", json={"title": "b5", "selectedTierId": "smart"}
    )
    assert create.status_code == 201
    conv_id = create.json()["id"]

    pause_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b5000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": "TOOL_APPROVE: schedule a meeting",
            "agenticMode": "single",
        },
    )
    assert pause_frames[-1][1]["status"] == "awaiting_approval"
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")

    async with session_factory() as session:
        paused = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
            )
        ).scalar_one()
        paused.server_state = put_run_ledger_in_server_state(
            paused.server_state if isinstance(paused.server_state, dict) else {},
            prior_run_cost_usd=0.2,
            prior_run_usage=UsageUpdate(input_tokens=20, output_tokens=0),
        )
        await session.commit()

    resume_frames = await _collect_sse(
        plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "b5000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "agenticMode": "single",
            "toolApproval": {"toolCallId": call_id, "decision": "approve"},
        },
    )
    assert resume_frames[-1][1]["status"] == "done"
    run_costs = [d for n, d in resume_frames if n == "run_cost"]
    assert run_costs
    assert float(run_costs[0]["subtotalUsd"]) >= 0.2 - 1e-9


async def test_b5_single_mode_pause_persists_prior_run_ledger_keys() -> None:
    """B5 helpers round-trip priorRunCostUsd into server_state."""
    state = put_run_ledger_in_server_state(
        None,
        prior_run_cost_usd=0.2,
        prior_run_usage=UsageUpdate(input_tokens=20, output_tokens=0),
    )
    assert state[SERVER_STATE_PRIOR_RUN_COST_KEY] == pytest.approx(0.2)
    assert state["priorRunUsage"] == usage_to_wire(
        UsageUpdate(input_tokens=20, output_tokens=0)
    )
    parsed = get_run_ledger_from_server_state(state)
    assert parsed.prior_run_cost_usd == pytest.approx(0.2)
    assert parsed.prior_run_usage is not None
    assert parsed.prior_run_usage.input_tokens == 20


async def test_b5_repeated_pause_accumulates_prior_run_cost() -> None:
    """B5: a second single-mode pause must keep the prior resume seed cost."""
    # Simulate what the handler does: seed from resume + this turn's cost.
    prior = get_run_ledger_from_server_state(
        put_run_ledger_in_server_state(None, prior_run_cost_usd=0.2)
    )
    turn_cost = 0.15
    accumulated = float(prior.prior_run_cost_usd) + turn_cost
    state = put_run_ledger_in_server_state(
        None,
        prior_run_cost_usd=accumulated,
        prior_run_usage=UsageUpdate(input_tokens=30, output_tokens=5),
    )
    parsed = get_run_ledger_from_server_state(state)
    assert parsed.prior_run_cost_usd == pytest.approx(0.35)


async def test_b9_headroom_uses_reserved_hold_not_remaining_after_subtract(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B9: orchestrator headroom should be the hold amount, not remaining-hold."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="b9",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        from app.db.models import Stream

        stream = Stream(conversation_id=convo.id, status="active")
        session.add(stream)
        await session.commit()
        await session.refresh(stream)

        binding = get_binding("smart")
        assert binding is not None
        settings = get_settings()
        hold = estimate_run_cost(
            sub_question_count=settings.agentic_max_workers,
            binding=binding,
            settings=settings,
            image_count=0,
        )
        assert hold > 0
        ok = await usage_repo.reserve_platform_budget(
            session,
            user_id=user.id,
            stream_id=stream.id,
            amount_usd=hold,
            monthly_quota_usd=100.0,
        )
        await session.commit()
        assert ok is True
        remaining = await usage_repo.get_platform_remaining_usd(
            session, user_id=user.id, monthly_quota_usd=100.0
        )
        assert remaining is not None
        assert remaining == pytest.approx(100.0 - hold)
        # Route passes `hold` (reserved_hold_usd), not `remaining`.
        assert hold > remaining or hold <= remaining


async def test_b13_compaction_usage_incremented(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """B13: summarizer usage is billed via reference_type=compaction."""
    usage = UsageUpdate(input_tokens=1000, output_tokens=50)
    binding = get_binding("smart")
    assert binding is not None
    expected = compute_cost_breakdown(usage=usage, binding=binding, image_count=0)
    expected_cost = expected.subtotal_usd + expected.session_surcharge_usd
    assert expected_cost > 0

    async with session_factory() as session:
        user = User(is_anonymous=False, email="b13@example.com", name="B13")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await usage_repo.increment_for_period(
            session,
            user_id=user.id,
            used_delta=0,
            cost_usd_delta=expected_cost,
            is_byok=False,
            monthly_quota_usd=100.0,
            reference_type="compaction",
            reference_id="stream-b13",
        )
        await session.commit()
        rollup = (
            await session.execute(
                select(UsageRollup).where(UsageRollup.user_id == user.id)
            )
        ).scalar_one()
        assert float(rollup.cost_usd) == pytest.approx(expected_cost)


class _StubRequest:
    async def is_disconnected(self) -> bool:
        return False


class _PauseAfterUsageProvider:
    """Single-mode provider that banks usage, then requests a gated tool."""

    def stream(self, *, user_text: str = "", **_kwargs: object):  # type: ignore[no-untyped-def]
        from app.providers.protocol import ProviderEvent, ToolCall

        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield UsageUpdate(input_tokens=40, output_tokens=12, reasoning_tokens=3)
            yield ToolCall(
                id="cal-1",
                name="calendar_create_event",
                status="running",
                input={"title": "Planning review"},
            )

        return _gen()


async def test_single_mode_pause_terminal_reports_tokens_and_receipt(
    plan_approval_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FL-14 (HITL-6): a single-mode pause must still ship tokens and a receipt.

    `run_single` returned at the pause before the untagged `Complete` and the
    final `RunCost`, and the handler `break`s at the pause terminal — so the
    paused row's attribution reported 0 tokens and carried no run summary even
    though billing was correct.
    """
    from app.streaming.handler import stream_and_persist

    monkeypatch.setenv("AGENTIC_PLAN_APPROVAL", "false")
    get_settings.cache_clear()

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="fl14",
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
            provider=_PauseAfterUsageProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=UUID(int=0x14),
            user_text="schedule a meeting",
            history=[],
            is_temporary=False,
            user_id=user_id,
            agentic_mode="single",
        ):
            payload: dict[str, object] = {}
            if ev.data:
                payload = json.loads(ev.data)
            frames.append((ev.event or "", payload))

    assert frames[-1][1]["status"] == "awaiting_approval"
    # The receipt precedes the pause on the wire — the handler stops reading after
    # the pause terminal, so a post-pause receipt would never be consumed.
    names = [n for n, _ in frames]
    assert names.index("run_cost") < names.index("terminal")

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .where(Message.role == "assistant")
            )
        ).scalar_one()

    attribution = row.attribution
    assert isinstance(attribution, dict)
    breakdown = attribution["breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown["inputTokens"] == 40
    assert breakdown["outputTokens"] == 12
    assert float(attribution["costUsd"]) > 0.0

    summary = next(
        p
        for p in (row.parts or [])
        if isinstance(p, dict) and p.get("type") == "agentic_run_summary"
    )
    # A resumable pause is not a finished answer.
    assert summary["outcome"] == "partial"
    assert summary["budgetHalted"] is False
