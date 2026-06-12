"""Agentic mode: multi-agent orchestration layered on the tool seam.

DEFAULT-OFF behind `AGENTIC_ENABLED` (which itself requires `TOOLS_ENABLED`).
The orchestrator (`orchestrator.run_orchestrator`) is the ONLY entry point — the
streaming handler routes into it from `_build_provider_iter` exclusively when the
flag is on AND a non-None `agentic_mode` was requested, so a flag-off turn (and
an agentic-off turn that still carries `agenticMode`) is byte-for-byte identical
to a pre-agentic build.

Modes:
- ``single`` (M1): one agent loop wrapped as a single ``primary`` subagent; every
  event is tagged with its ``subagent_id`` and bracketed by
  ``SubagentStarted`` / ``SubagentDone``.
- ``deep_research`` (M2): a planner decomposes the prompt into sub-questions, a
  bounded set of ``worker`` subagents answer them in parallel under a semaphore,
  and an ``aggregator`` subagent synthesizes the final answer from the workers'
  (untrusted) structured outputs.
"""

from __future__ import annotations

from app.agentic.orchestrator import (
    PLAN_APPROVAL_CALL_ID,
    PLAN_APPROVAL_TOOL_NAME,
    run_orchestrator,
)

__all__ = [
    "PLAN_APPROVAL_CALL_ID",
    "PLAN_APPROVAL_TOOL_NAME",
    "run_orchestrator",
]
