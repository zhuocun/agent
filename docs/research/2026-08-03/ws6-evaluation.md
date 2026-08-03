# WS6 — Evaluation & observability
**Scope:** Offline and online agent evaluation, benchmark validity, human evaluation, and tracing semantics (not runtime verification policy or production SLO ownership) | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS5 for verifiers as a runtime quality mechanism; WS7 for production monitoring, alerting, and SLOs

## 1. Executive summary

1. **[high] Descriptive — benchmark scores are system scores, not model scores.** Harness-Bench’s May 2026 fixed protocol produced a 23.8-point spread between NanoBot (76.2) and OpenClaw (52.4), averaged over the same 106 tasks and eight model backends [S13]. Agent, prompt, tools, budget, environment, and grader belong in every “benchmark receipt”: task/version, split, model, scaffold, attempts, date, reporter, and uncertainty.
2. **[high] Descriptive — benchmark validity is a first-order risk.** OpenAI’s July 2026 vendor audit estimates about 30% of SWE-bench Pro’s public tasks are broken [S3]. Independently, the peer-reviewed Agentic Benchmark Checklist (ABC) found outcome-validity flaws in seven of ten audited benchmarks and task-validity flaws in seven, including exploitable or false-positive grading in SWE-Lancer, τ-bench, WebArena, and SWE-bench Verified [S9].
3. **[high] Descriptive — the frontier moved toward dynamic, repaired environments.** GAIA2 adds asynchronous events and action-level verification; OSWorld 2.0 uses 108 workflows with 500 steps; MCP-Universe exercises real MCP servers. Terminal-Bench 2.1 replaced 2.0 after correcting 28/89 tasks, demonstrating that even audited container suites drift [S4,S8,S12,S15].
4. **[high] Normative — evaluate the product on a private, versioned task suite, not by importing a public leaderboard.** Public benchmarks are useful capability probes, but release gates should weight representative user tasks, state assertions, forbidden actions, reliability, cost, and latency. Tradeoff: private suites cost expert time and reduce public comparability, but resist contamination and measure the actual product.
5. **[high] Normative — score both outcome and trajectory.** Environment state or artifact correctness is the primary success signal; trajectory checks diagnose policy breaches, waste, and lucky outcomes. A single “golden path” is usually wrong because agents can legitimately take different routes.
6. **[high] Normative — reliability needs repeated trials.** Report pass^1, variance/confidence intervals, optimistic pass@k (at least one success), and strict pass^k (all k succeed). Mean success alone hides task-level flakiness; pass@k is appropriate only where retries are actually available and verified [S10].
7. **[high] Descriptive — OpenTelemetry’s GenAI conventions remain Development.** They moved to a dedicated repository and define `invoke_agent`, `invoke_workflow`, `chat`, and `execute_tool` shapes, including token attributes; content and tool arguments are opt-in because of sensitivity [S28]. Use them as a portable vocabulary, but pin a schema version and expect migration.

## 2. Findings

### 2.1 Benchmark landscape by capability axis

“Frontier” below is deliberately approximate. A number appears only with its harness, model version, date, and reporter; otherwise the row gives a qualitative position rather than combining incompatible submissions.

| Axis / benchmarks | What it measures and harness assumptions | Known flaws / present frontier |
| --- | --- | --- |
| **Software engineering — SWE-bench, Verified, Multimodal, Pro** | Repository patch must pass hidden tests. Official sets are 2,294 Full, 500 Verified, 517 Multimodal; Pro adds 1,865 longer tasks across public, held-out, and proprietary repositories [S1,S2]. | Contamination, solution hints, weak/strict tests, and scaffold confounding [S3,S9]. Two incompatible current receipts illustrate the problem: **Scale, accessed 2026-08-03:** SWE-Agent + `claude-4-5-sonnet`, uncapped, 250 turns, 730 tasks, 43.72% (initial) [S2]. **OpenAI, 2026-07-08:** an unnamed frontier system, model/scaffold/attempts undisclosed, 731-task public split, 80.3% [S3]. Neither is a sole “frontier” number; OpenAI also retracted its Pro recommendation after its audit. |
| **Software engineering — SWE-Lancer, Terminal-Bench, Aider polyglot, Commit0** | SWE-Lancer: 1,488 paid freelance implementation/manager tasks. Terminal-Bench: containerized terminal work. Aider: 225 Exercism edits in six languages. Commit0: rebuild 54 Python libraries from specifications [S4-S7]. | ABC showed SWE-Lancer tests could be overwritten to score 100% without solving tasks [S9]. Terminal-Bench **2.1** fixed 28/89 tasks (external drift, resource mismatch, misspecification); **Terminal-Bench team, 2026-05-06:** Codex CLI + GPT-5.3-Codex, attempts/CI unstated, 79.1% on 2.1 versus 73.3% on 2.0 [S4]. **Aider, GPT-5 (2025-08-07) high:** Aider diff harness, 225 tasks, 88.0% after up to two sequential repair attempts, $29.08 [S5]. This is not i.i.d. pass@2. |
| **General/tool — GAIA/GAIA2, AgentBench, τ-bench/τ²-bench, BFCL, MCP suites** | GAIA is exact-answer tool use; GAIA2/ARE uses 1,120 asynchronous scenarios, action verification, and three runs. AgentBench spans eight legacy environments. τ² gives user and agent shared-state tools and reports pass^k. BFCL v4 tests function calling; MCP-Universe uses 11 real servers [S8,S10-S12]. | Exact answers miss process quality; simulators add variance; BFCL’s unweighted mean is not outcome success; MCP services drift. ABC found τ-bench could award 38% to a do-nothing agent and 40% to database-dumping spam [S9]. **Meta/HF, Feb 2026:** GPT-5 in ARE, pass@1, ~42% [S8]. **Salesforce, Aug 2025:** GPT-5 native-FC track, 43.72% [S12]. |
| **Web/computer — WebArena, VisualWebArena, WebVoyager, Mind2Web, BrowseComp, OSWorld, AndroidWorld** | WebArena/VWA use hosted sites; WebVoyager live sites; Mind2Web largely offline action prediction; BrowseComp short-answer web research; OSWorld desktop workflows; AndroidWorld dynamically instantiates 116 tasks across 20 apps [S9,S14-S16]. | ABC found WebArena substring matching overestimated performance 5.2% and empty answers could satisfy some LLM-judged N/A tasks [S9]. Live sites drift; offline action matching is not autonomy. **OpenAI, Apr 2025:** benchmark-trained Deep Research, OpenAI browsing harness, 51.5% BrowseComp [S14]. **OSWorld authors, Jun 2026:** Claude Opus 4.8 max + batched tools, 500 steps, 20.6% binary / 54.8% partial [S15]. |
| **Research/knowledge — BrowseComp, HLE, DeepResearch-style** | HLE is a closed-answer expert knowledge exam, not an agent-process test; DeepResearch Bench uses 100 bilingual PhD-level tasks with RACE report rubrics and FACT citation checks [S18]. | DeepResearch Bench depends on judge/reference quality and mutable web evidence. **Benchmark authors, Jun 2025:** Gemini 2.5 Pro Deep Research, RACE judged by Gemini 2.5 Pro Preview, 48.88; OpenAI Deep Research 46.98 [S18]. Judge replacement can move the scale. |
| **ML/science autonomy — MLE-bench, RE-Bench, PaperBench** | MLE-bench runs 75 Kaggle competitions; RE-Bench has seven research-engineering environments and 71 expert attempts; PaperBench replicates 20 ICML papers using 8,316 rubric items [S19-S21]. | MLE’s board is frozen since 2026-04-24 while OpenAI develops fairer comparison, with known test-feedback concerns. Its historical leader **Famou-Agent 2.0 + Gemini-3-Pro-Preview, 24h, 2026-02-23** is 64.44%±1.18—not a current frontier claim [S19]. **OpenAI, 2025-04-02:** IterativeAgent + o1-high, 36h, three runs, PaperBench 26.0%±0.3; the same scaffold hurt Claude, showing prompt–model interaction [S21]. |
| **Long-horizon/economic — METR, GDPval, Vending-Bench 2** | METR fits success against human time; GDPval uses 1,320 occupational deliverables (220 open); Vending-Bench 2 simulates a year and scores ending cash [S22-S24]. | Human-time estimates and task composition drive METR; GDPval v1 is one-shot; cash is narrow and gameable. **METR, 2026-01-29:** Claude Opus 4.5 under Inspect, 228 tasks, p50 320 minutes [170,729] [S22]. **Andon Labs, accessed 2026-08-03:** five-run means put Claude Opus 5 first at $11,181.87±$2,094 and Opus 4.6 fifth at $8,017.59±$1,367; the cited page does not specify “high effort” [S24]. |
| **Safety/security — AgentHarm, AgentDojo, Cybench** | AgentHarm tests refusal and harmful multi-step completion over 110 base/440 augmented tasks. AgentDojo combines 97 useful tasks with 629 injection cases and reports benign utility, utility under attack, and attack success. Cybench has 40 professional CTFs plus guided subtasks [S25-S27]. | Synthetic harms and semantic judges can misgrade; AgentDojo has an incomplete attack×defense matrix and explicitly is not one leaderboard; CTF performance is narrower than real defensive work. Cybench documents an answer-leaking harness incident that inflated two models—an unusually concrete warning about evaluator integrity [S27]. |

### 2.2 Why agent numbers become untrustworthy

- **[high] Contamination and gaming:** public prompts, gold patches, and traces become training data. BrowseComp discloses benchmark-specific training; ABC demonstrates executable shortcuts, not hypothetical leakage [S9,S14]. Private canaries reduce this risk but reduce reproducibility.
- **[high] Harness–model confounding:** Harness-Bench measures a 23.8-point harness spread; METR found GPT-4o/o3 changed significantly after Vivaria→Inspect [S13,S22].
- **[high] Task/grader defects:** SWE-bench Pro’s 27.4–34.1% broken estimates include contradictory tests/prompts [S3]; ABC documents false-positive graders across four requested suites [S9]; Terminal-Bench changed 28/89 tasks [S4]; Cybench reports leaked-answer inflation [S27].
- **[high] Non-determinism:** single runs obscure simulator paths, tool outages, and sampling. pass@k rises with retries; pass^k falls and better reflects unattended reliability [S10].
- **[medium] Cost-blind saturation:** unrestricted turns, reasoning effort, parallel samples, and best-of-N can purchase score. Report USD, tokens, wall time, tool calls, retries, and success-per-dollar alongside quality.
- **[medium] Judge error:** LLM judges have position, style, verbosity, and self-family biases. They need blinded ordering, evidence-backed verdicts, abstention, and periodic human recalibration; agreement alone can hide systematic score shifts.

### 2.3 Evaluating one’s own agent

**[high] Normative — recommended evaluation stack:**

1. Build a private capability matrix from real intents: routine, hard, adversarial, ambiguous/clarification-required, tool failure, cancellation/resume, and budget exhaustion. Keep a frozen release set, rotating canaries, and a failure-derived regression set. Tradeoff: frozen sets support trend lines; rotating sets resist overfitting.
2. Define each case as `(initial state, user goal, allowed/forbidden effects, acceptable final states, rubric, budget)`. Use exact state/artifact graders first. Store a *golden trajectory envelope*—required/forbidden calls and partial-order constraints—not one exact path.
3. Grade outcome and trajectory separately: task success; policy/safety; factual/citation quality; recovery quality; unnecessary actions; cost; p50/p95 latency; time-to-first-useful-event; tokens; tool failures; and human interventions.
4. Run deterministic unit/contract tests on every change, a small live-model smoke suite in PR CI, and multi-seed statistical suites nightly/pre-release. Pin model snapshot, prompts, tools, environment image, judge, and scorer versions. Gate on confidence intervals and per-slice regressions, not only aggregate means.
5. Report pass^1, pass@k only where verified retries are a product feature, pass^k for consistency, task-level variance, failure clustering, and budget-normalized quality. Preserve all failed trajectories.
6. For open outputs, use explicit dimension rubrics and an independent judge; require evidence and `unknown`. Anthropic supports deterministic graders where possible and human-calibrated model graders where needed [S29]; OpenAI recommends measuring judge TPR/TNR on held-out SME labels [S30].
7. Online, randomize at user/thread level; compare completion, correction/retry, escalation, abandonment, user edits, delayed task outcome, latency, and cost. Thumbs are weak preference data unless paired with exposure and selection-bias analysis. Promote sampled failures and disagreements into the offline suite.

**[high] Normative — human-evaluation protocol:** recruit both domain experts (correctness/safety) and representative users (usefulness/taste); train them on anchored examples; blind model/harness identity and randomize pair order; permit tie/abstain; double-label a stratified sample with oversampling of critical and judge-disagreement cases; preserve pre-adjudication labels; report per-dimension agreement, Cohen’s κ/Krippendorff’s α, and uncertainty—not only consensus. AgentProcessBench demonstrates the standard: two expert labels per trajectory, 89.1% raw agreement and κ=0.767 before discussion [S17]. Periodically compare automated judges with these labels and delayed user outcomes; preference data is not a substitute for objective state checks.

### 2.4 Tracing and observability semantics

**[high] Descriptive:** OTel GenAI is Development and now lives in `semantic-conventions-genai` [S28]. A portable trace should be:

`invoke_workflow` (whole run) → `invoke_agent` (lead/worker/turn) → `plan` / `chat` / `retrieval` / `execute_tool`.

**[high] Normative:** record stable IDs (`trace`, run, conversation, user pseudonym, parent worker), agent/workflow/prompt/tool-schema versions, requested and returned model/provider, experiment arm, start/end/status/error type, retries, fan-out/depth, stop reason, input/output/cache/reasoning tokens, first-token and total latency, tool call ID/name/type, budget reserved/actual, artifact hashes, and later evaluator/human labels. Tool arguments/results and prompt/output content should be allowlisted, redacted, access-controlled, and sampled; metadata-only should be the default. This reduces debugging richness but avoids turning the trace store into a sensitive-data replica.

**[medium] Vendor-claimed capabilities:** LangSmith offers exact/subset/superset trajectory matching plus LLM trajectory judges and offline/online evaluation [S31]; Braintrust offers immutable experiments, CI and asynchronous production scoring [S32]; Langfuse is self-hostable with OTel traces, graph/session views, datasets, managed judges, and annotation queues [S33]; Phoenix accepts OTLP/OpenInference and supports span/trace evaluation, datasets, replay, and human labels [S34]; Weave renders OTel `invoke_agent`/`execute_tool`, versions prompts/data/models, and reuses scorers for monitoring [S35]. Product choice should follow data residency, OTel portability, evaluator reproducibility, and query/retention needs—not feature-checklist marketing.

## 3. Delta since 2026-07-14

- **[high]** The prior pass correctly marked OTel GenAI as Development and recommended a workflow→agent→tool span tree. Since then, the conventions’ dedicated-repository move is explicit; the implementation should pin a schema revision rather than assuming core-semconv versioning [S28].
- **[high]** The prior pass treated benchmark validity generically. ABC now supplies peer-reviewed, non-vendor evidence of flaws in SWE-Lancer, τ-bench, WebArena, and SWE-bench Verified; OpenAI’s later Pro audit is convergent vendor evidence [S3,S9].
- **[high]** Harness-Bench quantifies a 23.8-point harness effect; GAIA2, OSWorld 2.0, MCP-Universe, and METR TH1.1 add dynamic state, real protocols, and distribution sensitivity [S8,S12,S13,S15,S22].
- **[high]** Terminal-Bench 2.1’s 28/89 corrections supersede the 2.0 view and show why benchmark version belongs in every receipt [S4].
- **[medium]** The earlier “about 20 queries” guidance remains appropriate for early large-effect iterations, but mature release decisions need repeated runs, slice-level confidence intervals, human-calibrated judges, private canaries, and cost/latency gates [S29].
- **[medium]** Tracing vendors increasingly ingest OTel, but semantic rendering still differs; raw OTLP exportability does not guarantee evaluator or dataset portability [S31-S35].

## 4. Contested / open questions

- **[medium]** How much process scoring is desirable? It catches unsafe/wasteful routes, but can penalize novel valid strategies and teach agents to imitate the rubric.
- **[medium]** How should independent and vendor audits be reconciled? ABC already supplies peer-reviewed non-vendor confirmation of broad validity failures [S9], while OpenAI adds deeper Pro-specific review [S3]. The open work is publishing corrected/versioned splits and re-running systems—not waiting for first independent evidence.
- **[medium]** When do automated scores stop tracking user value? Likely when tasks become subjective, collaborative, preference-heavy, or delayed-outcome; pairwise human evaluation then has higher validity but lower throughput.
- **[low]** No accepted benchmark yet measures multi-day work with interruptions, collaboration quality, aesthetic taste, maintainability months later, calibrated clarification, graceful recovery, or organizational trust. Current “long-horizon” suites are bounded simulations or hours-long workflows.

## 5. Anti-patterns & failure modes

- Publishing a bare model percentage without a harness receipt or uncertainty [S4,S13].
- Tuning a scaffold per benchmark, then calling the result general capability [S13,S21].
- Using pass@k to imply single-attempt reliability, or using one stochastic run [S10].
- Treating tests, an LLM judge, or ending cash as ground truth without auditing the grader [S3,S9,S24,S27].
- Requiring one golden path where several safe paths exist; or grading only outcomes when side effects matter [S9,S31].
- Letting the generator self-grade, silently changing judges, or hiding disagreement/class balance [S17,S29,S30].
- Logging sensitive content by default, or only final text and no causal trace [S28].
- Hiding tail latency, spend, retries, or safety-slice regressions behind an aggregate [S4,S22,S24].

## 6. Design implications

1. **[high] Normative:** make `eval_receipt` first-class: git SHA, suite/split/revision, image, agent/prompt/tool/model versions, settings, budgets, seeds, grader/judge, cost, uncertainty, and trace links [S4,S13]. Rationale: separate system change from benchmark noise; tradeoff: storage and discipline.
2. **[high] Normative:** gate on a small private suite plus deterministic side-effect checks; run larger repeated suites asynchronously [S9,S29]. Rationale: fast feedback without pretending n≈20 detects small regressions.
3. **[high] Normative:** persist outcome, trajectory, economics, and reliability separately [S9,S10]. A dashboard composite is possible, but hides causes and contestable weights.
4. **[high] Normative:** emit version-pinned OTel spans and export raw OTLP; put prompts/results behind stricter access and retention [S28,S33-S35].
5. **[medium] Normative:** monthly, double-label a stratified sample, preserve raw labels, measure κ/α and judge TPR/TNR by slice, and adjudicate disagreements [S17,S30]. Tradeoff: expert cost, justified by avoiding scalable grader drift.

## 7. Sources

| # | Source (primary unless labeled) | Date / relevance |
| --- | --- | --- |
| S1 | [SWE-bench official leaderboards](https://www.swebench.com/) | live, accessed 2026-08-03 |
| S2 | [Scale — SWE-bench Pro official page](https://scaleapi.github.io/SWE-bench_Pro-os/) | 2025; live harness/results |
| S3 | [OpenAI — Separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/) | 2026-07-08; vendor audit |
| S4 | [Terminal-Bench team — Terminal-Bench 2.1](https://tbench.ai/news/terminal-bench-2-1) | 2026-05-06; 28/89-task correction |
| S5 | [Aider official polyglot leaderboard](https://aider.chat/docs/leaderboards/) | live |
| S6 | [OpenAI — SWE-Lancer](https://openai.com/index/swe-lancer/) | 2025-02-18; benchmark release |
| S7 | [Commit0 official site](https://commit-0.github.io/) | ICLR 2025; foundational |
| S8 | [Meta/HF — GAIA2 paper](https://arxiv.org/abs/2602.11964) | ICLR 2026 |
| S9 | [Zhu et al. — Agentic Benchmark Checklist](https://arxiv.org/html/2507.02825v5) | NeurIPS 2025; peer-reviewed independent audit |
| S10 | [Sierra — τ²-bench paper](https://arxiv.org/abs/2506.07982) | 2025-06; dual-control/pass^k |
| S11 | [Berkeley Function Calling Leaderboard v4](https://gorilla.cs.berkeley.edu/leaderboard) | updated 2026-04-12 |
| S12 | [Salesforce — MCP-Universe documentation](https://mcp-universe.github.io/usage.html) | 2025-08 |
| S13 | [Harness-Bench](https://arxiv.org/html/2605.27922) | 2026-05-27; 106 tasks/eight backends |
| S14 | [OpenAI — BrowseComp](https://openai.com/index/browsecomp) | 2025-04 |
| S15 | [OSWorld 2.0 official site](https://osworld-v2.xlang.ai/) | 2026-06 |
| S16 | [Google DeepMind — AndroidWorld](https://google-research.github.io/android_world/) | ICLR 2025; foundational |
| S17 | [AgentProcessBench](https://arxiv.org/html/2603.14465v2) | 2026-03; human process annotations |
| S18 | [DeepResearch Bench official site](https://deepresearch-bench.github.io/) | 2025-06; live evaluator |
| S19 | [OpenAI — MLE-bench repository/leaderboard](https://github.com/openai/mle-bench) | frozen 2026-04-24 |
| S20 | [METR — RE-Bench report](https://metr.org/blog/2024-11-22-evaluating-r-d-capabilities-of-llms/) | 2024-11; foundational, human baseline |
| S21 | [OpenAI — PaperBench repository/leaderboard](https://github.com/openai/frontier-evals/tree/main/project/paperbench) | 2025-04 |
| S22 | [METR — Time Horizon 1.1](https://metr.org/blog/2026-1-29-time-horizon-1-1/) | 2026-01-29 |
| S23 | [OpenAI — GDPval](https://openai.com/index/gdpval/) | 2025-10; vendor benchmark |
| S24 | [Andon Labs — Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) | 2025-11; live |
| S25 | [UK AISI et al. — AgentHarm](https://proceedings.iclr.cc/paper_files/paper/2025/hash/c493d23af93118975cdbc32cbe7323f5-Abstract-Conference.html) | ICLR 2025 |
| S26 | [ETH Zurich/Invariant — AgentDojo](https://agentdojo.spylab.ai/) | NeurIPS 2024; foundational/live |
| S27 | [Stanford — Cybench official site](https://cybench.github.io/) | ICLR 2025; live |
| S28 | [OpenTelemetry — GenAI span semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md) | Development, accessed 2026-08-03 |
| S29 | [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | 2026; vendor methodology |
| S30 | [OpenAI — Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices) | accessed 2026-08-03; vendor methodology |
| S31 | [LangSmith — trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals) | live vendor docs/claims |
| S32 | [Braintrust — evaluation](https://www.braintrust.dev/docs/evaluate) | live vendor docs/claims |
| S33 | [Langfuse documentation](https://langfuse.com/docs) | live vendor docs/claims |
| S34 | [Arize Phoenix documentation](https://arize.com/docs/phoenix) | live vendor docs/claims |
| S35 | [W&B Weave documentation](https://docs.wandb.ai/weave/concepts/what-is-weave) | live vendor docs/claims |

## 8. Proposed content for final doc sections

### Section 12 — Evaluation & observability

Adopt an eval-driven release loop: production failures → expert-labeled private cases → deterministic outcome graders plus human-calibrated rubric judges → repeated offline experiments → CI/release gates → sampled online evaluation [S29,S30]. Treat every result as an **agent-system** measurement and attach a receipt with suite/split, environment, model, scaffold, budgets, attempts, grader, cost, date, reporter, and uncertainty [S4,S13].

Use four score families without collapsing them: **outcome** (state/artifact correctness), **process** (required/forbidden actions and recovery), **economics** (tokens, USD, tool calls, p50/p95 latency), and **reliability** (pass^1, pass@k where retries are real, pass^k, confidence intervals) [S9,S10]. Public benchmarks are external probes, not release gates.

Trace each run as `invoke_workflow → invoke_agent → chat/retrieval/execute_tool`, following pinned OpenTelemetry GenAI Development conventions [S28]. Record versions, IDs, status/errors, model/provider, token classes, latency, budgets, fan-out, tool metadata, artifacts, and labels. Capture content only through redacted opt-in policies.

Require human calibration for open-ended judging: blinded double labels, anchored rubrics, tie/abstain, evidence-bearing verdicts, κ/α plus TPR/TNR, preserved disagreements, and recalibration after judge/rubric/distribution changes [S17,S30]. Defer runtime verifier behavior to WS5 and production SLOs to WS7.
