# Agentic Mode Plan (orchestrated bounded subagents)

> **Implementation status**: **SHIPPED behind `AGENTIC_ENABLED` (default off, gated by `TOOLS_ENABLED`).** M0–M3 are built and tested on the fake provider (`api/app/agentic/*`, `api/tests/test_agentic_*.py`, `web/tests/e2e/agentic.spec.ts`). With the flag off, the stream path stays byte-identical to the pre-agentic build (`test_agentic_flag_off.py`). **M4 is PARTIALLY SHIPPED** — real-provider planner/synthesis code paths exist in `orchestrator.py`; per-worker fallback + failure-degrade, agentic resumable-buffer sizing, and per-worker attribution *persistence* are built and tested (`test_agentic_resilience.py`, `test_agentic_real_provider.py`). The **fresh-context verifier judge is shipped default-off** (`AGENTIC_VERIFIER=false`): provider-backed JSON verdict, per-sample cost, sibling OTel span. Still open (see **Remaining gaps**): mid-fan-out `run_cost` ticks honesty, scoped per-worker tool subsets, fuller live/always-on attribution UX, heterogeneous fallback pricing, and broader live-network E2E coverage (opt-in gate exists). Do not enable `AGENTIC_ENABLED` in a real-key environment until the live-provider path is proven end to end.
>
> **Normative target architecture** lives in [`02-agent-architecture.md`](./02-agent-architecture.md). When this build plan and 02 disagree on *intent*, 02 wins; when either disagrees with *what code does today*, trust the [as-built audit](../research/2026-07-14/agent-architecture-as-built.md) and the code. Do not treat aspirational wording below as shipped.

The smallest extension that lets the existing chat turn spawn **bounded model subagents in-turn** — an orchestrator over N reuses of the shipped `run_agent_loop`, multiplexed back onto the one SSE stream — with **zero behavior change when `AGENTIC_ENABLED` is off**. Anchored to the shipped streaming/persistence path (`api/app/streaming/handler.py`), the shipped agent loop (`api/app/tools/agent_loop.py`), and the typed message-part union (`api/app/schemas/message.py`). PRDs guide direction; anything not gated behind a hard flag is out of scope.

"Zero behavior change" caveat: like tools and web search, agentic mode is a **default-OFF flag layered onto the existing stream handler**. With `AGENTIC_ENABLED=false` (the default) the orchestrator is never constructed and the byte stream is the pre-agentic build. No FE changes are required to ship the engine; the subagent-activity UI (PRD 01) lands alongside but is inert until the flag is set.

## Goal & non-goals

In scope (justified by FR-26c–FR-26k):

- An **orchestrator** at the existing `streaming/handler.py::_resolve_provider_iter()` seam that, within one assistant turn, fans out to **N bounded subagents** (each a `run_agent_loop` instance) and aggregates their outputs into one streamed answer.
- A **default single ReAct loop** (today's behavior, unchanged) plus an **opt-in "Deep Research"** mode: planner → workers → aggregator → optional verifier.
- **Subagent-scoped** stream events + typed message parts + a **per-run cost meter** (orchestrator emits estimate @ plan pause, progress ticks as workers complete, and final; wire schema carries `confidence`/`phase` — confirm handler encode + FE parse stay in sync) + per-subagent model attribution persistence (live `subagent_done` attribution on the wire is target/partial — see **Remaining gaps**).
- A **hard per-run USD cap**, **fan-out bounds**, a **recursion-depth bound**, and **plan approval** reusing the shipped `awaiting_approval` HITL terminal.
- A **fresh-context verifier judge** when `AGENTIC_VERIFIER` is on (**default off**): independent provider call with immutable system rubric + DATA envelope, strict JSON ``{verdict,report}``, manager-owned answer (pass/fail notes only; never draft replacement). ``AGENTIC_VERIFIER_N`` (default 1, hard-capped at 5) runs N independent samples; majority applies only to the closed-form verdict and requires all N samples to complete. Per-sample costs are summed (not a collapsed re-price). CitationAgent remains a future enhancement.
- A **Pro/BYOK entitlement gate** on `deep_research` — the fan-out's token burn (below) makes it a paid-tier / bring-your-own-key capability; anonymous/free turns fall back to `single` even with the flag on.
- **OTel `invoke_agent`** spans on worker / primary / aggregator / verifier / quiet-planner paths; **`execute_tool_span` wired** in `agent_loop.py`.
- **Fake-provider orchestration v1 first**; real-provider subagent wiring as the gating prereq (M4 partial — paths exist, live-network E2E does not).

Explicitly out of scope:

- **Any background, scheduled, or out-of-turn execution** — the orchestrator starts and ends within a single chat turn (the D23/D33 chat-anchored guardrail). No daemon, no cron, no "agent that runs without a chat turn."
- A general agent/automation **platform**, an agent SDK surface, or user-authored agent graphs.
- New tool primitives, a new loop engine, or changes to the shipped per-tool timeout / round-bound / untrusted-output model (subagents **reuse** them verbatim).
- Resumable replay of an interrupted agentic run beyond the shipped `RESUMABLE_STREAMS_ENABLED` path (an agentic run reuses the same `Stream` reconciliation; mid-fan-out resume of a paused *worker* is not added here — known hard gap, see plan 02). Replay **semantics** are reused as-is; agentic runs **multiply** event/byte buffer caps by `AGENTIC_RESUMABLE_BUFFER_MULTIPLIER` (default 4). Truncation/coalescing remains an operational tuning concern if fan-out still overflows the multiplied bound.
- Cross-turn / persistent orchestrator memory (memory stays the FR-40 account-global store; an agentic run holds only in-turn state).
- Real-provider tool/subagent wiring before the fake-provider v1 is proven (M4 gate; paths now exist — live E2E still open).

Shipped FE (behind `AGENTIC_ENABLED`; PRD 01):

- **Deep Research toggle** in the composer mode-row (`model-mode-picker.tsx`), peer of web-search / reasoning-effort; hidden when bootstrap does not advertise `agenticEnabled`.
- **Subagent activity panel** (`subagent-panel.tsx`): per-worker label, status, intermediate output, persisted substitution callout after reload, and run-cost meter fed by `run_cost` frames. Per-subagent per-row cost badges removed per D41.
- **Plan-approval surface**: reuses the shipped tool-approval UI (`tool-part.tsx` approve/deny) at the orchestration boundary — plan + cost estimate in the pause card.
- **Share-view `SubagentPanel`**: `public-conversation-view.tsx` → `AgenticAssistantParts` renders the panel cost-stripped. Public projection keeps nested `PublicAttribution` (identity/substitution) when the share schema is current; strip cost only.

Remaining FE gaps (see **Remaining gaps**): always-on per-worker served-model label + live-stream attribution (substitution callout exists on reload from persisted parts), high-cost composer hint, PRD 08 partial-synthesis warning chip, public per-worker attribution projection.

## Architecture overview

```
[ Next.js FE — composer Deep-Research toggle + subagent activity panel ]
        |
        |  POST /api/conversations/:id/messages  (agenticMode? in body)
        |  one SSE turn, unchanged transport
        v
[ FastAPI stream handler  (api/app/streaming/handler.py) ]
        |
        +-- _resolve_provider_iter()                      # the one seam
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
[ handler accumulation/persistence — subagent-AWARE: _apply_event/_build_parts group by subagentId ]
        |
        v
[ Neon Postgres — Message.parts (typed union + subagent grouping), attribution ]
```

Stack picks (one-line justifications):

- **Reuse `run_agent_loop`** — the bounded-round, per-tool-timeout, untrusted-output, HITL-pause behavior is already proven and tested; a subagent is just an instance of it over a scoped sub-prompt. No second loop engine.
- **One seam (`_resolve_provider_iter()`)** — the orchestrator is a third branch beside the raw stream and the single loop. The branch *selection* is the only change to those two paths: with the flag off, the raw and single-loop branches are byte-identical. The shared accumulation does change — `_apply_event` / `_build_parts` become subagent-aware (group by `subagentId`) — but additively: an un-tagged stream (raw/single-loop) groups into exactly one default group, so its output is unchanged.
- **`asyncio` fan-out** — workers run concurrently via `asyncio.create_task` bounded by a semaphore (max concurrency), their `ProviderEvent` streams merged into the handler's existing queue (unbounded queue + `gather` on completion). No `TaskGroup` / structured concurrency today. No Celery/arq/Redis — orchestration is in-turn on the same worker (this stays on the request task so cancellation propagates).
- **Subagent-tagged events** — every relayed `ProviderEvent` carries a `subagent_id` so the handler can group parts and the FE can render per-worker activity; the wire stays the same SSE event names with an added field (additive, camelCase).
- **Budget on the shipped cost math** — the per-run cap reads `api/app/providers/pricing.py` output, the same per-message accounting the transparency wedge already computes (no parallel cost model).
- **Flag discipline** — `AGENTIC_ENABLED` (default `False`) gated by `TOOLS_ENABLED`; both must be on. Validated at boot in `app/config.py` like the other backend flags.

## Architectural shifts vs the single agent loop

The biggest change: a turn may now drive **more than one** `run_agent_loop`. Knock-on effects:

- **Event multiplexing.** Today the handler pumps one `ProviderEvent` iterator into its queue. The orchestrator merges N child iterators; each event is tagged with its `subagent_id` so accumulation groups correctly. The single-loop and raw paths are untouched (one un-tagged stream).
- **Cost is a sum, not a single usage chunk.** The intended terminal cost is the **sum of planner + workers + aggregator (+ real verifier when metered)**. **As-built caveat:** fallback workers may display substituted provider/model labels while still pricing usage and tier breakdowns against the **original** binding; planner spend can be dropped on pause/decline/admit-reject exits; mid-flight cap checks currently accumulate worker costs only. Do not call the roll-up fully heterogeneous/auditable until those gaps close (plan 02 / FE-009). Persist per-subagent markers with nested attribution where built; the top-level `cost_usd` is the roll-up the handler emits.
- **HITL at two levels.** The shipped per-tool `awaiting_approval` gate still fires inside any worker; the orchestrator adds an optional **plan-level** `awaiting_approval` before fan-out. Both reuse the same terminal state + `toolApproval` resume route — no new pause primitive. **Known hard gap:** a tool pause *inside* a worker does not cleanly resume that worker (plan 02 open questions).
- **Cancellation across a fan-out.** Workers are spawned with `asyncio.create_task`; on Stop or mid-flight budget breach the orchestrator cancels unfinished tasks and `gather`s them (no `TaskGroup`). Completed-worker partials flush into `parts` (same `status="stopped"` discipline as the single path). **Disconnect ≠ cancel when resumable streaming is on**: with `RESUMABLE_STREAMS_ENABLED`, the handler wraps the request in `_NeverDisconnectedRequest`, so a client disconnect must **not** tear down the fan-out (the run keeps producing into the resumable buffer); only an explicit Stop cancels. The teardown path keys off the same cancel signal as the single loop, not raw disconnect.

## Wire contract

No new endpoint. The agentic run rides the **existing** `POST /api/conversations/:id/messages` SSE turn (build plan `00-backend-minimal.md` "Wire contract"). Two additive changes, both inert when the flag is off:

### Request body (additive field)

```ts
{
  // ...existing send fields (clientMessageId, tierId, text, ...)
  agenticMode?: "single" | "deep_research";   // default "single" (unchanged behavior)
}
```

`agenticMode` is ignored unless `AGENTIC_ENABLED && TOOLS_ENABLED`. With the flag **off**, the path is **byte-identical** to the shipped stream. With the flag **on**, `"single"` routes through the orchestrator as a one-worker run: it is a **behavioral equivalent** of the shipped loop (same rounds/timeout/HITL/output), **not wire-identical** — relayed events carry a `subagentId` tag and the message gains one `subagent` marker part. `"deep_research"` engages the full fan-out orchestrator. `deep_research` additionally requires the Pro/BYOK entitlement (see Goal & non-goals); a non-entitled request is coerced to `single`.

### Stream events (additive `subagentId` + new grouping)

Existing event names are unchanged; agentic events carry an optional `subagentId` and the orchestrator adds two:

- `subagent_started` — `{ subagentId, label, role }` where role is one of `primary` \| `worker` \| `aggregator` \| `orchestrator` \| `verifier` (plan 02 / as-built). Shipped emitters use `primary` (single wrap), `worker` (fan-out), `aggregator` (synthesis), `verifier` (fresh-context judge), and may use `orchestrator` for planner-phase markers; there is **no** shipped `reviewer` role — reserve that only if/when a CitationAgent ships.
- `reasoning_delta` / `answer_delta` / `status` / `tool_call` / `tool_result` — **unchanged payloads**, now optionally tagged `{ subagentId, ... }` so the FE groups them under the right worker.
- `subagent_done` — **wire schema** (`stream_events.py`): `{ subagentId, label?, role?, costUsd?, outcome?, attribution?, substitution?, … }`. **As-built emission:** orchestrator/handler still primarily send cost + split substitution fields; full nested `ModelAttribution` on the live frame and distinct failure `outcome` rendering remain partial until encoder + FE parse land together (persist path already builds nested attribution on `SubagentPart`).
- `run_cost` — `{ subtotalUsd, capUsd, confidence?, phase?, … }`. **Orchestrator:** estimate @ plan pause (`confidence: estimate`, `phase: plan`), progress ticks as workers complete (`phase: progress`), final at completion. Confirm handler encode forwards `confidence`/`phase` and FE meter labels estimates — do not assume end-to-end until those layers match.
- `terminal` — `{ status: "done" | "awaiting_approval", messageId, attribution }` where `attribution.costUsd` is the **run total** when present. A plan-approval pause **emits a `terminal` with `status: "awaiting_approval"`** (same as a tool pause) carrying the plan decomposition and the **estimated** cost in `attribution` (`costConfidence: "estimate"`); the turn resumes via `toolApproval`. The estimate-vs-actual distinction is on `attribution.costConfidence`.
- `error` — unchanged envelope (PRD 08). A per-run budget halt produces a **partial synthesis** + `done`, not an `error` (graceful degrade, FR-26g). Partial labeling today is **prose in the answer**, not a typed PRD 08 warning chip.

### Persistence (additive part grouping)

`message.parts` (the typed union — `text | reasoning | status | sources | attachment | tool_call | tool_result`) gains a **subagent grouping**: subagent-scoped parts carry a `subagentId` and a new `subagent` marker part (`{ subagentId, label, role, attribution, costUsd }`) so a reloaded agentic turn replays which subagent produced which output. This is **additive to the discriminated union** (PRD 00 §11 D7), not a rewrite — non-agentic messages carry no `subagentId` and render exactly as today. The `JSONB` column already accepts the wider shape (per `00-backend-minimal.md` data-model notes); no migration to the column type, only new optional keys.

## Orchestration

The orchestrator (`api/app/agentic/orchestrator.py`, NEW) is a thin coordinator returning the same `AsyncIterator[ProviderEvent]` the handler already consumes — so the handler's *transport contract* is unchanged (the orchestrator is just another `ProviderEvent` source). The handler's accumulation is **not** unchanged: `_apply_event` / `_build_parts` gain subagent-grouping (additive — an un-tagged stream still folds into one default group). It:

1. **Plans.** For `deep_research`, a bounded planning step (itself a `run_agent_loop` over the orchestrator role) decomposes the prompt into ≤`AGENTIC_MAX_WORKERS` independent sub-questions. For `single`, planning is a no-op and the run is one loop (today's path).
2. **(Optional) pauses for plan approval.** If `AGENTIC_PLAN_APPROVAL` (or a per-turn flag) is set, emit `AwaitingApproval` at the plan boundary with the decomposition + estimated cost; the handler renders this as a `terminal` with `status:"awaiting_approval"` carrying the plan + estimate (`costConfidence:"estimate"`), resumed via `toolApproval`.
3. **Reserves + fans out.** **Pre-spawn admission control**: estimate the run's worst-case cost (Cost & budget methodology) and reserve it against the per-run cap + composed user/platform headroom; if the estimate already exceeds headroom, don't spawn (pause for approval or return an explained empty/partial synthesis). Otherwise spawn one worker `run_agent_loop` per sub-question via `asyncio.create_task` bounded by an `AGENTIC_MAX_CONCURRENCY` semaphore; merge their `ProviderEvent` streams (tagged with `subagent_id`) into an in-orchestrator queue. Each worker gets a scoped sub-prompt and a **scoped HITL tool allowlist** (`request_user_confirmation` + fake-only `calendar_create_event`); each is bounded by the shipped `TOOL_MAX_ROUNDS` + per-tool timeout.
4. **Enforces bounds.** A recursion-depth bound (default 1 orchestrator→worker level; workers do **not** spawn unbounded sub-trees — depth 1 by construction; runtime assert is target) and the per-run USD cap, checked against **worker actuals** from `pricing.py` as `SubagentDone` lands. On cap breach (**mid-flight kill**): stop spawning, cancel unfinished tasks, and proceed to aggregate the completed workers' outputs (partial synthesis, labeled in prose).
5. **Aggregates.** A synthesis step (a bounded subagent / `aggregator` role) composes the workers' outputs — **fed back only as structured data, never spliced into instructions** (transitive untrusted-output, FR-26i) — into the final answer streamed on the turn.
6. **(Optional) verifies.** If `AGENTIC_VERIFIER` is on (default off), run the **fresh-context judge** in `verifier.py`: emit `SubagentStarted` before the judge await, bill per-sample usage/cost, append a verification note/caveat to the manager-owned draft (never replace it with judge prose). `AGENTIC_VERIFIER_N` is the independent sample count (default 1, ≤5); majority is closed-form verdict only and requires the full sample set. Budget-short / parse-fail / truncated inputs stay unverified (honest incomplete/unavailable notes).
7. **Finalizes.** The handler computes the run-total attribution (with the as-built pricing caveats above), persists the subagent-grouped `parts`, and yields `terminal`.

**Invariants:**

- With `AGENTIC_ENABLED=false`, `run_orchestrator` is never constructed — `_resolve_provider_iter()` returns exactly the shipped raw/single-loop branches. Byte-identical.
- A worker's behavior (rounds, timeout, HITL, untrusted feedback) is exactly the shipped single-loop behavior — the orchestrator adds only fan-out/aggregate/bound/verify logic.
- A subagent's output is **untrusted** to its parent/aggregator (transitive SR-2); it never alters orchestrator system/safety behavior.
- Cancellation/Stop cancels all in-flight workers and flushes completed-worker partials (`status="stopped"`, `costConfidence="estimate"`), same as the single path.
- The run never escapes the turn: no state persists except the assistant message + its subagent parts.

## Cost & budget

Per-run cost reuses `api/app/providers/pricing.py` — no parallel cost model. The **intended** run total is the **sum of planner + workers + aggregator (+ real verifier when metered)**. Two multipliers are budgeted **separately** (FR-26g) so the cap is sized against their product, not either alone:

- **Reasoning-token multiplier** — thinking tokens are full-price, never cache-eligible; the 2026 research observed **~4–15× cost vs a non-reasoning turn** (PRD 02 FR-18, `[verify-at-build]`).
- **Multi-agent fan-out multiplier** — a multi-agent system burns materially more tokens than one chat turn; **Anthropic's multi-agent research reports ~15× the tokens of a single chat** (`[verify-at-build]`).

The per-run cap composes with the shipped user/platform budget caps (`USAGE_BUDGET_USD`, `preferences.monthly_budget_usd`, `preferences.per_conversation_budget_usd`) and PRD 08 `PLATFORM_CONVERSATION_CAP`. Breaching the per-run cap **degrades gracefully** (partial synthesis), never a hang or a silent overrun. BYOK runs are exempt from platform caps but still metered and capped per-run.

**Admission control (two gates, not just a post-hoc roll-up):**

- **Pre-spawn reservation.** Before fan-out, the orchestrator estimates the run's worst-case cost (see methodology below) and reserves it against the per-run cap *and* the composed user/platform headroom. If the estimate already exceeds available headroom, workers are **not spawned** — the run either pauses for plan approval (if enabled) or returns immediately with an explanatory partial/empty synthesis, never a silent overrun. Reservation is released/trued-up as actuals land. **As-built:** admission counts planner + workers + aggregator; when `AGENTIC_VERIFIER` is on, reserve judge-call estimates for funded samples (not phantom full workers).
- **Mid-flight kill.** Because reservation is only an estimate, actual cost is checked against the cap as each **worker** `SubagentDone` lands. On breach, the orchestrator cancels unfinished tasks and proceeds to aggregate whatever completed — the graceful-degrade path above. The orchestrator also yields a mid-run `run_cost` progress tick per worker done. Planner/aggregator spend folding and early-exit planner billing have known gaps (plan 02); when the verifier is on, per-sample judge costs fold into the meter.

**Cost-estimation methodology (drives the plan-approval estimate + the reservation):** the estimate is `Σ worker estimates + planner + aggregator (+ real verifier calls when metered)`, where each subagent's estimate is `expected_tokens × tier_price` from `pricing.py`, expected tokens derived from the planner's decomposition (sub-question count and per-worker round budget = `TOOL_MAX_ROUNDS`), then scaled by the two FR-26g multipliers (reasoning-token × fan-out) so the estimate is sized against their **product**. This same number is what the `awaiting_approval` terminal surfaces as the plan's estimated cost (`costConfidence: "estimate"`) and what the pre-spawn reservation holds. When `AGENTIC_VERIFIER` is on, include funded judge-sample estimates (not N phantom full workers).

## Observability

Agentic runs emit OpenTelemetry spans on the shipped env-gated path (`api/app/observability/tracing.py`, no-op when `OTEL_EXPORTER_OTLP_ENDPOINT` unset): **`invoke_agent`** spans on worker / primary / aggregator / quiet-planner / verifier paths (verifier is a sibling under the workflow, not a child of the aggregator). **`execute_tool_span` is wired** in `agent_loop.py` around tool execution. Spans carry ids + model/tier + token/cost rollups, **never message content** (matching the structured-log discipline). structlog already injects `trace_id` / `span_id` when a span is active, so a run's fan-out tree is correlatable in logs when spans are active.

## Config / flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `AGENTIC_ENABLED` | `False` | Master switch; inert unless `TOOLS_ENABLED` is also true. |
| `AGENTIC_MAX_WORKERS` | small (e.g. 4) | Max total subagents per run. |
| `AGENTIC_MAX_CONCURRENCY` | small (e.g. 3) | Max concurrent workers (semaphore). |
| `AGENTIC_MAX_DEPTH` | `1` | Recursion-depth bound (orchestrator→worker levels). |
| `AGENTIC_RUN_BUDGET_USD` | small | Hard per-run USD cap. |
| `AGENTIC_PLAN_APPROVAL` | `False` | Require plan approval (HITL) before fan-out. |
| `AGENTIC_VERIFIER` | `False` | Enable fresh-context verifier judge (provider-backed; default off). |
| `AGENTIC_VERIFIER_N` | `1` | Independent judge sample count (hard-capped at 5). Majority is closed-form ``pass``/``fail`` only; consensus pass requires all N samples. |
| `AGENTIC_RESUMABLE_BUFFER_MULTIPLIER` | `4` | Multiplies global resumable event/byte caps for agentic turns (`routes/conversations.py`). |

Estimation knobs (`AGENTIC_REASONING_TOKEN_MULTIPLIER`, `AGENTIC_FANOUT_TOKEN_MULTIPLIER`, per-round token expectations) live in `.env.example` / `config.py` — see there for defaults.

All validated at boot in `app/config.py`; all bounds are config, never hardcoded (mirrors the no-hardcoding discipline of PRD 02 §5).

## Remaining gaps (as-built vs PRD / plan 02)

Target architecture and gap ownership: [`02-agent-architecture.md`](./02-agent-architecture.md). This table is the build-plan view of **code truth today**.

| Gap | Status | Notes |
| --- | --- | --- |
| Per-subagent `ModelAttribution` + substitution | **PARTIAL** | **Persisted** on `SubagentPart`. **FE:** substitution callout renders from persisted attribution after reload; always-on served-model label, live-stream attribution parse, fuller requested→served+reason callouts remain open |
| `subagent_done` full attribution + outcome on wire | **PARTIAL** | Schema includes `attribution` / `outcome`; end-to-end encode + FE parse still catching up — persist path remains the reliable reload source |
| `execute_tool` OTel spans in `agent_loop.py` | **SHIPPED** | `execute_tool_span` wrapped around tool execution in `agent_loop.py` |
| Provider-backed verifier / self-consistency (FR-26j) | **SHIPPED (default off)** | Fresh-context JSON judge; per-sample cost; fail/budget/quorum semantics; CitationAgent still open |
| Per-worker provider failure degrade (PRD 08) | **SHIPPED (M4)** | A failed worker is omitted; the run still synthesizes + halts `done` with a "failed and were omitted" callout (`test_agentic_resilience.py`) |
| Per-worker provider fallback on 429/5xx | **SHIPPED (M4)** | Retryable worker error falls back to the secondary route, tagged `substitution` (`orchestrator.py`; `test_agentic_resilience.py`) |
| Heterogeneous fallback pricing / roll-up | **NOT BUILT** | Fallback labels/provider can substitute; cost + tier breakdown may still price on the original binding — verify against current orchestrator before claiming auditable |
| Mid-run `run_cost` ticks | **PARTIAL → closing** | Orchestrator emits plan / progress / final ticks with `confidence`/`phase` on the protocol event; keep handler encode + FE meter labeling honest before calling this fully shipped |
| Resumable-buffer sizing for high fan-out event volume | **SHIPPED (M4)** | Agentic runs multiply the caps by `AGENTIC_RESUMABLE_BUFFER_MULTIPLIER` (default 4) when opening the buffer (`routes/conversations.py`) |
| Live-network real-provider agentic E2E proof | **NOT BUILT (M4 gate)** | Deterministic no-network path covered (`test_agentic_real_provider.py`); true live-API E2E absent |
| Scoped per-worker tool subsets | **NOT BUILT** | Workers inherit full `advertised_tool_specs()` unless a concurrent allowlist lands |
| `AGENTIC_MAX_DEPTH` runtime enforcement | **PARTIAL** | Config validated at boot; depth 1 by construction (workers never nest), not checked at runtime |
| High-cost composer hint (FR-26f) | **NOT BUILT** | Toggle description only; no explicit cost warning |
| Share-view subagent rendering | **SHIPPED (partial)** | `SubagentPanel` on public shares; `PublicSubagentPart` keeps cost-stripped `PublicAttribution` when share projection is current |
| PRD 08 partial-synthesis warning chip | **PARTIAL** | Wire may carry partial flags on final `run_cost`; dedicated FE warning chip still open |
| Worker tool-HITL resume / approval idempotency | **SHIPPED** | BE-005 wait-siblings + continuation resume; BE-007 claim/settle on paused row |

## Open questions / decisions for the user

- **Decomposition quality.** Planner-driven decomposition is the hardest quality lever; the fake-provider v1 uses a deterministic decomposition so the engine can be tested before planner quality is tuned on a real provider.
- **Partial-synthesis labeling.** Budget-halt today appends inline prose ("answered N of M planned steps"); the open question is whether to add a dedicated `severity: "warning"` chip (PRD 08) vs keeping prose-only (leaning chip).
- **Per-subagent tool subsets.** Whether workers get the full tool registry or a scoped subset by default (leaning scoped, least-privilege per FR-26 / SR-2).

## Milestones

### M0 — Seam + flag + inert orchestrator — **SHIPPED**

Scope: `app/agentic/` scaffolded; `AGENTIC_ENABLED` + bound/budget flags in `app/config.py` (boot-validated, gated by `TOOLS_ENABLED`); the third branch in `streaming/handler.py::_resolve_provider_iter()` constructed **only** when both flags are on; bootstrap advertises the capability so the FE can show the (hidden-by-default) Deep-Research toggle. No fan-out yet.

Demo: with the flag off, every existing test passes byte-for-byte; with the flag on and `agenticMode:"single"`, behavior is identical to the shipped single loop. A CI assertion proves flag-off byte-identity (`test_agentic_flag_off.py`).

### M1 — Fake-provider single-loop-equivalent orchestrator — **SHIPPED**

Scope: `run_orchestrator` returns a one-worker run for `agenticMode:"single"`. This is **behavioral equivalence, not wire-identity**: same rounds/timeout/HITL/output as the shipped `run_agent_loop`, but the relayed events now carry a `subagentId` tag and the message gains one additive `subagent` marker part (N=1). Persistence groups the single subagent's parts; reload replays them. The strict **byte-identity guarantee holds only flag-off** (and for the raw/single-loop branches the orchestrator never touches) — M0's CI assertion covers that; M1 does **not** claim wire-identity for the flag-on `single` path.

Demo: `test_agentic_fanout.py::test_single_mode_wraps_one_primary_subagent`.

### M2 — Fake-provider Deep-Research fan-out + aggregate — **SHIPPED**

Scope: deterministic planner decomposition; `asyncio` fan-out to N bounded workers under the concurrency semaphore (`create_task` + gather); event multiplexing into the handler queue; the synthesis/aggregation step (untrusted-output discipline); `subagent_started` / `subagent_done` / `run_cost` events; subagent-grouped parts for N>1.

Demo: `test_agentic_fanout.py::test_deep_research_fans_out_workers_and_aggregates`; `web/tests/e2e/agentic.spec.ts`.

### M3 — Budget, plan-approval HITL, verifier judge, transparency + OTel — **SHIPPED (partials noted)**

Scope: per-run USD cap with **admission control** — a **pre-spawn reservation** against the cap + composed user/platform headroom and a **mid-flight kill** that cancels unfinished worker tasks on worker-actual breach, both ending in a graceful partial-synthesis halt; plan-approval pause that **emits a `terminal` with `status:"awaiting_approval"`** carrying the plan decomposition + estimated cost (`costConfidence:"estimate"`), resumed via `toolApproval`; the Pro/BYOK entitlement gate coercing non-entitled `deep_research` to `single`; fresh-context verifier judge (default off; config N); run-cost meter frames; `invoke_agent` OTel spans on worker/primary/aggregator/verifier.

**Partials vs this milestone's original scope (historical note — see Remaining gaps for current status):** at M3 cut, per-subagent attribution persistence and FE display were incomplete. **Current (post-M4 + hardening):** attribution **is persisted** on `SubagentPart`; FE substitution callout renders after reload; `execute_tool` spans are wired in `agent_loop.py`; the verifier is a **fresh-context judge** (default off; per-sample billed); mid-run `run_cost` progress ticks emit from the orchestrator (handler/FE honesty labels may still be catching up); live-stream attribution + always-on served model + heterogeneous fallback pricing remain open; `AGENTIC_MAX_DEPTH` is config-only (depth 1 by construction).

Demo: `test_agentic_budget.py`, `test_agentic_approval.py`, `test_agentic_safety.py`.

### M4 — Real-provider subagent wiring + hardening (gating prereq) — **PARTIALLY SHIPPED**

Scope: wire real providers (DeepSeek/OpenAI-compatible + Anthropic) as subagent backends through the same `run_agent_loop` real-provider tool path; **only after M1–M3 are proven on the fake provider** (FR-26d / D40). PRD-08 error envelope on every agentic path; structlog run/subagent keys; **net-new per-worker fallback** (degrade the 429'd/errored worker, keep the run — the shipped fallback is per-turn) and the rest of the concurrency-vs-rate-limit handling; the resumable-buffer sizing for high event-volume fan-out (`AGENTIC_RESUMABLE_BUFFER_MULTIPLIER`); document remaining gaps.

**As-built:** real-provider planner + model-written synthesis paths (`orchestrator.py` / `planner.py` / `aggregate.py`); per-worker fallback + failure-degrade (`test_agentic_resilience.py`); agentic resumable-buffer sizing; per-worker attribution persistence in `_build_agentic_parts`; a deterministic no-network real-provider path test (`test_agentic_real_provider.py`); fresh-context verifier judge (default off) + opt-in live verifier E2E. **Still open:** fuller attribution UX, heterogeneous fallback pricing (verify current code), broader live-network E2E — see **Remaining gaps** and plan 02.

Demo (target): a real-provider `deep_research` run fans out, aggregates, and bills correctly with full transparency; a forced provider error/429 on one worker degrades **that worker only**, not the run.

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
    verifier.py            # fresh-context judge (default-off; N-sample closed-form verdict)
    budget.py              # per-run USD cap + fan-out/depth bounds (reads providers/pricing.py)
  streaming/
    handler.py             # _resolve_provider_iter(): + run_orchestrator branch (gated)
  schemas/
    stream_events.py       # + subagent_started / subagent_done / run_cost; subagentId on existing
    message.py             # + subagent marker part (additive to the typed union)
    conversation.py        # + agenticMode on the send body
  config.py                # + AGENTIC_* flags (boot-validated, gated by TOOLS_ENABLED)
  observability/
    tracing.py             # + invoke_agent (wired in orchestrator) + execute_tool (wired in agent_loop)
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
- The orchestrator yields the same `ProviderEvent` union the handler already consumes, so the transport contract is unchanged; accumulation (`_apply_event` / `_build_parts`) becomes subagent-aware additively (un-tagged streams fold into one default group), and only the flag-off and raw/single-loop branches stay byte-for-byte unchanged.
