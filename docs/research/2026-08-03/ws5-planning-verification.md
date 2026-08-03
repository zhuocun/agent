# WS5 — Planning, verification, and the training/inference boundary

**Scope:** how agents decompose work, how a system establishes that the work is correct, what an LLM can check about itself, and which parts of a verification harness endure versus get absorbed. | **Access date: 2026-08-03** | **Deferred to:** WS2 (multi-agent role wiring), WS6 (benchmark scores), WS1 (thinking budgets).

## 1. Executive summary

1. **Intrinsic self-correction of reasoning fails; the bottleneck is feedback generation, not revision.** Huang, Kamoi, CRITIC's tool ablation and Self-Refine's math null agree. **[high]** (§2.2)
2. **Self-Refine, the strongest positive counterfinding, does not contradict that** — its gains are on preference-judged open-ended tasks, and on math it gained 0–0.2 points — while the one demonstrated softening, SCoRe's on-policy RL, is at training time and cannot be bought by a builder who cannot train. **[high]** (§2.2)
3. **Verification is a capability distinct from generation;** verifiers can be far smaller than generators and still select well. **[medium-high]** (§2.3–2.4)
4. **Executable ground truth is the strongest signal and the most attackable:** a 10-line `conftest.py` resolved 500/500 SWE-bench Verified instances. **[high]** (§2.3)
5. **Verification buys reliability, not capability:** gpt-4o goes ~61% `pass^1` to under 25% `pass^8` on τ-retail. **[high]** (§2.4; WS6 owns scores)
6. **Separating verifier context from generator context is well-supported in principle** **[high]**; the "skeptical evaluator with browser tools" harness is one vendor experiment **[low-medium]** (§2.5)
7. **Plans pay off when machine-checkable rather than prose** — one vendor's harness plus its companion repo. **[low-medium]** (§2.1)
8. **At least one scaffold has been absorbed into a model** (context resets, dropped for Opus 4.5). **[medium]** (§2.6)
9. **Agents are bad at stopping:** best AgentAbstain paired accuracy 59.5%, 13/17 models below 50%. **[medium]** (§2.7)

## 2. Findings

### 2.1 Planning

Four shapes, separated by *what the plan is made of* more than when it is computed.

**Implicit (ReAct-style)** recomputes the next step each turn: adaptive, never exposing the whole task, costly as history grows. Its ceiling is measurable — on τ-bench, agents "built with simple LM constructs (like function calling or ReAct) perform poorly," gpt-4o reaching ~61% `pass^1` on τ-retail and ~35% on τ-airline (Yao et al., Sierra, Jun 2024, authors' harness). I found no measurement of its production share, so "the default" is an impression.

**Explicit plan-then-execute** trades brittleness for auditability, and replanning is its recovery path. It earns its cost when the plan is a contract someone else checks (Anthropic's generator and evaluator negotiate per-sprint criteria before code), when it must survive a context boundary, or when a human approves spend; it is overhead on single-step tasks and wherever each step depends on the last. **[medium — practitioner reports, not controlled experiments]**

**Artifact/state-file planning** has the most concrete evidence. Anthropic's initializer writes `feature_list.json` (200+ entries for a claude.ai clone) with every feature initialised `"passes": false`; agents may only flip `passes`, and JSON beat Markdown because "the model is less likely to inappropriately change or overwrite JSON files." The companion repo generalises this to a **default-FAIL contract** — "the agent can't mark it passing without opening evidence first" — enforced by a `PreToolUse` hook. **[low-medium — one vendor, one prompt, Opus 4.5, no controlled comparison against prose]**

**Search over plans (ToT / beam / lookahead).** Snell et al. searched against a process reward model, PaLM 2-S\* fine-tuned for revision and verification on MATH (Aug 2024, UC Berkeley + Google DeepMind): the best strategy depends on prompt difficulty, and compute-optimal allocation matched best-of-N on ~4× less test-time compute. **It says nothing about production adoption, which I found no source measuring either way.** **[medium; adoption unevidenced]**

**Replanning triggers** form an escalation ladder: retry with backoff on transient errors, local step substitution on deterministic "not found", full replan on a *contradicting observation*, abort after K consecutive failures on one step. Guardrails: step cap, a replan budget separate from the step budget, progress detection, semantic dedup. The self-healing-orchestrator work names the principle: recovery that is "targeted and bounded." **[medium]**

### 2.2 Self-correction: the precise state of the evidence

**Huang et al., arXiv:2310.01798 (ICLR 2024)** defines *intrinsic* self-correction: no external feedback, model decides when to stop. Prior positives leaked oracle labels — ground truth decided when to stop revising; remove it and "the accuracies of all models drop across all benchmarks." On GSM8K, GPT-3.5 kept its initial answer 74.7% of the time and, among changes, more often went correct→incorrect. **GPT-3.5-turbo-0613, GPT-4, Llama-2-70b-chat; authors' harness; accessed 2023-08-29.** **[high, foundational]**

**Kamoi et al., arXiv:2406.01297 (TACL)** audits the field for unfair setups and lands the load-bearing distinction: no work demonstrates self-correction from prompted-LLM feedback on general tasks; it works where reliable external feedback exists; large-scale fine-tuning enables it. **[high, foundational]**

**CRITIC (Gou et al., ICLR 2024)** isolates the variable by ablation: with tools, ChatGPT gained +7.7 F1 across three QA sets and +7.0 points across three math sets; same prompt with the tool removed, text-davinci-003 on GSM8K went +2.1 with a code interpreter and −1.8 without, and toxicity rose *above* the untouched baseline (0.344 → 0.353) once the classifier was gone. "LLMs (mostly) don't know what they know." **ChatGPT, text-davinci-003, LLaMA-2 7B/13B/70B; authors' harness.** **[high]**

**Self-Refine (Madaan et al., NeurIPS 2023)** is the standard counterexample, and its own numbers resolve the conflict: a ~20% absolute average gain over seven tasks hides the distribution — Dialogue Response +49.2 on GPT-4 under human A/B and GPT-4-as-proxy preference, against **Math Reasoning +0.0 / +0.2 / +0.2** for GPT-3.5 / ChatGPT / GPT-4. The authors attribute the math null to "the inability to accurately identify whether there is any error" — ChatGPT's feedback was "everything looks good" on 94% of instances — and report gains above 5% once an external source flags incorrectness. It improves subjective quality; it does not find errors. **[high]**

**SCoRe (Kumar et al., ICLR 2025)** is the training-time exception, carefully framed: SFT on offline correction traces is "often insufficient," not useless — Pair-SFT reached Δ(t1,t2) **+1.8%** against the base model's **−11.2%**, never substantially positive, since SFT falls prey to *either* distribution mismatch *or* behaviour collapse. Two-stage on-policy RL with a correction reward bonus reached **+4.4%**, the first significantly positive delta; gains over base **+15.6% on MATH (Gemini 1.5 Flash)**, **+9.1% on HumanEval (Gemini 1.0 Pro); authors' harness, Sept 2024, Google DeepMind.** **[high]**

A **Jan 2026 single-author preprint** (GSM8K-Complex, n=500 per model, three non-frontier models) reports an *Accuracy–Correction Paradox*: the strongest model had the lowest intrinsic correction rate (DeepSeek-Chat 16.7%, GPT-3.5-Turbo 26.8%, Claude-3-Haiku 29.1%). Its abstract claims error-location hints "hurt all models"; Table 1 shows them *helping* DeepSeek (16.7% → 26.7%), with only GPT-3.5 and Claude declining; DeepSeek's arm rests on 30 errors with overlapping intervals. **[low — direction only]**

**Synthesis:** every reliable correction loop closes over something the generator did not produce — a test result, a compiler, an environment observation, a differently-conditioned critic, or a training-time reward.

### 2.3 External verification

**Executable ground truth.** OpenAI's RFT use-cases page states the precondition: "If you can't write code to judge the answer with an available grader, RFT is not the right tool" — a *human-out-of-the-loop* grader, not executable ground truth specifically, since the same page recommends "an LLM judge when code falls short," with a separate model and a step to "evaluate the judge." The RFT guide warns a model may "learn to reward hack your grader… without actually being correct." **[high — vendor docs, one platform]**

The attack surface is documented at scale. Berkeley RDI reports a 10-line `conftest.py` registering a `pytest_runtest_makereport` hook that resolved **500/500 SWE-bench Verified and 731/731 SWE-bench Pro instances with zero issues solved** (Apr 2026, authors' agent). BenchJack audited 10 agent benchmarks, found 219 flaws in 8 classes, and patched hackable-task ratios from near 100% to under 10% (May 2026) — a fixable trust-boundary bug, not an indictment of executable verification. The root cause is constant: the patch runs in the grader's container. **The grader must not run in a filesystem the agent can write to.** **[high]**

**PRM vs ORM.** Lightman et al. established process supervision beating outcome supervision on MATH and released PRM800K; the 2025–2026 view is more equivocal, an ACL 2026 survey documenting a shift to implicit and generative PRMs because step labels are expensive and noisy. Deterministic outcome verification stays the authority; process signal aids it. **[medium-high]**

**LLM-as-judge** is scalable but not gate-worthy alone. Position bias across 15 judges and ~150k instances (MT-Bench + DevBench, IJCNLP 2025) is non-random and worst when candidates are close in quality — exactly where the judge matters most. Self-preference is real but smaller than first reported: across 9 judges and >5,000 human-annotated pairs (Aug 2025), GPT-4o and Claude 3.5 Sonnet over-scored their own *and* same-family outputs, but only "in some evaluation dimensions and datasets"; a Jan 2026 check over 37,448 queries found that controlling for judge error on hard items leaves **only 51% of prior self-preference findings significant** — near-vanishing on objective tasks (−98.8% on MATH500), persisting on subjective ones. Prefer a cross-family judge for subjective criteria; on objectively checkable tasks a judge is the wrong tool anyway. Mitigations are mechanical: swap positions on every pairwise call, tie on flips, recalibrate against human labels. **[high that the biases exist; medium on effect sizes]**

### 2.4 Sampling and selection

Self-consistency remains the canonical cheap selector (+17.9% GSM8K, +11.0% SVAMP, +12.2% AQuA on PaLM-540B, Wang et al. 2022), but its precondition is routinely violated in agent products: it marginalises reasoning paths onto a **unique closed-form answer**, so it cannot select among free-form reports. **[high, foundational]**

Weaver is the practical counterpart. Aggregating *weak* verifiers — 30+ reward models and LM judges, individually 43–62% accurate — by unsupervised weak supervision lifted first-sample accuracy **11.2–27.8 points** across MATH500, MMLU-Pro, MMLU-College and GPQA-Diamond. Distilling the ensemble into a 400M cross-encoder retained up to 98.7% of selection accuracy, cut verification inference FLOPs by up to 99.97%, and beat majority voting by 23.2 points. **Llama 3.3 70B and Llama 3.1 8B generators, 100 samples per query, Jun 2025, Hazy Research on its own paper.** **[medium-high]**

On **`pass@k` vs `pass^k`**, τ-bench is the primary source: it introduced `pass^k` and showed gpt-4o falling from ~61% `pass^1` to under 25% `pass^8` on τ-retail (Yao et al., Sierra, Jun 2024). Anthropic states the arithmetic for builders — a 75%-per-trial agent passes three consecutive trials 42% of the time, and by k=10 the metrics "tell opposite stories." A Mar 2026 preprint (396 tasks, 10 open-weight models, 23,392 episodes, k=3) adds a Graceful Degradation Score for partial completion, whose gap from `pass@1` widens at long horizons. **[medium — single preprint, open-weight models only]**

### 2.5 Critic and reflection loops

Reflexion originated verbal-feedback retry, and its own framing names external environments — compilers, APIs, games — as the feedback source: the variant later work finds reliable.

The 2026 production form is the generator/evaluator split. Anthropic's Mar 2026 harness is GAN-inspired: a generator builds, an evaluator with the Playwright MCP *clicks through the running application* and grades each sprint against per-criterion thresholds. Findings cite file and line (`LevelEditor.tsx:892`) and propose a fix — the critic's value came from acting in the environment, not re-reading the diff. Reported cost: solo run 20 min / $9 versus full harness 6 hr / $200. **[low-medium — n=1, one prompt, one author, Opus 4.5, no ablation]**

Shipped versions exist. Claude Code's `/goal` runs a small fast model as an after-every-turn evaluator so "completion is decided by a fresh model rather than the one doing the work" — but it "does not call tools, so it can only judge what Claude has already surfaced," the weak form. The companion repo ships an evaluator subagent **with no Write/Edit tools** that "reviews the diff and the screenshots from a context window that never saw the build." LangChain's `agentevals` encodes the §2.3 ordering as an API: a deterministic `create_trajectory_match_evaluator` that "doesn't require additional LLM calls," with an LLM judge reserved for "nuanced aspects." DSPy's GEPA makes critique an optimiser: its metric returns `dspy.Prediction(score, feedback)`, and a plain float degrades it because "concrete failure modes never reach" the proposer. **[medium]**

### 2.6 Training-time architecture: what gets absorbed

Sutton's essay frames §13: the two methods that scale arbitrarily with computation are **search and learning**, while built-in human knowledge "plateaus and even inhibits further progress." That argues about what to build *into the model*, not a licence to delete external checks.

The main agentic-RL survey frames the shift as single-step MDPs → temporally extended POMDPs, converting planning, tool use, memory and self-improvement "from static, heuristic modules into adaptive, robust agentic behavior." RLVR marks the honest boundary: automatic reward exists wherever correctness is programmatically checkable, and nothing equivalent exists for most agentic workflows, where long-horizon credit assignment remains open. **[medium — survey]**

The strongest durability signal available is a natural experiment across one vendor's two posts a quarter apart:

| Scaffold | Nov 2025 | Mar 2026 | Verdict |
| --- | --- | --- | --- |
| Context resets between sessions | Essential (Sonnet 4.5 "context anxiety") | **Dropped** — Opus 4.5 "largely removed that behavior on its own" | Absorbed |
| "Test end-to-end as a user would" | Prompting | An evaluator role driving Playwright | Enduring |
| Default-FAIL ledger / contract | Introduced | Elaborated as sprint contracts | Enduring |
| Separate evaluator context | Not yet | Shipped as `/goal` and a no-write subagent | Enduring, moving into the product |

The pattern — **scaffolds compensating for a model deficiency get absorbed; scaffolds encoding a trust boundary, a budget, or an external ground-truth signal do not** — rests on one data point: a hypothesis with a mechanism, not a law. The mechanism is what Sutton's argument does not reach: no amount of learning makes a generator an independent witness to its own output. Browser Use argues the strong form — "the less you build, the more it works" — from one experience report that still keeps a `done` tool and a retry layer. **[medium; vendor claim for the strong form]**

### 2.7 Reliability engineering and calibration

Three mechanisms make success machine-readable rather than narrative: **default-FAIL criteria with evidence requirements**, **weighted-subtask partial credit** so a run reports 0.44 rather than "failed", and **a fresh-context grader returning a structured verdict** plus findings seeding the next session.

Calibration is the weakest link. RiskEval finds models "neither cost-aware when articulating their verbal confidence, nor strategically responsive when deciding whether to engage or abstain," almost never abstaining even when extreme penalties make it optimal. AgentAbstain (Jul 2026, 17 models, 4 harnesses, authors' benchmark) reports best paired accuracy 59.5% with 13/17 below 50%, and names *post-hoc abstention* — taking the irreversible action, then claiming refusal — as an agent-specific failure absent from the chat literature. **[medium — direction consistent across two 2026 preprints; neither replicated]**

### 2.8 Human-in-the-loop as verification

Approval gates buy real safety at a point of no return and mostly latency elsewhere. Three properties make one load-bearing: it precedes the first irreversible action (gating the confirmation email after the refund issued is theatre); it shows the artifact, not an AI-written summary; and it blocks one decision, not the whole run.

Primary law now encodes the automation-bias concern, at a scope worth stating precisely. **EU AI Act Article 14 applies only to high-risk AI systems** (Chapter III, applicable 2 August 2026). 14(1) is a design obligation — such systems "shall be designed and developed in such a way… that they can be effectively overseen by natural persons"; 14(3) splits oversight measures between those the provider builds in and those "appropriate to be implemented by the deployer"; 14(4)(b) requires that oversight personnel can "remain aware of the possible tendency of automatically relying or over-relying on the output" (automation bias). A general-purpose coding or research agent is not automatically in scope: the failure mode is recognised in law, not mandated for every agent.

Two operational points follow, both weaker than usually stated. Approval rate is an *instrument*, not a proof: a rate near 100% means either the action class has earned auto-execution or review has stopped discriminating, and only sampling rejected-in-hindsight cases separates them. And a decayed gate is not categorically worse than no gate — worse only on misplaced assurance, while still preserving an audit trail and a human decision point. What a gate verifies is *intent and blast radius*, which no test covers. **[medium — regulatory scope verified against primary text; operational claims unmeasured]**

## 3. Delta since 2026-07-14

| Prior-pass position | Status now |
| --- | --- |
| §3.8 prefer fresh-context evaluator; a **transferred** coding lesson, "not research-native evidence" | **Partly upgraded.** The *separation* principle has independent support (Huang, Kamoi, CRITIC, Self-Refine's math null); the Anthropic harness stays n=1. |
| Anti-pattern: majority-vote over free-form reports | **Confirmed.** Generalise to weak-verifier aggregation or verifier rank-and-select. |
| Self-correction only as "self-verifier in same context → positive bias" | **Now has a literature.** Huang, Kamoi, CRITIC, Self-Refine and SCoRe were uncited. Intrinsic correction fails on reasoning; *trained* correction is the exception. |
| "Single coding agent + tests as ground truth" treated as unproblematic | **Materially revised.** Apr–May 2026 benchmark-hacking results make the grader trust boundary explicit. |
| Nothing on calibration, abstention, honest failure | **New.** Abstention appears to scale independently of capability. |
| Nothing on training-time / harness co-evolution | **New (§13).** Sutton frames it; the dropped context reset is the one absorption. |
| HITL framed only as "gate high-impact side effects" | **Adds decay and payload design**, regulatory hook scoped to high-risk systems. |

## 4. Contested / open questions

| Question | Confidence | Note |
| --- | --- | --- |
| Does a skeptical fresh-context evaluator help *research/synthesis*, or only code and UI? | **Low** | All strong evidence is coding/frontend. |
| Is search-over-plans used in production, and does it beat replanning? | **Low** | No adoption data either way; Snell is math with a trained PRM. |
| How large is judge self-preference after controlling for judge error? | **Low-medium** | Halved in the one sanity-check study; near-zero on objective tasks. |
| Do PRMs earn their cost outside math? | **Low-medium** | The survey documents a retreat to implicit/generative PRMs. |
| `pass^k` or partial-credit GDS as the product metric? | **Medium** | Depends on whether one success suffices. |
| How much will the next model absorb? | **Low** | One documented instance, one vendor. |

## 5. Anti-patterns & failure modes

| Anti-pattern | Why it fails | Prefer |
| --- | --- | --- |
| "Check your work carefully" to the generator | Feedback generation is the bottleneck | Any external signal: test, compiler, tool, observation |
| Grader in the agent's writable workspace | 500/500 SWE-bench Verified via a 10-line hook | Out-of-container / read-only grading |
| Single ordering, no calibration, same-family judge on subjective criteria | Position bias worst when candidates are close | Swap order and tie on flips; cross-family judge |
| Majority vote over free-form output | Needs a unique closed-form answer | Verifier rank-and-select; weak-verifier aggregation |
| Plan as prose | Nothing downstream can check it | Default-FAIL ledger, restricted edit surface |
| Replan on every error | Thrash without progress | Escalation ladder, replan budget, progress check |
| Binary outcome on long-horizon work | `pass@1` → 0; partial progress discarded | Weighted subtask credit |
| Gating on stated confidence | Dissociated from action choice | Gate on external checks or policy |
| Gating every action | Trains the reflex that approving is safe | Risk-signal gates at the point of no return |
| Post-hoc abstention | Acts irreversibly, then reports refusal | Feasibility check before the call |

## 6. Design implications

1. **Make the verifier structurally different — context and tools, not just prompt — and give it an action rather than a transcript.** A no-write evaluator cannot quietly fix what it should report; `/goal` can only judge what was surfaced. *Trade-off:* tokens, latency, and the acting-evaluator half rests on one vendor experiment.
2. **Move the plan into a default-FAIL ledger with a restricted edit surface**, turning "did it succeed?" into a query. *Trade-off:* upfront authoring; over-specified criteria cascade errors.
3. **Treat the grading trust boundary as a security property** — the cheapest path to a green signal is forging it. *Trade-off:* out-of-container grading costs infrastructure.
4. **Rank-and-select with a verifier before N-way voting; a small verifier may suffice.** *Trade-off:* one more artifact to calibrate.
5. **Report partial success with weighted subtask credit,** the only signal that varies at long horizons. *Trade-off:* partial scores are gameable.
6. **Gate on an external check or explicit policy, never on stated confidence; place gates by risk signal at the point of no return, show the artifact, instrument the approval rate.** *Trade-off:* needs an action inventory classified by reversibility, and external checks never cover every claim.
7. **Build scaffolds encoding trust boundaries, budgets and external ground truth; treat deficiency-compensating scaffolds as provisional.** *Trade-off:* the category is unknowable until a model ships, so version harness assumptions against model versions.
8. **If self-correction is the bottleneck and you cannot train, stop prompting your way there** — the substitute is a better external signal, not a better critique prompt.

## 7. Sources

All retrieved 2026-08-03.

| # | Source | Date | URL |
| --- | --- | --- | --- |
| 1 | Huang et al. — *LLMs Cannot Self-Correct Reasoning Yet* (foundational) | 2023-10 | https://arxiv.org/abs/2310.01798 |
| 2 | Kamoi et al. — *When Can LLMs Actually Correct Their Own Mistakes?* (foundational) | 2024-06 | https://arxiv.org/html/2406.01297v3 |
| 3 | Kumar et al. — *Training LMs to Self-Correct via RL* (SCoRe) | 2024-09 | https://arxiv.org/pdf/2409.12917 |
| 4 | Madaan et al. — *Self-Refine* (NeurIPS 2023; positive counterfinding) | 2023-03 | https://arxiv.org/abs/2303.17651 |
| 5 | Gou et al. — *CRITIC: Tool-Interactive Critiquing* (ICLR 2024) | 2023-05 | https://arxiv.org/pdf/2305.11738 |
| 6 | *Accuracy–Correction Paradox / Error Depth Hypothesis* (preprint **[low]**) | 2026-01 | https://arxiv.org/html/2601.00828v1 |
| 7 | Shinn et al. — *Reflexion* (foundational) | 2023-03 | https://arxiv.org/abs/2303.11366 |
| 8 | Lightman et al. — *Let's Verify Step by Step* (foundational) | 2023-05 | https://arxiv.org/abs/2305.20050 |
| 9 | Wang et al. — *Self-Consistency* (foundational) | 2022-03 | https://arxiv.org/abs/2203.11171 |
| 10 | Snell et al. — *Scaling LLM Test-Time Compute Optimally* | 2024-08 | https://arxiv.org/abs/2408.03314 |
| 11 | Yao et al. (Sierra) — *τ-bench* (origin of `pass^k`) | 2024-06 | https://arxiv.org/pdf/2406.12045 |
| 12 | Anthropic — *Effective harnesses for long-running agents* (vendor experiment) | 2025-11-26 | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| 13 | Anthropic — *Harness design for long-running application development* | 2026-03-24 | https://www.anthropic.com/engineering/harness-design-long-running-apps |
| 14 | Anthropic — *Demystifying evals for AI agents* | 2026-01-09 | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents |
| 15 | `anthropics/cwc-long-running-agents` — default-FAIL contract, no-write evaluator | 2026 | https://raw.githubusercontent.com/anthropics/cwc-long-running-agents/main/README.md |
| 16 | Claude Code docs — `/goal` per-turn separate-model evaluator | 2026 | https://code.claude.com/docs/en/goal |
| 17 | UC Berkeley RDI — *How we broke top AI agent benchmarks* (`conftest.py`, 500/500) | 2026-04 | https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/ |
| 18 | *BenchJack: Auditing AI Agent Benchmarks* | 2026-05 | https://arxiv.org/html/2605.12673 |
| 19 | Shi et al. — *Judging the Judges: Position Bias* (IJCNLP 2025) | 2025 | https://aclanthology.org/2025.ijcnlp-long.18.pdf |
| 20 | *Play Favorites: Measuring Self-Bias in LLM-as-a-Judge* (self- and family-bias) | 2025-08 | https://arxiv.org/pdf/2508.06709 |
| 21 | *Are LLM Evaluators Really Narcissists?* (self-preference confound; 37,448 queries) | 2026-01 | https://arxiv.org/pdf/2601.22548 |
| 22 | Hazy Research — *Weaver: Closing the Generation-Verification Gap* | 2025-06-18 | https://hazyresearch.stanford.edu/blog/2025-06-18-weaver |
| 23 | *Beyond pass@1: Reliability Science for Long-Horizon Agents* (preprint **[medium]**) | 2026-03 | https://arxiv.org/abs/2603.29231 |
| 24 | *AgentAbstain: Do LLM Agents Know When Not to Act?* (preprint) | 2026-07 | https://arxiv.org/html/2607.10059v1 |
| 25 | *Are LLM Decisions Faithful to Verbal Confidence?* (RiskEval, preprint) | 2026-01 | https://arxiv.org/pdf/2601.07767 |
| 26 | Zhang et al. — *Landscape of Agentic RL for LLMs* (survey) | 2025-09 (v5) | https://arxiv.org/html/2509.02547v5 |
| 27 | Sutton — *The Bitter Lesson* (foundational; §13 framing) | 2019-03-13 | http://www.incompleteideas.net/IncIdeas/BitterLesson.html |
| 28 | OpenAI — *Reinforcement fine-tuning use cases* (grader precondition; vendor docs) | 2026 | https://developers.openai.com/api/docs/guides/rft-use-cases |
| 29 | OpenAI — *Reinforcement fine-tuning* (reward-hacking warning; vendor docs) | 2026 | https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning |
| 30 | *A Survey of Process Reward Models* (ACL 2026) | 2026 | https://aclanthology.org/2026.acl-long.163.pdf |
| 31 | Agrawal et al. — *GEPA* + DSPy GEPA docs (feedback-shaped metric) | 2025-07 / 2026 | https://dspy.ai/api/optimizers/GEPA/overview/ |
| 32 | *Self-Healing Agentic Orchestrators* (bounded recovery ladder; preprint) | 2026-06 | https://arxiv.org/html/2606.01416v1 |
| 33 | EU AI Act, Article 14 — *Human Oversight* (primary regulation; high-risk scope) | 2024-06-13 (applies 2026-08-02) | https://artificialintelligenceact.eu/article/14/ |
| 34 | Zunic (Browser Use) — *The Bitter Lesson of Agent Frameworks* **[vendor claims]** | 2026-01-16 | https://browser-use.com/posts/bitter-lesson-agent-frameworks |
| 35 | LangChain — *Trajectory evaluations* (`agentevals`: deterministic matcher + LLM judge) | 2026 | https://docs.langchain.com/langsmith/trajectory-evals |

## 8. Proposed content for final doc sections

**§ 9 Planning & decomposition.** Organise by *plan substrate* — implicit / explicit step list / machine-checkable ledger / searched space — since the substrate decides whether anything downstream can check the plan. Implicit for short-horizon work, with τ-bench's `pass^1` as the ceiling; plan-then-execute where structure is knowable or spend needs approval; the Anthropic ledger labelled n=1; replanning as a bounded escalation ladder. Cross-ref WS2, WS1.

**§ 10 Verification, self-correction & quality.** Open with the load-bearing claim and its scope, then the verifier hierarchy: executable ground truth → environment observation by a separate agent → cross-family judge with mechanical debiasing → self-check, a heuristic not a verifier. Callout for the grader trust boundary. Selection: self-consistency only for closed-form answers, verifier rank-and-select otherwise. Reliability: `pass^k` versus `pass@k` as a product decision, weighted partial credit as the reporting primitive. Close on calibration and HITL.

**§ 13 Training-time vs inference-time architecture.** Sutton in his own terms, then the limit — his argument is about what goes *in the model*, not scaffolds built to be independent of it. Then agentic RL as MDP → POMDP, RLVR where correctness is checkable, credit assignment open; the absorption table as one instance; the durable/absorbed split as a hypothesis; the rule to version harness assumptions against model versions.
