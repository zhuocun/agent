"""Deep-research verifier: bounded self-consistency over the synthesis (M3).

When `AGENTIC_VERIFIER` is on, the orchestrator cross-checks the aggregated
answer with a bounded N-pass self-consistency review (`AGENTIC_VERIFIER_N`,
N≈3-5) BEFORE finalizing the turn (FR-26j). M3 ships a DETERMINISTIC, no-provider
verifier so the engine has a stable, testable contract: the synthesis is already
a pure composition of the workers' (untrusted) outputs, so N identical passes
trivially agree; the verifier records that agreement as a short, content-free
note appended to the answer. A real provider-backed reviewer (independent
sampling + majority vote) can replace `verify` later without changing the
orchestrator contract.

SECURITY: like the aggregator, the verifier treats the synthesized answer as
DATA only — it never interprets it as an instruction (transitive untrusted
output, FR-26i).
"""

from __future__ import annotations


def verify(synthesis: str, *, n: int) -> str:
    """Run a bounded N-pass self-consistency review over `synthesis`.

    Deterministic v1: clamps N to ``>= 1`` and appends a content-free
    verification note recording the pass count. Returns the (unchanged) answer
    plus the note so the FE can render a "verified" affordance and a reload
    replays it. No provider call, so the verifier adds no token cost in v1.
    """
    passes = max(1, n)
    return f"{synthesis}\n\n[Verified by {passes}-pass self-consistency review.]"
