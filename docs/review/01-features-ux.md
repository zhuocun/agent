# Features & UX — Fresh Research + PRD Review (2026-05-27)

**Scope:** Fresh 2025–2026 research on AI-chat features/UX (NEW vs. what's already in `docs/research/01-features-ux.md`), plus a critical review of `docs/prd/01-core-chat-experience.md`.
**Positioning anchor:** transparent, multi-model, privacy-first chat for power users/developers; mobile-web-first; lean text-core MVP (vision/tools/web-search → P1).

**Confidence flags:** **[Verified]** = confirmed against a cited live source consulted this pass · **[Recall]** = general knowledge, not re-verified · **[Uncertain]** = conflicting/fast-moving.

> Sourcing note: many cited pages are secondary (news/blogs/review sites). Patterns are consistent across sources, but exact tier/date/limit specifics should be re-verified against first-party docs before PRD lock — same caveat the existing research carries.

---

## 1. New ideas & opportunities (NOT in the existing docs)

Each item: why it matters for our positioning + MVP/P1/P2 suggestion.

### 1.1 Interactive / generative visualizations as a new *rendering* baseline (not "artifacts")
All three majors shipped in-chat interactive visualizations within ~30 days in 2026: **OpenAI dynamic visual explanations (Mar 10)**, **Anthropic interactive visualizations free across all tiers (Mar 12)**, **Gemini interactive 3D models / physics sims / slider-adjustable charts globally to Pro (Apr 9, 2026)**. The framing is explicit: *"static text responses are giving way to manipulable interfaces… becoming expected functionality rather than a differentiator."* **[Verified]** ([winbuzzer](https://winbuzzer.com/2026/04/10/google-gemini-now-generates-interactive-visualizations-in-ch-xcxwbn/); [TechCrunch I/O 2026](https://techcrunch.com/2026/05/19/google-updates-its-gemini-app-to-take-on-chatgpt-and-claude-at-io-2026/))
- **Why it matters:** The existing docs treat rich rendering as "markdown/code/KaTeX/mermaid" and treat anything richer as Artifacts/Canvas (P2). But the bar moved: lightweight *inline* interactivity (an adjustable chart, a rotatable diagram) is becoming an expected part of the response surface, distinct from a full Canvas. Our renderer architecture should not assume "text + a few static block types."
- **Suggestion: P1.** Don't build a 3D engine for MVP, but design the renderer/message schema to host **typed interactive blocks** (e.g., a chart spec the client renders with sliders) so this is an additive block type, not a rewrite. MVP can ship a static-chart renderer; P1 adds interactivity.

### 1.2 Generative UI / "the agent emits UI, not just text"
The Vercel AI SDK (`streamUI`, AI Elements), CopilotKit, assistant-ui, and the new **MCP Apps UI standard (Jan 2026; supported by ChatGPT, Claude, Goose, VS Code)** all let tools return *interactive UI components* (forms, dashboards, maps) rendered inline. OpenAI's **Apps SDK** surfaces partner apps (Zillow, Spotify, Canva, Figma) as interactive cards inside the conversation. **[Verified]** ([MCP Apps blog](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/); [OpenAI Apps SDK](https://openai.com/index/introducing-apps-in-chatgpt/); [AI SDK GenUI](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces); [dev.to chat-UI-libraries 2026](https://dev.to/alexander_lukashov/i-evaluated-every-ai-chat-ui-library-in-2026-heres-what-i-found-and-what-i-built-4p10))
- **Why it matters:** This is the single biggest *new* UX paradigm since artifacts and it's standardizing on MCP. For a multi-provider product, a UI that can render tool/MCP-returned components is a strong future-proofing wedge — and it's the natural home for our tool/function-calling P1 work.
- **Suggestion: P2** for full generative UI; but **design the message-part model now (MVP)** to be a typed list of parts (text / code / reasoning / tool-call / tool-result / ui-component) rather than a single markdown string. Cheap insurance against a rewrite. (See PRD review §4.3.)

### 1.3 Proactive / ambient briefings (ChatGPT Pulse, Gemini Daily Brief)
**ChatGPT Pulse (Sep 2025)** delivers overnight, proactively-researched personalized morning cards from chats + connected apps. **Gemini Daily Brief (I/O 2026)** is a personalized digest from inbox/calendar/tasks. Both shift chat from reactive to proactive. **[Verified]** ([OpenAI Pulse](https://openai.com/index/introducing-chatgpt-pulse/); [TechCrunch Pulse](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs/); [TechCrunch I/O 2026](https://techcrunch.com/2026/05/19/google-updates-its-gemini-app-to-take-on-chatgpt-and-claude-at-io-2026/))
- **Why it matters:** A genuine new category, but it's connector/agent-heavy and arguably *anti*-privacy-first (requires reading your mail/calendar). Likely a poor fit for our wedge and persona at MVP.
- **Suggestion: P2 / out-of-scope** for now; note it as a deliberate non-goal so the team isn't surprised when incumbents lean into it. Worth a one-line "why we're not doing this (privacy posture)" stance.

### 1.4 "Approve-with-edits" / human-in-the-loop tool-call UI
HITL approval gates are now treated as *standard infrastructure* for agentic actions: pause on a tool call, show a diff/context, allow approve / reject / **approve-with-modifications**. **[Verified]** ([getclaw HITL 2026](https://getclaw.sh/blog/human-in-the-loop-ai-agents-approvals-2026); [agentic-patterns](https://agentic-patterns.com/patterns/human-in-loop-approval-framework/))
- **Why it matters:** Our tool/function-calling is P1. The chat surface needs an approval/permission UI pattern (especially for a privacy-first product — users should consent before a tool reads data or hits an external API). PRD 01 has *no* tool-call/approval UX spec.
- **Suggestion: P1** (lands with tools). But the **streaming "status lines"** spec in PRD 01 §4.1 should be extended now to anticipate *interactive* tool steps (approve/deny), not just passive "Searching…" text.

### 1.5 Branching is back and is now *explicit & first-party* (this contradicts the docs — see §3.1)
ChatGPT shipped **"Branch in new chat"** (hover → More actions → Branch in new chat) in **Sep 2025**, copying the original history into a new thread and leaving the source intact; rolled out to web + iOS/Android. **[Verified]** ([OpenAI on X](https://x.com/OpenAI/status/1963697012014215181); [TechTimes](https://www.techtimes.com/articles/311823/20250906/chatgpt-introduces-conversation-branching.htm))
- **Why it matters:** Explicit branching is now table-stakes-ish among power-user tools (LibreChat/LobeChat fork-from-any-message), and it's *exactly* our persona. The docs mis-frame branching as something incumbents "retreated from."
- **Suggestion: P1, not P2.** The "branch in new chat" model is far simpler than an in-thread tree (it's a copy-on-branch), low-risk, and directly serves dev/power users. Strongly consider pulling forward.

### 1.6 Composer affordances we're under-weighting
- **Re-attach recently used files** (Grok) and a **sketchpad/drawing-as-prompt** (Grok) — low-cost composer wins. **[Verified]** ([Zapier best chatbots 2026](https://zapier.com/blog/best-ai-chatbot/))
- **Inline composer toggles** (DeepSeek/Gemini "Create" menu) are increasingly the *primary* mode-switch UI vs. a model dropdown. **[Verified]** ([Zapier](https://zapier.com/blog/best-ai-chatbot/))
- **Suggestion:** "re-attach recent file" → **P1** (lands with attachments). Sketchpad → **P2**. Worth noting the composer-toggle pattern as the future home for our P1 web-search/reasoning toggles.

### 1.7 Cross-tool memory *import* and a transparent memory ledger
Claude shipped **automatic chat memory on ALL plans incl. free (Mar 2, 2026)**, with a viewable/editable ledger (Settings → Capabilities → Memory), an explicit "I'm using a memory" acknowledgment, and **cross-platform memory import from ChatGPT/Gemini/Grok**. ChatGPT added **"Memory sources" (May 2026)** showing which memories informed a response. **[Verified]** ([Claude memory help](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context); [LumiChats memory 2026](https://lumichats.com/blog/claude-memory-2026-complete-guide-how-to-use); [willfrancis import guide](https://willfrancis.com/move-memory-from-chatgpt-to-claude/))
- **Why it matters:** Memory is no longer a paid differentiator — it's a free baseline, and the *transparency layer* (show what's stored, show what was used) is exactly our brand. A **transparent memory ledger + "memory used here" indicator + import from competitors** is an on-thesis differentiator, not generic memory.
- **Suggestion:** Memory itself stays **P1** (per PRD 00), but spec the **transparency/ledger UX** as the differentiated part, and consider **memory import** as a cheap acquisition lever (P1/P2). Migration-in is a recurring 2026 theme (many "switch from ChatGPT to Claude" guides).

### 1.8 Response structure beyond "wall of text" (Gemini Neural Expressive)
Gemini's I/O 2026 redesign formats answers as **key info bolded at top, then progressive detail (images/timelines) on scroll** — a deliberate "no wall of text" answer-layout pattern. **[Verified]** ([TechCrunch I/O 2026](https://techcrunch.com/2026/05/19/google-updates-its-gemini-app-to-take-on-chatgpt-and-claude-at-io-2026/))
- **Why it matters:** This is an answer-*layout* idea (TL;DR-first, progressive disclosure within a single answer), distinct from the reasoning panel. Cheap, high-perceived-quality, and complements our "polish over breadth" thesis.
- **Suggestion: P1 experiment.** Could be a renderer/prompt convention (lead-with-summary). Low cost; validate with our dev persona (who often want the answer-first, details-below structure).

### 1.9 Slash commands are *extension-delivered*, not native (validates a PRD open question)
Native consumer chat (ChatGPT/Claude/Gemini) still doesn't expose a `/` prompt-library popover; the demand is met by **browser extensions** (Prompster, Slashprompt) across all chat apps. **[Verified]** ([Prompster](https://github.com/LucasAschenbach/prompster); [Slashprompt](https://slashprompt.app/))
- **Why it matters:** Confirms PRD 01's "slash commands unproven in consumer chat" caution — *and* reveals an unmet need (users bolt on extensions). For our dev persona, **native** slash commands + a prompt library are a genuine differentiator vs. incumbents.
- **Suggestion: P1** native slash commands / prompt library — reframe from "risky/unproven" to "underserved need our persona already hacks around." (See PRD review §4.3 / open-question 4.)

---

## 2. Validated / challenged assumptions

### Validated by fresh research
- **Streaming is "solved"; differentiation is elsewhere.** 2026 library survey: token streaming, auto-grow composer + Shift+Enter, stop button, markdown+code, attachments, feedback are all *table-stakes*; the hard, unsolved parts are **reasoning display, tool-execution logs, citations, cost transparency, and generative UI composition.** This strongly validates our "polish + transparency" thesis — our *transparency/cost* wedge maps directly onto an acknowledged unsolved area. **[Verified]** ([dev.to chat-UI-libraries 2026](https://dev.to/alexander_lukashov/i-evaluated-every-ai-chat-ui-library-in-2026-heres-what-i-found-and-what-i-built-4p10))
- **Unified voice (talk + see responses on one screen)** is confirmed as ChatGPT's Nov 2025 direction and now the default. Validates the existing doc; keep voice at P1/P2. **[Verified]** ([TechCrunch](https://techcrunch.com/2025/11/25/chatgpts-voice-mode-is-no-longer-a-separate-interface/))
- **Reasoning-as-collapsible-summary** remains the production pattern; reasoning/thinking is now in nearly every major product by early 2026. Validates PRD 01 §4.2. **[Verified]** ([bytebytego trends](https://blog.bytebytego.com/p/whats-next-in-ai-five-trends-to-watch))
- **Live/connected artifacts** confirmed (Claude Cowork Live Artifacts, **launched Apr 20, 2026**, MCP-connected, refresh-on-open). Validates the existing doc's "Live Artifacts" note; reinforces this is heavy P2. **[Verified]** ([Claude live artifacts help](https://support.claude.com/en/articles/14729249-use-live-artifacts-in-claude-cowork))
- **Accessibility remains a real gap / opportunity.** 2026 guidance still centers the same fixes (ARIA live regions for streaming, labeled controls, 44×44 targets, manual NVDA/JAWS testing) — i.e., the differentiation thesis still holds, but it's now *well-documented best practice*, so it's table-stakes-expected, not novel. **[Verified]** ([Hurix WCAG conversational AI](https://www.hurix.com/blogs/designing-accessible-chatbots-what-wcag-means-for-conversational-ai/); [UXPin chat UI 2026](https://www.uxpin.com/studio/blog/chat-user-interface-design/))

### Challenged / updated
- **CHALLENGED (major): "incumbents retreated from branching in 2026."** Reality: ChatGPT *added* explicit branching (Sep 2025); the March 2026 change restricted **editing/retry of arbitrary older messages** — a *different* feature, plausibly a GPT-5.3/5.4 technical constraint, shipped silently with no announcement. The docs conflate "edit older messages" with "branching." See §3.1. **[Verified]** ([aiproductivity](https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/); [OpenAI on X](https://x.com/OpenAI/status/1963697012014215181))
- **UPDATED: memory is now a *free baseline*, not a paid/later differentiator.** Claude memory is free on all plans (Mar 2026); the differentiator has moved to **transparency + control + import**. PRD 00/01 treat memory as a generic P1 fast-follow without capturing that the *transparency angle* is the on-thesis part. **[Verified]** ([LumiChats](https://lumichats.com/blog/claude-memory-2026-complete-guide-how-to-use))
- **UPDATED: rich rendering bar moved past markdown** to inline interactive visualizations across all three majors in 2026 (see §1.1). PRD 01 §4.4's rendering scope (markdown/code/KaTeX/mermaid) is now the *floor*, not the ceiling. **[Verified]** ([winbuzzer](https://winbuzzer.com/2026/04/10/google-gemini-now-generates-interactive-visualizations-in-ch-xcxwbn/))
- **UPDATED: MCP is the emerging interop standard** for both tools and *UI* (MCP Apps, Jan 2026). Our P1 tools + future generative UI should target MCP rather than a bespoke shape. Not reflected in PRD 01. **[Verified]** ([MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/))
- **CONFIRMED-AND-SHARPENED: slash commands** — not native anywhere in consumer chat; users hack them in via extensions → an underserved need, not a risky bet (§1.9).

---

## 3. PRD 01 review — gaps, errors, outdated items, inconsistencies

Section references are to `docs/prd/01-core-chat-experience.md`.

### 3.1 ERROR / outdated — the branching narrative is wrong (§2 non-goals, §4.6, §8.1)
PRD 01 repeatedly justifies deferring/constraining branching by citing "the industry's 2026 retreat from editing arbitrary history" and "incumbents retreated from implicit edit-based branching" (§4.6 P0 edit-last; §8 risk 1).
- **The factual error:** ChatGPT *launched* explicit **"Branch in new chat"** in Sep 2025 (still live), and branching is standard in LibreChat/LobeChat. The March 2026 ChatGPT change restricted **editing/retrying *older* messages**, likely a model-version technical constraint — it is **not** a retreat from branching. **[Verified]** ([OpenAI on X](https://x.com/OpenAI/status/1963697012014215181); [aiproductivity](https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/))
- **Why it matters:** PRD 01 uses a misread of the news as the core rationale for a roadmap decision (branching at P2). The *correct* lesson — "explicit copy-on-branch is good and shipped; implicit edit-an-old-message-rewrites-history is what's fragile" — actually argues for **pulling explicit branching to P1**, especially for our dev/power-user persona.
- **Fix:** Rewrite §8 risk 1 and §4.6/§2 to (a) correct the branching-vs-editing conflation, (b) reconsider explicit "branch from here / branch in new chat" as **P1** (low-risk copy model), (c) keep edit-last-only at P0 but stop attributing it to a "branching retreat."

### 3.2 GAP — message data model is under-specified for the 2026 surface (§4.4, §5.4)
PRD 01 specifies rendering of a markdown *string* plus a reasoning panel. It has no notion of a **typed, multi-part message** (text / reasoning / tool-call / tool-result / citation / interactive-block / ui-component).
- **Why it matters:** Interactive visualizations (§1.1), generative/MCP UI (§1.2), tool-call + approval steps (§1.4), and citations (PRD §4.11) all need to interleave with text *in order*. Treating a message as one markdown blob now will force a painful refactor when P1 tools/search/vision land. The 2026 norm (Vercel AI SDK, AI Elements) is an ordered list of typed parts.
- **Fix:** Add an explicit "message is an ordered list of typed parts" requirement to §4.4/§5.4 even though MVP only renders the text/code/reasoning parts. This is the cheapest high-leverage architectural decision in the doc and is currently missing.

### 3.3 GAP — no tool-call / status-step *interactive* UX, only passive status lines (§4.1, §5.1)
§4.1 P0 "tool/status lines" are framed as transient passive text ("Searching the web…"). There's no spec for: persistent tool-call cards, expand-to-see inputs/outputs, errors/retries on a tool step, or the **approve/deny/approve-with-edits** pattern now standard for agentic actions (§1.4).
- **Why it matters:** Tools are P1 and central to a multi-model power-user product; a privacy-first product especially needs a *consent* affordance before a tool reads data / calls an external service. Designing status lines as throwaway text now blocks this later.
- **Fix:** Note in §4.1/§5.1 that status steps are a *previewable, persistable* part type (ties to §3.2), and add an open question for the HITL approval pattern at P1.

### 3.4 GAP — citation/source rendering decoupled from the message-part model (§4.11, §5.6)
Citations are spec'd (P1) as inline `[n]` markers + a source-card rail. But because the message is a markdown string (§3.2), there's no defined binding between an inline marker and a structured source object, nor how citations survive **streaming** (markers arriving before their sources resolve) — a known hard problem.
- **Fix:** Specify that citations are first-class message parts with stable IDs, and add a streaming rule (render marker as pending → resolve when source metadata arrives) mirroring the §5.4 "render once balanced" rule for math.

### 3.5 GAP/RISK — "reasoning effort" toggle (§4.2 P1) lacks a *cost/transparency* tie-in
PRD 01 §4.2 adds a P1 reasoning-effort toggle but doesn't connect it to the product's **cost-transparency** wedge. Reasoning tokens can dominate cost (the 30–100× token variance PRD 00 §10 flags). A "max reasoning" toggle with no visible cost consequence undercuts our core promise.
- **Fix:** Require the reasoning-effort control to surface its cost/latency implication (e.g., a relative cost hint), cross-ref PRD 02 reasoning-token accounting. This turns a generic toggle into an on-thesis transparency feature.

### 3.6 GAP — answer-layout / progressive disclosure within a single answer is absent (§4.4, §5.4)
The doc covers reasoning-panel disclosure and "collapsible long content" but not the emerging **answer-first / TL;DR-then-detail** layout (Gemini Neural Expressive, §1.8). For our answer-hungry dev persona this is cheap polish that maps to "feels more premium."
- **Fix:** Add as a P1 renderer/prompt convention experiment.

### 3.7 GAP — memory transparency UX is generic (§4.8 P1, cross-ref PRD 00)
§4.8 lists "Memory management UI (when memory ships)" as a P1 line with no detail. Given memory is now a free baseline everywhere and our wedge is transparency, the *differentiated* spec — a **viewable/editable memory ledger**, a **"this answer used memory X" indicator**, and **import-from-competitor** — is missing. This is one of our clearest on-thesis opportunities and it's a one-liner today.
- **Fix:** Expand the memory line to specify the transparency ledger + "memory used here" indicator as the differentiator; note import as an acquisition lever. **[Verified]** ([Claude memory help](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context))

### 3.8 INCONSISTENCY — share-link transparency vs. PRD 00 transparency contract (§4.10)
§4.10 says the shared read-only view "renders the conversation read-only **with model attribution**." Good — but PRD 00 §7's transparency contract is "model **and cost**." The shared view spec drops cost. Decide deliberately: do public shares show per-message *cost*? (Likely no, for privacy/competitive reasons — but the PRD should *say* so rather than silently diverge from the cross-cutting contract.)
- **Fix:** Add one line resolving whether share/export includes cost/token attribution.

### 3.9 GAP — export omits the transparency metadata it uniquely has (§4.10)
"Copy-as-markdown" (P0) and multi-format export (P1) don't state whether the **per-message model + token + cost** (our differentiator, captured in the data model per PRD 00 §8) is included in exports. A privacy-first product's export is also a *portability* promise (cf. the strong 2026 "migrate my history between tools" trend — §1.7). Exporting *with* model/cost metadata is a unique, on-brand capability incumbents can't match.
- **Fix:** Specify that copy/export can optionally include model attribution (and that the full export is genuinely complete — note ChatGPT's export historically *excludes* memory, a portability gap we can beat). **[Verified]** (existing research §11 / [OpenAI export help](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data))

### 3.10 GAP — search is title/content only; "search past chats as a tool" pattern missing (§4.5)
§4.5 search is a UI feature over an index (title + maybe full-text). In 2026, Claude exposes **chat search + memory as RAG tool-calls the model itself invokes mid-conversation** ("let me search our past chats…"). For our persona and multi-model story, "the assistant can reference your prior chats on request" is a compelling P1 that the current spec doesn't anticipate.
- **Fix:** Note retrieval-over-history as a P1 capability (owned with PRD 02/04), distinct from the UI search box. **[Verified]** ([Claude chat search](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context))

### 3.11 OUTDATED RISK FRAMING — §8 leans on the secondary-source caveat but repeats the branching misread
§8 risk 9 correctly says "re-verify secondary sources," yet §8 risk 1 (branching) is itself an un-re-verified secondary-source misread that drove a roadmap call (§3.1). The doc should practice its own caveat: the branching decision is the clearest example where the secondary source was misread.

### 3.12 MINOR — keyboard shortcuts copied wholesale from ChatGPT may collide / mislead (§5.5)
The shortcut table mirrors ChatGPT's set verbatim (e.g., `Cmd+Shift+S` toggle sidebar, `Cmd+Shift+I` custom instructions). These are reasonable, but (a) several browser/OS combos collide (`Cmd+Shift+S` is "Save As"/screenshot in some browsers; the existing research even notes ChatGPT's are *non-customizable*), and (b) blindly matching one vendor undercuts the "make shortcuts customizable for power users" angle that would differentiate vs. ChatGPT's locked set.
- **Fix:** Add a note to validate against browser-reserved combos and consider **user-customizable shortcuts** (a cheap power-user win incumbents lack — existing research §12).

### 3.13 MINOR — `Esc`-to-stop precedence (§5.3) may fight screen readers / IME
The detailed `Esc` precedence rule (Esc stops the stream when composer focused + streaming) is thoughtful but risks conflicting with IME composition (CJK input uses Esc to cancel a candidate) and with users who expect Esc to blur. Worth an explicit a11y/IME caveat and a usability check, given the mobile-web + EU/multilingual persona.

### 3.14 GAP — no spec for "model unavailable / silent-downgrade prevention" in the chat surface
PRD 00 D2/§7 makes "never silently downgrade" a core promise, but PRD 01 has no chat-surface treatment of: what the UI shows when the chosen model/tier is unavailable, rate-limited, or auto-routed to a cheaper model. This is *the* transparency moment and it lives on the chat surface (the message must say "answered by X because Y").
- **Fix:** Add a requirement: per-message attribution must visibly indicate when the *served* model differs from the *requested* model/tier, with a reason. This is arguably the highest-value transparency UX and it's currently unowned between PRD 01 and PRD 02.

---

## 4. Top 5 recommendations (prioritized)

1. **Fix the branching narrative and pull explicit branching to P1.** Correct the factual error (ChatGPT *added* branching Sep 2025; only *edit-old-message* was restricted). Adopt the low-risk **copy-on-branch ("branch from here / in new chat")** model at P1 — directly serves our dev/power-user beachhead and is far simpler than an in-thread tree. (Addresses §3.1, §3.11, §1.5.)

2. **Adopt a typed multi-part message model in the MVP data layer (even if only text/code/reasoning render at P0).** This single architectural decision de-risks every 2026 trend at once: interactive visualizations, generative/MCP UI, tool-call + approval steps, and structured citations. Skipping it now guarantees a P1 refactor. (Addresses §3.2, §3.3, §3.4, §1.1, §1.2.)

3. **Make transparency the *differentiated* spec on three surfaces PRD 01 currently leaves generic:** (a) per-message **served-vs-requested model + reason** including silent-downgrade prevention (§3.14); (b) **reasoning-effort toggle shows its cost** (§3.5); (c) **memory ledger + "memory used here" indicator + import** (§3.7). These convert generic features into our wedge at near-zero extra cost.

4. **Spec the tool-step / HITL approval UX as part of the streaming surface (P1).** Extend §4.1 status-lines into persistable, expandable tool-call parts with **approve / deny / approve-with-edits**, targeting **MCP** as the interop shape. Especially important for a privacy-first product (consent before a tool reads data / calls out). (Addresses §3.3, §1.2, §1.4.)

5. **Reframe slash commands / prompt library from "risky/unproven" to "underserved power-user need" → P1.** Users bolt extensions onto incumbents because no consumer chat ships native `/` prompt libraries; native support is a real differentiator for our exact persona. Pair with **customizable keyboard shortcuts** (incumbents lock theirs). (Addresses §1.9, §3.12.)

---

## 5. Notes on confidence & sourcing

- Strongest-verified, load-bearing claims: ChatGPT branching launch (Sep 2025) and the *separate* edit-restriction (Mar 20, 2026); Claude free memory + ledger + import (Mar 2026); interactive-visualization rollouts across all three majors (Mar–Apr 2026); MCP Apps UI standard (Jan 2026); unified voice (Nov 2025); Gemini I/O 2026 redesign. All **[Verified]** against the cited sources above.
- **[Uncertain]:** exact tier gating and dates for fast-moving features (e.g., which Gemini tier gets interactive viz this week; whether ChatGPT's edit restriction is permanent vs. a model-version artifact). Re-verify against first-party help/release notes before PRD lock — consistent with the existing docs' own caveat.
- No features or sources in this review were invented; every online claim carries a URL. Where I relied on the existing research without re-verifying, I did not re-flag it as Verified.
