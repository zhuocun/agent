---
name: backend-architecture
description: >-
  Use when designing or reviewing backend system architecture, responsibility
  boundaries, domain and data models, consistency guarantees, integration
  contracts, operational risks, or evolution strategies. Assess system-level
  decisions and their evidence. Do not use for line-by-line review of a specific
  backend diff for correctness, failure paths, contracts, data and concurrency
  bugs, test effectiveness, or change scope; those requests require concrete
  code review. In mixed requests, apply this procedure only to the architecture
  decisions. Do not use for frontend architecture or prose-only editing.
---

# Backend Architecture

Design and assess backend systems through responsibilities, business guarantees, reachable failures, and verifiable decisions. Deliver architecture conclusions, correction options, and an acceptance procedure. Do not turn architecture review into line-by-line code review or implement, merge, or deploy without authorization.

Apply this priority order: **effective requirements and authorization > business correctness and data protection > honest consistency and failure guarantees > evidence and operability > responsibility boundaries and evolution > minimum sufficient complexity > presentation**. Let explicit requirements override external extensions.

Evaluate roles and guarantees, not a prescribed programming paradigm. Treat cores, ports, objects, and adapters as responsibility descriptions, not mandatory classes, interfaces, duplicate models, or modules. Permit combined roles and shared representations only when the effective baseline allows them and required guarantees remain protected. Enforce invariants at their owning boundary through suitable functions, objects, or atomic operations. Require further separation only for a demonstrated boundary, correctness, or evolution need.

## Select The Review Depth

Run the basic path: establish mandate and impact closure, challenge mechanism necessity, inspect affected responsibilities/contracts, and report evidence and limits. Classify as **Basic** when tracing excludes changed guarantees and reachable specialist risks; **Focused** when a specific risk is reachable; **Consequential** when reachable failure threatens material data loss, unauthorized effects, or required cross-boundary/availability/recovery guarantees. Simple localized work without those risks uses only the basic path; size alone does not establish safety.

Deepen only affected paths, including proposed design paths. Record triggers and selected clauses; reuse valid evidence for unchanged guarantees. Infrastructure elsewhere does not trigger a system-wide audit. Mark exclusions `Not applicable: <reason>` with tracing grounds and missing proof `Unknown`. Create no mechanism merely because a pass names it.

- **Data and state:** changed fact meanings, representations, lifecycle entries, or durable writes trigger relevant Passes 4-6; time/numeric checks require correctness dependence on those values.
- **Concurrency and integration:** shared mutable state, competing invariant updates, cross-process calls, required propagation, or message consumption trigger matching concurrency, delivery, deadline, overload, and resource checks.
- **Operations and protection:** affected resource use/retention, access restrictions, sensitive flows, promised deletion, caches, dangerous operations, or availability/recovery assumptions trigger matching checks in Passes 5 and 7.
- **Evolution and proof:** affected published contracts, durable formats, support windows, mixed versions, or configuration transitions trigger Pass 8 and compatibility evidence; architecture guards trigger 9.2 and high-consequence guarantees trigger 9.5.

## Deliverable

Use applicable slots in order; combine headings when useful. For Basic work, retain concise scope/baseline and obligation/evidence rows, the decision or findings, and evidence/status. Keep the review arrangement (2) in every report. Omit candidate records/dispositions (3-4) when no candidates exist, owner decisions (5) when no unresolved owner choices exist, correction/release planning (6) when neither is proposed, compatibility matrices (7) when tracing excludes affected supported boundaries, and measurements within (8) if no relevant change or claim exists. For Basic work, one grounded scope statement may explain all omitted slots; otherwise give each omitted slot one sentence `Not applicable: <reason>`. Missing required work is pending, not inapplicable.

Focused reports include triggered proofs; Consequential reports expose decision-driving scenarios, failure evidence, and residual risks separately. Explicit effective reporting obligations override shortcuts. Accept a decision/review report separately from correction/release acceptance. Keep only actually required adjudication, independent-review, or execution gates pending; do not invent gates or claim plans as execution.

1. **Scope and baseline.** Name revision, effective requirements/decisions, observed state, approved target, assumptions, authorization, protected objects, and exclusions. Inventory code rules, architecture design documents, implementation documents, architecture tests, and contracts as separate categories: give each category's search scope and in-scope authoritative requirements, or record that none was found; for architecture tests, name the boundary each enforces. Describe tracing through entries, consumers, persisted forms, and effects, including unresolved external consumers. Map each obligation to source, applicability, acceptance condition, object, evidence status, and conclusion.
2. **Review arrangement.** Fix one brief containing baseline, authorization, protected objects, and questions. Separate architecture alignment from unnecessary complexity in each review. Give the identical brief to at least two independent reviewers and obtain their initial judgments before sharing conclusions; effective requirements may raise this number, never waive it. Record assignments, independence, completion, disagreements, and adjudication. If reviewers are unavailable or delegation is unauthorized, disclose local checks and retain the exact required procedure as a mandatory pending acceptance step. Local passes and implementation review do not replace it, and the absence of a written staffing rule does not make it inapplicable.
3. **Finding records.** Give each candidate's affected decision/object, reachable trigger/path, consequence, specific violated authoritative clause or explicit guidance-only basis, severity/impact rationale, precise evidence, and narrowest correction direction. Distinguish demonstrated defects, conditional risks, verification gaps, and optimization proposals. Missing authority or reachability is missing proof, not a conformance breach. Order actionable findings by severity.
4. **Verification, adjudication, and counts.** Recheck decisive facts against primary evidence independently of the producer's verdict. Classify distinct issues as `Confirmed`, `Unresolved`, or `Rejected`, with grounds; preserve every candidate or merge link. Reconcile these three counts separately from requirement coverage. `Unresolved` is provisional. Before accepting correction scope, finalize each candidate: confirm, reject, or retain the design with evidence and any required bounded exception approval. Retention does not disprove a confirmed issue. Missing proof needs an owner and pending adjudication, not a fabricated verdict. Reconcile final dispositions, correction list, change allowlist, validation scope, and counts; remove or narrow unsupported proposals. Close confirmed gaps only with accepted correction evidence or an approved bounded exception, not registration. Report delivery does not establish completed adjudication. Keep one disposition table covering every candidate, with final verdict, decisive evidence, correct-or-retain decision, and its write-back to the correction list, change allowlist, and validation scope; when evidence is missing, name it and the decision owner, and make disposition and write-back mandatory before correction-scope acceptance.
5. **Owner decisions.** Give unresolved business, permission, external-ownership, scope, or exception choices with authority, feasible options, tradeoffs, recommendation, and blocked work. Invent no approval gates for authorized factual corrections; do not decide unspecified product policy. Keep functional repairs outside architecture-only restructuring unless separately authorized.
6. **Correction and acceptance sequence.** Give the smallest cost-reviewed correction plan and each applicable gate's role, procedure, scope, and pass condition. Derive gates from effective policy/requested outcome. For code corrections requiring merge/release acceptance, order semantic failing-test evidence, minimum correction and passing tests, implementation-independent review, then final disposition/scope/behavior/gate acceptance before merge. Use controlled counterexamples for already-correct protections, not unrelated setup failure. Define quick gates as named focused checks with scope/pass criteria; repeat them and packaging on the merged revision when merge is required. For release acceptance, identify artifact/configuration, deploy that artifact in a suitable verification environment, and run the complete agreed product regression, not only smoke or changed-path tests. Define safe release-target checks separately and require no new product defects within scope. Apply 9.3 execution safety. Review/design work supplies the applicable future plan without claiming execution; justify inapplicable stages.
7. **Bidirectional compatibility.** Enumerate reachable old/new sender-receiver pairs for affected requests, responses, and events: old requests/new implementations, new requests/old implementations, new responses/old consumers, and old responses/new consumers, plus same-version pairs. Include rollout, rollback, delayed delivery, replay, unknown members, old entries/new protections, and old code reading new facts/in-flight work where supported. Attach evidence or pending checks. Protect unsupported pairs through routing, negotiation, activation order, conversion, or rejection; labeling them unsupported is insufficient. Exclude pairs only with unreachability evidence.
8. **Quantified results.** Fix baseline, population, units, method, and evidence. Apply 1.3 coverage counting; separate verification and final disposition counts. Prefer item status when percentages add no decision value. For implemented corrections, separate production lines added/removed/net from tests/generated material, enumerate authorized behavior changes, and show protected behavior unchanged. Include relevant measured quality results. For unimplemented corrections, retain applicable outcome reporting as a correction-completion gate; distinguish measurements, estimates, targets, and unavailable results.

## Pass 1: Establish The Mandate And Evidence

- **1.1 Establish the effective baseline.** Identify effective requirements, object versions, superseded decisions, observed state, approved target, assumptions, and unknowns.
  Pass condition: Each conformance conclusion cites a specific authoritative clause, effective status, object, and evidence. Verify replacement relationships, not dates or completion labels. Distinguish repository obligations from general guidance, including this skill: guidance may justify optimization, not an undocumented repository violation. Record missing source categories and search scope. Implementation does not lower the target, and design does not prove implementation; label changes to approved decisions as proposals.

- **1.2 Verify decisive facts independently.** Treat comments and prior verdicts as leads, then inspect the evidence that decides each claim.
  Pass condition: Confirmed, unresolved, and rejected claims each have inspectable grounds. Repetition, agreement, reviewer identity, and producer self-assessment do not prove a claim. Keep evidence verification distinct from independent review organization.

- **1.3 Verify promised coverage.** Trace separately decidable obligations through affected decisions, entries, consumers, persisted forms, effects, and evidence.
  Pass condition: Cover promised full scope or focused impact closure and record enumeration/tracing methods. Each row has source, applicability, acceptance condition, and evidence status. Fix population/counting rules before reporting coverage: distinguish satisfied, failed, partial, unknown, and justified inapplicable rows. Only fully evidenced satisfied rows count as covered; include failed/partial/unknown applicable rows in the denominator and exclude only grounded inapplicable rows. Missing, unexecuted, unexamined, or unverifiable evidence is not a pass. Item status may suffice; favorable totals cannot close a failed high-consequence obligation.

- **1.4 Protect authorized scope and behavior.** List permitted changes and frozen code, contracts, configuration, and other objects before proposing repairs.
  Pass condition: Every proposed difference serves the authorized objective. Preserve returns, rejection, error identities, failure order, commit effects, and side effects except for explicit approved changes. Where zero changes are required outside scope, require a baseline diff proving zero, not merely equivalent behavior. Obtain scope authorization before touching frozen objects; separate unrelated functional fixes.

- **1.5 Separate correction from business choice.** Apply established requirements to factual errors within granted authority; identify unspecified policy and ownership choices for the responsible decision maker.
  Pass condition: Each unresolved choice states its options and blocked decision. Neither implementation nor review silently freezes it, and already authorized corrections receive no invented approval gate.

- **1.6 Bound exceptions and transitions.** Record approval grounds, precise location and conditions, existing protection, and review or expiry trigger.
  Pass condition: Registration is not approval. Local permission does not exempt a category or survive expired conditions. Describe a transition's deviation and convergence direction instead of claiming full compliance.

## Pass 2: Choose The Smallest Justified Design

- **2.1 Compare decision-relevant alternatives.** State which goals or consequences make a decision consequential; compare no change, the simplest viable change, and credible alternatives that could change the choice.
  Pass condition: Present each candidate in its strongest feasible form under common constraints, and give constraint-based exclusion reasons. Record premises, deciding scenarios, benefits, costs, sensitivity, evidence gaps and affected conclusions, direction, and reconsideration triggers in a shared authoritative record. Do not claim an unbounded search or global optimum. Determine direction before scheduling cost; distinguish research acceptance from implementation authorization. Use a compact record for a small decision.

- **2.2 Justify adding and removing mechanisms.** Identify the current requirement or reachable failure, consequence without protection, existing safeguards, simpler equivalents, and development, verification, operational, and maintenance costs.
  Pass condition: Admit a correction plan only after recording why its benefit justifies its cost under the effective constraints. Prefer no new framework, layer, or general mechanism; justify any indispensable addition and obtain authorization if it changes approved scope or design. Reconsider unaffordable options without silently closing a confirmed gap. Do not remove real validation, failure classification, concurrency guards, or effective negative tests merely to reduce code. Apply extensions by reachable impact, not change size or hypothetical reuse.

- **2.3 Express quality goals as testable scenarios.** State stimulus source, stimulus, operating conditions, affected element, response, and response measure for goals that drive the decision.
  Pass condition: Identify sensitive parameters, conflicting goals, and residual risks. Name unknown thresholds and the decisions they block instead of inventing numbers. One decisive scenario can suffice; do not mandate a workshop or scoring system.

- **2.4 Derive business boundaries from language and ownership.** Assign fact and rule owners, interactions, shared semantics, transaction and change responsibility, and non-goals.
  Pass condition: Actual interactions identify callers, owners, and translation points for differing meanings. Shared deployment, storage, or source organization does not invalidate a business boundary; relationships and views do not automatically create one.

- **2.5 Derive aggregate boundaries from invariants and lifecycle.** List states that must hold, freeze, or change together, forbidden combinations, and atomic actions.
  Pass condition: Explain each boundary and use an interleaving to justify a split's intermediate states and coordination cost. Do not infer business identity from a row or impose full aggregate machinery on simple data services. Reassess when independent identity, permissions, or lifecycle emerges.

## Pass 3: Assign Responsibilities And Dependencies

- **3.1 Distinguish dependencies, calls, and assembly.** Identify who declares, implements, calls, and selects each contract.
  Pass condition: Actual dependencies and cycles match the effective responsibility and permission matrix. Directory placement or successful loading is not permission. Do not impose fixed layers or a universal matrix; assembly may know contract and implementation.

- **3.2 Separate judgment from obtaining facts and coordinating work.** Give rules an explicit responsibility and fact inputs; assign authorization orchestration, transactions, and protocol conversion separately.
  Pass condition: Business judgment does not hide storage, remote, or assembly access, and entries and adapters do not duplicate invariants. Do not turn filtering, pagination, or projection into a mandatory domain service.

- **3.3 Place capability contracts with consumers.** Define justified ports by needed business capability and keep technical collaboration with its adapter owner.
  Pass condition: Each port has a real consumer and required semantics, not leaked storage or transport detail. Adapter-internal work does not detour through a core port. A necessary contract may have one implementation; one implementation alone does not justify an interface.

- **3.4 Make assembly explicit and safe.** Select required roles at the composition boundary and isolate real capabilities from local substitutes.
  Pass condition: Required selection is unique, mutually exclusive, and exhaustive. Missing security-critical implementation or configuration fails explicitly; unknown conditions cannot select a permissive substitute. Permit isolated development substitutes and optional observation without universal startup failure.

- **3.5 Match reads to use cases.** Select needed projections without needless loading of a complete mutable write aggregate.
  Pass condition: Queries neither save business state nor trigger lifecycle changes; jointly judged facts use the required consistent snapshot. Observation is not a business write. Load necessary objects for full judgment without mandating separate databases or event projections.

- **3.6 Keep one authoritative rule and lifecycle definition.** Assign authority for transitions, idempotent success, rejection, error identities, and detection responsibility.
  Pass condition: Reachable entries use authoritative semantics, not independent copies. Protect authorized mirrors and projections against drift without requiring every representation to share a type or identical projection.

## Pass 4: Make Facts And Representations Honest

- **4.1 Define identities, version axes, cardinality, ownership, and lineage.** Separate business, physical, and display identities from structural generations, business versions, and concurrency revisions.
  Pass condition: Define meaning, uniqueness scope, mutability, and preservation or regeneration on creation, copy, and replay. Trace migrated fields through source, purpose, conversion, default, storage, and readback. Do not infer ownership from names or position, wrap every scalar, or equate value changes with structural versions.

- **4.2 Define equality and mutable ownership.** Separate full-value equality/consistent hashing from business identity or deduplication.
  Pass condition: Mutating inputs, outputs, mutable elements, or reused builders cannot rewrite internal facts; equal values hash equally. Safe views and immutable leaves may suffice; serialization does not prove lossless deep copying. For consequential process-local state shared by concurrent tasks, establish ownership, atomicity, visibility, and safe publication under the execution model, including compound updates and partially initialized/reconfigured snapshots. Storage transactions, immutability labels, and sequential tests do not prove publication safety. Exclusive ownership, safe message passing, safely published immutable snapshots, or suitable synchronization may suffice.

- **4.3 Translate representations at owning boundaries.** Define field meanings across protocol, business, and storage forms under the effective boundary rules.
  Pass condition: Preserve identity, units, encoding, absence, defaults, and failure meanings. Keep external forms outside an established business core; do not invent a core or duplicate models where no such boundary is required. Matching names or reflective copying do not prove correctness, and centralized conversion does not justify reversed dependencies.

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

- **5.1 Protect invariants before mutation.** Enumerate actual creation, save, submission, copy, reconstruction, and other write entries; assign controlled changes to the invariant-owning boundary.
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
  Pass condition: Success means established commit under the storage contract, not a matched write or held lock. Established pre-commit failure aborts the set; caught failure cannot permit partial commit. Response loss does not undo established commit. Commit interruption or connection/session failure may mean an unknown outcome; resolve or safely deduplicate it before retrying. Rejected guards leave no success-asserting record from the atomic set. Independently required rejection, attempt, deduplication, or security-audit records may survive through an explicit independent durability boundary and must describe actual outcomes. Batching cannot split atomicity; disposable observation is distinct.

- **6.2 Define concurrency per action.** State expected state, structural generation, validity, content revision, write set, final guards, and affected cardinality where applicable.
  Pass condition: Final writes guard the judged content. Distinguish matched from changed counts and classify missed guards by cause; zero is not inherently conflict. Preserve authorized last-write-wins saves and server-only revisions rather than imposing client revisions everywhere.

- **6.3 Separate uniqueness prechecks from enforcement.** Identify the effective unique constraint or equivalent serialization for every strong uniqueness claim.
  Pass condition: Requests passing prechecks concurrently cannot create forbidden duplicates; independently verify actual target constraints. Prechecks alone prove only best effort. Do not make every field unique or remove checks with a remaining responsibility.

- **6.4 Bound consistency and progress by actual protection.** Identify participants, protected state, valid interval, and uncovered windows for snapshots, locks, revisions, atomic writes, and cross-boundary protocols.
  Pass condition: Derive competing schedules from invariants/read-write sets, including reachable predicate/absence reads, write skew, stale snapshots, and expired lock/lease authority. Final enforcement rejects invalid states/stale writers; one benign schedule does not establish coverage of other conflict classes. Cross-system strength requires a common participant protocol, not local mechanisms; authorized best-effort windows remain explicit. Where work waits on resources/coordination, establish required completion, throughput, or bounded rejection. Examine wait cycles, nested acquisition, resource-pool dependencies, reentrant callbacks, starvation, and canceled waiters where reachable. Show progress or recoverable rejection within required bounds; safe writes and finite retries alone do not prove it. Require no universal fairness or particular primitive.

- **6.5 Attribute and bound retries.** Distinguish generated collisions, unrelated constraints, lock failures, and uncertain commit results; retry only diagnosed, authorized failures.
  Pass condition: Define retry unit, finite limit, transaction boundary, waiting, and interruption. End the failed attempt before another and preserve unrelated original causes. Do not classify every integrity failure as one collision, prohibit all lock retries, or copy delay constants without a current basis.

- **6.6 Separate idempotency guarantees.** Define target-state, content-equivalence, request, internal-retry, external-replay, and response-loss guarantees independently.
  Pass condition: State contracted repeat effects on objects, records, and external actions; resolve uncertainty or establish safe deduplication before repeating work. For existing/required request deduplication, define key ownership/scope, content binding, concurrent claims, outcome/effect coupling, and retention covering permitted replay. Check simultaneous repeats, changed content under one key, and crashes between effect and result recording. Define late-repeat handling within the contract; add no keys where weaker guarantees suffice.

- **6.7 Close commit-to-delivery gaps for required propagation.** State delivery/duplicate-effect contracts, recoverable handoff, and receiver responsibility.
  Pass condition: Rolled-back operations publish no false business-success claim; independent outcome/audit records follow 6.1. Required committed work survives a crash before send. Uncertain sending is retryable within contracted loss/duplication bounds; where one business effect is promised, redelivery cannot add another. Transport alone does not establish that promise. Reuse equivalent facilities; lossy observation or operation records alone require no message bus, delivery log, or event-sourced model.

- **6.8 Model external effects separately from local commit.** Distinguish remote reads, reversible reservations, and irreversible writes; state their ordering.
  Pass condition: Assign recovery responsibility or an authorized window for remote success/local rollback, local commit/remote failure, and remote execution/lost response. Local rollback does not undo remote effects. Do not add compensation without writes, split required atomic sets, or move all remote reads outside transactions regardless of snapshot and waiting needs.

- **6.9 Close consumption-to-effect gaps for actual asynchronous consumers.** Define acknowledgement, checkpoints, durable effects, ownership, recovery, and promised loss/duplication/order bounds.
  Pass condition: For required durable handling, acknowledge only durable effects or recoverable handoff. Check crashes, concurrent redelivery, and uncertain acknowledgement against the agreed bounds; prevent second effects where promised, not for explicitly repeatable processing. Where order matters, handle gaps, staleness, and replay according to snapshot/incremental semantics. Bound repeated failure, assign visible ownership, and provide authorized recovery without silent loss of required work or indefinite blockage. Require no unnecessary global order.

- **6.10 Ground storage guarantees in deployed conditions.** For consequential storage operations, state actual atomicity scope, isolation, acknowledgement, durability, and read visibility.
  Pass condition: Account for applicable records, documents, partitions, replicas, failover, and configured read/write policies. A successful acknowledgement alone proves neither durable commit nor fresh reads. Support contracted loss and visibility limits with configuration and risk-appropriate evidence; disclose accepted weaker guarantees without mandating a storage technology.

## Pass 7: Test Reachable Operational Failure Modes

- **7.1 Establish affected workload, capacity, and durable-growth bounds.** Define authorized data size, concurrency/arrival rate, amplification, resource limits, and operating horizon.
  Pass condition: Consider relevant tail latency, memory, connections, queues, background contention, skew, and cold caches. For accumulating durable state, state growth assumptions, retention authority, and headroom for base data, indexes, history, retained messages, and failed work. Include recovery/backfill/compaction temporary space and reduced throughput; define detection/safe response before exhaustion or disclose the missing bound. Short load tests and bounded request memory alone do not prove sustainable storage. Keep conditions with claims; reuse valid evidence for unaffected bounded paths instead of load-testing every edit or adding unjustified archival/distributed mechanisms.

- **7.2 Bound overload and retry amplification.** Combine attempts across layers and constrain concurrency, queues, and waiting by real resources.
  Pass condition: Define rejection, isolation, or authorized degradation and assess synchronized retries where relevant. Count work continuing after timeout; propagate supported cancellation without claiming unsupported termination. Prompt failure without retry can suffice; limiters and circuit breakers are not mandatory.

- **7.3 Make consequential results and failures diagnosable.** Select business success, rejection, technical failure, latency, and relevant saturation or backlog signals.
  Pass condition: Retain needed cross-boundary correlation, bounded dimensions, and protected sensitive content. Where timely detection is required, specify detection condition, observation and detection delay, responder, and response procedure. Check a representative actionable failure signal and missing or stale telemetry; unknown thresholds remain gaps. Reuse adequate monitoring or manual checks without requiring a new platform or per-function instrumentation.

- **7.4 Define consistency for existing caches.** Specify complete cache identity, allowed staleness, invalidation, and concurrent refresh.
  Pass condition: Include every answer-changing dimension and distinguish negative answers, dependency failures, and expiry. Cache publication cannot advertise a rolled-back change as committed; stale refresh cannot overwrite newer facts. Expiry alone proves no strong freshness. Keep permission-sensitive facts within authorized use; build no cache for this check.

- **7.5 Assign technical trust boundaries for reachable dangerous operations.** Trace untrusted influence on queries, network targets, files, processes, and deserialized types.
  Pass condition: Separate values from executable structure and constrain targets under actual execution semantics, not surface spelling. Login and business validation do not replace technical controls. Do not impose one sanitizer on every field or audit unrelated systems.

- **7.6 Protect actual sensitive flows and promised deletion.** Identify allowed readers and transmission, storage, cache, sample, backup, and deletion boundaries under established classification.
  Pass condition: Debugging cannot silently disable required peer authentication/communication protection; long-lived secrets remain replaceable. Where deletion/expiry is promised, define authoritative deletion state and permitted retention across projections, caches, diagnostic copies, replay sources, and recovery material. Delayed work, replay, or restoration cannot reintroduce forbidden data/effects. If recovery material cannot be rewritten immediately, bound retention/access and reapply deletions before serving restored state. Preserve independently required retention, not universal immediate erasure. Reuse validated protection; invent neither cryptography nor identical encryption/secret infrastructure for all data.

- **7.7 Verify required availability and recoverability.** For non-reconstructible state, define acceptable loss, recovery time, material, and dependencies; for availability dependent on replicas, failover, or restart, identify shared failure domains and startup/runtime dependencies.
  Pass condition: Authorized isolated restoration from actual material demonstrates readability, invariants, required deletion state, and external reconciliation; backup-job success is insufficient. For availability claims, evaluate relevant component loss, partition, stalled/shared dependencies, shared credentials, startup/health-check cycles, and capacity during failure/recovery. Show required response or bounded degradation; replica counts and normal-load success do not prove it. Disclose unperformed checks. Reconstructible transient state needs no separate backup; single-instance/manual recovery is valid when it meets agreed goals.

- **7.8 Budget deadlines when completion time is constrained.** Allocate one budget across admission, queueing, resource acquisition, calls, retry delays, and attempts.
  Pass condition: Propagate remaining time where supported and start no attempt after budget expiry. Distinguish definite failure from uncertain outcome; cancellation does not undo committed or irreversible work. Fallbacks retain required authorization, invariants, and freshness, and expose changed outcome semantics instead of claiming normal completion.

- **7.9 Assign ownership and lifetime for relevant resources.** Identify who releases or transfers connections, sessions, streams, cursors, handles, tasks, subscriptions, locks, and retained buffers.
  Pass condition: Completion, failure, cancellation, partial initialization, reconfiguration, and shutdown preserve lifecycle obligations. Bound long-lived retention or define reclamation. Use repeated-failure, sustained-workload, or equivalent justified evidence against resource growth after finished work. Eventual memory reclamation does not prove timely external-resource release.

## Pass 8: Plan Evolution And Recovery

- **8.1 Define authority and rollback facts per evolution stage.** State entry/pass conditions, permitted writers, authoritative read priority, migration progress, switch conditions, rollback action, and fact source.
  Pass condition: Coexistence creates no conflicting authoritative writers. Preserve executed migration history and independently verify actual structures and constraints. Separate initialization from incremental migration; give irreversible changes a recovery direction rather than claiming an inverse script proves rollback. Do not mandate a switch.

- **8.2 Evolve contracts for real consumers and support windows.** Preserve supported guarantees for published identity, types, units, defaults, failures, and consumption semantics; give new semantics an explicit carrier.
  Pass condition: Use Deliverable 7's version matrix, including unknown members and old entries/new protections. Where the effective baseline permits, compatible optional members, negotiated capabilities, or additive modes may extend an operation. Incompatible semantics need a separate operation/version while the old contract remains supported; obey stricter explicit requirements to preserve an in-use operation unchanged and add a new one. Internal signatures may change when semantics stay fixed and all callers move together. Derive support from valid durable facts, delayed/scheduled work, retained messages, replay, and recovery, not only live binaries. Test oldest-supported facts; define retirement/conversion/rejection without perpetual support or silent reinterpretation.

- **8.3 Bound actual migration risk.** Address locks, load, concurrent writes, interruption, restart, and stop conditions for existing data.
  Pass condition: Use risk-appropriate batches and progress for safe resumption; backfill cannot overwrite newer values. Reconcile contents and invariants, not only counts. Permit simpler empty initialization, authorized downtime, or explicit no-migration scope instead of mandatory online migration machinery.

- **8.4 Verify release health and real rollback compatibility.** Tie release judgment to actual artifacts, configuration, and business signals.
  Pass condition: Distinguish liveness, readiness, and correct outcomes; define stop-expansion conditions. Use Deliverable 7 for reachable mixed code/configuration/data/message versions; preserve committed work during switch/shutdown. Verify old code handles new facts/in-flight work, protect unsupported combinations, or disclose recovery limitations. Never erase new data to fabricate rollback. Deployment, monitoring windows, and safe release-target checks do not replace release acceptance's complete agreed regression in a suitable deployed verification environment.

- **8.5 Treat justified configuration transitions as behavior changes.** Define legal values, absence, both paths, and transition semantics for existing or necessary configuration and switches.
  Pass condition: Dynamic changes specify request snapshots, mixed-version safety, and in-flight work. Closing an entry does not leave forbidden effects running; switching back does not undo durable writes. Static startup validation may suffice; add no dynamic switching without need.

## Pass 9: Prove And Explain The Conclusions

- **9.1 Separate architecture explanation from implementation evidence.** Explain responsibilities, placement, boundaries, dependencies, benefits, and costs; retain control-flow, failure, transaction, and lock detail needed to judge feasibility.
  Pass condition: Diagrams, explanations, and affected contracts agree without forcing readers to reconstruct architecture from implementation. Identify authoritative sources and maintenance responsibility for affected contracts, schemas, examples, support windows, and recovery instructions. Specify change/release drift checks through existing validation or explicit comparison. Generated material is not automatically current; remove or version obsolete statements without duplicate specifications.

- **9.2 Prove architecture guards detect intended violations.** Automate only boundaries that need stability and check actual intended targets.
  Pass condition: Coverage is nonempty, complete for the target, and fresh after relocation or output changes. A well-formed violating sample reaches and fails the intended guard; a legal boundary sample passes. Unrelated parsing, typing, importing, compilation, or execution failure is not detection. Names and counts do not prove behavior; mature built-in rules need not each repeat their tests.

- **9.3 Match validation to authorization, execution, and artifact.** Record procedure, scope, actual phase, result, and freshness; separate design, implementation, testing, release, and availability evidence.
  Pass condition: Before regression/load/fault tests, identify authorized environment, data, effect destinations, initialization/cleanup effects, and resource budget. Isolate or explicitly authorize/bound writes, charges, notifications, deletion, and irreversible effects; deployment permission is not destructive-test permission. Keep unsafe/unauthorized checks pending. Disclose skipped work; restrict local evidence to its tested scope. Substitutes, inspection, and configuration presence do not establish unexecuted target-specific behavior or release. Plans/estimates are not execution; respect read-only limits.

- **9.4 Keep reusable instructions portable and complete.** Express prerequisites, actions, pass conditions, and exceptions without internal names, fixed locations, vendors, languages, frameworks, or machine assumptions.
  Pass condition: Another implementation approach can execute the instructions without hidden context or another instruction set. Generalization neither removes conditions nor strengthens obligations. Keep evidence references precise without making the procedure depend on a proprietary tool.

- **9.5 Challenge high-consequence guarantees in scope.** Identify representative wrong behavior and an expected outcome grounded independently of implementation.
  Pass condition: Validation rejects the violation for the intended semantic reason and accepts a valid control. Use suitable controlled alternatives, fault injection, or isolated mutation; unrelated setup failure is not detection. Distinguish equivalent, unreachable, and unexecuted counterexamples. Require no universal mutation score or tool, and mark design-only checks planned rather than proven.

## Self-check

- [ ] Reconcile applicable slots, grounded omissions, obligation rows, provisional verification, final dispositions, and counts. Separate report acceptance from pending adjudication/review and correction/release acceptance.
- [ ] Recheck authoritative clauses, authorization, frozen differences, approved behavior changes, owner choices, and bounded exceptions. Guidance and registration prove neither repository breach nor permission/closure.
- [ ] Challenge mechanism necessity and simpler equivalents; deepen only traced risks. Distinguish commit from caller observation, business success from independent audits, and delivery promises from assumed single effects.
- [ ] For applicable corrections, require ordered semantic red/green evidence, required independent review, scope acceptance, merged-revision gates/packaging, and safe deployed regression. Keep required unexecuted stages pending without inventing report-wide gates.
- [ ] Check reachable version pairs, unsupported-pair protection, supported older facts, rollback, and outcome reporting. State coverage units/denominators and distinguish failed, partial, unknown, and inapplicable rows from satisfied ones.
- [ ] Audit decisive evidence, discriminating counterexamples, execution safety, freshness, document drift, and portability. Claim no independent review, runtime proof, release, or completion without corresponding evidence.
