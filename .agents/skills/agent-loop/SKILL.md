---
name: agent-loop
description: >-
  Run a self-continuing agent loop over an owned work queue. Use when the user
  asks to start, resume, run, inspect, pause or stop an agent loop or autonomous
  backlog run, or to keep executing an owned queue across turns, compaction or
  sessions without another human prompt. Do not use for a new task that finishes
  within one turn, scheduled or cron-driven unattended agent runs, or a
  delegated worker that does not own the queue.
hooks:
  Stop:
    - hooks:
        - type: command
          command: 'for d in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/agent-loop}" "${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.claude/skills/agent-loop}" "${HOME:+$HOME/.claude/skills/agent-loop}"; do if [ -n "$d" ] && [ -f "$d/scripts/loop_hook.py" ] && grep -qx "name: agent-loop" "$d/SKILL.md" 2>/dev/null; then out=$(python3 "$d/scripts/loop_hook.py" 2>/dev/null) || out=""; if [ -n "$out" ]; then echo "$out"; else echo "{}"; fi; exit 0; fi; done; echo "{}"'
---

# Agent loop

Drive a goal to completion without waiting for human messages: repeatedly rebuild from the state file, pick the next unblocked item, act, check the result against evidence and record it, until pass 6 or the user stops the loop.

Priority: the user's consent rules and standing authorizations → truthful state backed by evidence → finishing the current item → visible progress → throughput.

**Start.** Apply this skill only to a queue you own under pass 2. On start, on resume (continuing the loop in a new session, or after a pause or stop), after compaction, or when this text is incomplete, read this skill through **Self-check**, then establish ownership, check **stop**, keep pass 4's gates and complete **Rebuild** before any queued action or loop status report; if ownership or these instructions cannot be recovered, only inspect evidence.

Read [Scale](references/scale.md) in full before the first iteration in which the state file exceeds 100 lines, the user allows parallel work or a worker does or is to do an item, and again after each compaction while any of these holds.

## 1. Keep one state file

Keep `.agent-loop.md` at the workspace root (the repository top, or a directory the user names) as the only loop scheduling record, out of version control: in a repository, append `/.agent-loop.*` to the file that `git rev-parse --git-path info/exclude` prints. It also holds any running checklist or run, attempt or guard record your instructions require; reference another tracker's criteria and evidence rather than copy them.

To start a loop, create the file in this form, with items in priority order and the user's budget or 50:

    # Agent loop

    goal: <outcome> — done when: <evidence>
    owner: <session ID>
    stop:
    async gates: <gate kinds, or none>
    budget: 50

    ## Queue
    - [doing] T2 <title> — done when: <evidence>; next: <next step>; tries: 1
    - [ready] T1 <title> — done when: <evidence>
    - [ready] T5 <title> — done when: <evidence>; after: T2, T3
    - [waiting] T3 <title> — done when: <evidence>; wake: <event>; check: <command that confirms it>
    - [user] T4 <title> — done when: <evidence>; ask: <exact questions>; asked: <date>

    ## Log
    - <UTC date and time> T0 closed — <evidence>

A malformed header or item line can silently end the hook's automatic continuation or hide an item from it.

- **Header:** one line per key, each once, above `## Queue`.
- **stop:** empty while the loop runs or idles, else a pass 6 reason or a user pause. On an explicit user instruction to pause or stop the loop, record `paused: <the instruction>` and take no queued action until the user explicitly resumes; then clear only that pause and reconcile. Keep a pause the user wrote, and never invent one; ending one turn after an item is not a pause.
- **async gates:** only the gate kinds the user said may wait in the queue.
- **done when:** evidence a later iteration can confirm without memory of this session; the goal and each item have one.
- **budget:** the automatic continuations the hook may grant for this goal; changing `goal` resets the count. A loop stopped by its budget resumes only when the user both raises `budget` and clears `stop: budget`.
- **Items:** the queue holds only open items, with the statuses shown and the fields this skill names. IDs are unique across Queue and Log and never reused; redo closed work as a new item that names the old ID.
- **Dependencies:** `after:` lists the IDs an item needs, comma-separated. The item is blocked, and stays `ready` below them, until each has a closure line in Log and no open item in Queue; a blocked `doing` item returns to `ready`. Repair an ID that is neither open nor closed, or a cycle, from evidence, or else handle it under pass 6.
- **Log:** close an item by moving it to the end of `## Log` as one line in the form shown, with the UTC date and time from the system clock and the ID directly before `closed`; leave its dependants unedited. Keep every Log line for the whole run; dependencies resolve from them.
- **Sidecar:** never edit `.agent-loop.hook.json`; only the hook writes it.

## 2. Own the loop

One session owns the state file: only it runs iterations and edits the file, and the user may edit it at any time.

- **Host:** read the common setup and the current host's section of [Host setup](references/hosts.md) in full before registering the hook, resolving the owner ID or choosing a waiter, and again after a host or mode change or when no complete copy is in context. Run a registration command it gives only after the user consents and chooses user or project scope; that consent covers no other installation, policy, permission, trust or limit change. Confirm that the hook is active, editing its command only within the authorized setup. Without an active hook, run owned, authorized work within turns; the user's next message continues the loop.
- **Owner ID:** use this session's exact ID from the host's **Owner ID** route in Host setup, never a child's or an unrelated identifier; without one, leave a new loop's `owner:` empty and run within turns. When `owner` names another session, only read the file, and write your own ID only when the user explicitly asks you to take over; a missing ID, a wake or a notification never changes `owner`.
- **One controller:** run no second continuation controller, such as a host's native goal or loop feature, in the same session.

## 3. Run each iteration

Run as many iterations as you can in one turn, ending it only when no item is actionable, a pass 6 stop reason applies, or a waiter needs the turn to end to deliver its event.

1. **Rebuild.** Trust the file over your memory. Read it whole and check it against pass 1 on start, on resume, after compaction and to repair it; on other iterations, read it whole while it has at most 100 lines, and otherwise as Scale directs. Reconcile it with evidence at the authoritative sources: close finished items and record user answers on `user` items.
2. **Pick.** Take the first unblocked `doing` item, else the first unblocked `ready` one, and mark it `doing`. Work on one item at a time unless the wave rules in Scale allow more. Handle a needed gate under pass 4 before acting.
3. **Check.** Show that a check you write or change rejects work missing the criterion and accepts work meeting it, with a new test failing on the pre-change state or a disposable copy, never by reverting finished work; record both results in the closure evidence. Close an item only on evidence that meets its `done when`: passing tests, a green gate, or a review without open findings by a reviewer other than the item's author (a fresh context counts). Fix every finding of a review round before the next; after three rounds without convergence, treat the dispute as a hard design choice under pass 4.
4. **Attempts.** Count in `tries:`, before the next run, every run of an item's action that fails its check or cannot be integrated, whoever runs it; review rounds do not count. At 3, mark the item `user` with an `ask:` naming the failure and what would unblock it, leave `stop:` unchanged and continue with other items.
5. **Shared cause.** When a second item shows the same failure, look for a shared cause before the next affected item; fix it within the authorized scope, recheck the items it already affected, and record the fix in the state file. This never authorizes editing the user's rules or this skill. Keep unrelated failures separate.
6. **Record.** Pass every result, wake and answer through **Check**, then save real changes to statuses, fields, evidence and **Log** before further scheduling or status reports. Never edit the file only to satisfy the hook.

## 4. Handle gates

A gate is an action outside the user's standing authorizations that needs their consent under their instructions or the project's rules, an acceptance the user reserves, or a hard design choice.

- **Async:** for a gate kind listed in `async gates`, mark the item `user` with an `ask:` that states the exact action and the options, name it in the turn's final message, and continue with other items. For a hard design choice, first consult an available advisor, such as a stronger model, and queue the choice, with the advice, only if it is still open.
- **Sync:** for every other gate, mark the item `user` with an `ask:` that lists every question you ask the user at this gate, set `stop: gate: <question>`, and end the turn with those questions.
- **Answer:** only the user's answer opens a gate, never a CI result, an agent's review or approval, or the host's permission mode. Record it on the item, set the item `ready`, and clear `stop` if it named this gate.

## 5. Wait for events

When an item needs an external result:

- **Waiter:** use a completion route that Host setup supports for this session, host and mode, within its scope and lifetime and with any blocking collection it requires; without one, wait within the turn by a blocking call, or else record that collection needs the next user message or an explicit resume. Record the waiter's lifetime and collection route; where a host stops background commands after a fixed time, collect or re-arm before that limit, within the user's authorization.
- **Scheduling boundary:** never create cron jobs or scheduled or periodic agent runs to execute the queue. A separately authorized completion notification may prompt reconciliation but grants no further authority.
- **Record:** mark the item `waiting` with a `wake:` and a `check:` that any later iteration can run to confirm the event without the waiter, and keep its `done when`.
- **Wake:** run a waiting item's `check` only on its wake, on resume or interruption, and when no item is ready; once its event has happened, set the item `doing` and continue from that result without redoing it, and on a failed check handle the wait under **Waiter** and continue other work. A duplicate wake changes nothing.
- **Idle:** when only waiting, user or blocked items remain, keep `stop:` empty unless a stop condition applies, and record and disclose any wait that no waiter covers. Run no model polling loop; a blocking command that checks for its event is not one.
- **Session end:** never assume a waiter survives turn end, interruption, process exit or resume; reuse or replace one only after its item's check under **Wake**.

## 6. Stop only for these reasons

Honor explicit pause and stop instructions under **stop**. Otherwise set `stop:` and end the turn only when:

- **Queue empty:** confirm the goal's `done when` with evidence, then set `stop: done`; if it is not met, add the missing items instead.
- **Budget used up:** when the hook says this is the last automatic turn the budget allows, checkpoint the current item, record state, and set `stop: budget`.
- **Synchronous gate:** under **Sync**.
- **Unresolvable blocker:** after trying alternatives and consulting an available advisor, set `stop: blocked: <reason; what would unblock it>`. A blocker of one item instead marks that item `user` while others continue.

**Continuation cap:** when a host reports that no more automatic turns are available, checkpoint state and report; after a silent cap no turn follows, so rely on state already recorded. The user's next message continues the loop under its recorded stop conditions.

## 7. Keep progress visible

Put this status line in each turn's final message, first unless an applicable instruction fixes that message's fields or order; then put the loop facts in its permitted fields.

    Loop · now: <ID title, idle or stop reason> · <n> ready · <n> waiting · <n> need you · turn <t>/<budget>

- **Count:** copy `turn <t>/<budget>` unchanged only from the latest actual `[agent-loop]` hook message for this loop in the current context, which a summary or an earlier status line is not, and otherwise omit it; never increment or extrapolate it.
- **Report:** when the loop goes idle or stops, or the hook announces a last automatic turn, follow the status line with the items closed since the user's last message and their evidence (when more than ten, instead their count, first and last IDs, and the state file's path), each open `ask:`, each waiting item and its wake, and the next item. The user's last message is the last one a human wrote, not hook feedback, a task notification or a tool result.

## Self-check

- **Start:** every step of **Start** done before acting?
- **Scale:** when due, read it in full and followed it?
- **Pass 1:** file meets every rule of pass 1?
- **Pass 2:** **Host**, **Owner ID** and **One controller** followed?
- **Pass 3:** each iteration followed **Rebuild** to **Record**, to an allowed turn end?
- **Pass 4:** **Async**, **Sync** and **Answer** followed?
- **Pass 5:** **Waiter** to **Session end** followed?
- **Pass 6:** only listed stops or **stop**, and **Continuation cap**?
- **Pass 7:** status line placed per pass 7, meeting **Count** and **Report**?
