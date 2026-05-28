"""User repository (M0 only needs `to_account_info`)."""

from __future__ import annotations

from app.db.models import User
from app.schemas.account import AccountInfo


def to_account_info(user: User, byok_enabled: bool = False) -> AccountInfo:
    """Map ORM User -> wire AccountInfo.

    For anonymous users we synthesize an empty email + "Free" plan. The FE
    renders these as a placeholder identity per plan §"Bootstrap".
    """
    return AccountInfo(
        name=user.name or "Guest",
        email=user.email or "",
        plan_label=user.plan_label,
        byok_enabled=byok_enabled,
        byok_masked_key=None,
    )
