"""Backend-aware tier binding tests for `app.providers.tiers`.

`get_binding(tier_id, settings=...)` is backend-aware: under
`PROVIDER_BACKEND=openai` it returns OpenAI provider/model/pricing (reusing the
canonical `ModelTier` instance so the FE-facing shape is byte-identical); under
`anthropic` it returns the Anthropic alternate table; under `deepseek`/`fake`
(the default) it returns the canonical DeepSeek table.

`TIER_BINDINGS`, `list_tiers()`, and `is_known_tier()` are backend-independent
and must stay identical — the wire contract (tier ids/labels/hints) never
changes with the provider. These tests pin both halves.
"""

from __future__ import annotations

from app.config import Settings
from app.providers.tiers import (
    TIER_BINDINGS,
    get_binding,
    is_known_tier,
    list_tiers,
    resolve_served_tier,
)


def _openai_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"provider_backend": "openai", "openai_api_key": "x"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_get_binding_openai_returns_openai_provider_model_and_pricing() -> None:
    """openai backend -> provider_id 'openai', configured model id, openai prices."""
    s = _openai_settings(openai_model_pro="custom-model")
    b = get_binding("pro", settings=s)
    assert b is not None
    assert b.provider_id == "openai"
    assert b.model_id == "custom-model"
    # Pro defaults track o1.
    assert b.list_price_in_per_m == 15.0
    assert b.list_price_out_per_m == 60.0
    assert b.cache_read_per_m == 7.50
    assert b.long_context_flat is True


def test_get_binding_openai_default_models_per_tier() -> None:
    """Each tier maps to its default OpenAI model + price when unoverridden."""
    s = _openai_settings()
    expected = {
        "fast": ("gpt-4o-mini", 0.15, 0.60, 0.075),
        "smart": ("gpt-4o", 2.50, 10.0, 1.25),
        "auto": ("gpt-4o", 2.50, 10.0, 1.25),
        "pro": ("o1", 15.0, 60.0, 7.50),
    }
    for tier_id, (model, in_m, out_m, cache_m) in expected.items():
        b = get_binding(tier_id, settings=s)  # type: ignore[arg-type]
        assert b is not None
        assert b.provider_id == "openai"
        assert b.model_id == model
        assert b.list_price_in_per_m == in_m
        assert b.list_price_out_per_m == out_m
        assert b.cache_read_per_m == cache_m


def test_get_binding_openai_reuses_canonical_modeltier_instance() -> None:
    """The OpenAI binding reuses the SAME ModelTier so labels/hints are identical."""
    s = _openai_settings()
    for tier_id in ("auto", "fast", "smart", "pro"):
        base = next(b for b in TIER_BINDINGS if b.tier.id == tier_id)
        openai_b = get_binding(tier_id, settings=s)  # type: ignore[arg-type]
        assert openai_b is not None
        assert openai_b.tier is base.tier  # same instance, not a copy


def test_get_binding_fake_returns_canonical_deepseek_binding() -> None:
    """The default/fake backend resolves to the canonical DeepSeek table."""
    s = Settings(provider_backend="fake")
    b = get_binding("fast", settings=s)
    assert b is not None
    assert b.provider_id == "deepseek"
    assert b.model_id == "deepseek-v4-flash"
    # DeepSeek V4 flash standing price.
    assert b.list_price_in_per_m == 0.14
    assert b.list_price_out_per_m == 0.28
    assert b.cache_read_per_m == 0.0028


def test_get_binding_deepseek_backend_returns_canonical_deepseek_binding() -> None:
    """The explicit deepseek backend resolves to the canonical DeepSeek table.

    `pro` binds deepseek-v4-pro (thinking on, reasoning_effort "high").
    """
    s = Settings(provider_backend="deepseek", deepseek_api_key="k")
    b = get_binding("pro", settings=s)
    assert b is not None
    assert b.provider_id == "deepseek"
    assert b.model_id == "deepseek-v4-pro"
    # DeepSeek V4 pro post-promo full price.
    assert b.list_price_in_per_m == 1.74
    assert b.list_price_out_per_m == 3.48
    assert b.thinking is True
    assert b.reasoning_effort == "high"


def test_deepseek_per_tier_thinking_and_effort_config() -> None:
    """Per-tier thinking/effort intent on the canonical DeepSeek table:
    fast is non-thinking; smart thinks; pro thinks with high reasoning effort."""
    by_id = {b.tier.id: b for b in TIER_BINDINGS}
    # auto/fast/smart all serve deepseek-v4-flash; pro serves deepseek-v4-pro.
    assert by_id["auto"].model_id == "deepseek-v4-flash"
    assert by_id["fast"].model_id == "deepseek-v4-flash"
    assert by_id["smart"].model_id == "deepseek-v4-flash"
    assert by_id["pro"].model_id == "deepseek-v4-pro"
    # auto mirrors the smart baseline: thinking on, no explicit effort.
    assert by_id["auto"].thinking is True
    assert by_id["auto"].reasoning_effort is None
    assert by_id["fast"].thinking is False
    assert by_id["fast"].reasoning_effort is None
    assert by_id["smart"].thinking is True
    assert by_id["smart"].reasoning_effort is None
    assert by_id["pro"].thinking is True
    assert by_id["pro"].reasoning_effort == "high"


def test_get_binding_anthropic_backend_returns_anthropic_binding() -> None:
    """The explicit anthropic backend resolves to the Anthropic alternate table."""
    s = Settings(provider_backend="anthropic", anthropic_api_key="k")
    b = get_binding("pro", settings=s)
    assert b is not None
    assert b.provider_id == "anthropic"
    assert b.model_id == "claude-opus-4-7"
    assert b.list_price_in_per_m == 15.0


def test_get_binding_unknown_tier_is_none_under_openai() -> None:
    """An unknown tier id returns None even under the openai backend."""
    s = _openai_settings()
    assert get_binding("nope", settings=s) is None  # type: ignore[arg-type]


def test_list_tiers_and_known_tier_are_backend_independent() -> None:
    """Tier ids/labels/hints never change with the provider backend."""
    ids = [t.id for t in list_tiers()]
    assert ids == ["auto", "fast", "smart", "pro"]
    assert is_known_tier("smart") is True
    assert is_known_tier("fast") is True
    assert is_known_tier("bogus") is False
    # list_tiers() reflects the canonical table regardless of any backend env.
    assert [t.id for t in list_tiers()] == [b.tier.id for b in TIER_BINDINGS]


def test_resolve_served_tier_maps_auto_to_smart() -> None:
    """Auto requests must surface a concrete served tier on the wire so the FE's
    `assertServedTier` invariant in attribution-row.tsx doesn't trip."""
    auto = next(b for b in TIER_BINDINGS if b.tier.id == "auto")
    served_id, served_label = resolve_served_tier(auto)
    assert served_id == "smart"
    assert served_label == "Smart"


def test_resolve_served_tier_passes_concrete_tiers_through() -> None:
    """Concrete tier bindings (fast/smart/pro) resolve to their own id+label."""
    for tier_id in ("fast", "smart", "pro"):
        binding = next(b for b in TIER_BINDINGS if b.tier.id == tier_id)
        served_id, served_label = resolve_served_tier(binding)
        assert served_id == binding.tier.id
        assert served_label == binding.tier.label


def test_resolve_served_tier_works_for_openai_auto_binding() -> None:
    """Backend-aware bindings preserve the canonical `tier` object, so OpenAI's
    auto binding resolves to smart just like Anthropic's does."""
    s = _openai_settings()
    auto = get_binding("auto", settings=s)
    assert auto is not None
    served_id, served_label = resolve_served_tier(auto)
    assert served_id == "smart"
    assert served_label == "Smart"
