# Simplified UI — binding spec

This spec governs the simplified draft of the Olune UI: what stays on screen, what goes, and what moves one step behind disclosure. The baseline is `current-ui.html`, a frozen render of the shipped UI. Every claim about the current UI was checked against that file's `<template id="view-…">` markup and against the baseline screenshots (1440×900 and 390×844, light and dark). Counts come from the baseline metrics for light desktop, all 35 views.

## 1. First principles

Olune exists so that a person can think with an AI. On every screen, the person's words and the model's answer are the protagonist. Everything else is there for one of three reasons:

- it starts the next thought (the composer);
- it keeps the person oriented (history, the current model);
- it keeps their trust (which model answered, what it cost, where data went, that this is an AI).

An element stays on screen only if it passes all four tests:

1. **Task.** It serves what the person is doing on this screen right now. If it is needed only sometimes, it moves one step behind disclosure.
2. **One path.** It is the only visible path to its action in this layout. A second visible path is cut or merged.
3. **Consequence.** Removing it would cause an error, a dead end, or a lost trust signal. The trust signals are AI disclosure, the served model, a substitution, cost or usage, and data handling.
4. **Cheapest form.** It takes the cheapest form that works: position, then space, then type, then text. An icon, border, badge, card, chip or helper sentence is allowed only when type and space cannot carry the meaning.

Failing test 1 means disclosure. Failing test 2 means merging into the surviving path. Failing test 4 means a plainer form. When the tests do not settle a case, subtract.

### Causes of complexity observed in the baseline

| Cause | Evidence in the baseline |
|---|---|
| Dialogs drawn over a fully live app | 27 of the 35 views are modals (dialogs, sheets, a drawer, a menu). They hold 724 of the 792 controls. Subtracting each dialog's own controls leaves about 19 controls and 18 icons per view in a blurred backdrop the user cannot operate, about 500 controls in all. The measured budget counts that backdrop, so the backdrop screens must shrink, not just the dialogs. |
| Duplicate paths | New chat ×2 on desktop (sidebar row, header pen). Search ×2 (sidebar input, header capsule). Advanced search ×4 (hover sidebar button, account menu, palette item, palette filter button). Select ×3 (sidebar button, row menu, account menu). Two sidebar-toggle controls. The model button rendered twice in the DOM. In compare mode, the composer picker beside two compare pickers. "Start your own chat" ×2 on share-unavailable. Wordmark ×2 on welcome. |
| An icon on every row | 21 palette row icons (20 actions, 1 recent chat). 83 icons on models, 48 of them check or minus glyphs in a capability matrix. Leading icons on settings tabs, prompt chips, follow-up chips and collection rows. |
| Keyboard-hint chips everywhere | 25 key chips in the palette, Ctrl K chips in the header, 27 in shortcuts. Footer hint strips in the palette and search-history. |
| Helper prose under every setting | Settings runs to 446 words. Nearly every row has a sentence restating its label, and every dialog has a subtitle restating its title. |
| Nested surfaces | Settings: a card inside the dialog, with the caps inside the "Platform credits" card. Models: tier lists inside provider cards. Status: headline in a card. Organize: a card around each radio group. |
| Too many scales | Settings: 14 type styles, 8 radii, 9 shadows. Welcome: 10 type styles, 4 shadows. |
| Glass and atmosphere | Glass header capsules and a glass composer. A magenta under-glow from `--accent-warm` (oklch chroma 0.19, a second saturated hue). A radial wash on welcome. A blurred backdrop behind every dialog. |
| Inconsistent primitives | Primary button: near-black in sign-in and share-dialog, black pill on share-unavailable, pale blue tint on shared and status, solid blue on 404. Danger varies by dialog: solid red on delete-conversation and delete-project, pale tint on delete-current-chat and delete-account; the split holds on phone too. new-project and palette-new-project are two dialogs with different copy, input style and disabled style. |
| Wrong or missing state | model-picker on phone shows no picker. settings-mobile opens over the open drawer. A guest is labeled "Free" with initials "GU". On shared, the substitution callout omits the requested model. |

## 2. Design system

### Type: 6 styles, 6 sizes

Display has a phone size, so there are six sizes in all (40, 34, 20, 16, 14, 12) and five on any one viewport. Sizes are in rem (16px root). The family is the system sans; code uses the system mono at Meta size.

| Style | Size / line-height | Weight | Use |
|---|---|---|---|
| Display | 40/44 (phone 34/40) | 400, Instrument Serif | Welcome greeting only |
| Title | 20/28 | 600 | Dialog and pane titles, page h1 |
| Body | 16/26 | 400 | Messages, composer, inputs, phone list rows |
| Label | 14/20 | 500 | Buttons, menu items, nav items, field labels, wordmark |
| Meta | 14/20 | 400 | Secondary text, attribution line, sidebar chat titles, code |
| Caption | 12/16 | 500 | Group headings ("Today", "Recent"), shortcut hints, timestamps |

No view may use a style outside these six. The welcome backdrops already spend Display, Label, Meta and Caption, and the thread backdrop spends Label, Meta, Caption and Body, so a dialog has room for Title plus one more. A one-off size or weight breaks the 6-per-view limit. Estimated total across the 35 views is about 160 type styles (baseline 325; ceiling 195): 1 on loading, 3–5 on the public pages, 4 on the base screens, and 5 on most modals.

The Instrument Serif greeting stays. It is type, not chrome, so it adds no control and no icon. It is spent on the one place the canon reserves for distinctiveness, the empty state. Once the wash, glow, chips and API-key pill are gone, it is what keeps that screen from reading as unfinished. Conditions:

- one line, on welcome only;
- loaded with `display: optional`, as in `web/src/app/layout.tsx` (the snapshot's `font-display: block` is a draft defect);
- falls back to the sans at Display size.

### Color: one accent, one danger, one notice

Contrast was computed from the oklch values (sRGB, WCAG 2.x). Every text pair passes AA at 4.5:1. Control outlines and the focus ring pass 3:1.

| Token | Light | Dark | Role and measured contrast |
|---|---|---|---|
| `canvas` | oklch(0.985 0.003 250) #f9fafc | oklch(0.17 0.010 255) #0d1014 | Page and sidebar |
| `surface` | oklch(0.995 0.002 250) #fcfdff | oklch(0.215 0.010 255) #161a1e | Composer, dialogs, sheets, menus |
| `subtle` | oklch(0.955 0.005 250) #eef0f3 | oklch(0.255 0.010 255) #202328 | User bubble, selected row, secondary button, code |
| `line` | oklch(0.90 0.005 250) #dbdee1 | oklch(0.33 0.010 255) #32363b | Decorative hairlines only |
| `line-strong` | oklch(0.64 0.008 250) #898d91 | oklch(0.55 0.010 250) #6d7277 | Input and switch outlines: 3.3 light / 3.6 dark on surface |
| `text` | oklch(0.20 0.006 250) #141619 | oklch(0.95 0.004 250) #eceff1 | 17.3 / 16.5 on canvas; 15.9 / 13.6 on subtle |
| `text-muted` | oklch(0.48 0.009 250) #5a5e63 | oklch(0.72 0.010 250) #a0a5ab | 6.3 / 7.7 on canvas; 5.7 / 6.4 on subtle |
| `accent` | oklch(0.53 0.17 252) #006cc9 | oklch(0.72 0.15 250) #52a9fe | Primary fill, links, focus ring, selected check: 5.1 / 7.7 on canvas |
| `on-accent` | oklch(0.99 0 0) | oklch(0.17 0.010 255) | Text on accent and danger fills: 5.1 / 7.7 |
| `danger` | oklch(0.55 0.20 27) #cc2827 | oklch(0.70 0.17 22) #f66c6d | Irreversible actions only: 5.2 / 6.6 on canvas |
| `notice-text` | oklch(0.45 0.09 65) #774914 | oklch(0.86 0.08 80) #edcc95 | Substitution line and data-risk facts, text only: 7.3 / 12.4 on canvas; 6.9 / 9.2 on `notice-bg` |
| `notice-bg` | oklch(0.965 0.035 80) #fff1da | oklch(0.29 0.045 75) #382810 | Fill for the near-limit usage line only |
| `scrim` | oklch(0.20 0.01 250 / 0.32) | oklch(0 0 0 / 0.56) | Behind modals, no blur |

The substitution line gets text color but no fill. A substitution is information about an answer that already succeeded, so it should read as part of the answer's footer, not as a warning box. The `notice-bg` fill is reserved for usage limits, the one case where the next request may fail.

Cut from the palette:

- `--accent-warm`, and every gradient wash and glow;
- the near-black `--primary` button, because the accent is the only primary;
- the accent tint on the user bubble, which becomes `subtle`;
- `success`, because healthy status reads in neutral text.

A view uses at most four text colors: `text`, `text-muted`, and two of `accent`, `on-accent`/`danger`, `notice-text`.

### Space, radius, elevation, controls

| Topic | Decision |
|---|---|
| Spacing scale | 4, 8, 12, 16, 24, 32, 48, 64 |
| Spacing in use | Between messages 32; between groups 32; between rows 4 on desktop, 0 on phone (rows are 44px); dialog padding 24 desktop / 16 phone; phone gutters 16 |
| Layout | Sidebar 264px; message column and composer at most 720px (about 75 characters of Body); header 56px; composer 24px above the safe area |
| Radius (3 values) | `r-sm` 8px: inputs, menu rows, list rows, notice lines, code. `r-lg` 16px: composer, bubbles, menus, dialogs, sheets, palette, phone frame. `r-full` (literal 9999px everywhere, never `50%`): buttons, chips, switches and their thumbs, the drag handle, segmented controls, meter bars. Switch thumbs have no shadow. The phone drawer is square, because a one-sided radius would count as a fourth value. Phone sheets are inset 8px from the side and bottom edges (plus the safe area) with `r-lg` on all four corners. |
| Elevation (2 levels) | `e1` raised (composer, menus, popovers, toasts): `0 1px 2px oklch(0.2 0.01 250/.06), 0 8px 24px oklch(0.2 0.01 250/.08)`. `e2` modal (dialogs, sheets, drawer, palette): `0 16px 48px oklch(0.2 0.01 250/.18)`. Dark uses the same offsets with `oklch(0 0 0/.45)` and `/.6`. Everything else is flat. |
| Phone frame | When a phone view is drawn at desktop width, its frame is a 1px `line` hairline with `r-lg` and no shadow. Otherwise frame + `e2` sheet + `e1` composer would be three shadows. Each framed phone document carries its own `lang` and `<title>`; in the baseline those two missing attributes were most of the serious accessibility findings. |
| Buttons | 36px tall desktop, 44px phone. Variants: primary (`accent` fill), secondary (`subtle` fill), danger (`danger` fill, the same on every viewport and every dialog), quiet (no fill, `subtle` on hover). |
| Icon buttons | 32px desktop, 44px phone; icons 16px / 20px at 1.5 stroke |

**Dialogs, menus, and the sidebar stay flat.** The welcome column, the thread column, and the composer keep the product's main-screen theme and are not restyled. Both columns use `--welcome-ambient` over `--hero-gradient`. The composer on both is the stronger glass, with the resting hero glow.

- The header has no surface; its buttons sit on the canvas over a 16px canvas-colored fade.
- The composer is `surface` with a `line` hairline and `e1`.
- Modals are `surface` with `e2` over the scrim.
- There is no `backdrop-filter` anywhere, so `prefers-reduced-transparency` needs no special path.

This deviates from the glass guidance in `00-principles.md` and `01-foundations.md`, so it needs a decision entry in `04-rationale.md` before it ships.

### Icon, motion and focus policy

- **Icons allowed:**
  - icon-only controls with a learned meaning and an accessible name: sidebar toggle, menu, close, back, more (ellipsis), plus, send, stop, copy, search filters, show password;
  - the check on the selected option of a single-select list;
  - a chevron on a control that opens or expands something.
- **Icons forbidden:**
  - an icon beside a text label (menus, nav, buttons, chips, palette rows);
  - an icon that repeats adjacent text (the callout info icon, the status check);
  - a capability matrix drawn in glyphs;
  - empty-state illustrations.
- Lucide stays the only family, colored by `currentColor`.
- **Hidden at rest means `opacity: 0`, never `visibility` or `display`.** Hover-revealed controls (desktop message actions, chat-row and project/tag-row menus, user-message Edit and Copy) set `opacity: 0` on the control and on its `svg` (`.reveal, .reveal svg { opacity: 0 }`), so they stay in the tab order. The hide is gated by `@media (hover: hover)`, never by viewport width (`UI_STANDARDS.md` UI-TOUCH-6). They reveal on `:hover` and `:focus-within` of the row or message, and on their own `:focus-visible`. On touch, message actions and row menus are always visible; user-message Edit and Copy also stay reachable by long-press. The swipe Pin/Delete tray stays `visibility: hidden` until swiped, because the row menu is its keyboard path.
- **Motion:**
  - 120ms for color, hover, press and focus; 200ms for menus, popovers, dialogs, sheets, the drawer and disclosures. One curve: `cubic-bezier(0.2, 0, 0, 1)`.
  - Welcome fades in once: 320ms with 8px of rise.
  - Streaming has one cadence: the "Thinking…" shimmer and the pre-token pulse share a 1.4s rhythm and stop on the frame the stream ends.
  - Cut: the hover micro-lift, the composer halo, all ambient motion.
  - Reduced motion: every transition is instant, the shimmer becomes static "Thinking…", and welcome renders already in place.
- **Focus:**
  - `:focus-visible` shows a 2px `accent` outline at 2px offset, following the element's radius. It uses `outline`, never `box-shadow`, and never appears on hover.
  - On accent and danger fills, the offset leaves a canvas gap so the ring stays visible.
  - The focused composer turns its hairline `accent`. This is the one brand moment.
  - A scroll region gets `tabindex="0"` only when it holds no focusable child (axe `scrollable-region-focusable`): the models pane and the shortcuts list. Each counts as one control. The thread's message list needs none, because it holds "Thought for" and the message actions.

## 3. Global chrome

### Sidebar (desktop, and the phone drawer)

Desktop order, top to bottom: toggle and "Olune" on one 56px row; "New chat"; "Search  Ctrl K"; "Projects and tags" (when shown); date groups with chat rows; the account button pinned to the bottom. Rows are 36px, in Label for actions and Meta for chat titles.

| Element (current) | Decision | Reason |
|---|---|---|
| "OLUNE" small-caps wordmark | REWORD to "Olune" in Label, plain text | One identity mark; the header copy is cut |
| Collapse button, plus a separate "Open sidebar" button in the header | MERGE into one toggle fixed at top-left | Two controls for one action |
| "+ New chat" | KEEP, text only | Primary action; the icon repeats the label |
| Search input "Search conversations" | MERGE into a "Search" row that opens the palette, with Caption "Ctrl K" (⌘K on Mac) | The palette already searches chats |
| "Advanced search" and "Select" (hover-revealed) | CUT | The palette filter button and the row menu's Select are the single paths |
| Empty state: icon and three lines | REWORD to one Meta line, "No chats yet" | The composer is the call to action |
| "Collections" disclosure with icon | REWORD to "Projects and tags", chevron only; shown once any chat, project or tag exists | Nothing to organize before then; the palette still creates both |
| Project and tag rows: icon, count "0" | CUT the icon; show the count only above 0. The tag row stays a filter button; the project row becomes a button that filters to the project; each has a hover-revealed menu (always visible on touch) | Type carries it; the row menu is the keyboard path to rename and delete |
| Date group "Today" | KEEP, Caption | Orientation in long history |
| Chat row, hover menu, swipe Pin/Delete on touch | KEEP | The only per-chat actions |
| Active row: accent stripe and tint | REWORD to `subtle` fill only | The accent is reserved for action and focus |
| Account: "GU" avatar, "Guest", "Free", ellipsis | MERGE into one button: "Guest" over Meta "1,000 guest credits left this month" (wraps to two lines rather than truncating); signed in: name over "N credits left this month" | Usage legible at rest; guests have no plan or initials |
| Account-menu "Advanced search", "Select conversations" | CUT. The menu keeps Sign in / Create account (guest) or Sign out, plus Settings | Duplicate paths |

On phone, the account button and its usage line live in the drawer, so remaining usage is one step away (menu). The near-limit line above the composer covers the case where it matters.

### Header

| Element | Decision | Reason |
|---|---|---|
| Centered "Olune" title (welcome) | CUT | Brand stays off the working surface |
| Glass capsule with search, Ctrl K chips, more | CUT capsule and chips | The search path lives in the sidebar |
| Search icon | KEEP only on desktop with the sidebar collapsed; CUT on phone | Phone search sits one step away in the drawer, opened by the button beside it |
| New chat pen icon | KEEP only on phone thread and on desktop with the sidebar collapsed | Appears only where the sidebar row is not visible |
| Chat menu (ellipsis) | KEEP | Temporary chat, Share…, Copy chat, Download as ▸ (Markdown, Word, PDF). On an empty chat, only Temporary chat |

### Composer

| Element | Decision | Reason |
|---|---|---|
| Textarea "Message Olune…" | KEEP | The task |
| "+" menu (attach, photo, prompt template, dictation) | KEEP | Only path to attachments |
| Model button "Auto ⌄", rendered twice in the DOM | KEEP one instance. Accessible name "Model Auto, reasoning Auto. Change." | PRD 07 §6.2: show the tier before send; the name keeps the reasoning setting that the visible label omits |
| Send / Stop in one slot | KEEP; Stop uses the `subtle` fill, never red | Neutral control |
| Glass, magenta under-glow, halo | CUT | Replaced by `surface`, `e1` and the focus hairline |
| Near-limit notice (new, conditional) | ADD one line in `notice-bg` / `notice-text` with `r-sm` above the composer, only at warning, critical or exhausted. Guest: "50 guest credits left this month · Create account". Signed-in Free: "50 credits left this month · Upgrade" | PRD 07 §6.3: call out the limit before a request fails |

## 4. Per-view spec

### How controls are counted (binding)

The budget is the **measured rule**: every visible interactive element in the rendered view, including the backdrop app behind a dialog, inert or not. Visible means a non-empty box, not `display: none`, not `visibility: hidden`, and opacity above 0.05. Scrolled-out content still counts. The backdrop stays `inert` under the scrim for users, but the budget counts it, so every modal names its backdrop:

| Backdrop | Screen (desktop unless noted) | Visible controls | Controls | Icons |
|---|---|---|---|---|
| W0 | Welcome, no chats | Toggle, New chat, Search, Account; chat menu; textarea, +, model, send | 9 | 5 |
| W1 | Welcome, one chat | W0 + "Projects and tags" + 1 chat row | 11 | 6 |
| WC | W1 with "Projects and tags" open, empty | W1 + "+ Project" + "+ Tag" | 13 | 8 |
| WR | Welcome with project "Cap 9597" and tag "t3875", no chats | W0 + "Projects and tags" + "+ Project" + "Cap 9597" row + "+ Tag" + "t3875" row | 14 | 8 |
| T | Thread | Sidebar 6; chat menu; message-list region; "Thought for 1s"; composer 4 | 13 | 7 |
| P0 | Phone welcome | Menu, chat menu; composer 4 | 6 | 5 |

The settings family (settings, activity, memory, templates, models, shortcuts) sits over W0. Row menus, message actions and the swipe tray are hidden at rest and are not counted. The project row is text, but it is counted as one control to keep a margin. Each view's count below is **measured = own + backdrop**.

Every view keeps to at most 6 type styles, 2 shadows (`e1`, `e2`), 3 radii and 4 text colors.

### 4.1 Core screens

**welcome** — start a thought. Measured 18 → 9 (phone 14 → 6); icons 20 → 5.

- **KEEP:** "Got an idea?" in Display; the AI disclosure `role=note` in Meta, directly below the greeting, copy unchanged; the composer.
- **CUT:** the three starter chips and the 4th prompt; the "Connect your API key" pill, which moves to Settings › Account; the radial wash; the under-glow.
- **Why the chips go (test 2, One path):** each chip is a second visible path to "send a message", and typing the same words does the same thing. This is the same rule that cuts the follow-up chips in thread. The chips also speak for the product rather than for the person, and losing them causes no error, dead end or lost trust signal. The greeting, the disclosure and the placeholder carry the empty state. This deviates from the "small set of prompt cards" in `02-patterns.md`, `UI_STANDARDS.md` UI-STATE-7 ("3–4 prompt cards") and PRD 06 §4, so all three need amending with a `04-rationale.md` entry before it ships. Desktop showed 4 chips, phone 3; across welcome and the views drawn over a welcome backdrop the cut is about 78 controls.
- **Layout:** sidebar on the left. On desktop, the greeting, the disclosure and the composer form one group centered at 40% of the column height; after the first send the composer settles to the bottom (200ms, instant under reduced motion). On phone the header has only menu and chat menu, the greeting sits at 35% of the height, and the composer stays at the bottom in thumb reach.

**thread** — read the answer and continue. Measured 23 → 13 (phone 18 → 11); icons 25 → 7 (phone 9).

- **KEEP:**
  - the user bubble (`subtle`); "Thought for 1s ⌄" in Caption; the answer in Body;
  - the attribution line in Meta, always visible: "Fake · Fast" (served model · tier). It appends "· your key" for BYOK, and "· Answered without live sources" when search was requested but no sources resolved;
  - Copy and More on every assistant message. More holds Regenerate, Helpful, Not helpful, Read aloud ▸ (Play/Stop, Slower, Faster, Voice), Continue, Branch in new chat, View spend, Regenerate with ▸ (tiers, then providers);
  - Jump to latest, only when scrolled away.
- **Action placement:** one footer row under each answer. The attribution text, or the substitution line that replaces it, sits on the left; Copy and More follow it 8px to its right on the same row. On desktop, Copy and More are hidden at rest on every message, including the latest. They appear on hover or `:focus-within` of the message, per `03-anti-patterns.md` §F ("One disclosure rule for both desktop and touch"). On phone they are always visible at 44px, and they drop to their own row only if the text wraps.
- **MERGE:** the separate "Fast" label goes into the substitution line.
- **REWORD:** the substitution callout becomes one text-only line in `notice-text` (no fill, no icon) that replaces the attribution line: "Requested Auto · Served Fake (Fast) · Auto chose a cheaper model". Reason copy comes from the PRD 07 §5 summaries. The "· your key" and "· Answered without live sources" suffixes still append to it.
- **CUT:** the callout's info icon and box; the user message's "Branch in new chat" (the assistant's More already has it); the follow-up chips (typing does the same).
- **Layout:** one 720px column, 32px between turns. User-message Edit and Copy appear on hover or focus on desktop and on long-press on phone. The message list is a region labeled "Messages".

**loading** — wait. Measured 0 → 0; icons 1 → 0.

- **CUT:** the spinner icon.
- **KEEP:** "Loading Olune…" in Meta, centered, pulsing its opacity at the streaming cadence (static under reduced motion).

### 4.2 Standalone public pages

These four pages share one shell: the wordmark "Olune" as plain Label text at top-left, at most one action at the right, and a 560px content column 64px below the header. On all four, CUT the theme toggle (they follow the system theme), the "· status" and "· shared chat" suffixes (the h1 says it), and the wordmark as a link (the right-hand action is the way back).

On phone: a 56px header with the wordmark at the left and the action at the right (a 44px quiet or primary button); the column runs full width inside 16px gutters, starting 24px below the header. share-unavailable and not-found center their block vertically; status and shared are top-aligned; shared messages run full width with no bubble inset beyond the gutter.

| View | Job | Elements after the change | Measured | Icons |
|---|---|---|---|---|
| status | Is the platform healthy? | Title "All systems operational"; Meta "Requests are completing normally."; Meta "Last 15 minutes: 0 requests, 0 errors."; Caption "Updated Nov 3, 2026, 4:53 PM · Platform-wide, not your account."; quiet "Back to chat" at the header right. CUT the card, check icon and 3-column stat grid. Degraded colors only the title: `notice-text`, or `danger` for an outage | 3 → 1 | 2 → 0 |
| shared | Read someone's chat | Title = chat name; Caption "Shared chat · read-only"; messages as in thread, with reasoning disclosure, attribution line and substitution line (now naming the requested model, which "Downgraded by router…" omits); primary "Start your own chat" at the header right. No cost, tokens or message actions | 4 → 2 | 3 → 1 |
| share-unavailable | Explain a dead link | Centered Title "This shared chat is no longer available"; Meta "The link may have been revoked or never existed. Ask the person who shared it for a new link."; primary "Start your own chat". CUT the icon and the duplicate header button | 4 → 1 | 2 → 0 |
| not-found | Recover from a bad URL | Title "Page not found"; Meta "This page doesn't exist or has moved."; primary "Back to chat". CUT the "404" eyebrow; the centered wordmark moves to the header | 2 → 1 | 0 → 0 |

### 4.3 Rules shared by every modal

- **Containers:** desktop dialogs are 400 (sm), 560 (md) or 760 (lg) wide. Phone dialogs are inset sheets with a drag handle. All use `surface`, `e2` and the scrim, with no blur and no subtitle that restates the title.
- **Two-button footer:** no X; Esc, a scrim click and Cancel close the dialog. Desktop puts Cancel left and the action right. Phone stacks full-width buttons, action first and Cancel second. Destructive dialogs open with focus on Cancel; name dialogs open with focus in the input, and Enter submits.
- **Single action or no footer** (sign-in, settings, shortcuts, and single-action phone sheets; two-button phone sheets follow the rule above): keep an X labeled "Close", unless the single action is itself Done (organize), which closes the dialog.
- **Focus** is trapped while open and returns to the launcher on close.
- **One noun:** "chat" everywhere in UI copy. "Conversation" is retired.

### 4.4 Name and confirm dialogs

Jobs: the new-* and rename-* views name a project or tag. The delete-* views confirm an irreversible deletion of a named object.

- **Name dialog** (sm): Title; a visible Label "Name"; an input with a `line-strong` outline; footer [Cancel] [Create | Save]. Create is disabled until the trimmed name is non-empty; Save until the name changes. All four helper sentences are cut, including the two different explanations of what a project is. Own controls: 3.
- **Confirm dialog** (sm): Title "Delete <thing>?"; Meta body that quotes the object's name, says what survives, and ends "This can't be undone."; footer [Cancel] [Delete] with the danger fill on every viewport and every dialog. Own controls: 2.

| View | Launcher → backdrop | Copy after the change | Measured | Icons |
|---|---|---|---|---|
| new-project | Sidebar "Projects and tags" › "+ Project" → WC | "New project" · Name · Create | 22 → 16 | 20 → 8 |
| palette-new-project | Palette "New project" → W1 | Identical dialog; focus returns to the composer | 22 → 14 | 18 → 6 |
| new-tag | Sidebar "+ Tag" → WC | "New tag" · Name · Create | 22 → 16 | 20 → 8 |
| palette-new-tag | Palette "New tag" → W1 | Identical dialog; focus returns to the composer | 22 → 14 | 18 → 6 |
| rename-project | "Cap 9597" row menu › Rename → WR | "Rename project", prefilled · Save | 24 → 17 | 25 → 8 |
| rename-tag | "t3875" row menu › Rename → WR | "Rename tag", prefilled · Save | 25 → 17 | 27 → 8 |
| delete-project | "Cap 9597" row menu › Delete → WR | "Delete project?" — "Cap 9597" will be permanently deleted. Its chats are kept and moved out of the project. This can't be undone. | 23 → 16 | 25 → 8 |
| delete-tag | "t3875" row menu › Delete → WR | "Delete tag?" — "t3875" will be permanently deleted and removed from every chat. The chats are kept. This can't be undone. | 24 → 16 | 27 → 8 |
| delete-conversation | Chat row menu › Delete → W1 | "Delete chat?" — "Brief thread on your request" will be permanently deleted. This can't be undone. | 21 → 13 | 18 → 6 |
| delete-current-chat | Palette, or Ctrl Shift Backspace on the open chat → T | Same copy; afterwards the user lands on welcome | 28 → 15 | 26 → 7 |
| delete-account | Settings › Privacy & data › "Delete account…" → W1 | "Delete account?" — Your account and all your chats will be permanently deleted. This can't be undone. Label "Type DELETE to confirm", input, then [Cancel] [Delete account], disabled until the input matches (own 3) | 22 → 14 | 18 → 6 |

The palette-launched views stay distinct screens with their own ids. Each differs from its sidebar twin only in launcher, backdrop (W1 instead of WC) and focus return; the dialog is identical. The same holds for delete-conversation (W1) and delete-current-chat (T).

### 4.5 Account and sharing dialogs

**sign-in and create-account** (sm, over W1) — sign a guest in, or create an account. Measured 24 → 17 each (own 6); icons 19 → 8.

- **KEEP:** Title; Email; Password with "Show password" (eye); the primary submit; the switch line "New here? Create an account" or "Have an account? Sign in"; the X.
- **REWORD:** one Meta line. Sign in: "Sync your chats and use your own API key." Create account: "Keep your chats and use your own API key."
- **Fix:** the primary button changes from near-black to `accent`. On phone the dialog is an inset sheet.

**share-dialog** (sm, over T) — create a public link. Measured 27 → 15 (own 2); icons 27 → 7.

- **KEEP:** Title "Share chat"; one Meta line carrying the public-share notice: Anyone with the link can read "Brief thread on your request". Cost and usage details are never included.
- **Footer:** [Cancel] [Create link].
- **CUT:** the link icon on the button; the second paragraph (merged into the line above); the X.
- **After creation** (a state, not a view): a read-only URL field, [Copy link], and a quiet "Stop sharing".

**organize-conversation** (sm, over W1) — file one chat. Measured 23 → 14 (own 3); icons 20 → 6.

- **REWORD:** Title "Organize chat" with the chat name in Meta. The two radio cards become two labeled selects that apply immediately: "Keep this chat" (Use default, 30 days, 90 days) and "Project" (None, then each project).
- **REPLACE:** the X becomes [Done], which closes the dialog (§4.3).
- **CUT:** the section cards and the check icons.

### 4.6 Command palette and search

**command-palette** (md, over W1) — find any action or chat. Measured 41 → 22 (own 11); icons 40 → 7.

- **Placement:** desktop, top edge at 20vh, max height 60vh, with the list scrolling under a pinned input. On phone it is an inset sheet.
- **KEEP:**
  - the input in Body, placeholder "Search chats and actions";
  - the "Search filters" icon button inside it, which opens search-history with the current query;
  - Captions "Recent" and "Actions";
  - desktop shortcut hints as right-aligned Caption text ("Ctrl Shift O").
- **Rows:** 36px (44px on phone), Label text, `r-sm`. The active row has a `subtle` fill and is tracked with `aria-activedescendant`; the first row is active on open, and arrow keys move it. There is no other selected style.
- **CUT:** all 22 row icons; all key chips; hints on phone; the footer hint strip (its text stays as the dialog's screen-reader description); the "Advanced search" item.
- **Empty query** shows up to 3 Recent chats and 8 Actions: New chat, Compare models, New project, New tag, Settings, Usage & spend, Keyboard shortcuts, Switch theme.
- **MOVE behind typing** (shown only on a matching query): Focus composer, Toggle sidebar, Toggle dictation, Copy last response, Copy last code block, Delete current chat, Custom instructions, Memory, Templates, Models, Activity, Use your own API key, Search with filters.

**search-history** (md, over W1) — filter chat history. Measured 26 → 17 (own 6); icons 18 → 7.

- **KEEP:** back (chevron-left, "Back to commands"); the query input.
- **MERGE:**
  - Model and Project stay selects; only Cost and Date change.
  - "Cost (USD)" min/max becomes one "Cost" select: Any, Under $0.01, $0.01–$0.10, Over $0.10, Custom range…. Custom reveals min and max.
  - Date from/to becomes one "Date" select: Any time, Past week, Past month, Past year, Custom range…. Custom reveals two date inputs.
- **Layout:** back and the input share the top row. Below it the four selects form a 2×2 grid (Model, Project / Date, Cost), 12px gaps, each with a Caption label above. Results follow under a `line` hairline: 44px rows with the chat title in Label and one Meta line "Fast · Nov 3 · Cap 9597" (tier · date · project). The active row uses the palette's `subtle` fill.
- **CUT:** the footer hint strip.
- **REWORD:** the empty text becomes "Type to search your chats."

### 4.7 Model choice and compare

**model-picker** (desktop menu anchored to the composer, `e1`, over W1) — pick the tier and modes for the next message. Measured 27 → 18 (own 7; phone 14 over P0); icons 22 → 8.

- **KEEP:**
  - Caption "Model";
  - four rows in Label + Meta: "Auto — Picks the best-value model for each message", "Fast — Fake · lowest cost", "Smart — Fake", "Pro — Fake", with the check on the selected row;
  - switches "Web search" and "Deep Research". Deep Research keeps the Meta line "Runs research agents in parallel; slower and uses more credits.";
  - "Advanced ⌄", holding reasoning effort and JSON output.
- **CUT:** "Attachments" on every row (show "No attachments" only when a tier lacks them); the "CHEAPEST" badge, which becomes Meta text; the globe, telescope and braces icons; the Web search description.
- **MOVE:** JSON output into Advanced.
- **Fix:** the phone view renders no picker today. On phone it is the same inset sheet as model-reasoning.

**model-reasoning** (phone sheet over P0) — the same choice on touch. Measured 25 → 14 (own 8); icons 15 → 8.

- **REWORD:** Title "Model"; the description is cut.
- **Content:** identical to model-picker, with switches at the right and 44px rows; keep the X and the drag handle.
- **Fix:** Advanced is clipped below the fold today. The sheet scrolls with its title pinned.

**compare** (a screen, not a modal) — send one prompt to two models side by side. Measured 14 → 13 (phone 11 → 9); icons 17 → 7.

- **MERGE:** the "Compare Auto vs Fast" bar becomes the column headers. Each header is a picker button in Label: "Auto ⌄", "Fast · Fake ⌄".
- **REPLACE:** in compare mode, the composer's model button becomes a quiet "Exit compare". Today there is no visible exit; the palette toggle is the only one.
- **KEEP:** "Waiting for your prompt…" in Meta.
- **Layout:** desktop shows two equal columns in a 960px width, 32px apart, with no rules. On phone, a two-segment "Auto | Fast" switch picks the visible column, and that column's header picker changes its model.

### 4.8 Settings

Settings is an lg dialog over W0, 760 × min(640, 85vh), with no description under "Settings".

- **Left rail:** 8 text-only items in Label, the selected one filled `subtle`: Account, Usage & spend, Preferences, Privacy & data, Activity, Memory, Templates, Models.
- **Close:** the X at top right.
- **Pane:** a Title, then groups 32px apart under Caption headings. Each row has a Label on the left, its control on the right, and at most one Meta helper line, only when the label cannot predict the effect.
- **No cards** inside the dialog.
- **Shortcuts** leaves Settings for its own dialog; it is reference material, not a setting.

The old General pane splits into four panes:

| Pane | Contents |
|---|---|
| Account | Identity ("Guest", or email and plan) · usage meter "1,000 guest credits left this month" (signed in: "N credits left this month") as `role="progressbar"` with `aria-valuetext` (UI-STATE-6) and a thin bar colored `text`, `notice-text` near the limit, `danger` when exhausted · guest: primary "Create account" + quiet "Sign in"; signed in: "Upgrade" + "Sign out" · "Use your own API key ⌄" reveals the BYOK form inline; BYOK users see "Billed to your key" |
| Usage & spend (the PRD 07 §6.1 Spend hub) | Window select (Last 7 / 30 / 90 days) · "$0.00 spent in the last 30 days", with "est." whenever confidence is not exact · Meta "Includes regenerated and deleted messages." with a "How this is counted ⌄" disclosure holding the surviving-messages figure · daily rows only for days with spend, otherwise "No spend in this window." · "Monthly limit" and "Per-chat limit" inputs that save on Enter or blur, with one helper "Platform-key usage pauses at a limit. Leave empty for none." · "Export ⌄" (CSV, JSON) |
| Preferences | Theme select (System, Light, Dark) · Default model select · "Send with Enter" switch · "Show reasoning expanded" switch · "Custom instructions ›" and "Project defaults ›" subpages · "Keyboard shortcuts" link (desktop) |
| Privacy & data | "Temporary chats by default" switch · "Keep saved chats" select (30 days, 90 days, Forever) · "Advanced privacy ›" · "Export your data" secondary button · "Delete account…" quiet button in `danger` text |

| View | Job; pane shown and its elements | Own | Measured | Icons |
|---|---|---|---|---|
| settings | Reach account and preferences. Account (guest): Create account, Sign in, Use your own API key | 12 | 54 → 21 | 37 → 7 |
| activity | Audit data access and where messages were processed. Title "Activity"; Meta "Only you can see this." · Caption "Where your messages were processed": "Appears after your first chat." and a quiet link "Choose a different route" (opens Models) · Caption "Account activity": "Nothing recorded yet." CUT the shield icon | 10 | 28 → 19 | 28 → 6 |
| memory | Control what Olune remembers. Title "Memory"; Meta "Facts Olune can use in new chats. Never used in temporary chats." · "Use memory" switch, description cut · "Add a fact" input + [Add], disabled until text · list, or "No facts yet." | 12 | 31 → 21 | 28 → 6 |
| templates | Keep reusable prompts. Title "Templates"; Meta "Reusable prompts. Use {{placeholders}} for the parts you fill in." · secondary "New template" reveals Title, Body, Description (optional) and [Cancel] [Save] inline · list, or "No templates yet." CUT the always-open form | 10 | 31 → 19 | 28 → 6 |
| models | Compare provider data handling before choosing a route. Title "Models and data" in a scrolling `tabindex="0"` pane · one block per provider: heading ("DeepSeek"); Meta status ("Available · used by Auto"); one fact line ("Data stored in China · may train on your data unless you opt out · retention not disclosed · no zero-retention option"), text-only `notice-text` when the route may train on your data or stores it outside US/EU; tier rows "Fast · DeepSeek V4 Flash · Web search", listing only the capabilities a tier has, in words · "Coming soon: Gemini, Grok (xAI)" as one Meta line. CUT badges, cards, shield and database icons, and all 48 check/minus glyphs | 10 | 28 → 19 | 83 → 6 |
| settings-mobile | Pick a settings section on phone. Phone sheet "Settings" with X; the 8 rail items as 44px Body rows with no icons, chevrons or card; opens over P0 with the drawer closed | 9 | 30 → 15 | 32 → 6 |

On phone, settings, activity, memory, templates and models show their pane as a page pushed inside the sheet, with a back button labeled "Settings". Each phone pane's own count is the desktop own count minus the 8 rail items plus 1 for back, over P0.

**shortcuts** (md, over W0) — keyboard reference. Measured 29 → 12 (own 3: X, Customize, the scrolling list); icons 27 → 6.

- **KEEP:** Title "Keyboard shortcuts"; a quiet "Customize" at the top right of the body; the X; group Captions General, Navigation, Editing.
- **REWORD:** each row is a Meta label with the keys at the right as plain Caption mono text ("Ctrl+Shift+O").
- **CUT:** the 27 key chips, the subtitle, the settings rail.
- **Reachable from:** Ctrl /, the palette, Preferences.

### 4.9 Navigation drawer

**sidebar** (phone drawer over P0) — navigate on touch. Measured 21 → 10 (own 4); icons 19 → 6 (X plus P0's 5, which stay visible under the drawer and count).

- **Drawer:** square, 85% wide (at most 320px), `e2`.
- **Contents, top to bottom:** "Olune" and X; "New chat"; "Search" (opens the palette); "Projects and tags" once a chat, project or tag exists; date groups; the account button with its usage line. Rows are 44px Body.
- **CUT:** the empty-state icon and the extra lines.

### 4.10 Measured totals (light desktop)

Controls: 792 → **478** (−40%; ceiling 530). Icons: 774 → **207** (−73%). Type styles: 325 → about 160 (ceiling 195). The 52-control margin is the room for later additions; a change that pushes the total past 530 must cut elsewhere first.

| View | Measured | View | Measured | View | Measured |
|---|---|---|---|---|---|
| welcome | 9 | settings | 21 | delete-account | 14 |
| thread | 13 | activity | 19 | new-project | 16 |
| status | 1 | memory | 21 | palette-new-project | 14 |
| shared | 2 | templates | 19 | new-tag | 16 |
| not-found | 1 | models | 19 | palette-new-tag | 14 |
| sign-in | 17 | shortcuts | 12 | share-unavailable | 1 |
| command-palette | 22 | search-history | 17 | sidebar | 10 |
| share-dialog | 15 | create-account | 17 | settings-mobile | 15 |
| model-picker | 18 | organize-conversation | 14 | model-reasoning | 14 |
| compare | 13 | delete-conversation | 13 | rename-project | 17 |
| delete-current-chat | 15 | delete-project | 16 | rename-tag | 17 |
| delete-tag | 16 | loading | 0 | | |

## 5. Guardrails that must survive

| Guardrail (source) | Today | After the change |
|---|---|---|
| AI-interaction disclosure (EU AI Act Art. 50(1); noted in PRD 07 §6.4) | welcome `p role=note` "You're chatting with an AI assistant…" | Same node and copy, directly under the greeting, desktop and phone |
| Served model and tier on every assistant message, without hover (§6.1, AC 1) | "Fast" label; the model appears only inside the callout | Attribution line "Fake · Fast", always visible, Meta at 6.3:1; also on shared. Only Copy and More hide at rest, never the attribution |
| Substitution callout names requested, served and reason (§5, §6.1) | "Rerouted from Auto → Fake · Downgraded by router…"; shared omits the requested model | "Requested Auto · Served Fake (Fast) · Auto chose a cheaper model", text-only `notice-text`, never `danger`, announced by the status region; same on shared |
| View spend on every finished message (AC 9) | Message More menu | Unchanged: More › View spend opens Usage & spend; More is reachable by hover, focus or touch. No inline cost in the thread |
| Usage remaining legible; guest cap and sign-up path (§6.3) | Settings only; the sidebar says "Free" | "1,000 guest credits left this month" on the account row at rest (phone: one step away in the drawer); near-limit `notice-bg` line above the composer with "Create account" for guests and "Upgrade" for signed-in Free; meter in Settings › Account; BYOK shows "Billed to your key" |
| Estimates labeled (§6.1, §7.2) | Spend panel | "est." beside any non-exact figure in Usage & spend and in model prices |
| Destructive confirmations explicit | Named object and "can't be undone"; danger fill varies by dialog | §4.4 confirm pattern: quoted name, what survives, "This can't be undone.", danger fill on every dialog and viewport, focus on Cancel, typed DELETE for the account |
| Public share strips cost and tokens (§6.4) | share-dialog second paragraph | share-dialog line "Cost and usage details are never included."; shared renders no cost or tokens |
| Activity log; "where your messages were processed" (§6.5) | Settings tab Activity | Settings › Activity; palette "Activity"; Models linked from it |
| Ungrounded answers marked (§4.3, §7.8) | Not in these views | Attribution suffix "· Answered without live sources" in Meta, not an error |
| At most one privacy banner (03-anti-patterns) | — | Temporary chat shows one Meta line above the messages, "Temporary chat · not saved". Nothing stacks with it |
| Keyboard reach and visible focus | Mostly; hover-only controls | Everything is in the tab order; hover-revealed controls appear on `:focus-within`; Ctrl K opens the palette, Ctrl / opens shortcuts; modals trap and restore focus; the 2px accent outline is never suppressed |
| Names on icon-only controls | Present | "Toggle sidebar", "Open menu", "New chat", "Search", "Chat menu", "Add files and more", "Send message" / "Stop", "Copy", "More actions", "Close", "Back to commands" / "Back to settings", "Search filters", "Show password"; the model button is "Model Auto, reasoning Auto. Change." |
| Every current task stays possible | — | §6. Nothing is more than one step from its new home |

## 6. Removed-capability ledger

| Removed or moved | Where it lives now |
|---|---|
| Header search capsule and Ctrl K chips (desktop, sidebar open) | Sidebar "Search" row, which opens the palette; a header search icon when the sidebar is collapsed; Ctrl K unchanged |
| Header New chat while the sidebar is visible | Sidebar "New chat"; the header icon returns when the sidebar is collapsed and on phone thread |
| Phone header search icon | Drawer › "Search"; Ctrl K |
| Sidebar inline filter of the chat list | The palette lists matching chats as you type |
| Sidebar, account-menu and palette "Advanced search" | The palette's "Search filters" button; typing "filter" surfaces "Search with filters" |
| Sidebar and account-menu "Select" | Chat row menu › Select, which enters bulk mode with that row checked |
| "Projects and tags" before any chat, project or tag exists | Palette › New project / New tag; the section appears with the first of them |
| Welcome "Connect your API key" | Settings › Account › "Use your own API key"; palette "Use your own API key" |
| Welcome starter chips (all four) and follow-up chips | Dropped (§4.1, test 2). Typing the same words does the same thing |
| Copy and More counted at rest on desktop (the baseline hid them by container opacity only) | The same controls on hover or `:focus-within` of the message; always visible on touch |
| Read aloud with speed and voice | More › Read aloud ▸ (Play/Stop, Slower, Faster, Voice), unchanged |
| User-message "Branch in new chat" | Assistant More › Branch in new chat |
| JSON output switch | Model picker › Advanced |
| 13 palette actions in the empty state | Shown on a matching query (§4.6) |
| Key chips; footer hint strips | Plain Caption hints on desktop; the shortcuts dialog; screen-reader descriptions |
| Search-history paired cost and date inputs | "Custom range…" in the Cost and Date selects |
| Settings description, tab icons, nested cards | Dropped (decoration) |
| General pane | Account, Usage & spend, Preferences, Privacy & data (§4.8) |
| Shortcuts tab | Its own dialog: Ctrl /, palette, Preferences link |
| Cumulative-vs-surviving explanation | Usage & spend › "How this is counted" |
| 31 zero-spend daily rows | "No spend in this window."; rows appear for days with spend |
| Two Save buttons for limits | Save on Enter or blur, with a polite "Saved" status message |
| 7d/30d/90d buttons; retention buttons; theme cycle button | One select each |
| Export CSV and Export JSON buttons | One "Export" menu |
| Always-open template form | "New template" reveals it inline |
| Models badges, icons, "Default-eligible" | Text: "Available · used by Auto"; capabilities in words |
| "Coming soon" provider cards | One line: "Coming soon: Gemini, Grok (xAI)" |
| Organize radio cards and X | Two selects with immediate apply, plus Done |
| X on two-button dialogs | Cancel, Esc, a scrim click |
| Theme toggle on status, shared, share-unavailable | Follows the system theme; signed-in users set it in Preferences |
| Wordmark link; duplicate "Start your own chat" | The single right-hand action on each standalone page |
| Guest "Free" badge, "GU" initials, account ellipsis | The account row button itself; the plan shows only for signed-in users |
| Glass, blur, gradient wash, magenta glow, hover lift, row accent stripe, composer halo, callout box | Dropped (decoration). The focus hairline, the `subtle` selection and `notice-text` carry the state |
