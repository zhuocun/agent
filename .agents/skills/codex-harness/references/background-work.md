# Background work and bounded monitoring

A command's outputs and exit record establish run evidence. They do not, by themselves, cause the controller to receive a completion message or start another turn. Choose evidence storage and result delivery separately.

## Choose ownership before launch

Use [SKILL.md — 3. Choose an execution vehicle](../SKILL.md#3-choose-an-execution-vehicle) for direct work, delegation conditions, CLI ownership, and existing-job watchers.

| Situation | Preferred approach |
| --- | --- |
| Authorized bounded work that native tools can perform | Prefer a native agent under **3. Choose an execution vehicle** |
| Native delegation is unavailable or forbidden | Keep controller ownership and use supported session waits or artifact checks in the active turn |
| Work must continue across a session boundary | Use a supported, authorized persistence and notification mechanism only after verifying its scope |

Avoid detached execution when a tracked session suffices. If persistence is necessary, follow the selected CLI's or runtime's documented persistence contract and verify persistence for that vehicle. Do not infer survival from a successful detached launch.

Use [task-ledger.md — Location and registration](task-ledger.md#location-and-registration) for the pre-launch record. Use a distinct directory or artifact set per attempt. Capture logs, the final deliverable, and terminal exit status. An end marker must represent the launched process's exit, not merely launcher startup or monitor completion.

Attach the returned handle to the run record and confirm startup through initial output. Confirm that the intended CLI and model started. A missing log for one member of a group is not covered by another member's output or a group launcher exit.

## Native owner and read-only watcher

Use [SKILL.md — 3. Choose an execution vehicle](../SKILL.md#3-choose-an-execution-vehicle) for native lifecycle ownership and [delegation.md — Brief and dispatch](delegation.md#brief-and-dispatch) for agent startup.

A watcher handles a narrower role. Use a self-contained brief with this contract:

- **Scope:** Name exact existing jobs, attempt identities, readable artifacts, and the controller destination. State any handles the watcher can actually access.
- **Boundary:** Observe and report only. Do not implement, review, certify completion, change scope, stop or retry jobs, configure subscriptions, or delegate again.
- **Bound:** Set a deadline and polling or wait cadence consistent with host limits. Stop after all watched runs reach terminal evidence, cancellation, or the deadline.
- **Signals:** Send an initial acknowledgement listing coverage and expiry. Report material completion, failure, access loss, blocker, or expiry. Stay quiet on unchanged state.
- **Evidence:** Include attempt identity, observation time, exit evidence or its absence, artifact paths, and the reported verdict. Separate observation from inference.

Use [SKILL.md — 5. Establish coverage before exit](../SKILL.md#5-establish-coverage-before-exit) to establish acknowledged coverage. Do not create an unbounded watcher tree. Read-only observation does not give the watcher ownership of continuation.

At deadline, report unfinished jobs and end coverage explicitly. Use **5. Establish coverage before exit** for controller renewal, transfer, coverage limits, and disclosure. A watcher that silently exits or loses access no longer covers its jobs.

## Wait, consume, continue

Use [SKILL.md — 4. Wait, validate, and continue](../SKILL.md#4-wait-validate-and-continue) for the operating loop. A wait timeout or mailbox summary is not a job result. After interruption, use [task-ledger.md — Handle messages and races](task-ledger.md#handle-messages-and-races) to reconcile ownership, remaining runs, and monitor expiry before the next wait.

Batch independent checks where the tools permit. Avoid busy polling or a model call for each log line. When polling an external status API, verify pagination and ordering, then match a unique run identity. Do not infer state from the first list item.

Use **4. Wait, validate, and continue** for subscription selection and reliance. Verify the controller destination, delivery scope, local artifact access, lifecycle, deadline, and cleanup before configuration. Configure it only when authorized. A timer or automation for another product is not a substitute for local thread wake-up.

Use [platform-tools.md — Verified active-session bridge](platform-tools.md#verified-active-session-bridge) for delivery evidence and [SKILL.md — 5. Establish coverage before exit](../SKILL.md#5-establish-coverage-before-exit) when execution limits force exit. Apply [platform-tools.md — Subscription discovery limits](platform-tools.md#subscription-discovery-limits) to callbacks and persistent configuration. When native agents or subscriptions are unavailable, use the controller-owned monitoring fallback in **Choose ownership before launch**.

## Validate completion

Apply the common result gate in [SKILL.md — 4. Wait, validate, and continue](../SKILL.md#4-wait-validate-and-continue) using these CLI evidence mechanics:

- **Terminal evidence:** Inspect the current attempt's exit from the execution tool or a trustworthy end marker. A watcher finishing does not prove the CLI exited.
- **Final artifact:** Open the actual deliverable. A nonempty final-message file can still be partial if the process continues.
- **Freshness:** Match the artifact to the attempt, launch time, and intended input or baseline. Modification time alone is insufficient provenance.
- **Semantic verdict:** Inspect whether the report completed its scope or says `BLOCKED`, `NEEDS_CONTEXT`, failed, or incomplete. A zero exit can carry any of those outcomes.
- **Required checks:** Use **Result inspection** in [delegation.md — Controller review and continuation](delegation.md#controller-review-and-continuation) for diff, artifact, and test evidence. Use [task-ledger.md — States and evidence](task-ledger.md#states-and-evidence) for required review and acceptance.

If the final model result is empty, inspect earlier visible, non-reasoning assistant output before repeated hook output. Recover a surviving deliverable only as unaccepted output. Do not expose reasoning or claim that a hook or completion gate cleared. Revalidate recovered content and preserve unresolved exit or gate status.

If an artifact exists without exit evidence, record it as partial or unvalidated and inspect the run. If a session disappears, check terminal markers again to resolve a write/exit race. Missing markers leave the exit unknown.

## Suspected hangs and retry limits

Silence or a stale modification time alone does not prove a dead process. Compare expected cadence, owned session status, terminal evidence, and available logs. A sandbox's process list may omit other namespaces.

Before a scoped stop or retry, verify identity using the recorded session, launcher PID, or other trusted run handle. Never kill by a broad name or prompt pattern. Stop only within authorization and the owning workflow's bounds.

Use [task-ledger.md — States and evidence](task-ledger.md#states-and-evidence) to preserve the prior attempt and [Handle messages and races](task-ledger.md#handle-messages-and-races) before a retry. Use a fresh attempt identity and artifact set as required by **Choose ownership before launch**. Honor the recorded retry budget and stop on a repeated unresolved blocker or exhausted limit. Do not use a retry to expand permissions, scope, models, or providers.
