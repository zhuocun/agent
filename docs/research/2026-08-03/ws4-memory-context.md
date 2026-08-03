# WS4 — Memory & context architecture
**Scope:** context construction, compaction, externalized state, retrieval, long-term memory, memory safety, and evaluation | **Access date: 2026-08-03** | **Sibling workstreams deferred to:** WS1 for the loop's use of context; WS3 for retrieval implemented as a tool call; WS6 for memory benchmarks beyond the three discussed here

## 1. Executive summary

- **[high] “Memory” is not one store.** Shipped systems increasingly separate the active context window, run-local ledgers, durable conversation history, extracted facts, learned instructions/skills, and files/artifacts. However, no reviewed product exposes the full cognitive taxonomy as six clean primitives; most collapse episodic and semantic memory into text records or retrieval stores, while procedural memory appears as instruction/skill files.
- **[high] Nominal context is capacity, not reliable working memory.** Controlled studies show degradation with length even when retrieval is easy or perfect. The engineering objective is therefore the smallest sufficient, high-signal context—not filling the advertised window.
- **[high] Compaction is necessary but lossy.** Preserve constraints, decisions, unresolved issues, open todos, current state, evidence, and artifact pointers; keep the raw transcript separately. Clearing/summarizing old content can invalidate prefix caches, so compact in meaningful batches.
- **[medium] Retrieval is becoming routed and iterative.** Hybrid lexical+dense retrieval with reranking remains the production baseline. Grep-and-read is strong for exact, current, inspectable corpora; iterative agentic retrieval helps multi-hop or underspecified questions but adds model calls, latency, and failure surface.
- **[high] Persistent memory is a security boundary.** Tenant scope, source provenance, temporal validity, user review/deletion, and write authorization are first-class requirements. Untrusted webpages, documents, or repository text must not silently become user preferences or procedural rules.
- **[medium] Self-improving memory remains promising but incompletely validated.** Reflection, background consolidation, reusable plans, and learned memory-control policies have positive task-suite results, but evidence is still narrow relative to months-long, multi-user production behavior.

## 2. Findings

### 2.1 The practised layered model

**[high] A useful 2026 decomposition is:**

| Layer | Typical shipped representation | Lifetime / writer | What is actually shipped |
|---|---|---|---|
| Working context | Prompt messages, tool results, reasoning state | One inference/turn; harness | Universal. OpenAI Responses can preserve reasoning/tool state across calls; Claude exposes explicit context curation.[S1][S6] |
| Scratchpad / run state | Plan, todo list, progress ledger, budgets | One run; model + deterministic runtime | Common in agent harnesses, often as messages, structured state, or files—not “long-term memory.” Claude Code keeps pending tasks in compaction summaries.[S5] |
| Episodic | Transcripts, timestamped events, successful trajectories | Cross-run; append or background extractor | Letta recall memory, LangMem episode collections, and benchmarked memory agents implement variants.[S14][S18][S25] |
| Semantic | User facts/preferences, entity relations, current profiles | Cross-thread; extractor or explicit user write | ChatGPT saved/chat-history memory, Mem0 fact records, Zep temporal graph, LangMem profiles/collections.[S7][S13][S17][S25] |
| Procedural | Prompt rules, skills, reusable plans/code | Cross-run; developer or reviewed learner | Claude Code `CLAUDE.md`, auto-memory and skills; LangMem prompt optimization. Autonomous mutation exists, but governance is immature.[S5][S25] |
| External artifacts | Files, notes, plans, patches, databases, object-store outputs | Task/project; tools and humans | Anthropic’s memory tool is literally client-owned files; Claude Code reloads durable instruction/memory files and loads skills on demand.[S4][S5] |

The taxonomy is descriptive, not proof of human-like cognition. A transcript can be episodic at write time, a summary can become semantic, and a saved playbook can be procedural. The operational distinctions that matter are **scope, authority, mutability, retrieval policy, provenance, and deletion behavior**.[S15]

### 2.2 Context rot and effective context

**[high] Longer input can reduce use of information well before the hard limit.** Chroma’s July 2025 controlled report held task difficulty constant across 18 models—including Claude Sonnet 4, GPT-4.1, Gemini 2.5, and Qwen3 variants—and varied semantic similarity, distractors, haystack structure, LongMemEval histories, and repeated-word tasks. Performance degraded non-uniformly across experiments; this is a technical report with reproducible tooling, not an independent leaderboard.[S8]

NoLiMa removed literal question–needle overlap; 13 models claiming at least 128K context degraded markedly as length grew. The important result is not a universal “effective window” number but that effective context depends on task, cue quality, distractors, and evidence structure.[S9] Du et al. went further: on math, QA, and coding, five models—Llama-3.1-8B-Instruct, Mistral-7B-Instruct-v0.3, GPT-4o, Claude 3.7 Sonnet, and Gemini 2.0 (closed-model API snapshots not fully pinned)—lost **13.9%–85%** as input length increased even with perfect evidence recitation, whitespace, masked distractors, or evidence adjacent to the question. Reporter: Du et al.; Findings of EMNLP, November 2025.[S10]

Google’s own Gemini 2.5 report illustrates nominal/effective separation: **Gemini 2.5 Pro**, MRCR-v2 eight-needle harness, reported by Google in July 2025, scored **58.0% cumulative through 128K** but **16.4% pointwise at exactly 1M**. This is vendor-reported and the two aggregation modes differ, so it is evidence of residual headroom, not a cross-model ranking.[S11]

### 2.3 Compaction, loss, and cache economics

**[high] Compaction should be an explicit state transition, not invisible forgetting.** Anthropic’s current server-side API defaults to a 150,000-input-token trigger (minimum 50,000), writes a `compaction` summary block, and discards earlier blocks on continuation. Custom instructions replace—not augment—the default summary prompt.[S2] Anthropic recommends retaining architectural decisions, unresolved bugs, implementation details, state and next steps while dropping redundant tool output.[S1]

Claude Code documents concrete loss: full tool outputs and intermediate reasoning disappear; conversation-only instructions can be summarized away; path-scoped rules and nested instruction files are absent until relevant files are read again. Root instructions, auto-memory, and invoked skills are re-injected, though skills have size caps.[S5] Recovery therefore means re-reading authoritative artifacts, checking the run ledger, and, where available, rewinding/forking from the raw transcript—not asking a summary to reconstruct absent detail.

**[high] Cache tradeoff:** editing old tool/thinking blocks invalidates the cached prefix at the edit point. Anthropic advises clearing enough tokens to justify a new cache write (`clear_at_least`) rather than repeatedly pruning tiny amounts; retaining thinking blocks preserves cache hits but consumes context.[S3] Normatively, compact at phase boundaries or at a measured attention threshold, batch removals, and preserve stable policy/tool prefixes. The tradeoff is larger prompts and context rot versus cache churn and summarization loss.

### 2.4 Files and artifacts as memory

**[high] Files beat an ever-growing prompt for long-horizon work because they are durable, selectively readable, addressable, diffable, and inspectable by humans and tools.** The active prompt becomes a cache of relevant slices; the filesystem/object store remains the source of record. Anthropic’s memory tool uses create/read/update/delete operations under a client-mapped `/memories` namespace, while Claude Code loads persistent memory and procedural files on demand.[S4][S5] MemGPT’s foundational virtual-memory analogy—page between scarce context and external storage—remains accurate even as windows grow.[S12]

This does not make files automatically safe or current. They need schemas or conventions, ownership, timestamps, provenance, access control, compaction/archival, and retrieval. A concise plan/todo file should point to evidence and artifacts rather than duplicate them.

### 2.5 Retrieval: static, hybrid, and agentic

**[high] The baseline remains hybrid retrieval.** Exact identifiers and code symbols favor grep/BM25; paraphrases favor embeddings; reranking reduces what enters context. Anthropic’s September 2024 vendor evaluation used code, fiction, scientific and financial corpora, Gemini Text 004 embeddings, BM25, recall@20, and a Cohere reranker: contextual embeddings+BM25 reduced top-20 failure from 5.7% to 2.9% (49% relative), and reranking to 1.9% (67%). These are vendor measurements, not universal production gains.[S22]

**[medium] Route by query rather than select one ideology.** Grep-and-read is attractive for live code/files: no stale embedding build, exact line-level verification, and transparent follow-up reads. Dense/hybrid RAG is better for large stable corpora and semantic recall. Iterative agentic search is justified when the agent must reformulate, decompose, follow entities, or test evidence sufficiency. Agentic-R reports consistent gains across seven single- and multi-hop QA benchmarks, but repeated retrieval/model turns make it slower and costlier.[S24] Older comparative work found full long context stronger when sufficiently resourced, RAG cheaper, and routing between them competitive—still a useful foundation despite older models.[S23] WS3 should own the actual tool contract.

### 2.6 Long-term writes, conflicts, forgetting, and learning

**[medium] Who writes memory is unresolved.** Agent-issued writes are timely and interpretable but compete with task execution and are injection-prone. Background extractors avoid hot-path latency and can consolidate globally, but introduce delay and a second fallible model. Letta ships a separate sleep-time agent; LangMem supports hot-path and background formation.[S14][S25]

Mem0’s concrete policy retrieves similar records and asks GPT-4o-mini to choose `ADD`, `UPDATE`, `DELETE`, or `NOOP`; Zep instead keeps bi-temporal facts and closes an old fact’s validity interval when contradicted.[S13][S17] The latter is more auditable than destructive overwrite. TTL should be class-specific: short for inferred situational preferences, longer for explicit stable preferences, and absent for immutable provenance logs. Per-user memory should be the default; organization memory should require an explicit shared namespace and curated write path.

**[medium] Self-improvement has evidence, not closure.** Sleep-time compute and LangMem procedural optimization turn episodes into learned context or prompt rules, but evaluation is mostly controlled reasoning/coding tasks.[S14][S25] MemCon, a July 15, 2026 preprint, learns when to retrieve, inject a plan, re-retrieve, consolidate, forget, or do nothing. Across six named benchmarks, three frameworks, and GPT-4.1-mini, Claude Sonnet-4, and DeepSeek-V3.2, its authors report gains up to **15.2 task-success points** and **5–20% fewer tokens** versus memory baselines. This is author-reported preprint evidence, not validation of unconstrained self-modifying production agents.[S16]

### 2.7 Privacy, tenancy, correctness, and evaluation

**[high] Memory amplifies prompt injection across time.** A May 2026 preprint demonstrates “sleeper” poisoning from external documents/webpages/repositories: fabricated user memories can be stored, retrieved in later sessions, and influence later actions. Exact attack rates are model- and harness-specific, but the demonstrated write→retrieve→use chain is sufficient to treat memory writes as privileged operations.[S19]

Required controls are: tenant-bound keys and caches; source/actor and derivation lineage; valid-time plus observed-time; explicit versus inferred labels; confidence; write ACLs; user-visible list/edit/delete/disable controls; incognito/no-memory sessions; and deletion propagation from source to derived facts. ChatGPT’s separate saved-memory/chat-history controls and Temporary Chat are useful shipped UX patterns, though product documentation is not evidence of backend correctness.[S7]

LoCoMo (10 human-edited long conversations) and LongMemEval (500 questions over scalable timestamped histories) established conversational recall, temporal reasoning, update, and abstention tests.[S20][S21] MemoryAgentBench advances to incremental multi-turn ingestion and four competencies: retrieval, test-time learning, long-range understanding, and selective forgetting.[S18] They still under-measure procedural task success, poisoning, cross-tenant isolation, deletion lineage, months-long drift, cost/latency under continuous writes, and whether a recalled statement was appropriate to use. LLM-as-judge and synthetic-history dependence further limit product-level conclusions. WS6 should expand the benchmark treatment.

## 3. Delta since 2026-07-14

The prior pass had four layers—turn scratch, orchestration state, thread, and long-term user/org—and correctly recommended externalized plans and worker artifacts. This pass adds:

1. **A sharper split of long-term state:** episodic records, semantic facts, procedural skills, and authoritative artifacts should not share one policy or deletion model.
2. **Concrete compaction semantics:** Anthropic’s current API exposes a 150K default trigger, custom summary instructions, pause-after-compaction, and explicit cache-invalidation tradeoffs; Claude Code now documents exactly what reloads and what is lost.[S2][S3][S5]
3. **Measured effective-context evidence:** post-prior evidence synthesis distinguishes advertised capacity from task-dependent useful context, including degradation despite perfect retrieval.[S8][S10]
4. **Adaptive memory control:** MemCon appeared July 15, 2026, one day after the prior pass, as early evidence for learned retrieve/consolidate/forget policies.[S16]
5. **Security and governance:** the prior section did not cover poisoning, temporal invalidation, tenant namespaces, user controls, or deletion lineage; these are now design requirements.[S17][S19]

## 4. Contested / open questions

- **[medium] Taxonomy versus implementation:** are episodic/semantic/procedural labels useful engineering boundaries or cognitive metaphors that hide shared text-store mechanics?
- **[medium] Writer authority:** should the acting model write memory, should a background model propose it, or should deterministic extraction/user confirmation gate durable writes? The answer likely varies by memory class.
- **[medium] Summaries versus raw episodes:** summaries reduce cost but erase detail and can fossilize inference errors; raw episodes preserve evidence but increase retrieval noise.
- **[medium] Graphs versus strong hybrid retrieval:** temporal graphs aid point-in-time conflict handling, but graph extraction adds LLM cost/errors. No reviewed evidence establishes graphs as a universal default.
- **[low] Learned controllers:** MemCon-style policies are promising, but online exploration, reward misspecification, non-stationary model versions, and rollback remain open.
- **[high] “Forget” semantics:** hiding a memory from retrieval, deleting a derived fact, deleting the source, cache expiry, and legal erasure are different operations and need separate contracts.

## 5. Anti-patterns & failure modes

1. **Transcript-as-memory:** replaying everything maximizes cost and context rot; use recent turns plus retrieval.
2. **Summary-as-source-of-truth:** compaction can omit exact evidence; retain immutable raw events/artifacts and cite them.
3. **One global memory bucket:** causes cross-user leakage and mixes preferences, business facts, episodes, and procedures.
4. **Untrusted-content writes:** a webpage or repository instruction becomes a user preference or skill; gate writes by origin and memory class.
5. **Embedding-only retrieval:** misses identifiers, negation, dates, and exact symbols; combine lexical, metadata, dense, and reranking.
6. **Destructive contradiction handling:** replacing an old fact loses history; close validity intervals and preserve provenance.
7. **Tiny frequent compactions:** repeatedly invalidates prefix caches and compounds summary loss; batch at meaningful thresholds.
8. **Unreviewed procedural self-modification:** a bad episode rewrites global behavior; stage, diff, evaluate, approve, and roll back skills.
9. **Deletion without lineage:** removing a chat but retaining extracted facts violates user expectations and can create stale “ghost” memory.

## 6. Design implications

**Normative recommendation [high]: implement a typed memory plane, not a generic `memories` table.** Use separate namespaces and policies for `(tenant, user, project, agent, memory_class)`. Store immutable episode/source IDs; version semantic facts with `valid_from`, `valid_to`, `observed_at`, provenance and confidence; store procedures as reviewed, versioned artifacts. Tradeoff: more schema and lifecycle work, but materially better isolation, auditability, conflict resolution, and deletion.

**Context assembly order [high]:** stable policy/tool prefix → current request → pinned constraints → run ledger/open todos → small retrieved semantic/episodic set → artifact excerpts → recent turns. Give each section a token budget and record why every retrieved item was included. Do not let retrieved memory outrank current explicit user instructions or system policy.

**Compaction protocol [high]:** trigger by measured token/quality thresholds and phase boundaries; preserve objective, constraints, decisions with rationale, unresolved questions, todos/owners, current state, test evidence, and artifact/source pointers. Keep raw history outside the prompt. After compaction, run a cheap continuity check against the ledger and re-read authoritative files. Batch enough removal to amortize cache invalidation.

**Retrieval router [medium]:** exact identifiers/current repository → grep/BM25; semantic recall → dense+metadata; high-value candidate set → rerank; multi-hop/ambiguous query → bounded iterative search; small stable corpus → cached long context. Tradeoff: routing complexity versus avoiding the worst cost/quality mode for every query.

**Write path [high]:** classify origin first. Explicit user facts may become proposed semantic memory; model inferences require lower confidence/TTL or confirmation; third-party/tool content may become source-attributed episodic evidence but must not become user preferences or procedures. Resolve conflicts temporally rather than silently overwriting. Provide inspect/edit/delete/disable and no-memory modes, plus derived-data deletion.

**Self-improvement [medium]:** begin with offline reflection that proposes skill diffs; require regression evals and human/policy approval before global activation. Permit automatic low-risk per-project notes with TTL and rollback. This captures reuse benefits while limiting reward hacking and persistent corruption.

## 7. Sources

| ID | Title | Publishing organization | Date on source | Type / note |
|---|---|---|---|---|
| S1 | [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Anthropic | 2025-09-29 | Primary engineering guidance |
| S2 | [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) | Anthropic | n.d.; beta version `2026-01-12` | Live product docs |
| S3 | [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) | Anthropic | n.d.; beta versions dated 2025 | Live product docs; cache behavior |
| S4 | [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) | Anthropic | n.d. | Live product docs |
| S5 | [Explore the context window](https://code.claude.com/docs/en/context-window) | Anthropic, Claude Code | n.d.; behavior notes v2.1.198 | Live product docs |
| S6 | [Why we built the Responses API](https://developers.openai.com/blog/responses-api) | OpenAI Developers | n.d. | Primary vendor architecture post; claims not independent measurements |
| S7 | [Memory and new controls for ChatGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | OpenAI | 2025-04-10; updated 2025-06-03 | Primary product post |
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
| S22 | [Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | Anthropic | 2024-09-19 | Vendor retrieval evaluation; foundational |
| S23 | [Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach](https://aclanthology.org/2024.emnlp-industry.66/) | Association for Computational Linguistics | 2024-11 | Peer-reviewed RAG/LC comparison; foundational |
| S24 | [Agentic-R: Learning to Retrieve for Agentic Search](https://aclanthology.org/2026.findings-acl.785/) | Association for Computational Linguistics | 2026-07 | Peer-reviewed Findings paper |
| S25 | [Long-term Memory in LLM Applications — Core Concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) | LangChain / LangMem | n.d. | Shipped framework docs; vendor guidance |

## 8. Proposed content for final doc sections

For final-doc §8, lead with this claim: **context is a task-scoped working set assembled from typed, durable memory—not the memory system itself.**

Recommended subsections:

1. **Six-layer architecture:** working context; run ledger; episodic events; semantic facts; procedural skills; external artifacts. Include scope, authority, write policy, retrieval, and deletion per layer.
2. **Context builder:** deterministic priority order and per-section token budgets; effective context is task-dependent and smaller than nominal capacity.
3. **Compaction contract:** phase/threshold triggers, mandatory preserved fields, raw-history retention, post-compaction continuity check, and prefix-cache tradeoff.
4. **Retrieval router:** grep/BM25, dense+metadata, reranking, bounded agentic search, and cached long-context fallback; defer tool mechanics to WS3.
5. **Memory lifecycle:** candidate write → provenance/tenant gate → conflict/temporal update → retrieval → TTL/consolidation → user-visible deletion.
6. **Safety and evaluation:** untrusted-content poisoning, cross-tenant isolation, audit UI, no-memory mode, and an eval matrix covering recall, update/forgetting, procedural task success, poisoning, deletion, cost, and drift; defer benchmark catalog depth to WS6.
