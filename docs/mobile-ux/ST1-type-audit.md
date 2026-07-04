# ST1 — Mobile type-size audit

Read-only audit of every Tailwind font-size utility in `web/src/components/**`,
scored against iOS-native comfortable minimums. No code was changed.

## Method

- Enumerated with ripgrep: `text-xs`, `text-2xs`, `text-sm`, `text-base`,
  `text-\[.*rem\]` across `web/src/components/**`.
- Root font-size is the browser default 16px (no `font-size` override on `html`
  in `web/src/app/globals.css`; only `text-size-adjust: 100%`), so 1rem = 16px.

### Token → px reference

| Utility | rem | px | Notes |
| --- | --- | --- | --- |
| `text-2xs` | 0.6875 | **11** | Custom token, `globals.css` `--text-2xs` |
| `text-xs` | 0.75 | **12** | Tailwind default |
| `text-[0.8rem]` | 0.8 | **12.8** | `button` `sm` size |
| `text-[0.8125rem]` | 0.8125 | **13** | `ai-disclosure` |
| `text-sm` | 0.875 | **14** | Tailwind default |
| `text-[0.9375rem]` | 0.9375 | **15** | desktop chat body / welcome chips |
| `text-base` | 1.0 | **16** | mobile input default |
| `text-[1.0625rem]` | 1.0625 | **17** | mobile chat body / bubbles |

### Flag thresholds (iOS comfortable minimums)

- **Primary / interactive** (list row, body copy, dialog body, button label,
  input, menu item, tab, link): flag when **mobile < 15px**.
- **Caption / metadata** (section eyebrow, meta caption, badge, footnote,
  count): flag when **mobile < 13px**.

An occurrence with a `md:` override that only changes the *desktop* size still
takes its *mobile* size from the base utility; the flag is always judged on the
mobile-rendered px.

### The existing mobile-first pattern to emulate

Three places already ship the correct "bigger on phone, denser on desktop" ramp.
Everything in the offender table below is measured against these:

| Reference | Mobile | Desktop | Source |
| --- | --- | --- | --- |
| `.chat-md` (assistant markdown) | 17px | 15px | `globals.css:772` — `text-[1.0625rem] md:text-[0.9375rem]` |
| User bubble / edit + composer textarea | 17px | 15px | `user-message.tsx:219,272`, `composer.tsx:1292` |
| Text inputs (iOS no-zoom pattern) | 16px | 14px | `text-base md:text-sm` — e.g. `sidebar.tsx:577,1578`, `auth-dialog.tsx:184` |

The input pattern is load-bearing: **16px mobile is the floor that stops iOS
Safari from auto-zooming the page on focus** (comments to that effect at
`sidebar.tsx:575`, `1577`, `2369`). Every text input in the app already follows
`text-base md:text-sm` — the offense is almost entirely in *non-input* chrome
(rows, captions, labels, buttons, badges) that was written desktop-first at a
flat `text-sm` / `text-xs` / `text-2xs` with **no mobile bump**.

---

## (a) Offender table

`md:?` column: `—` = no responsive override (mobile == desktop); otherwise the
desktop size is shown. **Bold px = the flagged mobile size.**

### Heavy offenders (the seven called out for close inspection)

#### `attribution-row.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 69 | metadata caption (model · cost · tokens) | **12** | 12 | — | ⚠ caption <13 |
| 75 | badge (substitution callout) | **11** | 11 | — | ⚠ caption <13 |

> Note: the public mirror `public-attribution-row.tsx:58` renders the same row at
> `text-sm` (14px) — the private one is 2px smaller for identical content.

#### `usage-meter.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 141 | badge / status pill (BYOK "billed to key") | **12** | 12 | — | ⚠ caption <13 |
| 165 | metadata caption (remaining credits + bar) | **12** | 12 | — | ⚠ caption <13 |

#### `sidebar.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 444 | **conversation row** (primary list text) | **14** | 14 | — | ⚠ interactive <15 |
| 485 / 503 | swipe-action labels (Pin / Delete) | **12** | 12 | — | ⚠ interactive <15 |
| 577 | rename input | 16 | 14 | text-sm | ✅ compliant |
| 636 | conv preview/subtitle caption | **12** | 12 | — | ⚠ caption <13 |
| 644 | conv meta row (time/status) | **12** | 12 | — | ⚠ caption <13 |
| 783 / 826 / 874 | section eyebrow (uppercase) | **12** | 12 | — | ⚠ caption <13 |
| 806 / 850 / 900 | command/action rows | **14** | 14 | — | ⚠ interactive <15 |
| 1517 | section eyebrow | **12** | 12 | — | ⚠ caption <13 |
| 1545 | new-chat button/row label | **14** | 14 | — | ⚠ interactive <15 |
| 1578 | search input | 16 | 14 | text-sm | ✅ compliant |
| 1601 | collapsed hint pill | **12** | 12 | — | ⚠ caption <13 |
| 1624 | collapsed nav row (interactive) | **12** | 12 | — | ⚠ interactive <15 |
| 1646 | label caption | **12** | 12 | — | ⚠ caption <13 |
| 1786 | empty-state body | **14** | 14 | — | ⚠ interactive <15 |
| 1815 / 1818 | body copy | **14** | 14 | — | ⚠ interactive <15 |
| 1833 | project toggle row | **12** | 12 | — | ⚠ interactive <15 |
| 1849 | count badge pill | **11** | 11 | — | ⚠ caption <13 |
| 1890 | section header | **12** | 12 | — | ⚠ caption <13 |
| 1913 | empty/caption | **12** | 12 | — | ⚠ caption <13 |
| 1926 | project row | **14** | 14 | — | ⚠ interactive <15 |
| 1937 | count caption | **12** | 12 | — | ⚠ caption <13 |
| 2015 | section header | **12** | 12 | — | ⚠ caption <13 |
| 2038 | caption | **12** | 12 | — | ⚠ caption <13 |
| 2061 | tag / list row | **14** | 14 | — | ⚠ interactive <15 |
| 2152 | empty-state body | **14** | 14 | — | ⚠ interactive <15 |
| 2167 / 2185 | section header row | **12** | 12 | — | ⚠ caption <13 |
| 2220 | avatar initials | **12** | 12 | — | ⚠ caption <13 |
| 2224 | account name (primary) | **14** | 14 | — | ⚠ interactive <15 |
| 2227 | account meta caption | **12** | 12 | — | ⚠ caption <13 |
| 2370 / 2466 | inputs | 16 | 14 | text-sm | ✅ compliant |

#### `follow-up-chips.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 78 | button label (suggestion chip) | **12** | 12 | — | ⚠ interactive <15 |

#### `command-palette.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 88 / 90 | search / select inputs | 16 | 14 | text-sm | ✅ compliant |
| 92 | filter input | **14** | 14 | — | ⚠ interactive <15 (also risks iOS zoom) |
| 619 / 640 / 659 / 694 / 722 | form label / body | **14** | 14 | — | ⚠ interactive <15 |
| 620 / 641 / 660 / 695 / 723 | field sub-label caption | **12** | 12 | — | ⚠ caption <13 |
| 744 | alert body | **14** | 14 | — | ⚠ interactive <15 |
| 752 / 762 | body | **14** | 14 | — | ⚠ interactive <15 |
| 783 | result title (list row) | **14** | 14 | — | ⚠ interactive <15 |
| 787 | result subtitle caption | **12** | 12 | — | ⚠ caption <13 |
| 799 | caption | **11** | 11 | — | ⚠ caption <13 |
| 814 / 821 | body / empty | **14** | 14 | — | ⚠ interactive <15 |
| 832 | section eyebrow | **12** | 12 | — | ⚠ caption <13 |
| 862 / 902 | command rows | **14** | 14 | — | ⚠ interactive <15 |
| 915 | row subtitle caption | **12** | 12 | — | ⚠ caption <13 |
| 921 | row shortcut hint | **12** | 12 | — | ⚠ caption <13 |
| 935 | footer hint | 11 | 11 | — | ✅ desktop-only (`hover:hover and pointer:fine` — hidden on touch) |

#### `settings-dialog.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 264 / 268 | form label | **14** | 14 | — | ⚠ interactive <15 |
| 271 | helper caption | **12** | 12 | — | ⚠ caption <13 |
| 281 | section eyebrow | **12** | 12 | — | ⚠ caption <13 |
| 300 | section title (h2) | **14** | 14 | — | ⚠ interactive <15 |
| 302 | helper caption | **12** | 12 | — | ⚠ caption <13 |
| 345 | segmented tab label | **12** | 12 | — | ⚠ interactive <15 |
| 396 / 475 / 748 | field label | **12** | 12 | — | ⚠ caption <13 |
| 403 / 482 / 755 | input prefix adornment | **12** | 12 | — | ⚠ caption <13 |
| 417 / 496 / 769 | number inputs | 16 | 14 | text-sm | ✅ compliant |
| 430 / 509 / 555 / 677 / 782 / 816 / 875 | helper captions | **12** | 12 | — | ⚠ caption <13 |
| 576 | select input | **14** | 14 | — | ⚠ interactive <15 |
| 607 / 641 | segmented tab label | **12** | 12 | — | ⚠ interactive <15 |
| 664 | form label | **14** | 14 | — | ⚠ interactive <15 |
| 710 | textarea | 16 | 14 | text-sm | ✅ compliant |
| 713 | char-count caption | **11** | 11 | — | ⚠ caption <13 |
| 813 / 872 | body / primary | **14** | 14 | — | ⚠ interactive <15 |
| 821 | caption | **12** | 12 | — | ⚠ caption <13 |
| 1052 | nav eyebrow | **11** | 12 | text-xs | ⚠ caption <13 **and inverted ramp** (grows on desktop) |
| 1065 | nav item row (primary) | **14** | 14 | — | ⚠ interactive <15 |
| 1088 | back-button label | **14** | 14 | — | ⚠ interactive <15 |
| 1115 | section eyebrow | **12** | 12 | — | ⚠ caption <13 |
| 1161 | tab / button label | **14** | 14 | — | ⚠ interactive <15 |
| 1200 | avatar initials | 14 | 14 | — | ✅ caption ≥13 (borderline) |
| 1206 | account name (primary) | **14** | 14 | — | ⚠ interactive <15 |
| 1207 | plan badge | **12** | 12 | — | ⚠ caption <13 |
| 1211 | email caption | **12** | 12 | — | ⚠ caption <13 |
| 1288 | billing alert | **12** | 12 | — | ⚠ interactive <15 (alert) |

#### `model-mode-picker.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 95 | trigger pill (model selector button) | **14** | 14 | — | ⚠ interactive <15 |
| 279 / 430 / 497 / 652 | section eyebrow (uppercase) | **11** | 11 | — | ⚠ caption <13 |
| 476 | body / caption | **12** | 12 | — | ⚠ caption <13 |
| 529 / 539 / 572 / 619 / 623 / 636 | item description captions | **11** | 11 | — | ⚠ caption <13 |
| 693 / 746 | menu item label (primary) | **14** | 14 | — | ⚠ interactive <15 |
| 695 / 752 | item description caption | **12** | 12 | — | ⚠ caption <13 |
| 779 | badge (uppercase) | **11** | 11 | — | ⚠ caption <13 |

### Shared UI primitives (one fix here cascades to many call sites)

#### `ui/button.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 7 | default button label | **14** | 14 | — | ⚠ interactive <15 |
| 25 | `xs` size button label | **12** | 12 | — | ⚠ interactive <15 |
| 26 | `sm` size button label | **12.8** | 12.8 | — | ⚠ interactive <15 |

#### `ui/badge.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 8 | base badge | **12** | 12 | — | ⚠ caption <13 |

#### `ui/dropdown-menu.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 68 | menu group label (header) | **12** | 12 | — | ⚠ caption <13 |
| 91 / 116 / 162 / 204 | menu item (interactive row) | **14** | 14 | — | ⚠ interactive <15 |
| 244 | shortcut hint caption | **12** | 12 | — | ⚠ caption <13 |

#### `ui/dialog.tsx` L204, `ui/drawer.tsx` L169

| Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- |
| dialog / drawer description body | **14** | 14 | — | ⚠ interactive <15 |

#### `ui/toast.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 165 | toast body | **14** | 14 | — | ⚠ interactive <15 |
| 195 | toast action button | **14** | 14 | — | ⚠ interactive <15 |

#### `ui/tooltip.tsx`

| Line | Role | Mobile | Desktop | md:? | Flag |
| --- | --- | --- | --- | --- | --- |
| 59 | tooltip body | **12** | 12 | — | ⚠ caption <13 (desktop-hover; low mobile impact) |

### Remaining chat components

| File:line | Role | Mobile | md:? | Flag |
| --- | --- | --- | --- | --- |
| `assistant-message.tsx:418` | body | **14** | — | ⚠ interactive |
| `assistant-message.tsx:497` | status line | **14** | — | ⚠ interactive |
| `assistant-message.tsx:512,530,563,670,726,764` | metadata captions | **12** | — | ⚠ caption |
| `assistant-message.tsx:660` | badge/pill | **12** | — | ⚠ caption |
| `assistant-message.tsx:717,745` | warning/alert body | **12** | — | ⚠ interactive |
| `assistant-message.tsx:758` | inline link | **12** | — | ⚠ interactive |
| `agentic-assistant-parts.tsx:130` | body | **14** | — | ⚠ interactive |
| `ai-disclosure.tsx:18` | disclosure caption | 13 | — | ✅ caption ≥13 |
| `activity-dialog.tsx:76` | section eyebrow | **12** | — | ⚠ caption |
| `activity-dialog.tsx:163,187,215,238,240,244,256` | body / list | **14** | — | ⚠ interactive |
| `activity-dialog.tsx:200` | caption | **12** | — | ⚠ caption |
| `activity-dialog.tsx:261` | caption | **11** | — | ⚠ caption |
| `byok-form.tsx:204,235,260` | body / label | **14** | — | ⚠ interactive |
| `byok-form.tsx:248` | provider select input | **14** | — | ⚠ interactive |
| `byok-form.tsx:276` | key input | 16→14 | text-sm | ✅ compliant |
| `byok-form.tsx:297,315,372` | captions | **12** | — | ⚠ caption |
| `auth-dialog.tsx:167,189` | form label | **14** | — | ⚠ interactive |
| `auth-dialog.tsx:184,207` | inputs | 16→14 | text-sm | ✅ compliant |
| `auth-dialog.tsx:229,243` | alert / body | **14** | — | ⚠ interactive |
| `web-search-panel.tsx:148,214` | caption | **12** | — | ⚠ caption |
| `web-search-panel.tsx:188` | body | **14** | — | ⚠ interactive |
| `user-message.tsx:219,272` | bubble / edit textarea | 17→15 | rem | ✅ compliant |
| `user-message.tsx:228,239` | edit action buttons | **14** | — | ⚠ interactive |
| `user-message.tsx:245` | alert caption | **12** | — | ⚠ caption |
| `user-message.tsx:280` | attachment chip | **12** | — | ⚠ caption |
| `typing-indicator.tsx:17` | status caption | **12** | — | ⚠ caption |
| `tool-part.tsx:118` | body | **14** | — | ⚠ interactive |
| `tool-part.tsx:145,158,255` | captions | **12** | — | ⚠ caption |
| `tool-part.tsx:308,320` | badges | **11** | — | ⚠ caption |
| `tool-group-panel.tsx:43` | body | **14** | — | ⚠ interactive |
| `tool-group-panel.tsx:61` | caption | **12** | — | ⚠ caption |
| `tier-picker.tsx:35` | trigger button | **12** | — | ⚠ interactive |
| `tier-picker.tsx:100,171` | captions | **12** | — | ⚠ caption |
| `tier-picker.tsx:104,175` | captions | **11** | — | ⚠ caption |
| `tier-picker.tsx:167` | menu item label | **14** | — | ⚠ interactive |
| `temporary-chat-banner.tsx:35` | banner status | **12** | — | ⚠ caption |
| `temporary-chat-banner.tsx:49` | banner button | **12** | — | ⚠ interactive |
| `template-picker-popover.tsx:149,164,176` | list row / body | **14** | — | ⚠ interactive |
| `template-picker-popover.tsx:167` | caption | **12** | — | ⚠ caption |
| `template-library-dialog.tsx:169,181,230,238,240,316,324` | body / label / list | **14** | — | ⚠ interactive |
| `template-library-dialog.tsx:171,320` | caption / inline code | **12** | — | ⚠ caption |
| `template-library-dialog.tsx:190,200,211,260,270,279` | inputs | 16→14 | text-sm | ✅ compliant |
| `subagent-panel.tsx:111` | body | **14** | — | ⚠ interactive |
| `subagent-panel.tsx:126,283,294,299,390,395` | body / captions | **12** | — | ⚠ caption |
| `subagent-panel.tsx:341` | badge | **11** | — | ⚠ caption |
| `spend-analytics-panel.tsx:113` | heading | **14** | — | ⚠ interactive |
| `spend-analytics-panel.tsx:150,239,265` | alert / rows | **14** | — | ⚠ interactive |
| `spend-analytics-panel.tsx:117,157,169,178,216,243,269` | captions | **12** | — | ⚠ caption |
| `spend-analytics-panel.tsx:137` | tab button | **12** | — | ⚠ interactive |
| `spend-analytics-panel.tsx:187,232,258` | section eyebrow | **12** | — | ⚠ caption |
| `spend-analytics-panel.tsx:159,221` | captions | **11** | — | ⚠ caption |
| `spend-analytics-panel.tsx:162,171` | numeric metric | 16 | — | ✅ ≥15 |
| `sources-panel.tsx:123` | trigger button | **12** | — | ⚠ interactive |
| `sources-panel.tsx:151,249` | captions | **11** | — | ⚠ caption |
| `sources-panel.tsx:255` | caption | **12** | — | ⚠ caption |
| `sources-panel.tsx:245` | list row | **14** | — | ⚠ interactive |
| `slash-commands-popover.tsx:167,185,197` | list row / body | **14** | — | ⚠ interactive |
| `slash-commands-popover.tsx:188` | caption | **12** | — | ⚠ caption |
| `memory-dialog.tsx:151,165,182,210,218,220,274` | body / label | **14** | — | ⚠ interactive |
| `memory-dialog.tsx:166` | caption | **12** | — | ⚠ caption |
| `memory-dialog.tsx:191,240` | textareas | 16→14 | text-sm | ✅ compliant |
| `shortcuts-dialog.tsx:108,188,292` | body / list | **14** | — | ⚠ interactive |
| `shortcuts-dialog.tsx:222` | kbd capture input | **12** | — | ⚠ interactive |
| `shortcuts-dialog.tsx:237` | alert caption | **12** | — | ⚠ caption |
| `shortcuts-dialog.tsx:318` | section eyebrow | **12** | — | ⚠ caption |
| `markdown-renderer.tsx:85` | mermaid error (mono body) | **14** | — | ⚠ interactive |
| `share-dialog.tsx:188,196,253` | body / label / alert | **14** | — | ⚠ interactive |
| `share-dialog.tsx:207` | url input | 16→14 | text-sm | ✅ compliant |
| `reasoning-panel.tsx:61` | disclosure trigger | **12** | — | ⚠ interactive |
| `reasoning-panel.tsx:124` | body | **14** | — | ⚠ interactive |
| `key-caps.tsx:33,37,49,56` | kbd hints | **12** | — | ⚠ caption (mostly desktop shortcut UI) |
| `model-directory-dialog.tsx:46` | section eyebrow | **12** | — | ⚠ caption |
| `model-directory-dialog.tsx:64,88,97,105,136,179` | captions | **12** | — | ⚠ caption |
| `model-directory-dialog.tsx:134,163,229,237,239,272` | list row / body / header | **14** | — | ⚠ interactive |
| `install-coachmark.tsx:130` | body | **14** | — | ⚠ interactive |
| `degraded-status-banner.tsx:71` | banner status | **12** | — | ⚠ caption |
| `degraded-status-banner.tsx:86` | banner button | **12** | — | ⚠ interactive |
| `compare-column.tsx:164` | header (list) | **14** | — | ⚠ interactive |
| `compare-column.tsx:170` | caption | **12** | — | ⚠ caption |
| `compare-column.tsx:184` | body | **14** | — | ⚠ interactive |
| `compare-view.tsx:41,50` | label caption | **12** | — | ⚠ caption |
| `compare-view.tsx:192` | tab button | **14** | — | ⚠ interactive |
| `message-actions.tsx:362,383,400,416,476,506` | captions | **12** | — | ⚠ caption |
| `message-actions.tsx:462,486` | section eyebrow | **11** | — | ⚠ caption |
| `chat-thread.tsx:3554,4197` | body | **14** | — | ⚠ interactive |
| `chat-thread.tsx:4117,4212` | inputs | 16→14 | text-sm | ✅ compliant |
| `welcome-screen.tsx:120` | eyebrow pill button | **12** | — | ⚠ interactive |
| `welcome-screen.tsx:164,178` | prompt chips (buttons) | 15 | — | ✅ interactive ≥15 |
| `platform-status-view.tsx:85,130,138,187` | body | **14** | — | ⚠ interactive |
| `platform-status-view.tsx:95,196` | buttons | **14** | — | ⚠ interactive |
| `platform-status-view.tsx:84` | brand wordmark | 16 | — | ✅ ≥15 |
| `platform-status-view.tsx:159` | caption | **12** | — | ⚠ caption |
| `public-conversation-view.tsx:124,157,163,297` | body | **14** | — | ⚠ interactive |
| `public-conversation-view.tsx:134,305,314` | buttons | **14** | — | ⚠ interactive |
| `public-conversation-view.tsx:123` | brand wordmark | 16 | — | ✅ ≥15 |
| `public-conversation-view.tsx:198` | user bubble | 17→15 | rem | ✅ compliant |
| `public-conversation-view.tsx:238` | caption | **12** | — | ⚠ caption |
| `public-attribution-row.tsx:58` | metadata caption | 14 | — | ✅ caption ≥13 |
| `public-attribution-row.tsx:73` | badge | **12** | — | ⚠ caption |

### Compliant reference occurrences (not offenders)

These already ride the mobile-first ramp and are the template for the fix:

- **Chat body / bubbles / composer** — `text-[1.0625rem] md:text-[0.9375rem]`
  (17→15): `globals.css:772` (`.chat-md`), `user-message.tsx:219,272`,
  `composer.tsx:1292`, `public-conversation-view.tsx:198`.
- **All text inputs** — `text-base md:text-sm` (16→14): `sidebar.tsx:577,1578,2370,2466`,
  `command-palette.tsx:88,90`, `settings-dialog.tsx:417,496,710,769`,
  `auth-dialog.tsx:184,207`, `byok-form.tsx:276`, `share-dialog.tsx:207`,
  `memory-dialog.tsx:191,240`, `template-library-dialog.tsx:190,200,211,260,270,279`,
  `chat-thread.tsx:4117,4212`.
- **Welcome prompt chips** — `text-[0.9375rem]` (15): `welcome-screen.tsx:164,178`.
- **Numeric metrics / brand wordmarks** — `text-base` (16):
  `spend-analytics-panel.tsx:162,171`, `platform-status-view.tsx:84`,
  `public-conversation-view.tsx:123`.

### Tally

- **Distinct flagged occurrences: ~200+** across 44 files.
- Two dominant anti-patterns account for nearly all of them:
  1. **`text-sm` with no `md:`** → 14px on both mobile and desktop for
     interactive rows, buttons, body, menu items, labels (should be 16→14).
  2. **`text-xs` / `text-2xs` with no `md:`** → 11–12px on both mobile and
     desktop for captions, eyebrows, badges, counts (should be 13→11/12).
- Only one *inverted* ramp exists (`settings-dialog.tsx:1052`,
  `text-2xs md:text-xs` — smaller on mobile than desktop), which is exactly
  backwards from the intended direction.

---

## (b) Proposed mobile-first type ramp

Bigger on the phone, denser on desktop via `md:` — mirroring the three existing
reference patterns. Interactive text sits at a 16px mobile floor (the iOS
no-zoom floor already proven by every input); captions bottom out at 13px mobile
(the caption comfortable minimum).

| Role token | Applies to | Mobile | Desktop | Tailwind pairing |
| --- | --- | --- | --- | --- |
| **list-row** | conversation rows, menu items, command/action rows, tabs, buttons, primary list text, form labels, dialog/drawer body | **16px** | 14px | `text-base md:text-sm` |
| **body** | dialog copy, descriptions, empty states, alerts, status lines | **16px** | 14px | `text-base md:text-sm` |
| **secondary** | item descriptions, supporting one-liners under a title | **15px** | 13px | `text-[0.9375rem] md:text-[0.8125rem]` |
| **caption** | metadata rows, helper text, counts, badges, timestamps | **13px** | 12px | `text-[0.8125rem] md:text-xs` |
| **section-eyebrow** | uppercase tracking-wide section headers / group labels | **13px** | 11px | `text-[0.8125rem] md:text-2xs` |

Rationale:

- **list-row / body → 16/14**: reuses the exact input pattern already in the
  codebase, so rows and inputs share one mobile size (16px). Interactive text at
  16px clears the iOS zoom trap and the comfortable minimum in one move; desktop
  stays at today's dense 14px.
- **secondary → 15/13**: for the "title + one-line description" pairs
  (`model-mode-picker`, `tier-picker`, sidebar conv preview) where the
  description should stay a notch under the title but still readable on a phone.
- **caption → 13/12**: the smallest *readable* mobile step. Lifts every 11–12px
  caption to the 13px floor while preserving today's compact 12px on desktop.
- **section-eyebrow → 13/11**: eyebrows can hold today's tiny 11px on the desktop
  (dense, uppercase, tracking-wide reads fine) but must climb to 13px on the
  phone. This also un-inverts `settings-dialog.tsx:1052`.

These can be expressed as three new size tokens plus reuse of existing ones:

```css
/* globals.css @theme inline — additions */
--text-body-mobile: 1rem;           /* 16 */
--text-secondary-mobile: 0.9375rem; /* 15 (already used as chat desktop) */
--text-caption-mobile: 0.8125rem;   /* 13 (already used by ai-disclosure) */
/* desktop steps reuse existing text-sm / text-xs / text-2xs */
```

---

## (c) Recommendation: shared utilities over per-component classes

**Fix with a small set of shared, responsive component utilities (plus the
shared UI primitives), not per-component `text-base md:text-sm` sprinkled at 200
call sites.** Rationale:

1. **The offense is systemic, not local.** ~200 occurrences collapse into five
   roles. Encoding those five roles once — the way `.chat-md` and `--text-2xs`
   are already encoded in `globals.css` — is the established precedent in this
   repo and keeps the ramp in one auditable place.
2. **Shared primitives are force multipliers.** `ui/button.tsx` (default/`xs`/`sm`),
   `ui/badge.tsx`, `ui/dropdown-menu.tsx` (item/label/shortcut), and
   `ui/dialog.tsx` + `ui/drawer.tsx` descriptions are single choke points. Making
   *these* responsive fixes dozens of downstream call sites (every dropdown row,
   every badge, every dialog description) with a handful of edits and zero
   per-call churn.
3. **Per-component classes drift.** 200 hand-edited `text-base md:text-sm`
   strings guarantee future inconsistency (someone will type `text-sm` again).
   A named utility (`.ui-list-row`, `.ui-caption`, `.ui-eyebrow`, …) is greppable
   and lints itself by convention.

Suggested shape (Tailwind v4 `@layer components`, same mechanism as `.chat-md`):

```css
@layer components {
  .ui-list-row  { @apply text-base md:text-sm; }               /* 16 → 14 */
  .ui-body      { @apply text-base md:text-sm; }               /* 16 → 14 */
  .ui-secondary { @apply text-[0.9375rem] md:text-[0.8125rem]; } /* 15 → 13 */
  .ui-caption   { @apply text-[0.8125rem] md:text-xs; }        /* 13 → 12 */
  .ui-eyebrow   { @apply text-[0.8125rem] md:text-2xs; }       /* 13 → 11 */
}
```

Rollout order (highest leverage first):

1. **Shared primitives** — `button.tsx`, `badge.tsx`, `dropdown-menu.tsx`,
   `dialog.tsx`/`drawer.tsx` descriptions. Biggest cascade, smallest diff.
2. **Heavy offenders** — `sidebar.tsx`, `settings-dialog.tsx`,
   `command-palette.tsx`, `model-mode-picker.tsx`, then the remaining chat
   panels, swapping raw `text-sm/xs/2xs` for the role utilities.
3. **Genuine one-offs** (e.g. mermaid error, keycap hints that only render on
   desktop) may keep bespoke classes — the utilities are for the recurring roles.

**Caveat — interactive text that is also a form input:** those already carry
`text-base md:text-sm`; folding them into `.ui-list-row` is a no-op but keeps the
16px iOS-no-zoom floor intact, so it is safe. Do **not** lower any input below
16px on mobile.
