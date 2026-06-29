# GPT-5.5 screenshot re-review — ST3 mobile

- **Model:** gpt-5.5-high
- **Timestamp:** 2026-06-29 18:34:03 UTC
- **Scope:** Viewed all 28 PNGs in `web/test-results/audit/st3-mobile/`.
- **Inputs:** `web/test-results/audit/ISSUES.md`; `web/test-results/audit/REVIEW-INVENTORY.md` ST3 rows.

## Per-file verdicts

| file | verdict | notes |
| --- | --- | --- |
| `iphone13-welcome-light.png` | confirms ISSUE-1 | Install coachmark visibly overlaps/occludes the fourth suggestion chip. |
| `iphone13-welcome-dark.png` | confirms ISSUE-1 | Install coachmark visibly overlaps/occludes the fourth suggestion chip. |
| `iphone13-drawer-light.png` | confirms ISSUE-3 | Drawer shows the desktop collapse chevron and no dedicated visible close control. |
| `iphone13-drawer-dark.png` | confirms ISSUE-3 | Same drawer affordance issue is visible in dark theme. |
| `iphone13-settings-light.png` | clean | Mobile settings bottom sheet appears correctly laid out. |
| `iphone13-settings-dark.png` | clean | Mobile settings bottom sheet appears correctly laid out in dark theme. |
| `iphone13-overflow-light.png` | clean | Overflow menu state looks intentional; disabled export/share rows are distinguishable. |
| `iphone13-overflow-dark.png` | clean | Disabled overflow rows are visibly dimmer than the active "Temporary chat" row; does not confirm ISSUE-4. |
| `iphone13-palette-light.png` | clean | Command palette bottom sheet appears usable; lower content is naturally scrollable. |
| `iphone13-palette-dark.png` | clean | Command palette bottom sheet appears usable in dark theme. |
| `iphone13-streaming-light.png` | clean | Streaming state shows expected thinking indicator and stop control; coachmark does not create a new obstruction here. |
| `iphone13-streaming-dark.png` | clean | Streaming state shows expected thinking indicator and stop control in dark theme. |
| `iphone13-after-stream-light.png` | clean | Settled turn, attribution row, chips, coachmark, and composer remain readable. |
| `iphone13-after-stream-dark.png` | clean | Settled turn, attribution row, chips, coachmark, and composer remain readable in dark theme. |
| `vp390-welcome-light.png` | clean | Welcome chips and composer are unobstructed; no coachmark present. |
| `vp390-welcome-dark.png` | clean | Welcome chips and composer are unobstructed; no coachmark present. |
| `vp390-drawer-light.png` | confirms ISSUE-3 | Drawer shows the desktop collapse chevron and no dedicated visible close control. |
| `vp390-drawer-dark.png` | confirms ISSUE-3 | Same drawer affordance issue is visible in dark theme. |
| `vp390-settings-light.png` | clean | Mobile settings bottom sheet appears correctly laid out. |
| `vp390-settings-dark.png` | clean | Mobile settings bottom sheet appears correctly laid out in dark theme. |
| `vp390-overflow-light.png` | clean | Overflow menu state looks intentional; disabled export/share rows are distinguishable. |
| `vp390-overflow-dark.png` | clean | Disabled overflow rows remain distinguishable from the active row; does not confirm ISSUE-4. |
| `vp390-palette-light.png` | clean | Command palette bottom sheet appears usable; lower content is naturally scrollable. |
| `vp390-palette-dark.png` | clean | Command palette bottom sheet appears usable in dark theme. |
| `vp390-streaming-light.png` | clean | Streaming state shows expected thinking indicator and stop control. |
| `vp390-streaming-dark.png` | clean | Streaming state shows expected thinking indicator and stop control in dark theme. |
| `vp390-after-stream-light.png` | clean | Settled turn, attribution row, chips, and composer remain readable. |
| `vp390-after-stream-dark.png` | clean | Settled turn, attribution row, chips, and composer remain readable in dark theme. |

## Issue dispositions

| issue | disposition | rationale |
| --- | --- | --- |
| ISSUE-1 — Install coachmark occludes 4th suggestion chip | confirmed | Both iPhone 13 welcome screenshots show the install coachmark covering the fourth suggestion chip; vp390 welcome shots without the coachmark are clean. |
| ISSUE-3 — Mobile drawer shows desktop "Collapse sidebar", no visible close | confirmed | All drawer screenshots show the inherited collapse chevron as the only top-right control; no separate close button is visible. |
| ISSUE-4 — Disabled overflow items under-dimmed | refuted | In both iPhone 13 and vp390 dark overflow screenshots, disabled rows are noticeably dimmed relative to the active "Temporary chat" row and read as disabled. |

## NEW findings

None.
