# WS2 — Multi-agent topologies, orchestration, and control flow

**Scope:** which multi-agent shapes exist and the evidence for each; how plans bind to execution; how state is shared; how fan-out is bounded; what it costs. | **Access date: 2026-08-03** | **Deferred to siblings:** WS1 (single-agent inner loop), WS5 (verifier/critic as a quality mechanism), WS7 (durability/runtime substrate).

---

## 1. Executive summary

- The "don't build multi-agents" argument [2] and the "+90.2% multi-agent research" result [1] are **both right and not in conflict**. The discriminator is not parallelism but **who writes**. Cognition, the original skeptic, now states it: multi-agent works "when writes stay single-threaded and the additional agents contribute intelligence rather than actions" [3]. **[high]**
- A second discriminator arrived in 2026: **compute accounting**. Under matched thinking-token budgets a single agent matches or beats five MAS topologies on multi-hop QA; MAS wins only once the single agent's context is **corrupted** — not merely long [7]. **[high]**
- Anthropic's +90.2% is a **vendor-reported internal eval**, and Anthropic attributes ~80% of BrowseComp variance to token usage alone [1]. Read it as "multi-agent usefully spends more tokens," not architectural superiority. **[high]**
- **Debate has the widest gap between reputation and evidence**: 2.1–3.4× the tokens of isolated self-correction for equal-or-worse accuracy, with peer rationales no better than rationales from *unrelated* problems [8]. **[medium-high]**
- **Failure is organizational, not model-limited**: MAST splits 200+ traces 41.8% specification / 36.9% inter-agent misalignment / 21.3% verification; prompt fixes recovered only ~15.6% on one system [6]. **[high]**
- **Artifact-as-interface beat message-passing**: filesystem refs [1], shard selectors [4], filesystem-as-context [21] and schema-validated patches [28] converge. **[medium]**
- **Fan-out bounds are shipped product surface with numbers**: 16 concurrent agents, 1,000 per run, warnings above 25 agents or 1.5M projected tokens [16]; 3-layer nesting default [18]; mandatory `max_iterations` on ADK loops [23]. **[high]**
- **Protocol reality is lopsided.** MCP (tool plane): 10,000+ public servers, 97M+ monthly SDK downloads, Linux Foundation governance [30]. A2A (agent plane): v1.0, 150+ member orgs [10][11], but nothing retrieved shows cross-vendor topologies actually coordinating. **[medium]**

---

## 2. Findings

### Topology catalogue

Cheapest/safest → riskiest; cost cells state their denominator or say none is published.

| # | Topology | Wins when | Cost | Characteristic failure | Conf | Refs |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | Pipeline (ADK `SequentialAgent`, MAF `SequentialBuilder`, CrewAI `@listen`) | the step sequence is known up front | additive; no coordination overhead | cannot handle unknown step counts — Anthropic's stated reason to use agents at all | [high] | [1][5][12][22][24] |
| F2 | Single agent + read-only subagents | one context is overloaded but one writer suffices | low: fresh worker context, one returned message | under-specified delegation prompt, the only channel to a worker that sees nothing else | [high] | [3][17][18] |
| F3 | Orchestrator → parallel workers → aggregator | breadth-first **read-only** retrieval exceeds one window | ~15× chat tokens vs ~4× single-agent (denominator is *chat*, not a matched run) | 50 subagents for trivial queries; duplicated work from vague specs; synchronous head-of-line blocking | [high] | [1] |
| F4 | Hierarchical supervisor tree | routing across specialists under developer-owned guardrails | per-hop supervisor turn; unpublished | dedicated libraries retiring; LangChain now advises supervisors "directly via tools" | [med-high] | [12][13][14] |
| F5 | Graph / state machine (LangGraph, ADK graph workflows, CrewAI Flows) | policy, branching and budget must be deterministic | overhead is runtime, not extra models | authoring burden; frameworks now push you *above* raw graph primitives | [high] | [19][20][22][24] |
| F6 | Blackboard / shared scratchpad | many roles converge on one structured artifact | 45.5k tokens/success vs 64.2k (Flock) / 368.3k (LangGraph) | omitting the 1980s **control unit** that picks the next writer → unmediated concurrent writes | [medium] | [27][28][33] |
| F7 | Peer swarm / handoff | peers are partitioned by file ownership under a fixed lead | unpublished | unsupervised swarm is "mostly a distraction"; task-status lag deadlocks dependents | [high] | [3][15] |
| F8 | Mixture-of-agents (layered refinement) | single-turn, preference-judged, no tools or state | N agents × L layers | benchmark unlike agentic work; **[low]** transfer | [medium] | [9] |
| F9 | Debate / consensus | no matched-cost evidence retrieved in its favour | 2.1–3.4× isolated self-correction | sycophantic conformity, contextual fragility, consensus collapse | [med-high] | [7][8] |

*Provenance.* **F3:** +90.2% over single-agent Claude Opus 4 (lead Opus 4 / workers Sonnet 4; Anthropic internal research eval and harness; 2025-06-13; **vendor-reported, eval unpublished**); shape is lead → 3–5 parallel subagents each issuing 3+ parallel tool calls → CitationAgent [1]. **F6:** 630 matched ALFWorld episodes, 84.6% success vs 61.6% / 30.8%; PatchBoard validates JSON Patch mutations against a shared schema through a deterministic transactional kernel, and ablations credit that interface plus bounded views, not shared memory (**authors' own system**, 2026-05) [28]. **F7:** agent teams ship behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, with no worktree isolation and an instruction to "partition the work so each teammate owns a different set of files" [15]. **F8:** 65.1% AlpacaEval 2.0 LC win rate, open-source models only, vs 57.5% GPT-4 Omni (Wang et al., 2024-06; the introduction states 65.8%) [9]. **F9:** N=10 homogeneous agents, R=3 rounds, GSM-Hard + MMLU-Hard, Qwen2.5-7B / Llama-3.1-8B / Ministral-3-8B (Bertalanič & Fortuna, ACM CAIS 2026, 2026-05-22): debate matched or lost to isolated self-correction everywhere (Ministral-3-8B/GSM-Hard 20.7% vs 48.3%, at 23,816 vs 10,707 tokens/problem), and a **noise control** injecting rationales from *unrelated* problems beat debate, 63.2% vs 58.8%, p<0.001 [8]. Caveat: 7–8B homogeneous only; at frontier scale debate was the best MAS variant, still short of single-agent under matched budget [7].

### The central controversy

**F10. Both arguments, from primaries. [high]** *Skeptic* (Cognition, 2025-06): share context and *full agent traces*, not individual messages; and **actions carry implicit decisions, and conflicting decisions carry bad results** — so "by default rule out any agent architectures that don't abide by them" [2]. *Pro* (Anthropic, 2025-06-13): search is compression, subagents compress in parallel across separate windows, token usage explains 80% of BrowseComp variance, +90.2% internally — but domains "that require all agents to share the same context or involve many dependencies between agents are not a good fit" [1].

**F11. The discriminator is write-concurrency over shared state. [high]** Both sides already agreed while emphasising different halves: Cognition's principle 2 is about *writes*, Anthropic's exclusion about *shared context and dependencies*; Cognition's 2026 synthesis says it outright [3]. Every shipping pattern obeys it — workers search / lead writes [1]; reviewer critiques / coder writes [3]; advisor advises / primary writes [3]; workers find / one Reducer synthesises [4]; peers write only after file-ownership partition [15]. Decomposability and verification cost are downstream: a task is safely decomposable exactly when the pieces need not agree about anything they each write.

**F12. Under matched compute, single-agent is the default, and the crossover is measurable. [high]** Tran & Kiela (Stanford, arXiv 2604.02460v1, 2026-04): SAS vs Sequential, Debate, Ensemble, Parallel-roles, Subtask-parallel; FRAMES + MuSiQue 4-hop; Qwen3-30B-A3B, DeepSeek-R1-Distill-Llama-70B, Gemini-2.5-Flash/Pro; matched *thinking-token* budgets; LLM-as-judge rubric. SAS matched or beat every MAS, even uncapped; their Data-Processing-Inequality argument explains why — inter-agent messages cannot carry more answer-information than the context they derive from. MAS wins only under **corruption** (masking, substitution), not deletion or distractor padding: under substitution SAS led at α=0.3, tied at 0.5, Sequential clearly won at 0.7. The gold answer appeared in SAS reasoning 42.7% of the time vs 18.6% for Sequential MAS (Gemini-2.5-Flash); MAS lost correct spans at finalization [7]. **"Our MAS beat our SAS" is an architecture claim only if budgets were matched — most published ones, Anthropic's included, were not.**

**F13. Write-heavy work becomes tractable by making the partition deterministic. [medium-high]** Anthropic: coding has "fewer truly parallelizable tasks than research" [1]. Cognition's counter is Agentic MapReduce — a planner authors Tree-sitter/compiler/import-graph **selectors**, a *non-agentic* pass shards the repo, workers reason over bounded shards, one Reducer synthesises. Coverage is "guaranteed by construction," and selectors are "an inspectable, version-controlled artifact... whereas a search agent's 'I've looked everywhere' is unfalsifiable". Devin Security Swarm reports 72% recall against CVEs pinned to pre-fix commits (**vendor-reported**) [4].

### State, plans, protocols, bounds, cost

**F14. Message-passing is the highest-yield thing to remove. [medium-high]** Mechanisms in use: full-trace passing [2][17]; summary handoff (Claude Code's default [18]); artifact/file-as-interface (write to a filesystem, pass refs, avoid the "game of telephone" [1]; a Deep Agents core capability [21]); shared mutable store (ADK `session.state`: parallel children share one object and the docs say "use distinct keys to avoid race conditions" — the framework does not resolve conflicts, it asks you to avoid them [24][25]); schema-validated patches [28]. **Exactly three shipped answers to conflicting edits exist: partition by ownership [15], single-threaded reduce [4], typed transactional writes [28].** Nothing retrieved shows reliable free-form concurrent editing.

**F15. Plans help in proportion to how deterministically they execute. [medium]** Claude Code dynamic workflows move the plan into a JavaScript script the runtime executes — "the script holds the loop, the branching, and the intermediate results" — diffable and re-runnable [16]; selectors do the same for coverage [4]. Plan-as-prompt over-constrains: managers "default to being overly prescriptive, which backfires when the manager lacks deep codebase context" [3]. Replanning evidence is thin (VMAO: completeness 3.1→4.2, source quality 2.6→4.1 on 1–5 scales, 25 expert-curated queries, **authors' own system**) [32]. Approval gates are standard [12][16].

**F16. Protocol adoption is real at the tool plane, aspirational at the agent plane. [medium-high]** MCP was donated to the Linux Foundation's Agentic AI Foundation on 2025-12-09 with 10,000+ active public servers and 97M+ monthly SDK downloads at donation [30]. A2A v1.0 (2026-04) adds signed Agent Cards, multi-tenancy and multi-protocol bindings [10]; the Linux Foundation reports 150+ orgs and Azure AI Foundry / Copilot Studio / Bedrock AgentCore integrations (**press-release claims, not measurements**) [11]. Both state the layering identically: **MCP inside agents, A2A between agents**. ACP and ANP are later roadmap phases [26] with no retrieved production traction; MAF 1.0 shipped with "A2A 1.0 support coming soon" [12]. A2A's headline benefit — coordinating "without sharing internal memory" [11] — is exactly the context-splitting F11 says to avoid *inside* one product.

**F17. Fan-out, recursion and straggler bounds have published defaults. [high]** Claude Code workflows: **16 concurrent agents**, **1,000 total per run**, no mid-run user input, advisory warning above **25 scheduled agents or 1.5M projected tokens** [16]. Subagents nest **3 layers** by default (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; `1` disables) [18]; agent teams forbid nesting [15]. ADK `LoopAgent` stops on `max_iterations` or a sub-agent `escalate=True` [23][24]; PatchBoard's kernel halts on consecutive invalid patches, repeated no-ops, exhausted budgets, or repeated state hashes [28]. **Partials:** `/deep-research` reports claims verifiers *couldn't* check as **unverified** rather than refuted [16]; the Reducer ignores zero-finding workers [4]. **Deadlock is documented:** "teammates sometimes fail to mark tasks as completed, which blocks dependent tasks" [15]. **Stragglers too:** Anthropic's lead runs subagents synchronously, so "the entire system can be blocked while waiting for a single subagent" [1].

**F18. No apples-to-apples cost multiplier exists; the honest numbers point opposite ways. [medium]** ~15× chat tokens vs ~4× single-agent — denominator is *chat*, not a matched run (Anthropic telemetry, 2025-06) [1]. 2.1–3.4× for debate vs self-correction at equal-or-worse accuracy (7–8B, 2026-05) [8]. 8.1× tokens-per-success for a LangGraph baseline vs PatchBoard on ALFWorld (self-reported) [28]. 63.9% token and 52.4% latency reduction from collapsing tool-call turns into one CodeAct program ("a representative multi-step workload," harness unspecified, **vendor-reported**, 2026-06) [13]. Resume economics: Claude Code replay invalidates every agent started after the first unfinished one, so "a workflow that fans work out across many small agents preserves more progress than one long agent" [16].

**F19. Coordination pathologies emerge at scale. [medium]** Magentic Marketplace (Microsoft Research; 100 customers × 300 businesses; GPT-4o/4.1/5, Gemini-2.5-Flash, Sonnet-4/4.5, GPTOSS-20b, Qwen3-14b/4b): 80–100% first-proposal acceptance across all models — a 10–30× advantage for speed over quality — plus a **paradox of choice**, welfare *falling* as the search limit rose 3→100 (GPT-5 ~2,000→~1,400; Sonnet 4 ~1,800→~600). Under prompt injection, three models redirected *all* payments [29].

---

## 3. Delta since 2026-07-14

**New.** (1) **The skeptic revised in public.** Cognition's "Multi-Agents: What's Actually Working" (2026-04-22) [3] is the most important document here and is absent from the prior brief, which cited neither Cognition post; it supplies the discriminating condition that brief listed as an open question at "Low–medium" confidence. (2) **Budget-controlled comparisons now exist** [7][8], with a falsifiable crossover — context *corruption*, not *length*. (3) **Anthropic ships three topologies in one product** with published caps — subagents [18], experimental agent teams [15], script-held dynamic workflows [16] — and **Cognition ships manager-over-child Devins and Agentic MapReduce** [3][4]. (4) **MAST** [6] gives a quantified failure taxonomy the prior brief did not use; the **blackboard revival** [27][28][33] is a new answer to shared writes. (5) **MAS-ProVe** finds process verification does *not* consistently help and is high-variance [31] — WS5's lane, flagged because it undercuts "add a verifier" as an unconditional fix.

**Changed.** (6) MAF 1.0 (GA 2026-04-02) supersedes *both* AutoGen and Semantic Kernel [12], which the prior brief cited as live; Magentic-One survives as a pattern *inside* MAF. LangGraph 1.0 GA'd 2025-10-22 [20], `create_react_agent` is deprecated [19], `langgraph-supervisor` is no longer recommended, ADK template workflows are superseded in ADK 2.0 [24]. (7) **Protocols matured** — A2A v1.0 under Linux Foundation governance [10][11], MCP into the AAIF [30]; the prior brief did not cover the agent plane.

**Wrong or now overstated.** (8) **"~15× tokens" is quoted as a task-matched multiplier**; it is a ratio against *chat* from one vendor's 2025 telemetry [1], and under matched budgets the comparison inverts [7]. (9) **"Anthropic reported ~90% gain" is under-caveated** — internal, unpublished eval, 80% of variance attributed to token spend [1]. (10) **"Pure peer swarms are rarely best for a single-brand chat product" is right for the wrong reason**: the problem is concurrent writes, not brand voice — stated correctly, the rule also says when peers *are* fine (partitioned ownership [15]). (11) **"Depth bound default 1" was presented as industry-aligned**; Anthropic's shipped default is 3 [18], so depth 1 is a product choice, not a norm. (12) **"Anthropic multi-agent vs OpenAI single-agent Deep Research" is now a weak framing** — the strong single-agent case is the budget-controlled literature [7][8], and the strong multi-agent case is narrower than "breadth research": read-heavy work with a single writer. (13) **"Graphs shine when policy and budget must be deterministic" understates the shift** — a deterministic skeleton is now every major framework's default posture [12][16][19][22][24].

---

## 4. Contested / open questions

- **Does multi-agent help at frontier scale once compute is matched?** Tran & Kiela say no for multi-hop QA over already-retrieved context [7]; Anthropic's regime — unbounded external search, information exceeding one window — is untested by them. **No matched-budget comparison exists in the retrieval-unbounded regime; that is the highest-value missing experiment.**
- **Is the corruption crossover general or a MuSiQue artifact?** One model, one benchmark, one 1,000-token budget [7]. **[low]** generality. Relatedly, Gemini 2.5 budget-control artifacts distort effective compute [7], so matched-budget results are themselves harness-sensitive.
- **Does A2A get used beyond announcement?** 150+ member orgs and three cloud integrations [11] versus zero retrieved production topology descriptions. Membership is not adoption. **[contested]**
- **Can the "smart friend" inversion — weak primary escalating to a strong advisor — work?** Cognition says not yet, and believes it is a *training* problem [3]. **[open]**
- **Is verification a reliable orchestration signal?** VMAO says yes on 25 queries [32]; MAS-ProVe says it is inconsistent across six frameworks [31]. Defer to WS5.

---

## 5. Anti-patterns & failure modes

| Anti-pattern | Evidence | Prefer |
| --- | --- | --- |
| Parallel writers to one artifact | Cognition principle 2 [2][3]; Anthropic asks you to partition files manually [15]; ADK asks you to avoid key collisions [24] | Single-threaded writes; ownership partition; typed patches [28] |
| Comparing MAS to SAS without matching compute | SAS ≥ MAS across 5 topologies under matched budgets [7]; 80% of BrowseComp variance is token usage [1] | State the token budget beside every architecture claim |
| Unguided homogeneous debate as a quality gate | Debate ≤ self-correction at 2.1–3.4× cost; a noise control beat debate [8] | Isolated self-correction, or clean-context review (WS5) |
| Vague subtask descriptions | Subagents duplicated each other's work [1]; MAST FM-1.1 at 10.98% [6] | Objective + output format + tools + boundaries per worker [1] |
| Unbounded spawn / no depth cap | Early Anthropic agents spawned 50 subagents for simple queries [1] | 16 concurrent / 1,000 total / depth 3 are shipped precedents [16][18] |
| No completion signal → deadlock | Teammates "fail to mark tasks as completed, which blocks dependent tasks" [15]; MAST FM-1.5 9.82%, FM-3.1 7.82% [6] | Deterministic completion detection; timeouts; stall detection [28] |
| Synchronous fan-out with no straggler policy | "The entire system can be blocked while waiting for a single subagent" [1] | Per-worker deadline; aggregate survivors; label the result partial |
| Piping worker transcripts through the orchestrator | "Game of telephone" [1]; 368.3k vs 45.5k tokens/success [28] | Artifact refs; reduce over conclusions, not transcripts [4] |
| Assuming more workers or options is monotonically better | Welfare fell as options grew 3→100 across all models [29] | Bound the consideration set; scale effort to query complexity [1] |
| Treating worker output as trusted | Injection redirected *all* payments for three models [29] | Schema-validated payloads; worker text is never control plane |

---

## 6. Design implications

*Normative. Each carries rationale and the tradeoff accepted.*

1. **Make "single writer" a hard invariant, above topology choice.** *Rationale:* the one rule both camps now agree on [1][2][3]. *Tradeoff:* write throughput caps at one agent, so write-heavy jobs must be restructured via deterministic sharding [4] rather than parallelised directly.
2. **Require a matched-budget A/B before shipping any fan-out.** *Rationale:* the compute confound is now the default explanation for MAS gains [7], supported by Anthropic's own variance analysis [1]. *Tradeoff:* needs a harness that pins token budgets, and single-agent may win — which is the point.
3. **Make the plan an artifact the runtime executes, not a prompt the model remembers.** *Rationale:* scripts and selectors are diffable, re-runnable and give provable coverage [4][16]; prompt-plans drift and over-prescribe [3]. *Tradeoff:* loses mid-run adaptivity (workflows forbid mid-run input [16]), so keep an interactive path for exploratory turns.
4. **Pass artifact references, not transcripts; where workers must share state, make writes typed and authorized.** *Rationale:* telephone loss and token blowup are both measured [1][28]. *Tradeoff:* schemas must be authored per task — PatchBoard needs an Architect agent to generate them [28].
5. **Publish hard caps as product contract:** concurrency, total workers, depth, per-run token/USD ceiling, per-worker deadline. *Rationale:* every mature implementation ships them with numbers [15][16][18][23]. *Tradeoff:* caps produce partial results, so the aggregator must emit a *labeled* partial — copy the "unverified, not refuted" distinction [16].
6. **Use MCP inside agents; reserve A2A for organizational boundaries.** *Rationale:* MCP has genuine scale and neutral governance [30]; A2A's headline benefit, coordination without shared internal memory [11], is a liability *inside* one product under rule 1. *Tradeoff:* forgoes cross-vendor composability until there is evidence it pays.
7. **For a second agent's quality contribution, give it a clean context and no write access.** *Rationale:* Cognition found the coder/reviewer loop works *best* when the two share no prior context [3]. *Tradeoff:* the reviewer raises out-of-scope findings, so a filtering bridge back through the writer's context is required [3].
8. **Do not adopt debate, consensus voting or MoA layering as default quality mechanisms.** *Rationale:* the only matched-cost evidence retrieved is negative or benchmark-narrow [8][9]. *Tradeoff:* gives up a cheap ensemble; revisit with a local eval if a closed-form sub-answer domain appears.

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
| 6 | Why Do Multi-Agent LLM Systems Fail? (MAST) — Cemri et al. | UC Berkeley et al. | 2025-03, arXiv:2503.13657v2 — *foundational: reference MAS failure taxonomy* | Preprint | https://arxiv.org/abs/2503.13657 |
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
| 28 | PatchBoard: Schema-Grounded State Mutation… — Zhang, Shi & Wang | Xidian University | 2026-05, arXiv:2605.29313v1 | Preprint (self-reported) | https://arxiv.org/html/2605.29313v1 |
| 29 | Magentic Marketplace: an open-source simulation environment for studying agentic markets | Microsoft Research | 2025 (paper arXiv:2510.25779) | Research blog + paper | https://www.microsoft.com/en-us/research/blog/magentic-marketplace-an-open-source-simulation-environment-for-studying-agentic-markets/ |
| 30 | Donating the Model Context Protocol and establishing the Agentic AI Foundation | Anthropic | 2025-12-09 | Vendor announcement | https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation |
| 31 | MAS-ProVe: Understanding the Process Verification of Multi-Agent Systems | Rutgers / Salesforce AI Research | 2026-02-04, arXiv:2602.03053 | Preprint | https://arxiv.org/pdf/2602.03053 |
| 32 | Verified Multi-Agent Orchestration (VMAO) | (authors) | 2026-03, arXiv:2603.11445v2 | Preprint (self-reported) | https://arxiv.org/html/2603.11445v2 |
| 33 | Terrarium: Revisiting the Blackboard for Multi-Agent Safety, Privacy, and Security Studies | (authors) | 2025-10, arXiv:2510.14312v1 | Preprint | https://arxiv.org/html/2510.14312v1 |

---

## 8. Proposed content for final doc sections

**Section 5 — Multi-agent topologies.** Open with the decision rule, not the catalogue: *choose a topology by asking who writes, not what can run in parallel.* Carry §2's topology table across as-is; it already has the columns the section needs. Then "The controversy, settled enough to build on" from F10–F13: both primary arguments quoted, Cognition's 2026 synthesis as the resolution, Tran & Kiela's corruption crossover as the boundary, and a plain statement that Anthropic's +90.2% is vendor-reported against an unpublished eval. Reuse §5's anti-pattern table verbatim.

**Section 6 — Orchestration & control flow.** Five subsections from F14–F18: (1) *state sharing* — five mechanisms, three shipped answers to conflicting writes; (2) *plan-to-execution binding* — script/selector as the strong form, prompt-plan as the weak one; (3) *interop* — MCP inside, A2A between, ACP/ANP not yet, member counts are not adoption; (4) *termination, budget, deadlock* — a defaults box (16 / 1,000 / 25 / 1.5M / depth-3 / `max_iterations`), the documented deadlock mode, and the unverified-vs-refuted distinction for partials; (5) *cost & latency* — every published multiplier **with its denominator**, and a standing rule that architecture claims state the token budget they were measured under. Cross-reference out: inner loop → WS1, verifier design → WS5, durable execution → WS7.
