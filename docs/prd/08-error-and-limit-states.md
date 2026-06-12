# PRD 08 — Error & Limit States

**Product:** Transparent, multi-model, cost-leading AI chat (web + mobile-web first).  
**Owner:** Product (Core UX + Platform Policy).  
**Status:** Draft for build.  
**Date:** 2026-05-27.  
**Related PRDs:** [00 Overview](00-product-overview.md) · [01 Core Chat](01-core-chat-experience.md) · [02 AI Capabilities](02-ai-capabilities.md) · [03 Mobile](03-mobile-cross-platform.md) · [04 Architecture](04-technical-architecture.md) · [05 Roadmap/Monetization](05-roadmap-monetization-metrics.md) · [06 Design System](06-design-system-visual-spec.md) · [07 Transparency Contract](07-transparency-contract.md).

> **What this document is.** A unified catalog of failure, quota, degradation, BYOK, and offline UX for P0. It complements PRD 01 stream states, PRD 03 flaky-network behavior, PRD 04 transport/rate limits, PRD 05 monetization caps, and PRD 07 transparency/substitution rules.

---

## 1. Purpose

Power users judge products by what happens when things go wrong. Multi-provider routing guarantees provider errors; metered economics guarantee cap hits; mobile-web guarantees flaky networks. This PRD makes those states:

- typed and instrumented,
- actionable,
- transparent,
- accessible,
- consistent across desktop and mobile-web.

---

## 2. Goals & non-goals

### Goals
- Define one error/limit taxonomy shared by API, client, analytics, and docs.
- Preserve partial assistant output on Stop/failure where possible.
- Explain limits before hard blocks.
- Convert guest limits into account-upgrade without data loss.
- Separate substitution callouts from true errors.

### Non-goals
- Provider-specific SDK runbook.
- P1 tool/HITL error flows beyond reserved codes.
- Enterprise admin incident console.
- Legal final copy for minors/companion personas.

---

## 3. Canonical error payload **[P0]**

```json
{
  "error": {
    "code": "PLATFORM_BUDGET_EXCEEDED",
    "severity": "blocking",
    "title": "Daily limit reached",
    "body": "You've reached your daily free-message limit.",
    "actions": [
      { "type": "upgrade", "label": "Upgrade to Pro" },
      { "type": "byok", "label": "Use your API key" }
    ],
    "retry_after_ms": 21600000,
    "meta": {
      "used": 50,
      "limit": 50,
      "reset_at": "2026-05-27T18:00:00Z"
    }
  }
}
```

All user-visible errors expose `code`, `severity`, `title`, `body`, and `actions[]`. New action types must degrade gracefully.

**Counts and reset time are structured data, not free text.** Limit counts and reset/retry information live in `meta` (`used`, `limit`, `reset_at`) and `retry_after_ms`, **not** baked into the `body` string — this keeps them localizable (i18n is a P0 baseline) and live. The client composes the displayed copy from these fields (e.g., "You've used {used}/{limit} free messages today. Resets in {countdown}."). `body` remains a **plain-text fallback** for when structured fields are absent or a client cannot compose copy.

---

## 4. Severity and UI pattern

| Severity | Default pattern | Example |
|---|---|---|
| `info` | Inline hint / meter text | 70% quota used |
| `warning` | Composer banner | 90% quota used |
| `error` | Inline message error + retry | Stream failed |
| `blocking` | Modal or disabled send + CTA | Hard cap, invalid BYOK key |

Visual primitives are defined in PRD 06; copy and actions are owned here.

---

## 5. Error code families **[P0]**

### 5.1 Stream / client

| Code | Trigger | Actions |
|---|---|---|
| `STREAM_FAILED` | SSE error mid-generation | Retry, Regenerate, Copy partial |
| `STREAM_TIMEOUT` | No first token by soft timeout | Stop, Retry, Change tier |
| `STREAM_STOPPED` | User Stop | Regenerate, Copy partial |
| `STREAM_CONFLICT` | 409 active stream in chat | Wait, Stop active stream |

### 5.2 Network / mobile

| Code | Trigger | Actions |
|---|---|---|
| `NET_OFFLINE` | Send while offline | Queue, Retry when online |
| `NET_INTERRUPTED` | Drop mid-stream | Continue, Regenerate, Copy partial |
| `NET_SYNC_FAILED` | Queued operation failed | Retry, Copy draft |

P0 Continue is a new continuation request; it is **not** P1 resumable replay.

### 5.3 Provider

| Code | Trigger | Actions |
|---|---|---|
| `PROVIDER_RATE_LIMIT` | Provider 429 | Retry later, Switch tier, BYOK |
| `PROVIDER_TIMEOUT` | Upstream timeout | Retry, Switch tier |
| `PROVIDER_ERROR` | Upstream 5xx/unknown | Retry, Status link |
| `PROVIDER_QUOTA` | BYOK/provider account quota | Check provider account/key |

> **`PROVIDER_ERROR` "Status link" target (resolves §13 #4).** The "Status link" action points at the public platform status surface — `GET /api/status` (unauthenticated, like `/api/share/{token}`) — described in §10 and owned by the F6 incident/status work. The surface reports per-provider-route operational state (operational / degraded / down) derived from recent `Stream` terminal-event error/fallback rates over a window plus a short incident list; no third-party status vendor is used for v1, and no per-user data or secrets are exposed. When the *active* route is degraded, an in-app degraded-provider banner (`role="status"`, dismissible per session, reusing the §5.7 substitution copy and linking to the model directory to switch routes) appears alongside the per-message substitution callout — extending "never silently downgrade" from the model to platform health. With telemetry insufficient (cold start), the surface reads "operational" rather than fabricating an incident. (Cite D30.)

### 5.4 Platform limits

| Code | Trigger | Actions |
|---|---|---|
| `PLATFORM_RATE_LIMIT` | Request/token window | Wait `retry_after`, Reduce usage |
| `PLATFORM_BUDGET_EXCEEDED` | Rolling USD/message cap (enforcement uses the LOWER of the platform `USAGE_BUDGET_USD` and the per-user `monthly_budget_usd`, composed in `api/app/db/repositories/usage.py::_effective_quota_usd`; a positive credit balance extends the cap) | Upgrade, Add credits, BYOK |
| `PLATFORM_BUDGET_WARNING` | Threshold alert at a configured % of `effective_quota_usd` (e.g. 50/80/100%) or low credit-balance runway | (transparency callout, not a block) View usage, Adjust budget |
| `PLATFORM_BUDGET_SOFT_CAP` | Soft-cap mode reached its ceiling; opt-in alternative to the hard `PLATFORM_BUDGET_EXCEEDED` block | (acknowledge-to-continue, not a block) Continue this period, View usage, Add credits |
| `PLATFORM_CONVERSATION_CAP` | Optional per-conversation USD ceiling exceeded on a single thread | Raise this chat's cap, Start new chat, BYOK |
| `PLATFORM_TIER_GATED` | Model/tier not available | Upgrade or pick available tier |
| `PLATFORM_GUEST_DOWNGRADE` | Guest moved to a weaker model after good-model allotment | (transparency callout, not a block) Sign up to keep the better model |
| `PLATFORM_GUEST_LIMIT` | Anonymous cap (hard sign-up wall) | Sign up / sign in |

> **Proactive budget guardrails (E6 — layered over the shipped hard gate; default behavior unchanged).** The shipped budget cap is a hard binary gate: at the cap the next platform turn 429s `PLATFORM_BUDGET_EXCEEDED` (`routes/conversations.py`). E6 adds three opt-in limit states *beside* it without altering that default.
> - **`PLATFORM_BUDGET_WARNING` (warn before the wall, `severity: "warning"`).** Fires once per threshold per period (deduped) at user-configured percentages of `effective_quota_usd` and on low credit runway. Continues generation; it is a pre-wall alert, not a block. Alerts deep-link into the §6 usage breakdown (E1) — "80% of your budget — DeepSeek Pro in 'X' is your top spender." In-app always; email is opt-in and off by default for registered users.
> - **`PLATFORM_BUDGET_SOFT_CAP` (soft cap warns + continues on acknowledgement, `severity: "warning"`).** **Opt-in only** per the user's `monthly_budget_usd`; when a user enables soft-cap mode, hitting the ceiling warns and lets them continue this period with one explicit acknowledgement rather than blocking. **The default remains the hard cap: with soft-cap mode off, `PLATFORM_BUDGET_EXCEEDED` preserves the current 429-blocking behavior byte-for-byte.** The acknowledge affordance is a single labeled action (no gesture-only dismissal).
> - **`PLATFORM_CONVERSATION_CAP` (per-conversation ceiling, `severity: "blocking"` for the one thread).** An optional ceiling on a single thread so a runaway long-context / agentic loop can't drain the month (relevant once tools/search are enabled — `TOOLS_ENABLED`, `SEARCH_BACKEND`). When exceeded it halts only that conversation's platform turns with a clear limit-state; other conversations are unaffected.
>
> BYOK turns are exempt from all platform caps (consistent with current enforcement) but may still receive *informational* spend estimates. (Cite D27.)

> **Guest model-downgrade transparency (distinct from the hard `PLATFORM_GUEST_LIMIT` block).** 2026 guest flows silently downgrade anonymous users to a weaker/mini model before the hard sign-up wall. For a transparency-first product, a **silent** downgrade is an own-goal. When a guest is moved to a weaker model, surface a **transparency callout reusing the substitution-callout** (PRD 06 §5.4 / PRD 07) — `severity: "info"`, not a block — naming the served model and the reason ("Now answering with Fast — sign up to keep the better model"). This is a transparency surface, **not** an error: `PLATFORM_GUEST_DOWNGRADE` continues generation; only `PLATFORM_GUEST_LIMIT` blocks send.

### 5.5 Auth / BYOK

| Code | Trigger | Actions |
|---|---|---|
| `AUTH_REQUIRED` | Feature needs account | Sign up |
| `BYOK_KEY_MISSING` | BYOK route selected without key | Add key |
| `BYOK_KEY_INVALID` | Test/decrypt/provider call fails | Re-enter key |
| `BYOK_KEY_REVOKED` | Soft-deleted key | Add new key |

### 5.6 Input / safety

| Code | Trigger | Actions |
|---|---|---|
| `SAFETY_BLOCKED` (alias `INPUT_MODERATION`) | Safety block | Edit message, Request review, Learn more |
| `INPUT_CONTEXT_EXCEEDED` | Over context pre-send | Shorten, Start new chat, Summarize when available |
| `INPUT_INVALID` | Schema/validation | Fix input |

> **Taxonomy reconciliation — `SAFETY_BLOCKED` is the as-built code; `INPUT_MODERATION` is its documented alias.** The shipped safety preflight emits `SAFETY_BLOCKED` (`routes/conversations.py::_safety_blocked`), while earlier drafts of this PRD named the same state `INPUT_MODERATION`. These are **one state, not two**: `SAFETY_BLOCKED` is the canonical, as-built code that the client must recognize; `INPUT_MODERATION` is retained only as its documented alias for cross-reference continuity. New clients key off `SAFETY_BLOCKED`. The block is gated by `SAFETY_BACKEND` (default `disabled`; `local` = operator blocklist); with `SAFETY_BACKEND=disabled` (the prod default today) no block fires and behavior is byte-identical.

#### 5.6.1 Transparent block + appeal **[Shipped — #145]**

The safety preflight (`safety/moderation.py::check_user_turn`) already computes a structured `SafetyDecision(allowed, reason_code, source)` where `source ∈ {message, attachment, custom_instructions}` and `reason_code = "configured_blocklist"`. Today the block surfaces with `severity: "warning"` but a **generic** body ("matched a configured safety rule") and no user-facing explanation or recourse. On a transparency-first product an opaque or silent block is an own-goal — the same failure the §5.4 guest-downgrade note calls out. F4 closes it by making the block transparent and appealable. **This is "never silently downgrade/modify" applied to safety: we never silently block or silently edit — we always surface a visible reason, and we offer recourse.**

- **Surface the category and source of the block** in the message UI as a `warning`/`info` callout styled per §5.7 substitution styling — **`severity: "warning"`, never `error`** (no red error banner). Example body composed from structured `meta`: "This message was held because it matched a safety rule on the message text. Edit and resend, or request a review." The displayed copy is composed from `meta` (`reasonCode`, `source`, optional operator-configurable `category` label) per the §3 structured-copy rule — **never a hard-coded English body**, and never leaking the exact blocklist terms (which would defeat the filter).
- **Request-review / appeal affordance** (lightweight): the callout offers ≤3 actions — Edit, Request review, and Learn more (links the content policy). Submitting an appeal writes an `AuditEvent` (`safety.appeal`) carrying the message id + the user's note (no raw blocked content beyond what the user re-submits) and returns a **confirmation, not an unblock** — there is no automated unblock in P1; operator review tooling trails to P2.
- **Output modification is transparent too.** If a future provider/gateway moderation adapter trims rather than blocks (the `safety/moderation.py` seam is shaped for this), show a transparency note — "Response was filtered by a safety policy" — never a silent edit.
- **Invariants preserved.** A blocked turn never persists an assistant message and never calls the provider (matches current preflight ordering). The callout uses `role="status"` (warning), is announced once, and all actions are keyboard-operable; on mobile-web the appeal is a small sheet with 44–48px tap targets and focus management on open/close. Block (`safety.block`) and appeal (`safety.appeal`) audit events feed the data-access activity log. (Cite D30.)

> **Ephemeral / temporary threads reject share and regenerate (F3).** An ephemeral or temporary conversation (per-conversation `expires_at` / the in-process temporary path) is non-persistent, so sharing it is incoherent: it **never mints a `share_token`** (a share request on such a thread is disabled / 400), and the regenerate / edit / continue message-actions remain rejected on temporary chats (matching the shipped in-process behavior). This is a constraint, not an error family of its own — surface it as a disabled affordance with a reason, consistent with the §7 limit-and-meter behavior. (Cite D31.)

### 5.7 Substitution is not an error

Served-vs-requested model changes use PRD 07 substitution callouts, not red error banners, unless combined with a blocking platform limit.

---

## 6. Copy rules

1. Lead with outcome: "Message couldn't finish" before technical cause.
2. State the limit: "12 of 50 free messages today" not just "quota exceeded." Compose the count from `meta.used`/`meta.limit` (structured, localizable), never from a hard-coded `body` string.
3. Offer 2–3 actions max.
4. Never blame the user for provider failures.
5. Preserve partial content; never imply it is lost if it is persisted.
6. Use substitution language for routing changes: "Answered with Fast because Pro was rate-limited."
7. **Show a live countdown / reset time** when a reset is known: drive it from `retry_after_ms` (relative) or `meta.reset_at` (absolute), rendering a ticking "Resets in {h}h {m}m" / "Try again in {s}s" that updates live and localizes — do not freeze a "Resets in 6h" string into `body`. The countdown surfaces on `PLATFORM_RATE_LIMIT`, `PLATFORM_BUDGET_EXCEEDED`, and `PROVIDER_RATE_LIMIT` states. When the countdown reaches zero, the blocking/wait state clears its disabled affordance.

---

## 7. Limit and meter behavior **[P0]**

| Threshold | UI |
|---|---|
| 0–79% cap | Meter only |
| 80–94% | info banner |
| 95–99% | warning banner + tier/BYOK nudge |
| 100% | blocking state; provider call not made |

Hard cap actions depend on account:

- Guest: a guest who exhausts the good-model allotment is **downgraded with a visible substitution callout** (`PLATFORM_GUEST_DOWNGRADE`, never silent) before the hard wall; at the hard wall (`PLATFORM_GUEST_LIMIT`), sign up to continue; preserve current thread.
- Free: upgrade, BYOK, wait until reset.
- Pro: add credits, BYOK, switch cheaper tier.
- BYOK: fix key/provider quota; do not upsell platform credits for provider-billed failures.

Per-conversation budget caps (E6 `PLATFORM_CONVERSATION_CAP`) follow the same meter thresholds above but scope the meter and the blocking state to the single thread (§5.4). **Ephemeral / temporary threads (F3)** present share and regenerate/edit/continue as disabled affordances with a visible reason rather than erroring — see §5.6; a non-persistent thread never mints a `share_token`.

---

## 8. Stream-state alignment **[P0]**

P0 state machine:

`idle -> submitted -> streaming -> done | stopped | error | interrupted`

- `stopped`: neutral chip; partial persisted.
- `error`: inline error; partial persisted when available; Retry/Regenerate.
- `interrupted`: partial persisted; Continue/Regenerate.
- `completed`: final attribution/cost is persisted and UI updates.

Terminal events feed PRD 05 analytics.

---

## 9. Accessibility **[P0]**

- Warnings use `role="status"`; blocking/errors use `role="alert"` only when immediate attention is required.
- **Announce model:** the streamed answer body is **not** an `aria-live` region; a **separate polite status region** announces discrete transitions ("Generating", "Response ready", "Stopped"). The streamed text node is never wrapped in a live region (avoids token-by-token re-reading).
- **Success-path completion announcement:** when generation completes normally, announce **once** ("Response ready") via the polite status region — the completed body is navigable but not auto-announced. (Implemented on the chat surface per PRD 01 §5.7; region defined in PRD 06 §3.5.)
- Stream errors are announced once when generation ends.
- Modals trap focus and return focus to the initiating control.
- All recovery actions keyboard-operable.
- Offline/queued status is visible and announced.

---

## 10. Phase boundaries

| Area | P0 | P1 | P2 |
|---|---|---|---|
| Stream fail/stop/timeout/409 | Yes | — | — |
| Provider 429/5xx | Yes | Automated fallback UX — **P1: Shipped (backend)** | — |
| Platform/guest/tier caps | Yes | Rich credit packs; budget alerts + soft-cap + per-conversation cap (E6) — **soft-cap + per-conversation cap Shipped (#144)** | Team/admin limits |
| BYOK errors | Yes | — | — |
| Offline queue + optimistic send | Yes | Background sync replay where supported | — |
| Resumable-stream Continue | Partial+Continue request | True replay — **P1: Shipped\* (`RESUMABLE_STREAMS_ENABLED`)** | — |
| Tool/HITL errors | Reserved | Yes — **P1: Shipped\* (`TOOLS_ENABLED`)** | — |
| Agentic-run errors (per-run budget halt → graceful partial synthesis; plan-approval pause) | — | — | **P2** (`AGENTIC_ENABLED`, gated by `TOOLS_ENABLED`): a per-run USD-cap breach degrades to a labeled partial synthesis (not an `error`); plan approval reuses the `awaiting_approval` terminal + `toolApproval` resume; a worker's provider failure degrades that subagent, not the run (PRD 02 §4.6 FR-26g, plans/01-agentic-mode.md) |
| Moderation appeals | — | User-facing transparency + appeal capture (F4 §5.6.1) — **Shipped (#145)** | Operator appeal-review tooling |
| Platform/provider status transparency | — | Public `/api/status` + `/status` page + degraded-provider banner (F6) — **Shipped (#145)** | — |

> **Shipped-on-`main` annotations (\* = behind a default-off flag; inert until enabled).**
> - **Provider 429/5xx → P1 Shipped (backend):** a single-shot, pre-first-token provider fallback is live (`api/app/routes/conversations.py::_select_fallback_route` + `streaming/handler.py`). It retries once on an alternate route for a retryable error (rate-limit / upstream) raised before any token, and records the substitution as `provider_fallback` (or `rate_limited`) per PRD 07 §5 — surfaced as a transparency callout, not a red error banner (§5.7). The automated *fallback UX* still belongs to the FE.
> - **Resumable-stream Continue → P1 Shipped\* (`RESUMABLE_STREAMS_ENABLED`):** true detached-producer replay + reconnect ships behind the default-off flag (prod additionally requires `STREAM_STATE_BACKEND=redis`). The **P0 `continueTurn`** path (a new continuation request that preserves the stopped partial; `NET_INTERRUPTED` Continue) is fully shipped and on by default — see §5.2.
> - **Tool/HITL errors → P1 Shipped\* (`TOOLS_ENABLED`):** the agent loop + HITL approval gate ship behind the default-off `TOOLS_ENABLED` flag. A paused turn ends in the persisted `awaiting_approval` terminal; a failed/timed-out/denied tool yields a failed/cancelled `tool_result` (the turn keeps going) rather than erroring the whole turn.

> **Shipped on `main` (D30, #145).**
> - **Platform/provider status transparency (F6 — shipped).** A public `GET /api/status` (unauthenticated, like `/api/share/{token}`) + a `/status` page returns per-route operational state (operational / degraded / down) derived from recent `Stream` terminal-event error/fallback rates over a configurable window, plus a short incident list — no third-party status vendor, no PII, no secrets. A route flips to "degraded" when its windowed error/fallback rate exceeds a configurable threshold and flips back on recovery. The §5.3 `PROVIDER_ERROR` "Status link" action targets this surface (resolving §13 #4); an in-app degraded-provider banner (`role="status"`, dismissible per session, reusing §5.7 substitution copy, linking to the model directory to switch routes) shows only when the *active* route is degraded. (Cite D30.)
> - **Moderation appeals split (F4, was P2-only — appeal capture now shipped).** User-facing transparency + appeal *capture* shipped (§5.6.1; `POST /api/account/moderation-appeal`); only the **operator** appeal-review tooling stays **P2** (no automated unblock). (Cite D30.)

---

## 11. Release acceptance criteria

1. 100% P0 codes have UI fixtures.
2. `STREAM_FAILED`, `NET_INTERRUPTED`, and Stop retain partial assistant text.
3. Hard cap blocks send before provider call.
4. Guest limit -> sign up -> same chat/messages preserved.
5. `auto_downgrade` renders substitution callout, not error banner.
5a. `PLATFORM_GUEST_DOWNGRADE` renders a substitution callout (info) and continues generation; only `PLATFORM_GUEST_LIMIT` blocks send. A guest downgrade is never silent.
6. Invalid BYOK key blocks send and leaves platform meter unchanged.
7. Error banner/modal passes axe-class check with 0 critical issues.
8. Offline send queues user message and reconciles on `online`/foreground.
9. Every error event logs `code`, `model_id`, `requested_tier`, `is_guest`, `is_byok`.

---

## 12. Success metrics

| Metric | Intent |
|---|---|
| Stream error rate | Reliability |
| Recovery success | % failed/interrupted streams followed by successful retry/continue |
| Cap hit rate | Monetization/funnel signal |
| Guest conversion at limit | Guest funnel health |
| BYOK error rate | Key UX/provider health |
| Substitution confusion | Thumbs-down within 1 min of substitution callout |
| False-blocking bugs | Sends blocked while under cap; target 0 |

---

## 13. Open questions

1. Exact free-tier caps (PRD 05 §9.3).
2. Soft timeout values per model/tier.
3. Whether P0 exposes both Continue and Regenerate, or a primary "Continue" plus secondary menu.
4. ~~Provider status page strategy.~~ **Resolved + shipped (F6, D30, #145):** a first-party public `GET /api/status` surface (+ `/status` page) derived from `Stream` terminal-event error/fallback rates (no third-party status vendor for v1) + an in-app degraded-provider banner; the §5.3 `PROVIDER_ERROR` "Status link" wires to it. See §5.3 and §10. *(Open input that remains: the windowed degraded-state threshold value — a tuning constant, not a strategy question.)*
5. ~~Moderation appeal flow timing.~~ **Resolved (F4, D30, #145):** user-facing transparent block + appeal *capture* shipped (§5.6.1; `POST /api/account/moderation-appeal`); the **operator** appeal-review tooling (and any automated unblock) stays **P2**. See §5.6.1 and the §10 phase table.
