"""Preferences repository.

M2 introduces the `preferences` table. One row per user. The wire shape is
`UserPreferences` (camelCase via Pydantic aliases); the DB column names mirror
the snake_case fields.

Bootstrap strategy (chosen): preferences are NOT eagerly created when an
anonymous user is provisioned. Instead, `GET /api/bootstrap` calls
`get_or_default(user_id)` — if a row exists it's returned, otherwise the
hard-coded defaults are returned WITHOUT a write. The row only lands when
`PUT /api/preferences` runs. This keeps the write path explicit (no surprise
inserts on every read) and makes `GET /api/bootstrap` cheap and sync-correct.
The defaults live in this module as `_DEFAULTS` (mirrored in
`web/src/lib/mock-data.ts:MOCK_PREFERENCES`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Preferences
from app.schemas.common import ModelTierId
from app.schemas.preferences import UserPreferences

_VALID_TIERS: tuple[ModelTierId, ...] = ("fast", "smart", "pro", "auto")


# Mirror web/src/lib/mock-data.ts:MOCK_PREFERENCES.
_DEFAULTS = UserPreferences(
    default_tier_id="auto",
    temporary_by_default=False,
    training_opt_in=False,
    send_on_enter=True,
    auto_expand_reasoning=False,
)


def _row_to_schema(row: Preferences) -> UserPreferences:
    # Coerce DB string -> ModelTierId. If somehow the row holds an unknown tier
    # id (manual DB edit, schema drift), fall back to "auto" — same safety net
    # the conversations repo uses.
    tier_value = row.default_tier_id
    tier: ModelTierId = tier_value if tier_value in _VALID_TIERS else "auto"
    return UserPreferences(
        default_tier_id=tier,
        temporary_by_default=row.temporary_by_default,
        training_opt_in=row.training_opt_in,
        send_on_enter=row.send_on_enter,
        auto_expand_reasoning=row.auto_expand_reasoning,
    )


async def get_or_default(db: AsyncSession, user_id: UUID) -> UserPreferences:
    """Return the user's preferences row, or the hard-coded defaults."""
    stmt = select(Preferences).where(Preferences.user_id == user_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return _DEFAULTS
    return _row_to_schema(row)


async def upsert(db: AsyncSession, user_id: UUID, prefs: UserPreferences) -> None:
    """Insert or update the preferences row for `user_id`.

    Cross-dialect upsert via select-then-update-or-insert (matches the votes
    repo pattern; see `votes.upsert` for the rationale).
    """
    stmt = select(Preferences).where(Preferences.user_id == user_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        db.add(
            Preferences(
                user_id=user_id,
                default_tier_id=prefs.default_tier_id,
                temporary_by_default=prefs.temporary_by_default,
                training_opt_in=prefs.training_opt_in,
                send_on_enter=prefs.send_on_enter,
                auto_expand_reasoning=prefs.auto_expand_reasoning,
            )
        )
    else:
        row.default_tier_id = prefs.default_tier_id
        row.temporary_by_default = prefs.temporary_by_default
        row.training_opt_in = prefs.training_opt_in
        row.send_on_enter = prefs.send_on_enter
        row.auto_expand_reasoning = prefs.auto_expand_reasoning
        # `updated_at` has no onupdate hook; touch it explicitly so the column
        # reflects the actual mutation time.
        row.updated_at = datetime.now(UTC)
    await db.flush()
