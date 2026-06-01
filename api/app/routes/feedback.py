"""Message feedback routes (M2).

`POST /api/messages/:id/feedback` upserts (or deletes) the `vote` row for the
target message. Ownership is enforced by the conversation join — the message
must belong to a conversation owned by the caller, else 404 (not 403, never
distinguish from missing).

Wire shape:

```
{ "feedback": "up" | "down" | null }
```

`null` clears any existing vote. Returns 204.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import User
from app.db.repositories import analytics as analytics_repo
from app.db.repositories import votes as votes_repo
from app.db.session import get_db
from app.errors import not_found
from app.middleware.ratelimit import limiter
from app.schemas.common import CamelModel, Feedback

router = APIRouter(prefix="/api/messages", tags=["feedback"])


class FeedbackRequest(CamelModel):
    """Body for POST /api/messages/:id/feedback.

    `feedback=null` is the "clear vote" sentinel; "up"/"down" upsert the row.
    """

    feedback: Feedback | None = None


@router.post("/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_messages)
async def post_feedback(
    message_id: UUID,
    body: FeedbackRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Set, replace, or clear feedback on a message owned by the caller."""
    message = await votes_repo.message_owned_by(db, message_id, user.id)
    if message is None:
        raise not_found("message")
    if body.feedback is None:
        await votes_repo.clear(db, message_id)
    else:
        await votes_repo.upsert(db, message_id, body.feedback)
        await analytics_repo.record(
            db,
            user_id=user.id,
            event_type="feedback.submitted",
            properties={"messageId": str(message_id), "feedback": body.feedback},
        )
    return None
