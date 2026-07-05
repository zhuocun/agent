# UX Best Practices

This directory holds **platform-specific UX best-practice guidance** for the transparent, multi-model AI chat product. It complements — but does not replace — the PRDs and design-principle canon.

## What lives here

| Document | Audience | Scope |
| --- | --- | --- |
| [desktop-ux.md](./desktop-ux.md) | Designers, engineers, reviewers shipping pointer/keyboard surfaces | Keyboard shortcuts, command palette, hover/focus, multi-pane layouts, wide-viewport density, mouse-precision affordances |
| [mobile-ux.md](./mobile-ux.md) | Designers, engineers, reviewers shipping touch/PWA surfaces | Touch targets, thumb reach, bottom sheets, safe-area, keyboard avoidance, PWA install, iOS Safari constraints |

Both documents share an **identical 14-section taxonomy** so they read as a matched pair. Shared concerns (streaming, transparency, agentic tools, billing) appear in both with the same semantics; platform-exclusive depth lives in §13 of each doc.

## Canonical position

These docs sit **alongside** `docs/design/` (direction) and **below** the PRDs (implementation contract):

- **PRDs win** on concrete values — token names, contrast ratios, component states, acceptance criteria.
- **Design principles win** on direction — restraint, warmth, what counts as ornament.
- **These docs win** on external best-practice rationale, gap callouts against shipped code, and actionable review checklists.

When a recommendation here and a PRD disagree on a concrete value, follow the PRD and file a rationale entry if the principle genuinely changed.

## How to use

1. **Before shipping a surface** — read the relevant section in the platform doc (desktop or mobile) and run the §14 checklist at PR review time.
2. **Before a cross-platform feature** — read the same section number in **both** docs; verify shared claims are identical and platform notes are honored.
3. **When canon already covers a practice** — link to the PRD or component; do not restate spec detail here.
4. **When a gap is flagged** — treat ✗/◑ items as backlog candidates; priority tags `[P0]`/`[P1]`/`[P2]` match the research memos.

## Related canon

- [PRD 01 — Core Chat](../prd/01-core-chat-experience.md)
- [PRD 02 — AI Capabilities](../prd/02-ai-capabilities.md)
- [PRD 03 — Mobile Cross-Platform](../prd/03-mobile-cross-platform.md)
- [PRD 05 — Roadmap & Monetization](../prd/05-roadmap-monetization-metrics.md)
- [PRD 06 — Design System](../prd/06-design-system-visual-spec.md)
- [PRD 07 — Transparency Contract](../prd/07-transparency-contract.md)
- [PRD 08 — Error & Limit States](../prd/08-error-and-limit-states.md)
- [Design principles](../design/00-principles.md)
- [Mobile UX audits (ST1–ST5)](../mobile-ux/ST5-spec.md)
- [Research memos (2026-07-05)](../research/2026-07-05/)

## Research provenance

These docs were synthesized from the 2026-07-05 research pass (R1–R5) grounded in repo canon and authoritative external sources (WCAG 2.2, WAI-ARIA APG, Apple HIG, Material Design 3, web.dev, Nielsen Norman Group, EU AI Act Art. 50). Items marked `[verify-at-build]` should be re-checked against live sources before locking acceptance criteria.
