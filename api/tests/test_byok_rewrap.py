"""BYOK KEK-rotation re-encryption tests.

Two seams:

* **Lazy re-wrap on read** -- `api_keys.get_decrypted_for_user` re-encrypts a
  row stored under a stale KEK version on the read path, best-effort, without
  ever breaking the read if the re-wrap fails.
* **Eager sweep** -- `app.scripts.reencrypt_byok` walks every row and rewraps
  stale ones, idempotently.

Tests build their own registry via env + `get_settings.cache_clear()` (matching
`tests/security/test_kek_rotation.py`) so the legacy KEK and a registered v1
KEK coexist, then store a v0 (legacy) row and assert it migrates to v1.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import ApiKey, User
from app.db.repositories import api_keys as api_keys_repo
from app.security.crypto import (
    VersionedCipher,
    ciphertext_version,
    get_cipher,
)

pytestmark = pytest.mark.asyncio


def _make_kek_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


@pytest.fixture
def rotated_kek_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Configure settings so current KEK version is 1, with a legacy KEK too.

    Yields the legacy KEK base64 so a test can hand-build a v0 (legacy) row
    that should migrate to v1 on read / sweep. Clears the settings cache on
    entry and exit so the rest of the suite sees conftest defaults again.
    """
    legacy_kek = _make_kek_b64()
    v1_kek = _make_kek_b64()
    monkeypatch.setenv("BYOK_ENCRYPTION_KEK", legacy_kek)
    monkeypatch.setenv("BYOK_KEK_VERSIONS", f"1:{v1_kek}")
    monkeypatch.setenv("BYOK_CURRENT_KEK_VERSION", "1")
    get_settings.cache_clear()
    try:
        yield legacy_kek
    finally:
        get_settings.cache_clear()


async def _seed_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid4().hex}@example.com", is_anonymous=False)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _legacy_ciphertext(legacy_kek: str, plaintext: str) -> str:
    """Build a v0 (magic-absent) ciphertext for `plaintext`."""
    legacy = VersionedCipher(
        legacy=get_cipher(legacy_kek), registry={}, current_version=0
    )
    blob = legacy.encrypt(plaintext)
    assert ciphertext_version(blob) == 0
    return blob


async def test_read_rewraps_legacy_row_to_current_version(
    session_factory: async_sessionmaker[AsyncSession],
    rotated_kek_env: str,
) -> None:
    """A legacy (v0) row migrates to the current version on successful read."""
    plaintext = "sk-ant-rotate-me-12345"
    async with session_factory() as session:
        user = await _seed_user(session)
        row = ApiKey(
            user_id=user.id,
            provider="anthropic",
            ciphertext=_legacy_ciphertext(rotated_kek_env, plaintext),
            masked_key="sk-...2345",
        )
        session.add(row)
        await session.commit()
        user_id = user.id
        row_id = row.id

    async with session_factory() as session:
        decrypted = await api_keys_repo.get_decrypted_for_user(
            session, user_id=user_id, provider="anthropic"
        )
    assert decrypted == plaintext

    # Row's stored ciphertext is now under the current version AND decryptable.
    async with session_factory() as session:
        row = (
            await session.execute(select(ApiKey).where(ApiKey.id == row_id))
        ).scalar_one()
        assert ciphertext_version(row.ciphertext) == 1
        # masked_key is unchanged by the re-wrap.
        assert row.masked_key == "sk-...2345"
        again = await api_keys_repo.get_decrypted_for_user(
            session, user_id=user_id, provider="anthropic"
        )
    assert again == plaintext


async def test_read_is_idempotent_for_current_version_row(
    session_factory: async_sessionmaker[AsyncSession],
    rotated_kek_env: str,
) -> None:
    """A row already at the current version is not re-wrapped (ciphertext stable)."""
    plaintext = "sk-current-version-row"
    async with session_factory() as session:
        user = await _seed_user(session)
        # upsert encrypts via the write path -> current version (1).
        row = await api_keys_repo.upsert(
            session, user_id=user.id, provider="anthropic", raw_api_key=plaintext
        )
        await session.commit()
        user_id = user.id
        before = row.ciphertext
        assert ciphertext_version(before) == 1

    async with session_factory() as session:
        decrypted = await api_keys_repo.get_decrypted_for_user(
            session, user_id=user_id, provider="anthropic"
        )
    assert decrypted == plaintext

    async with session_factory() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        # Same ciphertext bytes -- no needless re-wrap (would change the nonce).
        assert row.ciphertext == before


async def test_read_rewrap_failure_is_swallowed(
    session_factory: async_sessionmaker[AsyncSession],
    rotated_kek_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A re-wrap failure never breaks the read: plaintext returned, row unchanged."""
    plaintext = "sk-rewrap-will-fail"
    async with session_factory() as session:
        user = await _seed_user(session)
        legacy_ct = _legacy_ciphertext(rotated_kek_env, plaintext)
        row = ApiKey(
            user_id=user.id,
            provider="anthropic",
            ciphertext=legacy_ct,
            masked_key="sk-...fail",
        )
        session.add(row)
        await session.commit()
        user_id = user.id
        row_id = row.id

    # Force the re-wrap encrypt to blow up.
    def _boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("forced re-wrap failure")

    monkeypatch.setattr(api_keys_repo, "encrypt", _boom)

    async with session_factory() as session:
        decrypted = await api_keys_repo.get_decrypted_for_user(
            session, user_id=user_id, provider="anthropic"
        )
    assert decrypted == plaintext  # read still succeeds

    # Row's ciphertext is untouched -- still the original legacy blob (v0).
    async with session_factory() as session:
        row = (
            await session.execute(select(ApiKey).where(ApiKey.id == row_id))
        ).scalar_one()
        assert row.ciphertext == legacy_ct
        assert ciphertext_version(row.ciphertext) == 0


@pytest.fixture
async def sweep_db(
    sqlite_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Point the global engine/session factory at a per-test sqlite file.

    The sweep script reaches the DB via `app.db.session.get_session_factory`,
    not the test's `session_factory` fixture, so we rebind `DATABASE_URL` and
    clear the lru caches. Schema is created via `Base.metadata.create_all`.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.base import Base
    from app.db.session import get_engine, get_session_factory

    url = f"sqlite+aiosqlite:///{sqlite_db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    eng = create_async_engine(url, connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, autoflush=False)
    try:
        yield factory
    finally:
        await eng.dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        get_settings.cache_clear()


async def test_sweep_rewraps_legacy_rows_and_is_idempotent(
    sweep_db: async_sessionmaker[AsyncSession],
    rotated_kek_env: str,
) -> None:
    """The eager sweep migrates stale rows and rewraps nothing on a second run."""
    from app.scripts.reencrypt_byok import reencrypt_all

    async with sweep_db() as session:
        user = await _seed_user(session)
        # Two legacy rows + one already-current row.
        session.add(
            ApiKey(
                user_id=user.id,
                provider="anthropic",
                ciphertext=_legacy_ciphertext(rotated_kek_env, "sk-legacy-one"),
                masked_key="sk-...one1",
            )
        )
        session.add(
            ApiKey(
                user_id=user.id,
                provider="deepseek",
                ciphertext=_legacy_ciphertext(rotated_kek_env, "sk-legacy-two"),
                masked_key="sk-...two2",
            )
        )
        await api_keys_repo.upsert(
            session, user_id=user.id, provider="openai", raw_api_key="sk-current-row"
        )
        await session.commit()

    first = await reencrypt_all()
    assert first.scanned == 3
    assert first.rewrapped == 2
    assert first.skipped == 1
    assert first.failed == 0

    # All rows now under current version and still decryptable.
    async with sweep_db() as session:
        rows = (await session.execute(select(ApiKey))).scalars().all()
        assert all(ciphertext_version(r.ciphertext) == 1 for r in rows)

    # Second run is a no-op.
    second = await reencrypt_all()
    assert second.scanned == 3
    assert second.rewrapped == 0
    assert second.skipped == 3
    assert second.failed == 0
