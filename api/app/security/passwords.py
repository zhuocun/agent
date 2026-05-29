"""Password hashing for /api/auth/upgrade and friends.

argon2id is the primary scheme (`hash_password` always produces an argon2id
digest). bcrypt is retained as a verify-only fallback so users whose
`password_hash` predates the argon2 migration keep being able to sign in;
their hash is rewritten to argon2id opportunistically on first successful
login (the caller checks the `needs_rehash` flag returned by `verify_password`).

Bcrypt's 72-byte input cap is honored by truncating on a UTF-8 character
boundary -- the same contract as the original `_hash_password` had, so legacy
digests continue to verify against the truncated input. argon2id has no such
cap; the raw UTF-8 bytes are hashed as-is.

Argon2 parameters use `argon2-cffi`'s library defaults at the time of writing
(memory_cost=64 MiB, time_cost=3, parallelism=4). Pinning them here means
`check_needs_rehash` will signal a rewrite if those defaults drift later.
"""

from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

# argon2-cffi library defaults at time of writing (m=64 MiB, t=3, p=4). Pinned
# explicitly so `check_needs_rehash` flags upgrades if upstream defaults move.
_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536  # KiB == 64 MiB
_ARGON2_PARALLELISM = 4

_PH = PasswordHasher(
    time_cost=_ARGON2_TIME_COST,
    memory_cost=_ARGON2_MEMORY_COST,
    parallelism=_ARGON2_PARALLELISM,
)

# bcrypt only honors the first 72 bytes; cap on a UTF-8 char boundary so a
# multi-byte sequence is never split (matches the pre-argon2 contract).
_BCRYPT_MAX_BYTES = 72


def _truncate_for_bcrypt(password: str) -> bytes:
    """Encode `password` to at most 72 UTF-8 bytes on a character boundary.

    Slices the UTF-8 bytes and drops any trailing partial codepoint left by
    the cut, so a multi-byte UTF-8 sequence is never split. Bytes beyond 72
    are ignored (by both this cap and bcrypt itself). Kept private here; the
    legacy `_truncate_for_bcrypt` in `app.auth.routes` re-exports it for the
    existing test suite.
    """
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return truncated.decode("utf-8", "ignore").encode("utf-8")


def hash_password(plaintext: str) -> str:
    """Return an argon2id digest of `plaintext`.

    Always argon2id -- bcrypt is never minted by this function. Legacy bcrypt
    rows are upgraded on verify (see `verify_password`'s `needs_rehash` flag).
    """
    return _PH.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> tuple[bool, bool]:
    """Verify `plaintext` against `hashed`.

    Returns `(ok, needs_rehash)`:
    - `ok` is True iff the plaintext matches the stored digest.
    - `needs_rehash` is True iff a successful match should be re-hashed and
      persisted to advance the user off a legacy / weaker scheme. Always False
      when `ok` is False -- callers don't rehash on a failed login.

    Branches:
    - argon2id digest: delegated to `PasswordHasher.verify`; `needs_rehash`
      reflects `check_needs_rehash` (e.g. parameter drift after a tuning bump).
    - bcrypt digest (`$2a$` / `$2b$` / `$2y$`): verified with `bcrypt.checkpw`
      against the 72-byte UTF-8-safe truncation; `needs_rehash` is always True
      on success so the caller migrates the row to argon2id.
    - Anything else (unknown prefix, malformed): `(False, False)` -- treat as
      an unverifiable hash, surface as a failed login, no rehash.
    """
    if not hashed:
        return (False, False)

    if hashed.startswith("$argon2"):
        try:
            _PH.verify(hashed, plaintext)
        except (argon2_exceptions.VerifyMismatchError, argon2_exceptions.InvalidHash):
            return (False, False)
        except argon2_exceptions.VerificationError:
            return (False, False)
        return (True, _PH.check_needs_rehash(hashed))

    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            ok = bcrypt.checkpw(
                _truncate_for_bcrypt(plaintext), hashed.encode("ascii")
            )
        except (ValueError, UnicodeEncodeError):
            return (False, False)
        # Legacy bcrypt -> always flag for migration to argon2id on success.
        return (ok, ok)

    return (False, False)
