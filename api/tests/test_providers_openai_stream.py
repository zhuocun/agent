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
    Sources,
    StatusUpdate,
    UsageUpdate,
)
from app.providers.tiers import get_binding
from app.search.fake import FakeSearchProvider
from app.search.protocol import SourceItem

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


# --- web_search agentic tool loop ---------------------------------------------
#
# When `web_search=True` AND a search backend is injected, the provider advertises
# the `web_search` function tool with `tool_choice="auto"` and runs a BOUNDED
# agentic loop: each round streams one completion; if it emits web_search
# tool_call(s) the provider runs the search (StatusUpdate active/done + Sources),
# appends the tool-call + tool-result turns, and continues. The first round that
# produces NO tool_call streams the grounded answer and stops. The round count is
# capped at `_MAX_SEARCH_ROUNDS`; the final round forces `tool_choice="none"`.
# Usage sums across ALL rounds.


def _tool_call_stream_body(
    *,
    query: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> str:
    """A first-completion SSE body that streams a single `web_search` tool_call.

    The tool call's id/name arrive on the first fragment; the JSON arguments are
    split across two fragments to exercise the delta-accumulation path. The final
    usage chunk carries the first call's token counts.
    """
    args = json.dumps({"query": query})
    half = len(args) // 2
    frames = [
        _chunk(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_abc",
                                    "type": "function",
                                    "function": {"name": "web_search", "arguments": args[:half]},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        ),
        _chunk(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": args[half:]}}
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
        ),
        _chunk(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "model": "deepseek-v4-pro",
                "choices": [],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            }
        ),
        "data: [DONE]\n\n",
    ]
    return "".join(frames)


def _search_provider() -> OpenAIProvider:
    return OpenAIProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        search_provider=FakeSearchProvider(),
    )


@respx.mock
async def test_stream_web_search_runs_tool_loop_and_sums_usage() -> None:
    """web_search=True + tool_call -> Status(active)→Status(done)→Sources→answer.

    The first completion streams a `web_search` tool_call (prompt=10/comp=5); the
    second streams the grounded answer (prompt=20/comp=30). Final usage is the SUM
    of both calls' disjoint buckets: input=30, output=35.
    """
    first = _sse_response(
        _tool_call_stream_body(query="latest rust release", prompt_tokens=10, completion_tokens=5)
    )
    second = _sse_response(
        _stream_body(prompt_tokens=20, completion_tokens=30, answer_chunks=("Per", " [1]", " yes."))
    )
    respx.post(_COMPLETIONS_URL).mock(side_effect=[first, second])

    provider = _search_provider()
    seq: list[str] = []
    statuses: list[StatusUpdate] = []
    sources: list[Sources] = []
    answer_parts: list[str] = []
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, StatusUpdate):
            seq.append(f"status:{event.state}")
            statuses.append(event)
        elif isinstance(event, Sources):
            seq.append("sources")
            sources.append(event)
        elif isinstance(event, AnswerDelta):
            seq.append("answer")
            answer_parts.append(event.text)
        elif isinstance(event, UsageUpdate):
            final_usage = event

    # Ordered: active status, done status, sources, THEN answer deltas.
    assert statuses[0].state == "active"
    assert statuses[0].label == "Searching the web…"
    assert statuses[1].state == "done"
    first_status_idx = seq.index("status:active")
    done_idx = seq.index("status:done")
    sources_idx = seq.index("sources")
    first_answer_idx = seq.index("answer")
    assert first_status_idx < done_idx < sources_idx < first_answer_idx

    # Sources come from the injected FakeSearchProvider (3 deterministic items).
    assert len(sources) == 1
    assert [it.id for it in sources[0].items] == [1, 2, 3]

    assert "".join(answer_parts) == "Per [1] yes."

    # Usage summed across BOTH completions: input = 10+20, output = 5+30.
    assert final_usage is not None
    assert final_usage.input_tokens == 30
    assert final_usage.output_tokens == 35
    assert final_usage.reasoning_tokens == 0
    assert final_usage.cached_input_tokens == 0


@respx.mock
async def test_stream_web_search_advertises_tool_across_rounds() -> None:
    """The tool stays advertised on EVERY (non-final) round.

    Root-cause fix: keeping `tools=[WEB_SEARCH_TOOL]` with `tool_choice="auto"`
    across rounds makes the OpenAI-compatible endpoint parse tool calls into
    STRUCTURED `delta.tool_calls` rather than leaking the raw special tokens as
    content. Here round 1 streams a tool_call and round 2 streams the grounded
    answer — BOTH calls advertise the tool with `tool_choice="auto"` (round 2 is
    not the final capped round, so it is not forced to "none").
    """
    first = _sse_response(
        _tool_call_stream_body(query="q", prompt_tokens=1, completion_tokens=1)
    )
    second = _sse_response(
        _stream_body(prompt_tokens=1, completion_tokens=1, answer_chunks=("ok",))
    )
    route = respx.post(_COMPLETIONS_URL).mock(side_effect=[first, second])

    provider = _search_provider()
    async for _ in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        pass

    assert route.call_count == 2
    body0 = json.loads(route.calls[0].request.content)
    body1 = json.loads(route.calls[1].request.content)
    # Round 1 advertises the tool, auto choice.
    assert body0.get("tools")
    assert body0.get("tool_choice") == "auto"
    # Round 2 (grounded answer) STILL advertises the tool with auto choice — the
    # model declines to call it again and answers instead. This is what keeps the
    # endpoint parsing any further tool intent as structured calls, not content.
    assert body1.get("tools")
    assert body1.get("tool_choice") == "auto"
    # The tool-result turn was appended for the second call's context.
    roles = [m["role"] for m in body1["messages"]]
    assert "tool" in roles


@respx.mock
async def test_stream_web_search_no_tool_call_finishes_normally() -> None:
    """web_search=True but the model answers directly -> no Status/Sources, one call."""
    route = respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(prompt_tokens=10, completion_tokens=8, answer_chunks=("Direct",))
        )
    )

    provider = _search_provider()
    events: list[str] = []
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, (StatusUpdate, Sources)):
            events.append("search")
        elif isinstance(event, UsageUpdate):
            final_usage = event

    # No second call, no search events.
    assert route.call_count == 1
    assert events == []
    assert final_usage is not None
    assert final_usage.input_tokens == 10
    assert final_usage.output_tokens == 8


@respx.mock
async def test_stream_web_search_false_is_unchanged_no_tools() -> None:
    """web_search=False -> no tools advertised, behavior identical to today."""
    route = respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(prompt_tokens=5, completion_tokens=7, answer_chunks=("Hi",))
        )
    )

    provider = _search_provider()
    search_events = 0
    answer_parts: list[str] = []
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=False
    ):
        if isinstance(event, (StatusUpdate, Sources)):
            search_events += 1
        elif isinstance(event, AnswerDelta):
            answer_parts.append(event.text)

    assert route.call_count == 1
    assert search_events == 0
    assert "".join(answer_parts) == "Hi"
    # No tools key sent.
    body = json.loads(route.calls[0].request.content)
    assert "tools" not in body


@respx.mock
async def test_stream_web_search_true_without_backend_is_noop() -> None:
    """web_search=True but NO search provider injected -> no tools, no search events."""
    route = respx.post(_COMPLETIONS_URL).mock(
        return_value=_sse_response(
            _stream_body(prompt_tokens=5, completion_tokens=7, answer_chunks=("Hi",))
        )
    )

    # Provider built WITHOUT a search_provider (the default).
    provider = _provider()
    search_events = 0
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, (StatusUpdate, Sources)):
            search_events += 1

    assert route.call_count == 1
    assert search_events == 0
    body = json.loads(route.calls[0].request.content)
    assert "tools" not in body


class _RaisingSearchProvider:
    """A search backend that always fails — exercises graceful degradation."""

    async def search(self, query: str, *, max_results: int = 5) -> list[SourceItem]:
        raise RuntimeError("search backend down")


@respx.mock
async def test_stream_web_search_backend_failure_degrades_gracefully() -> None:
    """If the search backend raises, the turn still completes.

    The model calls `web_search`, the backend throws → the provider logs, emits a
    `done` status with an EMPTY `Sources`, feeds empty results to the grounded
    second completion, and still streams an answer. Usage sums both calls.
    """
    first = _sse_response(
        _tool_call_stream_body(query="q", prompt_tokens=10, completion_tokens=5)
    )
    second = _sse_response(
        _stream_body(prompt_tokens=20, completion_tokens=30, answer_chunks=("Answer",))
    )
    route = respx.post(_COMPLETIONS_URL).mock(side_effect=[first, second])

    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        search_provider=_RaisingSearchProvider(),
    )
    statuses: list[StatusUpdate] = []
    sources: list[Sources] = []
    answer_parts: list[str] = []
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, StatusUpdate):
            statuses.append(event)
        elif isinstance(event, Sources):
            sources.append(event)
        elif isinstance(event, AnswerDelta):
            answer_parts.append(event.text)
        elif isinstance(event, UsageUpdate):
            final_usage = event

    # Both completions ran despite the backend failure (no turn-level crash).
    assert route.call_count == 2
    # Status still resolves active -> done, but with an EMPTY sources list.
    assert [s.state for s in statuses] == ["active", "done"]
    assert len(sources) == 1
    assert sources[0].items == []
    # The grounded answer still streamed.
    assert "".join(answer_parts) == "Answer"
    # The tool-result turn carried an empty results array.
    body1 = json.loads(route.calls[1].request.content)
    tool_msg = next(m for m in body1["messages"] if m["role"] == "tool")
    assert json.loads(tool_msg["content"]) == {"results": []}
    # Usage summed across both calls: input = 10+20, output = 5+30.
    assert final_usage is not None
    assert final_usage.input_tokens == 30
    assert final_usage.output_tokens == 35


# --- multi-round loop, leak regression, round cap -----------------------------


@respx.mock
async def test_stream_web_search_multi_round_dedupes_and_sums_usage() -> None:
    """Three rounds: tool_call → tool_call → answer.

    - Exactly THREE completions are made; the search backend runs TWICE.
    - The two searches use the SAME query, so the accumulated sources collide on
      url and dedup to a single coherent set, renumbered 1..N (contiguous).
    - The final round produces no tool_call; its content is the clean answer.
    - Usage sums the disjoint buckets across ALL THREE rounds.
    """
    # Same query both rounds → identical urls from the FakeSearchProvider → the
    # accumulated 6 items dedup down to 3, renumbered 1..3.
    round1 = _sse_response(
        _tool_call_stream_body(query="spurs score", prompt_tokens=10, completion_tokens=5)
    )
    round2 = _sse_response(
        _tool_call_stream_body(query="spurs score", prompt_tokens=20, completion_tokens=7)
    )
    round3 = _sse_response(
        _stream_body(
            prompt_tokens=40, completion_tokens=9, answer_chunks=("Final", " [1]", " answer.")
        )
    )
    route = respx.post(_COMPLETIONS_URL).mock(side_effect=[round1, round2, round3])

    provider = _search_provider()
    statuses: list[StatusUpdate] = []
    sources: list[Sources] = []
    answer_parts: list[str] = []
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, StatusUpdate):
            statuses.append(event)
        elif isinstance(event, Sources):
            sources.append(event)
        elif isinstance(event, AnswerDelta):
            answer_parts.append(event.text)
        elif isinstance(event, UsageUpdate):
            final_usage = event

    # Three completions, two of which triggered a search.
    assert route.call_count == 3
    # Two search cycles → two active/done pairs, two Sources emissions.
    assert [s.state for s in statuses] == ["active", "done", "active", "done"]
    assert len(sources) == 2
    # The FINAL emitted Sources set is deduped (same query both rounds → 3 urls)
    # and renumbered contiguously 1..3.
    final_sources = sources[-1].items
    assert [it.id for it in final_sources] == [1, 2, 3]
    assert len({it.url for it in final_sources}) == 3

    # Final-round content is the clean grounded answer.
    assert "".join(answer_parts) == "Final [1] answer."

    # Usage summed across ALL THREE rounds: input = 10+20+40, output = 5+7+9.
    assert final_usage is not None
    assert final_usage.input_tokens == 70
    assert final_usage.output_tokens == 21
    assert final_usage.reasoning_tokens == 0
    assert final_usage.cached_input_tokens == 0


@respx.mock
async def test_stream_web_search_multi_round_distinct_queries_accumulate() -> None:
    """Distinct queries across rounds accumulate into one renumbered set."""
    round1 = _sse_response(
        _tool_call_stream_body(query="query alpha", prompt_tokens=1, completion_tokens=1)
    )
    round2 = _sse_response(
        _tool_call_stream_body(query="query beta", prompt_tokens=1, completion_tokens=1)
    )
    round3 = _sse_response(
        _stream_body(prompt_tokens=1, completion_tokens=1, answer_chunks=("done",))
    )
    respx.post(_COMPLETIONS_URL).mock(side_effect=[round1, round2, round3])

    provider = _search_provider()
    sources: list[Sources] = []
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, Sources):
            sources.append(event)

    # Two distinct queries → 3 + 3 distinct urls → 6 sources renumbered 1..6.
    final_sources = sources[-1].items
    assert [it.id for it in final_sources] == [1, 2, 3, 4, 5, 6]
    assert len({it.url for it in final_sources}) == 6


# A content body that leaks the EXACT captured prod tool-call markup as answer
# text. `｜` is U+FF5C (fullwidth bar). A correct fix must scrub all of this so
# none of it reaches the client as an answer delta.
_LEAKED_MARKUP = (
    "The user is asking if the Spurs played. Let me search for that."
    "<｜｜DSML｜｜tool_calls>\n"
    '<｜｜DSML｜｜invoke name="web_search">\n'
    '<｜｜DSML｜｜parameter name="query" string="true">'
    "San Antonio Spurs score</｜｜DSML｜｜parameter>\n"
    "</｜｜DSML｜｜invoke>\n"
    "</｜｜DSML｜｜tool_calls>"
)


@respx.mock
async def test_stream_web_search_leaked_markup_is_scrubbed_from_answer() -> None:
    """A round whose CONTENT leaks raw tool-call markup → none reaches the answer.

    The model declines the structured tool call and instead dumps the raw
    special-token block into `delta.content`. The streaming sanitizer truncates
    the answer at the first start marker, so the emitted answer contains NONE of
    the leak markup (`tool_calls`, `invoke name`, `｜｜DSML`, `web_search`).
    """
    leaked = _sse_response(
        _stream_body(
            prompt_tokens=10,
            completion_tokens=20,
            # Split the leak across two content chunks so the marker also
            # straddles a chunk boundary in part of the run.
            answer_chunks=(_LEAKED_MARKUP[:90], _LEAKED_MARKUP[90:]),
        )
    )
    respx.post(_COMPLETIONS_URL).mock(return_value=leaked)

    provider = _search_provider()
    answer_parts: list[str] = []
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, AnswerDelta):
            answer_parts.append(event.text)

    answer = "".join(answer_parts)
    # The clean lead-in prose (before the marker) survives; everything from the
    # marker onward is scrubbed.
    assert "Let me search for that." in answer
    for forbidden in ("tool_calls", "invoke name", "｜｜DSML", "DSML", "web_search", "<｜"):
        assert forbidden not in answer


@respx.mock
async def test_stream_web_search_round_cap_forces_terminal_answer() -> None:
    """If the model calls the tool EVERY round, the loop stops at the cap.

    Every round streams a `web_search` tool_call. The loop must stop after
    `_MAX_SEARCH_ROUNDS` completions; the final round is sent with
    `tool_choice="none"`. A terminal UsageUpdate + Complete still arrive, with
    usage summed across all capped rounds.
    """
    from app.providers.openai import _MAX_SEARCH_ROUNDS

    # Enough tool-call bodies to exceed the cap; only _MAX_SEARCH_ROUNDS consumed.
    bodies = [
        _sse_response(
            _tool_call_stream_body(query=f"q{i}", prompt_tokens=2, completion_tokens=3)
        )
        for i in range(_MAX_SEARCH_ROUNDS + 2)
    ]
    route = respx.post(_COMPLETIONS_URL).mock(side_effect=bodies)

    provider = _search_provider()
    usage_updates: list[UsageUpdate] = []
    completes: list[Complete] = []
    async for event in provider.stream(
        model_id="deepseek-v4-pro", history=[], user_text="hi", web_search=True
    ):
        if isinstance(event, UsageUpdate):
            usage_updates.append(event)
        elif isinstance(event, Complete):
            completes.append(event)

    # Stops exactly at the cap — no infinite loop.
    assert route.call_count == _MAX_SEARCH_ROUNDS
    # The final round was forced to answer (tool_choice="none").
    final_body = json.loads(route.calls[-1].request.content)
    assert final_body.get("tool_choice") == "none"
    # Still a single terminal UsageUpdate + Complete, usage summed across rounds.
    assert len(usage_updates) == 1
    assert len(completes) == 1
    assert usage_updates[0].input_tokens == 2 * _MAX_SEARCH_ROUNDS
    assert usage_updates[0].output_tokens == 3 * _MAX_SEARCH_ROUNDS
    assert completes[0].usage == usage_updates[0]
