# Concept A′ — "Aperture, lit" (wordmark-led)

> **Supersedes v1 "Aperture".** Richness levers per `RICHNESS_CHARTER.md`: full
> Instrument Serif craft + **phase-crescent monogram** (two flat brand-blue
> values, hard terminator — no gradient).
>
> **Tagline:** *The O that opens — and catches light.*

---

## 1. Concept

*Olune* in Instrument Serif 400 with full thick/thin contrast on every letter.
The capital **O** is a **phase crescent**: a lit limb (`brand` `#2079E8`) and a
shadow limb (`deep` `#14539C`) divided by a circle-intersection terminator — two
**flat solid fills, hard crisp edge, absolutely NO gradient/blend** between them
(`RICHNESS_CHARTER.md` §3).

The favicon monogram uses the same phase geometry at icon scale.

---

## 2. Charter alignment

| Move | Charter / principle |
| --- | --- |
| Two-value phase O | §2 ramp: `brand` + `deep`, hue 247 only |
| Flat hard terminator | §3 flat-steps-not-gradients |
| Full serif contrast on wordmark | P8 high aesthetics / typography craft |
| No glow on export | §5 static-vs-motion split |

---

## 3. Phase monogram geometry (512 grid)

- Center `(256, 256)`, outer radius `180`.
- **Lit disc:** full circle fill `brand` `#2079E8`.
- **Shadow disc:** second circle center `(310, 256)`, radius `175`, fill `deep`
  `#14539C` — occludes the right portion, leaving a crescent lit limb on the left.
- **Open gap:** lower-right arc removed (52° gap) per incumbent `icon.svg` gesture.
- Terminator = intersection of the two circles — a pure geometric edge, not hand-drawn.

Wordmark **O**: same phase construction inside the serif bowl envelope; `lune` in
`#23262B` light / `#F2F3F4` dark.

---

## 4. Color (light / dark)

| Element | Light | Dark |
| --- | --- | --- |
| Lit limb | `#2079E8` | `#5BA0F2` |
| Shadow limb | `#14539C` | `#14539C` (deep holds on navy) |
| Wordmark text | `#23262B` | `#F2F3F4` |
| Canvas | transparent / `#F9FAFC` | transparent / `#080B11` |

---

## 5. Scalability

- **≥32px:** full phase visible.
- **16px favicon:** collapse to single-value open ring `#2079E8` (degradation ladder).

---

## IMAGE_GENERATION_PROMPT — Light wordmark

```
Minimalist flat vector horizontal wordmark "Olune" on near-white #F9FAFC. High-contrast Instrument Serif: capital O then lowercase lune, full thick/thin serif contrast on every letter, tracking tight. Letters l,u,n,e in dark #23262B.

The capital O is a PHASE CRESCENT MOON: the left portion is vivid brand blue #2079E8 (lit limb), the right portion is deeper blue #14539C (shadow limb). Two FLAT solid fills with a HARD CRISP geometric edge between them — absolutely NO gradient, NO blend, NO glow, NO shadow. The O also has a small open gap on lower-right like a crescent. Hollow center empty.

Flat vector only. Spell exactly "Olune". Centered, generous margin. 16:9.
```

## IMAGE_GENERATION_PROMPT — Dark wordmark

```
Same as light wordmark but background deep navy #080B11. Text #F2F3F4. Phase O: lit limb sky-blue #5BA0F2, shadow limb deep #14539C. Two FLAT solid fills, HARD edge, NO gradient/glow. Open lower-right gap on O.
```

## IMAGE_GENERATION_PROMPT — Light favicon (phase monogram)

```
512x512 app icon, rounded squircle corners, plate #F9FAFC. Centered phase-crescent symbol: left lit portion flat #2079E8, right shadow portion flat #14539C, HARD crisp terminator edge between them, NO gradient. Small open gap lower-right. Crescent moon / letter O. NO text. Flat vector, no glow, no 3D.
```

## IMAGE_GENERATION_PROMPT — Dark favicon

```
Same phase-crescent monogram on #080B11 plate. Lit limb #5BA0F2, shadow #14539C. HARD flat edge, NO gradient. No text.
```
