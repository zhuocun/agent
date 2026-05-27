# PRD 00 — Product Overview & Vision

**Product (working):** A transparent, multi-model, privacy-first AI chat for web and mobile (mobile-web first).
**Status:** Draft for build. This is the integrating document for the PRD set.
**Date:** 2026-05-27.
**Owner:** Product.

> **What this document is.** The single entry point to the PRD set. It states the vision, the problem, the target users, the positioning, the MVP scope (and what is explicitly deferred), and how the five workstream PRDs fit together. Domain detail lives in PRDs 01–05; this document does not duplicate it — it frames and links it.

---

## 1. Vision & positioning

**"Every major model in one place — where you see (and control) the cost and your data."**

We are building a consumer/prosumer AI chat product comparable to the web and mobile-web experiences of ChatGPT, Claude, Gemini, and Perplexity — but differentiated on a wedge none of them own cleanly: **multi-model choice + transparency + privacy + cost control.**

The market gap (see PRD 05 §1, §3):
- Incumbents are **single-model** (ChatGPT/Claude/Gemini) — you can't pick the best model per task in one place.
- Perplexity is **trust-damaged** on transparency (reported silent model downgrades).
- Aggregators (Poe) offer many models but **no privacy/transparency story**.
- Most incumbents **train on chats by default** or quietly extended retention, and **under-invest in mobile-web**.

We stack three defensible wedges — **model choice, transparency (which model answered + what it cost), and privacy/BYOK** — and win the core experience on **streaming/rendering fidelity, composer ergonomics, accessibility, and mobile-web polish** rather than feature breadth.

**What we are not:** a generic AI work assistant, inbox/calendar agent, or "do everything for your job" productivity suite. We are a **chat product** whose wedge is **multi-model choice + per-message cost/model transparency + privacy/BYOK** — winning on the core chat loop and trust surfaces, not feature breadth.

---

## 2. Problem & opportunity

Power users and developers increasingly use multiple AI models but are forced to juggle several single-model subscriptions, can't see which model produced an answer or what it cost, and have weak guarantees about data training/retention. There is room for a **model-agnostic, transparent, privacy-first** product that is also genuinely excellent on mobile-web — an area incumbents treat as an afterthought.

---

## 3. Goals & non-goals (product level)

### Goals
1. Establish a **defensible beachhead with power users / developers** on the multi-model + transparency + privacy wedge.
2. Ship a **credible MVP fast** that feels faster and more polished than incumbents on the fundamentals.
3. **Protect gross margin from day one** (aggressive model routing, metered free tier, BYOK) given AI-economics reality.
4. Make **trust a product surface**: always show the model used and the cost; never silently downgrade.
5. Stay **expandable**: keep a simple default mode so we can move down-market (casual) and up-market (teams) later without a rebuild.

### Non-goals (this phase)
- Competing on raw feature breadth at the commoditized ~$20 single-model tier.
- Casual mass-market acquisition, enterprise seats / SSO / SOC 2, and ads — all deferred (see PRD 05 §2.2, §4).
- Native mobile apps at launch (responsive web + PWA first; Capacitor later — PRD 03 §6).

---

## 4. Target users

| Priority | Persona | Why them |
|---|---|---|
| **Primary (MVP)** | **Power users / developers** | They value model choice, transparency, and cost control — our exact wedges — will pay or BYOK (protecting margin), and are cheap to reach. |
| **Secondary (fast-follow)** | **Privacy-conscious prosumers** (researchers, journalists, lawyers, EU users) | Drawn by no-train-by-default + transparency + GDPR posture; low incremental build cost. |
| **Deferred (P2+)** | Teams / orgs, then enterprise; casual mass-market | High value or high reach but long cycle / high COGS — expand once the beachhead is solid. |

Canonical persona/positioning detail: **PRD 05 §3.**

---

## 5. MVP scope (the headline decision)

The MVP is a **lean, text-core, multi-model chat** that is polished, accessible, and mobile-web-first. Two scope decisions anchor the set:

- **Lean text-core MVP.** P0 is a polished multi-model **text** chat + the transparency surface + the core UX. **Vision/PDF input, tool/function-calling, and live web-search/citations are deferred to P1** (designed-for now, built next).
- **BYOK ships at launch (P0).** Bring-your-own-key is the power-user margin de-risk and a privacy/cost-control wedge; the architecture designs encrypted key handling from day one.

### In the MVP (P0)
Streaming chat with stop-that-preserves-partial-output · interrupted-stream recovery (**partial + Continue/Regenerate**, not P1 replay) · streaming-safe markdown rendering (code+copy, KaTeX, GFM tables; **Mermaid diagrams → P1**) · collapsible reasoning panel · robust **text-only** composer + model-tier picker · **multi-provider model picker + per-message transparency (model used + token/cost)** · **transparency cost-accounting schema rich enough for tiered/threshold/cached/promo pricing + reasoning tokens, with a served-vs-requested model surface** · **typed multi-part message model** (data layer is full; renderer ships the text/code/reasoning/status subset) · heuristic auto-routing to a cheap (non-DeepSeek-hosted Western no-train) default model · xAI/Grok in the registry but excluded from Auto/default until data-policy review · conversation management (history, rename, delete, search) · core message actions (copy, regenerate, edit-last, thumbs) · system prompt + custom instructions · context management + usage/cost meter · structured outputs + schema validation · baseline safety/moderation · onboarding empty state · settings (theme, custom instructions, data controls; BYOK only for non-anonymous accounts) · share link + copy-as-markdown · keyboard shortcuts + `Cmd/Ctrl+K` palette · **accessibility baseline** · **P0 i18n baseline** (externalized strings, RTL/logical CSS, IME-safe composer) · **responsive web + PWA** · optimistic send + offline draft/queue + virtualized message list · **INP performance budget** (`scheduler.yield()` + rAF token-batching) · **no-train-by-default + retention controls + export/delete + AI-interaction disclosure** · **metered free tier + Pro (metered caps + transparent USD credit overage; price open — see §12) + BYOK** · **minimal metered-overage/credit primitive**.

### Deferred
- **P1 (fast-follow):** vision/PDF understanding + file attachments (including mobile attach/camera affordances), Mermaid diagram rendering, tool/function-calling + agentic loop, web-search + citations, Projects/Spaces, memory transparency, TTS/dictation, **explicit copy-on-branch ("branch in new chat")**, **native slash commands / prompt library + customizable keyboard shortcuts**, multi-format export, richer usage-credit/prepaid-pack UX, resumable-stream replay.
- **P2 (later):** deep parallel model comparison, artifacts/canvas, code execution, RAG, unified voice, image generation, custom assistants, MCP/connectors, trained routing, Capacitor native, teams/enterprise, ads (revisit at scale), in-thread alternate-response trees.

> **Dropped (not a phase):** native **pull-to-refresh** — it reloads the page and kills in-flight streams; superseded by `overscroll-behavior: contain` (PRD 03 §4.4).

Full reconciled phase table with dependencies: **PRD 05 §4.**

---

## 6. The PRD set (how to read it)

| PRD | Scope |
|---|---|
| **00 — Overview** (this doc) | Vision, problem, personas, positioning, MVP scope, decisions log |
| **[01 — Core Chat Experience](01-core-chat-experience.md)** | The chat UI/UX: streaming, reasoning panel, composer, rendering, conversation mgmt, message actions, onboarding, settings, sharing, shortcuts, a11y |
| **[02 — AI Capabilities & Model Layer](02-ai-capabilities.md)** | Provider abstraction + data-driven model registry, picker/routing, reasoning, context mgmt, structured outputs, safety; tools/search/vision (P1) |
| **[03 — Mobile & Cross-Platform](03-mobile-cross-platform.md)** | Responsive pane model, mobile composer/keyboard, gestures, offline, PWA, performance, delivery (PWA→Capacitor) |
| **[04 — Technical Architecture](04-technical-architecture.md)** | Stack, streaming/resumable, data model, provider/BYOK, auth/guest, storage, security/privacy NFRs, deployment |
| **[05 — Roadmap, Monetization, Metrics & NFRs](05-roadmap-monetization-metrics.md)** | Reconciled P0/P1/P2 roadmap, monetization, KPIs, accessibility/i18n/privacy/compliance NFRs, risks |
| **[06 — Design System & Visual Spec](06-design-system-visual-spec.md)** | Tokens, layout primitives, chat components, transparency/privacy chrome, visual acceptance criteria |
| **[07 — Transparency Contract](07-transparency-contract.md)** | End-to-end model + cost + served-vs-requested contract across registry, persistence, UI, metering, and share/export rules |
| **[08 — Error & Limit States](08-error-and-limit-states.md)** | Unified taxonomy and UX for stream failures, provider/app errors, quota limits, guest gates, BYOK failures, and offline states |

> **Numbering note:** PRD numbers ≠ research-file numbers (e.g. research-04 *AI capabilities* → PRD 02; research-02 *mobile* → PRD 03; research-03 *architecture* → PRD 04).

---

## 7. Cross-cutting principles

- **Transparency as product:** every assistant message shows which model answered and (where available) its token/cost. Never silently downgrade. This is a single **transparency contract** — a cost-accounting schema rich enough to be *true* (tiered/threshold/cached/promo pricing + reasoning tokens) plus a **served-vs-requested** model surface — cutting across PRD 01 (UX/display), PRD 02 (registry + pricing schema), PRD 04 (data-model capture), and PRD 07 (contract authority). It is a **P0 cross-cutting workstream with one named owner**, not three loosely-coupled pieces. **Public share exception:** unlisted read-only shares show model attribution but omit token/cost fields; in-app threads and private export retain full transparency.
- **Privacy-first:** no training on user chats by default; short configurable retention; one-click export/delete; optional no-telemetry mode.
- **Accessibility is a differentiation lever, not a follow-up:** labeled controls, ARIA live regions for streaming, full keyboard operability — incumbents have measured gaps (PRD 01 §5.7, PRD 05 §7.1).
- **Mobile-web first:** the product is excellent on a phone browser, not a shrunk desktop UI (PRD 03).
- **Multi-provider from day one** behind a thin abstraction + data-driven model registry; **never hardcode** model IDs/prices/context windows (PRD 02 §5).
- **MVP-fast-but-not-cornered:** pragmatic Vercel-native defaults, every external dependency behind a thin adapter so a later move is a migration, not a rewrite (PRD 04).

---

## 8. Technical foundation (summary)

**Next.js 16** (App Router + **Cache Components / PPR**) + **Vercel AI SDK v6** over **SSE** (`Output.object()` for structured outputs; `generateObject`/`streamObject` deprecated; resumable-stream replay is P1) + Postgres/Drizzle + Upstash (Redis + QStash) + **Better Auth** (committed; Auth.js dropped) with **guest/anonymous sessions** that upgrade/link + KMS-encrypted **BYOK** + Langfuse/OpenTelemetry, deployed on Vercel (Fluid Compute), responsive web + PWA. The data model uses a **typed multi-part message model** (ordered `text | reasoning | tool-call | tool-result | citation | interactive-block` parts; renderer ships the text/code/reasoning subset at P0) and captures **model + per-message effective/tiered cost** (the transparency contract — `cost_usd` + `cost_breakdown`, which also serves as the live spend ledger for the P0 metered-overage primitive) and `is_anonymous` users (guest sessions). Full detail and the reference architecture diagram: **PRD 04.**

---

## 9. Success metrics (summary)

Instrument from day one: activation / time-to-first-value · a first-week **"Day-1 success" activation funnel** (% completing a first-week success checklist — the strongest countermeasure to AI-tourist churn) · **time-to-first-token + per-model latency** · **AI-native retention (≈40% GRR / 48% NRR — model on AI-native, not SaaS-optimistic, benchmarks)** + D1/D7/D30 **plus task-recurrence** (AI usage is bursty) · DAU/MAU stickiness · messages/session · free→paid conversion / MRR / churn · **ARPU target bands (sub-led ~$30–100+; hybrid ~$3–15)** · **cost-per-message / gross margin / model-routing mix** · stream terminal events (`completed` / `stopped` / `error` / `interrupted`) · thumbs/regeneration/NPS. Definitions, benchmarks, and phase-2 metrics: **PRD 05 §6.**

---

## 10. Top risks (summary)

Commoditization vs incumbents · **aggregator price-compression** (T3 Chat @ $8/mo multi-model undercuts the same surface — the sharper near-term risk than generic commoditization) · **pricing-model risk** (shipping a flat sub while the 2026 market reprices to metered credits) · COGS/margin erosion ("inference whales", 30–100× token variance) · trust/privacy execution · smaller power-user TAM · upstream provider dependency · **EU AI Act compliance timeline** — AI-interaction disclosure is **firm at ~Aug 2 2026**, but **content-marking (Art. 50(2)) remains legally unsettled** (readings range Aug 2–Dec 2 2026; the May-2026 Digital Omnibus is provisional pending Official Journal) and **needs legal sign-off before EU-launch scope is locked** · **US state-law surface (beyond EU):** CA SB 243 + AB 2013 (live 1/1/26); **CO SB 205 is no longer a live gate** (enforcement stayed Apr 2026; repealed/replaced by SB 26-189 → effective Jan 1 2027, narrowed to ADMT) — the US disclosure gate now rests on CA SB 243 + good practice. Mitigations: **PRD 05 §8.**

---

## 11. Decisions log

| # | Decision | Rationale |
|---|---|---|
| D1 | **Positioning = transparent, multi-model, privacy-first chat for power users.** | Open market gap; stacks three defensible wedges vs single-model / trust-damaged / no-privacy incumbents. |
| D2 | **Multi-provider model picker + per-message transparency is IN the MVP** (not a later phase). | It is the core wedge and is cheap via the provider-abstraction layer + gateway. (Resolved a research-01 vs research-05 conflict in favor of 05.) |
| D3 | **Lean text-core MVP:** vision/PDF, tool-calling, and web-search are **P1**, not P0. | Focus the MVP on a polished, accessible, mobile-web text chat; defer heavier multimodal/agentic/retrieval infra. (Resolved a PRD-02 vs PRD-05 P0/P1 conflict.) |
| D4 | **BYOK ships at launch (P0).** | Power-user margin de-risk + privacy/cost-control wedge; architecture designs encrypted key handling from day one. (Aligned PRDs 02/04/05.) |
| D5 | **Delivery = responsive web + PWA now; Capacitor native later** (trigger-based). React Native rejected (full UI rewrite). | Single codebase, fastest to market, ~100% reuse into Capacitor when iOS push / app-store / durable-offline triggers fire. |
| D6 | **Transparency contract = a single P0 cross-cutting workstream with one named owner**, spanning PRD 01 (UX/display), PRD 02 (registry + cost-accounting schema), PRD 04 (data-model capture). The cost-accounting schema must be rich enough to be *true* — **tiered/threshold/cached/promo pricing + reasoning-token cost** — plus a **served-vs-requested model** surface with reason-for-substitution. | It is the core wedge and was left generic across three PRDs, so the promise wasn't end-to-end true; a scalar price is *wrong on exactly the high-value long-context turns*. One owner, schema as the spine. |
| D7 | **Typed multi-part message model in the P0 data layer** (ordered `text \| reasoning \| tool-call \| tool-result \| citation \| interactive-block` parts); P0 renders only the text/code/reasoning subset. | Cheapest high-leverage decision in the set — de-risks tools/citations/interactive-viz/generative-UI (all P1/P2) in one move; modeling a message as one markdown string guarantees a P1 refactor. Made once in the data model (PRD 04), referenced by PRD 01. |
| D8 | **Minimal metered-overage / transparent USD credit primitive in P0** (was P1): Pro = explicit metered caps + transparent overage, not a flat "generous limits" plan. | The 2026 market reprices to usage/credits (Copilot 6/1/26, Anthropic, Cursor); a flat sub re-creates the "inference whale" risk the PRDs warn about. The P0 cost meter is already the spine; enforcement owned by PRD 04, monetization decision by PRD 05. Resolves the PRD 05 §5.1-vs-§5.2 flat-vs-metered inconsistency. |
| D9 | **Foundation committed: AI SDK v6 (GA 2025-12-22; SSE, `Output.object()` for structured outputs) + Next.js 16 (Cache Components/PPR) + Better Auth.** Auth.js dropped (security-patch-only); `generateObject`/`streamObject` deprecated. | Resolves the open v5-vs-v6 and 3-way auth questions; avoids shipping the MVP against a deprecated API or a deprecated auth path (PRD 04 §4/§5.5/§9). |
| D10 | **Explicit copy-on-branch ("branch in new chat") → P1** (was P2); in-thread alternate-response trees stay P2+. | Corrects a factual error (incumbents *shipped* explicit branching, didn't retreat); low-risk copy model that directly serves the dev/power-user beachhead (PRD 01 §4.6/§8). |
| D11 | **Free-tier default = a non-DeepSeek-hosted, Western no-train route** (Gemini Flash / OpenAI-mini / Claude Haiku / Mistral-EU class; PRD 02 owns final pick). DeepSeek-hosted API dropped as a default; Western-hosted open weights remain a separate P2+ line. | DeepSeek-hosted API is a poor privacy-first default (government/enterprise bans + Italy consumer block + data-in-China); decision *narrowed*, not fully answered — final route depends on the `data_policy` no-train guarantee (PRD 02 §5.3). |
| D12 | **Mermaid interactive rendering → P1; P0 ships code/math/tables only.** | Resolves cross-PRD scope drift and avoids P0 bundle bloat. Fenced Mermaid may render as code until P1. |
| D13 | **Mobile attach/camera UI → P1 with vision/PDF; P0 mobile composer is text-only.** | Resolves mobile PRD attach affordance drift against the lean text-core MVP. |
| D14 | **P0 interrupted-stream recovery ≠ P1 resumable replay.** | P0 preserves partial output and offers Continue/Regenerate; P1 replays buffered deltas from the same stream id. Keeping these separate avoids billing, persistence, and UX bugs. |

---

## 12. Open questions

Each PRD carries its own open-questions section; the cross-cutting product/business ones (Pro price point, BYOK monetization, free-tier caps, EU launch timing vs AI-Act dates, secondary-persona timing, RAG-pull-forward, native trigger, ads-at-scale, minors/companion personas) are in **PRD 05 §9**. Remaining technical spikes (virtualization × streaming, iOS keyboard, Better-Auth guest-link with no data loss, Postgres host, Vercel max-duration) are in **PRD 03 §9 / PRD 04 §9**.

**Contested — FLAGGED, not decided here** (per product-owner policy; needs the named owner / legal before lock):
- **Exact Pro price (~$15–20 vs T3 Chat's $8 anchor).** Our band is 2–2.5× the $8 multi-model floor — justify the premium (privacy + a11y + mobile-web + true cost transparency) or reprice (PRD 05 §9.1).
- **EU AI Act content-marking date (Aug 2 vs Dec 2 2026),** clouded by a May-2026 Council/Parliament provisional amendment reshuffling deadlines — **needs legal sign-off** before EU-launch scope is locked (PRD 04 §9 / PRD 05 §7.5/§9.6).
- **Whether we serve minors / offer companion-style personas** — triggers CA SB 243 + surviving child-safety carve-outs (crisis protocols, break reminders, minor protections); needs explicit product + legal decision (PRD 05 §7.5/§9.11).

**Newly resolved by the fresh-research + review pass:** AI SDK **v6** (not v5) committed; **Better Auth** committed (Auth.js dropped); free-tier default **narrowed** to a non-DeepSeek-hosted Western no-train route (final route open, PRD 02 §9.9); **metered Pro + P0 metered-overage primitive** confirmed (PRD 05 §9.4). See the decisions log (§11, D6–D11).

---

## 13. References

- Workstream PRDs: [01](01-core-chat-experience.md) · [02](02-ai-capabilities.md) · [03](03-mobile-cross-platform.md) · [04](04-technical-architecture.md) · [05](05-roadmap-monetization-metrics.md) · [06](06-design-system-visual-spec.md) · [07](07-transparency-contract.md) · [08](08-error-and-limit-states.md)
- **Traceability:** competitive/research findings are summarized and mapped in PRD 05 §10.1. Original `research-*.md` files are not checked into this repo; PRD file + section references are authoritative for build/review.
