# Concept C — "Antiphon" (the call-and-response O)

> **Lane:** Conversational dialogue motif. The open **"O"** of Olune is split
> into **two facing monoline arcs** — two crescents bowing toward each other like
> two voices in conversation. One arc is the *call*, the other its *response*
> (the same stroke rotated 180°). Together they close into an "O"; apart, they
> read as a dialogue — `( )` embracing, two speech curves answering across the
> centerline. *Antiphon* = a chant sung as call-and-response, one voice answered
> by another.
>
> **Tagline (internal, for the mark — not product copy):** *"Two voices, one O."*
>
> **Status:** Visual spec / generation brief. Grounded in
> `/workspace/docs/design/BRAND_BRIEF.md` (§3 existing mark, §6 principles).

---

## 1. Concept in one breath

The incumbent open ring is **one arc with one gap**. Concept C is **two arcs with
two gaps** — a left crescent open to the right and a right crescent open to the
left, point-symmetric about the center. The eye completes them into the letter
**"O"**; held a beat longer, they separate into **two voices facing each other**
— a question and the answer that comes back. The mark is literally a stroke *and
its echo*: take the right arc, rotate it 180° about the center, and you have the
left arc. Call and response, the same line answering itself. Nothing is added but
a second voice; the gaps are the breath between turns. *When in doubt, subtract.*

**Reads as, in one glance:** the letter **O** → two facing crescents → two
speech curves in dialogue → an open, ongoing exchange that never seals shut.

---

## 2. Why this honors Olune (every decision tied to BRAND_BRIEF §6)

| Brief principle (§6) | How Concept C satisfies it |
| --- | --- |
| **1 — One saturated accent, blue `#2079E8`** | Both arcs are the single brand blue (`#5BA0F2` on dark). No second hue, no gradient, no "two voices in two colors." |
| **2 — Monoline, stroke-based, rounded caps** | Each voice is one `fill:none` arc, even weight, `stroke-linecap:round`. Two strokes, identical DNA to the incumbent open ring — just mirrored. No filled shapes anywhere (no dot, no blob). |
| **3 — "O"/crescent-moon duality is the equity** | The two arcs *close into the "O"*, and **each arc is itself a crescent** — the lune read is doubled, not dropped. The motif amplifies the equity instead of replacing it. |
| **4 — Deference, flat, no gradients** | Flat, single-color, two primitives. The only "depth" is the figure/ground of the facing arcs — no glow, glass, or bevel. |
| **5 — Geometric, systematic, not organic-literal** | Pure circle math on a 512 grid: one radius, one arc, and its 180° rotation. No drawn speech-bubble tail, no hand-drawn quotes — the dialogue is *implied by symmetry*, never illustrated. |
| **6 — Theme parity** | Designed transparent-first (fixes the incumbent's baked light plate, brief §7). Dark build lifts to the dark-brand token `#5BA0F2` for equal presence on `#080B11`. |
| **7 — Accessible + scalable** | Survives maskable inset, `forced-colors`, and the 16px favicon (favicon thickens the stroke and widens the gaps so the two-voice break stays legible; degrades gracefully to a plain open "O"). `aria-label="Olune"`, `[data-no-flip]`. |
| **8 — Serif voice for wordmark** | Lockup wordmark is **Instrument Serif 400, `tracking-tight`** — the in-product display face, never the system sans. |

**Distinct from its siblings:**

- **Concept A ("Aperture")** is *wordmark-led* — a typographic *Olune* with one
  cut-open serif **O**. Concept C leads with a **standalone two-arc symbol** that
  works with zero letterforms.
- **Concept B ("Crescent Orbit")** is **one open crescent + one filled satellite
  dot** at the upper-right. Concept C has **no filled element at all** — it is
  **two equal open arcs**, point-symmetric, gaps top and bottom. There is no
  ring-plus-dot here: nothing orbits, nothing is filled. The signature that
  separates C is **two facing voices**, not a body circling a ring.

---

## 3. Construction & geometry

Built on the **same 512 × 512 grid as the shipped icon** (`web/public/icon.svg`)
so it drops straight into the existing asset pipeline.

```
viewBox          0 0 512 512
center (cx,cy)   256, 256
arc radius (r)   180            (centerline — matches incumbent icon.svg)
stroke-width     60             (incumbent is 64; trimmed slightly so two strokes don't read heavy)
stroke-linecap   round
fill             none           (both arcs — no filled element anywhere)
```

Angles below are measured **clockwise from 12 o'clock** (top). Point on the
centerline circle: `x = 256 + r·sin θ`, `y = 256 − r·cos θ`.

### 3.1 The two voices (two facing arcs)

Two **150° arcs**, mirror-and-rotation of each other, with a **30° gap at the top
(12 o'clock)** and a **30° gap at the bottom (6 o'clock)**. `150 + 150 + 30 + 30
= 360`.

**Right voice** — traces the right side (through 3 o'clock), open toward the
center (a reversed-C, `)`):

| Terminal | Angle (cw from top) | Coordinate (x, y) | On r = 180? |
| --- | --- | --- | --- |
| Start (upper) | 15° | **302.6, 82.1** | ✓ |
| End (lower) | 165° | **302.6, 429.9** | ✓ |

`M 302.6 82.1 A 180 180 0 0 1 302.6 429.9` — `large-arc-flag = 0` (150° < 180°),
`sweep-flag = 1` (clockwise, through 3 o'clock). Round caps.

**Left voice** — the right voice **rotated 180° about (256, 256)**; traces the
left side (through 9 o'clock), open toward the center (a C, `(`):

| Terminal | Angle (cw from top) | Coordinate (x, y) | On r = 180? |
| --- | --- | --- | --- |
| Start (lower) | 195° | **209.4, 429.9** | ✓ |
| End (upper) | 345° | **209.4, 82.1** | ✓ |

`M 209.4 429.9 A 180 180 0 0 1 209.4 82.1` — `large-arc-flag = 0`,
`sweep-flag = 1` (clockwise, through 9 o'clock). Round caps.

All four terminals are verified to land on the radius-180 centerline circle (the
two upper caps share `y = 82.1`, the two lower caps share `y = 429.9`; left/right
pairs are reflections across `x = 256`). The two concave openings face each other
across the vertical centerline → `( )` → two voices in dialogue.

### 3.2 Clearance math (the gaps must stay open)

Cap terminals are circles of radius `stroke/2 = 30`.

| Gap | Cap centers | Center-to-center chord | Edge-to-edge clear |
| --- | --- | --- | --- |
| **Top** (12 o'clock) | `(302.6, 82.1)` ↔ `(209.4, 82.1)` | `93.2` | `93.2 − 2·30 = 33.2` |
| **Bottom** (6 o'clock) | `(302.6, 429.9)` ↔ `(209.4, 429.9)` | `93.2` | `33.2` |

Both gaps stay open by **33.2 units at 512 scale** — the caps never fuse, and the
two arcs are otherwise far apart (left 9-o'clock `x = 76` vs. right 3-o'clock
`x = 436` → 360 units). Outer stroke edge sits at `180 + 30 = 210` from center,
well inside the 256 half-canvas.

**Negative space** is load-bearing three ways: the **counter** (the hollow O), and
the **two gaps** (the breaths between turns). Never fill the counter; never close
either gap.

### 3.3 Optical balance

- The mark is **point-symmetric** (180° rotational symmetry) and **bilaterally
  symmetric about the vertical axis** — it sits dead-still and upright, no implied
  spin. Calm, balanced, resolves to stillness (brief §4 motion ethos), unlike an
  orbit.
- In lockups, optically center on the geometric center `(256, 256)` — there is no
  off-axis mass to compensate for (no dot), so the bounding box and optical
  center coincide.

---

## 4. Color

Single accent only. No gradients, ever. Transparent canvas; the glyph swaps value
by theme (parity, not translation — brief §6.6).

| Context | Both arcs | Background |
| --- | --- | --- |
| **Light** | `#2079E8` (brand literal) | transparent → renders on `#F9FAFC` |
| **Dark** | `#5BA0F2` (dark `--brand`, `oklch(0.72 0.18 247)`) | transparent → renders on `#080B11` |
| **Mono / forced-colors** | `currentColor` (inherits `--foreground`) | transparent |
| **One-color print** | `#2079E8` on white, or solid foreground on tints | per medium |

- The two voices are **always the same single color** — they are one system in
  dialogue, not two hues. Coloring the arcs differently would invent a second
  permanent brand hue and break the one-accent law (brief §1.4, §6.1).
- **Pixel-exact builds:** prefer the OKLCH tokens (`--brand` light
  `oklch(0.59 0.20 247)` / dark `oklch(0.72 0.18 247)`); `#2079E8` / `#5BA0F2`
  are the established **static-asset** literals (brief §7).

---

## 5. Sizing, clear space & favicon

- **Clear space:** keep ≥ **one stroke-width (60 units @512)** of empty space on
  all sides of the mark's bounding box; in lockups the same unit sets the gap to
  the wordmark ("Ma" — charged emptiness, brief §4).
- **Minimum symbol size:** master mark ≥ **24px**; with wordmark ≥ **120px** wide.
  Below ~24px use the favicon variant (below).
- **Maskable (`icon-maskable.svg`):** scale the whole composition into the
  inset core — centerline **r = 144**, **stroke 48**, gaps held at 30°. Endpoints:
  right voice `(293.3, 116.9)`→`(293.3, 395.1)`, left voice `(218.7, 395.1)`→
  `(218.7, 116.9)`. Top/bottom gap chord `74.6`, clear `74.6 − 48 = 26.6`. Outer
  edge `144 + 24 = 168`, comfortably inside the ~205 maskable safe circle (the
  central 80% of 512). Verified inside the safe zone.
- **Favicon / ≤ 32px:** preserve the **two-voice read**, drop nothing else:
  - Centerline **r = 180**, **stroke 64** (back to incumbent weight for punch),
    **gaps widened to ~40°** so the breaks survive shrinking.
  - Endpoints: right voice `(317.6, 86.9)`→`(317.6, 425.1)`, left voice
    `(194.4, 425.1)`→`(194.4, 86.9)`. Top/bottom gap chord `123.2`, clear
    `123.2 − 64 = 59.2` @512 (≈ 1.85px at 16px) — the two arcs stay visibly apart.
  - **Degradation ladder:** full two-arc mark → favicon (thicker, wider gaps) →
    if the top/bottom gaps close at sub-pixel sizes it collapses to the incumbent
    open **"O"**, which is still a legitimate Olune mark. No information that
    *only* exists in color or animation.

---

## 6. Wordmark lockup

- **Logotype:** `Olune` set in **Instrument Serif, weight 400**, `tracking-tight`
  (`-0.006em`), color `--foreground` (`#23262B` light / `#F2F3F4` dark) — exactly
  the in-product welcome wordmark (brief §2, §8).
- **Horizontal lockup:** mark at left; cap-height of `Olune` ≈ **0.62 ×** the
  mark's bounding height; gap between mark and word ≈ one stroke-width (60).
  Baseline of the word aligns to the mark's vertical center `(y = 256)`.
- **Stacked lockup:** mark centered above, `Olune` centered below, gap ≈ one
  stroke-width. Preferred for square / social contexts.
- **Optical tie-in, not cleverness:** the lowercase **"o"** in *Olune* quietly
  rhymes with the round mark. Do **not** redraw the wordmark's "O" into two arcs —
  the symbol carries the dialogue; the wordmark stays plain serif so the two
  equities don't compete (deference over decoration, brief §6.4).

---

## 7. Motion (optional, app-side only — never baked into assets)

Concept C carries a quiet **call-and-response** animation for live surfaces
(loading state, idle welcome mark). The **exported logo asset stays static and
flat**; animation is a CSS/SVG enhancement, never inside the favicon or social
image.

- **Idle / load:** the **left voice (call) strokes on first**, then the **right
  voice (response) strokes on** a beat later, using a brand spring curve
  (`--ease-ios-*` / `--ease-welcome`, `globals.css:109–133`), settling into the
  static §3 layout and resting. One exchange, then stillness — choreographed,
  resolves to quiet (brief §4).
- **Conversational read in motion:** call → response → settle = one turn of
  dialogue. Never loops forever in the steady state.
- **`prefers-reduced-motion`:** first-class — both arcs render **statically** in
  the §3 layout, identical silhouette, no motion.
- **No motion decoration:** no trails, blur, glow-sweeps, or gradients — the
  strokes simply draw and stop.

---

## 8. Accessibility & robustness

- `role="img"`, `aria-label="Olune"`; decorative instances `aria-hidden`.
- `[data-no-flip]` — opt out of RTL mirroring; the mark is symmetric so it would
  look unchanged, but the attribute keeps behavior explicit (`globals.css:584–586`).
- **`forced-colors` / Windows high-contrast:** both arcs switch to `currentColor`
  (→ `CanvasText`); the two-voice silhouette survives because contrast comes from
  shape, not hue.
- **`prefers-reduced-transparency` / `prefers-contrast`:** nothing to strip — the
  mark is already flat, no glass, no glow.
- **Contrast:** `#2079E8` on `#F9FAFC` and `#5BA0F2` on `#080B11` both clear
  non-text-graphic contrast on each canvas.

---

## 9. Do / Don't

**Do**
- Keep both arcs the **same single blue**, equal weight, equal length.
- Keep both gaps open (top and bottom) — they are the breaths that make it two
  voices, not a broken ring.
- Preserve the "O" / crescent read (each arc is a crescent; together an O).
- Convey dialogue through the **facing-arc symmetry** + optional draw-on motion.

**Don't**
- ❌ Add a filled dot, node, or satellite — that is **Concept B**, not C. There is
  no filled element here.
- ❌ Add a second hue, a gradient, a glow, a glass, a bevel, or a shadow.
- ❌ Draw a literal speech-bubble tail, comet tail, or hand-drawn quote marks.
- ❌ Close the arcs into a solid ring, or fill the counter.
- ❌ Let the two voices touch or merge at the top/bottom gaps.
- ❌ Tilt, skew, or rotate the mark off the upright vertical axis.
- ❌ Redraw the wordmark's "O" to mimic the two arcs.

---

## 10. SVG reference (light theme, master)

Illustrative — production should re-derive from the §3 parameters and add the
theme-swap + `aria` / `data-no-flip` attributes.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"
     role="img" aria-label="Olune" data-no-flip>
  <!-- right voice: 150° arc, right side, open toward the center (response) -->
  <path d="M 302.6 82.1 A 180 180 0 0 1 302.6 429.9"
        fill="none" stroke="#2079E8" stroke-width="60" stroke-linecap="round"/>
  <!-- left voice: the right voice rotated 180° about (256,256) (call) -->
  <path d="M 209.4 429.9 A 180 180 0 0 1 209.4 82.1"
        fill="none" stroke="#2079E8" stroke-width="60" stroke-linecap="round"/>
</svg>
```

Dark theme: swap both `#2079E8` → `#5BA0F2`. Maskable: inset to r = 144 /
stroke 48 per §5. Favicon: r = 180 / stroke 64 / gaps ~40° per §5.

---

## 11. IMAGE_GENERATION_PROMPT — Light background (master, light theme)

```
A minimalist, flat vector app logo on a solid very-light cool-gray background (#F9FAFC), centered, with generous empty padding.

THE MARK: a single letter "O" drawn as TWO separate facing arcs — NOT one ring, NOT a ring with a dot. Picture a circle split into a left half and a right half: a left arc that bows out to the left (like an opening parenthesis "(") and a right arc that bows out to the right (like a closing parenthesis ")"), the two arcs facing each other across the vertical center. Each arc is a smooth monoline stroke of EVEN thickness (about 12% of the circle's diameter) in pure brand blue (#2079E8), with soft ROUND line-cap terminals at both ends. Between the two arcs there is a clean GAP at the very top (12 o'clock) and an equal clean GAP at the very bottom (6 o'clock) — each gap about 30 degrees wide — so the two arcs never touch. The two arcs are mirror images and together complete the shape of the letter "O".

MEANING (for composition, do not render text): the two facing arcs read as two voices in conversation — a call and its response — that together form an open "O" and a pair of facing crescent moons.

STYLE: completely flat, ONE solid color (#2079E8), no fill inside the arcs, no gradient, no glow, no shadow, no 3D, no bevel, no texture, no dot, no node, no satellite, no speech-bubble tail, no extra shapes, no text. Crisp geometric vector, perfectly symmetric, upright (gaps exactly at top and bottom), optically centered on a 1:1 canvas with breathing room. Calm, quiet, premium — Apple-HIG / Dieter Rams minimalism.
```

## 12. IMAGE_GENERATION_PROMPT — Dark background (master, dark theme)

```
A minimalist, flat vector app logo on a solid deep-navy near-black background (#080B11), centered, with generous empty padding.

THE MARK: a single letter "O" drawn as TWO separate facing arcs — NOT one ring, NOT a ring with a dot. A left arc that bows out to the left (like an opening parenthesis "(") and a right arc that bows out to the right (like a closing parenthesis ")"), the two arcs facing each other across the vertical center. Each arc is a smooth monoline stroke of EVEN thickness (about 12% of the circle's diameter) in a soft luminous sky-blue (#5BA0F2), with soft ROUND line-cap terminals at both ends. There is a clean GAP at the very top (12 o'clock) and an equal clean GAP at the bottom (6 o'clock), each about 30 degrees wide, so the two arcs never touch. The arcs are mirror images and together complete the letter "O".

MEANING (for composition, do not render text): two facing arcs = two voices in conversation, call and response, that together form an open "O" and a pair of facing crescent moons against a night sky.

STYLE: completely flat, ONE solid color (#5BA0F2) on the deep navy, no fill inside the arcs, no gradient, no glow, no halo, no shadow, no 3D, no bevel, no texture, no dot, no node, no satellite, no tail, no extra shapes, no text. Crisp geometric vector, perfectly symmetric, upright (gaps exactly at top and bottom), optically centered on a 1:1 canvas with ample margin. The blue should feel quietly luminous against the navy, equal in presence to the light-theme version (theme parity, not an afterthought).
```

## 13. IMAGE_GENERATION_PROMPT — Favicon / app-icon (small-size, simplified)

```
A tiny-size app icon / favicon, flat vector, optimized to stay legible from 16px to 512px. Square 1:1 canvas with a very-light cool-gray background (#F9FAFC) and modest rounded-square padding (keep all art inside the central ~80% safe circle for maskable icons).

THE MARK: a letter "O" built from TWO separate facing arcs — a left arc bowing left ("(") and a right arc bowing right (")") facing each other across the vertical center. For small-size clarity the stroke is BOLDER (about 13% of the circle diameter) and the two GAPS — one at the top (12 o'clock), one at the bottom (6 o'clock) — are a little WIDER (about 40 degrees each) so the two arcs stay clearly separated when shrunk. Both arcs are pure brand blue (#2079E8) with ROUND line-cap terminals at every end. No fill inside.

STYLE: completely flat, ONE solid color (#2079E8), no gradient, no glow, no shadow, no 3D, no dot, no node, no satellite, no tail, no text, no extra detail. Maximum clarity at small sizes: the icon must read as "an O made of two facing arcs." Geometric, crisp, perfectly symmetric, upright, centered. If shrunk so far that the top and bottom gaps disappear, it should gracefully simplify into a plain open "O" ring.
```

---

## 14. Asset deliverables (to close brief §7 gaps)

Produce from the finalized vector: transparent master SVG (light + dark color
variants), `icon.svg` / `icon-maskable.svg` / `apple-touch-icon.svg` updates,
the missing rasters (`icon-192.png`, `icon-512.png`, `icon-maskable-512.png`,
`apple-touch-icon.png`), splash assets, and an `opengraph-image` using the
stacked lockup on the theme background. The call-and-response animation (§7)
ships as a separate CSS/SVG component for loading / idle states only — never
inside the exported icon or social image.
