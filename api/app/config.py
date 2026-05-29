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

    # OpenAI(-compatible) provider (optional). Configured "OpenAI style":
    # OPENAI_API_KEY + optional OPENAI_BASE_URL (None lets the SDK use its own
    # default, https://api.openai.com/v1; override for Azure/OpenRouter/Ollama/
    # vLLM/local). Per-tier model ids are overridable via env so the same
    # backend can drive any OpenAI-compatible endpoint.
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)
    openai_model_fast: str = Field(default="gpt-4o-mini")
    openai_model_smart: str = Field(default="gpt-4o")
    openai_model_pro: str = Field(default="o1")
    openai_model_auto: str = Field(default="gpt-4o")

    # Provider backend selection (M1). `fake` for dev/tests, `anthropic`/`openai`
    # for prod.
    provider_backend: Literal["anthropic", "openai", "fake"] = Field(default="fake")

    # BYOK key encryption KEK (base64-encoded 32 bytes). Required in M3 — the
    # default value is a known-bad dev sentinel that `assert_prod_safe()`
    # rejects so production deploys fail fast.
    byok_encryption_kek: str = Field(default=_DEV_BYOK_KEK_B64, alias="BYOK_ENCRYPTION_KEK")

    # Versioned-KEK rotation registry. Raw env format is comma-separated
    # `version:base64key` pairs, e.g. `1:AAAA...=,2:BBBB...=`. Parsed by
    # `kek_version_registry` below into a `{version: base64}` dict. Empty
    # default keeps the legacy single-KEK path unchanged for everyone who
    # has not opted into rotation. See `app.security.crypto` for the on-disk
    # format and dispatch rules.
    byok_kek_versions_raw: str = Field(default="", alias="BYOK_KEK_VERSIONS")
    # Active KEK version used for new writes. `0` means "write the legacy
    # single-KEK format" (bit-compatible with rows written before rotation
    # was wired up). `>= 1` means "write the versioned format using the
    # registry entry for that version." Reads dispatch on the ciphertext
    # header regardless of this value, so old rows stay decryptable.
    byok_current_kek_version: int = Field(default=0, alias="BYOK_CURRENT_KEK_VERSION")

    @cached_property
    def cors_allowed_origins(self) -> list[str]:
        """Parse the comma-separated env string into a list of origins."""
        raw = self.cors_allowed_origins_raw or ""
        return [s.strip() for s in raw.split(",") if s.strip()]

    @cached_property
    def kek_version_registry(self) -> dict[int, str]:
        """Parse `BYOK_KEK_VERSIONS` into a `{version: base64}` registry.

        Parser lives in `app.security.crypto.parse_kek_versions` so tests
        and runtime share the same error surface. A malformed entry raises
        `RuntimeError` at first access -- in practice that is during
        `assert_prod_safe()` at boot.
        """
        from app.security.crypto import parse_kek_versions

        return parse_kek_versions(self.byok_kek_versions_raw)

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

        # Validate the rotation registry: every entry must decode to a
        # legal 32-byte KEK, and if writes target a versioned KEK that
        # version must actually be in the registry. Accessing
        # `kek_version_registry` runs the parser, which already raises
        # `RuntimeError` on malformed input.
        registry = self.kek_version_registry
        for version, kek_b64 in registry.items():
            try:
                decode_kek(kek_b64)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"BYOK_KEK_VERSIONS entry for version {version} is invalid: {exc}"
                ) from exc
        if self.byok_current_kek_version < 0:
            raise RuntimeError(
                "BYOK_CURRENT_KEK_VERSION must be >= 0"
            )
        if (
            self.byok_current_kek_version >= 1
            and self.byok_current_kek_version not in registry
        ):
            raise RuntimeError(
                "BYOK_CURRENT_KEK_VERSION="
                f"{self.byok_current_kek_version} but no matching entry in "
                "BYOK_KEK_VERSIONS"
            )

        if self.env != "production":
            return
        if self.session_secret == _DEV_SESSION_SECRET:
            raise RuntimeError("SESSION_SECRET must be overridden in production")
        if len(self.session_secret) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters in production")
        if self.byok_encryption_kek == _DEV_BYOK_KEK_B64:
            raise RuntimeError("BYOK_ENCRYPTION_KEK must be overridden in production")
        if not self.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true in production")
        if self.cookie_samesite != "none":
            raise RuntimeError("COOKIE_SAMESITE must be 'none' in production")
        if not self.cors_allowed_origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS must be set in production")
        if any(o == "*" for o in self.cors_allowed_origins):
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS must not contain '*' in production (credentialed CORS)"
            )
        if self.provider_backend == "fake":
            raise RuntimeError("PROVIDER_BACKEND must not be 'fake' in production.")
        if self.provider_backend == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY required when PROVIDER_BACKEND=anthropic")
        if self.provider_backend == "openai" and not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY required when PROVIDER_BACKEND=openai")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
