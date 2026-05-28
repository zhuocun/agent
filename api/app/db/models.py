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
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
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


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(UuidVariant, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
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
    temporary_by_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    training_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    send_on_enter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_expand_reasoning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
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
    role: Mapped[str] = mapped_column(String, nullable=False)
    parts: Mapped[list[dict[str, Any]]] = mapped_column(JsonVariant, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    attribution: Mapped[dict[str, Any] | None] = mapped_column(JsonVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_message_conversation_created", "conversation_id", "created_at"),
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="message_client_msg_uniq",
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

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="api_key_user_provider_uniq"),
    )


class UsageRollup(Base):
    __tablename__ = "usage_rollup"

    user_id: Mapped[UUID] = mapped_column(
        UuidVariant,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    is_byok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (PrimaryKeyConstraint("user_id", "period_start", name="usage_rollup_pk"),)
