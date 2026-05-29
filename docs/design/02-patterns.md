# Patterns

This document collects the recurring patterns that come from applying the principles in `00-principles.md` and the foundations in `01-foundations.md` to actual product surfaces. Each pattern is named, scoped, and illustrated with the concrete sites in the product where it already shows up. The intent is operational: a designer or engineer reading this should be able to make correct choices for a new component without first reading the design-system PRD. Component values, tokens, and acceptance criteria still live in PRD 06; this file owns the *patterns of application* above that layer.

The sections group related patterns. Surface hierarchy (A) governs how chrome and content arrange themselves on screen. Motion and disclosure (B) governs how things change and reveal. The working surface (C) is the moment-to-moment chat experience: focus, empty, transparency. Mobile (D) is treated as the primary form factor, not a downscaled version of desktop. Parallel surfaces (E) treats keyboard, screen-reader, and reduced-motion rendering as renderings of the same UI, not bolt-on accommodations.

---

## A. Surface hierarchy

The first decision for any new surface is where it sits in the visual stack. The three patterns below answer that question end-to-end: which surfaces should *recede*, which surfaces are allowed to *lift*, and where the single saturated accent is permitted to appear.

### Pattern: Deference of chrome

Chrome — the persistent UI scaffolding that surrounds content — defers to the conversation. Apple's "content is the interface" (Apple HIG, "Designing for visionOS" / "Materials") is the canonical lineage; here it manifests as chrome that is glass-tinted, low-contrast, and willing to disappear when it has nothing to say. The conversation thread itself is the figure; the header, the composer rim, and the FAB are the ground.

Three behaviors fall out of this. Transient controls (overflow menus on a conversation row, message-footer actions on an assistant turn) fade in only on hover or focus on pointer devices, and are always-visible on touch. Sticky header and composer use translucent glass over a gradient strip, not hard borders — the boundary is implied by depth, not drawn. The jump-to-latest FAB appears only when the user has scrolled away from the live end of the conversation, and dismisses itself as soon as it is no longer needed.

There is a second-order consequence worth naming. Because chrome defers, the conversation can be read end-to-end as a continuous column of text, and the visual rhythm of the page does not have to negotiate with a competing rhythm imposed by the chrome. This is why the header does not paint a bar, why the sidebar does not own a saturated background, and why the composer capsule sits inside the content column rather than under it. Every time a new piece of chrome is proposed, the question to ask is "is this asking to be looked at, or asking to be available?" Chrome may be available; it must not ask to be looked at.

- App header float buttons use `glass-regular` material and sit on top of scrolling content rather than over a painted bar.
- Conversation-row controls (rename, delete) are hidden until hover on desktop and visible on touch.
- The jump-to-latest FAB is rendered as a glass capsule and is only mounted while the user is off-bottom during streaming.
- Sticky header and composer use a gradient mask at their content-facing edge instead of a hairline border, so the boundary reads as depth, not as a drawn line.

### Pattern: Flat content, layered chrome

Message surfaces are flat. There is no border on a user or assistant bubble, no shadow, no card-like elevation. The assistant turn has at most a tinted-background panel for reasoning. This is the second half of the deference rule: the conversation is allowed to behave like text on paper, because the chrome around it is doing the work of containment.

Elevation is reserved for surfaces that are doing something modal-like: appearing over content, sliding in, or temporarily intercepting input. These surfaces earn shadow and blur because they need to register as "above" the working content; messages do not. Treat the list below as exhaustive — if a proposed surface is not in it and is asking for elevation, that is a signal the proposal is wrong, not a signal the list is wrong.

- Drawer (sidebar on mobile breakpoint, settings drawer).
- Sheet (bottom sheets on mobile; side sheets on tablet).
- Modal dialog (shortcuts dialog, destructive confirms, settings dialog).
- Tooltip and popover (link previews, citation popovers, model-tier hints).
- Transient FAB (jump-to-latest), which uses glass material and reads as floating only while present.

Anywhere else — message bubble, attribution row, reasoning panel collapsed or expanded, in-flow code block — stays flat. A flat message that needs internal distinction uses a faint background tint, not a shadow. A code block, similarly, distinguishes itself from prose by a low-contrast background fill and a fine-tuned monospace stack, not by a card frame around it. The rule is to use the cheapest visual treatment that produces the distinction, and to reserve depth for the surfaces that actually need to register as "above."

The "layered chrome" half of the rule has its own constraint: chrome elevation is *quiet* elevation. The glass shadow stack on the composer capsule and the header float buttons is intentionally low-key — an ambient shadow paired with a small key shadow and a highlight inset — not a dramatic drop. The point of elevation on chrome is to let it sit cleanly over content, not to perform "I am elevated." The drama is saved for true modal surfaces (sheet, dialog), where elevation is the user's cue that input has changed scope.

### Pattern: Single accent doctrine

There is exactly one saturated hue in the product: a single iOS-derived blue (value in PRD 06 §3.1). It has exactly one purpose — signaling primary action and brand activation. It appears on the send button, on the composer focus glow (brand-edge plus halo), on focus rings, and on the accent stripe of the active conversation row. It does not appear anywhere else. A second saturated hue is never introduced; a second saturated *usage* of the existing accent (decorative tinting, hover backgrounds, banner stripes) is also forbidden.

Semantic colors — destructive red, success green, warning amber, info — exist and are tokenized, but they are not "accents" in the same sense and do not violate the single-accent rule. They appear only inside their semantic context: destructive red only on a destructive confirm or a destructive icon (delete chat); success green only inside a positive-outcome toast or a "saved" inline state; warning amber only inside an approaching-limit meter or quota banner. They never colorize chrome, never tint backgrounds outside their context, and never compete with the accent in a default state. The rule is: the accent is the only color allowed to express *the product*; semantic colors are only allowed to express *the situation*.

There is one rule that often surprises new contributors: the substitution callout uses its own role token (`substitution-callout`) rather than the destructive role, even though a substitution might feel like a problem. PRD 07 is explicit that a routing substitution is *informational* — the user got an answer, the answer is attributed, and the callout exists so the user can see and understand the route. Rendering substitution in destructive red would mis-signal that something went wrong, and would also bleed a second saturated color onto a surface that should be calm. The substitution callout is a textbook case of "express the situation accurately, and the situation is not an error."

- Composer focus state: brand-edge plus halo glow, standard chrome easing, persistent while focused (timing in PRD 06 §3.4).
- Send button: filled with the accent; morphs to a neutral Stop when generating (per PRD 06 §5.2).
- Substitution callout (PRD 07): rendered in the substitution-callout role, not in destructive red — the situation is informational, not erroneous.
- Active conversation row in the sidebar: a thin accent stripe and a slightly stronger background tint, never a fully accent-filled row.

---

## B. Motion and disclosure

Motion in this product is choreographed, not decorative. The patterns here decide which surfaces move, how fast, and what the resting state looks like. Disclosure follows the same rule: things appear when they are needed and not before.

### Pattern: Choreographed motion

There is exactly one streaming cadence at any moment, and the working surface resolves to stillness when the response settles. Anxiety in a chat product comes from peripheral motion — pulsing badges, breathing icons, sliding hints — competing for attention while the user is reading. The rule: motion exists to communicate state changes, and once the state has changed, motion stops.

Three concrete cases anchor this:

- Streaming cadence. Reasoning text uses the linear shimmer cadence and the typing indicator uses the pulse-soft cadence defined in PRD 06 §3.4. Both stop the moment the stream resolves. The shimmer never bleeds onto the answer text itself once the answer begins to render (PRD 01 §5.4).
- Hover micro-lift. Icon buttons use a single-property translate-and-scale micro-lift (values in PRD 06 §3.4) — brief, with no accompanying color flare. The lift is felt more than seen; it acknowledges the cursor without performing.
- Progressive disclosure. Collapse and expand on the reasoning panel and on the attribution detail row use the standard chrome ease-out transition. There is no bounce, no overshoot. The motion is short enough that the user does not have to wait to read; long enough that the change registers.

Easing curves are pulled from a small palette: a standard ease-out for chrome, a soft spring (the spring curve named in PRD 06 §3.4) for entrance moments like the welcome screen. New surfaces should use one of these and not invent a third. The constraint is not aesthetic preference — it is that a small motion palette is what makes the product feel coherent across surfaces, and a large motion palette is what makes a product feel "designed by a committee." When in doubt, use the standard ease-out.

The rule about peripheral pulses is worth restating directly: nothing on the working surface breathes, pulses, or sweeps unless it is actively communicating a state change. A badge on the model picker indicating "Auto active" is a static dot, not a pulsing one. A new-conversation suggestion is a static card, not a shimmering one. If a surface is interesting enough to deserve attention, it can earn that attention through layout and typography, not through ambient motion.

### Pattern: Progressive disclosure

The default is *less*. Affordances are surfaced on demand on desktop (hover or focus) and always-visible on touch (no hover on touch). Details (cost breakdown, routing rationale, reasoning content) collapse to a compact summary by default and expand to a full view on user action. The rule is not "hide things" — the rule is "match the visual weight to the user's current intent."

This produces a measurably calmer working surface. A conversation list with only the current selection and the active conversation's name is restful; the same list with always-visible delete, share, and overflow on every row is not. The same logic governs the assistant message: the answer body is the figure, and copy/regenerate/edit live below it in a row that is invisible until the user moves toward the message.

A second consequence of progressive disclosure is that the summary state has to carry real information. "Thought for 4s" is not a placeholder — it is the answer to the user's likely question at that moment ("how long was it thinking?"), and that answer is what makes the collapsed state acceptable. The same is true of the compact attribution row: it shows the served model and tier, because that is what the user needs to know without clicking. Progressive disclosure only works when the summary is genuinely sufficient for the common case; if the user has to expand the row to find out anything useful, the disclosure has failed and the summary needs more.

- Message footer actions (copy, regenerate, edit, thumbs) are hover-revealed on desktop and persistent on touch (PRD 01 §4.6, PRD 06 §5.1).
- Reasoning panel collapses to "Thought for Xs" + chevron when the model finishes streaming reasoning (PRD 01 §4.2). Expanded state is remembered per message for the session.
- Attribution row shows model and tier always; cost, tokens, and routing notes expand on tap (PRD 06 §5.4, PRD 07 §6.1).

### Pattern: Streaming as a calmed state

Streaming is the moment a chat product is most likely to feel anxious — the cursor is jumping, text is unrolling, the user is waiting. Resist the urge to dress that moment up with motion. The single-cadence rule above is one half of this; the other half is that the Stop control is always reachable, sized to the touch target, and visually neutral. Stop is not a destructive action and must not be themed red.

The calm comes from doing less. There is no progress bar, no animated brand mark, no breathing border around the streaming message. The typing indicator is one dot, gently pulsing; the reasoning shimmer is a single linear sweep; the answer text appears at the rendering cadence the renderer dictates (PRD 01 §5.4). When the response settles, every animation stops. The conversation returns to text-on-paper.

The peacefulness pillar in `00-principles.md` is the principle that turns this from a stylistic preference into a rule. A chat product is a tool people use under cognitive load — drafting an email, debugging a stack trace, sketching an idea. A surface that performs activity at the user while the user is trying to think is a surface that is competing with them. The streaming-as-calmed-state pattern is the surface refusing to compete. It also has a downstream effect on the perceived quality of the renderer: a calm surface lets the eye notice rendering fidelity (smooth code highlighting, mid-token math resolution) rather than absorbing it through a haze of motion noise.

- Pre-first-token typing indicator uses pulse-soft and replaces itself with content on the first token (PRD 01 §4.1).
- Stop button morphs in the send slot, sized to the minimum touch-target in PRD 06 §3.3 on mobile, with a neutral "Stopped" chip on partial completion (PRD 06 §5.2).
- The streamed answer text is never wrapped in a live region (PRD 01 §5.7); a separate polite status region announces transitions.

---

## C. Working surface

The working surface is the chat thread itself: composer, message list, attribution row, reasoning panel. It is where the product earns its keep, and where the principles are most easily compromised by feature pressure. The patterns here protect that surface.

### Pattern: Focus as the brand moment

The composer focus state is one of the very few moments where the accent illuminates persistently during use. When the user focuses the composer, a brand-edge appears on the glass capsule and a soft halo glow extends behind it, both at the chrome easing curve. This is intentional. The composer is where the user is engaging the product; engagement deserves a moment of light. Everywhere else on the working surface, the accent appears only as a transient signal (a focus ring on Tab, the filled send button) and not as ambient color.

The principle to extract is this: brand identity does not live in the background tint of the page, in a colored sidebar, in a logo lockup at the top of the thread, or in a decorative stripe. It lives in the *moment of interaction*. The accent comes on when the user is acting, and recedes when they are reading. This is the smallest possible footprint for a brand cue that still feels present.

A useful corollary: if a designer or engineer feels the product needs "more brand presence," the first place to look is the composer focus state and the send button, not the chrome. Strengthening the focus glow, or refining the timing of the brand-edge fade-in, will produce more felt brand identity than any amount of accent color added to the header, the sidebar, or the empty-state hero. The pattern concentrates brand into the few moments where the user is leaning in; adding brand color to passive surfaces dilutes those moments instead of amplifying them.

- Composer focus glow: brand-edge + halo, at the chrome easing curve, persistent while focused.
- Send button: accent fill, neutralized to Stop when generating.
- Focus-visible ring on any focusable surface uses the accent at the same hue; it appears only on keyboard focus, never on hover.

### Pattern: Empty state earns distinctiveness

The four pillars require restraint on the working surface; they do not require restraint everywhere. The principles doc names the rule explicitly: distinctiveness belongs to empty states, transitions, and first-run. The welcome screen is where the product's voice is loudest, because the rest of the surface has to stay quiet. A reader of `00-principles.md` who has internalized the "calm content, calm chrome" rule should not also conclude that the empty state must be calm; it is the place the product is allowed to greet.

This shows up concretely in the welcome enter animation, which uses the spring entrance curve from PRD 06 §3.4 — the only place a spring curve appears in the working app. The initial state uses generous negative space (Ma): a single hero element rather than a feature grid, prompt cards arrayed under it rather than a wall of capability tiles. Once the user sends their first message, the welcome surface unmounts and the calm working surface takes over.

The pattern compounds with progressive disclosure. A user who sees the welcome screen only at first-run, and after that sees a calm working surface populated by their own conversations, gets a *personalized* product. The product's voice is heard once, registered, and then steps aside so the user's content is the surface. A wall-of-capability empty state — feature tiles, marketing copy, dismissable banners — does the opposite: it asks the user to absorb a marketing pitch every time they open a fresh chat. The principle's restriction of distinctiveness to empty states and first-run is the rule that makes restraint feel intentional rather than austere.

- Welcome enter animation: the spring entrance curve from PRD 06 §3.4; runs once on mount.
- Empty state composition: one hero element + a small set of prompt cards, not a feature grid.
- After first send: welcome unmounts and is not reintroduced until a new conversation is started.

### Pattern: Transparency as product surface

Transparency surfaces — model attribution, cost display, substitution callout — are first-class UI, not debug chrome. PRD 07 owns this contract end-to-end and the patterns doc inherits the rule: every assistant message renders an attribution row, the model is always visible without hover, cost is compact-but-accessible (visible in summary, expandable for breakdown), and substitution callouts are visibly rendered (not hover-only) when a non-null reason is present (PRD 07 §6.1).

The design consequence is that the attribution row gets the same typographic care as the answer text. It is not a smaller, greyer afterthought. It uses the same type stack, a one-step-down size, and a muted-but-readable color — high enough contrast to pass body-text thresholds. The substitution callout uses its own role token (`substitution-callout`), not the destructive role, because a routing substitution is informational, not erroneous. Treat any temptation to bury cost behind a tooltip, or to render the attribution row in a smaller secondary type stack, as a violation of this pattern.

The pattern also has an interaction-design half. The attribution row's expand control is keyboard-reachable and has an accessible name; the substitution callout is announced through the same status region as generation transitions when it appears at the end of a turn. Treating transparency as product surface means treating it as accessible-by-default, not as visual chrome that screen-reader users can skip. PRD 07 owns the contract; PRD 06 §5.4 owns the component; this pattern's job is to remind designers that the contract is load-bearing for the product wedge and cannot be deferred to "polish."

Cross-ref: PRD 07 §6 (UX rules) and PRD 06 §5.4 (model attribution row).

---

## D. Mobile first

Mobile-web is the primary form factor. The patterns here are not "responsive variants"; they are the default, and the desktop layout is the variant that has to argue for its differences.

### Pattern: Thumb zone primacy

The composer lives in the thumb zone. It floats at the bottom of the viewport, respects `safe-area-inset` on all four sides, and never lets a primary control fall under the OS gesture bar or the iOS Safari URL chrome. Primary controls — Send, Stop, the tier picker — meet the minimum touch-target size in PRD 06 §3.3 on every axis. The Stop control specifically must remain reachable during streaming without scrolling and without focus-trap workarounds (PRD 01 §1, PRD 06 §3.3).

The same rule applies to any new surface that lives near the bottom of the screen. A confirmation sheet, a tier-picker menu, an attachment chip row: all of them have to obey the safe-area rule, the minimum touch-target size in PRD 06 §3.3, and the reachability-during-streaming rule. If a proposed surface fails any of the three on the smallest supported mobile viewport, the proposal needs to change, not the rule.

"Thumb zone primacy" also constrains layout decisions higher up the screen. A primary action — anything the user is likely to invoke during a normal turn — does not live in the top-right corner of the viewport, because the top-right corner of a one-handed phone hold is the hardest place to reach. The top of the screen is for navigation, identity, and rarely-tapped controls. The bottom of the screen, and the composer in particular, is for the actions that drive the conversation. This is the rule that, applied consistently, keeps the product feeling phone-native rather than desktop-shrunk.

- Composer capsule: glass material, anchored at bottom, safe-area-inset honored top/right/bottom/left.
- Send/Stop control: meets the minimum touch-target size in PRD 06 §3.3, identical position before/during/after generation.
- Tier picker on mobile: bottom sheet, not a hover-dropdown.
- New-chat affordance: reachable from the composer or via a global shortcut, not parked exclusively in a hard-to-reach header corner.

### Pattern: Density splits by input modality

Hover does not exist on touch. The product handles this not by emulating hover with long-press (which fights the OS) but by splitting visual density by input modality. On desktop, the surface is calm and many affordances are revealed only on hover or focus. On touch, the same affordances are persistent, sized larger, and arranged for thumb travel.

This is not "two designs"; it is one design with one explicit rule. The rule appears in two specific places at the moment, and any new component that has hover-revealed controls on desktop must answer the same question on touch.

There is a temptation, when designing a new component for desktop, to lean hard on hover and figure out the touch story later. That order is backwards in this product. The touch rendering is the default; the hover-revealed desktop variant is the optimization that the calmer working surface allows. Designing in that order forces the question "is this affordance important enough to live persistently on a small screen?" up front, and that question is often the one that distinguishes a primary action (yes, persistent) from a secondary one (no, fold into an overflow menu).

- Conversation row controls (overflow menu, rename). Desktop: hidden until hover. Touch: always visible.
- Message footer actions (copy, regenerate, edit, thumbs). Desktop: fade-in on hover. Touch: persistent under each assistant message.

---

## E. Parallel surfaces

Accessibility is not a bolt-on. Keyboard navigation, screen-reader rendering, and reduced-motion rendering are each a complete rendering of the same UI, evaluated by the same standard as the visual rendering. The patterns here state that rule and point at the canonical source for each surface.

### Pattern: Keyboard, screen reader, reduced motion as renderings of one UI

A user navigating the product entirely by keyboard should reach the same affordances in the same logical order as a user navigating with a pointer. Every icon button is labeled; every focusable surface is reachable; every modal traps focus and returns it on close. The shortcuts dialog itself is keyboard-operable, focus-trapped, and screen-reader navigable — directly addressing a measured gap in incumbents (PRD 01 §5.7).

A user on a screen reader gets the same product. The streamed answer text is *not* wrapped in a live region, because token-by-token re-reading on NVDA/JAWS is a known anti-pattern. Generation transitions ("Generating", "Response ready", "Stopped") are announced by a single polite status region that lives outside the message body. The completed message body remains navigable but is not auto-announced. The history sidebar exposes a named landmark so a screen-reader user can jump to it without traversing the page (PRD 01 §5.7).

A user with `prefers-reduced-motion` set gets the same product. The shimmer, the pulse-soft typing indicator, the welcome spring enter, the hover micro-lift, and the focus-glow transition all follow the reduced-motion degradation defined in PRD 06 §3.4. The reduced-motion path is not a degraded experience; it is a parallel rendering. New components ship with the reduced-motion rendering verified at the same time as the visual rendering, not afterward.

The framing of these as *parallel renderings* matters because it changes how problems get triaged. If a screen-reader user cannot reach the substitution callout, that is not "an accessibility bug filed against a working product" — it is "the screen-reader rendering of the substitution callout is broken." The fix lives in the same code, on the same priority, as a visual bug in the same component. The "parallel rendering" framing collapses the gap between "main UI" and "a11y" that, in practice, is where accessibility regressions hide. PRD 01 §5.7 documents the gaps that incumbents have shipped and that this product is explicitly trying to close; that intent is only kept if every new component is reviewed against all four renderings before it ships.

- Keyboard. Every icon-only button has an accessible name (PRD 06 §5.1). The shortcuts dialog traps and returns focus (PRD 01 §5.7).
- Screen reader. Streamed body is not a live region; a separate polite status region announces transitions (PRD 01 §5.7, PRD 06 §3.5).
- Reduced motion. All animations follow the reduced-motion degradation defined in PRD 06 §3.4 when `prefers-reduced-motion` is set.

---

## Closing

These patterns are defaults, not laws. A deviation can be the right call — a new surface may have a genuine reason to elevate a flat surface, to introduce a second moment of brand color, to disclose something always-on instead of progressively. When that happens, the deviation requires a recorded entry in `04-rationale.md` naming the alternatives considered and the principle that the deviation is in tension with. Without a recorded entry, the deviation is a drift, and drifts compound.

The inverse rule also holds. When a pattern recurs across three or more components without being named, it should be added to this file. The point of the patterns doc is to make the second occurrence of a good idea look the same as the first. If a pattern is being reinvented every time it appears, the cost is paid by every reviewer and every new contributor; if it is named here, the cost is paid once.

Read alongside `00-principles.md` (the pillars) and `01-foundations.md` (color, type, space, motion philosophy). For anti-patterns and the failure modes these patterns are meant to prevent, see `03-anti-patterns.md`. For the recorded decisions behind specific tradeoffs, see `04-rationale.md`. For the implementation contract — tokens, components, acceptance criteria — see PRD 06.
