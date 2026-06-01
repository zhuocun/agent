"""OpenAI(-compatible) Chat Completions adapter.

Maps `client.chat.completions.create(..., stream=True)` chunks to our internal
`ProviderEvent`s. Mirrors `anthropic.py` in shape, streaming contract, usage
accounting, and error mapping so the rest of the system stays provider-agnostic.

Notable differences from the Anthropic adapter:

- Reasoning-text streaming is path-dependent. Stock OpenAI Chat Completions does
  NOT stream the model's reasoning content; it only reports `reasoning_tokens` in
  usage. DeepSeek's OpenAI-compatible endpoint, however, DOES surface the
  chain-of-thought as a separate `delta.reasoning_content` field, which we now
  forward as `ReasoningDelta`/`ReasoningDone`. The field is absent/None on stock
  OpenAI (and o-series) responses, so reading it is a safe no-op there (zero
  reasoning events is a legal stream per the Provider Protocol). Either way,
  reasoning is billed at the output rate via the usage buckets below.

- Disjoint usage buckets (THE correctness detail). `pricing.compute_cost_breakdown`
  sums FOUR buckets independently:
      input*in + output*out + reasoning*out + cached_input*cache
  so the buckets MUST be disjoint or we double-bill. OpenAI's usage is NOT
  disjoint: `prompt_tokens` INCLUDES `prompt_tokens_details.cached_tokens`, and
  `completion_tokens` INCLUDES `completion_tokens_details.reasoning_tokens`.
  We therefore subtract the overlaps:
      cached_input_tokens = cached_tokens
      input_tokens        = max(prompt_tokens - cached_tokens, 0)
      reasoning_tokens     = reasoning_tokens
      output_tokens        = max(completion_tokens - reasoning_tokens, 0)

- `stream_options={"include_usage": True}` is REQUIRED to get a usage object on
  a streaming call — it arrives in the final chunk (which carries empty
  `choices`). Some OpenAI-compatible endpoints ignore it; we then leave all
  buckets at 0.

- `max_completion_tokens` (NOT `max_tokens`). The o-series models (the `pro`
  default `o1`) reject the legacy `max_tokens` parameter.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import openai
import structlog
from openai import AsyncOpenAI

from app.errors import AppError, ErrorEnvelope
from app.providers._tool_markup import ToolMarkupSanitizer
from app.providers.protocol import (
    AnswerDelta,
    AttachmentPayload,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    Sources,
    StatusUpdate,
    ToolCall,
    ToolResult,
    UsageUpdate,
    text_with_attachment_fallback,
)
from app.providers.steering import steer_user_text
from app.search.protocol import SearchProvider, SourceItem

_log = structlog.get_logger(__name__)

# OpenAI function-tool schema advertised when `web_search=True` AND a search
# backend is wired. The model decides (tool_choice="auto") whether to call it.
# CRITICAL: the schema stays advertised on EVERY round of the agentic loop so the
# OpenAI-compatible endpoint parses tool calls into STRUCTURED `delta.tool_calls`
# instead of leaking the raw tool-call special tokens into `delta.content`. We
# run the configured `SearchProvider`, feed results back as a tool-result
# message, and loop until the model answers without calling the tool (or the
# round cap forces an answer).
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the public web for current, factual, or citable information. "
            "Use this when the answer depends on recent events or facts you are "
            "unsure about. Returns a ranked list of sources with titles, URLs, and "
            "snippets that you should ground your answer in and cite as [1], [2], …"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to run against the web.",
                },
            },
            "required": ["query"],
        },
    },
}

_SEARCH_STATUS_LABEL = "Searching the web…"
_MAX_SEARCH_RESULTS = 5
# Hard cap on web-search tool-call rounds to prevent an infinite tool loop. On
# the FINAL round we force `tool_choice="none"` so the model is compelled to
# answer; the streaming sanitizer scrubs any residual leaked markup.
_MAX_SEARCH_ROUNDS = 4
# Cap the model-emitted query length before it reaches the search backend. The
# model can emit an arbitrarily long `query` argument; bound it so a runaway
# value can't bloat the upstream request.
_MAX_SEARCH_QUERY_CHARS = 512


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _openai_attachment_part(attachment: AttachmentPayload) -> dict[str, Any] | None:
    """Map a transient attachment into Chat Completions multimodal content."""
    if attachment.data is None:
        return None
    encoded = _b64(attachment.data)
    if attachment.media_type == "image":
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{attachment.mime_type};base64,{encoded}",
            },
        }
    if attachment.media_type == "pdf":
        return {
            "type": "file",
            "file": {
                "filename": attachment.name,
                "file_data": f"data:{attachment.mime_type};base64,{encoded}",
            },
        }
    return None


def _openai_user_content(
    user_text: str,
    attachments: list[AttachmentPayload] | None,
) -> str | list[dict[str, Any]]:
    """Build the current user content, including native attachment bytes."""
    if not attachments:
        return steer_user_text(user_text)

    content: list[dict[str, Any]] = []
    metadata_only: list[AttachmentPayload] = []
    for attachment in attachments:
        part = _openai_attachment_part(attachment)
        if part is None:
            metadata_only.append(attachment)
        else:
            content.append(part)

    text = text_with_attachment_fallback(user_text, metadata_only) if metadata_only else user_text
    prompt = steer_user_text(text)
    if not content:
        return prompt
    content.append(
        {
            "type": "text",
            "text": prompt or "Please analyze the attached file(s).",
        }
    )
    return content


def _safe_int(value: Any) -> int:
    """Coerce SDK usage fields (often `int | None`) to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class _UsageAccumulator:
    """Sums the raw OpenAI usage buckets across one or more completions.

    The web-search path makes one completion PER ROUND of the agentic tool loop
    (tool-call rounds + the final grounded answer); each carries its own `usage`
    object on its final chunk. We add the raw (still-overlapping) OpenAI counts
    here, then compute the four DISJOINT buckets once in `to_usage_update()` so
    the subtraction (prompt minus cached, completion minus reasoning) is applied
    to the summed totals, never double-counted.
    """

    def __init__(self) -> None:
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._reasoning_tokens = 0
        self._cached_input_tokens = 0

    def add(self, usage_obj: Any) -> None:
        """Add one completion's raw usage object to the running totals."""
        self._prompt_tokens += _safe_int(getattr(usage_obj, "prompt_tokens", None))
        self._completion_tokens += _safe_int(getattr(usage_obj, "completion_tokens", None))
        prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
        completion_details = getattr(usage_obj, "completion_tokens_details", None)
        cached = max(_safe_int(getattr(prompt_details, "cached_tokens", None)), 0)
        # DeepSeek reports cache hits at the TOP LEVEL as `prompt_cache_hit_tokens`
        # (not under `prompt_tokens_details.cached_tokens`), so fall back to it
        # when the standard nested field is absent/zero — otherwise DeepSeek cache
        # discounts would never apply.
        if cached == 0:
            cached = max(_safe_int(getattr(usage_obj, "prompt_cache_hit_tokens", None)), 0)
        self._cached_input_tokens += cached
        self._reasoning_tokens += max(
            _safe_int(getattr(completion_details, "reasoning_tokens", None)), 0
        )

    def to_usage_update(self) -> UsageUpdate:
        """Compute the four DISJOINT buckets from the summed raw totals.

        OpenAI usage overlaps:
          prompt_tokens     includes prompt_tokens_details.cached_tokens
          completion_tokens includes completion_tokens_details.reasoning_tokens
        so we subtract the overlaps to avoid double-billing (pricing sums the four
        buckets independently). No usage seen at all leaves everything at 0.
        """
        input_tokens = max(self._prompt_tokens - self._cached_input_tokens, 0)
        output_tokens = max(self._completion_tokens - self._reasoning_tokens, 0)
        return UsageUpdate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=self._reasoning_tokens,
            cached_input_tokens=self._cached_input_tokens,
        )


class _ToolCallAccumulator:
    """Reassembles one streamed OpenAI `tool_call` from its delta fragments.

    OpenAI streams a tool call across many chunks: the `id` and
    `function.name` arrive once (on the first fragment for that index), then
    `function.arguments` arrives in pieces that must be concatenated.
    """

    def __init__(self) -> None:
        self.id: str | None = None
        self.name: str | None = None
        self.arguments: str = ""

    def update(self, tc: Any) -> None:
        tc_id = getattr(tc, "id", None)
        if tc_id:
            self.id = tc_id
        fn = getattr(tc, "function", None)
        if fn is not None:
            name = getattr(fn, "name", None)
            if name:
                self.name = name
            args = getattr(fn, "arguments", None)
            if args:
                self.arguments += args


def _accumulate_tool_calls(delta: Any, acc: dict[int, _ToolCallAccumulator]) -> None:
    """Fold a chunk's `delta.tool_calls` fragments into the per-index accumulators."""
    tool_calls = getattr(delta, "tool_calls", None)
    if not tool_calls:
        return
    for tc in tool_calls:
        index = getattr(tc, "index", 0) or 0
        acc.setdefault(index, _ToolCallAccumulator()).update(tc)


def _select_web_search_calls(
    acc: dict[int, _ToolCallAccumulator] | None,
) -> list[_ToolCallAccumulator]:
    """Return all accumulated calls whose function name is `web_search`, in order.

    A round may emit more than one `web_search` call (the model parallel-searches);
    we run each and feed back one tool-result message per call so the assistant
    tool-call turn and the tool-result turns stay paired (OpenAI requires every
    `tool_calls[*].id` to be answered by a matching `role="tool"` message).
    """
    if not acc:
        return []
    return [acc[index] for index in sorted(acc) if acc[index].name == "web_search"]


def _dedupe_and_renumber(items: list[SourceItem]) -> list[SourceItem]:
    """Dedup sources by url (first occurrence wins) and renumber ids 1..N.

    Sources accumulate across rounds; the same url can surface in multiple
    searches. We keep the first occurrence's display fields and reassign a
    coherent 1-based ordinal so the final `Sources`/citation ids are contiguous.
    """
    seen: set[str] = set()
    out: list[SourceItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        out.append(item.model_copy(update={"id": len(out) + 1}))
    return out


def _parse_query(raw_arguments: str) -> str:
    """Parse the `query` field out of a tool call's JSON arguments string.

    Tolerant: malformed / missing JSON yields an empty query (the caller then
    short-circuits with empty sources rather than crashing on a model that
    emitted bad arguments). The returned query is length-capped so a runaway
    model-emitted value can't bloat the search backend request.
    """
    try:
        parsed = json.loads(raw_arguments or "{}")
    except (ValueError, TypeError):
        return ""
    if isinstance(parsed, dict):
        query = parsed.get("query")
        if isinstance(query, str):
            return query[:_MAX_SEARCH_QUERY_CHARS]
    return ""


def _retry_after_ms(exc: openai.RateLimitError) -> int | None:
    """Best-effort `retryAfterMs` from a rate-limit response's headers.

    Mirrors the SDK's own precedence: the non-standard millisecond header
    `retry-after-ms` wins, else integer/float `retry-after` seconds. Returns
    None when neither header is present or parseable.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    ms_header = headers.get("retry-after-ms")
    if ms_header is not None:
        try:
            return int(float(ms_header))
        except (TypeError, ValueError):
            pass
    sec_header = headers.get("retry-after")
    if sec_header is not None:
        try:
            return int(float(sec_header) * 1000)
        except (TypeError, ValueError):
            pass
    return None


def _map_sdk_error(exc: openai.APIError) -> AppError:
    """Translate an OpenAI SDK error into a typed `AppError`.

    Rate limits become `RATE_LIMITED` (429) with `retryAfterMs` when the
    upstream response carries a retry-after header; everything else becomes
    `PROVIDER_UPSTREAM` (502, or 503 for explicit unavailability/overload). The
    raw SDK message is never placed in the user-facing `body` — only a clean
    generic string. The original exception is left for the caller to log.

    Note: `openai.APIConnectionError` is an `APIError` but NOT an
    `APIStatusError` (it has no `.status_code`); the isinstance guard below
    keeps it at 502.
    """
    if isinstance(exc, openai.RateLimitError):
        return AppError(
            ErrorEnvelope(
                code="RATE_LIMITED",
                severity="error",
                title="Rate limited",
                body="The model provider is rate-limiting requests. Please retry shortly.",
                retry_after_ms=_retry_after_ms(exc),
            ),
            status_code=429,
        )
    # 503/529 mean the upstream is unavailable/overloaded; surface as 503 so the
    # client can treat it as transient. All other upstream failures are 502.
    status_code = 502
    if isinstance(exc, openai.APIStatusError) and exc.status_code in (503, 529):
        status_code = 503
    return AppError(
        ErrorEnvelope(
            code="PROVIDER_UPSTREAM",
            severity="error",
            title="Provider error",
            body="The model provider returned an error. Please try again.",
        ),
        status_code=status_code,
    )


class OpenAIProvider:
    """Adapter over `openai.AsyncOpenAI.chat.completions.create(...)`.

    Holds a default client built from the platform key + configured base URL.
    Per-request BYOK overrides build a fresh `AsyncOpenAI(api_key=...)` on the
    same base URL (the SDK is cheap to construct -- HTTP session is lazy). This
    keeps the default fast path identical while making BYOK opt-in per call.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 16000,
        search_provider: SearchProvider | None = None,
    ):
        self._default_api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        # Optional web-search backend. When None, `web_search=True` is a no-op
        # (no tools advertised) — identical to a pre-web-search build. Injected
        # at the construction site (see app/providers/factory.py) from settings.
        self._search_provider = search_provider
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _client_for(self, api_key: str | None) -> AsyncOpenAI:
        """Return the default client, or a fresh one bound to `api_key`.

        The default client is reused across requests for connection pooling;
        BYOK clients are throwaway and rely on the SDK's own connection
        management for that single call. BYOK keeps the same base URL.
        """
        if api_key is None or api_key == self._default_api_key:
            return self._client
        return AsyncOpenAI(api_key=api_key, base_url=self._base_url)

    async def stream(
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
    ) -> AsyncIterator[ProviderEvent]:
        # Build messages: history + the current user turn. Only user/assistant
        # roles (no system role), which keeps o-series models happy.
        messages: list[dict[str, Any]] = [{"role": m.role, "content": m.text} for m in history]
        # Steer ONLY the current user turn (real-provider, outgoing request,
        # never persisted). History stays verbatim. See app/providers/steering.py.
        messages.append({"role": "user", "content": _openai_user_content(user_text, attachments)})

        # Optional provider hints, built CONDITIONALLY so we never send a
        # `reasoning_effort=None` or an empty `extra_body` to stock OpenAI.
        # `thinking` maps to DeepSeek V4's dual-mode toggle via `extra_body`;
        # `reasoning_effort` is the DeepSeek effort level ("high"/"max").
        kwargs: dict[str, Any] = {}
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        if thinking is not None:
            kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}

        client = self._client_for(api_key)

        # Web-search is opt-in AND requires a configured backend. When either is
        # absent, `tool_kwargs` stays empty and the whole path below is identical
        # to a pre-web-search build (no tools advertised). This is the
        # regression-critical no-op invariant.
        search_active = web_search and self._search_provider is not None

        # Accumulated usage across ALL rounds of the agentic loop. We sum the raw
        # OpenAI buckets across every completion, then compute the four DISJOINT
        # buckets once at the end so the overlap subtraction is applied to the
        # summed totals, never double-counted.
        usage_acc = _UsageAccumulator()

        if not search_active:
            # Fast path: web_search disabled or no backend. ONE completion, no
            # tools, no sanitizer. Byte-for-byte identical to a pre-web-search
            # build — the regression-critical no-op invariant.
            async for event in self._consume_completion(
                client=client,
                model_id=model_id,
                messages=messages,
                extra_kwargs=kwargs,
                usage_acc=usage_acc,
                tool_calls=None,
                sanitizer=None,
            ):
                yield event
            usage_update = usage_acc.to_usage_update()
            yield usage_update
            yield Complete(usage=usage_update)
            return

        # Bounded agentic tool loop. Each round streams ONE completion with the
        # web_search tool advertised (tool_choice="auto") so tool calls arrive as
        # STRUCTURED `delta.tool_calls`, never leaked as content. If the model
        # emits web_search call(s): run them, surface status + sources, append the
        # tool-call + tool-result turns, and continue. If it emits NO tool call,
        # that completion's content IS the final answer — stream it and stop.
        assert self._search_provider is not None  # search_active implies this
        accumulated_sources: list[SourceItem] = []
        for round_index in range(_MAX_SEARCH_ROUNDS):
            is_final_round = round_index == _MAX_SEARCH_ROUNDS - 1
            # Advertise the tool every round so structured parsing holds. On the
            # final capped round force tool_choice="none" to compel an answer and
            # break any infinite tool loop (sanitizer scrubs residual leaks).
            round_tool_kwargs: dict[str, Any] = {"tools": [WEB_SEARCH_TOOL]}
            round_tool_kwargs["tool_choice"] = "none" if is_final_round else "auto"

            tool_calls: dict[int, _ToolCallAccumulator] = {}
            sanitizer = ToolMarkupSanitizer()
            round_events: list[ProviderEvent] = []
            async for event in self._consume_completion(
                client=client,
                model_id=model_id,
                messages=messages,
                extra_kwargs={**kwargs, **round_tool_kwargs},
                usage_acc=usage_acc,
                tool_calls=tool_calls,
                sanitizer=sanitizer,
            ):
                round_events.append(event)

            calls = _select_web_search_calls(tool_calls)
            if not calls:
                # No tool call this round → the streamed content was the final
                # answer. Done.
                for event in round_events:
                    yield event
                break

            # Run each requested search, append ONE assistant tool-call turn
            # (carrying every call) plus one tool-result turn per call.
            results_by_call: list[
                tuple[_ToolCallAccumulator, str, str, list[SourceItem], str | None]
            ] = []
            for i, call in enumerate(calls):
                call_id = call.id or f"web_search_{round_index}_{i}"
                query = _parse_query(call.arguments)
                yield ToolCall(
                    id=call_id,
                    name="web_search",
                    label="Search web",
                    status="running",
                    input={"query": query},
                )
            yield StatusUpdate(label=_SEARCH_STATUS_LABEL, state="active")
            for i, call in enumerate(calls):
                call_id = call.id or f"web_search_{round_index}_{i}"
                query = _parse_query(call.arguments)
                error: str | None = None
                if not query.strip():
                    # Malformed / empty tool arguments: there's nothing to
                    # search. Skip the live backend call and feed an empty
                    # result so the second completion answers from the model's
                    # own knowledge.
                    items = []
                else:
                    try:
                        items = await self._search_provider.search(
                            query, max_results=_MAX_SEARCH_RESULTS
                        )
                    except Exception as exc:  # degrade gracefully on backend failure
                        # The search backend raised (transport / non-200). Don't
                        # fail the whole turn: log and feed empty results so the
                        # model answers from its own knowledge.
                        _log.warning("web_search.backend_failed", error=str(exc))
                        items = []
                        error = "Search backend unavailable."
                results_by_call.append((call, call_id, query, items, error))
                accumulated_sources.extend(items)
            yield StatusUpdate(label=_SEARCH_STATUS_LABEL, state="done")
            # Emit the running deduped/renumbered set so citation ids stay
            # coherent. The handler keeps only the latest Sources, so emitting
            # per round with the full accumulated set is correct.
            yield Sources(items=_dedupe_and_renumber(accumulated_sources))
            for _call, call_id, query, items, error in results_by_call:
                yield ToolResult(
                    tool_call_id=call_id,
                    name="web_search",
                    label="Search web",
                    status="failed" if error else "succeeded",
                    summary=(
                        error if error else f"{len(items)} source{'s' if len(items) != 1 else ''}"
                    ),
                    output={
                        "query": query,
                        "results": [item.model_dump() for item in items],
                    },
                    error=error,
                )

            assistant_content = "".join(
                event.text for event in round_events if isinstance(event, AnswerDelta)
            )
            assistant_reasoning = "".join(
                event.text for event in round_events if isinstance(event, ReasoningDelta)
            )
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": call.arguments or "{}",
                        },
                    }
                    for call, call_id, _query, _items, _error in results_by_call
                ],
            }
            if assistant_reasoning:
                assistant_message["reasoning_content"] = assistant_reasoning
            messages.append(assistant_message)
            for _call, call_id, _query, items, _error in results_by_call:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({"results": [item.model_dump() for item in items]}),
                    }
                )

        usage_update = usage_acc.to_usage_update()
        yield usage_update
        yield Complete(usage=usage_update)

    async def _consume_completion(
        self,
        *,
        client: AsyncOpenAI,
        model_id: str,
        messages: list[dict[str, Any]],
        extra_kwargs: dict[str, Any],
        usage_acc: _UsageAccumulator,
        tool_calls: dict[int, _ToolCallAccumulator] | None,
        sanitizer: ToolMarkupSanitizer | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Stream one chat completion, yield reasoning/answer events, accumulate usage.

        `usage_acc` collects the raw OpenAI usage buckets so the caller can sum
        them across multiple completions before emitting the single final
        `UsageUpdate`. When `tool_calls` is a dict, streamed `delta.tool_calls`
        fragments are accumulated into it (keyed by index) so the caller can
        inspect which web_search call(s) were requested this round. When
        `tool_calls` is None, tool-call deltas are ignored.

        `sanitizer`, when provided, scrubs leaked tool-call markup out of CONTENT
        (answer) deltas before they're yielded as `AnswerDelta` — a streaming-safe
        safety net for the web-search path. It is applied ONLY to content, NEVER
        to `reasoning_content`. When None (the no-web-search fast path) content
        passes through verbatim.
        """
        # Reasoning-event invariant (DeepSeek's `delta.reasoning_content`): emit
        # at most one ReasoningDone, only after >=1 ReasoningDelta, and before any
        # AnswerDelta. Stock OpenAI never sends `reasoning_content`, so these stay
        # False and no reasoning events are emitted.
        reasoning_seen = False
        reasoning_done_sent = False
        try:
            stream = await client.chat.completions.create(
                model=model_id,
                messages=cast(Any, messages),
                # o-series models reject `max_tokens`; use `max_completion_tokens`.
                max_completion_tokens=self._max_tokens,
                stream=True,
                # REQUIRED to get usage on a streaming call -- it rides the final
                # chunk (which has empty `choices`).
                stream_options={"include_usage": True},
                **extra_kwargs,
            )
            async for chunk in stream:
                # Usage arrives on the final chunk; capture from any chunk that
                # carries it (some compat endpoints place it differently).
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage_acc.add(chunk_usage)
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    # Accumulate streamed tool_call deltas (id / name / arguments
                    # arrive fragmented across chunks) when the caller is watching
                    # for a tool call.
                    if tool_calls is not None:
                        _accumulate_tool_calls(delta, tool_calls)
                    # DeepSeek streams chain-of-thought separately on
                    # `delta.reasoning_content` (absent/None on stock OpenAI).
                    rc = getattr(delta, "reasoning_content", None)
                    if rc:
                        yield ReasoningDelta(text=rc)
                        reasoning_seen = True
                    content = getattr(delta, "content", None)
                    if content:
                        # Scrub any leaked tool-call markup from the answer
                        # stream (web-search safety net). `feed` may hold back a
                        # split-marker tail and returns only confirmed-clean text.
                        emit = sanitizer.feed(content) if sanitizer is not None else content
                        if emit:
                            # Close the reasoning block exactly once, just before
                            # the first answer text follows it.
                            if reasoning_seen and not reasoning_done_sent:
                                yield ReasoningDone()
                                reasoning_done_sent = True
                            yield AnswerDelta(text=emit)
            # Flush any clean tail the sanitizer held back (no marker followed).
            if sanitizer is not None:
                tail = sanitizer.finish()
                if tail:
                    if reasoning_seen and not reasoning_done_sent:
                        yield ReasoningDone()
                        reasoning_done_sent = True
                    yield AnswerDelta(text=tail)
        except openai.APIError as exc:
            raise _map_sdk_error(exc) from exc

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        """Non-streaming variant. One `chat.completions.create` call, text out.

        Used by title autogen — small/fast tier, short max tokens. Returns the
        first choice's message content stripped. Returns empty string on a
        response without a choice / text (defensive — the caller swallows empty
        titles).
        """
        messages: list[dict[str, Any]] = [{"role": m.role, "content": m.text} for m in history]
        messages.append({"role": "user", "content": user_text})

        client = self._client_for(api_key)
        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=cast(Any, messages),
                # Title-autogen calls are short; cap output tokens tightly at 64.
                max_completion_tokens=64,
            )
        except openai.APIError as exc:
            raise _map_sdk_error(exc) from exc
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        content = getattr(choices[0].message, "content", None)
        return content.strip() if isinstance(content, str) else ""
