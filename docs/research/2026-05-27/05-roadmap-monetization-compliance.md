# Research Pass — Roadmap, Monetization, Metrics & Compliance (PRD 05)

**Scope:** Fresh online research (current as of May 2026) + critical review of `/home/user/agent/docs/prd/05-roadmap-monetization-metrics.md`.
**Owner domain:** Roadmap, Monetization, Metrics & NFRs (incl. compliance).
**Author:** Product Strategy / GTM / Compliance research.
**Date:** 2026-05-27. **Reasoning effort:** HIGH. **Method:** every price/date/benchmark verified against live secondary sources (and first-party where reachable); items I could not confirm are flagged.

---

## 1. Summary

- **The single most important pricing finding: T3 Chat — the PRD's explicit "$8/mo = 1,500 msgs (Claude capped 100/mo)" anchor — has materially changed its model.** T3 still costs **$8/mo**, but it overhauled credits during a 2026 Launch Week: no more "standard/premium" credits; it now runs a **"usage bar" that resets every 4 hours** plus a monthly **Overage bucket** (Base refills every 4h, Overage on monthly renewal). The PRD's "1,500 msgs / Claude 100" framing is **stale**. The $8 price point and "anchor-to-beat" logic still hold; the mechanics description does not. **[error]**
- **The PRD's two key compliance dates are both wrong or stale.** (1) EU AI Act **Article 50 penalties are €15M / 3%**, not "€35M or 7%" — the PRD quotes the Article 5 *prohibited-practices* tier. **[error]** (2) **Colorado SB 205's "enforce Jun 30 2026" is dead**: a federal court **stayed enforcement (Apr 27, 2026)** and Gov. Polis **signed SB 26-189 (May 14, 2026)** repealing/replacing the Act with a new effective date of **Jan 1, 2027** (and a narrower ADMT scope that likely does **not** cover a general chat product). **[error]**
- **The EU AI Act Article 50 contest the PRD flags is now largely resolvable.** Post-Omnibus (Commission proposal Nov 19, 2025; Council/Parliament provisional agreement **May 6–7, 2026**; Council confirmation **May 13, 2026**): **AI-interaction disclosure (Art. 50(1)) stays at 2 Aug 2026.** **Content-marking (Art. 50(2)) also applies from 2 Aug 2026 for systems placed on market on/after that date — there is NO grace period for a new product like ours.** The grace period (to ~2 Dec 2026, originally Feb 2027 in the proposal) is **only for systems already on the market before 2 Aug 2026.** So PRD 04's "content-marking may bind 2 Aug 2026" reading is **correct for us** — but only *if/when we ship AI-generated media* (text/image/audio/video). For a P0 text-relay chat with no own-generated synthetic-media product, the marking obligation is narrow.
- **The 2026 credit-economy pivot is real and well-dated** — confirms Decision D8. **GitHub Copilot → usage-based billing Jun 1, 2026** (monthly AI-credit allotment, token-metered); **Anthropic → dedicated usage-based credit system for programmatic/agent usage from Jun 15, 2026**; **Cursor** scales credit pools $20–$200. The PRD's instinct to ship a metered overage primitive at P0 is well-supported.
- **Core benchmarks verify as directionally correct and current:** AI-native **≈40% GRR / 48% NRR** (vs ~82% SaaS) is confirmed by the 2026 ChartMogul/Growth Unhinged "AI churn wave" data, which adds a sharp new datapoint: **budget AI tools <$50/mo see ~23% GRR; premium >$250/mo ~70% GRR / 85% NRR.** AI gross margin **~50–60%** confirmed (ICONIQ: 41%→45%→52% 2024-26). Free→paid **median ~8%, freemium organic ~2.6%, feature-gated ~5.1%** confirmed. The "inference whale ~$35k on $200/mo" figure is confirmed (Claude Code leaderboard, ~11B tokens).
- **Several incumbent prices in §5.3 are stale or wrong.** Copilot Pro is **$10/mo** (PRD says ~$20/seat) and Pro+ **$39**; new **$100/mo ChatGPT Pro tier** (launched Apr 9, 2026) and **$100/mo Google AI Ultra tier** (Google I/O, May 2026) both exist and are unmentioned; Gemini AI Ultra is now **$100 or $200** (the $250→$200 cut the PRD notes is real but incomplete). Perplexity Pro **$20** / Max **$200** confirmed; Mistral Pro **$14.99** / Team **$24.99** confirmed; Poe **$19.99** main tier confirmed (free tier now capped at 300 points, no rollover).
- **Perplexity-abandoned-ads / ChatGPT-expanding-ads signal confirmed and current.** Perplexity dropped all ads **Feb 2026** citing trust (now sub/enterprise-led, ~$200M ARR). OpenAI is **expanding** ads: pilot announced Jan 16, 2026; live in US Feb 9 on Free + Go; international expansion (UK, MX, BR, JP, KR) announced **May 7, 2026**; ads >$100M ARR. The PRD's "decline on trust/brand basis" framing is well-founded and current.
- **Privacy positioning is actually STRONGER than the PRD claims.** The PRD hedges that no-train "is not unique" because incumbents match it at enterprise tiers. But on **consumer defaults**, OpenAI/Anthropic/Google now **train-by-default and require opt-out** (Anthropic's Aug 2025 change; 5-yr retention if you allow training, else 30-day). Our **consumer/prosumer no-train-by-default** is a genuine and current differentiator against consumer defaults — the PRD under-sells it slightly (while correctly cautioning against a "confidential/privileged" claim).

---

## 2. Competitor pricing & market (May 2026)

All prices monthly USD unless noted. Verified against the listed sources on 2026-05-27.

| Product | Tiers | Price | Metered / credit notes | Source |
|---|---|---|---|---|
| **ChatGPT** | Free / Go / Plus / **Pro (new $100)** / Pro / Business / Enterprise | Free $0 (**ads on Free + Go**); Go ~$8; Plus **$20**; **Pro $100 (5× Plus, launched Apr 9 2026)**; Pro $200 (20×, 1M ctx); Business ~$25–30/seat; Enterprise custom | Subscription + usage caps; ads expanding (US→UK/MX/BR/JP/KR, May 7 2026); >$100M ad ARR | chatgpt.com/pricing; cloudzero; theaiinsider; openai.com ads |
| **Claude** | Free / Pro / Max 5× / Max 20× / Team / Enterprise | Pro **$20** ($17 annual); Max 5× **$100**; Max 20× **$200**; Team **$25**/seat; Team Premium **$125**/seat; Enterprise custom | **Dedicated usage-based credit system for programmatic/agent (Agent SDK, GH Actions) from Jun 15 2026**; weekly rate limits added Aug 2025 | claude.com/pricing; mem0; infoworld; implicator |
| **Gemini (Google AI)** | Free / AI Plus / AI Pro / **AI Ultra ($100)** / AI Ultra ($200) | AI Plus **$7.99**; AI Pro **$19.99**; **AI Ultra $100 (new, 5×, I/O 2026)**; AI Ultra **$200** (cut from $250) | "AI Credits" mechanism meters Gemini-app/Antigravity usage; tiered usage multipliers | one.google.com; 9to5google (May 25 2026); blog.google I/O 2026 |
| **Perplexity** | Free / Pro / Max / Enterprise | Pro **$20**; Max **$200** ($2,000/yr); Enterprise ~$40–325/seat; Edu Pro ~$10 | **Abandoned ALL ads Feb 2026 (trust)**; now sub + enterprise-led, ~$200M ARR; Max = 10k Computer credits/mo | finout; macrumors (Feb 18 2026); almcorp; perplexity.ai/max |
| **Copilot** | Free / Pro / Pro+ / Business / Enterprise | **Pro $10** (PRD wrong: says ~$20); **Pro+ $39**; Business **$19**/seat; Enterprise **$39**/seat | **Usage-based billing from Jun 1 2026**: monthly **GitHub AI Credits** allotment, token-metered; completions stay free | github.blog; docs.github.com; visualstudiomag |
| **Mistral Le Chat** | Free / Pro / Team | Pro **$14.99**; Team **$24.99**/seat ($19.99 annual) | Free ~limited; EU-sovereign angle; separate per-token API | mistral.ai/pricing; cloudzero; costbench |
| **DeepSeek** | Free app / API | Free (no paywall); ultra-cheap API | Aggressive per-token + cache discounts; **excluded as our default on privacy/geopolitics** | api-docs.deepseek.com |
| **T3 Chat** (anchor-to-beat) | trial / Pro | **$8/mo** (1st month $1 promo) | **CHANGED 2026:** dropped standard/premium credits → **"usage bar" resetting every 4h + monthly Overage bucket** (Base refills 4h, Overage on renewal). Old "1,500 msgs / Claude 100" framing superseded. No privacy story. | t3.chat; x.com/theo (status 2022844310165893484); useautumn.com |
| **Poe** | Free / Subscription / Teams | Sub **$19.99** (1M points); Teams **$249.99**; entry points from ~$4.99; higher prepaid up to ~$249.99 | Compute-points; **free tier now capped 300 pts, no rollover** (down from 3,000/day in 2024) | help.poe.com; costbench; oreateai |
| **OpenRouter** (BYOK/agg) | free models / credits | n/a sub | **BYOK 5% of equiv cost; first 1M BYOK req/mo FREE** (resets monthly UTC); platform fee on non-BYOK credit usage; Enterprise 5M free | openrouter.ai/announcements; openrouter.ai/pricing |
| **TypingMind** (BYOK) | one-time license | ~$79 one-time (verify) | Pay providers directly; not re-verified this pass | (PRD-carried; re-verify) |
| **Our product (proposed)** | Metered free / Metered Pro / BYOK | Pro band ~$15–20 (OPEN) | BYOK $0 markup + transparent USD credits; minimal overage primitive P0 | this PRD |

**Read (updated):** Two anchors still bracket us — the legacy **~$20 "Plus/Pro"** consumer tier (ChatGPT/Claude/Perplexity all sit there) and the **$8 multi-model floor (T3 Chat)**. New since the PRD was drafted: a **$100 "mid-Pro" tier proliferated** (ChatGPT Pro $100, Google AI Ultra $100) as vendors segment power users between $20 and $200. The whole market is **layering usage/credits onto subscriptions** (Copilot, Anthropic, Gemini "AI Credits," Cursor, and T3's 4-hour bucket) — exactly the D8 thesis. **Implication:** our metered-Pro-with-credit-overage shape is now the *mainstream* 2026 pattern, not a contrarian bet; the differentiation must come from **transparency + privacy + a11y/mobile polish**, not from the pricing mechanic itself (which is being commoditized).

---

## 3. Compliance status (May 2026)

| Law | Obligation (for us) | Applicable date | Status — verified? | Source |
|---|---|---|---|---|
| **EU AI Act Art. 50(1)** | Disclose users are interacting with AI | **2 Aug 2026** | **VERIFIED, firm.** Unaffected by Omnibus; "remaining Art. 50 obligations continue to apply from 2 Aug 2026." | gibsondunn (May 27 2026); plesner; mofo; artificialintelligenceact.eu/article/50 |
| **EU AI Act Art. 50(2)** (machine-readable marking of AI-generated content) | Mark AI-generated/manipulated content (text/image/audio/video) | **2 Aug 2026 for systems placed on market on/after that date (NO grace); grace to ~2 Dec 2026 only for pre-existing systems** | **VERIFIED but nuanced.** A new launch gets NO grace. Proposal originally said grace→Feb 2 2027 (6mo); final May agreement = ~4mo→2 Dec 2026. Resolves the PRD's contested flag: for *us*, binds **2 Aug 2026** **if** we generate synthetic media. | gibsondunn; mofo (Dec 1 2025); lexology; plesner |
| **EU AI Act — Digital Omnibus** | (Context) deadline reshuffle | Proposal **19 Nov 2025**; provisional agreement **6–7 May 2026**; Council confirmed **13 May 2026** | **VERIFIED.** Mainly **delays high-risk** (stand-alone → 2 Dec 2027; embedded → 2 Aug 2028). **Does NOT delay Art. 50 interaction-disclosure.** Still provisional pending Official Journal. | consilium (May 7 2026); hoganlovells; addleshawgoddard; gibsondunn |
| **EU AI Act penalties (Art. 50)** | Transparency-violation fines | In force with Art. 50 | **CORRECTION:** **€15M or 3%** of worldwide turnover (Art. 99). The **€35M / 7%** the PRD quotes is the **Art. 5 prohibited-practices** tier, not transparency. | artificialintelligenceact.eu/article/99; holisticai |
| **CA SB 243** (Companion Chatbot Act) | AI disclosure, crisis protocols, minor protections | **Effective Jan 1, 2026** | **VERIFIED, live.** Survives federal preemption EO (child-safety carve-out). Only bites if we offer companion personas / serve minors. | crowell; goodwinlaw; orrick |
| **CA AB 2013** (training-data transparency) | Developer must post training-dataset disclosures | **Effective Jan 1, 2026** | **VERIFIED, live.** Touches *model providers'* disclosures; we are a deployer relaying their models — obligation primarily upstream, but diligence needed. | crowell (AB 2013); goodwinlaw (Jan 2026); leginfo.ca.gov |
| **CO SB 205** (Colorado AI Act) | High-risk AI / consumer disclosure | **WAS Jun 30 2026 — NOW MOOT** | **CORRECTION:** Federal court **stayed enforcement Apr 27, 2026**; **SB 26-189 signed May 14, 2026** repeals/replaces SB 205, **new effective date Jan 1, 2027**, narrowed to **ADMT for "consequential decisions"** (education/employment/finance/insurance/healthcare/gov). A general chat product likely **out of scope**. | theemployerreport (May 5 2026); hklaw (May 2026); coloradosun (May 12 2026); cooley |
| **US federal preemption EO** | Context — challenges state AI laws | EO **Dec 11, 2025**; DOJ Task Force within 30 days | **VERIFIED.** Not self-executing; **expressly carves out child-safety**, AI compute/data-center, state procurement. State patchwork **live & contested, not preempted.** | whitehouse.gov; mofo (Dec 13 2025); sidley; npr |
| **GDPR (no-train / retention)** | Consent, access, deletion, minimization for EU users | In force | **VERIFIED, ongoing.** No-train-by-default + short retention + export/delete is the right posture; reduces what is compellable in discovery (cf. 2026 SDNY rulings — narrow, not binding precedent). | (PRD-carried; ongoing) |

**Net compliance read:** The PRD's compliance section is **directionally right but contains two factual errors (Art. 50 penalty figure; CO SB 205 status) and one now-resolvable contest (Art. 50(2) date).** The EU AI-interaction disclosure (2 Aug 2026) is the only firm hard launch-gate for an EU text-chat MVP; content-marking only bites if/when we ship AI-generated media. The US "AI-interaction disclosure is a P0 launch-gate" claim now rests on **CA SB 243** (if companion/minors) — **CO SB 205 can no longer be cited as a live US disclosure gate.**

---

## 4. New ideas & developments (online research)

### Theme A — Pricing/packaging: the credit economy is now mainstream (confirms D8)
- **GitHub Copilot → usage-based billing Jun 1, 2026.** Every plan gets a monthly **GitHub AI Credits** allotment; usage metered on input/output/cached tokens at API rates; code completions stay free; monthly Pro/Pro+ auto-migrate, annual plans grandfathered on request-based. (github.blog; docs.github.com — accessed 2026-05-27)
- **Anthropic → dedicated usage-based credit system Jun 15, 2026** for programmatic/agent usage (Agent SDK, GH Actions, 3rd-party frameworks), separated from chat-subscription limits; credit pool scales with subscription tier. (infoworld; implicator; pymnts — 2026)
- **Cursor** scales credit pools by tier ($20→$200) mapped to underlying model cost so devs "see the inference economics." (metronome; developersdigest — 2026)
- **T3 Chat's 4-hour usage bar + monthly Overage bucket** is a concrete consumer-facing pattern for bursty usage worth studying — it directly addresses the "bursty AI usage" problem the PRD's metrics section raises. (x.com/theo status 2022844310165893484; useautumn.com — 2026)
- **Implication for us:** D8 is vindicated and *more* urgent — a flat sub would now look dated within months. **Steal T3's "rolling short-window bucket + monthly overage" UX** as a candidate design for our P0 metered-overage primitive (smooths the bursty-usage friction that the PRD's §6 metrics note calls out). Make credits map to **real USD/token cost** (Metronome's finding: credits that reflect resource economics or a legible value metric win) — which is exactly our transparency wedge.

### Theme B — Retention/economics benchmarks (verify §6 figures)
- **AI-native ≈40% GRR / 48% NRR confirmed** (ChartMogul/Growth Unhinged "AI churn wave," 2026). New nuance: **GRR climbed 27% (Jan 2025) → 40% (Sep 2025)** as "tourists" churned out. **Budget tools <$50/mo: ~23% GRR; premium >$250/mo: ~70% GRR / 85% NRR.** (chartmogul; growthunhinged — 2026)
- **AI gross margin ~50–60% confirmed**; ICONIQ trend **41%→45%→52%** (2024→2026), structural ceiling ~60–65%. (softwareseni; saasmag — 2026)
- **Free→paid: median ~8%; freemium organic ~2.6%; feature-gated ~5.1%; CC-gated trials ~30%.** Guidance: if <2–3%, free tier too generous; consider reverse trial. (growthunhinged; firstpagesage — 2026)
- **Inference whale ~$35k on $200/mo confirmed** (Claude Code leaderboard, ~11B tokens, ~175× subsidy); median Claude Code dev implies ~$254/mo subsidy. (interestingengineering; benzatine; implicator — 2026)
- **Implication for us:** the **<$50/mo → 23% GRR** datapoint is a *strong new argument in the Pro-price debate*: pricing at/below the $8–15 budget band risks the catastrophic-churn cohort, while the $250+ tier is out of reach for our persona. Our ~$15–20 band sits in the worst-studied middle — we should instrument the AI-tourist churn cohort hard from day one and consider a credit-card-gated reverse trial to lift conversion.

### Theme C — Ads as a polarizing trust signal (confirms §2.2)
- **Perplexity dropped ALL ads Feb 2026** (FT-reported), executives: ads make users "doubt everything"; pivoted to sub+enterprise, ~$200M ARR. (macrumors Feb 18 2026; almcorp; trendingtopics)
- **OpenAI expanding ads:** pilot Jan 16 2026 → US live Feb 9 (Free+Go, ~1%→5% mobile) → intl May 7 2026 (UK/MX/BR/JP/KR); >$100M ad ARR; ads excluded from paid tiers and from under-18/sensitive topics. (openai.com; theaiinsider; techsifted)
- **Implication for us:** the mixed signal is real and current; our trust/brand-based deferral is defensible. Worth noting OpenAI's claim of "no trust-metric impact" — a counter-argument we should be ready to rebut if ads are revisited at scale.

### Theme D — Privacy defaults moved AGAINST consumers (strengthens our hook)
- **Anthropic (Aug 2025): consumer chats train-by-default unless you opt out**; 5-yr retention if you allow training, else 30-day. OpenAI/Google similar consumer-default drift; OpenAI uniquely lets you keep history without consenting to training. (techcrunch; anthropic.com; bitdefender — 2025-26)
- **API tiers are stronger** (Anthropic API: 7-day retention, never trained) — relevant to our BYOK/route design.
- **Implication for us:** our **consumer/prosumer no-train-by-default** is a *live, current* differentiator vs incumbent **consumer defaults** (not just enterprise parity). The PRD's hedge ("not unique") is too cautious on the consumer-default axis — recommend sharpening the claim while keeping the "minimal-retention, not confidential" guardrail.

### Theme E — Compliance is shifting under our feet (high priority)
- EU Omnibus delayed **high-risk** (not Art. 50 disclosure); Art. 50(2) marking grace only for pre-existing systems. (See §3.)
- Colorado's flagship AI Act effectively **collapsed** (stay + repeal/replace → Jan 2027, narrowed scope). (See §3.)
- **Implication for us:** treat all regulatory dates as **live-tracked, not locked**. The only firm near-term EU gate is **2 Aug 2026 interaction-disclosure** (cheap, already P0). Build content-marking design *with* any future media-gen, not for P0 text. Drop CO SB 205 as a cited US gate.

---

## 5. PRD review findings

Tagged `[error]` / `[gap]` / `[inconsistency]` / `[scope]` / `[risk]` with §reference + action.

1. **[error] §5.3, §9.1, §10.3, Risk table, §2.2 (and PRD 00 §10) — T3 Chat mechanics stale.** "$8/mo = 1,500 msgs (Claude capped 100/mo; +$8/100 Claude credits)" is superseded by T3's 2026 Launch-Week overhaul: a **4-hour-resetting usage bar + monthly Overage bucket**, no standard/premium credits. **Action:** keep the **$8 price** and "anchor-to-beat" logic; rewrite the mechanics to "4-hour usage bucket + monthly overage" and re-time the `[VERIFY]` to the new model.

2. **[error] §7.5, §10.3 — EU AI Act Article 50 penalty figure wrong.** PRD states "Penalties up to €35M or 7%." Art. 50 transparency violations are **€15M or 3%** (Art. 99); €35M/7% is the **Art. 5 prohibited-practices** tier. **Action:** correct to €15M/3% for Art. 50; reserve €35M/7% language for prohibited practices only.

3. **[error] §4.3, §7.5, §8 (Risk table), §9.6, §10.3 (and PRD 00 §10) — Colorado SB 205 status obsolete.** PRD treats CO SB 205 as a live US disclosure gate "enforce Jun 30 2026." It is **stayed (Apr 27 2026)** and **repealed/replaced by SB 26-189 (signed May 14 2026, effective Jan 1 2027)**, narrowed to ADMT for consequential decisions — a general chat product is likely **out of scope**. **Action:** remove CO SB 205 as a cited P0 US disclosure gate; rest the US disclosure argument on **CA SB 243** (only if companion/minors) and the general AI-interaction-disclosure good-practice; add a watch-item for SB 26-189's Jan 2027 ADMT scope.

4. **[inconsistency-resolved / scope] §4.3, §7.5, §9.6 — Art. 50(2) "Aug 2 vs Dec 2" contest is now resolvable.** The contest can be closed: for **a new product placed on market on/after 2 Aug 2026, content-marking binds 2 Aug 2026 with no grace** (grace is pre-existing-systems-only). PRD 04's "may bind Aug 2" reading is **correct for us**. **BUT** it only attaches **if we generate synthetic content** (text/image/audio/video). **Action:** resolve the flag: "If our P0 ships only model-relayed responses with attribution, the Art. 50(2) marking obligation is narrow; it becomes a hard 2 Aug 2026 gate the moment we ship AI media-gen (P2). Design marking with media-gen, not for P0 text." Keep the Omnibus-provisional `[VERIFY]` (not yet in Official Journal).

5. **[error] §5.3, §10.3 — Copilot Pro price wrong.** PRD lists "Pro ~$20/seat (needs M365)." Copilot **Pro is $10/mo**, Pro+ $39, Business $19/seat, Enterprise $39/seat; moving to usage-based billing Jun 1 2026. **Action:** correct to $10 Pro / $39 Pro+ / $19 Business / $39 Enterprise + note the Jun 1 2026 usage-based shift.

6. **[gap] §5.3 — Missing the new $100 "mid-Pro" tier and Gemini AI Ultra split.** ChatGPT **Pro $100** (Apr 9 2026) and Google **AI Ultra $100** (I/O 2026) are unmentioned; Gemini Ultra is now **$100 or $200**. **Action:** add the $100 tier row; note the market is segmenting power users into a $100 band between $20 and $200.

7. **[gap] §6.1, §9.1 — New retention-by-price-band data sharpens the pricing decision.** The 2026 churn-wave data (**<$50/mo → ~23% GRR; >$250/mo → ~70% GRR**) is directly load-bearing for the $8-vs-$15-20 debate and is not in the PRD. **Action:** add to §6.1 and cite in the §9.1 open question — our ~$15–20 band sits in the under-studied middle; instrument the AI-tourist churn cohort and consider a CC-gated reverse trial.

8. **[gap/risk] §7.3 — Privacy claim under-sold on the consumer-default axis.** PRD hedges no-train "is not unique (incumbents match at enterprise tiers)." On **consumer defaults**, incumbents now **train-by-default / require opt-out** (Anthropic Aug 2025; 5-yr retention if opted in). Our consumer no-train-by-default is a **current, real** differentiator. **Action:** sharpen to "ahead of incumbent **consumer defaults** (which train-by-default), positioned as least-data-retained + EU-friendly + transparent — not 'confidential.'" Keep the discovery/privilege guardrail.

9. **[inconsistency] §5.1/§5.3 vs market reality — "2–2.5× T3's $8" framing slightly off.** Since T3 moved off a clean per-message model to a 4-hour usage bucket, the "2–2.5×" multiple is now an apples-to-oranges comparison. **Action:** reframe the premium justification against the **$8 price** (still valid) but stop implying a clean per-message equivalence; lean on the privacy/a11y/transparency justification.

10. **[gap] §5.2, §6.1 — AI gross-margin trend is now quantified.** PRD cites "~50–60%" generically. ICONIQ now shows **41%→45%→52% (2024→2026)** with a ~60–65% ceiling. **Action:** cite the trend; it supports "margin is engineered, not assumed" and sets a realistic internal target (don't model toward SaaS 80%).

11. **[scope] §4.3 / D8 — metered-overage primitive is now mainstream, not contrarian.** With Copilot/Anthropic/Gemini/Cursor/T3 all on credits, the PRD's framing of D8 as a forward-looking bet is understated; it's now table stakes. **Action:** reframe D8 rationale from "the market is repricing" to "the market has repriced; a flat sub is now the dated option" — and note the *differentiation* must come from transparency, not the mechanic.

12. **[gap] §5.1, §9.2 — OpenRouter BYOK terms verified and current.** "5% of equiv cost, first 1M BYOK req/mo free, platform fee on non-BYOK" all **confirmed** (May 2026). One caveat to add: OpenRouter announced (Jun 2025) it **intends to replace the 5% usage fee with a fixed monthly subscription (TBD)** — a future-term risk to the $0-markup BYOK economics. **Action:** mark as `[VERIFIED 2026-05-27]` and add the "fee model may change to fixed sub" watch-item.

13. **[risk/gap] §7.5, §9.11 — minors/companion-persona gate is the *surviving* US compliance teeth.** With CO SB 205 gone and the federal EO carving out child-safety, **CA SB 243 is the main live US obligation** and it triggers specifically on companion/minors. **Action:** elevate the §9.11 decision — it is now the primary determinant of US P0 compliance load, not a side-question.

14. **[gap] §6.1 — "Day-1 success checklist → 52.7% trial conversion" is unverified and oddly precise.** I could not independently confirm this exact figure in this pass. **Action:** keep the `[VERIFY]` flag; treat 52.7% as illustrative, not a target, until sourced.

15. **[scope — confirm, no change] §2.2 — ads deferral framing is current and correct.** Perplexity-withdrew / OpenAI-expanding both verified as of May 2026. No change needed beyond refreshing the access dates.

---

## 6. Recommendations (prioritized)

### P0 (fix before PRD-lock / build)
- **Correct the three factual errors:** EU Art. 50 penalty → **€15M/3%**; **drop/replace CO SB 205** as a live gate (note SB 26-189 → Jan 2027, narrowed); Copilot Pro → **$10**. (Findings 2, 3, 5.)
- **Rewrite the T3 Chat anchor** to the new 4-hour-bucket + overage model; keep $8 and "anchor-to-beat." (Finding 1.)
- **Close the Art. 50(2) contest:** content-marking binds **2 Aug 2026 for us** *only when we ship AI-generated media*; for a P0 text-relay chat it is narrow. Keep AI-interaction disclosure (2 Aug 2026) as the firm EU P0 gate. Keep Omnibus "provisional pending Official Journal" `[VERIFY]`. (Finding 4.)
- **Decide the minors/companion-persona gate (§9.11)** — it is now the primary live US compliance determinant. (Finding 13.)

### P1 (strengthen before external/GTM use)
- **Add the $100 mid-Pro tier and the retention-by-price-band data**; use both to inform the §9.1 Pro-price decision. Strongly consider a **CC-gated reverse trial** to lift conversion above the <$50/mo churn trap. (Findings 6, 7.)
- **Sharpen the privacy claim** to "ahead of incumbent consumer defaults (which train-by-default)" while keeping the no-"confidential" guardrail. (Finding 8.)
- **Adopt a T3-style rolling short-window credit bucket + monthly overage** as the candidate P0 metered-overage UX (smooths bursty usage); ensure credits map to true USD/token cost (transparency wedge). (Theme A, Finding 11.)

### P2 (track, no immediate change)
- **Live-track regulatory dates** (EU Official Journal for the Omnibus; CA SB 243 guidance; SB 26-189 ADMT rulemaking) rather than locking them.
- **Watch OpenRouter's BYOK fee-model change** (5% usage → possible fixed sub) for $0-markup economics. (Finding 12.)
- **Monitor the ads signal** (OpenAI's "no trust impact" claim vs Perplexity's withdrawal) for any "revisit at scale" reconsideration. (Finding 15.)

---

## 7. Open questions

1. **Do we ship any AI-generated media in scope where Art. 50(2) marking attaches at 2 Aug 2026?** P0 appears to be text-relay only (no own synthetic media) → marking obligation narrow. Confirm with legal that relaying provider model output with attribution does not itself trigger 50(2) marking. (The Article 50(2) text targets providers of systems *generating* synthetic content.)
2. **Does CA SB 243 bite us at all** if we explicitly do **not** offer companion personas and do **not** target minors? If excluded, the only firm US obligation is generic AI-interaction disclosure (which we already do).
3. **Where exactly do we price** given the <$50/mo → 23% GRR cliff and the >$250/mo → 70% GRR ceiling? Is ~$15–20 the worst-of-both-worlds middle, or defensible with strong activation + privacy? (Needs a cost model + cohort plan.)
4. **Reverse trial vs freemium?** CC-gated reverse trial converts ~30% vs freemium ~2.6–8% — but raises acquisition friction for the power-user/dev persona. Test?
5. **Does the OpenRouter fixed-subscription-fee transition** (when it lands) break the $0-markup BYOK promise economics? Contingency?
6. **Is the EU Omnibus final text (Official Journal)** going to move any Art. 50 date again before our launch window? Currently provisional.
7. **Could ChatGPT's $100 mid-Pro / Google's $100 Ultra** pull the market's "power-user" price gravity toward $100, reshaping where our band sits relative to "value"?

---

## 8. Sources (accessed 2026-05-27)

**Competitor pricing**
- ChatGPT pricing — https://chatgpt.com/pricing/ ; https://www.cloudzero.com/blog/how-much-does-chatgpt-cost/ ; Pro $100 launch — https://fritz.ai/chatgpt-pricing/
- Claude pricing — https://claude.com/pricing ; https://mem0.ai/blog/anthropic-claude-pricing
- Gemini/Google AI — https://one.google.com/about/google-ai-plans/ ; https://9to5google.com/2026/05/25/google-ai-plus-pro-ultra-gemini-features/ ; https://blog.google/products-and-platforms/products/google-one/google-ai-subscriptions/
- Perplexity — https://www.finout.io/blog/perplexity-pricing-in-2026 ; https://www.perplexity.ai/max
- Copilot — https://github.blog/news-insights/company-news/github-copilot-is-moving-to-usage-based-billing/ ; https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals ; https://visualstudiomagazine.com/articles/2026/04/27/devs-sound-off-on-usage-based-copilot-pricing-change.aspx
- Mistral — https://mistral.ai/pricing ; https://www.cloudzero.com/blog/mistral-api-pricing/
- T3 Chat (new credit model) — https://x.com/theo/status/2022844310165893484 ; https://useautumn.com/blog/working-with-t3-chat-on-a-new-way-of-pricing ; https://t3.chat/faq ; (old model) https://x.com/theo/status/1887000229922353524
- Poe — https://help.poe.com/hc/en-us/articles/19945140063636-Poe-Purchases-FAQs ; https://costbench.com/software/ai-chatbots/poe/
- DeepSeek — https://api-docs.deepseek.com/quick_start/pricing
- OpenRouter BYOK — https://openrouter.ai/announcements/1-million-free-byok-requests-per-month ; https://openrouter.ai/pricing ; https://openrouter.ai/announcements/simplifying-our-platform-fee

**Credit-economy pivot**
- Metronome 2026 trends — https://metronome.com/blog/2026-trends-from-cataloging-50-ai-pricing-models
- Anthropic usage-based — https://www.infoworld.com/article/4171274/anthropic-puts-claude-agents-on-a-meter-across-its-subscriptions.html ; https://www.implicator.ai/anthropic-shifts-enterprise-billing-to-per-token-pricing-the-flat-fee-era-is-over/
- Cursor / coding tools — https://www.developersdigest.tech/blog/ai-coding-tools-pricing-2026 ; https://wilico.co.jp/en/blog/end-of-flat-rate-ai-github-copilot-llm-billing-shift

**Retention / economics**
- AI churn wave / GRR-NRR by price band — https://chartmogul.com/reports/saas-retention-the-ai-churn-wave/ ; https://www.growthunhinged.com/p/the-ai-churn-wave
- AI gross margin — https://www.softwareseni.com/why-ai-gross-margins-are-so-much-lower-than-saas-and-what-that-means-for-your-business/ ; https://www.saasmag.com/ai-cogs-saas-gross-margin-compression/
- Free→paid conversion — https://www.growthunhinged.com/p/free-to-paid-conversion-report ; https://firstpagesage.com/seo-blog/saas-freemium-conversion-rates/
- Inference whales — https://interestingengineering.substack.com/p/priced-to-scale-priced-to-fail-how ; https://www.implicator.ai/claudes-rate-limits-arent-a-capacity-problem-theyre-a-math-problem/ ; https://benzatine.com/news-room/the-rising-costs-of-ai-coding-startups-grapple-with-inference-whales

**Compliance — EU AI Act**
- Art. 50 — https://artificialintelligenceact.eu/article/50/ ; Art. 99 penalties — https://artificialintelligenceact.eu/article/99/
- Omnibus / Art. 50 dates — https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/ ; https://www.mofo.com/resources/insights/251201-eu-digital-omnibus ; https://plesner.com/en/news/ai-act-august-2026-what-expect-delayed-standards-pending-guidance-and-digital-omnibus-ai ; https://www.addleshawgoddard.com/en/insights/insights-briefings/2026/technology/ai-omnibus-provisional-agreement-changes-eu-ai-act-delayed-deadlines/
- Council provisional agreement (May 7 2026) — https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/ ; https://www.hoganlovells.com/en/publications/eu-legislators-agree-to-delay-for-highrisk-ai-rules
- Penalties context — https://www.holisticai.com/blog/penalties-of-the-eu-ai-act

**Compliance — US state laws**
- CA AB 2013 — https://www.crowell.com/en/insights/client-alerts/californias-ab-2013-requires-generative-ai-data-disclosure-by-january-1-2026 ; https://www.goodwinlaw.com/en/insights/publications/2026/01/alerts-otherindustries-californias-ab-2013-takes-effect
- CA SB 243 — https://www.orrick.com/en/Insights/2026/04/2026-State-Chatbot-Laws-Key-Provisions-and-Regulatory-Trends ; https://www.kslaw.com/news-and-insights/new-state-ai-laws-are-effective-on-january-1-2026-but-a-new-executive-order-signals-disruption
- CO SB 205 stay + SB 26-189 — https://www.theemployerreport.com/2026/05/ai-regulation-on-hold-in-colorado-but-employer-risk-isnt/ ; https://www.hklaw.com/en/insights/publications/2026/05/colorado-governor-signs-sb-189 ; https://coloradosun.com/2026/05/12/colorado-ai-law-rewrite-passes/ ; https://www.cooley.com/news/insight/2026/2026-04-24-state-ai-laws-where-are-they-now
- Federal preemption EO — https://www.whitehouse.gov/presidential-actions/2025/12/eliminating-state-law-obstruction-of-national-artificial-intelligence-policy/ ; https://www.mofo.com/resources/insights/251213-executive-order-state-ai-laws ; https://datamatters.sidley.com/2025/12/23/unpacking-the-december-11-2025-executive-order-ensuring-a-national-policy-framework-for-artificial-intelligence/

**Ads / privacy**
- Perplexity drops ads — https://www.macrumors.com/2026/02/18/perplexity-abandons-ai-advertising/ ; https://almcorp.com/blog/perplexity-ai-abandons-advertising-2026-analysis/
- OpenAI ads — https://openai.com/index/our-approach-to-advertising-and-expanding-access/ ; https://theaiinsider.tech/2026/02/26/openai-begins-advertising-rollout-in-chatgpt-as-it-tests-new-revenue-model/ ; https://techsifted.com/posts/chatgpt-ads-pilot-2026/
- Incumbent privacy defaults — https://techcrunch.com/2025/08/28/anthropic-users-face-a-new-choice-opt-out-or-share-your-data-for-ai-training/ ; https://www.anthropic.com/news/updates-to-our-consumer-terms ; https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data
