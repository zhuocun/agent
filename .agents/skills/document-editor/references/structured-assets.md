# Preserve structured assets

Keep content and asset mappings only in the editing-session record (working notes and summary to the user), an external approval record, or an owner-named file outside the place where the document is stored; never put a mapping in the document or in any other file stored with it. Keep protected-baseline measurements, required authorizations, and protected-asset change reasons and bases in the editing-session record or external approval record, never in the edited document.

## Accounting scope

Set the accounting scope before editing. For a loss-sensitive restructure, split, or compression, inventory the complete affected content and load-bearing assets: decisions, open questions and blockers, conditional branch tables, tradeoff matrices, invariants, non-goals, risks, rollout batches, diagrams, exact contracts, error catalogs, and critical checklists, as applicable. For another edit that touches a load-bearing or protected asset, inventory that asset and its dependencies. A bounded local edit that leaves these assets, protected records, and their relationships untouched needs only brief notes identifying the affected passages and checked dependencies, rather than an outline and dispositions for untouched content. If scope or preservation is uncertain, use the complete affected inventory and mapping; expand it before proceeding when the edit grows.

Preserve existing diagrams, images, videos, code blocks, callouts, evidence citations, and other native blocks unless the user requests a change or a source-backed edit requires one.

## Dispositions and protected baselines

1. Give every inventoried passage or asset a disposition: preserved in place, moved to a named destination, merged into a named authoritative item, or intentionally removed with a reason and the required authorization. Do not use compression as an unreported deletion path.
2. Apply rule 1 of **Registries vs decision narrative** in `references/decisions-and-evidence.md`, relocation is not deletion, to every inventoried asset, not only registry entries; read that file in full before the first relocation, and again after a context compaction before the next one. Treat conversion to a table or movement to an appendix as relocation under that rule.
3. Treat exact schemas, interface signatures, identifiers, error definitions, and other contract artifacts as deliverables in their own right. Preserve their completeness and exactness even when surrounding explanation is condensed.
4. Treat an asset's item count or byte identity as a protected baseline only when the owner or delivery format defines it. For a controlled baseline change, record the pre-change and post-change values and any required authorization; never change the baseline silently.
5. When byte-for-byte identity is required, use the configured checksum or comparison method. Do not modify a protected diagram or native asset without authorization; after an authorized change, record its reason and basis and apply the required rendering or behavior checks.
6. Resolve protected-content conflicts under **Conflict and continuation** in `SKILL.md`. Apply **Document policies** and **Governance applicability** within the resolved scope.
