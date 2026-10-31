---
name: document-editor
description: >-
  Author, edit, and review formal human-facing documents at the document level
  without silently changing their meaning. Use for design docs, RFCs,
  implementation plans, proposals, specs, research reports, guides, decision
  memos, and design-review documents when the work concerns authoring from
  sources, scope, reader path, structure, abstraction, factual grounding,
  evidence, tradeoffs, registries, structured assets, document governance,
  concision, or reviewability. Do not use for mechanical extraction,
  reformatting, or list generation when wording and organization are prescribed
  and no document-level judgment is needed; for casual notes, chat replies,
  routine status updates, or pure sentence-level wording or translation polish;
  or for agent-instruction files such as SKILL.md, prompts, workflows, or
  tool-routing docs.
---

# Document Editor

Produce and maintain formal human-facing documents so readers can understand them quickly, review them accurately, and act with less friction. When editing, preserve meaning while improving scope, order, explanation, and presentation; when authoring, write to the same standard from the first draft.

Apply this priority order: **truth and authority → reader contract and scope → decisions and evidence → abstraction and structure → completeness and actionability → concision and presentation**.

## Modes and framing

Pick the mode first; all three share the **Document standard** and **Review and verify** checks.

- **Create** — author a new document from authoritative sources. Follow **Create mode**.
- **Optimize** — edit an existing document while preserving its meaning except for authorized changes or source-backed corrections. Follow **Optimize mode**.
- **Review** — judge a document without editing it. Follow **Review mode**.

Frame the work before drafting, editing, or judging:

1. **Reader contract.** Identify the document type, audience, purpose, target language, abstraction level, and decision or action it promises to support. Establish the bottleneck, failure mode, or uncertainty it resolves, what readers already know, and the context they need.
2. **Authorities and constraints.** Identify the sources appropriate to each claim type, owner and format constraints, required content slots, governance state, content protected exactly or structurally, and task scope or success criteria. Treat owner-defined length and structural budgets as constraints; if a change is necessary, expose the content-level cause and follow the owner's approval process. Apply only controls relevant to the document type and its real governance; record an explicit not-applicable reason for excluding a required or high-risk control. State material assumptions and missing information rather than inventing the frame; proceed where they do not block accurate work.
3. **Policy fit.** Check the **Hard prohibitions** and **Governance applicability** against the document's required navigation, records, templates, and syntax. These are this skill's document policies, not universal measures of document quality. A legitimate reader task or lifecycle can be incompatible with them; report that as a policy-fit issue rather than a general quality defect. Semantic headings and established concept names remain available for navigation.
4. **Conflict and continuation.** Use known lifecycle facts and user decisions. If a policy conflict remains unresolved, name it and ask only for the missing decision about applicability, an authorized alternative, or delivery scope. Hold the conflicting change and continue independent safe work. Follow explicit informed user directions as higher-priority instructions within their stated scope, then resume without requesting the same decision again. A governance request or template protection marker alone does not waive other policies. Do not delete protected content or break required syntax to obtain compliance. Before relocating protected governance records out of the document, verify a compatible authorized destination; if none exists, leave the disputed content intact and surface the incompatibility.

## Hard prohibitions

Apply these eight policies throughout the task, with their stated exceptions and the instruction scope resolved under **Modes and framing**.

1. **No patch-style updates.** Never leave update residue: no addenda, errata, changelogs, revision histories, or correction notes, and no "updated" markers, "as of" notes, or before-vs-after narration that describe a change to the document. Fold every change into the owning passage so the document always reads as if written correct the first time. A date that bounds when a claim holds — a measurement date, data snapshot, or the evaluated version — is evidence and stays next to the claim.
2. **No deferral to other documents.** Never offload content readers need to another document in the same working set — the documents being authored or edited together in this task — through companion-volume pointers, document maps, or directions such as "see the implementation document." The document carries what its reader needs and omits the rest. Naming an approved source as the authority for a claim is not deferral when the document also states the content the reader needs. Evidence citations to externally published sources in research reports establish attribution and are not deferral; retain them.
3. **No cross-references between sections.** No "see chapter 6", "as described above/below", table of contents, or forward/backward pointers. Order sections so each is understandable where it stands; when another section's fact is needed, restate the minimum inline without naming the section.
4. **Prefer titled bullets over paragraphs.** When one to five parallel, independent points suffice, present them as bullet points, each opening with a clear and precise title, rather than paragraph prose. A causal chain or reasoning in which each sentence depends on the one before stays prose.
5. **No unnecessary table columns.** Every column must carry decision-relevant information that varies across rows; drop or merge any column that repeats another, restates the row label, or exists only for symmetry.
6. **No coined vocabulary or jargon.** Use plain words and terms established in the field or in the source material; never invent labels, metaphors, or shorthand names for the document's own concepts.
7. **No direct code references.** Never cite class, method, function, or variable names, file paths, or line numbers in the document. Describe the behavior in business or domain terms instead. Identifiers that are part of the subject's own contract, or that the reader must type or locate to act, stay byte-exact. These include table and field names, status enums, API fields, and the commands, configuration keys, and file paths that a step tells the reader to run, set, or open, as in a runbook, a setup path, or the steps of an implementation plan.
8. **No context-bound terms from other sections or documents.** Never use a term, code, or label whose meaning is established only in another section or another document — a bare error code, an internal task name, an abbreviation defined elsewhere. State the fact in plain wording in place; keep such a code only where the document itself establishes what it means.

## Document standard

### Forward reading order

Order content for a single top-down read: establish each concept or fact before it is needed, or explain it in place. A passage that requires later material to be understood is a structural defect whether or not an explicit reference marks it. After drafting or restructuring, read the document top to bottom once as a first-time reader; where understanding stalls, move the defining material ahead of its first use or restate the minimum context in place.

### Common reader paths

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

### Headings, navigation, and transitions

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

### Definition vs implementation

This section governs abstraction level; registry placement governs main-text versus appendix location, and asset preservation governs only lossless accounting when content moves.

Keep these layers distinct. Move definitions earlier and implementation later unless the document is explicitly implementation-focused.

- **Definition layer:** goals, domain semantics, responsibility boundaries, conceptual models, invariants, and decision criteria.
- **Implementation layer:** exact contracts, validation and error behavior, persistence and migration rules, algorithms, operational procedures, observability, permissions, and rollout changes.

Keep high-level design focused on decisions, boundaries, semantics, tradeoffs, compatibility, consistency, rollout strategy, and risk. Retain implementation detail only when it helps the intended reader judge feasibility, constraints, reliability, or tradeoffs.

When a document set splits material across volumes, apply the same layer boundaries and let each document independently fulfill its reader contract.

### Claim-type authority

1. Determine authority per claim type. Use implementation or observed behavior for current state, approved requirements or decisions for intended state, and direct observations or primary studies for measured outcomes. Do not apply one global source hierarchy across claim types.
2. When sources disagree, inspect the conflict, use the best-supported claim, and record any difference that affects scope, accuracy, or a decision. Do not choose a source merely because it appears in a preferred category.
3. Distinguish the observed current state, the approved or proposed target state, assumptions, and the gap between them. Do not describe or design against an invented current state.
4. Explain any departure from an established decision and preserve its authorization boundary. Writing or editing authority alone does not authorize a new decision.
5. Flag ambiguity, inconsistency, or missing evidence. Tighten wording noise, not substantive meaning.

### Unknowns, branches, and decisions

1. For a blocking unknown with no established default, record the question, why it is unresolved, the authority or resolver needed, known candidate space, affected decisions or passages, timing or trigger when relevant, and the consequence of remaining unresolved. State a fallback only when a source establishes one.
2. For a branch with an established default, state the default, alternatives, and the criterion that selects among them. Mark confirmation as open without presenting the default as newly invented.
3. Keep each open question independently answerable. When choices must be decided together, present a mutually exclusive and collectively complete decision package; include an explicit unknown or escalation branch when the candidate space is not closed.
4. Never turn an unanswered question into a design conclusion. If the missing answer prevents accurate prose, leave a governed placeholder or registry entry and identify what it blocks.

### Definitions and references

1. Give each definition, decision, invariant, complete comparison, and document-level disclaimer one authoritative location. Elsewhere, restate only the minimum a reader needs in place; do not maintain competing full copies.
2. Keep classification and evaluation axes orthogonal. Do not mix or substitute criteria that answer different questions.

### Decisions, evidence, and actionability

1. Start from the bottleneck, not the feature. State the constraint or failure mode the document resolves.
2. For proposals and decisions, use a compact opening summary that states the proposal, benefit, cost, and main uncertainty. State goals and non-goals, including exclusions readers could reasonably assume were in scope.
3. In decision-heavy sections, place the decision before its support and keep the minimum sufficient reasoning for a reviewer to verify that it holds under the stated constraints. Remove process narration only when the mechanism, evidence, tradeoffs, limitations, and risks remain reviewable.
4. For important claims, preserve the available chain: claim → mechanism → evidence → limitation. Flag a missing link instead of smoothing over it.
5. For research documents, use evidence citations to externally published sources or an owner-compatible provenance scheme to distinguish primary evidence, secondary reporting, established consensus, and analysis or inference. Such citations establish evidence attribution and are not deferral to another document.
6. For improvement claims, identify the named baseline, test condition, evaluation criteria, observed result, and caveat. Keep evidence near the claim, distinguish observation from interpretation, and ensure claimed quantities match the underlying material.
7. Treat realistic examples as evidence: give enough context, preconditions, behavior, outcome, and interpretation for the reader to understand what the example proves and what it does not.
8. Compare alternatives on stable criteria such as correctness, reliability, cost, latency, complexity, maintainability, rollout risk, and reversibility. Preserve each option's sourced strengths before its limits; do not invent balance that the sources do not support.
9. Put assumptions, dependencies, known failure modes, incomplete coverage, mitigations, and bounded caveats close to the solution or claim they qualify. Do not use future plans to compensate for weak present evidence.
10. Tie deferred work to a current gap. For a deliberate extension point or non-goal, state the reserved shape, the trigger for revisiting it, and why reserving it now matters; distinguish committed work, exploration, and open questions.
11. When work varies by type or risk, use an inspect → classify → guide → verify flow. Keep diagnosis separate from recovery validation, and apply the complete decision-package rules for unknowns and branches.
12. Convert tacit judgment into executable checklists, decision tables, workflows, risk categories, failure modes, and validation criteria. When readers must act, include the necessary owner, prerequisites, inputs, outputs, and success criteria.
13. For adoption or onboarding, provide a complete path through prerequisites, setup, invocation, success verification, troubleshooting, and an ownership or feedback route when one exists.

### Registries vs decision narrative

This section governs where content appears in the main text or appendix; abstraction level belongs to the definition-vs-implementation boundary, while lossless verification during moves belongs to asset preservation in Optimize mode.

Keep three layers distinct:

1. **Decision narrative** (main reading path): only the minimum facts, conditions, conclusions, costs, and re-evaluation triggers needed for the current review. Do not reproduce full ledger entries or point readers to the appendix.
2. **Registries and audit ledgers** (appendix of the same document): the unique, complete open-issue, blocker, and verification ledgers, each entry's one authoritative location; the passage an entry qualifies restates only the minimum its reader needs there.
3. **Operational detail** (procedures, runbook steps, configuration): kept out of the decision narrative. Place it with the implementation layer later in the same document, or omit it when the reader contract does not need it.

Rules:

1. Relocation is not deletion — a moved entry keeps every field, conditional direction, and decision-bearing relationship; after restructuring, verify the ledger remains complete entry by entry and field by field.
2. Settled items return to the owning decision section; historical recounts of registry size belong in the external lifecycle system, not in live registries.
3. Domain identifier semantics — uniqueness, immutability, recycling, regeneration on copy — belong in the domain model even while an aspect is still open. State the established default and name the open question inline; if no default exists, say so and identify the blocked decision instead of inventing one.
4. A design document carries non-functional targets such as expected volume, query scale, throughput, latency, and capacity ceilings, or names each unknown together with the decision threshold it unblocks. A named unknown with a threshold beats both an invented number and a silent gap.
5. With several external dependencies, include one unified failure-strategy table — dependency unavailable → affected operations → block or degrade → caching allowance — rather than scattering the rules across chapters.
6. When a per-decision comparison matrix outgrows its narrative, move the matrix to the appendix and keep the decision, its preconditions, and its reversal triggers inline.
7. Treat scanability as a placement goal, not a prose quota. Retain causal explanation that changes how reviewers judge assumptions, tradeoffs, or failure modes.

### Tables, diagrams, media, and code

1. Use tables for stable repeated columns such as options and tradeoffs, risks and mitigations, contracts and meanings, scenarios and verification, or phases and success criteria. Use prose for causality, ambiguity, hidden assumptions, and nuanced caveats.
2. Use parallel table shapes for parallel structures, and do not force uncertain reasoning into apparently precise cells. Tables improve placement; they do not replace the decision narrative.
3. Give every retained or added diagram, image, video, code block, callout, evidence citation, or other native block an editorial job: evidence, instruction, architecture, workflow, or reference.
4. Use a diagram only when it explains a spatial, temporal, boundary, state, or relationship model more clearly than prose. Use a format supported by the destination and its maintainers; do not impose one tool or syntax on every document.
5. Give every figure that must be understood independently the minimum in-place legend needed to read it. Keep semantics consistent by using the same wording in each figure's legend; do not create a shared legend center. Check decision-tree branches for mutually exclusive and collectively complete coverage.
6. Place an overview diagram after the framing needed to interpret it and before the details it organizes. Validate an editable diagram with its actual renderer after changes; if rendering cannot be checked, report that limitation.
7. Introduce code blocks with what they demonstrate and summarize the design implication when it is not obvious. Avoid raw dumps unless required for reproducibility, contract review, or implementation reference.

#### Structured technical expression

Choose the representation from the judgment the reader needs to make; do not default every technical fact to prose or every complex passage to a diagram.

| Reader judgment | Preferred representation |
| --- | --- |
| Data shape, nesting, or current-to-target structure | Minimal JSON, or JSONC when annotations are needed |
| Type, cardinality, optionality, or allowed values | A typed schema suited to the domain, such as TypeScript |
| Request, response, error, or system-boundary contract | A protocol-native example such as HTTP or RPC |
| Parsing order, validation logic, branching, or fallback | Pseudocode or a complete decision tree |
| Observable behavior and acceptance outcome | Gherkin, Given/When/Then, or another scenario form |
| Repeated field, trigger, state, or ownership mapping | A compact table with only varying columns |

1. Introduce each block with the question it helps answer, show only the minimum complete structure, and state the implication afterward when it is not self-evident.
2. Label every block as normative, current-state, target-state, illustrative, pseudocode, or unresolved when readers could mistake one for another.
3. Preserve frozen identifiers byte-exact. Use conspicuous placeholders for unresolved names and say that they are not part of the frozen contract; never invent realistic-looking fields, enum values, routes, or configuration keys.
4. Keep static contracts, dynamic control flow, observable behavior, and cross-item mappings in their native forms. Do not overload one notation to explain all four.
5. Put each complete rule or contract in one authoritative location. Do not repeat it in prose, code, and tables; elsewhere restate only the minimum local consequence.
6. Keep prose for causality, rationale, tradeoffs, uncertainty, and risk. Structured blocks reduce reconstruction work; they do not replace judgment.

### Governance applicability

Apply this section to document-governance apparatus, distinguishing it from domain facts and action owners. Resolve conflicts under **Modes and framing**.

1. Governance apparatus requires a real, external publication or approval lifecycle. Under this policy, an unpublished repository working document read only by repository collaborators carries no signature fields, lifecycle labels, or status or owner fields; its opening holds only what a reader needs to use the content. When governance fields are requested and the lifecycle is unknown, establish whether that external lifecycle exists before adding them.
2. Only when the owner explicitly mandates governance for a document with a genuine external lifecycle, provide only the non-revision metadata the owner requests from this set: status, accountable owner, approver, and approval date. Governance authorization does not waive any hard prohibition. Revision dates, change histories, and re-review narratives remain excluded; process traces belong in an external governance system.
3. Follow the document's real lifecycle rather than inventing one. Attribute approval only when it exists, return materially changed approved content to the appropriate review state, and record the true reason for re-review in the external lifecycle system.
4. Review history, consequential dissent, and lifecycle evidence belong in an external governance system; the edited document never carries them.

## Create mode

Author a new document from authoritative sources using **Modes and framing**; nothing pre-exists to preserve, so there is no inventory or lossless-accounting pass.

1. **Gather authorities before writing.** Collect the sources each claim type needs per **Claim-type authority**. Do not write a claim no source supports; record each genuine gap in the open-question form instead of inventing an answer or a current state.
2. **Outline by reader path.** Draft the section order from the matching reader path, then walk the outline once for forward reading order: every concept a section uses must be established by an earlier section or defined in place.
3. **Draft to the standard.** Apply the Document standard and document policies within the resolved scope from the first draft — placement, evidence chains, registries, media discipline, and governance applicability included.
4. **Verify before delivery.** Run **Review and verify** on the draft as if reviewing someone else's document.

## Optimize mode

Use the source document as the baseline and preserve its meaning under **Preserve source meaning**. Every change must be traceable to a quality rule or an explicit user request.

### Frame the edit

1. Read the full document once without editing and apply **Modes and framing**. Record the current section order as a compact outline unless the bounded local-edit conditions under **Preserve structured assets** apply.
2. Establish the content and asset accounting under **Preserve structured assets** before editing. If the owner requires a pre-edit approval gate, present the mapping at that gate.
3. Diagnose and fix by dependency in this order: authority and scope → reader contract → bottleneck framing → section order (forward reading order) → decision and evidence chain → abstraction boundaries → action path → accuracy → duplication → presentation. Fix any truth issue as soon as it is found; this sequence never delays it.
4. Integrate changes into the owning passages, run the applicable checks, and report unresolved ambiguity instead of hiding it in smoother prose.

### Preserve source meaning

1. Preserve the source meaning, facts, scope, and decisions unless the user explicitly requests a substantive change or the authority for that claim type shows a stated fact is wrong, in which case correct it and report the correction.
2. Do not silently change numbers, dates, owners, names, identifiers, field or API contracts, formulas, requirements, conditional direction, or decisions.

### Preserve structured assets

Keep content and asset mappings only in the editing-session record (working notes and summary to the user), an external approval record, or an owner-named file outside the document's repository; never put a mapping in the document or any other file in its repository. Keep protected-baseline measurements, required authorizations, and protected-asset change reasons and bases in the editing-session record or external approval record, never in the edited document.

1. Set the accounting scope before editing. For a loss-sensitive restructure, split, or compression, inventory the complete affected content and load-bearing assets: decisions, open questions and blockers, conditional branch tables, tradeoff matrices, invariants, non-goals, risks, rollout batches, diagrams, exact contracts, error catalogs, and critical checklists, as applicable. For another edit that touches a load-bearing or protected asset, inventory that asset and its dependencies. A bounded local edit that leaves these assets, protected records, and their relationships untouched needs only brief notes identifying the affected passages and checked dependencies, rather than an outline and dispositions for untouched content. Retain the full-document read and every applicable format, contract, asset, and verification check. If scope or preservation is uncertain, use the complete affected inventory and mapping; expand it before proceeding when the edit grows.
2. Preserve existing diagrams, images, videos, code blocks, callouts, evidence citations, and other native blocks unless the user requests a change or a source-backed edit requires one.
3. Give every inventoried passage or asset a disposition: preserved in place, moved to a named destination, merged into a named authoritative item, or intentionally removed with a reason and the required authorization. Do not use compression as an unreported deletion path.
4. Extend the relocation discipline for registries to every inventoried asset, not only registry entries. Treat conversion to a table or movement to an appendix as relocation under that discipline.
5. Treat exact schemas, interface signatures, identifiers, error definitions, and other contract artifacts as deliverables in their own right. Preserve their completeness and exactness even when surrounding explanation is condensed.
6. Treat an asset's item count or byte identity as a protected baseline only when the owner or delivery format defines it. For a controlled baseline change, record the pre-change and post-change values and any required authorization; never change the baseline silently.
7. When byte-for-byte identity is required, use the configured checksum or comparison method. Do not modify a protected diagram or native asset without authorization; after an authorized change, record its reason and basis and apply the required rendering or behavior checks.
8. Resolve protected-content conflicts under **Modes and framing**. Remove residue that the document policies forbid within the resolved scope; retain owner-required governance fields only within **Governance applicability** or explicit informed user directions.

## Review mode

Review without editing the document or its sources; do not run Optimize's asset-disposition workflow merely to judge them.

1. Read the full document and establish the review baseline using **Modes and framing**: the review question, reader contract, sources, and constraints. State material assumptions and source gaps as review limitations; proceed where the available evidence permits.
2. Apply the applicable **Document standard** and **Review and verify** checks read-only. Report substantiated findings under **Communication**, distinguishing document defects from policy-fit choices.

## Review and verify

Shared verification for all three modes; Create and Optimize use it as an exit gate, while Review reports the findings without making changes.

1. For high-risk work, give verification to a reviewer other than the producer, capable enough for the document's domain and risk, when one is available.
2. When author-reviewer separation is required, keep the independent review read-only and return requested changes to the author or editor. Let the accountable owner or a designated adjudicator who did not produce the work resolve disagreements independently; a producer's self-report is not verification.
3. Programmatically check every applicable deterministic constraint: declared lengths or counts, protected-asset inventory and byte identity, diagram rendering, target-format validity, prohibited patterns, terminology cleanup, identifier and evidence-citation existence, and diff hygiene.
4. Use semantic review for truth, authority, decision quality, evidence, and reader fit. Deterministic checks cannot establish those qualities, and semantic confidence cannot replace a failing hard check.
5. Confirm that the document has no section-jump internal links. Verify that every figure, table, attachment, evidence citation to an externally published source, and self-reported quantity resolves to real content. Report checks that could not run.

## Language and terminology boundary

Keep the owner-specified target language, register, and terminology scheme consistent while applying the authoritative-definition and identifier-fidelity rules for truth and authority. Sentence-level word choice, phrasing, naturalness, and register are outside this skill's scope. Within this skill, enforce only the document-level constraints and the term rules of the hard prohibitions: no coined vocabulary, no context-bound terms, stable concept names across headings, tables, and every repeated mention, and byte-exact identifiers, numbers, and quoted contracts.

## Communication

**Create mode** — deliver the document, then summarize: the reader contract and path chosen, the authorities each major claim rests on, open questions registered instead of answered, which checks ran, what remains uncertain, and the result against any success criteria set for the task.

**Optimize mode** — edit directly, then summarize what was reorganized, what remained unchanged to preserve truth, what was removed or deduplicated, how protected content was accounted for, which evidence or actionability gaps improved, which checks ran, what ambiguity remains, and the result against any success criteria set for the task.

**Review mode** — report findings first, ordered by consequence and the priority order. Identify each finding's area: truth and authority, scope and reader path, decisions and evidence, abstraction and registry placement, actionability and governance, or presentation. Give its location, triggering condition, consequence, supporting text or source or failed check, confidence and uncertainty, and concrete direction for resolution. Distinguish blocking defects, suggestions, and policy-fit issues that need an owner decision; do not report a possible consequence as an observed failure. Then state review scope, checks run or unavailable, and remaining limitations. If no findings are substantiated, say so within that scope.

## Self-check

For Create and Optimize, check the delivered document; for Review, check coverage and findings without implying that defects were fixed. Report unresolved failures and checks that could not run.

Shared:

- Did the work follow the priority order and apply every owner-required or high-risk control, with explicit reasons for important exclusions?
- Are current state, intended state, assumptions, unknowns, and source conflicts distinguishable?
- Does the title, section order, abstraction boundary, and audience path support the reader contract?
- Does the document read cleanly top to bottom, with needed definitions established before first use or in place?
- Does each definition and decision have one authoritative location, and are decision narrative, registries, and operational detail still separated?
- Does each important claim retain the available, applicable mechanism, evidence, and limitations, with missing links flagged, sourced alternatives and known risks where relevant, and complete action requirements where readers must act?
- Did applicable deterministic checks and renderers pass, with failures or unavailable checks and their consequences reported without claiming verification?
- Is the document free of internal contradictions, duplicate rules, editor-process residue, and project- or task-specific assumptions that the owner did not request?
- Do the eight document policies hold with their stated exceptions, or is a departure grounded in explicit informed user direction within its scope? Were unresolved conflicts held without destroying protected meaning or syntax, while independent safe work continued?

Create only:

- Does every claim rest on an authority appropriate to its claim type, with genuine gaps registered as open questions rather than answered by invention?

Optimize only:

- Is source meaning preserved except for substantive changes explicitly requested by the user or corrections justified by the appropriate claim-type authority and reported, with no silent change to numbers, contracts, conditional direction, or decisions?
- Did the accounting scope match the edit's risks, with every inventoried passage or asset's disposition verified and its fields, conditions, and protected baselines intact or changed under the required authorization and checks?

Review only:

- Did the document and sources remain unchanged, and are the findings prioritized, actionable, bounded by the available evidence, and distinct from policy-fit choices, with scope and limitations stated?
