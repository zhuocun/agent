# Olune Logo — Constraint Sheet & Concept Briefs (decoupled slate)

> **Status:** Direction synthesis — revision pass (Worker B). Reviewer verdict on
> the prior O/crescent slate: **REVISE**. Plan/spec only — no image generation here.
> **Inputs (ground truth):** `BRAND_BRIEF.md` §1–§7, as **amended** by
> `logos/DECOUPLING_ADDENDUM.md` (ignore the name; escape circular/O motifs),
> `logos/RICHNESS_CHARTER.md` (earned richness + final gate), and
> `logos/LOUDNESS_ADDENDUM.md` (measurable loudness levers). Where the addenda
> conflict with the original brief, **the addenda win** — most notably the brief's
> §6.3 "O / crescent duality is the equity," which is **retired** (see C3).
> **Purpose:** A non-negotiable, scoreable constraint sheet a reviewer can mark
> against, plus the concept briefs that survive those constraints.

---

## Part 0 — What changed in this revision (read first)

The previous constraint sheet locked the **crescent-O lineage** and carried a
"stacked-layers" continuity hedge. The decoupling directive overturns that:

1. **C3 is flipped.** It no longer *preserves* the O/crescent duality — it now
   **forbids** circular-dominant silhouettes and any read of the name "Olune."
   Enforces `DECOUPLING_ADDENDUM` gate items **16–18**.
2. **Loudness gates added.** New hard lines for **scale ≥ 75%**, **weight
   ≥ 88/512 (or solid mass)**, and **value contrast ΔL ≥ 0.14**, from
   `LOUDNESS_ADDENDUM` (the prior slate was rejected as *too quiet*).
3. **C2 loosened.** Monoline is no longer mandatory. A **solid filled mass** is
   now an allowed alternative to a heavy stroke, so loudness levers can be met
   without thin slivers. Rounded geometry + flat single-hue per element still
   bind.
4. **Concepts replaced.** The locked directions are now **L2 Bracket**,
   **L3 Fork**, and **L4 Lattice** — all symbol-led and non-circular.
5. **L1 is out.** **L1 "Stack" (the layers/aperture-slot lane) is the current
   bad shipped mark** — the rejected incumbent. It is *not* carried forward and
   *not* scored. It appears below only as the explicit "what we are moving away
   from" baseline so the reviewer can confirm the break on the record.

---

## Part 1 — Constraint Sheet (scoreable)

Every candidate mark is scored against the hard constraints below, distilled from
`BRAND_BRIEF.md §6` as amended by the three addenda. **Each C-line is PASS /
FAIL** — these are gates, not preferences. A concept that fails any **C-line** is
out, regardless of how it scores elsewhere. The **Q-lines** (quality modifiers)
are scored 0–2 and break ties between passing concepts.

### Hard gates (PASS / FAIL — all must PASS)

| # | Constraint | What a reviewer checks | Source |
| --- | --- | --- | --- |
| **C1** | **One accent, and it is brand blue.** | Mark uses **only** the brand hue ~247 — `#2079E8` (exact mark literal) / `--brand` OKLCH `0.59 0.20 247` light · `0.72 0.18 247` dark — plus optional neutral foreground/background and the chroma-capped `pale` tint. **No second saturated hue** (esp. the welcome-only warm magenta hue 18, electric 254). | §6.1; `RICHNESS_CHARTER` §1–§2 |
| **C2** | **Geometric, flat, rounded — heavy enough to register.** | Construction is grid/compass-based with **`stroke-linecap: round`** terminals. Each element is **one flat fill of a single hue step** (no per-element gradient). Form is built from **either** an even **monoline of sufficient weight** **or** a **solid filled mass** — *loosened from the old monoline-only rule so loudness (C9–C10) can be met*. No sharp/spiky corners; no decorative ornament. | §6.2, §3; `RICHNESS_CHARTER` §1 ("heavier or layered stroke … fuller fills"); `LOUDNESS_ADDENDUM` Weight lever |
| **C3** | **Non-circular & name-decoupled.** *(FLIPPED — supersedes old "O/crescent duality")* | The mark must **not** read as the letter **O**, must **not** spell or imply "Olune," and must **not** default to **ring / disc / open-arc / crescent / moon / circle-dominant / circular-aperture** silhouettes. It must be **symbol-led** (wordmark optional, secondary) and **lane-distinct at 32px**. Enforces `DECOUPLING` gates **16** (no circular-dominant silhouette), **17** (name-decoupled, symbol-led), **18** (lane-distinct at 32px). | `DECOUPLING_ADDENDUM` §1, §2, §5 (16–18) |
| **C4** | **Flat — no gradients, glows, or glass on the mark.** | Single flat color per plane. No smooth blend/fade, no gradient, no drop shadow, no bevel, no 3-D, no backdrop blur on the **exported** mark. Atmosphere/glass is welcome-/loading-chrome only. | §6.4; `RICHNESS_CHARTER` §3, §5; `LOUDNESS_ADDENDUM` ceiling block |
| **C5** | **Geometric, not organic-literal.** | Constructed from grid/compass geometry (precise angles, offsets, lattice spacing). **No** literal nature (craters, leaves, ripples), **no** hand-drawn wobble. "Nature" enters only via system geometry, never motif. | §6.5; `RICHNESS_CHARTER` §1, §6.6 |
| **C6** | **Theme parity on both canvases.** | Holds with **equal intent** on light `#F9FAFC` **and** dark `#080B11`. Delivered **theme-aware or transparent** — **no baked light plate.** | §6.6, §7; `RICHNESS_CHARTER` §6.8 |
| **C7** | **Accessible & scalable.** | Survives maskable safe-zone inset (radius ≤144 on 512 canvas), `forced-colors`, `prefers-contrast`, RTL via `[data-no-flip]` (no mirroring), and stays legible **16px → 512px** without clogging or vanishing. Carries `aria-label="Olune"`. | §6.7; `RICHNESS_CHARTER` §6.10 |
| **C8** | **Symbol-led; serif wordmark voice (if a logotype ships).** | Concepts are **symbol-only by default.** Any accompanying wordmark is **secondary** and set in **Instrument Serif, weight 400, `tracking-tight`** — never the system sans, never the lead. Mark and wordmark may ship independently. | §6.8; `DECOUPLING_ADDENDUM` §2 |
| **C9** | **Loud — scale.** | The figure occupies **≥ 75%** of the live area (with the maskable safe-zone still respected). No timid ~50% float. | `LOUDNESS_ADDENDUM` Scale lever (rubric 11) |
| **C10** | **Loud — weight / mass.** | Stroke **≥ 88/512**, **or** a **solid filled mass** of equivalent presence. **No thin slivers.** (Pairs with the C2 loosening.) | `LOUDNESS_ADDENDUM` Weight lever (rubric 12) |
| **C11** | **Loud — value contrast.** | If depth/layering is used, ≥ 2 ramp steps with OKLCH **ΔL ≥ 0.14** (e.g. `brand` 0.59 vs `deep` 0.45). The `pale` step is **canvas-side only**, never the primary mass. | `LOUDNESS_ADDENDUM` Value-contrast lever (rubric 13); `RICHNESS_CHARTER` §2 ramp |
| **C12** | **Dark luminous hero delivered.** | A first-class dark build on navy `#080B11` using the lifted light step `#5BA0F2` / `oklch(0.72 0.18 247)` is **mandatory** (not an afterthought of the light build). | `LOUDNESS_ADDENDUM` Dark luminous parity (rubric 14); §6.6 |

> **Atmosphere fence (rubric 15, enforced via C4):** any bloom/halo/draw-on lives
> on the **welcome/loading** surface only and resolves to stillness with a
> reduced-motion fallback; the exported mark is always flat and still.

### Quality modifiers (score 0 / 1 / 2 — tie-breakers among passing concepts)

| # | Modifier | 0 | 1 | 2 |
| --- | --- | --- | --- | --- |
| **Q1** | Concept legibility (does the lane idea read?) | Reads as nothing / generic | Reads with effort | Instant, unmistakable lane read |
| **Q2** | Geometric rigor / "engineered" feel | Loose, eyeballed | Mostly on-grid | Fully compass/grid-constructed, Linear-grade |
| **Q3** | Favicon survival (16–32px) | Collapses/muddy | Legible but soft | Crisp, unmistakable silhouette |
| **Q4** | Theme symmetry | One theme clearly favored | Both fine, minor imbalance | Mirror-equal intent both themes |
| **Q5** | Distinctiveness vs. prior O marks & category | Reads circular / generic AI orb | Recognizably different | Clear, ownable, category-breaking |
| **Q6** | Maskable / safe-zone headroom | Touches edges | Fits with little margin | Comfortable inset, no clipping |
| **Q7** | Loudness headroom (beyond the C9–C12 floor) | Just clears the floor | Comfortably loud | Commands the frame, still disciplined |

### Reviewer scorecard template

```
Concept: __________________________
Hard gates:  C1 [ ]  C2 [ ]  C3 [ ]  C4 [ ]  C5 [ ]  C6 [ ]
             C7 [ ]  C8 [ ]  C9 [ ]  C10 [ ]  C11 [ ]  C12 [ ]
             (any FAIL ⇒ rejected)
Quality:     Q1 _  Q2 _  Q3 _  Q4 _  Q5 _  Q6 _  Q7 _   /14
Verdict:     PASS-ALL-GATES?  ___    Quality total ___/14
```

### Standing assumptions (apply to all concepts)

- **The name is ignored on purpose.** Per `DECOUPLING_ADDENDUM` §1, the mark must
  not spell or imply "Olune" and must not lean on the (always-inferred, never
  documented) moon/"lune" etymology. The crescent equity is **retired for this
  slate** — C3 enforces this. `aria-label="Olune"` still ships for a11y (C7).
- **Three anti-overlap lanes.** Concepts must stay lane-distinct (C3 / gate 18).
  The lane definitions below derive from `DECOUPLING_ADDENDUM` §4, extended with
  the **Lattice** lane for this slate.

| Lane | Meaning | Silhouette | Forbidden |
| --- | --- | --- | --- |
| **L2** Dialogue / Brackets | Multi-model exchange, call-and-response | Paired angular chevrons / brackets `‹ ›` | Oval bubble, circle, arc-ring |
| **L3** Routing / Path | Model routing, choice, agentic flow | Single branching monoline (Y-fork) | Circular hub/O, orbital ring |
| **L4** System / Lattice | Composable structure, the system as a grid | Interlocking rectilinear grid / mesh node | Ring, disc, crescent, circular aperture |

> **L1 (Layers / Aperture-slot — "Stack")** is the **current bad shipped mark**
> and the rejected incumbent. It is **omitted from the scored slate**; see Part 2
> for why it is the baseline we are leaving, not a candidate.

---

## Part 2 — Locked Directions (3 concepts) + the rejected baseline

Three symbol-led, non-circular directions are carried forward. All clear C1–C12
by construction; the review scores them head-to-head on Q1–Q7.

---

### REJECTED BASELINE — L1 "Stack" (current shipped mark — DO NOT ADVANCE)

> **Not a candidate.** This is the mark currently in production and the reason for
> the redraw. Listed so the reviewer can confirm the break on the record.

**What it is.** The layers / aperture-slot lane — offset rectilinear planes with a
lens-notch reading as "transparency / stacked depth." It was the prior slate's
recommended lead.

**Why it is out.**
- **Reads quiet / generic** — it floats small and thin and does not command the
  frame (fails the spirit of C9–C10; the very defect `LOUDNESS_ADDENDUM` names).
- **Aperture-slot drifts circular** — the slot reads as a circular aperture at
  small sizes, brushing the C3 / gate-16 prohibition.
- It is the **incumbent we are explicitly moving away from**; carrying it forward
  would re-anchor the identity on the mark under review.

**Action:** reject on record; do not score.

---

### CONCEPT L2 — "Bracket" (dialogue / exchange)

**Design hypothesis.** Build the mark from a **paired set of angular brackets /
chevrons** — `‹ ›` — that read as **call-and-response between models**. The two
forms face each other across a center gap, framing an implied exchange. This is
the dialogue lane: the product is a *conversation between multiple models*, and
the bracket pair is the most direct, non-circular way to say "exchange" without an
oval speech bubble.

**Why it fits the gates.**
- **C1/C4:** one flat blue per element, no gradient. ✔
- **C2/C10:** the brackets are drawn as a **heavy stroke (≥88/512)** *or* as
  **solid filled wedges** — the loosened C2 lets the wedge option satisfy the
  weight/mass floor without thin slivers. Rounded-cap terminals. ✔
- **C3:** angular, paired, **not circular**; no O/crescent read; symbol-led; the
  two-wedge silhouette is instantly distinct at 32px. ✔ (gates 16–18)
- **C5:** pure constructed angles on a grid — engineered, never organic. ✔
- **C9:** the bracket pair spans **≥75%** of the frame, gap centered. ✔
- **C11/C12:** optional depth via two flat steps (`brand` over `deep`, ΔL ≥0.14)
  to separate the two brackets; mandatory dark luminous build on `#080B11` with
  `#5BA0F2`. ✔

**The risk it tests.** *Can "dialogue" read without a bubble?* The danger is the
bracket pair reading as generic `< >` code chevrons (a category cliché) rather
than a distinctive exchange mark — Q1/Q5 are where this is won or lost. Tune the
angle, weight, and gap so the pair feels like two parties, not punctuation.

**Light / dark intent.** Transparent asset; `--brand` `#2079E8` on `#F9FAFC`,
lifted `#5BA0F2` on `#080B11`. Mirror intent, no favored theme. Under
`forced-colors`, falls back to system color cleanly.

---

### CONCEPT L3 — "Fork" (routing / path)

**Design hypothesis.** A **single branching monoline** — one path entering and
splitting into a **Y-fork** — that reads as **model routing / choice / agentic
flow.** The junction is a clean angular diamond (not a circular hub). This lane
says the product *routes the request to the right model*: one input, a decision
point, multiple paths.

**Why it fits the gates.**
- **C1/C4:** single flat blue stroke, flat. ✔
- **C2/C10:** monoline at **≥88/512** weight with rounded caps — heavy enough to
  clear the weight floor; no thin slivers. ✔
- **C3:** a branching path is **inherently non-circular**; the **diamond junction
  is explicitly not a ring/hub** (gate 16); symbol-led; the Y silhouette is
  unmistakable at 32px. ✔ (gates 16–18)
- **C5:** constructed angles and equal limbs on a grid. ✔
- **C9:** the fork fills **≥75%** of the live area. ✔
- **C11/C12:** if the two output limbs are stepped in value (ΔL ≥0.14) to show
  "choice," it stays inside the ramp; mandatory dark luminous build. ✔

**The risk it tests.** *Can a monoline fork stay loud and distinct at 16px?* Thin
branching strokes are the first thing to clog or vanish at favicon scale
(Q3 risk), and a Y can read as a generic "merge/branch" git glyph (Q5 risk). The
heavy-weight requirement (C10) and a tuned junction are the mitigations.

**Light / dark intent.** Transparent; same `--brand` mapping as L2. The junction
diamond stays a stroke counter (not a filled disc) so it never drifts circular on
either canvas.

---

### CONCEPT L4 — "Lattice" (system / composable structure)

**Design hypothesis.** An **interlocking rectilinear lattice** — a small grid /
mesh of nodes and connectors — that reads as **the system itself: composable,
structured, engineered.** This is the loudest lane by mass: a tight lattice block
is a **solid, high-presence silhouette** that exploits the C2 loosening (filled
mass) and the value ramp (C11) to register depth between lattice planes. It says
Olune is a *structured system of parts*, not a single orb.

**Why it fits the gates.**
- **C1/C4:** one brand hue across the lattice; depth comes from **flat value
  steps**, never a gradient. ✔
- **C2/C10:** the lattice is **solid filled mass** (the loosened C2 path) — the
  single loudest, least-sliver option; corners rounded, not spiked. ✔
- **C3:** rectilinear grid / mesh — **categorically non-circular**; no ring/disc
  aperture (the forbidden L1 traits); symbol-led; reads as structure at 32px. ✔
  (gates 16–18)
- **C5:** the most overtly *systematic* lane — grid geometry is the whole point. ✔
- **C9:** the lattice block commands **≥75%** of the frame. ✔
- **C11:** lattice planes separated by **ΔL ≥0.14** (`brand` over `deep`) for
  honest stepped depth; `pale` stays canvas-side. **C12:** dark luminous build on
  `#080B11`. ✔

**The risk it tests.** *Can a grid survive favicon scale without turning to
mush?* A dense lattice is the highest-risk concept on Q3 (16–32px clogging) and
on C7 (maskable inset clipping a wide grid). Keep the node count low and the
spacing generous; verify the mesh stays readable at 16px and inside the safe-zone.

**Light / dark intent.** Transparent; `--brand`/`#5BA0F2` mapping. The stepped
lattice planes flip their value relationship by theme but hold equal intent on
both canvases (C6 / Q4); verify the depth steps still read on dark.

---

## Part 3 — Recommendation to the reviewer

- **Score L2, L3, and L4 head-to-head on Q1–Q7.** All three are gate-clean and
  non-circular by construction; the choice is *which product story leads* —
  **dialogue (L2)**, **routing (L3)**, or **system/structure (L4)** — balanced
  against small-size survival (Q3) and loudness headroom (Q7).
- **Likely shape of the decision:** **L4 Lattice** is the loudest and most
  distinctive but the highest favicon risk; **L2 Bracket** is the clearest
  product metaphor; **L3 Fork** is the cleanest monoline but the thinnest, so it
  leans hardest on the C10 weight floor. A common resolution is to lead with the
  concept that clears Q3 in testing without sacrificing C9/C10.
- **Formally reject L1 "Stack" on record** as the current bad shipped mark — it
  is the baseline being left, not an option.
- **Hold the line on the addenda:** no second hue (C1), no circular/name read
  (C3), no thin-and-quiet marks (C9–C12), and atmosphere fenced to welcome only
  (C4). Where this slate and the original `BRAND_BRIEF` §6.3 disagree, the
  decoupling directive governs.
