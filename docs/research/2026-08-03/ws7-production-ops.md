# WS7 — Production engineering & operations

**Scope:** the runtime substrate an agent executes on and the policy layer around it — durability, streaming/resume/cancel, HITL machinery, cost and latency, tenant isolation, identity and governance, degrade behaviour, rollout. | **Access date: 2026-08-03** (every source retrieved this session) | **Deferred to:** **WS3** tool/sandbox *interface* design and injection specifics; **WS6** eval and tracing *semantics*; **WS2** topology choice.

---

## 1. Executive summary

1. **[high] Durable execution won the long-running loop, and the trigger is infrastructure churn — provider outages, pod replacement, node loss — not multi-day waits.** Cursor's work-stealing beta ran at "one 9"; Temporal took it "past two 9s" and handles >50M actions/day across >7M workflows [S1] — vendor self-report.
2. **[high] Resume-from-offset is a first-party protocol feature.** OpenAI pairs `background: true, stream: true` with a `sequence_number` and a `?starting_after=N` reconnect [S8]; AG-UI models resumption as a new run carrying a `resume` array [S19].
3. **[high] The approval prompt is a measurably weak control, per the vendor that measured it.** Anthropic telemetry: **~93% of permission prompts approved**; an OS-level sandbox cut prompts **84%**; a February 2026 internal red-team phish got Claude to exfiltrate `~/.aws/credentials` in **24 of 25 retries** [S16]. Experienced users auto-approve ~2× as often, shifting to drift-watching.
4. **[high] An egress allowlist is a capability grant, not a destination filter.** Cowork's allowlist correctly passed `api.anthropic.com`, and an attacker's API key planted in a workspace file got user files uploaded into the attacker's account — "the sandbox worked perfectly, and yet the data was exfiltrated" [S16].
5. **[high] Prompt caching is a rate-limit lever before a cost lever.** Claude cache reads mostly skip ITPM, so 2M ITPM at an 80% hit rate passes ~10M input tokens/minute; reads cost 0.1×, 1-hour writes 2× [S11, S12]. OpenAI's `prompt_cache_key` moved one customer from 60% to 87% hit rate, though each prefix+key pair saturates near ~15 RPM [S14].
6. **[medium] Agent identity has stable plumbing and no live consent standard.** RFC 8693 covers server-side delegation; front-channel consent naming the agent is what `draft-oauth-ai-agents-on-behalf-of-user-02` adds — Informational, **expired 2026-02-27** [S20].
7. **[high] The EU AI Act's 2026 shape settled, and it is mostly not about autonomy.** The AI Omnibus (Regulation (EU) 2026/1744) entered force 2026-07-27, moving Annex III high-risk to **2027-12-02** and Annex I to **2028-08-02**; general application and enforcement stayed 2026-08-02 [S22, S23]. For a general assistant the binding near-term duty is disclosure, not an autonomy tier.

---

## 2. Findings

### 2.1 Runtime substrate: what durable execution buys and costs

- **Two families.** *Journal-and-replay* (Temporal, Restate) records steps and reconstructs state on recovery; Inngest's `step.run()` is quickest from app code but bills per step [S6]. *Actor-with-durable-state* (Cloudflare Durable Objects) gives an addressable agent, SQLite, zero compute while hibernated and fiber recovery after eviction [S4, S5].
- **Buys [high]:** outputs replayed not re-called, tools not re-run, approvals not re-requested, waits durable not compute-consuming; the history doubles as an audit log [S2, S6].
- **Costs [high]:** determinism, and payload limits that bite fat agents — Temporal warns at 256 KB, errors at 2 MB, caps gRPC at 4 MB, and **terminates** past 51,200 events or 50 MB of history [S2, S3]. Hence claim-check codecs, idempotency, and versioning work — Cursor replaced eternal workflows with short task-scoped ones [S1, S6].

### 2.2 Streaming and the UX protocol

- SSE remains the default. AG-UI standardises the event vocabulary — run/step lifecycle, text, tool calls, snapshot-plus-delta state — and 2026 adds activity events for plans and progress, so a reconnecting client renders a snapshot then resyncs [S19].
- Constraints: no new stream from a background response not created with `stream: true` [S8]; OpenAI's EU region forbids `background=True`, so residency can silently remove your resume mechanism [S15].
- **Cancel needs three states:** *disconnected* (keep running, buffer), *cancelled* (stop, release budget, terminal event), *paused for approval* (durable, zero compute, resumable by token). Conflating them is the commonest product bug; OpenAI makes the first two explicit, cancel idempotent [S8]. **[high]**

### 2.3 Human-in-the-loop machinery

- **Settled mechanism.** LangGraph's `interrupt()` suspends at the call site, persists via the checkpointer, waits **indefinitely** [S7]. OpenAI's Agents SDK records an *interruption* instead of executing the tool, returning a serialisable resumable `state` [S9]. Claude's SDK evaluates hooks → deny → ask → mode → allow → `canUseTool`; auto-approved tools never reach that callback, so per-call audit belongs in a `PreToolUse` hook [S17, S18]. Gate selection follows a per-tool risk rating: write access, reversibility, permissions, financial impact [S10].
- **Four traps.** *Durability illusion* — LangGraph's examples use `InMemorySaver`, so a pending approval dies with the process. *Idempotency* — on resume the node restarts from its beginning, so writes before the `interrupt` fire twice [S7]. *Gate placement* — input guardrails cover only a chain's first agent and output guardrails only the last, so validation belongs beside the side-effecting tool [S9]. *Inherited privilege* — `bypassPermissions`/`auto` can't be overridden per subagent [S17].
- Approvals need a **timeout with a defined expiry action** plus an audit record; no retrieved vendor doc gives a default, and in the cloud "the cost of blocking is much higher" [S1]. **[medium]**

### 2.4 Cost and latency engineering

- **Cache layout:** stable content first, dynamic last, no timestamp or user id in the prefix; the 1-hour TTL covers approval waits where a 5-minute cache evicts [S11]. One cookbook run of 2,300 prompts put cached TTFT 7% faster at 1,024 tokens and 67% faster at 150k+ — reporter OpenAI, no model version or date given, so shape credible, magnitudes indicative [S14].
- **Backpressure:** 429 `rate_limit_error` is your limit (honour `retry-after`; `anthropic-ratelimit-*` says whether RPM, ITPM or OTPM tripped), 529 `overloaded_error` is fleet-wide [S12, S13]. Retry with capped exponential backoff and **full jitter**, bounded, at one layer, idempotent only — no-jitter backoff is the measured worst case [S28], and SDKs already retry, so an app-level loop is a second layer by default [S13].
- **Failover** belongs in the gateway, which sees every provider and key: fallback buys independent failure domains but "the same prompt can behave differently on the fallback model", so restrict it to an ordered config-defined target chain, put failover events on the request trace, and validate the fallback's output [S31]. Attribute per-run cost as a sum of parts, since a caching regression hides inside a token total [S11, S14].

### 2.5 Concurrency, isolation, secrets

- **The fairness stack**, in order: rate limiter (admission, plus early rejection when the queue already can't meet the request's latency target), performance tier, **deficit round robin** with a per-tenant quantum debited by request cost, then priority → deadline → arrival ordering *inside* each tenant. Keeping urgency per-tenant rather than global is load-bearing: one org's 10,000 queued requests no longer sit in front of another's five [S29]. **[high]** for the pattern.
- **The budget unit is unresolved.** Cohere calls request-based budgeting "suboptimal for generative endpoints" — a 100K-token prompt can cost orders of magnitude more than a 1K one — yet still uses it there, reserving token-based budgeting for batched endpoints because streaming wants roughly one request per tenant per rotation; the named ideal is a feedback loop on an EMA of token-normalised cost [S29]. Anthropic's public limits are token-shaped [S12]. **[medium]**
- **Sandbox ladder**, three Anthropic shapes: ephemeral gVisor container per session; OS-level sandbox (bubblewrap/Seatbelt) with writes confined to the workspace and network denied by default; local VM with credentials in the host keychain. "The weakest layer is the one you built yourself" — gVisor and seccomp held, the custom proxy failed [S16]. Cursor adds VM hibernate/resume and checkpoint/restore/fork [S1].
- **Secrets:** keep credentials outside the sandbox and broker them, the proxy admitting only provenance-verified requests; resolve symlinks before path validation [S16]. Read a firewall's stated limits — GitHub's covers only Bash-tool processes in the Actions appliance and "sophisticated attacks may bypass" it [S30].

### 2.6 Identity, authorization, governance

- **EU AI Act** (dates in §1.7): Article 14, high-risk only, reads like an engineering spec — oversight commensurate with "the risks, level of autonomy and context of use", humans able to *remain aware of automation bias*, override output, and "interrupt the system through a 'stop' button… that allows the system to come to a halt in a safe state" [S21]. Automation bias is the 93%-approval finding arriving from the regulatory side. **[high]**
- **NIST:** COSAiS is writing SP 800-53 overlays with single- and multi-agent use cases — concept paper 2025-08-14, annotated outline 2026-01-08, so agent overlays remain upstream of a final [S24]; CSA's interim AI RMF Agentic Profile meanwhile adds autonomy tiering and delegation-chain monitoring [S25].
- **OWASP:** the Top 10 for Agentic Applications (2025-12-09) is the threat-model taxonomy; mine rather than WS3's are ASI03 privilege abuse, ASI08 cascading failures, ASI09 trust exploitation and ASI10 rogue agents — defended by per-agent scoped short-lived credentials, blast-radius isolation with breakers, forced confirmation and behavioural monitoring [S26, S27].
- **Residency:** OpenAI's controls are project-scoped and fixed at creation, carry a **10% uplift** for eligible models released on or after 2026-03-05, cover storage at rest in-region, and remove `background=True` in the EU [S15] — storage-at-rest and in-region processing are separate promises. **[high]**

### 2.7 Failure, degrade modes, SLOs

- **The degrade ladder:** stop scheduling new actions → return partial results already produced → say what tripped and which parts are incomplete → escalate if a gate exists → never discard completed work. Hard stop suits cost runaway and confirmed injection; a soft limit that warns and degrades the model suits latency overruns, and a global kill switch belongs beside the per-task one [S32].
- **Trip conditions must be plural, because each metric misses a class:** token count alone misses cheap endless loops, step count alone misses few-but-expensive tool calls. One worked set is 50k tokens and $0.50 per task, 30 steps, 3 failures in 5 attempts, 10 minutes per session, plus loop detection on a hash of recent tool calls; thresholds derive from the production p95. Every stop writes a structured log — trigger, measured value and threshold, task/user/trace id, hard-or-soft and what followed, timestamp — since a breaker with no log can't be tuned [S32]. **[medium]**
- **Poison pills** get no vendor coverage: a run failing deterministically on replay retries forever under a durable engine's default policy, so bound retries per activity *and* per run, and quarantine rather than re-queue. **[low]** — inference, not sourced.
- **SLOs:** consensus on *vocabulary*, none on *numbers*. Availability → task success rate; latency → TTFT plus end-to-end completion including HITL wait; errors → escalation rate; cost → tokens per task; plus a **judgement SLI** from human override and correction rate, which needs no ground-truth labels [S33]. Every target found (99.5% availability, <800 ms p95 TTFT, ≥97% tool-call success) comes from consultancy posts with no disclosed population, model version or harness — **[low]**; baseline a week and derive your own [S34]. Emit on OpenTelemetry GenAI conventions; semantics are WS6's.

### 2.8 Rollout practice

- **The gate sequence:** offline regression suite as a hard block → **shadow** on mirrored traffic, the candidate reasoning normally while every write-action call is intercepted as a dry run → **canary** on pre-registered gates over rolling windows (say, error rate not rising more than 1% absolute over 30 minutes with ≥500 requests) → stepped ramp → automatic rollback. Risk-tier it: prompt wording is bounded, a new tool changes tool selection everywhere, a model swap touches every reasoning step [S35].
- **Ship an immutable versioned bundle** — model, prompt, tool schemas, retrieval config, guardrails — referenced by id outside application code, so rollback lands on the next request with no redeploy [S35].
- **Rollback needs session pinning plus graceful drain:** version hash on the session, sessions kept on it during rollback, in-flight ones finishing under a max-session timeout. Without it a five-step plan finishes later steps on a version it didn't start on — "for long-running agent workflows this isn't an edge case; it's the common case during rollback" [S35]. Offline replay has a validity limit: stale context whenever the agent depends on real-time external state. **[medium]** — practitioner consensus, not primary-measured.

---

## 3. Delta since 2026-07-14

The prior pass ([S36]) covered this one level up — durable agents for background automation rather than chat, HITL as durable pause states, hard bounds as code invariants, OTel span trees. All of it holds. What changed:

1. **The durability trigger moved from "long waits" to "provider and infrastructure churn".** Cursor's reasons apply well below the prior "exceeds request or worker lifetime" threshold, with corrections: short task-scoped workflows, decoupled loop/machine/conversation state, client-side rewind on retried steps [S1].
2. **New here:** resumable streaming and durable interrupts as protocol features [S8, S19]; caching as a rate-limit multiplier [S11, S12, S14]; the quantified failure of approval gating [S16]; per-tenant fair scheduling with cost-debited quanta [S29]; the judgement SLI [S33]; session-pinned canaries [S35]; the identity and regulatory layer [S20]–[S27], where the AI Omnibus is in force with enforcement from 2026-08-02 [S22, S23].
3. **Permission detail sharpened into fan-out risk.** Subagent inheritance of `bypassPermissions`/`auto`, plus guardrails running only at chain edges, mean a topology decision (WS2's) silently changes the safety posture of every tool call [S9, S17]. Relatedly, gateway failover *is* silent model substitution unless traced and restricted to a declared target chain [S31].

---

## 4. Contested / open questions

| Question | Confidence | Notes |
| --- | --- | --- |
| Durable engine vs application checkpoints for in-turn fan-out | **medium** | Cursor's evidence is hours-to-weeks agents on dedicated VMs, not a chat turn; engine costs are documented [S1, S2, S3]. |
| Oversight or theatre? | **medium–high** that gating alone fails | 93% approval points to containment-first [S16]; Article 14 still mandates *effective* oversight for high-risk systems [S21]. |
| Approval timeout defaults, and failover under a model-transparency promise | **open** on both | No retrieved vendor doc specifies a timeout; LangGraph waits indefinitely by design [S7] while Cursor notes blocking is expensive [S1]. Failover trades independent failure domains against silent behaviour change [S31]. |
| When NIST overlays become procurement-relevant | **medium** | COSAiS moved concept paper → annotated outline; agent overlays still ahead [S24]. CSA's is a consortium artifact [S25]. |
| The fair-share cost unit for generative traffic | **open** | Cohere names request-based budgeting suboptimal for generative endpoints yet ships it there for streaming interleaving, and names an EMA of token-normalised cost as the ideal it hasn't adopted [S29]. |
| Whether a delegation consent protocol lands, and whether SLO *targets* exist | **low** on both | The on-behalf-of draft is Informational and expired without WG adoption [S20]; SLO vocabulary converged but every published number is consultancy-sourced [S33, S34]. |

---

## 5. Anti-patterns & failure modes

| Anti-pattern | Why it fails | Prefer |
| --- | --- | --- |
| In-memory checkpointer; non-idempotent work before `interrupt()` | Approval dies with the process; the node restarts on resume, so charges fire twice [S7] | Durable checkpointer, idempotency keys, gate before side effects |
| Eternal workflows | Versioning becomes intractable as history nears the termination limit [S1, S2] | Short task-scoped workflows |
| Allowlist as destination filter; trusting a firewall's stated coverage | Every capability behind an allowed domain is reachable [S16]; GitHub's covers only Bash-tool processes [S30] | Capability-scoped brokering proxy, credentials never inside, assume bypass |
| Retries at several layers, no jitter, 429 treated like 529 | No-jitter backoff is the measured worst case, SDKs already retry, only 429 carries a trustworthy `retry-after` [S12, S13, S28] | One layer, full jitter, distinct 429/529 policies |
| Timestamp or user id in the cached prefix; one global queue ordered by priority alone | Breaks prefix matching, collapsing the ITPM ceiling [S11, S14]; one tenant's burst becomes every tenant's latency [S29] | Stable prefix first, hit rate as an SLI; per-tenant queues, cost-debited quanta, urgency inside the tenant |
| Single-metric caps; a stop with no structured log or partial | Token count alone misses cheap endless loops, step count few-but-expensive calls; with no trigger/value/threshold record the breaker can't be tuned [S32] | Combined token/cost/step/error/time triggers, soft limit first, labelled partials |
| Fan-out inheriting parent permissions | Subagents inherit `bypassPermissions`/`auto`; edge guardrails miss inner calls [S9, S17] | Per-subagent least privilege, validation at the tool |
| Canary without sticky routing; assuming residency is uniform | Threads flip version mid-run and rollback strands sessions [S35]; storage-at-rest ≠ in-region processing [S15] | Version hash on the session with drain; demand both residency promises |

---

## 6. Design implications

Normative; each with rationale and tradeoff.

1. **Default to in-turn orchestration with a resumable event stream; adopt a durable engine only when runs outlive the process** — engine costs are concrete, benefits accrue across process boundaries [S1, S2, S3]. *Tradeoff:* you hand-roll retry and idempotency discipline, and migrating later is a real project.
2. **Make the event stream the contract:** monotonic sequence numbers, replay-from-offset, snapshot+delta plan state, three terminal states [S8, S19]. *Tradeoff:* buffer retention scales with fan-out volume.
3. **Gate on containment and server-issued ids, treat approval as a supplement, broker every credential** — 93% approval and approved-domain exfiltration mean supervision and hostname allowlists can't carry the load [S16]. *Tradeoff:* containment costs capability, and the broker is custom code — the layer the vendor found weakest.
4. **Design the prompt as a cache artifact and treat hit rate as an SLI** — caching is at once a 10×-cheaper read, a TTFT cut and an ITPM multiplier [S11, S12, S14]. *Tradeoff:* prefix stability constrains where personalisation sits, making prompt edits a scheduled invalidation event.
5. **Encode caps as runtime invariants — not prompt instructions — combining token, cost, step, error-rate and time triggers behind a labelled-partial degrade path** [S32]. *Tradeoff:* more visible partial outcomes, and thresholds need a p95 baseline before they can be trusted.
6. **Route model traffic through one gateway owning retries, failover, per-tenant fair queueing with cost-aware quanta and substitution logging, and make fan-out privilege explicit rather than inherited** [S9, S13, S17, S28, S31]. *Tradeoff:* the gateway is a single point of failure needing load-testing under backpressure; the fair-queueing cost unit is unsettled [S29]; and per-subagent policy is more configuration to keep correct.
7. **Ship changes as an immutable model+prompt+tools+retrieval bundle behind a flag — offline → shadow → sticky canary → ramp, session-pinned on rollback — and log the delegation chain (user, client, agent) per consequential action** [S20, S26, S35]. *Tradeoff:* shadow doubles inference cost on its slice and needs a per-tool dry-run mode; the consent protocol is unratified, so the delegation wire format will change.

---

## 7. Sources

All retrieved 2026-08-03; vendor posts are primary reports of their own systems. 35 external sources plus the prior-pass memo.

| # | Source · org · type | URL |
| --- | --- | --- |
| S1 | Lessons building cloud agents · Cursor 2026 · self-report | https://cursor.com/blog/cloud-agent-lessons |
| S2 | Events and Event History · Temporal · primary | https://docs.temporal.io/workflow-execution/event |
| S3 | Self-hosted defaults and limits · Temporal · primary | https://docs.temporal.io/self-hosted-guide/defaults |
| S4 | Durable execution with fibers · Cloudflare · primary | https://developers.cloudflare.com/agents/runtime/execution/durable-execution/ |
| S5 | Long-running agents · Cloudflare · primary | https://developers.cloudflare.com/agents/concepts/long-running-agents/ |
| S6 | Temporal vs Inngest vs Restate · Particula 2026 · secondary | https://particula.tech/blog/durable-execution-ai-agents-temporal-inngest-restate |
| S7 | Interrupts · LangGraph · primary | https://docs.langchain.com/oss/python/langgraph/interrupts |
| S8 | Background mode · OpenAI · primary | https://developers.openai.com/api/docs/guides/background |
| S9 | Guardrails and human review · OpenAI · primary | https://developers.openai.com/api/docs/guides/agents/guardrails-approvals |
| S10 | Practical guide to building agents · OpenAI 2025 · vendor guidance | https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf |
| S11 | Prompt caching · Anthropic · primary | https://platform.claude.com/docs/en/build-with-claude/prompt-caching |
| S12 | Rate limits · Anthropic · primary | https://platform.claude.com/docs/en/api/rate-limits |
| S13 | API errors · Anthropic · primary | https://platform.claude.com/docs/en/api/errors |
| S14 | Prompt Caching 201 · OpenAI Cookbook 2026 · self-report | https://developers.openai.com/cookbook/examples/prompt_caching_201 |
| S15 | Data controls and residency · OpenAI · primary | https://developers.openai.com/api/docs/guides/your-data |
| S16 | How we contain Claude · Anthropic 2026-05-25 · vendor telemetry | https://www.anthropic.com/engineering/how-we-contain-claude |
| S17 | Configure permissions · Claude Agent SDK · primary | https://code.claude.com/docs/en/agent-sdk/permissions |
| S18 | Approvals and user input · Claude Agent SDK · primary | https://code.claude.com/docs/en/agent-sdk/user-input |
| S19 | Events · AG-UI · spec | https://docs.ag-ui.com/concepts/events |
| S20 | On-Behalf-Of User Authorization for AI Agents, draft-02 · IETF 2025-08-26, expired 2026-02-27 | https://datatracker.ietf.org/doc/html/draft-oauth-ai-agents-on-behalf-of-user-02 |
| S21 | Article 14, human oversight · AI Act Service Desk · legislative | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 |
| S22 | Regulation (EU) 2026/1744, AI Omnibus · EUR-Lex · legislative | https://eur-lex.europa.eu/eli/reg/2026/1744/ |
| S23 | AI Act timeline · European Commission 2026-08-03 | https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai |
| S24 | SP 800-53 overlays for AI, COSAiS · NIST 2026-01-08 · primary | https://csrc.nist.gov/projects/cosais |
| S25 | AI RMF Agentic Profile v1 · Cloud Security Alliance 2026 · consortium | https://labs.cloudsecurityalliance.org/agentic/agentic-nist-ai-rmf-profile-v1/ |
| S26 | Top 10 for Agentic Applications 2026 · OWASP 2025-12-09 · standard | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| S27 | ASI01–ASI10 defences · Cycode 2026 · secondary | https://cycode.com/blog/owasp-top-10-agentic-applications/ |
| S28 | Exponential Backoff And Jitter · AWS 2015/2023 · foundational | https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/ |
| S29 | LLM serving fairness · Cohere 2026-06-17 · vendor eng. | https://cohere.com/blog/serving-fairness |
| S30 | Customizing the Copilot firewall · GitHub · primary | https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-the-firewall |
| S31 | LLM failover and load balancing · TrueFoundry 2026 · vendor claims | https://www.truefoundry.com/blog/llm-failover-load-balancing-provider-outages |
| S32 | Emergency stop design for AI agents · Unimon 2026 · practitioner | https://unimon.co.th/en/blog/ai-agent-circuit-breaker |
| S33 | SRE for AI agent systems · Zylos 2026-03 · secondary | https://zylos.ai/research/2026-03-22-sre-ai-agent-systems-observability-incident-response/ |
| S34 | Agent reliability SLO patterns · Velsof 2026 · secondary | https://www.velsof.com/ai-automation/ai-agent-reliability-engineering-slo-patterns/ |
| S35 | Canary, shadow mode, progressive rollouts · TuringPulse 2026 · secondary | https://turingpulse.ai/blog/safe-agent-deployments |
| S36 | Prior pass — agent architecture industry brief · internal 2026-07-14 | [`../2026-07-14/agent-architecture-industry.md`](../2026-07-14/agent-architecture-industry.md) |

---

## 8. Proposed content for final doc sections

### Section 11 — Production architecture, safety & operations

- **11.1 Execution model.** Substrate families; durability once a run outlives the process; engine costs [S1, S2, S3].
- **11.2 Streaming contract.** Sequence numbers, replay-from-offset with snapshot fallback, cancel ≠ disconnect ≠ pause [S8, S19].
- **11.3 HITL.** Durable pause on a server-issued id, risk-rated gates, expiry action, per-decision audit, the four traps [S7, S9, S10, S17, S18].
- **11.4 Containment.** Sandbox ladder, capability allowlists, credential brokering, firewall gaps; WS3 cross-reference [S16, S30].
- **11.5 Cost, latency, isolation.** Cache layout and hit-rate SLI, the 429/529 split, one-layer full-jitter retries, per-tenant fair queueing with cost-debited quanta, per-component attribution [S11]–[S14], [S28, S29].
- **11.6 Degrade and SLOs.** Stop → labelled partial → explain → escalate; multi-metric trips with structured stop logs; poison-pill quarantine; traced substitution; five signals plus the judgement SLI on OTel GenAI, semantics deferred to WS6 [S31]–[S34].
- **11.7 Identity and governance.** Delegation chain per action; OWASP ASI03/08/09/10 as index; AI Act dates labelled regulation; residency as two promises [S15], [S20]–[S23], [S26].

### Reference deployment (part of section 14)

1. **Turn path.** Client → app server → gateway → provider. The gateway owns provider credentials, one-layer retries, per-tenant fair queueing, a declared fallback chain with failover on the trace, and usage capture for attribution.
2. **Run state and streaming.** Append-only event store keyed by `run_id` with monotonic `sequence_number`, conversation storage separate from orchestration; SSE with offset resume, bounded replay window, snapshot endpoint, distinct terminal events. Stop is server-side; disconnect is not.
3. **HITL and containment.** An `awaiting_approval` row with server-issued ids, expiry timestamp, expiry action and decision audit; side effects strictly after the gate. Risk-rated tools, ephemeral sandbox, default-deny egress via a brokering proxy, credentials never mounted, symlinks resolved before path validation — interfaces are WS3's.
4. **Budgets and degrade.** Per-run token, USD, wall-clock, step, fan-out and depth caps as runtime invariants, plus a consecutive-failure breaker and a tool-call-hash loop detector; on breach, cancel in-flight work, write a structured stop log and emit a labelled partial.
5. **Durability boundary.** In-turn runs use application checkpoints plus the resumable stream; runs outliving the process use short versioned task-scoped workflows with idempotent activities.
6. **Observability, rollout, governance.** OTel GenAI spans, per-run outcome records, cache-hit/substitution/breaker counters; immutable bundle behind a flag gated offline → shadow → sticky canary → ramp, session-pinned with drain on rollback; delegation chain per consequential action; residency fixed at project creation; AI-interaction disclosure per the rules in force from 2026-08-02.

---

*End of memo.*
