# WS6 — Evaluation & observability
**Scope:** Offline and online agent evaluation, benchmark validity, human evaluation, and tracing semantics (not runtime verification policy or production SLO ownership) | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS5 for verifiers as a runtime quality mechanism; WS7 for production monitoring, alerting, and SLOs

## 1. Executive summary

1. **[high] Descriptive — benchmark scores are system scores, not model scores.** Agent, prompt, tools, action budget, retry policy, environment image, grader, and inference effort can move results as much as the base model. Every reported number should therefore carry a “benchmark receipt”: task/version, split, model version, scaffold, budget, attempts, date, and reporter.
2. **[high] Descriptive — benchmark validity is now a first-order risk.** OpenAI’s July 2026 audit estimates about 30% of SWE-bench Pro’s public tasks are broken (27.4% by its agent pipeline; 34.1% by five-engineer review), after previously withdrawing support for Verified. This is vendor-produced evidence, but its method and examples are public; it invalidates unqualified leaderboard comparisons even when scores rise rapidly on the same split [S3].
3. **[high] Descriptive — the frontier moved from short, static tasks toward dynamic environments.** GAIA2 adds asynchronous events and action-level verification; OSWorld 2.0 uses 108 workflows with a 500-step budget; Terminal-Bench 2.0 audits container trajectories; MCP-Universe exercises real MCP servers. These expose state drift and recovery failures hidden by final-answer benchmarks [S4,S8,S12,S15].
4. **[high] Normative — evaluate the product on a private, versioned task suite, not by importing a public leaderboard.** Public benchmarks are useful capability probes, but release gates should weight representative user tasks, state assertions, forbidden actions, reliability, cost, and latency. Tradeoff: private suites cost expert time and reduce public comparability, but resist contamination and measure the actual product.
5. **[high] Normative — score both outcome and trajectory.** Environment state or artifact correctness is the primary success signal; trajectory checks diagnose policy breaches, waste, and lucky outcomes. A single “golden path” is usually wrong because agents can legitimately take different routes.
6. **[high] Normative — reliability needs repeated trials.** Report pass^1, variance/confidence intervals, optimistic pass@k (at least one success), and strict pass^k (all k succeed). Mean success alone hides task-level flakiness; pass@k is appropriate only where retries are actually available and verified [S10].
7. **[high] Descriptive — OpenTelemetry’s GenAI conventions remain Development.** They moved to a dedicated repository and define `invoke_agent`, `invoke_workflow`, `chat`, and `execute_tool` shapes, including token attributes; content and tool arguments are opt-in because of sensitivity [S28]. Use them as a portable vocabulary, but pin a schema version and expect migration.

## 2. Findings

### 2.1 Benchmark landscape by capability axis

“Frontier” below is deliberately approximate. A number appears only with its harness, model version, date, and reporter; otherwise the row gives a qualitative position rather than combining incompatible submissions.

| Axis / benchmarks | What it measures and harness assumptions | Known flaws / present frontier |
| --- | --- | --- |
| **Software engineering — SWE-bench, Verified, Multimodal, Pro** | Repository patch must pass hidden tests. Official sets are 2,294 Full, 500 Verified, 517 Multimodal; Pro adds 1,865 longer tasks across public, held-out, and proprietary repositories [S1,S2]. | Public-repo contamination, solution hints, strict/underspecified/low-coverage tests, and scaffold confounding. **Scale, current 2026-08-03:** SWE-Agent + `claude-4-5-sonnet`, uncapped cost, 250 turns, 730 public tasks, 43.72% resolved (initial run) [S2]. Do not treat this as clean capability evidence: OpenAI’s 2026 audit retracts its Pro recommendation [S3]. |
| **Software engineering — SWE-Lancer, Terminal-Bench, Aider polyglot, Commit0** | SWE-Lancer: 1,488 paid freelance implementation/manager tasks, Docker and end-to-end tests. Terminal-Bench 2.0: 89 containerized terminal tasks, fixed resources/timeouts, five runs. Aider: 225 Exercism edits in six languages, two attempts and format/cost tracking. Commit0: rebuild 54 Python libraries from specifications with tests/lint/types [S4-S7]. | They measure different objects: economic task completion, terminal work, small code editing, and library synthesis. **Terminal-Bench team, 2026-05-14:** audited NexAU-AHE + GPT-5.5, `terminal-bench@2.0`, k=5, 84.7%±2.1 [S4]. **Aider, GPT-5 (2025-08-07) high effort:** Aider CLI diff harness, 225 tasks, pass@2 88.0%, $29.08 [S5]. Neither transfers directly to maintainability or unfamiliar product code. |
| **General/tool — GAIA/GAIA2, AgentBench, τ-bench/τ²-bench, BFCL, MCP suites** | GAIA is exact-answer research/tool use; GAIA2/ARE uses 1,120 smartphone-like asynchronous scenarios, causal action verification, and three runs. AgentBench spans eight legacy environments. τ² makes both user and agent act on shared state and reports pass^k. BFCL v4 tests native/prompt function calling across multi-turn, web, memory, and formatting. MCP-Universe uses 11 real servers across six domains [S8-S12]. | Exact answers miss process quality; simulated-user behavior adds variance; BFCL’s unweighted subcategory mean is not task completion; real MCP services drift. **Meta/HF, ICLR 2026:** GPT-5 in ARE, pass@1, about 42% overall [S8]. **Salesforce, Aug 2025:** GPT-5 native function-call track, 43.72% success [S12]. These are different harnesses, not a model ranking. |
| **Web/computer — WebArena, VisualWebArena, WebVoyager, Mind2Web, BrowseComp, OSWorld, AndroidWorld** | WebArena/VWA use reproducible hosted sites and functional validators; WebVoyager uses live sites; Mind2Web is largely offline demonstration/action prediction; BrowseComp uses 1,266 obscure short-answer web questions; OSWorld 2.0 uses desktop workflows; AndroidWorld dynamically instantiates 116 tasks across 20 apps [S13-S16]. | Hosted sites age; live sites drift; offline action matching is not end-to-end autonomy; short-answer browsing ignores report quality. **OpenAI, Apr 2025:** benchmark-trained Deep Research, OpenAI browsing harness, 51.5% BrowseComp [S14]—explicit training makes contamination/generalization a concern. **OSWorld authors, Jun 2026:** Claude Opus 4.8 max thinking + batched tools, 500 steps, 20.6% binary / 54.8% partial [S15]. OSWorld 1.x and 2.0 scores are not comparable. |
| **Research/knowledge — BrowseComp, HLE, DeepResearch-style** | HLE is a 2,500-question expert, multimodal, closed-answer knowledge exam; DeepResearch Bench uses 100 bilingual PhD-level tasks with RACE report rubrics and FACT citation checks [S17,S18]. | HLE mostly measures answer knowledge/calibration, not research operations. DeepResearch Bench depends on judge/reference quality and mutable web evidence. **Benchmark authors, Jun 2025:** Gemini 2.5 Pro Deep Research, RACE judged by Gemini 2.5 Pro Preview, 48.88 overall; OpenAI Deep Research 46.98 [S18]. Judge replacement can move the scale. |
| **ML/science autonomy — MLE-bench, RE-Bench, PaperBench** | MLE-bench runs 75 Kaggle competitions against private leaderboards; RE-Bench has seven open-ended research-engineering environments and 71 expert attempts; PaperBench replicates 20 ICML papers using 8,316 rubric items and an LLM judge [S19-S21]. | Compute budget and scaffold dominate; Kaggle history can contaminate; RE-Bench has tiny task n; PaperBench’s judge F1 was 0.83 and prompts changed model rankings. **OpenAI leaderboard, 2026-02-23:** Famou-Agent 2.0 + Gemini-3-Pro-Preview, 24h, 64.44% medal rate [S19]. **OpenAI, 2025-04-02:** IterativeAgent + o1-high, 36h, three runs, 26.0% PaperBench [S21]. |
| **Long-horizon/economic — METR, GDPval, Vending-Bench 2** | METR fits success against human completion time; GDPval uses 1,320 expert-created occupational deliverables (220 open); Vending-Bench 2 simulates a year of business decisions and scores ending cash [S22-S24]. | Human-time estimates and task composition drive METR; GDPval v1 is one-shot rather than interactive; ending cash is a narrow, gameable proxy. **METR TH1.1, 2026-01-29:** Claude Opus 4.5 under Inspect on 228 tasks, p50 horizon 320 minutes [170,729] [S22]. **Anthropic vendor claim, Feb 2026:** Opus 4.6 high effort, Vending context manager, $8,017.59 final balance [S24]; do not compare without repeated-run variance. |
| **Safety/security — AgentHarm, AgentDojo, Cybench** | AgentHarm tests refusal and harmful multi-step completion over 110 base/440 augmented tasks. AgentDojo combines 97 useful tasks with 629 injection cases and reports benign utility, utility under attack, and attack success. Cybench has 40 professional CTFs plus guided subtasks [S25-S27]. | Synthetic harms and semantic judges can misgrade; AgentDojo has an incomplete attack×defense matrix and explicitly is not one leaderboard; CTF performance is narrower than real defensive work. Cybench documents an answer-leaking harness incident that inflated two models—an unusually concrete warning about evaluator integrity [S27]. |

### 2.2 Why agent numbers become untrustworthy

- **[high] Contamination and gaming:** public prompts, repositories, gold patches, and leaderboard traces become training data. Benchmark-specific training is disclosed for BrowseComp Deep Research [S14]. Private/canary sets reduce this risk but reduce reproducibility.
- **[high] Harness–model confounding:** METR found statistically different performance for GPT-4o and o3 after moving Vivaria→Inspect, despite nominally measuring the same tasks [S22]. Terminal-Bench’s top rows are custom systems, not bare models [S4].
- **[high] Task/grader defects:** SWE-bench Pro’s 27.4–34.1% broken estimates include contradictory tests and prompts [S3]; Cybench reports a leaked answer through an evaluation fork [S27].
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
6. For open outputs, use explicit dimension rubrics and a strong independent judge; require cited evidence and `unknown`. Calibrate against blinded SME labels with TPR/TNR, Cohen’s κ or Krippendorff’s α, and inspect disagreements. Recalibrate after judge, rubric, or traffic-distribution changes [S29,S30].
7. Online, randomize at user/thread level; compare completion, correction/retry, escalation, abandonment, user edits, delayed task outcome, latency, and cost. Thumbs are weak preference data unless paired with exposure and selection-bias analysis. Promote sampled failures and disagreements into the offline suite.

### 2.4 Tracing and observability semantics

**[high] Descriptive:** OTel GenAI is Development and now lives in `semantic-conventions-genai` [S28]. A portable trace should be:

`invoke_workflow` (whole run) → `invoke_agent` (lead/worker/turn) → `plan` / `chat` / `retrieval` / `execute_tool`.

**[high] Normative:** record stable IDs (`trace`, run, conversation, user pseudonym, parent worker), agent/workflow/prompt/tool-schema versions, requested and returned model/provider, experiment arm, start/end/status/error type, retries, fan-out/depth, stop reason, input/output/cache/reasoning tokens, first-token and total latency, tool call ID/name/type, budget reserved/actual, artifact hashes, and later evaluator/human labels. Tool arguments/results and prompt/output content should be allowlisted, redacted, access-controlled, and sampled; metadata-only should be the default. This reduces debugging richness but avoids turning the trace store into a sensitive-data replica.

**[medium] Vendor-claimed capabilities:** LangSmith offers exact/subset/superset trajectory matching plus LLM trajectory judges and offline/online evaluation [S31]; Braintrust offers immutable experiments, CI and asynchronous production scoring [S32]; Langfuse is self-hostable with OTel traces, graph/session views, datasets, managed judges, and annotation queues [S33]; Phoenix accepts OTLP/OpenInference and supports span/trace evaluation, datasets, replay, and human labels [S34]; Weave renders OTel `invoke_agent`/`execute_tool`, versions prompts/data/models, and reuses scorers for monitoring [S35]. Product choice should follow data residency, OTel portability, evaluator reproducibility, and query/retention needs—not feature-checklist marketing.

## 3. Delta since 2026-07-14

- **[high]** The prior pass correctly marked OTel GenAI as Development and recommended a workflow→agent→tool span tree. Since then, the conventions’ dedicated-repository move is explicit; the implementation should pin a schema revision rather than assuming core-semconv versioning [S28].
- **[high]** The prior pass treated SWE-style evaluation generically. The July 2026 SWE-bench Pro audit is a major negative update: even a supposedly contamination-resistant successor has roughly 30% broken tasks, so public coding benchmarks cannot serve as release gates [S3].
- **[high]** GAIA2, OSWorld 2.0, Terminal-Bench 2.0, MCP-Universe, and METR TH1.1 make asynchronous state, long workflows, real protocols, repeated trials, and task-distribution sensitivity much more visible [S4,S8,S12,S15,S22].
- **[medium]** The earlier “about 20 queries” guidance remains appropriate for early large-effect iterations, but mature release decisions need repeated runs, slice-level confidence intervals, human-calibrated judges, private canaries, and cost/latency gates [S29].
- **[medium]** Tracing vendors increasingly ingest OTel, but semantic rendering still differs; raw OTLP exportability does not guarantee evaluator or dataset portability [S31-S35].

## 4. Contested / open questions

- **[medium]** How much process scoring is desirable? It catches unsafe/wasteful routes, but can penalize novel valid strategies and teach agents to imitate the rubric.
- **[medium]** Can benchmark auditors be neutral when a vendor’s model benefits from discrediting a benchmark? OpenAI’s audit is detailed, but independent replication and corrected splits are still needed [S3].
- **[medium]** When do automated scores stop tracking user value? Likely when tasks become subjective, collaborative, preference-heavy, or delayed-outcome; pairwise human evaluation then has higher validity but lower throughput.
- **[low]** No accepted benchmark yet measures multi-day work with interruptions, collaboration quality, aesthetic taste, maintainability months later, calibrated clarification, graceful recovery, or organizational trust. Current “long-horizon” suites are bounded simulations or hours-long workflows.

## 5. Anti-patterns & failure modes

- Publishing a bare model percentage without scaffold, split, attempts, date, reporter, cost, and confidence interval.
- Tuning prompts/scaffolds per public benchmark, then calling the result general capability.
- Using pass@k to imply single-attempt production reliability, or using only one stochastic run.
- Treating a unit-test pass, LLM-judge score, or final bank balance as ground truth without auditing the grader.
- Requiring an exact golden trajectory where several safe paths exist; conversely, grading only the final answer when side effects matter.
- Letting the generator self-grade, changing judge versions silently, or reporting judge agreement without class balance and disagreement analysis.
- Logging complete prompts, credentials, tool results, and user data by default; or logging only final text and losing the causal trace.
- Optimizing aggregate quality while hiding tail latency, spend, retries, tool errors, or regressions in safety-critical slices.

## 6. Design implications

1. **[high] Normative:** make `eval_receipt` a first-class artifact containing git SHA, suite/split, task revision, environment image, agent/prompt/tool versions, model snapshot, inference settings, budgets, seeds, grader, judge, cost, and trace links. Rationale: it separates system change from benchmark noise; tradeoff: more storage and operational discipline.
2. **[high] Normative:** gate releases on a small private suite plus deterministic safety/side-effect checks; run larger repeated suites asynchronously. Rationale: fast CI feedback without pretending n≈20 detects small regressions.
3. **[high] Normative:** persist outcome, trajectory, economics, and reliability as separate dimensions; never collapse them into one score for engineering decisions. A composite can support dashboards, but it hides the cause and embeds contestable weights.
4. **[high] Normative:** emit OTel-shaped traces at orchestration boundaries and add domain attributes under a versioned namespace. Export raw OTLP to avoid backend lock-in; keep prompts/results behind stricter retention and access controls.
5. **[medium] Normative:** establish a monthly human calibration panel: double-label a stratified sample, adjudicate disagreements, measure κ/α and judge TPR/TNR by slice, then revise the rubric or judge. Tradeoff: expert cost, justified by avoiding scalable grader drift.

## 7. Sources

| # | Source (primary unless labeled) | Date / relevance |
| --- | --- | --- |
| S1 | [SWE-bench official leaderboards](https://www.swebench.com/) | live, accessed 2026-08-03 |
| S2 | [Scale — SWE-bench Pro official page](https://scaleapi.github.io/SWE-bench_Pro-os/) | 2025; live harness/results |
| S3 | [OpenAI — Separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/) | 2026-07-08; vendor audit |
| S4 | [Terminal-Bench 2.0 official leaderboard](https://www.tbench.ai/leaderboard/terminal-bench/2.0) | live; audited submissions |
| S5 | [Aider official polyglot leaderboard](https://aider.chat/docs/leaderboards/) | live |
| S6 | [OpenAI — SWE-Lancer](https://openai.com/index/swe-lancer/) | 2025-02-18; benchmark release |
| S7 | [Commit0 official site](https://commit-0.github.io/) | ICLR 2025; foundational |
| S8 | [Meta/HF — GAIA2 paper](https://arxiv.org/abs/2602.11964) | ICLR 2026 |
| S9 | [THUDM — AgentBench repository](https://github.com/THUDM/AgentBench/) | ICLR 2024; foundational |
| S10 | [Sierra — τ²-bench paper](https://arxiv.org/abs/2506.07982) | 2025-06; dual-control/pass^k |
| S11 | [Berkeley Function Calling Leaderboard v4](https://gorilla.cs.berkeley.edu/leaderboard) | updated 2026-04-12 |
| S12 | [Salesforce — MCP-Universe documentation](https://mcp-universe.github.io/usage.html) | 2025-08 |
| S13 | [WebArena canonical repository](https://github.com/web-arena-x/webarena) | foundational; maintained environment |
| S14 | [OpenAI — BrowseComp](https://openai.com/index/browsecomp) | 2025-04 |
| S15 | [OSWorld 2.0 official site](https://osworld-v2.xlang.ai/) | 2026-06 |
| S16 | [Google DeepMind — AndroidWorld](https://google-research.github.io/android_world/) | ICLR 2025; foundational |
| S17 | [Humanity’s Last Exam official site](https://lastexam.ai/) | dataset updated 2025-04; Nature 2026 |
| S18 | [DeepResearch Bench official site](https://deepresearch-bench.github.io/) | 2025-06; live evaluator |
| S19 | [OpenAI — MLE-bench repository/leaderboard](https://github.com/openai/mle-bench) | live through 2026 |
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

Adopt an eval-driven release loop: production failures → expert-labeled private cases → deterministic outcome graders plus human-calibrated rubric judges → repeated offline experiments → CI/release gates → sampled online evaluation. Treat every result as an **agent-system** measurement and attach a benchmark receipt with suite/split, environment, model, scaffold, budgets, attempts, grader, cost, date, and reporter.

Use four score families without collapsing them: **outcome** (state/artifact correctness), **process** (required/forbidden actions and recovery), **economics** (tokens, USD, tool calls, p50/p95 latency), and **reliability** (pass^1, pass@k where retries are real, pass^k, variance/confidence intervals). Public benchmarks are external probes, not product release gates.

Trace each run as `invoke_workflow → invoke_agent → chat/retrieval/execute_tool`, following pinned OpenTelemetry GenAI Development conventions. Record versions, IDs, status/errors, model/provider, token classes, latency, budgets, fan-out, tool call metadata, artifacts, and evaluator labels. Capture prompt/tool content only through redacted opt-in policies. Preserve failed trajectories and link online incidents back into the regression suite.

Require human calibration for open-ended judging: blinded double labels, explicit rubrics, evidence-bearing verdicts, abstention, κ/α plus TPR/TNR, disagreement adjudication, and recalibration whenever the judge, rubric, or traffic distribution changes. Defer runtime verifier behavior to Section WS5 and production SLO/alert thresholds to WS7.
