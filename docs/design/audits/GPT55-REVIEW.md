# GPT-5.5 screenshot re-review — merged

- **Model:** gpt-5.5-high
- **Timestamp:** 2026-06-29 18:34:26 UTC (latest stage; stages ran 18:33:56–18:34:26 UTC)
- **Total images reviewed:** 96 stage PNGs (ST1 16 · ST2 18 · ST3 28 · ST4 12 · ST5 22).
- **Source reviews merged:** `GPT55-REVIEW-st1-st2.md`, `GPT55-REVIEW-st3.md`, `GPT55-REVIEW-st4.md`, `GPT55-REVIEW-st5.md`.
- **Inputs:** `ISSUES.md`, `REVIEW-INVENTORY.md`, per-stage `manifest.md` files, and the PNG contents themselves.

## Per-file verdicts (all 96)

| stage | filename | verdict | notes |
| --- | --- | --- | --- |
| st1 | 01-default-thread-light.png | clean | Desktop thread layout, reply metadata, chips, sidebar, and composer are unobstructed. |
| st1 | 01-default-thread-dark.png | clean | Dark thread state keeps readable text, attribution, chips, and composer affordances. |
| st1 | 02-tier-picker-light.png | clean | Tier picker popover is legible and anchored without clipping or overlap. |
| st1 | 02-tier-picker-dark.png | clean | Dark tier picker contrast and selected-state affordance read clearly. |
| st1 | 03-cost-detail-light.png | clean | Prefilled composer and token estimate render without crowding or clipped controls. |
| st1 | 03-cost-detail-dark.png | clean | Dark composer focus, send control, and token estimate are readable. |
| st1 | 04-sidebar-collapsed-light.png | clean | Collapsed desktop rail state keeps header/actions and centered hero intact. |
| st1 | 04-sidebar-collapsed-dark.png | clean | Dark collapsed rail state has no visible collision or lost control. |
| st1 | 05-welcome-hero-light.png | clean | Desktop welcome chips are unobstructed; no install coachmark overlap. |
| st1 | 05-welcome-hero-dark.png | clean | Dark desktop welcome chips and composer remain readable and unobstructed. |
| st1 | 06-suggestion-prefill-light.png | clean | Suggestion prefill appears correctly in composer with token count visible. |
| st1 | 06-suggestion-prefill-dark.png | clean | Dark suggestion prefill text and send affordance remain clear. |
| st1 | 08-temporary-banner-light.png | clean | Temporary banner and chat menu are legible; disabled exports are distinguishable. |
| st1 | 08-temporary-banner-dark.png | clean | Dark temporary menu and banner contrast are acceptable; disabled rows read as disabled. |
| st1 | 09-settings-panel-light.png | clean | Settings panel layout, controls, and spend cards are legible in light theme. |
| st1 | 09-settings-panel-dark.png | clean | Settings panel layout and controls are legible in dark theme. |
| st2 | command-palette__light.png | clean | Command palette overlay, active row, and keycaps are readable. |
| st2 | command-palette__dark.png | clean | Dark palette maintains contrast for rows, icons, and shortcuts. |
| st2 | account-menu__light.png | clean | Account menu is correctly positioned above the guest row and readable. |
| st2 | account-menu__dark.png | clean | Dark account menu contrast, borders, and item spacing are acceptable. |
| st2 | auth-dialog__light.png | clean | Sign-in dialog fields, button, focus ring, and secondary link are clear. |
| st2 | auth-dialog__dark.png | clean | Dark sign-in dialog fields, button, and link remain readable. |
| st2 | auth-dialog-create__light.png | clean | Create-account dialog layout and controls are clean in light theme. |
| st2 | auth-dialog-create__dark.png | clean | Dark create-account dialog has readable labels, inputs, and actions. |
| st2 | settings-general__light.png | clean | General settings spend controls and usage cards are readable. |
| st2 | settings-general__dark.png | confirms ISSUE-5 | The dark red spend-load error is present and still reads low-contrast. |
| st2 | settings-appearance__light.png | clean | Appearance section controls and switches are legible at the captured scroll position. |
| st2 | settings-appearance__dark.png | clean | Dark appearance section text, toggle states, and controls are readable. |
| st2 | settings-spend__light.png | clean | Spend section cards, chart area, and export buttons are readable in light theme. |
| st2 | settings-spend__dark.png | confirms ISSUE-5 | The dark red "Spend data could not be loaded." message remains low-contrast. |
| st2 | settings-shortcuts__light.png | clean | Shortcut rows and keycaps are readable and not clipped. |
| st2 | settings-shortcuts__dark.png | clean | Dark shortcut list keeps adequate row/keycap contrast. |
| st2 | settings-model-directory__light.png | clean | Model directory cards, provider badges, and pricing columns are readable. |
| st2 | settings-model-directory__dark.png | clean | Dark model directory cards and provider rows remain readable without clipping. |
| st3 | iphone13-welcome-light.png | confirms ISSUE-1 | Install coachmark visibly overlaps/occludes the fourth suggestion chip. |
| st3 | iphone13-welcome-dark.png | confirms ISSUE-1 | Install coachmark visibly overlaps/occludes the fourth suggestion chip. |
| st3 | iphone13-drawer-light.png | confirms ISSUE-3 | Drawer shows the desktop collapse chevron and no dedicated visible close control. |
| st3 | iphone13-drawer-dark.png | confirms ISSUE-3 | Same drawer affordance issue is visible in dark theme. |
| st3 | iphone13-settings-light.png | clean | Mobile settings bottom sheet appears correctly laid out. |
| st3 | iphone13-settings-dark.png | clean | Mobile settings bottom sheet appears correctly laid out in dark theme. |
| st3 | iphone13-overflow-light.png | clean | Overflow menu state looks intentional; disabled export/share rows are distinguishable. |
| st3 | iphone13-overflow-dark.png | refutes ISSUE-4 | Disabled overflow rows are visibly dimmer than the active "Temporary chat" row; does not confirm ISSUE-4. |
| st3 | iphone13-palette-light.png | clean | Command palette bottom sheet appears usable; lower content is naturally scrollable. |
| st3 | iphone13-palette-dark.png | clean | Command palette bottom sheet appears usable in dark theme. |
| st3 | iphone13-streaming-light.png | clean | Streaming state shows expected thinking indicator and stop control; coachmark does not create a new obstruction here. |
| st3 | iphone13-streaming-dark.png | clean | Streaming state shows expected thinking indicator and stop control in dark theme. |
| st3 | iphone13-after-stream-light.png | clean | Settled turn, attribution row, chips, coachmark, and composer remain readable. |
| st3 | iphone13-after-stream-dark.png | clean | Settled turn, attribution row, chips, coachmark, and composer remain readable in dark theme. |
| st3 | vp390-welcome-light.png | clean | Welcome chips and composer are unobstructed; no coachmark present. |
| st3 | vp390-welcome-dark.png | clean | Welcome chips and composer are unobstructed; no coachmark present. |
| st3 | vp390-drawer-light.png | confirms ISSUE-3 | Drawer shows the desktop collapse chevron and no dedicated visible close control. |
| st3 | vp390-drawer-dark.png | confirms ISSUE-3 | Same drawer affordance issue is visible in dark theme. |
| st3 | vp390-settings-light.png | clean | Mobile settings bottom sheet appears correctly laid out. |
| st3 | vp390-settings-dark.png | clean | Mobile settings bottom sheet appears correctly laid out in dark theme. |
| st3 | vp390-overflow-light.png | clean | Overflow menu state looks intentional; disabled export/share rows are distinguishable. |
| st3 | vp390-overflow-dark.png | refutes ISSUE-4 | Disabled overflow rows remain distinguishable from the active row; does not confirm ISSUE-4. |
| st3 | vp390-palette-light.png | clean | Command palette bottom sheet appears usable; lower content is naturally scrollable. |
| st3 | vp390-palette-dark.png | clean | Command palette bottom sheet appears usable in dark theme. |
| st3 | vp390-streaming-light.png | clean | Streaming state shows expected thinking indicator and stop control. |
| st3 | vp390-streaming-dark.png | clean | Streaming state shows expected thinking indicator and stop control in dark theme. |
| st3 | vp390-after-stream-light.png | clean | Settled turn, attribution row, chips, and composer remain readable. |
| st3 | vp390-after-stream-dark.png | clean | Settled turn, attribution row, chips, and composer remain readable in dark theme. |
| st4 | welcome.png | clean | Desktop welcome hero, suggestion chips, sidebar empty state, and composer render without overlap or clipping. |
| st4 | streaming-midstream.png | clean | Partial streamed text, thought label, and Stop control are visible and aligned. |
| st4 | after-stream.png | clean | Settled turns, attribution row, spend link, follow-up chips, and composer are readable and stable. |
| st4 | web-search-status.png | clean | Live web-search panel, running tool-call state, spinner, and Stop control render clearly. |
| st4 | web-search-sources.png | clean | Expanded sources panel, citations, source chip, attribution row, and actions are legible. |
| st4 | tool-approval-pause.png | clean | Approval gate shows input JSON plus Approve and Deny controls without crowding. |
| st4 | tool-approved-result.png | clean | Approved result state, status pills, attribution, and follow-up chips render consistently. |
| st4 | deep-research-plan.png | clean | Agent activity plan gate, decomposed plan, cost estimate, and approval controls are readable. |
| st4 | deep-research-fanout.png | clean | Fan-out panel, worker rows, synthesis row, merged answer, and actions fit the viewport. |
| st4 | mermaid-diagram.png | clean | Mermaid block renders as SVG with toolbar and zoom controls visible. |
| st4 | json-mode.png | clean | Structured output and JSON attribution chip are visible without invalid-state noise. |
| st4 | error-turn.png | clean | Partial answer, streaming-failed warning, Retry, Check status, and composer render cleanly. |
| st5 | welcome__default.png | clean | Baseline welcome hero renders correctly; no clipping, overflow, or contrast regression visible. |
| st5 | welcome__forced-colors.png | clean | Forced-colors repaint is visually distinct; controls, chips, sidebar search, and composer have visible real borders. |
| st5 | welcome__contrast-more.png | clean | Contrast-more shot is visually distinct from default; atmospheric effects are reduced and text remains legible. |
| st5 | welcome__reduced-motion.png | clean | Resting frame is acceptable; reduced-motion visual differences do not indicate a UI bug. |
| st5 | welcome__color-scheme-dark.png | clean | Dark scheme is visually distinct and coherent; hero, chips, sidebar, and composer remain readable. |
| st5 | settings__default.png | clean | Settings dialog baseline is complete and readable; no clipped controls or missing affordances. |
| st5 | settings__forced-colors.png | clean | Forced-colors settings dialog has visible outlines around the dialog, inputs, tab controls, cards, and buttons. |
| st5 | settings__contrast-more.png | clean | Contrast-more settings dialog remains readable and visually distinct from default. |
| st5 | settings__reduced-motion.png | clean | Byte-identical settled frame is expected for reduced motion; no bug indicated. |
| st5 | settings__color-scheme-dark.png | clean | Dark settings dialog is visually distinct and readable; controls remain visible. |
| st5 | palette__default.png | clean | Command palette baseline renders correctly with readable rows, icons, and shortcut pills. |
| st5 | palette__forced-colors.png | clean | Forced-colors palette is visually distinct; dialog border, row text, shortcuts, and footer remain visible. |
| st5 | palette__contrast-more.png | clean | Contrast-more palette remains readable with no layout or contrast regression visible. |
| st5 | palette__reduced-motion.png | clean | Byte-identical settled frame is expected for reduced motion; no bug indicated. |
| st5 | palette__color-scheme-dark.png | clean | Dark palette is visually distinct and coherent; selected row and shortcut pills remain legible. |
| st5 | mobile-thread__default.png | clean | Baseline mobile thread renders with contained user bubble, attribution row, chips, and composer. |
| st5 | mobile-thread__forced-colors.png | confirms ISSUE-2 | The user message text remains visible, but its bubble surface/container is missing in forced-colors, so the turn reads as floating text. |
| st5 | mobile-thread__contrast-more.png | clean | Contrast-more mobile thread remains visually distinct; bubble, composer, chips, and attribution are readable. |
| st5 | mobile-thread__reduced-motion.png | clean | Byte-identical settled frame is expected for reduced motion; no bug indicated. |
| st5 | mobile-thread__color-scheme-dark.png | clean | Dark mobile thread is visually distinct; user bubble, response, chips, and composer remain readable. |
| st5 | motion-proof__welcome-stream__default.png | clean | Default mid-stream frame renders the in-flight state; no unrelated visual regression visible. |
| st5 | motion-proof__welcome-stream__reduced-motion.png | clean | Reduced-motion proof is visually distinct from default, consistent with motion being applied differently; no bug indicated. |

## Prior issue dispositions (ISSUE-1 … ISSUE-5)

| issue | GPT-5.5 disposition | rationale |
| --- | --- | --- |
| ISSUE-1 — Install coachmark occludes 4th suggestion chip | **confirmed** | Both iPhone 13 welcome shots (`st3/iphone13-welcome-light.png`, `-dark.png`) show the install coachmark covering the fourth suggestion chip. The ST1 *desktop* welcome captures and `st3/vp390-welcome-*` (no coachmark) are clean — consistent with the issue being scoped to the short mobile viewport when the coachmark is present, not a desktop defect. |
| ISSUE-2 — User message bubble loses its container in forced-colors | **confirmed** | `st5/mobile-thread__forced-colors.png` shows the user message bubble losing its visible container under `forced-colors: active`; text stays visible but the turn reads as floating text. |
| ISSUE-3 — Mobile drawer shows desktop "Collapse sidebar", no visible close | **confirmed** | All four drawer shots (`st3/iphone13-drawer-{light,dark}.png`, `st3/vp390-drawer-{light,dark}.png`) show the inherited desktop collapse chevron as the only top-right control; no dedicated visible close button is present. |
| ISSUE-4 — Disabled overflow items under-dimmed | **refuted** | In both `st3/iphone13-overflow-dark.png` and `st3/vp390-overflow-dark.png`, disabled export/share rows are noticeably dimmer than the active "Temporary chat" row and read as disabled. The enabled/disabled distinction holds; the originally-flagged under-dimming is not observed. (The issue was logged as *uncertain*.) |
| ISSUE-5 — Dark-mode spend-error red low contrast | **confirmed** | `st2/settings-spend__dark.png` and `st2/settings-general__dark.png` both show the dark red "Spend data could not be loaded." error reading low-contrast against the dark surface; light-theme spend captures do not exhibit it. |

## NEW findings

None. No stage (ST1–ST5) surfaced any new defect beyond the five prior issues.

## Curated artifacts note

The 26 PNGs in `/opt/cursor/artifacts/` are **byte-identical (md5-verified) duplicates** of stage PNGs (per `REVIEW-INVENTORY.md`). They were **not** re-reviewed independently; each inherits the verdict of its stage source row above. No unique pixels exist to review, so they add no verdicts to the 96-image total.
