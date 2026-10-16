---
name: status-report
description: >-
  Produce a one-page project status report with fixed slots — Tasks, Changes since, Action required, Health, Unverified claims — for a capable peer who was not watching the work. The Tasks table lists each task with its subtasks, and shows who is assigned to each subtask and whether it is being executed now. Use when asked for a project-level status report or update — where a project or its tasks stand, a weekly or milestone report, a state-of-play summary, or a hand-off snapshot of a project, including when the user asks mid-conversation where the whole project stands. Also use when editing or reviewing an existing report in this form; keep the form. Do not use for changelogs, release notes, retrospectives, plans, roadmaps, metrics dashboards, an activity log of what was worked on, or a quick progress note on one task inside an ongoing conversation — this is a state document, so forward per-item actions and effort narratives belong elsewhere.
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

A section with nothing to report prints `None.` A section not examined this cycle prints `Not checked.` A section whose sources were all unreachable prints `Not checked.` and gets one `Unverified claims` line naming what would confirm it. A section whose sources were partly reached prints what was reached, marks each field it could not fill `(unverified)`, and gives each such field an `Unverified claims` line. Never omit a heading: an absent heading and an unexamined project read identically. Length budget is at most about 50 lines — a chosen editorial ceiling, not a target, so a small project's report is shorter. Count every physical line — headings, blanks, table rows, fenced blocks. An illustration that costs six lines costs an eighth of the report.

## Passes

### 1. Gather — reach every source, and record every source you could not reach

Before writing a line, collect: history since the last anchor; open change requests and their review state; results of automated checks on the current revision; the project's own tracking documents (trackers, checklists, work logs), specs, and plans; who is assigned to each piece of work, which agent runs or sessions are live now, and each person's latest dated activity; test and coverage output with the date it was produced; release or deployment state and what actually reached users; and the prior report, for its anchor and counts. Look for each of these whatever your access — a shell, an API, or neither. **Any source you cannot reach becomes an `Unverified claims` line, never a guess, and never silence.** Record for each unreachable source what would confirm the claim that depends on it.

### 2. Build the Tasks table

Columns are exactly `Task | Subtask | Status | Progress | Executor | Blocked by | Evidence`. Reject a `Next` column: a per-task forward action is plan content. Order inside the Tasks slot is fixed: Blocked line, then the status-count line if licensed, then the graph if licensed, then the table.

- **Two levels, task then subtask.** A task row writes its name in Task and `—` in Subtask, Executor and Blocked by. Its subtask rows follow directly below it, with Task left empty and the subtask name in Subtask. A subtask has no subtasks. A task with exactly one subtask still lists it unless the cap folds it, because the subtask row carries execution state. Model each stage the project has as its own subtask — for example `Development`, `Review`, `Release` — rather than as a status.
- **Subtask Status** — exactly six words, no seventh:
  - `Not started` — not begun.
  - `Running` — its executor is working on it now. Valid only with evidence in the Evidence cell carrying an as-of time: for an agent, a run or session that is live at the header time; for a person, activity since the prior report (on a first report, since the start of the report's day) — a commit, a review comment, an edit — with its date or time. Such evidence is enough for `Running` when nothing blocks the subtask; without it the subtask is not `Running`.
  - `Paused` — started, nobody is executing it now, and nothing blocks it.
  - `Blocked` — cannot begin or continue until the thing named in Blocked by acts, decides or arrives, for any reason, including that the people it waits on are elsewhere; a stage that waits only for an earlier stage of its own task is `Not started`. An absent executor with nothing else in the way is `Paused`.
  - `Done` — complete.
  - `Dropped` — abandoned.

  A review that has been requested but not picked up is `Not started` with the reviewer as Executor; it becomes `Running` on the reviewer's first activity. Code deployed but switched off for everyone is not released: its release subtask stays short of `Done`, and its Progress carries exposure, for example `5/9 handlers exposed`.
- **Task Status is derived from its subtasks, never hand-written.** Apply the first rule that matches: any subtask `Blocked` → `Blocked`; all subtasks `Dropped` → `Dropped`; all subtasks `Done` or `Dropped`, at least one `Done` → `Done`; all subtasks `Not started` → `Not started`; otherwise → `In progress`. Those five are the only task statuses.
- **Terminal task states are `Done` and `Dropped` only.** A terminal task collapses to its single task row, with no subtask rows, appears in exactly one report so the reader sees the closure, then leaves. A non-terminal task never disappears, however quiet.
- **Executor** names the assigned executor: an agent session ID, a person's name, or `Unassigned`. Whether it is executing now is read from Status, never from Executor. A `Running` subtask is never `Unassigned`.
- **Blocked by** is filled only when the subtask's Status is `Blocked`; every other row writes `—`. It names one thing: another subtask written `<Task> / <Subtask>`, a named person or team, an `Action required` item by its ask, or an external event. Never a verb phrase of intent, never a sequence, never a date.
- **Paused needs an ask.** Every `Paused` subtask has a matching `Action required` item, a **Decision** to assign an executor or confirm the pause; where no owner is known, the ask is "who owns this?". A pause that someone confirmed stays `Paused`, and its item stays open, naming who confirmed it, until the subtask resumes.
- **Evidence** is never blank. It holds a reference that lands the reader on the specific thing, not a place to search — or the literal `unverified — see Unverified claims`. A task row points at where the task and its subtasks are tracked, not at a subset of them. A `Not started` subtask may point at where its scope is defined, or write `—`.
- **Order deterministically**, so two people sort the same data identically: tasks by attention order `Blocked, In progress, Not started, Done, Dropped`, then alphabetically on task name; subtasks under their task in execution order — `Development` before `Review` before `Release` — never alphabetically.
- **Cap at 10 tasks and 20 table rows.** When over either cap, roll the terminal tasks into one row whose Task cell names each of them, whose Status follows the derivation rule applied to them, and whose Progress counts them by status (`2 done · 1 dropped`); then fold all of a non-terminal task's subtask rows at once into a count in its task row's Progress, in the order `blocked · running · paused · not started · done · dropped`, for example `1 blocked · 2 not started · 3 done`. Fold first the tasks whose subtasks are all `Not started`, `Done` or `Dropped`, then the others, until the table fits 20 rows or every task is folded; a folded `Blocked` or `Paused` subtask still appears on the Blocked line or in `Action required`, and a folded `Running` subtask's as-of evidence moves into its task row's Evidence cell. Never drop a task to fit. If more than 10 non-terminal tasks remain, print them all — complete picture outranks concision — and say so in the verdict.

The shape, in four tasks — a subtask blocked by another subtask, an agent running now, a paused subtask with its matching `Action required` item, a done development subtask followed by a running review, and a done task shown once:

```
# Payments — 2026-10-15 08:30 UTC @ 4ab7de1
<verdict>
## Tasks
Blocked: Payout rails / Reconciliation is blocked by Currency service / Rollout.
```

| Task | Subtask | Status | Progress | Executor | Blocked by | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Payout rails | — | Blocked | `▓▓` 0/2 subtasks done | — | — | CR-118 |
| | Reconciliation | Blocked | `██▓▓▓▓▓` 2/7 rails reconciled | Agent session S-51 | Currency service / Rollout | CR-118 |
| | Review | Not started | — | Unassigned | — | — |
| Currency service | — | In progress | `▓▓` 0/2 subtasks done | — | — | CR-120 |
| | Implementation | Running | `████████▓` 8/9 handlers implemented | Agent session S-42 | — | run 9913, live at 08:30 UTC |
| | Rollout | Paused | `█████▓▓▓▓` 5/9 handlers exposed | Unassigned | — | commit e91f0c2 (2026-10-09) |
| Refund flow | — | In progress | `█▓` 1/2 subtasks done | — | — | CR-131 |
| | Development | Done | `████` 4/4 endpoints implemented | Agent session S-37 | — | commit 7c21e0a |
| | Review | Running | `█████▓▓▓` 5/8 review comments resolved | Li Wei | — | CR-131 review thread, comment at 08:10 UTC |
| Fraud rules | — | Done (was In progress) | `██` 2/2 subtasks done | — | — | CR-127 |

Its matching `Action required` item; Reconciliation needs no item of its own, because its chain ends at Rollout:

`- **Decision** — Currency service / Rollout has no executor and nothing blocks it: assign an executor or confirm the pause — unblocks when an executor is named, owner payments team lead — Payout rails / Reconciliation stays blocked — commit e91f0c2`

### 3. Count progress — the denominator rule

Progress is a count of real units, and **the denominator must be an enumerable set that exists today and could be listed on request**, such as the subtasks under a task or a checklist of a task's success criteria. If you cannot name the set's members, you do not have a denominator: write the numerator and its unit alone — `4 states researched, total set not fixed`.

- A task row writes `<done subtasks>/<total subtasks> subtasks done`, with a bar where pass 9 allows one; the set is enumerable by construction, since its members are the rows below. `Dropped` subtasks count in neither number. A task with zero or one counted subtask writes `—`.
- A subtask row counts its own real units. A `Not started` subtask writes `—`; there are no units yet to count.
- Never write a denominator of one (`0/1`, `1/1`): it adds nothing the Status has not said, while reading as a measured ratio.
- Never a bare percentage. This governs Progress; Health's coverage field is a percentage by definition.
- Two axes on one subtask — built and exposed — are written as both, separated by a semicolon.
- Mark movement in the cell: `(unchanged)` only where the row's status moved but its count did not, `(new)` for a row absent then, `(+n)` for a changed count, `(was <status>)` for a changed status. `(was <status>)` follows the Status value in the Status cell, and every other marker goes in Progress; the status vocabularies apply to the value before the marker. Mark only rows that changed; a delta on every row is noise. A first report carries no delta markers. A task row, and any row carrying a folded count, marks movement on Status only.
- If the unit or denominator changed, write `(rebaselined from <old count>)` and make the rebaseline a `Changes since` bullet.
- A task row's count carries a bar, and a subtask's count may carry one, each under the exact-denominator rule in pass 9. The count is the claim and the bar is an aid: when a cell cannot hold both, the bar goes first; a bar sits inside its cell, so dropping it saves no line against the length budget.

### 4. Write `Changes since <prior anchor>`

Bullets, cap five. On overflow, fold changes of the same kind into one bullet, then keep the most consequential; the table's delta markers still show every status and count change. A change qualifies only if it altered a task's or a subtask's status, altered a progress count, or opened or closed an `Action required` item. Each bullet states the change, what it means, and a reference. Never restate a current count on its own; a count may appear only as the endpoint of a stated transition. **Effort is not a change.** On a first report the heading reads `## Changes since — first report` and the body is one line stating that the Tasks table is the baseline the next report diffs from.

### 5. Write `Action required`

An item belongs in this one slot only when someone other than the writer must act or decide before the work can proceed: a named person or team, an owner outside the project's control, or, where no owner is known, whoever can assign one. It is not a backlog. Each item opens with its type: **Blocked** (the action is known, someone must perform it) or **Decision** (the action is unknown, someone must choose). Format:

`- **<Blocked|Decision>** — <ask> — unblocks when <action or date>, owner <who, or "outside the project's control"> — <cost of leaving it> — <reference>`

A carried item marks its age: `(open since <anchor>)`. Order by cost of inaction, not by type. **A `Blocked` subtask is invalid without a matching item here, unless its Blocked by names another subtask**; the Blocked line carries that dependency. Follow the chain to the subtask at its end: a `Blocked` or `Paused` end carries the item under its own rule; a `Done` end no longer blocks, so re-derive the Status of the subtask it blocked; a `Running` end needs none; a `Not started` end needs a **Decision** item to start it or name its executor; a `Dropped` end needs a **Decision** item to re-scope or drop the blocked subtask. **A `Paused` subtask is invalid without a matching item here.** One item may match two subtasks if it names both. Cap five, and the cap yields to the matching rules: an item that matches a `Blocked` or `Paused` subtask is never cut, and if those items alone exceed five, merge the ones that share an owner and print the rest. On overflow of the other items, keep the most consequential and let the verdict name what was left out.

### 6. Write `Health` — product first, pipeline second

A section reading `Checks green · Tests 4180/4180 · Coverage 84%` can be true in every field while production rejects one payment in eight. So lead with `Product:` — what users are experiencing right now: normal, degraded (say how), down, or not yet released. Then the gates on one line: `Checks <state, as of <date>, or "none configured">` · `Tests <pass/total, how and when run>` · `Coverage <n%, gate n%, as of <date>, or "not measured">` · `Released <what reached users, where, when, or "not released">`. **Any field measured against something other than the header's revision carries its as-of date** — a nine-month-old green result read as current is the failure this prevents. If none of these surfaces exist, print `No build, test, or release surface exists for this project.` and list what stands in for it. Multi-surface projects get one line per released surface, capped at five; beyond five, one aggregate line plus one line for every surface that is not green. Every surface named in the anchor appears in Health, or the report says why it does not.

### 7. Write `Unverified claims` — and mark them inline too

Both, always: real caveats run 15–25 words and will not fit a table cell, but a caveat three slots below a claim never reaches a skimmer. The Evidence cell carries the visible `unverified` marker; this section carries the detail. **`unverified` is invalid unless it names what would confirm the claim.** Write claims in the neutral voice — "not confirmed for this report", never "I could not confirm". A claim outside the Tasks table carries the marker inline in its own sentence — `(unverified)` — with the detail below. If anything in this section would change the verdict were it false, the verdict must say so.

### 8. Write the header and the verdict last

Header: `# <Project> — <YYYY-MM-DD HH:MM and zone> @ <revision or version; one per surface if there is more than one>`. The time and zone are always required: execution state changes within the hour, and every `Running` claim is read against them. **The anchor is the revision the Tasks table was read at, not the date the report was written.**

Verdict: two to three sentences — where the project stands, its direction since the last anchor, and the one item whose resolution most changes the picture. It is not a summary of every slot, and it introduces no new claim; it may restate only claims grounded elsewhere in the report. The only exceptions are naming the `Action required` items left out on overflow and stating that the task cap was exceeded.

### 9. Add illustrations only where they earn their line

An illustration is mandatory only if all three hold: constant cost (at most one line, never a new column); mechanically derivable from the Tasks table with zero judgment; answers something a single-column scan cannot. The Blocked line is the one illustration that meets all three. Every other illustration below is permitted only under its own stated condition.

- **Mandatory, above the table:** `Blocked: <Task> / <Subtask> is blocked by <blocker>.` — one sentence per `Blocked` subtask, or the relations in one sentence separated by semicolons, where the blocker is that subtask's Blocked by value. Subtasks sharing one blocker may share a sentence: `Blocked: A / X and B / Y are blocked by C / Z.` When no subtask is `Blocked`, write `Nothing blocked.` Derived mechanically from the Status and Blocked by columns. Do not frame it as release gating: a library between versions, a research repo, a continuously published docs site, and a draft spec have no release event. Release framing is an optional specialization only when the report declares a release target.
- **Conditional, at 8 or more tasks:** `<N> tasks: <counts in the attention order>`. Below 8 it is a defect — a status tally is by definition the result of scanning one column, and at four tasks the line is longer than the column it summarizes.
- **Conditional, dependency graph:** include if and only if some subtask is blocked by a subtask that is itself blocked by a subtask — two edges, three subtasks. One blocking edge is not a chain: it is already carried by the blocked subtask's Blocked by cell and the Blocked line, and a graph that redraws it is a defect. Transitive gating is non-local, so no per-row note reveals it. Fan-in and fan-out at any count are local and belong on the Blocked line, in its shared-blocker form; subtasks that cannot finish are `Blocked`, not `Running`, and need no graph. Degrade in three rungs, taking the highest rung the destination renders legibly, each leaving the Blocked sentence standing: **G1** ASCII-only art in a fenced block, legible with the fence delimiters visible as literal backtick lines, no character above U+007F; **G2** one blocker per line, its dependents comma-separated, no fence; **G3, the floor** the mandatory Blocked line in that same one-sentence form. The floor is always present, so the ladder costs nothing.
- **Conditional, delta markers:** only when a prior report exists, only on changed rows, folded into existing cells.
- **Rejected outright:** fixed-width progress bars of any kind; sparklines; burn or trend indicators; a milestone track unless named milestones already exist outside the report; a Tasks table sectioned into status groups — task-and-subtask nesting is not a section; the order in pass 2 governs, and grouping by status restates the Status column.
- **Conditional, the progress bar — exact-denominator only.** A bar carries exactly as many cells as the denominator and exactly as many filled cells as the numerator: `3/5` is `███▓▓`. Never a fixed-width track, which rounds `4/6` to seven cells of ten and so reads 70% for 66.7%; never a scale shared across rows, which flattens a four-unit job and a twelve-unit job to the same length. Written this way the track length *is* the denominator, so two rows stay as incomparable as their numbers already are. Use `█` filled and `▓` empty: they share a character-width class, so a bar's width does not change with its value. Do not use `░`, which sits in a different class and makes a fuller bar physically wider. Omit the bar where no enumerable denominator exists and where the denominator exceeds 12 — the number then stands alone, and a row that cannot be measured says so in words.
- **A subtask with a build axis and an exposure axis carries one bar per axis** against the same denominator. A full bar above an empty one is work that is finished and that nobody can see, which is the state a single number always hides.
- **No other rendering may sit beside the value it renders.** A bar in a hand-edited document is a second representation of one fact, and the only reason this one is permitted is that cells-equal-denominator makes a drifted bar mechanically checkable rather than silently wrong. Nothing that fails that test — no sparkline, no trend glyph, no percentage — earns the same licence.
- **No illustration may be the sole carrier of the answer to "what is blocked and by what."** Topology beyond that answer — chain order, indirect dependents — may live only in the graph. Deleting every illustration must still leave the reader knowing what is blocked and by what, never how deep the chain runs.

## Failure modes

- **The invented denominator** — a total nobody could list. Name the members or drop the denominator and write the numerator alone.
- **Activity reported as progress** — work done, meetings held, effort spent. A bullet or count qualifies only if a status, a count, or an `Action required` item changed.
- **A task silently dropped** — quiet is not closed. A task leaves only after one report in `Done` or `Dropped`.
- **A release folded into another subtask** — a task closed as `Done` when its code is integrated or deployed but switched off for everyone. Release is its own subtask, short of `Done` until users have it.
- **`Running` without live evidence** — an assignment, a plan, or activity from before the prior report read as work happening now. Without a run or session live at the header time, or a person's dated activity since the prior report, the subtask is `Paused`, `Blocked` or `Not started`, whichever fits.
- **A paused subtask with no ask** — `Paused` without a matching `Action required` item hides work that nobody is doing. Every `Paused` subtask has one.
- **A hand-written task status** — a task Status that contradicts its subtasks, such as `In progress` over a `Blocked` subtask or `Done` over a `Paused` one. Derive it from the subtasks by the rule in pass 2.
- **An omitted heading** — the reader cannot tell an empty section from an unexamined one. Print every heading, with `None.` or `Not checked.`
- **A stale measurement read as current** — anything not measured against the header's revision carries its as-of date, or it is a lie by omission.
- **A green pipeline over a broken product** — gates can all pass while users are failing. `Product:` leads Health and states what users experience now.
- **`unverified` as a dodge** — a marker with no exit. Every unverified claim names the specific thing that would confirm it.
- **`Action required` as a backlog** — it holds only asks requiring someone other than the writer, capped at five (an item matching a `Blocked` or `Paused` subtask is never cut), ordered by cost of inaction.
- **`Changes since` as a changelog or effort diary** — it is a state delta with meaning and a reference, not a list of commits or hours.
- **A blocked subtask with no matching ask** — a `Blocked` subtask without an item in `Action required` is an invalid report, unless its Blocked by names another subtask, whose chain then ends at a `Running` subtask or at one that carries the item.
- **A verdict that summarizes every slot** — it names the one item whose resolution most changes the picture, and introduces no claim not grounded below.
- **A reference that points at a place to search** — evidence lands the reader on the specific thing, or the cell reads `unverified`.

## Self-check

- [ ] All seven slots present in fixed order; all five `##` headings printed, empty ones reading `None.` and unexamined ones `Not checked.`
- [ ] Header carries the revision the Tasks table was read at (one per surface if several), the date, and the time with its zone.
- [ ] Columns are exactly `Task | Subtask | Status | Progress | Executor | Blocked by | Evidence`; each task row writes `—` in Subtask, Executor and Blocked by, and its subtask rows follow directly below with Task empty; two levels only; a single-subtask task still lists its subtask unless the cap folds it; a terminal task is one row with no subtask rows.
- [ ] Every subtask Status, ignoring a trailing `(was ...)`, is one of the six; every task Status is one of the five and equals what the derivation rule gives for its subtasks; terminal tasks appear exactly once before leaving.
- [ ] Every `Running` subtask has a named executor and Evidence (its task row's, if folded) showing a run or session live at the header time, or a person's dated activity since the prior report.
- [ ] Every Executor cell on a subtask row holds an agent session ID, a person's name, or `Unassigned`.
- [ ] Every Blocked by cell is `—` unless the subtask is `Blocked`, and then names one thing — a subtask as `<Task> / <Subtask>`, a person or team, an `Action required` item, or an external event; no verb phrase, sequence, or date.
- [ ] Every task row's Progress is `<done>/<total> subtasks done` with its bar where pass 9 allows one, `—` for zero or one counted subtask, or a folded count; every subtask Progress counts real units against an enumerable set, or a numerator and unit alone, or `—` when `Not started`; no denominator of one, no bare percentage.
- [ ] Every bar has cells equal to its denominator and filled cells equal to its numerator, uses `█` and `▓`, and is absent wherever there is no denominator or the denominator exceeds 12; no other rendering sits beside a value.
- [ ] Every Evidence cell is filled with an openable reference or the literal `unverified — see Unverified claims`, except a `Not started` subtask, which may write an em dash; every such marker has a matching section entry naming what would confirm it.
- [ ] Tasks ordered by attention order, then alphabetically; subtasks in execution order; at most 10 tasks and 20 rows unless more than 10 non-terminal tasks remain, in which case all print, subtask rows still fold toward 20 rows, and the verdict says so; terminal tasks rolled, subtasks folded into counts, never a task dropped.
- [ ] The Blocked line is present; the status-count line appears only at 8+ tasks; a graph appears only for a two-edge chain (three subtasks); deltas only on changed rows, and task rows mark Status only.
- [ ] Every `Blocked` subtask has a matching `Action required` item unless its Blocked by names another subtask, and then the chain's end carries one unless it is `Running`; every `Paused` subtask has one; every item follows the format, is ordered by cost of inaction, and is capped at five, except that no item matching a `Blocked` or `Paused` subtask was cut.
- [ ] `Changes since` bullets each changed a status, a count, or an ask, carry meaning and a reference, restate no count except as the endpoint of a stated transition, and number five or fewer.
- [ ] Health leads with the product; every measurement not taken against the header's revision carries its as-of date.
- [ ] The verdict names the one pivotal item, adds no new claim beyond naming the `Action required` items cut on overflow, or that the task cap was exceeded, and says so if an `Unverified claims` item would overturn it.
- [ ] At most about 50 lines (a small project's report is shorter), plain markdown, legible as plain text, with no tool- or vendor-generated signature and no first-person authoring voice; a tool or vendor name appears only where it says where something was released or where a reference lives.
