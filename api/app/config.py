"""Environment-driven settings loaded once at import time.

`pydantic-settings` reads from environment variables; misconfigured CORS or
cookie flags fail fast at boot. Defaults are dev-friendly but loud — production
must override `SESSION_SECRET`, `DATABASE_URL`, and `CORS_ALLOWED_ORIGINS`.
"""

from __future__ import annotations

from functools import cached_property, lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Loud, fixed dev default so missing-env in prod is obvious in logs.
_DEV_SESSION_SECRET = "dev-only-insecure-session-secret-change-me"
# Loud, fixed dev KEK so BYOK roundtrips work locally without setting up real
# key material. Base64-encoded 32 zero bytes -- `assert_prod_safe()` refuses
# this value in production. NEVER reuse this value outside dev/test.
_DEV_BYOK_KEK_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class Settings(BaseSettings):
    """Process-wide settings. Use `get_settings()` to access."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["dev", "test", "production"] = Field(default="dev")

    # Database: async SQLAlchemy URL. asyncpg in prod; aiosqlite in tests.
    database_url: str = Field(default="sqlite+aiosqlite:///./dev.sqlite3")

    # Session cookie signing. Required in prod.
    session_secret: str = Field(default=_DEV_SESSION_SECRET)
    session_max_age_seconds: int = Field(default=60 * 60 * 24 * 30)  # 30 days
    cookie_secure: bool = Field(default=False)
    cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax")
    cookie_name: str = Field(default="sid")

    # CORS. Comma-separated env string -> parsed list via `cors_allowed_origins`.
    # We accept a string here so pydantic-settings doesn't try to JSON-parse
    # the env var; the parsed list is exposed via the `@cached_property` below.
    cors_allowed_origins_raw: str = Field(default="", alias="CORS_ALLOWED_ORIGINS")
    cors_max_age: int = Field(default=600)

    # Anthropic (optional in M0).
    anthropic_api_key: str | None = Field(default=None)

    # Provider backend selection (M1). `fake` for dev/tests, `anthropic` for prod.
    provider_backend: Literal["anthropic", "fake"] = Field(default="fake")

    # BYOK key encryption KEK (base64-encoded 32 bytes). Required in M3 — the
    # default value is a known-bad dev sentinel that `assert_prod_safe()`
    # rejects so production deploys fail fast.
    byok_encryption_kek: str = Field(
        default=_DEV_BYOK_KEK_B64, alias="BYOK_ENCRYPTION_KEK"
    )

    @cached_property
    def cors_allowed_origins(self) -> list[str]:
        """Parse the comma-separated env string into a list of origins."""
        raw = self.cors_allowed_origins_raw or ""
        return [s.strip() for s in raw.split(",") if s.strip()]

    def assert_prod_safe(self) -> None:
        """Raise if production is configured with an insecure default.

        Validates the BYOK KEK at every env: it must decode to exactly 32 bytes,
        regardless of `env`, because the encryption path assumes the cipher is
        constructable. In production we additionally refuse the known-bad dev
        sentinel.
        """
        # Always validate the KEK shape — boot fails fast if it can't build the
        # cipher. `decode_kek` raises `RuntimeError` on missing / malformed /
        # wrong-length input, which is exactly the failure mode we want at
        # startup rather than at the first BYOK write.
        from app.security.crypto import decode_kek

        decode_kek(self.byok_encryption_kek)

        if self.env != "production":
            return
        if self.session_secret == _DEV_SESSION_SECRET:
            raise RuntimeError("SESSION_SECRET must be overridden in production")
        if self.byok_encryption_kek == _DEV_BYOK_KEK_B64:
            raise RuntimeError("BYOK_ENCRYPTION_KEK must be overridden in production")
        if not self.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true in production")
        if self.cookie_samesite != "none":
            raise RuntimeError("COOKIE_SAMESITE must be 'none' in production")
        if not self.cors_allowed_origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS must be set in production")
        if self.provider_backend == "fake":
            raise RuntimeError("PROVIDER_BACKEND must not be 'fake' in production.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
