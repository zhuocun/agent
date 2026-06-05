"""Tag CRUD tests (Conversation Org v2).

Covers:
- CRUD on `/api/tags` (list / create / patch / delete), caller-scoped.
- Audit events emitted for each mutation (`tag.created` / `_updated` /
  `_deleted`).
- Ownership isolation: a forged id can't read/edit/delete another user's tag
  (404, never 403).
- Name validation (blank rejected).
- Three-valued PATCH on `color`: a value sets it, explicit `null` clears it,
  omission leaves it unchanged.
- Bootstrap inclusion + export inclusion + erasure.
- Deleting a tag clears its conversation assignments (chips disappear) without
  deleting the conversations.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, Tag, User

pytestmark = pytest.mark.asyncio


async def _audit_types(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).order_by(AuditEvent.created_at.asc())
            )
        ).scalars().all()
        return [r.event_type for r in rows]


# CRUD -------------------------------------------------------------------------


async def test_tag_crud_lifecycle(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # List is empty initially.
    listed = await client.get("/api/tags")
    assert listed.status_code == 200
    assert listed.json() == []

    # Create a tag with a color, name stripped.
    created = await client.post(
        "/api/tags", json={"name": "  Work  ", "color": "#ff0000"}
    )
    assert created.status_code == 201
    tag = created.json()
    assert tag["name"] == "Work"  # stripped
    assert tag["color"] == "#ff0000"
    assert "createdAt" in tag and "updatedAt" in tag
    tag_id = tag["id"]

    # List now returns it.
    listed = await client.get("/api/tags")
    assert [t["id"] for t in listed.json()] == [tag_id]

    # Patch the name + clear the color (three-valued null).
    patched = await client.patch(
        f"/api/tags/{tag_id}", json={"name": "Job", "color": None}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Job"
    assert patched.json()["color"] is None

    # Delete it.
    deleted = await client.delete(f"/api/tags/{tag_id}")
    assert deleted.status_code == 204

    listed = await client.get("/api/tags")
    assert listed.json() == []

    # Audit trail recorded one of each.
    types = await _audit_types(session_factory)
    assert "tag.created" in types
    assert "tag.updated" in types
    assert "tag.deleted" in types


async def test_tag_create_rejects_blank_name(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post("/api/tags", json={"name": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_tag_patch_missing_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.patch(f"/api/tags/{uuid4()}", json={"name": "nope"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_tag_delete_missing_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.delete(f"/api/tags/{uuid4()}")
    assert resp.status_code == 404


async def test_tag_patch_omitted_color_unchanged(client: AsyncClient) -> None:
    """A PATCH omitting `color` leaves it untouched (not cleared)."""
    await client.get("/api/bootstrap")
    created = await client.post("/api/tags", json={"name": "T", "color": "blue"})
    tag_id = created.json()["id"]

    # Patch only the name; color must survive.
    patched = await client.patch(f"/api/tags/{tag_id}", json={"name": "T2"})
    assert patched.json()["color"] == "blue"


async def test_tag_is_caller_scoped(
    app: object,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second user cannot read, edit, or delete the first user's tag."""
    await client.get("/api/bootstrap")
    created = await client.post("/api/tags", json={"name": "User A tag"})
    tag_id = created.json()["id"]

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        listed_b = await client_b.get("/api/tags")
        assert listed_b.json() == []
        assert (
            await client_b.patch(f"/api/tags/{tag_id}", json={"name": "hijack"})
        ).status_code == 404
        assert (
            await client_b.delete(f"/api/tags/{tag_id}")
        ).status_code == 404

    listed_a = await client.get("/api/tags")
    assert [t["id"] for t in listed_a.json()] == [tag_id]
    assert listed_a.json()[0]["name"] == "User A tag"


async def test_bootstrap_includes_tags(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/tags", json={"name": "Boot tag"})

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    payload = boot.json()
    assert "tags" in payload
    names = [t["name"] for t in payload["tags"]]
    assert "Boot tag" in names


async def test_export_includes_tags(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/tags", json={"name": "Export tag"})

    resp = await client.get("/api/account/export")
    assert resp.status_code == 200
    payload = resp.json()
    assert "tags" in payload
    names = [t["name"] for t in payload["tags"]]
    assert "Export tag" in names


async def test_delete_account_erases_tags(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/tags", json={"name": "Erase tag"})

    async with session_factory() as session:
        before = (await session.execute(select(Tag))).scalars().all()
        assert len(before) == 1
        user = (await session.execute(select(User))).scalar_one()
        confirmation = user.email or "DELETE"

    resp = await client.request(
        "DELETE", "/api/account", json={"confirmation": confirmation}
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        after = (await session.execute(select(Tag))).scalars().all()
        assert after == []


async def test_delete_tag_clears_assignments_keeps_conversation(
    client: AsyncClient,
) -> None:
    """Deleting a tag drops its chips but leaves the tagged conversation alive."""
    await client.get("/api/bootstrap")
    tag = (await client.post("/api/tags", json={"name": "Temp"})).json()
    convo = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False},
    )
    convo_id = convo.json()["id"]

    # Assign the tag via PATCH (full replace).
    assigned = await client.patch(
        f"/api/conversations/{convo_id}", json={"tagIds": [tag["id"]]}
    )
    assert assigned.status_code == 200
    assert assigned.json()["tagIds"] == [tag["id"]]

    # Delete the tag.
    assert (await client.delete(f"/api/tags/{tag['id']}")).status_code == 204

    # Conversation survives; its tagIds is now empty.
    fetched = await client.get(f"/api/conversations/{convo_id}")
    assert fetched.status_code == 200
    assert fetched.json()["tagIds"] == []
