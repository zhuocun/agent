# Concept B′ — "Phase" (symbol-led, boldest richness)

> **Supersedes v1 "Crescent + Satellite Node".** Richness lever per
> `RICHNESS_CHARTER.md`: **depth-by-occlusion** — overlapping discs painted in
> 2–3 flat brand-blue values. Zero smooth gradients.

---

## 1. Concept

Two concentric/overlapping circular forms on a 512 grid. A large **background
disc** (`pale` `#E6EFFB`) sits behind a **foreground eclipse disc** (`brand`
`#2079E8`). Where they overlap, a **deep** `#14539C` crescent-shaped shadow zone
defines the lit/eclipsed boundary. The v1 **agent node** survives as the
occluding satellite body (`brand` fill) at the upper-right gap.

Depth comes **ONLY from flat overlapping shapes in different solid blues** — no
drop-shadow, no glow, no 3D shading.

---

## 2. Charter alignment

| Move | Charter |
| --- | --- |
| 3-value ramp pale/brand/deep | §2 legal ramp, hue 247 |
| Occlusion geometry | §1 allowed: layered flat fills |
| Flat hard zone boundaries | §3 flat-steps rule |
| 16px collapse to open ring | §6 checklist item 10 |

---

## 3. Geometry (512 grid, center 256,256)

| Layer | Shape | Fill |
| --- | --- | --- |
| 1 — Field | Circle r=200 | `pale` `#E6EFFB` |
| 2 — Shadow crescent | Annulus from eclipse: occluder center (320,240) r=185 on field | `deep` `#14539C` |
| 3 — Lit crescent stroke | Open arc r=168, stroke 56, gap upper-right | `brand` `#2079E8` |
| 4 — Agent node | Circle center (393,160) r=42 | `brand` `#2079E8` |

Counter stays open — crescent/O equity preserved.

---

## 4. Color builds

**Light:** pale field, deep shadow zone, brand lit arc + node.
**Dark:** field becomes `deep` tint on `#080B11`; lit arc/node `#5BA0F2`; shadow
`#14539C`.
**Forced-colors:** all planes → `currentColor`, silhouette must remain.

---

## 5. Favicon collapse (≤16px)

Drop pale field and deep zone; render brand open crescent + node only.

---

## IMAGE_GENERATION_PROMPT — Light symbol

```
Flat vector logo on near-white #F9FAFC, square 1:1 centered. A dimensional moon symbol built ONLY from flat overlapping circles in different solid blues — NO gradient, NO glow, NO 3D.

Layers: (1) large soft pale blue circle #E6EFFB as background field. (2) a darker blue #14539C crescent-shaped shadow zone from one disc eclipsing another — HARD flat edge. (3) bright brand blue #2079E8 open crescent ring with gap at upper-right. (4) one solid #2079E8 round satellite dot in the gap. Reads as letter O, crescent moon, and agent node. Geometric, premium, Apple-minimal but RICHER than a single flat stroke. Absolutely NO smooth blends between blues — only hard-edged flat fills.
```

## IMAGE_GENERATION_PROMPT — Dark symbol

```
Same composition on deep navy #080B11. Pale field omitted or very subtle deep blue. Lit crescent and node in luminous #5BA0F2. Shadow zone #14539C. HARD flat edges only, NO gradient/glow.
```

## IMAGE_GENERATION_PROMPT — Favicon

```
Bold app icon on #F9FAFC, squircle plate. Simplified: bright #2079E8 open crescent plus one #2079E8 dot in upper-right gap. Thicker stroke for 16px legibility. Flat, no gradient, no text.
```
