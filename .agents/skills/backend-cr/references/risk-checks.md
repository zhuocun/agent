# Risk Checks

Use a section only when its trigger appears in the change, and only the checks the code makes reachable; note each one's trigger, contract or sourced limit, evidence and result. A check here yields a candidate until SKILL.md's Step 3 confirms it, and grants no permission for operational actions. Prefer the project's existing mechanisms over a new facility.

## Values, Time and Collections

- **Clocks across machines.** When expiry, leases, scheduling or cleanup compares times from different machines, find the time authority and allowed skew, and check clock jumps both ways. Local timestamp order is not global order; skew must not extend an access lifetime past its contract.
- **Elapsed and calendar time.** Measure timeouts and budgets with a monotonic clock. Add days, months and years with calendar operations; a fixed 24 hours is wrong across daylight-saving changes.
- **Numbers in transit.** The stored value must meet the column's type, scale and constraint, and a conversion must not bypass validation. Check exponent forms (`1e3`) and overflow at parsing. Do not demand exact decimals beyond money and counts.
- **Missing and empty values.** Distinguish a missing field, explicit null, an empty list, blank text, a default and a display value. A whole-record read-then-write must not drop fields the code does not understand.
- **Value semantics.** Equal values hash equally. Collections returned or passed in must not let callers change stored state; a read-only view or immutable value needs no copy.
- **Collection identity and limits.** Check the deduplication identity (every part of a compound key), how nulls count, per-group versus overall limits, and exact-limit and limit-plus-one cases. Splitting a batch must not change the whole set's result.
- **Replacements.** A replacement implementation or decorator accepts every input the original did and returns no weaker result.

## Locks and Progress

- **Locks and waits.** When work takes locks, connections, pool slots or leases, or waits on child work, trace acquisition order for cycles, waits on a task that needs the held slot, and starvation. Repeated timeouts do not prove progress. Do not add coordination to isolated, immutable computation.

## Asynchronous Work and Recovery

- **Authority.** Distinguish a user request, a delayed command acting for a user, and a notice of a completed fact. Check the producer, service identity, target tenant and delegation scope; an ID in the payload is not authority. For a delayed command, check the contract on permission changes, revocation and expiry before execution; for a completed-fact notice, check origin and permission to process, not the original user's current permission.
- **Acknowledgment.** Order the ack, consumer progress, business effect, retry handoff and final-failure handling. Under a durable-handling contract, the effect or a durable handoff precedes the ack; a function return, in-memory queue or fire-and-forget submit is not durable. Check partial batches and a crash at each step.
- **Order.** For effects that do not commute, find the required order, the routing key, the scope the broker actually orders within, and sequence evidence; check gaps, reordering and late arrivals against the contract. Partitions and timestamps do not prove global order. Do not demand ordering for commuting effects.
- **Stale writes.** A consumer applying a snapshot must not overwrite a newer one or drop increments the contract keeps.
- **Expired ownership.** When a lease can expire, the final write and the release check the worker's generation or token, so a stale worker cannot write or release its successor's lease.
- **Recovery after a crash.** Mark each interruption point: external call, local commit, outcome record, compensation, notification. Where recovery is required, the operation's identity and intent survive a crash or are rebuilt from durable data, and not executed, executed and unknown are distinguished. Manual recovery needs a detection condition, an entry point and executable steps, not just an owner. Do not invent a stronger promise than the accepted loss window.
- **Resource lifetime.** Owned resources (connections, files, threads, streams) close through nested scopes and shutdown; borrowed ones stay open for their owner. Restore request context after a nested scope. Observe failures of async work.

## Budgets and Capacity

- **Executed queries.** Check the statements actually executed and the plan where available; builder code or an index declaration is not evidence.
- **Remaining time.** Before new work or a retry, recompute the original budget minus queuing, processing and backoff, and pass a deadline on; a retry gets no fresh budget. With none left, start no new requested work and take the contracted failure or fallback; required cleanup runs under its own bounded budget or a durable handoff. Never pass a tiny remainder as 0 where 0 means no limit.
- **Total cost.** Where resource use changes, take sourced request rate, concurrency, payload size and data skew, and judge total amplification through parsing, decompression, serialization, lock hold time and retained results. Do not require a load test for an unrelated change.
- **Overload and retries.** Check concurrency limits, queue sizes, waits and backoff (with jitter for many clients) against real resource limits. Work running after a timeout still uses resources, and cancellation may not stop its effects. Failing fast can be correct. Do not add retries, circuit breakers or rate limiting by default.

## Caches and Diagnostics

- **Existing caches.** The key includes every input that changes the result, the caller's scope included. Distinguish cached success, "not found", dependency failure, expired and approved-stale entries. Check invalidation after writes and rollbacks, and that a slow fill cannot overwrite newer data. A shared cache must not replace a required per-request authorization check. Do not recommend a cache for request-local reuse.
- **Offline data investigation.** When an authorized investigation reads stored data, keep invalid raw values without widening valid domain states, record each row anomaly and continue, and stop on connection failure or an unknown decisive fact. Do not repair investigated data without permission.

## Data Protection and Technical Operations

- **Values reaching technical operations.** Trace client values into SQL, shell commands, file paths, URLs, templates and deserialization. Each must arrive bound, escaped or checked against an allowed set under the real execution rules; a value pasted into statement text breaks on quotes and changes the statement. Validation elsewhere does not make it safe there. A dynamic target (file path, outbound URL, class name) must come from an allowed set. Do not demand blanket sanitization of ordinary fields.
- **Personal and secret data.** Trace it through responses, logs, caches, messages, samples, backups and deletion. A debug setting must not disable peer authentication or transport encryption; secrets are replaceable, not hard-coded. Use the project's classification and mechanisms; do not invent cryptography.

## Migration, Release and Configuration

- **Live migration of retained data.** Check lock duration, load on business traffic, writes arriving mid-migration, progress tracking, bounded batches, safe re-entry and a stop condition. Reconcile business invariants, not only row counts. Do not override an explicit decision not to migrate.
- **Destructive conversion.** Identify the irreversible step and the promised recovery point, time and allowed loss. The original, a usable copy or a lossless reverse must exist and survive later writes; a backup setting is not proof of restore. Recovery must not overwrite later legitimate writes.
- **Release and rollback.** Distinguish "process started", "ready for traffic" and "business correct". Check the stop condition, every reachable mix of code, configuration, data and message versions, and in-flight work at switchover. Rollback is viable only with evidence the old version reads new data and handles outstanding work; otherwise record the limit and a forward fix. Never delete new data to make rollback look possible.
- **Live configuration changes.** Check invalid values, which version a request uses, which mixes are safe, and queued work. Turning a switch back on does not undo durable effects. Validate static settings at startup. Do not recommend dynamic configuration without a requirement.

## Compatibility Evidence

- **Real encoders and decoders.** Test a protocol or format change with versioned real encoders and decoders, old to new and new to old, for requests and responses. Assert an old decoder skips each added field where the protocol allows. Check types, IDs, units, enum values and unknown fields, or the required version negotiation or approved rejection. Check that stored data, queued messages and old clients still pass any new validation.
- **Duration.** Derive the needed combinations from client lifetimes, deploy overlap, retained and replayable messages, queued jobs, stored formats and promised backup restores.
- **Samples.** Produce samples with the delivered producer and the real client encoding; handwritten samples alone prove nothing.
- **Artifact dependencies.** Check dependency declarations, version authority, packaging and the target runtime, and build the affected artifacts; a host compile does not prove runtime compatibility.

## Logs and Detection

- **Useful, safe logs.** At the final error boundary, log the failure class, safe identifiers and the reason. Logs carry no secrets or whole sensitive payloads, strip control characters from client values, and bound field size.
- **Silent failure.** Apply when a sourced detection duty exists or a silent failure could hide an accepted write, external effect or completed job. Name the signal, its condition, window and response owner; distinguish zero traffic, zero errors and a missing signal, and cover "no progress". With no sourced detection time, record the missing owner decision. Do not instrument every pure function.

## Dependency Upgrades

- **Changed behavior.** Read the release notes of direct and transitive changes, checking serialization, time handling, retries, transactions, exceptions and connections. Relate published vulnerabilities to reachable runtime conditions, and mark unknown exposure unknown. A compile or a small version bump does not prove unchanged behavior. Do not upgrade unrelated dependencies.

## Test Evidence

- **Fault sensitivity.** When a changed guard or calculation controls authorization, stored data, money or an irreversible effect, check a test fails for a few relevant faults (flipped boundary, deleted guard, wrong classification, missing effect), by reasoning or an authorized isolated mutation.
- **Concurrency tests.** Use distinguishable writes and explicit states to drive success, conflict, abort, and confirmed and unknown commit, then check final contents and row counts. Waits are bounded and fail on timeout. Check storage-specific claims on the real engine and settings.
- **Dependency failures.** Drive scripted failures through the real adapter to the entry point, checking call budgets and unexpected calls. A stub that always succeeds does not test failure handling.
- **Execution claims.** Keep each claimed result's command, revision, selected tests, outcome and artifact freshness. A local run or in-memory store does not prove behavior on the target infrastructure.
