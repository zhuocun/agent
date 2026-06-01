"""Cost ledger + cost-based budget enforcement tests (PRD 04 §5.6/§6, PRD 05).

Covers the parallel cost field added alongside the integer `used` meter:

- `message.cost_usd` is persisted on the assistant row after a normal turn.
- `usage_rollup.cost_usd` accumulates across turns in the same period.
- `get_period_cost` reads the accumulated value.
- `USAGE_BUDGET_USD` enforcement: once the period's accumulated cost reaches the
  cap, the next platform-key turn is refused with a 429 BUDGET_EXCEEDED envelope.
- BYOK turns are exempt: a user with a stored BYOK key keeps streaming even when
  the cap is already exceeded (they pay their own provider).

Uses the fake provider (env defaults to `PROVIDER_BACKEND=fake`). The
`USAGE_BUDGET_USD` flips follow the `RATE_LIMIT_MESSAGES` precedent in
tests/test_ratelimit.py: monkeypatch the env, bust the `get_settings` lru_cache,
build a fresh app, and restore the cache in teardown so other tests are
unaffected.
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
from app.db.models import Conversation, Message, UsageCreditLedger, UsageRollup, User
from app.db.session import get_db

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a captured SSE body into (event, data-dict) tuples."""
    normalized = response_text.replace("\r\n", "\n").replace("\r", "\n")
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
    """POST `body`, assert 200, and return parsed SSE frames."""
    async with client.stream("POST", url, json=body, timeout=10.0) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


def _send_body() -> dict[str, object]:
    """Fresh body with a new clientMessageId so idempotent replay is skipped."""
    return {
        "clientMessageId": str(uuid4()),
        "tierId": "smart",
        "text": "hello world",
    }


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
    tier_id: str = "smart",
) -> str:
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
        return str(convo.id)


async def _current_user_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> object:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one().id


# Cost ledger persistence ------------------------------------------------------


async def test_assistant_message_persists_cost_usd(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A normal (non-temporary) turn writes a non-NULL `cost_usd` on the row."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", _send_body()
    )

    async with session_factory() as session:
        asst = (
            await session.execute(
                select(Message).where(Message.role == "assistant")
            )
        ).scalar_one()
        assert asst.cost_usd is not None
        assert asst.cost_usd > 0
        # Ledger field mirrors what the wire attribution reports as costUsd.
        assert asst.attribution is not None
        assert asst.cost_usd == pytest.approx(asst.attribution["costUsd"])


async def test_usage_rollup_cost_accumulates_across_turns(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two turns in the same period grow `usage_rollup.cost_usd`."""
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", _send_body()
    )
    async with session_factory() as session:
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        after_one = float(rollup.cost_usd)
    assert after_one > 0

    await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", _send_body()
    )
    async with session_factory() as session:
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        after_two = float(rollup.cost_usd)
        # `used` (the integer meter) stays in lockstep but is a separate axis.
        assert rollup.used == 2
    assert after_two > after_one


async def test_get_period_cost_returns_accumulated_value(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`get_period_cost` returns the period's accumulated `cost_usd`."""
    from app.db.repositories import usage as usage_repo

    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    await _collect_sse(
        client, f"/api/conversations/{conv_id}/messages", _send_body()
    )

    async with session_factory() as session:
        rollup = (await session.execute(select(UsageRollup))).scalar_one()
        ledger = float(rollup.cost_usd)
        period_cost = await usage_repo.get_period_cost(
            session, user_id=user_id  # type: ignore[arg-type]
        )
    assert period_cost == pytest.approx(ledger)
    assert period_cost > 0


async def test_get_period_cost_zero_when_no_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No rollup row for the period -> get_period_cost returns 0.0."""
    from app.db.repositories import usage as usage_repo

    async with session_factory() as session:
        cost = await usage_repo.get_period_cost(session, user_id=uuid4())
    assert cost == 0.0


# Budget enforcement -----------------------------------------------------------


@pytest.fixture
def budget_env() -> Iterator[None]:
    """Override `USAGE_BUDGET_USD` to a tiny cap for the duration of the test."""
    prior = os.environ.get("USAGE_BUDGET_USD")
    # Tiny but non-zero: a single fake turn's cost exceeds this, so the SECOND
    # turn's pre-flight gate sees an accumulated cost >= cap and refuses.
    os.environ["USAGE_BUDGET_USD"] = "0.0000001"
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("USAGE_BUDGET_USD", None)
        else:
            os.environ["USAGE_BUDGET_USD"] = prior
        get_settings.cache_clear()


@pytest.fixture
def budget_app(
    budget_env: None,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_db_path: Path,
) -> Iterator[FastAPI]:
    """Build a fresh app under the budget override, reusing the test DB."""
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
async def budget_client(budget_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=budget_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client_:
        yield client_


async def test_budget_exceeded_returns_429(
    budget_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """First platform-key turn passes (cap not yet reached); the next turn,
    after the ledger crosses the tiny cap, is refused with 429 BUDGET_EXCEEDED.
    """
    await budget_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    # Turn 1: ledger starts at 0 < cap, so the gate lets it through. It writes a
    # cost well above the tiny cap.
    first_body = _send_body()
    await _collect_sse(
        budget_client, f"/api/conversations/{conv_id}/messages", first_body
    )

    # Retrying the same idempotency key after the first turn depleted allowance
    # must replay the already-billed response, not consult budget again.
    replay = await _collect_sse(
        budget_client, f"/api/conversations/{conv_id}/messages", first_body
    )
    assert replay[-1][0] == "terminal"

    # Turn 2: pre-flight gate sees accumulated cost >= cap -> 429.
    resp = await budget_client.post(
        f"/api/conversations/{conv_id}/messages", json=_send_body()
    )
    assert resp.status_code == 429, resp.text
    payload = resp.json()
    assert payload["error"]["code"] == "BUDGET_EXCEEDED"
    assert payload["error"]["severity"] == "warning"
    assert payload["error"]["retryAfterMs"] > 0
    actions = payload["error"]["actions"]
    assert isinstance(actions, list)
    assert actions[0]["kind"] == "open_settings"


async def test_byok_turn_exempt_from_budget(
    budget_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A non-anonymous user with a stored BYOK key keeps streaming even when the
    period's accumulated cost is already over the cap -- they pay their own
    provider, so platform-cost enforcement does not apply.
    """
    from app.db.repositories import api_keys as api_keys_repo
    from app.providers.tiers import get_binding

    binding = get_binding("smart")
    assert binding is not None

    # Seed an upgraded (non-anonymous) user with a BYOK key for the bound
    # provider, plus an over-budget rollup so the gate WOULD fire if consulted.
    async with session_factory() as session:
        user = User(is_anonymous=False, name="Upgraded", email="byok@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await api_keys_repo.upsert(
            session,
            user_id=user.id,
            provider=binding.provider_id,
            raw_api_key="sk-test-byok-key-1234",
        )
        from app.db.repositories import usage as usage_repo

        # Push the ledger well past the tiny cap for this period.
        await usage_repo.increment_for_period(
            session, user_id=user.id, used_delta=1, cost_usd_delta=1.0
        )
        await session.commit()
        byok_user_id = user.id

    # Authenticate the client AS this user by minting its session cookie.
    cookie_name, cookie_value = await _session_cookie_for(
        session_factory, byok_user_id
    )
    budget_client.cookies.set(cookie_name, cookie_value)

    conv_id = await _seed_conversation(session_factory, user_id=byok_user_id)

    # BYOK turn streams 200 despite the over-budget ledger.
    frames = await _collect_sse(
        budget_client, f"/api/conversations/{conv_id}/messages", _send_body()
    )
    event_names = [n for n, _ in frames]
    assert event_names[0] == "submitted"
    assert event_names[-1] == "terminal"
    terminal = frames[-1][1]
    attribution = terminal["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["isByok"] is True


async def test_platform_credits_extend_budget_and_are_debited(
    budget_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When monthly spend is already over quota, a positive credit balance lets
    the next platform-key turn start and records a platform debit afterward.
    """
    from app.db.repositories import usage as usage_repo

    await budget_client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)

    async with session_factory() as session:
        await usage_repo.grant_credits(
            session,
            user_id=user_id,  # type: ignore[arg-type]
            amount_usd=1.0,
            description="Test credit",
        )
        await usage_repo.increment_for_period(
            session,
            user_id=user_id,  # type: ignore[arg-type]
            used_delta=1,
            cost_usd_delta=1.0,
        )
        await session.commit()

    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _collect_sse(
        budget_client, f"/api/conversations/{conv_id}/messages", _send_body()
    )
    assert frames[-1][0] == "terminal"

    async with session_factory() as session:
        debits = (
            await session.execute(
                select(UsageCreditLedger).where(
                    UsageCreditLedger.entry_type == "platform_debit"
                )
            )
        ).scalars().all()

    assert len(debits) == 1
    assert debits[0].amount_usd < 0


async def _session_cookie_for(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: object,
) -> tuple[str, str]:
    """Mint a signed session cookie (name, value) for `user_id`.

    Creates a Session row and signs its id the same way the auth layer does
    (`build_signer` + `dump_session_id`), so the test client can present as the
    BYOK user on subsequent requests.
    """
    from datetime import UTC, datetime, timedelta

    from app.auth.cookies import build_signer, dump_session_id
    from app.config import get_settings
    from app.db.models import Session as SessionModel

    settings = get_settings()
    async with session_factory() as session:
        sess = SessionModel(
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        session.add(sess)
        await session.commit()
        await session.refresh(sess)
        sid = sess.id

    signer = build_signer(settings.session_secret)
    return settings.cookie_name, dump_session_id(signer, str(sid))
