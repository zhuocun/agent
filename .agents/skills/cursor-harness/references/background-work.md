# Background work and waiting

Use this reference to choose a launch vehicle, collect completion signals, and wait without losing work.

## Completion signals and wake-ups

An **end marker** is a file written after a process exits that records its exit code. A **waiter** is a background shell job that exits when an end marker appears or its tmux session disappears.

| Launch | Tracked by Cursor? | Completion reaches you via | Status |
| --- | --- | --- | --- |
| Shell call that finishes within `block_until_ms` | yes | the call result | documented |
| Shell call with `block_until_ms: 0`, or one that outlives `block_until_ms` | yes, as a background job | end-of-turn notification for jobs that finish during a turn; `AwaitShell` | documented; no-wake behavior below verified 2026-10-12 |
| `tmux new-session -d`, `nohup`, `setsid`, `cmd &` | no: the launch command returns at once | nothing unless you add a waiter | verified 2026-10-12 |
| Task subagent with `run_in_background: true` | yes | [result delivery](delegation.md#task-tool-subagents-documented) | documented |
| `subscribe_timer` (Cloud Agent) | yes | a follow-up prompt that starts a new turn | verified 2026-10-12 |

**After the turn ends — verified 2026-10-12:** only a timer, a background Task subagent, or a user message wakes an idle agent. A background shell job or waiter that finishes then does not start a turn.

**Unverified:** whether background shell jobs survive session reclamation. Treat a tmux run plus end marker as the source of truth.

## Choosing the vehicle

Run work in the background when it takes more than a few minutes or is independent of your next step.

| Work | Vehicle |
| --- | --- |
| Under a few minutes, and your next step needs it | foreground shell call, with `block_until_ms` sized to the expected runtime |
| Longer, but does not need to survive the session | background shell job (`block_until_ms: 0`), then one smoke check of its output file |
| Must survive the session, needs a human to attach, or is an agent CLI run (Codex, Devin, Cursor CLI, Claude Code), a deployment, or a long regression | tmux run with an end marker plus a waiter |
| Analysis, review, or coding a subagent can do | background Task subagent ([delegation.md](delegation.md)) |

Pair every detached run with a waiter.

## Wait routine

A **blocking wait** uses `AwaitShell` to wait for output from a waiter. A **safety timer** is a `subscribe_timer` subscription that prompts an idle agent to run the ledger inventory.

**Pair the mechanisms — verified 2026-10-12:** keep a safety timer subscribed while any run is going. While independent ledger work exists, do that work. When no independent work remains, use a blocking wait. For one detached run, wait on its waiter. For two or more detached runs, use the [any-end waiter](#any-end-waiter). A background shell job is tracked by Cursor and needs no extra waiter: wait on it by job id with `AwaitShell` ([mechanics](#shell-job-mechanics-documented)) when no detached run is going, and otherwise block on the detached runs' waiter and collect the job at the next inventory. Background Task subagents follow [result delivery](delegation.md#task-tool-subagents-documented) instead. A blocking wait reacts within seconds of completion. A safety timer reacts at its next fire, subject to the delivery delays in [safety timers](#safety-timers).

**After an interruption — verified 2026-10-12:** a user message releases a blocking wait early. Handle the message through the [operating loop](../SKILL.md#operating-loop), then run the inventory again. Start a fresh waiter over the remaining runs and resume the blocking wait in the same turn. Use an any-end waiter when several runs remain. Leave only the safety timer if the user asked you to stop working or the runs will take much longer than the timer interval.

**Queue check — documented:** before a long blocking wait on a Cloud Agent, check `cursor-cloud.get-message-queue`. Handle queued user messages first and defer slow verification while messages remain queued.

## Polling

Poll only when your next step depends on that job or it needs close monitoring, such as a deployment, long test run, or migration. Continue until the job ends, stalls, or is clearly hung. For background Task subagents, follow [delegation.md](delegation.md#task-tool-subagents-documented).

**List ordering — verified 2026-10-12:** a deployment list API returned its oldest page first and capped the page size. A poller reading only page 1 would miss the new deployment and continue until timeout. Before writing a poller, check the sort order, pagination (`hasMore`), and page size limit once by hand. Match a unique key, such as the commit hash, instead of the first item.

## Shell job mechanics (documented)

- The output file header carries `pid` and `running_for_ms`, updated every 5 seconds. When the job ends, a footer adds `exit_code` and `elapsed_ms`.
- `AwaitShell` polls one job by id per call. `pattern` blocks until an RE2 regex matches the output body. It never matches the header or footer. A call blocks for at most 119 minutes.
- Without `shell_id`, `AwaitShell` is a plain sleep. Use it for agent-side sleeps instead of a shell `sleep` call.
- If you observe a job's end yourself, for example after killing it, call `AwaitShell` once to consume the stale notification.
- Size waits in slices of 60–270 seconds or 1200 seconds and longer. Avoid round 5-minute waits, which miss the prompt cache.
- Never poll a job the tool result says the user backgrounded manually.

## tmux run plus waiter (verified 2026-10-12)

1. **Write a launcher script for each run.** Do not inline long commands. Export the environment the run needs inside the script. tmux sessions inherit the tmux server's global environment. Capture stdout and stderr in a log, then write the end marker after the process exits:

```sh
#!/usr/bin/env bash
set -u
RUN_DIR="$1"; shift
"$@" >"$RUN_DIR/run.log" 2>&1
rc=$?
echo "rc=$rc ended=$(date -Is)" >"$RUN_DIR/run.end.tmp" && mv "$RUN_DIR/run.end.tmp" "$RUN_DIR/run.end"
```

   Use a unique run directory and result path for each run. Delete any old end marker before launch.

2. **Launch in a uniquely named session:** `<task-tag>-<role>-<n>`. This lets `tmux ls` map sessions to ledger entries.

3. **Start the waiter immediately after launch** as a background shell job (`block_until_ms: 0`):

```sh
S=t3-regress-1; END=runs/t3-regress-1/run.end
while [ ! -s "$END" ]; do
  if ! tmux has-session -t "=$S" 2>/dev/null; then
    [ -s "$END" ] && break
    echo "SESSION-GONE-NO-END"; exit 3
  fi
  sleep 15
done
echo "WAITER-DONE $(cat "$END")"
```

   The second check of the end marker handles the race between writing the file and the session exiting. Use `pattern: WAITER-DONE|SESSION-GONE` with `AwaitShell` to match the final token. Cursor tracks the waiter as a background job.

4. **Process completion.** Check the exit code, log tail, and artifacts. Confirm artifact modification times are after launch, then update the ledger.

If the waiter dies because the session is reclaimed or the turn stops, the tmux run continues. Collect its end marker during the turn-start inventory.

**Multi-process launchers — verified 2026-10-12:** a launcher ran two agents as `( ... ) &` subshells under `set -u`. A copied environment line used a variable defined elsewhere in the original script. One subshell died with `unbound variable` before creating its log. The other continued, and the combined end marker would still have been written.

After launch, confirm each leg's log exists and shows the expected model. Copy referenced variables with environment lines, or test the copied lines alone under `set -u`. Prefer one tmux session and one end marker per agent.

**Stopping a run — verified 2026-10-12:** after `tmux kill-session`, the waiter prints `SESSION-GONE-NO-END` and exits 3 on its next check. Cursor reports the stop as a normal job completion. Rename the artifacts, for example `<run>-attempt1.*`, before relaunching under the same name. Record the cancellation and its reason in the ledger.

## Any-end waiter

An **any-end waiter** is an extra background shell job that exits as soon as any watched end marker appears:

```sh
while :; do
  for f in runs/t3-worker-1/run.end runs/r7-regress/run.end; do
    [ -s "$f" ] && { echo "ANY-END $f $(cat "$f")"; exit 0; }
  done
  sleep 20
done
```

Use `AwaitShell` with `pattern: ANY-END`. When the waiter finishes, process that run. Start a fresh waiter over the remaining runs, following the [wait routine](#wait-routine).

Keep each run's own waiter to detect `SESSION-GONE-NO-END`. If the any-end waiter is the only waiter, add `tmux has-session` checks.

**Status: verified 2026-10-12.**

## Safety timers

Use `cursor-subscriptions.subscribe_timer` on Cloud Agent. Follow the [wait routine](#wait-routine) for when a safety timer must remain armed.

**API — documented:** use `once: true` with `delaySeconds` for a one-shot safety timer. Use `cron` or `delaySeconds` for a recurring safety timer.

**Behavior — verified 2026-10-12:** a safety timer enqueues a prompt that runs when the agent is free. The subscription name deduplicates timers, and the prompt is frozen at creation.

- Name the safety timer after its ledger entry.
- Set its prompt to say **"run the inventory from the ledger"**. Keep current end markers and next actions in the ledger.
- For a known end time, use a one-shot safety timer at the expected end plus a margin. When the end is uncertain, use a recurring safety timer, for example every 20 minutes.
- Choose an interval longer than a typical blocking wait, or use a one-shot safety timer re-armed at turn end.
- If a prompt becomes stale, replace the subscription with `unsubscribe`, then subscribe again.
- For subscription inventory and cleanup, follow [platform-tools.md](platform-tools.md#subscriptions-cursor-subscriptions-documented). Remove remaining safety timers when no run is left.

**Queued prompts — verified 2026-10-12:** a recurring safety timer fired at 21:40 during a long blocking turn. Cursor delivered its prompt at 23:13, after the turn ended and after unsubscribe. Every action in the prompt was already done. A recurring 15-minute safety timer fired five times during one turn. Cursor delivered all five prompts together at turn end, again after unsubscribe.

Treat a delivered timer prompt as a request for inventory. Check the ledger and end markers, skip completed actions, and compare `firedAt` with ledger timestamps. Run one inventory for a batch of prompts.

**First recurring fire — unverified (one observation, 2026-10-12):** a recurring `subscribe_timer` with `delaySeconds: 1200` first fired after about 400 seconds. It arrived after a separate one-shot timer fired and the agent became idle. The cause is unknown. Possible causes are phase alignment or delivery when the agent is free. Let inventory tolerate an early fire. Use a one-shot safety timer when timing matters.

For event subscriptions, see [platform-tools.md](platform-tools.md#subscriptions-cursor-subscriptions-documented).

## Hangs

- Watch output growth as well as elapsed time. Suspect a run with no output growth for much longer than its normal cadence.
- Before killing a run, save its log and confirm the PID belongs to it. Use the launcher's recorded PID or the output file header. Never kill by `pgrep -f` or `ps | grep` on prompt text. Such matches can select the waiter or your own shell. **Verified 2026-10-12:** a procfs `cmdline` scan for a run's brief name matched only the scanning shell itself.
- After killing a hung run, retry once. Escalate or switch vehicles if it fails again. Record both attempts in the ledger.
