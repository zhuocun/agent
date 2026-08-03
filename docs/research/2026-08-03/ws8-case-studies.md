# WS8 — Shipped agent systems and framework selection
**Scope:** Comparable architectures of shipped coding, research, computer-use, and enterprise agents; framework selection and migration reality | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS1–WS7 for loop, memory, tool, verification, safety, observability, and HITL mechanism depth

## 1. Executive summary

- **[high] The shipped-system consensus is a bounded model–tool–environment loop, not a peer “swarm.”** Coding products repeatedly combine repository search/read/edit, shell, tests, and an isolated workspace. Research products combine plan, search/read, code, synthesis, and citations. Computer-use products iterate screenshot → action → observation. Parallel agents exist, but usually behind one coordinator with isolated contexts and centralized synthesis. [S3–S8, S12–S20]
- **[high] State has separated into layers.** Products keep an event/thread history, compact or summarize it under context pressure, persist explicit plans/notes, and put long-lived user/repository memory outside the active trajectory. Examples include Codex compaction, OpenHands condensers and append-only events, Claude/Cursor subagent contexts, Google managed Sessions, and Mastra observational memory. [S1, S2, S3, S6, S24, S33]
- **[high] Verification is environmental.** Coding agents run tests/linters/type-checkers or browser checks; research agents verify citations or self-critique; consequential computer actions require confirmation. Published product-wide reliability and cost data remain rare, and vendor benchmark claims are not interchangeable.
- **[high] Frameworks converge on the same primitives but differ in ownership.** A thin SDK owns a tool loop; a graph framework owns state transitions/checkpoints; Temporal owns durable distributed execution; enterprise platforms additionally own sandbox/runtime, identity, memory, gateway, and telemetry. Every option still leaves product policy, tool semantics, evals, data governance, and user experience to the application.
- **[medium, normative] For a small chat-anchored team, keep the existing explicit loop and add a framework only for a demonstrated missing capability.** OpenAI Agents SDK or LangChain 1.x can remove loop boilerplate; LangGraph is justified by pause/resume and explicit branching; Temporal is justified only when runs must survive process lifetimes. This minimizes churn and preserves inspectability, at the cost of building persistence/streaming/approvals deliberately.

## 2. Findings

### 2.1 Coding agents: what actually ships

| System | Loop, tools, state / compaction | Subagents, verification, HITL, published data |
|---|---|---|
| **Claude Code** | **[high]** Model-directed loop over file/search/edit, shell, web/browser and extensions. `CLAUDE.md` supplies persistent project context; auto-compaction summarizes long sessions. | Isolated-context subagents can carry scoped tools/skills/memory; permissions and hooks gate actions; tests and browser checks are environmental evidence. Product-level success/cost data are undisclosed. [S1] |
| **Cursor Agent + background agents** | **[high]** Parent agent delegates to foreground/background subagents with separate context; cloud subagents receive their own VM/branch. Rules, local checkpoints, resumable subagent checkpoints, shell and editor tools form the harness. | Parallelism is manager-to-workers, not peer chat. Approval policy propagates; hooks can intercept lifecycle/tool use. No comparable reliability/cost series is published. [S2] |
| **OpenAI Codex** | **[high]** A Rust harness repeatedly sends model input, executes tool calls and appends results; cloud tasks run independently in repository-preloaded sandboxes with file/shell/test/lint/typecheck tools. The Responses compaction endpoint returns an opaque compaction item preserving latent context. | Parallelism is mainly independent tasks/threads, not disclosed in-turn specialists. Tests and terminal/file citations provide review evidence; approval/sandbox policy is runtime-controlled. Product success/cost is undisclosed. [S3] |
| **GitHub Copilot cloud agent** | **[high]** Research → plan → edit → test in an ephemeral GitHub Actions environment, one repository/branch/PR per session (hard maximum 59 minutes). MCP, Playwright, instructions, skills and hooks extend tools; Copilot Memory is preview. | Custom specialists exist, but public cloud-agent docs do not disclose an internal multi-agent topology. User reviews diffs/logs/commits before PR/merge. Costs consume Actions minutes plus AI credits; no success rate is published. [S4] |
| **Devin / managed Devins** | **[high, vendor claim]** One coordinator scopes work and launches full Devin workers, each in an isolated VM with terminal, browser, development environment, clean context and test runner. Coordinator can inspect full worker trajectories. | Explicit parallel orchestrator-workers; each worker tests before reporting. Humans can message workers, pause/terminate them, and monitor ACU consumption. Current comparable task success/cost distributions are undisclosed. [S5] |
| **OpenHands** | **[high]** Stateless single-step reason/action loop reads typed append-only events, condenses history, queries the LLM, emits action events, executes tools, and records observations. Workspace/runtime isolates bash/files; events support streaming and replay. | Pending actions can wait for confirmation and a security analyzer can assess risk. Multi-agent composition is application-level rather than the core loop. Current product-wide reliability/cost data are undisclosed. [S6] |
| **Aider** | **[high]** Interactive code loop with Git; architect mode is architect-model → editor-model. Context is selected files plus a graph-ranked repository map constrained by a token budget; chat can be cleared/saved. | No first-class autonomous swarm. User controls each turn; optional automatic lint/test feeds failures back for repair. Two-model architect mode explicitly adds latency/cost; no current fleet reliability data. [S7, S8] |
| **Amp / Jules** | **[medium]** Amp documents persistent shareable threads, file/shell tools, automatic isolated-context subagents and an “Oracle”; its manual explicitly rejects backward compatibility. Jules is asynchronous: each requested task runs in a temporary remote VM, syncs with GitHub, tests, and returns a PR; multiple sessions can run in parallel. | Amp exposes ask/reject/allow/delegate permissions; Jules is steered through web/CLI. Internal compaction, verifier topology, and comparable success/cost are undisclosed for both. [S9, S10] |

### 2.2 Research, computer-use, and enterprise systems

| System | Concrete architecture | Verification / HITL / evidence |
|---|---|---|
| **OpenAI Deep Research** | **[high]** Public description: early o3 optimized for persistent browsing; iterative web/PDF/image reading plus uploaded files and Python execution, ending in a cited report. No public subagent topology or compaction algorithm—do not infer one. | Safety training targets web prompt injection and privacy; current product HITL is user steering, while internal citation verification detail is limited. [S11] |
| **Anthropic Research** | **[high]** LeadResearcher writes its plan to Memory before 200K truncation, launches 3–5 specialized parallel workers (workers also parallelize tool calls), iterates, synthesizes, then hands documents/findings to a CitationAgent. | Vendor-reported June 2025 internal eval: Opus 4 lead + Sonnet 4 workers beat single Opus 4 by **90.2%**; dataset size/scoring are undisclosed. Anthropic also reports up to **90%** time reduction and roughly **15× chat tokens**; these are internal measurements, not independent benchmarks. [S12] |
| **Gemini Deep Research** | **[high]** Managed long-running `Plan → multi-source search → iterate → output`; Search, URL context, code execution, files and MCP. The model chooses parallel versus sequential subtasks and performs multiple self-critique passes. Background execution is mandatory. | Collaborative planning can return a plan for user edit/approval before execution; streams thought summaries/status and cited output. Cost/reliability distributions are undisclosed. [S13] |
| **Perplexity Deep Research / Computer** | **[medium, vendor claim]** Iterative plan/search/read/conflict-check/synthesis. Current “Search as Code” description says the model writes a retrieval program and executes thousands of steps in parallel in a secure sandbox, adapting as scored results arrive. | Citations and evidence sufficiency are the verifier surface. Model version, exact worker topology, compaction, and reproducible cost/reliability harness are undisclosed. [S14] |
| **Operator/CUA; Claude computer use** | **[high]** Both use a visual loop over screenshots and universal mouse/keyboard actions rather than site APIs. OpenAI-reported Mar. 2025 results for `computer-use-preview` using the named benchmarks’ universal-interface harnesses: **38.1% OSWorld, 58.1% WebArena, 87.0% WebVoyager**; OpenAI notes live-site drift. Anthropic-reported Sep. 2025 Claude Sonnet 4.5 at **61.4% OSWorld-Verified**, official harness, 100-step cap, mean of four runs. | Humans should confirm consequential actions; OpenAI explicitly recommends oversight because OS reliability is low. These results use different benchmark revisions/settings and must not be ranked directly. Memory/subagent strategies are undisclosed. [S15, S16] |
| **Manus / browser-agent products** | **[medium, vendor claim]** Manus Wide Research: controller decomposes, launches full Manus instances with separate VM/network/context/tool library, workers do not communicate, controller synthesizes. Stagehand exposes deterministic `observe/act/extract` plus an autonomous bounded agent loop in DOM, hybrid, or screenshot-CUA mode. | Manus centralizes review; quantitative claims lack a reproducible harness. Stagehand’s design supports the practical hybrid: deterministic primitives for critical steps, agent exploration for ambiguity, with Browserbase replay/identity infrastructure optional. [S17, S18] |
| **Enterprise platforms** | **[high]** OpenAI Agents SDK owns runner loop, sessions, streaming, handoffs/agents-as-tools, guardrails, approvals and traces; app owns deployment/tools/storage. Google ADK Runner composes agents/tools/callbacks with managed Sessions/Memory Bank on Agent Platform. Microsoft Agent Framework combines agents, a long-task harness, and typed graph workflows; it is the declared AutoGen/Semantic Kernel successor. Copilot Studio adds low-code flows and OTel-aligned agent/tool traces. AWS AgentCore supplies framework-neutral microVM runtime, short/long memory, identity, gateway and OTel observability and supports Strands alongside other frameworks. [S19–S24] |

### 2.3 Framework comparison: abstraction and cost

| Framework | Control/state/stream/HITL/observability/multi-agent | Lock-in, churn, and what remains yours |
|---|---|---|
| **LangChain 1.x + LangGraph 1.x** | **[high]** `create_agent` is a middleware-wrapped ReAct loop on LangGraph; graph adds typed state/nodes/edges, checkpointers, streaming, interrupts, replay and subgraphs. | Moderate semantic lock-in to message/state/runtime types. v1 moved legacy chains to `langchain-classic` and deprecated LangGraph `create_react_agent`; still build storage, tool safety, evals and product policy. [S25, S26] |
| **OpenAI Agents SDK** | **[high]** Runner loop, sessions, streams, guardrails, resumable approvals, traces, handoffs and manager “agents as tools.” | Low–moderate SDK lock-in, higher when using hosted OpenAI tools/models. Agent Builder’s June 2026 wind-down (shutdown Nov. 30, 2026) is direct evidence that managed visual surfaces churn; app still owns tools, persistence choice, deployment and policy. [S19, S20] |
| **AutoGen / AG2 → Microsoft Agent Framework / Semantic Kernel** | **[high]** AutoGen 0.4 was a breaking event-driven rewrite of 0.2; Microsoft now designates Agent Framework the successor to AutoGen and Semantic Kernel, adding sessions, middleware, telemetry, graph checkpoints and workflow HITL. AG2 independently ships an append-only MemoryStream, context assembly/compaction, middleware, parallel tools, observers and hub-based multi-agent networks. | Highest migration risk in this sample: package ownership confusion, rewrite, then successor. AG2’s fork is featureful but a separate ecosystem. Business tools, evaluation, deployment and data policy remain yours. [S21, S27, S28] |
| **CrewAI** | **[high]** Flow-first explicit branches/loops/state/persistence around role-based Crews; async kickoff, guardrails, structured outputs and tracing. | Role/task vocabulary can over-model simple work; managed deployment/observability encourages platform coupling. Build tool semantics, evals and secure runtime. [S29] |
| **smolagents** | **[high]** Minimal `MultiStepAgent` ReAct with JSON tool calls or generated Python, step memory/callbacks, optional planning and manager/managed agents; step streaming exists. | Low code lock-in, but docs label API experimental. Persistence, durable HITL, production telemetry and sandbox hardening are mostly yours. [S30] |
| **Pydantic AI** | **[high]** Typed agents/dependencies/outputs use an internal executable graph; runs expose node/tool event streams and tools can require approval. | Python/type-model coupling but relatively low provider lock-in. Durable persistence, production UI, evals, tracing backend and policy remain application/integration work. [S31] |
| **DSPy** | **[high]** Declarative signatures/modules; `ReAct` supplies bounded thought/tool/observation loop and trajectory, while optimizers tune prompts/examples against a metric. | Optimization is the differentiator, not runtime durability. You supply datasets/metrics, persistence, approvals, streaming UI, sandbox and orchestration. [S32] |
| **Mastra** | **[medium]** TypeScript agents/workflows, memory and OTel traces; Observational Memory uses background Observer/Reflector agents to replace growing raw history with dense append-only observations. | Convenient full stack means framework storage/runtime concepts spread widely. You still own eval truth, tool permissions and failure policy. [S33] |
| **Temporal custom build** | **[high]** Native-code Workflow controls deterministic orchestration; LLM/tool calls are retryable Activities; event history enables crash recovery, long waits and horizontal workers. Updates/Signals support HITL, traces integrate with the agent SDK, and the OpenAI integration became GA Mar. 2026. | Operational/runtime commitment is substantial and replay determinism constrains code. Token streaming/UI, prompts, agents, tools, evals and policy remain yours. [S34] |
| **No framework / just a loop** | **[high, foundational]** Direct API loop gives maximum visibility and minimum dependency surface; add coded caps, persistence and approvals as needed. | You build every production concern, but avoid hidden control flow. Anthropic’s older Dec. 2024 guidance is retained because it is the foundational primary articulation and remains consistent with 2026 shipped loops. [S35] |

### 2.4 Convergence and divergence

**Consensus [high]:** one reply owner; model/tool/observation loops; schema-defined tools; bounded steps; environment feedback; isolated execution for code/computer actions; layered state plus compaction; streaming traces; approvals at risky actions; centralized orchestration for parallel workers; and explicit deterministic workflow code around probabilistic nodes. [S3, S6, S12, S19, S24–S26, S35]

**Divergence [high]:** (1) long-horizon single workflow (OpenAI Deep Research) versus breadth-first worker fan-out (Anthropic/Manus); (2) DOM/API tools versus pixel-level computer use (Stagehand supports both); (3) local synchronous pairing versus remote asynchronous PR workers; (4) framework-owned checkpoint graphs versus application loops versus durable workflow engines; and (5) handoff ownership versus manager-owned synthesis. No public evidence makes one shape universally superior.

## 3. Delta since 2026-07-14

1. **[high] Newly surfaced:** Microsoft’s July 2026 docs now make Agent Framework—not AutoGen or Semantic Kernel—the forward foundation, with an explicit long-task harness and graph workflows. This raises the migration-risk weighting. [S21]
2. **[high] Newly surfaced:** OpenAI’s Agent Builder/Evals product wind-down and Nov. 2026 shutdown make visual/platform workflow coupling a concrete, current churn example. The code-first Agents SDK remains. [S20]
3. **[high] Expanded evidence:** shipped coding systems now expose isolated foreground/background/cloud subagents (Claude, Cursor, Devin) but retain a coordinator and environmental verification; this strengthens the prior memo’s “manager owns answer” conclusion. [S1, S2, S5]
4. **[medium] Expanded evidence:** Perplexity “Search as Code,” Manus Wide Research and Mastra Observational Memory show two distinct uses of background parallelism: task fan-out and context compression. These should not be conflated. [S14, S17, S33]
5. **[high] Correction/qualification:** framework “stability” is local, not ecosystem-wide. LangGraph v1 preserved its graph core while moving the prebuilt ReAct entry point; AutoGen rewrote; OpenAI retired Agent Builder. Pin versions and isolate adapters even after a 1.0 label. [S20, S25–S28]

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
4. **[high, normative] Select by missing infrastructure:** Agents SDK/LangChain for loop ergonomics; LangGraph/Pydantic Graph for explicit state and HITL; Temporal for process-surviving work; AgentCore/Vertex/Foundry for managed enterprise runtime. Do not adopt an enterprise platform merely for a tool loop.
5. **[high, normative] Make verification and economics first-class:** capture test/citation evidence, model/harness versions, per-worker tokens/cost, retries and partial outcomes. Vendor reports are insufficient for local product decisions.

## 7. Sources

All sources were retrieved online this session; vendor pages describe vendor claims unless independently specified.

| ID | Primary source (date/status) | URL |
|---|---|---|
| S1 | Anthropic, Claude Code features/subagent context (live docs) | https://docs.anthropic.com/en/docs/claude-code/features-overview |
| S2 | Cursor, Subagents (live docs) | https://cursor.com/docs/subagents |
| S3 | OpenAI, “Unrolling the Codex agent loop” (2026) | https://openai.com/index/unrolling-the-codex-agent-loop/ |
| S4 | GitHub, Copilot cloud agent (live docs) | https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent |
| S5 | Cognition, “Devin Can Now Manage a Team of Devins” (2026) | https://cognition.ai/blog/devin-can-now-manage-devins |
| S6 | OpenHands, Agent architecture (live docs) | https://docs.openhands.dev/sdk/arch/agent |
| S7 | Aider, Chat/architect modes (live docs) | https://aider.chat/docs/usage/modes.html |
| S8 | Aider, Repository map (live docs) | https://aider.chat/docs/repomap.html |
| S9 | Amp, Owner’s Manual (live docs) | https://ampcode.com/manual |
| S10 | Google, Jules Tools (2025-10-02) | https://developers.googleblog.com/en/meet-jules-tools-a-command-line-companion-for-googles-async-coding-agent/ |
| S11 | OpenAI, Deep Research system card (2025-02) | https://openai.com/index/deep-research-system-card/ |
| S12 | Anthropic, Multi-agent Research system (2025-06-13) | https://www.anthropic.com/engineering/multi-agent-research-system |
| S13 | Google, Gemini Deep Research Agent (live docs, 2026 preview models) | https://ai.google.dev/gemini-api/docs/deep-research |
| S14 | Perplexity, Deep Research in Computer / Search as Code (2026) | https://hub-prod.perplexity.ai/hub/blog/deep-research-now-in-computer |
| S15 | OpenAI, Computer-Using Agent (2025-03) | https://openai.com/index/computer-using-agent/ |
| S16 | Anthropic, Claude Sonnet 4.5 and methodology (2025-09-29) | https://www.anthropic.com/news/claude-sonnet-4-5 |
| S17 | Manus, Wide Research architecture (2025-10-29) | https://manus.im/blog/manus-wide-research-solve-context-problem |
| S18 | Browserbase/Stagehand, Agent reference (source snapshot) | https://github.com/browserbase/stagehand/blob/be0a2f63/packages/docs/v3/references/agent.mdx |
| S19 | OpenAI, Agents SDK guide (live docs) | https://developers.openai.com/api/docs/guides/agents |
| S20 | OpenAI, AgentKit update/wind-down (updated 2026-06-03) | https://openai.com/index/introducing-agentkit/ |
| S21 | Microsoft, Agent Framework overview (updated 2026-07-10) | https://learn.microsoft.com/en-us/agent-framework/overview/ |
| S22 | Microsoft, Copilot Studio OTel-aligned telemetry (live docs) | https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-environment-level-agent-telemetry |
| S23 | AWS, Bedrock AgentCore introduction (2025-07) | https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/ |
| S24 | Google Cloud, ADK managed Sessions (live docs) | https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions/manage-with-adk |
| S25 | LangChain, v1 release/migration (2025+) | https://docs.langchain.com/oss/python/releases/langchain-v1 |
| S26 | LangGraph, v1 release/deprecation (2025+) | https://docs.langchain.com/oss/python/releases/langgraph-v1 |
| S27 | Microsoft AutoGen, v0.2→v0.4 migration (live docs) | https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html |
| S28 | AG2, Agent Harness (2026-06-17) | https://docs.ag2.ai/docs/blog/2026/06/17/AG2-Agent-Harness/ |
| S29 | CrewAI, Production architecture (live docs) | https://docs.crewai.com/en/concepts/production-architecture |
| S30 | Hugging Face, smolagents ReAct architecture (v1.26 docs) | https://huggingface.co/docs/smolagents/en/conceptual_guides/react |
| S31 | Pydantic AI, Agent API: graph runs, streams and approvals (live docs) | https://ai.pydantic.dev/api/agent/index.md |
| S32 | DSPy, ReAct and tools (live docs) | https://dspy.ai/getting-started/react-and-tools/ |
| S33 | Mastra, Observational Memory (live docs) | https://mastra.ai/docs/memory/observational-memory |
| S34 | Temporal, OpenAI Agents SDK integration (GA update 2026-03-23) | https://temporal.io/blog/announcing-openai-agents-sdk-integration |
| S35 | Anthropic, “Building effective agents” (2024-12-19; foundational exception) | https://www.anthropic.com/engineering/building-effective-agents |

## 8. Proposed content for final doc sections

### Section 2 — State of the art, 2026-08 snapshot

Production agents have converged on a deterministic shell around a model-directed loop: typed tools, environment observations, hard stopping conditions, layered state, compaction, traces and human approval at consequential boundaries. Coding systems use repository/shell/test sandboxes; research systems use plan/search/read/code/citation loops; computer-use systems use screenshot/action loops. Multi-agent systems are usually centralized orchestrator-workers with isolated contexts—not peer swarms—and are selected for parallel breadth rather than by default. Public benchmark evidence remains harness-sensitive and product reliability/cost distributions are mostly undisclosed.

### Section 14 — Reference architectures & framework selection

Use the smallest architecture that supplies a demonstrated missing property. A direct bounded loop is the baseline for chat-anchored tools. Add manager→worker fan-out for independent research breadth; add LangGraph or Pydantic Graph when explicit branches, checkpoints and resumable HITL dominate; add Temporal when work must survive crashes, deploys or multi-hour waits; adopt AgentCore, Vertex Agent Platform or Microsoft Foundry/Copilot Studio when managed isolation, identity, gateway, memory and governance justify platform coupling. Keep product-owned tool, state, trace and approval schemas behind adapters: AutoGen’s rewrite/succession, LangGraph’s prebuilt deprecation, and Agent Builder’s shutdown show that framework migration is an architectural cost, not an edge case.
