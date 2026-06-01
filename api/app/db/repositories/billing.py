"""Billing entitlement repository.

The credit ledger remains the money source of truth for spendable USD credits.
This module owns payment-provider identity, Pro entitlements, and webhook
idempotency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    BillingCustomer,
    BillingEntitlement,
    BillingFulfillment,
    BillingWebhookEvent,
    User,
)
from app.schemas.account import BillingState

PlanId = Literal["free", "pro"]
ProviderId = Literal["stripe", "fake"]
_ACTIVE_STATUSES = {"active", "trialing"}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _plan_label(plan_id: PlanId) -> str:
    return "Pro" if plan_id == "pro" else "Free"


def _provider(settings: Settings) -> ProviderId | None:
    if settings.billing_backend in ("stripe", "fake"):
        return settings.billing_backend
    return None


async def get_customer_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: ProviderId,
) -> BillingCustomer | None:
    stmt = select(BillingCustomer).where(
        BillingCustomer.user_id == user_id,
        BillingCustomer.provider == provider,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_or_repair_customer_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: ProviderId,
) -> BillingCustomer | None:
    row = await get_customer_for_user(db, user_id=user_id, provider=provider)
    if row is not None:
        return row
    customer_id = (
        await db.execute(
            select(BillingEntitlement.external_customer_id)
            .where(
                BillingEntitlement.user_id == user_id,
                BillingEntitlement.provider == provider,
                BillingEntitlement.external_customer_id.is_not(None),
            )
            .order_by(BillingEntitlement.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not customer_id:
        return None
    return await upsert_customer(
        db,
        user_id=user_id,
        provider=provider,
        external_customer_id=customer_id,
    )


async def get_user_id_for_customer(
    db: AsyncSession,
    *,
    provider: ProviderId,
    external_customer_id: str,
) -> UUID | None:
    stmt = select(BillingCustomer.user_id).where(
        BillingCustomer.provider == provider,
        BillingCustomer.external_customer_id == external_customer_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def upsert_customer(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: ProviderId,
    external_customer_id: str,
) -> BillingCustomer:
    row = await get_customer_for_user(db, user_id=user_id, provider=provider)
    if row is None:
        row = BillingCustomer(
            user_id=user_id,
            provider=provider,
            external_customer_id=external_customer_id,
        )
        db.add(row)
    else:
        row.external_customer_id = external_customer_id
        row.updated_at = _now()
    await db.flush()
    return row


async def has_active_pro_entitlement(
    db: AsyncSession,
    *,
    user_id: UUID,
    now: datetime | None = None,
) -> bool:
    ref = now if now is not None else _now()
    rows = (
        (
            await db.execute(
                select(BillingEntitlement).where(
                    BillingEntitlement.user_id == user_id,
                    BillingEntitlement.plan_id == "pro",
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if row.status not in _ACTIVE_STATUSES:
            continue
        period_end = _aware(row.current_period_end)
        if period_end is not None and period_end > ref:
            return True
    return False


async def refresh_user_plan_label(db: AsyncSession, *, user_id: UUID) -> PlanId:
    user = await db.get(User, user_id)
    if user is None:
        return "free"
    plan_id: PlanId = (
        "pro" if await has_active_pro_entitlement(db, user_id=user_id) else "free"
    )
    user.plan_label = _plan_label(plan_id)
    await db.flush()
    return plan_id


async def get_billing_state(
    db: AsyncSession,
    *,
    user: User,
    settings: Settings,
    credit_balance_usd: float,
) -> BillingState:
    provider = _provider(settings)
    plan_id = await refresh_user_plan_label(db, user_id=user.id)
    customer = (
        await get_or_repair_customer_for_user(db, user_id=user.id, provider=provider)
        if provider is not None
        else None
    )
    base_checkout_available = provider is not None and not user.is_anonymous
    pro_checkout_available = base_checkout_available
    credit_checkout_available = base_checkout_available
    if provider == "stripe":
        pro_checkout_available = pro_checkout_available and bool(
            settings.stripe_pro_price_id
        )
        credit_checkout_available = credit_checkout_available and bool(
            settings.stripe_credit_price_id
        )
    return BillingState(
        plan_id=plan_id,
        plan_label=_plan_label(plan_id),
        pro_enabled=plan_id == "pro",
        billing_provider=provider,
        checkout_available=pro_checkout_available,
        pro_checkout_available=pro_checkout_available,
        credit_checkout_available=credit_checkout_available,
        portal_available=provider is not None
        and not user.is_anonymous
        and customer is not None,
        credit_balance_usd=credit_balance_usd,
    )


async def mark_webhook_event_processing(
    db: AsyncSession,
    *,
    provider: ProviderId,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    values = dict(
        event_id=event_id,
        provider=provider,
        event_type=event_type,
        payload=payload,
    )
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    if dialect == "postgresql":
        stmt_pg = pg_insert(BillingWebhookEvent).values(**values)
        stmt_pg = stmt_pg.on_conflict_do_nothing(
            index_elements=["provider", "event_id"]
        )
        result = await db.execute(stmt_pg)
    else:
        stmt_sq = sqlite_insert(BillingWebhookEvent).values(**values)
        stmt_sq = stmt_sq.on_conflict_do_nothing(
            index_elements=["provider", "event_id"]
        )
        result = await db.execute(stmt_sq)
    await db.flush()
    return cast(CursorResult[Any], result).rowcount == 1


async def mark_fulfillment_processing(
    db: AsyncSession,
    *,
    provider: ProviderId,
    fulfillment_type: str,
    object_id: str,
    event_id: str,
) -> bool:
    values = dict(
        provider=provider,
        fulfillment_type=fulfillment_type,
        object_id=object_id,
        event_id=event_id,
    )
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    if dialect == "postgresql":
        stmt_pg = pg_insert(BillingFulfillment).values(**values)
        stmt_pg = stmt_pg.on_conflict_do_nothing(
            index_elements=["provider", "fulfillment_type", "object_id"]
        )
        result = await db.execute(stmt_pg)
    else:
        stmt_sq = sqlite_insert(BillingFulfillment).values(**values)
        stmt_sq = stmt_sq.on_conflict_do_nothing(
            index_elements=["provider", "fulfillment_type", "object_id"]
        )
        result = await db.execute(stmt_sq)
    await db.flush()
    return cast(CursorResult[Any], result).rowcount == 1


async def upsert_subscription_entitlement(
    db: AsyncSession,
    *,
    user_id: UUID,
    provider: ProviderId,
    subscription_id: str,
    status: str,
    customer_id: str | None,
    current_period_end: datetime | None,
    event_created_at: datetime | None,
) -> BillingEntitlement:
    stmt = select(BillingEntitlement).where(
        BillingEntitlement.provider == provider,
        BillingEntitlement.external_subscription_id == subscription_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    incoming_event_created_at = _aware(event_created_at)
    if row is None:
        row = BillingEntitlement(
            user_id=user_id,
            provider=provider,
            plan_id="pro",
            status=status,
            external_subscription_id=subscription_id,
            external_customer_id=customer_id,
            current_period_end=current_period_end,
            external_event_created_at=incoming_event_created_at,
        )
        db.add(row)
    else:
        existing_event_created_at = _aware(row.external_event_created_at)
        if (
            existing_event_created_at is not None
            and incoming_event_created_at is not None
            and incoming_event_created_at < existing_event_created_at
        ):
            await refresh_user_plan_label(db, user_id=user_id)
            return row
        row.user_id = user_id
        row.status = status
        row.external_customer_id = customer_id
        row.current_period_end = current_period_end
        if incoming_event_created_at is not None:
            row.external_event_created_at = incoming_event_created_at
        row.updated_at = _now()
    if customer_id:
        await upsert_customer(
            db,
            user_id=user_id,
            provider=provider,
            external_customer_id=customer_id,
        )
    await refresh_user_plan_label(db, user_id=user_id)
    await db.flush()
    return row


def parse_provider(value: str) -> ProviderId:
    if value not in ("stripe", "fake"):
        raise ValueError(f"unsupported billing provider {value!r}")
    return cast(ProviderId, value)
