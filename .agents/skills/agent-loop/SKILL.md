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

Drive a goal to completion by running one cycle repeatedly without waiting for human messages: rebuild from the state file, pick the next ready item, act, check the result against evidence, record it, and continue. The state file is the durable scheduling record; each iteration reads it and verifies task facts at their authoritative sources. The loop stops only under pass 6 or an explicit user pause or stop instruction.

Priority: the user's consent rules and standing authorizations → truthful state backed by evidence → finishing the current item → visible progress → throughput.

Apply this skill only to a work queue you control under pass 2. On resume, after compaction, or when this text is incomplete, read this complete skill through **Self-check** and the state file before acting. Apply pass 2's ownership rules and check pass 1's **stop** value before resuming work; preserve pass 4's consent gates. If you cannot establish ownership or recover the required instructions, inspect evidence without changing the loop or taking queued actions.

## 1. Keep one state file

Use `.agent-loop.md` at the workspace root: the repository top level, or the directory the user names. Keep it out of version control: in a repository, append `/.agent-loop.*` to the file that `git rev-parse --git-path info/exclude` prints. Do not commit it. Keep one loop scheduling file; the hook owns the companion `.agent-loop.hook.json` at the same root. If an existing task tracker owns acceptance criteria and evidence, reference its stable entries and evidence locations in the queue's `done when` fields and closing log rather than maintaining competing copies. Verify those sources before changing scheduling state or closing an item. Otherwise use this file as the durable task ledger. Record any run, attempt, completion-signal and guard information required by the applicable work instructions, directly or by durable reference. Keep process state, loop scheduling state and task acceptance distinct.

To start a loop, create the file in this form. Fill in the goal and every item's independently confirmable `done when` criterion, `owner` as pass 2 describes, one queue line per item in priority order, the gate kinds the user allows to wait in the queue, and the user's budget or 50.

    # Agent loop

    goal: <outcome> — done when: <evidence>
    owner: <session ID>
    stop:
    async gates: <comma-separated gate kinds, or none>
    budget: 50

    ## Queue
    - [doing] T2 <title> — done when: <evidence>; next: <next step>
    - [ready] T1 <title> — done when: <evidence>
    - [ready] T5 <title> — done when: <evidence>; after: T3
    - [waiting] T3 <title> — done when: <evidence of the item's outcome>; wake: <event>; check: <command or source that shows the event happened>
    - [user] T4 <title> — done when: <evidence of the item's outcome>; ask: <exact question or approval>; asked: <date>

    ## Log
    - <UTC date and time> T0 closed — <evidence>

Follow these format rules exactly. The hook parses header keys, matched queue IDs and statuses, `next:`, `after:` and log-line counts. It does not validate acceptance criteria, unique IDs, dependency evidence or every required field, and it can ignore unmatched queue text. Acceptance by the parser is not validation of the file. Before continuing, check the complete file against this pass and repair it from evidence.

- **Header:** one `key: value` line per key, above `## Queue`; each key appears once.
- **owner:** the owning session's ID, or empty when no session ID exists.
- **stop:** empty while the loop runs or is idle; otherwise a reason from pass 6 or a user pause. On an explicit user instruction to pause or stop the loop, record `paused: <the user's instruction>` and take no further queued actions until the user explicitly resumes. Preserve any existing user-written pause value. Never invent a pause. An instruction merely to end one turn after an item does not pause the loop. On explicit resume, clear only the user pause and reconcile the state before continuing; budget, gate and blocker conditions still apply.
- **async gates:** the gate kinds that wait in the queue; every other gate is synchronous.
- **done when:** state evidence that any later iteration can confirm without memory of this session. Name a command and its required result, a required file or repository state, or a recorded review outcome.
- **budget:** a whole number of automatic continuations the hook may grant for this goal. Changing `goal` resets the count. To extend a loop stopped by its budget, the user raises `budget` and clears `stop: budget`; a raised budget alone leaves the loop stopped.
- **Statuses and dependencies:** use `ready` for queued work, `doing` for work in progress, `waiting` for an external event with `wake:` and `check:`, and `user` for a required answer with `ask:` and `asked:`. Give every item a unique ID. Keep only open items in the queue. An item with an unresolved dependency stays `ready`, below the item it needs, with `after: <ID>`. Queue order alone is not a dependency, and an open question blocks only work that needs its answer. Keep `after:` until evidence establishes the dependency's closure; remove the satisfied field when recording that closure. An absent or unknown ID does not establish closure. A `doing` item with a newly unresolved dependency returns to `ready` with its resumable next step preserved.
- **Log:** move each closed item to `## Log` as one line with its evidence. Keep every closure since the user's last message; older lines may be cut to the latest 20. In this skill, the user's last message is the last message a human wrote; hook feedback, task notifications and tool results do not count.
- **Sidecar:** never edit `.agent-loop.hook.json`; only the hook writes it.

## 2. Own the loop

One session owns the state file. Only the owner runs iterations and edits the file; the user may edit it at any time.

- **Host:** on Claude Code, invocation registers permitted skill-frontmatter hooks for the rest of the session, subject to managed policy and hook registration limits. Confirm that the hook is available and its command resolves this skill directory; loading the skill alone does not establish activation. If this skill is outside the frontmatter command's four candidate paths, adapt that command only within the authorized hook setup. On Codex, Cursor, Antigravity and Devin, register this hook once with `scripts/install_hook.py`: first obtain the user's consent to the host configuration change and ask which scope, user or project. That consent covers only this hook's registration, not other installation, policy, permission, trust or continuation-limit changes. Read the common setup and the current host's section in [Host setup](references/hosts.md) before registration, activation or owner-ID resolution; reread them when a complete applicable copy is absent or the host or mode changes. On other hosts, or without an active hook in the current mode, run owned, authorized work within turns; the user's next message resumes the loop. Recognize hook messages by `[agent-loop]` and their `turn <t>/<budget>` count.
- **Owner ID:** use the current host's **Owner ID** route in Host setup to obtain this session's exact ID. For a new loop without a matching ID, leave `owner:` empty and run within turns. For an existing loop, apply **Another owner**; an unavailable ID does not authorize clearing or replacing another owner's ID. Never substitute a child or unrelated identifier.
- **Another owner:** when `owner` names another session, only read the file. Take over only when the user explicitly asks; then write your own ID. A wake or notification never changes `owner`.
- **Workers:** give each dispatched worker (subagent or nested agent run) one item and a self-contained brief; workers report results to you and never edit the state file.
- **One controller:** do not run a host's native goal or loop feature in the same session; it would continue the session independently of the queue.

## 3. Run each iteration

Run as many iterations as you can within one turn. End the turn only when no item is actionable now, a stop reason from pass 6 applies, or the turn must end to let a waiter deliver an event. The turn-end hook in `scripts/loop_hook.py` exists only for the case where the host ends the turn while work remains.

1. **Rebuild.** Read the whole state file and trust it over your memory of earlier turns; the user may have edited it. Reconcile it with evidence at the authoritative sources: close finished items, run each waiting item's `check` and set it `ready` when its event has happened, and record the user's answers on `user` items. Reconcile every `after:` before picking work, including fields in existing state files. Clear a field only when the dependency's recorded criterion and required acceptance are confirmed, using retained closure evidence or the authoritative source if its log entry was trimmed. Leave unknown or unproven dependencies unresolved; seek available evidence or handle the unresolved work under passes 4 and 6. Return dependency-blocked `doing` items to `ready` without losing their next step. Do not infer completion from disappearance from Queue. Existing files, including fully dependency-blocked files, require this owner reconciliation on an authorized turn or explicit resume; the hook does not repair them.
2. **Pick.** Take the first `doing` item without an `after:` field, otherwise the first `ready` item without one, and mark it `doing`. Rebuild resolves satisfied dependencies before this selection. When the item needs a gate, handle it under pass 4 before you act.
3. **Act.** Do the work or dispatch workers. Run workers in parallel only on independent items that cannot change the same files, and mark each one `doing`.
4. **Check.** For a check you write or change for the item, show it rejecting work that misses the criterion and accepting work that meets it. For a new test, show it failing against the pre-change state. Use the pre-change state or a disposable copy to show failure. Never revert finished work to stage a failure. Record both results in the closing log evidence. Close an item only on evidence that meets its `done when` criterion: passing tests, a green gate, or a review with no open findings. Fix every finding of a review round before requesting the next round. After three rounds on one item without convergence, handle the dispute as a hard design choice under pass 4.
5. **Shared cause.** When the same failure appears in a second item, look for a shared cause before starting the next affected item. Possible causes include a generator, template, script, brief or rule. Fix any shared cause within the authorized scope. Recheck items the shared cause already affected. Record the fix in the state file. This step never authorizes editing the user's rules or this skill. Keep unrelated failures separate.
6. **Record.** Record real changes to status, `next:` and evidence. When closing an item, move it to Log with evidence and clear its satisfied dependents' `after:` fields in the same saved state update. Continue with the next item, fix a failure, or stop under pass 6. Never edit the file only to satisfy the hook. Its no-progress key contains the ordered parsed item IDs, statuses and `next:` values plus the number of log lines; two automatic turns with an unchanged key end automatic continuation. The key does not inspect evidence or detect every Queue or Log edit. Repeated attempts without evidenced progress are a blocker under pass 6.

## 4. Handle gates

A gate is an action outside the user's standing authorizations that needs the user's consent under the user's instructions or the project's rules, an acceptance the user reserves, or a hard design choice.

- **Async:** when the gate's kind is listed in `async gates`, mark the item `user` with an `ask:` that states the exact action and the options, name it in your turn's final message, and continue with other ready items. For a hard design choice, first consult an advisor when one is available (a stronger model, an independent reviewer, or the project's recorded decisions), and queue the choice with the advice only if it is still open.
- **Sync:** for every other gate, mark the item `user`, set `stop: gate: <question>`, and end the turn with the question.
- Only the user's answer opens a gate; a CI result, an agent's review or approval, or the host's permission mode does not. On the answer, record it on the item, set the item `ready`, and clear `stop` if it named this gate.

## 5. Wait for events

When an item needs an external result, such as a background job, a delegated agent or a CI run:

- **Waiter:** choose a completion route supported for this owning session in the current host and mode, within the documented or established delivery scope and lifetime. Read the common setup and applicable host section in [Host setup](references/hosts.md) before choosing or changing that route, and reread them after a host or mode change or when a complete applicable copy is absent. A native subagent result, a background shell completion and an output file are different mechanisms. Follow any applicable requirement for blocking result collection before relying on delivery after turn end. If a supported background completion route is available, a host-managed command may block until the item's `check` succeeds. Otherwise use an available blocking wait or result operation within the turn; if neither route is available, record that collection requires the next user message or explicit resume. Re-arm an expired bounded waiter only within the user's authorization and the host's lifetime limits. A delegated result returned within the turn needs no waiter.
- **Scheduling boundary:** do not create cron jobs or scheduled or periodic agent runs to execute the queue. A separately authorized completion subscription or safety notification may request reconciliation of existing work; it grants no additional work or configuration authority and gives no guarantee after session closure. Do not start a second continuation controller.
- **Record:** mark the item `waiting` with a `wake:` and a `check:` that any later iteration can run to confirm the event without the waiter. Retain its outcome criterion.
- **Idle:** continue other actionable work first. When only waiting, user or dependency-blocked items remain, keep `stop:` empty unless a stop condition applies. Complete any required blocking collection or coverage handoff for owned runs before ending the turn, and record and disclose uncovered work. Do not run a model polling loop; a blocking command that checks for its event is not a sequence of model turns.
- **Wake:** run the item's `check` first on every wake. If the check fails, handle the wait under **Waiter** and continue other authorized work. A duplicate wake changes nothing.
- **Session end:** do not assume a waiter survives turn end, interruption, process exit or resume. Record its supported lifetime and collection route. After interruption or resume, reconcile waiting items by their checks before reusing or replacing a waiter.

## 6. Stop only for these reasons

Honor explicit pause and stop instructions under pass 1's **stop** rule. Otherwise set `stop:` and end the turn only when:

- **Queue empty:** confirm the goal's done criterion with evidence, then set `stop: done`; if the criterion is not met, add the missing items instead.
- **Budget used up:** when the hook says this is the last automatic turn the budget allows, checkpoint the current item, record state, and set `stop: budget`.
- **Synchronous gate:** as pass 4 describes.
- **Unresolvable blocker:** after trying alternatives and consulting an available advisor, set `stop: blocked: <reason; what would unblock it>`. When the blocker affects only one item, mark that item `user` and continue with other items instead.

Continuation cap: when a host reports that further automatic turns are unavailable while you can still act, checkpoint state and report. A silent cap may provide no further turn; preserve the state already recorded rather than assuming a post-cap checkpoint can run. The loop resumes on the next user message subject to its recorded stop conditions.

A finished item, a long task or the end of a turn is not a reason to stop.

## 7. Keep progress visible

Include this status line in each turn's final message. Put it first unless an applicable instruction fixes that message's fields or order; preserve that form and place the loop facts in its permitted fields.

    Loop · now: <ID title, idle or stop reason> · <n> ready · <n> waiting · <n> need you · turn <t>/<budget>

Take the turn count from the latest hook message tagged `[agent-loop]` (`turn <t>/<budget>`), and omit it when no hook message arrived. When the loop is idle, use `now: idle`. When the loop goes idle or stops, or the hook announces a last automatic turn, follow the status line with the items closed since the user's last message and their evidence, each open `ask:`, each waiting item and its wake, and the next item.

## Self-check

- **State file (pass 1):** Is `.agent-loop.md` at the required workspace root and outside version control, in the required format with each header key once, unique item IDs, only open queue items, and the goal's and every item's independently confirmable criterion recorded directly or by stable authoritative reference? Are closure evidence and scheduling updates consistent with their authoritative sources, every closure since the last message a human wrote retained, any optional trimming of older lines limited to the latest 20, and the hook-owned sidecar untouched?
- **Ownership (pass 2):** Did you follow **Host** for registration, consent, scope and activation, set `owner:` from its applicable **Owner ID** route or use the permitted empty-owner fallback, read only another owner's file unless the user authorized takeover, keep owner unchanged on wakes, follow the early reload and ownership safeguard on resume or context loss, keep worker briefs self-contained and worker writes out of the state file, and avoid a second continuation controller?
- **Iteration (pass 3):** Did each iteration rebuild from the file and authoritative evidence, reconcile existing dependencies without inferring closure from absence, select only dependency-free items with `doing` preferred, handle gates before action, respect independent worker scopes, validate changed checks under **Check**, apply **Shared cause** when required, verify closure and resolve review findings, clear satisfied dependencies with the closure record, record only real progress, and continue within the turn until an allowed end?
- **Gates (pass 4):** Were only listed kinds handled asynchronously, with available advice consulted before an unresolved asynchronous design choice was queued; did every other gate stop under **Sync**, and did only the user's answer open a gate?
- **Events (pass 5):** Does each external wait use its supported, authorized route and lifetime, retain its outcome criterion, `wake:` and independently confirmable `check:`, continue other actionable work, honor blocking collection and coverage duties before idle turn end, disclose uncovered work, avoid scheduled queue execution and model polling, check wakes first, handle stale and duplicate wakes correctly, and reconcile waiting items after interruption or resume?
- **Stop (pass 6):** Does every stop follow its stated condition, with explicit user pause/stop instructions persisted and only explicitly resumed, no invented pause, budget and gate conditions retained, and a checkpoint/report at an observable host cap without assuming a turn after a silent cap?
- **Visibility (pass 7):** Does the turn's final message include loop facts under the applicable form rule, show idle explicitly, use the latest tagged hook count when present and omit it otherwise, and include the required closure evidence, open questions, waiting items and wakes, and next item when idle, stopped or on a last automatic turn, with the closure window measured from the last message a human wrote?
