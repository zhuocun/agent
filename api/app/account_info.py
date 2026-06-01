"""AccountInfo assembly shared by bootstrap/account/export routes."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import User
from app.db.repositories import api_keys, billing, usage, users
from app.providers.tiers import (
    active_byok_provider_id,
    get_provider_route,
    platform_provider_usable,
)
from app.schemas.account import AccountByokKey, AccountInfo

BYOK_ROUTABLE_PROVIDER_IDS = ("deepseek", "anthropic", "openai")
PLATFORM_ROUTABLE_PROVIDER_IDS = (*BYOK_ROUTABLE_PROVIDER_IDS, "fake")


def _provider_label(provider_id: str) -> str:
    route = get_provider_route(provider_id)
    return route.label if route is not None else provider_id


async def byok_key_metadata_for_user(
    db: AsyncSession,
    user: User,
) -> list[AccountByokKey]:
    """Return masked BYOK rows annotated with decryptability."""
    if user.is_anonymous:
        return []
    rows = await api_keys.list_for_user(db, user.id)
    metadata: list[AccountByokKey] = []
    for row in rows:
        usable = (
            await api_keys.get_decrypted_for_user(
                db,
                user_id=user.id,
                provider=row.provider,
            )
            is not None
        )
        metadata.append(
            AccountByokKey(
                provider_id=row.provider,
                provider_label=_provider_label(row.provider),
                masked_key=row.masked_key,
                usable=usable,
            )
        )
    return metadata


async def account_info_for_user(
    db: AsyncSession,
    user: User,
    settings: Settings | None = None,
) -> AccountInfo:
    """Build AccountInfo with legacy fields scoped to the active provider."""
    s = settings if settings is not None else get_settings()
    byok_keys = await byok_key_metadata_for_user(db, user)
    credit_balance_usd = await usage.get_credit_balance(db, user_id=user.id)
    billing_state = await billing.get_billing_state(
        db,
        user=user,
        settings=s,
        credit_balance_usd=credit_balance_usd,
    )
    active_provider = active_byok_provider_id(s)
    active_key = next(
        (
            key
            for key in byok_keys
            if key.provider_id == active_provider and key.usable
        ),
        None,
    )
    return users.to_account_info(
        user,
        byok_enabled=active_key is not None,
        byok_masked_key=active_key.masked_key if active_key is not None else None,
        byok_keys=byok_keys,
        billing=billing_state,
    )


async def usable_provider_ids_for_user(
    db: AsyncSession,
    user: User,
    settings: Settings | None = None,
) -> set[str]:
    """Providers callable by platform credentials or decryptable user BYOK."""
    s = settings if settings is not None else get_settings()
    usable = {
        provider_id
        for provider_id in PLATFORM_ROUTABLE_PROVIDER_IDS
        if platform_provider_usable(provider_id, s)
    }
    if user.is_anonymous:
        return usable

    for provider_id in BYOK_ROUTABLE_PROVIDER_IDS:
        if provider_id in usable:
            continue
        if (
            await api_keys.get_decrypted_for_user(
                db,
                user_id=user.id,
                provider=provider_id,
            )
            is not None
        ):
            usable.add(provider_id)
    return usable
