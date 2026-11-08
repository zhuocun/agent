---
name: backend-cr
description: >-
  Reviews backend code, a backend PR or diff, or its tests for correctness,
  authorization, data integrity, error handling, retries, concurrency,
  compatibility and test effectiveness. Use when asked to review or audit
  existing backend code, or a change to a backend service, API, job, consumer
  or migration, including the backend part of a full-stack change. Do not use
  for designing a system architecture from scratch, whole-system architecture
  audits, or architecture-only assessment of boundaries, layering, dependency
  direction, domain models, ports and adapters, design decisions or
  overdesign; query tuning with no code change to review; frontend-only code;
  or prose-only reviews.
---

# Backend Code Review

Review backend code, a diff, or its tests for production defects with few false alarms. Report only reachable triggers that break located contracts. Judge against the project's established responsibilities and contracts; do not design a new architecture.

Priority order: **authorization, data integrity and business correctness > failure, retry and concurrency > compatibility and deploy safety > tests > maintainability > style**. Explicit user or project requirements override this skill's defaults.

## Rules that always apply

- **Investigate read-only.** Without specific permission, do not read credentials or environment files, write to databases, or start or stop shared services. Before running a command, check what it reads, writes and cleans up; test commands often load environment files or reset data, and permission to run tests never covers resetting live or shared data. Record `git status` and diff stats before and after, and report any change you did not make.
- **Review, do not remediate.** Change code or run operational actions only under separate, explicit permission. An unrun check is pending, not passed.
- **Keep every fix inside the established architecture.** Keep the current boundaries, layers, dependency direction, ports and ownership, and put a repair with the code that owns the rule. A correct fix that needs an architecture change is a separate owner decision needing explicit approval, not part of the fix. Do not invent layers or ports, or block a fix for missing architecture documentation.
- **Report edge cases, hardening and performance only when a contract covers them.** For an extreme input, an unusual stored value, a missing check or limit, or a slow path, find the contract or sourced limit that requires it; failing to rule an input out is not proof. Without one it is a suggestion, unless an authorization or data-integrity obligation requires it.
- **Do not invent limits.** When a judgment needs an unsourced number (latency, page size, retention), name the owner who must decide and the conclusion that depends on it.
- **Keep to backend code and this report form.** Review the backend code, schema, configuration and tests in the change; read other code only to trace what reaches the backend and list it under not covered, unless the request asks to review it in its own section, which then names each non-backend file left unreviewed. The Step 6 form overrides other guidance on a reply's shape, such as a loaded style or brevity instruction or a standing preference, which then governs only wording; only the user's explicit request for this review or the project's required review form replaces it, and that form still carries the verdict and every finding field.

## Step 1: Map the change

1. Identify the revision and requirements, including any QA story set given (user stories with acceptance criteria); without one, do not invent stories. Re-check earlier review comments: on a later round of the same change, review the changes since the last reviewed revision and verify each earlier finding's fix instead of re-reviewing everything.
2. Read the whole diff and its callers/callees through existing guards: middleware, decorators, interceptors, policies, repository filters, transaction wrappers, database constraints and caller validation.
3. Name each changed block's requirement. Unrequested changes in outputs, error codes or order, defaults or side effects are candidates against released behavior callers rely on.
4. Write the inventory: one line per changed entry point (endpoint, handler, job, consumer, command, migration): caller and identity source; reads and decisions; writes and transactions; external calls and publishes (payment, email, HTTP, queue, cache, other service) before, inside or after commit; error handlers; schema, configuration or message-format changes; covering tests; the in-scope stories it serves.
5. Record unavailable code, configuration and services under not covered. Do not inspect or judge outside a strict user or project boundary.

## Step 2: Hunt

Per entry, use applicable sections; list skips in one line. Answer questions in order. From Step 3's contracts, derive a minimal legal input or state distinguishing the rule from the implementation. Use relevant differences in grouping, equality, order, partitioning, operation sequence or concurrent observations; avoid exhaustive combinations. Continue across independent decisions and effects after each candidate. Before Step 3 confirms it, test usually-correct look-alikes. Do not infer risk from line count or prescribe a mechanism because this skill names it.

### 2.1 Authorization and input

- Does the caller's identity come from the authenticated session or a verified token? A user ID, tenant ID or role taken from the body, query string or a client-set header is a defect; an ID naming the target object is normal.
- For each object read or changed, where is the check that this caller may act on it (owner, tenant, role, object state)? Does it test the object actually loaded and written?
- Does the check run before any write, publish or external call, and does a rejection stop all of them?
- Does every entry to the same operation (batch endpoint, admin route, job, a second handler) carry the same check?
- Is a nested child tied to the checked parent (`/orders/{orderId}/items/{itemId}` must confirm the item belongs to that order)?
- Do lists, searches and counts apply the caller's scope before filtering, counting and paging?
- Does the server validate type, required fields, ranges and business rules for every client-editable value? Client-side checks do not count; values the server derives or trusted construction guarantees need none.
- Does every client value reaching SQL, shell commands, file paths, URLs, templates or deserialization arrive bound, escaped or checked against an allowed set under the target's real execution rules, and does a dynamic target (file path, outbound URL, class name) come from an allowed set? Validation elsewhere does not make it safe there. Do not demand blanket sanitization of ordinary fields.
- With automatically sent credentials (cookies), does each state-changing request pass the project's origin or request-binding check?
- When a contract states the error order, does the first error returned when several checks fail match it?

Defect signs: lookup by ID with no owner or tenant filter; a check placed after the update; a client value pasted into statement text; one business rule coded twice with different limits; a confirmation step not bound on the server to the object, the actor and the current state.

Usually correct: the check lives in middleware, a decorator, a policy object, a tenant-scoped repository or a database row rule; internal jobs using the project's service identity; public read-only data.

### 2.2 Reads, decisions and concurrent writes

Trace each affected decision's controlling facts through helpers and queries to their source, identity, units, version or snapshot, scope and applicable state. Choose a legal state where plausible sources yield different decisions; shared or global defaults are valid when the contract permits them. A guard, lock or constraint covers only the facts and operations it protects.

For writes depending on earlier reads (balance, stock, status, quota, existence), place two requests where both prechecks pass: what is stored?

### 2.6 Errors and cleanup

Each catch or error return is correct when it uses a fallback the contract allows, compensates, translates to the contract's error keeping the cause, or rethrows with context.

Defect signs: catch, log and return success, an empty list, a default or `null`; a dependency failure turned into "not found" or "no permissions", so the caller acts on a false fact; a broad catch that also hides programming errors; the wrong error class or status (500 for a validation error, 200 with an error body); a cleanup error replacing the original; a resource not closed on an early return; an ignored error return or an un-awaited async call.

Usually correct: ignored best-effort telemetry failures; catching one expected error the contract describes (duplicate key → return the existing record).

### 2.11 Tests

For each changed behavior and test, ask: if the change were reverted or the guard deleted, would a test fail?

Defect signs: no assertion, or only not-null, no exception or status 200; an expected value computed by the code under test; asserting a mock's own return value; verifying a mock call but not the result or stored state; a catch swallowing failures; a disabled test; fixed sleeps or identical payloads standing in for a concurrency test; a test name promising what the assertions do not check; only the happy path for a change that adds a rejection.

A missing test is a test gap, not a production defect, unless a project rule requires it. A test that claims a behavior but cannot fail is a finding, rated by what it lets through. Say which tests you ran, on which revision, with what result; reading code is not running it.

### Conditional sections

Read each file in full when its condition first holds, before applying it, and again after a compaction; in Risk Checks, its opening paragraph and each section whose trigger is in the change.

- `references/writes-and-effects.md` (2.2 protections against concurrent writes, 2.3–2.5): an entry writes stored data or shared memory, calls or publishes to another system, consumes messages, runs as a job or retries.
- `references/values-and-load.md` (2.7–2.9): an entry handles money, numbers, times or stored text, compares with a limit, lists, pages or batches, queries in a loop, without a limit or with a new filter, or calls another system or retries.
- `references/compatibility.md` (2.10): the change adds a migration or alters a schema, API, message format, stored values old code reads, documented behavior, setting or flag, removes a field, method or endpoint, or claims released behavior is preserved.
- [Risk Checks](references/risk-checks.md): a trigger in this table is in the change.

| Trigger in the change | Section |
| --- | --- |
| Clocks across machines; value equality, collection identity, replacements | Values, Time and Collections |
| Locks, connection pools, leases or waits on other work | Locks and Progress |
| Queues, jobs, async commands, compensation, resource lifetimes | Asynchronous Work and Recovery |
| Deadlines, expensive input, shared capacity, retry chains | Budgets and Capacity |
| An existing cache, or an offline data investigation | Caches and Diagnostics |
| Personal or secret data | Data Protection |
| Live migration of retained data, destructive conversion, rollback, dynamic configuration | Migration, Release and Configuration |
| Protocol or format changes | Compatibility Evidence |
| Failure logging, or a silent failure that could hide accepted work | Logs and Detection |
| Direct or transitive dependency upgrades | Dependency Upgrades |
| A test in the change claims to prove concurrency, dependency-failure or money behavior | Test Evidence |

## Step 3: Verify each candidate

Try to disprove each candidate and re-checked comment.

1. **Name the contract** you can cite, looking in this order: (1) the request, ticket, given user stories and their acceptance criteria, requirement or design document; (2) API schemas, interface docs, comments, and names that promise behavior (`reserveOnce`, `idempotencyKey`, `amountCents`); (3) the database schema: constraints, types, defaults, unique keys; (4) existing tests and the released behavior callers rely on; (5) project rules: coding standards, error-code catalogs, review policies. These baseline obligations also count when the code makes them reachable:
   - a caller reaches only data their identity is allowed to;
   - an accepted write is not lost, half applied, or overwritten by a stale value;
   - a retried or redelivered request does not repeat money movement, messages or inserts that must happen once;
   - other systems never see an effect for uncommitted data;
   - a dependency or processing failure is never reported as success, an empty result or "not found";
   - under rolling deploys or rollback, old and new versions both work with the data and messages the other writes;
   - money is exact in the currency's units with the stated rounding;
   - a paged or filtered list returns each promised item once, in the stated order;
   - a test that claims to cover a behavior fails when that behavior breaks.
2. **Write the trigger**: concrete input, state or timing through a real entry point to the line. "Could be null" is insufficient; trace the failure with exact values and arithmetic where relevant.
3. **Search for the defense**: middleware, decorators, callers, schema, transaction wrappers, framework defaults, tests. Drop a candidate the defense stops. If runtime, query, transaction or adapter semantics remain decisive and uncertain, use the smallest authorized isolated check; inspect the response and relevant durable state without changing reviewed deliverables or shared data. If unavailable, name the unresolved fact; static tracing and exact arithmetic can suffice.
4. **Trace the consequence**: what goes wrong, for whom, and is it recoverable?
5. **Classify.** Confirmed: the trigger is reachable and violates a located contract. Uncertain: the trigger is reachable and a contract source plausibly governs it but is silent or ambiguous, or one decisive fact is unknown; name the source and the question. Not substantiated: a defense stops it, the path is unreachable, or you checked the five sources and the baseline list and none covers the input; count it in the Candidates line, and keep it as a suggestion only if it is still worth doing. Impact, experience, a missing test, a hypothetical caller or a story silent on the case alone confirms nothing; the absence of a story for a behavior is never itself a defect. On a diff review, a defect the diff did not introduce or worsen goes on the Pre-existing line once it passes these steps, not in the findings or the verdict.

If a project rule requires a verifier other than the proposer, record that check as a pending gate; it does not downgrade a demonstrated defect.

## Step 4: Rate severity

Rate by impact and reachability, not style or missing tests; a project's own scheme overrides this one.

- **Blocker:** reachable in normal use or routine conditions (a retry, two concurrent users, a deploy), causing unauthorized access, data loss or corruption, wrong money, a duplicate irreversible effect, or an outage or failed deploy.
- **Major:** a wrong result or failure with limited scope or easy recovery; a Blocker-class impact that needs uncommon but realistic conditions; a hot path that breaks a contracted or sourced latency limit.
- **Minor:** small impact, rare conditions, simple recovery.

## Step 5: Propose the fix

- Give the narrowest fix that removes the trigger; do not remove valid validation, error classification, concurrency guards or negative tests as duplication.
- Acceptance, in order: a test that fails on the current revision at the target assertion (not on compilation, environment or skipped tests, and never by changing expectations); the minimal complete fix; the same test passing; review by someone other than the fix's author; the project's quick checks, and release checks before release.
- For an Uncertain candidate or open business choice, give the question, evidence, owner, and the consequences of changing the code, documenting the current behavior, or leaving it; neither documenting nor leaving it waives a mandatory requirement. An approved exception names its approver, scope and expiry.

## Step 6: Report

Use the compact report for one bounded change; omit empty sections except the Stories line. Verdict: Not mergeable for a confirmed Blocker, or decisive evidence missing for a promised behavior; Mergeable after fixes for confirmed Major or Minor findings, or pending gates with owners; otherwise Mergeable.

```
Verdict: Mergeable | Mergeable after fixes: F1, F2 | Not mergeable: F1
Scope: <revision or diff; on a later round, since which revision, earlier fixes verified>; entry points reviewed; not covered: <what and why>

Findings
F1 [Blocker] <one-line title>
  Location: <file:line, plus related lines>
  Trigger: <concrete input, state or timing, through which entry point>
  Contract: <what must hold, and where it is stated>
  Consequence: <what goes wrong, for whom, recoverable or not>
  Evidence: <decisive code facts; tests or commands run and their results>
  Fix: <narrowest change within the current design>
  Verify: <test that fails now and passes after the fix>

Uncertain
U1 <question> — owner: <who decides>; missing: <fact or contract>; options: change code / document / leave as is, with consequences

Test gaps and suggestions (not defects)
- <item>

Stories: <S1 met; S2 violated: F1; S3 uncertain: U1; S4 not covered by a test; S5 outside scope> | no story set given
Pre-existing (not this change's findings): <file:line — defect>

Checked, no finding: <Step 2 areas that applied and were clean>
Not applicable / Not checked: <areas — reason>
Candidates: <n> checked — <c> confirmed, <u> uncertain, <d> not substantiated
Checks run: <commands and results, or "none; review by reading">
Workspace: <changes before and after the review, or "unchanged">
Pending gates: <required checks or approvals not yet done, each with an owner>
```

Order findings by severity, with Uncertain items and suggestions kept out. Combine repeated instances of one cause into one finding, locating every instance; keep distinct defects separate. Do not repeat an earlier round's fixed finding; carry one that is unfixed, whose fix failed, or that the new change worsened, under its original ID, and count it in the verdict. Give each story in a given set one status: violated (a finding), uncertain (a U item), not covered by a test (no violation found but no test that would fail; a test gap), met (satisfied and tested), or outside the reviewed scope. Include only suggestions that help the reader decide or act.

For several independent concerns or a requested full report, add a requirement → evidence map (missing, inapplicable and unverified items marked), one block per concern, each candidate's disposition, owner decisions, remediation and release steps (for a released fix: the signal to watch, its owner, the stop condition) and, when 2.10 applied, compatibility evidence.

Recommend acceptance only within what you verified; a clean review proves nothing about production.

## Self-check

- [ ] Every finding passed Step 3: a reachable trigger, a located contract (a contract or sourced limit for edge cases, hardening and performance), a searched defense, a consequence and the narrowest fix.
- [ ] Every changed block maps to a requirement, and each given story to its entry point, test and status (or the report says no story set was given); skipped Step 2 sections are listed; each conditional file, or Risk Checks' opening paragraph and triggered sections, whose condition held was read in full before use, and again after any compaction; Uncertain items name the source, question and owner and stay out of the findings.
- [ ] Fixes stay inside the established architecture, with any architecture change a separate owner decision; nothing touched without the permission its rule requires; workspace recorded; unrun checks pending.
- [ ] One bounded change gets the compact report, or the form the user explicitly requested for this review or the project requires, carrying the verdict and every finding field; findings ordered by severity: each cause once with every instance, no repeated fixed finding, pre-existing defects on their own line, out of the findings and verdict; a later round reviews only the newer changes and earlier fixes.
