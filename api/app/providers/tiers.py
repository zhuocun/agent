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
from app.schemas.tier import ModelTier, ProviderDataPolicy
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
    # tool loop / server tool). True on all real providers (DeepSeek, Anthropic,
    # OpenAI, fake). The FE-facing flag is gated additionally on a configured
    # search backend in `list_tiers` (`... AND search_enabled(settings)`); this
    # binding-level flag is the provider-capability half.
    supports_web_search: bool = False
    # Whether this binding can accept user attachments for a turn using native
    # provider payloads. Metadata-only fallback is intentionally not enough to
    # advertise this capability.
    supports_attachments: bool = False


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
    )


def list_tiers(settings: Settings | None = None) -> list[ModelTier]:
    """Public tier list for bootstrap.

    Tier ids/labels/hints are backend-independent, but each tier's
    `model_label` is filled from the ACTIVE backend's binding so the FE picker
    discloses the model that actually answers. `auto` stays blank — its served
    model varies per message via the router.
    """
    s = settings if settings is not None else get_settings()
    route = get_provider_route(s.provider_backend)
    # Web search is usable only when a search backend is configured; the
    # per-tier capability also requires the active binding's provider to support
    # it. Gate the wire flag on BOTH so the FE shows the affordance only when a
    # turn could actually ground.
    search_on = search_enabled(s)
    tiers: list[ModelTier] = []
    for base in TIER_BINDINGS:
        binding = get_binding(base.tier.id, settings=s)
        label = binding.model_label if binding is not None else ""
        supports_search = (
            binding.supports_web_search if binding is not None else False
        ) and search_on
        supports_attachments = (
            binding.supports_attachments if binding is not None else False
        )
        tiers.append(
            base.tier.model_copy(
                update={
                    "model_label": label,
                    "supports_web_search": supports_search,
                    "supports_attachments": supports_attachments,
                    "provider_id": route.provider_id if route is not None else "",
                    "provider_label": route.label if route is not None else "",
                    "provider_route_status": (
                        route.status if route is not None else "unavailable"
                    ),
                    "default_route_eligible": (
                        route.default_route_eligible if route is not None else False
                    ),
                    "data_policy": route.data_policy if route is not None else None,
                }
            )
        )
    return tiers


def get_binding(tier_id: ModelTierId, settings: Settings | None = None) -> TierBinding | None:
    """Return the binding for a tier id, or None if unknown.

    Backend-aware. The canonical `TIER_BINDINGS` table binds DeepSeek (the
    main/default real provider) and is used for `deepseek`/`fake`/default.
    `PROVIDER_BACKEND=openai` and `anthropic` are alternate paths that swap in
    their own provider/model/pricing while reusing the canonical `ModelTier`
    instances so the FE-facing shape stays byte-identical.

    `settings` is an optional override for tests / call sites that already hold
    a `Settings`; it defaults to the process-wide `get_settings()`.
    """
    s = settings if settings is not None else get_settings()
    route = get_provider_route(s.provider_backend)
    if route is None or route.status != "available" or route.adapter is None:
        return None
    if s.provider_backend == "openai":
        return _openai_binding(tier_id, s)
    if s.provider_backend == "anthropic":
        return _anthropic_binding(tier_id)
    if s.provider_backend == "fake":
        for binding in TIER_BINDINGS:
            if binding.tier.id == tier_id:
                return replace(binding, supports_attachments=True)
        return None
    if s.provider_backend != "deepseek":
        return None
    for binding in TIER_BINDINGS:
        if binding.tier.id == tier_id:
            return binding
    return None


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
