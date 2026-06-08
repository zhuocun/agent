---
name: reorient
description: >-
  Reconstruct and verify your working context after a context compaction, then resume an in-progress task safely. Use when a long conversation was summarized and detail was lost; when you are unsure what is finished versus still pending; or when the user says "catch up", "where were we", "recap", "rebuild context", "restore context", "re-orient", or "continue where we left off". The summary is a lossy pointer — confirm what is done against ground truth (git, PRs, CI, the actual files) before acting, never from the summary alone. Do not use for a brand-new task with no prior work, a trivial single-step request, or when full context is already in hand.
---

# Context Rebuild

A compaction replaces a long conversation with a short summary: detail is dropped, "done" is asserted without proof, and the *why* behind earlier decisions is gone. The summary is a pointer to ground truth, not ground truth itself. Before you take any action that assumes the prior state, **rebuild that state from the sources that cannot lie — the repo, the history, the files — then report a crisp recap so the user can confirm you are oriented.**

Priority order, highest first: **ground truth over the summary → understand before acting → verified-done over assumed-done → report 1–3 to the user, keep #4 internal.** When the summary and the repo disagree, the repo wins.

## Rebuild passes

Run these in order. Passes 1–4 reconstruct context; pass 5 reports it. Do not act irreversibly (commit, push, merge, deploy, delete) until 1–4 leave you able to resume without guessing.

### 1. Recover the thread — what have we been doing

Read the compaction summary, the system reminders, and the user's most recent explicit instruction. Reconcile them: the latest user message outranks an older summary if they conflict. State the task goal in **one sentence** — the objective the work is converging on, not a list of past actions. If you cannot, you are missing context; keep reading until you can.

### 2. Verify what is finished — never trust "done" from the summary

A summary that says "implemented X" is a claim, not a fact. Confirm each claimed-done item against ground truth before you treat it as complete:

- **Local state** — `git status`, `git log --oneline -20`, `git diff` and `git diff --staged`. What is actually committed, staged, or still dirty in the tree?
- **Remote state** — open PRs and *merged* PRs for this branch, their review state, and CI (passing, failing, pending). Work can be committed but unpushed, pushed but unmerged, or merged already.
- **The files themselves** — open the files the work touched and read what is really there. The function the summary says you wrote either exists or it does not.

Classify every item into exactly one bucket: **merged/pushed · committed-locally · in-progress (dirty/partial) · not-started.** An item with no commit, no diff, and no file change is not done, whatever the summary says.

### 3. Reconstruct the to-dos — goal minus verified-done

What remains is the one-sentence goal minus everything Pass 2 verified as done. Cross-check that delta against every record of remaining work, then order it:

- todo trackers (`docs/todo/*`, issue lists, plan docs) and PR-description checklists,
- failing or skipped tests, and `TODO` / `FIXME` markers in the touched code,
- the user's last explicit ask — the most authoritative "what next."

Order the list by dependency: what unblocks the most, or what the next step needs first.

### 4. Fill context gaps — what is needed to continue perfectly

This is the active pass — *rebuild until confident*, not skim. For the next one or two to-dos, list what you would need to do them correctly: the files and functions involved, the repo conventions (`AGENTS.md` / `CLAUDE.md`, lint/test/typecheck commands), the wire contracts or interfaces at the boundary, and the earlier decisions plus the **why** behind them. For each item you do not already hold, **go get it**: read the file, walk the git history (`git log -p <path>`, `git show <sha>`), open the linked docs, run the tests to see real state. Loop pass 4 until you could resume without guessing. Keep this pass internal — it is preparation, not the report.

### 5. Report — return 1–3 to the user

Give a concise recap, no wall of text:

1. **What we have been doing** — the goal, in a sentence or two.
2. **What is finished** — each item backed by a verifiable anchor (commit sha, PR number, merged/CI state, or file), so the user can check it.
3. **The to-dos** — the ordered remaining work from Pass 3.

Do **not** dump Pass 4 (files read, conventions, gap-filling) at the user — it is your prep, not their recap. End by resuming the top to-do or asking which to take, per what the user signalled.

## Failure modes

- **Trusting the lossy summary** — treating "done" or a remembered detail as fact without confirming against git/PRs/files. The summary points; the repo proves.
- **Redoing finished work** — re-implementing what is already committed or merged because Pass 2 was skipped. Verify before you build.
- **Acting before rebuilding** — committing, pushing, merging, or deploying on an assumed state. Reversible reads first; irreversible writes only after 1–4.
- **Dumping #4 as the report** — burying the user in everything you read instead of a crisp 1–3. Prep stays internal.
- **Inventing the record** — asserting a decision, rationale, or completed step that is in neither the summary nor the repo. If it is not in the record, say "unknown," do not fabricate it.

## Self-check

- [ ] The task goal is stated in one sentence, reconciled with the user's latest instruction.
- [ ] Every claimed-done item was checked against ground truth (git status/log/diff, open + merged PRs, CI, the actual files) and bucketed: merged/pushed · committed · in-progress · not-started.
- [ ] The to-do list is goal-minus-verified-done, cross-checked against trackers / PR checklists / failing tests / `TODO`s / the user's last ask, and ordered by dependency.
- [ ] For the next to-dos I have the files, conventions, contracts, and prior-decision *why* in hand — or I went and read them; nothing left to guess.
- [ ] No irreversible action (commit/push/merge/deploy/delete) was taken before the rebuild completed.
- [ ] The recap returns 1–3 with verifiable anchors on the "finished" items; #4 stayed internal; no decision was invented.
