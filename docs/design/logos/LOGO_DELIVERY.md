# Olune Logo Concepts — Delivery Summary

> Three distinct logo directions for Olune, grounded in
> [`BRAND_BRIEF.md`](../BRAND_BRIEF.md) and the design-principles canon
> (`docs/design/`). Each concept includes a full visual spec, generated
> reference renders, and production notes.

---

## 1. Concept A — "Aperture" (wordmark-led)

**Tagline:** *The O that opens.*

**Lane:** Typographic *Olune* logotype in Instrument Serif 400 with a custom
open-crescent **O**; the favicon reduces to the incumbent monoline open ring.

**Rationale (principles):** Promotes the in-product welcome wordmark to a brand
asset (P8). The single accent lands on the **O** only (P1). The open ring
preserves O/crescent equity (P3) with flat, gradient-free treatment (P4). The
favicon glyph reuses the shipped `icon.svg` geometry at two levels of dress.

**Files**

| Asset | Path |
| --- | --- |
| Full spec | [`CONCEPT_A.md`](./CONCEPT_A.md) |
| Wordmark (light) | [`assets/concept-a/olune-logo-concept-a-wordmark-light.png`](./assets/concept-a/olune-logo-concept-a-wordmark-light.png) |
| App icon (light) | [`assets/concept-a/olune-logo-concept-a-icon-light.png`](./assets/concept-a/olune-logo-concept-a-icon-light.png) |

**Best for:** Brand moments, marketing lockups, welcome-hero continuity.

---

## 2. Concept B — "Crescent + Satellite Node" (symbol-led)

**Tagline:** *One moon, one agent.*

**Lane:** Standalone geometric mark — open monoline crescent with one filled
satellite node at the upper-right gap. Symbol-first; pairs with Instrument Serif
wordmark in lockups.

**Rationale (principles):** Extends the incumbent crescent with exactly one new
primitive — a round node as the agent (P2, P5). Single brand blue throughout
(P1). Static by design; no motion decoration (P4). Strong favicon/app-icon
candidate.

**Files**

| Asset | Path |
| --- | --- |
| Full spec | [`CONCEPT_B.md`](./CONCEPT_B.md) |
| Symbol (light) | [`assets/concept-b/olune-logo-concept-b-symbol-light.png`](./assets/concept-b/olune-logo-concept-b-symbol-light.png) |
| App icon (light) | [`assets/concept-b/olune-logo-concept-b-icon-light.png`](./assets/concept-b/olune-logo-concept-b-icon-light.png) |

**Best for:** Favicon, app icon, avatar, symbol-only contexts.

---

## 3. Concept C — "Antiphon" (dialogue motif)

**Tagline:** *Two voices, one O.*

**Lane:** Two facing monoline arcs — call and response — that close into the
letter **O**. No filled elements; distinct from B's ring-plus-dot.

**Rationale (principles):** Doubles the crescent/O equity with two equal voices
(P3). Expresses Olune's conversational, transparent chat product without
literal speech-bubble illustration (P5). Optional draw-on animation for loading
states; exported assets stay flat (P4, P7).

**Files**

| Asset | Path |
| --- | --- |
| Full spec | [`CONCEPT_C.md`](./CONCEPT_C.md) |
| Symbol (light) | [`assets/concept-c/olune-logo-concept-c-symbol-light.png`](./assets/concept-c/olune-logo-concept-c-symbol-light.png) |
| App icon (light) | [`assets/concept-c/olune-logo-concept-c-icon-light.png`](./assets/concept-c/olune-logo-concept-c-icon-light.png) |

**Best for:** Differentiated symbol identity, motion-enhanced welcome/loading
moments, dialogue-forward brand story.

---

## Comparison at a glance

| | A — Aperture | B — Crescent + Node | C — Antiphon |
| --- | --- | --- | --- |
| **Leads with** | Wordmark | Symbol | Symbol |
| **Standalone glyph** | Monoline open ring | Crescent + dot | Two facing arcs |
| **Filled element** | No | Yes (node) | No |
| **Wordmark font** | Instrument Serif (custom O) | Instrument Serif (plain) | Instrument Serif (plain) |
| **Incumbent continuity** | Highest (reuses `icon.svg`) | High (extends arc) | Moderate (new silhouette) |

---

## Production notes

- Generated PNGs are **reference renders** for review. Production assets should
  be authored as SVG from the geometry in each `CONCEPT_*.md` spec.
- Dark-theme variants (`#080B11` canvas, `#5BA0F2` glyph) and monochrome builds
  are specified in each concept doc but not yet rendered here.
- The repo is missing raster icons referenced by `manifest.ts` / `layout.tsx`;
  whichever concept is chosen should close that gap.
- Confirm the lune/moon etymology with product before leaning marketing copy on
  a literal lunar story (`BRAND_BRIEF.md` §7).

---

## Source documents

- [`BRAND_BRIEF.md`](../BRAND_BRIEF.md) — palette, typography, principles synthesis
- [`docs/design/00-principles.md`](../00-principles.md) — four pillars canon
- [`docs/design/01-foundations.md`](../01-foundations.md) — one-accent doctrine
