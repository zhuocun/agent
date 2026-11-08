# Review and evidence

Read this file in full before dispatching the first reviewer or verifier and before the first reuse of raw evidence in a session, and again after a compaction before the next of either. **Reviewer** and **Verification** in `SKILL.md` say when a reviewer runs, how its verdict is handled and how verification is planned.

- [Reviewer handoff](#reviewer-handoff)
- [Verifiers](#verifiers)
- [Evidence reuse](#evidence-reuse)

## Reviewer handoff

**Reviewer input** — the handoff is exactly this:

- the exact brief the worker received
- the worker's final artifact (diff for code; write-up for research)
- the surrounding files needed for context
- the applicable verification plan and raw-evidence references, with the provenance and scope **Evidence reuse** requires, plus failed or uncovered checks

The reviewer does not see the worker's intermediate reasoning, scratch work, or chat — it judges the artifact, not the process. Beyond the handoff in **Reviewer handoff**, the reviewer may pull whatever it needs to check the work — primary sources, the wider repo, a test run.

**Reviewer output** — structured:

- **verdict**: `pass` / `revise` / `redo`
- **issues**: concrete problems with `file:line` references
- **suggested fixes**: precise corrections, not paraphrased rewordings
- **confidence**: low / medium / high, called out explicitly on judgment calls

The reviewer must **ground its verdict against external truth** wherever that signal exists: inspect the artifact and applicable raw evidence under **Verification** in `SKILL.md` and **Evidence reuse**, re-check research claims against primary sources, identify risks the worker missed, and perform the checks its review requires. It neither edits the artifact or any shared deliverable nor authors the fix. Mark a verdict reached without such grounding low confidence.

## Verifiers

A **verifier** is the same gate in narrower form: a subagent dispatched to confirm one specific claim or behavior that a worker, artifact or reviewer asserted — run the test suite, reproduce a bug, re-check a cited source — rather than judge a whole artifact. Verifiers follow the reviewer's rules: independent, grounded in external truth, never the author of the fix.

## Evidence reuse

Reuse raw evidence only after checking its producer and provenance, input identity and scope, method and effective configuration, environment and dependencies, actual coverage, and freshness for the claim. Relevant inputs include code, data, fixtures, toolchains, services and source versions. Infer coverage from execution definitions and results, never check names. Determine freshness from relevant input changes and any time sensitivity. Required independent clean reproduction must actually run with the specified independence; worker logs or a different reviewer's opinion cannot replace it. Checks of distinct properties, including negative, mutation and equivalence checks, remain separate obligations unless their coverage is demonstrated.
