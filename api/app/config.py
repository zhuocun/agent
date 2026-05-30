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

    # Anthropic (alternate provider). Optional unless PROVIDER_BACKEND=anthropic.
    anthropic_api_key: str | None = Field(default=None)

    # OpenAI(-compatible) provider (alternate). Configured "OpenAI style":
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

    # DeepSeek — the canonical / main real provider (cost leader; see
    # docs/prd/00-product-overview.md D11). DeepSeek is OpenAI-compatible, so the
    # `deepseek` backend drives the same `OpenAIProvider` adapter against the
    # built-in default `base_url` below. Running `PROVIDER_BACKEND=deepseek`
    # needs only an API key — no base_url/model env gymnastics. The per-tier
    # model ids (`deepseek-chat` for fast/smart/auto, `deepseek-reasoner` for
    # pro) live in the canonical `TIER_BINDINGS` registry (providers/tiers.py),
    # the single source of truth — same pattern as the Anthropic table.
    # `DEEPSEEK_API_KEY` falls back to `OPENAI_API_KEY` when unset (see
    # `deepseek_key`) so an OpenAI-compatible key works with either env name.
    deepseek_api_key: str | None = Field(default=None)
    deepseek_base_url: str = Field(default="https://api.deepseek.com")

    # Provider backend selection (M1). `fake` for dev/tests, `deepseek` is the
    # main/prod provider; `anthropic`/`openai` are alternates.
    provider_backend: Literal["deepseek", "anthropic", "openai", "fake"] = Field(
        default="fake"
    )

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

    # Observability (Post-M4 hardening): both OTel tracing and Sentry error
    # reporting are env-driven and no-op when unset. Production warns at boot
    # if either is missing but never refuses to start — observability is
    # optional and we'd rather serve traffic with degraded telemetry than
    # refuse it outright.
    #
    # - `sentry_dsn`: Sentry SDK init target. Unset -> Sentry is a no-op.
    # - `otel_exporter_otlp_endpoint`: OTLP/HTTP collector URL (e.g. the Fly
    #   Honeycomb add-on, an OTel Collector sidecar, etc.). Unset -> no
    #   tracer provider is registered and instrumentation is skipped. We
    #   deliberately choose OTLP/HTTP (pure Python) over gRPC so we don't
    #   need a native compile step in the Docker build.
    # - `otel_service_name`: `service.name` resource attribute on spans.
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_service_name: str = Field(default="api", alias="OTEL_SERVICE_NAME")

    # Slowapi rate limit strings (per-route). Format: "<count>/<window>" e.g.
    # "30/minute", "5/minute". Storage is in-process; multi-worker prod will
    # need a shared store (Redis). Per-route limits resolve via a callable in
    # the decorator so settings cache invalidation in tests takes effect.
    rate_limit_messages: str = Field(default="30/minute", alias="RATE_LIMIT_MESSAGES")
    rate_limit_upgrade: str = Field(default="5/minute", alias="RATE_LIMIT_UPGRADE")

    # Cost-based usage budget cap (USD per calendar-month period). When a user's
    # accumulated `usage_rollup.cost_usd` for the period reaches this value, the
    # next platform-key turn is refused with a 429 `BUDGET_EXCEEDED` envelope.
    # `<= 0` means "disabled / unlimited" -- the default, so existing behavior
    # and tests are unchanged. BYOK turns are always exempt (the user pays their
    # own provider) and never consult this cap.
    usage_budget_usd: float = Field(default=0.0, alias="USAGE_BUDGET_USD")

    # Orphan-stream reaper TTL (seconds). A hard worker crash (SIGKILL / OOM /
    # power loss) runs no Python cleanup, so a `stream` row can strand at
    # `status="active"` forever (PRD 04 §5.1). The reaper sweeps `active` rows
    # whose `updated_at` is older than this many seconds and marks them
    # `"error"`. Default 900s (15 min): MVP turns last seconds, and
    # `mark_status` bumps `updated_at` on every transition, so 15 minutes is
    # vastly longer than any legitimately-active stream — a live turn is never
    # reaped. (If a turn could ever plausibly run longer than the TTL the
    # handler should heartbeat `updated_at`; not needed for MVP.) `<= 0`
    # disables the reaper entirely.
    #
    # Single-process caveat (same as `_TEMP_IDS` / `stop_registry` / the
    # slowapi in-memory store): the reaper runs in-process. Behind multiple
    # uvicorn workers each process sweeps independently — harmless because the
    # bulk UPDATE is idempotent and keyed on a shared DB column, but a
    # production-grade reaper belongs in a single coordinated job (cron /
    # Redis-locked worker) rather than every web process.
    stream_reap_after_seconds: int = Field(
        default=900, alias="STREAM_REAP_AFTER_SECONDS"
    )
    # Interval (seconds) between background reaper sweeps. The first sweep also
    # runs once at startup (a fresh process knows any `active` row it didn't
    # create is orphaned from a prior crash). `<= 0` on EITHER this or
    # `stream_reap_after_seconds` disables the background loop.
    stream_reap_interval_seconds: int = Field(
        default=300, alias="STREAM_REAP_INTERVAL_SECONDS"
    )

    # Auto-tier routing. When True (default), an `auto` request runs the v0
    # complexity heuristic (`providers/router.py`) and is served by the routed
    # concrete tier (fast / smart / pro). When False, `auto` falls back to its
    # legacy static behavior (served by the `smart`-class binding) so the
    # routing layer can be killed without a redeploy. Disabling does NOT change
    # any non-auto tier.
    auto_routing_enabled: bool = Field(default=True, alias="AUTO_ROUTING_ENABLED")

    # Same-device resumable-stream replay (PRD 04 §5.1 P1; PRD 05 §4.4
    # "Resumable-stream spine"). DEFAULT-OFF feature flag — a hard safety gate
    # around the highest-risk path in the codebase.
    #
    # When OFF (the default), streaming behavior is byte-identical to today: a
    # client disconnect (or the stop endpoint) cancels the provider pump and
    # persists `status="stopped"`. The reconnect endpoint 404s (feature
    # disabled). Every existing test passes unchanged.
    #
    # When ON, the provider pump runs DETACHED from the HTTP connection: a mere
    # client disconnect no longer cancels it (a deliberate semantics inversion).
    # The producer keeps running, appending each SSE event to an in-process
    # ReplayBuffer (`app.streaming.replay_registry`); the POST connection and
    # any `GET .../stream/{stream_id}` reconnect subscribe to that buffer, replay
    # buffered events from the start, then tail live until the producer is done.
    # Only the stop endpoint (via `stop_registry`) or natural completion cancels
    # the producer. Cost / usage-rollup / attribution / persistence semantics are
    # unchanged — the producer runs the SAME code path, just detached.
    #
    # In-process, NO REDIS (single-worker MVP compromise — same caveat as
    # `stop_registry`, `_TEMP_IDS`, and the slowapi in-memory store). Behind
    # multiple uvicorn workers a reconnect that lands on a different worker than
    # the producer 404s (the buffer lives in the producer's process only);
    # multi-worker resumable streams need a shared Redis replay log. The durable
    # `stream` row remains the cross-worker record of the turn's lifecycle.
    resumable_streams_enabled: bool = Field(
        default=False, alias="RESUMABLE_STREAMS_ENABLED"
    )

    # TTL (seconds) a finished ReplayBuffer is retained after the producer marks
    # it `done`, so a late same-device reconnect can still replay the full final
    # sequence. After this window the buffer is evicted (lazy per-access sweep in
    # `replay_registry.get` / `.create`) and a reconnect → 404. Default 60s:
    # long enough for a transient network blip + reconnect, short enough to bound
    # per-process memory. Only consulted when `resumable_streams_enabled`.
    resumable_buffer_ttl_seconds: float = Field(
        default=60.0, alias="RESUMABLE_BUFFER_TTL_SECONDS"
    )

    @property
    def deepseek_key(self) -> str | None:
        """Effective DeepSeek key: `DEEPSEEK_API_KEY`, else `OPENAI_API_KEY`.

        DeepSeek is OpenAI-compatible, so a single OpenAI-compatible key set as
        either env var works. The dedicated `DEEPSEEK_API_KEY` wins when both
        are present.
        """
        return self.deepseek_api_key or self.openai_api_key

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
        if self.provider_backend == "deepseek" and not self.deepseek_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY (or OPENAI_API_KEY) required when PROVIDER_BACKEND=deepseek"
            )
        if self.provider_backend == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY required when PROVIDER_BACKEND=anthropic")
        if self.provider_backend == "openai" and not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY required when PROVIDER_BACKEND=openai")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
