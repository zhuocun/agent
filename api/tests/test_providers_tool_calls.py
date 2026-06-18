"""Real-provider native tool wiring (T14b).

Exercises the OpenAI-compatible and Anthropic adapters advertising the built-in
tool registry natively, parsing the model's tool calls into structured
`ToolCall` events, and — when driven by `run_agent_loop` — executing the tool
(auto path), reconstructing the result as NATIVE tool messages for the next
round, and pausing on the human-in-the-loop approval gate.

The SDKs are mocked with `respx` so we drive the real chunk/event decoding
without a network. The agent loop is the same one the handler wraps the provider
in when `TOOLS_ENABLED`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import respx

from app.config import Settings
from app.providers.anthropic import AnthropicProvider
from app.providers.openai import OpenAIProvider
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    ChatMessage,
    Complete,
    ProviderEvent,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from app.tools.agent_loop import (
    TOOL_FEEDBACK_SENTINEL,
    parse_tool_feedback_history,
    run_agent_loop,
    tool_feedback_to_history,
)
from app.tools.builtin import TOOL_REGISTRY

# `asyncio_mode = "auto"` (pyproject) marks the async tests automatically, so a
# module-level `pytest.mark.asyncio` would wrongly tag the two SYNC unit tests
# below (`parse_tool_feedback_history`) and warn. Leave the async tests to auto.

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _registry_tool_defs() -> list[ToolDefinition]:
    """The same neutral tool definitions the handler builds from the registry."""
    return [
        ToolDefinition(name=spec.name, label=spec.label, parameters=spec.schema)
        for spec in TOOL_REGISTRY.values()
    ]


def _time_tool() -> ToolDefinition:
    spec = TOOL_REGISTRY["get_current_time"]
    return ToolDefinition(name=spec.name, label=spec.label, parameters=spec.schema)


# --- parse_tool_feedback_history ---------------------------------------------


def test_parse_tool_feedback_history_round_trips() -> None:
    """The encoder/decoder are symmetric: encode results, decode them back out."""
    results = [
        ToolResult(
            tool_call_id="call_1",
            name="get_current_time",
            status="succeeded",
            output={"iso8601": "2026-01-01T00:00:00+00:00", "timezone": "UTC"},
        ),
    ]
    history = [ChatMessage(role="user", text="hi"), *tool_feedback_to_history(results)]
    clean, parsed, assistant_reasoning = parse_tool_feedback_history(history)
    # The sentinel turn is stripped; the plain user turn survives.
    assert [m.role for m in clean] == ["user"]
    assert not any(TOOL_FEEDBACK_SENTINEL in m.text for m in clean)
    assert len(parsed) == 1
    assert parsed[0]["toolCallId"] == "call_1"
    assert parsed[0]["name"] == "get_current_time"
    assert parsed[0]["status"] == "succeeded"
    assert assistant_reasoning is None


def test_parse_tool_feedback_history_round_trips_reasoning() -> None:
    """Assistant reasoning from the tool-calling turn survives encode/decode."""
    results = [
        ToolResult(
            tool_call_id="call_1",
            name="get_current_time",
            status="succeeded",
            output={"iso8601": "2026-01-01T00:00:00+00:00", "timezone": "UTC"},
            round_reasoning="Need the current time.",
        ),
    ]
    history = [ChatMessage(role="user", text="hi"), *tool_feedback_to_history(results)]
    clean, parsed, assistant_reasoning = parse_tool_feedback_history(history)
    assert [m.role for m in clean] == ["user"]
    assert len(parsed) == 1
    assert assistant_reasoning == "Need the current time."


def test_parse_tool_feedback_history_no_sentinel_is_passthrough() -> None:
    """History without a sentinel turn is returned unchanged, no results."""
    history = [ChatMessage(role="user", text="hi"), ChatMessage(role="assistant", text="hello")]
    clean, parsed, assistant_reasoning = parse_tool_feedback_history(history)
    assert clean == history
    assert parsed == []
    assert assistant_reasoning is None


# --- OpenAI-compatible adapter ------------------------------------------------


def _openai_chunk(data: dict[str, object]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _openai_tool_call_body(*, name: str, arguments: str, call_id: str = "call_x") -> str:
    """An SSE body whose single completion emits one function tool_call."""
    frames = [
        _openai_chunk(
            {
                "id": "c1",
                "object": "chat.completion.chunk",
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": call_id,
                                    "type": "function",
                                    "function": {"name": name, "arguments": arguments},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
        ),
        _openai_chunk(
            {
                "id": "c1",
                "object": "chat.completion.chunk",
                "model": "gpt-4o",
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            }
        ),
        "data: [DONE]\n\n",
    ]
    return "".join(frames)


def _openai_answer_body(text: str = "It is noon.") -> str:
    frames = [
        _openai_chunk(
            {
                "id": "c2",
                "object": "chat.completion.chunk",
                "model": "gpt-4o",
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            }
        ),
        _openai_chunk(
            {
                "id": "c2",
                "object": "chat.completion.chunk",
                "model": "gpt-4o",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        ),
        _openai_chunk(
            {
                "id": "c2",
                "object": "chat.completion.chunk",
                "model": "gpt-4o",
                "choices": [],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "total_tokens": 28,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            }
        ),
        "data: [DONE]\n\n",
    ]
    return "".join(frames)


def _sse_response(body: str) -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=body.encode("utf-8")
    )


def _openai_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", base_url="https://api.openai.com/v1")


@respx.mock
async def test_openai_advertises_registry_tools_and_emits_tool_call() -> None:
    """`tools` advertised → a model tool_call becomes a `ToolCall` event, no Complete."""
    route = respx.post(_OPENAI_URL).mock(
        return_value=_sse_response(
            _openai_tool_call_body(name="get_current_time", arguments='{"timezone": "UTC"}')
        )
    )

    provider = _openai_provider()
    events: list[ProviderEvent] = []
    async for ev in provider.stream(
        model_id="gpt-4o", history=[], user_text="what time is it?", tools=[_time_tool()]
    ):
        events.append(ev)

    # The registry tool was advertised as an OpenAI function tool.
    body = json.loads(route.calls.last.request.content)
    advertised = {t["function"]["name"] for t in body["tools"]}
    assert "get_current_time" in advertised
    assert body["tool_choice"] == "auto"

    # The model's tool call surfaced as a structured ToolCall (running), and the
    # provider STOPPED — no Complete (the agent loop fulfills it next).
    tool_calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "get_current_time"
    assert tool_calls[0].status == "running"
    assert tool_calls[0].input == {"timezone": "UTC"}
    assert not any(isinstance(e, Complete) for e in events)


@respx.mock
async def test_openai_agent_loop_auto_tool_round_trip() -> None:
    """End-to-end: tool_call round → loop executes → result fed back → grounded answer."""
    respx.post(_OPENAI_URL).mock(
        side_effect=[
            _sse_response(_openai_tool_call_body(name="get_current_time", arguments="{}")),
            _sse_response(_openai_answer_body("It is noon UTC.")),
        ]
    )
    provider = _openai_provider()

    def _make_stream(
        feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        history = tool_feedback_to_history(feedback)
        return provider.stream(
            model_id="gpt-4o",
            history=list(history),
            user_text="what time?",
            tools=None if suppress_tools else [_time_tool()],
        )

    events = [
        ev async for ev in run_agent_loop(make_stream=_make_stream, settings=Settings())
    ]
    kinds = [type(e).__name__ for e in events]
    assert "ToolCall" in kinds
    assert "ToolResult" in kinds
    assert "Complete" in kinds

    tool_result = next(e for e in events if isinstance(e, ToolResult))
    assert tool_result.name == "get_current_time"
    assert tool_result.status == "succeeded"
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer == "It is noon UTC."


@respx.mock
async def test_openai_feedback_round_reconstructs_native_tool_messages() -> None:
    """The fed-back result becomes a NATIVE assistant tool_calls + role=tool message.

    Crucially the tool messages are appended AFTER the current user turn so the
    OpenAI conversation is well-formed (assistant tool_calls → matching tool).
    """
    route = respx.post(_OPENAI_URL).mock(return_value=_sse_response(_openai_answer_body("Done.")))
    provider = _openai_provider()

    fed = [
        ToolResult(
            tool_call_id="call_abc",
            name="get_current_time",
            status="succeeded",
            output={"iso8601": "2026-01-01T00:00:00+00:00", "timezone": "UTC"},
        )
    ]
    history = tool_feedback_to_history(fed)
    async for _ in provider.stream(
        model_id="gpt-4o", history=list(history), user_text="what time?", tools=[_time_tool()]
    ):
        pass

    body = json.loads(route.calls.last.request.content)
    roles = [m["role"] for m in body["messages"]]
    # user turn precedes the reconstructed assistant(tool_calls) + tool result.
    assert roles == ["user", "assistant", "tool"]
    assistant = body["messages"][1]
    assert assistant["tool_calls"][0]["id"] == "call_abc"
    assert assistant["tool_calls"][0]["function"]["name"] == "get_current_time"
    tool_msg = body["messages"][2]
    assert tool_msg["tool_call_id"] == "call_abc"
    assert json.loads(tool_msg["content"])["status"] == "succeeded"


@respx.mock
async def test_openai_feedback_round_reconstructs_reasoning_for_thinking() -> None:
    """DeepSeek thinking mode requires reasoning_content on tool-call replay."""
    route = respx.post(_OPENAI_URL).mock(return_value=_sse_response(_openai_answer_body("Done.")))
    provider = _openai_provider()

    fed = [
        ToolResult(
            tool_call_id="call_abc",
            name="get_current_time",
            status="succeeded",
            output={"iso8601": "2026-01-01T00:00:00+00:00", "timezone": "UTC"},
            round_reasoning="Checking the clock.",
        )
    ]
    history = tool_feedback_to_history(fed)
    async for _ in provider.stream(
        model_id="deepseek-v4-flash",
        history=list(history),
        user_text="what time?",
        tools=[_time_tool()],
        thinking=True,
    ):
        pass

    body = json.loads(route.calls.last.request.content)
    assistant = body["messages"][1]
    assert assistant["reasoning_content"] == "Checking the clock."


@respx.mock
async def test_openai_approval_gated_tool_pauses_via_agent_loop() -> None:
    """A model call to an approval-gated tool pauses the loop (AwaitingApproval)."""
    respx.post(_OPENAI_URL).mock(
        return_value=_sse_response(
            _openai_tool_call_body(
                name="calendar_create_event", arguments='{"title": "Sync"}', call_id="call_cal"
            )
        )
    )
    provider = _openai_provider()

    def _make_stream(
        feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        history = tool_feedback_to_history(feedback)
        return provider.stream(
            model_id="gpt-4o",
            history=list(history),
            user_text="schedule a sync",
            tools=None if suppress_tools else _registry_tool_defs(),
        )

    events = [
        ev async for ev in run_agent_loop(make_stream=_make_stream, settings=Settings())
    ]
    # The gated call is relayed (running) then the loop pauses — no execution,
    # no Complete (the resume POST applies the decision).
    tool_call = next(e for e in events if isinstance(e, ToolCall))
    assert tool_call.name == "calendar_create_event"
    assert any(isinstance(e, AwaitingApproval) for e in events)
    assert not any(isinstance(e, Complete) for e in events)
    assert not any(isinstance(e, ToolResult) for e in events)


@respx.mock
async def test_openai_no_tools_is_unchanged() -> None:
    """tools=None → no tools advertised; identical to a pre-tools build."""
    route = respx.post(_OPENAI_URL).mock(return_value=_sse_response(_openai_answer_body("Hi")))
    provider = _openai_provider()
    async for _ in provider.stream(model_id="gpt-4o", history=[], user_text="hi"):
        pass
    body = json.loads(route.calls.last.request.content)
    assert "tools" not in body


# --- Anthropic adapter --------------------------------------------------------


def _anthropic_sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _anthropic_tool_use_body(*, name: str, args_json: str, tool_id: str = "toolu_1") -> str:
    """An SSE message stream that emits a single client-side tool_use block."""
    start_msg = {
        "id": "msg_tu_1",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
    return "".join(
        [
            _anthropic_sse("message_start", {"type": "message_start", "message": start_msg}),
            _anthropic_sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}},
                },
            ),
            _anthropic_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": args_json},
                },
            ),
            _anthropic_sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
            _anthropic_sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                    "usage": {"output_tokens": 6},
                },
            ),
            _anthropic_sse("message_stop", {"type": "message_stop"}),
        ]
    )


def _anthropic_text_body(text: str = "It is noon.") -> str:
    start_msg = {
        "id": "msg_txt_1",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 20,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
    return "".join(
        [
            _anthropic_sse("message_start", {"type": "message_start", "message": start_msg}),
            _anthropic_sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            _anthropic_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                },
            ),
            _anthropic_sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
            _anthropic_sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 8},
                },
            ),
            _anthropic_sse("message_stop", {"type": "message_stop"}),
        ]
    )


@respx.mock
async def test_anthropic_advertises_registry_tools_and_emits_tool_call() -> None:
    """`tools` advertised → a tool_use block becomes a `ToolCall` event, no Complete."""
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=_sse_response(
            _anthropic_tool_use_body(name="get_current_time", args_json='{"timezone": "UTC"}')
        )
    )
    provider = AnthropicProvider(api_key="sk-test")
    events: list[ProviderEvent] = []
    async for ev in provider.stream(
        model_id="test-model", history=[], user_text="what time?", tools=[_time_tool()]
    ):
        events.append(ev)

    body = json.loads(route.calls.last.request.content)
    advertised = {t["name"] for t in body["tools"]}
    assert "get_current_time" in advertised

    tool_calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "get_current_time"
    assert tool_calls[0].input == {"timezone": "UTC"}
    assert not any(isinstance(e, Complete) for e in events)


@respx.mock
async def test_anthropic_agent_loop_auto_tool_round_trip() -> None:
    """End-to-end: tool_use round → loop executes → tool_result fed back → answer."""
    respx.post(_ANTHROPIC_URL).mock(
        side_effect=[
            _sse_response(_anthropic_tool_use_body(name="get_current_time", args_json="{}")),
            _sse_response(_anthropic_text_body("It is noon UTC.")),
        ]
    )
    provider = AnthropicProvider(api_key="sk-test")

    def _make_stream(
        feedback: list[ToolResult], suppress_tools: bool = False
    ) -> AsyncIterator[ProviderEvent]:
        history = tool_feedback_to_history(feedback)
        return provider.stream(
            model_id="test-model",
            history=list(history),
            user_text="what time?",
            tools=None if suppress_tools else [_time_tool()],
        )

    events = [
        ev async for ev in run_agent_loop(make_stream=_make_stream, settings=Settings())
    ]
    tool_result = next(e for e in events if isinstance(e, ToolResult))
    assert tool_result.name == "get_current_time"
    assert tool_result.status == "succeeded"
    answer = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert answer == "It is noon UTC."
    assert any(isinstance(e, Complete) for e in events)


@respx.mock
async def test_anthropic_feedback_round_reconstructs_native_tool_blocks() -> None:
    """The fed-back result becomes a NATIVE assistant tool_use + user tool_result turn."""
    route = respx.post(_ANTHROPIC_URL).mock(
        return_value=_sse_response(_anthropic_text_body("Done."))
    )
    provider = AnthropicProvider(api_key="sk-test")
    fed = [
        ToolResult(
            tool_call_id="toolu_abc",
            name="get_current_time",
            status="succeeded",
            output={"iso8601": "2026-01-01T00:00:00+00:00", "timezone": "UTC"},
        )
    ]
    history = tool_feedback_to_history(fed)
    async for _ in provider.stream(
        model_id="test-model", history=list(history), user_text="what time?", tools=[_time_tool()]
    ):
        pass

    body = json.loads(route.calls.last.request.content)
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant", "user"]
    tool_use = body["messages"][1]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["id"] == "toolu_abc"
    tool_result_block = body["messages"][2]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "toolu_abc"
