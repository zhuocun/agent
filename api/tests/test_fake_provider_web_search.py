"""Web-search path tests for the deterministic `FakeProvider`.

The fake powers dev / e2e / unit flows, so its web_search event order must
mirror the real provider's: reasoning → StatusUpdate(active) → StatusUpdate(done)
→ Sources → grounded answer (citing [1][2]) → usage → Complete. With
web_search=False the stream is byte-for-byte unchanged from the non-search path.
"""

from __future__ import annotations

import pytest

from app.providers.fake import FakeProvider
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ReasoningDelta,
    ReasoningDone,
    Sources,
    StatusUpdate,
    UsageUpdate,
)

pytestmark = pytest.mark.asyncio


def _fast_provider() -> FakeProvider:
    # No sleeps so the test polls cheaply.
    return FakeProvider(delay_ms=0)


async def test_fake_web_search_emits_status_sources_then_answer() -> None:
    """web_search=True -> Status(active)→Status(done)→Sources→answer deltas."""
    provider = _fast_provider()
    seq: list[str] = []
    statuses: list[StatusUpdate] = []
    sources: list[Sources] = []
    answer_parts: list[str] = []
    async for event in provider.stream(
        model_id="fake", history=[], user_text="what is rust", web_search=True
    ):
        if isinstance(event, ReasoningDelta):
            seq.append("reasoning")
        elif isinstance(event, ReasoningDone):
            seq.append("reasoning_done")
        elif isinstance(event, StatusUpdate):
            seq.append(f"status:{event.state}")
            statuses.append(event)
        elif isinstance(event, Sources):
            seq.append("sources")
            sources.append(event)
        elif isinstance(event, AnswerDelta):
            seq.append("answer")
            answer_parts.append(event.text)

    # Reasoning precedes the search, which precedes the answer.
    assert seq.index("reasoning_done") < seq.index("status:active")
    assert seq.index("status:active") < seq.index("status:done")
    assert seq.index("status:done") < seq.index("sources")
    assert seq.index("sources") < seq.index("answer")

    assert [s.state for s in statuses] == ["active", "done"]
    assert statuses[0].label == "Searching the web…"

    # Three deterministic sources, ids 1..3.
    assert len(sources) == 1
    assert [it.id for it in sources[0].items] == [1, 2, 3]

    # The grounded answer references the sources.
    assert "[1][2]" in "".join(answer_parts)


async def test_fake_web_search_is_deterministic() -> None:
    """Same input -> identical Sources across runs."""

    async def collect_sources() -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        async for event in _fast_provider().stream(
            model_id="fake", history=[], user_text="stable query", web_search=True
        ):
            if isinstance(event, Sources):
                items = [it.model_dump() for it in event.items]
        return items

    assert await collect_sources() == await collect_sources()


async def test_fake_web_search_false_emits_no_search_events() -> None:
    """web_search=False (default) -> no StatusUpdate / Sources; normal answer."""
    provider = _fast_provider()
    search_events = 0
    has_answer = False
    has_usage = False
    async for event in provider.stream(
        model_id="fake", history=[], user_text="hello", web_search=False
    ):
        if isinstance(event, (StatusUpdate, Sources)):
            search_events += 1
        elif isinstance(event, AnswerDelta):
            has_answer = True
        elif isinstance(event, UsageUpdate):
            has_usage = True

    assert search_events == 0
    assert has_answer
    assert has_usage


async def test_fake_web_search_false_matches_default_stream() -> None:
    """The web_search=False stream is identical to the no-arg stream (no-op invariant)."""

    async def collect(web_search: bool) -> list[str]:
        out: list[str] = []
        async for event in _fast_provider().stream(
            model_id="fake", history=[], user_text="hello", web_search=web_search
        ):
            if isinstance(event, AnswerDelta):
                out.append(f"answer:{event.text}")
            elif isinstance(event, Complete):
                out.append("complete")
            else:
                out.append(type(event).__name__)
        return out

    default = await collect(False)
    async def collect_default() -> list[str]:
        out: list[str] = []
        async for event in _fast_provider().stream(
            model_id="fake", history=[], user_text="hello"
        ):
            if isinstance(event, AnswerDelta):
                out.append(f"answer:{event.text}")
            elif isinstance(event, Complete):
                out.append("complete")
            else:
                out.append(type(event).__name__)
        return out

    assert default == await collect_default()
