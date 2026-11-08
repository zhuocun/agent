# Background work and waiting

Use this reference to choose a launch vehicle, collect completion signals, and wait without losing work.

- [Completion signals and wake-ups](#completion-signals-and-wake-ups)
- [Choosing the vehicle](#choosing-the-vehicle)
- [Wait routine](#wait-routine)
- [Polling](#polling)
- [Shell job mechanics (documented)](#shell-job-mechanics-documented)
- [tmux run plus waiter (verified 2026-10-12)](#tmux-run-plus-waiter-verified-2026-10-12)
- [Any-end waiter](#any-end-waiter)
- [Safety timers](#safety-timers)
- [Hangs](#hangs)

## Completion signals and wake-ups

| Launch | Tracked by Cursor? | Completion reaches you via | Status |
| --- | --- | --- | --- |
| Shell call that finishes within `block_until_ms` | yes | the call result | documented |
| Shell call with `block_until_ms: 0`, or one that outlives `block_until_ms` | yes, as a background job | end-of-turn notification for jobs that finish during a turn; `AwaitShell` | documented; no-wake behavior verified 2026-10-12 (see **After the turn ends**) |
| `tmux new-session -d`, `nohup`, `setsid`, `cmd &` | no: the launch command returns at once | nothing unless you add a waiter | verified 2026-10-12 |
| Task subagent with `run_in_background: true` | yes | [result delivery](delegation.md#task-tool-subagents-documented) | documented |
| `subscribe_timer` (Cloud Agent) | yes | a follow-up prompt that starts a new turn | verified 2026-10-12 |

**After the turn ends — verified 2026-10-12:** a background shell job or waiter that finished after the turn ended did not start a turn; timer prompts and background Task subagent results did.

**Documented for the IDE agent:** background shells keep running between turns, and archiving the chat stops them. **Unverified:** whether background shell jobs survive session reclamation. Treat a tmux run plus end marker as the source of truth.

## Choosing the vehicle

Run work in the background when it takes more than a few minutes or is independent of your next step.

| Work | Vehicle |
| --- | --- |
| Under a few minutes, and your next step needs it | foreground shell call, with `block_until_ms` sized to the expected runtime |
| Longer, but does not need to survive the session | background shell job (`block_until_ms: 0`), then one smoke check of its output file |
| Must survive the session, needs a human to attach, or is an agent CLI run (Codex, Devin, Cursor CLI, Claude Code), a deployment, or a long regression | tmux run with an end marker plus a waiter |
| Analysis, review, or coding a subagent can do | background Task subagent ([delegation.md](delegation.md)) |

## Wait routine

**Evidence — verified 2026-10-12:** a blocking wait reacted within seconds of completion; a safety timer reacted only at its next fire, subject to the delivery delays in [safety timers](#safety-timers).

**Interruptions — verified 2026-10-12:** a user message released a blocking wait early.

**Queue check — unverified:** before a long blocking wait on a Cloud Agent, check `cursor-cloud.get-message-queue` if `GetDynamicTools` lists it, and handle queued user messages first.

## Polling

Poll only when your next step depends on that job or it needs close monitoring, such as a deployment, long test run, or migration. Continue until the job ends, stalls, or is clearly hung. For background Task subagents, follow [delegation.md](delegation.md#task-tool-subagents-documented).

**List ordering — verified 2026-10-12:** a deployment list API returned its oldest page first and capped the page size. A poller reading only page 1 would miss the new deployment and continue until timeout. Before writing a poller, check the sort order, pagination (`hasMore`), and page size limit once by hand. Match a unique key, such as the commit hash, instead of the first item.

## Shell job mechanics (documented)

- The output file header carries `pid` and `running_for_ms`, updated every 5 seconds. When the job ends, a footer adds `exit_code` and `elapsed_ms`.
- `AwaitShell` polls one job by id per call. `pattern` blocks until an RE2 regex matches the output body. It never matches the header or footer. A call blocks for at most 119 minutes.
- Without `shell_id`, `AwaitShell` is a plain sleep. Use it for agent-side sleeps instead of a shell `sleep` call.
- If you observe a job's end yourself, for example after killing it, call `AwaitShell` once to consume the stale notification.
- Size each wait well under or well over the model's prompt-cache lifetime; a wait just past it pays for a cache miss without the saving of a long wait. For an unknown lifetime or a 5-minute one (Anthropic's default), use slices of 60–270 seconds or 1200 seconds and longer.
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

Any-end waiter script:

```sh
while :; do
  for f in runs/t3-worker-1/run.end runs/r7-regress/run.end; do
    [ -s "$f" ] && { echo "ANY-END $f $(cat "$f")"; exit 0; }
  done
  sleep 20
done
```

Use `AwaitShell` with `pattern: ANY-END`. When the waiter finishes, process that run, then wait on the remaining runs as [wait efficiently](../SKILL.md#5-wait-efficiently) describes.

Keep each run's own waiter to detect `SESSION-GONE-NO-END`. If the any-end waiter is the only waiter, add `tmux has-session` checks.

**Status: verified 2026-10-12.**

## Safety timers

Use `cursor-subscriptions.subscribe_timer` on Cloud Agent. [Wait efficiently](../SKILL.md#5-wait-efficiently) says when a safety timer must stay subscribed.

**API — documented:** use `once: true` with `delaySeconds` for a one-shot safety timer. Use `cron` or `delaySeconds` for a recurring safety timer.

**Behavior — verified 2026-10-12:** a safety timer enqueues a prompt that runs when the agent is free. The subscription name deduplicates timers, and the prompt is frozen at creation.

- Name the safety timer after its ledger entry.
- Keep current end markers and next actions in the ledger rather than in the prompt.
- Set a one-shot safety timer at the expected end plus a margin, and a recurring one at an interval such as 20 minutes.
- Choose an interval longer than a typical blocking wait, or use a one-shot safety timer re-armed at turn end.
- If a prompt becomes stale, replace the subscription with `unsubscribe`, then subscribe again.
- For subscription inventory and cleanup, follow [platform-tools.md](platform-tools.md#subscriptions-cursor-subscriptions-documented). Remove remaining safety timers when no run is left.

**Queued prompts — verified 2026-10-12:** a recurring safety timer fired at 21:40 during a long blocking turn. Cursor delivered its prompt at 23:13, after the turn ended and after unsubscribe. Every action in the prompt was already done. A recurring 15-minute safety timer fired five times during one turn. Cursor delivered all five prompts together at turn end, again after unsubscribe.

When a timer prompt arrives, check the ledger and end markers, skip completed actions, and compare `firedAt` with ledger timestamps.

**First recurring fire — unverified (one observation, 2026-10-12):** a recurring `subscribe_timer` with `delaySeconds: 1200` first fired after about 400 seconds. It arrived after a separate one-shot timer fired and the agent became idle. The cause is unknown. Possible causes are phase alignment or delivery when the agent is free. Let inventory tolerate an early fire. Use a one-shot safety timer when timing matters.

For event subscriptions, see [platform-tools.md](platform-tools.md#subscriptions-cursor-subscriptions-documented).

## Hangs

- Watch output growth as well as elapsed time. Suspect a run with no output growth for much longer than its normal cadence.
- Before killing a run, save its log and confirm the PID belongs to it. Use the launcher's recorded PID or the output file header. Never kill by `pgrep -f` or `ps | grep` on prompt text. Such matches can select the waiter or your own shell. **Verified 2026-10-12:** a procfs `cmdline` scan for a run's brief name matched only the scanning shell itself.
- After killing a hung run, retry once. Escalate or switch vehicles if it fails again. Record both attempts in the ledger.
