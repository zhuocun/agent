"""Anonymous-guest send-limit tests (PRD 08 §5.4 / §7.4, T06).

Two gates for ANONYMOUS users on persisted platform-key turns:

- **Hard sign-up wall** (`PLATFORM_GUEST_LIMIT`): once a guest has sent
  `GUEST_MESSAGE_LIMIT` persisted messages, the next send is refused (403).
- **Premium-allotment downgrade** (`PLATFORM_GUEST_DOWNGRADE`): once a guest has
  been served `GUEST_PREMIUM_MESSAGE_LIMIT` premium-tier turns, the next premium
  request is transparently served by `fast` with a visible `auto_downgrade`
  substitution callout (never a silent swap).

Temporary chats persist nothing, so they are the deliberate escape hatch — never
gated. The integration tests flip the tiny env caps via the same monkeypatch /
fresh-app pattern as `tests/test_budget.py`.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.session import get_db
from app.guest_limits import (
    count_guest_messages,
    count_guest_premium_messages,
    is_premium_tier,
)

# `asyncio_mode = "auto"` (pyproject) runs the async tests below; the sync unit
# test stays sync, so no module-level asyncio mark is needed.


# Unit: tier classification + message counting --------------------------------


def test_is_premium_tier_only_fast_is_free() -> None:
    """`fast` is the only non-premium served tier; everything else is premium."""
    assert is_premium_tier("fast") is False
    assert is_premium_tier("smart") is True
    assert is_premium_tier("pro") is True
    # `auto` never appears as a SERVED tier, but a requested `auto` counts as
    # premium for the request-side gate.
    assert is_premium_tier("auto") is True


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> object:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id=tier_id,
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return convo.id


async def _seed_user_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conversation_id: object,
    text: str = "hi",
) -> None:
    async with session_factory() as session:
        session.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                parts=[{"type": "text", "text": text}],
            )
        )
        await session.commit()


async def _seed_assistant_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conversation_id: object,
    served_tier_id: str,
) -> None:
    async with session_factory() as session:
        session.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                parts=[{"type": "text", "text": "ok"}],
                attribution={"servedTierId": served_tier_id},
            )
        )
        await session.commit()


async def test_count_guest_messages_counts_only_user_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    await _seed_user_message(session_factory, conversation_id=conv_id)
    await _seed_user_message(session_factory, conversation_id=conv_id)
    # An assistant row must NOT count toward the user-message wall.
    await _seed_assistant_message(
        session_factory, conversation_id=conv_id, served_tier_id="smart"
    )

    async with session_factory() as session:
        assert await count_guest_messages(session, user_id) == 2  # type: ignore[arg-type]


async def test_count_guest_premium_messages_counts_only_non_fast_served(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    await _seed_assistant_message(
        session_factory, conversation_id=conv_id, served_tier_id="smart"
    )
    await _seed_assistant_message(
        session_factory, conversation_id=conv_id, served_tier_id="pro"
    )
    # A `fast`-served assistant turn does NOT count against the premium allotment.
    await _seed_assistant_message(
        session_factory, conversation_id=conv_id, served_tier_id="fast"
    )

    async with session_factory() as session:
        assert await count_guest_premium_messages(session, user_id) == 2  # type: ignore[arg-type]


# Integration: route enforcement ----------------------------------------------


def _send_body(tier_id: str = "smart") -> dict[str, object]:
    return {
        "clientMessageId": str(uuid4()),
        "tierId": tier_id,
        "text": "hello world",
    }


async def _parse_sse_stream(text: str) -> list[tuple[str, dict[str, object]]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    frames: list[tuple[str, dict[str, object]]] = []
    for chunk in normalized.split("\n\n"):
        if not chunk.strip():
            continue
        event_name: str | None = None
        data_payload: str | None = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                fragment = line[len("data:") :].strip()
                data_payload = (
                    fragment if data_payload is None else data_payload + fragment
                )
        if event_name is None or data_payload is None:
            continue
        try:
            parsed = json.loads(data_payload)
        except json.JSONDecodeError:
            parsed = {}
        frames.append((event_name, parsed))
    return frames


async def _collect_sse(
    client: AsyncClient, url: str, body: dict[str, object]
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


@pytest.fixture
def guest_env() -> Iterator[None]:
    """Tiny guest caps so a couple of seeded rows trip the gates."""
    prior_limit = os.environ.get("GUEST_MESSAGE_LIMIT")
    prior_premium = os.environ.get("GUEST_PREMIUM_MESSAGE_LIMIT")
    os.environ["GUEST_MESSAGE_LIMIT"] = "2"
    os.environ["GUEST_PREMIUM_MESSAGE_LIMIT"] = "1"
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, prior in (
            ("GUEST_MESSAGE_LIMIT", prior_limit),
            ("GUEST_PREMIUM_MESSAGE_LIMIT", prior_premium),
        ):
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
        get_settings.cache_clear()


@pytest.fixture
def guest_app(
    guest_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_db_path: Path,
) -> Iterator[FastAPI]:
    from app.main import create_app
    from app.middleware.ratelimit import limiter
    from app.routes.conversations import _TEMP_IDS

    _TEMP_IDS.clear()
    storage = limiter._storage
    if hasattr(storage, "storage"):
        storage.storage.clear()
    if hasattr(storage, "expirations"):
        storage.expirations.clear()

    app_ = create_app()

    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app_.dependency_overrides[get_db] = _get_db_override
    try:
        yield app_
    finally:
        _TEMP_IDS.clear()


@pytest.fixture
async def guest_client(guest_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=guest_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client_:
        yield client_


async def test_guest_hard_wall_refuses_after_limit(
    guest_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Once a guest hits GUEST_MESSAGE_LIMIT persisted messages, the next send
    is refused with a 403 PLATFORM_GUEST_LIMIT block."""
    await guest_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Seed the limit (2) of persisted user messages.
    await _seed_user_message(session_factory, conversation_id=conv_id)
    await _seed_user_message(session_factory, conversation_id=conv_id)

    resp = await guest_client.post(
        f"/api/conversations/{conv_id}/messages", json=_send_body("fast")
    )
    assert resp.status_code == 403, resp.text
    payload = resp.json()
    assert payload["error"]["code"] == "PLATFORM_GUEST_LIMIT"
    # The copy states the limit (PRD 08 copy rule).
    assert "2-message" in payload["error"]["body"]


async def test_guest_premium_downgrade_serves_fast_with_substitution(
    guest_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """After the premium allotment is exhausted, a premium request is served by
    `fast` with a visible `auto_downgrade` substitution; the requested tier
    stays the premium tier the guest asked for."""
    await guest_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Seed the premium allotment (1) of premium-served assistant turns.
    await _seed_assistant_message(
        session_factory, conversation_id=conv_id, served_tier_id="smart"
    )

    frames = await _collect_sse(
        guest_client, f"/api/conversations/{conv_id}/messages", _send_body("smart")
    )
    assert frames[-1][0] == "terminal"
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    # Served by fast, but the request is still disclosed as the premium tier.
    assert attribution["servedTierId"] == "fast"
    assert attribution["requestedTierId"] == "smart"
    # The downgrade is never silent — an auto_downgrade substitution callout.
    assert attribution["substitution"] is not None
    assert attribution["substitution"]["reasonCode"] == "auto_downgrade"


async def test_guest_premium_under_limit_is_not_downgraded(
    guest_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Below the premium allotment a premium request is served by the requested
    premium tier with no substitution."""
    await guest_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # No premium turns served yet (limit is 1), so this premium send is honored.
    frames = await _collect_sse(
        guest_client, f"/api/conversations/{conv_id}/messages", _send_body("smart")
    )
    assert frames[-1][0] == "terminal"
    attribution = frames[-1][1]["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["servedTierId"] == "smart"
    # No substitution: the field is omitted from the wire when there is none.
    assert attribution.get("substitution") is None


async def test_temporary_chat_is_never_gated_for_guests(
    guest_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Temporary chats persist nothing and are the deliberate escape hatch: a
    guest over the hard wall can still stream a temporary turn."""
    await guest_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)

    # Push the guest well over the persisted hard wall (limit is 2).
    convo_id = await _seed_conversation(session_factory, user_id=user_id)
    for _ in range(3):
        await _seed_user_message(session_factory, conversation_id=convo_id)

    # Create a temporary conversation and send to it — not gated.
    create_resp = await guest_client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": True},
    )
    assert create_resp.status_code == 201
    synthetic_id = create_resp.json()["id"]

    frames = await _collect_sse(
        guest_client,
        f"/api/conversations/{synthetic_id}/messages",
        {
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": "temp hello",
            "isTemporary": True,
        },
    )
    assert frames[0][0] == "submitted"
    assert frames[-1][0] == "terminal"
