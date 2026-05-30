"""POST /api/auth/login tests.

Login is a session HANDOFF to an existing registered account (contrast with
`upgrade`, which merges the current anonymous identity in place). Covered:

- Success from an anonymous session: the cookie repoints at the target, the
  previous anonymous user row + its guest scratch are deleted, the target's
  own data survives.
- Uniform 401 (`INVALID_CREDENTIALS`) across wrong password, unknown email,
  and a password-less (`password_hash IS NULL`) account -- the envelope's
  code/title/body must be byte-identical so the email cannot be enumerated.
- Opportunistic argon2id rehash of a legacy bcrypt target on successful login.
- Account switch (previous user is itself registered): session moves, the
  other account's row is left intact.
- `isAnonymous` is present + correct on the bootstrap AccountInfo for both an
  anonymous and a registered user.

Fixtures (`client`, `app`, `session_factory`) come from `conftest.py`; the
bcrypt-legacy helper mirrors `test_password_hashing.py`.
"""

from __future__ import annotations

from uuid import UUID

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, User
from app.db.models import Session as DbSession
from app.security.passwords import hash_password

pytestmark = pytest.mark.asyncio


def _bcrypt_legacy_digest(plaintext: str) -> str:
    """Mint a bcrypt `$2b$` digest the way the pre-argon2 route did.

    Inlined (matches `test_password_hashing.py`) so the test owns a realistic
    legacy row to exercise the rehash-on-login path.
    """
    return bcrypt.hashpw(
        plaintext.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)
    ).decode("ascii")


async def _seed_registered_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    password_hash: str | None,
    name: str = "registered",
) -> UUID:
    """Insert a non-anonymous user directly and return its id."""
    async with session_factory() as session:
        user = User(
            is_anonymous=False,
            name=name,
            email=email,
            password_hash=password_hash,
            plan_label="Free",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _user_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as s:
        return int(
            (await s.execute(select(func.count()).select_from(User))).scalar_one()
        )


async def _user_by_id(
    session_factory: async_sessionmaker[AsyncSession], user_id: UUID
) -> User | None:
    async with session_factory() as s:
        return (
            await s.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Success path + handoff semantics
# ---------------------------------------------------------------------------


async def test_login_from_anonymous_session_handoff(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Anon session logs in: cookie repoints at target, anon row is reclaimed."""
    target_id = await _seed_registered_user(
        session_factory,
        email="alice@example.com",
        password_hash=hash_password("supersecret"),
    )

    # Establish an anonymous session in this client's cookie jar.
    await client.get("/api/bootstrap")
    async with session_factory() as s:
        anon = (
            await s.execute(select(User).where(User.is_anonymous == True))  # noqa: E712
        ).scalar_one()
        anon_id = anon.id
    assert anon_id != target_id

    response = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "supersecret"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["isAnonymous"] is False

    # The previously-anonymous user row is gone.
    assert await _user_by_id(session_factory, anon_id) is None
    # The session now points at the target.
    async with session_factory() as s:
        sessions = (await s.execute(select(DbSession))).scalars().all()
        assert len(sessions) == 1
        assert sessions[0].user_id == target_id

    # The cookie still resolves to the target on a follow-up request.
    follow = await client.get("/api/bootstrap")
    assert follow.json()["account"]["email"] == "alice@example.com"


async def test_login_preserves_target_data_discards_guest_scratch(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Target's pre-existing conversation survives; the anon's scratch is gone."""
    target_id = await _seed_registered_user(
        session_factory,
        email="owner@example.com",
        password_hash=hash_password("pw"),
    )
    # Pre-existing conversation owned by the target.
    async with session_factory() as s:
        target_convo = Conversation(
            user_id=target_id, title="kept", selected_tier_id="smart"
        )
        s.add(target_convo)
        await s.commit()
        await s.refresh(target_convo)
        target_convo_id = target_convo.id

    # Anon session + a scratch conversation owned by the anon user.
    await client.get("/api/bootstrap")
    scratch = await client.post(
        "/api/conversations", json={"selectedTierId": "smart"}
    )
    assert scratch.status_code == 201
    scratch_id = UUID(scratch.json()["id"])

    response = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "pw"},
    )
    assert response.status_code == 200, response.text

    async with session_factory() as s:
        convo_ids = set(
            (await s.execute(select(Conversation.id))).scalars().all()
        )
    assert target_convo_id in convo_ids  # target's data intact
    assert scratch_id not in convo_ids  # guest scratch discarded


async def test_login_with_anon_no_session_mints_fresh_session(
    app: object,  # FastAPI app fixture
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No usable cookie on the request: login mints a fresh session for target.

    The `current_user` dependency creates a brand-new anon user (and commits a
    session for it), but `current_session` sees no incoming cookie and returns
    None -- exercising the fresh-session branch. The new session must point at
    the target and the cookie must be set.
    """
    target_id = await _seed_registered_user(
        session_factory,
        email="nocookie@example.com",
        password_hash=hash_password("pw"),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as fresh:
        response = await fresh.post(
            "/api/auth/login",
            json={"email": "nocookie@example.com", "password": "pw"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["isAnonymous"] is False
        assert "sid=" in response.headers.get("set-cookie", "").lower()

    # Exactly the target user remains; its session points at it.
    assert await _user_count(session_factory) == 1
    async with session_factory() as s:
        sessions = (await s.execute(select(DbSession))).scalars().all()
        assert all(row.user_id == target_id for row in sessions)


# ---------------------------------------------------------------------------
# Uniform 401: no account enumeration
# ---------------------------------------------------------------------------


def _error(body: dict[str, object]) -> dict[str, object]:
    return body["error"]  # type: ignore[return-value]


async def test_login_wrong_password_401(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_registered_user(
        session_factory,
        email="bob@example.com",
        password_hash=hash_password("correct"),
    )
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    assert _error(response.json())["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email_matches_wrong_password_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unknown-email and wrong-password 401s must be byte-identical (no enum)."""
    await _seed_registered_user(
        session_factory,
        email="known@example.com",
        password_hash=hash_password("correct"),
    )
    await client.get("/api/bootstrap")

    wrong_pw = await client.post(
        "/api/auth/login",
        json={"email": "known@example.com", "password": "wrong"},
    )
    unknown = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "whatever"},
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert _error(wrong_pw.json()) == _error(unknown.json())


async def test_login_password_less_account_401(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An email-only account (`password_hash IS NULL`) cannot log in -> 401."""
    await _seed_registered_user(
        session_factory,
        email="emailonly@example.com",
        password_hash=None,
    )
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/login",
        json={"email": "emailonly@example.com", "password": "anything"},
    )
    assert response.status_code == 401
    assert _error(response.json())["code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# Legacy bcrypt rehash on login
# ---------------------------------------------------------------------------


async def test_login_rehashes_bcrypt_target_to_argon2id(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A bcrypt-hashed target logs in successfully and its hash is rewritten."""
    target_id = await _seed_registered_user(
        session_factory,
        email="legacy@example.com",
        password_hash=_bcrypt_legacy_digest("legacy-pw"),
    )
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/login",
        json={"email": "legacy@example.com", "password": "legacy-pw"},
    )
    assert response.status_code == 200, response.text

    after = await _user_by_id(session_factory, target_id)
    assert after is not None
    assert after.password_hash is not None
    assert after.password_hash.startswith("$argon2id$")


# ---------------------------------------------------------------------------
# Account switch
# ---------------------------------------------------------------------------


async def test_login_account_switch_leaves_other_account_intact(
    app: object,  # FastAPI app fixture
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Logged in as A, login as B: session moves to B, A's row survives."""
    a_id = await _seed_registered_user(
        session_factory,
        email="a@example.com",
        password_hash=hash_password("a-pw"),
        name="a",
    )
    b_id = await _seed_registered_user(
        session_factory,
        email="b@example.com",
        password_hash=hash_password("b-pw"),
        name="b",
    )

    # Establish session A: an anon client logs in as A.
    await client.get("/api/bootstrap")
    login_a = await client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "a-pw"}
    )
    assert login_a.status_code == 200

    # Now switch to B on the same session.
    login_b = await client.post(
        "/api/auth/login", json={"email": "b@example.com", "password": "b-pw"}
    )
    assert login_b.status_code == 200
    assert login_b.json()["email"] == "b@example.com"

    # A's row is still there (account switch does NOT delete the prior account).
    assert await _user_by_id(session_factory, a_id) is not None
    # The session now points at B.
    async with session_factory() as s:
        sessions = (await s.execute(select(DbSession))).scalars().all()
        assert len(sessions) == 1
        assert sessions[0].user_id == b_id


# ---------------------------------------------------------------------------
# isAnonymous discriminator on bootstrap
# ---------------------------------------------------------------------------


async def test_bootstrap_is_anonymous_true_for_guest(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["account"]["isAnonymous"] is True


async def test_bootstrap_is_anonymous_false_after_login(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_registered_user(
        session_factory,
        email="reg@example.com",
        password_hash=hash_password("pw"),
    )
    await client.get("/api/bootstrap")
    await client.post(
        "/api/auth/login", json={"email": "reg@example.com", "password": "pw"}
    )
    response = await client.get("/api/bootstrap")
    assert response.json()["account"]["isAnonymous"] is False
