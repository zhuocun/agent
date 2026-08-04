# Research

Dated research passes and findings memos that ground the PRDs, design canon, and
UX best-practice docs in external sources and repo reality. Research is
orientation and provenance — it does not override a PRD's concrete values.

## Passes

### 2026-05-27 — PRD review synthesis

Initial research-and-PRD-review pass, one memo per PRD area plus a synthesis.

- [00-synthesis.md](./2026-05-27/00-synthesis.md) — cross-area synthesis of the pass.
- [01-core-chat-ux.md](./2026-05-27/01-core-chat-ux.md) — core chat, design system, error/limit states.
- [02-ai-capabilities-transparency.md](./2026-05-27/02-ai-capabilities-transparency.md) — AI capabilities, model layer, transparency contract.
- [03-mobile-cross-platform.md](./2026-05-27/03-mobile-cross-platform.md) — mobile & cross-platform.
- [04-technical-architecture.md](./2026-05-27/04-technical-architecture.md) — technical architecture.
- [05-roadmap-monetization-compliance.md](./2026-05-27/05-roadmap-monetization-compliance.md) — roadmap, monetization, metrics, compliance.

### 2026-07-05 — UX best-practices research

The pass that seeded [`docs/ux-best-practices/`](../ux-best-practices/README.md).

- [cross-cutting-ux-best-practices.md](./2026-07-05/cross-cutting-ux-best-practices.md) — accessibility, performance, trust/privacy/safety.
- [ux-best-practices-platform-split.md](./2026-07-05/ux-best-practices-platform-split.md) — desktop/mobile platform split.
- [02-agentic-tool-ui-ux.md](./2026-07-05/02-agentic-tool-ui-ux.md) — UX for agentic / tool-using AI UIs.

### UX best-practices findings (R2)

- [ux-best-practices/README.md](./ux-best-practices/README.md) — onboarding, guest→signup, BYOK, settings, billing, limit-states findings (R2).

### 2026-07-14 — AI agent architecture

Industry patterns + Olune as-built audit grounding the normative design at
[`docs/plans/02-agent-architecture.md`](../plans/02-agent-architecture.md).

- [Pass index](./2026-07-14/README.md)
- [agent-architecture-industry.md](./2026-07-14/agent-architecture-industry.md) — mid-2026 runtime patterns, bounds, HITL, cost, OTel, anti-patterns.
- [agent-architecture-as-built.md](./2026-07-14/agent-architecture-as-built.md) — shipped topology, invariants, and gaps vs plan 01.

### 2026-08-03 — Agent architecture state of the art

Extends the 2026-07-14 agent-architecture pass: eight parallel workstreams
reorganized by decision surface, with a scope limit on every number and six
prior positions corrected.

- [Pass index](./2026-08-03/README.md)
- [agent-architecture-state-of-the-art.md](./2026-08-03/agent-architecture-state-of-the-art.md) — loop, compute, topologies, tools, memory, planning, verification, production ops, evaluation, framework selection.

## Related canon

- [Docs index](../README.md)
- [Product requirements (PRDs)](../prd/)
- [Design principles](../design/README.md)
- [UX best practices](../ux-best-practices/README.md)
