"""`GET /api/bootstrap` — one-shot first-paint payload.

Idempotent. Works for anonymous users — synthesizes an empty-email AccountInfo
and a default `UserPreferences`. Side-effect: triggers the `current_user`
dependency, which creates an anonymous user + session on first hit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.db.models import User
from app.db.repositories import api_keys, conversations, usage, users
from app.db.session import get_db
from app.providers.tiers import list_tiers
from app.schemas.bootstrap import BootstrapResponse
from app.schemas.preferences import UserPreferences
from app.suggestions import list_suggestions

router = APIRouter(prefix="/api", tags=["bootstrap"])


# Privacy-first defaults — mirror web/src/lib/mock-data.ts:MOCK_PREFERENCES.
_DEFAULT_PREFERENCES = UserPreferences(
    default_tier_id="auto",
    temporary_by_default=False,
    training_opt_in=False,
    send_on_enter=True,
    auto_expand_reasoning=False,
)


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> BootstrapResponse:
    has_byok_key = await api_keys.user_has_any_key(db, user.id)
    account = users.to_account_info(user, byok_enabled=has_byok_key)
    budget = await usage.get_current_budget(db, user.id, is_byok=has_byok_key)
    summaries = await conversations.list_summaries_for_user(db, user.id)
    return BootstrapResponse(
        account=account,
        preferences=_DEFAULT_PREFERENCES,
        usage=budget,
        model_tiers=list_tiers(),
        suggestions=list_suggestions(),
        conversations=summaries,
    )
