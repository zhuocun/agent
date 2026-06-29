# REVIEW-INVENTORY — visual-UX re-review checklist

Flat checklist of every screenshot to re-review. One row per PNG. `verdict`
column is intentionally blank — it is filled during S3 review.

## Count reconciliation

| Source | Expected | Found | OK |
| --- | --- | --- | --- |
| `st1-desktop/` | 16 | 16 | ✓ |
| `st2-dialogs/` | 18 | 18 | ✓ |
| `st3-mobile/` | 28 | 28 | ✓ |
| `st4-dynamic/` | 12 | 12 | ✓ |
| `st5-a11y/` | 22 | 22 | ✓ |
| **Stage subtotal** | **96** | **96** | ✓ |
| `/opt/cursor/artifacts/` (curated) | ~26 | 26 | ✓ |
| **Grand total targets** | **~122** | **122** | ✓ |

Notes:
- All **26** curated PNGs in `/opt/cursor/artifacts/` are **byte-identical
  (md5-verified) duplicates** of stage PNGs — no unique pixels to review. They
  are listed below for traceability but inherit their stage row's verdict; do
  not re-review them independently.
- `st3-mobile/md5sums.txt` and `st4-dynamic/md5sums.txt` are checksum sidecars
  (not screenshots) — md5 ground truth for those stages.
- Each stage dir also carries a `manifest.md` (intent source; not a review
  target).
- Within-stage byte-dupes exist by design in st5 (reduced-motion settled shots
  equal their default) — flagged inline.

---

## ST1 — Desktop core (16)

Viewport 1280×880 @DPR2, light+dark, fake provider.

| stage | filename | intent | verdict |
| --- | --- | --- | --- |
| st1 | 01-default-thread-light.png | Default thread: fake reply + attribution byline + follow-up chips (light) |  |
| st1 | 01-default-thread-dark.png | Default thread: fake reply + attribution byline + follow-up chips (dark) |  |
| st1 | 02-tier-picker-light.png | Tier/model picker dropdown open (light) |  |
| st1 | 02-tier-picker-dark.png | Tier/model picker dropdown open (dark) |  |
| st1 | 03-cost-detail-light.png | Composer cost estimate expanded — "15 tokens in" (light) |  |
| st1 | 03-cost-detail-dark.png | Composer cost estimate expanded — "15 tokens in" (dark) |  |
| st1 | 04-sidebar-collapsed-light.png | Desktop rail collapsed (light) |  |
| st1 | 04-sidebar-collapsed-dark.png | Desktop rail collapsed (dark) |  |
| st1 | 05-welcome-hero-light.png | Empty new-chat hero + suggested-prompt rail (light) |  |
| st1 | 05-welcome-hero-dark.png | Empty new-chat hero + suggested-prompt rail (dark) |  |
| st1 | 06-suggestion-prefill-light.png | Composer prefilled from suggestion (light) |  |
| st1 | 06-suggestion-prefill-dark.png | Composer prefilled from suggestion (dark) |  |
| st1 | 08-temporary-banner-light.png | Temporary-chat toggled on; ephemeral-session banner (light) |  |
| st1 | 08-temporary-banner-dark.png | Temporary-chat toggled on; ephemeral-session banner (dark) |  |
| st1 | 09-settings-panel-light.png | Settings dialog opened from account menu (light) |  |
| st1 | 09-settings-panel-dark.png | Settings dialog opened from account menu (dark) |  |

(Skipped per manifest: history-empty placeholder light+dark — anonymous guest has no seeded history.)

## ST2 — Dialogs / overlays / settings (18)

Viewport 1280×880, light+dark.

| stage | filename | intent | verdict |
| --- | --- | --- | --- |
| st2 | command-palette__light.png | Command palette open (light) |  |
| st2 | command-palette__dark.png | Command palette open (dark) |  |
| st2 | account-menu__light.png | Account menu open (light) |  |
| st2 | account-menu__dark.png | Account menu open (dark) |  |
| st2 | auth-dialog__light.png | Auth (sign-in) dialog (light) |  |
| st2 | auth-dialog__dark.png | Auth (sign-in) dialog (dark) |  |
| st2 | auth-dialog-create__light.png | Auth create-account dialog (light) |  |
| st2 | auth-dialog-create__dark.png | Auth create-account dialog (dark) |  |
| st2 | settings-general__light.png | Settings → General tab (light) |  |
| st2 | settings-general__dark.png | Settings → General tab (dark) |  |
| st2 | settings-appearance__light.png | Settings → Appearance tab (light) |  |
| st2 | settings-appearance__dark.png | Settings → Appearance tab (dark) |  |
| st2 | settings-spend__light.png | Settings → Spend tab (light) |  |
| st2 | settings-spend__dark.png | Settings → Spend tab (dark) |  |
| st2 | settings-shortcuts__light.png | Settings → Shortcuts tab (light) |  |
| st2 | settings-shortcuts__dark.png | Settings → Shortcuts tab (dark) |  |
| st2 | settings-model-directory__light.png | Settings → Model directory tab (light) |  |
| st2 | settings-model-directory__dark.png | Settings → Model directory tab (dark) |  |

## ST3 — Mobile (28)

2 profiles (vp390 390×844 desktop-UA, iphone13 390×844 dsf3 mobile-UA) × 2 themes × 7 surfaces. md5 ground truth in `st3-mobile/md5sums.txt`.

| stage | filename | intent | verdict |
| --- | --- | --- | --- |
| st3 | iphone13-welcome-light.png | iPhone13 welcome hero (light) |  |
| st3 | iphone13-welcome-dark.png | iPhone13 welcome hero (dark) |  |
| st3 | iphone13-drawer-light.png | iPhone13 nav drawer open (light) |  |
| st3 | iphone13-drawer-dark.png | iPhone13 nav drawer open (dark) |  |
| st3 | iphone13-settings-light.png | iPhone13 settings bottom-sheet (light) |  |
| st3 | iphone13-settings-dark.png | iPhone13 settings bottom-sheet (dark) |  |
| st3 | iphone13-overflow-light.png | iPhone13 header overflow / chat menu (light) |  |
| st3 | iphone13-overflow-dark.png | iPhone13 header overflow / chat menu (dark) |  |
| st3 | iphone13-palette-light.png | iPhone13 command palette (light) |  |
| st3 | iphone13-palette-dark.png | iPhone13 command palette (dark) |  |
| st3 | iphone13-streaming-light.png | iPhone13 mid-stream "Thinking…" + Stop (light) |  |
| st3 | iphone13-streaming-dark.png | iPhone13 mid-stream "Thinking…" + Stop (dark) |  |
| st3 | iphone13-after-stream-light.png | iPhone13 settled turn + attribution + chips (light) |  |
| st3 | iphone13-after-stream-dark.png | iPhone13 settled turn + attribution + chips (dark) |  |
| st3 | vp390-welcome-light.png | vp390 welcome hero (light) |  |
| st3 | vp390-welcome-dark.png | vp390 welcome hero (dark) |  |
| st3 | vp390-drawer-light.png | vp390 nav drawer open (light) |  |
| st3 | vp390-drawer-dark.png | vp390 nav drawer open (dark) |  |
| st3 | vp390-settings-light.png | vp390 settings bottom-sheet (light) |  |
| st3 | vp390-settings-dark.png | vp390 settings bottom-sheet (dark) |  |
| st3 | vp390-overflow-light.png | vp390 header overflow / chat menu (light) |  |
| st3 | vp390-overflow-dark.png | vp390 header overflow / chat menu (dark) |  |
| st3 | vp390-palette-light.png | vp390 command palette (light) |  |
| st3 | vp390-palette-dark.png | vp390 command palette (dark) |  |
| st3 | vp390-streaming-light.png | vp390 mid-stream "Thinking…" + Stop (light) |  |
| st3 | vp390-streaming-dark.png | vp390 mid-stream "Thinking…" + Stop (dark) |  |
| st3 | vp390-after-stream-light.png | vp390 settled turn + attribution + chips (light) |  |
| st3 | vp390-after-stream-dark.png | vp390 settled turn + attribution + chips (dark) |  |

Manifest flags for review: welcome install-coachmark overlaps 4th suggestion chip on iphone13-welcome-light; drawer renders desktop "Collapse sidebar" chevron.

## ST4 — Dynamic feature states (12)

Desktop 1280×880, light, direct-BE FE for live streaming. md5 ground truth in `st4-dynamic/md5sums.txt`.

| stage | filename | intent | verdict |
| --- | --- | --- | --- |
| st4 | welcome.png | Empty conversation welcome hero (at rest) |  |
| st4 | streaming-midstream.png | Mid-stream: partial answer + Stop (■) control |  |
| st4 | after-stream.png | Settled turn + Rerouted/Fake·Fast/View-spend attribution + chips |  |
| st4 | web-search-status.png | Live "Searching the web…" status frame + spinner |  |
| st4 | web-search-sources.png | Expanded "1 query · 3 sources" panel + inline [1][2] citations |  |
| st4 | tool-approval-pause.png | HITL pause: "Needs approval" + Approve/Deny |  |
| st4 | tool-approved-result.png | Resumed tool call: "result · Complete · Approved" |  |
| st4 | deep-research-plan.png | Deep Research plan-approval gate + $0.202/$1.00 cost estimate |  |
| st4 | deep-research-fanout.png | Deep Research fan-out: 3-agent panel + synthesis answer |  |
| st4 | mermaid-diagram.png | Rendered mermaid flowchart (Start→End) + toolbar |  |
| st4 | json-mode.png | JSON-mode structured output + "{} JSON" chip |  |
| st4 | error-turn.png | Mid-stream provider error: partial kept + "Streaming failed" + Retry |  |

## ST5 — Accessibility media-emulation (22)

`emulateMedia` matrix on fresh contexts; 4 routes × 5 modes + 2 motion-proof frames.

| stage | filename | intent | verdict |
| --- | --- | --- | --- |
| st5 | welcome__default.png | Welcome — un-emulated baseline (= ST1 welcome-hero-light) |  |
| st5 | welcome__forced-colors.png | Welcome — forced-colors OS high-contrast |  |
| st5 | welcome__contrast-more.png | Welcome — prefers-contrast: more (hero atmosphere zeroed) |  |
| st5 | welcome__reduced-motion.png | Welcome — reduced-motion resting frame |  |
| st5 | welcome__color-scheme-dark.png | Welcome — system color-scheme dark |  |
| st5 | settings__default.png | Settings — baseline (= ST1 settings-panel-light) |  |
| st5 | settings__forced-colors.png | Settings — forced-colors |  |
| st5 | settings__contrast-more.png | Settings — prefers-contrast: more |  |
| st5 | settings__reduced-motion.png | Settings — reduced-motion (byte-identical to settings__default) |  |
| st5 | settings__color-scheme-dark.png | Settings — system color-scheme dark |  |
| st5 | palette__default.png | Command palette — baseline |  |
| st5 | palette__forced-colors.png | Command palette — forced-colors |  |
| st5 | palette__contrast-more.png | Command palette — prefers-contrast: more |  |
| st5 | palette__reduced-motion.png | Command palette — reduced-motion (byte-identical to palette__default) |  |
| st5 | palette__color-scheme-dark.png | Command palette — system color-scheme dark |  |
| st5 | mobile-thread__default.png | Mobile thread — baseline |  |
| st5 | mobile-thread__forced-colors.png | Mobile thread — forced-colors |  |
| st5 | mobile-thread__contrast-more.png | Mobile thread — prefers-contrast: more |  |
| st5 | mobile-thread__reduced-motion.png | Mobile thread — reduced-motion (byte-identical to mobile-thread__default) |  |
| st5 | mobile-thread__color-scheme-dark.png | Mobile thread — system color-scheme dark |  |
| st5 | motion-proof__welcome-stream__default.png | Reduced-motion proof — default mid-stream frame |  |
| st5 | motion-proof__welcome-stream__reduced-motion.png | Reduced-motion proof — reduced-motion mid-stream frame |  |

st5 manifest flags: `prefers-reduced-transparency` cannot be emulated by Playwright (no knob) — flagged, not captured.

---

## Curated artifacts in `/opt/cursor/artifacts/` (26 — all duplicates)

Every PNG below is md5-identical to the listed stage source. Verdict inherits
from the stage row; no independent re-review needed.

| filename | duplicate of (stage source) |
| --- | --- |
| auth-dialog__light.png | st2/auth-dialog__light.png |
| command-palette__dark.png | st2/command-palette__dark.png |
| command-palette__light.png | st2/command-palette__light.png |
| settings-general__dark.png | st2/settings-general__dark.png |
| settings-model-directory__light.png | st2/settings-model-directory__light.png |
| settings-shortcuts__dark.png | st2/settings-shortcuts__dark.png |
| st3-iphone13-after-stream-light.png | st3/iphone13-after-stream-light.png |
| st3-iphone13-drawer-light.png | st3/iphone13-drawer-light.png |
| st3-iphone13-overflow-light.png | st3/iphone13-overflow-light.png |
| st3-iphone13-palette-light.png | st3/iphone13-palette-light.png |
| st3-iphone13-settings-light.png | st3/iphone13-settings-light.png |
| st3-iphone13-streaming-light.png | st3/iphone13-streaming-light.png |
| st3-iphone13-welcome-dark.png | st3/iphone13-welcome-dark.png |
| st3-iphone13-welcome-light.png | st3/iphone13-welcome-light.png |
| st3-vp390-welcome-dark.png | st3/vp390-welcome-dark.png |
| st4-deep-research-fanout.png | st4/deep-research-fanout.png |
| st4-deep-research-plan.png | st4/deep-research-plan.png |
| st4-error-turn.png | st4/error-turn.png |
| st4-streaming-midstream.png | st4/streaming-midstream.png |
| st4-tool-approval-pause.png | st4/tool-approval-pause.png |
| st4-web-search-status.png | st4/web-search-status.png |
| welcome__color-scheme-dark.png | st5/welcome__color-scheme-dark.png |
| welcome__contrast-more.png | st5/welcome__contrast-more.png |
| welcome__forced-colors.png | st5/welcome__forced-colors.png |
| mobile-thread__forced-colors.png | st5/mobile-thread__forced-colors.png |
| settings__forced-colors.png | st5/settings__forced-colors.png |

(Also in `/opt/cursor/artifacts/`: `st3-mobile-manifest.md` — byte-identical copy
of `st3-mobile/manifest.md`; and an `assets/` dir — neither is a review target.)
