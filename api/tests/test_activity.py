"""Trust-surface tests (PRD 07 §6.5 / PRD 05 §7.4 / PRD 08 §5.6).

Covers the data-access activity log, the data-processing provenance rollup, the
moderation-appeal capture, and the new audit emits (login / share-mint /
moderation-blocked).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, Conversation, Message, User

pytestmark = pytest.mark.asyncio


async def _current_user_id(session_factory: async_sessionmaker[AsyncSession]) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


async def _seed_user(session_factory: async_sessionmaker[AsyncSession]) -> object:
    async with session_factory() as session:
        user = User(name="Other", is_anonymous=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _seed_audit(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    event_type: str,
    created_at: datetime,
) -> None:
    async with session_factory() as session:
        session.add(
            AuditEvent(
                user_id=user_id,
                event_type=event_type,
                details={},
                created_at=created_at,
            )
        )
        await session.commit()


async def _seed_attributed_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    attribution: dict[str, object],
) -> None:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="c",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.flush()
        session.add(
            Message(
                conversation_id=convo.id,
                role="assistant",
                parts=[{"type": "text", "text": "hi"}],
                status="done",
                attribution=attribution,
            )
        )
        await session.commit()


async def test_activity_returns_callers_events_newest_first_and_paginates(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    me = await _current_user_id(session_factory)
    other = await _seed_user(session_factory)

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(4):
        await _seed_audit(
            session_factory,
            user_id=me,
            event_type=f"event.{i}",
            created_at=base + timedelta(minutes=i),
        )
    # Another user's row must NEVER appear in the caller's feed.
    await _seed_audit(
        session_factory,
        user_id=other,
        event_type="other.secret",
        created_at=base + timedelta(minutes=10),
    )

    resp = await client.get("/api/account/activity")
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["eventType"] for r in rows] == ["event.3", "event.2", "event.1", "event.0"]
    assert all(r["eventType"] != "other.secret" for r in rows)
    # CamelModel shape.
    assert set(rows[0].keys()) == {"id", "eventType", "details", "createdAt"}

    # Page 1 (limit 2) then keyset page 2 via the composite `<createdAt>|<id>`
    # cursor of the oldest row seen.
    page1 = (await client.get("/api/account/activity?limit=2")).json()
    assert [r["eventType"] for r in page1] == ["event.3", "event.2"]
    cursor = f"{page1[-1]['createdAt']}|{page1[-1]['id']}"
    page2 = (await client.get(f"/api/account/activity?limit=2&before={cursor}")).json()
    assert [r["eventType"] for r in page2] == ["event.1", "event.0"]


async def test_activity_pagination_tie_safe_on_identical_created_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Events sharing an identical created_at must not be dropped across a page
    boundary — the composite (created_at, id) cursor keeps them all."""
    await client.get("/api/bootstrap")
    me = await _current_user_id(session_factory)

    tie = datetime(2026, 2, 1, tzinfo=UTC)
    for i in range(5):
        await _seed_audit(
            session_factory,
            user_id=me,
            event_type=f"tie.{i}",
            created_at=tie,
        )

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):  # generous page budget; loop breaks when drained
        url = "/api/account/activity?limit=2"
        if cursor:
            url += f"&before={cursor}"
        page = (await client.get(url)).json()
        if not page:
            break
        seen.extend(r["id"] for r in page)
        cursor = f"{page[-1]['createdAt']}|{page[-1]['id']}"
        if len(page) < 2:
            break

    # All 5 tied rows surface exactly once — none skipped, none duplicated.
    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_activity_rejects_bad_cursor(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.get("/api/account/activity?before=not-a-date")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_CURSOR"
    # The timestamp half alone (no `|<id>`) is also rejected.
    resp2 = await client.get("/api/account/activity?before=2026-01-01T00:00:00%2B00:00")
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "INVALID_CURSOR"


async def test_data_processing_rollup_groups_by_provider_with_registry_jurisdiction(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    me = await _current_user_id(session_factory)
    other = await _seed_user(session_factory)

    await _seed_attributed_message(
        session_factory,
        user_id=me,
        attribution={"providerId": "deepseek", "providerLabel": "DeepSeek", "isByok": False},
    )
    await _seed_attributed_message(
        session_factory,
        user_id=me,
        attribution={"providerId": "deepseek", "providerLabel": "DeepSeek", "isByok": False},
    )
    await _seed_attributed_message(
        session_factory,
        user_id=me,
        attribution={
            "providerId": "deepseek",
            "providerLabel": "DeepSeek",
            "isByok": True,
            "substitution": {"reasonCode": "provider_fallback", "reasonText": "x"},
        },
    )
    await _seed_attributed_message(
        session_factory,
        user_id=me,
        attribution={"providerId": "anthropic", "providerLabel": "Anthropic", "isByok": False},
    )
    # Another user's attribution must not leak into the caller's rollup.
    await _seed_attributed_message(
        session_factory,
        user_id=other,
        attribution={"providerId": "openai", "providerLabel": "OpenAI", "isByok": False},
    )

    resp = await client.get("/api/account/data-processing")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalAttributed"] == 4

    by_id = {b["providerId"]: b for b in body["byProvider"]}
    assert set(by_id) == {"deepseek", "anthropic"}

    deepseek = by_id["deepseek"]
    assert deepseek["messageCount"] == 3
    assert deepseek["isByokCount"] == 1
    assert deepseek["platformCount"] == 2
    assert deepseek["substitutionCount"] == 1
    # Jurisdiction is read from the LIVE registry, never hardcoded.
    assert deepseek["jurisdiction"] == "China"
    assert deepseek["providerLabel"] == "DeepSeek"

    anthropic = by_id["anthropic"]
    assert anthropic["messageCount"] == 1
    assert anthropic["jurisdiction"] == "US/EU"


async def test_data_processing_empty_for_fresh_user(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    body = (await client.get("/api/account/data-processing")).json()
    assert body == {"totalAttributed": 0, "byProvider": []}


async def test_moderation_appeal_records_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post(
        "/api/account/moderation-appeal",
        json={"reasonCode": "configured_blocklist", "source": "message", "note": "please review"},
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.event_type == "moderation.appeal")
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].details["reasonCode"] == "configured_blocklist"
        assert rows[0].details["source"] == "message"
        assert rows[0].details["note"] == "please review"


async def test_share_mint_writes_audit_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False},
    )
    assert created.status_code == 201
    convo_id = created.json()["id"]

    share = await client.post(f"/api/conversations/{convo_id}/share")
    assert share.status_code == 200

    # Visible through the caller's own activity feed.
    rows = (await client.get("/api/account/activity")).json()
    mint = [r for r in rows if r["eventType"] == "share.mint"]
    assert len(mint) == 1
    assert mint[0]["details"]["conversationId"] == convo_id


async def test_login_writes_auth_login_event(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    upgrade = await client.post(
        "/api/auth/upgrade",
        json={"email": "trust@example.com", "password": "password123"},
    )
    assert upgrade.status_code == 200
    await client.post("/api/auth/signout")

    login = await client.post(
        "/api/auth/login",
        json={"email": "trust@example.com", "password": "password123"},
    )
    assert login.status_code == 200

    async with session_factory() as session:
        target = (
            await session.execute(
                select(User).where(User.email == "trust@example.com")
            )
        ).scalar_one()
        types = (
            await session.execute(
                select(AuditEvent.event_type).where(AuditEvent.user_id == target.id)
            )
        ).scalars().all()
        assert "auth.login" in types
        assert "auth.upgrade" in types


async def test_moderation_blocked_emits_audit_event(
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
        async with session_factory() as session:
            convo = Conversation(
                user_id=user_id, title="c", selected_tier_id="smart", pinned=False
            )
            session.add(convo)
            await session.commit()
            await session.refresh(convo)
            convo_id = str(convo.id)

        resp = await client.post(
            f"/api/conversations/{convo_id}/messages",
            json={
                "clientMessageId": str(uuid4()),
                "tierId": "fast",
                "text": "please do-not-send this",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "SAFETY_BLOCKED"

        # The blocked turn is recorded even though the request transaction rolled
        # back (no user message persisted) — the emit uses an independent session.
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "moderation.blocked"
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].details["reasonCode"] == "configured_blocklist"
            assert rows[0].details["source"] == "message"
            assert rows[0].details["conversationId"] == convo_id

            messages = (await session.execute(select(Message))).scalars().all()
            assert messages == []
    finally:
        get_settings.cache_clear()
