# Research & Review — PRD 04 Technical Architecture

**Domain:** Technical Architecture
**Date:** 2026-05-27
**Reviewer:** Senior software architect (fresh-research + critical PRD review pass)
**Scope reviewed:** `/home/user/agent/docs/prd/04-technical-architecture.md` (framed by `/home/user/agent/docs/prd/00-product-overview.md`)
**Method:** Live web verification of every then-proposed stack component against May-2026 sources (npm dist-tags, vendor docs with `lastUpdated` stamps, GitHub issues, legal analyses). All claims cited with URL + access date (2026-05-27 unless noted).

> **Superseded implementation note (2026-06 housekeeping):** this is a dated
> research artifact for the original Vercel-native AI SDK / Better Auth /
> Drizzle / Upstash architecture. The shipped implementation is now documented
> in PRD 04, `AGENTS.md`, and `api/README.md`: Next.js FE on Vercel, same-origin
> `/api/*` rewrite to FastAPI on Fly, SQLAlchemy/Alembic on Neon, custom
> signed-cookie auth, DeepSeek via the OpenAI-compatible adapter, and optional
> Sentry/OpenTelemetry. Treat the stack-specific claims below as historical
> research context, not current implementation truth.

---

## 1. Summary

- **The originally researched Vercel-native stack was sound and current as of May 2026, but it is no longer the shipped implementation.** Next.js 16 (now 16.2.6), AI SDK v6 (now `latest` = 6.0.191, GA 2025-12-22), Better Auth (1.6.11), Postgres/Drizzle, Upstash, Vercel Fluid Compute, Langfuse v4 + OTel — every load-bearing version claim in that PRD framing was verified true or conservatively framed. Current implementation truth lives in PRD 04 and ops docs.
- **Two version-framing items have moved and the PRD lags reality:** (1) **AI SDK v7 is in active public beta** (`7.0.0-beta.116`, daily canaries, v7.0 milestone opened 2026-04-01) — the PRD treats v6→v7 as a distant "horizon," but it is the *next* migration and is closer than implied. (2) **Vercel Workflows / `DurableAgent` is now GA** (100M+ runs since Oct-2025 beta), not the "P1 horizon" the PRD describes — still correctly *scoped out* of the text-core MVP, but it is shipped tech now, not a research bet.
- **The EU AI Act content-marking question has materially shifted and should be re-flagged, not left as a generic "Aug 2 vs Dec 2" standoff.** The **7 May 2026 Digital Omnibus provisional agreement** keeps interaction-disclosure at **2 Aug 2026** and points content-marking/watermarking (Art. 50(2)) at **2 Dec 2026** (with grandfathering for pre-Aug-2 systems *still unconfirmed*). The PRD already flags this provisional agreement generically (§5.7) and its instinct ("keep the `[VERIFY]` flag, legal owns it") is correct — what this review adds is the now-public *specifics* (the 7-May dates and the Dec-2 marking read), not a correction of a PRD that was unaware of it.
- **The streaming/resumable-stream design is the strongest part of the PRD and is well-supported by primary sources** — the abort-semantics inversion, the dedicated stop endpoint, the orphaned-run reaper, and the known resume bugs (#13160 still open) all check out against AI SDK docs and live GitHub issues.
- **Real gaps for a lean billable MVP:** (a) **no message-send idempotency key** (only QStash job idempotency is specified) — a P0 billing-consistency hole given the per-message cost ledger; (b) **billing-vs-stream-failure atomicity is under-specified** (when is `cost_usd` written relative to partial/aborted streams?); (c) **ZDR is Pro/Enterprise-only and a paid add-on** — the PRD leans on it as a privacy control but doesn't acknowledge it is unavailable on Hobby and costs real money; (d) Edge runtime is now effectively **deprecated** on Vercel, which strengthens the PRD's Node choice but the PRD still frames Edge as a live "alternative."
- **Minor citation/precision errors:** the OWASP LLM10 reference URL points at the LLM01 slug; the ZDR fee is "$0.10 per 1,000 requests" (not "per 1,000 *successful* requests" — that wording belongs to the provider-allowlist add-on); the PRD names ZDR on Pro/Enterprise but doesn't flag that it is **unavailable on Hobby**, nor distinguish the two ZDR modes (per-request ZDR is free on Pro/Ent; team-wide ZDR is the metered $0.10/1k one).
- **Verdict: ship-ready architecture with disciplined adapter strategy.** The biggest risks are (1) AI SDK churn velocity (v6 ships multiple patch releases per week; v7 looming), (2) billing/idempotency edge cases, and (3) EU compliance timing — all addressable without re-architecting.

---

## 2. Stack verification (May 2026)

| Component | PRD claim | Current reality (source) | Verdict |
|---|---|---|---|
| **Next.js** | Next.js 16, App Router + Cache Components/PPR as rendering baseline | **16.2.6** (docs `lastUpdated` 2026-05-19). Cache Components GA; PPR is now the *default* behavior under `cacheComponents: true`; `experimental.ppr`/`experimental_ppr` **removed**. [nextjs cacheComponents](https://nextjs.org/docs/app/api-reference/config/next-config-js/cacheComponents) | **ok** |
| **proxy.ts (Node)** | `proxy.ts` on Node runtime is the successor to deprecated Edge `middleware.ts` | Confirmed: `proxy.ts` replaces `middleware.ts`, runs **Node-only** (runtime not configurable), `middleware.ts` deprecated and slated for removal. [nextjs proxy](https://nextjs.org/docs/app/api-reference/file-conventions/proxy) | **ok** |
| **async cookies()/headers()/params** | These are async in Next.js 16; `await` in every Better Auth read | Confirmed in the v16 upgrade guide. [v16 upgrade](https://nextjs.org/docs/app/guides/upgrading/version-16) | **ok** |
| **Vercel AI SDK** | v6, GA 2025-12-22; `Output.object()`; `generateObject`/`streamObject` deprecated; `Agent`/`ToolLoopAgent`; `needsApproval` HITL; stable MCP | npm `latest` = **6.0.191** (2026-05-22). GA **2025-12-22** confirmed. All named primitives confirmed. [npm `ai`](https://www.npmjs.com/package/ai), [ai-sdk-6 blog](https://vercel.com/blog/ai-sdk-6) | **ok** |
| **AI SDK v7** | "migration discipline now points at v6→v7 (early signal, horizon only)" | **v7 is in active public beta** (`7.0.0-beta.116`; canary.154 on 2026-05-27; v7.0 milestone opened 2026-04-01). Not a distant horizon — it is the *next* upgrade. Vendor expects "very little friction." [vercel/ai #12999 / #14011](https://github.com/vercel/ai/issues/14011) | **stale framing** |
| **Transport: SSE** | SSE is the AI SDK default; correct for chat | 2026 consensus has *inverted* to "SSE by default unless you need bidirectional." Strongly validated. [procedure.tech SSE](https://procedure.tech/blogs/sse-for-llms/), [hivenet](https://www.hivenet.com/post/llm-streaming-sse-websockets) | **ok** |
| **Resumable streams** | Vercel `resumable-stream` + Upstash Redis pub/sub; abort semantics invert; known bugs #13160/#11865 | Confirmed: client aborts = disconnects under resume; dedicated stop endpoint required; **abort + resume are mutually exclusive** per AI SDK troubleshooting. **#13160 still OPEN** (Mar 2026; fix PR #13829 in review). [resume-streams docs](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams), [abort-breaks-resumable-streams](https://ai-sdk.dev/docs/troubleshooting/abort-breaks-resumable-streams), [#13160](https://github.com/vercel/ai/issues/13160) | **ok (watch #13160)** |
| **Fluid Compute duration** | 300s default all plans; max 800s Pro/Enterprise; >300s requires Pro/Ent | Exactly confirmed (docs `last_updated` 2026-05-14): Hobby 300/300, Pro 300/800, Enterprise 300/800. [duration docs](https://vercel.com/docs/functions/configuring-functions/duration) | **ok** |
| **Vercel Workflows / DurableAgent** | "P1 horizon," Vercel-proprietary, durable execution | **Now GA** (vendor-reported 100M+ runs, 500M+ steps, 1,500+ customers since Oct-2025 beta). `DurableAgent` from `@workflow/ai` is shipped. Still correctly scoped out of MVP. [durable-execution blog](https://vercel.com/blog/a-new-programming-model-for-durable-execution), [workflows docs](https://vercel.com/docs/workflows) | **ok (under-stated maturity)** |
| **Edge vs Node runtime** | Run chat route on Node; Edge listed as portability "alternative" | Vercel now **recommends migrating off Edge to Node**; Edge Functions effectively deprecated; both run on Fluid Compute. Node choice is *more* correct than PRD implies. [runtimes docs](https://vercel.com/docs/functions/runtimes), [leerob](https://x.com/leerob/status/1780705942734331983) | **ok (Edge framing stale)** |
| **Better Auth** | Committed; anonymous→link plugin; Auth.js dropped (security-patch-only) | **1.6.11** (2026-05-12), stable 1.x. Anonymous plugin + `onLinkAccount` confirmed; recent 2026 security hardening (OAuth 2.1, PKCE, invitation-takeover fixes). **No formal third-party audit found.** [better-auth changelog](https://better-auth.com/changelog), [anonymous plugin](https://better-auth.com/docs/plugins/anonymous) | **ok (no audit — note)** |
| **Postgres host (Neon/Supabase)** | Neon (Databricks-owned, runs independently) cut pricing materially in 2026; Drizzle | Confirmed: post-Databricks (May-2025) Neon cut storage $1.75→$0.35/GB-mo, compute −15–25%, free tier 50→100 CU-hrs. Neon scales-to-zero (50–500ms resume). Drizzle commonly paired with Neon. [neon pricing 2026](https://vela.simplyblock.io/articles/neon-serverless-postgres-pricing-2026/), [neon vs supabase](https://www.closefuture.io/blogs/neon-vs-supabase) | **ok** |
| **Upstash Redis + QStash** | HTTP/REST Redis (no pooling); QStash retries/DLQ/idempotent | Architecture sound; no contradicting evidence. `resumable-stream` supports Upstash via generic Redis interface. [resumable-stream repo](https://github.com/vercel/resumable-stream) | **ok** |
| **BYOK envelope encryption** | Fresh DEK/record, AES-256-GCM, KMS-wrapped KEK, never log, never in system prompts | Matches 2026 best practice verbatim (fresh per-record DEK, AES-GCM, KEK never leaves KMS, never persist plaintext DEK). [GCP envelope encryption](https://docs.cloud.google.com/kms/docs/envelope-encryption), [AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html) | **ok** |
| **Observability: Langfuse v4 + OTel** | Langfuse v4 OTel-native; self-host needs ClickHouse+PG+Redis/S3; prefer cloud for MVP | Confirmed: Langfuse v4 OTel-native, ClickHouse-backed; **acquired by ClickHouse in 2026**; self-host upgrade path "still in development"; OTel GenAI semconv still **experimental**. Cloud-tier-for-MVP advice is sound. [langfuse OTEL](https://langfuse.com/integrations/native/opentelemetry), [clickhouse acquires langfuse](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability) | **ok** |
| **AI Gateway ZDR + BYOK** | ZDR covers Anthropic/OpenAI/Google "and more" (2026-04-06); ~$0.10/1k successful req; BYOK zero-markup | ZDR coverage + date confirmed. BYOK zero-markup confirmed. **Fee is "$0.10 per 1,000 requests" (not "successful"); team-wide ZDR is Pro/Enterprise-only; per-request ZDR is free on Pro/Ent.** [gateway pricing](https://vercel.com/docs/ai-gateway/pricing), [ZDR changelog](https://vercel.com/changelog/zero-data-retention-no-prompt-training-on-ai-gateway) | **ok (precision/availability nits — see §4)** |
| **EU AI Act Art. 50 dates** | Interaction-disclosure ~Aug 2 2026; content-marking contested (Aug 2 vs Dec 2); May-2026 provisional amendment | Disclosure **2 Aug 2026** (unchanged). Content-marking now points at **2 Dec 2026** per 7-May-2026 Digital Omnibus; grandfathering for pre-Aug-2 systems **unconfirmed**; agreement **provisional pending Official Journal**. [Orrick Digital Omnibus](https://www.orrick.com/en/Insights/2026/05/EUs-Digital-Omnibus-on-AI-7-Key-Changes-You-Need-to-Know), [Art. 50](https://artificialintelligenceact.eu/article/50/) | **stale facts — see §4 Q1** |
| **OWASP LLM Top 10 (2025)** | LLM10 Unbounded Consumption; LLM01 injection; LLM07 system-prompt leakage | All current (2025 list). **Cited URL for LLM10 is wrong slug** (points at LLM01). Correct: `/llmrisk/llm102025-unbounded-consumption/`. [genai.owasp LLM10](https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/) | **ok (citation error)** |

---

## 3. New ideas & developments (online research)

### Theme A — Framework / SDK velocity

- **AI SDK v7 is already in beta (not a far horizon).** `7.0.0-beta.116` published; v7.0 milestone opened 2026-04-01; canaries shipping daily. Maintainers say upgrade friction should be "very little" — the main driver of the major bump is the strict `@ai-sdk/provider` spec (any change to it is technically breaking). ([vercel/ai #14011](https://github.com/vercel/ai/issues/14011), [#12999](https://github.com/vercel/ai/issues/12999); accessed 2026-05-27)
  - **Implication for us:** Pin to `ai@6.x` exactly as the PRD says, **and** budget a v7 upgrade in the P1 window. Keep the provider adapter thin enough that v7 is a 1-day codemod (`npx @ai-sdk/codemod`), not a sprint. Track v7's stabilization before any agent/tool work hardens against v6-specific signatures.
- **AI SDK v6 has a fast patch cadence** (≈3–5 patch releases/week — indicative, inferred from npm release timestamps; 6.0.191 by 2026-05-22). ([npm `ai` time](https://www.npmjs.com/package/ai); accessed 2026-05-27)
  - **Implication:** lockfile + Renovate/Dependabot with a manual gate; don't float `^6`.
- **Next.js 16.2.x is the current line; PPR/Cache Components fully GA and default.** `<Activity>`-based state preservation on navigation is new and relevant for chat (preserves composer/scroll state when navigating between chats). ([cacheComponents docs](https://nextjs.org/docs/app/api-reference/config/next-config-js/cacheComponents); accessed 2026-05-27)
  - **Implication:** the "static shell instant + streamed chat pane" claim is real and supported; also leverage `<Activity>` for fast chat-to-chat switching without losing in-progress composer text.

### Theme B — Durable execution is now production tech

- **Vercel Workflows GA + `DurableAgent` (`@workflow/ai`)** turns each LLM call/tool invocation into a durable, individually-retried/checkpointed step with the full function timeout per step, surviving deploys/crashes. ([durable-execution blog](https://vercel.com/blog/a-new-programming-model-for-durable-execution), [DurableAgent](https://useworkflow.dev/docs/api-reference/workflow-ai/durable-agent); accessed 2026-05-27)
  - **Implication for us:** the PRD already names this as the strategic answer to the orphaned-run/long-stream problem and gates it behind the runtime adapter — good. Update the framing from "P1 horizon / research bet" to "GA, deliberately deferred." When the P1 tool/agent loop lands, this is the leading candidate to *replace* the hand-rolled resumable-stream + reaper + QStash trio with one model. Note the proprietary lock-in (Temporal + AI SDK is the portable equivalent — [Temporal blog](https://temporal.io/blog/building-durable-agents-with-temporal-and-ai-sdk-by-vercel)).

### Theme C — Streaming transport consensus solidified

- **"SSE by default" is now the explicit industry default for LLM chat**, with WebSockets reserved for bidirectional needs (voice, collab, interrupts). ([procedure.tech](https://procedure.tech/blogs/sse-for-llms/), [flowverify 2026 guide](https://www.flowverify.co/blog/sse-websockets-polling-guide-2026); accessed 2026-05-27)
  - **Implication:** PRD's transport decision is fully vindicated; the §4.2 deferral of WebSockets/Durable Objects to voice/collab is the textbook call.
- **EventSource caveat worth a build note:** native `EventSource` is GET-only and can't set custom headers; AI SDK's `DefaultChatTransport` sidesteps this by using `fetch`-based POST. ([transport docs](https://ai-sdk.dev/docs/ai-sdk-ui/transport); accessed 2026-05-27)
  - **Implication:** don't roll a raw `EventSource` client for auth'd streams — use the AI SDK transport (the PRD's "wire through the hook surface, not ad-hoc fetch" rule, §5.1, already covers this; make it explicit that this is *why*).

### Theme D — Data layer economics shifted toward Neon

- **Post-Databricks Neon cut prices materially in 2026** (storage $1.75→$0.35/GB-mo; compute −15–25%; free tier doubled). Scale-to-zero with 50–500ms resume. ([neon pricing 2026](https://vela.simplyblock.io/articles/neon-serverless-postgres-pricing-2026/); accessed 2026-05-27)
  - **Implication:** the PRD's open question (Neon vs Supabase) now tilts toward **Neon** for a Drizzle-first, no-bundled-backend stack — unless we standardize on Supabase for Auth+RLS+Realtime synergy (the only scenario the PRD allows Supabase Auth). Decide the *data-platform identity* first; the Postgres host falls out of it.

### Theme E — Privacy controls are now purchasable, with caveats

- **AI Gateway ZDR** covers Anthropic/OpenAI/Google + more (2026-04-06), **but**: team-wide ZDR is **Pro/Enterprise-only** at **$0.10/1,000 requests**; per-request ZDR is free on Pro/Ent; **not available on Hobby**. ([gateway pricing](https://vercel.com/docs/ai-gateway/pricing); accessed 2026-05-27)
  - **Implication:** ZDR is a real, hardening privacy control for the no-train wedge — but it presupposes a paid Vercel plan and adds a per-request cost. Fold into COGS, and do **not** market "ZDR" as a baseline guarantee until the plan/coverage is locked. The no-train wedge must still rest primarily on provider DPAs/API modes, with ZDR as defense-in-depth.

### Theme F — Compliance landscape (EU AI Act) moved under the PRD's feet

- **7 May 2026 Digital Omnibus provisional agreement** (Council + Parliament): interaction-disclosure stays **2 Aug 2026**; high-risk deadlines pushed to 2027/2028; **content-marking/watermarking (Art. 50(2)) now generally read as 2 Dec 2026**, with grandfathering for pre-Aug-2 systems *explicitly unclear*. Must be adopted + published in the Official Journal before 2 Aug 2026 to take effect. ([Orrick](https://www.orrick.com/en/Insights/2026/05/EUs-Digital-Omnibus-on-AI-7-Key-Changes-You-Need-to-Know), [Latham](https://www.lw.com/en/insights/ai-act-update-eu-resolves-to-change-rules-and-extend-deadlines), [Consilium press release](https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/); accessed 2026-05-27)
  - **Implication:** this supplies the *specifics* behind the provisional agreement the PRD already cited generically (§5.7). The "contested Aug 2 vs Dec 2" is now better characterized as: **disclosure = firm Aug 2; marking = likely Dec 2 but legally unsettled (grandfathering + Official Journal pending).** The PRD's "keep `[VERIFY]`, legal decides" posture remains correct; the *facts* in §5.7/§9 can be updated with these dates (see §4 Q1).
- **US state law remains a launch-gate** (PRD 00 §10): CA SB 243 + AB 2013 (live 1/1/26), CO SB 205 (enforce 6/30/26). Interaction-disclosure is a US gate too, independent of EU dates. (Cross-referenced; PRD 05 owns.)
  - **Implication:** the disclosure hook (§5.7) is needed regardless of EU outcome — reinforces building it now.

### Theme G — Idempotency for billable LLM endpoints is a recognized 2026 pattern

- 2026 best-practice writing treats **idempotency keys + dedup tables + bounded retries + DLQ** as table stakes for billable LLM pipelines, precisely because retries multiply token cost and a runaway loop can burn thousands in minutes. ([tianpan.co idempotency](https://tianpan.co/blog/2026-04-20-idempotency-llm-pipelines), [buildmvpfast](https://www.buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026); accessed 2026-05-27)
  - **Implication:** the PRD specifies job idempotency (QStash) but **not request-level idempotency on the message-send path** — a gap given the per-message cost ledger is the billing spine (see §4 [gap]).

---

## 4. PRD review findings

> Tagged `[error]` (factually wrong / stale), `[gap]` (missing), `[inconsistency]`, `[scope]` (over/under-engineering), `[risk]`.

### High priority

- **[gap] No message-send idempotency key (§5.1 / §5.6 / §6).** The PRD designs job-level idempotency (QStash, §5.6) but the *client→/api/chat send* path has none. With network retries, double-clicks, optimistic-send replays (PRD 00 lists "optimistic send + offline draft/queue"), and `regenerate()`, a single user intent can spawn duplicate assistant turns — each writing a `message` row and decrementing `usage_rollup.usd_spent_platform`/credits. This is a direct **billing-consistency** hole given `message.cost_usd` is the live ledger and the metering hook.
  - **Action:** add a client-generated idempotency key (e.g. `client_message_id` UUID) on send; unique-constrain it per chat; dedupe in the route handler before any provider call or ledger write. Surface in §5.1 contract and §6 (`message.client_message_id text unique-per-chat`).

- **[gap] Billing-vs-stream-failure atomicity is unspecified (§5.1 / §5.6 / §6).** The PRD says partial output is persisted on abort/error and that `cost_usd` powers budget enforcement, but never states **when** `cost_usd` / `usage_rollup` is written relative to a stream that fails mid-flight, nor how partial-token usage is metered. Risk: bill-for-nothing (charge then stream dies) or stream-for-free (tokens consumed, never metered) — the classic "billing vs stream failure consistency" problem.
  - **Action:** define the order-of-operations explicitly: capture provider usage from the AI SDK `onFinish`/lifecycle (covers `completed`/`stopped`/`error`/`interrupted` — the PRD already emits these terminal events in §5.1), write the ledger in the *same* transaction/step that finalizes the `message`+`stream` row, and reconcile via the reaper for orphaned runs. Partial usage (provider-reported tokens on abort) must still be metered. Add an AC.

- **[error/stale] AI SDK v7 is mischaracterized as a distant "horizon" (§4 AI-orchestration row; Risk #3; §10).** v7 is in **active public beta** (May 2026), not an "early signal." The PRD's mitigation (pin v6, isolate behind adapter, read migration guides) is right, but the framing understates how soon v6→v7 lands.
  - **Action:** reword to "v7 in beta as of May 2026; plan the v6→v7 codemod in P1; do not float `^6`." Pin exact versions.

- **[error/stale] EU AI Act content-marking facts in §5.7/§9 predate the 7-May-2026 Digital Omnibus (Q1).** The PRD presents Aug 2 vs Dec 2 as an open contest and cites a "May 2026 provisional agreement... reshuffling deadlines" without its content. The agreement is now public: disclosure firm at **Aug 2 2026**; marking generally **Dec 2 2026**; grandfathering unclear; pending Official Journal.
  - **Action:** keep the `[VERIFY]` flag (correct), but **update the facts**: state the Omnibus outcome, that disclosure is now *firm* (build the disclosure hook as P0, not contingent), and that marking is *likely Dec 2 but legally unsettled*. Reconcile with PRD 05 (whose ~Dec-2026 reading is now the *more* likely one — the conflict has narrowed in PRD 05's favor).

- **[gap/risk] ZDR availability + cost not fully stated (§4 deploy row; §5.7).** The PRD does name ZDR on **Pro/Enterprise**, but omits that it is **unavailable on Hobby**, does not distinguish the **two ZDR modes** (per-request ZDR is free on Pro/Ent; team-wide ZDR is metered), and the fee is "per 1,000 requests" (the PRD says "successful requests" — that phrasing is the *provider-allowlist* add-on, not ZDR).
  - **Action:** correct the wording; note ZDR presupposes a paid Vercel plan; keep provider DPAs/no-train API modes as the *primary* control with ZDR as defense-in-depth. Fold the per-request fee into the cost-per-message KPI (the PRD already says to do this — just make the plan-gating explicit).

### Medium priority

- **[inconsistency] Duplicate BYOK-gate + Grok-gating bullets in §5.2.** The two bullets "**[P0/MVP] BYOK UI gate**" and "**[P0/MVP] Grok registry gating**" are each repeated verbatim (lines ~173–176). Harmless but signals copy-paste drift.
  - **Action:** delete the duplicates.

- **[error] OWASP LLM10 citation points at the wrong slug (§5.6).** The Unbounded-Consumption reference links `genai.owasp.org/llmrisk/llm01-prompt-injection/` (that's LLM01).
  - **Action:** fix to `genai.owasp.org/llmrisk/llm102025-unbounded-consumption/`.

- **[stale] Edge runtime framed as a live alternative (§4 deploy/transport rows; §5.8).** Vercel now recommends migrating *off* Edge to Node; Edge Functions are effectively deprecated. The PRD's Node choice is *more* correct than it claims, but listing Edge as an "alternative" is dated.
  - **Action:** note Edge is deprecated on Vercel; the real portability escape hatch is Cloudflare Workers/DO (already named), not Vercel Edge.

- **[gap] No explicit rate-limit story for the BYOK proxy path's *abuse* dimension vs the resumable-stream Redis cost (§5.6).** §5.6(d) covers agent-loop circuit-breaking, but the resumable-stream layer adds its own Redis-cost amplification (one INCR+SUBSCRIBE per stream, more on resume) that a malicious client could trigger by repeatedly connecting/disconnecting. Minor, but the abuse surface of "every disconnect spawns a buffered stream" deserves a line.
  - **Action:** add a per-user cap on concurrent/active streams (the `unique active stream per chat` index helps, but a user-level cap across chats is missing) and a Redis-buffer size/TTL bound.

- **[gap] Better Auth has no third-party security audit (verified) — auth is the hardest-to-migrate dependency.** The PRD commits to Better Auth and flags the guest-link spike (good), but doesn't note the absence of a formal external audit as a residual risk for an auth lib that owns password hashes + the anonymous→linked graph.
  - **Action:** add to Risk table / §9: "Better Auth has frequent self-published security patches but no public third-party audit as of May 2026 — monitor advisories; the guest-link spike is the gating de-risk."

### Lower priority / scope

- **[scope — appropriately lean] The P0/P1 split is well-calibrated.** Deferring resumable *replay*, attachments, tools, RAG, voice, and WebSockets to P1/P2 is the right lean-MVP posture and is internally consistent with PRD 00's decisions log. No over-engineering found in the P0 core. The one thing modeled-but-not-built that earns its keep is the **typed multi-part `message.parts`** schema (D7) — correctly P0-schema / P0-partial-render.

- **[scope — watch] `routing_decision jsonb` + `substitution_reason` + served/requested model fields (§6 message table) are rich for a text-core MVP** where Auto-routing is "heuristic" (PRD 00). Not wrong (the transparency contract D6 demands it), but ensure PRD 02 actually populates these in P0 or they become dead columns. Cross-PRD contract is sound; just verify the producer ships.

- **[gap — minor] `audit_log` is "[P1 design, P2 enforce]" but several P0 actions (key_add, export, delete) are security-sensitive.** For a privacy-first product, capturing BYOK key add/revoke and export/delete in the audit log from P0 is cheap and defensible.
  - **Action:** consider pulling *write-only* audit logging for key/export/delete events into P0 (no UI needed); it's a few inserts and materially strengthens the privacy/GDPR story.

- **[inconsistency — cosmetic] §6 `message.cost_usd numeric(14,8)`** is fine, but `cost_breakdown jsonb` carrying the *authoritative* tiered/cached/promo detail while `cost_usd` is a derived scalar means the two can drift. Ensure `cost_usd` is always computed *from* `cost_breakdown` (single source of truth), not written independently.
  - **Action:** document the derivation rule in §6 (PRD 02 owns the pricing math; PRD 04 stores both; `cost_usd = f(cost_breakdown)`).

---

## 5. Recommendations (prioritized)

### P0 (before/at MVP build)
1. **Add request-level idempotency** to the message-send path (`client_message_id`, unique-per-chat, dedupe before provider call + ledger write). Closes the billing double-charge hole.
2. **Specify billing-vs-stream-failure atomicity**: meter from AI SDK lifecycle `onFinish`, write ledger in the same finalize transaction as `message`+`stream`, meter partial usage on abort, reaper reconciles orphans. Add ACs.
3. **Update EU AI Act facts (§5.7/§9 Q1)** to reflect the 7-May-2026 Digital Omnibus: disclosure firm Aug 2 (build the hook as unconditional P0); marking likely Dec 2 but unsettled; keep `[VERIFY]`; reconcile the now-narrowed conflict with PRD 05.
4. **Correct ZDR framing**: Pro/Enterprise-only, paid add-on, "$0.10/1,000 requests"; keep provider DPAs as the primary no-train control; fold ZDR fee into COGS.
5. **Pin exact AI SDK + Next.js versions** (no `^`); add a renovate gate; reword v7 as "imminent beta, P1 upgrade."
6. **Fix the two duplicate bullets and the OWASP LLM10 URL** in §5.2/§5.6.
7. **Pull write-only audit logging for key-add/revoke + export/delete into P0** (privacy-first product; cheap).

### P1 (fast-follow, design now)
8. **Evaluate Vercel Workflows / `DurableAgent` (now GA)** to replace the hand-rolled resumable-stream + reaper + QStash trio when the tool/agent loop lands; keep the runtime adapter so Temporal/Restate stay portable.
9. **Plan the v6→v7 codemod** in the P1 window; validate the provider adapter survives the `@ai-sdk/provider` spec change.
10. **Track AI SDK resume bug #13160** (and #11865) before enabling `resume: true`; gate resumable replay on the fix landing in a pinned `6.x`.
11. **Add a per-user concurrent/active-stream cap** + Redis-buffer TTL/size bound (resumable-stream abuse surface).

### P2 (later / decision-gated)
12. **Resolve the data-platform identity** (Neon vs Supabase) — decide *whether* we want Supabase's bundled Auth/RLS/Realtime; if not, Neon's 2026 pricing tilts the Postgres-host choice to Neon. Don't decide the host in isolation.
13. **Self-hosted Langfuse** only if cloud-tier cost/data-residency forces it; the ClickHouse+PG+Redis/S3 ops burden is real and the self-host v4 upgrade path is still maturing.

---

## 6. Open questions

1. **EU content-marking (legal sign-off, unchanged owner).** Will the Digital Omnibus be published in the Official Journal before 2 Aug 2026, and will pre-Aug-2 systems be grandfathered for Art. 50(2)? If we launch in the EU before Aug 2, are we a "pre-market" system (Dec 2 grace) or not? *Legal must answer; do not lock P0 EU marking scope on the architecture's read.*
2. **Where is the per-message cost computed and by whom at request time?** PRD 02 owns pricing math, PRD 04 stores it — but the *runtime* call that turns provider token usage + the pricing table into `cost_breakdown`/`cost_usd` before the ledger write isn't owned explicitly. Whose code runs it in the hot path?
3. **Is Auto-routing's `routing_decision` actually populated in P0**, or is it a reserved-but-empty column until P1 tools/router? (Affects whether the transparency UI has anything to show.)
4. **Do we need ZDR at launch, or do provider DPAs + no-train API modes suffice for the MVP privacy claim?** ZDR forces a paid Vercel plan + per-request fee; the no-train wedge may not require it on day 1.
5. **Postgres host decision** depends on the unresolved "are we a Supabase shop?" question — still open per PRD 04 §9.2.
6. **Vercel max-duration `[confirm at build]`** is now confirmed (300/800) — this open question (§9.3) can be *closed*.

---

## 7. Sources

All accessed 2026-05-27 unless noted.

**Next.js 16**
- https://nextjs.org/docs/app/api-reference/config/next-config-js/cacheComponents (docs lastUpdated 2026-05-19; Next 16.2.6)
- https://nextjs.org/docs/app/api-reference/file-conventions/proxy
- https://nextjs.org/docs/app/guides/upgrading/version-16
- https://nextjs.org/blog/next-16

**Vercel AI SDK**
- https://www.npmjs.com/package/ai (npm `latest` 6.0.191; v7 beta 7.0.0-beta.116; dist-tags verified via `npm view ai`)
- https://vercel.com/blog/ai-sdk-6 (GA 2025-12-22)
- https://github.com/vercel/ai/issues/14011 ; https://github.com/vercel/ai/issues/12999 (v7 pre-release)
- https://ai-sdk.dev/docs/ai-sdk-ui/transport ; https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat
- https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams
- https://ai-sdk.dev/docs/troubleshooting/abort-breaks-resumable-streams
- https://github.com/vercel/ai/issues/13160 (OPEN, Mar 2026; fix PR #13829) ; https://github.com/vercel/ai/issues/8390 ; https://github.com/vercel/ai/issues/11865
- https://github.com/vercel/resumable-stream

**Vercel platform (Fluid Compute, Gateway, Workflows, runtimes)**
- https://vercel.com/docs/functions/configuring-functions/duration (lastUpdated 2026-05-14; Hobby 300/300, Pro/Ent 300/800)
- https://vercel.com/docs/ai-gateway/pricing (lastUpdated 2026-05-22; ZDR $0.10/1k req, Pro/Ent; BYOK zero-markup)
- https://vercel.com/changelog/zero-data-retention-no-prompt-training-on-ai-gateway
- https://vercel.com/docs/ai-gateway/capabilities/zdr
- https://vercel.com/blog/a-new-programming-model-for-durable-execution ; https://vercel.com/docs/workflows ; https://useworkflow.dev/docs/api-reference/workflow-ai/durable-agent
- https://vercel.com/docs/functions/runtimes ; https://x.com/leerob/status/1780705942734331983 (Edge→Node)
- https://temporal.io/blog/building-durable-agents-with-temporal-and-ai-sdk-by-vercel

**Streaming transport**
- https://procedure.tech/blogs/sse-for-llms/ ; https://www.hivenet.com/post/llm-streaming-sse-websockets ; https://www.flowverify.co/blog/sse-websockets-polling-guide-2026

**Auth**
- https://better-auth.com/changelog (v1.6.11, 2026-05-12) ; https://better-auth.com/docs/plugins/anonymous ; https://workos.com/blog/top-better-auth-alternatives-secure-authentication-2026

**Data layer**
- https://vela.simplyblock.io/articles/neon-serverless-postgres-pricing-2026/ ; https://www.closefuture.io/blogs/neon-vs-supabase

**BYOK / KMS**
- https://docs.cloud.google.com/kms/docs/envelope-encryption ; https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html ; https://oneuptime.com/blog/post/2026-02-12-kms-envelope-encryption/view

**Observability**
- https://langfuse.com/integrations/native/opentelemetry ; https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability ; https://langfuse.com/blog/2026-03-10-simplify-langfuse-for-scale

**Idempotency / reliability**
- https://tianpan.co/blog/2026-04-20-idempotency-llm-pipelines ; https://www.buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026 ; https://redis.io/blog/what-is-idempotency-in-redis/

**Security (OWASP)**
- https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/ ; https://genai.owasp.org/llm-top-10/

**EU AI Act**
- https://artificialintelligenceact.eu/article/50/
- https://www.orrick.com/en/Insights/2026/05/EUs-Digital-Omnibus-on-AI-7-Key-Changes-You-Need-to-Know
- https://www.lw.com/en/insights/ai-act-update-eu-resolves-to-change-rules-and-extend-deadlines
- https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/
- https://verifywise.ai/blog/eu-ai-act-omnibus-what-changed
- https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content
