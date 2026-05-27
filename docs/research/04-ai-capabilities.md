# Research 04 — AI Capabilities & Model Integration

**Workstream:** AI Capabilities & Model Integration (the "intelligence" behind the chat)
**Date compiled:** 2026-05-27
**Status:** Research phase — feeds PRDs. Not a PRD or implementation spec.
**Scope:** Current (2025–2026) model offerings and capability patterns for a web/mobile AI chat product comparable to ChatGPT, Claude, Gemini, and Perplexity web apps.

---

## 0. How to read this document (verification discipline)

The AI model market moves weekly. Prices, model names, context windows, and tier structures change constantly. To keep this useful:

- **[VERIFIED]** = confirmed against a primary/provider source (or close secondary) during this research pass (2026-05-27). Still re-verify at build time.
- **[RECALLED]** = from general knowledge / pattern understanding, not freshly confirmed from a source. Treat as directionally correct only.
- **[FAST-MOVING — RE-VERIFY AT BUILD]** = a fact that is near-certain to drift (pricing, exact model IDs, context windows, which model is "flagship"). **Do not hardcode these.** Pull them from the provider's live model-list API at runtime where possible.

> **Architectural takeaway up front:** Treat models as a *configuration*, not a constant. Build a provider-abstraction layer and a model registry that is data-driven (ideally hydrated from provider model-list endpoints). Everything in the tables below will be stale within weeks.

---

## 1. Model Providers & Current Flagship Models

### 1.1 Provider/model comparison table

Pricing is USD per **million tokens** (input / output), standard tier, non-cached, non-batch. Context windows are total (input) tokens. **All pricing/context/IDs below are [FAST-MOVING — RE-VERIFY AT BUILD].**

| Provider | Flagship / notable models | Context window | Price in/out ($/M tok) | Modalities (in → out) | Reasoning/"thinking" | Notes |
|---|---|---|---|---|---|---|
| **OpenAI** | GPT-5.5, GPT-5.5 Pro (flagship); GPT-5.x family incl. Instant/Thinking; Realtime 2 (voice) | 1M (400K in Codex) [VERIFIED] | ~$5 / $30 (GPT-5.5) [VERIFIED] | text+image → text; image gen; realtime audio (separate models) | Reasoning effort: none/low/medium/high/xhigh [VERIFIED] | Structured outputs, function calling, MCP, web search, computer use built in [VERIFIED] |
| **Anthropic (Claude)** | Opus 4.7 (flagship), Sonnet 4.6 (recommended default), Haiku 4.5 (fast/cheap) | Opus/Sonnet **1M**; Haiku **200K** [VERIFIED] | Opus $5/$25; Sonnet $3/$15; Haiku $1/$5 [VERIFIED] | text+image → text (vision) [VERIFIED] | Adaptive thinking (Opus/Sonnet); extended thinking (Sonnet/Haiku) [VERIFIED] | Max output: Opus 128K, Sonnet/Haiku 64K. Prompt caching ~90% off cached input; Batch 50% off [VERIFIED] |
| **Google (Gemini)** | Gemini 3.1 Pro (flagship preview), 3.5 Flash, 3.1 Flash-Lite; 2.5 Pro/Flash/Flash-Lite (mature) | 2.5 Pro 1M; **3.1 Pro up to 2M** [VERIFIED] | 2.5 Pro $1.25/$10 (≤200K), $2.50/$15 (>200K); 3 Pro $2/$12 (≤200K) [VERIFIED] | text+image+audio+**video** → text; native image gen (Nano Banana), TTS, Live voice [VERIFIED] | thinking_level LOW/MEDIUM/HIGH (3.1 Pro) [VERIFIED] | Broadest native multimodality (video in). Pro tiers paid-only as of Apr 2026; Flash keeps free tier [VERIFIED] |
| **Mistral** | Mistral Large 3, Medium 3.5, Small 4; Magistral (reasoning); Devstral/Codestral (code); Ministral (small) | ~128K typical; Large 3 ~256K; Small 4 262K [VERIFIED] | Large 3 ~$2/$6; Medium ~$0.40/$2; Small ~$0.20/$0.60 [VERIFIED] | text+image (Pixtral-derived) → text | Magistral line is reasoning-focused | EU-based; cheapest flagship output tier; smaller context than US frontier [VERIFIED] |
| **DeepSeek** | V4 / V4-pro (latest), V3.x (chat), R1 (reasoning) | V4 **1M**; V3.x ~131K; R1 ~64K [VERIFIED] | V4 ~$0.30/$0.50; V3.x ~$0.28/$0.42; cached input ~$0.03 [VERIFIED] | text → text (some vision variants) | R1 + V4 hybrid reasoning modes [VERIFIED] | Extremely low cost; data-residency/governance concerns for some orgs [RECALLED] |
| **Meta Llama (open weights)** | Llama 4 Scout (10M ctx), Maverick (1M ctx) — MoE, natively multimodal | Scout **10M**; Maverick 1M [VERIFIED] | Self-host = $0/token; via providers Scout ~$0.08–0.15/M in [VERIFIED] | text+image → text (natively multimodal) [VERIFIED] | — | Open-weight (license restrictions). Run via Groq/Together/Fireworks/Bedrock or self-host [VERIFIED] |

### 1.2 Aggregators & inference providers [VERIFIED]

| Platform | What it is | Pricing model | Why use it |
|---|---|---|---|
| **OpenRouter** | API aggregator / router across 300+ models, one API key/format | Passthrough provider price + ~5.5% fee on credit purchases (no per-token markup) | One integration → many models; **automatic provider fallback** (e.g., Anthropic API → Bedrock → Vertex for Claude). Fastest path to multi-model. |
| **Groq** | Own hardware (LPU); hosts open models | $0–~$3/M | Lowest first-token latency; great for fast/cheap open models |
| **Together AI** | Own GPU clusters (H100/H200/B200) | Competitive per-token for open models | No middleman markup; inference + fine-tuning on one platform |
| **Fireworks AI** | Own GPU clusters | $0–~$9/M | Inference + fine-tuning; production open-model serving |

**Implication:** For an MVP, **OpenRouter is the fastest way to support many models behind one integration** and get built-in fallback. The tradeoff is a thin fee, less control over data-handling/SLA, and occasionally trailing the very newest first-party features. A common pattern: direct first-party APIs (OpenAI/Anthropic/Google) for the primary models you care most about, plus OpenRouter as a breadth/fallback layer.

---

## 2. Multi-Model Support & Model Picker UX

### 2.1 What the leaders do [VERIFIED for ChatGPT]
- **ChatGPT (2026):** Built around the GPT-5 family — **Instant** (default, incl. free), **Thinking** (paid, deeper reasoning), **Pro** (highest capability). A single **"Auto" router** picks Instant vs Thinking per query; "Auto is a routing system, not a model." Free users get no picker (always Instant) and rate-limited flagship access (e.g., N flagship messages per rolling window, then auto-downgrade to a mini model).
- **Pattern:** Hide complexity by default (Auto), but expose an explicit model dropdown for power users on paid tiers.

### 2.2 Design patterns to support
- **Tiered presentation:** Present *capability tiers* ("Fast", "Smart/Thinking", "Pro/Max") rather than raw model IDs to most users. Map tiers → concrete models in config.
- **Auto-routing:** Cheap classifier (or heuristics: length, code presence, "think hard" intent) routes simple queries to fast/cheap models, hard ones to flagship/reasoning. Saves cost and latency.
- **Fallbacks:** On provider error/timeout/rate-limit, retry same model on alternate provider (OpenRouter does this natively), or downgrade tier. Critical for reliability.
- **Per-conversation model lock vs per-message switching:** Allow switching mid-thread; persist which model produced which turn (affects re-streaming, cost display, and reasoning-token handling).
- **Surface metadata:** Context window, modality support, relative cost/speed, knowledge cutoff — drive the picker from the model registry.

---

## 3. Streaming & Reasoning Display

### 3.1 Token streaming [VERIFIED/RECALLED]
- SSE / chunked streaming is table stakes; all major providers stream tokens. Use the **Vercel AI SDK / AI Gateway** or LangChain-style abstractions to normalize streams across providers, or build a thin SSE layer.
- **Stop/abort:** Client must be able to cancel an in-flight stream. Implement via `AbortController` on the client and propagate cancellation to the provider request (close the stream / abort fetch). This is a hard UX requirement — every leading product has a "Stop" button.

### 3.2 Reasoning / "thinking" tokens [VERIFIED]
This area changed materially in 2026 and is **[FAST-MOVING]**:
- **Anthropic:** `thinking` config with a `display` field. `display: "summarized"` streams a *condensed summary* of the chain of thought. **Claude Opus 4.7+ requires adaptive thinking** (legacy fixed-budget API rejected) and **omits thinking text by default** — thinking blocks are present but empty unless you set `display: "summarized"`.
- **OpenAI:** o-series/GPT-5.x expose reasoning via thinking-token output and a `reasoning.effort` knob (none/low/medium/high/xhigh).
- **Google Gemini:** `thinking_level` = LOW/MEDIUM/HIGH (3.1 Pro). Note **thinking tokens are billed as output tokens** and can dramatically inflate output cost — a known billing trap.

**UX implications:**
- Render thinking in a collapsible "Thinking…" / "Reasoning" panel (Claude/ChatGPT/Gemini all do this). Default collapsed; expandable.
- **Cost & token accounting must include reasoning tokens** in output billing. Surface this in any cost meter.
- Reasoning content is provider-shaped and sometimes only a *summary* — don't assume you get the raw chain of thought; don't store/show what the provider hides.
- Expose a "thinking effort"/"extended thinking" toggle mapped per-provider.

---

## 4. Tool / Function Calling & Agentic Loops

### 4.1 Core mechanics [VERIFIED/RECALLED]
- **Tool definition:** Register functions with a JSON-schema describing name, description, parameters. Provider-specific wrappers exist but the shape is convergent.
- **Loop:** Model emits structured tool call(s) → app executes → results fed back → model continues. Repeat until done. This is the **ReAct** loop (Thought → Action → Observation), the 2026 standard for multi-step work.
- **Parallel tool calls:** Model can emit multiple independent tool calls in one turn; runtime executes concurrently. Reported ~1.4×–2.4× (up to ~3.7×) latency wins on suitable tasks.
- **Practical bottlenecks at scale:** shared API quotas, OAuth token expiry, schema drift. Smaller "distilled" tool-use models in 2026 cut cost/latency of agentic loops.

### 4.2 Product implications
- Build an **agentic loop runtime** with: max-iteration caps, per-tool timeouts, concurrency control, and tool-error handling that re-prompts the model.
- Stream intermediate steps to the UI (tool name, args, result) for transparency — leading apps show "Searching the web…", "Running code…", etc.
- Tools should be permission-gated (user consent for actions with side effects).

---

## 5. Web Search & RAG

### 5.1 Live web search / grounding [VERIFIED]
Two patterns:
1. **Built-in provider web search/grounding:** OpenAI web-search tool, Google "Grounding with Google Search" (Gemini), Anthropic web search tool. Lowest integration cost; provider handles retrieval + citations. Per-call/tool fees apply.
2. **Dedicated search-grounded API (Perplexity Sonar):** Every Sonar Online/Pro request runs **live web retrieval before generation** and returns **inline citations as metadata at no extra cost**. Tiers: lightweight lookup, Sonar Pro (multi-source, richer citations: titles/snippets/dates), reasoning, and deep-research (exhaustive multi-step). Sonar leads factuality benchmarks (F-score ~0.86 for Sonar Pro). Pricing e.g. Sonar small ~$0.20/$0.20, Pro ~$3/$15 per M tok.
   - **Tradeoff:** Sonar is the cleanest "Perplexity-style" experience (built-in citations, freshness) but locks you to one provider for the search experience; provider built-in search lets you keep your chosen chat model.

### 5.2 RAG over user documents [VERIFIED/RECALLED]
Standard 2026 pipeline:
- **Ingest → chunk → embed → store in vector DB → hybrid retrieve → rerank → inject → generate with citations.**
- **Chunking:** Context-aware/semantic partitioning (break where cosine distance between adjacent sentences exceeds a threshold) beats fixed-size chunks. Bad chunking is the #1 quality killer.
- **Hybrid search (keyword + semantic) is the single biggest quality win** over naive vector-only RAG; add a reranker for the next jump.
- **Embeddings:** provider embedding models (OpenAI, Gemini Embedding, Cohere, Voyage) or open models. Vector stores: pgvector/Postgres, Pinecone, Weaviate, Qdrant, etc.
- **Citations & freshness:** Return source spans with answers; show clickable citations (Perplexity/ChatGPT pattern). Track document recency; re-embed on update.
- **Caveat:** With 1M–2M token context windows now common, "just stuff the docs in context" is viable for small corpora and competes with RAG for some use cases — but RAG still wins on cost, large corpora, freshness, and auditability.

---

## 6. Multimodal

| Capability | State of the art (2026) | Notes / [VERIFIED] |
|---|---|---|
| **Vision (image input)** | Universal across OpenAI, Anthropic, Gemini, Llama 4, Mistral (Pixtral) | All current Claude/GPT-5.x/Gemini support image input [VERIFIED]. ~765+ tokens per image — cost adds up [VERIFIED] |
| **Document/PDF understanding** | Native in frontier models; multimodal models skip separate OCR pipeline | Strong for forms, scans, charts [VERIFIED] |
| **Video input** | **Gemini is the standout** (native video) | Differentiator if video matters [VERIFIED] |
| **Image generation** | OpenAI (gpt-image), Google Nano Banana / Nano Banana Pro, others | Separate models/endpoints, separate pricing [VERIFIED] |
| **Speech-to-text (STT)** | Whisper / Realtime Whisper (OpenAI), Gemini, many open models | ~$0.006/min Whisper-class transcription [VERIFIED] |
| **Text-to-speech (TTS)** | OpenAI, Gemini Flash TTS, ElevenLabs, etc. | — |
| **Realtime / live voice** | OpenAI **Realtime 2** (speech-to-speech, configurable reasoning), Gemini **Live**, Realtime Translate | Speech-to-speech agents are productized [VERIFIED] |

**Cost warning [VERIFIED]:** Adding vision/audio/video can raise infra cost 5–10×. A 10-min audio clip ≈ 10K tokens. Budget and gate multimodal features carefully.

---

## 7. System Prompts, Custom Instructions, Personas, Memory

### 7.1 System prompts / custom instructions / personas
- **System prompt:** app-level instructions (product persona, safety rules, formatting). Keep server-side; never let user content override safety sections (delimiter discipline — see §9).
- **Custom instructions:** user-level stable preferences (name, tone, expertise level) injected into every chat. (ChatGPT/Claude pattern.)
- **Personas / GPTs / Projects:** scoped configurations (custom system prompt + tools + knowledge files) that don't leak across contexts. "Projects" = persistent workspaces where context accumulates.

### 7.2 Memory & personalization [VERIFIED]
- **ChatGPT memory (2026):** two parts — **saved memories** (explicit, editable list) + **reference chat history** (implicit recall of patterns).
- **Claude memory (2026):** on by default for all tiers since Mar 2026; remembers preferences/projects/working style; **explicitly cites when it uses a memory**; controls = on / off / Temporary Chat.
- **Rule of thumb (industry):** Custom Instructions for stable identity traits; Memory for evolving context; Projects for tightly scoped contexts.
- **Build implications:** memory is a *product feature you build*, not purely a model feature — store extracted facts, give users an editable memory list, support "temporary/incognito chat," and be transparent about recall. Privacy/consent and easy deletion are mandatory.

---

## 8. Context Management, Token Counting & Cost Control

[VERIFIED/RECALLED]
- **Token counting varies 10–20% across providers** for the same text → don't share one tokenizer assumption across models. Use each provider's tokenizer/limits; expose `max_input_tokens`/`max_tokens` from the model registry (Anthropic exposes these via a Models API).
- **Truncation/summarization strategies:**
  - **Sliding window:** keep last N messages — simplest, can drop important early context.
  - **Summarize-on-threshold:** when ~70–80% of context is used (or at 32K–100K), LLM-summarize older turns; keep recent turns full-fidelity + the summary. Common heuristic.
  - **Semantic retrieval over history:** retrieve relevant old turns by similarity (RAG over conversation) instead of pure recency.
  - **Memory tiering:** working / short-term (session) / long-term (cross-session) tiers with different retention.
- **Cost control levers:** model/tier routing (§2), prompt caching (Anthropic ~90% off cached input; OpenAI/DeepSeek similar), batch APIs (50% off, async), capping max output + reasoning effort, summarizing instead of resending full history, and **counting reasoning tokens in cost** (they bill as output).

---

## 9. Structured Outputs, Safety & Moderation

### 9.1 Structured outputs / JSON mode [VERIFIED]
- Native **Structured Outputs / JSON-schema-constrained decoding** in OpenAI (GPT-5.x), and JSON modes across providers. Use for tool args, extraction, and machine-readable responses.
- **Security caveat:** grammar/schema-constrained decoding has been weaponized — **Constrained Decoding Attacks (CDA)** embed malicious intent in schema-level grammar while the surface prompt looks benign (reported ~96% attack success in research). **Always validate model output against a strict schema and treat it as untrusted before use.**

### 9.2 Safety & moderation [VERIFIED/RECALLED]
- **Moderation:** pre- and post-output moderation/classifier filters (OpenAI moderation endpoint, provider safety filters, or open classifiers). Filter both user input and model output.
- **Prompt injection / jailbreak:** all structured formats are injectable ("policy puppetry"). Mitigation is **architectural, not format choice**:
  - Separate user/untrusted data from system instructions with clear delimiters.
  - Treat tool/web/RAG content as untrusted (indirect prompt injection via retrieved docs is a top risk).
  - Validate outputs against schemas; least-privilege tools; human confirmation for high-impact actions.
- Layered defenses: instruction tuning, RLAIF, system-prompt safety guidelines, plus app-level filters.

---

## 10. Model Context Protocol (MCP) & Extensibility

[VERIFIED]
- **MCP** (open standard from Anthropic, Nov 2024) is now the de-facto integration standard for connecting models to tools/data/services. Adopted by **OpenAI, Google DeepMind, Microsoft, AWS**; governed by the **Linux Foundation's Agentic AI Foundation** (vendor-neutral). >10,000 public MCP servers by Mar 2026.
- Supported natively by Claude, ChatGPT/GPT, Gemini, Copilot, Cursor, etc. Pre-built servers for Drive, Slack, GitHub, Postgres, etc.
- **MCP Apps** extension standardizes delivering **interactive UIs** (forms, dashboards) from servers to host apps.
- **Implication:** Supporting MCP (as a client/host) is the standard way to offer extensibility/connectors/plugins without bespoke integrations. Strong "later" candidate; powerful differentiator but adds security surface (untrusted servers/tools → injection risk).

---

## 11. Prompt Templates, Prompt Library & Prompt Quality

[RECALLED/general pattern]
- **Prompt templates / library:** reusable parameterized prompts ("/commands", starter prompts, saved prompts). Low-effort, high-value UX (ChatGPT prompt suggestions, Claude prompt library, slash commands).
- **Prompt quality features:** prompt improver/optimizer (provider tools exist), variable insertion, few-shot examples, system-prompt templating per persona.
- Cheap to build, improves perceived quality and onboarding; good MVP+1 candidate (basic starter prompts in MVP).

---

## 12. Recommended AI Capability Set — MVP vs Later

### 12.1 Recommended providers/models to support FIRST (MVP)
Prioritize breadth-via-abstraction with a few high-quality direct integrations:
1. **Anthropic (Claude)** — Sonnet 4.6 as a strong, cost-balanced default; Haiku 4.5 for fast/cheap; Opus 4.7 as premium tier. Clean API, strong tool use, 1M context, good safety posture. **[VERIFIED pricing/IDs — re-verify]**
2. **OpenAI (GPT-5.x)** — GPT-5.x Instant/Thinking for the "everyone expects ChatGPT-quality" baseline; broad feature set (structured outputs, realtime voice later).
3. **Google Gemini** — Flash tier for cost-efficient high-volume + the only strong **native video/multimodal** option; 1–2M context for long-doc use cases.
4. **OpenRouter as the breadth + fallback layer** — instantly adds Mistral, DeepSeek, Llama, and dozens more behind one integration, with automatic provider fallback. Lets you offer a rich model picker on day one without N integrations.

> **Recommendation:** Build a provider-abstraction layer from day one. Integrate **Anthropic + OpenAI + Gemini directly** for the primary tiers, and **OpenRouter** for breadth/fallback. Defer DeepSeek/Mistral/Llama as *direct* integrations (get them free via OpenRouter initially).

### 12.2 The 6–10 most important AI capabilities for MVP
1. **Token streaming with Stop/Abort** — non-negotiable baseline.
2. **Multi-model picker with capability tiers** (Fast / Smart / Pro) + basic auto-routing, driven by a data-driven model registry.
3. **System prompt + user custom instructions** (persona/tone/preferences).
4. **Reasoning/"thinking" display** (collapsible panel) with correct token/cost accounting — frontier models default to this.
5. **Vision (image input) + PDF/document understanding** — universally expected, low marginal effort on multimodal models.
6. **Tool/function calling with a basic agentic loop** (max-iteration caps, parallel tools, streamed steps) — foundation for everything else.
7. **Live web search/grounding** — via provider built-in search (or Perplexity Sonar) to deliver the "Perplexity-style" cited answers users now expect.
8. **Context management** — summarize-on-threshold + per-model token counting + a visible cost/usage meter.
9. **Structured outputs/JSON mode + output schema validation** — needed for reliable tool args and any structured features.
10. **Baseline safety**: input/output moderation + prompt-injection-aware architecture (delimiters, untrusted-content handling, least-privilege tools).

### 12.3 Defer to LATER (post-MVP), with rationale
| Capability | Why defer | Trigger to build |
|---|---|---|
| **RAG over user documents** | Heavy infra (vector DB, chunking, reranking, eval); large-context can substitute for small corpora | When users need persistent doc knowledge bases / large corpora / auditability |
| **Persistent cross-chat memory** | Product + privacy complexity (editable memory, consent, deletion) | After core chat is solid; high retention value though — fast-follow |
| **Image generation** | Separate models/cost; not core to "chat" | When creative use cases prioritized |
| **Realtime voice (speech-to-speech)** | Complex latency/infra; separate models | Mobile-first voice push |
| **STT/TTS (non-realtime)** | Easier than realtime; nice-to-have | Accessibility / mobile dictation |
| **MCP / connectors / plugins** | Powerful but big security surface; ecosystem-dependent | When extensibility/enterprise connectors become a priority |
| **Prompt library/optimizer** | Cheap but not core | Fast-follow; ship basic starter prompts in MVP |
| **Advanced auto-routing/classifier** | Heuristic routing is enough at first | When scale/cost pressure justifies a trained router |

### 12.4 Key tradeoffs to flag for the PRD
- **Direct APIs vs OpenRouter:** direct = best features/latency/SLA/data-control; OpenRouter = breadth + fallback fast, small fee, less control. Recommended: both (direct for primaries, OpenRouter for breadth).
- **Big context window vs RAG:** 1M–2M context can defer RAG for small/medium corpora but costs more per call and lacks freshness/auditability. Start with large-context "attach a doc" before full RAG.
- **Reasoning models = better answers but higher latency + output cost** (thinking tokens bill as output). Gate behind a tier/toggle and meter clearly.
- **Built-in provider search vs Perplexity Sonar:** built-in keeps your chosen chat model + lower integration; Sonar gives best-in-class cited freshness but is its own provider/experience.
- **Multimodal cost:** 5–10× infra impact — gate vision/audio/video and meter usage.

---

## 13. Explicitly fast-moving facts — RE-VERIFY AT BUILD TIME

Do **not** hardcode any of the following; pull from provider model-list APIs / live pricing pages at implementation:
- **All pricing** (every $/M token figure here). Providers re-price and run promos frequently (e.g., DeepSeek noted active discount windows in 2026). **[FAST-MOVING]**
- **Exact model names/IDs and which is "flagship"** — Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5; OpenAI GPT-5.5 / GPT-5.x; Gemini 3.1 Pro / 3.5 Flash; Mistral Large 3; DeepSeek V4; Llama 4 Scout/Maverick — all dated and superseded quickly. **[FAST-MOVING]**
- **Context window sizes & max output** (Opus/Sonnet 1M, Gemini up to 2M, Llama Scout 10M, etc.). **[FAST-MOVING]**
- **Reasoning/thinking API shape** — Anthropic's `display`/adaptive-thinking, OpenAI `reasoning.effort` levels, Gemini `thinking_level`; defaults change (Opus 4.7 now omits thinking text by default). **[FAST-MOVING]**
- **Free-tier / rate-limit rules** (e.g., Gemini Pro paid-only as of Apr 2026; ChatGPT free flagship caps). **[FAST-MOVING]**
- **MCP spec/version, governance, server ecosystem** — actively evolving (Streamable HTTP, OAuth 2.1, MCP Apps). **[FAST-MOVING]**
- **Modality support per model** (image gen endpoints, realtime voice model names like "Realtime 2"). **[FAST-MOVING]**

---

## 14. Sources

Verified/consulted during this pass (2026-05-27):

- Anthropic — Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Anthropic — Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic — Extended thinking: https://platform.claude.com/docs/en/build-with-claude/extended-thinking
- Anthropic — Streaming: https://platform.claude.com/docs/en/build-with-claude/streaming
- Anthropic — Introducing MCP: https://www.anthropic.com/news/model-context-protocol
- Anthropic — Donating MCP to Agentic AI Foundation: https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
- OpenAI API — Models: https://developers.openai.com/api/docs/models
- OpenAI API — GPT-5.5 model: https://developers.openai.com/api/docs/models/gpt-5.5
- OpenAI API — Pricing: https://developers.openai.com/api/docs/pricing
- OpenAI — Introducing GPT-5.5: https://openai.com/index/introducing-gpt-5-5/
- OpenAI Help — GPT-5 in ChatGPT (model picker/routing): https://help.openai.com/en/articles/11909943-gpt-5-in-chatgpt
- Google — Gemini API models: https://ai.google.dev/gemini-api/docs/models
- Google — Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- Mistral pricing/catalog: https://llm-stats.com/providers/mistral ; https://tokenmix.ai/blog/mistral-api-pricing
- DeepSeek — Models & pricing: https://api-docs.deepseek.com/quick_start/pricing ; https://www.nxcode.io/resources/news/deepseek-api-pricing-complete-guide-2026
- Meta — Llama 4 herd: https://ai.meta.com/blog/llama-4-multimodal-intelligence/ ; https://www.llama.com/
- OpenRouter — Pricing: https://openrouter.ai/pricing ; AI inference providers compared: https://infrabase.ai/blog/ai-inference-api-providers-compared
- Perplexity — Sonar API quickstart: https://docs.perplexity.ai/docs/sonar/quickstart ; Sonar Pro intro: https://www.perplexity.ai/hub/blog/introducing-the-sonar-pro-api
- MCP — 2026 guide / adoption: https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026 ; https://en.wikipedia.org/wiki/Model_Context_Protocol
- RAG 2026: https://www.techment.com/blogs/rag-in-2026/ ; https://endjin.com/blog/2026/02/what-is-retrieval-augmented-generation-rag ; https://www.ibm.com/think/topics/retrieval-augmented-generation
- Tool/function calling & parallel tools: https://www.codeant.ai/blogs/parallel-tool-calling ; https://www.futureinsights.com/function-calling-tool-use-patterns-llm/
- Reasoning tokens billing trap: https://tokenmix.ai/blog/thinking-tokens-billing-trap-2026 ; OpenRouter reasoning tokens: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
- Multimodal 2026: https://myengineeringpath.dev/genai-engineer/multimodal-ai/ ; https://www.kdnuggets.com/the-multimodal-ai-guide-vision-voice-text-and-beyond
- Memory/personalization: https://lumichats.com/blog/claude-memory-2026-complete-guide-how-to-use ; https://www.knightli.com/en/2026/05/07/chatgpt-claude-gemini-memory-comparison/
- Context management: https://blog.logrocket.com/llm-context-problem/ ; https://earezki.com/ai-news/2026-04-24-the-hidden-challenge-of-multi-llm-context-management/
- Structured outputs / injection / safety: https://arxiv.org/pdf/2503.24191 ; https://dev.to/programmingcentral/shielding-your-llms-a-deep-dive-into-prompt-injection-jailbreak-defense-590p
