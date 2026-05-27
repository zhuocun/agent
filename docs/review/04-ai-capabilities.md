# AI Capabilities & Model Layer — Fresh Research + PRD Review (2026-05-27)

**Reviewer:** Senior AI/ML product researcher
**Scope:** (1) fresh 2025–2026 online research on the model landscape/capabilities not already in the existing docs; (2) a critical review of `docs/prd/02-ai-capabilities.md`.
**Inputs reviewed:** `docs/research/04-ai-capabilities.md`, `docs/prd/02-ai-capabilities.md`, `docs/prd/00-product-overview.md`.
**Positioning under review:** transparent, multi-model, privacy-first chat. Wedge = model choice + per-message transparency + heuristic auto-routing to a cheap default + BYOK at launch. MVP = lean text-core; vision/PDF, tools/function-calling, web-search/citations deferred to P1.

**Confidence flags:** **[Verified]** = confirmed against a first-party/provider source during this pass (2026-05-27). **[Recall]** = pattern knowledge, not freshly confirmed. **[Uncertain]** = could not verify a specific number/claim; treat as directional only. All model facts are FAST-MOVING — re-verify at build.

> **Headline:** The existing docs are unusually good — disciplined about not hardcoding model facts, and most numbers are still accurate as of today. The biggest substantive gaps are: (a) **xAI/Grok is entirely missing** despite being a credible cheap-frontier option and explicitly in scope; (b) the docs under-credit how far **gateway-level features** (Vercel AI Gateway web search, cross-model fallback, Portkey/LiteLLM guardrails) have advanced, which changes several MVP-vs-P1 calls; (c) a handful of **specific model facts have already drifted** (DeepSeek pricing, the OpenAI API lineup naming, Anthropic now having native Structured Outputs, Opus 4.7's new tokenizer). Details below.

---

## 2. New ideas & opportunities (not in the existing docs)

### 2.1 xAI / Grok is a missing provider — and a strong cheap-frontier option **[Verified]**
The existing research table (§1.1) and PRD §5.3 cover OpenAI, Anthropic, Google, Mistral, DeepSeek, Meta — but **omit xAI/Grok entirely**. As of May 2026, **Grok 4.3** (launched 2026-04-30) is a frontier-tier model at **$1.25 in / $2.50 out per 1M, 1M context, cached input ~$0.05/M** — i.e., flagship-adjacent quality at roughly Gemini-Flash-class output pricing, materially cheaper output than Claude Sonnet ($15) or GPT-5.5 ($30). There is also a **Grok 4.1 Fast** budget tier (~$0.20/$0.50, up to 2M context).
- **Why it matters:** A transparent multi-model product that *omits* a major provider users will ask for (and one that is unusually cheap on output) undercuts the "every major model in one place" promise (PRD 00 §1). Grok is a natural candidate for the "Smart" tier or a cheap reasoning default.
- **Suggestion:** **MVP** — add Grok to the registry (free via OpenRouter/Gateway breadth layer; no direct integration needed at launch). Reassess direct integration P1.
- **Caveat [Recall]:** evaluate data-handling/brand-safety posture against the privacy-first positioning before making it a *default* route, same bar applied to DeepSeek in PRD §5.3.
- Sources: https://www.aipricing.guru/xai-pricing/ , https://pricepertoken.com/pricing-page/model/x-ai-grok-4.3 , https://openrouter.ai/x-ai/grok-4.3

### 2.2 Gateway-native web search makes P1 grounding nearly free to build **[Verified]**
The PRD (FR-27) frames web search as a build-it-yourself choice between "provider built-in" (A) and "Perplexity Sonar" (B). That framing is now out of date: **Vercel AI Gateway (the architecture's MVP default gateway) ships built-in web search as a tool that works with *any* model**, via `gateway.tools.perplexitySearch()` or `gateway.tools.parallelSearch()` (Perplexity or Parallel.ai backends), **plus** passthrough to provider-native tools (Anthropic `webSearch`, OpenAI `webSearch`, Google `googleSearch`/enterprise grounding). Perplexity/Parallel search are billed at **$5 per 1,000 requests**; results return as tool results you can render with citations.
- **Why it matters:** This collapses FR-27's A-vs-B tradeoff. You can get Perplexity-quality grounding **with the user's chosen chat model** (the multi-model wedge) without locking to Sonar as a provider — the exact thing FR-27 says you can't have. It also means web search is far cheaper to ship than the PRD implies, weakening the rationale for deferring it to P1.
- **Suggestion:** **Re-evaluate pulling a minimal grounded mode into MVP** (or early P1) given near-zero integration cost. At minimum, rewrite FR-27 to make gateway-tool web search the default pattern, not provider-native-per-model.
- **Note [Verified]:** Google also offers a **zero-data-retention "Enterprise Web Grounding"** variant — relevant to the privacy-first positioning (PR-1).
- Source: https://vercel.com/docs/ai-gateway/web-search (last updated 2026-05-11)

### 2.3 Gateway-level guardrails (Portkey) can satisfy several P0 safety requirements **[Verified]**
PRD §6.1 specifies input/output moderation and prompt-injection-aware architecture as P0, but treats them as bespoke app-layer work. In 2026, **Portkey ships PII redaction, jailbreak detection, guardrails, and audit trails *at the gateway layer***; **LiteLLM** has built-in guardrails/cost-tracking/fallbacks; OpenRouter and Vercel Gateway provide moderation hooks. Choosing the gateway with these features can satisfy SR-1/SR-2 with far less custom code.
- **Why it matters:** The PRD's gateway choice (PRD 04 §5: Vercel Gateway vs OpenRouter vs LiteLLM) is currently framed mostly around routing/fallback/cost. **Built-in safety/guardrails should be an explicit evaluation criterion** in that decision, because it directly de-risks the P0 safety requirements.
- **Suggestion:** **MVP** — add "gateway-native guardrails/moderation/PII-redaction" to the gateway selection criteria; if the chosen gateway lacks them, budget the app-layer moderation work explicitly.
- Sources: https://www.pkgpulse.com/guides/portkey-vs-litellm-vs-openrouter-llm-gateway-2026 , https://dev.to/varshithvhegde/top-5-llm-gateways-in-2026-a-deep-dive-comparison-for-production-teams-34d2

### 2.4 The GPT-5 "Auto router" backlash is direct market validation for the transparency wedge **[Verified]**
OpenAI's GPT-5 launch (Aug 2025) replaced the picker with a real-time **Auto router** that silently chooses between fast/thinking models; it drew sustained backlash for *inconsistent quality* and *silently routing to a weaker model than users expected* — the very "silent downgrade" failure mode PRD 00 §1 calls out for Perplexity. The router trains on user signals (model switches, preference rates, measured correctness).
- **Why it matters:** This is strong external validation that **per-turn attribution + "never silently downgrade" (FR-11, PRD 00 §7) is a real, felt differentiator**, not a theoretical one. It also implies a concrete UX rule: when Auto routes *down* (to a cheaper model), say so visibly — don't just badge the model, surface that a routing decision happened and let power users override.
- **Suggestion:** **MVP** — make the Auto routing decision itself a first-class, visible, overridable surface (not just the resulting model badge). Consider logging user overrides as the seed signal for a future learned router (PRD §9 Q2).
- Sources: https://www.latent.space/p/gpt5-router , https://techcrunch.com/2025/08/12/chatgpts-model-picker-is-back-and-its-complicated/ , https://openai.com/index/introducing-gpt-5/

### 2.5 Multimodal / indirect prompt injection is now a top, named threat — affects P1 vision design **[Verified]**
2026 security reporting: prompt injection is still **OWASP LLM01 (#1)**; the new/maturing vectors are **multimodal injections (malicious instructions hidden in images, QR codes, steganographic payloads)**, **multi-turn jailbreaks** (now the preferred attack on frontier models), and **MCP server / tool poisoning**. There is a documented real-world case of indirect injection via a landing page bypassing an AI content moderator.
- **Why it matters:** PRD §6.2/SR-2 correctly treats *retrieved/tool/RAG content* as untrusted, but does **not** mention that **uploaded images/PDFs (the P1 vision/PDF feature) are themselves an injection vector**. When vision ships, image/PDF content must be treated as untrusted instruction-bearing input.
- **Suggestion:** **P1 (with vision)** — add "treat image/PDF content as untrusted, injection-capable input" to SR-2; **MVP** — note multi-turn jailbreak as a moderation consideration (single-shot input/output moderation is weaker against it).
- Sources: https://tokenmix.ai/blog/llm-security-news-2026-attacks-defenses-updates , https://reddogsecurity.substack.com/p/llm-security-in-2026-a-complete-attack , https://christian-schneider.net/blog/prompt-injection-agentic-amplification/

### 2.6 Prompt-cache-aware message ordering is a cheap, high-ROI cost lever **[Verified]**
The docs mention prompt caching as a cost lever (FR-37, §8) but not the **structural prerequisite**: cache hit rate depends on **message ordering** — stable content first (system prompt → tool defs → static context → old history), variable content (current user message) last. Done well this cuts input-token cost 30–50% on long threads/agent loops at no quality cost. This is an *architecture* decision (how you assemble the prompt), not just a toggle.
- **Why it matters:** The PRD's context-management (§4.9) and caching (FR-37) sections don't specify the ordering discipline, so the cache benefit may be left on the table or broken by re-ordering injected custom-instructions/memory.
- **Suggestion:** **MVP** — bake cache-friendly ordering into the prompt-assembly contract (and note that summarize-on-threshold, FR-35, can *break* the cache by mutating the stable prefix — sequence it carefully).
- Source: https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models

### 2.7 "Compact at task boundaries, not at the threshold" — refine summarize-on-threshold **[Verified]**
Anthropic/OpenAI/Google now explicitly advise **context compaction before ~100% and ideally at task/turn boundaries**, warning that automatic threshold-triggered compaction "can happen when the model is least able to judge what future turns will need." FR-35's pure ~70–80% threshold trigger is the industry default but is the *weaker* form.
- **Why it matters:** A naive threshold-only summarizer can compact mid-task and drop the very context the next turn needs — a subtle quality bug.
- **Suggestion:** **MVP/P1** — keep the threshold as a safety net but prefer compaction at natural boundaries (e.g., after a completed sub-task / before a topic shift) where feasible.
- Source: https://www.implicator.ai/anthropic-openai-google-tell-developers-to-budget-ai-context-windows/

### 2.8 Anthropic now has native Structured Outputs (strict) — update the "OpenAI-only" framing **[Verified]**
The research doc (§9.1) credits *native* schema-constrained decoding to OpenAI and "JSON modes" to others. As of 2026, **Anthropic shipped native Structured Outputs (public beta)** on the Claude Developer Platform (strict JSON-schema / tool-spec conformance), and **Gemini 2.0+ uses native `responseJsonSchema`**. So all three primaries now offer *native strict* structured outputs, not just JSON-mode best-effort.
- **Why it matters:** FR-38/FR-39 can rely on native strict mode across all three primary providers (lower failure rates, ~<0.1% for OpenAI), rather than treating only OpenAI as "real" structured output. Validation (FR-39) is still mandatory regardless (CDA risk).
- **Suggestion:** **MVP** — update the registry capability `supports_structured_output` to distinguish *native-strict* vs *json-mode* per model; prefer native-strict where available.
- Sources: https://tessl.io/blog/anthropic-brings-structured-outputs-to-claude-developer-platform-making-api-responses-more-reliable/ , https://logic.inc/resources/structured-outputs-guide

### 2.9 GPT-5.5 long-context surcharge — a billing trap to surface in the cost meter **[Verified]**
GPT-5.5 prices prompts with **>272K input tokens at 2× input / 1.5× output for the entire session** (standard/batch/flex). This is analogous to Gemini's >200K tiered pricing (already in the docs) but the *step-change-per-session* behavior is a sharper trap.
- **Why it matters:** The cost meter (FR-36) and any cost estimate will be wrong for long-context GPT-5.5 turns unless it models the per-session surcharge, not just a flat $/token.
- **Suggestion:** **MVP** — registry `price_in`/`price_out` need to support **tiered/threshold pricing**, not a single scalar (also true for Gemini Pro and Sonnet/Opus 1M-context tiers). This is a concrete schema gap (see §4).
- Source: https://www.metacto.com/blogs/unlocking-the-true-cost-of-openai-api-a-deep-dive-into-usage-integration-and-maintenance ; OpenAI pricing: https://developers.openai.com/api/docs/pricing

### 2.10 Reasoning summaries are sometimes absent even when reasoning happened **[Verified]**
2026 docs confirm a subtlety beyond FR-17: even when a provider *can* return a reasoning summary, it may return **none for short/brief reasoning** (OpenAI notes ChatGPT "may not always show a Thinking trace because the reasoning was brief"), and Anthropic's adaptive thinking returns a *condensed summary* (not raw CoT) while still billing full thinking tokens.
- **Why it matters:** Reinforces FR-17/FR-18 but adds a UX rule: "reasoning happened but no summary was returned" is a valid, expected state — don't show an empty/broken panel or imply the model didn't think.
- **Suggestion:** **MVP** — FR-17 should explicitly handle the "reasoned but no visible summary" case as distinct from "doesn't reason."
- Sources: https://platform.claude.com/docs/en/build-with-claude/extended-thinking , https://help.openai.com/en/articles/11909943-gpt-5-in-chatgpt

---

## 3. Validated / challenged assumptions + current model snapshot

### 3.1 Current model + pricing snapshot (USD per 1M tokens, standard non-cached tier)

> All figures **[FAST-MOVING]** — verified 2026-05-27 against the sources cited; re-verify at build. Prices are standard tier, non-cached, non-batch. "Reasoning?" = has a thinking/reasoning mode. "MM?" = multimodal input (vision at minimum).

| Model | Provider | Context | In $ | Out $ | Reasoning? | MM? | Confidence / source |
|---|---|---|---|---|---|---|---|
| GPT-5.5 | OpenAI | 1M (~1.05M); >272K = 2×in/1.5×out | 5.00 | 30.00 | Yes (effort) | Yes | [Verified] developers.openai.com/api/docs/pricing |
| GPT-5.5 Pro | OpenAI | ~1.05M | 30.00 | 180.00 | Yes | Yes | [Verified] same |
| GPT-5.4 | OpenAI | ~1.05M (Recall) | 2.50 | 15.00 | Yes | Yes | [Verified] price; [Recall] ctx |
| GPT-5.4-Mini | OpenAI | ~1.05M (Recall) | 0.75 | 4.50 | Yes | Yes | [Verified] price |
| GPT-5.4-Nano | OpenAI | ~1.05M (Recall) | 0.20 | 1.25 | Yes | Yes | [Verified] price |
| Claude Opus 4.7 | Anthropic | 1M (new tokenizer) | 5.00 | 25.00 | Adaptive only | Yes | [Verified] platform.claude.com models overview |
| Claude Sonnet 4.6 | Anthropic | 1M | 3.00 | 15.00 | Adaptive + extended | Yes | [Verified] same |
| Claude Haiku 4.5 | Anthropic | 200K | 1.00 | 5.00 | Extended (no adaptive) | Yes | [Verified] same |
| Gemini 3.1 Pro (preview) | Google | 2M; ≤200K vs >200K tiers | 2.00 / 4.00 | 12.00 / 18.00 | Yes (thinking_level) | Yes (+video) | [Verified] ai.google.dev/gemini-api/docs/pricing |
| Gemini 3.5 Flash | Google | 1M | 1.50 | 9.00 | Yes | Yes (+video) | [Verified] same (new, 2026-05-19) |
| Gemini 3.1 Flash-Lite | Google | 1M (Recall) | 0.25 | 1.50 | Yes | Yes | [Verified] price |
| Gemini 2.5 Flash | Google | 1M | 0.30 | 2.50 | Yes | Yes (+video) | [Verified] same |
| Grok 4.3 | xAI | 1M | 1.25 | 2.50 | Yes | Yes (Recall) | [Verified] price/ctx; aipricing.guru, pricepertoken |
| Grok 4.1 Fast | xAI | 2M | 0.20 | 0.50 | Yes | Recall | [Verified] price/ctx |
| Mistral Large 3 | Mistral | 128K (262K per some) | 2.00 | 6.00 | No (Magistral=reasoning) | Yes (Pixtral) | [Verified] price; [Uncertain] ctx (128K vs 262K) |
| Mistral Medium 3 | Mistral | 128K | 0.40 | 2.00 | No | Yes | [Verified] price |
| Mistral Small 3.1 | Mistral | 128K | 0.20 | 0.60 | No | Yes | [Verified] price |
| DeepSeek V4-Flash | DeepSeek | 1M | 0.14 | 0.28 | Yes (think/non-think) | Limited (Recall) | [Verified] api-docs.deepseek.com/quick_start/pricing |
| DeepSeek V4-Pro | DeepSeek | 1M | 0.435* | 0.87* | Yes | Limited | [Verified] *75% promo to 2026-05-31; then 1/4 of original |
| Llama 4 Scout | Meta (open) | 10M | self-host / ~0.08–0.15 via providers | — | No (Recall) | Yes (native) | [Verified] ctx; [Recall] hosted price |
| Llama 4 Maverick | Meta (open) | 1M | self-host / provider | — | No | Yes (native) | [Verified] ctx |

**DeepSeek V4-Pro footnote:** the *75%-off* promo ($0.435/$0.87) **expires 2026-05-31 15:59 UTC**, then settles to "1/4 of original price." This is exactly the kind of promo window the docs warn about — do not hardcode. [Verified] https://api-docs.deepseek.com/quick_start/pricing

### 3.2 Validated (existing docs are correct)
- **No-hardcoding / data-driven registry mandate (research §0, PRD §5):** strongly validated. Multiple facts below already drifted in <6 weeks; the discipline is correct. **[Verified]**
- **OpenAI GPT-5.5 = $5/$30, 1M context; Pro = $30/$180** — correct. **[Verified]**
- **Claude Opus 4.7 $5/$25, Sonnet 4.6 $3/$15, Haiku 4.5 $1/$5; Opus/Sonnet 1M, Haiku 200K; max output Opus 128K, Sonnet/Haiku 64K; prompt caching ~90% off, batch 50% off** — all correct. **[Verified]**
- **Opus 4.7 omits thinking text by default (opt-in)** — correct (research §3.2). **[Verified]**
- **Gemini 3.1 Pro $2/$12 (≤200K), 2M context; Flash keeps free tier, Pro paid-only** — correct. **[Verified]**
- **DeepSeek V4 1M context** — correct. **[Verified]**
- **Llama 4 Scout 10M / Maverick 1M, natively multimodal MoE, open-weight** — correct. **[Verified]**
- **OpenRouter passthrough + ~5.5% credit fee** — correct, with a new wrinkle (see below). **[Verified]**
- **MCP de-facto standard, donated to Linux Foundation (Agentic AI Foundation), >10K servers** — correct; refined below. **[Verified]**
- **Reasoning tokens bill as output; Gemini thinking billed as output** — correct. **[Verified]**

### 3.3 Challenged / updated / now-stale facts (flag these in the docs)
1. **STALE — DeepSeek pricing.** Research §1.1 says "V4 ~$0.30/$0.50." Current first-party: **V4-Flash $0.14/$0.28**, **V4-Pro $0.435/$0.87 (promo)**. Also the model split changed: `deepseek-chat`/`deepseek-reasoner` are being deprecated in favor of **V4-Flash (think/non-think modes)** and **V4-Pro**. **[Verified]** https://api-docs.deepseek.com/quick_start/pricing
2. **STALE/IMPRECISE — OpenAI API lineup naming.** Research §1.1/§2.1/§12.1 lean on "GPT-5.x family incl. Instant/Thinking." **Instant/Thinking/Pro are ChatGPT *product* names, not API model IDs.** The actual API lineup today is **GPT-5.5, GPT-5.5-Pro, GPT-5.4, GPT-5.4-Mini, GPT-5.4-Nano, GPT-5.4-Pro**. Mixing product names and API IDs in the model registry will cause real confusion. **[Verified]** https://developers.openai.com/api/docs/pricing
3. **OUTDATED FRAMING — reasoning effort levels.** Research §1.1 lists OpenAI effort "none/low/medium/high/xhigh." Current first-party guidance describes **low/medium/high** as the documented `reasoning_effort` knob; "xhigh" is not confirmed in the sources I checked. Flag as **[Uncertain]** and verify against the live API rather than asserting five levels. https://sureprompts.com/blog/ai-reasoning-models-prompting-complete-guide-2026
4. **INCOMPLETE — Gemini Flash generations.** Research §1.1 names "3.5 Flash" without price; the current price is **$1.50/$9.00, 1M context (launched 2026-05-19)**, sitting *above* 2.5 Flash ($0.30/$2.50). Don't assume "Flash = cheap"; 3.5 Flash output is pricier than some rivals' flagships. **[Verified]** https://ai.google.dev/gemini-api/docs/pricing
5. **UNDER-CREDITED — Anthropic structured outputs.** Research §9.1 implies only OpenAI has native schema-constrained decoding. Anthropic now has **native Structured Outputs (beta)**; Gemini has `responseJsonSchema`. Update. **[Verified]** (see §2.8)
6. **NEW NUANCE — Opus 4.7 tokenizer inflates token counts.** Opus 4.7 uses a **new tokenizer that can use up to ~35% more tokens for the same text** vs prior Claude models. This directly affects **token counting (FR-34), context budgeting (FR-35), and cost estimates (FR-36)** — the same prompt costs more on Opus 4.7 than the raw $/token suggests, and per-provider tokenizers diverge by more than the "10–20%" the docs cite. **[Verified]** https://www.silicondata.com/use-cases/anthropic-claude-api-pricing-2026/
7. **NEW — OpenRouter BYOK terms.** Research §1.2 cites only the ~5.5% credit fee. OpenRouter now offers **1M free BYOK requests/month, then a 5% fee** on BYOK usage — directly relevant to the BYOK-at-launch decision (FR-6) and PRD 05 economics. **[Verified]** https://openrouter.ai/announcements/1-million-free-byok-requests-per-month
8. **MISSING PROVIDER — xAI/Grok** (see §2.1). **[Verified]**
9. **MCP refinement.** Research §10 is broadly right but dated: the **2026 spec moved to a stateless HTTP core, MCP Apps for server-rendered UIs, formalized servers as OAuth Resource Servers (RFC 8707 Resource Indicators), and added server-side agent loops + parallel tool calls** (Nov 2025); a release candidate locked 2026-05-21 with final spec slated for 2026-07-28. **[Verified]** https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

---

## 4. PRD 02 review — gaps, errors, outdated items, inconsistencies

> Overall: a strong, internally-consistent PRD. The no-hardcoding rule (§5) is exactly right and the FR set is mostly complete for a lean text-core MVP. The issues below are ordered roughly by impact.

### 4.1 Gaps (missing requirements)

- **G1 — Registry price schema can't represent tiered/threshold/promo pricing (§5.2, FR-36).** `price_in`/`price_out` are modeled as single per-M scalars. Reality (verified today): **Gemini Pro and Claude 1M tiers price differently above 200K**, **GPT-5.5 applies a 2×/1.5× surcharge above 272K for the whole session**, **cached input is ~10% of input**, **batch is 50% off**, and **promo windows expire** (DeepSeek 2026-05-31). A scalar price field makes the "transparency wedge" cost meter (the product's core promise) **wrong** for exactly the long-context, high-value turns. **Fix:** registry price must support threshold tiers + cached/batch multipliers + effective-date/promo handling, OR the meter must be explicitly labeled an estimate with a documented error mode. This is arguably a P0 correctness issue given transparency is the wedge.

- **G2 — Embeddings / token-counting source is unspecified for non-supported models.** FR-34 says "use per-model token counts from the registry," but several providers don't expose a synchronous tokenizer and **Opus 4.7's new tokenizer diverges ~35%**. The PRD needs a stated fallback (provider count-tokens endpoint vs heuristic estimate) and must acknowledge counts may be **estimates pre-send, exact post-response** (from usage metadata). Otherwise FR-34's acceptance ("uses the selected model's own limits") is not achievable pre-send for some models.

- **G3 — No requirement that web search / grounding leverage the chosen gateway's built-in tools.** FR-27 predates Vercel Gateway's `perplexitySearch`/`parallelSearch` tools (work with *any* model, ~$5/1K requests) — see §2.2. As written, FR-27 forces the false A-vs-B tradeoff. **Fix:** add a third, now-preferred pattern (gateway web-search tool with the user's selected model) and note Google's zero-data-retention enterprise grounding for the privacy posture.

- **G4 — Gateway-level safety/guardrails not in the gateway selection criteria.** §6.1 (P0 moderation + injection defense) and §5.3 / PRD 04 §5 (gateway choice) are disconnected. Portkey/LiteLLM offer **PII redaction, jailbreak detection, guardrails at the gateway** (§2.3). The gateway decision should weigh this; otherwise the team may pick a gateway and then rebuild guardrails by hand.

- **G5 — Uploaded images/PDFs as an injection vector is not covered (SR-2, FR-30/31).** SR-2 treats web/tool/RAG content as untrusted but not **vision/PDF input**, which is a maturing injection vector in 2026 (hidden text in images, QR/steganographic payloads — §2.5). When vision ships (P1), this is a real gap.

- **G6 — Prompt-assembly ordering / cache-hit discipline unspecified (FR-37, §4.9).** Caching is listed as a P1 cost lever but the **ordering prerequisite** (stable-first, variable-last) and the **interaction with summarization** (FR-35 can invalidate the cached prefix) aren't specified. Cheap, high-ROI, and easy to get wrong (§2.6).

- **G7 — Embeddings/registry has no `data_policy` field, but PR-1 depends on per-provider data handling.** PR-1 ("no training by default") and §5.3 say to "document per-provider data handling in the registry/config," but §5.2's metadata table has **no field for it** (e.g., `trains_on_data`, `data_residency`, `zdr_available`). Add it so the router can *enforce* "only default to no-train routes," and so the picker can surface it (a privacy-first transparency feature). Note Google's free tier explicitly "may use content to improve products" while paid tier does not — exactly the kind of per-route distinction this field must capture. **[Verified]** https://ai.google.dev/gemini-api/docs/pricing

### 4.2 Errors / outdated items

- **E1 — OpenAI model naming will mislead implementers (§5.3 implicitly, References).** Same issue as research §3.3 #2: the PRD inherits "GPT-5.x Instant/Thinking" framing from research. The registry must use **API IDs (gpt-5.5, gpt-5.4, gpt-5.4-mini, …)**, not ChatGPT product names. Add an explicit note that product names ≠ API IDs to avoid a registry-population bug. **[Verified]**

- **E2 — "Counts vary 10–20% across providers" understates it (FR-34).** With Opus 4.7's new tokenizer using up to ~35% more tokens, the spread is larger. Update the figure or say "varies materially (>30% in some cases)." **[Verified]**

- **E3 — Reasoning-effort levels inherited from research may be wrong (FR-16).** FR-16 references the per-provider mapping generically (good), but if the registry seeds OpenAI with "none/low/medium/high/xhigh" it may be inaccurate (§3.3 #3, [Uncertain]). FR-16 is correctly *abstracted*, so this is a seed-data caution, not a spec error — but worth flagging.

### 4.3 Inconsistencies

- **I1 — Memory priority conflict between PRD 02 and PRD 00.** PRD 02 §2 / FR-40 mark persistent memory **[P1]**; PRD 00 §5 "Deferred" lists **memory under P1**, but PRD 00's own MVP P0 list and FR-41 put **"temporary chat" in MVP**. These are reconcilable (principle/temporary-chat now, full memory P1) but the docs state it three slightly different ways. Recommend one canonical statement: *temporary-chat = P0; editable persistent memory = P1.*

- **I2 — Web search priority vs cost reality.** PRD 00 §5 and PRD 02 §4.7 firmly defer web search to P1 on the rationale that it's "heavier." Given §2.2 (gateway web search is ~1 line of code + $5/1K requests with the user's own model), the *deferral rationale* is now weak. Not necessarily wrong to defer (focus discipline), but the **stated reason is outdated** — update it to "scope discipline / citation-UX polish," not "integration cost."

- **I3 — Success metric "Grounded-answer citation rate >95%" is P1 but web search is deferred.** Fine, but note that with gateway tools the citation comes back as a tool result you must render — the 95% target is really a *UI rendering* guarantee (PRD 01) more than a model guarantee. Cross-reference accordingly.

### 4.4 Missing considerations (smaller, worth a line each)

- **M1 — Provider/model deprecation handling.** Anthropic is **retiring Claude Sonnet 4 / Opus 4 on 2026-06-15**; models get deprecated constantly. The registry has a `status` field (good) but the PRD has no requirement to **detect deprecation and migrate/fallback automatically** (or alert). Add a P1 requirement tied to FR-4 hydration. **[Verified]** https://platform.claude.com/docs/en/about-claude/models/overview
- **M2 — Per-image/PDF token accounting in the meter.** FR-32 says image tokens count toward the meter, but image token math is **provider-specific** (Claude ~1,334 tok per 1000×1000px; Gemini ~258 tok/page; OpenAI charges vision at 4–8× text rate). The registry/meter needs per-provider image-token formulas, not a flat assumption. **[Verified]** https://blog.roboflow.com/image-token-cost-vlm/
- **M3 — "Reasoned but no summary returned" UX state (FR-17).** Add it as a distinct, expected state (§2.10).
- **M4 — Multi-turn jailbreak resilience (SR-1).** Single-shot input/output moderation is weak against multi-turn jailbreaks (now the dominant attack). Note conversation-level moderation as a consideration. **[Verified]**
- **M5 — Auto-routing "downgrade" visibility (FR-8/FR-11).** Make the routing *decision* (esp. routing *down*) explicitly visible/overridable, per the GPT-5 backlash lesson (§2.4) — currently FR-11 surfaces the resulting model but not "Auto chose to route you cheaper."
- **M6 — Compaction at task boundaries (FR-35).** Prefer boundary-based compaction over pure threshold (§2.7).

---

## 5. Top 5 recommendations (prioritized, actionable)

1. **Fix the cost/price model before launch — it's the wedge (G1, E2, M2).** Make the registry price schema represent **tiered/threshold pricing, cached/batch multipliers, promo effective-dates, and per-provider image-token formulas**, and handle **divergent/large tokenizer spreads (Opus 4.7 +35%)**. The transparency-of-cost promise is only as credible as this. **[P0]**

2. **Add xAI/Grok to the model registry now, via the breadth/gateway layer (§2.1, G/#8).** It's a cheap-frontier model users will expect in a "every major model" product; zero integration cost via OpenRouter/Gateway. Gate it from being a *default* until its data posture is reviewed (privacy-first). **[P0 registry entry; P1 direct integration TBD]**

3. **Rewrite FR-27 around gateway-native web search and reconsider pulling a minimal grounded mode forward (§2.2, G3, I2).** The A-vs-B Sonar-vs-provider framing is obsolete; Vercel Gateway's `perplexitySearch`/`parallelSearch` give Perplexity-quality grounding **with the user's chosen model** at ~$5/1K requests. Update the deferral rationale to "scope/UX," not "cost." **[P1, possibly early-P1/MVP-lite]**

4. **Make gateway-native guardrails an explicit gateway-selection criterion, and add a `data_policy` field to the registry (G4, G7).** Wire SR-1/SR-2 and PR-1 to the actual gateway capabilities (Portkey/LiteLLM guardrails, PII redaction, jailbreak detection) and let the router *enforce* "no-train routes only" defaults with a user-visible data-handling badge — a privacy-first transparency feature, not just a backend constraint. **[P0 for the field + criterion; guardrail depth scales P1]**

5. **Tighten the reasoning + context-management contracts with the 2026 nuances (M3, M6, G6, E3, §2.6–2.10).** Specifically: (a) handle "reasoned but no summary" as a real state; (b) prefer task-boundary compaction with the threshold as a safety net; (c) bake cache-friendly prompt ordering into prompt assembly and sequence it so summarization doesn't break the cached prefix; (d) treat reasoning-effort level lists as live-API-verified seed data, not hardcoded. **[P0/MVP, low effort, high correctness payoff]**

---

## Appendix — Sources consulted (2026-05-27)

First-party / provider:
- OpenAI pricing & models: https://developers.openai.com/api/docs/pricing , https://developers.openai.com/api/docs/models/gpt-5.5 , https://openai.com/index/introducing-gpt-5/
- Anthropic models overview: https://platform.claude.com/docs/en/about-claude/models/overview , extended thinking: https://platform.claude.com/docs/en/build-with-claude/extended-thinking
- Google Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- DeepSeek pricing: https://api-docs.deepseek.com/quick_start/pricing
- Meta Llama 4: https://ai.meta.com/blog/llama-4-multimodal-intelligence/
- Vercel AI Gateway web search: https://vercel.com/docs/ai-gateway/web-search ; AI Gateway: https://vercel.com/docs/ai-gateway
- OpenRouter BYOK: https://openrouter.ai/announcements/1-million-free-byok-requests-per-month ; pricing: https://openrouter.ai/pricing
- MCP 2026 RC: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

Secondary / aggregators (used for cross-checks; lower confidence on exact figures):
- xAI/Grok: https://www.aipricing.guru/xai-pricing/ , https://pricepertoken.com/pricing-page/model/x-ai-grok-4.3 , https://openrouter.ai/x-ai/grok-4.3
- Mistral: https://tokenmix.ai/blog/mistral-api-pricing , https://mistral.ai/pricing
- Anthropic tokenizer/pricing: https://www.silicondata.com/use-cases/anthropic-claude-api-pricing-2026/
- GPT-5.5 long-context surcharge: https://www.metacto.com/blogs/unlocking-the-true-cost-of-openai-api-a-deep-dive-into-usage-integration-and-maintenance
- Structured outputs: https://tessl.io/blog/anthropic-brings-structured-outputs-to-claude-developer-platform-making-api-responses-more-reliable/ , https://logic.inc/resources/structured-outputs-guide
- Prompt caching/compaction: https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models , https://www.implicator.ai/anthropic-openai-google-tell-developers-to-budget-ai-context-windows/
- LLM security 2026: https://tokenmix.ai/blog/llm-security-news-2026-attacks-defenses-updates , https://reddogsecurity.substack.com/p/llm-security-in-2026-a-complete-attack
- Gateways comparison: https://www.pkgpulse.com/guides/portkey-vs-litellm-vs-openrouter-llm-gateway-2026
- GPT-5 router analysis: https://www.latent.space/p/gpt5-router , https://techcrunch.com/2025/08/12/chatgpts-model-picker-is-back-and-its-complicated/
- Vision/PDF token costs: https://blog.roboflow.com/image-token-cost-vlm/
- Model landscape May 2026: https://llm-stats.com/llm-updates , https://whatllm.org/blog/new-ai-models-may-2026
