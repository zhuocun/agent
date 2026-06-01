"""Anthropic SDK adapter.

Maps `client.messages.stream(...)` events to our internal `ProviderEvent`s:

- `thinking` block → `ReasoningDelta` + a single `ReasoningDone` at block end.
- `text` block → `AnswerDelta`.
- Token usage is read from the merged final message after the stream closes.
  Anthropic reports `input_tokens` and the cache fields on `message_start` and
  the running cumulative `output_tokens` on each `message_delta`;
  `get_final_message().usage` reconciles both into one `Usage`, from which we
  emit a single final `UsageUpdate` + `Complete`.

Per PRD 07 §7 rule 7 (enforced in `pricing.py`), reasoning tokens bill at the
output rate. Extended thinking is not enabled on the real provider, so
`reasoning_tokens` stays 0 here; reasoning attribution is exercised by the
FakeProvider only. Cache token counts map cleanly.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any, cast

import anthropic
from anthropic import AsyncAnthropic

from app.errors import AppError, ErrorEnvelope
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
from app.search.protocol import SourceItem

# Anthropic's server-side web-search tool (hosted; the model runs the search and
# streams `server_tool_use` / `web_search_tool_result` content blocks back). We
# advertise it only when `web_search=True`. `max_uses` bounds the per-turn search
# count.
_ANTHROPIC_WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}
_SEARCH_STATUS_LABEL = "Searching the web…"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _anthropic_attachment_part(attachment: AttachmentPayload) -> dict[str, Any] | None:
    """Map a transient attachment into Anthropic Messages content."""
    if attachment.data is None:
        return None
    source = {
        "type": "base64",
        "media_type": attachment.mime_type,
        "data": _b64(attachment.data),
    }
    if attachment.media_type == "image":
        return {"type": "image", "source": source}
    if attachment.media_type == "pdf":
        return {"type": "document", "source": source}
    return None


def _anthropic_user_content(
    user_text: str,
    attachments: list[AttachmentPayload] | None,
) -> str | list[dict[str, Any]]:
    """Build the current user content, including native attachment bytes."""
    if not attachments:
        return steer_user_text(user_text)

    content: list[dict[str, Any]] = []
    metadata_only: list[AttachmentPayload] = []
    for attachment in attachments:
        part = _anthropic_attachment_part(attachment)
        if part is None:
            metadata_only.append(attachment)
        else:
            content.append(part)

    text = (
        text_with_attachment_fallback(user_text, metadata_only)
        if metadata_only
        else user_text
    )
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


@lru_cache(maxsize=256)
def _build_client(api_key: str, base_url: str | None) -> AsyncAnthropic:
    """Per-(api_key, base_url) cached `AsyncAnthropic` factory.

    Constructing the SDK client is cheap but its underlying httpx pool is not:
    a fresh client per request churns TCP / TLS sessions on the BYOK path.
    Caching by `(api_key, base_url)` lets each BYOK user (and the platform key)
    reuse one persistent connection pool across requests.

    Cache size 256 covers a healthy mix of platform + BYOK users in a single
    worker; LRU eviction keeps memory bounded if usage spikes. Keys are kept
    in-process only and never logged. Tests that swap in fake clients can
    call `_build_client.cache_clear()` to reset.
    """
    if base_url is None:
        return AsyncAnthropic(api_key=api_key)
    return AsyncAnthropic(api_key=api_key, base_url=base_url)


def reset_anthropic_client_cache() -> None:
    """Clear the per-key client cache. Useful in tests."""
    _build_client.cache_clear()


def _safe_int(value: Any) -> int:
    """Coerce SDK usage fields (often `int | None`) to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _domain_of(url: str) -> str | None:
    """Parse the host out of a URL; None when it can't be determined."""
    from urllib.parse import urlparse

    try:
        host = urlparse(url).netloc
    except ValueError:
        return None
    return host or None


def _parse_web_search_result(block: Any) -> list[SourceItem]:
    """Map an Anthropic `web_search_tool_result` content block to SourceItems.

    The block's `content` is a list of `web_search_result` entries, each with a
    `title`, `url`, and (optionally) page `content`. We duck-type defensively
    since the SDK shape varies by version; an `error`-shaped content (search
    failed upstream) yields an empty list so the turn still completes.
    """
    content = getattr(block, "content", None)
    if not isinstance(content, list):
        return []
    items: list[SourceItem] = []
    for idx, result in enumerate(content, start=1):
        url = getattr(result, "url", None)
        if url is None and isinstance(result, dict):
            url = result.get("url")
        if not url:
            continue
        title = getattr(result, "title", None)
        if title is None and isinstance(result, dict):
            title = result.get("title")
        raw_snippet: Any = None
        if isinstance(result, dict):
            raw_snippet = result.get("content") or result.get("snippet")
        else:
            raw_snippet = getattr(result, "content", None)
        snippet = (
            str(raw_snippet)[:300].strip() if isinstance(raw_snippet, str) and raw_snippet else None
        )
        url_str = str(url)
        items.append(
            SourceItem(
                id=idx,
                title=str(title) if title else url_str,
                url=url_str,
                snippet=snippet,
                domain=_domain_of(url_str),
            )
        )
    return items


def _block_value(block: Any, key: str) -> Any:
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


def _retry_after_ms(exc: anthropic.APIStatusError) -> int | None:
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


def _map_sdk_error(exc: anthropic.APIError) -> AppError:
    """Translate an Anthropic SDK error into a typed `AppError`.

    Rate limits become `RATE_LIMITED` (429) with `retryAfterMs` when the
    upstream response carries a retry-after header; everything else becomes
    `PROVIDER_UPSTREAM` (502, or 503 for explicit unavailability). The raw SDK
    message is never placed in the user-facing `body` — only a clean generic
    string. The original exception is left for the caller to log.
    """
    if isinstance(exc, anthropic.RateLimitError):
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
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code in (503, 529):
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


class AnthropicProvider:
    """Adapter over `anthropic.AsyncAnthropic.messages.stream(...)`.

    Clients are resolved per-request via `_build_client(api_key, base_url)`,
    which is `@lru_cache(maxsize=256)`. The platform-key client and each
    BYOK-key client are reused across requests so the underlying httpx
    connection pool isn't churned. `base_url` is currently always None for
    Anthropic, but is part of the cache key so a future Anthropic-compatible
    endpoint override slots in cleanly.
    """

    def __init__(self, api_key: str, max_tokens: int = 16000):
        self._default_api_key = api_key
        self._max_tokens = max_tokens

    def _client_for(self, api_key: str | None) -> AsyncAnthropic:
        """Return the cached client for `api_key` (or the platform default).

        Both the default and per-BYOK clients are cached by `_build_client`
        keyed on `(api_key, base_url)` — same key returns the same instance
        across requests, different key returns a different instance. LRU
        eviction keeps the cache bounded.
        """
        key = api_key if api_key is not None else self._default_api_key
        return _build_client(key, None)

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
        # `thinking` / `reasoning_effort` accepted for Protocol conformance but
        # ignored: Anthropic extended-thinking is not yet wired here.
        # Build messages: history + the current user turn.
        messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.text} for m in history
        ]
        # Steer ONLY the current user turn (real-provider, outgoing request,
        # never persisted). History stays verbatim. See app/providers/steering.py.
        messages.append(
            {"role": "user", "content": _anthropic_user_content(user_text, attachments)}
        )

        # Anthropic server-side web search (hosted tool). Advertise the tool only
        # when opted in; the model runs the search itself and streams
        # `server_tool_use` (it dispatched a search) + `web_search_tool_result`
        # (results came back) content blocks, which we map to StatusUpdate +
        # Sources. When web_search=False, no tools are sent and the path is
        # byte-for-byte unchanged.
        stream_kwargs: dict[str, Any] = {}
        if web_search:
            stream_kwargs["tools"] = [_ANTHROPIC_WEB_SEARCH_TOOL]

        # Track whether we're currently inside a thinking block so we can
        # emit exactly one ReasoningDone at block end.
        in_thinking = False
        # Whether we've already announced an active search status (so a multi-use
        # search turn only emits a single active/done pair around the results).
        search_active_emitted = False

        client = self._client_for(api_key)
        try:
            async with client.messages.stream(
                model=model_id,
                max_tokens=self._max_tokens,
                messages=cast(Any, messages),
                **stream_kwargs,
            ) as stream:
                async for event in stream:
                    etype = getattr(event, "type", None)

                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        block_type = _block_value(block, "type")
                        if block_type == "thinking":
                            in_thinking = True
                        elif block_type == "server_tool_use":
                            # The model dispatched a server-side web search.
                            # Surface the "Searching the web…" status once.
                            tool_id = str(_block_value(block, "id") or "web_search")
                            tool_name = str(_block_value(block, "name") or "web_search")
                            tool_input = _block_value(block, "input")
                            yield ToolCall(
                                id=tool_id,
                                name=tool_name,
                                label="Search web",
                                status="running",
                                input=(
                                    tool_input
                                    if isinstance(tool_input, dict)
                                    else None
                                ),
                            )
                            if not search_active_emitted:
                                yield StatusUpdate(
                                    label=_SEARCH_STATUS_LABEL, state="active"
                                )
                                search_active_emitted = True
                        elif block_type == "web_search_tool_result":
                            # Results returned: close the status and emit sources.
                            tool_use_id = str(
                                _block_value(block, "tool_use_id") or "web_search"
                            )
                            items = _parse_web_search_result(block)
                            yield ToolResult(
                                tool_call_id=tool_use_id,
                                name="web_search",
                                label="Search web",
                                status="succeeded",
                                summary=(
                                    f"{len(items)} source"
                                    f"{'s' if len(items) != 1 else ''}"
                                ),
                                output={
                                    "results": [
                                        item.model_dump() for item in items
                                    ]
                                },
                            )
                            if search_active_emitted:
                                yield StatusUpdate(
                                    label=_SEARCH_STATUS_LABEL, state="done"
                                )
                            if items:
                                yield Sources(items=items)

                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        dtype = getattr(delta, "type", None)
                        if dtype == "thinking_delta":
                            yield ReasoningDelta(text=getattr(delta, "thinking", ""))
                        elif dtype == "text_delta":
                            yield AnswerDelta(text=getattr(delta, "text", ""))

                    elif etype == "content_block_stop":
                        if in_thinking:
                            yield ReasoningDone()
                            in_thinking = False

                # Read the merged usage once the stream is fully consumed.
                # Anthropic reports input + cache counts on `message_start` and
                # the cumulative `output_tokens` on `message_delta`; the SDK
                # reconciles both into `get_final_message().usage`, so reading
                # it here gets every bucket (reading only `message_delta` would
                # drop input/cache counts).
                final_usage = (await stream.get_final_message()).usage
        except anthropic.APIError as exc:
            raise _map_sdk_error(exc) from exc

        input_tokens = _safe_int(getattr(final_usage, "input_tokens", None))
        output_tokens = _safe_int(getattr(final_usage, "output_tokens", None))
        # Only the cache-READ bucket maps to our cache-priced slot. Cache
        # creation/write pricing is out of scope until prompt caching is
        # enabled (no `cache_control` is sent today, so both are 0).
        cached_input_tokens = _safe_int(
            getattr(final_usage, "cache_read_input_tokens", None)
        )
        # Extended thinking isn't enabled here, so reasoning stays 0 on the real
        # provider (reasoning attribution is exercised by the FakeProvider only).
        reasoning_tokens = 0

        usage_update = UsageUpdate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        yield usage_update
        yield Complete(usage=usage_update)

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        """Non-streaming variant. One `messages.create` call, collected text.

        Used by title autogen — small/fast tier, short max_tokens. Concatenates
        any `text` blocks in the SDK response and returns the joined string.
        Returns empty string on a response without a text block (defensive —
        the caller will swallow empty titles).
        """
        # Title-autogen calls are short; cap output tokens tightly at 64 so a
        # runaway model can't burn a full max_tokens budget on a 5-word title.
        messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.text} for m in history
        ]
        messages.append({"role": "user", "content": user_text})

        client = self._client_for(api_key)
        try:
            response = await client.messages.create(
                model=model_id,
                max_tokens=64,
                messages=cast(Any, messages),
            )
        except anthropic.APIError as exc:
            raise _map_sdk_error(exc) from exc
        # `response.content` is a list of content blocks; we concatenate text
        # blocks (skip thinking / tool_use etc.). SDK shapes vary by version
        # so we duck-type defensively.
        texts: list[str] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_val = getattr(block, "text", "")
                if isinstance(text_val, str):
                    texts.append(text_val)
        return "".join(texts).strip()
