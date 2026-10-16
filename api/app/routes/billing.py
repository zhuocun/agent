"""Billing routes: Checkout, customer portal, and webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import current_user
from app.config import Settings, get_settings
from app.db.models import User
from app.db.repositories import billing as billing_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_db
from app.errors import AppError, ErrorAction, ErrorEnvelope
from app.schemas.billing import (
    BillingCheckoutRequest,
    BillingSessionResponse,
    BillingWebhookResponse,
)

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

_STRIPE_API_VERSION = "2025-05-28.basil"
_WEBHOOK_TOLERANCE_SECONDS = 300
_HANDLED_EVENT_TYPES = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


def _billing_error(
    *,
    code: str,
    title: str,
    body: str,
    status_code: int,
) -> AppError:
    return AppError(
        ErrorEnvelope(code=code, severity="error", title=title, body=body),
        status_code,
    )


def _sign_in_required() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="SIGN_IN_REQUIRED",
            severity="warning",
            title="Sign in required",
            body="Create an account or sign in before starting billing.",
            actions=[ErrorAction(label="Open settings", kind="open_settings")],
        ),
        status.HTTP_401_UNAUTHORIZED,
    )


def _require_registered_user(user: User) -> None:
    if user.is_anonymous:
        raise _sign_in_required()


def _require_backend(settings: Settings) -> billing_repo.ProviderId:
    if settings.billing_backend not in ("stripe", "fake"):
        raise _billing_error(
            code="BILLING_UNAVAILABLE",
            title="Billing unavailable",
            body="Billing is not configured for this deployment.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return billing_repo.parse_provider(settings.billing_backend)


def _require_stripe_secret(settings: Settings) -> str:
    if not settings.stripe_secret_key:
        raise _billing_error(
            code="BILLING_MISCONFIGURED",
            title="Billing misconfigured",
            body="Stripe billing is enabled but the API key is missing.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return settings.stripe_secret_key


async def _stripe_post(
    settings: Settings,
    path: str,
    data: dict[str, str],
) -> dict[str, Any]:
    key = _require_stripe_secret(settings)
    try:
        async with httpx.AsyncClient(base_url=settings.stripe_api_base_url) as client:
            response = await client.post(
                path,
                data=data,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Stripe-Version": _STRIPE_API_VERSION,
                },
                timeout=15.0,
            )
    except httpx.RequestError as exc:
        raise _billing_error(
            code="BILLING_PROVIDER_ERROR",
            title="Billing provider error",
            body="The billing provider could not be reached.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from exc
    try:
        parsed = response.json()
    except ValueError as exc:
        raise _billing_error(
            code="BILLING_PROVIDER_ERROR",
            title="Billing provider error",
            body="The billing provider returned an unexpected response.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from exc
    if not isinstance(parsed, dict):
        raise _billing_error(
            code="BILLING_PROVIDER_ERROR",
            title="Billing provider error",
            body="The billing provider returned an unexpected response.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    if response.status_code >= 400:
        raise _billing_error(
            code="BILLING_PROVIDER_ERROR",
            title="Billing provider error",
            body="The billing provider rejected the request.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return cast(dict[str, Any], parsed)


def _fake_url(kind: str, user_id: UUID) -> str:
    return f"/settings?billing=fake-{kind}&user={user_id}"


@router.post("/checkout", response_model=BillingSessionResponse)
async def create_checkout_session(
    body: BillingCheckoutRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> BillingSessionResponse:
    _require_registered_user(user)
    settings = get_settings()
    provider = _require_backend(settings)
    if provider == "fake":
        return BillingSessionResponse(url=_fake_url(body.kind, user.id))

    customer = await billing_repo.get_or_repair_customer_for_user(
        db,
        user_id=user.id,
        provider=provider,
    )
    data: dict[str, str] = {
        "success_url": settings.billing_success_url,
        "cancel_url": settings.billing_cancel_url,
        "client_reference_id": str(user.id),
        "metadata[user_id]": str(user.id),
        "metadata[purpose]": body.kind,
        "line_items[0][quantity]": "1",
    }
    if customer is not None:
        data["customer"] = customer.external_customer_id
    elif user.email:
        data["customer_email"] = user.email

    if body.kind == "pro_subscription":
        if not settings.stripe_pro_price_id:
            raise _billing_error(
                code="BILLING_MISCONFIGURED",
                title="Billing misconfigured",
                body="The Pro subscription price is not configured.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        data.update(
            {
                "mode": "subscription",
                "line_items[0][price]": settings.stripe_pro_price_id,
                "subscription_data[metadata][user_id]": str(user.id),
            }
        )
    else:
        if not settings.stripe_credit_price_id:
            raise _billing_error(
                code="BILLING_MISCONFIGURED",
                title="Billing misconfigured",
                body="The credit purchase price is not configured.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        data.update(
            {
                "mode": "payment",
                "line_items[0][price]": settings.stripe_credit_price_id,
                "metadata[credit_amount_usd]": str(settings.stripe_credit_amount_usd),
            }
        )
        if customer is None:
            data["customer_creation"] = "always"

    session = await _stripe_post(settings, "/v1/checkout/sessions", data)
    url = session.get("url")
    if not isinstance(url, str) or not url:
        raise _billing_error(
            code="BILLING_PROVIDER_ERROR",
            title="Billing provider error",
            body="The billing provider did not return a checkout URL.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return BillingSessionResponse(url=url)


@router.post("/portal", response_model=BillingSessionResponse)
async def create_customer_portal_session(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> BillingSessionResponse:
    _require_registered_user(user)
    settings = get_settings()
    provider = _require_backend(settings)
    customer = await billing_repo.get_or_repair_customer_for_user(
        db,
        user_id=user.id,
        provider=provider,
    )
    if customer is None:
        raise _billing_error(
            code="BILLING_CUSTOMER_REQUIRED",
            title="No billing customer",
            body="Start checkout before opening the customer portal.",
            status_code=status.HTTP_409_CONFLICT,
        )
    if provider == "fake":
        return BillingSessionResponse(url=_fake_url("portal", user.id))

    session = await _stripe_post(
        settings,
        "/v1/billing_portal/sessions",
        {
            "customer": customer.external_customer_id,
            "return_url": settings.billing_portal_return_url,
        },
    )
    url = session.get("url")
    if not isinstance(url, str) or not url:
        raise _billing_error(
            code="BILLING_PROVIDER_ERROR",
            title="Billing provider error",
            body="The billing provider did not return a portal URL.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    return BillingSessionResponse(url=url)


def _verify_stripe_signature(
    *,
    payload: bytes,
    signature_header: str | None,
    webhook_secret: str | None,
) -> None:
    if not webhook_secret:
        raise _billing_error(
            code="BILLING_MISCONFIGURED",
            title="Billing misconfigured",
            body="Stripe billing is enabled but the webhook secret is missing.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not signature_header:
        raise _billing_error(
            code="INVALID_WEBHOOK_SIGNATURE",
            title="Invalid webhook signature",
            body="Missing Stripe-Signature header.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    pieces: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        pieces.setdefault(key, []).append(value)
    timestamp_values = pieces.get("t") or []
    signatures = pieces.get("v1") or []
    if not timestamp_values or not signatures:
        raise _billing_error(
            code="INVALID_WEBHOOK_SIGNATURE",
            title="Invalid webhook signature",
            body="Stripe-Signature is missing timestamp or v1 signature.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        timestamp = int(timestamp_values[0])
    except ValueError as exc:
        raise _billing_error(
            code="INVALID_WEBHOOK_SIGNATURE",
            title="Invalid webhook signature",
            body="Stripe-Signature timestamp is invalid.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if abs(time.time() - timestamp) > _WEBHOOK_TOLERANCE_SECONDS:
        raise _billing_error(
            code="INVALID_WEBHOOK_SIGNATURE",
            title="Invalid webhook signature",
            body="Stripe-Signature timestamp is outside the allowed tolerance.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise _billing_error(
            code="INVALID_WEBHOOK_SIGNATURE",
            title="Invalid webhook signature",
            body="Stripe-Signature verification failed.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _object_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("id"), str):
        return cast(str, value["id"])
    return None


def _timestamp_to_datetime(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and math.isfinite(value):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            _log.warning("billing.timestamp_invalid", value=repr(value))
            return None
    return None


def _metadata_user_id(metadata: Any) -> UUID | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("user_id")
    if not isinstance(raw, str):
        return None
    try:
        return UUID(raw)
    except ValueError:
        _log.warning("billing.metadata_user_id_invalid", raw_value=raw)
        return None


def _credit_amount_usd(raw: Any, *, fallback: float) -> float | None:
    try:
        amount = float(raw) if raw is not None else fallback
    except (TypeError, ValueError):
        _log.warning("billing.credit_amount_invalid", raw_value=repr(raw), fallback=fallback)
        amount = fallback
    if amount <= 0:
        amount = fallback
    return amount if amount > 0 else None


async def _user_id_for_payload(
    db: AsyncSession,
    *,
    provider: billing_repo.ProviderId,
    obj: dict[str, Any],
) -> UUID | None:
    metadata_user_id = _metadata_user_id(obj.get("metadata"))
    customer_id = _object_id(obj.get("customer"))
    if customer_id is None:
        return metadata_user_id
    mapped_user_id = await billing_repo.get_user_id_for_customer(
        db,
        provider=provider,
        external_customer_id=customer_id,
    )
    return mapped_user_id if mapped_user_id is not None else metadata_user_id


async def _handle_checkout_completed(
    db: AsyncSession,
    *,
    provider: billing_repo.ProviderId,
    event_id: str,
    obj: dict[str, Any],
    settings: Settings,
) -> None:
    user_id = await _user_id_for_payload(db, provider=provider, obj=obj)
    if user_id is None:
        return
    customer_id = _object_id(obj.get("customer"))
    if customer_id:
        await billing_repo.upsert_customer(
            db,
            user_id=user_id,
            provider=provider,
            external_customer_id=customer_id,
        )

    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    purpose = cast(dict[str, Any], metadata).get("purpose")
    if purpose == "pro_subscription":
        return
    elif purpose == "credit_purchase":
        payment_status = obj.get("payment_status")
        if payment_status != "paid":
            return
        amount_usd = _credit_amount_usd(
            cast(dict[str, Any], metadata).get("credit_amount_usd"),
            fallback=settings.stripe_credit_amount_usd,
        )
        if amount_usd is None:
            return
        session_id = _object_id(obj.get("id"))
        if session_id is None:
            return
        should_fulfill = await billing_repo.mark_fulfillment_processing(
            db,
            provider=provider,
            fulfillment_type="checkout.session.completed:credit_purchase",
            object_id=session_id,
            event_id=event_id,
        )
        if not should_fulfill:
            return
        await usage_repo.grant_credits(
            db,
            user_id=user_id,
            amount_usd=amount_usd,
            description="Credit purchase",
            reference_type=f"{provider}_checkout_session",
            reference_id=session_id,
        )


async def _handle_subscription_event(
    db: AsyncSession,
    *,
    provider: billing_repo.ProviderId,
    event_type: str,
    event_created_at: datetime | None,
    obj: dict[str, Any],
) -> None:
    subscription_id = _object_id(obj.get("id"))
    if subscription_id is None:
        return
    user_id = await _user_id_for_payload(db, provider=provider, obj=obj)
    if user_id is None:
        return
    status_value = obj.get("status")
    sub_status = status_value if isinstance(status_value, str) else "canceled"
    if event_type == "customer.subscription.deleted":
        sub_status = "canceled"
    await billing_repo.upsert_subscription_entitlement(
        db,
        user_id=user_id,
        provider=provider,
        subscription_id=subscription_id,
        status=sub_status,
        customer_id=_object_id(obj.get("customer")),
        current_period_end=_timestamp_to_datetime(obj.get("current_period_end")),
        event_created_at=event_created_at,
    )


@router.post("/webhook", response_model=BillingWebhookResponse)
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
) -> BillingWebhookResponse:
    settings = get_settings()
    provider = _require_backend(settings)
    payload = await request.body()
    if provider == "stripe":
        _verify_stripe_signature(
            payload=payload,
            signature_header=stripe_signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
    try:
        event = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _billing_error(
            code="INVALID_WEBHOOK_PAYLOAD",
            title="Invalid webhook payload",
            body="Webhook body must be valid JSON.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not isinstance(event, dict):
        raise _billing_error(
            code="INVALID_WEBHOOK_PAYLOAD",
            title="Invalid webhook payload",
            body="Webhook body must be an object.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    event_id = event.get("id")
    event_type = event.get("type")
    event_created_at = _timestamp_to_datetime(event.get("created"))
    obj = (
        event.get("data", {}).get("object")
        if isinstance(event.get("data"), dict)
        else None
    )
    if (
        not isinstance(event_id, str)
        or not event_id
        or not isinstance(event_type, str)
        or not event_type
    ):
        raise _billing_error(
            code="INVALID_WEBHOOK_PAYLOAD",
            title="Invalid webhook payload",
            body="Webhook event id and type are required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(obj, dict):
        if event_type in _HANDLED_EVENT_TYPES:
            raise _billing_error(
                code="INVALID_WEBHOOK_PAYLOAD",
                title="Invalid webhook payload",
                body="Webhook data.object must be an object for this event type.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        obj = {}

    should_process = await billing_repo.mark_webhook_event_processing(
        db,
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        payload=cast(dict[str, Any], event),
    )
    if not should_process:
        return BillingWebhookResponse(received=True, processed=False)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(
            db,
            provider=provider,
            event_id=event_id,
            obj=cast(dict[str, Any], obj),
            settings=settings,
        )
    elif event_type in _HANDLED_EVENT_TYPES:
        await _handle_subscription_event(
            db,
            provider=provider,
            event_type=event_type,
            event_created_at=event_created_at,
            obj=cast(dict[str, Any], obj),
        )
    return BillingWebhookResponse(received=True, processed=True)
