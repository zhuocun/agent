---
name: cursor-harness
description: >-
  Cursor Harness operating manual: never lose a task, never block on a long process. Use whenever you run as an agent inside Cursor (IDE agent, Cloud Agent, or self-hosted worker) and the work involves more than one task at a time, delegating to Task-tool subagents or external CLIs, background shells, tmux sessions, deployments or test runs longer than a few minutes, follow-up messages that arrive mid-work, or restoring open tasks and runs from the ledger after a context compaction. Covers the task ledger, turn-start and turn-end routines, background-job waiting, subagent delegation, and Cursor tool quirks; the references directory holds topic files that grow over time. Do not use for a single short request that finishes inside one turn with no background work, or inside agents that do not run in Cursor.
---

# Cursor Harness

Use this operating loop inside Cursor's agent harness to track every task, watch long processes, handle interruptions, and close completed work. Cursor provides shell jobs, subagents, timers, and dynamic tools. Detached processes are invisible to the harness, and compaction drops detail.

Priority order, highest first: **no task is lost → no finished job goes unnoticed → never sit idle on a wait when other work exists → minimal tool and token cost.** Resolve conflicts in favor of the higher priority.

## Operating loop

### 1. Keep one ledger

Keep all work you own in one durable ledger file. A **ledger entry** records one item of work you owe. Follow [ledger registration, location, and states](references/task-ledger.md).

### 2. Turn start: inventory before anything new

At the start of every turn, including a follow-up message or a timer prompt:

1. Read the ledger. After a compaction, treat each claim in the summary as unverified until the ledger or ground truth (git state, PRs, CI, the files themselves) confirms it.
2. Collect completion signals: shell job notifications, end markers, `tmux ls`, and delivered subagent results.
3. Process completed work: record it, then verify the result and trigger the next step before handling the new message, unless the verification needs a long-running check, in which case handle the new message first.

### 3. Classify every new message before acting

Handle each part of the message using [message classification and interruptions](references/task-ledger.md#handling-interruptions).

### 4. Delegate and background by default

Choose a vehicle with [background work](references/background-work.md#choosing-the-vehicle). Use [delegation](references/delegation.md) for subagent briefs, dispatch, and review.

### 5. Wait efficiently

Only a timer, a background Task subagent, or a user message wakes an idle agent, and a user message cuts a blocking wait short. So, while any run is going:

- Do independent ledger work first. When none remains, block on the detached run's waiter, or on an **any-end waiter** over every running end marker when two or more detached runs are going, or, when only background shell jobs are running, on a job by id.
- Keep a **safety timer** subscribed, one-shot at a known end time or recurring when the end is uncertain, whose prompt says "run the inventory from the ledger". Its prompts can arrive late and batched, so treat each as an inventory request.
- After an interruption, handle the message, then start a fresh waiter and block again in the same turn.

Details, exceptions, and evidence: [wait routine](references/background-work.md#wait-routine).

### 6. Turn end: leave nothing unwatched

Before your final message:

1. Update the ledger.
2. Confirm every running entry has a live completion signal ([registration](references/task-ledger.md#registration)) and a safety timer covers it ([wait routine](references/background-work.md#wait-routine)), or, where no timer tool exists, that the report says nothing collects the run until the user's next message.
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
- When three or more field notes share a topic, move them into the matching reference file, or create `references/<topic>.md` and add it to the table above.
- Mark each fact as **verified** (you ran it, with date), **documented** (from Cursor's tool descriptions or docs), or **unverified**. Upgrade or delete entries when evidence changes. Never keep contradictory statements.
- Keep the skill machine-agnostic and project-agnostic: no absolute paths, usernames, session IDs, ports, proxy addresses, product codenames, or credentials. Keep project-specific lessons in the project's memory.
- Keep this file the short loop. Put detail in references.

## Self-check

- [ ] Every ask that leaves work owed, and every subagent, job, run, and timer I own, has a ledger entry with a completion signal and a next action.
- [ ] I ran the turn-start inventory before handling the new message.
- [ ] No detached process runs without a waiter.
- [ ] While runs were going, a safety timer was subscribed, and after each interruption I started a fresh waiter over the remaining runs, unless the wait routine let me leave only the safety timer.
- [ ] Nothing was marked done without evidence; acceptances quote the user.
- [ ] My final message lists what is still running, where to look, and what happens next.
- [ ] New reusable facts went to the right reference with a status label.
