# Competitive, Monetization, Metrics & NFRs — Fresh Research + PRD Review (2026-05-27)

**Scope.** Fresh online research (2025–2026) NOT already captured in `docs/research/05-competitive-monetization.md`, plus a critical review of `docs/prd/05-roadmap-monetization-metrics.md`. Focus areas: competitor pricing/tiers, monetization models, market size, differentiation viability, regulation (EU AI Act + US state laws), and consumer-AI metrics.

**Confidence flags.** `[Verified]` = confirmed against a vendor/primary page or a fetched source during this research · `[Recall]` = consistent with broadly reported industry knowledge but not pinned to a fetched primary source here · `[Uncertain]` = could not verify; do not quote without re-checking. Every fact carries a source URL where possible. Prices, model names, and regulatory dates move monthly — treat all dollar/date figures as needing re-verification at PRD-lock.

**Headline.** The existing research doc is unusually strong and was compiled the same day (2026-05-27), so most of its prices and the core EU AI Act dates check out. The real value of this review is in: (1) **material monetization-model shifts the docs under-weight** (industry-wide pivot to usage/credit billing; AI-native subscription retention is catastrophically worse than the docs assume); (2) **a whole regulatory layer the docs miss** (US state AI laws live as of Jan 1 2026 + the Dec 2025 Trump preemption EO); (3) **the free-tier-default-model decision is effectively foreclosed** (DeepSeek is banned across the US/EU/APAC for exactly the buyers we target); and (4) **two new direct competitors** (T3 Chat, and increasingly capable aggregators) that sit squarely on our wedge.

---

## 1. New ideas & opportunities (not in the existing docs)

### 1.1 The industry is pivoting from flat subscriptions to usage/credit billing — in 2026, not "someday"
The docs treat usage credits as a **P1 nice-to-have** ("optional prepaid credits for occasional heavy users"). In reality, credit/usage billing is becoming the **dominant** model for AI tools that get heavily used, and the pivot is happening *right now*:
- **GitHub Copilot** moves *all* plans to usage-based, token-metered "AI Credits" on **June 1, 2026** — explicitly because agentic workflows "consume far more compute." `[Verified]`
- **Anthropic** introduced (Feb 2026) a **$20/employee seat that covers Claude chat/Code/Cowork but bills all token consumption separately at API rates**. `[Verified]`
- **Cursor** moved its $20 Pro plan to credit-based API-rate billing (June 2025), with effective per-unit rates reportedly rising >20x through credit redenomination in early 2026. `[Verified]`
- Industry framing: "By mid-2026, the AI credit economy is now the dominant pricing model for AI tools that actually get used." `[Recall/Verified]`

**Why it matters.** Our positioning is "you see (and control) the cost." A **transparent, USD-denominated credit/metering layer is not a P1 add-on — it is the natural expression of our wedge** and arguably belongs in P0 alongside the transparency surface (the cost meter is already P0). Shipping a flat ~$15-20 Pro plan with "generous limits" while the whole market reprices toward metered consumption risks us inheriting exactly the "inference whale" subsidy the docs warn about. Recommend pulling a **lightweight usage-credit / hard-metered overage capability forward to P0**, even if the default UX is a simple subscription.
Sources: https://metronome.com/blog/2026-trends-from-cataloging-50-ai-pricing-models · https://windowsforum.com/threads/github-copilot-ai-credits-usage-based-billing-starts-june-1-2026.415470/ · https://vibecoding.clickfq.com/blog/ai-credit-economy

### 1.2 AI-native subscription retention is far worse than the docs' SaaS benchmarks — "AI tourist" churn
The docs use generic SaaS retention (D1/D7/D30 ≈ 25-30% / 15-18% / 5-8%) and "~21% stickiness." Fresh 2026 data specific to **AI-native** products is much grimmer:
- **AI-native gross revenue retention ~40%, net revenue retention ~48%** — vs B2B SaaS median ~82% NRR. `[Verified]`
- The **"AI tourist" effect** (sign up out of curiosity, churn fast) hits budget AI tools hardest; **~30% of annual subscriptions cancel in the first month**; **44% of cancellations occur in the first 90 days.** `[Verified]`
- Median AI-native GRR rose from ~27% (Jan 2025) to ~40% (Sep 2025) — stabilising, but still half of classic SaaS. `[Verified]`

**Why it matters.** Our financial model and activation strategy must assume **AI-native, not SaaS, retention**. The single highest-leverage countermeasure in the data: **early-success onboarding** — "7-day trial + Day-1 success checklist converted at 52.7%." This directly validates (and should strengthen) the PRD's P0 "onboarding empty state + activation/time-to-first-value" bets. Add a **30/60/90-day churn cohort** and a **first-week activation funnel** as day-one KPIs.
Sources: https://www.growthunhinged.com/p/free-to-paid-conversion-report · https://www.thrad.ai/content/arpu-benchmarks-for-ai-chatbot-apps · https://www.amraandelma.com/free-trial-conversion-statistics/

### 1.3 ARPU reality check + the Perplexity-ads counter-narrative
New, concrete 2026 ARPU bands for AI-chat apps: **ad-only free ≈ $0.40–$2; hybrid freemium ≈ $3–$15; subscription-led ≈ $30–$100+** (annual ARPU). Notably **Perplexity roughly doubled ARPU (~$3 → ~$6.50) in a year *primarily through enabling ads*, not subscriber growth.** `[Verified]`

**Why it matters.** Two things. (1) Our subscription-led plan implies an ARPU target near the **$30-100+ band** — only reachable with strong conversion + low churn, which §1.2 says is hard. (2) The docs (and PRD §2.2) lean on "Perplexity retreated from ads" to justify deferring ads. The **ARPU evidence shows the opposite** — ads were Perplexity's single biggest ARPU lever in 2026. The "ads are a fading lever" framing is **stale/contested** and should be softened (see §2 and §3).
Source: https://www.thrad.ai/content/arpu-benchmarks-for-ai-chatbot-apps

### 1.4 Two new direct competitors sit exactly on our wedge — T3 Chat and capable aggregators
- **T3 Chat**: multi-model (GPT/Claude/Gemini/others in one UI), **$8/mo Pro = 1,500 messages/mo**, with **per-model caps openly disclosed** (Claude capped at 100 msgs/mo "so we don't go broke"), and **buy-more credits ($8/100 Claude msgs)**. It is explicitly *multi-model + transparent-about-limits + cheap*, monetising via API-rate arbitrage. `[Verified]`
- **OpenRouter** now routes **315+ models**, OpenAI-compatible, **5.5% platform fee** on credit usage, and a **chat UI** on top of the API. `[Verified]`

**Why it matters.** The docs frame the multi-model field as Poe (no privacy story) + BYOK tools. **T3 Chat is the closest competitor to our exact pitch** (multi-model, transparent, cheap, message-metered) and undercuts our proposed ~$15-20 Pro at **$8/mo** — yet it is absent from the docs. Our defensible delta over T3 must be **privacy/no-train + accessibility/mobile-web polish + genuine cost transparency** (T3 leans on opaque-ish credit redenomination and has no privacy story). This sharpens, not invalidates, the wedge — but the PRD must name T3 as the price/feature anchor to beat.
Sources: https://skywork.ai/skypage/en/T3-Chat-Pricing-Is-the-$8-AI-Powerhouse-Too-Good-to-Be-True/1974387624371744768 · https://x.com/theo/status/1887000229922353524 · https://openrouter.ai/pricing

### 1.5 OpenRouter BYOK economics changed in our favour — first 1M BYOK requests/month free
BYOK on OpenRouter is **5% of equivalent OpenRouter cost, but waived for the first 1,000,000 BYOK requests/month.** `[Verified]` The docs cite a flat "5% of upstream cost."

**Why it matters.** For an early-stage product, BYOK routing through OpenRouter is **effectively free at our likely volumes** — strengthening the "BYOK at $0 markup" P0 plan and lowering its infra cost. Worth noting in the monetization model.
Source: https://openrouter.ai/announcements/1-million-free-byok-requests-per-month · https://openrouter.ai/docs/guides/overview/auth/byok

### 1.6 A whole missing regulatory layer: US state AI laws + the federal preemption fight
The docs cover only the EU AI Act. As of 2026 there is a **live US patchwork** the PRD ignores:
- **California SB 243 (Companion Chatbot Act)** — mandatory **"you're talking to an AI" disclosure**, crisis-handling protocols, minor protections — **effective Jan 1, 2026.** `[Verified]`
- **California AB 2013 (training-data transparency)** — developers must disclose training-dataset info — **effective Jan 1, 2026.** `[Verified]`
- **Colorado SB 205** (high-risk AI; consumer AI-interaction disclosure) — **enforcement postponed Feb 1 → June 30, 2026.** `[Verified]`
- **Federal preemption EO (Dec 11, 2025)** + a **DOJ "AI Litigation Task Force" (from Jan 10, 2026)** challenging state AI laws — but the EO **is not self-executing**, expressly **carves out child-safety laws**, and a 10-year state moratorium **failed in the Senate.** Net: the state patchwork is live and contested, not preempted. `[Verified]`

**Why it matters.** The PRD's compliance section is EU-only. A US launch — our primary market for power users/devs — **already triggers AI-interaction-disclosure obligations (CA, effective now)**, and AB 2013 touches our model-provider disclosures. The good news: the P0 "AI-interaction disclosure" we already plan **satisfies the core CA/CO requirement too**. But the PRD must (a) acknowledge US state law, (b) note child-safety/minor rules survive preemption, and (c) add a "are we serving minors / companion-style use?" gate.
Sources: https://www.orrick.com/en/Insights/2026/04/2026-State-Chatbot-Laws-Key-Provisions-and-Regulatory-Trends · https://www.kslaw.com/news-and-insights/new-state-ai-laws-are-effective-on-january-1-2026-but-a-new-executive-order-signals-disruption · https://www.gibsondunn.com/president-trump-latest-executive-order-on-ai-seeks-to-preempt-state-laws/

### 1.7 The "no legal confidentiality" privacy hook is real but narrower than the docs imply — and it's a marketing risk
Fresh detail: the ruling is **Judge Rakoff (SDNY), Feb 2026** — AI chat documents are **not attorney-client privileged** (a defendant's Claude prompts/outputs under subpoena). Separately, **Judge Stein (Jan 2026)** compelled OpenAI to produce a **20-million-ChatGPT-log sample** to copyright plaintiffs, **with no user notice or chance to object.** `[Verified]`

**Why it matters.** This is a **genuine, fresh privacy-differentiation hook** (incumbents can be forced to hand over your chats; our short-retention/no-train posture limits what exists to be subpoenaed). BUT: it is a **district-court opinion**, not binding federal precedent — the docs/PRD call it a "2026 US federal ruling," which **overstates it**. And it cuts both ways: we'd be subject to the same discovery. Marketing claim must be "we minimise what exists to be compelled (short retention, no-train, delete)," NOT "your chats are confidential/privileged." Flag the PRD's `[VERIFY]` note here as **needing legal precision**.
Sources: https://www.crowell.com/en/insights/client-alerts/federal-court-rules-some-ai-chats-are-not-protected-by-legal-privilege-what-it-means-for-you · https://natlawreview.com/article/openai-loses-privacy-gambit-20-million-chatgpt-logs-likely-headed-copyright

### 1.8 DeepSeek is largely unusable as our free-tier default — the PRD's open question is effectively answered
DeepSeek (proposed in the PRD as a candidate cheap free-tier default) is **banned/restricted across the US, Italy/EU, South Korea, Australia, Taiwan, India** for government use and increasingly enterprise; stores prompts on **servers in China**; flagged for **GDPR non-compliance** and data-exfiltration concerns. `[Verified]`

**Why it matters.** Routing privacy-first, EU-facing power users' free traffic through DeepSeek would **directly contradict our positioning and create regulatory liability**. The PRD lists "DeepSeek vs Gemini Flash" as an open question (§9.5) without flagging that DeepSeek is **effectively disqualified** for a privacy-first Western product. Practical default candidates: **Gemini 2.x/3.x Flash, GPT-5.x Instant/mini, Claude Haiku-class, or Mistral (EU-hosted)** — not DeepSeek (except perhaps self-hosted open weights, a P2+ option).
Sources: https://aitechtonic.com/deepseek-ai-banned-countries/ · https://introl.com/blog/deepseek-government-bans-spreading-worldwide-2026 · https://witness.ai/blog/deepseek-security-concerns/

### 1.9 Market is large and still steepening — but mobile is where it's growing
AI chatbot/assistant adoption keeps climbing in 2026: **~987M+ AI-chatbot users (≈ doubled since 2022)**; **76% YoY growth in gen-AI platform visits, ~319% surge in app downloads.** Mobile is the growth engine (ChatGPT alone ~557M mobile MAU by Aug 2025). `[Verified — directional]`

**Why it matters.** Validates the PRD's **mobile-web-first** bet hard. The growth is on phones, and incumbents under-invest in mobile-web (vs native apps) — a real opening. Worth elevating "mobile-web growth tailwind" from implicit to an explicit strategic rationale.
Sources: https://www.demandsage.com/chatbot-statistics/ · https://www.index.dev/blog/chatgpt-statistics · https://www.grandviewresearch.com/industry-analysis/chatbot-market

---

## 2. Validated / challenged assumptions

### 2.1 Current competitor pricing table (re-verified May 2026)

> Prices confirmed against 2026 secondary aggregators and (where noted) vendor pages this session. **Confidence flags per row.** Re-verify against vendor pricing pages before external quotes.

| Product | Free tier | Entry paid (~"Plus/Pro") | High / prosumer tier | Team / Enterprise | Usage / API | Confidence |
|---|---|---|---|---|---|---|
| **ChatGPT** | Yes — GPT-5.3 Instant, ~10 msgs/5h; **ads on Free + Go (US, expanding)** | **Go $8/mo**; **Plus $20/mo** | **Pro $100/mo** (5x; GPT-5.5/5.5 Pro) & **$200/mo** (20x, ~1M ctx, 250 Deep Research) | Business **$20/seat (annual)**, ~$25-30 monthly, 2-seat min; Enterprise custom | Per-token API | `[Verified]` |
| **Claude** | Yes (limited) | **Pro $20/mo** (~$17 annual) | **Max 5x $100/mo** / **Max 20x $200/mo** | **Team $25/seat**, **Team Premium $125/seat**; Enterprise custom | Per-token API (Sonnet 4.6 ~$3/$15 per 1M) | `[Verified]` |
| **Gemini (Google AI)** | Yes | **AI Plus $7.99/mo**; **AI Pro $19.99/mo** | **AI Ultra $99.99/mo** (5x, 20TB, YT Premium) & **$200/mo** (20x) — *Ultra top tier cut from $250 → $200* | Workspace/Enterprise | Vertex/Gemini API | `[Verified]` |
| **Perplexity** | Yes (throttled) | **Pro $20/mo** (~$16.67 annual) | **Max $200/mo**; Education Pro $10 | **Enterprise Pro $40/seat**; **Enterprise Max $325/seat** | Sonar API | `[Verified]` |
| **Copilot** | Limited | **Pro $20/seat** (needs M365 Personal $7 / Family $10; some regions now bundle Copilot into base M365) | — | **Business ~$18→$21/seat**; **Enterprise (M365 Copilot) $30/seat** | Azure OpenAI API | `[Verified]` |
| **Mistral Le Chat** | Yes — **~25 msgs/day**, Medium/Small models, no No-Telemetry on free | **Pro $14.99/mo** | — | Team (custom); Enterprise | Per-token API (separate) | `[Verified]` |
| **DeepSeek** | **Yes, no paywall** (web/app) | — | — | — | **V4 Flash ~$0.14/$0.28 per 1M (cache hit ~$0.0028, ~98% off); V4 Pro promo ~$0.435/$0.87 → official 1/4-price after May 31 2026**; 5M free tokens/new acct | `[Verified]` |
| **Poe** | Yes — free cap **≤300 points held** (no rollover) | **$19.99/mo** (1M points; ~$16.67 annual) | higher point tiers | **Teams $249.99/mo** | Dev API (points) | `[Verified]` |
| **T3 Chat** *(NEW)* | trial | **$8/mo Pro = 1,500 msgs/mo** (Claude capped 100/mo; +$8/100 Claude credits) | — | — | API-rate arbitrage | `[Verified]` |
| **OpenRouter (BYOK/agg)** | free models (rate-limited) | n/a | n/a | n/a | **5.5% platform fee** on credit usage; **BYOK 5% of equiv cost, FIRST 1M BYOK req/mo FREE**; "no markup on provider pricing" | `[Verified]` |
| **TypingMind (BYOK)** | n/a | **~$79 one-time** | n/a | Team licenses | Pay providers directly | `[Recall]` |
| **Our product (proposed)** | metered, cheap **non-DeepSeek** default | **Pro ~$15–20/mo** *(reconsider given T3 @ $8 + credit-pivot)* | usage credits *(consider P0)* | P2 | **BYOK $0 markup** + transparent USD credits | n/a |

**Net on pricing:** the existing research/PRD pricing tables are **substantially accurate as of today** (good — they were compiled the same day). Minor refinements: ChatGPT Business annual is **$20/seat** (docs say "~$25"); Claude **Team Premium $125/seat** is a tier the docs omit; Gemini AI Plus is **$7.99** (docs say "~$13.99" — **stale/incorrect**, see §2.4); Gemini Ultra top tier **cut $250→$200**. The **bigger gap is a missing competitor (T3 Chat)**, not wrong numbers.

### 2.2 Validated assumptions (research/PRD got these right)
- **~$20/mo is the consumer anchor; $100/$200 prosumer tiers are usage multipliers, not better models.** Confirmed across ChatGPT/Claude/Gemini/Perplexity. `[Verified]`
- **"Inference whale" risk is real and worsening.** OpenAI reportedly spends ~$1.35 per $1 earned; GitHub Copilot was losing >$20/user/mo at a $10 plan; a Cursor team burned a $7,000 annual plan in one day. The docs' "$35k whale vs $200/mo" anecdote is consistent with this pattern. `[Verified]` (treat the exact $35k figure as `[Recall]`).
- **Token price spread of ~30-100x across models** — confirmed: DeepSeek V4 Flash ~$0.14/$0.28 per 1M vs frontier Claude Sonnet ~$3/$15 (≈20-50x) and Opus-class higher; routing is a genuine margin lever. `[Verified]`
- **Perplexity's silent-downgrade trust failure is real and ongoing.** Nov 2025 silent model substitution (CEO admitted a "bug" but said downgrading was "by design"); **May 2026** fresh complaints of Pro limits cut ~99% without notice. This **strengthens** the transparency wedge. `[Verified]`
- **Incumbents train on consumer chats by default; Claude defaulted users into 5-yr retention (opt-out by Oct 8 2025).** Confirmed. **Enterprise/Team tiers do NOT train by default** (OpenAI + Anthropic) — so the no-train guarantee is **table stakes at the team tier, a differentiator only at the consumer tier.** `[Verified]`
- **EU AI Act Article 50 transparency applies from Aug 2, 2026; AI-content marking grace period → Dec 2, 2026.** Confirmed against artificialintelligenceact.eu and EC guidance. `[Verified]`
- **ChatGPT introduced ads on Free + Go (US, Feb 9 2026; ~1% → ~5% of mobile users; expanding to UK/MX/BR/JP/KR from ~May 7 2026).** Confirmed — and *more aggressive* than the docs suggest. `[Verified]`

### 2.3 Challenged / updated assumptions
- **"Perplexity has largely abandoned ads / ads are a fading lever."** **Challenged.** ARPU data shows ads were Perplexity's biggest ARPU driver in 2026 (~$3→$6.50). ChatGPT is *expanding* ads. Ads are **rising**, not fading, across the market. Keep ads deferred for *trust/brand* reasons (a legit choice) but **stop justifying it with "the market is retreating from ads."** `[Verified]`
- **Generic SaaS retention benchmarks.** **Updated** — AI-native retention is roughly half (40% GRR / 48% NRR). Use AI-native numbers (§1.2). `[Verified]`
- **Usage credits as a P1 afterthought.** **Challenged** — the market is pivoting to credits *now* (§1.1). `[Verified]`
- **"DeepSeek vs Gemini Flash" as a balanced open question for the free default.** **Challenged** — DeepSeek is effectively disqualified for our positioning/markets (§1.8). `[Verified]`

### 2.4 Stale / incorrect facts to fix in the existing docs
1. **Gemini "AI Plus ~$13.99"** (research §2.1 table; PRD §5.3 table) — **STALE/WRONG. Google AI Plus is $7.99/mo** as of May 2026. `[Verified]` https://one.google.com/about/google-ai-plans/
2. **"Perplexity largely abandoned advertising / ads a fading lever"** (research §1.4, §2.2; PRD §2.2) — **contradicted by 2026 ARPU + ChatGPT-ads-expansion evidence.** `[Verified]`
3. **"2026 US *federal ruling*: AI conversations carry no legal confidentiality"** (research §6.3; PRD §7.3) — **imprecise.** It's an **SDNY district-court opinion (Rakoff, Feb 2026)** on attorney-client privilege + a discovery order (Stein, Jan 2026) — **not binding federal precedent.** Do not market chats as "confidential/privileged"; frame as "minimise what can be compelled." `[Verified]`
4. **ChatGPT Business "~$25/seat"** (research §1.10 / PRD §5.3) — **annual is $20/seat**; $25-30 is the monthly-billing rate. Minor. `[Verified]`
5. **Claude Team** — docs say "min 5 seats; Enterprise ~$20+/seat" but **omit Team Premium ($125/seat)** and the **per-seat + separate-API enterprise model** Anthropic shifted to in early 2026. Add it. `[Verified]`
6. **OpenRouter BYOK "5% of upstream cost"** — incomplete: **first 1M BYOK requests/month are free** (and the *platform* fee on non-BYOK credit usage is now **5.5%**). `[Verified]`

### 2.5 Does the differentiation wedge still hold in mid-2026? (critical assessment)
**Verdict: the wedge holds, but it is narrower and more contested than the docs portray, and one leg (privacy) is weakening as a consumer differentiator.**

- **Multi-model choice — STILL OPEN at the incumbents, but aggregators are crowding it.** ChatGPT/Claude/Gemini remain single-vendor (ChatGPT's "model picker" only switches *OpenAI* models / an auto-router). So the *incumbents* haven't closed it. BUT **Poe, OpenRouter (chat), and especially T3 Chat ($8/mo)** all already deliver cross-vendor multi-model. The gap vs incumbents is real; the gap vs aggregators is **execution/price/trust, not concept.** `[Verified]`
- **Transparency — STILL THE STRONGEST, FRESHEST WEDGE.** Perplexity's silent downgrades (Nov 2025) and quiet ~99% limit cuts (May 2026), plus T3's opaque credit redenomination and Cursor's >20x repricing, mean **"we show the exact model + USD cost and never silently downgrade" is more differentiated in mid-2026 than it was when the docs were written.** Lean into this hardest. `[Verified]`
- **Privacy/no-train — WEAKENING as a *consumer* differentiator, still strong for prosumers/EU.** Incumbents now offer no-train by default *at enterprise/team tiers* and temporary-chat modes; Mistral owns the EU-sovereign niche natively. Our consumer no-train-by-default is still ahead of ChatGPT/Claude *consumer* defaults, but it's **not unique** and is undercut by the discovery-order reality (§1.7). Position privacy as **"least-data-retained + EU-friendly + transparent,"** not "private/confidential." `[Verified]`
- **Cost control / BYOK — STILL A REAL WEDGE, and *more* relevant** given the credit-economy pivot (§1.1) and free OpenRouter BYOK (§1.5).

**Implication:** the three-legged wedge is real, but **transparency + cost-control are the durable legs; multi-model is now contested by aggregators (T3 the price-setter at $8); privacy is a prosumer/EU play, not a mass-consumer one.** Re-weight messaging accordingly.

---

## 3. PRD 05 review — gaps, errors, outdated items, inconsistencies (main deliverable)

> Reviewing `docs/prd/05-roadmap-monetization-metrics.md`. Section refs are to that file.

### 3.1 Pricing & monetization (§5)
- **[Outdated data] §5.3 table — Gemini "AI Plus ~$13.99."** Wrong; it's **$7.99** (§2.4). The table is otherwise close, but this is a 75% error on one cell. Fix.
- **[Major gap] §5.1/§5.5 — flat ~$15-20 Pro vs the 2026 credit-economy pivot.** The PRD commits to a flat-sub-with-"higher limits" Pro and relegates usage credits to P1. Given GitHub/Anthropic/Cursor all repricing to metered consumption in 2026 (§1.1), and given the PRD's *own* "inference whale" warning (§5.2), a flat Pro with "higher limits" **re-creates the whale risk it's trying to avoid.** Recommend: (a) define Pro's "higher limits" as **explicit metered caps with transparent overage (credits)**, and (b) **pull a minimal credit/overage capability into P0**, not P1. This is an internal inconsistency: §5.2 preaches hard metering, §5.1 sells "higher limits."
- **[Competitive gap] §5.3 — T3 Chat absent.** The closest competitor to our pitch ($8/mo, multi-model, message-metered, transparent caps) is not in the table or the strategy. Our ~$15-20 Pro is **2-2.5x T3's price for a similar surface.** The PRD must either justify the premium (privacy + a11y + mobile + true cost transparency) or reconsider price. **Add T3 as the anchor-to-beat.**
- **[Challenged rationale] §2.2 — "Not shipping ads … Perplexity retreated from it."** The market evidence is the opposite (§1.3, §2.3). Keep ads deferred, but **change the rationale to "trust-first brand choice," not "the market is abandoning ads."**
- **[Open question with a clear answer] §9.5 / §5.4.1 — free-tier default "DeepSeek vs Gemini Flash."** DeepSeek is banned/restricted across our target markets and contradicts our privacy story (§1.8). The PRD should **remove DeepSeek as a hosted default** and pick from Gemini Flash / GPT-mini / Claude Haiku / Mistral (EU). Self-hosted open weights = P2+ only.
- **[Missing] BYOK economics detail.** §5.1 says "BYOK at $0 markup" but doesn't note that routing via OpenRouter is **free for the first 1M BYOK req/mo** (§1.5) — materially lowers BYOK infra cost and supports the $0-markup promise. Add.

### 3.2 Metrics & KPIs (§6)
- **[Outdated benchmarks] §6.1 — retention uses generic SaaS numbers.** Replace/augment with **AI-native** retention (40% GRR / 48% NRR) and add the **"AI tourist" first-30/90-day churn** cohort (§1.2). The current D1/D7/D30 targets (25-30/15-18/5-8%) are SaaS-optimistic for an AI product.
- **[Missing KPI] First-week activation funnel / "Day-1 success."** The data's strongest retention lever ("Day-1 success checklist" → 52.7% conversion) maps to a metric the PRD should name explicitly, not fold into generic "activation."
- **[Missing KPI] ARPU target band.** §6.1 lists "ARPU" but no benchmark. Add the 2026 bands (sub-led $30-100+; hybrid $3-15) so the target is calibrated (§1.3).
- **[Good, keep] cost-per-message / margin / routing-mix and TTFT-per-model** are correctly prioritised and remain best-practice in 2026. Validated.

### 3.3 Compliance & NFRs (§7)
- **[Major gap] §7.5 — EU-only compliance; no US state law.** Add **CA SB 243 (companion-chatbot AI-disclosure, effective Jan 1 2026), CA AB 2013 (training-data transparency, Jan 1 2026), CO SB 205 (enforcement Jun 30 2026)**, and the **Dec 2025 federal preemption EO + DOJ task force** (note: child-safety carve-outs survive; not self-executing). Our P0 AI-interaction disclosure already covers the core CA/CO requirement — say so. (§1.6)
- **[Add a gate] Minors / companion-style use.** CA SB 243 + surviving child-safety preemption carve-outs mean we need an explicit decision: do we serve minors / companion personas? If yes, additional obligations (crisis protocols, break reminders) attach. Currently unaddressed.
- **[Precision fix] §7.3 — "2026 US federal ruling … no legal confidentiality."** Reword to the accurate, narrower fact (SDNY district opinion on privilege + a discovery order); change the marketing claim from "confidential" to "we minimise retained data" (§1.7, §2.4).
- **[Refine] §7.3 — privacy as differentiator.** Note incumbents now match no-train **at enterprise/team tiers**; our edge is at the **consumer/prosumer** tier + EU-friendliness + transparency. Keep, but right-size the claim (§2.5).
- **[Verify dates — confirmed] §7.5 / §4.4 — EU AI Act Aug 2/Dec 2 2026 dates are CORRECT** (`[Verified]` this session). The `[VERIFY]` flags can be downgraded to "confirmed 2026-05-27." The €35M/7% penalty figure is also consistent with the Act. `[Verified]`

### 3.4 Roadmap (§4)
- **[Sequencing inconsistency] Usage credits P1 vs the credit-economy pivot.** Per §3.1 above, move a **minimal metered-overage/credit primitive to P0** (the cost meter is already P0; metering enforcement + a simple credit top-up is a small delta and directly de-risks whales). The PRD's own dependency logic supports this (transparency meter is the spine).
- **[Good] Multi-model picker + transparency in P0** — strongly validated; arguably the single best decision in the doc given §2.5.
- **[Add to §4.4 dependency notes] US-state-law disclosure** (CA, live now) belongs next to the EU-AI-Act note as a P0 launch-gate for the US market, not just EU.

### 3.5 Risks (§8)
- **[Under-weighted] Aggregator price compression.** "Commoditization vs incumbents" is listed, but the **sharper near-term risk is aggregator undercutting (T3 @ $8, OpenRouter chat)** on the *same* multi-model surface. Add a row: "multi-model is commoditised by cheap aggregators → differentiate on transparency/privacy/a11y/mobile, not on having many models."
- **[Add] Pricing-model risk.** "We ship a flat sub while the market reprices to metered credits, leaving us exposed to whales and looking dated." Mitigation = P0 metering/overage (§3.1).
- **[Add] Regulatory-surface risk beyond EU** (US state patchwork + shifting federal preemption) — currently only EU-AI-Act timeline slip is listed.

### 3.6 Open questions (§9)
- **§9.5 (free default model):** effectively answered — drop DeepSeek (§1.8).
- **§9.10 (ads at scale):** reframe — ads are *rising* market-wide; the question is purely brand/trust, not "is ads a real lever" (it is).
- **Add new OQ:** "Do we adopt a metered/credit Pro from launch given the 2026 credit-economy pivot?"
- **Add new OQ:** "Do we serve minors / companion use (triggers CA SB 243 + child-safety rules)?"

---

## 4. Top 5 recommendations (prioritized, actionable)

1. **Pull a minimal transparent-metering + credit-overage primitive into P0 (don't leave credits in P1).** The 2026 market is repricing to usage/credit billing (GitHub Copilot Jun 1, Anthropic, Cursor). A flat ~$15-20 Pro with "generous limits" re-creates the whale risk the PRD warns against and looks dated within a year. The cost meter is already P0 — add enforcement + a simple USD-credit top-up. This *is* our "you control the cost" wedge. (§1.1, §3.1, §3.4)

2. **Make *transparency + cost-control* the lead message; treat multi-model as table-stakes and privacy as a prosumer/EU play.** Multi-model is now commoditised by T3 Chat ($8/mo) and OpenRouter chat; incumbents match no-train at enterprise tiers. The freshest, most defensible wedge in mid-2026 is **"exact model + exact USD cost, never silently downgraded"** — sharpened by Perplexity's May-2026 limit-cut scandal and the industry's opaque credit redenomination. (§2.5, §1.4)

3. **Add a US-state-law compliance layer to the PRD (§7) and treat AI-interaction disclosure as a live US launch-gate, not just EU.** CA SB 243 + AB 2013 are effective *now* (Jan 1 2026); CO SB 205 enforces Jun 30 2026; federal preemption is contested and exempts child-safety. Add a "do we serve minors?" gate. Our planned P0 disclosure largely covers it — but the PRD must say so and fix the EU-only framing. (§1.6, §3.3)

4. **Disqualify DeepSeek as the hosted free-tier default and fix the privacy-claim precision.** DeepSeek is banned across our target markets and contradicts the privacy story — default to Gemini Flash / GPT-mini / Claude Haiku / Mistral instead. Separately, reword the "no legal confidentiality" point to its accurate (district-court, privilege-only) scope and market "minimal retention," not "confidential." (§1.7, §1.8, §3.3)

5. **Re-baseline the financial/metrics model on AI-native (not SaaS) economics, and add T3 Chat as the explicit price/feature anchor.** Use 40% GRR / 48% NRR, the "AI tourist" 30/90-day churn cohort, ARPU bands, and a first-week "Day-1 success" activation funnel (the top retention lever in the data). Decide explicitly whether ~$15-20 Pro is justified at ~2-2.5x T3's $8 — or reprice. (§1.2, §1.3, §1.4, §3.2)

---

## 5. Source list (this review)

**Competitor pricing**
- ChatGPT: https://chatgpt.com/pricing/ · https://www.cometapi.com/chatgpt-pricing-2026-free-vs-go-vs-plus-vs-pro/ · https://felloai.com/chatgpt-pricing-guide-free-go-plus-pro-alternatives-october-2025/
- Claude: https://claude.com/pricing · https://mem0.ai/blog/anthropic-claude-pricing · https://suprmind.ai/hub/claude/pricing/
- Gemini / Google AI: https://one.google.com/about/google-ai-plans/ · https://gemini.google/subscriptions/ · https://9to5google.com/2026/04/11/google-ai-pro-ultra-features/ · https://blog.google/products-and-platforms/products/google-one/google-ai-subscriptions/
- Perplexity: https://www.finout.io/blog/perplexity-pricing-in-2026 · https://suprmind.ai/hub/perplexity/pricing/
- Copilot: https://www.microsoft.com/en-us/microsoft-365-copilot/pricing · https://www.eesel.ai/blog/copilot-pricing
- Mistral: https://mistral.ai/pricing · https://costbench.com/software/ai-chatbots/mistral/ · https://techjacksolutions.com/ai-tools/mistral/mistral-pricing/
- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing · https://devtk.ai/en/blog/deepseek-api-pricing-guide-2026/
- Poe: https://costbench.com/software/ai-chatbots/poe/ · https://help.poe.com/hc/en-us/articles/19945140063636-Poe-Purchases-FAQs
- T3 Chat: https://skywork.ai/skypage/en/T3-Chat-Pricing-Is-the-$8-AI-Powerhouse-Too-Good-to-Be-True/1974387624371744768 · https://x.com/theo/status/1887000229922353524
- OpenRouter: https://openrouter.ai/pricing · https://openrouter.ai/announcements/1-million-free-byok-requests-per-month · https://openrouter.ai/docs/guides/overview/auth/byok

**Monetization / economics / metrics**
- Credit-economy pivot: https://metronome.com/blog/2026-trends-from-cataloging-50-ai-pricing-models · https://windowsforum.com/threads/github-copilot-ai-credits-usage-based-billing-starts-june-1-2026.415470/ · https://vibecoding.clickfq.com/blog/ai-credit-economy
- Inference-cost / whales: https://aiautomationglobal.com/blog/ai-inference-cost-crisis-openai-economics-2026 · https://interestingengineering.substack.com/p/priced-to-scale-priced-to-fail-how
- ARPU / retention / churn: https://www.thrad.ai/content/arpu-benchmarks-for-ai-chatbot-apps · https://www.growthunhinged.com/p/free-to-paid-conversion-report · https://www.amraandelma.com/free-trial-conversion-statistics/
- ChatGPT ads: https://openai.com/index/testing-ads-in-chatgpt/ · https://www.macrumors.com/2026/02/09/chatgpt-now-has-ads/ · https://theaiinsider.tech/2026/02/26/openai-begins-advertising-rollout-in-chatgpt-as-it-tests-new-revenue-model/

**Market size**
- https://www.demandsage.com/chatbot-statistics/ · https://www.index.dev/blog/chatgpt-statistics · https://www.grandviewresearch.com/industry-analysis/chatbot-market

**Differentiation / trust**
- Perplexity trust: https://www.remio.ai/post/perplexity-ai-silent-model-substitution-ceo-aravind-srinivas-responds-to-pro-user-accusations · https://www.androidheadlines.com/2026/05/perplexity-pro-users-complain-quiet-advanced-model-limits-cut.html
- ChatGPT model picker/router: https://the-decoder.com/openai-overhauls-chatgpts-model-selection/ · https://www.ai-toolbox.co/chatgpt-models/chatgpt-models-explained-complete-comparison-2026

**Regulation**
- EU AI Act: https://artificialintelligenceact.eu/article/50/ · https://artificialintelligenceact.eu/transparency-rules-article-50/ · https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content
- US state laws: https://www.orrick.com/en/Insights/2026/04/2026-State-Chatbot-Laws-Key-Provisions-and-Regulatory-Trends · https://www.kslaw.com/news-and-insights/new-state-ai-laws-are-effective-on-january-1-2026-but-a-new-executive-order-signals-disruption · https://leg.colorado.gov/bills/sb24-205
- Federal preemption EO: https://www.gibsondunn.com/president-trump-latest-executive-order-on-ai-seeks-to-preempt-state-laws/ · https://www.sidley.com/en/insights/newsupdates/2025/12/unpacking-the-december-11-2025-executive-order

**Privacy / data / legal**
- Training defaults: https://lumichats.com/blog/chatgpt-claude-gemini-training-your-data-2026-privacy-guide · https://www.anthropic.com/news/updates-to-our-consumer-terms · https://openai.com/enterprise-privacy/
- AI-chat discovery rulings: https://www.crowell.com/en/insights/client-alerts/federal-court-rules-some-ai-chats-are-not-protected-by-legal-privilege-what-it-means-for-you · https://natlawreview.com/article/openai-loses-privacy-gambit-20-million-chatgpt-logs-likely-headed-copyright
- DeepSeek bans: https://aitechtonic.com/deepseek-ai-banned-countries/ · https://introl.com/blog/deepseek-government-bans-spreading-worldwide-2026 · https://witness.ai/blog/deepseek-security-concerns/
