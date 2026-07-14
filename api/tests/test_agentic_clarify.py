"""Clarify-before-plan HITL for deep-research (plan 02).

Drives the FAKE provider behind `TOOLS_ENABLED=true`, `AGENTIC_ENABLED=true`,
and `AGENTIC_CLARIFY_BEFORE_PLAN=true`. Covers:
- Flag OFF: deep_research with the `CLARIFY:` marker does NOT pause.
- Flag ON + marker: pause with clarifying questions before any plan/fan-out.
- Resume approve (+ answers) proceeds to fan-out + aggregator; answers reach
  worker findings and the synthesis clarifications footer without polluting
  the DEEP_RESEARCH pipe-split.
- Resume deny declines the run without fan-out.
- Dual HITL: clarify → plan-approval keeps answers across both pauses.
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

from app.agentic import (
    PLAN_APPROVAL_TOOL_NAME,
    PLAN_CLARIFY_CALL_ID_PREFIX,
    PLAN_CLARIFY_TOOL_NAME,
    is_plan_approval_call_id,
    is_plan_clarify_call_id,
)
from app.agentic.clarify import (
    CLARIFICATIONS_HEADER,
    strip_clarify_marker,
    with_clarifications,
)
from app.agentic.planner import decompose
from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db

pytestmark = pytest.mark.asyncio

_CLARIFY_PROMPT = (
    "DEEP_RESEARCH: causes of inflation | effects on housing\nCLARIFY:"
)
_CLARIFY_ANSWERS = ["Focus on housing affordability", "US, last 5 years"]


@pytest.fixture
def clarify_env() -> Iterator[None]:
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_CLARIFY_BEFORE_PLAN": "true",
        "AGENTIC_PLAN_APPROVAL": "false",
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
def clarify_off_env() -> Iterator[None]:
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_CLARIFY_BEFORE_PLAN": "false",
        "AGENTIC_PLAN_APPROVAL": "false",
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
def clarify_and_plan_env() -> Iterator[None]:
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_CLARIFY_BEFORE_PLAN": "true",
        "AGENTIC_PLAN_APPROVAL": "true",
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
def clarify_app(
    clarify_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    app_ = _build_app(session_factory)
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
def clarify_off_app(
    clarify_off_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    app_ = _build_app(session_factory)
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
def clarify_and_plan_app(
    clarify_and_plan_env: None,
    session_factory: async_sessionmaker[AsyncSession],
):  # type: ignore[no-untyped-def]
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    app_ = _build_app(session_factory)
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()


@pytest.fixture
async def clarify_client(clarify_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=clarify_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


@pytest.fixture
async def clarify_off_client(clarify_off_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=clarify_off_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


@pytest.fixture
async def clarify_and_plan_client(
    clarify_and_plan_app,
) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=clarify_and_plan_app)
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
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
    return _parse_sse("".join(chunks))


def _names(frames: list[tuple[str, dict[str, object]]]) -> list[str]:
    return [n for n, _ in frames]


def _answer(frames: list[tuple[str, dict[str, object]]]) -> str:
    return "".join(str(d.get("text", "")) for n, d in frames if n == "answer_delta")


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
            subscription_id=f"sub-{user_id}",
            status="active",
            customer_id=f"cus-{user_id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        await session.commit()


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


async def _pause_on_clarify(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, list[tuple[str, dict[str, object]]]]:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": _CLARIFY_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    return conv_id, frames


async def test_strip_clarify_keeps_deep_research_scaffold_intact() -> None:
    """Answers / CLARIFY tails must not enter decompose's pipe-split."""
    cleaned = strip_clarify_marker(_CLARIFY_PROMPT)
    assert "CLARIFY:" not in cleaned
    assert cleaned.startswith("DEEP_RESEARCH:")
    parts = decompose(cleaned, max_workers=4)
    assert parts == ["causes of inflation", "effects on housing"]

    # Custom questions after the marker must also be stripped.
    with_custom = (
        "DEEP_RESEARCH: causes of inflation | effects on housing\n"
        "CLARIFY: prioritize housing | US only"
    )
    assert decompose(strip_clarify_marker(with_custom), max_workers=4) == [
        "causes of inflation",
        "effects on housing",
    ]

    # Appended clarification DATA is for planner/workers only — callers must
    # never feed ``with_clarifications`` into ``decompose`` (use stripped text).
    with_answers = with_clarifications(cleaned, _CLARIFY_ANSWERS)
    assert CLARIFICATIONS_HEADER in with_answers
    assert decompose(cleaned, max_workers=4) == [
        "causes of inflation",
        "effects on housing",
    ]
    assert "Focus on housing affordability" in with_answers


async def test_clarify_flag_off_skips_pause(
    clarify_off_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert get_settings().agentic_clarify_before_plan is False
    await clarify_off_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    await _grant_pro(session_factory, user_id=user_id)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    frames = await _collect_sse(
        clarify_off_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000010",
            "tierId": "smart",
            "text": _CLARIFY_PROMPT,
            "agenticMode": "deep_research",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    tool_calls = [d for n, d in frames if n == "tool_call"]
    assert not any(d.get("name") == PLAN_CLARIFY_TOOL_NAME for d in tool_calls)
    started = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert "worker-0" in started
    assert "aggregator" in started
    assert "Synthesis of 2 findings" in _answer(frames)


async def test_clarify_flag_on_pauses_before_plan(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert get_settings().agentic_clarify_before_plan is True
    conv_id, frames = await _pause_on_clarify(clarify_client, session_factory)

    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "awaiting_approval"

    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert started_ids == {"planner"}
    assert not any(sid.startswith("worker-") for sid in started_ids)

    tool_calls = [d for n, d in frames if n == "tool_call"]
    assert len(tool_calls) == 1
    call = tool_calls[0]
    call_id = str(call["id"])
    assert is_plan_clarify_call_id(call_id)
    assert call_id.startswith(PLAN_CLARIFY_CALL_ID_PREFIX)
    assert call["name"] == PLAN_CLARIFY_TOOL_NAME
    assert call["status"] == "awaiting_approval"
    questions = call["input"]["questions"]
    assert isinstance(questions, list)
    assert 1 <= len(questions) <= 3

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].status == "awaiting_approval"


async def test_clarify_approve_resumes_fanout_with_answers_in_context(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id, pause_frames = await _pause_on_clarify(clarify_client, session_factory)
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")

    frames = await _collect_sse(
        clarify_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": call_id,
                "decision": "approve",
                "editedInput": {"answers": list(_CLARIFY_ANSWERS)},
            },
        },
    )

    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert "worker-0" in started_ids
    assert "worker-1" in started_ids
    assert "aggregator" in started_ids
    full_answer = _answer(frames)
    assert "Synthesis of 2 findings" in full_answer
    # Scaffold intact: clarifications did NOT land in the last sub-question.
    assert "1. causes of inflation:" in full_answer
    assert "2. effects on housing:" in full_answer
    assert "CLARIFY:" not in full_answer
    # Answers reached workers (fake echoes them) and the synthesis footer.
    assert "Clarified: Focus on housing affordability; US, last 5 years" in full_answer
    assert "Clarifications applied:" in full_answer
    assert "Focus on housing affordability" in full_answer
    assert "US, last 5 years" in full_answer

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 2
    assert assistant[0].status == "awaiting_approval"
    assert assistant[1].status == "done"


async def test_clarify_deny_declines_run(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id, pause_frames = await _pause_on_clarify(clarify_client, session_factory)
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")

    frames = await _collect_sse(
        clarify_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": call_id,
                "decision": "deny",
            },
        },
    )

    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert not any(sid.startswith("worker-") for sid in started_ids)
    assert "aggregator" in started_ids
    full_answer = _answer(frames)
    assert "clarifying questions were skipped" in full_answer.lower() or (
        "no research plan" in full_answer.lower()
    )

    msgs = await _load_messages(session_factory, conv_id)
    assistant = [m for m in msgs if m.role == "assistant"]
    assert len(assistant) == 2
    assert assistant[0].status == "awaiting_approval"
    assert assistant[1].status == "done"


async def test_clarify_then_plan_approval_keeps_answers(
    clarify_and_plan_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Dual HITL: clarify answers persist onto the plan pause and into synthesis."""
    assert get_settings().agentic_clarify_before_plan is True
    assert get_settings().agentic_plan_approval is True

    conv_id, clarify_frames = await _pause_on_clarify(
        clarify_and_plan_client, session_factory
    )
    clarify_call_id = next(
        str(d["id"]) for n, d in clarify_frames if n == "tool_call"
    )

    plan_pause = await _collect_sse(
        clarify_and_plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000004",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": clarify_call_id,
                "decision": "approve",
                "editedInput": {"answers": list(_CLARIFY_ANSWERS)},
            },
        },
    )
    assert plan_pause[-1][1]["status"] == "awaiting_approval"
    plan_calls = [
        d
        for n, d in plan_pause
        if n == "tool_call" and d.get("name") == PLAN_APPROVAL_TOOL_NAME
    ]
    assert len(plan_calls) == 1
    plan_call = plan_calls[0]
    assert is_plan_approval_call_id(str(plan_call["id"]))
    assert plan_call["input"]["plan"] == [
        "causes of inflation",
        "effects on housing",
    ]
    assert plan_call["input"]["clarifications"] == list(_CLARIFY_ANSWERS)
    # Still no workers until the plan is approved.
    started_ids = {str(d["subagentId"]) for n, d in plan_pause if n == "subagent_started"}
    assert not any(sid.startswith("worker-") for sid in started_ids)

    final = await _collect_sse(
        clarify_and_plan_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "c0000000-0000-0000-0000-000000000005",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": str(plan_call["id"]),
                "decision": "approve",
            },
        },
    )
    assert final[-1][1]["status"] == "done"
    full_answer = _answer(final)
    assert "Synthesis of 2 findings" in full_answer
    assert "1. causes of inflation:" in full_answer
    assert "2. effects on housing:" in full_answer
    assert "Clarifications applied:" in full_answer
    assert "Focus on housing affordability" in full_answer
    assert "US, last 5 years" in full_answer
