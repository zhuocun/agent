# Task ledger

Use this reference to register work, choose a ledger location, record states, and handle messages. The ledger replaces memory: assume you will forget any task or process absent from it.

## Registration

Before starting work or launching a job, add a ledger entry. Include user asks other than a question you answer in the same turn, subagents, background shell jobs, tmux runs, scheduled safety timers, and work waiting on the user. Before launching a wave, register every member of the wave, then launch.

Each running ledger entry names its completion signal and the next action on completion. Signals include a shell job, an end marker, a subagent result, or a safety timer. A run without a live signal is a ledger defect. Give it a waiter or safety timer, or poll it now.

Quote the user's exact words for new tasks and acceptances.

## Where to keep it

Pick the first location that applies. State the location in your first progress note.

1. **The project's own tracker.** Use an existing task document or ledger the project already keeps for user-facing tasks. Keep run-level detail in a side file next to it, where a broad `git add` would not commit it.
2. **A persistent agent store**, when the system context lists one for the current agent. It survives compactions and new turns for this agent. Use `<store>/ledger.md`.
3. **A scratch file outside version control**, such as a directory the repo already ignores. Never put the ledger where a broad `git add` would commit it.

`TodoWrite` provides an in-session view and renders progress for the user. It does not replace the ledger file. Compaction can drop it, and it has no room for completion signals.

## Entry format

Use one line or short block per ledger entry. Keep it greppable.

```markdown
| id | kind | ask / purpose | owner | state | signal | next on completion | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T3 | task | "user's exact words" | me | running | run R7 | report to user | — |
| R7 | run | regression for T3 | tmux `t3-regress-1` | running | end marker `runs/t3-regress-1/run.end` + waiter job | verify report, then report to T3 | log path |
| S2 | subagent | review of T3 patch | background Task "Review T3 patch" | running | subagent result | apply or send back issues | — |
| W1 | timer | safety timer for R7 | `subscribe_timer` "r7-check" | armed | timer prompt | run the inventory from the ledger; unsubscribe if done | — |
```

Kinds: `task` (a user ask), `run` (shell job or tmux run), `subagent`, `timer`, `wait-user` (blocked on a user decision, credential, or acceptance), `guard` (an action forbidden while a run is live).

## Guards for runs against shared environments

Redeploying or reconfiguring a deployed environment invalidates a run against it, including an integration test, regression, or load test. Your own actions count. A push to a branch with continuous deployment restarts the service under test, even for a document-only commit.

- Before launch, identify deployment triggers: pushes to which branches, merges, and scheduled jobs. Add a `guard` entry naming the forbidden action and the protected run.
- Check guards before every push, merge, deploy, or configuration change. Commit locally and push after the run ends.
- Brief whoever runs it, you or a delegate, to accept any build whose relevant code matches the baseline, rather than pinning one commit. Require it to confirm no deployment is in progress before the run and again at the end.

## States

Use `queued → running → verifying → done` for work. Other states are `blocked` (name the blocker), `waiting-user` (record the exact question), `accepted` (the user accepted), `cancelled` (record who cancelled and why), and `failed` (record evidence and the decision taken).

- Mark a ledger entry `done` only with evidence: exit code and artifact for runs, a result verified as [verification](delegation.md#verifying-delegated-results) describes for subagents and external agent CLIs, and an observable outcome for tasks.
- Keep a task that needs user sign-off `verifying` or `waiting-user` until the user accepts, and quote the acceptance as [registration](#registration) requires.

## Handling interruptions

After the [turn-start inventory](../SKILL.md#2-turn-start-inventory-before-anything-new):

1. Split the message into parts. Classify each as a new task, a change to an existing task, a question, an acceptance or rejection, or a stop. Update the corresponding ledger entries before acting on any part.
2. Handle the cheapest high-value part first, usually the answer or acceptance record. Then resume the most blocked work.
3. For a question, answer and resume running work. A question does not cancel work.
4. For a scope change, let a correct running job finish and add a follow-up ledger entry for the change. Stop the job only if it is wrong or the user tells you to stop the job itself; a user who tells you to stop working leaves the runs going.
5. When the user switches topic, retain the old ledger entries in their real states. Mention them in turn-end reports until they close or the user drops them.

If the message releases a blocking wait, follow the [wait routine](background-work.md#wait-routine).

## Reporting

- **Progress notes:** name the ledger entry and its state change, with the detail the user needs to understand it. For example: "The regression finished with 72 passed and 3 failed, and I am reviewing the failures."
- **Turn end:** group open ledger entries as running, waiting on you, and queued. For running work, state where to look and what happens on completion. Skip closed entries unless they closed this turn.
- **On request** ("what's unfinished?"): read the ledger and project trackers. Verify each open ledger entry's real state before answering.
