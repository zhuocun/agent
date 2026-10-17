---
name: backend-cr
description: >-
  Use when reviewing existing backend code, a scoped backend change, or its
  tests for correctness, authorization, data integrity, failure behavior,
  concurrency, compatibility, and verification quality. Do not use for designing
  a system architecture from scratch, whole-system architecture audits, or
  architecture-only assessment of boundaries, layering, dependency direction,
  domain models, ports and adapters, design decisions, or overdesign; route
  those requests to architecture design and review. Do not use for
  frontend-only or prose-only reviews.
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

## Step 1: Map the change

1. Identify the revision and requirements; re-check earlier review comments.
2. Read the whole diff and its callers/callees through existing guards: middleware, decorators, interceptors, policies, repository filters, transaction wrappers, database constraints and caller validation.
3. Name each changed block's requirement. Unrequested changes in outputs, error codes or order, defaults or side effects are candidates against released behavior callers rely on.
4. Note one line per changed entry point (endpoint, handler, job, consumer, command, migration): caller and identity source; reads and decisions; writes and transactions; external calls and publishes (payment, email, HTTP, queue, cache, other service) before, inside or after commit; error handlers; schema, configuration or message-format changes; covering tests.
5. Record unavailable code, configuration and services as coverage gaps. Do not inspect or judge outside a strict user or project boundary.

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
- With automatically sent credentials (cookies), does each state-changing request pass the project's origin or request-binding check?
- When a contract states the error order, does the first error returned when several checks fail match it?

Defect signs: lookup by ID with no owner or tenant filter; a check placed after the update; one business rule coded twice with different limits; a confirmation step not bound on the server to the object, the actor and the current state.

Usually correct: the check lives in middleware, a decorator, a policy object, a tenant-scoped repository or a database row rule; internal jobs using the project's service identity; public read-only data.

### 2.2 Reads, decisions and concurrent writes

Trace each affected decision's controlling facts through helpers and queries to their source, identity, units, version or snapshot, scope and applicable state. Choose a legal state where plausible sources yield different decisions; shared or global defaults are valid when the contract permits them. A guard, lock or constraint covers only the facts and operations it protects.

For writes depending on earlier reads (balance, stock, status, quota, existence), place two requests where both prechecks pass: what is stored? Check the invariant under the actual protection:

- a single conditional statement (`UPDATE stock SET qty = qty - 1 WHERE id = ? AND qty >= 1`) whose affected row count is checked;
- a version column compared in the `WHERE`, with zero rows handled as a conflict;
- a row lock (`SELECT ... FOR UPDATE`) taken in the write's transaction and held until commit;
- a unique constraint enforcing a check-then-insert;
- a serializable transaction retried on serialization failure.

Defect signs: read, compute in code, write the whole value back (lost update); check-then-insert with no unique constraint; version read but not used in the `WHERE`; affected row count ignored; lock taken in another transaction than the write; an in-process lock guarding data shared by several instances; a rule across rows or ranges (a total under a cap, no overlapping bookings, "no active record exists") protected only by one row's version or a snapshot read, so two transactions both pass the check and write; shared mutable memory (static fields, singletons, module-level maps) changed concurrently without synchronization.

Usually correct: last-writer-wins where the contract allows it (a display name); an atomic database increment; a precheck for a clear message while a constraint enforces.

### 2.3 Transactions and partial failure

- Are the writes that must succeed or fail together in one transaction on one connection?
- Is the transaction really active? Check self-invocation bypassing a transaction decorator, a second connection, autocommit, and work handed to another thread or task.
- If it fails between two writes, what stays committed or visible? Does a catch inside the transaction let a partial write commit?
- On a commit timeout or lost response, does the code treat "unknown" as "failed" and repeat a write that must happen once? Unknown needs a lookup or safe replay.
- Does any path undo committed data by deleting it instead of the contracted compensation?

Defect signs: two saves with no transaction; a slow external call inside the transaction while row locks are held (rate by impact); a validation after the first write, which a rejection leaves in place.

Usually correct: a single-statement write; logs and metrics outside the atomic set; a follow-up the contract says a retrying job completes.

### 2.4 External calls, events and commit order

Place each external call or publish relative to the commit:

- **Before or inside the commit.** On rollback, the email, payment or event exists for data that does not; a defect when anyone acts on it.
- **After the commit, with no durable record.** A crash between commit and send loses the effect; a defect when the contract requires delivery.
- **Remote succeeded, local failed.** Is there compensation or reconciliation?
- **Response lost (timeout).** The remote side may have done the work; a blind retry repeats it unless the remote side honors an idempotency key.
- **Acknowledged before the effect is durable.** A crash after the ack loses the message.

Usually correct: an outbox row in the same transaction; an after-commit hook where the contract accepts occasional loss; read-only calls.

### 2.5 Retry, redelivery and duplicates

Ask: what happens when the client, a proxy, the scheduler or the queue sends the same request twice, possibly while the first still runs?

- A naturally idempotent effect (set status to X, upsert by natural key) is fine.
- Otherwise (charge, send, insert, increment), check the duplicate guard: an idempotency key enforced by a unique constraint in the effect's transaction, scoped to the operation and caller; a reused key with different content rejected; a replay returning the stored result; an in-progress record never reported as completed; retention covering the promised retry window.
- Queue consumers: unless the broker contract says otherwise, delivery is at least once; is the handler idempotent or deduplicated by message ID?
- Internal retry loops: only transient errors and operations safe to repeat, bounded attempts with backoff, a fresh transaction per attempt, no repeat of a call whose outcome is unknown?

Usually correct: retried reads or idempotent PUTs; a unique-keyed deduplication row inserted with the effect. Do not recommend a deduplication mechanism where no contract requires the effect to happen once.

### 2.6 Errors and cleanup

Each catch or error return is correct when it uses a fallback the contract allows, compensates, translates to the contract's error keeping the cause, or rethrows with context.

Defect signs: catch, log and return success, an empty list, a default or `null`; a dependency failure turned into "not found" or "no permissions", so the caller acts on a false fact; a broad catch that also hides programming errors; the wrong error class or status (500 for a validation error, 200 with an error body); a cleanup error replacing the original; a resource not closed on an early return; an ignored error return or an un-awaited async call.

Usually correct: ignored best-effort telemetry failures; catching one expected error the contract describes (duplicate key → return the existing record).

### 2.7 Money, numbers, time and text

- **Money.** Binary floating point (`float`, `double`, a JavaScript `number` with fractions) for amounts stored, charged, compared or summed is a defect; use decimals or integer minor units. Check currency minor units (JPY 0 decimals, KWD 3), the rounding mode and where it applies (per line or on the total, per the contract), split parts adding up to the total (allocate the remainder), truncating integer division, and the order of conversion and rounding.
- **Numbers.** Units (milliseconds versus seconds), percentages as 0.15 versus 15, division by zero, parse failures, overflow and values out of the column's range.
- **Time.** Candidate: an instant stored in local time or with no offset; confirm it when the schema, a contract or another reader expects UTC. Apply date-only rules (due today, end of month) in the contract's time zone. Check daylight-saving changes, month ends, leap days, and inclusive versus exclusive end times.
- **Text.** Normalize case and whitespace alike on write and lookup; check collation and whether length limits count bytes or characters.

Usually correct: floats for non-money ratios and metrics; rounding only for display when stored values are exact.

### 2.8 Boundaries, lists and batches

- Test each comparison at its edge: `<` versus `<=`, an inclusive end date, a count at the limit, zero or one item, the last page.
- Pagination: the sort order must be total (a unique tiebreaker such as the ID), and a cursor must encode every sort key and compare in the sort's direction. Offset paging under concurrent inserts can skip or repeat rows; a defect only when the contract promises a stable listing. "Has more" must be right when exactly `limit` rows remain: fetch `limit + 1`. Candidate: a page size the client can raise with no server cap.
- Batches: handle an empty `IN ()` list and duplicate input IDs; report errors at the input's original positions when the contract asks. Candidate: a batch with no maximum size.

Usually correct: offset paging on an internal list with no stability promise.

### 2.9 Queries and load

- **Per-item queries (N+1).** A query or remote call inside a loop over a result whose size grows with data or user input is a candidate. Confirm it only when the list size is user- or data-driven on a request path and a contract or sourced latency limit applies; otherwise it is a suggestion. Rate it by measured or sourced impact. Usually correct: a loop bounded by a small constant, a batched `IN` fetch, eager loading configured in the ORM, a per-request cache.
- **Unbounded work and timeouts.** Candidates: a user-driven query with no limit; a whole table loaded into memory; a new filter on a large table with no index (cite the schema); an external call with no timeout; retries multiplying across layers (3 × 3 × 3 = 27).

### 2.10 Compatibility, deploys and migrations

When the project deploys by rolling update or can roll back, assume old and new versions run together and a rollback runs old code on data new code wrote.

- **Migrations.** A NOT NULL column with no default on a table old code inserts into; renaming or dropping a column or table old code reads; a column type change; a new enum value old readers reject; a long-locking change on a large table; a backfill overwriting rows written after it started; a migration that fails on re-run. Safe pattern: add the nullable or defaulted shape, deploy code handling both, backfill, remove the old shape later.
- **APIs and messages.** Removing or renaming a field; changing its meaning, unit or default; making an optional request field required; a decoder rejecting unknown fields, so an added field breaks old readers. The new version must process messages the old one queued, and old consumers still running must read new messages.
- **Configuration and flags.** Check the default for a missing setting and both branches of a switch; turning a flag off must stop the effect, not just hide the entry point.
- **Removal.** Before removing a field, method or endpoint, search every caller, including reflection, configuration, scheduled jobs and other services, and report unknown external consumers.
- **Released behavior.** "Released behavior preserved" needs a comparison of inputs, outputs, defaults, failures, ordering and side effects with the released artifact or an approved equivalent, not a development branch; if unavailable, it is a pending gate with an owner.
- **Documentation.** When behavior changes, check that the API schema, interface comments and error catalog describe the new nullability, units, failures and effects; a stale description callers rely on is a finding.

Usually correct: an added nullable column or optional response field that clients ignore.

### 2.11 Tests

For each changed behavior and test, ask: if the change were reverted or the guard deleted, would a test fail?

Defect signs: no assertion, or only not-null, no exception or status 200; an expected value computed by the code under test; asserting a mock's own return value; verifying a mock call but not the result or stored state; a catch swallowing failures; a disabled test; fixed sleeps or identical payloads standing in for a concurrency test; a test name promising what the assertions do not check; only the happy path for a change that adds a rejection.

A missing test is a test-adequacy finding, not a production defect, unless a project rule requires it. A test that claims a behavior but cannot fail is a finding, rated by what it lets through. Say which tests you ran, on which revision, with what result; reading code is not running it.

### 2.12 Deeper checks

Open a [Risk Checks](references/risk-checks.md) section only when its trigger is in the inventory.

| Trigger in the change | Section in Risk Checks |
| --- | --- |
| Clocks across machines; value equality, collection identity, replacements | Values, Time and Collections |
| Locks, connection pools, leases or waits on other work | Locks and Progress |
| Queues, jobs, async commands, compensation, resource lifetimes | Asynchronous Work and Recovery |
| Deadlines, expensive input, shared capacity, retry chains | Budgets and Capacity |
| An existing cache, or an offline data investigation | Caches and Diagnostics |
| Client values reaching queries, files, processes or deserialization; personal or secret data | Data Protection and Technical Operations |
| Live migration of retained data, destructive conversion, rollback, dynamic configuration | Migration, Release and Configuration |
| Protocol or format changes | Compatibility Evidence |
| Failure logging, or a silent failure that could hide accepted work | Logs and Detection |
| Direct or transitive dependency upgrades | Dependency Upgrades |
| A test in the change claims to prove concurrency, dependency-failure or money behavior | Test Evidence |

## Step 3: Verify each candidate

Try to disprove each candidate and re-checked comment.

1. **Name the contract** you can cite, looking in this order: (1) the request, ticket, requirement or design document; (2) API schemas, interface docs, comments, and names that promise behavior (`reserveOnce`, `idempotencyKey`, `amountCents`); (3) the database schema: constraints, types, defaults, unique keys; (4) existing tests and the released behavior callers rely on; (5) project rules: coding standards, error-code catalogs, review policies. These baseline obligations also count when the code makes them reachable:
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
5. **Classify.** Confirmed: the trigger is reachable and violates a located contract. Uncertain: the trigger is reachable and a contract source plausibly governs it but is silent or ambiguous, or one decisive fact is unknown; name the source and the question. Not substantiated: a defense stops it, the path is unreachable, or you checked the five sources and the baseline list and none covers the input; if still worth doing, it may be a suggestion. Impact, experience, a missing test or a hypothetical caller alone confirms nothing.

If a project rule requires a verifier other than the proposer, record that check as a pending gate; it does not downgrade a demonstrated defect.

## Step 4: Rate severity

Rate by impact and reachability, not style or missing tests; a project's own scheme overrides this one.

- **Blocker:** reachable in normal use or routine conditions (a retry, two concurrent users, a deploy), causing unauthorized access, data loss or corruption, wrong money, a duplicate irreversible effect, or an outage or failed deploy.
- **Major:** a wrong result or failure with limited scope or easy recovery; a Blocker-class impact that needs uncommon but realistic conditions; a hot path that breaks a contracted or sourced latency limit.
- **Minor:** small impact, rare conditions, simple recovery.

## Step 5: Propose the fix

- Give the narrowest fix that removes the trigger; do not remove valid validation, error classification, concurrency guards or negative tests as duplication.
- Acceptance, in order: a test that fails on the current revision at the target assertion (not on compilation, environment or skipped tests, and never by changing expectations); the minimal complete fix; the same test passing; review by someone other than the fix's author; the project's quick checks, and release checks before release.
- For an Uncertain candidate or open business choice, give the question, evidence, owner, and the consequences of changing the code, documenting the current behavior, or leaving it; neither of the last two waives a mandatory requirement. An approved exception names its approver, scope and expiry.

## Step 6: Report

Use the compact report for one bounded change; omit empty sections. Verdict: Not mergeable for a confirmed Blocker, or decisive evidence missing for a promised behavior; Mergeable after fixes for confirmed Major or Minor findings, or pending gates with owners; otherwise Mergeable.

```
Verdict: Mergeable | Mergeable after fixes: F1, F2 | Not mergeable: F1
Scope: <revision or diff>; entry points reviewed; not covered: <what and why>

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

Checked, no finding: <Step 2 areas that applied and were clean>
Not applicable / Not checked: <areas — reason>
Candidates: <n> checked — <c> confirmed, <u> uncertain, <d> not substantiated
Checks run: <commands and results, or "none; review by reading">
Workspace: <changes before and after the review, or "unchanged">
Pending gates: <required checks or approvals not yet done, each with an owner>
```

Order findings by severity, with Uncertain items and suggestions kept out. Count a not-substantiated candidate rather than keeping it as a suggestion; list at most three suggestions.

For several independent concerns or a requested full report, add a requirement → evidence map (missing, inapplicable and unverified items marked), one block per concern, each candidate's disposition, owner decisions, remediation and release steps (for a released fix: the signal to watch, its owner, the stop condition) and, when 2.10 applied, compatibility evidence.

Recommend acceptance only within what you verified; a clean review proves nothing about production.

## Self-check

- [ ] Every finding passed Step 3: a reachable trigger, a located contract (a contract or sourced limit for edge cases, hardening and performance), a searched defense, a consequence and the narrowest fix.
- [ ] Every changed block maps to a requirement; skipped Step 2 sections are listed; Uncertain items name the source, question and owner and stay out of the findings.
- [ ] Fixes stay inside the established architecture, with any architecture change a separate owner decision; no code, data, services or credentials touched; workspace recorded; unrun checks pending.
- [ ] One bounded change gets the compact report, ordered by severity.
