"""First-party analytics tests."""

from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import AnalyticsEvent, Preferences, User
from app.db.repositories import analytics as analytics_repo
from app.middleware.ratelimit import limiter

pytestmark = pytest.mark.asyncio


async def _analytics_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[AnalyticsEvent]:
    async with session_factory() as session:
        return (
            (
                await session.execute(
                    select(AnalyticsEvent).order_by(AnalyticsEvent.created_at.asc())
                )
            )
            .scalars()
            .all()
        )


async def _current_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one()


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
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
                fragment = line[len("data:") :].strip()
                data_payload = fragment if data_payload is None else data_payload + fragment
        if event_name is not None and data_payload is not None:
            frames.append((event_name, json.loads(data_payload)))
    return frames


async def _collect_sse(
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


async def test_frontend_event_endpoint_persists_content_free_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200

    response = await client.post(
        "/api/analytics/events",
        json={
            "eventType": "settings.opened",
            "properties": {"surface": "settings"},
        },
    )
    assert response.status_code == 204

    rows = await _analytics_rows(session_factory)
    assert [(row.event_type, row.properties) for row in rows] == [
        ("settings.opened", {"surface": "settings"})
    ]


async def test_frontend_event_endpoint_validates_event_name_and_payload(
    client: AsyncClient,
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200

    bad_name = await client.post(
        "/api/analytics/events",
        json={"eventType": "message.sent", "properties": {}},
    )
    assert bad_name.status_code == 400
    assert bad_name.json()["error"]["code"] == "INVALID_INPUT"

    content_like = await client.post(
        "/api/analytics/events",
        json={
            "eventType": "settings.opened",
            "properties": {"messageText": "do not store this"},
        },
    )
    assert content_like.status_code == 400
    assert content_like.json()["error"]["code"] == "INVALID_INPUT"

    secret_key = await client.post(
        "/api/analytics/events",
        json={
            "eventType": "settings.opened",
            "properties": {"authToken": "not allowed"},
        },
    )
    assert secret_key.status_code == 400
    assert secret_key.json()["error"]["code"] == "INVALID_INPUT"

    secret_value = await client.post(
        "/api/analytics/events",
        json={
            "eventType": "settings.opened",
            "properties": {"surface": "prefix sk-test-secret-1234567890"},
        },
    )
    assert secret_value.status_code == 400
    assert secret_value.json()["error"]["code"] == "INVALID_INPUT"


async def test_frontend_event_endpoint_is_rate_limited(
    client: AsyncClient,
) -> None:
    old_value = os.environ.get("RATE_LIMIT_ANALYTICS")
    os.environ["RATE_LIMIT_ANALYTICS"] = "2/minute"
    get_settings.cache_clear()
    storage = limiter._storage
    if hasattr(storage, "storage"):
        storage.storage.clear()
    if hasattr(storage, "expirations"):
        storage.expirations.clear()
    try:
        assert (await client.get("/api/bootstrap")).status_code == 200
        for _ in range(2):
            ok = await client.post(
                "/api/analytics/events",
                json={"eventType": "settings.opened", "properties": {}},
            )
            assert ok.status_code == 204
        limited = await client.post(
            "/api/analytics/events",
            json={"eventType": "settings.opened", "properties": {}},
        )
        assert limited.status_code == 429
    finally:
        if old_value is None:
            os.environ.pop("RATE_LIMIT_ANALYTICS", None)
        else:
            os.environ["RATE_LIMIT_ANALYTICS"] = old_value
        get_settings.cache_clear()


async def test_telemetry_preference_skips_event_persistence(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    user = await _current_user(session_factory)
    async with session_factory() as session:
        session.add(
            Preferences(
                user_id=user.id,
                default_tier_id="auto",
                temporary_by_default=False,
                training_opt_in=False,
                send_on_enter=True,
                auto_expand_reasoning=False,
                telemetry_enabled=False,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/analytics/events",
        json={"eventType": "settings.opened", "properties": {}},
    )
    assert response.status_code == 204
    assert await _analytics_rows(session_factory) == []


async def test_server_side_analytics_drops_unsafe_properties(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    user = await _current_user(session_factory)

    async with session_factory() as session:
        await analytics_repo.record(
            session,
            user_id=user.id,
            event_type="internal.test",
            properties={
                "safe": "ok",
                "promptText": "do not store this",
                "apiKey": "sk-test-secret-1234567890",
                "surface": "prefix sk-test-secret-1234567890",
            },
        )
        await session.commit()

    rows = await _analytics_rows(session_factory)
    assert [(row.event_type, row.properties) for row in rows] == [
        ("internal.test", {"safe": "ok"})
    ]


async def test_stream_analytics_respects_telemetry_opt_out(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    user = await _current_user(session_factory)
    async with session_factory() as session:
        session.add(
            Preferences(
                user_id=user.id,
                default_tier_id="auto",
                temporary_by_default=False,
                training_opt_in=False,
                send_on_enter=True,
                auto_expand_reasoning=False,
                telemetry_enabled=False,
            )
        )
        await session.commit()

    created = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart"},
    )
    assert created.status_code == 201, created.text
    frames = await _collect_sse(
        client,
        f"/api/conversations/{created.json()['id']}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hello analytics opt out",
        },
    )
    assert frames[-1][0] == "terminal"
    assert await _analytics_rows(session_factory) == []


async def test_stream_records_terminal_and_first_success_events(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    created = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart"},
    )
    assert created.status_code == 201, created.text
    conv_id = created.json()["id"]

    async def send_once(conversation_id: str, text: str) -> None:
        frames = await _collect_sse(
            client,
            f"/api/conversations/{conversation_id}/messages",
            {
                "clientMessageId": str(uuid4()),
                "tierId": "smart",
                "text": text,
            },
        )
        assert frames[-1][0] == "terminal"

    await send_once(conv_id, "hello analytics")

    second = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart"},
    )
    assert second.status_code == 201, second.text
    await send_once(second.json()["id"], "second conversation")

    rows = await _analytics_rows(session_factory)
    terminal_rows = [row for row in rows if row.event_type == "response.terminal"]
    activation_rows = [
        row for row in rows if row.event_type == "activation.first_successful_response"
    ]
    assert len(terminal_rows) == 2
    assert len(activation_rows) == 1
    terminal = terminal_rows[0]
    assert terminal.properties["terminalStatus"] == "done"
    assert terminal.properties["conversationId"] == conv_id
    assert terminal.properties["requestedTierId"] == "smart"
    assert terminal.properties["servedTierId"] == "smart"
    assert terminal.properties["providerId"] == "deepseek"
    assert terminal.properties["isByok"] is False
    assert terminal.properties["costUsd"] > 0
    assert terminal.properties["ttftMs"] is not None
