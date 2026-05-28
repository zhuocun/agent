"""Conversation routes.

M0: `GET /api/conversations/:id` only. 404 (not 403) on not-owned to avoid
leaking existence — uniform ownership check per plan §"Auth seam".
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.db.models import User
from app.db.repositories import conversations
from app.db.session import get_db
from app.errors import not_found
from app.schemas.conversation import Conversation as ConversationSchema

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/{conversation_id}", response_model=ConversationSchema)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    convo = await conversations.get_for_user(db, conversation_id, user.id)
    if convo is None:
        raise not_found("conversation")
    return convo
