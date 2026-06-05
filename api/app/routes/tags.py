"""Tag CRUD — user-scoped labels for conversations (Conversation Org v2).

Four caller-scoped endpoints under `/api/tags`, all anonymous-allowed (guests
label conversations too) and all scoped to the caller.

- `GET    /tags`        — list the caller's tags, name-ordered.
- `POST   /tags`        — create a tag.
- `PATCH  /tags/{id}`   — update a tag's name / color (color three-valued).
- `DELETE /tags/{id}`   — delete a tag (also clears its conversation assignments).

Each mutation emits an audit event (`tag.created` / `tag.updated` /
`tag.deleted`) via `audit_events.record`, mirroring the trust-surface convention
`area.action`. The repository scopes every read/write to `user.id`, so a forged
id can never touch another user's tag (404, never 403).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import Tag as TagRow
from app.db.models import User
from app.db.repositories import audit_events
from app.db.repositories import tags as tags_repo
from app.db.session import get_db
from app.errors import not_found
from app.middleware.ratelimit import limiter
from app.schemas.tag import Tag, TagCreateRequest, TagUpdateRequest

router = APIRouter(prefix="/api/tags", tags=["tags"])


def _to_schema(row: TagRow) -> Tag:
    return Tag(
        id=str(row.id),
        name=row.name,
        color=row.color,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("", response_model=list[Tag])
@limiter.limit(lambda: get_settings().rate_limit_tags)
async def list_tags(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Tag]:
    """Return the caller's tags, name-ordered. Scoped to `user.id`."""
    rows = await tags_repo.list_for_user(db, user.id)
    return [_to_schema(row) for row in rows]


@router.post("", response_model=Tag, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().rate_limit_tags)
async def create_tag(
    body: TagCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Tag:
    """Create a tag for the caller and emit `tag.created`."""
    row = await tags_repo.create_for_user(
        db,
        user_id=user.id,
        name=body.name,
        color=body.color,
    )
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="tag.created",
        details={"tagId": str(row.id)},
    )
    return _to_schema(row)


@router.patch("/{tag_id}", response_model=Tag)
@limiter.limit(lambda: get_settings().rate_limit_tags)
async def update_tag(
    tag_id: UUID,
    body: TagUpdateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Tag:
    """Update a tag's name / color and emit `tag.updated`.

    `color` is THREE-VALUED: `model_fields_set` distinguishes "omitted" (leave
    unchanged) from an explicit `null` (clear the color). Not owned -> 404.
    """
    fields_set = body.model_fields_set
    update_kwargs: dict[str, object] = {"name": body.name}
    if "color" in fields_set:
        update_kwargs["color"] = body.color
    row = await tags_repo.update_for_user(
        db,
        tag_id=tag_id,
        user_id=user.id,
        **update_kwargs,  # type: ignore[arg-type]
    )
    if row is None:
        raise not_found("tag")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="tag.updated",
        details={"tagId": str(row.id)},
    )
    return _to_schema(row)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_tags)
async def delete_tag(
    tag_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a tag and emit `tag.deleted`. Not owned -> 404.

    Deleting a tag also removes its conversation assignments (the join rows), so
    chips disappear from any conversation that carried it — the conversations
    themselves are untouched.
    """
    deleted = await tags_repo.delete_for_user(db, tag_id=tag_id, user_id=user.id)
    if not deleted:
        raise not_found("tag")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="tag.deleted",
        details={"tagId": str(tag_id)},
    )


__all__ = ["router"]
