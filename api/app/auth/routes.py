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
return the upgraded AccountInfo." Cookie does not need to be re-signed -- the
session cookie holds a session id, NOT user identity, and the session row
already references the same user id we just mutated.
"""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, Response, status
from pydantic import EmailStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import COOKIE_NAME_DEFAULT, cookie_kwargs
from app.auth.dependency import current_session, current_user
from app.config import Settings, get_settings
from app.db.models import Session as DbSession
from app.db.models import User
from app.db.repositories import api_keys, users
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope
from app.schemas.account import AccountInfo
from app.schemas.common import CamelModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


# bcrypt has a hard 72-byte input limit; we cap the input on a UTF-8 character
# boundary so longer passwords don't surface as a 500 from the underlying
# library. Documented behavior.
_BCRYPT_MAX_BYTES = 72


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


def _truncate_for_bcrypt(password: str) -> bytes:
    """Encode `password` to at most 72 UTF-8 bytes on a character boundary.

    bcrypt only honors the first 72 bytes of its input, so we cap there. We
    slice the UTF-8 *bytes* (not codepoints) and then drop any trailing partial
    codepoint left by the cut, so a multi-byte UTF-8 sequence is never split.
    Any input beyond 72 bytes is ignored (by both this cap and bcrypt itself).
    """
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    # Round down to the last complete codepoint: decoding with "ignore" drops a
    # dangling partial sequence, and re-encoding gives clean <=72-byte bytes.
    return truncated.decode("utf-8", "ignore").encode("utf-8")


def _hash_password(password: str) -> str:
    """Return a bcrypt digest of `password`.

    The input is truncated to at most 72 UTF-8 bytes without splitting a
    multi-byte character (see `_truncate_for_bcrypt`); bytes beyond 72 are
    ignored by bcrypt regardless. The cost factor is pinned explicitly so it
    does not drift with the bcrypt library's default rounds.
    """
    truncated = _truncate_for_bcrypt(password)
    digest = bcrypt.hashpw(truncated, bcrypt.gensalt(rounds=12))
    return digest.decode("ascii")


@router.post("/upgrade", response_model=AccountInfo)
async def upgrade(
    body: UpgradeRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountInfo:
    """Promote anonymous user to email/password.

    In-place row mutation preserves the FK from `conversation.user_id` (and
    friends) -- the user id is unchanged. Verified by `test_auth_upgrade.py`.

    The session cookie is NOT re-signed here: the cookie holds a session id,
    not the user id, and the session row already references the user we
    just upgraded. No cookie work needed.
    """
    if not user.is_anonymous:
        raise _already_upgraded()

    normalized_email = body.email.strip().lower()

    # Uniqueness check: another user with this email already exists -> 409.
    # MVP: SELECT-then-mutate; two concurrent upgrades could both succeed with the
    # same email. TODO(post-m4): add a partial UNIQUE INDEX on users.email WHERE
    # email IS NOT NULL, plus retry on IntegrityError -> EMAIL_TAKEN.
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
        user.password_hash = _hash_password(body.password)

    await db.flush()
    await db.refresh(user)

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
