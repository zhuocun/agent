"""Billing route schemas."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel


class BillingCheckoutRequest(CamelModel):
    kind: Literal["pro_subscription", "credit_purchase"]


class BillingSessionResponse(CamelModel):
    url: str


class BillingWebhookResponse(CamelModel):
    received: bool = True
    processed: bool = True
