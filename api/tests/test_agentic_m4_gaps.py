"""Agentic M4 gaps: per-worker provider fallback, provider-backed verifier,
depth enforcement, and agentic replay-buffer sizing.

These drive the orchestrator / verifier / replay store DIRECTLY (no HTTP) with
controllable stream factories, so the retry / cost-folding / guard branches are
exercised in isolation:

- WORKER FALLBACK (task 4): a worker hitting a retryable provider error
  (429/5xx) BEFORE emitting content retries once on the fallback route; with no
  fallback it degrades (run still finalizes).
- PROVIDER-BACKED VERIFIER (task 5): the fake backend keeps the deterministic,
  zero-cost stub; a real backend runs a bounded reviewer pass whose usage is
  returned for folding into the run totals.
- DEPTH ENFORCEMENT (task 7): `run_orchestrator` refuses to run when
  `agentic_max_depth < 1`.
- AGENTIC BUFFER SIZING (task 8): the Redis replay store honors per-log
  count/byte overrides; None falls back to the store defaults.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.agentic import verifier
from app.agentic.orchestrator import StreamFactory, run_orchestrator
from app.config import Settings
from app.errors import AppError, ErrorEnvelope
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    SubagentDone,
    ToolResult,
    UsageUpdate,
)
from app.streaming.replay_registry import RedisReplayLogBuffer, RedisReplayLogStore
from app.tools.agent_loop import MakeStream
from tests.test_stream_state import _FakeRedis

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


def _answer_factory(text: str, *, usage: UsageUpdate | None = None) -> StreamFactory:
    """A `StreamFactory` whose stream yields one answer delta + a `Complete`."""
    final_usage = usage if usage is not None else UsageUpdate()

    def _factory(_prompt: str) -> MakeStream:
        def _make(_tool_feedback: list[ToolResult]) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text=text)
                yield Complete(usage=final_usage)

            return _gen()

        return _make

    return _factory


def _raising_factory(exc: BaseException) -> StreamFactory:
    """A `StreamFactory` whose stream raises before emitting anything."""

    def _factory(_prompt: str) -> MakeStream:
        def _make(_tool_feedback: list[ToolResult]) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                raise exc
                yield  # pragma: no cover - unreachable; makes this an async gen

            return _gen()

        return _make

    return _factory


def _rate_limited() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="RATE_LIMITED",
            severity="warning",
            title="Rate limited",
            body="Upstream returned 429.",
        ),
        status_code=429,
    )


def _zero_cost(_usage: UsageUpdate) -> float:
    return 0.0


async def _collect(gen: AsyncIterator[ProviderEvent]) -> list[ProviderEvent]:
    return [event async for event in gen]


def _answer_text(events: list[ProviderEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, AnswerDelta))


# 1. Per-worker provider fallback (task 4) -------------------------------------


async def test_worker_retries_on_fallback_route() -> None:
    """A retryable worker error retries once on the fallback route and succeeds."""
    settings = Settings(provider_backend="fake")
    events = await _collect(
        run_orchestrator(
            make_stream_for=_answer_factory("unused-primary"),
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: only question",
            cost_for_usage=_zero_cost,
            make_worker_stream_for=_raising_factory(_rate_limited()),
            fallback_make_worker_stream_for=_answer_factory("FALLBACK FINDING"),
        )
    )

    # The worker recovered on the fallback route: its finding made it into the
    # run and the turn finalized (a final untagged `Complete` is always emitted).
    assert any(isinstance(e, Complete) and e.subagent_id is None for e in events)
    assert "FALLBACK FINDING" in _answer_text(events)
    # A recovered worker is NOT a failed worker — no partial-failure label.
    assert "sub-agents failed" not in _answer_text(events)


async def test_worker_degrades_without_fallback() -> None:
    """A retryable worker error with no fallback degrades; the run still finishes."""
    settings = Settings(provider_backend="fake")
    events = await _collect(
        run_orchestrator(
            make_stream_for=_answer_factory("unused-primary"),
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: only question",
            cost_for_usage=_zero_cost,
            make_worker_stream_for=_raising_factory(_rate_limited()),
            fallback_make_worker_stream_for=None,
        )
    )

    # The failed worker still closed its section (zero-cost `SubagentDone`) and
    # the run finalized with the stable "no findings" synthesis (1 of 1 failed).
    worker_done = [
        e for e in events if isinstance(e, SubagentDone) and e.role == "worker"
    ]
    assert len(worker_done) == 1
    assert worker_done[0].cost_usd == 0.0
    assert any(isinstance(e, Complete) and e.subagent_id is None for e in events)
    assert "no worker findings were produced" in _answer_text(events).lower()


async def test_worker_does_not_retry_non_retryable_error() -> None:
    """A NON-retryable worker error degrades immediately (no fallback attempt)."""
    settings = Settings(provider_backend="fake")
    fallback_calls: list[str] = []

    def _tracking_fallback(prompt: str) -> MakeStream:
        fallback_calls.append(prompt)
        return _answer_factory("SHOULD NOT RUN")(prompt)

    events = await _collect(
        run_orchestrator(
            make_stream_for=_answer_factory("unused-primary"),
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: only question",
            cost_for_usage=_zero_cost,
            make_worker_stream_for=_raising_factory(RuntimeError("boom")),
            fallback_make_worker_stream_for=_tracking_fallback,
        )
    )

    # A plain RuntimeError is not retryable, so the fallback factory is never
    # invoked and the worker degrades.
    assert fallback_calls == []
    assert "SHOULD NOT RUN" not in _answer_text(events)
    assert any(isinstance(e, Complete) and e.subagent_id is None for e in events)


# 2. Provider-backed verifier (task 5) -----------------------------------------


async def test_verify_streamed_fake_is_deterministic_zero_cost() -> None:
    """On the fake backend the verifier is the deterministic, zero-cost stub."""
    settings = Settings(provider_backend="fake")
    text, usage = await verifier.verify_streamed(
        make_stream_for=_answer_factory("reviewer output"),
        settings=settings,
        synthesis="the answer",
        n=3,
    )
    assert text == "the answer\n\n[Verified by 3-pass self-consistency review.]"
    # No provider call ⇒ no token cost.
    assert usage == UsageUpdate()


async def test_verify_streamed_real_runs_reviewer_pass_and_bills_usage() -> None:
    """On a real backend the verifier runs a bounded pass and returns its usage."""
    settings = Settings(provider_backend="deepseek", deepseek_api_key="ds")
    reviewer_usage = UsageUpdate(input_tokens=11, output_tokens=7)
    text, usage = await verifier.verify_streamed(
        make_stream_for=_answer_factory("looks consistent", usage=reviewer_usage),
        settings=settings,
        synthesis="the answer",
        n=4,
    )
    # The user-visible note is identical across backends (the verdict text is
    # discarded) but the reviewer pass's usage is returned for run-total folding.
    assert text == "the answer\n\n[Verified by 4-pass self-consistency review.]"
    assert usage == reviewer_usage


async def test_verifier_cost_folds_into_run_total() -> None:
    """A real-backend verifier's spend is folded into the run-total `Complete`."""
    settings = Settings(
        provider_backend="deepseek", deepseek_api_key="ds", AGENTIC_VERIFIER=True
    )
    assert settings.agentic_verifier is True
    reviewer_usage = UsageUpdate(input_tokens=5, output_tokens=3)

    # Single mode never verifies; use deep_research on a real backend so the
    # streamed synthesis path runs `_maybe_verify` (a real reviewer pass). The
    # aggregator + verifier both drive `make_stream_for`; count output tokens so
    # the verifier fold is observable on the run total.
    def _cost(usage: UsageUpdate) -> float:
        return float(usage.output_tokens)

    events = await _collect(
        run_orchestrator(
            make_stream_for=_answer_factory("review", usage=reviewer_usage),
            settings=settings,
            mode="deep_research",
            user_text="DEEP_RESEARCH: only question",
            cost_for_usage=_cost,
            make_worker_stream_for=_answer_factory("worker finding"),
        )
    )

    # The run-total usage (final untagged Complete) includes the verifier tokens.
    finals = [e for e in events if isinstance(e, Complete) and e.subagent_id is None]
    assert finals, "expected a final untagged Complete"
    assert finals[-1].usage.output_tokens >= reviewer_usage.output_tokens


# 3. Depth enforcement (task 7) ------------------------------------------------


async def test_run_orchestrator_rejects_depth_below_one() -> None:
    """`agentic_max_depth < 1` is refused at runtime (matching the boot guard)."""
    # Aliased settings are populated by their env alias (the model ignores
    # field-name kwargs), so set AGENTIC_MAX_DEPTH explicitly here.
    settings = Settings(provider_backend="fake", AGENTIC_MAX_DEPTH=0)
    assert settings.agentic_max_depth == 0
    with pytest.raises(ValueError, match="agentic_max_depth"):
        await _collect(
            run_orchestrator(
                make_stream_for=_answer_factory("hi"),
                settings=settings,
                mode="single",
                user_text="hello",
                cost_for_usage=_zero_cost,
            )
        )


# 4. Agentic replay-buffer sizing (task 8) -------------------------------------


async def test_redis_store_create_honors_buffer_overrides() -> None:
    """The Redis store applies per-log count/byte overrides; None ⇒ defaults."""
    store = RedisReplayLogStore(
        _FakeRedis(), max_events=1000, max_bytes=1_048_576, live_ttl_seconds=30.0
    )

    overridden = await store.create(
        uuid4(), ttl_seconds=60.0, max_events=5000, max_bytes=5_242_880
    )
    assert isinstance(overridden, RedisReplayLogBuffer)
    assert overridden._max_events == 5000
    assert overridden._max_bytes == 5_242_880

    default = await store.create(uuid4(), ttl_seconds=60.0)
    assert isinstance(default, RedisReplayLogBuffer)
    assert default._max_events == 1000
    assert default._max_bytes == 1_048_576
