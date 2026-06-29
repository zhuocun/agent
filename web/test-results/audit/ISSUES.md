# Visual-UX audit — issue log

Issues found across the ST1–ST5 screenshot sweep (desktop core, dialogs/overlays,
mobile, dynamic interaction-states, a11y media-emulation). Screenshot paths are
relative to this directory (`web/test-results/audit/`) and name their stage
subfolder. Each issue carries a stable ID; do not renumber on edit. Severities:
`MAJOR` > `MINOR` > `NIT`.

## ISSUE-1 — MAJOR — Install coachmark occludes 4th suggestion chip

- **Screenshots:** `st3-mobile/iphone13-welcome-light.png`, `st3-mobile/iphone13-welcome-dark.png`
- **Observation:** On the 390×844 iPhone 13 welcome hero, the bottom-pinned "Install
  Olune…" coachmark banner overlays the **4th** suggestion chip ("Compare options"),
  partially occluding it. The banner is intermittent — it is absent in
  `st3-mobile/vp390-welcome-dark.png`, where all four chips render unobstructed — so
  the overlap surfaces only when the coachmark is present on the short viewport.
  Candidate fix: reserve space for, or auto-dismiss, the coachmark above the
  suggestion list on short viewports.
- **Status:** confirmed (GPT-5.5)
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
- **Status:** confirmed (GPT-5.5)
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
- **Status:** confirmed (GPT-5.5)
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
- **Status:** confirmed (GPT-5.5)
- **GPT-5.5 re-review:** Confirmed. Both `st2-dialogs/settings-spend__dark.png`
  and `st2-dialogs/settings-general__dark.png` show the dark red "Spend data could
  not be loaded." error reading low-contrast against the dark surface; light-theme
  spend captures do not exhibit it.

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
