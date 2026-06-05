"""Conversation archive + bulk-action tests (Conversation Org v2).

Covers:
- PATCH `archived` (three-valued bool toggle) reflected in summaries.
- PATCH `tagIds` full-replace, including clear (`[]`), and ownership 404 for a
  foreign / unknown tag id.
- POST /api/conversations/bulk: archive / unarchive / delete / tag / untag.
- Cross-user IDOR: user B's bulk call cannot touch user A's conversations, and
  the bulk tag action rejects a tag B doesn't own.
- The archived flag rides along on the sidebar summaries.
- DECISION: an expired archived conversation is STILL purged by retention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, User
from app.db.repositories import conversations as conversations_repo

pytestmark = pytest.mark.asyncio


async def _create_conversation(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _summary_by_id(client: AsyncClient, convo_id: str) -> dict:
    boot = await client.get("/api/bootstrap")
    for summary in boot.json()["conversations"]:
        if summary["id"] == convo_id:
            return summary
    raise AssertionError(f"conversation {convo_id} not in bootstrap summaries")


# PATCH archived + tagIds -------------------------------------------------------


async def test_patch_archived_three_valued(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    convo_id = await _create_conversation(client)

    # Default: not archived.
    assert (await _summary_by_id(client, convo_id))["archived"] is False

    # Archive it.
    patched = await client.patch(
        f"/api/conversations/{convo_id}", json={"archived": True}
    )
    assert patched.status_code == 200
    assert patched.json()["archived"] is True
    assert (await _summary_by_id(client, convo_id))["archived"] is True

    # Unarchive it.
    patched = await client.patch(
        f"/api/conversations/{convo_id}", json={"archived": False}
    )
    assert patched.status_code == 200
    assert patched.json()["archived"] is False


async def test_patch_empty_body_rejected(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    convo_id = await _create_conversation(client)
    resp = await client.patch(f"/api/conversations/{convo_id}", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_patch_tag_ids_full_replace_and_clear(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    convo_id = await _create_conversation(client)
    tag_a = (await client.post("/api/tags", json={"name": "A"})).json()
    tag_b = (await client.post("/api/tags", json={"name": "B"})).json()

    # Assign both.
    patched = await client.patch(
        f"/api/conversations/{convo_id}",
        json={"tagIds": [tag_a["id"], tag_b["id"]]},
    )
    assert patched.status_code == 200
    assert sorted(patched.json()["tagIds"]) == sorted([tag_a["id"], tag_b["id"]])

    # Full-replace down to just A.
    patched = await client.patch(
        f"/api/conversations/{convo_id}", json={"tagIds": [tag_a["id"]]}
    )
    assert patched.json()["tagIds"] == [tag_a["id"]]

    # Clear all.
    patched = await client.patch(
        f"/api/conversations/{convo_id}", json={"tagIds": []}
    )
    assert patched.json()["tagIds"] == []


async def test_patch_tag_ids_unknown_tag_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    convo_id = await _create_conversation(client)
    resp = await client.patch(
        f"/api/conversations/{convo_id}", json={"tagIds": [str(uuid4())]}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_patch_tag_ids_foreign_tag_is_404(
    app: object,
    client: AsyncClient,
) -> None:
    """A PATCH can't attach another user's tag to its own conversation."""
    await client.get("/api/bootstrap")
    convo_id = await _create_conversation(client)

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        foreign_tag = (await client_b.post("/api/tags", json={"name": "B"})).json()

    resp = await client.patch(
        f"/api/conversations/{convo_id}", json={"tagIds": [foreign_tag["id"]]}
    )
    assert resp.status_code == 404


# Bulk actions ------------------------------------------------------------------


async def test_bulk_archive_and_unarchive(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    c1 = await _create_conversation(client)
    c2 = await _create_conversation(client)

    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1, c2], "action": "archive"},
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 2
    assert (await _summary_by_id(client, c1))["archived"] is True
    assert (await _summary_by_id(client, c2))["archived"] is True

    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1], "action": "unarchive"},
    )
    assert resp.json()["affected"] == 1
    assert (await _summary_by_id(client, c1))["archived"] is False
    assert (await _summary_by_id(client, c2))["archived"] is True


async def test_bulk_delete(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    c1 = await _create_conversation(client)
    c2 = await _create_conversation(client)

    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1, c2], "action": "delete"},
    )
    assert resp.json()["affected"] == 2
    assert (await client.get(f"/api/conversations/{c1}")).status_code == 404
    assert (await client.get(f"/api/conversations/{c2}")).status_code == 404


async def test_bulk_tag_and_untag(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    c1 = await _create_conversation(client)
    c2 = await _create_conversation(client)
    tag = (await client.post("/api/tags", json={"name": "Bulk"})).json()

    # Tag both.
    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1, c2], "action": "tag", "tagId": tag["id"]},
    )
    assert resp.json()["affected"] == 2
    assert (await client.get(f"/api/conversations/{c1}")).json()["tagIds"] == [
        tag["id"]
    ]
    # Tagging again is idempotent (no duplicate join row, still one tag id).
    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1], "action": "tag", "tagId": tag["id"]},
    )
    assert resp.status_code == 200
    assert (await client.get(f"/api/conversations/{c1}")).json()["tagIds"] == [
        tag["id"]
    ]

    # Untag c1.
    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1], "action": "untag", "tagId": tag["id"]},
    )
    assert resp.json()["affected"] == 1
    assert (await client.get(f"/api/conversations/{c1}")).json()["tagIds"] == []
    assert (await client.get(f"/api/conversations/{c2}")).json()["tagIds"] == [
        tag["id"]
    ]


async def test_bulk_tag_requires_tag_id(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    c1 = await _create_conversation(client)
    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1], "action": "tag"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_bulk_tag_unknown_tag_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    c1 = await _create_conversation(client)
    resp = await client.post(
        "/api/conversations/bulk",
        json={"conversationIds": [c1], "action": "tag", "tagId": str(uuid4())},
    )
    assert resp.status_code == 404


async def test_bulk_is_caller_scoped_idor(
    app: object,
    client: AsyncClient,
) -> None:
    """User B's bulk delete/archive cannot touch user A's conversations."""
    await client.get("/api/bootstrap")
    a_convo = await _create_conversation(client)

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        # B tries to delete A's conversation — silently ignored (affected 0).
        resp = await client_b.post(
            "/api/conversations/bulk",
            json={"conversationIds": [a_convo], "action": "delete"},
        )
        assert resp.status_code == 200
        assert resp.json()["affected"] == 0
        # And archive — also 0.
        resp = await client_b.post(
            "/api/conversations/bulk",
            json={"conversationIds": [a_convo], "action": "archive"},
        )
        assert resp.json()["affected"] == 0

    # A's conversation is untouched: still present and not archived.
    fetched = await client.get(f"/api/conversations/{a_convo}")
    assert fetched.status_code == 200
    assert fetched.json()["archived"] is False


async def test_bulk_tag_idor_foreign_conversation(
    app: object,
    client: AsyncClient,
) -> None:
    """User B can't tag user A's conversation even with B's own tag."""
    await client.get("/api/bootstrap")
    a_convo = await _create_conversation(client)

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        b_tag = (await client_b.post("/api/tags", json={"name": "B"})).json()
        resp = await client_b.post(
            "/api/conversations/bulk",
            json={
                "conversationIds": [a_convo],
                "action": "tag",
                "tagId": b_tag["id"],
            },
        )
        # B's tag is valid for B, but A's conversation is not owned by B → 0.
        assert resp.status_code == 200
        assert resp.json()["affected"] == 0

    assert (await client.get(f"/api/conversations/{a_convo}")).json()["tagIds"] == []


# Retention decision ------------------------------------------------------------


async def test_expired_archived_conversation_is_still_purged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """DECISION: archiving does NOT exempt a conversation from retention purge.

    Seed an ARCHIVED conversation with a per-conversation retention of 1 day and
    an `updated_at` well in the past, then run the user-scoped purge. It must be
    deleted — an archive is an organizational flag, not a "keep forever" pin.
    """
    await client.get("/api/bootstrap")
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        old = datetime.now(UTC) - timedelta(days=10)
        convo = Conversation(
            user_id=user.id,
            title="Archived + expired",
            selected_tier_id="smart",
            pinned=False,
            archived=True,
            retention_days=1,
            created_at=old,
            updated_at=old,
        )
        session.add(convo)
        await session.commit()
        convo_id = convo.id
        user_id = user.id

    async with session_factory() as session:
        purged = await conversations_repo.delete_older_than_for_user(
            session, user_id=user_id, global_retention_days=None
        )
        await session.commit()
        assert purged >= 1

    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == convo_id)
            )
        ).scalar_one_or_none()
        assert row is None
