"""SQLAlchemy ORM models.

Matches the plan §"Data model" sketch. Snake_case columns; the Pydantic layer
emits camelCase to the wire. `JsonVariant` / `UuidVariant` resolve to JSONB +
PG UUID on Postgres, JSON + 36-char string on SQLite (tests).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonVariant, UuidVariant


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="Guest")
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    plan_label: Mapped[str] = mapped_column(String, nullable=False, default="Free")
    # bcrypt digest set during /api/auth/upgrade. NULL for anonymous users and
    # for upgraded users who chose magic-link / passkey (both M4+); the column
    # exists today so the auth-upgrade route can land without a follow-up
    # migration when passwords ship.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Post-M4: partial UNIQUE INDEX -- two non-NULL `email` values cannot
    # coexist. NULL `email` (anonymous users) is excluded from the index, so
    # multiple anon rows live side by side. SQLite + Postgres both treat NULL
    # values in a UNIQUE index as distinct, but the explicit partial predicate
    # makes the intent obvious and matches what the migration emits.
    __table_args__ = (
        Index(
            "ix_users_email_unique",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
            sqlite_where=text("email IS NOT NULL"),
        ),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Preferences(Base):
    """Per-user preferences. PK == user_id (one row per user)."""

    __tablename__ = "preferences"

    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    default_tier_id: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    temporary_by_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    send_on_enter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_expand_reasoning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telemetry_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    custom_instructions: Mapped[str] = mapped_column(
        String(4000), nullable=False, default="", server_default=text("''")
    )
    # NULL means "retain forever"; non-NULL values are constrained by the API
    # schema/repository to the currently supported short windows.
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String, nullable=False, default="New chat")
    selected_tier_id: Mapped[str] = mapped_column(String, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Public-by-link share token. NULL = unshared (the default); a non-NULL
    # URL-safe random token = shared. Anyone holding the token can read a
    # cost-stripped snapshot of the conversation via GET /api/share/{token}
    # without authenticating. The truthiness of this column IS the share state
    # — there is no separate boolean flag, so revoke is simply "set back to
    # NULL". The UNIQUE index makes the token an unguessable primary lookup key
    # and guards against the astronomically unlikely random collision.
    share_token: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "conversation_user_pinned_updated_idx",
            "user_id",
            "pinned",
            "updated_at",
        ),
        Index(
            "ix_conversation_share_token",
            "share_token",
            unique=True,
        ),
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_message_id: Mapped[UUID | None] = mapped_column(UuidVariant, nullable=True)
    request_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JsonVariant, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    parts: Mapped[list[dict[str, Any]]] = mapped_column(JsonVariant, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    attribution: Mapped[dict[str, Any] | None] = mapped_column(JsonVariant, nullable=True)
    # Per-turn cost in USD. Mirrors `attribution.costUsd` (the breakdown
    # subtotal + session surcharge) so the cost ledger can be queried without
    # re-parsing the JSON attribution blob. NULL on legacy rows written before
    # the 0006 migration and on user rows (cost is an assistant-turn concept).
    # Numeric(12,6) for fixed-precision money: Postgres (prod) stores it as an
    # exact NUMERIC so the SQL-side `cost_usd + excluded.cost_usd` accumulation
    # is exact decimal arithmetic — no binary-float ULP drift near the budget
    # `>=` cap when summed over many turns. `asdecimal=False` keeps SQLAlchemy
    # returning Python floats (no Decimal ripple through pricing/handler/tests).
    # SQLite (tests) stores NUMERIC as REAL, so tests don't get exactness; that
    # is fine because prod is Postgres.
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=True)
    # Post-M4: explicit reply pairing. On assistant rows this points at the
    # user message whose reply this is, so `_maybe_replay` can resolve via a
    # single indexed lookup instead of pair-by-index. NULL on legacy rows
    # (pre-migration data) and on user rows themselves.
    responds_to_message_id: Mapped[UUID | None] = mapped_column(
        UuidVariant,
        ForeignKey("message.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_message_conversation_created", "conversation_id", "created_at"),
        Index("ix_message_responds_to", "responds_to_message_id"),
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="message_client_msg_uniq",
        ),
    )


class Stream(Base):
    """Durable record of a streaming turn (PRD 04 §5.1).

    One row per streaming turn on a non-temporary conversation. Tracks the
    lifecycle `active -> done | stopped | error` and links to the in-progress /
    final assistant `message` (NULL until the assistant row is persisted). This
    is the durable counterpart to the in-process stop signal
    (`app.streaming.stop_registry`): the registry is the live cancel channel,
    this table is the persisted intent + status.

    Resumable replay is OUT of scope today, but the schema is deliberately
    shaped to support it later: the active row per conversation plus its
    `message_id` is enough to resume / re-attach a stream once that lands.
    """

    __tablename__ = "stream"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The in-progress / final assistant message. NULL until the assistant row is
    # persisted (stop-path / terminal-success set it). SET NULL on delete so a
    # purged message doesn't dangle the pointer.
    message_id: Mapped[UUID | None] = mapped_column(
        UuidVariant,
        ForeignKey("message.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Lifecycle: one of "active" | "done" | "stopped" | "error".
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active", default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_stream_conversation", "conversation_id"),
        Index("ix_stream_status", "status"),
        # Concurrency guard: at most ONE active stream per conversation. A
        # partial UNIQUE INDEX over `conversation_id` restricted to
        # `status = 'active'` rows means a concurrent double-submit /
        # double-regenerate that both try to open an active stream loses one
        # side to an IntegrityError (mapped to 409 by the repo + route).
        # Terminal rows (done / stopped / error) are excluded by the predicate,
        # so the legitimate sequential case — a new turn after the prior stream
        # finished — is always allowed. Both dialects get the predicate: SQLite
        # (tests, via Base.metadata.create_all) supports partial indexes (3.8+),
        # Postgres (prod) is the real enforcer. Matches the partial-index style
        # of `ix_users_email_unique` above.
        Index(
            "ix_stream_conversation_active_unique",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )


class Vote(Base):
    __tablename__ = "vote"

    message_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("message.id", ondelete="CASCADE"),
        primary_key=True,
    )
    feedback: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApiKey(Base):
    __tablename__ = "api_key"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    ciphertext: Mapped[str] = mapped_column(String, nullable=False)
    masked_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "provider", name="api_key_user_provider_uniq"),)


class UsageRollup(Base):
    __tablename__ = "usage_rollup"

    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Accumulated USD cost for the period. Parallel to `used` (the integer
    # per-turn counter the FE meter renders raw); `cost_usd` is the
    # cost-ledger axis that cost-based budget enforcement reads. Kept separate
    # so the FE wire contract for `used` is unchanged. `server_default="0"`
    # backfills legacy rows to a non-NULL zero.
    # Numeric(12,6) for fixed-precision money: Postgres (prod) stores exact
    # NUMERIC and accumulates exactly via SQL `cost_usd + excluded.cost_usd`,
    # so the period total never drifts by binary-float ULPs near the budget
    # cap. `asdecimal=False` keeps SQLAlchemy returning Python floats so the
    # budget gate and pricing math see plain floats. SQLite (tests) stores
    # NUMERIC as REAL — no exactness there, fine since prod is Postgres.
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6, asdecimal=False),
        nullable=False,
        server_default=text("0"),
        default=0.0,
    )
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    is_byok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (PrimaryKeyConstraint("user_id", "period_start", name="usage_rollup_pk"),)


class UsageCreditLedger(Base):
    __tablename__ = "usage_credit_ledger"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Signed USD amount. Grants and positive adjustments add credits; platform
    # debits and negative adjustments consume them. Payment-provider state is
    # deliberately absent from this primitive.
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    amount_usd: Mapped[float] = mapped_column(
        Numeric(12, 6, asdecimal=False),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('grant', 'platform_debit', 'adjustment')",
            name="ck_usage_credit_ledger_entry_type",
        ),
        CheckConstraint(
            "("
            "entry_type = 'grant' AND amount_usd > 0"
            ") OR ("
            "entry_type = 'platform_debit' AND amount_usd < 0"
            ") OR ("
            "entry_type = 'adjustment' AND amount_usd <> 0"
            ")",
            name="ck_usage_credit_ledger_amount_sign",
        ),
        Index(
            "ix_usage_credit_ledger_user_created",
            "user_id",
            "created_at",
        ),
    )


class BillingCustomer(Base):
    __tablename__ = "billing_customer"

    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String, primary_key=True)
    external_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_customer_id",
            name="billing_customer_provider_external_uniq",
        ),
        Index("ix_billing_customer_external", "provider", "external_customer_id"),
    )


class BillingEntitlement(Base):
    __tablename__ = "billing_entitlement"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    plan_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    external_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    external_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    external_event_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("plan_id IN ('pro')", name="ck_billing_entitlement_plan"),
        CheckConstraint(
            "status IN ("
            "'active', 'trialing', 'past_due', 'canceled', 'incomplete', "
            "'incomplete_expired', 'unpaid', 'paused'"
            ")",
            name="ck_billing_entitlement_status",
        ),
        Index("ix_billing_entitlement_user", "user_id", "plan_id", "status"),
        Index(
            "ix_billing_entitlement_external_subscription",
            "provider",
            "external_subscription_id",
            unique=True,
        ),
    )


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_event"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonVariant, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalyticsEvent(Base):
    """First-party product telemetry owned by the user.

    This is intentionally separate from `audit_event`: analytics rows are
    exportable and erased with the account, while audit rows cover sensitive
    account operations and may retain minimal non-user operational records.
    """

    __tablename__ = "analytics_event"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JsonVariant, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_analytics_event_user_created", "user_id", "created_at"),
        Index("ix_analytics_event_type_created", "event_type", "created_at"),
        Index(
            "ix_analytics_first_success_user_unique",
            "user_id",
            unique=True,
            postgresql_where=text("event_type = 'activation.first_successful_response'"),
            sqlite_where=text("event_type = 'activation.first_successful_response'"),
        ),
    )


class BillingFulfillment(Base):
    __tablename__ = "billing_fulfillment"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    fulfillment_type: Mapped[str] = mapped_column(String, nullable=False)
    object_id: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "fulfillment_type",
            "object_id",
            name="billing_fulfillment_provider_type_object_uniq",
        ),
    )


class AuditEvent(Base):
    """Write-only audit trail for sensitive account events.

    `user_id` is nullable with SET NULL so account deletion can retain a minimal
    operational audit trail without keeping the deleted account row alive.
    """

    __tablename__ = "audit_event"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JsonVariant, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_event_user_created", "user_id", "created_at"),
        Index("ix_audit_event_type_created", "event_type", "created_at"),
    )
