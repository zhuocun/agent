# WS3 — Tool & environment interface, and the tool-security seam

**Scope:** tool-call representation (schema / constrained output / code-as-action), tool ergonomics and token economics, tool-count scaling, MCP as of 2026-08, computer-use grounding, code execution as the universal tool, the untrusted-tool-output security seam, determinism and replay.
**Access date for all URLs: 2026-08-03.** Every source was retrieved in this session.
**Deferred to siblings:** **WS4** retrieval-as-memory (I cover retrieval only over *tool catalogs*); **WS7** infra multi-tenancy and runtime ops (I cover sandbox *interface* properties); **WS6** benchmark methodology.

---

## 1. Executive summary

1. **The interface has bifurcated, and the split is measured.** Schema calling stays correct for 1–2 call turns; code-as-action wins on composition, with Anthropic reporting 37% input-token reduction (43,588 → 27,297) for Programmatic Tool Calling. **[high]** direction, **[medium]** magnitude (vendor harness).
2. **Tool *definitions*, not results, break first, and the degradation is quantified twice.** Five MCP servers (58 tools) ≈ 55K tokens before the first user token; MCP-eval selection accuracy runs 49% (Opus 4) / 79.5% (Opus 4.5), recovering to 74% / 88.1% with on-demand tool search. **[high]**
3. **MCP shipped a breaking stateless rewrite on 2026-07-28:** no handshake, no session id, no SSE resumability; routable headers; cache hints; Multi Round-Trip Requests (MRTR) replacing server-initiated elicitation; Roots/Sampling/Logging and DCR deprecated. **[high]** primary spec.
4. **Computer use's ceiling is long-horizon, not clicking.** OSWorld 2.0 (108 workflows, median 1.6 human-hours): **20.6% completion / 54.8% partial**, Opus 4.8 at 500 steps; accessibility-tree vs pixel grounding *inverts per application*. **[high]** / **[medium]**
5. **Only deterministic environment boundaries mitigate; model-layer controls reduce.** ~93% of permission prompts were approved, Gray Swan ASR for Opus 4.7 rose from ~0.1% single-shot to ~5–6% over 100 adaptive attempts, and Anthropic's own egress allowlist was bypassed through an allowed first-party API. **[high]**
6. **Determinism gained spec support; idempotency has none.** Cache hints and deterministic `tools/list` ordering are normative — explicitly to protect upstream *prompt* caches — but no protocol-level idempotency key exists. **[high]**

---

## 2. Findings

### 2.1 Interface: schema, constrained output, code-as-action

Constrained decoding is OpenAI's recommended default ("we recommend always enabling strict mode"), with one trap worth asserting on: Responses requests attempt to normalize a schema and silently fall back to `strict: false`. **[high]** Code-as-action's evidence is foundational-2024 and holds: CodeAct (17 LLMs; API-Bank plus a purpose-built M³ToolEval of 82 multi-tool tasks) reports up to **+20 points absolute success** over JSON/text at **up to 30% fewer actions**, and is explicit that the gain is *composition* — control and data flow in one action — while on atomic actions it is merely comparable. **[high]** measurement, **[low]** for transferring 2024 model rankings. smolagents restates the case as framework doctrine (composability, object management, generality, training-data density) with no independent measurement — a design argument, not evidence. **[medium]** Where it loses: an independent replication of the MCP code-execution pattern measured **+7% latency and +120% output tokens** against −78.5% input tokens at identical success. So **code-as-action trades output tokens and a sandbox dependency for input tokens and turns, and only pays above roughly three composable steps.** **[medium]**

### 2.2 Tool description & ergonomics

Anthropic's *Writing effective tools for agents* (2025-09-11) is eval-derived: build **workflow tools, not API mirrors**; treat **namespacing as model-specific**, given non-trivial LLM-varying prefix-vs-suffix effects; **return tokens the model can act on**, since semantic names in place of UUIDs measurably reduce retrieval hallucination and a `concise`/`detailed` format cut their Slack example to ~⅓ the tokens (72 vs 206); and **bound results by construction**, with Claude Code capping responses at **25,000 tokens**. They report Sonnet 3.5 reaching state of the art on SWE-bench Verified after tool-description refinements alone. **[high]** The ancestor is SWE-agent's **agent-computer interface** (NeurIPS 2024), whose linting guardrail is the canonical teaching error: a syntax-breaking edit is reverted and the agent sees error type + attempted content + original content, all three necessary by ablation. **[high]** foundational. Anthropic's `input_examples` (2025-11) extends this to which optional-parameter combinations make sense: 72% → 90% on complex parameter handling. **[medium]**

### 2.3 Scaling tool count

By regime: below ~20–30 tools nothing structural breaks; at ~50–60 the *definitions* dominate context (58 tools ≈ 55K tokens, 134K in one internal config); into the 100s–1000s selection accuracy itself collapses (49% Opus 4 / 79.5% Opus 4.5, Anthropic MCP-eval). Mitigations in measured order: **filesystem progressive disclosure**, exposing servers as files the model reads on demand (150,000 → 2,000 tokens on one example task, **[medium]**); **deferred loading plus tool search**, leaving ~500 tokens in the prefix and loading tools on demand (~8.7K vs ~77K) while keeping deferred schemas *out of the cached prefix*, which lifts selection accuracy to 74% / 88.1% **[high]**; and **adaptive shortlist depth**, where Meta's Bits-over-Random work matched fixed-K=50 coverage on BFCL at K≈7.4 and found results on hard ToolBench queries where a fixed shortlist found none. **[high]** The gap none of these close: **ToolBench-X** injects five *recoverable* hazards (specification drift, invocation error, execution failure, output drift, cross-source conflict) into 1,106 tasks over 4,956 tools, and accuracy declines with chain length (GLM-5.1 0.490 → 0.335). The diagnosis is weak hazard recovery, not call volume — recovery hints rescue many tasks, test-time scaling helps little. **[high]**

### 2.4 MCP as of 2026-08

`2026-07-28` is the current stable revision (previous `2025-11-25`) and the direction is stateless HTTP. Handshake and sessions are gone: requests self-describe via `_meta`, `server/discover` is MUST-implement but optional to call, and servers needing cross-call state mint explicit handles passed as tool arguments. `Mcp-Method` and `Mcp-Name` headers let gateways route and authorize without parsing bodies, and **SSE resumability is removed**, so a broken stream loses the in-flight request. Elicitation becomes **MRTR**: a server returns `resultType: "input_required"` and the client *retries the original request* with `inputResponses` plus opaque `requestState` — how a stateless server gets mid-tool-call confirmation. Roots, Sampling and Logging are deprecated, as is DCR in favour of Client ID Metadata Documents; trace context becomes a `_meta` convention; a 12-month deprecation window applies. **[high]** primary spec.

**Honest adoption.** The registry is **still in preview** (2025-09-08 preview, v0.1 API freeze 2025-10-24, GA "later") and explicitly not for direct host consumption; SDK download counts are a poor proxy for production servers. **[medium]** MCP is **good at** being a cacheable, gateway-routable *catalog + invocation* protocol with a real auth story. It is **misused as** context delivery (the progressive-disclosure literature is a reaction to loading every catalog into every prefix), as a trust boundary, which it is not, and as a substitute for an in-process function call.

### 2.5 Computer use & browser agents

Anthropic's computer-use tool is pixel-grounded with a coordinate contract the *caller* owns — resize the screenshot, pass resized dimensions, scale coordinates back, within model-versioned pixel limits. **[high]** The number that should govern decisions is **OSWorld 2.0: 20.6% completion at 500 steps** (Opus 4.8, max thinking; 54.8% partial), GPT-5.5 plateauing near 13%, at ~318 tool calls per task versus ~30 in OSWorld 1.0. Its failure taxonomy is actionable: agents "lose track of constraints, miss information that arrives mid-task, **guess rather than ask the user**, and skip verification." **[high]** OSWorld-Human finds accessibility trees added to screenshots *increase* steps for visually rich apps and *decrease* them for OS/GIMP/Chrome — hybrid, per application, no general answer — on one agent and one task per app. **[medium]**

### 2.6 Code execution as the universal tool

Anthropic's *Code execution with MCP* (2025-11-04) names benefits beyond token count: in-environment filtering (10,000 rows → 5 the model sees), control flow without round-trips, PII tokenisation (`[EMAIL_1]`) so real values cross between services without entering model context, and filesystem-as-workspace with skills-as-persistence — caveated on sandboxing, resource limits and monitoring. **[high]** **Substrate is a threat-model choice:** E2B runs one Firecracker process per sandbox in its own cgroup and network namespace, where fresh creates are internally a *resume* of the template's base snapshot; Cloudflare's Dynamic Workers (open beta 2026-03-24) claim a few milliseconds and a few megabytes, ~100x faster than a container, with the honesty that "security bugs in V8 are more common than security bugs in typical hypervisors," and make egress first-class since `globalOutbound: null` blocks `fetch()`. **[high]** **Git-as-checkpoint, done right:** Claude Code on the web keeps git credentials outside the sandbox, with the in-sandbox client authenticating to a proxy that validates the push target before attaching the real token. **[high]**

### 2.7 Untrusted tool output & the security seam

The **lethal trifecta** — private data plus untrusted content plus an external-communication channel — is still the best triage heuristic, and its prescription is architectural: cut a leg. Well-sourced *secondary* framing, not a measurement. **[high]** **What has provable structure:** CaMeL derives control *and* data flow from the trusted query so untrusted data can never affect program flow, then enforces capability policies at every tool call — **77% of AgentDojo tasks solved with provable security vs 84% undefended**. Its companion design-patterns paper supplies the invariant: *"once an LLM agent has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions."* CaMeL-NOVA ports this to computer-use agents, retaining up to 57% of frontier OSWorld performance, but guarantees control-flow integrity only, leaving a residual **Branch Steering** class. **[high]**

**Measured mitigation vs residual** (primary vendor testing):

| Control | Effect | Residual |
| --- | --- | --- |
| Claude for Chrome mitigations | ASR 23.6% → **11.2%** (123 cases) | 11.2% |
| Claude Code OS sandbox, network denied by default | **84% fewer permission prompts** | egress-permitting designs still leak |
| Model robustness (Gray Swan, Opus 4.7) | ~**0.1%** ASR single-shot | ~**5–6%** after 100 adaptive attempts |
| Screenshot injection monitor (Operator, Jan 2025) | **99% recall / 90% precision** on 77 red-team attempts | 46 of 13,704 benign screens flagged; recall was 79% before a one-day retune |
| Classifier-gated auto-approval plus human backstop | catches ~83% of overeager behaviours | ~**17%** pass; ~**93%** of prompts approved |

**The most instructive negative result in the corpus.** Anthropic's containment post documents an allowlist bypass: the allowlist correctly passed `api.anthropic.com`, a poisoned workspace file carried hidden instructions *and* an attacker-controlled API key, and Claude uploaded other files to the attacker's account via Anthropic's own Files API. "The sandbox worked perfectly, and yet the data was exfiltrated." So **an allowlist is not a destination filter, it is a capability grant** — every function behind an allowed domain is attack surface — and the fix is a defensive proxy *inside* the VM, because only the VM knows provenance. **[high]** Three further rules from the same post: **tool output is an attack surface even when the tool is trusted** (a poisoned return leaves only a successful authorized call in the log, so they classify return values before context entry); **remote ≠ pinned** — a scan of 1,899 MCP servers found **7.2% vulnerable**, **5.5% with tool poisoning**; and **sub-agent output is not higher-trust**. OWASP's **Top 10 for Agentic Applications 2026** puts ASI02 Tool Misuse and ASI05 Unexpected Code Execution on this seam; NIST's **COSAiS** overlay is forward signal only. **[high]**

### 2.8 Determinism and replay

Spec-level caching is new and normative — `ttlMs` and `cacheScope` on the list and read methods, plus a SHOULD that servers return tools in **deterministic order** to improve prompt-cache hit rates. Prompt-cache stability is the real prize: deferred loading keeps on-demand schemas out of the cached prefix, and any scheme that mutates the prefix per turn destroys it. **[high]** Recording tool IO for replay is live but unstandardised, and the hard part is *request identity*: fresh tool-call ids and timestamps mean byte-exact matching always misses while loose matching replays stale answers. **[medium]** secondary. Idempotency is the biggest gap — nothing in 2026-07-28 provides a key, `readOnlyHint`/`destructiveHint` are advisory only, and ToolBench-X's hazards are precisely where agents retry. **[high]**

---

## 3. Delta since 2026-07-14

The prior brief compressed this surface into §3.2 (five bullets) plus an ACI mention — directionally right, evidentially thin. New since:

1. **MCP `2026-07-28` did not exist at the prior pass**, so any text assuming MCP sessions or `Last-Event-ID` resumability is now wrong; and **"sandbox tools" became a measurable design space** with named tradeoffs (Firecracker snapshot-resume vs V8 isolates) and published latency, memory and vulnerability-frequency characteristics.
2. **"Treat tool results as untrusted" now has a documented case where the correct implementation still failed** — the allowlist bypass — plus the reframing of an allowlist as a capability grant. Human approval is now quantified and weak, making HITL one probabilistic layer inside a deterministic boundary, not a control.
3. **Tool-count degradation moved from folklore to numbers** with a measurable mitigation stack, and **tool-environment *unreliability* became a distinct evaluation axis** — ToolBench-X shows failures are hazard recovery, not call syntax.
4. **Computer-use reliability was re-baselined downward** by OSWorld 2.0; Dual-LLM/CaMeL reached GUI agents with a sharp limit (control-flow integrity only) and a new attack class (Branch Steering); and ASI02/ASI05 are now the right primary standards references for this seam.

---

## 4. Contested / open questions

| Question | Confidence | Notes |
| --- | --- | --- |
| Does code-as-action beat schema calling for *our* turn shapes? | **Low–medium** | Conditional on ≥3 composable steps; needs local eval first |
| Accessibility-tree or pixel grounding? | **Low** | Inverts by application, on one agent and one task per app |
| Registry as a trust root? | **Low** | Still preview; a rug pull is post-approval by construction and pinning isn't in the spec |
| Can classifiers on tool results be relied on? | **Low** | 99%/90% on a 77-case set vs 5–6% ASR under 100 adaptive attempts. A layer, never a boundary |

---

## 5. Anti-patterns & failure modes

| Anti-pattern | Why it fails | Prefer |
| --- | --- | --- |
| Wrapping every API endpoint as a tool; returning UUIDs and unbounded payloads | Agent affordances differ from programs'; hallucination rises and the task is crowded out | Workflow tools; semantic names; `concise\|detailed`; truncation defaults |
| Loading every MCP catalog into every prefix, or dynamic loading that mutates the cached prefix | 55K tokens of definitions; accuracy 49–79.5%; prompt caching destroyed | Deferred loading outside the cached prefix; filesystem disclosure; deterministic ordering |
| Treating an egress allowlist as a destination filter | Every function behind an allowed domain is attack surface | Allowlist as capability grant; proxy inside the boundary |
| Opaque error codes; retry without idempotency; human approval as *the* control | Agent can't recover and repeats the call, no protocol key exists, and ~93% of prompts are approved anyway | Error-type + attempted + original triad; application-level dedupe keys; deterministic containment first |
| Treating remote MCP servers as pinned, or sub-agent output as higher-trust | 5.5% of 1,899 servers showed tool poisoning; trust escalation is an injection path | Pin, fingerprint, re-validate; treat all producers as untrusted |

---

## 6. Design implications

1. **Keep schema calling with `strict` as the default; add a code-execution seam only when a measured turn shape needs composition.** *Rationale:* the advantage is conditional on ≥3 steps and costs a sandbox plus output tokens. *Tradeoff:* forgoing input-token wins on data-heavy turns meanwhile.
2. **Invest in ergonomics before tool count, and add no tool retrieval below ~20 tools** — workflow-shaped tools, `concise|detailed`, semantic identifiers, bounded responses, errors that teach. *Rationale:* description-level refinements moved SOTA at Anthropic, and the token and accuracy problems are 50+-catalog phenomena, so retrieval below that only adds a failure mode fixed catalogs lack. *Tradeoff:* consolidated tools hide logic from the trace, and retrieval is a retrofit cost if the catalog grows.
3. **Treat every tool result — including sub-agent output — as untrusted, and inspect network-derived results before context entry.** *Rationale:* a poisoned return leaves no post-hoc signal. *Tradeoff:* latency, plus a classifier that must not be mistaken for a boundary.
4. **Build the deterministic boundary first:** filesystem scope, egress-as-capability-grant, credentials outside the sandbox. *Rationale:* every documented catastrophic case was egress through a permitted path. *Tradeoff:* isolation reduces observability, so budget OTLP export.
5. **Reserve human approval for consequential, inspectable decisions, and reuse any plan-approval gate as a security primitive.** *Rationale:* ~93% approval and ~17% pass-through make approval probabilistic, whereas an up-front plan is enumerable and policy-checkable. *Tradeoff:* more reliance on containment; single-shot plans degrade on underspecified tasks.
6. **Adopt MCP 2026-07-28 semantics and audit for removed features:** no session assumption, routable headers, MRTR for mid-call confirmation, honour cache hints, propagate `traceparent`, don't build on Roots/Sampling/Logging or DCR. *Rationale:* the deprecations are dated, so building on them now buys a rewrite inside the 12-month window. *Tradeoff:* SSE resumability is gone, so long tool calls need application-level retry with a new request id.
7. **Treat deterministic ordering and prefix-stable loading as cost engineering, add idempotency keys to every side-effecting tool, threat-model against OWASP ASI01–ASI10, and budget computer use against 20.6%.** *Rationale:* prompt-cache hit rate is the easiest thing to destroy, retry paths are where agents already fail, and GUI failure modes surface as confidently wrong answers. *Tradeoff:* per-tool work with no framework support; GUI automation is ruled out for now.

---

## 7. Sources

All URLs retrieved 2026-08-03. Vendor engineering posts are primary *for their own systems*; their benchmark numbers are **claims**, not independently reproduced measurements.

| # | Title | Org · Date · Type | URL |
| --- | --- | --- | --- |
| 1 | Key Changes (specification changelog) | Model Context Protocol · 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/changelog |
| 2 | Multi Round-Trip Requests | Model Context Protocol · rev. 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr |
| 3 | `modelcontextprotocol/registry` README | MCP community · preview 2025-09-08 · primary | https://github.com/modelcontextprotocol/registry |
| 4 | Writing effective tools for agents — with agents | Anthropic · 2025-09-11 · primary | https://www.anthropic.com/engineering/writing-tools-for-agents |
| 5 | Introducing advanced tool use on the Claude Developer Platform | Anthropic · 2025-11-24 · vendor claims | https://www.anthropic.com/engineering/advanced-tool-use |
| 6 | Code execution with MCP | Anthropic · 2025-11-04 · vendor claims | https://www.anthropic.com/engineering/code-execution-with-mcp |
| 7 | Beyond permission prompts | Anthropic · 2025-10-20 · primary | https://www.anthropic.com/engineering/claude-code-sandboxing |
| 8 | How we contain Claude across products | Anthropic · 2026-05-25 · primary | https://www.anthropic.com/engineering/how-we-contain-claude |
| 9 | Piloting Claude in Chrome | Anthropic · Aug 2025 · primary | https://claude.com/blog/claude-for-chrome |
| 10 | Computer use tool | Anthropic docs · current | https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool |
| 11 | Function calling | OpenAI docs · current | https://developers.openai.com/api/docs/guides/function-calling |
| 12 | Operator System Card | OpenAI · 2025-01-23 · primary; foundational (earliest published injection-monitor measurement for a shipped computer-use agent; cited only for that number) | https://cdn.openai.com/operator_system_card.pdf |
| 13 | What are agents? (conceptual guide) | Hugging Face smolagents docs · v1.26.0 · framework doctrine, not measurement | https://huggingface.co/docs/smolagents/en/conceptual_guides/intro_agents |
| 14 | Sandboxing AI agents, 100x faster | Cloudflare · 2026-03-24 · vendor claims | https://blog.cloudflare.com/dynamic-workers/ |
| 15 | E2B infra — `docs/ARCHITECTURE.md` | E2B · current | https://github.com/e2b-dev/infra/blob/main/docs/ARCHITECTURE.md |
| 16 | Executable Code Actions Elicit Better LLM Agents | Wang et al., arXiv 2402.01030 · Feb 2024 · foundational | https://arxiv.org/abs/2402.01030 |
| 17 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | Yang et al., arXiv 2405.15793 · May 2024 · foundational | https://arxiv.org/abs/2405.15793 |
| 18 | Defeating Prompt Injections by Design (CaMeL) | arXiv 2503.18813 · Mar 2025 · foundational | https://arxiv.org/abs/2503.18813 |
| 19 | Design Patterns for Securing LLM Agents against Prompt Injections | arXiv 2506.08837 · Jun 2025 · primary | https://arxiv.org/abs/2506.08837 |
| 20 | CaMeLs Can Use Computers Too | arXiv 2601.09923 · Jan 2026 · primary | https://arxiv.org/abs/2601.09923 |
| 21 | How Many Tools Should an LLM Agent See? | Repantis et al. (Meta), arXiv 2605.24660 · May 2026 · primary | https://arxiv.org/abs/2605.24660 |
| 22 | Beyond Function Calling: Tool-Using Agents under Tool-Environment Unreliability | Tian et al., arXiv 2606.25819 · Jun 2026 · primary | https://arxiv.org/abs/2606.25819 |
| 23 | OSWorld 2.0 | XLANG Lab et al., arXiv 2606.29537 · Jun 2026 · primary | https://arxiv.org/abs/2606.29537 |
| 24 | OSWorld-Human | MLSys 2026 proceedings · 2026 · primary | https://proceedings.mlsys.org/paper_files/paper/2026/file/5edb57c05c81d04beb716ef1d542fe9e-Paper-Conference.pdf |
| 25 | MCP at First Glance | Hasan et al., arXiv 2506.13538 · Jun 2025 · primary | https://arxiv.org/abs/2506.13538 |
| 26 | OWASP Top 10 for Agentic Applications for 2026 | OWASP GenAI Security Project · 2025-12-09 · standard | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| 27 | SP 800-53 Control Overlays for Securing AI Systems | NIST CSRC · 2025-08-14 · standard | https://csrc.nist.gov/projects/cosais |
| 28 | The lethal trifecta for AI agents | Simon Willison · 2025-06-16 · secondary | https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ |
| 29 | Code Execution with MCP (independent replication) | AIMultiple · 2026 · secondary | https://aimultiple.com/code-execution-with-mcp |
| 30 | Record and Replay Testing for AI Agents | dreaming.press · 2026 · secondary | https://dreaming.press/posts/record-replay-testing-for-ai-agents.html |

---

## 8. Proposed content for final doc sections

**§7 — Tool & environment interface.** Open with the bifurcation rather than a tool list: `strict` schema calling as the default, code-as-action earning its sandbox above ~3 composable steps. Then the ergonomics checklist; the scaling ladder by N (under 20 curate, 50+ defer-load outside the cached prefix, 100s+ filesystem disclosure); MCP 2026-08 as a what-changed/what-to-do table; then environment — filesystem-as-workspace, skills-as-persistence, PII tokenisation, substrate as threat-model choice, git-as-checkpoint with credentials outside the sandbox. Close on determinism plus one honest computer-use paragraph recommending against shipping browser control on current numbers.

**§11 (tool-security part).** Lead with the reframing — **an allowlist is a capability grant, not a destination filter** — via the documented bypass and its in-VM proxy fix, then a *mitigates vs merely-reduces* table using only measured numbers, residuals included. Then the three seam rules (untrusted tool output, remote ≠ pinned, sub-agent output not higher-trust), the standards mapping, the note that isolation reduces visibility so OTLP export needs budgeting, and the plan-approval gate as a security primitive with its limit stated.
