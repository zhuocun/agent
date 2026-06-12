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
| Citations/sources | PRD 07 (contract) / PRD 02 (shape) | `SourcesPart` record, grounded-vs-ungrounded honesty, provenance, share rules (§4.3) |
| Retrieval cost | PRD 02 (math) / PRD 07 (shape) | `cost_breakdown.retrieval` — search-fee + embedding/rerank spend (§4.1) |
| Activity log / data-access | PRD 07 (contract) / PRD 04 (capture) | user-facing access log + per-message provenance view (§6.5) |
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
| `outputFormat` | when structured output requested | `json_object` / `json_schema` — the structured-output mode requested for the turn (SHIPPED; `ModelAttribution.output_format` in `api/app/schemas/message.py`). Absent when no `responseFormat` was requested. |
| `outputValid` | when structured output requested | Boundary-validation result for the turn (SHIPPED): JSON parse for any JSON mode plus `jsonschema.validate` for `json_schema` (`api/app/streaming/handler.py::_apply_structured_output`). Invalid output sets this `false` but never hard-fails the turn. |

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
  "retrieval": {
    "applied": false,
    "search_call_usd": 0,
    "query_embedding_usd": 0,
    "rerank_usd": 0,
    "is_byok": false,
    "sources_resolved": 0
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

**`retrieval` carries the per-turn retrieval spend** when a turn grounded its answer on web search and/or document retrieval — so the cost wedge does not become false exactly when retrieval is on. It is an additive sub-object under the same structured-cost discipline (no scalar shortcut): `search_call_usd` is the per-call web-search fee for a per-call-billed backend; `query_embedding_usd` and `rerank_usd` cover RAG's per-query embedding + optional rerank (ingest/indexing embedding is amortized to the corpus, not the turn). `applied: false` (the default) means no retrieval ran and the sub-object is identity/zero — a non-retrieval turn shows no retrieval cost. When search/embeddings ride a user's own key, `is_byok: true` and the meter reads "billed to your key" with no platform markup (§6.3), mirroring chat BYOK. A route with no published retrieval rate labels `cost_confidence: "estimate"` / `"unavailable"`, never a silent `$0.00`-exact. `sources_resolved` records the citation-coverage count for the grounded turn (feeds the grounded-answer signal in §4.3, not a cost field). Cite D25.

Missing tier/promo data yields `cost_confidence: "estimate"` and a user-visible estimate label.

### 4.2 Cost scope — per-message vs request/session surcharge **[P0]**

`cost_usd` is the **effective cost attributed to this assistant message**. Long-context surcharges, however, can be **request- or session-scoped**: OpenAI's whole-session reprice (`tier_scope: "session"`) reprices the *entire request* once the threshold is crossed, not just the triggering message. To keep per-message cost and the session-wide surcharge reconcilable:

- `cost_scope` is `"message"` (default, per-message cost only) or `"session"` (this message carries a request-scoped surcharge).
- `session_surcharge_usd` records the request-scoped delta (the cost above what the same tokens would have cost at baseline rates). It is **always attributed to the triggering turn** — the assistant message whose request crossed the threshold — and is **not** amortized across the request's other messages. A `notes` entry records the trigger, e.g. `"session-repriced: 272K threshold crossed"`.
- The §8 AC#5 meter reconciliation therefore sums `cost_usd` across messages (each already including any surcharge attributed to it); the documented tolerance need not cover surcharge re-allocation because attribution is single-turn and deterministic.

### 4.3 Citation & source contract **[Shipped — #143]**

Citations are the **source-side** of the transparency contract — the counterpart to the model+cost+served-vs-requested record above. The model-attribution half answers *which model answered and what it cost*; this half answers *what the answer was grounded on, and whether it was grounded at all*. (Inline `[n]` marker rendering is owned by PRD 01 §4.11/§5.6; the source/citation metadata shape is owned by PRD 02 §4.7; this section is the contract authority for honesty + share/export behavior. Inline markers **shipped** (D24, #143) as a render-layer increment over the already-shipped source-card list — `sources-panel.tsx` — together with this contract (grounded/ungrounded honesty + provenance + share asymmetry) and backend `requested`/provenance; the surface is gated behind web search (`SEARCH_BACKEND`, default `none`) like the search it annotates.)

- **Canonical citation record.** The per-turn `SourcesPart` (an ordered list of `SourceItem`s, each with a 1-based ordinal `id` the inline `[n]` chip keys on) is the authoritative citation record for an assistant message. It is already persisted and replayed (PRD 04), so the grounded state survives reload, replay, and share without a new field.
- **Grounded vs ungrounded (honesty rule).** An assistant turn is **grounded** iff it carries a non-empty `SourcesPart`. If the user opted into web search / retrieval for a turn but **no usable sources resolved** (search backend failure → empty, an unsupported binding silently degrading, or `SEARCH_BACKEND=none`), the answer MUST be **visibly marked ungrounded** ("Answered without live sources") rather than implying grounding. This applies the anti-silent-downgrade ethos (§7) to retrieval: never let an ungrounded answer masquerade as a cited one. The ungrounded marker is a calm inline chip, not an error.
- **Provenance / origin label.** Each source set records its origin — `web` (shipped), with `knowledge` (user-document RAG) and `connector` (read-only data connectors) **reserved** for D25's retrieval cluster — so the UI can say "From the web" vs "From your documents." Provenance is additive and small (reserve the enum now, per the typed-parts precedent); it is the source's origin label, distinct from the *model's* `data_policy` badge (PRD 02).
- **Share/export asymmetry (defined here, enforced in §6.4).** Sources are model-identity-class data, **not** cost data, so a **web** source is public-share-safe — its `title` / `url` / `domain` / `snippet` are **retained** on a public share (they are part of the trust story and carry no private cost/token data), and the full cost/breakdown stays stripped per §6.4. A **private-knowledge** (`knowledge`/`connector`) citation is tighter: its `title` / `snippet` are owner-only and MUST NOT leak to a public share — only a **redacted** "from your knowledge base" marker survives. This boundary is pinned **before** RAG ships so it is not retrofitted as a leak fix.

**AC:** a search-requested turn that resolves zero sources renders an explicit "answered without live sources" marker (asserted on an empty-result fixture, and its absence asserted on a grounded fixture); grounded state + provenance round-trip on reload, replay, and share. Cite D24.

### 4.4 Agentic runs — per-subagent attribution & per-run cost **[P2 — spec'd; not built]**

When **agentic mode** (PRD 02 §4.6 FR-26c–FR-26k; PRD 00 §11 D33–D40) fans a single turn out to bounded subagents, the contract holds **per subagent, not just per turn**: each subagent records its own served-model attribution + substitution reason (§5), and the assistant turn's `cost_usd` / `cost_breakdown` is a **roll-up = the sum of all subagent costs** (workers + planner + aggregator + reviewer), with the per-subagent costs persisted on the subagent-scoped parts so the run stays auditable. **No silent downgrade inside a fan-out** — a worker served a different model than requested still surfaces its own callout (§5). The live per-run cost meter and subagent-scoped parts are owned by PRD 02 FR-26h (contract) and PRD 01 (display); this section only fixes the rule that agentic attribution + cost obey the same honesty/estimate/no-silent-downgrade discipline as a single turn. The roll-up is **heterogeneous** — subagents may be served by different models/providers, so the turn total sums distinct per-route effective `cost_breakdown`s (not a scalar × N) and the per-subagent breakdown stays visible. The per-run USD cap is **admission-controlled**: the budget gate (PRD 04 §5.6) checks each subagent launch against the remaining run budget *before* it spends and surfaces a budget-stop callout rather than silently truncating the fan-out. (Cite D38.)

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
| `policy_route` | Privacy policy route selected | no-train route selected by policy |

**AC:** any non-null reason renders a visible callout on the assistant message.

> **Shipped (as-built).** The backend emits **six** of these codes — `auto_downgrade`, `provider_fallback`, `rate_limited`, `capacity_reroute`, `deprecated_model`, `gateway_route` (`SubstitutionReasonCode` in `api/app/schemas/common.py`). `auto_route`, `budget_cap`, and `policy_route` are **spec-reserved**: they stay in this table but are intentionally not emitted until the FE renders them. `provider_fallback` and `rate_limited` are wired to the shipped single-shot provider-fallback retry (PRD 02 FR-5 / FR-11b): a fallback emits `provider_fallback`, except a rate-limited primary error reads as `rate_limited` so the wire reason matches the cause.

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
- The compact meter should make remaining quota legible and call out near-limit
  or exhausted states before a request fails.
- BYOK users: "Billed to your key"; no platform token markup.
- Guest users: stricter cap and sign-up CTA.

### 6.4 Share/export **[P0]**

One matrix, surfaces as rows, data classes as columns. The load-bearing rule is the **public-share-vs-private asymmetry**: a **public share STRIPS** cost/tokens; **private** export/copy **RETAINS** them; and each data class below honors that same asymmetry consistently.

| Surface | Model | Cost | Tokens | Sources | Memory facts | Gen-media provenance |
|---|---:|---:|---:|---:|---:|---:|
| In-app message row | Yes | Yes | Optional/expanded | Yes | Yes | Yes |
| Copy-as-markdown | Yes | Optional default-on | Optional default-on | Yes | Yes | Yes |
| GDPR/data export | Yes | Yes | Yes | Yes | Yes | Yes |
| Multi-format export — PDF/.docx (private) | Yes | Optional default-on | Optional default-on | Yes | Yes | Yes |
| Multi-format export — PDF/.docx (share-safe) | Yes | **No** | **No** | web Yes / private-knowledge **redacted** | **Omitted** | Yes |
| Public unlisted share link | Yes | **No** | **No** | web Yes / private-knowledge **redacted** | **Omitted** | Yes |

Column rules (each consistent with the public-strip / private-retain asymmetry):

- **Sources (D24, §4.3).** Sources are model-identity-class data, not cost — so a **web** source's `title`/`url`/`domain`/`snippet` is **retained** on a public share (and share-safe export); a **private-knowledge** (`knowledge`/`connector`) citation's `title`/`snippet` is owner-only and is **redacted** on any public/share-safe surface (only a "from your knowledge base" marker survives). Private surfaces (in-app, copy, GDPR export, private PDF/.docx) retain full source detail for both origins.
- **Memory facts (D19).** The per-message "memory used here" indicator and the list of injected facts are private user data (PII). They are retained in the in-app thread and in private export/copy, but are **OMITTED** from public share and share-safe export — the memory analogue of the cost exception (model-attribution Yes / cost No / memory Omitted). Pinned here per PRD 01 §4.8 / A2.
- **Generated-media provenance (D32).** A generated image's visible "AI-generated" badge + its structured provenance field (model · provider · timestamp · marking-standard/version) is a **content claim, not cost data** — it is **RETAINED** on every surface, including public share and share-safe export (it must *not* be stripped). Only the image's per-image *cost* follows the cost column and is stripped on public share. This is the EU AI Act Art. 50(2)-aligned marking surface (built only with image-gen and after legal sign-off); the shipped Art. 50(1) interaction disclosure is separate.
- **Multi-format export — PDF/.docx (D31).** Two variants of the same export: a **private** export retains cost/tokens (default-on, toggleable — matching copy-as-markdown and the GDPR export), while a **share-safe** variant strips cost/tokens (same guarantee as the public share payload) for sending the file onward. Both render model attribution + substitution callouts; the share-safe variant additionally applies the Sources-redaction and Memory-omission rules above. Export honors retention/ephemerality (an ephemeral conversation can be exported by its owner in-session) and emits an `AuditEvent` (feeds §6.5).

**AC:** public share markup and embedded JSON (and any **share-safe** PDF/.docx) contain no `cost_usd`, token counts, or `cost_breakdown`; contain **web** source `title`/`url`/`domain`/`snippet` but **no** private-knowledge source title/snippet (only a redacted marker); contain **no** memory facts / `injectedMemoryFactIds`; and **retain** generated-media provenance metadata. A **private** PDF/.docx export retains model attribution and (default-on) per-message cost/tokens, matching the GDPR/copy-as-markdown rows.

> **Shipped + structurally enforced (as-built).** Public-by-link sharing is live (`routes/share.py`) over a nullable `conversation.share_token` (mint / revoke = set NULL). The public payload uses dedicated narrow shapes — `PublicConversation` / `PublicMessage` / `PublicAttribution` (`api/app/schemas/share.py`) — that carry model identity (`requestedTierId`, `servedTierId`, `servedModelLabel`, `isByok`, `substitution`) but **have no cost/token/breakdown field at all**. The strip is therefore a structural guarantee (the field can't serialize because it doesn't exist on the model), not a runtime filter a refactor could silently undo. The full-fidelity `cost_usd` / `breakdown` stay on the owner-facing `ChatMessage` / `ModelAttribution` and in the GDPR export.

### 6.5 Activity log & data-access transparency **[Shipped — #145]**

The share/export rules above govern what leaves a thread; this surface governs **what the user can see about how their own data was accessed** — the retrospective half of the privacy promise. It is a **user-facing prosumer trust surface**, explicitly distinct from the enterprise audit/SOC2 console (a standing non-goal). It makes the data-residency tradeoff (e.g. a DeepSeek/China route) *auditable per message* rather than only badged prospectively. Built almost entirely on data the platform already persists (no migration); shipped as `GET /api/account/activity` + the `GET /api/account/data-processing` rollup (D30, #145).

- **Activity log.** A reverse-chronological, paginated **Activity** view in settings lists account-level events — sign-in, anonymous→account upgrade, export, deletion request, BYOK key add/revoke/use, retention purge, share-link mint/revoke, and moderation block/appeal. It is read-only and append-only, included verbatim in the GDPR export, and itself erased on account deletion (the `account.delete` row is retained with `user_id = NULL`, matching the shipped SET-NULL behavior). Anonymous users see their own session-scoped log.
- **"Where your messages were processed."** A per-conversation (and account-rollup) breakdown computed **only** from the already-persisted per-message `attribution` — provider, jurisdiction (from the route's `data_policy.data_residency`), BYOK-vs-platform, and any substitution reason (reusing the §5 reason codes) — surfacing facts like "N messages processed in China (DeepSeek)" as first-class and honest, with a one-tap link to switch routes. No new per-message table; no message content in the log (provider id + jurisdiction + message id only).
- **Honesty constraints.** Jurisdiction labels are read from the live registry `data_policy` (never hardcoded); a route with no published policy renders "policy unavailable," not a guess. This is the retrospective companion to the registry-backed display rules above.

**AC:** a read route (e.g. `GET /api/account/activity`, anonymous allowed) returns the caller's events newest-first, paginated, never leaking another user's rows; the per-message provenance view is derived solely from persisted `attribution`; the log is in the GDPR export and is erased on account deletion. Cite D30.

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
8. let an **ungrounded** answer masquerade as grounded — a turn that requested retrieval but resolved no usable sources must be visibly marked "answered without live sources" (§4.3), the retrieval-side of the no-silent-downgrade through-line;
9. hide **retrieval spend** — web-search call fees and RAG embedding/rerank cost ride the same per-message meter, structured in `cost_breakdown.retrieval` (§4.1), with BYO-search/BYO-embedding shown "billed to your key" and no platform markup.

---

## 8. Acceptance criteria

1. 100% assistant messages have model attribution after reload.
2. Forced `rate_limited`, `auto_downgrade`, and `capacity_reroute` fixtures persist reason + render callout.
3. Cost golden tests cover baseline, cached-input, **long-context pricing (three fixtures: OpenAI whole-session `session_multiplier` with separate ×in/×out, Gemini stepped `applied_tier`, Anthropic `flat:true`)**, **reasoning-token cache-exemption** (a reasoning-bearing turn computes reasoning at output rate with the cache discount NOT applied), and **promo-expiry boundary** (the same turn before vs after `effective_until` — DeepSeek 2026-05-31 reversion is the golden fixture — yields the promo'd vs reverted cost and sets `promo.date_valid_at_turn` accordingly).
4. Missing pricing fields produce estimate labels.
5. Platform usage meter matches sum of `message.cost_usd` within documented tolerance, where any request-scoped `session_surcharge_usd` is attributed to its single triggering turn (§4.2) and already included in that turn's `cost_usd`.
6. Public share leak test (and the share-safe PDF/.docx variant) finds zero cost/token fields, and: contains **web** source `title`/`url`/`domain`/`snippet` but **no** private-knowledge (`knowledge`/`connector`) source title/snippet (only a redacted marker), contains **no** memory facts / `injectedMemoryFactIds`, and **retains** generated-media provenance metadata (provenance present, cost absent) — per §6.4 and §4.3.
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
