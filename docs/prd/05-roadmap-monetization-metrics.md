# PRD 05 — Roadmap, Monetization, Metrics & Non-Functional Requirements

**Product:** A transparent, multi-model, cost-leading AI chat for web and mobile (mobile-web first).
**Owner:** Product Strategy
**Status:** Draft for stakeholder review
**Date:** 2026-05-27

> **Verification flags.** Every dollar figure, per-tier limit, model name, and regulatory date in this PRD is **fast-moving** and must be re-verified against first-party vendor/regulatory pages before it is committed to a build or quoted externally. Items needing re-verification are tagged `[VERIFY]`. A consolidated list lives in §10.

---

## 1. Summary & Purpose

This PRD consolidates the workstream PRDs into **one coherent execution plan**: a phased roadmap (P0/P1/P2), a monetization recommendation with cost economics, the day-one metrics program, and product-level non-functional requirements (accessibility, i18n, privacy, security/trust, compliance). Competitive/monetization findings are inlined here; legacy `research-*.md` files are **not in the repo** — see §10.1 for mapping.

It is the canonical reference for **scope sequencing, pricing, KPIs, and NFRs**. Where individual workstream PRDs go deep on their domain, this PRD resolves cross-cutting tensions — most notably that **the multi-provider model picker plus transparency (model used + token cost) is IN the MVP**, not a later phase, because it is the core wedge and is cheap to deliver via the provider-abstraction layer the architecture already requires.

Purpose:
- Give engineering a defensible P0/P1/P2 cut with dependency notes.
- Give the business a monetization model that survives AI-margin reality.
- Give analytics a day-one instrumentation list.
- Give legal/design a tagged NFR list aligned to the EU AI Act timeline.

---

## 2. Goals & Non-Goals

### 2.1 Product/business goals
1. **Establish a defensible beachhead with power users/developers** on a wedge incumbents do not own: multi-model + transparency + privacy.
2. **Ship a credible MVP fast** that wins on streaming/rendering fidelity, composer ergonomics, accessibility, and mobile-web polish — not feature breadth.
3. **Protect gross margin from day one** via aggressive model routing, metered free tier, and BYOK, given AI economics (§5).
4. **Build trust as a product surface**: always show which model answered and what it cost; never silently downgrade.
5. **Stay expandable**: keep a simple default ("just give me the best answer") mode so we can move down-market to casual users and up-market to teams/enterprise later without a rebuild.

### 2.2 Non-goals (this phase)
- **Not** competing head-on at the commoditized ~$20 single-model all-rounder tier on feature breadth.
- **Not** chasing casual mass-market acquisition (high COGS, low willingness to pay, must out-execute ChatGPT's free tier). `[VERIFY]` ad/free-tier dynamics.
- **Not** building enterprise seats, SSO/SAML, SOC 2, or DPAs in P0 (long sales cycle, compliance burden) — deferred to P2.
- **Not** shipping ads — a **trust liability we decline even as OpenAI leans in.** Perplexity *abandoned* ads (Feb 2026, citing user trust) and grew subscription/enterprise-led; only ChatGPT is *expanding* ads (Free + Go, US→intl). We defer on a **trust/brand** basis, not because "the market is abandoning ads." `[VERIFY]`.
- **Not** building heavy parallel model comparison, artifacts/canvas, RAG, memory, voice, image-gen, MCP, or native apps in P0.

---

## 3. Target Personas & Positioning (canonical)

> This section is the **canonical persona/positioning statement** that other PRDs reference.

### 3.1 Positioning statement
**"The transparent, multi-model, cost-leading AI chat — every major model in one place, where you see (and control) the cost and your data."**

The open market gap is **multi-model + transparency + privacy + cost control**. Incumbents are single-model (ChatGPT/Claude/Gemini), trust-damaged on transparency (Perplexity's silent model downgrades), or bare aggregators without a privacy/transparency story (Poe). We stack three defensible wedges (model choice, transparency, BYOK/privacy) rather than fight at the commoditized $20 all-rounder tier.

**What we are not:** a generic AI work assistant, inbox/calendar agent, or broad productivity suite. This is a **chat product** whose primary wedge is **multi-model choice + per-message cost/model transparency + privacy/BYOK**; workflow breadth follows only after the core chat loop is trusted and polished.

### 3.2 Personas

| Priority | Persona | Core needs | Willingness to pay | Cost to serve |
|---|---|---|---|---|
| **Primary (MVP)** | **Power users / developers** | Model choice, transparency, cost control, BYOK, keyboard speed, fast/polished core | Medium–High (pay for control/savings) | **Low** if BYOK/usage-based |
| **Secondary (fast-follow)** | **Privacy-conscious prosumers** (researchers, journalists, lawyers, EU users) | No-train-by-default, citations/transparency, GDPR posture | Medium | Low–Medium |
| **Defer (P2+)** | Teams / small orgs | Shared workspace, admin, no-train contracts, SSO, billing | High (per seat) | Medium; long sales cycle |
| **Defer (later)** | Enterprise | Data residency, audit, SSO, DPA | Highest | High compliance burden |
| **Defer (later)** | Casual mass-market | Simple, fast, free, mobile | Low (mostly free) | High (subsidized) |

2026 guidance: segment by **sophistication / automation preference**, not demographics. Our differentiation maps directly onto the power-user segment, which converts and is cheap to serve via BYOK/usage-based pricing. The bet: a defensible, profitable beachhead beats subsidizing casual users against incumbents. **Keep a simple default mode** so down-market expansion is a setting, not a rebuild.

> **Teams on-ramp (feature-expansion §4.5 / D29).** The **Teams / small orgs** row gets a *minimal prosumer realization* — shared credit pool + shared Projects + owner/member roles (P2). It deliberately serves only the prosumer subset of that persona's needs (shared workspace + pooled billing) and **declines** the SSO / per-seat / SOC2 / DPA parts, which stay on the **Enterprise** row (non-goal this phase). BYOK stays personal; the workspace primitive is the expandable seam, not an enterprise build.

---

## 4. Phased Roadmap (P0 / P1 / P2)

### 4.1 MVP scope statement (rough)

> **MVP (P0):** A fast, polished, mobile-web-first responsive chat app (Next.js 16 FE + FastAPI/Fly backend over SSE, custom anonymous-first sessions, PWA layer) that nails streaming + streaming-safe markdown rendering, composer ergonomics, conversation management, core message actions, a collapsible reasoning panel, onboarding, basic settings, share/export, a command palette, and an accessibility baseline — delivered over a **multi-provider model picker with a visible "model used + token cost" transparency surface** (the core wedge, backed by the provider-abstraction layer). It launches with a **no-train-by-default privacy posture**, **AI-interaction disclosure**, a **metered free tier** plus a **Pro subscription with explicit metered caps + transparent USD credit overage** (exact Pro price an open question — see §9) and a **BYOK option (no token markup)**, governed by aggressive model routing to protect margin. It targets power users/developers; everything heavier (deep comparison, artifacts, search/RAG, memory, voice, image-gen, MCP, native, enterprise) is explicitly later.

### 4.2 Tension resolution (explicit)
- **Multi-provider model picker + transparency → P0.** It is the wedge, and the architecture (backend provider protocol + DeepSeek/OpenAI-compatible and Anthropic adapters, with future gateway/OpenRouter breadth) makes a basic picker and per-message cost/model display cheap. Integrate Anthropic + OpenAI + Gemini directly for primary tiers and OpenRouter for breadth/fallback. `[VERIFY]` model IDs/pricing.
- **Deep *parallel* comparison (same prompt → N models side by side) → Shipped** (a 2-up view landed ahead of schedule, #134/#135; was variously slated P1/P2). The picker is P0; running and diffing multiple models in one view was a heavier, later layer now built.
- **Artifacts/canvas, web-search/RAG, memory, voice, image-gen, MCP, Capacitor native, enterprise → P1/P2** (high infra cost, mobile-web complexity, or long sales cycle).

### 4.3 Feature → phase table (reconciled)

Legend: **P0** = MVP / must-have to be credible · **P1** = fast-follow · **P2** = later/differentiator/heavier infra. **Source** cites authoritative workstream PRD sections. Legacy `research-*.md` files are not in this repo; see §10.1 for mapping.

**Shipped** / **Shipped\*** (behind a default-off flag) annotates rows whose code landed ahead of the original phase.

| Feature / capability | Phase | Source | Notes / dependencies |
|---|---|---|---|
| Token streaming with Stop/Abort (preserves partial output) | **P0** | 01 §4.1, 04 §5.1 | SSE + Stop/abort + partial persistence. |
| Interrupted-stream recovery (partial + Continue/Regenerate) | **P0** | 01 §4.1, 03 §4.6, 04 §5.1 | Distinct from resumable replay; no SSE replay at MVP. |
| Resumable-stream replay (same-device) | **P1 — Shipped\* (RESUMABLE_STREAMS_ENABLED; prod needs Redis)** | 04 §5.1, 01 §4.1 | Requires Redis + `Stream` table; Stop semantics invert. Dedicated stop endpoint + orphan reaper shipped & always-on. |
| Streaming-safe markdown renderer (code+copy, KaTeX, GFM tables) | **P0** | 01 §4.4, 03 §4.10 | Mermaid renders as code/source at P0. |
| Mermaid diagram rendering | **P1 — Shipped** | 01 §4.4, 03 §4.10 | Interactive/fullscreen; lazy-loaded engine. |
| Robust text composer (multiline, send/stop, text paste, model picker) | **P0** | 01 §4.3, 03 §4.3 | P0 text-only; no attach affordance. |
| Mobile camera/library/file attach UI | **P1 — partially shipped** | 03 §4.7, 01 §4.3, 02 §4.8 | Lands with vision/PDF; attach UI present, image vision Anthropic-only. |
| Multi-provider model picker (Fast/Smart/Pro tiers) | **P0** | 02 §4.2, 04 §5.2 | Core wedge; direct primaries + breadth layer. |
| xAI/Grok registry entry, gated from default/Auto | **P0** | 02 §5.3, 04 §5.2 | Not free-tier/Auto default until data-policy approval. |
| Transparency surface: model used + per-message token/cost | **P0** | 01 §4.6, 02 §4.1, 04 §6, 07 | Core wedge; no silent downgrade. |
| Transparency cost schema + served-vs-requested surface | **P0** | 00 §11 D6, 02 FR-2b, 04 §6, 07 | One contract; no scalar-only pricing. |
| Public share: model attribution, no per-message cost | **P0 — Shipped** | 01 §4.10, 07 §6.4 | Public-by-link exception. |
| Typed multi-part message model | **P0** | 00 §11 D7, 01 §4.4, 04 §6 | P0 data layer; render text/code/reasoning/status subset. |
| Tool-call/status parts in message schema | **P0** | 01 §4.1, 04 §5.3/§6 | Renderer = status lines; full tool UI P1. |
| Next.js 16 FE / FastAPI backend / custom anonymous-first auth | **P0** | 00 §8, 04 §4 | Shipped foundation. |
| Auto-routing (heuristic; cheap default) | **P0** | 02 §4.2, 05 §5.4 | Excludes `default_route_eligible=false`. |
| Conversation management, message actions, onboarding, settings, share, shortcuts | **P0** | 01 §4.5–§4.10 | Core chat shell and power-user controls. |
| Reasoning/status panel | **P0** | 01 §4.2, 02 §4.4 | Include reasoning-token cost. |
| BYOK restricted to non-anonymous accounts | **P0** | 02 FR-6, 04 §5.2, 05 §5.1 | Guests must link/upgrade before key storage. |
| P0 i18n baseline (externalized strings, RTL, IME-safe send) | **P0** | 05 §7.2, 01 §5.3, 03 §4.3 | Full locale packs later. |
| Accessibility baseline | **P0** | 01 §5.7, 03 §4.8, 05 §7.1 | Differentiation lever. |
| Responsive mobile-web layout + PWA layer | **P0** | 03 §4.1–§4.10 | Pull-to-refresh dropped. |
| Optimistic send + IndexedDB drafts/queue + retry | **P0** | 03 §4.6, 04 §5.8 | Server remains source of truth. |
| Virtualized message list + smart auto-scroll | **P0** | 03 §4.5 | Top technical spike. |
| INP budget + `scheduler.yield()` / rAF token batching | **P0** | 03 §4.10, 05 §6.1 | Streaming chat worst-case for INP. |
| Context management + usage/cost meter | **P0** | 02 §4.9, 04 §6, 07 | Underpins transparency + routing. |
| Structured outputs / schema validation | **P0** | 02 §4.10, 04 §5.2 | Validate at the backend/provider boundary. Shipped: `response_format` + boundary validation → `outputValid`. |
| Safety + AI-interaction disclosure | **P0** | 02 §6, 04 §5.7, 05 §7.5 | US + EU launch gate. |
| No-train-by-default + retention/export/delete | **P0** | 04 §5.7, 05 §7.3 | Privacy acquisition hook. Export/delete shipped (`/api/account/export`, `DELETE /api/account`); per-user retention purge shipped. |
| Metered free + metered Pro + BYOK | **P0** | 05 §5, 04 §5.6, 02 FR-6 | Pro = explicit caps + USD overage. Shipped: real Stripe checkout/portal/webhooks + USD credit ledger (grant/debit), default-off `BILLING_BACKEND`. |
| Minimal metered-overage / USD credit primitive | **P0** | 05 §5.1, 00 §11 D8, 04 §5.6 | Enforcement reads `message.cost_usd`. Shipped: real Stripe checkout/portal/webhooks + USD credit ledger (grant/debit), default-off `BILLING_BACKEND`. |
| Vision + PDF/document understanding | **P1 — partially shipped** | 02 §4.8, 04 §5.4 | Attach + text/PDF transcript on attachment-capable bindings (Anthropic/OpenAI); the prod DeepSeek route accepts no attachments; image vision Anthropic-only. |
| Tool/function calling + basic agent loop | **P1 — Shipped\* (TOOLS_ENABLED, fake-provider v1)** | 02 §4.6, 04 §5.2 | HITL approval for sensitive tools. |
| Web search/grounding + citations/source cards | **P1 — Shipped\* (SEARCH_BACKEND, Tavily)** | 01 §4.11, 02 §4.7 | Structured citation parts; source-card list, no inline `[n]` markers yet. |
| Deep parallel model comparison | **Shipped** | 00 §5, 02 FR-12 | 2-up same-prompt view; originally P2. P1 keeps per-turn switching and branch/retry workflows. |
| Projects/Spaces, memory transparency, copy-on-branch | **P1 (copy-on-branch Shipped; rest deferred)** | 01 §4.6, 01 §4.8, 05 §4.4 | Continuity and retention layer. |
| Slash commands / prompt library + customizable shortcuts | **P1** | 01 §4.3, 01 §4.9 | Power-user ergonomics. |
| Richer usage-credit UX / prepaid packs | **P1** | 05 §5.1 | P0 has minimal overage primitive. |
| Artifacts/Canvas, code execution, RAG, voice, image generation, MCP, native, teams/enterprise | **P2** | 01 §4.12, 02 §4.7/§4.12, 03 §6, 04 §8 | Later differentiators/heavier infra. |
| Ads on free tier | **P2 (revisit)** | 05 §2.2, 05 §9.10 | Trust risk; revisit only at scale. |
| Per-turn reasoning-effort override (+cost/latency hint) | **P0 — Shipped** | 02 FR-16, 01 §4.2 | minimal/standard/extended; graceful on unsupported providers. |
| Provider fallback (pre-first-token, substitution-coded) | **P0 — Shipped** | 02 FR-5/FR-11b, 07 §5, 08 §10 | single-shot; provider_fallback/rate_limited. |
| User monthly budget cap (lower-of platform/user) | **P0 — Shipped** | 05 §5.1, 04 §5.6 | preferences.monthly_budget_usd (mig 0018). |
| Real Stripe billing (checkout/portal/webhooks/entitlements/credits) | **P0 — Shipped\* (BILLING_BACKEND)** | 05 §5.1, 04 §5.6 | signed idempotent webhooks; Pro + credit packs. |
| First-party analytics (FE intake + server funnel events) | **P0 — Shipped** | 05 §6, 04 §5.6 | POST /api/analytics/events; analytics_event. |
| Continue-a-stopped-turn | **P0 — Shipped** | 08 §5.2, 04 §5.1 | distinct from replay. |
| Conversation branch / search / pin | **P0/P1 — Shipped** | 01 §4.6, 00 D10 | branch is cost-stripped. |
| Versioned-KEK BYOK + re-encryption | **P0 — Shipped** | 04 §5.2/§5.7 | BYOK_KEK_VERSIONS. |
| Safety / moderation preflight | **P0 — Shipped\* (SAFETY_BACKEND=local)** | 02 SR-1, 04 §5.7 | blocklist preflight. |
| Custom instructions + retention controls | **P0 — Shipped** | 02 FR-20, 04 §5.7 | preferences.custom_instructions/retention_days. |

### 4.4 Dependency notes
- **Provider-abstraction layer** (P0) is the spine: model picker, routing, transparency meter, BYOK, and later parallel comparison all sit on it. Build it thin so OpenRouter/LiteLLM can swap in without app changes.
- **Interrupted-stream spine (P0):** partial persistence + Continue/Regenerate + terminal stream analytics flags — no Redis replay required for launch.
- **Resumable-stream spine (P1 — shipped behind `RESUMABLE_STREAMS_ENABLED`):** Redis replay + dedicated stop endpoint + orphan reaper. Stop endpoint + reaper are shipped & always-on; replay is default-off and prod-gated on Redis.
- **Tool/function-calling loop** (P1) is a prerequisite for **web search** (P1), **data analysis** (P2), and **MCP** (P2).
- **Agentic loop + artifacts** precede **sandboxed code execution** (P2).
- **Vision/file understanding** (P1) precedes **RAG** (P2) — start with large-context "attach a doc" before full retrieval.
- **Capacitor native** (P2) reuses the P0 PWA codebase (~100% reuse) — do not build a separate app.
- **Transparency cost-accounting schema** (P0) is the spine for the **metered-overage / credit primitive** (P0): metering enforcement and USD-credit top-ups read from the same per-message cost accounting that powers the user-facing transparency surface. Build the schema rich enough (tiered/threshold/cached/promo) to be *true*, or the cost number — the wedge — is wrong on the high-value long-context turns.
- **Typed multi-part message model** (P0 data layer) is a prerequisite for tools (P1), structured citations (P1), interactive viz (P2), and generative UI (P2). It is one decision shared across PRD 01 (UX) and PRD 04 (data model) — make it once in the data layer and reference from both. Render only the text/code/reasoning subset at P0.
- **US-state-law AI-interaction disclosure** now rests on **CA SB 243** (live now, only if companion/minors — see §9.11) plus generic AI-interaction-disclosure good practice; it remains a **P0 launch-gate for the US market** sitting next to the EU AI Act note below — not EU-only. **CO SB 205 is no longer a live gate** (enforcement stayed Apr 27 2026; repealed/replaced by SB 26-189 → Jan 1 2027, narrowed to ADMT — likely out of scope for a general chat product; watch its Jan-2027 ADMT scope). Our P0 disclosure covers the core requirement (see §7.5).
- **EU AI-interaction disclosure** (Art. 50(1)) is **FIRM at 2 Aug 2026** — the firm EU P0 launch-gate (cheap, already P0) `[VERIFY]`. **EU AI Act content-marking** (Art. 50(2), machine-readable AI-content labels) should be designed alongside any **image/media generation** and only attaches **if/when we ship AI-generated media** (narrow for a P0 text-relay chat). Its date is **legally UNSETTLED for a new launch**: the 7-May-2026 Digital Omnibus is provisional pending Official Journal; readings range from no-grace → 2 Aug 2026 (compliance read) to ~2 Dec 2026 (architecture read). **Do not pick one — it needs legal sign-off before EU-launch scope is locked.** Keep `[VERIFY]` (see §7.5).
- **Feature-expansion clusters (PRD 00 §11 D19–D32) — added dependencies:** memory / Projects / advanced-search (P1, now shipped — #148/#151/#153) sit on the context-assembly seam (PRD 02 FR-37 cache-stable prefix) + new tables (`memory_fact` / `project` / `tag` / `conversation_tag`), and are in the export/erase cascade from first ship (PRD 04 §5.7). The **RAG cluster** (P2) is gated on object storage + a worker/queue + pgvector — the *same* object-storage gate as in-thread image generation. **Prosumer shared workspaces** (P2, D29) depend on **Projects** (P1, D20). **Spend analytics / value-aware picker / budget guardrails** (shipped, D27, #144) ride the shipped per-message cost + attribution + auto-router (no new routing brain). **Content-marking** (D32) is designed-for now but built only with image generation and after EU legal sign-off.

### 4.5 Feature-expansion backlog (this brainstorm — D19–D32; D19/D20/D21/D22/D23/D24/D27/D30 shipped, D31 partial, rest specced)

The feature-expansion pass (PRD 00 §11 **D19–D32**) specced a set of net-new, on-strategy features — each deepening one of the six wedges (multi-model · transparency · cost · privacy · mobile-web · accessibility). **Several have since shipped on `main`: D24 (inline `[n]` citations + contract, #143), D27 (spend analytics + budget guardrails + value-aware picker, #144), D30 (trust surfaces, #145), D19 (transparent long-term memory, #148), D22 (dictation + read-aloud, #149), D31 (granular per-conversation retention + scheduled purge — partial; ephemeral/incognito + multi-format export remain, #147), and D20 + D23 (Projects/Spaces, prompt library, customizable keyboard shortcuts, #151); plus the D20-tail + D21 "organize + find" wave (Conversation org v2 — tags/archive/bulk actions — plus advanced history search with transparency-native filters + query-time Postgres FTS, #153)** — marked **Shipped** / **Partially shipped** in the table below; the rest remain specced (not built). The table is the roadmap placement; **full specs live in the workstream PRDs** (01/02/03/04/06/07/08). It expands several summary rows in §4.3 — the Projects/Spaces + memory-transparency row, the slash-commands/prompt-library + customizable-shortcuts row, the richer-usage-credit row, the web-search "no inline `[n]` markers yet" note (now closed by D24), and the P2 Artifacts/Canvas/RAG/voice/image-gen/MCP/teams cluster row — into per-feature detail. Same P0/P1/P2 legend; **P2\*** = P2 stretch/later.

| Feature / capability | Phase | Source | Notes / dependencies |
|---|---|---|---|
| Transparent long-term memory (editable ledger + per-fact provenance + "memory used here" indicator) | **Shipped (#148)** | 00 D19, 01 §4.8, 02 §4.11/FR-40, 04 §6, 07 §6.4 | Opt-in / off-by-default; injected into the user turn (no cache-stable prefix as-built); excluded from temporary chats; export/erase-complete; `MemoryUsedChip` provenance. |
| Projects/Spaces (containers + scoped instructions/tier/retention/budget) | **Shipped (#151)** | 00 D20, 01 §4.5, 02 §4.5/FR-21, 04 §6 | Single-level; memory stays account-global; scoped tier (create-time seed) + instructions (concat) + retention (conv>project>global) + budget sub-cap; export/erase-complete. Personas stay P2. |
| Conversation org v2 (tags, archive, bulk actions) | **Shipped (#153)** | 00 D20, 01 §4.5, 04 §6 | User-scoped tags (`tag` + `conversation_tag`) + an `archived` flag + bulk archive/unarchive/delete/tag/untag (`POST /api/conversations/bulk`, owner-scoped — foreign ids dropped); pin was already shipped; nested folders deferred; tags export/erase-complete; archived stays subject to retention purge (`retention_days` is the override, not archive). |
| Advanced history search (served-model/cost/date/tag/project filters + Postgres FTS) | **Shipped (#153)** | 00 D21, 01 §4.5/§8, 04 §6 | Transparency-native filters layered onto the existing `/search` endpoint; **query-time** Postgres FTS (`to_tsvector @@ websearch_to_tsquery`, SQLite `LIKE` fallback, Python part-text re-filter as the precision gate), GIN functional index deferred as a perf follow-up; vector/semantic deferred P2. Resolved the PRD 01 §8 search-scope question. |
| Dictation (STT) + read-aloud (TTS) | **Shipped (#149)** | 00 D22, 01 §4.6, 02 §5.2, 03 §4.7 | Split out of the FR-33 P2 lump; Web Speech (browser-native) shipped, server/BYOK track deferred; editable transcript, never auto-send. |
| Prompt library + user-authored templates | **Shipped (#151)** | 00 D23, 01 §4.3, 02 | Variable `{{placeholder}}`s; slash-style picker; pure composer prefill (no model/cost change); export/erase-complete. |
| Customizable keyboard shortcuts | **Shipped (#151)** | 00 D23, 01 §5.5 | Remaps the shipped fixed set; reserved-combo guard; overrides on `preferences.keyboard_shortcuts`. |
| Inline `[n]` citation markers (clickable, hover/tap-to-source) | **Shipped (#143)** | 00 D24, 01 §4.11/§5.6, 02 §4.7, 07 §4.3 | Render-layer upgrade over the shipped source list; closed the §4.3 web-search named gap. Gated behind web search (`SEARCH_BACKEND`, default `none`). |
| Citation transparency contract (grounded-vs-ungrounded honesty + provenance + share rules) | **Shipped (#143)** | 00 D24, 07 §4.3, 02 §4.7 | Source-side of the transparency contract; shipped with the inline markers (backend `requested`/provenance added). |
| Spend-analytics dashboard (longitudinal by day/model/conversation; burn-down; export) | **Shipped (#144)** | 00 D27, 05 §6, 01 §4, 04 §6, 07 | `GET /api/account/spend`; aggregates `message.cost_usd` + attribution; labels cumulative-meter (month-to-date) vs surviving-messages basis. Sibling of "Richer usage-credit UX". |
| Value-aware picker — label-only "Cheapest" badge | **Shipped (#144)** | 00 D27, 05 §5.4, 02 §4.2, 01 §4.3 | Per-tier $/Mtok + a label-only "Cheapest" badge on the cheapest available route; never silent (no model switch). |
| Opt-in "cheapest capable route" suggestion + saved comparisons | **P1** | 00 D27, 02 §4.2, 01 §4.3 | Not shipped; the picker only labels today (no suggestion engine, no saved comparisons). |
| Budget alerts + soft/hard cap + per-conversation cap | **Shipped (#144)** | 00 D27, 05 §5.4, 08 | Per-conversation cap (migration `0019`, `preferences.per_conversation_budget_usd`) + 80%/100% soft-cap alerts layered over the shipped hard gate; default behavior unchanged. |
| Annual Pro + plan lifecycle (proration/pause/cancel/dunning) | **P1** | 00 D28, 05 §5.1, 04 §5.6 | Extends shipped Stripe Checkout/Portal/webhooks + `BillingEntitlement`; annual price configurable. |
| Data-access activity log (incl. which provider processed which message) | **Shipped (#145)** | 00 D30, 07 §6.5, 04, 05 §7.4 | `GET /api/account/activity` + `GET /api/account/data-processing` rollup over the write-only `AuditEvent` trail; no migration; user-facing, distinct from enterprise audit. |
| Model & data-policy directory (catalog + compare) | **Shipped (#145)** | 00 D30, 02 §5.4, 07, 06 | `GET /api/models/directory`; registry-driven; no hardcoded model facts (SR-3). |
| Granular retention + ephemeral/incognito chat (durable `expires_at` + scheduled purge) | **Partially shipped (#147)** | 00 D31, 05 §7.3, 04 §5.7, 02 FR-41 | Per-conversation retention override (`conversations.retention_days`) + always-on scheduled purge (`RETENTION_PURGE_ENABLED`) shipped, fixing opportunistic-only purge; ephemeral/incognito + sensitive tagging deferred. |
| Transparent moderation + appeal | **Shipped (#145)** | 00 D30, 08 §5.6, 07 §7 | Surface why (category + source), never silent; `POST /api/account/moderation-appeal` request-review path; `SAFETY_BLOCKED` as-built. Operator review tooling stays P2. |
| Platform incident & status transparency (public `/api/status` + degraded banner) | **Shipped (#145)** | 00 D30, 08 §10, 07 §5 | Public `GET /api/status` + `/status` page, derived from `Stream` telemetry; wires the `PROVIDER_ERROR` "Status link". |
| Multi-format export (PDF/.docx) | **P1** | 00 D31, 07 §6.4, 01 §4.10 | Honors cost asymmetry (private retains cost; share-safe strips it). |
| Custom assistants / personas (reusable model+prompt+tool bundle) | **P2** | 00 D23, 02 FR-21, 01 | Labeled default; served-badge supersedes the pinned label; gated on real-provider tool wiring. |
| Artifacts / canvas (editable, versioned side-panel) | **P2** | 00 D23, 01 §4.12, 02 | Conversation-bound; builds on typed-parts (D7); not a doc-editor product. |
| Code execution (sandboxed, HITL tool) | **P2** | 00 D23, 02 §4.6, 01 | Tool in the shipped agent loop; isolation / no-egress / bounded; gated on real-provider wiring. |
| MCP **action** connectors (approval-gated) | **P2** | 00 D23, 02 §4.12/FR-22 | Action/tool only; no background automation; secrets via the BYOK crypto path. |
| File/document RAG (chunk/embed/retrieve/cite; pgvector; BYO-embedding) | **P2** | 00 D25, 02 FR-29, 04 §5.3/§5.4/§6, 07 | Needs object storage + worker/queue + pgvector; FR-29 large-context bridge first. |
| Retrieval privacy & index-control (manifest, per-corpus delete, no-train embeddings) | **P2** | 00 D25, 04 §5.7, 02 §6.2, 05 §7.3 | Ships WITH RAG; privacy precondition of indexing. |
| Retrieval cost transparency (search-fee + embedding on the meter) | **P2** | 00 D25, 07 §4.1, 02 FR-2b/FR-36, 04 §6 | Rides RAG; the web-search-fee slice can land earlier with inline markers. |
| Unified hands-free voice mode (STT→model→TTS, barge-in) | **P2** | 00 D22, 02, 03 | Served model + cost preserved in voice; turn-based v1 (no realtime infra). |
| In-thread image generation (attribution + cost + provenance) | **P2** | 00 D22/D32, 02 FR-33, 04 §5.4, 07 §6.4 | Needs object storage; carries the content-marking obligation (D32). |
| Cross-tool memory import (paste/upload → review → ledger) | **P2** | 00 D19, 01 §4.8, 04 §6 | Acquisition lever; review-before-save; format-tolerant; lands after core memory. |
| Referral credit grants + giftable credit packs | **P2** | 00 D28, 05 §5.1/§6.2 | Idempotent `grant` ledger entries; anti-abuse is a launch requirement. |
| Lightweight shared workspaces (shared credit pool + shared Projects + owner/member) | **P2** | 00 D29, 05 §3/§4.4, 04 §6 | Prosumer-only; **excludes SSO/SCIM/SOC2/audit/DPA/seats**; depends on Projects (D20). |
| Content-marking / provenance (EU AI Act Art. 50(2)) | **P2 (legally gated)** | 00 D32, 05 §7.5, 07 §6.4, 08 | Designed-for now; built with image-gen AND after legal sign-off; date unsettled (`[VERIFY]`). |
| Read-only data-source connectors (URL/Drive/Notion → citable corpus) | **P2\* (stretch)** | 00 D26, 02 §4.13, 04 §5.4 | Read-only/least-privilege; distinct from MCP action connectors; needs RAG + privacy panel first. |

---

## 5. Monetization Model

### 5.1 Recommendation
**Hybrid: freemium funnel + metered Pro subscription + BYOK (no token markup) + transparent USD credit overage from launch — all governed by aggressive model routing.** The **exact Pro price is an open question** (see §9.1): the ~$15–20/mo band sits at/below the legacy ~$20 anchor but is **~2–2.5× T3 Chat's $8/mo multi-model plan** (§5.3) — that premium must be justified by privacy + accessibility + mobile-web polish + true cost transparency, or the price reconsidered. (T3's 2026 model is a 4-hour usage bar + monthly overage, not a clean per-message plan, so this is a price-point comparison, not a per-message equivalence.) `[VERIFY]` price point against both the ~$20 incumbent anchor and the $8 aggregator floor.

- **Free tier (metered):** message/token caps on the **DeepSeek** default (current registry: `deepseek-v4-flash` for fast/smart/auto and `deepseek-v4-pro` for pro; PRD 02 owns selection; see §9.5) to cap COGS and feed the funnel; Western no-train routes stay selectable in the picker. **No training on chats by default** as a configurable posture (privacy as an acquisition hook), surfaced per route via the data-handling badge.
- **Metered Pro subscription:** all frontier models, **explicit metered caps with transparent USD credit overage** (not a flat "generous limits" plan — see §5.2 / the P0 metered-overage primitive in §4.3), the transparency dashboard (model used + token cost), and (P1) multi-model comparison. Pulling metering forward to P0 resolves the prior §5.1-vs-§5.2 flat-Pro-vs-hard-metering inconsistency and matches the 2026 credit-economy pivot (Copilot 6/1/26, Anthropic, Cursor — §5.2). Enforcement mechanism is owned by PRD 04; the monetization/roadmap decision is owned here.
- **BYOK option:** user plugs in their own provider keys; **we add zero token markup**. Monetize via a small flat platform fee or bundle into Pro. Near-zero COGS revenue line that converts power users cheaply and **directly de-risks our biggest margin threat**. **Routing BYOK via OpenRouter is free for the first 1M BYOK requests/mo (then 5% of equivalent cost)** — materially lowers BYOK infra cost and supports the $0-markup promise. `[VERIFY]`.
- **Usage credits:** the **minimal metered-overage / USD credit primitive is now P0** (so Pro's caps have transparent overage); **richer prepaid credit-pack UX (top-up flows, Poe-style packs) is P1** for occasional heavy users who don't subscribe.
- **Subscription lifecycle + growth loops (feature-expansion §4.5 / D28):** complete the metered-Pro story with **annual Pro** + first-party **proration / pause / cancel / dunning** (P1), and add **referral credit grants + giftable credit packs** as idempotent entries on the same USD ledger (P2; anti-abuse a launch requirement). Both extend the shipped Stripe + credit spine — no new money primitive; the annual price feeds the §9.1 open band. **Lightweight prosumer shared workspaces** (P2 / D29) pool credits on the same primitive — explicitly **NOT enterprise** (no SSO/SCIM/SOC2/per-seat; BYOK stays personal).
- **Longitudinal cost transparency (shipped / D27, #144):** a user-facing **spend-analytics surface** (`GET /api/account/spend` — spend by day/model/conversation, month-to-date cumulative vs surviving-messages bases) shipped as the natural extension of the per-message transparency wedge to a retention/activation surface — over already-captured cost+attribution, no new money primitive. Shipped alongside a per-conversation budget cap (migration `0019`) with 80%/100% soft-cap alerts and a label-only "Cheapest" badge.
- **Defer:** ads (a **trust liability we decline even as OpenAI leans in** — §2.2) and enterprise seats (P2; long cycle/compliance).

*Implementation status: shipped behind default-off `BILLING_BACKEND` (`stripe`/`fake`) — Stripe Checkout (`pro_subscription` + `credit_purchase`), Billing Portal, signature-verified idempotent webhooks granting USD credits / Pro entitlements, and a `usage_credit_ledger` (grant/platform_debit/adjustment) read by the budget gate (`api/app/routes/billing.py`). The "richer prepaid credit-pack UX" remains the P1 layer.*

### 5.2 Cost economics (why this shape)
- AI-first companies run **~50–60% gross margins** (vs 80–90% classic SaaS); inference alone can eat **~23% of revenue**. `[VERIFY]`
- **"Inference whale" risk:** reports of a heavy flat-rate user generating **~$35,000** in compute while paying **$200/mo** — a ~175x subsidy. A flat sub with generous limits is a landmine for a sub-scale entrant. `[VERIFY]`
- **Token prices vary 30–100x** across models for the same workload (frontier vs DeepSeek class) — **model routing is a direct margin lever**, not a nicety. `[VERIFY]`
- **Free→paid conversion is single-digit %:** ~2.6% organic, ~5.6% average, up to ~5.1% with feature gating; opt-in trials 4–6%. Plan and model COGS around single-digit conversion. `[VERIFY]`

**Implication:** margin is engineered, not assumed. Default everything cheap; escalate to frontier only on paid/complex demand; push the heaviest users to BYOK; meter the free tier hard.

### 5.3 Market pricing comparison (`[VERIFY]` — re-confirm all figures against vendor pricing pages)

> All figures below are `[SOURCED]`/secondary from research file 05 and **must be re-verified** before external use. Prices, limits, and which tier gets what move month-to-month.

| Product | Free tier | Entry paid (~"Plus") | Pro / high tier | Team / Enterprise | Usage / API |
|---|---|---|---|---|---|
| ChatGPT | Yes (**ads on Free + Go**, US→intl) | Go ~$8; **Plus ~$20/mo** | Pro ~$100 / ~$200/mo | Business ~$20/seat (annual; ~$25–30 monthly); Enterprise custom | Per-token API |
| Claude | Yes (limited) | **Pro ~$20/mo** | Max 5x ~$100 / Max 20x ~$200/mo | Team ~$25/seat; **Team Premium ~$125/seat**; Enterprise custom (per-seat + separate API) | Per-token API |
| Gemini | Yes | **AI Plus ~$7.99**; **AI Pro ~$19.99/mo** | AI Ultra ~$99.99 / ~$200/mo (Ultra cut $250→$200) | Workspace/Enterprise | Vertex/Gemini API |
| Perplexity | Yes | **Pro ~$20/mo** | Max ~$200; Edu Pro ~$10 | Enterprise ~$40–$325/seat | Sonar API |
| Copilot | Limited | **Pro $10/mo**; **Pro+ $39** | — | Business **$19/seat**; Enterprise **$39/seat** | **Usage-based billing from Jun 1 2026** (monthly GitHub AI Credits, token-metered); completions stay free |
| Mistral Le Chat | Yes (~25 msgs/day) | **Pro ~$14.99/mo** | — | Team ~$24.99/seat | Per-token API (separate) |
| DeepSeek | **Yes, no paywall** | — | — | — | Ultra-cheap per-token; ~98% cache discount |
| **T3 Chat** (**anchor-to-beat**) | trial | **$8/mo Pro** — mechanics overhauled 2026: a **usage bar that resets every 4 hours** + a monthly **Overage bucket** (Base refills every 4h, Overage on monthly renewal); **no standard/premium credits** | — | — | API-rate arbitrage; transparent-about-limits, no privacy story |
| Poe | Yes (points) | ~$4.99 / ~$19.99 | ~$49.99 / ~$99.99 / ~$249.99 | Teams ~$249.99 | Dev API (points) |
| OpenRouter (BYOK/agg) | free models (rate-limited) | n/a | n/a | n/a | **5.5% platform fee** on credit usage; **BYOK 5% of equiv cost, first 1M BYOK req/mo FREE** |
| TypingMind (BYOK) | n/a | **~$79 one-time** | n/a | Team licenses | Pay providers directly |
| **Our product (proposed)** | **Metered, cheap DeepSeek default** | **Metered Pro (price open — see §9.1)** | (richer credit-pack UX P1; minimal overage primitive P0) | Team/Enterprise = P2 | **BYOK at $0 markup** + transparent USD credits |

**Read:** the legacy consumer anchor is ~$20/mo "Plus/Pro"; prosumer tiers ($100/$200) are **usage multipliers, not better models**. A new **$100 power-user band** is emerging between $20 and $200 (ChatGPT Pro $100, Apr 9 2026; Google AI Ultra $100 already listed above) as vendors segment power users. But the sharper near-term anchor is **T3 Chat at $8/mo** (multi-model, transparent caps; 2026 mechanics = a 4-hour-resetting usage bar + monthly Overage bucket) — the closest competitor to our exact pitch and the **explicit price/feature anchor-to-beat**. Our differentiation over T3 is privacy/no-train + accessibility/mobile-web polish + genuine cost transparency (T3 has no privacy story). We differentiate on transparency, model choice, and BYOK rather than on a higher price; the **exact Pro price (~$15–20 vs the $8 floor) stays an open question** (§9.1).

### 5.4 Free-tier metering strategy (to cap COGS)
1. **Cheap DeepSeek default model** (current registry: `deepseek-v4-flash` for fast/smart/auto; PRD 02 owns selection, §9.5) for free/default traffic; frontier models gated to Pro or BYOK. The **DeepSeek-hosted API is the main provider** precisely because it is the cost leader (token prices 30–100× below frontier), which is what makes a viable metered free tier possible; its data-residency posture (jurisdictional bans + data-in-China) is an accepted, badged tradeoff (PRD 02 §5.3 / PRD 00 D11), with Western no-train routes selectable in the picker. Western-hosted DeepSeek open weights remain a P2+ self-hosting option. `[VERIFY]` model IDs.
2. **Daily/rolling message + token caps** with clear in-UI remaining-quota display (doubles as transparency). `[VERIFY]` exact caps via cost modeling against single-digit conversion.
3. **Routing-by-default:** classify easy queries to the cheapest capable model; escalate only on explicit user choice or detected complexity.
4. **Reasoning/thinking gated:** thinking tokens bill as output — gate behind a tier/toggle and meter visibly.
5. **Value-aware selection + proactive guardrails (feature-expansion §4.5 / D27, #144 — shipped):** the picker surfaces a **label-only "Cheapest" badge** (value-aware, **never silently switches** the model, per §7/no-silent-downgrade), and **per-conversation budget cap + 80%/100% soft-cap alerts** (migration `0019`, `preferences.per_conversation_budget_usd`) ship layered over the shipped hard gate (default behavior unchanged). Turns routing-as-margin-lever into a user-facing cost-savings signal and warns *before* the wall, not just at it.
5. **Multimodal gated:** vision/file/voice carry 5–10x infra impact — meter and gate (P1+).
6. **Guest rate-limiting:** cap anonymous traffic to control spend before account creation.

### 5.5 Tradeoffs
- **Pro:** protects margins (BYOK + routing + metering), differentiates on transparency/privacy, multiple revenue lines, low capital risk, no dependence on massive scale.
- **Con:** more complex pricing UX than a single $20 plan; BYOK has setup friction and a smaller early TAM; multi-model creates **dependency on upstream provider pricing/terms**; usage credits add cognitive load.
- **Mitigation:** strong defaults + a simple "just give me the best answer" mode hide complexity for less-sophisticated users while power users get the dials.

---

## 6. Success Metrics & KPIs

> **AI usage is bursty/task-driven** — a user may run 50 queries then vanish for weeks. Classic 7/30-day windows are weaker signals here, so instrument **task-recurrence** alongside standard retention. Critically, **AI-native retention runs roughly half of classic SaaS** (≈40% GRR / 48% NRR vs ~82% SaaS NRR) and "AI tourist" churn is severe — model the financials on **AI-native, not SaaS, benchmarks** and instrument the first-week activation funnel hard. `[VERIFY]` benchmarks.

### 6.0 Primary KPI set (canonical for the PRD set)

Instrument **first** for AI-native economics and retention: (1) Day-1 success / first-week activation funnel, (2) **GRR / NRR** (AI-native benchmarks), (3) **task-recurrence interval**, (4) cost-per-message / gross margin / routing mix, (5) free→paid conversion, and (6) terminal stream events (`completed`, `stopped`, `error`, `interrupted`). **D1/D7/D30** and DAU/MAU are secondary habit proxies for a bursty category.

### 6.1 Day-one must-haves (instrument from launch)

| Category | Metric | Rough benchmark / target | Why |
|---|---|---|---|
| **Activation** | % new users reaching first successful response / first "valued" task; **time-to-first-value** | Track + improve | Leading indicator of everything downstream. |
| **First-week activation** | **"Day-1 success" funnel** — % completing a first-week success checklist (first valued task in week 1) | Highest retention lever in the data ("Day-1 success checklist" → ~52.7% trial conversion) `[VERIFY]` | Checklist for this wedge: first successful streamed reply, viewed model/cost attribution, opened usage meter, and either changed tier/Auto route or used privacy/BYOK/temporary-chat control. |
| **Latency (UX quality)** | **TTFT (time-to-first-token)** + full-response latency, **per model** | Lower is better; per-model SLAs | Core chat UX quality; informs routing. |
| **Retention (AI-native)** | **GRR / NRR** + **30/60/90-day "AI-tourist" churn cohort** + D1/D7/D30 **+ task-recurrence interval** | **AI-native ≈ 40% GRR / 48% NRR** (vs ~82% SaaS NRR); ~30% of annual subs cancel in month 1; ~44% of cancels in first 90 days `[VERIFY]` | Use AI-native benchmarks, not SaaS-optimistic numbers; bursty-usage correction. |
| **Engagement** | DAU, MAU, **DAU/MAU stickiness** | 20%+ = high; **~21% NA AI norm** `[VERIFY]` | Habit signal. |
| **Conversation depth** | Messages/session, conversation length, sessions/user | Track trend | Value-per-session proxy. |
| **Monetization** | **Free→paid conversion**, MRR, **ARPU (target bands)**, churn | Plan single-digit % conversion; **ARPU bands: sub-led $30–100+; hybrid $3–15** (annual) `[VERIFY]` | Revenue health; sub-led ARPU only reachable with strong conversion + low churn. |
| **Unit economics** | **Cost-per-user / cost-per-message (token COGS)**, gross margin per tier, **model-routing mix** | Margin target ~50–60% `[VERIFY]` | Existential given §5; routing mix is the lever. |
| **Quality/trust** | Thumbs up/down, **regeneration rate**, NPS/CSAT | Track + alert on spikes | Output quality + silent-downgrade detection. |

### 6.2 Phase-2 / later metrics
- Cohorted **LTV:CAC**.
- **Expansion / seat growth** (teams).
- **Feature-adoption funnels** (artifacts, search, memory).
- **Model-comparison usage** (validates multi-model positioning).
- **Accessibility / i18n usage by locale** (validates a11y + localization investment; localization can affect up to ~30% of retention in multilingual platforms `[VERIFY]`).
- **BYOK adoption rate** (margin de-risking) and credit-pack purchase behavior.
- **Spend-dashboard engagement** (opened usage insights; D27) — a first-week activation + retention signal — plus **budget-alert engagement** (threshold opt-in, soft-cap acknowledgements).
- **Annual-plan mix + ARPU lift** and **dunning recovery rate** (D28); **referral viral coefficient** (invites → qualified signups) + **gift-credit redemption**.
- **Grounded-answer citation rate** (inline `[n]` resolution; D24) and **memory adoption** (opt-in rate, facts/user; D19).
- **Trust-surface engagement** (activity-log / model-directory views, route-switch-after-provenance; D30) and **STT/TTS usage** (D22).

### 6.3 Instrumentation notes
- Capture **model used + token cost per message** server-side from day one (also powers the user-facing transparency surface).
- Tie every cost metric to the **routing decision** so margin regressions are attributable to model mix.
- Emit terminal stream events from backend stream handling: `done`, `stopped`, `error` — required day-one for regeneration-quality and mobile recovery KPIs (PRD 04 §5.1).
- Observability via structured logs plus optional Sentry/OpenTelemetry (per PRD 04) — keep KPI definitions in one source of truth.

---

## 7. Non-Functional Requirements

> Product-level NFRs. Technical implementation hooks (streaming infra, storage adapters, key encryption) live in PRD 04 (architecture). Each requirement is tagged **[MVP]** or **[Later]**.

### 7.1 Accessibility — target WCAG 2.1 AA → 2.2 AA
A **stated differentiation lever**: leaders have measured gaps (unlabeled icon buttons, missing live regions; Oct-2025 testing). `[VERIFY]` current state.

- **[MVP]** Level **AA** as the bar (EU EAA/EN 301 549, UK PSBAR, US Section 508, Accessible Canada Act).
- **[MVP]** Full keyboard operability; visible focus indicators (WCAG 2.2); logical focus order across history → composer → model picker → streaming output.
- **[MVP]** Semantic structure + **ARIA live regions** so screen readers announce streaming tokens **politely** (not spammy) and announce generation status ("Generating…", "Searching…").
- **[MVP]** Labeled icon buttons (copy vs edit vs rate distinguishable by SR); text alternatives for non-text content (code blocks, charts, generated images).
- **[MVP]** Mobile: **tap targets 44–48px** (WCAG 2.2 SC 2.5.8 ≥24px min + spacing); respect iOS Dynamic Type / Android `sp`; 4.5:1 body contrast; non-gesture alternative for every gesture; honor `prefers-reduced-motion`.
- **[Later]** Accessible-authentication review; full WCAG 2.2 cognitive-load criteria; per-locale a11y testing.

### 7.2 Internationalization / Localization
- **[MVP]** **UTF-8 everywhere**; **externalize all UI strings** from day one (retrofitting is costly).
- **[MVP]** Pseudo-localization testing to catch overflow (text expands ~20–30%).
- **[MVP]** **RTL/BiDi** support via `direction: rtl` + logical CSS (`text-align: start`), not hard-coded positions; handle mixed LTR/RTL in one line (Arabic + English code/brand). Incumbents have had RTL bugs — an opportunity.
- **[MVP]** **Language ≠ model-language:** the chat model must be prompted/configured for the user's language; a localized UI does not imply localized responses.
- **[MVP]** **IME-safe input:** do not submit on Enter or Send while `event.isComposing`; Esc must not Stop during composition (PRD 01 §5.3, PRD 03 §4.3). Required for CJK and mobile autocorrect.
- **[Later]** Full translated UI locales beyond launch set; locale-specific content/formatting; localized onboarding.

### 7.3 Privacy & data handling (acquisition hook)
- **[MVP]** **No training on user chats by default.**
- **[MVP]** **Short, configurable retention** with an **in-product retention-status disclosure**.
- **[MVP]** **One-click export & delete.**
- **[MVP]** **Optional no-telemetry mode** (Mistral-style differentiation).
- **[MVP]** GDPR essentials for EU users: consent, access, deletion, data minimization.
- **[P1]** (feature-expansion §4.5 / **D19, D31**) Opt-in **long-term memory** as a user-visible, editable, per-fact-attributed store (off by default), complete in export/erase and excluded from temporary chats; **per-conversation retention overrides + ephemeral/incognito chat + a scheduled purge** make retention actually enforced (not merely opportunistic on active users) and controllable per thread.
- **[P2]** (**D25**) **RAG indexing privacy** — a per-corpus index manifest (what's indexed, where embeddings live, retention, no-train embedding route), per-document/corpus delete with cross-store fan-out, and explicit indexing consent; shipped *with* retrieval, not after.
- **[Later]** Contractual no-train guarantees for Team/Enterprise; data residency options; DPA availability.
- *Context (narrow scope):* a **2026 SDNY district-court opinion (Rakoff, Feb 2026)** held that some AI-chat documents are **not attorney-client privileged** (not binding federal precedent), and a separate discovery order (Stein, Jan 2026) compelled OpenAI to produce a 20M-log sample with no user notice. `[VERIFY]` This strengthens the case for an explicit, user-controlled privacy posture — but the marketing claim must be **"we minimise what exists to be compelled (short retention, no-train, delete)," NOT "your chats are confidential/privileged."** We'd be subject to the same discovery.
- *Right-sizing the claim:* incumbents now match no-train **at enterprise/team tiers** (OpenAI + Anthropic) and offer temporary-chat modes; Mistral owns the EU-sovereign niche. Our consumer/prosumer no-train-by-default is still ahead of *consumer* defaults but is **not unique** — position privacy as **"least-data-retained + EU-friendly + transparent,"** a prosumer/EU play, not a mass-consumer "confidential" promise.

### 7.4 Security & trust
- **[MVP]** Encryption in transit and at rest.
- **[MVP]** **BYOK secret handling**: keys encrypted, never logged.
- **[MVP]** **BYOK guest gate:** key storage only for **non-anonymous** accounts; guests must complete account link before keys are accepted (PRD 04).
- **[MVP]** **Surface model used + token cost** on every response; **never silently downgrade** the model (Perplexity's mistake) — the trust surface is a product feature, not just a setting.
- **[MVP]** Baseline abuse monitoring + an abuse-reporting path.
- **[Shipped]** (feature-expansion §4.5 / **D30**, #145) **User-facing trust surfaces:** a data-access **activity log** (`GET /api/account/activity` — logins, exports, deletions, BYOK-key use) plus a **data-processing rollup** (`GET /api/account/data-processing` — *which provider processed which message*), a **model/data-policy directory** (`GET /api/models/directory`), **transparent moderation** (surface the why — category + source; never a silent block or silent edit; `POST /api/account/moderation-appeal` request-review path), and **incident/status transparency** (public `GET /api/status` + `/status` page + degraded-provider banner). Built on already-persisted data (no migration). These are prosumer trust surfaces — explicitly distinct from the **[Later]** enterprise audit/SOC 2 console below.
- **[Later]** SSO/SAML, audit logs, SOC 2 path, DPA (Team/Enterprise, P2).

### 7.5 Content moderation, US state law & EU AI Act compliance

> **This is a two-jurisdiction surface, not EU-only.** A US launch — our primary power-user/dev market — already triggers AI-interaction-disclosure obligations *today*. Our P0 **AI-interaction disclosure** (see §4.3) **already covers the core requirement of both the US state laws and the EU transparency obligation** — build it in from the start.

**US state-law layer (live now):**
- **[MVP]** **CA SB 243 (Companion Chatbot Act)** — mandatory "you're talking to an AI" disclosure, crisis-handling protocols, minor protections — **effective Jan 1, 2026.** **Now the main surviving live US obligation** (see the minors/companion-persona decision below and §9.11); only bites if we offer companion personas / serve minors. Our P0 disclosure covers the core disclosure requirement; we additionally rest the US disclosure posture on **generic AI-interaction-disclosure good practice.**
- **[MVP]** **CA AB 2013 (training-data transparency)** — developers must disclose training-dataset info — **effective Jan 1, 2026** (touches our model-provider disclosures).
- **[Watch — no longer a P0 gate]** **CO SB 205 (Colorado AI Act)** — **DEAD as a live US disclosure gate.** Enforcement was **stayed (Apr 27, 2026)** and SB 205 was **repealed/replaced by SB 26-189** (signed May 14, 2026; effective **Jan 1, 2027**), narrowed to **ADMT for "consequential decisions"** (education/employment/finance/insurance/healthcare/gov) — a general chat product is **likely out of scope.** Do **not** cite the old "enforce Jun 30 2026" gate. **Watch-item:** SB 26-189's Jan-2027 ADMT scope. `[VERIFY]`
- *Context:* a **Dec 11, 2025 federal preemption EO** + DOJ "AI Litigation Task Force" challenge state AI laws, but the EO is **not self-executing**, expressly **carves out child-safety laws**, and the 10-year state moratorium failed in the Senate — so the state patchwork is **live and contested, not preempted.** `[VERIFY]`

**Minors / companion-persona decision — `[PRIMARY US COMPLIANCE DETERMINANT — OPEN QUESTION, see §9.11]`:** With **CO SB 205 collapsed** and the federal EO carving out **child-safety**, **CA SB 243 is now the main surviving live US obligation** — and it triggers specifically on companion personas / serving minors. We must explicitly decide **whether we serve minors / offer companion-style personas**, because that decision — not CO SB 205 — now drives our US P0 compliance load. If yes, additional obligations attach (crisis protocols, break reminders, stronger minor protections). **This is a PRODUCT DECISION — flag and elevate; do not decide here.**

**EU AI Act layer (interaction-disclosure FIRM; content-marking date legally UNSETTLED — keep `[VERIFY]`, do not downgrade):**
- **[MVP]** **AI-interaction disclosure** — clearly tell users they are interacting with an AI (EU AI Act Article 50 transparency, **effective ~Aug 2, 2026** `[VERIFY]`). Art. 50 transparency violations are penalised at **up to €15M or 3%** of worldwide turnover (Art. 99); the **€35M / 7%** tier applies only to **Art. 5 prohibited-practices**, not to transparency. `[VERIFY]`
- **[MVP]** Baseline safety filtering / abuse monitoring (see §7.4).
- **[Later/contested — `[VERIFY]`]** **Machine-readable marking/labeling of AI-generated content** (Art. 50(2): deepfakes, public-interest text) — its date is **legally UNSETTLED for a new launch.** The **7-May-2026 Digital Omnibus is provisional pending Official Journal**, and readings range from **no-grace → 2 Aug 2026** (compliance read; grace is pre-existing-systems-only) to **~2 Dec 2026** (architecture read). **We do not pick one here — this needs legal sign-off before EU-launch scope is locked.** Critically, marking **only attaches if/when we ship AI-generated media** (text/image/audio/video); for a **P0 text-relay chat** that relays provider output with attribution it is **narrow** either way, and should be designed alongside any future image/media generation. Keep the `[VERIFY]` flags until legal confirms.

---

## 8. Risks & Mitigations (product/business)

| Risk | Likelihood / Impact | Mitigation |
|---|---|---|
| **Aggregator price compression** (T3 Chat @ $8/mo, OpenRouter chat undercut the *same* multi-model surface) | High / High | **Sharper near-term risk than generic commoditization.** Multi-model is now commoditised by cheap aggregators — differentiate on **transparency + cost-control (durable legs) + privacy/a11y/mobile**, not on "having many models"; justify any premium over the $8 floor or reprice (§5.1/§9.1). |
| **Pricing-model risk** (we ship a flat sub while the 2026 market reprices to metered credits) | Medium / High | Leaves us exposed to "inference whales" and looking dated within a year. Mitigation = **metered Pro + P0 metered-overage/credit primitive** (§4.3/§5.1) from launch, matching Copilot/Anthropic/Cursor repricing. |
| **Commoditization vs incumbents** (we look like "another $20 chat app") | Medium / High | Don't compete on breadth; lead with the stacked wedge (multi-model + transparency + BYOK/privacy); win on rendering/streaming/a11y/mobile polish. |
| **COGS / margin erosion** ("inference whales", 30–100x token variance) | High / High | Aggressive routing (cheap default), hard free-tier metering, push heavy users to BYOK, per-message cost instrumentation with margin alerts. |
| **Trust/privacy execution failure** (we promise transparency/no-train and slip) | Medium / High | Make transparency a visible product surface; no silent downgrades; encrypted BYOK keys; ship export/delete + retention disclosure in P0; audit before launch. |
| **Smaller power-user TAM** (beachhead too small to grow) | Medium / Medium | Keep a simple default mode for down-market expansion; fast-follow privacy-prosumers; sequence Projects/search/memory to broaden appeal. |
| **Upstream provider dependency** (pricing/terms/SLA changes) | Medium / High | Thin provider abstraction (swap DeepSeek/OpenAI-compatible routing to OpenRouter/LiteLLM/gateway if needed); multi-provider by design; BYOK offloads token risk to users; monitor provider price/term changes. |
| **Compliance timeline slip** (EU AI Act: firm 2 Aug 2026 interaction-disclosure; legally-unsettled content-marking date) | Medium / High | AI-interaction disclosure (Art. 50(1)) is the firm P0 gate; content-marking (Art. 50(2)) only attaches if/when we ship AI-generated media — design it alongside media-gen; track official EC pages `[VERIFY]`; **get legal sign-off on the content-marking date (no-grace → 2 Aug 2026 vs ~2 Dec 2026; 7-May-2026 Digital Omnibus provisional pending Official Journal) before EU-launch scope is locked** (§7.5). |
| **US regulatory-surface risk** (state AI-law patchwork + shifting federal preemption, beyond EU) | Medium / High | CA SB 243 / AB 2013 live now (SB 243 = the main surviving obligation, companion/minors); **CO SB 205 is dead** (stayed Apr 27 2026; repealed/replaced by SB 26-189 → Jan 1 2027, narrowed to ADMT — likely out of scope); preemption contested and carves out child-safety. P0 disclosure covers the core; track state patchwork (incl. SB 26-189's Jan-2027 ADMT scope); **resolve the minors/companion-persona gate — now the primary live US compliance determinant** (§7.5/§9.11). |
| **Fast-moving facts** (prices/models/limits churn monthly) | High / Medium | Pull pricing/model lists from live APIs, never hardcode; re-verify §10 list at build time. |

---

## 9. Open Questions (for stakeholders)

1. **Pro price point `[CONTESTED — flag, don't decide]`:** ~$15–20 vs T3 Chat's **$8** anchor? Our ~$15–20 is **~2–2.5× T3's price for a similar multi-model surface** — justify the premium (privacy + a11y + mobile-web + true cost transparency) or reprice. (T3's 2026 mechanics are a 4-hour usage bar + monthly overage, so compare on price point, not per-message.) Trade conversion volume against margin and both the ~$20 incumbent and $8 aggregator anchors. `[VERIFY]` market.
2. **BYOK monetization:** small flat platform fee, bundled into Pro, or free as an acquisition lever? Affects billing infra. (Note: OpenRouter BYOK free for first 1M req/mo lowers infra cost — §5.1.)
3. **Free-tier caps:** exact message/token limits — needs a cost model run against single-digit conversion assumptions. `[VERIFY]`
4. **Metered Pro from launch — RESOLVED:** Pro is a **metered plan with explicit caps + transparent USD credit overage from launch**, and the **minimal metered-overage/credit primitive is pulled to P0** (was P1), per the 2026 credit-economy pivot. Richer prepaid credit-pack UX stays P1. (Enforcement owned by PRD 04.) This resolves the prior §5.1-vs-§5.2 inconsistency.
5. **Default model for free tier — RESOLVED:** **DeepSeek is the main provider and default** (current registry: `deepseek-v4-flash` / `deepseek-v4-pro` via the OpenAI-compatible binding) — chosen as the cost leader. Its data-residency posture is an accepted, badged tradeoff (PRD 00 D11); Western no-train routes (Gemini Flash / GPT-mini / Claude Haiku / Mistral-EU class) stay selectable in the picker, and Western-hosted DeepSeek open weights remain a **P2+** self-hosting option. **PRD 02 owns the registry/selection.** `[VERIFY]` model IDs.
6. **EU launch timing vs AI Act dates `[CONTESTED — flag, don't decide]`:** do we gate EU availability on the **firm 2 Aug 2026** Art. 50(1) AI-**interaction disclosure** obligation, or launch globally with disclosure built in? The interaction-disclosure date is **firm**; the Art. 50(2) **content-marking** date is **legally UNSETTLED for a new launch** — the 7-May-2026 Digital Omnibus is provisional pending Official Journal, with readings from no-grace → 2 Aug 2026 to ~2 Dec 2026, and marking only attaches **if/when we ship AI-generated media** (narrow for P0 text relay). **Do not pick a marking date — needs legal sign-off before EU-launch scope is locked.** `[VERIFY]` (§7.5).
7. **Secondary persona timing:** how aggressively to court privacy-prosumers (researchers/journalists/lawyers) in P1 — affects citation/search prioritization.
8. **RAG in scope earlier?** If a target segment needs persistent doc knowledge bases, RAG may pull from P2 toward P1 (per PRD 04 open question).
9. **Native trigger:** which KPI threshold (iOS push re-engagement, app-store discoverability) flips Capacitor from P2 to active?
10. **Ads at scale:** ads are a **mixed** market signal (ChatGPT *expanding*; Perplexity *withdrew* for trust). Our deferral is on a **trust/brand** basis — is it permanently off-strategy or a "revisit at scale" option?
11. **Minors / companion-persona decision `[CONTESTED — PRIMARY US COMPLIANCE DETERMINANT — flag, don't decide]`:** do we serve minors or offer companion-style personas? **Since CO SB 205 collapsed (stayed + repealed/replaced → narrow ADMT scope) and the Dec-2025 federal preemption EO expressly carves out child-safety, CA SB 243 is now the main surviving live US obligation — and it triggers specifically on companion personas / serving minors.** This makes the yes/no call **the primary determinant of our US P0 compliance load**, not a side-question. If yes, additional obligations attach (crisis protocols, break reminders, stronger minor protections). **This is a PRODUCT DECISION — elevate its priority; needs explicit product + legal decision (§7.5).**

---

## 10. References

### 10.1 Internal PRD index & research mapping

| Legacy research file (external) | Maps to PRD | In repo? |
|---|---|---|
| research-01 (features/UX) | **PRD 01** | No — use PRD 01 §4–§5 |
| research-02 (mobile) | **PRD 03** | No — use PRD 03 §4–§6 |
| research-03 (architecture) | **PRD 04** | No — use PRD 04 §4–§6 |
| research-04 (AI capabilities) | **PRD 02** | No — use PRD 02 §4–§6 |
| research-05 (roadmap/monetization) | **PRD 05** | No — use this document |

**PRD numbering ≠ research numbering** (see PRD 00 §6). For build and reviews, cite **PRD file + section** only. Re-verify `[VERIFY]` facts at lock via §10.3, not stale research copies.

### 10.2 Key source URLs (re-verify before quoting — see §10.3)
- Pricing: https://chatgpt.com/pricing/ · https://claude.com/pricing · https://one.google.com/about/google-ai-plans/ · https://gemini.google/subscriptions/ · https://www.finout.io/blog/perplexity-pricing-in-2026 · https://www.eesel.ai/blog/copilot-pricing · https://mistral.ai/pricing · https://api-docs.deepseek.com/quick_start/pricing · https://costbench.com/software/ai-chatbots/poe/ · T3 Chat: https://x.com/theo/status/1887000229922353524
- BYOK: https://openrouter.ai/announcements/1-million-free-byok-requests-per-month · https://openrouter.ai/docs/guides/overview/auth/byok · https://openrouter.ai/pricing
- Credit-economy pivot: https://metronome.com/blog/2026-trends-from-cataloging-50-ai-pricing-models · https://windowsforum.com/threads/github-copilot-ai-credits-usage-based-billing-starts-june-1-2026.415470/
- US state AI laws / preemption: https://www.orrick.com/en/Insights/2026/04/2026-State-Chatbot-Laws-Key-Provisions-and-Regulatory-Trends · https://www.kslaw.com/news-and-insights/new-state-ai-laws-are-effective-on-january-1-2026-but-a-new-executive-order-signals-disruption · https://www.gibsondunn.com/president-trump-latest-executive-order-on-ai-seeks-to-preempt-state-laws/
- AI-chat discovery rulings: https://www.crowell.com/en/insights/client-alerts/federal-court-rules-some-ai-chats-are-not-protected-by-legal-privilege-what-it-means-for-you · https://natlawreview.com/article/openai-loses-privacy-gambit-20-million-chatgpt-logs-likely-headed-copyright
- Ads (mixed signal): https://www.macrumors.com/2026/02/09/chatgpt-now-has-ads/
- Economics/conversion: https://www.trendingtopics.eu/ai-software-margins/ · https://www.investing.com/analysis/the-ai-token-pricing-crisis-behind-openai-and-anthropics-revenue-race-200680777 · https://www.growthunhinged.com/p/free-to-paid-conversion-report · https://firstpagesage.com/seo-blog/saas-freemium-conversion-rates/
- Personas/metrics: https://www.unboxfuture.com/2026/04/ai-trends-2026-great-divide-between.html · https://www.arcade.dev/blog/user-retention-in-ai-platforms-metrics/ · https://mixpanel.com/blog/ai-product-metrics/ · https://mixpanel.com/blog/mau/
- Accessibility: https://www.audioeye.com/post/wcag-22/ · https://www.browserstack.com/guide/wcag-compliance-checklist · https://www.w3.org/TR/WCAG2Mobile-22/
- i18n: https://simplelocalize.io/blog/posts/ui-localization-best-practices/ · https://www.ai-toolbox.co/chatgpt-toolbox-features/chatgpt-rtl-language-support
- Privacy: https://felloai.com/how-to-stop-ai-from-training-on-your-data/ · https://lumichats.com/blog/chatgpt-claude-gemini-training-your-data-2026-privacy-guide
- EU AI Act: https://artificialintelligenceact.eu/article/50/ · https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content

### 10.3 "Needs verification" list (fast-moving — re-confirm at build/PRD-lock)
- All subscription **prices and per-tier limits** (ChatGPT/Claude/Gemini/Perplexity/Copilot/Mistral/Poe) and our own Pro price + free-tier caps.
- **DeepSeek API rates** and promo end dates — DeepSeek is the main provider / free-tier default, so its pricing directly drives free-tier COGS.
- **Ads (mixed signal):** **ChatGPT expanding ads** (Free + Go, US→intl) vs **Perplexity abandoned ads** (Feb 2026, trust) — confirm both still current.
- **Model names/IDs** (GPT-5.x, Claude Opus/Sonnet/Haiku 4.x, Gemini 3.x) — churn fastest; pull from live model-list APIs.
- **Privacy defaults & retention windows** for incumbents; current ToS.
- **EU AI Act dates** (interaction-disclosure ~Aug 2 2026, firm; content-marking date legally unsettled — see §7.5/§9.6) and **penalty figures** — Art. 50 transparency violations are **€15M / 3%** (Art. 99); the **€35M / 7%** tier is Art. 5 prohibited-practices only. **CONTESTED dates:** May-2026 Digital Omnibus provisional pending Official Journal; content-marking date needs legal sign-off. (§7.5/§9.6).
- **US state AI laws** — CA SB 243 + AB 2013 (live 1/1/26; SB 243 is the main surviving obligation, companion/minors); **CO SB 205 dead** (stayed Apr 27 2026; repealed/replaced by SB 26-189 → effective Jan 1 2027, narrowed to ADMT for "consequential decisions" — likely out of scope; watch its Jan-2027 ADMT scope); Dec-2025 federal preemption EO (child-safety carve-outs survive; not self-executing). Confirm scope before locking compliance + the minors gate — **now the primary live US compliance determinant** (§7.5/§9.11).
- **Margin (~50–60%), inference share (~23%), conversion (single-digit %), stickiness (~21%)** benchmarks — directional; validate with our own cohorts post-launch.
- **AI-native retention (~40% GRR / 48% NRR), AI-tourist churn (~30% month-1, ~44% first-90-day), ARPU bands (sub-led $30–100+; hybrid $3–15)** — directional 2026 benchmarks; replace SaaS-optimistic D1/D7/D30 numbers (§6).
- **OpenRouter BYOK** — **5% of equivalent cost, first 1M BYOK req/mo free** (platform fee on non-BYOK credit usage now 5.5%); `[VERIFIED]` in review; re-confirm at integration.
- **2026 "no legal confidentiality" ruling** — narrow scope: **SDNY district opinion (Rakoff, Feb 2026) on privilege** + a discovery order (Stein, Jan 2026); not binding federal precedent. Market "minimal retention," not "confidential" (§7.3).
- **T3 Chat $8/mo** — mechanics overhauled in 2026 to a **4-hour-resetting usage bar + monthly Overage bucket** (no standard/premium credits; old "1,500 msgs / Claude 100" framing superseded); the **$8 price/feature anchor-to-beat** holds — re-confirm the usage-bar/overage model before external use.
