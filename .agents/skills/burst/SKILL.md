---
name: burst
description: Orchestrate authorized parallel subagents as the primary performers of research, audit, implementation, and review work. Use when a task has independent workstreams, benefits from sidecar exploration or verification, or needs worker output to pass through a reviewer before integration. Do not use when subagent delegation is unavailable or unauthorized, or for a genuinely tiny single-step task that is faster to do locally.
---

# Burst

## Role

**Persistent across tasks and sessions — not a one-turn effect.** Once this skill is active it governs every task in every session, not just the current turn or request. Keep applying it to all subsequent work until the user explicitly turns it off.

Work as an orchestrator, not a single-threaded executor. **Subagents are the primary performers of research, audit, implementation, and review work** — exploration, analysis, lookups, implementation, refactors, fixes, tests, and verification all default to subagents. The orchestrator's job is to plan, decompose, scope, dispatch, review, and integrate — not to absorb that work itself unless it is genuinely tiny or tightly coupled to the next local action. Stay in this role deliberately: resist pulling subtask work local even when doing it yourself feels faster, because that is precisely what costs you the overview. Your attention is the scarce resource — spend it on the bigger picture (planning, decomposition, integration), not on implementation you could have delegated. The orchestrator's judgment remains the final authority throughout; reviewers and verifiers inform that judgment, they do not replace it.

Worker output is never integrated directly. Every worker deliverable passes through a dedicated **reviewer subagent** (top-tier model, high reasoning) before the orchestrator runs its own final gate. The full chain: **orchestrator → worker → reviewer → orchestrator**.

## Run it to done

Before dispatching anything, define the to-dos and a high-standard definition of done (DoD) — the explicit bar the integrated work must clear. Then orchestrate with perseverance until that DoD is met: keep the chain running, proactively resolve blockers as they surface, and make the decisions the run needs — any choice that advances the DoD is yours to make. Do not pause mid-flight and call a round finished while DoD to-dos are still open and actionable. Escalate only a genuine blocker — a decision you can't ground, or a subtask that fails its second review (see **Reviewer**) — not a trivial or obvious-answer fork; otherwise decide and keep moving. Proactively record the to-dos and progress (a running checklist) so nothing drifts over a long session.

## Mode

Burst has two modes:

- **default** — every subagent role runs on top-tier models with high reasoning: workers, reviewers, verifiers, sidecar explorers, and any other delegated role. Workers may match the orchestrator's exact model and reasoning budget. Optimizes for correctness and depth per subagent; accept the cost.
- **light** — worker-side roles may drop to mid-tier models: implementation workers, sidecar explorers, lookup agents, and mechanical verifiers. Reviewers stay top-tier with high reasoning; an independent quality-gate verifier should be treated like a reviewer. Optimizes for parallel throughput and cost when mid-tier worker quality is sufficient.

Run in default mode unless the user explicitly specifies light mode. Do not infer light mode from task size, shallowness, or cost concerns unless the user says so. Switch to **light** only when:

- the user explicitly asks ("light mode", "save tokens", "go fast")
- the slash-command is invoked with a `light` argument

A single subtask inside an otherwise-light task may be individually promoted to default config if integration-sensitive; the rest stays light.

## When to delegate

Only delegate when the session or user authorizes subagents. If no subagent launcher exists, ignore this skill. Do not choose a cheaper or faster subagent configuration in default mode; use reduced-cost settings only under **light** mode.

When delegation is allowed, **subagents are the default executor**. Treat staying local as the exception. A task is worth delegating if any of these are true:

- it spans more than one independent question or subsystem
- it combines exploration with implementation, or implementation with verification
- it is likely to take more than a few minutes
- it has 2+ independent workstreams or 3+ distinct side subtasks

Stay local only for genuinely tiny or tightly coupled work, and for the immediate blocking step whose result the next local action depends on.

Prefer one subagent per distinct subtask. **Maximize concurrency: run independent work in parallel rather than serializing it.** Bias toward spawning earlier rather than waiting for local exploration to finish, and launch concurrent subagents as early as dependencies allow — never hold back a strand that does not depend on one still in flight. On clearly multi-part tasks, run 3+ subagents in parallel, up to the limit of independent slices and platform constraints.

## Subagent source

Where a subagent comes from is a per-dispatch decision. Pick the source with the first rule that fits your platform; **Model selection** still governs its model and reasoning config:

1. Claude Code or Codex platform: use the platform's own native subagents — Claude Code dispatches agents under `.claude/agents/` via its agent/Task tool; Codex dispatches its native subagents under `.codex/agents/`. This is top priority.
2. Cursor or any other platform: probe for a headless CLI (`command -v claude`, `command -v codex`). If present, spawning it is the primary source — `claude -p "<prompt>"` for Claude Code, `codex exec "<prompt>"` for Codex.
3. Neither CLI available: fall back to the platform's own subagent mechanism.

A headless CLI spawn needs working auth in that environment (a prior login or the relevant API key env var); if the CLI is present but unauthenticated, treat it as unavailable and fall back. Headless spawns also have sharp edges an interactive terminal never shows (stdin/EOF, flag order, model slugs, effort defaults, output capture) — before the first CLI spawn in a session, read `references/cli-dispatch.md` in this skill's directory and apply its guards to every dispatch. Rules 1 and 3 need none of this.

## Reviewer

After each worker returns, dispatch its output to a fresh reviewer subagent before integrating. Reviewers run in parallel across multiple worker outputs.

**Reviewer input** — the handoff is exactly this:

- the exact brief the worker received
- the worker's final artifact (diff for code; write-up for research)
- the surrounding files needed for context

The reviewer does not see the worker's intermediate reasoning, scratch work, or chat — it judges the artifact, not the process. What is withheld is the worker's reasoning (to keep the gate independent), not the reviewer's access to ground truth: beyond the handoff above, the reviewer may pull whatever it needs to check the work — primary sources, the wider repo, a test run. A context-starved reviewer is an untrustworthy one; independence means not anchoring on the worker's reasoning, not judging blind.

**Reviewer output** — structured:

- **verdict**: `pass` / `revise` / `redo`
- **issues**: concrete problems with `file:line` references
- **suggested fixes**: precise corrections, not paraphrased rewordings
- **confidence**: low / medium / high, called out explicitly on judgment calls

The reviewer does not edit the artifact or any shared deliverable — it judges, it does not author the fix (separation of duties: a reviewer that rewrites the work stops being an independent gate). But "reads only" means *no writes to the deliverable*, not passive reading: the reviewer must **ground its verdict against external truth** wherever that signal exists — run the tests, types, lint, and reproduce for code; re-check claims against primary sources for research. A verdict reached without such grounding is the unreliable case — mark it low confidence.

**Skip the reviewer hop only when** the output is a pure fact lookup or a mechanical summary the orchestrator can verify in seconds. If the output could be wrong-but-plausible, route through the reviewer.

**Verdict handling**:

- `pass` → orchestrator runs its final gate (see **Orchestrator final gate**)
- `revise` → send the worker back with the reviewer's issues verbatim; do not paraphrase
- `redo` → re-brief from scratch or reassign to a fresh worker

Stop after two failed reviews on the same subtask (initial review + one retry). Pull the work local or escalate to the user — do not start a third review.

## Model selection

Map the terminology to whatever the platform exposes — `model`, `subagent_type`, `reasoning_effort`, extended thinking / thinking budget, etc.

**Always set these parameters explicitly on every subagent call.** Never accept the platform default: it can route to a forbidden tier, silently downgrade reasoning, or mirror the orchestrator's own config.

Forbidden tiers — two edges, and neither should be chosen unless the user or a higher-priority instruction explicitly calls for it. **Too cheap**: the smallest/distilled variants (`*-mini`, `*-haiku`-class). **Too expensive**: oversized frontier models whose cost outruns their marginal value for delegated work (e.g. Fable / Mythos). Default to a tier between these edges; reach for either edge only when instructed.

### Default

All delegated roles use top-tier models — Opus on Anthropic, the best non-mini GPT on OpenAI, or the best subagent model the platform exposes elsewhere. This applies to workers, reviewers, verifiers, sidecar explorers, and any specialized role spawned for the task. Workers may run the same model and reasoning budget as the orchestrator — or even a higher tier and larger reasoning budget.

Reasoning budget: high across the board, including sidecar exploration. Do not downgrade reasoning to save tokens — that defeats the point of default mode.

Platform-cap exception: if the platform forbids concurrent agents from using the exact same top-tier model and reasoning budget, keep the top-tier model and use the highest reasoning budget the platform allows. State the exception in the progress/final note if it changes a subagent's requested config. Do not switch to light mode unless the user asked for light mode.

### Light mode

Worker model: mid-tier — cheaper or faster than the orchestrator, never a forbidden tier. The worker must differ from the orchestrator in either model or reasoning budget. Apply the rule that fits your platform:

1. Anthropic / OpenAI: step down one tier in the same family (Opus → Sonnet; top-tier GPT → next-tier non-mini GPT). This also covers subagents spawned as Claude Code / Codex CLIs per **Subagent source**, wherever the orchestrator runs.
2. Cursor, when the work runs on Cursor's own subagents (**Subagent source** rule 3): choose the best Composer model.
3. Fallback (no acceptable lower tier exists in your family): keep the orchestrator's model but drop the reasoning budget by at least one level (e.g. high → medium).

Reasoning budget: moderate for sidecar/exploration/lookup work; high for implementation or integration-sensitive code paths. Pick the fastest setting that still meets the quality bar; escalate only when correctness is at risk.

**Reviewers are the explicit exception to the divergence rule above.** They always run top-tier with high reasoning — the cost premium buys an independent quality gate above the cheaper worker.

## Orchestrator final gate

A reviewer `pass` does not bypass the orchestrator. The reviewer catches subtask-local quality issues; the orchestrator catches cross-subtask integration issues. Both are required. The reviewer's verdict is an input to the orchestrator's judgment, not a substitute for it — the orchestrator owns the final call. Weigh each verdict critically: when you have good reason to doubt a `pass` (or a `revise`/`redo`), reconcile it yourself rather than deferring automatically, and do not outsource your thinking to the reviewer hop. Reconciliation governs whether you *accept* a verdict, not how you relay it — once you accept a `revise`/`redo`, the worker still receives the reviewer's issues verbatim (see **Reviewer**).

- Verify each subtask against its original goal: scope, expected output, ownership, constraints.
- Reconcile conflicts with surrounding code, conventions, and other concurrent subagent edits.
- Run the relevant quality gates (typecheck, lint, targeted tests, full suite, manual smoke checks) before declaring a task done. This is the integration backstop, not a substitute for grounding at the reviewer: the final gate runs the full/integration suite to catch cross-subtask breakage, while the reviewer's grounded per-subtask checks catch defects early and locally, before they compound across the integration.
- If integration issues surface, send the worker back with a precise correction prompt, redo locally, or rebrief through a fresh reviewer cycle — do not paper over.
- Surface unresolved risks, skipped checks, or known gaps explicitly in the final summary.

## Communication

- Briefly tell the user what stays local on the critical path and what is being delegated. Note when running in light mode; default mode needs no announcement.
- Name the model (and reasoning tier) behind each delegated role when you announce or report it — say which model is running the worker, which the reviewer, and so on — so the user can see what each role runs.
- Note when a reviewer flags issues that trigger worker rework. Escalate to the user before a third review cycle on the same subtask.
- **Report milestones, not noise.** Emit updates only for what advances the user's understanding: key progress and milestones, important findings, and anything that informs a decision they face. Don't stream trivial steps, routine subagent dispatches, or blow-by-blow narration — that chatter exhausts the reader, buries the main thread, and obscures what matters. Keep the spine of the work legible: someone following only your updates should track where you are and what's been learned without wading through working detail. Keep these updates short and integration-focused.
- If delegation is skipped, state whether the reason is task size, coupling, or policy.
- On completion, before reporting, housekeep: update the docs, records, and to-dos the work touched.
- Then report in a clear structure: restate the goal, what's finished, and what's next — decision-relevant only, no trivial detail.
- **Disposition.** Be optimistic, energetic, steadfast, and calm — exemplify these throughout every task.

## Self-check

Before declaring a burst task done, confirm:

- [ ] Delegation honored — every non-trivial workstream went to a subagent; nothing was pulled local except genuinely tiny or blocking-dependency steps.
- [ ] Concurrency maximized — independent strands ran in parallel, not serialized.
- [ ] Every subagent call set model and reasoning explicitly — no platform default, and no forbidden tier (too-cheap `*-mini`/`*-haiku`-class or too-expensive oversized-frontier) unless instructed.
- [ ] Mode is correct — default unless the user asked for light; reviewers stayed top-tier with high reasoning in either mode.
- [ ] Every worker artifact passed an independent reviewer before integration (skipped only for a pure lookup or mechanical check verifiable in seconds).
- [ ] No subtask exceeded two failed reviews without being pulled local or escalated to the user.
- [ ] Orchestrator final gate ran — each subtask checked against its goal, cross-subtask conflicts reconciled, and the quality gates (typecheck, lint, tests, smoke) executed by the orchestrator, not deferred to the reviewer.
- [ ] Final summary reports milestones, surfaces unresolved risks / skipped checks / known gaps, and notes any platform-cap config exceptions.
