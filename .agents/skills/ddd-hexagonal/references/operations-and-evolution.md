# Operations and Evolution

Passes 7 and 8 of the procedure in SKILL.md, which holds the fidelity rules (F1-F12). Deliverable slots 6 and 7, which 8.2 and 8.4 cite, are in [reporting-and-proof.md](reporting-and-proof.md#deliverable-slots).

## Pass 7: Test Reachable Operational Failure Modes

- **7.1 Establish affected workload, capacity, and durable-growth bounds.** Define authorized data size, concurrency/arrival rate, amplification, resource limits, and operating horizon.
  Pass condition: Consider relevant tail latency, memory, connections, queues, background contention, skew, and cold caches. For accumulating durable state, state growth assumptions, retention authority, and headroom for base data, indexes, history, retained messages, and failed work. Include recovery/backfill/compaction temporary space and reduced throughput; define detection and a safe response before exhaustion or disclose the missing bound. Short load tests and bounded request memory alone do not prove sustainable storage. Keep conditions with claims; reuse valid evidence for unaffected bounded paths instead of load-testing every edit or adding unjustified archival/distributed mechanisms.

- **7.2 Bound overload and retry amplification.** Combine attempts across layers and constrain concurrency, queues, and waiting by real resources.
  Pass condition: Define rejection, isolation, or authorized degradation and assess synchronized retries where relevant. Count work continuing after timeout; propagate supported cancellation without claiming unsupported termination. Prompt failure without retry can suffice; limiters and circuit breakers are not mandatory.

- **7.3 Make consequential results and failures diagnosable.** Select business success, rejection, technical failure, latency, and relevant saturation or backlog signals.
  Pass condition: Retain needed cross-boundary correlation, bounded dimensions, and protected sensitive content. Where timely detection is required, specify detection condition, telemetry delay, detection delay, responder, and response procedure. Check a representative actionable failure signal and missing or stale telemetry; unknown thresholds remain gaps. Reuse adequate monitoring or manual checks without requiring a new platform or per-function instrumentation.

- **7.4 Define consistency for existing caches.** Specify complete cache identity, allowed staleness, invalidation, and concurrent refresh.
  Pass condition: Include every answer-changing dimension and distinguish negative answers, dependency failures, and expiry. Cache publication cannot advertise a rolled-back change as committed; stale refresh cannot overwrite newer facts. Expiry alone proves no strong freshness. Keep permission-sensitive facts within authorized use; build no cache for this check.

- **7.5 Assign technical trust boundaries for reachable dangerous operations.** Trace untrusted influence on queries, network targets, files, processes, and deserialized types.
  Pass condition: Separate values from executable structure and constrain targets under actual execution semantics, not surface spelling. Login and business validation do not replace technical controls. Do not impose one sanitizer on every field or audit unrelated systems.

- **7.6 Protect actual sensitive flows and promised deletion.** Identify allowed readers and transmission, storage, cache, sample, backup, and deletion boundaries under established classification.
  Pass condition: Debugging cannot silently disable required peer authentication or communication protection; long-lived secrets remain replaceable. Where deletion or expiry is promised, define authoritative deletion state and permitted retention across projections, caches, diagnostic copies, replay sources, and recovery material. Delayed work, replay, or restoration cannot reintroduce forbidden data or effects. If recovery material cannot be rewritten immediately, bound retention/access and reapply deletions before serving restored state. Preserve independently required retention, not universal immediate erasure. Reuse validated protection; invent neither cryptography nor identical encryption/secret infrastructure for all data.

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
  Pass condition: Distinguish liveness, readiness, and correct outcomes; define stop-expansion conditions. Use Deliverable 7 for reachable mixed code/configuration/data/message versions; preserve committed work during switch/shutdown. Verify old code handles new facts/in-flight work, protect unsupported combinations, or disclose recovery limitations. Never erase new data to fabricate rollback. Deployment, monitoring windows, and safe release-target checks do not replace the release acceptance in Deliverable 6.

- **8.5 Treat justified configuration transitions as behavior changes.** Define legal values, absence, both paths, and transition semantics for existing or necessary configuration and switches.
  Pass condition: Dynamic changes specify request snapshots, mixed-version safety, and in-flight work. Closing an entry does not leave forbidden effects running; switching back does not undo durable writes. Static startup validation may suffice; add no dynamic switching without need.
