# PRD 06 — Design System & Visual Spec

**Product:** Transparent, multi-model, cost-leading AI chat (web + mobile-web first).  
**Owner:** Product Design (with Engineering review).  
**Status:** Draft for build.  
**Date:** 2026-05-27.  
**Related PRDs:** [00 Overview](00-product-overview.md) · [01 Core Chat](01-core-chat-experience.md) · [03 Mobile](03-mobile-cross-platform.md) · [05 Roadmap/NFRs](05-roadmap-monetization-metrics.md) · [07 Transparency Contract](07-transparency-contract.md) · [08 Error & Limit States](08-error-and-limit-states.md).

> **What this document is.** The visual and component contract for a lean, text-core P0: tokens, typography, layout primitives, and chat-specific components that make transparency, power-user density, mobile-web quality, and accessibility feel intentional. Implementation baseline: **shadcn/ui + Tailwind** on Next.js 16 (PRD 04). This PRD skins behavior owned by PRD 01/03/07/08; it does not redefine it.

---

## 1. Purpose

Incumbents compete on breadth; this product competes on **polish + trust surfaces**. The design system ensures:

- **Transparency is product chrome:** model badge, cost line, budget meter, and substitution callout are first-class UI.
- **Power users get density without clutter:** compact defaults with expandable details.
- **Mobile-web is primary:** thumb-zone composer, safe areas, 44–48px targets, sticky Stop.
- **Accessibility is designed in:** labels, contrast, live regions, keyboard paths, reduced motion.

---

## 2. Goals & non-goals

### Goals
- Define minimal P0 tokens: color, type, spacing, radius, elevation, motion.
- Define P0 chat components and their visual states.
- Encode privacy/trust surfaces consistently: BYOK, temporary chat, no-train, model/cost attribution.
- Meet WCAG 2.1 AA (stretch 2.2 AA where cheap).

### Non-goals
- Marketing site / brand campaign system.
- Artifact/canvas full design (**P2**).
- Citation/source rail full design (**P1**; the full **source-card list is shipped** — `sources-panel.tsx`; inline `[n]` citation chips remain pending).
- Native iOS/Android design languages (Capacitor **P2** reuses web tokens).

---

## 3. Foundations

### 3.1 Color **[P0]**
- Semantic roles: `background`, `foreground`, `muted`, `border`, `primary`, `destructive`, `success`, `warning`, `info`.
- Chat roles: `message-user`, `message-assistant`, `reasoning-muted`, `code-block`, `status-line`, `substitution-callout`.
- Trust roles: `trust-badge`, `byok-indicator`, `temporary-chat-banner`.
- Light / dark / system themes; all body text pairs **>= 4.5:1** contrast.

**AC:** zero hard-coded colors in chat feature code outside token/CSS variables.

### 3.2 Typography **[P0]**
- UI font: system stack or one variable sans; no blocking custom font on critical path.
- Monospace: code blocks and token/cost numerals.
- Chat body: 16px base, `rem`-based; message column capped around 70–80ch on wide screens.
- Pseudo-localization must not break attribution rows or composer layout.

### 3.3 Spacing, radius, elevation **[P0]**
- 4px base grid.
- Composer/header respect all four `safe-area-inset-*`.
- Message surfaces remain flat; elevation reserved for drawer/sheet/modal.

### 3.4 Motion **[P0]**
- Streaming and reasoning shimmer allowed by default.
- `prefers-reduced-motion`: static "Generating..." and no shimmer.
- **[P1] Reduced-motion media policy (extends the above to every animated media/voice surface).** The static-under-`prefers-reduced-motion` rule is a *single enforced policy* covering not just streaming/reasoning shimmer but the dictation listening indicator (§5.1), read-aloud reading-position highlight (§5.1), the voice-mode waveform, generated-image reveals (§5.4), and citation scroll/highlight (§5.6). No new animated media surface may ship that regresses the reduced-motion guarantee. Cite D22.

### 3.5 Live-region announce model **[P0]**
- A **single, separate polite status region** (`aria-live="polite"`, `role="status"`) owns generation-status announcements; the streamed **message body is NOT a live region** (wrapping it causes token-by-token re-reading on NVDA/JAWS — a known anti-pattern).
- Status region announces **discrete transitions only**: "Generating", **"Response ready"** (success-path completion), "Stopped". The completed message body stays navigable but is not auto-announced.
- Error/limit announcements follow PRD 08 §9 (`role="status"` for warnings, `role="alert"` only when immediate attention is required). Behavior owned by PRD 01 §5.7 / PRD 08 §9; this PRD specifies the region.

---

## 4. Layout primitives **[P0]**

| Primitive | Spec | Owner |
|---|---|---|
| App shell | Header + optional sidebar + chat column | PRD 03 |
| Sidebar / drawer | History, search, new chat, grouped threads (+ [P1] Projects section, tag chips, archive/bulk-select — §5.10) | PRD 01/03 |
| Composer bar | `[textarea] [tier picker] [Send/Stop]`; attach added P1 (attach shipped behind provider capability; inert on DeepSeek) | PRD 01/03 |
| Message list | Virtualized scroll region + jump-to-latest FAB | PRD 03 |
| Command palette | `Cmd/Ctrl+K`; full keyboard navigation | PRD 01 |
| Settings/data | Theme, custom instructions, BYOK, data controls | PRD 01/04 |
| Empty state | Greeting + 3–4 prompt cards | PRD 01 |

---

## 5. Chat components

### 5.1 Message bubble **[P0]**
- User: aligned end, plain text.
- Assistant: aligned start, part renderer for text/code/reasoning/status.
- Footer actions: copy, regenerate, edit (user last only), thumbs.
- All icon-only controls need accessible names.
- **[P1] Read-aloud (TTS) control + reading-position highlight.** A labeled "Read aloud" action joins the footer action row (alongside copy / regenerate / thumbs); it toggles to a Stop/pause treatment while playing, and reflects playing/paused state in **text + glyph, not color alone**. While playing, the current sentence is highlighted caption-style in the message body (the reading-position indicator the §3.4 reduced-motion policy degrades to a static highlight). Track-A (OS `speechSynthesis`, free) records zero cost; Track-B (billed neural voice) surfaces a per-message audio-cost chip on the attribution row (§5.4). Behavior owned by PRD 01 §4.6 / PRD 02 §4.8; this PRD specifies the control + highlight chrome. Cite D22.

### 5.2 Streaming + Stop **[P0]**
- Pre-first-token skeleton/typing state appears within 150ms.
- Send morphs to Stop in the same slot; Stop is 44x44px minimum on mobile.
- Stopped state shows neutral "Stopped" chip, not red error treatment.

### 5.3 Reasoning panel **[P0]**
- Collapsed: "Thought for Xs" + chevron.
- Expanded: muted panel above answer.
- Hidden entirely when no reasoning/summary is emitted.

### 5.4 Model attribution row **[P0]**
- Every assistant message shows served model/tier without hover.
- Expandable details: tokens, cost, estimate badge, routing notes.
- Served-vs-requested substitution uses `substitution-callout`, not generic error red.
- BYOK turns show "Your API key" badge.
- **[shipped] Cost-anomaly callout:** when no substitution clause is present, the byline can lead with a muted "why this cost" reason — "High reasoning cost" / "Long context" / "No cache hit" — derived from the cost breakdown (`attribution-row.tsx`, `cost-breakdown.tsx` `costAnomaly`).
- **[shipped] JSON-output chip:** when structured output was requested, the row shows a "JSON" chip, switching to "JSON (invalid)" (warning glyph) when the output failed to parse — the validity state reads in **text, not color alone** (`attribution-row.tsx`).
- **[P1] Audio-cost chip (read-aloud Track B / dictation).** When a turn's read-aloud or dictation rode a *billed* neural-audio route (not the free OS engine), the row carries an audio-units cost component in the same expandable cost detail (per-minute STT / per-character TTS), with `cost_confidence` semantics intact; a route with no published audio rate labels as estimate/unavailable, never `$0.00`-exact. The free OS-voice path shows no audio cost. Cite D22.
- **[P2] Generated-image part attribution + provenance badge.** A generated-media (`image`) part renders its own attribution: **which model produced it** and a **per-image cost** (priced per-image/megapixel → the cost breakdown; estimate/unavailable label when the rate is unknown — never an un-attributed image), using the same served-vs-requested substitution and `cost_confidence` treatment as text. Every generated image also carries a visible **"AI-generated" provenance badge** (a `trust-badge`-family affordance, announced to screen readers) backed by a structured provenance field (model · provider · timestamp · marking-standard/version); with content-marking unconfigured the visible "AI-generated" affordance still renders. The provenance badge is a **content claim, not cost data** — it is retained on public share while cost/tokens are stripped (PRD 07 §6.4). Cite D32 (and D22 for the cost/attribution spine).

### 5.5 Usage / budget meter **[P0]**
- Platform-key users: period usage vs cap.
- BYOK sessions: "Billed to your key"; no platform token markup.
- Approaching limits use warning state; hard caps hand off to PRD 08.
- **[shipped]** A **user-editable monthly budget cap** (with an explicit Save) that surfaces the platform's tighter enforced cap when it binds ("Enforced cap: … — the platform cap is tighter than your setting"), a **credit balance** line, and recent **ledger rows** (`settings-dialog.tsx` `BudgetEditor` / `UsageDetails`; the compact byline meter is `usage-meter.tsx`).
- **[P1] Longitudinal spend-analytics surface (Insights / Usage).** A dedicated view that expands the shipped byline meter + `UsageDetails` seed into a longitudinal dashboard: spend (USD) + message count over selectable ranges, breakdowns by **model/tier · conversation · day** (each a share-of-total bar), a **platform-vs-BYOK** split, and a **budget burn-down** projecting period-end spend vs the effective cap. **Charts are table-first for a11y:** every visualization renders as an **accessible data table first, visualization second** — non-color encodings throughout, numerals in monospace (§3.2/§3.3), `prefers-reduced-motion` disables animated draw-in, range/breakdown toggles ≥44px. Numbers must label their **cost basis** (cumulative meter vs surviving-message sum) and never silently mix them (PRD 07 §6.4 / §8 reconciliation). Proactive **budget-alert** thresholds (soft/hard cap, per-conversation cap) are set/visualized here. Behavior owned by PRD 01 §4 / PRD 05 §6; this PRD specifies the table-first chart chrome. Cite D27.

### 5.6 Composer + tier picker **[P0]**
- Tier labels: Fast / Smart / Pro / Auto; no raw model IDs by default.
- Menu shows relative speed/cost/context hints from registry.
- P0 is text-only; attach/paperclip is hidden until P1.
- **[shipped]** The picker grew into a combined **model + provider + reasoning-effort + web-search + JSON-output** control (`model-mode-picker.tsx`; desktop dropdown / mobile bottom sheet). The provider section appears only when >1 route is available; web search appears only on search-capable tiers; reasoning-effort rows disable with a one-line note when the served provider ignores effort.
- **[shipped]** An optional **Compare** toggle sits next to the model controls when the surface offers it (`composer.tsx`), and the **attach paperclip is shown only on attachment-capable tiers** (so it's inert on the prod DeepSeek backend).
- **[P1] Dictation (STT) mic button.** A **mic button** sits adjacent to Send in the composer; tapping it starts capture (tapping again or a silence timeout stops). It is **shown only when a capable STT route is configured** (hidden/disabled — never a silently-dead control — where no engine is available, e.g. Firefox without a server route, or an installed iOS PWA on the Web-Speech path). A clear, **animated "listening" indicator** with an elapsed timer and a visible Stop shows during capture and degrades to a static indicator under `prefers-reduced-motion` (§3.4). Dictation **never auto-sends** — recognized text lands editable in the textarea and is sent with the normal Send control. First capture is gated by a one-line route/data-posture disclosure (PRD 03 §4.7). Mic tap target ≥44px. Behavior owned by PRD 03 §4.7 / PRD 01 §4.3; this PRD specifies the composer chrome. Cite D22.

### 5.7 Code block **[P0]**
- Language label, syntax highlighting, copy button.
- Long blocks collapse with "Show more."
- Copy button is a real button and touch-safe.

### 5.8 Trust/privacy chrome **[P0]**
- Persistent AI-interaction disclosure.
- Temporary chat banner and distinct thread treatment.
- BYOK status in settings and usage meter.
- Data controls use consistent destructive-confirm patterns.

### 5.9 Share/export **[P0]**
- Public share: model visible, cost/tokens hidden.
- In-app copy/export: model + cost metadata may be included.

### 5.10 Conversation organization chrome **[P1]**
- **Projects section in the sidebar:** a collapsible "Projects" section sits **above** the recency groups (extends the existing `GROUP_ORDER`/`sidebar.tsx` grouping). A Project row carries a name and an optional decorative color/emoji that is **`aria-hidden` and never the sole identifier** — the name is always present. Selecting a project filters the list to its conversations and surfaces a project header (instructions + scoped defaults). A conversation shows its **project chip** in the thread header.
- **Tags:** freeform per-conversation tag chips (color optional), filterable via a chip row above the list or the search filters (§5.6 picker is unaffected). Tag chips are labeled; management (rename/merge/delete) lives in settings with ≥44px targets.
- **Archive + bulk select:** an "Archived" filter hides archived threads from the default list; a multi-select mode (checkbox on desktop hover, long-press on mobile, coexisting with the existing swipe actions) exposes bulk archive / move-to-project / add-tag / delete. The selection toolbar is a labeled region announcing the count ("3 selected"); destructive bulk delete confirms with a count using the consistent destructive-confirm pattern (§5.8). Reduced-motion is respected on list enter/exit (already in `sidebar.tsx`'s `RowWrapper`).
- Behavior/data owned by PRD 01 §4.5; this PRD specifies the navigation chrome. Cite D20.

---

## 6. Phase boundaries

| Item | P0 | P1 | P2 |
|---|---|---|---|
| Core tokens + themes | Yes | — | — |
| Message, composer, reasoning, attribution, meter | Yes | — | — |
| Error/limit visual primitives | Yes | — | — |
| Citation/source card visuals | Slots only | **Full source-card list — shipped** (`sources-panel.tsx`); inline `[n]` chips pending | — |
| Mermaid chrome | Code/source view | **Interactive/fullscreen — shipped** (rendered diagram via lazy Streamdown plugin, not code-only) | — |
| Memory ledger UI | — | Yes | — |
| Voice/media chrome: dictation mic + listening indicator, read-aloud control + reading-position highlight, Track-B audio-cost chip (§5.1/§5.4/§5.6) | — | Yes | — |
| Reduced-motion media policy across all animated media/voice surfaces (§3.4) | — | Yes | — |
| Conversation org chrome: Projects section, tags, archive/bulk-select (§5.10) | — | Yes | — |
| Longitudinal spend-analytics surface, table-first charts (§5.5) | — | Yes | — |
| Generated-image part: attribution + per-image cost + provenance badge (§5.4) | — | — | Yes |
| Artifact/canvas design | — | Read-only stretch | Full |

---

## 7. Release acceptance criteria

1. 100% assistant messages render attribution component.
2. Forced substitution fixtures show the substitution callout.
3. Public share view hides cost/tokens but shows model.
4. axe-class check: 0 critical violations on chat, composer, settings, palette.
5. 100% icon-only buttons labeled.
6. Mobile primary controls >=44px; composer safe-area verified on iOS Safari.
7. Light/dark/system parity for all P0 components.
8. Reduced-motion path verified for streaming/reasoning states.
9. Keyboard-shortcuts dialog traps/receives focus, is screen-reader navigable, and restores focus on close (per PRD 01 §5.7).
10. Sidebar/history exposes a named landmark region for direct screen-reader navigation (per PRD 01 §5.7).
11. **[P1]** The dictation mic and read-aloud controls are absent/disabled (never silently dead) when no capable route is configured; when present they are labeled and keyboard-operable, and their animated states (listening indicator, reading-position highlight) degrade to static under `prefers-reduced-motion`.
12. **[P1]** The spend-analytics surface renders every chart as an accessible data table first; numbers label their cost basis; reduced-motion disables animated draw-in.
13. **[P2]** A public share view of a thread with a generated image shows the image + model attribution **and** retains its "AI-generated" provenance badge, while still hiding cost/tokens (consistent with PRD 07 §6.4).

---

## 8. Open questions

1. Brand font vs system stack — only if LCP budget allows.
2. Cost default visibility — always-visible vs collapsed + expand; recommendation: collapsed with visible summary.
3. EU content-marking badge — pending legal resolution in PRD 04/05.
4. RTL QA depth for MVP — logical CSS is P0; full locale QA can phase.
