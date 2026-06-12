# Agentic Mode Plan (orchestrated bounded subagents)

> **Implementation status**: **NOT built — spec'd this pass.** This plan is the build sequence for PRD 02 §4.6 FR-26c–FR-26k (PRD 00 §11 D33–D40). It is the multi-agent extension of the **shipped** single-agent tool loop (`api/app/tools/agent_loop.py`, behind `TOOLS_ENABLED`, fake-provider v1). Nothing here ships until each milestone's flag-off byte-identity check passes; **real-provider orchestration (M4) is gated on the fake-provider v1 (M1–M3) being proven end-to-end.**

The smallest extension that lets the existing chat turn spawn **bounded model subagents in-turn** — an orchestrator over N reuses of the shipped `run_agent_loop`, multiplexed back onto the one SSE stream — with **zero behavior change when `AGENTIC_ENABLED` is off**. Anchored to the shipped streaming/persistence path (`api/app/streaming/handler.py`), the shipped agent loop (`api/app/tools/agent_loop.py`), and the typed message-part union (`api/app/schemas/message.py`). PRDs guide direction; anything not gated behind a hard flag is out of scope.

"Zero behavior change" caveat: like tools and web search, agentic mode is a **default-OFF flag layered onto the existing stream handler**. With `AGENTIC_ENABLED=false` (the default) the orchestrator is never constructed and the byte stream is the pre-agentic build. No FE changes are required to ship the engine; the subagent-activity UI (PRD 01) lands alongside but is inert until the flag is set.

## Goal & non-goals

In scope (justified by FR-26c–FR-26k):

- An **orchestrator** at the existing `streaming/handler.py::_build_provider_iter()` seam that, within one assistant turn, fans out to **N bounded subagents** (each a `run_agent_loop` instance) and aggregates their outputs into one streamed answer.
- A **default single ReAct loop** (today's behavior, unchanged) plus an **opt-in "Deep Research"** mode: planner → fan-out workers → reviewer/aggregator.
- **Subagent-scoped** stream events + typed message parts + a **live per-run cost meter** + per-subagent model attribution (no silent downgrade inside a fan-out).
- A **hard per-run USD cap**, **fan-out bounds**, a **recursion-depth bound**, and **plan approval** reusing the shipped `awaiting_approval` HITL terminal.
- A **verifier / self-consistency** reviewer step (N≈3–5), config-driven.
- **OTel `invoke_agent` / `execute_tool`** span tree on the shipped env-gated tracing path.
- **Fake-provider orchestration v1 first**; real-provider subagent wiring as the gating prereq.

Explicitly out of scope:

- **Any background, scheduled, or out-of-turn execution** — the orchestrator starts and ends within a single chat turn (the D23/D33 chat-anchored guardrail). No daemon, no cron, no "agent that runs without a chat turn."
- A general agent/automation **platform**, an agent SDK surface, or user-authored agent graphs.
- New tool primitives, a new loop engine, or changes to the shipped per-tool timeout / round-bound / untrusted-output model (subagents **reuse** them verbatim).
- Resumable replay of an interrupted agentic run beyond the shipped `RESUMABLE_STREAMS_ENABLED` path (an agentic run reuses the same `Stream` reconciliation; mid-fan-out resume is not added here).
- Cross-turn / persistent orchestrator memory (memory stays the FR-40 account-global store; an agentic run holds only in-turn state).
- Real-provider tool/subagent wiring before the fake-provider v1 is proven (M4 gate).

Known FE follow-ups (callouts, not BE work):

- **Deep Research toggle** in the composer mode-row (PRD 01 §4.3), peer of the web-search / reasoning-effort toggles; hidden when `AGENTIC_ENABLED` is off (bootstrap advertises the capability).
- **Subagent activity panel**: renders the subagent-scoped parts (per-worker label, status, intermediate output) and the live per-run cost meter (PRD 01).
- **Plan-approval surface**: reuses the shipped tool-approval UI (`tool-part.tsx` approve/deny) at the orchestration boundary — the plan + cost estimate render in the pause card.
- The substitution callout already renders per-message; for an agentic turn it renders **per subagent** (no new FE primitive, just per-part attribution).

## Architecture overview

```
[ Next.js FE — composer Deep-Research toggle + subagent activity panel ]
        |
        |  POST /api/conversations/:id/messages  (agenticMode? in body)
        |  one SSE turn, unchanged transport
        v
[ FastAPI stream handler  (api/app/streaming/handler.py) ]
        |
        +-- _build_provider_iter()                      # the one seam
        |     ├── raw provider stream            (tools off — unchanged)
        |     ├── run_agent_loop(...)            (tools on, single loop — unchanged)
        |     └── run_orchestrator(...)          (AGENTIC_ENABLED on — NEW)
        |
        v
[ Orchestrator  (api/app/agentic/orchestrator.py — NEW, thin) ]
        |   planner → fan-out → aggregate → (verifier)
        |   budget + fan-out/depth bounds + plan-approval (awaiting_approval)
        |
        +-- worker subagent 1 ─┐
        +-- worker subagent 2 ─┤  each = run_agent_loop(...)  (REUSED verbatim)
        +-- worker subagent N ─┘  over a scoped sub-prompt + tool subset
        |
        v   multiplexed ProviderEvent stream (subagent-tagged)
[ handler accumulation/persistence — subagent-scoped parts on Message.parts ]
        |
        v
[ Neon Postgres — Message.parts (typed union + subagent grouping), attribution ]
```

Stack picks (one-line justifications):

- **Reuse `run_agent_loop`** — the bounded-round, per-tool-timeout, untrusted-output, HITL-pause behavior is already proven and tested; a subagent is just an instance of it over a scoped sub-prompt. No second loop engine.
- **One seam (`_build_provider_iter()`)** — the orchestrator is a third branch beside the raw stream and the single loop, so the handler's accumulation, persistence, cancellation, and fallback paths are unchanged.
- **`asyncio` fan-out** — workers run concurrently as `asyncio` tasks bounded by a semaphore (max concurrency), their `ProviderEvent` streams merged into the handler's existing queue. No Celery/arq/Redis — orchestration is in-turn on the same worker, exactly like the shipped title-autogen detachment is *not* (this stays on the request task so cancellation propagates).
- **Subagent-tagged events** — every relayed `ProviderEvent` carries a `subagent_id` so the handler can group parts and the FE can render per-worker activity; the wire stays the same SSE event names with an added field (additive, camelCase).
- **Budget on the shipped cost math** — the per-run cap reads `api/app/providers/pricing.py` output, the same per-message accounting the transparency wedge already computes (no parallel cost model).
- **Flag discipline** — `AGENTIC_ENABLED` (default `False`) gated by `TOOLS_ENABLED`; both must be on. Validated at boot in `app/config.py` like the other backend flags.

## Architectural shifts vs the single agent loop

The biggest change: a turn may now drive **more than one** `run_agent_loop`. Knock-on effects:

- **Event multiplexing.** Today the handler pumps one `ProviderEvent` iterator into its queue. The orchestrator merges N child iterators; each event is tagged with its `subagent_id` so accumulation groups correctly. The single-loop and raw paths are untouched (one un-tagged stream).
- **Cost is a sum, not a single usage chunk.** The terminal cost for an agentic turn is the **sum of all subagent costs** (plus the aggregator/reviewer). The per-message `cost_usd` / `cost_breakdown` becomes a roll-up; per-subagent costs persist on the subagent parts so the run is auditable.
- **HITL at two levels.** The shipped per-tool `awaiting_approval` gate still fires inside any worker; the orchestrator adds an optional **plan-level** `awaiting_approval` before fan-out. Both reuse the same terminal state + `toolApproval` resume route — no new pause primitive.
- **Cancellation across a fan-out.** The existing disconnect-detect cancels the request task; the orchestrator must cancel all in-flight worker tasks on disconnect/Stop and flush completed-worker partials into `parts` (same `status="stopped"` discipline as the single path).

## Wire contract

No new endpoint. The agentic run rides the **existing** `POST /api/conversations/:id/messages` SSE turn (build plan `00-backend-minimal.md` "Wire contract"). Two additive changes, both inert when the flag is off:

### Request body (additive field)

```ts
{
  // ...existing send fields (clientMessageId, tierId, text, ...)
  agenticMode?: "single" | "deep_research";   // default "single" (unchanged behavior)
}
```

`agenticMode` is ignored unless `AGENTIC_ENABLED && TOOLS_ENABLED`. `"single"` is byte-identical to the shipped path. `"deep_research"` engages the orchestrator.

### Stream events (additive `subagentId` + new grouping)

Existing event names are unchanged; agentic events carry an optional `subagentId` and the orchestrator adds two:

- `subagent_started` — `{ subagentId, label, role: "worker" | "reviewer" | "orchestrator" }`. A new bounded subagent began.
- `reasoning_delta` / `answer_delta` / `status` / `tool_call` / `tool_result` — **unchanged payloads**, now optionally tagged `{ subagentId, ... }` so the FE groups them under the right worker.
- `subagent_done` — `{ subagentId, attribution: ModelAttribution, costUsd }`. A subagent finished; its per-subagent attribution + cost.
- `run_cost` — `{ subtotalUsd, capUsd }`. Live per-run cost meter tick (FR-26h); emitted as workers complete so the FE meter updates mid-run.
- `terminal` — `{ status: "done", messageId, attribution }` where `attribution.costUsd` is the **run total** (sum of subagents). A plan-approval pause ends the turn at `awaiting_approval` exactly as a tool pause does (no `terminal`).
- `error` — unchanged envelope (PRD 08). A per-run budget halt produces a **partial synthesis** + `done`, not an `error` (graceful degrade, FR-26g).

### Persistence (additive part grouping)

`message.parts` (the typed union — `text | reasoning | status | sources | attachment | tool_call | tool_result`) gains a **subagent grouping**: subagent-scoped parts carry a `subagentId` and a new `subagent` marker part (`{ subagentId, label, role, attribution, costUsd }`) so a reloaded agentic turn replays which subagent produced which output. This is **additive to the discriminated union** (PRD 00 §11 D7), not a rewrite — non-agentic messages carry no `subagentId` and render exactly as today. The `JSONB` column already accepts the wider shape (per `00-backend-minimal.md` data-model notes); no migration to the column type, only new optional keys.

## Orchestration

The orchestrator (`api/app/agentic/orchestrator.py`, NEW) is a thin coordinator returning the same `AsyncIterator[ProviderEvent]` the handler already consumes — so the handler's accumulation/persistence/cancellation is unchanged. It:

1. **Plans.** For `deep_research`, a bounded planning step (itself a `run_agent_loop` over the orchestrator role) decomposes the prompt into ≤`AGENTIC_MAX_WORKERS` independent sub-questions. For `single`, planning is a no-op and the run is one loop (today's path).
2. **(Optional) pauses for plan approval.** If `AGENTIC_PLAN_APPROVAL` (or a per-turn flag) is set, emit `AwaitingApproval` at the plan boundary with the decomposition + estimated cost; the handler turns this into the paused terminal, resumed via `toolApproval`.
3. **Fans out.** Spawn one worker `run_agent_loop` per sub-question as `asyncio` tasks bounded by an `AGENTIC_MAX_CONCURRENCY` semaphore; merge their `ProviderEvent` streams (tagged with `subagent_id`) into the handler's queue. Each worker gets a scoped sub-prompt and (optionally) a restricted tool subset; each is bounded by the shipped `TOOL_MAX_ROUNDS` + per-tool timeout.
4. **Enforces bounds.** A recursion-depth bound (default 1 orchestrator→worker level; workers do **not** spawn unbounded sub-trees) and the per-run USD cap (read from `pricing.py` as subagents complete). On cap breach: stop spawning, cancel un-started workers, and proceed to aggregate the completed workers' outputs (partial synthesis, labeled).
5. **Aggregates.** A synthesis step (a bounded subagent) composes the workers' outputs — **fed back only as structured data, never spliced into instructions** (transitive untrusted-output, FR-26i) — into the final answer streamed on the turn.
6. **(Optional) verifies.** If `AGENTIC_VERIFIER` is on, run a reviewer subagent or an N≈3–5 self-consistency pass over the synthesis before finalizing (FR-26j); its cost rolls into the run total.
7. **Finalizes.** The handler computes the run-total `CostBreakdown` + `ModelAttribution` (sum over subagents), persists the subagent-grouped `parts`, and yields `terminal`.

**Invariants:**

- With `AGENTIC_ENABLED=false`, `run_orchestrator` is never constructed — `_build_provider_iter()` returns exactly the shipped raw/single-loop branches. Byte-identical.
- A worker's behavior (rounds, timeout, HITL, untrusted feedback) is exactly the shipped single-loop behavior — the orchestrator adds only fan-out/aggregate/bound/verify logic.
- A subagent's output is **untrusted** to its parent/aggregator (transitive SR-2); it never alters orchestrator system/safety behavior.
- Cancellation/Stop cancels all in-flight workers and flushes completed-worker partials (`status="stopped"`, `costConfidence="estimate"`), same as the single path.
- The run never escapes the turn: no state persists except the assistant message + its subagent parts.

## Cost & budget

Per-run cost reuses `api/app/providers/pricing.py` — no parallel cost model. The run total is the **sum of subagent `cost_usd`** (workers + planner + aggregator + reviewer). Two multipliers are budgeted **separately** (FR-26g) so the cap is sized against their product, not either alone:

- **Reasoning-token multiplier** — thinking tokens are full-price, never cache-eligible; the 2026 research observed **~4–15× cost vs a non-reasoning turn** (PRD 02 FR-18, `[verify-at-build]`).
- **Multi-agent fan-out multiplier** — a multi-agent system burns materially more tokens than one chat turn; **Anthropic's multi-agent research reports ~15× the tokens of a single chat** (`[verify-at-build]`).

The per-run cap composes with the shipped user/platform budget caps (`USAGE_BUDGET_USD`, `preferences.monthly_budget_usd`, `preferences.per_conversation_budget_usd`) and PRD 08 `PLATFORM_CONVERSATION_CAP`. Breaching the per-run cap **degrades gracefully** (partial synthesis), never a hang or a silent overrun. BYOK runs are exempt from platform caps but still metered and capped per-run.

## Observability

Agentic runs emit OpenTelemetry spans on the shipped env-gated path (`api/app/observability/tracing.py`, no-op when `OTEL_EXPORTER_OTLP_ENDPOINT` unset): one **`invoke_agent`** span per subagent (orchestrator → worker → reviewer) nested under the turn's request span, with the existing **`execute_tool`** spans nested under each subagent. Spans carry ids + model/tier + token/cost rollups, **never message content** (matching the structured-log discipline). structlog already injects `trace_id` / `span_id` when a span is active, so a run's fan-out tree is correlatable in logs.

## Config / flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `AGENTIC_ENABLED` | `False` | Master switch; inert unless `TOOLS_ENABLED` is also true. |
| `AGENTIC_MAX_WORKERS` | small (e.g. 4) | Max total subagents per run. |
| `AGENTIC_MAX_CONCURRENCY` | small (e.g. 3) | Max concurrent workers (semaphore). |
| `AGENTIC_MAX_DEPTH` | `1` | Recursion-depth bound (orchestrator→worker levels). |
| `AGENTIC_RUN_BUDGET_USD` | small | Hard per-run USD cap. |
| `AGENTIC_PLAN_APPROVAL` | `False` | Require plan approval (HITL) before fan-out. |
| `AGENTIC_VERIFIER` | `False` | Enable reviewer / self-consistency step. |
| `AGENTIC_VERIFIER_N` | `3` | Self-consistency sample count (≈3–5). |

All validated at boot in `app/config.py`; all bounds are config, never hardcoded (mirrors the no-hardcoding discipline of PRD 02 §5).

## Open questions / decisions for the user

- **Decomposition quality.** Planner-driven decomposition is the hardest quality lever; the fake-provider v1 uses a deterministic decomposition so the engine can be tested before planner quality is tuned on a real provider.
- **Partial-synthesis labeling.** How prominently to label a budget-halted partial answer (a calm "answered with N of M planned steps" chip vs an error-class banner — leaning chip, per the no-silent-downgrade/honesty ethos).
- **Concurrency vs provider rate limits.** `AGENTIC_MAX_CONCURRENCY` interacts with provider 429s; the shipped single-shot fallback is per-subagent, so a worker rate-limit degrades that worker, not the run.
- **Per-subagent tool subsets.** Whether workers get the full tool registry or a scoped subset by default (leaning scoped, least-privilege per FR-26 / SR-2).

## Milestones

### M0 — Seam + flag + inert orchestrator

Scope: `app/agentic/` scaffolded; `AGENTIC_ENABLED` + bound/budget flags in `app/config.py` (boot-validated, gated by `TOOLS_ENABLED`); the third branch in `streaming/handler.py::_build_provider_iter()` constructed **only** when both flags are on; bootstrap advertises the capability so the FE can show the (hidden-by-default) Deep-Research toggle. No fan-out yet.

Demo: with the flag off, every existing test passes byte-for-byte; with the flag on and `agenticMode:"single"`, behavior is identical to the shipped single loop. A CI assertion proves flag-off byte-identity.

Effort: ~1–2 days (config + seam + the byte-identity test harness).

### M1 — Fake-provider single-loop-equivalent orchestrator

Scope: `run_orchestrator` returns a one-worker run that is behaviorally identical to `run_agent_loop` for `agenticMode:"single"`; the subagent-tagging plumbing (`subagent_id` on relayed events) and the additive `subagent` marker part land but with N=1. Persistence groups the single subagent's parts; reload replays them.

Demo: a `single` agentic turn over the fake provider streams + persists exactly one subagent group; the run total cost equals the single subagent's cost.

Effort: ~2–3 days (event tagging + part grouping + persistence round-trip).

### M2 — Fake-provider Deep-Research fan-out + aggregate

Scope: deterministic planner decomposition; `asyncio` fan-out to N bounded workers under the concurrency semaphore; event multiplexing into the handler queue; the synthesis/aggregation step (untrusted-output discipline); `subagent_started` / `subagent_done` / `run_cost` events; subagent-grouped parts for N>1.

Demo: a `deep_research` turn over the fake provider spawns ≥2 concurrent workers, streams their tagged activity, and aggregates one answer; reload replays per-worker groups. Cancellation cancels all workers and flushes completed-worker partials.

Effort: ~4–5 days (fan-out + multiplexing + aggregate + cancellation are the high-risk area).

### M3 — Budget, plan-approval HITL, verifier, transparency + OTel

Scope: per-run USD cap (graceful partial-synthesis halt) + fan-out/depth bounds enforced; plan-approval pause reusing `awaiting_approval` + `toolApproval` resume; verifier / self-consistency step (config N); per-subagent `ModelAttribution` + substitution codes (no silent downgrade in fan-out); the live per-run cost meter; `invoke_agent` / `execute_tool` OTel span tree.

Demo: a run that would exceed its cap returns a labeled partial synthesis; a plan-approval-required run pauses at `awaiting_approval` with plan + estimate; a forced per-worker substitution renders a per-subagent callout; with OTel configured the run produces the expected span tree.

Effort: ~4–5 days (budget + HITL reuse + verifier + attribution).

### M4 — Real-provider subagent wiring + hardening (gating prereq)

Scope: wire real providers (DeepSeek/OpenAI-compatible + Anthropic) as subagent backends through the same `run_agent_loop` real-provider tool path; **only after M1–M3 are proven on the fake provider** (FR-26d / D40). PRD-08 error envelope on every agentic path; structlog run/subagent keys; tighten budget + concurrency-vs-rate-limit handling; document remaining gaps.

Demo: a real-provider `deep_research` run fans out, aggregates, and bills correctly with full transparency; a forced provider error on a worker degrades that worker, not the run.

Effort: ~3–4 days (real-provider parity is the slow part; gated on the fake-provider v1).

## What we are explicitly NOT building (and where it lives in the PRD)

| Deferred capability | PRD reference |
| --- | --- |
| Background / scheduled / out-of-turn agents | PRD 00 §1/§3 guardrail; PRD 02 §4.6 (D23/D33 — chat-anchored only) |
| Agent SDK / user-authored agent graphs / agent platform | PRD 00 §1/§3 (anti-goal) |
| New tool primitives or a second loop engine | PRD 02 §4.6 (subagents reuse `run_agent_loop`) |
| Sandboxed code execution as a worker tool | PRD 02 FR-26a (P2; its own approval-gated tool) |
| MCP action connectors as worker tools | PRD 02 FR-42a / §4.12 (P2) |
| RAG / retrieval as a worker capability | PRD 02 FR-29 / §4.13 (P2; object storage + pgvector) |
| Mid-fan-out resumable replay | PRD 04 §5.1 (P1 replay reused as-is, not extended) |
| Cross-turn / persistent orchestrator memory | PRD 02 FR-40 (account-global memory, not orchestrator state) |
| Real-provider orchestration before fake-provider v1 | PRD 02 FR-26d / FR-26k (M4 gate; D40) |

## File / folder layout

`api/app/agentic/` is the new home; everything else is an additive touch to existing modules.

```
api/app/
  agentic/
    __init__.py
    orchestrator.py        # run_orchestrator: plan → fan-out → aggregate → verify; bounds + budget
    planner.py             # decomposition (deterministic for fake-provider v1)
    aggregate.py           # synthesis of worker outputs (untrusted-output discipline)
    verifier.py            # reviewer / self-consistency (N≈3–5)
    budget.py              # per-run USD cap + fan-out/depth bounds (reads providers/pricing.py)
  streaming/
    handler.py             # _build_provider_iter(): + run_orchestrator branch (gated)
  schemas/
    stream_events.py       # + subagent_started / subagent_done / run_cost; subagentId on existing
    message.py             # + subagent marker part (additive to the typed union)
    conversation.py        # + agenticMode on the send body
  config.py                # + AGENTIC_* flags (boot-validated, gated by TOOLS_ENABLED)
  observability/
    tracing.py             # + invoke_agent spans (execute_tool already present)
tests/
  test_agentic_flag_off.py     # byte-identity with the shipped single-loop path
  test_agentic_fanout.py       # fake-provider fan-out + aggregate + part grouping
  test_agentic_budget.py       # per-run cap → graceful partial synthesis
  test_agentic_approval.py     # plan-approval pause + toolApproval resume
  test_agentic_safety.py       # transitive untrusted-output fixture; recursion/fan-out bounds
```

Conventions (inherited from `00-backend-minimal.md`):
- Pydantic schemas are the wire-boundary truth; the SSE encoder stays one module; every new event payload is a Pydantic model under `app/schemas/stream_events.py`.
- All `AGENTIC_*` bounds are config validated at boot; no hardcoded fan-out/depth/budget constants (PRD 02 §5 no-hardcoding discipline applies).
- The orchestrator yields the same `ProviderEvent` union the handler already consumes, so accumulation / persistence / cancellation / fallback are unchanged.
