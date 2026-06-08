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
from app.schemas.common import ModelTierId, coerce_tier
from app.schemas.preferences import (
    KeyboardShortcuts,
    ShortcutOverride,
    UserPreferences,
)


def _coerce_shortcuts(raw: object) -> KeyboardShortcuts:
    """Best-effort coerce a stored JSON value into the override map.

    The column is `NOT NULL DEFAULT '{}'`, but a manual DB edit or schema drift
    could leave a non-conforming value. Skip any entry that doesn't validate
    (non-string id, malformed combo) rather than 500 the read — the same safety
    posture the tier/retention fallbacks take above.
    """
    if not isinstance(raw, dict):
        return {}
    out: KeyboardShortcuts = {}
    for action_id, combo in raw.items():
        if not isinstance(action_id, str) or not isinstance(combo, dict):
            continue
        try:
            out[action_id] = ShortcutOverride.model_validate(combo)
        except ValueError:
            continue
    return out


def _shortcuts_to_db(shortcuts: KeyboardShortcuts) -> dict[str, object]:
    """Serialize the override map to a JSON-storable plain dict."""
    return {
        action_id: combo.model_dump(by_alias=True)
        for action_id, combo in shortcuts.items()
    }


# Mirror web/src/lib/mock-data.ts:MOCK_PREFERENCES.
_DEFAULTS = UserPreferences(
    default_tier_id="auto",
    temporary_by_default=False,
    training_opt_in=False,
    send_on_enter=True,
    auto_expand_reasoning=False,
    telemetry_enabled=True,
    custom_instructions="",
    retention_days=None,
    monthly_budget_usd=None,
    per_conversation_budget_usd=None,
    memory_enabled=False,
    keyboard_shortcuts={},
)


def _row_to_schema(row: Preferences) -> UserPreferences:
    tier: ModelTierId = coerce_tier(row.default_tier_id)
    retention_days = row.retention_days if row.retention_days in (30, 90) else None
    return UserPreferences(
        default_tier_id=tier,
        temporary_by_default=row.temporary_by_default,
        training_opt_in=row.training_opt_in,
        send_on_enter=row.send_on_enter,
        auto_expand_reasoning=row.auto_expand_reasoning,
        telemetry_enabled=row.telemetry_enabled,
        custom_instructions=row.custom_instructions or "",
        retention_days=retention_days,
        monthly_budget_usd=row.monthly_budget_usd,
        per_conversation_budget_usd=row.per_conversation_budget_usd,
        memory_enabled=row.memory_enabled,
        keyboard_shortcuts=_coerce_shortcuts(row.keyboard_shortcuts),
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
                telemetry_enabled=prefs.telemetry_enabled,
                custom_instructions=prefs.custom_instructions,
                retention_days=prefs.retention_days,
                monthly_budget_usd=prefs.monthly_budget_usd,
                per_conversation_budget_usd=prefs.per_conversation_budget_usd,
                memory_enabled=prefs.memory_enabled,
                keyboard_shortcuts=_shortcuts_to_db(prefs.keyboard_shortcuts),
            )
        )
    else:
        row.default_tier_id = prefs.default_tier_id
        row.temporary_by_default = prefs.temporary_by_default
        row.training_opt_in = prefs.training_opt_in
        row.send_on_enter = prefs.send_on_enter
        row.auto_expand_reasoning = prefs.auto_expand_reasoning
        row.telemetry_enabled = prefs.telemetry_enabled
        row.custom_instructions = prefs.custom_instructions
        row.retention_days = prefs.retention_days
        row.monthly_budget_usd = prefs.monthly_budget_usd
        row.per_conversation_budget_usd = prefs.per_conversation_budget_usd
        row.memory_enabled = prefs.memory_enabled
        row.keyboard_shortcuts = _shortcuts_to_db(prefs.keyboard_shortcuts)
        # `updated_at` has no onupdate hook; touch it explicitly so the column
        # reflects the actual mutation time.
        row.updated_at = datetime.now(UTC)
    await db.flush()
