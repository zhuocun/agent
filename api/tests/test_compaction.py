"""Context-window compaction tests (FR-35).

Covers the cheap token estimate, the `should_compact` budget gate, and the
`compact_history` behavior: no-op under budget, provider summary + sliding
window over budget, the pure sliding-window fallback when no provider is
available or the summary call fails, usage metering, cache hits, fit
guarantee when the recent window alone overflows, the two-watermark
hysteresis that keeps one compaction from re-tripping on the next turn, and
the prefix-anchored cut that keeps the boundary — and so the summary cache —
stable while the route re-projects and recompacts the whole history each turn.
"""

from __future__ import annotations

import hashlib
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


class _BoundaryEchoProvider(_SummaryProvider):
    """Summary text derived from the prompt, so it identifies the boundary.

    A fixed summary string would make "the same summary was emitted" true even
    when the cut moved. Deriving it from the transcript makes byte-identical
    summary text mean byte-identical summarized prefix.
    """

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
        digest = hashlib.sha256(user_text.encode("utf-8")).hexdigest()[:16]
        return CompleteResult(text=f"Earlier prefix {digest}.", usage=self.usage)


def _append_turn(history: list[ChatMessage], turn: int) -> list[ChatMessage]:
    """One user+assistant exchange appended, as the route's re-projection sees it."""
    return [
        *history,
        ChatMessage(role="user", text=f"q{turn} " + "x" * 195),
        ChatMessage(role="assistant", text=f"a{turn} " + "x" * 195),
    ]


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


# prefix-anchored cut ------------------------------------------------------------


async def test_reprojected_history_reuses_the_summary_across_turns() -> None:
    # The production shape. `routes/conversations.py` never persists a
    # compaction: it re-projects the entire conversation from the database and
    # compacts that projection for the provider call, on every turn. A cut
    # measured backwards from the newest message therefore moved forward every
    # turn, handed `_boundary_cache_key` a different prefix every turn, and
    # billed a summarizer call every turn — the low watermark alone bought
    # nothing here. Anchored to the leading prefix, the boundary only moves once
    # growth crosses a quantum.
    binding = _binding(context_window=20000, max_output_tokens=2000)
    provider = _BoundaryEchoProvider()
    compaction._summary_cache.clear()
    history = _history(300, text="x" * 200)
    assert should_compact(binding, history) is True

    turns = 80
    compacting = 0
    cache_hits = 0
    for turn in range(turns):
        history = _append_turn(history, turn)
        result = await compact_history(
            history, binding, provider=provider, model_id="model-x"
        )
        assert result.compacted is True
        compacting += 1
        cache_hits += 1 if result.cache_hit else 0

    # Every turn past the high watermark compacts — that is unchanged.
    assert compacting == turns
    # Each compacting turn either summarizes or reuses a cached summary.
    assert cache_hits == compacting - len(provider.calls)
    # One summarizer call per quantum of growth, not one per turn: the quantum
    # is half of a 8000-token target and a turn adds ~106 tokens, so a small
    # minority of turns pay for a summary.
    assert len(provider.calls) <= turns // 10
    assert cache_hits >= (turns * 9) // 10


async def test_boundary_is_stable_while_history_only_grows() -> None:
    # Within one quantum the emitted summary is byte-identical and the verbatim
    # tail only grows at its end: no message that was verbatim last turn has
    # been dropped or resummarized.
    binding = _binding(context_window=20000, max_output_tokens=2000)
    provider = _BoundaryEchoProvider()
    compaction._summary_cache.clear()
    history = _history(300, text="x" * 200)

    previous_summary: ChatMessage | None = None
    previous_tail: list[ChatMessage] = []
    for turn in range(6):
        history = _append_turn(history, turn)
        result = await compact_history(
            history, binding, provider=provider, model_id="model-x"
        )
        summary, tail = result.history[0], result.history[1:]
        if previous_summary is not None:
            assert result.cache_hit is True
            assert summary.text == previous_summary.text
            assert summary.role == previous_summary.role
            # Append-only: last turn's tail is a prefix of this turn's, and the
            # difference is exactly the exchange just appended.
            assert tail[: len(previous_tail)] == previous_tail
            assert tail[len(previous_tail) :] == history[-2:]
        previous_summary = summary
        previous_tail = tail

    # One summarizer call for the whole stable stretch.
    assert len(provider.calls) == 1


@pytest.mark.parametrize("quantum_fraction", [None, "1.0"])
async def test_cut_lands_under_the_low_watermark_every_turn(
    monkeypatch: pytest.MonkeyPatch,
    settings_cache_reset: None,
    quantum_fraction: str | None,
) -> None:
    # At the default and at the `le=1.0` bound (where the cut can overshoot far
    # enough to collapse the window onto the `_MIN_KEEP_RECENT` floor), the
    # history handed to the provider never exceeds the low watermark.
    if quantum_fraction is not None:
        monkeypatch.setenv("COMPACTION_CUT_QUANTUM_FRACTION", quantum_fraction)
    get_settings.cache_clear()
    expected = float(quantum_fraction) if quantum_fraction is not None else 0.5
    assert get_settings().compaction_cut_quantum_fraction == expected

    binding = _binding(context_window=20000, max_output_tokens=2000)
    target = compaction._target_budget(binding)
    compaction._summary_cache.clear()
    history = _history(300, text="x" * 200)

    for turn in range(80):
        history = _append_turn(history, turn)
        # The selection lands under the target on its own — `_fit_to_budget` is
        # a backstop, not the thing that makes the invariant true.
        assert estimate_tokens(compaction._select_recent(history, binding)) <= target
        result = await compact_history(
            history, binding, provider=_SummaryProvider(), model_id="model-x"
        )
        assert estimate_tokens(result.history) <= target


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
