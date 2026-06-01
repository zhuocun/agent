"""User repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalyticsEvent,
    ApiKey,
    AuditEvent,
    BillingCustomer,
    BillingEntitlement,
    Conversation,
    Message,
    Preferences,
    Session,
    Stream,
    UsageCreditLedger,
    UsageRollup,
    User,
    Vote,
)
from app.schemas.account import AccountByokKey, AccountInfo, BillingState


async def delete_user_and_data(db: AsyncSession, *, user_id: UUID) -> None:
    """Permanently erase the user and ALL data owned by them (right to erasure).

    Deletes in FK-dependency order with explicit statements, mirroring
    `conversations.delete_for_user`. SQLite (tests) does not enforce FK
    cascades by default (no `PRAGMA foreign_keys=ON`), so we cannot rely on the
    DB to fan out the delete — each child table is removed explicitly. On
    Postgres the `ON DELETE CASCADE` chains would also fire; the explicit
    deletes here are idempotent there too.

    Order: vote (by message id) -> stream (by conversation id) ->
    message (by conversation id) -> conversation -> analytics_event ->
    api_key / usage ledgers / preferences / session -> audit purge -> user.
    Flush only; the caller (request dependency) owns the commit.
    """
    convo_id_stmt = select(Conversation.id).where(Conversation.user_id == user_id)
    convo_ids = (await db.execute(convo_id_stmt)).scalars().all()
    if convo_ids:
        msg_id_stmt = select(Message.id).where(Message.conversation_id.in_(convo_ids))
        msg_ids = (await db.execute(msg_id_stmt)).scalars().all()
        if msg_ids:
            await db.execute(delete(Vote).where(Vote.message_id.in_(msg_ids)))
        # Drop stream rows before their parent conversation/message. The
        # `stream` table postdates the original erasure code; its
        # `conversation_id` is ON DELETE CASCADE, but we deliberately do NOT
        # rely on DB cascade (SQLite tests have no `PRAGMA foreign_keys=ON`),
        # so it must be removed explicitly or rows orphan on SQLite.
        await db.execute(delete(Stream).where(Stream.conversation_id.in_(convo_ids)))
        await db.execute(delete(Message).where(Message.conversation_id.in_(convo_ids)))
    await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.user_id == user_id))
    await db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
    await db.execute(delete(BillingEntitlement).where(BillingEntitlement.user_id == user_id))
    await db.execute(delete(BillingCustomer).where(BillingCustomer.user_id == user_id))
    await db.execute(delete(UsageCreditLedger).where(UsageCreditLedger.user_id == user_id))
    await db.execute(delete(UsageRollup).where(UsageRollup.user_id == user_id))
    await db.execute(delete(Preferences).where(Preferences.user_id == user_id))
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()


def to_account_info(
    user: User,
    *,
    byok_enabled: bool = False,
    byok_masked_key: str | None = None,
    byok_keys: list[AccountByokKey] | None = None,
    billing: BillingState | None = None,
) -> AccountInfo:
    """Map ORM User -> wire AccountInfo.

    For anonymous users we synthesize an empty email + "Free" plan. The FE
    renders these as a placeholder identity per plan §"Bootstrap".

    `byok_masked_key` is propagated as-is — the caller (bootstrap / BYOK
    routes) picks one of the user's BYOK rows' `masked_key` values to surface.
    Anonymous users always pass `byok_enabled=False`, so the masked key is
    suppressed below for safety even if the caller forgot.
    """
    return AccountInfo(
        name=user.name or "Guest",
        email=user.email or "",
        is_anonymous=user.is_anonymous,
        plan_label=user.plan_label,
        billing=billing
        or BillingState(
            plan_id="pro" if user.plan_label == "Pro" else "free",
            plan_label=user.plan_label,
            pro_enabled=user.plan_label == "Pro",
        ),
        byok_enabled=byok_enabled,
        byok_masked_key=byok_masked_key if byok_enabled else None,
        byok_keys=byok_keys or [],
    )
