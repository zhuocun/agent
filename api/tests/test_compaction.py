"""Context-window compaction tests (FR-35).

Covers the cheap token estimate, the `should_compact` budget gate, and the
`compact_history` behavior: no-op under budget, provider summary + sliding
window over budget, the pure sliding-window fallback when no provider is
available or the summary call fails, usage metering, cache hits, fit
guarantee when the recent window alone overflows, and the two-watermark
hysteresis that keeps one compaction from re-tripping on the next turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace

import pytest

from app.config import get_settings
from app.context import compaction
from app.context.compaction import (
    _MIN_KEEP_RECENT,
    compact_history,
    estimate_tokens,
    should_compact,
)
from app.providers.protocol import ChatMessage, CompleteResult, ProviderEvent, UsageUpdate
from app.providers.tiers import get_binding


def _binding(*, context_window: int = 128000, max_output_tokens: int = 8192):
    """A concrete `smart` binding with overridable window/output budgets."""
    base = get_binding("smart")
    assert base is not None
    return replace(
        base,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )


def _history(n: int, *, text: str = "hello there friend") -> list[ChatMessage]:
    return [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", text=text)
        for i in range(n)
    ]


class _SummaryProvider:
    """Minimal provider whose `complete` returns a fixed summary string."""

    def __init__(self, summary: str = "Earlier they discussed the project plan.") -> None:
        self.summary = summary
        self.calls: list[str] = []
        self.usage = UsageUpdate(input_tokens=11, output_tokens=7)

    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:  # pragma: no cover
        raise NotImplementedError

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
        system_prefix: str | None = None,
    ) -> CompleteResult:
        self.calls.append(user_text)
        return CompleteResult(text=self.summary, usage=self.usage)


class _RaisingProvider(_SummaryProvider):
    async def complete(self, **_kwargs: object) -> CompleteResult:
        raise RuntimeError("summarizer unavailable")


@pytest.fixture
def settings_cache_reset() -> Iterator[None]:
    """Settings are `@lru_cache`d — bust the cache around env overrides."""
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


# estimate_tokens ---------------------------------------------------------------


def test_estimate_tokens_grows_with_history() -> None:
    short = _history(2)
    long = _history(20)
    assert estimate_tokens(short) < estimate_tokens(long)


def test_estimate_tokens_empty_is_zero() -> None:
    assert estimate_tokens([]) == 0


# should_compact ----------------------------------------------------------------


def test_should_not_compact_short_history() -> None:
    # A handful of small turns is nowhere near a 128k window — the common path.
    assert should_compact(_binding(), _history(4)) is False


def test_should_compact_when_history_exceeds_budget() -> None:
    # Tiny window so a modest history blows the budget.
    binding = _binding(context_window=200, max_output_tokens=50)
    assert should_compact(binding, _history(40)) is True


# compact_history ---------------------------------------------------------------


async def test_compact_history_noop_under_budget() -> None:
    history = _history(4)
    result = await compact_history(history, _binding())
    assert result.history is history
    assert result.usage is None
    assert result.compacted is False


async def test_compact_history_summarizes_older_and_keeps_recent() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)
    provider = _SummaryProvider()
    compaction._summary_cache.clear()

    result = await compact_history(
        history,
        binding,
        provider=provider,
        model_id="model-x",
    )

    # A summary message is prepended; the newest turns that fit under the low
    # watermark are kept verbatim.
    assert result.compacted is True
    assert result.usage == provider.usage
    assert result.history[0].role == "assistant"
    assert "Earlier they discussed the project plan." in result.history[0].text
    # Fitted result must aim to fit the budget.
    assert estimate_tokens(result.history) <= compaction._compaction_budget(binding)
    assert provider.calls[0].startswith(compaction._SUMMARY_PROMPT)


async def test_compact_history_sliding_window_without_provider() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)

    result = await compact_history(history, binding)

    # No provider ⇒ pure sliding window, then fit-to-budget.
    assert result.compacted is True
    assert result.usage is None
    assert estimate_tokens(result.history) <= compaction._target_budget(binding)
    assert len(result.history) < len(history)


async def test_compact_history_falls_back_when_summary_raises() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)
    compaction._summary_cache.clear()

    result = await compact_history(
        history,
        binding,
        provider=_RaisingProvider(),
        model_id="model-x",
    )

    assert result.compacted is True
    assert estimate_tokens(result.history) <= compaction._compaction_budget(binding)


async def test_compact_history_blank_summary_falls_back() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)
    compaction._summary_cache.clear()

    result = await compact_history(
        history,
        binding,
        provider=_SummaryProvider(summary="   "),
        model_id="model-x",
    )

    assert result.compacted is True
    assert estimate_tokens(result.history) <= compaction._compaction_budget(binding)


async def test_compact_history_caches_summary_by_boundary() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)
    provider = _SummaryProvider()
    compaction._summary_cache.clear()

    first = await compact_history(
        history, binding, provider=provider, model_id="model-x"
    )
    second = await compact_history(
        history, binding, provider=provider, model_id="model-x"
    )

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert len(provider.calls) == 1
    assert first.history[0].text == second.history[0].text


async def test_compact_history_fits_when_recent_alone_overflows() -> None:
    # Tiny budget where even KEEP_LAST_N short messages overflow; no older
    # prefix to summarize — must truncate rather than pass-through.
    binding = _binding(context_window=40, max_output_tokens=20)
    history = _history(8, text="x" * 200)
    assert should_compact(binding, history) is True

    result = await compact_history(history, binding)
    assert result.compacted is True
    assert estimate_tokens(result.history) <= compaction._compaction_budget(binding)


# low watermark / hysteresis -----------------------------------------------------


async def test_compaction_buys_headroom_for_the_next_turn() -> None:
    # Recent turns each cost a sizeable share of the budget — the shape that
    # made compact-to-the-threshold re-trip (and re-bill a summarizer call, with
    # a fresh prefix boundary) on every subsequent turn.
    binding = _binding(context_window=2000, max_output_tokens=500)
    history = _history(20, text="x" * 1000)
    compaction._summary_cache.clear()
    assert should_compact(binding, history) is True

    result = await compact_history(
        history, binding, provider=_SummaryProvider(), model_id="model-x"
    )

    assert result.compacted is True
    next_turn = [*result.history, ChatMessage(role="user", text="x" * 1000)]
    assert should_compact(binding, next_turn) is False


async def test_compacted_history_lands_under_the_low_watermark(
    monkeypatch: pytest.MonkeyPatch, settings_cache_reset: None
) -> None:
    monkeypatch.setenv("COMPACTION_TARGET_FRACTION", "0.25")
    get_settings.cache_clear()
    binding = _binding(context_window=2000, max_output_tokens=500)
    history = _history(40, text="x" * 200)
    compaction._summary_cache.clear()
    assert should_compact(binding, history) is True

    result = await compact_history(
        history, binding, provider=_SummaryProvider(), model_id="model-x"
    )

    target = compaction._target_budget(binding)
    assert target == int(compaction._compaction_budget(binding) * 0.25)
    assert estimate_tokens(result.history) <= target


def test_recent_window_keeps_the_immediate_exchange() -> None:
    # A target so small that not even one message fits: the floor still admits
    # the last exchange, leaving the fit-to-budget backstop to truncate it.
    binding = _binding(context_window=100, max_output_tokens=50)
    history = _history(8, text="x" * 400)
    assert compaction._target_budget(binding) < estimate_tokens(history[-1:])

    recent = compaction._select_recent(history, binding)

    assert recent == history[-_MIN_KEEP_RECENT:]


def test_summary_prompt_carries_the_preservation_contract() -> None:
    prompt = compaction._SUMMARY_PROMPT.lower()
    for term in (
        "objective",
        "constraints",
        "decisions",
        "rationale",
        "open questions",
        "todos",
        "evidence",
        "pointers",
        "pleasantries",
    ):
        assert term in prompt


def test_default_binding_carries_window_budget() -> None:
    # The defaults land on the dataclass (FR-35) so a binding always exposes a
    # budget for the compaction pass.
    base = get_binding("smart")
    assert base is not None
    assert base.context_window == 128000
    assert base.max_output_tokens == 8192
    # The compaction module reads them without error.
    assert compaction._compaction_budget(base) > 0
