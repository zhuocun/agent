---
name: govern-agent-docs
description: >-
  Set up, audit or reorganise repository guidance for agents
  (仓库指引、文档治理、文档分类、入口路由). Use when designing guidance,
  classifying a guidance document or section, changing the entry structure
  or routing scheme, or reviewing documentation against governance rules,
  including memory migration within that work. Do not use for routine
  capture, verification or correction of specific durable memory entries,
  including the entry-file and index updates those entries require. Do
  not use for task progress, prose editing, writing or reviewing code
  rules themselves, or human-only material.
---

# Govern Agent Docs

Keep a repository's agent-facing guidance classified, findable and consistent, so that an executor starting a fresh session finds every rule that binds its task, applies one authority order, and never acts on stale or duplicated text.

Apply **Host controls** first. Resolve conflicts between applicable clauses by **Apply the authority order**.

## Standing rules

- **Roles.** The owner is the person with authority over the repository's scope, rules and exemptions. A maintainer is the person the owner names to maintain a document or a class of documents. The executor is the agent or person doing the task.
- **Scope.** Govern only content that guides an agent's judgement or action, judged by its function. When the owner or an existing authority has designated a human-facing or external document as the canonical source of a contract, cite the relevant section directly. Pure introductions, delivery covers and release metadata are out of scope. Attach a generated artefact to the contract or evidence it serves, with its source noted.
- **Host controls.** Permissions, sandboxes, hooks, and the code host's branch protection and required checks stand outside the authority order. No written or chat instruction overrides a failing host control. When you believe a control is wrong, stop the affected action and change the control through its own change path.
- **Approval.** The owner approves principles and methodology, the authority order, hard constraints, project decisions and authorisations, exemptions, incompatible changes to external contracts, and host controls. The maintainer of the content approves other ordinary text. An explicit approval already given for the same text and scope stands. The executor may propose changes, record approvals already given and update its own task's progress.
- **What no document or memory stores.** Do not store credential values, other people's private information or unredacted production data in any governed document or in either kind of memory. Do not store task progress in either kind of memory: keep task progress and one-off task, release and pipeline numbers in work state. Keep superseded content that must survive in a decision record's supersession chain or in the archive. Do not copy into memory implementation facts that can be looked up directly.
- **Memory grants nothing.** Knowledge entries, work state, archive and evidence, personal memory and delegation briefs cannot on their own grant permission or change current text.
- **Pending project content.** Use only verified and promoted content as a cross-task project rule.
- **One canonical source.** Keep one canonical source for each current rule or controlled fact. Summaries, indexes and display artefacts name their source. When an existing script or test reads a passage, name it in the canonical source. If you change the interface it reads, run the corresponding existing verification.
- **One authority order.** The entry file keeps one applicable authority order.
- **Normative wording.** Apply these rules to text written by people and agents. For requirements, defaults and permissions, use `must` or `must not`, `should`, and `may` in English, and `必须` or `不得`, `应`, and `可` in Chinese. Give the condition for departing from a default. Use `YYYY-MM-DD` or a locatable revision in fields that must be rechecked, including approval, observation and expiry.
- **Volatile state.** Use time fields in stable text to mark approval, effect, verification or review. Keep a binding expiry condition in the record it governs. Keep volatile progress, schedules, to-dos and unfinished implementation in work state; a fixed historical fact may stay in a decision basis or in evidence. A normative reference inside the repository resolves from the applicable branch to a version-controlled target.
- **Limits on checks.** Use at most the three checks of **Run the light checks** for documentation governance; a small repository may run them by hand. Add no document-length gate, natural-language parsing script or preference-blocking hook. Source verification, existing tests and platform permissions run under their own rules.

## Reference files

Read each file in full when its condition first holds, before applying its rules, and again after a context compaction while the condition holds:

- `references/type-tables.md` (what each type holds, who may change it and how it loads): before classifying or reviewing any unit's type, or deciding what a type holds, who may change it or how it loads.
- `references/skills-and-hosts.md` (skill packaging, copies, host configuration and adapters): before choosing skill packaging, placing, copying or writing a skill, writing host configuration, or adapting host access to an entry file or skill.
- `references/memory-entries.md` (destinations, capture, promotion, cleanup, layout and staleness of memory entries): before assigning a destination to memory content or placing, routing, writing, verifying, migrating or reviewing decision records or knowledge entries.
- `references/adoption.md` (the steps for applying these rules to existing guidance): before applying this skill to an existing repository's guidance as a whole, or auditing or reorganising it.

## Passes

### 1. Classify each unit

Split the guidance into units that work on their own, clauses or sections, and give each the first type that matches:

1. **Host configuration:** configuration, import declarations and adapter links that a host or platform reads to change loading or execution.
2. **Entry file:** guidance that tells an executor entering a scope what it must read, the authority order and when to read. Principles, rules and commands written inline keep the type of their own function.
3. **Decision record:** an entry that keeps one long-term project ruling's content, scope, basis and force.
4. **Archive and evidence:** content kept only to consult history, or to prove an execution, verification or review that already happened. Keep to-dos, recheck results and open questions in **work state** while they still need updates.
5. **Current design and contract:** behaviour, data and acceptance results the system must present internally or externally, or a complete candidate contract under review.
6. **Principles and methodology:** principles that guide trade-offs between constraints and explain how to judge a case no rule covers. Constraints checkable item by item take step 7.
7. **Rulebook:** conditions engineering work must meet, with a cross-project general text as canonical source. **Project register:** an adoption, tightening, project-only constraint or registered approved exemption.
8. **Runbook:** reusable steps that perform one operation under fixed preconditions. Classify optional diagnostic and workaround experience as **knowledge and pitfalls**.
9. **Work state:** the goal, status, to-dos, open questions and handoff notes of a task still in progress.
10. **Knowledge and pitfalls:** a verified project finding, with its conditions of application, that the code and history do not show.

A file name, loading method, length or location never changes a unit's type. Use the following 11 types and their omission conditions:

| Type | When a small repository can omit a separate file or index |
| --- | --- |
| Entry file, with nested entries and directory index pages | Keep a repository entry file. Use **Nested entries** for per-subtree entry files. A directory index page carries the entry file's routing where present. |
| Principles and methodology | It is a few lines: write it in the entry file; the type remains, with no file of its own. |
| Rulebook | The repository adopts no cross-project rules. |
| Project register | The repository adopts no rulebook and states its project rules in one or two lines in the entry file. |
| Decision record | No cross-task decision exists and no project authorisation remains in force. The first entry may take its own section in an existing document. |
| Current design and contract | Types, interface descriptions or contract tests named as authoritative express every current contract explicitly and locatably. |
| Runbook | Omit it when there are no reusable steps. If an existing script entry point fully expresses the preconditions, actions and expected results, link it directly in place of a separate runbook. |
| Work state | The task finishes within one turn with no cross-turn to-do or handoff. |
| Knowledge and pitfalls | No reusable project finding exists; few entries may share separate sections of one file. |
| Archive and evidence | Version history supplies the evidence needed. |
| Host configuration | Every host in use reads the canonical sources and no project-level adaptation or control is needed. |

One file may hold separate sections of several types, each locatable on its own. A rule's rationale and examples, and a runbook's expected results, may share its section; independent task state, approval basis and historical evidence each take their own. Split the file when reading by section still loads much unrelated content.

### 2. Apply the authority order

Inside the **Host controls** boundary, highest first:

1. The owner's explicit instruction in the current conversation, within the task and scope it sets. Where it explicitly names the rules and scope it overrides, follow it. If later tasks need it, use **Capture, hand off, promote, clean** in `references/memory-entries.md`.
2. Hard constraints the owner explicitly approved as high priority, decisions and authorisations that take effect on their own, and exemptions registered in the project register after approval. An exemption covers only the rules, scope and period it lists.
3. Principles and methodology.
4. Ordinary local rules and tightenings in the project register.
5. The rulebook, which constrains engineering practice, and the current design and contract, which constrain system behaviour. When both apply and cannot both be met, ask the owner to decide.
6. Runbooks.

A clause's level follows its function and the scope explicitly approved for it. Indexes and summaries in the entry file only point to canonical sources, and current text a decision record cites keeps its own level.

Settle current system behaviour by the code and run results, intended behaviour by the current design and contract, and task progress by version history, check results and work state. When documents and code disagree, decide which one is wrong before changing either.

To resolve a conflict, check each clause's status and scope; apply an owner instruction in the current conversation that explicitly covers the clause, and any explicitly approved supersession or exemption in effect; obey together the clauses that can apply together, including tightenings within their scope; and settle the remaining cross-level conflicts by the order. Relaxing a current limit requires an owner instruction, supersession or exemption that explicitly covers that limit; a newer or narrower clause is not enough. On a same-level conflict, a scope you cannot determine, or a needed relaxation without explicit approval, pause the affected action, list the conflicting texts and their locations, and ask the owner to decide; then update the canonical sources and indexes by pass 4.

### 3. Write the entry file and its routes

The entry file, such as `AGENTS.md`, states directly or indexes the core methodology and the long-term high-priority requirements. High-priority requirements include those that change task scope, authorisation, prohibitions or cross-task judgement. Each route applies under its task trigger.

- **Direct or indexed.** You may state a requirement directly when one sentence gives its condition, requirement and exceptions and the executor need not consult steps, a checklist or a parameter table. Otherwise keep a one-sentence conclusion and index the canonical source. Where content loads never changes its type, binding force or approval.
- **Entry test.** A line may move out of the entry file if deleting it would leave the executor's permissions, obligations and judgement on applicable tasks unchanged and would leave every required canonical source findable.
- **Order and budget.** Put hard constraints, the authority order and required routes first. For each host, start location and configuration in use, check what loads automatically and its budget, and tell hard limits apart from length advice.
- **Nested entries.** Add one only where a subtree really differs, holding only the routes the subtree adds and tightenings of the parent's rules; approved exceptions take effect in the project register. When a version-controlled shared task entry exists, route to it. Omit that route otherwise.
- **Index line.** Write the trigger first and the target second. Build the trigger from the action words, domain nouns, terms, code paths and package roots that appear in tasks, in every language the team writes tasks in. Point the target to a specific file and section and say what it decides, never "read the relevant parts of" a document. Use this form:

  > When the task 〈modifies / reviews / troubleshoots〉 〈domain noun, in each task language〉, or changes 〈path〉, first read 〈file#section〉 (decides 〈what〉).

  ✗ `Follow docs/rules.md before development.` (no trigger, no section)
- **Skill routes.** Route each required skill explicitly, giving its name, canonical path, trigger and what it decides:

  > Before writing or reviewing 〈language〉 code, load `〈skill-name〉` (`〈canonical path〉/SKILL.md`) and read the project register's matching section (decides this repository's tightenings and exemptions).
- **Indirection.** Point from always-loaded text straight to the owning section; justify each extra level of indirection.

### 4. Run the lifecycle

Locate each canonical type and destination by **Classify each unit**.

| Action | Operation and approval |
| --- | --- |
| Create or change | Apply **Approval**. Mark proposals `proposed` and versions approved for future effect `approved-pending-effect`. Keep both apart from current text. Add a new record to change a decision. In an existing decision record, change only its status and supersession link, with approval fields filled on approval as specified in the form. On effect, update other current text in place and update the affected summaries and routes in the same change. |
| Supersede or revoke | The role that may approve the original approves. When a supersession or revocation takes effect, update the old entry's status, its supersession link if it has a successor, and every affected current index in the same change. When an explicitly recorded expiry condition is met, the maintainer updates the status on evidence. Restore an older rule only on explicit grounds. |
| Archive or delete | The maintainer may archive content or remove redundancy after confirming it has left current use and keeping the history links needed. You may delete a redirect stub with no live consumer. While it has consumers, keep a compatible redirect or fix the references in the same change. Deleting a rule or host control still in force needs revocation approval. |

Reuse the repository's existing record of maintainers; a single owner acts as maintainer, with no approval file. When a change alters a source, scope or route, check only the documents it affects.

**Adoption change description.** When applying the adoption procedure, list in the existing change description what this change keeps, splits, merges, migrates or archives. Use the co-location conditions of pass 1 for retained sections.

### 5. Place memory

- **The test question.** Classify the content by function and apply **What no document or memory stores** before using this test to choose between repository and personal memory. Ask whether the item would still hold if another person did this project, on another machine, with another agent. Keep the conditions of application the project defines, such as role, path scope, platform and version. Replace only the specific person, machine and agent. If it still holds, use repository memory. If it does not, use personal memory. If a finding's applicability is unknown, keep the observation pending in work state until you can classify it.
- **Boundary rules.** Personal memory is never the only location of a project rule. When repository and personal memory conflict, the repository wins: correct the personal entry in the same turn, or, without write access, hand the correction to that memory's owner. Repository memory holds no personal preferences, private accounts, local absolute paths or content true only on one machine; state project rules by project role or condition of application. When content mixes a project requirement with a personal practice, extract each: the project requirement enters the repository through capture and promotion, an authorisation addressed to a project role is a decision record, and a practice that applies only to its user and changes no project authorisation stays in personal memory.

Use **Entry formats** to write decision records and knowledge entries. Follow `references/memory-entries.md` for destinations, capture, promotion, cleanup, layout and staleness.

**Hand off.** When you cannot write the canonical source in this turn, register the target location, unfinished items and authorised recipient in the target repository's existing shared task record. For a decision or authorisation, include the owner's words with any necessary redactions marked, the approved object and its scope. For knowledge, include the phenomenon, conditions and evidence or method to recheck it. Mark any unresolved details as pending. If you cannot use the shared task record, give the same information to the owner or an authorised maintainer in the handoff or final report. Keep handoff records out of personal memory.

#### Entry formats

**Decision record.** Give each decision its own addressable unit. You may leave the approval basis and `decided_by` empty while it is proposed. Fill both on approval. Use this format:

```markdown
---
id: D-0007                  # never reused
title: <one-sentence conclusion>
status: proposed            # proposed | approved-pending-effect | current | superseded by <id> | revoked | expired
date: YYYY-MM-DD            # date of the decision, absolute
decided_by: <role or code-host account name of the decider>
scope: <paths, modules, task types or branches it applies to>
grantee: <authorisations only: who is authorised>
allowed_actions: <authorisations only: which actions are allowed>
effective_when: <approved effective date or condition; "on approval" when approval makes it effective>
expires_when: <concrete expiry condition and date; omit if none>
supersedes: <id of the superseded record; "none" if none>
applied_in: <link to the current text; omit when this record is the canonical source>
---
## Approval basis
> <The owner's words, verbatim, with a link to the approved proposal or its exact text, and the confirmed scope. Mark any redaction of credentials or private information.>

## Decision
<The full decision when this record is the canonical source. When the text is maintained elsewhere, state which change was approved and link the current text.>

## Rationale
<Optional: the least background later judgements need.>
```

**Knowledge entry.** Make each entry locatable on its own, as a file or a separate section. This is a reference format:

```markdown
---
name: <short lowercase hyphenated name>
description: <one line: the symptom and its trigger, in words tasks use>
observed: YYYY-MM-DD        # date observed, absolute
scope: <module, tool version, branch>
source: <how it was observed: command, log or commit>
verify: <how to check that it still holds>
status: valid               # valid | needs-verification
---
Symptom: <...>
Cause: <...; "not found" when unknown>
Action: <...>
```

### 6. Choose an inline line, a plain document or a skill

Decide the type first. Decision records, knowledge and pitfalls, work state, the project register and the current design and contract stay plain, linkable canonical documents. Decide whether a rulebook, runbook or method becomes a skill, where a skill lives, how it is copied, what host configuration holds and whether a host needs an adapter as `references/skills-and-hosts.md` directs.

### 7. Reference across repositories and branches; brief delegates

- **Cross-repository and cross-branch references.** Give a cross-repository reference its source repository, applicable branch or revision and in-repository path. Whether text takes effect across branches follows the scope its canonical source states. Maintain a shared document along a merge direction only when the repository has approved a fixed one. Omit cross-repository arrangements when there is only one repository. Omit cross-branch arrangements when there is only one branch.
- **Delegation briefs.** A brief states the applicable entry file, the required canonical sources and sections, the scope of change and the verification method. When the delegate cannot read a canonical source, attach the verbatim text the task must obey and its source. When a needed basis is missing, the delegate first searches the sources it may read; failing that, the delegator supplies the necessary content it may pass on; failing that, the delegate reports the gap and holds the affected actions. A brief's force follows pass 2.

### 8. Run the light checks

Apply **Limits on checks**.

1. **Reference integrity.** Each normative reference the change touches resolves from the applicable branch. Where host adapters or controlled copies exist, check their targets and recorded source revisions.
2. **Current indexes.** In each index the change affects, no expired, superseded, archived or deleted content is listed as current, each listed entry resolves, and each superseded entry links its successor. Skip the part for which no current index or supersession record exists.
3. **Cold-start discovery sample.** Run it when the structure, condition or target of the entry file or a route changes, or when the trigger of a key skill's description changes. For other changes, you may omit it. Take a few representative tasks from the affected common hosts, with at least one that must hit and one that must not, and name no document or skill in the task text. In a fresh session with no personal memory, check that the hit case reads and obeys the required guidance before acting, and that the miss case does not misread or misapply the guidance under test.

## Self-check

- [ ] **Standing rules.** Did each standing rule hold as stated?
- [ ] **Reference files.** Was each file whose condition held read in full before its rules were applied?
- [ ] **Pass 1.** Did **Classify each unit** hold as stated, including the omission and co-location conditions?
- [ ] **Pass 2.** Were the authority order, clause levels, the sources for questions of fact and the conflict procedure applied as stated?
- [ ] **Pass 3.** Did **Write the entry file and its routes** hold as stated?
- [ ] **Pass 4.** Did **Run the lifecycle** hold as stated?
- [ ] **Pass 5.** Did **Place memory** and its applicable reference rules hold as stated?
- [ ] **Pass 6.** Was the type decided first, did the types listed there stay plain, linkable canonical documents, and were packaging, location, copies, host configuration and adapters chosen as `references/skills-and-hosts.md` directs?
- [ ] **Pass 7.** Did the cross-repository and cross-branch rules and delegation rules apply as stated, including their omission and missing-basis conditions?
- [ ] **Pass 8.** Did each check in **Run the light checks** run under its stated conditions?
- [ ] **Adoption.** If the adoption reference applied, did each applicable step run in order, including any correction required by **Verify**?
