"""Memory-fact CRUD — the editable, attributed fact ledger (D19).

Four caller-scoped endpoints under `/api/account/memory`, all anonymous-allowed
(guests accrue memory too) and all scoped to the caller — the glass-box
differentiator made operable: every fact the assistant may use is a row the user
can read, edit, and delete.

- `GET    /memory`        — list the caller's facts, newest-first.
- `POST   /memory`        — add a fact.
- `PATCH  /memory/{id}`   — edit a fact's content.
- `DELETE /memory/{id}`   — delete a fact.

Each mutation emits an audit event (`memory.fact_added` / `memory.fact_edited` /
`memory.fact_deleted`) via `audit_events.record`, mirroring the trust-surface
convention `area.action`. The repository scopes every read/write to `user.id`,
so a forged id can never touch another user's ledger (404, never 403).
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import MemoryFact as MemoryFactRow
from app.db.models import User
from app.db.repositories import audit_events
from app.db.repositories import memory_facts as memory_repo
from app.db.session import get_db
from app.errors import not_found
from app.middleware.ratelimit import limiter
from app.schemas.memory import (
    MemoryFact,
    MemoryFactCreateRequest,
    MemoryFactUpdateRequest,
)

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/account/memory", tags=["account"])


def _to_schema(row: MemoryFactRow) -> MemoryFact:
    return MemoryFact(
        id=str(row.id),
        content=row.content,
        # The DB column is a free String; narrow unknown values to "manual" so a
        # manual DB edit can't break the wire literal.
        source="conversation" if row.source == "conversation" else "manual",
        source_conversation_id=(
            str(row.source_conversation_id)
            if row.source_conversation_id is not None
            else None
        ),
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("", response_model=list[MemoryFact])
@limiter.limit(lambda: get_settings().rate_limit_memory)
async def list_memory(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryFact]:
    """Return the caller's saved facts, newest-first. Scoped to `user.id`."""
    rows = await memory_repo.list_for_user(db, user.id)
    return [_to_schema(row) for row in rows]


@router.post("", response_model=MemoryFact, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().rate_limit_memory)
async def add_memory(
    body: MemoryFactCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryFact:
    """Add a fact to the caller's ledger and emit `memory.fact_added`."""
    # The schema validator already rejected blank content; store the trimmed form.
    content = body.content.strip()
    source_conversation_id: UUID | None = None
    if body.source_conversation_id:
        try:
            source_conversation_id = UUID(body.source_conversation_id)
        except ValueError:
            _log.warning(
                "memory.invalid_source_conversation_id",
                raw_value=body.source_conversation_id,
            )
            source_conversation_id = None
    row = await memory_repo.add(
        db,
        user_id=user.id,
        content=content,
        source="conversation" if source_conversation_id is not None else "manual",
        source_conversation_id=source_conversation_id,
    )
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="memory.fact_added",
        details={"factId": str(row.id), "source": row.source},
    )
    return _to_schema(row)


@router.patch("/{fact_id}", response_model=MemoryFact)
@limiter.limit(lambda: get_settings().rate_limit_memory)
async def edit_memory(
    fact_id: UUID,
    body: MemoryFactUpdateRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryFact:
    """Edit a fact's content and emit `memory.fact_edited`. Not owned -> 404."""
    row = await memory_repo.update_content(
        db,
        fact_id=fact_id,
        user_id=user.id,
        content=body.content.strip(),
    )
    if row is None:
        raise not_found("memory fact")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="memory.fact_edited",
        details={"factId": str(row.id)},
    )
    return _to_schema(row)


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_memory)
async def delete_memory(
    fact_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a fact and emit `memory.fact_deleted`. Not owned -> 404."""
    deleted = await memory_repo.delete(db, fact_id=fact_id, user_id=user.id)
    if not deleted:
        raise not_found("memory fact")
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="memory.fact_deleted",
        details={"factId": str(fact_id)},
    )


__all__ = ["router"]
