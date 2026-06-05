"""Public platform-status route (PRD 08 §10).

`GET /api/status` — PUBLIC, unauthenticated (mounted like the share route, with
NO `current_user` dependency so an anonymous status check never mints a cookie).
Derives a calm platform-level health verdict from recent `Stream` telemetry via
one cheap COUNT query.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories import streams as streams_repo
from app.db.session import get_db
from app.schemas.status import PlatformStatus

router = APIRouter(tags=["status"])


@router.get("/api/status", response_model=PlatformStatus)
async def get_platform_status(
    db: AsyncSession = Depends(get_db),
) -> PlatformStatus:
    """Return the public platform health summary.

    `operational` by default; `degraded` only when the recent window holds a
    meaningful sample (>= `status_min_sample`) AND the error ratio EXCEEDS
    `status_error_ratio`. No auth: this is a public, content-free read.
    """
    settings = get_settings()
    health = await streams_repo.recent_health(
        db, window_seconds=settings.status_window_seconds
    )
    total = health["total"]
    errors = health["errors"]
    degraded = (
        total >= settings.status_min_sample
        and total > 0
        and (errors / total) > settings.status_error_ratio
    )
    return PlatformStatus(
        status="degraded" if degraded else "operational",
        window_seconds=settings.status_window_seconds,
        sample_size=total,
        error_count=errors,
        updated_at=datetime.now(UTC).isoformat(),
    )


__all__ = ["router"]
