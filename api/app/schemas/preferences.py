"""UserPreferences schema."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import CamelModel, ModelTierId, ReasoningEffortId

CustomInstructions = Annotated[str, StringConstraints(max_length=4000)]


class ShortcutOverride(CamelModel):
    """A single user-supplied keyboard-shortcut override (D23).

    Mirrors the FE `ShortcutKeys` shape that the live keydown matcher and the
    shortcuts dialog consume (`web/src/lib/use-keyboard-shortcuts.ts`). Only the
    matcher-significant fields are persisted: `key` is required; `mod` (Cmd on
    Mac / Ctrl elsewhere) and `shift` default to False. `allowInInput` is NOT
    stored — it is a per-action display/behavior trait owned by the built-in
    default, never by an override.
    """

    # The matcher lower-cases single-character keys and compares named keys
    # verbatim, so keep the value permissive but non-empty.
    key: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    mod: bool = False
    shift: bool = False


# The override map: stable `ShortcutId` -> override combo. Keyed by the FE's
# action ids; values validated as `ShortcutOverride`. An empty/missing entry for
# an action means "use the built-in default". Unknown ids are accepted (and
# simply ignored by the FE resolver) so a newer client that adds an action can
# round-trip its overrides through an older server without data loss.
KeyboardShortcuts = dict[str, ShortcutOverride]


class UserPreferences(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool
    telemetry_enabled: bool
    custom_instructions: CustomInstructions = ""
    # None means "retain forever"; finite choices stay intentionally narrow.
    retention_days: Literal[30, 90] | None = None
    # User-set monthly platform-spend cap in USD. None means "no user cap" (only
    # the operator's `USAGE_BUDGET_USD` applies, if any). When both are set the
    # lower one wins (see `usage._effective_quota_usd`).
    monthly_budget_usd: float | None = None
    # User-set per-conversation platform-spend ceiling in USD. None means "no
    # per-conversation cap". Enforced in the send-gate for platform-key turns
    # (BYOK/temporary turns are exempt) once a conversation's accumulated
    # assistant cost reaches it.
    per_conversation_budget_usd: float | None = None
    # Transparent long-term memory opt-in (D19). OFF by default. When True (and
    # the turn is not temporary) the user's saved facts are injected into the
    # turn — see `app.streaming.handler._apply_memory`.
    memory_enabled: bool = False
    # User remaps of the app's keyboard shortcuts (D23). Empty map = every action
    # uses its built-in default; each entry overrides one action's combo. The
    # effective binding (default merged with override) drives both the live
    # matcher and the shortcuts dialog on the FE.
    keyboard_shortcuts: KeyboardShortcuts = Field(default_factory=dict)
    # Persisted Model/Reasoning popup selections. These mirror the per-turn
    # composer controls so a returning session reopens with the user's last
    # choices instead of the hard defaults.
    #
    # Default per-turn reasoning effort. "auto" defers to the tier binding's
    # default (the privacy/latency-neutral baseline).
    default_reasoning_effort_id: ReasoningEffortId = "auto"
    # Preferred provider id from the model popup. None = no explicit preference
    # (the platform routes to its default). Kept as an opaque string — the BE
    # does not enumerate provider ids in the wire enum so a newer client can
    # round-trip a provider the server doesn't yet know about.
    default_provider_id: str | None = None
    # Composer toggles persisted from the popup. All OFF by default to keep the
    # baseline turn cheap and private.
    web_search_default: bool = False
    json_mode_default: bool = False
    deep_research_default: bool = False


class UserPreferencesRequest(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool
    telemetry_enabled: bool | None = None
    custom_instructions: CustomInstructions | None = None
    # None means "retain forever"; finite choices stay intentionally narrow.
    retention_days: Literal[30, 90] | None = None
    # User-set monthly platform-spend cap in USD. Non-negative; None clears it.
    monthly_budget_usd: Annotated[float, Field(ge=0)] | None = None
    # User-set per-conversation platform-spend ceiling in USD. Non-negative;
    # None clears it.
    per_conversation_budget_usd: Annotated[float, Field(ge=0)] | None = None
    # Transparent long-term memory opt-in (D19). Optional for stale clients;
    # omission preserves the existing saved value (mirrors `telemetry_enabled`).
    memory_enabled: bool | None = None
    # Keyboard-shortcut remaps (D23). Optional for stale clients; omission
    # preserves the existing saved map (mirrors `telemetry_enabled`). When
    # present the map fully replaces the saved one (an empty map clears all
    # overrides back to defaults).
    keyboard_shortcuts: KeyboardShortcuts | None = None
    # Persisted Model/Reasoning popup selections. Optional for stale clients;
    # omission preserves the existing saved value (mirrors `telemetry_enabled`).
    default_reasoning_effort_id: ReasoningEffortId | None = None
    # Preferred provider id from the model popup. Optional; omission preserves
    # the existing saved value. The popup always sends an explicit value (a
    # concrete id, or `null` to clear back to "no preference").
    default_provider_id: str | None = None
    web_search_default: bool | None = None
    json_mode_default: bool | None = None
    deep_research_default: bool | None = None
