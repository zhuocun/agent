# ST2 — Mobile tap-target audit (iOS HIG 44×44pt)

**Scope:** every interactive element under `web/src/components/**` — `<button>`,
`Button`, `[role="button"]`, `[role="tab"]`, `[role="option"]`, icon-only
controls, dropdown/menu items, `Checkbox`/`Switch`, and dialog/drawer close (X)
buttons.

**Why:** Apple's HIG puts the comfortable minimum touch target at **44×44pt**.
On the web that is 44 CSS px, since 1pt ≈ 1px at the default scale. A control can
clear the floor two ways: (a) be ≥44px in both dimensions, or (b) keep a small
*visual* size but expand its *hit region* to 44px with hit-slop
(negative-margin padding, or a `::before` overlay). The second matters because a
44px target that would bloat desktop density can instead grow only on touch.

**Method:** static read of the class strings on every control (read-only; no code
changed). "Mobile size" is the value that applies with **no** `md:` prefix
active (the `md` breakpoint is 768px, i.e. all phones). Size reference (Tailwind
v4 defaults): `size-4`=16px, `size-6`=24px, `size-7`=28px, `size-8`=32px,
`size-9`=36px, `size-11`=44px; `h-6`=24, `h-7`=28, `h-8`=32, `h-9`=36, `h-10`=40,
`h-11`=44; `min-h-9`=36, `min-h-11`=44.

**Reference-compliant baselines (per the task brief):** the composer circular
controls are `size-11` (44px) — `composer.tsx:136` `BUTTON_BASE`, and the
attach/camera/templates/dictate/more/remove buttons at 840, 857, 880, 911, 947,
1151, 1177, 1312 — and the header float buttons/pills are `size-[45px]` /
`h-[45px]` (`app-header.tsx:63,77`). Both already exceed 44px; the rest of the
surface is measured against them.

---

## Findings — controls below 44px on mobile with no adequate hit-slop

| # | File | Line(s) | Control | Mobile size | ≥44px? | Notes |
| - | ---- | ------- | ------- | ----------- | ------ | ----- |
| 1 | `web/src/components/ui/checkbox.tsx` | 16 | `Checkbox` primitive (`size-4`) | **16×16px** | ❌ | Shared primitive; no hit-slop. Rendered in the sidebar multi-select at `sidebar.tsx:545` inside a `pl-3` span — the 44px lives on the row, not the box, so the tickable region is ~16px. |
| 2 | `web/src/components/chat/compare-view.tsx` | 192 | Mobile compare tab strip (`role="tab"`, `min-h-9`) | **36px tall** | ❌ | Mobile-only (`md:hidden`), `flex-1` tabs sit **edge-to-edge** with `gap-2` — a **dense cluster**: even at 44px they'd need the existing gap to avoid mis-taps. |
| 3 | `web/src/components/chat/memory-dialog.tsx` | 281, 292 | Edit / Delete icon buttons (`size="icon"` → `size-8`) | **32×32px** | ❌ | Adjacent pair in a `gap-1` (4px) cluster → **collision risk**; needs spacing *and* size. Sheet-facing (renders as a bottom sheet on mobile). |
| 4 | `web/src/components/chat/template-library-dialog.tsx` | 332, 343 | Edit / Delete icon buttons (`size="icon"` → `size-8`) | **32×32px** | ❌ | Same dense `gap-1` Edit+Delete pair as memory-dialog. |
| 5 | `web/src/components/chat/shortcuts-dialog.tsx` | 196 | Reset-to-default icon button (`size="icon-xs"` → `size-6`) | **24×24px** | ❌ | Smallest offender. Sits `gap-1.5` from the rebind control — dense two-control row. |
| 6 | `web/src/components/chat/byok-form.tsx` | 211, 321, 331, 344, 356, 380, 390 | Text action buttons (`size="sm"` → `h-7`, no `min-h` override) | **28px tall** | ❌ | Mounted inside Settings (`settings-dialog.tsx`), which is a bottom sheet on mobile. Save/Remove/Cancel/Replace all short. |
| 7 | `web/src/components/chat/settings-dialog.tsx` | 423, 502, 775, 1235, 1246, 1259, 1272, 1296, 1556, 1571 | Text action buttons (`size="sm"` → `h-7`, no `min-h`) | **28px tall** | ❌ | Budget/conversation-cap Save, billing (Upgrade/Buy credits/Manage/Sign in/Sign out), and footer actions. |
| 8 | `web/src/components/chat/settings-dialog.tsx` | 344, 606, 640 | Segmented retention / project-model / project-retention toggles (`px-3 py-1.5 text-xs`) | **~29px tall** | ❌ | **Dense segmented clusters** (`grid grid-cols-3` / `flex-wrap` inside a `p-0.5` pill) — segments abut, so 44px alone would collide; needs the pill geometry rethought, not just taller segments. |
| 9 | `web/src/components/chat/activity-dialog.tsx` | 224, 272 | "Change your model route" / "Load more" (`size="sm"` → `h-7`) | **28px tall** | ❌ | Sheet-facing dialog. |
| 10 | `web/src/components/chat/spend-analytics-panel.tsx` | 286, 304 | Export CSV / Export JSON buttons (`size="sm"` → `h-7`) | **28px tall** | ❌ | `flex-wrap gap-2` row — spacing is fine; height is short. |
| 11 | `web/src/components/chat/memory-dialog.tsx` · `template-library-dialog.tsx` | 247, 256 · 287, 296 | Inline edit **Save / Cancel** (`size="sm"` → `h-7`) | **28px tall** | ❌ | `justify-end gap-2` pair; height short. |
| 12 | `web/src/components/share/public-conversation-view.tsx` | 301, 311 | Error-state "Try again" / "Start your own chat" (`h-10`) | **40px tall** | ⚠️ | 4px short of 44. Full-page centered empty state → **low collision risk**; borderline. |

**Dense-cluster flags (spacing, not just size):** rows **2, 3, 4, 5, 8**.
Growing these to 44px without also guaranteeing ≥8px separation (or bounded,
non-overlapping hit-slop) would make neighbouring targets steal each other's
taps — the Edit/Delete `gap-1` pairs and the abutting segmented toggles are the
worst offenders.

---

## Compliant controls (already ≥44px on mobile, or adequate hit-slop) — verified

The surface is broadly hardened; the offenders above are the exceptions that
slipped through. The established, repo-wide idioms are worth calling out because
the recommended fix generalises them:

**A. Touch-only min-height on labelled rows/buttons — `min-h-11 md:min-h-0`:**

- `message-actions.tsx:283,550` — overflow + IconAction buttons (`size-11 md:size-9`).
- `follow-up-chips.tsx:75`; `tool-part.tsx:169,180` (Approve/Deny); `assistant-message.tsx:683,704,738` (Retry / Check status / Request review); `welcome-screen.tsx:120`.
- `command-palette.tsx:862,902` (result rows), `553,604` (icons `size-11 md:size-7`).
- `template-picker-popover.tsx:149`, `slash-commands-popover.tsx:167`, `model-mode-picker.tsx:430,687,739`, `tier-picker.tsx:161`.

**B. Vertical hit-slop on inline disclosure triggers — `py-3.5 -my-3.5` / `py-2 -my-2` (`md:` cancels it):**

- `reasoning-panel.tsx:67`, `sources-panel.tsx:127`, `subagent-panel.tsx:118,452`, `tool-group-panel.tsx:54`, `web-search-panel.tsx:199`.

**C. `::before` overlay hit-slop (visual stays small, hit region = 44px):**

- `switch.tsx:13` — `before:h-11 before:w-11` centered pseudo-target on a 20×16px switch. **This is the model fix for `Checkbox` (row 1), which lacks it.**

**D. Menu items get a touch floor automatically — `[@media(hover:none)]:min-h-11`:**

- `dropdown-menu.tsx:91,116,162,204` — `Item`, `SubTrigger`, `CheckboxItem`, `RadioItem`. Every `DropdownMenuItem`/`…CheckboxItem` (message-actions overflow, app-header chat menu, tier-picker & model-mode-picker desktop rows, theme-toggle) inherits 44px on touch while staying dense on desktop.

**E. Fixed 44px targets:**

- Dialog close `dialog.tsx:149` (`size-11`); Drawer close `drawer.tsx:112` (`size-11`); Toast dismiss `toast.tsx:208` (`size-11`); composer attachment remove `composer.tsx:1151,1177` (`size-11 md:size-7`); `install-coachmark.tsx:140`, `theme-toggle.tsx:37`, `auth-dialog.tsx:217,237` (`size-11` / `h-11`); banners `temporary-chat-banner.tsx:35,49` & `degraded-status-banner.tsx:71,86,96` (`h-11` / `size-11`, overriding their `size="xs"`); `public-conversation-view.tsx:134` (`h-11 sm:h-9`).

**No interactive elements (nothing to audit):** `attribution-row.tsx` and
`public-attribution-row.tsx` render only `<span>`s (the `Info`/`Key` glyphs are
decorative); `usage-meter.tsx`, `typing-indicator.tsx`, `live-region.tsx`,
`ai-disclosure.tsx`, `key-caps.tsx`, `badge.tsx` are display-only.

---

## Recommended approach

Two complementary changes; neither adds a single pixel to desktop density
because both are gated on `@media (hover: none)` (touch) — the same gate the repo
already uses in `dropdown-menu.tsx`.

### 1. Bake a touch floor into `buttonVariants` (fixes rows 3–7, 9–11 at once)

In `web/src/components/ui/button.tsx`, add a touch-only minimum to the small
sizes so *any* `size="sm|xs|icon|icon-sm|icon-xs"` clears 44px on phones without
each caller re-adding `min-h-11 md:min-h-0`:

- icon sizes (`icon`, `icon-sm`, `icon-xs`): append `[@media(hover:none)]:size-11`.
- text sizes (`default`, `sm`, `xs`, `lg`): append `[@media(hover:none)]:min-h-11`.

This is the single highest-leverage fix: it auto-repairs the icon buttons in
`memory-dialog`/`template-library-dialog` (rows 3–4), the `icon-xs` reset (row
5), and every stray `size="sm"` in `byok-form`, `settings-dialog`,
`activity-dialog`, `spend-analytics-panel`, and the inline edit Save/Cancel
(rows 6–7, 9–11). It also makes the many already-hardened call sites redundant
(they keep working; the explicit `min-h-11 md:min-h-0` becomes belt-and-braces).
Desktop is untouched because `hover:none` never matches a mouse.

> Verify twMerge ordering when a caller passes its own `size-*`/`h-*` in
> `className` (e.g. `composer.tsx:1151` `size-11 md:size-7`): a caller override
> should still win. Keep the variant token first so the class-merge resolves to
> the caller's value where present.

### 2. Hit-slop (not resize) for the shared `Checkbox` and dense clusters (fixes rows 1, 2, 8)

Pure min-size is wrong where the control must stay visually small or where
neighbours abut:

- **`Checkbox` (row 1):** copy the `Switch` pattern — add a centered
  `before:absolute before:size-11 before:-translate-x-1/2 before:-translate-y-1/2`
  pseudo-target (touch-gated) so the 16px box keeps its look but taps land inside
  44px. Preferable to enlarging the box, which would disrupt the sidebar row.
- **Compare tabs (row 2):** bump `min-h-9` → `min-h-11` on the mobile-only strip
  (`md:hidden`, so zero desktop cost); the existing `gap-2` already separates
  them.
- **Segmented toggles (row 8) & Edit/Delete pairs (rows 3–4):** size alone
  collides. Either widen separation to `gap-2` (≥8px) **or** keep small visuals
  with **bounded** hit-slop that can't overlap a neighbour. A naïve 44px
  `::before` on two controls 4px apart would make their hit regions overlap and
  steal taps — so for these, **spacing is part of the fix, not optional**.

### Net effect

Change (1) is one edit to a shared variant and clears the majority of the table;
change (2) is targeted hit-slop/spacing for the handful of small-by-design or
abutting controls. Because every added rule is `@media (hover: none)`-gated,
desktop density is byte-for-byte unchanged.
