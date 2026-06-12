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
class ToolDefinition:
    """A provider-neutral description of a backend tool to advertise to the model.

    Threaded into `Provider.stream(..., tools=[...])` when `TOOLS_ENABLED` so a
    REAL provider (OpenAI-compatible / Anthropic) advertises the built-in tool
    registry natively and parses the model's tool calls into structured
    `ToolCall` events for the agent loop (see `app/tools/agent_loop.py`). Each
    adapter maps this neutral shape to its own native tool schema:
    OpenAI `{"type":"function","function":{name,description,parameters}}`,
    Anthropic `{name,description,input_schema}`.

    `parameters` is a JSON-Schema object describing the tool's input (the same
    `ToolSpec.schema` the registry holds). `label` is the human-facing name used
    for the wire `ToolCall.label` and as the model-facing description.
    """

    name: str
    label: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResponseFormat:
    """Structured-output request threaded into `Provider.stream(...)`.

    `type="json_object"` asks the model for any single valid JSON value;
    `type="json_schema"` additionally constrains it to `schema` (JSON Schema).
    Adapters degrade gracefully: a backend that can't enforce a schema natively
    (DeepSeek, Anthropic) injects the schema into a system instruction and falls
    back to plain json-object mode. The handler validates the final text at the
    boundary regardless of how the provider enforced (or failed to enforce) it.
    """

    type: Literal["json_object", "json_schema"]
    schema: dict[str, Any] | None = None


# Agentic mode (multi-agent orchestration): every content/usage event MAY carry
# a `subagent_id` tagging the orchestrator subagent (worker / aggregator /
# primary) that produced it. None on every non-agentic path — the orchestrator
# (`app/agentic/orchestrator.py`) is the ONLY producer that sets it, so the
# field is invisible (omitted from the wire via `exclude_none`) for every
# existing single-stream turn and the flag-off path stays byte-for-byte
# identical.
@dataclass(frozen=True)
class ReasoningDelta:
    type: Literal["reasoning_delta"] = "reasoning_delta"
    text: str = ""
    subagent_id: str | None = None


@dataclass(frozen=True)
class ReasoningDone:
    type: Literal["reasoning_done"] = "reasoning_done"


@dataclass(frozen=True)
class AnswerDelta:
    type: Literal["answer_delta"] = "answer_delta"
    text: str = ""
    subagent_id: str | None = None


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
    subagent_id: str | None = None


@dataclass(frozen=True)
class Sources:
    """The resolved source / citation list for a web-search turn.

    `items` is the ordered (1-based id) `SourceItem` list the search backend
    returned; the handler maps it to the wire `sources` event and the FE
    renders inline citations keyed on `id`.
    """

    items: list[SourceItem] = field(default_factory=list)
    type: Literal["sources"] = "sources"
    subagent_id: str | None = None


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
    subagent_id: str | None = None


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
    subagent_id: str | None = None


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
    subagent_id: str | None = None


@dataclass(frozen=True)
class AwaitingApproval:
    """Agent-loop "pause here" marker for a human-in-the-loop tool gate.

    Emitted by the agent loop (NOT by a real provider's own stream) right after
    a `ToolCall(status="awaiting_approval", approval_state="pending")` when the
    requested tool needs approval and none has been granted yet. It is the
    analogue of `Complete`: it ENDS the provider event stream for this turn, but
    instead of finalizing the turn as `done` the handler persists the assistant
    row as `awaiting_approval` and frees the active-stream guard so a follow-up
    resume POST can open its own stream. `tool_call_id` identifies the gated call
    the resume must decide.
    """

    tool_call_id: str
    type: Literal["awaiting_approval"] = "awaiting_approval"
    subagent_id: str | None = None


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
    subagent_id: str | None = None


@dataclass(frozen=True)
class SubagentStarted:
    """Agentic mode: a subagent (primary / worker / aggregator) began streaming.

    Emitted by the orchestrator BEFORE any of that subagent's tagged content
    events so the handler (and FE) can open a transcript section keyed on
    `subagent_id`. `role` distinguishes the orchestration role (`primary` for the
    single-loop turn, `worker` / `aggregator` for deep-research fan-out); `label`
    is the human-facing name.
    """

    subagent_id: str
    label: str
    role: str
    type: Literal["subagent_started"] = "subagent_started"


@dataclass(frozen=True)
class SubagentDone:
    """Agentic mode: a subagent finished streaming.

    Carries that subagent's accumulated `usage` and computed `cost_usd` so the
    handler can attribute per-subagent cost and the FE can render a per-subagent
    spend chip. `label` / `role` echo the matching `SubagentStarted` so a late
    subscriber that missed the start can still render the section.
    """

    subagent_id: str
    label: str | None = None
    role: str | None = None
    usage: UsageUpdate = field(default_factory=UsageUpdate)
    cost_usd: float | None = None
    type: Literal["subagent_done"] = "subagent_done"


@dataclass(frozen=True)
class RunCost:
    """Agentic mode: the running cost subtotal for the whole orchestration run.

    `subtotal_usd` is the sum of every subagent's cost so far; `cap_usd` is the
    configured per-run budget (`AGENTIC_RUN_BUDGET_USD`). The orchestrator
    enforces the cap via admission + mid-flight kill; this event surfaces live
    subtotal vs cap to the FE.
    """

    subtotal_usd: float
    cap_usd: float
    type: Literal["run_cost"] = "run_cost"


ProviderEvent = (
    ReasoningDelta
    | ReasoningDone
    | AnswerDelta
    | StatusUpdate
    | Sources
    | ToolCall
    | ToolResult
    | UsageUpdate
    | AwaitingApproval
    | Complete
    | SubagentStarted
    | SubagentDone
    | RunCost
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

    `response_format` opts the turn into structured output (JSON mode). When set,
    the implementation asks the model to answer as JSON: `json_object` is any
    single valid JSON value; `json_schema` additionally constrains it to the
    provided JSON Schema. Implementations enforce this best-effort — a backend
    with native support (true OpenAI) uses the API parameter; backends without
    it (DeepSeek strict schema, Anthropic) degrade to a system instruction and/or
    plain json-object mode. Implementations that don't support it at all degrade
    gracefully (best-effort, never error). The streaming handler validates the
    accumulated text at the boundary regardless, surfacing the result on
    `ModelAttribution.output_valid`. When None (the default), behavior is
    byte-for-byte unchanged.

    `system_prefix` is a cache-stable system preamble (custom instructions +
    long-term memory facts, assembled by `app/prompt_assembly.py`). When set,
    the implementation prepends it as a system message (OpenAI-compatible) or
    passes it as the top-level `system` prompt (Anthropic) so a cache-aware
    backend can reuse the unchanged prefix across turns. When None (the
    default) no system preamble is sent and behavior is byte-for-byte
    unchanged. Implementations that can't carry a system role (e.g. the fake)
    accept it for Protocol conformance and ignore it.

    `tools` opts the turn into backend tool calling driven by the agent loop
    (`app/tools/agent_loop.py`). When a non-empty list is passed (the handler
    only does so when `TOOLS_ENABLED`), the implementation advertises those tools
    to the model natively and, when the model requests one, emits a `ToolCall`
    event and STOPS the round (no `Complete`) so the agent loop can execute the
    tool, apply the human-in-the-loop approval gate, and re-invoke `stream(...)`
    with the result fed back through `history` (a sentinel-prefixed turn the
    adapter reconstructs into native tool-result messages). A real provider that
    natively supports tools wires this; implementations that don't (the fake)
    ignore `tools` and rely on their own deterministic markers. When None/empty
    (the default), no tools are advertised and behavior is byte-for-byte
    unchanged. `tools` composes with `web_search` (the hosted/internal
    web-search tool stays separate).
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
        response_format: ResponseFormat | None = None,
        system_prefix: str | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[ProviderEvent]: ...

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
        system_prefix: str | None = None,
    ) -> str: ...
