# PRD 07 — Transparency Contract

**Product:** Transparent, multi-model, cost-leading AI chat (web + mobile-web first).  
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
| `cost_usd` | post-turn when computable | effective per-message platform cost (incl. any surcharge attributed to this turn, §4.2) |
| `cost_breakdown` | post-turn | structured details in §4.1 (incl. `cost_scope`, `long_context`, `promo`) |
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
  "cost_scope": "message",
  "long_context": {
    "flat": false,
    "tier_scope": "session",
    "tokens_repriced": "all",
    "applied_tier": {
      "label": "",
      "threshold_tokens": 0,
      "price_in_per_m": 0,
      "price_out_per_m": 0,
      "cached_input_per_m": 0
    },
    "session_multiplier": { "input": 1, "output": 1 }
  },
  "multipliers": {
    "cached_input": 1,
    "batch": 1,
    "promo": 1
  },
  "promo": {
    "applied": false,
    "id": null,
    "effective_until": null,
    "date_valid_at_turn": null
  },
  "subtotal_usd": 0,
  "session_surcharge_usd": 0,
  "notes": []
}
```

**`long_context` represents all three real 2026 long-context pricing models as one self-consistent shape:**
- **(a) Whole-session reprice (OpenAI style).** Crossing a token threshold reprices the *whole* request, and input and output reprice by *different* factors (e.g. ×2 input / ×1.5 output — **two multipliers, never one scalar**). Set `tier_scope: "session"`, `tokens_repriced: "all"`, and `session_multiplier: { "input": 2, "output": 1.5 }`. The request-scoped delta is carried in `session_surcharge_usd` (see §4.2).
- **(b) Stepped per-band base rates (Gemini style).** A band above a threshold has its own resolved base rates from the registry tier table; the surcharge applies only to the overflow band, not the whole request. Set `tier_scope: "overage"`, `tokens_repriced: "above_threshold"`, and `applied_tier` carrying the resolved `price_in_per_m` / `price_out_per_m` / `cached_input_per_m` for that band, plus `threshold_tokens` (the band floor, e.g. 200000). Recording `threshold_tokens` lets the meter split tokens into the below-threshold band (priced at `list_price_*`) and the overflow band (priced at `applied_tier`) **from the stored breakdown alone** — so a turn is independently auditable/reconcilable without re-reading the registry. `cached_input_per_m` is the *stepped* cached rate (Gemini caches are also tiered), distinct from the prefix `multipliers.cached_input`.
- **(c) Flat / no surcharge (Anthropic style).** Set `flat: true` with an empty/identity `applied_tier` and `session_multiplier` of 1/1. This is a **first-class positive fact** the picker surfaces as "no long-context penalty," not merely the absence of a tier.

`session_multiplier` (whole-session reprice) and `applied_tier` (stepped band) are mutually exclusive: exactly one applies per turn, selected by `tier_scope`; `flat: true` means neither applies. The `list_price_*` fields remain the model's baseline (below-threshold) rates.

Missing tier/promo data yields `cost_confidence: "estimate"` and a user-visible estimate label.

### 4.2 Cost scope — per-message vs request/session surcharge **[P0]**

`cost_usd` is the **effective cost attributed to this assistant message**. Long-context surcharges, however, can be **request- or session-scoped**: OpenAI's whole-session reprice (`tier_scope: "session"`) reprices the *entire request* once the threshold is crossed, not just the triggering message. To keep per-message cost and the session-wide surcharge reconcilable:

- `cost_scope` is `"message"` (default, per-message cost only) or `"session"` (this message carries a request-scoped surcharge).
- `session_surcharge_usd` records the request-scoped delta (the cost above what the same tokens would have cost at baseline rates). It is **always attributed to the triggering turn** — the assistant message whose request crossed the threshold — and is **not** amortized across the request's other messages. A `notes` entry records the trigger, e.g. `"session-repriced: 272K threshold crossed"`.
- The §8 AC#5 meter reconciliation therefore sums `cost_usd` across messages (each already including any surcharge attributed to it); the documented tolerance need not cover surcharge re-allocation because attribution is single-turn and deterministic.

---

## 5. Substitution reasons **[P0]**

| Code | User-facing summary | Trigger |
|---|---|---|
| `auto_route` | Auto chose this model | Heuristic Auto selection |
| `auto_downgrade` | Auto chose a cheaper model | Cost/complexity routing |
| `rate_limited` | Requested model unavailable | Provider/platform rate limit |
| `provider_fallback` | Provider failed; fallback answered | Fallback route |
| `deprecated_model` | Requested model retired | Registry status/fallback |
| `capacity_reroute` | Requested model at capacity; rerouted | Provider/gateway capacity reroute (PRD 02 FR-11b) |
| `gateway_route` | Gateway selected an alternate route | Gateway-level routing/policy reroute |
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
6. leak cost/tokens into public share links;
7. apply the `cached_input` discount to reasoning tokens. **Reasoning tokens are billed at the output rate and are never cache-eligible** — they are per-request and full-price every turn. The `multipliers.cached_input` (and any stepped `applied_tier.cached_input_per_m`) applies only to non-reasoning input/output; `reasoning_tokens` are billed at `list_price_out_per_m` (or the applicable `applied_tier.price_out_per_m`) with no cache discount.

---

## 8. Acceptance criteria

1. 100% assistant messages have model attribution after reload.
2. Forced `rate_limited`, `auto_downgrade`, and `capacity_reroute` fixtures persist reason + render callout.
3. Cost golden tests cover baseline, cached-input, **long-context pricing (three fixtures: OpenAI whole-session `session_multiplier` with separate ×in/×out, Gemini stepped `applied_tier`, Anthropic `flat:true`)**, **reasoning-token cache-exemption** (a reasoning-bearing turn computes reasoning at output rate with the cache discount NOT applied), and **promo-expiry boundary** (the same turn before vs after `effective_until` — DeepSeek 2026-05-31 reversion is the golden fixture — yields the promo'd vs reverted cost and sets `promo.date_valid_at_turn` accordingly).
4. Missing pricing fields produce estimate labels.
5. Platform usage meter matches sum of `message.cost_usd` within documented tolerance, where any request-scoped `session_surcharge_usd` is attributed to its single triggering turn (§4.2) and already included in that turn's `cost_usd`.
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
