# PRD 02 — AI Capabilities & Model Layer

**Product:** A transparent, multi-model, cost-leading AI chat for web and mobile (mobile-web first).
**This PRD owns:** the "intelligence" layer behind the chat — provider abstraction, the model registry, model selection/routing, streaming contract, reasoning display, tool calling, grounded web search, multimodal input, context management, structured outputs, and the AI-layer safety/cost requirements.
**Status:** Draft for build. Incorporates the 2026-05-27 fresh-research + review pass.
**Date:** 2026-05-27.
**Priority tags:** **[P0/MVP]** ship-blocking · **[P1]** fast-follow · **[P2]** later.

---

## 1. Summary & Purpose

This PRD specifies the model-facing capabilities that turn our chat UI into a product. Our positioning wedge is **multi-model + transparency**: users can pick among models from multiple providers, and every answer shows *which* model produced it (and, where available, token/cost). Critically, transparency means the layer records and exposes the **model actually served** — including when it differs from the model/tier requested (Auto downgrade, fallback, deprecation) — so we never silently downgrade (§4.2). We deliver this cheaply via a **provider-abstraction layer** plus a **gateway/aggregator**, so we offer a rich model picker on day one without N bespoke integrations.

The defining engineering constraint is that **models, prices, IDs, and context windows move weekly** — and this is not theoretical: the 2026-05-27 review found multiple illustrative facts that had drifted within 6 weeks (DeepSeek pricing, OpenAI API-ID naming, Anthropic gaining native structured outputs, the Opus 4.7 tokenizer, Gemini tiered pricing). This PRD therefore mandates a **data-driven model registry** (no hardcoded model facts) as a first-class, ship-blocking requirement — not an implementation detail. Everything user-facing about a model is read from configuration that can be hydrated from provider model-list APIs. **Any concrete model ID, price, or context window in this document is illustrative / `[verify-at-build]`, never a normative requirement.**

The MVP target persona is **power users / developers**, with a secondary **privacy-conscious prosumer** segment, and a simple **"Auto" default** so casual users never have to think about models. **No training on user chats by default** is a product principle, but it is a *configurable posture* — surfaced per route via the `data_policy` badge — not a hard gate that excludes the cost-leading default provider. The main default route is **DeepSeek**; privacy-sensitive users can pick a Western route in the picker or use BYOK (§6).

---

## 2. Goals & Non-Goals

### Goals
- Make multi-model selection and **per-turn transparency** (which model answered) a core, visible differentiator.
- Treat models as configuration: a registry that can be updated without a code deploy and ideally hydrated from provider APIs.
- Ship a credible **text-first** capability baseline for the MVP: streaming + stop, reasoning display, multi-model + per-turn transparency, context management, structured outputs, baseline safety. **Vision + PDFs, tool/function calling, and grounded web search are fast-follow ([P1])** per the lean-text-core scope decision — designed-for now, built next.
- Keep cost controllable and visible (routing, caching, usage meter) — reasoning tokens accounted correctly.
- Keep the provider layer thin so we can add/drop providers and swap gateways without touching app code.

### Non-Goals (MVP)
- Heavy **side-by-side parallel comparison** of models (the multi-pane "race" UX) — **[P2]**, the picker + per-turn attribution is the MVP expression of "multi-model."
- **RAG over user documents** (vector DB, chunking, reranking) — **[P2]**; **P1 bridge:** vision/PDF "attach and ask" (§4.8), not P0.
- **Persistent cross-chat memory** — **[P1]**; principle specified here, build later.
- **Image generation, STT/TTS, realtime voice** — **[P2]**.
- **MCP / connectors / third-party plugins** — **[P2]**.
- A trained/learned auto-router — **[P1]**; heuristic routing is enough for MVP.
- Billing/metering implementation and pricing tiers — owned by **PRD 05**; this PRD emits the usage/cost signals it consumes.

---

## 3. Key User Stories

| # | As a… | I want… | So that… | Priority |
|---|---|---|---|---|
| U1 | casual user | to just type and get a good answer without choosing a model | I don't have to understand models | P0 (Auto default) |
| U2 | power user | to pick a specific model per conversation, and switch mid-thread | I can use the right tool for the task | P0 |
| U3 | any user | to see which model produced each answer | I can trust/judge the output (transparency wedge) | P0 |
| U4 | developer | to see token usage and (where available) cost per message | I can manage spend and pick efficient models | P0 |
| U5 | user | to stop a long/wrong response immediately | I'm not stuck waiting or burning budget | P0 |
| U6 | power user | to use sensible reasoning defaults at launch, then toggle reasoning effort once the UI ships | I get deeper answers on hard problems and can inspect the tradeoff | P0 defaults / P1 toggle |
| U7 | user | to attach an image or PDF and ask about it | I can work with documents and screenshots | P1 (vision/PDF) |
| U8 | user | to get answers grounded in live web results with citations | I can trust freshness and verify sources | P1 (web search) |
| U9 | developer | the assistant to call tools (search, code, fetch) in a visible, controllable loop | I can do multi-step work and see what it did | P1 (tools) |
| U10 | privacy-conscious user | assurance my chats aren't used to train models, plus a "temporary chat" | my data stays mine | P0 (default + temporary chat) |
| U11 | user | the conversation to keep working even on very long threads | I don't hit opaque context errors | P0 (summarize-on-threshold) |
| U12 | returning user | the product to remember my preferences (editable, deletable) | it feels personalized without being creepy | P1 (memory) |

---

## 4. Functional Requirements

### 4.1 Provider abstraction & model registry — **[P0/MVP]**
- **FR-1 [P0]** All model usage goes through a single **provider-abstraction interface** (normalized request/response/stream shape). No app/UI code calls a provider SDK directly. Recommended baseline: AI SDK providers + a gateway (see PRD 04 §5). *Acceptance: adding or removing a model is a registry/config change, never an app-code change; swapping the underlying gateway requires touching only the adapter.*
- **FR-2 [P0]** A **data-driven model registry** is the single source of truth for all model metadata (§5). **No model IDs, prices, context windows, or "which is flagship" may be hardcoded in app logic or UI.** *Acceptance: a grep for any concrete model ID or $/token figure outside the registry/config fails review.*
- **FR-2b [P0]** **Registry cost-accounting schema (THIS PRD OWNS IT).** The price representation must be **structured, not a single scalar per direction**, because a flat $/token makes the cost-transparency wedge *itself* wrong on exactly the long-context, high-value turns where it matters most. Long-context pricing has bifurcated into **three incompatible math models that must all be representable** (all illustrative/`[verify-at-build]`, not normative): **(a) whole-session reprice** — crossing a token threshold reprices the *entire request*, with **separate input and output multipliers** (e.g. ×2 input / ×1.5 output — *two factors, never one scalar*) and a `tier_scope` distinguishing a session-wide reprice from a per-band overage; **(b) stepped per-band base rates** — a band above a threshold carries its own resolved `price_in`/`price_out` (and stepped cached rate) from the registry tier table, repricing only the overflow band; **(c) flat / no surcharge** — representable as a first-class *positive* fact (e.g. `flat: true` / an empty tier list) so the picker can surface "no long-context penalty" rather than only the absence of a tier. The schema MUST also express: **cached-input** and **batch** rate multipliers; **promo windows** carrying `effective_until`/date metadata (a discounted rate that reverts on a date, recording whether the promo was date-valid at turn time); and **reasoning-token accounting** (reasoning tokens billed as output and **never cache-eligible**, FR-18/FR-37). The cost computation (FR-36) applies this full model; where tier/promo data is missing, the value is labeled an estimate with a documented error mode rather than silently shown wrong. The canonical per-message `cost_breakdown` fields (`long_context` with `tier_scope`/`applied_tier`/`session_multiplier`/`flat`, `promo.effective_until`, `cost_scope`) and leak rules are in **PRD 07 §4**; this PRD owns how the registry computes them. *Acceptance: the registry can represent (a) a whole-session reprice with separate in/out multipliers, (b) a stepped per-band tier with its own resolved rates, and (c) flat/no-surcharge for one model each; a cached and a batch multiplier; and a dated promo with an expiry; the meter (FR-36) produces a different per-turn cost for an above-threshold vs below-threshold turn, and a different cost for the same promo'd turn before vs after its `effective_until`.*
- **FR-3 [P0]** Registry entries map to **capability tiers** (Fast / Smart / Pro). The UI and router reference tiers; tier→model mapping lives in config. *Acceptance: changing which concrete model backs "Smart" is a config edit with no deploy of app logic.*
- **FR-4 [P1]** Registry can be **hydrated/refreshed from provider model-list APIs** (e.g., available models, context limits) on a schedule, with a hand-maintained overlay for fields providers don't expose (tier, relative cost/speed labels, knowledge cutoff). *Acceptance: a registry refresh job updates available models without a deploy.*
- **FR-5 [P1]** Per-provider **fallback**: on provider error/timeout/rate-limit, retry the same logical model via an alternate provider/route, or downgrade tier per policy; **record the substitution as a served-vs-requested event (FR-11b)** — never substitute silently. (A gateway/OpenRouter provides this natively — prefer it over hand-rolling.) *Acceptance: simulated provider 5xx/timeout results in a successful fallback response or a clear, typed user-facing error, never a silent hang; the served model + reason is recorded.*
- **FR-6 [P0]** **BYOK** (bring-your-own-key): users supply provider keys; keys encrypted at rest (KMS/envelope), never logged, scoped to user. **BYOK ships at launch** — it is the power-user margin de-risk + privacy/cost-control wedge (see PRD 05 §5). Policy (platform-keys vs BYOK default) coordinated with PRD 05. (Key-storage schema lives in PRD 04 `api_key` table, P0.) *Acceptance: anonymous/guest users (`is_anonymous`) cannot store BYOK keys; UI prompts account link before key entry (PRD 04 §5.2/§5.5).*

### 4.2 Model picker, routing & persistence — **[P0/MVP]**
- **FR-7 [P0]** Default mode is **"Auto"** — the user need not choose a model. Auto is a *routing system, not a model*. *Acceptance: a new user can send a message and get a response with zero model selection.*
- **FR-8 [P0]** **Auto-routing (heuristic)**: route to a Fast/cheap model for simple queries and a Smart/Pro/reasoning model for hard ones, using cheap signals (prompt length, code presence, explicit "think hard" intent; **attachment presence is inert until P1 attachments ship**). The routing **decision itself** (not just the resulting model) is a first-class, visible, **overridable** surface — especially when Auto routes *down* to a cheaper model — and is recorded per turn via FR-11b. Auto never selects models with `default_route_eligible = false` (e.g., Grok before data-policy review). **DeepSeek is `default_route_eligible: true` and is the cost-leading Auto default**; its data-residency posture is surfaced via the `data_policy` badge, not gated out. *Acceptance: short trivia routes Fast; a long code-debugging prompt routes Smart/Pro; the routing decision is recorded and surfaced per turn and the user can override it.*
- **FR-9 [P0]** **Explicit model picker** presents **capability tiers** with optional drill-down to concrete models. The picker is driven by the registry and surfaces per-model metadata (context window, modalities, relative cost/speed, knowledge cutoff). *Acceptance: picker contents change when the registry changes, with no code edit.*
- **FR-10 [P0]** **Per-conversation model selection** persists; **per-message switching** is allowed mid-thread. *Acceptance: switching model mid-thread applies to subsequent turns and is persisted.*
- **FR-11 [P0]** **Per-turn model attribution is persisted and displayed**: every assistant message stores which model/provider produced it (and routing decision if Auto). This is the transparency wedge. *Acceptance: each assistant turn shows a model badge; reloading the thread preserves correct per-turn attribution even across mid-thread switches.* (Stored in the `Message.parts`/metadata per PRD 04 data model.)
- **FR-11b [P0]** **Served-vs-requested model + reason (silent-downgrade prevention).** The model layer records both the **requested** model/tier and the **served** model/provider, and — whenever they differ — a machine-readable **reason** for the substitution, drawn from the PRD 07 §5 reason-code enum to which these triggers map 1:1: Auto downgrade (`auto_downgrade`), FR-5 fallback (`provider_fallback`), deprecation/migration per `status`/`fallback_to` in §5.2 (`deprecated_model`), and capacity reroute (`capacity_reroute`, optionally `gateway_route` for gateway-level reroutes). This is the core transparency promise: **never silently downgrade.** *Acceptance: a turn where the served model ≠ requested model persists both plus a reason code; a turn served exactly as requested records no substitution.* (This PRD owns the model-layer logic and the served/reason fields; **PRD 01 renders** the "served X instead of Y because Z" surface; persisted on `Message` metadata per PRD 04.)
- **FR-12 [P2]** Side-by-side multi-model comparison (parallel responses). Out of MVP scope.

### 4.3 Streaming & Stop/Abort — **[P0/MVP]**
- **FR-13 [P0]** All responses **stream tokens** (SSE). *Acceptance: first tokens render progressively, not as one blob.*
- **FR-14 [P0]** **Stop/Abort contract**: the client can cancel an in-flight generation; cancellation propagates to the provider request (abort fetch / close stream) so we stop billing. The partial response is preserved. *Acceptance: pressing Stop halts output within ~1s, the upstream request is aborted, and the partial turn is saved.*
- **FR-15 [P0]** **Stream row + orphan reconciliation:** persist `Stream` rows and reconcile `active` → `aborted` on Stop, timeout, and reaper job so no run stays orphaned past max duration. This supports P0 partial persistence and does **not** require P1 resumable replay.
- **FR-15b [P1]** When resumable-stream replay ships, Stop from a resumed connection uses the **dedicated server-side stop endpoint** (PRD 04 §5.1), not client `AbortSignal` alone.
- *Note: the Stop button and streaming UI live in **PRD 01 (chat UI)**; this PRD owns the functional/abort contract behind it.*

### 4.4 Reasoning / "thinking" — **[P0/MVP]**
- **FR-16 [P0/P1]** **Reasoning-effort mapping:** **P0** defines provider-specific defaults and registry mappings for reasoning knobs (Anthropic adaptive / extended-thinking, OpenAI `reasoning.effort`, Gemini `thinking_level`) so cost accounting is correct even without a user-facing control. **P1** exposes a normalized UI toggle (owned by PRD 01 §4.2/§4.3). The set of valid effort levels per provider is registry seed data verified against the live API at build, not hardcoded. *Acceptance (P0): adapter applies valid default effort per model and records reasoning-token cost. Acceptance (P1): UI hides the toggle for unsupported models and shows cost/latency hints.*
- **FR-17 [P0]** **Show only what the provider exposes.** Some providers return only a *condensed summary* of reasoning (Anthropic adaptive thinking) or omit it by default (Opus 4.7 opt-in). Never fabricate, store, or display reasoning content the provider hides. Additionally, **"the model reasoned but returned no visible summary" is a distinct, expected state** (e.g., brief reasoning) and must be handled as such — not an empty/broken panel, and not implying the model didn't think. Note: reasoning is **still billed even when no summary is returned** (FR-18). *Acceptance: for a provider that returns no reasoning text, the UI shows no reasoning panel (or an empty-by-design state), not a hallucinated one; a reasoned-but-no-summary turn is visually distinct from a non-reasoning turn.*
- **FR-18 [P0]** **Reasoning tokens are billed as output tokens and are NOT cache-eligible** — they are per-request and full-price every turn, so the cost computation MUST exclude `reasoning_tokens` from the `cached_input` (and any stepped `applied_tier` cached) discount and bill them at the output rate. They must be included in token/cost accounting and the usage meter. *Acceptance: a high-effort reasoning turn shows materially higher output-token/cost counts that include reasoning tokens; a golden test asserts the cache discount is applied to non-reasoning input/output only and never to reasoning tokens (mirrors PRD 07 §7 rule 7 / §8 AC#3).*
- *Note: the collapsible "Thinking…" panel UI lives in **PRD 01**; this PRD owns the toggle mapping, accounting, and "only show what's exposed" rule.*

### 4.5 System prompt & custom instructions — **[P0/MVP]**
- **FR-19 [P0]** **App-level system prompt** (product persona, formatting, safety rules) is held server-side and is never overridable by user content (delimiter discipline, §6).
- **FR-20 [P0]** **User custom instructions** (name, tone, expertise level) are injected into every chat as clearly-delimited user-level preferences. *Acceptance: custom instructions affect responses and are editable/removable by the user.*
- **FR-21 [P2]** **Personas / Projects** (scoped system prompt + tools + knowledge files; persistent workspaces). Later.

### 4.6 Tool / function calling & agentic loop — **[P1]** (deferred from MVP per the lean-text-core scope decision)
- **FR-22 [P1]** Support **tool/function calling** with JSON-schema tool definitions, normalized across providers via the abstraction layer. **MCP (Model Context Protocol) is the tool/connector interop standard** the layer targets so we add tools/connectors without bespoke per-tool integrations (the MCP 2026 spec moved to a stateless HTTP core, formalized servers as OAuth Resource Servers, and added server-side agent loops + parallel tool calls; release candidate locked 2026-05-21, final spec slated 2026-07-28). *Implementation note:* AI SDK v6's `Agent` primitive and `needsApproval` (HITL gate) are the recommended implementation and are **owned by PRD 04**; full MCP **client/host** is FR-42 (P2). This FR defines the capability framing and normalization, not the connector ecosystem.
- **FR-23 [P1]** An **agentic loop runtime** (ReAct: model emits tool call → app executes → result fed back → repeat) with mandatory guardrails:
  - **max-iteration cap** (hard limit; loop terminates with a clear message),
  - **per-tool timeout**,
  - **concurrency control** for parallel tool calls (model may emit multiple independent calls executed concurrently),
  - **tool-error handling** that re-prompts the model with a scoped error (error stays attributed to the tool, not the whole turn).
  - *Acceptance: a loop that would exceed the cap terminates gracefully; a slow tool times out without hanging the turn; a tool error is surfaced to the model and recovered from or reported.*
- **FR-24 [P1]** **Streamed steps**: tool name, args, and results stream to the UI for transparency ("Searching the web…", "Running code…"). *Acceptance: intermediate steps render live, not just the final answer.*
- **FR-25 [P1]** **Permission-gating**: tools with side effects require user consent; **human confirmation is required for high-impact actions** (§6). *Acceptance: a side-effecting tool cannot execute without an explicit confirm path.*
- **FR-26 [P1]** **Least-privilege tools**; tool inputs/outputs treated as untrusted (§6).

### 4.7 Web search / grounding & citations — **[P1]** (deferred from MVP per the lean-text-core scope decision)
- **FR-27 [P1]** **Live web search/grounding** with **inline citations** (clickable sources). Three implementation patterns:
  - **(A) Provider built-in search** (OpenAI web-search tool, Gemini "Grounding with Google Search", Anthropic web search) — lowest per-provider integration cost, keeps the user's chosen chat model, per-call fees.
  - **(B) Dedicated search-grounded API (Perplexity Sonar)** — best-in-class cited freshness, citations as free metadata, but locks the search experience to one provider/model.
  - **(C) Gateway-native web search (default):** Vercel AI Gateway (the PRD 04 MVP-default gateway) exposes web search as a **tool that works with *any* model** via `gateway.tools.perplexitySearch()` / `gateway.tools.parallelSearch()` (Perplexity / Parallel.ai backends, ~$5 per 1,000 requests), plus passthrough to provider-native tools. Results return as tool results rendered with citations. This delivers Perplexity-quality grounding **with the user's chosen chat model** — collapsing the old A-vs-B tradeoff and removing the lock-in objection to Sonar.
  - **Recommendation (default):** ship **pattern (C) gateway-native web search** so grounding works with whatever chat model the user selected (the multi-model wedge), falling back to (A) where the gateway lacks coverage; keep (B) Sonar only as an optional "research" mode if a distinct UX warrants it. Prefer **Google's zero-data-retention "Enterprise Web Grounding"** variant where the privacy-first default route requires it (PR-1). *Acceptance: a "what happened this week" query returns an answer with at least one working, clickable citation, using the user's selected model.*
  - *Deferral rationale (updated):* web search stays **[P1]** for **scope discipline + citation-UX polish**, **not** integration cost — gateway-native search is near-zero to wire. A minimal grounded mode may be pulled to **early P1 / MVP-lite**; flag for the PRD 05 roadmap worker.
- **FR-28 [P1]** Retrieved web content is **untrusted** (indirect prompt injection) — see §6.
- **FR-29 [P2]** **RAG over user documents** (ingest → chunk → embed → hybrid retrieve → rerank → cite). Out of MVP. **Bridge:** use large-context "attach a document and ask" for small corpora in MVP (§4.9). Build full RAG when users need persistent knowledge bases / large corpora / freshness / auditability. (pgvector in the same Postgres per PRD 04.)

### 4.8 Multimodal — vision + documents **[P1]**; rest **[P2]** (vision/PDF deferred from MVP per the lean-text-core scope decision)
- **FR-30 [P1]** **Vision (image input)**: users attach images; vision-capable models answer about them. Registry marks which models support image input; non-vision models reject/hide attachments. *Acceptance: attaching a screenshot to a vision model yields a relevant answer; attaching to a non-vision model is blocked with a clear message.*
- **FR-31 [P1]** **PDF / document understanding** (native multimodal, no separate OCR pipeline for supported models). *Acceptance: a user can attach a PDF and ask questions about its content.*
- **FR-32 [P1]** **Cost gating for multimodal**: vision/document input can raise cost 5–10×; image/document tokens count toward the usage meter, and multimodal use may be gated by tier/limits (coordinate with PRD 05). Image/PDF token math is **provider-specific** (e.g., Claude ~1,334 tok/1000×1000px; Gemini ~258 tok/page; OpenAI charges vision at ~4–8× text rate, [verify-at-build]), so the registry/meter needs **per-provider image-token formulas**, not a flat assumption. *Acceptance: an image-bearing turn reflects added token cost in the meter using the selected provider's image-token formula.*
- **FR-33 [P2]** Image generation, STT, TTS, realtime/live voice. Later (separate models/endpoints/pricing; voice pulls WebSockets/realtime infra forward — see PRD 04 §4/§11).

### 4.9 Context management — **[P0/MVP]**
- **FR-34 [P0]** **Per-model token counting**: token counts/limits (`context_window` and `max_output_tokens` per the §5.2 registry schema) come from the registry per model; **do not assume a shared tokenizer** — counts vary **materially (>30% in some cases)** across providers, e.g., Claude Opus 4.7's new tokenizer uses **≈ +12–35% tokens for the same text** vs prior Claude models ([verify-at-build]). Because several providers expose no synchronous client-side tokenizer, the layer must specify a **fallback**: provider `count-tokens` endpoint where available, else a per-model heuristic estimate, and must treat pre-send counts as **estimates, reconciled to exact from response usage metadata**. *Acceptance: the context/usage display uses the selected model's own limits and tokenizer; pre-send estimate is reconciled to the provider's reported usage post-response.*
- **FR-35 [P0]** **Summarize/compact context.** When context use crosses ~70–80% of the model's window, LLM-summarize older turns while keeping recent turns full-fidelity + the summary. **Prefer compacting at natural task/turn boundaries** (after a completed sub-task / before a topic shift) and treat the ~70–80% threshold as a **safety net** — threshold-only compaction can fire mid-task and drop context the next turn needs. Sliding-window fallback acceptable as a simpler first cut, but boundary-aware summarization is the target. *Note:* sequence compaction so it does **not** mutate the cache-stable prefix and invalidate prompt caching (FR-37, §4.9 ordering rule). *Acceptance: a thread long enough to approach the window keeps responding correctly instead of erroring; summarization is visible/logged and prefers boundaries over the raw threshold.*
- **FR-36 [P0]** **Visible cost/usage meter**: surface tokens used (input/output, including reasoning) and, where the provider/registry gives price, an estimated cost per message and per conversation. The cost computation **must apply the full price model** (tiered/threshold pricing, cached-input and batch multipliers, active promos — per the §5.2 schema, FR-2b), because a scalar price makes the wedge wrong on exactly the long-context, high-value turns where transparency matters most (review G1). Where the layer cannot compute an exact cost (e.g., missing tier data), it labels the value an **estimate** with a documented error mode rather than silently showing a wrong number. *Acceptance: a >272K-token GPT-5.5 turn or a >200K Gemini turn reflects the surcharge tier; a cached/batch turn reflects the multiplier; the meter updates per turn and includes reasoning tokens.* (Per-message **persisted** cost is owned by PRD 04's data model; the **chat-surface display** is owned by PRD 01 — this PRD owns the computation/schema.)
- **FR-37 [P1]** Cost levers: **prompt caching** (where supported), **batch APIs** for async work, capping max output + reasoning effort, summarizing instead of resending full history. **Cache-friendly prompt assembly is part of the contract:** order the assembled prompt **stable-content-first, variable-content-last** (system prompt → tool defs → static context → older history → current user message) to maximize cache hit rate (cuts input-token cost ~30–50% on long threads/agent loops at no quality cost). Injected custom-instructions/memory and summarization (FR-35) must be sequenced so they do **not** reorder or mutate the cache-stable prefix. **Reasoning-token carve-out:** reasoning/thinking tokens are never cache-eligible (FR-18) — the cache discount applies only to the cache-stable prefix's non-reasoning input/output, never to reasoning tokens.

### 4.10 Structured outputs / JSON mode — **[P0/MVP] where used**
- **FR-38 [P0]** Support **JSON mode / schema-constrained structured outputs** for tool arguments and any machine-readable feature.
- **FR-39 [P0]** **Strict output-schema validation**: all structured model output is validated against a strict schema and **treated as untrusted** before use. Reasoning: **Constrained Decoding Attacks (CDA)** can smuggle malicious intent through schema-level grammar even when the surface prompt looks benign. *Acceptance: malformed or schema-violating output is rejected/re-prompted, never passed downstream unchecked.*

### 4.11 Memory / personalization — **[P1]** (principle now, build later)
- **FR-40 [P1]** Persistent memory is **deferred** but high-retention; when built it MUST be: **editable** (user sees and edits stored facts), **consented** (opt-in, transparent about what's stored), **deletable** (one-click clear), with explicit **"temporary chat"** that stores nothing and is excluded from memory/training. *Acceptance (when built): the assistant cites when it uses a memory, and a temporary chat leaves no persisted memory.*
- **FR-41 [P0]** **"Temporary chat" / incognito mode** is in MVP at the privacy level even before memory ships: a temporary chat is excluded from any future memory and from training (consistent with §6). *Acceptance: starting a temporary chat is possible at MVP and its contents are flagged non-persistent for personalization.*

### 4.12 MCP / connectors / plugins — **[P2]**
- **FR-42 [P2]** Act as an **MCP client/host** to offer connectors/plugins without bespoke integrations. Deferred: powerful differentiator but large security surface (untrusted servers/tools → injection). Build when extensibility/enterprise connectors are prioritized.

---

## 5. Model Registry & Provider-Abstraction Requirement (the no-hardcoding rule)

> **This is a ship-blocking architectural requirement, not a nice-to-have.** Models, prices, IDs, context windows, "which is flagship," reasoning-API shape, and free-tier rules are **FAST-MOVING** and drift within weeks. Hardcoding them creates silent staleness and incorrect cost/UX. **Evidence this is real, not theoretical:** the 2026-05-27 review re-verified a full current snapshot and found multiple illustrative facts had drifted within ~6 weeks — DeepSeek repricing (and a promo reverting on a fixed date), OpenAI API-ID naming (API IDs ≠ ChatGPT product names — see §5.3 note), Anthropic gaining native structured outputs, Opus 4.7's higher-token tokenizer, and Gemini tiered pricing. **Cite that snapshot as the source-of-truth-at-a-point-in-time; do not bake its volatile numbers into normative requirements here.**

### 5.1 Rules
1. **Models are configuration, not constants.** All model facts live in a registry, editable without an app-logic deploy.
2. **No hardcoded model IDs, prices, or context windows** anywhere in app/UI logic. App code references **capability tiers** and **registry fields**. **Use provider API model IDs, never product/marketing names** — e.g., OpenAI API IDs are of the form `gpt-5.5` / `gpt-5.5-pro` / `gpt-5.4` / `gpt-5.4-mini` / `gpt-5.4-nano` / `gpt-5.4-pro`, **not** ChatGPT product names like "Instant"/"Thinking" (illustrative/`[verify-at-build]`; mixing the two is a registry-population bug).
3. **Hydrate from provider model-list APIs where possible** ([P1]); hand-maintain only the fields providers don't expose.
4. **Surface metadata from the registry** into the picker, router, token counter, and cost meter — one source of truth.
5. **Per-provider parameter mapping** (reasoning effort, modalities, max output) lives in the registry/adapter, not scattered in feature code.

### 5.2 Required metadata per model entry

| Field | Purpose |
|---|---|
| `provider` + `model_id` | Routing identity (id is config, never hardcoded in logic) |
| `display_name` | What the user sees in the picker |
| `tier` (Fast / Smart / Pro) | Tier mapping the UI & router reference |
| `context_window` (max input tokens) | Token budgeting / summarize-on-threshold |
| `max_output_tokens` | Output capping / cost |
| `modalities_in` (text, image, pdf/doc, audio, video) | Picker capability + attachment gating |
| `modalities_out` (text, image, audio) | Feature gating |
| `supports_reasoning` + reasoning param mapping | Reasoning toggle mapping; whether to show panel |
| `reasoning_visibility` (none / summary / full) | "Show only what's exposed" rule |
| `supports_tools`, `supports_structured_output` (native-strict vs json-mode), `supports_web_search` | Feature gating per model (Anthropic, OpenAI, and Gemini now all offer *native-strict* structured outputs — distinguish from best-effort json-mode) |
| `pricing` (structured per FR-2b: base `price_in`/`price_out` per-M tokens **+ long-context model {whole-session reprice with separate in/out multipliers + `tier_scope`, OR stepped per-band tiers each carrying their own resolved `price_in`/`price_out`/cached rate, OR `flat: true` as a positive "no surcharge" fact} + cached/batch multipliers + dated promos with `effective_until`**) | Cost meter — **not a single scalar** (nullable; from live source where possible). A scalar makes the wedge wrong on long-context turns; `flat: true` lets the picker surface "no long-context penalty" |
| `image_token_formula` (per-provider) | Multimodal cost accounting — image/PDF token math is provider-specific (FR-32), not a flat assumption |
| `data_policy` (`{trains_on_data, train_default: opt_in\|opt_out\|never, data_residency, zdr_available, retention_days}`) | Per-**route** data handling so the router can *enforce* "no-train routes only" defaults (PR-1) and the picker can surface an accurate data-handling badge. `train_default` captures the consumer-vs-API nuance (a provider may train on its consumer surface while the API route does `never`, or be `opt_out` requiring an explicit setting); `retention_days` and `data_residency` make the badge precise (e.g. Anthropic `retention_days: 7`, OpenAI `~30`, DeepSeek `data_residency: CN`) |
| `relative_cost` / `relative_speed` labels | Picker hints without committing to exact numbers |
| `knowledge_cutoff` | Picker transparency |
| `status` (available / preview / deprecated), `fallback_to` | Routing & graceful degradation |
| `default_route_eligible` | Whether Auto/free-tier/default routing may select this model |
| `data_policy_review_status` | `pending` \| `approved` \| `blocked`; a route with unverified data-handling (e.g., Grok) stays `pending` and is barred from Auto/default until reviewed. The cost-leading default (DeepSeek) is `approved` with its data-residency posture badged (D11) |

### 5.3 Provider recommendation (a recommendation, not a hardcoded list)

- **Main provider (default route, all tiers): DeepSeek** via the OpenAI-compatible binding. Rationale: it is the cost leader (token prices 30–100× below frontier), exposes raw thinking tokens on `deepseek-reasoner`, and carries the metered free tier and the Auto default at a margin no Western frontier route can match.
- **Alternate / picker routes:** **Anthropic + OpenAI + Google Gemini** as selectable picker routes and alternate backends (clean APIs, first-party reasoning/tools/structured-outputs, Gemini's native multimodal + very large context). Anthropic is wired as a drop-in alternate `PROVIDER_BACKEND`.
- **Breadth + fallback layer:** **OpenRouter** (and/or the chosen gateway) to instantly add **xAI/Grok**, Mistral, Llama, etc. behind one integration, with automatic provider fallback — a rich picker on day one without N integrations. (OpenRouter now offers ~1M free BYOK requests/month then a ~5% fee — [verify-at-build]; relevant to BYOK-at-launch economics, FR-6 / PRD 05.)
- **FR-2c [P0] Include xAI/Grok in the lineup at MVP (registry entry, via the breadth/gateway layer):** "every major model in one place" (PRD 00 §1) cannot credibly omit a major provider. Grok is a cheap-frontier option (illustrative/`[verify-at-build]`). Direct integration is a P1 reassessment; **ship Grok with `default_route_eligible: false` and `data_policy_review_status: pending` until its data-handling posture is reviewed** against PR-1. Explicit picker selection can be allowed for signed-in users who opt in; Auto-routing and free-tier defaults MUST exclude Grok until approved. (DeepSeek, by contrast, is `default_route_eligible: true` — the cost-leading default, with its data-residency posture surfaced as an accepted, badged tradeoff per D11.)
- **Direct-vs-aggregator tradeoff:** direct = best features/latency/SLA/data-control; aggregator = breadth + fallback fast, thin fee, less control. **Recommended: both** (DeepSeek direct as the cost-leading default, other primaries direct in the picker, aggregator for breadth/fallback). Final gateway choice coordinated with **PRD 04 §5** (Vercel AI Gateway vs OpenRouter vs LiteLLM). **Gateway-native guardrails (PII redaction, jailbreak detection, moderation hooks) are an explicit selection criterion** — see §6.1 SR-4.
- **Data-handling note on provider choice:** the picker surfaces each route's data posture via the registry `data_policy` field (§5.2 / PR-1) so users can choose. DeepSeek's data-residency/governance posture (data processed in mainland China; jurisdictional bans) is shown via the badge and is an **accepted tradeoff for the default**, not a disqualifier; Western no-train routes are one click away for users who need them. (Grok's posture still gates it from Auto, see FR-2c.)
- **Free-tier default model (THIS PRD OWNS the selection):** the always-available default for free/guest users is **DeepSeek** (`deepseek-chat` for fast/smart/auto, `deepseek-reasoner` for pro) — the cost leader that lets the metered free tier exist at all. Western no-train routes (Gemini Flash / an OpenAI mini / Claude Haiku / a Mistral-EU model; all illustrative/`[verify-at-build]`) remain **selectable picker alternatives** for privacy-sensitive users, and Western-hosted DeepSeek **open weights** remain a separate **[P2+]** self-hosting line. *(PRD 05 references this for its tier/cost gating.)*

> **Current implementation (MVP deploy):** the deployed BE binds the OpenAI-compatible adapter to the DeepSeek-hosted API as the main provider — `PROVIDER_BACKEND=openai` with `OPENAI_BASE_URL=https://api.deepseek.com` and per-tier overrides `OPENAI_MODEL_FAST` / `OPENAI_MODEL_SMART` / `OPENAI_MODEL_AUTO` = `deepseek-chat` and `OPENAI_MODEL_PRO=deepseek-reasoner` (env-var names match `api/app/config.py` and `api/.env.example`). This matches the free-tier default decided above and PRD 00 §11 D11.

---

## 6. Safety, Privacy & Cost-Control Requirements

### 6.1 Safety & moderation — **[P0]**
- **SR-1 [P0]** Moderate **both input and output** (provider safety filters / a moderation endpoint / open classifier). Block or flag per policy. *Note:* single-shot input/output moderation is weaker against **multi-turn jailbreaks** (now the dominant attack on frontier models); treat conversation-level moderation as a consideration as the product matures.
- **SR-2 [P0]** **Prompt-injection-aware architecture** (mitigation is architectural, not format choice):
  - Separate system instructions from user/untrusted data with **clear delimiters**; user content can never override safety sections.
  - **Treat tool results, web/search content, and (future) RAG documents as untrusted** — indirect prompt injection via retrieved content is a top risk.
  - **Treat uploaded images and PDFs as untrusted, injection-capable input [P1, with vision/PDF].** Multimodal injection (instructions hidden in images, QR codes, steganographic payloads, hidden PDF text) is a maturing 2026 vector; when the P1 vision/PDF feature (FR-30/FR-31) ships, image/document content must be handled with the same untrusted-input discipline as retrieved web/tool content, not treated as inert media.
  - **Least-privilege tools**; **human confirmation for high-impact actions** (FR-25).
  - **Validate all structured output against strict schemas** (FR-39); treat model output as untrusted.
- **SR-3 [P0]** Run prompt-injection / system-prompt-leakage checks in CI, alongside the **FR-2 no-hardcoded-model-facts gate** (a grep for any concrete model ID or `$`/token figure outside the registry/config fails the build). (Coordinate with PRD 04 §9.)
- **SR-4 [P0]** **Prefer gateway-native guardrails to satisfy SR-1/SR-2 with less custom code.** Modern LLM gateways ship **PII redaction, jailbreak detection, guardrails, and audit trails at the gateway layer**. Choosing a gateway with these features directly de-risks the P0 safety requirements; **gateway-native guardrails are therefore an explicit gateway-selection criterion** (§5.3, PRD 04 §5). If the chosen gateway lacks them, the app-layer moderation work for SR-1/SR-2 must be budgeted explicitly. *Acceptance: the gateway-selection decision (PRD 04 §5) records whether guardrails are gateway-native or app-layer, and SR-1/SR-2 coverage is accounted for either way.*

### 6.2 Privacy — **[P0]**
- **PR-1 [P0]** **No training on user chats by default**, configured per route. Document per-provider data handling in the registry/config **via the `data_policy` field (§5.2)** so the picker can surface an accurate data-handling badge and users can choose a route that matches their needs. The badge — not a hard gate — is the primary control: the cost-leading default (DeepSeek) ships with its data-residency posture badged and accepted (§5.3 / D11), while genuinely unverified routes (e.g., Grok) stay gated from Auto until reviewed. Note that some providers' **free tiers may use content to improve products while the paid tier does not** — exactly the per-route distinction `data_policy` must capture ([verify-at-build]). For the DeepSeek default, prefer the API route's no-train/opt-out settings where available, and offer BYOK for users who want full control.
- **PR-2 [P0]** **Temporary chat** stores nothing for personalization/memory and is excluded from any training (FR-41).
- **PR-3 [P0]** **Minimize data sent to models**; never put secrets/keys in system prompts (leakage risk). BYOK keys encrypted at rest, never logged (FR-6, PRD 04 §5).
- **PR-4 [P1]** Memory is opt-in, editable, deletable, transparent about recall (FR-40).

### 6.3 Cost control — **[P0]**
- **CC-1 [P0]** **Reasoning tokens count as output** in all accounting (FR-18).
- **CC-2 [P0]** **Visible usage/cost meter** (FR-36).
- **CC-3 [P0]** **Auto-routing** to cheap models for simple queries (FR-8). **[P1] multimodal gating** for the 5–10× cost impact (FR-32) lands with vision/PDF.
- **CC-4 [P1]** Prompt caching, batch APIs, output/effort caps, summarize-don't-resend (FR-37).
- **CC-5 [P0]** Rate-limit by user and IP (esp. guest traffic) to control spend — implemented per PRD 04 §9; this PRD requires the model layer to respect those limits.

---

## 7. Dependencies & Cross-References

| Doc | Relationship |
|---|---|
| **PRD 01 — Chat UI / Features-UX** | Owns the visible **Stop button**, streaming render, collapsible reasoning panel, model-badge display, citation chips, usage-meter UI, attachment UI. This PRD provides the functional contracts behind them (FR-13–18, FR-24, FR-27, FR-36). |
| **PRD 03 — Mobile / Responsive** | Mobile-web-first picker & attachment UX, reasoning-panel collapse on small screens; multimodal capture (camera) consumes §4.8. |
| **PRD 04 — Architecture / Provider layer** | Implements the provider abstraction + gateway (§5 here ↔ §5 there: AI SDK providers + AI Gateway vs OpenRouter vs LiteLLM), **with gateway-native guardrails (PII redaction / jailbreak detection) as an explicit selection criterion (SR-4)**; SSE + resumable streams + Stop reconciliation; data model (`Message.parts` attribution **incl. served-vs-requested model + reason (FR-11b)** and **per-message persisted cost (FR-2b/FR-36)**, `Stream`, `ApiKey`, future `Embedding`); the **AI SDK v6 `Agent`/`needsApproval` tool-loop implementation (FR-22/FR-23)**; moderation/PII in CI; rate limiting. |
| **PRD 05 — Monetization / Cost** | Consumes the usage/cost signals emitted here (tokens incl. reasoning, per-turn cost, routing mix); owns tiers/limits, BYOK-vs-platform-keys policy, and multimodal/reasoning gating thresholds. |

---

## 8. Success Metrics

| Metric | Definition | Target (initial) |
|---|---|---|
| **TTFT** (time-to-first-token) | Stream start latency, p50/p95, per tier | Fast tier p50 < 1s; Smart p50 < 3s |
| **Routing mix** | % of turns routed Fast vs Smart vs Pro under Auto | Majority Fast (cost efficiency) without quality complaints |
| **Cost per message** | Avg blended $/message incl. reasoning tokens | Tracked; trend down via routing/caching |
| **Tool-success rate** *(P1)* | % agentic loops that complete without hitting the iteration cap or erroring out | > 90% on supported tasks |
| **Grounded-answer citation rate** *(P1)* | % of web-grounded answers with ≥1 valid clickable citation | > 95% |
| **Stop latency** | Time from Stop press to upstream abort | < 1s; upstream request confirmed aborted |
| **Attribution correctness** | % of reloaded threads with correct per-turn model badges | 100% |
| **Fallback success** | % of provider failures recovered via fallback without user-visible hang | > 95% |

---

## 9. Open Questions / Risks

1. **Direct-vs-aggregator balance.** How many primaries do we integrate directly vs lean on the gateway/OpenRouter? Affects features/latency/data-control vs speed. (See §5.3; coordinate PRD 04 §5.)
2. **Auto-routing depth.** Heuristic router for MVP — when do we invest in a trained/classifier router? Trigger = scale/cost pressure. ([P1])
3. **Big-context vs RAG.** Where is the line between "attach a doc into large context" and building real RAG? Large context costs more per call and lacks freshness/auditability. ([P2] RAG trigger.)
4. **Search "research mode" only.** *Resolved for the default:* FR-27 commits to **gateway-native web search** (works with the user's chosen model), collapsing the old built-in-vs-Sonar tradeoff. Remaining question: is Perplexity Sonar worth a separate optional **"research mode"** if a distinct UX warrants it? Re-evaluate after MVP. (§4.7)
5. **Multimodal cost gating.** 5–10× cost — what tier/limit gating? Owned with PRD 05. (FR-32)
6. **Memory transparency & privacy.** When we add memory: consent model, editability UX, "cite when used," temporary-chat guarantees. (FR-40)
7. **BYOK monetization.** BYOK at launch is resolved (FR-6; PRD 04 §5; PRD 05 §5). Remaining question: whether BYOK remains free as an acquisition lever, requires a small platform fee, or is bundled into Pro.
8. **Reasoning-API drift.** Defaults change (e.g., flagship models omitting thinking text by default); the toggle mapping must absorb this via the registry, not code. (FR-16)
9. **Free-tier default model — RESOLVED to DeepSeek.** The main provider and free-tier/Auto default is the **DeepSeek-hosted API** (`deepseek-chat` / `deepseek-reasoner`), chosen as the cost leader; its data-residency posture is an accepted, badged tradeoff (§5.3 / D11). **Western no-train routes** (Gemini Flash / an OpenAI mini / Claude Haiku / a Mistral-EU model) remain selectable picker alternatives, and Western-hosted DeepSeek **open weights** stay a separate **[P2+]** self-hosting line. Open sub-question: which DeepSeek API route/settings (and which Western alternatives) give the strongest no-train guarantee to expose in the badge? (PR-1, §5.3)

---

## 10. References

Key source URLs (re-verify at build — all model facts are fast-moving):
- Anthropic models / pricing / extended thinking / streaming — https://platform.claude.com/docs/en/about-claude/models/overview , .../pricing , .../build-with-claude/extended-thinking , .../build-with-claude/streaming
- OpenAI models / pricing / ChatGPT routing — https://developers.openai.com/api/docs/models , .../pricing , https://help.openai.com/en/articles/11909943-gpt-5-in-chatgpt
- Google Gemini models / pricing — https://ai.google.dev/gemini-api/docs/models , .../pricing
- OpenRouter pricing / inference providers compared — https://openrouter.ai/pricing , https://infrabase.ai/blog/ai-inference-api-providers-compared
- Perplexity Sonar — https://docs.perplexity.ai/docs/sonar/quickstart , https://www.perplexity.ai/hub/blog/introducing-the-sonar-pro-api
- Reasoning-token billing trap — https://tokenmix.ai/blog/thinking-tokens-billing-trap-2026
- Structured-output / Constrained Decoding Attack — https://arxiv.org/pdf/2503.24191
- MCP (2026) — https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026

---

> ### ⚠️ FAST-MOVING facts — DO NOT HARDCODE
> Pull these from provider model-list APIs / live pricing at build & runtime; keep them in the **model registry (§5)**, never in app/UI logic. Treat any verified snapshot as a point-in-time reference, not a normative table:
> - **All pricing** ($/M tokens) — re-priced and promo'd frequently; **structured per FR-2b** (long-context model: whole-session reprice with separate in/out multipliers + `tier_scope`, OR stepped per-band tiers, OR `flat: true`; cached/batch multipliers; dated promos with `effective_until`), not a scalar.
> - **Exact model names/IDs and "which is flagship"** — superseded within weeks; **use API IDs, not product/marketing names** (§5.1).
> - **Context windows & max output** — change per model revision.
> - **Tokenizer behavior** — diverges materially across providers (>30% in cases, e.g., Opus 4.7) — affects token counting/budgeting/cost (FR-34).
> - **Reasoning/"thinking" API shape & defaults** — provider-specific and drifting (some flagships now omit thinking text by default; valid effort levels are live-API-verified seed data, FR-16).
> - **Free-tier / rate-limit rules** — change per provider policy.
> - **Per-route data handling** (`data_policy`: `trains_on_data` / `train_default` opt_in\|opt_out\|never / `data_residency` / `zdr_available` / `retention_days`) — varies by route and tier; consumer-vs-API train defaults differ (PR-1, §5.2 / G7).
> - **Modality support + per-provider image/PDF token formulas** — vision/doc/audio/video/image-gen vary and evolve (FR-32).
> - **MCP spec/version & server ecosystem** — actively evolving.
>
> If a number or ID appears in code or UI strings instead of the registry, it is a bug.
