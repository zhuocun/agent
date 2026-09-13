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

**Precedence when sources disagree.** PRDs win on concrete values (tokens, ratios, component states, acceptance criteria); `docs/design/*` wins on direction; `docs/ux-best-practices/*` wins on external rationale and review checklists — this ordering is stated in `docs/ux-best-practices/README.md` ("Canonical position") and `docs/design/README.md` ("Canonical position"). Where repo canon and external canon (WCAG, Apple HIG) conflict, **repo canon rules** and the clause says so explicitly. Section 14 is the standing register of every conflict and silence found while writing this document.

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
**Source.** `web/src/app/globals.css` `.chat-message-row` block; `docs/prd/03-mobile-cross-platform.md` §4.5 and §4.10 (CLS protection, reserve space); `docs/ux-best-practices/mobile-ux.md` §11 ("virtualize past ~80 with overscan; complement with `content-visibility: auto`").
**Verify.** Playwright: render a 100-message thread, record `document.body.scrollHeight`, scroll to the middle and back to the top, assert the height is unchanged within 1 px.

### UI-LAYOUT-4 [must] — Elevation is reserved for modal-class surfaces
**Assertion.** No message bubble, attribution row, reasoning panel, status line or inline control carries a `box-shadow` other than `none` at rest; shadow appears only on drawer, sheet, dialog, tooltip/popover and the transient jump-to-latest FAB.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.3 ("message surfaces remain flat; elevation reserved for drawer/sheet/modal"); `docs/design/02-patterns.md`, "Flat content, layered chrome" (exhaustive list); `docs/design/03-anti-patterns.md` §B; Decision 15 in `docs/design/04-rationale.md`.
**Verify.** Playwright: for `[data-testid="assistant-message"]`, `[data-testid="message-attribution"]`, `[data-testid="reasoning-panel"]`, `[data-testid="user-message-text"]`, assert `getComputedStyle(el).boxShadow === "none"`.

### UI-LAYOUT-5 [must] — Glass is chrome-only
**Assertion.** No element inside the message column has a non-`none` `backdrop-filter`; the `glass-regular` / `glass-strong` / `glass-clear` / `glass-capsule` / `chrome-frost` utilities appear only on header, composer capsule, FAB, drawer, dialog and popover surfaces.
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
**Verify.** Playwright at `?rtl=1`: assert `getComputedStyle(pre).direction === "ltr"`, assert `text-align` resolves to the start edge on `.chat-md`, and re-run the UI-LAYOUT-1 scroll-width assertion.

---

## 2. Typography and measure — `UI-TYPE`

### UI-TYPE-1 [must] — No blocking font on the critical path
**Assertion.** No `@font-face` on the critical path uses a blocking `font-display`; the UI stack resolves from `--font-sans` / `--font-mono` immediately, and `--font-heading` (Instrument Serif) loads with `display: optional` and a metric-adjusted fallback so it never swaps in late.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2; Decision 04 and Decision 16 in `docs/design/04-rationale.md`; `docs/design/03-anti-patterns.md` §D.
**Verify.** Grep the generated CSS for `font-display`; assert every face is `optional` (or absent). Lighthouse/DevTools: no render-blocking font request before first contentful paint.

### UI-TYPE-2 [must] — Display serif is welcome-only
**Assertion.** `--font-heading` is applied only to the welcome greeting at display size; no body, chrome, message or attribution text resolves to it.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("display sizes only"); Decision 16 in `docs/design/04-rationale.md`; `docs/design/03-anti-patterns.md` §G, "Personality bleeding into the working surface".
**Verify.** `rg -n 'font-heading' web/src` — every hit must be inside `welcome-screen.tsx`.

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
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("chat body: 16px base, `rem`-based"); `web/src/app/globals.css` `.chat-md`; `docs/design/03-anti-patterns.md` §D ("density that costs comprehension is not power-user density").
**Verify.** Computed style on `.chat-md`: `font-size` is `17px` at ≤767 px and `15px` at ≥768 px, `line-height` is `28px`.

### UI-TYPE-6 [must] — Reading measure is capped
**Assertion.** On any viewport wider than the column, a full line of assistant prose measures no more than ~80 characters; the column is capped, not fluid to the viewport.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("message column capped around 70–80ch on wide screens"); `docs/prd/03-mobile-cross-platform.md` §5.3; `docs/design/01-foundations.md`, Typography → "Measure"; `docs/design/03-anti-patterns.md` §D.
**Verify.** Playwright at 1920 px: measure the rendered column against the font's `ch` unit — `await page.evaluate(() => { const el = document.querySelector('.chat-md'); const probe = document.createElement('span'); probe.style.cssText='position:absolute;visibility:hidden;width:80ch'; el.appendChild(probe); const ok = el.clientWidth <= probe.clientWidth; probe.remove(); return ok; })`. **Note:** the shipped cap is a rem cap (`max-w-3xl` on `web/src/components/chat/message-list.tsx:366`), not a `ch` cap, so this must be measured rather than read off the class — see §14 C4.

### UI-TYPE-7 [must] — Monospace carries code and numerals
**Assertion.** Code blocks, inline code, token counts and USD figures render in `--font-mono`; prose never does.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("monospace: code blocks and token/cost numerals") and §5.5 ("numerals in monospace").
**Verify.** Computed `font-family` on a rendered `pre`, on inline `code`, and on the usage-meter figure resolves through `--font-mono`.

### UI-TYPE-8 [should] — Text survives user spacing overrides
**Assertion.** With line-height 1.5×, paragraph spacing 2×, letter-spacing 0.12× and word-spacing 0.16× forced, no text is clipped and no control overlaps.
**Source.** WCAG 2.2 SC 1.4.12 Text Spacing (AA). Repo canon is silent on this criterion (see §14 C6); it is adopted here as part of the AA baseline that `docs/prd/03-mobile-cross-platform.md` §4.8 and `docs/ux-best-practices/desktop-ux.md` §10 commit the product to.
**Verify.** Playwright: inject the WCAG text-spacing bookmarklet stylesheet, screenshot the surface, and assert no element has `scrollHeight > clientHeight` where `overflow` is `hidden`.

---

## 3. Color, theme and contrast — `UI-COLOR`

### UI-COLOR-1 [must] — Zero hard-coded colors in feature code
**Assertion.** No component file under `web/src/components/` contains a literal hex, `rgb()`, `hsl()` or `oklch()` color value; all color comes from the semantic, chat and trust tokens in `web/src/app/globals.css`.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1 AC ("zero hard-coded colors in chat feature code outside token/CSS variables"); `docs/design/03-anti-patterns.md` §A, "Raw hex codes in component code"; Decision 03 in `docs/design/04-rationale.md`.
**Verify.** `rg -n '#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(|oklch\(' web/src/components` returns no hit outside a documented exception. Exceptions today: the `--glass-*` rgba fills and the `forced-colors` system keywords, which live in `globals.css`, not in components.

### UI-COLOR-2 [must] — One saturated accent
**Assertion.** The only saturated hue in steady state is `--brand` / `--color-brand`; no surface introduces a second permanent saturated hue, and the semantic roles (`--color-destructive`, `--color-success`, `--color-warning`, `--color-info`) appear only inside their semantic context.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1; `docs/design/02-patterns.md`, "Single accent doctrine"; `docs/design/01-foundations.md`, Color → "A single saturated accent"; Decision 02 in `docs/design/04-rationale.md`.
**Verify.** Manual review against the token list, plus `rg -n 'accent-warm' web/src/components` — `--accent-warm` is a welcome-hero-only input to `--hero-glow-magenta` and must not appear in a component.

### UI-COLOR-3 [must] — Body text meets 4.5:1 in both themes
**Assertion.** Every body-size text/background pair resolves to a contrast ratio of at least 4.5:1 in light and in dark, including the attribution row, status lines, reasoning-panel text and the substitution callout.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.1 ("all body text pairs >= 4.5:1"); `docs/prd/03-mobile-cross-platform.md` §4.8; WCAG 2.2 SC 1.4.3 Contrast (Minimum) (AA).
**Verify.** Automated contrast sweep over the rendered surface in both themes (the axe-class run required by `docs/prd/06-design-system-visual-spec.md` §7 AC 4 — see §14 C5 for the missing dependency), or compute pairwise ratios from resolved `color` / `background-color` in a Playwright evaluate.

### UI-COLOR-4 [must] — Non-text UI meets 3:1
**Assertion.** Control boundaries, the focus indicator, the usage-meter fill, checkbox/switch states and the substitution-callout ring meet 3:1 against their adjacent surface in both themes.
**Source.** WCAG 2.2 SC 1.4.11 Non-text Contrast (AA); `docs/ux-best-practices/desktop-ux.md` §10 platform note ("focus ring must meet ... 3:1 contrast; audit `--focus-ring` token").
**Verify.** Compute the ratio between the resolved `--ring` / `--color-border` values and the surface they sit on, per theme.

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
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.4 ("every gesture has a tappable alternative") and §4.8; `docs/ux-best-practices/desktop-ux.md` §13 "Cross-platform seam"; WCAG 2.2 SC 2.5.7 Dragging Movements (AA).
**Verify.** Manual matrix review: for each entry in the shortcut table (`docs/prd/01-core-chat-experience.md` §5.5) and each gesture in `docs/prd/03-mobile-cross-platform.md` §4.4, name the visible control; a row with no named control fails.

### UI-FOCUS-8 [should] — Focus indicator meets the appearance target
**Assertion.** The focus indicator is at least 2 CSS px thick around the perimeter of the focused control and meets 3:1 against both the control and the adjacent background in both themes.
**Source.** WCAG 2.2 SC 2.4.13 Focus Appearance — **AAA**, not AA (see §14 C3, where `docs/ux-best-practices/desktop-ux.md` §10 cites it without its level); SC 1.4.11 Non-text Contrast (AA) carries the 3:1 half at AA. Shipped indicator: `--focus-ring` in `web/src/app/globals.css`.
**Verify.** Read the resolved `--focus-ring` value (a 2 px background offset plus a 2 px brand ring) and compute its contrast against `--background` and against each control fill, per theme.

---

## 5. Touch targets and pointer — `UI-TOUCH`

### UI-TOUCH-1 [must] — 44 px floor on touch
**Assertion.** On a device where `hover: none` matches, every interactive control has a hit region of at least 44×44 CSS px, measured on the hit region (which may be hit-slop) rather than the painted box.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.3, §5.2 and §7 AC 6; `docs/prd/03-mobile-cross-platform.md` §4.8 ("44–48px"); `docs/mobile-ux/ST2-touch-audit.md` (method and offender table); `docs/mobile-ux/ST5-spec.md` §(d) gates H3/H4; Apple HIG (44×44 pt minimum hit target). **Stricter than external canon:** WCAG 2.2 SC 2.5.8 Target Size (Minimum) (AA) sets 24×24 px; repo canon rules and 44 is the floor on touch.
**Verify.** Playwright with `hasTouch: true` at ≤767 px: for every `button, [role="button"], [role="tab"], [role="option"], a, input[type=checkbox]`, assert the union of `boundingBox()` and any `::before` hit-slop is ≥ 44 in both axes.

### UI-TOUCH-2 [must] — 24 px floor on pointer
**Assertion.** On a pointer device, every interactive control has a target of at least 24×24 CSS px, or is separated from its neighbours so that a 24 px circle centred on it overlaps no other target.
**Source.** WCAG 2.2 SC 2.5.8 Target Size (Minimum) (AA); `docs/ux-best-practices/desktop-ux.md` §13 D9 ("desktop may use denser targets (24px WCAG floor); gate 44px touch floor on `hover:none` only").
**Verify.** Playwright at 1280 px without `hasTouch`: assert every interactive `boundingBox()` is ≥ 24 in both axes, or that the spacing exception applies.

### UI-TOUCH-3 [must] — Dense clusters do not steal taps
**Assertion.** Adjacent controls in a cluster (segmented toggles, Edit/Delete pairs, tab strips) are separated by at least 8 px, and no expanded hit region overlaps a neighbour's.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.8 ("≥8px spacing"); `docs/mobile-ux/ST5-spec.md` §(d) gate H8 and §(e) risk R1 ("do not ship 44px targets without the spacing half").
**Verify.** Playwright with touch emulation: for each pair of sibling controls, assert the gap between their hit regions is ≥ 8 px and the regions do not intersect; then tap each and assert the intended handler fired.

### UI-TOUCH-4 [must] — Desktop density is not changed by a touch fix
**Assertion.** Every rule added to satisfy a touch floor is gated on `md:`, `@media (hover: none)` or `@media (pointer: coarse)`; a mouse viewport at ≥768 px renders byte-for-byte identically before and after the change.
**Source.** `docs/mobile-ux/ST5-spec.md` §0 cross-cutting invariant and §(d) gate H7 ("a hard acceptance criterion, not a nicety").
**Verify.** Playwright screenshot diff at 1280 px without `hasTouch`, before and after the change; zero pixel delta.

### UI-TOUCH-5 [must] — Touch floors are gated on pointer capability, not width
**Assertion.** The 44 px floor is selected by `hover: none` / `pointer: coarse`, so a touch tablet at ≥768 px keeps 44 px targets while receiving the desktop layout.
**Source.** `docs/ux-best-practices/desktop-ux.md` §13 D13 and `docs/ux-best-practices/mobile-ux.md` §13 M17; shipped in `web/src/components/ui/button.tsx` `buttonVariants` (`[@media(hover:none)]:size-11` / `:min-h-11`).
**Verify.** Playwright at 1024×768 with `hasTouch: true`: assert icon buttons measure 44 px and the desktop two-pane shell is rendered.

### UI-TOUCH-6 [must] — Hover is never the sole affordance
**Assertion.** Any control revealed on hover on a pointer device is persistently visible (or reachable through a labeled overflow control) on a touch device, and is revealed by `:focus-visible` for keyboard users.
**Source.** `docs/design/02-patterns.md`, "Density splits by input modality"; `docs/design/03-anti-patterns.md` §F, "One disclosure rule for both desktop and touch"; `docs/ux-best-practices/desktop-ux.md` §13 D3.
**Verify.** Playwright with `hasTouch: true`: assert message footer actions and conversation-row controls are visible without any hover event; then on desktop, Tab to the row and assert the same controls become visible.

### UI-TOUCH-7 [should] — Press feedback within 100 ms
**Assertion.** Every tappable control gives a visible pressed state (scale or fill change) within ~100 ms of touchdown, and that state is suppressed under `prefers-reduced-motion`.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.4 ("sub-100ms visual feedback regardless"); `docs/mobile-ux/ST4-native-gap-audit.md` G6; shipped in `buttonVariants` (`active:...scale-[0.96] active:duration-[70ms] motion-reduce:active:...scale-100`).
**Verify.** Computed style under `:active` shows a transform or background change with `transition-duration ≤ 100ms`; re-check under `prefers-reduced-motion: reduce` and assert the transform is `none`.

---

## 6. Motion and reduced motion — `UI-MOTION`

### UI-MOTION-1 [must] — Nothing animates in the periphery while the column streams
**Assertion.** While an assistant message is streaming, no element outside the streaming message column — header, sidebar, FAB, banners, badges — has a running animation or transition.
**Source.** `docs/design/00-principles.md`, Peacefulness ("the periphery carries none while the foreground is active"); `docs/design/02-patterns.md`, "Choreographed motion"; `docs/design/03-anti-patterns.md` §C, "Ambient motion outside a choreographed event".
**Verify.** Playwright: during a stream, `await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').map(a => a.effect.target.closest('[data-testid="message-list"]') ? null : a.effect.target.tagName).filter(Boolean))`; assert the result is empty.

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
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.4; `web/src/app/globals.css` easing tokens (which exist specifically so "future code reuses the tokens"); `docs/design/02-patterns.md`, "Choreographed motion" ("New surfaces should use one of these and not invent a third").
**Verify.** `rg -n 'cubic-bezier\(' web/src/components` returns no hit.

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

### UI-COMPOSER-8 [should] — Fields declare their purpose
**Assertion.** Inputs that collect information about the user (email, API key, display name) carry an appropriate `autocomplete` token and a programmatically associated label.
**Source.** WCAG 2.2 SC 1.3.5 Identify Input Purpose (AA) and SC 3.3.2 Labels or Instructions (A). Repo canon is silent on `autocomplete` (see §14 C6).
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
**Verify.** Playwright: `expect(page.locator('[role="status"][aria-live="polite"]')).toHaveCount(1)` scoped to the status region (toasts carry their own `aria-label` and must be excluded by that label, per `web/tests/e2e/ui-primitives.spec.ts`).

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
**Assertion.** No assistant message renders an inline cost figure or cost-breakdown popover in the thread; each finished assistant message instead exposes a keyboard-reachable, accessibly named **View spend** affordance that opens the Spend hub.
**Source.** `docs/prd/07-transparency-contract.md` §6.1, §8 AC 9 and §10 open question 2 (D41); `docs/prd/06-design-system-visual-spec.md` §5.4 and §8 open question 2. **This clause currently fails against shipped code** — no View-spend affordance exists in `web/src/components/` (see §14 C1). It is stated here as the bar, not as a description.
**Verify.** Playwright on a finished turn: assert the attribution row contains no `$` figure, and `expect(row.getByRole('link', { name: /view spend/i })).toBeVisible()`.

### UI-TRUST-4 [must] — Cost that is shown labels its confidence
**Assertion.** Wherever a cost figure is displayed (Spend hub, usage meter, model-picker list prices, agentic run meter), a non-exact computation is explicitly labeled as an estimate or as unavailable; a route with no published rate never renders an exact `$0.00`.
**Source.** `docs/prd/07-transparency-contract.md` §6.1 ("estimate labels must be explicit"), §7 rule 2 and §8 AC 4; `docs/prd/06-design-system-visual-spec.md` §5.4.
**Verify.** Playwright against a fixture whose `cost_confidence` is not `exact`: assert the rendered figure is adjacent to an estimate label and is not an exact-formatted zero.

### UI-TRUST-5 [must] — Public share strips cost and tokens, keeps model
**Assertion.** A public share view shows served model attribution and substitution callouts, and shows no cost figure, token count or breakdown anywhere in its markup or embedded JSON.
**Source.** `docs/prd/07-transparency-contract.md` §6.4 matrix and AC, and §8 AC 6; `docs/prd/06-design-system-visual-spec.md` §5.9 and §7 AC 3.
**Verify.** Playwright: mint a share link, fetch the public page, assert the rendered text contains the model label and assert the page HTML matches no `/cost_usd|costUsd|tokens?\b.*\d|cost_breakdown/` pattern.

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
**Assertion.** Every user-visible error states the outcome before the cause, offers two or three actions, never blames the user for a provider failure, and never implies persisted partial content was lost.
**Source.** `docs/prd/08-error-and-limit-states.md` §6 rules 1–5.
**Verify.** Manual copy review per error code against §6, using the canonical payload's `title` / `body` / `actions[]`; more than three actions, or a cause-first title, fails.

### UI-STATE-6 [must] — The meter is a labeled progress element
**Assertion.** The usage/budget meter exposes `role="progressbar"` with an accessible name, `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and an `aria-valuetext` carrying the human-readable detail.
**Source.** `docs/prd/06-design-system-visual-spec.md` §5.5; shipped in `web/src/components/chat/usage-meter.tsx`.
**Verify.** Playwright: `expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuetext', /.+/)` and assert the accessible name is non-empty.

### UI-STATE-7 [must] — The empty state is one hero plus a small card set
**Assertion.** The empty/welcome state renders one hero element and a small set of prompt cards (3–4) — not a feature grid, capability wall, marketing copy or dismissable banner — and unmounts after the first send.
**Source.** `docs/prd/06-design-system-visual-spec.md` §4 ("empty state: greeting + 3–4 prompt cards"); `docs/design/02-patterns.md`, "Empty state earns distinctiveness"; `docs/design/03-anti-patterns.md` §F and §G; Decision 11 in `docs/design/04-rationale.md`.
**Verify.** Playwright: on a fresh session assert the prompt-card count is ≤ 4; send a message and assert the welcome surface is detached and does not reappear in the same conversation.

---

## 11. Mobile viewport and safe areas — `UI-MOBILE`

### UI-MOBILE-1 [must] — `viewport-fit=cover` is set
**Assertion.** The document's viewport meta includes `viewport-fit=cover`, without which every `env(safe-area-inset-*)` resolves to zero.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.3 ("required for `env(safe-area-inset-*)` to be non-zero at all"); shipped in the `viewport` export of `web/src/app/layout.tsx` (`viewportFit: "cover"`).
**Verify.** Playwright: assert the rendered `<meta name="viewport">` content contains `viewport-fit=cover`.

### UI-MOBILE-2 [must] — All four insets are honored on edge-anchored chrome
**Assertion.** Header, composer, bottom sheets, the command palette sheet, toasts and the install coachmark each apply the top, bottom, left and right safe-area insets — not bottom only — so nothing sits under the notch, the home indicator or a landscape inset.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.3; `docs/prd/03-mobile-cross-platform.md` §4.3; `docs/design/01-foundations.md`, Spacing → "Safe areas as floors"; `docs/mobile-ux/ST4-native-gap-audit.md` G2/G3/G10.
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
**Assertion.** Opening a drawer, bottom sheet or full-screen panel pushes a history entry, so the device/gesture Back dismisses them in order — bottom sheet, then drawer, then full-screen panel, then chat root — before leaving the app.
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.2 ("History API integration").
**Verify.** Playwright: open a drawer then a sheet; `page.goBack()` twice; assert the sheet closes first, then the drawer, and the URL is still the chat route.

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
**Verify.** Playwright with the media emulated: assert `backdropFilter === "none"` on `.glass-regular`, `.glass-strong`, `.glass-capsule`, `.glass-clear` and `.chrome-frost`, and that each has a non-transparent `background-color`.

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
**Verify.** Playwright: `await page.emulateMedia({ media: 'print' })`, then `page.pdf()` on a 30-message thread; assert every message's text appears in the extracted PDF text.

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

## 14. Conflict and silence register

Recorded while writing this document. Each entry names the disagreement, the ruling, and what a reviewer should do.

**C1 — Canon requires an affordance that is not shipped.** `docs/prd/07-transparency-contract.md` §6.1 and §8 AC 9, and `docs/prd/06-design-system-visual-spec.md` §5.4 (D41), require a per-message **View spend** link on every finished assistant message. No such affordance exists in `web/src/components/` (`rg -i 'view spend' web/src` returns nothing), and `web/src/components/chat/attribution-row.tsx` renders no cost element at all. **Ruling:** UI-TRUST-3 states the canon bar; it fails today, and that is a defect against PRD 07, not a defect in this document.

**C2 — WCAG version is stated two ways.** `docs/prd/06-design-system-visual-spec.md` §2 sets the goal at "WCAG 2.1 AA (stretch 2.2 AA where cheap)", while `docs/prd/03-mobile-cross-platform.md` §4.8 makes WCAG 2.2 SC 2.5.8 a P0 floor and `docs/ux-best-practices/desktop-ux.md` §10 / `docs/ux-best-practices/mobile-ux.md` §10 target 2.2 AA including 2.4.11, 2.5.7 and 2.5.8 — with shipped implementations (the `.chat-message-row` scroll margins in `globals.css` are commented "WCAG 2.4.11"). **Ruling:** repo canon prevails over external canon, but here repo canon contradicts itself; this document takes **WCAG 2.2 AA** as the bar, because PRD 03 §4.8 is the more specific clause and is the one that shipped. PRD 06 §2 should be amended to match.

**C3 — A criterion is cited without its level.** `docs/ux-best-practices/desktop-ux.md` §10 platform note treats SC 2.4.13 Focus Appearance as a requirement. 2.4.13 is **AAA** in WCAG 2.2; the AA obligations for focus are 2.4.7 Focus Visible and 2.4.11 Focus Not Obscured (Minimum), with the 3:1 indicator contrast coming from 1.4.11 Non-text Contrast. **Ruling:** UI-FOCUS-2 and UI-FOCUS-3 are `[must]` at AA; UI-FOCUS-8 carries the 2.4.13 appearance target as `[should]`.

**C4 — The measure cap is not expressed in the unit canon uses.** PRD 06 §3.2 and PRD 03 §5.3 cap the reading column at ~70–80ch, but the shipped cap is `max-w-3xl` (48 rem) on `web/src/components/chat/message-list.tsx:366` — a rem cap whose character count depends on the resolved font. **Ruling:** UI-TYPE-6 is written against the ch cap and must be *measured*, never inferred from the class. A reviewer who measures above 80ch should file against PRD 06 §3.2 rather than silently widening this standard.

**C5 — A required tool is not installed.** `docs/prd/06-design-system-visual-spec.md` §7 AC 4 requires an "axe-class check: 0 critical violations on chat, composer, settings, palette", but no axe dependency exists in `web/package.json` and no spec in `web/tests/e2e/` runs one. **Ruling:** every clause here that would naturally be an axe rule (UI-COLOR-3, UI-FOCUS-5, UI-STREAM-1) is given an explicit Playwright or computed-style check that does not depend on axe. Wiring the axe-class gate is outstanding work against PRD 06 §7 AC 4.

**C6 — Canon is silent on three AA criteria a reviewer will need.** Nothing in the PRDs or the UX best-practice docs addresses WCAG 2.2 SC 1.4.12 Text Spacing, SC 1.3.5 Identify Input Purpose, or SC 3.3.7 Redundant Entry. **Ruling:** 1.4.12 and 1.3.5 are adopted here as `[should]` (UI-TYPE-8, UI-COMPOSER-8) on the strength of the 2.2-AA commitment in C2; 3.3.7 is left unstated because no flow in this product currently re-asks for previously entered information. If one is added, this register is where the clause gets filed.

**C7 — Two supporting documents carry stale paths.** `docs/mobile-ux/ST5-spec.md` §(c) lists `web/src/components/layout/app-shell.tsx` and `.../layout/app-header.tsx`; no `layout/` directory exists — both files live under `web/src/components/chat/`. Separately, `web/.nycrc.json` excludes three files that no longer exist (`src/components/chat/history-search-dialog.tsx`, `src/components/chat/spend-dialog.tsx`, `src/components/ui/skeleton.tsx`). **Ruling:** neither changes a standard, but a reviewer following ST5's file list will not find the files, and the stale nyc excludes quietly widen the coverage exemptions. Both are cleanup items.

**C8 — Repo canon is deliberately stricter than external canon in two places.** Touch target: Apple HIG and repo canon set 44 pt where WCAG 2.2 SC 2.5.8 sets 24 px — repo wins (UI-TOUCH-1), with 24 px retained only as the pointer-device floor (UI-TOUCH-2). Motion: `prefers-reduced-motion` support corresponds to SC 2.3.3, a AAA criterion, but `docs/prd/06-design-system-visual-spec.md` §7 AC 8 makes it release-blocking — repo wins (UI-MOTION-5). Both are noted inside the clauses so no reviewer relaxes them by citing the weaker external number.

---

## 15. Running a review

1. Identify the surface and the renderings it has: visual light, visual dark, keyboard, screen reader, reduced motion, reduced transparency, increased contrast, forced colors, mobile touch, print. `docs/design/02-patterns.md` §E is the rule that these are the same UI, not accommodations.
2. Walk sections 1–13 in order. Skip a section only when the surface provably has no instance of it — record the skip.
3. For each `[must]` failure, file the defect against the clause ID. For each `[should]` deviation, require a rationale entry per `docs/design/04-rationale.md` before approval.
4. Re-run UI-PERF-1 (`pnpm check:bundle`) and UI-PERF-7 (`pnpm test:e2e:coverage && pnpm coverage:report`) on any PR that adds a dependency or a component.
5. Anything this document cannot decide goes in §14, not into the reviewer's judgment.
