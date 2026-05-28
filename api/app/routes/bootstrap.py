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

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.db.models import User
from app.db.repositories import api_keys, conversations, preferences, usage, users
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
    # Pull all BYOK rows so we can surface masked_key for the first one (the
    # FE's settings-dialog shows a single key today). Anonymous users always
    # render `byokEnabled=false` per plan §"BYOK gating" -- enforced below.
    byok_rows = await api_keys.list_for_user(db, user.id)
    has_byok_key = (not user.is_anonymous) and len(byok_rows) > 0
    masked = byok_rows[0].masked_key if has_byok_key else None
    account = users.to_account_info(
        user, byok_enabled=has_byok_key, byok_masked_key=masked
    )
    budget = await usage.get_current_budget(db, user.id, is_byok=has_byok_key)
    summaries = await conversations.list_summaries_for_user(db, user.id)
    prefs = await preferences.get_or_default(db, user.id)
    return BootstrapResponse(
        account=account,
        preferences=prefs,
        usage=budget,
        model_tiers=list_tiers(),
        suggestions=list_suggestions(),
        conversations=summaries,
    )
