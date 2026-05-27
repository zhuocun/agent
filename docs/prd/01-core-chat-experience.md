# PRD 01 — Core Chat Experience (Web + Mobile-Web)

**Owner:** Product (Core Conversational Surface)
**Status:** Draft for build
**Date:** 2026-05-27
**Primary source:** `docs/research/01-features-ux.md` (feature/UX teardown); reasoning-panel UX from `docs/research/04-ai-capabilities.md` §3.
**Related PRDs:** 02 AI Capabilities & Model Integration · 03 Mobile / Responsive · 04 Architecture.

---

## 1. Summary & purpose

This PRD specifies the **core conversational experience** — the chat surface itself — for a transparent, multi-model, privacy-first AI chat product on web and mobile-web (mobile-web first). It covers everything a user sees and touches while having a conversation: streaming responses, the reasoning panel, the composer, rich content rendering, conversation management, message actions, onboarding, basic settings, sharing/export, keyboard shortcuts, and the accessibility baseline.

The product thesis: **incumbents win on breadth; we win on a fast, polished, accessible core.** Rendering/streaming fidelity, composer ergonomics, accessibility, and mobile-web polish are the levers we are deliberately over-investing in. A janky renderer or a laggy stream reads as "low quality" instantly; a crisp one reads as premium. This document is written so a senior engineer can build the MVP from it.

Out of scope here (owned elsewhere): model internals/routing/cost accounting (PRD 02), mobile-specific composer/keyboard/gesture behavior (PRD 03), streaming transport and persistence architecture (PRD 04), and organizational primitives like Projects/Spaces (post-MVP, separate spec).

---

## 2. Goals & non-goals

### Goals
- Ship a conversational surface that **feels faster and more polished** than incumbents on the basics: first-token latency perception, smooth streaming, flawless markdown/code/math rendering.
- Make **transparency a first-class UI value**: show which model answered each message; expose (but don't force) reasoning.
- Deliver an **accessibility baseline that beats the leaders** (who have documented gaps) — labeled controls, ARIA live regions for streaming, full keyboard operability, announced status.
- Provide a **simple default mode** so casual users aren't excluded, while giving power users/developers shortcuts, a command palette, and dense controls.
- Be **excellent on mobile-web**, not a shrunk-down desktop UI (detailed in PRD 03; this PRD sets responsive expectations).

### Non-goals (this PRD / this phase)
- Heavy parallel **model comparison** (run N models side-by-side) — later.
- **Branching / alternate-response trees** — P2+, designed conservatively (see §8).
- **Projects/Spaces, folders, tagging, pin/archive** — post-MVP organizational layer.
- **Voice mode, image generation, code execution / data analysis** — owned by PRD 02, later phases.
- **Memory** (persistent cross-chat facts) — fast-follow, separate spec; we only ship the *custom instructions* entry point in MVP.
- Full multi-format export (PDF/.docx) — MVP ships copy-as-markdown + share link only.

---

## 3. Target users & key user stories

**Priority persona (MVP):** power users / developers. **Secondary:** privacy-conscious prosumers. **Constraint:** keep a simple default so casual users succeed without learning anything.

Key user stories:

1. **As a developer**, I paste a long error log and ask for a fix, so I want code blocks to render with syntax highlighting and a one-click copy, and I want to keep the partially-streamed answer if I hit Stop early.
2. **As a power user**, I want `Cmd/Ctrl+K` to jump to any past chat or start a new one without touching the mouse, and a discoverable shortcut list.
3. **As a privacy-conscious prosumer**, I want to know exactly which model produced an answer, to see its reasoning if I choose, and to find data controls without hunting.
4. **As a casual user**, I land on an empty state with a friendly greeting and 3–4 example prompt cards so I immediately know what I can ask.
5. **As a screen-reader user**, I want every icon button labeled, generation status announced, and the streamed answer readable without fighting focus.
6. **As any user on my phone**, I want a thumb-friendly composer, a Stop button that's always reachable, and tables/code that don't break the layout.
7. **As a user who got a great answer**, I want to copy it as markdown or share an unlisted link in two clicks.

---

## 4. Functional requirements

Priority tags: **[P0/MVP]** must ship to be credible · **[P1]** fast-follow · **[P2]** later/differentiator. Acceptance criteria (AC) given where load-bearing.

### 4.1 Streaming response
- **[P0]** Token/word streaming renders incrementally as chunks arrive (SSE; transport per PRD 04).
  - *AC:* Visible text updates within ~50ms of each chunk; no full-message re-layout flicker per chunk.
- **[P0]** **Pre-first-token indicator**: animated typing/skeleton indicator shown from send until first content token.
  - *AC:* Indicator appears <150ms after send; replaced by streamed content on first token; never shown simultaneously with content.
- **[P0]** **Stop control that preserves partial output**: Stop aborts the stream (client `AbortController`, cancellation propagated per PRD 04) and **keeps everything streamed so far** as a normal, actionable assistant message.
  - *AC:* After Stop, partial message is persisted, copy/regenerate available, and a subtle "stopped" marker is shown.
- **[P0]** **Tool/status lines**: when the backend emits intermediate steps (e.g., "Searching the web…", "Running analysis…"), render them as transient status lines above/within the forming message. (Step payloads defined in PRD 02.)
- **[P1]** Resume an interrupted stream after a transient disconnect (resumable streams per PRD 04) without losing already-rendered tokens.

### 4.2 Reasoning / "thinking" panel
- **[P0]** A **collapsible reasoning panel** attached to an assistant message, rendered only when the model emits reasoning/summary content (provider-shaped; may be a summary only — see PRD 02 §3).
  - **Auto-open** with a shimmer + label ("Thinking…") while reasoning streams.
  - On completion, show **"Thought for Xs"** and **auto-collapse**.
  - User can **expand/collapse** any time; expansion state is per-message and remembered for the session.
  - *AC:* If no reasoning content is emitted, no panel/affordance appears (no empty panel). We never fabricate or store reasoning the provider hides.
- **[P1]** A per-conversation or per-message **"reasoning effort"/extended-thinking** toggle surfaced in the UI (mapping to provider knobs lives in PRD 02).

### 4.3 Message composer
- **[P0]** Multiline textarea: **Enter sends, Shift+Enter inserts newline** (desktop). Auto-grows to a max height then scrolls. (Mobile send/keyboard behavior: PRD 03.)
- **[P0]** **Send button morphs into Stop** during generation; same position.
- **[P1]** **Attachments**: paperclip/"+" menu to attach images and files; **paste image from clipboard**; **drag-and-drop** files onto the composer with a drop overlay. (Accepted types/limits and what the model does with them: PRD 02.) **Deferred to P1 with vision/PDF understanding** — the lean text-core MVP is text-only, so there is no attach affordance at launch.
  - *AC (P1):* Pasting an image inserts a thumbnail chip; drag-drop shows a highlighted drop zone; each attachment chip is removable and labeled.
- **[P0]** Plain-text **paste** into the composer works at MVP (e.g., pasting a long error log); only *image/file* attachment is deferred.
- **[P0]** **Model picker** lives in the composer (compact control adjacent to send) **and** is reflected in the thread header. Presents **capability tiers** (e.g., Fast / Smart / Pro), not raw model IDs, driven by the model registry (PRD 02 owns tiers/registry). Selection can change mid-thread.
- **[P1]** **Slash commands** (`/`) popover for quick actions/prompt templates.
- **[P1]** Inline **mode toggles** in composer (e.g., web search on/off) once those capabilities land (PRD 02).
- **Non-goal (MVP):** token/character counters in the composer (hidden complexity; reconsider only if user research demands it).

### 4.4 Rich content rendering (the single biggest perceived-quality lever — see §5.4)
- **[P0]** **Streaming-safe markdown** (CommonMark + GFM). Must render *mid-token* content gracefully — unclosed code fences, half-written tables, dangling emphasis must not flicker, break layout, or dump raw markdown. Adapt a battle-tested streaming renderer (Streamdown-style); do not roll our own naive parser.
- **[P0]** **Code blocks**: syntax highlighting (Shiki/Prism-class), language label, **copy button**. *AC:* copy puts exact source on clipboard; highlighting applies progressively during stream without re-flicker.
- **[P0]** **Math** via **KaTeX**: inline `$…$` and block `$$…$$`.
- **[P0]** **GFM tables**, horizontally scrollable on narrow viewports.
- **[P0]** **Images**: the renderer supports inline images with alt text (cheap markdown capability). User-attached and model-generated images are **exercised at P1** when attachments/vision land (§4.3).
- **[P0]** **Collapsible long content**: very long code blocks / responses get a "show more" / collapse affordance to keep the thread scannable.
- **[P1]** **Mermaid diagrams** with a fullscreen view.
- **[P1]** Code block **download** button and optional line numbers.
- **[P0 security]** Sanitize all rendered HTML/markdown; safe link handling (`rel="noopener noreferrer"`, no script injection). Treat model output as untrusted (cross-ref PRD 02 §9).

### 4.5 Conversation management
- **[P0]** **New chat** button (sidebar top) + shortcut.
- **[P0]** **History sidebar**, reverse-chronological, **grouped by time** ("Today / Yesterday / Previous 7 days / older").
- **[P0]** **Rename** and **delete** a conversation via hover/overflow (`···`) menu; delete asks for confirmation.
- **[P0]** **Search** across conversation titles and content, surfaced via the command palette (§4.9) and a sidebar search field.
  - *AC:* Search returns matching chats with a title match and, where the index supports it, a content snippet; selecting one opens it scrolled to context. (Title-only vs full-text depends on PRD 04's index — see §8.)
- **[P0]** Auto-title a new conversation from its first exchange; user can override via rename.
- **[P1]** Pin / archive.
- **[P2]** Folders / tagging / Projects (separate org-layer spec).

### 4.6 Message actions
- **[P0]** **Copy** assistant message (icon row under message; also copies as clean markdown).
- **[P0]** **Regenerate** the most recent assistant response.
- **[P0]** **Edit last user message + re-run** (in-place edit of the latest user turn, then regenerate). Scope edit to the most recent user message in MVP (mirrors the industry's 2026 retreat from editing arbitrary history; avoids implicit branching complexity).
- **[P0]** **Thumbs up / down** feedback; thumbs-down opens an optional detail note. (Storage/usage of feedback: PRD 04.)
- **[P0]** **Per-message model attribution**: each assistant message shows which model/tier produced it (transparency requirement).
- **[P1]** Read aloud (TTS) — also an a11y aid (PRD 02 for synthesis).
- **[P2]** Branch / alternate responses — see §8 risk note (design explicit "branch from here," never implicit edits).

### 4.7 Onboarding / empty state
- **[P0]** Centered friendly greeting + **3–4 suggested-prompt cards** showcasing variety of use cases + a focused composer.
  - *AC:* Clicking a card populates the composer (or sends immediately — see open question §8) and clears the empty state.
- **[P1]** Use-case template gallery.

### 4.8 Settings basics
- **[P0]** **Theme**: light / dark / **system** (default system).
- **[P0]** **Custom instructions** entry point (stable user preferences injected per chat; content semantics in PRD 02). MVP = a simple text-entry dialog reachable from settings and a shortcut.
- **[P0]** **Data controls** entry point: clear/delete history; training opt-out toggle if applicable (privacy-first posture). Detailed data handling in PRD 04.
- **[P1]** Memory management UI (when memory ships).

### 4.9 Keyboard shortcuts & command palette
- **[P0]** **`Cmd/Ctrl+K` command palette**: search/jump-to-chat, new chat, focus composer, toggle theme, toggle sidebar, open shortcuts list.
- **[P0]** Core shortcut set (see §5.5 table) including new chat, focus composer, copy last response, toggle sidebar, and a **show-all-shortcuts** dialog (`Cmd/Ctrl+/`).
- *AC:* All P0 actions reachable by keyboard alone; palette is fully keyboard-navigable and screen-reader friendly.

### 4.10 Sharing & export
- **[P0]** **Shareable unlisted conversation link** (read-only public-by-link; not indexed). Creating a link is explicit; user can revoke it.
  - *AC:* Shared view renders the conversation read-only with model attribution; no composer; revoke invalidates the link.
- **[P0]** **Copy-as-markdown**: copy the whole conversation (or a single message) as clean markdown.
- **[P1]** Multi-format export (PDF / .docx / Markdown file download).
- **[P2]** Published "pages" (Perplexity-style formatted public artifact).

### 4.11 Citations / source cards + suggested follow-ups
- **[P1]** When web search/RAG is used (PRD 02 owns retrieval), render **inline numbered citations** `[1][2]` that, on click/hover, reveal source title, domain/favicon, and snippet; render a **source-card list** (right-rail on desktop, stacked below answer on mobile).
- **[P1]** **Suggested follow-up** chips under cited answers; tapping one sends it as the next message.
- *Note:* In-chat rendering of citations/cards is owned here; retrieval, citation metadata shape, and freshness are owned by **PRD 02**. Spec'd lightly in §5.6.

### 4.12 Artifacts / Canvas side panel
- **[P1 stretch]** **MVP-lite read-only side panel:** an **"open in side panel"** affordance on long code/document outputs — opens a read-only side panel (desktop) / full-screen toggle (mobile-web) with **copy** and **download**. No live execution, no versioning. (Stretch for the MVP window; drops to P2 if capacity is constrained — see §8.)
- **[P2 — full]** Full Artifacts/Canvas: editable surface, live preview/execution, version history, publish/embed. Deferred (sandboxing/versioning cost; awkward on mobile-web).

---

## 5. UX & interaction details (load-bearing specifics)

### 5.1 Streaming behavior
- **State machine per assistant message:** `idle → submitted (pre-first-token indicator) → streaming (content + optional reasoning + status lines) → done | stopped | error`.
- **Pre-first-token:** show typing/skeleton; if no token within a soft timeout (e.g., ~10s), keep indicator but expose Stop prominently (latency budgeting in PRD 04/02).
- **Stop:** single click aborts; partial content frozen and persisted; UI transitions to `stopped` with a small "Stopped" tag; **Regenerate** offered. Stop must remain visible/sticky on mobile (PRD 03).
- **Auto-scroll:** follow the stream to the bottom **only if** the user is already at/near the bottom; if the user scrolls up to read, stop auto-following and show a "↓ Jump to latest" pill.
- **Error:** failed/aborted-by-server streams show an inline error with **Retry**, preserving any partial content.

### 5.2 Reasoning panel states
| State | Trigger | Visual |
|---|---|---|
| Hidden | No reasoning emitted | No panel, no affordance |
| Thinking (open) | Reasoning content streaming | Auto-expanded, shimmer + "Thinking…", live text |
| Done (collapsed) | Reasoning complete + answer streaming/done | Collapsed bar: "Thought for Xs", chevron to expand |
| Expanded | User expands | Full reasoning text (summary if provider only gives summary) |

- Reasoning text uses the same streaming-safe renderer (it may contain markdown/code).
- The panel is a **sibling above the answer**, clearly visually subordinate (muted), so it never competes with the answer.
- Never block the answer on reasoning: answer tokens may stream while/after reasoning.

### 5.3 Composer keybindings & layout
| Key | Action |
|---|---|
| `Enter` | Send |
| `Shift+Enter` | Newline |
| `Esc` (while streaming) | Stop generation |
| `Shift+Esc` (global) | Focus composer |
| `/` at line start | Open slash-command popover (P1) |

> **`Esc` precedence:** When the composer is focused and a stream is active, `Esc` stops generation (it does **not** blur the composer); a second `Esc` is a no-op. When no stream is active, `Esc` follows default browser/textarea behavior.

- Layout (desktop): `[+ attach] [ multiline textarea ] [ model tier control ] [ Send/Stop ]`. Attachment chips render in a row above the input. Model control is compact (label = current tier) and opens a tiered menu with brief metadata (relative speed/cost, modality) sourced from the registry.
- Composer is sticky to the bottom of the thread; remains anchored during streaming.
- Mobile composer specifics (touch targets, keyboard avoidance, sticky Stop): **defer to PRD 03**.

### 5.4 Renderer requirements (spec carefully)
- **Streaming-safe parsing:** the renderer must tolerate incomplete markdown each frame: auto-close open code fences for rendering, defer table rendering until a row boundary is parseable, never render raw `*`/`#`/backticks as a flash. No layout shift > the height of the newly added content.
- **Code blocks:** language label from the fence info-string; highlight progressively; copy copies raw source (not highlighted DOM); long blocks collapse with "show more"; (P1) download with sensible filename/extension from language.
- **Math:** KaTeX for `$…$` / `$$…$$`; render only once delimiters are balanced to avoid mid-token flashes.
- **Tables:** wrap in a horizontal-scroll container; sticky header optional; never overflow the viewport on mobile.
- **Images:** lazy-load, constrained max-width, alt text required (use model-provided alt or a generic label).
- **Links:** open in new tab, `rel="noopener noreferrer"`; show domain on hover.
- **Sanitization:** strip scripts/iframes/event handlers; allowlist-based HTML; this is both a quality and security requirement.
- **Performance target:** rendering keeps up with stream at 60fps on a mid-tier mobile device; virtualize very long threads.

### 5.5 Keyboard shortcuts (global)
| Action | Mac / Win-Linux |
|---|---|
| Command palette / search | `Cmd+K` / `Ctrl+K` |
| New chat | `Cmd+Shift+O` / `Ctrl+Shift+O` |
| Focus composer | `Shift+Esc` |
| Stop generation | `Esc` (while streaming) |
| Copy last response | `Cmd+Shift+C` / `Ctrl+Shift+C` |
| Copy last code block | `Cmd+Shift+;` / `Ctrl+Shift+;` |
| Toggle sidebar | `Cmd+Shift+S` / `Ctrl+Shift+S` |
| Open custom instructions | `Cmd+Shift+I` / `Ctrl+Shift+I` |
| Delete current chat | `Cmd+Shift+Backspace` / `Ctrl+Shift+Backspace` |
| Show all shortcuts | `Cmd+/` / `Ctrl+/` |

Conventions follow established category norms (low learning cost). A visible, searchable shortcut dialog is required for discoverability.

### 5.6 Citations & follow-ups rendering (light spec; P1)
- Inline marker `[n]` is a small superscript chip; click scrolls to / highlights the matching source card; hover (desktop) shows a popover with title + snippet.
- Source cards: favicon, title, domain, short snippet, opens in new tab. Right-rail on wide screens; collapsible list under the answer on mobile.
- Follow-up chips: max ~3–4, tappable to send.

### 5.7 Accessibility baseline (deliberate differentiation lever)
- **Labeled controls:** every icon button has a descriptive accessible name (Copy, Regenerate, Edit, Thumbs up/down, Attach, Send, Stop) — explicitly fixing the unlabeled-button gap measured in incumbents.
- **ARIA live regions:** streaming answer is announced appropriately (e.g., `aria-live="polite"`); status lines and "generating…/done/stopped" transitions are announced (not silently visual-only).
- **Full keyboard operability:** every action (send, stop, copy, regenerate, edit, navigate history, open palette, expand reasoning) reachable and operable by keyboard with visible focus states.
- **Semantic structure:** messages as a navigable list with roles; reasoning panel exposes expanded/collapsed state via ARIA.
- **Reduced motion:** honor `prefers-reduced-motion` (shimmer/typing animations degrade gracefully).
- **Contrast & target size:** meet WCAG AA contrast; touch targets sized per PRD 03.
- Treat a11y as acceptance-blocking for MVP, not a follow-up.

---

## 6. Dependencies & cross-references

| Concern | Owner PRD | What this PRD relies on |
|---|---|---|
| Model registry, capability tiers, auto-routing, per-message model metadata, cost/token accounting (incl. reasoning tokens) | **02 AI Capabilities** | Tier names + metadata for the picker; which model answered each message; reasoning/summary payload shape; attachment handling semantics; web-search/citation metadata; TTS for read-aloud |
| Reasoning/"thinking" payload shape (summary vs raw; provider differences; effort knobs) | **02 AI Capabilities §3** | What the reasoning panel renders and the effort toggle maps to |
| Mobile composer, keyboard avoidance, gestures, touch targets, sticky Stop, mobile artifact fallback (full-screen toggle) | **03 Mobile / Responsive** | All mobile-specific composer/keyboard/layout details; this PRD only sets responsive intent |
| Streaming transport (SSE/resumable), abort propagation, persistence, search index, share-link backend, feedback storage, data controls/export plumbing | **04 Architecture** | Stream lifecycle, cancellation, conversation storage, full-text search, unlisted-link generation/revocation |
| Output sanitization / untrusted-content posture | **02 §9 + 04** | Renderer treats model/web content as untrusted |

**Deferral rule:** any mobile composer/keyboard specifics raised here are intentionally light — **defer to PRD 03** for the authoritative spec.

---

## 7. Success metrics (this surface)

| Metric | Definition | Target (MVP) |
|---|---|---|
| **Perceived time-to-first-token (TTFT)** | Send → first rendered content token | p50 < 1.0s, p95 < 2.5s (front-end portion; provider latency per PRD 02) |
| **Stream smoothness** | Dropped frames / jank during stream on mid-tier mobile | 0 layout-break events; sustained 60fps render |
| **Render correctness** | % of responses with code/math/tables that render without breakage (sampled + golden-set tests) | > 99% |
| **Stop-preserves-output** | % of Stop actions that retain partial content | 100% |
| **Regeneration rate** | % of assistant messages regenerated | Track as a quality signal (high rate may indicate answer or UX issues) |
| **Thumbs-down rate** | Negative feedback per assistant message | Track; trend down over time |
| **Copy / share usage** | Copy-as-markdown + share-link events per active conversation | Track (engagement/value proxy) |
| **Accessibility** | Automated a11y (axe-class) pass on chat surface + manual screen-reader smoke | 0 critical violations; labeled-control coverage 100% |
| **Keyboard reachability** | % of P0 actions doable without mouse | 100% |
| **Empty-state activation** | % of new users who send a first message (incl. via suggested cards) | Track as activation KPI |

---

## 8. Open questions / risks

Pulled from research open-questions and shared context:

1. **Branching design caution (risk).** Incumbents retreated from implicit edit-based branching in 2026 because it's a confusing data model and UX. **Decision for MVP:** edit is restricted to the most recent user turn (re-run in place, no tree). If/when we add branching (P2), use **explicit "branch from here"**, never implicit edits. Study a concrete fork implementation before designing the data model.
2. **Mobile artifact fallback (open).** Side-by-side panels are awkward on mobile-web; exact full-screen-toggle behavior must be defined with **PRD 03** before building even the MVP-lite side panel.
3. **Suggested-prompt card behavior (open).** Do cards send immediately or just prefill the composer? Default proposal: **prefill** (lower commitment, lets users edit), pending quick usability check.
4. **Slash commands in MVP? (scope).** Strong for our dev persona but unproven in consumer chat; currently **P1**. Revisit if dev-user research pulls it forward.
5. **Token/char hints (open).** Consumer products generally hide these. Default: **omit** in MVP; reconsider only with evidence.
6. **Reasoning content storage (privacy/risk).** Providers may only return a *summary*, and some omit thinking by default (PRD 02 §3). We must **not** store or display reasoning the provider hides; the panel renders only what's emitted.
7. **Citation interaction details (open).** Hover vs click, right-rail vs inline expansion — finalize with retrieval design (PRD 02) when web search lands.
8. **Search scope (open).** Title-only vs full-text history search at MVP depends on the search index (PRD 04); target full-text if feasible, fall back to title + recent-content otherwise.
9. **Sourcing caveat.** Research is partly secondary; re-verify any specific shortcut/limit against first-party docs before locking. Shortcut conventions here follow category norms and are safe; exact provider limits are not owned by this PRD.

---

## 9. References

**Internal**
- Primary source: `docs/research/01-features-ux.md` (feature & UX teardown; MVP-vs-later recommendations §15).
- Reasoning-panel UX: `docs/research/04-ai-capabilities.md` §3 (streaming & reasoning display).
- Cross-PRDs: 02 AI Capabilities, 03 Mobile/Responsive, 04 Architecture.

**Key external sources (from research, re-verify at build)**
- Streaming-safe markdown rendering — Streamdown: https://streamdown.ai/
- Reasoning panel components — shadcn AI reasoning: https://www.shadcn.io/ai/reasoning ; AI Elements: https://elements.ai-sdk.dev/components/reasoning
- Reasoning display patterns — digestibleux: https://www.digestibleux.com/p/how-ai-models-show-their-reasoning ; Claude extended thinking: https://renezander.com/blog/claude-extended-thinking/
- Keyboard shortcuts — ai-toolbox ChatGPT shortcuts: https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide
- Editing/branching restriction (2026) — aiproductivity: https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/
- Accessibility gaps in leaders — accessibility-test.org: https://accessibility-test.org/blog/qa-testing/automated-testing/ai-accessibility-testing-chatgpt-vs-claude-vs-gemini-oct-2025/
- Citations/source cards — unusual.ai Perplexity guide: https://www.unusual.ai/blog/perplexity-platform-guide-design-for-citation-forward-answers
- Empty-state / suggested prompts — fuselabcreative: https://fuselabcreative.com/chatbot-interface-design-guide/
- Artifacts/Canvas — Claude Artifacts: https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them
