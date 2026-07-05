# Research — UX Best Practices for Agentic / Tool-Using AI UIs (R2)

**Author:** UX research worker (R2)
**Date:** 2026-07-05
**Scope:** Plan display & plan-approval (HITL); tool-call rendering (running/succeeded/failed, expandable args/results); subagent/worker progress; long-running task progress & cancellation; web-search grounding + sources/citations panel; model picker & tier selection; and the transparency contract (which model answered, per-message cost, silent-downgrade disclosure, reasoning/thinking display).
**Method:** Fresh online pass (2026) + grounding against `docs/prd/02-ai-capabilities.md`, `docs/prd/07-transparency-contract.md`, `docs/plans/01-agentic-mode.md`, `docs/research/2026-05-27/02-ai-capabilities-transparency.md`, and the shipped agentic components under `web/src/components/chat/`. Output rules follow R1: actionable/imperative/testable findings, a `platform` tag (`desktop`/`mobile`/`both`), a cited source, `[verify-at-build]` on date/version-sensitive claims, and an explicit note where **canon already covers** the practice.

> This is a findings memo only. It does not edit any doc under `docs/ux-best-practices/`.

---

## 1. Summary

- **The shipped surfaces are unusually close to 2026 best practice.** `tool-part.tsx`, `subagent-panel.tsx`, `sources-panel.tsx`, `reasoning-panel.tsx`, and `model-mode-picker.tsx` already implement the state-aware collapsible tool card, per-worker activity panel, inline-citation-to-source-card reveal, auto-open/auto-collapse reasoning, and progressive-disclosure model picker that the industry converged on. Most findings below are **gaps against the product's own canon** (PRD 07 §6.1 / PRD 02 FR-26h) or small enhancements, not rewrites.
- **The largest canon-vs-shipped gap is transparency of a downgrade.** PRD 07 §6.1 requires a served-vs-requested callout to name requested tier, served model, and reason; `attribution-row.tsx` renders only a bare "Rerouted" pill (the requested/served/reason detail lives in `aria-label` only). Best-practice sources say the *point of a substitution callout is to show the "why"* — the shipped pill under-delivers on the wedge.
- **The live per-run cost meter is specified but not rendered.** PRD 02 FR-26h and the agentic plan promise a live cost meter during a fan-out; `run_cost` SSE frames are parsed in `stream-client.ts` but `chat-thread.tsx` explicitly does not render them, and `subagent-panel.tsx` accepts `costUsd` but never shows it (per D41 row-badge removal). Cost legibility for long agent runs is a named 2026 open problem — the meter closes it and should ship.
- **Plan-approval shows the plan but hides the estimate.** `tool-part.tsx` renders the decomposition as a numbered list (good "evidence pack") but deliberately drops the parsed `estimatedCostUsd`/`capUsd`. 2026 HITL guidance is emphatic that an approval card must show enough to judge in seconds — a Deep-Research plan approval without its cost estimate invites rubber-stamping of the exact high-cost action the gate exists for.
- **Edit-before-approve is missing.** The HITL surface is approve/deny only. Multiple 2026 sources call approve-or-restart an anti-pattern that trains users to approve blindly; edit-then-approve is the recommended default for gated actions.
- **Two honesty behaviors already exceed most competitors:** the ungrounded marker ("Answered without live sources", `assistant-message.tsx`) and the reasoning panel that renders nothing when no trace is emitted. Keep both; they are the retrieval- and reasoning-side of the no-silent-downgrade through-line.

---

## 2. Findings table

Imperative, testable items. `Canon` = where the repo already covers the practice (✅ covered / ◑ partial / ✗ gap vs canon / ➕ net-new opportunity). Source keys map to §5.

### 2A. Plan display & plan-approval (HITL)

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| P1 | **Show the decomposed plan before fan-out as a legible list, not a JSON blob**; assert the plan-approval pause renders one numbered step per sub-question. | both | ✅ `tool-part.tsx` `PlanApprovalDetail` renders `plan[]` as `<ol>`; PRD plan "Plan-approval surface". | S1, S4, S6 |
| P2 | **Surface the run's estimated cost + per-run cap inside the approval card** (label `costConfidence: "estimate"`); assert the estimate is visible, not only on the wire. Today `estimatedCostUsd`/`capUsd` are parsed then dropped. | both | ✗ gap vs PRD plan ("plan + cost estimate in the pause card") and PRD 02 FR-26g; `tool-part.tsx` comment: "Cost fields are parsed … but not displayed". | S3, S5, S6 |
| P3 | **Allow edit-then-approve on a gated call, not just approve/deny**; assert a user can amend a proposed tool input (e.g. `run_code` source per FR-26a) before approving without restarting the run. | both | ◑ partial — approve/deny only in `tool-part.tsx`; FR-26a specifies "editable source, server-re-validated" but no edit affordance ships. | S2, S5 |
| P4 | **Keep the gated tool set small and gate by risk/blast-radius, not blanket-confirm**; assert low-risk read tools flow without a pause while side-effecting tools pause. | both | ✅ modeled on `needs_approval` per-tool (FR-26/FR-26a); no global "ask me" gate. | S1, S2, S5 |
| P5 | **Never treat a subagent's own message as user approval**; assert an injected "approved" string in worker output does not resume a paused gate. | both | ✅ transitive untrusted-output (PRD 02 FR-26i; `test_agentic_safety.py`). Reinforced by Claude Code's explicit rule. | S8, S9 |
| P6 | **Render an approval *receipt/audit* trace (who approved/denied, when) for gated actions**, retained for the message. Increasingly a compliance expectation (EU AI Act human-oversight evidence, effective 2026-08-02 `[verify-at-build]`). | both | ➕ opportunity — `approvalState` pill shows current state but no persisted receipt; activity log (`activity-dialog.tsx`) covers account events, not per-turn approvals. | S3 |

### 2B. Tool-call rendering (running / succeeded / failed, expandable args/results)

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| T1 | **Render every tool lifecycle state with a distinct icon + status word**: pending, running, awaiting-approval, succeeded, failed, cancelled (map to AI-SDK `input-streaming`/`input-available`/`approval-requested`/`output-available`/`output-error`/`output-denied` `[verify-at-build]`). Assert each state has a testable label. | both | ✅ `tool-part.tsx` `StatusIcon`/`statusLabel` cover all six; `ApprovalPill` covers denied/approved. | S7, S12 |
| T2 | **Auto-collapse settled tool runs behind a one-line summary; keep running & awaiting-approval expanded**; assert a succeeded run collapses and an awaiting-approval run stays open with reachable controls. | both | ✅ `tool-part.tsx` (`isTerminal` collapses; live states stay expanded). Matches AI Elements "auto-open completed" inverted to the repo's quieter default. | S7 |
| T3 | **Make args and results expandable but truncated at rest** (cap preview length; expand for full payload); assert a >180-char input renders truncated with a disclosure. | both | ✅ `tool-part.tsx` `previewJson` truncates to ~180 chars; `Collapsible` reveals detail. | S7, S12 |
| T4 | **Surface tool errors clearly and distinctly (destructive tint + error text), never swallow them**; assert a failed tool shows the error string, not a generic "done". | both | ✅ `tool-part.tsx` `destructive` styling + `part.error` in `detailBody`; web-search failures show `run.result.error`. | S7, S12 |
| T5 | **Coalesce a contiguous run of settled calls into one collapsed group** ("N calls · M failed") to keep the thread quiet; assert ≥2 settled runs render one `tool-group` panel. | both | ✅ `tool-group-panel.tsx`. Mirrors Claude Code's "collapse to a single `Queried {server}` line". | S9 |
| T6 | **Give every collapsible trigger an accessible name and a ≥44px touch target**; assert `aria-label` names the tool + status and the row clears the iOS 44pt floor. | both | ✅ `tool-part.tsx`/`tool-group-panel.tsx` (`aria-label`, `min-h-11`). | S7 |

### 2C. Subagent / worker progress

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| S1 | **Show per-worker rows with label, role, and running/done status in a dedicated activity panel** (not inline chat prose); assert each subagent renders a row with a status icon and role chip. | both | ✅ `subagent-panel.tsx` (`SubagentRow`, `roleLabel`, `Loader2`/`CheckCircle2`). Matches Anthropic orchestrator-worker + Claude Code `/agents` panel. | S8, S9, S10 |
| S2 | **Keep running rows expanded (live text streams in); collapse settled rows behind their summary**; assert a running worker shows "Working…" + streaming text and a done worker collapses. | both | ✅ `subagent-panel.tsx` (`isRunning` stays expanded; settled rows use `Collapsible`). | S9, S11 |
| S3 | **Show a live per-run cost meter during the fan-out** (rolling `subtotalUsd` vs `capUsd`); assert the meter updates as `run_cost` frames arrive. Cost legibility for agent runs is a named 2026 open problem. | both | ✗ gap vs PRD 02 FR-26h + plan ("live per-run cost meter"); `run_cost` parsed in `stream-client.ts` but `chat-thread.tsx` does not render it and `subagent-panel.tsx` ignores `costUsd`. | S11, S3 |
| S4 | **Attribute each subagent's served model + any substitution per worker** (no silent downgrade inside a fan-out); assert a worker rerouted from its requested model shows its own callout. | both | ✗ gap vs PRD 02 FR-26h / PRD 07 §4.4; attribution is *persisted* per `SubagentPart` but `subagent-panel.tsx` renders only the turn-level `AttributionRow`. | S8 |
| S5 | **Never let a fan-out look stalled: show per-worker activity and fail a hung worker loudly** (elapsed-time hint; Claude Code errors a stalled subagent after 10 min `[verify-at-build]`); assert a worker that produces nothing still shows a progress affordance, not a frozen panel. | both | ◑ partial — panel shows running/done + "N of M running", but no per-worker elapsed time and no stall timeout in the FE. | S13, S14, S11 |
| S6 | **Title the panel honestly to its shape**: "Deep research" for a real fan-out, "Agent activity" for a single-loop run — never overclaim. | both | ✅ `subagent-panel.tsx` (`isDeepResearch` → title). | S8 |
| S7 | **Render the panel identically for the streaming turn and a reloaded transcript** (derive sections from persisted `subagent` parts when live activity is absent); assert a reloaded agentic turn replays which worker did what. | both | ✅ `assistant-message.tsx` (`buildSubagentSectionsFromParts` fallback). | S1 |

### 2D. Long-running task progress & cancellation

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| L1 | **Expose Stop as a first-class, always-visible control during a run; a stopped turn must flush partial work, not vanish**; assert Stop cancels in-flight workers and the bubble shows a "Stopped" marker with completed output retained. | both | ✅ Stop path + `StoppedChip` (`assistant-message.tsx`); orchestrator flushes completed-worker partials (`status="stopped"`, plan §"Cancellation across a fan-out"). | S15, S16, S17 |
| L2 | **On a budget/failure halt, degrade gracefully: synthesize partial results and label them, never silently give up**; assert a per-run cap breach yields a labeled partial answer + `done`, not an error or hang. | both | ◑ partial — budget halt labels inline prose (plan "Remaining gaps": PRD 08 partial-synthesis warning chip **not built**); recommend a dedicated `severity:"warning"` chip. | S15, S17 |
| L3 | **Show step/lifecycle progress (current step, activity) rather than a bare spinner**; assert the turn shows named status lines ("Searching the web…") while working. | both | ✅ `StatusLine` (`assistant-message.tsx`); `web-search-panel.tsx` live label. | S15, S17, S18 |
| L4 | **Treat a client disconnect as *not* a cancel when resumable streaming is on** — only explicit Stop cancels; assert closing the tab mid-run does not tear down the fan-out. | both | ✅ plan "Disconnect ≠ cancel" (`_NeverDisconnectedRequest`, `RESUMABLE_STREAMS_ENABLED`). | S16 |
| L5 | **Because the orchestrator is chat-anchored (in-turn, no background job), the "persistent status surface that survives tab close for hours" pattern is intentionally out of scope** — do not build a cross-session agent dashboard. Note the divergence so a reviewer does not read its absence as a gap. | both | ✅ deliberate — D23/D33 chat-anchored guardrail (PRD 02 §4.6). The 2026 "persistent surface" pattern targets background agents; not applicable here. | S15, S17 |
| L6 | **Add a per-run elapsed/duration signal** so a multi-minute Deep-Research run reads as progressing; assert a long run shows elapsed time. | both | ➕ opportunity — reasoning panel shows "Thought for Xs" but the run/worker level has no elapsed indicator. | S13, S14 |

### 2E. Web-search grounding + sources / citations panel

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| G1 | **Use the hybrid pattern: inline `[n]` markers in prose + a source-card list** (favicon · title · domain · snippet); assert a cited claim's `[n]` maps to a card. | both | ✅ `sources-panel.tsx` + inline markers via `MarkdownRenderer` `onCitationClick`→`revealSource`. Matches Perplexity/ChatGPT/Claude. | S19, S20, S21 |
| G2 | **Clicking an inline `[n]` opens the panel, scrolls to, and briefly highlights the matching card**; assert the reveal works even when the panel is collapsed. | both | ✅ `sources-panel.tsx` `revealSource` (`keepMounted` + pulse highlight). | S19, S23 |
| G3 | **Add a hover (desktop) / tap (mobile) preview on the inline marker** showing title + domain + snippet, so the reader need not scroll to the card; open the preview immediately on keyboard focus (no hover delay). | desktop+mobile | ➕ opportunity — inline marker reveals the card but has no lightweight hover/tap tooltip preview. | S19, S20, S22, S23 |
| G4 | **Mark an ungrounded turn honestly**: a search-requested turn that resolves zero usable sources shows a calm "Answered without live sources", never an implied-cited answer; assert the marker appears on an empty-result fixture and is absent on a grounded one. | both | ✅ `assistant-message.tsx` `UngroundedMarker`; PRD 07 §4.3 (shipped #143). Exceeds most competitors. | S1(canon), S17 |
| G5 | **Never render a model-generated URL as a source — only retrieved metadata — and never render a non-http(s) scheme as a clickable link**; assert a `javascript:`/`data:` URL renders as inert text. | both | ✅ `sources-panel.tsx` `isHttpUrl` gate (belt-and-suspenders on the public share view). | S21 |
| G6 | **Label source provenance** ("From the web" / reserved: "From your documents" / "From a connector"); assert the provenance line renders per turn. | both | ✅ `sources-panel.tsx` `provenanceLabel`; PRD 07 §4.3 origin enum. | S19, S21 |
| G7 | **Markers must be real anchors announced as links, and copy-to-clipboard should preserve citation references**; assert screen readers announce "link" on `[n]` and copied markdown keeps the refs. | both | ◑ partial — inline reveal is wired; verify SR semantics of the `[n]` chip and that copy preserves refs (`markdown-renderer.tsx`/`message-actions.tsx`). | S22, S23 |
| G8 | **Keep the source list collapsed at rest post-stream** (progressive disclosure), summarizing as "N sources"; assert the panel is collapsed by default after the turn settles. | both | ✅ `sources-panel.tsx` (`defaultOpen=false`, "N sources" trigger). | S19 |

### 2F. Model picker & tier selection

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| M1 | **Put model/tier selection in the composer (web) / at the top of the conversation (mobile), reachable before send**; assert the trigger sits in the composer toolbar and shows the selected tier. | desktop+mobile | ✅ `model-mode-picker.tsx` trigger in composer toolbar; PRD 07 §6.2. Matches ChatGPT's 2026-06-10 picker move `[verify-at-build]`. | S24, S25, S26 |
| M2 | **Present tiers as a plain-language difficulty/effort scale, not raw model IDs**; assert tier rows show human labels with the concrete model as secondary meta. | both | ✅ `model-mode-picker.tsx` `TierRow` (label + `tierMeta`); `tier-picker.tsx`. Matches ChatGPT Instant/Medium/High reframing `[verify-at-build]`. | S24, S25, S26 |
| M3 | **Offer an "Auto" route and show the *actual* served route post-turn** (auto-routing is a request, resolved server-side); assert an Auto turn's attribution names the concrete tier that answered. | both | ✅ `"auto"` tier + `attribution-row.tsx` `assertServedTier` (loud failure if `auto` leaks as served). PRD 07 §6.2. | S24, S25 |
| M4 | **Use progressive disclosure: lead with the tier choice; tuck provider, reasoning-effort, and data policy behind "Advanced"**; assert the picker opens showing only tiers + primary toggles. | both | ✅ `model-mode-picker.tsx` (`Advanced` collapsible, parity across dropdown/sheet). | S24, S27 |
| M5 | **Show a value hint (cheapest capable route) and per-effort cost/latency trade-off — as a label that never auto-changes the selection**; assert a "Cheapest" badge and "Cost X · Latency Y" meta render. | both | ✅ `model-mode-picker.tsx` `cheapestAvailableTierId` badge + `effortMeta`. Matches "show the trade-off before a max pick". | S27, S28 |
| M6 | **Omit the reasoning-effort section entirely when the served provider ignores it** (e.g. flat providers), rather than showing disabled rows; assert the section is absent when `effortSupported=false`. | both | ✅ `model-mode-picker.tsx` (`effortSupported` gate). | S28 |
| M7 | **Frame reasoning-effort as a hint the provider may override** (2026 providers auto-route whether to think), so it is not presented as a hard switch. | both | ➕ opportunity — picker treats effort as deterministic; add copy/label acknowledging provider auto-decision. `[verify-at-build]` | S24, S26 |
| M8 | **Badge each route's data policy / residency in the picker** so a privacy-sensitive user can switch; assert the selected route shows its `data_policy` label. | both | ✅ `model-mode-picker.tsx` `DataPolicyRow`/Data-policy sheet section; PRD 02 §5.3. | S26 |

### 2G. Transparency contract (which model answered · cost · silent-downgrade · reasoning)

| # | Finding (imperative, testable) | Platform | Canon | Source |
|---|---|---|---|---|
| X1 | **Show the served model/tier on every assistant message without hover**; assert a finished turn shows the tier label at rest (not only in `aria-label`). | both | ◑ partial — `attribution-row.tsx` shows the *tier* at rest but the concrete `servedModelLabel` is `aria-label`-only. PRD 07 §6.1 says "served model/tier without hover". Confirm tier-only satisfies canon or surface the model label. | S29, S32 |
| X2 | **A substitution must render a visible callout naming requested tier, served model, and reason** — the bare "Rerouted" pill is insufficient; assert the callout (expanded or inline) exposes requested→served + reason text, not just an icon. | both | ✗ gap vs PRD 07 §6.1/§5 ("callouts include requested model/tier, served model/tier, and reason"); `attribution-row.tsx` renders only a "Rerouted" pill (detail in `aria-label`). | S29, S30 |
| X3 | **Never silently serve a different model** — any non-null substitution reason must produce UI; assert a forced `rate_limited`/`auto_downgrade`/`capacity_reroute` fixture renders a callout. | both | ✅ (mechanism) PRD 07 §5 AC + backend emits 6 reason codes; pairs with X2 for the *content* of the callout. | S29, S30 |
| X4 | **Keep per-turn cost out of the thread but expose a per-message "View spend" affordance** into the Spend hub; assert every finished turn links to spend and shows no inline cost figure. | both | ✅ decision (Option B / D41, PRD 07 §6.1 / AC#9). Verify the View-spend link is present on `assistant-message.tsx` finished turns. | S17(cost-legibility rationale) |
| X5 | **Render reasoning only when a trace is emitted; default collapsed post-stream with a "Thought for Xs" summary; auto-open while streaming; keep the answer visually primary**; assert no empty reasoning panel renders when no trace exists. | both | ✅ `reasoning-panel.tsx` (auto-open streaming, auto-collapse settled, "Thinking…"/"Thought for Xs"). Matches Cloudscape/LangChain/uipotion. | S31, S33, S34 |
| X6 | **Treat displayed reasoning as a processed summary, not a faithful transcript** — do not imply it is the model's literal computation (most 2026 providers summarize/redact; DeepSeek exposes raw thinking `[verify-at-build]`). Consider a subtle "summary" affordance where the provider summarizes. | both | ➕ opportunity — panel shows reasoning text with no summary/verbatim distinction. | S35, S33, S36 |
| X7 | **Use `aria-expanded`/`aria-controls` and visual differentiation on the reasoning disclosure so it is never confused with the answer**; assert the toggle exposes expand state to AT and the reasoning is visually distinct (muted/italic). | both | ✅ `reasoning-panel.tsx` (Collapsible primitive; muted styling); confirm `aria-expanded` is emitted by the Base UI trigger. | S34, S36 |
| X8 | **BYOK turns read "billed to your key" with no platform markup, and do not decrement platform budget**; assert a BYOK turn shows the key indicator and the usage meter reads BYOK. | both | ✅ `attribution-row.tsx` BYOK clause + `usage-meter.tsx` BYOK branch; PRD 07 §6.3. | S29 |
| X9 | **Make the usage meter call out near-limit / exhausted before a request fails** (warning→critical→exhausted), speaking in USD when a spend cap binds; assert the meter escalates tone at 80%/95%/100%. | both | ✅ `usage-meter.tsx` (`WARN`/`CRIT`/spend thresholds, `formatUsdMeter`). | S17, S29 |

---

## 3. Platform split

Most agentic/tool UI practices are **platform-agnostic** because the repo renders one component tree and splits only the *disclosure surface* by modality (dropdown on desktop, bottom sheet on mobile — `model-mode-picker.tsx`/`tier-picker.tsx`). The genuinely platform-specific calls:

**`both` (default — same behavior, verify at both widths):**
- All tool-call, subagent, long-running-progress, cancellation, grounding-honesty, reasoning, and transparency findings (P1–P6, T1–T6, S1–S7, L1–L6, G1–G2/G4–G8, M2–M8, X1–X9). These are logic/semantics, not layout, and must be asserted at desktop and mobile widths.

**`desktop`-leaning:**
- **G3 hover preview** on inline `[n]` markers — hover is the desktop idiom; pair with a tap equivalent on touch. Open on keyboard focus with no delay (a11y) — do not gate the preview behind a 300 ms hover on focus. Cite S22/S23.
- Dense multi-worker subagent panels (S1/S5) have room for per-worker elapsed time + current-tool lines on desktop; on mobile, cap visible rows and scroll (Claude Code caps at 5 rows with scroll hints `[verify-at-build]`, S13).

**`mobile`-leaning:**
- **M1 placement**: mobile picker belongs at the top of the conversation / in a bottom sheet within thumb reach; the composer-anchored dropdown is the desktop form. `[verify-at-build]` against the current ChatGPT split. Cite S24/S25.
- **G3 / P3 controls** must meet the 44pt touch floor and use tap-to-expand rather than hover; approval + edit controls especially (the repo already applies `min-h-11` on coarse pointers — keep it for any new controls). Cite S19/S23.
- Reasoning/subagent panels should stay collapsed at rest on mobile to protect vertical space (X5/S2 already do). Cite S33/S34.

**Divergence to flag (not a gap):** the 2026 "persistent status surface that survives tab close" pattern (L5) is intentionally not built — the orchestrator is chat-anchored (D23/D33). This is a deliberate scope line, `both`.

---

## 4. Open questions

1. **Substitution callout depth (X2).** How much of requested→served+reason should be visible at rest vs behind a tap/expand? Best practice says show the "why"; the wedge says never hide a downgrade — but the thread should stay quiet. Options: (a) inline reason word next to "Rerouted", (b) tap-to-expand detail popover, (c) always-visible one-liner. Product decision.
2. **Live run-cost meter placement (S3).** Where does the rolling `subtotalUsd`/`capUsd` render — inside the `SubagentPanel` header, as a status line, or a composer-adjacent chip — given D41 removed per-row cost badges and the thread defers per-message cost to the Spend hub? Reconcile "cost visible during a run" (FR-26h) with "no per-turn cost in thread" (Option B).
3. **Plan-approval estimate display (P2).** Show the estimate as a single USD figure, a range, or a "≈N steps × tier" breakdown? And should it appear only when `AGENTIC_PLAN_APPROVAL` is on, or always for `deep_research`? `[verify-at-build]` the estimate's confidence labeling.
4. **Edit-before-approve scope (P3).** Which gated tools get an editable payload first — just `run_code` (FR-26a), or any side-effecting tool? Edit adds a re-validation round-trip; scope it to high-blast-radius tools initially.
5. **Reasoning-summary honesty (X6).** Does the product label reasoning as a summary universally, or only for providers that summarize (OpenAI/Anthropic/Gemini) while leaving DeepSeek's raw thinking unlabeled? Depends on the served route — needs registry signal. `[verify-at-build]` per-provider reasoning-visibility mode.
6. **Per-subagent attribution display (S4).** Render each worker's served-model/substitution as a per-row chip, or only surface it on a rerouted worker (exception-only) to keep the panel quiet? Data is already persisted on `SubagentPart`.
7. **Inline citation preview vs reveal (G3).** Is the current click-to-reveal-card enough, or is a hover/tap preview worth the tooltip complexity and mobile positioning cost? Measure citation click-through before adding.
8. **Elapsed-time granularity (L6/S5).** Per-run only, or per-worker? And what threshold triggers a "still working" reassurance vs a stall warning (Claude Code uses 10 min `[verify-at-build]`)?

---

## 5. Sources

All accessed 2026-07-05 unless noted. `[verify-at-build]` flags in the tables mark facts (dates, version labels, provider behaviors) likely to drift.

- **S1** — Smashing Magazine, "Designing For Agentic AI: Practical UX Patterns For Control, Consent, And Accountability" (Feb 2026). https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/
- **S2** — AI/TLDR, "Human-in-the-Loop UX: Designing AI Approvals." https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/human-in-the-loop-ux/
- **S3** — Agent Native, "Human-in-the-Loop Approval Flow Pattern for AI Agents (2026)" (EU AI Act human-oversight, 2026-08-02). https://www.agentnative.dev/patterns/human-in-the-loop-approval-flow-pattern
- **S4** — Thiago Patriota, "UX Patterns for Agentic AI: 16 Essentials for 2026" (risk matrix, plan preview, anti-patterns). https://library.thiagopatriota.com/blog/ux-patterns-for-agentic-ai-guide
- **S5** — Boundev, "Human-in-the-loop approval for AI agents" (show payload+reason; edit/reject; in-the-loop vs on-the-loop; monitor approval rates). https://www.boundev.ai/blog/human-in-the-loop-approval-ai-agents-saas
- **S6** — LangGraph `interrupt`/`Command(resume=...)` HITL primitive (via S1/S2 synthesis and LangGraph docs).
- **S7** — Vercel AI Elements, `Tool` component (states, auto-open completed, collapsible, a11y). https://elements.ai-sdk.dev/components/tool
- **S8** — Anthropic, "How we built our multi-agent research system" (orchestrator-worker; CitationAgent; plan saved to memory; parallel subagents). https://www.anthropic.com/engineering/multi-agent-research-system
- **S9** — Claude Code changelog (subagent panel: idle auto-hide 30s, cap 5 rows scroll hints; MCP collapse to `Queried {server}`; transcript with tool results + live progress). https://code.claude.com/docs/en/changelog
- **S10** — GitHub anthropics/claude-code #48246, "Show agent/subagent task progress in terminal UI" (per-subagent name/status/elapsed/current tool). https://github.com/anthropics/claude-code/issues/48246
- **S11** — Creative Alive, "Designing for Agentic UI: 5 Patterns for AI-Run Workflows (2026)" (persistent status surface; trust checkpoint; end-of-run summary; never silently give up; cost legibility open problem). https://creativealive.com/designing-agentic-ui-5-patterns-ai-workflows-2026/
- **S12** — Vercel AI SDK 6 Deep Dive (four-stage tool lifecycle; discriminated error shapes). https://www.digitalapplied.com/blog/vercel-ai-sdk-6-deep-dive-features-tool-calls-2026
- **S13** — Claude Code Changelog mirror, claudefa.st (stalled subagent error after 10 min; `/agents` Running tab + live count; inline thinking spinner). https://claudefa.st/blog/guide/changelog
- **S14** — GitHub anthropics/claude-code #24580, "background agent progress visibility / subagent status indicators." https://github.com/anthropics/claude-code/issues/24580
- **S15** — Fuselab Creative, "Agent UX: UI Design for AI Agents in 2026" (activity panel separate from chat; step-level intervention; timeline survives interruption). https://fuselabcreative.com/ui-design-for-ai-agents/
- **S16** — Agent Patterns Catalog, "Interruptible Agent Execution" (pause/resume/cancel first-class + visible; cancel runs compensating actions; forbids start+kill only). https://www.agentpatternscatalog.org/patterns/interruptible-agent-execution/
- **S17** — WebDesignerIndia (Medium), "AI Agents in UX Design: New Rules for 2026" (override at point of action; design failure state first; measure recovery). https://webdesignerindia.medium.com/how-ai-agents-are-rewriting-ux-design-rules-in-2026-73ed56e4b5b6
- **S18** — uipotion, "AI Response Rendering Pattern — Streaming, Tool Calls, and Optional Reasoning." https://uipotion.com/potions/patterns/ai-response-rendering
- **S19** — AI/TLDR, "How to Show Citations in AI Answers (UX + Code)" (inline superscript + source cards; hover preview; cap 2–5; tap-to-expand mobile). https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/ai-citations-sources-ux/
- **S20** — Geodocs.dev, "AI Citation Format Specification by Engine (2026)" (ChatGPT/Perplexity/Gemini/Claude rendering). https://geodocs.dev/reference/ai-citation-format-spec-by-engine
- **S21** — RedHop, "RAG citations: how Perplexity and ChatGPT do it" (hybrid inline+bibliography; never model-generate URLs). https://www.redhopai.com/guides/rag-citations/
- **S22** — YPAI Design System, "Footnote" (markers as real anchors; `aria-describedby` to popover; focus opens tooltip immediately; back-link). https://ypai.ai/design/components/footnote/
- **S23** — Koder Meta, "AI citations / source attribution" (copy preserves citations; `role=tooltip` on hover / `role=dialog` on tap; keyboard nav). https://meta.koder.dev/specs/ai-ui/citations/
- **S24** — OpenAI Help Center, ChatGPT Release Notes, "Simplified controls in the model picker" (2026-06-10; picker in composer/top-of-conversation; Instant→Medium auto-switch). `[verify-at-build]` https://help.openai.com/en/articles/6825453-chatgpt-release-notes
- **S25** — AI News Briefs (PersonaStack), "Reasoning Becomes a Button: ChatGPT's New Picker" (2026-06-10). https://ainews.personastack.ai/posts/chatgpt-reasoning-effort-product-ux-2026
- **S26** — reconnAI, "ChatGPT's Simplified Model Picker: What the New Reasoning Tiers Mean." https://reconn-ai.com/news/chatgpt-model-picker-update-ai-visibility/
- **S27** — Thiago Patriota (S4) + progressive-disclosure guidance; corroborated by `model-mode-picker.tsx` Advanced-collapsible pattern.
- **S28** — bytelabs, "UX Patterns for AI Explainability and Trust" (show the trade-off; show input context / planned action / confidence / recovery path; don't dump raw CoT). https://www.bytelabs.space/blog/ux-patterns-for-ai-explainability-and-trust
- **S29** — Repo canon: `docs/prd/07-transparency-contract.md` §6.1–§6.3 (served model without hover; substitution callout content; BYOK; usage meter).
- **S30** — Repo canon: `docs/prd/07-transparency-contract.md` §5 substitution reason enum + AC.
- **S31** — Cloudscape Design System, "Thinking" pattern (expandable; collapsed by default in chat; expanded when response not primary). https://cloudscape.design/gen-ai/patterns/thinking/
- **S32** — Repo review of the 2026-05-27 core-chat UX research (`docs/research/2026-05-27/01-core-chat-ux.md`) — auto-open/auto-collapse reasoning; reasoning-effort coexists with provider auto-decisions.
- **S33** — uipotion (S18): surface reasoning only when exposed AND product decides; prefer summary/status; verbatim collapsed; answer visually primary; no placeholder surface.
- **S34** — LangChain docs, "Reasoning tokens" (collapsible `ThinkingBubble`; default collapsed; differentiate visually; `aria-expanded`/`aria-controls`; truncate preview). https://docs.langchain.com/oss/python/langchain/frontend/reasoning-tokens
- **S35** — PastAGI, "The End of AI Reasoning Transparency: When Chain of Thought Becomes a Summary" (displayed CoT is a processed summary, not a faithful transcript). https://pastagi.com/guides/ai-reasoning-transparency-hidden-chain-of-thought/
- **S36** — bytelabs (S28): keep enough detail for post-hoc analysis without exposing raw CoT; Anthropic/OpenAI guidance pushes toward summaries.
