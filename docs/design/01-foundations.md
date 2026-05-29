# Foundations

This file translates the four pillars from `00-principles.md` — minimalism, peacefulness, nature, and high aesthetics — into the five concrete surfaces every interface decision touches: color, typography, spacing, motion, and iconography.

It is the bridge between principle (`00-principles.md`) and pattern (`02-patterns.md`).

It does not publish tokens. Exact OKLCH values, rem ladders, motion durations, and the component inventory live in `docs/prd/06-design-system-visual-spec.md` ("PRD 06"); the live values are in `web/src/app/globals.css`. This chapter owns the *why* behind those numbers.

When a designer asks "why is the accent iOS blue?" the answer is here. When they ask "what is the accent hex?" the answer is PRD 06.

The voice of this chapter is declarative. A foundation is not a suggestion; it is the floor every component stands on. Where two pillars pull in different directions, the resolution is named explicitly so a reviewer can cite a rule rather than relitigate it.

## Color

Color is the loudest surface. Get it wrong and no amount of motion, type, or spacing can rescue the product.

The discipline below is what the low-chroma OKLCH palette in `web/src/app/globals.css` is *for*; this section explains the reasoning, not the values.

### Restraint by chroma

The palette is low-chroma. Background and surface tokens sit at a deliberately low chroma ceiling (exact range in PRD 06 §3.1), which is what makes the page read as calm before a single piece of content has loaded.

The hue is cool — a deliberately cool neutral hue (exact angle in PRD 06 §3.1) — and is deliberately secondary. It could be slid five or ten degrees warmer or cooler without changing what the product *is*. What is not negotiable is the chroma ceiling.

The reason is the deference principle inherited from Apple's Human Interface Guidelines: color is communication, not decoration ("Color," Apple HIG).

A high-chroma background competes with content. Once the surface is making a statement, the user's writing, the model's response, the code block, and the accent badge are all fighting for the same eye.

Lower the surface chroma and every meaningful glyph in the foreground gets louder for free. The chrome stops claiming attention it was never meant to hold.

The minimalism pillar from `00-principles.md` is sometimes read as "use less of everything." That reading is wrong for color. The pillar is asking for less *competition*, not fewer colors. A page with one accent and four well-chosen semantic roles is more minimal than a page with two muted greys, because the second page is hiding its hierarchy.

This is an honest trade-off and the chapter records it as such. The cool-neutral palette is Apple-HIG-aligned and resembles iOS more than it resembles a warm Bear-style canvas. Warmth in this product does *not* live in a sepia or off-white background.

Warmth lives in three other places, and naming them is important so reviewers stop asking the wrong question:

- The soft diffusion of the glass material — Liquid Glass-style blur with inset highlight and the opacity range specified in PRD 06, used for header float buttons, the composer capsule, and the FAB. The glass softens the boundary between chrome and content; that softness reads as warmth without ever shifting a hue.
- The spring curve of the entrance easing. A spring-decelerated motion is read by the eye as a living object settling, not a mechanical part snapping into place. That perception of life is warmth.
- The Ma-rich spacing between elements. Generous gutters between messages, between sections, around the empty state. Crowding is what makes an interface feel cold and rushed; space is what makes it feel hospitable.

A reviewer who asks for a "warmer" background is asking the wrong question; the lever they want is glass diffusion, spring easing, or gutter generosity, not a hue shift on the surface token. The hue is doing its job by stepping out of the way.

### A single saturated accent

There is exactly one saturated accent in the system, and it is the iOS-blue `--brand` (an OKLCH approximation of iOS system blue; exact hue in PRD 06 §3.1).

It carries primary affordance, focus, brand identification, and "destination" cues — the chips a user is meant to act on, the focus ring, the active state of a tier picker.

Everything else — destructive, success, warning, info — is allowed *one* saturated hue per role, used only when the role is invoked. Destructive only appears next to an irreversible action; warning only appears as a limit approaches. Routine chrome stays low-chroma.

The prohibition is structural: a second saturated accent is not allowed in steady state. If a future feature proposes a "secondary accent" — a teal for analytics, a violet for memory, a coral for sharing — that feature is being asked to compete with content.

Two saturated hues in steady state breaks deference and pulls the eye into the chrome. The product stops being a quiet surface for reading and writing; it becomes a dashboard. That is not the product this codebase is building.

The correct move for a feature that wants emphasis is a *role-bound* color (info, success, warning) used only at the moment the role applies, not a permanent second brand color riding alongside the accent.

A concrete violation: shipping a permanent violet "BYOK" pill next to the blue brand affordance on every assistant message.

The fix is in `web/src/app/globals.css` already — the BYOK indicator surface chroma is capped at the system's low-chroma tint ceiling (see PRD 06 §3.1) so the role is *recognizable* without becoming a second accent. It is a tint, not a hue claim.

Things 3 enforces the same one-accent discipline; Linear does the same. Both are referenced in `00-principles.md` for related reasons.

The discipline is not novel — it is the dominant rule among interfaces that read as calm and premium. A second saturated accent is the single most common reason a "clean" interface stops feeling clean.

### Semantic roles, not raw colors

Color tokens are named for what they *do*, not what they *are*.

PRD 06 §3.1 owns the role taxonomy — semantic roles, chat roles, trust roles — and this chapter does not republish it. What this chapter owns is the answer to "why a taxonomy at all?"

A component that picks a raw hex creates drift. The hex was correct on the day it was written; six months later the surface token has shifted by a few hundredths of chroma in dark mode, and that one component is now wrong in a way no audit can find by reading code. Nothing is broken; nothing throws. The component is just quietly off-system.

A role-bound component inherits the system. The same component is automatically correct in light, dark, increased-contrast, and any future theme. The acceptance criterion in PRD 06 §3.1 — zero hard-coded colors in chat feature code outside token or CSS-variable references — is the operational form of this principle.

Roles also encode *meaning*. `substitution-callout` is not just an amber surface; it is the system's promise that a forced model substitution will never look like an error (red) and will never look like routine chrome (muted).

The role exists so that promise can be enforced at the token level instead of being re-decided at every component. The first time a substitution callout ships in error red because a single engineer reached for a familiar destructive token, the trust the product is trying to build evaporates. The role taxonomy is the structural guarantee that won't happen.

The same logic applies to `trust-badge`, `byok-indicator`, and `temporary-chat-banner`. Each is a promise that the surface will read the same way every time it appears, across every theme. The promise is enforced by the token, not by reviewer vigilance.

### Light, dark, and OS-honored modes

Three modes are first-class: light, dark, and system. The system mode is the default.

Honoring the operating-system theme is not a feature; it is a baseline of respect for the user's environment — the same logic that dictates honoring `prefers-reduced-motion` and `prefers-reduced-transparency`.

A user who has chosen dark at the OS level has already declared their intent. An app that opens in light mode is overriding a decision the user already made.

Light and dark are mirrors of the same role taxonomy, not two different products.

Any visual difference between them beyond surface inversion is a bug. The chat role behaves the same way; the trust role behaves the same way; the accent stays the same accent, with the OKLCH lightness shifted but the hue unchanged.

PRD 06 §3.1's contrast requirements ensure both modes meet WCAG AA without re-art-directing either.

Code blocks are a deliberate exception worth naming. The code-block surface is dark in both modes — a near-black surface with light foreground text — because syntax highlighting is calibrated for dark surfaces and because that inversion telegraphs "this is code, not prose" without an additional badge. The inversion is the badge.

That exception is principled, not ad hoc. It survives the role-taxonomy test because the role is named (`code-block`, `code-block-foreground` in `web/src/app/globals.css`) and the surface is consistent across themes. A second exception of the same kind would have to clear the same bar.

## Typography

Type is where high aesthetics actually lives in this product. The system stack does not look like a custom typeface, but the *rhythm* of type — measure, leading, scale, weight — is fully under design control and is the highest-leverage place to spend craft.

### Type is the workhorse aesthetic

Bear and iA Writer earn their reputation almost entirely through typography. No illustration, no bespoke palette, no novel chrome — just disciplined type setting on a quiet canvas.

A chat product is a typography product wearing a chat product's costume. The single most important visible artifact, message after message, is body text.

If body text is set well, the product reads as premium. If body text is set poorly, no chrome can repair it. A glass capsule on top of badly leaded body text is lipstick.

This is what the high-aesthetics pillar from `00-principles.md` is asking for. Generous line-height, a restrained type scale (a handful of sizes, not a dozen), comfortable tracking, and a capped measure are how that pillar becomes visible in pixels.

The chat-body size is the body size in PRD 06 §3.2.

That choice is not a default; it is the size at which body text reads as comfortable on both a phone held at conversational distance and a laptop at desk distance. Anything smaller and the phone case suffers; anything larger and the laptop case starts to feel large-print.

Line-height follows. A tight `leading-tight` on body text reads as compressed and rushed; the generous leading specified in PRD 06 §3.2 is what gives long assistant responses room to breathe. The same body size with tight leading reads as a different — worse — product.

### System stack as deference

PRD 06 §3.2 requires the UI font to be a system stack or a single variable sans, with no blocking custom font on the critical path.

This is not a performance bullet hiding inside a design doc; it is a principle in performance clothing. A blocking custom font produces a flash of unstyled or invisible text — a moment where the user's attention is captured by the *typeface arriving* instead of the *content arriving*.

That is a deference violation. The font is competing with what the font is supposed to render. The user's eye is briefly held by a visual event that has nothing to do with the message.

The system stack also lets each operating system render in the family its user already trusts. A macOS user reads in SF; a Windows user reads in Segoe; an Android user reads in Roboto.

The product picks up the OS's optical tuning, hinting, and weight calibration for free. The result is not "no typography choice"; it is the choice to honor a thousand small decisions Apple, Microsoft, and Google have already made about how text should look on their respective surfaces.

A custom brand font is not forbidden forever — PRD 06 §8 leaves it as an open question gated on LCP budget. The principle this chapter records is the gate: a custom font ships only if it does not block first paint. That gate is permanent regardless of which font is eventually chosen.

### Dynamic scale

All type scales are rem-based. A user who has set their browser or OS to a larger root font size — for vision, for environment, for preference — gets a proportionally larger interface at every level.

This is the cross-platform analogue of Apple's Dynamic Type ("Typography," Apple HIG): the system honors the user's declared size, the design adapts.

The principle is not "support large text." The principle is that the user's declared comfort is part of the design input, not a constraint imposed on it.

A px-based ladder treats the design as authoritative and the user as a special case. A rem-based ladder treats the design as a recipe and the user as the cook. PRD 06's spacing scale ladders alongside the type scale precisely so the proportional relationships hold at any root size — the measure, the leading, and the gutters all scale together.

### Measure

Long-form readable text is capped at roughly 70–80 characters per line on wide screens.

This is not a stylistic preference; it is the readability law documented by Bringhurst in *The Elements of Typographic Style* and corroborated by every legibility study since.

A line longer than about 80 characters makes the eye lose its place returning to the next line; shorter than about 50 makes the eye work too hard scanning. The chat column is set to this measure for the same reason newspaper columns are: comfort over many minutes of reading.

The exact ceiling is PRD 06 §3.2's to set. The principle this chapter records is that no surface in this product is allowed to render long-form text edge-to-edge on a wide monitor.

If a future component wants the full width — a table, a diagram, a code block — that is acceptable because those surfaces are not read line-by-line. Prose is.

The same component can host both: a code block inside a message bubble is allowed to overflow the prose measure because the code is scanned, not read; the prose around it stays inside the measure.

The measure rule and the type-size rule work together. A comfortable body size at a 70–80ch measure stays restful; the same size stretched edge-to-edge on a wide monitor exhausts the eye. Both knobs matter. Adjusting one without the other moves the surface out of the comfort band.

## Spacing

This is the Ma (間) chapter. If a single principle had to carry the peacefulness pillar by itself, it would be the discipline of negative space.

### Ma — negative space as substance

In Japanese spatial aesthetics, *ma* is the interval — the gap between two notes, the pause between two phrases, the silence around a tea bowl. It is not the absence of substance; it *is* substance.

A Western reading of "empty space" treats the gap as nothing happening. A Ma reading treats the gap as the thing the surrounding objects exist to frame.

In this product, the gap between two messages, the gutter around the composer, the headroom above the empty state, and the floor below the last assistant response are all Ma. They are *load-bearing*.

They are the cheapest way to make an interface read as calm, and they are the first thing a feature under deadline pressure will try to compress. The pressure is wrong. Compressing Ma to fit "more" on screen does not make the interface denser; it makes it cramped, and cramped is the opposite of peaceful.

The rule this chapter writes down: when a layout feels crowded, the first move is to *add space*, not to shrink type or drop a divider. When a layout feels empty, the first move is to *add information*, not to fill the space with chrome.

Most "crowded" layouts have enough information and not enough Ma; most "empty" layouts have enough Ma and not enough information. Diagnose before adjusting.

### A strict base grid, generous gutters

PRD 06 §3.3 specifies the base grid unit. This chapter records why: a strict grid is what makes generous spacing read as intentional instead of sloppy.

Without a grid, large gutters look like a mistake — "did someone forget to align that?" With a strict base grid as the discipline, every gutter is a deliberate multiple, and the eye reads the rhythm even when it can't articulate it.

Discipline and generosity are not in tension. The grid is the discipline; the choice to use eight grid units instead of four for the inter-message gap is the generosity. PRD 06's spacing scale ladders up in multiples of the base unit precisely so a designer can choose "more breathing room" without leaving the system.

The rule: a generous gutter on a strict grid reads as calm. A tight gutter on a loose grid reads as careless. The pillars want the first.

Inter-message spacing in particular sits at the generous end of the scale (see PRD 06 §3.3).

Two messages packed tight read as a wall of dialogue; the same two messages spaced apart read as a conversation. The added Ma changes the *register* of the surface — from transcript to exchange.

Radius participates in the same logic. The base radius in `web/src/app/globals.css` is a single base radius (see PRD 06 §3.3) — rounded enough that nothing reads as a sharp box, restrained enough that nothing reads as a child's app. The radius scales proportionally with component size so the visual rhythm holds at every scale.

### Safe areas as floors

The composer and the header respect every `safe-area-inset-*` value. On a notched phone, on a home-indicator iPhone, on a foldable, on a tablet with a virtual keyboard, the composer never sits flush against the edge it isn't supposed to touch.

The CSS in `web/src/app/globals.css` defines a `--bottom-inset` that takes the larger of the OS-reported inset and a desktop floor (PRD 06 §3.3); this is the floor pattern in code.

The principle: a thumb-zone is real estate the *device* owns, not the *app*. The app is a guest there.

Treating the safe-area insets as floors rather than suggestions is the same logic as treating the OS theme as a default rather than an override — the device's declared constraints come first, and the design lives inside them.

This is also the bridge to PRD 03's mobile work. The composer is touch-safe (minimum target per PRD 06 §5.2) for the same reason it respects safe-area-inset: because the device is telling the app what it needs, and the app is listening.

Scrollbars belong in the same family. The thin themed scrollbar in `web/src/app/globals.css` honors the surrounding theme and stays out of the way until invoked. A heavy chrome-grey scrollbar would claim attention every time the user scrolls; the thin themed one does not. The principle: persistent interface furniture should be as quiet as possible without disappearing.

## Motion

This is where nature actually lives in this product. The pillars ask for an interface that feels *alive* without being busy; motion is the surface that carries that contradiction.

### Physical easing

Linear easing reads as artificial. A mechanical curve — constant velocity, sharp start, sharp stop — does not exist anywhere in the physical world; nothing in nature moves that way.

The eye reads it as machine motion and the interface reads as a machine. The product is supposed to feel alive; a machine curve undoes that on the first transition.

Spring physics — damped harmonic motion, gradual deceleration, the slight overshoot of an object settling — is how real objects move. Doors close that way. Drawers slide that way. Leaves fall that way.

The easing curve currently in use (specified in PRD 06 §3.4) is a spring approximation: it starts fast, decelerates dramatically, and settles. It is the visible expression of the nature pillar in `00-principles.md`.

The Nielsen Norman Group's "The Role of Animation and Motion in UX" (2020) formalizes this distinction: motion that follows physical curves is read as natural and pleasant; motion that follows mechanical curves is read as unpleasant or unfinished.

The principle: every animated transition in this product uses a spring-derived curve unless there is a documented reason not to.

A linear shimmer is acceptable for streaming because the *content itself* is the motion (the text is appearing) and the shimmer is a status surface; a linear UI transition is not.

Duration matters alongside curve.

A spring curve held too long reads as sluggish; the same curve at the durations specified in PRD 06 §3.4 reads as alive. PRD 06 §3.4 owns the durations; this chapter records that fast-but-decelerated is the target.

The eye should perceive the destination as inevitable, not as a long journey. A long journey is a screensaver; an inevitable arrival is a system.

### Cadence and stillness

Streaming text has a single steady cadence: the shimmer on reasoning, the pulse-soft on the typing indicator, the rAF-flushed token batching of the renderer.

These exist while the model is producing. The moment the model finishes, motion stops. Nothing in the periphery moves once the response settles.

This is the peacefulness rule from `00-principles.md` restated for motion: motion resolves to stillness.

An interface where idle elements drift, breathe, or pulse "to feel alive" is not peaceful; it is a screensaver. The product is alive when something is *happening* and quiet when nothing is.

Ambient micro-motion in steady state is a violation.

The system has a typing pulse because the system is typing; it does not have a "thinking" pulse on the avatar of a model that finished responding two minutes ago.

It does not have a slow ambient drift on the FAB. It does not have a breathing border on the composer when the composer is idle. Idle is still.

This rule has teeth at review time: any proposal for ambient idle-state motion has to defend itself against the peacefulness pillar before it ships.

The shimmer on reasoning is the boundary case worth naming. It is allowed because reasoning is *in progress* — the model is actively producing thought, and the shimmer is the visible cadence of that production. The moment reasoning resolves, the shimmer stops. The boundary is "is something happening right now?" — if yes, motion is allowed; if no, motion is a violation.

### Reduced motion as principle

`prefers-reduced-motion` is not an accessibility bolt-on. It is a principle gate.

The CSS in `web/src/app/globals.css` collapses animation and transition durations to effectively zero when the user has declared the preference, and PRD 06 §3.4 specifies the static "Generating..." substitute for the shimmer. PRD 01 §5.7 reiterates that this degrades gracefully across the chat surface.

The framing matters. A user who has set `prefers-reduced-motion` has told the system that motion makes their interaction worse — through vestibular sensitivity, through cognitive load, through preference.

Honoring that signal is the same kind of respect as honoring the dark-mode preference: the system default is a feature of the user's environment, and the app's job is to fit inside it. ("Motion," Apple HIG.)

The principle: every motion in the product has a static fallback specified at design time, not retrofitted at audit time.

The same logic extends to `prefers-reduced-transparency`, which collapses the glass material to a solid surface, and to `prefers-contrast: more`, which thickens hairlines and densifies fills. These are not three separate accessibility features; they are three instances of the same principle.

The principle is that the user's environment is part of the design input, not a constraint imposed on it. A design that breaks when these preferences are honored was never finished.

### Choreography of disclosure

Drawers slide. Sheets rise. Modals scale in. Reasoning panels expand.

These are *disclosures* — the interface is revealing information that was hidden a moment ago — and they share a choreographic logic: motion flows from the affordance that triggered it.

A sheet rises from the bottom because the gesture summoned it from the bottom. A drawer slides from the side because the trigger lives at the edge. A reasoning panel expands downward because the header that owns it is above.

Motion that does not flow from its trigger reads as random; motion that flows from its trigger reads as causal. The user does not have to think about it; the eye tracks it.

The same principle says: only one disclosure surface is in motion at a time. A sheet rising while a drawer is also sliding is two simultaneous claims on the user's attention.

The peacefulness pillar resolves this — one motion completes before the next begins. The cost is a few hundred milliseconds of serialization; the benefit is the user's attention is never split between two competing movements.

Elevation in this system is reserved for these disclosure surfaces (drawer, sheet, modal). Message surfaces stay flat.

This is the spatial half of the same choreographic principle: only things that have just appeared float above the page; the resting surfaces sit at zero elevation.

The glass material follows the same restraint. Glass is used for chrome — header float buttons, the composer capsule, the FAB — because those are the surfaces that *float* by definition. Message bubbles are not glass; they are flat. Using glass for resting content surfaces would turn the page into a stack of floating panels, which is the opposite of the calm flat canvas the pillars want.

## Iconography

Iconography is small surface, big consequence. A single off-system icon does more damage to coherence than an entire row of off-system buttons, because the eye reads icons as a family before it reads any one icon individually.

### Icons as glyphs

Apple's SF Symbols treats icons as typographic objects: matched weight to the surrounding text, matched optical scale, alignment to the baseline. An icon next to a label is not an image; it is a glyph.

The system this product uses — Lucide React — is not SF Symbols, but the discipline transfers. Lucide icons share a stroke weight, a corner radius, an optical scale, and a grid; that is what makes them read as one family.

The principle: icons inherit weight, scale, and alignment from their text context, not from themselves. An icon set rendered at an arbitrary size next to a body-text label, with a hardcoded stroke width that doesn't match the surrounding type, will read as foreign no matter how good the icon is. ("SF Symbols," Apple HIG, applies by analogy.)

The same rule covers optical centering. A small icon glyph dropped into a larger button without optical compensation sits *off-center* even though it is mathematically centered. The system's icon-bearing components handle this once, at the component layer; individual feature code does not re-solve it.

### One family, never mixed

The codebase uses Lucide React exclusively. There is no hand-rolled SVG in the components layer, and there is no second icon library.

The moment a custom SVG ships next to a Lucide icon, the system is broken — the two will not match on stroke weight, terminal style, optical centering, or grid, and the eye will see the inconsistency even when the reviewer cannot name it.

The rule is binary. Anything new must come from Lucide. If Lucide does not have the icon, the options are: pick a near-equivalent that does exist, request the icon upstream, or replace the entire icon system wholesale with a documented migration.

There is no "just one custom icon for this case." That is how systems die. The first custom icon makes the second easier to justify; the tenth has destroyed the family.

### Color from context

Icons take their color from the text context they sit in: an icon in muted-foreground text is muted-foreground; an icon in brand-foreground text is brand-foreground. Icons do not hard-code fills.

This is the same principle as the no-raw-hex rule in the color section, applied to a different surface. A hardcoded fill is a small bet that the design will never change; the bet always loses.

An icon that inherits from `currentColor` is correct in light, dark, hover, focus, disabled, and any future theme without any per-icon work.

The cost of the discipline is one line of code; the cost of skipping it is a global audit every theme change.

The same principle applies to icon weight in a future variable-weight icon system. If Lucide ships variable stroke weights, the icon should pick up its weight from a text-context CSS variable, not a per-component prop. The text decides; the icon follows.

## Closing

Foundations are *consistent application* of principle.

The point of writing them down is not to remember them — anyone who built the system can recite them — but to give a reviewer something to point at when a proposal drifts. "This adds a second saturated accent" is a faster conversation than "this feels off."

When a new token is proposed, ask first: which principle does it serve? If the answer is "none, but the designer wanted it" the token is decoration and should not ship.

Ask second: does an existing token already serve this? If yes, use the existing token. Tokens proliferate when each feature owner adds one rather than reusing one, and a system with three hundred tokens is a system with no tokens at all.

Ask third: which sibling doc does the proposal touch? A new pattern belongs in `02-patterns.md`. A new anti-pattern belongs in `03-anti-patterns.md`. A new rationale belongs in `04-rationale.md`. This file is the floor; the others build on it.

When in doubt, return to `00-principles.md`. The four pillars settle most arguments before they reach the token table.

The pillars are not equal weights in every situation. Peacefulness usually outranks high aesthetics when the two collide — a beautiful animation that disturbs the calm fails the more important test. Minimalism usually outranks nature when the two collide — a spring curve that adds visual interest but also adds a second moving element fails the deference test.

Naming the order helps. The rough sequence is peacefulness, then minimalism, then nature, then high aesthetics — not because high aesthetics matters less, but because high aesthetics is the *output* of the other three done well, not a separate lever. If the surface is calm, deferential, and physical, it will already read as high aesthetics. Reaching directly for high aesthetics without the other three produces decoration, not design.
