# PRD 05 — Roadmap, Monetization, Metrics & Non-Functional Requirements

**Product:** A transparent, multi-model, privacy-first AI chat for web and mobile (mobile-web first).
**Owner:** Product Strategy
**Status:** Draft for stakeholder review
**Date:** 2026-05-27
**Source research:** `docs/research/05-competitive-monetization.md` (primary), with cross-cutting roadmap inputs from research files 01 (§15), 02 (§13), 03 (§13–14), 04 (§12).

> **Verification flags.** Every dollar figure, per-tier limit, model name, and regulatory date in this PRD is **fast-moving** and must be re-verified against first-party vendor/regulatory pages before it is committed to a build or quoted externally. Items needing re-verification are tagged `[VERIFY]`. A consolidated list lives in §10.

---

## 1. Summary & Purpose

This PRD consolidates the four product workstreams (features/UX, mobile, architecture, AI capabilities) plus the competitive/monetization research into **one coherent execution plan**: a phased roadmap (P0/P1/P2), a monetization recommendation with cost economics, the day-one metrics program, and product-level non-functional requirements (accessibility, i18n, privacy, security/trust, compliance).

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
- **Not** shipping ads (needs scale; trust-risky; Perplexity retreated from it). `[VERIFY]`
- **Not** building heavy parallel model comparison, artifacts/canvas, RAG, memory, voice, image-gen, MCP, or native apps in P0.

---

## 3. Target Personas & Positioning (canonical)

> This section is the **canonical persona/positioning statement** that other PRDs reference.

### 3.1 Positioning statement
**"The transparent, multi-model, privacy-first AI chat — every major model in one place, where you see (and control) the cost and your data."**

The open market gap is **multi-model + transparency + privacy + cost control**. Incumbents are single-model (ChatGPT/Claude/Gemini), trust-damaged on transparency (Perplexity's silent model downgrades), or bare aggregators without a privacy/transparency story (Poe). We stack three defensible wedges (model choice, transparency, BYOK/privacy) rather than fight at the commoditized $20 all-rounder tier.

### 3.2 Personas

| Priority | Persona | Core needs | Willingness to pay | Cost to serve |
|---|---|---|---|---|
| **Primary (MVP)** | **Power users / developers** | Model choice, transparency, cost control, BYOK, keyboard speed, fast/polished core | Medium–High (pay for control/savings) | **Low** if BYOK/usage-based |
| **Secondary (fast-follow)** | **Privacy-conscious prosumers** (researchers, journalists, lawyers, EU users) | No-train-by-default, citations/transparency, GDPR posture | Medium | Low–Medium |
| **Defer (P2+)** | Teams / small orgs | Shared workspace, admin, no-train contracts, SSO, billing | High (per seat) | Medium; long sales cycle |
| **Defer (later)** | Enterprise | Data residency, audit, SSO, DPA | Highest | High compliance burden |
| **Defer (later)** | Casual mass-market | Simple, fast, free, mobile | Low (mostly free) | High (subsidized) |

2026 guidance: segment by **sophistication / automation preference**, not demographics. Our differentiation maps directly onto the power-user segment, which converts and is cheap to serve via BYOK/usage-based pricing. The bet: a defensible, profitable beachhead beats subsidizing casual users against incumbents. **Keep a simple default mode** so down-market expansion is a setting, not a rebuild.

---

## 4. Phased Roadmap (P0 / P1 / P2)

### 4.1 MVP scope statement (rough)

> **MVP (P0):** A fast, polished, mobile-web-first responsive chat app (Next.js + AI SDK over SSE, PWA layer) that nails streaming + streaming-safe markdown rendering, composer ergonomics, conversation management, core message actions, a collapsible reasoning panel, onboarding, basic settings, share/export, a command palette, and an accessibility baseline — delivered over a **multi-provider model picker with a visible "model used + token cost" transparency surface** (the core wedge, cheap via the provider-abstraction layer). It launches with a **no-train-by-default privacy posture**, **AI-interaction disclosure**, a **metered free tier** plus a **Pro subscription (~$15–20/mo)** and a **BYOK option (no token markup)**, governed by aggressive model routing to protect margin. It targets power users/developers; everything heavier (deep comparison, artifacts, search/RAG, memory, voice, image-gen, MCP, native, enterprise) is explicitly later.

### 4.2 Tension resolution (explicit)
- **Multi-provider model picker + transparency → P0.** It is the wedge, and the architecture (AI SDK provider layer + Vercel AI Gateway / OpenRouter breadth) makes a basic picker and per-message cost/model display cheap. Integrate Anthropic + OpenAI + Gemini directly for primary tiers and OpenRouter for breadth/fallback. `[VERIFY]` model IDs/pricing.
- **Deep *parallel* comparison (same prompt → N models side by side) → P1.** The picker is P0; running and diffing multiple models in one view is a heavier, later layer.
- **Artifacts/canvas, web-search/RAG, memory, voice, image-gen, MCP, Capacitor native, enterprise → P1/P2** (high infra cost, mobile-web complexity, or long sales cycle).

### 4.3 Feature → phase table (reconciled across all five research files)

Legend: **P0** = MVP / must-have to be credible · **P1** = fast-follow · **P2** = later/differentiator/heavier infra. The **Source** column cites *research files* (`docs/research/0X`), whose numbering differs from the PRD numbering — e.g. research-04 (AI capabilities) → **PRD 02**, research-02 (mobile) → **PRD 03**, research-03 (architecture) → **PRD 04**. The owning workstream PRD's tag governs; this table reflects the **reconciled scope after the lean-text-core MVP decision** (vision/PDF, tool-calling, and web-search are P1; BYOK is P0).

| Feature / capability | Phase | Source | Notes / dependencies |
|---|---|---|---|
| Token streaming with Stop/Abort (preserves partial output) | **P0** | 01 §15, 04 §12 | Non-negotiable. SSE + Stop/abort + `Stream`-table schema = **P0**; resumable-stream *replay* = **P1** (PRD 04 §5.1). |
| Streaming-safe markdown renderer (code+copy, KaTeX, GFM tables, Mermaid) | **P0** | 01 §15 | Biggest perceived-quality lever; adopt Streamdown-style renderer. |
| Robust composer (multiline, send/stop, text paste, model picker) | **P0** | 01 §15 | Highest-leverage surface. Mobile: `dvh`, safe-area, auto-grow. **Image/file attach + drag-drop = P1** (lands with vision/PDF). |
| **Multi-provider model picker (capability tiers: Fast/Smart/Pro)** | **P0** | 04 §12, 05 §8 | **Core wedge.** Provider abstraction + Gateway/OpenRouter. |
| **Transparency surface: model used + per-message token cost** | **P0** | 05 §4/§8 | Core wedge + trust. Avoid "silent downgrade." |
| Basic auto model-routing (heuristic; cheap default model) | **P0** | 04 §12, 05 §3 | Margin lever; route easy queries to cheap models. |
| Conversation management (new chat, time-grouped history, rename, delete, search) | **P0** | 01 §15 | Full-text search across history. |
| Core message actions (copy, regenerate, edit-last + re-run, thumbs up/down) | **P0** | 01 §15 | Note ChatGPT's 2026 retreat from deep editing — design conservatively. |
| Collapsible reasoning/status panel (auto-open, "Thought for Xs", auto-collapse) | **P0** | 01 §15, 04 §12 | Correct token/cost accounting for thinking tokens. |
| System prompt + user custom instructions | **P0** | 04 §12 | Persona/tone/preferences. |
| Onboarding empty state (greeting + 3–4 suggested-prompt cards) | **P0** | 01 §15, 04 §11 | Cheap, high activation impact. |
| Settings basics (light/dark/system theme, custom instructions, data controls) | **P0** | 01 §15 | Includes training opt-out / clear history. |
| Share link (unlisted) + copy-as-markdown export | **P0** | 01 §15 | Lightweight; richer export later. |
| Keyboard shortcuts + `Cmd/Ctrl+K` command palette | **P0** | 01 §15 | Most power-user value cheaply. |
| Accessibility baseline (labeled buttons, ARIA live regions, keyboard, announced status) | **P0** | 01 §13/§15, 02 §12 | Differentiation lever — incumbents have measured gaps. |
| Responsive mobile-web layout + PWA layer (manifest, SW, app-shell cache) | **P0** | 02 §13 | Fluid panes + adaptive shell; Android web push; iOS A2HS coachmark. |
| Optimistic send + IndexedDB drafts/queue + retry w/ backoff | **P0** | 02 §13 | Resilience on mobile networks. |
| Virtualized message list + smart auto-scroll + scroll-to-bottom | **P0** | 02 §13 | Top technical risk (virtualization × streaming) — needs spike. |
| Context management (token counting + visible usage/cost meter) | **P0** | 04 §12 | Underpins transparency + routing. |
| Structured outputs / JSON mode + schema validation | **P0** | 04 §12 | Needed for reliable tool args + future structured features. |
| Baseline safety (input/output moderation, prompt-injection-aware design) | **P0** | 04 §12, 05 §6 | Least-privilege; abuse-reporting path. |
| **AI-interaction disclosure** ("you're talking to an AI") | **P0** | 05 §6 | EU AI Act transparency (Aug 2026 `[VERIFY]`); build in from start. |
| **No-train-by-default + short retention + one-click export/delete** | **P0** | 05 §6 | Privacy acquisition hook; in-product retention disclosure. |
| Metered free tier + Pro subscription + BYOK | **P0** | 05 §8 | See §5. Billing/metering/key-encryption infra. |
| Vision (image input) + PDF/document understanding | **P1** | 04 §12 | Low marginal effort on multimodal models; meter usage. |
| Tool/function calling + basic agentic loop (max-iteration caps) | **P1** | 04 §12 | Foundation for search, analysis, MCP. |
| Web search/grounding + inline citations + source cards + follow-ups | **P1** | 01 §15, 04 §12 | Perplexity-style trust layer; couples to retrieval infra. |
| **Deep parallel model comparison** (same prompt → N models) | **P1** | 05 §4 | Heavy-comparison layer over the P0 picker. |
| Projects/Spaces (named container + pinned instructions + files + grouped chats) | **P1** | 01 §15 | Table-stakes for serious users; post-MVP layer over history. |
| Persistent cross-chat memory (transparent, editable, consent/deletion) | **P1** | 04 §12 | High retention value; privacy complexity → fast-follow. |
| Pin/archive, tagging/folders | **P1** | 01 §15 | Organization layer. |
| Read-aloud (TTS) + voice input (dictation) | **P1** | 01 §15, 04 §12 | Accessibility/mobile dictation; Web Speech API as enhancement. |
| Multi-format export (PDF/.docx/Markdown) | **P1** | 01 §15 | Richer than P0 copy-as-markdown. |
| Branching / alternate responses (explicit "branch from here") | **P1** | 01 §15 | Non-trivial data model; design conservatively. |
| Optional usage credits (prepaid, transparent USD) | **P1** | 05 §8 | For occasional heavy users who won't subscribe. |
| Usage credits | **P1** | 05 §8 | See §5; adds cognitive load — gate behind defaults. |
| Artifacts/Canvas (side panel, live preview, versioning, copy/download) | **P2** | 01 §15 | High wow, high cost; awkward on mobile-web (full-screen fallback). |
| Sandboxed code execution / data analysis | **P2** | 01 §15, 04 §12 | Builds on artifacts + agentic loop. |
| RAG over user documents (pgvector → Pinecone at scale) | **P2** | 03 §13, 04 §12 | Large-context can substitute early; build when corpora/auditability needed. |
| Unified voice mode (speech-to-speech) | **P2** | 01 §15, 04 §12 | Latency/infra; pulls WebSockets/Durable Objects forward. |
| Image / media generation | **P2** | 01 §15, 04 §12 | Separate models/cost; not core to chat. |
| Custom assistants (Gems/GPT-style) + template gallery | **P2** | 01 §15 | Prompt library is a cheap fast-follow; full assistants later. |
| MCP / connectors / plugins | **P2** | 04 §12 | Powerful but big security surface (injection risk). |
| Advanced auto-routing (trained classifier) | **P2** | 04 §12 | Heuristic routing suffices until scale/cost pressure. |
| Capacitor native wrapper (iOS/Android apps) | **P2** | 02 §13 | Trigger: iOS push re-engagement KPI, app-store presence, durable offline. |
| Team/enterprise seats, SSO/SAML, SOC 2, DPA, no-train contracts | **P2** | 05 §3/§9 | High ACV, long cycle, compliance burden. |
| Ads on free tier | **P2 (revisit)** | 05 §2 | Needs massive scale; trust risk; revisit only at scale. |

### 4.4 Dependency notes
- **Provider-abstraction layer** (P0) is the spine: model picker, routing, transparency meter, BYOK, and later parallel comparison all sit on it. Build it thin so OpenRouter/LiteLLM can swap in without app changes.
- **Streaming spine:** SSE token streaming + Stop/abort + the `Stream`-table schema are **P0**; **resumable-stream replay is P1** (PRD 04 §5.1, PRD 01 §4.1). The orphaned-run reconciliation (Stream row + Redis abort channel + reaper) is designed in P0 so long responses don't break on serverless timeouts.
- **Tool/function-calling loop** (P1) is a prerequisite for **web search** (P1), **data analysis** (P2), and **MCP** (P2).
- **Agentic loop + artifacts** precede **sandboxed code execution** (P2).
- **Vision/file understanding** (P1) precedes **RAG** (P2) — start with large-context "attach a doc" before full retrieval.
- **Capacitor native** (P2) reuses the P0 PWA codebase (~100% reuse) — do not build a separate app.
- **EU AI Act content-marking** (machine-readable AI-content labels) should be designed alongside any **image/media generation** (P2) and is due **Dec 2, 2026** `[VERIFY]`; **AI-interaction disclosure** is P0 (due Aug 2026 `[VERIFY]`).

---

## 5. Monetization Model

### 5.1 Recommendation
**Hybrid: freemium funnel + Pro subscription (~$15–20/mo) + BYOK (no token markup) + optional usage credits — all governed by aggressive model routing.** `[VERIFY]` price point against the live ~$20 market anchor.

- **Free tier (metered):** message/token caps with a cheap default model (DeepSeek/Flash class) to cap COGS and feed the funnel. **No training on chats by default** (privacy as an acquisition hook).
- **Pro subscription (~$15–20/mo):** all frontier models, higher limits, the transparency dashboard (model used + token cost), and (P1) multi-model comparison. Price at/slightly below the $20 anchor.
- **BYOK option:** user plugs in their own provider keys; **we add zero token markup**. Monetize via a small flat platform fee or bundle into Pro. Near-zero COGS revenue line that converts power users cheaply and **directly de-risks our biggest margin threat**.
- **Usage credits (P1):** optional prepaid credits for occasional heavy users who don't want a subscription (Poe-style, but with transparent USD pricing).
- **Defer:** ads (scale + trust risk) and enterprise seats (P2; long cycle/compliance).

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
| ChatGPT | Yes (ads in US) | Go ~$8; **Plus ~$20/mo** | Pro ~$100 / ~$200/mo | Business ~$25/seat; Enterprise custom | Per-token API |
| Claude | Yes (limited) | **Pro ~$20/mo** | Max ~$100 / ~$200/mo | Team (min 5 seats); Enterprise ~$20+/seat | Per-token API |
| Gemini | Yes | AI Plus ~$13.99; **AI Pro ~$19.99/mo** | AI Ultra ~$100 / ~$200/mo | Workspace/Enterprise | Vertex/Gemini API |
| Perplexity | Yes | **Pro ~$20/mo** | Max ~$200; Edu Pro ~$10 | Enterprise ~$40–$325/seat | Sonar API |
| Copilot | Limited | **Pro ~$20/seat** (needs M365) | — | Business ~$18→$21; Enterprise ~$30/seat | Azure OpenAI API |
| Mistral Le Chat | Yes | **Pro ~$14.99/mo** | — | Team ~$24.99/seat | Per-token API (separate) |
| DeepSeek | **Yes, no paywall** | — | — | — | Ultra-cheap per-token; ~98% cache discount |
| Poe | Yes (points) | ~$4.99 / ~$19.99 | ~$49.99 / ~$99.99 / ~$249.99 | Teams ~$249.99 | Dev API (points) |
| OpenRouter (BYOK) | n/a | n/a | n/a | n/a | **+5% of upstream cost** (`[VERIFIED]` in research) |
| TypingMind (BYOK) | n/a | **~$79 one-time** | n/a | Team licenses | Pay providers directly |
| **Our product (proposed)** | **Metered, cheap default model** | **Pro ~$15–20/mo** | (usage credits P1) | Team/Enterprise = P2 | **BYOK at $0 markup** + optional credits |

**Read:** the consumer anchor is ~$20/mo "Plus/Pro"; prosumer tiers ($100/$200) are **usage multipliers, not better models**. We price Pro at/below the anchor and differentiate on transparency, model choice, and BYOK rather than on a higher price.

### 5.4 Free-tier metering strategy (to cap COGS)
1. **Cheap default model** (DeepSeek/Flash class) for all free traffic; frontier models gated to Pro or BYOK. `[VERIFY]` model IDs.
2. **Daily/rolling message + token caps** with clear in-UI remaining-quota display (doubles as transparency). `[VERIFY]` exact caps via cost modeling against single-digit conversion.
3. **Routing-by-default:** classify easy queries to the cheapest capable model; escalate only on explicit user choice or detected complexity.
4. **Reasoning/thinking gated:** thinking tokens bill as output — gate behind a tier/toggle and meter visibly.
5. **Multimodal gated:** vision/file/voice carry 5–10x infra impact — meter and gate (P1+).
6. **Guest rate-limiting:** cap anonymous traffic to control spend before account creation.

### 5.5 Tradeoffs
- **Pro:** protects margins (BYOK + routing + metering), differentiates on transparency/privacy, multiple revenue lines, low capital risk, no dependence on massive scale.
- **Con:** more complex pricing UX than a single $20 plan; BYOK has setup friction and a smaller early TAM; multi-model creates **dependency on upstream provider pricing/terms**; usage credits add cognitive load.
- **Mitigation:** strong defaults + a simple "just give me the best answer" mode hide complexity for less-sophisticated users while power users get the dials.

---

## 6. Success Metrics & KPIs

> **AI usage is bursty/task-driven** — a user may run 50 queries then vanish for weeks. Classic 7/30-day windows are weaker signals here, so instrument **task-recurrence** alongside standard retention. `[VERIFY]` benchmarks.

### 6.1 Day-one must-haves (instrument from launch)

| Category | Metric | Rough benchmark / target | Why |
|---|---|---|---|
| **Activation** | % new users reaching first successful response / first "valued" task; **time-to-first-value** | Track + improve | Leading indicator of everything downstream. |
| **Latency (UX quality)** | **TTFT (time-to-first-token)** + full-response latency, **per model** | Lower is better; per-model SLAs | Core chat UX quality; informs routing. |
| **Retention** | D1 / D7 / D30 **+ task-recurrence interval** | ~25–30% / ~15–18% / ~5–8% `[VERIFY]` | Classic retention + bursty-usage correction. |
| **Engagement** | DAU, MAU, **DAU/MAU stickiness** | 20%+ = high; **~21% NA AI norm** `[VERIFY]` | Habit signal. |
| **Conversation depth** | Messages/session, conversation length, sessions/user | Track trend | Value-per-session proxy. |
| **Monetization** | **Free→paid conversion**, MRR, ARPU, churn | Plan single-digit % conversion `[VERIFY]` | Revenue health. |
| **Unit economics** | **Cost-per-user / cost-per-message (token COGS)**, gross margin per tier, **model-routing mix** | Margin target ~50–60% `[VERIFY]` | Existential given §5; routing mix is the lever. |
| **Quality/trust** | Thumbs up/down, **regeneration rate**, NPS/CSAT | Track + alert on spikes | Output quality + silent-downgrade detection. |

### 6.2 Phase-2 / later metrics
- Cohorted **LTV:CAC**.
- **Expansion / seat growth** (teams).
- **Feature-adoption funnels** (artifacts, search, memory).
- **Model-comparison usage** (validates multi-model positioning).
- **Accessibility / i18n usage by locale** (validates a11y + localization investment; localization can affect up to ~30% of retention in multilingual platforms `[VERIFY]`).
- **BYOK adoption rate** (margin de-risking) and credit-pack purchase behavior.

### 6.3 Instrumentation notes
- Capture **model used + token cost per message** server-side from day one (also powers the user-facing transparency surface).
- Tie every cost metric to the **routing decision** so margin regressions are attributable to model mix.
- Observability via Langfuse + OpenTelemetry (per PRD 04) — keep KPI definitions in one source of truth.

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
- **[Later]** Full translated UI locales beyond launch set; locale-specific content/formatting; localized onboarding.

### 7.3 Privacy & data handling (acquisition hook)
- **[MVP]** **No training on user chats by default.**
- **[MVP]** **Short, configurable retention** with an **in-product retention-status disclosure**.
- **[MVP]** **One-click export & delete.**
- **[MVP]** **Optional no-telemetry mode** (Mistral-style differentiation).
- **[MVP]** GDPR essentials for EU users: consent, access, deletion, data minimization.
- **[Later]** Contractual no-train guarantees for Team/Enterprise; data residency options; DPA availability.
- *Context:* a 2026 US ruling held AI conversations carry **no legal confidentiality** `[VERIFY]` — strengthens the case for an explicit, user-controlled privacy posture as a differentiator.

### 7.4 Security & trust
- **[MVP]** Encryption in transit and at rest.
- **[MVP]** **BYOK secret handling**: keys encrypted, never logged.
- **[MVP]** **Surface model used + token cost** on every response; **never silently downgrade** the model (Perplexity's mistake) — the trust surface is a product feature, not just a setting.
- **[MVP]** Baseline abuse monitoring + an abuse-reporting path.
- **[Later]** SSO/SAML, audit logs, SOC 2 path, DPA (Team/Enterprise, P2).

### 7.5 Content moderation & EU AI Act compliance
- **[MVP]** **AI-interaction disclosure** — clearly tell users they are interacting with an AI (EU AI Act transparency, **effective ~Aug 2026** `[VERIFY]`). Penalties up to **€35M or 7%** of worldwide turnover. `[VERIFY]`
- **[MVP]** Baseline safety filtering / abuse monitoring (see §7.4).
- **[Later, by ~Dec 2, 2026 `[VERIFY]`]** **Machine-readable marking/labeling of AI-generated content** (deepfakes, public-interest text) — design alongside any image/media generation (P2); content-labeling obligation has a deferral to that date.

---

## 8. Risks & Mitigations (product/business)

| Risk | Likelihood / Impact | Mitigation |
|---|---|---|
| **Commoditization vs incumbents** (we look like "another $20 chat app") | High / High | Don't compete on breadth; lead with the stacked wedge (multi-model + transparency + BYOK/privacy); price at/below the anchor; win on rendering/streaming/a11y/mobile polish. |
| **COGS / margin erosion** ("inference whales", 30–100x token variance) | High / High | Aggressive routing (cheap default), hard free-tier metering, push heavy users to BYOK, per-message cost instrumentation with margin alerts. |
| **Trust/privacy execution failure** (we promise transparency/no-train and slip) | Medium / High | Make transparency a visible product surface; no silent downgrades; encrypted BYOK keys; ship export/delete + retention disclosure in P0; audit before launch. |
| **Smaller power-user TAM** (beachhead too small to grow) | Medium / Medium | Keep a simple default mode for down-market expansion; fast-follow privacy-prosumers; sequence Projects/search/memory to broaden appeal. |
| **Upstream provider dependency** (pricing/terms/SLA changes) | Medium / High | Thin provider abstraction (swap Gateway↔OpenRouter↔LiteLLM); multi-provider by design; BYOK offloads token risk to users; monitor provider price/term changes. |
| **Compliance timeline slip** (EU AI Act Aug/Dec 2026) | Medium / High | AI-interaction disclosure in P0; design content-marking alongside media-gen; track official EC pages `[VERIFY]`; legal review gate before EU launch. |
| **Fast-moving facts** (prices/models/limits churn monthly) | High / Medium | Pull pricing/model lists from live APIs, never hardcode; re-verify §10 list at build time. |

---

## 9. Open Questions (for stakeholders)

1. **Pro price point:** ~$15 vs ~$20? Trade conversion volume against margin and the anchor. `[VERIFY]` market.
2. **BYOK monetization:** small flat platform fee, bundled into Pro, or free as an acquisition lever? Affects billing infra.
3. **Free-tier caps:** exact message/token limits — needs a cost model run against single-digit conversion assumptions. `[VERIFY]`
4. **Usage credits in P1 or pulled forward?** Depends on observed demand from occasional heavy users.
5. **Default model for free tier:** which cheap class (DeepSeek vs Gemini Flash) balances cost, quality, and privacy/geopolitical trust? `[VERIFY]`
6. **EU launch timing vs AI Act dates:** do we gate EU availability on the Aug 2026 transparency obligation, or launch globally with disclosure built in? `[VERIFY]` dates.
7. **Secondary persona timing:** how aggressively to court privacy-prosumers (researchers/journalists/lawyers) in P1 — affects citation/search prioritization.
8. **RAG in scope earlier?** If a target segment needs persistent doc knowledge bases, RAG may pull from P2 toward P1 (per PRD 04 open question).
9. **Native trigger:** which KPI threshold (iOS push re-engagement, app-store discoverability) flips Capacitor from P2 to active?
10. **Ads at scale:** is ad monetization permanently off-strategy (trust-first brand) or a "revisit at scale" option?

---

## 10. References

### 10.1 Research documents
- **`docs/research/05-competitive-monetization.md`** — primary (competitive teardown, pricing, economics, personas, NFR landscape, metrics, positioning).
- `docs/research/01-features-ux.md` §15 — feature MVP-vs-later set.
- `docs/research/02-mobile-responsive.md` §13 — responsive/PWA-first MVP, Capacitor-later.
- `docs/research/03-architecture.md` §13–14 — recommended MVP stack + risks.
- `docs/research/04-ai-capabilities.md` §12 — AI capability MVP-vs-later set.

### 10.2 Key source URLs (re-verify before quoting — see §10.3)
- Pricing: https://chatgpt.com/pricing/ · https://claude.com/pricing · https://gemini.google/subscriptions/ · https://www.finout.io/blog/perplexity-pricing-in-2026 · https://www.eesel.ai/blog/copilot-pricing · https://mistral.ai/pricing · https://api-docs.deepseek.com/quick_start/pricing · https://costbench.com/software/ai-chatbots/poe/
- BYOK: https://openrouter.ai/announcements/bring-your-own-api-keys · https://surfmind.ai/blog/byok-bring-your-own-key-future-of-ai-tools
- Economics/conversion: https://www.trendingtopics.eu/ai-software-margins/ · https://www.investing.com/analysis/the-ai-token-pricing-crisis-behind-openai-and-anthropics-revenue-race-200680777 · https://www.growthunhinged.com/p/free-to-paid-conversion-report · https://firstpagesage.com/seo-blog/saas-freemium-conversion-rates/
- Personas/metrics: https://www.unboxfuture.com/2026/04/ai-trends-2026-great-divide-between.html · https://www.arcade.dev/blog/user-retention-in-ai-platforms-metrics/ · https://mixpanel.com/blog/ai-product-metrics/ · https://mixpanel.com/blog/mau/
- Accessibility: https://www.audioeye.com/post/wcag-22/ · https://www.browserstack.com/guide/wcag-compliance-checklist · https://www.w3.org/TR/WCAG2Mobile-22/
- i18n: https://simplelocalize.io/blog/posts/ui-localization-best-practices/ · https://www.ai-toolbox.co/chatgpt-toolbox-features/chatgpt-rtl-language-support
- Privacy: https://felloai.com/how-to-stop-ai-from-training-on-your-data/ · https://lumichats.com/blog/chatgpt-claude-gemini-training-your-data-2026-privacy-guide
- EU AI Act: https://artificialintelligenceact.eu/article/50/ · https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content

### 10.3 "Needs verification" list (fast-moving — re-confirm at build/PRD-lock)
- All subscription **prices and per-tier limits** (ChatGPT/Claude/Gemini/Perplexity/Copilot/Mistral/Poe) and our own Pro price + free-tier caps.
- **DeepSeek API rates** and promo end dates; which cheap model we default the free tier to.
- **ChatGPT free-tier ads** scope; **Perplexity ad abandonment** (confirm still current).
- **Model names/IDs** (GPT-5.x, Claude Opus/Sonnet/Haiku 4.x, Gemini 3.x) — churn fastest; pull from live model-list APIs.
- **Privacy defaults & retention windows** for incumbents; current ToS.
- **EU AI Act dates** (transparency ~Aug 2026; content-marking deferral ~Dec 2, 2026) and **penalty figures (€35M/7%)** — confirm against official EC pages.
- **Margin (~50–60%), inference share (~23%), conversion (single-digit %), stickiness (~21%), retention (D1/D7/D30)** benchmarks — directional; validate with our own cohorts post-launch.
- **OpenRouter BYOK = 5% of upstream** — `[VERIFIED]` in research; re-confirm at integration.
- **2026 US "no legal confidentiality" ruling** — confirm scope before using in marketing/legal claims.
