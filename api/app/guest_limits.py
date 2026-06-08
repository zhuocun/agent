"""Anonymous-guest send limits (PRD 08 §5.4, T07/T06).

Two gates, both for ANONYMOUS users on PLATFORM-key turns (a guest never has a
BYOK key, so a BYOK turn is never gated here):

- **Hard sign-up wall** (`PLATFORM_GUEST_LIMIT`): once a guest has sent
  `GUEST_MESSAGE_LIMIT` persisted messages, the next send is refused. The route
  raises the envelope; this module only counts.
- **Premium-allotment downgrade** (`PLATFORM_GUEST_DOWNGRADE`): once a guest has
  been served `GUEST_PREMIUM_MESSAGE_LIMIT` premium-tier (non-`fast`) turns, the
  route transparently downgrades the next premium request to `fast` with a
  visible substitution callout (never a silent swap).

Counts are derived from persisted rows (a "message count query") scoped to the
guest's own conversations:

- guest message count = the guest's `role="user"` messages.
- guest premium count = the guest's `role="assistant"` messages whose served
  tier (`attribution.servedTierId`) is a premium tier (anything but `fast`).

Temporary chats persist nothing, so they neither grow nor are gated by these
counters — that is the deliberate escape hatch, consistent with how temp chats
already skip persistence elsewhere.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message
from app.schemas.common import ModelTierId

# Premium = any served tier that is NOT the cheap `fast` route. `auto` never
# appears as a SERVED tier (it resolves to a concrete tier in attribution), so
# the served-tier comparison only ever sees fast/smart/pro.
_FAST_TIER: ModelTierId = "fast"


def is_premium_tier(tier_id: str) -> bool:
    """Whether a tier counts against the guest premium allotment."""
    return tier_id != _FAST_TIER


async def count_guest_messages(db: AsyncSession, user_id: UUID) -> int:
    """Count the guest's persisted `user` messages across their conversations."""
    stmt = (
        select(func.count())
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id, Message.role == "user")
    )
    return int((await db.execute(stmt)).scalar_one())


async def count_guest_premium_messages(db: AsyncSession, user_id: UUID) -> int:
    """Count the guest's assistant turns served by a premium (non-`fast`) tier.

    `attribution.servedTierId` lives in the JSON attribution blob, so the
    premium decision is finished in Python (SQLite, used in tests, has no SQL
    JSON ops). A guest is bounded by `GUEST_MESSAGE_LIMIT` rows, so this scan is
    small.
    """
    stmt = (
        select(Message.attribution)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Message.role == "assistant",
            Message.attribution.is_not(None),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    count = 0
    for attribution in rows:
        if not isinstance(attribution, dict):
            continue
        served = attribution.get("servedTierId")
        if isinstance(served, str) and is_premium_tier(served):
            count += 1
    return count
