"""Batch B unit tests: O-010..O-014 orchestrator residuals."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.agentic.aggregate import (
    WorkerOutput,
    build_artifacts,
    build_synthesis_prompt,
    omitted_artifact_count,
)
from app.agentic.clarify import (
    MAX_CLARIFY_ANSWER_CHARS,
    MAX_CLARIFY_ANSWERS_AGGREGATE_CHARS,
    MAX_CLARIFY_BLOCK_CHARS_WORKER,
    ClarificationRecord,
    clarification_amplified_chars,
    clarification_extra_input_tokens,
    clarification_payload_for_phase,
    format_clarification_data,
    synthesis_clarification_encoded_chars,
    with_clarifications,
)
from app.agentic.continuation import parse_continuation
from app.agentic.orchestrator import (
    _AGGREGATOR_ALLOWED_TOOLS,
    _WORKER_ALLOWED_TOOLS,
    _WORKER_FAKE_HITL_TOOLS,
    _WORKER_PROD_HITL_TOOLS,
    _finalize_synthesis_streamed,
)
from app.config import MAX_WORKER_ARTIFACTS, Settings
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    ToolResult,
    UsageUpdate,
)
from app.tools.builtin import TOOL_REGISTRY, advertised_tool_specs, execute_tool
from app.tools.protocol import ToolCallRequest


def test_o010_worker_allowlist_splits_prod_and_fake_hitl() -> None:
    """O-010: real workers can receive a prod_safe gated tool; calendar is fake-only."""
    assert "request_user_confirmation" in _WORKER_PROD_HITL_TOOLS
    assert "calendar_create_event" in _WORKER_FAKE_HITL_TOOLS
    assert _WORKER_ALLOWED_TOOLS == _WORKER_PROD_HITL_TOOLS | _WORKER_FAKE_HITL_TOOLS

    conf = TOOL_REGISTRY["request_user_confirmation"]
    cal = TOOL_REGISTRY["calendar_create_event"]
    assert conf.prod_safe is True
    assert conf.needs_approval is True
    assert cal.prod_safe is False
    assert cal.needs_approval is True

    advertised = {s.name for s in advertised_tool_specs(allowed_names=_WORKER_ALLOWED_TOOLS)}
    assert advertised == {"request_user_confirmation"}
    assert "calendar_create_event" not in advertised


@pytest.mark.asyncio
async def test_o010_request_user_confirmation_executes_when_approved() -> None:
    result = await execute_tool(
        ToolCallRequest(
            id="c1",
            name="request_user_confirmation",
            input={"prompt": "Confirm research scope?"},
            approval_state="approved",
        )
    )
    assert result.status == "succeeded"
    assert result.output.get("confirmed") is True
    assert result.output.get("prompt") == "Confirm research scope?"


def test_o011_aggregator_tools_forbidden_and_unsupported_phases_rejected() -> None:
    """O-011 / H-011: empty aggregator allowlist; no aggregator continuation phase."""
    assert frozenset() == _AGGREGATOR_ALLOWED_TOOLS
    assert parse_continuation({"phase": "aggregator", "pausedSubagentId": "a"}) is None
    assert parse_continuation({"phase": "primary", "pausedSubagentId": "p"}) is None
    assert (
        parse_continuation(
            {
                "phase": "worker",
                "pausedSubagentId": "worker-0",
                "userText": "q",
                "plan": ["a"],
            }
        )
        is not None
    )


@pytest.mark.asyncio
async def test_o011_aggregator_stream_factory_always_empty_allowlist() -> None:
    """O-011: streamed aggregator always gets empty tools + web_search=False."""
    seen: list[dict[str, object]] = []

    def _make_stream_for(prompt: str, **kwargs: object):
        seen.append(
            {
                "allowed_tools": kwargs.get("allowed_tools"),
                "web_search": kwargs.get("web_search"),
            }
        )

        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="synth")
                yield Complete(usage=UsageUpdate(input_tokens=1, output_tokens=1))

            return _gen()

        return _make

    settings = Settings(  # type: ignore[call-arg]
        PROVIDER_BACKEND="openai",
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
        AGENTIC_MAX_WORKERS=2,
        AGENTIC_VERIFIER=False,
        OPENAI_API_KEY="sk-test",
    )
    outputs = [
        WorkerOutput(subagent_id="worker-0", sub_question="q", answer="a"),
    ]
    _ = [
        ev
        async for ev in _finalize_synthesis_streamed(
            make_stream_for=_make_stream_for,
            settings=settings,
            user_text="original",
            outputs=outputs,
            planned=1,
            worker_usages=[UsageUpdate(input_tokens=1)],
            worker_total_cost=0.01,
            cost_for_usage=lambda u: 0.01,
            cap_usd=1.0,
            budget_halted=False,
            scaffolded=False,
        )
    ]
    assert seen
    assert all(s["allowed_tools"] == frozenset() for s in seen)
    assert all(s["web_search"] is False for s in seen)


def test_o013_artifact_cap_aligned_with_max_workers_constant() -> None:
    """O-013: artifact ceiling is public and truncates with an omitted count."""
    assert MAX_WORKER_ARTIFACTS == 16
    outputs = [
        WorkerOutput(subagent_id=f"w-{i}", sub_question=f"q{i}", answer=f"a{i}")
        for i in range(20)
    ]
    arts = build_artifacts(outputs)
    assert len(arts) == MAX_WORKER_ARTIFACTS
    assert omitted_artifact_count(outputs) == 4
    arts_capped = build_artifacts(outputs, max_artifacts=4)
    assert len(arts_capped) == 4
    assert omitted_artifact_count(outputs, max_artifacts=4) == 16


def test_o013_settings_rejects_max_workers_above_artifact_ceiling() -> None:
    settings = Settings(  # type: ignore[call-arg]
        AGENTIC_MAX_WORKERS=MAX_WORKER_ARTIFACTS + 1,
        AGENTIC_ENABLED=True,
        TOOLS_ENABLED=True,
    )
    with pytest.raises(RuntimeError, match="AGENTIC_MAX_WORKERS"):
        settings.assert_prod_safe()


def test_o014_clarify_phase_caps_limit_worker_amplification() -> None:
    """O-014: worker phase attaches a tighter block than planner/synthesis."""
    records = [
        ClarificationRecord(
            question_id="0",
            question="Q1",
            answer="A" * MAX_CLARIFY_ANSWER_CHARS,
        ),
        ClarificationRecord(
            question_id="1",
            question="Q2",
            answer="B" * MAX_CLARIFY_ANSWER_CHARS,
        ),
    ]
    # Aggregate parse caps to 4k — records_from path already caps; here we build
    # oversized records directly to exercise format re-capping.
    planner_block = format_clarification_data(records, phase="planner")
    worker_block = format_clarification_data(records, phase="worker")
    assert len(worker_block) <= MAX_CLARIFY_BLOCK_CHARS_WORKER
    assert len(planner_block) >= len(worker_block)

    amplified = clarification_amplified_chars(records, worker_count=4)
    # Worker copies are bounded; total must be << unbounded 4k * (1+4+1).
    assert amplified < MAX_CLARIFY_ANSWERS_AGGREGATE_CHARS * 6
    assert amplified == (
        len(format_clarification_data(records, phase="planner"))
        + 4 * len(format_clarification_data(records, phase="worker"))
        + synthesis_clarification_encoded_chars(records)
    )
    tokens = clarification_extra_input_tokens(records, worker_count=4)
    assert tokens >= 1
    assert tokens == max(1, (amplified + 3) // 4)  # ceil(chars/4)

    worker_prompt = with_clarifications("BASE", records, phase="worker")
    assert "BASE" in worker_prompt
    assert len(worker_prompt) <= len("BASE\n\n") + MAX_CLARIFY_BLOCK_CHARS_WORKER


def test_o014_synthesis_clarifications_encoded_once_escape_heavy() -> None:
    """O-014: escape-heavy clarify JSON is priced at once-encoded envelope size."""
    esc = '\\"' * 500
    records = [
        ClarificationRecord(question_id="0", question='Q"1', answer=esc[:2000]),
        ClarificationRecord(question_id="1", question='Q"2', answer=esc[:2000]),
    ]
    payload = clarification_payload_for_phase(records, phase="synthesis")
    accounted = synthesis_clarification_encoded_chars(records)
    assert payload
    assert accounted > 0

    outputs = [WorkerOutput(subagent_id="w0", sub_question="q", answer="a")]
    plan = "research topic"
    once = build_synthesis_prompt(plan, outputs, clarifications=payload)
    plain = build_synthesis_prompt(plan, outputs)
    actual = len(once) - len(plain)
    assert actual == accounted

    # Legacy double-encode path (footer inside original_request) inflates ~2x.
    footer = with_clarifications(plan, records, phase="planner")
    doubled = build_synthesis_prompt(footer, outputs)
    double_delta = len(doubled) - len(plain)
    assert double_delta > actual * 1.5
    assert "clarifications" in once
    assert 'Q\\"1' in once or '"question":"Q\\"1"' in once or "Q\\\"1" in once
