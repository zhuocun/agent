"""api_key repository.

Owns the AES-GCM encryption boundary: callers never see plaintext at rest.
`upsert(...)` encrypts the raw key, `get_decrypted_for_user(...)` decrypts on
the read path for per-request resolution. Decryption failures are surfaced as
`None` from `get_decrypted_for_user` so the streaming handler can fall back to
the platform key rather than failing the user's turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import ApiKey
from app.security.crypto import (
    DecryptionError,
    ciphertext_version,
    decrypt,
    encrypt,
)

log = structlog.get_logger(__name__)


def _mask_key(raw_api_key: str) -> str:
    """Render the user-visible mask for `raw_api_key`.

    "sk-"-prefixed Anthropic-style keys get `"sk-...XXXX"`; everything else
    falls back to a generic `"...XXXX"`. Always uses the last 4 chars after
    trimming; for keys shorter than 4 chars (rejected at the route layer
    anyway) we degrade to `"..."` to avoid leaking the whole secret.
    """
    trimmed = raw_api_key.strip()
    if len(trimmed) < 4:
        return "..."
    tail = trimmed[-4:]
    if trimmed.startswith("sk-"):
        return f"sk-...{tail}"
    return f"...{tail}"


async def upsert(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: str,
    raw_api_key: str,
) -> ApiKey:
    """Encrypt and persist a BYOK key. Returns the row.

    Cross-dialect upsert via select-then-insert-or-update (matches the votes /
    preferences repositories). The encryption KEK is read from settings; a
    misconfigured KEK fails at boot, not here.
    """
    settings = get_settings()
    ciphertext = encrypt(raw_api_key, settings.byok_encryption_kek)
    masked = _mask_key(raw_api_key)

    stmt = select(ApiKey).where(
        ApiKey.user_id == user_id,
        ApiKey.provider == provider,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = ApiKey(
            user_id=user_id,
            provider=provider,
            ciphertext=ciphertext,
            masked_key=masked,
        )
        db.add(row)
    else:
        row.ciphertext = ciphertext
        row.masked_key = masked
    await db.flush()
    await db.refresh(row)
    return row


async def delete(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: str,
) -> bool:
    """Delete the BYOK row for `(user_id, provider)`. Returns True if removed.

    Idempotent at the call-site: returning False for a missing row lets the
    route layer treat it as a no-op rather than a 404.
    """
    stmt = select(ApiKey).where(
        ApiKey.user_id == user_id,
        ApiKey.provider == provider,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def get_decrypted_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: str,
) -> str | None:
    """Return the plaintext key for `(user_id, provider)`, or None.

    None on either "no row" or "decrypt failed". The caller treats both the
    same way -- fall back to platform defaults. Decrypt failures are logged at
    WARN with no key material (the ciphertext is logged via its row id only).
    """
    settings = get_settings()
    stmt = select(ApiKey).where(
        ApiKey.user_id == user_id,
        ApiKey.provider == provider,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    try:
        plaintext = decrypt(row.ciphertext, settings.byok_encryption_kek)
    except DecryptionError as exc:
        log.warning(
            "byok.decrypt_failed",
            api_key_id=str(row.id),
            provider=provider,
            exc_info=exc,
        )
        return None

    # Lazy re-wrap: if the stored ciphertext was written under a stale KEK
    # version, re-encrypt under the current one so retiring an old KEK never
    # orphans this row. Done in an INDEPENDENT short-lived session (see
    # `_rewrap_ciphertext`) so it can never commit or roll back the caller's
    # request transaction, and so a re-wrap failure can never break the read
    # path (the plaintext we already hold is valid regardless).
    if ciphertext_version(row.ciphertext) != settings.byok_current_kek_version:
        await _rewrap_ciphertext(
            db, api_key_id=row.id, provider=provider, plaintext=plaintext
        )

    return plaintext


async def _rewrap_ciphertext(
    db: AsyncSession,
    *,
    api_key_id: UUID,
    provider: str,
    plaintext: str,
) -> None:
    """Re-encrypt one BYOK row under the current KEK version, best-effort.

    Runs in its own session bound to the SAME engine as `db` (mirrors the
    streaming handler's `_derive_session_factory` so it works against the
    per-test SQLite bind too), which fully decouples the re-wrap's commit from
    the caller's request transaction -- the read path and any other pending
    writes in `db` are never touched by a re-wrap commit/rollback. Any failure
    is swallowed and logged with the row id only (never key material); the next
    read simply retries. Re-checks the version under the isolated session so a
    concurrent re-wrap by another worker is a no-op (idempotent).
    """
    bind = db.bind
    if bind is None:  # pragma: no cover - session has executed by here
        # Can't derive an isolated session; skip rather than touch the
        # caller's transaction. The next read retries the re-wrap.
        return
    factory = async_sessionmaker(
        bind=bind, expire_on_commit=False, autoflush=False
    )
    settings = get_settings()
    try:
        async with factory() as rewrap_db:
            row = await rewrap_db.get(ApiKey, api_key_id)
            if row is None:
                return
            if ciphertext_version(row.ciphertext) == settings.byok_current_kek_version:
                return  # already re-wrapped (e.g. by a concurrent reader)
            row.ciphertext = encrypt(plaintext, settings.byok_encryption_kek)
            await rewrap_db.commit()
    except Exception as exc:  # read path must survive any re-wrap error
        log.warning(
            "byok.rewrap_failed",
            api_key_id=str(api_key_id),
            provider=provider,
            exc_info=exc,
        )


async def get_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: str,
) -> ApiKey | None:
    """Return the BYOK row for `(user_id, provider)`, or None."""
    stmt = select(ApiKey).where(
        ApiKey.user_id == user_id,
        ApiKey.provider == provider,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[ApiKey]:
    """Return all BYOK rows owned by `user_id`. Order: insertion (`created_at`)."""
    stmt = (
        select(ApiKey)
        .where(ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.asc(), ApiKey.id.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
