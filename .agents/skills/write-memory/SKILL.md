---
name: write-memory
description: >-
  Record durable decisions, approvals, authorisations, prohibitions and
  scope corrections (决定记录、批准、授权、禁令、范围纠正). Use when the
  owner makes one, including “OK”, “批准” or “按你的推荐处理”, or when
  capturing a reusable finding, pitfall, lasting personal preference or
  machine-specific fact (知识、踩坑、个人偏好、本机特性). Use before relying
  on a knowledge entry, or to verify, correct or route specific memory
  entries (核实、过时、冲突), including a project decision found only in
  personal memory. Do not use for designing, reorganising or auditing
  repository guidance, including memory migration within that work, or
  for task progress, credentials, facts directly retrievable from the
  implementation, prose editing, or writing code rules themselves.
---

# Write Memory

Maintain durable project and personal memory in locations that a later session can read. Apply the rules below when recording, finding or maintaining an entry.

Apply **Host controls** and **What no document or memory stores** throughout. Decide the destination before applying **Capture, hand off, promote, clean**.

## Standing rules

- **Roles.** The owner is the person with authority over the repository's scope, rules and exemptions. A maintainer is the person the owner names to maintain a document or a class of documents. The executor is the agent or person doing the task.
- **Host controls.** Permissions, sandboxes, hooks, and the code host's branch protection and required checks stand outside the authority order. No written or chat instruction overrides a failing host control. When you believe a control is wrong, stop the affected action and change the control through its own change path.
- **What no document or memory stores.** Do not store credential values, other people's private information or unredacted production data in any governed document or in either kind of memory. Do not store task progress in either kind of memory: keep task progress and one-off task, release and pipeline numbers in work state. Keep superseded content that must survive in a decision record's supersession chain or in the archive. Do not copy into memory implementation facts that can be looked up directly.
- **Approval.** The owner approves principles and methodology, the authority order, hard constraints, project decisions and authorisations, exemptions, incompatible changes to external contracts, and host controls. The maintainer of the content approves other ordinary text. An explicit approval already given for the same text and scope stands. The executor may propose changes, record approvals already given and update its own task's progress.
- **Memory grants nothing.** Knowledge entries, work state, archive and evidence, personal memory and delegation briefs cannot on their own grant permission or change current text.
- **Pending project content.** Use only verified and promoted content as a cross-task project rule.
- **One canonical source.** Keep one canonical source for each current rule or controlled fact. Summaries, indexes and display artefacts name their source. When an existing script or test reads a passage, name it in the canonical source. If you change the interface it reads, run the corresponding existing verification.
- **Normative wording.** Apply these rules to text written by people and agents. For requirements, defaults and permissions, use `must` or `must not`, `should`, and `may` in English, and `必须` or `不得`, `应`, and `可` in Chinese. Give the condition for departing from a default. Use `YYYY-MM-DD` or a locatable revision in fields that must be rechecked, including approval, observation and expiry.
- **Volatile state.** Use time fields in stable text to mark approval, effect, verification or review. Keep a binding expiry condition in the record it governs. Keep volatile progress, schedules, to-dos and unfinished implementation in work state; a fixed historical fact may stay in a decision basis or in evidence. A normative reference inside the repository resolves from the applicable branch to a version-controlled target.
- **Limits on checks.** Use at most the three checks of **Run the light checks** for documentation governance; a small repository may run them by hand. Add no document-length gate, natural-language parsing script or preference-blocking hook. Source verification, existing tests and platform permissions run under their own rules.

## 1. Decide the destination

Split an entry that mixes kinds, then send each kind to its place:

| Content | Destination |
| --- | --- |
| The owner's decisions | Decision record |
| Standing authorisations addressed to agents | Decision record, as an authorisation |
| This project's knowledge and pitfalls | Knowledge entry |
| Routes and context maps | The entry file; delete the copy in memory |
| Personal collaboration preferences | Personal memory |
| Tool and machine traits | Decide by the test question |
| Stage status and handoff snapshots | Work state, or archive and evidence; never memory |

- **The test question.** Classify the content by function and apply **What no document or memory stores** before using this test to choose between repository and personal memory. Ask whether the item would still hold if another person did this project, on another machine, with another agent. Keep the conditions of application the project defines, such as role, path scope, platform and version. Replace only the specific person, machine and agent. If it still holds, use repository memory. If it does not, use personal memory. If a finding's applicability is unknown, keep the observation pending in work state until you can classify it.
- **Destinations.** Repository memory holds the owner's decisions and authorisations for this project, and knowledge and pitfalls that hold for other executors within the project's conditions of application, as decision records and knowledge entries with no separate inbox or new type. Personal memory holds communication and reporting preferences, preferences on dividing work between models and hosts, local paths and machine-specific traits, accounts by name and purpose without credentials, and personal tool habits shared across repositories, in a user-level location outside every repository.
- **Boundary rules.** Personal memory is never the only location of a project rule. When repository and personal memory conflict, the repository wins: correct the personal entry in the same turn, or, without write access, hand the correction to that memory's owner. Repository memory holds no personal preferences, private accounts, local absolute paths or content true only on one machine; state project rules by project role or condition of application. When content mixes a project requirement with a personal practice, extract each: the project requirement enters the repository through capture and promotion, an authorisation addressed to a project role is a decision record, and a practice that applies only to its user and changes no project authorisation stays in personal memory.

## 2. Capture, hand off, promote, clean

Write a personal item worth keeping in the same turn when you have user-level write access; otherwise tell the owner of that memory what is pending. These steps handle repository memory:

1. **Capture.** In the same turn, record each long-term project decision, authorisation or reusable finding that is new or changed. Record a brief approval together with the one locatable proposal, options and scope it approves. When the object or scope is ambiguous, record what remains unresolved as pending in work state and leave the current rules in force. If work state is unwritable, report the same pending information to the owner or an authorised maintainer. Record project knowledge with a phenomenon and conditions that can be rechecked.
2. **Hand off.** When you cannot write the canonical source in this turn, register the target location, unfinished items and authorised recipient in the target repository's existing shared task record. For a decision or authorisation, include the owner's words with any necessary redactions marked, the approved object and its scope. For knowledge, include the phenomenon, conditions and evidence or method to recheck it. Mark any unresolved details as pending. If you cannot use the shared task record, give the same information to the owner or an authorised maintainer in the handoff or final report. Keep handoff records out of personal memory.
3. **Promote.** Write the decision basis as a decision record. When a decision changes current text, follow **Run the lifecycle** for that text and link the decision record from it. When an authorisation is itself a complete executable rule, the decision record may be its canonical source. Write knowledge into a knowledge entry after verification. Before the next work that depends on the rule, confirm that the change has reached the applicable branch and can be found from the entry file.
4. **Clean.** After verifying that the canonical source works, delete the pending copies and the project copies in personal memory.

## 3. Write the entries

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

## 4. Place and route the entries

- **Layout.** By default, keep decision records in `docs/decisions/`, one file per decision plus a `README.md` index, and knowledge in `docs/knowledge/`, a `README.md` index plus one file per entry. While decisions and entries are few, `docs/decisions.md` and `docs/knowledge.md` may replace them, with one numbered section per item. Another layout is allowed when the entry file's routing line points to the actual location and each entry has every field of its format.
- **Findability.** When the repository has decision records or knowledge entries, the entry file, such as `AGENTS.md`, points to their location in one line. For example: before a scope, authorisation or design judgement, read the applicable decision records; before troubleshooting, testing or changing a tool version, look up knowledge entries by symptom and task. Use the repository's actual paths or sections. When an entry needs indexing, use **Index line**.
- **Index line.** Write the trigger first and the target second. Build the trigger from the action words, domain nouns, terms, code paths and package roots that appear in tasks, in every language the team writes tasks in. Point the target to a specific file and section and say what it decides, never "read the relevant parts of" a document. Use this form:

  > When the task 〈modifies / reviews / troubleshoots〉 〈domain noun, in each task language〉, or changes 〈path〉, first read 〈file#section〉 (decides 〈what〉).

## 5. Handle staleness and conflicts

Before acting on a knowledge entry, confirm by its `verify` method that it still holds under current conditions. The maintainer updates, deletes or moves to evidence an entry that is stale. When personal memory holds a project decision the repository does not record, check the original approval and hand it off by the capture steps; the current repository rules stay in force, and work that depends on the unconfirmed decision waits.

## 6. Run the lifecycle

Use **Decide the destination** and **Place and route the entries** for memory entries. For a decision that changes existing current text, locate the affected clause through the entry file, retain its canonical type and location, and apply the repository's authority order. If the source, scope or authority cannot be established, use **Hand off** and leave current text in force.

| Action | Operation and approval |
| --- | --- |
| Create or change | Apply **Approval**. Mark proposals `proposed` and versions approved for future effect `approved-pending-effect`. Keep both apart from current text. Add a new record to change a decision. In an existing decision record, change only its status and supersession link, with approval fields filled on approval as specified in the form. On effect, update other current text in place and update the affected summaries and routes in the same change. |
| Supersede or revoke | The role that may approve the original approves. When a supersession or revocation takes effect, update the old entry's status, its supersession link if it has a successor, and every affected current index in the same change. When an explicitly recorded expiry condition is met, the maintainer updates the status on evidence. Restore an older rule only on explicit grounds. |
| Archive or delete | The maintainer may archive content or remove redundancy after confirming it has left current use and keeping the history links needed. You may delete a redirect stub with no live consumer. While it has consumers, keep a compatible redirect or fix the references in the same change. Deleting a rule or host control still in force needs revocation approval. |

Reuse the repository's existing record of maintainers; a single owner acts as maintainer, with no approval file. When a change alters a source, scope or route, check only the documents it affects.

## 7. Run the light checks

Apply **Limits on checks**.

1. **Reference integrity.** Each normative reference the change touches resolves from the applicable branch. Where host adapters or controlled copies exist, check their targets and recorded source revisions.
2. **Current indexes.** In each index the change affects, no expired, superseded, archived or deleted content is listed as current, each listed entry resolves, and each superseded entry links its successor. Skip the part for which no current index or supersession record exists.
3. **Cold-start discovery sample.** Run it when the structure, condition or target of the entry file or a route changes, or when the trigger of a key skill's description changes. For other changes, you may omit it. Take a few representative tasks from the affected common hosts, with at least one that must hit and one that must not, and name no document or skill in the task text. In a fresh session with no personal memory, check that the hit case reads and obeys the required guidance before acting, and that the miss case does not misread or misapply the guidance under test.

## Self-check

- [ ] **Standing rules.** Did each standing rule hold as stated?
- [ ] **Pass 1.** Did **Decide the destination** hold as stated?
- [ ] **Pass 2.** Did each applicable step meet **Capture, hand off, promote, clean**?
- [ ] **Pass 3.** Is each decision separately addressable and in its required form, with the approval fields filled after approval? Is each knowledge entry separately locatable, with the layout conditions checked under pass 4?
- [ ] **Pass 4.** Did **Place and route the entries** hold as stated?
- [ ] **Pass 5.** Did each applicable action meet **Handle staleness and conflicts**?
- [ ] **Pass 6.** Did **Run the lifecycle** hold as stated?
- [ ] **Pass 7.** Did each check in **Run the light checks** run under its stated conditions?
