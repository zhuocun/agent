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


def synthesize(
    outputs: list[WorkerOutput],
    *,
    planned: int | None = None,
    budget_halted: bool = False,
) -> str:
    """Deterministically merge worker outputs into one synthesized answer.

    Pure string composition over the workers' (untrusted) answer text — no
    worker output is ever treated as an instruction. Empty input yields a stable
    "no findings" line so the aggregator subagent always has a non-empty answer.

    `planned` is the number of sub-questions the planner produced; when the run
    was cut short by the per-run budget (`budget_halted`), the synthesis is
    LABELED as a partial answer ("answered N of M planned steps") rather than an
    error — the graceful-degrade path (FR-26g). With `budget_halted=False` (the
    default) the output is byte-for-byte the historical synthesis.
    """
    completed = len(outputs)
    total = planned if planned is not None else completed
    if not outputs:
        base = "Synthesis: no worker findings were produced."
    else:
        lines = [f"Synthesis of {completed} findings:"]
        for index, output in enumerate(outputs, start=1):
            answer = output.answer.strip() or "(no answer)"
            lines.append(f"{index}. {output.sub_question}: {answer}")
        base = "\n".join(lines)
    if budget_halted:
        base += (
            "\n\n[Partial answer: stopped early to stay within the run budget; "
            f"answered {completed} of {total} planned steps.]"
        )
    return base
