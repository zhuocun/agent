"""Public-by-link share route.

`GET /api/share/{share_token}` — the ONE public, unauthenticated read in the
API. It returns a cost-stripped snapshot of a shared conversation (messages +
model attribution, never per-message cost) per PRD 01 §4.10 / PRD 05 §4.3 /
PRD 07 §6.4.

Deliberately NOT under the `/api/conversations` router and NOT depending on
`current_user`: this is public-by-link, so adding the auth dependency would
mint a fresh anonymous user on every anonymous reader's hit and gate the read
behind a cookie. The cost strip is structural — `get_public_by_share_token`
builds `PublicConversation` / `PublicMessage` / `PublicAttribution`, none of
which have a field for cost, so cost cannot serialize even by accident.

Unknown / revoked token -> 404 (same envelope as everywhere else), never
leaking which tokens once existed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import conversations as conversations_repo
from app.db.session import get_db
from app.errors import not_found
from app.schemas.share import PublicConversation

router = APIRouter(prefix="/api/share", tags=["share"])


@router.get("/{share_token}", response_model=PublicConversation)
async def get_shared_conversation(
    share_token: str,
    db: AsyncSession = Depends(get_db),
) -> PublicConversation:
    """Return the cost-stripped public view for a share token, or 404.

    No auth: public-by-link. The token IS the capability — possession grants
    read. Unknown / revoked token -> 404 so revocation is observable and the
    set of live tokens never leaks.
    """
    public = await conversations_repo.get_public_by_share_token(db, share_token)
    if public is None:
        raise not_found("conversation")
    return public
