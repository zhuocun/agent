---
name: cursor-harness
description: >-
  When you are running as an agent inside Cursor (IDE agent, Cloud Agent, or self-hosted worker), track every task, subagent and long-running job to completion through follow-up messages and context compaction. Use when the work involves more than one task at a time, delegating to Task-tool subagents or external CLIs, background shells, tmux sessions, deployments or test runs longer than a few minutes, follow-up messages that arrive mid-work, or restoring open tasks and runs from the ledger after a context compaction. Covers the task ledger, turn-start and turn-end routines, background-job waiting, subagent delegation, and Cursor tool quirks. Do not use for a single short request that finishes inside one turn with no background work, or when you are not running inside Cursor, including when Cursor is only the subject of the request, such as a brief, prompt or plan for a Cursor agent to run later.
---

# Cursor Harness

Use this operating loop inside Cursor's agent harness to track every task, watch long processes, handle interruptions, and close completed work. Cursor provides shell jobs, subagents and dynamic tools, and on Cloud Agent, timers. Detached runs are invisible to the harness, and compaction drops detail.

Priority order, highest first: **no task is lost → no finished job goes unnoticed → never sit idle on a wait when other work exists → minimal tool and token cost.** Resolve conflicts in favor of the higher priority.

## Rules for the whole task

- **Register first.** Before you start work you owe, or launch a job, subagent or timer, add a ledger entry for it ([what to register](references/task-ledger.md#registration)). Each running entry names its completion signal and the next action on completion. A running entry without a live signal is a defect: give it a waiter or safety timer, or poll it now.
- **Pair every detached run with a waiter.** A **detached run** is a process whose launch command returns at once (`tmux new-session -d`, `nohup`, `setsid`, `cmd &`), so Cursor does not track it. Give it an **end marker**, a file written after the process exits that records its exit code, and a **waiter**, a background shell job that exits when the end marker appears or the run's tmux session disappears.
- **Mark a ledger entry `done` only with evidence:** exit code and artifact for runs, a result verified as [verification](references/delegation.md#verifying-delegated-results) describes for subagents and external agent CLIs, and an observable outcome for tasks.
- **Quote the user's exact words** for new tasks and acceptances.

## Operating loop

### 1. Keep one ledger

Keep all work you own in one durable ledger file. A **ledger entry** records one item of work you owe. Follow [ledger registration, location, and states](references/task-ledger.md).

### 2. Turn start: inventory before anything new

At the start of every turn, including a follow-up message or a timer prompt:

1. Read the ledger. After a compaction, treat each claim in the summary as unverified until the ledger or ground truth (git state, PRs, CI, the files themselves) confirms it.
2. Collect completion signals: shell job notifications, end markers, `tmux ls`, delivered subagent results, and, where subscription tools exist, `list_subscriptions`.
3. Process completed work: record it, then verify the result and trigger the next step before handling the new message, unless the verification needs a long-running check, in which case handle the new message first.

### 3. Classify every new message before acting

Handle each part of the message using [message classification and interruptions](references/task-ledger.md#handling-interruptions).

### 4. Delegate and background by default

Choose a vehicle with [background work](references/background-work.md#choosing-the-vehicle). Use [delegation](references/delegation.md) for subagent briefs, dispatch, and review.

### 5. Wait efficiently

An idle agent wakes only on a user message or on an event Cursor delivers as a new turn, such as a safety timer prompt, a subscription event or a background Task subagent's result. Do not rely on a background shell job or waiter that finishes after your turn ends to start a turn. A **blocking wait** is an `AwaitShell` call on a job; a user message cuts it short. So, while any run is going:

- Do independent ledger work first. When none remains, block with `AwaitShell`: on the waiter when one detached run is going; on an any-end waiter when two or more are going; or on a job by id when only background shell jobs are running. An **any-end waiter** is one background shell job that exits as soon as any watched end marker appears. Collect other background shell jobs and Task subagent results at the next inventory.
- Where a timer tool exists, keep a **safety timer** subscribed: a timer subscription whose prompt says "run the inventory from the ledger", one-shot at a known end time or recurring when the end is uncertain. Its prompts can arrive late and batched, so treat each batch as one inventory request.
- After an interruption, handle the message and run the inventory. Then start a fresh waiter over the remaining runs and block again in the same turn, unless the user asked you to stop working, or a safety timer covers the remaining runs and they will take much longer than its interval; in those cases end the turn and leave the runs going.

Scripts and settings: [tmux run plus waiter](references/background-work.md#tmux-run-plus-waiter-verified-2026-10-12), [any-end waiter](references/background-work.md#any-end-waiter), [safety timers](references/background-work.md#safety-timers); evidence and the Cloud Agent queue check: [wait routine](references/background-work.md#wait-routine).

### 6. Turn end: leave nothing unwatched

Before your final message:

1. Update the ledger.
2. Confirm every running entry has a live completion signal and, where a timer tool exists, a safety timer covers it; where no timer tool exists, say in the report that nothing collects the run until the user's next message.
3. Report open work using [ledger reporting](references/task-ledger.md#reporting).

## References

Load the topic file when the situation arises.

| File | Read when |
| --- | --- |
| [references/task-ledger.md](references/task-ledger.md) | Starting multi-task work; picking a ledger location; deciding entry states |
| [references/background-work.md](references/background-work.md) | Running anything long: shell jobs, `AwaitShell`, tmux plus waiter, safety timers, hangs |
| [references/delegation.md](references/delegation.md) | Dispatching Task subagents or external agent CLIs; verifying their results |
| [references/platform-tools.md](references/platform-tools.md) | Dynamic tools, Cloud Agent diagnostics, subscriptions, self-hosted machine rules |
| [references/field-notes.md](references/field-notes.md) | Before an unfamiliar shell technique; after discovering a new quirk |

## Maintenance

When you confirm a reusable Cursor Harness fact or fix:

- Put it in the topic file it belongs to. If none fits, put it in `references/field-notes.md`, using its entry format.
- When three or more field notes share a topic, move them into the matching reference file, or create `references/<topic>.md` and add it to the table under [References](#references).
- Mark each fact as **verified** (you ran it, with date), **documented** (from Cursor's tool descriptions or docs), or **unverified**. Upgrade or delete entries when evidence changes. Never keep contradictory statements.
- Keep the skill machine-agnostic and project-agnostic: no absolute paths, usernames, session IDs, ports, proxy addresses, product codenames, or credentials. Keep project-specific lessons in the project's memory.

## Self-check

- [ ] Every ask that leaves work owed, and every subagent, job, run, and timer I own, got a ledger entry before I started or launched it, and every running entry names its completion signal and next action.
- [ ] I ran the turn-start inventory before handling the new message.
- [ ] Every detached run has an end marker and a waiter.
- [ ] While runs were going, a safety timer was subscribed wherever a timer tool existed, and after each interruption I started a fresh waiter over the remaining runs and blocked again, or ended the turn because the user asked me to stop working or a safety timer covered the remaining runs and they would take much longer than its interval.
- [ ] Nothing was marked done without evidence; new tasks and acceptances quote the user's exact words.
- [ ] My final message groups open entries as running, waiting on you, and queued, and for running work says where to look and what happens on completion.
- [ ] New reusable facts went to the right reference with a status label.
