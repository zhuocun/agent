# Olune Logo — Richness Charter

> **Status:** Shared design contract. Binding on all three logo workers.
> **Question this file resolves — the only one:** *where may an Olune mark
> become visually richer without violating the principles?*
> **Method:** Every clause cites the canon doc + section it descends from. This
> file does **not** propose concepts and does **not** generate images. It is the
> ledger, the legal color ramp, the flat-steps rule, the depth doctrine, the
> static-vs-motion split, and the final-gate checklist that Concepts A, B, and C
> must each pass.

The incumbent renders were rejected as **too minimal**. That verdict does not
license decoration. It licenses *earned richness* — depth, layered flat fills, a
disciplined value ramp, and atmosphere confined to the surfaces that already
carry it. The pillars stay in force: "when in doubt, subtract"
(`00-principles.md` §The Meta-Rule, lines 154–158). Richness is added **only**
after subtraction has been tried and the mark still reads as thin
(`00-principles.md` §The Meta-Rule, "Add only after the subtraction has been
tried and rejected on its merits," line 158).

The governing reframe is the same one the color foundation already makes: the
minimalism pillar "is asking for less *competition*, not fewer colors"
(`01-foundations.md` §Color → Restraint by chroma, line 31). A mark may hold
more visual information so long as no part of it competes for the eye against the
single accent or the product content it represents.

---

## 1. The ALLOWED / FORBIDDEN richness ledger

Two columns. The left names where a mark may become richer; the right names the
moves that look like richness but are decoration. Each row cites its source.

| ALLOWED — earned richness | FORBIDDEN — decoration in disguise |
| --- | --- |
| **Multiple flat solid fills** of the *same* brand hue at different Lightness steps, hard-edged (layered depth; see §3). Source: depth is a real HIG foundation, `00-principles.md` §High Aesthetics, line 81. | **Any smooth gradient / blend** between two colors or two Lightness values on the mark. Source: "Refuse the gradient-on-button reflex," `00-principles.md` §High Aesthetics, line 88; gradients reserved for welcome atmosphere only, `BRAND_BRIEF.md` §4 Gradients row. |
| **A value ramp within the brand-blue family** (pale → light → brand → deep) used to separate foreground/background planes of the glyph. Source: light/dark hold "the accent stays the same accent, with the OKLCH lightness shifted but the hue unchanged," `01-foundations.md` §Color → Light, dark, and OS-honored modes, line 91. | **A second saturated hue** anywhere in the mark (teal, violet, the welcome warm magenta hue 18). Source: single-accent doctrine, `01-foundations.md` §A single saturated accent, lines 43–63; `03-anti-patterns.md` §A "Second saturated hue alongside the accent," lines 9–13; `BRAND_BRIEF.md` §6 principle 1. |
| **A neutral foreground/background plane** drawn from the canonical neutrals (`--foreground`, `--background`, `--card`) behind or beside the brand element. Source: theme-parity neutrals, `BRAND_BRIEF.md` §1.2; "no pure white / pure black surfaces," `00-principles.md` §Nature, line 66. | **A high-chroma fill plate** behind the mark. Source: `03-anti-patterns.md` §A "High-chroma background fill," lines 21–25; "low-chroma neutral band," line 25. |
| **Geometric layering / overlap / counter-forms** (concentric flat shapes, an inset plane, a constructed-grid counter) that add structural depth. Source: "Geometric and systematic," `BRAND_BRIEF.md` §6 principle 5; "system governs structure," `00-principles.md` §Tension 4, line 136. | **Literal-nature ornament** (leaves, craters on the moon, ripples, hand-drawn marks). Source: "Do not literalize nature," `00-principles.md` §Nature, line 68; `BRAND_BRIEF.md` §6 principle 5. |
| **Soft, diffuse depth cues inside non-exported surfaces only** (welcome/loading), e.g. a single diffuse halo behind the mark on the welcome canvas. Source: warmth lives in material/motion/space, `01-foundations.md` §Color → Restraint by chroma, lines 35–41; atmosphere is welcome-only, `BRAND_BRIEF.md` §1.4 and §4 Gradients row. | **Glow / drop shadow / bevel / 3-D / glass on the exported mark.** Source: glass is chrome-only, `03-anti-patterns.md` §B "Glass material on message bubbles," lines 41–45; flat, no gradients on the mark, `BRAND_BRIEF.md` §6 principle 4. |
| **Rounded-cap, monoline or modulated stroke geometry**, including a heavier or layered stroke, as long as it stays flat and single-hue per element. Source: "Monoline, stroke-based, rounded-cap geometry," `BRAND_BRIEF.md` §6 principle 2 and §3 Existing Mark. | **Decorative dividers, flourishes, ASCII-art, ornament-for-personality** added around the glyph. Source: `03-anti-patterns.md` §G "Decorative dividers, ASCII art, ornament-as-decoration," lines 135–139. |
| **Distinctiveness and atmosphere spent on the welcome / first-run lockup.** Source: "distinctiveness belongs to empty states, transitions, and the first-run moment," `00-principles.md` §Tension 5, line 147. | **Personality / atmosphere bled into the working-surface or exported favicon/OG.** Source: `03-anti-patterns.md` §G "Personality bleeding into the working surface," lines 147–151; `00-principles.md` §Tension 5, line 147. |
| **Tint surfaces (chroma-capped)** as a recognizable but quiet plane — a *tint*, never a hue claim. Source: BYOK precedent, `01-foundations.md` §A single saturated accent, lines 57–59 (see §4). | **Raw hex literals off the token system** in production assets. Source: `03-anti-patterns.md` §A "Raw hex codes in component code," lines 15–19; `01-foundations.md` §Semantic roles, not raw colors. |

**The seam rule for the whole ledger:** richness is allowed only where it adds
*hierarchy or structure*, never where it adds *attention-for-its-own-sake*. This
is the high-aesthetics pillar verbatim — "thoroughness, not ornament"
(`00-principles.md` §High Aesthetics, line 75) — and its resolving rule:
"aesthetic investment goes into typography, spacing, and motion — never
decorative elements" (`00-principles.md` §Tension 2, line 114).

---

## 2. The legal brand-blue value ramp

There is exactly **one** saturated accent and it is the iOS-blue brand at **hue
≈ 247** (`01-foundations.md` §A single saturated accent, lines 43–63;
`BRAND_BRIEF.md` §1.3). A mark may build depth by stepping the *Lightness* of
this one hue — and nothing else. OKLCH is authoritative; hex is the
sRGB approximation per `BRAND_BRIEF.md` (preamble, lines 9–13). The canonical
brand literal `#2079E8` is exact (`BRAND_BRIEF.md` §1.1).

| Step | OKLCH (authoritative) | Hex | Provenance |
| --- | --- | --- | --- |
| **pale** | `oklch(0.95 0.04 247)` | `#E6EFFB` *(approx)* | `--brand-muted` light — the chroma-capped brand tint. `BRAND_BRIEF.md` §1.3 (`globals.css:212`). |
| **light** | `oklch(0.72 0.18 247)` | `#5BA0F2` *(approx)* | `--brand` dark / `--ring` dark — the lightness-lifted brand. `BRAND_BRIEF.md` §1.3, §1.2 (`globals.css:385`, `:383`). |
| **brand** | `oklch(0.59 0.20 247)` | **`#2079E8`** *(exact mark literal)* | `--brand` light — the canonical accent; the only brand hex shipped as a literal. `BRAND_BRIEF.md` §1.1, §1.3 (`globals.css:210`). |
| **deep** | `oklch(0.45 0.18 247)` | `#14539C` *(approx — OKLCH is authoritative)* | Darkened brand for a recessed/background plane; a Lightness step below `brand`, chroma held in the saturated brand band. Derived per the ramp rule below; consistent with the dark-theme brand-muted recession `oklch(0.38 0.11 247)` (`BRAND_BRIEF.md` §1.3, `globals.css:387`). |

### The ramp rule (binding)

1. **Hue is fixed at 247 ± 3.** No step may leave this window. A step that moves
   the hue is a second accent and is forbidden (`01-foundations.md` §A single
   saturated accent, lines 43–63; `03-anti-patterns.md` §A, lines 9–13). The
   neutral hue (~250) and the welcome hues (warm 18, electric 254) are **not** in
   this family and may not appear on the mark (`BRAND_BRIEF.md` §1.2, §1.4, and
   the §1.4 Note, lines 71–75).
2. **Only Lightness varies to create depth.** The four steps differ by their
   OKLCH `L` value (0.95 → 0.72 → 0.59 → 0.45). This is the exact mechanism the
   system already uses across light/dark: "the OKLCH lightness shifted but the
   hue unchanged" (`01-foundations.md` §Color → Light, dark, and OS-honored
   modes, line 91).
3. **Chroma stays within the brand family band.** The saturated steps sit at
   `C ≈ 0.18–0.20` (the brand's own range across light/dark, `BRAND_BRIEF.md`
   §1.3); the `pale` tint step is capped at `C ≈ 0.04`, the system's low-chroma
   tint ceiling (`01-foundations.md` §A single saturated accent, lines 57–59;
   `BRAND_BRIEF.md` §1.6). No step may exceed the brand chroma or fall outside
   this family.
4. **Theme parity, not translation.** Light and dark builds pick the
   corresponding Lightness end of the same hue (brand `0.59` on light canvas,
   `0.72` on dark) so the accent holds equal presence on `#F9FAFC` and `#080B11`
   (`BRAND_BRIEF.md` §6 principle 6; `01-foundations.md` §Light, dark, and
   OS-honored modes, lines 81–97).

Using more than these steps, or stepping by anything other than Lightness, is
out of contract.

---

## 3. Flat-steps-not-gradients rule (for image prompts)

This rule is stated explicitly because it is the single most likely way a "make
it richer" instruction degrades into a forbidden gradient when handed to an image
generator.

> **Layered depth = multiple flat solid fills with hard edges.**
> **A smooth blend is a forbidden gradient.**

Operationally, every image prompt that asks for depth MUST phrase it as discrete,
hard-edged planes drawn from the §2 ramp, and MUST explicitly negate gradients:

- **Say:** "two (or three) **flat solid fills** of the brand blue at different
  lightness steps, each a single uniform color, with a **hard crisp edge**
  between them; no blending."
- **Never say / always negate:** "NO gradient, NO smooth blend, NO fade, NO glow,
  NO shadow, NO 3-D, NO bevel" — the same negation block the existing concept
  prompts already carry (`CONCEPT_A.md` §IMAGE_GENERATION_PROMPT, e.g. lines
  304–305 "NO gradient, NO glow, NO shadow, NO 3D, NO texture").

Source of the prohibition: "Refuse the gradient-on-button reflex … change its
spacing, weight, or position before reaching for color or decoration"
(`00-principles.md` §High Aesthetics, line 88); gradients are "Reserved for
welcome-surface atmosphere only … Buttons/chrome get no gradients — the
'gradient-on-button reflex' is explicitly refused" (`BRAND_BRIEF.md` §4 Gradients
row). A flat step ramp is honest depth; a blend is decoration mimicking depth,
which is dishonest in Rams' sense (`00-principles.md` §High Aesthetics, line 79,
"good design is honest").

---

## 4. The depth doctrine

Depth is **permitted and encouraged** as the answer to "too minimal" — but only
the kind of depth the canon already sanctions.

**Depth is a foundation, not an ornament.** Apple HIG names *depth* as one of the
three foundations alongside deference and clarity, and this product treats it as
"small and earned … used to make hierarchy legible, not to ornament it. Depth is
the only HIG foundation that adds something to the screen; the principle here is
that what it adds is exactly enough hierarchy and no more" (`00-principles.md`
§High Aesthetics, line 81). A mark may therefore carry depth — a foreground plane
over a recessed plane, a counter-form, concentric flat steps — provided each
added plane buys *hierarchy* and stops there.

**Depth is rendered flat, via the value ramp, never via material.** In this
system, depth on a resting surface is expressed by Lightness separation, not by
glow, glass, or shadow: light and dark are "mirrors of the same role taxonomy"
and "the accent stays the same accent, with the OKLCH lightness shifted but the
hue unchanged" (`01-foundations.md` §Light, dark, and OS-honored modes, lines
89–91). Glass and elevation are reserved for chrome and modal surfaces, not for
content or marks (`03-anti-patterns.md` §B, lines 35–51; `01-foundations.md`
§Motion → Choreography of disclosure, lines 283–287). So depth on the mark =
stacked flat steps from §2, with hard edges per §3.

**The BYOK precedent — "a tint, not a hue claim."** The load-bearing precedent
for *how rich a non-primary plane may get* is the BYOK indicator: rather than
shipping a permanent second accent, "the BYOK indicator surface chroma is capped
at the system's low-chroma tint ceiling … so the role is *recognizable* without
becoming a second accent. **It is a tint, not a hue claim.**"
(`01-foundations.md` §A single saturated accent, lines 57–59). Applied to a mark:
any supporting plane added for richness must be a **chroma-capped tint** (the
`pale` step, §2) or a neutral — recognizable, quiet, and subordinate — never a
second saturated statement. A supporting plane that reads as its own color is a
hue claim and is forbidden (`03-anti-patterns.md` §A, lines 9–13;
`BRAND_BRIEF.md` §1.4 Note, lines 71–75).

---

## 5. The static-vs-motion split

Richness that lives in **light and motion** is allowed — but only on the surfaces
that already own atmosphere, and **never** in the exported asset.

- **Atmosphere and animation are permitted on the welcome and loading surfaces
  only.** Distinctiveness "belongs to empty states, transitions, and the
  first-run moment — not the working surface" (`00-principles.md` §Tension 5,
  line 147). The welcome surface is the one place the dual-hue bloom, a diffuse
  halo behind the mark, or a one-shot draw-on of the glyph may live
  (`BRAND_BRIEF.md` §1.4 "welcome screen ONLY"; §4 Gradients row). A draw-on at
  loading is acceptable because motion is bound to a discrete in-progress event
  (`01-foundations.md` §Motion → Cadence and stillness, lines 233–251; the
  shimmer boundary case, line 251).

- **Any such motion resolves to stillness and ships a reduced-motion path.**
  "Motion resolves to stillness" and "Ambient micro-motion in steady state is a
  violation" (`01-foundations.md` §Motion → Cadence and stillness, lines
  239–243). A logo that bobs, breathes, or drifts at rest is the named
  anti-pattern (`03-anti-patterns.md` §C "Ambient motion outside a choreographed
  event," lines 55–59 — "A logo that bobs at rest"). Every motion has a static
  fallback designed at the same time, not retrofitted (`01-foundations.md`
  §Motion → Reduced motion as principle, lines 253–267; `03-anti-patterns.md`
  §C, lines 61–65).

- **The exported favicon, app icon, maskable icon, and OG image are STATIC and
  FLAT — no atmosphere, no animation, no gradient, no glow.** These are
  working/identity assets, and atmosphere on them is "personality bleeding into
  the working surface" (`03-anti-patterns.md` §G, lines 147–151). The mark "must
  read as flat, single-color, and quiet" (`BRAND_BRIEF.md` §6 principle 4). The
  exported icon must also survive maskable safe-zones, `forced-colors`,
  increased-contrast, and 16px favicon scale — none of which tolerate atmosphere
  (`BRAND_BRIEF.md` §6 principle 7).

**One-line split:** *atmosphere and motion may enrich the welcome/loading
moment; the exported mark is always flat and still.*

---

## 6. The 10-point principle checklist (final gate)

The final gate runs every candidate mark against these ten. A single failure
sends the candidate back. Each cites the rule it enforces.

1. **One accent only.** The mark uses brand blue (hue 247 ± 3) and nothing else
   saturated — no second hue, no welcome warm/electric hue. (`01-foundations.md`
   §A single saturated accent, lines 43–63; `03-anti-patterns.md` §A, lines
   9–13; `BRAND_BRIEF.md` §6 principle 1.)
2. **Legal value ramp.** Any depth is built only from the §2 steps
   (pale/light/brand/deep) — Lightness varies, hue fixed at 247 ± 3, chroma
   within the brand family. (`01-foundations.md` §Light, dark, and OS-honored
   modes, line 91; `BRAND_BRIEF.md` §1.3, §1.6.)
3. **Flat steps, no gradients.** All fills are flat and hard-edged; there is no
   smooth blend, fade, glow, shadow, bevel, or 3-D anywhere on the exported mark.
   (`00-principles.md` §High Aesthetics, line 88; `BRAND_BRIEF.md` §4 Gradients
   row; §3 of this charter.)
4. **Depth earns hierarchy.** Each added plane/layer buys structural hierarchy
   and stops there; nothing is added for attention alone; subtraction was tried
   first. (`00-principles.md` §High Aesthetics, line 81; §The Meta-Rule, line
   158; §4 of this charter.)
5. **Supporting planes are tints or neutrals.** Any non-primary plane is a
   chroma-capped tint (`pale`) or a canonical neutral — "a tint, not a hue
   claim." (`01-foundations.md` §A single saturated accent, lines 57–59;
   `BRAND_BRIEF.md` §1.6.)
6. **No literal nature, no ornament.** No leaves/craters/ripples/hand-drawn
   marks; no decorative dividers, flourishes, or personality ornament.
   (`00-principles.md` §Nature, line 68; `03-anti-patterns.md` §G, lines
   135–139; `BRAND_BRIEF.md` §6 principle 5.)
7. **Geometry stays systematic.** Construction is grid-based, monoline /
   stroke-first or clean flat shapes with rounded-cap terminals; structure is
   engineered, not organic-irregular. (`00-principles.md` §Tension 4, line 136;
   `BRAND_BRIEF.md` §6 principle 2, §3.)
8. **Theme parity.** A first-class light build (on `#F9FAFC`) and dark build (on
   `#080B11`) exist with equal intent — mirror, not afterthought; no baked single
   plate. (`01-foundations.md` §Light, dark, and OS-honored modes, lines 81–97;
   `BRAND_BRIEF.md` §6 principle 6, §7.)
9. **Exported asset is static and flat; atmosphere/motion confined to
   welcome/loading.** Favicon/app-icon/maskable/OG carry no atmosphere or
   animation; any motion or bloom lives only on welcome/loading, resolves to
   stillness, and has a reduced-motion fallback. (`00-principles.md` §Tension 5,
   line 147; `03-anti-patterns.md` §C lines 55–59 and §G lines 147–151;
   `01-foundations.md` §Motion, lines 233–267; §5 of this charter.)
10. **Accessible and scalable, tokens not raw hex.** Legible from 16px → 512px,
    survives maskable inset / `forced-colors` / increased-contrast, carries
    `aria-label="Olune"`, opts out of RTL mirroring (`data-no-flip`), and
    production builds reference tokens/`currentColor` rather than stray hex.
    (`BRAND_BRIEF.md` §6 principle 7; `03-anti-patterns.md` §A lines 15–19, §H
    lines 157–161; `01-foundations.md` §Iconography → Color from context, lines
    313–323.)

---

## 7. What this charter does not do

It does not propose, rank, or modify any concept (A "Aperture", B "Crescent +
Satellite Node", C "Antiphon"); those live in their own `CONCEPT_*.md` files. It
does not generate or commission images. It defines the **boundary of allowable
richness** and the **gate**; the three workers design within it, and the final
gate scores against §6.
