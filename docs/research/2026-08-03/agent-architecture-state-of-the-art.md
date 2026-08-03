# The State of AI Agent Architecture — 2026-08

**Purpose.** A standalone reference on how production LLM agents are built as of August 2026: what the evidence supports, what it does not, and which decisions a team must make. Cite it as *provenance*, not specification.

**Access date for all external sources: 2026-08-03.** Specs, docs and leaderboards are version-drifting; revisions are named at the citation.

**Scope.** Agent *runtime* architecture: the single-agent loop, inference-time compute, multi-agent topologies, orchestration, tool and environment interfaces, memory, planning, verification. Part B covers production operations, the security seam, evaluation, the training/inference boundary, reference architectures and framework selection. Out of scope: pretraining, chat UX, hosting stacks, product values.

**How this differs from the 2026-07-14 pass.** That brief was a pattern catalog; this is eight parallel workstreams reorganized by decision surface, with a scope limit on every number, and multi-agent moved from vendor anecdote to controlled evidence [54][33][34][55]. Six prior positions are corrected: "~15× tokens" is a ratio against *chat*; "+90.2%" is an unpublished internal eval whose own vendor attributes ~80% of variance to token spend; shipped subagent depth default is 3, not 1; hard bounds are sound advice but **not** framework consensus; "tests as ground truth" needed the grader trust boundary; "prefer a fresh-context evaluator" was justified by the wrong mechanism [24][43][6][17][124][113]. New surfaces: MCP `2026-07-28`, published loop internals, benchmark-validity audits, memory-security benchmarks, the self-correction literature, calibration, the regulatory clock.

**Research, not canon.** This is what evidence supports at one date. It does not override a PRD's values, and every default names the condition under which its opposite is right. Several widely repeated numbers here are vendor-internal claims with undisclosed harnesses; they are labeled and are not targets.

**How to read this.** **Confidence tags** attach to claims, not sections: **[high]** = independent sources, a primary spec, or an audited measurement; **[medium-high]** = one strong controlled study, or convergent primaries with a scope limit; **[medium]** = a single study, or practitioner reports without controlled comparison; **[low-medium]** = n=1 with a named mechanism; **[low]** = direction only. Tags are never raised above their source; a figure missing model, scaffold, task count, date or reporter is downgraded. **Citations** are unified across Parts A and B: every `[n]` resolves in §20 Sources, grouped there by subject area. **Synthesis inference** marks a bridging claim no single source states, never above **[medium]**.

**Limitations and deferred items.** Four gaps recur unresolved: no matched-compute multi-agent comparison in the **retrieval-unbounded** regime, precisely where the strongest vendor claim lives; no public tool-count threshold at which catalog degradation warrants retrieval; undisclosed product-level reliability and cost distributions for essentially every shipped product; no accepted benchmark for multi-day interrupted work, maintainability, or calibrated clarification. The research round closed with no deferred issues of its own. §§11–20 are Part B.

---

## 1. Executive summary

### 1.1 What the evidence agrees on

1. **One bounded, typed loop with one writer is the default (§3). [high]** Parallelism sits behind a coordinator with isolated workers and centralized synthesis, not a peer swarm. [7][10][209][213][24]
2. **A final message is a protocol stop, not proof of success. [high]** Code acceptance separately; agents are documented declaring victory before completion. [4][7]
3. **"Turn" is not portable, so every bound must name its counted event (§3.1); the deterministic skeleton is strongest as a plan the runtime executes (§6). [high]** [6][10][18][41][47]
4. **Nominal context is capacity, not reliable working memory (§8). [high]** Losses of 13.9%–85% appear *despite perfect evidence recitation*. [86][87]
5. **Compaction is necessary, lossy, and a state transition (§8). [high]** Batch removals: rewriting the prefix invalidates the cache. [79][82][109]
6. **Every reliable correction loop closes over something the generator did not produce. [high]** Carry-forward B, §10. [112][113][115][116]
7. **Executable ground truth is the strongest verification signal and the most attackable (§10.1). [high]** [124][125]
8. **Strict schema calling is the default; long context degrades tool use through three independent channels (§7), only one of which progressive disclosure addresses. [high]** [66][71]
9. **Fan-out needs one aggregation bottleneck. [medium-high]** Error amplification 17.2× independent against 4.4× centralized (P=0.030, cluster-robust). [54]
10. **Benchmark numbers are system scores, not model scores. [high]** One protocol, 106 tasks, eight backends: a 23.8-point harness spread. [143]
11. **Environment boundaries bound capability; approvals and classifiers only lower probability. [high]** ~93% of prompts approved, ~83% classifier catch on *overeager commands* not attacks, 84% fewer prompts from an OS sandbox (usage, not efficacy) — no figure is an attack-mitigation rate. [63][64][65]
12. **Delegated authority has token plumbing; consent does not. [medium]** *(Carry-forward D; Part B §11.5 owns the detail.)* Under RFC 8693 the **authorization server** consults `may_act` at the exchange and mints a narrowly scoped, short-lived token for that run; the **resource server** authorizes the **current actor plus top-level claims and scope**. Deeper `act` nesting is **audit evidence, not an access-control input** — the chain is not what the resource server checks. Front-channel consent naming the agent came from a draft that expired without working-group adoption. [179][176]

### 1.2 What is genuinely contested

| Question | Status | Conf |
| --- | --- | --- |
| Does the ~45% saturation threshold generalize? | Validated within-domain over 16 configurations; same paper reports leave-one-dataset-out R² = −2.09 [54] | **[medium]** local, **[low]** cross-domain |
| Does multi-agent help at matched compute when retrieval is unbounded? | Matched-token study is multi-hop QA over retrieved context; controlled study matches per-system ceilings [33][54] | open — highest-value missing experiment |
| Step count at which code-as-action beats schema calling? | Only replication: 2 query types × 50 runs, one model, vendor-adjacent outlet [77] | **[low]** |
| Tool count at which degradation warrants retrieval? | No source gives a threshold; curves are continuous [71] | **[low]** |
| Is *fresh-context isolation*, not mere externality, the critic mechanism? | All strong evidence coding/frontend, n=1 vendor harness [4][120] | **[low-medium]** |
| Where should adaptive reasoning effort stop? | Clearest curve is budget-forcing on two 32B open models [22] | **[medium]** |
| Who writes long-term memory; do temporal graphs beat hybrid retrieval? | Both writer paths ship; graphs aid point-in-time conflicts, extraction adds cost and error [90][101] | **[medium]** |
| Is A2A used beyond announcement? | 150+ member orgs and three cloud integrations (press-release claims) against zero retrieved production topologies [37] | contested |
| `pass^k` or weighted partial credit as the product metric? | Depends whether one success suffices; partial-credit evidence is one preprint [119][130] | **[medium]** |
| How much does a low override rate overstate quality? | Needs no labels but is depressed by approval fatigue; gap unmeasured [181][64] | open |

### 1.3 Ten decisions, with default and exit condition

| # | Decision | Default | Deviate when | Evidence | Conf |
| --- | --- | --- | --- | --- | --- |
| 1 | Loop shape | One typed bounded loop; explicit `sampling / awaiting_tool / executing_tool / awaiting_approval / terminal`; one writer | Disposable read-only prototypes | [7][213] | **[high]** |
| 2 | Stop semantics | Separate protocol stop from coded acceptance | Low-risk prose, no oracle, no side effects | [4][7] | **[high]** |
| 3 | Bounds | Name the counted event; cap invocations, tool calls, tokens, time, USD, fan-out, depth independently | A single resource dominates | [6][17][180] | **[high]** |
| 4 | Compute allocation | Adaptive: deepen on stateful progress; resample only with measured diversity **and** an evaluated selector; refine on failure or stall | Hard latency SLOs | [20][21][22] | **[high]** |
| 5 | Fan-out gate | Measure the single-agent baseline; test decomposability; keep writes single-threaded; require a matched-budget A/B | Below threshold, decomposable read-only breadth, one aggregator | [54][30][33] | **[medium-high]** |
| 6 | Plan substrate | Machine-checkable: default-FAIL ledger with a restricted edit surface, or a runtime-executed script | Single-step work | [122][41] | **[medium]**; ledger **[low-medium]** |
| 7 | Tool interface | Strict schema calling; workflow-shaped tools; bounded results; deterministic ordering; deferred loading outside the cached prefix | Composable multi-step work, gated on local measurement | [66][3][69] | **[high]** default, **[low]** cutover |
| 8 | Memory | Typed plane — working context, run ledger, episodic, semantic, procedural, artifacts — with separate scope, authority, retrieval and deletion | Single-tenant prototype | [91][110] | **[high]** |
| 9 | Verification | Executable ground truth → environment observation by a separate agent → cross-family judge with mechanical debiasing → self-check, never a gate. Grader outside the agent's writable filesystem | A judge is wrong on objectively checkable tasks | [112][124][126] | **[high]** |
| 10 | Identity and receipts | One narrowly scoped delegated token per run (`may_act` checked at the exchange); an `eval_receipt` on every reported number; version-pinned OTel GenAI spans | Never reuse user credentials | [179][143][146] | **[medium]**; receipts **[high]** |

---

## 2. State of the art — 2026-08 snapshot

**The convergent shape. [high]** A deterministic shell around a model-directed loop: typed tools, environment observations, hard stops, layered state with compaction, streaming traces, approval at consequential boundaries. [209][7][213][24][216]

| Surface | Loop, state, verification | Topology | Undisclosed |
| --- | --- | --- | --- |
| Interactive coding | Gather → act → verify; append-only events; compaction via an opaque item; durable root memory re-injected; tests, lint, checkpoints, steering | One loop plus fresh-context subagents returning a summary | Success rate, cost distributions [209][210][7] |
| Cloud/async coding | Research → plan → edit → test in an ephemeral VM/branch; one PR per session (one caps at 59 min) | Coordinator over full workers in isolated VMs | Internal topologies; reviewer figures vendor-reported [211][212][30] |
| Research | Browse, read PDFs/images, execute code, cited report; lead saves its plan before truncation; citation agent | Single long-horizon workflow **or** breadth-first fan-out — both ship | Subagent topology, compaction, verifier design, cost [214][24][215] |
| Computer use | Screenshot → action → observation; caller owns coordinate scaling; step-capped (200 against 100 across vendors) | One loop | Memory, subagents; caps plus live-site filtering preclude cross-vendor ranking [216][217][222] |
| Enterprise platforms | SDK-owned loop, sessions, streaming, handoffs, approvals, traces; guardrails at chain edges | Framework graphs or managed runtimes | Policy, tool semantics, evals, governance and UX stay the application's [218][219][220] |

**Ceilings and standards, with scope. [high]** Long-horizon desktop autonomy: 20.6% binary / 54.8% partial at 500 steps over 108 workflows of median 1.6 human-hours (one frontier model, benchmark authors, 2026-06) — this bounds multi-application multi-hour GUI work; it does not license "GUI automation is unusable." Time-horizon fitting gives p50 320 minutes [170, 729] for one model, one harness, 228 tasks: a distribution-sensitive fit, not a constant. MCP is the tool plane, revision `2026-07-28`; A2A v1.0 is the agent plane and stays aspirational; OpenTelemetry GenAI conventions are **Development** status, so pin a schema revision; EU AI Act Article 14 attaches to **high-risk systems only** (§10.4). [74][144][145][53][57][146][178]

**What has *not* converged. [medium, synthesis inference across shipped-system descriptions]** Five workload tradeoffs, not an evidence hierarchy: single long-horizon workflow against breadth-first fan-out; pixel against semantic/DOM control; synchronous pairing against asynchronous PR workers; checkpoint graphs against application loops against durable engines; handoff ownership against manager-owned synthesis. [214][30][221][223]

---

## 3. The single-agent loop

**Canonical algorithm. [high]** Build the smallest valid context from policy, model instructions, relevant tool schemas, scoped rules and skills, environment state and run state. Invoke. On tool calls: validate, approve, execute, append **every** reasoning/call/result item in provider-required order, update counters, invoke again. On a valid final message: end the model-directed loop, then decide acceptance separately. The semantic loop has been stable since ReAct; what changed is representation — typed items with call IDs rather than textual `Thought/Action/Observation` parsing, which makes mismatches, cancellation and retries tractable. **The harness is the whole control envelope**, so record harness version, tools, context policy and stop policy with every number. [1][7][10][15]

### 3.1 Counters and stop conditions are not portable [high]

| Harness | Counted unit | Default bound | Overflow |
| --- | --- | --- | --- |
| Codex (published loop) | User-to-assistant interval; one turn may hold hundreds of tool calls | Ends the turn on an assistant message | Run-level bounds separate [7] |
| OpenAI Agents SDK | Model invocations | 10 | `MaxTurnsExceeded` or fallback; `None` accepted [10][11] |
| Claude Agent SDK | Tool round trips | `maxTurns` **undefined** | Unbounded unless set [6] |
| smolagents | Steps | 20 | Step cap [18] |
| Google ADK `LoopAgent` | Iterations | None inherently — docs say you must implement termination | `max_iterations` or escalation [17] |

Pair one semantic stop with independent invocation, tool, time, token and cost limits. "Hard bounds are non-negotiable" is sound advice, **not** framework consensus. Outcomes: `completed`, `partial_limit`, `interrupted`, `failed`, `awaiting_input`. [6][12][17]

### 3.2 Reasoning state, prompts, skills

**Reasoning state is a protocol invariant [medium]**, and effort is orthogonal to loop length, so meter both — one vendor exposes thinking effort separately from turn count because deeper thinking helps hard tasks and overthinks easy ones. Within a tool-assisted turn the reasoning item must be replayed alongside its call and result; dropping items causes re-derived intent, lost cache efficiency, or invalid continuation. The vendor's ~+3% and ~+5% preservation figures are **directional only**. **Layer the prompt [high]:** stable policy and model instructions first as a cacheable prefix, then tool schemas, scoped rules and skill metadata, mutable context late. One vendor recommends a minimal-but-sufficient system prompt with canonical examples rather than edge-case laundry lists; another reports **deleting** static guardrails as models improved. **Skills are progressive disclosure, not personas [medium]:** across 84 deterministic-verifier tasks and 7,308 trajectories, **curated** skills raised mean pass rate 24.3% → 40.6%, self-generated skills came out slightly negative, and 2–3 focused modules beat 4+ or comprehensive documentation — curation is the supported intervention, not volume. [2][3][5][6][7][8][9][15][16][25]

### 3.3 Run control: steer, queue, interrupt, disconnect [high]

Four distinct transitions; conflating them produces turn-ID races, lost instructions and duplicate execution. One protocol separates `turn/steer` (append to the active turn with the expected turn ID) from `turn/interrupt` (cancel, finishing `interrupted`). **Ordering is correctness:** an April 2026 fix records pending steering injected *before* the interrupted continuation after auto-compaction, so it looked like the newest task. A disconnect must not silently mean cancellation. **A context-isolated worker is a loop-level tool [medium]:** it gets the parent's task prompt rather than conversation history and returns only a final result, trading pollution and action scope against handoff loss — pass paths, errors, constraints and decisions explicitly. [6][12][13][14][24]

---

## 4. Inference-time compute

Three axes, all allocations of compute rather than architectures. [high]

| Axis | Fits | Ceiling and evidence | Conf |
| --- | --- | --- | --- |
| **Serial** (longer stateful trajectory) | Stateful tasks where environment state carries value | Context instability past model- and domain-specific lengths. Five trajectories/task, one ReAct scaffold, five suites: larger budgets helped broadly, weakest on stateless suites [20][21] | **[medium]** |
| **Parallel** (samples plus selection) | Stateless, cheaply judged tasks | **Selection**, not generation: pass@K rises while self-choice saturates or worsens, and a frontier external selector did not close the gap [20][21] | **[medium]** |
| **Iterative refinement** | Where a credible failure or progress signal exists | Ritual reflection regresses: on 165 GAIA tasks, best-of-N moved 55.76 → 63.03 while reflecting on *every* step moved it to 55.15 [19] | **[medium]** |

**More thinking can reverse answers or displace action. [high]** Across 3,900+ trajectories and 19 models on SWE-bench Verified, higher overthinking correlated with lower resolution in three shapes: analysis paralysis, rogue actions, premature disengagement. Budget-forcing two 32B open models from 500 to 16,000 tokens showed a decline between 12k and 16k (−0.9 points, 95% CI −1.4 to −0.4). Effort is a policy, not a quality slider, and cheap adaptive signals exist **[medium]** — inter-rollout action agreement matched fixed self-consistency with 33–65% fewer calls, both limited in transfer by model and benchmark scale. [22][23][26][27]

**Policy. [high]** Start modestly; deepen while environment evidence or tests improve; refine on failure, contradiction or stall rather than after every action; parallelize only with measured diversity **and** an evaluated selector; stop when progress turns negative or simulation displaces action. Report compute curves with model, scaffold, tools, limits, feedback source, sample count and selector — a score without its budget is not comparable. [21][22][26]

---

## 5. Multi-agent topologies

### CARRY-FORWARD A — multi-agent is a conditional, never a rule

**Mean measured improvement from adding agents is 0.0%, 95% CI −58.7% to +77.2%, spanning +80.8% to −70.0%. [medium-high]** Source: a controlled study holding prompts, tools and per-system compute ceilings constant while varying only coordination structure and model capability — 260 configurations, 6 agentic benchmarks, 5 architectures, 3 model families; peer-reviewed 2026-07-24, cross-validated R² = 0.373. [54]

| Factor | Statistical status | What it licenses |
| --- | --- | --- |
| **Single-agent baseline capability** | Survives cluster-robust inference **and** Holm–Bonferroni (P=0.004, P_Holm=0.018) — the only predictor that does | The **~45% saturation threshold**: above roughly 45% single-agent baseline, added agents predict zero-to-negative gains. A **validated selection rule, not a scaling law**; matched the sign of the gain in 94% of 16 configurations |
| Baseline-scaled error amplification | Survives cluster-robust inference (P=0.030) | Route fan-out through one aggregation bottleneck: 17.2× independent against 4.4× centralized |
| Decomposability | Reported factor; two benchmarks at near-identical complexity diverge +80.8% against −70.0% | Test decomposability, not difficulty |
| **Tool intensity**, **coordination overhead** | Directionally consistent across all six benchmarks but **do not survive cluster-robust correction** — **descriptive only** | Do not use as selection criteria |

**Single writer is necessary, not sufficient. [medium]** The vendor camps converged on write-concurrency — multi-agent works "when writes stay single-threaded and the additional agents contribute intelligence rather than actions" — and every shipping pattern obeys it. But it does **not predict gains**: PlanCraft degrades **39–70% under every multi-agent variant** despite no shared mutable artifact, because the task is sequentially interdependent. Write-concurrency-as-the-rule is downgraded on that evidence. [30][54]

**Scope limit.** The threshold is validated within-domain; the same paper reports leave-one-dataset-out R² = −2.09. Treat ~45% as a calibration target for your own domain, not a portable constant: **[medium]** locally, **[low]** across domains. [54]

### 5.1 Topology catalogue

Cheapest first; cost cells name their denominator.

| # | Topology | Wins when | Cost | Characteristic failure | Conf |
| --- | --- | --- | --- | --- | --- |
| F1 | Pipeline | Step sequence known up front | Additive | Cannot handle unknown step counts | **[high]** [38][47] |
| F2 | Single agent plus read-only subagents | One context overloaded, one writer suffices | Low | Under-specified delegation prompt — the worker's only channel | **[high]** [30][42] |
| F3 | Orchestrator → workers → aggregator | Read-only breadth exceeds one window **and** baseline is low | ~15× chat tokens against ~4× single-agent — **denominator is chat, not a matched run** | 50 subagents for trivial queries; duplicated work | **[high]** [24][54] |
| F4 | Hierarchical supervisor tree | Routing across specialists; centralized verification contains errors best | A supervisor turn per hop | Supervisor libraries retiring; one framework now advises supervisors "directly via tools" | **[medium-high]** [38] |
| F5 | Graph / state machine | Policy, branching, budget must be deterministic | Runtime overhead, not extra models | Authoring burden | **[high]** [44][47] |
| F6 | Blackboard / shared scratchpad | Many roles converge on one structured artifact | 45.5k tokens/success against 64.2k and 368.3k — authors' prototype | Omitting the classical **control unit** that picks the next writer | **[medium]** [50][51] |
| F7 | Peer swarm / handoff | Peers partitioned by file ownership under a fixed lead | Unpublished | Unsupervised swarm "mostly a distraction"; status lag deadlocks dependents | **[high]** [30][40][56] |
| F8 | Mixture-of-agents | Single-turn, preference-judged, no tools or state | N agents × L layers | Benchmark unlike agentic work; **[low]** transfer | **[medium]** [35] |
| F9 | Debate / consensus | Protocol **collaborative (non-zero-sum)** *and* debaters **cross-family** | 2.1–3.4× isolated self-correction | Debate hacking — cheap talk under competition, premature consensus under consensus-seeking | **[medium]** [34][55] |

**Provenance for contested cells.** F3's **+90.2%** is a vendor internal eval on an unpublished harness [24]. F9's negative result used 10 homogeneous 7–8B agents, where a **noise control injecting rationales from unrelated problems beat debate 63.2% against 58.8%, p<0.001**; the positive result is a collaborative cross-family protocol beating self-consistency at matched tokens [34][55].

### 5.2 Single against multi, by condition

| Condition observed | Choose | Why | Conf |
| --- | --- | --- | --- |
| Single-agent baseline ≳45% | Single agent | Zero-to-negative predicted gains; one suite degraded 1.3–12.8% across all four variants [54] | **[medium-high]** |
| Sequentially interdependent task | Single agent | 39–70% degradation under every variant, at the complexity score where a decomposable benchmark gained 80.8% [54] | **[high]** |
| Read-only breadth exceeds one window, baseline low | Orchestrator → workers → one aggregator | Separate windows compress in parallel; centralized aggregation contains error ~4× better [24][54] | **[high]** direction |
| Write-heavy work over a corpus that must be *covered* | Deterministic partition plus single-threaded reduce | A non-agentic selector yields a **finite work queue**; completeness rests on **selector recall**, because selectors are inspectable whereas "I've looked everywhere" is unfalsifiable. 72% CVE recall, **vendor-reported** [31] | **[medium-high]** |
| One context polluted, one writer sufficient | Single agent plus read-only subagents | Cheapest isolation; failure mode is the delegation prompt [30] | **[high]** |
| Compute not yet matched between arms | Neither — run the A/B | At matched **thinking-token** budgets single-agent was best or indistinguishable at every budget above the lowest; the matched quantity excludes prompts and answers; one model, one dataset [33] | **[medium]** |
| Peers must edit the same files concurrently | Nothing retrieved supports it | Two shipped answers (ownership partition, single-threaded reduce); typed transactional writes are a prototype [40][51] | **[medium-high]** |

**Failure is organizational, not model-limited. [high]** A taxonomy over 1,642 traces clusters 14 modes into system design ~44%, inter-agent misalignment ~32% and task verification ~24%, with inter-agent failures occurring "even when agents within the same framework communicate using natural language" — collapsed theory-of-mind, not transport: standardizing the wire does not fix coordination. [32]

---

## 6. Orchestration & control flow

**State sharing is the highest-yield thing to get right. [medium-high]**

| Mechanism | Shipped? | Cost / risk |
| --- | --- | --- |
| Full-trace passing | Yes | Highest fidelity and cost; actions carry implicit decisions [29][42] |
| Summary handoff | Yes (one subagent default) | Telephone loss at every hop [43] |
| Artifact / file-as-interface | Yes | Avoids the "game of telephone"; needs conventions and provenance [24][45] |
| Shared mutable store | Yes | Parallel children share one state object; docs say "use distinct keys to avoid race conditions" — **it does not resolve conflicts, it asks you to avoid them** [47][48] |
| Schema-validated typed patches | Prototype only | Most general answer to conflicting writes; nothing retrieved ships it [51] |

**Plan-to-execution binding. [medium]** Plans help in proportion to how deterministically they execute. The strong form moves the plan out of the prompt into an artifact the runtime executes — a script that "holds the loop, the branching, and the intermediate results" — or a deterministic selector pass producing a finite work queue. Plan-as-prompt over-constrains: managers "default to being overly prescriptive, which backfires when the manager lacks deep codebase context." A script's cost is mid-run **human** input. [30][31][38][41]

**Termination, bounds, deadlock. [high]** Termination is a design obligation the frameworks decline (§3.1). Shipped precedents: **16 concurrent workers**, **1,000 total per run**, warnings above **25 scheduled agents or 1.5M projected tokens**, subagent nesting **depth 3** by default (1 disables). **Label partials rather than dropping them** — one product reports claims its verifiers *could not check* as **unverified rather than refuted**. A lead running subagents synchronously can block "the entire system … waiting for a single subagent." [24][31][40][41][43][46]

**Interop and cost. [medium-high on layering, medium on cost]** MCP inside agents, A2A between them — both specs state the layering identically (§1.2 on A2A's adoption evidence). No apples-to-apples cost multiplier exists: "~15× tokens" is against *chat* on one vendor's research workload; competitive/consensus debate costs 2.1–3.4× isolated self-correction for equal-or-worse accuracy on 7–8B models; a vendor's 63.9% token reduction from collapsing tool calls into one program is self-reported on an unspecified workload. Use local compute curves. [24][34][36][37][38][39][49][53][24]

**Coordination pathologies emerge at scale. [medium]** In a marketplace simulation, first proposals achieved 60–100% selection against near-zero for third — 10–30× for **speed over quality** — welfare *fell* as the search limit rose from 3 to 100, and three models redirected **all** payments under injection. Without market framing the defect persists: over 1,620 runs, agents "communicate actively, yet fail to translate interaction into effective distributed computation." [52][56]

---

## 7. Tool & environment interface

**Strict schema calling is the default [high]** — "we recommend always enabling strict mode," with one trap: a request may normalize a schema and silently fall back to non-strict. [66]

**Code-as-action's measured advantage is specifically composition. [high] as a 2024 measurement, [low] carried forward.** The load-bearing study (17 LLMs; an 82-task composition eval plus an API benchmark) reports **up to +20 points absolute at up to 30% fewer actions** and is explicit that on **atomic** actions it is merely comparable. The only replication is thin (2 query types × 50 runs, one model, outlet disclosing that server's vendor as a customer), and a vendor's own 37% token reduction has model, task set and date undisclosed. "Pays above roughly three composable steps" is a **hypothesis to falsify locally**, not a cutoff. [69][77][61]

**Ergonomics: strong mechanism, weak evidence.** Ship **workflow tools, not API mirrors**; return tokens the model can act on, preferring semantic identifiers over UUIDs; **bound results by construction**. Vendor numbers on description quality are unusable as targets — one worked example, a "state-of-the-art" claim with no ablation delta, a 72% → 90% figure from "our own internal testing" **[low]**. The ablated ancestor: revert a syntax-breaking edit showing the agent **all three** of error type, attempted content and original content **[high]**. [3][61][70]

**Three independent degradation channels. [high]**

| Channel | Measured degradation | Progressive disclosure helps? |
| --- | --- | --- |
| Tool **catalog** size, 8K → 120K tokens | 7.59–85.58% across six open-weight 128K models plus one frontier model | Yes — the only channel it addresses |
| Tool **response** length, 10K → 80K tokens | 7–91% loss in answer retrieval | No — bound results |
| **Conversation** length | 13–40% | No — prune and compact (§8) |

Degradation is **continuous and model-dependent**, and **no retrieved source establishes a tool count at which it begins.** Catalog retrieval helps selection — one vendor reports 49% → 74% accuracy on internal "MCP evaluations" with no task count, harness or date (**[medium]** direction, **[low]** magnitude), and independent work matched fixed-K=50 coverage at **K≈7.4 [high]** — while the quoted "150,000 → 2,000 tokens" is **illustrative arithmetic [low]**. Orthogonally, five *recoverable* hazards injected into 1,106 tasks over 4,956 tools drove accuracy down with chain length (0.490 → 0.335) — **weak hazard recovery**, not call volume **[high]**. [71][61][72][73]

**MCP as of 2026-08 — revision `2026-07-28`, previously `2025-11-25`. [high, primary spec]**

| Change | What to do |
| --- | --- |
| Stateless HTTP: no handshake or session id; requests self-describe via `_meta`; cross-call state becomes explicit handles passed as tool arguments | Stop assuming sessions; mint and pass handles |
| `Mcp-Method` / `Mcp-Name` headers let gateways route and authorize without parsing bodies | Route and authorize at the gateway |
| **SSE resumability removed** — a broken stream loses the in-flight request | Application-level retry for long calls |
| Elicitation is multi-round-trip: server returns `resultType: "input_required"`, client **retries the original request** with `inputResponses` plus opaque `requestState` | Retry-with-inputs, not a callback |
| Roots, Sampling, Logging, dynamic client registration deprecated; cache hints normative; tools SHOULD be returned in **deterministic order** | Keep the cached prefix stable; defer on-demand schemas outside it |

**The authorization chapter is the under-read half, and normative. [high]** Clients **MUST** implement PKCE `S256` where capable and **MUST refuse to proceed** when `code_challenge_methods_supported` is absent from authorization-server metadata; **MUST** send the RFC 8707 `resource` parameter, and servers **MUST** reject tokens omitting them from the audience; redirect URIs **MUST** be pre-registered and exactly matched; proxies with static client IDs **MUST** obtain consent per dynamically registered client (the confused-deputy mitigation); **token passthrough is explicitly forbidden**. MCP is good at being a cacheable, gateway-routable catalog-plus-invocation protocol; it is **misused as** context delivery, as a trust boundary, and as a substitute for an in-process function call. [59][60]

**Substrate is a threat-model choice. [high]** Code execution as a universal tool buys in-environment filtering, control flow without round-trips, PII tokenization, and filesystem-as-workspace; isolation strength is an explicit tradeoff, one isolate-based design claiming ~100× faster starts than a container while conceding "security bugs in V8 are more common than security bugs in typical hypervisors." Keep sandbox credentials *outside* the sandbox, behind a proxy that validates the target. [62][67][68]

**Computer use has two ceilings and the security one binds first. [high within scope]** Capability: 20.6% at 500 steps (§2). Security: pop-up attacks achieved **76.67–100% payload delivery across every model category** (330 tasks, 6 environments, 6 vectors, 9 agents, 2,970 trajectories), with GUI-specialized grounding conferring **no** security benefit. Accessibility trees added to screenshots *increase* steps on visually rich applications and *decrease* them on OS, editor and browser targets — go hybrid per application **[medium]**. [74][75][76]

**Determinism gained normative support; enforced idempotency did not. [high]** An advisory `idempotentHint` exists alongside read-only, destructive and open-world hints, but the schema states **all** are hints "not guaranteed to provide a faithful description of tool behavior" and must not drive tool-use decisions from untrusted servers. A **protocol-enforced idempotency key exists nowhere in the current revision**, so deduplication belongs at the application layer, enforced by the callee; replay recording is live but unstandardized, and the hard part is **request identity** **[medium]**. [58][73][78]

*The untrusted-tool-output security seam — allowlist-as-capability-grant, the mechanism-labeled control table, the OWASP mapping — is Part B §11.5–§11.6.*

---

## 8. Memory & context architecture

**Framing claim. [high]** Context is a **task-scoped working set assembled from typed, durable memory** — not the memory system itself. No reviewed product exposes clean primitives; most collapse episodic and semantic memory into text or retrieval stores. [91]

| Layer | Lifetime / writer | Policy notes |
| --- | --- | --- |
| Working context (messages, tool results, reasoning state) | One turn; harness | Some providers preserve reasoning/tool state across calls [2][83] |
| Scratchpad / run ledger (plan, todos, budgets) | One run; model plus runtime | *Not* long-term memory. One product preserves pending tasks in summaries; another recites an updated todo near the tail [82][110] |
| Episodic (transcripts, events, successful trajectories) | Cross-run; append or extractor | Store immutable episode and source IDs [90][94] |
| Semantic (user facts, entity relations, profiles) | Cross-thread; extractor or user write | Version with `valid_from`, `valid_to`, `observed_at`, provenance [84][89][93] |
| Procedural (rules, skills, reusable plans and code) | Cross-run; developer or reviewed learner | Autonomous mutation exists; **governance is immature** — stage, diff, evaluate, approve [82][101] |
| External artifacts (files, plans, patches, databases) | Task/project; tools and humans | Source of record; the prompt is a cache of slices [81][82][110] |

The taxonomy is descriptive, not cognitive — records change class as episodes become summaries and summaries become playbooks. The boundaries that matter are **scope, authority, mutability, retrieval, provenance, deletion**: implement a typed plane keyed by `(tenant, user, project, agent, memory_class)`, not a generic `memories` table. **[high]** [91]

**Context rot. [high]** Overlap-free needle testing: at 32K, **11 of 13** models rated ≥128K fell below 50% of their short-context baseline, one frontier model 99.3% → 69.7% [86]. Length-alone testing on five named models found **13.9%–85%** losses **despite perfect evidence recitation and placement** [87]. Degradation is non-uniform, and a profiling benchmark over 26 models on an 8K–1M grid found **seven moved ≥2 ranks** between reporting lengths: prefer capability-by-length profiles to a headline window size [85][111][88].

**Compaction contract and cache economics. [high]** One platform defaults to a 150,000-input-token trigger (minimum 50,000), emits a compaction block and discards prior blocks; one product documents that tool output, reasoning and conversation-only instructions can disappear while durable root memory is re-injected. Preserve objective, constraints, decisions and rationale, open questions, todos, evidence and restorable pointers. Editing earlier blocks invalidates the downstream cached prefix, so clear enough tokens to amortize a new cache write — tiny frequent compactions are the anti-pattern, and whole-playbook rewrites produce **brevity bias** and **context collapse**, so prefer append/refine deltas. **Assembly order:** stable policy/tool prefix → current request → pinned constraints → run ledger and todos → small retrieved set → artifact excerpts → recent turns, with per-section budgets. [2][79][80][82][91][109][110]

**Retrieval is routed, not chosen ideologically. [medium]** Exact identifiers and current repository state → grep or BM25. Semantic recall → a **hybrid** lexical-plus-dense index with reranking; one vendor evaluation (code, fiction, arXiv, science — **not** finance) cut top-20 failure 5.7% → 2.9% with contextual embeddings plus BM25 and → 1.9% with a reranker, but **only the code dataset is public**. Multi-hop or ambiguous queries → bounded iterative search, where a retriever trained for multi-turn agent search beat one-shot retrieval on seven QA benchmarks, without comparing grep. Small stable corpora → long context. [98][99][100]

**Writes, conflicts, forgetting. [medium]** Who writes is unresolved: agent writes are timely but injection-prone, background extractors keep work off the hot path but add delay and another fallible model, and both ship. Conflict handling divides into overwrite-style decisions (`ADD`/`UPDATE`/`DELETE`/`NOOP` chosen by a small model) and **bi-temporal validity closure**, which is materially more auditable. **"Forget" is five operations [high]:** hiding from retrieval, deleting a derived fact, deleting the source, cache expiry and legal erasure each need their own contract, because synthesis can rebuild a fact from surviving sources. [89][90][92][93][101][102][109]

### CARRY-FORWARD C — memory benchmark validity, stated precisely

**The widely used long-term-conversation benchmark's audit is directional, not decisive.** Its final peer-reviewed set is **10 human-edited conversations averaging 600 turns, 16K tokens, up to 32 sessions** — not the earlier 300-turn/9K description sometimes cited [96]. A reproducible, human-reviewed **vendor-run** audit (April 2026) found **99 of 1,540 score-corrupting errors (6.4%)** and a small-model judge accepting **62.81%** of intentionally wrong vague-but-topical answers. **The auditor has a competing-benchmark interest, so both figures are directional** — but the actionable consequence stands: **small score deltas on this benchmark are uninterpretable.** [103]

**The other standard benchmark's short split can be passed without any external memory. [high]** That configuration is **~115K tokens per question and explicitly fits 128K-context models**, so a frontier long-context system can treat it as a long-context test, not a memory test; the ~1.5M-token configuration is the one that forces external memory. Reporting a memory-architecture win on the short split without stating the model's context window is not evidence about the memory system. A complementary benchmark adds incremental ingestion and selective forgetting. [97][94]

**Using both together (synthesis inference, [medium]):** credible memory evaluation needs audited labels, a split whose token budget exceeds the model's context window, and provenance and deletion assertions — otherwise it measures long-context capability, judge leniency, or both.

**Persistent memory is a security boundary. [high]** Memory amplifies prompt injection **across time**: sleeper-memory work stores external content and activates it later, one peer-reviewed attack demonstrated retrieval-triggered backdoors, a later one injected malicious records through **ordinary query-only interaction**. Source classification is therefore audit metadata, **not a sufficient write gate**: require namespace authorization plus intent, content and policy checks; treat inferences as low-confidence with TTL; stage procedural changes as reviewed diffs; carry tenant-bound keys, derivation lineage and write ACLs. Memory-security **evaluation is now a benchmark family** — write→retrieve attack suites, deletion-leakage benchmarks, a Write–Execute–Forget lifecycle suite — so adopt those protocols. Part B §11.6 owns the surrounding seam. [95][104][105][106][107][108]

---

## 9. Planning & decomposition

Organize by plan **substrate** — it decides whether anything downstream can check the plan.

| Substrate | Wins when | Ceiling / cost | Conf |
| --- | --- | --- | --- |
| **Implicit (ReAct-style)** — next step recomputed each turn | Short-horizon, adaptive work | Never exposes the whole task; costly as history grows. Ceiling: agents "built with simple LM constructs (like function calling or ReAct) perform poorly" — ~61% `pass^1` on one retail suite, ~35% on an airline suite, authors' harness. **No source measures its production share, so "the default" is an impression** | **[high]** number, **[medium]** prevalence |
| **Explicit plan-then-execute** — ordered step list up front, replanning as recovery | The plan is a contract someone else checks; must survive a context boundary; a human approves spend | Overhead on single-step tasks and wherever each step depends on the last | **[medium]** — practitioner reports only |
| **Artifact / state-file plan** — a machine-checkable ledger: an initializer writes 200+ entries all `"passes": false` and agents may only flip that field; generalized as a **default-FAIL contract** — "the agent can't mark it passing without opening evidence first" — enforced by a pre-tool hook | You want "did it succeed?" to be a query, not a narrative | **n=1: one vendor, one prompt, one model, no controlled comparison against prose** | **[low-medium]** |
| **Search over plans** — candidates scored by a process reward model | Math-like domains with a trained scorer | Compute-optimal allocation matched best-of-N at ~4× less test-time compute. **Says nothing about production adoption** | **[medium]**; adoption unevidenced |

**Replanning is an escalation ladder, not a reflex. [medium]** Retry with backoff on transient errors → local step substitution on a deterministic "not found" → full replan on a **contradicting observation** → abort after K consecutive failures on one step. Guardrails: step cap, a **replan budget separate from the step budget**, progress detection, semantic deduplication. [119][136][137]

**Approval placement (synthesis inference, [medium]).** A script-executed plan removes mid-run human input while approval gates remain standard practice, so stages requiring sign-off should be separate runs, not in-script branches. Neither source states this; it follows from both. [41][138]

---

## 10. Verification, self-correction & quality

### CARRY-FORWARD B — external feedback is the mechanism; fresh-context isolation is not established as *the* mechanism

**Feedback must originate outside the generator's own reasoning. [high]** Four independent lines converge:

| Source | Design | Result |
| --- | --- | --- |
| Intrinsic self-correction study (peer-reviewed) | Removes the oracle label deciding when to stop revising | "The accuracies of all models drop across all benchmarks"; on one math suite the model kept its initial answer 74.7% of the time and, among changes, more often went correct→incorrect [112] |
| Field audit (journal) | Audits prior setups for unfair conditions | **No work demonstrates self-correction from prompted-LLM feedback on general tasks**; it works where reliable external feedback exists [113] |
| Tool-ablation study (peer-reviewed) | Same prompt, tool removed | With tools, +7.7 F1 across three QA sets and +7.0 across three math sets; tool removed, +2.1 → −1.8, toxicity rising **above** the untouched baseline [116] |
| Strongest positive counterexample | ~20% average gain over seven tasks | **+49.2** on preference-judged dialogue against **+0.0 / +0.2 / +0.2** on math, where one model's feedback was "everything looks good" on **94%** of instances. It improves subjective quality; **it does not find errors** [115] |

**The one demonstrated softening is at training time, and a builder who cannot train cannot buy it. [high]** SFT on offline correction traces is "often insufficient" (+1.8% against −11.2% for the base model); two-stage **on-policy RL** with a correction reward bonus reached +4.4%, the first significantly positive delta. [114]

**But "external" ≠ "fresh-context isolated." [low-medium]** The claim that *fresh-context isolation*, rather than mere externality, is the effective mechanism rests on **one coding/UI vendor harness: n=1, one prompt, one model, no ablation** — a generator builds while an evaluator with a browser-automation tool **clicks through the running application**, grading each sprint and citing file and line. That evaluator's value came from **acting in the environment**, not from re-reading the diff: an externality argument, not an isolation argument. Shipped variants span both strengths, from a per-turn evaluator that "does not call tools" to a no-write evaluator subagent reviewing the diff "from a context window that never saw the build." **Do not upgrade isolation above [low-medium], and do not assume it transfers to research or synthesis** — all strong evidence is coding and frontend. [4][120][122][123]

### 10.1 The verifier hierarchy

| Tier | Mechanism | Strength | Limit / attack surface |
| --- | --- | --- | --- |
| 1 | **Executable ground truth** (tests, compiler, deterministic state check) | Strongest available **[high]** | **Most attackable.** A 10-line `conftest.py` hook resolved **500/500** SWE-bench Verified and **731/731** SWE-bench Pro instances with **zero issues solved**; an audit of 10 agent benchmarks found 219 flaws. Root cause is constant: **the patch runs in the grader's container** [124][125] |
| 2 | **Environment observation by a separate agent** | Catches what tests do not encode | Rests on one vendor harness (carry-forward B) **[low-medium]** [120] |
| 3 | **Cross-family judge with mechanical debiasing** | Scalable; **[high]** that biases exist, **[medium]** on effect sizes | Position bias across 15 judges and ~150k instances is non-random and **worst when candidates are close in quality**; self-preference is real but smaller than first reported. Mitigations are mechanical: swap positions, tie on flips, recalibrate against human labels [126][127][128] |
| 4 | **Self-check** | A heuristic, never a gate **[high]** | Carry-forward B |

**The grading trust boundary is a security property. [high]** The cheapest path to a green signal is forging it, so the grader must not run in a filesystem the agent can write to. One platform's training guidance says the same from the other side: use a model judge only when code cannot grade the answer, **with a separate model and an explicit step to evaluate the judge**, because a model may "learn to reward hack your grader… without actually being correct." **Process against outcome supervision [medium-high]:** process supervision beating outcome supervision is the foundational result, but a peer-reviewed survey documents a shift to *implicit* and *generative* process reward models because step labels are expensive and noisy — deterministic **outcome** verification remains the authority. [117][124][125][133][134][135]

### 10.2 Selection: verification buys reliability, not capability [high]

Self-consistency remains the canonical cheap selector (+17.9%, +11.0%, +12.2% on three math suites for a 540B model), but **its precondition is routinely violated in agent products**: it marginalizes reasoning paths onto a **unique closed-form answer**, so it cannot select among free-form reports. The practical counterpart aggregates *weak* verifiers — 30+ reward models and judges, individually 43–62% accurate — lifting first-sample accuracy **11.2–27.8 points** across four suites (authors on their own work) **[medium-high]**. [118][129]

**`pass@k` against `pass^k` is a product decision. [high] for the primary numbers.** The benchmark introducing `pass^k` showed one frontier model falling from ~61% `pass^1` to under 25% `pass^8`. The arithmetic builders need: a 75%-per-trial agent passes three consecutive trials 42% of the time, and by k=10 the two metrics "tell opposite stories." A 2026 preprint (396 tasks, 10 open-weight models) adds a graceful-degradation score whose gap from `pass@1` **widens at long horizons** **[medium]**. [119][121][130]

### 10.3 Machine-readable success, and calibration [medium]

Make success a query: **default-FAIL criteria with evidence requirements** (§9); **weighted-subtask partial credit** so a long run reports 0.44 rather than "failed" — the only signal that varies at long horizons, though gameable; **a fresh-context grader returning a structured verdict** seeding the next session. A metric returning score **plus feedback** beats a plain float, or "concrete failure modes never reach" the proposer. [122][136][139]

**Calibration is the weakest link. [medium]** Two 2026 preprints agree in direction, neither replicated. One finds models "neither cost-aware when articulating their verbal confidence, nor strategically responsive when deciding whether to engage or abstain." The other (17 models, 4 harnesses, authors' benchmark) reports best paired accuracy **59.5%** with **13 of 17 below 50%**, and names an agent-specific failure: **post-hoc abstention** — taking the irreversible action, then claiming refusal. Never gate on stated confidence; gate on an external check or policy, and put a feasibility check *before* the call. [131][132]

### 10.4 Human-in-the-loop as verification [medium]

Approval gates buy real safety at a point of no return and mostly latency elsewhere. Three properties make one load-bearing: it precedes the **first irreversible action** (gating the confirmation email after the refund issued is theatre); it shows the **artifact**, not an AI-written summary; it blocks **one decision**, not the run. A gate verifies **intent and blast radius**, which no test covers. **Approval rate is an instrument, not a proof** — near-100% means either the action class earned auto-execution or review stopped discriminating, and only sampling rejected-in-hindsight cases separates them (§1.1).

**Regulatory scope, stated precisely. [high] on the text, [low] on scope-to-your-product.** EU AI Act Article 14 applies **only to high-risk AI systems**: 14(1) requires such systems be designed so "that they can be effectively overseen by natural persons"; 14(4)(b) requires oversight personnel to "remain aware of the possible tendency of automatically relying or over-relying on the output" — automation bias in law — with a stop mechanism bringing the system "to a halt in a safe state." A general-purpose coding or research agent is **not automatically in scope**. Applicability dates conflict across sources; treat the Commission timeline as controlling (Part B §11.9 reconciles them). [138][177][178]

**Anti-patterns.** "Check your work carefully" addressed to the generator; a grader inside the agent's writable workspace; single-ordering same-family judging; majority vote over free-form output; prose plans and reflexive replanning; binary outcomes on long-horizon work; gating on stated confidence, or gating every action. [112][119][124][126][131]

---

## 11. Production architecture, safety and operations

Everything in §§3–10 assumes a substrate. Two cautions frame this section: the reliability case for durable execution is a single vendor self-report [182], and supervision plus hostname allowlists both **failed measurement at the vendor that measured them** [64]. Numeric defaults live once, in §17.

### 11.1 Execution model and the durability boundary [high on mechanics, medium on payoff]

Two substrate families: *journal-and-replay*, reconstructing state from a step journal [183][186][187], and *actor-with-durable-state*, an addressable agent with embedded durable state, idle at zero compute [185].

**Buys:** completed activities are not re-executed, and waits are durable at zero compute, so a pending approval survives process loss [183][186]. **Does not buy:** exactly-once side effects — an activity reaches history only when it returns or errors, so a worker that finishes then dies is retried, the engine's own example being duplicate payment charges. The contract is **at-least-once execution, exactly-once observation** [186]. **Costs:** replay determinism, plus payload and history limits that terminate a run outright (§17) [183][184].

The trigger is infrastructure churn, not run length. One vendor reports "one 9" before adopting an engine and "past two 9s" after at >50M actions/day, with no availability definition, denominator, window or harness [182]. **The mechanism travels; the figure does not.** Default to in-turn orchestration with application checkpoints and a resumable stream; adopt an engine when runs outlive the process, keeping workflows short and task-scoped — the correction that vendor made to its own design [182].

### 11.2 Idempotency and ambiguous outcomes [high]

Because execution is at-least-once, the deduplication key belongs at the **callee**: a caller-supplied identifier committed with the mutation in one ACID operation, replaying a *semantically equivalent* response rather than an `AlreadyExists` error that hides which request did the work [186][200]. A tool that cannot honour a key is **non-retryable**. **Ambiguous outcomes need their own path:** a write that timed out mid-flight has an unknown result, so read state back and escalate — a bare retry is how one action becomes two [186][200]. Bound retries per activity *and* per run, then quarantine a run that fails deterministically on replay (**synthesis inference [low]**; nothing retrieved covers poison pills). Gap from §7: no MCP revision enforces an idempotency key, and the advisory `idempotentHint` must not drive decisions from an untrusted server [58].

### 11.3 The streaming contract [high]

**Resume has two layers and only one understands your run.** Transport resume replays bytes — `id:` sets the last event id, the client returns `Last-Event-ID` [198]; application offsets sit above, with monotonic sequence numbers and a start-after parameter, because only they know which *run* events a client missed [189]. One protocol supplies the vocabulary for run and step lifecycle, text, tool calls, snapshot-plus-delta state and resume, so a reconnecting client renders a snapshot then resyncs [199]. SSE is what these APIs document; nothing retrieved compares deployed share **[low]**. Three states stay distinct: *disconnected* (keep running, buffer), *cancelled* (stop, release budget, terminal event, idempotent), *paused for approval* (durable, resumable by token) [189]. Two traps: a background response not created as a stream cannot be re-streamed, and one provider's EU region forbids background mode, so **residency can silently remove your resume mechanism** [189][196]; and MCP's removed SSE resumability makes a broken stream lose the in-flight request [57].

### 11.4 Human-in-the-loop machinery [high on mechanism, medium on policy]

Three implementations agree on mechanism: a graph framework's `interrupt()` suspends at the call site, persists via the checkpointer and waits **indefinitely** [188]; one SDK records an *interruption* instead of executing the tool and returns resumable state [190]; another evaluates hooks → deny → ask → mode → allow → callback, where **auto-approved tools never reach the callback**, so per-call audit belongs in a pre-tool hook [197]. Gate by per-tool risk: writes, reversibility, permissions, financial impact [191].

**Four traps [high]:** *durability illusion* — an in-memory checkpointer kills a pending approval with the process; *idempotency* — on resume the node restarts from its beginning, so writes before the interrupt fire twice [188]; *gate placement* — guardrails run at chain edges, so validation belongs beside the side-effecting tool [190]; *inherited privilege* — bypass and auto modes cannot be overridden per subagent, so a **topology decision silently changes the safety posture of every inner call** [197].

Bind the decision, not the intent: an `awaiting_approval` record keyed by `(run_id, step_id, tool_name, argument_hash, bundle_version)` with expiry and expiry action, resumed by a **server-issued** token against a re-derived hash that refuses if it moved — so the human authorised *that* call, not what the agent proposes next [188][190]. Nothing retrieved gives a default expiry, and in cloud settings "the cost of blocking is much higher" **[medium]** [182].

### 11.5 CARRY-FORWARD D — identity and delegation, stated mechanically

**Delegated authority has token plumbing; consent does not. [medium]**

- RFC 8693 separates **delegation** — the agent keeps its own identity while acting for the user, carried in an `act` claim — from **impersonation**, where the token still identifies the user [179].
- The **authorization server** consults `may_act` **at the exchange** and mints a narrowly scoped, short-lived token for that run: `subject_token` the user, `actor_token` the agent [179].
- The **resource server** authorizes the **current actor plus top-level claims and scope**. Deeper `act` nesting is **audit evidence, not an access-control input** [179].
- So least privilege lives entirely in the **scope minted at the exchange**, never in chain depth; the `act` chain is what you read after an incident.
- **Consent is unstandardised**: front-channel consent naming the agent came from a draft that expired 2026-02-27 without working-group adoption [176].

Practice: one narrowly scoped delegated token per run, no user-credential reuse, credentials kept **outside** the sandbox and brokered behind a proxy that validates the target [62][64]. Cost: an STS plus cooperating resource servers. OWASP's agentic top ten supplies the surrounding taxonomy — a taxonomy, not a measurement — pairing privilege abuse with scoped per-agent credentials, cascading failures with blast-radius isolation and per-worker budgets, trust exploitation with untrusted-by-default tool output, and rogue agents with monitoring plus a kill switch [202]. NIST's SP 800-53 AI overlays reached annotated outline on 2026-01-08, so agent overlays remain **upstream of a final** [201].

### 11.6 The untrusted-output seam: label the mechanism, not the number

Part A deferred this table. Every figure below is a usage or approval statistic; **none is an attack-mitigation rate**, and reading them as one is the most common security error in this space.

| Control | Mechanism class | Measured evidence |
| --- | --- | --- |
| OS or container sandbox (gVisor, bubblewrap/Seatbelt, local VM) | **Capability removal** | 84% fewer permission prompts — usage, not efficacy [63]. "The weakest layer is the one you built yourself": gVisor and seccomp held, the custom proxy failed [64] |
| Hostname allowlist | **Capability grant, not a filter** | An allowlist passed a legitimate API host while an attacker's planted key uploaded user files to the attacker's account [64] |
| Managed egress firewall | **Partial coverage** | Covers only Bash-tool processes; "sophisticated attacks may bypass" it [205] |
| Human approval prompt | **Probability reduction** | ~93% of prompts approved; fatigue, not malice, is the failure [64] |
| Command classifier | **Probability reduction** | ~83% catch rate on *overeager commands*, not attacks [64] |
| Credential brokering | **Capability removal** | Credential inside the sandbox: a red-team phish exfiltrated `~/.aws/credentials` in **24 of 25 retries** [64] |
| Content defences for GUI agents | **Probability reduction** | Pop-ups reached 76.67–100% payload delivery across every model category; GUI-specialised grounding gave **no** security benefit [76] |
| Memory write gate | **Capability removal plus authorization** | Poisoning succeeds through query-only interaction; retrieval-triggered backdoors demonstrated, deletion leaks benchmarked [95][104][105][106][107][108] |

**Environment boundaries bound capability; approvals and classifiers only lower probability** — Part A §1.1, restated, not raised.

### 11.7 Cost, caching, rate limits and tenancy

**Caching is a rate-limit lever before a cost lever [medium-high].** On one platform cache reads mostly skip input-token-per-minute accounting, so a 2M ITPM ceiling at an 80% hit rate passes ~10M input tokens/minute; reads cost 0.1×, one-hour writes 2× [192][193]. Another reports a customer moving 60% → 87% hit rate with an explicit cache key, saturating near ~15 requests/minute per key [195]. Hence stable content first, dynamic last, no timestamp or user id in the prefix, and a long TTL for approval-bearing runs [192][195]. Track hit rate as an SLI; prefix stability constrains personalisation, and compaction rewrites the prefix (§8).

**Backpressure [high].** A 429 is your limit — honour `retry-after`, and the rate-limit headers name whether requests, input or output tokens tripped — while a 529 is fleet-wide [193][194]. Retry with capped exponential backoff and **full jitter**, one layer, idempotent calls only; no-jitter backoff is the measured worst case [203] and SDKs already retry. Failover belongs in the gateway, restricted to an ordered config-defined chain with events traced, since "the same prompt can behave differently on the fallback model" **[medium]** [206].

**Tenancy [medium on shape, low on transfer].** One provider's inference-fairness stack combines admission rate-limiting, performance tiers and **deficit round robin** with a per-tenant quantum debited by request cost [204]. It schedules its own accelerators, while an application gateway rations against someone else's limits, so only the **shape** transfers — per-tenant queues, a cost-debited quantum, urgency kept inside a tenant — and whether quanta behave the same against a remote token ceiling is untested **[low]**. Key tenant id into run state, the event store, sandbox volumes **and the cache-prefix namespace**: a shared prefix cache is a cross-tenant read channel (**synthesis inference, [medium]**).

### 11.8 Degrade modes and SLOs

**The degrade ladder [medium]:** stop scheduling new actions → return partials already produced → name what tripped and which parts are incomplete → escalate if a gate exists → **never discard completed work**. Hard stop for cost runaway and confirmed injection, soft limit for latency overrun, a global kill switch beside the per-task one [180]. Label partials: one product reports claims its verifiers *could not check* as **unverified rather than refuted** [41]. **Trips must be plural** — token count alone misses cheap endless loops, step count alone misses few-but-expensive calls — so combine §17's token, USD, step, failure and time trips with loop detection on a hash of recent tool calls, every stop writing a structured log because unlogged breakers cannot be tuned **[medium]** [180].

**SLO vocabulary has converged; one SLI has a known bias direction [medium].** Availability → task success rate; latency → time-to-first-token plus completion **including** human wait; errors → escalation rate; cost → tokens per task; plus a **judgement SLI** from override and correction rate, offered as sufficient signal without ground-truth labels [181]. It needs no labels but is depressed by approval fatigue: against ~93% blanket approval, an absent override records fatigue as readily as a correct action [64]. Treat it as a **floor on detected error, never an estimate of true error**, paired with §12's sampled review — **[high]** that it understates error. Published targets (99.5% availability, sub-800 ms p95 first token) come from a consultancy post with no population or harness **[low]** [207].

### 11.9 Rollout and governance

**Gate sequence [medium, practitioner consensus]:** offline regression suite as a hard block → **shadow** on mirrored traffic, the candidate reasoning normally while every write is intercepted as a dry run → **canary** behind pre-registered gates → stepped ramp → automatic rollback. Risk-tier it: prompt wording is bounded, a new tool changes tool selection everywhere, a model swap touches everything. Ship an **immutable versioned bundle** — model, prompt, tool schemas, retrieval config, guardrails — referenced by id outside application code so rollback needs no redeploy, and pin sessions with graceful drain, or a plan finishes on a version it did not start on: "for long-running agent workflows this isn't an edge case; it's the common case during rollback" [208].

**Governance [high on the text, low on scope-to-your-product].** Per the Commission, the AI Omnibus entered force 2026-07-27, moving Annex III high-risk obligations to 2027-12-02 and Annex I to 2028-08-02, with general application from 2026-08-02 [178]. Article 14 attaches to **high-risk systems only** and reads like an engineering spec: effective oversight by natural persons, personnel who remain aware of automation bias, and a stop mechanism halting the system in a safe state [138][177]. Dates conflict across secondary sources — treat the Commission timeline as controlling. Residency is **two promises**, storage-at-rest and in-region processing; one provider's controls are project-scoped, fixed at creation, and carry a 10% uplift for eligible models released on or after 2026-03-05 [196].

---

## 12. Evaluation and observability

**A benchmark number is a system score. [high]** One fixed protocol over 106 tasks and eight backends produced a **23.8-point harness spread** [143]. **Validity is a first-order risk. [high]** A peer-reviewed independent audit found outcome-validity flaws in seven of ten benchmarks and task-validity flaws in seven, including exploitable or false-positive grading [155]; a vendor audit estimates ~30% of one public split broken and retracted its own recommendation [149]; an audited container suite corrected **28 of 89** tasks between revisions [150].

Six failure modes recur, each a reason to demand a receipt rather than a percentage: contamination and gaming, with executable shortcuts demonstrated rather than hypothesised [155][159]; **harness–model confounding**, that spread plus a lab's scores shifting after a harness migration [143][145]; task and grader defects [149][150][155][170]; non-determinism, where one run hides simulator paths, tool outages and sampling while `pass@k` rises with retries and `pass^k` falls [156]; **cost-blind saturation [medium]**, since unrestricted turns, effort and parallel samples purchase score; and **judge error [medium]** — position, style, verbosity and self-family bias, needing blinded ordering, evidence-bearing verdicts, abstention and periodic human recalibration [126][127][128].

### 12.1 Capability → benchmark map

Capability probes, not release gates (§12.2).

| Capability | Probes (and what they measure) | Caveat you must state |
| --- | --- | --- |
| Repository-scale code change | SWE-bench Full/Verified/Multimodal (2,294 / 500 / 517) and Pro (+1,865 longer tasks) [147][148] | Two incompatible receipts: 43.72% (named agent and model, 250 turns, 730 tasks) [148] against 80.3% (unnamed system, undisclosed scaffold, 731 tasks) [149]; contamination and scaffold confounding [155] |
| Terminal and CLI work | Terminal-Bench 2.1: 79.1% against 73.3% on 2.0, attempts unstated [150] | Version belongs in the receipt; 2.0 results are superseded |
| Spec-to-implementation, paid tasks | SWE-Lancer (1,488 paid tasks) [152]; Commit0 (54 libraries from specification) [153]; Aider polyglot (225 edits, 88.0% after up to two sequential repairs, $29.08) [151] | SWE-Lancer tests could be overwritten to score 100% without solving tasks [155]; the Aider figure is **not** i.i.d. `pass@2` |
| Tool use over changing state | GAIA2/ARE (1,120 asynchronous scenarios, action-level verification, ~42% `pass@1`) [154]; τ²-bench (dual control, `pass^k`) [119][156]; BFCL v4 [157]; MCP-Universe (11 live servers) [158] | τ-bench could award 38% to a do-nothing agent and 40% to database-dumping spam [155]; an unweighted mean is not outcome success; live services drift |
| Web and desktop control | OSWorld 2.0 (108 workflows; 20.6% binary / 54.8% partial) [74][144]; AndroidWorld (116 tasks, 20 apps) [160]; BrowseComp (51.5%, benchmark-trained system on its own harness) [159] | Substring matching overestimated one suite by 5.2% [155]; 200- against 100-step caps and live-site filtering preclude ranking [216][217][222]; human step-cost is separate [75] |
| Research reports with citations | DeepResearch Bench (100 bilingual expert tasks, rubric plus citation checks; 48.88 against 46.98 under one judge) [162] | Judge replacement moves the scale; web evidence mutates |
| ML and science autonomy | MLE-bench (75 competitions, board **frozen 2026-04-24**) [163]; RE-Bench (7 environments, 71 expert attempts) [164]; PaperBench (20 papers, 8,316 rubric items; 26.0%±0.3) [165] | Scaffold–model interaction is first-order — the same scaffold *hurt* another model [165]; test feedback can leak |
| Long-horizon and economic value | METR time-horizon fitting (228 tasks, one harness, p50 320 min [170, 729]) [145]; GDPval (1,320 occupational deliverables, one-shot) [166]; Vending-Bench 2 (year-long simulation; top five-run mean $11,181.87 ± $2,094) [167] | Human-time estimates and task composition drive the fit; cash is narrow and gameable |
| Safety and security | AgentHarm (110 base / 440 augmented) [168]; AgentDojo (97 tasks × 629 injection cases, reporting benign utility, utility under attack and attack success separately) [169]; Cybench (40 CTFs, documenting an answer-leaking harness incident) [170]; SecureWebArena [76] | Synthetic harms and semantic judges misgrade; CTFs are narrower than defensive work |
| Trajectory and process quality | AgentProcessBench (two expert labels per trajectory, 89.1% raw agreement, κ=0.767 before discussion) [161] | Process rubrics can penalise novel-but-valid strategies |
| Memory | §8's audited long-conversation set, the long-context-passable short split, incremental-ingestion suites [94][96][97][103], plus write→retrieve, deletion-leakage and lifecycle security suites [104][105][106] | Report the model's context window beside any memory result, or you measured long context |

### 12.2 Evaluating your own agent [high, normative]

Build a **private capability matrix** from real intents — routine, hard, adversarial, ambiguous, tool failure, cancel-and-resume, budget exhaustion — as a frozen release set plus rotating canaries plus a failure-derived regression set. Define each case as `(initial state, user goal, allowed/forbidden effects, acceptable final states, rubric, budget)`, prefer exact state and artifact graders, and store a **golden trajectory envelope** of required and forbidden calls rather than one exact path. Score outcome, process, economics and reliability separately (`pass^1`; `pass@k` only where verified retries are a product feature; `pass^k`; confidence intervals) [155][156].

Run three tiers — deterministic unit and contract tests per change, a live-model smoke suite in PR CI, multi-seed statistical suites nightly — pinning model snapshot, prompts, tools, image, judge and scorer versions, and gating on confidence intervals and per-slice regressions rather than aggregate means [121]. Judge open outputs with dimension rubrics, an independent cross-family judge, required evidence, an `unknown` option, and judge TPR/TNR on held-out expert labels by slice [121][171]. Use experts for correctness and safety and representative users for usefulness, with blinded identity, randomised order, abstention permitted, stratified double-labelling that oversamples disagreement, and per-dimension κ/α with uncertainty [161][171]. Online, randomise at user or thread level and compare completion, correction, escalation, abandonment, delayed outcome, latency and cost; thumbs are weak preference data absent exposure and selection-bias analysis. Attach an **`eval_receipt`** to every number (§19) [143][150].

### 12.3 Tracing [high on the convention, medium on tooling]

OpenTelemetry's GenAI conventions are **Development** status in a dedicated repository, defining `invoke_agent`, `invoke_workflow`, `chat` and `execute_tool` with token attributes and **opt-in** content — pin a schema revision and expect migration [146]. Shape the tree `invoke_workflow` → `invoke_agent` → `plan` / `chat` / `retrieval` / `execute_tool`, recording stable ids, agent/prompt/tool-schema versions, requested **and returned** model, experiment arm, error type, retries, fan-out and depth, stop reason, token classes, latencies, budget reserved against actual, and artifact hashes; keep content allowlisted, redacted and sampled, metadata-only by default, or the trace store becomes a sensitive-data replica [146]. Platforms add trajectory matching and judges [139], immutable experiments with CI and asynchronous production scoring [172], self-hostable traces with annotation queues [173], span-level evaluation and replay [174], versioned prompts with scorers reused for monitoring [175], and OTel-aligned exports from enterprise runtimes [226]. Choose on residency, OTel portability, evaluator reproducibility and retention: **raw OTLP export does not guarantee evaluator or dataset portability**.

---

## 13. Training-time against inference-time architecture

**The framing and its limit. [medium]** The canonical argument is that search and learning scale arbitrarily with computation while built-in human knowledge "plateaus and even inhibits further progress" [140]. That is an argument about what to build **into the model**. It does not reach a scaffold whose purpose is to be independent of the model: no amount of learning makes a generator an independent witness to its own output (§10, carry-forward B) [112][113], and no capability makes a grader inside the agent's writable filesystem trustworthy [124][125].

**What is moving. [medium, survey]** Agentic RL reframes the problem from single-step MDPs to temporally extended POMDPs, converting planning, tool use, memory and self-improvement "from static, heuristic modules into adaptive, robust agentic behavior" [141]. Verifiable rewards mark the honest boundary: automatic reward exists wherever correctness is programmatically checkable, nothing equivalent exists for most agentic workflows, and long-horizon credit assignment remains open [141]. Self-correction is the one scaffold problem measurably softened by training — SFT on offline correction traces is "often insufficient" (+1.8% against −11.2% for the base model), while two-stage on-policy RL with a correction reward bonus reached +4.4% [114]. **A builder who cannot train cannot buy it.**

**The absorption evidence is one natural experiment. [low-medium]** One vendor's two posts a quarter apart [4][120][122][123]:

| Scaffold | Late 2025 | Early 2026 | Verdict |
| --- | --- | --- | --- |
| Context resets between sessions | Essential, against "context anxiety" | **Dropped** — the newer model "largely removed that behavior on its own" | Absorbed |
| "Test end-to-end as a user would" | Prompt instruction | An evaluator role driving browser automation | Enduring |
| Default-FAIL ledger | Introduced | Elaborated as per-sprint contracts | Enduring |
| Separate evaluator context | Not yet | A per-turn evaluator and a no-write subagent | Enduring, moving into the product |

The pattern — **scaffolds compensating for a model deficiency get absorbed; scaffolds encoding a trust boundary, a budget or an external ground-truth signal do not** — rests on that single data point: a hypothesis with a named mechanism, not a law. Its strong form ("the less you build, the more it works") is argued by one framework vendor from an experience report that still keeps a completion tool and a retry layer [142]. The inference-time counterpart is visible already: adaptive reasoning effort is now a model-side control that used to be scaffold policy [5][9]. **Operational rule [medium]:** version harness assumptions against model versions and re-run the ablation at each upgrade; grader isolation, hard budgets and delegated-token scope are the assumptions least likely to become obsolete.

---

## 14. Reference architectures and framework selection

Three designs, cheapest first. Adopt the smallest that supplies a **demonstrated** missing property; all bounds are §17's.

### 14.1 Design A — minimal bounded loop

One typed loop with explicit states (§3); strict schema tools with bounded results (§7); an append-only event store keyed by `run_id` with monotonic sequence numbers, separate from conversation storage; SSE offset resume over `Last-Event-ID`; approvals as durable rows; executable verification outside the agent's writable filesystem; version-pinned OTel spans [7][124][146][189][198][213]. The semantic stop is a final message **plus** a coded acceptance check [4][7].

| Fails first | Mitigation |
| --- | --- |
| Context exhaustion — half-implemented state at the cap, or premature completion | Compaction contract plus re-injected run ledger (§8) [4][79][82] |
| Unbounded loop — cost runaway with no protocol stop | Invocation, tool, token, USD and time caps as invariants [10][17][180] |
| Non-idempotent write retried — duplicate side effects | Callee-enforced keys (§11.2) [186][200] |
| Approval lost on deploy | Durable checkpoint plus server-issued resume token [188] |
| Grader in the workspace — green signal with nothing solved | Out-of-container grading [124][125] |

**Outgrown when** runs must survive process death, read-only breadth exceeds one window, or approvals wait hours.

### 14.2 Design B — orchestrator → workers → aggregator

A coordinator, N context-isolated read-only workers, **one** aggregation bottleneck, and a deterministic partition wherever a corpus must be *covered* rather than sampled, with writes single-threaded [24][30][31][224]. **Preconditions, not options:** measure the single-agent baseline, test decomposability rather than difficulty, require a matched-budget A/B — above roughly a 45% baseline added agents predict zero-to-negative gains, and at matched thinking-token budgets single-agent was best or indistinguishable at every budget above the lowest [33][54]. Fan-out, depth and warning thresholds come from shipped precedent [24][40][41][43].

| Fails first | Mitigation |
| --- | --- |
| Error amplification — one wrong worker output reaches the answer | Centralised aggregation: 17.2× independent against 4.4× centralised [54] |
| Under-specified delegation — duplicated or off-target work | The prompt is the worker's only channel: pass paths, errors, constraints, decisions [42][43] |
| Sequential interdependence — 39–70% degradation under every variant | Do not fan out; use Design A [54] |
| Synchronous lead — the system waits on one worker | Asynchronous workers with per-worker budgets [43] |
| Aggregator failure — the run degrades quietly while the turn ends `done` | Exception-level logging, labelled partial (§11.8) [41] |
| Inherited permissions — subagents run with the parent's bypass mode | Per-subagent least privilege [197] |

**Cost:** no apples-to-apples multiplier exists; "~15× tokens" is against *chat* on one research workload [24].

### 14.3 Design C — durable long-horizon runner

Short versioned task-scoped workflows; model and tool calls as retryable activities idempotent **at the callee**; durable waits for approvals; claim-check payloads; horizontal workers; session-pinned bundle versions [182][183][186][188][208][223]. Payload, history and session caps are hard platform limits, one shipped cloud coding agent allowing a single repository, branch and pull request in an ephemeral environment [183][184][211][212].

| Fails first | Mitigation |
| --- | --- |
| Determinism violation — a code change breaks replay of in-flight runs | Workflow versioning; framework types behind adapters [183] |
| At-least-once double execution after worker loss | Keys at the callee, atomic token-plus-mutation commit [186][200] |
| History growth — the engine terminates the run | Short workflows, claim-check codec [182][183][184] |
| Rollback mid-run — later steps run on a version they did not start on | Session pinning plus drain [208] |
| Poison-pill run — infinite retry of a deterministic failure | Per-activity and per-run retry bounds, then quarantine (**synthesis inference [low]**) |

### 14.4 Framework selection

| Option | Owns | Churn and risk | Choose when |
| --- | --- | --- | --- |
| No framework — direct loop | Nothing; maximum visibility, minimum dependencies [235] | None inherited | The loop is small and hidden control flow is unacceptable |
| OpenAI Agents SDK | Runner loop, sessions, streaming, guardrails, resumable approvals, traces, handoffs [10][190][218] | A managed visual builder wound down, shutdown 2026-11-30 [225] | Loop ergonomics without a runtime commitment |
| LangChain 1.x + LangGraph | Middleware-wrapped loop on a graph runtime: persistence, durable execution, streaming, indefinite `interrupt()` [44][188][221] | Legacy chains moved to a classic package; the prebuilt ReAct entry point replaced at v1 [221] | Explicit branching, checkpoints and resumable approvals dominate |
| Microsoft Agent Framework | Agent abstractions, typed graph workflows, session state, middleware, telemetry [38][39][219] | Highest sampled migration risk: event-driven rewrite then successor; an independent fork ships its own harness [228][229] | Already in that stack, wanting graph checkpoints plus telemetry |
| CrewAI | Flow-first branches, loops, state and persistence around role-based crews [230] | Role vocabulary over-models simple work | Role decomposition genuinely matches the domain |
| smolagents | Minimal multi-step ReAct with JSON or generated-Python actions [18][231] | Low lock-in; pin the version | You want the loop as a readable dependency |
| Pydantic AI | Typed agents and outputs over an internal graph; node and tool event streams; tool approval [232] | Python and type-model coupling | Type safety and streaming events outrank durability |
| DSPy | Declarative modules plus optimisers tuning prompts against a metric [136][233] | Optimisation is the differentiator, not runtime | You have a metric and want it optimised, not hand-tuned |
| Mastra | Observational memory: background observers replace raw history with append-only observations [234] | Couples memory to its own storage | Context compression is the binding constraint |
| Temporal (custom build) | Deterministic orchestration, retryable activities, crash recovery, long waits [183][186][223] | Replay determinism constrains code; real operational commitment | Work must survive crashes, deploys and multi-hour waits |
| Managed platforms | Isolated runtime, memory, identity, gateway, OTel observability [220][226][227] | Platform coupling; managed surfaces churn [225] | Managed isolation, identity and governance justify coupling |

**Build against adopt [medium, normative].** Buy the hardest **missing lifecycle property**, not ergonomics: loop boilerplate → thin SDK; explicit state, branching and resumable approvals → graph framework; survival across process death → durable engine; managed isolation, identity and governance → platform. Keep product-owned message, tool, checkpoint, trace and approval schemas behind adapters, because 2025–2026 migrations make adapter maintenance the cheaper cost [221][225][228]. Two symmetrical errors: buying a platform for a tool loop, and running an in-memory loop for multi-hour approvals [188][213].

---

## 15. Anti-pattern catalogue

Documented or measured failures, not style preferences.

| Surface | Anti-pattern | Why it fails | Prefer |
| --- | --- | --- | --- |
| Loop | Prompt-only "keep going", no coded cap | One SDK leaves `maxTurns` undefined; another warns omission loops indefinitely [6][10][17] | Coded invocation, tool, token, time and USD caps |
| Loop | Final text read as success | It is a protocol stop; agents declare victory before completion [4][7] | Separate coded acceptance |
| Loop | Replaying only visible messages | Drops reasoning, call and phase items: re-derivation, lost cache, invalid continuation [7][8][9] | Persist full continuation state |
| Loop | Conflating steer, queue, interrupt, disconnect | Turn-id races, lost instructions, duplicate execution, wrong post-compaction order [12][13][14] | Four explicit transitions with a target turn |
| Compute | Fixed maximum thinking; reflection after every step | Overthinking flips answers and postpones action; per-step reflection moved 63.03 → 55.15 against best-of-N [5][19][22][27] | Adaptive effort; refine on failure, contradiction or stall |
| Compute | Best-of-N without an evaluated selector | `pass@K` rises while self-choice saturates or worsens [20][21] | Verifier rank-and-select; measure diversity first |
| Multi-agent | Fan-out by default | Mean improvement 0.0%, 95% CI −58.7% to +77.2%; interdependent work degrades 39–70% [54] | Baseline, decomposability test, matched A/B |
| Multi-agent | Workers with no aggregation bottleneck | 17.2× against 4.4× error amplification [54] | One aggregator |
| Multi-agent | Peers editing the same files concurrently | Unsupported by anything retrieved; typed transactional writes are a prototype [40][51] | Ownership partition or single-threaded reduce |
| Multi-agent | Standardising the wire to fix coordination | Inter-agent failure occurs inside one framework's own natural-language channel [32] | Fix delegation payloads and verification |
| Tools | API mirrors with unbounded results | Response length 10K → 80K tokens costs 7–91% answer retrieval [71] | Workflow tools; bound results by construction |
| Tools | Assuming MCP sessions; trusting tool hints | Stateless HTTP removed sessions; annotations are explicitly not faithful [57][58] | Explicit handles; callee-enforced dedupe |
| Tools | Progressive disclosure as the fix for all degradation | It addresses catalog size only [71] | Treat the three channels separately |
| Memory | One undifferentiated transcript called "memory" | Logs, run state, plans and user facts differ in scope, authority, deletion [91] | Typed plane keyed by tenant, user, project, agent, class |
| Memory | Tiny frequent compactions; whole-playbook rewrites | Prefix rewrites invalidate the cache; rewrites cause brevity bias and context collapse [79][80][109] | Batch removals; append or refine deltas |
| Memory | Source classification as a write gate | Poisoning succeeds through query-only interaction [105][107] | Namespace authorization plus content and policy checks |
| Verification | "Check your work carefully" to the generator | Feedback generation is the bottleneck; accuracy drops once the oracle stop signal is removed [112][113] | Any external signal: test, compiler, tool, observation |
| Verification | Grader inside the agent's writable workspace | A 10-line hook resolved 500/500 and 731/731 instances, zero issues solved [124][125] | Out-of-container, read-only grading |
| Verification | Majority vote over free-form output | Self-consistency needs a unique closed-form answer [118] | Rank-and-select; weak-verifier aggregation [129] |
| Verification | Prose plans; replanning on every error | Nothing downstream can check prose; reflexive replanning thrashes [122][137] | Default-FAIL ledger; bounded escalation ladder |
| Verification | Gating on stated confidence, or gating everything | Best paired abstention accuracy 59.5%, 13 of 17 below 50%; universal gates train the approve reflex [131][132] | External checks; gates at the point of no return |
| Ops | Durable engine treated as exactly-once | At-least-once execution; a timed-out write has an unknown outcome [186][200] | Callee keys plus an ambiguous-outcome path |
| Ops | Allowlist as filter; assumed firewall coverage | An allowed host carried the exfiltration; one firewall covers only Bash-tool processes [64][205] | Capability-scoped brokering proxy |
| Ops | Low override rate read as high quality | Absence of correction is not correctness at ~93% approval [64][181] | A floor on detected error plus sampled review |
| Ops | Canary without sticky routing | Threads flip version mid-run [208] | Session pinning plus drain |
| Eval | Bare percentages; per-benchmark scaffold tuning | 23.8-point harness spread; one scaffold helped one model and hurt another [143][165] | `eval_receipt` on every number |
| Eval | `pass@k` implying single-attempt reliability | One model fell from ~61% `pass^1` to under 25% `pass^8` [119] | Report `pass^1`, `pass^k`, variance |
| Eval | One golden path; outcome-only grading | Several safe paths usually exist and side effects matter [139][155] | Trajectory envelope plus state assertions |

---

## 16. Open problems and what to watch next

**Open, with what would settle each.** The front matter's four gaps stand: *matched-compute multi-agent in the retrieval-unbounded regime*, settled by an A/B holding tokens, tools and wall-clock constant on a retrieval-heavy workload [24][33][54]; a *tool-count threshold for catalog retrieval*, where curves are continuous and model-dependent, so the answer is a local measurement [71][72]; *product-level reliability and cost distributions*, undisclosed for essentially every shipped agent [209][210][211][214]; and *benchmarks for multi-day interrupted work, maintainability, calibrated clarification, collaboration quality and graceful recovery*, which do not exist — today's "long-horizon" suites are bounded simulations or hours-long workflows [131][145][166][167]. Two more: *how much a judgement SLI overstates quality*, needing override rate paired against sampled ground truth under measured approval fatigue [64][181]; and *how much the next model absorbs*, where the evidence is one documented absorption at one vendor [4][120].

**Watch list.** MCP revision cadence and the stateless-HTTP migration, since `2026-07-28` removed sessions and SSE resumability [57]; whether A2A yields retrievable production topologies rather than membership counts [36][37]; republication of corrected benchmark splits with systems re-run [149][150][155]; OpenTelemetry GenAI conventions leaving Development [146]; the AI Act clock [178]; NIST's agent overlays reaching a draft [201]; long-duration autonomy claims shipping without task sets, harnesses or denominators [28]; memory-security benchmarks maturing into release gates [104][105][106]; and whether separate evaluators and adaptive effort become model features rather than scaffolds [5][123].

**Deferred issues.** This round closed with none outstanding — the patch round applied the memory, verification and operations corrections, and the multi-agent workstream cleared with zero edits (see `deferred-issues.md` beside this document). The 2026-07-14 pass [236] stands superseded wherever §§1–10 correct it; its six corrected positions are named in the front matter.

---

## 17. Recommended defaults — bounds and limits

**Starting values, not targets.** Provenance classes: *shipped precedent* (a vendor default), *practitioner set* (one worked configuration), *engine limit* (a hard platform constraint), *derived* (calibrate from your own p95). Every bound names its counted event (§3.1) and is enforced as a runtime invariant, never a prompt instruction.

| Bound | Starting value | Provenance | Move it when |
| --- | --- | --- | --- |
| Model invocations per run | 20–30 | Derived from defaults of 10 and 20 steps [10][11][18] | Tool-heavy work needs more; keep an absolute ceiling |
| Tool calls per run | 100, or 30 "steps" | Practitioner set [180] | Only with a cost cap in place |
| Wall clock | 10 min interactive, 60 min asynchronous | Practitioner set plus a 59-minute session cap [180][211] | Longer needs durable execution (§14.3) |
| Tokens per run | 50k, else p95 × 2 | Practitioner set [180] | Recalibrate per task class |
| USD per run | $0.50, plus a per-tenant daily cap | Practitioner set [180] | Raise for verified high-value tasks only |
| Consecutive failures | 3 in 5 attempts, then breaker | Practitioner set [180] | Tighten where attempts have side effects |
| Loop detection | Hash of recent tool calls | Practitioner set [180] | Always on — cheap loops evade token caps |
| Fan-out | 3–5 typical, >10 for complex queries; hard 16 concurrent, 1,000 per run | Shipped precedent [24][40][41] | Only above a measured baseline gain [54] |
| Subagent depth | 3 (1 disables nesting) | Shipped precedent [43] | Reduce to 1 until per-level budgets exist |
| Fan-out warnings | 25 scheduled agents or 1.5M projected tokens | Shipped precedent [41] | Lower for interactive products |
| Compaction trigger | ~150k input tokens, minimum 50k | Shipped precedent [79] | Earlier only if a new cache write amortises [80] |
| Cache TTL | 1 hour for approval-bearing runs | Shipped precedent [192][195] | Shorter when prefixes churn |
| Retry policy | Capped exponential backoff, full jitter, one layer, idempotent only | Foundational [203] | Never add a second retry layer |
| Approval expiry | 24 h with explicit expiry action and audit record | **No documented default** — derived [188][190] | Shorten where the argument hash goes stale fast |
| Computer-use step cap | 100–200 | Shipped precedent, and why vendor scores are incomparable [216][217][222] | Raise only with a cost cap and partial credit |
| Durable payload / history | ≤256 KB payloads (2 MB errors); histories far below 51,200 events or 50 MB | Engine limit [183][184] | Claim-check codec instead of raising |
| SSE replay window | Sized to fan-out volume and retention budget | Derived [189][199] | Grows with worker count, not users |
| Eval gate | n≈20 for large-effect iteration; nightly multi-seed with CIs for release | Vendor methodology [121] | Never gate a release on n≈20 |

---

## 18. Production readiness checklist

Each item is testable; the section reference is where its evidence lives.

**Loop and bounds.** Typed states with one writer (§3); every counter names its event and outcomes include `partial_limit` and `awaiting_input` (§3.1); invocation, tool, token, USD, time, fan-out and depth caps as code invariants (§17); protocol stop separate from coded acceptance (§3); reasoning, call and result items replayed in provider order (§3.2); steer, queue, interrupt and disconnect as four transitions (§3.3).

**State and memory.** Typed plane keyed by `(tenant, user, project, agent, memory_class)`; compaction preserves objective, constraints, decisions, open questions, todos, evidence and pointers, and batches removals; retrieval routed by query type; "forget" implemented as five operations; writes pass namespace authorization plus content and policy checks (§8, §11.6).

**Tools and environment.** Strict schema mode verified as actually applied; results bounded by construction; deterministic tool order with deferred schemas outside the cached prefix; PKCE `S256`, RFC 8707 `resource`, exact redirect-URI matching, no token passthrough (§7); sandbox chosen as a threat model with credentials brokered from outside (§7, §11.5); callee-enforced idempotency on every write tool (§11.2).

**Verification.** Executable ground truth where it exists, grader outside any filesystem the agent can write (§10.1, §11.6); cross-family judge with position swapping and human recalibration for subjective criteria (§10.1); self-check never a gate (§10); success machine-readable as default-FAIL criteria with evidence and weighted partial credit (§10.3).

**Identity and security.** One narrowly scoped delegated token per run, `may_act` checked at the exchange, no user-credential reuse; resource servers authorize the current actor plus claims and scope, the `act` chain being audit evidence (§11.5); per-subagent least privilege, never inherited bypass (§11.4); controls labelled by mechanism class (§11.6); kill switch, per-task and global (§11.8).

**Streaming and HITL.** Monotonic sequence numbers with replay-from-offset above `Last-Event-ID`; disconnect, cancel and pause distinct, cancel idempotent (§11.3); durable checkpointer for pending approvals bound to `(run_id, step_id, tool_name, argument_hash, bundle_version)` with expiry and audit (§11.4); gates before the first irreversible action, showing the artifact (§10.4).

**Cost, degrade and SLOs.** Cache hit rate as an SLI with a stable prefix; full-jitter retry at one layer with 429 and 529 handled differently; per-tenant queues, budgets and cache namespace (§11.7). Plural trip conditions with structured stop logs; labelled partials and completed work never discarded; judgement SLI read as a floor beside sampled review (§11.8); ambiguous outcomes escalate rather than retry (§11.2).

**Evaluation, rollout and governance.** Private versioned suite with frozen, canary and regression sets, scoring outcome, process, economics and reliability separately; `eval_receipt` on every reported number; human double-labelling with κ/α and judge TPR/TNR by slice (§12.2); version-pinned OTel spans with content redacted and sampled (§12.3). Immutable versioned bundle referenced by id; offline → shadow with intercepted writes → sticky canary → ramp → automatic rollback, session-pinned with drain; residency treated as two promises; high-risk scope assessed rather than assumed (§10.4, §11.9).

---

## 19. Glossary

**Harness.** The whole control envelope around the model — prompt layers, tool schemas, permissions, context and stop policy. Benchmarks score harness-plus-model (§3, §12).

**Protocol stop against acceptance.** A valid final message ends the model-directed loop; acceptance is a separate coded decision (§3).

**Context rot.** Non-uniform degradation as input length grows, observed *despite* perfect evidence recitation (§8).

**Absorption.** A scaffold becoming unnecessary because a model improved — observed once, for context resets (§13).

**Default-FAIL ledger.** A machine-checkable plan artifact whose criteria start false and flip only with evidence, through a restricted edit surface (§9, §10.3).

**`pass@k` against `pass^k`.** At least one success in k attempts, against all k succeeding; they diverge at long horizons (§10.2).

**Grading trust boundary.** The grader does not run in a filesystem the agent can write to. Security, not hygiene (§10.1).

**Saturation threshold.** Above roughly a 45% single-agent baseline, added agents predict zero-to-negative gains — a calibration target, not a constant (§5).

**At-least-once execution, exactly-once observation.** The contract of journal-and-replay engines: activities may run more than once, history records one outcome (§11.1).

**Idempotency key at the callee.** A caller-supplied identifier committed atomically with the mutation by the service performing it (§11.2).

**`may_act` / `act`.** `may_act` is the authorization-server check at token exchange that an actor may act for a subject; `act` names the current actor in the issued token and is audit evidence, not an access-control input (§11.5).

**Capability grant against filter.** A hostname allowlist grants everything reachable behind a permitted host; only capability removal bounds behaviour (§11.6).

**Judgement SLI.** Override and correction rate as a label-free quality proxy: a floor on detected error, depressed by approval fatigue (§11.8).

**Shadow against canary.** Shadow mirrors traffic with writes intercepted; canary exposes real traffic behind pre-registered gates and needs session pinning (§11.9).

**`eval_receipt`.** The metadata making a number comparable: suite, split and revision, image, agent/prompt/tool/model versions, budgets, seeds, grader and judge versions, cost, uncertainty (§12.2).

---

## 20. Sources

**236 sources, all retrieved 2026-08-03.** Numbering is unified across the document: every `[n]` in §§1–19 resolves here, and every source is cited at least once. Grouping is by subject area, not citation order. Where a memo flagged a source as vendor-reported, undisclosed-harness, author-reported or holding a competing interest, that qualifier appears **at the claim** in the body; the type column carries its summary form.

### 20.1 Loop, harness and inference-time compute

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 1 | ReAct: Synergizing Reasoning and Acting in Language Models | Princeton / Google Research via arXiv · 6 Oct 2022 · paper · foundational origin of the loop | https://arxiv.org/abs/2210.03629 |
| 2 | Effective context engineering for AI agents | Anthropic · 29 Sep 2025 · engineering blog | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents |
| 3 | Writing effective tools for AI agents—using AI agents | Anthropic · 11 Sep 2025 · engineering blog | https://www.anthropic.com/engineering/writing-tools-for-agents |
| 4 | Effective harnesses for long-running agents | Anthropic · 26 Nov 2025 · engineering report | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| 5 | Introducing Claude Opus 4.6 | Anthropic · 5 Feb 2026 · product/technical announcement | https://www.anthropic.com/news/claude-opus-4-6 |
| 6 | TypeScript SDK reference | Anthropic · n.d. · current reference cites v2.1.219 · documentation | https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-typescript |
| 7 | Unrolling the Codex agent loop | OpenAI · 23 Jan 2026 · engineering blog | https://openai.com/index/unrolling-the-codex-agent-loop/ |
| 8 | Better performance from reasoning models using the Responses API | OpenAI · 11 May 2025 · cookbook · foundational reasoning-item implementation | https://developers.openai.com/cookbook/examples/responses_api/reasoning_items |
| 9 | Reasoning models | OpenAI · n.d. · current documentation · documentation | https://developers.openai.com/api/docs/guides/reasoning |
| 10 | Running agents | OpenAI Agents SDK · n.d. · current documentation · documentation | https://openai.github.io/openai-agents-python/running_agents/ |
| 11 | `src/agents/run_config.py` (`DEFAULT_MAX_TURNS = 10`) | OpenAI Agents SDK · n.d. · commit `7029ea8f` · source code | https://github.com/openai/openai-agents-python/blob/7029ea8f/src/agents/run_config.py |
| 12 | Codex App Server | OpenAI · n.d. · current documentation · protocol documentation | https://developers.openai.com/codex/app-server |
| 13 | feat(app-server): turn/steer API | OpenAI Codex · 5 Feb 2026 · merged source PR | https://github.com/openai/codex/pull/10821 |
| 14 | Defer steering until after sampling the model post-compaction | OpenAI Codex · 8 Apr 2026 · merged source PR | https://github.com/openai/codex/pull/17163 |
| 15 | Continually improving our agent harness | Cursor · 30 Apr 2026 · engineering blog | https://cursor.com/blog/continually-improving-agent-harness |
| 16 | Dynamic context discovery | Cursor · 6 Jan 2026 · engineering blog | https://cursor.com/blog/dynamic-context-discovery |
| 17 | Loop workflow — Agent Development Kit | Google · n.d. · current documentation · documentation | https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/ |
| 18 | Agents — smolagents reference | Hugging Face · n.d. · main / v1.26.0 visible · documentation/source reference | https://huggingface.co/docs/smolagents/main/en/reference/agents |
| 19 | Scaling Test-time Compute for LLM Agents | OPPO PersonalAI Lab via arXiv · 15 Jun 2025 · paper · foundational agent-specific scaling study | https://arxiv.org/abs/2506.12928 |
| 20 | Benchmark Test-Time Scaling of General LLM Agents | Carnegie Mellon / Meta via arXiv · 22 Feb 2026 · paper | https://arxiv.org/abs/2602.18998 |
| 21 | How Inference Compute Shapes Frontier LLM Evaluation | UK AI Security Institute via arXiv · 16 Jun 2026 · paper | https://arxiv.org/abs/2606.17930 |
| 22 | When More Thinking Hurts: Overthinking in LLM Test-Time Compute Scaling | Nanjing University / Baidu via arXiv · 12 Apr 2026 · paper | https://arxiv.org/abs/2604.10739 |
| 23 | Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters | UC Berkeley / Google DeepMind via arXiv · 7 Aug 2024 · paper · foundational compute-allocation result | https://arxiv.org/abs/2408.03314 |
| 24 | How we built our multi-agent research system | Anthropic · 13 Jun 2025 · engineering report · workload-specific token-use comparison | https://www.anthropic.com/engineering/multi-agent-research-system |
| 25 | SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks (v1) | BenchFlow-led consortium via arXiv · 13 Feb 2026 · paper · paired deterministic-verifier benchmark | https://arxiv.org/abs/2602.12670v1 |
| 26 | Don’t Overthink It: Inter-Rollout Action Agreement as a Free Adaptive-Compute Signal for LLM Agents | Stanford University via arXiv · 9 Apr 2026 · paper · TrACE adaptive-compute study | https://arxiv.org/abs/2604.08369 |
| 27 | The Danger of Overthinking: Examining the Reasoning-Action Dilemma in Agentic Tasks | UC Berkeley / ETH Zurich / UIUC / CMU via arXiv · 12 Feb 2025 · paper · foundational agentic-overthinking study | https://arxiv.org/abs/2502.08235 |
| 28 | Building more with GPT-5.1-Codex-Max | OpenAI · 2025-11-19 · product announcement (undisclosed harness) | https://openai.com/index/gpt-5-1-codex-max/ |

### 20.2 Multi-agent topologies and orchestration

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 29 | Don't Build Multi-Agents | Cognition · 2025-06 (undated · follow-up dates it 10 mo. before 2026-04-22) · Vendor eng. | https://cognition.ai/blog/dont-build-multi-agents |
| 30 | Multi-Agents: What's Actually Working | Cognition (Walden Yan) · 2026-04-22 · Vendor eng. | https://cognition.ai/blog/multi-agents-working |
| 31 | Agentic MapReduce | Cognition / Devin · 2026 (undated · cites a 2026 study) · Vendor eng. | https://devin.ai/blog/agentic-map-reduce |
| 32 | Why Do Multi-Agent LLM Systems Fail? — Cemri et al., **v3** | UC Berkeley et al. · v1 2025-03-17, v3 2025-10-26, arXiv:2503.13657v3 · Preprint | https://arxiv.org/abs/2503.13657v3 |
| 33 | Single-Agent LLMs Outperform Multi-Agent Systems… Equal Thinking Token Budgets — Tran & Kiela | Stanford · 2026-04, arXiv:2604.02460v1 · Preprint | https://arxiv.org/html/2604.02460v1 |
| 34 | The Cost of Consensus — Bertalanič & Fortuna | Jožef Stefan Inst. / ACM CAIS 2026 · 2026-05-22 · Peer-reviewed | https://arxiv.org/abs/2605.00914 |
| 35 | Mixture-of-Agents Enhances LLM Capabilities — Wang et al. | Duke / Together AI / UChicago / Stanford · 2024-06, arXiv:2406.04692 — *foundational: canonical MoA reference* · Preprint | https://arxiv.org/abs/2406.04692 |
| 36 | Announcing Version 1.0 | A2A Protocol project · 2026-04 · Spec announcement | https://a2a-protocol.org/latest/announcing-1.0/ |
| 37 | A2A Protocol Surpasses 150 Organizations… | Linux Foundation · 2026-04-09 · Press release (claims) | https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year |
| 38 | Microsoft Agent Framework Version 1.0 | Microsoft · 2026-04-08 (GA 2026-04-02 in text) · Vendor release | https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/ |
| 39 | Microsoft Agent Framework at BUILD 2026 | Microsoft · 2026-06-09 · Vendor release | https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/ |
| 40 | Orchestrate teams of Claude Code sessions | Anthropic · docs at v2.1.178–2.1.199 · Product docs | https://code.claude.com/docs/en/agent-teams.md |
| 41 | Orchestrate subagents at scale with dynamic workflows | Anthropic · docs at v2.1.154–2.1.203 · Product docs | https://code.claude.com/docs/en/workflows.md |
| 42 | Subagents (Claude Code) | Anthropic · undated docs · Product docs | https://code.claude.com/docs/en/sub-agents.md |
| 43 | Subagents (Claude Agent SDK) | Anthropic · docs at v2.1.217–2.1.219 · SDK docs | https://code.claude.com/docs/en/agent-sdk/subagents.md |
| 44 | What's new in LangGraph v1 | LangChain · undated docs (v1 line) · Framework docs | https://docs.langchain.com/oss/python/releases/langgraph-v1 |
| 45 | Deep Agents overview | LangChain · undated docs · Framework docs | https://docs.langchain.com/oss/python/deepagents/overview |
| 46 | Loop workflow (LoopAgent) | Google ADK · undated docs (Python v0.1.0+) · Framework docs | https://adk.dev/agents/workflow-agents/loop-agents/ |
| 47 | Multi-agent systems (`docs/agents/multi-agents.md`) | Google ADK · repo docs, rev 5331a07f · Framework docs | https://github.com/google/adk-docs/blob/5331a07f/docs/agents/multi-agents.md |
| 48 | Multi-agent workflow patterns (`docs/workflows/patterns.md`) | Google ADK · repo docs, main · Framework docs | https://github.com/google/adk-docs/blob/main/docs/workflows/patterns.md |
| 49 | A Survey of Agent Interoperability Protocols: MCP, ACP, A2A, ANP | (survey authors) · 2025-05, arXiv:2505.02279 · Survey preprint | https://arxiv.org/abs/2505.02279 |
| 50 | Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture | (authors) · 2025-07, arXiv:2507.01701v1 · Preprint | https://arxiv.org/abs/2507.01701v1 |
| 51 | PatchBoard: Schema-Grounded State Mutation… — Zhang, Shi & Wang | Xidian University · 2026-05, arXiv:2605.29313v1 · Preprint (research prototype, self-reported) | https://arxiv.org/html/2605.29313v1 |
| 52 | Magentic Marketplace: An Open-Source Environment for Studying Agentic Markets | Microsoft Research · 2025-10, arXiv:2510.25779 · Preprint + research blog | https://arxiv.org/abs/2510.25779 |
| 53 | Donating the Model Context Protocol and establishing the Agentic AI Foundation | Anthropic · 2025-12-09 · Vendor announcement | https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation |
| 54 | Capable language models can outgrow the benefits of collaboration — Kim, Gu, Park et al. | *Nature Machine Intelligence* 8:1157–1172 · published 2026-07-24 · Peer-reviewed | https://www.nature.com/articles/s42256-026-01268-y |
| 55 | When and Why Does Multi-Agent Debate Fail and Does It Really Underperform? (ColMAD) — Chen, Niu, Cheng, Han & Sugiyama | CUHK / RIKEN AIP / HKBU / U. Tokyo · v1 2025-10-23, v2 2026-07-14, arXiv:2510.20963v2 · Preprint | https://arxiv.org/html/2510.20963v2 |
| 56 | SILO-BENCH: A Scalable Environment for Evaluating Distributed Coordination in Multi-Agent LLM Systems — Zhang et al. | ACL 2026 (Long Papers), pp. 29379–29398 · 2026-07 · Peer-reviewed | https://aclanthology.org/2026.acl-long.1354/ |

### 20.3 Tools, MCP, environment and sandboxing

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 57 | Key Changes (specification changelog) | Model Context Protocol · 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/changelog |
| 58 | Schema Reference (`Tool`, `ToolAnnotations`) | Model Context Protocol · rev. 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/schema |
| 59 | Authorization Security Considerations | Model Context Protocol · rev. 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations |
| 60 | `modelcontextprotocol/registry` README | MCP community · preview 2025-09-08 · primary | https://github.com/modelcontextprotocol/registry |
| 61 | Introducing advanced tool use on the Claude Developer Platform | Anthropic · 2025-11-24 · vendor claims · harness undisclosed | https://www.anthropic.com/engineering/advanced-tool-use |
| 62 | Code execution with MCP | Anthropic · 2025-11-04 · vendor claims | https://www.anthropic.com/engineering/code-execution-with-mcp |
| 63 | Beyond permission prompts | Anthropic · 2025-10-20 · primary · 84% is internal usage | https://www.anthropic.com/engineering/claude-code-sandboxing |
| 64 | How we contain Claude across products | Anthropic · 2026-05-25 · primary | https://www.anthropic.com/engineering/how-we-contain-claude |
| 65 | Piloting Claude in Chrome | Anthropic · 2025-08-25 · primary · model version undisclosed | https://claude.com/blog/claude-for-chrome |
| 66 | Function calling | OpenAI · current documentation · primary | https://developers.openai.com/api/docs/guides/function-calling |
| 67 | Sandboxing AI agents, 100x faster | Cloudflare · 2026-03-24 · vendor claims | https://blog.cloudflare.com/dynamic-workers/ |
| 68 | E2B infra — `docs/ARCHITECTURE.md` | E2B · current | https://github.com/e2b-dev/infra/blob/main/docs/ARCHITECTURE.md |
| 69 | Executable Code Actions Elicit Better LLM Agents | Wang et al., arXiv 2402.01030 · Feb 2024 · foundational | https://arxiv.org/abs/2402.01030 |
| 70 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | Yang et al., arXiv 2405.15793 · May 2024 · foundational | https://arxiv.org/abs/2405.15793 |
| 71 | LongFuncEval: Measuring the effectiveness of long context models for function calling | Kate et al. (IBM Research), arXiv 2505.10570 · May 2025 · primary | https://arxiv.org/html/2505.10570 |
| 72 | How Many Tools Should an LLM Agent See? | Repantis et al. (Meta), arXiv 2605.24660 · May 2026 · primary | https://arxiv.org/abs/2605.24660 |
| 73 | Beyond Function Calling: Tool-Using Agents under Tool-Environment Unreliability | Tian et al., arXiv 2606.25819 · Jun 2026 · primary | https://arxiv.org/abs/2606.25819 |
| 74 | OSWorld 2.0 | XLANG Lab et al., arXiv 2606.29537 · Jun 2026 · primary | https://arxiv.org/abs/2606.29537 |
| 75 | OSWorld-Human | MLSys 2026 proceedings · 2026 · primary | https://proceedings.mlsys.org/paper_files/paper/2026/file/5edb57c05c81d04beb716ef1d542fe9e-Paper-Conference.pdf |
| 76 | SecureWebArena: A Holistic Security Evaluation Benchmark for LVLM-based Web Agents | Ying et al., Findings of ACL 2026, pp. 11986–11998 · primary | https://aclanthology.org/2026.findings-acl.582.pdf |
| 77 | Code Execution with MCP (replication; 2 query types, GPT-4.1, Bright Data disclosed as customer) | Sezer & Alper, AIMultiple · 2026-06-24 · secondary | https://aimultiple.com/code-execution-with-mcp |
| 78 | Record and Replay Testing for AI Agents | dreaming.press · 2026 · secondary | https://dreaming.press/posts/record-replay-testing-for-ai-agents.html |

### 20.4 Memory and context

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 79 | Compaction | Anthropic · n.d. · beta version `2026-01-12` · Live product docs | https://platform.claude.com/docs/en/build-with-claude/compaction |
| 80 | Context editing | Anthropic · n.d. · beta versions dated 2025 · Live product docs · cache behavior | https://platform.claude.com/docs/en/build-with-claude/context-editing |
| 81 | Memory tool | Anthropic · n.d. · Live product docs | https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool |
| 82 | Explore the context window | Anthropic, Claude Code · n.d. · behavior notes v2.1.198 · Live product docs | https://code.claude.com/docs/en/context-window |
| 83 | Why we built the Responses API | OpenAI Developers · n.d. · Primary vendor architecture post · claims not independent measurements | https://developers.openai.com/blog/responses-api |
| 84 | ChatGPT release notes — memory Sources and “Memory that stays more up to date” | OpenAI · 2026-05-05 · 2026-06-04 · Primary product release notes | https://help.openai.com/en/articles/6825453-chatgpt-release-notes |
| 85 | Context Rot: How Increasing Input Tokens Impacts LLM Performance | Chroma Research · 2025-07 · Technical report + reproducible toolkit · foundational, just outside recency window | https://research.trychroma.com/context-rot |
| 86 | NoLiMa: Long-Context Evaluation Beyond Literal Matching | PMLR / ICML · 2025-07-13–19 · Peer-reviewed benchmark · foundational | https://proceedings.mlr.press/v267/modarressi25a.html |
| 87 | Context Length Alone Hurts LLM Performance Despite Perfect Retrieval | Association for Computational Linguistics · 2025-11 · Peer-reviewed Findings paper | https://aclanthology.org/2025.findings-emnlp.1264/ |
| 88 | Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities | Google, Gemini Team · 2025-07 · Primary technical report · vendor-reported | https://doi.org/10.48550/arxiv.2507.06261 |
| 89 | Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory | Mem0 authors / ECAI · 2025-04 · ECAI 2025 · Paper from vendor authors · results treated as author claims | https://arxiv.org/abs/2504.19413 |
| 90 | Sleep-time Compute: Beyond Inference Scaling at Test-time | Letta & UC Berkeley authors / arXiv · 2025-04 · Research paper plus shipped Letta architecture | https://arxiv.org/abs/2504.13171 |
| 91 | Rethinking Memory Mechanisms of Foundation Agents in the Second Half: A Survey | Multi-institution authors / arXiv · 2026-02, v3 · Recent survey · taxonomy source | https://arxiv.org/html/2602.06052v3 |
| 92 | Memory as a Controlled Process: Learned Adaptive Memory Management for LLM Agents | UCLA, UW & Northwestern authors / arXiv · 2026-07-15 · Preprint · early learned-control evidence | https://arxiv.org/html/2607.13591v1 |
| 93 | Zep: A Temporal Knowledge Graph Architecture for Agent Memory | Zep AI authors / arXiv · 2025-01-20 · Vendor-authored preprint · temporal model | https://arxiv.org/html/2501.13956 |
| 94 | Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions | UC San Diego authors / ICLR · 2025-07 · ICLR 2026 · Peer-reviewed MemoryAgentBench | https://arxiv.org/abs/2507.05257 |
| 95 | Hidden in Memory: Sleeper Memory Poisoning in LLM Agents | SPAR, ELLIS/MPI, APTA & CISPA authors / arXiv · 2026-05-14 · Security preprint | https://arxiv.org/html/2605.15338 |
| 96 | Evaluating Very Long-Term Conversational Memory of LLM Agents | Association for Computational Linguistics · 2024-08 · Peer-reviewed LoCoMo · foundational benchmark | https://aclanthology.org/2024.acl-long.747/ |
| 97 | LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory | UCLA, Tencent AI Lab Seattle & UC San Diego authors / ICLR · 2024-10 · ICLR 2025 · Peer-reviewed benchmark · foundational | https://arxiv.org/abs/2410.10813 |
| 98 | Introducing Contextual Retrieval | Anthropic · 2024-09-19 · Vendor evaluation · only code subset public | https://www.anthropic.com/engineering/contextual-retrieval |
| 99 | Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach | Association for Computational Linguistics · 2024-11 · Peer-reviewed RAG/LC comparison · foundational | https://aclanthology.org/2024.emnlp-industry.66/ |
| 100 | Agentic-R: Learning to Retrieve for Agentic Search | Association for Computational Linguistics · 2026-07 · Peer-reviewed · narrow retriever-training evidence | https://aclanthology.org/2026.findings-acl.785/ |
| 101 | Long-term Memory in LLM Applications — Core Concepts | LangChain / LangMem · n.d. · Shipped framework docs · vendor guidance | https://langchain-ai.github.io/langmem/concepts/conceptual_guide/ |
| 102 | Memory FAQ | OpenAI · updated 2026-06-04 · Current UX · also documents legacy deletion distinction | https://help.openai.com/en/articles/8590148-memory-in-chatgpt-remembering-what-you-chat-about |
| 103 | Vendor-run audit of LoCoMo | Penfield Labs · 2026-04 · Reproducible vendor-run audit · Claude Opus 4.6 labels with human review · Penfield Labs has competing-benchmark interest | https://github.com/dial481/locomo-audit |
| 104 | MemSecBench: Tracking Agent Memory Poisoning from Persistence to Consequence and Repair | Multi-institution authors / arXiv · 2026-07-29 · Security benchmark preprint | https://arxiv.org/abs/2607.27080 |
| 105 | From Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning Attacks in LLM Agents | Multi-institution authors / arXiv · 2026-06-04 · MPBench security preprint | https://arxiv.org/abs/2606.04329 |
| 106 | MemLeak: Diagnosing Information Leaks in Multimodal Agent Memory | Independent authors / arXiv · 2026-06-30 · Deletion-leakage benchmark preprint | https://arxiv.org/abs/2606.29788 |
| 107 | Memory Injection Attacks on LLM Agents via Query-Only Interaction | NeurIPS · 2025 · Peer-reviewed MINJA | https://proceedings.neurips.cc/paper_files/paper/2025/hash/42a97bbd9844d2bf68596730af80bcdf-Abstract-Conference.html |
| 108 | AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases | NeurIPS · 2024 · Peer-reviewed foundational attack | https://proceedings.neurips.cc/paper_files/paper/2024/hash/eb113910e9c3f6242541c1652e30dfd6-Abstract-Conference.html |
| 109 | Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models | Stanford, SambaNova & collaborators / ICLR · 2025-10 · ICLR 2026 · Peer-reviewed ACE · author-reported results | https://arxiv.org/abs/2510.04618 |
| 110 | Context Engineering for AI Agents: Lessons from Building Manus | Manus · 2025-07-18 · Primary production engineering report | https://manus.im/en/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus |
| 111 | ATLAS: All-round Testing of Long-context Abilities across Scales | Multi-institution authors / arXiv · 2026-05-27 · Long-context benchmark preprint | https://arxiv.org/abs/2605.28079 |

### 20.5 Planning, verification and self-correction

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 112 | LLMs Cannot Self-Correct Reasoning Yet | Huang et al., ICLR 2024 via arXiv · 2023-10 · peer-reviewed paper (foundational) | https://arxiv.org/abs/2310.01798 |
| 113 | When Can LLMs Actually Correct Their Own Mistakes? | Kamoi et al., TACL via arXiv · 2024-06 · peer-reviewed field audit (foundational) | https://arxiv.org/html/2406.01297v3 |
| 114 | Training Language Models to Self-Correct via Reinforcement Learning (SCoRe) | Kumar et al., Google DeepMind, ICLR 2025 · 2024-09 · peer-reviewed paper | https://arxiv.org/pdf/2409.12917 |
| 115 | Self-Refine: Iterative Refinement with Self-Feedback | Madaan et al., NeurIPS 2023 · 2023-03 · peer-reviewed paper | https://arxiv.org/abs/2303.17651 |
| 116 | CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing | Gou et al., ICLR 2024 · 2023-05 · peer-reviewed paper | https://arxiv.org/pdf/2305.11738 |
| 117 | Let's Verify Step by Step | Lightman et al., OpenAI via arXiv · 2023-05 · paper (foundational) | https://arxiv.org/abs/2305.20050 |
| 118 | Self-Consistency Improves Chain of Thought Reasoning | Wang et al., Google Research via arXiv · 2022-03 · paper (foundational) | https://arxiv.org/abs/2203.11171 |
| 119 | τ-bench: A Benchmark for Tool-Agent-User Interaction | Yao et al., Sierra via arXiv · 2024-06 · paper (origin of `pass^k`) | https://arxiv.org/pdf/2406.12045 |
| 120 | Harness design for long-running application development | Anthropic · 2026-03-24 · engineering report (n=1 vendor harness) | https://www.anthropic.com/engineering/harness-design-long-running-apps |
| 121 | Demystifying evals for AI agents | Anthropic · 2026-01-09 · vendor eval methodology | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents |
| 122 | `anthropics/cwc-long-running-agents` (default-FAIL contract, no-write evaluator) | Anthropic, `anthropics/cwc-long-running-agents` · 2026 · vendor repo README | https://raw.githubusercontent.com/anthropics/cwc-long-running-agents/main/README.md |
| 123 | Claude Code `/goal` (per-turn separate-model evaluator) | Anthropic, Claude Code · 2026 · product documentation | https://code.claude.com/docs/en/goal |
| 124 | How we broke top AI agent benchmarks | UC Berkeley RDI · 2026-04 · independent audit blog | https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/ |
| 125 | BenchJack: Auditing AI Agent Benchmarks | BenchJack authors via arXiv · 2026-05 · preprint audit | https://arxiv.org/html/2605.12673 |
| 126 | Judging the Judges: A Systematic Study of Position Bias | Shi et al., IJCNLP 2025 · 2025 · peer-reviewed | https://aclanthology.org/2025.ijcnlp-long.18.pdf |
| 127 | Play Favorites: Measuring Self-Bias in LLM-as-a-Judge | arXiv · 2025-08 · preprint (self- and family-bias) | https://arxiv.org/pdf/2508.06709 |
| 128 | Are LLM Evaluators Really Narcissists? | arXiv · 2026-01 · preprint (self-preference confound; 37,448 queries) | https://arxiv.org/pdf/2601.22548 |
| 129 | Weaver: Closing the Generation-Verification Gap | Hazy Research, Stanford · 2025-06-18 · research blog (authors on own work) | https://hazyresearch.stanford.edu/blog/2025-06-18-weaver |
| 130 | Beyond pass@1: Reliability Science for Long-Horizon Agents | arXiv · 2026-03 · preprint | https://arxiv.org/abs/2603.29231 |
| 131 | AgentAbstain: Do LLM Agents Know When Not to Act? | arXiv · 2026-07 · preprint | https://arxiv.org/html/2607.10059v1 |
| 132 | Are LLM Decisions Faithful to Verbal Confidence? (RiskEval) | arXiv · 2026-01 · preprint | https://arxiv.org/pdf/2601.07767 |
| 133 | Reinforcement fine-tuning use cases | OpenAI · 2026 · vendor documentation | https://developers.openai.com/api/docs/guides/rft-use-cases |
| 134 | Reinforcement fine-tuning | OpenAI · 2026 · vendor documentation | https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning |
| 135 | A Survey of Process Reward Models | ACL 2026 · 2026 · peer-reviewed survey | https://aclanthology.org/2026.acl-long.163.pdf |
| 136 | GEPA plus DSPy GEPA documentation (feedback-shaped metric) | Agrawal et al. plus DSPy docs · 2025-07 / 2026 · paper plus framework docs | https://dspy.ai/api/optimizers/GEPA/overview/ |
| 137 | Self-Healing Agentic Orchestrators | arXiv · 2026-06 · preprint | https://arxiv.org/html/2606.01416v1 |
| 138 | EU AI Act, Article 14 — Human Oversight | EU · 2024-06-13, Chapter III applicable 2026-08-02 · primary regulation | https://artificialintelligenceact.eu/article/14/ |
| 139 | Trajectory evaluations (`agentevals`) | LangChain · 2026 · framework documentation | https://docs.langchain.com/langsmith/trajectory-evals |
| 140 | The Bitter Lesson | Sutton · 2019-03-13 · essay (foundational framing) | http://www.incompleteideas.net/IncIdeas/BitterLesson.html |
| 141 | The Landscape of Agentic Reinforcement Learning for LLMs | Zhang et al. via arXiv · 2025-09 (v5) · survey preprint | https://arxiv.org/html/2509.02547v5 |
| 142 | The Bitter Lesson of Agent Frameworks | Zunic, Browser Use · 2026-01-16 · vendor claims | https://browser-use.com/posts/bitter-lesson-agent-frameworks |

### 20.6 Evaluation, benchmarks and observability

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 143 | Harness-Bench | Harness-Bench authors via arXiv · 2026-05-27 · preprint; 106 tasks, eight backends | https://arxiv.org/html/2605.27922 |
| 144 | OSWorld 2.0 official site | XLANG Lab et al. · 2026-06 · official benchmark site | https://osworld-v2.xlang.ai/ |
| 145 | METR — Time Horizon 1.1 | METR · 2026-01-29 · research report | https://metr.org/blog/2026-1-29-time-horizon-1-1/ |
| 146 | OpenTelemetry — GenAI span semantic conventions | OpenTelemetry · accessed 2026-08-03 · specification, Development status | https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md |
| 147 | SWE-bench official leaderboards | SWE-bench team · live, accessed 2026-08-03 · leaderboard | https://www.swebench.com/ |
| 148 | SWE-bench Pro official page | Scale AI · 2025, live · benchmark harness and results | https://scaleapi.github.io/SWE-bench_Pro-os/ |
| 149 | Separating signal from noise in coding evaluations | OpenAI · 2026-07-08 · vendor audit | https://openai.com/index/separating-signal-from-noise-coding-evaluations/ |
| 150 | Terminal-Bench 2.1 | Terminal-Bench team · 2026-05-06 · benchmark release notes | https://tbench.ai/news/terminal-bench-2-1 |
| 151 | Aider polyglot leaderboard | Aider · live · leaderboard | https://aider.chat/docs/leaderboards/ |
| 152 | SWE-Lancer | OpenAI · 2025-02-18 · benchmark release | https://openai.com/index/swe-lancer/ |
| 153 | Commit0 | Commit0 authors, ICLR 2025 · benchmark site (foundational) | https://commit-0.github.io/ |
| 154 | GAIA2 / ARE | Meta and Hugging Face, ICLR 2026 · peer-reviewed benchmark | https://arxiv.org/abs/2602.11964 |
| 155 | Agentic Benchmark Checklist (ABC) | Zhu et al., NeurIPS 2025 · peer-reviewed independent audit | https://arxiv.org/html/2507.02825v5 |
| 156 | τ²-bench | Sierra via arXiv · 2025-06 · paper (dual control, `pass^k`) | https://arxiv.org/abs/2506.07982 |
| 157 | Berkeley Function Calling Leaderboard v4 | UC Berkeley · updated 2026-04-12 · leaderboard | https://gorilla.cs.berkeley.edu/leaderboard |
| 158 | MCP-Universe | Salesforce · 2025-08 · benchmark documentation | https://mcp-universe.github.io/usage.html |
| 159 | BrowseComp | OpenAI · 2025-04 · benchmark release | https://openai.com/index/browsecomp |
| 160 | AndroidWorld | Google DeepMind, ICLR 2025 · benchmark site (foundational) | https://google-research.github.io/android_world/ |
| 161 | AgentProcessBench | arXiv · 2026-03 · preprint (human process annotations) | https://arxiv.org/html/2603.14465v2 |
| 162 | DeepResearch Bench | benchmark authors · 2025-06 · live benchmark site with hosted evaluator | https://deepresearch-bench.github.io/ |
| 163 | MLE-bench repository and leaderboard | OpenAI · leaderboard frozen 2026-04-24 · benchmark repo | https://github.com/openai/mle-bench |
| 164 | RE-Bench report | METR · 2024-11 · research report (foundational, human baseline) | https://metr.org/blog/2024-11-22-evaluating-r-d-capabilities-of-llms/ |
| 165 | PaperBench repository and leaderboard | OpenAI · 2025-04 · benchmark repo | https://github.com/openai/frontier-evals/tree/main/project/paperbench |
| 166 | GDPval | OpenAI · 2025-10 · vendor benchmark | https://openai.com/index/gdpval/ |
| 167 | Vending-Bench 2 | Andon Labs · 2025-11, live · benchmark leaderboard | https://andonlabs.com/evals/vending-bench-2 |
| 168 | AgentHarm | UK AISI et al., ICLR 2025 · peer-reviewed benchmark | https://proceedings.iclr.cc/paper_files/paper/2025/hash/c493d23af93118975cdbc32cbe7323f5-Abstract-Conference.html |
| 169 | AgentDojo | ETH Zurich and Invariant, NeurIPS 2024 · peer-reviewed benchmark, live | https://agentdojo.spylab.ai/ |
| 170 | Cybench | Stanford, ICLR 2025 · peer-reviewed benchmark, live | https://cybench.github.io/ |
| 171 | Evaluation best practices | OpenAI · accessed 2026-08-03 · vendor methodology | https://developers.openai.com/api/docs/guides/evaluation-best-practices |
| 172 | Braintrust evaluation documentation | Braintrust · live · vendor docs and claims | https://www.braintrust.dev/docs/evaluate |
| 173 | Langfuse documentation | Langfuse · live · vendor docs and claims | https://langfuse.com/docs |
| 174 | Arize Phoenix documentation | Arize · live · vendor docs and claims | https://arize.com/docs/phoenix |
| 175 | W&B Weave documentation | Weights & Biases · live · vendor docs and claims | https://docs.wandb.ai/weave/concepts/what-is-weave |

### 20.7 Production operations, security, identity and governance

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 176 | On-Behalf-Of User Authorization for AI Agents, draft-02 | IETF 2025-08-26, expired 2026-02-27 | https://datatracker.ietf.org/doc/html/draft-oauth-ai-agents-on-behalf-of-user-02 |
| 177 | Article 14, human oversight | AI Act Service Desk · legislative | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 |
| 178 | AI Act timeline and AI Omnibus | European Commission 2026-08-03 · legislative | https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai |
| 179 | RFC 8693 OAuth 2.0 Token Exchange (`act`, `may_act`, `actor_token`) | IETF · Proposed Standard | https://datatracker.ietf.org/doc/html/rfc8693 |
| 180 | Emergency stop design for AI agents | Unimon 2026 · practitioner | https://unimon.co.th/en/blog/ai-agent-circuit-breaker |
| 181 | SRE for AI agent systems | Zylos 2026-03 · secondary | https://zylos.ai/research/2026-03-22-sre-ai-agent-systems-observability-incident-response/ |
| 182 | Lessons building cloud agents | Cursor · 2026 · vendor self-report, n=1 | https://cursor.com/blog/cloud-agent-lessons |
| 183 | Events and Event History | Temporal · live docs · primary | https://docs.temporal.io/workflow-execution/event |
| 184 | Self-hosted defaults and limits | Temporal · live docs · primary | https://docs.temporal.io/self-hosted-guide/defaults |
| 185 | Durable execution with fibers | Cloudflare · live docs · primary | https://developers.cloudflare.com/agents/runtime/execution/durable-execution/ |
| 186 | Activity Definition (idempotency, at-least-once, retry policy) | Temporal · live docs · primary | https://docs.temporal.io/activity-definition |
| 187 | Temporal vs Inngest vs Restate | Particula · 2026 · secondary comparison | https://particula.tech/blog/durable-execution-ai-agents-temporal-inngest-restate |
| 188 | Interrupts | LangGraph · live docs · framework documentation | https://docs.langchain.com/oss/python/langgraph/interrupts |
| 189 | Background mode | OpenAI · live docs · primary | https://developers.openai.com/api/docs/guides/background |
| 190 | Guardrails and human review | OpenAI · live docs · primary | https://developers.openai.com/api/docs/guides/agents/guardrails-approvals |
| 191 | A practical guide to building agents | OpenAI · 2025 · vendor guidance (PDF) | https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf |
| 192 | Prompt caching | Anthropic · live docs · primary | https://platform.claude.com/docs/en/build-with-claude/prompt-caching |
| 193 | Rate limits | Anthropic · live docs · primary | https://platform.claude.com/docs/en/api/rate-limits |
| 194 | API errors | Anthropic · live docs · primary | https://platform.claude.com/docs/en/api/errors |
| 195 | Prompt Caching 201 | OpenAI Cookbook · 2026 · customer self-report | https://developers.openai.com/cookbook/examples/prompt_caching_201 |
| 196 | Data controls and residency | OpenAI · live docs · primary | https://developers.openai.com/api/docs/guides/your-data |
| 197 | Configure permissions | Claude Agent SDK · live docs · SDK documentation | https://code.claude.com/docs/en/agent-sdk/permissions |
| 198 | Server-sent events (`id`, `Last-Event-ID`, `retry`) | WHATWG HTML · living standard · specification | https://html.spec.whatwg.org/multipage/server-sent-events.html |
| 199 | Events | AG-UI · live docs · protocol specification | https://docs.ag-ui.com/concepts/events |
| 200 | Making retries safe with idempotent APIs | AWS Builders' Library · foundational | https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ |
| 201 | SP 800-53 control overlays for AI (COSAiS) | NIST · 2026-01-08 · standards project, annotated outline | https://csrc.nist.gov/projects/cosais |
| 202 | Top 10 for Agentic Applications 2026 | OWASP · 2025-12-09 · standard | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| 203 | Exponential Backoff And Jitter | AWS · 2015/2023 · foundational | https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/ |
| 204 | LLM serving fairness | Cohere · 2026-06-17 · vendor engineering | https://cohere.com/blog/serving-fairness |
| 205 | Customizing the Copilot firewall | GitHub · live docs · primary | https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-the-firewall |
| 206 | LLM failover and load balancing | TrueFoundry · 2026 · vendor claims | https://www.truefoundry.com/blog/llm-failover-load-balancing-provider-outages |
| 207 | Agent reliability SLO patterns | Velsof · 2026 · secondary; no population, model or harness | https://www.velsof.com/ai-automation/ai-agent-reliability-engineering-slo-patterns/ |
| 208 | Canary, shadow mode, progressive rollouts | TuringPulse · 2026 · secondary practitioner | https://turingpulse.ai/blog/safe-agent-deployments |

### 20.8 Shipped systems and frameworks

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 209 | How Claude Code works | Anthropic · live docs · product documentation | https://code.claude.com/docs/en/how-claude-code-works |
| 210 | Subagents (Cursor) | Cursor · live docs · product documentation | https://cursor.com/docs/subagents |
| 211 | About Copilot cloud agent | GitHub · live docs · product documentation | https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent |
| 212 | Devin Can Now Manage a Team of Devins | Cognition · 2026 · vendor engineering blog | https://cognition.ai/blog/devin-can-now-manage-devins |
| 213 | Agent architecture (OpenHands) | OpenHands · live docs · project documentation | https://docs.openhands.dev/sdk/arch/agent |
| 214 | Deep Research system card | OpenAI · 2025-02 · system card | https://openai.com/index/deep-research-system-card/ |
| 215 | Gemini Deep Research Agent | Google · live docs, 2026 preview models · product documentation | https://ai.google.dev/gemini-api/docs/deep-research |
| 216 | Computer-Using Agent (CUA) | OpenAI · 2025-01-23 · product/technical announcement | https://openai.com/index/computer-using-agent/ |
| 217 | Claude Sonnet 4.5 announcement and eval methodology | Anthropic · 2025-09-29 · product announcement plus eval methodology | https://www.anthropic.com/news/claude-sonnet-4-5 |
| 218 | Agents SDK guide | OpenAI · live docs · SDK documentation | https://developers.openai.com/api/docs/guides/agents |
| 219 | Agent Framework overview | Microsoft · updated 2026-07-10 · product documentation | https://learn.microsoft.com/en-us/agent-framework/overview/ |
| 220 | Gemini Enterprise Agent Platform launch | Google Cloud · 2026-04-22 · product announcement | https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform |
| 221 | LangChain v1 release and migration | LangChain · 2025+ · framework release and migration docs | https://docs.langchain.com/oss/python/releases/langchain-v1 |
| 222 | CUA evaluation addendum | OpenAI · 2025 · evaluation addendum (PDF) | https://cdn.openai.com/cua/CUA_eval_extra_information.pdf |
| 223 | OpenAI Agents SDK integration (Temporal) | Temporal · GA update 2026-03-23 · vendor announcement | https://temporal.io/blog/announcing-openai-agents-sdk-integration |
| 224 | Wide Research architecture | Manus · 2025-10-29 · vendor claims | https://manus.im/blog/manus-wide-research-solve-context-problem |
| 225 | AgentKit update and Agent Builder wind-down | OpenAI · updated 2026-06-03 · product announcement | https://openai.com/index/introducing-agentkit/ |
| 226 | Environment-level agent telemetry | Microsoft Copilot Studio · live docs · product documentation | https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-environment-level-agent-telemetry |
| 227 | Introducing Amazon Bedrock AgentCore | AWS · GA 2025-10-13 · product announcement | https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/ |
| 228 | AutoGen v0.2 to v0.4 migration guide | Microsoft · live docs · framework documentation | https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html |
| 229 | AG2 Agent Harness | AG2 · 2026-06-17 · framework blog | https://docs.ag2.ai/docs/blog/2026/06/17/AG2-Agent-Harness/ |
| 230 | Production architecture | CrewAI · live docs · framework documentation | https://docs.crewai.com/en/concepts/production-architecture |
| 231 | smolagents ReAct architecture | Hugging Face · docs pinned v1.26.0 · framework documentation | https://huggingface.co/docs/smolagents/v1.26.0/en/conceptual_guides/react |
| 232 | Agent API: graph runs, streams and approvals | Pydantic AI · live docs · framework documentation | https://ai.pydantic.dev/api/agent/index.md |
| 233 | ReAct and tools | DSPy · live docs · framework documentation | https://dspy.ai/getting-started/react-and-tools/ |
| 234 | Observational Memory | Mastra · live docs · framework documentation | https://mastra.ai/docs/memory/observational-memory |
| 235 | Building effective agents | Anthropic · 2024-12-19 · engineering guidance (foundational) | https://www.anthropic.com/engineering/building-effective-agents |

### 20.9 Internal prior work

| # | Source | Org · date · type | URL |
| --- | --- | --- | --- |
| 236 | Agent architecture industry brief (prior pass) | internal · 2026-07-14 · internal memo | ../2026-07-14/agent-architecture-industry.md |
