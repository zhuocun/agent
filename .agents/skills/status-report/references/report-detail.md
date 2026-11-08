# Report detail

Apply this file before collecting sources for a current report, and before building, editing or reviewing the Tasks table or Health.

## Sources

For a current report, collect the project's applicable sources: history since the last anchor; open change requests and review state; automated checks on the current revision; tracking documents, specs and plans; confirmed assignments and task-linked live runs or sessions, or people's latest dated activity; test and coverage output with its date; release or deployment state and what reached users; and the prior report's anchor and counts.

## Work

In split columns, repeat the task name on subtask rows; a task row writes `—` in Subtask. A task with exactly one subtask still lists it unless the cap folds it, because the subtask row carries execution state. Model each stage the project has as its own subtask — for example `Development`, `Review`, `Release` — rather than as a status. Keep long explanations in a source note linked from the relevant cell; the note must contain the specific locator and counts toward the length budget.

## Status

`Running` evidence carries an as-of time and ties the executor to this subtask: for an agent, a run or session live at the header time; for a person, dated activity since the prior report (on a first report, since the start of the report's day). Task-linked liveness can establish `Running` with zero completed deliverables. A generic live process establishes only liveness; it establishes neither task identity nor outcome progress.

An unbegun stage waiting only for a known earlier stage of its own task is `Not started`. A started subtask with no executor and no other impediment is `Paused`; an unbegun one is `Not started`. A pause that someone confirmed stays `Paused`, and its item stays open, naming who confirmed it, until the subtask resumes.

A requested review is `Not started` until picked up; name the reviewer only if assigned. Code deployed but switched off for everyone is not released: its release subtask stays short of `Done`, and its Progress carries exposure, for example `5/9 handlers exposed`. When a source asserts a state without sufficient evidence, qualify that state `(unverified)`; when the state itself is unknown, write `Unknown (unverified)`. Missing evidence alone does not establish `Paused`, `Blocked` or `Not started`.

## Executor

Preserve a model or role only as useful context beside the identity or its missing-information marker. Read execution state from Status. A verified `Running` subtask always has an identified actual executor.

## Dependency

A blocker names another subtask as `<Task> / <Subtask>`, a person or team, an `Action required` item by its ask, or an external event. Do not infer a dependency from row order, stage names or an authorization. Keep intent, proposed sequencing and dates out of this field.

## Evidence

A task row points at the tracking source for its full scope, with closure evidence for a terminal task. A specific file and section may support an inspected result; a glob or directory is only a place to search. Authorization proves scope, an assignment proves assignment, and task-linked liveness proves execution; none alone proves completion. A `Not started` subtask may cite its scope or write `—` for Evidence only when it makes no other claim needing support.

## Progress

- A task row writes `<done subtasks>/<total subtasks> subtasks done`; its set is the tracked subtasks, including any folded from view. `Dropped` subtasks count in neither number. A task with zero or one counted subtask writes `—`. This measures closure count, not effort, time remaining or an overall completion percentage; do not compare unlike units or weight them equally by implication.
- A subtask row counts its own real units. A `Not started` subtask writes `—`; there are no units yet to count.
- Never write a denominator of one (`0/1`, `1/1`): it adds nothing the Status has not said, while reading as a measured ratio.
- Health's coverage field is a percentage by definition; pass 3's percentage rule governs Progress only.
- Two axes on one subtask — built and exposed — are written as both, separated by a semicolon.

## Gates

Write the gates on one line: `Checks <state, as of <date>, or "none configured">` · `Tests <pass/total, how and when run>` · `Coverage <n%, gate n%, as of <date>, or "not measured">` · `Released <what reached users, where, when, or "not released">`.

## Surfaces

Multi-surface projects get one line per released surface, capped at five; beyond five, one aggregate line plus one line for every surface that is not green.
