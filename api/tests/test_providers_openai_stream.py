"""Streaming-path tests for `OpenAIProvider.stream(...)`.

Drives the OpenAI SDK's streaming Chat Completions client against a mocked SSE
response (`respx`) so we exercise the real chunk-decoding + usage-ingestion path
without hitting the network.

The headline assertion is THE disjoint-bucket mapping: OpenAI's `prompt_tokens`
INCLUDES `prompt_tokens_details.cached_tokens` and `completion_tokens` INCLUDES
`completion_tokens_details.reasoning_tokens`. Because `compute_cost_breakdown`
sums the four buckets independently, the provider MUST subtract the overlaps or
every cached / reasoning turn double-bills. These tests pin the math.

Also covers SDK error mapping: a 429 becomes a typed `RATE_LIMITED` AppError
(with `retryAfterMs` from the response header), a 500 becomes `PROVIDER_UPSTREAM`
(502), and a 503 becomes `PROVIDER_UPSTREAM` (503) — with no raw SDK text leaking
into the user-facing body. And that OpenAI Chat Completions never produces
reasoning-text events (zero `ReasoningDelta`/`ReasoningDone`).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.config import Settings
from app.errors import AppError
from app.providers.openai import OpenAIProvider
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)
from app.providers.tiers import get_binding

pytestmark = pytest.mark.asyncio

_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def _chunk(data: dict[str, object]) -> str:
    """Render one OpenAI streaming SSE frame: `data: {json}\\n\\n`."""
    return f"data: {json.dumps(data)}\n\n"


def _stream_body(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int = 0,
    cached_tokens: int = 0,
    cache_hit_tokens: int | None = None,
    reasoning_chunks: tuple[str, ...] = (),
    answer_chunks: tuple[str, ...] = ("Hello", " there"),
    include_usage: bool = True,
) -> str:
    """Build a full OpenAI streaming SSE body.

    Content chunks carry `choices[0].delta.content`; the final usage chunk
    (emitted because `stream_options.include_usage` is set) carries empty
    `choices` and a `usage` object. Terminated by `data: [DONE]`.

    `reasoning_chunks` model DeepSeek's OpenAI-compatible chain-of-thought
    stream (`choices[0].delta.reasoning_content`), emitted BEFORE any content.
    `cache_hit_tokens` models DeepSeek's TOP-LEVEL `usage.prompt_cache_hit_tokens`
    (distinct from the nested `prompt_tokens_details.cached_tokens`); when set,
    the nested `cached_tokens` field is omitted entirely so we exercise the
    DeepSeek fallback path.
    """
    frames: list[str] = []
    for part in reasoning_chunks:
        frames.append(
            _chunk(
                {
                    "id": "chatcmpl-1",
                    "object": "chat.completion.chunk",
                    "model": "deepseek-v4-pro",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"reasoning_content": part},
                            "finish_reason": None,
                        }
                    ],
                }
            )
        )
    for part in answer_chunks:
        frames.append(
            _chunk(
                {
                    "id": "chatcmpl-1",
                    "object": "chat.completion.chunk",
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": part},
                            "finish_reason": None,
                        }
                    ],
                }
            )
        )
    # Final content chunk with finish_reason + empty delta.
    frames.append(
        _chunk(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "model": "gpt-4o",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
    )
    if include_usage:
        usage: dict[str, Any] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        }
        if cache_hit_tokens is not None:
            # DeepSeek shape: TOP-LEVEL cache field, no nested `cached_tokens`.
            usage["prompt_cache_hit_tokens"] = cache_hit_tokens
        else:
            usage["prompt_tokens_details"] = {"cached_tokens": cached_tokens}
        frames.append(
            _chunk(
                {
                    "id": "chatcmpl-1",
                    "object": "chat.completion.chunk",
                    "model": "gpt-4o",
                    "choices": [],
                    "usage": usage,
                }
            )
        )
    frames.append("data: [DONE]\n\n")
    return "".join(frames)


def _sse_response(body: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body.encode("utf-8"),
    )


def _provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", base_url="https://api.openai.com/v1")


@respx.mock
async def test_stream_disjoint_buckets_and_answer_text() -> None:
    """The four usage buckets are disjoint, and answer text assembles in order.

    prompt=50 / cached=5 -> input=45; completion=100 / reasoning=10 -> output=90.
    Exactly one UsageUpdate then one Complete; Complete.usage == the UsageUpdate.
    No reasoning events. And `compute_cost_breakdown` over an openai binding
    yields the four-bucket subtotal computed from the disjoint counts.
    """
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(
                prompt_tokens=50,
                completion_tokens=100,
                reasoning_tokens=10,
                cached_tokens=5,
                answer_chunks=("Hello", " there"),
            )
        )
    )

    provider = _provider()
    answer_parts: list[str] = []
    usage_updates: list[UsageUpdate] = []
    completes: list[Complete] = []
    reasoning_events = 0
    async for event in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
        if isinstance(event, UsageUpdate):
            usage_updates.append(event)
        elif isinstance(event, Complete):
            completes.append(event)
        elif isinstance(event, AnswerDelta):
            answer_parts.append(event.text)
        elif isinstance(event, (ReasoningDelta, ReasoningDone)):
            reasoning_events += 1

    assert "".join(answer_parts) == "Hello there"
    # OpenAI Chat Completions never streams reasoning text.
    assert reasoning_events == 0

    # Exactly one UsageUpdate, then exactly one Complete carrying the same usage.
    assert len(usage_updates) == 1
    assert len(completes) == 1
    final_usage = usage_updates[0]
    assert completes[0].usage == final_usage

    # THE disjoint-bucket math.
    assert final_usage.cached_input_tokens == 5
    assert final_usage.input_tokens == 45  # prompt(50) - cached(5)
    assert final_usage.reasoning_tokens == 10
    assert final_usage.output_tokens == 90  # completion(100) - reasoning(10)

    # And cost: bill each disjoint bucket at the openai binding's rates.
    s = Settings(provider_backend="openai", openai_api_key="x")
    binding = get_binding("smart", settings=s)
    assert binding is not None
    assert binding.provider_id == "openai"
    bd = compute_cost_breakdown(usage=final_usage, binding=binding)
    expected = (
        45 * binding.list_price_in_per_m
        + 90 * binding.list_price_out_per_m
        + 10 * binding.list_price_out_per_m  # reasoning bills at OUTPUT rate
        + 5 * (binding.cache_read_per_m or 0.0)
    ) / 1_000_000
    assert bd.subtotal_usd == pytest.approx(expected)
    # Breakdown surfaces the disjoint counts verbatim.
    assert bd.input_tokens == 45
    assert bd.output_tokens == 90
    assert bd.reasoning_tokens == 10
    assert bd.cached_input_tokens == 5


@respx.mock
async def test_stream_zero_cached_and_reasoning_no_subtraction() -> None:
    """With no cached/reasoning tokens, input/output equal prompt/completion."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(_stream_body(prompt_tokens=30, completion_tokens=12))
    )

    provider = _provider()
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
        if isinstance(event, UsageUpdate):
            final_usage = event

    assert final_usage is not None
    assert final_usage.input_tokens == 30
    assert final_usage.output_tokens == 12
    assert final_usage.reasoning_tokens == 0
    assert final_usage.cached_input_tokens == 0


@respx.mock
async def test_stream_missing_usage_leaves_zero_buckets() -> None:
    """A compat endpoint that ignores `include_usage` -> all buckets stay 0."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(
                prompt_tokens=99,
                completion_tokens=99,
                include_usage=False,
                answer_chunks=("ok",),
            )
        )
    )

    provider = _provider()
    answer_parts: list[str] = []
    final_usage: UsageUpdate | None = None
    complete: Complete | None = None
    async for event in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
        if isinstance(event, UsageUpdate):
            final_usage = event
        elif isinstance(event, Complete):
            complete = event
        elif isinstance(event, AnswerDelta):
            answer_parts.append(event.text)

    assert "".join(answer_parts) == "ok"
    assert final_usage is not None
    assert (
        final_usage.input_tokens,
        final_usage.output_tokens,
        final_usage.reasoning_tokens,
        final_usage.cached_input_tokens,
    ) == (0, 0, 0, 0)
    assert complete is not None
    assert complete.usage == final_usage


@respx.mock
async def test_stream_maps_rate_limit_to_app_error() -> None:
    """A 429 stream open becomes RATE_LIMITED with retryAfterMs, no raw text."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            429,
            headers={"retry-after": "2"},
            json={"error": {"type": "rate_limit_error", "message": "slow down"}},
        )
    )

    provider = _provider()
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
            pass

    err = excinfo.value
    assert err.envelope.code == "RATE_LIMITED"
    assert err.status_code == 429
    assert err.envelope.retry_after_ms == 2000  # 2s header -> ms
    assert err.envelope.body
    assert "slow down" not in err.envelope.body


@respx.mock
async def test_stream_maps_server_error_to_provider_upstream_502() -> None:
    """A 500 stream open becomes PROVIDER_UPSTREAM (502), no raw SDK text."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            500,
            json={"error": {"type": "server_error", "message": "boom internal"}},
        )
    )

    provider = _provider()
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
            pass

    err = excinfo.value
    assert err.envelope.code == "PROVIDER_UPSTREAM"
    assert err.status_code == 502
    assert "boom internal" not in err.envelope.body


@respx.mock
async def test_stream_maps_unavailable_to_provider_upstream_503() -> None:
    """A 503 stream open becomes PROVIDER_UPSTREAM with status_code 503."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            503,
            json={"error": {"type": "overloaded", "message": "busy"}},
        )
    )

    provider = _provider()
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
            pass

    err = excinfo.value
    assert err.envelope.code == "PROVIDER_UPSTREAM"
    assert err.status_code == 503
    assert "busy" not in err.envelope.body


@respx.mock
async def test_stream_rate_limit_prefers_retry_after_ms_header() -> None:
    """The non-standard `retry-after-ms` header wins over `retry-after` seconds."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            429,
            headers={"retry-after-ms": "1500", "retry-after": "9"},
            json={"error": {"type": "rate_limit_error", "message": "slow down"}},
        )
    )

    provider = _provider()
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
            pass

    err = excinfo.value
    assert err.envelope.code == "RATE_LIMITED"
    assert err.envelope.retry_after_ms == 1500  # ms header wins over the 9s one


@respx.mock
async def test_stream_connection_error_maps_to_provider_upstream_502() -> None:
    """A transport failure (no HTTP status) maps to PROVIDER_UPSTREAM (502).

    The OpenAI SDK wraps an httpx transport error as `openai.APIConnectionError`,
    which is an `APIError` but NOT an `APIStatusError` (no `.status_code`); the
    error mapper must not crash on it and must fall through to 502.
    """
    respx.post(_COMPLETIONS_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    provider = _provider()
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
            pass

    err = excinfo.value
    assert err.envelope.code == "PROVIDER_UPSTREAM"
    assert err.status_code == 502
    assert "connection refused" not in err.envelope.body


async def test_client_for_byok_selects_fresh_client_with_same_base_url() -> None:
    """BYOK: a key mismatch yields a fresh client pinned to the SAME base_url."""
    provider = _provider()
    # Default client reused when there's no override or the key matches platform.
    assert provider._client_for(None) is provider._client
    assert provider._client_for("test-key") is provider._client
    # A different (BYOK) key builds a throwaway client on the same operator base.
    byok_client = provider._client_for("byok-other-key")
    assert byok_client is not provider._client
    assert byok_client.base_url == provider._client.base_url


# --- DeepSeek V4 dual-mode hints + reasoning_content + cache fallback ---------
#
# These exercise the provider-hint passthrough (thinking / reasoning_effort) and
# DeepSeek-specific stream/usage shapes that stock OpenAI never produces.


class _EmptyStream:
    """An empty async-iterable of chunks — the awaited result of `create(...)`.

    Used by the kwargs-passthrough tests, where we only care about what was
    passed into `create(...)`, not what comes back.
    """

    def __aiter__(self) -> _EmptyStream:
        return self

    async def __anext__(self) -> Any:
        raise StopAsyncIteration


async def _capture_create_kwargs(
    *, thinking: bool | None, reasoning_effort: str | None
) -> dict[str, Any]:
    """Patch the client's `create` and return the kwargs `stream(...)` passed it."""
    provider = _provider()
    create_mock = AsyncMock(return_value=_EmptyStream())
    provider._client.chat.completions.create = create_mock  # type: ignore[method-assign]
    async for _ in provider.stream(
        model_id="deepseek-v4-pro",
        history=[],
        user_text="hi",
        thinking=thinking,
        reasoning_effort=reasoning_effort,
    ):
        pass
    assert create_mock.await_count == 1
    return dict(create_mock.await_args.kwargs)


async def test_stream_thinking_enabled_sets_extra_body() -> None:
    """thinking=True -> extra_body={"thinking": {"type": "enabled"}}."""
    kwargs = await _capture_create_kwargs(thinking=True, reasoning_effort=None)
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "reasoning_effort" not in kwargs


async def test_stream_thinking_disabled_sets_extra_body() -> None:
    """thinking=False -> extra_body={"thinking": {"type": "disabled"}}."""
    kwargs = await _capture_create_kwargs(thinking=False, reasoning_effort=None)
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


async def test_stream_thinking_none_omits_extra_body() -> None:
    """thinking=None -> no extra_body / no thinking key (provider default)."""
    kwargs = await _capture_create_kwargs(thinking=None, reasoning_effort=None)
    assert "extra_body" not in kwargs


async def test_stream_reasoning_effort_passed_through() -> None:
    """reasoning_effort="high" is forwarded verbatim; None is omitted."""
    kwargs = await _capture_create_kwargs(thinking=None, reasoning_effort="high")
    assert kwargs["reasoning_effort"] == "high"
    assert "extra_body" not in kwargs

    kwargs_none = await _capture_create_kwargs(thinking=None, reasoning_effort=None)
    assert "reasoning_effort" not in kwargs_none


@respx.mock
async def test_stream_reasoning_content_emits_ordered_events() -> None:
    """DeepSeek `reasoning_content` -> ReasoningDelta(s), one ReasoningDone, then AnswerDelta(s).

    The Provider invariant: at most one ReasoningDone, only after >=1
    ReasoningDelta, and strictly before the first AnswerDelta.
    """
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(
                prompt_tokens=10,
                completion_tokens=10,
                reasoning_chunks=("Thinking", " harder"),
                answer_chunks=("Answer", " here"),
            )
        )
    )

    provider = _provider()
    events: list[str] = []
    reasoning_text: list[str] = []
    answer_text: list[str] = []
    async for event in provider.stream(model_id="deepseek-v4-pro", history=[], user_text="hi"):
        if isinstance(event, ReasoningDelta):
            events.append("rdelta")
            reasoning_text.append(event.text)
        elif isinstance(event, ReasoningDone):
            events.append("rdone")
        elif isinstance(event, AnswerDelta):
            events.append("answer")
            answer_text.append(event.text)

    assert "".join(reasoning_text) == "Thinking harder"
    assert "".join(answer_text) == "Answer here"
    # Exactly one ReasoningDone, after the reasoning deltas and before any answer.
    assert events.count("rdone") == 1
    done_idx = events.index("rdone")
    first_answer_idx = events.index("answer")
    assert all(e == "rdelta" for e in events[:done_idx])
    assert done_idx < first_answer_idx


@respx.mock
async def test_stream_content_without_reasoning_emits_no_reasoning_done() -> None:
    """Content with no prior reasoning_content -> NO ReasoningDone (stock OpenAI shape)."""
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(
                prompt_tokens=10,
                completion_tokens=10,
                answer_chunks=("Just", " answer"),
            )
        )
    )

    provider = _provider()
    reasoning_events = 0
    async for event in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
        if isinstance(event, (ReasoningDelta, ReasoningDone)):
            reasoning_events += 1

    assert reasoning_events == 0


@respx.mock
async def test_stream_deepseek_prompt_cache_hit_tokens_captured() -> None:
    """DeepSeek top-level `prompt_cache_hit_tokens` -> cached bucket, subtracted from input.

    No nested `prompt_tokens_details.cached_tokens` is present (DeepSeek shape),
    so the provider must fall back to the top-level field — otherwise DeepSeek
    cache discounts would silently never apply.
    """
    respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(
                prompt_tokens=80,
                completion_tokens=40,
                cache_hit_tokens=30,
                answer_chunks=("ok",),
            )
        )
    )

    provider = _provider()
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(model_id="deepseek-v4-pro", history=[], user_text="hi"):
        if isinstance(event, UsageUpdate):
            final_usage = event

    assert final_usage is not None
    assert final_usage.cached_input_tokens == 30
    assert final_usage.input_tokens == 50  # prompt(80) - cache_hit(30)
    assert final_usage.output_tokens == 40
