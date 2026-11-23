# Preserve structured assets

Keep the editor's disposition records and internal mappings — including which display names on an external publishing surface correspond to which frozen identifiers — only in the editing-session record (working notes and summary to the user), an external approval record, or an owner-named file outside the place where the document is stored; never put those internal records or mappings in the document or in any other file stored with it. Reader-facing mappings needed to understand or act on the document stay in the document under the document's own rules. Keep protected-baseline measurements, required authorizations, and protected-asset change reasons and bases in the editing-session record or external approval record, never in the edited document.

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

## Parallel copies

When the edited document also lives on an external publishing surface where others edit it:

1. Before editing, fetch the latest published revision and compare both sides against their common baseline. If the published revision or the common baseline is unavailable, hold the write-back and report the limitation.
2. Subject each external edit to the same checks as your own: **Meaning and authorization** and **Claim-type authority** in `SKILL.md`. Fold each adopted external edit into the edited document. Resolve each conflict by evidence and explicit informed user direction for the content in dispute, never by timestamp or by a fixed rule that one side always wins.
3. Keep on the target each external edit you do not adopt, hold your conflicting change under **Conflict and continuation** in `SKILL.md`, and record the edit with the reason in the editing-session record. Revert an external edit on write-back only with explicit informed user direction, and disclose each revert to the user.
4. Before writing back, confirm that the target revision has not changed since the comparison, and make each incremental write conditional on that revision or use an equivalent concurrency safeguard. On a revision mismatch, fetch the latest revision and repeat the comparison; if no safe write mechanism is available, hold the write-back and report the limitation. Preserve destination-native blocks such as callouts, quotations, mentions, embeds, and icons under **Accounting scope**.
