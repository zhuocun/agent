# Principles

The product is built on four pillars — minimalism, peacefulness, nature, and high aesthetics — held together by a single meta-rule: when in doubt, subtract. Minimalism is the floor. The other three pillars are not achieved by what gets added but by what survives the cut: warmth in the palette and motion, charged emptiness in the spacing, thoroughness in the typography. The pillars genuinely conflict in real design work, so each is given a sharper operational definition than its label suggests, and the conflicts are named and ruled at the end of this document.

## Minimalism

Minimalism here means *deference*, not asceticism. The chrome recedes so the content leads. In a chat product the conversation is the protagonist; every chromatic, decorative, or motion choice that competes with the streaming text is a regression. Minimalism is not the absence of design — it is design pulled tight enough that nothing in the interface is louder than the user's own thought.

Asceticism would say: remove things until only the necessary remains. Deference says: shape what remains so that it points to the user's content rather than to itself. A perfectly empty composer is not minimalist if it sits inside a header with three competing affordances; a richly featured composer can be minimalist if its affordances quiet down the moment the user starts typing. The test is not "is there less?" but "does the content lead?"

The product surface that benefits most from this distinction is the message column. A streamed assistant response is dense with structure — code, prose, math, citations, tool calls — and the chrome that frames it is constantly tempted to compete for attention with badges, dividers, and accent surfaces. Deference is the discipline that keeps those temptations off the screen until the user reaches for them.

This pillar descends from two traditions. Apple's Human Interface Guidelines articulate the trio of deference, clarity, and depth as foundations for software that feels native rather than dressed up (Apple HIG, on deference, clarity, and depth). Dieter Rams' tenth principle — "less, but better" — governs the difference between subtraction-as-laziness and subtraction-as-craft (Rams, "Ten Principles for Good Design"). Read together, they say the same thing in two dialects: refuse anything the content does not need. Rams' first principle — "good design is innovative" — is often quoted in defense of additive moves; the tenth is the principle that disciplines the first.

Concrete moves this pillar makes you do:

- Default every surface to flat. Reserve elevation for genuinely modal surfaces — drawer, sheet, dialog — per PRD 06.
- Use one saturated accent. The product has a single accent for primary action and focus; introducing a second saturated hue is a principle change, not a styling choice.
- Hide chrome until interaction asks for it. Header float buttons, FAB, and composer affordances are present but quiet; they do not advertise themselves while the user is reading.
- Prefer typographic hierarchy over rule lines, badges, and chips. If weight, size, and spacing can carry the structure, do not add a border.
- Treat new components as a cost. Before adding one, check whether an existing pattern can carry the weight. PRD 06 owns the inventory; this principle owns the bar for entry.
- Refuse "polish" that only the designer can see. If a flourish requires a hover state at a specific zoom level to notice, it is decoration, not craft.
- Make icon-only controls accessible by name, not by decoration. Every control earns its place in the chrome by being labeled and useful, not by being illustrated.

Exemplar: iA Writer earns its beauty entirely from type, measure, and rhythm. There is no decorative shell, no accent surface, no second color — and the writing surface is the most readable in its category precisely because of what is missing. The product makes the case that deference can be the entire design language without the result feeling unfinished.

## Peacefulness

Peacefulness in a chat product cannot mean stillness. The surface streams tokens, surfaces tool calls, reasons aloud; it is in motion by design. Peace here is *choreographed restraint*: nothing pulses, shimmers, or moves in the periphery; motion has a single steady cadence; surfaces collapse to stillness the moment a unit of work completes. The user should never feel that the interface is asking for attention.

The distinction is between motion that is necessary (a token streaming in, a reasoning panel expanding, a sheet rising) and motion that is ambient (a logo that bobs, a button that breathes, a gradient that drifts). The first is information; the second is noise. The pillar permits the first and forbids the second. When streaming ends, the streaming affordance ends with it — no decorative tail, no lingering shimmer, no celebratory bounce.

A second distinction is between motion in the foreground and motion in the periphery. A message column that is streaming holds the user's attention; a sidebar that pulses while the column streams steals it. The rule is that the foreground may carry exactly one motion at a time, and the periphery carries none while the foreground is active. Calm is what is left when nothing in the periphery is asking to be looked at.

The lineage is Japanese: *Ma* (間), the charged emptiness between elements that gives each its weight; and *Kanso* (簡素), simplicity reached by elimination rather than by addition (with *Seijaku*, 静寂, active stillness, naming the state a well-designed surface returns to between events). Ma teaches that the space around a message is part of the message; Kanso teaches that calm is not a treatment applied over a busy layout but the result of taking the busy layout apart. Both predate software, but both transfer cleanly to a streaming surface where the most important visual property is the *cadence* of arrival, not the arrival itself.

Concrete moves this pillar makes you do:

- Give streaming one cadence. The shimmer used for "thinking" and the pulse used for the typing indicator are the same family; a second motion grammar for the same semantic event is a violation.
- Resolve to stillness. When a stream completes, the surface becomes flat and quiet within a single frame budget. No lingering effects, no completion confetti, no afterglow.
- Honor `prefers-reduced-motion` as a first-class path, not a fallback. The reduced path is designed at the same time as the default and approved at the same review.
- Keep the periphery quiet. The header, sidebar, and FAB are not allowed to animate while the message column is streaming. Two motions on screen at once are one too many.
- Avoid attention-grabbing affordances on idle surfaces. Empty states, the composer at rest, and the model picker do not animate to attract use.
- Treat status announcements as part of the cadence. The live region (PRD 06 §3.5) announces discrete transitions only; an interface that pulses without announcing is no calmer than one that pulses with a klaxon.
- Refuse celebratory feedback for ordinary success. A response that arrives is its own reward; an animation that congratulates the user for receiving it adds noise without information.

Exemplar: Linear holds an aggressive amount of Ma in its sidebars and command palette, runs every transition on a spring with one steady character, and goes completely still the instant the user stops interacting. The product feels alive without feeling restless.

## Nature

Nature here is *biomorphic surface within systematic structure*. Grid, type scale, component geometry, spacing scale — these are systematic, regular, engineered. Color, light, easing, and shadow — these are biomorphic, soft, drawn from how surfaces look in daylight rather than in a vector editor. The product is not pastoral; it is software that lets warmth into the places where warmth does the most work.

A common failure is to apply "nature" as a theme: warm beige backgrounds, leaf icons, organic blobs. None of that survives contact with a chat surface that has to render code, math, and substitution callouts at WCAG AA contrast. The pillar instead asks: where can the system relax into something that looks grown rather than drawn? The answers are mostly invisible — easing curves that decelerate the way physical objects do, shadows with the soft falloff of diffuse light, glass materials whose tint shifts with what sits underneath them.

A note on warmth in this codebase. The palette is a low-chroma OKLCH neutral with a slightly cool hue (around 250), aligned with Apple HIG's cool-neutral defaults. Warmth in this product does not come from a sepia background; it comes from the spring character of the entrance easing, from the diffusion in the glass material used on header, composer, and FAB, and from the generous Ma in the spacing scale. Calling the current background "warm" would be inaccurate; calling the system as a whole cold would also be inaccurate. The trade-off is explicit and lives in PRD 06. Designers who want to make the product feel "warmer" should reach for motion character, material diffusion, and vertical rhythm before reaching for hue.

This pillar descends from biophilic design — the argument that environments built for humans should retain the patterns humans evolved to read (Browning et al., *14 Patterns of Biophilic Design*) — and from wabi-sabi, which prefers surfaces with the marks of their making to surfaces that pretend to be machine-perfect. The transfer to software is restrained: no asymmetry for its own sake, no hand-drawn affectations, no faux-paper textures. The discipline is to admit organic behavior in the places where it is true (light, motion, material) and refuse it in the places where it is not (grid, type, spacing).

The Apple Liquid Glass material this product uses for chrome is the most concrete expression of the pillar. Glass tints with what sits beneath it, blurs without erasing, and gives the chrome a sense of being in the same room as the content rather than pasted on top of it. It is also a discipline: glass is used for chrome (header float buttons, composer capsule, FAB) and not for message surfaces, which stay flat. The split is what keeps the product from drifting into theming.

Concrete moves this pillar makes you do:

- Use spring-derived easing for entrance and surface motion. Linear curves are reserved for purely indicative animations like progress bars; everything else decelerates the way matter does.
- Prefer diffuse, soft shadows to hard drops. Elevation reads as light, not as a stencil.
- Let the glass material carry warmth. The chrome surfaces (header float, composer capsule, FAB) tint with what sits beneath; message surfaces stay flat and do not borrow this treatment.
- Avoid pure white and pure black as surface colors. The neutrals are OKLCH lightness values pulled inward from the extremes so the eye is not asked to focus against a flat wall.
- Keep iconography geometric and consistent. Nature is not in the icon set; it is in the surface the icons sit on.
- Do not literalize nature. No leaves, no mountains, no water ripples. The pillar is a posture, not a motif.
- Allow subtle context-awareness in chrome tinting. Glass surfaces are permitted to shift with theme, scroll position, and content beneath; message surfaces are not.

Exemplar: Arc combines atmospheric, environment-aware tinting in its workspace surfaces with a rigorously geometric sidebar and grid. The product feels alive at the level of light and material without ever loosening its structural discipline. The lesson is that "organic" can sit on top of "engineered" without contaminating it, as long as the boundary between the two is held.

## High Aesthetics

High aesthetics is *thoroughness, not ornament*. Beauty here is earned through typography, spacing, and motion — the three dimensions where small refinements compound into perceived quality — and never through decoration. A product reads as premium because the optical alignment of an attribution row was checked at every breakpoint, not because someone added a gradient to a button.

The clearest sign that a product has invested in high aesthetics is that the user cannot point at any one thing that explains why it feels premium. A small spacing change in a thread, a slightly looser tracking on the type ramp, a focus ring that fades in rather than snapping — none of these survive being described, but each subtracts a small amount of friction from every interaction, and they compound. Decoration is the opposite shape of investment: it is visible, nameable, and almost always a substitute for the refinement that wasn't done.

This pillar borrows Rams' eighth principle directly: good design is thorough down to the last detail (Rams, "Ten Principles for Good Design"). The translation is that aesthetic investment goes into the places the user cannot consciously name but can always feel — the rhythm of vertical spacing in a long thread, the way an icon's optical weight matches its neighbor at 14px, the precise moment a composer focus ring appears. Rams' sixth principle — good design is honest — keeps the pillar from drifting into faux-craft: a surface that pretends to thoroughness by adding decoration that mimics polish is dishonest in exactly Rams' sense.

A second framing comes from Apple HIG's notion of *depth* as one of the three foundations alongside deference and clarity (Apple HIG, "Foundations"). Depth in this product is small and earned — a sheet rises from below, a popover sits a single elevation step above the surface that opened it — and is used to make hierarchy legible, not to ornament it. Depth is the only HIG foundation that adds something to the screen; the principle here is that what it adds is exactly enough hierarchy and no more.

Concrete moves this pillar makes you do:

- Tune optical alignment, not just metric alignment. Glyphs are aligned by eye to baselines, caps height, and neighbor weight — not only to a pixel grid.
- Treat spacing as the primary aesthetic surface. The spacing scale (PRD 06 §3.3) is where craft lives; bring spacing decisions to review with the same seriousness as color decisions.
- Invest in transitions between states. The composer at rest, focused, generating, and disabled are four designed states with deliberate transitions, not four CSS overrides.
- Refuse the gradient-on-button reflex. If a control needs more presence, change its spacing, weight, or position before reaching for color or decoration.
- Match the optical weight of icons to neighboring text at every breakpoint. Mismatched weight is the most common failure of "premium" interfaces and the cheapest one to fix.
- Verify the dark theme has parity, not a translation. Light and dark are designed together; a dark theme that is a tonal flip of light has not been designed.
- Hold the type ramp to a small number of sizes. Premium feel comes from disciplined reuse of the ramp, not from finding the exact font size for each label.

Exemplar: Bear demonstrates that a product can feel completely finished without a single decorative element. It sells typography as the product — the editor surface is the design, and there is nothing else competing with it. The premium feel is entirely the result of disciplined type, measure, and rhythm; no decoration is doing any work.

## Tensions and Governing Rules

The four pillars genuinely conflict. Naming the tensions is not an admission of weakness — it is how the pillars stay usable in a real design review. Each tension below has a governing rule that resolves it; treat the rule as load-bearing.

### Tension 1: Nature versus Minimalism

Nature pulls toward organic warmth — warm off-whites, soft shadows, atmospheric tints, easing that decelerates like matter. Minimalism pulls toward cold reduction — pure neutrals, flat surfaces, hard edges, no atmosphere at all. Applied without a rule, the two pillars produce either a sterile palette no one wants to sit inside or a cozy palette that loses focus the moment a code block lands in it.

**Rule:** *warmth lives in the palette and motion; reduction lives in the layout.*

**In practice:**

- The neutrals are pulled in from pure white and pure black, easing is spring-derived, shadows are diffuse — but the grid, the spacing scale, and the component geometry are systematic and uncompromising.
- Glass materials carry tint and depth on the chrome (header float, composer, FAB); message surfaces remain flat and disciplined so the reading column never feels styled.

### Tension 2: High Aesthetics versus Minimalism

High aesthetics wants refinement that can be felt; minimalism forbids the easiest forms of "feeling refined" — visible decoration, ornament, polish for its own sake. Designers under deadline reach for the wrong vocabulary first: a gradient, a glow, a sparkle. The rule keeps the budget pointed at the moves that compound.

**Rule:** *aesthetic investment goes into typography, spacing, and motion — never decorative elements.*

**In practice:**

- Time and review attention go into type ramp, vertical rhythm, optical alignment, transition timing, and easing character — the dimensions where refinement is felt but not named.
- Proposals that add decoration (a flourish, a gradient on a surface, a subtle texture) are redirected into a spacing or motion proposal before they enter the system.

### Tension 3: Peacefulness versus AI Chat's Constant Motion

A chat product streams; it cannot be motionless. But the user is reading, and a reading surface that vibrates is hostile. The naive resolution is to slow every animation down; the right resolution is to give all motion one steady character and to make sure the surface returns to true rest the instant a unit of work finishes.

**Rule:** *motion is choreographed, not constant.*

**In practice:**

- Streaming has one cadence — shimmer-on-reasoning and the pre-first-token indicator share the same family of motion; idle surfaces do not animate; the periphery is quiet while the message column streams.
- Surfaces collapse to stillness when a stream completes. No decorative tails, no lingering glows, no celebratory bounce. The `prefers-reduced-motion` path is designed alongside the default, not after it.

### Tension 4: Nature versus Systematic Discipline

Nature wants organic and irregular; HIG and Rams want systematic and disciplined. Letting nature into the grid produces a hand-crafted-looking app that does not scale; refusing nature anywhere produces a CAD drawing. The rule splits the surface so each pillar governs the layer it is good at.

**Rule:** *system governs structure; nature governs surface.*

**In practice:**

- Grid, type scale, spacing scale, radius, and component geometry are systematic and consistent across the product. They are defined once in PRD 06 and not negotiated per surface.
- Color, light, easing, material, and shadow are biomorphic — soft, atmospheric, spring-driven — and are allowed to vary subtly with context (dark vs light, content beneath glass, scroll position) without breaking the structural rules above.

### Tension 5: High Aesthetics versus Deference

A product that is too aesthetically distinctive competes with its own content; a product that is purely deferential never earns the user's loyalty. The pillar of high aesthetics can take the user's breath at first contact without ever competing with the working surface — but only if its budget is constrained to the moments the user is not yet working.

**Rule:** *distinctiveness belongs to empty states, transitions, and the first-run moment — not the working surface.*

**In practice:**

- The empty state, onboarding, and first-message moment are where aesthetic ambition is spent. The reading and composing surface, by contrast, is designed to disappear into use.
- Transitions between major states (entering a thread, opening the command palette, dismissing a sheet) are where motion character is most expressive; mid-thread surfaces stay quiet.

## The Meta-Rule

When in doubt, subtract.

Minimalism is the only pillar in this document achieved by removal. Peacefulness is achieved by *what is not allowed to move*. Nature is achieved by *what is not allowed to flatten into pure white or hard linear motion*. High aesthetics is achieved by *what is not allowed to become decoration*. The meta-rule sits beneath all four because it is the only one that is safe to apply when none of the four offers a clean answer. Add only after the subtraction has been tried and rejected on its merits.
