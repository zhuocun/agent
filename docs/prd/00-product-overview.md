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

The market gap (see PRD 05 §1, §3 and `docs/research/05-competitive-monetization.md`):
- Incumbents are **single-model** (ChatGPT/Claude/Gemini) — you can't pick the best model per task in one place.
- Perplexity is **trust-damaged** on transparency (reported silent model downgrades).
- Aggregators (Poe) offer many models but **no privacy/transparency story**.
- Most incumbents **train on chats by default** or quietly extended retention, and **under-invest in mobile-web**.

We stack three defensible wedges — **model choice, transparency (which model answered + what it cost), and privacy/BYOK** — and win the core experience on **streaming/rendering fidelity, composer ergonomics, accessibility, and mobile-web polish** rather than feature breadth.

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
Streaming chat with stop-that-preserves-partial-output · streaming-safe markdown rendering (code+copy, KaTeX, tables, mermaid) · collapsible reasoning panel · robust **text** composer + model-tier picker · **multi-provider model picker + per-message transparency (model used + token/cost)** · heuristic auto-routing to a cheap default model · conversation management (history, rename, delete, search) · core message actions (copy, regenerate, edit-last, thumbs) · system prompt + custom instructions · context management + usage/cost meter · structured outputs + schema validation · baseline safety/moderation · onboarding empty state · settings (theme, custom instructions, data controls) · share link + copy-as-markdown · keyboard shortcuts + `Cmd/Ctrl+K` palette · **accessibility baseline** · **responsive web + PWA** · optimistic send + offline draft/queue + virtualized message list · **no-train-by-default + retention controls + export/delete + AI-interaction disclosure** · **metered free tier + Pro (~$15–20/mo) + BYOK**.

### Deferred
- **P1 (fast-follow):** vision/PDF understanding + file attachments, tool/function-calling + agentic loop, web-search + citations, deep parallel model comparison, Projects/Spaces, memory, TTS/dictation, branching, multi-format export, usage credits, resumable-stream replay.
- **P2 (later):** artifacts/canvas, code execution, RAG, unified voice, image generation, custom assistants, MCP/connectors, trained routing, Capacitor native, teams/enterprise, ads (revisit at scale).

Full reconciled phase table with dependencies: **PRD 05 §4.**

---

## 6. The PRD set (how to read it)

| PRD | Scope | Source research |
|---|---|---|
| **00 — Overview** (this doc) | Vision, problem, personas, positioning, MVP scope, decisions log | synthesis of all |
| **[01 — Core Chat Experience](01-core-chat-experience.md)** | The chat UI/UX: streaming, reasoning panel, composer, rendering, conversation mgmt, message actions, onboarding, settings, sharing, shortcuts, a11y | `research/01-features-ux.md` |
| **[02 — AI Capabilities & Model Layer](02-ai-capabilities.md)** | Provider abstraction + data-driven model registry, picker/routing, reasoning, context mgmt, structured outputs, safety; tools/search/vision (P1) | `research/04-ai-capabilities.md` |
| **[03 — Mobile & Cross-Platform](03-mobile-cross-platform.md)** | Responsive pane model, mobile composer/keyboard, gestures, offline, PWA, performance, delivery (PWA→Capacitor) | `research/02-mobile-responsive.md` |
| **[04 — Technical Architecture](04-technical-architecture.md)** | Stack, streaming/resumable, data model, provider/BYOK, auth/guest, storage, security/privacy NFRs, deployment | `research/03-architecture.md` |
| **[05 — Roadmap, Monetization, Metrics & NFRs](05-roadmap-monetization-metrics.md)** | Reconciled P0/P1/P2 roadmap, monetization, KPIs, accessibility/i18n/privacy/compliance NFRs, risks | `research/05-competitive-monetization.md` |

> **Numbering note:** PRD numbers ≠ research-file numbers (e.g. research-04 *AI capabilities* → PRD 02; research-02 *mobile* → PRD 03; research-03 *architecture* → PRD 04). Each PRD cites its own source research.

---

## 7. Cross-cutting principles

- **Transparency as product:** every assistant message shows which model answered and (where available) its token/cost. Never silently downgrade.
- **Privacy-first:** no training on user chats by default; short configurable retention; one-click export/delete; optional no-telemetry mode.
- **Accessibility is a differentiation lever, not a follow-up:** labeled controls, ARIA live regions for streaming, full keyboard operability — incumbents have measured gaps (PRD 01 §5.7, PRD 05 §7.1).
- **Mobile-web first:** the product is excellent on a phone browser, not a shrunk desktop UI (PRD 03).
- **Multi-provider from day one** behind a thin abstraction + data-driven model registry; **never hardcode** model IDs/prices/context windows (PRD 02 §5).
- **MVP-fast-but-not-cornered:** pragmatic Vercel-native defaults, every external dependency behind a thin adapter so a later move is a migration, not a rewrite (PRD 04).

---

## 8. Technical foundation (summary)

Next.js (App Router) + Vercel AI SDK over **SSE** (resumable-stream replay is P1) + Postgres/Drizzle + Upstash (Redis + QStash) + Better Auth (with **guest/anonymous sessions** that upgrade/link) + KMS-encrypted **BYOK** + Langfuse/OpenTelemetry, deployed on Vercel (Fluid Compute), responsive web + PWA. The data model captures **model + token + cost per message** (the transparency contract) and `is_anonymous` users (guest sessions). Full detail and the reference architecture diagram: **PRD 04.**

---

## 9. Success metrics (summary)

Instrument from day one: activation / time-to-first-value · **time-to-first-token + per-model latency** · D1/D7/D30 **plus task-recurrence** (AI usage is bursty) · DAU/MAU stickiness · messages/session · free→paid conversion / MRR / ARPU / churn · **cost-per-message / gross margin / model-routing mix** · thumbs/regeneration/NPS. Definitions, benchmarks, and phase-2 metrics: **PRD 05 §6.**

---

## 10. Top risks (summary)

Commoditization vs incumbents · COGS/margin erosion ("inference whales", 30–100× token variance) · trust/privacy execution · smaller power-user TAM · upstream provider dependency · EU AI Act compliance timeline (AI-interaction disclosure ~Aug 2026; content-marking ~Dec 2026). Mitigations: **PRD 05 §8.**

---

## 11. Decisions log

| # | Decision | Rationale |
|---|---|---|
| D1 | **Positioning = transparent, multi-model, privacy-first chat for power users.** | Open market gap; stacks three defensible wedges vs single-model / trust-damaged / no-privacy incumbents. |
| D2 | **Multi-provider model picker + per-message transparency is IN the MVP** (not a later phase). | It is the core wedge and is cheap via the provider-abstraction layer + gateway. (Resolved a research-01 vs research-05 conflict in favor of 05.) |
| D3 | **Lean text-core MVP:** vision/PDF, tool-calling, and web-search are **P1**, not P0. | Focus the MVP on a polished, accessible, mobile-web text chat; defer heavier multimodal/agentic/retrieval infra. (Resolved a PRD-02 vs PRD-05 P0/P1 conflict.) |
| D4 | **BYOK ships at launch (P0).** | Power-user margin de-risk + privacy/cost-control wedge; architecture designs encrypted key handling from day one. (Aligned PRDs 02/04/05.) |
| D5 | **Delivery = responsive web + PWA now; Capacitor native later** (trigger-based). React Native rejected (full UI rewrite). | Single codebase, fastest to market, ~100% reuse into Capacitor when iOS push / app-store / durable-offline triggers fire. |

---

## 12. Open questions

Each PRD carries its own open-questions section; the cross-cutting product/business ones (Pro price point, BYOK monetization, free-tier caps, default free model, EU launch timing vs AI-Act dates, RAG-pull-forward, native trigger, ads-at-scale) are in **PRD 05 §9**. Key technical spikes (virtualization × streaming, iOS keyboard, auth choice, AI SDK v5 vs v6, Vercel max-duration) are in **PRD 03 §9 / PRD 04 §9**.

---

## 13. References

- Workstream PRDs: [01](01-core-chat-experience.md) · [02](02-ai-capabilities.md) · [03](03-mobile-cross-platform.md) · [04](04-technical-architecture.md) · [05](05-roadmap-monetization-metrics.md)
- Research: `docs/research/01-features-ux.md` · `02-mobile-responsive.md` · `03-architecture.md` · `04-ai-capabilities.md` · `05-competitive-monetization.md`
