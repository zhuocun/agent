"""`current_user` dependency.

Reads the signed cookie, looks up the session row; if missing or expired,
creates a new anonymous user + session and sets the cookie on the response.

The session is committed BEFORE we set the cookie so the row exists by the
time the cookie hits the browser. We share the request's transactional
session for the user lookup, then commit explicitly when we create a new
user/session pair (the outer `get_db` dependency also commits, but we want
the cookie to point at a row that's already durable). The outer commit is a
deliberate idempotent no-op once `_create_anonymous` has flushed everything:
with `expire_on_commit=False` and an empty TX, the second commit() is free.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import (
    COOKIE_NAME_DEFAULT,
    build_signer,
    cookie_kwargs,
    dump_session_id,
    load_session_id,
)
from app.config import Settings, get_settings
from app.db.models import Session as DbSession
from app.db.models import User
from app.db.session import get_db


def _now_utc() -> datetime:
    return datetime.now(UTC)


async def _try_load_existing_user(
    db: AsyncSession,
    settings: Settings,
    raw_cookie: str,
) -> User | None:
    signer = build_signer(settings.session_secret)
    session_id_str = load_session_id(signer, raw_cookie)
    if not session_id_str:
        return None
    try:
        session_uuid = UUID(session_id_str)
    except ValueError:
        return None
    db_session = await db.get(DbSession, session_uuid)
    if db_session is None:
        return None
    # Normalize naive timestamps coming back from SQLite (no TZ) for compare.
    # We assume naive timestamps are UTC: every write path uses _now_utc() or a
    # server_default that we expect to render in UTC on Postgres.
    expires_at = db_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= _now_utc():
        return None
    return await db.get(User, db_session.user_id)


async def _create_anonymous(
    db: AsyncSession, settings: Settings, response: Response
) -> User:
    user = User(is_anonymous=True, name="Guest", plan_label="Free")
    db.add(user)
    await db.flush()
    expires_at = _now_utc() + timedelta(seconds=settings.session_max_age_seconds)
    db_session = DbSession(user_id=user.id, expires_at=expires_at)
    db.add(db_session)
    # Commit so the cookie always points at a row that exists.
    await db.commit()
    # The outer get_db dependency will commit() once more at request end; with
    # expire_on_commit=False and no pending changes, that call is a no-op.
    await db.refresh(db_session)
    await db.refresh(user)
    signer = build_signer(settings.session_secret)
    response.set_cookie(
        key=settings.cookie_name or COOKIE_NAME_DEFAULT,
        value=dump_session_id(signer, str(db_session.id)),
        **cookie_kwargs(settings),
    )
    return user


async def current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Return the current user, creating an anonymous one on first hit."""
    cookie_name = settings.cookie_name or COOKIE_NAME_DEFAULT
    raw = request.cookies.get(cookie_name)
    if raw:
        existing = await _try_load_existing_user(db, settings, raw)
        if existing is not None:
            return existing
    return await _create_anonymous(db, settings, response)


async def current_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DbSession | None:
    """Return the current DB session row if the cookie is valid."""
    cookie_name = settings.cookie_name or COOKIE_NAME_DEFAULT
    raw = request.cookies.get(cookie_name)
    if not raw:
        return None
    signer = build_signer(settings.session_secret)
    session_id_str = load_session_id(signer, raw)
    if not session_id_str:
        return None
    try:
        session_uuid = UUID(session_id_str)
    except ValueError:
        return None
    stmt = select(DbSession).where(DbSession.id == session_uuid)
    return (await db.execute(stmt)).scalar_one_or_none()
