"""Shared retryable-provider-error predicate for turn- and worker-level fallback."""

from __future__ import annotations

from app.errors import AppError

RETRYABLE_PROVIDER_CODES = frozenset({"RATE_LIMITED", "PROVIDER_UPSTREAM"})


def is_retryable_provider_error(exc: BaseException) -> bool:
    """Whether a provider exception qualifies for a fallback-route retry."""
    return isinstance(exc, AppError) and exc.envelope.code in RETRYABLE_PROVIDER_CODES
