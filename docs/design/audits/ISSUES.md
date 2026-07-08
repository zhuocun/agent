# Visual-UX audit — issue log

Issues found across the ST1–ST5 screenshot sweep (desktop core, dialogs/overlays,
mobile, dynamic interaction-states, a11y media-emulation). Screenshot paths are
relative to the ephemeral audit run-output tree (`web/test-results/audit/`, which
`web/.gitignore` marks ephemeral) and name their stage subfolder — the PNGs are
**not** committed alongside this log, which was relocated here (from
`web/test-results/audit/`) to `docs/design/audits/` for a non-ephemeral home. Each
issue carries a stable ID; do not renumber on edit. Severities: `MAJOR` > `MINOR`
> `NIT`.

## ISSUE-1 — MAJOR — Install coachmark occludes 4th suggestion chip

- **Screenshots:** `st3-mobile/iphone13-welcome-light.png`, `st3-mobile/iphone13-welcome-dark.png`
- **Observation:** On the 390×844 iPhone 13 welcome hero, the bottom-pinned "Install
  Olune…" coachmark banner overlays the **4th** suggestion chip ("Compare options"),
  partially occluding it. The banner is intermittent — it is absent in
  `st3-mobile/vp390-welcome-dark.png`, where all four chips render unobstructed — so
  the overlap surfaces only when the coachmark is present on the short viewport.
  Candidate fix: reserve space for, or auto-dismiss, the coachmark above the
  suggestion list on short viewports.
- **Status:** fixed (PR #229)
- **Fix:** `install-coachmark.tsx` — suppress coachmark while `ul[aria-label="Suggested prompts"]` is mounted (MutationObserver); reappears after first send or on surfaces without a rail (e.g. `/status`).
- **GPT-5.5 re-review:** Confirmed. Both `st3-mobile/iphone13-welcome-light.png`
  and `-dark.png` show the install coachmark covering the 4th chip; the
  coachmark-free `st3-mobile/vp390-welcome-*` and ST1 desktop welcome captures
  are clean, consistent with a short-mobile-viewport-only overlap.

## ISSUE-2 — MINOR — User message bubble loses its container in forced-colors

- **Screenshots:** `st5-a11y/mobile-thread__forced-colors.png`
- **Observation:** Under `forced-colors: active` (OS High-Contrast), the user message
  bubble loses its visible container. The bubble's edge is normally drawn with an
  inset `box-shadow`, which forced-colors strips; `globals.css @media (forced-colors:
  active)` restores real borders on glass capsules/cards/inputs but does not appear to
  re-border the user message bubble, so it reads as floating text rather than a
  contained turn. Candidate fix: add a forced-colors border rule covering the user
  bubble surface.
- **Status:** fixed (PR #229)
- **Fix:** `globals.css` `@media (forced-colors: active)` — `border: 1px solid CanvasText` on `[data-testid="user-message-text"]` and `[data-testid="user-message-edit"]`.
- **GPT-5.5 re-review:** Confirmed. `st5-a11y/mobile-thread__forced-colors.png`
  shows the user bubble losing its visible container under `forced-colors:
  active`; the text stays visible but the turn reads as floating text.

## ISSUE-3 — MINOR — Mobile drawer shows desktop "Collapse sidebar", no visible close

- **Screenshots:** `st3-mobile/iphone13-drawer-light.png`, `st3-mobile/vp390-drawer-light.png`
- **Observation:** The mobile nav drawer renders the desktop "Collapse sidebar" chevron
  (top-right) — a no-op-ish affordance in a drawer context where the rail is already an
  overlay. The drawer's own close button exists in source (`size-11`, 44px) but ships
  with `showClose={false}`, so there is **no visible close control**; dismissal relies
  on backdrop-tap / Back. The only top-right glyph is the inherited desktop collapse
  icon. Worth confirming intent and surfacing a real close affordance.
- **Status:** fixed (PR #229)
- **Fix:** `app-shell.tsx` `showClose={true}` on mobile drawer; `globals.css` hides `[data-sidebar-collapse]` inside `[data-slot="drawer-content"]` only.
- **GPT-5.5 re-review:** Confirmed. All four drawer captures
  (`st3-mobile/iphone13-drawer-{light,dark}.png`,
  `st3-mobile/vp390-drawer-{light,dark}.png`) show the inherited desktop collapse
  chevron as the only top-right control; no dedicated visible close button.

## ISSUE-4 — MINOR (uncertain) — Disabled overflow items under-dimmed

- **Screenshots:** `st3-mobile/iphone13-overflow-dark.png`
- **Observation:** In the iPhone 13 dark header overflow ("Chat menu"), the
  copy/download/share items are disabled before the first turn (expected — nothing to
  export yet; only "Temporary chat" is active). The disabled items appear only lightly
  dimmed against the dark sheet, so the enabled/disabled distinction is weak. Marked
  **uncertain** — this may be within the intended disabled-state token contrast; needs a
  contrast check against the active row before treating as a defect.
- **Status:** refuted (GPT-5.5)
- **GPT-5.5 re-review:** Refuted. In both `st3-mobile/iphone13-overflow-dark.png`
  and `st3-mobile/vp390-overflow-dark.png`, the disabled export/share rows are
  noticeably dimmer than the active "Temporary chat" row and read as disabled.
  The enabled/disabled distinction holds, so the flagged under-dimming is not a
  defect. Issue retained (not deleted) with this disposition.

## ISSUE-5 — NIT — Dark-mode spend-error red low contrast

- **Screenshots:** `st2-dialogs/settings-spend__dark.png`
- **Observation:** In the dark-theme Spend settings panel, the "Spend data could not
  be loaded." error red reads low-contrast against the dark surface, making the
  warning easy to miss.
  Cosmetic; candidate fix is a dark-mode-specific error token bump to clear contrast
  thresholds.
- **Status:** fixed (PR #229)
- **Fix:** `globals.css` — scoped dark `--destructive-text` token + `text-destructive-text` utility; applied to spend/billing error alerts without changing `--destructive` button fills.
- **GPT-5.5 re-review:** Confirmed. Both `st2-dialogs/settings-spend__dark.png`
  and `st2-dialogs/settings-general__dark.png` show the dark red "Spend data could
  not be loaded." error reading low-contrast against the dark surface; light-theme
  spend captures do not exhibit it.

## 2026-07-07 sweep (W2 triage) — new issues

Source captures: `web/test-results/audit/` @ commit `31c01e7` (107 PNGs, five
stages, per-stage `manifest.md`, run summary `SWEEP-RUN.md`). Regression
verdicts for ISSUE-1/2/3/5: **all PASS** (see SWEEP-RUN.md table; re-verified
against the cited PNGs during this triage). Probes live in the gitignored
`web/test-results/audit/harness/probe-w2*.mjs`.

## ISSUE-6 — MAJOR — Install coachmark occludes both follow-up chips on iPhone 13 thread

- **Screenshots:** `st3-mobile/iphone13-thread-light.png`, `st3-mobile/iphone13-thread-dark.png`
- **Observation:** After a completed turn on the iPhone 13 profile, the
  "Install Olune…" pill renders directly on top of the "Tell me more" and
  "Give an example" follow-up chips. Probe (`probe-w2.mjs` A): coachmark rect
  `y 368–432` fully covers both chip rects (`y 392.5–436.5`);
  `document.elementFromPoint` at both chip centers resolves INSIDE the
  coachmark (`hitIsInsideCoachmark: true`), so taps on either chip are stolen
  by the pill. Same interactive-occlusion class as ISSUE-1.
- **Root cause:** `install-coachmark.tsx` parks the fixed pill at
  `bottom-[calc(var(--bottom-inset)+13rem)]` z-30. The ISSUE-1 fix suppresses
  it only while the welcome rail (`ul[aria-label="Suggested prompts"]`) is
  mounted; the follow-up chips (`[data-testid="follow-up-chips"]`, rendered
  in-flow after each done assistant turn) land in the same parked band on a
  short thread and are not covered by the suppression selector.
- **Candidate fix:** extend the coachmark's MutationObserver yield to also
  suppress while a `[data-testid="follow-up-chips"]` rect intersects the
  pill's fixed band (rect-intersection, not mere presence, so long threads
  where chips sit above the band keep the pill).
- **Disposition:** **fix** (W4)
- **Status:** fixed (commit `e58e977`)
- **Fix:** `install-coachmark.tsx` — pill measures its own rect against every
  `[data-testid="follow-up-chips"]` group and yields via `visibility` (rect
  stays measurable) while any intersects; rechecked on DOM mutations, scrolls,
  and resizes.

## ISSUE-7 — MINOR — Install coachmark overlaps /status page content on iPhone 13

- **Screenshots:** `st3-mobile/iphone13-status-light.png`, `st3-mobile/iphone13-status-dark.png`
- **Observation:** On /status the pill sits over the "Errors" metric value and
  the "Updated Jul 7, 2026 …" caption. Probe (`probe-w2.mjs` B): coachmark
  rect `y 368–432` overlaps the Errors value node (`y 368–392`) and the
  Updated caption (`y 416–474.5`); `composerPresent: false`.
- **Root cause:** the same `+13rem` parking offset exists to clear the
  composer capsule + follow-up chips, but /status has no composer — the pill
  floats mid-content instead of resting near the safe-area floor.
- **Candidate fix:** when no composer is mounted, park the pill at the
  safe-area floor (`bottom-[calc(var(--bottom-inset)+0.75rem)]`) so it hugs
  the bottom edge on composer-less surfaces.
- **Disposition:** **fix** (W4)
- **Status:** fixed (commit `e58e977`)
- **Fix:** `install-coachmark.tsx` — tracks composer presence and parks the
  pill at the safe-area floor (`+0.75rem`) when no composer is mounted, so
  composer-less surfaces like /status no longer get the 13rem mid-content
  float.

## ISSUE-8 — MINOR — Dark-mode overlay scrim lightens the page behind drawer/dialog

- **Screenshots:** `st3-mobile/vp390-drawer-dark.png`, `st3-mobile/iphone13-drawer-dark.png`, `st3-mobile/iphone13-settings-dark.png`, `st2-dialogs/auth-dialog__dark.png`
- **Observation:** In dark theme, the exposed page behind the drawer / settings
  sheet / auth dialog reads as a washed-out light-gray column instead of a
  dimmed dark page. Probe (`probe-w2.mjs` C): the backdrop computes to
  `oklab(0.96 … / 0.3)` — i.e. near-WHITE at 30% + `blur(12px)` — and the same
  page pixels measure relative luminance 0.0033–0.0051 before open vs
  0.081–0.092 with the scrim up: the "scrim" makes the dark page ~23×
  BRIGHTER. In light theme the same rule darkens (foreground is near-black),
  so dimming direction is theme-inverted.
- **Root cause:** `dialog.tsx` / `drawer.tsx` backdrops use `bg-foreground/30`
  (command-palette uses `bg-foreground/45`). `--foreground` flips to
  near-white in `.dark`, so the overlay tint inverts with the theme. PR #110
  ("lighter scrim with stronger backdrop blur") tuned opacity, not the
  theme-inverting base color; no design doc specifies a lightening scrim in
  dark mode, and iOS sheet scrims dim toward black in both appearances.
- **Candidate fix:** theme-stable dim — keep the blur, base the tint on black
  in dark mode (e.g. a `--scrim` token: `foreground/30` in light,
  `black/45`-ish in dark) across dialog, drawer, and command-palette
  backdrops.
- **Disposition:** **fix** (W4)
- **Status:** fixed (commit `9744e92`)
- **Fix:** `globals.css` — new `--scrim` color token (foreground-family ink in
  light, pure black in dark) exposed as the Tailwind `scrim` color;
  `dialog.tsx` / `drawer.tsx` backdrops moved to `bg-scrim/30` and
  `command-palette.tsx` to `bg-scrim/45`, so modals dim (never lighten) in
  both themes.

## ISSUE-9 — NIT — Disabled Save in user-message edit capsule low contrast

- **Screenshots:** `st4-dynamic/user-message-editing.png`
- **Observation:** The disabled Save pill (draft unchanged ⇒ `canSave` false)
  renders `bg-brand` + white label at `disabled:opacity-40`. Measured from the
  PNG: label-on-fill ≈ 1.7:1; fill-on-surface ≈ 4.07:1 vs the page. The washed
  pill reads clearly as disabled next to the fully-saturated enabled state
  (the composer send affordance in `composer-filled.png` shows the enabled
  reference).
- **Root cause:** intended disabled-state token (`disabled:opacity-40` in
  `user-message.tsx`), the same idiom the rest of the app uses; disabled
  controls are exempt from WCAG 1.4.3/1.4.11 contrast minima.
- **Disposition:** **refuted** — same reasoning as ISSUE-4: the
  enabled/disabled distinction holds and the dimming is the intended token, so
  low label contrast on an inert control is not a defect. Retained with this
  disposition per ISSUE-4 precedent.

### W2 triage — reviewed and NOT logged as defects

- **Blank thread at `st4-dynamic/streaming-plus120ms.png`** (no hero, no user
  bubble): refuted as a harness/timing artifact. Probe
  (`probe-w2-sendgap.mjs`): the welcome hero unmounts and the optimistic user
  message mounts in the SAME animation frame (`blankWindowMs: 0`); there is no
  DOM state in which neither is present.
- **Empty send-button circle in `streaming-mid-answer.png`**: race-adjacent
  frame (stream finished between rAF-arm and shot; icon caught mid-swap with
  `animations: "disabled"`). Not reproducible as a stable state; deferred.
- **Stale "Needs approval" pill on the historical tool_call part after
  Approve/Deny** (`tool-approved-resumed.png`, `tool-denied.png`): reads as
  the persisted record of the gate; the result part carries the outcome pill
  ("Approved"/"Rejected"). Matches `tool-part.tsx` status vocabulary; not a
  defect.
- **"Fast" tier label wraps to its own line under the substitution capsule on
  390px threads** (`st3-mobile/vp390-thread-*.png`): natural flex-wrap of the
  attribution row; deferred as a typographic nit, no fix proposed.
- **All-zero "Daily spend" chart renders a 112px empty region with only axis
  labels** (`st2-dialogs/settings-spend__light.png`, `__dark.png`): the
  "No spend in this window." empty-state only covers `daily.length === 0`, not
  all-zero windows; deferred (empty-state polish, product-intent call).
- **`contrast-more`, `forced-colors`, `scheme-dark`, `reduced-motion` ST5
  matrix**: clean; forced-colors user-bubble border (ISSUE-2 fix) holds in
  both palettes; a suspected gray "smudge" above the user bubble in
  forced-colors shots was disproven by pixel sampling (pure white — preview
  scaling artifact).

## Harness caveats

These bound what the captures can and cannot prove. None are product bugs.

- **SSE buffering through the same-origin rewrite (ST4):** The `:3000` prod-style FE
  (and any `next dev`/`next start` FE that proxies `/api/*`) buffers the SSE response
  body locally until the upstream closes, so genuinely transient frames (partial answer
  tokens, the live "Searching the web…" status) collapse into the terminal frame. ST4
  worked around this by pointing the FE directly at the BE
  (`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`), exactly as the e2e config does.
  Terminal/persisted states render identically on either stack.
- **Transient spend / streaming load timing:** The fake provider streams its canned
  reply in ~450ms, so the in-flight window is narrow; transient shots are timing-tuned
  (e.g. ST3 streaming captured at +280ms) and are inherently race-adjacent versus the
  stable terminal/`awaiting_approval` frames.
- **Safe-area insets resolve to 0 in headless (ST3):** Headless Chromium injects no
  physical notch/home-indicator, so `env(safe-area-inset-*)` resolve to **0** in every
  shot — only the fallback paddings render. These captures confirm the fallback layout
  but cannot visually validate true inset behavior; that needs a real device or a
  notch-simulating harness.
- **reduced-transparency is unemulatable (ST5):** The app ships
  `@media (prefers-reduced-transparency: reduce)` CSS, but Playwright's `emulateMedia`
  exposes no `reducedTransparency` knob (only media/colorScheme/reducedMotion/
  forcedColors/contrast as of Playwright 1.60). This surface cannot be
  screenshot-emulated here — flagged, not silently skipped.

## Scope & provenance

- **Source sweep — `web/test-results/audit/`, 96 PNGs total:**
  - `st1-desktop/` — 16 PNGs (desktop core surfaces, light + dark).
  - `st2-dialogs/` — 18 PNGs (dialogs / overlays / settings, light + dark).
  - `st3-mobile/` — 28 PNGs (2 profiles `vp390`/`iphone13` × 2 themes × 7 surfaces).
  - `st4-dynamic/` — 12 PNGs (dynamic/transient interaction-states, light).
  - `st5-a11y/` — 22 PNGs (forced-colors / contrast-more / reduced-motion /
    color-scheme-dark matrix + reduced-motion motion-proof pair).
- **Curated set — `/opt/cursor/artifacts/`:** 26 representative PNGs promoted from the
  full sweep for the walkthrough (e.g. `st3-iphone13-welcome-light.png`,
  `mobile-thread__forced-colors.png`, `settings-spend`-adjacent dialogs, the ST4
  interaction-state set), plus `st3-mobile-manifest.md`.
- **Provenance:** Findings are drawn from the per-stage manifests (`*/manifest.md`)
  and the captures themselves; no new issues were invented for this log. Every cited
  screenshot path was verified to exist on disk at authoring time.

## Re-review summary

- **Model:** gpt-5.5-high
- **Date:** 2026-06-29
- **Scope:** Full re-review of all 96 stage PNGs (ST1–ST5). The 26 curated PNGs in
  `/opt/cursor/artifacts/` are byte-identical duplicates and inherit their stage
  verdicts (not re-reviewed independently). Merged report:
  `GPT55-REVIEW.md`.

| issue | original status | GPT-5.5 disposition | evidence |
| --- | --- | --- | --- |
| ISSUE-1 — Install coachmark occludes 4th suggestion chip | open | **confirmed** | `st3-mobile/iphone13-welcome-{light,dark}.png` |
| ISSUE-2 — User bubble loses container in forced-colors | open | **confirmed** | `st5-a11y/mobile-thread__forced-colors.png` |
| ISSUE-3 — Mobile drawer shows desktop collapse, no visible close | open | **confirmed** | `st3-mobile/{iphone13,vp390}-drawer-{light,dark}.png` |
| ISSUE-4 — Disabled overflow items under-dimmed | open (uncertain) | **refuted** | `st3-mobile/{iphone13,vp390}-overflow-dark.png` |
| ISSUE-5 — Dark-mode spend-error red low contrast | open | **confirmed** | `st2-dialogs/settings-spend__dark.png`, `settings-general__dark.png` |

- **New findings:** none across ST1–ST5.
- **Net result:** 4 confirmed, 1 refuted (ISSUE-4). Refuted issue is retained with
  its disposition rather than deleted.
- **Fix pass (2026-06-29):** ISSUE-1/2/3/5 fixed in PR #229; ISSUE-4 skipped (refuted).
- **Fix pass (2026-07-07):** ISSUE-6/7 fixed in commit `e58e977`, ISSUE-8 fixed in
  commit `9744e92` (branch `cursor/ui-ux-sweep-fixes-10db`); ISSUE-9 skipped
  (refuted, per ISSUE-4 precedent).
