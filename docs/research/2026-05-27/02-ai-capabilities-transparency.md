# Research & Review — AI Capabilities, Model Layer & Transparency Contract

**Domain:** PRD 02 (AI Capabilities & Model Layer) + PRD 07 (Transparency Contract)
**Author:** AI-platform research worker
**Date:** 2026-05-27
**Method:** Fresh online research pass (live pricing/docs verified May 2026) + critical review of PRDs 02 & 07.

> All prices are $/1M tokens (USD) unless stated. Pricing/IDs are **point-in-time snapshots, May 2026** — they belong in the registry, not in code (PRD 02 §5). Where a primary provider doc and an aggregator disagreed, the provider doc is preferred and the disagreement is flagged.

---

## 1. Summary

- The PRD set is **unusually current and well-reasoned**. The 2026-05-27 review pass that produced these PRDs already absorbed most of what fresh research surfaces (DeepSeek repricing, Opus 4.7 tokenizer, Gemini tiered pricing, AI SDK v6, GPT-5.5 long-context surcharge). The cost-accounting schema (PRD 02 §4.1b / PRD 07 §4.1) is correct in shape and survives scrutiny. Findings below are mostly **refinements and one real schema gap**, not rewrites.
- **Verified live pricing (May 2026):** GPT-5.5 $5/$30 (1.05M ctx, >272K-token sessions → 2×/1.5× surcharge, cached $0.50); GPT-5.4 $2.50/$15; Claude Opus 4.7 $5/$25 and Sonnet 4.6 $3/$15 and Haiku 4.5 $1/$5 (all 1M ctx, **no long-context surcharge**); Gemini 3.1 Pro Preview $2/$12 → $4/$18 above 200K (tiered), Gemini 3.5 Flash $1.50/$9, 3.1 Flash-Lite $0.25/$1.50; Grok 4.3 $1.25/$2.50 (1M ctx), Grok 4.1 Fast $0.20/$0.50; DeepSeek V4-Pro $0.435/$0.870 (1M ctx, **promo reverts 2026-05-31**); Mistral Large 3 $2/$6 (EU residency); Llama 4 Maverick ~$0.27/$0.85.
- **Two distinct long-context pricing patterns must both be representable** and the schema needs a tweak: OpenAI uses a **whole-session multiplier above a token threshold** (cross 272K → *all* tokens reprice), while Gemini uses a **tiered/stepped rate above 200K**. The current `multipliers.threshold_tier` scalar cannot even fully model the OpenAI style — input reprices ×2 but output ×1.5, i.e. **two multipliers, not one scalar** — and does **not** express stepped per-tier base rates or *which* tokens reprice. This is the one substantive [error]/[gap] in the cost schema.
- **Reasoning-token billing** is universal-as-output and the PRDs handle it correctly, but research adds nuance the PRDs should capture: most providers (OpenAI, Anthropic, Gemini) **only return summarized or hidden reasoning** while billing the full hidden chain; **thinking tokens are never cache-eligible** (full price every request); DeepSeek is the outlier that exposes raw thinking tokens. The schema should carry `reasoning_tokens` (it does, good) plus a note that reasoning is **excluded from cache multipliers**.
- **Gateway landscape favors the PRD's lean: Vercel AI Gateway default + OpenRouter for breadth.** Verified: AI Gateway is **zero-markup**, now ships **team-wide ZDR + no-prompt-training controls** (Apr 6 2026, covers Anthropic/OpenAI/Google), and **gateway-native web search via Perplexity** that works with any model — exactly the PRD 02 §4.7 pattern (C). OpenRouter confirmed: **1M free BYOK requests/month then 5% fee**, opt-out-of-training routing, per-request/per-group ZDR enforcement. This directly de-risks PR-1, SR-4, FR-6, FR-27.
- **Privacy posture is now a badged tradeoff, not a hard gate.** Western API defaults (OpenAI, Anthropic, Google paid) are **no-train-by-default**; Anthropic dropped API retention to **7 days**. **xAI Grok trains on consumer data by default (opt-out required)** and stays gated from Auto pending review. **DeepSeek-hosted stores data in mainland China** and is banned/blocked in Italy, US agencies, South Korea, Australia, Taiwan, India — but the product now ships DeepSeek as the **cost-leading main provider / default** with that posture surfaced via the `data_policy` badge and Western no-train routes one click away (PRD 00 D11 / PRD 02 §5.3). So `default_route_eligible:false` now applies to **Grok only**; DeepSeek is `default_route_eligible:true`.
- **Structured outputs are now genuinely native across the big three** (OpenAI strict schemas, Gemini, and Anthropic's constrained-decoding `output_format` + `strict:true` tool use). The PRD 02 §5.2 claim is correct; one caveat is that **Anthropic's structured outputs were still behind a beta header** in the docs we read — registry should carry a `native-strict` vs `json-mode` vs `beta` distinction, slightly finer than the current binary.
- **Net assessment:** PRD 02 and 07 are **build-ready** with a handful of P0/P1 corrections — chiefly the threshold-vs-stepped pricing schema fix, a per-message-vs-session cost-scope field, and tightening a few illustrative facts that have already drifted (Anthropic structured-outputs beta status; Gemini Pro free tier removed Apr 1 2026; DeepSeek promo expiry date).

---

## 2. Model landscape & pricing (May 2026)

Prices = $/1M tokens. "Train default" = whether the **paid API** route trains on data by default. ZDR = zero-data-retention option available.

| Model (API ID) | Context | Input | Output | Cached in | Reasoning / thinking | Train default (API) | ZDR | Source |
|---|---|---|---|---|---|---|---|---|
| **OpenAI GPT-5.5** | 1.05M | $5 | $30 | $0.50 | `reasoning.effort` none→xhigh; reasoning billed as output, summary only | No (30-day abuse retention) | Enterprise ZDR | openai.com/api/pricing; developers.openai.com/api/docs/models/gpt-5.5 |
| **OpenAI GPT-5.5** (>272K-token session) | — | $10 (2×) | $45 (1.5×) | — | whole-session reprice once 272K crossed | No | — | openrouter.ai/announcements/gpt55-cost-analysis |
| **OpenAI GPT-5.5-pro** | 1.05M | $30 | $180 | — | high-reasoning flagship | No | Ent. | aipricing.guru/openai-pricing |
| **OpenAI GPT-5.4** | 1M | $2.50 | $15 | $0.25 | recommended workhorse | No | Ent. | devtk.ai/openai-api-pricing-guide-2026 |
| **OpenAI GPT-5.4-mini / nano** | 1M | mini ~$0.25 / nano lower | — | — | cheap default candidate | No | Ent. | aipricing.guru/openai-pricing |
| **Anthropic Claude Opus 4.7** | 1M | $5 | $25 | 90% off w/ cache | adaptive thinking, **thinking omitted by default (opt-in)**; new tokenizer ~+12–35% tokens; img to 3.75MP | **No, never trains API I/O** | 7-day default; ZDR for ent. | platform.claude.com/docs/.../pricing; finout.io/claude-opus-4.7-pricing |
| **Anthropic Claude Sonnet 4.6** | 1M | $3 | $15 | 90% off | adaptive thinking | No | 7-day | benchlm.ai/claude-api-pricing |
| **Anthropic Claude Haiku 4.5** | 1M | $1 | $5 | 90% off | fast tier; **selectable Western picker alternative** | No | 7-day | aipricing.guru/anthropic-pricing |
| **Google Gemini 3.1 Pro Preview** | 2M | $2 (≤200K) / **$4 (>200K)** | $12 / **$18 (>200K)** | $0.20 / $0.40 | `thinking_level` min→high; **Pro free tier removed Apr 1 2026** | No (paid/Workspace) | Ent./Workspace | ai.google.dev/gemini-api/docs/pricing; aipricing.guru/google-ai-pricing |
| **Google Gemini 3.5 Flash** | ~1M | $1.50 | $9 | $0.15 | flat pricing (no threshold); **selectable Western picker alternative** | No | Ent. | ai.google.dev/gemini-api/docs/pricing |
| **Google Gemini 3.1 Flash-Lite** | ~1M | $0.25 | $1.50 | — | flat; cheapest Google tier | No | Ent. | ai.google.dev/gemini-api/docs/pricing |
| **xAI Grok 4.3** | 1M | $1.25 | $2.50 | — | cheap frontier; tool-calling | **⚠ Consumer trains by default; API/ent. posture must be verified** | unclear | mem0.ai/blog/xai-grok-api-pricing; docs.x.ai |
| **xAI Grok 4.1 Fast** | 2M | $0.20 | $0.50 | $0.05 | huge context, budget | ⚠ as above | unclear | pricepertoken.com/.../xai-grok-4-fast |
| **DeepSeek V4-Pro** | 1M | $0.435 | $0.870 | — | exposes raw thinking tokens; **promo reverts 2026-05-31 → ~4× higher**; **chosen as our main provider / free-tier default (cost leader)** | Data processed/stored in mainland China; banned/blocked in several jurisdictions — **accepted, badged tradeoff for the default** | **Yes (badged tradeoff)** | api-docs.deepseek.com/quick_start/pricing; infoworld.com |
| **Mistral Large 3** | ~256K | $2 | $6 | — | **EU data residency by default (GDPR)** | No | EU | aipricing.guru/mistral-pricing; llmwise.ai/mistral-api-pricing |
| **Mistral Small 3.1** | ~128K | $0.20 | $0.60 | — | budget EU tier; **selectable Western picker alternative** | No | EU | devtk.ai/mistral-api-pricing-guide-2026 |
| **Meta Llama 4 Maverick** | 1M | ~$0.27 | ~$0.85 | — | open weights; price varies by host | host-dependent (open weights) | host-dependent | morphllm.com/llm-api; futureagi.substack.com |
| **Qwen 3 / 2.5 (open)** | up to 256K+ | ~$0.30 | ~$0.80 | — | open weights; cheap | host-dependent | host-dependent | aimagicx.com/local-ai-models-2026 |

**Reading notes / caveats:**
- **Tiered vs stepped vs whole-session reprice are three different math models.** Gemini Pro = stepped (different base rate per token band, threshold 200K). OpenAI GPT-5.5 = whole-session multiplier (cross 272K → *every* token in the request reprices at 2×/1.5×). Anthropic = flat to 1M (no surcharge — a competitive advantage to surface in the picker). The registry must distinguish these (see §4, finding T1).
- **Gemini 3.1 Pro context window**: official docs we fetched did not restate the window but aggregators report **2M**; the tiered threshold is **200K** (verified in docs). [verify-at-build].
- **Anthropic structured-outputs docs** still showed a **beta header (`structured-outputs-2025-11-13`) and older model names (Sonnet 4.5 / Opus 4.1)** — likely a stale docs cache; treat "native-strict on Opus 4.7/Sonnet 4.6" as [verify-at-build].
- **DeepSeek promo**: the 75% discount that yields $0.435/$0.870 is documented to **revert 2026-05-31 15:59 UTC** to ~4× higher — a textbook dated-promo the schema must model.

---

## 3. New ideas & developments (online research)

### Theme A — Long-context pricing has bifurcated into two incompatible math models
- **OpenAI GPT-5.5**: prompts >272K input tokens reprice the **whole session** at 2× input / 1.5× output (applies to standard, batch, flex). Crossing the threshold reprices *all* tokens, not just the overflow. (openrouter.ai/announcements/gpt55-cost-analysis; evolink.ai/gpt-5-5-api-pricing-guide-2026 — May 2026)
- **Gemini 3.1 Pro**: **stepped** — ≤200K at $2/$12, >200K at $4/$18, with cached-input also stepped ($0.20/$0.40). Flash/Flash-Lite are flat. (ai.google.dev/gemini-api/docs/pricing — accessed 2026-05-27)
- **Anthropic**: **flat to 1M, no surcharge** on Opus 4.7/Sonnet 4.6 — a genuine differentiator. (finout.io/claude-opus-4.7-pricing — 2026)
- **Implication for us:** PRD 02 FR-2b/§5.2 and PRD 07 §4.1 must represent **(a)** a threshold + whole-session multiplier (OpenAI), **(b)** stepped per-band base rates (Gemini), and **(c)** "no surcharge" as a first-class, surfaceable fact. The current single `threshold_tier` scalar is awkward even for (a) — OpenAI's ×2 input / ×1.5 output reprice needs two multipliers, not one — and cannot express (b) at all. See §4 finding T1.

### Theme B — Reasoning tokens: billed-as-output, mostly hidden, never cached
- Reasoning/thinking tokens are billed at the **output rate** across OpenAI, Anthropic, Gemini, DeepSeek. (tokenmix.ai/blog/thinking-tokens-billing-trap-2026 — 2026)
- **Visibility differs:** OpenAI returns *summaries* (`summary:auto`); Anthropic returns *condensed* thinking and **omits thinking by default on Opus 4.7**; Gemini hides raw chain but inflates output token counts; **DeepSeek (V4 family) is the only major model exposing raw thinking tokens** (which V4 variant — Pro vs Flash — to confirm at build; the §2 table row is V4-Pro). (help.apiyi.com/gemini-3-1-pro-thinking-tokens; tokenmix.ai — 2026)
- **Thinking tokens are not cache-eligible** — per-request stochastic, full price every time; observed 4–15× cost multipliers vs non-reasoning turns. (tokenmix.ai — 2026)
- **Effort knobs converged on named levels:** OpenAI `reasoning.effort` (none→xhigh), Gemini `thinking_level` (minimal/low/medium/high), Anthropic adaptive thinking with an effort param (old `budget_tokens` deprecated). (docs.requesty.ai/features/reasoning — 2026)
- **Implication for us:** PRD 02 FR-16/FR-17/FR-18 are correct. Add two concrete schema rules: **reasoning tokens are excluded from the `cached_input` multiplier**, and the registry's per-provider effort enum should be **named levels** (the PRDs already say "live-API-verified seed data" — good). The "reasoned-but-no-summary is a distinct state" rule (FR-17) is well-founded given Opus 4.7 omitting thinking by default.

### Theme C — Gateways: the PRD's Vercel-default + OpenRouter-breadth lean is validated
- **Vercel AI Gateway**: zero markup on tokens with BYOK; $5/mo free credit; **team-wide ZDR + no-prompt-training controls (Apr 6 2026)** auto-routing only to ZDR-compliant providers (Anthropic/OpenAI/Google+), failing closed if none available; **per-request ZDR free**, team-wide ZDR $0.10/1K requests. (vercel.com/changelog/zero-data-retention-no-prompt-training-on-ai-gateway; vercel.com/blog/zdr-on-ai-gateway — Apr 2026)
- **Gateway-native web search**: AI Gateway intercepts a Perplexity-backed search tool server-side, works with **any** model in one line — exactly PRD 02 §4.7 pattern (C). (vercel.com/docs/ai-gateway/capabilities; folding-sky.com — 2026)
- **OpenRouter**: **1M free BYOK requests/month then 5% fee**; opt-out-of-training routes only to non-training providers; per-request/per-group/global **ZDR enforcement**; normalized model catalog with pricing/context/policy metadata; but **5.5% credit-purchase fee, ~100–150ms added latency, no public SLA**. (openrouter.ai/announcements/1-million-free-byok-requests-per-month; openrouter.ai/docs/guides/privacy/logging — 2026)
- **Portkey** ($49/mo+) and **LiteLLM** (OSS self-host, quote-based enterprise) remain the production-routing / self-host options with richer guardrails/budgets. (portkey.ai/buyers-guide; braintrust.dev/articles/best-llm-gateways-2026 — 2026)
- **Implication for us:** Confirms PRD 02 §5.3 + SR-4 + FR-27(C). Two concrete wins: (1) the **no-prompt-training routing control** is now a platform feature we can *enforce* (PR-1) rather than per-provider negotiate; (2) gateway-native search makes FR-27 near-zero to wire, strengthening the "pull a minimal grounded mode to MVP-lite" note. Caveat to record: OpenRouter's **5.5% credit fee + latency + no SLA** argue for keeping it as *breadth/fallback*, not the primary route — which PRD 04's lean already reflects.

### Theme D — Structured outputs are now native-strict across the big three (+ a security caveat)
- **Anthropic** shipped constrained-decoding structured outputs: `output_config.format` (JSON) and `strict:true` tool use, compiling JSON schema into a grammar (model *cannot* emit violating tokens) — though docs still showed a **beta header**. (platform.claude.com/docs/en/build-with-claude/structured-outputs; towardsdatascience.com — 2026)
- **OpenAI** strict schemas and **Gemini** structured output are mature. **AI SDK v6** unifies on `Output.object()` / `streamText({output})`; **`generateObject`/`streamObject` deprecated** (GA tied to the 2025-12-22 v6 wave). (vercel.com/blog/ai-sdk-6; ai-sdk.dev/docs/migration-guides/migration-guide-6-0; github.com/vercel/ai/issues/10025 — 2026)
- **Security:** Constrained Decoding Attacks (CDA) — schema grammar can smuggle malicious intent even with benign surface prompts — remain real; PRD 02 FR-39 already cites this. Prompt injection is **still OWASP LLM01 #1 (Apr 2026)**; multi-turn jailbreaks now dominate; MCP server exploitation is a new surface. (arxiv.org/pdf/2503.24191; tokenmix.ai/blog/llm-security-news-2026 — 2026)
- **Implication for us:** PRD 02 §4.10/§5.2/§6.1 are current. Refine the registry's `supports_structured_output` from binary to a small enum: `native-strict | json-mode | beta` (Anthropic is `beta` today). Keep the AI SDK v6 `Output.object()` commitment.

### Theme E — Privacy posture: Western paid APIs no-train by default; Grok stays gated, DeepSeek is the accepted cost-leading default
- **OpenAI API**: not used for training by default, ~30-day abuse retention, Enterprise ZDR. **Anthropic API**: never trains I/O, **retention cut to 7 days (Sep 14 2025)**, ZDR for enterprise. **Google**: paid/Workspace not used for training. (ax-sentinel.com/blog/ai-data-retention-policies-compared; anarlog.so/anthropic-data-retention-policy — 2026)
- **xAI Grok**: **trains on public X posts + Grok conversations by default for non-EU users; opt-out required.** API/enterprise posture less clear and must be verified. (siliconrepublic.com/grok-ai-training; x.ai/legal/privacy-policy — 2026)
- **DeepSeek**: data processed/stored in **mainland China**; banned/blocked in **Italy (GDPR), US agencies, South Korea, Australia, Taiwan, India**; a Wiz-discovered open database leaked 1M+ records. (tomsguide.com/deepseek-ai-banned-italy; aitechtonic.com/deepseek-ban — 2026) **Product decision (post-research):** despite this posture, DeepSeek is adopted as the **cost-leading main provider / default** (token prices 30–100× below frontier make the metered free tier viable); the data-residency tradeoff is surfaced via the `data_policy` badge with Western no-train routes selectable in the picker, and BYOK available for full control (PRD 00 D11 / PRD 02 §5.3).
- **Implication for us:** The free-tier default is **DeepSeek** (cost leader; PRD 02 §5.3 / D11), with **Gemini 3.5 Flash, an OpenAI mini, Claude Haiku 4.5, or Mistral Small 3.1** — all no-train-by-default — kept as **selectable picker alternatives** for privacy-sensitive users (PR-1 badges each route's posture). **Grok must keep `default_route_eligible:false` until its *API* (not consumer) data posture is confirmed** — note the consumer default-train finding is about X posts, and the *API* posture is a separate, still-open question worth a dedicated registry note.

### Theme F — Provider-side moderation & guardrails moved toward the gateway/open tooling
- Open tooling matured: **LLM Guard** (Protect AI), **Llama Guard**, **WildGuard** (matches GPT-4-judge on jailbreak/refusal detection). Gateways now ship PII redaction + jailbreak detection + audit trails at the gateway layer. (appsecsanta.com/llm-guard; arxiv.org/pdf/2406.18495 — 2026)
- **Single-shot input/output moderation is weak vs multi-turn jailbreaks** (now dominant) — conversation-level moderation is the maturing requirement. (tokenmix.ai/blog/llm-security-news-2026 — 2026)
- **Implication for us:** PRD 02 SR-1/SR-4 already note the multi-turn weakness and gateway-native guardrails — current. If the chosen gateway lacks guardrails, **WildGuard/Llama Guard/LLM Guard** are concrete open fallbacks worth naming in the registry/PRD references.

---

## 4. PRD review findings

Tags: **[error]** factually wrong/stale · **[gap]** missing · **[inconsistency]** internal conflict · **[scope]** over/under-scoped · **[risk]** correct but risky.

### PRD 07 — Transparency Contract (cost schema is high-stakes)

- **T1 [error]/[gap] — §4.1 `cost_breakdown` cannot cleanly express the two real long-context pricing models.** The `multipliers.threshold_tier` scalar assumes "one base rate × a multiplier." That partially fits OpenAI's **whole-session reprice** (cross 272K → repricing on everything) — but even there a single scalar is insufficient, because input reprices ×2 while output reprices ×1.5 (two multipliers, not one) — and it does **not** cleanly express Gemini's **stepped per-band base rates** ($2/$12 ≤200K, $4/$18 >200K, with stepped cached rates too), nor does it record **which tokens repriced** or whether the surcharge was session-wide vs band-only. As written, a Gemini >200K turn computed via a single `threshold_tier` multiplier off the ≤200K base will be **wrong**. **Recommended action:** evolve the schema to carry either (i) explicit `applied_tier` with its own `price_in/price_out` resolved from the registry's tier table, plus a `tier_scope: "session" | "overage"` flag, or (ii) keep `threshold_tier` only for the session-multiplier (OpenAI) case and add a `stepped_pricing` representation for Gemini. Add a `cached_input` step value too (Gemini caches are tiered). This is the single most important correctness fix and it touches PRD 02 §5.2 `pricing` and FR-2b in lockstep.

- **T2 [gap] — §4 cost is per-message but long-context surcharge is per-*session/request*.** OpenAI's 272K reprice applies to the **whole request**, and prompt-cache economics span the thread. The canonical fields are per-assistant-message; nothing records **request-scope** vs **message-scope** cost attribution. **Recommended action:** add a field/note distinguishing per-message cost from request-scoped surcharge (e.g., `cost_scope` or a `notes` entry "session-repriced: 272K threshold crossed"), so the meter (PRD 02 FR-36) and the §8 golden tests can assert the right number.

- **T3 [gap] — reasoning tokens vs cache multiplier not specified.** §4.1 lists `reasoning_tokens` and a `cached_input` multiplier but never states that **reasoning tokens are NOT cache-eligible** (verified: thinking tokens are full-price every request). A naive implementation could apply the cache discount to reasoning tokens and under-bill. **Recommended action:** add a behavioral rule (§7) and a golden test: `cached_input` applies only to non-reasoning input/output; reasoning tokens are billed at output rate with no cache discount.

- **T4 [gap] — no `promo` effective-date handling in the shape.** §4.1 has a `promo` multiplier but no `effective_until`/date metadata, while PRD 02 FR-2b explicitly requires "dated promos." The DeepSeek promo reverting **2026-05-31** is a live example. **Recommended action:** the registry tier/promo entries (PRD 02 §5.2) must carry effective dates; PRD 07 §4.1 `notes`/`multipliers.promo` should record the applied promo + whether it was date-valid at turn time. Add a golden test for a turn before/after a promo expiry.

- **T5 [inconsistency] — §8 AC #5 "usage meter matches sum of message.cost_usd within tolerance" collides with session-scoped surcharge (T2).** If a 272K surcharge is request-scoped but cost is summed per-message, the tolerance must explicitly cover surcharge allocation. **Recommended action:** define how a request-scoped surcharge is allocated across the request's messages (or attributed to the triggering turn) so AC #5 is testable.

- **T6 [gap] — substitution reason enum (§5) lacks a "capacity_reroute"/"gateway_route" code**, yet PRD 02 FR-11b explicitly lists "capacity reroute" as a substitution trigger. **Recommended action:** add `capacity_reroute` (and optionally `gateway_route`) to the §5 enum so PRD 02's triggers map 1:1 to PRD 07's codes (they currently don't fully align).

- **T7 [scope/risk] — §6.4 public-share leak rule is good but cost is on the message row by default.** The contract correctly bars cost/tokens from public shares (AC #6). Worth flagging as a **risk** that the same `cost_breakdown` JSON is persisted on the message and could leak via an under-filtered share/export serializer. **Recommended action:** keep the explicit "embedded JSON contains no cost fields" test (already AC #6) and add a serializer-level allowlist note. (No change to intent, just hardening.)

### PRD 02 — AI Capabilities & Model Layer

- **A1 [error] — §5.2 "Anthropic ... now all offer native-strict structured outputs."** Verified-but-stale: Anthropic's structured outputs are real but were **behind a beta header** (`structured-outputs-2025-11-13`) in the docs we read, with docs still naming older models. Stating it as a settled "native-strict" peer of OpenAI/Gemini is slightly ahead of reality. **Recommended action:** make `supports_structured_output` a 3-value enum `native-strict | json-mode | beta` and mark Anthropic `beta` until GA confirmed at build. Low effort, removes an overclaim.

- **A2 [error/stale] — §5.1 illustrative OpenAI ID list and §5.3 "OpenAI mini" need a refresh.** The current ID family is **GPT-5.5 / GPT-5.5-pro / GPT-5.4 / GPT-5.4-mini / GPT-5.4-nano** (verified). The PRD's illustrative list omits `gpt-5.5-pro` and includes `gpt-5.4-pro` which we could not confirm exists. Since these are explicitly illustrative/[verify-at-build] this is minor, but the cited examples should match the live family to avoid seeding a wrong registry. **Recommended action:** update the illustrative IDs to the verified May-2026 family; keep the [verify-at-build] disclaimer.

- **A3 [gap] — §5.2 schema has no field for "no long-context surcharge" as a positive fact.** Anthropic's flat-to-1M pricing is a **marketing/transparency advantage** ("this model has no long-context penalty") and the picker can't surface it because the schema only models surcharges, not their absence. **Recommended action:** allow the `pricing` tier list to be explicitly empty/`flat:true` so the picker can show "flat pricing to 1M" as a positive differentiator (ties to the transparency wedge).

- **A4 [gap] — §5.2 `data_policy` should distinguish *consumer/default-train* from *API-no-train*, and carry an opt-out flag.** The Grok finding (consumer trains by default, API posture unclear) shows the registry needs to capture **route-level** nuance: a provider can train on its consumer surface while the API/enterprise route does not, and some routes are opt-out vs opt-in. PRD 02 PR-1 already hints "free tiers may train while paid does not" but the schema field is a flat `trains_on_data`. **Recommended action:** expand `data_policy` to `{trains_on_data, train_default (opt_in|opt_out|never), data_residency, zdr_available, retention_days}` so the router can enforce PR-1 precisely and the picker badge is accurate. (Anthropic `retention_days:7`, OpenAI `~30`, DeepSeek `residency:CN`.)

- **A5 [error/stale] — §4.7(C) gateway-native search backends.** PRD says "Perplexity / Parallel.ai backends, ~$5 per 1,000 requests." Verified that AI Gateway ships **Perplexity-backed** server-side search; the "Parallel.ai" backend and the exact "$5/1K" figure I could not confirm against Vercel docs in this pass. **Recommended action:** mark the backend list and per-1K price [verify-at-build]; the *capability* (any-model gateway search) is confirmed.

- **A6 [gap] — FR-34 tokenizer divergence: name the reconciliation source of truth.** FR-34 correctly says pre-send counts are estimates reconciled to response usage. With Opus 4.7's new tokenizer (+12–35%) verified, add that the **registry must store a per-model tokenizer id / count-tokens-endpoint reference**, not just a heuristic, because the divergence is now large enough to break budgeting and the summarize-on-threshold trigger (FR-35). **Recommended action:** add `tokenizer_ref` / `count_tokens_endpoint` to §5.2 metadata.

- **A7 [inconsistency] — FR-8/§5.3 now gate Grok only from Auto (DeepSeek is the cost-leading default); Grok's exclusion rationale conflates consumer-train with API posture.** Gating Grok is correct; the *stated reason* ("before data-policy review") should be sharpened: research shows the consumer default-train is confirmed but the **API/enterprise data posture is genuinely unknown** — that's the real open item, not a generic "review." **Recommended action:** reword §5.3 FR-2c Grok rationale to "API data posture unverified" and add it to Open Questions §9. DeepSeek's data-residency posture is, by contrast, a known-and-accepted badged tradeoff for the default (PRD 00 D11), not an Auto gate. (Substantive accuracy, not scope.)

- **A8 [scope] — FR-27 web search is [P1] but research shows it's near-zero to wire via the gateway.** The PRD already flags this ("a minimal grounded mode may be pulled to early P1 / MVP-lite"). Given the verified one-line gateway integration, this is a **legitimate scope-pull-forward candidate** for the roadmap worker — flag, don't decide here. **Recommended action:** none in PRD 02; ensure PRD 05 roadmap sees the "MVP-lite grounded mode" flag.

- **A9 [risk] — §6.1 SR-1 single-shot moderation vs multi-turn jailbreaks.** Correctly noted as a maturity consideration. Research confirms multi-turn jailbreaks are now **dominant** and prompt injection is **OWASP LLM01 #1 (Apr 2026)**. **Recommended action:** keep as-is but name concrete open tooling (WildGuard/Llama Guard/LLM Guard) in §10 references so the build has a fallback if the gateway lacks guardrails.

- **A10 [gap] — no explicit schema rule that reasoning tokens are cache-exempt** (mirror of T3 on the registry/computation side). **Recommended action:** FR-18 should state reasoning tokens are billed as output **and are not cache-eligible**; FR-37's cache-friendly-assembly section should note the reasoning carve-out.

### Cross-cutting

- **C1 [inconsistency] — substitution triggers (PRD 02 FR-11b) ⊅ substitution reason codes (PRD 07 §5).** FR-11b lists Auto-downgrade, fallback, deprecation/migration, **capacity reroute**; PRD 07 §5 has no `capacity_reroute`. (Same as T6.) Align both lists.
- **C2 [gap] — DeepSeek promo expiry (2026-05-31) is a live test fixture.** Both PRDs cite "dated promo that reverts" abstractly; this real date is the ideal golden-test case for T4. Worth adding to PRD 07 §8 AC #3 (extend "cached-input and threshold-tier" to include "promo-expiry").

---

## 5. Recommendations (prioritized)

**P0 (correctness — do before build locks the schema):**
1. **Fix the long-context pricing representation (T1/A3).** Support (a) whole-session multiplier (OpenAI), (b) stepped per-band base rates (Gemini), (c) flat/no-surcharge as a positive fact (Anthropic). Resolve `threshold_tier` ambiguity; add `tier_scope`. This is the highest-leverage fix.
2. **Specify reasoning-token cache exemption (T3/A10):** reasoning billed as output, never cache-discounted; add a golden test.
3. **Add request/session cost-scope handling (T2/T5):** define how a session-wide surcharge is attributed across messages so the meter reconciliation AC is testable.
4. **Add dated-promo effective dates to the registry + breakdown (T4/C2):** use the DeepSeek 2026-05-31 reversion as the golden fixture.
5. **Expand `data_policy` to route-level granularity (A4):** `train_default (opt_in|opt_out|never)`, `retention_days`, `data_residency`, `zdr_available` — enables true PR-1 enforcement and an accurate picker badge.
6. **Align substitution triggers ↔ reason codes (T6/C1):** add `capacity_reroute`/`gateway_route` to PRD 07 §5.

**P1 (accuracy/refinement):**
7. Make `supports_structured_output` a 3-value enum and mark **Anthropic `beta`** until GA (A1).
8. Refresh illustrative OpenAI ID family to verified May-2026 set; drop unconfirmed `gpt-5.4-pro` (A2).
9. Add `tokenizer_ref` / `count_tokens_endpoint` to registry given the Opus 4.7 +12–35% divergence (A6).
10. Mark §4.7(C) search backend list + "$5/1K" as [verify-at-build]; capability confirmed (A5).
11. Sharpen Grok gating rationale to "API data posture unverified" + add to Open Questions (A7).

**P2 (opportunistic):**
12. Flag gateway-native grounded search as an **MVP-lite pull-forward** candidate to the PRD 05 roadmap worker (A8).
13. Name concrete open moderation tooling (WildGuard/Llama Guard/LLM Guard) in §10 as a guardrail fallback (A9/F).
14. Surface "flat pricing to 1M" (Anthropic) and "no long-context penalty" as picker transparency facts (A3).

---

## 6. Open questions

1. **xAI Grok *API* (not consumer) data posture** — does the paid API train by default, and is there a no-train/ZDR option? The consumer X-post default-train is confirmed; the API route is the actual gating question. (A7)
2. **Anthropic structured-outputs GA** — still beta-headed in docs as of this pass; will it be GA (and on Opus 4.7/Sonnet 4.6) at our build date? (A1)
3. **Gemini 3.1 Pro context window** — aggregators say 2M; provider docs we fetched didn't restate it. Confirm at build. (§2 note)
4. **Free-tier default route** — among Gemini 3.5 Flash / OpenAI-mini / Claude Haiku 4.5 / Mistral Small 3.1, which specific *route/setting* guarantees no-train-by-default at the free/guest tier, and at what blended cost? (carries PRD 02 §9.9)
5. **OpenRouter as breadth layer economics** — given the 5.5% credit fee + ~100–150ms latency + no SLA, is BYOK-via-OpenRouter (1M free req/mo) cheap enough to be the breadth default, or do we direct-integrate Grok/Mistral sooner?
6. **Session-surcharge attribution** — product decision: attribute the OpenAI 272K surcharge to the triggering turn, or amortize across the request's messages? (T2/T5)
7. **DeepSeek open-weights (Western-hosted) line** — still a [P2+] option; what host gives no-train + acceptable latency if we ever offer it?

---

## 7. Sources

All accessed **2026-05-27** unless noted.

**OpenAI**
- https://openai.com/api/pricing/
- https://developers.openai.com/api/docs/models/gpt-5.5
- https://developers.openai.com/api/docs/pricing
- https://openrouter.ai/announcements/gpt55-cost-analysis (GPT-5.5 272K whole-session reprice)
- https://www.aipricing.guru/openai-pricing/
- https://devtk.ai/en/blog/openai-api-pricing-guide-2026/
- https://evolink.ai/blog/gpt-5-5-api-pricing-guide-2026

**Anthropic**
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://www.finout.io/blog/claude-opus-4.7-pricing-the-real-cost-story-behind-the-unchanged-price-tag (tokenizer +35%, thinking opt-in)
- https://benchlm.ai/blog/posts/claude-api-pricing
- https://www.aipricing.guru/anthropic-pricing/
- https://anarlog.so/blog/anthropic-data-retention-policy/ (7-day retention)

**Google Gemini**
- https://ai.google.dev/gemini-api/docs/pricing (tiered ≤200K/>200K, last updated 2026-05-19)
- https://www.aipricing.guru/google-ai-pricing/ (Pro free tier removed Apr 1 2026)
- https://help.apiyi.com/en/gemini-3-1-pro-thinking-tokens-output-high-explained-en.html

**xAI Grok**
- https://mem0.ai/blog/xai-grok-api-pricing
- https://docs.x.ai/developers/models
- https://pricepertoken.com/pricing-page/model/xai-grok-4-fast
- https://x.ai/legal/privacy-policy
- https://www.siliconrepublic.com/business/grok-ai-training-x-twitter-default-user-data-privacy-turn-off (consumer default-train)

**DeepSeek**
- https://api-docs.deepseek.com/quick_start/pricing
- https://www.infoworld.com/article/4176709/deepseeks-steep-v4-pro-price-cut-escalates-ai-pricing-war.html
- https://www.explainx.ai/blog/deepseek-v4-pro-permanent-api-pricing-discount (promo reverts 2026-05-31)
- https://www.tomsguide.com/computing/online-security/deepseek-ai-banned-in-italy-as-data-privacy-concerns-pile-up
- https://aitechtonic.com/deepseek-ai-banned-countries/

**Mistral / Llama / Qwen**
- https://www.aipricing.guru/mistral-pricing/
- https://llmwise.ai/mistral-api-pricing/ (EU residency)
- https://devtk.ai/en/blog/mistral-api-pricing-guide-2026/
- https://www.morphllm.com/llm-api (Llama 4 Maverick pricing)
- https://futureagi.substack.com/p/top-11-llm-api-providers-in-2026
- https://www.aimagicx.com/blog/local-ai-models-2026-qwen-mistral-llama-hardware-guide

**Gateways / aggregation**
- https://vercel.com/changelog/zero-data-retention-no-prompt-training-on-ai-gateway (Apr 6 2026)
- https://vercel.com/blog/zdr-on-ai-gateway
- https://vercel.com/docs/ai-gateway/capabilities
- https://folding-sky.com/blog/vercel-ai-gateway-hundreds-ai-models-zero-data-retention
- https://openrouter.ai/announcements/1-million-free-byok-requests-per-month
- https://openrouter.ai/docs/guides/privacy/logging
- https://openrouter.ai/docs/guides/features/zdr
- https://www.respan.ai/market-map/compare/openrouter-vs-vercel-ai-gateway
- https://www.braintrust.dev/articles/best-llm-gateways-2026
- https://portkey.ai/buyers-guide/ai-gateway-solutions

**Reasoning tokens / structured outputs / AI SDK v6**
- https://tokenmix.ai/blog/thinking-tokens-billing-trap-2026
- https://docs.requesty.ai/features/reasoning
- https://vercel.com/blog/ai-sdk-6
- https://ai-sdk.dev/docs/migration-guides/migration-guide-6-0
- https://github.com/vercel/ai/issues/10025 (generateObject/streamObject deprecation)
- https://ai-sdk.dev/docs/reference/ai-sdk-core/output

**Safety / moderation / security**
- https://tokenmix.ai/blog/llm-security-news-2026-attacks-defenses-updates (OWASP LLM01 #1; multi-turn jailbreaks)
- https://appsecsanta.com/llm-guard
- https://arxiv.org/pdf/2406.18495 (WildGuard)
- https://arxiv.org/abs/2312.06674 (Llama Guard)
- https://arxiv.org/pdf/2503.24191 (Constrained Decoding Attacks)
- https://ax-sentinel.com/blog/ai-data-retention-policies-compared

**Data-retention / ZDR**
- https://vercel.com/docs/ai-gateway/capabilities/zdr
- https://www.gosearch.ai/blog/announcing-zero-data-retention-agreements-anthropic-openai/
