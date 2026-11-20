# Scale

These rules hold, beside every rule in `SKILL.md`, while the state file exceeds 100 lines, `parallel` is above 1, or a worker does or is to do an item.

- [Status command](#status-command)
- [Workers](#workers)
- [Waves](#waves)
- [Integration](#integration)
- [Growing queue](#growing-queue)
- [Notes](#notes)
- [Budget](#budget)

## Status command

```sh
python3 "$SKILL_DIR/scripts/loop_hook.py" status [--state PATH] [--limit K]
```

`SKILL_DIR` is this skill's directory. Without `--state`, the command looks for `.agent-loop.md` from the current directory upward to the repository top, so run it inside the workspace or pass the path. It never writes a file, and it prints an empty header value as `(none)`. Exit code 0 means it read the file, with any problems listed in its output; exit code 2 means a bad argument, no state file found, or a file it could not read, and its message on stderr says what to try.

Its output has a fixed size whatever the queue length. `K`, 5 by default, caps every list, and a capped list ends with `+N more`. The sections, in order:

1. the path, then `goal`, `owner`, `stop`, `async gates` when the file has it, `budget` and `parallel`;
2. `counts:` doing, ready with dependencies met, ready but blocked, waiting, need you, closed;
3. `doing:` the full lines of `doing` items;
4. `next:` the first K unblocked `ready` items, in queue order;
5. `wave:` only when `parallel` exceeds 1, the IDs whose `writes:` scopes fit the free slots without overlapping, as **Waves** defines;
6. `waiting:` and `need you:` the full lines of `waiting` and `user` items;
7. `problems:` each problem with its line number, reason and fix, or `none`.

- **Use:** on each iteration that does not read the whole file, run the command in place of that read. Take the first unblocked item in `doing:`, else the first in `next:`, as **Pick** directs. Where the script cannot run, read the whole file instead.
- **Waiting:** `waiting:` shows at most K items; when **Wake** calls for every waiting item's check, raise `--limit` above the waiting count or read the whole file.
- **Problems:** when `problems:` is not `none`, read the whole file, repair each listed problem from evidence, and run the command again before picking. Several of these problems end the hook's automatic continuation without a message.
- **Edits:** build each snapshot under **Record** from the whole file, never from the command's output, which shows only part of it.

## Workers

A worker is an agent you dispatch to do one item. Do an item yourself or dispatch a worker as its work, the overhead and the resources the user has authorized warrant.

- **Brief:** give each worker one item and a self-contained brief: the item's line with its `done when` and `writes:`, the check to run, the whole `## Notes` section, this attempt's detail path, and the form under **Result**. A worker makes one attempt and reports a failure instead of retrying. A worker never edits the state file.
- **Copy:** when a worker gets its own copy of the repository under **Isolation** in Waves, the copy holds the integrated state, uncommitted work included, and every path the worker writes.
- **Result:** the worker writes its commands, output, evidence and failures to this attempt's detail file, for example `.agent-loop.d/<ID>-<attempt>.md` at the root of its working copy, which the `/.agent-loop.*` exclude line already keeps out of version control, ends that file with the result block, and returns only that block:

  ```
  item: <ID>
  result: done | failed: <one-line reason> | blocked: <one-line question>
  evidence: <absolute path of the detail file>
  files: <changed paths, comma-separated, or none>
  ```

  Route a result by its `result:` line. `done` is a claim: integrate it under Integration. `failed:` returns the item to `ready` with `tries:` raised under **Attempts**. `blocked:` marks the item `user`, as a gate under pass 4 or under **Unresolvable blocker**. Open the detail file only when the result or your check needs it.
- **Held items:** an item is held while a worker, or a command you started that is still running, does it. Give each attempt its own result entry, a worker's detail file or a command's output and exit-status files, and record it in `check:` before the attempt starts; when the authorized write scope allows no new path, first confirm that the earlier execution ended and handle its result, or else wait or ask. Accept a result only from the current entry, after checking the state of its execution; a result at an earlier entry is evidence for reconciliation only. Record `next: held by <worker or command>`, and add the host's handle, such as a task or process ID, once known. A held item is `doing`, and **Pick** skips it. Before ending a turn while an item is held, set it `waiting` with `wake: <worker or command>`, keeping its `check:`. When the result arrives, the item is no longer held: remove that `next:` and handle the result under **Result** or Integration, never redoing the item.

## Waves

A wave is the set of items held at the same time, by workers or by commands you start. Work sequentially unless all four hold:

- `parallel: <N>` in the header is above 1. Absent, it is 1. Choose N yourself within the cost and access the user has already authorized and the capacity of the host and machine; keep it at 1 when the user asked for serial work, and ask first when more items at once would need new cost or access.
- The items are listed in the command's `wave:` output now.
- **Pilot:** you are sure that the brief, check and scope work for these items. When you are not, first close one item of that kind alone, and record what it taught in `## Notes`. Items are of one kind when the same steps, brief and check apply to each, such as moving one module each to a new package.
- **Isolation:** you know that the items do not interfere: their write targets, including paths that reach one file through `..` or a link, which `wave:` does not compare, and the resources they use, such as an output directory, a port or an external service, do not overlap. When you do not know, isolate what they actually share, such as with a repository copy per item or a port per process, or run them one at a time.

`writes: <path or glob>, <path or glob>` on an item lists every file it may change. `wave:` fills the free slots, which are `parallel` minus the open `doing` and `waiting` items that have `writes:`. It walks the unblocked `ready` items in queue order and takes an item only when its scopes overlap no scope of an item already taken or of an open `doing` or `waiting` item. An item without `writes:` never joins a wave. Two scopes overlap when the part of one before its first `*`, `?` or `[` is a prefix of that part of the other. So:

- Write the narrowest scope that covers the item, such as `java/billing/invoice/**` rather than `java/**`. A scope that starts with a wildcard overlaps every other scope.
- Change a file that many items touch, such as a shared build file, in an item of its own with no `writes:`, so that it runs only between waves.
- While an item is held, start only items that `wave:` lists. When it lists none, wait for a held item's result with a blocking call, or end the turn where the host offers none; the hook grants no automatic turn for other `ready` items while a `waiting` item with `writes:` leaves no place for them in the wave.

## Integration

- **One at a time:** take the wave's results one by one, a worker's from its result block and a command's from its recorded output and exit status. For each, check that every changed file, by the `files:` line and by the change itself, lies inside the item's `writes:`, when it has one; bring a change made in an isolated copy into the shared working state; confirm the item under **Check**; and close it under **Log**.
- **Rejects:** a result that conflicts with integrated work or changes a file outside its `writes:` returns its item to `ready` with `tries:` raised under **Attempts**, and its changes leave the shared working state. Keep its detail file and name it in the next attempt's brief.
- **Regression check:** each time the last result of a wave is handled, so that no item is held, run one check over the integrated state, such as the project's full build and test suite, before starting another item, and record its result as a Log line of its own, such as `- <UTC date and time> regression check passed — <evidence>`, also when every result failed. If it fails, add an item that names the failure and the closed IDs at the top of the Queue, run repair items one at a time, and start no further wave until the check passes. After an interruption, rerun the check before the next wave unless a Log line shows that it ran on the current integrated state.

## Growing queue

- **Children:** an item may close by adding child items. Keep an ID that the source of the work already gives a child; otherwise give each child the parent's ID with a numbered suffix (`T4.1`, `T4.2`). Then add them in dependency order with each below the items it needs, and list them in the parent's closure line, such as `- <UTC date and time> T4 closed — inventory in docs/billing.md; added T4.1, T4.2, T4.3`.
- **Open parent:** closing a parent meets every dependency on it. When an open item needs the children's work rather than the parent's, keep the parent open instead: add the children above it, give it `after:` naming them, and close it when they have closed.

## Notes

`## Notes` is an optional section between Queue and Log, or after Log; the hook and the command ignore it. When the same problem or convention appears a second time, record it there as one line, such as `- Value objects are Java records in domain/model, with no setters.` Keep the section short: merge lines, and delete each line that no longer holds.

## Budget

One automatic turn can close many items, so set `budget` for a large queue from the number of turns the run is expected to take, not from the number of items. A value the user set wins.
