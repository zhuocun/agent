"""Streaming endpoint tests.

Uses the fake provider (env defaults to `PROVIDER_BACKEND=fake`). httpx ASGI
transport doesn't expose mid-stream disconnect cleanly — the stop-path test is
marked xfail with a TODO citing the limitation. Production code still works;
the disconnect-detect path is exercised manually in dev.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, Stream, User
from app.db.repositories import streams as streams_repo
from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a captured SSE response body into (event, data-dict) tuples.

    sse-starlette emits frames with `\r\n` line endings; normalize first so we
    can split on the canonical SSE blank-line separator (`\n\n`).
    """
    normalized = response_text.replace("\r\n", "\n").replace("\r", "\n")
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
                # sse-starlette may emit multiple data: lines per frame; join.
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
    """POST `body` and return the parsed SSE frames."""
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        # Verify required headers.
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        assert resp.headers.get("cache-control") == "no-store"
        # Defeats nginx/CDN buffering (set in routes/conversations.py).
        assert resp.headers.get("x-accel-buffering") == "no"
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> str:
    """Create an owned conversation for the given user, return its id."""
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


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


# Happy path -------------------------------------------------------------------


async def test_send_message_happy_path_streams_and_persists(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Bootstrap creates the anonymous user.
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "hello world",
        },
    )

    # Event order: submitted -> reasoning_delta* -> reasoning_done -> answer_delta* -> terminal.
    event_names = [name for name, _ in frames]
    assert event_names[0] == "submitted"
    assert "reasoning_done" in event_names
    assert event_names[-1] == "terminal"

    # reasoning_done precedes any answer_delta.
    done_idx = event_names.index("reasoning_done")
    first_answer_idx = event_names.index("answer_delta")
    assert done_idx < first_answer_idx

    # Terminal payload assertions.
    terminal_payload = frames[-1][1]
    assert terminal_payload["status"] == "done"
    assert isinstance(terminal_payload["messageId"], str)
    attribution = terminal_payload["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["costConfidence"] == "exact"
    # The request asked for tier "smart"; the attribution must echo that
    # tier id and a non-empty model label (defended against silent breakage
    # of the tier-binding lookup).
    assert attribution["requestedTierId"] == "smart"
    assert isinstance(attribution.get("servedModelLabel"), str)
    assert attribution["servedModelLabel"] != ""
    breakdown = attribution["breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown["inputTokens"] > 0
    assert breakdown["outputTokens"] > 0
    assert breakdown["subtotalUsd"] > 0
    assert breakdown["longContext"]["flat"] is True
    # `exclude_none=True` strips substitution=None from the wire; M1 has no
    # fallback logic yet (M4), so its absence is the expected shape.
    assert attribution.get("substitution") is None

    # Confirm both messages persisted.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role.in_(["user", "assistant"]))
            )
        ).scalars().all()
        assert len(rows) == 2
        user_msg = next(r for r in rows if r.role == "user")
        asst_msg = next(r for r in rows if r.role == "assistant")
        assert user_msg.parts[0]["text"] == "hello world"
        # Assistant parts should include reasoning + text.
        types = [p["type"] for p in asst_msg.parts]
        assert "reasoning" in types
        assert "text" in types
        assert asst_msg.status == "done"
        assert asst_msg.attribution is not None

    # GET the conversation: both messages come back.
    get_resp = await client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert len(body["messages"]) == 2


async def test_custom_instructions_are_provider_only(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await client.get("/api/bootstrap")
    await client.put(
        "/api/preferences",
        json={
            "defaultTierId": "smart",
            "temporaryByDefault": False,
            "trainingOptIn": False,
            "sendOnEnter": True,
            "autoExpandReasoning": False,
            "telemetryEnabled": True,
            "customInstructions": "Always answer in terse bullets.",
            "retentionDays": None,
        },
    )
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    seen_prompts: list[str] = []
    seen_prefixes: list[str | None] = []

    class _CaptureProvider:
        async def stream(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            attachments: list[object] | None = None,
            api_key: str | None = None,
            thinking: bool | None = None,
            reasoning_effort: str | None = None,
            web_search: bool = False,
            supports_vision: bool = True,
            response_format: object | None = None,
            system_prefix: str | None = None,
            tools: list[object] | None = None,
        ) -> AsyncIterator[ProviderEvent]:
            seen_prompts.append(user_text)
            seen_prefixes.append(system_prefix)
            yield ReasoningDone()
            yield AnswerDelta(text="ok")
            usage = UsageUpdate(
                input_tokens=10,
                output_tokens=2,
                reasoning_tokens=0,
                cached_input_tokens=0,
            )
            yield Complete(usage=usage)

        async def complete(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            api_key: str | None = None,
            system_prefix: str | None = None,
        ) -> str:
            return "Custom Instructions Test"

    from app.routes import conversations as conversation_routes

    monkeypatch.setattr(
        conversation_routes,
        "build_provider",
        lambda *args, **kwargs: _CaptureProvider(),
    )

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "Summarize the launch plan.",
        },
    )
    assert frames[-1][0] == "terminal"
    assert seen_prompts
    # Custom instructions ride the cache-stable system prefix (T20), not the
    # user turn; the user turn stays the verbatim message.
    assert seen_prefixes[0] is not None
    assert "Always answer in terse bullets." in seen_prefixes[0]
    assert seen_prompts[0] == "Summarize the launch plan."

    async with session_factory() as session:
        user_msg = (
            await session.execute(select(Message).where(Message.role == "user"))
        ).scalar_one()
        assert user_msg.parts[0]["text"] == "Summarize the launch plan."


async def test_project_custom_instructions_reach_composed_user_turn(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Project's `customInstructions` are CONCATENATED with the user-global
    instructions (user first, project appended) and reach the same user-turn
    wrapper the user-global instructions use (D20). Unfiled conversations see
    only the user-global instructions (no project bleed)."""
    await client.get("/api/bootstrap")
    await client.put(
        "/api/preferences",
        json={
            "defaultTierId": "smart",
            "temporaryByDefault": False,
            "trainingOptIn": False,
            "sendOnEnter": True,
            "autoExpandReasoning": False,
            "telemetryEnabled": True,
            "customInstructions": "GLOBAL: be terse.",
            "retentionDays": None,
        },
    )
    # Project carrying its own shared instructions.
    project = await client.post(
        "/api/projects",
        json={"name": "Legal", "customInstructions": "PROJECT: cite statutes."},
    )
    project_id = project.json()["id"]
    user_id = await _current_user_id(session_factory)

    # One conversation filed under the project, one left unfiled.
    filed = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False, "projectId": project_id},
    )
    filed_id = filed.json()["id"]
    unfiled_id = await _seed_conversation(session_factory, user_id=user_id)

    seen_prompts: list[str] = []
    seen_prefixes: list[str | None] = []

    class _CaptureProvider:
        async def stream(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            attachments: list[object] | None = None,
            api_key: str | None = None,
            thinking: bool | None = None,
            reasoning_effort: str | None = None,
            web_search: bool = False,
            supports_vision: bool = True,
            response_format: object | None = None,
            system_prefix: str | None = None,
            tools: list[object] | None = None,
        ) -> AsyncIterator[ProviderEvent]:
            seen_prompts.append(user_text)
            seen_prefixes.append(system_prefix)
            yield ReasoningDone()
            yield AnswerDelta(text="ok")
            yield Complete(
                usage=UsageUpdate(
                    input_tokens=10,
                    output_tokens=2,
                    reasoning_tokens=0,
                    cached_input_tokens=0,
                )
            )

        async def complete(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            api_key: str | None = None,
            system_prefix: str | None = None,
        ) -> str:
            return "Project Instructions Test"

    from app.routes import conversations as conversation_routes

    monkeypatch.setattr(
        conversation_routes,
        "build_provider",
        lambda *args, **kwargs: _CaptureProvider(),
    )

    # Filed conversation: BOTH instructions reach the cache-stable system prefix
    # (T20), user-global first; the user turn stays the verbatim message.
    filed_frames = await _collect_sse(
        client,
        f"/api/conversations/{filed_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "Question one."},
    )
    assert filed_frames[-1][0] == "terminal"
    assert seen_prefixes
    filed_prefix = seen_prefixes[-1]
    assert filed_prefix is not None
    assert "GLOBAL: be terse." in filed_prefix
    assert "PROJECT: cite statutes." in filed_prefix
    assert seen_prompts[-1] == "Question one."
    # Ordering: user-global instructions precede the project's.
    assert filed_prefix.index("GLOBAL: be terse.") < filed_prefix.index(
        "PROJECT: cite statutes."
    )

    # Unfiled conversation: only the user-global instructions; no project bleed.
    unfiled_frames = await _collect_sse(
        client,
        f"/api/conversations/{unfiled_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "Question two."},
    )
    assert unfiled_frames[-1][0] == "terminal"
    unfiled_prefix = seen_prefixes[-1]
    assert unfiled_prefix is not None
    assert "GLOBAL: be terse." in unfiled_prefix
    assert "PROJECT: cite statutes." not in unfiled_prefix


async def test_send_message_with_attachment_streams_persists_metadata_only(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )

    event_names = [name for name, _ in frames]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"
    answer = "".join(
        str(payload.get("text", ""))
        for name, payload in frames
        if name == "answer_delta"
    )
    assert "Received attachments: paper.pdf." in answer

    async with session_factory() as session:
        user_msg = (
            await session.execute(select(Message).where(Message.role == "user"))
        ).scalar_one()
        assert user_msg.parts == [
            {"type": "text", "text": "please read this"},
            {
                "type": "attachment",
                "id": "att-1",
                "name": "paper.pdf",
                "mediaType": "pdf",
                "mimeType": "application/pdf",
                "sizeBytes": 5,
                "storagePolicy": "transient",
            },
        ]


async def test_send_message_with_text_attachment_extracts_transcript_metadata_only(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "summarize",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-text-1",
                    "name": "notes.txt",
                    "mediaType": "text",
                    "mimeType": "text/plain",
                    "sizeBytes": 16,
                    "contentBase64": "QWxwaGEgYmV0YSBub3Rlcw==",
                }
            ],
        },
    )

    answer = "".join(
        str(payload.get("text", ""))
        for name, payload in frames
        if name == "answer_delta"
    )
    assert "Received attachments: notes.txt." in answer
    assert "Extracted text: Alpha beta notes." in answer

    async with session_factory() as session:
        user_msg = (
            await session.execute(select(Message).where(Message.role == "user"))
        ).scalar_one()
        assert user_msg.parts == [
            {"type": "text", "text": "summarize"},
            {
                "type": "attachment",
                "id": "att-text-1",
                "name": "notes.txt",
                "mediaType": "text",
                "mimeType": "text/plain",
                "sizeBytes": 16,
                "storagePolicy": "transient",
            },
        ]


async def test_safety_blocklist_rejects_before_persisting_message(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("SAFETY_BACKEND", "local")
    monkeypatch.setenv("SAFETY_BLOCKLIST", "do-not-send")
    get_settings.cache_clear()
    try:
        await client.get("/api/bootstrap")
        user_id = await _current_user_id(session_factory)
        conv_id = await _seed_conversation(session_factory, user_id=user_id)

        response = await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "clientMessageId": str(uuid4()),
                "tierId": "fast",
                "text": "please do-not-send this",
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "SAFETY_BLOCKED"

        async with session_factory() as session:
            messages = (await session.execute(select(Message))).scalars().all()
            streams = (await session.execute(select(Stream))).scalars().all()
            assert messages == []
            assert streams == []
    finally:
        get_settings.cache_clear()


async def test_safety_blocklist_rejects_regenerate_before_mutating_history(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    initial = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "please do-not-send this",
        },
    )
    assert initial[-1][0] == "terminal"

    monkeypatch.setenv("SAFETY_BACKEND", "local")
    monkeypatch.setenv("SAFETY_BLOCKLIST", "do-not-send")
    get_settings.cache_clear()
    try:
        response = await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "clientMessageId": str(uuid4()),
                "tierId": "fast",
                "text": "ignored on regenerate",
                "regenerate": True,
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "SAFETY_BLOCKED"

        async with session_factory() as session:
            rows = (await session.execute(select(Message))).scalars().all()
            assert [row.role for row in rows] == ["user", "assistant"]
            streams = (await session.execute(select(Stream))).scalars().all()
            assert [stream.status for stream in streams] == ["done"]
    finally:
        get_settings.cache_clear()


async def test_safety_blocklist_rejects_saved_custom_instructions_before_provider(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    await client.get("/api/bootstrap")
    assert (
        await client.put(
            "/api/preferences",
            json={
                "defaultTierId": "smart",
                "temporaryByDefault": False,
                "trainingOptIn": False,
                "sendOnEnter": True,
                "autoExpandReasoning": False,
                "telemetryEnabled": True,
                "customInstructions": "Always include do-not-send.",
                "retentionDays": None,
            },
        )
    ).status_code == 204
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    monkeypatch.setenv("SAFETY_BACKEND", "local")
    monkeypatch.setenv("SAFETY_BLOCKLIST", "do-not-send")
    get_settings.cache_clear()
    try:
        response = await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "clientMessageId": str(uuid4()),
                "tierId": "fast",
                "text": "normal user message",
            },
        )

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "SAFETY_BLOCKED"
        assert error["meta"]["source"] == "custom_instructions"

        async with session_factory() as session:
            messages = (await session.execute(select(Message))).scalars().all()
            streams = (await session.execute(select(Stream))).scalars().all()
            assert messages == []
            assert streams == []
    finally:
        get_settings.cache_clear()


async def test_attachment_idempotent_replay_accepts_metadata_only_retry(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )
    first_terminal = next(payload for name, payload in first if name == "terminal")

    second = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                }
            ],
        },
    )

    assert [name for name, _ in second] == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "answer_delta",
        "terminal",
    ]
    assert second[-1][1]["messageId"] == first_terminal["messageId"]
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert len(rows) == 2


async def test_attachment_idempotency_rejects_changed_payload_digest(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )
    assert first[-1][0] == "terminal"

    changed = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": client_msg_id,
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 5,
                    "dataUrl": "data:application/pdf;base64,SEVMTE8=",
                }
            ],
        },
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"

    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert len(rows) == 2
        user_row = next(row for row in rows if row.role == "user")
        assert "attachmentPayloadSha256" in (user_row.request_fingerprint or {})


async def test_send_message_with_attachment_rejects_mismatched_payload_size(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "paper.pdf",
                    "mediaType": "pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 6,
                    "dataUrl": "data:application/pdf;base64,aGVsbG8=",
                }
            ],
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_ATTACHMENT"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


async def test_send_message_rejects_unextractable_text_attachment(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    binary_text = b"a\x00b\x00c\x00d\x00"
    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-text-binary",
                    "name": "notes.txt",
                    "mediaType": "text",
                    "mimeType": "text/plain",
                    "sizeBytes": len(binary_text),
                    "contentBase64": base64.b64encode(binary_text).decode("ascii"),
                }
            ],
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_ATTACHMENT"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


async def test_send_message_rejects_image_for_non_vision_tier(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An image to a non-vision binding fails cleanly with VISION_UNSUPPORTED.

    The fake `fast` tier is attachment-capable but NOT vision-capable, so an
    image is rejected at the route (defense-in-depth) rather than erroring at
    the provider. PDFs/text on the same tier still succeed (degraded to text).
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "what's in this image?",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-img-1",
                    "name": "sketch.png",
                    "mediaType": "image",
                    "mimeType": "image/png",
                    "sizeBytes": 5,
                    "dataUrl": "data:image/png;base64,aGVsbG8=",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VISION_UNSUPPORTED"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


async def test_send_message_rejects_unsupported_image_attachment_mime(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "fast",
            "text": "please read this",
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-svg",
                    "name": "vector.svg",
                    "mediaType": "image",
                    "mimeType": "image/svg+xml",
                    "sizeBytes": 11,
                    "dataUrl": "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ATTACHMENT"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


async def test_active_stream_rejects_before_persisting_user_message(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    async with session_factory() as session:
        await streams_repo.create_stream(session, conversation_id=UUID(conv_id))
        await session.commit()

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"clientMessageId": str(uuid4()), "tierId": "smart", "text": "blocked"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STREAM_IN_PROGRESS"
    async with session_factory() as session:
        messages = (await session.execute(select(Message))).scalars().all()
        streams = (await session.execute(select(Stream))).scalars().all()
        assert messages == []
        assert len(streams) == 1


async def test_active_stream_unique_loss_same_client_id_uses_idempotency_path(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.repositories import messages as messages_repo
    from app.routes import conversations as conversation_routes

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    client_msg_id = str(uuid4())
    original_create_stream = streams_repo.create_stream

    async def _lose_to_matching_request(
        db: AsyncSession,
        *,
        conversation_id: UUID,
    ) -> Stream:
        del db
        async with session_factory() as winner_session:
            await messages_repo.create_user_message(
                db=winner_session,
                conversation_id=conversation_id,
                client_message_id=UUID(client_msg_id),
                text="race",
            )
            await original_create_stream(winner_session, conversation_id=conversation_id)
            await winner_session.commit()
        raise streams_repo.ActiveStreamExistsError(str(conversation_id))

    monkeypatch.setattr(
        conversation_routes.streams_repo,
        "create_stream",
        _lose_to_matching_request,
    )

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"clientMessageId": client_msg_id, "tierId": "smart", "text": "race"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_IN_FLIGHT"
    async with session_factory() as session:
        messages = (await session.execute(select(Message))).scalars().all()
        streams = (await session.execute(select(Stream))).scalars().all()
        assert [message.client_message_id for message in messages] == [UUID(client_msg_id)]
        assert len(streams) == 1


# Idempotency ------------------------------------------------------------------


async def test_idempotent_replay_returns_prior_terminal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())

    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "ping",
        },
    )
    # Pull the terminal data so we can compare.
    first_terminal = next(payload for name, payload in first if name == "terminal")

    second = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": client_msg_id,
            "tierId": "smart",
            "text": "ping",
        },
    )

    # Replay reconstructs persisted reasoning before the final answer.
    event_names = [name for name, _ in second]
    assert event_names == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "answer_delta",
        "terminal",
    ]

    # The answer_delta payload carries the full prior answer text.
    second_answer = next(payload for name, payload in second if name == "answer_delta")
    second_terminal = next(payload for name, payload in second if name == "terminal")
    assert isinstance(second_answer.get("text"), str)
    assert len(second_answer["text"]) > 0
    # Terminal message id matches the persisted assistant message id (replay).
    assert second_terminal["messageId"] == first_terminal["messageId"]

    # No new rows.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role.in_(["user", "assistant"]))
            )
        ).scalars().all()
        assert len(rows) == 2


# Temporary chats --------------------------------------------------------------


async def test_temporary_conversation_streams_but_persists_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # Create a temporary conversation.
    create_resp = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": True},
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["isTemporary"] is True
    synthetic_id = body["id"]

    # GET on a temporary id returns 404.
    get_resp = await client.get(f"/api/conversations/{synthetic_id}")
    assert get_resp.status_code == 404

    # POST messages still works.
    frames = await _collect_sse(
        client,
        f"/api/conversations/{synthetic_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "temp hello",
            "isTemporary": True,
            "attachments": [
                {
                    "type": "attachment",
                    "id": "att-temp",
                    "name": "sketch.png",
                    "mediaType": "image",
                    "mimeType": "image/png",
                    "sizeBytes": 5,
                    "dataUrl": "data:image/png;base64,aGVsbG8=",
                }
            ],
        },
    )
    assert frames[0][0] == "submitted"
    assert frames[-1][0] == "terminal"
    answer = "".join(
        str(payload.get("text", ""))
        for name, payload in frames
        if name == "answer_delta"
    )
    assert "Received attachments: sketch.png." in answer

    # Confirm NO conversation or message rows.
    async with session_factory() as session:
        convos = (await session.execute(select(Conversation))).scalars().all()
        msgs = (await session.execute(select(Message))).scalars().all()
        assert convos == []
        assert msgs == []


# Ownership --------------------------------------------------------------------


async def test_send_message_to_other_users_conversation_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # Create a separate user B's conversation.
    async with session_factory() as session:
        other = User(is_anonymous=True, name="Other")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_user_id = other.id

    other_conv_id = await _seed_conversation(session_factory, user_id=other_user_id)

    response = await client.post(
        f"/api/conversations/{other_conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"

    # Ensure no Message rows were created in the other user's conversation.
    # A leak here would mean the ownership check ran AFTER the user-message
    # INSERT, which is a privacy hazard.
    from uuid import UUID

    async with session_factory() as session:
        leaked = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == UUID(other_conv_id)
                )
            )
        ).scalars().all()
        assert leaked == []


# Unknown tier -----------------------------------------------------------------


async def test_unknown_tier_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "bogus",
            "text": "hi",
        },
    )
    # 400 from request validation (Pydantic literal mismatch) or our explicit
    # INVALID_TIER envelope — either is acceptable per the spec.
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] in ("INVALID_INPUT", "INVALID_TIER")


async def test_send_message_provider_id_selects_alternate_binding(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.repositories import api_keys as api_keys_repo
    from app.providers.fake import FakeProvider
    from app.routes import conversations as conversation_routes

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        user.is_anonymous = False
        await api_keys_repo.upsert(
            session,
            user_id=user.id,
            provider="openai",
            raw_api_key="sk-openai-test-byok-12345678",
        )
        await session.commit()
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    calls: list[dict[str, object]] = []

    def _fake_build_provider(
        settings: object | None = None,
        *,
        provider_id: str | None = None,
        api_key: str | None = None,
    ) -> FakeProvider:
        calls.append({"settings": settings, "provider_id": provider_id, "api_key": api_key})
        return FakeProvider(delay_ms=0)

    monkeypatch.setattr(conversation_routes, "build_provider", _fake_build_provider)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "openai",
            "text": "use openai binding",
        },
    )

    assert calls[0]["provider_id"] == "openai"
    terminal = next(payload for name, payload in frames if name == "terminal")
    assert terminal["attribution"]["servedModelLabel"] == "gpt-4o"
    assert terminal["attribution"]["providerId"] == "openai"
    assert terminal["attribution"]["providerLabel"] == "OpenAI"


async def test_send_message_provider_id_missing_credentials_returns_400_before_insert(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "openai",
            "text": "hi",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


async def test_send_message_pending_provider_id_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "gemini",
            "text": "hi",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


async def test_send_message_unknown_provider_id_returns_400(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "bogus",
            "text": "hi",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PROVIDER"


async def test_send_message_fake_provider_id_returns_400_in_production(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings
    from app.routes import conversations as conversation_routes

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    monkeypatch.setattr(
        conversation_routes,
        "get_settings",
        lambda: Settings(
            provider_backend="deepseek",
            deepseek_api_key="k",
            env="production",
        ),
    )

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "fake",
            "text": "hi",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    async with session_factory() as session:
        rows = (await session.execute(select(Message))).scalars().all()
        assert rows == []


# M2: regenerate path ---------------------------------------------------------


async def test_regenerate_drops_trailing_assistant_and_re_streams(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A regen drops the prior assistant, keeps the user message id, re-streams."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1.
    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hello",
        },
    )
    first_submitted = next(p for n, p in first if n == "submitted")
    first_terminal = next(p for n, p in first if n == "terminal")
    user_msg_id_1 = first_submitted["messageId"]
    assistant_msg_id_1 = first_terminal["messageId"]

    # Snapshot DB.
    from uuid import UUID

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        # SQLite same-second timestamps may sort assistant before user when
        # `created_at` ties. Assert role membership, not order.
        assert len(rows) == 2
        roles = {r.role for r in rows}
        assert roles == {"user", "assistant"}

    # Regen (fresh clientMessageId — FE mints one).
    regen = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ignored on regen",  # body.text ignored; original is reused
            "regenerate": True,
        },
    )
    regen_submitted = next(p for n, p in regen if n == "submitted")
    regen_terminal = next(p for n, p in regen if n == "terminal")

    # User message id reused; assistant id is fresh.
    assert regen_submitted["messageId"] == user_msg_id_1
    assert regen_terminal["messageId"] != assistant_msg_id_1
    # Event ordering same as a fresh send.
    event_names = [n for n, _ in regen]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"

    # DB: original assistant gone, new assistant present, user unchanged.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert len(rows) == 2
        user_row = next(r for r in rows if r.role == "user")
        asst_row = next(r for r in rows if r.role == "assistant")
        assert str(user_row.id) == user_msg_id_1
        assert str(asst_row.id) != assistant_msg_id_1
        assert str(asst_row.id) == regen_terminal["messageId"]


async def test_regenerate_with_no_trailing_assistant_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regen on a fresh (no user message) conversation -> 400 INVALID_INPUT."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
            "regenerate": True,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


async def test_regenerate_rejects_persisted_attachments_for_unsupported_provider(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import UTC, datetime

    from app.db.repositories import api_keys as api_keys_repo

    await client.get("/api/bootstrap")
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        user.is_anonymous = False
        await api_keys_repo.upsert(
            session,
            user_id=user.id,
            provider="deepseek",
            raw_api_key="sk-deepseek-test-byok-12345678",
        )
        convo = Conversation(
            user_id=user.id,
            title="Attachment regen",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.flush()
        user_msg = Message(
            conversation_id=convo.id,
            client_message_id=uuid4(),
            role="user",
            parts=[
                {"type": "text", "text": "inspect this"},
                {
                    "type": "attachment",
                    "id": "att-1",
                    "name": "diagram.png",
                    "mediaType": "image",
                    "mimeType": "image/png",
                    "sizeBytes": 1234,
                },
            ],
            status=None,
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        session.add(user_msg)
        await session.flush()
        assistant = Message(
            conversation_id=convo.id,
            client_message_id=None,
            role="assistant",
            parts=[{"type": "text", "text": "ok"}],
            status="done",
            attribution={
                "requestedTierId": "smart",
                "servedTierId": "smart",
                "servedModelLabel": "Fake",
                "providerId": "fake",
                "providerLabel": "Fake",
                "isByok": False,
                "costUsd": 0.0,
                "costConfidence": "exact",
                "breakdown": {
                    "currency": "USD",
                    "listPriceInPerM": 0,
                    "listPriceOutPerM": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "reasoningTokens": 0,
                    "cachedInputTokens": 0,
                    "longContext": {"flat": True, "tokensRepriced": "none"},
                    "promoApplied": False,
                    "subtotalUsd": 0,
                    "sessionSurchargeUsd": 0,
                },
            },
            responds_to_message_id=user_msg.id,
            created_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
        )
        session.add(assistant)
        await session.commit()
        conv_id = str(convo.id)
        assistant_id = assistant.id

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "deepseek",
            "text": "ignored",
            "regenerate": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ATTACHMENTS_UNSUPPORTED"
    async with session_factory() as session:
        row = (
            await session.execute(select(Message).where(Message.id == assistant_id))
        ).scalar_one_or_none()
        assert row is not None


# Continue stopped turn --------------------------------------------------------


async def _mark_trailing_assistant_stopped(
    session_factory: async_sessionmaker[AsyncSession],
    conv_id: str,
) -> tuple[str, str]:
    """Flip the trailing assistant row to `status="stopped"` (simulates a Stop).

    Returns `(stopped_assistant_id, responds_to_message_id)`. Mid-stream
    disconnect isn't reproducible over httpx's ASGI transport, so we persist a
    normal turn then mutate its status to model the Stop outcome the continue
    path consumes.
    """
    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message)
                .where(
                    Message.conversation_id == UUID(conv_id),
                    Message.role == "assistant",
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
        ).scalar_one()
        asst.status = "stopped"
        await session.commit()
        return str(asst.id), str(asst.responds_to_message_id)


async def test_continue_appends_linked_assistant_and_keeps_partial(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Continue keeps the stopped partial and streams a NEW linked assistant."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1 — a normal turn we then mark stopped to model an interrupted turn.
    first = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hello"},
    )
    user_msg_id = next(p for n, p in first if n == "submitted")["messageId"]
    stopped_id, responds_to = await _mark_trailing_assistant_stopped(
        session_factory, conv_id
    )
    assert responds_to == user_msg_id

    # Usage before the continue, to assert the meter increments.
    async with session_factory() as session:
        from app.db.models import UsageRollup

        used_before = (
            await session.execute(select(UsageRollup.used).where(UsageRollup.user_id == user_id))
        ).scalar_one()

    # Continue (fresh clientMessageId — the FE mints one like regenerate).
    cont = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ignored on continue",
            "continueTurn": True,
        },
    )
    cont_submitted = next(p for n, p in cont if n == "submitted")
    cont_terminal = next(p for n, p in cont if n == "terminal")
    # submitted echoes the SAME user message id the stopped turn responded to.
    assert cont_submitted["messageId"] == user_msg_id
    # A NEW assistant message — not the stopped one.
    assert cont_terminal["messageId"] != stopped_id
    # The continuation answer streamed (fake's deterministic trigger).
    answer = "".join(str(p.get("text", "")) for n, p in cont if n == "answer_delta")
    assert answer.startswith("…continued: ")

    # DB: stopped partial row NOT deleted; new assistant linked to same user msg.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assistants = [r for r in rows if r.role == "assistant"]
        assert len(assistants) == 2  # stopped partial + continuation
        stopped_row = next(r for r in assistants if str(r.id) == stopped_id)
        new_row = next(r for r in assistants if str(r.id) == cont_terminal["messageId"])
        assert stopped_row.status == "stopped"
        assert str(new_row.responds_to_message_id) == user_msg_id

        from app.db.models import UsageRollup

        used_after = (
            await session.execute(select(UsageRollup.used).where(UsageRollup.user_id == user_id))
        ).scalar_one()
        assert used_after == used_before + 1


async def test_continue_with_regenerate_is_mutually_exclusive(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """continueTurn + regenerate in one body -> 400 INVALID_INPUT."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
            "continueTurn": True,
            "regenerate": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_continue_with_no_stopped_turn_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Continue when the trailing turn is `done` (not stopped) -> 400."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # A completed turn — its assistant persists with status="done".
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hello"},
    )
    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ignored",
            "continueTurn": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NOTHING_TO_CONTINUE"


# M2: edit path ---------------------------------------------------------------


async def test_edit_truncates_and_re_streams(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Edit truncates from the target inclusive, inserts new user, re-streams."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1.
    t1 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "turn 1"},
    )
    t1_user_id = next(p for n, p in t1 if n == "submitted")["messageId"]
    # Turn 2.
    t2 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "turn 2"},
    )
    t2_user_id = next(p for n, p in t2 if n == "submitted")["messageId"]
    # Turn 3.
    t3 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "turn 3"},
    )
    t3_user_id = next(p for n, p in t3 if n == "submitted")["messageId"]
    t3_assistant_id = next(p for n, p in t3 if n == "terminal")["messageId"]

    from uuid import UUID

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert len(rows) == 6  # 3 user + 3 assistant

    # Edit turn-2 user message: truncate it + everything after.
    edit_client_id = str(uuid4())
    edit_body = {
        "clientMessageId": edit_client_id,
        "tierId": "smart",
        "text": "edited turn 2",
        "editMessageId": t2_user_id,
    }
    edit_resp = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        edit_body,
    )
    edit_user_id = next(p for n, p in edit_resp if n == "submitted")["messageId"]
    edit_assistant_id = next(p for n, p in edit_resp if n == "terminal")["messageId"]

    retry_resp = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        edit_body,
    )
    retry_submitted = next(p for n, p in retry_resp if n == "submitted")["messageId"]
    retry_terminal = next(p for n, p in retry_resp if n == "terminal")["messageId"]
    assert retry_submitted == edit_user_id
    assert retry_terminal == edit_assistant_id

    # submitted carries a NEW user message id (not the edited one).
    assert edit_user_id != t2_user_id
    # Event ordering same as a fresh send.
    event_names = [n for n, _ in edit_resp]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"

    # DB shape: turn 1 (user + assistant) preserved; turn 2 user gone; turn 3
    # gone; new user + assistant inserted at the truncation point.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == UUID(conv_id))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars().all()
        assert len(rows) == 4
        ids = {str(r.id) for r in rows}
        # Turn 1 preserved.
        assert t1_user_id in ids
        # Old turn-2 user, turn-3 user + assistant all gone.
        assert t2_user_id not in ids
        assert t3_user_id not in ids
        assert t3_assistant_id not in ids
        # New rows present.
        assert edit_user_id in ids
        assert edit_assistant_id in ids
        # Confirm the new user message has the edited text.
        new_user = next(r for r in rows if str(r.id) == edit_user_id)
        assert new_user.parts[0]["text"] == "edited turn 2"


async def test_edit_with_unknown_message_id_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """editMessageId pointing to a uuid not in this conversation -> 400."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
            "editMessageId": str(uuid4()),
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


async def test_edit_with_assistant_message_id_errors(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """editMessageId pointing to an assistant row -> 400."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Build turn 1 to get an assistant message id.
    t1 = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "hi"},
    )
    assistant_id = next(p for n, p in t1 if n == "terminal")["messageId"]

    response = await client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "bad edit",
            "editMessageId": assistant_id,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"


# M2: title autogen -----------------------------------------------------------


async def test_title_autogen_updates_title_on_first_terminal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """First terminal -> detached task updates conversation.title.

    Timing: the fake provider's `complete()` returns synchronously (no
    sleeps). The detached task runs against a fresh session and should
    finish within a few hundred ms. Poll with a 2s ceiling.
    """
    import asyncio
    from uuid import UUID

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "ping"},
    )

    # Poll until the title flips off "New chat" or we hit the timeout.
    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    final_title: str = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            final_title = row.title
        if final_title and final_title != "New chat":
            break
        await asyncio.sleep(interval)
        elapsed += interval

    assert final_title != "New chat"
    assert final_title.strip() != ""


async def test_title_autogen_uses_selected_provider_context(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import UUID

    from app.db.repositories import api_keys as api_keys_repo
    from app.providers.fake import FakeProvider
    from app.routes import conversations as conversation_routes
    from app.streaming import handler as streaming_handler

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    plaintext_key = "sk-openai-test-byok-12345678"
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        user.is_anonymous = False
        await api_keys_repo.upsert(
            session,
            user_id=user.id,
            provider="openai",
            raw_api_key=plaintext_key,
        )
        await session.commit()
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    def _main_provider(
        settings: object | None = None,
        *,
        provider_id: str | None = None,
        api_key: str | None = None,
    ) -> FakeProvider:
        return FakeProvider(delay_ms=0)

    title_calls: list[dict[str, object]] = []

    class TitleProvider(FakeProvider):
        async def complete(
            self,
            *,
            model_id: str,
            history: list[ChatMessage],
            user_text: str,
            api_key: str | None = None,
        ) -> str:
            title_calls.append(
                {
                    "model_id": model_id,
                    "history": history,
                    "api_key": api_key,
                }
            )
            return "Selected Provider Title"

    def _title_provider(
        settings: object | None = None,
        *,
        provider_id: str | None = None,
        api_key: str | None = None,
    ) -> TitleProvider:
        title_calls.append({"provider_id": provider_id, "api_key": api_key})
        return TitleProvider(delay_ms=0)

    monkeypatch.setattr(conversation_routes, "build_provider", _main_provider)
    monkeypatch.setattr(streaming_handler, "build_provider", _title_provider)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "openai",
            "text": "first turn",
        },
    )
    assert frames[-1][0] == "terminal"

    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    final_title = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            final_title = row.title
        if final_title == "Selected Provider Title":
            break
        await asyncio.sleep(interval)
        elapsed += interval

    assert title_calls[0] == {"provider_id": "openai", "api_key": plaintext_key}
    assert title_calls[1]["model_id"] == "gpt-4o-mini"
    assert title_calls[1]["api_key"] == plaintext_key
    assert final_title == "Selected Provider Title"


async def test_title_autogen_does_not_re_fire_on_second_terminal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Second turn must NOT overwrite the title (first-terminal gate)."""
    import asyncio
    from uuid import UUID

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1 fires autogen.
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "first"},
    )
    # Wait for the title to flip.
    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    first_title = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            first_title = row.title
        if first_title and first_title != "New chat":
            break
        await asyncio.sleep(interval)
        elapsed += interval
    assert first_title != "New chat"

    # Manually rename to a sentinel so we can detect any overwrite.
    sentinel = "Manually renamed title"
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        row.title = sentinel
        await session.commit()

    # Turn 2 must NOT overwrite the sentinel.
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "second"},
    )
    # Give any rogue autogen task a chance to overwrite.
    await asyncio.sleep(0.4)
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        assert row.title == sentinel


async def test_regenerate_does_not_re_fire_title_autogen(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regen of the first turn deletes the prior assistant, leaving the
    assistant-count at 0 immediately before the new assistant persists. Without
    the `is_initial` gate, this would re-fire title autogen and clobber a
    user-renamed title. Confirm the gate keeps the user-set title intact.
    """
    import asyncio
    from uuid import UUID

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1 fires autogen; wait for the title to flip off "New chat".
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {"clientMessageId": str(uuid4()), "tierId": "smart", "text": "first"},
    )
    deadline = 2.0
    interval = 0.05
    elapsed = 0.0
    first_title = "New chat"
    while elapsed < deadline:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.id == UUID(conv_id))
                )
            ).scalar_one()
            first_title = row.title
        if first_title and first_title != "New chat":
            break
        await asyncio.sleep(interval)
        elapsed += interval
    assert first_title != "New chat"

    # User manually renames the conversation.
    sentinel = "User picked this title"
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        row.title = sentinel
        await session.commit()

    # Regen the (now sole) turn. This drops the trailing assistant, so the
    # assistant-count is 0 before the new assistant persists. The `is_initial`
    # gate must prevent autogen from overwriting the user's title.
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ignored on regen",
            "regenerate": True,
        },
    )
    await asyncio.sleep(0.4)
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(conv_id))
            )
        ).scalar_one()
        assert row.title == sentinel


# POST /api/conversations creation --------------------------------------------


async def test_post_conversation_creates_persisted_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "New chat"
    assert body["isTemporary"] is False
    assert body["messages"] == []
    assert body["selectedTierId"] == "smart"

    # Persisted in DB.
    async with session_factory() as session:
        rows = (await session.execute(select(Conversation))).scalars().all()
        assert len(rows) == 1


async def test_post_conversation_with_unknown_tier_returns_400(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/conversations",
        json={"selectedTierId": "bogus", "isTemporary": False},
    )
    assert response.status_code == 400


# M4: forced provider fallback ------------------------------------------------


async def test_forced_fallback_emits_substitution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_FALLBACK:` user_text marker → fake provider emits Complete with
    `substitution="provider_fallback"`; the terminal frame's attribution
    carries `substitution.reasonCode="provider_fallback"`.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_FALLBACK: please answer",
        },
    )
    terminal_payload = next(p for n, p in frames if n == "terminal")
    attribution = terminal_payload["attribution"]
    assert isinstance(attribution, dict)
    sub = attribution.get("substitution")
    assert sub is not None, "expected substitution on forced-fallback turn"
    assert isinstance(sub, dict)
    assert sub["reasonCode"] == "provider_fallback"
    # reason_text is canonical-from-builder; assert it's non-empty.
    assert isinstance(sub["reasonText"], str)
    assert len(sub["reasonText"]) > 0
    # Sanity: requested vs served tier ids round-trip unchanged.
    assert attribution["requestedTierId"] == "smart"
    assert attribution["servedTierId"] == "smart"


async def test_happy_path_substitution_is_none(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Without the FORCE_FALLBACK marker, attribution.substitution is absent."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "ordinary turn",
        },
    )
    terminal_payload = next(p for n, p in frames if n == "terminal")
    attribution = terminal_payload["attribution"]
    # `exclude_none=True` on the JSON dump means absence on the wire.
    assert attribution.get("substitution") is None


# Stop path --------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "httpx ASGITransport does not expose mid-stream client disconnect. "
        "The stop-path is implemented in handler.py (polling "
        "request.is_disconnected() between yields + cancelling the provider "
        "task) and exercised manually in dev; an integration test would "
        "require a real uvicorn server + abortable HTTP client."
    ),
    strict=False,
)
async def test_stop_path_persists_with_status_stopped(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    _ = await _seed_conversation(session_factory, user_id=user_id)

    # Intentionally fail — see xfail reason above.
    assert False, "stop-path test requires real HTTP transport"


# Deterministic stop path (no real server) -------------------------------------


async def test_stop_path_atomic_persist_and_usage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Drive `stream_and_persist` with a Request stub that reports connected
    for the first poll then disconnected, against the controlled fake
    provider. The now-atomic stop path must:

    - persist the assistant row with status="stopped" and an estimate
      attribution, and
    - increment the usage meter in the SAME commit,
    - WITHOUT emitting a `terminal` frame (socket already closed).

    Complements the route-level xfail above by exercising the disconnect
    branch directly (httpx ASGITransport can't surface mid-stream disconnect).
    """
    from app.db.models import UsageRollup
    from app.providers.fake import FakeProvider
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

    class _DisconnectAfterFirstPoll:
        """is_disconnected(): connected for the first poll, then disconnected.

        Letting one poll return False allows `submitted` to be yielded and the
        provider to start streaming before the disconnect is detected, so the
        accumulators carry partial parts on the stopped row.
        """

        def __init__(self) -> None:
            self._polls = 0

        async def is_disconnected(self) -> bool:
            self._polls += 1
            return self._polls > 1

    event_names: list[str] = []
    async with session_factory() as session:
        # delay_ms=0 keeps the fake fast; the disconnect fires on poll #2.
        provider = FakeProvider(delay_ms=0)
        gen = stream_and_persist(
            request=_DisconnectAfterFirstPoll(),  # type: ignore[arg-type]
            db=session,
            provider=provider,
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

    # No terminal on disconnect; submitted is allowed (sent before the loop).
    assert "terminal" not in event_names
    assert event_names[0] == "submitted"

    # Assistant row persisted as stopped with an estimate attribution.
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalars().all()
        assert len(rows) == 1
        asst = rows[0]
        assert asst.status == "stopped"
        assert asst.attribution is not None
        assert asst.attribution["costConfidence"] == "estimate"

        # Atomic: the usage meter incremented in the same commit.
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        assert rollup.used == 1


# Mid-stream provider error ----------------------------------------------------


async def test_mid_stream_error_emits_error_frame_and_persists_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_ERROR:` makes the fake provider raise mid-stream. The client
    must receive an SSE `error` frame (an ErrorEnvelope) and NO `terminal`,
    and NO assistant row may be persisted/committed for the turn (the
    provider error is not a successful turn).
    """
    from app.streaming.handler import _BG_TASKS

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_ERROR: blow up mid-stream",
        },
    )
    event_names = [name for name, _ in frames]
    # An `error` frame terminates the stream; no `terminal` on failure.
    assert event_names[-1] == "error"
    assert "terminal" not in event_names

    # The error frame is a well-formed ErrorEnvelope.
    error_payload = frames[-1][1]
    assert error_payload["code"] == "PROVIDER_UPSTREAM"
    assert error_payload["severity"] == "error"
    assert isinstance(error_payload["title"], str)
    assert isinstance(error_payload["body"], str)

    # Some answer text streamed before the raise (a couple of deltas).
    assert "answer_delta" in event_names

    # No assistant row persisted; the user row may exist (persisted on submit).
    async with session_factory() as session:
        assistants = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalars().all()
        assert assistants == []

    # No leaked background task: title autogen only fires on a successful
    # terminal, so the error turn must not have scheduled one.
    assert all(t.done() for t in _BG_TASKS)


async def test_mid_stream_rate_limit_surfaces_typed_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_RATE_LIMIT:` makes the fake provider raise a typed
    AppError(RATE_LIMITED) mid-stream. The handler must surface that envelope
    verbatim — code RATE_LIMITED with retryAfterMs — rather than flattening it
    to a generic PROVIDER_UPSTREAM, and persist no assistant row.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_RATE_LIMIT: slow down",
        },
    )
    event_names = [name for name, _ in frames]
    assert event_names[-1] == "error"
    assert "terminal" not in event_names

    error_payload = frames[-1][1]
    assert error_payload["code"] == "RATE_LIMITED"
    assert error_payload["retryAfterMs"] == 4200

    async with session_factory() as session:
        assistants = (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalars().all()
        assert assistants == []


# Web search ------------------------------------------------------------------


async def test_web_search_emits_status_sources_and_persists_parts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`webSearch=true` -> status/sources plus persisted tool transcript parts."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            "webSearch": True,
        },
    )
    event_names = [name for name, _ in frames]
    # Search/tool wire events appear in the right relative order.
    assert "tool_call" in event_names
    assert "tool_result" in event_names
    assert "status" in event_names
    assert "sources" in event_names
    tool_call_idx = event_names.index("tool_call")
    status_idx = event_names.index("status")
    sources_idx = event_names.index("sources")
    tool_result_idx = event_names.index("tool_result")
    first_answer_idx = event_names.index("answer_delta")
    terminal_idx = event_names.index("terminal")
    # LIVE wire order follows the provider emission: tool call -> status ->
    # sources/result -> answer, all before terminal.
    assert tool_call_idx < status_idx
    assert status_idx < sources_idx
    assert sources_idx < tool_result_idx
    assert tool_result_idx < first_answer_idx
    assert sources_idx < first_answer_idx
    assert first_answer_idx < terminal_idx

    tool_call_payload = next(p for n, p in frames if n == "tool_call")
    assert tool_call_payload["name"] == "web_search"
    assert tool_call_payload["status"] == "running"
    assert tool_call_payload["input"]["query"] == "what is rust"

    tool_result_payload = next(p for n, p in frames if n == "tool_result")
    assert tool_result_payload["toolCallId"] == tool_call_payload["id"]
    assert tool_result_payload["status"] == "succeeded"
    assert tool_result_payload["output"]["results"]

    # The `sources` payload carries the deterministic fake citations (ids 1..3).
    sources_payload = next(p for n, p in frames if n == "sources")
    items = sources_payload["items"]
    assert isinstance(items, list)
    assert [it["id"] for it in items] == [1, 2, 3]
    for it in items:
        assert isinstance(it["title"], str)
        assert isinstance(it["url"], str)

    # The `status` payload's final state is `done`.
    status_payloads = [p for n, p in frames if n == "status"]
    assert status_payloads[-1]["state"] == "done"

    # Persisted assistant parts include the durable tool transcript.
    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        part_types = [p["type"] for p in asst.parts]
        assert part_types == [
            "reasoning",
            "tool_call",
            "tool_result",
            "status",
            "text",
            "sources",
        ]
        tool_call_part = next(p for p in asst.parts if p["type"] == "tool_call")
        assert tool_call_part["input"]["query"] == "what is rust"
        tool_result_part = next(p for p in asst.parts if p["type"] == "tool_result")
        assert tool_result_part["toolCallId"] == tool_call_part["id"]
        status_part = next(p for p in asst.parts if p["type"] == "status")
        assert status_part["state"] == "done"
        sources_part = next(p for p in asst.parts if p["type"] == "sources")
        assert [it["id"] for it in sources_part["items"]] == [1, 2, 3]

    # GET round-trips the new parts through the wire schema (validates the union).
    get_resp = await client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    asst_msg = next(m for m in body["messages"] if m["role"] == "assistant")
    wire_types = [p["type"] for p in asst_msg["parts"]]
    assert "status" in wire_types
    assert "sources" in wire_types
    assert "tool_call" in wire_types
    assert "tool_result" in wire_types


async def test_web_search_omitted_is_byte_for_byte_unchanged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`webSearch` omitted/false -> NO status/sources frames or parts (no-op).

    Regression-critical: the non-search turn must be identical to the historical
    stream — no `status`, no `sources`, and the persisted parts stay
    [reasoning] [text].
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "what is rust",
            # webSearch intentionally omitted (defaults False).
        },
    )
    event_names = [name for name, _ in frames]
    assert "status" not in event_names
    assert "sources" not in event_names
    assert "tool_call" not in event_names
    assert "tool_result" not in event_names
    # The classic shape is intact.
    assert event_names[0] == "submitted"
    assert "reasoning_done" in event_names
    assert "answer_delta" in event_names
    assert event_names[-1] == "terminal"

    # Persisted parts unchanged: [reasoning] [text], no status/sources/tools.
    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        part_types = [p["type"] for p in asst.parts]
        assert part_types == ["reasoning", "text"]


async def test_web_search_replay_reconstructs_status_and_sources(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An idempotent re-POST of a web-search turn replays the persisted parts
    back into `status` + `sources` frames so a reconnecting client still sees
    the grounded turn's citations."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    client_msg_id = str(uuid4())
    body = {
        "clientMessageId": client_msg_id,
        "tierId": "smart",
        "text": "what is rust",
        "webSearch": True,
    }
    await _collect_sse(client, f"/api/conversations/{conv_id}/messages", body)

    # Re-POST the SAME clientMessageId -> idempotent replay from persisted parts.
    replay = await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", body
    )
    replay_names = [name for name, _ in replay]
    # Replay sequence mirrors persisted part ordering:
    # reasoning -> tools -> status -> answer -> sources -> terminal.
    assert replay_names == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "tool_call",
        "tool_result",
        "status",
        "answer_delta",
        "sources",
        "terminal",
    ]
    replay_tool_call = next(p for n, p in replay if n == "tool_call")
    replay_tool_result = next(p for n, p in replay if n == "tool_result")
    assert replay_tool_result["toolCallId"] == replay_tool_call["id"]
    replay_sources = next(p for n, p in replay if n == "sources")
    assert [it["id"] for it in replay_sources["items"]] == [1, 2, 3]
    replay_status = next(p for n, p in replay if n == "status")
    assert replay_status["state"] == "done"


# Auto-tier routing ------------------------------------------------------------


async def test_auto_route_downgrade_surfaces_substitution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`auto` + a short, signal-free prompt routes to `fast` and surfaces the
    `auto_downgrade` substitution honestly (never silent)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "hi",
        },
    )
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    # Requested stays `auto`; served is the routed concrete tier (`fast`).
    assert attribution["requestedTierId"] == "auto"
    assert attribution["servedTierId"] == "fast"
    sub = attribution.get("substitution")
    assert isinstance(sub, dict)
    assert sub["reasonCode"] == "auto_downgrade"


async def test_auto_route_to_baseline_emits_no_substitution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`auto` + a code fence routes to the `smart` baseline -> no substitution
    (routing to the baseline is not a downgrade)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "Review this:\n```python\nprint('x')\n```",
        },
    )
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["requestedTierId"] == "auto"
    assert attribution["servedTierId"] == "smart"
    assert attribution.get("substitution") is None


# Auto-routing x stop / provider-fallback interplay ---------------------------


class _NoSubstitutionThenBlockProvider:
    """Streams a normal turn, then a `Complete` carrying NO substitution.

    Used by the stop-path test. After the terminal `Complete` is yielded (and
    thus enqueued by the handler's pump), the generator sets `done` so the test
    can tell the handler to tear the turn down. The closing `finally` therefore
    runs only after `Complete` is on the queue — guaranteeing the drain path
    sees a `substitution=None` `Complete`, which is exactly the event that must
    NOT clobber the router's `auto_downgrade` seed.
    """

    def __init__(self, done: asyncio.Event) -> None:
        self._done = done

    async def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[object] | None = None,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
        web_search: bool = False,
        supports_vision: bool = True,
        response_format: object | None = None,
        system_prefix: str | None = None,
        tools: list[object] | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        try:
            yield ReasoningDelta(text="thinking")
            yield ReasoningDone()
            yield AnswerDelta(text="partial answer")
            usage = UsageUpdate(
                input_tokens=20,
                output_tokens=5,
                reasoning_tokens=2,
                cached_input_tokens=0,
            )
            yield UsageUpdate(
                input_tokens=20,
                output_tokens=5,
                reasoning_tokens=2,
                cached_input_tokens=0,
            )
            # Terminal Complete with NO provider substitution. On the stop/drain
            # path this is the event that, pre-fix, clobbered the auto_downgrade
            # seed with None.
            yield Complete(usage=usage)
        finally:
            # Runs after `Complete` has been pulled by the pump and enqueued, so
            # signalling `done` here means the queue already holds the Complete
            # the drain branch must fold without clobbering the seed.
            self._done.set()

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        return "title"


async def test_stop_path_preserves_auto_downgrade_seed_in_persisted_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STOP an `auto`→`fast` turn mid-stream; the PERSISTED stopped assistant
    row must still carry `substitution.reasonCode == "auto_downgrade"`.

    Catches the silent-downgrade leak: the disconnect/stop drain folds a
    trailing `Complete(substitution=None)` into the running sub state. Without
    the `_fold_complete_substitution` guard that None overwrites the router's
    `auto_downgrade` seed, and the stopped row — re-served on reload — loses its
    downgrade disclosure. We assert against the durable DB row, not an in-flight
    frame.
    """
    from app.routes import conversations as conv_routes

    provider_done = asyncio.Event()

    monkeypatch.setattr(
        conv_routes,
        "build_provider",
        lambda *a, **k: _NoSubstitutionThenBlockProvider(provider_done),
    )

    # Drive the stop via the handler's `request.is_disconnected()` poll. The
    # first poll BLOCKS until the provider has fully streamed (Complete enqueued
    # + terminal None), then reports disconnected. This makes the handler take
    # the drain path with the un-substituted Complete already in the queue —
    # deterministic, no timing race.
    from starlette.requests import Request

    async def _fake_is_disconnected(self: Request) -> bool:
        await provider_done.wait()
        return True

    monkeypatch.setattr(Request, "is_disconnected", _fake_is_disconnected)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    # `"hi"` is the short, signal-free prompt that routes auto→fast (downgrade),
    # seeding router_substitution="auto_downgrade" before the provider call.
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "hi",
        },
    )
    # Stop/disconnect path emits no terminal frame (socket closed semantics);
    # the proof is the persisted row, asserted below.
    assert all(name != "terminal" for name, _ in frames)

    # Reload the durable stopped assistant row and assert its attribution still
    # discloses the auto downgrade.
    async with session_factory() as session:
        assistant = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        assert assistant.status == "stopped"
        attribution = assistant.attribution
        assert isinstance(attribution, dict)
        assert attribution["requestedTierId"] == "auto"
        assert attribution["servedTierId"] == "fast"
        sub = attribution.get("substitution")
        assert isinstance(sub, dict), "stopped auto→fast row lost its substitution"
        assert sub["reasonCode"] == "auto_downgrade"


async def test_auto_route_provider_fallback_wins_over_downgrade_seed(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`auto`→`fast` (downgrade-seeded) turn whose provider ALSO force-falls-back:
    the provider substitution WINS over the router seed.

    Precedence claim: a real provider `Complete(substitution="provider_fallback")`
    overwrites the router-side `auto_downgrade` seed AND brings the served model
    label with it. The terminal attribution must read `provider_fallback`, not
    `auto_downgrade`, and the served model label must reflect the fallback model.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id, tier_id="auto")

    # `FORCE_FALLBACK:` flips the fake provider's terminal Complete into the
    # provider_fallback shape; the leading short text still routes auto→fast,
    # so the router seeds `auto_downgrade` first — the provider must override it.
    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "auto",
            "text": "FORCE_FALLBACK: hi",
        },
    )
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["requestedTierId"] == "auto"
    # Routed to the concrete fast tier before the provider fallback fired.
    assert attribution["servedTierId"] == "fast"
    sub = attribution.get("substitution")
    assert isinstance(sub, dict)
    # Provider fallback wins precedence over the auto_downgrade seed.
    assert sub["reasonCode"] == "provider_fallback"
    # The served label reflects the provider's substituted model, not the
    # routed tier's default label.
    assert attribution["servedModelLabel"] == "Fallback Model"


# Feature 1: per-turn reasoning-effort override ------------------------------


async def test_map_reasoning_effort_all_values() -> None:
    """`_map_reasoning_effort` maps every enum value (and None) correctly.

    None / "auto" defer to the binding default for BOTH hints; "minimal" forces
    thinking OFF; "standard"/"extended" select effort levels and leave thinking
    at the binding default (None override). Pinned against bindings with and
    without a binding-level `reasoning_effort` so the auto/None passthrough is
    exercised both ways.
    """
    from app.providers.tiers import get_binding
    from app.routes.conversations import _map_reasoning_effort

    smart = get_binding("smart")  # binding.reasoning_effort is None
    pro = get_binding("pro")  # binding.reasoning_effort == "high"
    assert smart is not None and pro is not None

    # None / auto pass the binding default through for the effort hint, never
    # touching thinking (None = "use binding default").
    assert _map_reasoning_effort(None, smart) == (None, None)
    assert _map_reasoning_effort("auto", smart) == (None, None)
    assert _map_reasoning_effort("auto", pro) == ("high", None)
    assert _map_reasoning_effort(None, pro) == ("high", None)

    # minimal forces thinking OFF and omits the effort level.
    assert _map_reasoning_effort("minimal", smart) == (None, False)
    assert _map_reasoning_effort("minimal", pro) == (None, False)

    # standard / extended select effort levels; thinking stays at binding default.
    assert _map_reasoning_effort("standard", smart) == ("medium", None)
    assert _map_reasoning_effort("extended", smart) == ("high", None)


async def test_reasoning_effort_extended_streams_and_persists(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A turn carrying `reasoningEffort:"extended"` streams normally under the
    fake backend (the hint is accepted and ignored — never an error)."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hello world",
            "reasoningEffort": "extended",
        },
    )
    event_names = [name for name, _ in frames]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"


async def test_reasoning_effort_minimal_forwards_thinking_off_to_provider(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`reasoningEffort:"minimal"` reaches the provider as `thinking=False` and
    `reasoning_effort=None`; `"extended"` reaches it as `reasoning_effort="high"`.

    Spy on `FakeProvider.stream` to capture the per-call hints the route resolved
    so the end-to-end override threading is pinned without a real provider.
    """
    captured: list[dict[str, object]] = []
    from app.providers.fake import FakeProvider

    real_stream = FakeProvider.stream

    def _spy_stream(self: FakeProvider, **kwargs: object) -> object:
        captured.append(
            {
                "thinking": kwargs.get("thinking"),
                "reasoning_effort": kwargs.get("reasoning_effort"),
            }
        )
        return real_stream(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(FakeProvider, "stream", _spy_stream)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "minimal please",
            "reasoningEffort": "minimal",
        },
    )
    assert captured, "provider.stream was never called"
    assert captured[-1]["thinking"] is False
    assert captured[-1]["reasoning_effort"] is None

    captured.clear()
    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "extended please",
            "reasoningEffort": "extended",
        },
    )
    assert captured[-1]["reasoning_effort"] == "high"


async def test_reasoning_effort_auto_uses_binding_default(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`reasoningEffort:"auto"` leaves the provider call at the binding defaults.

    The `smart` binding's defaults are `thinking=True`, `reasoning_effort=None`,
    so the captured outbound call must match those — proving the override is a
    no-op for `auto`.
    """
    captured: list[dict[str, object]] = []
    from app.providers.fake import FakeProvider
    from app.providers.tiers import get_binding

    binding = get_binding("smart")
    assert binding is not None

    real_stream = FakeProvider.stream

    def _spy_stream(self: FakeProvider, **kwargs: object) -> object:
        captured.append(
            {
                "thinking": kwargs.get("thinking"),
                "reasoning_effort": kwargs.get("reasoning_effort"),
            }
        )
        return real_stream(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(FakeProvider, "stream", _spy_stream)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "auto effort",
            "reasoningEffort": "auto",
        },
    )
    assert captured[-1]["thinking"] is binding.thinking
    assert captured[-1]["reasoning_effort"] == binding.reasoning_effort


# Phase 2: provider fallback retry --------------------------------------------


async def test_provider_fallback_retry_succeeds_and_bills_once(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`FORCE_FALLBACK_RETRY:` makes the PRIMARY route raise a retryable upstream
    error before any token; the handler retries ONCE on the fallback route, which
    streams a normal answer.

    Asserts: terminal `done`, attribution.substitution.reasonCode is a fallback
    code, attribution.providerId is the fallback provider, EXACTLY one assistant
    row persisted, and `usage_rollup.used == 1` (billed once — no double-bill).
    """
    from app.db.models import UsageRollup

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_FALLBACK_RETRY: please answer",
        },
    )
    event_names = [name for name, _ in frames]
    assert event_names[-1] == "terminal", event_names
    assert "error" not in event_names
    # Real answer streamed on the fallback route.
    assert "answer_delta" in event_names

    terminal_payload = frames[-1][1]
    assert terminal_payload["status"] == "done"
    attribution = terminal_payload["attribution"]
    assert isinstance(attribution, dict)
    sub = attribution.get("substitution")
    assert isinstance(sub, dict), "expected a substitution on the fallback turn"
    assert sub["reasonCode"] in {"provider_fallback", "rate_limited"}
    # The served provider is the fallback route (fake), not the primary deepseek.
    assert attribution["providerId"] == "fake"

    # Exactly one assistant row; billed exactly once.
    async with session_factory() as session:
        assistants = (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalars().all()
        assert len(assistants) == 1
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        assert rollup.used == 1


async def test_provider_fallback_self_fallback_on_fake_primary(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When the PRIMARY route is the `fake` dev/test backend (e.g. the FE sends
    `providerId="fake"` in a fake-only deployment), the one-shot retry must still
    find an alternate: `fake` self-falls-back via the `fake-fallback` model id.

    This is the exact path the browser E2E suite drives; without the
    fake-self-fallback the turn regresses to an `error` frame because the
    primary-exclusion would skip the only platform-usable backend. Real
    providers never self-fall-back (and `fake` is gated out of production), so
    this does not change prod behavior.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "providerId": "fake",
            "text": "FORCE_FALLBACK_RETRY: please answer",
        },
    )
    event_names = [name for name, _ in frames]
    assert event_names[-1] == "terminal", event_names
    assert "error" not in event_names
    assert "answer_delta" in event_names

    terminal_payload = frames[-1][1]
    assert terminal_payload["status"] == "done"
    sub = terminal_payload["attribution"].get("substitution")
    assert isinstance(sub, dict), "expected a substitution on the self-fallback turn"
    assert sub["reasonCode"] in {"provider_fallback", "rate_limited"}
    # Served route is the fake fallback; primary `fake` was retried as fake-fallback.
    assert terminal_payload["attribution"]["providerId"] == "fake"


async def test_post_token_rate_limit_does_not_retry(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A retryable error that arrives AFTER the first token (`FORCE_RATE_LIMIT:`
    raises after a couple of answer deltas) must NOT trigger the fallback retry.

    The boundary is strict: once content was emitted, retrying would double-emit
    / double-bill. So the turn surfaces an `error` frame and persists no
    assistant row — identical to the pre-fallback behavior.
    """
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_RATE_LIMIT: slow down",
        },
    )
    event_names = [name for name, _ in frames]
    # Some answer text streamed BEFORE the raise, so no retry happened.
    assert "answer_delta" in event_names
    assert event_names[-1] == "error"
    assert "terminal" not in event_names
    error_payload = frames[-1][1]
    assert error_payload["code"] == "RATE_LIMITED"

    async with session_factory() as session:
        assistants = (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalars().all()
        assert assistants == []


async def test_no_alternate_route_surfaces_error_as_today(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `_select_fallback_route` returns None (no alternate), a retryable
    pre-token error surfaces as an `error` frame exactly as before — proving the
    fallback path is purely additive and gated on an available alternate.
    """
    import app.routes.conversations as convo_routes

    async def _no_fallback(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(convo_routes, "_select_fallback_route", _no_fallback)

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        client,
        f"/api/conversations/{conv_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "FORCE_FALLBACK_RETRY: please answer",
        },
    )
    event_names = [name for name, _ in frames]
    assert event_names[-1] == "error", event_names
    assert "terminal" not in event_names
    error_payload = frames[-1][1]
    assert error_payload["code"] == "PROVIDER_UPSTREAM"

    async with session_factory() as session:
        assistants = (
            await session.execute(select(Message).where(Message.role == "assistant"))
        ).scalars().all()
        assert assistants == []
