"""Billing entitlement and credit route tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.models import (
    BillingCustomer,
    BillingEntitlement,
    BillingFulfillment,
    BillingWebhookEvent,
    User,
)
from app.db.repositories import billing as billing_repo
from app.db.repositories import usage as usage_repo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_test() -> Iterator[None]:
    yield
    get_settings.cache_clear()


def _enable_fake_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILLING_BACKEND", "fake")
    get_settings.cache_clear()


async def _upgrade(client: AsyncClient, email: str = "u@example.com") -> None:
    response = await client.post(
        "/api/auth/upgrade",
        json={"email": email, "password": "hunter2hunter2"},
    )
    assert response.status_code == 200, response.text


async def _current_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    async with session_factory() as session:
        return (await session.execute(select(User))).scalar_one()


async def _post_fake_webhook(
    client: AsyncClient,
    payload: dict[str, object],
) -> dict[str, object]:
    response = await client.post("/api/billing/webhook", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


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
    *,
    tier_id: str,
    text: str,
) -> list[tuple[str, dict[str, object]]]:
    async with client.stream(
        "POST",
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": str(uuid4()),
            "tierId": tier_id,
            "text": text,
        },
        timeout=10.0,
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        chunks: list[str] = []
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
        return await _parse_sse_stream("".join(chunks))


def _future_period_end() -> int:
    return int((datetime.now(UTC) + timedelta(days=30)).timestamp())


async def test_anonymous_checkout_requires_sign_in(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    response = await client.post(
        "/api/billing/checkout",
        json={"kind": "pro_subscription"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SIGN_IN_REQUIRED"


async def test_fake_checkout_and_portal_use_customer_mapping(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    await _upgrade(client)
    user = await _current_user(session_factory)

    checkout = await client.post(
        "/api/billing/checkout",
        json={"kind": "pro_subscription"},
    )
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["url"].startswith("/settings?billing=fake-pro_subscription")

    no_customer = await client.post("/api/billing/portal")
    assert no_customer.status_code == 409

    async with session_factory() as session:
        await billing_repo.upsert_customer(
            session,
            user_id=user.id,
            provider="fake",
            external_customer_id="cus_fake",
        )
        await session.commit()

    portal = await client.post("/api/billing/portal")
    assert portal.status_code == 200, portal.text
    assert portal.json()["url"].startswith("/settings?billing=fake-portal")


async def test_subscription_event_upgrades_to_pro_and_bootstrap_surfaces_state(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    await _upgrade(client)
    user = await _current_user(session_factory)

    checkout = await _post_fake_webhook(
        client,
        {
            "id": "evt_checkout_pro",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_pro",
                    "customer": "cus_pro",
                    "subscription": "sub_pro",
                    "metadata": {
                        "user_id": str(user.id),
                        "purpose": "pro_subscription",
                    },
                }
            },
        },
    )
    assert checkout["processed"] is True
    async with session_factory() as session:
        entitlements = (await session.execute(select(BillingEntitlement))).scalars().all()
        refreshed_user = await session.get(User, user.id)
        assert entitlements == []
        assert refreshed_user is not None
        assert refreshed_user.plan_label == "Free"

    subscription = await _post_fake_webhook(
        client,
        {
            "id": "evt_subscription_active",
            "type": "customer.subscription.created",
            "created": 100,
            "data": {
                "object": {
                    "id": "sub_pro",
                    "customer": "cus_pro",
                    "status": "active",
                    "current_period_end": _future_period_end(),
                    "metadata": {"user_id": str(user.id)},
                }
            },
        },
    )
    assert subscription["processed"] is True

    async with session_factory() as session:
        ent = (await session.execute(select(BillingEntitlement))).scalar_one()
        refreshed_user = await session.get(User, user.id)
        assert ent.status == "active"
        assert refreshed_user is not None
        assert refreshed_user.plan_label == "Pro"
        await usage_repo.grant_credits(
            session,
            user_id=user.id,
            amount_usd=4.25,
            description="Test billing credit",
        )
        await session.commit()

    boot = await client.get("/api/bootstrap")
    assert boot.status_code == 200, boot.text
    billing = boot.json()["account"]["billing"]
    assert billing["planId"] == "pro"
    assert billing["proEnabled"] is True
    assert billing["billingProvider"] == "fake"
    assert billing["checkoutAvailable"] is True
    assert billing["proCheckoutAvailable"] is True
    assert billing["creditCheckoutAvailable"] is True
    assert billing["portalAvailable"] is True
    assert billing["creditBalanceUsd"] == pytest.approx(4.25)

    pro_conversation = await client.post(
        "/api/conversations",
        json={"selectedTierId": "pro"},
    )
    assert pro_conversation.status_code == 201, pro_conversation.text


async def test_credit_purchase_webhook_is_event_idempotent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    await _upgrade(client)
    user = await _current_user(session_factory)
    event = {
        "id": "evt_credit",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_credit",
                "customer": "cus_credit",
                "payment_status": "paid",
                "metadata": {
                    "user_id": str(user.id),
                    "purpose": "credit_purchase",
                    "credit_amount_usd": "12.50",
                },
            }
        },
    }

    first = await _post_fake_webhook(client, event)
    second = await _post_fake_webhook(client, event)
    duplicate_object = dict(event)
    duplicate_object["id"] = "evt_credit_duplicate_object"
    third = await _post_fake_webhook(client, duplicate_object)
    unpaid_event = {
        "id": "evt_credit_unpaid",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_credit_unpaid",
                "customer": "cus_credit",
                "status": "complete",
                "payment_status": "unpaid",
                "metadata": {
                    "user_id": str(user.id),
                    "purpose": "credit_purchase",
                    "credit_amount_usd": "99.00",
                },
            }
        },
    }
    unpaid = await _post_fake_webhook(client, unpaid_event)

    assert first["processed"] is True
    assert second["processed"] is False
    assert third["processed"] is True
    assert unpaid["processed"] is True
    async with session_factory() as session:
        balance = await usage_repo.get_credit_balance(session, user_id=user.id)
        webhook_events = (
            (await session.execute(select(BillingWebhookEvent)))
            .scalars()
            .all()
        )
        fulfillments = (
            (await session.execute(select(BillingFulfillment)))
            .scalars()
            .all()
        )
    assert balance == pytest.approx(12.5)
    assert sorted(row.event_id for row in webhook_events) == [
        "evt_credit",
        "evt_credit_duplicate_object",
        "evt_credit_unpaid",
    ]
    assert [(row.object_id, row.event_id) for row in fulfillments] == [
        ("cs_credit", "evt_credit")
    ]


async def test_webhook_customer_mapping_wins_over_conflicting_metadata(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    await _upgrade(client)
    primary_user = await _current_user(session_factory)
    other_user = User(
        email=f"{uuid4()}@example.com",
        name="Other",
        is_anonymous=False,
    )
    async with session_factory() as session:
        session.add(other_user)
        await session.flush()
        await billing_repo.upsert_customer(
            session,
            user_id=primary_user.id,
            provider="fake",
            external_customer_id="cus_shared",
        )
        await session.commit()

    result = await _post_fake_webhook(
        client,
        {
            "id": "evt_conflicting_customer_metadata",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_conflicting_customer_metadata",
                    "customer": "cus_shared",
                    "payment_status": "paid",
                    "metadata": {
                        "user_id": str(other_user.id),
                        "purpose": "credit_purchase",
                        "credit_amount_usd": "7.00",
                    },
                }
            },
        },
    )

    assert result["processed"] is True
    async with session_factory() as session:
        primary_balance = await usage_repo.get_credit_balance(
            session,
            user_id=primary_user.id,
        )
        other_balance = await usage_repo.get_credit_balance(
            session,
            user_id=other_user.id,
        )
    assert primary_balance == pytest.approx(7.0)
    assert other_balance == pytest.approx(0.0)


async def test_credit_purchase_webhook_handles_bad_amount_metadata(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    await _upgrade(client)
    user = await _current_user(session_factory)

    malformed = await _post_fake_webhook(
        client,
        {
            "id": "evt_credit_malformed_amount",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_credit_malformed_amount",
                    "customer": "cus_credit",
                    "payment_status": "paid",
                    "metadata": {
                        "user_id": str(user.id),
                        "purpose": "credit_purchase",
                        "credit_amount_usd": "not-a-number",
                    },
                }
            },
        },
    )
    negative = await _post_fake_webhook(
        client,
        {
            "id": "evt_credit_negative_amount",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_credit_negative_amount",
                    "customer": "cus_credit",
                    "payment_status": "paid",
                    "metadata": {
                        "user_id": str(user.id),
                        "purpose": "credit_purchase",
                        "credit_amount_usd": "-5.00",
                    },
                }
            },
        },
    )

    assert malformed["processed"] is True
    assert negative["processed"] is True
    async with session_factory() as session:
        balance = await usage_repo.get_credit_balance(session, user_id=user.id)
    assert balance == pytest.approx(20.0)


async def test_webhook_rejects_invalid_utf8_payload(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    response = await client.post(
        "/api/billing/webhook",
        content=b"\xff",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_WEBHOOK_PAYLOAD"


async def test_handled_webhook_rejects_missing_object(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    response = await client.post(
        "/api/billing/webhook",
        json={
            "id": "evt_missing_object",
            "type": "checkout.session.completed",
            "data": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_WEBHOOK_PAYLOAD"
    async with session_factory() as session:
        rows = (await session.execute(select(BillingWebhookEvent))).scalars().all()
    assert rows == []


async def test_customer_mapping_is_scoped_by_provider(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await _upgrade(client, email=f"{uuid4()}@example.com")
    user = await _current_user(session_factory)

    async with session_factory() as session:
        await billing_repo.upsert_customer(
            session,
            user_id=user.id,
            provider="fake",
            external_customer_id="cus_fake",
        )
        await billing_repo.upsert_customer(
            session,
            user_id=user.id,
            provider="stripe",
            external_customer_id="cus_stripe",
        )
        await session.commit()

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(BillingCustomer).where(BillingCustomer.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )

    assert sorted((row.provider, row.external_customer_id) for row in rows) == [
        ("fake", "cus_fake"),
        ("stripe", "cus_stripe"),
    ]


async def test_stripe_checkout_availability_is_per_kind(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.get("/api/bootstrap")
    await _upgrade(client, email=f"{uuid4()}@example.com")
    user = await _current_user(session_factory)

    async with session_factory() as session:
        pro_only = await billing_repo.get_billing_state(
            session,
            user=user,
            settings=Settings(
                BILLING_BACKEND="stripe",
                STRIPE_PRO_PRICE_ID="price_pro",
                STRIPE_CREDIT_PRICE_ID=None,
            ),
            credit_balance_usd=0.0,
        )
        credit_only = await billing_repo.get_billing_state(
            session,
            user=user,
            settings=Settings(
                BILLING_BACKEND="stripe",
                STRIPE_PRO_PRICE_ID=None,
                STRIPE_CREDIT_PRICE_ID="price_credit",
            ),
            credit_balance_usd=0.0,
        )

    assert pro_only.checkout_available is True
    assert pro_only.pro_checkout_available is True
    assert pro_only.credit_checkout_available is False
    assert credit_only.checkout_available is False
    assert credit_only.pro_checkout_available is False
    assert credit_only.credit_checkout_available is True


async def test_subscription_deleted_downgrades_when_no_active_entitlement_remains(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_fake_billing(monkeypatch)

    await client.get("/api/bootstrap")
    await _upgrade(client)
    user = await _current_user(session_factory)
    async with session_factory() as session:
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=user.id,
            provider="fake",
            subscription_id="sub_to_cancel",
            status="active",
            customer_id="cus_cancel",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.fromtimestamp(100, tz=UTC),
        )
        await session.commit()

    await _post_fake_webhook(
        client,
        {
            "id": "evt_sub_deleted",
            "type": "customer.subscription.deleted",
            "created": 200,
            "data": {
                "object": {
                    "id": "sub_to_cancel",
                    "customer": "cus_cancel",
                    "metadata": {"user_id": str(user.id)},
                }
            },
        },
    )

    async with session_factory() as session:
        refreshed = await session.get(User, user.id)
        assert refreshed is not None
        assert refreshed.plan_label == "Free"

    await _post_fake_webhook(
        client,
        {
            "id": "evt_sub_old_active",
            "type": "customer.subscription.updated",
            "created": 100,
            "data": {
                "object": {
                    "id": "sub_to_cancel",
                    "customer": "cus_cancel",
                    "status": "active",
                    "current_period_end": _future_period_end(),
                    "metadata": {"user_id": str(user.id)},
                }
            },
        },
    )
    async with session_factory() as session:
        refreshed = await session.get(User, user.id)
        assert refreshed is not None
        assert refreshed.plan_label == "Free"


async def test_free_platform_pro_route_is_blocked_but_byok_is_exempt(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")

    fast = await client.post(
        "/api/conversations",
        json={"selectedTierId": "fast"},
    )
    assert fast.status_code == 201, fast.text

    pro = await client.post(
        "/api/conversations",
        json={"selectedTierId": "pro"},
    )
    assert pro.status_code == 402
    assert pro.json()["error"]["code"] == "PRO_REQUIRED"

    await _upgrade(client, email=f"{uuid4()}@example.com")
    byok = await client.put(
        "/api/account/byok",
        json={"provider": "deepseek", "apiKey": "sk-deepseek-fake-12345678"},
    )
    assert byok.status_code == 200, byok.text

    pro_byok = await client.post(
        "/api/conversations",
        json={"selectedTierId": "pro"},
    )
    assert pro_byok.status_code == 201, pro_byok.text


async def test_free_platform_auto_does_not_route_to_pro(
    client: AsyncClient,
) -> None:
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/conversations",
        json={"selectedTierId": "auto"},
    )
    assert created.status_code == 201, created.text
    frames = await _send_message(
        client,
        created.json()["id"],
        tier_id="auto",
        text=(
            "```python\n"
            "def f(x): return x\n"
            "```\n"
            "Please reason step by step and prove correctness."
        ),
    )
    terminal = next(payload for name, payload in frames if name == "terminal")
    attribution = terminal["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["requestedTierId"] == "auto"
    assert attribution["servedTierId"] == "smart"
