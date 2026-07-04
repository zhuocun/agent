# ST4 — Native-feel gap audit (PWA)

Read-only audit of what still separates this PWA from a native feel, scoped to the
six areas in the ST4 brief. Every finding carries `file:line` evidence and a
one-line fix sketch. Items already handled are marked **✅ HANDLED** so nobody
re-does them.

The baseline (already present and confirmed in-tree): safe areas on
header/composer, the `haptic()` shim, visual-viewport keyboard handling,
edge-swipe drawer, Android back, swipe-to-delete, viewport meta
(`viewportFit: "cover"`), paired light/dark `theme-color`, manifest + service
worker, iOS install coachmark, `overscroll-behavior: none` on `html/body`,
`-webkit-tap-highlight-color: transparent`, and reduced-motion gating.

**iOS caveat that colors every haptic finding:** web `navigator.vibrate` is
unreliable/absent on iOS Safari (see `docs/prd/03-mobile-cross-platform.md:106`).
The `haptic()` shim already no-ops safely on iOS (`use-haptic.ts:24-25`), so every
haptic recommendation below is a **feature-detected Android/Chromium win** that
degrades silently on iOS — cheap to add, zero risk.

---

## Priority summary

| # | Gap | Priority | Primary file(s) |
| - | --- | -------- | --------------- |
| G1 | Copy / feedback / model-select / toggle / tab commits fire no haptic | **High** | `message-actions.tsx`, `switch.tsx`, `settings-dialog.tsx`, `model-mode-picker.tsx` |
| G2 | Bottom-sheet dialogs lack left/right (landscape) safe-area padding | **Med** | `dialog.tsx:122`, `command-palette.tsx:525` |
| G3 | Command-palette sheet lacks bottom safe-area padding | **Med** | `command-palette.tsx:525` |
| G4 | Manifest has no `shortcuts` (long-press jump list) | **Med** | `app/manifest.ts` |
| G5 | Nested dialog/menu scrollers lack `overscroll-contain` | **Med** | `activity-dialog.tsx`, `template-library-dialog.tsx`, `shortcuts-dialog.tsx`, `model-directory-dialog.tsx`, `memory-dialog.tsx`, `tier-picker.tsx`, `dropdown-menu.tsx` |
| G6 | Bespoke `<button>`s (not `ui/button`) have no pressed/active state | **Low** | `install-coachmark.tsx`, `settings-dialog.tsx`, `compare-view.tsx`, `dialog.tsx`, `drawer.tsx` |
| G7 | Code block / table horizontal scroll can chain to browser back-swipe | **Low** | `globals.css:784-790` |
| G8 | Manifest has no `screenshots` (richer install UI) | **Low** | `app/manifest.ts` |
| G9 | Drawer open via header tap + drawer close fire no haptic | **Low** | `app-shell.tsx`, `app-header.tsx` |
| G10 | Install coachmark uses fixed `inset-x-3`, not landscape safe insets | **Low** | `install-coachmark.tsx:106` |

---

## 1. Haptic coverage

### ✅ HANDLED
- **Send** — `composer.tsx:712` `haptic("selection")` on submit.
- **Swipe-to-delete commit** — `use-swipe-actions.ts:243` `haptic("impact")` on full-swipe; `:254` `haptic("selection")` on settle-open.
- **Edge-swipe drawer open** — `app-shell.tsx:39` `haptic("selection")` when the edge gesture commits.
- **Sheet swipe-to-dismiss** — `use-swipe-dismiss.ts:144` `haptic("light")` on dismiss.
- **Pull-to-refresh** — intentionally **not** a gesture; blocked by `overscroll-behavior: none` (`globals.css:528`) and dropped in `docs/prd/00-product-overview.md:80`. No haptic needed. **N/A by design.**

Only three modules import `haptic` (`composer.tsx`, `app-shell.tsx`, and the two
swipe hooks) — confirmed by grep. Every commit below therefore has **no** haptic.

### GAPS

- **G1a — Message copy (High).** `message-actions.tsx:119-143` `handleCopy` marks
  `copied` state but never buzzes. Copy is the single most-tapped inline action.
  - *Fix:* call `haptic("selection")` inside `markCopied()` (`message-actions.tsx:120`).

- **G1b — Feedback thumbs up/down (High).** `message-actions.tsx:319` and `:332`
  `onCheckedChange` toggle rating with no haptic.
  - *Fix:* `haptic("selection")` in each `onFeedback` handler.

- **G1c — Toggle switches (High).** `ui/switch.tsx` renders `SwitchPrimitive.Root`
  with zero haptic. It backs every settings toggle plus composer chips
  (search/json/deep-research toggles routed through `model-mode-picker.tsx:361-367`).
  - *Fix:* wrap `onCheckedChange` in `switch.tsx` (or add an `onCheckedChange`
    shim) to fire `haptic("selection")` — one edit covers all consumers.

- **G1d — Tab / segment changes (Med).** `settings-dialog.tsx:1133` `selectTab`
  and the compare tablist (`compare-view.tsx:177-185`) commit with no haptic.
  - *Fix:* `haptic("selection")` in `selectTab` and the compare tab `onClick`.

- **G1e — Model / tier / provider select (Med).** Selection handlers in
  `tier-picker.tsx` and `model-mode-picker.tsx` (`onSelectTier`,
  `onSelectProvider`, `onSelectEffort`) and the regenerate-with items in
  `message-actions.tsx:469` have no haptic.
  - *Fix:* `haptic("selection")` at each selection commit.

- **G1f — Jump-to-latest tap (Low).** `message-list.tsx:425` `scrollToBottom(true)`
  with no haptic — a nice "landed" confirmation on a discrete action.
  - *Fix:* `haptic("light")` in the `onClick`.

- **G9 — Drawer open-by-tap + close (Low).** Only the *edge-swipe* path buzzes
  (`app-shell.tsx:39`); opening via the header menu button (`app-header.tsx`) and
  every close path (`onMobileNavOpenChange(false)`, Android back at
  `app-shell.tsx:75`) are silent, so open feels inconsistent depending on how you
  triggered it.
  - *Fix:* buzz `haptic("selection")` in the single `onMobileNavOpenChange`
    owner so open/close parity holds regardless of trigger.

---

## 2. Safe-area completeness

### ✅ HANDLED (all four insets where it matters)
- **Header** — `app-header.tsx:97` `pl/pr max(env(safe-area-inset-left/right),…)`.
- **Composer bottom strip** — `chat-thread.tsx:3907` `pr/pl env(...-right/left)` + `pb-[var(--bottom-inset)]` (`--bottom-inset = max(env(safe-area-inset-bottom),1.5rem)`, `globals.css:174`).
- **Top chrome strip** — `chat-thread.tsx:3693` top/right/left insets.
- **Message list** — `chat-thread.tsx:3763,3787` left/right insets.
- **Toast stack** — `toast.tsx:242` bottom + left/right (mobile) and top (md+).
- **Drawer** — `drawer.tsx:90` top/bottom; close button folds in top/right insets `drawer.tsx:112`.
- **Dialog sheet bottom** — `dialog.tsx:122` `pb-[max(env(safe-area-inset-bottom),1rem)]`.
- **Tier / model pickers** — `tier-picker.tsx:143`, `model-mode-picker.tsx:357` bottom inset.
- **Jump-to-latest** — `message-list.tsx:418` right inset.
- **Status / share headers** — `platform-status-view.tsx:70`, `public-conversation-view.tsx:109` top/left/right.

### GAPS

- **G2 — Bottom-sheet dialogs miss left/right insets in landscape (Med).**
  `dialog.tsx:122` is `fixed inset-x-0 … p-6 pb-[max(env(safe-area-inset-bottom),1rem)]`
  — horizontal padding is a flat `p-6`, so on a landscape notched iPhone the
  sheet content (title, close ✕, form rows) sits under the notch / rounded
  corner. Bottom is handled; sides are not.
  - *Fix:* add `pl-[max(env(safe-area-inset-left),1.5rem)] pr-[max(env(safe-area-inset-right),1.5rem)]` to the mobile branch (keep `sm:p-6`).

- **G3 — Command palette sheet misses bottom + side insets (Med).**
  `command-palette.tsx:525` `fixed inset-x-0 bottom-0 … p-0` — no
  `env(safe-area-inset-bottom)` and no left/right, so the results list runs under
  the home indicator (portrait) and the notch (landscape).
  - *Fix:* pad the results container / footer by the bottom inset and add L/R
    insets on the popup, mirroring `dialog.tsx`.

- **G10 — Install coachmark uses fixed `inset-x-3` (Low).**
  `install-coachmark.tsx:106` pins `inset-x-3` (flat 0.75rem) rather than
  `env(safe-area-inset-left/right)`. It's `mx-auto max-w-md`, so on most phones
  it centers clear of the notch, but on a narrow landscape iPhone the pill's edge
  can still tuck under the inset.
  - *Fix:* swap `inset-x-3` for `left-[max(env(safe-area-inset-left),0.75rem)] right-[max(env(safe-area-inset-right),0.75rem)]`.

---

## 3. Inner-scroll polish

### ✅ HANDLED
- **Message list** — `message-list.tsx:353` `overscroll-contain` + `overflow-anchor:auto` (`:352`) so streaming reflow doesn't shove the reader.
- **Page rubber-band / PTR** — `globals.css:528` `overscroll-behavior: none` on `html,body`.
- **Settings body** — `settings-dialog.tsx:1048` `overscroll-contain`.
- **Model-mode-picker body** — `model-mode-picker.tsx:365` `overscroll-contain`.
- **Sheet swipe never steals inner scroll** — `use-swipe-dismiss.ts:160-172` only engages a downward drag when the inner scroller is already at the top.

### GAPS

- **G5 — Nested dialog/menu scrollers lack `overscroll-contain` (Med).** These
  scroll regions can chain to whatever is behind them (backdrop / page):
  `activity-dialog.tsx:169`, `template-library-dialog.tsx:176`,
  `shortcuts-dialog.tsx:315`, `model-directory-dialog.tsx:235`,
  `memory-dialog.tsx:158`, `tier-picker.tsx:150`, `command-palette.tsx:612`.
  The page-level `overscroll-behavior: none` blunts the worst case, but the local
  scroller still rubber-bands its own container edge.
  - *Fix:* add `overscroll-contain` to each `overflow-y-auto` region (same
    pattern already used in `settings-dialog.tsx:1048`).

- **G5b — Dropdown / popover menus (Low).** `dropdown-menu.tsx:44`,
  `template-picker-popover.tsx:124`, `slash-commands-popover.tsx:141` are
  `overflow-y-auto` with no containment; a flick at the list end scrolls the page
  underneath.
  - *Fix:* add `overscroll-contain` to the menu content class.

- **G7 — Horizontal scrollers can trigger browser back-swipe (Low).** Code blocks
  and tables (`globals.css:784-790`) are `overflow-x-auto` with no
  `overscroll-behavior-x: contain`; on iOS/Chromium a horizontal fling at the
  edge can fire the OS back/forward navigation instead of settling.
  - *Fix:* add `overscroll-behavior-x: contain` to `.chat-md :where(pre)` and
    `:where(table)`.

- *Momentum:* `-webkit-overflow-scrolling: touch` is intentionally absent — it's
  the default on modern iOS and now a no-op, so no action. **N/A.**

---

## 4. Manifest richness

`app/manifest.ts` currently ships `id`, name/short_name, description, start_url,
scope, `display: standalone`, `display_override`, `orientation: any`,
colors, categories, and three icons (`manifest.ts:4-42`). Missing:

- **G4 — `shortcuts` (Med).** No app long-press jump list. High-value, zero new
  assets (icons optional).
  - *Fix:* add a `shortcuts` array — e.g. **New chat** (`/?new=1` or the existing
    new-chat route), **Search chats**, **Settings** — each `{ name, short_name, url }`.
    Wire the target URLs to existing client entry points.

- **G8 — `screenshots` (Low).** No `screenshots`, so Android/Chromium shows the
  minimal (not the richer) install UI. Requires producing narrow + wide PNG/WebP
  assets — `web/public/` currently has **no** product screenshots (only framework
  SVGs), so this is an asset-generation cost, not a one-line add.
  - *Fix:* capture 1–2 mobile (`form_factor: "narrow"`) and 1 desktop
    (`form_factor: "wide"`) screenshots into `web/public/`, then add the
    `screenshots` array. Defer unless install-conversion is a priority.

- *Also worth a note:* no `launch_handler` / `handle_links`; defaults are fine for
  a single-scope PWA. **No action.**

---

## 5. Selection/callout, double-tap-zoom, momentum, active states

### ✅ HANDLED
- **Pressed/active on the shared button** — `button.tsx:7`
  `active:not-aria-[haspopup]:scale-[0.96]` + `brightness-[0.92]` + fast
  `active:duration-[70ms]`, with `motion-reduce:active:…:scale-100` guard.
- **Tap-highlight kill** — `globals.css:507` `-webkit-tap-highlight-color: transparent`.
- **Long-press callout** — suppressed on controls (`globals.css:540` `-webkit-touch-callout:none` + `user-select:none`), re-enabled on chat content/code (`globals.css:550-558`).
- **Double-tap-zoom** — `globals.css:536` `touch-action: manipulation` on `button,[role=button],a`.
- **Text auto-inflate on rotate** — `globals.css:520` `text-size-adjust:100%`.
- **Switch hit target** — `switch.tsx:13` `before:` pseudo expands the tap area to 44px even though the visual is 20px.

### GAPS

- **G6 — Bespoke `<button>`s bypass the shared active state (Low).** Raw
  `<button>` elements don't inherit `button.tsx`'s `active:scale`, so they feel
  flat under the thumb: install-coachmark dismiss (`install-coachmark.tsx:135`),
  settings tab buttons (`settings-dialog.tsx:1124`), compare tabs
  (`compare-view.tsx:185`), and the dialog/drawer close ✕
  (`dialog.tsx:147`, `drawer.tsx:112`) — all hover-only.
  - *Fix:* add `active:scale-[0.96] active:duration-[70ms] motion-reduce:active:scale-100`
    to these class lists, or route them through `ui/button`.

- **G6b — Switch has no press feedback (Low).** `switch.tsx` animates the thumb on
  checked-change but has no `active:` scale, so the toggle itself doesn't
  acknowledge the press before the state flips.
  - *Fix:* add a subtle `active:scale-95` on the thumb (reduced-motion guarded).

No selection/callout or double-tap regressions found — the content re-enable in
`globals.css:550-558` correctly scopes selectability to chat text and code only.

---

## 6. Scroll restoration / 100dvh correctness under keyboard (dialogs)

### ✅ HANDLED
- **Main shell** — `app-shell.tsx:50-53` pins height + `translateY` to the visual
  viewport while the keyboard is up (iOS doesn't shrink `dvh`).
- **Dialog bottom sheet** — `dialog.tsx:92-101` lifts by `keyboardInset` and trims
  the same amount off `max-height` (respecting each sheet's `--dialog-max-h`), so
  focused form fields stay above the keyboard.
- **Command palette** — `command-palette.tsx:351-358` lifts + trims `max-height`
  identically.
- **Toast stack** — `toast.tsx:234` lifts above the keyboard on mobile.
- **Sheet heights** — all sheets cap at `80–90dvh` (`dialog.tsx:123`,
  `command-palette.tsx:525`); none use a raw `100vh`, so no full-screen dialog is
  cut off by the URL bar.

### GAPS / NOTES
- **No true full-screen (`100dvh`) dialog exists**, so the ST4 concern ("do
  full-screen dialogs handle 100dvh under keyboard?") is **not currently
  applicable** — every modal is a capped bottom sheet and all three keyboard-aware
  sheets are handled above. If a full-screen sheet is ever added, reuse the
  `useVisualViewport().keyboardInset` lift pattern from `dialog.tsx:92`.
- **Desktop centered dialogs** don't react to the keyboard (`dialog.tsx` only
  applies the lift when `isMobile`), which is correct — desktop has no soft
  keyboard overlaying content. **No action.**
- **Scroll restoration:** SPA navigation, no multi-document history; nothing relies
  on `history.scrollRestoration`. **No action.**

---

## Recommended sequencing

1. **G1c + G1a/G1b (High, tiny):** one edit in `switch.tsx` plus two in
   `message-actions.tsx` covers the highest-frequency commits (toggles, copy,
   feedback) — biggest perceived-nativeness gain per line, Android-only, silent
   on iOS.
2. **G1d/G1e/G9/G1f (High→Low):** finish haptic parity across tabs, model select,
   drawer, jump-to-latest.
3. **G2 + G3 (Med):** landscape/bottom safe-area padding on the dialog and command
   palette — pure class additions, no logic.
4. **G4 (Med):** manifest `shortcuts` — no new assets, real long-press value.
5. **G5/G5b/G7 (Med→Low):** sprinkle `overscroll-contain` / `overscroll-behavior-x`
   on nested scrollers.
6. **G6/G6b (Low):** pressed states on bespoke buttons + the switch.
7. **G8 (Low, deferrable):** manifest `screenshots` once screenshot assets exist.
