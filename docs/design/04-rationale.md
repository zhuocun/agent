# Decision Rationale

The record of non-obvious design decisions in force today. Each entry names what was chosen, the alternatives considered, why this choice won, what was given up, and the condition that would warrant revisiting.

This file is not a changelog. Changelogs record what changed and when; this file records *why something is the way it is*, so that a future reviewer or designer can recover the reasoning without having to re-derive it. Pair each entry with the corresponding entries in `03-anti-patterns.md` — most "why not" lives there in its operational form; the longer-form "why" lives here.

References to PRD sections follow the form "PRD 06 §3.1." References to the principles canon follow `00-principles.md`. Token names and CSS variables follow `web/src/app/globals.css`.

## Decision 01: Cool-neutral palette, not warm off-white

**Choice:** A low-chroma OKLCH neutral palette with a slightly cool hue (around 250).

**Alternatives considered:**

- *Warm off-white* — cream, paper, or sepia neutral, hue around 70–90. The most direct lexical translation of the "warmth" brief, and the choice that reading apps (iA Writer, Bear in its paper theme) make. Rejected because chat surfaces must host code blocks, math, substitution callouts, and glass chrome inside the reading column; warm paper degrades contrast on those secondary surfaces in ways the reading-app exemplars do not have to handle.
- *Pure neutral grays (chroma zero)* — the achromatic position. Rejected because zero-chroma neutrals read as flat and clinical; the slight cool tilt costs almost nothing in OKLCH terms and recovers temperature without committing to warm.
- *A warm beige "wabi-sabi" palette* — closer to the Japanese-inspired reader-app aesthetic the principles flirt with. Rejected for the same content-hosting reason as warm off-white, with the additional risk that beige reads as a brand statement on a working-surface product where the surface should not advertise itself.
- *Dual-temperature palette* — cool on the working surface, warm on the welcome state and seams. Rejected as too clever; the temperature shift at the welcome→thread boundary would itself become a designed moment that competes with the actual welcome→thread choreography (Decision 11), and dual-temperature systems are difficult to maintain consistency across over time.

**Why this choice:** The principles call for warmth, but warmth in a chat product is not the same thing as a warm background. A warm-paper surface fights every other content type the renderer must host — code blocks, math, substitution callouts, glass chrome — and degrades AA contrast for the most-read parts of the surface. The cool-neutral choice aligns with Apple HIG's default surface temperature ("Color"), preserves contrast and chroma headroom for the single accent, and keeps the working surface readable when code and substitution callouts land in it. Warmth in this codebase comes from the spring character of motion, the diffusion in the glass material on chrome, and the generous Ma in the spacing scale — not from the background fill. This trade-off is explicit and load-bearing.

**Trade-off accepted:** The codebase reads slightly cooler than a strict "warm wabi-sabi" interpretation of the brief would suggest. The first-look feel is closer to a calm Apple HIG surface than to a paper-and-ink reader.

**Revisit when:** Apple shifts its default cool-neutral baseline (their move would create permission to follow), or a strong content-readability study shows that a low-chroma warm neutral could carry code and math without losing contrast.

## Decision 02: iOS blue as the single accent

**Choice:** A single brand accent — an iOS-system-blue analogue in OKLCH (exact triple in PRD 06 §3.1). No second saturated hue anywhere in the system.

**Alternatives considered:**

- *A nature-coded accent* — terracotta, moss green, ochre, deep indigo. More on-brief at the lexical level for the "warmth" pillar. Rejected because the working surface already carries warmth through motion and material; a warm accent on top of warm chrome cumulates into a temperature the reading column does not need, and competes with the system colors users see in their browser chrome and OS.
- *Two accents* — one warm, one cool (e.g., moss for confirmation, iOS blue for primary action). The "dual palette" pattern. Rejected because two accents on a calm surface always read as two accents competing; the doctrine that there is exactly *one* accent is what allows the focus glow (Decision 07) to remain the single moment of accent illumination without ambiguity.
- *No accent at all* — a fully achromatic system that uses only weight and spacing for emphasis. The most minimal possible position. Rejected because the brand accent does meaningful work on the composer focus state and on primary action — moments where the user needs an unambiguous "this is where the system is asking for your input" signal that weight alone cannot carry.

**Why this choice:** The single-accent doctrine is the load-bearing decision; the *specific hue* is secondary. iOS blue ties the product to the Apple design vocabulary the rest of the system already speaks (HIG-aligned neutrals, glass material on chrome, system font stack, 44px touch targets, safe-area insets). It reads as a calm, recognizable signaling color rather than a brand statement, which is exactly what the working surface needs. A warm "nature" accent would have been more on-brief at the lexical level but would have introduced a second visual character into a palette already carrying warmth through motion and material — and would compete with the system colors users see in their browser chrome and OS. The doctrine that there is only *one* accent matters more than the specific hue: it is what allows the focus glow on the composer (Decision 07) to remain the single moment of accent illumination on the working surface without ambiguity, and what keeps the destructive, warning, success, and info semantic roles legible as *meanings* rather than as ornamental color (see also `03-anti-patterns.md`, Palette section).

**Trade-off accepted:** The accent is less "nature-coded" than a moss or ochre would be. Some reviewers will (correctly) note the system reads as cooler than the four-pillar brief implies. The Nature pillar is carried by motion, material, and Ma — not by accent hue.

**Revisit when:** A second product surface (a marketing site, a published-pages feature) needs a second accent for genuinely separate reasons, *and* that need cannot be served by a chroma-trimmed semantic role. The doctrine itself should not be loosened.

## Decision 03: OKLCH as the color space

**Choice:** All color tokens in `web/src/app/globals.css` are defined in OKLCH.

**Alternatives considered:**

- *HSL* — the historical web default and the space most existing token systems are written in. Rejected because HSL fails perceptual uniformity in obvious ways (a 50% lightness yellow and a 50% lightness blue are radically different in perceived brightness), which makes principled dark mode harder than it should be.
- *Raw hex values* — the original, no abstraction. Rejected because every hex value is a hand-tuned point with no relationship to its neighbors; chroma-trimming a hex by 10% requires re-deriving it. The token system would lose all of its arithmetic discipline.
- *sRGB with manual contrast tuning* — keep the existing color pipeline but ship a per-pair contrast audit. Rejected because contrast tuning then becomes per-token cleanup forever; OKLCH makes it a one-line adjustment per hue identity.
- *LCH (the predecessor to OKLCH)* — almost the same model, slightly worse perceptual uniformity at the extremes. Rejected because OKLCH solves the LCH discontinuities, has near-identical tooling support, and is what the Tailwind v4 / shadcn ecosystem speaks natively.
- *Display-P3 with manual chroma trimming* — embrace wide-gamut early and ship a P3-native palette today. Rejected because the chat surface gets nothing meaningful from P3 (the brand accent and the neutrals all fit well within sRGB), and shipping P3 now would require parallel sRGB fallbacks for every token. OKLCH gives the option to widen later without rewriting the system.

**Why this choice:** OKLCH is perceptually uniform — equal lightness deltas look equal across hues, so reasoning about contrast, the dark-mode mirror, and chroma-trimmed semantic roles can be done arithmetically. HSL fails this in obvious ways (a 50% lightness yellow and a 50% lightness blue are radically different in perceived brightness), which makes principled dark mode harder than it should be. OKLCH also gives the system a single shared knob for chroma — central to the low-chroma discipline this product depends on, since "pull this hue inward by the same amount" is a one-number operation rather than a per-hue tuning exercise. The performance and tooling story is solved (Tailwind v4, modern browsers, the shadcn token system all speak OKLCH natively). Choosing OKLCH now also leaves room for wide-gamut hues later without rewriting the token system. The semantic-role table in PRD 06 §3.1 is built on this discipline: every chat role, trust role, and substitution callout is a low-chroma variant of a fixed hue identity, expressible as a one-line OKLCH adjustment.

**Trade-off accepted:** OKLCH values are less guessable from a glance than hex; designers must use a color tool that speaks the space. The team accepts that cost in exchange for the dark-mode and contrast-reasoning gains.

**Revisit when:** A wide-gamut color delivery target (P3, Rec2020 in product surfaces) requires a more capable space, or browser support regresses (not anticipated).

## Decision 04: System font stack, no custom font

**Choice:** Geist as a non-blocking enhancement, with the OS system font stack as the underlying default. No font is on the critical path; `font-display` semantics prevent any FOIT.

**Alternatives considered:**

- *A branded custom font* — Inter, Söhne, GT America, Recoleta-class display. The standard "premium chat surface" move. Rejected for three compounding reasons: critical-path cost, the Minimalism pillar's deference rule, and the loss of the Dynamic-Type analogue the system stack provides for free.
- *A paid superfamily* with display, text, and mono in one license — the maximally-controlled typographic position. Rejected for the same reasons as a single branded font, plus a permanent license cost and a vendor dependency for a surface that should not need one.
- *Font-preload with FOUT* — accept a flash of unstyled text in exchange for the branded face once it lands. Rejected because FOUT causes a layout shift the renderer contract in PRD 01 §5.4 specifically prohibits, and because the shift lands at first paint, the worst possible moment.
- *A serif on the working surface for "warmth"* — the choice that pushes the system toward iA Writer territory. Rejected because the warmth pillar is carried by motion, material, and Ma, not by serif typography; a serif also costs a custom face (system serifs vary too much across platforms to ship with confidence).
- *A variable font shipped as the system enhancement* — pick one variable face (Inter Variable, Recursive) and lean on axis interpolation to cover the weight range. Rejected because variable fonts still hit the critical path with the same blocking cost as static custom fonts; the optimization is on file size after they arrive, not on whether they should arrive on the critical path at all.

**Why this choice:** Three reasons compound. First, the Minimalism pillar's deference rule (`00-principles.md`) — a custom font on the working surface competes with the content the user came to read; a custom face is the loudest possible typographic signal, and the working surface is where typographic signals should be quiet. Second, performance — a blocking font on the critical path costs LCP, frustrates the perceived-latency metrics in PRD 01 §7 and the per-model TTFT line PRD 05 §"Latency (UX quality)" names, and on mobile-web (the primary surface per PRD 00) costs cellular bandwidth on every cold load. Third, the system stack is the Dynamic-Type analogue named in PRD 06 §3.2: it picks up the user's OS font and accessibility preferences automatically, including reader-friendly substitutions, OS-level font-size preferences, and locale-appropriate fallbacks for CJK and RTL scripts. The aesthetics come from spacing, measure, scale, and motion — the dimensions the High-Aesthetics pillar names as where investment compounds. iA Writer, the exemplar cited in `00-principles.md`, demonstrates this point in production: its beauty is entirely typographic restraint, not font identity.

**Related operational rule (no blocking font swap):** The decision above translates to a hard rule on first paint — the product does not render text behind a font swap. There is no FOIT, because blocking text behind a font request, even briefly, competes with the content the user came to read at the moment of highest attention. FOUT-style swap is a related risk: a font that lands after first paint causes a layout shift the renderer-contract in PRD 01 §5.4 specifically prohibits. The conclusion is that the system stack is not a fallback but the *baseline*, and any custom font is purely additive at non-critical surfaces. The discipline that results — spacing and measure decisions have to work across the system-font variants the user might actually be served (Geist, San Francisco, Segoe UI, Roboto, system-ui) rather than depending on the optical metrics of a single chosen face — is, on net, healthier than tuning against one face.

**Trade-off accepted:** The product has a weaker individual typographic identity than competitors who ship a branded face. A reviewer cannot identify the product by its font alone. The pillars are clear that this is the right exchange.

**Revisit when:** A marketing site or first-run surface needs a display face for a single moment (not for the working surface), and the budget can be confined to that surface. The working-surface decision does not change.

## Decision 05: Lucide as the sole icon family

**Choice:** Lucide icons exclusively across the product surface.

**Alternatives considered:**

- *SF Symbols* — the most consistent visual match for the rest of the Apple-vocabulary system the product already leans on. Rejected because the license restricts use to Apple platforms; the product is web-first, so SF Symbols is not portable.
- *Phosphor* — broad coverage, multi-weight, well-maintained. Rejected because its character is slightly playful; the strokes are heavier and the corners softer than what the High-Aesthetics pillar wants at body text size.
- *Heroicons* — paired tightly with Tailwind, narrower coverage. Rejected because the coverage gap would force the product to introduce a second family for surfaces Heroicons does not cover, which is itself an anti-pattern.
- *A custom-drawn set* — the maximum-identity position. Rejected because it would create a permanent maintenance line item the team cannot justify against the deference principle; identity belongs in spacing, motion, and material, not in glyphs.
- *Mix Lucide with one bespoke addition for the product mark* — the "ninety-percent rule" position. Rejected because mixing even one custom glyph with the Lucide grid produces an optical inconsistency at body text size that the High-Aesthetics pillar specifically rules out; the product mark belongs in the welcome state and marketing surfaces, where it is not adjacent to Lucide.

**Why this choice:** Lucide is open-source, has consistent stroke weight tuned to glyph-like behavior next to text, covers the breadth the product needs without bespoke additions, and is actively maintained. The pillar of High Aesthetics specifically calls out optical-weight match between icons and neighboring text at every breakpoint — Lucide's stroke is tuned for exactly that. SF Symbols would have been the most consistent visual match with the rest of the Apple-vocabulary system, but the license restricts use to Apple platforms; the product is web-first, so SF Symbols is not portable. A custom set would have produced a stronger identity but would have created a permanent maintenance line item that the team cannot justify against the deference principle.

**Trade-off accepted:** Less unique identity at the icon level than a custom set. Identical icons appear across many products in the same neighborhood (Linear, Vercel-adjacent tooling). This is acceptable; identity lives in spacing, motion, and material, not in glyphs.

**Revisit when:** A specific affordance has no acceptable Lucide glyph *and* the affordance is high-traffic; the path is to add the glyph upstream, not to introduce a second family.

## Decision 06: Glass material on chrome only, not on message surfaces

**Choice:** Glass material (backdrop blur, specular highlight, ambient + key shadow stack) is reserved for chrome: the header float, the composer capsule, the FAB, and modal-class surfaces (drawer, sheet, popover). Message surfaces are flat and opaque.

**Alternatives considered:**

- *Glass on the assistant message body* — the "translucent bubble" pattern some premium-positioned chat products use to signal richness. Rejected because the message body is the most-read surface in the product; making it sample the background visually shifts the content with scroll position, which is the exact opposite of reading calm.
- *Glass on the entire thread background* — atmospheric blur behind the message column. Rejected because it competes with the code blocks, math, and substitution callouts the renderer must host inside the column; backdrops that sample reduce contrast on dense content.
- *Flat chrome and flat content* — no glass anywhere; everything opaque. Rejected because flat chrome loses the layered language entirely; without material vocabulary, drawers and sheets read as "more thread," not as floating-above-thread. The user loses the spatial model.
- *Glass only on transient surfaces* (popovers, command palette) and opaque persistent chrome — a middle position. Rejected because the floating header and composer capsule are conceptually layered too; the inconsistency between transient and persistent floating surfaces would be visible at a glance.
- *Specular-highlight glass with no backdrop blur* — a "frosted card" pattern that uses the highlight + shadow stack from glass but skips the blur. Rejected because without the blur sampling, the material reads as a plain elevated surface; the layered character collapses, and the team would have shipped a separate material vocabulary in exchange for nothing.

**Why this choice:** Messages are the content. Content is flat — that is what allows the reading column to stay calm and the type to lead. Glass is the material vocabulary of *layered* surfaces — chrome that sits over content. Putting glass on the message body would make the most-read part of the interface visually shift with the background that sits behind it (its blur sampling changes with scroll position), which is the exact opposite of reading calm. The Minimalism pillar's deference rule and the Nature pillar's "glass material carries warmth on the chrome" rule both arrive at the same place. Apple's own Liquid Glass guidance treats glass as a chrome material, not a content material (Apple HIG, "Materials"). The practical implication is that warmth on this product comes from chrome the user is *aware* of as chrome (the floating header, the composer capsule that sits over the thread, the FAB that floats over the message list) — surfaces whose layered character is part of their job — rather than from content surfaces that should not advertise themselves as treated.

**Trade-off accepted:** Some of the visual richness reviewers might expect on a "premium chat" surface (translucent bubbles, atmospheric tinting on messages) is forgone. The Nature pillar is carried by the chrome material and by motion, not by message-surface treatment.

**Revisit when:** Apple's HIG itself moves glass into content surfaces (not anticipated), or a specific message-class (a special announcement, a transient toast inside the thread) needs to read as layered. The default stays flat-on-content.

## Decision 07: Composer focus glow as the single accent illumination

**Choice:** The composer focus glow — brand-edge plus soft outward halo, on the transition budget PRD 06 §3.4 names — is the only persistent accent illumination on the working surface. The send button does not carry the brand color at rest.

**Alternatives considered:**

- *A persistently brand-colored Send button* — the most conventional choice; signals "this is the primary action" by paint. Rejected because it burns the single moment of accent illumination from a fixed position and shouts at the user even while they are reading earlier in the thread.
- *A brand-tinted thread background* — saturate the working surface slightly toward the accent hue. Rejected because the working surface must stay calm; a tinted background is the most pervasive possible brand statement, and it cannot be ignored.
- *A brand-edge on every assistant message* — a thin accent border or left-edge bar on each assistant turn. Rejected because it competes with the flat-message-surface doctrine (Decision 15) and because per-message accent illumination is exactly the multi-accent failure the single-accent doctrine rules out.
- *No accent illumination at all* — fully achromatic; let weight and spacing carry every cue. Rejected because the composer focus state genuinely benefits from an unambiguous "the system knows you have the composer" signal that weight alone cannot deliver.
- *Accent illumination distributed across discrete events* — focus glow on the composer, a small brand pulse when streaming starts, a brand tick when a message is copied. Rejected because distributed illumination is multi-accent in time rather than space; the user experiences the brand color as ambient feedback, which dilutes its signaling power at the moment that matters (composing).

**Why this choice:** The working surface stays calm; the brand only lights up at the moment of engagement. A persistently brand-tinted Send button would burn the single moment of accent illumination the working surface is allowed, and would visually shout from a fixed position even when the user is reading. A focus glow on engagement reads as feedback ("you have the composer; the system knows") and disappears the moment focus leaves — which is exactly the choreographed-restraint character the Peacefulness pillar describes. It also concentrates the accent's signaling power into the moment the user is committing to send, where it does the most work.

**Trade-off accepted:** The Send button is visually quiet at rest, which can read as less "actionable" to first-time users. The empty state's prompt cards do the work of inviting first input; the composer itself does not need to advertise.

**Revisit when:** The first-week activation funnel PRD 05 §"Activation" / §"First-week activation" instruments shows the quiet composer measurably suppresses first-send rate, *and* the welcome-state choreography (Decision 11) cannot recover it.

## Decision 08: Spring-derived entrance easing as default

**Choice:** The spring-derived entrance curve named in PRD 06 §3.4 — a damped-harmonic, fast-rising, slow-settling shape — is the default for entrance and surface-state motion across the product.

**Alternatives considered:**

- *Linear* — rejected on first principles: nothing in the natural world moves at constant velocity from rest to rest, so linear motion in software always reads as machine-driven rather than physical. Reserved for genuinely indicative animations (a determinate progress bar).
- *Standard CSS `ease-out`* — the platform default. Closer to physical than linear, but its character is generic; the curve does not commit to a temperament. Rejected because the Nature pillar's "warmth from motion" rule needs a curve that *is* something, not a hedged-default shape.
- *Material's "standard" curve* — a well-tuned, broadly-tested cubic-bezier from a different design system. Rejected because its character is engineered-feeling, appropriate for Material's broader system and less so for one that wants warmth specifically from motion.
- *A true spring physics implementation via Web Animations* — full damped-harmonic motion with stiffness, mass, and damping parameters. Gives finer control and is closer to "actual" physics. Rejected because it introduces a runtime cost and a JS dependency on a surface that should be CSS-only; the cubic-bezier approximation is close enough that no reviewer in practice can tell the difference, and the simpler implementation is more durable across browser engines.

**Why this choice:** Damped-harmonic motion is the Nature pillar's clearest translation into pixels — the curve mirrors how a physical object decelerates against friction or settles against a stop. The named curve is tuned to be perceptible without being slow (entrance lands within the perceptual budget PRD 06 §3.4 names), and its character is consistent across browsers without needing a JS physics engine. Material's curve was considered and rejected because its character is engineered-feeling — appropriate for Material's broader system, less so for one that wants warmth from motion. A real spring implementation would have given finer control but introduces a runtime cost and a JS dependency on a CSS-only surface; the cubic-bezier approximation is close enough that no one in review can tell the difference. Linear was rejected on first principles: nothing in the natural world moves at constant velocity from rest to rest, so linear motion in software always reads as machine-driven rather than physical.

**Trade-off accepted:** The same curve is used across many entrance moments, which means the product's motion character is recognizable rather than per-surface tuned. This is treated as a feature: a steady cadence is the Peacefulness pillar's whole point.

**Revisit when:** A surface-class (a celebratory moment, a destructive confirmation) genuinely needs a different motion character, in which case it gets its own named curve — not a per-component override.

## Decision 09: Reasoning panel collapses to "Thought for Xs"

**Choice:** Once reasoning completes, the panel collapses to a single line: "Thought for Xs," with a chevron to expand. The panel is hidden entirely when no reasoning is emitted.

**Alternatives considered:**

- *Inline interleaved reasoning* — render reasoning in the same stream as the answer, distinguished only by italic or muted color. ChatGPT briefly shipped a variant of this for `o1-preview` and several smaller chat clients have copied it. The pattern is the cheapest to implement and the worst to read: the user cannot tell where the reasoning ends and the answer begins without parsing the typography mid-stream, and copy/paste loses the distinction entirely.
- *Expanded-by-default panel* — keep the panel expanded once reasoning starts, leave it expanded after, and let the user collapse manually. This is the choice that prioritizes power users over first-time readers, and it is in tension with the load-bearing observation that the *answer* is the main task. On long-answer turns the expanded reasoning column visibly pushes the answer below the fold on mobile-web.
- *Two-column thinking trace* — render reasoning in a side panel parallel to the answer (the pattern some research UIs and agentic coding tools use). This works on a desktop research surface; it does not work on a mobile-web-primary product (PRD 00), where there is no second column.
- *Count or duration without expansion* — show "Thought for Xs" with no chevron, no body. The most opaque option that still nods at transparency. Rejected because it satisfies the letter of the PRD 07 contract but not the spirit; "show me what the model did" requires that the doing be inspectable, not just summarized.
- *Ephemeral thought* — show reasoning live while streaming, then hide it entirely once the answer lands (no chevron, no recall). Rejected for the same reason as count-only: it surfaces reasoning only at the moment the user is busy reading the answer, then removes the audit trail.
- *User-controlled per-thread default* — let the user set a preference (collapsed, expanded, hidden) and apply it per thread. Rejected because the right default is the product's job, not the user's; preferences are a fallback for when the default is wrong, and the per-thread option here just adds settings without changing the basic question of what the surface should do for a first-time reader.

**Why this choice:** Reasoning is interesting to power users, useful for debugging, and load-bearing for the trust contract (PRD 07's promise that the user can see what the model did). But reading reasoning is not the main task — the answer is. Always-expanded reasoning competes with the answer for the user's attention, particularly on long answers; hiding reasoning entirely violates the transparency contract. Progressive disclosure resolves both: the collapsed line is small enough to live above the answer without dominating, the duration anchor ("Thought for Xs") gives the user a sense of effort, and the chevron makes the full reasoning a single click away. The pattern matches the broader pillar of deference: the surface defers to the content (the answer), while the trust surface (the reasoning) remains a peer rather than a primary.

**Trade-off accepted:** Users who would benefit from seeing reasoning by default — debugging, prompt iteration — must click. The keyboard shortcut and the persistent-expand setting (under user preferences) recover most of the gap.

**Revisit when:** Reasoning models become the default rather than the exception, and users routinely want reasoning visible without an extra click. The default could shift to expanded-while-streaming, collapsed-after-completion.

## Decision 10: Mobile composer at the thumb zone with sticky Stop

**Choice:** On mobile-web, the composer sits at the bottom of the viewport (within the safe-area inset), Stop replaces Send in the same slot during streaming, and Stop is sticky — always reachable even while the user scrolls the thread.

**Alternatives considered:**

- *Top-placed composer* — some 2026 chat clients tried this for a "mail-like" feel, treating the composer as the subject-line input and the thread as the inbox. Reading-from-top is a desktop ergonomic; on mobile it forces the user to reach over the entire screen on every send, which is not what users do in iMessage, WhatsApp, Slack, or any established touch chat surface.
- *Hidden Stop under an overflow menu* — saves a slot in the composer row but breaks the trust contract: if the user is reading earlier in the thread when an answer goes off the rails, they must reveal the overflow menu just to abort. The cost lands at the exact moment the user is most stressed.
- *Stop only at the location of the streaming message* — Stop floats next to the assistant message currently streaming, not in the composer. Sounds locally cleaner, but breaks down on long answers: the streaming message scrolls past the viewport while still streaming, and Stop scrolls with it. The user loses the abort affordance and has to scroll back to find it.
- *Send-and-Stop as two separate buttons in the composer* — render Send and Stop side by side at all times, with whichever is inactive disabled. Doubles the composer's footprint on the smallest viewport for no real benefit; the same-slot toggle is unambiguous because exactly one is meaningful at any moment.
- *Composer minimized to a floating pill, expand-on-focus* — the "WhatsApp record-affordance" pattern that collapses the composer to a small action button until the user taps it. Rejected because the composer is the product's primary surface in many sessions; collapsing it costs the at-a-glance affordance and adds a tap to every fresh thread.

**Why this choice:** PRD 00 §1 names mobile-web as the primary surface. Thumb-zone biomechanics put the composer at the bottom-right — top-placed composers require reaching over the entire screen on every send, which is hostile and not what users do in iMessage, WhatsApp, or any other established touch chat surface. Stop must remain reachable because trust requires that the user can always abort: if the user is reading earlier in the thread when an answer goes off the rails, hiding Stop under an overflow forces them to scroll back just to abort — wasted seconds where their bill is racking up and their trust is eroding.

**Trade-off accepted:** A persistently visible composer eats vertical space that could be reading room. Safe-area-inset awareness keeps the composer from sitting on top of the iOS home indicator but does not recover the space cost. The exchange is the right one for a chat product.

**Revisit when:** The product stops being mobile-web-primary (not on the roadmap), or a new mobile interaction pattern produces measurably better outcomes than thumb-zone composer + sticky Stop.

## Decision 11: Welcome state owns the personality

**Choice:** The first-run / empty-state surface is where aesthetic ambition is spent — atmospheric tinting, expressive typography, hero spacing. The working thread is calm and generic by design.

**Alternatives considered:**

- *Persistent brand chrome on the thread* — logo in header, brand-colored Send button, themed accent on every assistant message. Spends the personality budget on the surface the user lives in. Forces them to read past brand on every turn, which is the exact failure the Minimalism pillar's deference rule names.
- *Equally minimal welcome state* — no atmospheric treatment anywhere, with the empty state as bare as the thread. Wastes the one moment in the entire product where distinctiveness costs the user nothing (because no content is being deferred to). The welcome state then has no job; it is just empty space waiting to be filled.
- *Separate "themed" mode the user can opt into* — let the user toggle between a calm and an expressive variant. Rejected because it forces every design decision to be designed twice (Decision 13's reasoning applied at theme-scale), and because the meaningful design choice is not "should this exist for some users" but "where in the user's journey does distinctiveness belong."
- *Personality distributed across the working surface in low doses* — a subtle gradient on the header, a tinted glow on the FAB, a brand-colored progress dot during streaming. The "ambient brand" pattern. Rejected because low-dose brand still reads as ornament on the reading column, and ornament on the reading column is what the High-Aesthetics pillar specifically rules out.
- *Personality concentrated in the empty state only, with no transition* — fully calm thread, atmospheric empty state, and a hard cut between the two. Rejected because the transition between welcome and thread is itself a moment the user experiences; a hard cut makes the empty state feel like a separate page rather than the same product introducing itself. The choreographed transition (`02-patterns.md`) is what makes the seam work.

**Why this choice:** The fifth tension in `00-principles.md` is the explicit ruling: distinctiveness belongs to the seams (empty state, transitions, first-run) and not to the working surface. The user lives in the working surface; the welcome state is what they see once. Spending the personality budget on the working surface forces the user to read past it on every turn for the life of the product. Spending it on the seam means the user gets the product's character on contact, then gets out of their way the moment they start working. This also gives the welcome state a real job — it is not just an empty space waiting to be filled, it is the moment the product *introduces itself* — which is the only thing it ever needs to do.

**Trade-off accepted:** The thread is visually understated enough that a screenshot in isolation does not communicate the product's character. Marketing and onboarding screenshots therefore need to come from the welcome state, not from mid-thread.

**Revisit when:** A persistent surface (a sidebar, a settings header) needs to carry distinctiveness for a real reason that the empty state cannot. The working thread itself does not change.

## Decision 12: Transparency surfaces are first-class

**Choice:** Model attribution, cost, substitution callouts, BYOK indicators, and the usage meter are first-class UI elements rendered on every assistant message — not hover-revealed, not collapsed behind a "details" panel.

**Alternatives considered:**

- *Hover-revealed cost and model* — the incumbent default in most chat products. The user has to know to hover; the information is not transparent if it is conditionally revealed by interaction. On touch surfaces (the primary surface per PRD 00) it is functionally hidden.
- *Substitution shown only in the error log* — treat substitution as a developer-facing concern. Rejected because substitution is a user-facing transparency event (PRD 07 §5–§6); the served model is part of the answer, not part of the debugger output.
- *Cost behind a separate "billing" surface* — keep the thread clean by moving cost figures to a settings or billing pane. Reasonable for a product where cost is monthly-flat; wrong for a product where cost is per-message and the user is sensitive to which model just answered.
- *Trust chrome only in settings* — surface attribution and cost in a dedicated "details" view the user opens on demand. Same failure as hover-reveal at one layer of indirection.
- *Always-on attribution but no cost* — show the served model on every message but elide the cost. Cleaner-looking; partially defeats the wedge. PRD 05's monetization story rests on the user seeing what the model cost; hiding it weakens the per-message accountability that makes the BYOK and metered-tier story coherent.
- *Toggleable attribution row* — let the user dismiss the model/cost row on a per-thread basis. Rejected because dismissal is a form of hiding, and the user who dismisses is the user who most needs the reminder; once dismissed, the surface no longer earns the trust it claimed.

**Why this choice:** PRD 07's whole product promise is that the user *sees* what model answered, what it cost, and when a substitution happened. Hover-revealed transparency is not transparency; it is plausible deniability — the user has to know to look. The doctrine here is that the trust surface is part of the product, not a debug view layered over it (`00-principles.md` calls this out, and PRD 06 §1 names "transparency is product chrome"). The visual cost of always-on attribution is paid by spacing and typographic restraint — model badges are small, monospaced for numerals, in muted-foreground tones — so the surface does not shout while still being immediately readable. Substitution callouts use a dedicated color role (`--color-substitution-callout`), specifically *not* the destructive role, because substitution is a transparency event rather than a failure (PRD 07 §5–§6). The discipline that all of this requires — that no surface invent its own attribution treatment — is what keeps the trust chrome consistent across the in-app thread, copy-as-markdown, and the GDPR export, while the public share view legitimately hides cost (PRD 07 §6.4).

**Trade-off accepted:** Mid-thread density is higher than on competitors who hide attribution. Some users will find this busier than they would prefer. The fix is *better typography and spacing on the attribution row*, not hiding it.

**Revisit when:** Usage telemetry shows the attribution row is genuinely unread (low expand rate combined with low gaze-time signals); even then, the answer is probably better default-collapsed details, not hidden attribution.

## Decision 13: `prefers-reduced-motion` as a principle, not a checklist

**Choice:** The reduced-motion path is designed at the same time as the default motion path, reviewed at the same review, and treated as a peer surface — not as an end-of-release accessibility audit.

**Alternatives considered:**

- *QA-stage backfill* — address reduced-motion in a dedicated accessibility audit before each release. This is how most teams in practice handle it. The cost is invisible until shipping pressure compresses the audit window, at which point reduced-motion is the first thing cut; the discipline never sticks across releases.
- *Outsource to library default* — rely on whatever Framer Motion, Radix, Tailwind, or another dependency ships for reduced-motion behavior and call it covered. The trap is that each library's default is tuned for *its* component vocabulary, not for *this* product's choreography. The library knows nothing about the streaming surface, the reasoning collapse, or the welcome→thread seam — and silently doing-nothing is worse than designing the reduced path.
- *Blanket disable override* — ship a single global rule that zeroes all transition durations under the reduced-motion media query. Technically passes the media-query check; loses meaningful state-change semantics in the process (the user can no longer tell that a sheet opened, only that something changed). Conflates "less motion" with "no motion," which Apple HIG and WAI both warn against.
- *Ignore entirely* — the implicit pattern in most chat products today, including some that otherwise position themselves as accessibility-forward. Worth naming because it is the realistic default this decision is being made against.
- *Reduced-motion as a user-controlled product toggle* — surface a "calm mode" preference inside the app rather than reading the OS setting. Rejected because the user has already told their OS what they want; surfacing a duplicate in-app toggle either ignores the OS setting (worse than respecting it) or shadows it (confusing). The OS preference is the right contract.

**Why this choice:** Honoring system motion preferences is a Peacefulness-pillar move (the user has told their OS they want less motion; the product respects that without ceremony), an Apple-HIG-aligned move (HIG treats Reduce Motion as a first-class setting), and free — it costs nothing at design time *if* the reduced path is designed alongside the default; it becomes expensive only when retrofitted. The discipline is therefore to design both at once, not to backfill the reduced path under a deadline. PRD 06 §3.4 makes this concrete (shimmer degrades to static "Generating..."); PRD 06 §7 makes it a release-blocking acceptance criterion.

**Trade-off accepted:** Every new motion proposal carries an explicit second design (the reduced path). This is treated as a feature, not as overhead — proposals that cannot articulate a reduced path probably should not ship.

**Revisit when:** Not anticipated. The principle is durable; the implementation tokens for "what reduced means in this surface" continue to evolve, but the principle that they are designed in pairs does not.

## Decision 14: Streaming announcements via a separate polite live region

**Choice:** Generation status ("Generating", "Response ready", "Stopped") is announced through a single, separate `aria-live="polite"` status region. The streamed message body itself is *not* wrapped in a live region; it is navigable but not auto-announced.

**Alternatives considered:**

- *Wrap the message body in `aria-live="polite"`* — the most common mistake. Causes screen readers to re-read partial tokens as the stream lands; functionally hostile in long answers and a documented anti-pattern.
- *Use `aria-live="assertive"` for completion* — interrupts whatever the user is currently reading or hearing, which is the wrong contract for a "your answer is ready" event. Assertive is reserved for genuinely interrupting events (an error, an irreversible warning).
- *Announce nothing at all* — the inverse failure. The message appears, but a screen-reader user gets no signal that streaming began or ended. Silently a release-blocking gap.
- *Per-message live regions* — give each assistant message its own live region. Creates a cacophony in long threads as the screen reader queues announcements from every region, and the queue order is undefined across implementations.
- *Use a `role="status"` element instead of `aria-live`* — semantically close, but `role="status"` implies the region exists for status only, while the streaming surface needs to handle "Generating", "Response ready", and "Stopped" in the same region. The explicit `aria-live="polite"` on a generic container is clearer.
- *Announce only completion, not start* — fire "Response ready" once but skip the "Generating" announcement at stream start. Rejected because the start announcement gives the user something to wait for; without it, the silence before the first announcement is ambiguous (did the request go through? did the network drop?). The cadence needs both ends.

**Why this choice:** Wrapping the streamed body in a live region causes NVDA and JAWS to re-read partial tokens as they arrive — a documented anti-pattern (PRD 06 §3.5, PRD 01 §5.7) that is genuinely hostile to screen-reader users. The opposite failure — wrapping nothing — is what several major chat clients shipped at one point, where the message simply *appeared* without any announcement at all. The Peacefulness pillar's rule that status is part of the cadence resolves both: a separate, polite, discrete-transition-only region carries the announcement, and the body stays readable on demand. The completion announcement ("Response ready") is the success-path acceptance criterion in PRD 08 §9 and is the single most important moment in the whole streaming choreography — without it, a screen-reader user has no signal that the answer is done.

**Trade-off accepted:** The status region is a small piece of permanent DOM that has to be coordinated by whoever owns the streaming state machine. The coordination cost is real but small, and it is the only way to make the screen-reader path match the visual path.

**Revisit when:** Screen reader behavior around live regions materially changes (not anticipated; the live-region semantics in WAI-ARIA are stable and the major screen readers' handling of them is settled), or the streaming surface grows additional discrete states that need announcement.

## Decision 15: Flat message surfaces with elevation reserved for modal-class chrome

**Choice:** Message bubbles — user and assistant — render as flat typographic surfaces with no border, no shadow, no card frame. Elevation is reserved for the surfaces that conceptually float above the thread: drawer, sheet, dialog, command palette, popover, FAB.

**Alternatives considered:**

- *Bubble cards with soft drop shadow on every assistant message* — the most common chat-product treatment, used by ChatGPT, Claude.ai, Gemini, and most descendants. Rejected because it spends the elevation language on the highest-frequency surface in the product, which leaves nothing left for the surfaces (drawer, sheet, dialog) that actually need to read as floating.
- *Asymmetric framing* — a single subtle hairline border on assistant messages only, with user messages remaining flat. Rejected for two reasons: the asymmetry implies a hierarchy the conversation does not have (the user is not a second-class participant), and a single hairline still frames the content the user is trying to read past — frames optical noise around the most-read surface in the product, even if it is the lightest possible frame.
- *State-dependent elevation* — elevated assistant messages while streaming, flat after. Tries to use elevation as a "live" signal. Rejected because the elevation change at stream completion is a layout shift the renderer contract in PRD 01 §5.4 rules out, and because the "is streaming" state already has clearer signals (the separate live region, the shimmer affordance, the Stop replacing Send).
- *Card-on-hover* — flat by default, raised on hover. Rejected because hover is desktop-only and the product is mobile-web-primary (PRD 00); building a state-elevation pattern for half the user base is incoherent.
- *Inverted framing* — make user messages elevated and assistant messages flat (rare, but tried by a few "assistant-as-document" products that treat the assistant's output as the canvas and the user's prompts as edits on top). Rejected because it reads as a chat-versus-canvas hybrid that this product is not; threads here are dialogues, not edited documents.
- *Flat surfaces with role color tint* — assistant messages on the muted-foreground surface, user messages on a slightly cooler neutral, both flat. The "two-tone" pattern. Rejected because the role distinction is already carried by alignment and avatar; adding a second signal (surface color) over the same axis is redundant and spends chroma the cool-neutral palette intentionally holds back.
- *Background tint on alternating turns* — give assistant messages a slightly cooler surface and user messages a slightly warmer one (or vice versa), without borders. The "alternating-row" pattern from tables. Rejected because it still spends a chroma signal on every turn, just diffused into the surface; it also fights the cool-neutral palette doctrine (Decision 01).

**Why this choice:** Elevation is a finite vocabulary. Spending it on the most-frequent surface (every assistant message) burns the language for the surfaces that actually need it (a sheet rising from below, a dialog asking for confirmation). It also makes the reading column visually busier on every turn — borders and shadows are chrome the user has to filter past to get to the content. The Minimalism pillar's deference rule and the High-Aesthetics pillar's "typography and spacing carry hierarchy" rule arrive at the same place: differentiation between user and assistant messages comes from alignment (end vs start) and spacing, not from frames. PRD 06 §3.3 codifies this; this entry is the why.

**Trade-off accepted:** Reviewers used to the bubble-card pattern can mistake the flat treatment for incomplete styling. Once the spacing and motion are tuned, the absence of frames reads as deliberate calm rather than missing chrome.

**Revisit when:** A genuinely new message class (a system announcement, an artifact preview, an inline interactive block) needs to read as a layered surface within the thread — in which case that surface gets its own elevation treatment without changing the default.
