"""Prompt library + user-authored templates tests (D23).

Covers:
- CRUD on `/api/account/prompt-templates` (list / create / edit / delete),
  caller-scoped.
- Audit events emitted for each mutation (`prompt_template.created` /
  `_updated` / `_deleted`).
- Ownership isolation: a forged id can't edit/delete another user's template
  (404, never 403).
- Empty title/body rejected as INVALID_INPUT (400).
- The account export includes the caller's template library.
- Account erasure removes the caller's templates.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, PromptTemplate, User

pytestmark = pytest.mark.asyncio


async def _audit_types(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditEvent).order_by(AuditEvent.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [r.event_type for r in rows]


# CRUD -------------------------------------------------------------------------


async def test_prompt_template_crud_lifecycle(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")

    # List is empty initially.
    listed = await client.get("/api/account/prompt-templates")
    assert listed.status_code == 200
    assert listed.json() == []

    # Create a template (title + body trimmed; description optional).
    created = await client.post(
        "/api/account/prompt-templates",
        json={
            "title": "  Blog post  ",
            "body": "  Write a blog post about {{topic}}.  ",
            "description": "  Long-form draft  ",
        },
    )
    assert created.status_code == 201
    template = created.json()
    assert template["title"] == "Blog post"  # trimmed
    assert template["body"] == "Write a blog post about {{topic}}."  # trimmed
    assert template["description"] == "Long-form draft"  # trimmed
    template_id = template["id"]

    # List now returns it.
    listed = await client.get("/api/account/prompt-templates")
    assert [t["id"] for t in listed.json()] == [template_id]

    # Edit it (and clear the description by sending a blank one).
    edited = await client.patch(
        f"/api/account/prompt-templates/{template_id}",
        json={
            "title": "Blog post v2",
            "body": "Write a detailed post about {{topic}} for {{audience}}.",
            "description": "   ",
        },
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["title"] == "Blog post v2"
    assert body["body"] == "Write a detailed post about {{topic}} for {{audience}}."
    assert body["description"] is None  # blank description normalized to null

    # Delete it.
    deleted = await client.delete(
        f"/api/account/prompt-templates/{template_id}"
    )
    assert deleted.status_code == 204

    listed = await client.get("/api/account/prompt-templates")
    assert listed.json() == []

    # Audit trail recorded one of each.
    types = await _audit_types(session_factory)
    assert "prompt_template.created" in types
    assert "prompt_template.updated" in types
    assert "prompt_template.deleted" in types


async def test_prompt_template_create_rejects_empty_title(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post(
        "/api/account/prompt-templates",
        json={"title": "   ", "body": "Some body."},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_prompt_template_create_rejects_empty_body(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    resp = await client.post(
        "/api/account/prompt-templates",
        json={"title": "A title", "body": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_prompt_template_edit_missing_is_404(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    resp = await client.patch(
        f"/api/account/prompt-templates/{uuid4()}",
        json={"title": "nope", "body": "nope"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_prompt_template_delete_missing_is_404(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    resp = await client.delete(f"/api/account/prompt-templates/{uuid4()}")
    assert resp.status_code == 404


async def test_prompt_template_is_caller_scoped(
    app: object,
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second user cannot read, edit, or delete the first user's templates."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/account/prompt-templates",
        json={"title": "User A template", "body": "Secret body {{x}}."},
    )
    template_id = created.json()["id"]

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        # B's list never contains A's template.
        listed_b = await client_b.get("/api/account/prompt-templates")
        assert listed_b.json() == []
        # B cannot edit or delete A's template (404, never 403).
        assert (
            await client_b.patch(
                f"/api/account/prompt-templates/{template_id}",
                json={"title": "hijack", "body": "hijack"},
            )
        ).status_code == 404
        assert (
            await client_b.delete(
                f"/api/account/prompt-templates/{template_id}"
            )
        ).status_code == 404

    # A's template is untouched.
    listed_a = await client.get("/api/account/prompt-templates")
    assert [t["id"] for t in listed_a.json()] == [template_id]
    assert listed_a.json()[0]["title"] == "User A template"


# Export -----------------------------------------------------------------------


async def test_export_includes_prompt_templates(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    await client.post(
        "/api/account/prompt-templates",
        json={"title": "Export me", "body": "Export body {{topic}}."},
    )

    resp = await client.get("/api/account/export")
    assert resp.status_code == 200
    payload = resp.json()
    assert "promptTemplates" in payload
    titles = [t["title"] for t in payload["promptTemplates"]]
    assert "Export me" in titles


async def test_delete_account_erases_prompt_templates(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await client.post(
        "/api/account/prompt-templates",
        json={"title": "Erase me", "body": "Erase body."},
    )

    async with session_factory() as session:
        before = (
            (await session.execute(select(PromptTemplate))).scalars().all()
        )
        assert len(before) == 1
        user = (await session.execute(select(User))).scalar_one()
        confirmation = user.email or "DELETE"

    resp = await client.request(
        "DELETE", "/api/account", json={"confirmation": confirmation}
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        after = (await session.execute(select(PromptTemplate))).scalars().all()
        assert after == []
