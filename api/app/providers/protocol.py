"""Provider abstraction: a swappable backend that streams model output.

DeepSeek/OpenAI-compatible, Anthropic, and fake providers implement `Provider`.
The streaming handler consumes `ProviderEvent`s and maps them to wire SSE
events.

`ProviderEvent` is an internal union — keep it tight to what the handler
needs. The wire schema (`schemas/stream_events.py`) stays the source of truth
for what the FE sees.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.schemas.common import SubstitutionReasonCode
from app.search.protocol import SourceItem
from app.tools.protocol import ToolApprovalState, ToolRunStatus


@dataclass(frozen=True)
class ChatMessage:
    """Minimal chat message shape passed into the provider.

    Distinct from the wire `ChatMessage` (which carries parts, attribution,
    etc.) — the provider only needs role + text.
    """

    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class AttachmentPayload:
    """Transient user attachment passed to providers for the current turn.

    `data` is intentionally provider-only and must never be persisted in message
    history. Regenerated turns may have metadata but no bytes because historical
    raw payloads are stripped before storage. `extracted_text` is also transient:
    it is derived from the current request payload and is never persisted.
    """

    id: str
    name: str
    media_type: Literal["image", "pdf", "text"]
    mime_type: str
    size_bytes: int
    data: bytes | None = None
    extracted_text: str | None = None


def text_with_attachment_fallback(
    user_text: str,
    attachments: list[AttachmentPayload] | None,
) -> str:
    """Append provider-neutral attachment metadata/transcripts to a prompt."""
    if not attachments:
        return user_text
    prompt_text = user_text if user_text.strip() else "Please analyze the attached file(s)."
    lines = [
        prompt_text,
        "",
        "Attached files for this turn "
        "(raw bytes are request-only and are not stored):",
    ]
    for attachment in attachments:
        lines.append(
            f"- {attachment.name} ({attachment.mime_type}, "
            f"{attachment.size_bytes} bytes)"
        )
        if attachment.extracted_text:
            lines.extend(
                [
                    f"  Extracted text from {attachment.name}:",
                    attachment.extracted_text,
                ]
            )
    return "\n".join(lines)


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
class StatusUpdate:
    """Generic streamed status line (e.g. "Searching the web…").

    `state` toggles between an in-progress (`active`) and finished (`done`)
    rendering of the same `label`. The web-search loop emits an `active` line
    when it dispatches the search and a `done` line when results return.
    """

    label: str
    state: Literal["active", "done"]
    type: Literal["status_update"] = "status_update"


@dataclass(frozen=True)
class Sources:
    """The resolved source / citation list for a web-search turn.

    `items` is the ordered (1-based id) `SourceItem` list the search backend
    returned; the handler maps it to the wire `sources` event and the FE
    renders inline citations keyed on `id`.
    """

    items: list[SourceItem] = field(default_factory=list)
    type: Literal["sources"] = "sources"


@dataclass(frozen=True)
class ToolCall:
    """A provider/tool loop requested a tool call."""

    id: str
    name: str
    label: str | None = None
    status: ToolRunStatus = "running"
    approval_state: ToolApprovalState = "not_required"
    input: dict[str, Any] | None = None
    type: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True)
class ToolResult:
    """A provider/tool loop completed a tool call."""

    tool_call_id: str
    name: str
    label: str | None = None
    status: ToolRunStatus = "succeeded"
    approval_state: ToolApprovalState = "not_required"
    summary: str | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    type: Literal["tool_result"] = "tool_result"


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


ProviderEvent = (
    ReasoningDelta
    | ReasoningDone
    | AnswerDelta
    | StatusUpdate
    | Sources
    | ToolCall
    | ToolResult
    | UsageUpdate
    | Complete
)


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

    `web_search` opts the turn into the `web_search` tool: when True AND a
    search backend is configured, the implementation may run a real web search
    mid-stream and emit `StatusUpdate` + `Sources` events around the grounded
    answer. When False (the default), behavior is byte-for-byte unchanged — no
    tools are advertised. Implementations with no search backend available
    treat True as a no-op.

    `supports_vision` reflects whether the active binding can INTERPRET images
    and native PDF *document* blocks. When False (the default), the real-provider
    adapters MUST NOT emit native image/PDF-document content blocks: images are
    dropped and PDFs degrade to their `extracted_text` transcript only. The route
    rejects images to a non-vision binding before reaching the provider, so this
    flag is defense-in-depth at the adapter. Text attachments always flow as
    transcript regardless of this flag.
    """

    def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[AttachmentPayload] | None = None,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
        web_search: bool = False,
        supports_vision: bool = True,
    ) -> AsyncIterator[ProviderEvent]: ...

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str: ...
