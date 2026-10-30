# Task ledger and interruptions

Use a durable record to reconstruct obligations and ownership after a new turn or compaction. Durability applies only while the chosen storage remains accessible. An in-session plan or agent list can supplement the ledger but cannot replace its run evidence.

## Location and registration

Use [SKILL.md — 1. Record ownership](../SKILL.md#1-record-ownership) for the ledger and project tracker. Link detailed run records from that ledger. If no tracker applies, use a writable task-scoped record outside version control. Choose storage suitable for the expected task lifetime and state its location.

Register an ask before dispatching its work and a run before launch. Link each attempt to its parent ask. Record unavailable fields explicitly instead of inventing them. For command startup, use [background-work.md — Choose ownership before launch](background-work.md#choose-ownership-before-launch). For agent startup, use [delegation.md — Brief and dispatch](delegation.md#brief-and-dispatch).

Each entry needs the following information, compacted into a table or short block:

| Information | Record |
| --- | --- |
| Ask and authority | User request, scope, constraints, latest steering, and any required acceptance |
| Task context | Actual feature tracker, branch or worktree, and relevant baseline, when applicable |
| Ownership | Controller, implementing agent or CLI, monitor, and exact returned handles with their tool namespaces |
| Attempt | Distinct attempt identity, launch time, brief, timeout or deadline, requested and confirmed model, effort, and speed |
| Evidence | Per-attempt log, final artifact, terminal exit record, freshness or provenance checks, and verdict |
| State | Task obligation separately from process state and result validation |
| Completion signal | How the controller obtains the result and who consumes it |
| Monitor lifecycle | Covered jobs, acknowledgement, last check, deadline, expiry action, and delivery scope |
| Next action and guards | Authorized continuation, dependency, retry limit, and actions that invalidate evidence |

Quote consequential user instructions, including stops and required acceptances, exactly. A ledger is not permission to execute a recorded action after scope changes.

## States and evidence

- **Task state:** Track queued, active, verifying, done, blocked, waiting for the user, or cancelled work. Name a real blocker or the exact pending question. Track acceptance only when the workflow requires it.
- **Run state:** Track not started, running, exited, interrupted, or unknown. Record exit status independently from the reported outcome.
- **Result state:** Keep unvalidated, incomplete, blocked, failed, and validated outcomes distinct. A finished run can leave its parent task active or blocked.

These are ordinary ledger labels. Goal-management or project lifecycle tools may enforce different transitions. Follow their current contracts instead of mapping labels automatically.

Mark a task done only after its required observable outcome and checks hold. Keep required review or acceptance pending until its evidence exists. Do not manufacture a user sign-off requirement for routine authorized work.

Record retries separately. Keep the prior exit, artifacts, and reason. Never apply an old failed exit or old successful artifact to a new attempt.

## Handle messages and races

Classify each message part as a new ask, scope change, question, acceptance, rejection, or stop. Update scope before any consequential continuation.

| Incoming event | Controller action |
| --- | --- |
| Question during a run | Preserve valid work, inventory remaining jobs, and follow [SKILL.md — 4. Wait, validate, and continue](../SKILL.md#4-wait-validate-and-continue) for the reply and same-turn resumption |
| Scope change | Keep compatible work, record any follow-up, prevent actions the new constraint forbids, and interrupt incompatible owned agents or jobs through supported scoped controls |
| Topic change | Retain outstanding obligations unless the user cancels or replaces them |
| Acceptance or rejection | Record the user's words and apply the owning workflow's actual next step |
| Stop with a concurrent completion | Apply the stop first, record the result, and suppress superseded continuation |
| Duplicate or delayed signal | Match the exact attempt and latest scope, then skip actions already completed |

When a stop requires process cleanup, identify the owned job before using a supported scoped stop. Resolve ambiguity without broad process matching. Preserve compatible in-flight work when a question or correction arrives.

Before a duplicate launch or retry, inspect ownership, current handles, and terminal evidence, including late completion. Another agent may already own the same next action. If a wait ends early, inventory the remaining jobs and monitor expiry before resuming.

## Guards and handoffs

Record only guards that protect actual work. A deploy, configuration change, or push with an automatic deployment trigger can invalidate evidence from a running test. Check those guards before mutations.

Use [SKILL.md — 5. Establish coverage before exit](../SKILL.md#5-establish-coverage-before-exit) for the handoff record and report. For open work, report the monitor's identity and coverage deadline. Distinguish active-session coverage from any verified ability to start another turn.
