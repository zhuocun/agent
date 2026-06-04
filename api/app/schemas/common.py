"""Shared Pydantic config and enums for the wire layer.

`CamelModel` is the base for every response model: snake_case in Python,
camelCase on the JSON wire via `alias_generator=to_camel`. `populate_by_name`
keeps server-side construction ergonomic (`Model(field_name=...)` works), and
serialization is always `by_alias=True` so the wire stays consistent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for wire schemas. snake_case in, camelCase out.

    Whitespace handling: NOT auto-stripped. `str_strip_whitespace=True` here
    would silently mutate every string field on construction — fine for an
    input-validation reflex, catastrophic for opaque payloads. The two
    concrete cases that bit us:

    1. Streaming text deltas (`AnswerDeltaEvent.text`, `ReasoningDeltaEvent
       .text`) carry single tokens including their leading/trailing spaces;
       auto-strip turns `" ready"` into `"ready"` on every chunk and the FE
       renders `"I'mready"`.
    2. Passwords (`UpgradeRequest.password`) must preserve user-supplied
       whitespace; silently trimming them changes the credential the user
       believes they set.

    Schemas that genuinely want input cleaning (e.g. a title field) should
    do it explicitly via a Pydantic `field_validator`, not via a base-class
    default that affects unrelated fields.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
    )


# Wire enums kept tight to what the FE renders. See web/src/lib/types.ts.
ModelTierId = Literal["fast", "smart", "pro", "auto"]
# Per-turn reasoning-effort override the FE composer can attach. `auto` defers to
# the tier binding's default; `minimal` forces thinking OFF for a real latency
# win; `standard`/`extended` map to provider effort levels. Providers that don't
# support effort hints ignore them (it's a hint, never an error).
ReasoningEffortId = Literal["auto", "minimal", "standard", "extended"]
StreamStatus = Literal["idle", "submitted", "streaming", "done", "stopped", "error"]
Feedback = Literal["up", "down"]  # null serialized as `feedback: null` on the wire

# The six SubstitutionReasonCodes the FE renders. PRD-only codes
# (`auto_route`, `budget_cap`, `policy_route`) are intentionally excluded —
# they ship when the FE renders them.
SubstitutionReasonCode = Literal[
    "auto_downgrade",
    "provider_fallback",
    "rate_limited",
    "capacity_reroute",
    "deprecated_model",
    "gateway_route",
]

CostConfidence = Literal["exact", "estimate"]

SpeedHint = Literal["fastest", "fast", "balanced", "slow"]
CostHint = Literal["lowest", "low", "medium", "high"]

MessageRole = Literal["user", "assistant"]
