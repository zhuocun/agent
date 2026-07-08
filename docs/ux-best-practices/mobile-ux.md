# UX Best Practices — Mobile

**Owner:** Product/UX (Best-Practices canon)
**Status:** Draft for build
**Date:** 2026-07-05
**Scope:** Mobile-web / PWA touch surface of the transparent, multi-model AI chat product. Best-practice guidance + gap callouts, grounded in the 2026-07-05 research pass (R1–R5).
**Companion:** [desktop-ux.md](./desktop-ux.md) — identical taxonomy, pointer/keyboard surface.
**Related canon:** [PRD 01 Core Chat](../prd/01-core-chat-experience.md) · [PRD 02 AI Capabilities](../prd/02-ai-capabilities.md) · [PRD 03 Mobile](../prd/03-mobile-cross-platform.md) · [PRD 06 Design System](../prd/06-design-system-visual-spec.md) · [PRD 07 Transparency](../prd/07-transparency-contract.md) · [PRD 08 Error/Limit States](../prd/08-error-and-limit-states.md) · [Design principles](../design/00-principles.md) · [Mobile ST5 spec](../mobile-ux/ST5-spec.md).

> **How to read.** Each section states the 2026 best practice (external, cited by `C#`), then the repo's stance: ✅ covered (link canon, don't restate) · ◑ partial · ✗ gap · ➕ opportunity. Items are ordered gaps-first. `[verify-at-build]` marks facts to re-check at build. This doc is guidance, not an implementation contract — the PRDs own the spec.

---

## 1. Purpose, scope & how to read

**Best practice.** Mobile AI chat surfaces should optimize for thumb reach, 44/48px touch targets, bottom-anchored primary actions, safe-area compliance, and iOS Safari constraints (16px input floor, visualViewport keyboard, first-party cookies). [C52][C54][C55]

**Repo stance.**

- **Treat this doc as the mobile companion to [desktop-ux.md](./desktop-ux.md).** Shared semantics must read identically; mobile-only patterns live in §13.
- **PRD 03 and ST1–ST5 audits are the implementation contract for mobile values.** — ✅ link, don't restate; this doc adds external rationale and gap callouts.
- **Every gesture must have a ≥44pt tap alternative.** — ✅ swipe actions, long-press bulk select, bottom sheets. [C31]

---

## 2. Chat surface — composer, rendering & streaming

**Best practice.** Mobile composers should require explicit Send tap (not Enter-to-send), anchor to the thumb zone with safe-area padding, avoid iOS input zoom (<16px), and stream with the same rAF batching and non-live-region a11y model as desktop. [C54][C55][C35][C38]

**Repo stance.**

- **Do not bind Enter to send on mobile; require explicit Send tap.** — ✅ per [PRD 01 §4.3](../prd/01-core-chat-experience.md) deferring to [PRD 03](../prd/03-mobile-cross-platform.md).
- **Anchor composer to bottom; apply all four `safe-area-inset` values.** — ✅ `app-shell.tsx`, `composer.tsx`. [C52]
- **Keep Send/Stop ≥44pt and sticky during streaming without scrolling.** — ✅ `min-h-11` / `size-11` on primary controls.
- **Keep all form controls ≥16px font-size on mobile to prevent iOS Safari auto-zoom.** — ✅ ST-8 gate; `text-base md:text-sm` on selects. [C55][C56]
- **Use `visualViewport` (not `dvh` alone) to lift composer above software keyboard on iOS.** — ✅ `use-visual-viewport.ts`. [C54]
- **Buffer streamed tokens per rAF; yield main thread during long parses.** — ✅ same as desktop. [C38][C39]
- **Do not wrap streamed body in `aria-live`; use discrete polite status region.** — ✅ `live-region.tsx`. [C34][C35]
- **Auto-follow stream only near bottom; show "Jump to latest" otherwise.** — ✅ [PRD 01 §5.1](../prd/01-core-chat-experience.md).
- **Render streaming-safe markdown with sanitization and code copy-of-raw.** — ✅ [PRD 01 §4.4](../prd/01-core-chat-experience.md).
- **Offer dictation into editable textarea; never auto-send transcript.** — ◑ hooks exist; verify ship state. [PRD 01 §4.3]

**Platform note (Mobile).** Message actions must be always-visible on touch — never hover-only.

---

## 3. Message actions, branching & sharing

**Best practice.** Touch message actions should be always visible or reachable via overflow; support the same copy/regenerate/edit/feedback/branch flows as desktop; substitution callouts must be readable without hover. [C26]

**Repo stance.**

- **Keep message actions always visible on touch (no hover-only disclosure).** — ✅ [Design patterns D](../design/02-patterns.md).
- **Offer Copy, Regenerate, Edit-last, thumbs on every assistant turn.** — ✅ [PRD 01 §4.6](../prd/01-core-chat-experience.md).
- **Show model/tier attribution at rest without requiring tap-to-reveal.** — ✅ `attribution-row.tsx`.
- **Render visible substitution callout (requested, served, reason) — not pill-only.** — ✅ `attribution-row.tsx` renders the "Rerouted from {requested} → {served} · {reason}" callout inline, per [PRD 07 §6.1](../prd/07-transparency-contract.md). [C26]
- **Branch-in-new-chat without in-thread version trees.** — ✅ shipped.
- **Share via unlisted link; public view strips cost/memory, keeps model attribution.** — ✅ [PRD 01 §4.10](../prd/01-core-chat-experience.md).

---

## 4. Conversation management & navigation

**Best practice.** Mobile history should live in a left drawer (hamburger + edge swipe), with swipe actions on rows, long-press for bulk select, and search reachable from palette or drawer header. [C52]

**Repo stance.**

- **Render history in left drawer below 768px; hamburger + 20px edge-swipe zone opens nav.** — ✅ `app-shell.tsx`. [PRD 03 §4.1](../prd/03-mobile-cross-platform.md)
- **Handle Android system back: close drawer before leaving page (History API).** — ✅ shipped.
- **Expose swipe-to-archive/delete on conversation rows.** — ✅ `use-swipe-actions.ts`.
- **Enter bulk select via long-press on mobile.** — ◑ specced; verify ship state. [PRD 01 §4.5](../prd/01-core-chat-experience.md)
- **Keep row actions always visible or in overflow — not hover-only.** — ✅ touch pattern.
- **Expose labeled `<nav>` landmark on drawer.** — ✅ `sidebar.tsx`.
- **Keep state coherent across tabs and PWA windows (BroadcastChannel or `storage` events); server stays source of truth on reload/refocus.** — ✗ no cross-tab channel ships; `localStorage` is a write-only fast-path (`chat-thread.tsx`) and stream reconnect (`stream-client.ts`) is same-tab only — a second tab or installed-PWA window catches up only on reload. [C76]

**Platform note (Mobile).** Drawer must honor left safe-area inset and not trap focus when closed.

---

## 5. Agentic & tool-use UX

**Best practice.** Agentic surfaces on mobile use the same component tree as desktop; collapsible panels default closed at rest to protect vertical space; HITL approval controls must meet 44pt targets. [C1][C6]

**Repo stance.**

- **Render plan-approval, tool cards, and subagent panel with same semantics as desktop.** — ✅ shared components. [C1]
- **Show estimated cost + cap in approval card.** — ✅ `tool-part.tsx` `PlanApprovalDetail` renders "Estimated run cost" + "Per-run cap" above the plan steps. [C4]
- **Keep collapsible tool/subagent panels collapsed at rest post-stream.** — ✅ progressive disclosure.
- **Ensure HITL approve/deny buttons ≥44pt touch targets.** — ✅ `min-h-11` on tool rows. [C52]
- **Show live per-run cost meter during fan-out.** — ✅ `RunCostMeter` in the `subagent-panel.tsx` header (subtotal / cap), fed by `run_cost` frames via `stream-client.ts` + `agentic-layout.ts`. [C11]
- **Expose Stop prominently during runs; retain partial output.** — ✅ Stop in composer thumb zone. [C15]
- **Cue settled runs when the app is backgrounded — PWA app badge (`navigator.setAppBadge`) and/or opt-in notification, cleared on refocus.** — ✗ no Badging or Notification usage in `web/src` or `public/sw.js`; runs settle silently while the app is hidden (see M15). [C73][C74]
- **Do not build cross-session agent dashboard.** — ✅ intentional.

**Platform note (Mobile).** Subagent panel may cap visible worker rows and scroll; per-worker elapsed time especially valuable on long mobile sessions.

---

## 6. Grounding, web search & citations

**Best practice.** Citation markers on mobile use tap-to-expand (no hover); source cards stack below the answer; marker hit targets ≥44pt. [C18][C22]

**Repo stance.**

- **Map inline `[n]` to source cards; tap marker scrolls to and highlights card.** — ◑ reveal wired; inline chips partial.
- **Use tap-to-popover on citation markers (no hover); dismiss via tap-away or Esc.** — ➕ lightweight preview opportunity. [C18]
- **Stack source cards below answer on mobile (not right rail).** — ✅ [PRD 01 §5.6](../prd/01-core-chat-experience.md).
- **Show ungrounded marker when search returns zero sources.** — ✅ `UngroundedMarker`.
- **Keep source panel collapsed at rest ("N sources").** — ✅ `sources-panel.tsx`.

---

## 7. Model selection & the transparency contract

**Best practice.** Model/tier picker on mobile should open as bottom sheet within thumb reach; tiers framed as effort scale; Auto's resolved route shown post-turn. [C23][C24]

**Repo stance.**

- **Open model/tier picker as bottom sheet on compact width.** — ✅ `model-mode-picker.tsx` / `tier-picker.tsx`. [C23]
- **Show tier labels with model ID as secondary meta.** — ✅ `TierRow`.
- **Show served tier on every message without tap-to-reveal.** — ✅ `attribution-row.tsx`.
- **Keep per-message cost out of the thread.** — ✅ the per-message View-spend footer link was removed (#241) — spend lives in Settings → Activity (`spend-analytics-panel.tsx`) per D41 in [PRD 07 §6.1](../prd/07-transparency-contract.md).
- **Visible substitution callout with requested/served/reason.** — ✅ `attribution-row.tsx`; see §3.
- **Reasoning panel auto-open while streaming, collapse on complete.** — ✅ `reasoning-panel.tsx`. [C27]

**Platform note (Mobile).** Picker trigger should sit in composer toolbar or top-of-thread — reachable before send without reaching status bar.

---

## 8. Onboarding, guest, BYOK & settings

**Best practice.** Mobile onboarding should allow immediate anonymous chat, surface PWA install coachmark on iOS (no auto-prompt), organize settings as mobile master-detail drill-down, and never echo BYOK secrets. [C58][C42]

**Repo stance.**

- **Bootstrap guest session; first message without auth wall.** — ✅ anonymous-first flow.
- **Show welcome with tappable prompt suggestion buttons (prefill, not auto-send).** — ✅ `welcome-screen.tsx`.
- **Render persistent AI-interaction disclosure at first interaction.** — ✅ `ai-disclosure.tsx` rendered on the welcome screen (`welcome-screen.tsx`); #245 removed the below-composer placement, #247 restored it on the welcome/empty state. [C42]
- **Show iOS "Add to Home Screen" coachmark at contextual moment.** — ✅ `install-coachmark.tsx`. [C58]
- **Render settings as bottom sheet with master-detail tab drill-down.** — ✅ `settings-dialog.tsx`.
- **BYOK: password field, never echo, encrypted-server cue.** — ✅ `byok-form.tsx`.
- **Cover the account lifecycle end-to-end: sign out, data export, and hard delete with confirmation — export/delete available to guests too.** — ◑ sign out, JSON export, and delete-account ship in `settings-dialog.tsx` (both data endpoints accept anonymous callers); email-change and password-change/reset flows are absent.
- **Audit remaining controls below 44pt (checkbox, segmented toggles, `size="sm"` in settings).** — ✅ [ST2 touch audit](../mobile-ux/ST2-touch-audit.md) offenders closed in #244: `hover:none`-gated `min-h-11` floor in `buttonVariants`, `::before` hit-slop on `checkbox.tsx`, `min-h-11` segments in `settings-dialog.tsx` and `compare-view.tsx`.

---

## 9. Billing, usage meters & limit states

**Best practice.** Usage meters and limit errors on mobile should be readable without horizontal scroll; inline limit blocks should surface `actions[]` buttons at thumb reach. [PRD 08](../prd/08-error-and-limit-states.md)

**Repo stance.**

- **Escalate usage meter tone at thresholds; BYOK branch distinct.** — ✅ `usage-meter.tsx`.
- **Render limit errors inline in thread with Upgrade/Add credits/BYOK actions.** — ◑ inline buttons ship in `ErrorFooter` (`assistant-message.tsx`) for every `error.actions[]` entry (kinds: retry / open_settings / dismiss; `Sign up` added to `PLATFORM_GUEST_LIMIT`), but dedicated Upgrade/Add-credits/BYOK deep-link actions still funnel through open_settings.
- **Use bottom sheet for billing/checkout flows.** — ✅ settings billing section.
- **Show `meta.reset_at` as live countdown where applicable.** — ◑ structured meta exists; countdown partial.

---

## 10. Accessibility

**Best practice.** Mobile a11y must meet WCAG 2.2 AA with 44/48px touch targets (stricter than 24px floor), focus not obscured by keyboard or chrome, and the same streaming live-region model as desktop. [C30][C52][C34]

**Repo stance.**

- **Use 44pt (iOS) / 48dp (Android) minimum touch targets with ≥8px spacing.** — ✅ gated on `@media (hover:none)`. [C52]
- **Expand hit regions via padding/`::before` without visually resizing controls.** — ✅ checkbox/switch hit-slop (ST-7).
- **Single polite status region for streaming; body not a live region.** — ✅ `live-region.tsx`. [C34][C35]
- **Announce "Stopped" through polite region.** — ◑ verify shipped.
- **Dropdown menu items get `min-h-11` on touch.** — ✅ `[@media(hover:none)]` in menu primitives.
- **Honor `prefers-reduced-motion` with static alternates per affordance.** — ✅ `globals.css`.
- **Do not use `user-scalable=no` to suppress iOS input zoom.** — ✅ not used; 16px floor instead. [C56]
- **Keep focused rows clear of sticky chrome and keyboard (WCAG 2.4.11).** — ✅ `scroll-margin` on `.chat-message-row` (`globals.css`).

**Platform note (Mobile).** 44/48px touch floor, 24px WCAG floor, and 2.4.13 focus indicator are three different numbers — never conflate.

---

## 11. Performance

**Best practice.** Mobile INP is especially sensitive to keyboard + streaming; virtualize long threads; bound cold-start; optimistic send improves perceived latency. [C37][C41]

**Repo stance.**

- **rAF token batching + `scheduler.yield()` with fallback.** — ✅ `scheduler-yield.ts`. [C38][C39]
- **Virtualize messages past ~80 with overscan.** — ✅ `message-list.tsx`. [C41]
- **Persist composer drafts per conversation in IndexedDB for offline resilience.** — ✅ `offline-store.ts`.
- **Optimistic send echoes user turn immediately.** — ✅ shipped.
- **Bound bootstrap with timeout + retry.** — ✅ `BOOTSTRAP_TIMEOUT_MS`.
- **Set `overscroll-behavior: contain` on scroll regions; drop pull-to-refresh on chat.** — ✅ PTR kills in-flight streams. [C57]

---

## 12. Trust, privacy & safety

**Best practice.** Mobile users need the same AI disclosure, no-train framing, and honest grounding as desktop; iOS Safari requires first-party cookies via same-origin API proxy. [C42][C63]

**Repo stance.**

- **Ship AI-interaction disclosure at first interaction (Art. 50(1)).** — ✅ `ai-disclosure.tsx` (`role="note"`, `aria-label`) on the welcome screen. [C42]
- **Proxy `/api/*` same-origin so session cookie is first-party on Vercel origin (iOS ITP).** — ✅ `web/next.config.ts` rewrite. [C63]
- **State no-train default in settings; per-route data policy in model directory.** — ✅ shipped.
- **Never silently downgrade; surface substitution with reason.** — ✅ substitution callout with requested/served/reason ships in `attribution-row.tsx` (§3, §7).
- **Mark ungrounded search turns.** — ✅ shipped.
- **Offline queue visible with retry on reconnect.** — ✅ optimistic + offline store.

---

## 13. Platform surface — mobile touch & PWA

**Best practice.** Mobile-web AI chat should meet Apple/Material touch standards, handle iOS keyboard via `visualViewport`, ship PWA manifest with shortcuts, and respect platform differences (Android `interactive-widget` vs iOS visualViewport). [C52][C54][C58][C64]

This section confirms/refreshes [PRD 03](../prd/03-mobile-cross-platform.md) and [ST5 spec](../mobile-ux/ST5-spec.md). Findings from 2026-07-05 platform-split research:

| # | Surface | Best-practice guidance | Repo status |
| --- | --- | --- | --- |
| M1 | **44px touch targets & hit-slop** | iOS 44pt / Android 48dp minimum; ≥8px spacing; expand hit region without visual resize. | ✅ `buttonVariants` + checkbox/switch slop (ST-7). [C52] |
| M2 | **Thumb reachability** | Primary actions in bottom third; composer + Send pinned bottom. | ✅ composer thumb zone. [PRD 03 §5.3](../prd/03-mobile-cross-platform.md) |
| M3 | **Bottom sheets vs dialogs** | Bottom sheet for contextual choices; dialog for interruptive ack; compact width uses sheets. | ✅ `ui/dialog.tsx` sheet mode, `ui/drawer.tsx`. [C52] |
| M4 | **Safe-area insets** | `viewport-fit=cover` required; apply all four insets (notch, home indicator, landscape L/R). | ✅ `layout.tsx` `viewportFit: "cover"`. |
| M5 | **Keyboard avoidance (`visualViewport`)** | iOS keyboard resizes visual viewport only — `visualViewport` JS is primary; coalesce per rAF. | ✅ `use-visual-viewport.ts`. [C54] |
| M6 | **16px input-zoom floor** | All inputs/selects/textareas ≥16px on mobile; never `user-scalable=no`. | ✅ ST-8. [C55][C56] |
| M7 | **Haptics** | Feature-detect `navigator.vibrate` on Android; silent no-op on iOS. | ✅ `use-haptic.ts`. [C60][C61] |
| M8 | **PWA install & shortcuts** | Contextual install prompt on Android; iOS coachmark; manifest with `standalone` + shortcuts. | ✅ `manifest.ts`, `install-coachmark.tsx`. [C58][C59] |
| M9 | **Offline behavior** | IndexedDB drafts + optimistic send + resumable replay; server stays source of truth. | ✅ `offline-store.ts`, `stream-client.ts`. [C58][C62] |
| M10 | **Pull-to-refresh & overscroll** | Drop PTR on chat (kills streams); `overscroll-behavior: contain`. | ✅ applied. [C57] |
| M11 | **Orientation / landscape** | Handle landscape L/R safe-area; keyboard trap check in short viewports. | ◑ insets applied; auth/share scroll shells flagged. |
| M12 | **iOS Safari (ITP + address bar)** | First-party cookie via same-origin `/api/*` proxy; `dvh` shell + visualViewport for keyboard. | ✅ `next.config.ts` + viewport hooks. [C63] |
| M13 | **Android vs iOS** | `interactive-widget=resizes-content` on Chromium/Firefox; `visualViewport` on iOS; background sync Android-only. | ✅ both paths present. [C64] |
| M14 | **Theming & color scheme** | Honor `prefers-color-scheme` with a Light/Dark/System override; boot without theme flash; tint standalone/browser chrome and splash per scheme. | ✅ next-themes provider + `ThemeToggle`; paired light/dark `theme-color` metas + per-scheme iOS splash images in `layout.tsx`; `manifest.ts` single `theme_color` (light) is covered by the meta pairing. [C72] |
| M15 | **Background-run cues & app badge** | Badge the installed PWA (`navigator.setAppBadge`, Chromium + iOS 16.4+ installed) and/or notify when an agentic run settles while hidden; clear on focus. | ✗ no Badging/Notification usage in `web/src` or `public/sw.js`. [C73][C74] |
| M16 | **i18n / RTL readiness** | CSS logical properties; locale-aware `Intl.NumberFormat` for USD spend; `dir` derived from locale. | ◑ baseline ships — `dir` plumbing + `[dir="rtl"]` CSS baseline (`globals.css`) + en catalog (`lib/i18n/`); physical utilities dominate and `money.ts` pins `en-US`. ➕ full localization is P2. [C75] |
| M17 | **Tablet seam (≥768px touch)** | Tablets leave the drawer layout at 768px and get the desktop shell; touch floors must persist via pointer-capability gating (`hover:none`), not width. | ◑ `hover:none`-gated 44pt floors ship orthogonal to the `md:` seam, so a tablet gets desktop layout with touch targets; no dedicated tablet layout tier or real-device tablet pass — see [desktop D13](./desktop-ux.md#13-platform-surface--desktop-pointer--keyboard). [C77] |

**Cross-platform seam.** Every gesture (swipe, long-press, edge-drag) must have a visible tap/menu alternative (WCAG 2.5.7). Cross-reference [desktop-ux.md §13](./desktop-ux.md#13-platform-surface--desktop-pointer--keyboard).

**Open verification (empirical).** Real-device iOS lab: composer never covered by keyboard regardless of thread length; tapping composer does not yank scroll position. [PRD 03 §9](../prd/03-mobile-cross-platform.md)

---

## 14. Appendix — Actionable checklist

Each item is a single assertable statement. `[P0]/[P1]/[P2]` priority; `(§N)` back-reference.

### §2 Chat surface
- [ ] [P0] Mobile does not bind Enter to send; explicit Send tap required. (§2)
- [ ] [P0] Composer anchored bottom with all four safe-area insets applied. (§2) [C52]
- [ ] [P0] All form controls ≥16px on mobile (no iOS zoom); never `user-scalable=no`. (§2) [C55][C56]
- [ ] [P0] `visualViewport` drives composer inset above iOS keyboard. (§2) [C54]
- [ ] [P0] Streamed tokens flush per rAF; body not in `aria-live`. (§2, §10) [C38][C34]
- [ ] [P0] Send/Stop ≥44pt and reachable during streaming without scrolling. (§2)
- [ ] [P0] Message actions always visible on touch. (§2, §3)

### §3 Message actions
- [ ] [P0] Copy, Regenerate, Edit-last, thumbs on every assistant turn. (§3)
- [x] [P0] Substitution callout visible with requested/served/reason. (§3) — `attribution-row.tsx` [C26]
- [ ] [P1] Dictation fills editable textarea; never auto-sends. (§2)

### §4 Conversation management
- [ ] [P0] History in left drawer with hamburger + edge-swipe open. (§4)
- [ ] [P0] Android back closes drawer before page exit. (§4)
- [ ] [P1] Swipe actions on rows (archive/delete). (§4)
- [ ] [P1] Long-press enters bulk multi-select. (§4)
- [ ] [P2] Cross-tab/PWA-window continuity via BroadcastChannel or `storage` events. (§4) [C76]

### §5 Agentic & tools
- [ ] [P0] HITL approve/deny controls ≥44pt. (§5) [C52]
- [x] [P0] Plan-approval shows cost estimate + cap. (§5) — `tool-part.tsx` `PlanApprovalDetail` [C4]
- [x] [P0] Live per-run cost meter during fan-out. (§5) — `RunCostMeter` in `subagent-panel.tsx`
- [ ] [P0] Tool/subagent panels collapsed at rest post-stream. (§5)
- [ ] [P1] Run-settled cue while app hidden: PWA badge and/or opt-in notification, cleared on focus. (§5, §13) [C73][C74]

### §6 Citations
- [ ] [P0] Tap citation marker scrolls to source card; markers ≥44pt. (§6)
- [ ] [P1] Tap-to-preview on markers (title + domain). (§6) [C18]
- [ ] [P0] Source cards stack below answer on mobile. (§6)
- [ ] [P0] Ungrounded marker when zero sources. (§6)

### §7 Transparency
- [ ] [P0] Model picker opens as bottom sheet on compact width. (§7) [C23]
- [ ] [P0] Served tier visible without tap-to-reveal. (§7)
- [ ] [P0] Reasoning panel collapses after stream completes. (§7) [C27]

### §8 Onboarding & settings
- [x] [P0] AI-interaction disclosure at first interaction. (§8, §12) — `ai-disclosure.tsx` on welcome screen [C42]
- [x] [P0] iOS install coachmark at contextual moment. (§8) [C58] — closed 2026-07-07: coachmark now yields while follow-up chips intersect its band and parks at the safe-area floor on composer-less surfaces (ISSUE-6/7).
- [ ] [P0] Settings master-detail drill-down in bottom sheet. (§8)
- [x] [P1] All settings controls meet 44pt (ST2 audit items closed). (§8) — #244 `hover:none`-gated floors
- [ ] [P2] Account lifecycle rounds out with email/password change alongside shipped sign-out, export, delete. (§8)

### §9 Billing & limits
- [x] [P0] Inline limit errors with `actions[]` at thumb reach. (§9) — `ErrorFooter` buttons `min-h-11`; Upgrade/Add-credits/BYOK deep-links still ◑ (see §9)
- [ ] [P1] Usage meter escalation visible in header/footer. (§9)

### §10 Accessibility
- [ ] [P0] Touch targets ≥44pt with ≥8px spacing on `@media (hover:none)`. (§10) [C52]
- [x] [P0] Announce "Stopped" through polite region. (§10) [C34] — verified 2026-07-07: `chat-thread.tsx` sets "Generation stopped" through the polite `LiveRegion` on stop/terminal.
- [x] [P0] `prefers-reduced-motion` static path for every animation. (§10) — closed 2026-07-07: remaining animated controls (collapsible chevrons, swipe-tray/press-scale rows, header pill) gained `motion-reduce` paths.
- [x] [P1] Focus not fully obscured by keyboard or chrome. (§10) — `scroll-margin` on `.chat-message-row` (`globals.css`, WCAG 2.4.11)

### §11 Performance
- [ ] [P0] `overscroll-behavior: contain`; no pull-to-refresh on chat. (§11) [C57]
- [ ] [P0] Offline drafts persist in IndexedDB per conversation. (§11)
- [ ] [P0] Bootstrap timeout surfaces retry. (§11)
- [ ] [P1] Virtualized message list on long threads. (§11) [C41]

### §12 Trust
- [ ] [P0] Same-origin `/api/*` proxy for iOS ITP first-party cookies. (§12) [C63]
- [x] [P0] AI-interaction disclosure shipped. (§12) — `ai-disclosure.tsx` [C42]
- [x] [P0] No silent model downgrade. (§12) — `attribution-row.tsx`

### §13 Platform (mobile)
- [ ] [P0] `viewport-fit=cover` + all four safe-area insets. (§13) [C52]
- [ ] [P0] `visualViewport` keyboard path on iOS. (§13) [C54]
- [ ] [P0] PWA manifest with `standalone`, maskable icons, shortcuts. (§13) [C58][C59]
- [ ] [P0] Haptics feature-detected; no-op on iOS. (§13) [C60]
- [ ] [P0] `interactive-widget=resizes-content` for Android keyboard. (§13) [C64]
- [ ] [P1] Real-device iOS keyboard lab passed (composer never covered). (§13)
- [ ] [P0] Every swipe/long-press gesture has tap/menu alternative. (§13) [C31]
- [x] [P0] Theme follows `prefers-color-scheme` with no boot flash; chrome tint via paired `theme-color` metas. (§13) — next-themes + `layout.tsx` [C72]
- [ ] [P1] App badge (`setAppBadge`) on settled background runs, cleared on focus. (§13) [C74]
- [ ] [P2] Logical properties in new layout code; locale-aware `Intl.NumberFormat` for spend. (§13) [C75]
- [ ] [P1] ≥768px tablet width verified: desktop shell with touch floors intact (`hover:none`). (§13) [C77]

---

## Appendix — Citation keys (mobile)

External sources cited by `C#` key. Access date **2026-07-05** unless `[verify-at-build]`.

| Key | Source |
| --- | --- |
| C1–C17 | Agentic/HITL — [research memo](../research/2026-07-05/02-agentic-tool-ui-ux.md) |
| C18–C22 | Citations — ibid. |
| C23–C29 | Model/transparency — ibid. |
| C30–C36 | WCAG/ARIA — [cross-cutting memo](../research/2026-07-05/cross-cutting-ux-best-practices.md) |
| C37–C41 | Performance — ibid. |
| C42–C45 | Trust/legal — ibid. |
| C52–C64 | Mobile platform — [platform-split memo](../research/2026-07-05/ux-best-practices-platform-split.md) |
| C55–C56 | iOS 16px input floor |
| C58–C59 | PWA install + manifest shortcuts |
| C60–C61 | Haptics / Vibration API on iOS |
| C62–C63 | WebKit storage policy / ITP |
| C64 | Chrome `interactive-widget` viewport resize |
| C72 | Theming — `prefers-color-scheme` / `color-scheme`, no-flash theme boot (MDN, web.dev) `[verify-at-build]` |
| C73 | Page Visibility API — hidden-tab completion cues (MDN) `[verify-at-build]` |
| C74 | Badging API — `navigator.setAppBadge` for installed PWAs, Chromium + iOS 16.4+ (web.dev, WebKit) `[verify-at-build]` |
| C75 | i18n — CSS logical properties (MDN) + `Intl.NumberFormat` locale-aware currency (ECMA-402) `[verify-at-build]` |
| C76 | Cross-tab state sync — BroadcastChannel / `storage` events (MDN) `[verify-at-build]` |
| C77 | Tablet adaptation — `hover`/`pointer` media features, Material window size classes, iPadOS HIG `[verify-at-build]` |
