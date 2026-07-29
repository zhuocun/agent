# Agent architecture (normative design)

**Status:** Design canon / decision record  
**Date:** 2026-07-14  
**Audience:** Anyone evolving the agent runtime, wire contract, or Deep Research UX

## Purpose

Define the **best agent architecture for Olune** — chat-anchored, flag-gated,
transparency-first — as lasting principles and evolution decisions. This is not
a generic agent essay and not a replacement for the build plan.

| Doc | Role |
| --- | --- |
| [`01-agentic-mode.md`](./01-agentic-mode.md) | **Build plan** for the shipped flag-gated engine (`AGENTIC_ENABLED` ∧ `TOOLS_ENABLED`; M0–M3 shipped, M4 partial). |
| **This doc (02)** | **Target architecture** — principles, topology, bounds, HITL, cost, observability, FE contract, shipped vs target gaps, and explicit non-goals. |

When 01 and 02 disagree on *intent*, 02 wins for direction; when they disagree
on *what code does today*, trust the as-built audit and the code. Close gaps by
changing code to match 02, then updating 01's remaining-gaps table.

**Provenance:** [research pass 2026-07-14](../research/2026-07-14/README.md) —
[industry brief](../research/2026-07-14/agent-architecture-industry.md) ·
[as-built audit](../research/2026-07-14/agent-architecture-as-built.md).

---

## Recommendation (normative)

**Default:** a single bounded ReAct / native tool-calling loop (today's
`run_agent_loop`).

**Opt-in Deep Research:** planner → bounded parallel workers → aggregator →
**(real) verifier**, with the **manager owning the user-facing answer**,
**chat-anchored in-turn only**.

Do not make multi-agent the default path. Most turns must not pay the ~15×
token tax of orchestrator-workers. Do not adopt peer swarm as the product shape.
Do not introduce Temporal (or equivalent durable execution) until there is an
explicit long-running workflow product surface.

---

## Topology

### Mermaid

```mermaid
flowchart TD
  FE[FE composer: Deep Research toggle]
  POST["POST /messages + agenticMode"]
  H[stream_and_persist / _resolve_provider_iter]
  RAW[raw provider.stream]
  LOOP[run_agent_loop]
  ORCH[run_orchestrator]

  FE --> POST --> H
  H -->|tools off| RAW
  H -->|tools on, agentic off| LOOP
  H -->|AGENTIC ∧ TOOLS| ORCH

  ORCH -->|mode=single| PRIM[primary run_agent_loop]
  ORCH -->|mode=deep_research| PLAN[Plan]
  PLAN --> HITL{Plan approval?}
  HITL -->|approve / skip| ADMIT[Budget admit]
  HITL -->|deny| PARTIAL[Labeled partial / empty]
  ADMIT -->|reject| PARTIAL
  ADMIT --> FAN[Bounded asyncio workers]
  FAN --> AGG[Aggregator]
  AGG --> VER{Verifier?}
  VER -->|on (default off)| JUDGE["Verifier (SHIPPED: fresh-context judge; TARGET: + CitationAgent)"]
  VER -->|off| DONE[Untagged Complete + RunCost]
  JUDGE --> DONE
  PRIM --> DONE
```

### ASCII (as-built shape, target verifier noted)

```
POST /api/conversations/:id/messages
  body.agenticMode?: "single" | "deep_research"
        │
        ▼
routes/conversations.py
  • coerce deep_research → single if !Pro && !BYOK
  • budget_headroom_usd · resumable buffer × N when agentic
        │
        ▼
streaming/handler.py :: _resolve_provider_iter
  ├── tools off              → raw provider.stream
  ├── tools on, agentic off  → run_agent_loop
  └── AGENTIC ∧ TOOLS        → run_orchestrator
        │
        ├── single → primary run_agent_loop (+ subagent tags)
        │
        └── deep_research
              plan → (plan HITL?) → admit
              → asyncio workers under Semaphore(MAX_CONCURRENCY)
                    each = run_agent_loop(scoped prompt)
              → mid-flight budget kill on SubagentDone
              → aggregate (untrusted DATA framing)
              → verifier  [SHIPPED: fresh-context judge (default off);
                           TARGET: + CitationAgent]
              → untagged Complete (summed usage) + RunCost
```

**Ownership rule:** the orchestrator / aggregator owns the reply
(manager-owns-answer / agents-as-tools). Workers never become the conversation
owner. Handoffs / peer swarm are out of scope for this product.

---

## Control phases (`deep_research`)

| # | Phase | Normative behavior |
| --- | --- | --- |
| 1 | **Plan** | Decompose into ≤ `AGENTIC_MAX_WORKERS` independent sub-questions; scale effort to complexity; persist the plan before truncation risk. |
| 2 | **Clarify (optional)** | When `AGENTIC_CLARIFY_BEFORE_PLAN`, ask 1–3 clarifying questions before planning / admit when ambiguity is high (fake: `CLARIFY:` marker; real: always ask). Pause via `agentic_plan_clarify` + `awaiting_approval` / `toolApproval`; resume with optional `editedInput.answers`. |
| 3 | **Plan approval (HITL)** | When `AGENTIC_PLAN_APPROVAL`, pause with plan + **estimated** cost (`costConfidence: "estimate"`); resume via server-issued `toolApproval` ids only. |
| 4 | **Admit** | Pre-spawn worst-case estimate vs per-run cap + composed headroom; refuse spawn rather than silent overrun. |
| 5 | **Fan-out** | Concurrent workers under concurrency semaphore; each reuses `run_agent_loop` (rounds, timeouts, tool HITL, untrusted feedback). |
| 6 | **Mid-flight budget** | On each worker `SubagentDone`, true-up cost; on cap breach cancel unfinished work and proceed to partial synthesis. |
| 7 | **Aggregate** | Compose survivors as **structured / DATA-framed** inputs — never splice into system/safety instructions. |
| 8 | **Verify** | **Shipped (default off):** fresh-context LLM-as-judge with JSON verdict, per-sample cost, sibling span. CitationAgent remains target. Do **not** treat `AGENTIC_VERIFIER_N` as free-form majority vote; N-sample majority is closed-form ``pass``/``fail`` only and requires all N samples. |
| 9 | **Finalize** | Untagged summed `Complete` + `RunCost`; persist subagent-grouped parts + per-worker attribution. |

`single` skips 1–8 fan-out: one `primary` loop, still chat-anchored.

---

## Hard bounds

Encode in config / code — never as prompt suggestions (OWASP LLM10:2025
Unbounded Consumption).

| Bound | Config (defaults) | Enforcement |
| --- | --- | --- |
| Master flags | `TOOLS_ENABLED`, `AGENTIC_ENABLED` (both required; boot-asserted) | Handler + `assert_prod_safe` |
| Max workers | `AGENTIC_MAX_WORKERS=4` | Planner truncate |
| Concurrency | `AGENTIC_MAX_CONCURRENCY=3` | Semaphore |
| Depth | `AGENTIC_MAX_DEPTH=1` | By construction (+ boot); raise only with eval proof |
| Per-run USD | `AGENTIC_RUN_BUDGET_USD=1.0` | Admit + mid-flight kill, plus a `single`-mode pre-flight halt on an already-exhausted seeded ledger (**soft** within an in-flight provider call — overshoot bounded ≈ one concurrent batch; A-10) |
| Tool rounds / timeout | `TOOL_MAX_ROUNDS`, `TOOL_TIMEOUT_SECONDS` | `run_agent_loop` / `execute_tool` |
| Entitlement | Pro / BYOK for `deep_research` | Coerce to `single` |
| Resumable buffer | `AGENTIC_RESUMABLE_BUFFER_MULTIPLIER` | Conversations route |

On breach: **cancel in-flight work**, aggregate survivors, emit a **labeled
partial** outcome — never hang or silent overrun.

---

## HITL layers

| Layer | When | Mechanism |
| --- | --- | --- |
| Tool approval | Side-effecting tools inside any loop | Shipped `awaiting_approval` + `toolApproval` |
| Plan approval | Before expensive fan-out | Same terminal; plan + estimate in pause card |
| Clarify-before-plan | Optional HITL (`AGENTIC_CLARIFY_BEFORE_PLAN`, default off) | Same terminal; `agentic_plan_clarify` questions card; resume via `toolApproval` (+ optional answers) |
| Stop | User cancels turn | Cancel workers; flush completed partials (`stopped`) |

**Never** treat worker or model text as approval. Gates bind to **server-issued**
plan/tool ids only.

**Disconnect ≠ cancel** when resumable streams are on; only Stop cancels.

---

## Untrusted-output rules

1. Schema-validate tool **arguments** before execution; least-privilege tools.
2. Tool results and LLM strings are **untrusted** (OWASP LLM05 / LLM06).
3. **Transitive:** worker findings enter the aggregator as structured data /
   artifact refs only — never as system/safety instructions; never as HITL
   authority.
4. Prefer artifact refs over stuffing full worker text into the lead (telephone
   loss + token bloat); in-turn `WorkerArtifact` + JSON DATA envelope is the
   shipped path (`aggregate.py`).

---

## Cost & attribution

- Run total = **sum of parts** (planner + workers + aggregator + verifier).
- Persist **per-worker** `ModelAttribution` (model/tier/substitution); **no
  silent downgrade** — the planner, a superseded sibling and a HITL-paused
  worker are each priced and attributed on the route that actually served them.
- `subtotal_usd` **is** the charge; `session_surcharge_usd` is a disclosure
  slice of it, never an addend. Image tokens bill on the phase that sent the
  attachments, once per turn.
- `run_cost` meter (`subtotalUsd` / `capUsd`) is a product feature.
  - **Shipped:** estimate at plan pause, progress ticks as workers complete,
    final at done — each with `confidence` / `phase`, and each persisted, so a
    reloaded meter keeps the label the backend emitted. A total reconstructed by
    summing per-subagent costs falls back to `estimate` / `plan`; it may never
    claim `exact` / `final`.
- Multi-agent research ≈ **~15×** chat tokens (industry published figure;
  `[verify-at-build]` against Olune metering). Entitlement-gate `deep_research`.

---

## Observability

OTel GenAI span tree (env-gated; no-op when unset):

- **Target tree:** parent request / workflow → `invoke_agent` per subagent
  (planner, worker, aggregator, verifier) → `execute_tool` / `chat` leaves.
- Spans carry ids, model/tier, token/cost rollups — **never message content**.

**Shipped:** `invoke_agent_span` on worker / primary / aggregator / quiet-planner
/ verifier paths in the orchestrator (verifier is a **sibling** under the
workflow, not nested under the aggregator). `execute_tool_span` wired in
`agent_loop.py`.

**Known limitation:** multi-sample (`N>1`) verifier currently opens one
`invoke_agent` span per sample (same subagent id).

---

## FE contract (additive, flag-gated)

| Surface | Contract |
| --- | --- |
| Bootstrap | `agenticEnabled = AGENTIC ∧ TOOLS` |
| Request | `agenticMode?: "single" \| "deep_research"` |
| SSE | Additive `subagentId`; `subagent_started` / `subagent_done` / `run_cost`; roles `primary` \| `worker` \| `aggregator` \| `orchestrator` \| `verifier` |
| Persist | `SubagentPart` + tagged children; share view cost-stripped |
| UI | Deep Research toggle; `SubagentPanel`; plan-approval via tool-approval UI; `RunCostMeter` on `run_cost` (**shipped:** estimate @ plan pause + final; **target:** live mid-fan-out ticks) |

Flag-off: byte-identical stream path (proven). Flag-on `single`: behavioral
reuse of the loop **with** subagent tags — not wire-identical.

---

## Memory layering

| Layer | Scope | Olune stance |
| --- | --- | --- |
| In-turn scratch | One ReAct loop | Message list inside `run_agent_loop` |
| Orchestration state | One Deep Research run | Plan, worker outputs/refs, budget counters — **in-request only** |
| Thread / conversation | Cross-turn chat | DB messages; resumable stream buffer |
| Long-term user/org | Cross-thread | Account prefs / FR-40 memory — **not** orchestrator state |

No cross-turn orchestrator memory. No background agent state store.

---

## Failure / degrade paths

| Failure | Behavior |
| --- | --- |
| Flag off | Pre-agentic path; byte-identical |
| Non-entitled `deep_research` | Coerce to `single` |
| Admit reject | Explained empty / partial; no spawn |
| Plan deny | Labeled synthesis; no fan-out |
| One worker fails, or writes no prose at all | Mark the worker `failed` (`agentic.worker_no_prose` for the silent case); omit it; synthesize survivors; `done` |
| Retryable worker error | Optional fallback route + substitution attribution |
| Budget breach mid-flight | Cancel unfinished — a superseded or budget-cancelled worker pause still gets its terminal `subagent_done` — labeled partial synthesis; `done` |
| Aggregator fails | Deterministic synthesis of survivors, labeled as a synthesis failure and never as a budget halt; already-relayed model prose is not re-sent; `partial` |
| Stop | Cancel remaining workers; flush completed partials |
| Disconnect (resumable on) | Continue into buffer; not cancel |
| Verifier off | Skip judge; do not claim verification |
| Verifier on (fail / budget skip / first-sample refusal / parse / truncate / judge crash) | Preserve manager draft with an honest incomplete caveat on **every** non-pass path; bill observed usage |

---

## Shipped vs target vs out of scope

### Shipped (as-built) — keep

- Flag-off identity; `single` wrap + `deep_research` plan/fan-out/aggregate
- Hard bounds + admit + mid-flight kill (planner-inclusive ledger); plan-approval HITL bound to `planHash`; Pro/BYOK coerce with FE callout
- Untrusted DATA framing into aggregator (delimited/capped); worker failure degrade + fallback priced on fallback binding
- Subagent-tagged SSE + persisted parts (incl. status/sources, outcome, attribution); buffer × N
- Real-provider planner/synthesis paths (deterministic no-network tests)
- `invoke_agent` OTel on worker/primary/aggregator/quiet planner; `execute_tool` OTel in `agent_loop`
- Mid-run `run_cost` ticks with `confidence`/`phase`; FE meter labels estimates
- Fresh-context verifier judge (default off; per-sample billed; fail/budget/quorum semantics); workers advertise+execute a scoped HITL allowlist (`request_user_confirmation`, plus fake-only `calendar_create_event`); `AGENTIC_MAX_DEPTH` boot-pinned to 1
- Always-on per-worker served model + live substitution; partial-synthesis warning chip; chat-anchored in-turn only; reuse `run_agent_loop`
- One degrade label per channel: an aggregator failure reads as a synthesis failure, a real cap breach keeps the budget label (including a halt before any prose, and the deep-research admit reject), and a relayed aggregator draft is delivered exactly once
- Every started subagent reaches a terminal outcome — streamed `subagent_done` for superseded and budget-cancelled worker pauses, handler-repaired on the persisted row for stop/disconnect (which structurally cannot stream one)
- Verifier honesty on every non-pass path: a first-sample affordability refusal reports `budget_halted`, a judge exception and a budget skip both caveat the draft, a non-success verifier *result* raises `partial`, and a budget skip raises it via `budget_halted` — the judge-exception arm caveats the draft but returns no result, so it ships `partial=False` (see Deferred)
- `single` mode refuses a resume whose seeded ledger is already over cap before opening a provider call and cancels the pending approval instead of parking an actionable card; a `single` pause emits its untagged `Complete` + final `RunCost` before the pause terminal
- Pause identity is server-owned: a resume runs in the orchestration mode (and tier / provider / model) it paused in, rejecting a conflicting client value without consuming the approval; a claim orphaned between claim and settle reaches a durable terminal — same-decision adoption for pseudo-tools, a persisted `failed` result for registry tools — with no side effect re-run
- Citation markers are per-worker safe: a marker cited before its own `Sources` event allocates a fresh global id instead of resolving to another worker's source; a settled tool-call id stays consumed across the worker id namespace
- FE contract parity: cased `verifier` role label, one ungrounded-marker rule shared by the thread and the public share, a reloaded meter that keeps its `Est.` label, persisted reasoning duration so "Thought for Ns" survives a cold render (untagged reasoning; a subagent-tagged panel renders no duration clause), non-success outcomes validated on both the live and reload path (never laundered into a green check), and no dead `plannedWorkers` / `completedWorkers` on the wire

### Target (gaps to close)

| Gap | Normative target |
| --- | --- |
| Verifier | **Shipped** fresh-context judge (default off); cost in meter per sample; CitationAgent still open. |
| `AGENTIC_VERIFIER_N` semantics | **Shipped:** N independent samples (≤5); majority on closed-form verdict only; consensus pass requires all N. |
| Tool subsets | **Shipped minimum** — workers get a scoped HITL allowlist (`request_user_confirmation` + fake-only `calendar_create_event`); expand to per-task scoped tools when broader worker tools are re-enabled |
| Mid-run `run_cost` ticks | **Shipped** — estimate + mid + final with `confidence`/`phase` + FE Est. label |
| `execute_tool` OTel | **Shipped** — wired in `agent_loop.py` |
| Planner / verifier `invoke_agent` spans | **Shipped** — quiet planner + verifier sibling spans |
| FE attribution display | **Shipped** always-on served model + live substitution on every served route (planner, superseded sibling, paused worker); fuller requested→served reason disclosure still open |
| High-cost composer hint | Surface before spend (partial-synthesis chip shipped; pre-send composer hint still open) |
| Clarify-before-plan | **Shipped** (flag-gated, default off) — `agentic_plan_clarify` HITL before plan/admit; fake marker `CLARIFY:`; real always asks 1–3 |
| Structured worker artifacts | **Shipped** (in-turn) — `WorkerArtifact` refs + JSON DATA envelope into aggregator; length caps; no DB table |
| Live E2E | **Gate shipped** — `api/tests/test_agentic_live_e2e.py` (opt-in `AGENTIC_LIVE_E2E=1` + real provider key). Run before prod `AGENTIC_ENABLED=true`; default CI skips cleanly. See `api/README.md` / `.env.example`. |
| Depth runtime check | **Shipped** boot pin `AGENTIC_MAX_DEPTH == 1`; runtime nesting counter only if recursion ever lands |

### Out of scope (do not grow into)

| Non-goal | Why |
| --- | --- |
| Background / scheduled / out-of-turn daemons | D23/D33 chat-anchored guardrail |
| Peer-swarm as default ownership | Confuses brand reply ownership + attribution |
| Temporal / durable workflows | No product surface for multi-hour / crash-proof runs yet |
| Agent SDK / user-authored graphs / platform | PRD anti-goal |
| Second loop engine | Subagents reuse `run_agent_loop` |
| Cross-turn orchestrator memory | FR-40 is account memory, not run state |
| OpenAI-style long-horizon single-agent as **default fan-out** | See decision table — keep as evaluated alternative for non-parallelizable research |

---

## Decision table

| Decision | Choice | Rationale |
| --- | --- | --- |
| Default path | Bounded single ReAct loop | Simplicity first; most turns must not pay ~15×; Anthropic "start simple"; OpenAI also shows strong single-agent research exists |
| Deep Research shape | Orchestrator-workers (manager-owns-answer) | Best-supported published pattern for **parallel breadth**; matches shipped 01 engine; separate contexts compress search |
| Why **not** OpenAI-style long-horizon single-agent as the Deep Research **fan-out default** | Keep single-loop as `single` / non-DR path; do not replace orchestrator with one long ReAct as the opt-in DR mode | Olune's product bet for the toggle is parallel breadth + per-worker attribution + plan HITL. Long-horizon single-agent remains a **competing architecture** to evaluate for sequential / non-parallelizable queries — not the DR default |
| Why **not** swarm | Manager owns the microphone | Peer handoffs confuse identity, guardrails, and cost attribution in a single-brand chat product |
| When durable execution becomes relevant | Explicit product mode for runs that outlive SSE/worker lifetime, multi-hour HITL, or crash-proof progress | Until then: in-request asyncio + resumable buffers + Stop≠disconnect. Temporal is a product decision, not a silent chat-turn evolution |
| Depth default | 1 | Blocks recursive orchestrator trees; raise only with eval proof |
| Verifier | Fresh-context judge / CitationAgent | Self-grade bias; Wang majority vote is for closed-form answers, not free-form reports |

---

## Competing architectures

| Shape | Summary | Fit for Olune |
| --- | --- | --- |
| **OpenAI Deep Research (long-horizon single-agent)** | One strong ReAct-style browse/reason trajectory; caps on iterations / wall-clock / fetches | Excellent for sequential research and as the **default `single` path**. Not the opt-in DR fan-out shape — would drop parallel context windows, plan HITL fan-out, and per-worker attribution UX the product already ships |
| **Anthropic Research (orchestrator-workers)** | Planner → parallel subagents → synthesis → CitationAgent / fresh-context eval; ~15× tokens; hard ops bounds | **Olune pick for `deep_research`.** Aligns with shipped topology; industry lessons map 1:1 to our bounds, HITL, untrusted-output, and cost meter |
| **Peer swarm / handoffs** | Specialists own the turn after transfer | Support-triage niche only; **not** Deep Research |
| **Graph / durable workflow** | LangGraph / ADK / Temporal checkpointed runs | Future **explicit** mode if runs outlive chat turns; premature as the SSE default |

**Pick:** default single bounded loop + Anthropic-style orchestrator-workers for
opt-in Deep Research, with deterministic budget/HITL/observability shell.

Confidence note: Anthropic's published gains are on *their* evals; OpenAI's
single-agent DR is competitive. Olune must keep a local golden set and re-eval
before raising depth, worker counts, or claiming multi-agent superiority on
every query class.

---

## Open questions / remaining gaps

**Batch C closed (V-009..V-013):** verifier lifecycle order + sibling span, failure-semantics tests, per-sample cost accounting / phase pricer, dead helper removal, and plan 01/02 as-built updates for the shipped default-off fresh-context judge.


Aligned with the as-built audit. Plan 01's remaining-gaps table tracks build-plan
status; this section owns **target** decisions and **deferred hard gaps**.

1. **Verifier enhancements** — CitationAgent (and/or chunked full-draft coverage);
   keep `AGENTIC_VERIFIER` default off until proven in live E2E.
2. **`AGENTIC_VERIFIER_N`** — shipped as independent sample count (default 1, ≤5);
   closed-form majority only; further quorum policy / parallel sampling still open.
3. **Per-worker tool subsets** — **minimum shipped** (workers: scoped HITL
   allowlist `{request_user_confirmation, calendar_create_event}`);
   expand to per-task scoped tools when broader worker tools are re-enabled.
4. **Mid-run `run_cost` ticks** — **closed** (estimate / mid / final + FE Est.).
5. **`execute_tool` OTel** — **closed**; quiet planner + verifier sibling spans shipped.
6. **Live-network E2E** — **gate shipped** (`test_agentic_live_e2e.py`); still a hard
   ops checklist item before flipping Fly `AGENTIC_ENABLED` (not auto-run in CI).
7. **Clarify-before-plan** — **shipped** behind `AGENTIC_CLARIFY_BEFORE_PLAN`
   (default off). Product latency vs budget-control trade remains tunable.
8. **Artifact store vs inline worker text** — **shipped minimum**: in-turn
   `WorkerArtifact` refs + schema-tagged JSON DATA envelope in
   `aggregate.build_synthesis_prompt` (no DB table). Durable artifact store
   remains a future upgrade.
9. **Sync vs async worker batches** — shipped sync wait is fine; async is a
   deliberate upgrade (head-of-line today).
10. **Entitlement coerce callout** — **shipped** via `submitted` + FE banner;
    copy/UX polish may continue.
11. **Partial-synthesis chip** — **shipped** (`agentic_run_summary` + warning UI).
12. **FE attribution display** — **shipped** always-on served model + live
    substitution, disclosed on every served route (planner, superseded sibling,
    HITL-paused worker); fuller requested→served reason disclosure still open.
    Public per-worker identity via `PublicAttribution` on `PublicSubagentPart`.
13. **Worker HITL resume (BE-005)** — **shipped**: tool `awaiting_approval`
    inside a worker suspends fan-out after siblings finish (wait policy),
    persists continuation (including `partialAnswer`) on the pending tool
    input (`_agenticContinuation`), and a later `toolApproval` continues that
    subagent with validated tool feedback — not a full re-plan. Workers may
    pause on the approval-gated stub `calendar_create_event` (allowlisted;
    `prod_safe=False` so real providers do not advertise it) and on
    provider-emitted pauses. Reuses the shipped `toolApproval` route +
    server-issued call ids. The resume runs in the orchestration mode the pause
    was taken in — pinned from the persisted continuation for plan, clarify and
    single-mode pauses alike, and resolved **before** the pseudo-tool settles, so
    a rejected mode cannot burn the approval.
14. **Approval idempotency (BE-007)** — **shipped**: approve/deny **CAS-claims**
    the pending tool_call (pending→approved/rejected + `_approvalClaimId`) and
    **commits before execute**, then settles a `tool_result` on the paused row.
    Concurrent double-approve is serialized with `SELECT … FOR UPDATE`; only the
    winner executes. Retries reuse the stored result. Claimed-without-result
    (crash/stop/disconnect between claim and settle) still never re-runs the side
    effect, and no longer strands the card: a **pseudo-tool** retry carrying the
    **same** decision adopts the row's existing claim and settles (an opposite
    decision still conflicts), and a **registry tool** persists a terminal
    `failed` `tool_result` under the existing claim instead of leaving the row
    `approved` / `running`. Persisting a failure executes nothing, so the
    fail-closed guarantee is unchanged.

---

## Deferred / product notes

- **A-8 (public share reasoning):** keep exposing worker reasoning / tool
  transcripts on public shares for now. Cost keys remain stripped. Revisit if
  product wants an internal-only filter.
- **AR-011 (whole-run wall-clock deadline):** deferred. Per-tool timeouts +
  round bounds + per-run USD soft cap remain the active consumption controls
  until an explicit product surface needs a run-level deadline.
- **Per-run USD soft cap (A-10):** admit + mid-flight kill are hard at phase
  boundaries; overshoot within an in-flight provider call is bounded ≈ one
  concurrent batch (see Hard bounds table).
- **Fan-out queue lost-sentinel hang (ORCH-6):** deferred as unreachable at the
  shipped bounds — `_FANOUT_QUEUE_MAXSIZE = 256` against a worst case of two
  protected items × `AGENTIC_MAX_WORKERS ≤ MAX_WORKER_ARTIFACTS = 16`, itself
  boot-asserted. Threading a lost-sentinel counter through producer and consumer
  buys nothing until a module constant moves, and the bound is now pinned by
  `api/tests/test_agentic_resilience.py::test_fanout_queue_bound_exceeds_protected_item_worst_case`
  so such a move fails loudly. Adjacent to AR-011 above, but not covered by it.
- **`ModelAttribution.memory_fact_ids` on the FE (FE-10):** deferred. The memory
  chip needs only the `memoryApplied` count, so adding an unused FE field or
  deleting a forward-looking backend field are both churn. Revisit when the
  per-fact deep-link the schema anticipates is built.
- **Per-worker served-model disclosure has no E2E coverage:** the backend
  contract — fallback pricing, persisted attribution, reason code — is covered by
  pytest, but no Playwright spec exercises `subagent-served-model` /
  `subagent-substitution-callout`. The fake provider has no trigger that yields a
  *fallback-served worker*: `RETRYABLE_WORKER:` emits reasoning before raising, so
  the visible-progress guard blocks transparent fallback and the worker simply
  fails. Closing it means a pre-visibility worker fallback trigger in
  `api/app/providers/fake.py`.
- **A judge exception caveats the answer without setting `RunCost.partial`:** the
  `partial` disjunction keys on a returned verifier result, so the exception arm
  (which returns none) ships `[Verification: incomplete …]` with `partial=False`.
  `budget_halted` stays correctly false, so this is an honesty-of-degree gap, not
  a wrong number; close it by keying `partial` on the verifier *outcome*.

## Invariants (must hold)

1. Flag-off byte-identical to pre-agentic stream.
2. Flag-on `single` = behavioral loop reuse + tags (not wire-identical).
3. Chat-anchored in-turn only — no out-of-turn execution.
4. Every subagent reuses `run_agent_loop`.
5. One seam: `_resolve_provider_iter`.
6. Additive wire + parts accumulation.
7. Untrusted transitive worker output into aggregator.
8. Budget halt → graceful labeled `done`, never opaque error hang.
9. Last untagged `Complete` wins for roll-up cost.
10. `AGENTIC_ENABLED` requires `TOOLS_ENABLED` at boot.
11. Disconnect ≠ cancel under resumable streams.
12. Plan approval reuses `toolApproval` — no parallel pause primitive.
13. No silent model downgrade inside a fan-out.
14. Manager owns the answer; workers are tools, not conversation owners.

---

## Related docs

- Build plan: [`01-agentic-mode.md`](./01-agentic-mode.md)
- PRDs: [`02` AI capabilities](../prd/02-ai-capabilities.md),
  [`07` transparency](../prd/07-transparency-contract.md),
  [`08` errors/limits](../prd/08-error-and-limit-states.md)
- Research: [2026-07-14 pass](../research/2026-07-14/README.md)
