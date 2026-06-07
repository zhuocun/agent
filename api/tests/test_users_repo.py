"""Unit tests for app.db.repositories.users.

Covers:
- `delete_user_and_data`: full erasure with conversations, messages, votes,
  streams, tags, projects, memory facts, prompt templates, and audit events.
- `delete_user_and_data`: no-op when the user has no child data.
- `to_account_info`: anonymous user mapping, named user mapping, BYOK fields,
  billing state propagation.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnalyticsEvent,
    AuditEvent,
    Conversation,
    ConversationTag,
    MemoryFact,
    Message,
    Preferences,
    Project,
    PromptTemplate,
    Stream,
    Tag,
    User,
    Vote,
)
from app.db.repositories.users import delete_user_and_data, to_account_info
from app.schemas.account import AccountByokKey, BillingState

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# delete_user_and_data
# ---------------------------------------------------------------------------


async def test_delete_user_and_data_full_cascade(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Erasure deletes all owned child rows in FK-dependency order."""
    async with session_factory() as db:
        user = User(id=uuid4(), name="Doomed", is_anonymous=False, plan_label="Free")
        db.add(user)
        await db.flush()

        # Conversation with a message and a vote on it.
        convo = Conversation(
            id=uuid4(), user_id=user.id, title="c1", selected_tier_id="fast"
        )
        db.add(convo)
        await db.flush()
        msg = Message(
            id=uuid4(),
            conversation_id=convo.id,
            role="assistant",
            parts=[{"type": "text", "content": "hello"}],
        )
        db.add(msg)
        await db.flush()
        vote = Vote(message_id=msg.id, feedback="positive")
        db.add(vote)
        stream = Stream(
            id=uuid4(),
            conversation_id=convo.id,
            message_id=msg.id,
            status="done",
        )
        db.add(stream)

        # Tag + conversation_tag join.
        tag = Tag(id=uuid4(), user_id=user.id, name="work")
        db.add(tag)
        await db.flush()
        ct = ConversationTag(conversation_id=convo.id, tag_id=tag.id)
        db.add(ct)

        # Other child objects.
        project = Project(id=uuid4(), user_id=user.id, name="P1")
        db.add(project)
        fact = MemoryFact(id=uuid4(), user_id=user.id, content="fact1")
        db.add(fact)
        tmpl = PromptTemplate(
            id=uuid4(), user_id=user.id, title="T", body="B"
        )
        db.add(tmpl)
        prefs = Preferences(user_id=user.id)
        db.add(prefs)
        audit = AuditEvent(
            id=uuid4(), user_id=user.id, event_type="test.event", details={}
        )
        db.add(audit)
        analytics = AnalyticsEvent(
            id=uuid4(), user_id=user.id, event_type="page_view", properties={}
        )
        db.add(analytics)
        await db.flush()

        # Act
        await delete_user_and_data(db, user_id=user.id)
        await db.commit()

    # Assert: all rows gone.
    async with session_factory() as db:
        stmt = select(User).where(User.id == user.id)
        assert (await db.execute(stmt)).scalar_one_or_none() is None
        assert (await db.execute(select(Conversation))).scalars().all() == []
        assert (await db.execute(select(Message))).scalars().all() == []
        assert (await db.execute(select(Vote))).scalars().all() == []
        assert (await db.execute(select(Stream))).scalars().all() == []
        assert (await db.execute(select(Tag))).scalars().all() == []
        assert (await db.execute(select(ConversationTag))).scalars().all() == []
        assert (await db.execute(select(Project))).scalars().all() == []
        assert (await db.execute(select(MemoryFact))).scalars().all() == []
        assert (await db.execute(select(PromptTemplate))).scalars().all() == []
        assert (await db.execute(select(Preferences))).scalars().all() == []
        assert (await db.execute(select(AuditEvent))).scalars().all() == []
        assert (await db.execute(select(AnalyticsEvent))).scalars().all() == []


async def test_delete_user_no_conversations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Erasure works cleanly when the user has no conversations."""
    async with session_factory() as db:
        user = User(id=uuid4(), name="Lonely", is_anonymous=True, plan_label="Free")
        db.add(user)
        await db.flush()

        await delete_user_and_data(db, user_id=user.id)
        await db.commit()

    async with session_factory() as db:
        assert (await db.execute(select(User))).scalars().all() == []


# ---------------------------------------------------------------------------
# to_account_info
# ---------------------------------------------------------------------------


def test_to_account_info_anonymous_user() -> None:
    """Anonymous user gets synthesized Guest/empty-email identity."""
    user = User(
        id=uuid4(),
        name=None,
        email=None,
        is_anonymous=True,
        plan_label="Free",
    )
    info = to_account_info(user)
    assert info.name == "Guest"
    assert info.email == ""
    assert info.is_anonymous is True
    assert info.plan_label == "Free"
    assert info.byok_enabled is False
    assert info.byok_masked_key is None
    assert info.byok_keys == []


def test_to_account_info_named_user_with_byok() -> None:
    """Named user with BYOK keys surfaces the masked key and key list."""
    user = User(
        id=uuid4(),
        name="Alice",
        email="alice@example.com",
        is_anonymous=False,
        plan_label="Pro",
    )
    key = AccountByokKey(
        provider_id="deepseek",
        provider_label="DeepSeek",
        masked_key="sk-...xyz",
        usable=True,
    )
    info = to_account_info(
        user,
        byok_enabled=True,
        byok_masked_key="sk-...xyz",
        byok_keys=[key],
    )
    assert info.name == "Alice"
    assert info.email == "alice@example.com"
    assert info.is_anonymous is False
    assert info.plan_label == "Pro"
    assert info.byok_enabled is True
    assert info.byok_masked_key == "sk-...xyz"
    assert info.byok_keys == [key]


def test_to_account_info_byok_masked_key_suppressed_when_disabled() -> None:
    """Even if byok_masked_key is passed, it's suppressed when byok_enabled=False."""
    user = User(
        id=uuid4(),
        name="Bob",
        email="bob@example.com",
        is_anonymous=False,
        plan_label="Free",
    )
    info = to_account_info(user, byok_enabled=False, byok_masked_key="sk-...abc")
    assert info.byok_masked_key is None


def test_to_account_info_custom_billing_state() -> None:
    """Custom BillingState is propagated verbatim."""
    user = User(
        id=uuid4(),
        name="Pro User",
        email="pro@example.com",
        is_anonymous=False,
        plan_label="Pro",
    )
    billing = BillingState(plan_id="pro", plan_label="Pro", pro_enabled=True)
    info = to_account_info(user, billing=billing)
    assert info.billing == billing
    assert info.billing.pro_enabled is True


def test_to_account_info_default_billing_derived_from_plan_label() -> None:
    """When no billing is passed, it's derived from the user's plan_label."""
    user = User(
        id=uuid4(),
        name="Frugal",
        email="frugal@example.com",
        is_anonymous=False,
        plan_label="Free",
    )
    info = to_account_info(user)
    assert info.billing.plan_id == "free"
    assert info.billing.pro_enabled is False

    pro_user = User(
        id=uuid4(),
        name="Spender",
        email="spender@example.com",
        is_anonymous=False,
        plan_label="Pro",
    )
    pro_info = to_account_info(pro_user)
    assert pro_info.billing.plan_id == "pro"
    assert pro_info.billing.pro_enabled is True
