# Lovable-inspired redesign brief

Reference screenshot: `artifacts/design-reference/lovable-reference.png`

## Design language to adopt (for Olune — adapt, don't clone)

### Atmosphere
- **Deep dark canvas**: near-black / dark navy base, not flat grey
- **Dual-hue gradient glow**: electric blue bloom in the center/top, warm magenta/red-purple wash at the bottom
- **Glassmorphism**: translucent surfaces (keyboard, overlays) that let the gradient show through
- **Premium depth**: saturated accents against high-contrast white text

### Typography
- **Serif display** for hero greeting and brand wordmark (Olune already uses Instrument Serif — lean harder into it)
- **Sans** for all UI chrome, controls, labels

### Shapes
- **Pill everything**: buttons, toggles, banners, input containers
- **Generous rounding** on the hero composer card (`--radius-3xl` territory)

### Header (welcome state)
- Circular dark glass hamburger (left)
- Centered serif wordmark with brand accent (heart → Olune's brand mark)
- Optional slim pill banner below header ("Connect all your tools →" analogue: integrations / BYOK / transparency hook)

### Hero content
- Large centered serif greeting: "Got an idea, {name}?" energy (personalized, inviting)
- Platform/mode pill toggle aesthetic where applicable (Web/Mobile → could map to chat modes or stay decorative on welcome)
- Suggestion pills wrapping under greeting (already shipped — enhance glass + hover)

### Composer (Lovable card)
- Two-row card: textarea top, toolbar bottom
- Left: `+` disclosure, model dropdown ("Fable 5" → tier picker)
- Right: mic + **white circular send** with dark arrow (inverted send button on dark theme welcome)
- Dark grey glass card with heavy rounding

### Constraints (repo)
- Welcome-only atmosphere: `--hero-gradient`, `--welcome-ambient`, `--hero-glow-*` — **never on working thread** (PRD 06 / anti-patterns §G)
- Token-based colors only in feature code; define new tokens in `globals.css`
- Preserve all `data-testid`, aria contracts, e2e hooks
- `prefers-contrast: more` must zero decorative gradients/glows
- Light theme should get a softer version of the dual-hue treatment, not only dark

## Files likely touched
- `web/src/app/globals.css` — tokens, gradients, dark palette shift
- `web/src/components/chat/welcome-screen.tsx` — greeting copy/style, banner
- `web/src/components/chat/app-header.tsx` — wordmark, welcome chrome
- `web/src/components/chat/composer.tsx` — welcome send button inversion, card styling
- `web/src/components/chat/chat-thread.tsx` — hero atmosphere layers, centerSlot wordmark
