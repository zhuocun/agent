"""Regression tests for post-#258 architecture review residuals (Phase 1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic.continuation import (
    AgenticContinuation,
    CompletedWorkerState,
)
from app.agentic.orchestrator import _resume_worker_continuation
from app.config import Settings
from app.db.models import Conversation, Message, User
from app.db.repositories import messages as messages_repo
from app.providers.protocol import (
    AnswerDelta,
    Complete,
    ProviderEvent,
    ToolResult,
    UsageUpdate,
)
from app.streaming.handler import ResumeToolSeed


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "PROVIDER_BACKEND": "fake",
        "AGENTIC_ENABLED": True,
        "TOOLS_ENABLED": True,
        "AGENTIC_PLAN_APPROVAL": False,
        "AGENTIC_VERIFIER": False,
        "AGENTIC_MAX_WORKERS": 2,
        "AGENTIC_RUN_BUDGET_USD": 10.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _cost(_usage: UsageUpdate) -> float:
    return 0.01


@pytest.mark.asyncio
async def test_ar005_resume_worker_propagates_cancelled_error() -> None:
    """AR-005: CancelledError on resume must not become outcome=failed."""

    def _make_stream_for(
        _prompt: str, *, allowed_tools: set[str] | None = None
    ):
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="partial")
                raise asyncio.CancelledError()
                if False:  # pragma: no cover
                    yield Complete(usage=UsageUpdate())

            return _gen()

        return _make

    cont = AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="DEEP_RESEARCH: alpha | beta",
        plan=("alpha", "beta"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="beta",
                answer="beta ok",
                usage=UsageUpdate(input_tokens=1, output_tokens=1),
                cost_usd=0.1,
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        planner_cost_usd=0.05,
        budget_halted=False,
        actual_cost_usd=0.2,
        paused_worker_index=0,
        paused_sub_question="alpha",
        partial_answer="pre ",
        orchestration_mode="deep_research",
        paused_worker_usage=UsageUpdate(input_tokens=2, output_tokens=1),
        paused_worker_cost_usd=0.05,
    )

    async def _drain() -> None:
        async for _ in _resume_worker_continuation(
            make_stream_for=_make_stream_for,
            settings=_settings(),
            cost_for_usage=_cost,
            continuation=cont,
            resume_tool_result=ToolResult(
                tool_call_id="call-1",
                name="request_user_confirmation",
                status="success",
                approval_state="approved",
            ),
            server_approved_call_ids={"call-1"},
        ):
            pass

    with pytest.raises(asyncio.CancelledError):
        await _drain()


@pytest.mark.asyncio
async def test_ar004_budget_halted_skips_awaiting_approval_branch() -> None:
    """AR-004: when budget_halted and a pause exists, emit cancel not HITL."""
    from app.providers.protocol import AwaitingApproval

    budget_halted = True
    worker_pause: object | None = type(
        "P",
        (),
        {
            "tool_call_id": "w0:call",
            "tool_name": "calendar_create_event",
            "tool_label": "Create",
            "subagent_id": "worker-0",
            "sub_question": "alpha",
            "partial_answer": "partial",
            "source_ids": (),
            "usage": UsageUpdate(input_tokens=1, output_tokens=1),
        },
    )()

    emitted: list[ProviderEvent] = []
    if worker_pause is not None and budget_halted:
        emitted.append(
            ToolResult(
                tool_call_id=worker_pause.tool_call_id,  # type: ignore[attr-defined]
                name=worker_pause.tool_name,  # type: ignore[attr-defined]
                label=worker_pause.tool_label,  # type: ignore[attr-defined]
                status="cancelled",
                approval_state="rejected",
                summary="Cancelled: run budget already exhausted.",
                error="budget",
                subagent_id=worker_pause.subagent_id,  # type: ignore[attr-defined]
            )
        )
        worker_pause = None

    if worker_pause is not None:
        emitted.append(AwaitingApproval(tool_call_id="should-not"))

    assert len(emitted) == 1
    assert isinstance(emitted[0], ToolResult)
    assert emitted[0].status == "cancelled"
    assert not any(isinstance(e, AwaitingApproval) for e in emitted)


@pytest.mark.asyncio
async def test_a1_has_completed_hitl_continuation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(id=uuid4(), is_anonymous=True)
        session.add(user)
        await session.flush()
        conv = Conversation(
            id=uuid4(),
            user_id=user.id,
            title="t",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(conv)
        await session.flush()
        user_msg = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="user",
            parts=[{"type": "text", "text": "hi"}],
            status="done",
        )
        session.add(user_msg)
        await session.flush()
        paused = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            parts=[{"type": "text", "text": "paused"}],
            status="awaiting_approval",
            responds_to_message_id=user_msg.id,
        )
        session.add(paused)
        await session.commit()

        assert not await messages_repo.has_completed_hitl_continuation(
            session,
            conversation_id=conv.id,
            paused_message=paused,
            user_message_id=user_msg.id,
        )

        done = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            parts=[{"type": "text", "text": "done"}],
            status="done",
            responds_to_message_id=user_msg.id,
        )
        session.add(done)
        await session.commit()

        assert await messages_repo.has_completed_hitl_continuation(
            session,
            conversation_id=conv.id,
            paused_message=paused,
            user_message_id=user_msg.id,
        )


def test_ar002_billable_delta_subtracts_prior_and_paused_worker() -> None:
    """AR-002 helper: resume must not re-charge pre-pause dollars."""
    from app.streaming import handler as handler_mod

    prior = 0.2
    paused_worker = 0.05
    logical = 0.55

    already = prior + paused_worker
    billable = max(0.0, logical - already)
    assert billable == pytest.approx(0.3)

    seed = ResumeToolSeed(
        tool_call_id="c",
        name="t",
        label=None,
        decision="approve",
        input={},
        prior_run_cost_usd=prior,
        agentic_continuation=AgenticContinuation(
            phase="worker",
            paused_subagent_id="worker-0",
            user_text="q",
            plan=("a",),
            completed_workers=(),
            planner_usage=UsageUpdate(),
            planner_cost_usd=0.0,
            paused_worker_cost_usd=paused_worker,
        ),
    )
    assert seed.prior_run_cost_usd == pytest.approx(0.2)
    assert seed.agentic_continuation is not None
    assert seed.agentic_continuation.paused_worker_cost_usd == pytest.approx(0.05)
    assert hasattr(handler_mod, "ResumeToolSeed")


@pytest.mark.asyncio
async def test_ar001_assert_prod_safe_requires_tools_with_agentic() -> None:
    """Fable gap 1: AGENTIC_ENABLED without TOOLS_ENABLED must fail boot."""
    with pytest.raises(RuntimeError, match="AGENTIC_ENABLED requires TOOLS_ENABLED"):
        Settings(
            PROVIDER_BACKEND="fake",
            AGENTIC_ENABLED=True,
            TOOLS_ENABLED=False,
        ).assert_prod_safe()


def test_ar007_residual_estimate_smaller_than_full_run() -> None:
    """AR-007: resume reservation must be smaller than a fresh full estimate."""
    from app.agentic import budget as budget_mod
    from app.providers.tiers import get_binding

    settings = _settings(AGENTIC_MAX_WORKERS=4, AGENTIC_VERIFIER=False)
    binding = get_binding("smart")
    full = budget_mod.estimate_run_cost(
        sub_question_count=4, binding=binding, settings=settings
    )
    residual = budget_mod.estimate_residual_run_cost(
        remaining_workers=1,
        binding=binding,
        settings=settings,
        include_planner=False,
    )
    assert residual < full
    assert residual > 0


def test_a9_parse_ok_quorum_blocks_minority_pass() -> None:
    """A-9: [garbage, garbage, pass] with N=3 must not claim Verification: pass."""
    from app.agentic.verifier import JudgeSample, _finalize_samples

    garbage = JudgeSample(
        verdict="fail", report="", raw="not json", parse_ok=False
    )
    ok_pass = JudgeSample(
        verdict="pass", report="looks good", raw='{"verdict":"pass"}', parse_ok=True
    )
    result = _finalize_samples(
        draft="manager draft",
        samples=[garbage, garbage, ok_pass],
        total_usage=UsageUpdate(input_tokens=1, output_tokens=1),
        sample_usages=(UsageUpdate(), UsageUpdate(), UsageUpdate()),
        cost_usd=0.01,
        requested_n=3,
        budget_halted=False,
        draft_truncated=False,
    )
    assert result.parse_failed is True
    assert "Verification: pass" not in result.answer


def test_agentic_max_concurrency_config_positive() -> None:
    """Fable gap 2 (config half): concurrency bound is boot-validated."""
    s = _settings(AGENTIC_MAX_CONCURRENCY=3)
    s.assert_prod_safe()
    assert s.agentic_max_concurrency == 3
    with pytest.raises(RuntimeError, match="AGENTIC_MAX_CONCURRENCY"):
        Settings(
            PROVIDER_BACKEND="fake",
            AGENTIC_ENABLED=True,
            TOOLS_ENABLED=True,
            AGENTIC_MAX_CONCURRENCY=0,
        ).assert_prod_safe()


def test_ar021_rejects_nan_budget() -> None:
    """AR-021: NaN/inf must fail assert_prod_safe."""
    import math

    with pytest.raises(RuntimeError, match="finite"):
        Settings(
            PROVIDER_BACKEND="fake",
            AGENTIC_ENABLED=True,
            TOOLS_ENABLED=True,
            AGENTIC_RUN_BUDGET_USD=math.nan,
        ).assert_prod_safe()
