# WS5 — Planning, verification, and the training/inference boundary

**Scope:** how agents decompose work, how a system establishes the work is correct, what an LLM can check about itself, and which parts of a verification harness are durable versus scaffolding the next model absorbs. | **Access date: 2026-08-03** | **Deferred to:** WS2 (multi-agent role wiring), WS6 (benchmark scores as measurements), WS1 (thinking budgets).

## 1. Executive summary

1. **"LLMs cannot self-correct reasoning" held up.** Per Kamoi et al. the bottleneck is *feedback generation*, not revision. **[high]** (§2.2)
2. **The one real softening is at training time** — SCoRe's multi-turn online RL. A builder who cannot train cannot buy it. **[high]** (§2.2)
3. **Verification is a capability distinct from generation**; verifiers can be far smaller and still select well. **[medium-high]** (§2.3–2.4)
4. **Executable ground truth is the strongest signal and the most attackable.** 500/500 SWE-bench Verified fell to a ~10-line `conftest.py`. **[high]** (§2.3)
5. **Tuning a standalone evaluator to be skeptical beats making a generator self-critical** — Anthropic, Mar 2026. **[high]** (§2.5)
6. **Explicit plans pay off as machine-checkable artifacts, not prose.** **[medium-high]** (§2.1)
7. **Some scaffolds already got absorbed** — Anthropic dropped context resets once Opus 4.5 removed the behaviour it compensated for. **[high]** (§2.6)
8. **Verification buys reliability, not capability.** `pass@k` rises with k, `pass^k` falls. **[high]** (§2.4; WS6 owns scores)
9. **Agents are bad at stopping.** Best AgentAbstain paired accuracy 59.5%; 13/17 below 50%. **[high]** (§2.7)
10. **Approval gates are verification with a decay function**, and a decayed gate is worse than none. **[medium-high]** (§2.8)

## 2. Findings

### 2.1 Planning

Four shapes, separated by *what the plan is made of* more than when it is computed.

**Implicit (ReAct)** is the production default: recomputed each turn, adapts freely, but the agent never sees the whole task and cost grows with history.

**Explicit plan-then-execute** — a strong model emits an ordered plan, a cheaper executor walks it. Gains are auditability and cost-shifting; the cost is brittleness, since the plan was written before any step ran, making replanning its load-bearing recovery path. **[medium — pattern catalogs and practitioner reports, not controlled experiments]**

**Artifact/state-file planning** is where the strongest evidence sits. Anthropic's initializer agent writes `feature_list.json` (200+ entries for a claude.ai clone) with every feature initialised `"passes": false`; coding agents may only flip `passes`. They chose JSON over Markdown because "the model is less likely to inappropriately change or overwrite JSON files." Their companion repo generalises this to a **default-FAIL contract**: "every criterion starts `false`; the agent can't mark it passing without opening evidence first," enforced by a `PreToolUse` hook. **[high]**

**Search over plans (ToT / graph-of-thought)** largely did not survive production in its original form — reasoning models internalise the search. It survives as bounded beam search at the *plan* level (3–5 candidates, evaluator keeps the best), not at leaf level, restating Snell et al.: matching strategy to difficulty beat best-of-N by >4×. **[medium]**

**Replanning triggers** form an escalation ladder: retry with backoff on transient errors; local step substitution on deterministic "not found"; full replan on a *contradicting observation*; abort after K consecutive failures on one step. Guardrails: hard step cap, a replan budget distinct from the step budget, progress detection, semantic dedup. The self-healing-orchestrator work names the principle: recovery that is "targeted and bounded." **[medium]**

**Helps vs. overhead.** A plan earns its cost when it is a contract someone else can check (Anthropic's generator and evaluator negotiate per-sprint criteria before code — Sprint 3 carried 27), when it must survive a context boundary, or when a human approves spend. It is overhead on single-step tasks and wherever each step depends on the last result.

### 2.2 Self-correction: the precise state of the evidence

**Huang et al., arXiv:2310.01798 (ICLR 2024)** defines *intrinsic* self-correction: inherent capabilities only, no external feedback, model decides when to stop. Prior positives leaked oracle labels by using ground truth to decide whether to keep revising; remove the oracle and "the accuracies of all models drop across all benchmarks." Mechanism: on GSM8K, GPT-3.5 kept its initial answer 74.7% of the time and, among changes, more often went correct→incorrect. Multi-agent debate was no better than self-consistency at matched response count. **GPT-3.5-turbo-0613, GPT-4, GPT-4-1106-preview, Llama-2-70b-chat; accessed 2023-08-29; authors' harness** — cite for mechanism, not capability. **[high, foundational]**

**Kamoi et al., arXiv:2406.01297 (TACL)** audits the field for unfair setups: no work shows self-correction from prompted-LLM feedback on general tasks; it works where reliable external feedback exists; fine-tuning at scale enables it. **[high, foundational]**

**SCoRe, arXiv:2409.12917 (ICLR 2025).** SFT on offline correction traces fails; two-stage on-policy RL with a correction reward bonus works. Δ(t1,t2) +4.4% (first significantly positive), +15.6% MATH, +9.1% HumanEval; incorrect→correct 9.5%→14.5% while correct→incorrect fell 15.8%→1.4%. **Gemini 1.0 Pro / 1.5 Flash, authors' MATH/MBPP-R/HumanEval eval, Sept 2024, DeepMind reporting.** **[high]**

A **Jan 2026 preprint** on GSM8K-Complex reports an *Accuracy–Correction Paradox*: the strongest model had the lowest intrinsic correction rate (16.7% vs 26.8%), and error-location hints hurt every model. **[low — small preprint, n=500/model]**

**Synthesis:** every reliable correction loop closes over something the generator did not produce — a test result, a compiler, an environment observation, a differently-conditioned critic, or a training-time reward.

### 2.3 External verification

**Executable ground truth.** OpenAI's RFT docs state the precondition bluntly — "If you can't write code to judge the answer with an available grader, RFT is not the right tool" — and warn that reward functions must be designed against exploitation, since reasoning models find edge cases in grading logic. **[high — vendor docs]**

The attack surface is documented at scale: BenchJack found 219 flaws in 8 recurring classes across 10 agent benchmarks; SWE-bench Verified fell 500/500 to a `pytest_runtest_makereport` hook, and its 231 `unittest` Django instances to a monkey-patch of `unittest.TestCase.run`. BenchJack also patched hackable-task ratios from near 100% to <10% — a fixable trust-boundary bug, not an indictment of executable verification. **The rule that generalises: the grader must not run in a filesystem the agent can write to.** **[high]**

**PRM vs ORM.** Lightman et al. established process supervision beating outcome supervision on MATH and released PRM800K. The 2025–2026 view is more equivocal: an ACL 2026 survey documents a shift to implicit and generative PRMs because step labels are expensive and noisy, and VeriGate frames integration as *preserving verifier authority*, warning that naive use "can let an imperfect signal override a trustworthy verifier and invite reward hacking." Deterministic outcome verification stays the authority. **[medium-high]**

**LLM-as-judge** is scalable but not gate-worthy alone. Position bias is documented across 15 judges and ~150k instances (MT-Bench + DevBench) as non-random, varying by judge and task, and strongly affected by the quality gap between candidates — worst exactly where the judge matters most. Mitigation is mechanical, not prompt-based: swap positions every pairwise call and tie on flips; never judge with a same-family model; recalibrate against human labels on every swap. Anthropic's rule is "deterministic graders where possible, LLM graders where necessary." **[high that the biases exist; medium on effect sizes]**

**Reasoning as a verification surface.** OpenAI's deliberative-alignment and CoT-monitorability work treat the reasoning trace as something a *separate* monitor reads, not something the generator scores for itself — the separation principle one level down, plus the caution that optimising against a monitor degrades it. **[medium]**

### 2.4 Sampling and selection

Self-consistency remains the canonical cheap selector (+17.9% GSM8K, +11.0% SVAMP, +12.2% AQuA on PaLM-540B/GPT-3-class models), but its precondition is routinely violated in agent products: it marginalises reasoning paths onto a **unique closed-form answer**, so it cannot select among free-form reports. **[high, foundational]**

Snell et al. supply the cost curve — the best test-time strategy depends on prompt difficulty. Weaver is the orthogonal practical result: aggregating *weak* verifiers by unsupervised weak supervision lifted 1-sample accuracy 17.9–27.8 points across four benchmarks, beat majority voting by 23.2 points, then distilled to a 400M model keeping up to 98.7% of ensemble selection accuracy at ~0.03% of verification FLOPs. **[medium-high — lab blog on its own paper]**

On **`pass@k` vs `pass^k`**, Anthropic states the arithmetic plainly: a 75%-per-trial agent passes three consecutive trials 42% of the time, and by k=10 the metrics "tell opposite stories." A Mar 2026 reliability-science preprint (396 tasks, 10 open-weight models, 23,392 episodes, k=3) adds a Graceful Degradation Score for partial completion, finds the GDS–pass@1 gap widens at long horizons, and reports two counterintuitive results: high variance amplification is a *capability* signature, and naive episodic memory was negative or neutral for all 10 models. **[medium — single preprint, open-weight models only]**

### 2.5 Critic and reflection loops

Reflexion originated verbal-feedback retry, and its own framing already names external environments (compilers, APIs, games) as the feedback source — the variant later work says reliably helps. Its 2023 headline number is not current.

The 2026 production form is the generator/evaluator split. Anthropic's Mar 2026 harness is GAN-inspired: a generator builds; an evaluator with the Playwright MCP *clicks through the running application* and grades each sprint against per-criterion thresholds. Published findings cite file and line (`LevelEditor.tsx:892`) and propose the fix — the critic's value came from acting in the environment, not re-reading the diff. Cost: solo run 20 min / $9 versus full harness 6 hr / $200. **[high on the pattern; low on the cost/quality trade — n=1 prompt, one author, Opus 4.5]**

Shipped versions exist. Claude Code's `/goal` runs a small fast model as an after-every-turn evaluator so "completion is decided by a fresh model rather than the one doing the work" — but it "does not call tools, so it can only judge what Claude has already surfaced," the weak form of the pattern. The companion repo ships an evaluator subagent **with no Write/Edit tools** that "reviews the diff and the screenshots from a context window that never saw the build." LangChain's `agentevals` encodes the §2.3 ordering as an API: a `create_trajectory_match_evaluator` its docs call "deterministic, fast, and cost-effective since it doesn't require additional LLM calls," with an LLM trajectory judge reserved for "nuanced aspects like efficiency and appropriateness." Anthropic's skills guidance packages the same cycle as a reusable skill. DSPy's GEPA turns critique into an optimiser — its metric returns `dspy.Prediction(score, feedback)`, and a plain float degrades it because "concrete failure modes never reach" the proposer. **[medium-high]**

### 2.6 Training-time architecture: what gets absorbed

The main agentic-RL survey frames the shift as single-step MDPs → temporally extended POMDPs, with planning, tool use, memory and self-improvement as capabilities RL converts "from static, heuristic modules into adaptive, robust agentic behavior" — the bitter-lesson claim from RL researchers. A 2026 companion survey adds the engineering layer, notably **environments as first-class artifacts** separating training gyms from held-out certifications. The honest boundary: RLVR supplies automatic reward wherever correctness is programmatically checkable, and no equivalent exists for most agentic workflows. Long-horizon credit assignment remains the open problem. **[medium — surveys]**

The strongest durability signal is a natural experiment across one vendor's two posts:

| Scaffold | Nov 2025 | Mar 2026 | Verdict |
| --- | --- | --- | --- |
| Context resets between sessions | Essential (Sonnet 4.5 "context anxiety") | **Dropped** — Opus 4.5 "largely removed that behavior on its own" | Absorbed |
| "Test end-to-end as a user would" | Prompting | An evaluator role driving Playwright | Enduring |
| Default-FAIL ledger / contract | Introduced | Elaborated as sprint contracts | Enduring |
| Separate evaluator context | Not yet | Shipped as `/goal` and a no-write subagent | Enduring, moving into the product |

The pattern: **scaffolds compensating for a model deficiency get absorbed; scaffolds encoding a trust boundary, a budget, or an external ground-truth signal do not** — no model improvement makes a generator an independent witness to its own output. Browser Use argues the strong form, "the less you build, the more it works"; a useful corrective, but one experience report that still keeps a `done` tool, ephemeral messages and a retry layer. **[medium — vendor]**

### 2.7 Reliability engineering and calibration

Three mechanisms make success machine-readable rather than narrative: **default-FAIL criteria with evidence requirements**; **weighted-subtask partial credit**, so a run reports 0.44 not "failed"; and **a fresh-context grader returning a structured verdict** (`PASS`/`NEEDS_WORK` plus findings seeding the next session).

Calibration is the weakest link. RiskEval finds models "neither cost-aware when articulating their verbal confidence, nor strategically responsive when deciding whether to engage or abstain," almost never abstaining even when extreme penalties make it optimal. AgentAbstain (Jul 2026, 17 models, 4 harnesses) reports a best paired accuracy of 59.5% with 13/17 below 50%, and names *post-hoc abstention* — irreversible action first, refusal claimed after — as an agent-specific failure. Agentic Abstention (13 systems, >28,000 tasks) finds *timing* is the harder half, with "larger or more capable models sometimes perform worse at timely abstention"; its CONVOLVE method distils trajectories into stopping rules with no weight updates, raising Llama-3.3-70B's WebShop timely recall 26.7 → 57.4. **[high on direction; medium on specifics — 2026 preprints]**

### 2.8 Human-in-the-loop as verification

Approval gates buy real safety at a point of no return and only latency elsewhere. Three properties make one load-bearing: it precedes the first irreversible action (gating the confirmation email after the refund issued is theatre); it surfaces the actual artifact plus the agent's reasoning, not an AI-written summary; and it blocks one decision, not the whole run.

The decay mechanism is named in the human-factors literature (automation bias, complacency) and now anticipated by regulation: EU AI Act Article 14 requires deployers to keep operators aware of the tendency to over-rely on AI output. Operational tell — an approval rate pinned at 99–100% means the action class has earned auto-execution or the review is dead. Of the three shipped variants (approve-before-tool-call, choose-between-options, free-form correction) only the latter two capture reviewer judgment as reusable signal. A gate verifies *intent and blast radius*, which a test cannot; a test verifies *correctness*, which a rushed reviewer cannot. **[medium-high — practitioner synthesis over an older decision-support literature; the regulatory hook is primary]**

## 3. Delta since 2026-07-14

| Prior-pass position | Status now |
| --- | --- |
| §3.8 prefer fresh-context evaluator; labelled a **transferred** coding lesson, "not research-native evidence" | **Upgraded, mechanism named.** Anthropic (Mar 2026) states the causal claim and shipped it. Relax the caveat for the *separation principle*, keep it for domain rubrics. |
| Anti-pattern: majority-vote over free-form reports | **Confirmed.** The right generalisation is weak-verifier aggregation or verifier rank-and-select. |
| Self-correction appeared only as "self-verifier in same context → positive bias" | **Now has a literature.** Huang, Kamoi, SCoRe were uncited. Intrinsic self-correction fails; *trained* self-correction is the exception. |
| "Single coding agent + tests as ground truth" treated as unproblematic | **Materially revised.** Apr–May 2026 benchmark-hacking results make the trust boundary explicit. |
| Nothing on calibration, abstention, honest failure | **New.** Abstention scales independently of capability. |
| Nothing on training-time / harness co-evolution | **New (§13 material).** Dropping context resets anchors absorption. |
| HITL framed only as "gate high-impact side effects" | **Adds the decay function** — needs approval-rate monitoring and payload design. |
| ToT / graph-of-thought absent | **New.** Survives only as bounded plan-level beam. |

## 4. Contested / open questions

| Question | Confidence | Note |
| --- | --- | --- |
| Does a skeptical fresh-context evaluator help *research/synthesis*, or only code and UI? | **Low–medium** | All strong evidence is coding/frontend. |
| Is the generation–verification gap narrowing or stable? | **Low** | No longitudinal series; the durability argument is analytic. |
| Do PRMs earn their cost outside math? | **Low–medium** | Both sources gate process signal behind outcome verifiers. |
| Does eval-time reward hacking transfer to production? | **Low** | Flagged as open by the reporting sources. |
| `pass^k` or partial-credit GDS as the product metric? | **Medium** | Depends on whether one success suffices. |
| How much will the next model absorb? | **Low** | One documented instance. |
| Are the 2026 abstention/reliability preprints replicable? | **Low–medium** | Several single-lab. |

## 5. Anti-patterns & failure modes

| Anti-pattern | Why it fails | Prefer |
| --- | --- | --- |
| "Check your work carefully" to the generator | Degrades accuracy | Any external signal: test, compiler, observation |
| Grader in the agent's writable workspace | 500/500 SWE-bench Verified | Out-of-container / read-only grading |
| Same-family judge, single ordering, no calibration | Position bias, worst when candidates are close | Swap order, tie on flips; cross-family judge |
| Majority vote over free-form output | Needs a closed-form answer | Verifier rank-and-select; weak-verifier aggregation |
| Plan as prose | Nothing to check | Default-FAIL ledger, restricted edit surface |
| Replan on every error | Thrash without progress | Escalation ladder, replan budget, progress check |
| Unbounded critic loop | No convergence guarantee | Iteration cap; exhaustion routes to review |
| Binary outcome on long-horizon work | pass@1 → 0; partial progress discarded | Weighted subtask credit |
| Gating on stated confidence | Dissociated from action | Gate on external checks |
| Gating every action | Trains the reflex that approving is safe | Risk-signal gates at the point of no return |
| Approving an AI-written summary | Reviewer cannot disagree without the artifact | Show the diff / payload |
| Post-hoc abstention | Acts irreversibly, then reports refusal | Feasibility check before the call |

## 6. Design implications

1. **Make the verifier structurally different from the generator — context and tools, not just prompt.** A no-write evaluator cannot quietly fix what it should report. *Trade-off:* tokens, wall-clock, and calibration examples.
2. **Give the verifier an action, not a transcript.** The actionable findings came from an evaluator driving the app; a transcript-only evaluator like `/goal` can only judge what was surfaced. *Trade-off:* slow; needs tools.
3. **Move the plan into a default-FAIL ledger with a restricted edit surface.** Converts "did it succeed?" into a query. *Trade-off:* upfront authoring; over-specified criteria cascade errors.
4. **Treat the grading trust boundary as a security property.** The cheapest path to a green signal is to forge it. *Trade-off:* out-of-container grading costs infrastructure.
5. **Rank-and-select with a verifier before N-way voting; a small verifier may suffice.** Voting's closed-form precondition is usually violated. *Trade-off:* another artifact to calibrate.
6. **Report partial success as a first-class outcome with weighted subtask credit.** Binary reporting discards the only signal that varies at long horizons. *Trade-off:* partial scores are gameable.
7. **Never gate on stated confidence; gate on an external check or policy.** Verbal confidence is dissociated from action. *Trade-off:* external checks don't cover every claim — an argument for narrowing promises.
8. **Place gates by risk signal at the point of no return, show the artifact, instrument the approval rate.** *Trade-off:* needs an action inventory.
9. **Build scaffolds encoding trust boundaries, budgets and external ground truth; delete ones compensating for model deficiencies.** *Trade-off:* the category is unknowable until a model ships — version harness assumptions accordingly.
10. **If self-correction is the bottleneck and you cannot train, stop prompting your way there.** The substitute is a better external signal.

## 7. Sources

All retrieved 2026-08-03.

| # | Source | Date | URL |
| --- | --- | --- | --- |
| 1 | Huang et al. — *LLMs Cannot Self-Correct Reasoning Yet* (foundational) | 2023-10 | https://arxiv.org/abs/2310.01798 |
| 2 | Kamoi et al. — *When Can LLMs Actually Correct Their Own Mistakes?* (foundational) | 2024-06 | https://arxiv.org/html/2406.01297v3 |
| 3 | Kumar et al. — *Training LMs to Self-Correct via RL* (SCoRe) | 2024-09 | https://arxiv.org/pdf/2409.12917 |
| 4 | *Accuracy–Correction Paradox / Error Depth Hypothesis* (preprint **[low]**) | 2026-01 | https://arxiv.org/html/2601.00828v1 |
| 5 | Shinn et al. — *Reflexion* (foundational) | 2023-03 | https://arxiv.org/abs/2303.11366 |
| 6 | Lightman et al. — *Let's Verify Step by Step* (foundational) | 2023-05 | https://arxiv.org/abs/2305.20050 |
| 7 | Wang et al. — *Self-Consistency* (foundational) | 2022-03 | https://arxiv.org/abs/2203.11171 |
| 8 | Snell et al. — *Scaling LLM Test-Time Compute Optimally* (foundational) | 2024-08 | https://arxiv.org/abs/2408.03314 |
| 9 | Anthropic — *Effective harnesses for long-running agents* (vendor experiment) | 2025-11-26 | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| 10 | Anthropic — *Harness design for long-running application development* | 2026-03-24 | https://www.anthropic.com/engineering/harness-design-long-running-apps |
| 11 | Anthropic — *Demystifying evals for AI agents* | 2026-01-09 | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents |
| 12 | Anthropic — *Building verification loops in Claude Code with skills* | 2026-07-22 | https://claude.com/blog/building-verification-loops-in-claude-code-with-skills |
| 13 | `anthropics/cwc-long-running-agents` — default-FAIL contract, no-write evaluator | 2026 | https://raw.githubusercontent.com/anthropics/cwc-long-running-agents/main/README.md |
| 14 | Claude Code docs — `/goal` per-turn separate-model evaluator | 2026 | https://code.claude.com/docs/en/goal |
| 15 | UC Berkeley RDI — *How we broke top AI agent benchmarks* | 2026-04 | https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/ |
| 16 | *BenchJack: Auditing AI Agent Benchmarks* | 2026-05 | https://arxiv.org/html/2605.12673 |
| 17 | Shi et al. — *Judging the Judges: Position Bias* (IJCNLP 2025) | 2025 | https://aclanthology.org/2025.ijcnlp-long.18.pdf |
| 18 | Hazy Research — *Weaver: Closing the Generation-Verification Gap* | 2025-06-18 | https://hazyresearch.stanford.edu/blog/2025-06-18-weaver |
| 19 | *Beyond pass@1: Reliability Science for Long-Horizon Agents* (preprint **[medium]**) | 2026-03 | https://arxiv.org/abs/2603.29231 |
| 20 | *AgentAbstain: Do LLM Agents Know When Not to Act?* (preprint) | 2026-07 | https://arxiv.org/html/2607.10059v1 |
| 21 | *Agentic Abstention* / CONVOLVE (preprint) | 2026-06 | https://arxiv.org/html/2606.28733v1 |
| 22 | *Are LLM Decisions Faithful to Verbal Confidence?* (RiskEval, preprint) | 2026-01 | https://arxiv.org/pdf/2601.07767 |
| 23 | Zhang et al. — *Landscape of Agentic RL for LLMs* (survey) | 2025-09 (v5) | https://arxiv.org/html/2509.02547v5 |
| 24 | *Training Recipes for Agentic RL in LLMs* (survey) | 2026 | https://doi.org/10.36227/techrxiv.176972131.13438500/v1 |
| 25 | OpenAI — *Reinforcement fine-tuning* (grader contract; vendor docs) | 2026 | https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning |
| 26 | OpenAI — *Evaluating chain-of-thought monitorability* | 2025-12-18 | https://openai.com/index/evaluating-chain-of-thought-monitorability/ |
| 27 | OpenAI — *Deliberative Alignment* | 2024-12 | https://arxiv.org/pdf/2412.16339 |
| 28 | *A Survey of Process Reward Models* (ACL 2026) | 2026 | https://aclanthology.org/2026.acl-long.163.pdf |
| 29 | *VeriGate: Verifier-Gated Step-Level Supervision for GRPO* (preprint) | 2026-05 | https://arxiv.org/pdf/2605.30451 |
| 30 | Agrawal et al. — *GEPA* + DSPy GEPA docs (feedback-shaped metric) | 2025-07 / 2026 | https://dspy.ai/api/optimizers/GEPA/overview/ |
| 31 | *Self-Healing Agentic Orchestrators* (bounded recovery ladder; preprint) | 2026-06 | https://arxiv.org/html/2606.01416v1 |
| 32 | Agent Patterns Catalog — *Replan on Failure*, *Tree of Thoughts* **[medium]** | 2026-04/05 | https://www.agentpatternscatalog.org/patterns/replan-on-failure/ |
| 33 | Tian Pan — *Approval Fatigue* (EU AI Act Art. 14, gate placement) **[medium]** | 2026-06 | https://tianpan.co/blog/2026-06-25-approval-fatigue-how-human-in-the-loop-gates-decay-into-rubber-stamps |
| 34 | Zunic (Browser Use) — *The Bitter Lesson of Agent Frameworks* **[vendor claims]** | 2026-01-16 | https://browser-use.com/posts/bitter-lesson-agent-frameworks |
| 35 | LangChain — *Trajectory evaluations* (`agentevals`: deterministic matcher + LLM judge) | 2026 | https://docs.langchain.com/langsmith/trajectory-evals |

## 8. Proposed content for final doc sections

**§ 9 Planning & decomposition.** Organise by *plan substrate* (implicit / explicit step list / machine-checkable ledger / searched space) — it decides whether anything downstream can check the plan.

- Default to ReAct for unpredictable short-horizon turns; plan-then-execute where structure is knowable and someone approves spend.
- Make the ledger concrete with Anthropic's shape: default-FAIL, restricted edit surface, git handoff. The sprint contract seats a plan-approval gate.
- Present replanning as the escalation ladder plus four guardrails; resolve ToT explicitly. Cross-ref WS2 for who executes, WS1 for thinking budget.

**§ 10 Verification, self-correction & quality.** Lead with the load-bearing claim and its scope: intrinsic self-correction fails, the bottleneck is feedback generation, and the one demonstrated exception is a training-time result.

- Verifier hierarchy strongest → weakest: executable ground truth → environment observation by a separate agent → cross-family judge with mechanical debiasing → self-check, a heuristic rather than a verifier.
- Give the trust boundary its own callout with the `conftest.py` result.
- Selection: self-consistency only for closed-form answers, verifier rank-and-select otherwise. Reliability: `pass@k` vs `pass^k` as a product decision, weighted partial credit as the reporting primitive, plus the three self-detectability mechanisms.
- Close on calibration and HITL: never gate on stated confidence; gate at the point of no return; show artifacts; track approval rate. Reuse §5.

**§ 13 Training-time vs inference-time architecture.** Frame as one question: how much scaffolding to build if the model will absorb some of it.

- Descriptive half: agentic RL as MDP → POMDP, RLVR where correctness is checkable, the gap for non-verifiable workflows, credit assignment as the open problem, environments as first-class artifacts.
- Include the Nov 2025 → Mar 2026 absorption table verbatim; it is the only first-party evidence here.
- State the durable/absorbed heuristic, note the harness-to-product path (`/goal`), then the rule: version harness assumptions against model versions.
