"""User preferences route (M2).

`PUT /api/preferences` replaces the user's preferences row in full. Pydantic
validates the `UserPreferences` body (camelCase via alias generator). Anonymous
users CAN set preferences — the row keys off the user id, which exists for
anon users too.

Returns 204. The bootstrap response surfaces the saved values on the next
hit (see `app.routes.bootstrap`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.db.models import User
from app.db.repositories import preferences as preferences_repo
from app.db.session import get_db
from app.schemas.preferences import UserPreferences

router = APIRouter(prefix="/api", tags=["preferences"])


@router.put("/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def put_preferences(
    body: UserPreferences,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Replace the user's preferences row with `body`.

    `UserPreferences.default_tier_id` is a `ModelTierId` literal — Pydantic
    rejects unknown values (e.g. `"giant"`) at validation time with the
    standard `INVALID_INPUT` envelope from `validation_error_handler`.
    """
    await preferences_repo.upsert(db, user.id, body)
    return None
