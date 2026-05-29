"""Account data routes — GDPR export + right-to-erasure (PRD 05 §7.3, PRD 04 §5.7).

Two endpoints under the `/api/account` prefix that let any caller (including
anonymous users — they accrue data too) get all their data out and erase their
account:

- `GET /api/account/export` -> 200 JSON. A single self-contained, camelCase
  document of everything we hold for the caller. Served with a
  `Content-Disposition: attachment` header so a browser downloads it. Reuses the
  same byok-masked `AccountInfo` as bootstrap — it NEVER leaks the decrypted
  BYOK key, the ciphertext, or any session secret.

- `DELETE /api/account` -> 204. Permanently deletes the caller's account and all
  associated data, then clears the session cookie. The session row is gone, so
  the next request mints a fresh anonymous user — the desired erasure behavior.

Kept in a sibling module to `account.py` so the BYOK concerns there stay
untouched. Both routers share the `/api/account` prefix and are mounted in
`app/main.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import COOKIE_NAME_DEFAULT, cookie_kwargs
from app.auth.dependency import current_user
from app.config import Settings, get_settings
from app.db.models import User
from app.db.repositories import api_keys, conversations, preferences, usage, users
from app.db.session import get_db
from app.schemas.account import AccountExport
from app.schemas.conversation import Conversation as ConversationSchema

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/export")
async def export_account(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return a single JSON document of everything we hold for the caller.

    `Content-Disposition: attachment` makes a browser download it. The payload
    reuses the byok-masked `AccountInfo` (no ciphertext, no decrypted key) and
    carries no session-secret material — it must not leak secrets.
    """
    byok_rows = await api_keys.list_for_user(db, user.id)
    has_byok_key = (not user.is_anonymous) and len(byok_rows) > 0
    masked = byok_rows[0].masked_key if has_byok_key else None
    account = users.to_account_info(
        user, byok_enabled=has_byok_key, byok_masked_key=masked
    )
    budget = await usage.get_current_budget(db, user.id, is_byok=has_byok_key)
    prefs = await preferences.get_or_default(db, user.id)

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
        preferences=prefs,
        usage=budget,
        conversations=full,
        exported_at=datetime.now(UTC).isoformat(),
    )
    return JSONResponse(
        content=export.model_dump(by_alias=True),
        headers={
            "Content-Disposition": 'attachment; filename="account-export.json"'
        },
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Permanently delete the caller's account + all data, then clear the cookie.

    The repo flushes in FK-dependency order (the request dependency commits on
    success). After deletion the caller's session row is gone, so the NEXT
    request mints a fresh anonymous user — the desired right-to-erasure
    behavior. The cookie is cleared with the same path/samesite/secure attrs the
    signout handler uses so the browser actually drops it.
    """
    await users.delete_user_and_data(db, user_id=user.id)

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
