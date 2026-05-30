"""Provider abstraction: a swappable backend that streams model output.

Both `AnthropicProvider` and `FakeProvider` implement `Provider`. The streaming
handler consumes `ProviderEvent`s and maps them to wire SSE events.

`ProviderEvent` is an internal union — keep it tight to what the handler
needs. The wire schema (`schemas/stream_events.py`) stays the source of truth
for what the FE sees.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.schemas.common import SubstitutionReasonCode


@dataclass(frozen=True)
class ChatMessage:
    """Minimal chat message shape passed into the provider.

    Distinct from the wire `ChatMessage` (which carries parts, attribution,
    etc.) — the provider only needs role + text.
    """

    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    type: Literal["reasoning_delta"] = "reasoning_delta"
    text: str = ""


@dataclass(frozen=True)
class ReasoningDone:
    type: Literal["reasoning_done"] = "reasoning_done"


@dataclass(frozen=True)
class AnswerDelta:
    type: Literal["answer_delta"] = "answer_delta"
    text: str = ""


@dataclass(frozen=True)
class UsageUpdate:
    """Final accumulated usage from the provider.

    Field names match the canonical wire shape (see pricing.py for the
    Anthropic→canonical mapping). Reasoning tokens are billed at the output
    rate; cached input tokens are never cache-eligible for reasoning.
    """

    type: Literal["usage_update"] = "usage_update"
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class Complete:
    """End-of-stream marker. Provider has yielded everything.

    Optional substitution metadata (M4): when the provider had to swap to a
    fallback served (provider, model, display_label) for this turn, it sets
    `substitution` to one of the wire-allowed SubstitutionReasonCode values
    (string) and populates the `substituted_*` triple. The streaming handler
    threads these through to `build_attribution(...)`. For non-fallback turns
    these stay None and the wire attribution emits no `substitution` field.
    """

    type: Literal["complete"] = "complete"
    usage: UsageUpdate = field(default_factory=UsageUpdate)
    substitution: SubstitutionReasonCode | None = None
    substituted_provider: str | None = None
    substituted_model: str | None = None
    substituted_display_label: str | None = None


ProviderEvent = ReasoningDelta | ReasoningDone | AnswerDelta | UsageUpdate | Complete


class Provider(Protocol):
    """Swappable streaming backend.

    `stream(...)` returns an async iterator of ProviderEvents directly (no
    `await` on the call). Implementations may use `async def` + `yield` (the
    result is then an async generator, which is an AsyncIterator) or a class
    with `__aiter__`.

    Implementations MUST yield at most one `ReasoningDone` and only when at
    least one `ReasoningDelta` preceded it. The caller relies on this to
    emit the wire `reasoning_done` exactly once before any `answer_delta`.

    `complete(...)` is a non-streaming variant used for short, fire-and-forget
    calls (e.g. title autogen). Returns the assistant text as a single string;
    the implementation may use the streaming API internally but must not yield
    intermediate events to any caller.

    `api_key` is an optional per-call override for BYOK (M3). When provided,
    the implementation MUST use that key for the underlying provider call
    instead of its default credentials. Implementations that don't talk to a
    real provider (e.g. the fake) may ignore this argument.

    `thinking` / `reasoning_effort` are optional provider hints (DeepSeek V4
    dual-mode): `thinking` toggles the model's chain-of-thought (None = provider
    default, True = enabled, False = disabled) and `reasoning_effort` selects the
    effort level (e.g. "high"; None = omit). Implementations that don't support
    them ignore them.
    """

    def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[ProviderEvent]: ...

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str: ...
