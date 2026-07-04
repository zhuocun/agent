# ST5 — Mobile-UX Phase B spec (single source of truth)

Synthesis of the four read-only audits (ST1 type, ST2 touch, ST3 input, ST4
native-gap) into an executable plan. This doc **resolves overlaps**, **locks the
mobile-first type ramp** as concrete `globals.css` utilities, **partitions every
fix into the ST-6/7/8/9 implementation buckets with exact file lists**, **marks
the High-priority items the final gate must verify**, and **flags the risky /
uncertain calls for orchestrator decision**.

No code is changed by this doc. Everything downstream of Phase B references it.

Source audits: `ST1-type-audit.md`, `ST2-touch-audit.md`, `ST3-input-audit.md`,
`ST4-native-gap-audit.md`.

---

## 0. Bucket map

Four implementation streams, one per audit surface. Each bucket owns a **single
class of change** so a file touched by several buckets still has an unambiguous
owner per property.

| Bucket | Charter | Owning audit | Mechanism |
| --- | --- | --- | --- |
| **ST-6** | Mobile-first **type ramp** — every non-input font-size rides "bigger on phone, denser on desktop" | ST1 | New `@layer components` utilities in `globals.css` + apply at call sites |
| **ST-7** | **Touch targets** — every interactive control clears 44×44 on touch, dense clusters de-collided | ST2 | Touch-gated floor in `buttonVariants` + `Checkbox` hit-slop + targeted spacing |
| **ST-8** | **Input zoom + keyboard scroll** — every field ≥16px on mobile; no focused field trapped under the keyboard | ST3 | `text-base md:text-sm` on the 3 stray `<select>`s + scroll-container shells |
| **ST-9** | **Native-feel gaps** — haptics, safe-area, overscroll, manifest, pressed states | ST4 | Feature-detected / touch-gated class + small handler additions |

**Cross-cutting invariant (all buckets):** every rule added is **mobile / touch /
`@media (hover:none)`-gated or `md:`-ramped** so **desktop density is
byte-for-byte unchanged**. This is a hard acceptance criterion, not a nicety.

Bucket naming is consistent with the existing `web/tests/e2e/ui-primitives.spec.ts`
header ("UI primitives … per ST-7").

---

## (a) Overlap resolution — one owner per fix

Several controls surface in more than one audit. The rule below assigns exactly
one owner per **fix**, splitting a control into distinct fixes only when the
properties are genuinely independent (font-size vs. geometry).

**Ownership rule:**

1. **Font-size / type ramp → ST-6** — *except* a control whose *single* class
   edit simultaneously satisfies another bucket's floor (see rule 3).
2. **Touch geometry** (min-height, `size-*`, hit-slop, inter-control spacing) **→
   ST-7**.
3. **`<select>` zoom floor → ST-8 exclusively.** A `<select>` at `text-sm` is
   flagged by *both* ST1 (interactive <15px) and ST3 (zoom <16px). One edit —
   `text-sm` → `text-base md:text-sm` — fixes both, so ST-8 owns it and ST-6's
   sweep **skips all `<select>`s**. No double edit.
4. **Haptics / safe-area / overscroll / active-state → ST-9**, even on controls
   ST-6/ST-7 also touch (different property, no conflict).

### Resolved overlaps

| Control(s) | Flagged by | Resolution | Owner(s) |
| --- | --- | --- | --- |
| `<select>` — `byok-form.tsx:248`, `settings-dialog.tsx:576`, `command-palette.tsx:92` (`FILTER_SELECT_CLASS`, used at 623/644/726) | ST1 (interactive <15) + ST3 (zoom <16) | Single `text-base md:text-sm` edit clears both floors → **ST-8 only**; excluded from ST-6 | **ST-8** |
| Settings segmented toggles — `settings-dialog.tsx:344,606,640` | ST1 (`text-xs` interactive) + ST2 (dense abutting cluster) | Two independent fixes: font ramp → **ST-6**; segment geometry + spacing → **ST-7** | ST-6 (font) + ST-7 (geometry) |
| `ui/button.tsx` `buttonVariants` — base label `text-sm`, `xs`=`text-xs`, `sm`=`text-[0.8rem]` (L7/25/26) | ST1 (label <15) + ST2 (touch floor) | Two independent properties in one cva: font tokens → **ST-6**; `[@media(hover:none)]` min-h/size floor → **ST-7** | ST-6 (font) + ST-7 (touch) |
| `size="sm"` / `size="icon*"` text/icon buttons across `byok-form`, `settings-dialog`, `activity-dialog`, `spend-analytics-panel`, `memory-dialog`, `template-library-dialog`, `shortcuts-dialog` | ST2 (short height) — label size inherited from button variant | Label size is fixed once by ST-6's `button.tsx` font edit (cascades); height/hit region is **ST-7**. **No per-call type edit.** | **ST-7** (touch only) |
| `Checkbox` primitive `ui/checkbox.tsx:16` (`size-4`) | ST2 (16px target) | Hit-slop `::before`, not resize → **ST-7** (display-only for type, so ST-6 N/A) | **ST-7** |
| `settings-dialog.tsx:1052` nav eyebrow — `text-2xs md:text-xs` (inverted ramp) | ST1 (caption <13 **and inverted**) | Re-map to `.ui-eyebrow` (13→11) which un-inverts → **ST-6** | **ST-6** |
| Dialog / command-palette sheets — description body (`dialog.tsx:204`, `drawer.tsx:169`) vs. safe-area padding (`dialog.tsx:122`, `command-palette.tsx:525`) | ST1 (body <15) + ST4 (safe-area, overscroll) | Description font → **ST-6**; safe-area/overscroll/active → **ST-9** | ST-6 (font) + ST-9 (chrome) |
| `ui/switch.tsx` | ST2 (already compliant, model hit-slop) + ST4 (no haptic, no active) | No touch work needed; haptic + `active:` → **ST-9** | **ST-9** |
| `auth-dialog.tsx` / `share-dialog.tsx` — labels/body (font) vs. missing internal scroll container | ST1 (body <15) + ST3 (keyboard-scroll caveat) | Font → **ST-6**; scroll-container shell → **ST-8** | ST-6 (font) + ST-8 (scroll) |

**Net:** no fix is authored twice. Files co-owned by multiple buckets (notably
`settings-dialog.tsx`, `command-palette.tsx`, `byok-form.tsx`,
`ui/button.tsx`, `ui/dialog.tsx`) each carry orthogonal property edits — see the
**Sequencing & coordination** note in §(c).

---

## (b) Locked mobile-first type ramp

Five role utilities, added once to `globals.css` in the existing
`@layer components` block (same mechanism as `.chat-md`). Interactive text sits
at the **16px mobile floor** already proven by every text input (the iOS
no-zoom floor); captions bottom out at the **13px mobile** comfortable minimum.
Desktop holds today's dense sizes via `md:`.

### Role table (LOCKED)

| Utility | Applies to | Mobile | Desktop | Expansion |
| --- | --- | --- | --- | --- |
| `.ui-list-row` | conversation rows, menu items, command/action rows, tabs, primary list text, form labels | **16px** | 14px | `text-base md:text-sm` |
| `.ui-body` | dialog/drawer copy, descriptions, empty states, alerts, status lines | **16px** | 14px | `text-base md:text-sm` |
| `.ui-secondary` | one-line description *under* a title (model/tier picker item subtitle, sidebar conv preview) | **15px** | 13px | `text-[0.9375rem] md:text-[0.8125rem]` |
| `.ui-caption` | metadata rows, helper text, counts, badges, timestamps | **13px** | 12px | `text-[0.8125rem] md:text-xs` |
| `.ui-eyebrow` | uppercase tracking-wide section headers / group labels | **13px** | 11px | `text-[0.8125rem] md:text-2xs` |

`.ui-list-row` and `.ui-body` are intentionally the same size (16→14); both names
ship for greppable semantic intent at call sites.

### Concrete `globals.css` addition (LOCKED)

Append inside the existing `@layer components { … }` block (currently ends at
`globals.css:814`), directly after the `.chat-md` rules:

```css
@layer components {
  /* ── Mobile-first type ramp (ST5 §b) ─────────────────────────────
     Bigger on the phone, denser on desktop — mirrors .chat-md (17→15)
     and the input pattern (16→14). Interactive roles hold the 16px iOS
     no-zoom floor on mobile; captions bottom out at the 13px minimum.
     Desktop steps reuse text-sm / text-xs / text-2xs unchanged. */
  .ui-list-row  { @apply text-base md:text-sm; }                 /* 16 → 14 */
  .ui-body      { @apply text-base md:text-sm; }                 /* 16 → 14 */
  .ui-secondary { @apply text-[0.9375rem] md:text-[0.8125rem]; } /* 15 → 13 */
  .ui-caption   { @apply text-[0.8125rem] md:text-xs; }          /* 13 → 12 */
  .ui-eyebrow   { @apply text-[0.8125rem] md:text-2xs; }         /* 13 → 11 */
}
```

**No new `@theme` tokens are required.** The desktop steps reuse the existing
`text-sm` (14) / `text-xs` (12) / `text-2xs` (11, `globals.css:169`) utilities;
the 15px and 13px mobile steps are arbitrary values already used in-tree
(`.chat-md` desktop = `0.9375rem`; `ai-disclosure` = `0.8125rem`). The audit's
alternative of minting `--text-body-mobile` / `--text-secondary-mobile` /
`--text-caption-mobile` tokens (ST1 §b) is **rejected** — utilities keep the ramp
in one auditable, greppable place and match the `.chat-md` precedent; loose
tokens would re-invite drift.

### Application idiom

Swap raw `text-sm` / `text-xs` / `text-2xs` on a flagged element for the matching
role utility. When the element already carries a semantic class, add the utility
alongside. **Never** add a font-size utility that resolves below 16px mobile to a
text input.

---

## (c) Partition into ST-6/7/8/9 — exact file lists

`+N` = approximate flagged occurrences in that file (from ST1's offender table);
line refs live in the source audits and are authoritative there.

### ST-6 — Type ramp (owning audit: ST1)

**Foundation (do first — biggest cascade, smallest diff):**

| File | Scope |
| --- | --- |
| `web/src/app/globals.css` | Add the 5 `.ui-*` utilities (§b) |
| `web/src/components/ui/button.tsx` | Font only: base `text-sm`→list-row-equiv, `xs`/`sm` size label steps (L7/25/26). **Coordinate with ST-7 touch edit.** |
| `web/src/components/ui/badge.tsx` | Base badge → `.ui-caption` (L8) |
| `web/src/components/ui/dropdown-menu.tsx` | Item/label/shortcut → `.ui-list-row` / `.ui-eyebrow` / `.ui-caption` (L68/91/116/162/204/244). **Coordinate with ST-9 overscroll.** |
| `web/src/components/ui/dialog.tsx` | Description body → `.ui-body` (L204). **Coordinate with ST-9 safe-area.** |
| `web/src/components/ui/drawer.tsx` | Description body → `.ui-body` (L169) |
| `web/src/components/ui/toast.tsx` | Toast body + action → `.ui-body` (L165/195) |
| `web/src/components/ui/tooltip.tsx` | Body → `.ui-caption` (L59) — desktop-hover, low mobile impact |

**Heavy offenders:**

| File | ~count |
| --- | --- |
| `web/src/components/chat/sidebar.tsx` | +30 (rows, eyebrows, previews, counts) |
| `web/src/components/chat/settings-dialog.tsx` | +40 incl. un-invert L1052. **Skip `<select>` L576 (ST-8).** **Coordinate with ST-7/8/9.** |
| `web/src/components/chat/command-palette.tsx` | +25. **Skip `FILTER_SELECT_CLASS` L92 (ST-8).** **Coordinate with ST-9.** |
| `web/src/components/chat/model-mode-picker.tsx` | +18 (eyebrows, item descriptions → `.ui-secondary`/`.ui-caption`) |
| `web/src/components/chat/attribution-row.tsx` | 2 (caption + badge) |
| `web/src/components/chat/usage-meter.tsx` | 2 (status pill + meta) |
| `web/src/components/chat/follow-up-chips.tsx` | 1 (chip label) |

**Remaining chat / view components** (all pure or font-portion-only):

`assistant-message.tsx`, `agentic-assistant-parts.tsx`, `activity-dialog.tsx`,
`byok-form.tsx` *(skip `<select>` L248 → ST-8)*, `auth-dialog.tsx`,
`web-search-panel.tsx`, `user-message.tsx`, `typing-indicator.tsx`,
`tool-part.tsx`, `tool-group-panel.tsx`, `tier-picker.tsx`,
`temporary-chat-banner.tsx`, `template-picker-popover.tsx`,
`template-library-dialog.tsx`, `subagent-panel.tsx`, `spend-analytics-panel.tsx`,
`sources-panel.tsx`, `slash-commands-popover.tsx`, `memory-dialog.tsx`,
`shortcuts-dialog.tsx`, `markdown-renderer.tsx`, `share-dialog.tsx`,
`reasoning-panel.tsx`, `key-caps.tsx`, `model-directory-dialog.tsx`,
`install-coachmark.tsx`, `degraded-status-banner.tsx`, `compare-column.tsx`,
`compare-view.tsx`, `message-actions.tsx`, `chat-thread.tsx`,
`welcome-screen.tsx`, `platform-status-view.tsx`,
`share/public-conversation-view.tsx`, `share/public-attribution-row.tsx`.

**Genuine one-offs that keep bespoke classes** (do not force into utilities):
`markdown-renderer.tsx:85` mermaid mono error; `key-caps.tsx` kbd hints and
`command-palette.tsx:935` footer (desktop-only, `hover:hover and pointer:fine`).

**ST-6 out of scope:** all `<select>` font sizes (→ ST-8); already-compliant
inputs marked ✅ in ST1 (do **not** rewrap — see risk R7).

### ST-7 — Touch targets (owning audit: ST2)

| File | Fix |
| --- | --- |
| `web/src/components/ui/button.tsx` | **Highest leverage:** touch floor in `buttonVariants` — icon sizes append `[@media(hover:none)]:size-11`; text sizes append `[@media(hover:none)]:min-h-11`. Fixes rows 3–7, 9–11 at once. **Coordinate with ST-6 font edit.** |
| `web/src/components/ui/checkbox.tsx` | Copy the `Switch` `::before` pattern — centered `[@media(hover:none)]` 44px pseudo-target (row 1) |
| `web/src/components/chat/compare-view.tsx` | Mobile tab strip `min-h-9`→`min-h-11` (`md:hidden`, zero desktop cost) (row 2) |
| `web/src/components/chat/settings-dialog.tsx` | Segmented toggle geometry + spacing (rows 8) — **needs geometry decision, see R1** |
| `web/src/components/chat/memory-dialog.tsx` | Edit/Delete `gap-1`→spacing + button floor (rows 3, 11) |
| `web/src/components/chat/template-library-dialog.tsx` | Same Edit/Delete pair (rows 4, 11) |
| `web/src/components/chat/shortcuts-dialog.tsx` | `icon-xs` reset button auto-fixed by button floor; verify `gap-1.5` cluster (row 5) |
| `web/src/components/chat/byok-form.tsx` | `size="sm"` action buttons auto-fixed by button floor (row 6) |
| `web/src/components/chat/activity-dialog.tsx` | `size="sm"` buttons auto-fixed (row 9) |
| `web/src/components/chat/spend-analytics-panel.tsx` | Export buttons auto-fixed (row 10) |
| `web/src/components/share/public-conversation-view.tsx` | Error-state `h-10`→44 (row 12, borderline) |

Most of rows 6/7/9/10/11 are **auto-repaired** by the single `button.tsx` floor;
the per-file entries above are the dense-cluster residue that needs spacing, plus
the `Checkbox` and compare-tab hit-slop.

### ST-8 — Input zoom + keyboard scroll (owning audit: ST3)

| File | Fix |
| --- | --- |
| `web/src/components/chat/byok-form.tsx` | Provider `<select>` L248 → `text-base md:text-sm` |
| `web/src/components/chat/settings-dialog.tsx` | Project `<select>` L576 → `text-base md:text-sm` |
| `web/src/components/chat/command-palette.tsx` | `FILTER_SELECT_CLASS` L92 → `text-base md:text-sm` (fixes Model/Project/Tag selects at 623/644/726) |
| `web/src/components/chat/auth-dialog.tsx` | Add `flex flex-col overflow-hidden` shell + `overflow-y-auto` body (landscape scroll fallback) — **low-risk, see R6** |
| `web/src/components/share/share-dialog.tsx` | Same scroll-container shell — **low-risk, see R6** |

All text `<input>`/`<textarea>` are already ≥16px mobile; no `contenteditable`
exists. No further input-zoom work.

### ST-9 — Native-feel gaps (owning audit: ST4)

**Haptics** (feature-detected, silent on iOS):

| File | Gap |
| --- | --- |
| `web/src/components/chat/message-actions.tsx` | G1a copy (`markCopied`), G1b feedback, G1e regenerate-with |
| `web/src/components/ui/switch.tsx` | G1c toggle `onCheckedChange` shim — covers all settings/composer toggles |
| `web/src/components/chat/settings-dialog.tsx` | G1d `selectTab` |
| `web/src/components/chat/compare-view.tsx` | G1d compare tab `onClick` |
| `web/src/components/chat/model-mode-picker.tsx` | G1e select handlers |
| `web/src/components/chat/tier-picker.tsx` | G1e `onSelectTier` |
| `web/src/components/chat/message-list.tsx` | G1f jump-to-latest |
| `web/src/components/layout/app-shell.tsx` | G9 drawer open/close parity (`onMobileNavOpenChange`) |
| `web/src/components/layout/app-header.tsx` | G9 drawer open-by-tap |

**Safe-area:**

| File | Gap |
| --- | --- |
| `web/src/components/ui/dialog.tsx` | G2 landscape L/R insets on mobile branch (L122) |
| `web/src/components/chat/command-palette.tsx` | G3 bottom + L/R insets on sheet (L525) |
| `web/src/components/chat/install-coachmark.tsx` | G10 `inset-x-3`→env insets (L106) |

**Overscroll containment:**

| File | Gap |
| --- | --- |
| `activity-dialog.tsx`, `template-library-dialog.tsx`, `shortcuts-dialog.tsx`, `model-directory-dialog.tsx`, `memory-dialog.tsx`, `tier-picker.tsx`, `command-palette.tsx` | G5 add `overscroll-contain` to each `overflow-y-auto` region |
| `ui/dropdown-menu.tsx`, `template-picker-popover.tsx`, `slash-commands-popover.tsx` | G5b add `overscroll-contain` to menu content |
| `web/src/app/globals.css` | G7 `overscroll-behavior-x: contain` on `.chat-md :where(pre)` + `:where(table)` (L784–790) |

**Manifest:**

| File | Gap |
| --- | --- |
| `web/src/app/manifest.ts` | G4 `shortcuts` (New chat / Search / Settings) — no new assets |

**Pressed / active states** (bespoke `<button>`s):

| File | Gap |
| --- | --- |
| `install-coachmark.tsx`, `settings-dialog.tsx`, `compare-view.tsx`, `ui/dialog.tsx`, `ui/drawer.tsx` | G6 add `active:scale-[0.96] active:duration-[70ms] motion-reduce:active:scale-100` |
| `ui/switch.tsx` | G6b subtle `active:scale-95` on thumb (reduced-motion guarded) |

**ST-9 deferred:** G8 manifest `screenshots` (requires producing narrow/wide PNG
assets — none exist in `web/public/`). See R8.

### Sequencing & coordination

1. **ST-6 foundation first** (`globals.css` utilities + shared primitives) — the
   `button.tsx` / `badge.tsx` / `dropdown-menu.tsx` / `dialog.tsx` / `drawer.tsx`
   edits cascade to dozens of call sites and shrink every downstream diff.
2. **ST-7 `button.tsx` touch floor** next — auto-repairs most of ST-2's table.
3. Then **ST-6 offenders**, **ST-8**, **ST-9** in parallel-safe order.
4. **Multi-bucket files** (`settings-dialog.tsx` = all four; `command-palette.tsx`
   = 6/8/9; `byok-form.tsx` = 6/7/8; `ui/button.tsx` = 6/7; `ui/dialog.tsx` =
   6/9; `ui/dropdown-menu.tsx` = 6/9): land each bucket's edit to that file
   sequentially, not concurrently, to avoid merge churn. Properties are
   orthogonal, so ordering within a file is free.

---

## (d) High-priority — the final gate MUST verify

Everything else is quality; these are the load-bearing, regression-prone
invariants. The Phase B closing gate fails if any is untrue.

| # | Gate check | Bucket | Source |
| --- | --- | --- | --- |
| H1 | **iOS no-zoom floor intact:** every `<input>` / `<textarea>` renders **≥16px** on mobile — no regression from the type sweep | ST-6 + ST-8 | ST1 §b caveat, ST3 |
| H2 | **The 3 stray `<select>`s** (`byok-form:248`, `settings-dialog:576`, `command-palette:92`) render **≥16px** mobile | ST-8 | ST3 |
| H3 | **Button touch floor:** every `size="sm\|xs\|icon\|icon-sm\|icon-xs"` clears **44×44** on `@media (hover:none)`, and a caller's own `size-*`/`h-*` override still wins (twMerge order) | ST-7 | ST2 §1 |
| H4 | **`Checkbox` hit region = 44px** on touch (sidebar multi-select tickable) | ST-7 | ST2 row 1 |
| H5 | **No interactive/body text below role floor on mobile:** list-row/body ≥16, secondary ≥15, caption/eyebrow ≥13; inverted ramp `settings-dialog:1052` un-inverted | ST-6 | ST1 §b |
| H6 | **High-frequency haptics fire:** copy (G1a), feedback thumbs (G1b), toggle switches (G1c) buzz on Android/Chromium, no-op on iOS | ST-9 | ST4 G1 (High) |
| H7 | **Desktop density byte-for-byte unchanged** — every added rule is `md:` / touch / `hover:none`-gated; a mouse viewport at ≥768px is visually identical pre/post | all | cross-cutting |
| H8 | **Dense clusters don't steal taps:** the segmented toggles + Edit/Delete pairs have ≥8px separation or bounded, non-overlapping hit-slop after ST-7 | ST-7 | ST2 §2 (rows 2–5, 8) |

Suggested gate evidence: a mobile-viewport (`hover:none`, ≤767px) pass measuring
computed `font-size` on inputs/selects and hit-box on buttons/checkbox; a desktop
(≥768px) before/after screenshot diff for H7; a touch-emulation tap on the
segmented toggles + Edit/Delete pairs for H8; Android haptic spot-check for H6.

---

## (e) Risks / uncertainties for orchestrator decision

| # | Item | Question / risk | Recommendation |
| --- | --- | --- | --- |
| **R1** | **Dense-cluster geometry** (ST2 rows 3,4,5,8) | A naïve 44px `::before` on two controls 4px apart makes their hit regions **overlap and steal taps**. Segmented toggles abut inside a `p-0.5` pill; Edit/Delete sit in `gap-1`. Size alone is wrong. | **Decide:** widen to `gap-2` (≥8px) **and** cap hit-slop so it can't cross a neighbour. Do **not** ship 44px targets without the spacing half. Needs sign-off because it changes visual layout, not just touch. |
| **R2** | **`<select>` zoom worth the churn?** | ST3 notes modern iOS does **not** reliably zoom on `<select>` focus (native picker, not inline caret). The 3 edits are cheap but touch shared classes. | **Do all 3 anyway** for a hard "every field ≥16px" invariant and surface consistency. Low cost, removes an audit exception. |
| **R3** | **Utility API vs. per-component classes** | Locking `.ui-list-row/.ui-body/.ui-secondary/.ui-caption/.ui-eyebrow` adds a small public CSS API to `globals.css`. | **Approve the utilities** (matches `.chat-md`, greppable, drift-resistant). Confirm naming before ST-6 lands so ~200 call sites don't churn twice. |
| **R4** | **`.ui-secondary` mis-binding** | Mapping "description under a title" to 15→**13** *shrinks desktop* for anything currently `text-sm` (14). Applied to the wrong element it makes desktop smaller than today. | Bind `.ui-secondary` **only** to genuine title-subtitle pairs (model/tier picker item desc, sidebar conv preview). When unsure, use `.ui-caption` (13→12) or `.ui-body`. Impl judgment; call out ambiguous cases in review. |
| **R5** | **`button.tsx` twMerge ordering** | The touch floor + font edit must not clobber caller overrides like `composer.tsx:1151` `size-11 md:size-7`. | Keep variant tokens first so class-merge resolves to the caller's value where present; add an e2e assertion (H3). |
| **R6** | **auth/share scroll containers** | ST3 rates the missing internal scroll region **low-risk, landscape/short-viewport only** — fields stay visible in portrait via the sheet lift. | **Include** (cheap, matches the pattern the other dialogs already use) but acceptable to **defer** if Phase B scope is tight. Not a gate item. |
| **R7** | **Don't rewrap compliant inputs** | Folding existing `text-base md:text-sm` inputs into `.ui-list-row` is a semantic no-op but risks someone later "simplifying" a util below 16px. | **Leave compliant inputs as-is** (ST1 ✅ rows). ST-6 touches only flagged non-input elements. |
| **R8** | **Manifest `screenshots` (G8)** | Requires producing narrow + wide product PNG/WebP assets; `web/public/` has none today — an asset-generation task, not a one-liner. | **Defer** out of Phase B unless install-conversion is prioritized. `shortcuts` (G4) still ships. |
| **R9** | **`chat-thread.tsx` scope** | The file is very large (edits near L3554/4197/4117/4212); type edits there are higher-risk to review. | Scope the ST-6 edit to the exact flagged lines; keep the diff surgical. The two inputs at 4117/4212 are already ✅ — leave them. |
| **R10** | **Public/private attribution parity** | `attribution-row.tsx` renders 2px smaller than its public mirror `public-attribution-row.tsx:58` for identical content (ST1 note). | Ramp both to `.ui-caption`; the two rows converge. Flag if intentional divergence is expected. |

---

## Appendix — audit tallies (for reference)

- **ST1:** ~200+ flagged font-size occurrences across ~44 files; two anti-patterns
  (`text-sm` no-`md:` → 14/14; `text-xs`/`text-2xs` no-`md:` → 11–12/11–12); one
  inverted ramp (`settings-dialog:1052`).
- **ST2:** 12 sub-44px control groups; 5 are dense-cluster (spacing) flags; the
  rest fall to one `buttonVariants` floor + `Checkbox` hit-slop.
- **ST3:** 3 `<select>`s <16px; all text inputs already ≥16px; keyboard-scroll OK
  everywhere except the auth/share landscape caveat.
- **ST4:** 10 native-feel gaps (G1 High: haptics on copy/feedback/toggle); the
  rest Med/Low; G8 deferred pending screenshot assets.
