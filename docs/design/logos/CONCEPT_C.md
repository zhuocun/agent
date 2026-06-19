# Concept C′ — "Antiphon, voiced" (dialogue motif, medium richness)

> **Supersedes v1 "Antiphon".** Richness levers per `RICHNESS_CHARTER.md`:
> **calligraphic stroke modulation** (thick→thin along serif stress axis) +
> **overlap depth** at one crossing (`deep` `#14539C`).

---

## 1. Concept

Two facing arcs `( )` — call and response — but now with **variable stroke weight**
(thick on flanks, thin at terminals) borrowing Instrument Serif's contrast axis
(P8). The arcs **cross at the lower-left terminus**; the crossing zone is filled
`deep` `#14539C` as a flat interlock (hard edge, no gradient).

**P2 justification:** modulation is not decoration — it imports the wordmark's
thick/thin grammar onto the symbol (`RICHNESS_CHARTER.md` §1 allowed: modulated
stroke, single hue).

App-side call-and-response draw-on animation remains welcome/loading only; exported
assets stay static (`RICHNESS_CHARTER.md` §5).

---

## 2. Geometry (512 grid)

- Right voice: arc r=180, stroke modulates **72px at 3 o'clock → 36px at tips**.
- Left voice: 180° rotation of right voice.
- **Crossing:** lower-left at ~(209, 430); overlap patch = flat `deep` fill, ~24px
  radius, hard edge.
- Gaps at 12 and 6 o'clock preserved (33px clearance).

---

## 3. Color

| Build | Arcs | Crossing |
| --- | --- | --- |
| Light | `#2079E8` | `#14539C` |
| Dark | `#5BA0F2` | `#14539C` |

Single hue family throughout.

---

## 4. Motion (app-side only)

Left arc draws on → right arc responds → settle to static §2 layout.
`prefers-reduced-motion`: static layout, no draw.

---

## IMAGE_GENERATION_PROMPT — Light symbol

```
Flat vector logo on #F9FAFC, square centered. Letter O formed by TWO facing parenthesis-like arcs — left arc "(" and right arc ")" bowing toward each other. Each arc has CALLIGRAPHIC stroke weight: THICK on the outer flanks (about 14% of diameter), THIN at the tips (about 7%) — smooth variation along the curve, like elegant serif stroke contrast. Color vivid brand blue #2079E8.

At the lower-left where the two arcs CROSS, a small flat interlock patch in deeper blue #14539C — HARD crisp edge, two FLAT solid fills, absolutely NO gradient between blues. Gaps at top and bottom so arcs do not touch. NO dot, NO satellite, NO text. Richer and more crafted than even-weight strokes. NO glow, NO shadow, NO 3D.
```

## IMAGE_GENERATION_PROMPT — Dark symbol

```
Same two voiced arcs on #080B11. Arcs #5BA0F2 with calligraphic thick-to-thin modulation. Crossing patch #14539C, hard flat edge. NO gradient/glow.
```

## IMAGE_GENERATION_PROMPT — Favicon

```
App icon #F9FAFC plate. Two facing blue #2079E8 arcs with bolder calligraphic stroke (thick flanks, thinner tips), small deep #14539C crossing at lower-left, gaps top and bottom. No text. Flat, legible at small size.
```
