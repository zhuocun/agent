---
name: status-report
description: >-
  Produce a one-page project status report with fixed slots — Ledger, Moved since, Needs a person, Health, Not verified — for a capable peer who was not watching the work. Use when asked for a project-level status report or update — where a project or its workstreams stand, a weekly or milestone report, a state-of-play summary, or a hand-off snapshot of a project. Also use when editing or reviewing an existing report in this form; keep the form. Do not use for changelogs, release notes, retrospectives, plans, roadmaps, metrics dashboards, or an activity log of what was worked on — this is a state document, so forward per-item actions and effort narratives belong elsewhere. Do not use for a quick progress note on the task in hand, which is an ordinary reply, or for recovering context after a compaction (use reorient).
---

# Project Status Report

Write a one-page document that answers, in order: where does the project stand, what moved since last time, and what needs a person. The reader is a capable peer with one screen of attention who was not watching the work, so state is the product — not a diary, changelog, plan, retrospective, or metrics dashboard. Every claim either carries a reference the reader can open or is marked unverified in place. The report names the revision it was read at, so the next report can diff from it.

Priority order, highest first: **grounded evidence → complete picture → legible progress → the reader's next action → concision → fixed form.** When two rules collide, the higher one wins; concision never buys itself a dropped workstream or an unreferenced claim.

Nothing here depends on a particular version-control host, CI vendor, issue tracker, command line, or renderer. Evidence is named by kind — a commit id, a change-request number, a run id, a file path, a document anchor, a filing section, a scoring sheet — never by tool. Look for the thing; choose your own way to reach it.

## Form

Slots print in this order, always, whatever the project:

```
# <Project> — <date> @ <revision>
<verdict>
## Ledger
## Moved since <prior anchor>
## Needs a person
## Health
## Not verified
```

A section with nothing to report prints `None.` A section not examined this cycle prints `Not checked.` A section whose sources were all unreachable prints `Not checked.` and gets one `Not verified` line naming what would confirm it. A section whose sources were partly reached prints what was reached, marks each field it could not fill `(unverified)`, and gives each such field a `Not verified` line. Never omit a heading: an absent heading and an unexamined project read identically. Length budget is at most about 50 lines — a chosen editorial ceiling, not a target, so a small project's report is shorter. It is not a property of any screen either: screen height is a viewer property and the report must not depend on one. Count every physical line — headings, blanks, table rows, fenced blocks. An illustration that costs six lines costs an eighth of the report.

## Passes

### 1. Gather — reach every source, and record every source you could not reach

Before writing a line, collect: history since the last anchor; open change requests and their review state; results of automated checks on the current revision; the project's own tracking documents, specs, and plans; test and coverage output with the date it was produced; release or deployment state and what actually reached users; and the prior report, for its anchor and counts. Look for each of these whatever your access — a shell, an API, or neither. **Any source you cannot reach becomes a `Not verified` line, never a guess, and never silence.** Record for each unreachable source what would confirm the claim that depends on it.

### 2. Build the Ledger

Columns are exactly `Workstream | Status | Progress | Waiting on | Evidence`. Reject a `Next` column: a per-workstream forward action is plan content. Order inside the Ledger slot is fixed: blocked-by line, then the status-count line if licensed, then the graph if licensed, then the table.

- **Status** — exactly seven words, no eighth: `Shipped` (in users' hands) · `Merged` (integrated into the canonical copy, not yet released) · `In review` (complete, awaiting approval) · `In progress` · `Blocked` · `Not started` · `Dropped`. Code deployed but switched off for everyone is `Merged`; carry exposure in Progress. `Blocked` means cannot proceed for any reason, including that the people are elsewhere, and outranks lifecycle position in the cell — Progress carries the position. Where the project has no separate release step, `Merged` collapses into `Shipped`; where it has no review step, `In review` is unused. A row awaiting a review that has been requested is `In review`, not `Blocked`; it becomes `Blocked` only once the review is overdue against a named date or the reviewer is unassigned.
- **Terminal states are `Shipped` and `Dropped` only.** `Merged` is a waypoint. A workstream leaves the Ledger only after appearing once in a terminal state, shown for exactly one report so the reader sees the closure, then absent. It never disappears while non-terminal, however quiet.
- **Waiting on** names the single thing the row's next state change depends on: a named person or team, a review, a decision by its `Needs a person` label, an external event, or — when the dependency is internal — the blocking workstream by name. Actively worked and depending on nothing outside itself is `in hand`; terminal rows write `—`. Never a verb phrase of intent, never a sequence, never a date. A non-terminal row that is neither `in hand` nor waiting on something nameable is stalled: give it a `Needs a person` item, and if no owner is known, that item's ask is "who owns this?".
- **Evidence** is never blank. It holds a reference that lands the reader on the specific thing, not a place to search — or the literal `unverified — see Not verified`. A `Not started` row may point at where its scope is defined, or write `—`.
- **Order deterministically**, so two people sort the same data identically: by attention order `Blocked, In review, In progress, Not started, Merged, Shipped, Dropped`, then alphabetically on workstream name.
- **Cap at 10 rows.** A row may cover a group: its Status is the least advanced among its sub-items (`Blocked` if any is blocked) and its Progress counts sub-items at each status in attention order, for example `1 blocked · 2 not started · 3 merged`. Fold sub-items into the count; never drop a workstream to fit. A group row's Evidence points at where the group's sub-items are enumerated, not at a subset of them.

The shape, in five rows — a blocked row waiting on another row, an exact-denominator bar, a two-axis count carrying a delta, a group row rolled up, and a row with no denominator and therefore no bar:

| Workstream | Status | Progress | Waiting on | Evidence |
| --- | --- | --- | --- | --- |
| Payout rails | Blocked | `██▓▓▓▓▓` 2/7 rails reconciled | Currency service | CR-118 |
| Fraud rules | In review | `███` 3/3 rule sets authored | review on CR-127 | unverified — see Not verified |
| Currency service | In progress | `████████▓` 8/9 handlers implemented; `█████▓▓▓▓` 5/9 exposed (+2) | in hand | commit 4ab7de1 |
| Locale bundles | In progress | 3 in progress · 3 shipped, of 6 | in hand | doc: locales.md#bundle-list |
| Merchant onboarding | In progress | 9 partners integrated, total set not fixed | in hand | doc: partners.md#status |

### 3. Count progress — the denominator rule

This is the rule the format lives or dies on. Progress is a count of real units, and **the denominator must be an enumerable set that exists today and could be listed on request.** If you cannot name its members, you do not have a denominator: write the numerator and its unit alone — `4 states researched, total set not fixed`.

- Never write a denominator of one (`0/1`, `1/1`): it adds nothing the Status has not said, while reading as a measured ratio.
- Never a bare percentage. This governs Progress; Health's coverage field is a percentage by definition.
- Two axes — built and exposed — are written as both, separated by a semicolon.
- A `Not started` row writes an em dash in Progress; there are no units yet to count.
- Mark movement in the cell: `(unchanged)` only where the row's status moved but its count did not, `(new)` for a row absent then, `(+n)` for a changed count, `(was <status>)` for a changed status. `(was <status>)` follows the Status value in the Status cell, and every other marker goes in Progress; the seven-word rule applies to the value before the marker. Mark only rows that changed; a delta on every row is noise. A first report carries no delta markers. A group row marks movement on Status only; its roll-up counts carry no delta.
- If the unit or denominator changed, write `(rebaselined from <old count>)` and make the rebaseline a `Moved since` bullet.
- A bar may accompany a count under the exact-denominator rule in pass 9. The count is the claim and the bar is an aid: if anything has to go, the bar goes first.

### 4. Write `Moved since <prior anchor>`

Bullets, cap five. On overflow, fold changes of the same kind into one bullet, then keep the most consequential; the Ledger's delta markers still show every status and count change. A change qualifies only if it altered a Ledger row's status, altered a progress count, or opened or closed a `Needs a person` item. Each bullet states the change, what it means, and a reference. Never restate a current count on its own; a count may appear only as the endpoint of a stated transition. **Effort is not a change.** On a first report the heading reads `## Moved since — first report` and the body is one line stating that the Ledger is the baseline the next report diffs from.

### 5. Write `Needs a person`

One slot; it replaces separate blocked and decision sections. An item belongs here only when someone other than the writer must act or decide before the work can proceed: a named person or team, an owner outside the project's control, or, where no owner is known, whoever can assign one. It is not a backlog. Each item opens with its type: **Blocked** (the action is known, someone must perform it) or **Decision** (the action is unknown, someone must choose). Format:

`- **<Blocked|Decision>** — <ask> — unblocks when <action or date>, owner <who, or "outside the project's control"> — <cost of leaving it> — <reference>`

A carried item marks its age: `(open since <anchor>)`. Order by cost of inaction, not by type. **A Ledger row with status `Blocked` is invalid without a matching item here, unless its `Waiting on` names another Ledger row**; the blocked-by line carries that dependency, and any item belongs to the row at the end of the chain. One item may match two rows if it names both. Cap five, and the cap yields to the matching rule: an item that matches a `Blocked` row is never cut, and if those items alone exceed five, merge the ones that share an owner and print the rest. On overflow of the other items, keep the most consequential and let the verdict name what was left out.

### 6. Write `Health` — product first, pipeline second

A section reading `Checks green · Tests 4180/4180 · Coverage 84%` can be true in every field while production rejects one payment in eight. So lead with `Product:` — what users are experiencing right now: normal, degraded (say how), down, or not yet released. Then the gates on one line: `Checks <state, as of <date>, or "none configured">` · `Tests <pass/total, how and when run>` · `Coverage <n%, gate n%, as of <date>, or "not measured">` · `Released <what reached users, where, when, or "not released">`. **Any field measured against something other than the current revision carries its as-of date** — a nine-month-old green result read as current is the failure this prevents. If none of these surfaces exist, print `No build, test, or release surface exists for this project.` and list what stands in for it. Multi-surface projects get one line per released surface, capped at five; beyond five, one aggregate line plus one line for every surface that is not green. Every surface named in the anchor appears in Health, or the report says why it does not.

### 7. Write `Not verified` — and mark it inline too

Both, always: real caveats run 15–25 words and will not fit a table cell, but a caveat three slots below a claim never reaches a skimmer. The Evidence cell carries the visible `unverified` marker; this section carries the detail. **`unverified` is invalid unless it names what would confirm the claim.** Write claims in the neutral voice — "not confirmed for this report", never "I could not confirm". A claim outside the Ledger carries the marker inline in its own sentence — `(unverified)` — with the detail below. If anything in this section would change the verdict were it false, the verdict must say so.

### 8. Write the header and the verdict last

Header: `# <Project> — <YYYY-MM-DD, plus time and zone if the situation moves faster than a day> @ <revision or version; one per surface if there is more than one>`. **The anchor is the revision the Ledger was read at, not the date the report was written.**

Verdict: two to three sentences — where the project stands, its direction since the last anchor, and the one item whose resolution most changes the picture. It is not a summary of every slot, and it introduces no new claim; it may restate only claims grounded elsewhere in the report. The one exception is naming the `Needs a person` items left out on overflow.

### 9. Add illustrations only where they earn their line

An illustration is mandatory only if all three hold: constant cost (at most one line, never a new column); mechanically derivable from the Ledger with zero judgment; answers something a single-column scan cannot. The blocked-by line is the one illustration that meets all three. Every other illustration below is permitted only under its own stated condition.

- **Mandatory, above the table:** `Blocked by: <blocker> -> <blocked rows>.` — one relation per blocker, relations separated by semicolons, where the blocker is each `Blocked` row's `Waiting on` value; the arrow points from the blocker to what it blocks. When no row is `Blocked`, write `Nothing blocked.` Derived mechanically from the Status and Waiting on columns. Do not frame it as release gating: a library between versions, a research repo, a continuously published docs site, and a draft spec have no release event. Release framing is an optional specialization only when the report declares a release target.
- **Conditional, at 8 or more rows:** `<N> workstreams: <counts in the attention order>`. Below 8 it is a defect — a status tally is by definition the result of scanning one column, and at four rows the line is longer than the column it summarizes. 8 is a chosen round number, not a derived one.
- **Conditional, dependency graph:** include if and only if some row is blocked by a row that is itself blocked by a row — two edges, three rows. One blocking edge is not a chain: it is already carried by the blocked row's `Waiting on` cell and the blocked-by line, and a graph that redraws it is a defect. Transitive gating is non-local, so no per-row note reveals it. Fan-in and fan-out at any count are local and belong on the blocked-by line, which may name the relation inline — `Blocked by: Auth -> Billing, Search.` Do not justify a graph with "three rows read In progress while none can finish" — those are three rows carrying the wrong Status, and the vocabulary already has `Blocked`. Degrade in three rungs, each leaving the blocked-by sentence standing: **G1** ASCII-only art in a fenced block, legible with the fence delimiters visible as literal backtick lines, no character above U+007F; **G2** one source per line, dependents comma-separated, no fence; **G3, the floor** the mandatory blocked-by line in that same inline relation form. The floor is always present, so the ladder costs nothing.
- **Conditional, delta markers:** only when a prior report exists, only on changed rows, folded into existing cells.
- **Rejected outright:** fixed-width progress bars of any kind; sparklines; burn or trend indicators; a milestone track unless named milestones already exist outside the report; a Ledger sectioned into groups — the order in pass 2 governs, and grouping by status restates the Status column.
- **Conditional, the progress bar — exact-denominator only.** A bar carries exactly as many cells as the denominator and exactly as many filled cells as the numerator: `3/5` is `███▓▓`. Never a fixed-width track, which rounds `4/6` to seven cells of ten and so reads 70% for 66.7%; never a scale shared across rows, which flattens a four-unit job and a twelve-unit job to the same length. Written this way the track length *is* the denominator, so two rows stay as incomparable as their numbers already are. Use `█` filled and `▓` empty: they share a character-width class, so a bar's width does not change with its value. Do not use `░`, which sits in a different class and makes a fuller bar physically wider. Omit the bar where no enumerable denominator exists and where the denominator exceeds 12 — the number then stands alone, and a row that cannot be measured says so in words.
- **A row with a build axis and an exposure axis carries one bar per axis** against the same denominator. A full bar above an empty one is a workstream that is finished and that nobody can see, which is the state a single number always hides.
- **No other rendering may sit beside the value it renders.** A bar in a hand-edited document is a second representation of one fact, and the only reason this one is permitted is that cells-equal-denominator makes a drifted bar mechanically checkable rather than silently wrong. Nothing that fails that test — no sparkline, no trend glyph, no percentage — earns the same licence.
- **No illustration may be the sole carrier of the answer to "what is blocked and by what."** Topology beyond that answer — chain order, indirect dependents — may live only in the graph. Deleting every illustration must still leave the reader knowing what is blocked and by what, never how deep the chain runs.

## Failure modes

- **The invented denominator** — a total nobody could list. Name the members or drop the denominator and write the numerator alone.
- **Activity reported as progress** — work done, meetings held, effort spent. A bullet or count qualifies only if a status, a count, or a `Needs a person` item changed.
- **A workstream silently dropped** — quiet is not closed. A row leaves only after one report in `Shipped` or `Dropped`.
- **A row parked at `Merged`** — it vanishes before it ships. `Merged` is a waypoint; keep the row until users have it.
- **An omitted heading** — the reader cannot tell an empty section from an unexamined one. Print every heading, with `None.` or `Not checked.`
- **A stale measurement read as current** — anything not measured against the current revision carries its as-of date, or it is a lie by omission.
- **A green pipeline over a broken product** — gates can all pass while users are failing. `Product:` leads Health and states what users experience now.
- **`unverified` as a dodge** — a marker with no exit. Every unverified claim names the specific thing that would confirm it.
- **`Needs a person` as a backlog** — it holds only asks requiring someone other than the writer, capped at five (an item matching a `Blocked` row is never cut), ordered by cost of inaction.
- **`Moved since` as a changelog or effort diary** — it is a state delta with meaning and a reference, not a list of commits or hours.
- **A blocked row with no matching ask** — `Blocked` in the Ledger without an item in `Needs a person` is an invalid report, unless the row's `Waiting on` names another Ledger row.
- **A verdict that summarizes every slot** — it names the one item whose resolution most changes the picture, and introduces no claim not grounded below.
- **A reference that points at a place to search** — evidence lands the reader on the specific thing, or the cell reads `unverified`.

## Self-check

- [ ] All seven slots present in fixed order; all five `##` headings printed, empty ones reading `None.` and unexamined ones `Not checked.`
- [ ] Header carries the revision the Ledger was read at (one per surface if several) and the date at the right granularity.
- [ ] Every Progress cell counts real units against an enumerable set, or a numerator and unit alone; no denominator of one, no bare percentage.
- [ ] Every bar has cells equal to its denominator and filled cells equal to its numerator, uses `█` and `▓`, and is absent wherever there is no denominator or the denominator exceeds 12; no other rendering sits beside a value.
- [ ] Every Status, ignoring a trailing `(was ...)`, is one of the seven; every `Merged` row is still present because users do not have it yet; terminal rows appear exactly once before leaving.
- [ ] Every `Waiting on` names one nameable thing, `in hand`, or `—`; no verb phrase, sequence, or date; every stalled row has an ask.
- [ ] Every Evidence cell is filled with an openable reference or the literal `unverified — see Not verified`, except a `Not started` row, which may write an em dash; every such marker has a matching section entry naming what would confirm it.
- [ ] Rows ordered by attention order, then alphabetically; Ledger at 10 rows or fewer with groups rolled up, never truncated.
- [ ] The blocked-by line is present; the status-count line appears only at 8+ rows; a graph appears only for a two-edge chain (three rows); deltas only on changed rows.
- [ ] Every `Blocked` row has a matching `Needs a person` item, unless its `Waiting on` names another Ledger row; every item follows the format, is ordered by cost of inaction, and is capped at five, except that no item matching a `Blocked` row was cut.
- [ ] `Moved since` bullets each changed a status, a count, or an ask, carry meaning and a reference, restate no count except as the endpoint of a stated transition, and number five or fewer.
- [ ] Health leads with the product; every measurement not taken against the current revision carries its as-of date.
- [ ] The verdict names the one pivotal item, adds no new claim beyond naming the `Needs a person` items cut on overflow, and says so if a `Not verified` item would overturn it.
- [ ] At most about 50 lines (a small project's report is shorter), plain markdown, legible as plain text, with no tool- or vendor-generated signature and no first-person authoring voice; a tool or vendor name appears only where it says where something shipped or where a reference lives.
