---
name: document-editor
description: >-
  Create, edit, and review formal human-facing documents in any language while
  preserving meaning. Use when drafting, editing, or reviewing design docs,
  RFCs, plans, proposals, specs, research reports, guides, decision memos,
  formal notices, or formal wording and translations, including inline
  documents and documents within larger tasks. Do not use for mechanical
  extraction, reformatting, or list generation when wording and organization
  are prescribed and no editorial judgment is needed; ordinary chat, casual
  notes or creative writing, routine
  status updates, code implementation, or agent-instruction files such as
  SKILL.md, prompts, workflows, or tool-routing docs.
---

# Document Editor

Create, edit, and review formal human-facing documents so readers can find, understand, judge, and use what they need. Apply the same method to a long report, a short formal notice, or formal sentence and translation cleanup, in files or inline and within larger tasks. Rough notes may supply source material; the intended deliverable determines scope. Prioritize **truth and authority → reader contract and scope → decisions and evidence → abstraction and structure → completeness and actionability → clear expression and concision**.

## 1. Frame the work

Choose the authorized mode, then apply the five passes with the controls relevant to the document:

- **Create** — author from authoritative sources. Gather the sources before drafting; do not invent claims or a current state. No pre-existing document means no preservation inventory is needed.
- **Optimize** — edit an existing document, including wording or translation. Read the full document before editing, record its current section order as a compact outline unless the bounded local-edit conditions in **Preserve structured assets** apply, and establish the required accounting before changing content. Every change must follow a quality rule or an explicit user request. If the owner requires a pre-edit approval gate, present the mapping at that gate.
- **Review** — read the full document and judge it without editing the document or its sources. Establish the review question and evidence baseline. Do not run Optimize's asset-disposition workflow merely to judge a document; state material assumptions and source gaps as review limitations and proceed where the evidence permits.

Scale effort and reporting to the task's risk and scope. A short formal passage may need only a mental pass and brief local-edit notes; retain the full-document read and every applicable format, contract, asset, governance, and verification check. Resolve truth issues as soon as they are found. For an edit, diagnose dependencies from authority and scope through reader contract, bottleneck, section order, evidence, abstraction, action path, accuracy, duplication, and presentation.

1. **Reader contract.** Identify the document type, audience, purpose, target language, register, voice, abstraction level, and decision or action it promises to support from the request, sources, and destination. Establish the bottleneck, failure mode, or uncertainty it resolves, what readers already know, and the context they need.
2. **Authorities and constraints.** Identify the sources appropriate to each claim type, owner and format constraints, required content slots, governance state, content protected exactly or structurally, and task scope or success criteria. Treat owner-defined length and structural budgets as constraints; if a change is necessary, expose the content-level cause and follow the owner's approval process. Apply only controls relevant to the document type and its real governance; record an explicit not-applicable reason for excluding a required or high-risk control. State material assumptions and missing information rather than inventing the frame; proceed where they do not block accurate work.
3. **Policy fit.** Check the **Document policies** and **Governance applicability** against the document's required navigation, records, templates, and syntax. These are this skill's document policies, not universal measures of document quality. A legitimate reader task or lifecycle can be incompatible with them; report that as a policy-fit issue rather than a general quality defect. Semantic headings and established concept names remain available for navigation.
4. **Conflict and continuation.** Use known lifecycle facts and user decisions. If a policy conflict remains unresolved, name it and ask only for the missing decision about applicability, an authorized alternative, or delivery scope. Hold the conflicting change and continue independent safe work. Follow explicit informed user directions as higher-priority instructions within their stated scope, then resume without requesting the same decision again. A governance request or template protection marker alone does not waive other policies. Do not delete protected content or break required syntax to obtain compliance. Before relocating protected governance records out of the document, verify a compatible authorized destination; if none exists, leave the disputed content intact and surface the incompatibility.

### Governance applicability

Apply this section to document-governance apparatus, distinguishing it from domain facts and action owners. Resolve conflicts under **1. Frame the work**.

1. Governance apparatus requires a real, external publication or approval lifecycle. Under this policy, an unpublished repository working document read only by repository collaborators carries no signature fields, lifecycle labels, or status or owner fields; its opening holds only what a reader needs to use the content. When governance fields are requested and the lifecycle is unknown, establish whether that external lifecycle exists before adding them.
2. Only when the owner explicitly mandates governance for a document with a genuine external lifecycle, provide only the non-revision metadata the owner requests from this set: status, accountable owner, approver, and approval date. Governance authorization does not waive any hard prohibition. Revision dates, change histories, and re-review narratives remain excluded; process traces belong in an external governance system.
3. Follow the document's real lifecycle rather than inventing one. Attribute approval only when it exists, return materially changed approved content to the appropriate review state, and record the true reason for re-review in the external lifecycle system.
4. Review history, consequential dissent, and lifecycle evidence belong in an external governance system; the edited document never carries them.

### Document policies

Apply these eight policies throughout the task, with their stated exceptions and the instruction scope resolved under **1. Frame the work**.

1. **No patch-style updates.** Never leave update residue: no addenda, errata, changelogs, revision histories, or correction notes, and no "updated" markers, "as of" notes, or before-vs-after narration that describe a change to the document. Fold every change into the owning passage so the document always reads as if written correct the first time. A date that bounds when a claim holds — a measurement date, data snapshot, or the evaluated version — is evidence and stays next to the claim.
2. **No deferral to other documents.** Never offload content readers need to another document in the same working set — the documents being authored or edited together in this task — through companion-volume pointers, document maps, or directions such as "see the implementation document." The document carries what its reader needs and omits the rest. Naming an approved source as the authority for a claim is not deferral when the document also states the content the reader needs. Evidence citations to externally published sources in research reports establish attribution and are not deferral; retain them.
3. **No cross-references between sections.** No "see chapter 6", "as described above/below", table of contents, or forward/backward pointers. Order sections so each is understandable where it stands; when another section's fact is needed, restate the minimum inline without naming the section.
4. **Prefer titled bullets over paragraphs.** When one to five parallel, independent points suffice, present them as bullet points, each opening with a clear and precise title, rather than paragraph prose. A causal chain or reasoning in which each sentence depends on the one before stays prose.
5. **No unnecessary table columns.** Every column must carry decision-relevant information that varies across rows; drop or merge any column that repeats another, restates the row label, or exists only for symmetry.
6. **No coined vocabulary or jargon.** Use plain words and terms established in the field or in the source material; never invent labels, metaphors, or shorthand names for the document's own concepts.
7. **No direct code references.** Never cite class, method, function, or variable names, file paths, or line numbers in the document. Describe the behavior in business or domain terms instead. Identifiers that are part of the subject's own contract, or that the reader must type or locate to act, stay byte-exact. These include table and field names, status enums, API fields, and the commands, configuration keys, and file paths that a step tells the reader to run, set, or open, as in a runbook, a setup path, or the steps of an implementation plan.
8. **No context-bound terms from other sections or documents.** Never use a term, code, or label whose meaning is established only in another section or another document — a bare error code, an internal task name, an abbreviation defined elsewhere. State the fact in plain wording in place; keep such a code only where the document itself establishes what it means.

## 2. Ground claims and preserve meaning

### Claim-type authority

1. Determine authority per claim type. Use implementation or observed behavior for current state, approved requirements or decisions for intended state, and direct observations or primary studies for measured outcomes. Do not apply one global source hierarchy across claim types.
2. When sources disagree, inspect the conflict, use the best-supported claim, and record any difference that affects scope, accuracy, or a decision. Do not choose a source merely because it appears in a preferred category.
3. Distinguish the observed current state, the approved or proposed target state, assumptions, and the gap between them. Do not describe or design against an invented current state.
4. Explain any departure from an established decision and preserve its authorization boundary. Writing or editing authority alone does not authorize a new decision.
5. Flag ambiguity, inconsistency, or missing evidence. Tighten wording noise, not substantive meaning.

### Meaning and authorization

In Optimize, preserve the source's meaning, facts, scope, and decisions unless the user explicitly requests a substantive change or the appropriate claim-type authority shows a stated fact is wrong. Correct a source-backed factual error and report the correction. Treat a change to needed meaning or function as substantive, including changes made through shortening or translation.

Preserve numbers, units, dates, owners, names, identifiers, field and API contracts, formulas, requirements, conditions, exceptions, scope limits, uncertainty, citations, and quoted contracts. Keep conditional direction and normative force exact: “may,” “should,” and “must” express different permissions and obligations. In procedural documents, preserve triggers, ordering dependencies, branches, tool arguments, and completion conditions. Do not silently change any of these.

### Unknowns, branches, and decisions

1. For a blocking unknown with no established default, record the question, why it is unresolved, the authority or resolver needed, known candidate space, affected decisions or passages, timing or trigger when relevant, and the consequence of remaining unresolved. State a fallback only when a source establishes one.
2. For a branch with an established default, state the default, alternatives, and the criterion that selects among them. Mark confirmation as open without presenting the default as newly invented.
3. Keep each open question independently answerable. When choices must be decided together, present a mutually exclusive and collectively complete decision package; include an explicit unknown or escalation branch when the candidate space is not closed.
4. Never turn an unanswered question into a design conclusion. If the missing answer prevents accurate prose, leave a governed placeholder or registry entry and identify what it blocks.

### Preserve structured assets

Keep content and asset mappings only in the editing-session record (working notes and summary to the user), an external approval record, or an owner-named file outside the document's repository; never put a mapping in the document or any other file in its repository. Keep protected-baseline measurements, required authorizations, and protected-asset change reasons and bases in the editing-session record or external approval record, never in the edited document.

1. Set the accounting scope before editing. For a loss-sensitive restructure, split, or compression, inventory the complete affected content and load-bearing assets: decisions, open questions and blockers, conditional branch tables, tradeoff matrices, invariants, non-goals, risks, rollout batches, diagrams, exact contracts, error catalogs, and critical checklists, as applicable. For another edit that touches a load-bearing or protected asset, inventory that asset and its dependencies. A bounded local edit that leaves these assets, protected records, and their relationships untouched needs only brief notes identifying the affected passages and checked dependencies, rather than an outline and dispositions for untouched content. Retain the full-document read and every applicable format, contract, asset, and verification check. If scope or preservation is uncertain, use the complete affected inventory and mapping; expand it before proceeding when the edit grows.
2. Preserve existing diagrams, images, videos, code blocks, callouts, evidence citations, and other native blocks unless the user requests a change or a source-backed edit requires one.
3. Give every inventoried passage or asset a disposition: preserved in place, moved to a named destination, merged into a named authoritative item, or intentionally removed with a reason and the required authorization. Do not use compression as an unreported deletion path.
4. Extend the relocation discipline for registries to every inventoried asset, not only registry entries. Treat conversion to a table or movement to an appendix as relocation under that discipline.
5. Treat exact schemas, interface signatures, identifiers, error definitions, and other contract artifacts as deliverables in their own right. Preserve their completeness and exactness even when surrounding explanation is condensed.
6. Treat an asset's item count or byte identity as a protected baseline only when the owner or delivery format defines it. For a controlled baseline change, record the pre-change and post-change values and any required authorization; never change the baseline silently.
7. When byte-for-byte identity is required, use the configured checksum or comparison method. Do not modify a protected diagram or native asset without authorization; after an authorized change, record its reason and basis and apply the required rendering or behavior checks.
8. Resolve protected-content conflicts under **1. Frame the work**. Apply **Document policies** and **Governance applicability** within the resolved scope.

## 3. Organize for the reader

For Create, outline from the reader's task before drafting and check that each concept is established before use or defined in place. For Optimize, repair the structure within the established accounting scope. In Review, assess the same requirements read-only. Apply the following standards at the depth the reader contract needs.

### Forward reading order

Order content for a single top-down read: establish each concept or fact before it is needed, or explain it in place. A passage that requires later material to be understood is a structural defect whether or not an explicit reference marks it. Where understanding requires later material, move the defining material ahead of its first use or restate the minimum context in place. Verify the result in **5. Verify and deliver**.

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

Keep these layers distinct. Move definitions earlier and implementation later unless the document is explicitly implementation-focused.

- **Definition layer:** goals, domain semantics, responsibility boundaries, conceptual models, invariants, and decision criteria.
- **Implementation layer:** exact contracts, validation and error behavior, persistence and migration rules, algorithms, operational procedures, observability, permissions, and rollout changes.

Keep high-level design focused on decisions, boundaries, semantics, tradeoffs, compatibility, consistency, rollout strategy, and risk. Retain implementation detail only when it helps the intended reader judge feasibility, constraints, reliability, or tradeoffs.

When a document set splits material across volumes, apply the same layer boundaries and let each document independently fulfill its reader contract.

### Definitions and authoritative locations

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

## 4. Prune by function and clarify expression

Give each passage and phrase a job in the reader's understanding, decision, or action. Ask what the reader would lose if it were removed. Remove filler, empty framing, irrelevant detail, and repetition with no distinct function; do not treat a shorter result as sufficient evidence of a better one. Merge overlaps into their authoritative owning passage while retaining every distinct condition, reason, and qualification. Update affected references and integrate changes without patch residue. A change that removes needed meaning or function follows **Meaning and authorization**.

Judge repetition by function, not matching words. Within **Document policies**, **Definitions and authoritative locations**, and **Registries vs decision narrative**, retain the minimum summary, local warning, context, or worked explanation needed for a distinct reading path, safety, or learning. For example, a runbook may repeat “Disconnect power before opening the cover” before each procedure that can be followed independently. Preserve required records under the resolved policy and governance scope; useful repetition does not create an exception for otherwise forbidden navigation or history.

Use natural, precise wording and syntax in the target language, register, and terminology scheme. Simplify overloaded sentences and make actors, actions, and relationships clear without supplying facts the sources do not establish. Preserve purposeful voice and tone. Keep established concept names consistent across headings, tables, and repeated mentions; explain unfamiliar terms in place without paraphrasing exact identifiers. Use prose for connected reasoning, steps for ordered actions, and tables for comparable attributes under the representation rules in **3. Organize for the reader**. Wording and translation changes remain subject to **Meaning and authorization**.

## 5. Verify and deliver

Use this pass as the exit gate for Create and Optimize; in Review, report findings without making changes. Read the whole result top to bottom as a first-time intended reader, then follow each relevant decision or action path. Check that readers can find what they need, understand relationships, and complete the task. Recheck transitions and references after structural changes. Compare drafts with their sources and requirements, and edits with the source document for lost distinctions, altered claims or normative force, changed conditions, and unintended shifts of voice. Verify every inventoried passage or asset's disposition and preservation requirements. Check for internal contradictions, duplicate rules, editor-process residue, and project- or task-specific assumptions the owner did not request.

1. For high-risk work, give verification to a reviewer other than the producer, capable enough for the document's domain and risk, when one is available.
2. When author-reviewer separation is required, keep the independent review read-only and return requested changes to the author or editor. Let the accountable owner or a designated adjudicator who did not produce the work resolve disagreements independently; a producer's self-report is not verification.
3. Programmatically check every applicable deterministic constraint: declared lengths or counts, protected-asset inventory and byte identity, diagram rendering, target-format validity, prohibited patterns, terminology cleanup, identifier and evidence-citation existence, and diff hygiene.
4. Use semantic review for truth, authority, decision quality, evidence, and reader fit. Deterministic checks cannot establish those qualities, and semantic confidence cannot replace a failing hard check.
5. Confirm that the document has no section-jump internal links. Verify that every figure, table, attachment, evidence citation to an externally published source, and self-reported quantity resolves to real content. Report checks that could not run.

### Delivery

Honor the requested output format, including document-only or inline output. Fit the mode-specific account to the request and task size; a short wording edit needs no unnecessary editorial report. Keep editorial change accounts and verification reports outside the document; substantive uncertainties stay with the claims they qualify. Disclose material substantive changes, source corrections, unresolved ambiguities, and failed or unavailable checks without adding routine commentary to document-only output. If a blocking issue prevents faithful delivery in the requested form, surface it rather than claiming completion.

**Create** — deliver the document, then summarize: the reader contract and path chosen, the authorities each major claim rests on, open questions registered instead of answered, which checks ran, what remains uncertain, and the result against any success criteria set for the task.

**Optimize** — deliver the authorized edits, then summarize what was reorganized, what remained unchanged to preserve truth, what was removed or deduplicated, how protected content was accounted for, which evidence or actionability gaps improved, which checks ran, what ambiguity remains, and the result against any success criteria set for the task.

**Review** — report findings first, ordered by consequence and the priority order. Identify each finding's area: truth and authority, scope and reader path, decisions and evidence, abstraction and registry placement, actionability and governance, or presentation. Give its location, triggering condition, consequence, supporting text or source or failed check, confidence and uncertainty, and concrete direction for resolution. Distinguish blocking defects, suggestions, and policy-fit issues that need an owner decision; do not report a possible consequence as an observed failure. Then state review scope, checks run or unavailable, and remaining limitations. If no findings are substantiated, say so within that scope.

## Self-check

For Create and Optimize, check the delivered document; for Review, check coverage and findings without implying that defects were fixed. Report unresolved failures and checks that could not run.

- **Framing and policy:** Did pass 1 follow the priority order, authorized mode, reader contract, constraints, and risk, with explicit reasons for excluding required or high-risk controls? For Review, did the document and sources remain unchanged? Do the eight policies and governance rules hold with their stated exceptions or explicit informed user direction? Were unresolved conflicts held without destroying protected content or syntax while independent safe work continued?
- **Authority and meaning:** Does pass 2 distinguish current state, target state, assumptions, unknowns, defaults, and source conflicts, using the appropriate authority for each claim type? Are decisions, permissions, conditions, and exact details preserved unless a substantive change was authorized or a source-backed factual correction was made and reported?
- **Accounting:** For Optimize, did pass 2's accounting scope match the edit's risk, with every inventoried passage or asset accounted for and protected fields, relationships, and baselines preserved or changed under the required authorization and checks?
- **Reader path:** Does pass 3 support a forward read at the right abstraction and depth, with authoritative definitions, distinct narrative and registry layers, complete evidence and action paths, and suitable tables, diagrams, and technical forms?
- **Function and expression:** Did pass 4 remove dispensable content, retain purposeful local repetition within the policies, and integrate distinct meaning coherently, with any removal of needed meaning or function handled under **Meaning and authorization**? Is the language natural and precise, with consistent terms and preserved voice, meaning, and force?
- **Verification and delivery:** Did pass 5 check the whole result against sources and requirements, including contradictions, duplicate rules, process residue, and unrequested assumptions, complete applicable semantic and deterministic checks, and disclose limitations without claiming unperformed verification? Does delivery follow the requested format with the appropriate mode-specific account or prioritized, substantiated Review findings?
