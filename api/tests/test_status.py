"""Public platform-status tests (PRD 08 §10).

Covers the `/api/status` health derivation from `Stream` telemetry:
- no streams -> `operational` (and the route needs NO session cookie),
- enough recent `error` streams to exceed the threshold -> `degraded`,
- a sub-threshold sample stays `operational` even at a high error ratio,
- streams created outside the window are excluded.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Stream, User

pytestmark = pytest.mark.asyncio


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        user = User(name="Streamer", is_anonymous=True)
        session.add(user)
        await session.flush()
        convo = Conversation(
            user_id=user.id,
            title="c",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return convo.id


async def _seed_streams(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conversation_id: object,
    status: str,
    count: int,
    age_seconds: int = 0,
) -> None:
    created = datetime.now(UTC) - timedelta(seconds=age_seconds)
    async with session_factory() as session:
        for _ in range(count):
            session.add(
                Stream(
                    conversation_id=conversation_id,
                    status=status,
                    created_at=created,
                    updated_at=created,
                )
            )
        await session.commit()


async def test_status_operational_with_no_streams_and_no_cookie(
    client: AsyncClient,
) -> None:
    # No bootstrap, no prior session: the route is public and must not require
    # (or mint) a session cookie.
    assert "sid" not in client.cookies
    resp = await client.get("/api/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "operational"
    assert body["sampleSize"] == 0
    assert body["errorCount"] == 0
    assert body["windowSeconds"] == 900
    assert isinstance(body["updatedAt"], str) and body["updatedAt"]
    # Public read: no session cookie set on the response.
    assert "sid" not in resp.cookies
    assert "sid" not in client.cookies


async def test_status_degraded_when_error_ratio_exceeds_threshold(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    convo = await _seed_conversation(session_factory)
    # 6 recent errors (>= min sample 5, ratio 1.0 > 0.5) -> degraded.
    await _seed_streams(
        session_factory, conversation_id=convo, status="error", count=6
    )
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["sampleSize"] == 6
    assert body["errorCount"] == 6


async def test_status_operational_when_sample_below_min(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    convo = await _seed_conversation(session_factory)
    # 3 errors: ratio is 1.0, but the sample is below the min (5), so the
    # banner must stay calm — a couple of stray errors never trips degraded.
    await _seed_streams(
        session_factory, conversation_id=convo, status="error", count=3
    )
    body = (await client.get("/api/status")).json()
    assert body["status"] == "operational"
    assert body["sampleSize"] == 3
    assert body["errorCount"] == 3


async def test_status_operational_when_error_ratio_at_or_below_threshold(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    convo = await _seed_conversation(session_factory)
    # 5 errors + 5 done = ratio exactly 0.5, which does NOT exceed the 0.5
    # threshold -> operational.
    await _seed_streams(
        session_factory, conversation_id=convo, status="error", count=5
    )
    await _seed_streams(
        session_factory, conversation_id=convo, status="done", count=5
    )
    body = (await client.get("/api/status")).json()
    assert body["status"] == "operational"
    assert body["sampleSize"] == 10
    assert body["errorCount"] == 5


async def test_status_excludes_streams_outside_window(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    convo = await _seed_conversation(session_factory)
    # 6 errors but all created an hour ago — well outside the 900s window, so
    # they don't count and the platform reads operational with an empty sample.
    await _seed_streams(
        session_factory,
        conversation_id=convo,
        status="error",
        count=6,
        age_seconds=3600,
    )
    body = (await client.get("/api/status")).json()
    assert body["status"] == "operational"
    assert body["sampleSize"] == 0
    assert body["errorCount"] == 0
