"""Unit tests for the `complete(...)` non-streaming Protocol method.

Covers both implementations:
- `FakeProvider.complete` — deterministic 5-word title from user_text hash.
- `AnthropicProvider.complete` — single `messages.create` call, joined text
  blocks. Uses `respx` to mock the HTTP layer of the Anthropic SDK so the
  test never reaches the real API.

Title autogen uses `complete(...)` exclusively. These tests pin the contract
so the streaming path stays uncoupled from the autogen path.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.providers.anthropic import AnthropicProvider
from app.providers.fake import FakeProvider

pytestmark = pytest.mark.asyncio


# FakeProvider -----------------------------------------------------------------


async def test_fake_provider_complete_returns_deterministic_title() -> None:
    """Same `user_text` always produces the same title; different text differs."""
    provider = FakeProvider()
    title_a = await provider.complete(
        model_id="ignored", history=[], user_text="hello world"
    )
    title_a2 = await provider.complete(
        model_id="ignored", history=[], user_text="hello world"
    )

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
        candidate = await provider.complete(
            model_id="ignored", history=[], user_text=sample
        )
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
    title = await provider.complete(
        model_id="test-model", history=[], user_text="hi"
    )
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
    title = await provider.complete(
        model_id="test-model", history=[], user_text="hi"
    )
    assert title == ""
