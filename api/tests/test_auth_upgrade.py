"""POST /api/auth/upgrade tests (M3).

Covers:
- Upgrade anonymous -> returns updated AccountInfo with email + derived name.
- Re-upgrade (already non-anonymous) -> 400 ALREADY_UPGRADED.
- Duplicate email across two anon users -> 409 EMAIL_TAKEN.
- Upgrade preserves conversation FK (the row id is unchanged, the FK still
  points at it). This is the verification spike from the plan.
- Missing email -> 400 from Pydantic.
- Optional password is hashed via bcrypt and not stored plaintext.
- Password >72 bytes upgrades and verifies (bcrypt's 72-byte cap).
- Multi-byte char straddling the 72-byte cut truncates safely and verifies.
- Passwords equal in their first 72 bytes are treated as equivalent.
"""

from __future__ import annotations

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.routes import _truncate_for_bcrypt
from app.db.models import Conversation, User

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
    assert bcrypt.checkpw(b"supersecret", row.password_hash.encode("ascii"))


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
    """A >72-byte password upgrades and the stored hash verifies with it."""
    long_password = "a" * 100  # 100 ASCII bytes, well past the 72-byte cap.
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "long@example.com", "password": long_password},
    )
    assert response.status_code == 200, response.text
    row = await _current_user(session_factory)
    assert row.password_hash is not None
    # bcrypt rejects raw >72-byte input, so verify with the same truncation the
    # route applied; the password the user typed maps to this digest.
    assert bcrypt.checkpw(
        _truncate_for_bcrypt(long_password), row.password_hash.encode("ascii")
    )


async def test_upgrade_with_multibyte_char_at_byte_boundary(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A multi-byte char straddling the 72-byte cut must not raise and verifies.

    "é" is 2 bytes (0xc3 0xa9); placed at byte offset 71 it straddles the cut,
    so a naive byte slice would leave a dangling 0xc3 and bcrypt would reject
    the malformed input. The boundary-safe truncation drops the partial char.
    """
    password = "a" * 71 + "é" + "z" * 10
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "mb@example.com", "password": password},
    )
    assert response.status_code == 200, response.text
    row = await _current_user(session_factory)
    assert row.password_hash is not None
    # The boundary-safe cut lands at byte 71: the partial "é" (0xc3 0xa9 would
    # straddle byte 72) is dropped whole, leaving a clean 71-byte value with no
    # dangling 0xc3 that bcrypt would reject.
    truncated = _truncate_for_bcrypt(password)
    assert truncated == b"a" * 71
    # A valid bcrypt hash is produced and the truncated input verifies.
    assert row.password_hash.startswith("$2")
    assert bcrypt.checkpw(truncated, row.password_hash.encode("ascii"))


async def test_passwords_equal_in_first_72_bytes_are_equivalent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two passwords sharing their first 72 bytes hash-verify interchangeably.

    bcrypt ignores input past 72 bytes, so the truncation contract means a
    password differing only after byte 72 verifies against the stored hash.
    """
    stored = "a" * 72 + "DIFFERS-AFTER-72"
    other = "a" * 72 + "completely-different-suffix"
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": "trunc@example.com", "password": stored},
    )
    assert response.status_code == 200, response.text
    row = await _current_user(session_factory)
    assert row.password_hash is not None
    assert row.password_hash.startswith("$2")
    # Both inputs collapse to the same first-72-bytes value, so both verify
    # against the one stored digest -- the truncation contract in action.
    assert _truncate_for_bcrypt(stored) == _truncate_for_bcrypt(other) == b"a" * 72
    digest = row.password_hash.encode("ascii")
    assert bcrypt.checkpw(_truncate_for_bcrypt(stored), digest)
    assert bcrypt.checkpw(_truncate_for_bcrypt(other), digest)
