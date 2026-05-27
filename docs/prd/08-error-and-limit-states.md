# PRD 08 — Error & Limit States

**Product:** Transparent, multi-model, privacy-first AI chat (web + mobile-web first).  
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

### 5.4 Platform limits

| Code | Trigger | Actions |
|---|---|---|
| `PLATFORM_RATE_LIMIT` | Request/token window | Wait `retry_after`, Reduce usage |
| `PLATFORM_BUDGET_EXCEEDED` | Rolling USD/message cap | Upgrade, Add credits, BYOK |
| `PLATFORM_TIER_GATED` | Model/tier not available | Upgrade or pick available tier |
| `PLATFORM_GUEST_DOWNGRADE` | Guest moved to a weaker model after good-model allotment | (transparency callout, not a block) Sign up to keep the better model |
| `PLATFORM_GUEST_LIMIT` | Anonymous cap (hard sign-up wall) | Sign up / sign in |

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
| `INPUT_MODERATION` | Safety block | Edit message |
| `INPUT_CONTEXT_EXCEEDED` | Over context pre-send | Shorten, Start new chat, Summarize when available |
| `INPUT_INVALID` | Schema/validation | Fix input |

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
| Provider 429/5xx | Yes | Automated fallback UX | — |
| Platform/guest/tier caps | Yes | Rich credit packs | Team/admin limits |
| BYOK errors | Yes | — | — |
| Offline queue + optimistic send | Yes | Background sync replay where supported | — |
| Resumable-stream Continue | Partial+Continue request | True replay | — |
| Tool/HITL errors | Reserved | Yes | — |
| Moderation appeals | — | — | Yes |

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
4. Provider status page strategy.
5. Moderation appeal flow timing.
