# AI Chat Products: Feature & UX Teardown (2025–2026)

**Workstream:** Comprehensive feature & UX teardown of leading AI chat products (web + mobile-web).
**Date:** 2026-05-27
**Purpose:** Feed Product Requirements Documents (PRDs) for a new web-based AI chat interface.

---

## 0. How to read this document

This report catalogs current (2025–2026) behavior of leading AI chat web/mobile-web products and distills patterns into a recommended MVP-vs-later feature set.

**Confidence flags used throughout:**

- **[Verified]** — Confirmed against a source consulted during this research (URL cited inline).
- **[Recall]** — From general knowledge of these products; not re-verified against a live source in this pass. Treat as a hypothesis to confirm during PRD work.
- **[Uncertain]** — Conflicting signals, fast-moving, or vendor-specific; verify before relying on it.

A note on sourcing: many cited pages are secondary (blogs, guides, review sites) rather than first-party docs. The broad patterns are consistent across many sources and match direct product experience, but **exact specifics (limits, dates, which tier gets what) should be re-verified against first-party help docs before locking PRD decisions.** The AI chat space changes monthly; several "facts" below carry dates (e.g., "as of March 2026") that may shift.

---

## 1. Product landscape at a glance

| Product | Positioning | Standout UX signature |
|---|---|---|
| **ChatGPT** (OpenAI) | Broadest general-purpose assistant | Canvas side-panel, Projects, unified voice+text, image gen, data analysis |
| **Claude** (Anthropic) | Writing/coding/reasoning; "workspace" framing | Artifacts (live preview + publish), Projects w/ 200K context, extended thinking |
| **Gemini** (Google) | Multimodal + Google ecosystem | "Neural Expressive" redesign, Canvas, Gems, Deep Research → interactive content |
| **Perplexity** | Answer engine / cited search | Inline numbered citations, source cards, follow-ups, Spaces, Pages |
| **Microsoft Copilot** | Microsoft 365-integrated assistant | Deep Office integration, agentic workflows, free Bing-backed tier |
| **Mistral Le Chat** | Fast, lightweight, multilingual, EU | Speed + multilingual focus |
| **DeepSeek** | Strong free tier, open reasoning | Toggle deep-thinking / web-search / upload; very transparent reasoning |
| **Poe** (Quora) | Multi-model aggregator | Discovery feed of bots/apps; many models under one subscription |
| **LibreChat / Lobe Chat / Open WebUI** | Open-source self-hosted UIs | Multi-provider, branching, presets, folders, tagging, RAG, MCP |

Sources: [Zapier best AI chatbots 2026](https://zapier.com/blog/best-ai-chatbot/); [IGMGuru best AI chatbots](https://www.igmguru.com/blog/best-ai-chatbots); [Arahi ChatGPT alternatives](https://arahi.ai/blog/chatgpt-alternatives). **[Verified]** general positioning; **[Uncertain]** on exact pricing/tier specifics.

---

## 2. Conversation & thread management

### Patterns observed

- **New chat:** Persistent button (sidebar top) + keyboard shortcut. ChatGPT: `Cmd/Ctrl+Shift+O`. **[Verified]** ([ai-toolbox shortcuts](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide))
- **History list:** Reverse-chronological sidebar, typically grouped by time ("Today / Yesterday / Previous 7 days"). **[Recall]** — consistent across ChatGPT, Claude, Gemini.
- **Rename / delete:** Inline via hover/overflow (`···`) menu. ChatGPT delete shortcut `Cmd/Ctrl+Shift+Backspace`. **[Verified]** ([ai-toolbox](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide))
- **Search:** Quick-switcher / search palette. ChatGPT `Cmd/Ctrl+K` opens search + jump-to-chat. **[Verified]** Open-source UIs (LibreChat) use Meilisearch for full-text search across history. **[Verified]** ([elest.io](https://blog.elest.io/librechat-vs-openwebui-vs-lobe-chat-which-to-self-host-in-2026/))
- **Pin / archive:** ChatGPT and others support archiving and pinning. **[Recall]** — exact placement varies; verify.
- **Folders / Projects / Workspaces / Spaces:** This is the major organizational primitive across all leaders.

### Projects / Spaces comparison

| Product | Container name | Key capabilities | Notes |
|---|---|---|---|
| ChatGPT | **Projects** | Drag a chat into a project; per-project goals/instructions in sidebar; shareable project thread links | Convert any chat to a Project by drag-drop from history. **[Verified]** ([datastudios](https://www.datastudios.org/post/chatgpt-canvas-projects-update-export-options-deep-research-voice-mode-and-mobile-workflow)) |
| Claude | **Projects** | Curated knowledge + chats in one place; **200K-token project context (~500-page book)**; Team activity feed for sharing best chats | Pro/Team. **[Verified]** ([Anthropic Projects](https://www.anthropic.com/news/projects)) |
| Gemini | **Gems** (custom assistants) | Reusable task-specific assistants from templates or natural-language descriptions | Gems are closer to "custom GPTs" than folders. **[Verified]** ([freshvanroot](https://freshvanroot.com/blog/google-gemini-review/)) |
| Perplexity | **Spaces** | Project folders for research; save reusable workflows; collaborative | **[Verified]** ([Perplexity hub](https://www.perplexity.ai/hub/blog/getting-started-with-perplexity)) |
| Open-source | Folders + tags | Open WebUI: conversation tagging, chat cloning; LibreChat: presets | **[Verified]** ([elest.io](https://blog.elest.io/the-best-open-source-chatgpt-interfaces-lobechat-vs-open-webui-vs-librechat/)) |

**Takeaway:** A "Project/Space" abstraction (named container + pinned instructions + attached files/knowledge + grouped chats) is now table-stakes for serious users, but is a **post-MVP** layer over basic chat history.

---

## 3. Message composer

### Patterns observed

- **Multiline input:** `Enter` sends, `Shift+Enter` newline (universal). **[Verified]** ([ai-toolbox](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide))
- **Send / Stop:** Send button morphs into a Stop button during generation. **[Recall]** — universal pattern.
- **Attachments:** Paperclip / "+" menu; supports files, images, and (per product) photos, camera, Drive/SharePoint connectors. ChatGPT file upload: hard limit **512MB/file**, text/doc capped at **2M tokens/file**; free users limited to ~3 uploads/day. **[Verified]** ([OpenAI file uploads help](https://help.openai.com/en/articles/8555545-uploading-files-with-advanced-data-analysis-in-chatgpt))
- **Drag-and-drop + paste image:** Drag files into the composer; paste images from clipboard. Standard across modern UIs and dev tools. **[Verified]** for dev tooling ([JetBrains AI chat](https://www.jetbrains.com/help/ai-assistant/chat-mode.html)); **[Recall]** for ChatGPT/Claude/Gemini consumer web (well-established).
- **Slash commands:** Type `/` to open a command popover (switch model, insert prompt template, run action). Strongest in dev tools and open-source UIs; in consumer chat, used for custom prompts/GPT invocation. **[Verified]** pattern ([assistant-ui slash commands](https://www.assistant-ui.com/docs/guides/slash-commands)); **[Uncertain]** on which consumer products expose `/` today.
- **Model picker placement:** Typically a dropdown at top of composer or top-of-thread header. DeepSeek exposes **toggles** for "deep thinking" and "web search" right in the composer rather than a model dropdown. **[Verified]** ([Zapier](https://zapier.com/blog/best-ai-chatbot/))
- **Token/char hints:** Generally **not** surfaced in consumer chat UIs (hidden complexity); more common in dev/playground tools. **[Recall]**
- **Mode toggles in composer:** Increasingly common — web search on/off, reasoning on/off, "Deep Research," image/video/music create menus (Gemini's "Create" menu). **[Verified]** ([9to5google redesign](https://9to5google.com/2026/05/19/gemini-app-google-io-2026/))

**Takeaway:** Composer is the highest-leverage surface. MVP must nail multiline + send/stop + image/file attach + paste + drag-drop + a model picker. Slash commands and inline mode toggles are strong later additions.

---

## 4. Streaming response UX

### Patterns observed

- **Token streaming:** Word/token-by-token streaming is universal and expected; perceived latency matters more than total time. **[Recall]**
- **Stop generation:** Stop button replaces send during stream; partial output is kept. **[Recall]**
- **"Thinking" / reasoning display:** A major 2025–2026 UX area.
  - **Pattern:** A collapsible reasoning panel that **auto-opens while streaming** (with a shimmer effect + brain icon), shows "Thought for X seconds," then **auto-collapses** when done. Users expand to read details. **[Verified]** ([shadcn AI reasoning](https://www.shadcn.io/ai/reasoning); [AI Elements reasoning](https://elements.ai-sdk.dev/components/reasoning); [Nuxt UI ChatReasoning](https://ui.nuxt.com/docs/components/chat-reasoning))
  - **Per-product flavor:** ChatGPT shows concise reasoning and auto-collapses; **DeepSeek is the most transparent** (shows full reasoning); **Claude renders reasoning as it streams** in a relatively structured, low-overload way. **[Verified]** ([digestibleux](https://www.digestibleux.com/p/how-ai-models-show-their-reasoning); [renezander](https://renezander.com/blog/claude-extended-thinking/))
  - **Key insight:** Most users don't want to read thousands of reasoning tokens — **stream into a collapsed panel + show a one-line summary** is the recommended production pattern. **[Verified]** ([renezander](https://renezander.com/blog/claude-extended-thinking/))
- **Loading/typing indicators:** Before first token, show a typing/skeleton indicator; tool-use steps ("Searching the web…", "Running analysis…") are shown as status lines. **[Verified]** ([digestibleux](https://www.digestibleux.com/p/how-ai-models-show-their-reasoning))

**Takeaway:** Smooth streaming + a clean stop control + a collapsible reasoning/status panel is core differentiating UX. The reasoning panel pattern is well-componentized and copyable.

---

## 5. Message actions

| Action | ChatGPT | Claude | Gemini | Perplexity | Notes |
|---|---|---|---|---|---|
| Copy | Yes (icon row under response; `Cmd+Shift+C` copies last response) | Yes | Yes | Yes | **[Verified]** ([ai-toolbox](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide)) |
| Regenerate / retry | Yes (retry most recent response) | Yes | Yes | Yes | ChatGPT restricted editing/retry to **most recent message only** (March 23, 2026). **[Verified]** ([aiproductivity](https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/)) |
| Edit user message | **Restricted to most recent message** (ChatGPT, 2026) | Yes (edit + re-run) | Yes | n/a | ChatGPT change removed editing of older prompts. **[Verified]** ([aiproductivity](https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/)) |
| Branch / alternate responses | Branching via edit historically; restricted in 2026 | Yes | Yes | Threads | Editing an earlier message used to create branches in ChatGPT; this was curtailed. Open-source UIs (LibreChat) explicitly support **fork/branch**. **[Verified]** ([Hacker News thread](https://news.ycombinator.com/item?id=46394566); [elest.io](https://blog.elest.io/librechat-vs-openwebui-vs-lobe-chat-which-to-self-host-in-2026/)) |
| Thumbs up/down feedback | Yes (icons under response; thumbs-down opens detail panel + note) | Yes | Yes | Yes | Used for model training. **[Verified]** ([transferllm](https://transferllm.com/blog/where-is-the-option-on-chatgpt-to-give-feedback-complete-guide-2026/)) |
| Read aloud / TTS | Yes | Yes | Yes | Yes | Also an accessibility feature. **[Recall]** |
| Share single message / response | Via share-link of conversation; Perplexity shares answer/Page | Share link / publish | Share | Pages | See §11. **[Verified]** in part |

**Takeaway:** Copy / regenerate / edit-last / thumbs feedback are MVP. Branching is a power-user feature (great differentiation, more complex data model). Note ChatGPT's 2026 retreat from deep editing/branching — a signal that unconstrained branching is hard to get right.

---

## 6. Rich content rendering

### Patterns observed (now considered baseline quality bar)

- **Markdown:** Full CommonMark + GFM (tables, task lists, footnotes). **[Verified]** ([streamdown.ai](https://streamdown.ai/))
- **Code blocks:** Syntax highlighting (Shiki / Prism), language label, **copy button**, sometimes **download** and line numbers. ChatGPT has a "copy last code block" shortcut (`Cmd/Ctrl+Shift+;`). **[Verified]** ([streamdown.ai](https://streamdown.ai/); [ai-toolbox shortcuts](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide))
- **Math/LaTeX:** Rendered via **KaTeX**, inline `$…$` and block `$$…$$`. **[Verified]** ([streamdown.ai](https://streamdown.ai/))
- **Mermaid diagrams:** Interactive flowchart/sequence diagrams with fullscreen view. **[Verified]** ([streamdown.ai](https://streamdown.ai/); [merMDitor](https://www.mermditor.dev/))
- **Tables:** GFM tables; horizontally scrollable on mobile. **[Recall]**
- **Streaming-safe rendering:** Tools like **Streamdown** specifically handle markdown that arrives mid-token (e.g., unclosed code fences) so rendering doesn't flicker/break during streaming — a subtle but important quality detail. **[Verified]** ([assistant-ui Streamdown](https://www.assistant-ui.com/docs/ui/streamdown))
- **Images, link previews, collapsible sections:** Inline image rendering is standard; Gemini's redesign adds **inline images, narrated videos, timelines, interactive visualizations** directly in responses. **[Verified]** ([9to5google](https://9to5google.com/2026/05/19/gemini-app-google-io-2026/))

**Takeaway:** A high-quality, **streaming-safe** markdown renderer (code+copy, KaTeX, Mermaid, tables) is an MVP requirement — users now judge product quality heavily on rendering fidelity. Use/adapt a battle-tested renderer (e.g., Streamdown-style) rather than rolling your own.

---

## 7. Citations & sources (Perplexity-style)

### Patterns observed

- **Inline numbered citations:** Every factual claim numbered `[1][2][3]`; clicking shows URL, title, and supporting snippet. Typical answer has **5–10 inline citations**. **[Verified]** ([unusual.ai Perplexity guide](https://www.unusual.ai/blog/perplexity-platform-guide-design-for-citation-forward-answers); [stackmatix](https://www.stackmatix.com/blog/perplexity-ai-optimization-strategy))
- **Source cards / list:** Sources shown as a list/right-rail of cards (title, domain, favicon, snippet). **[Verified]** ([techsifted Perplexity review](https://techsifted.com/reviews/perplexity-ai-review-2026/))
- **Follow-up questions:** Suggested follow-ups under the answer; thread keeps context so users refine without restating. **[Verified]** ([Perplexity hub](https://www.perplexity.ai/hub/blog/getting-started-with-perplexity))
- **Pages:** Perplexity auto-formats research into a publishable page (headings, sections, visuals) with citations carried over, at a shareable `perplexity.ai/page/...` URL. **[Verified]** ([Perplexity hub](https://www.perplexity.ai/hub/blog/getting-started-with-perplexity))
- **Convergence:** ChatGPT/Gemini/Claude all now show web sources/citations when search is used, though Perplexity remains the citation-forward leader. **[Recall]**

**Takeaway:** If our product includes web search / RAG, inline citations + source cards + suggested follow-ups are essential and a strong trust/differentiation signal. This is a later phase unless search is in MVP scope.

---

## 8. Artifacts / Canvas / side panels

This is the most significant UX innovation of the era: a **split view** with chat on the left and a live, editable work surface on the right.

| Product | Name | Content types | Live preview / execution | Editing | Versions | Share/publish |
|---|---|---|---|---|---|---|
| Claude | **Artifacts** | Docs (MD/text), code, single-page HTML sites, SVG, diagrams/flowcharts, interactive **React components** | Yes — changes render live in artifact window; "Try fixing with Claude" on errors | Request edits from Claude; copy/download | Version selector to switch iterations | Publish publicly + embed; **viewer usage counts against viewer's own subscription** | 
| ChatGPT | **Canvas** | Documents and code | Inline targeted edits, length controls, language conversion; can build interactive apps + call APIs | Direct inline editing | — | Export to **PDF, .docx, Markdown, code files** (.py/.js/.sql) |
| Gemini | **Canvas** | Docs, code, web pages, infographics, quizzes, apps/games | Transforms Deep Research reports → interactive visuals/apps | Yes | — | Share |

Sources: [Claude Artifacts help](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them); [InstaPods Canvas guide](https://instapods.com/blog/what-is-chatgpt-canvas/); [datastudios Canvas update](https://www.datastudios.org/post/chatgpt-canvas-projects-update-export-options-deep-research-voice-mode-and-mobile-workflow); [Gemini Canvas](https://gemini.google/overview/canvas/). **[Verified]**

Additional 2026 evolutions:
- **Claude Live Artifacts** (April 2026): dashboards/trackers that refresh with current data on reopen (stay connected to data sources). **[Verified]** ([eigent](https://www.eigent.ai/blog/claude-live-artifacts-guide))
- ChatGPT Canvas is **on by default for all tiers** (web/desktop/mobile) in 2026. **[Verified]** ([instapods](https://instapods.com/blog/what-is-chatgpt-canvas/))

**Mobile-web caveat:** Side-by-side split is hard on small screens; products fall back to a full-screen toggle/tab between chat and artifact. **[Recall]** — important for our mobile-web target; verify exact behavior.

**Takeaway:** Artifacts/Canvas is high-value but high-complexity (sandboxed execution, versioning, live preview). Strong **Phase 2/3** differentiator; a lightweight "open long code/doc in a side panel with copy/download" is a feasible MVP-lite version.

---

## 9. Voice, image generation, file understanding, data analysis

- **Voice mode (ChatGPT, Nov 2025):** Voice and text **merged into one interface** — talk while seeing responses appear in real-time on the same screen; no separate voice mode to switch into; can view past messages, images, maps mid-voice. Advanced Voice can **share screen/video** for real-time guidance. Free users get Advanced Voice with time limits. **[Verified]** ([TechCrunch](https://techcrunch.com/2025/11/25/chatgpts-voice-mode-is-no-longer-a-separate-interface/); [theaiinsider](https://theaiinsider.tech/2025/11/26/openai-updates-chatgpt-interface-to-integrate-voice-conversations-directly-into-chats/))
- **Image generation:** ChatGPT integrates DALL·E 3 — brief in any language, get ~4 alternatives, refine conversationally; outputs commercially usable. **[Verified]** ([PAM AI Studio](https://www.pamistanbul.com/en/pamlab/chatgpt-image-generation-dall-e-guide.html)). Gemini "Create" menu spans image/video/music. **[Verified]** ([9to5google](https://9to5google.com/2026/05/19/gemini-app-google-io-2026/))
- **File/document understanding:** Upload PDFs, Word, slides; vision on images. ChatGPT limits: 512MB/file, 2M tokens/file text. **[Verified]** ([OpenAI help](https://help.openai.com/en/articles/8555545-uploading-files-with-advanced-data-analysis-in-chatgpt))
- **Data analysis (Code Interpreter / Advanced Data Analysis):** Writes + runs Python (pandas/matplotlib/numpy) in a secure sandbox to analyze uploaded data and produce charts. **[Verified]** ([QWE academy](https://www.qwe.edu.pl/tutorial/chatgpt-advanced-data-analysis-upload-files/); [MIT Sloan](https://mitsloanedtech.mit.edu/ai/tools/how-to-use-chatgpts-advanced-data-analysis-feature/))
- **DeepSeek** exposes simple **toggles** for deep-thinking, web search, and uploads — a clean low-friction model. **[Verified]** ([Zapier](https://zapier.com/blog/best-ai-chatbot/))

**Takeaway:** These are mostly **backend-capability-dependent** (model + sandbox infra). File understanding and image input are the most MVP-feasible; voice mode and code execution are later.

---

## 10. Onboarding, empty states, suggested prompts

### Patterns observed

- **Empty state must teach capability:** Without examples, users guess. Surface supported tasks via suggestion prompts / example queries. **[Verified]** ([fuselabcreative](https://fuselabcreative.com/chatbot-interface-design-guide/))
- **Starter-prompt cards:** Gemini's empty state uses **four cards**, each a different call-to-action chosen to showcase variety of use cases. **[Verified]** ([fuselabcreative](https://fuselabcreative.com/chatbot-interface-design-guide/))
- **Friendly tone + low barrier:** Even a tiny prompt ("say hi") lowers the barrier; playful copy/illustration reduces friction. **[Verified]** ([eleken empty state UX](https://www.eleken.co/blog-posts/empty-state-ux))
- **Example/template galleries:** Pre-built templates aligned to common use cases. (Poe takes this furthest with a **discovery feed of bots/apps by category**.) **[Verified]** ([fuselabcreative](https://fuselabcreative.com/chatbot-interface-design-guide/); [Zapier](https://zapier.com/blog/best-ai-chatbot/))

**Takeaway:** Cheap to build, high impact on activation. **MVP**: centered greeting + 3–4 suggested-prompt cards + a focused composer.

---

## 11. Settings, personalization, sharing & export

### Settings & personalization
- **Custom instructions / memory:** ChatGPT custom instructions (dialog at `Cmd/Ctrl+Shift+I`); persistent **memory** managed under Settings → Personalization → Manage Memory. Claude added **memory for free accounts (March 2026)** + a memory **import** flow (`claude.com/import-memory` / Settings → Capabilities → Memory Import). **[Verified]** ([ai-toolbox shortcuts](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide); [willfrancis migration guide](https://willfrancis.com/move-memory-from-chatgpt-to-claude/))
- **Themes:** Light/dark/system is universal. **[Recall]**
- **Data controls:** Toggle whether chats train the model; manage/clear history. **[Verified]** (export under Data Controls) ([OpenAI export help](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data))

### Sharing & export
- **Share link:** Create a shareable link to a conversation (public/unlisted). **[Verified]** ([tactiq export guide](https://tactiq.io/learn/export-chatgpt-conversation))
- **Full data export:** ChatGPT Settings → Data Controls → Export data → email link (expires 24h); ZIP includes `conversations.json` (+ metadata) and a browser-readable `chat.html`. Memory is **not** in the export. **[Verified]** ([OpenAI export help](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data); [mindlock](https://mindlock.io/blog/how-to-export-chatgpt-conversations))
- **Canvas export formats:** PDF, .docx, Markdown, code files. **[Verified]** ([datastudios](https://www.datastudios.org/post/chatgpt-canvas-projects-update-export-options-deep-research-voice-mode-and-mobile-workflow))
- **Public pages:** Perplexity Pages publishes formatted research with citations at a shareable URL. **[Verified]** ([Perplexity hub](https://www.perplexity.ai/hub/blog/getting-started-with-perplexity))

**Takeaway:** Custom instructions + theme + basic data controls + share-link + copy/markdown export are achievable in MVP. Memory and rich multi-format export are later.

---

## 12. Keyboard shortcuts & power-user features

ChatGPT web shortcut set (representative of the category). **[Verified]** ([ai-toolbox](https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide))

| Action | Shortcut (Mac / Win-Linux) |
|---|---|
| Send / newline | `Enter` / `Shift+Enter` |
| Open search / jump to chat | `Cmd+K` / `Ctrl+K` |
| New chat | `Cmd+Shift+O` / `Ctrl+Shift+O` |
| Focus composer | `Shift+Esc` |
| Copy last response | `Cmd+Shift+C` / `Ctrl+Shift+C` |
| Copy last code block | `Cmd+Shift+;` / `Ctrl+Shift+;` |
| Toggle sidebar | `Cmd+Shift+S` / `Ctrl+Shift+S` |
| Open custom instructions | `Cmd+Shift+I` / `Ctrl+Shift+I` |
| Delete chat | `Cmd+Shift+Backspace` / `Ctrl+Shift+Backspace` |
| Show all shortcuts | `Cmd+/` / `Ctrl+/` |

Note: ChatGPT shortcuts are **not customizable**. **[Verified]** Open-source UIs and dev tools tend to be more configurable. Power-user features include a **command palette** (`Cmd+K`), slash commands, presets (LibreChat), mid-chat endpoint switching (LibreChat), and conversation tagging (Open WebUI). **[Verified]** ([elest.io](https://blog.elest.io/librechat-vs-openwebui-vs-lobe-chat-which-to-self-host-in-2026/))

**Takeaway:** A small, discoverable shortcut set + a `Cmd+K` command palette delivers most power-user value cheaply. Build it in MVP.

---

## 13. Accessibility

### Patterns observed (and gaps to beat)
- **Semantic HTML + ARIA roles + ARIA live regions** are needed so screen readers announce streaming responses; status updates ("generating…") should be announced. **[Verified]** ([sitelint chatbot a11y](https://www.sitelint.com/blog/making-chatbots-accessible-a-guide-to-enhance-usability-for-users-with-disabilities); [MITRE playbook](https://mitre.github.io/chatbot-accessibility-playbook/docs/4_3_4.html))
- **Documented gaps in leaders (Oct 2025 testing):** ChatGPT icon bubbles **lack alt text** and buttons **lack labels** (can't tell copy vs edit vs rating via screen reader); Claude requires focusing the copy button to have generated text read; Bard/Gemini provided generation status updates while Claude/ChatGPT did not. **[Verified]** ([accessibility-test.org](https://accessibility-test.org/blog/qa-testing/automated-testing/ai-accessibility-testing-chatgpt-vs-claude-vs-gemini-oct-2025/); [Harvard URC](https://urc.library.harvard.edu/blog/review-generative-ai-chatbots-accessibility))
- **Read Aloud** doubles as an accessibility aid; voice input/dictation lowers barriers. **[Verified]** ([sitelint](https://www.sitelint.com/blog/making-chatbots-accessible-a-guide-to-enhance-usability-for-users-with-disabilities))

**Takeaway:** Accessibility is a clear **differentiation opportunity** — the leaders have measurable gaps. Labeled icon buttons, ARIA live regions for streaming, keyboard operability, and announced status are low-cost, high-trust wins. Bake into MVP.

---

## 14. Cross-product feature matrix (summary)

| Feature | ChatGPT | Claude | Gemini | Perplexity | Copilot | DeepSeek | Open-source UIs |
|---|---|---|---|---|---|---|---|
| Projects/Spaces/folders | Projects | Projects (200K) | Gems | Spaces | (M365) | — | Folders/tags/presets |
| Artifacts/Canvas | Canvas | Artifacts (Live) | Canvas | Pages | — | — | (varies) |
| Inline citations | When searching | When searching | When searching | **Core** | Yes | Web search | Via search/RAG |
| Reasoning display | Collapsed | Streamed | Yes | — | — | **Most open** | Configurable |
| Voice mode | Unified voice+text | Yes | Yes | Yes | Yes | App | — |
| Image gen | DALL·E 3 | (limited) | Create menu | — | Yes | — | Provider-dependent |
| Data analysis | Adv. Data Analysis | Analysis tool | Yes | — | Yes | Code exec | — |
| Branching | Restricted (2026) | Yes | Yes | Threads | — | — | **Fork/branch** |
| Memory | Yes | Yes (free, 2026) | Yes | — | Yes | — | Memory system |
| Multi-provider | No | No | No | Multi-model | (MS stack) | No | **Yes** |

(Cells reflect the sources cited above; **[Uncertain]** on exact current tier availability per cell.)

---

## 15. Recommended feature set for our product (MVP vs later)

> Goal framing: a web + mobile-web AI chat interface comparable to ChatGPT/Claude/Gemini/Perplexity. The biggest near-term risk is **rendering/streaming quality and composer ergonomics**, not exotic features. Win on a fast, polished core + accessibility, then layer organization and artifacts.

### MVP (must-have to be credible) — the 8–12 essentials
1. **Streaming chat with stop** — token streaming, stop control that preserves partial output, typing/skeleton indicator before first token.
2. **High-quality, streaming-safe markdown renderer** — code blocks with syntax highlighting + copy button, KaTeX math, GFM tables, safe rendering of in-flight tokens. (Biggest perceived-quality lever.)
3. **Robust composer** — multiline (`Enter`/`Shift+Enter`), send/stop, image + file attach, **paste image**, **drag-and-drop**, model picker.
4. **Conversation management** — new chat, history sidebar (time-grouped), rename, delete, **search**.
5. **Core message actions** — copy, regenerate, edit-last-message + re-run, thumbs up/down.
6. **Collapsible reasoning/status panel** — auto-open while thinking, "Thought for Xs," auto-collapse; show tool/status lines ("Searching…").
7. **Onboarding empty state** — greeting + 3–4 suggested-prompt cards.
8. **Settings basics** — light/dark/system theme, custom instructions, basic data controls (clear history; training opt-out if applicable).
9. **Share + lightweight export** — shareable conversation link (unlisted) + copy-as-markdown export.
10. **Keyboard shortcuts + `Cmd/Ctrl+K` command palette** — new chat, search, focus composer, copy last, toggle sidebar.
11. **Accessibility baseline** — labeled icon buttons, ARIA live regions for streaming, full keyboard operability, announced generation status. (Cheap differentiator.)
12. **Responsive mobile-web layout** — collapsible sidebar, touch-friendly composer, sticky stop button.

### Phase 2 (fast follow)
- **Projects/Spaces:** named container + pinned instructions + attached files + grouped chats.
- **File/document understanding** (PDF/Word/images → context) and **image input (vision)**.
- **Web search + inline citations + source cards + suggested follow-ups** (Perplexity-style trust layer).
- **Pin / archive**, conversation **tagging/folders**.
- **Memory** (persistent user facts) with a transparent management UI.
- **Read aloud (TTS)** and **voice input (dictation)**.
- **Multi-format export** (PDF/.docx/Markdown).
- **Branching / alternate responses** (note ChatGPT's 2026 retreat — design conservatively, e.g., explicit "branch from here" rather than implicit edits).

### Phase 3 (differentiators / heavier infra)
- **Artifacts/Canvas:** side panel with live preview, versioning, copy/download; later sandboxed code execution + data analysis.
- **Image / media generation.**
- **Unified voice mode** (talk + see responses on one screen).
- **Custom assistants** (Gems/GPT-style) and/or **template gallery**.
- **Multi-provider/model aggregation** (Poe/LibreChat-style) — viable strategic differentiator vs single-vendor incumbents.

### Main tradeoffs
- **Polish vs breadth:** Incumbents are broad; we can't out-feature them at launch. Win on **speed, rendering fidelity, accessibility, and composer ergonomics** first. A janky renderer or laggy stream reads as "low quality" instantly.
- **Artifacts/Canvas ROI:** Highest "wow," but expensive (sandboxing, versioning, live preview) and **awkward on mobile-web** (must degrade to full-screen toggle). Defer; ship a read-only "open in side panel + copy/download" first.
- **Branching complexity:** Powerful but a non-trivial data model and confusing UX if implicit. ChatGPT's 2026 restriction is a caution flag — prefer explicit, visible branching later.
- **Search/citations dependency:** Requires a search/RAG backend and careful trust UX; high value but couples us to retrieval infra — Phase 2 once the chat core is solid.
- **Multi-provider as wedge:** Being model-agnostic (like Poe/LibreChat) differentiates from single-vendor apps and future-proofs against model churn, but adds abstraction cost and per-provider quirks (capabilities, attachments, citations differ).

### Top differentiation opportunities (where incumbents are weak)
1. **Accessibility done right** — leaders have documented, measurable gaps (unlabeled buttons, missing live regions). Low cost, high trust.
2. **Best-in-class mobile-web** — most polish goes to native apps and desktop web; an excellent *mobile-browser* experience (composer, attachments, artifact fallback) is underserved.
3. **Rendering & streaming fidelity** — streaming-safe markdown + crisp reasoning panel as a core brand quality.
4. **Model-agnostic / multi-provider** — one UI over many models, future-proof.
5. **Transparent, well-designed reasoning + citations** — combine DeepSeek-level transparency (opt-in) with Perplexity-level source clarity.

---

## 16. Open questions / things to verify before PRD lock
- **Exact current tier availability** per feature (free vs paid) for each product — fast-moving; confirm against first-party help pages.
- **Slash-command presence** in *consumer* ChatGPT/Claude/Gemini web today (verified for dev tools/OSS; uncertain for consumer chat).
- **Mobile-web artifact/canvas fallback behavior** — confirm exactly how each product degrades the split view on small screens (load-bearing for our mobile-web target).
- **Token/char hint conventions** — confirm none of the major consumer products surface these (to decide whether we should).
- **Branching data model** — study LibreChat's fork implementation as a concrete reference before designing ours.
- **Citation/source-card interaction details** — hover vs click, right-rail vs inline expansion; verify Perplexity's current exact behavior.
- **Accessibility specifics** — re-test current ChatGPT/Claude/Gemini a11y state (the cited testing is Oct 2025) to validate the differentiation thesis still holds.
- **Sourcing caveat** — several cited pages are secondary; validate any number/date/limit against first-party docs before it enters a PRD.

---

### Appendix: primary sources consulted (selection)
- Claude Artifacts (first-party): https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them
- Anthropic Projects (first-party): https://www.anthropic.com/news/projects
- OpenAI file uploads (first-party): https://help.openai.com/en/articles/8555545-uploading-files-with-advanced-data-analysis-in-chatgpt
- OpenAI data export (first-party): https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data
- Gemini Canvas (first-party): https://gemini.google/overview/canvas/
- Perplexity getting started (first-party): https://www.perplexity.ai/hub/blog/getting-started-with-perplexity
- TechCrunch — ChatGPT unified voice: https://techcrunch.com/2025/11/25/chatgpts-voice-mode-is-no-longer-a-separate-interface/
- 9to5Google — Gemini Neural Expressive redesign: https://9to5google.com/2026/05/19/gemini-app-google-io-2026/
- accessibility-test.org — a11y comparison: https://accessibility-test.org/blog/qa-testing/automated-testing/ai-accessibility-testing-chatgpt-vs-claude-vs-gemini-oct-2025/
- Streamdown (streaming markdown rendering): https://streamdown.ai/
- shadcn AI reasoning component: https://www.shadcn.io/ai/reasoning
- elest.io — OSS UI comparison: https://blog.elest.io/librechat-vs-openwebui-vs-lobe-chat-which-to-self-host-in-2026/
- ai-toolbox — ChatGPT keyboard shortcuts: https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-keyboard-shortcuts-guide
- aiproductivity — ChatGPT editing/branching restriction: https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/
