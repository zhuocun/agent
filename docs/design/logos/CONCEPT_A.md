# Concept A — "Aperture"

> **Lane:** Wordmark-led. A typographic *Olune* logotype set in Instrument
> Serif, carrying one custom letterform detail — the capital **O** is cut open
> into a crescent — that doubles as a standalone monogram glyph for the favicon.
>
> **Tagline (internal, for the mark — not product copy):** *"The O that opens."*

---

## 1. Concept in one breath

*Olune* is written in its native display face, Instrument Serif 400, exactly as
it already renders on the welcome surface — so the logo is not a new invention,
it is the **product's own voice promoted to an asset** (Principle 8). The only
intervention is on the first letter: the **O** is not a closed serif bowl, it is
an **open ring with one rounded terminal** — the incumbent crescent mark fused
into the type. Read left to right it is the word *Olune*; read at the glyph it is
an **O / crescent moon** (Principle 3). Nothing else is added. *When in doubt,
subtract.*

The custom **O** has a sibling — not a clone — in the **monogram glyph**. The
favicon glyph is a pure **monoline** open ring in brand blue (the shipped
`icon.svg` arc); the wordmark's **O** is a **serif-modulated open bowl** — the
same break in Instrument Serif's high-contrast letterform, thick/thin contrast
intact. They share the **same silhouette and gesture** — an open ring whose break
faces lower-right — but wear it at **two levels of dress**: one undressed
monoline, one in full serif. Same shape read two ways, not the identical path.

---

## 2. Rationale — every decision tied to BRAND_BRIEF §6

| Decision | Principle(s) | Why |
| --- | --- | --- |
| Single accent = brand blue `#2079E8` (`#5BA0F2` on dark); no second hue anywhere | **1** | The mark obeys the one-accent law. The warm welcome hue is never touched. |
| The standalone glyph is a **monoline open arc, `fill:none`, even weight, round caps** | **2** | It *is* the incumbent geometry (`icon.svg`), not a redraw — line-first, rounded-terminal, rhymes with Lucide. |
| The **O** reads as letter **and** crescent moon | **3** | Preserves the existing equity; ties name → mark → night-sky palette. |
| Flat, one color, no gradient/glow/glass on the mark | **4** | Deference over decoration; atmosphere stays on chrome only. |
| Geometry is constructed on a grid; the "lune" reading is structural, not a drawn moon-with-craters | **5** | Systematic, engineered; nature enters via palette/space, never literal motif. |
| Three first-class color builds (light, dark, mono), nothing baked to one plate | **6** | Theme-parity: designed for `#F9FAFC` and `#080B11` with equal intent; transparent canvases by default. |
| Stroke weight + gap tuned to survive 16px → 512px and maskable inset; `data-no-flip`, `aria-label="Olune"` | **7** | Accessibility-robust, scalable, RTL-safe. |
| Wordmark is Instrument Serif 400, `tracking-tight: -0.006em` | **8** | The logotype *is* the in-product serif voice, not the working-UI sans. |

---

## 3. Composition

### 3.1 Construction grid

All geometry is laid out on a **512 × 512** master unit (the icon viewBox already
in the repo) and a **4px base grid** (BRAND_BRIEF §4 spacing rhythm). The
monogram is built first; the wordmark inherits the monogram's optical weight.

### 3.2 Standalone monogram glyph (the favicon mark)

Pure monoline open ring — identical in spirit and metrics to
`web/public/icon.svg`, refined for crispness.

| Property | Value | Notes |
| --- | --- | --- |
| Canvas | `512 × 512` viewBox | matches incumbent |
| Center | `(256, 256)` | optically centered |
| Radius (centerline) | `180` | full mark |
| Radius (maskable inset) | `144` | survives Android/iOS safe-zone |
| Stroke width | `64` (maskable `51`) | weight = `0.355 × radius`; keeps a 16px favicon ≈ 2px stroke |
| Cap | `stroke-linecap: round` → terminal corner radius `= 32` (½ of the `64` stroke; maskable build = `25.5`, ½ of `51`) | the two rounded caps are the only "corners"; nothing sharp |
| Fill | `none` | line-first, never a filled blob |
| Gap | arc opening of **≈ 52°** on the **east / lower-east** edge (≈ 3 o'clock → 5 o'clock) | the break that makes it an open "O" / crescent; opening points outward to the right |
| Sweep | large-arc, single `<path>` | one continuous stroke, no joins |

Reference path (incumbent, reused verbatim as the canonical centerline):
`M 356.7 403.2 A 180 180 0 1 1 435.6 266.6`
(center `256,256`; terminals at ≈ 56° and ≈ 3° below the horizontal, gap between
them).

**Negative space** is load-bearing twice over: the **counter** (the ring's hollow
center) and the **gap** (the crescent opening). Both must stay open — never fill
the counter, never close the gap.

### 3.3 Horizontal wordmark lockup

```
   ◜‿◞  l u n e        ← "O" is the open-ring glyph; "lune" in Instrument Serif
   └─ crescent O ──┘
```

- **Type:** Instrument Serif, weight **400 only**, letter-spacing
  `-0.006em` (`--tracking-tight`). Case: capital **O**, lowercase **l u n e**
  (exactly the in-product `Olune` casing, `chat-thread.tsx:3704–3719`).
- **The custom O:** within the wordmark the **O** is drawn as the *serif-dressed*
  crescent — Instrument Serif's high-contrast bowl with its **lower-right
  terminal cut open** and finished with a **single rounded cap**, the gap angle
  echoing the monogram (**52°**). The thick/thin modulation of the serif is
  preserved on the closed portion of the bowl; only the opening is monoline-ish
  where the cap rounds off. This is the one — and only — custom letterform.
- **Optical alignment:** the O's overshoot sits on the same baseline and cap line
  as a normal Instrument Serif cap O; the opening is positioned so the word still
  reads instantly as *Olune* (the gap does not collide with the following `l`).
- **Cap height (H):** set the wordmark so cap-height `H` defines the unit. The
  monogram-as-O occupies the full cap height.

**Serif open-O construction:**

| Aspect | Spec |
| --- | --- |
| Cut location | the bowl is opened on the **lower-right** (≈ 4–5 o'clock), the same quadrant as the monogram gap, so glyph and letter share one gesture |
| Gap angle | **52°** measured at the centerline, matching the monogram canonically |
| Terminal cap | the open end is finished with a **single rounded terminal** — the hairline-side stroke tapers into the cap so the round read is soft, not a blunt cut |
| Thick/thin axis | Instrument Serif's contrast axis is **vertical-ish** (stress near 0–10° off vertical): thick at the left/right flanks of the bowl, thin at top and at the cut, with bracketed serifs untouched |
| Preserved modulation | the closed ~308° of the bowl keeps the full serif thick/thin; only the last few degrees into the rounded terminal flatten toward an even weight |

**Proportions & spacing of the lockup (in cap-height units, `1H` = O height):**

| Metric | Value |
| --- | --- |
| O diameter | `1.00 H` |
| `l` ascender height | `≈ 1.02 H` (Instrument Serif ascender ≈ cap) |
| x-height (`u n e`) | `≈ 0.52 H` |
| Space O → l (after the open O) | `0.30 H` |
| Letterspacing rest of word | tracking-tight `-0.006em` (subtle negative) |
| Lockup left/right padding (clear space) | `≥ 0.75 H` |
| Lockup top/bottom clear space | `≥ 0.50 H` |
| Baseline shift | none — single baseline |

**Vertical lockup (secondary):** monogram glyph centered above the full *Olune*
wordmark, both horizontally centered on a shared vertical axis. Used only where a
horizontal lockup cannot fit (rare).

**Proportions & spacing of the vertical lockup (glyph diameter `G` = the unit):**

| Metric | Value |
| --- | --- |
| Glyph diameter | `1.00 G` |
| Wordmark cap-height (`H`) | `≈ 0.42 G` (wordmark sits subordinate to the glyph) |
| Vertical gap (glyph baseline → wordmark cap line) | `0.40 G` |
| Horizontal alignment | optical center of glyph aligned to optical center of the wordmark (not its bounding-box center — the open O shifts the word's optical center slightly right) |
| Total lockup height | `≈ 1.82 G` (`1.00 G` glyph + `0.40 G` gap + `0.42 G` wordmark) |
| Total lockup width | wordmark width (always ≥ glyph diameter at this `H`) |
| Clear space | `≥ 0.50 G` on all sides |

**Clear space rule:** the cap-height `H` is the exclusion unit; keep `≥ 0.75 H`
of empty space on all sides of any lockup ("Ma" — charged emptiness, §4).

---

## 4. Color

All builds are **flat, single-fill per element, no gradients** (Principle 4).
Backgrounds are **transparent by default**; the swatches below name the *intended*
canvas so contrast is verified, but the assets do not bake a plate (Principle 6,
fixing the latent light-plate conflict in §7).

### 4.1 Light build — on `#F9FAFC`

| Element | Color | Token / source |
| --- | --- | --- |
| Wordmark `Olune` text (l, u, n, e) | `#23262B` | `--foreground` light (approx) |
| Custom **O** / crescent | **`#2079E8`** | `--brand` light (mark literal) |
| Standalone glyph | **`#2079E8`** | brand blue, full |

Rationale: the wordmark stays a quiet near-black; the single accent lands on the
**O** so the one brand hue carries the identity exactly where the meaning lives.

### 4.2 Dark build — on `#080B11`

| Element | Color | Token / source |
| --- | --- | --- |
| Wordmark `Olune` text | `#F2F3F4` | `--foreground` dark (approx) |
| Custom **O** / crescent | **`#5BA0F2`** | `--brand` dark (approx) — the lightness-lifted brand blue |
| Standalone glyph | **`#5BA0F2`** | brand blue, dark variant |

Rationale: brand blue is lifted to its dark-theme value so it holds equal
saturation-presence against deep navy (theme-parity, not a dim copy).

### 4.3 Monochrome variant

Single ink, no accent — for forced-colors, single-color print, embossing,
favicons under `prefers-contrast`, and partner placements.

| Context | Color |
| --- | --- |
| On light | `#000000` (or `currentColor`) entire lockup + glyph |
| On dark | `#FFFFFF` (or `currentColor`) entire lockup + glyph |
| Inline / system | `fill: currentColor` so it inherits text color |

Note: pure black/white is allowed **only** in the mono/forced-colors variant; the
steady-state builds use the pulled-in neutrals (§4.1–4.2) per the "no pure
white/black surfaces" posture.

---

## 5. Typography

- **Face:** Instrument Serif, weight **400 only**, loaded via `next/font`
  (`Instrument_Serif`) and exposed as `--font-heading` — already in the build
  (`layout.tsx:21–26`, `globals.css:32–33`). No new font is introduced.
- **Tracking:** `--tracking-tight: -0.006em` on the whole wordmark, matching the
  live `Olune` header and welcome hero (`chat-thread.tsx:3714`,
  `welcome-screen.tsx:133`).
- **Fallback:** `ui-serif, Georgia, "Times New Roman", serif` (for live/HTML
  rendering of the wordmark before the web font resolves).
- **Casing:** capital `O`, lowercase `lune` — the product's own casing.
- **The serif is display-only:** this asset is a brand/display artifact; it never
  implies the working UI changes face (system sans stays everywhere else,
  Decision 16).
- **Outlining for static assets:** in shipped SVG/PNG the wordmark is converted to
  **outlines** (paths) so it renders identically without the font; the custom O is
  authored as a path regardless.

---

## 6. Symbolism

- **O = open ring = crescent moon = "lune".** The single custom letterform fuses
  the word's first letter with the moon in its name. The opening is not a defect;
  it is an **aperture** — an opening, a way in, a thing not sealed shut — echoing
  Olune's stance: transparent, open about cost and data, nothing hidden
  (BRAND_BRIEF §5).
- **The gap faces outward (east).** A crescent waxing toward fullness — quiet
  forward motion, never loud (calm/peaceful pillar).
- **Monoline + rounded caps = softness without decoration.** Engineered geometry,
  warmth only in the radius of the terminals (§4 visual language).
- **One accent on one letter** = the whole "one saturated accent" philosophy made
  literal: the brand is a single blue, placed with restraint.

---

## 7. Scalability

| Size | Build | Behavior |
| --- | --- | --- |
| **16px favicon** | monogram glyph only | stroke renders ≈ 2px; gap ≈ 52° stays visibly open; counter stays hollow. Wordmark is dropped — never shown below ~96px wide. |
| **32px** | monogram glyph | stroke ≈ 4px; crisp; round caps read. |
| **512px app icon** | monogram glyph at the **inset radius `144`**, centered in a **rounded-square safe area** | art uses the maskable geometry (radius `144`, stroke `51`, half-stroke `25.5`) → outer edge `= 144 + 25.5 = 169.5` from center, well inside the `≈ 205px` maskable safe radius (≈ `410px` safe-circle diameter). Rounded-square corner radius for the plate = `≈ 90px` (`512 × 0.176`, iOS superellipse feel). |
| **Maskable** | glyph radius inset to `144`, stroke `51` (half-stroke `25.5`) | outer edge `= 144 + 25.5 = 169.5` from center; survives Android adaptive-icon and iOS mask crop with margin to the `≈ 205px` safe radius — nothing critical near the edge. |
| **Wordmark min size** | `≥ 96px` wide / cap-height `≥ 14px` | below this the open O's gap and serif modulation muddy; switch to the monogram. |
| **forced-colors / prefers-contrast** | mono variant, `currentColor` | gap + counter give the shape silhouette legibility without relying on hue. |
| **RTL** | `data-no-flip` on all assets | the crescent never mirrors. |

**Stroke-to-radius discipline:** weight is locked at `0.355 × radius` so the
glyph keeps identical optical weight at every size; the favicon and the 512 icon
are the same shape scaled, not redrawn.

---

## 8. Suggested filenames

```
web/public/
  icon.svg                      # monogram glyph, brand blue, transparent (favicon master)
  icon-maskable.svg             # glyph at radius 144 / stroke 51, transparent
  apple-touch-icon.svg          # glyph centered in rounded-square safe area
  icon-192.png                  # raster, transparent
  icon-512.png                  # raster, transparent
  icon-maskable-512.png         # raster, maskable inset
  apple-touch-icon.png          # 180×180 raster, plate per platform
  opengraph-image.png           # 1200×630 social card, wordmark lockup

docs/design/logos/assets/concept-a/
  olune-glyph.svg               # monogram, fill:currentColor (theme-agnostic)
  olune-glyph-light.svg         # glyph #2079E8
  olune-glyph-dark.svg          # glyph #5BA0F2
  olune-wordmark-light.svg      # lockup: #23262B text + #2079E8 O
  olune-wordmark-dark.svg       # lockup: #F2F3F4 text + #5BA0F2 O
  olune-wordmark-mono.svg       # lockup, single currentColor
  olune-lockup-vertical.svg     # glyph over wordmark (secondary)
```

---

## IMAGE_GENERATION_PROMPT

> Three independent prompts. Each is fully self-contained (no shared state).
> Colors are exact sRGB hex. **No text/lettering is requested in the favicon
> prompt** to avoid glyph garbling; the wordmark prompts spell the word
> letter-by-letter and instruct the generator to render type as clean vector
> shapes. Render as flat vector art, no photographic texture.

### Prompt 1 — Primary mark on LIGHT background

```
A minimalist flat vector brand logo, horizontal wordmark lockup, on a solid
near-white background of exact color #F9FAFC. The wordmark spells the five
letters O - l - u - n - e ("Olune"), set in a high-contrast classical display
serif typeface (Instrument Serif style: thin hairlines, thick stems, elegant
bracketed serifs), weight regular, tightly spaced (slightly negative tracking).
Casing: a single capital "O" followed by lowercase "l", "u", "n", "e". The four
letters l, u, n, e are filled in a dark near-black ink of exact color #23262B.

The first letter, the capital "O", is special: it is NOT a closed circle. It is
an OPEN, SERIF-MODULATED bowl — a crescent cut from a high-contrast serif "O".
Keep the typeface's THICK/THIN contrast: the left and right flanks of the bowl are
THICK, the top and bottom are THIN hairlines (vertical stress, like a classical
serif O). The bowl is broken open on its LOWER-RIGHT edge with a single gap of
about 52 degrees, and that one open end is finished with a soft ROUNDED TERMINAL
(no sharp corner). Do NOT draw it as an even-weight monoline ring — it must look
like an elegant serif letter whose lower-right has been opened. This open "O" is
colored in a vivid medium blue of exact color #2079E8. The hollow center of the O
stays empty (transparent to the background); the gap stays open. The open O reads
as both the letter O and a crescent moon.

Style: extremely clean, flat, single solid color per element, NO gradient, NO
glow, NO shadow, NO 3D, NO texture, NO outline stroke around the letters. Crisp
geometric vector. Generous empty margin around the wordmark. Centered. The letters
must be perfectly formed, legible, and spelled exactly "Olune" — render type as
clean vector letterforms, not handwriting, not distorted, no extra characters.
Aspect ratio 16:9, the lockup occupying the central third.
```

### Prompt 2 — Primary mark on DARK background

```
A minimalist flat vector brand logo, horizontal wordmark lockup, on a solid
deep-navy near-black background of exact color #080B11. The wordmark spells the
five letters O - l - u - n - e ("Olune"), set in a high-contrast classical
display serif typeface (Instrument Serif style: thin hairlines, thick stems,
elegant bracketed serifs), weight regular, tightly spaced (slightly negative
tracking). Casing: a single capital "O" followed by lowercase "l", "u", "n", "e".
The four letters l, u, n, e are filled in a soft off-white of exact color
#F2F3F4.

The first letter, the capital "O", is special: it is NOT a closed circle. It is
an OPEN, SERIF-MODULATED bowl — a crescent cut from a high-contrast serif "O".
Keep the typeface's THICK/THIN contrast: the left and right flanks of the bowl are
THICK, the top and bottom are THIN hairlines (vertical stress, like a classical
serif O). The bowl is broken open on its LOWER-RIGHT edge with a single gap of
about 52 degrees, and that one open end is finished with a soft ROUNDED TERMINAL
(no sharp corner). Do NOT draw it as an even-weight monoline ring — it must look
like an elegant serif letter whose lower-right has been opened. This open "O" is
colored in a luminous sky blue of exact color #5BA0F2. The hollow center of the O
stays empty (showing the dark background); the gap stays open. The open O reads as
both the letter O and a crescent moon glowing against a night sky — but render it
FLAT, with no actual glow or gradient.

Style: extremely clean, flat, single solid color per element, NO gradient, NO
glow, NO shadow, NO 3D, NO texture, NO outline stroke around the letters. Crisp
geometric vector. Generous empty dark margin around the wordmark. Centered. The
letters must be perfectly formed, legible, and spelled exactly "Olune" — render
type as clean vector letterforms, not handwriting, not distorted, no extra
characters. Aspect ratio 16:9, the lockup occupying the central third.
```

### Prompt 3 — Favicon / app icon (512px, rounded-square safe area)

```
A 512x512 pixel app icon, flat vector, square format with gently rounded corners
(superellipse / iOS-style squircle, corner radius about 90px). The square plate
is a solid near-white fill of exact color #F9FAFC.

Centered on the plate is a single symbol: an OPEN RING in vivid medium blue of
exact color #2079E8. The ring is a near-complete circle drawn as ONE smooth
stroke of constant thickness (monoline), with the two ends finished in soft
ROUNDED caps. There is a single gap of roughly 52 degrees in the ring on its
lower-right edge, so it reads as an open letter "O" and equally as a crescent
moon. The ring's center is hollow and empty (shows the plate color through it).

Geometry: the ring's centerline radius is about 180px relative to a 512px canvas,
stroke thickness about 64px; the entire symbol sits comfortably inside a centered
safe circle of ~410px diameter with clear empty margin to all edges (safe for
masking/cropping). Perfectly symmetric placement, optically centered.

Style: absolutely minimal, flat, ONE solid blue color for the ring, NO text, NO
letters, NO numbers, NO gradient, NO glow, NO shadow, NO 3D, NO bevel, NO texture,
NO inner second ring. Just the single open blue ring on the rounded near-white
square. Crisp, clean, geometric.
```

> **Dark favicon alternate:** reuse Prompt 3 verbatim but change the plate fill to
> `#080B11` and the ring color to `#5BA0F2`. For a **transparent** icon, omit the
> square plate entirely and request "transparent background, only the open blue
> ring centered in a 512x512 frame."
