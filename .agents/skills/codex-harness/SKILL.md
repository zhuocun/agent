---
name: codex-harness
description: >-
  Track concurrent Codex tasks and long-running jobs through completion,
  interruptions, and compaction. Use when an agent running in Codex manages
  background commands, authorized subagents or external agent CLIs, overlapping
  user asks, or resumes work with unfinished runs. Do not use for a short
  synchronous request with no unfinished work, or for agents not running in Codex.
---

# Codex Harness

Keep a Codex controller's owned work accounted for until its authorized outcome is verified or a real blocker is recorded. The controller retains scope, acceptance, and the next decision, while a monitor reports events for the controller to handle.

Priority order, highest first: **current user instructions → reliable task accounting → prompt handling of results → useful work during waits → low monitoring cost**.

## Reference files

Read a file in full where its bullet says "in full", and a named section where its bullet names one, before the work its condition names. After a compaction, read them again as **2. Reconstruct the current task** directs.

- [task-ledger.md](references/task-ledger.md) (ledger storage, registration, fields and states): in full during **1. Record ownership**; its section [Handle messages and races](references/task-ledger.md#handle-messages-and-races) when new user steering arrives; its section [Guards and handoffs](references/task-ledger.md#guards-and-handoffs) before an interruption or turn exit.
- [delegation.md](references/delegation.md) (settings and briefs): in full when you choose an execution vehicle; its section [Controller review and continuation](references/delegation.md#controller-review-and-continuation) when you review an agent's result.
- [background-work.md](references/background-work.md), by section: [Choose ownership before launch](references/background-work.md#choose-ownership-before-launch) before launching or monitoring long work; [Validate completion](references/background-work.md#validate-completion) when checking CLI evidence for completion; [Suspected hangs and retry limits](references/background-work.md#suspected-hangs-and-retry-limits) when checking a suspected hang or preparing a stop or retry; [Native owner and read-only watcher](references/background-work.md#native-owner-and-read-only-watcher) when you use a watcher.
- [platform-tools.md](references/platform-tools.md) (host distinctions and evidence details): in full during **6. Check capabilities and retain evidence**.

## 1. Record ownership

Use one durable ledger that links asks, actual project lifecycle, branches or worktrees, agents, attempts, artifacts, signals, and next authorized actions. Reuse the owning project's tracker when applicable. Machine-level work does not create a feature lifecycle. `references/task-ledger.md` holds its storage, registration, fields and states.

## 2. Reconstruct the current task

At turn start, read the ledger and current user instructions before acting on queued completions. A stop or scope change can invalidate a recorded next action. Apply [task-ledger.md — Handle messages and races](references/task-ledger.md#handle-messages-and-races) to new user steering.

After compaction, reload this skill and any reference whose applicable instructions are missing from context. Rebuild scope and ownership. Confirm the reconstruction against relevant files and project status, including the branch or worktree when applicable, before launching work, accepting results, retrying jobs, or changing task resources.

Reconcile only owned jobs and agents using delivered messages, current tool results, and per-attempt exit records. Use the host's supported agent listing when ownership reconciliation requires it. Process queued completions under **4. Wait, validate, and continue** before choosing or launching new work.

## 3. Choose an execution vehicle

Handle short work directly. Delegate only when current user and host instructions permit it and the task benefits, including monitoring assignments. Preserve explicit user overrides. Follow the applicable instructions and documented contracts for the chosen CLI, model routing, review, and project lifecycle. Apply a project lifecycle only to work that belongs to it.

For a required external CLI, prefer an authorized native lifecycle owner when available. That agent launches and manages a bounded CLI run through terminal reporting. For existing jobs whose ownership cannot change, one bounded, read-only native watcher can cover several jobs.

`references/delegation.md` holds settings and briefs, and **Choose ownership before launch** in `references/background-work.md` holds the ownership rules for long work.

## 4. Wait, validate, and continue

Do independent authorized work while runs continue. Otherwise use the available wait mechanism in slices within host and developer limits. Consume actual result messages after a wait. Answer a user question briefly, then resume valid work in the same active turn.

Validate each completed result using terminal evidence, a fresh final artifact, and its semantic verdict. A successful process exit can still report blocked work. Update the result state and take the next authorized action, or record a concrete blocker and continue unaffected work. Keep run state separate from task completion or acceptance.

External output files do not inherently subscribe the controller to completion. Discover and verify a suitable supported subscription before relying on one. Native messages establish delivery only within their verified session scope. Do not end an actionable active turn and rely on user reminders.

Use [background-work.md — Validate completion](references/background-work.md#validate-completion) for CLI evidence mechanics and [delegation.md — Controller review and continuation](references/delegation.md#controller-review-and-continuation) for agent review.

## 5. Establish coverage before exit

Before interruption or turn exit, update the ledger with each owned job, retrieval method, agent status, monitor identity, completion signal, last signal, artifact locations, expiry, next authorized action, and continuation owner.

Confirm monitor acknowledgement and coverage scope. Renew or transfer an expiring monitor only within authorization. If coverage is unavailable, record and disclose the exact unmonitored work. Never imply indefinite monitoring or wake-up after session closure.

Report completed outcomes and material open work with artifact locations and real blockers. A watcher notification alone does not advance the task. Apply **4. Wait, validate, and continue** to watcher results.

Use [background-work.md — Native owner and read-only watcher](references/background-work.md#native-owner-and-read-only-watcher) for watcher mechanics and [task-ledger.md — Guards and handoffs](references/task-ledger.md#guards-and-handoffs) for handoff details.

## 6. Check capabilities and retain evidence

Check current exposed schemas before relying on a host capability. Keep capability claims and monitoring promises within current tool contracts and verified delivery scope.

Keep reusable facts in the relevant reference. Label them documented, verified with date and scope, or unverified. Retain the mechanism and verified scope. Remove contradicted claims. Keep task-specific machine paths, identifiers, credentials, project details, and observation sources in the task's own records.

`references/platform-tools.md` holds host distinctions and evidence details.

## Self-check

- [ ] Each owned ask and attempt satisfies **1. Record ownership** and has the fields required by **Location and registration**, with unavailable fields marked explicitly.
- [ ] At turn start, the ledger and current user instructions were read before acting on queued completions, only owned jobs and agents were reconciled from messages, tool results, and per-attempt exit records, the supported agent listing was used when ownership reconciliation required it, and queued completions were processed under **4. Wait, validate, and continue** before choosing or launching new work.
- [ ] After compaction, this skill and any reference whose applicable instructions were missing from context were reloaded, and scope and ownership were rebuilt and confirmed against relevant files and project status, including the branch or worktree when applicable, before launching work, accepting results, retrying jobs, or changing task resources.
- [ ] New user steering was handled according to **Handle messages and races**.
- [ ] Execution vehicle selection satisfies **3. Choose an execution vehicle**, with settings and briefs checked against **Model and vehicle** and **Brief and dispatch** where applicable.
- [ ] Waiting, completed results, and continuation satisfy **4. Wait, validate, and continue**, with CLI evidence and stops or retries checked against **Validate completion** and **Suspected hangs and retry limits** where applicable.
- [ ] Agent deliverables satisfy **Controller review and continuation** where applicable.
- [ ] Before interruption or exit, coverage and reporting satisfy **5. Establish coverage before exit**, with watcher mechanics and handoff details checked against **Native owner and read-only watcher** and **Guards and handoffs** where applicable.
- [ ] Host capabilities were checked before reliance, every claimed capability and monitoring promise has support from current tool contracts and verified delivery scope, and reusable facts satisfy **6. Check capabilities and retain evidence**.
- [ ] Each file or section under **Reference files** whose condition held was read before the work its condition names.
