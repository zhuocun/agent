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

## Standing rules

### Modes

Choose the authorized mode, then apply the five passes:

- **Create** — author from authoritative sources. Gather the sources before drafting; do not invent claims or a current state. No pre-existing document means no preservation inventory is needed.
- **Optimize** — edit an existing document, including wording or translation. Read the full document before editing, record its current section order as a compact outline unless the bounded local-edit conditions in **Accounting scope** (`references/structured-assets.md`; read it in full before the first edit, and again after a context compaction) apply, and establish the required accounting before changing content. Every change must follow a quality rule or an explicit user request. If the owner requires a pre-edit approval gate, present the mapping — each inventoried passage or asset with its planned disposition — at that gate.
- **Review** — read the full document and judge it without editing the document or its sources. Establish the review question and evidence baseline. Do not run Optimize's asset-disposition workflow merely to judge a document; state material assumptions and source gaps as review limitations and proceed where the evidence permits.

### Document policies

Apply these policies throughout the task, with their stated exceptions and the instruction scope resolved under **Conflict and continuation**.

1. **No patch-style updates.** Never leave update residue: no addenda, errata, changelogs, revision histories, or correction notes, and no "updated" markers, "as of" notes, or before-vs-after narration that describe a change to the document. Fold every change into the owning passage so the document always reads as if written correct the first time. A date that bounds when a claim holds — a measurement date, data snapshot, or the evaluated version — is evidence and stays next to the claim.
2. **No deferral to other documents.** Never offload content readers need to another document in the same working set — the documents being authored or edited together in this task — through companion-volume pointers, document maps, or directions such as "see the implementation document." The document carries what its reader needs and omits the rest. Naming an approved source as the authority for a claim is not deferral when the document also states the content the reader needs. Evidence citations to externally published sources in research reports establish attribution and are not deferral; retain them.
3. **No cross-references between sections.** No "see chapter 6", "as described above/below", table of contents, or forward/backward pointers. Order sections so each is understandable where it stands; when another section's fact is needed, restate the minimum inline without naming the section.
4. **Prefer titled bullets over paragraphs.** When one to five parallel, independent points suffice, present them as bullet points, each opening with a clear and precise title, rather than paragraph prose. A causal chain or reasoning in which each sentence depends on the one before stays prose.
5. **No unnecessary table columns.** Every column must carry decision-relevant information that varies across rows; drop or merge any column that repeats another, restates the row label, or exists only for symmetry.
6. **No coined vocabulary or jargon.** Use plain words and terms established in the field or in the source material; never invent labels, metaphors, or shorthand names for the document's own concepts.
7. **No direct code references.** Never cite class, method, function, or variable names, file paths, or line numbers in the document. Describe the behavior in business or domain terms instead. Identifiers that are part of the subject's own contract, or that the reader must type or locate to act, stay byte-exact. These include table and field names, status enums, API fields, and the commands, configuration keys, and file paths that a step tells the reader to run, set, or open, as in a runbook, a setup path, or the steps of an implementation plan.
8. **No context-bound terms from other sections or documents.** Never use a term, code, or label whose meaning is established only in another section or another document — a bare error code, an internal task name, an abbreviation defined elsewhere. State the fact in plain wording in place; keep such a code only where the document itself establishes what it means.

### Meaning and authorization

In Optimize, preserve the source's meaning, facts, scope, and decisions unless the user explicitly requests a substantive change or the appropriate claim-type authority shows a stated fact is wrong. Correct a source-backed factual error and report the correction. Treat a change to needed meaning or function as substantive, including changes made through shortening or translation.

Preserve numbers, units, dates, owners, names, identifiers, field and API contracts, formulas, requirements, conditions, exceptions, scope limits, uncertainty, citations, and quoted contracts. Keep conditional direction and normative force exact: “may,” “should,” and “must” express different permissions and obligations. In procedural documents, preserve triggers, ordering dependencies, branches, tool arguments, and completion conditions. Do not silently change any of these.

### Conflict and continuation

Use known lifecycle facts and user decisions. If a policy conflict remains unresolved, name it and ask only for the missing decision about applicability, an authorized alternative, or delivery scope. Hold the conflicting change and continue independent safe work. Follow explicit informed user directions as higher-priority instructions within their stated scope, then resume without requesting the same decision again. A governance request or template protection marker alone does not waive other policies. Do not delete protected content or break required syntax to obtain compliance. Before relocating protected governance records out of the document, verify a compatible authorized destination; if none exists, leave the disputed content intact and surface the incompatibility.

## Reference files

Read each file in this list in full when its condition first holds, before applying any of its rules, and again after a context compaction before applying them next.

- `references/governance.md` (**Governance applicability**): before you add, keep, remove, or judge any signature, approval, status, owner, lifecycle, revision, or history field, and whenever a request asks for governance fields.
- `references/structured-assets.md` (**Accounting scope**): in Optimize, before the first edit.
- `references/decisions-and-evidence.md` (**Unknowns, branches, and decisions**; **Registries vs decision narrative**): when the document has an unresolved question, unknown, default, or branch; states, proposes, or compares decisions, recommendations, or options; makes research, measurement, or improvement claims; keeps an open-issue, blocker, or verification ledger; or tells readers how to act on or adopt something.
- `references/structure-and-navigation.md` (**Definitions and authoritative locations**): when you outline a document; set, change, or judge its title, headings, or section order; separate its definition and implementation material; or split material across documents.
- `references/tables-diagrams-and-code.md` (**Tables, diagrams, media, and code**): when the document has or needs a table, diagram, image, video, code block, callout, or structured technical form such as a schema, data or protocol example, pseudocode, decision tree, or scenario, or when you convert content between prose, steps, tables, and diagrams.
- `references/independent-review.md` (**Independent review**): for high-risk work, and whenever author-reviewer separation is required.

## 1. Frame the work

Scale effort and reporting to the task's risk and scope. A short formal passage may need only a mental pass and brief local-edit notes. At every scale, retain the full-document read and every applicable format, contract, asset, governance, and verification check. Resolve truth issues as soon as they are found. For an edit, diagnose dependencies from authority and scope through reader contract, bottleneck, section order, evidence, abstraction, action path, accuracy, duplication, and presentation.

1. **Reader contract.** Identify the document type, audience, purpose, target language, register, voice, abstraction level, and decision or action it promises to support from the request, sources, and destination. Establish the bottleneck, failure mode, or uncertainty it resolves, what readers already know, and the context they need.
2. **Authorities and constraints.** Identify the sources appropriate to each claim type, owner and format constraints, required content slots, governance state, content protected exactly or structurally, and task scope or success criteria. Treat owner-defined length and structural budgets as constraints; if a change is necessary, expose the content-level cause and follow the owner's approval process. Apply only the checks relevant to the document type and its real governance; record an explicit not-applicable reason for skipping a check the owner requires or one that guards high-risk content. State material assumptions and missing information rather than inventing the frame; proceed where they do not block accurate work.
3. **Policy fit.** Check the **Document policies** and **Governance applicability** against the document's required navigation, records, templates, and syntax. These are this skill's document policies, not universal measures of document quality. A legitimate reader task or lifecycle can be incompatible with them; report that as a policy-fit issue rather than a general quality defect. Semantic headings and established concept names remain available for navigation.

## 2. Ground claims and preserve meaning

### Claim-type authority

1. Determine authority per claim type. Use implementation or observed behavior for current state, approved requirements or decisions for intended state, and direct observations or primary studies for measured outcomes. Do not apply one global source hierarchy across claim types.
2. When sources disagree, inspect the conflict, use the best-supported claim, and record any difference that affects scope, accuracy, or a decision. Do not choose a source merely because it appears in a preferred category.
3. Distinguish the observed current state, the approved or proposed target state, assumptions, and the gap between them. Do not describe or design against an invented current state.
4. Explain any departure from an established decision and preserve its authorization boundary. Writing or editing authority alone does not authorize a new decision.
5. Flag ambiguity, inconsistency, or missing evidence. Tighten wording noise, not substantive meaning.

## 3. Organize for the reader

For Create, outline from the reader's task before drafting and check that each concept is established before use or defined in place. For Optimize, repair the structure within the established accounting scope. In Review, assess the same requirements read-only. Apply this pass's standards, held in `references/structure-and-navigation.md`, `references/decisions-and-evidence.md` and `references/tables-diagrams-and-code.md`, at the depth the reader contract needs; read each file in full when its condition in **Reference files** holds, and again after a context compaction.

## 4. Prune by function and clarify expression

Give each passage and phrase a job in the reader's understanding, decision, or action. Ask what the reader would lose if it were removed. Remove filler, empty framing, irrelevant detail, and repetition with no distinct function; do not treat a shorter result as sufficient evidence of a better one. Merge overlaps into their authoritative owning passage while retaining every distinct condition, reason, and qualification. Update affected references and integrate changes without update residue. A change that removes needed meaning or function follows **Meaning and authorization**.

Judge repetition by function, not matching words. Within **Document policies**, **Definitions and authoritative locations**, and **Registries vs decision narrative**, retain the minimum summary, local warning, context, or worked explanation needed for a distinct reading path, safety, or learning. For example, a runbook may repeat “Disconnect power before opening the cover” before each procedure that can be followed independently. Preserve required records under the resolved policy and governance scope; useful repetition does not create an exception for otherwise forbidden navigation or history.

Use natural, precise wording and syntax in the target language, register, and terminology scheme. Simplify overloaded sentences and make actors, actions, and relationships clear without supplying facts the sources do not establish. Preserve purposeful voice and tone. Keep established concept names consistent across headings, tables, and repeated mentions; explain unfamiliar terms in place without paraphrasing exact identifiers. Use prose for connected reasoning, steps for ordered actions, and tables for comparable attributes under the representation rules in **Tables, diagrams, media, and code**. Wording and translation changes remain subject to **Meaning and authorization**.

## 5. Verify and deliver

Use this pass as the exit gate for Create and Optimize; in Review, report findings without making changes. Read the whole result top to bottom as a first-time intended reader, then follow each relevant decision or action path. Check that readers can find what they need, understand relationships, and complete the task. Recheck transitions and references after structural changes. Compare drafts with their sources and requirements, and edits with the source document for lost distinctions, altered claims or normative force, changed conditions, and unintended shifts of voice. Verify every inventoried passage or asset's disposition and preservation requirements. Check for internal contradictions, duplicate rules, editor-process residue, and project- or task-specific assumptions the owner did not request.

1. Programmatically check every applicable deterministic constraint: declared lengths or counts, protected-asset inventory and byte identity, diagram rendering, target-format validity, prohibited patterns, terminology cleanup, identifier and evidence-citation existence, and diff hygiene.
2. Use semantic review for truth, authority, decision quality, evidence, and reader fit. Deterministic checks cannot establish those qualities, and semantic confidence cannot replace a failing hard check.
3. Confirm that the document has no section-jump internal links. Verify that every figure, table, attachment, evidence citation to an externally published source, and self-reported quantity resolves to real content.

### Delivery

Honor the output format that the request, the user's standing preferences, or another applicable instruction sets, including document-only output, inline output, or a form with fixed slots. Keep editorial change accounts and verification reports outside the document; substantive uncertainties stay with the claims they qualify. Disclose material substantive changes, source corrections, unresolved ambiguities, and failed or unavailable checks in every format, without adding routine commentary to document-only output. Fit the rest of the mode-specific account to that format and the task size; a short wording edit needs no unnecessary editorial report. If a blocking issue prevents faithful delivery in that format, surface it rather than claiming completion.

**Create** — deliver the document, then summarize: the reader contract and path chosen, the authorities each major claim rests on, open questions registered instead of answered, which checks ran, what remains uncertain, and the result against any success criteria set for the task.

**Optimize** — deliver the authorized edits, then summarize what was reorganized, what remained unchanged to preserve truth, what was removed or deduplicated, how protected content was accounted for, which evidence or actionability gaps improved, which checks ran, what ambiguity remains, and the result against any success criteria set for the task.

**Review** — report findings first, ordered by consequence and the priority order. Identify each finding's area: truth and authority, scope and reader path, decisions and evidence, abstraction and registry placement, actionability and governance, or presentation. Give its location, triggering condition, consequence, supporting text or source or failed check, confidence and uncertainty, and concrete direction for resolution. Distinguish blocking defects, suggestions, and policy-fit issues that need an owner decision; do not report a possible consequence as an observed failure. Then state review scope, checks run or unavailable, and remaining limitations. If no findings are substantiated, say so within that scope.

## Self-check

For Create and Optimize, check the delivered document; for Review, check coverage and findings without implying that defects were fixed. Report unresolved failures and checks that could not run.

- **Framing and policy:** Did the work follow the priority order and the authorized mode, and did pass 1 cover the reader contract, constraints, and risk, with an explicit not-applicable reason for each skipped check that the owner requires or that guards high-risk content? For Review, did the document and sources remain unchanged? Was each reference file read in full when its condition first held, before any of its rules were applied, and again after any context compaction before they were next applied? Do the **Document policies** and governance rules hold with their stated exceptions or explicit informed user direction? Were unresolved conflicts held without destroying protected content or syntax while independent safe work continued?
- **Authority and meaning:** Do pass 2 and **Unknowns, branches, and decisions** distinguish current state, target state, assumptions, unknowns, defaults, and source conflicts, using the appropriate authority for each claim type? Are decisions, permissions, conditions, and exact details preserved unless a substantive change was authorized or a source-backed factual correction was made and reported?
- **Accounting:** For Optimize, did the **Accounting scope** match the edit's risk, with every inventoried passage or asset accounted for and protected fields, relationships, and baselines preserved or changed under the required authorization and checks?
- **Reader path:** Does pass 3 support a forward read at the right abstraction and depth, with authoritative definitions, distinct narrative and registry layers, complete evidence and action paths, and suitable tables, diagrams, and technical forms?
- **Function and expression:** Did pass 4 remove dispensable content, retain purposeful local repetition within the policies, and integrate distinct meaning coherently, with any removal of needed meaning or function handled under **Meaning and authorization**? Is the language natural and precise, with consistent terms and preserved voice, meaning, and force?
- **Verification and delivery:** Did pass 5 check the whole result against sources and requirements, including contradictions, duplicate rules, editor-process residue, and unrequested assumptions, complete applicable semantic and deterministic checks, and disclose limitations without claiming unperformed verification? Does delivery follow the output format that the request, the user's standing preferences, or another applicable instruction sets, with the required disclosures and the appropriate mode-specific account or prioritized, substantiated Review findings? For high-risk work or required author-reviewer separation, did verification follow **Independent review**?
