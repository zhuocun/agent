"""Auth routes.

- `POST /api/auth/upgrade` (M3) -- promote an anonymous user to email/password.
  Mutates the CURRENT user row in place (`is_anonymous=False`, sets `email`,
  optionally hashes `password`). The row id is unchanged, so every FK from
  `conversation.user_id` / `api_key.user_id` / `preferences.user_id` continues
  to point at the same user without any data migration. This is the whole
  reason the anonymous-first seam is shaped this way (plan §"Auth seam").

- `POST /api/auth/login` -- authenticate against an existing registered user.
  Unlike upgrade (which merges the current anonymous identity in place), login
  is a HANDOFF: the current session is repointed at the target user and the
  previous anonymous user + its guest scratch are discarded. Failures are a
  single uniform 401 that never reveals whether the email exists.

- `POST /api/auth/signout` -- clears the cookie and revokes the session row.

Passkey / magic-link / email-verification ceremonies are deferred. The MVP
contract is just "give me an email, I'll optionally take a password, I'll
return the upgraded AccountInfo."

Password hashing is delegated to `app.security.passwords`: new digests are
argon2id, legacy bcrypt rows are verified and opportunistically rewritten on
their first successful login. Bcrypt remains a runtime dep for that fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
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
from app.middleware.ratelimit import limiter
from app.schemas.account import AccountInfo
from app.schemas.common import CamelModel
from app.security.passwords import (
    _truncate_for_bcrypt as _truncate_for_bcrypt_impl,
)
from app.security.passwords import (
    hash_password,
    verify_password,
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


class LoginRequest(CamelModel):
    """Body for POST /api/auth/login.

    Both fields are required: login authenticates against an existing
    registered user, so unlike upgrade there is no passwordless variant here.
    `EmailStr` enforces basic validity; everything else (no such user, wrong
    password, password-less account) collapses into a single uniform 401 in
    the route -- we never reveal whether the email exists.
    """

    email: EmailStr
    password: str


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


def _invalid_credentials() -> AppError:
    """Single uniform 401 for every login failure mode.

    Returned identically whether the email is unknown, the account has no
    password set, or the password is wrong -- the title/body must not let a
    caller distinguish "no such account" from "wrong password" (no account
    enumeration). The matching dummy-verify in the route closes the timing
    side-channel for the unknown-email branch.
    """
    return AppError(
        ErrorEnvelope(
            code="INVALID_CREDENTIALS",
            severity="error",
            title="Sign-in failed",
            body="Incorrect email or password.",
        ),
        status.HTTP_401_UNAUTHORIZED,
    )


def _set_session_cookie(
    response: Response,
    settings: Settings,
    session_id: str,
) -> None:
    """Emit `Set-Cookie sid=...` for `session_id` with the standard flags.

    The lowest-level cookie writer shared by the re-sign path (existing
    session id, used by upgrade/login when reusing the session) and the
    fresh-session path (a new session id minted during login when the caller
    arrived without a usable cookie). Mirrors `dependency._create_anonymous`'s
    cookie emission so every issuance uses the same signer + flags.
    """
    signer = build_signer(settings.session_secret)
    response.set_cookie(
        key=settings.cookie_name or COOKIE_NAME_DEFAULT,
        value=dump_session_id(signer, session_id),
        **cookie_kwargs(settings),
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
    _set_session_cookie(response, settings, str(session.id))


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
@limiter.limit(lambda: get_settings().rate_limit_upgrade)
async def upgrade(
    body: UpgradeRequest,
    request: Request,
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


# A throwaway argon2id digest used purely to spend a verify cycle when the
# target user is missing, so the unknown-email branch costs roughly the same
# wall-clock time as a wrong-password branch (timing-enumeration mitigation).
# Best-effort: minted once at import; the plaintext it hashes is irrelevant.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


@router.post("/login", response_model=AccountInfo)
@limiter.limit(lambda: get_settings().rate_limit_login)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    session: DbSession | None = Depends(current_session),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountInfo:
    """Authenticate against an existing registered user (session handoff).

    Unlike `upgrade` (in-place merge of the current anonymous identity), login
    is a HANDOFF: the current session is repointed at the target user and the
    previous anonymous user + its guest scratch are discarded. Any guest data
    the caller created in this session is intentionally NOT migrated -- it is
    upgrade's job to keep guest work, login switches to an existing account.

    Failures are a single uniform 401 (`INVALID_CREDENTIALS`) that never lets
    a caller distinguish "no such email" from "wrong password" / "no password
    set" -- the message is identical across all three, and a dummy verify is
    run when the user is missing to flatten the timing side-channel.
    """
    normalized_email = body.email.strip().lower()

    stmt = select(User).where(
        User.email == normalized_email, User.is_anonymous == False  # noqa: E712
    )
    target = (await db.execute(stmt)).scalar_one_or_none()

    if target is None or target.password_hash is None:
        # Spend a verify cycle so the unknown-email / no-password branches cost
        # roughly the same as a real verify (timing-enumeration mitigation),
        # then fail uniformly.
        verify_password(body.password, _DUMMY_PASSWORD_HASH)
        raise _invalid_credentials()

    ok, needs_rehash = verify_password(body.password, target.password_hash)
    if not ok:
        raise _invalid_credentials()

    if needs_rehash:
        await _maybe_rehash_password(db, target, body.password)

    # Session handoff. Repoint the current session at the target FIRST so the
    # subsequent anon-cleanup delete does not take the session row with it (the
    # repointed row is now FK'd to `target`, not to the previous anon user).
    prev = user
    if prev.id != target.id:
        if session is not None:
            session.user_id = target.id
            await db.flush()
            _resign_session_cookie(response, settings, session)
        else:
            # No usable session arrived with the request (e.g. cookie cleared
            # mid-flight). Mint a fresh session for the target, mirroring how
            # `dependency._create_anonymous` builds one, and point the cookie
            # at it.
            expires_at = datetime.now(UTC) + timedelta(
                seconds=settings.session_max_age_seconds
            )
            new_session = DbSession(user_id=target.id, expires_at=expires_at)
            db.add(new_session)
            await db.flush()
            _set_session_cookie(response, settings, str(new_session.id))

        # Discard the guest identity we are switching away FROM. Only anon
        # scratch is reclaimed -- an account switch (prev is a real account)
        # must leave the other account's rows intact.
        if prev.is_anonymous:
            await users.delete_user_and_data(db, user_id=prev.id)
    elif session is not None:
        # Already this user (re-login). Refresh the cookie window defensively.
        _resign_session_cookie(response, settings, session)

    # Login mutates/deletes rows; commit explicitly (mirrors `signout`) rather
    # than relying solely on the request dependency's end-of-request commit.
    await db.commit()

    byok_rows = await api_keys.list_for_user(db, target.id)
    has_byok = len(byok_rows) > 0
    masked = byok_rows[0].masked_key if has_byok else None
    return users.to_account_info(
        target, byok_enabled=has_byok, byok_masked_key=masked
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
    "LoginRequest",
    "UpgradeRequest",
    "_maybe_rehash_password",
    "_truncate_for_bcrypt",
    "router",
]
