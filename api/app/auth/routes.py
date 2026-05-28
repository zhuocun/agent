"""Auth route stubs.

M0 only needs the routes mounted:
- `POST /api/auth/upgrade` returns 501 NotImplemented (M3 ships the real flow).
- `POST /api/auth/signout` clears the cookie and revokes the session row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import COOKIE_NAME_DEFAULT, cookie_kwargs
from app.auth.dependency import current_session
from app.config import Settings, get_settings
from app.db.models import Session as DbSession
from app.db.session import get_db
from app.errors import not_implemented

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/upgrade")
async def upgrade() -> None:
    """Promote anonymous user to email/passkey. Stubbed until M3."""
    raise not_implemented("Auth upgrade")


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
