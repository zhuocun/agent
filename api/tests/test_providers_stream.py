"""Streaming-path tests for `AnthropicProvider.stream(...)`.

Drives the SDK's streaming client against a mocked SSE response (`respx`) so we
exercise the real event-decoding + usage-ingestion path without hitting the
network. Anthropic puts `input_tokens` and the cache fields on `message_start`
and the cumulative `output_tokens` on `message_delta`; these tests pin that the
provider surfaces both buckets (a regression where usage was read only from
`message_delta` dropped `input_tokens` and under-billed every turn).

Also covers SDK error mapping: a 429 becomes a typed `RATE_LIMITED` AppError
(with `retryAfterMs` from the response header) and a 500 becomes
`PROVIDER_UPSTREAM`, with no raw SDK text leaking into the user-facing body.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from app.errors import AppError
from app.providers.anthropic import AnthropicProvider
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import (
    AnswerDelta,
    AttachmentPayload,
    Complete,
    Sources,
    StatusUpdate,
    UsageUpdate,
)
from app.providers.tiers import get_binding

pytestmark = pytest.mark.asyncio

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def _sse(event: str, data: dict[str, object]) -> str:
    """Render one SSE frame the way the Anthropic API streams events."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_body(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    answer_text: str = "Hello there",
) -> str:
    """Build a full SSE message stream.

    `input_tokens`/cache counts ride on `message_start`; the cumulative
    `output_tokens` rides on the final `message_delta` (mirroring real wire
    behavior, where `message_start.usage.output_tokens` is a small placeholder).
    """
    start_msg = {
        "id": "msg_stream_1",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": 1,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cache_creation_input_tokens": 0,
        },
    }
    frames = [
        _sse("message_start", {"type": "message_start", "message": start_msg}),
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": answer_text},
            },
        ),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            },
        ),
        _sse("message_stop", {"type": "message_stop"}),
    ]
    return "".join(frames)


def _sse_response(body: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body.encode("utf-8"),
    )


@respx.mock
async def test_stream_surfaces_input_and_output_tokens() -> None:
    """`message_start` input/cache + `message_delta` output both reach usage.

    Pre-fix this read usage only from `message_delta`, so `input_tokens` came
    back 0 and the cost breakdown billed output only.
    """
    respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(
            _stream_body(
                input_tokens=1234,
                output_tokens=567,
                cache_read_input_tokens=89,
            )
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    answer_parts: list[str] = []
    final_usage: UsageUpdate | None = None
    complete: Complete | None = None
    async for event in provider.stream(
        model_id="test-model", history=[], user_text="hi"
    ):
        if isinstance(event, UsageUpdate):
            final_usage = event
        elif isinstance(event, Complete):
            complete = event
        elif getattr(event, "type", None) == "answer_delta":
            answer_parts.append(getattr(event, "text", ""))

    assert "".join(answer_parts) == "Hello there"
    assert final_usage is not None
    # The bug: input_tokens dropped to 0 because usage was read from
    # message_delta only.
    assert final_usage.input_tokens == 1234
    assert final_usage.output_tokens == 567
    assert final_usage.cached_input_tokens == 89  # cache_read only
    assert final_usage.reasoning_tokens == 0
    # Complete carries the same merged usage.
    assert complete is not None
    assert complete.usage == final_usage

    # And the cost breakdown now bills input, not output-only.
    binding = get_binding("smart")
    assert binding is not None
    bd = compute_cost_breakdown(usage=final_usage, binding=binding)
    assert bd.input_tokens == 1234
    assert bd.output_tokens == 567
    expected_input_cost = 1234 * binding.list_price_in_per_m / 1_000_000
    assert expected_input_cost > 0
    assert bd.subtotal_usd > 567 * binding.list_price_out_per_m / 1_000_000


@respx.mock
async def test_stream_cache_creation_not_pooled_into_cache_read() -> None:
    """Cache-creation tokens must not land in the cache-read (10%) bucket."""
    body = _stream_body(input_tokens=100, output_tokens=10, cache_read_input_tokens=40)
    # Inject a non-zero cache_creation on message_start; it must be ignored.
    body = body.replace(
        '"cache_creation_input_tokens": 0', '"cache_creation_input_tokens": 999'
    )
    respx.post(_MESSAGES_URL).mock(return_value=_sse_response(body))

    provider = AnthropicProvider(api_key="sk-test")
    final_usage: UsageUpdate | None = None
    async for event in provider.stream(
        model_id="test-model", history=[], user_text="hi"
    ):
        if isinstance(event, UsageUpdate):
            final_usage = event

    assert final_usage is not None
    # Only cache_read (40) — NOT 40 + 999.
    assert final_usage.cached_input_tokens == 40


@respx.mock
async def test_stream_sends_attachment_bytes_as_multimodal_content() -> None:
    """Current-turn image/PDF bytes are sent to Anthropic, not metadata-only."""
    route = respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(_stream_body(input_tokens=10, output_tokens=10))
    )

    image_bytes = b"image-bytes"
    pdf_bytes = b"%PDF-bytes"
    provider = AnthropicProvider(api_key="sk-test")
    async for _ in provider.stream(
        model_id="test-model",
        history=[],
        user_text="read these",
        attachments=[
            AttachmentPayload(
                id="img-1",
                name="sketch.png",
                media_type="image",
                mime_type="image/png",
                size_bytes=len(image_bytes),
                data=image_bytes,
            ),
            AttachmentPayload(
                id="pdf-1",
                name="paper.pdf",
                media_type="pdf",
                mime_type="application/pdf",
                size_bytes=len(pdf_bytes),
                data=pdf_bytes,
            ),
        ],
    ):
        pass

    body = json.loads(route.calls.last.request.content)
    content = body["messages"][-1]["content"]
    assert isinstance(content, list)
    assert content[0] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(image_bytes).decode("ascii"),
        },
    }
    assert content[1] == {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.b64encode(pdf_bytes).decode("ascii"),
        },
    }
    assert content[2]["type"] == "text"
    assert content[2]["text"].endswith("read these")


@respx.mock
async def test_stream_adds_instruction_for_attachment_only_send() -> None:
    route = respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(_stream_body(input_tokens=10, output_tokens=10))
    )

    image_bytes = b"image-bytes"
    provider = AnthropicProvider(api_key="sk-test")
    async for _ in provider.stream(
        model_id="test-model",
        history=[],
        user_text="",
        attachments=[
            AttachmentPayload(
                id="img-1",
                name="sketch.png",
                media_type="image",
                mime_type="image/png",
                size_bytes=len(image_bytes),
                data=image_bytes,
            ),
        ],
    ):
        pass

    body = json.loads(route.calls.last.request.content)
    content = body["messages"][-1]["content"]
    assert isinstance(content, list)
    assert content[1]["type"] == "text"
    assert "Please analyze the attached file(s)." in content[1]["text"]


@respx.mock
async def test_stream_sends_text_attachment_transcript_as_text_content() -> None:
    """Text documents are sent as bounded transcripts, not native raw bytes."""
    route = respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(_stream_body(input_tokens=10, output_tokens=10))
    )

    provider = AnthropicProvider(api_key="sk-test")
    async for _ in provider.stream(
        model_id="test-model",
        history=[],
        user_text="summarize",
        attachments=[
            AttachmentPayload(
                id="txt-1",
                name="notes.txt",
                media_type="text",
                mime_type="text/plain",
                size_bytes=16,
                data=b"Alpha beta notes",
                extracted_text="Alpha beta notes",
            ),
        ],
    ):
        pass

    body = json.loads(route.calls.last.request.content)
    content = body["messages"][-1]["content"]
    assert isinstance(content, str)
    assert "notes.txt (text/plain, 16 bytes)" in content
    assert "Alpha beta notes" in content


@respx.mock
async def test_stream_maps_rate_limit_to_app_error() -> None:
    """A 429 stream open becomes RATE_LIMITED with retryAfterMs, no raw text."""
    respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(
            429,
            headers={"retry-after": "2"},
            json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(
            model_id="test-model", history=[], user_text="hi"
        ):
            pass

    err = excinfo.value
    assert err.envelope.code == "RATE_LIMITED"
    assert err.status_code == 429
    assert err.envelope.retry_after_ms == 2000  # 2s header → ms
    assert "slow down" not in err.envelope.body


@respx.mock
async def test_stream_maps_server_error_to_provider_upstream() -> None:
    """A 500 stream open becomes PROVIDER_UPSTREAM, no raw SDK text in body."""
    respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(
            500,
            json={"type": "error", "error": {"type": "api_error", "message": "boom internal"}},
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    with pytest.raises(AppError) as excinfo:
        async for _ in provider.stream(
            model_id="test-model", history=[], user_text="hi"
        ):
            pass

    err = excinfo.value
    assert err.envelope.code == "PROVIDER_UPSTREAM"
    assert err.status_code in (502, 503)
    assert "boom internal" not in err.envelope.body


@respx.mock
async def test_complete_maps_rate_limit_to_app_error() -> None:
    """`complete(...)` also maps a 429 to RATE_LIMITED with retryAfterMs (ms hdr)."""
    respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(
            429,
            headers={"retry-after-ms": "1500"},
            json={"type": "error", "error": {"type": "rate_limit_error", "message": "nope"}},
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    with pytest.raises(AppError) as excinfo:
        await provider.complete(model_id="test-model", history=[], user_text="hi")

    err = excinfo.value
    assert err.envelope.code == "RATE_LIMITED"
    assert err.envelope.retry_after_ms == 1500
    assert "nope" not in err.envelope.body


@respx.mock
async def test_complete_maps_server_error_to_provider_upstream() -> None:
    """`complete(...)` maps a 503 to PROVIDER_UPSTREAM (503)."""
    respx.post(_MESSAGES_URL).mock(
        return_value=httpx.Response(
            503,
            json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}},
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    with pytest.raises(AppError) as excinfo:
        await provider.complete(model_id="test-model", history=[], user_text="hi")

    err = excinfo.value
    assert err.envelope.code == "PROVIDER_UPSTREAM"
    assert err.status_code == 503
    assert "busy" not in err.envelope.body


# --- web_search (server-side hosted tool, best-effort) -------------------------
#
# Anthropic runs the search server-side and streams `server_tool_use` (it
# dispatched a search) + `web_search_tool_result` (results returned) content
# blocks. The provider maps those to StatusUpdate(active/done) + Sources. With
# web_search=False the path is unchanged (no tools advertised).


def _web_search_stream_body(*, input_tokens: int, output_tokens: int) -> str:
    """An SSE stream that includes a server_tool_use + web_search_tool_result.

    Mirrors Anthropic's hosted web-search wire shape: the model emits a
    `server_tool_use` block (the dispatched query), then a
    `web_search_tool_result` block carrying `web_search_result` entries, then a
    `text` block with the grounded answer.
    """
    start_msg = {
        "id": "msg_ws_1",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
    frames = [
        _sse("message_start", {"type": "message_start", "message": start_msg}),
        # The model dispatches a server-side search.
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "server_tool_use",
                    "id": "srvtoolu_1",
                    "name": "web_search",
                    "input": {},
                },
            },
        ),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        # Results return.
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srvtoolu_1",
                    "content": [
                        {
                            "type": "web_search_result",
                            "title": "Rust 1.99 released",
                            "url": "https://blog.rust-lang.org/1.99.html",
                            "content": "The Rust team announced 1.99.",
                            "encrypted_content": "enc1",
                            "page_age": None,
                        },
                        {
                            "type": "web_search_result",
                            "title": "Release notes",
                            "url": "https://doc.rust-lang.org/notes",
                            "content": "Detailed changelog.",
                            "encrypted_content": "enc2",
                            "page_age": None,
                        },
                    ],
                },
            },
        ),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 1}),
        # Grounded answer text.
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "text_delta", "text": "Rust 1.99 is out [1]."},
            },
        ),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 2}),
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            },
        ),
        _sse("message_stop", {"type": "message_stop"}),
    ]
    return "".join(frames)


@respx.mock
async def test_stream_web_search_emits_status_and_sources() -> None:
    """server_tool_use -> Status(active); web_search_tool_result -> Status(done)+Sources."""
    respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(_web_search_stream_body(input_tokens=10, output_tokens=20))
    )

    provider = AnthropicProvider(api_key="sk-test")
    seq: list[str] = []
    statuses: list[StatusUpdate] = []
    sources: list[Sources] = []
    answer_parts: list[str] = []
    async for event in provider.stream(
        model_id="test-model", history=[], user_text="latest rust", web_search=True
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

    assert [s.state for s in statuses] == ["active", "done"]
    assert statuses[0].label == "Searching the web…"
    assert seq.index("status:active") < seq.index("status:done") < seq.index("sources")
    assert seq.index("sources") < seq.index("answer")

    assert len(sources) == 1
    items = sources[0].items
    assert [it.id for it in items] == [1, 2]
    assert items[0].title == "Rust 1.99 released"
    assert items[0].domain == "blog.rust-lang.org"
    assert "".join(answer_parts) == "Rust 1.99 is out [1]."


@respx.mock
async def test_stream_web_search_advertises_tool() -> None:
    """web_search=True sends the hosted web_search tool; False sends no tools."""
    route = respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(_stream_body(input_tokens=5, output_tokens=5))
    )

    provider = AnthropicProvider(api_key="sk-test")
    async for _ in provider.stream(
        model_id="test-model", history=[], user_text="hi", web_search=True
    ):
        pass
    body = json.loads(route.calls.last.request.content)
    assert body.get("tools") == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
    ]


@respx.mock
async def test_stream_web_search_false_sends_no_tools() -> None:
    """web_search=False -> no tools key, behavior unchanged."""
    route = respx.post(_MESSAGES_URL).mock(
        return_value=_sse_response(_stream_body(input_tokens=5, output_tokens=5))
    )

    provider = AnthropicProvider(api_key="sk-test")
    search_events = 0
    async for event in provider.stream(
        model_id="test-model", history=[], user_text="hi", web_search=False
    ):
        if isinstance(event, (StatusUpdate, Sources)):
            search_events += 1
    body = json.loads(route.calls.last.request.content)
    assert "tools" not in body
    assert search_events == 0
