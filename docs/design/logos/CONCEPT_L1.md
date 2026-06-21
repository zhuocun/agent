# Concept L1 — "Stack" (layers / aperture-slot)

> **Lane L1** per `DECOUPLING_ADDENDUM.md`. Transparency & depth via **offset
> rectilinear planes** — a vertical lens-notch aperture. **No circles.**

---

## Concept

Three offset rounded-rect planes stacked upper-left → lower-right, each a
different ramp step (`deep` → `brand` → `light`). A vertical **slot** cut
through the stack reveals the canvas — literal "see-through." Reads as layered
context / transparency without spelling anything.

---

## Geometry (512 viewBox)

All three planes share one footprint — `308×328` `rx=26` — staggered by a
constant `46px` step on both axes (down-right), so depth reads from a generous
staircase. The figure is centered in the 512 frame (figure center `(256, 256)`).

- Plane 1 (back): offset `(56, 46)`, `308×328` `rx=26`, fill `deep` `#13539F`
- Plane 2 (mid): offset `(102, 92)`, `308×328` `rx=26`, fill `brand` `#1D7CEC` (dark: `#5BA4F6`)
- Plane 3 (front): offset `(148, 138)`, `308×328` `rx=26`, fill `light` `#5BA4F6` (dark: `#1D7CEC`)
- Slot: a **contained rounded pill** carved through the stack via a group mask
  (the mask reveals the canvas, never a painted bar). Explicit rect
  `x=267 y=209 w=70 h=186 rx=18`, centered on the front plane
  (front center `(302, 302)` = slot center `(302, 302)`), fully inside
  the front footprint on both axes.

### Reconciliation (computed from the coordinates above)

- **Figure bbox**: spans x `56→456` (`400px`, **78.1%** of 512) and y `46→466`
  (`420px`, **82.0%** of 512), centered on `(256, 256)` — i.e. **≥75% of frame**
  on both axes.
- **Plane aspect**: `308:328` (`0.94`) — near-square, marginally portrait.
- **Plane vs figure**: a single plane is `77.0%` wide × `78.1%` tall of the
  figure bbox (≈ **77.5%** combined), so the staggered planes form a clear
  staircase rather than thin slivers.
- **Stagger step**: `46px` on both axes = `14.9%` of plane width / `11.5%` of
  figure width — matching the approved render's staircase depth (~96px stagger
  on a ~644px plane ≈ 14.9% of plane / 11.5% of figure).
- **Slot proportion**: `70×186` = `0.227 × 0.567` of the plane footprint
  (`~0.225 × 0.57`).

---

## Color

| Build | Planes back→front | Background |
| --- | --- | --- |
| Light | `#13539F`, `#1D7CEC`, `#5BA4F6` | `#F9FAFC` |
| Dark | `#13539F`, `#5BA4F6`, `#1D7CEC` | `#080B11` |

---

## IMAGE_GENERATION_PROMPT — Symbol light

```
BOLD flat vector logo square #F9FAFC. Three offset stacked rounded rectangles filling ~78% of frame, poster cutout style: back plane flat deep blue #13539F, middle flat brand blue #1D7CEC, front flat lighter blue #5BA4F6. A vertical rounded SLOT (pill) cut through the stack center reveals background — transparency aperture. HARD crisp edges between each blue plane NO gradient NO blend NO glow NO shadow NO 3D NO circles NO rings NO letter O NO text. Geometric layers symbol. NO gradient, NO blend/fade, NO glow, NO drop-shadow, NO bevel, NO 3-D, NO glass, NO second saturated hue.
```

## IMAGE_GENERATION_PROMPT — Symbol dark (hero)

```
Same stacked planes on flat deep navy #080B11 filling ~78% frame. Back #13539F, mid luminous #5BA4F6, front #1D7CEC. Vertical rounded slot through center. HARD flat edges NO gradient NO glow NO circles NO text. Luminous night-sky presence.
```

## IMAGE_GENERATION_PROMPT — Icon light

```
Squircle #F9FAFC. Simplified three stacked rounded rects ~78% scale with vertical rounded slot, flat blues #13539F #1D7CEC #5BA4F6 HARD edges NO text NO circles.
```

## IMAGE_GENERATION_PROMPT — Icon dark

```
Squircle #080B11. Stacked rects luminous blues flat HARD edges ~78% scale vertical rounded slot NO text.
```

## IMAGE_GENERATION_PROMPT — Welcome dark

```
Welcome screen flat #080B11. Center large stacked-plane symbol flat single-hue blues HARD edges. Canvas: soft electric blue bloom top warm wash bottom BEHIND symbol only glyph flat NO gradient on mark. NO text NO Olune wordmark. Symbol only.
```
