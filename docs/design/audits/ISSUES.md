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

## 2026-09-23 audit run — new issues

Source: the `pnpm audit:ui` Playwright harness (`web/tests/audit/ui.audit.ts`),
453 captures across five viewports (`d1440`, `d1024`, `t820`, `m390`, `m320`)
× two themes, plus media variants (`__reduced-motion`, `__forced-colors`,
`__contrast-more`, `__text200` / `__zoom200`) on the primary viewports and a
one-off `p600` narrow-pointer probe. Probes: overflow, target size, axe WCAG 2.2
AA, focus visibility, CLS and off-scale spacing. Raw triage input:
`docs/design/audits/2026-09-23-findings.md` (F1–F18). ISSUE-28–33 were found
after that list was written, while verifying the fixes. Unlike the sweeps above,
this run's screenshot paths are relative to `web/test-results/audit/shots/`
(`<viewport>/<theme>/<surface><__media>.png`) and are ephemeral. The PNGs of the original run were not retained, so each path names the harness surface that shows the defect; re-run `pnpm audit:ui` to regenerate it. Each entry
names the `docs/design/UI_STANDARDS.md` clause it fails. Where no clause asserts
the defect, the entry says so and names the nearest one. Fixes landed on branch
`claude/ui-optimization-playwright-iju8tj`.

## ISSUE-10 — MAJOR — Stop, then any new send, fails with 409 and loses the draft

- **Source:** F1
- **Standard:** UI-STREAM-7, UI-STREAM-9 (and UI-STATE-5: the failure implies the draft was never sent)
- **Screenshots:** `d1440/light/stopped.png`, `d1440/light/send-after-stop.png`, `d1440/light/share-view.png`
- **Observation:** After Stop, every new send returns `409 STREAM_IN_PROGRESS`
  (10 of 10 attempts, and still failing 12 s or more later). The optimistic user
  bubble is removed and the typed draft is lost. The API logs no `turn.stopped`
  line, and the stopped partial never reaches the share view. Hypothesis:
  sse-starlette's cancellation of the disconnected stream also cancels the
  stop-path DB write (`api/app/streaming/handler.py`,
  `api/app/streaming/turn_lifecycle.py` `_terminalize`), so the turn row is
  never terminalized and the in-progress guard stays latched. The FE half is in
  `chat-thread.tsx`, which drops the bubble and the draft on the 409.
- **Status:** fixed (commits `392de99`, `82bc7c8`, `23a3151`, `1508daf`, merged
  in `a4c1fdc`)
- **Fix:** the inline turn runs in its own task, outside the SSE response's
  cancel scope, and relays frames through a one-slot queue so it stays paced by
  the client. A disconnect raises the stop signal, and Stop's terminal write
  completes. The next send waits up to 3 s for a stopping stream to release its
  row. On a 409 the FE restores the draft into an empty composer and offers
  "Send again". Tests: `api/tests/test_stop_disconnect.py` and the "stop then
  send again immediately" and "409 keeps the draft" cases in
  `web/tests/e2e/streaming.spec.ts`. Unless the Redis stop store is configured,
  the stop flag is per machine, so the 3 s wait only helps when both requests
  reach the same Fly machine.

## ISSUE-11 — MAJOR — Mouse and pen clicks inside bottom sheets are dead below 768 px

- **Source:** F2
- **Standard:** UI-FOCUS-7 (a swipe gesture must leave single-pointer operation intact). No clause asserts pointer operability of sheet contents directly.
- **Screenshots:** `p600/light/sheet-mouse-click.png`
- **Observation:** Below 768 px, where dialogs render as swipe-dismissable
  bottom sheets, a mouse or pen click on a control inside the sheet did nothing.
  Keyboard and touch taps worked. `use-swipe-dismiss.ts` called
  `setPointerCapture` on `pointerdown`, which retargeted the resulting `click`
  to the sheet element and swallowed the control's handler.
- **Status:** fixed (commits `0fa4207`, `c31426c`)
- **Fix:** `web/src/lib/use-swipe-dismiss.ts` — a press stays a plain click until it
  travels 6 px downward, and pointer capture is taken only then (`0fa4207`).
  `web/src/components/chat/command-palette.tsx` drops its control-skipping
  workaround, which the hook change made unnecessary. Follow-up `c31426c`: a
  pending press is cleared when a move arrives with no button held, so a press
  released outside the sheet no longer turns a later hover into a drag. The sheet
  offset starts after the slop. Covered in `web/tests/e2e/ui-primitives.spec.ts`.

## ISSUE-12 — MAJOR — Deep research shows "Partial answer" before the plan is approved

- **Source:** F3
- **Standard:** UI-STATE-1 (a pause is `awaiting_approval`, not a degraded result); UI-TRUST-5 for the share projection
- **Screenshots:** `d1440/light/deep-research-plan.png`, `d1440/light/deep-research-done.png`
- **Observation:** A deep-research run waiting at its plan-approval gate showed
  "Partial answer — some research steps did not finish" before the user had
  decided. The server put `partial=True` on the wire at the pause
  (`api/app/agentic/orchestrator.py`), and `web/src/lib/agentic-layout.ts` had
  no pause guard. The chip also survived approval and reload. NIT in the same
  flow: the approved plan card kept its optimistic "Running" pill after the run
  finished.
- **Status:** fixed (commit `3c91260`)
- **Fix:** the pause sites in `api/app/agentic/orchestrator.py` stop raising the
  wire `partial` flag. `api/app/streaming/turn_reducer.py` folds a pause-boundary
  receipt to a new `paused` outcome (`api/app/schemas/message.py`,
  `api/app/schemas/share.py`). On the FE, `web/src/lib/agentic-layout.ts`,
  `web/src/lib/types.ts` and `chat-thread.tsx` mirror the fold.
  `assistant-message.tsx`, `agentic-assistant-parts.tsx` and
  `share/public-conversation-view.tsx` suppress the chip on an
  `awaiting_approval` row, which also covers rows persisted before the change.
  The plan card settles once the run finishes, so no stale "Running" pill.
  Covered in `api/tests/test_arch_review_ledger_resume.py` and
  `web/tests/e2e/agentic.spec.ts`.

## ISSUE-13 — MINOR — Table cells break mid-word and the table never scrolls

- **Source:** F4
- **Standard:** UI-LAYOUT-2 (UI-LAYOUT-11 keeps `anywhere` for prose only)
- **Screenshots:** `m390/light/thread-rich-table.png`
- **Observation:** Markdown table cells inherited `overflow-wrap: anywhere`
  from `.chat-md` (`globals.css`). Every column shrank to about one character,
  words broke mid-letter, and the table never overflowed into its horizontal
  scroller.
- **Status:** fixed (commit `cd66b4c`; test hardened in `a720b7c`)
- **Fix:** `web/src/app/globals.css` — table cells wrap at word boundaries, and a wide
  table scrolls inside its container. Prose keeps `anywhere`. Covered in
  `web/tests/e2e/markdown-parts.spec.ts`. `a720b7c` makes that test check
  whichever element actually scrolls.

## ISSUE-14 — MINOR — 320×640 welcome hero overflows upward under the header

- **Source:** F5
- **Standard:** UI-LAYOUT-1 (SC 1.4.10 Reflow at 320 px: content pushed out of scroll reach)
- **Screenshots:** `m320/light/welcome.png`, `m320/dark/welcome.png`
- **Observation:** At 320×640 the welcome hero was taller than its scroll area.
  Because it was centred, it grew upward: "Connect your API key" sat under the
  header, out of scroll reach, and the title collided with the header's
  trailing pill (`welcome-screen.tsx`).
- **Status:** fixed (commits `2877c27`, `0cd6287`)
- **Fix:** `web/src/components/chat/welcome-screen.tsx` — the hero start-aligns once it
  overflows. `web/src/components/chat/app-header.tsx` drops the decorative
  wordmark below 360 px (`2877c27`). `0cd6287` replaces `safe center`, which
  needs Safari 17.6+, with auto margins that work on every engine. Covered in
  `web/tests/e2e/app-shell.spec.ts` (`8bb5c87`, `0cd6287`).

## ISSUE-15 — MINOR — Auth dialog clips the left edge of the input focus ring

- **Source:** F6
- **Standard:** UI-FOCUS-2
- **Screenshots:** harness surface `auth-signin` focus walk (`focus/d1440__light/`) at d1440
- **Observation:** The auth dialog's scroll body padded only its right edge.
  Its overflow clip cut the 4 px focus ring on the left of the full-width inputs.
- **Status:** fixed (commit `e770bd8`)
- **Fix:** `web/src/components/chat/auth-dialog.tsx` — the scroll body leaves room on both
  sides for the field focus ring. Covered in
  `web/tests/e2e/a11y-structure.spec.ts` (`cd7bf0b`).

## ISSUE-16 — MINOR — Command palette ARIA structure invalid (axe critical)

- **Source:** F7
- **Standard:** UI-FOCUS-1. No clause asserts ARIA ownership. The axe gate is PRD 06 §7 AC 4, recorded as §15 C5.
- **Screenshots:** `d1440/light/command-palette.png`
- **Observation:** The palette rendered its options inside `<ul>`/`<li>` wrappers
  under `role="listbox"`. The listbox owned list items, and the options had no
  listbox or group parent (axe `aria-required-children` /
  `aria-required-parent`, critical).
- **Status:** fixed (commits `a837762`, `44ad47f`)
- **Fix:** `web/src/components/chat/command-palette.tsx` — options are nested in listbox
  groups (`a837762`). Follow-up `44ad47f` scrolls the active option into view,
  because focus stays in the input (`aria-activedescendant`). Covered in
  `web/tests/e2e/a11y-structure.spec.ts` (`cd7bf0b`, `44ad47f`).

## ISSUE-17 — MINOR — Small secondary text at 70% muted fails contrast

- **Source:** F8
- **Standard:** UI-COLOR-3 (UI-TRUST-6 for the tier and tool captions)
- **Screenshots:** `d1440/light/deep-research-done.png`, `d1440/light/tool-approval.png`, `d1440/light/model-picker.png`
- **Observation:** `text-muted-foreground/70` (and `/60`) at 12–13 px measured
  3.06–4.04:1, below the 4.5:1 floor, in both themes (subagent panel, tool part,
  tier picker).
- **Status:** fixed (commit `91e2e55`)
- **Fix:** switched to full-strength `text-muted-foreground` in
  `subagent-panel.tsx`, `tool-part.tsx`, `tier-picker.tsx`,
  `model-directory-dialog.tsx` and `web-search-panel.tsx`
  (`web/src/components/chat/`).

## ISSUE-18 — MINOR — Citation markers under the 24 px pointer floor

- **Source:** F9
- **Standard:** UI-TOUCH-2 (UI-TOUCH-1 on touch, bounded by §15 C50; see ISSUE-33)
- **Screenshots:** `d1440/light/web-search.png`
- **Observation:** Inline citation markers (`[1]`) painted at about 22×13 px,
  under the 24 px pointer floor (`markdown-renderer.tsx`).
- **Status:** fixed (commit `6d89b40`)
- **Fix:** `web/src/components/chat/markdown-renderer.tsx` — an invisible `::before`
  hit-slop grows the target to 24 px on a pointer and 44 px on touch without
  changing the type size or line box. Covered in
  `web/tests/e2e/touch-targets.spec.ts`. The touch half's vertical slop later
  proved too tall: ISSUE-33.

## ISSUE-19 — MINOR — 820 px touch tablet gets sub-44 px targets

- **Source:** F10
- **Standard:** UI-TOUCH-1, UI-TOUCH-5 (UI-TOUCH-4 bounds the fix)
- **Screenshots:** `t820/light/sidebar.png`, `t820/light/thread.png`, `t820/light/web-search-expanded.png`
- **Observation:** On the 820 px touch tablet, which gets the desktop layout,
  several targets fell below 44 px. Sidebar "Advanced search" measured 24 px
  tall and "Select" 36 px. The "Thought for" reasoning toggle and the sources
  toggle measured 28 px. The two toggles used the inverted form UI-TOUCH-5 names:
  a 44 px base reset by `md:`. The command palette's filter fields had no touch
  floor at all.
- **Status:** fixed (commit `6d89b40`)
- **Fix:** `sidebar.tsx`, `reasoning-panel.tsx`, `sources-panel.tsx` and
  `command-palette.tsx` (`web/src/components/chat/`) keep the dense size as the
  base with a `[@media(hover:none)]` 44 px override, so mouse density is
  unchanged. Covered in `web/tests/e2e/touch-targets.spec.ts`.

## ISSUE-20 — MINOR — Composer breaks at 200% text size

- **Source:** F11
- **Standard:** UI-TYPE-3 (WCAG 1.4.4)
- **Screenshots:** `m390/light/welcome__text200.png`, `m390/light/thread__text200.png`
- **Observation:** With the root font at 200%, the composer broke. The
  auto-grown textarea did not re-fit its changed box, its cap was not rem-based,
  and the model pill was crushed to its padding.
- **Status:** fixed (commits `cd66b4c`, `a720b7c`)
- **Fix:** `web/src/components/chat/composer.tsx` — the textarea re-fits when its box
  changes, uses a rem-based cap, and the toolbar wraps.
  `web/src/components/chat/model-mode-picker.tsx` gives the pill's rem width
  budget a floor (`cd66b4c`). `a720b7c` gives the picker a zero-basis, 6rem-floor
  wrapper, so the row wraps only at 200% text and not on a long label at 100%.
  Covered in `web/tests/e2e/composer-extras.spec.ts`.

## ISSUE-21 — MINOR — Code-block and table scrollers not keyboard-reachable

- **Source:** F12
- **Standard:** UI-FOCUS-1, UI-LAYOUT-2
- **Screenshots:** `d1440/light/thread-rich-code.png`, `d1440/light/thread-rich-table.png`
- **Observation:** A long code line or a wide table scrolled horizontally with
  no way to reach the scroller from the keyboard (axe
  `scrollable-region-focusable`).
- **Status:** fixed (commits `934fd8f`, `97fb905`)
- **Fix:** `web/src/components/chat/markdown-renderer.tsx` and
  `web/src/app/globals.css` — a scroller that overflows gets `tabIndex=0`, a
  name and `role=region` (unless it is the table itself), plus a focus ring. It
  leaves the Tab order once its content fits (`934fd8f`). `97fb905` syncs on a
  150 ms trailing debounce instead of every streamed frame, and keeps a focused
  region's tabindex until focus leaves. Covered in
  `web/tests/e2e/a11y-structure.spec.ts` (`cd7bf0b`, `97fb905`).

## ISSUE-22 — MINOR — Toast stack list markup invalid

- **Source:** F13
- **Standard:** no clause asserts list semantics. The axe gate is PRD 06 §7 AC 4, recorded as §15 C5. The toasts' live-region roles are UI-STATE-2's.
- **Screenshots:** harness axe probe (`list` rule) at d1440; the raw findings do not record the surface
- **Observation:** Each toast is a status or alert live region. An `<li>`
  carrying that role loses its `listitem` role, so the `<ol>` had no valid
  children (axe `list`).
- **Status:** fixed (commit `af11472`)
- **Fix:** `web/src/components/ui/toast.tsx` — the stack renders without list markup.
  `web/tests/e2e/ui-primitives.spec.ts` was updated to match, and
  `web/tests/e2e/a11y-structure.spec.ts` covers it (`cd7bf0b`).

## ISSUE-23 — MINOR — Model picker nests a switch inside a button

- **Source:** F14
- **Standard:** UI-FOCUS-1 (the desktop Advanced trigger was unreachable by keyboard); UI-FOCUS-12 for the row's name. The axe gate is §15 C5.
- **Screenshots:** `m390/light/model-picker.png`, `d1440/light/model-picker-advanced.png`
- **Observation:** In the mobile sheet, each toggle row was a button containing
  an `aria-hidden` Switch (axe `nested-interactive`). In the desktop menu, the
  Advanced collapsible trigger was a bare button inside `role=menu` (axe
  `aria-required-children`). At `tabIndex=-1`, outside the menu's roving focus,
  it could not be reached by keyboard.
- **Status:** fixed (commit `1b45caf`)
- **Fix:** `web/src/components/chat/model-mode-picker.tsx` — the row is the only
  control: a `role=switch` named by its visible label, with a decorative track.
  Advanced renders as a menu item. Covered in
  `web/tests/e2e/a11y-structure.spec.ts` (`cd7bf0b`).

## ISSUE-24 — NIT — Double divider under Platform credits

- **Source:** F15
- **Standard:** no clause names a doubled rule. This is a visual-craft NIT in the UI-CRAFT family.
- **Screenshots:** `d1440/light/settings-general.png`
- **Observation:** Two rules were stacked under Platform credits. The Monthly
  budget cap editor drew its own top border, and the budget group's wrapper
  already drew one.
- **Status:** fixed (commit `cd66b4c`; test fixed in `62bb2ac`)
- **Fix:** `web/src/components/chat/settings-dialog.tsx` — drops the editor's own top
  rule. Covered in `web/tests/e2e/bootstrap.spec.ts`. `62bb2ac` makes that
  assertion filter on border width, because the original `border-left-style`
  check passed without testing anything (Tailwind preflight sets every side to
  `solid`).

## ISSUE-25 — NIT — Missing space in run-cost meter ("$0.0001/ $1.00")

- **Source:** F16
- **Standard:** no clause asserts the spacing. The figure is a cost display under UI-TRUST-4.
- **Screenshots:** `d1440/light/deep-research-done.png`
- **Observation:** The run-cost meter painted "$0.0001/ $1.00". The leading space
  before "/ cap" sat at the start of a flex item, where it collapsed.
- **Status:** fixed (commit `cd66b4c`)
- **Fix:** `web/src/components/chat/subagent-panel.tsx` — a margin replaces the text
  space. The pill stays on one line, and the panel header wraps at narrow
  widths. Covered in `web/tests/e2e/agentic.spec.ts`.

## ISSUE-26 — NIT — Mobile drawer's bottom strip is a mismatched color

- **Source:** F17
- **Standard:** UI-MOBILE-2 (the inset is honoured, but it is painted in a different surface color)
- **Screenshots:** `m390/light/drawer.png`, `m390/dark/drawer.png`
- **Observation:** The drawer carried the safe-area padding itself. The strip
  below the opaque sidebar therefore showed the drawer's translucent glass, in a
  different color.
- **Status:** fixed (commit `8bb5c87`)
- **Fix:** `web/src/components/chat/app-shell.tsx` — the insets sit on a
  sidebar-colored wrapper inside the drawer. Covered in
  `web/tests/e2e/app-shell.spec.ts`, which also runs in light mode
  (`0cd6287`).

## ISSUE-27 — NIT — Model picker section headings repeat as the only row label

- **Source:** F18
- **Standard:** no clause asserts it directly. The nearest is UI-FOCUS-11: each toggle got a heading that only repeated its row's label.
- **Screenshots:** `m390/light/model-picker.png`
- **Observation:** In the mobile model picker, each toggle sat under its own
  section title, and that title only repeated the row's label.
- **Status:** fixed (commit `1b45caf`)
- **Fix:** `web/src/components/chat/model-mode-picker.tsx` — the toggles share one
  untitled list.

## ISSUE-28 — MINOR — Settings disclosure toggles 16–20 px tall on a touch tablet

- **Source:** later finding L1
- **Standard:** UI-TOUCH-1, UI-TOUCH-5 (UI-TOUCH-4 bounds the fix)
- **Screenshots:** `t820/light/settings-general.png`, `t820/light/settings-models.png`
- **Observation:** The BYOK, custom-instructions, project-defaults and
  advanced-privacy disclosure triggers in Settings measured 16–20 px tall on the
  touch tablet.
- **Status:** fixed (commit `f75911e`)
- **Fix:** `web/src/components/chat/settings-dialog.tsx` — adds the
  `[@media(hover:none)]:min-h-11` floor that Button and Checkbox use, so desktop
  density is unchanged. Covered in `web/tests/e2e/a11y-structure.spec.ts`
  (`9408cc6`).

## ISSUE-29 — MINOR — Chat menu covers the temporary-chat banner's Turn off

- **Source:** later finding L2
- **Standard:** UI-TRUST-10 (the control that leaves the mode is obscured), UI-TOUCH-2 (axe `target-size`, partially obscured)
- **Screenshots:** `m390/light/temporary-chat.png`
- **Observation:** Toggling "Temporary chat" (a checkbox menu item) left the
  chat menu open. On phones the menu then sat over the new banner and covered its
  Turn off button (axe `target-size`, partially obscured).
- **Status:** fixed (commit `5d20a79`)
- **Fix:** `web/src/components/chat/app-header.tsx` — toggling Temporary chat closes
  the menu. Covered in `web/tests/e2e/a11y-structure.spec.ts` (`9408cc6`).

## ISSUE-30 — MINOR — Scrolling message overflow menu not keyboard-reachable

- **Source:** later finding L3
- **Standard:** UI-FOCUS-1
- **Screenshots:** `m390/light/message-overflow.png`
- **Observation:** Opened by pointer, the tall message overflow menu scrolls,
  but no row is highlighted, so no descendant holds a tab stop. Axe reports the
  scroller as keyboard-unreachable (`scrollable-region-focusable`).
- **Status:** fixed (commit `756a16a`)
- **Fix:** `web/src/components/chat/message-actions.tsx` — the popup gets `tabIndex=0`.
  It already takes focus on open, so arrow-key and Tab behaviour are unchanged.
  Covered in `web/tests/e2e/a11y-structure.spec.ts` (`9408cc6`).

## ISSUE-31 — MINOR — Models and Shortcuts settings scrollers not keyboard-reachable

- **Source:** later finding L4
- **Standard:** UI-FOCUS-1
- **Screenshots:** `m390/light/settings-models.png`, `m390/light/settings-shortcuts.png`
- **Observation:** These read-only panels hold only text, so a keyboard user had
  no focus stop from which to scroll them (axe `scrollable-region-focusable`).
- **Status:** fixed (commit `9408cc6`)
- **Fix:** `web/src/components/chat/model-directory-dialog.tsx` and
  `web/src/components/chat/shortcuts-dialog.tsx` — each scroller gets a region
  role, a name, `tabIndex=0` and an inset focus ring. Covered in
  `web/tests/e2e/a11y-structure.spec.ts`.

## ISSUE-32 — MINOR — Spend "(month-to-date)" caption at 3.37:1

- **Source:** later finding L5
- **Standard:** UI-COLOR-3
- **Screenshots:** `d1440/light/settings-general.png`
- **Observation:** The "(month-to-date)" caption in the Settings spend panel
  faded the muted token with `opacity-70` and measured 3.37:1 (axe
  `color-contrast`). ISSUE-17 did not cover this site.
- **Status:** fixed (commit `dedd921`)
- **Fix:** `web/src/components/chat/spend-analytics-panel.tsx` — full-strength
  `text-muted-foreground` in both themes. Covered in
  `web/tests/e2e/a11y-structure.spec.ts`.

## ISSUE-33 — MINOR — Citation touch hit areas overlap neighbours

- **Source:** later finding, from verifying ISSUE-18
- **Standard:** UI-TOUCH-3; resolved against UI-TOUCH-1 by UI_STANDARDS §15 C50
- **Screenshots:** harness surface `web-search` at m390
- **Observation:** ISSUE-18's 44 px touch hit-slop introduced two overlaps.
  Across a run like `[1][2]`, adjacent slops overlapped, so a tap on the right of
  `[1]` opened source 2. The 44 px-tall slop also reached about 9 px into the
  28 px prose lines above and below, where it took taps from links and from
  citations on neighbouring lines.
- **Status:** fixed (commits `5c91983`, `d9c5961`; standard ruling `2da0ca7`)
- **Fix:** `web/src/components/chat/citation-rehype.ts` flags a marker that
  directly follows another. On touch, `web/src/components/chat/markdown-renderer.tsx`
  pushes that marker clear of its neighbour's slop (`5c91983`). The touch slop
  stops at the 28 px line box, and a following marker starts its pointer slop at
  its own edge (`d9c5961`). `docs/design/UI_STANDARDS.md` §15 C50 records the
  exception: an inline citation's touch hit area is at least 44 px wide and
  exactly its line box tall (`2da0ca7`). Covered in
  `web/tests/e2e/touch-targets.spec.ts`.

### 2026-09-23 run — known, not counted

Seen in the run and already on record, so not logged as new issues (per the
findings file):

- **"Fast" tier label wraps under the substitution capsule** on narrow
  threads. This is the W2 triage deferral above, still deferred.
- **§15 C40** — code-block controls draw Streamdown's own icon family
  (UI-CRAFT-4). Already registered as failing.
- **§15 C48** — toasts close on a clock the user cannot stop (UI-STATE-8).
  Already registered as failing.
- **§15 C15** — print clips the thread (UI-PREF-5). Already registered.

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
- **Fix pass (2026-09-23/24):** ISSUE-10–33 fixed on branch
  `claude/ui-optimization-playwright-iju8tj` (commits cited per entry).
