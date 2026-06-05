"""Account data routes — GDPR export + right-to-erasure (PRD 05 §7.3, PRD 04 §5.7).

Two endpoints under the `/api/account` prefix that let any caller (including
anonymous users — they accrue data too) get all their data out and erase their
account:

- `GET /api/account/export` -> 200 JSON. A single self-contained, camelCase
  document of everything we hold for the caller. Served with a
  `Content-Disposition: attachment` header so a browser downloads it. Reuses the
  same byok-masked `AccountInfo` as bootstrap — it NEVER leaks the decrypted
  BYOK key, the ciphertext, or any session secret.

- `DELETE /api/account` -> 204. Requires an explicit confirmation body, then
  permanently deletes the caller's account and all associated data and clears
  the session cookie. The session row is gone, so the next request mints a
  fresh anonymous user — the desired erasure behavior.

Kept in a sibling module to `account.py` so the BYOK concerns there stay
untouched. Both routers share the `/api/account` prefix and are mounted in
`app/main.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.account_info import account_info_for_user
from app.auth.cookies import COOKIE_NAME_DEFAULT, cookie_kwargs
from app.auth.dependency import current_user
from app.config import Settings, get_settings
from app.db.models import User
from app.db.repositories import (
    analytics,
    api_keys,
    audit_events,
    conversations,
    preferences,
    usage,
    users,
)
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope
from app.middleware.ratelimit import limiter
from app.schemas.account import (
    AccountDeleteRequest,
    AccountExport,
    AccountExportMetadata,
    AnalyticsEventExport,
    AuditEventExport,
    ByokKeyMetadata,
    SpendAnalytics,
    UsageRollupExport,
)
from app.schemas.conversation import Conversation as ConversationSchema

router = APIRouter(prefix="/api/account", tags=["account"])


def _iso(value: datetime) -> str:
    return value.isoformat()


def _confirmation_required(expected: str) -> AppError:
    return AppError(
        ErrorEnvelope(
            code="CONFIRMATION_REQUIRED",
            severity="error",
            title="Confirmation required",
            body="Type the required confirmation value to delete this account.",
            meta={"expected": expected},
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _expected_delete_confirmation(user: User) -> str:
    return user.email or "DELETE"


@router.get("/export")
@limiter.limit(lambda: get_settings().rate_limit_export)
async def export_account(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return a single JSON document of everything we hold for the caller.

    `Content-Disposition: attachment` makes a browser download it. The payload
    reuses the byok-masked `AccountInfo` (no ciphertext, no decrypted key) and
    carries no session-secret material — it must not leak secrets.
    """
    settings = get_settings()
    byok_rows = await api_keys.list_for_user(db, user.id)
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="account.export",
    )
    account = await account_info_for_user(db, user, settings)
    budget = await usage.get_current_budget(
        db,
        user.id,
        is_byok=account.byok_enabled,
        monthly_quota_usd=settings.usage_budget_usd,
    )
    credit_ledger = await usage.list_credit_entries_for_user(db, user_id=user.id)
    rollups = await usage.list_rollups_for_user(db, user.id)
    prefs = await preferences.get_or_default(db, user.id)
    # Purge expired conversations (global window AND per-conversation overrides,
    # D31) before snapshotting the export so it never ships already-expired data.
    await conversations.delete_older_than_for_user(
        db,
        user_id=user.id,
        global_retention_days=prefs.retention_days,
    )
    audit_rows = await audit_events.list_for_user(db, user.id)
    analytics_rows = await analytics.list_for_user(db, user.id)

    # Full conversations with messages. N+1 is acceptable for an export: list
    # the summaries to learn the ids, then load each full conversation.
    summaries = await conversations.list_summaries_for_user(db, user.id)
    full: list[ConversationSchema] = []
    for summary in summaries:
        convo = await conversations.get_for_user(db, UUID(summary.id), user.id)
        if convo is not None:
            full.append(convo)

    export = AccountExport(
        account=account,
        account_metadata=AccountExportMetadata(
            id=str(user.id),
            created_at=_iso(user.created_at),
            is_anonymous=user.is_anonymous,
        ),
        preferences=prefs,
        usage=budget,
        usage_credit_ledger=credit_ledger,
        usage_rollups=[
            UsageRollupExport(
                period_start=_iso(row.period_start),
                used=row.used,
                limit=row.limit_value,
                cost_usd=float(row.cost_usd),
                is_byok=row.is_byok,
            )
            for row in rollups
        ],
        byok_keys=[
            ByokKeyMetadata(
                provider=row.provider,
                masked_key=row.masked_key,
                created_at=_iso(row.created_at),
            )
            for row in byok_rows
            if not user.is_anonymous
        ],
        conversations=full,
        audit_events=[
            AuditEventExport(
                event_type=row.event_type,
                created_at=_iso(row.created_at),
                details=row.details,
            )
            for row in audit_rows
        ],
        analytics_events=[
            AnalyticsEventExport(
                event_type=row.event_type,
                created_at=_iso(row.created_at),
                properties=row.properties,
            )
            for row in analytics_rows
        ],
        exported_at=datetime.now(UTC).isoformat(),
    )
    return JSONResponse(
        content=export.model_dump(by_alias=True),
        headers={"Content-Disposition": 'attachment; filename="account-export.json"'},
    )


@router.get("/spend", response_model=SpendAnalytics)
@limiter.limit(lambda: get_settings().rate_limit_export)
async def account_spend(
    request: Request,
    response: Response,
    days: Annotated[int, Query()] = 30,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SpendAnalytics:
    """Return the caller's longitudinal spend analytics (PRD 05 §4.5 D27).

    Allowed for anonymous users — they accrue spend too, and this is their own
    data. `days` is clamped to 1..365 (default 30) in the repo rather than
    rejected, so an out-of-range value degrades gracefully. Surfaces BOTH honest
    cost bases (cumulative meter vs surviving messages); see `SpendAnalytics`.
    """
    return await usage.get_spend_analytics(db, user_id=user.id, days=days)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_account_delete)
async def delete_account(
    body: AccountDeleteRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Permanently delete the caller's account + all data, then clear the cookie.

    The repo flushes in FK-dependency order. We commit EXPLICITLY here (before
    clearing the cookie / returning 204) rather than relying solely on the
    request dependency's end-of-request commit: a right-to-erasure success must
    not be signalled (204 + cleared cookie) unless the rows are actually gone.
    A commit failure after the handler returns would otherwise leave the client
    believing its data was erased while the rows survived — silent incomplete
    erasure. Committing here surfaces that failure as a 5xx and leaves the
    cookie intact. The dependency's later commit is then a no-op (nothing
    pending), so there is exactly one effective commit.

    After deletion the caller's session row is gone, so the NEXT request mints a
    fresh anonymous user — the desired right-to-erasure behavior. The cookie is
    cleared with the same path/samesite/secure attrs the signout handler uses so
    the browser actually drops it.
    """
    expected = _expected_delete_confirmation(user)
    if body.confirmation.strip() != expected:
        raise _confirmation_required(expected)

    await users.delete_user_and_data(db, user_id=user.id)
    await audit_events.record(
        db,
        user_id=None,
        event_type="account.delete",
    )
    # Durably commit the cascade BEFORE signalling success. A failure here
    # propagates (the dependency rolls back) and the cookie is never cleared.
    await db.commit()

    cookie_name = settings.cookie_name or COOKIE_NAME_DEFAULT
    kw = cookie_kwargs(settings)
    response.delete_cookie(
        key=cookie_name,
        path=kw["path"],
        samesite=kw["samesite"],
        secure=kw["secure"],
        httponly=kw["httponly"],
    )


__all__ = ["router"]
