"""POST /api/auth/upgrade tests (M3).

Covers:
- Upgrade anonymous -> returns updated AccountInfo with email + derived name.
- Re-upgrade (already non-anonymous) -> 400 ALREADY_UPGRADED.
- Duplicate email across two anon users -> 409 EMAIL_TAKEN.
- Upgrade preserves conversation FK (the row id is unchanged, the FK still
  points at it). This is the verification spike from the plan.
- Missing email -> 400 from Pydantic.
- Optional password is hashed via bcrypt and not stored plaintext.
"""

from __future__ import annotations

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
