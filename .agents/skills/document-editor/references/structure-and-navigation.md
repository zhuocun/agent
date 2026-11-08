# Structure and navigation

## Forward reading order

Order content for a single top-down read: establish each concept or fact before it is needed, or explain it in place. A passage that requires later material to be understood is a structural defect whether or not an explicit reference marks it. Where understanding requires later material, move the defining material ahead of its first use or restate the minimum context in place. Verify the result in **5. Verify and deliver** in `SKILL.md`.

## Definitions and authoritative locations

1. Give each definition, decision, invariant, rule, contract, complete comparison, and document-level disclaimer one authoritative location. Elsewhere, restate only the minimum local consequence a reader needs in place; do not maintain competing full copies in prose, code, or tables.
2. Keep classification and evaluation axes orthogonal. Do not mix or substitute criteria that answer different questions.

## Common reader paths

Choose and adapt the path that matches the reader's task:

| Document need | Typical reader path |
| --- | --- |
| High-level design or review | Problem and goals → context and definitions → constraints → proposed design → success criteria → contracts and data semantics → affected systems → rollout strategy → risks and validation |
| Implementation design or runbook | Scope and prerequisites → current and target behavior → detailed changes → data flow and edge cases → migration and operations → testing, observability, rollout, and rollback → risks and open questions |
| Decision memo, ADR, or RFC | Context → decision or recommendation → options → evaluation and tradeoffs → consequences and re-evaluation triggers |
| Research report | Question and scope → sources and method → findings and provenance → analysis and limitations → conclusions or recommendations → unresolved questions |
| Technical solution or adoption guide | Audience and bottleneck → current limits → proposed capability → proof → usage path → alternatives → internals → failure modes and mitigations → next steps |
| Workflow or guidance | Applicability → classification or diagnosis → source-grounding steps → operating workflow → verification → escalation and limitations |

Move definitions before evaluation when readers need the concepts to judge the design. Move proof and the usage path before internals when adoption is the primary task.

## Headings, navigation, and transitions

1. Match the title and opening scope to the document's real coverage.
2. Use a consistent semantic heading hierarchy. Add numeric heading labels only when the destination convention or navigation need calls for them.
3. Do not invent parallel module, decision, validation, option, or step ID systems for editorial organization. Use ordered steps when order is operationally meaningful, not as a substitute for semantic names.
4. Provide the necessary context at the point of use.
5. Give each section one clear purpose or reader question and keep neighboring sections non-overlapping.
6. Order sections by the reader's decision path, not by the history of how the team built or discussed the work. Separate audience paths when reviewers, adopters, operators, and implementers need different depth.
7. Use a short bridge only when it clarifies causality. Put it at the start of the section it introduces, and remove trailing meta-narration about what the document will explain next.
8. Use question headings only for genuine reader questions and answer them immediately. Prefer declarative headings in settled decision narratives; do not use staged questions to recreate deliberation.
9. Reuse concept names already established in the source material or domain as navigation anchors; do not coin labels for navigation.
10. Do not front-load lookup blocks. Make each opaque term readable at its first occurrence in place: use plain wording with the exact code in parentheses, such as "rejected: the record is still referenced (error 1042)," instead of a bare code. An identifier that already reads plainly, such as ERR_TEMPLATE_IN_USE, needs no added gloss. Add a front-of-document glossary, error-code table, or quick-reference only when the owner explicitly asks for one.

## Definition vs implementation

Keep these layers distinct. Move definitions earlier and implementation later unless the document is explicitly implementation-focused.

- **Definition layer:** goals, domain semantics, responsibility boundaries, conceptual models, invariants, and decision criteria.
- **Implementation layer:** exact contracts, validation and error behavior, persistence and migration rules, algorithms, operational procedures, observability, permissions, and rollout changes.

Keep high-level design focused on decisions, boundaries, semantics, tradeoffs, compatibility, consistency, rollout strategy, and risk. Retain implementation detail only when it helps the intended reader judge feasibility, constraints, reliability, or tradeoffs.

When a document set splits material across volumes, apply the same layer boundaries and let each document independently fulfill its reader contract.
