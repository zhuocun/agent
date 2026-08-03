# WS3 — Tool & environment interface, and the tool-security seam

**Scope:** tool-call representation (schema / constrained output / code-as-action), tool ergonomics and token economics, tool-count and long-context scaling, MCP as of 2026-08 including authorization, computer-use grounding, code execution, the untrusted-tool-output security seam, determinism and replay.
**Access date for all URLs: 2026-08-03.** Every source was retrieved in this session.
**Deferred to siblings:** **WS4** retrieval-as-memory (I cover retrieval only over *tool catalogs*); **WS7** infra multi-tenancy and runtime ops (I cover sandbox *interface* properties); **WS6** benchmark methodology.

---

## 1. Executive summary

1. **The interface question is settled in direction, open in threshold.** Schema calling is the vendor-recommended default; code-as-action's measured advantage is specifically *composition* — CodeAct (17 LLMs; 82-task M³ToolEval) reports up to **+20 points absolute** at **up to 30% fewer actions**, and is explicit that on atomic actions it is merely comparable. **[high]** for direction; any cutover point is a local hypothesis, not a finding. **[low]**
2. **Long context degrades tool use through three independent channels, not just definitions.** LongFuncEval (IBM Research; 6 open-weight 128K models + GPT-4o) measures **7.59–85.58%** degradation as the catalog grows 8K→120K tokens, **7–91%** loss in answer retrieval as tool *responses* grow 10K→80K, and **13–40%** as *conversations* lengthen. Definition bloat is the cheapest channel to fix, not the only one that breaks. **[high]**
3. **MCP `2026-07-28` is a breaking stateless rewrite whose authorization chapter is the under-read half:** no handshake, session id or SSE resumability; routable headers; cache hints; MRTR — plus normative **PKCE/`S256`**, RFC 8707 audience binding, RFC 9207 issuer validation, per-client consent and an explicit **token-passthrough prohibition**. **[high]** primary spec.
4. **Computer use has two separate ceilings.** Capability: OSWorld 2.0 **20.6%** completion (Opus 4.8, 500 steps) across 108 workflows of median **1.6 human-hours**, bounding long-horizon autonomy rather than short scripted GUI steps. Security: SecureWebArena finds pop-up attacks achieve **76.67–100%** payload delivery across 9 LVLM agents. **[high]** within those scopes.
5. **The layers mitigate differently, and the headline numbers measure different things** — a model-layer benchmark, a classifier's catch rate and human-approval telemetry are not comparable. Environment boundaries are the most reliable layer but not the only thing that mitigates: CaMeL is application-level with provable properties. **[high]**
6. **Determinism gained normative support; enforced idempotency did not.** Cache hints and deterministic `tools/list` ordering are normative, and an advisory `idempotentHint` exists — but the schema says all annotations are hints clients should never trust from untrusted servers, and no protocol-enforced idempotency key exists. **[high]**

---

## 2. Findings

### 2.1 Interface: schema, constrained output, code-as-action

Constrained decoding is OpenAI's recommended default ("we recommend always enabling strict mode"), with one trap: Responses requests attempt to normalize a schema and silently fall back to `strict: false`. **[high]** The load-bearing measurement for code-as-action is still CodeAct (Wang et al., Feb 2024): 17 LLMs, API-Bank plus a purpose-built 82-task M³ToolEval, up to **+20 points absolute** over JSON/text at **up to 30% fewer actions**, with the paper's own scope limit that the gain is *composition* and that atomic actions are merely comparable. **[high]** as a 2024 measurement, **[low]** for carrying 2024 rankings forward. smolagents restates the case as framework doctrine with no independent measurement. **[medium]**

The counter-evidence is thin and must be read as such. AIMultiple's replication of the MCP code-execution pattern measured **+7% latency, +120% output tokens, −78.5% input tokens, 100% success on both arms** — but on **two query types** at 50 runs each, **one model (GPT-4.1)**, one LangGraph ReAct harness over a 63-tool Bright Data MCP server, published 2026-06-24 by an outlet disclosing Bright Data as a customer. It supports a direction — code-as-action shifts cost from input to output tokens and adds a sandbox dependency — but cannot establish a step count. Anthropic's own Programmatic Tool Calling figure points the same way (**43,588 → 27,297 average tokens, a 37% reduction "on complex research tasks"**) with **model, task set and date of run all undisclosed**. **[low]** vendor-internal. **So read "code-as-action pays above roughly three composable steps" as a hypothesis to falsify locally, not an evidence-backed cutoff.** **[low]**

### 2.2 Tool description & ergonomics

Anthropic's *Writing effective tools for agents* (2025-09-11) is the best-articulated guidance in the corpus and among the weakest-evidenced. The advice is sound and mechanism-explained: **workflow tools, not API mirrors**; **namespacing is model-specific**; **return tokens the model can act on**, preferring semantic identifiers over UUIDs; and **bound results by construction** — Claude Code restricts responses to **25,000 tokens** by default, a documented default rather than a result. Two numbers need labels: the `concise`/`detailed` contrast (**72 vs 206 tokens**) is a worked example on one Slack tool, not a benchmark **[medium]**; and "Claude Sonnet 3.5 achieved state-of-the-art performance on the SWE-bench Verified evaluation after we made precise refinements to tool descriptions" names a model and harness but reports **no score, baseline or ablation delta** — an unquantified vendor claim. **[low]** `input_examples` (2025-11) likewise reports **72% → 90%** on complex parameter handling from "our own internal testing" with **model, task count and harness undisclosed**. **[low]**

The genuinely ablated ancestor is SWE-agent's **agent-computer interface** (NeurIPS 2024), whose linting guardrail is the canonical teaching error: a syntax-breaking edit is reverted and the agent sees error type, attempted content and original content, all three necessary by ablation. **[high]** foundational.

### 2.3 Scaling tool count and context

**What is measured.** LongFuncEval is the most useful public result because it is multi-model and separates the three channels in §1, showing degradation is continuous and model-dependent rather than switching on at some catalog size. **[high]** Anthropic's Tool Search Tool reports MCP-eval selection accuracy improving **49% → 74% (Opus 4)** and **79.5% → 88.1% (Opus 4.5)**, deferred loading holding ~**500 tokens** in the prefix and ~8.7K against ~77K total; models and direction are named, but the harness is "internal testing" on unspecified "MCP evaluations" with **no task count, public harness or run date** (2025-11-24). **[medium]** direction, **[low]** magnitude. Meta's Bits-over-Random work matched fixed-K=50 coverage on BFCL at **K≈7.4**. **[high]** The much-quoted "150,000 → 2,000 tokens" is **illustrative arithmetic**, not a measured task. **[low]**

**What is not measured.** No source I retrieved establishes a tool count at which degradation begins; LongFuncEval's curves are continuous and the vendor numbers come from "large tool libraries" of undisclosed size. So **"nothing structural breaks below ~20–30 tools" and "add no retrieval below ~20" are working hypotheses, not findings** — falsify them against your own catalog. **[low]** The defensible statements are narrower: degradation is continuous, starts earlier than intuition suggests, and retrieval adds a failure mode fixed catalogs lack.

**The orthogonal gap.** ToolBench-X injects five *recoverable* hazards (specification drift, invocation error, execution failure, output drift, cross-source conflict) into 1,106 tasks over 4,956 tools; accuracy declines with chain length (GLM-5.1 0.490 → 0.335) and the diagnosis is weak hazard recovery rather than call volume. **[high]**

### 2.4 MCP as of 2026-08

`2026-07-28` is the current stable revision (previous `2025-11-25`) and the direction is stateless HTTP. Handshake and sessions are gone: requests self-describe via `_meta`, `server/discover` is MUST-implement but optional to call, and servers needing cross-call state mint explicit handles passed as tool arguments. `Mcp-Method` and `Mcp-Name` headers let gateways route and authorize without parsing bodies, and **SSE resumability is removed**, so a broken stream loses the in-flight request. Elicitation becomes **MRTR**: the server returns `resultType: "input_required"` and the client *retries the original request* with `inputResponses` plus opaque `requestState`. Roots, Sampling, Logging and DCR are deprecated. **[high]** primary spec.

**Authorization is the strongest and least-discussed part of the spec**, and its requirements are normative and testable. Clients **MUST** implement PKCE with `S256` where capable and **MUST refuse to proceed** when `code_challenge_methods_supported` is absent from authorization-server metadata. Clients **MUST** send the RFC 8707 `resource` parameter, and servers **MUST** validate that tokens were issued for them, rejecting any that omit them from the audience. Mix-up attacks are mitigated by RFC 9207 authorization-response validation, and redirect URIs **MUST** be pre-registered and exactly validated. Proxies using static client IDs **MUST** obtain consent per dynamically registered client — the confused-deputy mitigation — and a server acting as an upstream OAuth client **MUST NOT** pass through the token it received: **token passthrough is explicitly forbidden**. Client ID Metadata Document fetching raises SSRF considerations. **[high]** primary spec.

**Honest adoption.** The registry is **still in preview** (v0.1 API freeze 2025-10-24, GA "later") and explicitly not for direct host consumption; SDK download counts are a poor proxy for production servers. **[medium]** MCP is **good at** being a cacheable, gateway-routable *catalog + invocation* protocol with a rigorous auth story. It is **misused as** context delivery, as a trust boundary, and as a substitute for an in-process function call.

### 2.5 Computer use & browser agents

Anthropic's computer-use tool is pixel-grounded with a coordinate contract the *caller* owns — resize the screenshot, pass resized dimensions, scale coordinates back, within model-versioned pixel limits. **[high]** The capability number most often quoted needs its scope attached: **OSWorld 2.0 reports 20.6% completion at 500 steps** (Opus 4.8, max thinking; 54.8% partial), GPT-5.5 plateauing near 13%, ~318 tool calls per task against ~30 in OSWorld 1.0 — but its 108 workflows have a median length of **1.6 human-hours**. It bounds *long-horizon, multi-application workflow autonomy*, and does not license a claim that GUI automation in general is unusable. **[high]** for the benchmark, **[low]** beyond it. OSWorld-Human finds accessibility trees added to screenshots *increase* steps for visually rich apps and *decrease* them for OS/GIMP/Chrome — hybrid, per application — on one agent and one task per app. **[medium]**

The security ceiling is measured separately and is worse. SecureWebArena (ACL 2026 Findings; 330 adversarial tasks over 6 environments and 6 attack vectors, 9 LVLM agents, 2,970 trajectories) reports **Payload Delivery Rate of 76.67–100% for pop-up attacks across every model category**, best average Gemini 2.5 Pro at 65.00%. Visual-perception attacks beat semantic ones, GUI-specialised grounding does not confer security, and its staged protocol shows agents reasoning into a compromised plan and only sometimes halting at execution. **[high]**

### 2.6 Code execution as the universal tool

Anthropic's *Code execution with MCP* (2025-11-04) names benefits beyond token count: in-environment filtering, control flow without round-trips, PII tokenisation (`[EMAIL_1]`) so real values cross between services without entering model context, and filesystem-as-workspace with skills-as-persistence. **[high]** mechanisms, **[low]** token arithmetic. **Substrate is a threat-model choice:** E2B runs one Firecracker process per sandbox in its own cgroup and network namespace, fresh creates being a *resume* of the template snapshot; Cloudflare's Dynamic Workers claim ~100x faster starts than a container while conceding "security bugs in V8 are more common than security bugs in typical hypervisors," and make egress first-class (`globalOutbound: null` blocks `fetch()`). **[high]** vendor-primary. **Git-as-checkpoint, done right:** Claude Code on the web keeps git credentials outside the sandbox, the in-sandbox client authenticating to a proxy that validates the push target before attaching the real token. **[high]**

### 2.7 Untrusted tool output & the security seam

The **lethal trifecta** — private data plus untrusted content plus an external-communication channel — remains the best triage heuristic, and its prescription is architectural: cut a leg. Well-sourced *secondary* framing, not a measurement. **[high]** as a heuristic. **What has provable structure:** CaMeL derives control *and* data flow from the trusted query so untrusted data can never affect program flow, then enforces capability policies at every tool call — **77% of AgentDojo tasks solved with provable security against 84% undefended**. Its companion design-patterns paper supplies the invariant: once an agent has ingested untrusted input, it must be constrained so that input cannot trigger any consequential action. CaMeL-NOVA ports this to computer-use agents, retaining up to 57% of frontier OSWorld performance, but guarantees control-flow integrity only, leaving a residual **Branch Steering** class. **[high]**

**These numbers are not comparable; each measures a different mechanism:**

| Control | What the number actually measures | Number | Residual |
| --- | --- | --- | --- |
| Claude for Chrome mitigations | Internal red-team ASR; 123 cases / 29 scenarios, autonomous mode, model undisclosed (2025-08-25) | 23.6% → **11.2%** | 11.2%; a 4-type browser challenge set went 35.7% → 0% |
| Model-layer robustness | Named third-party benchmark (Gray Swan Agent Red Teaming), Opus 4.7, reported by Anthropic 2026-05-25 | ~**0.1%** single attempt | ~**5–6%** over 100 adaptive attempts |
| Claude Code auto-mode classifier | Accuracy on *overeager commands* — not attack success | catches ~**83%** | ~**17%** pass; ~0.4% of benign commands blocked |
| Human permission prompts | Telemetry on human diligence — not an attack measurement | ~**93%** approved | approval fatigue rises with volume |
| Claude Code OS sandbox | Internal usage; *prompt-count reduction*, not attack efficacy | **84% fewer prompts** | egress-permitting designs still leak |
| CaMeL (application-level) | AgentDojo task utility under provable enforcement | 77% vs 84% undefended | Branch Steering, per CaMeL-NOVA |

The honest ordering: environment boundaries are most reliable because they bound capability rather than tendency; CaMeL-style application-level constructions also provide provable properties without being boundaries; model-layer defences and human approval reduce probability without bounding it. **[high]**

**The most instructive negative result in the corpus.** Anthropic's containment post documents an allowlist bypass: the allowlist correctly passed `api.anthropic.com`, a poisoned workspace file carried hidden instructions *and* an attacker-controlled API key, and Claude uploaded other files to the attacker's account via Anthropic's own Files API. "The sandbox worked perfectly, and yet the data was exfiltrated." So **an allowlist is not a destination filter, it is a capability grant** — every function behind an allowed domain is attack surface — and the fix is a defensive proxy *inside* the VM, since only the VM knows provenance. **[high]** Three further rules from the same post: **tool output is an attack surface even when the tool is trusted**, because a poisoned return leaves only a successful authorized call in the log; **remote ≠ pinned** — a scan of 1,899 MCP servers found **7.2% vulnerable**, **5.5% with tool poisoning**; and **sub-agent output is not higher-trust**. OWASP's **ASI02** and **ASI05** own this seam; NIST's **COSAiS** overlay is forward signal only. **[high]**

### 2.8 Determinism and replay

Spec-level caching is new and normative — `ttlMs` and `cacheScope` on the list and read methods, plus a SHOULD that servers return tools in **deterministic order** to improve prompt-cache hit rates. Prompt-cache stability is the real prize: deferred loading keeps on-demand schemas out of the cached prefix, and mutating that prefix per turn destroys it. **[high]**

**Idempotency needs a precise statement, because both halves are true.** `ToolAnnotations` does carry an advisory **`idempotentHint`** — "if true, calling the tool repeatedly with the same arguments will have no additional effect on its environment," defaulting to false and meaningful only when `readOnlyHint` is false — alongside `readOnlyHint`, `destructiveHint` and `openWorldHint`. But the schema is explicit that **all** are hints, "not guaranteed to provide a faithful description of tool behavior," and that clients "should never make tool use decisions based on `ToolAnnotations` received from untrusted servers." So a *declaration* of idempotence exists and is unverifiable, while a **protocol-enforced idempotency key — a caller-supplied token the server must use to deduplicate retries — exists nowhere in `2026-07-28`**. Since ToolBench-X's hazards land where agents retry, deduplication belongs at the application layer. **[high]** Replay recording is live but unstandardised, and the hard part is *request identity*: fresh tool-call ids and timestamps mean byte-exact matching always misses while loose matching replays stale answers. **[medium]**

---

## 3. Delta since 2026-07-14

The prior brief compressed this surface into §3.2 (five bullets) plus an ACI mention — directionally right, evidentially thin. New since, including two corrections to my own earlier framing:

1. **MCP `2026-07-28` did not exist at the prior pass**, so any text assuming MCP sessions or `Last-Event-ID` resumability is now wrong; and its **authorization chapter** supplies a normative checklist that "MCP has OAuth" summaries flatten away.
2. **"Tool definitions are what breaks" was too narrow.** LongFuncEval separates catalog size, response length and conversation length as three independent channels, two of which progressive disclosure does not touch.
3. **"Treat tool results as untrusted" now has a documented case where the correct implementation still failed** — the allowlist bypass — plus the capability-grant reframing. The human-approval and classifier numbers are public and measure different things; neither is an attack-mitigation rate.
4. **Computer use was re-baselined on both axes:** OSWorld 2.0 lowers the long-horizon capability estimate and SecureWebArena supplies the security ceiling, while CaMeL reached GUI agents with a sharp limit — control-flow integrity only — and a new attack class, Branch Steering.

---

## 4. Contested / open questions

| Question | Confidence | Notes |
| --- | --- | --- |
| At what step count does code-as-action beat schema calling? | **Low** | Only replication is 2 query types on one model; needs local eval before any cutover rule |
| At what tool count does degradation warrant retrieval? | **Low** | No cited source gives a threshold; LongFuncEval's curves are continuous |
| Can classifiers on tool results be relied on? | **Low** | ~83% catch on overeager commands, 99%/90% on a 77-case injection set, against 5–6% ASR over 100 adaptive attempts. A layer, never a boundary |

---

## 5. Anti-patterns & failure modes

| Anti-pattern | Why it fails | Prefer |
| --- | --- | --- |
| Wrapping every API endpoint as a tool; returning UUIDs and unbounded payloads | Agent affordances differ from programs'; hallucination rises and the task is crowded out | Workflow tools; semantic names; truncation |
| Treating definition bloat as the whole context problem, or mutating the cached prefix per turn | Responses and conversation degrade independently (7–91%, 13–40%); prefix churn destroys prompt caching | Bound results; prune conversation; defer loading outside the cached prefix |
| Treating an egress allowlist as a destination filter | Every function behind an allowed domain is attack surface | Allowlist as capability grant; proxy inside the boundary |
| Trusting `idempotentHint`/`readOnlyHint` from a remote server, or retrying without dedupe | Annotations are unverifiable hints; no protocol key exists | Application-level idempotency keys; treat hints as UI copy |
| Passing the client's token through to an upstream API | Spec-forbidden; breaks audience binding and enables confused-deputy | Separate upstream token; validate audience; per-client consent |
| Quoting ~93% approval and ~83% classifier catch as if both were attack rates | Different mechanisms, different denominators | State mechanism and denominator with every number |
| Treating remote MCP servers as pinned, or sub-agent output as higher-trust | 5.5% of 1,899 servers showed tool poisoning; trust escalation is an injection path | Pin, fingerprint, re-validate; treat all producers as untrusted |

---

## 6. Design implications

1. **Keep schema calling with `strict` as the default; gate any code-execution seam on a local measurement.** *Rationale:* the composition advantage is real but its cutover point is unestablished, and the seam costs a sandbox plus output tokens. *Tradeoff:* forgoing input-token wins on data-heavy turns meanwhile.
2. **Budget tool *results* and conversation growth as first-class limits, not just catalog size.** *Rationale:* LongFuncEval shows both degrade independently of catalog size. *Tradeoff:* truncation can drop the needed field.
3. **Set catalog and retrieval thresholds from your own eval, not this memo.** *Rationale:* no retrieved source establishes a tool-count cutoff, and retrieval risks never shortlisting the right tool. *Tradeoff:* an eval is upfront work; the alternative is a number with no evidence behind it.
4. **Treat every tool result — including sub-agent output — as untrusted, inspecting network-derived results before context entry.** *Rationale:* a poisoned return leaves no post-hoc signal. *Tradeoff:* latency, plus a classifier that must not be mistaken for a boundary.
5. **Build the deterministic boundary first, layer application-level constraint and model-layer defence above it, and state the mechanism whenever quoting a safety number.** *Rationale:* boundaries bound capability rather than tendency, CaMeL adds provable properties above them, and ~93% approval (telemetry) versus ~83%/~17% (classifier accuracy) are not attack-mitigation rates. *Tradeoff:* isolation reduces observability, so budget OTLP export.
6. **Implement the MCP `2026-07-28` authorization checklist as written, and add application-level idempotency keys with deterministic tool ordering.** *Rationale:* PKCE-or-refuse, `resource` plus audience validation, RFC 9207 response validation, exact redirect URIs, per-client proxy consent and no token passthrough are MUSTs with named attacks behind them, while `idempotentHint` is unverifiable. *Tradeoff:* integration work, and SSE resumability is gone so long calls need application-level retry.
7. **Scope any computer-use proposal to short, verifiable, recoverable steps, treating security as the binding constraint.** *Rationale:* 20.6% bounds multi-hour workflow autonomy specifically, while 76.67–100% pop-up payload delivery says the failure arriving first is adversarial, not capability. *Tradeoff:* rules out long-horizon GUI autonomy, leaving narrow uses open to evaluation.

---

## 7. Sources

All URLs retrieved 2026-08-03. Vendor engineering posts are primary *for their own systems*; their benchmark numbers are **claims**, and where model, harness, task count or date is unstated I label them vendor-internal undisclosed rather than treating them as measurements.

| # | Title | Org · Date · Type | URL |
| --- | --- | --- | --- |
| 1 | Key Changes (specification changelog) | Model Context Protocol · 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/changelog |
| 2 | Multi Round-Trip Requests | Model Context Protocol · rev. 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr |
| 3 | Schema Reference (`Tool`, `ToolAnnotations`) | Model Context Protocol · rev. 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/schema |
| 4 | Authorization Security Considerations | Model Context Protocol · rev. 2026-07-28 · spec | https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations |
| 5 | `modelcontextprotocol/registry` README | MCP community · preview 2025-09-08 · primary | https://github.com/modelcontextprotocol/registry |
| 6 | Writing effective tools for agents — with agents | Anthropic · 2025-09-11 · primary; SOTA claim unquantified | https://www.anthropic.com/engineering/writing-tools-for-agents |
| 7 | Introducing advanced tool use on the Claude Developer Platform | Anthropic · 2025-11-24 · vendor claims; harness undisclosed | https://www.anthropic.com/engineering/advanced-tool-use |
| 8 | Code execution with MCP | Anthropic · 2025-11-04 · vendor claims | https://www.anthropic.com/engineering/code-execution-with-mcp |
| 9 | Beyond permission prompts | Anthropic · 2025-10-20 · primary; 84% is internal usage | https://www.anthropic.com/engineering/claude-code-sandboxing |
| 10 | How we contain Claude across products | Anthropic · 2026-05-25 · primary | https://www.anthropic.com/engineering/how-we-contain-claude |
| 11 | Piloting Claude in Chrome | Anthropic · 2025-08-25 · primary; model version undisclosed | https://claude.com/blog/claude-for-chrome |
| 12 | Computer use tool | Anthropic docs · current | https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool |
| 13 | Function calling | OpenAI docs · current | https://developers.openai.com/api/docs/guides/function-calling |
| 14 | Operator System Card | OpenAI · 2025-01-23 · primary; foundational (earliest published injection-monitor measurement for a shipped computer-use agent) | https://cdn.openai.com/operator_system_card.pdf |
| 15 | What are agents? (conceptual guide) | Hugging Face smolagents docs · v1.26.0 · framework doctrine, not measurement | https://huggingface.co/docs/smolagents/en/conceptual_guides/intro_agents |
| 16 | Sandboxing AI agents, 100x faster | Cloudflare · 2026-03-24 · vendor claims | https://blog.cloudflare.com/dynamic-workers/ |
| 17 | E2B infra — `docs/ARCHITECTURE.md` | E2B · current | https://github.com/e2b-dev/infra/blob/main/docs/ARCHITECTURE.md |
| 18 | Executable Code Actions Elicit Better LLM Agents | Wang et al., arXiv 2402.01030 · Feb 2024 · foundational | https://arxiv.org/abs/2402.01030 |
| 19 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | Yang et al., arXiv 2405.15793 · May 2024 · foundational | https://arxiv.org/abs/2405.15793 |
| 20 | LongFuncEval: Measuring the effectiveness of long context models for function calling | Kate et al. (IBM Research), arXiv 2505.10570 · May 2025 · primary | https://arxiv.org/html/2505.10570 |
| 21 | Defeating Prompt Injections by Design (CaMeL) | arXiv 2503.18813 · Mar 2025 · foundational | https://arxiv.org/abs/2503.18813 |
| 22 | Design Patterns for Securing LLM Agents against Prompt Injections | arXiv 2506.08837 · Jun 2025 · primary | https://arxiv.org/abs/2506.08837 |
| 23 | CaMeLs Can Use Computers Too | arXiv 2601.09923 · Jan 2026 · primary | https://arxiv.org/abs/2601.09923 |
| 24 | How Many Tools Should an LLM Agent See? | Repantis et al. (Meta), arXiv 2605.24660 · May 2026 · primary | https://arxiv.org/abs/2605.24660 |
| 25 | Beyond Function Calling: Tool-Using Agents under Tool-Environment Unreliability | Tian et al., arXiv 2606.25819 · Jun 2026 · primary | https://arxiv.org/abs/2606.25819 |
| 26 | OSWorld 2.0 | XLANG Lab et al., arXiv 2606.29537 · Jun 2026 · primary | https://arxiv.org/abs/2606.29537 |
| 27 | OSWorld-Human | MLSys 2026 proceedings · 2026 · primary | https://proceedings.mlsys.org/paper_files/paper/2026/file/5edb57c05c81d04beb716ef1d542fe9e-Paper-Conference.pdf |
| 28 | SecureWebArena: A Holistic Security Evaluation Benchmark for LVLM-based Web Agents | Ying et al., Findings of ACL 2026, pp. 11986–11998 · primary | https://aclanthology.org/2026.findings-acl.582.pdf |
| 29 | MCP at First Glance | Hasan et al., arXiv 2506.13538 · Jun 2025 · primary | https://arxiv.org/abs/2506.13538 |
| 30 | OWASP Top 10 for Agentic Applications for 2026 | OWASP GenAI Security Project · 2025-12-09 · standard | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| 31 | SP 800-53 Control Overlays for Securing AI Systems | NIST CSRC · 2025-08-14 · standard | https://csrc.nist.gov/projects/cosais |
| 32 | The lethal trifecta for AI agents | Simon Willison · 2025-06-16 · secondary | https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ |
| 33 | Code Execution with MCP (replication; 2 query types, GPT-4.1, Bright Data disclosed as customer) | Sezer & Alper, AIMultiple · 2026-06-24 · secondary | https://aimultiple.com/code-execution-with-mcp |
| 34 | Record and Replay Testing for AI Agents | dreaming.press · 2026 · secondary | https://dreaming.press/posts/record-replay-testing-for-ai-agents.html |

---

## 8. Proposed content for final doc sections

**§7 — Tool & environment interface.** Open with the bifurcation rather than a tool list: `strict` schema calling as the default, code-as-action as an experiment whose cutover point the team measures. Then the ergonomics checklist; the three degradation channels, noting no public threshold exists; MCP 2026-08 as a what-changed/what-to-do table with authorization as its own subsection; then environment — filesystem-as-workspace, PII tokenisation, substrate as threat-model choice, git-as-checkpoint. Close on determinism, stating both that `idempotentHint` exists and that it is unverifiable, plus a scoped computer-use paragraph separating the two ceilings.

**§11 (tool-security part).** Lead with the reframing — **an allowlist is a capability grant, not a destination filter** — via the documented bypass and its in-VM proxy fix. Then the mechanism-labelled table, where every number carries what it measures and its denominator, so a classifier catch rate is never read as an attack-mitigation rate. Then the three seam rules, the MCP authorization MUSTs, and the ASI02/ASI05 mapping.
