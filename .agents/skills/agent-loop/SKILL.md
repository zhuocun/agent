---
name: agent-loop
description: >-
  Run a self-continuing agent loop: keep a durable goal and work queue in one
  plain-text state file, take the next ready item, act, check it against
  evidence, record the result, and continue without a new human message until
  the goal is complete, the budget is used up, a synchronous consent gate is
  reached, or a blocker remains. On Claude Code the turn-end hook ships in the
  skill and continues only the session that owns the queue; background waiters
  resume the loop when a job, delegated agent or CI run finishes. On other
  hosts the loop runs within turns. Use when the user asks to start, resume,
  run, inspect, pause or stop an agent loop, autonomous backlog run or work
  queue, or to keep working through tasks across turns, compaction or sessions
  without being prompted. Do not use for a task that finishes within one turn,
  for scheduled or cron-driven unattended runs, or inside a delegated worker
  that does not own the queue.
hooks:
  Stop:
    - hooks:
        - type: command
          command: 'for d in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/agent-loop}" "${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.claude/skills/agent-loop}" "${HOME:+$HOME/.claude/skills/agent-loop}"; do if [ -n "$d" ] && [ -f "$d/scripts/loop_hook.py" ] && grep -qx "name: agent-loop" "$d/SKILL.md" 2>/dev/null; then out=$(python3 "$d/scripts/loop_hook.py" 2>/dev/null) || out=""; if [ -n "$out" ]; then echo "$out"; else echo "{}"; fi; exit 0; fi; done; echo "{}"'
---

# Agent loop

Drive a goal to completion by running one cycle repeatedly without waiting for human messages: rebuild from the state file, pick the next ready item, act, check the result against evidence, record it, and continue. The state file is the loop's only memory; it survives compaction and session end, and every iteration starts from it. The loop stops only for the reasons in pass 6.

Priority: the user's consent rules and standing authorizations → truthful state backed by evidence → finishing the current item → visible progress → throughput.

## 1. Keep one state file

Use `.agent-loop.md` at the workspace root: the repository top level, or the directory the user names. Keep it out of version control: in a repository, append `/.agent-loop.*` to the file that `git rev-parse --git-path info/exclude` prints. Do not commit it or create other task records for the loop; the state file and its log replace task documents. The hook owns the companion `.agent-loop.hook.json` at the same workspace root.

To start a loop, create the file in this form. Fill in the goal with its done criterion, `owner` as pass 2 describes, one queue line per item in priority order, the gate kinds the user allows to wait in the queue, and the user's budget or 50:

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
    - [waiting] T3 <title> — wake: <event>; check: <command or source that shows it happened>
    - [user] T4 <title> — ask: <exact question or approval>; asked: <date>

    ## Log
    - <UTC date and time> T0 closed — <evidence>

Follow these format rules exactly; the hook reads the header keys, the `## Queue` heading, the bracketed statuses, `next:`, `after:` and the log lines, and it ignores a file that breaks them:

- **Header:** one `key: value` line per key, above `## Queue`; each key appears once.
- **owner:** the owning session's ID, or empty when no session ID exists.
- **stop:** empty while the loop runs or is idle; otherwise a reason from pass 6. Any other value is a pause, and only the user writes one. Never write a pause yourself: an instruction to end your turn after an item is not a pause, so leave `stop:` empty and let the hook continue the loop.
- **async gates:** the gate kinds that wait in the queue; every other gate is synchronous.
- **budget:** a whole number of automatic continuations the hook may grant for this goal. Changing `goal` resets the count. To extend a loop stopped by its budget, the user raises `budget` and clears `stop: budget`; a raised budget alone leaves the loop stopped.
- **Statuses:** `ready` (actionable), `doing` (in progress), `waiting` (needs an external event; has `wake:` and `check:`), `user` (needs the user's answer; has `ask:` and `asked:`). An item that needs another open item's result stays `ready`, sits lower in the queue and carries `after: <ID>`. Queue order alone is not a dependency, and an open question blocks only the items that need its answer. Keep only open items in the queue.
- **Log:** move each closed item to `## Log` as one line with its evidence. Keep every closure since the user's last message; older lines may be cut to the latest 20. In this skill, the user's last message is the last message a human wrote; hook feedback, task notifications and tool results do not count.
- **Sidecar:** never edit `.agent-loop.hook.json`; only the hook writes it.

## 2. Own the loop

One session owns the state file. Only the owner runs iterations and edits the file; the user may edit it at any time.

- **Host:** on Claude Code the Stop hook comes with this skill: invoking the skill registers it for the rest of the session, with nothing to install. If the skill directory is somewhere other than the four paths in the hook command in this skill's frontmatter, edit the command's path list. Recognize the hook's messages by the prefix `[agent-loop]` and their `turn <t>/<budget>` count. On other hosts there is no turn-end hook yet: run as many iterations as you can within each turn; the user's next message resumes the loop.
- **Owner ID:** when creating the state file, set `owner:` to this session's ID: `${CLAUDE_SESSION_ID}`. If that text appears unexpanded, take the ID from the environment variable `CLAUDE_CODE_SESSION_ID`. If no session ID exists, leave `owner:` empty; the loop then runs within turns only.
- **Another owner:** when `owner` names another session, only read the file. Take over only when the user explicitly asks; then write your own ID. A wake or notification never changes `owner`.
- **Resume:** on resume or after compaction, reload this skill and the state file, check `stop` before acting, then continue. Resuming the same session keeps the same ID.
- **Workers:** give each dispatched worker (subagent or nested agent run) one item and a self-contained brief; workers report results to you and never edit the state file.
- **One controller:** do not run a host's native goal or loop feature in the same session; it would continue the session independently of the queue.

## 3. Run each iteration

Run as many iterations as you can within one turn. End the turn only when no item is actionable now, a stop reason from pass 6 applies, or the turn must end to let a waiter deliver an event. The turn-end hook in `scripts/loop_hook.py` exists only for the case where the host ends the turn while work remains.

1. **Rebuild.** Read the whole state file and trust it over your memory of earlier turns; the user may have edited it. Reconcile it with evidence (repository, CI, reviews, worker output): close items the evidence shows are finished, run the `check` of each `waiting` item and set it `ready` when its event has happened, and record the user's answers on `user` items.
2. **Pick.** Take the first `doing` item, otherwise the first `ready` item whose `after:` item is closed, and mark it `doing`. When the item needs a gate, handle it under pass 4 before you act.
3. **Act.** Do the work or dispatch workers. Run workers in parallel only on independent items that cannot change the same files, and mark each one `doing`.
4. **Check.** Close an item only on evidence that meets its `done when` criterion: passing tests, a green gate, or a review with no open findings. Fix every finding of a review round before requesting the next round. After three rounds on one item without convergence, handle the dispute as a hard design choice under pass 4.
5. **Record.** Record real changes to an item's status, its `next:` and the evidence, log closed items, then continue with the next item, fix a failure, or stop under pass 6. Never edit the file only to satisfy the hook: it ends automatic continuation after two automatic turns that leave the queue and log unchanged, and repeated attempts without evidenced progress are a blocker under pass 6.

## 4. Handle gates

A gate is an action outside the user's standing authorizations that needs the user's consent under the user's instructions or the project's rules, an acceptance the user reserves, or a hard design choice.

- **Async:** when the gate's kind is listed in `async gates`, mark the item `user` with an `ask:` that states the exact action and the options, name it in your turn's final message, and continue with other ready items. For a hard design choice, first consult an advisor when one is available (a stronger model, an independent reviewer, or the project's recorded decisions), and queue the choice with the advice only if it is still open.
- **Sync:** for every other gate, mark the item `user`, set `stop: gate: <question>`, and end the turn with the question.
- Only the user's answer opens a gate; a CI result, an agent's review or approval, or the host's permission mode does not. On the answer, record it on the item, set the item `ready`, and clear `stop` if it named this gate.

## 5. Wait for events

When an item needs an external result, such as a background job, a delegated agent or a CI run:

- **Waiter:** start a background command whose completion the host reports to this session (on Claude Code: Bash with `run_in_background`) and that blocks until the item's `check` succeeds, for example `until <check>; do sleep 30; done`. If the host limits a background command's run time, re-arm the waiter when it ends. Never start scheduled or periodic agent runs. When a delegated agent returns its result within the turn, no waiter is needed.
- **Record:** mark the item `waiting` with a `wake:` and a `check:` that any later iteration can run to confirm the event without the waiter.
- **Idle:** continue with other ready items. When no actionable `ready` or `doing` item remains and only `waiting` or `user` items remain, the loop is idle: keep `stop:` empty and end the turn. Do not poll.
- **Wake:** on every wake, run the item's `check` first. When it fails (an early or stale wake), re-arm the waiter and continue. A duplicate wake changes nothing.
- **Session end:** a waiter lives only as long as this session's process. If the session ends, the user's next message or a resume reconciles the waiting items by their `check`.

## 6. Stop only for these reasons

Set `stop:` and end the turn only when:

- **Queue empty:** confirm the goal's done criterion with evidence, then set `stop: done`; if the criterion is not met, add the missing items instead.
- **Budget used up:** when the hook says this is the last automatic turn the budget allows, checkpoint the current item, record state, and set `stop: budget`.
- **Synchronous gate:** as pass 4 describes.
- **Unresolvable blocker:** after trying alternatives and consulting an available advisor, set `stop: blocked: <reason; what would unblock it>`. When the blocker affects only one item, mark that item `user` and continue with other items instead.

Continuation cap: when the host refuses further automatic turns with ready work remaining, record state and report; the loop resumes on the next user message.

Keep the user's pause (pass 1) until the user resumes the loop. A finished item, a long task or the end of a turn is not a reason to stop.

## 7. Keep progress visible

Begin the final message of every turn with a status line:

    Loop · now: <ID title, idle or stop reason> · <n> ready · <n> waiting · <n> need you · turn <t>/<budget>

Take the turn count from the latest hook message tagged `[agent-loop]` (`turn <t>/<budget>`), and omit it when no hook message arrived. When the loop is idle, use `now: idle`. When the loop goes idle or stops, or the hook announces a last automatic turn, follow the status line with the items closed since the user's last message and their evidence, each open `ask:`, each waiting item and its wake, and the next item.

## Self-check

- **State file (pass 1):** Is `.agent-loop.md` at the workspace root, outside version control, in the required format with each header key once, with only open queue items, every closure since the last message a human wrote logged (older lines cut to at most 20) and the sidecar untouched?
- **Ownership (pass 2):** Did you set `owner` to this session's ID, or leave it empty without one, read only another session's file unless the user asked you to take over, leave `owner` unchanged on wakes, reload the skill and file on resume, keep workers from editing the file and avoid a second continuation controller?
- **Iteration (pass 3):** Did each iteration rebuild from the file, prefer `doing` work, respect `after:`, handle each picked item's gate before acting, respect independent worker scopes, verify closure, resolve review findings and record only real progress, continuing within the turn until an allowed end?
- **Gates (pass 4):** Did you queue only listed asynchronous kinds, consult available advice before queuing an unresolved design choice, stop at every other gate and open none without the user's answer?
- **Events (pass 5):** Does each external wait have a running waiter where needed, a `wake:` and a `check:`, with every wake checked first, waiters re-armed after early wakes, no polling and idle recorded without a stop?
- **Stop (pass 6):** Does each stop you set follow its stated condition, with the state recorded at a continuation cap, no pause set by you, and the user's pause preserved until the user resumes?
- **Visibility (pass 7):** Does the final message begin with the status line, report idle explicitly and use the hook's count when available, followed by the required summary, counted from the last message a human wrote, when idle, stopped or on a last automatic turn?
