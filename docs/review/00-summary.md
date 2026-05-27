# Fresh Research + PRD Review — Synthesis (2026-05-27)

**What this is.** The integrating document for a fresh, comprehensive 2025–2026 online-research pass over the web/mobile-web AI-chat product, plus a critical review of the existing PRD set (`docs/prd/00`–`05`). It consolidates five per-workstream reviews (`docs/review/01`–`05`) into the cross-cutting picture: the best *new* ideas, the most important *PRD gaps/corrections*, and — the part no single-domain review could see — the *cross-PRD conflicts and integration issues*.

**How it was produced.** Five parallel research workers (one per workstream, top-tier model + high reasoning) each (a) re-researched their domain online for 2026 developments and (b) critically reviewed the matching PRD. Each write-up then passed through an independent reviewer (top-tier, high reasoning) that **independently re-verified the load-bearing facts via the live web** before this synthesis. Reviewer verdicts and what was checked are in §6.

> Read order: this doc → the per-domain reviews (`01`–`05`) for the evidence, sources, and section-level detail. Every online claim in the per-domain docs carries a source URL and a confidence flag (`[Verified]`/`[Recall]`/`[Uncertain]`).

---

## 1. Headline takeaways

1. **The existing PRD set is strong and mostly holds up** — its prices/dates were largely correct on the day they were written, and its core strategic bets (multi-model picker + transparency in P0; lean text MVP; mobile-web-first; data-driven registry) are validated by fresh research. The value below is in **sharpening**, not rebuilding.
2. **The differentiation wedge has shifted within itself.** Of the three legs (multi-model · transparency · privacy), **transparency + cost-control are now the durable, freshest legs**; **multi-model is commoditizing** (T3 Chat at $8/mo, OpenRouter chat, aggregators); **privacy is a prosumer/EU play, not a mass-consumer one** (incumbents match no-train at team/enterprise tiers). Lead with *transparency*.
3. **The transparency wedge is under-specified in exactly the places that make it true** — and that gap is spread across three PRDs (see §3.1 / §4.1). This is the most important finding.
4. **Two genuine factual errors drove roadmap/rationale calls** and were corrected: the "incumbents retreated from branching" misread (PRD 01) and an ads-narrative inversion in an early draft of the competitive review (now corrected — the PRD was right).
5. **One unresolved cross-review conflict needs a lawyer**: the EU AI Act content-marking date (Aug 2 vs Dec 2 2026), now also clouded by a May-2026 provisional amendment (§4.2).
6. **A typed multi-part message model is the single cheapest high-leverage change** — one architectural decision that de-risks nearly every P1 trend at once (§3.2).

---

## 2. Top new ideas & opportunities (cross-cutting, ranked)

| # | Idea | Why it matters | Suggested phase | Source review |
|---|---|---|---|---|
| 1 | **Typed multi-part message model** (ordered list of text/reasoning/tool-call/tool-result/citation/ui-block parts) instead of one markdown string | De-risks tools, citations, interactive viz, and generative UI in one move; skipping it guarantees a P1 refactor | **P0 data model** (render only text/code/reasoning at P0) | 01 §3.2, 04 |
| 2 | **Make the transparency wedge concrete in the data model**: per-message *served-vs-requested* model + reason, tiered/cached/threshold cost accounting, reasoning-token cost | This *is* the core wedge; today it's left generic across PRDs 01/02/04 | **P0** | 01 §3.5/§3.14, 02 G1 |
| 3 | **Vercel AI Gateway native web search** (`perplexitySearch`/`parallelSearch`, any model, ~$5/1k req) + **gateway-level guardrails** (PII redaction, jailbreak detection) | Collapses the P1 "provider-built-in vs Sonar" build to near-zero and can satisfy P0 safety with less custom code | P1 search / P0 safety | 02 (G3) |
| 4 | **AI SDK v6 (GA 2025-12-22) as the build target** — resolves the v5/v6 open question; `Agent` primitive + stable MCP; **`generateObject`/`streamObject` deprecated** → build P0 structured outputs on `Output.object()` | Avoids shipping the MVP against a deprecated API | P0 decision | 03 §1.1/§3.2 |
| 5 | **Memory transparency ledger + "memory used here" indicator + cross-tool import** | Memory is now a *free baseline* everywhere (Claude, Mar 2026); the on-thesis differentiator is the transparency layer, and import is a cheap acquisition lever | P1 (spec the ledger now) | 01 §1.7/§3.7 |
| 6 | **Explicit copy-on-branch ("branch in new chat") pulled to P1** | Corrects a factual error; low-risk copy model; directly serves the dev/power-user beachhead | P1 (was P2) | 01 §1.5/§3.1 |
| 7 | **Pull a minimal metered-overage / credit primitive into P0** | The industry is repricing to usage/credits *now* (Copilot 6/1/26, Anthropic, Cursor); a flat "higher-limits" Pro re-creates the whale risk the PRD itself warns about | P0 (was P1) | 05 §3.1/§3.4 |
| 8 | **iOS keyboard: `visualViewport` JS as the *primary* composer path** (not `dvh`) | The PRD's #1 mobile risk; `dvh` does **not** shrink under the iOS keyboard, so a `dvh`-only sticky composer gets covered | P0 (corrects existing P0) | 02 §4.1 |
| 9 | **INP budget + `scheduler.yield()` / rAF token-batching to P0** | INP is the most-failed 2026 Web Vital and streaming chat is a worst case; currently P1 with no budget | P0 (was P1) | 02 §4.5 |
| 10 | **Add xAI/Grok to the model lineup** (Grok 4.3: ~$1.25/$2.50, 1M ctx) | "Every major model in one place" can't credibly omit it; flagship-adjacent at near-Flash output pricing | P0 registry | 02 |
| 11 | **MCP as the interop standard** for both tools and *UI* (MCP Apps, Jan 2026) + HITL "approve-with-edits" tool-call UX | The biggest new UX paradigm since artifacts; a privacy-first product especially needs a consent gate before tools read data | P1 (design now) | 01 §1.2/§1.4/§3.3 |
| 12 | **T3 Chat ($8/mo, multi-model) as the explicit price anchor-to-beat** | Closest competitor to our pitch at ~half our Pro price; absent from the PRD entirely | P0 strategy | 05 §1.4 |

---

## 3. Top PRD gaps & corrections (ranked)

### 3.1 The transparency wedge is fragmented and under-built (PRD 01 + 02 + 04) — **highest priority**
The product's core promise ("see the exact model + exact cost; never silently downgrade") is left generic in each PRD that owns a piece of it:
- **PRD 02 (G1):** the model-registry price schema is a **single scalar per direction** — it cannot represent **tiered/threshold pricing** (Gemini >200K; GPT-5.5 >272K 2×in/1.5×out), **cached-input** or **batch** multipliers, or **promos**. Result: the cost number — *the wedge itself* — is **wrong on exactly the high-value, long-context turns** where it matters most.
- **PRD 01 (§3.5):** the P1 reasoning-effort toggle has **no cost/latency tie-in**, despite reasoning tokens driving the 30–100× cost variance the product warns about.
- **PRD 01/02 (§3.14):** **"served-vs-requested model / silent-downgrade prevention" is unowned** between the two PRDs — yet it's the single highest-value transparency moment and it lives on the chat surface.
**Fix:** treat these three as one P0 workstream: a cost-accounting schema rich enough to be *true*, surfaced per message, including reason-for-substitution. (Detail: 02 §G1, 01 §3.5/§3.14.)

### 3.2 Message is modeled as a markdown string (PRD 01 §4.4/§5.4, PRD 04)
Blocks tools, structured citations, interactive visualizations, and generative UI — all P1. **Fix:** adopt a typed-parts model in the P0 data layer (render subset at P0). Cheapest high-leverage decision in the set. (01 §3.2.)

### 3.3 Mobile technical corrections (PRD 03) — three are load-bearing and verified
- **`dvh` keyboard fix is wrong for iOS** (§4.3, marked P0): iOS resizes only the *visual* viewport, so `dvh` doesn't shrink; `interactive-widget` is Android-only. Needs `visualViewport` JS as primary + `viewport-fit=cover` + safe-area insets. **[Verified by reviewer against MDN/WebKit/quirksmode]**
- **"~50 MB iOS storage cap" is outdated** (§4.6/4.9/5.3/6.2/6.4): Safari 17+ quota is disk-proportional (tens of GB); real constraint is 7-day eviction unless `navigator.storage.persist()`. **Invalidates Capacitor trigger #3.** **[Verified]**
- **Voice "prefer on-device for privacy" is false** (§4.7): Web Speech ships audio to Apple/Google — a red flag for a privacy-first product. **[Verified]**
- Plus: pull-to-refresh (§4.4) reloads and kills in-flight streams → use `overscroll-behavior: contain`.

### 3.4 Architecture gaps/risks (PRD 04)
- **Stop/abort semantics invert under resumable streams** (§5.1): every stop becomes a disconnect that must *not* cancel generation → orphaned-run handling is the **primary** path, needs a dedicated stop endpoint. **[Verified]**
- **Rate limiting is request-count-centric** (§5.6): real exposure is **token/$ spend** → token + cost-budget caps + circuit breakers (OWASP LLM10).
- **No cross-store GDPR deletion** (§5.7): delete must cascade to object storage, Redis, and **observability traces** (a PII store).
- **Auth presented as 3-way undecided** despite **PRD 00 already committing to Better Auth** (PRD 04 §5.5 vs PRD 00) — internal inconsistency; commit and drop Auth.js (now security-patch-only). **[Verified]**

### 3.5 Stale facts to fix in the PRDs (verified)
| Fact (PRD location) | Existing | Correct (2026-05-27) | Source review |
|---|---|---|---|
| Gemini consumer tier (PRD 05 §5.3) | "AI Plus ~$13.99" | **$7.99/mo** | 05 §2.4 [Verified] |
| DeepSeek pricing (PRD 02) | "~$0.30/$0.50" | **V4-Flash $0.14/$0.28; V4-Pro $0.435/$0.87 promo → $1.74/$3.48 after 5/31** | 04 [Verified] |
| OpenAI lineup naming (PRD 02) | mixes "Instant/Thinking" product names w/ API IDs | API IDs are **gpt-5.5 / 5.5-pro / 5.4 / 5.4-mini / 5.4-nano / 5.4-pro** | 04 [Verified] |
| Structured outputs (PRD 02) | credits only OpenAI | **Anthropic now has native Structured Outputs** | 04 [Verified] |
| Opus tokenizer (PRD 02) | spreads "10–20%" | Opus 4.7 new tokenizer ≈ **+12–35% tokens** | 04 [Verified] |
| US regulation (PRD 05 §7.5) | EU-only | **CA SB 243 + AB 2013 (live 1/1/26), CO SB 205 (enforce 6/30/26), Dec-2025 federal preemption EO** | 05 §1.6 [Verified] |
| Retention benchmarks (PRD 05 §6.1) | generic SaaS | **AI-native ≈ 40% GRR / 48% NRR** | 05 §1.2 [Verified] |

---

## 4. Cross-PRD conflicts & integration issues (orchestrator-level)

These span multiple PRDs/reviews and cannot be resolved inside any one workstream.

### 4.1 The transparency wedge has no single owner
See §3.1. PRD 01 owns the UX surface, PRD 02 the registry/accounting, PRD 04 the data model — and each leaves its piece generic, so the promise isn't end-to-end true. **Action:** assign one owner for the "transparency contract" cutting across 01/02/04, with the cost-accounting schema as the spine.

### 4.2 EU AI Act content-marking date — **unresolved conflict, needs legal sign-off**
- PRD 00 §10 / PRD 04 §5.7 / PRD 05: content-marking treated as **~Dec 2026** (a later, separate obligation; watermarking deferred).
- **Architecture review (03 §3.1)** contends Article 50(2) machine-readable content-marking **also binds Aug 2, 2026** (per Art. 113) — which would **pull watermarking into P0** for an EU launch.
- **Competitive review (05)** confirms the base Aug-2/Dec-2 split but flags a **May 7, 2026 Council/Parliament provisional agreement reshuffling deadlines** — so all dates are *provisional pending Official Journal publication*.
**Action:** legal confirmation before locking; this can change P0 EU scope. Do **not** downgrade the `[VERIFY]` flags yet.

### 4.3 The "typed message model" decision spans PRD 01 and PRD 04
A UX/rendering decision (01) that is really a data-model decision (04). **Action:** make it once, in the data layer, and reference it from both.

### 4.4 Free-tier default model — decision narrowed, not "answered"
The **DeepSeek-hosted API** is a poor privacy-first default (government/enterprise bans + Italy consumer block), but Western-hosted DeepSeek open weights remain a P2+ option, and Perplexity itself routes DeepSeek R1 on US/EU infra. **Action:** PRD 02/05 should pick a non-DeepSeek-hosted default (Gemini Flash / GPT-mini / Claude Haiku / Mistral-EU) and keep open weights as a separate P2+ line.

### 4.5 Pricing model: flat Pro (PRD 05 §5.1) vs hard-metering preached in §5.2
Internal inconsistency, now sharpened by the 2026 credit-economy pivot. **Action:** define Pro's "higher limits" as explicit metered caps with transparent credit overage; pull a minimal credit primitive to P0. The P0 cost meter is already the spine for this.

---

## 5. What still holds (don't churn these)
- Multi-model picker + per-message transparency in **P0** — strongly validated; the best single decision in the set.
- Lean text-core MVP; vision/tools/web-search at P1.
- Mobile-web-first; responsive web + PWA now, Capacitor later (React Native rejected).
- Data-driven registry / no hardcoded model IDs/prices — *vindicated*: multiple "facts" drifted within 6 weeks.
- BYOK at P0; KMS-encrypted keys.
- Accessibility as a differentiation lever (now well-documented best practice → table-stakes-expected).
- "Perplexity retreated from ads" rationale for deferring ads — **correct** (Perplexity dropped ads Feb 2026 for trust; only ChatGPT is expanding ads).

---

## 6. Review provenance & confidence

| Workstream (review file) | Worker | Reviewer verdict | Independently re-verified by reviewer |
|---|---|---|---|
| Features/UX (`01`) | ✅ | **pass** (+3 minor fixes applied) | ChatGPT branching Sep 2025 vs Mar-2026 edit restriction; Claude free memory; interactive-viz rollouts; MCP Apps |
| Mobile (`02`) | ✅ | **pass** (no corrections) | iOS `dvh`/visualViewport; 50 MB→disk-proportional quota; Web Speech audio off-device; pull-to-refresh; INP |
| Architecture (`03`) | ✅ | **pass** (+2 sourcing fixes applied) | AI SDK v6 GA + deprecations; Better Auth/Auth.js; Next.js 16; Fluid Compute limits; EU AI Act Art. 50; stop/abort inversion |
| AI capabilities (`04`) | ✅ | **pass** (+2 numeric fixes applied) | Grok/DeepSeek/OpenAI/Gemini/Anthropic prices + context windows; Gateway native search; OpenRouter BYOK; Anthropic structured outputs |
| Competitive (`05`) | ✅ | **revise → corrected** | Gemini $7.99; T3 Chat $8; Copilot/Anthropic/Cursor repricing; **Perplexity-ads inversion (fixed)**; DeepSeek-ban scope (right-sized); US state laws; EU dates |

**Confidence.** High on facts a reviewer independently re-verified against first-party/authoritative sources (the tables above and in each per-domain doc). Fast-moving specifics (exact tier gating, in-flight regulation dates) stay `[Uncertain]`/`[VERIFY]` — re-confirm against first-party docs before PRD lock, consistent with the existing docs' own discipline. The one item explicitly **not** settled here is the EU AI Act content-marking date (§4.2): legal sign-off required.

---

## 7. Recommended next actions
1. **Decide the transparency-contract ownership** across PRD 01/02/04 and design the **cost-accounting schema** (tiered/cached/threshold/promo) — the wedge depends on it (§3.1, §4.1).
2. **Adopt the typed multi-part message model** in the P0 data layer (§3.2, §4.3).
3. **Apply the verified corrections** to the PRDs: branching narrative (01), mobile `dvh`/storage/voice (03), stop-abort/rate-limit/GDPR-deletion/auth (04), stale prices + US-law layer + retention benchmarks + T3 anchor (02/05) — see §3.3–3.5.
4. **Get legal sign-off on the EU AI Act content-marking date** before locking P0 EU scope (§4.2).
5. **Commit the resolved decisions**: AI SDK v6, Next.js 16, Better Auth (drop Auth.js), non-DeepSeek-hosted free default, P0 metered-overage primitive (§2 #4/#7, §4.4/§4.5).
