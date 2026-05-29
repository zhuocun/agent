"""Password hashing tests (Post-M4 hardening item 7).

Covers the contract `app.security.passwords` exposes:

- argon2id roundtrip: `hash_password` -> `$argon2id$...`, `verify_password`
  reports `ok=True, needs_rehash=False`.
- legacy bcrypt verify: a hand-rolled `$2b$` digest still verifies, with
  `needs_rehash=True` so the caller can opportunistically rewrite it.
- failure modes: empty string and unknown-prefix hashes return
  `(False, False)`; a wrong password against argon2 / bcrypt returns
  `(False, False)` (no rehash on failed login).
- integration via /api/auth/upgrade: an anonymous user with a hand-seeded
  bcrypt `password_hash` whose plaintext we know -- re-upgrading would 400
  (already non-anonymous), so we exercise the rehash path directly through
  `_maybe_rehash_password` and confirm the row is rewritten to argon2id.
- counter-test: a fresh argon2id digest is NOT rewritten by the same helper
  unless `needs_rehash` is asserted by the caller (we never call rehash on
  an up-to-date hash, so the field stays untouched).
"""

from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.routes import _maybe_rehash_password
from app.db.models import User
from app.security.passwords import hash_password, verify_password


def _bcrypt_legacy_digest(plaintext: str) -> str:
    """Mint a bcrypt digest the way the pre-Post-M4 route did.

    Inlined so we don't depend on a now-deleted helper -- we just need a
    realistic legacy row to exercise the bcrypt-fallback verify + rehash path.
    """
    return bcrypt.hashpw(
        plaintext.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)
    ).decode("ascii")


# ---------------------------------------------------------------------------
# Unit-level contract on app.security.passwords
# ---------------------------------------------------------------------------


def test_hash_password_emits_argon2id_prefix() -> None:
    """New digests must be argon2id, never bcrypt -- that's the migration."""
    digest = hash_password("hunter2")
    assert digest.startswith("$argon2id$"), digest


def test_argon2id_roundtrip_no_rehash_needed() -> None:
    """Hash then verify the same plaintext -- ok=True, needs_rehash=False."""
    digest = hash_password("correct horse battery staple")
    ok, needs_rehash = verify_password("correct horse battery staple", digest)
    assert ok is True
    assert needs_rehash is False


def test_argon2id_wrong_password_returns_false_no_rehash() -> None:
    """A mismatched plaintext must NOT signal `needs_rehash` -- caller
    only rewrites on a successful verify."""
    digest = hash_password("the right one")
    ok, needs_rehash = verify_password("the wrong one", digest)
    assert ok is False
    assert needs_rehash is False


def test_bcrypt_legacy_verifies_with_rehash_flag() -> None:
    """A `$2b$` digest verifies and signals `needs_rehash=True` so the
    caller can migrate the row to argon2id on next login."""
    legacy = _bcrypt_legacy_digest("legacy-pw")
    assert legacy.startswith("$2")  # `$2a$` or `$2b$` -- both supported.
    ok, needs_rehash = verify_password("legacy-pw", legacy)
    assert ok is True
    assert needs_rehash is True


def test_bcrypt_wrong_password_returns_false_no_rehash() -> None:
    """Failed bcrypt verify => no migration."""
    legacy = _bcrypt_legacy_digest("legacy-pw")
    ok, needs_rehash = verify_password("not-legacy-pw", legacy)
    assert ok is False
    assert needs_rehash is False


def test_unknown_hash_prefix_is_unverifiable() -> None:
    """Anything not argon2id / bcrypt is treated as unverifiable, never True."""
    ok, needs_rehash = verify_password("x", "plaintext-not-a-hash")
    assert ok is False
    assert needs_rehash is False


def test_empty_hash_is_unverifiable() -> None:
    """Defensive: an empty stored hash never lets a verify succeed."""
    ok, needs_rehash = verify_password("anything", "")
    assert ok is False
    assert needs_rehash is False


# ---------------------------------------------------------------------------
# Integration-ish: _maybe_rehash_password against a DB row
# ---------------------------------------------------------------------------


async def test_login_with_bcrypt_user_rehashes_and_persists(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The opportunistic-rehash path: a bcrypt-hashed user that just logged
    in successfully gets `password_hash` rewritten to argon2id and persisted.

    Mirrors what a future `POST /api/auth/login` handler would do after
    `verify_password` returns `(ok=True, needs_rehash=True)`.
    """
    async with session_factory() as session:
        user = User(
            is_anonymous=False,
            name="legacy",
            email="legacy@example.com",
            password_hash=_bcrypt_legacy_digest("legacy-pw"),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
        before = user.password_hash
        assert before.startswith("$2")

        # Simulate a successful login flow: verify_password returned
        # (ok=True, needs_rehash=True), caller invokes the rehash helper.
        ok, needs_rehash = verify_password("legacy-pw", before)
        assert (ok, needs_rehash) == (True, True)
        await _maybe_rehash_password(session, user, "legacy-pw")
        await session.commit()

    # Re-read from a fresh session: the bcrypt digest is gone, replaced
    # with an argon2id one that verifies the same plaintext.
    async with session_factory() as session:
        after = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        assert after.password_hash is not None
        assert after.password_hash != before
        assert after.password_hash.startswith("$argon2id$")
        ok_after, needs_rehash_after = verify_password(
            "legacy-pw", after.password_hash
        )
        assert ok_after is True
        assert needs_rehash_after is False


async def test_login_with_argon2id_user_does_not_rewrite_hash(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The opposite path: an argon2id-hashed user whose verify reports
    `needs_rehash=False` keeps the same digest -- the caller never invokes
    rehash on an up-to-date hash.
    """
    async with session_factory() as session:
        original_hash = hash_password("up-to-date-pw")
        user = User(
            is_anonymous=False,
            name="modern",
            email="modern@example.com",
            password_hash=original_hash,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

        ok, needs_rehash = verify_password("up-to-date-pw", original_hash)
        assert ok is True
        assert needs_rehash is False
        # The caller skips _maybe_rehash_password when needs_rehash is False,
        # so the row is untouched in this branch.

    async with session_factory() as session:
        after = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        # Same digest persists -- no opportunistic rewrite for fresh hashes.
        assert after.password_hash == original_hash
