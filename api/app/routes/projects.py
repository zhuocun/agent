"""Project/Space CRUD — thin scoping containers for conversations (D20).

Four caller-scoped endpoints under `/api/projects`, all anonymous-allowed
(guests file conversations too) and all scoped to the caller. A Project groups
conversations and scopes the existing wedge controls (default tier, retention,
budget sub-cap, shared instructions) — each a labeled default, never a lock.

- `GET    /projects`        — list the caller's projects, newest-first.
- `POST   /projects`        — create a project.
- `PATCH  /projects/{id}`   — update a project's name / settings (three-valued).
- `DELETE /projects/{id}`   — delete a project (un-files its conversations).

Each mutation emits an audit event (`project.created` / `project.updated` /
`project.deleted`) via `audit_events.record`, mirroring the trust-surface
convention `area.action`. The repository scopes every read/write to `user.id`,
so a forged id can never touch another user's project (404, never 403).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import Project as ProjectRow
from app.db.models import User
from app.db.repositories import audit_events
from app.db.repositories import projects as projects_repo
from app.db.session import get_db
from app.errors import not_found
from app.middleware.ratelimit import limiter
from app.schemas.project import (
    Project,
    ProjectCreateRequest,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _to_schema(row: ProjectRow) -> Project:
    return Project(
        id=str(row.id),
        name=row.name,
        custom_instructions=row.custom_instructions,
        default_tier_id=row.default_tier_id,
        retention_days=row.retention_days,
        per_conversation_budget_usd=row.per_conversation_budget_usd,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("", response_model=list[Project])
@limiter.limit(lambda: get_settings().rate_limit_projects)
async def list_projects(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    """Return the caller's projects, newest-first. Scoped to `user.id`."""
    rows = await projects_repo.list_for_user(db, user.id)
    return [_to_schema(row) for row in rows]


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().rate_limit_projects)
async def create_project(
    body: ProjectCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Create a project for the caller and emit `project.created`."""
    row = await projects_repo.add(
        db,
        user_id=user.id,
        name=body.name,
        custom_instructions=body.custom_instructions,
        default_tier_id=body.default_tier_id,
        retention_days=body.retention_days,
        per_conversation_budget_usd=body.per_conversation_budget_usd,
    )
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="project.created",
        details={"projectId": str(row.id)},
    )
    return _to_schema(row)


@router.patch("/{project_id}", response_model=Project)
@limiter.limit(lambda: get_settings().rate_limit_projects)
async def update_project(
    project_id: UUID,
    body: ProjectUpdateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Update a project's name / settings and emit `project.updated`.

    The four settings columns are THREE-VALUED: `model_fields_set` distinguishes
    "omitted" (leave unchanged) from an explicit `null` (clear back to inherit).
    Not owned -> 404.
    """
    fields_set = body.model_fields_set
    update_kwargs: dict[str, object] = {"name": body.name}
    for field in (
        "custom_instructions",
        "default_tier_id",
        "retention_days",
        "per_conversation_budget_usd",
    ):
        if field in fields_set:
            update_kwargs[field] = getattr(body, field)
    row = await projects_repo.update(
        db,
        project_id=project_id,
        user_id=user.id,
        **update_kwargs,  # type: ignore[arg-type]
    )
    if row is None:
        raise not_found("project")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="project.updated",
        details={"projectId": str(row.id)},
    )
    return _to_schema(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_projects)
async def delete_project(
    project_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a project and emit `project.deleted`. Not owned -> 404.

    Conversations filed under the project are un-filed (membership SET NULL),
    not deleted — a Project is a labeled default, never owning its threads.
    """
    deleted = await projects_repo.delete(db, project_id=project_id, user_id=user.id)
    if not deleted:
        raise not_found("project")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="project.deleted",
        details={"projectId": str(project_id)},
    )


__all__ = ["router"]
