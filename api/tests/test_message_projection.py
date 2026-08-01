"""AC-05 closure: the durable-part projection boundary.

`app.messages.projection` is the single owner of what a persisted message part
means, so these are pure unit tests over part lists — no DB, no HTTP, no clock.
Two behaviors are load-bearing and each has its own section below:

1. Provider history keeps planner/worker prose OUT of the manager's answer.
2. Idempotency replay is a CANONICAL SEMANTIC replay of the stored row, not a
   fake re-run of the original stream: durable fields replay, absent ones are
   omitted rather than invented, and a flat non-agentic row still produces the
   frame sequence clients have always seen.

The repo-level and route-level halves of AC-05 are covered where those consumers
live (`test_messages_repo.py`, `test_messages_stream.py`).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sse_starlette import ServerSentEvent

from app.messages.projection import (
    parts_to_provider_history,
    parts_to_semantic_replay,
)

_USER_ID = uuid4()
_ASSISTANT_ID = uuid4()


def _attribution(label: str = "Fake", tier_id: str = "smart") -> dict[str, Any]:
    return {
        "requestedTierId": tier_id,
        "servedTierId": tier_id,
        "servedModelLabel": label,
        "providerId": "fake",
        "providerLabel": "Fake",
        "isByok": False,
        "costUsd": 0.0,
        "costConfidence": "exact",
        "breakdown": {
            "currency": "USD",
            "listPriceInPerM": 0.14,
            "listPriceOutPerM": 0.28,
            "inputTokens": 10,
            "outputTokens": 20,
            "reasoningTokens": 0,
            "cachedInputTokens": 0,
            "longContext": {"flat": True},
            "promoApplied": False,
            "subtotalUsd": 0.0,
            "sessionSurchargeUsd": 0.0,
        },
    }


def _frames(
    parts: object,
    attribution: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Replay a row as `(event_name, decoded_payload)` pairs.

    Decoding the encoder's own JSON (rather than asserting on typed events) is
    what the SSE tests assert against, so a drift between the projection and the
    wire shape shows up here too.
    """
    encoded = parts_to_semantic_replay(
        parts,
        attribution if attribution is not None else _attribution(),
        user_message_id=_USER_ID,
        assistant_message_id=_ASSISTANT_ID,
    )
    out: list[tuple[str, dict[str, Any]]] = []
    for frame in encoded:
        assert isinstance(frame, ServerSentEvent)
        assert isinstance(frame.event, str)
        assert isinstance(frame.data, str)
        out.append((frame.event, json.loads(frame.data)))
    return out


def _names(parts: object, attribution: dict[str, Any] | None = None) -> list[str]:
    return [name for name, _ in _frames(parts, attribution)]


def _payload(
    frames: list[tuple[str, dict[str, Any]]], event: str, index: int = 0
) -> dict[str, Any]:
    matching = [payload for name, payload in frames if name == event]
    assert len(matching) > index, f"missing {event}[{index}] in {[n for n, _ in frames]}"
    return matching[index]


# A deep-research row as the orchestrator persists one: an untagged preamble, a
# planner section, two worker sections (one failed), and the aggregator whose
# prose IS the manager's answer. Reused so the history and replay assertions are
# reading the exact same durable row.
def _deep_research_parts() -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": "Untagged preamble. "},
        {
            "type": "subagent",
            "subagentId": "planner",
            "label": "Planner",
            "role": "orchestrator",
            "outcome": "succeeded",
        },
        {"type": "text", "text": "PLAN: split into two lookups.", "subagentId": "planner"},
        {
            "type": "subagent",
            "subagentId": "worker-1",
            "label": "Rust history",
            "role": "worker",
            "outcome": "succeeded",
            "costUsd": 0.002,
            "attribution": _attribution("Worker Model"),
        },
        {"type": "reasoning", "text": "Worker 1 thinking.", "subagentId": "worker-1"},
        {
            "type": "tool_call",
            "id": "call-1",
            "name": "web_search",
            "status": "succeeded",
            "input": {"query": "rust history", "_agenticContinuation": "SECRET"},
            "subagentId": "worker-1",
        },
        {
            "type": "tool_result",
            "toolCallId": "call-1",
            "name": "web_search",
            "status": "succeeded",
            "output": {"hits": 3, "actualCostUsd": 0.5},
            "subagentId": "worker-1",
        },
        {
            "type": "sources",
            "items": [{"id": 1, "title": "Rust", "url": "https://example.com/rust"}],
            "requested": True,
            "subagentId": "worker-1",
        },
        {"type": "text", "text": "Worker 1 finding.", "subagentId": "worker-1"},
        {
            "type": "subagent",
            "subagentId": "worker-2",
            "label": "Rust adoption",
            "role": "worker",
            "outcome": "failed",
        },
        {"type": "text", "text": "Worker 2 partial note.", "subagentId": "worker-2"},
        {
            "type": "subagent",
            "subagentId": "aggregator",
            "label": "Synthesis",
            "role": "aggregator",
            "outcome": "succeeded",
            "costUsd": 0.004,
        },
        {"type": "text", "text": "Rust began in 2006.", "subagentId": "aggregator"},
        {
            "type": "agentic_run_summary",
            "outcome": "partial",
            "budgetHalted": True,
            "failedWorkers": 1,
            "subtotalUsd": 0.006,
            "capUsd": 0.05,
            "costConfidence": "exact",
            "costPhase": "final",
        },
    ]


# -- provider history ----------------------------------------------------------


def test_flat_row_projects_text_and_reasoning_unchanged() -> None:
    """The non-agentic case is the old flattening, so history is unchanged."""
    projected = parts_to_provider_history(
        [
            {"type": "reasoning", "text": "thinking "},
            {"type": "reasoning", "text": "more"},
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
            {"type": "attachment", "id": "a1", "name": "f.png"},
        ],
        role="assistant",
    )
    assert projected is not None
    assert projected.role == "assistant"
    assert projected.text == "hello world"
    assert projected.reasoning_content == "thinking more"


def test_deep_research_history_is_manager_answer_only() -> None:
    """AC-05: the provider sees the aggregator's synthesis and the untagged
    preamble. Planner prose, worker findings and worker reasoning are working
    material — promoting them would tell the model it had said things it never
    said, and would leak one worker's scratch notes into every later turn."""
    projected = parts_to_provider_history(_deep_research_parts(), role="assistant")
    assert projected is not None
    assert projected.text == "Untagged preamble. Rust began in 2006."
    # Worker reasoning is tagged, so it is not the manager's reasoning either.
    assert projected.reasoning_content is None


def test_primary_scope_is_manager_owned() -> None:
    """A single-agent agentic turn tags everything `primary`; that IS the answer."""
    projected = parts_to_provider_history(
        [
            {"type": "subagent", "subagentId": "primary", "label": "Agent", "role": "primary"},
            {"type": "reasoning", "text": "deliberating", "subagentId": "primary"},
            {"type": "text", "text": "The answer.", "subagentId": "primary"},
        ],
        role="assistant",
    )
    assert projected is not None
    assert projected.text == "The answer."
    assert projected.reasoning_content == "deliberating"


def test_worker_only_row_projects_to_nothing() -> None:
    """A row whose only prose is a worker's gives the provider nothing to
    consume, so it drops out of history entirely rather than contributing an
    empty (or worse, worker-authored) assistant turn."""
    assert (
        parts_to_provider_history(
            [
                {"type": "subagent", "subagentId": "worker-1", "label": "W", "role": "worker"},
                {"type": "text", "text": "Worker finding.", "subagentId": "worker-1"},
            ],
            role="assistant",
        )
        is None
    )


def test_tagged_content_without_a_marker_is_not_manager_owned() -> None:
    """Ownership comes from the stored `subagent` marker's role. With no marker
    the tag cannot be resolved to a manager scope, so the safe read is that the
    content belongs to somebody else's section."""
    assert (
        parts_to_provider_history(
            [{"type": "text", "text": "orphan", "subagentId": "worker-9"}],
            role="assistant",
        )
        is None
    )


@pytest.mark.parametrize("role", ["system", "tool", ""])
def test_non_chat_roles_project_to_nothing(role: str) -> None:
    assert parts_to_provider_history([{"type": "text", "text": "x"}], role=role) is None


@pytest.mark.parametrize("parts", [None, "not-a-list", 7, [], [None, "junk", 3]])
def test_unreadable_parts_column_projects_to_nothing(parts: object) -> None:
    """`parts` is a nullable JSON column; a NULL or hand-seeded row must not 500."""
    assert parts_to_provider_history(parts, role="assistant") is None


# -- canonical semantic replay -------------------------------------------------


def test_flat_replay_sequence_is_unchanged() -> None:
    """Sequence compatibility: a flat grounded turn replays exactly the frame
    order clients already handle — reasoning, tools, status, answer, sources."""
    assert _names(
        [
            {"type": "reasoning", "text": "thinking"},
            {
                "type": "tool_call",
                "id": "c1",
                "name": "web_search",
                "status": "succeeded",
                "input": {"query": "rust"},
            },
            {
                "type": "tool_result",
                "toolCallId": "c1",
                "name": "web_search",
                "status": "succeeded",
            },
            {"type": "status", "label": "Searched the web", "state": "done"},
            {"type": "text", "text": "Rust is a language."},
            {
                "type": "sources",
                "items": [{"id": 1, "title": "Rust", "url": "https://example.com"}],
                "requested": True,
            },
        ]
    ) == [
        "submitted",
        "reasoning_delta",
        "reasoning_done",
        "tool_call",
        "tool_result",
        "status",
        "answer_delta",
        "sources",
        "terminal",
    ]


def test_bare_flat_replay_still_emits_its_answer_frame() -> None:
    """A text-only row keeps the minimal submitted/answer/terminal sequence, and
    an untagged answer frame is emitted even when the stored text is empty —
    that is the flat wire contract, not an invented frame."""
    assert _names([{"type": "text", "text": "hi"}]) == [
        "submitted",
        "answer_delta",
        "terminal",
    ]
    assert _names([]) == ["submitted", "answer_delta", "terminal"]


def test_deep_research_replay_is_deterministic_tagged_sections() -> None:
    """The canonical replay: sections in stored order, each opened by its durable
    `subagent_started` and closed by `subagent_done`, then the persisted run
    receipt and the stored terminal attribution."""
    parts = _deep_research_parts()
    frames = _frames(parts)
    assert [name for name, _ in frames] == [
        "submitted",
        # Untagged preamble owns no marker, so it emits no lifecycle frames.
        "answer_delta",
        "subagent_started",
        "answer_delta",
        "subagent_done",
        "subagent_started",
        "reasoning_delta",
        "reasoning_done",
        "tool_call",
        "tool_result",
        "sources",
        "answer_delta",
        "subagent_done",
        "subagent_started",
        "answer_delta",
        "subagent_done",
        "subagent_started",
        "answer_delta",
        "subagent_done",
        "run_cost",
        "terminal",
    ]
    # Deterministic: the same row always projects to the same frames.
    assert _frames(parts) == frames

    starts = [p["subagentId"] for n, p in frames if n == "subagent_started"]
    assert starts == ["planner", "worker-1", "worker-2", "aggregator"]
    # Lifecycle order per section: Started < its tagged content < Done.
    names = [name for name, _ in frames]
    for scope in starts:
        section = [
            i
            for i, (name, payload) in enumerate(frames)
            if payload.get("subagentId") == scope
        ]
        assert names[section[0]] == "subagent_started"
        assert names[section[-1]] == "subagent_done"
    # Every worker/planner answer stays inside its own tagged frame; only the
    # untagged preamble replays without a scope.
    answers = [(p.get("subagentId"), p["text"]) for n, p in frames if n == "answer_delta"]
    assert answers == [
        (None, "Untagged preamble. "),
        ("planner", "PLAN: split into two lookups."),
        ("worker-1", "Worker 1 finding."),
        ("worker-2", "Worker 2 partial note."),
        ("aggregator", "Rust began in 2006."),
    ]


def test_replay_carries_durable_subagent_outcomes_and_attribution() -> None:
    frames = _frames(_deep_research_parts())
    done = {p["subagentId"]: p for n, p in frames if n == "subagent_done"}
    assert done["worker-1"]["outcome"] == "succeeded"
    assert done["worker-1"]["costUsd"] == 0.002
    assert done["worker-1"]["role"] == "worker"
    assert done["worker-1"]["attribution"]["servedModelLabel"] == "Worker Model"
    # A failed worker replays as failed, not as a green check.
    assert done["worker-2"]["outcome"] == "failed"
    assert done["aggregator"]["costUsd"] == 0.004


def test_replay_projects_the_persisted_run_receipt() -> None:
    """The stored `agentic_run_summary` is the receipt authority on reload, so the
    replayed meter matches the live one instead of defaulting to zero."""
    frames = _frames(_deep_research_parts())
    receipt = _payload(frames, "run_cost")
    assert receipt == {
        "subtotalUsd": 0.006,
        "capUsd": 0.05,
        "confidence": "exact",
        "phase": "final",
        "partial": True,
        "budgetHalted": True,
        "failedWorkerCount": 1,
    }
    # Exactly one receipt, and it precedes the terminal.
    names = [name for name, _ in frames]
    assert names.count("run_cost") == 1
    assert names.index("run_cost") < names.index("terminal")


def test_replay_terminal_carries_the_stored_attribution() -> None:
    attribution = _attribution("Stored Label", tier_id="pro")
    frames = _frames([{"type": "text", "text": "x"}], attribution)
    terminal = _payload(frames, "terminal")
    assert terminal["messageId"] == str(_ASSISTANT_ID)
    assert terminal["attribution"]["servedModelLabel"] == "Stored Label"
    assert terminal["attribution"]["servedTierId"] == "pro"
    assert _payload(frames, "submitted")["messageId"] == str(_USER_ID)


def test_replay_rejects_an_unusable_attribution() -> None:
    """A done row with a NULL/garbage attribution has no terminal to project.
    Raising lets the route fall through to a fresh turn instead of replaying a
    fabricated one."""
    with pytest.raises(ValidationError):
        parts_to_semantic_replay(
            [{"type": "text", "text": "x"}],
            {},
            user_message_id=_USER_ID,
            assistant_message_id=_ASSISTANT_ID,
        )


def test_replay_strips_reserved_control_keys_from_the_transcript() -> None:
    """H-012 at the boundary: neither consumer can forget to sanitize, because
    the projection does it for both."""
    blob = json.dumps(_frames(_deep_research_parts()))
    assert "_agenticContinuation" not in blob
    assert "actualCostUsd" not in blob
    assert "SECRET" not in blob
    # The non-reserved payload survives the strip.
    assert _payload(_frames(_deep_research_parts()), "tool_call")["input"] == {
        "query": "rust history"
    }


def test_replay_groups_a_marker_stored_after_its_content() -> None:
    """Sections are keyed on `subagentId`, not on position, so a row written with
    the marker trailing its content still replays as one bounded section."""
    assert _names(
        [
            {"type": "text", "text": "finding", "subagentId": "worker-1"},
            {
                "type": "subagent",
                "subagentId": "worker-1",
                "label": "W",
                "role": "worker",
            },
        ]
    ) == ["submitted", "subagent_started", "answer_delta", "subagent_done", "terminal"]


def test_replay_keeps_the_ungrounded_sources_marker() -> None:
    """An empty `items` with `requested=True` is the honest "answered without
    live sources" state, so it replays; a never-requested empty part does not."""
    assert "sources" in _names(
        [{"type": "text", "text": "a"}, {"type": "sources", "items": [], "requested": True}]
    )
    assert "sources" not in _names(
        [{"type": "text", "text": "a"}, {"type": "sources", "items": [], "requested": False}]
    )


def test_replay_follows_the_stored_answer_and_sources_order() -> None:
    """A flat turn stores [text][sources] and an agentic section [sources][text].
    Replay follows the row instead of reshuffling one of them into the other."""
    sources = {
        "items": [{"id": 1, "title": "T", "url": "https://example.com"}],
        "requested": True,
        "type": "sources",
    }
    marker = {"type": "subagent", "subagentId": "w", "label": "W", "role": "worker"}
    assert _names([{"type": "text", "text": "a"}, sources]) == [
        "submitted",
        "answer_delta",
        "sources",
        "terminal",
    ]
    tagged_sources_first = [
        marker,
        {**sources, "subagentId": "w"},
        {"type": "text", "text": "a", "subagentId": "w"},
    ]
    assert _names(tagged_sources_first) == [
        "submitted",
        "subagent_started",
        "sources",
        "answer_delta",
        "subagent_done",
        "terminal",
    ]


# -- non-durable fields are omitted, never fabricated --------------------------


def test_replay_omits_substitution_detail_that_was_never_stored() -> None:
    """The marker stores a reason code inside its attribution but never the
    substituted provider/model/label triple the live event carried. Replay
    forwards the code and leaves the rest absent rather than guessing."""
    attribution = _attribution("Fallback Model")
    attribution["substitution"] = {
        "reasonCode": "auto_downgrade",
        "reasonText": "Routed to a faster tier.",
    }
    done = _payload(
        _frames(
            [
                {
                    "type": "subagent",
                    "subagentId": "worker-1",
                    "label": "W",
                    "role": "worker",
                    "attribution": attribution,
                },
                {"type": "text", "text": "finding", "subagentId": "worker-1"},
            ]
        ),
        "subagent_done",
    )
    assert done["substitution"] == "auto_downgrade"
    assert "substitutedProvider" not in done
    assert "substitutedModel" not in done
    assert "substitutedDisplayLabel" not in done


def test_replay_omits_a_receipt_the_row_never_carried() -> None:
    """Rows predating AR-012 persist a summary with no cost scalars. A missing
    receipt replays as no `run_cost` at all, never as a confident $0.00."""
    legacy = {
        "type": "agentic_run_summary",
        "outcome": "partial",
        "budgetHalted": False,
        "failedWorkers": 2,
    }
    assert "run_cost" not in _names([{"type": "text", "text": "a"}, legacy])
    # Half a receipt is still not a receipt.
    assert "run_cost" not in _names(
        [{"type": "text", "text": "a"}, {**legacy, "subtotalUsd": 0.01}]
    )


def test_replay_omits_lifecycle_for_an_unreadable_marker() -> None:
    """A marker missing its required `label`/`role` cannot open a section
    honestly, so its content replays tagged while the lifecycle stays absent."""
    frames = _frames(
        [
            {"type": "subagent", "subagentId": "worker-1"},
            {"type": "text", "text": "finding", "subagentId": "worker-1"},
        ]
    )
    assert [name for name, _ in frames] == ["submitted", "answer_delta", "terminal"]
    assert _payload(frames, "answer_delta")["subagentId"] == "worker-1"


def test_replay_does_not_fabricate_chunking_or_progress() -> None:
    """Chunk boundaries, interleaving and progress ticks were never persisted.
    Each section replays as ONE answer frame, and no progress-only frame appears
    — exact buffered replay stays `ReplayLogBuffer`'s contract."""
    names = _names(
        [
            {"type": "subagent", "subagentId": "primary", "label": "A", "role": "primary"},
            {"type": "text", "text": "one ", "subagentId": "primary"},
            {"type": "text", "text": "two ", "subagentId": "primary"},
            {"type": "text", "text": "three", "subagentId": "primary"},
        ]
    )
    assert names.count("answer_delta") == 1
    assert names.count("reasoning_delta") == 0
    assert "progress" not in names
    frames = _frames(
        [
            {"type": "subagent", "subagentId": "primary", "label": "A", "role": "primary"},
            {"type": "text", "text": "one ", "subagentId": "primary"},
            {"type": "text", "text": "two", "subagentId": "primary"},
        ]
    )
    assert _payload(frames, "answer_delta")["text"] == "one two"


def test_replay_tolerates_an_unreadable_parts_column() -> None:
    for parts in (None, "not-a-list", [None, "junk"]):
        assert _names(parts) == ["submitted", "answer_delta", "terminal"]
