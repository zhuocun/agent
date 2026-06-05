"""Project/Space CRUD tests (D20).

Covers:
- CRUD on `/api/projects` (list / create / patch / delete), caller-scoped.
- Audit events emitted for each mutation (`project.created` / `_updated` /
  `_deleted`).
- Ownership isolation: a forged id can't read/edit/delete another user's project
  (404, never 403).
- Name validation (blank rejected) + unknown `defaultTierId` rejected.
- Three-valued PATCH: a value sets a setting, explicit `null` clears it back to
  inherit, omission leaves it unchanged.
- Deleting a project un-files (does NOT delete) the conversations under it.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, Conversation, Project, User

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


async def test_project_crud_lifecycle(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # List is empty initially.
    listed = await client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json() == []

    # Create a project with all settings.
    created = await client.post(
        "/api/projects",
        json={
            "name": "  Research  ",
            "customInstructions": "Cite sources.",
            "defaultTierId": "smart",
            "retentionDays": 30,
            "perConversationBudgetUsd": 1.5,
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Research"  # stripped
    assert project["customInstructions"] == "Cite sources."
    assert project["defaultTierId"] == "smart"
    assert project["retentionDays"] == 30
    assert project["perConversationBudgetUsd"] == 1.5
    project_id = project["id"]

    # List now returns it.
    listed = await client.get("/api/projects")
    assert [p["id"] for p in listed.json()] == [project_id]

    # Patch the name + clear one setting (three-valued null).
    patched = await client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Deep Research", "defaultTierId": None},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Deep Research"
    assert patched.json()["defaultTierId"] is None
    # Untouched fields survive.
    assert patched.json()["retentionDays"] == 30
    assert patched.json()["customInstructions"] == "Cite sources."

    # Delete it.
    deleted = await client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204

    listed = await client.get("/api/projects")
    assert listed.json() == []

    # Audit trail recorded one of each.
    types = await _audit_types(session_factory)
    assert "project.created" in types
    assert "project.updated" in types
    assert "project.deleted" in types


async def test_project_create_rejects_blank_name(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post("/api/projects", json={"name": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_project_create_rejects_unknown_tier(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post(
        "/api/projects", json={"name": "X", "defaultTierId": "ultra"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_project_patch_missing_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.patch(
        f"/api/projects/{uuid4()}", json={"name": "nope"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_project_delete_missing_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.delete(f"/api/projects/{uuid4()}")
    assert resp.status_code == 404


async def test_project_is_caller_scoped(
    app: object,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second user cannot read, edit, or delete the first user's project."""
    await client.get("/api/bootstrap")
    created = await client.post("/api/projects", json={"name": "User A project"})
    project_id = created.json()["id"]

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        listed_b = await client_b.get("/api/projects")
        assert listed_b.json() == []
        assert (
            await client_b.patch(
                f"/api/projects/{project_id}", json={"name": "hijack"}
            )
        ).status_code == 404
        assert (
            await client_b.delete(f"/api/projects/{project_id}")
        ).status_code == 404

    listed_a = await client.get("/api/projects")
    assert [p["id"] for p in listed_a.json()] == [project_id]
    assert listed_a.json()[0]["name"] == "User A project"


async def test_project_patch_omitted_field_unchanged(client: AsyncClient) -> None:
    """A PATCH omitting a settings field leaves it untouched (not cleared)."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/projects",
        json={"name": "P", "retentionDays": 90, "customInstructions": "keep me"},
    )
    project_id = created.json()["id"]

    # Patch only the name; retentionDays + customInstructions must survive.
    patched = await client.patch(
        f"/api/projects/{project_id}", json={"name": "P2"}
    )
    assert patched.json()["retentionDays"] == 90
    assert patched.json()["customInstructions"] == "keep me"


async def test_delete_project_unfiles_conversations(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting a project SET-NULLs its conversations' membership, not deletes."""
    await client.get("/api/bootstrap")
    created = await client.post("/api/projects", json={"name": "Filing"})
    project_id = created.json()["id"]

    convo = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": False, "projectId": project_id},
    )
    convo_id = convo.json()["id"]
    assert convo.json()["projectId"] == project_id

    # Delete the project.
    assert (await client.delete(f"/api/projects/{project_id}")).status_code == 204

    # The conversation survives, now un-filed.
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Conversation).where(Conversation.id == UUID(convo_id))
            )
        ).scalar_one()
        assert row.project_id is None
    # And via the API.
    fetched = await client.get(f"/api/conversations/{convo_id}")
    assert fetched.status_code == 200
    assert fetched.json()["projectId"] is None


async def test_bootstrap_includes_projects(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/projects", json={"name": "Boot project"})

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    payload = boot.json()
    assert "projects" in payload
    names = [p["name"] for p in payload["projects"]]
    assert "Boot project" in names


async def test_export_includes_projects(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/projects", json={"name": "Export project"})

    resp = await client.get("/api/account/export")
    assert resp.status_code == 200
    payload = resp.json()
    assert "projects" in payload
    names = [p["name"] for p in payload["projects"]]
    assert "Export project" in names


async def test_delete_account_erases_projects(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await client.post("/api/projects", json={"name": "Erase project"})

    async with session_factory() as session:
        before = (await session.execute(select(Project))).scalars().all()
        assert len(before) == 1
        user = (await session.execute(select(User))).scalar_one()
        confirmation = user.email or "DELETE"

    resp = await client.request(
        "DELETE", "/api/account", json={"confirmation": confirmation}
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        after = (await session.execute(select(Project))).scalars().all()
        assert after == []
