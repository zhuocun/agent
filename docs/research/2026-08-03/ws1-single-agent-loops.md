# WS1 — Single-agent loops and inference-time compute
**Scope:** production single-agent control loops, reasoning-state handling, inference-time compute, prompt/harness architecture, and loop-level control | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS3 for tool mechanics/MCP, WS4 for memory and compaction internals, WS5 for verifier/training mechanics, WS2 for peer-agent topologies

## 1. Executive summary

- [high] The canonical production loop is still ReAct in typed form: assemble instructions and state, invoke the model, parse typed reasoning/message/tool items, execute allowed calls, append correlated results, and repeat until a valid final message or an external stop. Modern “harnesses” add state ordering, permissions, streaming, context management, and lifecycle controls; they do not replace the loop. [1][3][11][15]
- [high] “Turn” is not a stable unit across products. Codex calls the whole user-to-assistant interval one turn even if it contains hundreds of model/tool iterations; OpenAI Agents SDK counts each model invocation as a turn; Claude Agent SDK counts tool-use round trips. Budgets must therefore name the counted event, not merely `max_turns`. [10][11][15]
- [high] A model-emitted final message is a *protocol stop signal*, not proof of task success. Public harness evidence shows both premature victory and one-shot overreach; production acceptance must be a separate coded decision, even if the model decides when to stop attempting. [7][11]
- [high] Reasoning models make trajectory state part of the API contract. During a tool chain, reasoning, function-call, and function-result items must remain ordered and correlated. Server state (`previous_response_id`/conversation) and stateless encrypted-item replay are equivalent transport strategies; dropping intermediate reasoning can degrade behavior or make the API reject malformed continuation. [11][12][14]
- [medium] More inference compute helps only when the task and protocol provide productive search or correction. Current evidence rejects a universal “think longer” rule: serial depth helps stateful tasks more often, parallel attempts help stateless tasks more often, and both eventually hit context, verification, or overthinking limits. [26][27][28]
- [high] Compute allocation should be adaptive to difficulty and observable progress. Foundational compute-optimal work and 2025–2026 agent studies agree that fixed per-task budgets waste compute; unconditional reflection can slightly reduce aggregate performance. [25][28][29]
- [medium] Production prompt architecture has converged on a small stable core plus model-specific instructions, precise tool schemas, environment/permission state, repository rules, and progressively disclosed skills. Published Codex and Cursor descriptions show the prompt is one component of a model-specific harness, not a portable magic string. [4][5][6][11][21][22]
- [high] Steering, interruption, cancellation, and resumption are different state transitions. Mature protocols identify the active turn, preserve or explicitly cancel queued input, emit a terminal interrupted state, and resume pending model/tool continuation before injecting later steering after compaction. [10][18][19][20]

## 2. Findings

### 2.1 The canonical loop: ReAct → typed tool loop → harness

**Finding 1 — the semantic loop is stable; the representation changed. [high]** ReAct formalized interleaved reasoning, action, environmental observation, and updated reasoning. Contemporary implementations replace textual `Thought/Action/Observation` parsing with typed items and call IDs. Codex documents: build prompt → infer → receive either final assistant output or a tool call → execute → append reasoning, call, and output → infer again; no more calls plus an assistant message ends the user turn. OpenAI Agents SDK expresses the same loop and adds handoffs; smolagents writes memory to messages, samples an action, executes it, records an `ActionStep`, and repeats. [1][11][15][24]

**Why it matters for design.** The reusable abstraction is not “an LLM with tools”; it is a state machine with explicit states such as `sampling`, `awaiting_tool`, `executing_tool`, `awaiting_approval`, and `terminal`. Typed transitions make malformed call/result pairs, cancellation, retries, and observability tractable.

**Finding 2 — production “harness” means the entire control envelope. [high]** Codex’s published initial context includes model-specific base instructions, tool schemas, sandbox/approval instructions, optional developer instructions, scoped `AGENTS.md` files, skill metadata, environment state, then the user request. Cursor describes its harness as system prompt + tool descriptions + conversation/request context, tuned per frontier model and evaluated through offline suites and online experiments. [11][21]

**Why it matters for design.** Benchmarking a model without naming the harness measures a different system. Harness version, tool set, context policy, and stop policy belong in every evaluation record.

**Finding 3 — stop conditions and bounds are heterogeneous. [high]** Codex terminates a conversation turn on an assistant message, while acknowledging that one turn may contain hundreds of tool calls. OpenAI Agents SDK defaults to 10 model invocations and raises `MaxTurnsExceeded` (or returns a configured fallback); Claude Agent SDK exposes `maxTurns` but leaves it undefined by default; smolagents defaults to 20 steps. Google ADK warns that its deterministic `LoopAgent` needs an explicit maximum or escalation condition. [10][11][15][16][23][24]

**Why it matters for design.** Specify at least a semantic stop and independent hard limits on model invocations, tool executions, elapsed time, output tokens, and cost. A single ambiguous “round” limit is not portable.

### 2.2 Reasoning models change state, not the outer loop

**Finding 4 — extended/interleaved thinking inserts private compute between actions. [medium]** Claude 4 introduced alternation between extended thinking and tool use; Opus 4.6 added adaptive thinking and effort controls because deeper thinking can improve hard tasks but add latency/cost or overthink easy ones. Claude Agent SDK now exposes adaptive/fixed/disabled thinking separately from `maxTurns`. [8][9][10]

**Why it matters for design.** Reasoning effort and loop length are orthogonal: one controls compute inside a model invocation; the other controls how many environment-feedback cycles occur. Meter and tune both.

**Finding 5 — preserve reasoning state within tool-assisted continuations. [high]** OpenAI’s o3/o4-mini cookbook distinguishes ordinary later user turns from the multiple API calls constituting one tool-assisted turn: the latter should replay the reasoning item with the function call and result. Current reasoning docs extend this with `current_turn` versus `all_turns`; access to earlier reasoning still requires response chaining, a conversation, or complete manual replay. Codex remains transport-stateless for Zero Data Retention but replays encrypted reasoning content and exact item order. [11][12][14]

**What breaks when traces are dropped.** The continuation may re-derive intent, choose a poorer next action, lose cache-prefix efficiency, treat an intermediate update as final if phase metadata is dropped, or fail validation because a function call lacks its required reasoning/call item. OpenAI reports about +3% on unspecified SWE-bench and +5% on unspecified TAUBench from preserved reasoning, but neither disclosure names the benchmark variant, harness, complete model version, or sampling protocol; these are vendor claims, not decision-grade benchmark results. [12][13][14]

**Why it matters for design.** Persist opaque reasoning IDs/items as protocol state, not user-visible memory. If retention policy forbids server state, use encrypted client replay rather than silently reverting to stateless chat semantics.

### 2.3 Inference-time compute: serial, parallel, iterative

**Finding 6 — gains are task- and protocol-dependent. [high]** McFadyen et al. (16 June 2026) ran five independent trajectories per task through one Inspect AI ReAct scaffold, comparing Opus 4/4.5/4.6 and GPT-5/5.2/5.4 at 16k reasoning tokens per call on TerminalBench 2.0, SWE-Bench Pro, FrontierMath, HealthBench Hard, and non-multiple-choice HLE. Larger budgets and repeated submission helped broadly, but parallel scaling was strongest on stateless HealthBench/HLE and weakest on stateful tasks; feedback mattered where it could guide continued search. [27]

**Why it matters for design.** Product compute modes should reflect task statefulness: continue one trajectory when environment state and accumulated work matter; restart/sample when attempts are independent and cheaply judged.

**Finding 7 — serial scaling hits a context ceiling; parallel scaling hits a selection ceiling. [medium]** Li et al. (22 February 2026) evaluated ten models in the unified General AgentBench harness over search, coding, reasoning, and tool use at temperature 0.7. Most models lost roughly 10–30% relative performance versus domain-specific settings (Claude Sonnet 4.5 was the reported robustness exception at 0.2% average degradation). Longer histories became unstable after model/domain-specific ceilings; pass@K rose while self-choice saturated or worsened, and GPT-5 as external selector did not close the gap. [26]

**Why it matters for design.** Neither “keep going” nor “sample more” is sufficient without context control and a reliable acceptance signal. Selection mechanics themselves belong to WS5.

**Finding 8 — conditional refinement beats ritual reflection. [medium]** Reflexion established the retry-with-verbal-feedback pattern; newer evidence narrows where to apply it. Zhou et al. (13 June 2025; included as the foundational agent-specific test-time-scaling study) used a modified smolagents `CodeAgent` scaffold with GPT-4.1 on all 165 GAIA validation tasks. Best-of-N increased overall score from 55.76 to 63.03, while reflection on every step slightly reduced it to 55.15; reflection helped some easy and hard subsets but disrupted intermediate tasks. [2][25]

**Why it matters for design.** Trigger refinement after failure, contradiction, stalled progress, or a cheap uncertainty signal—not after every action.

**Finding 9 — more thinking can reverse correct answers. [medium]** Zhou et al. (12 April 2026) used budget forcing from 500–16,000 tokens with DeepSeek-R1-32B and s1-32B on AIME, GPQA Diamond, and MATH-500. On AIME, marginal utility turned negative beyond 12k; R1-32B accuracy fell 0.9 points from 12k to 16k (95% CI −1.4 to −0.4), and negative answer flips overtook positive flips around 7k. This is one two-model harness, not a universal threshold. [28]

**Why it matters for design.** Expose effort as a policy, not a quality slider. Foundational PaLM 2-S* work on MATH similarly found difficulty-adaptive revision/PRM search could match best-of-N with roughly 4× less compute and sometimes beat a 14× larger model at matched FLOPs; it is foundational because it established compute-optimal allocation, not because its 2024 model transfers unchanged. [29]

### 2.4 Prompt and instruction architecture

**Finding 10 — use a layered, model-specific prompt. [high]** Published Codex construction orders server system content, model/developer instructions, tools, permissions, scoped repository rules, skill metadata, environment, and request. Anthropic recommends a minimal but sufficient system prompt, canonical few-shot examples rather than edge-case laundry lists, and explicit tool boundaries/parameters. Cursor reports deleting static guardrails as models improved while retaining OS/git/editor state and tuning each model-harness pair. [4][5][11][21]

**Why it matters for design.** Keep invariant policy high-priority and stable for cacheability; place mutable context late; add examples only for measured failures. Opposite choice—more static instruction—is justified when retrieval is unreliable or the rule is safety-critical.

**Finding 11 — skills/rules are progressive disclosure, not extra personas. [high]** Anthropic Skills preload only name/description, load `SKILL.md` when relevant, then follow linked resources. Claude Code’s hybrid instead loads `CLAUDE.md` up front and discovers files just in time. Cursor reports the same file-oriented pattern and a 46.9% token reduction in an internal A/B among runs that called an MCP tool; Cursor does not disclose sample size or full harness, so treat the magnitude as a vendor measurement. [4][6][22]

**Why it matters for design.** The core prompt should teach discovery and precedence; domain procedure should live in scoped files with concise metadata. Few-shot examples remain useful for ambiguous tool selection, but only after evaluation identifies a repeatable confusion. [4][5]

### 2.5 Context-isolated delegation (adjacent)

**Finding 12 — an ephemeral worker can act as a clean context window. [medium]** Anthropic describes a lead sending a focused task into a clean context and receiving a 1k–2k-token distilled result after much larger exploration. That is useful when isolation/compression is the goal, but spawning, topology, coordination, and worker verification are deferred to WS2/WS5. [4]

### 2.6 Interruption, steering, cancellation, and resume

**Finding 13 — these controls need distinct protocol semantics. [high]** Codex App Server defines `turn/steer` (append to the active turn with expected turn ID), `turn/interrupt` (cancel and finish with `interrupted`), and terminal `completed|interrupted|failed` statuses. The dedicated steer API was introduced to eliminate races and misleading new turn IDs. Claude’s SDK `interrupt()` returns a receipt identifying queued messages that survive; newer control protocol versions can cancel queued messages too, and persisted sessions can resume from a session/message ID. [10][18][19]

**Finding 14 — steering order is part of correctness. [high]** An April 2026 Codex fix documents a concrete bug: after auto-compaction, pending steering was injected before interrupted model/tool continuation, making it look like the newest task. The fix resumes real continuation once, then drains steering; if the previous answer was final, steering starts immediately. [20]

**Why it matters for design.** Treat new user input as an event with target turn, ordering, and disposition (`steer`, `queue`, `cancel-and-restart`). A network disconnect must not silently mean cancellation, and cancellation must resolve outstanding tool-call bookkeeping before resumption.

## 3. Delta since 2026-07-14

- **New. [high]** The prior memo named ReAct but did not describe the now-published Codex item-level loop: instruction roles, encrypted reasoning items, call/result correlation, prompt-prefix caching, and the distinction between one user turn and many inference iterations. [11]
- **New. [high]** Current OpenAI reasoning docs add cross-user-turn `all_turns` reasoning context and phase metadata; this makes preservation policy more granular than “keep the chat history.” [14]
- **New. [high]** General AgentBench and the June 2026 cross-generation study supply the missing counterweight to “more compute helps”: context ceilings, selection gaps, stateful/stateless differences, and protocol-dependent scaling. [26][27]
- **Changed. [medium]** Reasoning control is becoming adaptive. Claude Opus 4.6 chooses whether to think under an effort policy, while OpenAI separates reasoning context and effort from outer-loop turns. [9][14]
- **Changed. [high]** Production loop control now includes first-class in-flight steering and explicit queue/cancel receipts, not only pause/resume. The compaction-ordering bug shows these are correctness concerns, not UI polish. [10][18][20]
- **Overstated in the prior memo. [high]** “Hard bounds are non-negotiable” is sound normative advice but was presented as if descriptive consensus. Public SDKs permit undefined/unbounded runs: Claude `maxTurns` defaults undefined, OpenAI accepts `None`, and ADK warns omission can loop indefinitely. [10][15][23]
- **Overstated in the prior memo. [high]** “Single agents ≈4× tokens” is not an industry constant; it is workload/harness-specific vendor reporting. Use local compute curves, not that multiplier, for capacity planning.
- **Incomplete in the prior memo. [high]** “Modern APIs replace regex parsers with structured calls” understates the change: reasoning items, phase, call IDs, and ordering are continuation invariants. Dropping them can alter stop behavior or invalidate a request. [12][14]
- **Still correct, with qualification. [high]** A bounded single loop remains the default architecture. However, a shipped long-horizon product is evidence of feasibility, not comparative proof that its single-agent shape beats orchestrator-workers; that comparison remains WS2/local-eval territory.

## 4. Contested / open questions

1. [medium] Does `all_turns` reasoning improve long-running work enough to justify retaining stale assumptions? Current guidance is first-party but lacks a public, reproducible cross-turn benchmark. [14]
2. [medium] Where should adaptive effort stop? The 2026 overthinking result is compelling but limited to two 32B open models and budget forcing; frontier API models may have different curves. [28]
3. [medium] Can self-choice close the parallel-scaling verification gap without spending as much as another full trajectory? General AgentBench says not yet; mechanics are deferred to WS5. [26]
4. [low] How much of Cursor’s harness improvement comes from model progress versus prompt/tool/context changes? Cursor explicitly says they interact, but public CursorBench and online experiment details are insufficient to attribute causality. [21]
5. [medium] Should a final assistant message end a run immediately when external completion evidence is absent, or trigger one last cheap check? The answer depends on side-effect risk, check cost, and false-completion rate.
6. [low] OpenAI reports GPT-5.1-Codex-Max runs exceeding 24 hours in internal evaluations, but supplies no task set, harness version, success denominator, or stopping protocol; this is evidence of possible duration, not measured reliability. [30]

## 5. Anti-patterns & failure modes

| Anti-pattern / failure | Evidence and consequence |
| --- | --- |
| Prompt-only “keep going” with no coded cap | [high] Semantic persistence can fight premature stopping, but SDKs allow infinite loops; cap invocations, tools, time, tokens, and spend independently. [15][17][23] |
| Treating final text as success | [high] Codex uses it as a stop signal; Anthropic observed agents declaring victory before end-to-end completion. [7][11] |
| Replaying only visible messages | [high] Drops reasoning/call/phase items, causing re-derivation, misclassified finals, poorer behavior, or invalid continuation. [11][12][14] |
| Reflection after every step | [medium] The GPT-4.1/GAIA modified-smolagents study slightly regressed overall performance. [25] |
| Fixed maximum thinking for every request | [medium] Wastes latency on easy tasks and can flip correct answers; difficult tasks may still need the larger budget. [9][28][29] |
| Best-of-N without an evaluated selector | [high] pass@K can rise while usable self-choice saturates or falls. [26] |
| Context stuffing | [high] Long trajectories accumulate distracting tool output; current harnesses use just-in-time discovery and compact artifacts. Internals belong to WS4. [4][22] |
| Tool-call thrash | [medium] Redundant calls often indicate overlapping tools, ambiguous parameters, or oversized responses rather than insufficient model intelligence. [5] |
| Conflating steer, queue, interrupt, and disconnect | [high] Produces turn-ID races, lost instructions, duplicate execution, and wrong post-compaction ordering. [18][19][20] |
| One-shotting long work | [medium] Anthropic observed half-implemented state at context exhaustion; the inverse failure was premature completion. [7] |

## 6. Design implications

1. **Adopt a typed bounded loop. [high]** Rationale: typed state and call IDs make continuation and cancellation auditable. Tradeoff: more orchestration code than a raw `while` loop. A raw loop wins only for disposable, read-only prototypes with cheap deterministic tools.
2. **Define counters precisely. [high]** Rationale: “turn” differs by harness. Track model invocations, tool calls, reasoning/output tokens, wall time, and cost. Tradeoff: more telemetry/cardinality. A single limit wins only when one resource dominates and tasks are homogeneous.
3. **Treat model finality and task acceptance separately. [high]** Rationale: premature success is documented. Tradeoff: an acceptance check adds latency and can reject valid work. Immediate acceptance wins for low-risk prose with no objective oracle; detailed verifier design is WS5.
4. **Preserve the provider’s complete continuation state. [high]** Rationale: reasoning/call/phase items are protocol invariants. Tradeoff: storage and privacy complexity. Stateless encrypted replay wins under ZDR; server chaining wins when operational simplicity and cache reuse dominate.
5. **Route compute adaptively. [high]** Rationale: difficulty, statefulness, and progress determine whether serial depth, parallel breadth, or conditional refinement pays. Tradeoff: routing mistakes and evaluation burden. A fixed budget wins for predictable latency SLOs or narrow tasks.
6. **Layer prompts and disclose procedures progressively. [high]** Rationale: stable policy plus scoped rules preserves attention and cache prefixes. Tradeoff: discovery can miss relevant instructions. Eager loading wins for short, safety-critical, always-applicable rules.
7. **Implement explicit run-control events. [high]** Rationale: steering and cancellation have different ordering and terminal semantics. Tradeoff: clients must maintain turn IDs and queue state. Simple abort wins only when runs are non-resumable and have no side effects.
8. **Expose a context-isolated worker only as a bounded tool. [medium]** Rationale: it can compress focused exploration without contaminating the lead context. Tradeoff: cost and lost detail. Staying in one context wins for tightly sequential tasks; topology belongs to WS2.

## 7. Sources

| [n] | title | org | date | type | URL | retrieved 2026-08-03 |
| --- | --- | --- | --- | --- | --- | --- |
| [1] | ReAct: Synergizing Reasoning and Acting in Language Models | Princeton / Google Research via arXiv | 6 Oct 2022 | paper; foundational origin of the loop | https://arxiv.org/abs/2210.03629 | yes |
| [2] | Reflexion: Language Agents with Verbal Reinforcement Learning | Northeastern / MIT / Princeton via arXiv | 20 Mar 2023 | paper; foundational iterative-reflection reference | https://arxiv.org/abs/2303.11366 | yes |
| [3] | Building effective agents | Anthropic | 19 Dec 2024 | engineering guidance; foundational production taxonomy | https://www.anthropic.com/engineering/building-effective-agents | yes |
| [4] | Effective context engineering for AI agents | Anthropic | 29 Sep 2025 | engineering blog | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | yes |
| [5] | Writing effective tools for agents — with agents | Anthropic | 11 Sep 2025 | engineering blog | https://www.anthropic.com/engineering/writing-tools-for-agents | yes |
| [6] | Equipping agents for the real world with Agent Skills | Anthropic | 16 Oct 2025 | engineering blog | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | yes |
| [7] | Effective harnesses for long-running agents | Anthropic | 26 Nov 2025 | engineering report | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents | yes |
| [8] | Introducing Claude 4 | Anthropic | 22 May 2025 | product/technical announcement; foundational interleaved-thinking reference | https://www.anthropic.com/news/claude-4 | yes |
| [9] | Introducing Claude Opus 4.6 | Anthropic | 5 Feb 2026 | product/technical announcement | https://www.anthropic.com/news/claude-opus-4-6 | yes |
| [10] | TypeScript SDK reference | Anthropic | n.d.; current reference cites v2.1.219 | documentation | https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-typescript | yes |
| [11] | Unrolling the Codex agent loop | OpenAI | 23 Jan 2026 | engineering blog | https://openai.com/index/unrolling-the-codex-agent-loop/ | yes |
| [12] | Better performance from reasoning models using the Responses API | OpenAI | 11 May 2025 | cookbook; foundational reasoning-item implementation | https://developers.openai.com/cookbook/examples/responses_api/reasoning_items | yes |
| [13] | Why we built the Responses API | OpenAI | n.d. | developer blog | https://developers.openai.com/blog/responses-api | yes |
| [14] | Reasoning models | OpenAI | n.d.; current documentation | documentation | https://developers.openai.com/api/docs/guides/reasoning | yes |
| [15] | Running agents | OpenAI Agents SDK | n.d.; current documentation | documentation | https://openai.github.io/openai-agents-python/running_agents/ | yes |
| [16] | `src/agents/run_config.py` (`DEFAULT_MAX_TURNS = 10`) | OpenAI Agents SDK | n.d.; commit `7029ea8f` | source code | https://github.com/openai/openai-agents-python/blob/7029ea8f/src/agents/run_config.py | yes |
| [17] | GPT-5 prompting guide | OpenAI | 7 Aug 2025 | cookbook | https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide | yes |
| [18] | Codex App Server | OpenAI | n.d.; current documentation | protocol documentation | https://developers.openai.com/codex/app-server | yes |
| [19] | feat(app-server): turn/steer API | OpenAI Codex | 5 Feb 2026 | merged source PR | https://github.com/openai/codex/pull/10821 | yes |
| [20] | Defer steering until after sampling the model post-compaction | OpenAI Codex | 8 Apr 2026 | merged source PR | https://github.com/openai/codex/pull/17163 | yes |
| [21] | Continually improving our agent harness | Cursor | 30 Apr 2026 | engineering blog | https://cursor.com/blog/continually-improving-agent-harness | yes |
| [22] | Dynamic context discovery | Cursor | n.d. | engineering blog | https://cursor.com/blog/dynamic-context-discovery | yes |
| [23] | Loop workflow — Agent Development Kit | Google | n.d.; current documentation | documentation | https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/ | yes |
| [24] | Agents — smolagents reference | Hugging Face | n.d.; main / v1.26.0 visible | documentation/source reference | https://huggingface.co/docs/smolagents/main/en/reference/agents | yes |
| [25] | Scaling Test-time Compute for LLM Agents | Zhou et al. via arXiv | 13 Jun 2025 | paper; foundational agent-specific scaling study | https://arxiv.org/abs/2506.12928 | yes |
| [26] | Benchmark Test-Time Scaling of General LLM Agents | Carnegie Mellon / Meta via arXiv | 22 Feb 2026 | paper | https://arxiv.org/abs/2602.18998 | yes |
| [27] | How Inference Compute Shapes Frontier LLM Evaluation | McFadyen et al. via arXiv | 16 Jun 2026 | paper | https://arxiv.org/abs/2606.17930 | yes |
| [28] | When More Thinking Hurts: Overthinking in LLM Test-Time Compute Scaling | Nanjing University / Baidu via arXiv | 12 Apr 2026 | paper | https://arxiv.org/abs/2604.10739 | yes |
| [29] | Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters | UC Berkeley / Google DeepMind via arXiv | 7 Aug 2024 | paper; foundational compute-allocation result | https://arxiv.org/abs/2408.03314 | yes |
| [30] | Building more with GPT-5.1-Codex-Max | OpenAI | 19 Nov 2025 | product/technical announcement | https://openai.com/index/gpt-5-1-codex-max/ | yes |

## 8. Proposed content for final doc sections 3, 4

### Section 3 — The single-agent loop

**Canonical algorithm. [high]** Build the smallest valid context from policy, model-specific instructions, relevant tools, scoped rules/skills, environment state, and conversation/run state. Invoke the model. If it emits tool calls, validate/approve them, execute them, append every reasoning/call/result item in provider-required order, update counters, and invoke again. If it emits a valid final message, end the model-directed loop; separately decide whether the product accepts the task as successful. At every transition, honor cancellation/steering and hard limits.

**Control contract. [high]** Define “turn,” “round,” and “step” explicitly. Record model invocations and tool calls separately. Terminal outcomes should include at least `completed`, `partial_limit`, `interrupted`, `failed`, and `awaiting_input`. Steering targets an active turn; queued input targets the next; disconnect changes neither unless policy says so. [10][18][20]

**Prompt shape. [high]** Use stable high-priority policy and model instructions, precise tool schemas, scoped repository rules, and progressively disclosed skills. Keep mutable/request-specific context late for cacheability. Treat published prompts as model-harness examples, not portable templates. [4][5][6][11][21]

### Section 4 — Inference-time compute

**Three axes. [high]** Serial scaling spends compute on a longer stateful trajectory; parallel scaling samples independent trajectories and selects one; iterative refinement revises a candidate using feedback. These are allocations of compute, not architectures. Serial tends to fit persistent environments, parallel tends to fit stateless tasks, and refinement pays when a credible failure/progress signal exists. [25][26][27]

**Policy. [high]** Start with a modest adaptive budget. Increase serial depth while the environment yields new evidence or tests improve; trigger refinement on failure/stall rather than every step; use parallel attempts only when diversity and selection are measured. Stop or lower reasoning effort when marginal progress turns negative. Report benchmark results as curves over compute and include model version, scaffold, tools, turn/token limits, feedback, sample count, and selector—not a score alone. [27][28][29]
