# Olune Logo — Concept B: "Crescent + Satellite Node" (abstract agent-mark)

> **Lane:** Abstract symbol / agent-mark — symbol-first, pairs with a wordmark
> lockup. Distinct from the wordmark-led **Concept A** by leading with a
> standalone geometric glyph rather than typography.
> **Ground truth:** `docs/design/BRAND_BRIEF.md`. Every constraint below traces
> to a brief principle (§6) — citations inline.

---

## 1. One-liner

A single open monoline crescent (the **lune** / letter **"O"**) with one solid
round **node** resting at its mouth — a **fixed satellite**. The crescent is the
moon and the "O"; the node is the **agent**: one autonomous point held at the
crescent's edge. Same stroke DNA as the incumbent ring, plus exactly one new idea
(the satellite node) that says *agent* without a literal robot, gear, or spark.

**Reads as, in one glance:** moon + one satellite body → "O" with a single fixed
node → a quiet, engineered system. Nothing organic, nothing decorative. The mark
is **static by design**; any literal motion/orbit *animation* belongs to **Concept
C**, not here.

---

## 2. Why this, against the brief

| Brief principle (§6) | How Concept B honors it |
| --- | --- |
| **1. One accent, blue `#2079E8`** | The entire mark is the single brand blue (light) / `#5BA0F2` brand-dark token (dark). No second hue, no gradient. |
| **2. Monoline, rounded-cap geometry** | Crescent is one `fill:none` stroke, even weight, `stroke-linecap:round`. The node is a filled circle — geometrically *a round cap given mass*, so it shares the crescent's terminal language instead of fighting it. |
| **3. "O" / crescent duality is the equity** | Preserved as the core: the arc still reads as both **O** and **moon**. The node *extends* the equity (moon→system) rather than replacing it. |
| **4. Deference, flat, no gradients** | Flat single-color. The only "depth" is the figure/ground relationship between arc and node — no glow, glass, or bevel. |
| **5. Geometric, not organic-literal** | Pure circle math on a 512 grid (one radius, one center, one node). No leaves/ripples/hand-drawn marks. The node simply *sits on* the crescent's circle — no orbit path is drawn, and no motion is implied. |
| **6. Theme-parity** | Ships **transparent** (no baked plate), with explicit light/dark stroke values — fixes the incumbent's hard-coded `#F9FAFC` plate (brief §7). |
| **7. Accessible & scalable** | Survives maskable inset, `forced-colors`, increased-contrast, and 16px favicon (node thickens for legibility at small sizes — see §8). `aria-label="Olune"`, `data-no-flip`. |
| **8. Serif wordmark** | Lockup wordmark is **Instrument Serif 400, `tracking-tight`** — the in-product display face, never the system sans. |

**Distinct from Concept A:** Concept A leads with the typographic "Olune"
logotype; Concept B leads with a **standalone symbol** that works with zero
letterforms (favicon, app icon, avatar) and only *adds* the wordmark in lockups.

---

## 3. Symbol geometry (construction spec)

Drawn on a **512 × 512** viewBox. One center, one radius, one node — fully
parametric.

```
viewBox          0 0 512 512
center (cx,cy)   256, 256
arc radius (r)   168            (incumbent uses 180; 168 buys room for the node + clear space)
stroke-width     64             (matches incumbent icon.svg stroke)
stroke-linecap   round
stroke-linejoin  round
fill (arc)       none
```

### 3.1 The crescent (open arc)

The arc is a **290° sweep** — a near-complete ring left **open at the
upper-right**, gap centered on **35°** (math angle, CCW from +x; screen-y down).
Gap half-width 35° → arc terminals at **0°** and **70°**.

| Terminal | Angle | Coordinate (x, y) |
| --- | --- | --- |
| Start (right, 3 o'clock) | 0° | **424.0, 256.0** |
| End (upper) | 70° | **313.5, 98.1** |

**Reference path (the major arc, the long way round through left + bottom):**

```
M 313.5 98.1 A 168 168 0 1 0 424.0 256.0
```

`large-arc-flag = 1` (take the 290° major arc), `sweep-flag = 0`. Round caps on
both terminals. This is the crescent / "O" and is the direct descendant of the
incumbent `M 356.7 403.2 A 180 180 0 1 1 435.6 266.6`.

### 3.2 The agent node

One **filled** circle sitting on the crescent's radius, centered in the
crescent's gap (35°):

| Property | Value |
| --- | --- |
| Center (x, y) | **393.6, 159.6** (= 35° at r = 168) |
| Radius | **40** (display); **fill** = same brand color as arc |
| Relationship | Sits *in the mouth* of the open crescent, on the same circle the arc traces → reads as one fixed satellite node resting at the crescent's edge |

The node radius (40) is deliberately a touch larger than half the stroke width
(32), so the node reads as a distinct mass slightly larger than the stroke,
giving it "body" as the agent without overpowering the arc. The gap
between the upper arc terminal (313.5, 98.1) and the node leaves clean negative
space so the two never visually merge at display size.

### 3.3 Optical balance

- The mark's **visual center of mass** shifts slightly up-right because of the
  node; in lockups, optically center on the **crescent's center (256,256)**, not
  the bounding box, so the wordmark baseline aligns to the moon, not the
  satellite.
- The gap opening points **up-and-right** (toward "forward / ascending"), a
  static composition cue — not an animation. The mark never moves; any literal
  motion/orbit animation is **Concept C**'s territory.

---

## 4. Color

One accent only. Transparent canvas; the glyph swaps value by theme (parity, not
translation — brief §6.6).

| Element | Light theme | Dark theme | Token / source |
| --- | --- | --- | --- |
| Crescent stroke | **`#2079E8`** | **`#5BA0F2`** *(approx of `--brand` dark `oklch(0.72 0.18 247)`)* | brief §1.3 `--brand` |
| Agent node fill | **`#2079E8`** | **`#5BA0F2`** | same — node and arc are always the same single color |
| Canvas | **transparent** (or `#F9FAFC` only when a plate is mandatory, e.g. some maskable contexts) | **transparent** (or `#080B11`) | brief §1.1 |

- **Pixel-exact builds:** prefer the OKLCH tokens (`--brand` light
  `oklch(0.59 0.20 247)` / dark `oklch(0.72 0.18 247)`) over the hex approxes;
  `#2079E8` is the established **static-asset** literal (brief §7).
- **Monochrome fallbacks:** on a brand-blue fill (e.g. a launch tile), render the
  whole mark in `--brand-foreground` (`#FCFCFC` light context). For ink/emboss or
  `forced-colors`, the mark is a single `currentColor` glyph (arc stroke + node
  fill share the color) and degrades cleanly to `CanvasText`.
- **No** second hue, **no** gradient, **no** glow on the mark — ever (brief §6.4).

---

## 5. Clear space & minimum sizes

- **Clear space:** keep a margin of **½ × stroke-width (32 units / 0.5× the cap
  diameter)** of empty space on all sides of the glyph bounding box; in lockups,
  the same unit defines the wordmark gap.
- **Minimum symbol size:** 16 px (favicon). Below ~24 px use the **favicon
  variant** (§8.3) where the node thickens.
- **Maskable safe zone:** all geometry must live inside the maskable inner circle
  (radius 144 on the 512 grid, per incumbent). At maskable scale the arc radius
  drops to **~136** and stroke to **~51** (incumbent maskable values), node
  scales proportionally to keep it inside the safe circle.

---

## 6. Lockups

The symbol is primary; the wordmark is optional and always set in **Instrument
Serif 400, `tracking-tight` (−0.006em)** — the in-product display face (brief
§2, §6.8). Wordmark color: `--foreground` (`#23262B` light / `#F2F3F4` dark), or
`text-foreground/90` to match the live in-app wordmark.

| Lockup | Layout | Use |
| --- | --- | --- |
| **Symbol only** | The glyph, transparent | Favicon, app icon, avatar, social profile, watermark |
| **Horizontal** | Symbol ▸ clear-space ▸ "Olune". Cap height of "Olune" ≈ crescent diameter; baseline optically centered on the crescent center (256), not the node | App header, nav, marketing lockup |
| **Stacked** | Symbol centered above "Olune" | Splash, square share cards, vertical contexts |

**Wordmark casing/spacing:** "Olune", initial cap only, `tracking-tight`, no
letter-spacing tricks. Do **not** redraw the "O" of the wordmark to mimic the
crescent — the symbol carries the moon; the wordmark stays plain serif so the
two equities don't compete.

---

## 7. Wordmark pairing rationale

The symbol and the serif "O" both encode the moon, so the lockup gives a gentle
double-read (mark-as-moon, type-as-moon) without being a rebus. Keeping the
wordmark in unmodified Instrument Serif honors the brief's narrow display
carve-out and means the lockup degrades to either half alone — symbol for
square/tiny contexts, wordmark for text contexts — with no loss of identity.

---

## 8. Favicon / app-icon / maskable specs

All derive from the §3 geometry. Replace the missing raster set (brief §7:
`/icon-192.png`, `/icon-512.png`, `/icon-maskable-512.png`,
`/apple-touch-icon.png`, splashes, `opengraph-image`).

### 8.1 Standard app icon (`icon.svg`, `icon-512.png`, `icon-192.png`)
- 512 grid, **transparent** background (theme-aware via CSS `prefers-color-scheme`
  in the SVG, or two PNGs).
- Arc r = 168, stroke 64, node r = 40, brand blue. Exactly the §3 mark.

### 8.2 Maskable icon (`icon-maskable.svg`, `icon-maskable-512.png`)
- Geometry inset to the maskable safe circle: arc r ≈ 136, stroke ≈ 51, node
  scaled to keep its full body inside r = 144.
- Background **filled** (maskable requires opaque): `#F9FAFC` (light) — matches
  incumbent maskable plate. Provide a dark maskable variant on `#080B11` if the
  platform supports theme-specific maskables.

### 8.3 Favicon (16 / 32 px) — legibility variant
- At ≤ 24 px the 64-weight arc + 40 node can muddy. Favicon variant:
  **arc stroke +8 (→72), node radius +6 (→46)**, gap widened ~5° so the node
  stays visually separate. Everything else identical.
- 32 px and up can use the standard mark.

### 8.4 Apple touch icon (`apple-touch-icon.svg/png`)
- 180 px target, but authored on the 512 grid. iOS auto-masks corners, so use a
  **filled** plate (`#F9FAFC`) with the standard (non-inset) mark, matching
  incumbent behavior.

### 8.5 Social / OpenGraph (`opengraph-image`)
- 1200 × 630, background `#F9FAFC` (light) — the brand canvas, flat, no gradient.
- Stacked lockup (symbol above "Olune") centered, generous *Ma* margins; optional
  tagline line in system sans, `--muted-foreground`, small: *"multi-model AI
  chat."* Symbol in `#2079E8`, wordmark in `--foreground`.

---

## 9. Theme behavior

- **Light** (`#F9FAFC` canvas): `#2079E8` glyph.
- **Dark** (`#080B11` canvas): `#5BA0F2` glyph (the brand-dark token) — *not* the
  same blue dimmed; uses the system's designed dark accent so contrast stays
  intentional against the deep navy night-sky canvas (which itself reinforces the
  lune reading — brief §5).
- **Transparent contexts:** inherits `currentColor` where embedded inline (e.g. an
  in-app SVG using `text-brand`), so it tracks the live theme token automatically.

---

## 10. Accessibility

- **`forced-colors` / Windows high-contrast:** single-color glyph collapses to
  `CanvasText`; arc + node both honor it (no fills that vanish).
- **Increased contrast:** no glow to zero out (the mark has none); stroke already
  high-contrast on both canvases.
- **RTL:** mark opts out of mirroring via `[data-no-flip]` (brief §7,
  `globals.css:584-586`) — the crescent's up-right opening is meaningful and must
  not flip.
- **Labeling:** `aria-label="Olune"`, `role="img"`.
- **Min contrast:** `#2079E8` on `#F9FAFC` and `#5BA0F2` on `#080B11` both clear
  UI-component contrast for a non-text graphic; the node's mass aids
  recognizability at favicon scale.

---

## 11. Don'ts

- ❌ No gradient, glow, glass, bevel, or shadow on the mark.
- ❌ No second hue (the welcome-only warm magenta hue-18 is forbidden on the mark — brief §1.4).
- ❌ Don't add more than one node, draw the orbit as a visible ellipse, or add spokes/sparks/gears — that breaks "subtract" and "no literal motifs."
- ❌ Don't square the caps or vary the stroke weight along the arc.
- ❌ Don't redraw the wordmark's "O" to match the crescent.
- ❌ Don't bake a light plate into transparent-context assets (the incumbent's latent dark-mode conflict — brief §7).
- ❌ Don't let the node touch or merge with the arc terminal at display size.

---

## 12. SVG reference (light theme, standard icon)

Illustrative — production should re-derive from §3 parameters and add the
theme-swap + `aria`/`data-no-flip` attributes.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"
     role="img" aria-label="Olune" data-no-flip>
  <!-- crescent: open ring, 290° major arc, round caps -->
  <path d="M 313.5 98.1 A 168 168 0 1 0 424.0 256.0"
        fill="none" stroke="#2079E8" stroke-width="64"
        stroke-linecap="round" stroke-linejoin="round"/>
  <!-- agent node: satellite at the crescent mouth (35° on r=168) -->
  <circle cx="393.6" cy="159.6" r="40" fill="#2079E8"/>
</svg>
```

Dark theme: swap both `#2079E8` → `#5BA0F2`. Maskable: inset radii/stroke per
§8.2 and add the opaque plate.

---

## IMAGE_GENERATION_PROMPT — Light background

```
A minimalist flat vector logo on a solid near-white background (#F9FAFC, NOT pure
white). The logo is a single geometric symbol: one open monoline crescent — a
near-complete circular ring, even stroke weight, with both ends rounded (round
line-caps), left OPEN at the upper-right. The crescent reads simultaneously as the
letter "O" and a crescent moon. Resting in the open mouth of the crescent, on the
same circular path, is exactly ONE solid filled round dot — a single fixed
satellite node, the only filled element — resting at the edge of the moon. The
dot is slightly larger than the stroke width and sits cleanly separated from the
arc's tip. Both the crescent and the dot are the SAME single color: a clear
medium brand blue (#2079E8). Absolutely flat: no gradient, no glow, no shadow, no
glass, no bevel, no texture, no second color, no text, no extra shapes, no spokes,
no sparks, no orbit ellipse drawn. Perfectly geometric and engineered, centered
with generous empty margin around it. Style: Apple-HIG / Linear / iA Writer
restraint — calm, quiet, premium, monoline like Lucide stroke icons. Square 1:1,
vector-crisp, centered.
```

## IMAGE_GENERATION_PROMPT — Dark background

```
A minimalist flat vector logo on a solid deep-navy night-sky background (#080B11).
The logo is a single geometric symbol: one open monoline crescent — a
near-complete circular ring, even stroke weight, both ends rounded (round
line-caps), left OPEN at the upper-right, reading as both the letter "O" and a
crescent moon. In the open mouth of the crescent, on the same circular path, sits
exactly ONE solid filled round dot — a single fixed satellite node, the only
filled element, a touch larger than the stroke width and clearly separated from
the arc tip — resting at the edge of the moon against a night sky. Both the crescent and
the dot are the SAME single color: a soft luminous sky-blue (#5BA0F2) that glows
gently against the dark navy WITHOUT any gradient or actual glow effect. Strictly
flat: no gradient, no halo, no shadow, no glass, no bevel, no texture, no second
color, no text, no extra shapes, no spokes, no drawn orbit line. Geometric,
engineered, centered with generous empty margin. Style: Apple-HIG / Linear
restraint — calm, premium, monoline like Lucide stroke icons. Square 1:1,
vector-crisp, centered.
```

## IMAGE_GENERATION_PROMPT — Favicon / app icon (small-size variant)

```
A tiny app-icon / favicon, square, optimized for legibility at very small sizes
(16–32px). Transparent or solid near-white (#F9FAFC) background. A single bold
geometric symbol fills most of the frame with a small even margin: one open
monoline crescent ring with rounded end-caps, left OPEN at the upper-right
(reads as letter "O" + crescent moon), and exactly ONE solid round dot resting in
the crescent's open mouth on the same circular path — a single fixed satellite node. For
small-size clarity the stroke is slightly THICKER and the dot slightly LARGER and
more separated than usual, so both stay crisp when shrunk. Both crescent and dot
are the SAME single brand blue (#2079E8). Completely flat and solid: no gradient,
no glow, no shadow, no glass, no text, no second color, no extra detail. Bold,
simple, instantly recognizable at 16px. Centered, square 1:1, vector-crisp. (For a
maskable variant: place all geometry well inside the central safe circle with the
symbol on an opaque #F9FAFC plate.)
```

---

## 13. Open questions / dependencies

- **Etymology gate (brief §7):** the lune/moon read is inferred, not documented.
  Concept B leans on it harder than the incumbent (moon **+** one satellite node).
  Confirm with product before committing; the mark still works as a pure abstract
  "O + a single fixed agent node" if the lunar story is dropped.
- **Node-as-agent legibility:** validate at 16px that the dot doesn't collapse
  into the arc — the §8.3 favicon variant exists for this; needs a real
  small-size render to confirm.
- **Theme-swap delivery:** decide SVG-internal `prefers-color-scheme` vs. two
  PNGs vs. inline `currentColor`; affects how `manifest.ts` references assets.
- **Comparison:** to be evaluated head-to-head against wordmark-led **Concept A**;
  Concept B is the symbol-first option (favicon/app-icon/avatar strength), A is
  the typographic option.
