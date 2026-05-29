"""Account data route tests — GDPR export + right-to-erasure.

Covers (PRD 05 §7.3, PRD 04 §5.7):
- GET /api/account/export returns 200 with the caller's conversations/messages/
  preferences, an attachment Content-Disposition header, and NO secret material
  (no ciphertext, no decrypted BYOK key).
- DELETE /api/account returns 204, actually erases every owned row across all
  tables, and clears the cookie so the next request mints a fresh anon user.
- Anonymous users can export and delete (no 403).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ApiKey, Conversation, Message, Preferences, UsageRollup, User, Vote
from app.db.models import Session as DbSession

pytestmark = pytest.mark.asyncio


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    """Return the single anonymous user created by a prior bootstrap hit."""
    async with session_factory() as s:
        return (await s.execute(select(User))).scalar_one().id


async def _seed_owned_data(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
) -> tuple[str, str, str]:
    """Seed a full ownership graph for `user_id`.

    Creates a conversation with a user + assistant message, a vote on the
    assistant message, a preferences row, a BYOK api_key row (with ciphertext +
    masked key) and a usage_rollup row.

    Returns (conversation_id, user_message_id, assistant_message_id).
    """
    async with session_factory() as s:
        convo = Conversation(
            user_id=user_id,
            title="My conversation",
            selected_tier_id="smart",
            pinned=False,
        )
        s.add(convo)
        await s.flush()

        m_user = Message(
            conversation_id=convo.id,
            role="user",
            parts=[{"type": "text", "text": "hello world"}],
            status=None,
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        m_asst = Message(
            conversation_id=convo.id,
            role="assistant",
            parts=[{"type": "text", "text": "hi there"}],
            status="done",
            attribution=None,
            created_at=datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC),
        )
        s.add(m_user)
        s.add(m_asst)
        await s.flush()

        s.add(Vote(message_id=m_asst.id, feedback="up"))
        s.add(
            Preferences(
                user_id=user_id,
                default_tier_id="smart",
                temporary_by_default=False,
                training_opt_in=True,
                send_on_enter=True,
                auto_expand_reasoning=False,
            )
        )
        s.add(
            ApiKey(
                user_id=user_id,
                provider="anthropic",
                ciphertext="SUPER-SECRET-CIPHERTEXT-DO-NOT-LEAK",
                masked_key="sk-...abcd",
            )
        )
        s.add(
            UsageRollup(
                user_id=user_id,
                period_start=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
                used=3,
                limit_value=100,
                is_byok=False,
            )
        )
        await s.commit()
        return str(convo.id), str(m_user.id), str(m_asst.id)


async def test_export_returns_data_with_attachment_and_no_secrets(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    user_id = await _current_user_id(session_factory)
    conv_id, _, _ = await _seed_owned_data(session_factory, user_id)

    response = await client.get("/api/account/export")
    assert response.status_code == 200, response.text

    # Browser-download header.
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert 'filename="account-export.json"' in cd

    body = response.json()
    # camelCase envelope shape.
    for key in ("account", "preferences", "usage", "conversations", "exportedAt"):
        assert key in body, f"missing top-level key {key!r}"

    # exportedAt is an ISO-8601 timestamp.
    assert datetime.fromisoformat(body["exportedAt"])

    # The seeded conversation + both messages are present.
    convos = body["conversations"]
    assert len(convos) == 1
    assert convos[0]["id"] == conv_id
    assert convos[0]["title"] == "My conversation"
    assert len(convos[0]["messages"]) == 2
    texts = {m["parts"][0]["text"] for m in convos[0]["messages"]}
    assert texts == {"hello world", "hi there"}

    # Preferences reflect the seeded row.
    assert body["preferences"]["trainingOptIn"] is True

    # No secret material anywhere in the serialized payload.
    raw = json.dumps(body)
    assert "SUPER-SECRET-CIPHERTEXT-DO-NOT-LEAK" not in raw
    assert "ciphertext" not in raw
    assert "passwordHash" not in raw and "password_hash" not in raw
    assert "sessionSecret" not in raw and "session_secret" not in raw


async def test_export_works_for_anonymous_user(
    client: AsyncClient,
) -> None:
    # Anonymous caller (bootstrap mints the anon user) — no 403.
    assert (await client.get("/api/bootstrap")).status_code == 200
    response = await client.get("/api/account/export")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account"]["email"] == ""
    assert body["account"]["byokEnabled"] is False
    assert body["conversations"] == []


async def test_delete_erases_all_data_and_clears_cookie(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    user_id = await _current_user_id(session_factory)
    conv_id, _, asst_id = await _seed_owned_data(session_factory, user_id)

    # Sanity: the conversation is reachable before deletion.
    pre = await client.get(f"/api/conversations/{conv_id}")
    assert pre.status_code == 200

    response = await client.delete("/api/account")
    assert response.status_code == 204
    assert response.content == b""

    # Cookie cleared on the response.
    set_cookie = response.headers.get("set-cookie", "")
    assert "sid=" in set_cookie

    # Every owned row across every table is gone.
    async with session_factory() as s:
        assert (
            await s.execute(select(func.count()).select_from(User).where(User.id == user_id))
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(Conversation).where(
                    Conversation.user_id == user_id
                )
            )
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(Message).where(
                    Message.conversation_id == UUID(conv_id)
                )
            )
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(Vote).where(
                    Vote.message_id == UUID(asst_id)
                )
            )
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(Preferences).where(
                    Preferences.user_id == user_id
                )
            )
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(ApiKey).where(
                    ApiKey.user_id == user_id
                )
            )
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(UsageRollup).where(
                    UsageRollup.user_id == user_id
                )
            )
        ).scalar_one() == 0
        assert (
            await s.execute(
                select(func.count()).select_from(DbSession).where(
                    DbSession.user_id == user_id
                )
            )
        ).scalar_one() == 0

    # The old conversation now 404s (the cookie was cleared → fresh anon user).
    post = await client.get(f"/api/conversations/{conv_id}")
    assert post.status_code == 404

    # A fresh bootstrap mints a NEW identity with no conversations.
    fresh = await client.get("/api/bootstrap")
    assert fresh.status_code == 200
    assert fresh.json()["conversations"] == []
    # The post-delete identities are all distinct from the erased user — the
    # cleared cookie means the next request(s) mint fresh anon user(s).
    async with session_factory() as s:
        remaining_ids = (await s.execute(select(User.id))).scalars().all()
    assert user_id not in remaining_ids
    assert len(remaining_ids) >= 1


async def test_delete_works_for_anonymous_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert (await client.get("/api/bootstrap")).status_code == 200
    user_id = await _current_user_id(session_factory)

    # Anonymous caller — no 403.
    response = await client.delete("/api/account")
    assert response.status_code == 204

    async with session_factory() as s:
        assert (
            await s.execute(
                select(func.count()).select_from(User).where(User.id == user_id)
            )
        ).scalar_one() == 0
