# PRD 06 — Design System & Visual Spec

**Product:** Transparent, multi-model, privacy-first AI chat (web + mobile-web first).  
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
- Citation/source rail full design (**P1**; reserve component slots now).
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

### 3.5 Live-region announce model **[P0]**
- A **single, separate polite status region** (`aria-live="polite"`, `role="status"`) owns generation-status announcements; the streamed **message body is NOT a live region** (wrapping it causes token-by-token re-reading on NVDA/JAWS — a known anti-pattern).
- Status region announces **discrete transitions only**: "Generating", **"Response ready"** (success-path completion), "Stopped". The completed message body stays navigable but is not auto-announced.
- Error/limit announcements follow PRD 08 §9 (`role="status"` for warnings, `role="alert"` only when immediate attention is required). Behavior owned by PRD 01 §5.7 / PRD 08 §9; this PRD specifies the region.

---

## 4. Layout primitives **[P0]**

| Primitive | Spec | Owner |
|---|---|---|
| App shell | Header + optional sidebar + chat column | PRD 03 |
| Sidebar / drawer | History, search, new chat, grouped threads | PRD 01/03 |
| Composer bar | `[textarea] [tier picker] [Send/Stop]`; attach added P1 | PRD 01/03 |
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

### 5.5 Usage / budget meter **[P0]**
- Platform-key users: period usage vs cap.
- BYOK sessions: "Billed to your key"; no platform token markup.
- Approaching limits use warning state; hard caps hand off to PRD 08.

### 5.6 Composer + tier picker **[P0]**
- Tier labels: Fast / Smart / Pro / Auto; no raw model IDs by default.
- Menu shows relative speed/cost/context hints from registry.
- P0 is text-only; attach/paperclip is hidden until P1.

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

---

## 6. Phase boundaries

| Item | P0 | P1 | P2 |
|---|---|---|---|
| Core tokens + themes | Yes | — | — |
| Message, composer, reasoning, attribution, meter | Yes | — | — |
| Error/limit visual primitives | Yes | — | — |
| Citation/source card visuals | Slots only | Full | — |
| Mermaid chrome | Code/source view | Interactive/fullscreen | — |
| Memory ledger UI | — | Yes | — |
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

---

## 8. Open questions

1. Brand font vs system stack — only if LCP budget allows.
2. Cost default visibility — always-visible vs collapsed + expand; recommendation: collapsed with visible summary.
3. EU content-marking badge — pending legal resolution in PRD 04/05.
4. RTL QA depth for MVP — logical CSS is P0; full locale QA can phase.
