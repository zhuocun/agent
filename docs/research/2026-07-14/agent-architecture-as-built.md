# Olune shipped AI agent architecture — as-built audit

**Status:** Research provenance (**ARCHIVAL** as of 2026-07-18) for
[`docs/plans/02-agent-architecture.md`](../../plans/02-agent-architecture.md)  
**Pass index:** [README](./README.md)  
**Scope:** code + [`docs/plans/01-agentic-mode.md`](../../plans/01-agentic-mode.md) as of the 2026-07-14 architecture pass.  
**Verdict:** M0–M3 shipped behind flags; M4 partially shipped. Default path is still single-stream / single-loop; orchestrator is opt-in.

> **Archival note (2026-07-18):** This snapshot predates PRs #254–#258 and the
> residual fix pass. Do **not** treat §2/§7 claims about a no-op verifier stub,
> missing worker HITL resume, or missing approval idempotency as current.
> Prefer plan 02 + the live code for as-built truth. Kept for provenance of the
> 2026-07-14 design pass.

---

## 1. As-built topology

```
POST /api/conversations/:id/messages
  body.agenticMode?: "single" | "deep_research"
        │
        ▼
routes/conversations.py
  • coerce deep_research → single if !Pro && !BYOK
  • budget_headroom_usd for platform-key deep_research
  • resumable buffer × AGENTIC_RESUMABLE_BUFFER_MULTIPLIER when agentic
        │
        ▼
streaming/handler.py :: stream_and_persist
  agentic_active = TOOLS_ENABLED ∧ AGENTIC_ENABLED ∧ agentic_mode≠None
        │
        ├── agentic_active=false
        │     ├── tools off  → raw provider.stream
        │     └── tools on   → run_agent_loop(make_stream=raw)
        │
        └── agentic_active=true
              run_orchestrator(...)
                    │
                    ├── mode=single
                    │     SubagentStarted(primary)
                    │     → run_agent_loop(user_text)
                    │     → tag events w/ subagent_id
                    │     → SubagentDone + RunCost
                    │
                    └── mode=deep_research
                          plan (fake: decompose; real: quiet planner loop)
                          → optional plan-approval HITL (AwaitingApproval)
                          → budget.admit (pre-spawn)
                          → asyncio workers under Semaphore(MAX_CONCURRENCY)
                          │     each: run_agent_loop(worker_prompt)
                          │     optional fallback_make_stream on retryable error
                          │     mid-flight: SubagentDone cost → budget.exceeds_cap → cancel
                          → aggregate (fake: string synthesize; real: streamed loop)
                          → optional verifier stub note
                          → untagged Complete (summed usage) + RunCost
        │
        ▼
handler pump → SSE (subagent_started|done, run_cost, tagged deltas, terminal)
        │
        ▼
_build_agentic_parts → Message.parts (subagent markers + tagged children)
        │
        ▼
Neon Postgres (assistant message + attribution roll-up)
```

**FE (flag-gated):** bootstrap `agenticEnabled` → Deep Research toggle → `agenticMode:"deep_research"`; `SubagentPanel` + `RunCostMeter` on `run_cost` frames (orchestrator: estimate + mid progress + final; confirm FE confidence labeling).

---

## 2. Component inventory

| Path | Responsibility |
| --- | --- |
| `api/app/tools/agent_loop.py` | Bounded ReAct/tool loop: rounds, HITL pause, untrusted tool feedback, final suppress-tools pass |
| `api/app/tools/builtin.py` | Tool registry + `advertised_tool_specs()` + timeout-wrapped `execute_tool` |
| `api/app/tools/protocol.py` | Tool call/result/approval types |
| `api/app/agentic/orchestrator.py` | `run_orchestrator`: single wrap + deep_research plan/fan-out/aggregate/verify |
| `api/app/agentic/planner.py` | Deterministic `DEEP_RESEARCH:` decompose + real-provider plan prompt/parse + worker prompts |
| `api/app/agentic/aggregate.py` | Deterministic synthesis + real-provider synthesis prompt (untrusted DATA framing) |
| `api/app/agentic/verifier.py` | Deterministic honest no-op stub when flag on (no provider call; no "Verified…" claim); N reserved |
| `api/app/agentic/budget.py` | Worst-case estimate, `admit`, `exceeds_cap`, headroom composition (stub verifier adds 0 calls) |
| `api/app/agentic/retry.py` | `RATE_LIMITED` / `PROVIDER_UPSTREAM` retry predicate |
| `api/app/streaming/handler.py` | Seam `_build_provider_iter`; subagent accumulators; SSE encode; persist |
| `api/app/routes/conversations.py` | Entitlement coerce, headroom, resumable sizing, plan-approval resume short-circuit |
| `api/app/routes/bootstrap.py` | Advertises `agenticEnabled = AGENTIC ∧ TOOLS` |
| `api/app/schemas/stream_events.py` | Wire events + optional `subagentId` |
| `api/app/schemas/message.py` | Parts union + `SubagentPart` |
| `api/app/schemas/conversation.py` | Send-body `agenticMode` |
| `api/app/schemas/bootstrap.py` | `agentic_enabled` flag |
| `api/app/schemas/share.py` | Cost-stripped `PublicSubagentPart` |
| `api/app/providers/protocol.py` | Internal `ProviderEvent` union incl. Subagent*/RunCost |
| `api/app/observability/tracing.py` | `invoke_agent_span` (wired in orchestrator); `execute_tool_span` (wired in `agent_loop`) |
| `api/app/config.py` | All `AGENTIC_*` / `TOOLS_*` + boot validation |
| `web/src/components/chat/model-mode-picker.tsx` | Deep Research toggle |
| `web/src/components/chat/subagent-panel.tsx` | Per-worker activity + run-cost meter + substitution callout |
| `web/src/components/chat/agentic-assistant-parts.tsx` | Share-view renderer via `SubagentPanel`; chat uses `assistant-message.tsx`; shared layout in `agentic-layout.ts` |
| `web/src/lib/stream-client.ts` | Parses `subagent_*` / `run_cost` |
| `web/src/lib/agentic-layout.ts` | Parts → sections / main-bubble rules |
| `docs/plans/01-agentic-mode.md` | Build plan + remaining-gaps table (aligned to as-built / plan 02 intent) |
| `docs/plans/02-agent-architecture.md` | Normative target architecture (this audit grounds it) |

---

## 3. Control-flow phases (`deep_research`)

From `_run_deep_research` (`orchestrator.py:412–712`):

1. **Plan** — Fake / `DEEP_RESEARCH:` / declined resume → `planner.decompose`; else real → quiet planner + `parse_plan`
2. **Plan approval?** (`AGENTIC_PLAN_APPROVAL`) — Fresh: emit planner SubagentStarted, RunCost(estimate), pseudo ToolCall, AwaitingApproval; resume approve → continue; deny → labeled synthesis
3. **Admit** — `budget.admit`; reject → explained empty synthesis
4. **Fan-out** — concurrent workers under Semaphore; each `run_agent_loop`; events tagged
5. **Mid-flight budget** — on SubagentDone, exceeds_cap → cancel unfinished
6. **Aggregate** — synthesize (fake string or streamed model)
7. **Verify?** — if AGENTIC_VERIFIER, honest no-op stub (unchanged answer)
8. **Finalize** — aggregator SubagentDone, untagged summed Complete, RunCost (final)

`single` skips plan/fan-out: one `primary` loop.

---

## 4. Hard bounds (config key → enforcement)

| Bound | Key / default | Where enforced |
| --- | --- | --- |
| Tools master | `TOOLS_ENABLED=false` | Handler |
| Agentic master | `AGENTIC_ENABLED=false` | Handler; boot requires tools |
| Max workers | `AGENTIC_MAX_WORKERS=4` | planner truncate |
| Concurrency | `AGENTIC_MAX_CONCURRENCY=3` | Semaphore |
| Depth | `AGENTIC_MAX_DEPTH=1` | Boot + by construction |
| Per-run USD | `AGENTIC_RUN_BUDGET_USD=1.0` | admit + exceeds_cap |
| Plan HITL | `AGENTIC_PLAN_APPROVAL=false` | _maybe_plan_approval |
| Verifier | `AGENTIC_VERIFIER=false`, `N=3` | stub |
| Tool rounds | `TOOL_MAX_ROUNDS=4` | run_agent_loop |
| Tool timeout | `TOOL_TIMEOUT_SECONDS=10` | execute_tool |
| Pro/BYOK for DR | billing/BYOK | coerce to single |
| Resumable buffer | `AGENTIC_RESUMABLE_BUFFER_MULTIPLIER=4` | conversations route |

---

## 5. Event / wire contract

Request: `agenticMode?: "single"|"deep_research"`. Bootstrap: `agenticEnabled`. SSE additive: `subagentId`, `subagent_started`, `subagent_done`, `run_cost`. Roles: `primary`|`worker`|`aggregator`|`orchestrator`. Persistence: SubagentPart + tagged children.

---

## 6. Safety / HITL / degrade

Flag-off byte-identical. Untrusted worker outputs framed as DATA. Tool HITL inside workers. Plan HITL via toolApproval. Budget halt → partial synthesis + done. Worker failure → omit + continue. Disconnect ≠ cancel under resumable. Stop cancels the handler pump task; orchestrator cancels remaining `create_task` workers (no TaskGroup).

---

## 7. Shipped vs remaining gaps

Shipped: flag-off identity, M1–M3 fake, per-worker degrade/fallback, attribution persist, buffer×N, real planner/synthesis (no-network), share-view `SubagentPanel` (cost-stripped; `PublicAttribution` on public subagent parts when projection is current), substitution callout on reload, `execute_tool` OTel in loop, orchestrator mid-run `run_cost` progress ticks, honest verifier stub. NOT: live E2E, real verifier, tool subsets (unless allowlist lands), high-cost composer hint, full FE live attribution/always-on model, worker HITL resume, approval idempotency. Confirm handler encode forwards `run_cost` confidence/phase and `subagent_done` outcome/attribution before calling those end-to-end shipped.

---

## 8. Invariants

1. Flag-off byte-identical
2. Flag-on single ≠ wire-identical (behavioral reuse + tags)
3. Chat-anchored in-turn only
4. Reuse run_agent_loop
5. One seam `_build_provider_iter`
6. Additive accumulation
7. Untrusted transitive output
8. Budget halt → graceful done
9. Last untagged Complete wins for roll-up
10. AGENTIC requires TOOLS at boot
11. Disconnect ≠ cancel under resumable
12. Plan approval reuses toolApproval

---

## 9. Open design tensions

Honest no-op verifier stub (`AGENTIC_VERIFIER_N` reserved, not majority vote / not N provider samples / not billed); full tools for every worker unless subsets land; run_cost mid ticks vs FE confidence labeling; attribution UX partial (persist + reload callout yes; live/always-on partial); fake vs real dual contracts; quiet planner billing; depth knob inert; silent entitlement coerce; prod enablement gated on live E2E; **worker tool-HITL resume** and **approval idempotency** deferred hard gaps (plan 02 open questions 13–14).
