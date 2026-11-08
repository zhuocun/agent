---
name: status-report
description: >-
  Produce, edit or review a one-page project status report with fixed slots — Tasks, Changes since, Action required, Health, Unverified claims — for a capable peer who was not watching the work. Use when asked for a project-level status report or update, a weekly or milestone report, a state-of-play summary, a project hand-off snapshot, or a review of an existing report in this form. Do not use for changelogs, release notes, retrospectives, plans, roadmaps, metrics dashboards, activity logs, a quick progress note on one task inside an ongoing conversation, or the close-out or hand-off of a single task.
---

# Project Status Report

Write a one-page document — or edit or review one against every rule here — that answers, in order: where does the project stand, what changed since last time, and what action is required of someone. The reader is a capable peer with one screen of attention who was not watching the work, so state is the product — not a diary, changelog, plan, retrospective, or metrics dashboard. Every claim either carries a reference the reader can open or is marked unverified in place. The report names the revision and time its sources were read at, so the next report can diff from it.

Priority order, highest first: **grounded evidence → complete picture → legible progress → the reader's next action → concision → fixed form.** When two rules collide, the higher one wins; concision never buys itself a dropped task or an unreferenced claim.

Name evidence by kind — a commit id, a change-request number, a run id, a session id, a file path, a document anchor, a filing section, a scoring sheet — never by the tool that holds it.

This skill fixes the report's slots and their order, the Tasks table's fields and status values, the markers and fixed phrases it defines, and its voice and length rules, over any other guidance on the shape, length or layout of replies, such as another loaded instruction or a standing preference; where it sets no wording, that guidance governs the wording. Only an explicit instruction from the user about this report, or a template the user supplies or the destination documents, replaces the parts of this form it conflicts with; every claim still carries a reference or is marked unverified.

## Form

Slots print in this order:

```
# <Project> — <date and time with zone> @ <revision>
<verdict>
## Tasks
## Changes since <prior anchor>
## Action required
## Health
## Unverified claims
```

A section with nothing to report prints `None.` A section not examined this cycle prints `Not checked.` A section whose sources were all unreachable prints `Not checked.` and gets one `Unverified claims` line naming what would confirm it. A section whose sources were partly reached prints what was reached, marks each field it could not fill `(unverified)`, and gives each such field an `Unverified claims` line. Never omit a heading. Length budget is at most about 50 lines, a ceiling rather than a target. Count every physical line, blanks included.

Use one report language for headings, column labels, status labels and prose; the English labels here specify meanings and may be translated consistently. Preserve source identifiers and proper names. Explain an unfamiliar abbreviation only when its meaning is known from the sources. Reserve `—` for a structurally inapplicable field; write `None` for a checked absence and `Unknown (unverified)` for missing information.

Write plain Markdown that stays legible as plain text, in the neutral voice — "not confirmed for this report", never "I could not confirm" — with no first-person authoring voice and no tool- or vendor-generated signature. Name a tool or vendor only as evidence, a release destination or useful executor context.

## Reference files

Read each file in full when its condition holds, before applying its rules, and again after context compaction. To review or edit a report, also read each file whose condition the supplied report meets:

- `references/report-detail.md`: before collecting sources for a current report, and before building, editing or reviewing the Tasks table or Health.
- `references/prior-report.md`: when a prior report exists, before marking movement in the table or writing `Changes since`.
- `references/overflow.md`: when the Tasks table would exceed 10 tasks or 20 table rows or has a rolled or folded row, or more than five items qualify for `Action required`.
- `references/blocking-chains.md`: when a `Blocked` subtask's Dependency names another subtask as its blocker.
- `references/illustrations.md`: when a report has or adds any illustration other than the Blocked line.

## Passes

### 1. Gather — match the sources to the requested scope

For a current report, collect every applicable source that **Sources** in `references/report-detail.md` lists. Mark claims whose sources cannot be reached unverified and record what would confirm them. For a review limited to supplied text or readability, assess that text and its stated evidence; preserve reported facts, identify unresolved claims, and keep its anchor. A current-state audit requires current sources; a presentation review does not establish current project facts.

### 2. Build the Tasks table

Retain these fields: Task, Subtask, Status, Progress, Executor, Dependency, Evidence. Use `Work | Status | Progress | Executor | Dependency | Evidence` with task and subtask paths in Work, or separate Task and Subtask columns when they fit legibly. Reject a `Next` column: a per-task forward action is plan content. Order inside the Tasks slot is fixed: Blocked line, then the status-count line if licensed, then the graph if licensed, then the table and any source notes.

- **Two levels, task then subtask.** Make task names bold. In Work, write the task name on its task row and `<Task> / <Subtask>` on each subtask row. Task rows write `—` in Executor and Dependency. Keep subtasks directly below their task, with no third level.
- **Subtask Status** — six lifecycle states:
  - `Not started` — not begun.
  - `Running` — execution is active as of the report's observation; its task-linked, as-of evidence follows **Status** in `references/report-detail.md`.
  - `Paused` — started, nobody is executing it now, and nothing blocks it.
  - `Blocked` — cannot begin or continue until the blocker named in Dependency acts, decides or arrives, including when the people it waits on are elsewhere.
  - `Done` — complete.
  - `Dropped` — abandoned.
- **Task Status is derived from its subtasks, never hand-written.** Apply the first rule that matches: any subtask `Blocked` → `Blocked`; all subtasks `Dropped` → `Dropped`; all subtasks `Done` or `Dropped`, at least one `Done` → `Done`; all subtasks `Not started` → `Not started`; otherwise → `In progress`. Those five are the task lifecycle states. If uncertain subtask states could alter the result, qualify it `(unverified)`; if no result is supported, write `Unknown (unverified)`.
- **Terminal task states are `Done` and `Dropped` only.** A terminal task collapses to its single task row, with no subtask rows, appears in exactly one report so the reader sees the closure, then leaves. A non-terminal task never disappears, however quiet.
- **Executor** identifies the actual executor for `Running`, or the confirmed assignee for other states: an agent run/session ID or a person's name. A model name or role alone identifies neither. Prefix a proposed assignment `Planned:`. Write `Unassigned` only for a confirmed lack of assignment, and `Unknown (unverified)` when identity is missing.
- **Dependency** distinguishes `None` (checked, no dependency), `After <Task> / <Subtask>` (a known routine predecessor for a `Not started` stage), `Blocked by <blocker>` (for `Blocked`), and `Unknown (unverified)` (not established).
- **Paused needs an ask.** Every `Paused` subtask has a matching `Action required` item, a **Decision** to assign an executor or confirm the pause; where no owner is known, the ask is "who owns this?".
- **Evidence** is never blank. Cite an openable source that supports the particular status, count, identity or dependency claimed; qualify unsupported fields `(unverified)` and give their confirming source in `Unverified claims`. Use `unverified — see Unverified claims` when no supporting source is available.
- **Order deterministically**: tasks by attention order `Blocked, Unknown, In progress, Not started, Done, Dropped`, then alphabetically on task name; subtasks under their task in known execution order — for example `Development` before `Review` before `Release`. Ordering alone asserts no dependency.
- **Cap at 10 tasks and 20 table rows.** Never drop a task to fit. Over either cap, roll and fold rows as `references/overflow.md` directs.

### 3. Count progress — the denominator rule

Progress counts completed deliverables or satisfied criteria, with their stage explicit — drafted, reviewed, delivered or exposed are different outcomes. **The denominator must be an enumerable set that exists today and could be listed on request**, such as a task's subtasks or success criteria. Without a fixed set, write the numerator and its unit alone — `4 states researched, total set not fixed`. Lines written, diff size, elapsed time and live-process counts describe activity; they do not establish how much of the intended outcome is complete. If only activity is known, write `Outcome progress unverified` and keep useful activity detail in an evidence note. Progress is never a bare percentage; a reported share such as "80% done" with no countable set is activity, quoted unverified in the evidence note. Do not infer zero completed outcomes from missing evidence.

- Write each Progress cell as **Progress** in `references/report-detail.md` defines; a task row reads `<done subtasks>/<total subtasks> subtasks done` or `—`.
- When a prior report exists, mark movement only on changed rows, folded into existing cells, with the `(was <status>)`, `(new)`, `(+n)`, `(unchanged)` and `(rebaselined from <old count>)` markers of **Delta markers** in `references/prior-report.md`. A first report carries no delta markers.

### 4. Write `Changes since <prior anchor>`

On a first report the heading reads `## Changes since — first report` and the body is one line stating that the Tasks table is the baseline the next report diffs from. When a prior report exists, write this section as **Changes since** in `references/prior-report.md` directs.

### 5. Write `Action required`

An item belongs in this one slot only when someone other than the writer must act or decide before the work can proceed: a named person or team, an owner outside the project's control, or, where no owner is known, whoever can assign one. It is not a backlog. Each item opens with its type: **Blocked** (the action is known, someone must perform it) or **Decision** (the action is unknown, someone must choose). Format:

`- **<Blocked|Decision>** — <ask> — unblocks when <action or date>, owner <who, or "outside the project's control"> — <cost of leaving it> — <reference>`

A carried item marks its age: `(open since <anchor>)`. Order by cost of inaction, not by type. **A `Blocked` subtask is invalid without a matching item here, unless its Dependency names another subtask as its blocker**; the Blocked line carries that dependency. Follow such a chain to the subtask at its end as `references/blocking-chains.md` directs. **A `Paused` subtask is invalid without a matching item here.** One item may match two subtasks if it names both. Cap five; an item that matches a `Blocked` or `Paused` subtask is never cut. When more than five items qualify, apply **Action required overflow** in `references/overflow.md`.

### 6. Write `Health` — product first, pipeline second

Gates can all pass while users are failing, so lead with `Product:` — what users are experiencing right now: normal, degraded (say how), down, or not yet released. Then the gates line `Checks` · `Tests` · `Coverage` · `Released`, as **Gates** in `references/report-detail.md` gives. **Any field measured against something other than the header's revision carries its as-of date**. If none of these surfaces exist, print `No build, test, or release surface exists for this project.` and list what stands in for it. Every surface named in the header appears in Health, or the report says why it does not.

### 7. Write `Unverified claims` — and mark them inline too

Mark each unsupported claim `(unverified)` where it appears and give its confirming source in this section. A row's Evidence may still support its other fields; keep the scope of that support clear. **`unverified` is invalid unless it names what would confirm the claim.** If anything in this section would change the verdict were it false, the verdict must say so.

### 8. Write the header and the verdict last

Header: `# <Project> — <YYYY-MM-DD HH:MM and zone> @ <revision or version; one per surface if there is more than one>`. The time and zone are always required. **The anchor is the revision the Tasks table was read at, not the date the report was written.**

Verdict: two to three sentences — where the project stands, its direction since the last anchor, and the one item whose resolution most changes the picture. It is not a summary of every slot, and it introduces no new claim; it may restate only claims grounded elsewhere in the report. The only exceptions are naming the `Action required` items left out on overflow and stating that the task cap was exceeded.

### 9. Draw the Blocked line; add other illustrations only where licensed

Keep illustrations mechanically derivable from the Tasks table and useful at the destination's width. The Blocked line exposes dependencies across rows and is the only mandatory illustration. Add no other illustration — a status-count line, dependency graph, progress bar, milestone track or other rendering — unless `references/illustrations.md` licenses it. A progress bar, even a requested one, has one cell per unit of a denominator of at most 12.

- **Mandatory, above the table:** `Blocked: <Task> / <Subtask> is blocked by <blocker>.` — one sentence per `Blocked` subtask, or the relations in one sentence separated by semicolons, using its Dependency blocker. Subtasks sharing one blocker may share a sentence: `Blocked: A / X and B / Y are blocked by C / Z.` Carry any unverified qualifier with the relation. With no `Blocked` subtask, write `Nothing blocked.` only when dependency information is confirmed; otherwise write `No confirmed blockers; dependencies unverified.` Do not frame it as release gating unless the report declares a release target.
- **Do not section the Tasks table into status groups:** task-and-subtask nesting is not a section; the order in pass 2 governs.
- **No illustration may be the sole carrier of the answer to "what is blocked and by what."** Deleting every illustration must still leave the reader knowing what is blocked and by what.

## Self-check

- [ ] **Form:** unless **Scope and form** applies, seven slots in fixed order; every `##` heading printed: `None.` if empty; `Not checked.` if unexamined, or if wholly unreachable with one `Unverified claims` line; if partly reached, what was reached, each unfilled field `(unverified)` with its own `Unverified claims` line; one report language, identifiers intact, abbreviation meanings from sources; `—`, `None` and `Unknown (unverified)` distinct; at most about 50 lines; every other `## Form` rule.
- [ ] **Header and verdict:** the header carries the revision the Tasks table was read at (one per surface if several), the date, and the time with its zone; the verdict names the one pivotal item, adds no claim beyond the two pass 8 exceptions, and says so if an `Unverified claims` item would overturn it.
- [ ] **Tasks table:** the pass 2 fields, levels, terminal rows, derived statuses, order and caps, rolled and folded as `references/overflow.md` directs; never a task dropped.
- [ ] **Status and Executor:** each value follows pass 2 and **Status** and **Executor** in `references/report-detail.md`.
- [ ] **Dependency:** checked `None`, routine `After`, named `Blocked by` and `Unknown (unverified)` are distinct; task rows use `—`; sequencing is not inferred.
- [ ] **Progress:** each count follows pass 3 and **Progress** in `references/report-detail.md`.
- [ ] **Evidence:** never blank; each locator or linked source note opens to a specific place that supports the claims beside it; a `Not started` `—` hides no other claim; every unsupported field is marked in place and has an `Unverified claims` entry naming what would confirm it.
- [ ] **Illustrations:** the Blocked line is present and qualifies unverified relations or unknown dependencies; the table is not sectioned into status groups; each progress bar follows pass 9; every other illustration is one `references/illustrations.md` licenses.
- [ ] **Asks:** every `Paused` subtask, and every `Blocked` subtask without a subtask blocker, has its pass 5 item; a subtask blocker's chain is handled as `references/blocking-chains.md` directs; asks follow the pass 5 format, age marker, order and cap.
- [ ] **Prior report:** a first report has the `first report` heading and no delta markers; otherwise `Changes since` and the delta markers follow passes 3–4.
- [ ] **Health:** leads with the product; every measurement not taken against the header's revision carries its as-of date.
- [ ] **Scope and form:** a review or edit stayed within the requested scope, and a supplied-text review preserved reported facts and its anchor without claiming a current-state audit; an explicit user instruction about this report, or a template the user supplies or the destination documents, replaced only the parts of this form it conflicts with, and every claim still carries a reference or is marked unverified.
