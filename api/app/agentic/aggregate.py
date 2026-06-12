"""Deep-research aggregation: synthesize a final answer from worker outputs.

SECURITY: worker outputs are UNTRUSTED (each is model output over a sub-question,
a prompt-injection surface). The synthesizer treats them as DATA only — it
concatenates their text into a structured summary and never interprets any
worker output as an instruction. M2 ships a deterministic, no-provider synthesis
so the fan-out has a stable, testable contract; a real LLM synthesizer can
replace `synthesize` later without changing the orchestrator contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerOutput:
    """One worker subagent's contribution to the synthesis (untrusted data)."""

    subagent_id: str
    sub_question: str
    answer: str


def synthesize(outputs: list[WorkerOutput]) -> str:
    """Deterministically merge worker outputs into one synthesized answer.

    Pure string composition over the workers' (untrusted) answer text — no
    worker output is ever treated as an instruction. Empty input yields a stable
    "no findings" line so the aggregator subagent always has a non-empty answer.
    """
    if not outputs:
        return "Synthesis: no worker findings were produced."
    lines = [f"Synthesis of {len(outputs)} findings:"]
    for index, output in enumerate(outputs, start=1):
        answer = output.answer.strip() or "(no answer)"
        lines.append(f"{index}. {output.sub_question}: {answer}")
    return "\n".join(lines)
