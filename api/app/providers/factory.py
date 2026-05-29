"""Env-driven provider selection.

`PROVIDER_BACKEND=fake` (default) → `FakeProvider` for dev/tests.
`PROVIDER_BACKEND=anthropic` → `AnthropicProvider` for prod. Requires
`ANTHROPIC_API_KEY` — boot fails fast if missing.
`PROVIDER_BACKEND=openai` → `OpenAIProvider` (OpenAI-compatible) for prod.
Requires `OPENAI_API_KEY`; `OPENAI_BASE_URL` is optional (SDK default).
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.errors import AppError, ErrorEnvelope
from app.providers.anthropic import AnthropicProvider
from app.providers.fake import FakeProvider
from app.providers.openai import OpenAIProvider
from app.providers.protocol import Provider


def build_provider(settings: Settings | None = None) -> Provider:
    """Return a Provider matching the configured backend."""
    s = settings if settings is not None else get_settings()
    if s.provider_backend == "anthropic":
        if not s.anthropic_api_key:
            # Surface a typed envelope so ops can grep for `MISCONFIGURED`
            # rather than the generic FATAL 500 that bare RuntimeError yields.
            raise AppError(
                ErrorEnvelope(
                    code="MISCONFIGURED",
                    severity="fatal",
                    title="Provider misconfigured",
                    body=("ANTHROPIC_API_KEY is required when PROVIDER_BACKEND=anthropic."),
                ),
                status_code=500,
            )
        return AnthropicProvider(api_key=s.anthropic_api_key)
    if s.provider_backend == "openai":
        if not s.openai_api_key:
            raise AppError(
                ErrorEnvelope(
                    code="MISCONFIGURED",
                    severity="fatal",
                    title="Provider misconfigured",
                    body="OPENAI_API_KEY is required when PROVIDER_BACKEND=openai.",
                ),
                status_code=500,
            )
        return OpenAIProvider(api_key=s.openai_api_key, base_url=s.openai_base_url)
    return FakeProvider()
