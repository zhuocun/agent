# 2026-05-27 Research & PRD-Review Synthesis

**What this is.** The integrating document for a fresh online research pass (current as of May 2026) plus a critical review of the existing PRD set (PRDs 00–08). Five domain workstreams each did (A) comprehensive online research for new ideas and (B) a skeptical review of their PRD(s); every workstream artifact then passed through an independent senior reviewer before this synthesis. The per-workstream reports are the detail; this document frames the headline verdict, the cross-cutting findings, the integration conflicts, and a single prioritized action list.

> **Superseded implementation note (2026-06 housekeeping):** the W4
> architecture research reviewed the then-proposed Vercel-native AI SDK /
> Better Auth / Drizzle / Upstash stack. The shipped implementation is now the
> split Vercel FE + FastAPI/Fly API + SQLAlchemy/Alembic/Neon stack documented
> in PRD 04, `AGENTS.md`, and `api/README.md`.

**Method / provenance.** Orchestrated as five parallel research+review workers → five independent reviewers (all top-tier, high-reasoning) → orchestrator integration. **All five reviews returned `pass`** with only minor, precise corrections; those corrections have been folded back into each report (see §5). Sources with access dates live in each report's `## Sources` section.

| # | Workstream | Report | Reviewer verdict |
|---|---|---|---|
| W1 | Core chat UX, design system, error/limit states (PRD 01/06/08) | [`01-core-chat-ux.md`](01-core-chat-ux.md) | pass (a11y attribution corrected) |
| W2 | AI capabilities, model layer, transparency contract (PRD 02/07) | [`02-ai-capabilities-transparency.md`](02-ai-capabilities-transparency.md) | pass (schema-claim tightened) |
| W3 | Mobile & cross-platform (PRD 03) | [`03-mobile-cross-platform.md`](03-mobile-cross-platform.md) | pass (two sourcing caveats hedged) |
| W4 | Technical architecture (PRD 04) | [`04-technical-architecture.md`](04-technical-architecture.md) | pass (ZDR / EU framing tightened) |
| W5 | Roadmap, monetization, metrics, compliance (PRD 05) | [`05-roadmap-monetization-compliance.md`](05-roadmap-monetization-compliance.md) | pass (EU label / Gemini price reframed) |

---

## 1. Headline verdict

**The PRD set is unusually current and well-reasoned, and is build-ready after a focused set of corrections.** All five workstreams independently reached the same conclusion: the 2026-05-27 review pass that produced these PRDs already absorbed most of what fresh research surfaces (AI SDK v6, Opus 4.7 tokenizer, GPT-5.5 long-context surcharge, DeepSeek repricing, the credit-economy pivot, branching-is-standard, metered pricing, token-first design). This is **not** a rewrite. It is a short list of factual corrections, one genuine cost-schema gap, a few P0 billing/idempotency and accessibility fixes, and a handful of opportunistic pull-forwards.

The most important single finding per domain:

- **W1 (UX):** the streaming **accessibility announce model** is the highest-value fix — and a11y is our cited differentiation wedge. Get the live-region semantics right and add two cheap "beat-the-leader" ACs.
- **W2 (model layer):** the **transparency cost-accounting schema (PRD 07 §4.1) has one real, high-stakes gap** — a single `threshold_tier` scalar cannot correctly express the real 2026 long-context pricing models. This is the core wedge; a wrong number here is wrong on exactly the high-value turns.
- **W3 (mobile):** no architectural rework; the PRD's hard calls (visualViewport-primary, disk-proportional storage, server-side Web Speech) hold. A few platform facts went stale; the virtualizer choice is a spike.
- **W4 (architecture):** the then-proposed Vercel-native stack verified as current and sound at the time, but has since been superseded by the shipped split architecture. The durable findings were **billing-consistency** (message-send idempotency key; billing-vs-stream-failure atomicity), which connect directly to the transparency ledger and are now reflected in PRD 04.
- **W5 (GTM/compliance):** **two factual compliance errors** (EU Art. 50 penalty tier; Colorado SB 205 is dead) and a stale T3 Chat anchor; the metered-credit thesis (D8) is vindicated and now mainstream; the privacy wedge is **stronger** than the PRD claims.

---

## 2. Cross-cutting findings (where workstreams reinforce each other)

These are the threads that span multiple PRDs and deserve a single owner / coordinated edit.

1. **The transparency contract is the spine, and three workstreams independently stress-tested it.**
   - W2: the cost schema can't express Gemini's stepped per-band rates, OpenAI's whole-session reprice (which itself needs *two* multipliers — ×2 input / ×1.5 output, not one scalar), or Anthropic's flat-to-1M as a positive fact; reasoning tokens are never cache-eligible; dated promos need effective dates.
   - W4: the per-message `cost_usd` ledger has **no idempotency key** and **unspecified write-vs-stream-failure atomicity** — so the schema can be perfect and still be double-charged or never charged.
   - W1: the per-message cost/model display and the **guest model-downgrade** surface are where the contract becomes visible to users.
   - **Integration implication:** PRD 06's "transparency contract = one P0 cross-cutting workstream with one named owner" (D6) is exactly right; these findings should be handed to that one owner as a bundle, not split across PRD 02/04/07 reviewers.

2. **Privacy-first is a *live* differentiator, not enterprise parity — and it's purchasable but plan-gated.**
   - W5 + W2 both found incumbents now **train on consumer chats by default** (opt-out), while paid Western APIs are no-train-by-default. Our consumer/prosumer no-train-by-default is genuinely ahead of incumbent *consumer defaults* — PRD 05 §7.3 under-sells this.
   - W4 adds the guardrail: gateway **ZDR is Pro/Enterprise-only and metered**, so the no-train wedge must rest primarily on provider DPAs/API modes with ZDR as defense-in-depth — don't market ZDR as a baseline guarantee.

3. **Gateway-native, no-train routing is now a platform feature we can enforce (not negotiate).** W2 verified Vercel AI Gateway's team-wide ZDR + no-prompt-training controls (Apr 2026) and gateway-native search; W4 verified the same with the cost/plan caveat. Together they de-risk PR-1 (no-train enforcement) and make **W2's "MVP-lite grounded search" pull-forward** (gateway-native, ~one line) a credible candidate for W5's roadmap.

4. **Streaming smoothness has a named mechanism across web *and* mobile.** W1 and W3 converge on the identical production pattern: buffer tokens in a ref, flush once per `requestAnimationFrame`, `scheduler.yield()` to protect INP (optionally `startTransition`). The PRDs set the 60fps/INP *target* (PRD 01 §5.4) but omit the *mechanism* — adopt it as the implementation note in both PRD 01 and PRD 03.

5. **Compliance is live-tracked, not locked — and one date genuinely conflicts between workstreams (see §3).**

---

## 3. Integration conflict to resolve (do NOT let a reviewer or the orchestrator decide this)

**EU AI Act Art. 50(2) content-marking date for a *new* launch — W4 and W5 disagree, and it's a legal call.**

- **W4** reads the 7-May-2026 Digital Omnibus as pointing content-marking at **~2 Dec 2026** (grandfathering for pre-Aug-2 systems unconfirmed).
- **W5** reads it as **no grace for a new product → binds 2 Aug 2026** (the ~Dec-2026 grace being pre-existing-systems-only).

**What both agree on (safe to treat as settled):** (a) AI-**interaction disclosure** (Art. 50(1)) is **firm at 2 Aug 2026** — build the disclosure hook as unconditional P0; (b) the Omnibus is **provisional pending Official Journal**; (c) content-**marking** only bites **if/when we ship AI-generated media** — for a P0 text-relay chat with attribution it is narrow either way.

**Resolution path:** this is the kind of ambiguity the product-owner policy says route to the named owner / legal, not the architecture's or orchestrator's read. **Action: legal sign-off on the marking date before EU-launch scope is locked; until then, ship the firm disclosure hook and design marking to attach to any future media-gen.** (Flagged in PRD 00 §12, PRD 04 §9 Q1, PRD 05 §9.6.)

---

## 4. Prioritized action list (consolidated across workstreams)

### P0 — correctness / on-wedge / cheap, do before build or PRD-lock

**Transparency contract (one owner — D6 bundle):**
- Fix the long-context **cost-schema** (PRD 07 §4.1 / PRD 02 §5.2): support (a) whole-session multiplier *with separate in/out factors* (OpenAI), (b) stepped per-band base rates (Gemini), (c) flat/no-surcharge as a surfaceable positive fact (Anthropic); add `tier_scope`. *(W2 T1/A3)*
- Specify **reasoning tokens are never cache-eligible**; add a golden test. *(W2 T3/A10)*
- Define **request/session cost-scope** attribution so the meter-reconciliation AC is testable. *(W2 T2/T5)*
- Add **dated-promo `effective_until`** (DeepSeek 2026-05-31 reversion is the golden fixture). *(W2 T4)*
- Expand `data_policy` to route-level (`train_default opt_in|opt_out|never`, `retention_days`, `data_residency`, `zdr_available`). *(W2 A4)*
- Align substitution **triggers ↔ reason codes** (add `capacity_reroute`). *(W2 T6/C1)*

**Billing consistency (PRD 04):**
- Add a **message-send idempotency key** (`client_message_id`, unique-per-chat, dedupe before provider call + ledger write). *(W4)*
- Specify **billing-vs-stream-failure atomicity** (meter from `onFinish`, write ledger in the finalize transaction, meter partial usage on abort, reaper reconciles orphans). *(W4)*

**Accessibility & UX (PRD 01/06/08):**
- Fix the **streaming announce model**: the streamed text node must NOT be a live region; status-only polite region + a success-path completion announcement (currently unspecced in both PRDs). *(W1 — corrected after review)*
- Add two **measured-leader ACs**: accessible keyboard-shortcuts dialog + sidebar landmarks. *(W1)*
- Add the **rAF token-batching + `scheduler.yield()` + `rehype-harden`** mechanisms behind the 60fps/security targets (PRD 01 §5.4; mirror in PRD 03). *(W1/W3)*
- Add a **guest model-downgrade transparency** surface (silent downgrade is an own-goal for a transparency product). *(W1)*
- Move error-payload counts/reset into `meta` (i18n/live); spec a `retry_after`/`reset_at` countdown. *(W1)*

**Compliance corrections (PRD 05 / PRD 00):**
- EU Art. 50 penalty is **€15M/3%** (Art. 99), not €35M/7% (that's the Art. 5 prohibited-practices tier). *(W5)*
- **Drop Colorado SB 205** as a live US gate: stayed Apr 27 2026, repealed/replaced by SB 26-189 → Jan 1 2027, narrowed to ADMT (a chat product likely out of scope). Rest the US disclosure argument on CA SB 243 (companion/minors) + good practice. *(W5)*
- Resolve the **Art. 50(2) marking** flag per §3 above (legal sign-off; disclosure hook is the firm P0 gate). *(W4/W5)*
- Decide the **minors / companion-persona gate** — now the primary live US compliance determinant. *(W5)*

**Stack hygiene (PRD 04):**
- Pin exact AI SDK + Next.js versions (no `^`); reword AI SDK **v7 as imminent beta + P1 codemod** (not a distant horizon). *(W4)*
- Fix the duplicate BYOK/Grok bullets and the OWASP LLM10 citation slug. *(W4)*
- Correct ZDR framing: names Pro/Enterprise but flag Hobby-unavailable; distinguish per-request-free vs team-wide-metered. *(W4)*

### P1 — fast-follow / strengthen

- **Pull-forward candidate:** gateway-native grounded search as an MVP-lite mode (near-zero to wire). *(W2 A8 → W5 roadmap)*
- Elevate **answer-first / progressive-disclosure** layout (now an incumbent default). *(W1)*
- Wire shipped **AI SDK 6 primitives** (`MessageBranch*`, `needsApproval` HITL) instead of "design now." *(W1)*
- Reframe the **reasoning-effort toggle as a hint** the provider may override. *(W1)*
- `supports_structured_output` as a 3-value enum; mark Anthropic `beta` until GA. *(W2 A1)*
- Add `tokenizer_ref` to the registry (Opus 4.7 +12–35% token divergence). *(W2 A6)*
- Add the **$100 ChatGPT "mid-Pro" tier** + the retention-by-price-band data (`<$50/mo → ~23% GRR`) to the Pro-price decision; consider a CC-gated reverse trial. *(W5 — corrected: Google AI Ultra $100/$200 already in PRD)*
- Sharpen the **privacy claim** to "ahead of incumbent consumer defaults." *(W5)*
- Steal **T3's rolling short-window bucket + monthly overage** UX for the metered-overage primitive; credits map to true USD/token cost. *(W5)*
- Evaluate **Vercel Workflows / DurableAgent (now GA)** to replace the hand-rolled resumable-stream + reaper + QStash when the tool/agent loop lands. *(W4)*

### P2 — design-ahead / track

- Virtualizer **spike** with three co-equal candidates (Virtua / VirtuosoMessageList / TanStack Virtual), validated **inside a Capacitor WebView** on mid-tier Android. *(W3)*
- Make the **server-authoritative vs local-first** choice an explicit, owned PRD 04 decision (it interacts with the privacy story). *(W3)*
- Resolve the **data-platform identity** (Neon vs Supabase) before picking the Postgres host (Neon's 2026 repricing tilts toward Neon absent a Supabase-Auth decision). *(W4)*
- Live-track regulatory dates (EU Official Journal; CA SB 243 guidance; SB 26-189 ADMT rulemaking); watch OpenRouter's BYOK fee-model change. *(W5)*

---

## 5. Review corrections folded in (audit trail)

Each reviewer returned `pass`; the precise corrections they flagged were applied to the source reports:

- **W1:** corrected an a11y attribution — the Claude teardown documents the *inverse* bug (content not in a live region → nothing announced); the token-by-token re-reading is an anti-pattern from the article's comments + general guidance. Noted PRD 08 §9's "announce once" is scoped to *errors* only, so the success-path completion announcement is unspecced in both PRDs.
- **W2:** tightened the §4.1 schema framing (even OpenAI's session reprice needs two multipliers, not one scalar) and reconciled a DeepSeek Pro-vs-Flash raw-thinking-token inconsistency.
- **W3:** hedged the iOS-haptics "patched in 26.5" claim (community sources, no primary release note) and flagged the TanStack chat-support capability as single-source/two-days-old (the spike arbitrates).
- **W4:** corrected the ZDR availability framing (PRD does state Pro/Enterprise; the gap is Hobby-exclusion + the two ZDR modes) and the EU-Act "PRD lags reality" overstatement (the PRD already cited the provisional agreement generically; this adds the dated specifics); tagged vendor-reported figures.
- **W5:** downgraded the Art. 50(2) status label from "VERIFIED" to "provisional pending Official Journal" and reframed the "Gemini AI Ultra $100 unmentioned" finding (the PRD already lists ~$99.99/~$200; the genuinely-new item is ChatGPT Pro $100).

## 6. Residual risks / known gaps

- **Date-sensitive single-source claims** remain in the mobile report (iOS haptics patch version; the two-day-old TanStack post) — now hedged; resolve empirically in the relevant spikes, don't cite as settled platform facts.
- **The EU Art. 50(2) marking date is unresolved by design** (§3) — it needs legal, not engineering.
- A few model facts are flagged **`[verify-at-build]`** in W2 (Anthropic structured-outputs GA/beta status; Gemini 3.1 Pro context window; unconfirmed `gpt-5.4-pro` ID; gateway-search "$5/1K" figure) — registry seed data, verify at build.
- Reviewers could not browse, so live-pricing and version figures were judged for sourcing discipline and internal consistency, not re-fetched ground truth.
