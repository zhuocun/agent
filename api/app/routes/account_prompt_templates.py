"""Prompt-template CRUD — the user-authored prompt library (D23).

Four caller-scoped endpoints under `/api/account/prompt-templates`, all
anonymous-allowed (guests author templates too) and all scoped to the caller.
Selecting a template prefills the composer (a pure composer prefill — no
model/cost/provider change); the library here is the editable store behind that.

- `GET    /prompt-templates`        — list the caller's templates, newest-first.
- `POST   /prompt-templates`        — create a template.
- `PATCH  /prompt-templates/{id}`   — edit a template.
- `DELETE /prompt-templates/{id}`   — delete a template.

Each mutation emits an audit event (`prompt_template.created` /
`prompt_template.updated` / `prompt_template.deleted`) via `audit_events.record`,
mirroring the trust-surface convention `area.action`. The repository scopes every
read/write to `user.id`, so a forged id can never touch another user's library
(404, never 403).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import PromptTemplate as PromptTemplateRow
from app.db.models import User
from app.db.repositories import audit_events
from app.db.repositories import prompt_templates as templates_repo
from app.db.session import get_db
from app.errors import not_found
from app.middleware.ratelimit import limiter
from app.schemas.prompt_template import (
    PromptTemplate,
    PromptTemplateCreateRequest,
    PromptTemplateUpdateRequest,
)

router = APIRouter(prefix="/api/account/prompt-templates", tags=["account"])


def _to_schema(row: PromptTemplateRow) -> PromptTemplate:
    return PromptTemplate(
        id=str(row.id),
        title=row.title,
        body=row.body,
        description=row.description,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _clean_description(value: str | None) -> str | None:
    """Trim the optional description; treat a blank string as absent."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


@router.get("", response_model=list[PromptTemplate])
@limiter.limit(lambda: get_settings().rate_limit_prompt_templates)
async def list_templates(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PromptTemplate]:
    """Return the caller's templates, newest-first. Scoped to `user.id`."""
    rows = await templates_repo.list_for_user(db, user.id)
    return [_to_schema(row) for row in rows]


@router.post(
    "", response_model=PromptTemplate, status_code=status.HTTP_201_CREATED
)
@limiter.limit(lambda: get_settings().rate_limit_prompt_templates)
async def create_template(
    body: PromptTemplateCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptTemplate:
    """Create a template and emit `prompt_template.created`."""
    # The schema validators already rejected blank title/body; store trimmed.
    row = await templates_repo.add(
        db,
        user_id=user.id,
        title=body.title.strip(),
        body=body.body.strip(),
        description=_clean_description(body.description),
    )
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="prompt_template.created",
        details={"templateId": str(row.id)},
    )
    return _to_schema(row)


@router.patch("/{template_id}", response_model=PromptTemplate)
@limiter.limit(lambda: get_settings().rate_limit_prompt_templates)
async def edit_template(
    template_id: UUID,
    body: PromptTemplateUpdateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptTemplate:
    """Edit a template and emit `prompt_template.updated`. Not owned -> 404."""
    row = await templates_repo.update(
        db,
        template_id=template_id,
        user_id=user.id,
        title=body.title.strip(),
        body=body.body.strip(),
        description=_clean_description(body.description),
    )
    if row is None:
        raise not_found("prompt template")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="prompt_template.updated",
        details={"templateId": str(row.id)},
    )
    return _to_schema(row)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_prompt_templates)
async def delete_template(
    template_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a template and emit `prompt_template.deleted`. Not owned -> 404."""
    deleted = await templates_repo.delete(
        db, template_id=template_id, user_id=user.id
    )
    if not deleted:
        raise not_found("prompt template")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="prompt_template.deleted",
        details={"templateId": str(template_id)},
    )


__all__ = ["router"]
