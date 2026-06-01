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
    PROVIDER_ROUTES,
    TIER_BINDINGS,
    available_provider_backend_ids,
    get_binding,
    get_provider_route,
    is_known_tier,
    list_tiers,
    platform_provider_usable,
    require_available_provider_route,
    resolve_served_tier,
)
from app.schemas.tier import ModelTier


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
    # DeepSeek V4 pro post-promo adjusted price.
    assert b.list_price_in_per_m == 0.435
    assert b.list_price_out_per_m == 0.87
    assert b.cache_read_per_m == 0.003625
    assert b.thinking is True
    assert b.reasoning_effort == "high"


def test_deepseek_platform_availability_fallback_is_active_backend_only() -> None:
    assert platform_provider_usable(
        "deepseek",
        Settings(provider_backend="deepseek", openai_api_key="legacy-compatible"),
    )
    assert not platform_provider_usable(
        "deepseek",
        Settings(provider_backend="openai", openai_api_key="openai-platform-key"),
    )
    assert not platform_provider_usable(
        "openai",
        Settings(provider_backend="deepseek", openai_api_key="legacy-compatible"),
    )
    assert platform_provider_usable(
        "openai",
        Settings(
            provider_backend="deepseek",
            deepseek_api_key="deepseek-platform-key",
            openai_api_key="openai-platform-key",
        ),
    )


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
    # Curated model-disclosure labels (FE tier picker); auto is blank (varies).
    assert by_id["fast"].model_label == "DeepSeek V4 Flash"
    assert by_id["smart"].model_label == "DeepSeek V4 Flash"
    assert by_id["pro"].model_label == "DeepSeek V4 Pro"
    assert by_id["auto"].model_label == ""


def _openai_settings_tiers(**overrides: object) -> list[ModelTier]:
    base: dict[str, object] = {"provider_backend": "openai", "openai_api_key": "x"}
    base.update(overrides)
    return list_tiers(Settings(**base))  # type: ignore[arg-type]


def test_list_tiers_carries_active_backend_model_label() -> None:
    """`list_tiers` fills each wire tier's `model_label` from the ACTIVE
    backend's binding so the picker discloses the model that really answers."""
    # DeepSeek (canonical): friendly V4 names; auto blank.
    ds = {
        t.id: t.model_label
        for t in list_tiers(Settings(provider_backend="deepseek", deepseek_api_key="k"))
    }
    assert ds["fast"] == "DeepSeek V4 Flash"
    assert ds["pro"] == "DeepSeek V4 Pro"
    assert ds["auto"] == ""
    # Anthropic alternate: friendly Claude names; auto blank.
    an = {
        t.id: t.model_label
        for t in list_tiers(Settings(provider_backend="anthropic", anthropic_api_key="k"))
    }
    assert an["fast"] == "Claude Haiku 4.5"
    assert an["pro"] == "Claude Opus 4.7"
    assert an["auto"] == ""
    # OpenAI(-compatible): the operator-configured model id is the disclosure.
    oa = {t.id: t.model_label for t in _openai_settings_tiers(openai_model_pro="deepseek-reasoner")}
    assert oa["pro"] == "deepseek-reasoner"
    assert oa["auto"] == ""


def test_get_binding_anthropic_backend_returns_anthropic_binding() -> None:
    """The explicit anthropic backend resolves to the Anthropic alternate table."""
    s = Settings(provider_backend="anthropic", anthropic_api_key="k")
    b = get_binding("pro", settings=s)
    assert b is not None
    assert b.provider_id == "anthropic"
    assert b.model_id == "claude-opus-4-7"
    assert b.list_price_in_per_m == 15.0


def test_get_binding_provider_id_override_ignores_active_backend() -> None:
    """A per-request provider override selects that provider's binding only."""
    s = Settings(provider_backend="fake", openai_api_key="x")
    b = get_binding("smart", settings=s, provider_id="openai")
    assert b is not None
    assert b.provider_id == "openai"
    assert b.model_id == "gpt-4o"
    # The Settings object itself stays process-level fake.
    assert s.provider_backend == "fake"


def test_get_binding_explicit_fake_route_has_fake_provider_id() -> None:
    """Omitted fake keeps legacy DeepSeek BYOK semantics; explicit fake is fake."""
    s = Settings(provider_backend="fake")
    legacy = get_binding("smart", settings=s)
    explicit = get_binding("smart", settings=s, provider_id="fake")
    assert legacy is not None
    assert explicit is not None
    assert legacy.provider_id == "deepseek"
    assert explicit.provider_id == "fake"
    assert explicit.model_label == "Fake"


def test_get_binding_explicit_fake_route_disabled_in_production() -> None:
    """The dev/test fake adapter is not selectable in production."""
    s = Settings(provider_backend="deepseek", deepseek_api_key="k", env="production")
    assert get_binding("smart", settings=s, provider_id="fake") is None


def test_provider_route_registry_lists_available_and_pending_routes() -> None:
    """The provider route registry is the backend/source-of-truth for route policy."""
    by_id = {route.provider_id: route for route in PROVIDER_ROUTES}
    assert set(by_id) == {"deepseek", "anthropic", "openai", "gemini", "fake"}
    assert available_provider_backend_ids() == (
        "deepseek",
        "anthropic",
        "openai",
        "fake",
    )
    assert by_id["deepseek"].data_policy.trains_on_data is True
    assert by_id["deepseek"].data_policy.training_default == "opt_out"
    assert by_id["deepseek"].data_policy.policy_label == (
        "May train unless opted out; China data residency"
    )
    assert by_id["gemini"].status == "pending"
    assert by_id["gemini"].adapter is None
    assert by_id["gemini"].default_route_eligible is False
    assert by_id["gemini"].data_policy is None


def test_require_available_provider_route_rejects_pending_gemini() -> None:
    """Pending registry entries fail closed until a provider adapter is wired."""
    s = Settings(provider_backend="gemini")
    assert get_provider_route("gemini") is not None
    try:
        require_available_provider_route(s)
    except RuntimeError as exc:
        assert "PROVIDER_BACKEND='gemini'" in str(exc)
        assert "no available adapter" in str(exc)
    else:  # pragma: no cover - assertion branch only
        raise AssertionError("gemini route unexpectedly available")


def test_require_available_provider_route_rejects_fake_in_production() -> None:
    """The production guard also applies when the factory validates routes."""
    s = Settings(provider_backend="fake", env="production")
    try:
        require_available_provider_route(s)
    except RuntimeError as exc:
        assert "not allowed in production" in str(exc)
    else:  # pragma: no cover - assertion branch only
        raise AssertionError("fake route unexpectedly available in production")


def test_get_binding_gemini_pending_route_is_none() -> None:
    """A pending provider must not silently reuse the DeepSeek binding table."""
    s = Settings(provider_backend="gemini")
    assert get_binding("fast", settings=s) is None


def test_list_tiers_includes_provider_policy_metadata() -> None:
    """Bootstrap tiers carry active route metadata/data policy from the registry."""
    tiers = {
        t.id: t for t in list_tiers(Settings(provider_backend="anthropic", anthropic_api_key="k"))
    }
    fast = tiers["fast"]
    assert fast.provider_id == "anthropic"
    assert fast.provider_label == "Anthropic"
    assert fast.provider_route_status == "available"
    assert fast.default_route_eligible is True
    assert fast.data_policy is not None
    assert fast.data_policy.training_default == "never"
    assert fast.data_policy.retention_days == 30
    options = {option.provider_id: option for option in fast.provider_options}
    assert set(options) == {"deepseek", "anthropic", "openai", "gemini", "fake"}
    assert options["anthropic"].model_label == "Claude Haiku 4.5"
    assert options["anthropic"].status == "available"
    assert options["anthropic"].supports_attachments is True
    assert options["openai"].status == "unavailable"
    assert options["deepseek"].status == "unavailable"
    assert options["fake"].status == "available"
    assert options["gemini"].status == "pending"
    assert options["gemini"].model_label == ""
    assert options["gemini"].supports_web_search is False
    assert options["gemini"].default_route_eligible is False


def test_list_tiers_marks_byok_usable_provider_available() -> None:
    """Bootstrap can pass user BYOK providers into the runtime route catalog."""
    tiers = {
        t.id: t
        for t in list_tiers(
            Settings(provider_backend="fake"),
            usable_provider_ids={"fake", "openai"},
        )
    }
    options = {option.provider_id: option for option in tiers["fast"].provider_options}
    assert options["openai"].status == "available"
    assert options["anthropic"].status == "unavailable"


def test_list_tiers_marks_fake_unavailable_in_production() -> None:
    """Fake remains registered but is not operationally selectable in prod."""
    tiers = {
        t.id: t
        for t in list_tiers(
            Settings(
                provider_backend="deepseek",
                deepseek_api_key="k",
                env="production",
            )
        )
    }
    options = {option.provider_id: option for option in tiers["fast"].provider_options}
    assert options["deepseek"].status == "available"
    assert options["fake"].status == "unavailable"


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


# Web search capability --------------------------------------------------------


def test_all_canonical_bindings_support_web_search() -> None:
    """Every real DeepSeek tier binding advertises the provider-capability half
    (the tool loop / server tool); the wire flag is gated separately on a
    configured search backend in `list_tiers`."""
    for binding in TIER_BINDINGS:
        assert binding.supports_web_search is True, binding.tier.id


def test_alternate_backend_bindings_support_web_search() -> None:
    """The OpenAI and Anthropic alternate bindings also support web search."""
    oa = _openai_settings()
    for tier_id in ("auto", "fast", "smart", "pro"):
        ob = get_binding(tier_id, settings=oa)  # type: ignore[arg-type]
        assert ob is not None
        assert ob.supports_web_search is True
    an = Settings(provider_backend="anthropic", anthropic_api_key="k")
    for tier_id in ("auto", "fast", "smart", "pro"):
        ab = get_binding(tier_id, settings=an)  # type: ignore[arg-type]
        assert ab is not None
        assert ab.supports_web_search is True


def test_attachment_support_tracks_native_provider_payload_support() -> None:
    """Attachment support is only advertised when bytes reach the provider."""
    deepseek = Settings(provider_backend="deepseek", deepseek_api_key="k")
    assert all(
        get_binding(tier_id, settings=deepseek).supports_attachments is False  # type: ignore[union-attr]
        for tier_id in ("auto", "fast", "smart", "pro")
    )

    fake = Settings(provider_backend="fake")
    assert get_binding("smart", settings=fake).supports_attachments is True  # type: ignore[union-attr]

    openai = _openai_settings()
    assert get_binding("smart", settings=openai).supports_attachments is True  # type: ignore[union-attr]

    anthropic = Settings(provider_backend="anthropic", anthropic_api_key="k")
    assert get_binding("smart", settings=anthropic).supports_attachments is True  # type: ignore[union-attr]


def test_list_tiers_gates_supports_web_search_on_search_enabled() -> None:
    """`list_tiers` sets the wire flag = binding.supports_web_search AND
    search_enabled(settings). With a configured backend (`fake`) the flag is
    True for every tier; with `none` it is False even though every binding
    supports search at the provider level."""
    # `search_backend` carries the env alias `SEARCH_BACKEND`; pydantic-settings
    # populates aliased fields by their alias, not the field name, so pass the
    # alias key (a bare `search_backend=` kwarg would be ignored in favor of the
    # process env, which conftest sets to `fake`).
    on = {
        t.id: t.supports_web_search
        for t in list_tiers(
            Settings(  # type: ignore[call-arg]
                provider_backend="deepseek",
                deepseek_api_key="k",
                SEARCH_BACKEND="fake",
            )
        )
    }
    assert all(on.values())
    assert set(on) == {"auto", "fast", "smart", "pro"}

    off = {
        t.id: t.supports_web_search
        for t in list_tiers(
            Settings(  # type: ignore[call-arg]
                provider_backend="deepseek",
                deepseek_api_key="k",
                SEARCH_BACKEND="none",
            )
        )
    }
    assert not any(off.values())


def test_list_tiers_supports_web_search_false_when_tavily_key_missing() -> None:
    """`tavily` backend with no key is NOT search-enabled, so the wire flag is
    False even though the bindings support search."""
    tiers = list_tiers(
        Settings(  # type: ignore[call-arg]
            provider_backend="deepseek",
            deepseek_api_key="k",
            SEARCH_BACKEND="tavily",
        )
    )
    assert all(t.supports_web_search is False for t in tiers)


def test_list_tiers_anthropic_hosted_web_search_ignores_search_backend() -> None:
    """Anthropic uses hosted web search, so SEARCH_BACKEND is irrelevant."""
    tiers = list_tiers(
        Settings(  # type: ignore[call-arg]
            provider_backend="anthropic",
            anthropic_api_key="k",
            SEARCH_BACKEND="none",
        )
    )
    assert all(t.supports_web_search is True for t in tiers)
