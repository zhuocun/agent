"""POST /api/auth/upgrade tests (M3).

Covers:
- Upgrade anonymous -> returns updated AccountInfo with email + derived name.
- Re-upgrade (already non-anonymous) -> 400 ALREADY_UPGRADED.
- Duplicate email across two anon users -> 409 EMAIL_TAKEN.
- Upgrade preserves conversation FK (the row id is unchanged, the FK still
  points at it). This is the verification spike from the plan.
- Missing email -> 400 from Pydantic.
- Optional password is hashed via argon2id (Post-M4 hardening) and not
  stored plaintext.
- argon2id has no input length cap, so a >72-byte password verifies
  losslessly (the bcrypt-era truncation contract no longer applies).
- After a successful upgrade, the response carries a fresh `Set-Cookie sid=`
  header (defensive cookie re-sign, Post-M4 hardening item 9).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, User
from app.security.passwords import verify_password

pytestmark = pytest.mark.asyncio


async def _current_user(session_factory: async_sessionmaker[AsyncSession]) -> User:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one()


async def test_upgrade_anonymous_returns_updated_account_info(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "alice@example.com", "password": "supersecret"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "alice@example.com"
    # Name derived from local part since the anon row had "Guest".
    assert body["name"] == "alice"
    assert body["planLabel"] == "Free"
    assert body["byokEnabled"] is False

    # DB state: is_anonymous flipped, password_hash set, same id.
    row = await _current_user(session_factory)
    assert row.email == "alice@example.com"
    assert row.is_anonymous is False
    assert row.password_hash is not None
    # Post-M4 hardening: new digests are argon2id, not bcrypt.
    assert row.password_hash.startswith("$argon2id$")
    ok, needs_rehash = verify_password("supersecret", row.password_hash)
    assert ok is True
    assert needs_rehash is False  # fresh hash, current params -> no rehash


async def test_upgrade_normalizes_email_casing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "  Mixed@Example.COM  "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "mixed@example.com"
    row = await _current_user(session_factory)
    assert row.email == "mixed@example.com"


async def test_re_upgrade_returns_400_already_upgraded(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    r1 = await client.post(
        "/api/auth/upgrade", json={"email": "u@example.com"}
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/api/auth/upgrade", json={"email": "v@example.com"}
    )
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "ALREADY_UPGRADED"


async def test_duplicate_email_returns_409(
    app: object,  # FastAPI app injected via fixture
    client: AsyncClient,
) -> None:
    # Client A claims an email first.
    await client.get("/api/bootstrap")
    r1 = await client.post(
        "/api/auth/upgrade", json={"email": "taken@example.com"}
    )
    assert r1.status_code == 200

    # Client B (fresh cookie jar) tries the same email.
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client_b:
        await client_b.get("/api/bootstrap")
        r2 = await client_b.post(
            "/api/auth/upgrade", json={"email": "taken@example.com"}
        )
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_upgrade_preserves_conversation_fk(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The verification spike from the plan: upgrading mutates the user row in
    place, so FK rows like `conversation.user_id` keep pointing at the right
    user without any data migration."""
    await client.get("/api/bootstrap")
    anon = await _current_user(session_factory)
    anon_id = anon.id

    # Create a conversation as the anon user.
    convo = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart"},
    )
    assert convo.status_code == 201
    conv_id = convo.json()["id"]

    # Upgrade in place.
    response = await client.post(
        "/api/auth/upgrade", json={"email": "founder@example.com"}
    )
    assert response.status_code == 200

    async with session_factory() as session:
        user_after = (await session.execute(select(User))).scalar_one()
        assert user_after.id == anon_id  # SAME id -- in-place mutation
        assert user_after.is_anonymous is False
        # The conversation row still points at the SAME user id.
        convo_row = (
            await session.execute(select(Conversation))
        ).scalar_one()
        assert convo_row.user_id == anon_id

    # Round-trip via the API: GET the conversation -- still owned by the
    # now-upgraded user (the cookie is unchanged, the session row still maps
    # to the same user, the conversation FK still resolves).
    get_response = await client.get(f"/api/conversations/{conv_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == conv_id


async def test_missing_email_returns_400(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.post("/api/auth/upgrade", json={"password": "x"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_invalid_email_format_returns_400(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade", json={"email": "not-an-email"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_upgrade_without_password_leaves_password_hash_null(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade", json={"email": "nopass@example.com"}
    )
    assert response.status_code == 200
    row = await _current_user(session_factory)
    assert row.password_hash is None
    assert row.is_anonymous is False


async def test_upgrade_with_password_longer_than_72_bytes(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A >72-byte password upgrades and the stored hash verifies losslessly.

    Post-M4 hardening: argon2id replaces bcrypt as the minted scheme, so the
    72-byte cap is gone -- the full plaintext is hashed and any suffix beyond
    72 bytes is part of the verifying input.
    """
    long_password = "a" * 100  # 100 ASCII bytes; bcrypt would have capped at 72.
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "long@example.com", "password": long_password},
    )
    assert response.status_code == 200, response.text
    row = await _current_user(session_factory)
    assert row.password_hash is not None
    assert row.password_hash.startswith("$argon2id$")
    ok, _ = verify_password(long_password, row.password_hash)
    assert ok is True


async def test_upgrade_argon2id_distinguishes_long_password_suffixes(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """argon2id hashes the full plaintext: differing suffixes do NOT collide.

    Under bcrypt, two passwords sharing their first 72 bytes verified against
    the same digest. Under argon2id (Post-M4 hardening) the entire input is
    fed to the KDF, so a suffix change after byte 72 must fail verification.
    """
    stored = "a" * 72 + "DIFFERS-AFTER-72"
    other = "a" * 72 + "completely-different-suffix"
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "argon2-suffix@example.com", "password": stored},
    )
    assert response.status_code == 200, response.text
    row = await _current_user(session_factory)
    assert row.password_hash is not None
    assert row.password_hash.startswith("$argon2id$")
    # The exact plaintext verifies.
    ok_stored, _ = verify_password(stored, row.password_hash)
    assert ok_stored is True
    # A different suffix does NOT -- argon2id is sensitive to the full input.
    ok_other, _ = verify_password(other, row.password_hash)
    assert ok_other is False


async def test_upgrade_response_resigns_session_cookie(
    client: AsyncClient,
) -> None:
    """A successful upgrade re-emits a Set-Cookie sid=... header.

    Defensive against signature drift / key rotation: even though the session
    id is unchanged (the cookie value is usually identical to what the client
    already holds), we re-sign and re-set the cookie so a SESSION_SECRET
    rotation never leaves an upgraded client on a stale signature.
    """
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "cookie@example.com", "password": "doesnotmatter"},
    )
    assert response.status_code == 200, response.text
    set_cookie = response.headers.get("set-cookie", "")
    assert "sid=" in set_cookie.lower()
    # Verify it's an issuance, not a deletion: a re-sign sets Max-Age to the
    # session window (>0), unlike signout's Max-Age=0 clear.
    assert "max-age=0" not in set_cookie.lower()
