# GPT-5.5 screenshot re-review — ST1/ST2

- model: gpt-5.5-high
- timestamp: 2026-06-29 18:34:11 UTC

## Per-PNG verdicts

| filename | verdict | notes |
| --- | --- | --- |
| st1-desktop/01-default-thread-light.png | clean | Desktop thread layout, reply metadata, chips, sidebar, and composer are unobstructed. |
| st1-desktop/01-default-thread-dark.png | clean | Dark thread state keeps readable text, attribution, chips, and composer affordances. |
| st1-desktop/02-tier-picker-light.png | clean | Tier picker popover is legible and anchored without clipping or overlap. |
| st1-desktop/02-tier-picker-dark.png | clean | Dark tier picker contrast and selected-state affordance read clearly. |
| st1-desktop/03-cost-detail-light.png | clean | Prefilled composer and token estimate render without crowding or clipped controls. |
| st1-desktop/03-cost-detail-dark.png | clean | Dark composer focus, send control, and token estimate are readable. |
| st1-desktop/04-sidebar-collapsed-light.png | clean | Collapsed desktop rail state keeps header/actions and centered hero intact. |
| st1-desktop/04-sidebar-collapsed-dark.png | clean | Dark collapsed rail state has no visible collision or lost control. |
| st1-desktop/05-welcome-hero-light.png | clean | Desktop welcome chips are unobstructed; no install coachmark overlap. |
| st1-desktop/05-welcome-hero-dark.png | clean | Dark desktop welcome chips and composer remain readable and unobstructed. |
| st1-desktop/06-suggestion-prefill-light.png | clean | Suggestion prefill appears correctly in composer with token count visible. |
| st1-desktop/06-suggestion-prefill-dark.png | clean | Dark suggestion prefill text and send affordance remain clear. |
| st1-desktop/08-temporary-banner-light.png | clean | Temporary banner and chat menu are legible; disabled exports are distinguishable. |
| st1-desktop/08-temporary-banner-dark.png | clean | Dark temporary menu and banner contrast are acceptable; disabled rows read as disabled. |
| st1-desktop/09-settings-panel-light.png | clean | Settings panel layout, controls, and spend cards are legible in light theme. |
| st1-desktop/09-settings-panel-dark.png | clean | Settings panel layout and controls are legible in dark theme. |
| st2-dialogs/command-palette__light.png | clean | Command palette overlay, active row, and keycaps are readable. |
| st2-dialogs/command-palette__dark.png | clean | Dark palette maintains contrast for rows, icons, and shortcuts. |
| st2-dialogs/account-menu__light.png | clean | Account menu is correctly positioned above the guest row and readable. |
| st2-dialogs/account-menu__dark.png | clean | Dark account menu contrast, borders, and item spacing are acceptable. |
| st2-dialogs/auth-dialog__light.png | clean | Sign-in dialog fields, button, focus ring, and secondary link are clear. |
| st2-dialogs/auth-dialog__dark.png | clean | Dark sign-in dialog fields, button, and link remain readable. |
| st2-dialogs/auth-dialog-create__light.png | clean | Create-account dialog layout and controls are clean in light theme. |
| st2-dialogs/auth-dialog-create__dark.png | clean | Dark create-account dialog has readable labels, inputs, and actions. |
| st2-dialogs/settings-general__light.png | clean | General settings spend controls and usage cards are readable. |
| st2-dialogs/settings-general__dark.png | confirms ISSUE-5 | The dark red spend-load error is present and still reads low-contrast. |
| st2-dialogs/settings-appearance__light.png | clean | Appearance section controls and switches are legible at the captured scroll position. |
| st2-dialogs/settings-appearance__dark.png | clean | Dark appearance section text, toggle states, and controls are readable. |
| st2-dialogs/settings-spend__light.png | clean | Spend section cards, chart area, and export buttons are readable in light theme. |
| st2-dialogs/settings-spend__dark.png | confirms ISSUE-5 | The dark red "Spend data could not be loaded." message remains low-contrast. |
| st2-dialogs/settings-shortcuts__light.png | clean | Shortcut rows and keycaps are readable and not clipped. |
| st2-dialogs/settings-shortcuts__dark.png | clean | Dark shortcut list keeps adequate row/keycap contrast. |
| st2-dialogs/settings-model-directory__light.png | clean | Model directory cards, provider badges, and pricing columns are readable. |
| st2-dialogs/settings-model-directory__dark.png | clean | Dark model directory cards and provider rows remain readable without clipping. |

## Prior issue disposition for ST1/ST2

- ISSUE-1: refuted for ST1 desktop welcome captures; all four desktop suggestion chips are unobstructed and no install coachmark is present. Not otherwise in ST2 scope.
- ISSUE-2: not applicable to ST1/ST2; forced-colors mobile thread is ST5 scope.
- ISSUE-3: not applicable to ST1/ST2; mobile drawer is ST3 scope.
- ISSUE-4: not applicable to ST1/ST2; mobile overflow is ST3 scope. Desktop temporary-chat overflow in ST1 does not show the same under-dimming concern.
- ISSUE-5: confirmed in `st2-dialogs/settings-general__dark.png` and `st2-dialogs/settings-spend__dark.png`; not present in light-theme spend captures.

## New findings

- None.
