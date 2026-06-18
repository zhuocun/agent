"""Real-provider agentic path proof without network (M4 gate)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest

from app.agentic.orchestrator import run_orchestrator
from app.agentic.planner import build_planner_prompt
from app.config import Settings
from app.providers.protocol import AnswerDelta, Complete, UsageUpdate
from app.tools.agent_loop import MakeStream

pytestmark = pytest.mark.asyncio


@pytest.fixture
def deepseek_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("PROVIDER_BACKEND", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("TOOLS_ENABLED", "true")
    monkeypatch.setenv("AGENTIC_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def _make_stream_factory() -> tuple[object, list[str]]:
    prompts: list[str] = []

    def _factory(prompt: str) -> MakeStream:
        prompts.append(prompt)

        async def _stream(
            _tool_feedback: list[object], _suppress_tools: bool = False
        ) -> AsyncIterator[object]:
            if "planner for a deep-research run" in prompt:
                yield AnswerDelta(text="alpha question\nbeta question")
            elif "synthesizer for a deep-research run" in prompt:
                yield AnswerDelta(text="Streamed synthesis result.")
            elif "focused research sub-agent" in prompt:
                yield AnswerDelta(text=f"Finding for {prompt[-24:]}")
            else:
                yield AnswerDelta(text="unexpected prompt")
            usage = UsageUpdate(input_tokens=10, output_tokens=5)
            yield usage
            yield Complete(usage=usage)

        return _stream

    return _factory, prompts


async def test_real_provider_orchestrator_streams_model_synthesis(
    deepseek_settings: Settings,
) -> None:
    factory, prompts = _make_stream_factory()
    events: list[object] = []
    async for event in run_orchestrator(
        make_stream_for=factory,
        settings=deepseek_settings,
        mode="deep_research",
        user_text="Compare solar and wind energy tradeoffs",
        cost_for_usage=lambda _usage: 0.0,
    ):
        events.append(event)

    assert any(
        isinstance(ev, AnswerDelta)
        and ev.subagent_id == "aggregator"
        and "Streamed synthesis result." in ev.text
        for ev in events
    )
    assert not any(
        isinstance(ev, AnswerDelta) and "Synthesis of 2 findings" in ev.text for ev in events
    )
    assert any("focused research sub-agent" in p for p in prompts)
    assert all("DEEP_RESEARCH_WORKER:" not in p for p in prompts)
    assert all("DEEP_RESEARCH:" not in p for p in prompts)
    assert any(build_planner_prompt("x", max_workers=4)[:20] in p for p in prompts)
