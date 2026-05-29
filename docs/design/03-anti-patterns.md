# Anti-Patterns

A curated list of failure modes the product is actively designed against. Each entry names a specific shipped-or-shippable mistake, the pillar or rule it violates, and the correct move. The point is to fail a code review before the mistake lands, not to lecture. Where a "why not" needs more breath than one sentence allows, the entry cross-references a decision in `04-rationale.md`.

The categories below match the foundations and patterns from `01-foundations.md` and `02-patterns.md`; the violations here are the negative space around those positive specs.

## A. Palette and color

### Anti-pattern: Second saturated hue alongside the accent

**What it looks like:** A warm or saturated secondary color (terracotta success, ochre warning treatment, magenta link) used as a decorative accent next to the iOS-blue primary.
**Why not:** Violates the single-accent doctrine from `00-principles.md` (Minimalism); two accents on a calm surface always read as two accents competing.
**Instead:** Keep the single brand accent for primary action and focus only. Reach for muted-foreground or chroma-trimmed semantic roles for secondary emphasis (see `01-foundations.md` color section; Decision 02 in `04-rationale.md`).

### Anti-pattern: Raw hex codes in component code

**What it looks like:** `color: #1d4ed8` or `background: rgb(245, 244, 240)` literal in a component file, a story, or a Tailwind arbitrary value.
**Why not:** Breaks PRD 06 §3.1's acceptance criterion ("zero hard-coded colors in chat feature code outside token/CSS variables") and silently desynchronizes light/dark themes.
**Instead:** Use the semantic token names defined in PRD 06 §3.1 and `web/src/app/globals.css` (e.g., `--color-foreground`, `--color-message-assistant`). Decision 03 in `04-rationale.md` covers why the token system is OKLCH and why that matters.

### Anti-pattern: High-chroma background fill

**What it looks like:** A section, panel, or message surface filled with any non-neutral color whose OKLCH chroma exceeds the palette floor (the calm low-chroma neutrals defined in `globals.css`).
**Why not:** Saturated backgrounds permanently destabilize the reading column and make code, math, and substitution callouts illegible at AA contrast.
**Instead:** Backgrounds stay in the low-chroma neutral band; emphasis comes from spacing, weight, or the single accent on a small surface (a button, a focus ring).

### Anti-pattern: Destructive color spent on non-destructive states

**What it looks like:** Destructive red used to brand a "Premium" badge or warning amber to dress up an empty state; the served-vs-requested substitution callout styled as an error; a red Stop button replacing Send during streaming.
**Why not:** Semantic colors carry meaning — using them decoratively burns their signal value for the moment they are actually needed (a confirm-delete dialog, a near-cap usage meter). Substitution is not failure; it is a transparency event (PRD 07 §5–§6). Stop is a neutral control — pause, not error (PRD 06 §5.2; PRD 01 §5.1's "Stopped chip, not red error treatment"). Painting either red miscommunicates the meaning and dilutes the destructive role.
**Instead:** Decorative emphasis uses spacing, weight, or — sparingly — the brand accent. Substitution uses the dedicated `--color-substitution-callout` role from PRD 06 §3.1. Stop renders in the same slot as Send with a neutral chip; "Stopped" status uses neutral foreground. Destructive is reserved for confirm-delete and irreversible actions (PRD 06 §3.1; PRD 08).

## B. Surface and elevation

### Anti-pattern: Borders or shadows on message surfaces

**What it looks like:** A card border, soft drop shadow, or hairline frame applied to the assistant or user message body.
**Why not:** Violates PRD 06 §3.3 ("message surfaces remain flat") and the Minimalism pillar's deference rule — chrome on the reading column makes content compete with its own frame.
**Instead:** Messages are typographic units differentiated by alignment, spacing, and (for code) the `--color-code-block` surface. Elevation is reserved for drawer, sheet, and dialog. See Decision 15 in `04-rationale.md`.

### Anti-pattern: Glass material on message bubbles

**What it looks like:** Backdrop-blur, glass tint, or specular highlight applied to the assistant or user message surface.
**Why not:** Glass is reserved for chrome (header float, composer capsule, FAB) per `01-foundations.md`; applying it to content makes the content itself shimmer with the background it sits on, which is the opposite of reading calm.
**Instead:** Glass on chrome only. Messages stay flat and opaque. Decision 06 in `04-rationale.md` explains why.

### Anti-pattern: Always-on elevation on inline controls

**What it looks like:** A small icon button or chip rendered with persistent shadow at rest, mid-thread.
**Why not:** Elevation is the language of modal-class surfaces (drawer, sheet, dialog, FAB). Spending it on inline controls dilutes the hierarchy and adds visual noise to the reading column.
**Instead:** Inline controls are flat at rest. Elevation appears only on the surfaces PRD 06 §3.3 names. See Decision 15 in `04-rationale.md`.

## C. Motion and stream behavior

### Anti-pattern: Ambient motion outside a choreographed event

**What it looks like:** A logo that bobs at rest; a send button that gently breathes; a hero gradient that drifts on the empty state; an auto-rotating banner in the header; hover decoration on a sidebar item that animates while the message column is streaming.
**Why not:** Violates the Peacefulness pillar's rule that motion is choreographed, not constant ("two motions on screen at once are one too many"). Idle surfaces that animate force the user to filter the periphery; periphery that animates during streaming competes with the active reading column.
**Instead:** Motion is bound to a discrete event (a stream arriving, a panel opening, a focus state engaging). Idle surfaces are still; while streaming, the header, sidebar, and FAB are visually inert. Streaming shimmer and pulse live only inside the streaming context and end with the stream.

### Anti-pattern: Motion without a `prefers-reduced-motion` fallback

**What it looks like:** Shipping a new animation, transition, or shimmer without designing the reduced path at the same time.
**Why not:** Treating reduced-motion as a follow-up violates the Peacefulness pillar's "first-class path, not a fallback" rule and PRD 06 §3.4. PRD 06 §7 lists it as release-blocking.
**Instead:** Design the reduced path in the same review. Shimmer degrades to a static "Generating..." indicator; entrance transitions collapse to opacity or vanish entirely. Decision 13 in `04-rationale.md`.

### Anti-pattern: Animating layout while content streams

**What it looks like:** A message bubble whose width or padding tweens as new tokens arrive; a code block whose corner radius interpolates while collapsing.
**Why not:** Compounds with rAF token flushing to produce visible jank and violates PRD 01 §5.4's no-layout-shift renderer contract.
**Instead:** Geometry is fixed at frame boundaries during streaming. Animations of layout happen when streaming ends, or on user interaction. Decisions 08 and 09 in `04-rationale.md` cover why motion is choreographed around the stream rather than across it (the reasoning-panel collapse, specifically, fires *after* the stream completes).

### Anti-pattern: Auto-scroll that fights the reader

**What it looks like:** The view follows the stream to the bottom even after the user scrolls up to re-read a previous turn.
**Why not:** Violates PRD 01 §5.1's auto-scroll rule ("follow only if the user is already at/near the bottom") and is one of the most-cited usability failures in chat products.
**Instead:** Auto-scroll engages only at/near the bottom; otherwise show the "↓ Jump to latest" pill and stop following.

## D. Typography

### Anti-pattern: Custom font discipline broken on the working surface

**What it looks like:** A `@font-face` declaration without `font-display: swap` (or `optional`), or a font preload that blocks first paint; a "branded" serif for assistant messages, a sans for chrome, and a different mono than the project's chosen one for code.
**Why not:** A blocking font ships text-of-interest behind a network round-trip and degrades LCP — PRD 06 §3.2 forbids it outright. Multiple type families on the working surface make family swap the loudest possible typographic signal, destroying hierarchy and shouting "designed" in the place the design should be quiet. Both fail Minimalism's deference rule.
**Instead:** Use the system font stack via the CSS variables already defined in `web/src/app/globals.css`. One sans family on the working surface, one mono family for code/numerals (PRD 06 §3.2). Hierarchy comes from weight, size, and spacing — not family swaps. Decision 04 in `04-rationale.md`.

### Anti-pattern: Reading text that ignores user scale

**What it looks like:** A type scale defined entirely in `px` across the reading column; a "denser" thread mode that drops the message body below the comfort floor PRD 06 §3.2 names.
**Why not:** A px-only scale defeats the user's OS-level font-size preference (the Dynamic-Type analogue named in PRD 06 §3.2) and is hostile to readers who need larger text; shrinking the reading text under the banner of density loses readability outright. Density that costs comprehension is not power-user density; it is regression dressed up as compactness.
**Instead:** Body and UI text use `rem` so the user's root setting governs scale; density comes from spacing and from the dense-affordance patterns in `02-patterns.md`, not from shrinking the reading text. Decision 04 in `04-rationale.md`.

### Anti-pattern: Measure exceeding ~80ch on wide screens

**What it looks like:** A message column that expands to fill a 1600px viewport, producing lines hundreds of characters wide.
**Why not:** Reading research consistently puts comfortable measure at 45–80ch; PRD 06 §3.2 caps around 70–80ch. Wider lines drop comprehension and break Ma in the surrounding column.
**Instead:** Cap the message column. Surrounding space is feature, not waste.

## E. Iconography

### Anti-pattern: Mixed icon families or stroke weights

**What it looks like:** A handful of bespoke SVG icons sprinkled among Lucide imports because "Lucide didn't have exactly the right one"; Heroicons in marketing, Phosphor in settings, Lucide in chat.
**Why not:** Every family has a distinct stroke and grid; mixing them — even at the level of one bespoke glyph next to a Lucide row — is visible at a glance and produces the optical inconsistency the High-Aesthetics pillar specifically forbids ("match the optical weight of icons to neighboring text at every breakpoint").
**Instead:** One family across the entire surface — Lucide exclusively (Decision 05 in `04-rationale.md`). If a specific glyph genuinely does not exist, propose it upstream or change the affordance to a labeled control rather than introducing a second family.

### Anti-pattern: Hardcoded fill or stroke colors on icons

**What it looks like:** `<svg fill="#3B82F6">` or a CSS rule pinning icon stroke to a literal color.
**Why not:** Breaks dark mode parity (Decision 03 in `04-rationale.md`) and re-introduces the hardcoded-color anti-pattern through the side door.
**Instead:** Icons inherit `currentColor` and pick up the surrounding text token. Tinting happens at the container, not the SVG.

## F. Disclosure and density

### Anti-pattern: One disclosure rule for both desktop and touch

**What it looks like:** Copy / regenerate / edit icons rendered at full opacity under every message at rest on desktop; or, the opposite failure, a touch device that shows nothing where desktop's hover would have revealed the message actions, leaving users unable to copy or regenerate.
**Why not:** Permanently-visible affordances on desktop violate Minimalism's "hide chrome until interaction asks for it" rule and add ambient noise to the reading column. Mirroring desktop hover-reveal to touch is the most common cross-platform a11y break, because touch has no hover. The two surfaces need different disclosure rules.
**Instead:** Hover-reveal the action row on desktop with focus-visible parity for keyboard users; touch surfaces the affordances always-on (or via long-press for secondary actions). See `02-patterns.md` for the disclosure matrix.

### Anti-pattern: Persistent tooltip-like banners

**What it looks like:** An always-visible "Tip:" or "Did you know?" strip pinned to the top of the thread.
**Why not:** Tooltips and contextual help are choreographed (they appear in response to a question), not ambient. A persistent banner is ornament that occupies prime real estate.
**Instead:** Help is reachable from the command palette and the `?` shortcut; transient education appears on first-run only.

### Anti-pattern: Hover-only cost or model details

**What it looks like:** The served model is shown only on hover over the assistant message; cost details require a mouseover.
**Why not:** Violates PRD 07 §6.1 ("every assistant message shows served model/tier without hover") and the transparency-as-chrome rule.
**Instead:** Model attribution is always visible; expandable details handle the second tier. Decision 12 in `04-rationale.md`.

## G. Chrome and ornament

### Anti-pattern: Decorative dividers, ASCII art, ornament-as-decoration

**What it looks like:** A row of `─────` or a glyph flourish separating empty-state copy; banner art that exists for personality.
**Why not:** Decoration substitutes for refinement that was not done; the High-Aesthetics pillar specifically rules ornament out.
**Instead:** Use spacing and type hierarchy to carry the structure. If a divider is truly needed, it is a single hairline at `--color-border`.

### Anti-pattern: Multi-banner walls

**What it looks like:** A temporary-chat banner stacked above a BYOK banner stacked above a usage-warning banner, with a gradient strip on top.
**Why not:** Each banner taken alone is in-spec; the wall of them is what violates the Peacefulness pillar. The thread becomes a notification surface, not a reading surface.
**Instead:** Banners collapse and prioritize: one persistent privacy banner at most; transient warnings appear as status-line entries inside the thread; sticky elements compete with each other for a single slot.

### Anti-pattern: Personality bleeding into the working surface

**What it looks like:** The product logo persistently rendered in the chat header; a brand-colored Send button mid-thread; atmospheric gradients or hero typography that the welcome state uses correctly, repeated on the working thread.
**Why not:** Distinctiveness belongs to empty states, transitions, and the first-run moment — not the working surface (`00-principles.md`, Tension 5; Decision 11 in `04-rationale.md`). Spending the personality budget on the thread forces the user to read past it on every turn for the life of the product.
**Instead:** The thread is calm and generic by design. Brand and atmosphere surface on the welcome state, the empty state, and the marketing entry points; the transition between welcome and thread is itself a designed moment (see `02-patterns.md`).

## H. Accessibility-as-bolt-on

A category, not a single anti-pattern. Each item below is its own violation; collectively they are the symptom of treating accessibility as cleanup rather than as foundation.

### Anti-pattern: Icon buttons without accessible names

**What it looks like:** `<button><CopyIcon /></button>` with no `aria-label`, no `<span class="sr-only">`, no surrounding label.
**Why not:** PRD 01 §5.7 and PRD 06 §5.1 require 100% accessible-name coverage on icon-only controls; this is a release-blocking gap.
**Instead:** Every icon-only button has a descriptive accessible name. The label survives icon swaps.

### Anti-pattern: Live region wrapping streamed body content

**What it looks like:** The assistant message body itself is `aria-live="polite"`, so NVDA/JAWS re-read partial tokens as they arrive.
**Why not:** Documented anti-pattern in PRD 06 §3.5 and PRD 01 §5.7. Token-by-token re-reading is functionally hostile.
**Instead:** A separate `aria-live="polite"` status region announces discrete transitions ("Generating", "Response ready", "Stopped"). The message body is navigable but not auto-announced. Decision 14 in `04-rationale.md` explains why the body is not a live region.

### Anti-pattern: Focus traps without close + restore

**What it looks like:** A shortcuts dialog or command palette that traps focus on open but does not restore focus to the invoking control on close.
**Why not:** Violates PRD 01 §5.7 and PRD 06 §7. Users lose their place in the keyboard map.
**Instead:** Open → focus moves in; Tab cycles within; Esc closes; focus restores to the invoking control. This is one of the named acceptance criteria.

### Anti-pattern: Mobile composer that breaks thumb-zone ergonomics

**What it looks like:** Icon buttons shipped to the mobile composer below the touch-target minimum PRD 06 §5.2 names ("the icon is only 16px"); a sticky composer that sits under the iOS home indicator or behind the notch.
**Why not:** Sub-minimum targets are hostile to thumb interaction and to motor-impairment users; ignoring `safe-area-inset` breaks mobile-web on iOS Safari, which is the primary surface per PRD 00. Both fail PRD 06 §3.3 and §5.2, and both make Stop unreachable at exactly the moment the user needs to abort.
**Instead:** Mobile primary controls meet the PRD 06 §5.2 touch-target minimum and respect all four `safe-area-inset-*` directions (the `--bottom-inset` token is defined in `globals.css` for this). Stop stays sticky and reachable. Decision 10 in `04-rationale.md`.

