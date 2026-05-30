"""Language-steering tests for the real providers' outgoing request bodies.

The bug: with no system prompt by design (o-series compatibility), DeepSeek (a
Chinese-trained model, our default real provider) replied in Chinese to a bare
English "Hello". The fix prefixes a one-line language steer onto the CURRENT
user turn of the OUTGOING request to a real provider only.

These tests pin the contract by inspecting the request body respx captures:
- `OpenAIProvider.stream` / `AnthropicProvider.stream`: the final (current) user
  message starts with the steer constant and ends with the original `user_text`;
  any `history` messages are forwarded verbatim (no steer).
- `complete()` (title autogen) sends the original text unmodified — no steer.

Hermetic: no network. The SDK HTTP layer is `respx`-mocked.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.providers.anthropic import AnthropicProvider
from app.providers.openai import OpenAIProvider
from app.providers.protocol import ChatMessage
from app.providers.steering import STEER_PREFIX, steer_user_text

pytestmark = pytest.mark.asyncio

_OPENAI_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


# Helpers ----------------------------------------------------------------------


def _openai_stream_body() -> str:
    """A minimal OpenAI streaming SSE body: one content chunk + [DONE]."""
    chunk = {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "model": "gpt-4o",
        "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"


def _openai_sse_response() -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=_openai_stream_body().encode("utf-8"),
    )


def _anthropic_stream_body() -> str:
    """A minimal Anthropic SSE message stream with one text delta."""

    def _sse(event: str, data: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    start_msg = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    return "".join(
        [
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
                    "delta": {"type": "text_delta", "text": "ok"},
                },
            ),
            _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
            _sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                },
            ),
            _sse("message_stop", {"type": "message_stop"}),
        ]
    )


def _anthropic_sse_response() -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=_anthropic_stream_body().encode("utf-8"),
    )


def _sent_messages(route: respx.Route) -> list[dict]:
    """Decode the `messages` array from the captured request body."""
    body = json.loads(route.calls.last.request.content)
    messages = body["messages"]
    assert isinstance(messages, list)
    return messages


# The helper itself ------------------------------------------------------------


async def test_steer_user_text_prefixes_and_preserves() -> None:
    out = steer_user_text("Hello")
    assert out.startswith(STEER_PREFIX)
    assert out.endswith("Hello")
    assert out == f"{STEER_PREFIX}Hello"


# OpenAIProvider ---------------------------------------------------------------


def _openai_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", base_url="https://api.openai.com/v1")


@respx.mock
async def test_openai_stream_steers_current_turn_only() -> None:
    """The current user turn is steered; history is forwarded verbatim."""
    route = respx.post(_OPENAI_COMPLETIONS_URL).mock(return_value=_openai_sse_response())

    provider = _openai_provider()
    history = [
        ChatMessage(role="user", text="prior question"),
        ChatMessage(role="assistant", text="prior answer"),
    ]
    async for _ in provider.stream(
        model_id="gpt-4o", history=history, user_text="Hello"
    ):
        pass

    assert route.called
    messages = _sent_messages(route)
    # History forwarded unmodified, no steer.
    assert messages[0] == {"role": "user", "content": "prior question"}
    assert messages[1] == {"role": "assistant", "content": "prior answer"}
    assert STEER_PREFIX not in messages[0]["content"]
    assert STEER_PREFIX not in messages[1]["content"]
    # Current (final) turn is steered: starts with the steer, ends with original.
    current = messages[-1]
    assert current["role"] == "user"
    assert current["content"].startswith(STEER_PREFIX)
    assert current["content"].endswith("Hello")
    assert current["content"] == f"{STEER_PREFIX}Hello"


@respx.mock
async def test_openai_complete_does_not_steer() -> None:
    """Title autogen (`complete`) sends the original text unmodified."""
    route = respx.post(_OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-title",
                "object": "chat.completion",
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "A Title"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )
    )

    provider = _openai_provider()
    await provider.complete(model_id="gpt-4o-mini", history=[], user_text="Hello")

    assert route.called
    messages = _sent_messages(route)
    assert messages[-1] == {"role": "user", "content": "Hello"}
    assert STEER_PREFIX not in messages[-1]["content"]


# AnthropicProvider ------------------------------------------------------------


@respx.mock
async def test_anthropic_stream_steers_current_turn_only() -> None:
    """The current user turn is steered; history is forwarded verbatim."""
    route = respx.post(_ANTHROPIC_MESSAGES_URL).mock(return_value=_anthropic_sse_response())

    provider = AnthropicProvider(api_key="sk-test")
    history = [
        ChatMessage(role="user", text="prior question"),
        ChatMessage(role="assistant", text="prior answer"),
    ]
    async for _ in provider.stream(
        model_id="test-model", history=history, user_text="Hello"
    ):
        pass

    assert route.called
    messages = _sent_messages(route)
    assert messages[0] == {"role": "user", "content": "prior question"}
    assert messages[1] == {"role": "assistant", "content": "prior answer"}
    assert STEER_PREFIX not in messages[0]["content"]
    assert STEER_PREFIX not in messages[1]["content"]
    current = messages[-1]
    assert current["role"] == "user"
    assert current["content"].startswith(STEER_PREFIX)
    assert current["content"].endswith("Hello")
    assert current["content"] == f"{STEER_PREFIX}Hello"


@respx.mock
async def test_anthropic_complete_does_not_steer() -> None:
    """Title autogen (`complete`) sends the original text unmodified."""
    route = respx.post(_ANTHROPIC_MESSAGES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_abc",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [{"type": "text", "text": "A Title"}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    await provider.complete(model_id="test-model", history=[], user_text="Hello")

    assert route.called
    messages = _sent_messages(route)
    assert messages[-1] == {"role": "user", "content": "Hello"}
    assert STEER_PREFIX not in messages[-1]["content"]
