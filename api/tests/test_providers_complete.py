"""Unit tests for the `complete(...)` non-streaming Protocol method.

Covers all three implementations:
- `FakeProvider.complete` — deterministic 5-word title from user_text hash.
- `AnthropicProvider.complete` — single `messages.create` call, joined text
  blocks. Uses `respx` to mock the HTTP layer of the Anthropic SDK so the
  test never reaches the real API.
- `OpenAIProvider.complete` — single non-streaming `chat.completions.create`
  call; returns the first choice's stripped message content (empty string when
  there is no choice / no text content). Also `respx`-mocked.

Title autogen uses `complete(...)` exclusively. These tests pin the contract
so the streaming path stays uncoupled from the autogen path.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.errors import AppError
from app.providers.anthropic import AnthropicProvider
from app.providers.fake import FakeProvider
from app.providers.openai import OpenAIProvider

pytestmark = pytest.mark.asyncio

_OPENAI_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def _openai_completion(content: object | None, *, with_choice: bool = True) -> dict:
    """Build a non-streaming OpenAI chat completion response body."""
    choices: list[dict] = []
    if with_choice:
        choices = [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    return {
        "id": "chatcmpl-title",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": choices,
        "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
    }


# FakeProvider -----------------------------------------------------------------


async def test_fake_provider_complete_returns_deterministic_title() -> None:
    """Same `user_text` always produces the same title; different text differs."""
    provider = FakeProvider()
    title_a = await provider.complete(model_id="ignored", history=[], user_text="hello world")
    title_a2 = await provider.complete(model_id="ignored", history=[], user_text="hello world")

    # Determinism.
    assert title_a == title_a2
    # Non-empty 4-6 word title.
    words = title_a.split()
    assert len(words) >= 4
    assert len(words) <= 6
    # Differentiation: scan several distinct inputs and confirm at least one
    # produces a title distinct from `title_a`. The template pool has 8
    # entries, so a single pair could collide; scan a small batch to make
    # the assertion robust without depending on hash distribution specifics.
    distinct_seen = False
    for sample in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"):
        candidate = await provider.complete(model_id="ignored", history=[], user_text=sample)
        if candidate != title_a:
            distinct_seen = True
            break
    assert distinct_seen, "fake provider should not always return the same title"


# AnthropicProvider ------------------------------------------------------------


@respx.mock
async def test_anthropic_provider_complete_joins_text_blocks() -> None:
    """A 200 response with a text content block returns the joined text."""
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_abc123",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [
                    {"type": "text", "text": "Concise five word title here"},
                ],
                "usage": {"input_tokens": 12, "output_tokens": 5},
            },
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    title = await provider.complete(
        model_id="test-model",
        history=[],
        user_text="please summarize",
    )

    assert route.called
    assert title == "Concise five word title here"


@respx.mock
async def test_anthropic_provider_complete_handles_multi_block_response() -> None:
    """Multiple text blocks are concatenated; non-text blocks are skipped."""
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_xyz",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [
                    {"type": "thinking", "thinking": "internal"},  # skipped
                    {"type": "text", "text": "Part one "},
                    {"type": "text", "text": "part two"},
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    title = await provider.complete(model_id="test-model", history=[], user_text="hi")
    assert title == "Part one part two"


@respx.mock
async def test_anthropic_provider_complete_returns_empty_on_no_text_block() -> None:
    """A response with no `text` content block returns an empty string."""
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_only_thinking",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [{"type": "thinking", "thinking": "only thinking"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )

    provider = AnthropicProvider(api_key="sk-test")
    title = await provider.complete(model_id="test-model", history=[], user_text="hi")
    assert title == ""


# OpenAIProvider ---------------------------------------------------------------


def _openai_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", base_url="https://api.openai.com/v1")


@respx.mock
async def test_openai_provider_complete_returns_stripped_text() -> None:
    """A 200 response returns the first choice's content, stripped."""
    route = respx.post(_OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200, json=_openai_completion("  Concise five word title here  ")
        )
    )

    provider = _openai_provider()
    title = await provider.complete(
        model_id="gpt-4o-mini", history=[], user_text="please summarize"
    )

    assert route.called
    assert title == "Concise five word title here"


@respx.mock
async def test_openai_provider_complete_empty_on_no_choices() -> None:
    """A response with no choices returns an empty string."""
    respx.post(_OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_openai_completion(None, with_choice=False))
    )

    provider = _openai_provider()
    title = await provider.complete(model_id="gpt-4o-mini", history=[], user_text="hi")
    assert title == ""


@respx.mock
async def test_openai_provider_complete_empty_on_null_content() -> None:
    """A choice whose message content is null returns an empty string."""
    respx.post(_OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_openai_completion(None))
    )

    provider = _openai_provider()
    title = await provider.complete(model_id="gpt-4o-mini", history=[], user_text="hi")
    assert title == ""


@respx.mock
async def test_openai_provider_complete_maps_error_to_app_error() -> None:
    """An upstream error on the complete() path surfaces a typed AppError.

    Both stream() and complete() route SDK errors through the same mapper; this
    pins the complete() try/except so a regression there can't go uncaught.
    """
    respx.post(_OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            503, json={"error": {"type": "overloaded", "message": "busy now"}}
        )
    )

    provider = _openai_provider()
    with pytest.raises(AppError) as excinfo:
        await provider.complete(model_id="gpt-4o-mini", history=[], user_text="hi")

    err = excinfo.value
    assert err.envelope.code == "PROVIDER_UPSTREAM"
    assert err.status_code == 503
    assert "busy now" not in err.envelope.body
