"""User repository."""

from __future__ import annotations

from app.db.models import User
from app.schemas.account import AccountInfo


def to_account_info(
    user: User,
    *,
    byok_enabled: bool = False,
    byok_masked_key: str | None = None,
) -> AccountInfo:
    """Map ORM User -> wire AccountInfo.

    For anonymous users we synthesize an empty email + "Free" plan. The FE
    renders these as a placeholder identity per plan §"Bootstrap".

    `byok_masked_key` is propagated as-is — the caller (bootstrap / BYOK
    routes) picks one of the user's BYOK rows' `masked_key` values to surface.
    Anonymous users always pass `byok_enabled=False`, so the masked key is
    suppressed below for safety even if the caller forgot.
    """
    return AccountInfo(
        name=user.name or "Guest",
        email=user.email or "",
        plan_label=user.plan_label,
        byok_enabled=byok_enabled,
        byok_masked_key=byok_masked_key if byok_enabled else None,
    )
