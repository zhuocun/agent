# WS2 — Multi-agent topologies, orchestration, and control flow

**Scope:** which multi-agent shapes exist and the evidence for each; plan-to-execution binding; state sharing; fan-out bounds; cost. | **Access date: 2026-08-03** | **Deferred to siblings:** WS1 (single-agent inner loop), WS5 (verifier/critic quality mechanisms, incl. process-verification evidence), WS7 (durability substrate).

---

## 1. Executive summary

- There is **no single decisive condition**. The vendor camps converged on write-concurrency ("who writes"), but the one controlled multi-factor study — 260 configurations at matched compute, *Nature Machine Intelligence*, 2026-07-24 — finds **single-agent baseline capability** the most robust predictor, with decomposability, topology, tool intensity and coordination overhead as further factors [32]. "Single writer" is a necessary term, not the rule. **[medium]**
- The practical selection rule is a **capability-saturation threshold**: above roughly 45% single-agent baseline, added agents predict zero-to-negative gains; the rule matched the sign of the gain in 94% of 16 SWE-bench Verified and Terminal-Bench configurations [32]. **[medium-high]**
- **Decomposability beats complexity**: two benchmarks at near-identical complexity scores diverge from +80.8% (parallelizable) to −70.0% (strictly sequential) [32]. **[high]**
- Anthropic's +90.2% is a **vendor-reported internal eval**, and Anthropic attributes ~80% of BrowseComp variance to token usage alone [1]. Read it as "multi-agent usefully spends more tokens." **[high]**
- **Debate's verdict is about protocol design, not debate.** Competitive and consensus-seeking protocols lose to single-agent, but ColMAD — collaborative, non-zero-sum, over *cross-family* debaters — beats self-consistency at matched tokens [8][33]. Homogeneous debate stays a bad default. **[medium]**
- **Failure is organizational, not model-limited**: MAST v3 clusters 14 modes into system design (~44%), inter-agent misalignment (~32%), task verification (~24%); interventions recovered +9.4% and +15.6% on ChatDev [6]. **[high]**
- **Bounding fan-out is a design obligation.** ADK states the developer *must* implement termination, offering `max_iterations` or sub-agent escalation as the two mechanisms [23]; shipped products publish caps — 16 concurrent agents, 1,000 per run, warnings above 25 agents or 1.5M tokens [16], 3-layer nesting [18]. **[high]**
- **Protocol reality is lopsided.** MCP (tool plane): 10,000+ public servers, 97M+ monthly SDK downloads, Linux Foundation governance [30]. A2A (agent plane): v1.0 and 150+ member orgs [10][11], but nothing retrieved shows cross-vendor topologies coordinating. **[medium]**

---

## 2. Findings

### Topology catalogue

Cheapest/safest → riskiest; cost cells name their denominator.

| # | Topology | Wins when | Cost | Characteristic failure | Conf | Refs |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | Pipeline (ADK `SequentialAgent`, MAF `SequentialBuilder`, CrewAI `@listen`) | the step sequence is known up front | additive; no coordination overhead | cannot handle unknown step counts | [high] | [1][5][12][22][24] |
| F2 | Single agent + read-only subagents | one context is overloaded but one writer suffices | low: fresh worker context, one returned message | under-specified delegation prompt, the worker's only channel | [high] | [3][17][18] |
| F3 | Orchestrator → parallel workers → aggregator | breadth-first **read-only** retrieval exceeds one window *and* the single-agent baseline is low | ~15× chat tokens vs ~4× single-agent (denominator is *chat*, not a matched run) | 50 subagents for trivial queries; duplicated work; synchronous head-of-line blocking | [high] | [1][32] |
| F4 | Hierarchical supervisor tree | routing across specialists; centralized verification contains errors best (4.4× vs 17.2× amplification) | per-hop supervisor turn; unpublished | dedicated libraries retiring; LangChain now advises supervisors "directly via tools" | [med-high] | [12][13][14][32] |
| F5 | Graph / state machine (LangGraph, ADK graph workflows, CrewAI Flows) | policy, branching and budget must be deterministic | overhead is runtime, not extra models | authoring burden; frameworks push you *above* raw graph primitives | [high] | [19][20][22][24] |
| F6 | Blackboard / shared scratchpad | many roles converge on one structured artifact | 45.5k tokens/success vs 64.2k (Flock) / 368.3k (LangGraph); research prototype | omitting the 1980s **control unit** that picks the next writer | [medium] | [27][28][31] |
| F7 | Peer swarm / handoff | peers are partitioned by file ownership under a fixed lead | unpublished | unsupervised swarm is "mostly a distraction"; status lag deadlocks dependents; silo coordination collapses at scale | [high] | [3][15][34] |
| F8 | Mixture-of-agents (layered refinement) | single-turn, preference-judged, no tools or state | N agents × L layers | benchmark unlike agentic work; **[low]** transfer | [medium] | [9] |
| F9 | Debate / consensus | the protocol is collaborative (non-zero-sum) **and** debaters are cross-family | 2.1–3.4× isolated self-correction for competitive/consensus protocols; ColMAD wins at matched ~14.7K tokens | debate hacking — cheap talk under competition, premature consensus under consensus-seeking; homogeneous panels add nothing | [medium] | [7][8][33] |

*Provenance.* **F3:** +90.2% over single-agent Claude Opus 4 (lead Opus 4 / workers Sonnet 4; Anthropic internal research eval and harness; 2025-06-13; **vendor-reported, eval unpublished**) [1]. **F4:** trace-level error amplification ranks independent 17.2× → centralized 4.4×; the baseline × amplification interaction survives cluster-robust correction (P=0.030) [32]. **F6:** 630 matched ALFWorld episodes, 84.6% vs 61.6% / 30.8% (**authors' own research prototype**, 2026-05) [28]. **F8:** 65.1% AlpacaEval 2.0 LC win rate, open-source models only, vs 57.5% GPT-4 Omni (Wang et al., 2024-06; the paper's introduction says 65.8%) [9]. **F9 negative:** N=10 homogeneous agents, R=3 rounds, GSM-Hard + MMLU-Hard, Qwen2.5-7B / Llama-3.1-8B / Ministral-3-8B (Bertalanič & Fortuna, ACM CAIS 2026, 2026-05-22) — debate lost to isolated self-correction everywhere (Ministral-3-8B/GSM-Hard 20.7% vs 48.3%, 23,816 vs 10,707 tokens/problem), and a noise control injecting rationales from *unrelated* problems beat it 63.2% vs 58.8%, p<0.001 [8]. **F9 positive:** ColMAD on the Kamoi et al. error-detection suite, F2 score, Llama-3.1-70B + GPT-4o-mini heterogeneous pair (Chen, Niu, Cheng, Han & Sugiyama, arXiv 2510.20963v2, 2026-07-14) — at matched ~14.7K tokens, 86.29 avg F2 vs self-consistency SC@14 at 81.98 (+4.3) and 77.36 (+8.9), attributed to cross-model diversity rather than compute [33].

### The central controversy

**F10. Both arguments, from primaries. [high]** *Skeptic* (Cognition, 2025-06): share *full agent traces*, not individual messages, because **actions carry implicit decisions, and conflicting decisions carry bad results** — so "by default rule out any agent architectures that don't abide by them" [2]. *Pro* (Anthropic, 2025-06-13): search is compression and subagents compress in parallel across separate windows; token usage explains 80% of BrowseComp variance; +90.2% internally — but domains "that require all agents to share the same context or involve many dependencies between agents are not a good fit" [1].

**F11. Write-concurrency is the condition the vendors converged on — necessary, not sufficient. [medium]** Cognition's 2026 synthesis states it outright: multi-agent works "when writes stay single-threaded and the additional agents contribute intelligence rather than actions" [3]. Every shipping pattern obeys it — workers search / lead writes [1]; reviewer critiques / coder writes [3]; workers find / one Reducer synthesises [4]; peers write only after file-ownership partition [15]. But it does not *predict* gains: PlanCraft degrades 39–70% under every multi-agent variant despite no shared mutable artifact, because the task is sequentially interdependent [32]. Confidence downgraded from [high] on that evidence.

**F12. The measured rule is multi-factor, and baseline capability dominates it. [medium-high]** Kim et al. (*Nature Machine Intelligence* 8:1157–1172, 2026-07-24) hold prompts, tools and per-system compute ceilings constant, varying only coordination structure and model capability: 260 configurations, 6 agentic benchmarks (BrowseComp-Plus, Finance Agent, PlanCraft, WorkBench, SWE-bench Verified, Terminal-Bench), 5 architectures, 3 LLM families. Mean multi-agent improvement is **0.0%** (95% CI −58.7% to +77.2%), spanning +80.8% to −70.0%. By evidential strength: (1) **single-agent baseline** is the only predictor surviving both cluster-robust inference and Holm–Bonferroni (P=0.004, P_Holm=0.018), giving the ~45% saturation threshold, which the authors offer as a validated selection rule rather than a scaling law; (2) **baseline-scaled error amplification** survives cluster-robust inference (P=0.030); (3) **decomposability** — Finance Agent (D=0.41) gains 80.8% while PlanCraft (D=0.42) loses 70%; (4) **tool intensity** and **coordination overhead** are directionally consistent across all six benchmarks but do **not** survive cluster-robust correction, and are reported as descriptive only. Cross-validated R²=0.373 (0.413 with a task-grounded capability metric); best architecture picked in 87% of held-out *within-domain* configurations.

**F13. Matched-*thinking-token* comparisons favour single-agent, within a narrow scope. [medium]** Tran & Kiela (arXiv 2604.02460v1, 2026-04): SAS vs Sequential, Debate, Ensemble, Parallel-roles, Subtask-parallel; FRAMES + MuSiQue 4-hop; Qwen3-30B-A3B, DeepSeek-R1-Distill-Llama-70B, Gemini-2.5-Flash/Pro. Three scope limits. (i) The matched quantity is the **thinking-token budget** — "intermediate reasoning, excluding prompts and final answers" — not total compute; Sequential MAS emits more visible thought text at the same requested budget (693 vs 390 proxy tokens at 1K on Pro). (ii) The finding is that SAS is "the best-performing system **or statistically indistinguishable from the best**" at every budget **above the lowest (100 tokens)**, where neither produces a usable trace. (iii) The uncapped Gemini sweep compares **only SAS against Sequential MAS**, as does the corruption experiment (one model, one dataset, one 1,000-token budget), where MAS wins under masking or substitution — not deletion or distractor padding — and only at the highest substitution level [7]. **"Our MAS beat our SAS" is an architecture claim only under matched budgets — most published ones, Anthropic's included, were not.**

**F14. Deterministic partition makes write-heavy work tractable — with the trade stated. [medium-high]** Cognition's Agentic MapReduce has a planner author Tree-sitter/compiler/import-graph **selectors**, a *non-agentic* pass shard the repo, workers reason over bounded shards, one Reducer synthesise. What is guaranteed is **queue coverage**: "the deterministic pass produces a finite work queue... the scan is complete only when that queue is exhausted." Semantic completeness is not — "completeness now rests on selector recall: a file that matches no selector never reaches a worker. We take this trade deliberately," the argument being that selectors are inspectable and tunable "whereas a search agent's 'I've looked everywhere' is unfalsifiable." Devin Security Swarm reports 72% CVE recall on this design (**vendor-reported**) [4].

### State, plans, protocols, bounds, cost

**F15. Message-passing is the highest-yield thing to remove. [medium-high]** Mechanisms in use: full-trace passing [2][17]; summary handoff (Claude Code's default [18]); artifact/file-as-interface (pass refs, avoid the "game of telephone" [1][21]); shared mutable store (ADK `session.state`: parallel children share one object and the docs say "use distinct keys to avoid race conditions" — the framework does not resolve conflicts, it asks you to avoid them [24][25]); schema-validated patches [28]. **Three answers to conflicting edits appear in the retrieved material, of which two are shipped** — partition by ownership [15] and single-threaded reduce [4] — while typed transactional writes exist only as a research prototype [28]. Nothing retrieved shows reliable free-form concurrent editing.

**F16. Plans help in proportion to how deterministically they execute. [medium]** Claude Code dynamic workflows move the plan into a JavaScript script the runtime executes — "the script holds the loop, the branching, and the intermediate results" — diffable and re-runnable [16]; selectors do the same for coverage [4]. Plan-as-prompt over-constrains: managers "default to being overly prescriptive, which backfires when the manager lacks deep codebase context" [3]. Approval gates are standard [12][16]. Replanning and verifier-in-the-loop orchestration are WS5's lane.

**F17. Protocol adoption is real at the tool plane, aspirational at the agent plane. [medium-high]** MCP was donated to the Linux Foundation's Agentic AI Foundation on 2025-12-09 with 10,000+ active public servers, 97M+ monthly SDK downloads [30]. A2A v1.0 (2026-04) adds signed Agent Cards, multi-tenancy and multi-protocol bindings [10]; the Linux Foundation reports 150+ orgs and three cloud integrations (**press-release claims, not measurements**) [11]. Both state the layering identically: **MCP inside agents, A2A between agents**. ACP and ANP are later roadmap phases with no retrieved production traction [26]; MAF 1.0 shipped with "A2A 1.0 support coming soon" [12]. Standardising formats does not fix coordination — MAST observes inter-agent failures "even when agents within the same framework communicate using natural language," attributing them to a collapse of theory-of-mind rather than transport [6].

**F18. Termination is a design obligation; fan-out and depth bounds have published defaults. [high]** ADK is explicit that the framework does not decide for you — "the `LoopAgent` itself does not inherently decide when to stop looping. You must implement a termination mechanism to prevent infinite loops" — and offers two optional mechanisms, `max_iterations` or a sub-agent setting `escalate=True` [23][24]. Shipped bounds: Claude Code workflows run **16 concurrent agents** and **1,000 total per run**, warning above **25 scheduled agents or 1.5M projected tokens** [16]; subagents nest **3 layers** by default (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; `1` disables) [18]; agent teams forbid nesting [15]. **Partials:** `/deep-research` reports claims verifiers *couldn't* check as **unverified** rather than refuted [16]; the Reducer ignores zero-finding workers [4]. **Deadlock is documented:** "teammates sometimes fail to mark tasks as completed, which blocks dependent tasks" [15]. **Stragglers too:** Anthropic's lead runs subagents synchronously, so "the entire system can be blocked while waiting for a single subagent" [1].

**F19. No apples-to-apples cost multiplier exists; honest numbers point both ways. [medium]** ~15× chat tokens vs ~4× single-agent — denominator is *chat*, not a matched run (Anthropic telemetry, 2025-06) [1]. 2.1–3.4× for competitive/consensus debate at equal-or-worse accuracy (7–8B, 2026-05) [8], against which ColMAD is the matched-token counterexample [33]. 8.1× tokens-per-success for a LangGraph baseline vs PatchBoard on ALFWorld (self-reported) [28]. 63.9% token and 52.4% latency reduction from collapsing tool calls into one CodeAct program ("a representative multi-step workload," harness unspecified, **vendor-reported**, 2026-06) [13]. Resume economics is WS7's lane.

**F20. Coordination pathologies emerge at scale. [medium]** Magentic Marketplace (Microsoft Research; 100 customers × 300 businesses; GPT-4o/4.1/5, Gemini-2.5-Flash, Sonnet-4/4.5, GPTOSS-20b, Qwen3-14b/4b): first proposals achieve **60–100% selection rates** against near-zero for third proposals — a 10–30× advantage for response speed over quality — plus a **paradox of choice**, welfare falling as the search limit rose 3→100 (GPT-5 ~2,000→~1,400; Sonnet 4 ~1,800→~600). Under prompt injection, three models redirected *all* payments [29]. SILO-BENCH shows the same defect without market framing: across 30 role-free algorithmic tasks and 1,620 runs, agents "communicate actively, yet fail to translate interaction into effective distributed computation," the hardest tier scoring **zero** beyond 50 agents [34].

---

## 3. Delta since 2026-07-14

**New.** (1) **The skeptic revised in public.** Cognition's "Multi-Agents: What's Actually Working" (2026-04-22) [3] is absent from the prior brief, which cited neither Cognition post; it supplies the write-concurrency condition that brief left open at "Low–medium" confidence. (2) **A controlled multi-factor study now exists** — 260 matched-compute configurations, peer-reviewed, 2026-07-24 [32] — superseding any single-condition framing. (3) **Budget-controlled comparisons** [7][8] and a matched-token *positive* debate result [33] bracket the question from both sides. (4) **Anthropic ships three topologies in one product** with published caps [15][16][18]; **Cognition ships manager-over-child Devins and Agentic MapReduce** [3][4]. (5) **MAST v3** [6] quantifies failure modes over 1,642 traces; the **blackboard revival** [27][28][31] answers shared writes; **SILO-BENCH** [34] adds a role-free coordination benchmark.

**Changed.** (6) MAF 1.0 (GA 2026-04-02) supersedes *both* AutoGen and Semantic Kernel [12], which the prior brief cited as live. LangGraph 1.0 GA'd 2025-10-22 [20], `create_react_agent` is deprecated [19], `langgraph-supervisor` is no longer recommended, ADK template workflows are superseded in ADK 2.0 [24]. (7) **Protocols matured** — A2A v1.0 under Linux Foundation governance [10][11], MCP into the AAIF [30]; the prior brief did not cover the agent plane.

**Wrong or now overstated.** (8) **"~15× tokens" is quoted as a task-matched multiplier**; it is a ratio against *chat* from one vendor's 2025 telemetry [1]. (9) **"Anthropic reported ~90% gain" is under-caveated** — internal, unpublished eval, 80% of variance attributed to token spend [1]. (10) **"Pure peer swarms are rarely best for a single-brand chat product" is right for the wrong reason**: the problem is concurrent writes and coordination overhead, not brand voice; stated correctly the rule also says when peers *are* fine [15]. (11) **"Depth bound default 1" was called industry-aligned**; Anthropic's shipped default is 3 [18]. (12) **"Anthropic multi-agent vs OpenAI single-agent Deep Research" is a weak framing** — the evidence that matters is the matched-compute literature [7][32]. (13) **"Graphs shine when policy and budget must be deterministic" understates the shift** — a deterministic skeleton is now every major framework's default [12][16][19][22][24].

---

## 4. Contested / open questions

- **Does the ~45% saturation threshold generalise?** Validated within-domain on 16 SWE-bench Verified and Terminal-Bench configurations, but the same paper reports leave-one-dataset-out R² = −2.09 [32]. **[medium]** locally, **[low]** across domains.
- **Does multi-agent help once compute is matched in the retrieval-unbounded regime?** Tran & Kiela's scope is multi-hop QA over already-retrieved context [7]; the Nature study matches per-system ceilings but not Anthropic's unbounded-search regime [32]. **Still the highest-value missing experiment.**
- **Is the corruption crossover general?** One model, one dataset, one 1,000-token budget, SAS vs Sequential only [7]. **[low]** generality.
- **How far does the ColMAD result carry?** One heterogeneous pair, one error-detection suite [33]; whether collaborative protocols beat single-agent on tool-using agentic tasks is untested.
- **Does A2A get used beyond announcement?** 150+ member orgs and three cloud integrations [11] versus zero retrieved production topology descriptions. Membership is not adoption. **[contested]**

---

## 5. Anti-patterns & failure modes

| Anti-pattern | Evidence | Prefer |
| --- | --- | --- |
| Adding agents to a task the single agent already does well | Above ~45% baseline, added agents predict zero-to-negative gains; SWE-bench Verified degrades 1.3–12.8% across all four MAS variants [32] | Measure the baseline first; fan out only below the threshold |
| Parallel writers to one artifact | Cognition principle 2 [2][3]; Anthropic asks you to partition files manually [15]; ADK asks you to avoid key collisions [24] | Single-threaded writes; ownership partition; typed patches [28] |
| Decomposing a sequentially interdependent task | PlanCraft loses 39–70% at the same complexity score where Finance Agent gains 80.8% [32] | Test decomposability, not difficulty, before fanning out |
| Comparing MAS to SAS without matching compute | SAS best or statistically indistinguishable above the 100-token regime [7]; 80% of BrowseComp variance is token usage [1] | State the budget, and what it does and does not cover |
| Fan-out with no centralized verification | Error amplification 17.2× for independent agents vs 4.4× centralized [32] | Route worker output through one aggregation bottleneck |
| Homogeneous competitive or consensus-seeking debate | Debate ≤ self-correction at 2.1–3.4× cost, beaten by a noise control [8]; both protocols exhibit debate hacking [33] | Isolated self-correction, or a collaborative protocol over cross-family models [33] |
| Unbounded spawn / no depth cap | 50 subagents for simple queries [1]; ADK: "you must implement a termination mechanism" [23] | 16 concurrent / 1,000 total / depth 3 are shipped precedents [16][18] |
| No completion signal → deadlock | Teammates "fail to mark tasks as completed, which blocks dependent tasks" [15]; MAST FM-1.5 12.4%, FM-3.1 6.2% [6] | Deterministic completion detection; timeouts; stall detection [28] |

---

## 6. Design implications

*Normative; each states its rationale and accepted tradeoff.*

1. **Gate fan-out on a measured single-agent baseline, then on write-concurrency.** *Rationale:* baseline capability is the only predictor surviving both robustness corrections, threshold ~45% [32]; single-threaded writes are necessary but do not predict gains [3][32]. *Tradeoff:* you must run the baseline first and recalibrate per domain.
2. **Require a matched-budget A/B before shipping fan-out, and state what the budget covers.** *Rationale:* compute is the default confound [1][7][32]. *Tradeoff:* thinking-token parity is not total-compute parity [7], so pin per-system ceilings including prompts and tool calls.
3. **Route every fan-out through one aggregation bottleneck.** *Rationale:* centralized topologies contain errors roughly 4× better than independent ones, surviving cluster-robust correction [32]. *Tradeoff:* the aggregator becomes the throughput limit; give it a deadline and a labeled-partial path [16].
4. **Make the plan an artifact the runtime executes, not a prompt the model remembers.** *Rationale:* scripts and selectors are diffable, re-runnable, and yield a finite work queue [4][16]. *Tradeoff:* what is lost is mid-run **human** input — the script still branches on intermediate results [16] — so run stages needing sign-off separately, and state the recall assumption when coverage rests on selectors [4].
5. **Pass artifact references, not transcripts; where workers share state, partition ownership or serialize the reduce.** *Rationale:* telephone loss and token blowup are both measured [1][28]. *Tradeoff:* typed transactional writes are more general but remain a research prototype [28], so shipping today means a coarser partition.
6. **Treat termination as a design obligation and publish the caps:** concurrency, total workers, depth, per-run token/USD ceiling, per-worker deadline. *Rationale:* ADK states the developer must implement termination [23]; mature products ship numbers [15][16][18]. *Tradeoff:* caps produce partial results, so emit a *labeled* partial — copy the "unverified, not refuted" distinction [16].
7. **Use MCP inside agents; reserve A2A for organizational boundaries.** *Rationale:* MCP has scale and neutral governance [30], and standardised transport does not fix coordination failures [6]. *Tradeoff:* forgoes cross-vendor composability until there is evidence it pays.
8. **Do not adopt debate or MoA layering as defaults, but do not treat debate as settled-negative.** *Rationale:* homogeneous competitive/consensus debate loses at 2.1–3.4× cost [8], while a collaborative protocol over cross-family models beats self-consistency at matched tokens [33]. *Tradeoff:* that positive rests on one pair and one benchmark family, so pilot behind a local eval.

---

## 7. Sources

All retrieved **2026-08-03**.

| [n] | Title | Org | Date | Type | URL |
| --- | --- | --- | --- | --- | --- |
| 1 | How we built our multi-agent research system | Anthropic | 2025-06-13 | Vendor eng. | https://www.anthropic.com/engineering/multi-agent-research-system |
| 2 | Don't Build Multi-Agents | Cognition | 2025-06 (undated; follow-up dates it 10 mo. before 2026-04-22) | Vendor eng. | https://cognition.ai/blog/dont-build-multi-agents |
| 3 | Multi-Agents: What's Actually Working | Cognition (Walden Yan) | 2026-04-22 | Vendor eng. | https://cognition.com/blog/multi-agents-working |
| 4 | Agentic MapReduce | Cognition / Devin | 2026 (undated; cites a 2026 study) | Vendor eng. | https://devin.ai/blog/agentic-map-reduce |
| 5 | Building effective agents | Anthropic | 2024-12-19 — *foundational: canonical workflow/agent taxonomy still in use* | Vendor eng. | https://www.anthropic.com/engineering/building-effective-agents |
| 6 | Why Do Multi-Agent LLM Systems Fail? — Cemri et al., **v3** | UC Berkeley et al. | v1 2025-03-17, v3 2025-10-26, arXiv:2503.13657v3 | Preprint | https://arxiv.org/abs/2503.13657v3 |
| 7 | Single-Agent LLMs Outperform Multi-Agent Systems… Equal Thinking Token Budgets — Tran & Kiela | Stanford | 2026-04, arXiv:2604.02460v1 | Preprint | https://arxiv.org/html/2604.02460v1 |
| 8 | The Cost of Consensus — Bertalanič & Fortuna | Jožef Stefan Inst. / ACM CAIS 2026 | 2026-05-22 | Peer-reviewed | https://arxiv.org/abs/2605.00914 |
| 9 | Mixture-of-Agents Enhances LLM Capabilities — Wang et al. | Duke / Together AI / UChicago / Stanford | 2024-06, arXiv:2406.04692 — *foundational: canonical MoA reference* | Preprint | https://arxiv.org/abs/2406.04692 |
| 10 | Announcing Version 1.0 | A2A Protocol project | 2026-04 | Spec announcement | https://a2a-protocol.org/latest/announcing-1.0/ |
| 11 | A2A Protocol Surpasses 150 Organizations… | Linux Foundation | 2026-04-09 | Press release (claims) | https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year |
| 12 | Microsoft Agent Framework Version 1.0 | Microsoft | 2026-04-08 (GA 2026-04-02 in text) | Vendor release | https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/ |
| 13 | Microsoft Agent Framework at BUILD 2026 | Microsoft | 2026-06-09 | Vendor release | https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/ |
| 14 | Agent orchestration (Agents SDK) | OpenAI | undated docs | SDK docs | https://openai.github.io/openai-agents-python/multi_agent/ |
| 15 | Orchestrate teams of Claude Code sessions | Anthropic | docs at v2.1.178–2.1.199 | Product docs | https://code.claude.com/docs/en/agent-teams.md |
| 16 | Orchestrate subagents at scale with dynamic workflows | Anthropic | docs at v2.1.154–2.1.203 | Product docs | https://code.claude.com/docs/en/workflows.md |
| 17 | Subagents (Claude Code) | Anthropic | undated docs | Product docs | https://code.claude.com/docs/en/sub-agents.md |
| 18 | Subagents (Claude Agent SDK) | Anthropic | docs at v2.1.217–2.1.219 | SDK docs | https://code.claude.com/docs/en/agent-sdk/subagents.md |
| 19 | What's new in LangGraph v1 | LangChain | undated docs (v1 line) | Framework docs | https://docs.langchain.com/oss/python/releases/langgraph-v1 |
| 20 | LangGraph 1.0 is now generally available | LangChain | 2025-10-22 | Changelog | https://langchain.launchnotes.io/announcements/ann_lxOZRCoFw2Qn9 |
| 21 | Deep Agents overview | LangChain | undated docs | Framework docs | https://docs.langchain.com/oss/python/deepagents/overview |
| 22 | Flows | CrewAI | undated docs | Framework docs | https://docs.crewai.com/en/concepts/flows |
| 23 | Loop workflow (LoopAgent) | Google ADK | undated docs (Python v0.1.0+) | Framework docs | https://adk.dev/agents/workflow-agents/loop-agents/ |
| 24 | Multi-agent systems (`docs/agents/multi-agents.md`) | Google ADK | repo docs, rev 5331a07f | Framework docs | https://github.com/google/adk-docs/blob/5331a07f/docs/agents/multi-agents.md |
| 25 | Multi-agent workflow patterns (`docs/workflows/patterns.md`) | Google ADK | repo docs, main | Framework docs | https://github.com/google/adk-docs/blob/main/docs/workflows/patterns.md |
| 26 | A Survey of Agent Interoperability Protocols: MCP, ACP, A2A, ANP | (survey authors) | 2025-05, arXiv:2505.02279 | Survey preprint | https://arxiv.org/abs/2505.02279 |
| 27 | Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture | (authors) | 2025-07, arXiv:2507.01701v1 | Preprint | https://arxiv.org/abs/2507.01701v1 |
| 28 | PatchBoard: Schema-Grounded State Mutation… — Zhang, Shi & Wang | Xidian University | 2026-05, arXiv:2605.29313v1 | Preprint (research prototype, self-reported) | https://arxiv.org/html/2605.29313v1 |
| 29 | Magentic Marketplace: An Open-Source Environment for Studying Agentic Markets | Microsoft Research | 2025-10, arXiv:2510.25779 | Preprint + research blog | https://arxiv.org/abs/2510.25779 |
| 30 | Donating the Model Context Protocol and establishing the Agentic AI Foundation | Anthropic | 2025-12-09 | Vendor announcement | https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation |
| 31 | Terrarium: Revisiting the Blackboard for Multi-Agent Safety, Privacy, and Security Studies | (authors) | 2025-10, arXiv:2510.14312v1 | Preprint | https://arxiv.org/html/2510.14312v1 |
| 32 | Capable language models can outgrow the benefits of collaboration — Kim, Gu, Park et al. | *Nature Machine Intelligence* 8:1157–1172 | published 2026-07-24 | Peer-reviewed | https://www.nature.com/articles/s42256-026-01268-y |
| 33 | When and Why Does Multi-Agent Debate Fail and Does It Really Underperform? (ColMAD) — Chen, Niu, Cheng, Han & Sugiyama | CUHK / RIKEN AIP / HKBU / U. Tokyo | v1 2025-10-23, v2 2026-07-14, arXiv:2510.20963v2 | Preprint | https://arxiv.org/html/2510.20963v2 |
| 34 | SILO-BENCH: A Scalable Environment for Evaluating Distributed Coordination in Multi-Agent LLM Systems — Zhang et al. | ACL 2026 (Long Papers), pp. 29379–29398 | 2026-07 | Peer-reviewed | https://aclanthology.org/2026.acl-long.1354/ |

---

## 8. Proposed content for final doc sections

**Section 5 — Multi-agent topologies.** Open with the multi-factor decision rule: measure the single-agent baseline, test decomposability, then check that writes stay single-threaded. Carry §2's topology table across as-is. Follow with "The controversy, as far as the evidence settles it" from F10–F14 — both primary arguments quoted, Cognition's 2026 synthesis as the vendor convergence, the Nature study as the controlled result demoting any single condition, Tran & Kiela within their scope, Anthropic's +90.2% marked vendor-reported. Reuse §5's anti-pattern table verbatim.

**Section 6 — Orchestration & control flow.** Five subsections from F15–F19: (1) *state sharing* — five mechanisms, two shipped answers to conflicting writes plus one prototype; (2) *plan-to-execution binding* — script/selector as the strong form, with the selector-recall trade stated; (3) *interop* — MCP inside, A2A between, ACP/ANP not yet, transport standardisation no fix for coordination; (4) *termination, budget, deadlock* — termination as a design obligation, a defaults box (16 / 1,000 / 25 / 1.5M / depth-3), the unverified-vs-refuted distinction; (5) *cost & latency* — every multiplier **with its denominator**. Cross-reference out: WS1, WS5, WS7.
