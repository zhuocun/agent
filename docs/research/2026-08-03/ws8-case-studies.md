# WS8 — Shipped agent systems and framework selection
**Scope:** Comparable architectures of shipped coding, research, computer-use, and enterprise agents; framework selection and migration reality | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS1–WS7 for loop, memory, tool, verification, safety, observability, and HITL mechanism depth

## 1. Executive summary

- **[high] The shipped-system consensus is a bounded model–tool–environment loop, not a peer “swarm.”** Coding products repeatedly combine repository search/read/edit, shell, tests, and an isolated workspace. Research products combine plan, search/read, code, synthesis, and citations. Computer-use products iterate screenshot → action → observation. Parallel agents exist, but usually behind one coordinator with isolated contexts and centralized synthesis. [S3–S8, S12–S20]
- **[high] State has separated into layers.** Products keep an event/thread history, compact or summarize it under context pressure, persist explicit plans/notes, and put long-lived user/repository memory outside the active trajectory. Examples include Codex compaction, OpenHands condensers and append-only events, Claude/Cursor subagent contexts, Google managed Sessions, and Mastra observational memory. [S1, S2, S3, S6, S24, S33]
- **[high] Verification is environmental.** Coding agents run tests or browser checks; research agents verify citations; consequential computer actions require confirmation. Product-wide reliability and cost data remain rare, and vendor benchmarks are not interchangeable.
- **[high] Frameworks converge on the same primitives but differ in ownership.** A thin SDK owns a tool loop; a graph framework owns state transitions/checkpoints; Temporal owns durable distributed execution; enterprise platforms additionally own sandbox/runtime, identity, memory, gateway, and telemetry. Every option still leaves product policy, tool semantics, evals, data governance, and user experience to the application.
- **[medium, normative] For a small chat-anchored team, keep the existing explicit loop and add a framework only for a demonstrated missing capability.** OpenAI Agents SDK or LangChain 1.x can remove loop boilerplate; LangGraph is justified by pause/resume and explicit branching; Temporal is justified only when runs must survive process lifetimes. This minimizes churn and preserves inspectability, at the cost of building persistence/streaming/approvals deliberately.

## 2. Findings

### 2.1 Coding agents: what actually ships

| System | Loop, tools, state / compaction | Subagents, verification, HITL, published data |
|---|---|---|
| **Claude Code** | **[high]** Adaptive `gather context → take action → verify` loop over files, search, shell, web and code intelligence. It clears old tool output before summarizing; `CLAUDE.md`/auto-memory persist outside compacted history. | Subagents have fresh context and return a summary; checkpoints, permission modes, tests and user steering provide control/evidence. Product-level success/cost data are undisclosed. [S1] |
| **Cursor Agent + background agents** | **[high]** Parent delegates to foreground/background subagents with separate context; cloud subagents get their own VM and branch. Completed subagents can be resumed with preserved context. | This is manager-to-workers, not peer chat. The cited subagent page does not disclose product-wide verification accuracy or cost distributions. [S2] |
| **OpenAI Codex** | **[high]** OpenAI’s cited architecture post explicitly scopes itself to the Codex CLI harness: a model↔tool loop with append-only history and automatic Responses compaction using an opaque compaction item. | The post says the harness underlies Codex experiences, but does not disclose Codex Cloud’s sandbox/parallel topology; this memo does not transfer CLI implementation details to Cloud. Product reliability/cost is undisclosed. [S3] |
| **GitHub Copilot cloud agent** | **[high]** Research → plan → edit → test in an ephemeral GitHub Actions environment, one repository/branch/PR per session (hard maximum 59 minutes). MCP, Playwright, instructions, skills and hooks extend tools; Copilot Memory is preview. | Custom specialists exist, but public cloud-agent docs do not disclose an internal multi-agent topology. User reviews diffs/logs/commits before PR/merge. Costs consume Actions minutes plus AI credits; no success rate is published. [S4] |
| **Devin / managed Devins** | **[high, vendor claim]** A coordinator scopes work and launches full workers in isolated VMs with terminal, browser, clean context and tests; it monitors trajectories and resolves conflicts. [S5] Cognition’s June 2025 warning was about dispersed decisions/context and conflicting parallel writes, not all delegation. [S8] | Its April 2026 reconciliation: useful production shapes keep writes single-threaded (reviewer/researcher/“smart friend”) or use centrally managed map-reduce for independent children—not free-form swarms. Devin Review, a clean-context reviewer iterating with the writer, reportedly finds **2 bugs/PR on average, ~58% severe**; reporter Cognition, Apr. 2026, on Devin-authored PRs, with model, sample size and adjudication undisclosed. [S18] |
| **OpenHands** | **[high]** Stateless single-step reason/action loop reads typed append-only events, condenses history, queries the LLM, emits action events, executes tools and records observations. | Pending actions can wait for confirmation and a security analyzer can assess risk. Multi-agent composition is not described by the cited core-loop page; fleet reliability/cost is undisclosed. [S6] |
| **Aider** | **[high]** Interactive Git-oriented code/ask/architect modes; architect mode uses an architect model followed by an editor model. | User controls turns; configurable auto-lint/auto-test can feed failures back. The second model adds latency/cost. No first-class swarm or current fleet reliability data is disclosed. [S7] |
| **Amp / Jules** | **[medium]** Amp documents persistent shareable threads, file/shell tools, automatic isolated-context subagents and an “Oracle”; its manual explicitly rejects backward compatibility. Jules is asynchronous: each requested task runs in a temporary remote VM, syncs with GitHub, tests, and returns a PR; multiple sessions can run in parallel. | Amp exposes ask/reject/allow/delegate permissions; Jules is steered through web/CLI. Internal compaction, verifier topology, and comparable success/cost are undisclosed for both. [S9, S10] |

### 2.2 Research, computer-use, and enterprise systems

| System | Concrete architecture | Verification / HITL / evidence |
|---|---|---|
| **OpenAI Deep Research** | **[high]** The reviewed system card describes early o3 optimized for persistent browsing, web/PDF/image reading, uploaded files and Python, ending in a cited report. | Safety training targets prompt injection and privacy. Subagent topology, compaction, citation-verifier design, HITL and product-wide cost/reliability are not characterized there. [S11] |
| **Anthropic Research** | **[high]** LeadResearcher saves its plan to Memory before 200K truncation, delegates and iterates, synthesizes, then passes documents/findings to a CitationAgent. Parallel batches are typically 3–5 workers with 3+ tool calls each, but complex queries may use **more than 10 subagents**; 3–5 is not a total architecture limit. | Anthropic-reported June 2025 internal eval: Opus 4 lead + Sonnet 4 workers beat single Opus 4 by **90.2%**; the exact comparison-set size is unstated. Evaluation method is disclosed: an initial ~20-query real-usage set, then a single LLM judge scoring factual accuracy, citation accuracy, completeness, source quality and tool efficiency from 0–1 plus pass/fail, supplemented by humans. Anthropic also reports roughly **15× chat tokens**. [S12] |
| **Gemini Deep Research** | **[high]** Managed long-running planning, iterative search/read and synthesis with Google Search, URL Context, Code Execution, files and optional MCP tools. `background=true` is mandatory. | Collaborative planning can return a plan for user edit/approval before execution; streaming can expose progress/thought summaries and cited output. Subagent topology, compaction, verifier internals and cost/reliability distributions are undisclosed on this page. [S13] |
| **Perplexity Deep Research / Computer** | **[medium, vendor claim]** “Search as Code” says the model writes a retrieval program and executes thousands of parallel steps in a secure sandbox, adapting as scored results arrive and deduplicating/filtering before synthesis. | Model version, worker topology, compaction, verifier, HITL and reproducible cost/reliability harness are undisclosed on this page. [S14] |
| **Operator/CUA; Claude computer use** | **[high]** OpenAI’s **Jan. 23, 2025** CUA combines GPT‑4o vision with RL-trained advanced reasoning and loops over screenshots plus mouse/keyboard actions. OpenAI reported exact CUA scores: **38.1% OSWorld, 58.1% WebArena, 87.0% WebVoyager**. [S15] Its addendum specifies pass@1 autoregressive sampling, temperature 0.6, maximum 200 steps; WebArena/WebVoyager ran in the Operator browser (not Playwright), 35 broken WebVoyager tasks were removed, and OSWorld used the VMware Ubuntu image with the dock moved right, which slightly improved performance. [S26] | Anthropic reported Sep. 29, 2025 Claude Sonnet 4.5 at **61.4% OSWorld-Verified**, official harness, **100-step** cap, mean of four runs. [S16] OpenAI’s 200-step default versus Anthropic’s 100-step cap, different revisions and live-site filtering preclude direct ranking. Both recommend human control for consequential actions; memory/subagents are undisclosed. |
| **Manus / browser-agent products** | **[medium, vendor claim]** Manus Wide Research uses a controller to decompose work, launch full Manus instances with separate VM/network/context/tool libraries, prevent worker-to-worker communication, and synthesize results. OpenAI Operator/CUA and Claude computer use provide the separate shipped screenshot-action browser pattern. | Manus centralizes coordination; its quantitative scalability claims lack a reproducible harness. Browser agents remain reliability-limited and need confirmation at consequential boundaries. [S15–S17] |
| **Enterprise platforms** | **[high]** OpenAI Agents SDK owns loop, sessions, streaming, handoffs/agents-as-tools, guardrails, approvals and traces; the app owns deployment/tools/storage. Microsoft Agent Framework combines agents, a long-task harness and typed graph workflows; Copilot Studio exports OTel-aligned agent/tool traces. AWS AgentCore—**GA Oct. 13, 2025**—supplies framework-neutral isolated runtime, memory, identity, gateway and OTel observability; AWS demonstrates Strands as the model/tool agent layer but permits replacement by another framework. [S19–S23] Google’s **Gemini Enterprise Agent Platform**, launched Apr. 22, 2026 as the evolution of Vertex AI, combines upgraded ADK, Agent Runtime, Memory Bank, identity/registry/gateway, evaluation and observability. [S24] |

### 2.3 Framework comparison: abstraction and cost

| Framework | Control/state/stream/HITL/observability/multi-agent | Lock-in, churn, and what remains yours |
|---|---|---|
| **LangChain 1.x + LangGraph 1.x** | **[high]** `create_agent` is a middleware-wrapped ReAct loop on LangGraph; the underlying runtime supplies persistence, durable execution, streaming and HITL. | Moderate semantic lock-in to message/state/runtime types. v1 moved legacy chains to `langchain-classic` and replaced LangGraph’s prebuilt `create_react_agent`; still build storage, tool safety, evals and product policy. [S25] |
| **OpenAI Agents SDK** | **[high]** Runner loop, sessions, streams, guardrails, resumable approvals, traces, handoffs and manager “agents as tools.” | Low–moderate SDK lock-in, higher when using hosted OpenAI tools/models. Agent Builder’s June 2026 wind-down (shutdown Nov. 30, 2026) is direct evidence that managed visual surfaces churn; app still owns tools, persistence choice, deployment and policy. [S19, S20] |
| **AutoGen / AG2 → Microsoft Agent Framework / Semantic Kernel** | **[high]** AutoGen 0.4 broke from 0.2 with an event-driven rewrite. Microsoft now calls Agent Framework the successor, combining AutoGen’s agent abstractions with Semantic Kernel’s session state, typing, middleware and telemetry, plus graph checkpoints/workflow HITL. AG2 independently ships append-only memory, compaction, middleware, parallel tools, observers and hub networks. | Highest sampled migration risk: rewrite, fork/ownership confusion, then successor. Business tools, evaluation, deployment and policy remain yours. [S21, S27, S28] |
| **CrewAI** | **[high]** Flow-first explicit branches/loops/state/persistence around role-based Crews; async kickoff, guardrails, structured outputs and tracing. | Role/task vocabulary can over-model simple work; managed deployment/observability encourages platform coupling. Build tool semantics, evals and secure runtime. [S29] |
| **smolagents** | **[high]** Minimal `MultiStepAgent` ReAct with JSON tool calls or generated Python, step memory/callbacks and optional planning. | Low code lock-in; pinned here to v1.26.0. Persistence, durable HITL, telemetry, multi-agent policy and sandbox hardening remain yours. [S30] |
| **Pydantic AI** | **[high]** Typed agents/dependencies/outputs use an internal executable graph; runs expose node/tool event streams and tools can require approval. | Python/type-model coupling but relatively low provider lock-in. Durable persistence, production UI, evals, tracing backend and policy remain application/integration work. [S31] |
| **DSPy** | **[high]** Declarative signatures/modules; `ReAct` supplies bounded thought/tool/observation loop and trajectory, while optimizers tune prompts/examples against a metric. | Optimization is the differentiator, not runtime durability. You supply datasets/metrics, persistence, approvals, streaming UI, sandbox and orchestration. [S32] |
| **Mastra** | **[medium]** Its cited Observational Memory feature uses background Observer/Reflector agents to replace growing raw history with dense append-only observations. | This feature couples memory to Mastra’s storage/runtime; the reviewed page does not establish its broader streaming/HITL surface. Evals, permissions and failure policy remain yours. [S33] |
| **Temporal custom build** | **[high]** Native-code Workflow controls deterministic orchestration; LLM/tool calls are retryable Activities; event history enables crash recovery, long waits and horizontal workers. Updates/Signals support HITL, traces integrate with the agent SDK, and the OpenAI integration became GA Mar. 2026. | Operational/runtime commitment is substantial and replay determinism constrains code. Token streaming/UI, prompts, agents, tools, evals and policy remain yours. [S34] |
| **No framework / just a loop** | **[high, foundational]** Direct API loop gives maximum visibility and minimum dependency surface; add coded caps, persistence and approvals as needed. | You build every production concern, but avoid hidden control flow. Anthropic’s older Dec. 2024 guidance is retained because it is the foundational primary articulation and remains consistent with 2026 shipped loops. [S35] |

### 2.4 Convergence and divergence

**Consensus [high]:** one reply owner; model/tool/observation loops; schema-defined tools; bounded steps; environment feedback; isolated execution for code/computer actions; layered state plus compaction; streaming traces; approvals at risky actions; centralized orchestration for parallel workers; and explicit deterministic workflow code around probabilistic nodes. [S3, S6, S12, S19, S24, S25, S35]

**Divergence [medium, synthesis]:** (1) long-horizon single workflow (OpenAI Deep Research) versus breadth-first worker fan-out (Anthropic/Manus); (2) semantic search/API tools versus pixel-level computer use; (3) local synchronous pairing versus remote asynchronous PR workers; (4) framework-owned checkpoint graphs versus application loops versus durable workflow engines; and (5) handoff ownership versus manager-owned synthesis. These are workload tradeoffs, not a public-evidence hierarchy: parallel breadth buys coverage at coordination/token cost, while one writer preserves shared context but limits throughput. [S11–S18, S25, S34]

## 3. Delta since 2026-07-14

1. **[high] Newly surfaced:** Microsoft’s July 2026 docs now make Agent Framework—not AutoGen or Semantic Kernel—the forward foundation, with an explicit long-task harness and graph workflows. This raises the migration-risk weighting. [S21]
2. **[high] Newly surfaced:** OpenAI’s Agent Builder/Evals product wind-down and Nov. 2026 shutdown make visual/platform workflow coupling a concrete, current churn example. The code-first Agents SDK remains. [S20]
3. **[high] Expanded evidence:** shipped coding systems expose isolated foreground/background/cloud subagents (Claude, Cursor, Devin) but retain a coordinator and environmental verification. Cognition’s 2026 follow-up narrows its 2025 warning: parallel-writer swarms remain fragile; single-writer reviewers and centrally managed independent work can succeed. [S1, S2, S5, S8, S18]
4. **[medium] Expanded evidence:** Perplexity “Search as Code,” Manus Wide Research and Mastra Observational Memory show two distinct uses of background parallelism: task fan-out and context compression. These should not be conflated. [S14, S17, S33]
5. **[high] Correction/qualification:** framework “stability” is local, not ecosystem-wide. LangGraph v1 preserved its graph core while moving the prebuilt ReAct entry point; AutoGen rewrote; OpenAI retired Agent Builder. Pin versions and isolate adapters even after a 1.0 label. [S20, S25, S27, S28]

## 4. Contested / open questions

- **[low]** Whether a strong long-horizon research model beats orchestrator-workers at equal dollar and wall-clock budgets: no cross-vendor reproducible comparison exists.
- **[low]** Whether compaction preserves decision-critical constraints over multi-day runs: products disclose mechanisms, not calibrated loss rates.
- **[medium]** Pixel-only versus DOM/API hybrid control: visual interfaces generalize, while semantic tools are cheaper and more deterministic; benchmark revisions and live-site drift frustrate comparison.
- **[low]** Framework total cost: migration, trace storage, managed runtime, and debugging labor are rarely reported alongside token spend.
- **[medium]** Repository/user memory governance: validation, deletion, poisoning resistance and tenant boundaries remain unevenly disclosed.

## 5. Anti-patterns & failure modes

- Treating vendor benchmark numbers as product SLAs, or comparing different harness revisions.
- Parallelizing dependent work: duplicated edits, merge conflicts, context loss and superlinear spend.
- Letting worker prose become control-plane instructions; workers should return typed artifacts/evidence.
- Using “memory” as one undifferentiated transcript; raw logs, run state, plans and user facts have different retention/trust needs.
- Choosing a framework for demos, then discovering it does not own durable execution, sandboxing, approvals or evals.
- Depending on a visual builder or unstable prebuilt abstraction without an exit adapter.
- Graphing a 30-line loop before requirements demand checkpoints/branches; conversely, using an in-memory loop for multi-hour approvals.
- Calling self-critique “verification” without independent evidence or environment tests.

## 6. Design implications

1. **[high, normative] Start with one bounded loop and explicit application state.** Rationale: this matches shipped systems and preserves debuggability. Tradeoff: more bespoke persistence/stream plumbing.
2. **[high, normative] Add manager→worker fan-out only for independently testable breadth.** Rationale: Anthropic/Manus gains rely on independence and separate contexts. Tradeoff: roughly order-of-magnitude token growth and aggregation risk.
3. **[high, normative] Keep framework boundaries behind adapters.** Pin message, tool, checkpoint and trace schemas owned by the product; translate at the edge. Rationale: 2025–2026 migrations show control abstractions change quickly. Tradeoff: adapter maintenance.
4. **[high, normative] Select by missing infrastructure:** Agents SDK/LangChain for loop ergonomics; LangGraph/Pydantic Graph for explicit state and HITL; Temporal for process-surviving work; AgentCore/Gemini Enterprise Agent Platform/Microsoft for managed runtime. Rationale: buy the hardest missing lifecycle property. Tradeoff: each step upward exchanges control and portability for less infrastructure work; do not buy an enterprise platform for a tool loop.
5. **[high, normative] Make verification and economics first-class:** capture test/citation evidence, model/harness versions, per-worker tokens/cost, retries and partial outcomes. Rationale: vendor reports do not predict the local workload. Tradeoff: eval runs, retained traces and independent reviewers add latency, spend, storage and privacy obligations; sample selectively but never omit outcome evidence.

## 7. Sources

All sources were retrieved online this session; vendor pages describe vendor claims unless independently specified.

| ID | Primary source (date/status) | URL |
|---|---|---|
| S1 | Anthropic, “How Claude Code works” (live docs) | https://code.claude.com/docs/en/how-claude-code-works |
| S2 | Cursor, Subagents (live docs) | https://cursor.com/docs/subagents |
| S3 | OpenAI, “Unrolling the Codex agent loop” (2026) | https://openai.com/index/unrolling-the-codex-agent-loop/ |
| S4 | GitHub, Copilot cloud agent (live docs) | https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent |
| S5 | Cognition, “Devin Can Now Manage a Team of Devins” (2026) | https://cognition.ai/blog/devin-can-now-manage-devins |
| S6 | OpenHands, Agent architecture (live docs) | https://docs.openhands.dev/sdk/arch/agent |
| S7 | Aider, Configuration options (live docs) | https://aider.chat/docs/config/options.html |
| S8 | Cognition, “Don’t Build Multi-Agents” (2025-06-12) | https://cognition.ai/blog/dont-build-multi-agents |
| S9 | Amp, Owner’s Manual (live docs) | https://ampcode.com/manual |
| S10 | Google, Jules Tools (2025-10-02) | https://developers.googleblog.com/en/meet-jules-tools-a-command-line-companion-for-googles-async-coding-agent/ |
| S11 | OpenAI, Deep Research system card (2025-02) | https://openai.com/index/deep-research-system-card/ |
| S12 | Anthropic, Multi-agent Research system (2025-06-13) | https://www.anthropic.com/engineering/multi-agent-research-system |
| S13 | Google, Gemini Deep Research Agent (live docs, 2026 preview models) | https://ai.google.dev/gemini-api/docs/deep-research |
| S14 | Perplexity, Deep Research in Computer / Search as Code (2026) | https://www.perplexity.ai/hub/blog/deep-research-now-in-computer |
| S15 | OpenAI, Computer-Using Agent (2025-01-23) | https://openai.com/index/computer-using-agent/ |
| S16 | Anthropic, Claude Sonnet 4.5 and methodology (2025-09-29) | https://www.anthropic.com/news/claude-sonnet-4-5 |
| S17 | Manus, Wide Research architecture (2025-10-29) | https://manus.im/blog/manus-wide-research-solve-context-problem |
| S18 | Cognition, “Multi-Agents: What’s Actually Working” (2026-04-22) | https://cognition.ai/blog/multi-agents-working |
| S19 | OpenAI, Agents SDK guide (live docs) | https://developers.openai.com/api/docs/guides/agents |
| S20 | OpenAI, AgentKit update/wind-down (updated 2026-06-03) | https://openai.com/index/introducing-agentkit/ |
| S21 | Microsoft, Agent Framework overview (updated 2026-07-10) | https://learn.microsoft.com/en-us/agent-framework/overview/ |
| S22 | Microsoft, Copilot Studio OTel-aligned telemetry (live docs) | https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-environment-level-agent-telemetry |
| S23 | AWS, Bedrock AgentCore introduction, updated for GA (2025-10-13) | https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/ |
| S24 | Google Cloud, Gemini Enterprise Agent Platform launch / Vertex AI evolution (2026-04-22) | https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform |
| S25 | LangChain, v1 release/migration (2025+) | https://docs.langchain.com/oss/python/releases/langchain-v1 |
| S26 | OpenAI, CUA evaluation addendum (2025) | https://cdn.openai.com/cua/CUA_eval_extra_information.pdf |
| S27 | Microsoft AutoGen, v0.2→v0.4 migration (live docs) | https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html |
| S28 | AG2, Agent Harness (2026-06-17) | https://docs.ag2.ai/docs/blog/2026/06/17/AG2-Agent-Harness/ |
| S29 | CrewAI, Production architecture (live docs) | https://docs.crewai.com/en/concepts/production-architecture |
| S30 | Hugging Face, smolagents ReAct architecture (v1.26.0 pinned docs) | https://huggingface.co/docs/smolagents/v1.26.0/en/conceptual_guides/react |
| S31 | Pydantic AI, Agent API: graph runs, streams and approvals (live docs) | https://ai.pydantic.dev/api/agent/index.md |
| S32 | DSPy, ReAct and tools (live docs) | https://dspy.ai/getting-started/react-and-tools/ |
| S33 | Mastra, Observational Memory (live docs) | https://mastra.ai/docs/memory/observational-memory |
| S34 | Temporal, OpenAI Agents SDK integration (GA update 2026-03-23) | https://temporal.io/blog/announcing-openai-agents-sdk-integration |
| S35 | Anthropic, “Building effective agents” (2024-12-19; foundational exception) | https://www.anthropic.com/engineering/building-effective-agents |

## 8. Proposed content for final doc sections

### Section 2 — State of the art, 2026-08 snapshot

Production agents have converged on a deterministic shell around a model-directed loop: typed tools, environment observations, hard stopping conditions, layered state, compaction, traces and human approval at consequential boundaries. Coding systems use repository/shell/test sandboxes; research systems use plan/search/read/code/citation loops; computer-use systems use screenshot/action loops. Multi-agent systems are usually centralized orchestrator-workers with isolated contexts—not peer swarms—and are selected for parallel breadth rather than by default. Public benchmark evidence remains harness-sensitive and product reliability/cost distributions are mostly undisclosed.

### Section 14 — Reference architectures & framework selection

Use the smallest architecture that supplies a demonstrated missing property. A direct bounded loop is the baseline for chat-anchored tools. Add manager→worker fan-out for independent breadth; add LangGraph or Pydantic Graph when explicit branches, checkpoints and resumable HITL dominate; add Temporal when work must survive crashes, deploys or multi-hour waits; adopt AgentCore, Gemini Enterprise Agent Platform or Microsoft’s platform when managed isolation, identity, gateway, memory and governance justify coupling. Keep product-owned tool, state, trace and approval schemas behind adapters: AutoGen’s rewrite/succession, LangGraph’s prebuilt deprecation and Agent Builder’s shutdown show that migration is an architectural cost, not an edge case.
