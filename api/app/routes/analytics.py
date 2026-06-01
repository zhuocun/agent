"""First-party analytics endpoint.

Only accepts a tight set of frontend-originated funnel events that the backend
cannot infer. Payloads are scalar-only and content-free by schema.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import User
from app.db.repositories import analytics
from app.db.session import get_db
from app.middleware.ratelimit import limiter
from app.schemas.analytics import AnalyticsEventRequest

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_analytics)
async def post_analytics_event(
    body: AnalyticsEventRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await analytics.record(
        db,
        user_id=user.id,
        event_type=body.event_type,
        properties=body.properties,
    )
    return None


__all__ = ["router"]
