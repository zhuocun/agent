# PRD 02 — AI Capabilities & Model Layer

**Product:** A transparent, multi-model, privacy-first AI chat for web and mobile (mobile-web first).
**This PRD owns:** the "intelligence" layer behind the chat — provider abstraction, the model registry, model selection/routing, streaming contract, reasoning display, tool calling, grounded web search, multimodal input, context management, structured outputs, and the AI-layer safety/cost requirements.
**Status:** Draft for build. Derived from `docs/research/04-ai-capabilities.md` and `docs/research/03-architecture.md` §5.
**Date:** 2026-05-27.
**Priority tags:** **[P0/MVP]** ship-blocking · **[P1]** fast-follow · **[P2]** later.

---

## 1. Summary & Purpose

This PRD specifies the model-facing capabilities that turn our chat UI into a product. Our positioning wedge is **multi-model + transparency**: users can pick among models from multiple providers, and every answer shows *which* model produced it (and, where available, token/cost). We deliver this cheaply via a **provider-abstraction layer** plus a **gateway/aggregator**, so we offer a rich model picker on day one without N bespoke integrations.

The defining engineering constraint is that **models, prices, IDs, and context windows move weekly**. This PRD therefore mandates a **data-driven model registry** (no hardcoded model facts) as a first-class, ship-blocking requirement — not an implementation detail. Everything user-facing about a model is read from configuration that can be hydrated from provider model-list APIs.

The MVP target persona is **power users / developers**, with a secondary **privacy-conscious prosumer** segment, and a simple **"Auto" default** so casual users never have to think about models. Privacy-first is a hard product principle: **no training on user chats by default**, which constrains provider/data choices (§6).

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
- **RAG over user documents** (vector DB, chunking, reranking) — **[P2]**; large-context "attach a doc" is the MVP bridge.
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
| U6 | power user | to toggle "thinking/reasoning effort" and optionally see the reasoning | I get deeper answers on hard problems and can inspect them | P0 |
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
- **FR-3 [P0]** Registry entries map to **capability tiers** (Fast / Smart / Pro). The UI and router reference tiers; tier→model mapping lives in config. *Acceptance: changing which concrete model backs "Smart" is a config edit with no deploy of app logic.*
- **FR-4 [P1]** Registry can be **hydrated/refreshed from provider model-list APIs** (e.g., available models, context limits) on a schedule, with a hand-maintained overlay for fields providers don't expose (tier, relative cost/speed labels, knowledge cutoff). *Acceptance: a registry refresh job updates available models without a deploy.*
- **FR-5 [P1]** Per-provider **fallback**: on provider error/timeout/rate-limit, retry the same logical model via an alternate provider/route, or downgrade tier per policy; log the substitution. (A gateway/OpenRouter provides this natively — prefer it over hand-rolling.) *Acceptance: simulated provider 5xx/timeout results in a successful fallback response or a clear, typed user-facing error, never a silent hang.*
- **FR-6 [P0]** **BYOK** (bring-your-own-key): users supply provider keys; keys encrypted at rest (KMS/envelope), never logged, scoped to user. **BYOK ships at launch** — it is the power-user margin de-risk + privacy/cost-control wedge (see PRD 05 §5). Policy (platform-keys vs BYOK default) coordinated with PRD 05. (Key-storage schema lives in PRD 04 `api_key` table, P0.)

### 4.2 Model picker, routing & persistence — **[P0/MVP]**
- **FR-7 [P0]** Default mode is **"Auto"** — the user need not choose a model. Auto is a *routing system, not a model*. *Acceptance: a new user can send a message and get a response with zero model selection.*
- **FR-8 [P0]** **Auto-routing (heuristic)**: route to a Fast/cheap model for simple queries and a Smart/Pro/reasoning model for hard ones, using cheap signals (prompt length, code presence, explicit "think hard" intent, attachment presence). *Acceptance: short trivia routes Fast; a long code-debugging prompt routes Smart/Pro; routing decision is recorded per turn.*
- **FR-9 [P0]** **Explicit model picker** presents **capability tiers** with optional drill-down to concrete models. The picker is driven by the registry and surfaces per-model metadata (context window, modalities, relative cost/speed, knowledge cutoff). *Acceptance: picker contents change when the registry changes, with no code edit.*
- **FR-10 [P0]** **Per-conversation model selection** persists; **per-message switching** is allowed mid-thread. *Acceptance: switching model mid-thread applies to subsequent turns and is persisted.*
- **FR-11 [P0]** **Per-turn model attribution is persisted and displayed**: every assistant message stores which model/provider produced it (and routing decision if Auto). This is the transparency wedge. *Acceptance: each assistant turn shows a model badge; reloading the thread preserves correct per-turn attribution even across mid-thread switches.* (Stored in the `Message.parts`/metadata per PRD 04 data model.)
- **FR-12 [P2]** Side-by-side multi-model comparison (parallel responses). Out of MVP scope.

### 4.3 Streaming & Stop/Abort — **[P0/MVP]**
- **FR-13 [P0]** All responses **stream tokens** (SSE). *Acceptance: first tokens render progressively, not as one blob.*
- **FR-14 [P0]** **Stop/Abort contract**: the client can cancel an in-flight generation; cancellation propagates to the provider request (abort fetch / close stream) so we stop billing. The partial response is preserved. *Acceptance: pressing Stop halts output within ~1s, the upstream request is aborted, and the partial turn is saved.*
- **FR-15 [P0]** Stop must work with **resumable streams**: if a Stop is issued from a resumed/different connection, the persistence layer reconciles stream state so no run is orphaned past timeout. (Coordinate with PRD 04 streaming design; the `Stream` table tracks active stream state.)
- *Note: the Stop button and streaming UI live in **PRD 01 (chat UI)**; this PRD owns the functional/abort contract behind it.*

### 4.4 Reasoning / "thinking" — **[P0/MVP]**
- **FR-16 [P0]** A **reasoning-effort toggle** ("effort/level" — e.g., off/low/medium/high) is mapped **per provider** in the registry (Anthropic adaptive/`display`, OpenAI `reasoning.effort`, Gemini `thinking_level`). The user sees one normalized control; the adapter maps it. *Acceptance: the same UI control produces correct provider-specific parameters; models that don't support reasoning hide the control.*
- **FR-17 [P0]** **Show only what the provider exposes.** Some providers return only a *summary* of reasoning (or omit it by default). Never fabricate, store, or display reasoning content the provider hides. *Acceptance: for a provider that returns no reasoning text, the UI shows no reasoning panel (or an empty-by-design state), not a hallucinated one.*
- **FR-18 [P0]** **Reasoning tokens are billed as output tokens** and must be included in token/cost accounting and the usage meter. *Acceptance: a high-effort reasoning turn shows materially higher output-token/cost counts that include reasoning tokens.*
- *Note: the collapsible "Thinking…" panel UI lives in **PRD 01**; this PRD owns the toggle mapping, accounting, and "only show what's exposed" rule.*

### 4.5 System prompt & custom instructions — **[P0/MVP]**
- **FR-19 [P0]** **App-level system prompt** (product persona, formatting, safety rules) is held server-side and is never overridable by user content (delimiter discipline, §6).
- **FR-20 [P0]** **User custom instructions** (name, tone, expertise level) are injected into every chat as clearly-delimited user-level preferences. *Acceptance: custom instructions affect responses and are editable/removable by the user.*
- **FR-21 [P2]** **Personas / Projects** (scoped system prompt + tools + knowledge files; persistent workspaces). Later.

### 4.6 Tool / function calling & agentic loop — **[P1]** (deferred from MVP per the lean-text-core scope decision)
- **FR-22 [P1]** Support **tool/function calling** with JSON-schema tool definitions, normalized across providers via the abstraction layer.
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
- **FR-27 [P1]** **Live web search/grounding** with **inline citations** (clickable sources). Two implementation patterns, presented as a tradeoff:
  - **(A) Provider built-in search** (OpenAI web-search tool, Gemini "Grounding with Google Search", Anthropic web search) — lowest integration cost, keeps the user's chosen chat model, per-call fees.
  - **(B) Dedicated search-grounded API (Perplexity Sonar)** — best-in-class cited freshness, citations as free metadata, but locks the search experience to one provider/model.
  - **Recommendation (default):** ship **provider built-in search** behind the abstraction so grounding works with whatever chat model the user selected (consistent with our multi-model wedge); evaluate **Sonar as an alternative "research"/grounded mode** — **[P1]** — as a fast-follow. *Acceptance: a "what happened this week" query returns an answer with at least one working, clickable citation.*
- **FR-28 [P1]** Retrieved web content is **untrusted** (indirect prompt injection) — see §6.
- **FR-29 [P2]** **RAG over user documents** (ingest → chunk → embed → hybrid retrieve → rerank → cite). Out of MVP. **Bridge:** use large-context "attach a document and ask" for small corpora in MVP (§4.9). Build full RAG when users need persistent knowledge bases / large corpora / freshness / auditability. (pgvector in the same Postgres per PRD 04.)

### 4.8 Multimodal — vision + documents **[P1]**; rest **[P2]** (vision/PDF deferred from MVP per the lean-text-core scope decision)
- **FR-30 [P1]** **Vision (image input)**: users attach images; vision-capable models answer about them. Registry marks which models support image input; non-vision models reject/hide attachments. *Acceptance: attaching a screenshot to a vision model yields a relevant answer; attaching to a non-vision model is blocked with a clear message.*
- **FR-31 [P1]** **PDF / document understanding** (native multimodal, no separate OCR pipeline for supported models). *Acceptance: a user can attach a PDF and ask questions about its content.*
- **FR-32 [P1]** **Cost gating for multimodal**: vision/document input can raise cost 5–10×; image/document tokens count toward the usage meter, and multimodal use may be gated by tier/limits (coordinate with PRD 05). *Acceptance: an image-bearing turn reflects added token cost in the meter.*
- **FR-33 [P2]** Image generation, STT, TTS, realtime/live voice. Later (separate models/endpoints/pricing; voice pulls WebSockets/realtime infra forward — see PRD 04 §4/§11).

### 4.9 Context management — **[P0/MVP]**
- **FR-34 [P0]** **Per-model token counting**: token counts/limits (`context_window` and `max_output_tokens` per the §5.2 registry schema) come from the registry per model; **do not assume a shared tokenizer** (counts vary 10–20% across providers). *Acceptance: the context/usage display uses the selected model's own limits.*
- **FR-35 [P0]** **Summarize-on-threshold**: when context use crosses ~70–80% of the model's window, LLM-summarize older turns while keeping recent turns full-fidelity + the summary. Sliding-window fallback acceptable as a simpler first cut, but summarization is the target. *Acceptance: a thread long enough to approach the window keeps responding correctly instead of erroring; summarization is visible/logged.*
- **FR-36 [P0]** **Visible cost/usage meter**: surface tokens used (input/output, including reasoning) and, where the provider/registry gives price, an estimated cost per message and per conversation. *Acceptance: a meter updates per turn and includes reasoning tokens.*
- **FR-37 [P1]** Cost levers: **prompt caching** (where supported), **batch APIs** for async work, capping max output + reasoning effort, summarizing instead of resending full history.

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

> **This is a ship-blocking architectural requirement, not a nice-to-have.** Models, prices, IDs, context windows, "which is flagship," reasoning-API shape, and free-tier rules are **FAST-MOVING** and drift within weeks. Hardcoding them creates silent staleness and incorrect cost/UX.

### 5.1 Rules
1. **Models are configuration, not constants.** All model facts live in a registry, editable without an app-logic deploy.
2. **No hardcoded model IDs, prices, or context windows** anywhere in app/UI logic. App code references **capability tiers** and **registry fields**.
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
| `supports_tools`, `supports_structured_output`, `supports_web_search` | Feature gating per model |
| `price_in` / `price_out` (per-M tokens) | Cost meter (nullable; from live source where possible) |
| `relative_cost` / `relative_speed` labels | Picker hints without committing to exact numbers |
| `knowledge_cutoff` | Picker transparency |
| `status` (available / preview / deprecated), `fallback_to` | Routing & graceful degradation |

### 5.3 Provider recommendation (a recommendation, not a hardcoded list)

- **Direct integrations for primary tiers:** **Anthropic + OpenAI + Google Gemini.** Rationale: clean APIs, best first-party features (reasoning, tools, structured outputs), and Gemini covers the strongest native multimodal (incl. video later) and very large context.
- **Breadth + fallback layer:** **OpenRouter** (and/or the chosen gateway) to instantly add Mistral, DeepSeek, Llama, etc. behind one integration, with automatic provider fallback — a rich picker on day one without N integrations.
- **Defer as *direct* integrations:** DeepSeek / Mistral / Llama — obtain via the breadth layer initially.
- **Direct-vs-aggregator tradeoff:** direct = best features/latency/SLA/data-control; aggregator = breadth + fallback fast, thin fee, less control. **Recommended: both** (direct for primaries, aggregator for breadth/fallback). Final gateway choice coordinated with **PRD 04 §5** (Vercel AI Gateway vs OpenRouter vs LiteLLM) — architecture's current lean is **Vercel AI Gateway as the MVP default**, with OpenRouter as the breadth/fallback layer (not necessarily the default route).
- **Privacy constraint on provider choice:** prefer routes/settings with **no training on user data by default**; note data-residency/governance concerns for some providers (e.g., DeepSeek) when selecting defaults (§6).

---

## 6. Safety, Privacy & Cost-Control Requirements

### 6.1 Safety & moderation — **[P0]**
- **SR-1 [P0]** Moderate **both input and output** (provider safety filters / a moderation endpoint / open classifier). Block or flag per policy.
- **SR-2 [P0]** **Prompt-injection-aware architecture** (mitigation is architectural, not format choice):
  - Separate system instructions from user/untrusted data with **clear delimiters**; user content can never override safety sections.
  - **Treat tool results, web/search content, and (future) RAG documents as untrusted** — indirect prompt injection via retrieved content is a top risk.
  - **Least-privilege tools**; **human confirmation for high-impact actions** (FR-25).
  - **Validate all structured output against strict schemas** (FR-39); treat model output as untrusted.
- **SR-3 [P0]** Run prompt-injection / system-prompt-leakage checks in CI, alongside the **FR-2 no-hardcoded-model-facts gate** (a grep for any concrete model ID or `$`/token figure outside the registry/config fails the build). (Coordinate with PRD 04 §9.)

### 6.2 Privacy — **[P0]**
- **PR-1 [P0]** **No training on user chats by default.** Choose provider routes/settings that honor this; document per-provider data handling in the registry/config. This constrains which providers/routes can be defaults.
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
| **PRD 04 — Architecture / Provider layer** | Implements the provider abstraction + gateway (§5 here ↔ §5 there: AI SDK providers + AI Gateway vs OpenRouter vs LiteLLM), SSE + resumable streams + Stop reconciliation, data model (`Message.parts` attribution, `Stream`, `ApiKey`, future `Embedding`), moderation/PII in CI, rate limiting. |
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
4. **Built-in search vs Perplexity Sonar.** Default is provider built-in (keeps chosen model); is Sonar worth a separate "research mode"? Re-evaluate after MVP. (§4.7)
5. **Multimodal cost gating.** 5–10× cost — what tier/limit gating? Owned with PRD 05. (FR-32)
6. **Memory transparency & privacy.** When we add memory: consent model, editability UX, "cite when used," temporary-chat guarantees. (FR-40)
7. **BYOK policy.** Platform-keys-only vs user BYOK at launch — affects billing/metering/key-encryption infra. (FR-6; PRD 04 §5, PRD 05)
8. **Reasoning-API drift.** Defaults change (e.g., flagship models omitting thinking text by default); the toggle mapping must absorb this via the registry, not code. (FR-16)
9. **Provider data-handling for "no training by default."** Which provider routes/settings actually guarantee it, and which providers can be defaults given residency/governance concerns? (PR-1)

---

## 10. References

**Primary research:** `docs/research/04-ai-capabilities.md` (model market, capability patterns, MVP-vs-later recommendations). **Architecture alignment:** `docs/research/03-architecture.md` §5 (provider abstraction, gateway options, BYOK).

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
> Pull these from provider model-list APIs / live pricing at build & runtime; keep them in the **model registry (§5)**, never in app/UI logic:
> - **All pricing** ($/M tokens) — re-priced and promo'd frequently.
> - **Exact model names/IDs and "which is flagship"** — superseded within weeks.
> - **Context windows & max output** — change per model revision.
> - **Reasoning/"thinking" API shape & defaults** — provider-specific and drifting (some flagships now omit thinking text by default).
> - **Free-tier / rate-limit rules** — change per provider policy.
> - **Modality support per model** — vision/doc/audio/video/image-gen vary and evolve.
> - **MCP spec/version & server ecosystem** — actively evolving.
>
> If a number or ID appears in code or UI strings instead of the registry, it is a bug.
