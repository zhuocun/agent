# UI Standards

This document is the explicit, checkable bar that any screen of this product must clear. It is not a design direction (that is `00-principles.md` through `04-rationale.md`) and not a product spec (that is `docs/prd/`); it is the **review instrument** those two produce — one numbered, falsifiable clause per rule, each with the canon it derives from and the concrete check that decides pass or fail. Use it three ways: as the checklist a reviewer runs against a PR that touches a rendered surface; as the acceptance list a new component must clear before it is considered done; and as the citation source in review comments, so a disagreement resolves against a clause ID instead of taste. A clause that cannot be decided without interpretation is a defect in this document — report it rather than guessing.

---

## 0. How to read a clause

Every clause has a stable ID (`UI-<AREA>-<n>`), a strength marker, and exactly three parts.

- **Assertion** — one testable sentence. A reviewer says pass or fail with no interpretation.
- **Source** — the repo canon clause or external criterion it derives from, cited by file and section. Never a paraphrase standing in for a citation.
- **Verify** — the concrete check: a Playwright probe sketch, a computed-style assertion, a grep, a command, or an explicitly manual step.

**Strength.** `[must]` means a screen that fails it is a defect and does not ship. `[should]` means a deviation requires a recorded entry in `docs/design/04-rationale.md` naming the principle it is in tension with (the deviation protocol in `02-patterns.md`, "Closing").

**Citation form.** `§3.2` is a numbered heading. `§7 AC 4` is item 4 of a numbered acceptance-criteria list under §7 — those lists have no sub-headings, so they are cited by item, not as `§7.4`. `§8 open question 2` follows the same convention.

**Precedence when sources disagree.** PRDs win on concrete values (tokens, ratios, component states, acceptance criteria); `docs/design/*` wins on direction; `docs/ux-best-practices/*` wins on external rationale and review checklists — this ordering is stated in `docs/ux-best-practices/README.md` ("Canonical position") and `docs/design/README.md` ("Canonical position"). Where repo canon and external canon (WCAG, Apple HIG) conflict, **repo canon rules** and the clause says so explicitly. Section 15 is the standing register of every conflict and silence found while writing this document.

**Verification environment.** The e2e suite is Chromium-only by design (`web/playwright.config.ts`, header comment), so no Playwright probe in this document proves anything about WebKit. Every clause whose subject is iOS Safari behaviour is marked manual and requires the real-device lab named in `docs/prd/03-mobile-cross-platform.md` §4.3/§9. A "mobile viewport" probe means `hover: none`-emulated touch at ≤767 px width, matching the gate method in `docs/mobile-ux/ST5-spec.md` §(d).

**Token discipline.** Every token named in this document was read from `web/src/app/globals.css`. A clause that names a token that no longer resolves there is stale and must be fixed, not worked around.

---

## 1. Layout, overflow and reflow — `UI-LAYOUT`

### UI-LAYOUT-1 [must] — No horizontal page scroll
**Assertion.** At every supported width from 320 px to 1920 px, in both themes, `document.scrollingElement.scrollWidth` is not greater than `clientWidth`; only designated scrollers (code blocks, tables, the compare strip) scroll horizontally.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4 ("never overflow the viewport on mobile"); WCAG 2.2 SC 1.4.10 Reflow (AA), which forbids two-dimensional scrolling for content at 320 CSS px equivalent.
**Verify.** Playwright: for each width in `[320, 375, 414, 768, 1024, 1440, 1920]`, `await page.setViewportSize(...)` then assert `await page.evaluate(() => document.scrollingElement.scrollWidth <= document.scrollingElement.clientWidth + 1)`.

### UI-LAYOUT-2 [must] — Wide content scrolls inside its own container
**Assertion.** Every `pre` and `table` inside streamed markdown has `overflow-x: auto` and `overscroll-behavior-x: contain` in computed style; neither widens its message row.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4 (tables wrap in a horizontal-scroll container); `web/src/app/globals.css` `.chat-md :where(pre)` / `:where(table)`; `docs/mobile-ux/ST4-native-gap-audit.md` G7 (edge chaining to browser back-swipe).
**Verify.** Computed style on a rendered fenced block and a rendered table: `overflow-x === "auto"` and `overscroll-behavior-x === "contain"`.

### UI-LAYOUT-3 [must] — Message rows keep a stable scroll range
**Assertion.** Every message row carries the `.chat-message-row` class with a role-specific `contain-intrinsic-size`, so virtualized/off-screen rows do not change the document scroll height as they enter and leave.
**Source.** `web/src/app/globals.css` `.chat-message-row` block; `docs/prd/03-mobile-cross-platform.md` §4.5 and §4.10 (CLS protection, reserve space); `docs/ux-best-practices/mobile-ux.md` §11 ("Virtualize messages past ~80 with overscan") and `docs/ux-best-practices/desktop-ux.md` §11 ("complement with `content-visibility: auto`" — the mobile document carries the virtualization half only).
**Verify.** Playwright: render a 100-message thread, record `document.body.scrollHeight`, scroll to the middle and back to the top, assert the height is unchanged within 1 px.

### UI-LAYOUT-4 [must] — Elevation is reserved for modal-class surfaces
**Assertion.** No message bubble, attribution row, reasoning panel, status line or inline control carries a `box-shadow` other than `none` at rest; shadow appears only on drawer, sheet, dialog, tooltip/popover and the transient jump-to-latest FAB.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.3 ("message surfaces remain flat; elevation reserved for drawer/sheet/modal"); `docs/design/02-patterns.md`, "Flat content, layered chrome" (exhaustive list); `docs/design/03-anti-patterns.md` §B; Decision 15 in `docs/design/04-rationale.md`.
**Verify.** Playwright: for `[data-testid="assistant-message"]`, `[data-testid="message-attribution"]`, `[data-testid="reasoning-panel"]`, `[data-testid="user-message-text"]`, assert `getComputedStyle(el).boxShadow === "none"`.

### UI-LAYOUT-5 [must] — Glass is chrome-only
**Assertion.** No element inside the message column has a non-`none` `backdrop-filter`, and no message-part renderer carries a glass utility; the `glass-regular` / `glass-strong` / `glass-clear` / `glass-capsule` / `chrome-frost` utilities appear only on chrome — header, composer capsule, FAB, drawer, dialog, sheet, popover, tooltip, toast — and on cards nested inside one of those chrome surfaces.
**Why cards count as chrome.** `glass-clear` is the shipped card material *within* chrome: the settings, memory, activity, template-library and model-directory dialogs, the sidebar's tag and assignment cards, the spend-analytics tiles, the BYOK form and the welcome screen's suggestion pills all use it, which is over twenty sites. A list naming only the six outer surfaces fails every one of them while the rule's actual subject — the message column — is untouched. The line the clause draws is the message column, not the nesting depth.
**Source.** `docs/design/01-foundations.md`, Motion → "Choreography of disclosure" (glass on chrome, messages flat); `docs/design/03-anti-patterns.md` §B, "Glass material on message bubbles"; Decision 06 in `docs/design/04-rationale.md`; utilities defined in `web/src/app/globals.css`.
**Verify.** `rg -n 'glass-(regular|strong|clear|capsule)|chrome-frost' web/src/components` and confirm no hit sits on a message-part renderer; plus a computed-style assertion that `backdrop-filter` is `none` on the assistant message body.

### UI-LAYOUT-6 [must] — The shell derives from one source of truth
**Assertion.** Pane count and drawer mode are read from the single shell breakpoint source, not recomputed per component; resizing across the 768 / 1024 / 1440 boundaries changes layout without a reload and without a duplicated or orphaned drawer state.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.1 and §5.3 ("single source of truth for the shell"); `docs/ux-best-practices/desktop-ux.md` §13 D8.
**Verify.** Playwright: open the drawer at 375 px, resize to 1280 px, assert exactly one sidebar is in the accessibility tree and the drawer is not mounted; resize back and assert the drawer state is not stale.

### UI-LAYOUT-7 [should] — Reusable panes adapt by container, not viewport
**Assertion.** A pane that can appear at more than one column width (artifact panel, composer toolbar, message action row) adapts to its own available width via container queries rather than a viewport media query.
**Source.** `docs/prd/03-mobile-cross-platform.md` §5.3 ("container (size) queries — Baseline-safe — for reusable panes").
**Verify.** Manual code review of the component's CSS: a `@container` rule, not an `md:` prefix, drives its internal density.

### UI-LAYOUT-8 [must] — RTL renders without layout breakage
**Assertion.** Under `dir="rtl"`, prose and user-message text align to the start edge, code and `pre` stay LTR, and directional affordance glyphs are mirrored via `.rtl-flip` / `[data-rtl-flip]`; no control overlaps another and UI-LAYOUT-1 still holds.
**Source.** `web/src/app/globals.css`, RTL / logical-direction baseline block; `docs/prd/06-design-system-visual-spec.md` §8 open question 4 (logical CSS is P0); `docs/ux-best-practices/desktop-ux.md` §13 D12.
**Verify.** Playwright at `?rtl=1`: assert `getComputedStyle(pre).direction === "ltr"`, assert `text-align` resolves to the start edge on `.chat-md`, and re-run the UI-LAYOUT-1 scroll-width assertion. Then check the mirroring half, which the three assertions above do not reach: `rg -n 'rtl-flip' web/src/components` must return at least the send control and the directional chevrons, and under `?rtl=1` each of those must resolve `transform` to a matrix with a negative horizontal scale. Without that step the check passes on a build where the mirroring is never applied — which is the state §15 C29 records.

---

### UI-LAYOUT-9 [must] — Message role is carried by alignment
**Assertion.** In the thread, a user message's box ends at the message column's end edge and is narrower than the column. An assistant message spans the column from edge to edge. Alignment alone distinguishes the two roles, and no clause elsewhere may remove it without replacing it.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.1 ("User: aligned end, plain text. / Assistant: aligned start, part renderer"); `docs/design/04-rationale.md` Decision 15, which rejects two-tone and alternating-row treatments on the stated ground that "the role distinction is already carried by alignment and avatar".
**Why this clause exists.** UI-LAYOUT-4 forbids the shadow and UI-LAYOUT-5 forbids the glass, so both subtract role signal. Decision 15 permits that subtraction because alignment carries the role. Nothing asserted the alignment, so the rationale rested on a property no clause guaranteed. This clause guarantees it.
**Scope.** The visual half only. The programmatic half — `role="article"` with an accessible name of "You" or "Assistant" — is UI-FOCUS-6's. Decision 15 names alignment **and avatar**; the assistant message ships no avatar, so this clause asserts alignment alone and §15 C36 records the missing second carrier. Do not add an avatar assertion here.
**Verify.** Playwright at 1280 px: send one message and read `boundingBox()` for the last `[data-testid="user-message-text"]`, the last `[data-testid="assistant-message"]` and the last `[data-testid="message-list-row"]`, which is the column. Assert the user box's end edge sits within 2 px of the column's end edge and its width is less than the column's. Assert the assistant box matches the column's box within 2 px.

### UI-LAYOUT-10 [must] — A code block names its language and copies its source
**Assertion.** Every fenced code block in a rendered message shows a language label and a copy control, and the copy control writes the raw fence source to the clipboard rather than the highlighted DOM text.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.7 ("Language label, syntax highlighting, copy button"); `docs/prd/01-core-chat-experience.md` §5.4 ("copy copies raw source (not highlighted DOM)").
**Scope.** Presence, the language label and the clipboard payload only. The copy control's accessible name is UI-FOCUS-5's and its touch size is UI-TOUCH-1's, so this clause must not re-assert either. The "Show more" collapse named in the same PRD bullet is not shipped — §15 C35.
**Vendor caveat.** The chrome is Streamdown's, not this repo's: `web/src/components/chat/markdown-renderer.tsx` delegates it and passes only `controls={{ code: { download: false } }}`. `data-language` and `[data-streamdown="code-block-copy-button"]` are the vendored library's own hooks. Streamdown marks its parts with `data-streamdown`, not with class names, so a check written against a `.code-block-*` class matches nothing and fails on conformant code. An upgrade can rename them, so a failing Verify means "read the new markup first", not "the app regressed" — the same caution §15 C4 records for `max-w-3xl`.
**Verify.** Playwright with the fake provider: send a prompt beginning `RICH_MARKDOWN:`, which makes the fake emit a fenced `python` block (`api/app/providers/fake.py`). Assert `[data-streamdown="code-block-header"]` carries `data-language="python"` and shows that text. Grant the `clipboard-read` and `clipboard-write` permissions, click `[data-streamdown="code-block-copy-button"]`, read `navigator.clipboard.readText()`, and assert the result is the fence's source text, `print("hello")` followed by a newline.

### UI-LAYOUT-11 [must] — An unbroken string wraps inside its own box
**Assertion.** A 300-character string with no break opportunity wraps inside its box in a user message and in assistant prose, and a 200-character conversation title truncates inside its sidebar row, so none of the three widens its container past the message column or the row.
**Source.** WCAG 2.2 SC 1.4.10 Reflow (AA); `web/src/app/globals.css` `.chat-md` and `.chat-md :where(a)`, which both set `overflow-wrap: anywhere` and are the shipped statement of intent for prose; `api/app/schemas/conversation.py`, whose title PATCH constraint (`max_length=200`) fixes the longest title a row must survive.
**Scope.** The strings in question are what users paste: URLs, hashes, base64 blobs.
**Why UI-LAYOUT-1 does not cover it.** UI-LAYOUT-1 reads the page's scroll width only. A bubble can overflow its column without moving the page when an ancestor clips it, and then the tail of the string is simply gone. This clause measures the box itself. The designated scrollers, `pre` and `table`, are UI-LAYOUT-2's and are exempt here.
**Verify.** Playwright at 320 px and at 1280 px, with `S = "https://example.com/" + "a".repeat(280)`. (1) Send `S`. For the last `[data-testid="user-message-text"]`, assert `scrollWidth <= clientWidth + 1`, and assert its right edge is at most the right edge of its `[data-testid="message-list-row"]` plus 1 px. (2) When that turn's assistant message reads `data-status="done"`, append a `p` containing `S` to the last `.chat-md` with `page.evaluate`, and assert the same two things on that `.chat-md`. The injection is deliberate: the fake provider echoes nothing back, and the property under test is the stylesheet, not the model. (3) Record the width of the conversation's `[data-conversation-id]` row, then rename the conversation to `"W".repeat(200)` through the row's "Conversation actions" → "Rename" flow, as `web/tests/e2e/conversation.spec.ts` does. Assert `[data-testid="sidebar-conversation-title"]` has `scrollWidth > clientWidth`, which proves it truncated rather than wrapped the row open, and that the row's width is unchanged. Re-run the UI-LAYOUT-1 assertion after each step.

### UI-LAYOUT-12 [should] — Truncated text keeps its full value within reach
**Assertion.** Every element that visibly truncates its text — `text-overflow: ellipsis`, or a line clamp that is actually clipping — exposes the full string through a `title` on itself or an ancestor, or through a tooltip bound to its nearest interactive ancestor, and that ancestor's accessible name does not contradict the full string.
**Source.** WCAG 2.2 SC 1.4.10 Reflow (AA), whose "without loss of information" condition a truncation meets only when the full text stays available; shipped precedent in `web/src/components/chat/sidebar.tsx`, which puts `title={conversation.title}` on the truncated row title. The accessible-name half is WCAG 2.2 SC 2.5.3 Label in Name, which UI-FOCUS-12 asserts for every control.
**On the strength marker.** `[should]`, not `[must]`, and deliberately. A `title` never appears on touch, which is this product's primary form factor, so a `[must]` would certify a mechanism that restores the text for mouse users only. The better remedy on touch is to let the text wrap or clamp at two lines. A deviation entry is where a surface argues that its truncation is worth that cost.
**Verify.** Playwright at 320 px and at 1280 px, on the thread, the sidebar carrying UI-LAYOUT-11's 200-character title, the command-palette results and the open model picker. Evaluate:
`[...document.querySelectorAll("body *")].filter(el => { if (!el.getClientRects().length) return false; const cs = getComputedStyle(el); const clipped = (cs.textOverflow === "ellipsis" && el.scrollWidth > el.clientWidth + 1) || (cs.webkitLineClamp !== "none" && el.scrollHeight > el.clientHeight + 1); if (!clipped) return false; const full = el.textContent.trim(); const ctl = el.closest('button, a[href], [role="button"], [role="menuitem"], [role="option"], [role="tab"]'); const titled = (el.closest("[title]")?.getAttribute("title") ?? "").includes(full); const tip = !!ctl?.matches('[data-slot="tooltip-trigger"]'); const label = ctl?.getAttribute("aria-label"); const named = !label || label.includes(full); return !((titled || tip) && named); }).map(el => el.textContent.trim().slice(0, 40))`
and assert the result is empty. Each string it returns names a truncation with no way back to its full text.

## 2. Typography and measure — `UI-TYPE`

### UI-TYPE-1 [must] — No blocking font on the critical path
**Assertion.** No `@font-face` on the critical path uses a blocking `font-display`; the UI stack resolves from `--font-sans` / `--font-mono` immediately, and `--font-heading` (Instrument Serif) loads with `display: optional` and a metric-adjusted fallback so it never swaps in late.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2; Decision 04 and Decision 16 in `docs/design/04-rationale.md`; `docs/design/03-anti-patterns.md` §D.
**Verify.** Grep the generated CSS for `font-display`; assert every face is `optional` (or absent). Lighthouse/DevTools: no render-blocking font request before first contentful paint.

### UI-TYPE-2 [must] — Display serif is welcome-only
**Assertion.** `--font-heading` is applied only to the welcome greeting at display size; no body, chrome, message or attribution text resolves to it.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("display sizes only"); Decision 16 in `docs/design/04-rationale.md`; `docs/design/03-anti-patterns.md` §G, "Personality bleeding into the working surface".
**A wordmark is not an exception.** The product name set in the display serif at chrome size was argued as a logotype rather than UI text. It is not carved out, for a reason that is about type rather than about branding: Instrument Serif is drawn for hero sizes, and at 1.25 rem its hairlines muddy, so the header was using a display face below its optical size. The brand moment stays where the face reads — the hero greeting. A wordmark that needs to appear in the chrome appears in the UI sans.
**Verify.** `rg -n 'font-heading' web/src/components` — every hit must be inside `welcome-screen.tsx`. The sweep is scoped to `components/` on purpose: across all of `web/src` the same pattern also matches the token's own definition (`globals.css` `--font-heading`) and the `next/font` wiring that feeds it (`layout.tsx` `--font-heading-serif`), so the unscoped form can never pass, however conformant the code.

### UI-TYPE-3 [must] — Every size is rem-based
**Assertion.** No rendered text has a `px`-literal `font-size`; the type ramp is expressed in `rem` (or Tailwind utilities that resolve to `rem`) so a raised root font size scales the whole interface.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("`rem`-based"); `docs/prd/03-mobile-cross-platform.md` §4.8 (Dynamic type); `docs/design/03-anti-patterns.md` §D, "Reading text that ignores user scale"; WCAG 2.2 SC 1.4.4 Resize Text (AA).
**Verify.** Playwright: set `document.documentElement.style.fontSize = "24px"`, assert the composer textarea's computed `font-size` scaled proportionally (≥ 24 px) and UI-LAYOUT-1 still holds.

### UI-TYPE-4 [must] — Mobile type-role floors hold
**Assertion.** On a mobile viewport, list-row and body text render ≥ 16 px, title-subtitle secondary text ≥ 15 px, and captions/eyebrows ≥ 13 px; no ramp is inverted (desktop must never be larger than mobile for the same role).
**Source.** `docs/mobile-ux/ST5-spec.md` §(b) role table (LOCKED) and §(d) gate H5; shipped as `.ui-list-row` / `.ui-body` / `.ui-secondary` / `.ui-caption` / `.ui-eyebrow` in `web/src/app/globals.css`.
**Verify.** Playwright at 390×844 with `hasTouch`: for every text node inside the surface under review, read computed `font-size` and assert it clears the floor for its role utility; repeat at 1280 px and assert the desktop value is ≤ the mobile value.

### UI-TYPE-5 [must] — Chat body uses the reading ramp
**Assertion.** Streamed assistant markdown renders through `.chat-md` (17 px mobile / 15 px desktop, `leading-7`); no message-body renderer overrides the size downward for density.
**Source.** `web/src/app/globals.css` `.chat-md`, which is the normative figure for the two-step ramp; `docs/prd/06-design-system-visual-spec.md` §3.2 ("Chat body: 16px base, `rem`-based"), which commits to a `rem`-based body but states a single 16 px figure rather than this ramp — see §15 C12; `docs/design/03-anti-patterns.md` §D ("density that costs comprehension is not power-user density").
**Verify.** Computed style on `.chat-md`: `font-size` is `17px` at ≤767 px and `15px` at ≥768 px, `line-height` is `28px`.

### UI-TYPE-6 [must] — Reading measure is capped
**Assertion.** On any viewport wider than the column, a full line of assistant prose measures no more than ~80 characters; the column is capped, not fluid to the viewport.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("message column capped around 70–80ch on wide screens"); `docs/prd/03-mobile-cross-platform.md` §5.3; `docs/design/01-foundations.md`, Typography → "Measure"; `docs/design/03-anti-patterns.md` §D.
**Verify.** Playwright at 1920 px: measure the rendered column against the font's `ch` unit — `await page.evaluate(() => { const el = document.querySelector('.chat-md'); const probe = document.createElement('span'); probe.style.cssText='position:absolute;visibility:hidden;width:80ch'; el.appendChild(probe); const ok = el.clientWidth <= probe.clientWidth; probe.remove(); return ok; })`. **Note:** the shipped cap is a rem cap (`max-w-3xl` on `web/src/components/chat/message-list.tsx:366`), not a `ch` cap, so this must be measured rather than read off the class — see §15 C4.

### UI-TYPE-7 [must] — Monospace carries code and numerals
**Assertion.** Code blocks, inline code, token counts and USD figures render in `--font-mono`; prose never does.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("monospace: code blocks and token/cost numerals") and §5.5 ("numerals in monospace").
**Verify.** Computed `font-family` on a rendered `pre`, on inline `code`, and on the usage-meter figure resolves through `--font-mono`.

### UI-TYPE-8 [must] — Text survives user spacing overrides
**Assertion.** With line-height 1.5×, paragraph spacing 2×, letter-spacing 0.12× and word-spacing 0.16× forced, no text is clipped and no control overlaps.
**Source.** WCAG 2.2 SC 1.4.12 Text Spacing (AA). Repo canon is silent on this criterion (see §15 C6); it is `[must]` here because it is an AA criterion and C2 sets the bar at WCAG 2.2 AA, and it is adopted as part of the AA baseline that `docs/prd/03-mobile-cross-platform.md` §4.8 and `docs/ux-best-practices/desktop-ux.md` §10 commit the product to.
**Verify.** Playwright: inject the WCAG text-spacing bookmarklet stylesheet, screenshot the surface, and assert no element has `scrollHeight > clientHeight` where `overflow` is `hidden`.

---

### UI-TYPE-9 [should] — Layout survives string expansion
**Assertion.** With every visible text node expanded by 40%, no attribution row and no composer control clips its text, overlaps a neighbour, or pushes the page into horizontal scroll.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2, final bullet: "Pseudo-localization must not break attribution rows or composer layout."
**Why the Verify carries its own mechanism.** This repo has no pseudo-locale to switch to. `web/src/lib/i18n/messages.ts` defines `catalogs` as `{ en }`, and that catalog is a roughly 25-key subset covering `composer.*`, `sidebar.*`, `usage.*` and `followups.*`. The attribution row the PRD names is hardcoded English in the components, so swapping the catalog would not expand it. The `?rtl=1` hook is a direction override, not a locale. The check therefore expands the rendered text itself. §15 C6 records the i18n gap this works around.
**Verify.** Playwright at 390 px and at 1280 px: walk the document with a `TreeWalker` over text nodes and rewrite each one so its length grows by 40%. Then assert `document.documentElement.scrollWidth <= clientWidth + 1`, and for every element inside the attribution row and the composer assert `scrollWidth <= clientWidth + 1`.

## 3. Color, theme and contrast — `UI-COLOR`

### UI-COLOR-1 [must] — Zero hard-coded colors in feature code
**Assertion.** No component file under `web/src/components/` contains a literal hex, `rgb()`, `hsl()` or `oklch()` color value; all color comes from the semantic, chat and trust tokens in `web/src/app/globals.css`.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1 AC ("zero hard-coded colors in chat feature code outside token/CSS variables"); `docs/design/03-anti-patterns.md` §A, "Raw hex codes in component code"; Decision 03 in `docs/design/04-rationale.md`.
**Verify.** `rg -n '#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(|oklch\(' web/src/components` returns no hit outside a documented exception, and a hit inside a comment is not a color — the pattern matches a bare issue reference such as `#245` and the reviewer discards those by reading the line. Exceptions today: the `--glass-*` rgba fills and the `forced-colors` system keywords, which live in `globals.css`, not in components; and the conversation export document built in `web/src/components/chat/chat-thread.tsx`, which is a standalone `<!doctype html>` string where the app's custom properties do not exist, so its four literals are the only way to carry the product's typography and link color into a printed or downloaded file. That exception is bounded to the generated document: a literal anywhere in rendered app markup is still a defect.

### UI-COLOR-2 [must] — One saturated accent
**Assertion.** The only saturated hue in steady state is `--brand` / `--color-brand`; no surface introduces a second permanent saturated hue, and the semantic roles (`--color-destructive`, `--color-success`, `--color-warning`, `--color-info`) appear only inside their semantic context.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1; `docs/design/02-patterns.md`, "Single accent doctrine"; `docs/design/01-foundations.md`, Color → "A single saturated accent"; Decision 02 in `docs/design/04-rationale.md`.
**Verify.** Manual review against the token list, plus `rg -n 'accent-warm' web/src/components` — `--accent-warm` is a welcome-hero-only input to `--hero-glow-magenta` and must not appear in a component.

### UI-COLOR-3 [must] — Body text meets 4.5:1 in both themes
**Assertion.** Every body-size text/background pair resolves to a contrast ratio of at least 4.5:1 in light and in dark, including the attribution row, status lines, reasoning-panel text and the substitution callout.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1 ("all body text pairs >= 4.5:1"); `docs/prd/03-mobile-cross-platform.md` §4.8; WCAG 2.2 SC 1.4.3 Contrast (Minimum) (AA).
**Verify.** Automated contrast sweep over the rendered surface in both themes (the axe-class run required by `docs/prd/06-design-system-visual-spec.md` §7 AC 4 — see §15 C5 for the missing dependency), or compute pairwise ratios from resolved `color` / `background-color` in a Playwright evaluate.

### UI-COLOR-4 [must] — Non-text UI meets 3:1
**Assertion.** Control boundaries, the focus indicator, the usage-meter fill, checkbox/switch states and the substitution-callout ring meet 3:1 against their adjacent surface in both themes.
**Scope of "control boundary".** Not every drawn line. The obligation attaches to a boundary a user needs in order to perceive that something is a control, or to perceive its state. A card edge, a table rule or a list divider separates two regions of the same surface and carries no obligation, because nothing depends on seeing it; those stay on `--border`, which is deliberately quiet. A boundary that is the only signal of interactivity is load-bearing and takes `--control-border`, the 3:1 role. The decisive case is the follow-up chip: its label is a sentence sitting directly beneath body prose, so the pill outline is the sole thing that reads as "button", and SC 1.4.11's "identifiable by other means" exception does not apply. Shipped ratios for `--control-border`: light 3.47:1 on the page and 3.40:1 on the chip fill; dark 3.88:1 and 3.37:1.
**Source.** WCAG 2.2 SC 1.4.11 Non-text Contrast (AA); `docs/ux-best-practices/desktop-ux.md` §10 platform note ("focus ring must meet ... 3:1 contrast; audit `--focus-ring` token").
**Verify.** Compute the ratio between the resolved `--ring` / `--color-control-border` values and both surfaces they sit between (the page and the control's own fill, at rest and on hover), per theme.

### UI-COLOR-5 [must] — Color is never the sole carrier of state
**Assertion.** Every state distinction (JSON valid vs invalid, approaching vs exceeded limit, playing vs paused, selected vs unselected) is carried by text or glyph in addition to color.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.4 ("reads in text, not color alone") and §5.1; WCAG 2.2 SC 1.4.1 Use of Color (A).
**Verify.** Manual: render the surface in grayscale (`filter: grayscale(1)` on `html`) and confirm every state is still distinguishable.

### UI-COLOR-6 [must] — Substitution is not an error color
**Assertion.** The served-vs-requested callout renders in `--color-substitution-callout` / `-foreground` / `-border`, never in the destructive role; the Stop control is neutral, never red.
**Source.** `docs/prd/07-transparency-contract.md` §5 and §6.1; `docs/prd/08-error-and-limit-states.md` §5.7; `docs/prd/06-design-system-visual-spec.md` §5.2 and §5.4; `docs/design/03-anti-patterns.md` §A, "Destructive color spent on non-destructive states".
**Verify.** Playwright against a forced-substitution fixture: assert `[data-testid="attribution-substitution"]` resolves its background to `var(--substitution-callout)` and does not contain `var(--destructive)`.

### UI-COLOR-7 [must] — Light and dark are parity, not translation
**Assertion.** Every P0 component renders in light, dark and system with the same information, the same affordances and the same role semantics; no element is visible in one theme and invisible in the other.
**Source.** `docs/prd/06-design-system-visual-spec.md` §7 AC 7 ("light/dark/system parity for all P0 components"); `docs/design/01-foundations.md`, Color → "Light, dark, and OS-honored modes".
**Verify.** Playwright screenshot pairs per surface with `colorScheme: "light"` and `"dark"`; assert identical accessibility-tree node counts and identical visible text.

### UI-COLOR-8 [must] — System theme is the default and boots without flash
**Assertion.** With no stored preference the app follows `prefers-color-scheme`; the correct theme class and `color-scheme` are set before first paint, so no wrong-theme frame is visible.
**Source.** `docs/design/01-foundations.md`, Color → "Light, dark, and OS-honored modes"; `docs/ux-best-practices/desktop-ux.md` §13 D11 and `docs/ux-best-practices/mobile-ux.md` §13 M14.
**Verify.** Playwright with `colorScheme: "dark"` and cleared storage: capture a trace and assert no frame renders the light background before the dark class is applied.

### UI-COLOR-9 [should] — Trust roles stay tints, not second accents
**Assertion.** `--color-trust-badge`, `--color-byok-indicator` and `--color-temporary-chat-banner` render as low-chroma tints that read as role markers, not as a competing saturated hue next to `--brand`.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1 (trust roles); `docs/design/01-foundations.md`, Color → "A single saturated accent" (the BYOK-pill example and its chroma cap).
**Verify.** Manual: place the BYOK chip beside a `--brand`-filled control and confirm the chip does not read as a second brand color; cross-check the token's OKLCH chroma against the neutral band in `globals.css`.

---

## 4. Focus and keyboard — `UI-FOCUS`

### UI-FOCUS-1 [must] — Every interactive element is keyboard reachable and operable
**Assertion.** Send, Stop, copy, regenerate, edit, thumbs, expand-reasoning, model picker, history navigation, command palette and every recovery action are reachable by Tab/Shift-Tab and operable by Enter/Space, with no keyboard trap outside a deliberate modal.
**Source.** `docs/prd/01-core-chat-experience.md` §5.7 ("full keyboard operability"); `docs/prd/08-error-and-limit-states.md` §9 ("all recovery actions keyboard-operable"); WCAG 2.2 SC 2.1.1 Keyboard (A) and SC 2.1.2 No Keyboard Trap (A).
**Verify.** Playwright: walk the surface with `page.keyboard.press("Tab")`, collecting `document.activeElement`; assert the set of reached elements is a superset of the surface's interactive roles and that the walk terminates.

### UI-FOCUS-2 [must] — Focus is always visible
**Assertion.** Every focusable element shows the `--focus-ring` indicator on keyboard focus (`:focus-visible`), and no element shows it on mouse hover or pointer click alone.
**Source.** `docs/design/02-patterns.md`, "Focus as the brand moment" ("appears only on keyboard focus, never on hover"); `web/src/app/globals.css` `--focus-ring`; WCAG 2.2 SC 2.4.7 Focus Visible (AA).
**Verify.** Playwright: focus by keyboard and assert computed `box-shadow` contains the resolved `--focus-ring` value; then click the same element with the mouse and assert the ring is absent.

### UI-FOCUS-3 [must] — Focus is not obscured by sticky chrome
**Assertion.** A keyboard-focused element inside the scrolling thread is never fully hidden behind the sticky header or composer chrome; focused message rows keep the `.chat-message-row` scroll margins that clear both.
**Source.** WCAG 2.2 SC 2.4.11 Focus Not Obscured (Minimum) (AA); `web/src/app/globals.css` `.chat-message-row` (`scroll-margin-top: 5rem; scroll-margin-bottom: 6rem`, commented "WCAG 2.4.11"); `docs/ux-best-practices/desktop-ux.md` §13 D3.
**Verify.** Playwright: Tab to the first and last message rows in a long thread and assert `boundingBox()` does not intersect the header or composer bounding boxes.

### UI-FOCUS-4 [must] — Modals trap and restore focus
**Assertion.** Opening a dialog, drawer, sheet or command palette moves focus into it, Tab cycles within it, Esc closes it, and focus returns to the invoking control.
**Source.** `docs/prd/01-core-chat-experience.md` §5.7 (shortcuts-dialog AC); `docs/prd/06-design-system-visual-spec.md` §7 AC 9; `docs/prd/08-error-and-limit-states.md` §9; `docs/design/03-anti-patterns.md` §H, "Focus traps without close + restore".
**Verify.** Playwright: record `document.activeElement` before opening; open, Tab through twice and assert focus never escapes; press Escape; assert focus equals the recorded element.

### UI-FOCUS-5 [must] — Icon-only controls have accessible names
**Assertion.** 100% of icon-only buttons expose a descriptive accessible name that survives an icon swap.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.1 and §7 AC 5; `docs/prd/01-core-chat-experience.md` §5.7; `docs/design/03-anti-patterns.md` §H, "Icon buttons without accessible names".
**Verify.** Playwright: `const unnamed = await page.$$eval('button', bs => bs.filter(b => !b.textContent.trim() && !b.getAttribute('aria-label') && !b.getAttribute('aria-labelledby')).length)`; assert `unnamed === 0`.

### UI-FOCUS-6 [must] — Landmarks are present and named
**Assertion.** The surface exposes a labeled `navigation`/`complementary` landmark for history, a `main` landmark for the thread, and a labeled header, so a screen-reader user can jump directly to history without traversing the page.
**Source.** `docs/prd/01-core-chat-experience.md` §5.7 (sidebar landmark AC); `docs/prd/06-design-system-visual-spec.md` §7 AC 10; `docs/ux-best-practices/desktop-ux.md` §10.
**Verify.** Playwright: `expect(page.getByRole('navigation', { name: /history|conversations/i })).toBeVisible()` and `expect(page.getByRole('main')).toBeVisible()`.

### UI-FOCUS-7 [must] — Every shortcut and gesture has a visible equivalent
**Assertion.** Every keyboard shortcut, right-click action, swipe and long-press has a visible, single-pointer, keyboard-operable control that performs the same action.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.4 ("every gesture has a tappable alternative") and §4.8; `docs/ux-best-practices/desktop-ux.md` §13 "Cross-platform seam"; WCAG 2.2 SC 2.5.7 Dragging Movements (AA), which reaches the swipe half of this assertion only — the keyboard-shortcut, right-click and long-press halves rest on repo canon, not on 2.5.7.
**Verify.** Manual matrix review: for each entry in the shortcut table (`docs/prd/01-core-chat-experience.md` §5.5) and each gesture in `docs/prd/03-mobile-cross-platform.md` §4.4, name the visible control; a row with no named control fails.

### UI-FOCUS-8 [should] — Focus indicator meets the appearance target
**Assertion.** The focus indicator is at least 2 CSS px thick around the perimeter of the focused control and meets 3:1 against both the control and the adjacent background in both themes.
**Source.** WCAG 2.2 SC 2.4.13 Focus Appearance — **AAA**, not AA (see §15 C3, where `docs/ux-best-practices/desktop-ux.md` §10 cites it without its level); SC 1.4.11 Non-text Contrast (AA) carries the 3:1 half at AA. Shipped indicator: `--focus-ring` in `web/src/app/globals.css`.
**Verify.** Read the resolved `--focus-ring` value (a 2 px background offset plus a 2 px brand ring) and compute its contrast against `--background` and against each control fill, per theme.

---

### UI-FOCUS-9 [must] — Every rendered image carries an alt attribute, and a content image names itself
**Assertion.** No `<img>` in rendered app markup omits its `alt` attribute. An image inside a rendered message has a non-empty `alt`, supplied by the model when the model gives one and by the renderer when it does not. An empty `alt` is permitted only on a decorative image.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4: "Images: lazy-load, constrained max-width, alt text required (use model-provided alt or a generic label)."
**Scope.** The decidable subject is the renderer, not the content. A model can emit a bare `![](url)`, so the clause holds the renderer to supplying the fallback label — `web/src/components/chat/markdown-renderer.tsx` overrides `img` for exactly that reason. The one decorative image today is the source favicon in `web/src/components/chat/sources-panel.tsx`, which is correctly `alt=""`. UI-FOCUS-5 is scoped to `button` elements and reaches no image, which is why this clause is separate rather than an extension of it.
**Verify.** Playwright: send a prompt beginning `RICH_MARKDOWN:`, which makes the fake provider emit a deliberately alt-less markdown image. Assert `page.$$eval("img", els => els.every(e => e.hasAttribute("alt")))`. Then assert every `img` inside `.chat-md` has a non-empty `alt` — the renderer's fallback label, since the model supplied none.

### UI-FOCUS-10 [must] — A tooltip opens on focus, dismisses, stays hoverable, and is never essential
**Assertion.** Every tooltip opens on keyboard focus as well as on pointer hover, closes on Escape without moving focus, stays open while the pointer travels from its trigger onto it, and carries no text that the trigger's accessible name, or a visible surface such as the shortcuts dialog, does not also carry.
**Source.** WCAG 2.2 SC 1.4.13 Content on Hover or Focus (AA): dismissible, hoverable, persistent; `docs/ux-best-practices/desktop-ux.md` §13 D10 ("not sole carrier of essential info; keyboard-focus triggerable; WCAG 1.4.13 dismissable"), whose repo-status column still reads "verify keyboard + 1.4.13".
**Scope.** The shipped tooltips are the `web/src/components/ui/tooltip.tsx` primitive, mounted today in `message-actions.tsx` and `user-message.tsx`. Touch is not asserted here. A tooltip cannot be the only route to an action on touch, and UI-TOUCH-6 already forbids that.
**Verify.** Playwright at 1280 px without touch, on a finished turn. Tab to the first `[data-slot="tooltip-trigger"]` inside `[role="toolbar"][aria-label="Message actions"]` and assert a `[data-slot="tooltip-content"]` becomes visible within 1.5 s. Record `document.activeElement`, press Escape, and assert the content is hidden and `activeElement` is unchanged. Next, hover the trigger, wait for the content, move the mouse in ten steps to the content's centre, and assert it is still visible. Finally, for every tooltip trigger on the page, assert the tooltip's text is contained in the trigger's accessible name, or is a key combination that the shortcuts dialog also lists.

### UI-FOCUS-11 [should] — Headings form an outline
**Assertion.** The document has exactly one `h1`, and in document order no heading is more than one level deeper than the heading before it, with an open dialog restarting the count at its own title.
**Source.** WCAG 2.2 SC 1.3.1 Info and Relationships (A) and SC 2.4.6 Headings and Labels (AA), with technique G141, "Organizing a page using headings"; `web/src/components/chat/chat-thread.tsx`, whose `sr-only` `h1` exists so that a screen-reader user's heading navigation starts from the thread's name.
**On the strength marker.** A skipped level fails neither criterion by itself — G141 is a sufficient technique, not a requirement — so the clause is `[should]`. A screen-reader user navigating by heading level is the person a skipped level costs, and the deviation entry has to say why that cost is worth paying.
**Verify.** Playwright on the welcome surface, a thread, and each dialog (Settings on every tab, shortcuts, memory, activity, template library, model directory). Collect `h1`–`h6` that are neither inside `[hidden]` or `[aria-hidden="true"]` nor inside a closed dialog. Outside any `[role="dialog"]`, assert exactly one `h1` and that each heading's level is at most one more than the previous heading's. Inside each open `[role="dialog"]`, take the level of the dialog's title as the base and apply the same step rule. The standalone export document built in `chat-thread.tsx` is a separate file and out of scope.

### UI-FOCUS-12 [must] — A control's accessible name contains its visible label
**Assertion.** Every control that shows visible text and takes its accessible name from `aria-label` or `aria-labelledby` has a name that contains that visible text, word for word, ignoring case and whitespace.
**Source.** WCAG 2.2 SC 2.5.3 Label in Name (A) — a speech-input user says what they see, and a name that omits it leaves the control unreachable by voice; `docs/prd/06-design-system-visual-spec.md` §2, Goals ("Meet WCAG 2.1 AA"), and `docs/prd/05-roadmap-monetization-metrics.md` §7.1 ("Level **AA** as the bar") — 2.5.3 is Level A in both 2.1 and 2.2.
**Scope.** Controls named from their content pass by construction and are not checked. Text that is not part of the label — a `kbd` shortcut hint, anything under `aria-hidden="true"` — is stripped before comparing. Icon-only controls have no visible text and are UI-FOCUS-5's.
**Verify.** Playwright at 1280 px on the welcome surface, a thread with a finished turn and its message overflow open, the sidebar with a row's "Conversation actions" menu open, and the Settings dialog on every tab. Evaluate:
`[...document.querySelectorAll('button, a[href], [role="button"], [role="link"], [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [role="option"], [role="tab"], [role="switch"], [role="checkbox"]')].filter(el => el.getClientRects().length && (el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby"))).filter(el => { const norm = t => (t ?? "").toLowerCase().replace(/\s+/g, " ").trim(); const c = el.cloneNode(true); c.querySelectorAll('kbd, [aria-hidden="true"]').forEach(n => n.remove()); const visible = norm(c.textContent); if (!visible) return false; const name = el.hasAttribute("aria-labelledby") ? el.getAttribute("aria-labelledby").split(/\s+/).map(id => document.getElementById(id)?.textContent).join(" ") : el.getAttribute("aria-label"); return !norm(name).includes(visible); }).map(el => el.outerHTML.slice(0, 100))`
and assert the result is empty. Each entry is a control a voice user cannot name by what it says.

## 5. Touch targets and pointer — `UI-TOUCH`

### UI-TOUCH-1 [must] — 44 px floor on touch
**Assertion.** On a device where `hover: none` matches, every interactive control has a hit region of at least 44×44 CSS px, measured on the hit region (which may be hit-slop) rather than the painted box.
**Source.** `docs/prd/06-design-system-visual-spec.md` §7 AC 6 ("Mobile primary controls >=44px") and §5.2 ("Stop is 44x44px minimum on mobile") — §3.3 covers spacing, radius and elevation and states no touch figure; `docs/prd/03-mobile-cross-platform.md` §4.8 ("44–48px"); `docs/mobile-ux/ST2-touch-audit.md` (method and offender table); `docs/mobile-ux/ST5-spec.md` §(d) gates H3/H4; Apple HIG (44×44 pt minimum hit target). **Stricter than external canon:** WCAG 2.2 SC 2.5.8 Target Size (Minimum) (AA) sets 24×24 px; repo canon rules and 44 is the floor on touch.
**Verify.** Playwright with `hasTouch: true` at ≤767 px: for every `button, [role="button"], [role="tab"], [role="option"], a, input[type=checkbox]`, assert the union of `boundingBox()` and any `::before` hit-slop is ≥ 44 in both axes. Exclude the Next.js dev overlay first — the e2e harness boots the frontend with `next dev`, whose Dev Tools trigger renders a 32×32 button into the page and is the one hit an otherwise clean sweep returns. It is harness furniture, absent from any production build, so scope the selector under the app root or filter `[data-nextjs-*]` rather than recording it as a defect.

### UI-TOUCH-2 [must] — 24 px floor on pointer
**Assertion.** On a pointer device, every interactive control has a target of at least 24×24 CSS px, or is separated from its neighbours so that a 24 px circle centred on it overlaps no other target.
**Source.** WCAG 2.2 SC 2.5.8 Target Size (Minimum) (AA); `docs/ux-best-practices/desktop-ux.md` §13 D9 ("desktop may use denser targets (24px WCAG floor); gate 44px touch floor on `hover:none` only").
**Verify.** Playwright at 1280 px without `hasTouch`: assert every interactive `boundingBox()` is ≥ 24 in both axes, or that the spacing exception applies.

### UI-TOUCH-3 [must] — Dense clusters do not steal taps
**Assertion.** Adjacent controls in a cluster (segmented toggles, Edit/Delete pairs, tab strips) are separated by at least 8 px, and no expanded hit region overlaps a neighbour's.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.8 ("≥8px spacing"); `docs/mobile-ux/ST5-spec.md` §(d) gate H8 and §(e) risk R1 ("do not ship 44px targets without the spacing half").
**Verify.** Playwright with touch emulation: for each pair of sibling controls, assert the gap between their hit regions is ≥ 8 px and the regions do not intersect; then tap each and assert the intended handler fired.

### UI-TOUCH-4 [must] — Desktop density is not changed by a touch fix
**Assertion.** Every rule added to satisfy a touch floor is gated on `@media (hover: none)` or `@media (pointer: coarse)`, and a mouse viewport at ≥768 px renders byte-for-byte identically before and after the change. A width gate (`md:`) does not satisfy this clause: it also changes a touch tablet at ≥768 px, which is the failure UI-TOUCH-5 names.
**Source.** `docs/mobile-ux/ST5-spec.md` §0 cross-cutting invariant and §(d) gate H7 ("a hard acceptance criterion, not a nicety"). ST5 §0 also admits an `md:`-ramped floor; that half is **superseded** here, for the reason C10 records.
**Verify.** Playwright screenshot diff at 1280 px without `hasTouch`, before and after the change; zero pixel delta.

### UI-TOUCH-5 [must] — Touch floors are gated on pointer capability, not width
**Assertion.** The 44 px floor is selected by `hover: none` / `pointer: coarse`, so a touch tablet at ≥768 px keeps 44 px targets while receiving the desktop layout.
**Source.** `docs/ux-best-practices/desktop-ux.md` §13 D13 and `docs/ux-best-practices/mobile-ux.md` §13 M17; shipped in `web/src/components/ui/button.tsx` `buttonVariants` (`[@media(hover:none)]:size-11` / `:min-h-11`).
**How to write it.** The dense size is the base and the 44 px floor is the pointer-gated override: `size-9 [@media(hover:none)]:size-11`. The inverted form — a 44 px base with a width-gated reset, `size-11 md:size-9` — is the failure this clause names, and reads as correct until a tablet opens it. `rg -n '(size-11|min-h-11|h-11)[^"]*\b(sm|md|lg):(size-|min-h-|h-)' web/src` must return nothing: it matches a 44 px base followed by a width-gated sizing reset in the same class string, whatever the reset value. Do not shorten it to a bare width-prefixed size. A width-prefixed height on chrome that carries no floor — a header ramping `h-[46px] md:h-16` — is a layout ramp and not this defect, and the qualified pattern does not match it.
**Verify.** Playwright at 1024×768 with `hasTouch: true`: assert icon buttons measure 44 px and the desktop two-pane shell is rendered.

### UI-TOUCH-6 [must] — Hover is never the sole affordance
**Assertion.** Any control revealed on hover on a pointer device is persistently visible (or reachable through a labeled overflow control) on a touch device, and is revealed by `:focus-visible` for keyboard users.
**Source.** `docs/design/02-patterns.md`, "Density splits by input modality"; `docs/design/03-anti-patterns.md` §F, "One disclosure rule for both desktop and touch"; `docs/ux-best-practices/desktop-ux.md` §13 D3.
**How to write it.** Persistent visibility is the base and the hover hide is the pointer-gated override: `opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/x:opacity-100`. A width-gated hide (`md:opacity-0`) leaves the control invisible at rest on a touch tablet, which is this clause's failure. `rg -n '(md|sm|lg):opacity-0' web/src` must return nothing.
**Verify.** Playwright with `hasTouch: true`: assert message footer actions and conversation-row controls are visible without any hover event; then on desktop, Tab to the row and assert the same controls become visible.

### UI-TOUCH-7 [should] — Press feedback within 100 ms
**Assertion.** Every tappable control gives a visible pressed state (scale or fill change) within ~100 ms of touchdown, and that state is suppressed under `prefers-reduced-motion`.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.4 ("sub-100ms visual feedback regardless"); `docs/mobile-ux/ST4-native-gap-audit.md` G6; shipped in `buttonVariants` (`active:...scale-[0.96] active:duration-[70ms] motion-reduce:active:...scale-100`).
**Verify.** Computed style under `:active` shows a transform or background change with `transition-duration ≤ 100ms`; re-check under `prefers-reduced-motion: reduce` and assert the transform is `none`.

---

## 6. Motion and reduced motion — `UI-MOTION`

### UI-MOTION-1 [must] — Nothing animates in the periphery while the column streams
**Assertion.** While an assistant message is streaming, no element outside the streaming message column — header, sidebar, FAB, banners, badges — runs an ambient or looping animation. A finite transition that a state change at the stream boundary drives is not this failure: the send-to-Stop morph and the scroll-to-bottom control's reveal are both mandated choreography, and both fire in the periphery the moment a turn starts.
**Source.** `docs/design/00-principles.md`, Peacefulness ("the periphery carries none while the foreground is active"); `docs/design/02-patterns.md`, "Choreographed motion"; `docs/design/03-anti-patterns.md` §C, "Ambient motion outside a choreographed event".
**Verify.** Playwright: one second into a stream (past the boundary transitions, which are 400 ms at the longest), collect `document.getAnimations()` entries whose `playState` is `running` and whose `effect.target` is outside `[data-testid="message-list"]`. Assert every survivor has a finite `effect.getComputedTiming().iterations`. An entry with `iterations: Infinity` fails.

### UI-MOTION-2 [must] — Idle surfaces are still
**Assertion.** With no stream in flight and no pointer interaction, `document.getAnimations()` contains no running animation anywhere on the surface.
**Source.** `docs/design/01-foundations.md`, Motion → "Cadence and stillness" ("ambient micro-motion in steady state is a violation"); `docs/design/00-principles.md`, Peacefulness.
**Verify.** Playwright: wait for the turn to reach `data-status="done"`, wait 1 s, assert `await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length) === 0`.

### UI-MOTION-3 [must] — Streaming has exactly one cadence
**Assertion.** At any instant during a turn, at most one streaming-status animation is running: the reasoning shimmer (`--animate-shimmer`) or the pre-first-token pulse (`--animate-pulse-soft`), never both, and neither runs after the turn resolves.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.4; `docs/design/02-patterns.md`, "Streaming as a calmed state"; `docs/design/01-foundations.md`, Motion → "Cadence and stillness".
**Verify.** Playwright: poll `document.getAnimations()` through a turn and assert the count of running shimmer/pulse animations never exceeds 1 and reaches 0 on `data-status="done"`.

### UI-MOTION-4 [must] — Layout does not animate while content streams
**Assertion.** No width, padding, height or radius transition runs on a message bubble or code block while tokens are arriving; layout animations fire only after the stream settles or on user interaction.
**Source.** `docs/design/03-anti-patterns.md` §C, "Animating layout while content streams"; `docs/prd/01-core-chat-experience.md` §5.4 ("no layout shift > the height of the newly added content"); Decisions 08 and 09 in `docs/design/04-rationale.md`.
**Verify.** Playwright: during a stream, assert no running animation targets a geometric property — `a.effect.getKeyframes().every(k => !('width' in k || 'padding' in k || 'borderRadius' in k))`.

### UI-MOTION-5 [must] — Every animation ships with a designed static alternate
**Assertion.** Under `prefers-reduced-motion: reduce`, every animated affordance on the surface has a deliberate static rendering that remains legible and preserves the discrete state change — not a blanket kill.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.4 and §7 AC 8 (release-blocking); `web/src/app/globals.css`, reduced-motion block (which explicitly rejects a universal `* { animation-duration: 0 }` override); Decision 13 in `docs/design/04-rationale.md`; `docs/design/03-anti-patterns.md` §C. Related external criterion: WCAG 2.2 SC 2.3.3 Animation from Interactions (**AAA**) — repo canon is stricter, making this release-blocking.
**Verify.** Playwright with `reducedMotion: "reduce"`: assert zero running animations during a stream, and assert the reasoning label is still readable (solid `--muted-foreground`, not transparent gradient text) and the typing dot is still visible at full opacity.

### UI-MOTION-6 [must] — Reduced motion also covers scroll and disclosure
**Assertion.** Under `prefers-reduced-motion: reduce`, programmatic scrolls use `behavior: "auto"`, and drawer/dialog/collapsible transitions complete instantly while still flipping state.
**Source.** `web/src/app/globals.css` reduced-motion block (`scroll-behavior: auto !important`; `[data-slot="drawer-content"]`, `[data-slot="dialog-content"]`, `[data-slot="collapsible-content"]` at `transition-duration: 0ms`); `docs/prd/01-core-chat-experience.md` §5.6 ("reduced-motion honored on scroll/highlight").
**Verify.** Playwright with `reducedMotion: "reduce"`: tap jump-to-latest and assert the scroll completes in a single frame; open the drawer and assert it is at its final transform on the next animation frame.

### UI-MOTION-7 [must] — Motion uses the token curves
**Assertion.** Every transition and entrance uses one of `--ease-ios-smooth`, `--ease-ios-sheet`, `--ease-ios-spring` or `--ease-welcome`; no component introduces a new raw `cubic-bezier` literal.
**Source.** `web/src/app/globals.css` easing tokens (which exist specifically so "future code reuses the tokens"), the normative list for this clause — `docs/prd/06-design-system-visual-spec.md` §3.4 governs reduced motion and names no curve; `docs/design/02-patterns.md`, "Choreographed motion" ("New surfaces should use one of these and not invent a third").
**Verify.** `rg -n 'cubic-bezier\(|\bease-(out|in|in-out|linear)\b' web/src/components` returns no hit. The `cubic-bezier` half alone is strictly weaker than the assertion and passes on code that fails it: Tailwind's `ease-out` utility resolves to `cubic-bezier(0, 0, 0.2, 1)`, a fifth curve that never appears as a literal. The check fails today — see §15 C13.

### UI-MOTION-8 [should] — One disclosure moves at a time
**Assertion.** No two disclosure surfaces (drawer, sheet, dialog, popover) are in motion simultaneously; one completes before the next begins.
**Source.** `docs/design/01-foundations.md`, Motion → "Choreography of disclosure" ("only one disclosure surface is in motion at a time").
**Verify.** Playwright: trigger a second disclosure while the first is animating and assert `document.getAnimations()` never contains two running disclosure animations in the same frame.

---

## 7. Forms and the composer — `UI-COMPOSER`

### UI-COMPOSER-1 [must] — 16 px input floor on mobile
**Assertion.** Every `input`, `textarea`, `select` and `contenteditable` renders at a computed `font-size` of at least 16 px below the `md` breakpoint, and `user-scalable=no` is never used to suppress iOS zoom.
**Source.** `docs/mobile-ux/ST3-input-audit.md` (criterion and offender list); `docs/mobile-ux/ST5-spec.md` §(d) gates H1/H2; `docs/ux-best-practices/mobile-ux.md` §10 and §13 M6.
**Verify.** Playwright at 390 px: `await page.$$eval('input, textarea, select, [contenteditable]', els => els.map(e => parseFloat(getComputedStyle(e).fontSize)))`; assert every value ≥ 16. Separately assert the viewport meta contains no `user-scalable=no`.

### UI-COMPOSER-2 [must] — The composer is never covered by the keyboard
**Assertion.** On iOS Safari, with the software keyboard open and the composer at any height from one line to its maximum, the composer and its Send/Stop control remain fully visible above the keyboard, and tapping the composer does not yank the thread scroll position.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.3 (acceptance, marked "Corrected (verified, blocking)") and §9; `docs/ux-best-practices/mobile-ux.md` §13 M5/M12; platform behaviour: the iOS software keyboard resizes only the **visual** viewport, so `dvh`/`svh`/`lvh` do not shrink and `visualViewport` is the primary mechanism.
**Verify.** **Manual, real device.** Chromium-only Playwright cannot prove this (`web/playwright.config.ts`). Run the iOS lab pass named in `docs/prd/03-mobile-cross-platform.md` §9 across multiple iPhone/iOS versions, at one line and at the composer's max height, in portrait and landscape.

### UI-COMPOSER-3 [must] — Send and Stop occupy the same slot
**Assertion.** The Stop control appears in the same position and at the same size as Send, is reachable without scrolling during streaming, meets the 44 px touch floor, and is styled neutrally.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.2 ("Send morphs to Stop in the same slot; Stop is 44x44px minimum on mobile"); `docs/prd/01-core-chat-experience.md` §5.1; `docs/design/02-patterns.md`, "Thumb zone primacy"; Decision 10 in `docs/design/04-rationale.md`.
**Verify.** Playwright: record the Send button's `boundingBox()`, send a message, assert the Stop control's box matches within 1 px, that its computed background is not the destructive token, and that it is in the viewport without scrolling.

### UI-COMPOSER-4 [must] — Composer keybindings behave per platform, and IME wins
**Assertion.** On desktop, `Enter` sends and `Shift+Enter` inserts a newline; on touch, `Enter` inserts a newline and only the Send control sends; while an IME composition is active (`event.isComposing` or `keyCode === 229`), neither `Enter` nor `Esc` is intercepted.
**Source.** `docs/prd/01-core-chat-experience.md` §5.3 (including the "IME caveat" note); `docs/prd/03-mobile-cross-platform.md` §4.3 ("Mobile Enter = newline", "IME composition handling").
**Verify.** Playwright: dispatch a `keydown` with `isComposing: true` during a stream and assert generation is not stopped; then dispatch `Enter` at 1280 px and assert send fires, and at 390 px with touch and assert a newline is inserted.

### UI-COMPOSER-5 [must] — Composer focus is the only ambient accent illumination
**Assertion.** The focused composer shows the brand edge plus halo (`--shadow-focus-edge` / `--shadow-focus-halo`) while focused, and no other resting surface on the working thread carries a persistent brand glow.
**Source.** `docs/design/02-patterns.md`, "Focus as the brand moment"; Decision 07 in `docs/design/04-rationale.md`; `web/src/app/globals.css` focus-glow tokens. The hero glow tokens (`--shadow-hero-edge` / `--shadow-hero-halo`) are welcome-surface-only per `docs/prd/06-design-system-visual-spec.md` §3.1 and Decision 16.
**Verify.** Playwright: focus the composer, assert the capsule's computed `box-shadow` contains the resolved focus-glow values; then assert no element on a non-welcome thread resolves `--hero-glow-edge` or `--hero-glow-halo`.

### UI-COMPOSER-6 [must] — Mobile keyboard hints are set
**Assertion.** The composer textarea sets `enterkeyhint="send"` and appropriate `inputmode` / `autocapitalize` / `autocorrect`, and auto-grows from one line to a bounded maximum before scrolling internally.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.3 ("auto-grow textarea ... set `enterkeyhint="send"`, `inputmode`, and sensible `autocapitalize`/`autocorrect`").
**Verify.** Playwright: assert the attributes on `[data-testid="composer-textarea"]`; type 20 lines and assert the element's height stops growing and `scrollHeight > clientHeight`.

### UI-COMPOSER-7 [must] — A control with no route is absent or disabled, never silently dead
**Assertion.** Capability-gated composer controls (attach, mic, web search, reasoning effort, provider section) are hidden or visibly disabled with a one-line reason when no capable route is configured; none renders as an enabled control that does nothing.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.6 and §7 AC 11; `docs/prd/03-mobile-cross-platform.md` §4.9 ("no feature silently fails; unsupported features are hidden or clearly labeled").
**Verify.** Playwright against the fake-provider fixture with the capability off: assert the control is absent, or present with `disabled` and an adjacent explanatory string.

### UI-COMPOSER-8 [must] — Fields declare their purpose
**Assertion.** Inputs that collect information about the user (email, API key, display name) carry an appropriate `autocomplete` token and a programmatically associated label.
**Source.** WCAG 2.2 SC 1.3.5 Identify Input Purpose (AA) and SC 3.3.2 Labels or Instructions (A). Repo canon is silent on `autocomplete` (see §15 C6); the clause is `[must]` because both criteria fall inside the WCAG 2.2 AA bar C2 sets.
**Verify.** Playwright: for each field in the auth and BYOK forms, assert a non-empty accessible name and, for user-information fields, a non-empty `autocomplete` attribute.

---

## 8. Streaming and live regions — `UI-STREAM`

### UI-STREAM-1 [must] — The message body is never a live region
**Assertion.** No element containing streamed assistant text carries `aria-live`, `role="status"`, `role="alert"` or `role="log"`, directly or by inheritance.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.5; `docs/prd/01-core-chat-experience.md` §5.7; `docs/prd/08-error-and-limit-states.md` §9; `docs/design/03-anti-patterns.md` §H; Decision 14 in `docs/design/04-rationale.md`.
**Verify.** Playwright during a stream: `await page.$$eval('[data-testid="assistant-message"]', els => els.some(e => e.closest('[aria-live], [role=status], [role=alert], [role=log]')))`; assert `false`.

### UI-STREAM-2 [must] — Exactly one polite status region
**Assertion.** The document contains exactly one `role="status" aria-live="polite"` generation-status region, it is `aria-atomic="true"` and visually hidden, and it announces discrete transitions only.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.5; shipped as `web/src/components/chat/live-region.tsx`.
**Verify.** Playwright: `expect(page.locator('[role="status"][aria-live="polite"][aria-atomic="true"]:not([aria-label])')).toHaveCount(1)`. The `aria-label` exclusion is load-bearing and the `toHaveCount(1)` alone cannot pass on compliant code: every toast carries a label, and so does the per-message copy-status region in `web/src/components/chat/user-message.tsx`, one per user turn. This clause governs the single generation-status region only.

### UI-STREAM-3 [must] — The three transitions are announced
**Assertion.** "Generating", "Response ready" and "Stopped" each reach the status region exactly once per turn in which they occur; the completed message body is navigable but not auto-announced.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.5; `docs/prd/08-error-and-limit-states.md` §9 (success-path completion announcement, announced once); `docs/prd/01-core-chat-experience.md` §5.7.
**Verify.** Playwright: subscribe a `MutationObserver` to the status region across a normal turn and a stopped turn; assert the observed text sequence and that no announcement repeats.

### UI-STREAM-4 [must] — Pre-first-token indicator within 150 ms, replaced by content
**Assertion.** A typing/skeleton indicator becomes visible within 150 ms of send, is `aria-hidden` (its meaning is carried by the status region), and is never on screen at the same time as streamed content for the same message.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.2; `docs/prd/01-core-chat-experience.md` §4.1 AC ("never shown simultaneously with content"); shipped as `web/src/components/chat/typing-indicator.tsx` (`aria-hidden="true"`).
**Verify.** Playwright: timestamp the click and the indicator's first visibility, assert the delta ≤ 150 ms; then assert the indicator is detached before the first token node appears.

### UI-STREAM-5 [must] — Auto-scroll never fights the reader
**Assertion.** If the user has scrolled away from the bottom, incoming tokens do not move the viewport; the jump-to-latest control appears instead, and tapping it re-pins to the bottom and resumes following.
**Source.** `docs/prd/01-core-chat-experience.md` §5.1; `docs/prd/03-mobile-cross-platform.md` §4.4 (acceptance); `docs/design/03-anti-patterns.md` §C, "Auto-scroll that fights the reader".
**Verify.** Playwright: mid-stream, scroll up 400 px, record `scrollTop`, wait 2 s, assert `scrollTop` is unchanged and `getByRole('button', { name: 'Jump to latest' })` is visible; click it and assert following resumes.

### UI-STREAM-6 [must] — Hidden transient controls leave the a11y tree
**Assertion.** A transient control that is visually hidden (the jump-to-latest FAB at bottom, a fading action row) is also `aria-hidden`, `tabIndex={-1}` and `pointer-events: none`; it is never a focusable invisible target.
**Source.** `web/src/components/chat/message-list.tsx` (the FAB's documented hidden-state contract); WCAG 2.2 SC 2.4.7 Focus Visible (AA) — a focused element that is invisible fails it.
**Verify.** Playwright: at the bottom of the thread, assert the FAB has `aria-hidden="true"` and `tabIndex === -1`; Tab through the surface and assert focus never lands on it.

### UI-STREAM-7 [must] — Stop preserves partial output
**Assertion.** After Stop, the partial message remains rendered and actionable (copy, regenerate available), a neutral "Stopped" marker is shown, and nothing in the UI implies the partial content was lost.
**Source.** `docs/prd/01-core-chat-experience.md` §4.1 AC and §5.1; `docs/prd/08-error-and-limit-states.md` §6 rule 5 and §8; `docs/prd/06-design-system-visual-spec.md` §5.2.
**Verify.** Playwright: stop mid-stream, assert the message text length is unchanged after 1 s, assert the copy and regenerate controls are enabled, and assert the "Stopped" chip's computed color is not the destructive token.

### UI-STREAM-8 [must] — The renderer never flashes raw markdown
**Assertion.** During streaming, no frame renders an unbalanced fence, a bare `*`/`#`/backtick run, a partially parsed table row or an unbalanced math delimiter as literal text.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4 ("streaming-safe parsing ... never render raw `*`/`#`/backticks as a flash"; "render only once delimiters are balanced").
**Verify.** Playwright: sample `innerText` of the streaming message every animation frame through a fixture that streams a fenced block, a table and `$$…$$`; assert no sample contains an unclosed fence marker or a lone `$$`.

---

### UI-STREAM-9 [must] — A failed turn keeps its body and offers recovery
**Assertion.** When a turn ends in `error`, the assistant bubble is never empty: the partial text stays rendered and a named recovery control is present and enabled.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.6, interrupted-stream recovery: "*AC:* no empty/broken bubble; actions work after reload"; `docs/prd/08-error-and-limit-states.md` §8.
**Why it is written against `error`.** PRD 08 §8 names an `interrupted` terminal. The frontend has no such status: `StreamStatus` in `web/src/lib/types.ts` is `idle | submitted | streaming | done | awaiting_approval | stopped | error`, which collapses `interrupted` onto `error` and adds a terminal the PRD omits. A clause turning on a status that does not exist could not be run, so this one is written against the shipped statuses. §15 C34 records the divergence.
**Scope.** The live turn only. UI-STREAM-7 owns the Stop path and the `stopped` chip, and the two must not overlap. PRD 03 §4.6's AC also says "actions work after reload", and that half is deliberately not asserted here: a failed turn persists no assistant row, so the bubble does not survive a reload and no shipped status carries the persisted-partial behaviour PRD 08 §8 attaches to `interrupted`. §15 C34 records it. Asserting it would make this clause fail on every build until that behaviour ships.
**Verify.** Playwright with the fake provider: send a prompt beginning `FORCE_ERROR:`, which fails the stream after two answer deltas. Wait for the assistant message's `data-status` to read `error`. Assert its text content is non-empty and that the **Retry** control inside it is enabled.

## 9. Transparency surfaces — `UI-TRUST`

### UI-TRUST-1 [must] — Every assistant message carries attribution without hover
**Assertion.** 100% of finished assistant messages render the attribution component showing served model and tier, visible without hover, focus or expansion — including after a reload.
**Source.** `docs/prd/07-transparency-contract.md` §6.1 and §8 AC 1; `docs/prd/06-design-system-visual-spec.md` §5.4 and §7 AC 1; `docs/design/03-anti-patterns.md` §F, "Hover-only cost or model details"; Decision 12 in `docs/design/04-rationale.md`.
**Verify.** Playwright: send three turns, reload, and assert `getByTestId('message-attribution')` has the same count as `getByTestId('assistant-message')` and each contains the served model label with no pointer interaction.

### UI-TRUST-2 [must] — Any substitution reason renders a visible callout
**Assertion.** When a turn carries a non-null substitution reason, a visible callout names the requested model/tier, the served model/tier and the reason; it is not hover-only and not an error treatment.
**Source.** `docs/prd/07-transparency-contract.md` §5 AC and §6.1; `docs/prd/06-design-system-visual-spec.md` §5.4 and §7 AC 2; `docs/prd/08-error-and-limit-states.md` §5.7.
**Verify.** Playwright against forced `rate_limited`, `auto_downgrade` and `capacity_reroute` fixtures: assert `[data-testid="attribution-substitution"]` is visible and its text contains requested, served and reason.

### UI-TRUST-3 [must] — No per-turn cost figure in the thread
**Assertion.** No assistant message renders an inline cost figure or cost-breakdown popover in the thread; each finished assistant message instead exposes a keyboard-reachable, accessibly named **View spend** affordance that opens the spend breakdown.
**Source.** `docs/prd/07-transparency-contract.md` §6.1, §8 AC 9 and §10 open question 2 (D41); `docs/prd/06-design-system-visual-spec.md` §5.4 and §8 open question 2. Shipped as the **View spend** item in the message overflow menu (`web/src/components/chat/message-actions.tsx`), which opens the Settings hub on its General tab and scrolls the spend breakdown into view.
**Where it lives, and why not the byline.** It is a button in the message overflow menu, not a link in the attribution row. Two reasons. It opens a dialog rather than navigating, so `role="link"` would tell a screen-reader user the wrong thing about what happens next. And the footer already splits into a metadata byline (facts, always visible) and an action cluster (verbs, in the overflow); a "View spend" control repeated visibly under every answer is the same thread noise that the no-inline-cost rule exists to prevent.
**Verify.** Playwright on a finished turn: assert the attribution row contains no `$` figure; open `[data-testid="message-actions-overflow"]`, click `[data-testid="view-spend"]`, and assert `[data-testid="spend-analytics-panel"]` is visible. Landing on the tab is not enough — the General tab is a scroll container and the breakdown sits below the account block, so the check is that the breakdown itself is on screen.

### UI-TRUST-4 [must] — Cost that is shown labels its confidence
**Assertion.** Wherever a cost figure is displayed (Spend hub, usage meter, model-picker list prices, agentic run meter), a non-exact computation is explicitly labeled as an estimate or as unavailable; a route with no published rate never renders an exact `$0.00`.
**Source.** `docs/prd/07-transparency-contract.md` §6.1 ("estimate labels must be explicit"), §7 rule 2 and §8 AC 4; `docs/prd/06-design-system-visual-spec.md` §5.4.
**Verify.** Playwright against a fixture whose `cost_confidence` is not `exact`: assert the rendered figure is adjacent to an estimate label and is not an exact-formatted zero.

### UI-TRUST-5 [must] — Public share strips cost, tokens and memory, keeps model and web sources
**Assertion.** A public share view shows served model attribution and substitution callouts, and shows the web sources the private turn carried. It shows no cost figure, token count or breakdown, and no memory chip, memory count or memory fact id, anywhere in its markup or embedded JSON.
**Source.** `docs/prd/07-transparency-contract.md` §6.4 matrix and AC, and §8 AC 6; `docs/prd/06-design-system-visual-spec.md` §5.9 and §7 AC 3.
**Why the memory and sources halves live here.** PRD 07 §8 AC 6 states three things about a public share, and this clause originally asserted one of them. The memory half is already structurally guaranteed — `memory_applied` and `memory_fact_ids` sit on the private `ModelAttribution` in `api/app/schemas/message.py`, and `PublicAttribution` in `api/app/schemas/share.py` does not carry them — so the assertion pins a guarantee that exists rather than requesting a change. The web-sources half ships too: `SourcesPart` passes through the public parts union unmodified. Folding both in here beats a second clause, because a reviewer checking a share view should read one clause, not three.
**Not asserted here.** AC 6 also requires a redacted marker for `knowledge` and `connector` sources, and retention of generated-media provenance. Neither ships — §15 C32.
**Verify.** Playwright: mint a share link from a conversation whose private turn rendered a sources panel. Fetch the public page, assert the rendered text contains the model label, assert the sources panel renders, and assert the page HTML matches neither `/cost_usd|costUsd|tokens?\b.*\d|cost_breakdown/` nor `/memory_applied|memoryApplied|memory_fact_ids|memoryFactIds/`.

### UI-TRUST-6 [must] — Transparency chrome is typographically first-class
**Assertion.** The attribution row uses the same font stack as the answer, one step down the ramp, with a muted-but-readable color meeting the 4.5:1 body threshold; it is not a smaller secondary stack.
**Source.** `docs/design/02-patterns.md`, "Transparency as product surface"; `docs/prd/06-design-system-visual-spec.md` §3.1 (contrast) and §5.4; `docs/mobile-ux/ST5-spec.md` §(e) risk R10 (the private and public rows must converge on `.ui-caption`).
**Verify.** Computed style: the attribution row's `font-family` matches the body's, its `font-size` is the `.ui-caption` step, and its color/background pair computes ≥ 4.5:1. Assert the same values on `web/src/components/share/public-attribution-row.tsx`.

### UI-TRUST-7 [must] — The expand control is keyboard-reachable and named
**Assertion.** Any attribution or reasoning detail that expands does so via a real button with an accessible name and a correct `aria-expanded` state.
**Source.** `docs/design/02-patterns.md`, "Transparency as product surface" (interaction-design half) and "Progressive disclosure"; `docs/prd/01-core-chat-experience.md` §5.7 ("reasoning panel exposes expanded/collapsed state via ARIA").
**Verify.** Playwright: `expect(toggle).toHaveAttribute('aria-expanded', 'false')`, press Enter, assert it flips to `'true'` and the panel is in the accessibility tree.

### UI-TRUST-8 [must] — The collapsed summary is sufficient
**Assertion.** The collapsed reasoning panel states the duration ("Thought for Xs"), and the collapsed attribution row states served model and tier — so the common case needs no expansion.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.3 and §5.4; `docs/prd/01-core-chat-experience.md` §5.2 state table; `docs/design/02-patterns.md`, "Progressive disclosure"; Decision 09 in `docs/design/04-rationale.md`.
**Verify.** Playwright on a reasoning-bearing turn: assert the collapsed bar's text matches `/Thought for \d+/` and the attribution row's text contains the model label before any expansion.

---

### UI-TRUST-9 [must] — The AI-interaction disclosure renders on the entry surface
**Assertion.** The empty state renders a disclosure with `role="note"` and a non-empty accessible name, whose text states that the responder is an AI and that its answers may be wrong.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.8, bullet 1; `docs/ux-best-practices/desktop-ux.md` §12 (EU AI Act Article 50(1)).
**Canon says more than the code ships.** PRD 06 §5.8 says "persistent". The shipped ruling places the disclosure on the welcome surface only: `web/src/components/chat/ai-disclosure.tsx` is mounted at one call site, `welcome-screen.tsx`, and its own header comment records that the below-composer placement was deliberately removed as chrome clutter. UI-STATE-7 requires the welcome surface to unmount on first send, so the disclosure does leave the thread. This clause asserts the shipped ruling so that it decides something. §15 C31 records the disagreement and is where an amendment to PRD 06 §5.8 belongs. Do not read this clause as ratifying "persistent".
**Verify.** Playwright on a fresh session: assert `getByTestId("ai-interaction-disclosure")` is visible, that its `role` is `note`, that its `aria-label` is non-empty, and that its text contrast clears the UI-COLOR-3 floor.

### UI-TRUST-10 [must] — A temporary thread renders its banner
**Assertion.** While a conversation is in temporary mode, the thread renders a banner that names the mode, states that the conversation is not saved, and carries a control to leave the mode.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.8, bullet 2; `docs/prd/01-core-chat-experience.md` §4.8 AC: "starting a temporary chat sets `chat.is_temporary = true` and the UI shows a temporary-chat banner."
**Scope.** The banner only. The same PRD bullet also asks for "distinct thread treatment", which is not decidable as canon states it and which no clause asserts — §15 C37 records that silence. PRD 01 §4.8 makes the banner an acceptance criterion, and the banner is the half this clause can decide.
**Verify.** Playwright: start a temporary chat, assert `getByTestId("temporary-chat-banner")` is visible, assert its text names the mode and says the chat is not saved, and assert the control that leaves the mode is enabled.

### UI-TRUST-11 [must] — The composer names the selected route before send
**Assertion.** The composer renders a control stating the model tier currently selected, before any message is sent, with an accessible name containing that tier's label. The control follows the selection when it changes.
**Source.** `docs/prd/07-transparency-contract.md` §6.2 **[P0]**, bullet 1: "Show selected tier/model before send."
**Scope.** The *selected* tier, never the served route. Auto resolves at send time, so under Auto the correct pre-send label is "Auto". The served route is UI-TRUST-1's claim and this clause must not duplicate it. UI-COMPOSER-7 governs whether a capability-gated control is absent or disabled, not what the picker displays. Section 9's other clauses are all post-turn, which is what left this half uncovered.
**Verify.** Playwright at 1280 px and at 390 px: assert the visible `[data-testid="model-mode-trigger"]` is present and that its `aria-label` contains the selected tier's label. Change the tier through the picker and assert the label follows the change.

### UI-TRUST-12 [must] — No reasoning means no panel and no affordance
**Assertion.** When a turn emits no reasoning content, the message renders neither a reasoning panel nor its expand affordance. No empty panel, and no chevron with nothing behind it.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.3, bullet 3: "Hidden entirely when no reasoning/summary is emitted"; `docs/prd/01-core-chat-experience.md` §4.2 AC: "If no reasoning content is emitted, no panel/affordance appears (no empty panel)."
**Scope.** UI-TRUST-7 asserts the toggle's `aria-expanded` and UI-TRUST-8 asserts the collapsed bar's text. Both presuppose a panel exists, so neither forbids an empty one. The affordance half matters as much as the panel half, because a chevron rendered with nothing behind it is the likelier regression.
**Verify.** Playwright with the fake provider: send a prompt beginning `NO_REASONING:`, the one marker that makes the fake skip its reasoning block (`api/app/providers/fake.py`). Assert `getByTestId("reasoning-panel")` has count 0 within that assistant message, and assert no control whose accessible name matches `/reasoning|thought/i` exists within it.

### UI-TRUST-13 [must] — A link in an answer shows where it goes and opens apart from the chat
**Assertion.** Activating a link in assistant prose shows the destination's host on screen before anything opens, then opens the destination in a new browsing context that has no `window.opener` and receives no referrer, leaving the chat tab where it was.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4, Links ("open in new tab, `rel="noopener noreferrer"`; show domain on hover"). Shipped through Streamdown's default link-safety step: `web/src/components/chat/markdown-renderer.tsx` passes no `linkSafety` prop, so each link renders as `[data-streamdown="link"]`, a `button` that opens a confirmation showing the full URL, whose "Open link" calls `window.open(url, "_blank", "noreferrer")`. The `noreferrer` feature implies `noopener`.
**Scope.** Links in `.chat-md` only. Source chips and citation chips are out of scope. The PRD's "on hover" and the shipped confirmation step are two routes to the same guarantee, and the clause asserts the guarantee — §15 C49.
**Verify.** Playwright at 1280 px. The fake provider emits no link, so serve the turn: `page.route("**/api/conversations/*/messages", r => r.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: 'event: submitted\ndata: {"messageId":"11111111-1111-4111-8111-111111111111"}\n\nevent: answer_delta\ndata: {"text":"See [the guide](https://example.com/docs/page)."}\n\nevent: terminal\ndata: {"status":"done","messageId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}\n\n' }))`, the frame shape `web/tests/e2e/streaming.spec.ts` already uses, and `context.route("https://example.com/**", r => r.fulfill({ body: "<title>ok</title>" }))`. Send any message and wait for the link inside the last `.chat-md`. If it is an `a`, assert `target="_blank"` and a `rel` containing `noreferrer` (which implies `noopener` in the HTML standard), and assert its `title` or an adjacent visible element names `example.com` on hover. If it is `[data-streamdown="link"]` as a `button`, click it and assert `[data-streamdown="link-safety-modal"]` is visible and contains `example.com`. In either case, activate the link (or "Open link"), take the new page from `context.waitForEvent("page")`, assert `await popup.evaluate(() => window.opener === null && document.referrer === "")`, and assert the chat page's URL is unchanged.

## 10. Error, empty and limit states — `UI-STATE`

### UI-STATE-1 [must] — Severity maps to pattern
**Assertion.** An error's `severity` selects its pattern exactly: `info` → inline hint/meter text, `warning` → composer banner, `error` → inline message error with retry, `blocking` → modal or disabled send with a CTA.
**Source.** `docs/prd/08-error-and-limit-states.md` §4 table; visual primitives per `docs/prd/06-design-system-visual-spec.md` §5.
**Verify.** Playwright: drive each severity through the fixture and assert the rendered pattern's role and placement match the table row.

### UI-STATE-2 [must] — Announcement role matches severity
**Assertion.** Warnings announce through `role="status"`; `role="alert"` is used only where immediate attention is required; stream errors are announced once, when generation ends.
**Source.** `docs/prd/08-error-and-limit-states.md` §9; WCAG 2.2 SC 4.1.3 Status Messages (AA).
**Verify.** Playwright: observe the a11y tree across a warning and a blocking error; assert the role on each and assert the error text appears exactly once.

### UI-STATE-3 [must] — Counts and countdowns are composed from structured data
**Assertion.** Limit copy renders counts from `meta.used` / `meta.limit` and a live-ticking reset from `retry_after_ms` or `meta.reset_at`; no count or duration is baked into the `body` string, and the blocking affordance clears when the countdown reaches zero.
**Source.** `docs/prd/08-error-and-limit-states.md` §3 ("counts and reset time are structured data, not free text") and §6 rule 7.
**Verify.** Playwright: serve a `PLATFORM_BUDGET_EXCEEDED` payload with `retry_after_ms = 5000`; assert the rendered countdown decrements within 2 s and the send control re-enables at zero.

### UI-STATE-4 [must] — Meter thresholds drive the escalation
**Assertion.** Quota display escalates exactly at the documented thresholds: meter only below 80%, info banner 80–94%, warning banner plus tier/BYOK nudge 95–99%, blocking at 100% with no provider call made.
**Source.** `docs/prd/08-error-and-limit-states.md` §7 table; `docs/prd/06-design-system-visual-spec.md` §5.5; `docs/prd/07-transparency-contract.md` §6.3.
**Verify.** Playwright: step the usage fixture through 79 / 80 / 94 / 95 / 99 / 100 and assert the rendered pattern at each step; at 100, assert no outbound provider request is made.

### UI-STATE-5 [must] — Error copy leads with outcome and offers recourse
**Assertion.** Every user-visible error states the outcome before the cause, offers at least one action and at most three, never blames the user for a provider failure, and never implies persisted partial content was lost.
**Source.** `docs/prd/08-error-and-limit-states.md` §6 rules 1–5.
**Verify.** Manual copy review per error code against §6, using the canonical payload's `title` / `body` / `actions[]`. More than three actions, none at all, or a cause-first title fails. Note the source sets a ceiling, not a floor — §6 rule 3 reads "Offer 2–3 actions **max**" — so a single well-chosen action passes, and every shipped envelope carries exactly one.

### UI-STATE-6 [must] — The meter is a labeled progress element
**Assertion.** The usage/budget meter exposes `role="progressbar"` with an accessible name, `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and an `aria-valuetext` carrying the human-readable detail.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.5; shipped in `web/src/components/chat/usage-meter.tsx`.
**Verify.** Playwright: `expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuetext', /.+/)` and assert the accessible name is non-empty.

### UI-STATE-7 [must] — The empty state is one hero plus a small card set
**Assertion.** The empty/welcome state renders one hero element and a small set of prompt cards (3–4) — not a feature grid, capability wall, marketing copy or dismissable banner — and unmounts after the first send.
**Source.** `docs/prd/06-design-system-visual-spec.md` §4 ("empty state: greeting + 3–4 prompt cards"); `docs/design/02-patterns.md`, "Empty state earns distinctiveness"; `docs/design/03-anti-patterns.md` §F and §G; Decision 11 in `docs/design/04-rationale.md`.
**Verify.** Playwright: on a fresh session assert the prompt-card count is ≤ 4; send a message and assert the welcome surface is detached and does not reappear in the same conversation.

### UI-STATE-8 [must] — A self-dismissing toast waits for the user who is reading it
**Assertion.** A toast that dismisses itself on a timer pauses that timer while the pointer is over it or focus is inside it, and a toast that carries an action never dismisses itself.
**Source.** WCAG 2.2 SC 2.2.1 Timing Adjustable (A) — a message that removes itself on a clock is a time limit the user did not set; `docs/prd/06-design-system-visual-spec.md` §2, Goals ("Meet WCAG 2.1 AA"), where 2.2.1 is Level A. The shipped timer is `defaultDurationFor` in `web/src/components/ui/toast.tsx`: `info` and `success` close after 5000 ms, `warning` and `error` persist, and the `setTimeout` in `ToastItem` is not paused by hover or focus.
**Scope.** The timer only. Which severity a failure takes is UI-STATE-1's, and its announcement role is UI-STATE-2's. No consumer passes `actions` today, so the second half binds the first caller that does.
**Verify.** Playwright at 1280 px without touch, on a finished turn. (1) Activate "Branch in new chat", which raises the `info` toast "Branched into new chat". As soon as `getByRole("status", { name: "Information" }).filter({ hasText: "Branched into new chat" })` is visible, hover it, wait 6 s, and assert it is still visible. Move the pointer away and assert it is gone within 6 s. (2) Repeat, focusing its "Dismiss notification" button instead of hovering. (3) Code read: in `web/src/components/ui/toast.tsx`, a record with a non-empty `actions` must resolve its duration to `null`. Fails today on all three — §15 C48.

---

## 11. Mobile viewport and safe areas — `UI-MOBILE`

### UI-MOBILE-1 [must] — `viewport-fit=cover` is set
**Assertion.** The document's viewport meta includes `viewport-fit=cover`, without which every `env(safe-area-inset-*)` resolves to zero.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.3 ("required for `env(safe-area-inset-*)` to be non-zero at all"); shipped in the `viewport` export of `web/src/app/layout.tsx` (`viewportFit: "cover"`).
**Verify.** Playwright: assert the rendered `<meta name="viewport">` content contains `viewport-fit=cover`.

### UI-MOBILE-2 [must] — All four insets are honored on edge-anchored chrome
**Assertion.** Header, composer, bottom sheets, the command palette sheet, toasts and the install coachmark each apply the safe-area inset on every viewport edge they are anchored to — not the bottom inset alone — so nothing sits under the notch, the home indicator or a landscape inset. A surface anchored to three edges owes three insets, not four: read literally as "all four on every surface", this clause would fail the header (which is not bottom-anchored) and the bottom sheet (which is not top-anchored), and its own Verify takes the per-edge reading.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.3 ("Composer/header respect all four `safe-area-inset-*`"); `docs/prd/03-mobile-cross-platform.md` §4.3; `docs/design/01-foundations.md`, Spacing → "Safe areas as floors"; `docs/mobile-ux/ST4-native-gap-audit.md` G2/G3/G10.
**Verify.** Playwright: emulate a device with non-zero insets (or shim the four `env()` values), then assert each edge-anchored element's padding on that edge is ≥ the inset. Confirm on real hardware for the landscape-iPhone case.

### UI-MOBILE-3 [must] — The bottom inset has a desktop floor
**Assertion.** Bottom-anchored chrome positions from `--bottom-inset` (`max(env(safe-area-inset-bottom), 1.5rem)`), so it never sits flush against the viewport edge on a device with no inset.
**Source.** `docs/design/01-foundations.md`, Spacing → "Safe areas as floors" (the floor pattern); `web/src/app/globals.css` `--bottom-inset`; `docs/prd/06-design-system-visual-spec.md` §3.3.
**Verify.** `rg -n 'safe-area-inset-bottom' web/src/components` — a bottom-anchored surface using the raw inset instead of `--bottom-inset` fails unless it also supplies its own floor via `max()`.

### UI-MOBILE-4 [must] — Full-height surfaces use `dvh`, never raw `vh`
**Assertion.** No app-shell or full-height surface sizes with raw `vh`; the shell uses `dvh`, with `svh`/`lvh` only where the specific behaviour is wanted.
**Source.** `docs/prd/03-mobile-cross-platform.md` §5.3 ("prefer `dvh` for the app shell"; sizing to `lvh` shows a white strip on iOS until first scroll).
**Verify.** `rg -n '\b[0-9]+vh\b|h-screen' web/src` returns no hit on a layout surface.

### UI-MOBILE-5 [must] — Scroll chaining and pull-to-refresh cannot kill a stream
**Assertion.** `html`/`body` set `overscroll-behavior: none`, every inner scroller sets `overscroll-contain`, and no surface implements pull-to-refresh on the conversation.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.4 (`overscroll-behavior: contain`; pull-to-refresh explicitly dropped); `web/src/app/globals.css` base layer; `docs/mobile-ux/ST4-native-gap-audit.md` G5/G7.
**Verify.** Playwright: assert `getComputedStyle(document.body).overscrollBehavior === "none"`, and for every `overflow-y: auto` container in the surface assert `overscrollBehavior` contains `contain`.

### UI-MOBILE-6 [must] — Primary actions live in the thumb zone
**Assertion.** On mobile, the actions that drive a turn (Send, Stop, tier picker, new chat) are reachable in the bottom third of the viewport; no primary action is parked exclusively in the top-right corner.
**Source.** `docs/design/02-patterns.md`, "Thumb zone primacy"; `docs/prd/03-mobile-cross-platform.md` §5.3 ("primary actions in the thumb zone (bottom third)").
**Verify.** Playwright at 390×844: assert the `boundingBox().y` of Send/Stop and of the tier control is ≥ 2/3 of the viewport height, and that a new-chat affordance exists at or below that line or in the drawer.

### UI-MOBILE-7 [must] — Back dismisses overlays in order
**Assertion.** Opening the mobile navigation drawer pushes a history entry, so the device/gesture Back dismisses the drawer before leaving the chat route.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.2 ("History API integration"). The PRD asks for this on every overlay; only the drawer ships it, so the clause is scoped to what a reviewer can decide today — see §15 C14 for the sheets and panels.
**Verify.** Playwright at a mobile viewport: open the navigation drawer, `page.goBack()` once, assert the drawer is closed and the URL is still the chat route. Do not extend this to a sheet opened over the drawer until C14 is closed — today the drawer would close first, which is the inverse of the order the PRD names.

### UI-MOBILE-8 [should] — Unsupported platform features are hidden, not broken
**Assertion.** On a platform where a capability is unavailable (Web Speech in an installed iOS PWA, web push in a Safari tab, haptics on iOS), the affordance is hidden or clearly labeled and the rest of the surface degrades silently.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.9 acceptance ("no feature silently fails") and §6.4; `docs/mobile-ux/ST4-native-gap-audit.md`, iOS caveat.
**Verify.** **Manual** on the real platform, plus a code check that the capability is feature-detected rather than user-agent-sniffed.

---

## 12. Forced colors, contrast and transparency preferences — `UI-PREF`

### UI-PREF-1 [must] — Boundaries survive forced colors
**Assertion.** Under `forced-colors: active`, every glass surface and every flat-filled bubble keeps a visible boundary drawn with a system color keyword, not an inset box-shadow (which forced colors strips).
**Source.** `web/src/app/globals.css`, `@media (forced-colors: active)` block (restores `border: 1px solid CanvasText` on the glass utilities and on the user-message bubbles); `docs/ux-best-practices/desktop-ux.md` §10 (honor `forced-colors`); WCAG 2.2 SC 1.4.11 Non-text Contrast (AA).
**Verify.** Playwright: `await page.emulateMedia({ forcedColors: 'active' })`; assert `borderTopWidth !== "0px"` on the composer capsule, dialog and user bubble, and screenshot for visual confirmation.

### UI-PREF-2 [must] — Reduced transparency collapses glass to a solid surface
**Assertion.** Under `prefers-reduced-transparency: reduce`, no element has a non-`none` `backdrop-filter`, and every former glass surface renders on an opaque `--card` / `--popover` fill with a visible hairline.
**Source.** `web/src/app/globals.css`, `@media (prefers-reduced-transparency: reduce)` block; `docs/design/01-foundations.md`, Motion → "Reduced motion as principle" (the same-principle extension to reduced transparency).
**Verify.** Playwright cannot emulate this preference: `emulateMedia` has no `reducedTransparency` option through 1.60.0 and **silently ignores** one, so a probe written that way reports a green pass while testing nothing. Drive it over CDP instead: `(await context.newCDPSession(page)).send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }] })`. Then sweep **every** element in the page and assert `getComputedStyle(el).backdropFilter === "none"`, rather than a fixed class list — a class list cannot see an inline `backdrop-filter`, which no media query can reach. Assert the opaque fill on `.glass-regular`, `.glass-strong`, `.glass-capsule` and `.glass-clear` only: `.chrome-frost` is a blur-only layer with no background of its own, so it has no fill to make opaque.

### UI-PREF-3 [must] — Increased contrast zeroes decorative atmosphere
**Assertion.** Under `prefers-contrast: more`, `--welcome-ambient` and `--hero-gradient` resolve to `none` and the hero glow tokens resolve to a no-op shadow, so no atmospheric wash erodes text contrast; glass fills densify rather than thinning.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1 ("`prefers-contrast: more` zeroes them alongside `--welcome-ambient`"); `web/src/app/globals.css`, `@media (prefers-contrast: more)` block; Decision 16 in `docs/design/04-rationale.md`.
**Verify.** Playwright with `{ contrast: 'more' }` emulated: assert the resolved value of `--welcome-ambient` and `--hero-gradient` is `none`, and that `--hero-glow-halo` is a transparent no-op shadow rather than `none` (it must stay valid inside a composed `box-shadow` list).

### UI-PREF-4 [must] — Glass has a no-support fallback
**Assertion.** Where `backdrop-filter` is unsupported, glass surfaces fall back to an opaque `--card` / `--popover` fill retaining the shadow stack; no surface becomes transparent or illegible.
**Source.** `web/src/app/globals.css`, the `@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))` block.
**Verify.** Manual in a browser without `backdrop-filter` support, or by temporarily disabling the feature flag; confirm the composer capsule and dialog remain opaque and bounded.

### UI-PREF-5 [must] — The print rendering stays legible
**Assertion.** Printing the live page hides the floating chrome (frost strips, toasts, coachmark), flows the message area at full height on a white background, and does not clip virtualized rows.
**Source.** `web/src/app/globals.css`, `@media print` block.
**Verify.** Playwright: `await page.emulateMedia({ media: 'print' })`, then `page.pdf()` on a thread of **more than 80 messages**, and assert the first and the last message's text both appear in the extracted PDF text. The threshold matters: `VIRTUALIZE_AFTER` is 80 in `web/src/components/chat/message-list.tsx`, so a 30-message thread never virtualizes and cannot exercise the last half of the assertion. See §15 C15 — this check fails today.

### UI-PREF-6 [should] — Every user-preference rendering is reviewed with the visual one
**Assertion.** A PR that adds or changes a rendered surface includes evidence for the reduced-motion, reduced-transparency, increased-contrast, forced-colors and dark renderings, produced in the same review — not filed as follow-up.
**Source.** `docs/design/02-patterns.md` §E, "Keyboard, screen reader, reduced motion as renderings of one UI"; `docs/design/01-foundations.md`, Motion → "Reduced motion as principle"; `docs/prd/06-design-system-visual-spec.md` §7 AC 8.
**Verify.** Manual review-process check: the PR description names the five renderings and links evidence for each.

---

## 13. User-visible performance budgets — `UI-PERF`

### UI-PERF-1 [must] — Initial route JS stays within budget
**Assertion.** The JavaScript the browser must download for a route's first paint is at most 200 KB gzip and 700 KB raw.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.10 ("initial route JS ≤ ~200 KB compressed, enforced by a CI bundle-size check"); implemented as `web/scripts/check-bundle-size.mjs` (`BUNDLE_BUDGET_GZIP_KB` default 200, `BUNDLE_BUDGET_RAW_KB` default 700).
**Verify.** `cd web && pnpm build && pnpm check:bundle`. Raising a budget requires changing the env value in `web/package.json` and explaining why in the PR, per the script's own failure message.

### UI-PERF-2 [must] — Heavy renderers are lazy
**Assertion.** KaTeX, the syntax highlighter and the Mermaid engine are not in the initial bundle; each loads on demand when a message part needs it.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.10 ("KaTeX + syntax highlighter must be lazy-loaded, not in the initial bundle. Mermaid engine is P1 ... P0 may ship zero Mermaid JS").
**Verify.** Inspect the `check:bundle` per-chunk report for the initial set; separately, a Playwright network log on a plain-text turn shows no KaTeX/highlighter/Mermaid chunk request.

### UI-PERF-3 [must] — Field vitals stay within budget
**Assertion.** At p75 on mobile field data, LCP ≤ 2.5 s, INP ≤ 200 ms and CLS ≤ 0.1.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.10; `docs/ux-best-practices/mobile-ux.md` §11 and `docs/ux-best-practices/desktop-ux.md` §11.
**Verify.** RUM dashboard (metrics ownership per `docs/prd/05-roadmap-monetization-metrics.md`). Lab approximation: Lighthouse mobile profile plus a Playwright INP probe that types into the composer during an active stream.

### UI-PERF-4 [must] — Streaming does not re-render per token
**Assertion.** Streamed deltas are buffered and flushed once per animation frame; the surface does not perform a React state update per token, and rendering keeps up with the stream without layout shift beyond the height of newly added content.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4 (mechanism note); `docs/prd/03-mobile-cross-platform.md` §4.10 ("streaming render coalescing ... promoted P1→P0").
**Verify.** Playwright: record a performance trace across a streaming turn and assert the count of style/layout recalcs on the message subtree does not exceed the frame count; assert no layout-shift entry exceeds the added content height.

### UI-PERF-5 [must] — Bootstrap is bounded and offers a retry
**Assertion.** The first-paint bootstrap fetch is bounded by `BOOTSTRAP_TIMEOUT_MS`; on a stall, the surface shows a retry affordance rather than an unbounded spinner.
**Source.** `AGENTS.md`, "Debugging in production" item 1; shipped as `BOOTSTRAP_TIMEOUT_MS` in `web/src/components/chat/chat-thread.tsx`; `docs/ux-best-practices/desktop-ux.md` §11.
**Verify.** Playwright: `page.route('**/api/bootstrap', r => {})` to hang the request; assert a retry control becomes visible within `BOOTSTRAP_TIMEOUT_MS` + 1 s and that clicking it re-issues the request.

### UI-PERF-6 [must] — Long threads are virtualized
**Assertion.** A thread past roughly 80 messages renders a bounded window with overscan rather than the full list, and scrolling it does not drop below a usable frame rate on a mid-tier mobile profile.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.5 and §4.10; `docs/prd/01-core-chat-experience.md` §5.4 ("virtualize very long threads"); `docs/ux-best-practices/mobile-ux.md` §11.
**Verify.** Playwright: render 300 messages and assert `document.querySelectorAll('[data-testid="assistant-message"]').length` is well under 300; scroll with CPU throttling ×4 and assert no long task exceeds 200 ms.

### UI-PERF-7 [should] — FE coverage does not regress below the floor
**Assertion.** The FE e2e coverage run stays at or above the `web/.nycrc.json` floors (statements 73, lines 77, functions 75, branches 64), so new UI surfaces arrive with exercised behaviour rather than untested markup.
**Source.** `web/.nycrc.json`; `AGENTS.md`, "Lint / test / build" (the `web-coverage` CI job gates this).
**Verify.** `cd web && pnpm test:e2e:coverage && pnpm coverage:report` — the run ends in `nyc check-coverage` and fails below the floor.

---

### UI-PERF-8 [must] — A rendered image defers its load and reserves a box
**Assertion.** Every `<img>` in rendered app markup sets `loading="lazy"`. An image inside a rendered message resolves a `max-width` no wider than the reading column and paints a visible placeholder box before its bytes arrive.
**Source.** `docs/prd/01-core-chat-experience.md` §5.4 ("lazy-load, constrained max-width"); `docs/prd/03-mobile-cross-platform.md` §4.10 CLS protection.
**On the strength marker.** PRD 03 §4.10's dedicated image bullet is **[P1]**, but the CLS budget it serves is **[P0]** and PRD 01 §5.4 states the requirement without qualification. The clause is `[must]` on the strength of those two, not of the P1 bullet. A reviewer relaxing it by citing the P1 marker alone has read only one of the three sources.
**Scope.** The naming half of the same PRD bullet is UI-FOCUS-9's. A model-supplied remote URL has no intrinsic dimensions and no configured loader, so the clause asks for a reserved box rather than exact dimensions — exact dimensions are only assertable where the app itself knows them, as the source favicon does.
**Verify.** Playwright: send a prompt beginning `RICH_MARKDOWN:` and assert every `img` on the page has `loading="lazy"`. Then assert the image inside `.chat-md` resolves `max-width` to `100%` of the reading column and resolves a `background-color` that is not `rgba(0, 0, 0, 0)`, which is the reserved box.

### UI-PERF-9 [must] — A session's seams do not shift the layout
**Assertion.** Measured from navigation through bootstrap, the welcome surface, a first send, the stream, and one second past `done`, the layout-shift entries not preceded by input (`hadRecentInput === false`) sum to no more than 0.1.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.10 **[P0]** CLS protection ("reserve space for streaming content, images … and the composer") and the same section's CLS ≤ 0.1 budget; §5.3 ("Reserve space (anti-CLS)"); `docs/prd/01-core-chat-experience.md` §5.4.
**Why this is not UI-PERF-3 or UI-PERF-4.** UI-PERF-3 is the field p75, and its lab approximation is a Lighthouse load that never sends a message. UI-PERF-4 bounds each shift during streaming by the height of the content just added. Neither reaches the seams between states: the bootstrap spinner giving way to the shell, the 200 ms welcome exit (Decision 11), and the composer reflowing when the thread mounts. This clause is the session gate across all of them. One lab session must clear the budget the field holds at p75, which makes the lab reading stricter, not looser.
**Verify.** Playwright at 390×844 with touch and at 1280×800, in both themes. Before navigation, `page.addInitScript` a `PerformanceObserver({ type: "layout-shift", buffered: true })` that adds up `value` for every entry with `!hadRecentInput` and keeps each entry's `sources`; `installClsObserver` in `web/tests/audit/probes.ts` does exactly this. Navigate to `/`, wait for bootstrap, wait 1 s, send a message, wait for `data-status="done"`, wait 1 s. Assert the sum is ≤ 0.1. On a failure, report each entry's `sources` so the defect names the node that moved rather than a number.

---

## 14. Visual craft and state completeness — `UI-CRAFT`

Sections 1–13 decide whether a screen works. This section decides whether it is *made* to one system: whether its spacing, radius, elevation and icons come from the token set, whether every control has all of its states, and whether overlays, banners and floating chrome stay out of each other's way. `docs/design/00-principles.md`, High Aesthetics, is the reason the section exists — "the optical alignment of an attribution row was checked at every breakpoint" is a claim a reviewer can only make if there is something to check it against.

### UI-CRAFT-1 [must] — Spacing sits on the 4 px grid
**Assertion.** Every margin, padding and gap between components, and every container gutter, resolves at the default root size to 0, 1 px or a multiple of 4 px; inside a single control or inline chip — `button`, `[role=menuitem|option|tab]`, `code`, `[data-slot=badge]` and their descendants — multiples of 2 px up to 14 px are also admitted.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.3 ("4px base grid", and its sub-step bullet admitting 2 px steps inside a control or inline chip), which wins on the value under §0's precedence rule; `docs/design/01-foundations.md`, Spacing → "A strict base grid, generous gutters" ("every gutter is a deliberate multiple"); `docs/design/00-principles.md`, Tension 4 (the spacing scale is "defined once in PRD 06 and not negotiated per surface").
**Verify.** (1) No component or stylesheet writes an arbitrary spacing value other than a composition of `env(safe-area-inset-*)` or `--bottom-inset` with an on-grid floor: `rg -nP '(?<![\w-])-?(p[xytrblse]?|m[xytrblse]?|gap(-[xy])?|space-[xy])-\[' web/src/components web/src/app/globals.css`, where every hit must contain `safe-area-inset` or `--bottom-inset`. (2) Playwright at 390 px and at 1280 px, on the welcome surface, a thread with a `RICH_MARKDOWN:` turn, and each dialog: for every rendered element `el` read `marginTop`/`Right`/`Bottom`/`Left`, `paddingTop`/`Right`/`Bottom`/`Left`, `rowGap` and `columnGap`, and with `const on = (a, n) => Math.abs(a / n - Math.round(a / n)) < 0.01` and `const inCtl = !!el.closest('button, [role="menuitem"], [role="option"], [role="tab"], code, [data-slot="badge"]')`, assert each pixel value `v`, `a = Math.abs(v)`, satisfies `a === 0 || a === 1 || on(a, 4) || (inCtl && a <= 14 && on(a, 2))`. Headless Chromium resolves every inset to 0, so a safe-area composition reduces to its floor and needs no exemption. The 2 px sub-step is the amendment §15 C38 records. The audit harness's spacing probe (`web/tests/audit/probes.ts`) applies this same predicate on every surface it captures, so its off-scale table lists candidate findings against this clause.

### UI-CRAFT-2 [must] — Radius comes from the token ladder
**Assertion.** Every rounded corner resolves through `--radius` — a ladder step from `rounded-sm` to `rounded-3xl` or its per-corner form — or is `rounded-full`, `rounded-none` or `rounded-[inherit]`.
**Source.** `docs/design/01-foundations.md`, Spacing → "A strict base grid, generous gutters" (its radius paragraph: "a single base radius … The radius scales proportionally with component size"); `docs/prd/06-design-system-visual-spec.md` §3.3, which added `--radius-3xl` so the welcome rounding "now tracks the system radius knob"; `docs/design/00-principles.md`, Tension 4; the ladder itself, `--radius-sm` through `--radius-3xl` as multiples of `--radius`, in the `@theme inline` block of `web/src/app/globals.css`.
**Why bare `rounded` fails.** Bare `rounded`, a bare per-corner form such as `rounded-t`, `rounded-xs`, `rounded-4xl` and any arbitrary radius each compile to a fixed length that ignores the radius knob. Bare `rounded` is the insidious one: it reads like a token and is not one. `globals.css` overrides the named steps in `@theme inline` and never the unsuffixed utility, so Tailwind's default theme inlines a literal for it. The built stylesheet has `.rounded{border-radius:.25rem}` beside `.rounded-lg{border-radius:var(--radius)}`.
**Verify.** (1) `rg -nP '(?<![\w-])rounded(-(t|r|b|l|s|e|tl|tr|br|bl|ss|se|es|ee))?(?=["'"'"'\x60\s;])' web/src/components web/src/app/globals.css`. A hit inside a comment is prose ("rounded top", "rounded corners") and is discarded by reading the line; any hit in a class string or an `@apply` fails. (2) `rg -nP '(?<![\w-])rounded(-(t|r|b|l|s|e|tl|tr|br|bl|ss|se|es|ee))?-(xs|4xl|\[(?!inherit\]))' web/src/components web/src/app/globals.css` returns nothing. Both fail today — §15 C39.

### UI-CRAFT-3 [should] — Elevation is composed from shadow tokens
**Assertion.** Every `box-shadow` a component writes is a shadow token — `shadow-glass-*`, `shadow-float`, `shadow-pill`, `shadow-focus-*`, `shadow-hero-*`, `var(--focus-ring)` or a `glass-*` utility — or an arbitrary stack whose colors all come from a token `var()`, and never a stock Tailwind elevation utility (bare `shadow`, `shadow-xs` through `shadow-2xl`).
**Source.** `web/src/app/globals.css`, the shadow tokens in `@theme inline` (the glass stack, and `--shadow-float` / `--shadow-pill` as the "iOS-style elevation tokens"); `docs/design/00-principles.md`, Nature ("Prefer diffuse, soft shadows to hard drops"); `docs/design/02-patterns.md`, "Flat content, layered chrome" ("chrome elevation is *quiet* elevation"); `docs/design/03-anti-patterns.md` §B, "Always-on elevation on inline controls".
**Scope.** UI-LAYOUT-4 decides *where* elevation may appear on the thread. This clause decides what elevation is made of, on every surface, dialogs included, where UI-LAYOUT-4 does not reach.
**Verify.** `rg -nP '(?<![\w-])shadow(-(xs|sm|md|lg|xl|2xl))?(?=["'"'"'\x60\s])' web/src/components` — a hit in a class string fails and a hit in a comment is discarded. `rg -n 'shadow-\[[^]]*(rgba?\(|#[0-9a-fA-F]{3})' web/src/components` returns nothing. Deviates today — §15 C41.

### UI-CRAFT-4 [must] — One icon family, drawn in the text's color
**Assertion.** Every icon inside a control is a Lucide glyph (`svg.lucide`) whose stroke, or fill for a filled glyph, resolves to the control's text color.
**Source.** `docs/design/01-foundations.md`, Iconography → "One family, never mixed" and "Color from context"; `docs/design/03-anti-patterns.md` §E, "Mixed icon families or stroke weights" and "Hardcoded fill or stroke colors on icons"; Decision 05 in `docs/design/04-rationale.md`.
**Scope.** Icons only. A rendered Mermaid diagram is message content, and the brand mark under `web/public/` is an asset Decision 05 places outside the Lucide grid. Vendored chrome is in scope when the vendor accepts an icon override, because a second family then ships by this repo's choice, not the vendor's. The static half — no inline `<svg>` in a component, no second icon package — is Verify (1).
**Verify.** (1) `rg -n '<svg' web/src/components` returns nothing, and `web/package.json` names no icon package besides `lucide-react`. (2) Playwright at 1280 px on a finished `RICH_MARKDOWN:` turn, which renders the code-block chrome: `page.$$eval('button svg, a svg, [role="button"] svg, [role="menuitem"] svg', els => els.filter(s => { const cs = getComputedStyle(s); const text = getComputedStyle(s.closest('button, a, [role="button"], [role="menuitem"]')).color; return !s.classList.contains("lucide") || ![cs.stroke, cs.fill].includes(text); }).length)` returns 0. The comparison is against the control's color, not the `svg`'s own, so a color class pinned on the glyph itself fails. Fails today on the code-block controls — §15 C40.

### UI-CRAFT-5 [should] — Icons in one cluster share size and weight
**Assertion.** Within one control cluster — the app header, a message's action toolbar, the composer's control row, an open menu — every icon renders at the same box size and the same `stroke-width`, and that stroke width is between 2 and 2.25.
**Source.** `docs/design/00-principles.md`, High Aesthetics ("Match the optical weight of icons to neighboring text at every breakpoint"); `docs/design/01-foundations.md`, Iconography → "Icons as glyphs"; `docs/design/BRAND_BRIEF.md` §4, Iconography row (`strokeWidth 2`–`2.25`).
**Verify.** Playwright at 390 px with touch and at 1280 px. For each cluster root — `header`, `[role="toolbar"][aria-label="Message actions"]`, each open `[role="menu"]`, and the nearest common ancestor of `[data-testid="composer-more-actions"]` and `[data-testid="composer-send"]` — collect the visible `svg.lucide` descendants. Assert `new Set(svgs.map(s => s.getBoundingClientRect().width.toFixed(1))).size === 1`, and that the set of `parseFloat(getComputedStyle(s).strokeWidth)` values has one member between 2 and 2.25. The computed value is read, not the attribute, so a CSS override is caught.

### UI-CRAFT-6 [should] — Every control has distinct hover and disabled renderings
**Assertion.** On a pointer device every enabled interactive control changes visibly on hover in at least one of background, text color, border color, shadow, opacity, transform or text decoration, and every disabled control is dimmed to an opacity of 0.5 or less and ignores the pointer.
**Source.** `docs/design/00-principles.md`, High Aesthetics ("The composer at rest, focused, generating, and disabled are four designed states with deliberate transitions, not four CSS overrides"); `docs/prd/06-design-system-visual-spec.md` §2 ("Define P0 chat components and their visual states"); `docs/design/02-patterns.md`, "Choreographed motion" (the hover micro-lift); `docs/design/audits/ISSUES.md` ISSUE-4 and ISSUE-9, whose dispositions name opacity dimming — `disabled:opacity-50` in `buttonVariants`, `disabled:opacity-40` on the edit Save — as the intended disabled token.
**Scope.** Focus-visible is UI-FOCUS-2's and pressed is UI-TOUCH-7's; this clause completes the set. Links inside `.chat-md` are excluded: they are prose, they carry an underline at rest, and their styling is Streamdown's. A control already in its selected state — `[aria-selected="true"]`, `[aria-current]`, `[data-state="active"]` — is exempt from the hover half, because its resting rendering is already the emphasized one.
**Verify.** Playwright at 1280 px without touch. For every visible, enabled `button, a[href], [role="button"], [role="tab"], [role="menuitem"], [role="option"], [role="switch"], [role="checkbox"]` outside `.chat-md` and not matching `[aria-selected="true"], [aria-current], [data-state="active"]`, snapshot the computed `backgroundColor`, `color`, `borderColor`, `boxShadow`, `opacity`, `transform`, `textDecorationLine` and `filter` of the control, its parent and each of its descendants, so a `group-hover` change painted on a child or a hover painted on a wrapper both count. Call `locator.hover()`, wait 350 ms (the longest shipped control transition is 280 ms), snapshot again, and assert at least one value differs. Then, for every `:disabled`, `[aria-disabled="true"]` or `[data-disabled]` control, assert that its own computed `opacity`, or that of the nearest ancestor carrying the disabled state, is ≤ 0.5, and that its `pointer-events` is `none` or its `cursor` is `not-allowed` or `default`.

### UI-CRAFT-7 [should] — An async action shows it is pending and cannot fire twice
**Assertion.** A control that starts a server round-trip other than a chat turn — branch, save, share, delete, key test — switches on activation to a pending rendering, disabled and showing a spinner or a pending label, and ignores further activation until the request settles.
**Source.** `docs/design/00-principles.md`, High Aesthetics (the four-designed-states bullet); the shipped idiom in `web/src/components/chat/message-actions.tsx`, where Branch swaps to `Loader2` and "Branching" and sets `disabled` while `isBranching`.
**Scope.** A chat turn's own pending state is UI-STREAM-4's and UI-COMPOSER-3's, and this clause does not re-assert either.
**Verify.** Playwright on a finished turn. `page.route("**/api/conversations/*/branch", r => setTimeout(() => r.continue(), 2000))` and count requests to that URL. Activate the control named "Branch in new chat", opening the message overflow first if it lives there. Within 100 ms — a probe tolerance for one render, not a canon value — assert the control is disabled (or `aria-disabled="true"`) and its accessible name reads "Branching". Activate it again, let the request settle, and assert exactly one request was made. Repeat the shape for every other async control a surface under review adds.

### UI-CRAFT-8 [must] — Hover and focus never move layout
**Assertion.** Hovering or keyboard-focusing any control leaves the layout box — offset position and size — of that control, its parent and its siblings unchanged, so hover and focus feedback is paint or transform only.
**Source.** `docs/design/02-patterns.md`, "Choreographed motion" (hover is "a single-property translate-and-scale micro-lift"); `docs/prd/03-mobile-cross-platform.md` §4.10 **[P0]** CLS protection.
**Verify.** Playwright at 1280 px, over the same control set as UI-CRAFT-6. Record `[offsetLeft, offsetTop, offsetWidth, offsetHeight]` for the control, its parent and each of the parent's children. `offset*` ignores transforms, so the sanctioned micro-lift does not register. Hover, wait 350 ms, record again and assert equality. Repeat with keyboard focus reached by Tab. As a backstop, `rg -nP '(hover|focus|focus-visible|group-hover[^:\s"]*):(font-(medium|semibold|bold)|border-[0-9]|p[xytrblse]?-[0-9]|m[xytrblse]?-[0-9]|w-|h-|size-|text-(xs|sm|base|lg|xl))' web/src/components` returns nothing.

### UI-CRAFT-9 [must] — Overlays stack by the layer scale and stay on screen
**Assertion.** Every z-index in component code comes from the documented layer scale, and every open overlay paints above the surface that opened it and lies inside the viewport at 320 px wide.
**Source.** `web/src/app/globals.css`, the z-index scale comment at the head of the file; `docs/design/00-principles.md`, High Aesthetics ("a popover sits a single elevation step above the surface that opened it"); WCAG 2.2 SC 1.4.10 Reflow (AA) — an overlay pushed past the viewport edge at 320 px loses the content it carries.
**Verify.** (1) The scale is base content 0–30, modals 50, contextual popovers 60, toasts 70, status strip 100: `rg -noP '(?<![\w-])z-(\[[^\]]+\]|[0-9]+)' web/src/components`, where every value must be one of `z-0`, `z-10`, `z-20`, `z-30`, `z-50`, `z-[60]`, `z-[70]`, `z-[100]`. Fails today on two sites — §15 C42. (2) Playwright at 320×568 with touch and at 1280×800. Open, one at a time, the message overflow (`[data-testid="message-actions-overflow"]`), the composer's more-actions (`[data-testid="composer-more-actions"]`), the model picker (`[data-testid="model-mode-trigger"]`), a conversation row's "Conversation actions" menu, and, inside the Settings dialog, the "Change theme" menu. For each open `[role="menu"]`, `[role="listbox"]`, `[role="dialog"]` or `[data-slot="tooltip-content"]`, assert its box satisfies `left >= -1`, `top >= -1`, `right <= innerWidth + 1` and `bottom <= innerHeight + 1`, and that `document.elementFromPoint` at its centre is inside it. For the theme menu, that last assertion is the proof it paints above the dialog.

### UI-CRAFT-10 [must] — Floating chrome never covers a resting control
**Assertion.** At the page's resting scroll positions — the welcome surface, and a thread pinned to its latest turn — no floating element covers the centre of a visible interactive control in the content column.
**Source.** `docs/design/audits/ISSUES.md` ISSUE-1, ISSUE-6 and ISSUE-7, where the install coachmark covered a suggestion chip, then both follow-up chips, then `/status` content: three shipped regressions of one class that no clause caught; `docs/design/02-patterns.md`, "Deference of chrome" ("Chrome may be available; it must not ask to be looked at"). UI-FOCUS-3 covers the keyboard-focus case on message rows only.
**Scope.** Floating elements here are the install coachmark, the jump-to-latest control, the banner slot and the status strip.
**Verify.** Playwright with `devices["iPhone 13"]`, the profile the ISSUES.md sweep used, and again at 1280 px, with no toast on screen. On the welcome surface, check each `ul[aria-label="Suggested prompts"] button`. After a finished turn, scrolled to the bottom, check each `[data-testid="follow-up-chips"] button` and each control in the last `[role="toolbar"][aria-label="Message actions"]`. For each, take the centre of its box and assert `el.contains(document.elementFromPoint(x, y))`. Repeat on `/status` for every visible control.

### UI-CRAFT-11 [must] — Banners share one slot
**Assertion.** At most one persistent banner is visible in the thread chrome at a time, so when the temporary-chat banner and the degraded-status banner are both active, one of them yields.
**Source.** `docs/design/03-anti-patterns.md` §G, "Multi-banner walls" ("one persistent privacy banner at most … sticky elements compete with each other for a single slot"); shipped as the prioritized slot in `web/src/components/chat/chat-thread.tsx` (`DegradedStatusBanner`'s `onActiveChange`).
**Scope.** The count only. *Which* banner wins is disputed between the anti-pattern and the code — §15 C45 — so the order is not asserted. The install coachmark is a dismissible transient pill (`docs/prd/03-mobile-cross-platform.md` §4.9), and toasts are transient; neither is a banner. When the quota banners of PRD 08 §7 ship (§15 C18), they join this slot.
**Verify.** Playwright: `page.route("**/api/status", r => r.fulfill({ json: { status: "degraded", windowSeconds: 300, sampleSize: 100, errorCount: 20, updatedAt: new Date().toISOString() } }))`, then load the page and start a temporary chat. Assert that the visible count across `[data-testid="temporary-chat-banner"]` and `[data-testid="degraded-status-banner"]` is at most 1. Dismiss whichever is showing and assert the other appears, so the slot is shared rather than lost.

### UI-CRAFT-12 [must] — No large surface is pure white or pure black
**Assertion.** In default media, in both themes, no element whose visible painted box covers at least 10% of the viewport resolves its background to opaque pure white or opaque pure black.
**Source.** `docs/design/00-principles.md`, Nature ("Avoid pure white and pure black as surface colors. The neutrals are OKLCH lightness values pulled inward from the extremes") and Tension 1 ("The neutrals are pulled in from pure white and pure black"); `docs/design/BRAND_BRIEF.md` §4, Surface character row.
**Why 10%.** The principle governs surfaces, not every pixel. A switch thumb or a checkbox painting `--card` is a control, and 10% of a 320×568 viewport is a 135 px square, larger than any control and smaller than any sheet or dialog. Print (UI-PREF-5 requires white) and the reduced-transparency and no-`backdrop-filter` fallbacks (§15 C43) are outside default media and out of scope.
**Verify.** Playwright at 390×844 and at 1280×800, with `colorScheme` set to light and then dark, on the welcome surface, a thread, the open drawer and each dialog. Chromium reports OKLCH tokens in `oklch()` form, so normalize through a canvas: `const ctx = document.createElement("canvas").getContext("2d"); const rgba = c => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = "rgba(0,0,0,0)"; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data]; };`. For every element, compute its box's area clipped to the viewport. Where that is ≥ `0.1 * innerWidth * innerHeight`, assert that `rgba(getComputedStyle(el).backgroundColor)` is neither `[255, 255, 255, 255]` nor `[0, 0, 0, 255]`.

### UI-CRAFT-13 [should] — One accent-filled control per view
**Assertion.** At any moment, each view — the page outside any modal, and each open dialog or sheet — shows at most one control filled with the accent, `--brand` or `--brand-fill`.
**Source.** `docs/design/02-patterns.md`, "Single accent doctrine" (the accent appears on the Send button, the composer focus glow, focus rings and the active-row stripe, and "does not appear anywhere else"); `docs/design/00-principles.md`, High Aesthetics ("If a control needs more presence, change its spacing, weight, or position before reaching for color or decoration").
**Scope.** Filled controls of at least 24×24 px only, so the 2 px active-row stripe and the translucent chart bars (`bg-brand/70`) are out. The user bubble's `--brand-muted` wash fills with neither token and is §15 C44's subject, not this clause's.
**Verify.** Playwright at 390 px and at 1280 px, in both themes. Check the welcome surface with a typed draft, a thread with a typed draft, a turn at `awaiting_approval` (send `TOOL_APPROVE:` with tools enabled, then type a draft), and each dialog. Resolve `--brand` and `--brand-fill` by painting two probe elements and normalizing through UI-CRAFT-12's canvas helper. Within each view root, count the visible `button`, `a` and `[role="button"]` elements whose normalized `backgroundColor` equals either value and whose box is at least 24×24 px, and assert the count is ≤ 1.

---

## 15. Conflict and silence register

Recorded while writing this document. Each entry names the disagreement, the ruling, and what a reviewer should do.

**C1 — Canon requires an affordance that is not shipped. RESOLVED.** `docs/prd/07-transparency-contract.md` §6.1 and §8 AC 9, and `docs/prd/06-design-system-visual-spec.md` §5.4 (D41), require a per-message **View spend** affordance on every finished assistant message. None existed when this document was written. **Ruling:** the affordance ships — a **View spend** item in the message overflow menu that opens the Settings hub on its General tab, scrolled to the spend breakdown (and skipping the mobile grouped list, which a plain tab deep-link would show). Two departures from the canon wording, both recorded in UI-TRUST-3: it is a button, not a link, because it opens a dialog rather than navigating; and it lives in the action cluster rather than the metadata byline, because the byline states facts and the cluster holds verbs. PRD 07 §8 AC 9 already reads "affordance". The "link" wording survives at PRD 07 §6.1 and at `docs/prd/06-design-system-visual-spec.md` §5.4 (both the byline bullet and the D41 resolution line); those are the ones left to amend.

**C2 — WCAG version is stated two ways.** `docs/prd/06-design-system-visual-spec.md` §2 sets the goal at "WCAG 2.1 AA (stretch 2.2 AA where cheap)", while `docs/prd/03-mobile-cross-platform.md` §4.8 makes WCAG 2.2 SC 2.5.8 a P0 floor and `docs/ux-best-practices/desktop-ux.md` §10 / `docs/ux-best-practices/mobile-ux.md` §10 target 2.2 AA including 2.4.11, 2.5.7 and 2.5.8 — with shipped implementations (the `.chat-message-row` scroll margins in `globals.css` are commented "WCAG 2.4.11"). **Ruling:** repo canon prevails over external canon, but here repo canon contradicts itself; this document takes **WCAG 2.2 AA** as the bar, because PRD 03 §4.8 is the more specific clause and is the one that shipped. PRD 06 §2 should be amended to match.

**C3 — A criterion is cited without its level.** `docs/ux-best-practices/desktop-ux.md` §10 platform note treats SC 2.4.13 Focus Appearance as a requirement. 2.4.13 is **AAA** in WCAG 2.2; the AA obligations for focus are 2.4.7 Focus Visible and 2.4.11 Focus Not Obscured (Minimum), with the 3:1 indicator contrast coming from 1.4.11 Non-text Contrast. **Ruling:** UI-FOCUS-2 and UI-FOCUS-3 are `[must]` at AA; UI-FOCUS-8 carries the 2.4.13 appearance target as `[should]`.

**C4 — The measure cap is not expressed in the unit canon uses.** PRD 06 §3.2 and PRD 03 §5.3 cap the reading column at ~70–80ch, but the shipped cap is `max-w-3xl` (48 rem) on `web/src/components/chat/message-list.tsx:366` — a rem cap whose character count depends on the resolved font. **Ruling:** UI-TYPE-6 is written against the ch cap and must be *measured*, never inferred from the class. A reviewer who measures above 80ch should file against PRD 06 §3.2 rather than silently widening this standard.

**C5 — A required tool is not installed.** `docs/prd/06-design-system-visual-spec.md` §7 AC 4 requires an "axe-class check: 0 critical violations on chat, composer, settings, palette", but no axe dependency exists in `web/package.json` and no spec in `web/tests/e2e/` runs one. **Ruling:** every clause here that would naturally be an axe rule (UI-COLOR-3, UI-FOCUS-5, UI-STREAM-1) is given an explicit Playwright or computed-style check that does not depend on axe. Wiring the axe-class gate is outstanding work against PRD 06 §7 AC 4.

**C6 — Canon is silent on three criteria a reviewer will need.** Nothing in the PRDs or the UX best-practice docs addresses WCAG 2.2 SC 1.4.12 Text Spacing, SC 1.3.5 Identify Input Purpose (both **AA**), or SC 3.3.7 Redundant Entry (**Level A**, not AA — an earlier revision of this entry mislabelled it). **Ruling:** 1.4.12 and 1.3.5 are adopted here as `[must]` (UI-TYPE-8, UI-COMPOSER-8), because C2 sets the bar at WCAG 2.2 AA and an AA criterion cannot sit under a strength that permits a recorded deviation. 3.3.7 is left unstated on scope, not on strength: no flow in this product currently re-asks for previously entered information. If one is added, 3.3.7 enters as `[must]` on its Level A standing alone, and this register is where the clause gets filed.

**C7 — Two supporting documents carry stale paths.** `docs/mobile-ux/ST5-spec.md` §(c) lists `web/src/components/layout/app-shell.tsx` and `.../layout/app-header.tsx`; no `layout/` directory exists — both files live under `web/src/components/chat/`. Separately, `web/.nycrc.json` excludes three files that no longer exist (`src/components/chat/history-search-dialog.tsx`, `src/components/chat/spend-dialog.tsx`, `src/components/ui/skeleton.tsx`). **Ruling:** neither changes a standard, but a reviewer following ST5's file list will not find the files, and the stale nyc excludes quietly widen the coverage exemptions. Both are cleanup items.

**C8 — Repo canon is deliberately stricter than external canon in two places.** Touch target: Apple HIG and repo canon set 44 pt where WCAG 2.2 SC 2.5.8 sets 24 px — repo wins (UI-TOUCH-1), with 24 px retained only as the pointer-device floor (UI-TOUCH-2). Motion: `prefers-reduced-motion` support corresponds to SC 2.3.3, a AAA criterion, but `docs/prd/06-design-system-visual-spec.md` §7 AC 8 makes it release-blocking — repo wins (UI-MOTION-5). Both are noted inside the clauses so no reviewer relaxes them by citing the weaker external number.

**C9 — "Control boundaries" did not say which boundaries. RESOLVED.** The first review against UI-COLOR-4 measured the follow-up chip outline at 1.15:1 and could not tell whether the clause meant every drawn boundary or only a boundary a control depends on. **Ruling:** only load-bearing boundaries, as UI-COLOR-4's new scope paragraph now states. Two roles exist: `--border` for separators that carry no obligation, `--control-border` for a boundary that is the sole signal of interactivity or of state.

**C10 — Touch floors were width-gated across the app. RESOLVED.** A sweep found 37 sites writing the 44 px floor as a base with a width-gated reset (`size-11 md:size-9`, `min-h-11 md:min-h-0`) and 8 sites hiding hover-revealed controls the same way (`md:opacity-0`). Every one satisfied UI-TOUCH-4 as it was then worded and broke UI-TOUCH-5 and UI-TOUCH-6 on any touch tablet at >= 768 px. **Ruling:** the inverted form is the defect, not the exception. UI-TOUCH-4 no longer lists `md:` as an acceptable gate — which also supersedes the "or `md:`-ramped" half of `docs/mobile-ux/ST5-spec.md` §0 — and UI-TOUCH-5 and UI-TOUCH-6 each carry a "How to write it" line with the `rg` check that catches a regression.

**C11 — The first regression check was narrower than the clause it guarded. RESOLVED.** UI-TOUCH-5 originally published `rg -n 'md:size-|md:min-h-0|(md|sm):h-9' web/src`, a list of the literal forms the C10 sweep happened to meet. It missed two surviving sites in `web/src/components/chat/command-palette.tsx` (`size-11 … md:size-7`), because `md:size-7` is not `md:size-9` and the sweep's own verification used a different pattern again. **Ruling:** a regression check is written against the *shape* of the defect, never against the instances of it. UI-TOUCH-5 now carries a pattern qualified by a 44 px base class, which matches a width-gated sizing reset at any value. Measured against the pre-sweep tree it finds 47 hits and does not match a header ramping `h-[46px] md:h-16`, which carries no floor and is a layout ramp rather than this defect. The two `command-palette.tsx` sites are fixed.

**C12 — The shipped chat ramp is not the figure PRD 06 states.** `docs/prd/06-design-system-visual-spec.md` §3.2 states one figure, "Chat body: 16px base, `rem`-based". The shipped `.chat-md` ramp in `web/src/app/globals.css` is 17 px at ≤767 px and 15 px at ≥768 px — a two-step ramp that brackets the PRD's single number rather than matching it. The ramp is deliberate (larger for a phone held at arm's length, denser for a desktop reading column already capped at 70–80ch) and it shipped. **Ruling:** per the precedence rule in §0, a PRD wins on concrete values, so this is a real conflict and not a silence. The shipped ramp stands and UI-TYPE-5 is written against it, because the PRD's own companion clause in the same sentence — the 70–80ch cap — is what makes 15 px correct on desktop. PRD 06 §3.2 should be amended to state the ramp.

**C13 — A fifth easing curve ships under a Tailwind name.** UI-MOTION-7 requires every transition to use one of the four `--ease-*` tokens, and its check greps for a raw `cubic-bezier` literal. `rg -no 'ease-(out|in|in-out|linear)\b' web/src/components` returns 16 hits — in `toast.tsx`, `switch.tsx`, `button.tsx`, `welcome-screen.tsx`, `usage-meter.tsx`, `sidebar.tsx`, `reasoning-panel.tsx`, `composer.tsx` and `chat-thread.tsx`. Tailwind's `ease-out` resolves to `cubic-bezier(0, 0, 0.2, 1)`, so the code uses a curve outside the token set while the grep stays clean. One of the sites is the composer focus glow, whose own comment claims it "rides the chrome ease-out" while `02-patterns.md` names the token curve. **Ruling:** the assertion stands and the check is corrected to catch the named utilities. The 16 replacements are a visual change across buttons, toasts and switches and are **not** made here, because none has been reviewed on screen. They are open work against UI-MOTION-7.

**C14 — Only the drawer integrates with the history stack.** `docs/prd/03-mobile-cross-platform.md` §4.2 asks every overlay to push a history entry so Back unwinds them in order. `rg -n 'pushState|popstate' web/src` finds the pattern in `web/src/components/chat/app-shell.tsx` only, scoped in its own comment to the mobile drawer. `dialog.tsx`, `drawer.tsx`, `command-palette.tsx` and `tier-picker.tsx` carry no history integration. Running the clause's original probe — drawer, then sheet, then two `goBack()` calls — closes the **drawer** first, the inverse of the order the PRD names, and the second call leaves the chat route. **Ruling:** UI-MOBILE-7 is narrowed to the drawer, which is what a reviewer can decide today. Closing the gap means lifting `app-shell.tsx`'s `pushState`/`popstate` pair into a shared hook that `DialogContent`, the palette sheet and the full-screen panels consume, at which point the LIFO order falls out of the history stack. Open work against PRD 03 §4.2.

**C15 — Print clips the thread twice over.** UI-PREF-5 asks the print rendering to flow the message area at full height without clipping virtualized rows. Two things defeat it. First, `@media print` in `globals.css` resets `html`, `body` and `.chat-scroll`, but three ancestors between them keep a bounded box — `app-shell.tsx` twice (`h-dvh` plus `overflow-hidden`, then `overflow-hidden`) and the thread wrapper in `chat-thread.tsx` — and a bounded ancestor clips its descendants in paged media whatever the scroller does. Second, above `VIRTUALIZE_AFTER` (80) `message-list.tsx` slices the rows out of the DOM entirely, and the print block's `content-visibility: visible !important` can only un-skip a row that is still there. A thread over 80 messages prints its window and two blank spacers. **Ruling:** the clause stands and its check now uses a thread over 80 messages, so the failure is visible. The fix needs both a print reset on the shell and thread wrappers and a `beforeprint` path that disables the virtual window — a behaviour change, not a stylesheet change, and open work.

**C16 — Enter sends on touch. RESOLVED as a conflict, open as code.** UI-COMPOSER-4 and `docs/prd/03-mobile-cross-platform.md` §4.3 ("Mobile Enter = newline") both require Enter to insert a newline on a touch device. `web/src/components/chat/composer.tsx` branches on `preferences.sendOnEnter` alone, which defaults to true server-side, and `rg 'hover: *none|pointer: *coarse|isTouch'` finds no pointer gate anywhere on that path. So the shipped default sends on Enter on a phone. **Ruling:** the assertion stands; this is a code defect, not a clause to soften. The fix is to gate the send branch on a fine pointer and keep the stored preference as the desktop override. It interacts with UI-COMPOSER-6's required `enterkeyhint="send"`, so the two need reconciling in `docs/design/04-rationale.md` when it lands. Open work.

**C17 — The composer focus halo is canon but not shipped.** `docs/design/02-patterns.md` and Decision 07 in `04-rationale.md` both describe the composer focus state as "brand-edge plus halo glow". `composer.tsx` applies the edge only, and its own comment records dropping `--focus-glow-halo` because "iOS text fields don't glow". The token is still defined in `globals.css` and referenced by no component, and no deviation entry exists in `04-rationale.md`, which the `[should]` protocol in §0 requires. **Ruling:** the split must close in one direction or the other — restore the halo, or amend Decision 07 and `02-patterns.md` and retire the two dead tokens. Not decided here, because it is a visual-design call rather than a defect. Open work.

**C18 — The usage-threshold banners are canon but not shipped.** `docs/prd/08-error-and-limit-states.md` §7 requires an info banner at 80–94% of budget and a warning banner with a tier or BYOK nudge at 95–99%. `usage-meter.tsx` defines both thresholds but spends them on its own colour tone and an accessible-label suffix, and the meter mounts only inside the settings dialog — it is not on the chat surface at all. No banner exists in `web/src`. **Ruling:** UI-STATE-4 correctly fails; this is unshipped canon, like C1 before the View spend affordance landed. Open work against PRD 08 §7.

**C19 — The severity vocabulary and its dispatch both diverge.** `docs/prd/08-error-and-limit-states.md` §4 and UI-STATE-1 both name a `blocking` severity. The shipped contract has no such value: `api/app/errors.py` and `web/src/lib/apiClient.ts` agree on `info | warning | error | fatal`. Separately, severity selects no pattern — `rg 'severity ===' web/src` finds only the toast's role and duration and one `=== "fatal"` destructive flag, while the choice between toast, banner and inline hint is made per call site. **Ruling:** two items of open work, one naming and one structural. Pick `fatal` or `blocking` and make PRD 08 §4, `errors.py` and `apiClient.ts` agree, then route the error surfaces through a single severity-to-pattern dispatcher. UI-STATE-1 is written against the PRD's vocabulary and will keep failing until the name is settled.

**C20 — The structured limit counts do not exist.** PRD 08 §6 rule 2 requires a count composed from `meta.used` and `meta.limit`, "never from a hard-coded `body` string". `api/app/errors.py` interpolates the percentage and the guest limit straight into `body`, and `rg 'meta\.used|meta\.limit|reset_at|resetAt' api/app web/src` returns nothing — the fields are produced nowhere and read nowhere. The live countdown half of UI-STATE-3 does hold, from `error.retryAfterMs`. **Ruling:** UI-STATE-3 correctly fails on its first half. Add `meta` to the limit envelopes, strip the interpolated values out of `body`, and compose the count in the frontend. Open work.

**C21 — The first turn's typing indicator misses the 150 ms budget.** UI-STREAM-4 and `docs/prd/06-design-system-visual-spec.md` §5.2 both put the pre-first-token indicator on screen within 150 ms. On the first send of a conversation, `chat-thread.tsx` defers `commitTurn` — and with it the `setPendingId` that mounts the bubble and the indicator — behind the 200 ms welcome-exit timer, so the indicator cannot appear before ~200 ms. Every later send calls `commitTurn` directly and is inside budget. The 200 ms seam is itself named in Decision 11, so this is canon against canon rather than a plain slip. **Ruling:** mounting the placeholder at click time and letting the welcome exit cross-fade over it satisfies both, and is the fix to prefer. Until then UI-STREAM-4 fails on the first turn only. Open work, and a reconciliation to record in `04-rationale.md` if the seam wins instead.

**C22 — The frontend stream states and PRD 08's state machine disagree in both directions.** PRD 08 §8 gives `idle -> submitted -> streaming -> done | stopped | error | interrupted`. `StreamStatus` in `web/src/lib/types.ts` has no `interrupted` — an interrupted turn is collapsed onto `error` — and adds `awaiting_approval`, a terminal the PRD omits. **Ruling:** neither side is wrong on its own terms, and no clause here should be written against `interrupted` until the two agree. A recovery clause should be written against `error` plus the `canContinue` flag, which is what actually ships. Open work: amend PRD 08 §8 to carry `awaiting_approval`, and decide whether `interrupted` becomes a real frontend state or is retired from the PRD.

**C23 — The offline queue is storage plumbing with no caller.** `docs/prd/08-error-and-limit-states.md` §9 requires offline and queued status to be "visible and announced". `web/src/lib/offline-store.ts` exports `enqueueUnsent`, `getUnsentQueue` and `removeFromQueue`, and `rg` finds no caller for any of the three anywhere in `web/src`. There is no `navigator.onLine` listener, no offline banner and no queued-message chrome. **Ruling:** no clause is written for this. A `[must]` that every screen fails, with no defect to file it against, is a backlog item rather than a review instrument — this register is where it waits. When the offline surface ships, its announcement half must reconcile with UI-STREAM-2's single polite status region.

**C24 — There is no pseudo-locale to test string expansion against.** `docs/prd/06-design-system-visual-spec.md` §3.2 requires that "pseudo-localization must not break attribution rows or composer layout". `web/src/lib/i18n/messages.ts` defines exactly one catalog, `en`, and it holds roughly 25 keys — the attribution row the PRD names is hardcoded English in its component and is not in the catalog at all. The `?rtl=1` hook is a direction override, not a locale. **Ruling:** a clause phrased as "switch to the pseudo-locale" is unrunnable. A clause that carries its own mechanism is not: expand every text node by about 40 percent in the page, then re-run UI-LAYOUT-1's scroll-width assertion and a clipping check, which is the shape UI-TYPE-8's Verify already uses. Open work, either way.

**C25 — The AI-interaction disclosure is not persistent.** `docs/prd/06-design-system-visual-spec.md` §5.8 calls for a "persistent AI-interaction disclosure", and `docs/ux-best-practices/desktop-ux.md` §12 ties it to Article 50(1). `web/src/components/chat/ai-disclosure.tsx` ships correctly — `role="note"`, a non-empty `aria-label` — but mounts at exactly one call site, the welcome screen, and the component's own comment records that the placement below the composer was deliberately removed as chrome clutter. UI-STATE-7 requires the welcome surface to unmount on first send, so the disclosure leaves the page with it. **Ruling:** this is canon against a shipped ruling, the same shape as C1. The ruling is not overturned here. PRD 06 §5.8 should be amended to say where the disclosure is required, and a clause written against that answer rather than against the word "persistent".

**C26 — An inline `backdrop-filter` is unreachable by every preference reset. RESOLVED.** UI-PREF-2 requires `backdrop-filter` to resolve to `none` under `prefers-reduced-transparency: reduce`. Four surfaces set the property as an inline style — the navigation drawer, the dialog sheet, the command-palette sheet and the status-bar strip — and the reset blocks in `globals.css` all match by class, so none of the four could reach them. Measured in Chromium over CDP, all four kept their blur under `reduce` while the glass utilities around them went opaque. **Ruling:** a filter belongs on a class, which is what `chrome-frost`'s own comment in `globals.css` already says. The four now retune `--glass-blur` (and, where the surface omits the brightness lift, `--glass-brightness`) instead of assigning `backdrop-filter`, and the strip takes the `chrome-frost` class it was duplicating inline. Measured after the change: identical filters under default media, `none` for all four under both `reduce` and `forced-colors: active`. `.chrome-frost` was added to the forced-colors reset, without the border the glass utilities take there — it has no fill of its own to bound.

**C27 — Streamed markdown had no image rule at all. RESOLVED.** `docs/prd/01-core-chat-experience.md` §5.4 requires images to lazy-load, carry a constrained max-width, and have alt text, using a generic label when the model supplies none. `.chat-md` styled every other markdown element and had no `img` rule, and the renderer passed images through untouched, so a model-emitted image was uncapped — an over-wide one widened the message row and put a horizontal scrollbar on the page, failing UI-LAYOUT-1. **Ruling:** the cap belongs in the stylesheet and the attributes belong in the renderer. `.chat-md :where(img)` now caps the width to the reading column, keeps the aspect ratio and reserves a muted box during decode; the renderer supplies `loading="lazy"`, `decoding="async"` and the generic label. A remote URL still has no dimensions to reserve against, so the CLS half of PRD 03 §4.10 is served only as far as a stylesheet can serve it.

**C28 — Four smaller conformance defects the first full pass found. RESOLVED.** Each was a single-site fix against a clause that already existed. A warning toast took `role="alert"`, so a routine quota notice interrupted the screen reader — `docs/prd/08-error-and-limit-states.md` §9 puts warnings on `role="status"`, and only errors now take `alert`. The agentic plan-clarify answer field rendered at 13 px on mobile, the one form control in the app below the 16 px floor that stops iOS Safari zooming on focus (UI-COMPOSER-1) — it now uses the same size class as every other field. The navigation drawer padded its bottom with a raw `env(safe-area-inset-bottom)` rather than the `--bottom-inset` floor, so its last row sat flush against the viewport edge on any device reporting a zero inset (UI-MOBILE-3). Five inner scrollers — the compare and welcome surfaces and the settings, share and auth dialogs — shipped without `overscroll-contain`, chaining a fling at their edge to the page and to the OS back-swipe (UI-MOBILE-5).

**C29 — The RTL mirroring rule has no consumer.** UI-LAYOUT-8 asserts that directional affordance glyphs are mirrored under `dir="rtl"` via `.rtl-flip` / `[data-rtl-flip]`. The rule exists — `web/src/app/globals.css` defines `[dir="rtl"] .rtl-flip, [dir="rtl"] [data-rtl-flip]:not([data-no-flip]) { transform: scaleX(-1); }` under a comment naming the send arrow, chevrons and back arrows, and an opt-out for glyphs whose meaning is absolute. `rg -n 'rtl-flip|rtlFlip' web/src/components` returns nothing: not one component applies either hook, so the rule is dead and every directional glyph keeps pointing left-to-right under RTL. The clause's own Verify never caught it, because the three assertions it listed covered `pre` direction, text alignment and scroll width only — that half is fixed here, and the fix is what makes the clause fail honestly. **Ruling:** UI-LAYOUT-8 now correctly fails on its mirroring half. The fix is not mechanical and is not taken here: deciding which glyphs are directional is a design pass, because a vertical disclosure chevron and a brand mark must not flip, and `scaleX(-1)` on the wrong glyph is a worse defect than no mirroring at all. Open work: walk the icon set, tag the directional glyphs, and verify against an RTL rendering rather than against the grep.

**C30 — The trust badge is a token with nothing to color.** UI-COLOR-9 `[should]` asserts that `--color-trust-badge`, `--color-byok-indicator` and `--color-temporary-chat-banner` read as low-chroma role markers rather than as second accents. Two of the three ship: the BYOK indicator and the temporary-chat banner each have component consumers. `--trust-badge` and `--trust-badge-foreground` are defined in both themes and aliased to `--color-trust-badge`, and `rg 'trust-badge' web/src --glob '!globals.css'` returns nothing — no surface renders them. **Ruling:** the clause cannot be decided on its first token, the same shape as C17 and C18. This is not a defect in the token, whose chroma sits correctly in the neutral band; it is a clause written ahead of the surface. Either a trust badge ships and the clause decides all three, or the token is retired and the clause names the two that exist. That is a product call, not a review finding.

**C31 — Canon says the AI disclosure is persistent; the shipped ruling puts it on one surface.** `docs/prd/06-design-system-visual-spec.md` §5.8 requires a "Persistent AI-interaction disclosure", and `docs/ux-best-practices/desktop-ux.md` §12 ties it to EU AI Act Article 50(1). `web/src/components/chat/ai-disclosure.tsx` has exactly one call site, the welcome screen, and its header comment records that the below-composer placement was removed deliberately as chrome clutter. UI-STATE-7 then requires the welcome surface to unmount on first send, so the disclosure is absent from an active thread. **Ruling:** the shipped placement stands, and UI-TRUST-9 is written against it so that it decides something rather than passing on a build that arguably fails canon. This is the same shape as C1 — canon wording against a deliberate product ruling — and the same remedy applies: amend PRD 06 §5.8 to describe the entry-surface placement, or reopen the #245 decision. Until one of those happens, a reviewer must not read UI-TRUST-9 as ratifying the word "persistent".

**C32 — Two thirds of the public-share redaction rule have no code to check.** `docs/prd/07-transparency-contract.md` §8 AC 6 states three requirements for a public share: memory detail stripped, web sources retained, and `knowledge` / `connector` sources shown with a redacted marker. It also requires generated-media provenance to survive. The first two now sit in UI-TRUST-5, because both are shipped. The redaction marker is not: `provenance?: "web" | "knowledge" | "connector"` in `web/src/lib/types.ts` is explicitly reserved with a comment naming `web` as the only live value, and no redaction code exists on either side. Generated-media provenance is marked **[P2]** at PRD 06 §7 AC 13. **Ruling:** neither becomes a clause now. When a non-`web` provenance ships, extend UI-TRUST-5's Verify rather than adding a clause, since the reviewer's action is one page fetch either way.

**C33 — Offline and queued state is canon with no interface behind it.** `docs/prd/08-error-and-limit-states.md` §9 ends with "Offline/queued status is visible and announced". The words "offline" and "queue" appear nowhere in this document, and the product has nothing to point them at: `web/src/lib/offline-store.ts` exports `enqueueUnsent`, `getUnsentQueue` and `removeFromQueue`, and none of the three has a caller anywhere in `web/src`. The one importer, `composer.tsx`, takes only the draft helpers. There is no `navigator.onLine` listener, no offline banner and no queued-message chrome. **Ruling:** no clause. A `[must]` that every screen fails, with no defect to file it against, is a backlog item wearing a clause ID. The queue is dead storage plumbing. When the offline surface ships, the clause is worth writing, and its announcement half will have to reconcile with UI-STREAM-2's "exactly one polite status region".

**C34 — The frontend stream state machine does not match PRD 08 §8.** The PRD's machine is `idle -> submitted -> streaming -> done | stopped | error | interrupted`, and it defines `interrupted` as "partial persisted; Continue/Regenerate". `StreamStatus` in `web/src/lib/types.ts` is `idle | submitted | streaming | done | awaiting_approval | stopped | error`. The frontend collapses `interrupted` onto `error`, and it adds `awaiting_approval`, a human-in-the-loop tool-approval terminal the PRD omits. The divergence runs in both directions. One consequence is user-visible: PRD 08 §8 defines `interrupted` as "partial persisted; Continue/Regenerate", and PRD 03 §4.6's AC turns on that persistence when it says "actions work after reload". The `error` path persists no assistant row, so a failed turn's bubble and its Retry control are gone after a reload — confirmed against the running app, where the user message survives the reload and the assistant bubble does not. **Ruling:** the shipped statuses are correct for what the product does today, and UI-STREAM-9 is written against them and asserts the live half only. Two things are open, and they are separate. PRD 08 §8 is the document to amend for the status list — drop `interrupted` in favour of `error`, and add `awaiting_approval`. Persisting a failed partial so the reload half of PRD 03 §4.6 can hold is a product change, not a documentation one, and it is the one worth doing: the `stopped` path already persists its partial, so the two failure terminals behave differently for no reason a user would recognise. Until then a reviewer must not file the missing `interrupted` status, or the vanishing bubble, as fresh defects.

**C35 — Code blocks have no "Show more" collapse.** `docs/prd/06-design-system-visual-spec.md` §5.7 asks that "Long blocks collapse with 'Show more.'" The chrome is Streamdown's, and the string "Show more" appears in none of its distributed bundles and nowhere in `web/src`. **Ruling:** UI-LAYOUT-10 asserts the language label, the copy control and the clipboard payload, and states that the collapse is out of its scope. The collapse is a vendored-library capability this repo does not have, so shipping it means either a Streamdown feature or a local renderer override. That is a product call. Until it is made, a reviewer must not file the absent collapse as a defect against UI-LAYOUT-10.

**C36 — Decision 15 leans on an avatar that does not exist.** `docs/design/04-rationale.md` Decision 15 rejects two-tone and alternating-row message treatments on the stated ground that "the role distinction is already carried by alignment and avatar". Alignment ships. The assistant message renders no avatar. **Ruling:** UI-LAYOUT-9 asserts alignment alone, deliberately, so that it passes on the build the rationale actually produced. The alternative — asserting both carriers — would make a `[must]` fail on day one over a design element nobody has decided to ship. Decision 15's wording should be amended to name alignment only, or an avatar should ship and the clause should gain its second half.

**C37 — "Distinct thread treatment" for a temporary chat is undefined.** `docs/prd/06-design-system-visual-spec.md` §5.8 asks for a temporary-chat banner "and distinct thread treatment". The banner is decidable and is asserted by UI-TRUST-10. The second phrase names no property: a different background, a different message surface and a different chrome tint would all satisfy it, and UI-LAYOUT-5 and UI-COLOR-5 constrain what a thread may look like in ways some readings would break. **Ruling:** silence recorded, no clause. Either the PRD names the treatment, or the phrase is dropped in favour of the banner it already requires.

**C38 — The spacing grid admits a 2 px sub-step inside controls. RESOLVED.** `docs/prd/06-design-system-visual-spec.md` §3.3 said only "4px base grid", and a first reading of UI-CRAFT-1 applied that to every box. The build carries 256 half-step spacing utilities across 49 files under `web/src/components`, resolving to 2, 6, 10 or 14 px, and most sit inside a control: `buttonVariants` sets `gap-1.5 px-2.5`, and the `.chat-md` inline-code rule sets `px-1.5 py-0.5`. A base grid sets the rhythm between components, not a ban on finer steps inside one; Tailwind's own spacing scale ships the half-steps for that purpose. **Resolution:** PRD 06 §3.3 now carries a bullet admitting 2 px sub-steps up to 14 px inside a single control or inline chip, and UI-CRAFT-1 asserts exactly that, branching on the control's selector. Half-steps between components or in a container gutter remain findings against UI-CRAFT-1; they have not been counted here, so each one a reviewer finds is a fresh defect, not a re-filing. The audit harness in `web/tests/audit/probes.ts` applies the clause's predicate as written, control branch included; its report is triage, not the gate.

**C39 — Seven radius sites sit off the token ladder.** UI-CRAFT-2 `[must]` requires every corner to come from the `--radius-*` ladder. Tailwind v4 compiles a bare `rounded` to a fixed `.25rem` rather than to a token. Five sites use it: `rounded-t` at `web/src/components/chat/spend-analytics-panel.tsx:230`, `rounded` at `web/src/components/chat/sources-panel.tsx:218` and `:232`, `rounded` at `web/src/components/chat/markdown-renderer.tsx:124`, and `@apply rounded` in the `.chat-md` inline-code rule at `web/src/app/globals.css:873`. Two primitives use arbitrary radii: `rounded-[4px]` at `web/src/components/ui/checkbox.tsx:16`, and `rounded-[min(var(--radius-md),10px)]` / `rounded-[min(var(--radius-md),12px)]` in `web/src/components/ui/button.tsx` at lines 25, 26, 30 and 32. At the default radius knob the button caps equal `--radius-md`, so nothing looks wrong today; the cap only bites when the knob is raised. **Ruling:** the clause fails on these sites. Moving a bare `rounded` to `rounded-sm` changes a pixel value, so it is a visual change, and it is not made here.

**C40 — Code-block controls draw a second icon family.** UI-CRAFT-4 `[must]` requires Lucide glyphs drawn in `currentColor`. Streamdown renders its own filled 16 px glyphs for the code-block copy, download and expand controls, and `web/src/components/chat/markdown-renderer.tsx` does not pass Streamdown's `icons` prop. **Ruling:** fails. The fix is small: every key of Streamdown's `IconMap` (`CheckIcon`, `CopyIcon`, `DownloadIcon`, `ExternalLinkIcon`, `Loader2Icon`, `Maximize2Icon`, `RotateCcwIcon`, `XIcon`, `ZoomInIcon`, `ZoomOutIcon`) has a Lucide component of the same name, so the renderer can pass them through.

**C41 — Segmented controls in settings use an untokened shadow.** UI-CRAFT-3 `[should]` asks that shadows come from the elevation tokens. `shadow-sm` sits on the active segment at `web/src/components/chat/spend-analytics-panel.tsx:139` and at `web/src/components/chat/settings-dialog.tsx` lines 356, 618, 652 and 1196. **Ruling:** a `[should]` deviation. Either a `--shadow-segment` token is added and these sites use it, or a rationale entry records the stock shadow as deliberate. Either closes the entry.

**C42 — Two standalone headers use a z-index off the scale.** UI-CRAFT-9 `[must]` admits the layers named in the `globals.css` scale comment. `z-40` sits on the sticky headers at `web/src/components/status/platform-status-view.tsx:70` and `web/src/components/share/public-conversation-view.tsx:109`. Neither page mounts a modal under the header, so nothing is occluded today. **Ruling:** fails; move both to `z-30`, which is the scale's chrome layer.

**C43 — The opaque fallbacks turn dialogs pure white.** UI-CRAFT-12 `[must]` rules out a pure white or black large surface, citing Nature in `docs/design/00-principles.md` and `docs/design/BRAND_BRIEF.md` §4. In the light theme `globals.css` defines `--card` and `--popover` as `oklch(1 0 0)`. The glass surfaces avoid them in default media, but the `prefers-reduced-transparency` and `@supports not (backdrop-filter…)` fallbacks swap to these tokens as the opaque fill, so a dialog becomes pure white exactly for the users who asked for less visual noise. **Ruling:** UI-CRAFT-12 is scoped to default media so that it decides something on the shipped glass. The fallback modes are out of its scope. Tinting `--card` and `--popover` towards the paper hue closes the entry and lets the clause drop its scope line.

**C44 — Canon and code disagree on where the accent may fill.** `docs/design/02-patterns.md` "Single accent doctrine" names an accent-filled Send as a permitted site. `docs/design/03-anti-patterns.md` §G "Personality bleeding" lists "a brand-colored Send button mid-thread" as an anti-pattern. Separately, the user bubble paints `bg-brand-muted` at `web/src/components/chat/user-message.tsx:272`, while the `--message-user` token defined for it in `globals.css` has no consumer. **Ruling:** UI-CRAFT-13 counts filled controls only, and it follows 02-patterns, so a filled Send passes. §G should be amended to say "a second brand-colored control", which is what it means. Whether the user bubble should use `--message-user` is a design call and is not a finding under any clause.

**C45 — The degraded banner displaces the privacy banner.** `web/src/components/chat/chat-thread.tsx` renders `TemporaryChatBanner` only when `isTemporary && !degradedActive`, so during a platform degrade a temporary chat loses its banner, and UI-TRUST-10 fails. `docs/design/03-anti-patterns.md` §G "Multi-banner walls" asks for the opposite order: "one persistent privacy banner at most; transient warnings appear as status-line entries". **Ruling:** UI-CRAFT-11 asserts the count only, and it passes. The win order is a defect against UI-TRUST-10, diagnosed here. The fix is to keep the temporary banner and move the degraded notice into the status line, as §G asks. A reviewer must not re-file it.

**C46 — Loading placeholders and copy casing have no canon.** Two gaps a craft review is likely to reach for have no ground to stand on. Loading placeholders: canon covers only the pre-first-token indicator (UI-STREAM) and the bootstrap retry. `globals.css` ships a `skeleton-shimmer` utility with no consumer, and bootstrap is a centred spinner. Copy casing: no repo document names a casing rule. Shipped labels are uniformly sentence case, and the one title-case label, "Download Markdown", names a format. **Ruling:** silence recorded, no clause for either. A reviewer must not file skeletons or casing by taste. If a PRD or 01-foundations names a rule, write the clause then.

**C47 — Empty states beyond the welcome surface have no canon.** Canon's "empty state" is the welcome surface only: `docs/prd/01-core-chat-experience.md` §4.7, the PRD 06 §4 table row and `docs/design/02-patterns.md`, "Empty state earns distinctiveness", all describe the greeting and its prompt cards, and UI-STATE-7 asserts them. The product has other empty states, each written ad hoc: "No chats yet" and "No matches" in `web/src/components/chat/sidebar.tsx`, "No results — try a different term" in `command-palette.tsx`, "No templates yet…" in `template-library-dialog.tsx` and `template-picker-popover.tsx`, the `showEmpty` branch of `memory-dialog.tsx`, the `showEmptyActivity` branch of `activity-dialog.tsx`, and the `showEmpty` branch of `template-library-dialog.tsx`. No document says what these must contain — a next step, an illustration, a single line — or how they relate to the welcome surface's distinctiveness rule. **Ruling:** silence recorded, no clause. A reviewer must not file their wording or composition by taste. If a PRD names a rule, write the clause then; UI-CRAFT-12, UI-LAYOUT-11 and the focus clauses already apply to them as to any surface.

**C48 — Toasts close on a clock the user cannot stop.** UI-STATE-8 `[must]` applies WCAG 2.2.1. In `web/src/components/ui/toast.tsx`, `defaultDurationFor` gives `info` and `success` 5000 ms, and `ToastItem`'s `setTimeout` runs to completion whatever the pointer or focus is doing. The `actions` field does not affect the duration either; it is unreachable today only because no consumer passes it. **Ruling:** fails. The fix is local to `ToastItem`: clear the timer on `pointerenter` and `focusin`, restart it on `pointerleave` and `focusout`, and resolve the duration to `null` whenever `actions` is non-empty.

**C49 — Links show their destination in a confirmation, not on hover.** `docs/prd/01-core-chat-experience.md` §5.4 asks that answer links "open in new tab, `rel="noopener noreferrer"`; show domain on hover". The build does neither literally. `markdown-renderer.tsx` leaves Streamdown's default `linkSafety` on, so a link renders as a `button` with no `href`, nothing appears on hover, and activation opens a confirmation that shows the full URL, whose "Open link" calls `window.open(url, "_blank", "noreferrer")`. The guarantee the PRD is after — the user sees where a link goes before going, and the new tab cannot reach back into the chat — holds, and holds more strongly than a hover would on touch. Two things follow. A link is no longer a link to assistive technology or to the browser: no link role, no "Copy link address", no middle-click. And the confirmation, per Streamdown's distributed bundle, carries no `role="dialog"` or accessible name; whether it meets UI-FOCUS-4 has not been measured. **Ruling:** UI-TRUST-13 asserts the guarantee and accepts either mechanism. Amend PRD 01 §5.4 to name the confirmation step, or turn `linkSafety` off and render anchors that meet the PRD's wording. A reviewer running UI-TRUST-13 should also run UI-FOCUS-4 on the confirmation.

---

## 16. Running a review

1. Read §15 first. Several entries there name a `[must]` clause that the current build fails for a reason already diagnosed — C13 through C25, C29 through C37, C39, C40, C42, C45 and C48, plus C41 as a `[should]` deviation — and re-filing one of those as a fresh defect wastes the review. An entry marked RESOLVED is closed and needs no attention.
2. Identify the surface and the renderings it has: visual light, visual dark, keyboard, screen reader, reduced motion, reduced transparency, increased contrast, forced colors, mobile touch, print. `docs/design/02-patterns.md` §E is the rule that these are the same UI, not accommodations.
3. Walk sections 1–14 in order. Skip a section only when the surface provably has no instance of it — record the skip.
4. For each `[must]` failure, file the defect against the clause ID. For each `[should]` deviation, require a rationale entry per `docs/design/04-rationale.md` before approval.
5. Re-run UI-PERF-1 (`pnpm check:bundle`) and UI-PERF-7 (`pnpm test:e2e:coverage && pnpm coverage:report`) on any PR that adds a dependency or a component.
6. Anything this document cannot decide goes in §15, not into the reviewer's judgment.
