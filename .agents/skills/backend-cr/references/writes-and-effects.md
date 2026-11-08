# Writes and Effects

Apply these sections as Step 2 sections of SKILL.md: answer each question for every inventory entry whose subject the section has, and pass every candidate through SKILL.md's Step 3.

## 2.2 Protections against concurrent writes

Check the invariant under the actual protection:

- a single conditional statement (`UPDATE stock SET qty = qty - 1 WHERE id = ? AND qty >= 1`) whose affected row count is checked;
- a version column compared in the `WHERE`, with zero rows handled as a conflict;
- a row lock (`SELECT ... FOR UPDATE`) taken in the write's transaction and held until commit;
- a unique constraint enforcing a check-then-insert;
- a serializable transaction retried on serialization failure.

Defect signs: read, compute in code, write the whole value back (lost update); check-then-insert with no unique constraint; version read but not used in the `WHERE`; affected row count ignored; lock taken in another transaction than the write; an in-process lock guarding data shared by several instances; a rule across rows or ranges (a total under a cap, no overlapping bookings, "no active record exists") protected only by one row's version or a snapshot read, so two transactions both pass the check and write; shared mutable memory (static fields, singletons, module-level maps) changed concurrently without synchronization.

Usually correct: last-writer-wins where the contract allows it (a display name); an atomic database increment; a precheck for a clear message while a constraint enforces.

## 2.3 Transactions and partial failure

- Are the writes that must succeed or fail together in one transaction on one connection?
- Is the transaction really active? Check self-invocation bypassing a transaction decorator, a second connection, autocommit, and work handed to another thread or task.
- If it fails between two writes, what stays committed or visible? Does a catch inside the transaction let a partial write commit?
- On a commit timeout or lost response, does the code treat "unknown" as "failed" and repeat a write that must happen once? Unknown needs a lookup or safe replay.
- Does any path undo committed data by deleting it instead of the contracted compensation?

Defect signs: two saves with no transaction; a slow external call inside the transaction while row locks are held (rate by impact); a validation after the first write, which a rejection leaves in place.

Usually correct: a single-statement write; logs and metrics outside the atomic set; a follow-up the contract says a retrying job completes.

## 2.4 External calls, events and commit order

Place each external call or publish relative to the commit:

- **Before or inside the commit.** On rollback, the email, payment or event exists for data that does not; a defect when anyone acts on it.
- **After the commit, with no durable record.** A crash between commit and send loses the effect; a defect when the contract requires delivery.
- **Remote succeeded, local failed.** Is there compensation or reconciliation?
- **Response lost (timeout).** The remote side may have done the work; a blind retry repeats it unless the remote side honors an idempotency key.
- **Acknowledged before the effect is durable.** A crash after the ack loses the message.

Usually correct: an outbox row in the same transaction; an after-commit hook where the contract accepts occasional loss; read-only calls.

## 2.5 Retry, redelivery and duplicates

Ask: what happens when the client, a proxy, the scheduler or the queue sends the same request twice, possibly while the first still runs?

- A naturally idempotent effect (set status to X, upsert by natural key) is fine.
- Otherwise (charge, send, insert, increment), check the duplicate guard: an idempotency key enforced by a unique constraint in the effect's transaction, scoped to the operation and caller; a reused key with different content rejected; a replay returning the stored result; an in-progress record never reported as completed; retention covering the promised retry window.
- Queue consumers: unless the broker contract says otherwise, delivery is at least once; is the handler idempotent or deduplicated by message ID?
- Internal retry loops: only transient errors and operations safe to repeat, bounded attempts with backoff, a fresh transaction per attempt, no repeat of a call whose outcome is unknown?

Usually correct: retried reads or idempotent PUTs; a unique-keyed deduplication row inserted with the effect. Do not recommend a deduplication mechanism where no contract requires the effect to happen once.
