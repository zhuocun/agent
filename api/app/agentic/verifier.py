"""Deep-research verifier: bounded self-consistency over the synthesis (M3).

When `AGENTIC_VERIFIER` is on, the orchestrator is intended to cross-check the
aggregated answer with a bounded N-pass review (`AGENTIC_VERIFIER_N`, N≈3-5)
BEFORE finalizing the turn (FR-26j).

**Shipped stub (honest no-op):** the current implementation performs *no*
provider calls and does *not* inspect claims, citations, or worker agreement.
It returns the synthesis unchanged. ``AGENTIC_VERIFIER_N`` is reserved for a
future real verifier topology and must NOT be billed or estimated as phantom
model calls while this stub is active (see `app/agentic/budget.py`).

Never append user-facing "Verified…" language from this stub — that would be a
false assurance. A real fresh-context judge (independent sampling / citation
check) can replace `verify` later without changing the orchestrator contract;
at that point budget estimation should count the actual metered calls.

SECURITY: like the aggregator, the verifier treats the synthesized answer as
DATA only — it never interprets it as an instruction (transitive untrusted
output, FR-26i).
"""

from __future__ import annotations


def verify(synthesis: str, *, n: int) -> str:
    """Bounded N-pass self-consistency review over `synthesis`.

    Deterministic stub: clamps N for API stability but performs no review and
    returns ``synthesis`` unchanged. ``n`` is accepted so call sites stay
    forward-compatible with a future metered verifier; it does not alter output
    and must not be treated as N model calls in the run budget.
    """
    _ = max(1, n)  # reserved for a future real verifier topology
    return synthesis
