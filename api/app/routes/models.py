"""Model & data-policy directory route (PRD 05 §4.5 / PRD 07 §5).

`GET /api/models/directory` — the browsable catalog of provider routes and
their tiers' capabilities + list prices, read entirely from the live registry
(`app.providers.tiers`). Anonymous-allowed: a guest can compare data policies
before committing to a route, exactly like the authenticated case.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependency import current_user
from app.db.models import User
from app.providers.tiers import list_provider_directory
from app.schemas.directory import ProviderDirectoryEntry

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/directory", response_model=list[ProviderDirectoryEntry])
async def get_model_directory(
    _user: User = Depends(current_user),
) -> list[ProviderDirectoryEntry]:
    """Return the full provider/data-policy directory from the registry.

    The catalog is registry-derived and identical for every caller, but we keep
    `current_user` so a guest session is minted on first hit (consistent with
    the rest of the anonymous-allowed surface) and the route shares the standard
    cookie/auth plumbing.
    """
    return list_provider_directory()


__all__ = ["router"]
