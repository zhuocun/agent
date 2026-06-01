"""User preferences route (M2).

`PUT /api/preferences` replaces the user's preferences row in full. Pydantic
validates the request body (camelCase via alias generator). Anonymous users CAN
set preferences — the row keys off the user id, which exists for anon users too.
`telemetryEnabled` is optional for stale clients; omission preserves the
existing saved value instead of re-enabling telemetry.

Returns 204. The bootstrap response surfaces the saved values on the next
hit (see `app.routes.bootstrap`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.db.models import User
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import preferences as preferences_repo
from app.db.session import get_db
from app.schemas.preferences import UserPreferences, UserPreferencesRequest

router = APIRouter(prefix="/api", tags=["preferences"])


@router.put("/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def put_preferences(
    body: UserPreferencesRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Replace the user's preferences row with `body`.

    `UserPreferences.default_tier_id` is a `ModelTierId` literal — Pydantic
    rejects unknown values (e.g. `"giant"`) at validation time with the
    standard `INVALID_INPUT` envelope from `validation_error_handler`.
    """
    existing = await preferences_repo.get_or_default(db, user.id)
    merged = UserPreferences(
        default_tier_id=body.default_tier_id,
        temporary_by_default=body.temporary_by_default,
        training_opt_in=body.training_opt_in,
        send_on_enter=body.send_on_enter,
        auto_expand_reasoning=body.auto_expand_reasoning,
        telemetry_enabled=(
            body.telemetry_enabled
            if body.telemetry_enabled is not None
            else existing.telemetry_enabled
        ),
        retention_days=body.retention_days,
    )
    await preferences_repo.upsert(db, user.id, merged)
    if body.retention_days is not None:
        await conversations_repo.delete_older_than_for_user(
            db,
            user_id=user.id,
            cutoff=datetime.now(UTC) - timedelta(days=body.retention_days),
        )
    return None
