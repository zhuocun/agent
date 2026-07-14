# Best AI Agent Architecture Design — Industry Research Brief (mid-2026)

**Status:** Research provenance (reviewed pass) for
[`docs/plans/02-agent-architecture.md`](../../plans/02-agent-architecture.md)  
**Pass index:** [README](./README.md)  
**Scope:** Agent *runtime* architecture (control loops, multi-agent orchestration, tools, memory, HITL, budgets, observability, failure modes) — not chat UX chrome or hosting stacks  
**Access date for all URLs:** 2026-07-14  
**Product context:** Olune — chat-anchored, flag-gated Deep Research fan-out ([`01-agentic-mode.md`](../../plans/01-agentic-mode.md))

---

## 1. Executive summary

What “best” means for a **production chat-anchored agent product** (as of mid-2026):

1. **Simplicity first, complexity earned.** Start with an augmented LLM + bounded tool loop; add multi-agent / graph / durable layers only when evals show clear gains (Anthropic *Building effective agents*, Dec 2024).
2. **Hard bounds are non-negotiable.** Cap rounds, tokens, USD, wall-clock, recursion depth, and fan-out; degrade to labeled partial synthesis rather than hang or silent overrun (OWASP LLM10:2025 Unbounded Consumption + Anthropic multi-agent research ops lessons).
3. **Separate planning from execution from verification.** Planner → workers → aggregator → (fresh-context) verifier / CitationAgent outperforms self-grading; treat worker output as untrusted structured data (Anthropic Research system + transferred harness lessons; OWASP LLM05 improper-output / LLM06 excessive-agency).
4. **Ownership of the user reply must be explicit.** Prefer manager-owns-answer (“agents as tools” / orchestrator-workers) for research synthesis; use handoffs only when a specialist should own the conversation (OpenAI Agents SDK).
5. **Deterministic skeleton + probabilistic flesh.** Encode routing, budgets, approvals, and retries in code/graph/workflow; leave only open-ended decomposition and tool choice to the LLM (Anthropic workflows vs agents; Google ADK 2.0 graphs; Temporal durable workflows).
6. **Sandbox tools; never trust model- or tool-shaped strings as authority.** Schema-validate tool args; isolate execution; never let subagent text resume HITL gates or rewrite system policy (OWASP LLM Top 10 / GenAI; transitive untrusted-output).
7. **Cost transparency is a product feature.** Multi-agent research burns ~15× chat tokens; meter live, attribute per worker, never silent model downgrade (Anthropic Research eng post; transparency contracts).
8. **HITL at consequential boundaries.** Plan approval before expensive fan-out; optional clarify-before-plan; tool approval for side effects; pause/resume via durable state, not polling loops (LangGraph interrupts; Temporal signals; OpenAI/ADK HITL).
9. **Observability is structural.** Emit OTel GenAI spans (`invoke_agent`, `execute_tool`, `invoke_workflow`, chat) as a parent/child tree across workers; agent failures are emergent and undiagnosable without traces (OTel GenAI semconv — Development status; Anthropic production reliability section).
10. **Chat-anchored products should not grow background agent platforms by accident.** In-turn orchestration with resumable streaming ≠ autonomous daemons; durable execution is for long-running *workflows* with an explicit product surface (Temporal deep-research tutorials vs Olune D23/D33 guardrail).

**Competing shapes (not one winner):** OpenAI Deep Research is a long-horizon single-agent ReAct-style browsing system (o3-class); Anthropic Research is orchestrator-workers with parallel subagents. For *parallel breadth* research, Anthropic’s published multi-agent pattern is the best-supported primary source — not an industry monopoly.

---

## 2. Canonical patterns catalog

### 2.1 Single-loop ReAct / tool-calling agent

| | |
| --- | --- |
| **Name** | Single-loop ReAct / native tool-calling agent |
| **When to use** | Default for chat+tools: open-ended steps, unpredictable path length, one conversation owner. Sufficient for most product turns before Deep Research. Also the published shape of OpenAI Deep Research (long-horizon browse/reason loop). |
| **Strengths** | Minimal moving parts; interpretable thought→act→observe traces; native function-calling APIs map cleanly; easy to bound (`max_rounds`, per-tool timeout); strong when a single context can hold the trajectory. |
| **Failure modes** | Unbounded loops / tool thrashing; hallucinated tools; quadratic context growth; compounding error without ground-truth tool feedback; weak parallel breadth when many independent sources must be covered at once. |
| **Citations** | Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, arXiv:2210.03629 (ICLR 2023) — https://arxiv.org/abs/2210.03629 ; https://react-lm.github.io/ ; Anthropic “Agents” section — https://www.anthropic.com/engineering/building-effective-agents ; OpenAI — *Introducing deep research* — https://openai.com/index/introducing-deep-research/ |

**Opinion:** This remains the **production default** for ordinary chat+tools. Anthropic’s autonomous-agent diagram is literally “LLM + tools in a loop with stopping conditions.” Modern APIs replace regex Thought/Action parsers with structured tool calls, but the control loop is the same. OpenAI’s Deep Research product demonstrates that a *well-trained* long-horizon single agent can also own the research category without fan-out.

---

### 2.2 Planner → workers → aggregator → verifier

| | |
| --- | --- |
| **Name** | Orchestrator-workers with synthesis + evaluation (multi-agent Deep Research shape) |
| **When to use** | Breadth-first, high-value queries where subtasks are parallelizable and exceed one context window; research / multi-source investigation. |
| **Strengths** | Parallel context windows compress search; separation of concerns; CitationAgent / fresh-context judge catches unsupported claims; Anthropic reported ~90% gain vs single-agent on internal research eval; parallelization cut research time up to ~90%. |
| **Failure modes** | ~15× token cost vs chat; vague sub-tasks → duplicated/gapped work; over-spawn (early Anthropic agents spawned ~50 workers); self-grading bias if verifier shares generator context; coordination thrash on highly sequential tasks (coding often poorer fit); sync lead waiting on worker batches creates head-of-line blocking (Anthropic production note). |
| **Citations** | Anthropic *How we built our multi-agent research system* (2025-06-13) — https://www.anthropic.com/engineering/multi-agent-research-system ; Anthropic *Building effective agents* — Orchestrator-workers + Evaluator-optimizer — https://www.anthropic.com/engineering/building-effective-agents ; Anthropic *Harness design for long-running apps* (Planner/Generator/Evaluator, fresh-context eval — **coding harness, Mar 2026**; transfer to research is analogy, not research-native evidence) — https://www.anthropic.com/engineering/harness-design-long-running-apps ; Wang et al., *Self-Consistency…*, arXiv:2203.11171 — https://arxiv.org/abs/2203.11171 (closed-form sub-answers only; see §3.8) |

**Opinion:** This is the **best-supported published multi-agent pattern for parallel breadth** (Anthropic Research eng post) — not the only Deep Research architecture in market. Critical design rules from Anthropic’s production write-up: (1) give each worker objective + output format + tools + boundaries; (2) scale effort to query complexity in the planner prompt; (3) start wide then narrow; (4) parallelize both workers and tool calls; (5) externalize the plan to memory before context truncates; (6) CitationAgent / verifier with independent (fresh) context; (7) prefer **structured worker artifacts** (filesystem / object refs) over stuffing full findings through the lead (“telephone”); (8) today’s lead often **waits synchronously** on subagent batches — async fan-out is a deliberate upgrade, not free; (9) consider an optional **clarify-before-plan** gate (OpenAI Deep Research / Temporal deep-research tutorial) before spending the ~15× budget.

**Harness→research transfer (labeled):** Anthropic’s Planner/Generator/Evaluator + fresh-context evaluator pattern is documented for *long-running coding* (2026-03). Applying that separation to research verification is a reasonable analogy (separate judge context beats self-grade) but is **not** research-native evidence; Anthropic Research’s published verifier path is CitationAgent + LLM-as-judge / fresh-context eval.

**Contrast — OpenAI Deep Research vs Anthropic multi-agent:** OpenAI Deep Research is a long-horizon **single-agent** ReAct-style browsing/reasoning system (o3-class), not Anthropic-style orchestrator-workers. Choose multi-agent when the product bet is parallel breadth + separate context windows; choose (or keep) a strong single-loop agent when the bet is extended CoT + tool use inside one trajectory. Do not treat multi-agent as automatic “best.”

---

### 2.3 Hierarchical / supervisor agents

| | |
| --- | --- |
| **Name** | Hierarchical supervisor / manager–specialist (agents-as-tools) |
| **When to use** | Stable outer conversation ownership; specialists for bounded skills (summarize, classify, billing policy); shared guardrails at one choke point. |
| **Strengths** | Clear reply ownership; policy isolation; parallel specialist calls under one manager; easier UX (one answer stream); CrewAI/OpenAI first-class support. |
| **Failure modes** | God-manager prompt bloat; premature splitting (more prompts/traces/approvals without gain); specialists as tools still consume manager context when results return; deep hierarchies without depth caps. |
| **Citations** | OpenAI Agents SDK — Agents as tools vs handoffs — https://openai.github.io/openai-agents-python/multi_agent/ ; https://developers.openai.com/api/docs/guides/agents/orchestration ; CrewAI Hierarchical process — https://docs.crewai.com/en/concepts/processes ; https://docs.crewai.com/en/learn/hierarchical-process ; Microsoft Magentic-One Orchestrator + Task/Progress ledgers — https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/ ; https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/magentic-one.html |

**Opinion:** For chat products, **supervisor + agents-as-tools ≈ orchestrator-workers** with the manager keeping the microphone. Prefer this over peer handoffs when the product promise is “one assistant answers.” Magentic-One’s nested Task Ledger / Progress Ledger is the research-grade version of plan + stall detection.

---

### 2.4 Swarm / peer multi-agent

| | |
| --- | --- |
| **Name** | Swarm / peer handoffs / decentralized group chat |
| **When to use** | Routing is part of the UX (triage → billing specialist owns the rest of the turn); multi-party simulation; domains where specialists should speak directly. |
| **Strengths** | Focused specialist prompts; clean ownership transfer; modular agents; OpenAI Swarm→Agents SDK lineage keeps this lightweight. |
| **Failure modes** | Ping-pong / handoff loops; lost shared guardrails; user-facing identity confusion; harder cost attribution across peers; emergent coordination failures without a ledger. |
| **Citations** | OpenAI handoffs docs (above); AutoGen / Magentic-One as *orchestrated* peers under a lead (not pure swarm) — Magentic-One PDF — https://www.microsoft.com/en-us/research/wp-content/uploads/2024/11/MagenticOne.pdf |

**Opinion:** Pure peer swarms are **rarely best for a single-brand chat product**. Use handoffs for support triage; keep breadth research on manager-owned synthesis (or a single long-horizon agent). If peers are used, impose max handoffs and a sticky “conversation owner” for attribution.

---

### 2.5 Graph / state-machine orchestration (LangGraph-style)

| | |
| --- | --- |
| **Name** | Graph / workflow state-machine (nodes + edges + reducers) |
| **When to use** | Mixed deterministic + LLM steps; explicit branches; loops with coded exit criteria; HITL interrupt nodes; need for time-travel / replay. |
| **Strengths** | Predictable control flow; testable edges; checkpointed thread state; parent `invoke_workflow` spans; Google ADK 2.0 (Python GA 2026-05-19) converges on the same graph/workflow model. |
| **Failure modes** | Over-graphing simple chat; large payloads in state → checkpoint bloat; subgraph checkpointer misuse; framework opacity if teams stop reading prompts. |
| **Citations** | LangGraph Persistence (checkpointer vs store) — https://docs.langchain.com/oss/python/langgraph/persistence ; Google ADK 2.0 — https://adk.dev/2.0/ ; ADK graph-based workflows — https://adk.dev/graphs/ ; Google Developers Blog multi-agent patterns in ADK — https://developers.googleblog.com/en/developers-guide-to-multi-agent-patterns-in-adk/ (short: https://goo.gle/3Ng8qVt ); Anthropic workflows vs agents distinction — https://www.anthropic.com/engineering/building-effective-agents |

**Opinion:** Graphs shine when **policy and budget must be deterministic**. Deep Research can be a small graph: `plan → (clarify?) → (approve?) → fanout → aggregate → (verify?) → respond`, with each LLM node still running a ReAct loop. Do not replace a 50-line asyncio orchestrator with a heavy framework unless checkpointing/HITL require it.

---

### 2.6 Durable / checkpointed agents (Temporal, Workflows)

| | |
| --- | --- |
| **Name** | Durable execution / workflow-checkpointed agents |
| **When to use** | Runs that must survive process crash, wait hours/days for HITL, auto-retry rate-limited LLM calls, or outlive a single HTTP request — *and* the product explicitly supports that lifecycle. |
| **Strengths** | Crash-proof progress; activity retries without re-paying completed LLM steps; indefinite HITL wait without burning compute; Temporal↔OpenAI Agents SDK integration; LangGraph Postgres checkpointers for shorter thread durability; tutorials often include clarify-before-research gates. |
| **Failure modes** | Wrong product fit for “one SSE chat turn”; non-deterministic workflow code breaks replay; expensive activity retry storms; MCP/external tools need their own durability; operational complexity (workers, task queues). |
| **Citations** | Temporal + OpenAI Agents SDK — https://temporal.io/blog/announcing-openai-agents-sdk-integration ; Temporal Python contrib README — https://github.com/temporalio/sdk-python/blob/main/temporalio/contrib/openai_agents/README.md ; Temporal Learn: Deep Research tutorial — https://learn.temporal.io/tutorials/ai/deep-research/setting-the-stage/ ; LangGraph persistence (above) |

**Opinion:** Durable agents are the **right answer for background automation platforms**, not the default for chat-anchored Deep Research. Chat products should first use: in-request asyncio fan-out + resumable SSE buffers + explicit Stop ≠ disconnect. Graduate to Temporal when runs routinely exceed request/worker lifetime or need multi-hour approvals.

---

## 3. Cross-cutting design principles

### 3.1 Hard bounds (rounds, tokens, $, wall-clock, recursion depth, fan-out)

- Encode **max tool rounds**, **per-tool timeouts**, **max workers**, **max concurrency**, **max depth**, **per-run USD**, and **wall-clock** as code invariants, not prompt suggestions.
- Map directly to OWASP **LLM10:2025 Unbounded Consumption** — the Top-10 risk most tied to fan-out, runaway tool loops, and uncapped $ spend (https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/).
- Anthropic’s Research team had to teach planners to *scale effort to complexity* after agents over-invested; pair soft heuristics with hard caps.
- On breach: **cancel in-flight work**, aggregate survivors, emit **labeled partial** outcome — never opaque hang.
- Admission control: **pre-spawn cost reservation** + **mid-flight kill** (estimate then true-up).

### 3.2 Tool sandboxing + untrusted tool output

- OWASP GenAI / LLM Top 10: treat LLM output and tool results as **untrusted** — **LLM05:2025 Improper Output Handling** and **LLM06:2025 Excessive Agency** (prompt injection → improper output handling → excessive agency chain). Keep **LLM10 Unbounded Consumption** for the budget/fan-out layer (§3.1), not as a substitute for output/agency hygiene.
- Validate tool **arguments** with schemas/allowlists before execution; least-privilege credentials; isolate code exec (Wasm / micro-VM).
- **Transitive untrusted-output:** subagent findings fed to aggregator as structured data / artifact refs only — never spliced into system/safety instructions; never treat worker text as HITL approval.
- Invest in **ACI** (agent–computer interface): tool docs as carefully as prompts (Anthropic Appendix 2).

### 3.3 HITL / approval gates

- Gate **high-impact side effects** and **expensive plan fan-outs**.
- Optional **clarify-before-plan** (OpenAI Deep Research UX; Temporal deep-research tutorial triage/clarifying agents) before committing the ~15× token budget.
- Implement as durable pause states (`awaiting_approval`, LangGraph `interrupt_*`, Temporal signals) with resume tokens — not “model says approved.”
- Keep approval UI bound to **server-issued** plan/tool ids; ignore forged strings in content.

### 3.4 Cost attribution & transparency

- Multi-agent research ≈ **15×** chat tokens; single agents ≈ **4×** (Anthropic Research eng post). Product must meter and gate entitlement.
- Roll up cost as **sum of parts** (planner + workers + aggregator + verifier); persist **per-worker** model attribution; **no silent downgrade**.
- Live run-cost meter during fan-out is now table stakes for trust.

### 3.5 Observability (OTel GenAI spans)

- Standardize on OpenTelemetry GenAI semantic conventions (**Development** status through mid-2026, but de facto industry vocabulary): `chat`, `invoke_agent`, `execute_tool`, `invoke_workflow`, etc.
- Multi-agent: parent workflow/orchestrator span → child `invoke_agent` per worker → `execute_tool` / `chat` leaves.
- Anthropic: production tracing was required to debug “agent didn’t find obvious info”; monitor decision patterns without logging private contents where policy forbids.
- Primary refs (canonical — GenAI semconv moved out of the main `semantic-conventions` tree): https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md ; https://opentelemetry.io/docs/specs/semconv/gen-ai/ (redirects / points at the GenAI conventions repo).

### 3.6 Idempotency / resumability

- Distinguish **client disconnect** from **user cancel** when resumable streams are on.
- Checkpoint after meaningful steps; on retry, skip completed LLM/tool activities (Temporal event history) or resume from last checkpoint (LangGraph).
- Rainbow / dual-version deploys for long-lived agent processes (Anthropic production section).
- Idempotent tool design where side effects exist (dedupe keys).

### 3.7 Context / memory layering

| Layer | Scope | Mechanism |
| --- | --- | --- |
| In-turn scratch | Current ReAct loop | Message list / thinking tokens |
| Orchestration state | One Deep Research run | Plan ledger, worker artifact refs, budget counters |
| Thread / conversation | Cross-turn chat | Checkpointer or DB messages |
| Long-term user/org | Cross-thread | Store / preferences / RAG — separate from run state |

- Anthropic harness (coding, transferred lesson): prefer **context resets between roles** (planner / generator / evaluator) over lossy compaction when fidelity matters.
- Lead researcher should **persist the plan** before context truncation (~200k warning in Anthropic Research post).
- Anthropic Research appendix: **subagent → filesystem / artifact store** with lightweight refs back to the lead — reduces token overhead and “game of telephone.”
- LangGraph: checkpointer = short-term thread; store = long-term facts.

### 3.8 Evaluation / verifier / self-consistency

- For **free-form research reports**, prefer Anthropic Research’s published path: **CitationAgent** + **LLM-as-judge / fresh-context evaluator** — not generator self-grade, and **not** N-way majority vote over whole reports.
- Fresh-context separation is reinforced by the coding harness (Mar 2026) as a **transferred** lesson: separate judge context is easier to tune skeptical than making a generator self-critical.
- **Self-consistency** (sample N paths, majority vote — Wang et al. 2022/ICLR 2023) remains a cheap verifier for **closed-form sub-answers** (facts, IDs, numeric fields). Do **not** equate product knobs like `AGENTIC_VERIFIER_N` with Wang majority vote over free-form synthesis without an explicit caveat and eval proof.
- LLM-as-judge with explicit rubrics scales research-output eval; keep a small golden set early (Anthropic: ~20 queries caught large effect sizes).
- Human eval still required for source-quality bias and weird edge cases.

---

## 4. Anti-patterns to avoid

| Anti-pattern | Why it fails | Prefer instead |
| --- | --- | --- |
| **Unbounded recursion / fan-out** | Cost explosions, spawn storms (Anthropic early Research); OWASP LLM10 | Hard `max_depth`, `max_workers`, effort scaling rules, $ / wall-clock caps |
| **Silent model downgrade** | Breaks trust & attribution contracts | Surface substitution per worker; fail or pause if policy requires |
| **God-agent** | One prompt owns every skill → shallow results, unmaintainable | Specialists + orchestrator; split only when contract changes (OpenAI) |
| **Background agents without chat anchor** (when product forbids) | Orphan runs, unclear cancel/billing UX, support burden | In-turn orchestration; or explicit workflow product surface |
| **Framework opacity** | Can’t debug prompts/tools | Start with thin loops; understand codegen; reduce abstraction in prod (Anthropic) |
| **Trusting tool/LLM strings as control plane** | Prompt injection / HITL bypass (LLM05/LLM06) | Server-side gates; schema validation; untrusted-output hygiene |
| **Self-verifier in same context** | Positive bias | Fresh-context CitationAgent / LLM-as-judge |
| **Majority-vote over free-form reports** | Wang self-consistency is for closed-form answers | CitationAgent + rubric judge; reserve N-sample vote for atomic facts |
| **Checkpointing huge blobs / stuffing full worker text into lead** | DB/memory collapse; telephone loss | Artifact refs (S3/filesystem); prune TTL |
| **Assuming async fan-out is free** | Anthropic lead historically sync-waits on batches | Design for sync head-of-line; upgrade async deliberately |
| **Multi-agent for sequential coding by default** | Anthropic: coding less parallelizable; coordination weak | Single coding agent + tests; hierarchical only for clear file splits |
| **Evals delayed until “large suite”** | Miss 30%→80% wins | Tiny golden set from day one |
| **Restart-from-scratch on any error** | User pain + double spend | Resume/checkpoint + adaptive tool failure messaging |
| **Treating multi-agent as the only Deep Research shape** | OpenAI Deep Research is long-horizon single-agent | Pick shape by breadth vs long CoT bet; evaluate both |

---

## 5. Recommendation matrix

| Product shape | Primary architecture | Secondary pieces | Avoid |
| --- | --- | --- | --- |
| **Simple chat + tools** | Single ReAct / tool loop | Round/timeout bounds; OTel `chat`+`execute_tool`; optional tool HITL | Multi-agent fan-out; Temporal |
| **Deep research / breadth investigation** | Planner → parallel workers → aggregator → CitationAgent / fresh-context judge | Hard fan-out & $ caps (LLM10); plan approval; optional clarify-before-plan; live cost meter; per-worker attribution; structured worker artifacts; untrusted worker payloads | Peer swarm ownership; unbounded nested orchestrators; equating `VERIFIER_N` with free-form majority vote |
| **Deep research / long-horizon single trajectory** | Strong single-agent ReAct (OpenAI Deep Research shape) | Iteration / wall-clock / fetch caps; citations; resume | Forced multi-agent when sources aren’t parallelizable |
| **Coding agent** | Single agent + rich ACI tools + tests as ground truth; optional evaluator loop | Sandbox; git checkpoints; sprint contracts (Anthropic harness) | Large peer swarms; premature multi-agent |
| **Support / triage** | Handoffs *or* supervisor with specialists | Narrow specialist tools; shared policy at edge | Deep Research-style 15× spend on FAQ |
| **Long-running background automation** | Durable workflow (Temporal) or graph+Postgres checkpointer | Signals for HITL; clarify gates; activity retries; rainbow deploys | Tying run lifetime to a browser SSE without durability |
| **Enterprise mixed workflows** | ADK/LangGraph-style deterministic graph with LLM nodes | Explicit HITL nodes; retries; nested workflows | Prompt-only control of compliance steps |

---

## 6. Sources

| # | Source | URL | Accessed |
| --- | --- | --- | --- |
| 1 | Anthropic — Building effective agents | https://www.anthropic.com/engineering/building-effective-agents | 2026-07-14 |
| 2 | Anthropic — How we built our multi-agent research system | https://www.anthropic.com/engineering/multi-agent-research-system | 2026-07-14 |
| 3 | Anthropic — Harness design for long-running application development (coding harness; transferred lessons) | https://www.anthropic.com/engineering/harness-design-long-running-apps | 2026-07-14 |
| 4 | Yao et al. — ReAct (arXiv:2210.03629) | https://arxiv.org/abs/2210.03629 | 2026-07-14 |
| 5 | ReAct project site | https://react-lm.github.io/ | 2026-07-14 |
| 6 | Wang et al. — Self-Consistency (arXiv:2203.11171) | https://arxiv.org/abs/2203.11171 | 2026-07-14 |
| 7 | OpenAI Agents SDK — Agent orchestration | https://openai.github.io/openai-agents-python/multi_agent/ | 2026-07-14 |
| 8 | OpenAI API — Orchestration and handoffs | https://developers.openai.com/api/docs/guides/agents/orchestration | 2026-07-14 |
| 9 | LangGraph — Persistence | https://docs.langchain.com/oss/python/langgraph/persistence | 2026-07-14 |
| 10 | Google ADK 2.0 (canonical docs; Python GA 2026-05-19) | https://adk.dev/2.0/ | 2026-07-14 |
| 11 | Google ADK — Graph-based workflows | https://adk.dev/graphs/ | 2026-07-14 |
| 12 | Google Developers — Multi-agent patterns in ADK | https://goo.gle/3Ng8qVt | 2026-07-14 |
| 13 | CrewAI — Processes | https://docs.crewai.com/en/concepts/processes | 2026-07-14 |
| 14 | CrewAI — Hierarchical process | https://docs.crewai.com/en/learn/hierarchical-process | 2026-07-14 |
| 15 | Microsoft Research — Magentic-One | https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/ | 2026-07-14 |
| 16 | Magentic-One technical report (PDF) | https://www.microsoft.com/en-us/research/wp-content/uploads/2024/11/MagenticOne.pdf | 2026-07-14 |
| 17 | AutoGen — Magentic-One user guide | https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/magentic-one.html | 2026-07-14 |
| 18 | Temporal — OpenAI Agents SDK integration | https://temporal.io/blog/announcing-openai-agents-sdk-integration | 2026-07-14 |
| 19 | Temporal SDK — openai_agents contrib | https://github.com/temporalio/sdk-python/blob/main/temporalio/contrib/openai_agents/README.md | 2026-07-14 |
| 20 | Temporal Learn — Deep research (setting the stage) | https://learn.temporal.io/tutorials/ai/deep-research/setting-the-stage/ | 2026-07-14 |
| 21 | OWASP — Top 10 for LLM Applications / GenAI Security | https://owasp.org/www-project-top-10-for-large-language-model-applications/ ; https://genai.owasp.org/llm-top-10/ | 2026-07-14 |
| 22 | OWASP Top 10 for LLMs 2025 (PDF) | https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf | 2026-07-14 |
| 22b | OWASP LLM10:2025 Unbounded Consumption | https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/ | 2026-07-14 |
| 23 | OpenTelemetry GenAI spans (canonical: `semantic-conventions-genai`) | https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md | 2026-07-14 |
| 24 | OpenAI — Introducing deep research | https://openai.com/index/introducing-deep-research/ | 2026-07-14 |
| 25 | Olune — Agentic Mode Plan (product grounding, not industry claim) | [`docs/plans/01-agentic-mode.md`](../../plans/01-agentic-mode.md) | 2026-07-14 |
| 26 | Olune — Agent Architecture (normative design this brief grounds) | [`docs/plans/02-agent-architecture.md`](../../plans/02-agent-architecture.md) | 2026-07-14 |

---

## 7. Implications for a chat-anchored, flag-gated Deep Research fan-out product

Olune’s shipped shape (`AGENTIC_ENABLED` ∧ `TOOLS_ENABLED`; modes `single` | `deep_research`; planner → workers → aggregator → optional verifier; hard `AGENTIC_MAX_*` + `AGENTIC_RUN_BUDGET_USD`; plan-approval HITL; OTel agent/tool spans; **no** out-of-turn daemons) is **aligned with the best-supported published multi-agent pattern for parallel breadth** (Anthropic Research) — not a claim that every mid-2026 Deep Research product converges on the same architecture:

1. **Keep `single` = ReAct loop as the default.** Most turns should not pay the ~15× multi-agent tax; OpenAI Deep Research also shows a strong single-agent path exists for research-class work.
2. **Treat Olune `deep_research` as Anthropic-style orchestrator-workers**, not AutoGen peer swarm or Temporal workflow — appropriate for chat-anchored SSE turns that bet on *parallel breadth*. Document the OpenAI long-horizon single-agent shape as a competing alternative, not a discarded one.
3. **Double down on production lessons Anthropic published:** rich worker task specs, effort scaling, parallel tool calls inside workers, CitationAgent / fresh-context judge, resume-friendly error handling, full span trees, **structured worker artifacts** (refs, not full dumps into the lead), and explicit handling of **sync vs async** fan-out (lead head-of-line wait is the current published default).
4. **Finish the transparency/safety edges:** live cost meter, per-worker substitution callouts, no silent downgrade, transitive untrusted-output into the aggregator, plan-approval before spend, and hard caps framed as **LLM10 Unbounded Consumption** mitigations.
5. **Do not “upgrade” to durable background agents** unless/until the product explicitly adds a long-running workflow surface; until then, invest in resumable stream buffers sized for fan-out event volume and Stop≠disconnect semantics.
6. **Verifier:** prefer CitationAgent and/or fresh-context LLM-as-judge over generator self-check. If `AGENTIC_VERIFIER_N` exists, **do not treat it as Wang self-consistency over free-form reports** without caveat — reserve N-sample majority vote for closed-form sub-answers; keep the whole verifier path flag-gated for cost.
7. **Depth bound default 1** is the right anti-pattern guard against recursive orchestrator trees; raise only with eval proof.
8. **Entitlement gate on `deep_research`** matches Anthropic’s economic framing: multi-agent is for high-value parallelizable work, not free-tier chatter.
9. **Optional clarify-before-plan** (OpenAI Deep Research / Temporal tutorial pattern) before fan-out spend — product decision, not required by Anthropic’s published Research post, but high leverage for chat UX and budget control.

**Normative design-doc stance (adopted in plan 02):** Standardize on *bounded orchestrator-workers over reused single-loop workers* for Olune’s breadth bet, with deterministic budget/HITL/observability shell — and document Temporal/graph durability as an explicit future product mode, not a silent evolution of the chat turn. Keep single-agent long-horizon research as an evaluated alternative, not an afterthought. See [`02-agent-architecture.md`](../../plans/02-agent-architecture.md).

### 7.1 Open questions / competing shapes (claim confidence)

| Question | Confidence today | Notes |
| --- | --- | --- |
| Is orchestrator-workers always better than a strong long-horizon single agent for research? | **Low–medium** | Anthropic’s +90% is on *their* internal eval with Opus lead + Sonnet workers; OpenAI ships a competitive single-agent Deep Research product. Needs Olune-local eval. |
| Sync vs async worker batches | **Medium** | Anthropic documents sync wait + desire for async; async adds coordination/error-propagation cost. |
| Artifact store vs inline worker text | **High** (direction) | Anthropic appendix strongly recommends filesystem/artifact refs; implementation detail open. |
| Clarify-before-plan as default HITL | **Medium** | Present in OpenAI/Temporal flows; optional for Olune depending on latency/UX. |
| `AGENTIC_VERIFIER_N` semantics | **Low** until defined | Must not silently mean free-form majority vote; prefer CitationAgent + judge. |
| When to adopt Temporal/ADK graphs | **Medium** | Clear when runs outlive SSE/worker lifetime or need multi-hour HITL; premature for in-turn fan-out. |
| OTel GenAI semconv stability | **Medium** | Still **Development** mid-2026; vocabulary is de facto but attributes may shift. |

---

*End of brief.*
