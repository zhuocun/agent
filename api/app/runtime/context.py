"""Immutable per-turn runtime context (AC-04).

One `RuntimeContext` is derived from the request `AsyncSession` at turn entry and
carried through every piece of lifecycle work that needs its OWN session:
stream heartbeats, budget-reservation release, fresh-session stop/error
persistence, the detached producer, and the detached post-turn tasks (title
autogen, memory extraction).

Why this exists: those call sites used to reach for the process-wide
`get_session_factory()`. Under test that factory is bound to the env
`DATABASE_URL`, NOT the per-test database the request session is bound to, so
heartbeats and reservation releases silently wrote to (or failed against) the
wrong database while the test still went green. Deriving the factory from the
request session's bind makes the lifecycle observable in the same database the
turn is being asserted against, in prod and in tests alike.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_session_factory


def derive_session_factory(
    db: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    """Build a sessionmaker pointing at the same engine as `db`.

    Background work needs a fresh session because the request scope is closing.
    `get_session_factory()` is the wrong source: in tests it is the process-wide
    factory bound to env `DATABASE_URL` rather than the per-test database this
    session is bound to.

    Falls back to `get_session_factory()` if the bind can't be extracted
    (defensive — should not happen in practice; `AsyncSession.bind` is an
    `AsyncEngine` for any session built by a bound sessionmaker, and unbound
    sessions do not carry the attribute at all).
    """
    bind = getattr(db, "bind", None)
    if bind is None:
        return get_session_factory()
    return async_sessionmaker(
        bind=bind,
        expire_on_commit=False,
        autoflush=False,
    )


@dataclass(frozen=True)
class RuntimeContext:
    """Frozen database context for one turn's lifecycle work.

    `session_factory` is the ONLY authorized source of sessions for lifecycle
    and background work started by that turn. It is frozen so no branch can
    swap the database mid-turn.
    """

    session_factory: async_sessionmaker[AsyncSession]

    @classmethod
    def from_session(cls, db: AsyncSession) -> RuntimeContext:
        """Derive the context from the request-scoped session's bind."""
        return cls(session_factory=derive_session_factory(db))

    @classmethod
    def from_factory(
        cls, session_factory: async_sessionmaker[AsyncSession]
    ) -> RuntimeContext:
        """Adopt an already-derived factory (detached producer entry point)."""
        return cls(session_factory=session_factory)
