---
name: status-report
description: >-
  Produce, edit or review a one-page project status report with fixed slots — Tasks, Changes since, Action required, Health, Unverified claims — for a capable peer who was not watching the work. Show task/subtask hierarchy, outcome progress, executor identity and execution state. Use when asked for a project-level status report or update, a weekly or milestone report, a state-of-play summary, a project hand-off snapshot, or a review of an existing report in this form. Preserve the slots while choosing a readable presentation. Do not use for changelogs, release notes, retrospectives, plans, roadmaps, metrics dashboards, activity logs, or a quick progress note on one task inside an ongoing conversation.
---

# Project Status Report

Write a one-page document — or edit or review one against every rule here — that answers, in order: where does the project stand, what changed since last time, and what action is required of someone. The reader is a capable peer with one screen of attention who was not watching the work, so state is the product — not a diary, changelog, plan, retrospective, or metrics dashboard. Every claim either carries a reference the reader can open or is marked unverified in place. The report names the revision and the time it was read at, which change only when its sources are re-read, so the next report can diff from it.

Priority order, highest first: **grounded evidence → complete picture → legible progress → the reader's next action → concision → fixed form.** When two rules collide, the higher one wins; concision never buys itself a dropped task or an unreferenced claim.

Nothing here depends on a particular version-control host, CI vendor, issue tracker, command line, or renderer. Evidence is named by kind — a commit id, a change-request number, a run id, a session id, a file path, a document anchor, a filing section, a scoring sheet — never by tool. Look for the thing; choose your own way to reach it.

## Form

Slots print in this order, always, whatever the project:

```
# <Project> — <date and time with zone> @ <revision>
<verdict>
## Tasks
## Changes since <prior anchor>
## Action required
## Health
## Unverified claims
```

A section with nothing to report prints `None.` A section not examined this cycle prints `Not checked.` A section whose sources were all unreachable prints `Not checked.` and gets one `Unverified claims` line naming what would confirm it. A section whose sources were partly reached prints what was reached, marks each field it could not fill `(unverified)`, and gives each such field an `Unverified claims` line. Never omit a heading: an absent heading and an unexamined project read identically. Length budget is at most about 50 lines — a chosen editorial ceiling, not a target, so a small project's report is shorter. Count every physical line — headings, blanks, table rows, fenced blocks.

Use one report language for headings, column labels, status labels and prose; the English labels here specify meanings and may be translated consistently. Preserve source identifiers and proper names. Explain an unfamiliar abbreviation only when its meaning is known from the sources. Reserve `—` for a structurally inapplicable field; write `None` for a checked absence and `Unknown (unverified)` for missing information.

## Passes

### 1. Gather — match the sources to the requested scope

For a current report, collect the project's applicable sources: history since the last anchor; open change requests and review state; automated checks on the current revision; tracking documents, specs and plans; confirmed assignments and task-linked live runs or sessions, or people's latest dated activity; test and coverage output with its date; release or deployment state and what reached users; and the prior report's anchor and counts. Mark claims whose sources cannot be reached unverified and record what would confirm them. For a review limited to supplied text or readability, assess that text and its stated evidence; preserve reported facts, identify unresolved claims, and keep its anchor. A current-state audit requires current sources; a presentation review does not establish current project facts.

### 2. Build the Tasks table

Retain these fields: Task, Subtask, Status, Progress, Executor, Dependency, Evidence. Use `Work | Status | Progress | Executor | Dependency | Evidence` with task and subtask paths in Work, or separate Task and Subtask columns when they fit legibly. Keep long explanations in a source note linked from the relevant cell; the note must contain the specific locator and counts toward the length budget. Reject a `Next` column: a per-task forward action is plan content. Order inside the Tasks slot is fixed: Blocked line, then the status-count line if licensed, then the graph if licensed, then the table and any source notes.

- **Two levels, task then subtask.** Make task names bold. In Work, write the task name on its task row and `<Task> / <Subtask>` on each subtask row. In split columns, repeat the task name on subtask rows; a task row writes `—` in Subtask. Task rows write `—` in Executor and Dependency. Keep subtasks directly below their task, with no third level. A task with exactly one subtask still lists it unless the cap folds it, because the subtask row carries execution state. Model each stage the project has as its own subtask — for example `Development`, `Review`, `Release` — rather than as a status.
- **Subtask Status** — six lifecycle states:
  - `Not started` — not begun.
  - `Running` — execution is active as of the report's observation. Evidence carries an as-of time and ties the executor to this subtask: for an agent, a run or session live at the header time; for a person, dated activity since the prior report (on a first report, since the start of the report's day). Task-linked liveness can establish `Running` with zero completed deliverables. A generic live process establishes only liveness; it establishes neither task identity nor outcome progress.
  - `Paused` — started, nobody is executing it now, and nothing blocks it.
  - `Blocked` — cannot begin or continue until the blocker named in Dependency acts, decides or arrives, including when the people it waits on are elsewhere. An unbegun stage waiting only for a known earlier stage of its own task is `Not started`. A started subtask with no executor and no other impediment is `Paused`; an unbegun one is `Not started`.
  - `Done` — complete.
  - `Dropped` — abandoned.

  A requested review is `Not started` until picked up; name the reviewer only if assigned. Code deployed but switched off for everyone is not released: its release subtask stays short of `Done`, and its Progress carries exposure, for example `5/9 handlers exposed`. When a source asserts a state without sufficient evidence, qualify that state `(unverified)`; when the state itself is unknown, write `Unknown (unverified)`. Missing evidence alone does not establish `Paused`, `Blocked` or `Not started`.
- **Task Status is derived from its subtasks, never hand-written.** Apply the first rule that matches: any subtask `Blocked` → `Blocked`; all subtasks `Dropped` → `Dropped`; all subtasks `Done` or `Dropped`, at least one `Done` → `Done`; all subtasks `Not started` → `Not started`; otherwise → `In progress`. Those five are the task lifecycle states. If uncertain subtask states could alter the result, qualify it `(unverified)`; if no result is supported, write `Unknown (unverified)`.
- **Terminal task states are `Done` and `Dropped` only.** A terminal task collapses to its single task row, with no subtask rows, appears in exactly one report so the reader sees the closure, then leaves. A non-terminal task never disappears, however quiet.
- **Executor** identifies the actual executor for `Running`, or the confirmed assignee for other states: an agent run/session ID or a person's name. A model name or role alone identifies neither. Prefix a proposed assignment `Planned:`; preserve a model or role only as useful context beside the identity or its missing-information marker. Write `Unassigned` only for a confirmed lack of assignment, and `Unknown (unverified)` when identity is missing. Read execution state from Status. A verified `Running` subtask always has an identified actual executor.
- **Dependency** distinguishes `None` (checked, no dependency), `After <Task> / <Subtask>` (a known routine predecessor for a `Not started` stage), `Blocked by <blocker>` (for `Blocked`), and `Unknown (unverified)` (not established). A blocker names another subtask as `<Task> / <Subtask>`, a person or team, an `Action required` item by its ask, or an external event. Do not infer a dependency from row order, stage names or an authorization. Keep intent, proposed sequencing and dates out of this field.
- **Paused needs an ask.** Every `Paused` subtask has a matching `Action required` item, a **Decision** to assign an executor or confirm the pause; where no owner is known, the ask is "who owns this?". A pause that someone confirmed stays `Paused`, and its item stays open, naming who confirmed it, until the subtask resumes.
- **Evidence** is never blank. Cite an openable source that supports the particular status, count, identity or dependency claimed; qualify unsupported fields `(unverified)` and give their confirming source in `Unverified claims`. Use `unverified — see Unverified claims` when no supporting source is available. A task row points at the tracking source for its full scope, with closure evidence for a terminal task. A specific file and section may support an inspected result; a glob or directory is only a place to search. Authorization proves scope, an assignment proves assignment, and task-linked liveness proves execution; none alone proves completion. A `Not started` subtask may cite its scope or write `—` for Evidence only when it makes no other claim needing support.
- **Order deterministically**, so two people sort the same data identically: tasks by attention order `Blocked, Unknown, In progress, Not started, Done, Dropped`, then alphabetically on task name; subtasks under their task in known execution order — for example `Development` before `Review` before `Release`. Ordering alone asserts no dependency.
- **Cap at 10 tasks and 20 table rows.** When over either cap, roll the terminal tasks into one row naming each of them, whose Status follows the derivation rule applied to them, and whose Progress counts them by status (`2 done · 1 dropped`); then fold all of a non-terminal task's subtask rows at once into a count in its task row's Progress, in the order `blocked · running · paused · not started · done · dropped · unknown`, for example `1 blocked · 2 not started · 3 done`. Retain unverified qualifiers on folded counts. Fold first the tasks whose subtasks are all `Not started`, `Done` or `Dropped`, then the others, until the table fits 20 rows or every task is folded; a folded `Blocked` or `Paused` subtask still appears on the Blocked line or in `Action required`, and a folded `Running` subtask's identity and as-of evidence move into its task row's Evidence cell. Never drop a task to fit. If more than 10 non-terminal tasks remain, print them all — complete picture outranks concision — and say so in the verdict.

The shape, in four tasks — a subtask blocked by another subtask, an agent running now, a paused subtask with its matching `Action required` item, a done development subtask followed by a running review, and a done task shown once:

```
# Payments — 2026-10-15 08:30 UTC @ 4ab7de1
<verdict>
## Tasks
Blocked: Payout rails / Reconciliation is blocked by Currency service / Rollout.
```

| Work | Status | Progress | Executor | Dependency | Evidence |
| --- | --- | --- | --- | --- | --- |
| **Payout rails** | Blocked | 0/2 subtasks done | — | — | CR-118 task checklist |
| Payout rails / Reconciliation | Blocked | 2/7 rails reconciled | Session S-51 | Blocked by Currency service / Rollout | CR-118 reconciliation record |
| Payout rails / Review | Not started | — | Unassigned | After Payout rails / Reconciliation | CR-118 review assignment and sequence |
| **Currency service** | In progress | 0/2 subtasks done | — | — | CR-120 task checklist |
| Currency service / Implementation | Running | 8/9 handlers implemented | Session S-42 | None | CR-120 handler checklist; run 9913 linked to S-42, live at 08:30 UTC |
| Currency service / Rollout | Paused | 5/9 handlers exposed | Unassigned | None | CR-120 rollout record; commit e91f0c2 (2026-10-09) |
| **Refund flow** | In progress | 1/2 subtasks done | — | — | CR-131 task checklist |
| Refund flow / Development | Done | 4/4 endpoints implemented | Session S-37 | None | CR-131 assignment; commit 7c21e0a |
| Refund flow / Review | Running | 5/8 review comments resolved | Li Wei | None | CR-131 review checklist, comment at 08:10 UTC |
| **Fraud rules** | Done (was In progress) | 2/2 subtasks done | — | — | CR-127 closed checklist |

Its matching `Action required` item; Reconciliation needs no item of its own, because its chain ends at Rollout:

`- **Decision** — Currency service / Rollout has no executor and nothing blocks it: assign an executor or confirm the pause — unblocks when an executor is named, owner payments team lead — Payout rails / Reconciliation stays blocked — commit e91f0c2`

### 3. Count progress — the denominator rule

Progress counts completed deliverables or satisfied criteria, with their stage explicit — drafted, reviewed, delivered or exposed are different outcomes. **The denominator must be an enumerable set that exists today and could be listed on request**, such as a task's subtasks or success criteria. Without a fixed set, write the numerator and its unit alone — `4 states researched, total set not fixed`. Lines written, diff size, elapsed time and live-process counts describe activity; they do not establish how much of the intended outcome is complete. If only activity is known, write `Outcome progress unverified` and keep useful activity detail in an evidence note. Do not infer zero completed outcomes from missing evidence.

- A task row writes `<done subtasks>/<total subtasks> subtasks done`; its set is the tracked subtasks, including any folded from view. `Dropped` subtasks count in neither number. A task with zero or one counted subtask writes `—`. This measures closure count, not effort, time remaining or an overall completion percentage; do not compare unlike units or weight them equally by implication.
- A subtask row counts its own real units. A `Not started` subtask writes `—`; there are no units yet to count.
- Never write a denominator of one (`0/1`, `1/1`): it adds nothing the Status has not said, while reading as a measured ratio.
- Never a bare percentage. This governs Progress; Health's coverage field is a percentage by definition.
- Two axes on one subtask — built and exposed — are written as both, separated by a semicolon.
- Mark movement in the cell: `(unchanged)` only where the row's status moved but its count did not, `(new)` for a row absent then, `(+n)` for a changed count, `(was <status>)` for a changed status. `(was <status>)` follows the Status value in the Status cell, and every other marker goes in Progress; the status vocabularies apply to the value before the marker. Mark only rows that changed; a delta on every row is noise. A first report carries no delta markers. A task row, and any row carrying a folded count, marks movement on Status only.
- If the unit or denominator changed, write `(rebaselined from <old count>)` and make the rebaseline a `Changes since` bullet.
- A count may carry a bar under pass 9. The count and unit remain the claim; omit the bar when it adds width without helping the reader.

### 4. Write `Changes since <prior anchor>`

Bullets, cap five. On overflow, fold changes of the same kind into one bullet, then keep the most consequential; the table's delta markers still show every status and count change. A change qualifies only if it altered a task's or a subtask's status, altered a progress count, or opened or closed an `Action required` item. Each bullet states the change, what it means, and a reference. Never restate a current count on its own; a count may appear only as the endpoint of a stated transition. **Effort is not a change.** On a first report the heading reads `## Changes since — first report` and the body is one line stating that the Tasks table is the baseline the next report diffs from.

### 5. Write `Action required`

An item belongs in this one slot only when someone other than the writer must act or decide before the work can proceed: a named person or team, an owner outside the project's control, or, where no owner is known, whoever can assign one. It is not a backlog. Each item opens with its type: **Blocked** (the action is known, someone must perform it) or **Decision** (the action is unknown, someone must choose). Format:

`- **<Blocked|Decision>** — <ask> — unblocks when <action or date>, owner <who, or "outside the project's control"> — <cost of leaving it> — <reference>`

A carried item marks its age: `(open since <anchor>)`. Order by cost of inaction, not by type. **A `Blocked` subtask is invalid without a matching item here, unless its Dependency names another subtask as its blocker**; the Blocked line carries that dependency. Follow the chain to the subtask at its end: a `Blocked` or `Paused` end carries the item under its own rule; a `Done` end no longer blocks, so re-derive the Status of the subtask it blocked; a `Running` end needs none; a `Not started` end needs a **Decision** item to start it or name its executor; a `Dropped` end needs a **Decision** item to re-scope or drop the blocked subtask. An unknown end needs an `Unverified claims` entry, without an invented ask. **A `Paused` subtask is invalid without a matching item here.** One item may match two subtasks if it names both. Cap five, and the cap yields to the matching rules: an item that matches a `Blocked` or `Paused` subtask is never cut, and if those items alone exceed five, merge the ones that share an owner and print the rest. On overflow of the other items, keep the most consequential and let the verdict name what was left out.

### 6. Write `Health` — product first, pipeline second

A section reading `Checks green · Tests 4180/4180 · Coverage 84%` can be true in every field while production rejects one payment in eight. So lead with `Product:` — what users are experiencing right now: normal, degraded (say how), down, or not yet released. Then the gates on one line: `Checks <state, as of <date>, or "none configured">` · `Tests <pass/total, how and when run>` · `Coverage <n%, gate n%, as of <date>, or "not measured">` · `Released <what reached users, where, when, or "not released">`. **Any field measured against something other than the header's revision carries its as-of date** — a nine-month-old green result read as current is the failure this prevents. If none of these surfaces exist, print `No build, test, or release surface exists for this project.` and list what stands in for it. Multi-surface projects get one line per released surface, capped at five; beyond five, one aggregate line plus one line for every surface that is not green. Every surface named in the anchor appears in Health, or the report says why it does not.

### 7. Write `Unverified claims` — and mark them inline too

Mark each unsupported claim `(unverified)` where it appears and give its confirming source in this section. A row's Evidence may still support its other fields; keep the scope of that support clear. **`unverified` is invalid unless it names what would confirm the claim.** Write claims in the neutral voice — "not confirmed for this report", never "I could not confirm". If anything in this section would change the verdict were it false, the verdict must say so.

### 8. Write the header and the verdict last

Header: `# <Project> — <YYYY-MM-DD HH:MM and zone> @ <revision or version; one per surface if there is more than one>`. The time and zone are always required: execution state changes within the hour, and every `Running` claim is read against them. **The anchor is the revision the Tasks table was read at, not the date the report was written.**

Verdict: two to three sentences — where the project stands, its direction since the last anchor, and the one item whose resolution most changes the picture. It is not a summary of every slot, and it introduces no new claim; it may restate only claims grounded elsewhere in the report. The only exceptions are naming the `Action required` items left out on overflow and stating that the task cap was exceeded.

### 9. Add illustrations only where they earn their line

Keep illustrations mechanically derivable from the Tasks table and useful at the destination's width. The Blocked line exposes dependencies across rows; other illustrations are optional under the conditions below. Omit an optional illustration that merely duplicates an easy scan or makes the report harder to read.

- **Mandatory, above the table:** `Blocked: <Task> / <Subtask> is blocked by <blocker>.` — one sentence per `Blocked` subtask, or the relations in one sentence separated by semicolons, using its Dependency blocker. Subtasks sharing one blocker may share a sentence: `Blocked: A / X and B / Y are blocked by C / Z.` Carry any unverified qualifier with the relation. With no `Blocked` subtask, write `Nothing blocked.` only when dependency information is confirmed; otherwise write `No confirmed blockers; dependencies unverified.` Do not frame it as release gating unless the report declares a release target.
- **Conditional, at 8 or more tasks:** `<N> tasks: <counts in the attention order>`. Below 8 it is a defect — a status tally is by definition the result of scanning one column, and at four tasks the line is longer than the column it summarizes.
- **Conditional, dependency graph:** include only when a chain has at least two blocking edges across three subtasks and the graph makes its indirect effects easier to see. One edge and shared blockers are already expressed by the Dependency cells and Blocked line. Use ASCII art in a fenced block if legible, otherwise one blocker per line with dependents comma-separated, or rely on the Blocked line. Keep the Blocked line in every case.
- **Conditional, delta markers:** only when a prior report exists, only on changed rows, folded into existing cells.
- **Rejected outright:** fixed-width progress bars of any kind; sparklines; burn or trend indicators; a milestone track unless named milestones already exist outside the report; a Tasks table sectioned into status groups — task-and-subtask nesting is not a section; the order in pass 2 governs, and grouping by status restates the Status column.
- **Conditional, progress bars:** use only for a small enumerable denominator of at most 12, when the symbols are distinguishable at the destination and help the reader scan comparable units. Explain the symbols once, for example `█ done, · remaining`; retain the numeric count and unit. A bar has exactly as many cells as the denominator and filled cells as the numerator: `3/5` is `███··`. It measures unit count, never effort. If two outcome axes need bars, label each axis; neither may hide the other. Omit bars for unknown totals, unlike-unit comparisons or crowded cells. Do not add another rendering beside a value unless this exact-unit rule makes it mechanically checkable.
- **No illustration may be the sole carrier of the answer to "what is blocked and by what."** Topology beyond that answer — chain order, indirect dependents — may live only in the graph. Deleting every illustration must still leave the reader knowing what is blocked and by what, never how deep the chain runs.

## Failure modes

- **The invented denominator** — a total nobody could list. Name the members or drop the denominator and write the numerator alone.
- **Activity reported as progress** — draft length, diff size or process count presented as completed outcomes. Keep activity as context, task-linked liveness as execution evidence, and outcome counts in Progress.
- **A task silently dropped** — quiet is not closed. A task leaves only after one report in `Done` or `Dropped`.
- **A release folded into another subtask** — a task closed as `Done` when its code is integrated or deployed but switched off for everyone. Release is its own subtask, short of `Done` until users have it.
- **`Running` without task-linked evidence** — an assignment, plan or generic live process presented as verified execution. Qualify an unsupported reported state unverified; classify an unknown state as unknown rather than infer that work stopped.
- **A paused subtask with no ask** — `Paused` without a matching `Action required` item hides work that nobody is doing. Every `Paused` subtask has one.
- **A hand-written task status** — a task Status that contradicts its subtasks, such as `In progress` over a `Blocked` subtask or `Done` over a `Paused` one. Derive it from the subtasks by the rule in pass 2.
- **An omitted heading** — the reader cannot tell an empty section from an unexamined one. Print every heading, with `None.` or `Not checked.`
- **A stale measurement read as current** — anything not measured against the header's revision carries its as-of date, or it is a lie by omission.
- **A green pipeline over a broken product** — gates can all pass while users are failing. `Product:` leads Health and states what users experience now.
- **`unverified` as a dodge** — a marker with no exit. Every unverified claim names the specific thing that would confirm it.
- **`Action required` as a backlog** — it holds only asks requiring someone other than the writer, capped at five (an item matching a `Blocked` or `Paused` subtask is never cut), ordered by cost of inaction.
- **`Changes since` as a changelog or effort diary** — it is a state delta with meaning and a reference, not a list of commits or hours.
- **A blocked subtask with no matching ask** — a `Blocked` subtask lacks an `Action required` item unless its Dependency names a subtask blocker. Follow that chain under pass 5; an unknown end needs verification rather than an invented ask.
- **A verdict that summarizes every slot** — it names the one item whose resolution most changes the picture, and introduces no claim not grounded below.
- **A reference that proves a different claim** — a scope document, live process or glob cited as proof of completed work. Locate the claimed result or mark that claim unverified.

## Self-check

- [ ] All seven slots present in fixed order; all five `##` headings printed, empty ones reading `None.` and unexamined ones `Not checked.`
- [ ] Header carries the revision the Tasks table was read at (one per surface if several), the date, and the time with its zone.
- [ ] The table retains Task, Subtask, Status, Progress, Executor, Dependency and Evidence, with Task/Subtask merged into Work or split legibly; bold task rows precede explicit subtask paths or repeated parent names; two levels only; a single-subtask task is listed unless folded; terminal tasks have no subtask rows.
- [ ] Status values follow the six subtask and five derived task lifecycle states, allowing delta and unverified qualifiers; unknown states are explicitly missing information, and uncertainty that could alter a roll-up is visible; terminal tasks appear exactly once before leaving.
- [ ] Every verified `Running` subtask has an actual identified executor and task-linked, as-of execution evidence (on its task row if folded); zero completed outcomes do not invalidate active execution, and liveness alone does not establish outcome progress.
- [ ] Executor distinguishes actual execution, confirmed assignment, `Planned:`, confirmed `Unassigned`, and unknown identity; a model or role alone is not treated as an identity.
- [ ] Dependency distinguishes checked `None`, a known routine `After` predecessor, a named `Blocked by` blocker, and `Unknown (unverified)`; task rows use `—`; sequencing is not inferred.
- [ ] Task Progress counts subtasks done, `—` for zero or one counted subtask, or folded states; outcome counts have enumerable denominators or numerator and unit alone, distinguish maturity, and imply no equal effort or overall percentage; unknown outcomes are marked, activity stays context, `Not started` uses `—`; no denominator of one or bare percentage.
- [ ] Optional bars help scan comparable units, have an explained distinguishable symbol pair and exact cells/filled cells matching a denominator of at most 12, retain the numeric count and unit, and do not crowd cells or imply effort; no other redundant rendering sits beside a value.
- [ ] Evidence supports the particular claims beside it, with specific openable locators or linked source notes; unsupported fields are marked in place and have matching `Unverified claims` entries naming what would confirm them; a `Not started` Evidence dash hides no other claim needing support.
- [ ] Tasks ordered by attention order, then alphabetically; subtasks in execution order; at most 10 tasks and 20 rows unless more than 10 non-terminal tasks remain, in which case all print, subtask rows still fold toward 20 rows, and the verdict says so; terminal tasks rolled, subtasks folded into counts, never a task dropped.
- [ ] The Blocked line is present and qualifies unverified relations or unknown dependencies; the status-count line appears only at 8+ tasks; a graph appears only when a chain of at least two edges benefits from it; deltas only on changed rows, and task rows mark Status only.
- [ ] Every `Blocked` subtask has a matching `Action required` item unless its blocker is another subtask, whose chain is handled under pass 5; unknown ends get verification entries, every `Paused` subtask has an ask, and all asks follow the format, cost ordering and cap without cutting items matching `Blocked` or `Paused` subtasks.
- [ ] `Changes since` bullets each changed a status, a count, or an ask, carry meaning and a reference, restate no count except as the endpoint of a stated transition, and number five or fewer.
- [ ] Health leads with the product; every measurement not taken against the header's revision carries its as-of date.
- [ ] The verdict names the one pivotal item, adds no new claim beyond naming the `Action required` items cut on overflow, or that the task cap was exceeded, and says so if an `Unverified claims` item would overturn it.
- [ ] Labels and prose use one report language, identifiers remain intact, and abbreviation meanings come from sources; `—`, checked absence and unknown information are distinct.
- [ ] The review stayed within the requested scope; a supplied-text review preserved reported facts and its anchor without claiming a current-state audit.
- [ ] At most about 50 lines (a small project's report is shorter), plain markdown, legible as plain text, with no tool- or vendor-generated signature and no first-person authoring voice; tool or vendor names serve evidence, release destinations or useful executor context.
