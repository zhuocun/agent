"""Auth routes.

- `POST /api/auth/upgrade` (M3) -- promote an anonymous user to email/password.
  Mutates the CURRENT user row in place (`is_anonymous=False`, sets `email`,
  optionally hashes `password`). The row id is unchanged, so every FK from
  `conversation.user_id` / `api_key.user_id` / `preferences.user_id` continues
  to point at the same user without any data migration. This is the whole
  reason the anonymous-first seam is shaped this way (plan §"Auth seam").

- `POST /api/auth/signout` -- clears the cookie and revokes the session row.

Passkey / magic-link / email-verification ceremonies are deferred. The MVP
contract is just "give me an email, I'll optionally take a password, I'll
return the upgraded AccountInfo."

Password hashing is delegated to `app.security.passwords`: new digests are
argon2id, legacy bcrypt rows are verified and opportunistically rewritten on
their first successful login. Bcrypt remains a runtime dep for that fallback.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Response, status
from pydantic import EmailStr
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import (
    COOKIE_NAME_DEFAULT,
    build_signer,
    cookie_kwargs,
    dump_session_id,
)
from app.auth.dependency import current_session, current_user
from app.config import Settings, get_settings
from app.db.models import Session as DbSession
from app.db.models import User
from app.db.repositories import api_keys, users
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope
from app.schemas.account import AccountInfo
from app.schemas.common import CamelModel
from app.security.passwords import (
    _truncate_for_bcrypt as _truncate_for_bcrypt_impl,
)
from app.security.passwords import (
    hash_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_log = structlog.get_logger(__name__)


# Re-export of the boundary-safe bcrypt truncation. The helper itself moved to
# `app.security.passwords` along with the rest of the password machinery; this
# alias keeps the existing test suite (which imports it from `app.auth.routes`)
# working without churning the import site.
_truncate_for_bcrypt = _truncate_for_bcrypt_impl


class UpgradeRequest(CamelModel):
    """Body for POST /api/auth/upgrade.

    Email is required. Password is optional for MVP -- without it the user can
    only sign back in via the (M4+) passwordless flow. Pydantic's `EmailStr`
    enforces basic validity at validation time; the wider envelope (existing
    anon, already taken, etc.) is checked in the route.
    """

    email: EmailStr
    password: str | None = None


def _already_upgraded() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="ALREADY_UPGRADED",
            severity="error",
            title="Already signed in",
            body="This session is already attached to a non-anonymous account.",
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _email_taken() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="EMAIL_TAKEN",
            severity="error",
            title="Email already in use",
            body="An account with that email already exists.",
        ),
        status.HTTP_409_CONFLICT,
    )


def _resign_session_cookie(
    response: Response,
    settings: Settings,
    session: DbSession,
) -> None:
    """Re-emit `Set-Cookie sid=...` for the existing session id.

    Defensive against signature drift / key rotation: the session id itself
    does not change on upgrade, so functionally the cookie value is usually
    identical to what the browser already holds. We re-sign and re-set it
    anyway so a `SESSION_SECRET` rotation between the previous request and
    this one doesn't leave the client stuck on a stale signature, and so
    upgraded clients always leave with a fresh `Max-Age` window.
    """
    signer = build_signer(settings.session_secret)
    response.set_cookie(
        key=settings.cookie_name or COOKIE_NAME_DEFAULT,
        value=dump_session_id(signer, str(session.id)),
        **cookie_kwargs(settings),
    )


async def _maybe_rehash_password(
    db: AsyncSession, user: User, plaintext: str
) -> None:
    """Rewrite the user's `password_hash` to the current scheme, best-effort.

    Called after a successful `verify_password` that returned `needs_rehash`:
    the stored digest is legacy (bcrypt) or using outdated argon2 parameters,
    so we mint a fresh argon2id hash and persist it. Any error here is
    swallowed -- a failed rehash must never fail the caller's flow (login,
    upgrade-re-auth, ...); we just log and let the next successful verify try
    again.
    """
    try:
        user.password_hash = hash_password(plaintext)
        await db.flush()
    except Exception:  # pragma: no cover - defensive belt
        _log.warning("password_rehash_failed", user_id=str(user.id), exc_info=True)


@router.post("/upgrade", response_model=AccountInfo)
async def upgrade(
    body: UpgradeRequest,
    response: Response,
    user: User = Depends(current_user),
    session: DbSession | None = Depends(current_session),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountInfo:
    """Promote anonymous user to email/password.

    In-place row mutation preserves the FK from `conversation.user_id` (and
    friends) -- the user id is unchanged. Verified by `test_auth_upgrade.py`.

    The session cookie IS re-signed here as a defensive measure: the session
    id is unchanged so the value is usually identical, but re-emitting the
    cookie protects against signature drift across a `SESSION_SECRET` rotation
    and refreshes the `Max-Age` window on a successful upgrade.
    """
    if not user.is_anonymous:
        raise _already_upgraded()

    normalized_email = body.email.strip().lower()

    # Uniqueness check: another user with this email already exists -> 409.
    # SELECT-first catches the common case without touching the DB write path.
    # The partial UNIQUE INDEX from alembic/0004 is the authoritative guard;
    # the IntegrityError catch below races with concurrent upgrades that slip
    # past the SELECT and converts the DB-level violation into EMAIL_TAKEN.
    stmt = select(User).where(User.email == normalized_email, User.id != user.id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise _email_taken()

    # In-place mutation. Keep `name` if it's already custom; otherwise derive
    # from the email's local part. The FE renders `account.name` so a
    # placeholder "Guest" right after upgrade is jarring.
    user.email = normalized_email
    user.is_anonymous = False
    if user.name in ("", "Guest"):
        user.name = normalized_email.split("@", 1)[0]
    if body.password:
        user.password_hash = hash_password(body.password)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _email_taken() from exc
    await db.refresh(user)

    # Re-sign + re-set the cookie after the upgrade succeeded. Documented in
    # the route docstring: defensive against signature drift / key rotation.
    if session is not None:
        _resign_session_cookie(response, settings, session)

    # Synthesize the updated AccountInfo from the post-upgrade row.
    byok_rows = await api_keys.list_for_user(db, user.id)
    has_byok = len(byok_rows) > 0
    masked = byok_rows[0].masked_key if has_byok else None
    return users.to_account_info(
        user, byok_enabled=has_byok, byok_masked_key=masked
    )


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def signout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session: DbSession | None = Depends(current_session),
) -> None:
    """Clear the cookie and revoke the current session row."""
    if session is not None:
        await db.execute(delete(DbSession).where(DbSession.id == session.id))
        await db.commit()
    cookie_name = settings.cookie_name or COOKIE_NAME_DEFAULT
    # Pass the same path/samesite/secure as set so the browser actually clears.
    kw = cookie_kwargs(settings)
    response.delete_cookie(
        key=cookie_name,
        path=kw["path"],
        samesite=kw["samesite"],
        secure=kw["secure"],
        httponly=kw["httponly"],
    )


__all__ = [
    "UpgradeRequest",
    "_maybe_rehash_password",
    "_truncate_for_bcrypt",
    "router",
]
