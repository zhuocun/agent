"""`GET /api/bootstrap` — one-shot first-paint payload.

Idempotent. Works for anonymous users — synthesizes an empty-email AccountInfo
and (since M2) loads `UserPreferences` from the DB if a row exists, falling
back to the hard-coded defaults otherwise (see
`app.db.repositories.preferences.get_or_default`). Side-effect: triggers the
`current_user` dependency, which creates an anonymous user + session on first
hit. No preferences row is auto-created on bootstrap — it lands only when the
user actually calls `PUT /api/preferences`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.account_info import account_info_for_user, usable_provider_ids_for_user
from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import User
from app.db.repositories import conversations, preferences, usage
from app.db.session import get_db
from app.providers.tiers import list_tiers
from app.schemas.bootstrap import BootstrapResponse
from app.suggestions import list_suggestions

router = APIRouter(prefix="/api", tags=["bootstrap"])

@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> BootstrapResponse:
    settings = get_settings()
    account = await account_info_for_user(db, user, settings)
    usable_provider_ids = await usable_provider_ids_for_user(db, user, settings)
    prefs = await preferences.get_or_default(db, user.id)
    if prefs.retention_days is not None:
        await conversations.delete_older_than_for_user(
            db,
            user_id=user.id,
            cutoff=datetime.now(UTC) - timedelta(days=prefs.retention_days),
        )
    budget = await usage.get_current_budget(
        db,
        user.id,
        is_byok=account.byok_enabled,
        monthly_quota_usd=settings.usage_budget_usd,
    )
    summaries = await conversations.list_summaries_for_user(db, user.id)
    return BootstrapResponse(
        account=account,
        preferences=prefs,
        usage=budget,
        model_tiers=list_tiers(settings, usable_provider_ids=usable_provider_ids),
        suggestions=list_suggestions(),
        conversations=summaries,
    )
