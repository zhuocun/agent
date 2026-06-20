# Olune — Brand Brief

> **Status:** Research synthesis. Ground truth for downstream logo work.
> **Method:** Extracted directly from the repo (CSS tokens, layout metadata,
> icon SVGs, component code) and the canon design docs (`docs/design/`,
> `docs/prd/`). Every color carries a source citation. This document does **not**
> propose logo concepts — it records what Olune already *is* so the marks honor it.

The authoritative color format in this codebase is **OKLCH** (see
`web/src/app/globals.css`). Hex values below are either (a) **repo-stated
literals** — used verbatim in shipped files, safe to treat as exact — or (b)
**OKLCH-derived sRGB approximations** for convenience, marked *(approx)*. When a
logo must match a token precisely, use the OKLCH value, not the approx hex.

---

## 1. Palette

### 1.1 Repo-stated hex literals (exact — use these directly)

| Name | Hex | Where it's used | Source |
| --- | --- | --- | --- |
| Brand blue (mark) | `#2079E8` | Stroke color of every favicon/app-icon SVG | `web/public/icon.svg:3`, `web/public/icon-maskable.svg:3`, `web/public/apple-touch-icon.svg:3` |
| App background (light) | `#F9FAFC` | Icon canvas fill; PWA `background_color` + `theme_color`; light `theme-color` meta | `web/public/icon.svg:2`, `web/src/app/manifest.ts:16,20`, `web/src/app/layout.tsx:91`; equals `--background` light `oklch(0.985 0.003 250)` per `globals.css:179` |
| App background (dark) | `#080B11` | Dark `theme-color` meta (deep navy canvas) | `web/src/app/layout.tsx:92`; equals `--background` dark `oklch(0.15 0.014 262)` per `globals.css:356` |
| (Prior dark bg, superseded) | `#0C0F12` | Documented previous dark canvas, now replaced | `web/src/app/globals.css:353` |
| Print background | `#FFF` | Forced white only in `@media print` | `web/src/app/globals.css:949` |

> **iOS reference:** the brand token is documented as "default system blue
> (close to iOS `#007AFF`)" (`globals.css:209`). The rendered mark uses
> `#2079E8`. Treat **`#2079E8` as the canonical brand blue** for logo work; it is
> the only brand hex that ships as a literal.

### 1.2 Core theme tokens (OKLCH authoritative; hex approx)

All tokens are defined twice — light in `:root` (`globals.css:175`) and dark in
`.dark` (`globals.css:349`). Hue ~250 is the cool neutral; brand/ring sit at
hue 247; the warm counter-accent at hue 18; the welcome "electric blue" at 254.

| Token | Light OKLCH | Light hex *(approx)* | Dark OKLCH | Dark hex *(approx)* | Source |
| --- | --- | --- | --- | --- | --- |
| `--background` | `0.985 0.003 250` | `#F9FAFC` (exact) | `0.15 0.014 262` | `#080B11` (exact) | `globals.css:179,356` |
| `--foreground` | `0.18 0.005 250` | `#23262B` | `0.96 0.003 250` | `#F2F3F4` | `globals.css:180,357` |
| `--card` | `1 0 0` | `#FFFFFF` (exact) | `0.205 0.006 250` | `#2A2D31` | `globals.css:181,358` |
| `--primary` | `0.21 0.006 250` | `#2C2F34` | `0.92 0.003 250` | `#E7E8E9` | `globals.css:186,363` |
| `--muted` | `0.968 0.004 250` | `#F2F3F5` | `0.27 0.006 250` | `#3A3D42` | `globals.css:190,367` |
| `--muted-foreground` | `0.46 0.008 250` | `#6B6F76` | `0.7 0.008 250` | `#A7ABB2` | `globals.css:191,368` |
| `--accent` | `0.96 0.005 250` | `#F0F1F3` | `0.28 0.006 250` | `#3C4045` | `globals.css:192,369` |
| `--border` | `0.916 0.004 250` | `#E4E6E9` | `oklch(1 0 0 / 11%)` | white @ 11% | `globals.css:205,381` |
| `--ring` | `0.59 0.20 247` | `#2A7DEA` | `0.72 0.18 247` | `#5BA0F2` | `globals.css:207,383` |

### 1.3 Brand accent family (the single saturated accent)

| Token | Light OKLCH | Light hex *(approx)* | Dark OKLCH | Dark hex *(approx)* | Role / Source |
| --- | --- | --- | --- | --- | --- |
| `--brand` | `0.59 0.20 247` | **`#2079E8`** (mark literal) | `0.72 0.18 247` | `#5BA0F2` | The one saturated accent: primary action, focus, identity. `globals.css:210,385` |
| `--brand-foreground` | `0.99 0 0` | `#FCFCFC` | `0.16 0.01 247` | `#1A1D22` | Text/glyph on brand fill. `globals.css:211,386` |
| `--brand-muted` | `0.95 0.04 247` | `#E6EFFB` | `0.38 0.11 247` | `#3A4E73` | Pale brand tint surface. `globals.css:212,387` |

### 1.4 Welcome-surface atmosphere (welcome screen ONLY — never chrome)

These power the first-run dual-hue "bloom" (electric blue from the top, warm
wash from the bottom). They are **forbidden on the working thread** by the
anti-pattern catalog (`docs/prd/06-design-system-visual-spec.md:47`).

| Token | Light OKLCH | Dark OKLCH | Hex *(approx)* | Source |
| --- | --- | --- | --- | --- |
| `--accent-warm` (warm counter-hue) | `0.58 0.19 18` | `0.64 0.22 18` | `#CF4B5B` light / `#EC5A66` dark | `globals.css:220,392` |
| Electric-blue bloom (hue 254) | `0.60 0.21 254` | `0.74 0.20 254` | `#2E6FF2` light / `#5F9BF7` dark | `globals.css:231,243,342` / `397,403,489` |

> **Note:** there is **no second steady-state saturated accent.** The warm
> magenta/red (hue 18) exists *only* to feed welcome-surface gradients/glows; it
> is never applied to chrome (`globals.css:217–219`). A logo that introduces a
> permanent second brand hue would violate the one-accent rule
> (`docs/design/01-foundations.md:43–63`).

### 1.5 Semantic role colors (invoked only when the role applies)

| Token | Light OKLCH | Dark OKLCH | Hex *(approx, light)* | Source |
| --- | --- | --- | --- | --- |
| `--destructive` | `0.577 0.220 27.325` | `0.704 0.172 22.216` | `#E0494A` | `globals.css:196,372` |
| `--success` | `0.62 0.126 152` | `0.7 0.126 152` | `#2E9D63` | `globals.css:198,374` |
| `--warning` | `0.72 0.135 75` | `0.8 0.126 80` | `#C28A33` | `globals.css:200,376` |
| `--info` | `0.58 0.117 245` | `0.68 0.108 245` | `#3B82BE` | `globals.css:202,378` |

### 1.6 Chat & trust role colors (for completeness)

Chat: `--message-user` `0.955 0.005 250` light / `0.305 0.006 250` dark;
`--message-assistant` is `transparent` (flat reading surface);
`--code-block` is near-black in **both** themes (`0.205`/`0.235`) — the
deliberate "code is inverted" badge (`globals.css:248–255,410–417`;
rationale `docs/design/01-foundations.md:95`). Trust roles (`--trust-badge`
hue 245, `--byok-indicator` hue 280, `--temporary-chat-banner` hue 250) are all
**chroma-capped tints**, never hue claims (`globals.css:261–269,423–430`).

---

## 2. Typography

| Axis | Value | Source |
| --- | --- | --- |
| **UI / body (sans)** | Apple system stack — **no web-font load**: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", system-ui, sans-serif` | `globals.css:22–23` |
| **Mono** | `"SF Mono", ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace` — code blocks + token/cost numerals | `globals.css:24–25`; PRD `06:54` |
| **Display / heading (serif)** | **Instrument Serif**, weight **400 only**, loaded via `next/font` (`Instrument_Serif`), `display: "optional"`, exposed as `--font-heading-serif` → `--font-heading` | `web/src/app/layout.tsx:2,21–26`; `globals.css:32–33` |
| **Heading fallback** | `ui-serif, Georgia, "Times New Roman", serif` | `globals.css:32–33` |

**Weights in use:** body is regular; emphasis via `font-semibold` (headings,
strong, links) — `globals.css:770,790`. The serif ships **one weight (400)**, so
`font-normal` on the hero is structural, not stylistic
(`web/src/components/chat/welcome-screen.tsx:128–137`).

**Letter-spacing:** `--tracking-tight: -0.006em` — a subtle tightening tuned for
SF Pro (`globals.css:159–161`). The hero greeting and the `Olune` wordmark both
use `tracking-tight` (`welcome-screen.tsx:133`,
`chat-thread.tsx:3714`).

**Display vs body distinction (load-bearing):** the **serif is display-only** —
reserved for the welcome-hero greeting and the centered `Olune` wordmark on the
welcome surface. **Body and all chrome stay on the system sans.** This is an
explicit, narrow carve-out (Decision 16 / PRD `06:53`). The wordmark "Olune"
renders in `font-heading` (Instrument Serif), `text-xl`, `tracking-tight`,
`text-foreground/90` (`web/src/components/chat/chat-thread.tsx:3704–3719`).

**Type ramp:** restrained, rem-based; chat body ~`1.0625rem` mobile /
`0.9375rem` desktop, `leading-7` (`globals.css:764`); base 16px, measure capped
~70–80ch (PRD `06:55`). A custom `--text-2xs: 0.6875rem` (11px) caption step
exists for metadata/eyebrows (`globals.css:163–167`).

> **Verdict:** Olune has a **deliberate type identity** — Apple system sans for
> the entire working surface (deference / no FOIT), with **Instrument Serif as
> the single "brand voice" display face**, confined to first-run moments. There
> is **no custom brand sans**; the serif is the closest thing to a typographic
> logotype and the existing `Olune` wordmark is set in it.

---

## 3. Existing Mark

**A mark exists.** It is a single open circular arc — a near-complete ring with
a gap and round line-cap terminals — drawn in brand blue on the app background.

| Property | Value |
| --- | --- |
| Files | `web/public/icon.svg`, `web/public/icon-maskable.svg`, `web/public/apple-touch-icon.svg` |
| Canvas | `512 × 512` viewBox, filled `#F9FAFC` |
| Geometry | One `<path>` SVG arc, `radius 180` (maskable inset to `144`), spanning most of a circle but **left open** (an open "O" / crescent) |
| Stroke | `#2079E8`, `stroke-width 64` (maskable `51`), `fill: none`, **`stroke-linecap: round`** |
| Style | Pure line/stroke geometry — **no fill, no gradient, no text, monoline, rounded caps** |
| `aria-label` | `"Olune"` |

Exact path (icon.svg): `M 356.7 403.2 A 180 180 0 1 1 435.6 266.6`
(`web/public/icon.svg:3`).

**Wordmark:** the text "Olune" is rendered live (not as an asset) in Instrument
Serif on the welcome header (`chat-thread.tsx:3704–3719`) and the loading state
says "Loading Olune…" (`chat-thread.tsx:3565`). No SVG/PNG logotype file exists.

**Missing assets (referenced but NOT present in repo):** `manifest.ts` and
`layout.tsx` reference `/icon-192.png`, `/icon-512.png`,
`/icon-maskable-512.png`, `/apple-touch-icon.png`, and
`/splash-*-{light,dark}.png` — **none of these PNGs exist** in `web/public/`
(only the three SVGs above plus Next/Vercel default SVGs). **No `opengraph-image`
exists.** This is a real gap: the raster icon set and social-share image need to
be produced from whatever mark logo work settles on.

> **Summary:** the current mark is a **minimal monoline open ring / crescent in
> `#2079E8`** — reads simultaneously as the letter **"O"** and a **crescent moon
> ("lune")**, matching the name. It is consistent with the brand's deference +
> geometry discipline. Logo work should treat it as the incumbent baseline.

---

## 4. Visual Language

| Dimension | What the repo does | Source |
| --- | --- | --- |
| **Radius** | Single base `--radius: 0.625rem` (10px); scale `sm 0.6× → 3xl 2.4×` of base; everything rounded, nothing sharp; capsules are full `9999px` pills | `globals.css:176,98–107`; `app-header.tsx:63` |
| **Iconography** | **Lucide React, exclusively** — line/stroke icons, `strokeWidth 2`–`2.25`, color inherited from text context (`currentColor`), never hard-coded fills | `welcome-screen.tsx:3–11`; `app-header.tsx:4–13,111`; `package.json:19`; `docs/design/01-foundations.md:289–323` |
| **Shadows / elevation** | Soft, diffuse, bottom-heavy halos (no hard drops, no bevels): `--float-shadow`, `--pill-shadow`, plus the glass ambient/key stack | `globals.css:314–320,141–145` |
| **Glassmorphism** | **Apple "Liquid Glass"** is the signature chrome material: `backdrop-filter: blur(14–32px) saturate(~1.6–1.7)`, translucent fills, inset refraction rim/highlight. Used for **chrome only** (header float buttons, composer capsule, FAB, overlays); **message surfaces stay flat** | `globals.css:280–312,442–467,664–725`; `docs/design/01-foundations.md:283–287` |
| **Gradients** | Reserved for **welcome-surface atmosphere only** (dual-hue radial blooms). Buttons/chrome get **no gradients** — the "gradient-on-button reflex" is explicitly refused | `globals.css:231,243–245,403–405`; `docs/design/00-principles.md:88` |
| **Spacing rhythm** | 4px base grid; generous gutters ("Ma" — charged emptiness as substance); space added before chrome | PRD `06:59`; `docs/design/01-foundations.md:159–205` |
| **Motion** | Spring-derived iOS easing curves (`--ease-ios-*`, `--ease-welcome`); choreographed, resolves to stillness; `prefers-reduced-motion` is a first-class designed path | `globals.css:109–133`; `docs/design/01-foundations.md:207–267` |
| **Accessibility posture** | Honors `prefers-reduced-motion`, `prefers-reduced-transparency`, `prefers-contrast`, `forced-colors`; welcome glow zeroes under increased contrast; RTL-aware (logo opts out via `[data-no-flip]`) | `globals.css:584–586,860–892,1080–1091` |
| **Surface character** | No pure white / pure black surfaces (neutrals pulled inward); flat reading column; chrome floats, content sits at zero elevation | `docs/design/00-principles.md:66`; `01-foundations.md:283–287` |

**Leaning:** **flat + minimal for content, glassmorphic for chrome, iOS/Apple-HIG
aligned throughout.** Not skeuomorphic, not heavily decorated. Geometry is
systematic and engineered; warmth lives in material, motion, and spacing — never
in hue.

---

## 5. Brand Tone

**What Olune is:** a transparent, multi-model, privacy-first, cost-leading **AI
chat** for web and mobile-web. Tagline candidates in-repo: *"Every major model in
one place — where you see (and control) the cost and your data"* (PRD
`00-product-overview.md:14`) and the manifest's *"Chat that respects your time."*
(`manifest.ts:9`). Metadata title: *"Olune — multi-model AI chat"*; description:
*"A transparent, multi-model, privacy-first AI chat. See which model answered and
what it cost."* (`layout.tsx:29–31`).

**Positioning wedge:** model choice + per-message transparency + aggressive cost
leadership (DeepSeek default) + privacy (no-train-by-default, BYOK). **Trust is a
product surface.** Explicitly **not** a "do-everything" productivity/agent suite —
it is a focused chat product (PRD `00:26`).

**Voice / copy character:** calm, quiet, and human. The welcome greeting is a
single inviting line ("Got an idea?" / "Got an idea, {name}?") rather than a
feature pitch; prompt suggestions are "quiet objects that hint at variety
without performing a feature pitch" (`welcome-screen.tsx:43–62`). No
celebratory/exclamatory tone, no hype.

**Design ethos (the four pillars):** **minimalism, peacefulness, nature, high
aesthetics**, governed by the meta-rule **"when in doubt, subtract"**
(`docs/design/00-principles.md:1–3,154–158`). Lineage explicitly cited: Apple HIG
(deference/clarity/depth), Dieter Rams ("less, but better"), Japanese *Ma* /
*Kanso* / *Seijaku*, biophilic design. Exemplars named: iA Writer, Bear, Linear,
Arc, Things 3.

**Name etymology (inferred, not documented):** no explicit etymology exists in
the repo. The strongest signal is the **mark itself** — an open ring / crescent
that reads as both **"O"** and a **moon**. **"Olune" ≈ "O" + _lune_** (French for
*moon*), consistent with the crescent mark, the calm/peaceful pillar, and the
deep-navy night-sky dark canvas (`#080B11`). *Flagged as inference — confirm with
product before leaning a logo concept on a literal moon.*

---

## 6. Design Principles Synthesis

Concrete, non-generic principles any Olune mark must honor:

1. **One saturated accent, and it is blue `#2079E8`.** The mark lives in this
   single brand blue (or a neutral on it). Introducing a second permanent
   saturated hue (e.g. the welcome-only warm magenta) violates the system's
   one-accent law (`01-foundations.md:43–63`).

2. **Monoline, stroke-based, rounded-cap geometry.** The existing mark is a
   single open arc: `fill:none`, even stroke weight, `stroke-linecap: round`.
   Honor this line-first, rounded-terminal language — it rhymes with Lucide's
   stroke icons. Avoid filled blobs, multi-shape compositions, or sharp corners.

3. **"O" / crescent-moon duality is the equity.** The current mark already
   doubles as the letter O and a moon ("lune"). Preserve this read; it ties the
   name, the mark, and the calm/night-sky palette together.

4. **Deference over decoration — flat, no gradients on the mark.** Gradients,
   glows, and glass are reserved for atmosphere/chrome, never logos or buttons.
   The mark must read as flat, single-color, and quiet (`00-principles.md:88`).

5. **Geometric and systematic, not organic-literal.** Structure is engineered
   (grid, geometry); "nature" enters only through soft light/motion/material —
   **never** through literal motifs. No leaves, ripples, or hand-drawn marks
   (`00-principles.md:49–71`).

6. **Theme-parity, not theme-translation.** The mark must hold on the near-white
   `#F9FAFC` light canvas **and** the deep-navy `#080B11` dark canvas with equal
   intent — designed for both, mirror not afterthought (`01-foundations.md:81–97`).
   Note the current SVGs hard-code a light `#F9FAFC` plate; a theme-aware or
   transparent treatment would be an improvement.

7. **Accessibility-robust and scalable.** Must survive maskable safe-zone insets
   (already handled at radius 144), `forced-colors`, increased-contrast, and tiny
   favicon sizes. Stroke weight should remain legible from 16px to 512px; the
   mark carries `aria-label="Olune"` and should opt out of RTL mirroring
   (`[data-no-flip]`, `globals.css:584–586`).

8. **Serif voice for the wordmark.** If a logotype accompanies the mark, the
   in-product wordmark is **Instrument Serif (400), tracking-tight**. A wordmark
   should reference this display serif, not the system sans used for working UI
   (`layout.tsx:21–26`, `chat-thread.tsx:3704–3719`).

---

## 7. Flagged Conflicts & Gaps

- **Default theme is `system` (no fixed light/dark default).** `ThemeProvider`
  uses `defaultTheme="system"` with `enableSystem` (`layout.tsx:146–150`). The
  manifest can express only one `theme_color` and pins the **light** surface
  `#F9FAFC` (`manifest.ts:17–20`), while paired `theme-color` metas serve light
  **and** dark (`layout.tsx:90–93`). **Implication:** the mark cannot assume a
  background — design for both, or transparent. The current SVGs bake in a light
  `#F9FAFC` plate, which is a latent conflict on dark surfaces.
- **Brand hex vs OKLCH token.** The shipped mark uses literal `#2079E8`; the
  `--brand` token is `oklch(0.59 0.20 247)` (light) / `oklch(0.72 0.18 247)`
  (dark) and is described as "close to iOS `#007AFF`." These are *close but not
  identical*. For pixel-exact brand matching prefer the OKLCH token; for a static
  asset, `#2079E8` is the established literal.
- **Missing raster + social assets.** All PNG icons, maskable rasters, splash
  screens, and any `opengraph-image` referenced by `manifest.ts`/`layout.tsx` are
  **absent from the repo** — they must be generated as part of finalizing the mark.
- **Name etymology unconfirmed.** The moon/"lune" reading is an inference from the
  mark + palette, not documented anywhere. Confirm before committing a logo
  concept to a literal lunar motif.
