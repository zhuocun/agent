"""BE model tier registry — single source of truth for capability tiers.

Mirrors `web/src/lib/model-tiers.ts` exactly on the wire, but is BE-owned.
Bootstrap returns this list so the FE can stop carrying its own copy once it
consumes `bootstrap.modelTiers`.

`ModelTier` is the FE-facing slice. Route metadata and data-policy fields are
serialized for disclosure; concrete model ids, pricing, and provider knobs stay
private in `TierBinding` for `providers/pricing.py` and the streaming handler.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from app.config import Settings, get_settings
from app.schemas.common import CostHint, ModelTierId, SpeedHint
from app.schemas.tier import ModelTier, ProviderDataPolicy, ProviderRouteOption
from app.search.factory import search_enabled

ProviderRouteStatus = Literal["available", "pending", "unavailable"]


@dataclass(frozen=True)
class ProviderRoute:
    """Backend/provider route metadata independent of tier bindings."""

    provider_id: str
    label: str
    status: ProviderRouteStatus
    adapter: Literal["openai_compatible", "anthropic", "fake"] | None
    default_route_eligible: bool
    data_policy: ProviderDataPolicy | None
    notes: str = ""


PROVIDER_ROUTES: tuple[ProviderRoute, ...] = (
    ProviderRoute(
        provider_id="deepseek",
        label="DeepSeek",
        status="available",
        adapter="openai_compatible",
        default_route_eligible=True,
        data_policy=ProviderDataPolicy(
            trains_on_data=True,
            training_default="opt_out",
            data_residency="China",
            retention_days=None,
            zero_data_retention_available=False,
            policy_label="May train unless opted out; China data residency",
        ),
        notes="Canonical cost-leading production route via OpenAI-compatible API.",
    ),
    ProviderRoute(
        provider_id="anthropic",
        label="Anthropic",
        status="available",
        adapter="anthropic",
        default_route_eligible=True,
        data_policy=ProviderDataPolicy(
            trains_on_data=False,
            training_default="never",
            data_residency="US/EU",
            retention_days=30,
            zero_data_retention_available=True,
            policy_label="No training; API retention up to 30 days",
        ),
        notes="Direct Anthropic Messages API adapter.",
    ),
    ProviderRoute(
        provider_id="openai",
        label="OpenAI",
        status="available",
        adapter="openai_compatible",
        default_route_eligible=True,
        data_policy=ProviderDataPolicy(
            trains_on_data=False,
            training_default="never",
            data_residency="US/EU",
            retention_days=30,
            zero_data_retention_available=True,
            policy_label="No training; standard API retention",
        ),
        notes="Direct OpenAI or operator-supplied OpenAI-compatible endpoint.",
    ),
    ProviderRoute(
        provider_id="gemini",
        label="Gemini",
        status="pending",
        adapter=None,
        default_route_eligible=False,
        data_policy=None,
        notes="Registered for roadmap visibility only; no provider adapter is wired.",
    ),
    ProviderRoute(
        provider_id="fake",
        label="Fake",
        status="available",
        adapter="fake",
        default_route_eligible=False,
        data_policy=ProviderDataPolicy(
            trains_on_data=False,
            training_default="never",
            data_residency="local",
            retention_days=0,
            zero_data_retention_available=True,
            policy_label="Local deterministic test route",
        ),
        notes="Deterministic in-process provider for dev/tests.",
    ),
)


def get_provider_route(provider_id: str) -> ProviderRoute | None:
    """Return provider route metadata for a configured backend id."""
    return next((route for route in PROVIDER_ROUTES if route.provider_id == provider_id), None)


def available_provider_backend_ids() -> tuple[str, ...]:
    """Provider backend ids that have a real runtime adapter."""
    return tuple(
        route.provider_id
        for route in PROVIDER_ROUTES
        if route.status == "available" and route.adapter is not None
    )


def platform_provider_usable(provider_id: str, settings: Settings | None = None) -> bool:
    """Return whether the platform can call a provider without a user BYOK key."""
    s = settings if settings is not None else get_settings()
    if provider_id == "deepseek":
        return bool(
            s.deepseek_api_key
            or (s.provider_backend == "deepseek" and s.openai_api_key)
        )
    if provider_id == "openai":
        # Legacy DeepSeek deployments may store a DeepSeek-compatible key in
        # OPENAI_API_KEY. Until a dedicated DEEPSEEK_API_KEY is present, do not
        # also advertise that fallback key as a platform OpenAI route.
        return bool(
            s.openai_api_key
            and not (s.provider_backend == "deepseek" and not s.deepseek_api_key)
        )
    if provider_id == "anthropic":
        return bool(s.anthropic_api_key)
    if provider_id == "fake":
        return s.env != "production"
    return False


def provider_route_runtime_status(
    provider_id: str,
    settings: Settings | None = None,
    *,
    usable_provider_ids: set[str] | None = None,
) -> ProviderRouteStatus:
    """Return the operational status for a route under current runtime state.

    The registry's `status` is static adapter/catalog state. This helper folds
    in production fake-provider hardening plus key availability so bootstrap
    does not advertise a route that will fail at send time. `usable_provider_ids`
    may include user BYOK providers in addition to platform-key providers.
    """
    s = settings if settings is not None else get_settings()
    route = get_provider_route(provider_id)
    if route is None:
        return "unavailable"
    if route.status != "available" or route.adapter is None:
        return route.status
    if not route_adapter_available(provider_id, s):
        return "unavailable"
    if usable_provider_ids is not None:
        return "available" if provider_id in usable_provider_ids else "unavailable"
    return "available" if platform_provider_usable(provider_id, s) else "unavailable"


def route_adapter_available(provider_id: str, settings: Settings | None = None) -> bool:
    """Return whether a provider route has an adapter allowed in this runtime."""
    s = settings if settings is not None else get_settings()
    route = get_provider_route(provider_id)
    if route is None or route.status != "available" or route.adapter is None:
        return False
    return not (provider_id == "fake" and s.env == "production")


def require_available_provider_route(settings: Settings) -> ProviderRoute:
    """Fail fast if `PROVIDER_BACKEND` has no usable adapter.

    This is the registry hardening guardrail: a backend may be present in the
    route registry as pending (e.g. Gemini) without becoming silently served by
    the canonical DeepSeek binding.
    """
    provider_id = settings.provider_backend
    route = get_provider_route(provider_id)
    if route is None:
        raise RuntimeError(f"PROVIDER_BACKEND={provider_id!r} is not registered.")
    if route.status != "available" or route.adapter is None:
        raise RuntimeError(
            f"PROVIDER_BACKEND={provider_id!r} is registered as {route.status} "
            "and has no available adapter."
        )
    if provider_id == "fake" and settings.env == "production":
        raise RuntimeError("PROVIDER_BACKEND='fake' is not allowed in production.")
    return route


@dataclass(frozen=True)
class TierBinding:
    """BE-internal binding from tier id to concrete provider/model + pricing.

    `cache_read_per_m` (M4): optional per-million price for cache-read tokens.
    When set, `compute_cost_breakdown` bills `cached_input_tokens` at this rate
    instead of `list_price_in_per_m`. Anthropic cache reads are a documented
    ~90% discount off input; DeepSeek's cache-read rates are now the real
    documented values (no longer placeholders). `None` falls back to 10% of the
    input rate.

    `thinking` toggles DeepSeek V4 thinking mode via the provider call — the
    per-tier intent for which tier reasons by default. `None` leaves the
    provider default; `True`/`False` force-enable/disable. `reasoning_effort`
    (e.g. "high") is passed through to the provider when set, and omitted when
    `None`. Both default to `None` so the Anthropic/OpenAI alternate bindings,
    which never set them, stay valid.
    """

    tier: ModelTier
    provider_id: str
    model_id: str
    list_price_in_per_m: float
    list_price_out_per_m: float
    long_context_flat: bool
    cache_read_per_m: float | None = None
    thinking: bool | None = None
    reasoning_effort: str | None = None
    # Curated display name of this binding's model, surfaced to the FE tier
    # picker via bootstrap (see `list_tiers`). A friendly label, never a raw
    # model id. Empty for tiers whose served model varies per request (the
    # `auto` router), so the picker shows no single model for them.
    model_label: str = ""
    # Whether this binding's provider can ground a turn with web search (via the
    # tool loop / server tool). The FE-facing flag is resolved in `list_tiers`:
    # OpenAI-compatible routes also need a configured search backend, while
    # Anthropic's hosted server tool does not.
    supports_web_search: bool = False
    # Whether this binding can accept user attachments for a turn using native
    # provider payloads. Metadata-only fallback is intentionally not enough to
    # advertise this capability. Text attachments flow as transcript text; PDFs
    # flow as transcript text plus (on vision bindings) a native document block.
    supports_attachments: bool = False
    # Whether this binding can INTERPRET images (and native PDF *document*
    # blocks). DISTINCT from `supports_attachments`: a binding may accept files
    # (text/PDF as transcript text) without being multimodal. When False, the
    # provider adapters emit NEITHER native image blocks NOR native PDF document
    # blocks — PDFs degrade to their `extracted_text` transcript only. DeepSeek
    # (the canonical OpenAI-compatible prod route) is NOT multimodal, so the
    # OpenAI-compatible binding stays conservative (`supports_vision=False`).
    supports_vision: bool = False


def _tier(
    id_: ModelTierId,
    label: str,
    description: str,
    speed: SpeedHint,
    cost: CostHint,
    context: str,
) -> ModelTier:
    return ModelTier(
        id=id_,
        label=label,
        description=description,
        speed_hint=speed,
        cost_hint=cost,
        context_hint=context,
    )


# Order matters: the FE keeps the same order in its picker.
#
# CANONICAL = DeepSeek — the main/default real provider (cost leader; see
# docs/prd/00-product-overview.md D11). The default/`fake`/`deepseek` paths and
# bootstrap all reflect this table. Anthropic and OpenAI are alternate paths
# selected by `PROVIDER_BACKEND` (see `_anthropic_binding` / `_openai_binding`).
#
# DeepSeek V4 pricing (shipped 2026-04-24), per api-docs.deepseek.com/
# quick_start/pricing. Two models, both 1M context, both dual-mode (thinking
# default + non-thinking):
#   - deepseek-v4-flash: cheap, standing price — input(cache-miss) $0.14,
#     output $0.28, input(cache-hit) $0.0028 per 1M tokens.
#   - deepseek-v4-pro: frontier — quarter-rate adjusted price after the
#     2026-05-31 promo cutover: input(cache-miss) $0.435, output $0.87,
#     input(cache-hit) $0.003625 per 1M.
# These models REPLACE the legacy `deepseek-chat` / `deepseek-reasoner` aliases,
# which retire 2026-07-24. Thinking mode is a per-request param (the provider
# call path applies it); the per-tier default intent lives here on `thinking` /
# `reasoning_effort`. DeepSeek is flat-rate (no context-length pricing tiers for
# V4), so `long_context_flat=True` for all. `cache_read_per_m` values are the
# REAL documented DeepSeek cache-hit rates (flash 0.0028, pro 0.003625) — no
# longer placeholders.
TIER_BINDINGS: tuple[TierBinding, ...] = (
    TierBinding(
        tier=_tier(
            "auto",
            "Auto",
            "Routes each message to the best-value model for the task.",
            "fast",
            "low",
            "Adaptive",
        ),
        provider_id="deepseek",
        model_id="deepseek-v4-flash",
        list_price_in_per_m=0.14,
        list_price_out_per_m=0.28,
        long_context_flat=True,
        cache_read_per_m=0.0028,
        thinking=True,
        supports_web_search=True,
    ),
    TierBinding(
        tier=_tier(
            "fast",
            "Fast",
            "Quick, low-cost answers for everyday questions.",
            "fastest",
            "lowest",
            "1M",
        ),
        provider_id="deepseek",
        model_id="deepseek-v4-flash",
        list_price_in_per_m=0.14,
        list_price_out_per_m=0.28,
        long_context_flat=True,
        cache_read_per_m=0.0028,
        thinking=False,
        model_label="DeepSeek V4 Flash",
        supports_web_search=True,
    ),
    TierBinding(
        tier=_tier(
            "smart",
            "Smart",
            "Balanced reasoning and speed for most work.",
            "balanced",
            "medium",
            "1M",
        ),
        provider_id="deepseek",
        model_id="deepseek-v4-flash",
        list_price_in_per_m=0.14,
        list_price_out_per_m=0.28,
        long_context_flat=True,
        cache_read_per_m=0.0028,
        thinking=True,
        model_label="DeepSeek V4 Flash",
        supports_web_search=True,
    ),
    TierBinding(
        tier=_tier(
            "pro",
            "Pro",
            "Maximum capability for hard, high-stakes tasks.",
            "slow",
            "high",
            "1M",
        ),
        provider_id="deepseek",
        model_id="deepseek-v4-pro",
        list_price_in_per_m=0.435,
        list_price_out_per_m=0.87,
        long_context_flat=True,
        cache_read_per_m=0.003625,
        thinking=True,
        reasoning_effort="high",
        model_label="DeepSeek V4 Pro",
        supports_web_search=True,
    ),
)


# --- Anthropic alternate path -------------------------------------------------
# Selected when `PROVIDER_BACKEND=anthropic`. Mirrors the `_openai_binding`
# pattern: reuses the canonical `ModelTier` instances (labels/hints are
# backend-independent and the FE contract must not change); only provider id,
# model id, and pricing differ. Prices track current Anthropic public
# per-million-token pricing; `cache_read_per_m` is ~10% of input per Anthropic's
# cache-read convention.
_ANTHROPIC_PRICING: dict[ModelTierId, tuple[float, float, float]] = {
    # tier id -> (in_per_m, out_per_m, cache_read_per_m)
    "fast": (1.0, 5.0, 0.10),  # claude-haiku-4-5
    "smart": (3.0, 15.0, 0.30),  # claude-sonnet-4-6
    "auto": (3.0, 15.0, 0.30),  # claude-sonnet-4-6
    "pro": (15.0, 75.0, 1.50),  # claude-opus-4-7
}

_ANTHROPIC_MODEL_FOR: dict[ModelTierId, str] = {
    "fast": "claude-haiku-4-5-20251001",
    "smart": "claude-sonnet-4-6",
    "auto": "claude-sonnet-4-6",
    "pro": "claude-opus-4-7",
}

# Friendly model display names for the FE picker (never the raw model id).
# `auto` is empty: its served model varies per message via the router.
_ANTHROPIC_LABEL_FOR: dict[ModelTierId, str] = {
    "fast": "Claude Haiku 4.5",
    "smart": "Claude Sonnet 4.6",
    "auto": "",
    "pro": "Claude Opus 4.7",
}


def _anthropic_binding(tier_id: ModelTierId) -> TierBinding | None:
    """Build the Anthropic binding for a tier id, or None if unknown.

    Mirrors `_openai_binding`: reuses the SAME canonical `ModelTier` instance so
    labels/hints stay byte-identical across backends. Returns None for a tier
    not wired into `_ANTHROPIC_PRICING` / `_ANTHROPIC_MODEL_FOR` so callers can
    treat it as an unknown tier rather than 500 mid-request.
    """
    base = next((b for b in TIER_BINDINGS if b.tier.id == tier_id), None)
    pricing = _ANTHROPIC_PRICING.get(tier_id)
    model_id = _ANTHROPIC_MODEL_FOR.get(tier_id)
    if base is None or pricing is None or model_id is None:
        return None
    in_per_m, out_per_m, cache_read_per_m = pricing
    return TierBinding(
        tier=base.tier,
        provider_id="anthropic",
        model_id=model_id,
        list_price_in_per_m=in_per_m,
        list_price_out_per_m=out_per_m,
        long_context_flat=True,
        cache_read_per_m=cache_read_per_m,
        model_label=_ANTHROPIC_LABEL_FOR.get(tier_id, ""),
        supports_web_search=True,
        supports_attachments=True,
        # Claude is multimodal — it can interpret images and native PDF
        # document blocks.
        supports_vision=True,
    )


# OpenAI(-compatible) per-tier pricing defaults (USD per million tokens),
# tracking the *default* model ids in `Settings` (gpt-4o-mini / gpt-4o / o1).
# `cache_read` is OpenAI's cached-input rate, which is 50% of the input rate for
# all of these models. Overriding the model via `OPENAI_MODEL_*` makes these
# prices APPROXIMATE — the binding still bills against these constants, not the
# substituted model's real card. Keyed by tier id.
_OPENAI_PRICING: dict[ModelTierId, tuple[float, float, float]] = {
    # tier id -> (in_per_m, out_per_m, cache_read_per_m)
    "fast": (0.15, 0.60, 0.075),  # gpt-4o-mini
    "smart": (2.50, 10.0, 1.25),  # gpt-4o
    "auto": (2.50, 10.0, 1.25),  # gpt-4o
    "pro": (15.0, 60.0, 7.50),  # o1
}


def _openai_model_for(tier_id: ModelTierId, s: Settings) -> str | None:
    """Map a tier id to its configured OpenAI model id, or None if unmapped."""
    return {
        "fast": s.openai_model_fast,
        "smart": s.openai_model_smart,
        "auto": s.openai_model_auto,
        "pro": s.openai_model_pro,
    }.get(tier_id)


def _openai_binding(tier_id: ModelTierId, s: Settings) -> TierBinding | None:
    """Build the OpenAI binding for a tier id, or None if unknown.

    Reuses the SAME `ModelTier` instance from `TIER_BINDINGS` so labels/hints
    stay byte-identical across backends (they're backend-independent and the FE
    contract must not change). Only the provider id, model id, and pricing
    differ.

    Returns None (rather than raising KeyError -> a 500 mid-request) if a future
    tier id lands in `TIER_BINDINGS` but isn't wired into `_OPENAI_PRICING` /
    `_openai_model_for` in lockstep; `get_binding` callers already treat None as
    an unknown tier.
    """
    base = next((b for b in TIER_BINDINGS if b.tier.id == tier_id), None)
    pricing = _OPENAI_PRICING.get(tier_id)
    model_id = _openai_model_for(tier_id, s)
    if base is None or pricing is None or model_id is None:
        return None
    in_per_m, out_per_m, cache_read_per_m = pricing
    return TierBinding(
        tier=base.tier,
        provider_id="openai",
        model_id=model_id,
        list_price_in_per_m=in_per_m,
        list_price_out_per_m=out_per_m,
        long_context_flat=True,
        cache_read_per_m=cache_read_per_m,
        # The OpenAI(-compatible) backend's model is operator-configured via
        # OPENAI_MODEL_*, so the configured id IS the most honest disclosure.
        # `auto` stays blank (router picks per message).
        model_label="" if tier_id == "auto" else model_id,
        supports_web_search=True,
        supports_attachments=True,
        # Conservative: the canonical prod OpenAI-compatible route is DeepSeek,
        # which is NOT multimodal. Leave `supports_vision=False` so attachments
        # are accepted (text/PDF as transcript) but images are rejected at the
        # route and native image/document blocks are never emitted.
        supports_vision=False,
    )


def active_byok_provider_id(settings: Settings | None = None) -> str:
    """Provider id used for BYOK lookup under the active backend.

    The request path resolves BYOK keys by `TierBinding.provider_id`; for the
    dev/test `fake` backend that is intentionally still `deepseek`, because the
    canonical tier table represents the real production route. Account/bootstrap
    state should mirror that same lookup instead of treating any stored key row
    as active.
    """
    s = settings if settings is not None else get_settings()
    binding = get_binding("smart", settings=s)
    if binding is not None:
        return binding.provider_id
    return s.provider_backend


def web_search_available_for_binding(
    binding: TierBinding,
    settings: Settings | None = None,
) -> bool:
    """Return whether a `web_search=True` turn can run for this binding.

    OpenAI-compatible routes need an injected search backend. Anthropic uses its
    hosted server-side search tool, so tier metadata must not depend on
    `SEARCH_BACKEND` for that provider. Kept exported so the route orchestrator
    can use the same gate when it wires provider-specific search dispatch.
    """
    if not binding.supports_web_search:
        return False
    if binding.provider_id == "anthropic":
        return True
    s = settings if settings is not None else get_settings()
    return search_enabled(s)


def tier_requires_pro(tier_id: ModelTierId) -> bool:
    """Whether platform-paid usage of a tier requires a Pro entitlement."""
    return tier_id == "pro"


# Per-tier vision capability for the dev/test `fake` backend. The `fast` tier is
# deliberately attachment-capable-but-NOT-vision so the FE e2e (which runs under
# PROVIDER_BACKEND=fake) can drive the vision-removed path by switching to it,
# while the other tiers (auto/smart/pro) keep vision so the vision-allowed path
# is exercised too. Tiers absent from this map default to vision-capable.
_FAKE_SUPPORTS_VISION: dict[ModelTierId, bool] = {
    "fast": False,
    "smart": True,
    "auto": True,
    "pro": True,
}


def _binding_for_provider(
    tier_id: ModelTierId,
    *,
    provider_id: str,
    settings: Settings,
    explicit_provider_override: bool,
) -> TierBinding | None:
    """Return a tier binding for a concrete provider route."""
    if not route_adapter_available(provider_id, settings):
        return None
    if provider_id == "openai":
        return _openai_binding(tier_id, settings)
    if provider_id == "anthropic":
        return _anthropic_binding(tier_id)
    if provider_id == "fake":
        for binding in TIER_BINDINGS:
            if binding.tier.id == tier_id:
                # The fake backend exercises BOTH capability paths so the FE e2e
                # can cover vision-allowed and vision-removed flows under
                # PROVIDER_BACKEND=fake: `fast` is attachment-capable but NOT
                # vision (images rejected, PDFs/text degrade to transcript),
                # while the rest are vision-capable.
                fake_vision = _FAKE_SUPPORTS_VISION.get(tier_id, True)
                if explicit_provider_override:
                    return replace(
                        binding,
                        provider_id="fake",
                        model_id="fake",
                        model_label="" if tier_id == "auto" else "Fake",
                        supports_attachments=True,
                        supports_vision=fake_vision,
                    )
                return replace(
                    binding,
                    supports_attachments=True,
                    supports_vision=fake_vision,
                )
        return None
    if provider_id == "deepseek":
        for binding in TIER_BINDINGS:
            if binding.tier.id == tier_id:
                return binding
        return None
    return None


def _provider_options_for_tier(
    tier_id: ModelTierId,
    settings: Settings,
    usable_provider_ids: set[str] | None,
) -> list[ProviderRouteOption]:
    options: list[ProviderRouteOption] = []
    for route in PROVIDER_ROUTES:
        runtime_status = provider_route_runtime_status(
            route.provider_id,
            settings,
            usable_provider_ids=usable_provider_ids,
        )
        binding = _binding_for_provider(
            tier_id,
            provider_id=route.provider_id,
            settings=settings,
            explicit_provider_override=True,
        )
        supports_search = (
            web_search_available_for_binding(binding, settings=settings)
            if binding is not None
            else False
        )
        options.append(
            ProviderRouteOption(
                provider_id=route.provider_id,
                label=route.label,
                status=runtime_status,
                model_label=binding.model_label if binding is not None else "",
                supports_web_search=supports_search,
                supports_attachments=(
                    binding.supports_attachments if binding is not None else False
                ),
                supports_vision=(
                    binding.supports_vision if binding is not None else False
                ),
                default_route_eligible=(
                    route.default_route_eligible and runtime_status == "available"
                ),
                data_policy=route.data_policy,
            )
        )
    return options


def list_tiers(
    settings: Settings | None = None,
    *,
    usable_provider_ids: set[str] | None = None,
) -> list[ModelTier]:
    """Public tier list for bootstrap.

    Tier ids/labels/hints are backend-independent, but each tier's
    `model_label` is filled from the ACTIVE backend's binding so the FE picker
    discloses the model that actually answers. `auto` stays blank — its served
    model varies per message via the router.
    """
    s = settings if settings is not None else get_settings()
    route = get_provider_route(s.provider_backend)
    active_status = provider_route_runtime_status(
        s.provider_backend,
        s,
        usable_provider_ids=usable_provider_ids,
    )
    tiers: list[ModelTier] = []
    for base in TIER_BINDINGS:
        binding = get_binding(base.tier.id, settings=s)
        label = binding.model_label if binding is not None else ""
        supports_search = (
            web_search_available_for_binding(binding, settings=s) if binding is not None else False
        )
        supports_attachments = binding.supports_attachments if binding is not None else False
        supports_vision = binding.supports_vision if binding is not None else False
        tiers.append(
            base.tier.model_copy(
                update={
                    "model_label": label,
                    "supports_web_search": supports_search,
                    "supports_attachments": supports_attachments,
                    "supports_vision": supports_vision,
                    "provider_id": route.provider_id if route is not None else "",
                    "provider_label": route.label if route is not None else "",
                    "provider_route_status": active_status,
                    "default_route_eligible": (
                        route.default_route_eligible and active_status == "available"
                        if route is not None
                        else False
                    ),
                    "data_policy": route.data_policy if route is not None else None,
                    "provider_options": _provider_options_for_tier(
                        base.tier.id,
                        s,
                        usable_provider_ids,
                    ),
                }
            )
        )
    return tiers


def get_binding(
    tier_id: ModelTierId,
    settings: Settings | None = None,
    provider_id: str | None = None,
) -> TierBinding | None:
    """Return the binding for a tier id, or None if unknown.

    Backend-aware. The canonical `TIER_BINDINGS` table binds DeepSeek (the
    main/default real provider) and is used for `deepseek`/`fake`/default.
    `PROVIDER_BACKEND=openai` and `anthropic` are alternate paths that swap in
    their own provider/model/pricing while reusing the canonical `ModelTier`
    instances so the FE-facing shape stays byte-identical.

    `settings` is an optional override for tests / call sites that already hold
    a `Settings`; it defaults to the process-wide `get_settings()`.

    `provider_id` is a per-request route override. When omitted, current
    settings-based behavior is preserved exactly.
    """
    s = settings if settings is not None else get_settings()
    return _binding_for_provider(
        tier_id,
        provider_id=provider_id or s.provider_backend,
        settings=s,
        explicit_provider_override=provider_id is not None,
    )


def is_known_tier(tier_id: str) -> bool:
    """Backend-independent: the set of known tier ids never changes."""
    return any(b.tier.id == tier_id for b in TIER_BINDINGS)


# Fallback served tier for an UNROUTED `auto` binding. The per-request router
# (`providers/router.py`, wired in `routes/conversations.py::send_message`)
# rebinds `auto` to a concrete tier BEFORE attribution, so in the routed path
# `resolve_served_tier` never sees an `auto` binding. This constant is the
# safety net for the unrouted path — `AUTO_ROUTING_ENABLED=false`, or any future
# call site that bills the raw `auto` binding — and matches the current
# auto->smart mapping (deepseek-v4-flash on DeepSeek, claude-sonnet on
# Anthropic, gpt-4o on OpenAI). The FE attribution row requires a concrete
# served tier (see `web/src/components/chat/attribution-row.tsx::assertServedTier`).
_AUTO_RESOLVES_TO: ModelTierId = "smart"


def resolve_served_tier(binding: TierBinding) -> tuple[ModelTierId, str]:
    """Resolve `(servedTierId, servedTierLabel)` for an attribution.

    For concrete tiers this is `(binding.tier.id, binding.tier.label)`. For the
    "auto" tier, the FE requires the wire to surface a concrete tier id so the
    attribution row can render which class of model actually served the turn —
    we resolve to the smart tier's id + label. Pricing still bills via the
    `binding` that was actually used (which for `auto` may be the auto-specific
    pricing if backends ever diverge).
    """
    if binding.tier.id == "auto":
        for candidate in TIER_BINDINGS:
            if candidate.tier.id == _AUTO_RESOLVES_TO:
                return candidate.tier.id, candidate.tier.label
    return binding.tier.id, binding.tier.label
