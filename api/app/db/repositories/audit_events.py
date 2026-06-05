"""Audit-event repository.

Routes append sensitive account/trust events; account export includes the
caller's own prior events. A bounded, newest-first read
(`list_recent_for_user`) backs the user-facing activity log — it returns ONLY
the caller's own rows and never another user's.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, Conversation, Message


async def record(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    row = AuditEvent(
        user_id=user_id,
        event_type=event_type,
        details=details or {},
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.user_id == user_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def list_recent_for_user(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    before: tuple[datetime, UUID] | None = None,
) -> Sequence[AuditEvent]:
    """Return the caller's own audit events, newest-first, keyset-paginated.

    `before` is a COMPOSITE `(created_at, id)` cursor matching the
    `(created_at DESC, id DESC)` sort. A composite cursor is required because
    `created_at` ties are reachable — `func.now()` is the transaction timestamp
    on Postgres (constant within a request that emits several events) and only
    second-resolution on SQLite — and `id` is a random uuid4, so a plain
    `created_at <` cursor would silently drop a tie group straddling a page
    boundary. Scoped to `user_id`, so it can NEVER surface another user's rows
    (and the SET-NULL `account.delete` rows, whose `user_id` is NULL, are
    excluded).
    """
    stmt = select(AuditEvent).where(AuditEvent.user_id == user_id)
    if before is not None:
        before_ts, before_id = before
        stmt = stmt.where(
            or_(
                AuditEvent.created_at < before_ts,
                and_(
                    AuditEvent.created_at == before_ts,
                    AuditEvent.id < before_id,
                ),
            )
        )
    stmt = stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@dataclass
class ProviderAttributionCounts:
    """Per-provider attribution counts for the data-processing rollup.

    `provider_label` is a best-effort fallback captured from the persisted
    attribution; the route prefers the live registry label/jurisdiction.
    """

    provider_id: str
    provider_label: str
    message_count: int = 0
    is_byok_count: int = 0
    platform_count: int = 0
    substitution_count: int = 0


@dataclass
class AttributionRollup:
    total_attributed: int = 0
    by_provider: list[ProviderAttributionCounts] = field(default_factory=list)


async def aggregate_attribution_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> AttributionRollup:
    """Group the caller's persisted per-message attribution by provider.

    Computed SOLELY from the `message.attribution` JSON already persisted on the
    caller's OWNED conversations — no new table, no message content. Grouping is
    done Python-side (SQLite-safe; the prod Postgres path is identical). Returns
    raw counts keyed by `providerId`; the route enriches each bucket with the
    live registry's label + jurisdiction (the only source of that fact).
    """
    stmt = (
        select(Message.attribution)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == user_id,
            Message.attribution.is_not(None),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()

    buckets: dict[str, ProviderAttributionCounts] = {}
    total = 0
    for attribution in rows:
        if not isinstance(attribution, dict):
            continue
        total += 1
        provider_id = attribution.get("providerId")
        provider_id = provider_id if isinstance(provider_id, str) and provider_id else "unknown"
        label = attribution.get("providerLabel")
        bucket = buckets.get(provider_id)
        if bucket is None:
            bucket = ProviderAttributionCounts(
                provider_id=provider_id,
                provider_label=label if isinstance(label, str) and label else provider_id,
            )
            buckets[provider_id] = bucket
        elif isinstance(label, str) and label and bucket.provider_label == provider_id:
            bucket.provider_label = label
        bucket.message_count += 1
        if attribution.get("isByok") is True:
            bucket.is_byok_count += 1
        else:
            bucket.platform_count += 1
        if attribution.get("substitution"):
            bucket.substitution_count += 1

    ordered = sorted(
        buckets.values(),
        key=lambda b: (-b.message_count, b.provider_id),
    )
    return AttributionRollup(total_attributed=total, by_provider=ordered)
