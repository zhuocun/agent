# WS7 — Production engineering & operations

**Scope:** the runtime substrate an agent runs on and the policy layer around it — durability, streaming, HITL, cost, isolation, identity, degrade behaviour, rollout. | **Access date: 2026-08-03**, all sources retrieved this session | **Deferred to:** **WS3** tool/sandbox *interface* design; **WS6** eval and tracing *semantics*; **WS2** topology.

---

## 1. Executive summary

1. **[medium] Durable execution helped one vendor; the numbers aren't a benchmark.** Cursor reports "one 9" before Temporal and "past two 9s" after, at >50M actions/day over >7M workflows [S1] — self-reported, n=1, no availability definition, denominator, window or harness. The mechanism — provider outages, pod replacement, node loss — travels better than the figure.
2. **[high] It does not buy exactly-once side effects.** Activities may execute and partially complete more than once; idempotency is "enforced by the service you are calling from your Activity, not by the Activity itself" [S5] — §2.1.
3. **[high] Resume has two layers, one of which understands your run.** Transport `Last-Event-ID` [S18] sits under application offsets [S8, S19]; transport resume replays bytes, not run semantics — §2.2.
4. **[high] Supervision and hostname allowlists both failed measurement at the vendor that measured them.** Anthropic: **~93% of permission prompts approved**, an OS sandbox cut prompts **84%**, a February 2026 red-team phish exfiltrated `~/.aws/credentials` in **24 of 25 retries**. Cowork's allowlist passed `api.anthropic.com` while an attacker's planted key uploaded user files to their account [S16] — an allowlist is a capability grant, not a filter.
5. **[high] Prompt caching is a rate-limit lever before a cost lever.** Claude cache reads mostly skip ITPM, so 2M ITPM at an 80% hit rate passes ~10M input tokens/minute; reads cost 0.1×, 1-hour writes 2× [S11, S12]. OpenAI's `prompt_cache_key` took one customer 60%→87%, saturating near ~15 RPM per key [S14].
6. **[medium] Delegated authority has plumbing; consent doesn't.** RFC 8693 mints narrow delegated tokens — the authorization server consults `may_act` before issuing, and `act` names the current actor [S25]; front-channel consent naming the agent was the expired draft's contribution [S20] — §2.6.
7. **[medium] The AI Act's 2026 dates are settled; what binds a general assistant is narrower than "autonomy".** Per the Commission the AI Omnibus entered force 2026-07-27, moving Annex III high-risk to **2027-12-02** and Annex I to **2028-08-02**, general application from 2026-08-02, transparency rules from August 2026 [S23]. Article 14 attaches to high-risk systems only [S21].

---

## 2. Findings

### 2.1 Runtime substrate: what durable execution buys and costs

- **Two families.** *Journal-and-replay* (Temporal, Restate) records steps and reconstructs state on recovery; Inngest's `step.run()` bills per step [S6]. *Actor-with-durable-state* (Cloudflare Durable Objects) gives an addressable agent with SQLite, idle at zero compute [S4].
- **Buys [high]:** completed Activities aren't re-executed on replay, so finished LLM and tool results come from history, not the provider; waits are durable at zero compute, so a pending approval survives process loss [S2, S5].
- **Doesn't buy [high]:** exactly-once execution. Activities don't record to history until they return or error, so a worker that finishes the work then dies before reporting is retried — Temporal's example is duplicate charges in a payment processor [S5]. The contract is **at-least-once execution, exactly-once observation**.
- **So idempotency is yours, at the callee.** Temporal suggests Run ID + Activity ID as the key [S5]. AWS adds: a caller-supplied request identifier; that token and the mutation committed as one ACID operation; and a *semantically equivalent* replay response rather than `AlreadyExists`, which leaves the caller unable to tell whether this request or an earlier one did the work [S22].
- **Costs [high]:** determinism, plus payload limits — Temporal warns at 256 KB, errors at 2 MB, **terminates** past 51,200 events or 50 MB of history [S2, S3]. Hence claim-check codecs and versioning; Cursor moved to short task-scoped workflows [S1].

### 2.2 Streaming and the UX protocol

- SSE is the transport these vendor APIs document; nothing retrieved compares deployments, so "default" describes documented interfaces, not measured share — **[low]**.
- **Two resume layers.** WHATWG: `id:` sets the last event ID and the client returns `Last-Event-ID` on reconnect [S18]. Application offsets sit above, because only they know which *run* events a client missed [S8]. AG-UI adds the vocabulary — run/step lifecycle, text, tool calls, snapshot-plus-delta state — so a reconnecting client renders a snapshot then resyncs [S19].
- A background response not created with `stream: true` can't be re-streamed, and OpenAI's EU region forbids `background=True` — residency can silently remove your resume mechanism [S8, S15].
- **Cancel needs three states:** *disconnected* (keep running, buffer), *cancelled* (stop, release budget, terminal event), *paused for approval* (durable, resumable by token). OpenAI makes the first two explicit, cancel idempotent [S8]. **[high]**

### 2.3 Human-in-the-loop machinery

- **Settled mechanism.** LangGraph's `interrupt()` suspends at the call site, persists via the checkpointer, waits **indefinitely** [S7]. OpenAI's Agents SDK records an *interruption* rather than executing the tool, returning a resumable `state` [S9]. Claude's SDK evaluates hooks → deny → ask → mode → allow → `canUseTool`; auto-approved tools never reach that callback, so per-call audit belongs in a `PreToolUse` hook [S17]. Gates follow a per-tool risk rating — write access, reversibility, permissions, financial impact [S10].
- **Four traps.** *Durability illusion* — LangGraph's examples use `InMemorySaver`, so a pending approval dies with the process. *Idempotency* — on resume the node restarts from its beginning, so writes before the `interrupt` fire twice [S7]. *Gate placement* — guardrails run only at chain edges, so validation belongs beside the side-effecting tool [S9]. *Inherited privilege* — `bypassPermissions`/`auto` can't be overridden per subagent [S17].
- Approvals need a **timeout with a defined expiry action** plus an audit record; no retrieved doc gives a default, and in the cloud "the cost of blocking is much higher" [S1]. **[medium]**

### 2.4 Cost and latency engineering

- **Cache layout:** stable content first, dynamic last, no timestamp or user id in the prefix; the 1-hour TTL covers approval waits where a 5-minute cache evicts [S11, S14].
- **Backpressure:** 429 `rate_limit_error` is your limit (honour `retry-after`; `anthropic-ratelimit-*` names whether RPM, ITPM or OTPM tripped), 529 `overloaded_error` is fleet-wide [S12, S13]. Retry with capped exponential backoff and **full jitter**, at one layer, idempotent only — no-jitter backoff is the measured worst case [S28] and SDKs already retry.
- **Failover** belongs in the gateway. Fallback buys independent failure domains, but "the same prompt can behave differently on the fallback model", so restrict it to an ordered config-defined chain and trace failover events [S31]. Attribute per-run cost by part: a caching regression hides in a token total [S11, S14].

### 2.5 Concurrency, isolation, secrets

- **Cohere's fairness stack, in order:** rate limiter (admission, plus early rejection once the queue can't meet the latency target), performance tier, **deficit round robin** with a per-tenant quantum debited by request cost, then priority → deadline → arrival ordering *inside* each tenant [S29].
- **The transfer needs qualifying.** That stack schedules inference onto Cohere's *own* GPU batches; an application gateway calling an external provider owns no accelerator and rations outbound calls against someone else's limits. Transferable is the **shape** — per-tenant queues rather than one global priority queue, a cost-debited quantum, urgency kept within a tenant: **[medium]**. That DRR quanta behave the same when the bottleneck is a remote ITPM ceiling is untested: **[low]**. Cohere itself calls request-based budgeting "suboptimal for generative endpoints" yet ships it there, so the unit is unsettled at the source [S29].
- **Sandbox ladder**, three Anthropic shapes: ephemeral gVisor container per session; OS-level sandbox (bubblewrap/Seatbelt), network denied by default; local VM. "The weakest layer is the one you built yourself" — gVisor and seccomp held, the custom proxy failed. Keep credentials outside the sandbox and broker them; resolve symlinks before path validation [S16]. Read a firewall's limits — GitHub's covers only Bash-tool processes and "sophisticated attacks may bypass" it [S30].

### 2.6 Identity, authorization, governance

- **Delegation has token plumbing; consent has none.** RFC 8693 separates *delegation* (the agent keeps its own identity while acting for the user) from *impersonation* (the token still identifies the user), carrying the former in an `act` claim; the *authorization server* consults `may_act` before issuing [S25]. A resource server authorizes the current actor plus top-level claims and scope — deeper nesting is informational, not an access-control input — so least privilege lives in the scope minted at exchange; the chain is audit evidence.
- **EU AI Act** (dates in §1.7): Article 14 applies to high-risk systems and reads like an engineering spec — humans able to *remain aware of automation bias*, override output, and "interrupt the system through a 'stop' button… that allows the system to come to a halt in a safe state" [S21]. Automation bias is §1.4's 93% arriving from the regulatory side. **[high]** on the text, **[low]** on scope.
- **NIST:** COSAiS's SP 800-53 overlays reached annotated outline on 2026-01-08, so agent overlays remain upstream of a final [S24].
- **OWASP:** the Top 10 for Agentic Applications (2025-12-09) is the taxonomy; mine rather than WS3's are ASI03 privilege abuse, ASI08 cascading failures, ASI09 trust exploitation, ASI10 rogue agents — met with scoped short-lived per-agent credentials, blast-radius isolation and behavioural monitoring [S26, S27].
- **Residency:** OpenAI's controls are project-scoped, fixed at creation, and carry a **10% uplift** for eligible models released on or after 2026-03-05 [S15] — storage-at-rest and in-region processing are separate promises. **[high]**

### 2.7 Failure, degrade modes, SLOs

- **The degrade ladder:** stop scheduling new actions → return partial results already produced → say what tripped and which parts are incomplete → escalate if a gate exists → never discard completed work. Hard stop suits cost runaway and confirmed injection, a soft limit suits latency overruns, and a global kill switch sits beside the per-task one [S32].
- **Trip conditions must be plural, because each metric misses a class:** token count alone misses cheap endless loops, step count alone misses few-but-expensive tool calls. One worked set is 50k tokens and $0.50 per task, 30 steps, 3 failures in 5 and 10 minutes, plus loop detection on a hash of recent tool calls. Every stop writes a structured log, since unlogged breakers can't be tuned [S32]. **[medium]**
- **Ambiguous outcomes need their own path, not a retry.** A write that times out mid-flight has an unknown result; retrying without an idempotency key is how one action becomes two [S5, S22]. Bound retries per activity *and* per run, and quarantine a run that fails deterministically on replay — no retrieved source covers poison pills, so that is inference. **[low]**
- **SLO vocabulary has converged; the quality metric is a proxy whose bias direction is known.** Availability → task success rate; latency → TTFT plus completion including HITL wait; errors → escalation rate; cost → tokens per task; plus a **judgement SLI** from override and correction rate, which Zylos presents as sufficient signal without ground-truth labels [S33]. That holds only where reviewers genuinely review: against ~93% blanket approval [S16], an absent override records fatigue as readily as a correct action. Treat it as a **floor on detected error, never an estimate of true error**, paired with sampled ground-truth review (WS6's) — **[medium]** for the metric, **[high]** that it understates error. Published targets (99.5% availability, <800 ms p95 TTFT) come from consultancy posts with no population, model version or harness — **[low]** [S34].

### 2.8 Rollout practice

- **The gate sequence:** offline regression suite as a hard block → **shadow** on mirrored traffic, the candidate reasoning normally while every write-action call is intercepted as a dry run → **canary** on pre-registered gates → stepped ramp → automatic rollback. Risk-tier it: prompt wording is bounded, a new tool changes tool selection everywhere, a model swap touches everything [S35].
- **Ship an immutable versioned bundle** — model, prompt, tool schemas, retrieval config, guardrails — referenced by id outside application code, so rollback needs no redeploy [S35].
- **Rollback needs session pinning plus graceful drain**, or a five-step plan finishes later steps on a version it didn't start on — "for long-running agent workflows this isn't an edge case; it's the common case during rollback" [S35]. **[medium]**, practitioner consensus.

---

## 3. Delta since 2026-07-14

**Already in the prior pass, not claimed as new** ([S36]): in-turn orchestration with resumable SSE buffers and explicit Stop ≠ disconnect; client disconnect distinguished from user cancel; HITL as durable pause states with resume tokens bound to **server-issued** ids; skipping completed activities on retry; idempotent tools with dedupe keys; hard caps as code invariants. All of it holds.

What actually changed:

1. **Those patterns acquired first-party wire formats.** The prior advice was to build a resumable buffer; vendors now specify the format — OpenAI's `sequence_number` plus `?starting_after=N`, AG-UI's `resume` array — so this is conformance rather than design [S8, S19]. WHATWG `Last-Event-ID` was always underneath [S18].
2. **"Skip completed activities on retry" needs correcting.** True for *completed* Activities, but an Activity may execute and partially complete more than once, so dedupe keys are load-bearing rather than hygiene, and must be enforced by the callee [S5, S22].
3. **The durability trigger reframed** from "exceeds request or worker lifetime" to infrastructure churn, with Cursor's corrections: short task-scoped workflows and decoupled loop/machine/conversation state [S1].
4. **Genuinely new:** quantified approval-gate failure [S16]; caching as a rate-limit multiplier [S11, S12, S14]; residency removing `background=True` [S15]; provider-side fair scheduling [S29]; the judgement SLI and its fatigue bias [S33]; session-pinned canaries [S35]; RFC 8693 as the delegated-token layer [S25]; the regulatory clock [S21, S23].
5. **Permission detail sharpened into fan-out risk.** Subagent inheritance of `bypassPermissions`, plus guardrails at chain edges only, mean a topology decision (WS2's) silently changes the safety posture of every tool call [S9, S17].

---

## 4. Contested / open questions

| Question | Confidence | Notes |
| --- | --- | --- |
| Whether durable-engine reliability gains transfer to an in-turn chat product | **low** | Cursor's evidence is hours-to-weeks agents on dedicated VMs, self-reported, n=1 [S1]; engine costs are documented [S2, S3, S5]. |
| Oversight or theatre? | **medium–high** that gating alone fails | 93% approval points to containment-first [S16]; Article 14 mandates *effective* oversight for high-risk systems [S21]. |
| Whether provider-side fair queueing suits a client-side gateway | **low** | Cohere's DRR rations its own GPU batches, not third-party calls [S29]; nothing retrieved tests the analogue. |
| How much a judgement SLI overstates quality | **open** | Override rate needs no labels [S33] but is depressed by approval fatigue [S16]; the gap is unmeasured in anything retrieved. |
| Whether front-channel agent consent standardises | **low** | RFC 8693 covers the token mechanics [S25]; the draft adding consent expired without WG adoption [S20]. |

---

## 5. Anti-patterns & failure modes

| Anti-pattern | Why it fails | Prefer |
| --- | --- | --- |
| Durable engine treated as exactly-once; ambiguous write retried | At-least-once execution; a timed-out write has an unknown outcome [S5] | Callee-enforced keys, atomic token+mutation commit [S22] |
| In-memory checkpointer; non-idempotent work before `interrupt()` | Approval dies with the process; the node restarts, charging twice [S7] | Durable checkpointer; gate before side effects |
| Allowlist as destination filter; firewall coverage assumed | Any capability behind an allowed domain is reachable [S16]; GitHub's covers only Bash-tool processes [S30] | Capability-scoped brokering proxy |
| Low override rate read as high quality | Absence of correction isn't correctness at ~93% approval [S16, S33] | A floor on detected error, plus sampled review |
| Fan-out inheriting parent permissions; canary without sticky routing | Subagents inherit `bypassPermissions`; edge guardrails miss inner calls [S9, S17]; threads flip version mid-run [S35] | Per-subagent least privilege; session version hash |

---

## 6. Design implications

Normative; each with rationale and tradeoff.

1. **Default to in-turn orchestration with a resumable event stream; adopt a durable engine only when runs outlive the process** — engine costs are documented, the reliability evidence is one self-report [S1, S2, S3]. *Tradeoff:* you hand-roll retry and idempotency discipline, and migrating later is a project.
2. **Make every side-effecting tool idempotent at the callee before adopting a durability layer** — at-least-once is the actual contract, so the key belongs where the mutation commits [S5, S22]. *Tradeoff:* third-party tools without keys become non-retryable and escalate on ambiguity.
3. **Make the event stream the contract:** monotonic sequence numbers, replay-from-offset, snapshot+delta state, three terminal states, `Last-Event-ID` beneath [S8, S18, S19]. *Tradeoff:* buffer retention scales with fan-out volume.
4. **Gate on containment and server-issued ids; treat approval as a supplement; broker every credential** — supervision and hostname allowlists demonstrably can't carry the load [S16]. *Tradeoff:* containment costs capability, and the broker is custom code.
5. **Design the prompt as a cache artifact and treat hit rate as an SLI** — caching is a cheaper read, a TTFT cut and an ITPM multiplier at once [S11, S12, S14]. *Tradeoff:* prefix stability constrains personalisation.
6. **Encode caps as runtime invariants, not prompt instructions, combining token, cost, step, error-rate and time triggers behind a labelled-partial degrade path** [S32]. *Tradeoff:* more visible partials; thresholds need a p95 baseline.
7. **Route model traffic through one gateway owning retries, failover, per-tenant queues and substitution logging** [S9, S13, S17, S28, S31]. *Tradeoff:* a single point of failure needing backpressure load-testing; quanta need local calibration [S29].
8. **Mint a narrowly scoped delegated token per run instead of reusing user credentials** — under RFC 8693 the scope granted at exchange enforces least privilege; the `act` chain is audit evidence [S25, S26]. *Tradeoff:* needs an STS and cooperating resource servers; consent is unstandardised [S20].
9. **Ship changes as an immutable bundle behind a flag: offline → shadow → sticky canary → ramp, session-pinned on rollback** [S35]. *Tradeoff:* shadow doubles inference cost on its slice and needs per-tool dry-run.

---

## 7. Sources

All retrieved 2026-08-03; vendor posts are primary reports of their own systems. **Length convention:** the substantive word count is §1–§6 plus §8; this reference table is excluded. 35 external sources plus the prior-pass memo.

| # | Source · org · type | URL |
| --- | --- | --- |
| S1 | Lessons building cloud agents · Cursor 2026 · self-report | https://cursor.com/blog/cloud-agent-lessons |
| S2 | Events and Event History · Temporal · primary | https://docs.temporal.io/workflow-execution/event |
| S3 | Self-hosted defaults and limits · Temporal · primary | https://docs.temporal.io/self-hosted-guide/defaults |
| S4 | Durable execution with fibers · Cloudflare · primary | https://developers.cloudflare.com/agents/runtime/execution/durable-execution/ |
| S5 | Activity Definition — idempotency, at-least-once, retry policy · Temporal · primary | https://docs.temporal.io/activity-definition |
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
| S18 | Server-sent events (`id`, `Last-Event-ID`, `retry`) · WHATWG HTML · spec | https://html.spec.whatwg.org/multipage/server-sent-events.html |
| S19 | Events · AG-UI · spec | https://docs.ag-ui.com/concepts/events |
| S20 | On-Behalf-Of User Authorization for AI Agents, draft-02 · IETF 2025-08-26, expired 2026-02-27 | https://datatracker.ietf.org/doc/html/draft-oauth-ai-agents-on-behalf-of-user-02 |
| S21 | Article 14, human oversight · AI Act Service Desk · legislative | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 |
| S22 | Making retries safe with idempotent APIs · AWS Builders' Library · foundational | https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ |
| S23 | AI Act timeline and AI Omnibus · European Commission 2026-08-03 · legislative | https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai |
| S24 | SP 800-53 overlays for AI, COSAiS · NIST 2026-01-08 · primary | https://csrc.nist.gov/projects/cosais |
| S25 | RFC 8693 OAuth 2.0 Token Exchange (`act`, `may_act`, `actor_token`) · IETF · Proposed Standard | https://datatracker.ietf.org/doc/html/rfc8693 |
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

- **11.1 Execution model.** Substrate families; durability once a run outlives the process; at-least-once execution; history limits [S1]–[S6].
- **11.2 Idempotency.** Keys at the callee, atomic token+mutation commit, equivalent replay response, ambiguous-outcome escalation [S5, S22].
- **11.3 Streaming contract.** `Last-Event-ID` under application sequence numbers; replay-from-offset; cancel ≠ disconnect ≠ pause [S8, S18, S19].
- **11.4 HITL.** Durable pause on a server-issued id, risk-rated gates, expiry action, per-decision audit, the four traps [S7, S9, S10, S17].
- **11.5 Containment and identity.** Sandbox ladder, capability allowlists, credential brokering; RFC 8693 scopes minted at exchange; OWASP ASI03/08/09/10 [S16, S25, S26, S30].
- **11.6 Cost and isolation.** Cache layout and hit-rate SLI, the 429/529 split, one-layer full-jitter retries, per-tenant queues [S11]–[S14], [S28, S29].
- **11.7 Degrade and SLOs.** Stop → labelled partial → explain → escalate; multi-metric trips with stop logs; judgement SLI as a floor on detected error [S31]–[S34].
- **11.8 Governance.** AI Act dates scope-dependent; residency as two promises; NIST overlays still upstream [S15, S21, S23, S24].

### Reference deployment (part of section 14)

1. **Turn path.** Client → app server → gateway → provider. The gateway owns provider credentials, one-layer retries, per-tenant queues, a declared fallback chain traced on failover, and usage capture.
2. **Identity enforcement.** Each run mints a short-lived credential for its own agent identity via RFC 8693 exchange — `subject_token` the user, `actor_token` the agent — with the authorization server consulting `may_act` and narrowing scope to that run's tools. The resource server authorizes the current actor, claims and scope; the `act` chain is audit evidence, not the access-control input [S25, S26].
3. **Tenant-state isolation.** Tenant id keys run state, the event store, sandbox volumes and the cache-prefix namespace — a prefix cache shared across tenants is a cross-tenant read channel. Per-tenant queues and budgets, never a global priority queue [S29].
4. **Approval binding.** An `awaiting_approval` row binds the decision to `(run_id, step_id, tool_name, argument_hash, bundle_version)` with expiry timestamp and action. Resume presents a server-issued token; the server re-derives the hash and refuses if it moved, so a decision authorises *that* call, not what the agent proposes next [S7, S9].
5. **Run state and streaming.** Append-only event store keyed by `run_id` with monotonic `sequence_number`, separate from conversation storage; SSE offset resume over `Last-Event-ID`, bounded replay window, snapshot endpoint, distinct terminal events. Stop is server-side, disconnect is not [S8, S18].
6. **Ambiguous side-effect recovery.** Every write tool takes an idempotency key from `(run_id, step_id)`; the callee commits key and mutation atomically, returning an equivalent response on replay. A tool that cannot honour a key is non-retryable: on timeout or worker loss the run reads state back rather than retrying, and escalates if it cannot establish whether the effect landed [S5, S22].
7. **Budgets and degrade.** Per-run token, USD, wall-clock, step, fan-out and depth caps as runtime invariants, plus a consecutive-failure breaker and loop detector; on breach, cancel in-flight work, log the stop, emit a labelled partial [S32].
8. **Durability boundary.** In-turn runs use application checkpoints plus the resumable stream; runs outliving the process use short versioned task-scoped workflows whose activities are idempotent by construction at the callee, since the engine gives at-least-once execution [S5].
9. **Observability and rollout.** OTel GenAI spans, per-run outcome records, cache-hit and breaker counters, override rate beside sampled review; immutable bundle behind a flag gated offline → shadow → sticky canary → ramp, session-pinned with drain; AI-interaction disclosure per the rules in effect from August 2026 [S23, S33, S35].
