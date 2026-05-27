# PRD 01 — Core Chat Experience (Web + Mobile-Web)

**Owner:** Product (Core Conversational Surface)
**Status:** Draft for build
**Date:** 2026-05-27
**Related PRDs:** 00 Product Overview · 02 AI Capabilities & Model Integration · 03 Mobile / Responsive · 04 Architecture · 05 Roadmap / Monetization.

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
- Deliver an **accessibility baseline that beats the leaders** (who have documented gaps) — labeled controls, a correct streaming announce model (status-only polite region; see §5.7), full keyboard operability, announced status.
- Provide a **simple default mode** so casual users aren't excluded, while giving power users/developers shortcuts, a command palette, and dense controls.
- Be **excellent on mobile-web**, not a shrunk-down desktop UI (detailed in PRD 03; this PRD sets responsive expectations).

### Non-goals (this PRD / this phase)
- Heavy parallel **model comparison** (run N models side-by-side) — later.
- **Explicit copy-on-branch ("branch from here / branch in new chat")** — now **P1** (was P2), designed as a low-risk copy model, never an in-thread tree (see §4.6, §8). **In-thread alternate-response trees** remain P2+.
- **Projects/Spaces, folders, tagging, pin/archive** — post-MVP organizational layer.
- **Voice mode, image generation, code execution / data analysis** — owned by PRD 02, later phases.
- **Memory** (persistent cross-chat facts) — fast-follow (P1); we only ship the *custom instructions* entry point in MVP. Note: memory is now a *free baseline* across incumbents, so our P1 spec leads with the **transparency layer** (ledger + "memory used here" + import), not the feature itself — see §4.8.
- Full multi-format export (PDF/.docx) — MVP ships copy-as-markdown + share link only.
- **Proactive / ambient briefings** (ChatGPT Pulse / Gemini Daily Brief style overnight digests) — **deliberate non-goal**. They are connector/agent-heavy and require reading the user's mail/calendar, which cuts against our privacy-first posture. Listed here so the team isn't surprised when incumbents lean in.

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
- **[P0]** **Tool/status lines**: when the backend emits intermediate steps (e.g., "Searching the web…", "Running analysis…"), render them as status lines above/within the forming message. (Step payloads defined in PRD 02.) These are **not throwaway text**: a status line is the streaming form of a **tool-call part** (§4.4) and must be persistable, so designing them as transient-only is prohibited.
- **[P1]** **Tool-call parts with human-in-the-loop (HITL) approval** (design now, lands with tools). Status lines become **persistable, expandable tool-call parts** that show the tool name, inputs, and output/result, with **errors/retries** on a step. When a step requires consent (a tool reads user data or calls an external service), the part presents **approve / deny / approve-with-edits** controls and **pauses** generation until the user acts. Target **MCP** as the interop shape (capability owned by PRD 02; AI SDK v6 `Agent` / `needsApproval` wiring owned by PRD 04 — reference both). This consent gate is acceptance-relevant for our privacy-first posture.
  - *AC (P1):* an approval-gated tool step blocks the stream, surfaces inputs/context for review, and on deny/edit feeds the decision back without losing prior streamed content.
- **[P1]** Resume an interrupted stream after a transient disconnect (resumable streams per PRD 04) without losing already-rendered tokens.

### 4.2 Reasoning / "thinking" panel
- **[P0]** A **collapsible reasoning panel** attached to an assistant message, rendered only when the model emits reasoning/summary content (provider-shaped; may be a summary only — see PRD 02 §3).
  - **Auto-open** with a shimmer + label ("Thinking…") while reasoning streams.
  - On completion, show **"Thought for Xs"** and **auto-collapse**.
  - User can **expand/collapse** any time; expansion state is per-message and remembered for the session.
  - *AC:* If no reasoning content is emitted, no panel/affordance appears (no empty panel). We never fabricate or store reasoning the provider hides.
- **[P1]** A per-conversation or per-message **"reasoning effort"/extended-thinking** toggle surfaced in the UI (mapping to provider knobs lives in PRD 02). The toggle **must surface a cost/latency hint** (e.g., a relative "higher cost / slower" indicator) so users understand the trade-off — reasoning tokens drive the large per-turn cost variance the product warns about, so a "max reasoning" control with no visible cost consequence would undercut our transparency wedge. Cross-ref **PRD 02** reasoning-token accounting for the underlying numbers.

### 4.3 Message composer
- **[P0]** Multiline textarea: **Enter sends, Shift+Enter inserts newline** (desktop). Auto-grows to a max height then scrolls. (Mobile send/keyboard behavior: PRD 03.)
- **[P0]** **Send button morphs into Stop** during generation; same position.
- **[P1]** **Attachments**: paperclip/"+" menu to attach images and files; **paste image from clipboard**; **drag-and-drop** files onto the composer with a drop overlay. (Accepted types/limits and what the model does with them: PRD 02.) **Deferred to P1 with vision/PDF understanding** — the lean text-core MVP is text-only, so there is no attach affordance at launch.
  - *AC (P1):* Pasting an image inserts a thumbnail chip; drag-drop shows a highlighted drop zone; each attachment chip is removable and labeled.
- **[P0]** Plain-text **paste** into the composer works at MVP (e.g., pasting a long error log); only *image/file* attachment is deferred.
- **[P0]** **Model picker** lives in the composer (compact control adjacent to send) **and** is reflected in the thread header. Presents **capability tiers** (e.g., Fast / Smart / Pro), not raw model IDs, driven by the model registry (PRD 02 owns tiers/registry). Selection can change mid-thread.
- **[P1]** **Native slash commands (`/`) + prompt library** popover for quick actions/prompt templates. **Reframed from "risky/unproven" to a committed P1 differentiator:** no consumer chat ships native slash commands today, so users bolt browser extensions (Prompster/Slashprompt) onto incumbents — an underserved need our dev/power-user persona already hacks around.
- **[P1]** **Re-attach recently used files** in the attach menu (lands with attachments) — a low-cost composer win for repeat-context workflows.
- **[P1]** Inline **mode toggles** in composer (e.g., web search on/off, reasoning effort) once those capabilities land (PRD 02). The inline-toggle pattern is increasingly the *primary* mode-switch UI (vs. a dropdown) and is the intended home for our P1 web-search/reasoning controls.
- **Non-goal (MVP):** token/character counters in the composer (hidden complexity; reconsider only if user research demands it).

### 4.4 Rich content rendering (the single biggest perceived-quality lever — see §5.4)
- **[P0 — message model]** A message is an **ordered list of typed parts** (text / reasoning / tool-call / tool-result / citation / interactive-block), **not** a single markdown string. **Ownership:** the data-model schema for typed parts is owned by **PRD 04** (reference it; a separate worker keeps the schema authoritative). This PRD owns the **rendering contract**: the renderer iterates an ordered part list and dispatches by type so new part types are *additive*, never a rewrite. **At P0 the renderer renders text, code, and reasoning parts;** tool-call/tool-result, citation, and interactive-block parts render at **P1** (they arrive with tools/search/vision). This is the cheapest high-leverage architectural decision in the doc — modeling a message as one blob would force a painful refactor when P1 features land.
- **[P0]** **Streaming-safe markdown** (CommonMark + GFM) for text parts. Must render *mid-token* content gracefully — unclosed code fences, half-written tables, dangling emphasis must not flicker, break layout, or dump raw markdown. Adapt a battle-tested streaming renderer (Streamdown-style); do not roll our own naive parser.
- **[P0]** **Code blocks**: syntax highlighting (Shiki/Prism-class), language label, **copy button**. *AC:* copy puts exact source on clipboard; highlighting applies progressively during stream without re-flicker.
- **[P0]** **Math** via **KaTeX**: inline `$…$` and block `$$…$$`.
- **[P0]** **GFM tables**, horizontally scrollable on narrow viewports.
- **[P0]** **Images**: the renderer supports inline images with alt text (cheap markdown capability). User-attached and model-generated images are **exercised at P1** when attachments/vision land (§4.3).
- **[P0]** **Collapsible long content**: very long code blocks / responses get a "show more" / collapse affordance to keep the thread scannable.
- **[P1]** **Mermaid diagrams** with a fullscreen view.
- **[P1]** **Interactive blocks as a rendering baseline (not "Artifacts").** The renderer **hosts typed interactive blocks** — e.g., a chart spec rendered client-side with sliders, an adjustable/rotatable diagram — delivered as an `interactive-block` part (§4.4 message model). Inline interactivity is now expected response-surface functionality across the majors, *distinct* from a full Canvas/Artifacts panel (§4.12). **P0 ships a static-chart renderer; P1 adds interactivity.** Do not build a 3D engine for MVP — the requirement is only that the renderer/schema can host these blocks additively. Full generative/MCP-returned UI components remain **P2** (§4.12).
- **[P1]** **Answer-first / progressive-disclosure layout** (renderer/prompt experiment). Lead with key info / a TL;DR, then progressive detail below — distinct from the reasoning panel; an answer-*layout* convention our answer-hungry dev persona tends to prefer. Cheap, high-perceived-quality; validate with the persona.
- **[P1]** Code block **download** button and optional line numbers.
- **[P0 security]** Sanitize all rendered HTML/markdown via **`rehype-harden`-class allowlist hardening** (the mechanism shipped in Streamdown — see §5.4); safe link handling (`rel="noopener noreferrer"`, no script injection). Treat model output as untrusted (cross-ref PRD 02 §9).

### 4.5 Conversation management
- **[P0]** **New chat** button (sidebar top) + shortcut.
- **[P0]** **History sidebar**, reverse-chronological, **grouped by time** ("Today / Yesterday / Previous 7 days / older").
- **[P0]** **Rename** and **delete** a conversation via hover/overflow (`···`) menu; delete asks for confirmation.
- **[P0]** **Search** across conversation titles and content, surfaced via the command palette (§4.9) and a sidebar search field.
  - *AC:* Search returns matching chats with a title match and, where the index supports it, a content snippet; selecting one opens it scrolled to context. (Title-only vs full-text depends on PRD 04's index — see §8.)
- **[P0]** Auto-title a new conversation from its first exchange; user can override via rename.
- **[P1]** Pin / archive.
- **[P1]** **Retrieval-over-history** — the assistant can **search past chats as a tool** it invokes mid-conversation ("let me check our earlier chats…"), distinct from the §4.5 UI search box (which is a user-driven find). This is a tool-call surface (renders as a tool-call part, §4.4) owned jointly with **PRD 02** (retrieval) and **PRD 04** (index). Note: incumbents gate the higher-value retrieval-over-history behind paid plans even where memory is free — treat it as the gated, higher-value capability.
- **[P2]** Folders / tagging / Projects (separate org-layer spec).

### 4.6 Message actions
- **[P0]** **Copy** assistant message (icon row under message; also copies as clean markdown).
- **[P0]** **Regenerate** the most recent assistant response.
- **[P0]** **Edit last user message + re-run** (in-place edit of the latest user turn, then regenerate). Scope edit to the most recent user message in MVP to avoid implicit branching/history-rewrite complexity. (Note: in 2026 ChatGPT *restricted editing/retry of arbitrary older messages* — a separate, likely model-version constraint; this is **not** a "branching retreat," and is **not** the rationale for edit-last. We constrain edit-last purely to keep the data model simple.)
- **[P0]** **Thumbs up / down** feedback; thumbs-down opens an optional detail note. (Storage/usage of feedback: PRD 04.)
- **[P0]** **Per-message model attribution**: each assistant message shows which model/tier produced it (transparency requirement).
- **[P0]** **Served-vs-requested transparency (silent-downgrade prevention) — this PRD owns the surface.** When the model/tier that actually *served* a message differs from what was *requested* (unavailable, rate-limited, or auto-routed to a cheaper model), the per-message attribution must **visibly indicate the substitution and a short reason** ("answered by Fast because Pro was rate-limited"). The routing/availability/decision logic is owned by **PRD 02** (reference it); the per-message indicator is owned here. This is the single highest-value transparency moment and it lives on the chat surface.
- **[P1]** **Explicit copy-on-branch ("branch from here" / "branch in new chat")** — **pulled to P1 (was P2).** On hover/overflow, copy the conversation up to a chosen point into a **new** thread, leaving the source intact. This is a low-risk *copy* model (not an in-thread tree) and directly serves the dev/power-user beachhead; it is now a shipped, standard power-user feature, not something incumbents retreated from. In-thread alternate-response trees remain **P2** (see §8).
- **[P1]** Read aloud (TTS) — also an a11y aid (PRD 02 for synthesis).

### 4.7 Onboarding / empty state
- **[P0]** Centered friendly greeting + **3–4 suggested-prompt cards** showcasing variety of use cases + a focused composer.
  - *AC:* Clicking a card populates the composer (or sends immediately — see open question §8) and clears the empty state.
- **[P1]** Use-case template gallery.

### 4.8 Settings basics
- **[P0]** **Theme**: light / dark / **system** (default system).
- **[P0]** **Custom instructions** entry point (stable user preferences injected per chat; content semantics in PRD 02). MVP = a simple text-entry dialog reachable from settings and a shortcut.
- **[P0]** **Data controls** entry point: clear/delete history; training opt-out toggle if applicable (privacy-first posture). Detailed data handling in PRD 04.
- **[P0]** **Temporary chat** entry point in the New Chat menu and thread header. Temporary chats are visibly marked, excluded from future memory/personalization, and use the retention fields defined in PRD 04. *AC:* starting a temporary chat sets `chat.is_temporary = true` and the UI shows a temporary-chat banner.
- **[P1]** **Memory transparency UX (the differentiated spec; memory stays P1).** Memory is now a free baseline everywhere, so our wedge is the transparency layer, not the feature: (a) a **viewable/editable memory ledger** (see/add/edit/delete stored facts); (b) a per-message **"memory used here" indicator** showing which stored memory informed a response; (c) **cross-tool memory import** (from ChatGPT/Gemini/Grok) as a cheap acquisition lever. Generic memory management without the ledger/indicator is off-thesis.

### 4.9 Keyboard shortcuts & command palette
- **[P0]** **`Cmd/Ctrl+K` command palette**: search/jump-to-chat, new chat, focus composer, toggle theme, toggle sidebar, open shortcuts list.
- **[P0]** Core shortcut set (see §5.5 table) including new chat, focus composer, copy last response, toggle sidebar, and a **show-all-shortcuts** dialog (`Cmd/Ctrl+/`). The default set **must be validated against browser/OS-reserved combos** (e.g., `Cmd/Ctrl+Shift+S` collides with "Save As"/screenshot in some browsers) before locking — do not blindly mirror one vendor's set.
- **[P1]** **User-customizable keyboard shortcuts.** Let power users remap shortcuts — incumbents lock theirs, so this is a cheap differentiator for our persona. Remapping UI must reject/warn on browser-reserved combos.
- *AC:* All P0 actions reachable by keyboard alone; palette is fully keyboard-navigable and screen-reader friendly.

### 4.10 Sharing & export
- **[P0]** **Shareable unlisted conversation link** (read-only public-by-link; not indexed). Creating a link is explicit; user can revoke it.
  - *AC:* Shared view renders the conversation read-only with model attribution; no composer; revoke invalidates the link.
  - **Decision — public shares show model attribution but NOT per-message cost.** PRD 00's transparency contract is "model **and cost**"; we deliberately drop **cost** from *public* shares (privacy/competitive reasons) while keeping model attribution. Stated here so the share view doesn't silently diverge from the cross-cutting contract.
- **[P0]** **Copy-as-markdown**: copy the whole conversation (or a single message) as clean markdown. **Copy/export can optionally include per-message model + token + cost metadata** (our differentiator, captured in the data model per PRD 04) — distinct from the public-share view above, which omits cost. The full export must be **genuinely complete** (and, when memory ships, *include* memory) — beating ChatGPT's export, which historically excludes memory; export-as-portability is on-brand for a privacy-first product.
- **[P1]** Multi-format export (PDF / .docx / Markdown file download).
- **[P2]** Published "pages" (Perplexity-style formatted public artifact).

### 4.11 Citations / source cards + suggested follow-ups
- **[P1]** **Citations are first-class message parts** (`citation` part type, §4.4), each carrying a **stable ID** that binds an inline marker to a structured source object — *not* a loose `[n]` token inside a markdown string. When web search/RAG is used (PRD 02 owns retrieval), render **inline numbered citations** `[1][2]` that, on click/hover, reveal source title, domain/favicon, and snippet; render a **source-card list** (right-rail on desktop, stacked below answer on mobile).
- **[P1]** **Streaming resolution rule:** an inline citation marker may stream **before** its source metadata resolves. Render the marker in a **pending** state and resolve it (title/domain/snippet) when the source object arrives — mirroring the §5.4 "render once balanced" rule for math. A marker whose source never resolves degrades gracefully (no dangling `[n]`).
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
>
> **IME caveat (a11y/i18n):** if an IME composition is active (`event.isComposing` true, or `keyCode === 229`), `Esc` must be left to the IME (CJK input uses Esc to cancel a candidate) and must **not** stop the stream. Validate this with a usability/screen-reader check given the mobile-web + EU/multilingual persona.

- Layout (desktop, P0): `[ multiline textarea ] [ model tier control ] [ Send/Stop ]`. **No attach control at P0**; P1 layout adds `[+ attach]` and attachment chips above the input when vision/PDF ships. Model control is compact (label = current tier) and opens a tiered menu with brief metadata (relative speed/cost, modality) sourced from the registry.
- Composer is sticky to the bottom of the thread; remains anchored during streaming.
- Mobile composer specifics (touch targets, keyboard avoidance, sticky Stop): **defer to PRD 03**.

### 5.4 Renderer requirements (spec carefully)
- **Streaming-safe parsing:** the renderer must tolerate incomplete markdown each frame: auto-close open code fences for rendering, defer table rendering until a row boundary is parseable, never render raw `*`/`#`/backticks as a flash. No layout shift > the height of the newly added content.
- **Code blocks:** language label from the fence info-string; highlight progressively; copy copies raw source (not highlighted DOM); long blocks collapse with "show more"; (P1) download with sensible filename/extension from language.
- **Math:** KaTeX for `$…$` / `$$…$$`; render only once delimiters are balanced to avoid mid-token flashes.
- **Tables:** wrap in a horizontal-scroll container; sticky header optional; never overflow the viewport on mobile.
- **Images:** lazy-load, constrained max-width, alt text required (use model-provided alt or a generic label).
- **Links:** open in new tab, `rel="noopener noreferrer"`; show domain on hover.
- **Sanitization:** strip scripts/iframes/event handlers; allowlist-based HTML; this is both a quality and security requirement. *Mechanism:* **`rehype-harden`-class allowlist hardening** (as shipped in Streamdown) is the satisfying implementation for the §4.4 [P0 security] requirement; adopt Streamdown's hardening rather than a hand-rolled sanitizer.
- **Performance target:** rendering keeps up with stream at 60fps with no layout shift on a mid-tier mobile device; virtualize very long threads.
  - *Mechanism (implementation note — the lever behind the 60fps/no-shift target):* **buffer streamed deltas in a mutable ref and flush once per `requestAnimationFrame`** (rAF token-batching) rather than `setState` per token (the naive per-token re-render is the known jank anti-pattern); use **`scheduler.yield()`** to keep the main thread responsive and protect INP (optionally `startTransition`); parse markdown **incrementally per chunk (O(n)), not a full re-parse (O(n²)) every frame**, paired with the renderer's memoization model. This is the same pattern mirrored in PRD 03 for mobile.

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
- Inline marker `[n]` is a small superscript chip **backed by a stable citation-part ID** (§4.11); click scrolls to / highlights the matching source card; hover (desktop) shows a popover with title + snippet. A marker streamed before its source resolves shows a muted pending state until metadata arrives.
- Source cards: favicon, title, domain, short snippet, opens in new tab. Right-rail on wide screens; collapsible list under the answer on mobile.
- Follow-up chips: max ~3–4, tappable to send.

### 5.7 Accessibility baseline (deliberate differentiation lever)
- **Labeled controls:** every icon button has a descriptive accessible name (Copy, Regenerate, Edit, Thumbs up/down, Attach, Send, Stop) — explicitly fixing the unlabeled-button gap measured in incumbents.
- **ARIA live regions (announce model — get this right; it is the a11y wedge):** the **streamed answer text node must NOT be wrapped in an `aria-live` region** — doing so makes NVDA/JAWS re-read the partial text token-by-token (a known anti-pattern). Instead, announce **discrete status transitions** ("Generating", "Response ready", "Stopped") via a **separate polite status region** (`aria-live="polite"`, distinct from the message body). The completed message body is **navigable but not auto-announced** (avoiding the inverse Claude bug where nothing is announced at all). The **success-path completion announcement** ("Response ready") is specified in PRD 08 §9 — this surface implements it. Status lines render their progress through the same status region.
- **Full keyboard operability:** every action (send, stop, copy, regenerate, edit, navigate history, open palette, expand reasoning) reachable and operable by keyboard with visible focus states.
- **Semantic structure:** messages as a navigable list with roles; reasoning panel exposes expanded/collapsed state via ARIA.
- **Keyboard-shortcuts dialog accessibility (beats a measured leader gap):** the show-all-shortcuts dialog (§4.9, `Cmd/Ctrl+/`) **traps focus on open, receives focus**, is screen-reader navigable, and returns focus to the invoking control on close — directly fixing the inaccessible-shortcuts-dialog blocker documented in incumbents.
  - *AC:* opening the shortcuts dialog moves focus into it; Tab cycles within it; Esc closes and restores focus; every shortcut row is reachable and announced by a screen reader.
- **Sidebar/history landmarks (beats a measured leader gap):** the history sidebar (§4.5) exposes **landmark roles** (e.g., a labeled `navigation`/`complementary` region) so screen-reader users can jump to it directly instead of traversing from top of page.
  - *AC:* the sidebar is reachable as a named landmark; history items are a navigable list with accessible names.
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

1. **Branching data-model caution (risk) — narrative corrected.** Earlier drafts justified deferring branching by citing an "industry retreat from branching." That was a factual error: ChatGPT *launched* explicit **"Branch in new chat"** (Sep 2025, still live), and branching is standard in LibreChat/LobeChat; the 2026 ChatGPT change only restricted **editing/retry of arbitrary older messages** (a separate, likely model-version constraint). The correct lesson: **explicit copy-on-branch is good and shipped** (now **P1**, §4.6); only **implicit edit-an-old-message-rewrites-history** is the fragile pattern we avoid. **Decision for MVP:** edit is restricted to the most recent user turn (re-run in place, no tree) purely to keep the data model simple — *not* because of any "retreat." In-thread alternate-response **trees** remain **P2**; study a concrete fork implementation before designing that data model.
2. **Mobile artifact fallback (open).** Side-by-side panels are awkward on mobile-web; exact full-screen-toggle behavior must be defined with **PRD 03** before building even the MVP-lite side panel.
3. **Suggested-prompt card behavior (open).** Do cards send immediately or just prefill the composer? Default proposal: **prefill** (lower commitment, lets users edit), pending quick usability check.
4. **Slash commands — RESOLVED (committed P1).** Previously framed as a "risky/unproven" scope question; now a **committed P1 differentiator** (native `/` prompt library, §4.3) reframed as an underserved power-user need our persona already hacks around via extensions. No longer open.
5. **Token/char hints (open).** Consumer products generally hide these. Default: **omit** in MVP; reconsider only with evidence.
6. **Reasoning content storage (privacy/risk).** Providers may only return a *summary*, and some omit thinking by default (PRD 02 §3). We must **not** store or display reasoning the provider hides; the panel renders only what's emitted.
7. **Citation interaction details (partly resolved / open).** The data binding is now decided: citations are first-class parts with stable IDs and a pending→resolved streaming rule (§4.11). Still open: hover vs click and right-rail vs inline expansion — finalize with retrieval design (PRD 02) when web search lands.
8. **Search scope (open).** Title-only vs full-text history search at MVP depends on the search index (PRD 04); target full-text if feasible, fall back to title + recent-content otherwise.
9. **Sourcing caveat.** Research is partly secondary; re-verify any specific shortcut/limit against first-party docs before locking. Shortcut conventions here follow category norms and are safe; exact provider limits are not owned by this PRD.
10. **Contested cross-PRD items this surface touches (FLAGGED, not decided here).** Per the product owner, these are not unilaterally decided in this PRD; integrated as open flags only:
    - **Exact Pro price.** This PRD shows a **"Pro" capability-tier label** in the composer/model picker (§4.3, §5.3) and can include per-message cost metadata in copy/export (§4.10); none of those depend on the Pro *price*, which is owned by **PRD 05**. Metered Pro + P0 USD overage is resolved (PRD 00 D8, PRD 05 §9.4); only the price band remains contested. The tier label is safe regardless; do not encode a price here.
    - **EU AI Act content-marking date** (Aug 2 vs Dec 2 2026, plus a May-2026 provisional reshuffle) — owned by **PRD 00/04/05**, needs legal sign-off. Not surfaced on this chat surface today; if a content-marking/watermark badge ever lands in the renderer, gate it on that decision rather than assuming a date.
    - **Whether we serve minors / companion personas** — owned by **PRD 05** (policy/competitive). Not touched by this surface; flagged so onboarding/empty-state copy (§4.7) isn't designed around an unresolved audience decision.

---

## 9. References

**Internal**
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
