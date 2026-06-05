"""User-facing trust surfaces (PRD 07 §6.5 / PRD 05 §7.4 / PRD 08 §5.6).

Three read/capture endpoints under `/api/account`, all anonymous-allowed and
all scoped to the caller — a prosumer trust surface, explicitly NOT an
enterprise audit console:

- `GET /activity` — the data-access activity log: the caller's own
  `AuditEvent`s, newest-first, keyset-paginated. Never returns another user's
  rows.
- `GET /data-processing` — "where your messages were processed": a rollup
  computed solely from the persisted per-message `attribution`, with the
  jurisdiction read from the LIVE provider registry.
- `POST /moderation-appeal` — request-review capture for a blocked turn,
  recorded as a `moderation.appeal` audit event.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import User
from app.db.repositories import audit_events
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope
from app.middleware.ratelimit import limiter
from app.providers.tiers import get_provider_route
from app.schemas.activity import (
    ActivityEvent,
    DataProcessingBucket,
    DataProcessingRollup,
    ModerationAppealRequest,
)

router = APIRouter(prefix="/api/account", tags=["account"])

_ACTIVITY_LIMIT_DEFAULT = 50
_ACTIVITY_LIMIT_MAX = 200


def _invalid_cursor() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="INVALID_CURSOR",
            severity="error",
            title="Invalid cursor",
            body="The `before` cursor must be `<ISO-8601 timestamp>|<event id>`.",
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _parse_before(before: str | None) -> tuple[datetime, UUID] | None:
    """Parse the composite `<iso>|<uuid>` keyset cursor.

    A naive (tz-less) timestamp is normalized to UTC so a hand-crafted cursor
    can't compare naive-vs-aware at the DB layer. Both halves are required so
    pagination is tie-safe (see `list_recent_for_user`).
    """
    if before is None or before == "":
        return None
    iso, _, raw_id = before.partition("|")
    if not iso or not raw_id:
        raise _invalid_cursor()
    try:
        ts = datetime.fromisoformat(iso)
        cursor_id = UUID(raw_id)
    except ValueError as exc:
        raise _invalid_cursor() from exc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts, cursor_id


@router.get("/activity", response_model=list[ActivityEvent])
@limiter.limit(lambda: get_settings().rate_limit_trust_read)
async def list_activity(
    request: Request,
    response: Response,
    before: str | None = Query(default=None),
    limit: int = Query(default=_ACTIVITY_LIMIT_DEFAULT, ge=1, le=_ACTIVITY_LIMIT_MAX),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityEvent]:
    """Return the caller's own activity events, newest-first.

    Anonymous-allowed (guests accrue data too). The repository scopes to
    `user.id`, so this can never surface another user's rows.
    """
    cursor = _parse_before(before)
    rows = await audit_events.list_recent_for_user(
        db,
        user.id,
        limit=limit,
        before=cursor,
    )
    return [
        ActivityEvent(
            id=str(row.id),
            event_type=row.event_type,
            details=row.details or {},
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


@router.get("/data-processing", response_model=DataProcessingRollup)
@limiter.limit(lambda: get_settings().rate_limit_trust_read)
async def data_processing(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DataProcessingRollup:
    """Return a provider rollup of where the caller's messages were processed.

    Aggregates the persisted per-message `attribution` across the caller's
    owned conversations; the jurisdiction for each provider is read from the
    LIVE registry's `data_policy.data_residency` (never hardcoded). A provider
    with no policy yields `jurisdiction: null`.
    """
    rollup = await audit_events.aggregate_attribution_for_user(db, user.id)
    buckets: list[DataProcessingBucket] = []
    for counts in rollup.by_provider:
        route = get_provider_route(counts.provider_id)
        jurisdiction = (
            route.data_policy.data_residency
            if route is not None and route.data_policy is not None
            else None
        )
        provider_label = route.label if route is not None else counts.provider_label
        buckets.append(
            DataProcessingBucket(
                provider_id=counts.provider_id,
                provider_label=provider_label,
                jurisdiction=jurisdiction,
                message_count=counts.message_count,
                is_byok_count=counts.is_byok_count,
                platform_count=counts.platform_count,
                substitution_count=counts.substitution_count,
            )
        )
    return DataProcessingRollup(
        total_attributed=rollup.total_attributed,
        by_provider=buckets,
    )


@router.post("/moderation-appeal", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_moderation_appeal)
async def moderation_appeal(
    body: ModerationAppealRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Capture a request for review of a blocked turn.

    Records a `moderation.appeal` audit event with the (content-free) reason
    code + source the FE forwarded. This is a capture only — there is no
    operator review tooling here.
    """
    details: dict[str, str] = {}
    if body.reason_code:
        details["reasonCode"] = body.reason_code
    if body.source:
        details["source"] = body.source
    if body.note:
        details["note"] = body.note
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="moderation.appeal",
        details=details,
    )


__all__ = ["router"]
