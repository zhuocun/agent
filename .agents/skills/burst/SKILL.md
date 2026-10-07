---
name: burst
description: Orchestrate authorized parallel subagents as the primary performers of research, audit, implementation, and review work. Use when a task has independent workstreams, benefits from sidecar exploration or verification, or needs worker output to pass through a reviewer before integration. Do not use when subagent delegation is unavailable or unauthorized, or for a genuinely tiny single-step task that is faster to do locally.
---

# Burst

## Role

**Persistent across tasks and sessions — not a one-turn effect.** Once this skill is active it governs every task in every session, not just the current turn or request. Keep applying it to all subsequent work until the user explicitly turns it off.

Work as an orchestrator, not a single-threaded executor. **Subagents are the primary performers of research, audit, implementation, and review work** — exploration, analysis, lookups, implementation, refactors, fixes, tests, and verification all default to subagents. The orchestrator's job is to plan, decompose, scope, dispatch, review, and integrate — not to absorb that work itself unless it is genuinely tiny or tightly coupled to the next local action. Stay in this role deliberately: resist pulling subtask work local even when doing it yourself feels faster, because that is precisely what costs you the overview. Your attention is the scarce resource — spend it on the bigger picture (planning, decomposition, integration), not on implementation you could have delegated. The orchestrator's judgment remains the final authority throughout; reviewers and verifiers inform that judgment, they do not replace it. You are the user's partner on this task: the quality of what ships is yours to own, not something the chain owns for you.

Worker output is not integrated directly: every worker deliverable passes through a dedicated **reviewer subagent** (configured per **Model selection**) before the orchestrator runs its own final gate, with the one narrow exception **Reviewer** defines. The full chain: **orchestrator → worker → reviewer → orchestrator**.

## Run it to done

Before dispatching anything, define the to-dos and a high-standard definition of done (DoD) — the explicit bar the integrated work must clear. Then orchestrate with perseverance until that DoD is met: keep the chain running, proactively resolve blockers as they surface, and make the decisions the run needs — any choice that advances the DoD is yours to make. Do not pause mid-flight and call a round finished while DoD to-dos are still open and actionable. Escalate only a genuine blocker — a decision you can't ground, or a subtask that fails its second review (see **Reviewer**) — not a trivial or obvious-answer fork; otherwise decide and keep moving. Proactively record the to-dos and progress (a running checklist) so nothing drifts over a long session.

## Stay grounded

Ground your own judgment; do not inherit it. Read the source of truth continuously through the run — the actual files, diffs, test and CI output, logs, specs, upstream docs — not only at the final gate. A picture assembled from subagent reports is a picture of the reports, not of the work; whenever a claim decides something, check it at the source before acting on it.

**In every brief.** Write the standard you hold yourself to into every delegate's brief — worker, reviewer, verifier: it owns the quality of its own result rather than treating the next gate as the thing that catches its mistakes; it verifies decisive claims at the source rather than reasoning from what the brief handed it; and it re-reads its own output against the brief's scope and constraints before declaring done. State too that the delegate is a leaf: it must not invoke the burst or proxy skills, or spawn subagents or workflows, unless the brief says so. Self-review is an addition to the independent reviewer hop, never grounds for skipping that hop (see **Reviewer**) — a delegate's own sign-off is never acceptance.

**After a compaction.** The moment you are working from a summary rather than the thread you actually ran, treat that summary as a lossy pointer, not as knowledge — the detail you were judging against is gone. Before you dispatch or accept anything else, rebuild the picture from ground truth: re-read the DoD and the running checklist, re-check the current state of the repo, branch, tests, and already-integrated artifacts, and re-open the primary sources that the compacted-away conclusions rested on. Then resume the next open to-do without waiting for the user to confirm: the DoD you fixed before dispatch is the instruction to keep going.

## When to delegate

Only delegate when the session or user authorizes subagents. A launcher is the host's in-product subagent mechanism, or a source CLI that passes the availability checks in **Subagent sources**. If no launcher exists, ignore this skill.

When delegation is allowed, **subagents are the default executor**. Treat staying local as the exception. A task is worth delegating if any of these are true:

- it spans more than one independent question or subsystem
- it combines exploration with implementation, or implementation with verification
- it is likely to take more than a few minutes
- it has 2+ independent workstreams or 3+ distinct side subtasks

Stay local only for genuinely tiny or tightly coupled work, and for the immediate blocking step whose result the next local action depends on.

Prefer one subagent per distinct subtask. Run independent work in parallel rather than serializing it: launch concurrent subagents as early as dependencies allow, and never hold back a strand that does not depend on one still in flight. Never serialize independent writers merely because they share one working tree — that is concurrency you gave up, not a limit you found. Where the shared environment is what caps parallelism, give each writing strand its own `git worktree` and record where each one is. A worktree holds tracked content only — dependencies and other ignored files do not come across — so isolate where that setup costs less than the parallelism it buys, and not for a strand that only reads.

## Subagent sources

Four sources can run a subagent, each through an in-product mechanism or a headless CLI. **Model selection** decides each dispatch's model family and effort; this section decides which source carries it.

| Source | In-product mechanism | Headless CLI |
|---|---|---|
| Claude Code | the `Workflow` tool (`agent(prompt, {model, effort})`), or a custom subagent whose frontmatter sets `model` and `effort`, dispatched through the `Agent` tool's `subagent_type`; a bare `Agent` call sets `model` only | `claude -p` |
| Codex | Codex subagents / custom agents (TOML with `model` and `model_reasoning_effort`) | `codex exec` |
| Cursor | Cursor's Task-tool subagents (frontmatter `model`; effort and speed as bracket parameters, e.g. `<model-id>[effort=high,fast=false]`) | `agent -p` (legacy binary name `cursor-agent`) |
| Devin | Devin's subagents (custom-subagent frontmatter `model`; effort is encoded in the model ID) | `devin -p` |

Take the first available source in the family's order:

- **Claude-family models**: Claude Code → Cursor → Devin.
- **GPT-family models**: Codex → Devin → Cursor.

For the source you are running in, use its in-product mechanism before its own CLI — on Claude Code the `Workflow` tool or an effort-setting custom subagent, not `claude -p`; on Codex its subagents, not `codex exec`; likewise on Cursor and Devin. Fall back to that source's own CLI only when its in-product mechanism is unavailable or cannot carry the assigned model, effort and fast-mode setting (see **Fast mode** under **Model selection**), and tell the user. Reach every other source through its CLI; such a source is unavailable when its CLI is absent (`command -v <cli>`) or not authenticated (no prior login or API-key env var). A source is also unavailable for a family when its own model list holds no top-tier model of that family (Opus for Claude, Sol for GPT); never substitute a forbidden tier. Skip an unavailable source and take the next source in the family's order. When the family has no available source, **Model selection** names the fallback.

On Claude Code a bare `Agent` call cannot set effort, so two in-product routes carry it: the `Workflow` tool, and a custom subagent. **The `Workflow` tool needs the user's explicit opt-in. It holds from the moment the user invokes or names this skill (for example `/burst`) and stays in force for every later task in the session. It also holds when the user asks for subagents or a workflow, or when ultracode is on for the session. It does not hold when you loaded the skill yourself and the user has never invoked or named it; then dispatch through a custom subagent, or through `claude -p` when that route is unavailable or cannot carry the assignment, and tell the user which route ran.** Under the opt-in, a single-agent workflow script is a legitimate dispatch, not over-orchestration. Write each custom subagent as `~/.claude/agents/<name>.md`, one file per model and effort pair, with `model` and `effort` in its frontmatter, so no file lands in the user's repository; for a leaf delegate, also set `disallowedTools: Agent, Workflow` so it cannot fan out. Pass the brief as the `Agent` prompt. Claude Code picks up a new or edited file without a restart, except in an `agents` directory that did not exist when the session started; until a restart, treat that route as unavailable.

Headless spawns have sharp edges an interactive terminal never shows (stdin/EOF, flag order, model IDs, effort flags, auth checks, output capture). Before the first CLI spawn in a session, read `references/cli-dispatch.md` in this skill's directory and apply its guards to every CLI dispatch.

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

A **verifier** is the same gate in narrower form: a subagent dispatched to confirm one specific claim or behavior — run the test suite, reproduce a bug, re-check a cited source — rather than judge a whole artifact. Verifiers follow the reviewer's rules: independent, grounded in external truth, never the author of the fix.

## Model selection

Map the terminology to whatever the platform exposes — `model`, `subagent_type`, `effort`, `reasoning_effort`, an effort level encoded in the model ID, etc.

**Always set these parameters explicitly on every subagent call.** Never accept the platform default: it can route to a forbidden tier, silently downgrade reasoning, or mirror the orchestrator's own config.

**Parameter-gap rule.** "Set explicitly" applies only to parameters the dispatch tool actually exposes — check the tool's schema, don't assume. When a required knob (typically the effort level) is missing from the default agent tool: (1) still set every knob that does exist (model, agent type); (2) dispatch through the path **Subagent sources** names for that source — the in-product mechanism or CLI flag that carries the knob per agent (for example `-c model_reasoning_effort=<level>` on `codex exec`), subject to the `Workflow` opt-in rule in **Subagent sources**; (3) when the source carries effort but not the level the table assigns, use the highest level it supports at or below the assigned one; (4) only when no available source in the family's order carries the knob, dispatch with the inherited default for that knob alone. An unavailable mechanism, source or runtime goes to **Subagent sources** and **Fallbacks**, never to the inherited default. Disclose (3) and (4) the first time each happens in a run: tell the user which parameter or level could not be passed and what the subagent will actually run. Never report a config label (e.g. "Opus high") as in effect when the mechanism didn't carry it.

Forbidden tiers — two edges, and neither should be chosen unless the user or a higher-priority instruction explicitly calls for it. **Too cheap**: the smallest/distilled variants (`*-mini`, `*-haiku`-class, GPT Luna). **Too expensive**: oversized tiers whose cost outruns their marginal value for delegated work (Fable and Mythos on Anthropic, Astra on OpenAI). Stay between these edges.

All delegated roles use top-tier models — the strongest model inside those edges: Opus on Anthropic, Sol on OpenAI, or the best subagent model the platform exposes elsewhere. In the table below, "Claude" means Opus and "GPT" means Sol. This applies to workers, reviewers, verifiers, sidecar explorers (read-only scouts probing in parallel, off the integration path), and any specialized role spawned for the task. A worker's config may be as strong as the orchestrator's own, capped at that top tier — the too-expensive edge stays forbidden even if the orchestrator itself runs there.

**Resolving the model ID.** Use the newest version of the family that the source offers, read from that source's own model list — never an ID remembered from earlier work or training. Use an alias that resolves to the latest version only when the alias cannot land on a forbidden tier; otherwise pin the full ID read from the list. A bare family alias such as `gpt` can resolve to Luna or Astra, so never use it.

**Family and effort by task type.** Each delegated role runs the family and effort level its task type assigns — no lower to save tokens, no higher by habit. Classify a worker by the work it does; reviewers and verifiers are Review; sidecar explorers are Research. The orchestrator's own final gate is not delegated.

| Task type | First choice | Fallback | Includes |
|---|---|---|---|
| Coding | Claude `medium` | GPT `xhigh` | writing tests, debugging and root-causing, CI and infrastructure config, frontend implementation code |
| Review | GPT `max` | Claude `high` | reviewers, verifiers, security review |
| Backend architecture design | Claude `high` and GPT `max`, both run | — | each produces an independent design; the orchestrator compares and synthesizes them |
| Frontend UI design | Claude `high` | GPT `xhigh` | visual and interaction design (implementation code is Coding) |
| Documentation | GPT `xhigh` | Claude `high` | translation, Chinese writing |
| Research | GPT `max` | Claude `high` | sidecar explorers, data analysis |
| Other simple work | GPT `high` | Claude `medium` | single-step, mechanical, verifiable in seconds |
| Other complex work | GPT `xhigh` | Claude `high` | everything else |

**Fallbacks.** An unavailable source passes to the next source in the family's order (see **Subagent sources**). When the first-choice family has no available source, run the row's fallback family at the row's fallback effort, and tell the user. When only one family is available for backend architecture design, run that one alone and tell the user. A source that cannot carry the assigned effort level falls under the parameter-gap rule. An explicit user instruction overrides all of the above.

Platform-cap exception: if the platform forbids concurrent agents from using the exact same model and effort level, keep the assigned model and use the highest effort level the platform allows at or below the assigned one. State the exception in the progress/final note if it changes a subagent's requested config.

**Fast mode.** Fast mode is the faster, pricier serving tier or speed setting of the same model — a fast variant ID, a service tier or a settings switch, depending on the source. It is off for every model unless the user's own instruction turns it on.

- **Off by default.** Never enable it on your own initiative, for a subagent or for yourself, and never infer it from urgency ("this is urgent", "be quick").
- **An enabling instruction names a scope**: one model (for example "use the fast variant of <model> for this task"); a set of models (for example "use fast mode for all GPT models", or for one family or provider); or every model where a source offers it ("use fast mode for all models as long as it's available"). A request with no model scope, such as "use fast mode for this task", is not yet an instruction: keep fast mode off, and ask the user once which scope they mean — one model, a set, or all models where available — giving those three forms as examples.
- **Persistence.** Once enabled, fast mode stays on for that scope, across later tasks in the session, until the user turns it off or changes the scope. When the user bounds it ("for this task"), it ends with that bound.
- **Scope matching.** A model outside the enabled scope runs at standard speed. When a model inside the scope has no fast option on the source that carries it, run it at standard speed and tell the user; never switch to another model or family to get fast mode.
- **Tiers and effort are unchanged.** Fast mode changes serving speed only. It never unlocks a forbidden tier, never changes the model family or effort level the task-type table assigns, and is not a reason to pick a different source.
- **Carrying it.** On Claude Code and Codex the in-product subagent mechanism cannot set fast mode per subagent: neither the `Workflow` tool nor a custom subagent's frontmatter has a fast setting, and every Codex subagent takes the root session's tier. A role inside an enabled scope on either source is therefore a case of the rule in **Subagent sources** that falls back to the source's own CLI when its in-product mechanism cannot carry the assignment: dispatch it through `claude -p` or `codex exec` with fast mode on, whether or not the `Workflow` opt-in holds, and tell the user which route ran. For the same reason, while your own session runs in fast mode (on Codex, while it has a fast tier selected, even if its own model cannot run it), dispatch a role outside the scope through that CLI with fast mode forced off, since an in-product subagent inherits that setting: on Claude Code every `Agent` and `Workflow` subagent copies the session's fast-mode flag and runs fast when its model supports it, and every Codex subagent takes the root session's selected tier. On Cursor and Devin the subagent's model carries the fast or standard variant, so name it explicitly for every role, inside the scope or outside it, and never let a role take its model from the parent (Cursor's `inherit`, Devin's `subagent_general`), which runs the parent's model and can carry its fast variant. On Devin the `model` frontmatter takes the same values as `--model`, so the fast or standard UID goes there (a fast UID there is untested); on Cursor the parent can name the fast variant ID at launch; in a subagent file `<model-id>[fast=false]` selects the standard variant, while the fast form there is unconfirmed (`references/cli-dispatch.md`). `references/cli-dispatch.md` gives each source's on and off settings, its saved-setting traps, and how it confirms what ran.
- **Disclosure.** When you announce or report each role's model, effort and source, also say whether fast mode is on for it. Report fast mode as in effect only when the run confirms it; where the source gives no confirmation, report it as requested, not confirmed. `references/cli-dispatch.md` says how each source confirms it.

## Orchestrator final gate

A reviewer `pass` does not bypass the orchestrator. The reviewer catches subtask-local quality issues; the orchestrator catches cross-subtask integration issues. The reviewer's verdict is an input to the orchestrator's judgment, not a substitute for it — the orchestrator owns the final call. Everything a worker, reviewer, or verifier returns is reference material by default — a claim to check, not a fact to adopt. Weigh every verdict critically and reconcile a `pass` (or a `revise`/`redo`) yourself against the source of truth and the DoD before accepting it. Reconciliation governs whether you *accept* a verdict, not how you relay it — once you accept a `revise`/`redo`, the worker still receives the reviewer's issues verbatim (see **Reviewer**).

- Verify each subtask against its original goal — scope, expected output, ownership, constraints — and the integrated whole against the DoD.
- Reconcile conflicts with surrounding code, conventions, and other concurrent subagent edits.
- Run the relevant quality gates (typecheck, lint, targeted tests, full suite, manual smoke checks) before declaring a task done. This is the integration backstop, not a substitute for grounding at the reviewer: the final gate runs the full/integration suite to catch cross-subtask breakage, while the reviewer's grounded per-subtask checks catch defects early and locally, before they compound across the integration.
- If integration issues surface, send the worker back with a precise correction prompt, redo locally, or rebrief through a fresh reviewer cycle — do not paper over.
- Surface unresolved risks, skipped checks, or known gaps explicitly in the final summary.

## Communication

- Briefly tell the user what stays local on the critical path and what is being delegated.
- Name the model, effort level, and source behind each delegated role, and whether fast mode is on for it, when you announce or report it — say which model is running the worker, which the reviewer, and so on — so the user can see what each role runs. Disclose every fallback (source, family, or effort) when it happens.
- Note when a reviewer flags issues that trigger worker rework, and report when a subtask hits the two-failed-review stop (see **Reviewer**).
- **Report milestones.** Between tool calls and dispatches, write to the user when something they would want to know has changed: key progress or a milestone, an important finding, a failure or stall, or anything that informs a decision they face. Report a dispatched piece of work when it completes or fails. When a wait has a knowable end — a test suite, a CI pipeline, a long-running delegate — check once at that end rather than polling at intervals. If the state is unchanged, arm the next check. A wait that outruns the end you expected is itself worth a line. Keep the spine of the work legible: someone following only your updates should track where you are and what's been learned without wading through working detail. Keep these updates short and integration-focused.
- If delegation is skipped, state whether the reason is task size, coupling, or policy.
- Before the orchestrator final gate, housekeep: update the docs, records, and to-dos the work touched, so the gate covers those edits too.
- After the final gate, report in the structure and register **Final summary** prescribes — decision-relevant only, no trivial detail.
- **Disposition.** Stay optimistic, steadfast, and calm throughout every task. Report a setback plainly and keep going.

## Final summary

Two registers, two audiences. An update between tool calls and dispatches goes to a reader who already knows your earlier updates, so brevity there is good. The final summary is different: it is written for a reader who saw none of that.

When the run has gone on without the user watching — overnight, across many dispatches, since they last spoke — the final message is their first look at any of it. Write it as a re-grounding, not a continuation of the working thread. The vocabulary the run built up — subtask codenames, worker labels, internal shorthand — is yours, not the reader's; leave it behind unless you re-introduce it.

In the summary itself, drop the working shorthand. Write complete sentences. Spell out terms. Don't use arrow chains, hyphen-stacked compounds, or labels you made up mid-run. When you mention files, commits, flags, or other identifiers, give each one its own plain-language clause.

Take the same order every time. The task, in one or two bullets naming what the reader asked for in their words rather than the run's. The outcome, in one sentence on what happened or what was found. The definition of done as a checklist — the one you fixed before dispatch, not one written afterwards to fit the result — with every ticked item naming the evidence that proves it, and every unticked item saying what is missing and why. Any risk the checklist does not already carry. What remains as open work. Last, and separately, each thing you need from the reader — anything that blocks the work or needs their decision — explained as if new; if you need nothing, ask nothing.

## Self-check

Before declaring a burst task done, confirm:

- [ ] Delegation honored — every non-trivial workstream went to a subagent; nothing was pulled local except genuinely tiny or blocking-dependency steps, the orchestrator's own final gate, and work pulled local after two failed reviews or an integration redo (see **Reviewer** and **Orchestrator final gate**).
- [ ] Concurrency maximized — independent strands ran in parallel, not serialized.
- [ ] Every role ran the model family and effort level the task-type table assigns (see **Model selection**), or a disclosed fallback or explicit user override, resolved to the newest version in the source's own model list, through the highest-priority available source for that family — the host's in-product mechanism for its own source (or, disclosed, its own CLI when that mechanism cannot carry the assignment), a CLI for any other.
- [ ] Every subagent call set every exposed parameter explicitly — no silent platform default, and no forbidden tier (too-cheap `*-mini`/`*-haiku`-class/Luna or too-expensive Fable/Mythos/Astra) unless instructed; every fallback (source, family, or effort) and any un-passable parameter was disclosed to the user, never reported as in effect.
- [ ] Fast mode ran only inside a scope the user named, and was off everywhere else (see **Fast mode** under **Model selection**).
- [ ] Every brief carried the standard forward — the delegate was told to own its result's quality, check decisive claims at the source, and self-review against the brief before declaring done, with that self-review added to the reviewer hop rather than replacing it; and told it is a leaf unless the brief let it fan out.
- [ ] Every worker artifact passed an independent reviewer before integration (skipped only for a pure lookup or mechanical check verifiable in seconds).
- [ ] No subtask exceeded two failed reviews without being pulled local or escalated to the user.
- [ ] Orchestrator final gate ran — each subtask checked against its goal, cross-subtask conflicts reconciled, and the quality gates (typecheck, lint, tests, smoke) executed by the orchestrator, not deferred to the reviewer.
- [ ] Judgment grounded in the source of truth — subagent output treated as reference to verify rather than fact to adopt, and the integrated result checked against the DoD from the sources themselves.
- [ ] Any stretch of the run you know only through a summary, rather than the thread you actually ran, was rebuilt from ground truth before the next dispatch or acceptance (see **Stay grounded**).
- [ ] Final summary reports milestones, carries every skipped check and known gap as an unticked checklist item, notes any fallback or platform-cap config exception, and re-grounds a reader who saw none of the working thread — in the prescribed order, complete sentences, no run-internal shorthand (see **Final summary**).
- [ ] The checklist in the summary is the definition of done fixed before dispatch, not one written to fit the result; every ticked item names its evidence, and every unticked item says what is missing.
