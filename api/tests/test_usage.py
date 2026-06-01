"""usage_rollup increment tests (M3).

Covers:
- A successful streaming turn bumps usage_rollup.used by 1.
- Multi-turn accumulation (3 turns -> used=3).
- Bootstrap.usage.used reflects the rollup row.
- Stop-path increment exercised by directly driving `stream_and_persist` with
  a Request stub that signals disconnect immediately (the route-level
  disconnect path is xfail under the httpx ASGI transport -- see
  test_messages_stream.py).
- Repository upsert semantics for the calendar-month period_start key.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, UsageCreditLedger, UsageRollup, User
from app.db.repositories import usage as usage_repo

pytestmark = pytest.mark.asyncio


async def _parse_sse_stream(response_text: str) -> list[tuple[str, dict[str, object]]]:
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
                data_payload = fragment if data_payload is None else data_payload + fragment
        if event_name is None or data_payload is None:
            continue
        try:
            parsed = json.loads(data_payload)
        except json.JSONDecodeError:
            parsed = {}
        frames.append((event_name, parsed))
    return frames


async def _send_message(
    client: AsyncClient,
    conv_id: str,
    text: str = "hello",
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": "smart",
            "text": text,
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: object,
) -> str:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id="smart",
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


# Route-level tests ------------------------------------------------------------


async def test_single_turn_increments_usage_rollup(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    frames = await _send_message(client, conv_id)
    # Sanity: the turn completed with a terminal frame.
    assert frames[-1][0] == "terminal"

    async with session_factory() as session:
        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.used == 1
        # No BYOK key -> is_byok stays False.
        assert row.is_byok is False


async def test_multi_turn_accumulation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)

    for i in range(3):
        await _send_message(client, conv_id, text=f"turn {i}")

    async with session_factory() as session:
        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.used == 3


async def test_bootstrap_usage_used_reflects_increments(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    boot0 = await client.get("/api/bootstrap")
    assert boot0.json()["usage"]["used"] == 0

    user_id = await _current_user_id(session_factory)
    conv_id = await _seed_conversation(session_factory, user_id=user_id)
    await _send_message(client, conv_id, text="t1")
    await _send_message(client, conv_id, text="t2")

    boot1 = await client.get("/api/bootstrap")
    body = boot1.json()
    assert body["usage"]["used"] == 2
    # No BYOK rows -> false.
    assert body["usage"]["isByok"] is False


async def test_temporary_chat_does_not_increment(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Temporary chats skip persistence, including usage_rollup."""
    await client.get("/api/bootstrap")
    # Create a temporary chat via POST /api/conversations.
    convo = await client.post(
        "/api/conversations",
        json={"selectedTierId": "smart", "isTemporary": True},
    )
    assert convo.status_code == 201
    conv_id = convo.json()["id"]
    await _send_message(client, conv_id, text="ephemeral")

    async with session_factory() as session:
        count = int(
            (
                await session.execute(select(func.count()).select_from(UsageRollup))
            ).scalar_one()
        )
        assert count == 0


# Repository-level tests -------------------------------------------------------


async def test_increment_for_period_inserts_then_updates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Direct repo test -- bumps for the same period accumulate, not overwrite."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        # First bump inserts.
        await usage_repo.increment_for_period(session, user_id=user.id)
        await session.commit()
        # Second bump updates in place.
        await usage_repo.increment_for_period(session, user_id=user.id)
        await session.commit()

        rows = (await session.execute(select(UsageRollup))).scalars().all()
        assert len(rows) == 1
        assert rows[0].used == 2


async def test_increment_records_is_byok_flag(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """is_byok=True propagates to the row on insert and on subsequent updates."""
    async with session_factory() as session:
        user = User(is_anonymous=False, name="Eve", email="e@e.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        await usage_repo.increment_for_period(
            session, user_id=user.id, is_byok=True
        )
        await session.commit()

        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.used == 1
        assert row.is_byok is True


async def test_get_current_budget_returns_zero_when_no_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        budget = await usage_repo.get_current_budget(session, user.id, is_byok=False)
        assert budget.used == 0
        assert budget.limit == 1000
        assert budget.is_byok is False
        assert budget.credit_balance_usd == 0
        assert budget.recent_ledger_entries == []


async def test_credit_grant_and_adjustment_update_balance(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        await usage_repo.grant_credits(
            session,
            user_id=user.id,
            amount_usd=5.25,
            description="Local grant",
        )
        await usage_repo.adjust_credits(
            session,
            user_id=user.id,
            amount_usd=-1.0,
            description="Correction",
        )
        await session.commit()

        balance = await usage_repo.get_credit_balance(session, user_id=user.id)
        entries = await usage_repo.list_recent_credit_entries(
            session,
            user_id=user.id,
        )

        assert balance == pytest.approx(4.25)
        by_type = {entry.entry_type: entry for entry in entries}
        assert set(by_type) == {"adjustment", "grant"}
        assert by_type["adjustment"].amount_usd == pytest.approx(-1.0)


async def test_platform_usage_debits_credits_only_after_monthly_quota(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        await usage_repo.grant_credits(session, user_id=user.id, amount_usd=3.0)
        await usage_repo.increment_for_period(
            session,
            user_id=user.id,
            cost_usd_delta=0.75,
            monthly_quota_usd=1.0,
        )
        await usage_repo.increment_for_period(
            session,
            user_id=user.id,
            cost_usd_delta=0.50,
            monthly_quota_usd=1.0,
        )
        await session.commit()

        balance = await usage_repo.get_credit_balance(session, user_id=user.id)
        debits = (
            await session.execute(
                select(UsageCreditLedger).where(
                    UsageCreditLedger.entry_type == "platform_debit"
                )
            )
        ).scalars().all()

        assert balance == pytest.approx(2.75)
        assert len(debits) == 1
        assert debits[0].amount_usd == pytest.approx(-0.25)


async def test_byok_usage_does_not_debit_platform_credits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=False, name="Eve", email="eve@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        await usage_repo.grant_credits(session, user_id=user.id, amount_usd=2.0)
        await usage_repo.increment_for_period(
            session,
            user_id=user.id,
            cost_usd_delta=5.0,
            is_byok=True,
            monthly_quota_usd=1.0,
        )
        await session.commit()

        balance = await usage_repo.get_credit_balance(session, user_id=user.id)
        entries = (
            await session.execute(
                select(UsageCreditLedger).where(
                    UsageCreditLedger.user_id == user.id
                )
            )
        ).scalars().all()

        assert balance == pytest.approx(2.0)
        assert [entry.entry_type for entry in entries] == ["grant"]


async def test_concurrent_platform_debits_cannot_overspend_credits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await usage_repo.grant_credits(session, user_id=user.id, amount_usd=1.0)
        await session.commit()
        user_id = user.id

    async def _debit() -> None:
        async with session_factory() as session:
            await usage_repo.debit_platform_credits(
                session,
                user_id=user_id,
                amount_usd=0.75,
            )
            await session.commit()

    await asyncio.gather(_debit(), _debit())

    async with session_factory() as session:
        balance = await usage_repo.get_credit_balance(session, user_id=user_id)
        rows = (
            await session.execute(
                select(UsageCreditLedger).where(
                    UsageCreditLedger.user_id == user_id,
                    UsageCreditLedger.entry_type == "platform_debit",
                )
            )
        ).scalars().all()
        ledger_total = (
            await session.execute(
                select(func.coalesce(func.sum(UsageCreditLedger.amount_usd), 0)).where(
                    UsageCreditLedger.user_id == user_id
                )
            )
        ).scalar_one()

    assert balance == pytest.approx(0)
    assert sum(float(row.amount_usd) for row in rows) == pytest.approx(-1.0)
    assert float(ledger_total) == pytest.approx(0)


async def test_concurrent_cross_quota_usage_debits_full_overage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    period = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await usage_repo.grant_credits(session, user_id=user.id, amount_usd=10.0)
        await session.commit()
        user_id = user.id

    async def _record_usage() -> None:
        async with session_factory() as session:
            await usage_repo.increment_for_period(
                session,
                user_id=user_id,
                cost_usd_delta=0.75,
                monthly_quota_usd=1.0,
                period_start=period,
            )
            await session.commit()

    await asyncio.gather(_record_usage(), _record_usage())

    async with session_factory() as session:
        balance = await usage_repo.get_credit_balance(session, user_id=user_id)
        rollup = (
            await session.execute(
                select(UsageRollup).where(UsageRollup.user_id == user_id)
            )
        ).scalar_one()
        debits = (
            await session.execute(
                select(UsageCreditLedger).where(
                    UsageCreditLedger.user_id == user_id,
                    UsageCreditLedger.entry_type == "platform_debit",
                )
            )
        ).scalars().all()

    assert rollup.cost_usd == pytest.approx(1.5)
    assert sum(float(row.amount_usd) for row in debits) == pytest.approx(-0.5)
    assert balance == pytest.approx(9.5)


async def test_get_current_budget_exposes_credit_read_model(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        await usage_repo.grant_credits(session, user_id=user.id, amount_usd=1.5)
        await usage_repo.increment_for_period(
            session,
            user_id=user.id,
            cost_usd_delta=0.25,
            monthly_quota_usd=1.0,
        )
        await session.commit()

        budget = await usage_repo.get_current_budget(
            session,
            user.id,
            is_byok=False,
            monthly_quota_usd=1.0,
        )

        assert budget.monthly_spend_usd == pytest.approx(0.25)
        assert budget.monthly_quota_usd == pytest.approx(1.0)
        assert budget.credit_balance_usd == pytest.approx(1.5)
        assert budget.platform_remaining_usd == pytest.approx(2.25)
        assert len(budget.recent_ledger_entries) == 1
        assert budget.recent_ledger_entries[0].entry_type == "grant"


async def test_stopped_flush_increments_usage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Direct stop-path test: drive `stream_and_persist` with a Request stub
    that returns is_disconnected()=True immediately. The handler must
    persist the assistant row with status=stopped AND bump usage_rollup.

    This complements the route-level test (xfail above) by exercising the
    stop-path branch directly without needing a real HTTP transport.
    """
    from app.providers.factory import build_provider
    from app.providers.tiers import get_binding
    from app.streaming.handler import stream_and_persist

    binding = get_binding("smart")
    assert binding is not None

    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        user_id = user.id
        conv_id = convo.id

    class _StubRequest:
        async def is_disconnected(self) -> bool:
            return True

    async with session_factory() as session:
        provider = build_provider()
        # Drain the generator: each yield is an SSE event, but on instant
        # disconnect the loop bails out before any yields beyond `submitted`.
        gen = stream_and_persist(
            request=_StubRequest(),  # type: ignore[arg-type]
            db=session,
            provider=provider,
            binding=binding,
            requested_tier_id="smart",
            conversation_id=conv_id,
            user_message_id=uuid4(),
            user_text="hello",
            history=[],
            is_temporary=False,
            user_id=user_id,
        )
        async for _ in gen:
            pass

    async with session_factory() as session:
        row = (await session.execute(select(UsageRollup))).scalar_one()
        assert row.used == 1


async def test_increment_separate_periods_isolated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two distinct period_start values produce two distinct rows."""
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Current month and a previous month -- 2 rows.
        now = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_year = now.year if now.month > 1 else now.year - 1
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_period = now.replace(year=prev_month_year, month=prev_month)

        await usage_repo.increment_for_period(session, user_id=user.id)
        await usage_repo.increment_for_period(
            session, user_id=user.id, period_start=prev_period
        )
        await session.commit()

        rows = (await session.execute(select(UsageRollup))).scalars().all()
        assert len(rows) == 2
