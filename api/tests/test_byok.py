"""BYOK route + repository tests (M3).

Covers:
- PUT byok stores encrypted data; repo-level decryption matches plaintext.
- PUT byok rejects anonymous users -> 403 ANONYMOUS_REQUIRED.
- DELETE byok removes the row and is idempotent.
- DELETE byok rejects anonymous -> 403.
- Invalid (empty / short) apiKey -> 400 INVALID_INPUT.
- Bootstrap.account.byokEnabled and byokMaskedKey reflect roundtrip state.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ApiKey, AuditEvent, User
from app.db.repositories import api_keys as api_keys_repo

pytestmark = pytest.mark.asyncio


async def _upgrade_anonymous(client: AsyncClient, email: str = "u@example.com") -> None:
    """Bootstrap then upgrade so the test user is non-anonymous."""
    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": email, "password": "hunter2hunter2"},
    )
    assert response.status_code == 200, response.text


async def test_put_byok_stores_encrypted_and_roundtrips_decrypt(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _upgrade_anonymous(client)
    plaintext_key = "sk-deepseek-fake-12345678abcdef"

    response = await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": plaintext_key},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["byokEnabled"] is True
    assert body["byokMaskedKey"] == "sk-...cdef"

    # Confirm the row's ciphertext does NOT contain the plaintext.
    async with session_factory() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        assert plaintext_key not in row.ciphertext
        # Repo-level decryption returns the plaintext.
        decrypted = await api_keys_repo.get_decrypted_for_user(
            session, user_id=row.user_id, provider="deepseek"
        )
        assert decrypted == plaintext_key


async def test_put_byok_anonymous_returns_403(client: AsyncClient) -> None:
    # No upgrade -- the user stays anonymous.
    await client.get("/api/bootstrap")
    response = await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": "sk-ant-fake-12345678"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ANONYMOUS_REQUIRED"


async def test_delete_byok_removes_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _upgrade_anonymous(client)
    await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "sk-deepseek-fake-12345678"},
    )
    async with session_factory() as session:
        assert (await session.execute(select(ApiKey))).scalar_one_or_none() is not None

    response = await client.delete("/api/account/byok/deepseek")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["byokEnabled"] is False
    # Masked key is suppressed when no key exists.
    assert body.get("byokMaskedKey") is None

    async with session_factory() as session:
        assert (await session.execute(select(ApiKey))).scalar_one_or_none() is None


async def test_byok_writes_audit_events(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _upgrade_anonymous(client)

    put = await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": "sk-ant-fake-12345678"},
    )
    assert put.status_code == 200
    delete = await client.delete("/api/account/byok/anthropic")
    assert delete.status_code == 200

    async with session_factory() as session:
        rows = (
            (await session.execute(select(AuditEvent).order_by(AuditEvent.created_at.asc())))
            .scalars()
            .all()
        )
    assert [row.event_type for row in rows] == ["byok.upsert", "byok.revoke"]
    assert [row.details["provider"] for row in rows] == ["anthropic", "anthropic"]
    assert rows[1].details["removed"] is True


async def test_delete_byok_anonymous_returns_403(client: AsyncClient) -> None:
    await client.get("/api/bootstrap")
    response = await client.delete("/api/account/byok/anthropic")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ANONYMOUS_REQUIRED"


async def test_delete_byok_idempotent(client: AsyncClient) -> None:
    await _upgrade_anonymous(client)
    # First DELETE on a non-existent row.
    r1 = await client.delete("/api/account/byok/anthropic")
    assert r1.status_code == 200
    assert r1.json()["byokEnabled"] is False
    # Second DELETE on a now-confirmed missing row.
    r2 = await client.delete("/api/account/byok/anthropic")
    assert r2.status_code == 200
    assert r2.json()["byokEnabled"] is False


async def test_put_byok_rejects_empty_apikey(client: AsyncClient) -> None:
    await _upgrade_anonymous(client)
    response = await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": ""},
    )
    # Pydantic min_length=1 catches "" -> validation error -> INVALID_INPUT.
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_put_byok_rejects_short_apikey(client: AsyncClient) -> None:
    await _upgrade_anonymous(client)
    response = await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": "  short  "},  # trims to "short"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


async def test_bootstrap_reflects_byok_state(client: AsyncClient) -> None:
    await _upgrade_anonymous(client)
    # Before PUT.
    boot1 = await client.get("/api/bootstrap")
    assert boot1.status_code == 200
    account1 = boot1.json()["account"]
    assert account1["byokEnabled"] is False
    assert account1.get("byokMaskedKey") is None

    # After PUT.
    await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "sk-deepseek-fake-12345678abc"},
    )
    boot2 = await client.get("/api/bootstrap")
    account2 = boot2.json()["account"]
    assert account2["byokEnabled"] is True
    assert account2["byokMaskedKey"] == "sk-...8abc"
    # usage.isByok also flips because list_for_user returns >=1 row now.
    assert boot2.json()["usage"]["isByok"] is True

    # After DELETE.
    await client.delete("/api/account/byok/deepseek")
    boot3 = await client.get("/api/bootstrap")
    account3 = boot3.json()["account"]
    assert account3["byokEnabled"] is False
    assert account3.get("byokMaskedKey") is None
    assert boot3.json()["usage"]["isByok"] is False


async def test_put_byok_upsert_replaces_existing_row(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _upgrade_anonymous(client)
    await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": "sk-ant-fake-first1234"},
    )
    await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": "sk-ant-fake-second5678"},
    )
    # Exactly one row, holding the second key.
    async with session_factory() as session:
        rows = (await session.execute(select(ApiKey))).scalars().all()
        assert len(rows) == 1
        user = (await session.execute(select(User))).scalar_one()
        decrypted = await api_keys_repo.get_decrypted_for_user(
            session, user_id=user.id, provider="anthropic"
        )
        assert decrypted == "sk-ant-fake-second5678"


async def test_bootstrap_ignores_inactive_provider_byok(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A stored key for another provider is saveable but not active BYOK state."""
    await _upgrade_anonymous(client)
    response = await client.put(
        "/api/account/byok",
        json={"provider": "anthropic", "apiKey": "sk-ant-fake-12345678abc"},
    )
    assert response.status_code == 200
    assert response.json()["byokEnabled"] is False
    assert response.json().get("byokMaskedKey") is None

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200
    assert boot.json()["account"]["byokEnabled"] is False
    assert boot.json()["account"].get("byokMaskedKey") is None
    assert boot.json()["usage"]["isByok"] is False

    async with session_factory() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        assert row.provider == "anthropic"


async def test_non_sk_provider_uses_generic_mask(
    client: AsyncClient,
) -> None:
    await _upgrade_anonymous(client)
    response = await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "abcdefghIJKL"},
    )
    assert response.status_code == 200
    assert response.json()["byokMaskedKey"] == "...IJKL"


async def test_byok_resolved_per_request_for_signed_in_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A signed-in user's BYOK key is resolved at request time and flagged on
    the usage_rollup row."""
    from uuid import uuid4

    from app.db.models import Conversation, UsageRollup

    await _upgrade_anonymous(client)
    # Canonical backend is DeepSeek (fake/default path binds provider_id
    # "deepseek"), so the BYOK key must be stored for the "deepseek" provider
    # for per-request resolution to flag this turn is_byok.
    await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "sk-deepseek-fake-12345678"},
    )

    # Seed a conversation for the upgraded user.
    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        convo = Conversation(
            user_id=user.id,
            title="t",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = str(convo.id)

    # Send a turn; the usage row should be flagged is_byok=True.
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200
        async for _ in resp.aiter_text():
            pass

    async with session_factory() as session:
        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.is_byok is True


async def test_byok_decryption_failure_falls_back_silently(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Corrupted ciphertext in the DB falls back to the platform key without
    failing the request. The repo logs and returns None; the route proceeds
    with `api_key=None` (platform default)."""
    from uuid import uuid4

    from app.db.models import ApiKey, Conversation, UsageRollup

    await _upgrade_anonymous(client)
    await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "sk-deepseek-fake-12345678"},
    )

    # Tamper with the stored ciphertext.
    async with session_factory() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        row.ciphertext = "not-valid-base64!!!"
        await session.commit()

    async with session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        convo = Conversation(
            user_id=user.id,
            title="t",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        conv_id = str(convo.id)

    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "hi",
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200
        async for _ in resp.aiter_text():
            pass

    # Turn completed; usage row exists. is_byok=False since we fell back.
    async with session_factory() as session:
        row2 = (await session.execute(select(UsageRollup))).scalar_one()
        assert row2.used == 1
        assert row2.is_byok is False
