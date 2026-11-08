# Design and Structure

The standard vocabulary, Pass 1, Passes 2 and 3, and clauses 9.1 and 9.2 of the procedure in SKILL.md, which holds the fidelity rules (F1-F12), Hold The Default Standard, and the Standing Rules. The Standing Rules complete the pass conditions of 1.1, 1.2, 1.4, 1.5, and 1.6. Pass 6, which 3.6 cites, is in [state-and-concurrency.md](state-and-concurrency.md).

## Standard Vocabulary

Use the standard vocabulary:

- **Strategic design.** A *bounded context* is the boundary within which one *ubiquitous language* and one model hold. A *context map* names each relationship between contexts (for example customer-supplier, conformist, shared kernel, open host service with a published language, anti-corruption layer). An *anti-corruption layer* translates a foreign model so it never enters the local one. A *subdomain* is a part of the business problem, classified as a *core subdomain* (differentiating), a *supporting subdomain*, or a *generic subdomain*; concentrate modeling depth on core subdomains, and for a generic subdomain prefer conforming to or adopting an existing solution when no local invariant requires a model.
- **Tactical design.** An *aggregate* is a consistency boundary changed only through its *root*. An *entity* has identity and lifecycle; a *value object* is immutable, compared by value, and self-validating. A *domain service* holds pure domain logic that belongs to no single aggregate. A *domain event* records, in the ubiquitous language and past tense, a fact others react to. A *repository* is the outbound port through which an aggregate is loaded and saved whole.
- **Hexagonal roles.** An *application service* realizes *use cases*. An *inbound (driving) port* is a use-case contract the application exposes; an *outbound (driven) port* is a capability contract the core declares and consumes. An *adapter* translates between a port and a technology: driving adapters call inbound ports, driven adapters implement outbound ports. The *composition root* constructs dependencies and selects concrete implementations across architectural boundaries; domain types and adapter-local collaborators remain with their owners.

## Pass 1: Establish The Mandate And Evidence

- **1.1 Establish the effective baseline.** Identify effective requirements, object versions, superseded decisions, observed state, approved target, assumptions, and unknowns.
  Pass condition: Each conformance conclusion cites a specific authoritative clause, effective status, object, and evidence. Verify replacement relationships, not dates or completion labels. Record missing source categories and search scope.

- **1.2 Verify decisive facts independently.** Treat comments and prior verdicts as leads, then inspect the evidence that decides each claim.
  Pass condition: Confirmed, unresolved, and rejected claims each have inspectable grounds. Keep evidence verification distinct from independent review organization.

- **1.3 Verify promised coverage.** Trace separately decidable obligations through affected decisions, entries, consumers, persisted forms, effects, and evidence.
  Pass condition: Cover promised full scope or focused impact closure and record enumeration/tracing methods. Each row has source, applicability, acceptance condition, and evidence status. Fix population/counting rules before reporting coverage: distinguish satisfied, failed, partial, unknown, and justified inapplicable rows. Only fully evidenced satisfied rows count as covered; include failed/partial/unknown applicable rows in the denominator and exclude only grounded inapplicable rows. Missing, unexecuted, unexamined, or unverifiable evidence is not a pass. Item status may suffice; favorable totals cannot close a failed high-consequence obligation.

- **1.4 Protect authorized scope and behavior.** List permitted changes and the protected objects (code, contracts, configuration, and other objects that must not change) before proposing repairs.
  Pass condition: Every proposed difference serves the authorized objective. Preserve returns, rejection, error identities, failure order, commit effects, and side effects except for explicit approved changes. Where zero changes are required outside scope, require a baseline diff proving zero, not merely equivalent behavior.

- **1.5 Separate correction from business choice.** Apply established requirements to factual errors within granted authority; identify unspecified policy and ownership choices for the responsible decision maker.
  Pass condition: Each unresolved choice states its options and blocked decision.

- **1.6 Bound exceptions and transitions.** Record approval grounds, precise location and conditions, existing protection, and review or expiry trigger.
  Pass condition: Describe a transition's deviation and convergence direction instead of claiming full compliance.

## Pass 2: Choose The Faithful, Justified Design

- **2.1 Compare decision-relevant alternatives from the target form.** State which goals or consequences make a decision consequential; compare no change, the simplest faithful viable change, and credible alternatives that could change the choice, including ones neither the incumbent design nor any reviewer proposed. Derive the target from business facts, the default standard, and best practice independently of implementation history.
  Pass condition: Present each candidate in its strongest feasible form under common constraints, and give principle- or constraint-based exclusion reasons (Hold The Default Standard); a changeable local rule that blocks the faithful form does not exclude it: recommend the faithful form with a proposed rule change, and until the change is approved, design within the effective rule and report the deviation (1.1, 1.6). Record premises, deciding scenarios, benefits, costs, sensitivity, evidence gaps and affected conclusions, direction, and reconsideration triggers in a shared authoritative record. Do not claim an unbounded search or global optimum. Record cost as a secondary note, and distinguish research acceptance from implementation authorization. Resolve in-scope architecture choices against the goal rather than leaving them pending or delivering a knowingly diluted form; route genuine business, permission, external-ownership, scope, or exception choices to owners. Use a compact record for a small decision.

- **2.2 Justify adding and removing mechanisms by necessity, then cost.** Identify the current requirement, invariant, boundary, fidelity rule applied to a present use case, consumer, or boundary, or reachable failure, consequence without protection, existing safeguards, simpler equivalents, and development, verification, operational, and maintenance costs.
  Pass condition: Admit a mechanism only for a recorded necessity, and admit a correction when it closes a confirmed gap or moves the design toward the target form. Prefer no new framework, layer, or general mechanism beyond necessary responsibilities and boundaries; justify any indispensable addition and obtain authorization if it changes approved scope or design. When available effort cannot reach the target at once, phase it as a bounded transition (1.6) without silently closing a confirmed gap. Remove redundant defensive state, duplicate checks/tests/gates without unique evidence, and arbitrary fragmentation of coherent work; preserve unique behavioral, concurrency, architecture, and real-storage evidence. Apply the deeper passes by reachable impact, not change size or hypothetical reuse.

- **2.3 Express quality goals as testable scenarios.** State stimulus source, stimulus, operating conditions, affected element, response, and response measure for goals that drive the decision.
  Pass condition: Identify sensitive parameters, conflicting goals, and residual risks. Name unknown thresholds and the decisions they block instead of inventing numbers. One decisive scenario can suffice; do not mandate a workshop or scoring system.

- **2.4 Classify subdomains and derive bounded contexts from ubiquitous language and ownership.** Assign fact and rule owners, interactions, shared semantics, transaction and change responsibility, and non-goals; record the context map (F1).
  Pass condition: Actual interactions identify callers, owners, relationship types, and translation points, and the chosen context-map relationship. Use an anti-corruption layer where external semantics would corrupt the local model, not a wrapper for every call. Enforce source boundaries independently; they do not prove isolation from shared-resource failures. Shared deployment, storage, or source organization does not invalidate a business boundary; relationships and views do not automatically create one.

- **2.5 Derive aggregate boundaries from invariants and lifecycle.** List states that must hold, freeze, or change together, forbidden combinations, and atomic actions; classify members as entities or value objects (F4).
  Pass condition: Explain each boundary and use an interleaving to justify a split's intermediate states and coordination cost. Do not infer business identity from a row. Where no invariant or lifecycle needs an aggregate, apply the omission rule in Hold The Default Standard instead of adding aggregate machinery. Reassess when independent identity, permissions, or lifecycle emerges.

## Pass 3: Assign Responsibilities And Dependencies

- **3.1 Distinguish dependencies, calls, and assembly.** Identify who declares, implements, calls, and selects each contract.
  Pass condition: Actual dependencies and cycles match the effective responsibility and permission matrix. Directory placement, build visibility, or successful loading is not permission. Apply the F2 matrix unless the effective baseline records another, and report any other matrix as a deviation (1.6).

- **3.2 Separate judgment from obtaining facts and coordinating work.** Give rules an explicit responsibility and fact inputs; assign authorization orchestration, transactions, and protocol conversion separately.
  Pass condition: Business judgment lives in aggregates, value objects, or pure domain services and does not hide storage, remote, or assembly access; application services orchestrate (F6); entries and adapters do not duplicate invariants. Do not turn filtering, pagination, or projection into a mandatory domain service.

- **3.3 Place capability contracts with consumers.** Define explicit inbound operations per use case (F5) and outbound ports by capability the core consumes (F7); keep technical collaboration with its adapter owner.
  Pass condition: Each port has a real consumer and required semantics, not leaked storage or transport detail. Adapter-internal work does not detour through a core port. Ports may have one implementation (F10); one implementation alone justifies no other interface.

- **3.4 Make assembly explicit and safe.** Select required roles at the composition root (F9) and isolate real capabilities from local substitutes.
  Pass condition: Required selection is unique, mutually exclusive, and exhaustive. Missing security-critical implementation or configuration fails explicitly; unknown conditions cannot select a permissive substitute. Permit isolated development substitutes and optional telemetry without universal startup failure.

- **3.5 Match reads to use cases.** Select needed read projections or immutable facts rather than loading mutable write aggregates or using write-side persistence.
  Pass condition: Queries neither save business state nor trigger lifecycle changes; jointly judged facts use the required consistent snapshot. Recording telemetry is not a business write. Load necessary facts, including immutable snapshots for full judgment, through read capabilities distinct from the write-side repository (F7) without mandating separate read-model types, databases, event-driven projections, or event sourcing.

- **3.6 Keep one authoritative rule and lifecycle definition.** Assign authority for transitions, idempotent success, rejection, error identities, and detection responsibility. A domain event expresses an actual past business fact with an owner, payload, commit meaning, and real consumer, not generic logging.
  Pass condition: Reachable entries use authoritative semantics, not independent copies. Protect authorized mirrors and projections against drift without requiring every representation to share a type or identical projection. Separate domain events, integration representations, business operation records, and telemetry; apply Pass 6 where durability/delivery is required. Introduce no event machinery without a domain or consumer need.

## Pass 9 (9.1-9.2): Prove And Explain The Conclusions

- **9.1 Separate architecture explanation from implementation evidence.** Explain DDD/hexagonal principles, responsibilities, placement, boundaries, dependencies, justified omissions, benefits, and secondary implementation costs separately from implementation mechanics; retain control-flow, failure, transaction, and lock detail needed to judge feasibility.
  Pass condition: Diagrams, explanations, and affected contracts agree without forcing readers to reconstruct architecture from implementation. Identify authoritative sources and maintenance responsibility for affected contracts, schemas, examples, support windows, and recovery instructions. Specify change/release drift checks through existing validation or explicit comparison. Generated material is not automatically current; remove or version obsolete statements without duplicate specifications.

- **9.2 Prove architecture guards detect intended violations.** Apply F12's executable guards or recorded checks to affected stable source-level fidelity rules; automate other boundaries only where stability is needed and check actual intended targets.
  Pass condition: Coverage is nonempty, complete for the target, and fresh after relocation or output changes. A well-formed violating sample reaches and fails the intended check; a legal boundary sample passes. Include representative counterexamples such as a driving adapter bypassing its inbound port to invoke a concrete handler, an inbound result embedding an outbound type, a domain dependency on storage/framework code, a driven adapter implementing an inbound use case, and a query use case loading a write aggregate through its repository. Unrelated parsing, typing, importing, compilation, or execution failure is not detection. Names and counts do not prove behavior; mature built-in rules need not each repeat their tests.
