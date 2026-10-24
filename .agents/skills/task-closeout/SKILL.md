---
name: task-closeout
description: >-
  Verify outcomes and complete task housekeeping and handoff. Use when finishing,
  pausing, or handing off a task that changed files, systems, records, or deliveries
  outside the conversation, or when asked to wrap up, clean up, or close out a task.
  Do not use for conversation-only answers, routine mid-task updates, code review,
  or prescribing status report formats.
---

# Task Closeout

Reconcile task outputs, records, and resources with actual state. Follow user or host closeout steps. Apply these passes, in order, only to what those steps do not cover. Scale checks to task changes and skip absent surfaces without creating closeout infrastructure. When the task created no working resources, changed no records or deliveries, and changed nothing that documentation, copies, or consumers depend on, use only pass 1 and the pass 7 report.

Priority order, highest first: **preserve work and respect authorization → verify state → reconcile records → synchronize documentation → preserve evidence → clean resources → capture lessons → hand off accurately.**

## 1. Verify scope and outcomes

Read agreed outcomes, acceptance requirements, instructions, and authorizations; identify unfinished work.

Inspect deliverables at their destinations. For version-controlled work, distinguish uncommitted changes, local commits, pushed changes, merged changes, and deployments. Treat check results as evidence only for tested revisions and environments. Mark partial and unverified outcomes; memory and tracker entries alone cannot prove completion. Remove task-added temporary debugging output, instrumentation, and placeholders; restore temporarily disabled checks.

Before actions that others can see or that cannot be undone, such as pushing, merging, publishing, deploying, or sending messages, use existing authorization or obtain what is missing. Pass 5 states which removals need authorization. Continue independent authorized work during pending decisions.

Before sharing, inspect artifacts, logs, reports, and commits for secrets; redact shared material and remove secrets from task scratch files. Report secret exposure in commits, pushed changes, or delivered records immediately to the owner and recommend revocation or rotation. Withhold further material containing exposed secrets until the owner confirms remediation.

## 2. Reconcile records and deliveries

Align the tracker and task status document with pass 1: mark verified parts complete and reopen parts wrongly marked complete. Append verified results and evidence to the task log. Reserve overall closure for pass 7.

Confirm required submissions, reports, and notifications through the receiving system's responses or receipts. Check ambiguous delivery status before retrying. Retry failed or unconfirmed deliveries through safe authorized alternatives without duplicates; leave failures or uncertain deliveries open. Label rebuilt submissions as reconstructed; include only recoverable facts and leave unknown fields empty or marked unknown.

## 3. Synchronize documentation and identify propagation

Update affected current specifications, designs, rules, guides, indexes, and changelogs. Search current documentation and relevant sources, including applicable code, until no outdated reference to a term that the task renamed or removed remains. Leave historical and archived records unchanged. Before removing duplicates, verify identical retained content; for superseded copies, verify retention of everything still current. Repair references to removed copies.

Identify copies, mirrors, consumers, and dependent branches needing propagation. Synchronize within authorization and list outstanding propagation.

## 4. Preserve evidence

Before cleanup, retain artifacts needed for reconciliation, pending deliveries, or handoff. Keep files linked from records or reports reachable at retained locations; repair links after moves.

## 5. Clean working resources

Inventory task-created working resources. Retain intended deliverables and resources needed for their ongoing operation or for unfinished work; note the reason for each. Clean the remaining temporary execution resources:

- **Temporary worktrees, checkouts, and scratch directories:** Remove task-created ones after version-controlled changes are pushed or merged and unique uncommitted, untracked, or ignored work is preserved elsewhere. Obtain missing authorization for other removals. Use non-forcing removal and stop on refusal. Keep branches unless explicitly instructed otherwise.
- **Background work and locks:** Stop task-owned processes, servers, watchers, and agent runs without affecting unrelated work. Release locks through their owning tools; never delete shared lock files.
- **Temporary access, settings, and schedules:** Revoke task-issued credentials, tokens, and grants. Revert temporary changes to configuration, permissions, feature switches, and debug settings. Cancel task-created scheduled runs, reminders, and subscriptions.
- **Shared or external data:** Remove only test data you created, and only where existing authorization covers it; otherwise obtain authorization first. Leave others' data untouched.
- **Capacity after heavy work:** Check available storage, file-count, and quota headroom. Propose cleanup for constrained capacity using measured usage and remaining capacity.

## 6. Capture lessons and follow-up work

Record reusable lessons and confirmed preferences in the existing persistent memory or knowledge store, if one exists. Keep task state in task records. Keep proposed instruction or tooling improvements separate from confirmed lessons.

Register unresolved work as follow-up tasks in the authorized tracker, or otherwise the handoff, with an owner or explicit ownership gap, next action, and evidence. Close or mark superseded your obsolete drafts and change requests when authorized.

## 7. Finalize closure and hand off

Recheck outcomes changed during closeout. Report concisely to the owner: verified outcomes with evidence, outstanding work and propagation, risks, unverified items, retained resources with their reasons, unremovable data, irreversible states, and needed decisions or authorizations. Use any required form. When switching tasks or ending a session with unfinished work, record its state and resumption steps in the task status document, or in the report when no such document exists.

After reporting, close the overall task in its tracker and status document only when required work, including documentation and cleanup, is finished and the owner accepts explicitly or through a completion rule set in advance. If acceptance arrives later, close then. After closing, verify the recorded status and append the completion record. Until every condition holds, leave the task open and report which conditions are unmet. Mark working to-do steps complete as they finish.

## Self-check

- [ ] Pass 1: Outcomes, requirements, instructions, and authorizations were read; unfinished work was identified; claims match destinations, revisions, and environments, with version-control states distinguished where applicable, partial and unverified outcomes marked, and no completion based on memory or trackers alone; temporary deliverable changes were removed or restored.
- [ ] Pass 1: Actions respected authorization; independent authorized work continued during pending decisions; sharing checks and scratch cleanup removed detected secrets; exposed secrets were reported immediately with revocation or rotation recommended, and further affected sharing awaited owner-confirmed remediation.
- [ ] Pass 2: Records and logs match verified progress; required deliveries are confirmed by responses or receipts, or remain open; ambiguous statuses were checked before retries, failed or unconfirmed deliveries had safe authorized alternative retries where available without duplicates, and reconstructed submissions are labelled with only recoverable facts and unknowns empty or marked.
- [ ] Pass 3: Affected current documentation is updated; searches leave no outdated reference to a term that the task renamed or removed; historical and archived records are unchanged; removed duplicates have identical retained content, all still-current content from superseded copies is preserved in the retained copy, and references are repaired; propagation is completed within authorization or listed.
- [ ] Pass 4: Needed artifacts were retained before cleanup, and linked evidence remains reachable after moves.
- [ ] Pass 5: The inventory of task-created working resources is complete, with intended deliverables and resources needed for their ongoing operation or for unfinished work retained and each reason noted. Remaining temporary execution resources were removed, stopped, revoked, reverted, or cancelled. Task-created worktrees, checkouts, and scratch directories were removed only after version-controlled changes were pushed or merged and unique uncommitted, untracked, or ignored work was preserved elsewhere; other such removals had any required authorization. Those removals were non-forcing and stopped on refusal. Branches were kept unless explicitly instructed otherwise. Removal of self-created test data had authorization, and unrelated work, others' data, and shared lock files remained untouched. Locks were released through their owning tools. Available storage, file-count, and quota headroom were checked after heavy work, with cleanup proposed for constrained capacity using measured usage and remaining capacity.
- [ ] Pass 6: Lessons and confirmed preferences are in the existing persistent memory or knowledge store, if one exists. Task state is in task records, and proposed instruction or tooling improvements remain separate from confirmed lessons. Unresolved work has an owner or an explicit ownership gap, a next action, and evidence in the authorized tracker or handoff. The agent's obsolete drafts and change requests were closed or marked superseded within authorization.
- [ ] Pass 7: Changed outcomes were rechecked; the owner report covers required contents and form; resumption notes satisfy pass 7's condition and destinations; overall closure follows pass 7's sequence, conditions, status verification, and completion record, or remains open with its unmet conditions reported; finished to-do steps are complete.
