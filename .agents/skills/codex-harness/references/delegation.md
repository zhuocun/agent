# Bounded delegation

Use [SKILL.md — 3. Choose an execution vehicle](../SKILL.md#3-choose-an-execution-vehicle) for execution vehicle selection and delegation authority.

An implementing agent owns a bounded deliverable. Use **3. Choose an execution vehicle** for native lifecycle ownership and [background-work.md — Native owner and read-only watcher](background-work.md#native-owner-and-read-only-watcher) for the watcher's narrower role.

## Model and vehicle

Resolve the requested model, effort, speed, and vehicle against current exposed schemas and available routing guidance, following **3. Choose an execution vehicle** for explicit overrides. Record requested settings separately from confirmed settings. Never infer Fast mode from a capability label or a model name. If the native schema cannot express requested speed, report that limitation or use an already authorized suitable vehicle. Do not silently substitute a model or add a provider.

Use **3. Choose an execution vehicle** for workflow boundaries. Keep routing and lifecycle decisions with their responsible owners instead of duplicating routing tables or feature procedures.

Use [platform-tools.md — Documented reference-host schemas](platform-tools.md#documented-reference-host-schemas) for context inheritance and mode constraints, subject to [SKILL.md — 6. Check capabilities and retain evidence](../SKILL.md#6-check-capabilities-and-retain-evidence).

## Brief and dispatch

Give each agent enough information to act without hidden conversation dependencies:

- **Goal and authority:** State the exact deliverable, user constraints, approved scope, and stopping condition.
- **Context:** Provide relevant files, baseline, prior evidence, dependencies, and the actual workspace or worktree.
- **Boundaries:** Name writable resources, exclusions, shared-environment guards, and whether further delegation is allowed.
- **Run contract:** State deadline, retry budget, artifact locations, completion signal, and who owns the next action.
- **Final report:** Require outcome, changed files or artifact paths, checks and their results, limitations, and concrete blockers.

For a watcher, use the narrower observation contract in [background-work.md](background-work.md). Do not brief a watcher as an implementer or reviewer.

Use [task-ledger.md — Location and registration](task-ledger.md#location-and-registration) for the assignment record and [Handle messages and races](task-ledger.md#handle-messages-and-races) to check for an existing owner. Attach its returned identity and confirm startup. Use distinct visible task names and per-attempt artifacts.

Do not assume agents receive isolated branches or machines. Verify workspace sharing from the host schema. Separate edit ownership or coordinate overlapping writes. A controller retry must not race an agent still managing the original run.

Process independent results as they arrive. Wait for all agents only when the next step depends on all their results. Use [platform-tools.md — Documented reference-host schemas](platform-tools.md#documented-reference-host-schemas) and the current schema to distinguish native message and follow-up behavior.

## Controller review and continuation

Apply [SKILL.md — 4. Wait, validate, and continue](../SKILL.md#4-wait-validate-and-continue) to every agent deliverable and watcher event. For external CLI evidence mechanics, use [background-work.md — Validate completion](background-work.md#validate-completion).

**Result inspection:** Open the actual artifact or inspect the diff and run checks appropriate to the change before advancing the parent task.

Return concrete review findings to the responsible implementer when that ownership remains active. Record each review attempt and record retries using [task-ledger.md — States and evidence](task-ledger.md#states-and-evidence). If the controller edits the result, record that ownership rather than attributing the edit to the delegate.

Use **4. Wait, validate, and continue** for authorized continuation and [task-ledger.md — States and evidence](task-ledger.md#states-and-evidence) for required review or acceptance.

On a user stop or changed scope, apply [task-ledger.md — Handle messages and races](task-ledger.md#handle-messages-and-races) and send changed constraints to the current owner promptly. Use its **Guards and handoffs** section before exit.
