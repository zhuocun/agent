"""Eager re-encryption sweep for BYOK keys after a KEK rotation.

Lazy re-wrap on read (see `app.db.repositories.api_keys.get_decrypted_for_user`)
only touches rows that are actually read. This script is the eager companion:
it walks every `api_key` row, decrypts it, and re-encrypts under the current
KEK version so an operator can retire an old KEK without orphaning cold rows.

Idempotent: a row already stored under `byok_current_kek_version` is left
untouched, so running twice rewraps nothing the second time.

Usage::

    uv run python -m app.scripts.reencrypt_byok
    uv run python app/scripts/reencrypt_byok.py

Honours the env's `DATABASE_URL` (Neon in prod, SQLite in tests). Reuses the
process-wide engine / session factory from `app.db.session` and the same
crypto helpers as the read path, so re-wrapped rows are byte-compatible with
normal writes. Prints a counts-only summary -- never key material.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.db import models as _models  # noqa: F401 -- register tables with Base.metadata
from app.db.models import ApiKey
from app.db.session import get_engine, get_session_factory
from app.security.crypto import (
    DecryptionError,
    ciphertext_version,
    decrypt,
    encrypt,
)

log = structlog.get_logger(__name__)


@dataclass
class SweepResult:
    """Counts-only summary of a sweep. Never carries key material."""

    scanned: int = 0
    rewrapped: int = 0
    skipped: int = 0
    failed: int = 0


async def reencrypt_all() -> SweepResult:
    """Re-encrypt every `api_key` row under the current KEK version.

    Rows already at `byok_current_kek_version` are skipped (idempotent). A
    row that fails to decrypt or re-encrypt is counted as `failed` and left
    untouched -- the sweep continues rather than aborting the whole batch, so
    one corrupt row doesn't block rotating the rest.
    """
    settings = get_settings()
    current = settings.byok_current_kek_version
    result = SweepResult()

    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (await session.execute(select(ApiKey))).scalars().all()
        for row in rows:
            result.scanned += 1
            try:
                stored_version = ciphertext_version(row.ciphertext)
            except DecryptionError as exc:
                result.failed += 1
                log.warning(
                    "byok.sweep.version_unreadable",
                    api_key_id=str(row.id),
                    exc_info=exc,
                )
                continue

            if stored_version == current:
                result.skipped += 1
                continue

            try:
                plaintext = decrypt(row.ciphertext, settings.byok_encryption_kek)
                row.ciphertext = encrypt(plaintext, settings.byok_encryption_kek)
            except Exception as exc:  # one bad row must not abort the batch
                result.failed += 1
                log.warning(
                    "byok.sweep.rewrap_failed",
                    api_key_id=str(row.id),
                    exc_info=exc,
                )
                continue
            result.rewrapped += 1

        await session.commit()

    return result


async def _run() -> int:
    settings = get_settings()
    try:
        result = await reencrypt_all()
    finally:
        # Best-effort engine teardown so a one-shot invocation doesn't leak the
        # pool. Disposed on the same loop `reencrypt_all` used.
        await get_engine().dispose()
    print(
        "reencrypt_byok: "
        f"current_version={settings.byok_current_kek_version} "
        f"scanned={result.scanned} rewrapped={result.rewrapped} "
        f"skipped={result.skipped} failed={result.failed}",
        file=sys.stderr,
    )
    # A non-zero failed count is a soft signal to the operator (e.g. a lost
    # KEK), so surface it as a non-zero exit without hiding the partial work.
    return 1 if result.failed else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
