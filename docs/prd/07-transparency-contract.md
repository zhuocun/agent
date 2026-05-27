# PRD 07 — Transparency Contract

**Product:** Transparent, multi-model, privacy-first AI chat (web + mobile-web first).  
**Owner:** Product (cross-cutting workstream — single named owner required by PRD 00 D6).  
**Status:** Draft for build.  
**Date:** 2026-05-27.  
**Related PRDs:** [00 Overview](00-product-overview.md) · [01 Core Chat](01-core-chat-experience.md) · [02 AI Capabilities](02-ai-capabilities.md) · [04 Architecture](04-technical-architecture.md) · [05 Roadmap/Monetization](05-roadmap-monetization-metrics.md) · [06 Design System](06-design-system-visual-spec.md) · [08 Error & Limit States](08-error-and-limit-states.md).

> **What this document is.** The end-to-end contract for the product wedge: users always see **which model answered**, **what it cost** when computable, and **when the served model differed from what they asked for**. It unifies registry schema (PRD 02), persistence (PRD 04), display (PRD 01/06), metering (PRD 05), and share/export behavior.

---

## 1. Promise

**"Every major model in one place — where you see and control the cost and your data."**

Transparency is not a debug view. It is persisted per turn and displayed in product UI:

1. structured cost accounting, not scalar-only pricing;
2. requested-vs-served model recording;
3. visible substitution reasons;
4. honest estimate labeling;
5. consistent behavior across in-app thread, copy/export, share links, quota meters, and analytics.

---

## 2. Goals & non-goals

### Goals
- Prevent silent model downgrades/substitutions.
- Make long-context/reasoning costs truthful enough to support user trust and metered billing.
- Feed metered free tier, Pro caps, BYOK state, and analytics from the same ledger.
- Define public-share exceptions so transparency does not leak private/competitive cost data.

### Non-goals
- Public share URLs showing cost/tokens.
- Invoice-grade reconciliation in P0.
- Full parallel model-comparison cost rollups (P1/P2).
- Tax/VAT/billing invoice line items.

---

## 3. Ownership

| Layer | Owner PRD | Responsibility |
|---|---|---|
| Registry pricing fields | PRD 02 | Structured `pricing`, model metadata, data policy |
| Cost computation | PRD 02 | `cost_usd`, `cost_breakdown`, estimate status |
| Routing/substitution | PRD 02 | requested vs served, reason codes |
| Persistence | PRD 04 | message fields and ledger capture |
| Display | PRD 01 / 06 | badges, rows, callouts, meter |
| Monetization | PRD 05 | caps, credits, BYOK policy |
| Contract authority | PRD 07 | end-to-end acceptance rules |

**Rule:** no UI may show final cost/model metadata that is not backed by persisted message metadata, except live "calculating..." states during streaming.

---

## 4. Canonical message fields **[P0]**

Every assistant message stores:

| Field | Required | Notes |
|---|---:|---|
| `requested_model_id` | if explicit | Concrete model requested by user/router |
| `requested_tier` | if tier/Auto | `fast` / `smart` / `pro` / `auto` |
| `served_model_id` / `model_id` | yes | Concrete model that answered |
| `provider` | yes | Provider or route |
| `substitution_reason` | when served differs | enum in §5 |
| `routing_decision` | when Auto | heuristic signals + selected route |
| `prompt_tokens` / `completion_tokens` / `total_tokens` | post-turn | reasoning tokens included as output |
| `cost_usd` | post-turn when computable | effective per-message platform cost |
| `cost_breakdown` | post-turn | structured details in §4.1 |
| `cost_confidence` | post-turn | `exact` / `estimate` / `unavailable` |
| `is_byok` | yes | platform meter vs user's provider key |

### 4.1 `cost_breakdown` minimum shape **[P0]**

```json
{
  "currency": "USD",
  "list_price_in_per_m": 0,
  "list_price_out_per_m": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "reasoning_tokens": 0,
  "multipliers": {
    "cached_input": 1,
    "batch": 1,
    "threshold_tier": 1,
    "promo": 1
  },
  "subtotal_usd": 0,
  "notes": []
}
```

Missing tier/promo data yields `cost_confidence: "estimate"` and a user-visible estimate label.

---

## 5. Substitution reasons **[P0]**

| Code | User-facing summary | Trigger |
|---|---|---|
| `auto_route` | Auto chose this model | Heuristic Auto selection |
| `auto_downgrade` | Auto chose a cheaper model | Cost/complexity routing |
| `rate_limited` | Requested model unavailable | Provider/platform rate limit |
| `provider_fallback` | Provider failed; fallback answered | Fallback route |
| `deprecated_model` | Requested model retired | Registry status/fallback |
| `budget_cap` | Account limit constrained routing | Free/Pro cap |
| `policy_route` | Privacy policy route selected | no-train/default route |

**AC:** any non-null reason renders a visible callout on the assistant message.

---

## 6. UX rules

### 6.1 In-app thread **[P0]**
- Every assistant message shows served model/tier without hover.
- Cost can be compact, but it must be accessible from the message.
- Estimate labels must be explicit.
- Served-vs-requested callouts include requested model/tier, served model/tier, and reason.

### 6.2 Composer/header **[P0]**
- Show selected tier/model before send.
- For Auto, post-turn attribution must show the actual route.

### 6.3 Usage meter **[P0]**
- Platform-key users: period spend/usage vs cap.
- BYOK users: "Billed to your key"; no platform token markup.
- Guest users: stricter cap and sign-up CTA.

### 6.4 Share/export **[P0]**

| Surface | Model | Cost | Tokens |
|---|---:|---:|---:|
| In-app message row | Yes | Yes | Optional/expanded |
| Copy-as-markdown | Yes | Optional default-on | Optional default-on |
| GDPR/data export | Yes | Yes | Yes |
| Public unlisted share link | Yes | **No** | **No** |

**AC:** public share markup and embedded JSON contain no `cost_usd`, token counts, or `cost_breakdown`.

---

## 7. Behavioral rules

The product must never:

1. silently serve a different model without reason and UI callout;
2. show `exact` when the computation is only an estimate;
3. use scalar-only pricing for long-context/reasoning-aware cost display;
4. decrement platform token budget for `is_byok = true` token charges;
5. hardcode model display/pricing facts outside the registry;
6. leak cost/tokens into public share links.

---

## 8. Acceptance criteria

1. 100% assistant messages have model attribution after reload.
2. Forced `rate_limited` and `auto_downgrade` fixtures persist reason + render callout.
3. Cost golden tests cover baseline, cached-input, and threshold-tier turns.
4. Missing pricing fields produce estimate labels.
5. Platform usage meter matches sum of `message.cost_usd` within documented tolerance.
6. Public share leak test finds zero cost/token fields.
7. BYOK turns set `is_byok = true` and do not decrement platform token-charge budget.
8. Registry no-hardcoding grep catches model IDs/prices outside approved config.

---

## 9. Metrics

| Metric | Definition |
|---|---|
| Silent downgrade incidents | served != requested and no reason; target 0 |
| Substitution rate | % turns with non-null reason |
| Cost estimate rate | % turns where `cost_confidence != exact` |
| Attribution expand rate | % messages where user expands cost details |
| BYOK share | % turns billed to user keys |
| Substitution thumbs-down delta | quality/trust proxy after substitution |

---

## 10. Open questions

1. Exact tolerance for estimate vs provider invoice per provider.
2. Default cost visibility: compact always-on vs expanded on demand.
3. One-click "retry with requested model" on substitution (P1?).
4. Final free-tier default model route (PRD 02 §9.9).
