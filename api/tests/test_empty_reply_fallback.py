"""Empty-reply fallback coverage (RC-1/2/3/5/8)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.models import Conversation, Message, User
from app.db.session import get_db
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.providers.tiers import get_binding
from app.runtime.answer_policy import (
    EMPTY_REPLY_FALLBACK,
    EMPTY_REPLY_RETRY_NUDGE,
    contains_tool_markup,
    empty_reply_retry_nudge,
    main_answer_is_empty,
    strip_tool_markup,
)
from app.streaming.empty_reply_retry import run_chat_with_empty_retry
from app.streaming.handler import stream_and_persist
from app.tools.agent_loop import run_agent_loop

from .test_agentic_fanout import (
    _collect_sse,
    _grant_pro,
    _load_messages,
    _names,
    _seed_conversation,
)
from .test_providers_openai_stream import (
    _COMPLETIONS_URL,
    _search_provider,
    _sse_response,
    _stream_body,
    _tool_call_stream_body,
)

pytestmark = pytest.mark.asyncio

# A markup-only completion as the unsanitized Anthropic provider can yield it
# (raw tool-call markup relayed as answer text with no `ToolMarkupSanitizer`).
# `.strip()` sees non-whitespace (a naive guard thinks the turn answered), but
# `strip_tool_markup` truncates at the leading start marker so the shared
# `main_answer_is_empty` helper — and the FE — resolve it to empty.
_RAW_TOOL_MARKUP = '<｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="web_search">'


@pytest.fixture
def tools_env() -> Iterator[None]:
    prior = os.environ.get("TOOLS_ENABLED")
    os.environ["TOOLS_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("TOOLS_ENABLED", None)
        else:
            os.environ["TOOLS_ENABLED"] = prior
        get_settings.cache_clear()


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
def tools_app(
    tools_env: None,
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
async def tools_client(tools_app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=tools_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client_:
        yield client_


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
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def test_agent_loop_complete_only_after_tools_emits_fallback() -> None:
    """After tool activity, a Complete-only provider pass must not end blank."""
    from app.config import Settings

    tools_executed = False

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        nonlocal tools_executed

        async def _gen() -> AsyncIterator[ProviderEvent]:
            nonlocal tools_executed
            if not tools_executed:
                tools_executed = True
                yield ToolCall(id="c1", name="get_current_time", status="running")
                return
            yield Complete()

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer.strip() == EMPTY_REPLY_FALLBACK
    assert any(isinstance(e, Complete) for e in events)


@respx.mock
async def test_stream_web_search_round_cap_relays_non_empty_answer() -> None:
    """When every search round is tool-only, the relayed stream ends with text."""
    from app.providers.openai import _MAX_SEARCH_ROUNDS

    bodies = [
        _sse_response(_tool_call_stream_body(query=f"q{i}", prompt_tokens=2, completion_tokens=3))
        for i in range(_MAX_SEARCH_ROUNDS)
    ] + [
        _sse_response(
            _stream_body(
                prompt_tokens=1,
                completion_tokens=2,
                answer_chunks=("Search ", "summary."),
            )
        )
    ]
    route = respx.post(_COMPLETIONS_URL).mock(side_effect=bodies)

    provider = _search_provider()
    answer_parts: list[str] = []
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, AnswerDelta):
            answer_parts.append(event.text)

    assert route.call_count == _MAX_SEARCH_ROUNDS + 1
    assert "".join(answer_parts).strip() != ""
    assert "Search summary." in "".join(answer_parts)


@respx.mock
async def test_stream_reasoning_only_emits_reasoning_done() -> None:
    """Reasoning-only completions must close with ReasoningDone before Complete."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(
                prompt_tokens=10,
                completion_tokens=10,
                reasoning_chunks=("Thinking", " only"),
                answer_chunks=(),
            )
        )
    )

    provider = _search_provider()
    event_kinds: list[str] = []
    async for event in provider.stream(model_id="deepseek-v4-pro", history=[], user_text="hi"):
        if isinstance(event, ReasoningDelta):
            event_kinds.append("reasoning_delta")
        elif isinstance(event, ReasoningDone):
            event_kinds.append("reasoning_done")
        elif isinstance(event, Complete):
            event_kinds.append("complete")

    assert "reasoning_done" in event_kinds
    assert event_kinds.index("reasoning_done") < event_kinds.index("complete")


async def test_handler_done_with_tools_and_empty_answer_persists_fallback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Handler guard fills blank done turns that carried tool activity."""

    class _EmptyToolTurnProvider:
        async def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
            yield ToolCall(id="stub-1", name="web_search", status="running", input={"query": "x"})
            yield ToolResult(
                tool_call_id="stub-1",
                name="web_search",
                status="succeeded",
                summary="1 source",
                output={"query": "x", "results": []},
            )
            yield UsageUpdate(input_tokens=1, output_tokens=1)
            yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

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

    class _StubRequest:
        async def is_disconnected(self) -> bool:
            return False

    event_names: list[str] = []
    answer_frames: list[str] = []
    async with session_factory() as session:
        gen = stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=_EmptyToolTurnProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        )
        async for ev in gen:
            event_names.append(ev.event or "")
            if ev.event == "answer_delta" and ev.data:
                payload = json.loads(ev.data)
                answer_frames.append(str(payload.get("text", "")))

    assert EMPTY_REPLY_FALLBACK in answer_frames
    assert event_names.count("answer_delta") >= 1
    terminal_idx = event_names.index("terminal")
    last_answer_idx = len(event_names) - 1 - event_names[::-1].index("answer_delta")
    assert last_answer_idx < terminal_idx

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .order_by(Message.created_at.desc())
            )
        ).scalar_one()
        assert row.status == "done"
        parts = row.parts
        assert isinstance(parts, list)
        text_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        assert text_parts
        assert str(text_parts[0].get("text", "")).strip() == EMPTY_REPLY_FALLBACK


async def test_agentic_single_empty_primary_emits_fallback(
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
            "clientMessageId": "77777777-7777-7777-7777-777777777777",
            "tierId": "smart",
            "text": "TOOL_COMPLETE_ONLY: run tools then stop",
            "agenticMode": "single",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    primary_answer = "".join(
        str(d.get("text", ""))
        for n, d in frames
        if n == "answer_delta" and d.get("subagentId") == "primary"
    )
    assert primary_answer.strip() == EMPTY_REPLY_FALLBACK

    messages = await _load_messages(session_factory, conv_id)
    assistant = next(m for m in messages if m.role == "assistant")
    text_parts = [
        p for p in assistant.parts if isinstance(p, dict) and p.get("type") == "text"
    ]
    primary_text = next(
        str(p.get("text", "")) for p in text_parts if p.get("subagentId") == "primary"
    )
    assert primary_text.strip() == EMPTY_REPLY_FALLBACK


async def test_agent_loop_awaiting_approval_does_not_emit_fallback() -> None:
    """HITL pauses must never inject the empty-reply fallback."""
    from app.config import Settings

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield ToolCall(
                id="c1",
                name="calendar_create_event",
                status="awaiting_approval",
                approval_state="pending",
            )
            yield AwaitingApproval(tool_call_id="c1")

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    fallback_answers = [
        e for e in events if isinstance(e, AnswerDelta) and e.text == EMPTY_REPLY_FALLBACK
    ]
    assert not fallback_answers
    assert any(isinstance(e, AwaitingApproval) for e in events)


async def test_stopped_disconnect_does_not_persist_fallback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Stop-path persistence must not run the done-path fallback injector."""

    class _EmptyToolTurnProvider:
        async def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
            yield ToolCall(id="stub-1", name="web_search", status="running", input={"query": "x"})
            yield ToolResult(
                tool_call_id="stub-1",
                name="web_search",
                status="succeeded",
                summary="1 source",
                output={"query": "x", "results": []},
            )
            yield UsageUpdate(input_tokens=1, output_tokens=1)
            yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

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

    class _DisconnectAfterFirstPoll:
        def __init__(self) -> None:
            self._polls = 0

        async def is_disconnected(self) -> bool:
            self._polls += 1
            return self._polls > 1

    async with session_factory() as session:
        gen = stream_and_persist(
            request=_DisconnectAfterFirstPoll(),  # type: ignore[arg-type]
            db=session,
            provider=_EmptyToolTurnProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        )
        async for _ev in gen:
            pass

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .order_by(Message.created_at.desc())
            )
        ).scalar_one()
        assert row.status == "stopped"
        parts = row.parts
        assert isinstance(parts, list)
        text_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        if text_parts:
            assert EMPTY_REPLY_FALLBACK not in str(text_parts[0].get("text", ""))
        else:
            assert True


async def test_tool_complete_only_single_fallback_via_handler_and_agent_loop(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Agent-loop backstop + handler guard must not double-inject fallback text."""
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "88888888-8888-8888-8888-888888888888",
            "tierId": "smart",
            "text": "TOOL_COMPLETE_ONLY: tools then complete only",
        },
    )
    assert _names(frames)[-1] == "terminal"
    fallback_frames = [
        d
        for n, d in frames
        if n == "answer_delta" and str(d.get("text", "")) == EMPTY_REPLY_FALLBACK
    ]
    assert len(fallback_frames) == 1

    messages = await _load_messages(session_factory, conv_id)
    assistant = next(m for m in messages if m.role == "assistant")
    text_parts = [
        p for p in assistant.parts if isinstance(p, dict) and p.get("type") == "text"
    ]
    assert len(text_parts) == 1
    assert str(text_parts[0].get("text", "")).strip() == EMPTY_REPLY_FALLBACK


async def test_leak_markup_persists_raw_markup_through_tools_handler(
    tools_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """BE guard for `leaked-markup.spec.ts`: prose + markup persists the DSML.

    Drives the fake provider's `LEAK_MARKUP:` path (prose delta then a raw DSML
    tool-call block) through the tools-enabled handler + agent loop — the same
    wiring the e2e uses. The answer is non-empty (strips to the prose), so NO
    fallback fires and the raw markup must persist unchanged; the FE
    render-time scrub is what hides it. Regression guard: the agent loop must
    not drop the trailing markup delta.
    """
    await tools_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        tools_client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": "99999999-9999-9999-9999-999999999999",
            "tierId": "smart",
            "text": "LEAK_MARKUP: please leak tool markup",
        },
    )
    assert _names(frames)[-1] == "terminal"
    assert frames[-1][1]["status"] == "done"

    fallback_frames = [
        d
        for n, d in frames
        if n == "answer_delta" and str(d.get("text", "")) == EMPTY_REPLY_FALLBACK
    ]
    assert not fallback_frames

    messages = await _load_messages(session_factory, conv_id)
    assistant = next(m for m in messages if m.role == "assistant")
    text_parts = [
        p for p in assistant.parts if isinstance(p, dict) and p.get("type") == "text"
    ]
    persisted_text = "".join(str(p.get("text", "")) for p in text_parts)
    # The raw markup persists (the e2e asserts `persistedText` contains "DSML")
    # and the clean lead-in prose survives the FE scrub.
    assert "DSML" in persisted_text
    assert contains_tool_markup(persisted_text)
    assert "Sure, here is the answer you asked for." in strip_tool_markup(persisted_text)


async def test_handler_reasoning_only_blank_done_emits_reasoning_done_then_fallback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reasoning-only blank done turns close reasoning then inject fallback."""

    class _ReasoningOnlyBlankProvider:
        async def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
            yield ReasoningDelta(text="Thinking without answering.")
            yield UsageUpdate(input_tokens=5, output_tokens=0)
            yield Complete(usage=UsageUpdate(input_tokens=5, output_tokens=0))

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

    class _StubRequest:
        async def is_disconnected(self) -> bool:
            return False

    event_names: list[str] = []
    answer_texts: list[str] = []
    async with session_factory() as session:
        gen = stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=_ReasoningOnlyBlankProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        )
        async for ev in gen:
            event_names.append(ev.event or "")
            if ev.event == "answer_delta" and ev.data:
                answer_texts.append(str(json.loads(ev.data).get("text", "")))

    reasoning_done_idx = event_names.index("reasoning_done")
    fallback_idx = event_names.index("answer_delta")
    terminal_idx = event_names.index("terminal")
    assert reasoning_done_idx < fallback_idx < terminal_idx
    assert answer_texts == [EMPTY_REPLY_FALLBACK]


async def test_main_answer_is_empty_treats_raw_tool_markup_as_empty() -> None:
    """The shared helper's contract: markup-only / whitespace resolve empty."""
    assert main_answer_is_empty("") is True
    assert main_answer_is_empty("   \n\t ") is True
    assert main_answer_is_empty("A real written reply.") is False
    # The gap the helper closes: a naive `.strip()` guard would treat leaked
    # markup as a written answer; the markup-aware helper agrees with the FE.
    assert _RAW_TOOL_MARKUP.strip() != ""
    assert strip_tool_markup(_RAW_TOOL_MARKUP).strip() == ""
    assert main_answer_is_empty(_RAW_TOOL_MARKUP) is True


async def test_handler_raw_tool_markup_answer_injects_fallback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unsanitized raw markup in answer_buf is treated as empty → done injects.

    Simulates the Anthropic provider yielding raw tool-call markup as answer
    text (no `ToolMarkupSanitizer`). The old raw-`.strip()` guard thought the
    turn answered and skipped the inject; the shared markup-aware helper now
    resolves it to empty so the done-path injects `EMPTY_REPLY_FALLBACK`.
    """

    class _RawMarkupAnswerProvider:
        async def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text=_RAW_TOOL_MARKUP)
            yield UsageUpdate(input_tokens=1, output_tokens=1)
            yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

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

    class _StubRequest:
        async def is_disconnected(self) -> bool:
            return False

    event_names: list[str] = []
    answer_frames: list[str] = []
    async with session_factory() as session:
        gen = stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=_RawMarkupAnswerProvider(),  # type: ignore[arg-type]
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        )
        async for ev in gen:
            event_names.append(ev.event or "")
            if ev.event == "answer_delta" and ev.data:
                answer_frames.append(str(json.loads(ev.data).get("text", "")))

    # Done-path injected the fallback as a live answer_delta before terminal.
    assert EMPTY_REPLY_FALLBACK in answer_frames
    terminal_idx = event_names.index("terminal")
    last_answer_idx = len(event_names) - 1 - event_names[::-1].index("answer_delta")
    assert last_answer_idx < terminal_idx

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id)
                .order_by(Message.created_at.desc())
            )
        ).scalar_one()
        assert row.status == "done"
        parts = row.parts
        assert isinstance(parts, list)
        text_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        assert text_parts
        persisted_text = str(text_parts[0].get("text", ""))
        # Replace-on-inject: the persisted main text is the fallback ALONE — the
        # leaked markup was cleared, not left ahead of the fallback. So the
        # fallback SURVIVES the FE `stripToolMarkup` (truncate-from-first-marker)
        # on reload / share instead of being wiped to ''.
        assert strip_tool_markup(persisted_text).strip() == EMPTY_REPLY_FALLBACK
        assert not contains_tool_markup(persisted_text)


async def test_agent_loop_prose_then_trailing_markup_relays_raw_markup() -> None:
    """Prose + trailing leaked markup: the markup is KEPT (not dropped).

    A stubborn provider can stream real prose then dump raw tool-call markup as
    answer content. The combined answer is non-empty (strips to the prose), so
    NO fallback fires and the raw markup must be relayed intact — the FE
    render-time scrub is what hides it on reload / share. This is the exact
    shape the `LEAK_MARKUP:` e2e (`web/tests/e2e/leaked-markup.spec.ts`) drives
    through the agent loop, and it must persist the `DSML` markup.
    """
    from app.config import Settings

    prose = "Sure, here is the answer you asked for. "

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text=prose)
            yield AnswerDelta(text=_RAW_TOOL_MARKUP)
            yield Complete()

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    # Prose survives AND the raw markup is relayed unchanged (no drop, no
    # fallback) so the persisted transcript still carries the leaked markup.
    assert prose in answer
    assert _RAW_TOOL_MARKUP in answer
    assert contains_tool_markup(answer)
    assert EMPTY_REPLY_FALLBACK not in answer
    # FE-side scrub still resolves the rendered answer to the clean prose.
    assert strip_tool_markup(answer).strip() == prose.strip()


async def test_agent_loop_markup_only_drops_markup_and_injects_fallback() -> None:
    """Markup-only answer: the markup is DROPPED and the fallback stands alone.

    With no real prose the answer strips to empty, so the terminal fallback
    fires. Relaying the raw markup ahead of it would let the FE
    truncate-from-first-marker scrub wipe the fallback too, so the markup delta
    is dropped from the wire and only `EMPTY_REPLY_FALLBACK` is relayed.
    """
    from app.config import Settings

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield AnswerDelta(text=_RAW_TOOL_MARKUP)
            yield Complete()

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    answer_deltas = [e.text for e in events if isinstance(e, AnswerDelta)]
    assert answer_deltas == [EMPTY_REPLY_FALLBACK]
    assert not contains_tool_markup("".join(answer_deltas))


async def test_agent_loop_no_tools_empty_completion_emits_fallback() -> None:
    """No-tools empty completion still ends with the fallback (tools_ran drop).

    Before the change the terminal fallback was gated on `tools_ran`, so a
    completion that ran no tools AND produced no answer ended blank. The gate is
    now `not answer_emitted`, so a pathological blank no-tools turn is backstopped.
    """
    from app.config import Settings

    def _make_stream(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        async def _gen() -> AsyncIterator[ProviderEvent]:
            yield Complete()

        return _gen()

    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [ev async for ev in run_agent_loop(make_stream=_make_stream, settings=settings)]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer.strip() == EMPTY_REPLY_FALLBACK
    assert sum(1 for e in events if isinstance(e, AnswerDelta)) == 1
    assert any(isinstance(e, Complete) for e in events)


# --- Automatic empty-reply retry -------------------------------------------
#
# A `MakeStream` spy: each call `i` replays the events from `passes[i]` and
# records `(suppress_tools, answer_nudge)` in `.calls`. Missing passes yield an
# empty stream (defensive). Mirrors the real closures' keyword-only signature.


def _spy_make_stream(
    *passes: list[ProviderEvent],
) -> tuple[object, list[tuple[bool, bool]]]:
    calls: list[tuple[bool, bool]] = []

    def _make(
        _feedback: list[ToolResult],
        suppress_tools: bool = False,
        *,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        index = len(calls)
        calls.append((suppress_tools, answer_nudge))
        events = list(passes[index]) if index < len(passes) else []

        async def _gen() -> AsyncIterator[ProviderEvent]:
            for event in events:
                yield event

        return _gen()

    return _make, calls


async def test_empty_reply_retry_nudge_response_format_aware() -> None:
    """The nudge omits the plain-prose clause when structured output is wanted."""
    plain = empty_reply_retry_nudge(response_format_requested=False)
    structured = empty_reply_retry_nudge(response_format_requested=True)
    assert structured == EMPTY_REPLY_RETRY_NUDGE
    assert "plain prose" not in structured
    assert plain.startswith(EMPTY_REPLY_RETRY_NUDGE)
    assert plain.endswith("Respond in plain prose.")
    # Base copy is JSON-safe (no "plain text"/"prose" clause baked in).
    assert "prose" not in EMPTY_REPLY_RETRY_NUDGE


async def test_agent_loop_empty_retry_recovers() -> None:
    """Empty terminal → one suppress-tools+nudge retry recovers a real answer."""
    make, calls = _spy_make_stream(
        [Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))],
        [AnswerDelta(text="Recovered answer."), Complete()],
    )
    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer == "Recovered answer."
    assert EMPTY_REPLY_FALLBACK not in answer
    # Exactly one extra invocation, and it was the nudged suppress-tools pass.
    assert calls == [(False, False), (True, True)]
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is True
    assert complete.empty_retry_recovered is True


async def test_agent_loop_empty_retry_still_empty_static_once() -> None:
    """Retry also empty → exactly one static fallback, recovered marker false."""
    make, calls = _spy_make_stream(
        [Complete()],
        [Complete()],
    )
    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
    ]
    fallbacks = [
        e for e in events if isinstance(e, AnswerDelta) and e.text == EMPTY_REPLY_FALLBACK
    ]
    assert len(fallbacks) == 1
    # Retry attempted exactly once (no re-retry on the second empty).
    assert calls == [(False, False), (True, True)]
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is True
    assert complete.empty_retry_recovered is False


async def test_agent_loop_empty_retry_is_one_shot() -> None:
    """The one-shot latch prevents a second retry even across empty rounds."""
    make, calls = _spy_make_stream(
        [Complete()],  # round 0 empty terminal → spends the retry
        [Complete()],  # retry pass, still empty → static
    )
    settings = Settings(TOOL_MAX_ROUNDS=4)  # type: ignore[call-arg]
    _ = [
        ev
        async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
    ]
    # Only two streams ever opened: the initial pass + the single retry.
    assert len(calls) == 2
    assert calls[1] == (True, True)


async def test_agent_loop_reserved_pass_unconditional_and_nudge_free() -> None:
    """Reserved force-final pass fires unconditionally and carries NO nudge.

    With N=2 the sole action round still requests a tool, so the reserved
    suppress-tools final pass fires. It must be nudge-free and fire regardless of
    the empty-reply-retry kill switch; an empty reserved pass goes straight to the
    static fallback with NO extra retry pass (budget exhausted).
    """
    for enabled in (True, False):
        make, calls = _spy_make_stream(
            [ToolCall(id="c1", name="get_current_time", status="running")],
            [Complete()],  # reserved suppress-tools pass, empty
        )
        settings = Settings(  # type: ignore[call-arg]
            TOOL_MAX_ROUNDS=2, EMPTY_REPLY_RETRY_ENABLED=enabled
        )
        events = [
            ev
            async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
        ]
        answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
        assert answer.strip() == EMPTY_REPLY_FALLBACK
        # Exactly two streams: action round + reserved pass. The reserved pass is
        # suppress-tools but NEVER carries the answer nudge, and no retry follows.
        assert len(calls) == 2
        assert calls[1] == (True, False)
        complete = next(e for e in reversed(events) if isinstance(e, Complete))
        assert complete.empty_retry is False


async def test_agent_loop_tool_max_rounds_1_no_retry() -> None:
    """N=1 exhausts the budget on the sole round → no tool-path retry."""
    make, calls = _spy_make_stream([Complete()])
    settings = Settings(TOOL_MAX_ROUNDS=1)  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer.strip() == EMPTY_REPLY_FALLBACK
    assert len(calls) == 1  # no retry pass opened
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is False


async def test_agent_loop_flag_off_no_retry() -> None:
    """Kill-switch off → static immediately, no extra invocation."""
    make, calls = _spy_make_stream([Complete()])
    settings = Settings(  # type: ignore[call-arg]
        TOOL_MAX_ROUNDS=3, EMPTY_REPLY_RETRY_ENABLED=False
    )
    events = [
        ev
        async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer.strip() == EMPTY_REPLY_FALLBACK
    assert len(calls) == 1
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is False


async def test_agent_loop_worker_allow_empty_retry_false() -> None:
    """Worker subagents (allow_empty_retry=False) never spend the retry."""
    make, calls = _spy_make_stream([Complete()])
    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=make,  # type: ignore[arg-type]
            settings=settings,
            allow_empty_retry=False,
        )
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer.strip() == EMPTY_REPLY_FALLBACK
    assert len(calls) == 1
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is False


async def test_agent_loop_awaiting_approval_spends_no_retry_budget() -> None:
    """A HITL pause returns before the terminal decision — no retry pass."""
    make, calls = _spy_make_stream(
        [
            ToolCall(
                id="c1",
                name="calendar_create_event",
                status="awaiting_approval",
                approval_state="pending",
            ),
            AwaitingApproval(tool_call_id="c1"),
        ],
    )
    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_agent_loop(make_stream=make, settings=settings)  # type: ignore[arg-type]
    ]
    assert any(isinstance(e, AwaitingApproval) for e in events)
    assert not any(
        isinstance(e, AnswerDelta) and e.text == EMPTY_REPLY_FALLBACK for e in events
    )
    # Only the first stream ever opened; the pause spent no retry budget.
    assert len(calls) == 1


async def test_wrapper_empty_then_recovers_folds_usage() -> None:
    """Plain-chat wrapper: empty pass 1 → retry recovers; usage sums both."""
    make, calls = _spy_make_stream(
        [
            UsageUpdate(input_tokens=2, output_tokens=3),
            Complete(usage=UsageUpdate(input_tokens=2, output_tokens=3)),
        ],
        [
            AnswerDelta(text="Now answered."),
            UsageUpdate(input_tokens=5, output_tokens=7),
            Complete(usage=UsageUpdate(input_tokens=5, output_tokens=7)),
        ],
    )
    settings = Settings()  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_chat_with_empty_retry(make, settings)  # type: ignore[arg-type]
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer == "Now answered."
    assert calls == [(False, False), (True, True)]
    completes = [e for e in events if isinstance(e, Complete)]
    assert len(completes) == 1
    # Cumulative Complete tokens = pass1 + pass2.
    assert completes[0].usage.input_tokens == 7
    assert completes[0].usage.output_tokens == 10
    assert completes[0].empty_retry is True
    assert completes[0].empty_retry_recovered is True


async def test_wrapper_markup_drop_then_prose_persists() -> None:
    """Pass1 markup-only is dropped; pass2 prose is relayed intact (not wiped)."""
    make, _calls = _spy_make_stream(
        [AnswerDelta(text=_RAW_TOOL_MARKUP), Complete()],
        [AnswerDelta(text="Real prose answer."), Complete()],
    )
    settings = Settings()  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_chat_with_empty_retry(make, settings)  # type: ignore[arg-type]
    ]
    answer_deltas = [e.text for e in events if isinstance(e, AnswerDelta)]
    # The markup-only delta was dropped; only the prose reaches the wire.
    assert answer_deltas == ["Real prose answer."]
    assert not contains_tool_markup("".join(answer_deltas))


async def test_wrapper_non_empty_passthrough_no_retry() -> None:
    """A non-empty first pass is transparent — no second invocation."""
    make, calls = _spy_make_stream(
        [AnswerDelta(text="First answer."), Complete()],
        [AnswerDelta(text="SHOULD NOT RUN"), Complete()],
    )
    settings = Settings()  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_chat_with_empty_retry(make, settings)  # type: ignore[arg-type]
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer == "First answer."
    assert len(calls) == 1
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is False


async def test_wrapper_web_search_self_inject_not_retried() -> None:
    """A provider that self-injects the static string reads as answered — no retry."""
    make, calls = _spy_make_stream(
        [AnswerDelta(text=EMPTY_REPLY_FALLBACK), Complete()],
        [AnswerDelta(text="SHOULD NOT RUN"), Complete()],
    )
    settings = Settings()  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_chat_with_empty_retry(make, settings)  # type: ignore[arg-type]
    ]
    fallbacks = [
        e for e in events if isinstance(e, AnswerDelta) and e.text == EMPTY_REPLY_FALLBACK
    ]
    # Relayed exactly once (no double-inject), and no retry pass opened.
    assert len(fallbacks) == 1
    assert len(calls) == 1
    complete = next(e for e in reversed(events) if isinstance(e, Complete))
    assert complete.empty_retry is False


async def test_wrapper_both_empty_emits_no_static() -> None:
    """Both passes empty → wrapper emits no static text (handler is last resort)."""
    make, calls = _spy_make_stream([Complete()], [Complete()])
    settings = Settings()  # type: ignore[call-arg]
    events = [
        ev
        async for ev in run_chat_with_empty_retry(make, settings)  # type: ignore[arg-type]
    ]
    assert not any(isinstance(e, AnswerDelta) for e in events)
    assert len(calls) == 2
    completes = [e for e in events if isinstance(e, Complete)]
    assert len(completes) == 1
    assert completes[0].empty_retry is True
    assert completes[0].empty_retry_recovered is False


async def test_inject_empty_fallback_false_suppresses_static_filler() -> None:
    """FL-04: subagents that own their recovery must get a genuinely empty answer.

    Covers the no-tool terminal, the retry-exhausted terminal and the reserved
    final pass: every injection site is gated on the same flag, and the single
    terminal `Complete` still ships so the wire sees exactly one terminal.
    """
    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]

    # Empty terminal with the retry allowed: both the retry pass and the static
    # fallback must stay silent.
    make, calls = _spy_make_stream([Complete()], [Complete()])
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=make,  # type: ignore[arg-type]
            settings=settings,
            inject_empty_fallback=False,
        )
    ]
    assert not any(isinstance(e, AnswerDelta) for e in events)
    assert len([e for e in events if isinstance(e, Complete)]) == 1
    assert len(calls) == 2

    # Reserved final pass after a tool round: same suppression.
    make2, calls2 = _spy_make_stream(
        [ToolCall(id="c1", name="get_current_time", status="running")],
        [Complete()],
        [Complete()],
    )
    events2 = [
        ev
        async for ev in run_agent_loop(
            make_stream=make2,  # type: ignore[arg-type]
            settings=settings,
            inject_empty_fallback=False,
        )
    ]
    assert not any(isinstance(e, AnswerDelta) for e in events2)
    assert len([e for e in events2 if isinstance(e, Complete)]) == 1
    assert len(calls2) >= 2


async def test_inject_empty_fallback_default_still_injects_static_filler() -> None:
    """FL-04: the primary loop's default behavior is unchanged (guards #264)."""
    settings = Settings(TOOL_MAX_ROUNDS=3)  # type: ignore[call-arg]
    make, _calls = _spy_make_stream([Complete()], [Complete()])
    events = [
        ev
        async for ev in run_agent_loop(
            make_stream=make,  # type: ignore[arg-type]
            settings=settings,
        )
    ]
    fallbacks = [
        e
        for e in events
        if isinstance(e, AnswerDelta) and e.text == EMPTY_REPLY_FALLBACK
    ]
    assert len(fallbacks) == 1
    assert len([e for e in events if isinstance(e, Complete)]) == 1


async def test_aggregator_empty_draft_degrades_to_deterministic_synthesis() -> None:
    """FL-04: an empty aggregator draft must fall back to the worker findings.

    The injected filler used to make `main_answer_is_empty(streamed)` false, so
    the degrade was unreachable and total answer loss shipped as `partial=False`.
    """
    from app.agentic.aggregate import WorkerOutput
    from app.agentic.orchestrator import _finalize_synthesis_streamed
    from app.providers.protocol import RunCost, SubagentDone

    def _markup_only_stream(prompt: str, **_kwargs: object):
        def _make(
            _feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text=_RAW_TOOL_MARKUP)
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_VERIFIER=False,
        AGENTIC_RUN_BUDGET_USD=10.0,
    )
    events = [
        ev
        async for ev in _finalize_synthesis_streamed(
            make_stream_for=_markup_only_stream,
            settings=settings,
            user_text="req",
            outputs=[
                WorkerOutput(
                    subagent_id="w0", sub_question="alpha", answer="alpha finding"
                ),
                WorkerOutput(
                    subagent_id="w1", sub_question="beta", answer="beta finding"
                ),
            ],
            planned=2,
            worker_usages=[],
            worker_total_cost=0.0,
            cost_for_usage=lambda _u: 0.0,
            cap_usd=10.0,
            budget_halted=False,
            scaffolded=False,
        )
    ]
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert "alpha finding" in answer
    assert "beta finding" in answer
    assert EMPTY_REPLY_FALLBACK not in answer
    # The bracket still closes cleanly — this is a degrade, not a crash.
    done = next(e for e in events if isinstance(e, SubagentDone))
    assert done.role == "aggregator"
    assert done.outcome == "succeeded"
    finals = [e for e in events if isinstance(e, RunCost) and e.phase == "final"]
    assert finals and finals[-1].budget_halted is False
