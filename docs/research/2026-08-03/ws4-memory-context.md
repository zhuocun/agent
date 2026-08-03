# WS4 — Memory & context architecture
**Scope:** context construction, compaction, externalized state, retrieval, long-term memory, memory safety, and evaluation | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS1 for the loop's use of context; WS3 for retrieval implemented as a tool call; WS6 for benchmark-catalog depth

## 1. Executive summary

- **[high] “Memory” is not one store.** Systems separate active context, run ledgers, history, extracted facts, instructions/skills, and artifacts. No reviewed product exposes six clean primitives; most collapse episodic and semantic memory into text/retrieval stores.
- **[high] Nominal context is capacity, not reliable working memory.** Controlled studies show degradation with length even when retrieval is easy or perfect. The engineering objective is therefore the smallest sufficient, high-signal context—not filling the advertised window.
- **[high] Compaction is necessary but lossy.** Preserve constraints, decisions, unresolved issues, todos, evidence, and restorable artifact pointers; keep raw events separately. Rewriting context can invalidate prefix caches and, when repeated, cause “context collapse,” so compact deliberately and prefer local delta updates.
- **[medium] Retrieval is routed and sometimes iterative.** Hybrid lexical+dense retrieval plus reranking remains the baseline; grep-and-read suits exact live corpora, while iterative retrieval helps multi-hop questions but adds calls and failures.
- **[high] Persistent memory is a security boundary.** Tenant scope, provenance, temporal validity, review/deletion, and write authorization are first-class requirements. Origin labels help but are not a gate: query-only and retrieval-trigger attacks can poison apparently ordinary interactions.
- **[medium] Self-improving memory remains promising but incompletely validated.** Reflection, background consolidation, reusable plans, and learned memory-control policies have positive task-suite results, but evidence is still narrow relative to months-long, multi-user production behavior.

## 2. Findings

### 2.1 The practised layered model

**[high] A useful 2026 decomposition is:**

| Layer | Typical shipped representation | Lifetime / writer | What is actually shipped |
|---|---|---|---|
| Working context | Prompt messages, tool results, reasoning state | One inference/turn; harness | Universal. OpenAI Responses can preserve reasoning/tool state across calls; Claude exposes explicit context curation.[S1][S6] |
| Scratchpad / run state | Plan, todo list, progress ledger, budgets | One run; model + deterministic runtime | Common as messages, state, or files—not “long-term memory.” Claude Code preserves pending tasks in summaries; Manus recites `todo.md` to refresh attention.[S5][S34] |
| Episodic | Transcripts, timestamped events, successful trajectories | Cross-run; append or background extractor | Letta recall memory, LangMem episode collections, and benchmarked memory agents implement variants.[S14][S18][S25] |
| Semantic | User facts/preferences, entity relations, current profiles | Cross-thread; extractor or explicit user write | ChatGPT’s synthesized memory, Mem0 fact records, Zep temporal graph, LangMem profiles/collections.[S7][S13][S17][S25] |
| Procedural | Prompt rules, skills, reusable plans/code | Cross-run; developer or reviewed learner | Claude Code `CLAUDE.md`, auto-memory and skills; LangMem prompt optimization. Autonomous mutation exists, but governance is immature.[S5][S25] |
| External artifacts | Files, notes, plans, patches, databases, object-store outputs | Task/project; tools and humans | Anthropic’s memory tool is client-owned files; Claude Code and Manus reload durable files on demand.[S4][S5][S34] |

The taxonomy is descriptive, not cognitive. Records can change class as episodes become summaries or playbooks. Engineering boundaries are **scope, authority, mutability, retrieval, provenance, and deletion**.[S15]

### 2.2 Context rot and effective context

**[high] Longer input can fail before the hard limit.** Chroma’s July 2025 report varied similarity, distractors, haystack structure, LongMemEval histories, and repeated words across 18 models; degradation was non-uniform. It is reproducible, not an independent leaderboard.[S8]

NoLiMa removed literal question–needle overlap. At 32K, **11 of 13** ≥128K models fell below 50% of their short-context baseline; GPT-4o fell from **99.3% to 69.7%** (API snapshot unpinned). Reporter: Modarressi et al., ICML, July 2025.[S9] Du et al. found **13.9%–85%** losses on math, QA, and coding across five named models despite perfect evidence recitation/placement; closed snapshots were not fully pinned. Reporter: Findings of EMNLP, November 2025.[S10]

Vendor evidence points the same way: Google reported Gemini 2.5 Pro at **58.0% cumulative through 128K** versus **16.4% pointwise at 1M** on its July 2025 MRCR-v2 eight-needle harness; different aggregation modes limit comparison.[S11] ATLAS, a May 2026 preprint, improves methodology by profiling 26 models over an 8K–1M grid, separating foundational from application abilities, and integrating score–length curves. Seven models moved at least two ranks between 8K–128K and 8K–1M reporting, supporting capability-by-length profiles over a headline window size.[S35]

### 2.3 Compaction, loss, and cache economics

**[high] Compaction should be an explicit state transition.** Anthropic’s API defaults to a 150,000-input-token trigger (minimum 50,000), emits a `compaction` block, and discards prior blocks; custom instructions replace its summary prompt.[S2] Claude Code says tool output, reasoning, and conversation-only instructions can disappear while durable root memory is re-injected.[S5] Recover by re-reading artifacts and the ledger.

Editing earlier blocks invalidates the downstream cached prefix. Anthropic recommends clearing enough tokens to amortize a new cache write.[S3] Manus reports ~**100:1** input/output and a then-current **10×** cached-input discount—vendor observations, not universal prices. It keeps prefixes stable, retains URL/path recovery pointers, and recites an updated todo near the tail.[S34]

ACE identifies “brevity bias” and “context collapse” from repeated playbook rewrites. Its ICLR 2026 authors use delta updates; the useful mechanism is to append/refine local items, deduplicate, and retain sources rather than generalize from framework-specific scores.[S33]

### 2.4 Files and artifacts as memory

**[high] Files beat an ever-growing prompt for long-horizon work because they are durable, selectively readable, addressable, diffable, and inspectable.** The prompt becomes a cache of relevant slices; the filesystem/object store remains the source of record. Anthropic exposes a client-mapped `/memories` namespace, Claude Code loads persistent files on demand, and Manus explicitly uses files for restorable compression.[S4][S5][S34] MemGPT’s virtual-memory analogy remains accurate as windows grow.[S12]

Files still need conventions, ownership, timestamps, provenance, access control, archival, and retrieval. Plans should point to evidence rather than duplicate it.

### 2.5 Retrieval: static, hybrid, and agentic

**[high] The baseline remains hybrid retrieval.** Exact identifiers favor grep/BM25; paraphrases favor embeddings; reranking limits context. Anthropic’s September 2024 vendor evaluation used **codebases, fiction, arXiv papers, and science papers**—not a financial corpus—plus Gemini Text 004 embeddings, BM25, recall@20, and a Cohere reranker. Contextual embeddings+BM25 reduced top-20 failure from 5.7% to 2.9% (49% relative), and reranking to 1.9% (67%). Only its code dataset is public, so these are not independently generalizable gains.[S22]

**[medium] Route by query rather than select one ideology.** Grep-and-read suits live files and exact verification; hybrid RAG suits large stable corpora and paraphrase; bounded iterative search suits multi-hop questions. Agentic-R supports only the narrower claim that a retriever trained for multi-turn agent search can outperform one-shot retrieval across seven QA benchmarks; it does **not** compare grep or establish production latency/cost.[S24] Older comparative work found full context stronger when sufficiently resourced, RAG cheaper, and routing competitive, but used older models.[S23] WS3 should own tool mechanics and current cost evidence.

### 2.6 Long-term writes, conflicts, forgetting, and learning

**[medium] Who writes memory is unresolved.** Agent writes are timely but injection-prone; background extractors avoid hot-path work but add delay and another fallible model. Letta ships a sleep-time agent; LangMem supports both paths.[S14][S25]

Mem0 asks GPT-4o-mini to choose `ADD`, `UPDATE`, `DELETE`, or `NOOP`; Zep closes a bi-temporal fact’s validity interval when contradicted.[S13][S17] The latter is more auditable than overwrite. TTL should be short for inferred situations, longer for explicit preferences, and absent for immutable provenance. Organization memory needs an explicit shared namespace and curated writes.

**[medium] Self-improvement has evidence, not closure.** Sleep-time compute, LangMem prompt optimization, and ACE turn episodes into context or proposed rules, but tests remain controlled.[S14][S25][S33] MemCon, a July 15, 2026 preprint, learns retrieve/plan/consolidate/forget/no-op decisions and reports improvements across named models and task suites—early author evidence, not validation of unconstrained production self-modification.[S16]

### 2.7 Privacy, tenancy, correctness, and evaluation

**[high] Memory amplifies prompt injection across time.** Sleeper-memory work shows external content stored then activated later; AgentPoison demonstrated retrieval-triggered backdoors at NeurIPS 2024; and MINJA (NeurIPS 2025) injected malicious records through ordinary query-only interaction, without third-party content or direct store access.[S19][S32][S31] Thus source classification is useful audit metadata, not a sufficient write gate.

Controls should include tenant-bound keys/caches; source and derivation lineage; valid/observed time; explicit/inferred labels; write ACLs; policy/content checks; staged procedural writes; user inspect/edit/delete/disable; no-memory sessions; and derived-data deletion. On June 4, 2026, OpenAI replaced its old two-toggle ChatGPT UX with a single memory control, an inspectable/editable summary, and per-response Sources; the view may omit factors. Temporary Chat remains the clean-session control.[S7][S26] The legacy model’s “delete chat ≠ delete saved memory,” and the current requirement to remove data from every surviving source, both support anti-pattern #9.[S26]

LoCoMo’s final ACL set is **10** human-edited conversations averaging **600 turns, 16K tokens, and up to 32 sessions**—not the earlier 300-turn/9K description.[S20] It and LongMemEval established recall, temporal reasoning, update, and abstention tasks, but are qualified foundations. Penfield Labs’ April 2026 independent audit found **99/1,540 score-corrupting LoCoMo errors (6.4%)** and its GPT-4o-mini judge accepted **62.81%** of intentionally wrong vague-but-topical answers.[S27] LongMemEval-S is ~115K tokens per question and explicitly fits 128K models, so frontier systems can treat it as a long-context test; LongMemEval-M (~1.5M) better forces external memory.[S21] MemoryAgentBench adds incremental ingestion and selective forgetting.[S18]

Security evaluation is no longer missing. The 2026 literature includes MEMFLOW control-flow persistence, MPBench write→retrieve attacks, MemLeak deletion leakage, and other suites summarized by MemSecBench.[S28][S29][S30] MemSecBench uses a Write–Execute–Forget lifecycle and tests selective repair across harness, memory, and model backends.[S28] These preprints do not prove product safety, but §8 should adopt and extend their protocols—not present poisoning, leakage, or repair evaluation as novel scaffolding. WS6 should own the full catalog.

## 3. Delta since 2026-07-14

The prior pass had four layers—turn scratch, orchestration state, thread, and long-term user/org—and correctly recommended externalized plans and worker artifacts. This pass adds:

1. **A sharper split of long-term state:** episodic records, semantic facts, procedural skills, and authoritative artifacts should not share one policy or deletion model.
2. **Concrete compaction semantics:** Anthropic’s current API exposes a 150K default trigger, custom summary instructions, pause-after-compaction, and explicit cache-invalidation tradeoffs; Claude Code now documents exactly what reloads and what is lost.[S2][S3][S5]
3. **Measured effective-context evidence:** post-prior evidence synthesis distinguishes advertised capacity from task-dependent useful context, including degradation despite perfect retrieval.[S8][S10]
4. **Adaptive memory control:** MemCon adds learned retrieve/consolidate/forget actions; ACE adds delta-updated playbooks that resist context collapse.[S16][S33]
5. **Security and governance:** memory-security evaluation is now a benchmark family—MEMFLOW, MPBench, MemLeak, MemSecBench—not an empty gap.[S28][S29][S30]
6. **Current product controls:** ChatGPT now has one memory switch, an inspectable summary, response-level sources, and Temporary Chat.[S7][S26]

## 4. Contested / open questions

- **[medium] Taxonomy versus implementation:** are episodic/semantic/procedural labels useful engineering boundaries or cognitive metaphors that hide shared text-store mechanics?
- **[medium] Writer authority:** should the acting model write memory, should a background model propose it, or should deterministic extraction/user confirmation gate durable writes? The answer likely varies by memory class.
- **[medium] Summaries versus raw episodes:** summaries reduce cost but erase detail and can fossilize inference errors; raw episodes preserve evidence but increase retrieval noise.
- **[medium] Delta growth versus rewrite:** ACE-style deltas preserve details but can accumulate contradictions and bloat; full rewrite is smaller but risks context collapse.
- **[medium] Graphs versus strong hybrid retrieval:** temporal graphs aid point-in-time conflict handling, but graph extraction adds LLM cost/errors. No reviewed evidence establishes graphs as a universal default.
- **[low] Learned controllers:** MemCon-style policies are promising, but online exploration, reward misspecification, non-stationary model versions, and rollback remain open.
- **[high] Benchmark validity:** audited label/judge failures make small LoCoMo score deltas uninterpretable; long-context-capable models can bypass retrieval on LongMemEval-S.
- **[high] “Forget” semantics:** hiding a memory from retrieval, deleting a derived fact, deleting the source, cache expiry, and legal erasure are different operations and need separate contracts.

## 5. Anti-patterns & failure modes

1. **Transcript-as-memory:** replaying everything maximizes cost and context rot; use recent turns plus retrieval.
2. **Summary-as-source-of-truth:** compaction can omit exact evidence; retain immutable raw events/artifacts and cite them.
3. **One global memory bucket:** causes cross-user leakage and mixes preferences, business facts, episodes, and procedures.
4. **Origin-only write gates:** query-only MINJA bypasses a third-party-content distinction; validate authorization, intent, content, and memory class.
5. **Embedding-only retrieval:** misses identifiers, negation, dates, and exact symbols; combine lexical, metadata, dense, and reranking.
6. **Destructive contradiction handling:** replacing an old fact loses history; close validity intervals and preserve provenance.
7. **Tiny frequent compactions:** repeatedly invalidates prefix caches and compounds summary loss; batch at meaningful thresholds.
8. **Unreviewed procedural self-modification:** a bad episode rewrites global behavior; stage, diff, evaluate, approve, and roll back skills.
9. **Deletion without lineage:** legacy ChatGPT separated chat deletion from saved-memory deletion; current synthesis can rebuild from surviving sources. Delete or detach all derived and source records explicitly.[S26]

## 6. Design implications

**Normative recommendation [high]: implement a typed memory plane, not a generic `memories` table.** Use separate namespaces and policies for `(tenant, user, project, agent, memory_class)`. Store immutable episode/source IDs; version semantic facts with `valid_from`, `valid_to`, `observed_at`, provenance and confidence; store procedures as reviewed, versioned artifacts. Tradeoff: more schema and lifecycle work, but materially better isolation, auditability, conflict resolution, and deletion.

**Context assembly order [high]:** stable policy/tool prefix → current request → pinned constraints → run ledger/open todos → small retrieved set → artifact excerpts → recent turns. Budget each section and record inclusion reasons. Tradeoff: this improves priority and cache stability but can omit weakly ranked evidence; retain pointers and permit bounded rereads.

**Compaction protocol [high]:** trigger by measured token/quality thresholds and phase boundaries; preserve objective, constraints, decisions/rationale, unresolved questions, todos, evidence, and restorable pointers. Prefer ACE-style delta edits; keep raw history outside the prompt and check continuity against the ledger. Tradeoff: more retained structure and rereads cost tokens, but reduce irreversible loss; batch removals to amortize cache invalidation.

**Retrieval router [medium]:** exact identifiers/current repository → grep/BM25; semantic recall → dense+metadata; high-value candidate set → rerank; multi-hop/ambiguous query → bounded iterative search; small stable corpus → cached long context. Tradeoff: routing complexity versus avoiding the worst cost/quality mode for every query.

**Write path [medium]:** record origin, but do not trust it as the gate: MINJA uses ordinary queries and AgentPoison uses retrieval triggers.[S31][S32] Require namespace authorization plus intent/content/policy checks; treat explicit user facts as candidates, inferences as low-confidence/TTL, and procedural changes as staged diffs. Resolve conflicts temporally and expose inspect/edit/delete/disable/no-memory controls. Tradeoff: stronger gating adds latency and false rejections; tune by memory class and test with existing security suites.

**Self-improvement [medium]:** begin with offline reflection proposing skill diffs; require regression/security evals and human/policy approval before global activation. Allow low-risk project notes with TTL, provenance, and rollback. Tradeoff: review slows adaptation, while autonomous activation compounds reward hacking, brevity bias, and persistent corruption.

## 7. Sources

| ID | Title | Publishing organization | Date on source | Type / note |
|---|---|---|---|---|
| S1 | [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Anthropic | 2025-09-29 | Primary engineering guidance |
| S2 | [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) | Anthropic | n.d.; beta version `2026-01-12` | Live product docs |
| S3 | [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) | Anthropic | n.d.; beta versions dated 2025 | Live product docs; cache behavior |
| S4 | [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) | Anthropic | n.d. | Live product docs |
| S5 | [Explore the context window](https://code.claude.com/docs/en/context-window) | Anthropic, Claude Code | n.d.; behavior notes v2.1.198 | Live product docs |
| S6 | [Why we built the Responses API](https://developers.openai.com/blog/responses-api) | OpenAI Developers | n.d. | Primary vendor architecture post; claims not independent measurements |
| S7 | [ChatGPT release notes — “Memory that stays more up to date”](https://help.openai.com/en/articles/6825453-chatgpt-release-notes) | OpenAI | 2026-06-04 | Primary product release note |
| S8 | [Context Rot: How Increasing Input Tokens Impacts LLM Performance](https://research.trychroma.com/context-rot) | Chroma Research | 2025-07 | Technical report + reproducible toolkit; foundational, just outside recency window |
| S9 | [NoLiMa: Long-Context Evaluation Beyond Literal Matching](https://proceedings.mlr.press/v267/modarressi25a.html) | PMLR / ICML | 2025-07-13–19 | Peer-reviewed benchmark; foundational |
| S10 | [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://aclanthology.org/2025.findings-emnlp.1264/) | Association for Computational Linguistics | 2025-11 | Peer-reviewed Findings paper |
| S11 | [Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities](https://doi.org/10.48550/arxiv.2507.06261) | Google, Gemini Team | 2025-07 | Primary technical report; vendor-reported |
| S12 | [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560v1) | UC Berkeley authors / arXiv | 2023-10 | Foundational virtual-context paper |
| S13 | [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413) | Mem0 authors / ECAI | 2025-04; ECAI 2025 | Paper from vendor authors; results treated as author claims |
| S14 | [Sleep-time Compute: Beyond Inference Scaling at Test-time](https://arxiv.org/abs/2504.13171) | Letta & UC Berkeley authors / arXiv | 2025-04 | Research paper plus shipped Letta architecture |
| S15 | [Rethinking Memory Mechanisms of Foundation Agents in the Second Half: A Survey](https://arxiv.org/html/2602.06052v3) | Multi-institution authors / arXiv | 2026-02, v3 | Recent survey; taxonomy source |
| S16 | [Memory as a Controlled Process: Learned Adaptive Memory Management for LLM Agents](https://arxiv.org/html/2607.13591v1) | UCLA, UW & Northwestern authors / arXiv | 2026-07-15 | Preprint; early learned-control evidence |
| S17 | [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/html/2501.13956) | Zep AI authors / arXiv | 2025-01-20 | Vendor-authored preprint; temporal model |
| S18 | [Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions](https://arxiv.org/abs/2507.05257) | UC San Diego authors / ICLR | 2025-07; ICLR 2026 | Peer-reviewed MemoryAgentBench |
| S19 | [Hidden in Memory: Sleeper Memory Poisoning in LLM Agents](https://arxiv.org/html/2605.15338) | SPAR, ELLIS/MPI, APTA & CISPA authors / arXiv | 2026-05-14 | Security preprint |
| S20 | [Evaluating Very Long-Term Conversational Memory of LLM Agents](https://aclanthology.org/2024.acl-long.747/) | Association for Computational Linguistics | 2024-08 | Peer-reviewed LoCoMo; foundational benchmark |
| S21 | [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://arxiv.org/abs/2410.10813) | UCLA, Tencent AI Lab Seattle & UC San Diego authors / ICLR | 2024-10; ICLR 2025 | Peer-reviewed benchmark; foundational |
| S22 | [Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | Anthropic | 2024-09-19 | Vendor evaluation; only code subset public |
| S23 | [Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach](https://aclanthology.org/2024.emnlp-industry.66/) | Association for Computational Linguistics | 2024-11 | Peer-reviewed RAG/LC comparison; foundational |
| S24 | [Agentic-R: Learning to Retrieve for Agentic Search](https://aclanthology.org/2026.findings-acl.785/) | Association for Computational Linguistics | 2026-07 | Peer-reviewed; narrow retriever-training evidence |
| S25 | [Long-term Memory in LLM Applications — Core Concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) | LangChain / LangMem | n.d. | Shipped framework docs; vendor guidance |
| S26 | [Memory FAQ](https://help.openai.com/en/articles/8590148-memory-in-chatgpt-remembering-what-you-chat-about) | OpenAI | updated 2026-06-04 | Current UX; also documents legacy deletion distinction |
| S27 | [Independent audit of LoCoMo](https://github.com/dial481/locomo-audit) | Penfield Labs | 2026-04 | Reproducible independent audit; human-reviewed |
| S28 | [MemSecBench: Tracking Agent Memory Poisoning from Persistence to Consequence and Repair](https://arxiv.org/abs/2607.27080) | Multi-institution authors / arXiv | 2026-07-29 | Security benchmark preprint |
| S29 | [From Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning Attacks in LLM Agents](https://arxiv.org/abs/2606.04329) | Multi-institution authors / arXiv | 2026-06-04 | MPBench security preprint |
| S30 | [MemLeak: Diagnosing Information Leaks in Multimodal Agent Memory](https://arxiv.org/abs/2606.29788) | Independent authors / arXiv | 2026-06-30 | Deletion-leakage benchmark preprint |
| S31 | [Memory Injection Attacks on LLM Agents via Query-Only Interaction](https://proceedings.neurips.cc/paper_files/paper/2025/hash/42a97bbd9844d2bf68596730af80bcdf-Abstract-Conference.html) | NeurIPS | 2025 | Peer-reviewed MINJA |
| S32 | [AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases](https://proceedings.neurips.cc/paper_files/paper/2024/hash/eb113910e9c3f6242541c1652e30dfd6-Abstract-Conference.html) | NeurIPS | 2024 | Peer-reviewed foundational attack |
| S33 | [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models](https://arxiv.org/abs/2510.04618) | Stanford, SambaNova & collaborators / ICLR | 2025-10; ICLR 2026 | Peer-reviewed ACE; author-reported results |
| S34 | [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/en/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | Manus | 2025-07-18 | Primary production engineering report |
| S35 | [ATLAS: All-round Testing of Long-context Abilities across Scales](https://arxiv.org/abs/2605.28079) | Multi-institution authors / arXiv | 2026-05-27 | Long-context benchmark preprint |

## 8. Proposed content for final doc sections

For final-doc §8, lead with this claim: **context is a task-scoped working set assembled from typed, durable memory—not the memory system itself.**

Recommended subsections:

1. **Six-layer architecture:** working context; run ledger; episodic events; semantic facts; procedural skills; external artifacts. Include scope, authority, write policy, retrieval, and deletion per layer.
2. **Context builder:** deterministic priority order and per-section token budgets; effective context is task-dependent and smaller than nominal capacity.
3. **Compaction contract:** phase/threshold triggers, mandatory preserved fields, raw-history retention, post-compaction continuity check, and prefix-cache tradeoff.
4. **Retrieval router:** grep/BM25, dense+metadata, reranking, bounded agentic search, and cached long-context fallback; defer tool mechanics to WS3.
5. **Memory lifecycle:** candidate write → provenance/tenant gate → conflict/temporal update → retrieval → TTL/consolidation → user-visible deletion.
6. **Safety and evaluation:** start from MemSecBench’s Write–Execute–Forget lifecycle and the MEMFLOW/MPBench/MemLeak family; add tenant-isolation and product-specific authorization cases rather than presenting memory-security evaluation as new. Pair these with audited conversational tests, incremental memory tasks, provenance/deletion assertions, cost, latency, and drift; defer catalog depth to WS6.
