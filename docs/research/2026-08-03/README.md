# Research pass — 2026-08-03 — Agent architecture state of the art

Provenance for
[`agent-architecture-state-of-the-art.md`](./agent-architecture-state-of-the-art.md),
a standalone reference on how production LLM agents are built as of August 2026.
This pass extends the [2026-07-14 agent-architecture pass](../2026-07-14/README.md):
that one was a pattern catalog, this one runs eight parallel workstreams and
reorganizes their findings by decision surface, puts a scope limit on every
number, and corrects six prior positions. The eight workstream memos are the raw
inputs; the main document is the reviewed synthesis and the thing to cite.

| Memo | Role |
| --- | --- |
| [agent-architecture-state-of-the-art.md](./agent-architecture-state-of-the-art.md) | Main deliverable. The synthesis across all eight workstreams, organized by decision surface: loop shape, inference-time compute, multi-agent topologies, tools, memory, planning, verification (Part A); production ops, security seam, evaluation, training/inference boundary, reference architectures, framework selection (Part B). Confidence-tagged claims, ten decisions with defaults and exit conditions, unified sources. |
| [ws1-single-agent-loops.md](./ws1-single-agent-loops.md) | Single-agent control loops, reasoning-state handling, inference-time compute, prompt/harness architecture, steering and cancellation semantics. |
| [ws2-multi-agent.md](./ws2-multi-agent.md) | Multi-agent topologies and the controlled evidence for each; plan-to-execution binding, state sharing, fan-out bounds, cost, MCP/A2A protocol reality. |
| [ws3-tools-and-environment.md](./ws3-tools-and-environment.md) | Tool-call representation (schema vs. code-as-action), tool ergonomics and token economics, long-context tool degradation, MCP `2026-07-28` including authorization, computer-use grounding, the untrusted-tool-output security seam, determinism and replay. |
| [ws4-memory-context.md](./ws4-memory-context.md) | Context construction, compaction, externalized state, retrieval, long-term memory, memory as a security boundary, memory evaluation. |
| [ws5-planning-verification.md](./ws5-planning-verification.md) | Task decomposition and plan substrates, the self-correction literature, verifier design and grader trust boundary, abstention, and which scaffolds get absorbed into models. |
| [ws6-evaluation.md](./ws6-evaluation.md) | Offline and online evaluation, benchmark validity audits, harness-driven score spread, human evaluation, reliability metrics, OpenTelemetry GenAI tracing semantics. |
| [ws7-production-ops.md](./ws7-production-ops.md) | Runtime substrate and the policy layer around it: durable execution, streaming and resume, HITL supervision efficacy, cost and prompt caching, isolation, delegated identity, degrade behavior, rollout, the regulatory clock. |
| [ws8-case-studies.md](./ws8-case-studies.md) | Comparable architectures of shipped coding, research, computer-use, and enterprise agents, plus framework selection and migration reality. |
| [deferred-issues.md](./deferred-issues.md) | Close-out record for the review/patch round — which workstream patches applied and that no deferred issues remain open. |

**Access date for all external URLs in this pass:** 2026-08-03.

Research is orientation and provenance — it does not override a PRD's concrete
values. Several widely repeated figures carried here are vendor-internal claims
with undisclosed harnesses; they are labeled as such and are not targets.
