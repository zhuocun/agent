# State and Concurrency

Passes 4, 5, and 6 of the procedure in SKILL.md, which holds the fidelity rules (F1-F12) they cite.

## Pass 4: Make Facts And Representations Honest

- **4.1 Define identities, version axes, cardinality, ownership, and lineage.** Separate business, physical, and display identities from structural generations, business versions, and concurrency revisions.
  Pass condition: Define meaning, uniqueness scope, mutability, and preservation or regeneration on creation, copy, and replay. Trace migrated fields through source, purpose, conversion, default, storage, and readback. Do not infer ownership from names or position, wrap every scalar, or equate value changes with structural versions.

- **4.2 Define equality and mutable ownership.** Separate full-value equality/consistent hashing from business identity or deduplication.
  Pass condition: Mutating inputs, outputs, mutable elements, or reused builders cannot rewrite internal facts; equal values hash equally. Safe views and immutable leaves may suffice; serialization does not prove lossless deep copying. For consequential process-local state shared by concurrent tasks, establish ownership, atomicity, visibility, and safe publication under the execution model, including compound updates and partially initialized/reconfigured snapshots. Storage transactions, immutability labels, and sequential tests do not prove publication safety. Exclusive ownership, safe message passing, safely published immutable snapshots, or suitable synchronization may suffice.

- **4.3 Translate representations at owning boundaries.** Define field meanings across protocol, business, and storage forms under the effective boundary rules.
  Pass condition: Preserve identity, units, encoding, absence, defaults, and failure meanings. Keep protocol and storage forms out of the domain layer and port signatures; translate in adapters and use the chosen context-map relationship for foreign models (F1). Separate models only where sharing would carry an outer dependency inward or merge two contexts' meanings. Matching names or reflective copying do not prove correctness, and centralized conversion does not justify reversed dependencies.

- **4.4 Preserve required presence and round trips.** Define missing members, explicit nulls, empty collections or objects, blanks, defaults, and display values per affected field path.
  Pass condition: Typed reads and actual round trips preserve required distinctions. Do not discard unsupported content before whole-object writes, impose one policy on like-named fields, retain every physical form forever, or require configuration rewriting for state-only actions.

- **4.5 Establish suitable authoritative facts before judgment.** Specify source, identity, units, version, applicable dimensions, completeness, and absence meaning.
  Pass condition: Do not splice incompatible snapshots, treat bounded candidates as complete, or replace dependency failure with valid emptiness or success. Authorized empty results remain valid; candidate absence does not prove invalidity. Alternative authority requires a business decision, not an invented source.

- **4.6 Isolate diagnostic tolerance from online acceptance.** For authorized offline investigation, preserve invalid raw facts without expanding legal domain states.
  Pass condition: Record bad records and continue independently decidable ones while online corruption rejection remains unchanged. Stop dependent judgment on connection failure or missing decisive facts. Diagnostic permission does not authorize online writes or repair.

- **4.7 Define time semantics when correctness depends on time.** Distinguish instants, elapsed durations, calendar periods, event time, and processing time; name clock authority, zone, precision, and interval boundaries.
  Pass condition: Check relevant expiry, scheduling, ordering, replay, and leases against clock skew, clock adjustment, and calendar transitions. Use an appropriate monotonic source for elapsed time where available, without comparing unrelated process-local clocks. Verify applicable boundaries rather than assuming fixed-length days or synchronized clocks; do not mandate one format or zone.

- **4.8 Preserve numeric meaning when quantities affect correctness.** Specify range, representation, scale, precision, rounding stage and rule, and overflow or invalid-value handling across transport, computation, and storage.
  Pass condition: Boundary values, aggregation, division, and conversions preserve the promised result without silent truncation or identity loss. Distinguish exact quantities from permitted approximations and name allowed error. Do not prescribe one representation for all quantities.

## Pass 5: Define State Changes And Consumer Guarantees

- **5.1 Protect invariants before mutation.** Enumerate actual creation, save, submission, copy, reconstruction, and other write entries; assign controlled changes to the aggregate root or other invariant-owning boundary. When using aggregates, route creation and mutation through domain-owned operations; application code cannot assemble persistable aggregates by direct assignment. Keep creation distinct from persistence reconstruction.
  Pass condition: External assignment and reconstruction cannot bypass protection. Reject invalid changes before applying them and preserve the contracted failure state and change set. Entry prechecks do not replace owning-boundary protection or justify submission rules for copying.

- **5.2 Separate validation by lifecycle stage.** Define structural constraints, draft acceptance, submission completeness, copying, and reconstruction independently.
  Pass condition: Distinguish illegal structure, legal incompleteness, current inability to submit, and corrupted storage. Permit legitimate incomplete drafts to save or reconstruct; apply submission completeness only where required. Reconstruction does not legitimize corruption, and copying is not automatically submission.

- **5.3 State contracts that signatures cannot express.** Specify nullability, units, outcomes, failures, side effects, and non-obvious restrictions; maintain affected explanations.
  Pass condition: Consumers can use the capability without reading implementation, and explanations match behavior. Do not repeat obvious code, impose comment or authorship formats, introduce empty wrappers, or place process arguments in production code.

- **5.4 Specify postconditions and substitutability.** Distinguish accepted, completed, and partially successful outcomes, per-input correspondence, completeness, and allowed failure state.
  Pass condition: Alternatives and decorators do not strengthen preconditions or weaken promised outcomes. Callers need not identify the implementation to repair guarantees. Use types and tests where sufficient; do not upgrade draft acceptance into submission validation.

- **5.5 Bind admission confirmation to current facts.** Where confirmation permits proceeding, bind server-verifiable evidence to the object, actor, and relevant current facts.
  Pass condition: Clients cannot forge it, encoding is unambiguous, and relevant changes invalidate old confirmation. Bypass only the agreed soft warning, never hard checks or final guards. Display-only confirmation needs no automatic credential; do not assume single use or equate confirmation with idempotency or commit.

- **5.6 Verify authorization wherever access restrictions apply.** Define trusted actor or service identity, delegation, tenant, object, action, and field scope.
  Pass condition: Reads, writes, batches, asynchronous work, and replay cannot bypass policy through another entry or caller-supplied identity. Verify forbidden actor-object-action combinations. Validation and confirmation do not replace authorization. State revocation effects on in-flight work under the required guarantee without inventing a stronger one or changing approved failure order.

## Pass 6: Prove Atomicity And Concurrency Boundaries

- **6.1 Enumerate the complete atomic write set.** Include business state and durable business records required to commit together or not at all.
  Pass condition: Success means established commit under the storage contract, not a matched write or held lock. Established pre-commit failure aborts the set; caught failure cannot permit partial commit. Response loss does not undo established commit. Commit interruption or connection/session failure may mean an unknown outcome; resolve or safely deduplicate it before retrying. Rejected guards leave no success-asserting record from the atomic set. Independently required rejection, attempt, deduplication, or security-audit records may survive through an explicit independent durability boundary and must describe actual outcomes. Batching cannot split atomicity; disposable telemetry is distinct.

- **6.2 Define concurrency per action.** State expected state, structural generation, validity, content revision, write set, final guards, and affected cardinality where applicable.
  Pass condition: Final writes guard the judged content. Distinguish matched from changed counts and classify missed guards by cause; zero is not inherently conflict. Preserve authorized last-write-wins saves and server-only revisions rather than imposing client revisions everywhere.

- **6.3 Separate uniqueness prechecks from enforcement.** Identify the effective unique constraint or equivalent serialization for every strong uniqueness claim.
  Pass condition: Requests passing prechecks concurrently cannot create forbidden duplicates; independently verify actual target constraints. Prechecks alone prove only best effort. Do not make every field unique or remove checks with a remaining responsibility.

- **6.4 Bound consistency and progress by actual protection.** Identify participants, protected state, valid interval, and uncovered windows for snapshots, locks, revisions, atomic writes, and cross-boundary protocols.
  Pass condition: Derive competing schedules from invariants/read-write sets, including reachable predicate/absence reads, write skew, stale snapshots, and expired lock/lease authority. Where a guarantee requires facts from a protected scope, verify that the decision being persisted uses the required facts from that scope for the same subject; acquisition alone is insufficient. Define the required equivalence or identity relation and reject writes that fail it; accept equal business fact values in distinct instances. Keep protection mechanisms and scope authority/lifetime checks in infrastructure, separate from domain business values and their equality. Final enforcement rejects invalid states/stale writers; one benign schedule does not establish coverage of other conflict classes. Cross-system strength requires a common participant protocol, not local mechanisms; authorized best-effort windows remain explicit. Where work waits on resources/coordination, establish required completion, throughput, or bounded rejection. Examine wait cycles, nested acquisition, resource-pool dependencies, reentrant callbacks, starvation, and canceled waiters where reachable. Show progress or recoverable rejection within required bounds; safe writes and finite retries alone do not prove it. Require no universal fairness or particular primitive.

- **6.5 Attribute and bound retries.** Distinguish generated collisions, unrelated constraints, lock failures, and uncertain commit results; retry only diagnosed, authorized failures.
  Pass condition: Define retry unit, finite limit, transaction boundary, waiting, and interruption. End the failed attempt before another and preserve unrelated original causes. Do not classify every integrity failure as one collision, prohibit all lock retries, or copy delay constants without a current basis.

- **6.6 Separate idempotency guarantees.** Define target-state, content-equivalence, request, internal-retry, external-replay, and response-loss guarantees independently.
  Pass condition: State contracted repeat effects on objects, records, and external actions; resolve uncertainty or establish safe deduplication before repeating work. For existing/required request deduplication, define key ownership/scope, content binding, concurrent claims, outcome/effect coupling, and retention covering permitted replay. Check simultaneous repeats, changed content under one key, and crashes between effect and result recording. Define late-repeat handling within the contract; add no keys where weaker guarantees suffice.

- **6.7 Close commit-to-delivery gaps for required propagation.** State delivery/duplicate-effect contracts, recoverable handoff, and receiver responsibility.
  Pass condition: Rolled-back operations publish no false business-success claim; independent outcome/audit records follow 6.1. Required committed work survives a crash before send. Uncertain sending is retryable within contracted loss/duplication bounds; where one business effect is promised, redelivery cannot add another. Transport alone does not establish that promise. Reuse equivalent facilities; lossy telemetry or operation records alone require no message bus, delivery log, or event-sourced model.

- **6.8 Model external effects separately from local commit.** Distinguish remote reads, reversible reservations, and irreversible writes; state their ordering.
  Pass condition: Assign recovery responsibility or an authorized window for remote success/local rollback, local commit/remote failure, and remote execution/lost response. Local rollback does not undo remote effects. Do not add compensation without writes, split required atomic sets, or move all remote reads outside transactions regardless of snapshot and waiting needs.

- **6.9 Close consumption-to-effect gaps for actual asynchronous consumers.** Define acknowledgement, checkpoints, durable effects, ownership, recovery, and promised loss/duplication/order bounds.
  Pass condition: For required durable handling, acknowledge only durable effects or recoverable handoff. Check crashes, concurrent redelivery, and uncertain acknowledgement against the agreed bounds; prevent second effects where promised, not for explicitly repeatable processing. Where order matters, handle gaps, staleness, and replay according to snapshot/incremental semantics. Bound repeated failure, assign visible ownership, and provide authorized recovery without silent loss of required work or indefinite blockage. Require no unnecessary global order.

- **6.10 Ground storage guarantees in deployed conditions.** For consequential storage operations, state actual atomicity scope, isolation, acknowledgement, durability, and read visibility.
  Pass condition: Account for applicable records, documents, partitions, replicas, failover, and configured read/write policies. A successful acknowledgement alone proves neither durable commit nor fresh reads. Support contracted loss and visibility limits with configuration and risk-appropriate evidence; disclose accepted weaker guarantees without mandating a storage technology.
