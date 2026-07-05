# Findings memo — UX best practices, platform split (Desktop / Mobile)

**Date:** 2026-07-05
**Role:** Research worker (platform-split). Read-only research; **no docs under
`docs/ux-best-practices/` were edited**. This memo is the source input that feeds
**both** downstream best-practice docs (the desktop doc and the mobile doc).
**Method:** grounded in-repo first (PRD 03, ST1–ST5 mobile-UX audits, the
2026-05-27 mobile research review, `web/next.config.ts`, `web/src/app/manifest.ts`,
and the live `web/src/**` component/lib tree), then refreshed against primary
sources (Apple HIG, Material Design 3 / Android adaptive, W3C WCAG 2.2, MDN,
web.dev, WebKit ITP). Sources accessed 2026-07-05.
**Scope note:** desktop and mobile findings are kept in **separate tables** (§2.1
desktop, §2.2 mobile) per the split brief. Same three-section structure as R1:
(1) grounding + repo coverage, (2) findings, (3) sources.

---

## 1. Grounding & repo coverage

The repo is a Next.js (App Router) + FastAPI chat app already shipping a
responsive, PWA-enhanced surface (PRD 03). Mobile UX is unusually mature — the
ST1–ST5 mobile-UX audits and the 2026-05-27 research review already lock most of
the mobile scope with primary-source citations. The **desktop** scope has **no
dedicated best-practice doc yet**, so this memo carries most of its new value on
the desktop side while confirming/refreshing the mobile side.

**What the repo already covers (verified in-tree):**

*Desktop:*
- **Keyboard shortcuts + discoverability:** a full binding registry
  (`chat-thread.tsx` `KEY_BINDINGS` — palette, new-chat, focus-composer,
  copy-last-response, copy-last-code, toggle-sidebar, custom-instructions,
  delete-chat, toggle-dictation, shortcuts), user-remappable with a
  **reserved-combo guard** that protects composer invariants (Enter/Escape) and
  **browser-critical combos** (⌘/Ctrl+C/V/X/A/Z/T/W/N/Q/R/L) and rejects Alt +
  duplicates (`lib/shortcut-defaults.ts`), a shortcuts dialog (`shortcuts-dialog.tsx`),
  and `⌘`/`Ctrl` key-cap rendering (`key-caps.tsx`, `lib/shortcut-format.ts`).
- **Command palette:** `command-palette.tsx` (the `palette` binding, ⌘/Ctrl+K
  class), grouped rows, filter `<select>`s, `focus-visible:shadow-[var(--focus-ring)]`.
- **Hover/focus states:** `hover:` + `focus-visible:shadow-[var(--focus-ring)]`
  used across ~34 components; a single `--focus-ring` token.
- **Multi-pane / compare:** `compare-view.tsx` renders 2-up on desktop
  (`grid-cols-1 … md:grid-cols-2`) with per-column handles (`compare-column.tsx`);
  the app shell escalates sidebar → chat → artifact column (PRD §4.1/§5.1).
- **Wide-viewport density / resize:** mobile-first type ramp that *densifies* on
  desktop via `md:` (ST5 §b), reading column cap ~70–80ch (PRD §5.3), a single
  source of truth for the shell (breakpoint hook + container queries, PRD §5.3).
- **Tooltips:** `ui/tooltip.tsx` (desktop-hover, low mobile impact per ST1).

*Mobile:*
- **visualViewport keyboard avoidance** (`lib/use-visual-viewport.ts`, rAF-coalesced,
  pinch-zoom guarded, 50px noise floor), consumed by the app shell.
- **All four safe-area insets** + `viewportFit: "cover"` +
  `interactiveWidget: "resizes-content"` (`app/layout.tsx`), applied to header,
  composer, dialogs, drawer, toasts, coachmark.
- **44/48px touch floors** gated on `@media (hover:none)` + checkbox hit-slop (ST-7).
- **16px input-zoom floor** (all inputs ≥16px; 3 stray `<select>`s ramped
  `text-base md:text-sm`, ST-8).
- **Haptics** feature-detected/no-op-on-iOS (`lib/use-haptic.ts`).
- **PWA:** `manifest.ts` (`display: standalone`, `shortcuts` jump-list, maskable
  icons), iOS `install-coachmark.tsx`, service worker.
- **Offline:** `lib/offline-store.ts`, optimistic send, resumable-stream replay
  (`lib/stream-client.ts`), `overscroll-contain` widely applied.
- **iOS ITP first-party cookie fix:** the same-origin `/api/*` → Fly rewrite in
  `web/next.config.ts` keeps the BE `Set-Cookie` first-party on the Vercel origin.

**Gaps found in-tree (flagged in the tables, not fixed here):**
- **No right-click context menu** anywhere (`onContextMenu` absent); message
  actions use a kebab/`dropdown-menu` + long-press instead (an acceptable
  accessible alternative, but the desktop right-click accelerator is unbuilt).
- **No drag-and-drop** (`draggable`/`onDrop`/`DataTransfer` absent) — relevant
  when attachments (PRD 01 §4.3, P1) or sidebar reordering arrive.
- No `screenshots` in the manifest (ST5 R8/G8, deferred pending assets).

---

## 2. Findings

Each row: **Surface → best-practice guidance → repo status → source(s)**.
`✅` covered · `◑` partial / needs verification · `○` gap.

### 2.1 Desktop findings

| # | Surface | Best-practice guidance | Repo status | Source |
| --- | --- | --- | --- | --- |
| D1 | **Keyboard shortcuts & discoverability** | Use ⌘/Ctrl as primary modifier; **respect system/browser-reserved combos** and never repurpose them; make shortcuts **discoverable** (a shortcuts sheet + inline hints in menus/tooltips), not secret; support Full Keyboard Access / a logical Tab key-view loop; allow customization as a labeled default. | ✅ Registry + reserved-combo guard (browser-critical + composer invariants + Alt/dup) + shortcuts dialog + key-caps + remap persistence. | Apple HIG *Keyboards* (Command primary, respect standard shortcuts, Full Keyboard Access); WWDC26 "Modernize your AppKit app" (key-view loop) [S1][S2] |
| D2 | **Command palette** | ⌘/Ctrl+K global toggle **plus a visible trigger** (never shortcut-only); move focus to the input on open, **restore focus to the opener on close**; arrows navigate, Enter activates, Escape closes; `role="dialog"` + listbox semantics, focus trapped while open; group commands, show scope + active row + empty/loading/failure states; keep **destructive commands out of one-keystroke** execution (require a confirm step). | ◑ Palette exists, grouped, focus-ring rows; verify a **visible entry point** + **focus-return-to-opener** + destructive-confirm on palette rows. | UX Patterns Guide *Command palette*; UX Patterns for Developers; cmdk guide [S3][S4][S5] |
| D3 | **Hover / focus states** | Hover is an **enhancement, not the sole affordance** (no hover on touch/keyboard); every interactive element needs a **visible focus indicator** (WCAG 2.4.7) meeting **Focus Appearance** (≥3:1 focused-vs-unfocused, area ≥ a 2px perimeter — 2.4.13 AAA) and **Non-text Contrast** (1.4.11); focused element must **not be fully obscured** by sticky chrome (2.4.11 AA). | ✅ `hover:` + `focus-visible:shadow-[var(--focus-ring)]` token used broadly; ◑ audit the focus-ring contrast/area vs 2.4.13 and sticky-header obscuring vs 2.4.11. | W3C WCAG 2.2 — 2.4.11 / 2.4.13 / 1.4.11 [S6][S7] |
| D4 | **Right-click context menus** | Fine as a power-user **accelerator**, but never the **only** path to an action — mirror every item in a visible menu/kebab/toolbar; use ARIA menu semantics + arrow-key nav + Escape; don't gratuitously suppress the native browser menu. | ○ No `onContextMenu` in-tree; message actions live in a kebab/`dropdown-menu` + mobile long-press (a valid alternative — the accelerator itself is unbuilt). | UX Patterns (accelerator-with-visible-equivalent principle); Apple HIG menus [S3][S1] |
| D5 | **Drag-and-drop** | **WCAG 2.5.7 (AA):** any dragging operation must also be achievable with a **single pointer without dragging** (e.g. a click-to-move / picker / "move to…" menu); make it keyboard-operable and announce drops. Applies to file-drop attach, sidebar reorder, sortable lists. | ○ No DnD today; becomes load-bearing when attachments (PRD 01 §4.3, P1) / sidebar reorder land — design the single-pointer alternative up front. | W3C WCAG 2.2 — 2.5.7 Dragging Movements [S6][S8] |
| D6 | **Multi-pane / compare layouts** | Use **canonical adaptive layouts** (list-detail, supporting pane); at expanded width split **~70/30** (primary/supporting), each pane **independently scrollable**; collapse the supporting pane into a bottom/side sheet at compact width; keep pane count driven by window-size class, not per-component. | ✅ `compare-view` = 2-up desktop grid (mobile tab strip fallback); shell escalates sidebar/chat/artifact by breakpoint (PRD §5.2). | Android *Canonical layouts* (supporting-pane 70/30, size-class driven) [S9] |
| D7 | **Wide-viewport information density** | **Densify on desktop** (smaller type, tighter spacing) while keeping the mobile floor; **cap the reading column (~70–80ch)** so wide screens don't produce fatiguing line lengths; don't stretch primary content edge-to-edge. | ✅ `md:`-ramped type (ST5 §b) inverts the mobile 16px floor down to 14/13/12/11 on desktop; ~70–80ch chat column cap (PRD §5.3). | ST5 §b type ramp (repo); PRD 03 §5.3 [repo] |
| D8 | **Window-resize behavior** | Derive the shell from **one source of truth** (breakpoint hook for pane count/drawer mode; **container queries** for reusable panes); transition across breakpoints **without reload** and without orphaned/duplicated state; content reflows fluidly rather than snapping to fixed px. | ✅ PRD §4.1/§5.3 single-source shell; container-query panes (Baseline-safe). | PRD 03 §4.1/§5.3 [repo]; MDN container queries |
| D9 | **Mouse-precision affordances** | A precise pointer tolerates **denser** targets (WCAG 2.5.8 floor = 24×24 CSS px) than touch — but **gate the larger touch floor on `@media (hover:none)`** so desktop density stays byte-for-byte unchanged; use hover-revealed row actions/affordances that a coarse pointer can't rely on only as enhancements. | ✅ `buttonVariants` appends `[@media(hover:none)]:size-11 / min-h-11`; desktop keeps dense sizes (ST5 H7 invariant). | W3C WCAG 2.2 — 2.5.8 (24px floor); ST5 §(d) H7 [S6][repo] |
| D10 | **Tooltips** | Keep tags **brief, action-oriented, < ~75 chars**, sentence case; **don't name the element**; never the **sole** carrier of essential info; content shown on hover/focus must be **dismissable, hoverable, and persistent** (WCAG 1.4.13) and reachable by keyboard focus, not hover only. | ✅ `ui/tooltip.tsx` present (desktop-hover); ◑ confirm keyboard-focus trigger + 1.4.13 dismiss behavior + concise copy. | Apple HIG help tags (<75 chars, don't name element); WCAG 1.4.13 Content on Hover or Focus [S1][S6] |

### 2.2 Mobile findings

| # | Surface | Best-practice guidance | Repo status | Source |
| --- | --- | --- | --- | --- |
| M1 | **44px touch targets & hit-slop** | **iOS 44pt / Android 48dp** minimum; **≥8px spacing** between targets; WCAG 2.5.8's 24px is the **floor, not the target**. Expand the *hit region* (padding / invisible pseudo-target) without visually resizing; **watch overlap** — 44px slop on two controls 4px apart steals taps, so widen spacing too. | ✅ `buttonVariants` touch floor + `Checkbox`/`Switch` `::before` hit-slop (ST-7); dense-cluster spacing tracked (ST5 R1). | Apple HIG (44pt); Material 3 / Android (48dp, 8dp spacing, `minimumInteractiveComponentSize`); WCAG 2.5.8 [S1][S10][S6] |
| M2 | **Thumb reachability / one-handed** | Put primary actions in the **thumb zone** (bottom third, bottom-right favored for right-handers; ~49% browse one-handed); avoid top-corner primary actions on tall phones. | ✅ Composer + Send pinned bottom; hamburger top-left is the reachable-alternative pattern. | PRD 03 §5.3 [repo]; Material 3 layout |
| M3 | **Bottom sheets vs dialogs** | Prefer a **bottom sheet** for contextual choices / supporting content on mobile (reachable, less modal); reserve **dialogs** for interruptive decisions requiring acknowledgement; on compact width, render supporting-pane content as a bottom sheet. | ✅ Mobile dialogs render as bottom sheets (`rounded-t-3xl` in `ui/dialog.tsx`), command palette sheet, `ui/drawer.tsx`. | Material 3 (bottom sheets; supporting content → bottom sheet at compact width) [S10][S9] |
| M4 | **Safe-area insets (notch / home indicator)** | `viewport-fit=cover` is **required** for `env(safe-area-inset-*)` to be non-zero; apply **all four** insets (top/bottom/left/right) so content clears the notch/Dynamic Island, home indicator, and **landscape L/R** insets — not bottom only. | ✅ `viewportFit: "cover"` + all four insets across header/composer/dialogs/drawer/toasts/coachmark. | PRD 03 §4.3 [repo]; MDN `env()` / WebKit safe-area |
| M5 | **Keyboard avoidance via `visualViewport`** | On iOS the software keyboard resizes only the **visual** viewport, so `dvh`/`svh`/`lvh` **do not shrink** and a `dvh`-only bottom composer gets covered — make **`visualViewport` JS the primary** iOS mechanism (track `resize`/`scroll`, coalesce per rAF). The Virtual Keyboard API remains **absent from WebKit** (2026), so `visualViewport` is the only iOS option. | ✅ `lib/use-visual-viewport.ts` (rAF-coalesced, pinch-zoom epsilon, 50px noise floor) drives the composer inset. | MDN `VisualViewport`; PRD 03 §4.3; 2026-05-27 review Theme A [S11][repo] |
| M6 | **16px input-zoom floor (iOS)** | Any focused `<input>`/`<select>`/`<textarea>` **< 16px** triggers iOS Safari auto-zoom; keep form controls **≥16px on mobile** (`font-size: max(16px, 1em)` or `text-base md:text-sm`). **Do not** use `user-scalable=no`/`maximum-scale=1` to suppress it (accessibility regression). | ✅ All text inputs ≥16px; 3 stray `<select>`s ramped `text-base md:text-sm` (ST-8, gate H1/H2). | CSS-Tricks / danburzo / Stack Overflow (16px floor) [S12][S13] |
| M7 | **Haptics (feature-detected, no-op iOS)** | Use the **Vibration API on Android** (feature-detect `navigator.vibrate`, short ≤20ms buzzes, honor reduced-motion/system settings); treat **web haptics on iOS as unreliable** (the old checkbox-`switch` label-`click()` shim appears patched out) → **degrade silently to visual feedback**. | ✅ `lib/use-haptic.ts` feature-detects `navigator.vibrate`, try/catch, no-op on iOS/desktop; call sites per ST-9. | 2026-05-27 review Finding 1 / Theme B; MDN Vibration API; `ios-haptics` [repo][S14] |
| M8 | **PWA install & manifest shortcuts** | Android: defer `beforeinstallprompt` to a **contextual** moment (not first load). iOS: **no auto-prompt** → a dismissible **Add-to-Home-Screen coachmark**. Ship a **web app manifest** (`standalone`, icons incl. maskable, theme/bg) and **`shortcuts`** for OS jump-lists (in-scope deep links, no new assets needed). | ✅ `manifest.ts` (standalone, maskable icon, 3 `shortcuts` → `?action=`), `install-coachmark.tsx`, SW registration. | web.dev PWA / Add-to-home-screen; PRD 03 §4.9; MDN manifest `shortcuts` [S15][repo] |
| M9 | **Offline behavior** | Optimistic send + **IndexedDB** (drafts, unsent-actions queue) + retry w/ backoff; **server stays source of truth**; request `navigator.storage.persist()` (more likely granted for installed PWAs) — iOS quota is **disk-proportional (tens of GB)**, the real limit is **7-day ITP eviction** of non-persisted data (installed web apps have their own use-counter and fare better). | ✅ `lib/offline-store.ts`, optimistic send, resumable-stream replay (`lib/stream-client.ts`) with Continue/Regenerate fallback. | web.dev offline; PRD 03 §4.6; WebKit storage policy [S15][S16][repo] |
| M10 | **Pull-to-refresh & overscroll containment** | Native pull-to-refresh **reloads the page and kills an in-flight stream** + optimistic/queue state — so **drop PTR** on the conversation and set **`overscroll-behavior: contain`** on the message list/app root to block PTR + scroll-chaining. | ✅ `overscroll-contain` applied across scroll regions + `globals.css`; PTR dropped (PRD §4.4). | MDN `overscroll-behavior`; PRD 03 §4.4 [S17][repo] |
| M11 | **Orientation / landscape** | Handle **landscape L/R safe-area insets** (notch on the side); ensure focused fields aren't trapped under the keyboard in **short/landscape** viewports (internal scroll container as a fallback); layout adapts on rotate without reload. | ◑ Landscape L/R insets applied; auth/share internal scroll shells flagged low-risk (ST-8 R6). | PRD 03 §5.1; MDN `env()`; ST-8 [repo] |
| M12 | **iOS Safari specifics (ITP + address-bar resize)** | **ITP blocks third-party cookies with no exceptions** — the BE cookie must be **first-party**, so proxy `/api/*` **same-origin** (Next rewrite → Fly) rather than calling `fly.dev` cross-origin (symptom of breakage: 201 create then 404 messages as each request mints a fresh anon user). Address-bar show/hide resizes the viewport → use `dvh` for the shell + `visualViewport` for the keyboard. | ✅ `web/next.config.ts` same-origin `/api/*` rewrite; `dvh` shell + visualViewport (M5). | WebKit *Tracking Prevention* (3rd-party cookies blocked); PRD 03 iOS-cookie note [S18][repo] |
| M13 | **Android vs iOS differences** | Two-track everything: **`interactive-widget=resizes-content`** (Chromium 108+ **and Firefox 132+**, **no-op on iOS**) resizes the layout viewport on Android; **`visualViewport`** is the iOS keyboard path. **Background Sync** = Android only (replay on `online`/foreground on iOS); **web push** install-gated on iOS (16.4+, home-screen). | ✅ `interactiveWidget: "resizes-content"` + `visualViewport` both present; offline replay on foreground. | Chrome for Developers viewport-resize; 2026-05-27 review Themes A/B [S19][repo] |

### 2.3 Cross-platform seams (for both downstream docs)

- **Gesture/accelerator ↔ visible-control parity is the unifying rule.** WCAG
  2.5.7 (drag → single-pointer), the mobile "every gesture has a tappable
  alternative" (PRD §4.4/§4.8), and the desktop "right-click/shortcut is an
  accelerator, never the only path" (D1/D4) are the same principle on two
  platforms. Both docs should state it once and cross-reference.
- **Density is the platform dial.** One mobile-first type/target ramp that
  *densifies* on desktop via `md:`/`@media (hover:none)` (D7/D9, M1) keeps a
  single codebase honest — the load-bearing invariant is "desktop unchanged when
  a rule is added" (ST5 H7).
- **Focus vs touch target are different floors, not the same number:** 24px CSS
  (WCAG 2.5.8 desktop floor) vs 44/48px (touch) vs the 2px-perimeter/3:1 **focus
  indicator** (2.4.13). Don't conflate.

### 2.4 Open questions (empirical / verification, not desk-closeable)

1. **D2** — does the palette expose a **visible trigger** and **return focus to
   the opener** on close, and are destructive palette rows confirm-gated? (Audit.)
2. **D3/D10** — does `--focus-ring` meet 2.4.13 (area + 3:1) and are tooltips
   keyboard-focus-triggerable + 1.4.13-dismissable? (Audit.)
3. **D4/D5** — is a desktop right-click menu and/or DnD (with a 2.5.7 single-pointer
   alternative) in scope pre-attachments, or deferred to the attachments/Capacitor era?
4. **M5** — real-device iOS lab across iPhone/iOS versions (composer never covered
   regardless of length; tapping composer never yanks scroll) — PRD §9 #2, still required.

---

## 3. Sources (accessed 2026-07-05)

**Apple HIG**
- [S1] Human Interface Guidelines — Keyboards (Command primary, respect standard shortcuts, Full Keyboard Access) — https://developer.apple.com/design/human-interface-guidelines/keyboards ; help-tag/tooltip guidance (mirrored) — https://developer.apple.com/documentation/uikit/uitooltipinteractiondelegate/tooltipinteraction(_:configurationat:)
- [S2] Modernize your AppKit app — WWDC26 (key-view loop, gesture recognizers, keyboard navigation) — https://developer.apple.com/videos/play/wwdc2026/289/

**Command palette / interaction patterns**
- [S3] Command palette UX Pattern — UX Patterns Guide — https://uxpatternsguide.com/patterns/command-palette/
- [S4] Command Palette Pattern — UX Patterns for Developers — https://uxpatterns.dev/patterns/advanced/command-palette
- [S5] cmdk in React — Practical Guide (⌘K, focus management) — https://chemikam.pl/cmdk-in-react-practical-guide-to-building-a-fast-command-palette-k

**W3C WCAG 2.2**
- [S6] What's New in WCAG 2.2 (2.4.11 / 2.4.13 / 2.5.7 / 2.5.8 / 1.4.13) — https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- [S7] Understanding SC 2.4.13 Focus Appearance — https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance
- [S8] Understanding SC 2.5.7 Dragging Movements — https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements

**Material Design 3 / Android adaptive**
- [S9] Canonical layouts (list-detail, supporting pane, 70/30, size classes, compact→bottom sheet) — https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts
- [S10] Touch target size (48dp, 8dp spacing) — https://support.google.com/accessibility/android/answer/7101858 ; `minimumInteractiveComponentSize` — https://developer.android.com/reference/kotlin/androidx/compose/material3/minimumInteractiveComponentSize.modifier

**MDN**
- [S11] VisualViewport API — https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport
- [S13] `font-size: max(16px, 1em)` to prevent iOS input zoom (Dan Burzo) — https://danburzo.ro/css-safari-zoom-inputs/
- [S17] `overscroll-behavior` — https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior

**web.dev / PWA**
- [S15] Progressive Web Apps (install, offline, manifest) — https://web.dev/explore/progressive-web-apps ; MDN manifest `shortcuts` — https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/shortcuts

**iOS input zoom / haptics**
- [S12] 16px or Larger Text Prevents iOS Form Zoom — CSS-Tricks — https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/
- [S14] ios-haptics (community; iOS shim reliability) — https://github.com/tijnjh/ios-haptics ; navigator.vibrate on iOS (mdn browser-compat #29166) — https://github.com/mdn/browser-compat-data/issues/29166

**WebKit / ITP / storage**
- [S16] Updates to Storage Policy (disk-proportional quota, 7-day eviction) — https://webkit.org/blog/14403/updates-to-storage-policy/
- [S18] Tracking Prevention in WebKit (third-party cookies blocked; first-party requirement) — https://webkit.org/tracking-prevention/

**Chrome for Developers**
- [S19] Prepare for viewport resize behavior changes (`interactive-widget`, Chromium+Firefox, iOS no-op) — https://developer.chrome.com/blog/viewport-resize-behavior

**In-repo ground truth**
- PRD 03 — `docs/prd/03-mobile-cross-platform.md`; ST1–ST5 audits — `docs/mobile-ux/`; 2026-05-27 review — `docs/research/2026-05-27/03-mobile-cross-platform.md`; `web/next.config.ts`; `web/src/app/manifest.ts`; `web/src/app/layout.tsx`; `web/src/lib/{use-visual-viewport,use-haptic,shortcut-defaults}.ts`; `web/src/components/chat/{command-palette,compare-view,chat-thread}.tsx`.
