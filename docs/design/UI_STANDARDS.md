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
**Source.** `web/src/app/globals.css` `.chat-message-row` block; `docs/prd/03-mobile-cross-platform.md` §4.5 and §4.10 (CLS protection, reserve space); `docs/ux-best-practices/mobile-ux.md` §11 ("Virtualize messages past ~80 with overscan") and `docs/ux-best-practices/desktop-ux.md` §11 ("complement with `content-visibility: auto`" — the mobile document carries the virtualization half only).
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
**A wordmark is not an exception.** The product name set in the display serif at chrome size was argued as a logotype rather than UI text. It is not carved out, for a reason that is about type rather than about branding: Instrument Serif is drawn for hero sizes, and at 1.25 rem its hairlines muddy, so the header was using a display face below its optical size. The brand moment stays where the face reads — the hero greeting. A wordmark that needs to appear in the chrome appears in the UI sans.
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
**Source.** `web/src/app/globals.css` `.chat-md`, which is the normative figure for the two-step ramp; `docs/prd/06-design-system-visual-spec.md` §3.2 ("Chat body: 16px base, `rem`-based"), which commits to a `rem`-based body but states a single 16 px figure rather than this ramp — see §14 C12; `docs/design/03-anti-patterns.md` §D ("density that costs comprehension is not power-user density").
**Verify.** Computed style on `.chat-md`: `font-size` is `17px` at ≤767 px and `15px` at ≥768 px, `line-height` is `28px`.

### UI-TYPE-6 [must] — Reading measure is capped
**Assertion.** On any viewport wider than the column, a full line of assistant prose measures no more than ~80 characters; the column is capped, not fluid to the viewport.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("message column capped around 70–80ch on wide screens"); `docs/prd/03-mobile-cross-platform.md` §5.3; `docs/design/01-foundations.md`, Typography → "Measure"; `docs/design/03-anti-patterns.md` §D.
**Verify.** Playwright at 1920 px: measure the rendered column against the font's `ch` unit — `await page.evaluate(() => { const el = document.querySelector('.chat-md'); const probe = document.createElement('span'); probe.style.cssText='position:absolute;visibility:hidden;width:80ch'; el.appendChild(probe); const ok = el.clientWidth <= probe.clientWidth; probe.remove(); return ok; })`. **Note:** the shipped cap is a rem cap (`max-w-3xl` on `web/src/components/chat/message-list.tsx:366`), not a `ch` cap, so this must be measured rather than read off the class — see §14 C4.

### UI-TYPE-7 [must] — Monospace carries code and numerals
**Assertion.** Code blocks, inline code, token counts and USD figures render in `--font-mono`; prose never does.
**Source.** `docs/prd/06-design-system-visual-spec.md` §3.2 ("monospace: code blocks and token/cost numerals") and §5.5 ("numerals in monospace").
**Verify.** Computed `font-family` on a rendered `pre`, on inline `code`, and on the usage-meter figure resolves through `--font-mono`.

### UI-TYPE-8 [must] — Text survives user spacing overrides
**Assertion.** With line-height 1.5×, paragraph spacing 2×, letter-spacing 0.12× and word-spacing 0.16× forced, no text is clipped and no control overlaps.
**Source.** WCAG 2.2 SC 1.4.12 Text Spacing (AA). Repo canon is silent on this criterion (see §14 C6); it is `[must]` here because it is an AA criterion and C2 sets the bar at WCAG 2.2 AA, and it is adopted as part of the AA baseline that `docs/prd/03-mobile-cross-platform.md` §4.8 and `docs/ux-best-practices/desktop-ux.md` §10 commit the product to.
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
**Source.** WCAG 2.2 SC 2.4.13 Focus Appearance — **AAA**, not AA (see §14 C3, where `docs/ux-best-practices/desktop-ux.md` §10 cites it without its level); SC 1.4.11 Non-text Contrast (AA) carries the 3:1 half at AA. Shipped indicator: `--focus-ring` in `web/src/app/globals.css`.
**Verify.** Read the resolved `--focus-ring` value (a 2 px background offset plus a 2 px brand ring) and compute its contrast against `--background` and against each control fill, per theme.

---

## 5. Touch targets and pointer — `UI-TOUCH`

### UI-TOUCH-1 [must] — 44 px floor on touch
**Assertion.** On a device where `hover: none` matches, every interactive control has a hit region of at least 44×44 CSS px, measured on the hit region (which may be hit-slop) rather than the painted box.
**Source.** `docs/prd/06-design-system-visual-spec.md` §7 AC 6 ("Mobile primary controls >=44px") and §5.2 ("Stop is 44x44px minimum on mobile") — §3.3 covers spacing, radius and elevation and states no touch figure; `docs/prd/03-mobile-cross-platform.md` §4.8 ("44–48px"); `docs/mobile-ux/ST2-touch-audit.md` (method and offender table); `docs/mobile-ux/ST5-spec.md` §(d) gates H3/H4; Apple HIG (44×44 pt minimum hit target). **Stricter than external canon:** WCAG 2.2 SC 2.5.8 Target Size (Minimum) (AA) sets 24×24 px; repo canon rules and 44 is the floor on touch.
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
**Verify.** `rg -n 'cubic-bezier\(|\bease-(out|in|in-out|linear)\b' web/src/components` returns no hit. The `cubic-bezier` half alone is strictly weaker than the assertion and passes on code that fails it: Tailwind's `ease-out` utility resolves to `cubic-bezier(0, 0, 0.2, 1)`, a fifth curve that never appears as a literal. The check fails today — see §14 C13.

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
**Source.** WCAG 2.2 SC 1.3.5 Identify Input Purpose (AA) and SC 3.3.2 Labels or Instructions (A). Repo canon is silent on `autocomplete` (see §14 C6); the clause is `[must]` because both criteria fall inside the WCAG 2.2 AA bar C2 sets.
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
**Source.** `docs/prd/03-mobile-cross-platform.md` §4.2 ("History API integration"). The PRD asks for this on every overlay; only the drawer ships it, so the clause is scoped to what a reviewer can decide today — see §14 C14 for the sheets and panels.
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
**Verify.** Playwright: `await page.emulateMedia({ media: 'print' })`, then `page.pdf()` on a thread of **more than 80 messages**, and assert the first and the last message's text both appear in the extracted PDF text. The threshold matters: `VIRTUALIZE_AFTER` is 80 in `web/src/components/chat/message-list.tsx`, so a 30-message thread never virtualizes and cannot exercise the last half of the assertion. See §14 C15 — this check fails today.

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

---

## 15. Running a review

1. Read §14 first. Several entries there name a `[must]` clause that the current build fails for a reason already diagnosed — C13 through C25 — and re-filing one of those as a fresh defect wastes the review. An entry marked RESOLVED is closed and needs no attention.
2. Identify the surface and the renderings it has: visual light, visual dark, keyboard, screen reader, reduced motion, reduced transparency, increased contrast, forced colors, mobile touch, print. `docs/design/02-patterns.md` §E is the rule that these are the same UI, not accommodations.
3. Walk sections 1–13 in order. Skip a section only when the surface provably has no instance of it — record the skip.
4. For each `[must]` failure, file the defect against the clause ID. For each `[should]` deviation, require a rationale entry per `docs/design/04-rationale.md` before approval.
5. Re-run UI-PERF-1 (`pnpm check:bundle`) and UI-PERF-7 (`pnpm test:e2e:coverage && pnpm coverage:report`) on any PR that adds a dependency or a component.
6. Anything this document cannot decide goes in §14, not into the reviewer's judgment.
