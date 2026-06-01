"""Account / BYOK routes (M3).

- `PUT /api/account/byok` -- upsert the user's BYOK key for a provider.
- `DELETE /api/account/byok/{provider}` -- remove the user's BYOK key.

Both are 403 ANONYMOUS_REQUIRED for anonymous users (plan §"BYOK gating" /
PRD 04 §5.2). The PUT body is validated by Pydantic; an empty `apiKey` after
trimming, or one shorter than 8 chars, is rejected as 400 INVALID_INPUT.

Returns the updated `AccountInfo` so the FE doesn't need a follow-up GET.
DELETE is idempotent -- removing a non-existent row returns 200 with the
current account state (rather than 404), so the FE's clear-key button never
surfaces a spurious "not found" toast.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import User
from app.db.repositories import api_keys, audit_events, users
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope
from app.middleware.ratelimit import limiter
from app.providers.tiers import active_byok_provider_id
from app.schemas.account import AccountInfo
from app.schemas.common import CamelModel

router = APIRouter(prefix="/api/account", tags=["account"])


_MIN_API_KEY_LEN = 8


class ByokPutRequest(CamelModel):
    """Body for PUT /api/account/byok.

    `provider` is a free-form string today (matches the table column shape).
    Future tightening: a `Literal["anthropic", ...]` once we ship multi-
    provider routing.
    """

    provider: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


def _anonymous_required() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="ANONYMOUS_REQUIRED",
            severity="error",
            title="Sign in required",
            body="Bring your own API key requires a signed-in account.",
        ),
        status.HTTP_403_FORBIDDEN,
    )


def _invalid_input(body: str) -> AppError:
    return AppError(
        ErrorEnvelope(
            code="INVALID_INPUT",
            severity="error",
            title="Invalid input",
            body=body,
        ),
        status.HTTP_400_BAD_REQUEST,
    )


async def _current_account_info(
    db: AsyncSession,
    user: User,
) -> AccountInfo:
    """Recompute AccountInfo from current DB state -- shared by PUT/DELETE."""
    active_provider = active_byok_provider_id(get_settings())
    row = await api_keys.get_for_user(db, user_id=user.id, provider=active_provider)
    byok_enabled = (not user.is_anonymous) and row is not None
    masked = row.masked_key if byok_enabled and row is not None else None
    return users.to_account_info(user, byok_enabled=byok_enabled, byok_masked_key=masked)


@router.put("/byok", response_model=AccountInfo)
@limiter.limit(lambda: get_settings().rate_limit_byok)
async def put_byok(
    body: ByokPutRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountInfo:
    """Encrypt and store the user's BYOK key. 403 for anonymous users."""
    if user.is_anonymous:
        raise _anonymous_required()
    trimmed = body.api_key.strip()
    if len(trimmed) < _MIN_API_KEY_LEN:
        raise _invalid_input(f"apiKey must be at least {_MIN_API_KEY_LEN} characters.")
    await api_keys.upsert(
        db,
        user_id=user.id,
        provider=body.provider.strip(),
        raw_api_key=trimmed,
    )
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="byok.upsert",
        details={"provider": body.provider.strip()},
    )
    return await _current_account_info(db, user)


@router.delete("/byok/{provider}", response_model=AccountInfo)
@limiter.limit(lambda: get_settings().rate_limit_byok)
async def delete_byok(
    provider: str,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountInfo:
    """Remove the user's BYOK key for `provider`. Idempotent.

    Returns 200 with the updated AccountInfo even if the row didn't exist
    (per plan §"DELETE /api/account/byok/:provider" -- "Returns updated
    AccountInfo. Idempotent."). Anonymous users get 403 regardless.
    """
    if user.is_anonymous:
        raise _anonymous_required()
    removed = await api_keys.delete(db, user_id=user.id, provider=provider.strip())
    await audit_events.record(
        db,
        user_id=user.id,
        event_type="byok.revoke",
        details={"provider": provider.strip(), "removed": removed},
    )
    return await _current_account_info(db, user)
