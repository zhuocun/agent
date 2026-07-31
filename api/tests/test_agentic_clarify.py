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

import asyncio
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
    MAX_CLARIFY_ANSWER_CHARS,
    ClarifyInputError,
    format_clarification_data,
    parse_clarification_answers,
    parse_clarify_edited_input,
    records_from_questions_and_answers,
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
    cleaned = strip_clarify_marker(_CLARIFY_PROMPT, allow_strip=True)
    assert "CLARIFY:" not in cleaned
    assert cleaned.startswith("DEEP_RESEARCH:")
    parts = decompose(cleaned, max_workers=4)
    assert parts == ["causes of inflation", "effects on housing"]

    # Custom questions after the marker must also be stripped.
    with_custom = (
        "DEEP_RESEARCH: causes of inflation | effects on housing\n"
        "CLARIFY: prioritize housing | US only"
    )
    assert decompose(
        strip_clarify_marker(with_custom, allow_strip=True), max_workers=4
    ) == [
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


async def test_strip_clarify_marker_gated_off_preserves_literal() -> None:
    """C-004: real/non-scaffolded paths must not truncate at CLARIFY:."""
    text = "Compare the literal CLARIFY: token with ordinary text"
    assert strip_clarify_marker(text, allow_strip=False) == text
    assert strip_clarify_marker(text, allow_strip=True) == "Compare the literal"
    # Flag-off + scaffolded still must not strip when allow_strip is False
    # (orchestrator gates on scaffolded AND agentic_clarify_before_plan).
    assert strip_clarify_marker(_CLARIFY_PROMPT, allow_strip=False) == _CLARIFY_PROMPT


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


async def test_blank_answers_preserve_question_association() -> None:
    """C-002: blank slots must not shift later answers onto earlier questions."""
    questions = ["Q1?", "Q2?", "Q3?"]
    records = records_from_questions_and_answers(questions, ["", "answer to q2", ""])
    assert [r.answer for r in records] == ["", "answer to q2", ""]
    assert records[1].question == "Q2?"
    # Question text must appear in the DATA block fed to planner/workers.
    encoded = format_clarification_data(records)
    assert "Q2?" in encoded
    assert '"question": "Q1?"' in encoded or '"question":"Q1?"' in encoded


async def test_multiline_clarifications_round_trip_via_json_block() -> None:
    """C-003: multiline answers must not be re-parsed as extra numbered lines."""
    answers = [
        "Priority one\n2. nested constraint",
        "Actual second answer",
        "Actual third answer",
    ]
    encoded = format_clarification_data(answers)
    decoded = parse_clarification_answers(encoded)
    assert decoded == answers


async def test_parse_clarify_edited_input_rejects_malformed_and_oversize() -> None:
    """C-005 / C-006: wrong shapes and oversized answers are INVALID_INPUT."""
    questions = ["Q1?", "Q2?"]
    # Omitted edited_input → explicit blank continue.
    blanks = parse_clarify_edited_input(None, questions=questions)
    assert [r.answer for r in blanks] == ["", ""]

    with pytest.raises(ClarifyInputError, match="must be a list"):
        parse_clarify_edited_input({"answers": "nope"}, questions=questions)

    with pytest.raises(ClarifyInputError, match="exactly 2"):
        parse_clarify_edited_input({"answers": ["only-one"]}, questions=questions)

    with pytest.raises(ClarifyInputError, match="must be a string or object"):
        parse_clarify_edited_input(
            {"answers": ["ok", 123]}, questions=questions
        )

    with pytest.raises(ClarifyInputError, match="unknown fields"):
        parse_clarify_edited_input({"answers": ["a", "b"], "extra": 1}, questions=questions)

    huge = "x" * (MAX_CLARIFY_ANSWER_CHARS + 1)
    with pytest.raises(ClarifyInputError, match="exceeds"):
        parse_clarify_edited_input(
            {
                "answers": [
                    {"questionId": "0", "question": "Q1?", "answer": huge},
                    {"questionId": "1", "question": "Q2?", "answer": "ok"},
                ]
            },
            questions=questions,
        )

    bound = parse_clarify_edited_input(
        {
            "answers": [
                {"questionId": "0", "question": "Q1?", "answer": ""},
                {"questionId": "1", "question": "Q2?", "answer": "yes"},
            ]
        },
        questions=questions,
    )
    assert [r.answer for r in bound] == ["", "yes"]
    assert bound[1].question == "Q2?"


def _settled_clarify_parts(parts: object) -> tuple[dict, dict | None]:
    assert isinstance(parts, list)
    call = next(
        p
        for p in parts
        if isinstance(p, dict)
        and p.get("type") == "tool_call"
        and p.get("name") == PLAN_CLARIFY_TOOL_NAME
    )
    result = next(
        (
            p
            for p in parts
            if isinstance(p, dict)
            and p.get("type") == "tool_result"
            and p.get("toolCallId") == call.get("id")
        ),
        None,
    )
    return call, result


async def test_clarify_approve_resumes_fanout_with_answers_in_context(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conv_id, pause_frames = await _pause_on_clarify(clarify_client, session_factory)
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")
    questions = next(
        d["input"]["questions"] for n, d in pause_frames if n == "tool_call"
    )

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
                "editedInput": {
                    "answers": [
                        {
                            "questionId": str(i),
                            "question": q,
                            "answer": _CLARIFY_ANSWERS[i],
                        }
                        for i, q in enumerate(questions)
                    ]
                },
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
    # C-001: paused clarify pseudo-tool is settled on the original row.
    call, result = _settled_clarify_parts(assistant[0].parts)
    assert call.get("approvalState") == "approved"
    assert call.get("status") == "succeeded"
    assert result is not None
    assert result.get("approvalState") == "approved"
    assert assistant[1].status == "done"


@pytest.mark.parametrize("requested_mode", [None, "single", "deep_research"])
async def test_clarify_resume_with_omitted_or_wrong_agentic_mode_is_pinned_or_rejected(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    requested_mode: str | None,
) -> None:
    """FL-28, clarify twin: the typed answers must survive the resume.

    The mode pin was gated on a worker continuation, which a clarify pause never
    has. An omitted `agenticMode` therefore settled the clarify gate and then ran
    a plain single turn — the answers the user had just typed were consumed and
    thrown away, unrecoverably. A conflicting `single` is a 400 that leaves the
    gate pending, so a correct-mode retry still delivers the answers.
    """
    conv_id, pause_frames = await _pause_on_clarify(clarify_client, session_factory)
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")
    questions = next(
        d["input"]["questions"] for n, d in pause_frames if n == "tool_call"
    )
    assert isinstance(questions, list)

    body: dict[str, object] = {
        "clientMessageId": "c0000000-0000-0000-0000-0000000000f1",
        "tierId": "smart",
        "text": "",
        "toolApproval": {
            "toolCallId": call_id,
            "decision": "approve",
            "editedInput": {
                "answers": [
                    {
                        "questionId": str(i),
                        "question": q,
                        "answer": _CLARIFY_ANSWERS[i],
                    }
                    for i, q in enumerate(questions)
                ]
            },
        },
    }
    if requested_mode is not None:
        body["agenticMode"] = requested_mode

    if requested_mode == "single":
        response = await clarify_client.post(
            f"/api/conversations/{conv_id}/messages", json=body, timeout=30.0
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_INPUT"
        msgs = await _load_messages(session_factory, conv_id)
        paused = next(m for m in msgs if m.status == "awaiting_approval")
        call, result = _settled_clarify_parts(paused.parts)
        # Rejected before the settle: the gate is untouched, answers not burned.
        assert call.get("approvalState") == "pending"
        assert result is None
        body["clientMessageId"] = "c0000000-0000-0000-0000-0000000000f2"
        body["agenticMode"] = "deep_research"

    frames = await _collect_sse(
        clarify_client, f"/api/conversations/{conv_id}/messages", body
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"
    started_ids = {str(d["subagentId"]) for n, d in frames if n == "subagent_started"}
    assert {"worker-0", "worker-1", "aggregator"} <= started_ids
    # The typed answers survive: they reach the workers AND the synthesis footer.
    full_answer = _answer(frames)
    assert "Clarified: Focus on housing affordability; US, last 5 years" in full_answer
    assert "Clarifications applied:" in full_answer


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
    call, result = _settled_clarify_parts(assistant[0].parts)
    assert call.get("approvalState") == "rejected"
    assert call.get("status") == "cancelled"
    assert result is not None
    assert result.get("approvalState") == "rejected"
    assert assistant[1].status == "done"


async def test_clarify_malformed_answers_rejected(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """C-006: wrong-shaped editedInput.answers must not silently continue."""
    conv_id, pause_frames = await _pause_on_clarify(clarify_client, session_factory)
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")

    resp = await clarify_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "c0000000-0000-0000-0000-000000000020",
            "tierId": "smart",
            "text": "",
            "agenticMode": "deep_research",
            "toolApproval": {
                "toolCallId": call_id,
                "decision": "approve",
                "editedInput": {"answers": "not-a-list"},
            },
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"


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
    clarify_call = next(d for n, d in clarify_frames if n == "tool_call")
    clarify_call_id = str(clarify_call["id"])
    questions = clarify_call["input"]["questions"]

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
                "editedInput": {
                    "answers": [
                        {
                            "questionId": str(i),
                            "question": q,
                            "answer": _CLARIFY_ANSWERS[i],
                        }
                        for i, q in enumerate(questions)
                    ]
                },
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
    clarifications = plan_call["input"]["clarifications"]
    assert isinstance(clarifications, list)
    assert [c["answer"] for c in clarifications] == list(_CLARIFY_ANSWERS)
    # C-002: question text must survive into plan-approval input (not blank).
    assert [c["question"] for c in clarifications] == list(questions)
    assert all(c["question"].strip() for c in clarifications)
    # Still no workers until the plan is approved.
    started_ids = {str(d["subagentId"]) for n, d in plan_pause if n == "subagent_started"}
    assert not any(sid.startswith("worker-") for sid in started_ids)

    # C-001: clarify row settled even after dual-HITL advance.
    msgs_mid = await _load_messages(session_factory, conv_id)
    clarify_row = next(
        m
        for m in msgs_mid
        if m.role == "assistant"
        and any(
            isinstance(p, dict)
            and p.get("type") == "tool_call"
            and p.get("name") == PLAN_CLARIFY_TOOL_NAME
            for p in (m.parts or [])
        )
    )
    call, result = _settled_clarify_parts(clarify_row.parts)
    assert call.get("approvalState") == "approved"
    assert result is not None

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


async def test_clarify_concurrent_opposite_decisions_one_wins(
    clarify_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Route-level race: approve vs deny — durable settle wins; loser 409s."""
    conv_id, pause_frames = await _pause_on_clarify(clarify_client, session_factory)
    call_id = next(str(d["id"]) for n, d in pause_frames if n == "tool_call")
    questions = next(
        d["input"]["questions"] for n, d in pause_frames if n == "tool_call"
    )
    url = f"/api/conversations/{conv_id}/messages"
    approve_body: dict[str, object] = {
        "clientMessageId": "c0000000-0000-0000-0000-000000000030",
        "tierId": "smart",
        "text": "",
        "agenticMode": "deep_research",
        "toolApproval": {
            "toolCallId": call_id,
            "decision": "approve",
            "editedInput": {
                "answers": [
                    {
                        "questionId": str(i),
                        "question": q,
                        "answer": _CLARIFY_ANSWERS[i],
                    }
                    for i, q in enumerate(questions)
                ]
            },
        },
    }
    deny_body: dict[str, object] = {
        "clientMessageId": "c0000000-0000-0000-0000-000000000031",
        "tierId": "smart",
        "text": "",
        "agenticMode": "deep_research",
        "toolApproval": {
            "toolCallId": call_id,
            "decision": "deny",
        },
    }

    r_approve, r_deny = await asyncio.gather(
        clarify_client.post(url, json=approve_body, timeout=30.0),
        clarify_client.post(url, json=deny_body, timeout=30.0),
    )
    codes = {r_approve.status_code, r_deny.status_code}
    assert 200 in codes
    assert 409 in codes
    winner_is_approve = r_approve.status_code == 200
    loser = r_deny if winner_is_approve else r_approve
    err = loser.json()["error"]["code"]
    assert err in (
        "APPROVAL_DECISION_CONFLICT",
        "APPROVAL_SETTLEMENT_INCOMPLETE",
        "STREAM_IN_PROGRESS",
    )

    msgs = await _load_messages(session_factory, conv_id)
    paused = next(
        m
        for m in msgs
        if m.role == "assistant"
        and any(
            isinstance(p, dict)
            and p.get("type") == "tool_call"
            and p.get("name") == PLAN_CLARIFY_TOOL_NAME
            for p in (m.parts or [])
        )
    )
    call, result = _settled_clarify_parts(paused.parts)
    assert result is not None
    durable = str(result.get("approvalState") or "")
    if winner_is_approve:
        assert durable == "approved"
        assert call.get("approvalState") == "approved"
        frames = _parse_sse(r_approve.text)
        assert frames[-1][1]["status"] == "done"
        started_ids = {
            str(d["subagentId"]) for n, d in frames if n == "subagent_started"
        }
        assert any(sid.startswith("worker-") for sid in started_ids)
    else:
        assert durable == "rejected"
        assert call.get("approvalState") == "rejected"
        frames = _parse_sse(r_deny.text)
        assert frames[-1][1]["status"] == "done"
        started_ids = {
            str(d["subagentId"]) for n, d in frames if n == "subagent_started"
        }
        assert not any(sid.startswith("worker-") for sid in started_ids)
