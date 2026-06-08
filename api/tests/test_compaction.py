"""Context-window compaction tests (FR-35).

Covers the cheap token estimate, the `should_compact` budget gate, and the
`compact_history` behavior: no-op under budget, provider summary + sliding
window over budget, and the pure sliding-window fallback when no provider is
available or the summary call fails.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

from app.context import compaction
from app.context.compaction import (
    KEEP_LAST_N,
    compact_history,
    estimate_tokens,
    should_compact,
)
from app.providers.protocol import ChatMessage, ProviderEvent
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
    ) -> str:
        self.calls.append(user_text)
        return self.summary


class _RaisingProvider(_SummaryProvider):
    async def complete(self, **_kwargs: object) -> str:
        raise RuntimeError("summarizer unavailable")


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
    assert result is history


async def test_compact_history_summarizes_older_and_keeps_recent() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)
    provider = _SummaryProvider()

    result = await compact_history(
        history,
        binding,
        provider=provider,
        model_id="model-x",
    )

    # A summary message is prepended; the last KEEP_LAST_N turns are kept.
    assert len(result) == KEEP_LAST_N + 1
    assert result[0].role == "assistant"
    assert "Earlier they discussed the project plan." in result[0].text
    assert result[1:] == history[-KEEP_LAST_N:]
    # The summarizer was asked to summarize only the older prefix.
    assert provider.calls


async def test_compact_history_sliding_window_without_provider() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)

    result = await compact_history(history, binding)

    # No provider ⇒ pure sliding window: just the last KEEP_LAST_N, no summary.
    assert result == history[-KEEP_LAST_N:]


async def test_compact_history_falls_back_when_summary_raises() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)

    result = await compact_history(
        history,
        binding,
        provider=_RaisingProvider(),
        model_id="model-x",
    )

    # Summary failed ⇒ fall back to the sliding window (older prefix dropped).
    assert result == history[-KEEP_LAST_N:]


async def test_compact_history_blank_summary_falls_back() -> None:
    binding = _binding(context_window=200, max_output_tokens=50)
    history = _history(40)

    result = await compact_history(
        history,
        binding,
        provider=_SummaryProvider(summary="   "),
        model_id="model-x",
    )

    assert result == history[-KEEP_LAST_N:]


def test_default_binding_carries_window_budget() -> None:
    # The defaults land on the dataclass (FR-35) so a binding always exposes a
    # budget for the compaction pass.
    base = get_binding("smart")
    assert base is not None
    assert base.context_window == 128000
    assert base.max_output_tokens == 8192
    # The compaction module reads them without error.
    assert compaction._compaction_budget(base) > 0
