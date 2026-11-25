# Visual system

This file gives starting points for the page's visual design, with the
details of the fixed colors and of the floors that `SKILL.md` states. A
starting point is one workable answer, given so that you do not start from
nothing. Depart from it whenever another choice gives a better design for the
content: where it states a reason, when that reason does not apply to the
content or another choice serves the reason better. Such departures are
expected. Each starting point here is marked **Starting point**, mostly with
the reason it exists. Text without that mark states a fixed value or a floor.

- [Palette and color roles](#palette-and-color-roles)
- [Dark mode and brand palettes](#dark-mode-and-brand-palettes)
- [Typography](#typography)
- [Page anatomy and spacing](#page-anatomy-and-spacing)
- [Legend](#legend)
- [Diagram grammar and focal hierarchy](#diagram-grammar-and-focal-hierarchy)
- [Arrow routing](#arrow-routing)
- [Figure budgets and splitting](#figure-budgets-and-splitting)
- [Two-layout breakpoints and reflow](#two-layout-breakpoints-and-reflow)
- [Motion, print and no-JavaScript CSS](#motion-print-and-no-javascript-css)

## Palette and color roles

Define these values once as theme tokens in the generator and emit them as CSS
custom properties. The contrast ratios are WCAG 2 ratios against `--paper`.

| Token | Value | Level | Role | Contrast on paper |
| --- | --- | --- | --- | --- |
| `--paper` | `#FAF9F6` | fixed | page background, figure background | — |
| `--card` | `#FFFFFF` | fixed | cards, panels, node fill, text on an accent fill | — |
| `--ink` | `#161D2B` | fixed | headings, primary labels | 16.0:1 |
| `--ink-2` | `#353E50` | fixed | second ink: body text, secondary labels, the lines that carry the diagram | 10.2:1 |
| `--muted` | `#5B6474` | fixed | muted text: planned or future labels, metadata | 5.7:1 |
| `--accent` | `#3446A6` | fixed | the focal group of each figure, links outside the figures | 7.75:1 |
| `--accent-tint` | `#EBECF6` | fixed | fill of the focal group | 1.1:1 |
| `--line` | `#8A8F99` | starting point | lighter lines of secondary or reference elements | 3.1:1 |
| `--hairline` | `#D8D4CA` | starting point | separators and rules that carry no meaning | 1.4:1 |
| `--region` | `#F2F0EA` | starting point | pale neutral fill of regions | 1.1:1 |
| `--ok` | `#1F7A6A` | starting point | done, healthy, passing | 4.9:1 |
| `--warn` | `#8F6110` | starting point | pending, caution, partial | 5.1:1 |
| `--risk` | `#B0442B` | starting point | blocked, failing, risk | 5.4:1 |
| `--ext` | `#5F6B7A` | starting point | external system, out of scope | 5.2:1 |

- `--accent-tint` is the swatch derived by mixing 10% of `--accent` into
  `#FFFFFF` in sRGB, with each channel rounded to the nearest integer and
  halves rounded to even. The accent keeps 6.94:1 against its tint, `--ink`
  keeps 14.35:1 on it, and `--card` text on an `--accent` fill keeps 8.16:1.
- **Starting point:** derive each other hue's tint the same way:
  `--ok-tint: #E9F2F0`, `--warn-tint: #F4EFE7`, `--risk-tint: #F7ECEA`,
  `--ext-tint: #EFF0F2`. Each of these hues keeps at least 4.54:1 against its
  own tint, and `--ink` keeps more than 14:1 on each tint.
- A tint fill against paper is only about 1.1:1, so a tint cannot carry a
  boundary alone: a stroke or a marker carries it.
- With the starting-point `--line` and `--region`, a receding line inside a
  region reaches only 2.85:1, against 3.1:1 on `--paper`. When such a line
  carries meaning, draw it in `--muted` (5.24:1 on `--region`) or another color
  that meets 3:1.
- **Starting point:** at most four muted semantic hues, because each added hue
  weakens the contrast between the others and needs its own second encoding.
  Use only the semantic and category hues a page needs.
- **Starting point:** pair hues on the blue–orange axis or with a clear
  luminance difference, because readers with the common color-vision
  deficiencies tell those pairs apart.
- Compute the contrast of every new color pair with the WCAG
  relative-luminance formula before using it, against the color beside it, and
  compare the result with the contrast floors of the **Editorial aesthetics**
  rule in `SKILL.md`.
- **Starting point:** at most `box-shadow: 0 1px 2px rgba(22, 29, 43, 0.06)`
  on an HTML card and no shadow on SVG shapes, because a stronger shadow reads
  as decoration and competes with the lines that carry the diagram.
- **Starting point:** no patterned fills, because a pattern adds a texture the
  reader must decode and competes with text. A pattern may encode a status when
  the page explains it with the other encodings and no text sits on it.

## Dark mode and brand palettes

Keep the token names and the roles in
[Palette and color roles](#palette-and-color-roles), and change only the
values. The first seven values below are the dark values of the fixed colors;
use them as given. The rest are starting points.

Dark tokens, with contrast against `#15181E`:

| Token | Value | Contrast |
| --- | --- | --- |
| `--paper` | `#15181E` | — |
| `--card` | `#1D2129` | — |
| `--ink` | `#ECEAE4` | 14.8:1 |
| `--ink-2` | `#C9CDD4` | 11.1:1 |
| `--muted` | `#A3AAB5` | 7.6:1 |
| `--accent` | `#7FA6F5` | 7.3:1 |
| `--accent-tint` | `#2D364A` | — |
| `--line` | `#7A8290` | 4.6:1 |
| `--hairline` | `#3A404B` | 1.7:1 |
| `--region` | `#191C23` | 1.0:1 |
| `--ok` | `#5FC2AE` | 8.3:1 |
| `--warn` | `#E0B062` | 8.9:1 |
| `--risk` | `#EE8A70` | 7.2:1 |
| `--ext` | `#9AA3B0` | 7.0:1 |

- `--accent-tint` is 16% of `--accent` mixed into `--card`, rounded as the
  light tints are. **Starting point:** make the other dark tints the same way;
  `--ink` keeps more than 9:1 on each of them.
- Serve dark values under `@media (prefers-color-scheme: dark)` when the user
  asks for automatic switching, or as the only palette when the user asks for a
  dark page. Verify and export each palette the page ships.
- For a brand palette, map the brand primary to `--accent` only. If the brand
  color is below 4.5:1 as text, use it for strokes and fills at 3:1 or more and
  derive a darker text variant. Keep the semantic hues muted, and recompute
  every contrast pair.

## Typography

Set `lang` on `<html>` to the page language. A font embedded as a `data:` URI
meets **Offline single file** in `SKILL.md`; embed one only when its license
permits embedding.

**Starting point:** system font stacks, because system fonts load offline, in
a sans voice throughout, with the Latin stack first and the stack for the page
language after it. A second voice, such as a system serif for the page title
and headings, is open to you.

| Script or voice | Stack |
| --- | --- |
| Latin | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` |
| Simplified Chinese | `"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif` |
| Traditional Chinese | `"PingFang TC", "Microsoft JhengHei", "Noto Sans CJK TC", sans-serif` |
| Japanese | `"Hiragino Sans", "Yu Gothic", Meiryo, "Noto Sans CJK JP", sans-serif` |
| Korean | `"Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", sans-serif` |
| Code | `ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace` |
| Latin serif, for display text | `"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif` |

**Starting point:** this HTML type scale, in CSS pixels, because its clear
steps from title to heading to lead sentence rank the page text at a glance. A
wider scale is open to you above the font floors:

| Element | Size | Weight | Line height |
| --- | --- | --- | --- |
| Page title | 34–40 | 700 | 1.2 |
| Section heading | 24–26 | 650 | 1.25 |
| Section number | 14–15 | 600, tabular numerals | 1.2 |
| Lead sentence | 17–18 | 400 | 1.6 Latin |
| Badge, source link | 13–14 | 500–600 | 1.2 |

**Starting point:** this SVG type scale, in SVG user units, because node
titles one step above the details rank the labels while every label stays
below the lead sentence. A wider scale is open to you above the font floors
and below the lead-size limit in
[Two-layout breakpoints and reflow](#two-layout-breakpoints-and-reflow):

| Text | Wide | Narrow |
| --- | --- | --- |
| Display text: one key number or a figure title | 24–32, weight 600 | 20–24, weight 600 |
| Node title | 16, weight 600 | 14, weight 600 |
| Node detail, container label, annotation | 14 | 12.5 |
| Edge label, axis label, badge | 14 | 12.5 |

- Mark each display text with `data-display` on its own `<text>` element, so
  that `verify.mjs` exempts it from the lead-size limit and from the
  comparison of kinds of text. The mark covers only that element and its
  `<tspan>` children, never the text inside a marked group.
- Mark every other `<text>` element with its kind of text in
  `data-text-kind`, such as `node-title`, `node-detail` or `edge-label`, with
  the same value in every figure, so that `verify.mjs` compares the rendered
  size of each kind across the figures.
- **Starting point:** give a single-layout SVG the wide sizes.
- **Starting point:** use a line height of 1.3 for Latin text inside SVG.
- **Starting point:** Latin badges may use uppercase with `0.04em` letter
  spacing.

## Page anatomy and spacing

**Starting point:** this page order, top to bottom:

```text
header    page title · one-sentence page thesis · status badge · date of the sources
legend    the shared legend
section   number · heading · lead sentence · badge? · source links? · figure
section   ...
sources   source list (and glossary, when the terms need one)
```

The header comes first so that the page opens on its thesis. The legend comes
before the first section so that the reader knows each encoding before meeting
it. When each encoding is instead explained at its first use or labelled in
its figure, place the legend elsewhere or leave it out. The source list comes
last because it serves a reader checking a claim, not a reader following the
argument.

**Starting point:** this spacing, because one grid and fixed gaps make
alignment and grouping read without lines:

- Center a content column of at most 1120px. Use 32px side padding at the
  wide layout and 16px at the narrow layout.
- Space on an 8-unit grid, with 4 units for fine adjustment. Separate sections
  by 64–80px at the wide layout and 40–48px at the narrow layout.
- Give each figure 16px inner padding at the wide layout and 12px at the
  narrow layout, and no inline margin.
- Inside SVG nodes, use at least 16 horizontal and 10 vertical units of
  padding in the wide layout, and 12 and 8 in the narrow layout, so that text
  keeps clear of its border.
- Separate nodes by at least 32 units along the flow and 24 across it in the
  wide layout, and by 20 and 16 in the narrow layout.
- Give containers 20 units of inner padding in the wide layout and 14 in the
  narrow layout, with the container label inside the top edge.
- Use corner radius 6–8 for nodes and 10–12 for containers, because a slight
  radius separates a node from a region; a schematic, a bare label or a scale
  mark needs no box.
- Use stroke widths of 2.5 for the focal group, 1.5 for the lines that carry
  the diagram and 1 for lighter lines and hairlines, so that the focal group
  carries the heaviest line.

## Legend

- Give each entry a sample glyph drawn with the same primitive the figures use
  and a noun-phrase label in the page language.
- **Starting point:** place the legend after the page header and before the
  first section, for the reason in
  [Page anatomy and spacing](#page-anatomy-and-spacing).
- **Starting point:** list the encodings in this order: focal group, statuses,
  semantic hues, markers and arrow kinds.
- **Starting point:** at the narrow layout, let the entries wrap into one or
  two columns.

## Diagram grammar and focal hierarchy

**Starting point:** this grammar. Each row is its own combination of
encodings, and each style meets the contrast floors and the **Lines and
emphasis** rule in `SKILL.md`; recompute each pair you change. The neutral
fills (`--card`, `--paper`) and the label inks carry no meaning of their own:
the stroke, the marker and the badge of each row carry it.

| Meaning | Stroke | Fill | Label | Second encoding |
| --- | --- | --- | --- | --- |
| Focal: current or primary | `--accent`, 2.5, solid | `--accent-tint`, or `--accent` as a filled mass | `--ink`, 600; `--card`, 600 on an `--accent` fill | heavier stroke or filled mass |
| Normal: present | `--ink-2`, 1.5, solid | `--card` | `--ink-2` | — |
| Secondary or reference | `--line`, 1, solid | `--card` | `--muted` | lighter, thinner line |
| Planned, proposed or future | `--muted`, 1, dashed `6 4` | `--paper` | `--muted` | "planned" badge |
| Inferred | `--ink-2`, 1.5, dotted `2 3` | `--card` | `--ink-2` | "inferred" badge |
| Estimated value | as its node | as its node | `≈` before the value | "estimate" badge |
| Placeholder for a missing source | `--ink-2`, 1.5, dash-dot `8 3 2 3` | `--paper` | "source needed" | placeholder badge |
| Region or container | `--ink-2`, 1, solid | `--region` | `--ink-2`, label inside the top edge | — |
| External system | `--ext`, 1.5, solid | `--ext-tint` | `--ink-2` | a named tag |
| Done or healthy | `--ok` | `--ok-tint` | `--ink` | check mark |
| Pending or caution | `--warn` | `--warn-tint` | `--ink` | clock or triangle marker |
| Blocked or risk | `--risk` | `--risk-tint` | `--ink` | exclamation marker |

- Keep the badge words in the page language, and use the same words wherever
  the page explains the encodings.
- **Starting point:** draw every element outside the focal group in one of the
  styles below the focal row.

## Arrow routing

- Define one arrowhead marker for each line color in the shared defs, so that
  each arrowhead takes its line's color. **Starting point:** a filled head
  with `markerUnits="userSpaceOnUse"`, so that heads keep one size.
- **Starting point:** route edges orthogonally, with horizontal and vertical
  segments and corner radius 6, and use a straight line when the ends align
  and one arc style for feedback loops. Right-angle routes suit system
  structure; direct or curved lines can suit concepts, cycles and flows that
  merge or divide.
- **Starting point:** attach each edge to the midpoint of a node side, or to
  evenly spaced ports when one side has several edges. Leave a 3-unit gap
  between the arrowhead tip and the node, and make the last segment at least
  12 units long.
- **Starting point:** follow the reading direction: left to right in the wide
  layout and top to bottom in the narrow layout. On a right-to-left page
  (`dir="rtl"`), mirror the horizontal flows.
- **Starting point:** at most two crossings per figure, at right angles, with
  parallel edges at least 12 units apart, because each crossing makes the
  reader trace a line through it.
- **Starting point:** put an edge label at a segment midpoint. Its plate, which
  **Lines and emphasis** in `SKILL.md` requires, is a rectangle in the color
  behind the line (`--paper` on the page, `--region` inside a region) with
  3–4 units of padding.
- **Starting point:** draw two separate arrows instead of one double-headed
  arrow when the two directions carry different things, so that each direction
  carries its own label.

## Figure budgets and splitting

**Starting point:** these budgets, each with its reason:

| Budget | Limit | Reason |
| --- | --- | --- |
| Nodes per figure | 12 | more nodes make the focal group harder to find and crowd the narrow layout |
| Nesting depth of containers | 3 | each level costs padding in the narrow layout and makes containment harder to follow |
| Edge crossings | 2 | each crossing makes the reader trace a line through it |
| Lines per node label | 2 | a longer label turns a node into a text block |
| Characters per label line | about 24 Latin or 12 CJK | fits the starting-point node widths at the starting-point sizes |
| Words per edge label | 3 Latin words or 6 CJK characters | an edge label must fit on its segment |
| Height of a narrow figure | about 1400 CSS px at the phone viewport | about 1.7 phone screens of 844px, so that the reader keeps the figure in view |

- **Starting point:** split a figure with one of these patterns:
  - an overview figure, then one detail figure per part;
  - one figure per stage of a long flow;
  - a before figure and an after figure instead of one mixed figure;
  - one figure per audience question.

## Two-layout breakpoints and reflow

Mark each figure SVG with its layout. The structural checker, `verify.mjs` and
`export.mjs` classify an SVG the same way:

| Layout | Marker | Accepted aliases |
| --- | --- | --- |
| Wide | `class="wide" data-layout="wide"` | class `w` |
| Narrow | `class="narrow" data-layout="narrow"` | class `n` |
| Single | `data-layout="single"` | the only diagram SVG in its `<figure>`, with no wide or narrow sibling |

Emit the full class names and the `data-layout` value in generated pages.
Accept the short aliases when you review a page that uses them, and match
them in its CSS.

The font floors, the lead-size limit (text in a figure SVG renders smaller
than its section's lead sentence) and one rendered size for each kind of text
across figures are outcomes that **Maximum readability** in `SKILL.md`
requires at every viewport width from 360px up. The widths, breakpoints, caps
and scales below are starting points for meeting them; check the outcomes
themselves whenever you depart from them. All the arithmetic below assumes
the starting-point paddings in
[Page anatomy and spacing](#page-anatomy-and-spacing), with no figure inline
margin and no figure border; a border adds twice its width to each
breakpoint.

- **Starting point:** one `viewBox` width for all wide SVGs, 960, and one for
  all narrow SVGs, 300, because one width keeps type and line weights the same
  size in every figure. A figure with another wide width, such as an inset
  figure, needs its own breakpoint: give its `<figure>` a `data-breakpoint`
  attribute with that width and media queries of its own, as in the CSS below.
- **Starting point:** have the generator write a cap on each figure SVG as an
  inline `style="max-width:…px"`: cap = `viewBox` width × s, rounded down to
  a whole pixel. Choose s so that s × the largest text size in the SVG,
  display text apart, is smaller than the lead sentence size, and so that each
  kind of text renders at one size in every layout. With a 17px lead and the
  starting-point type scale, s = 1.05 for wide and single-layout SVGs and
  s = 1.2 for narrow SVGs, so that node titles render at 16.8px in both:
  16 × 1.05 = 14 × 1.2 = 16.8, below the 17px lead. The caps are then 1008px
  for a 960 wide `viewBox`, 714px for a 680 inset `viewBox`, 360px for a 300
  narrow `viewBox` and 350px for a 334 single-layout `viewBox`.
- **Starting point:** set each breakpoint at the viewport width where the
  figure content box equals the cap of the figure's wide SVG, so that the wide
  layout shows only at its cap scale, where its text matches the text of the
  other figures. The page breakpoint is then 1008 + 2 × 32 page padding +
  2 × 16 figure padding = 1104px. Below it the narrow paddings apply, so the
  680-unit inset figure's breakpoint is 714 + 2 × 16 + 2 × 12 = 770px.
- **Starting point:** a narrow `viewBox` width no larger than the figure
  content box at 360px, 360 − 2 × 16 − 2 × 12 = 304px, so that narrow text
  renders at its authored size or larger at every supported width.
- **Starting point:** a single-layout `viewBox` width no larger than the
  figure content box at 391px, 335px, so that the SVG renders at a scale of at
  least 1 above 390px. At 360px, the content box of 304px scales a 334-unit
  `viewBox` by 0.910, so 14-unit text renders at 12.74px.

With these starting points, each figure renders at the scales below. At every
width from 360px up, each kind of text stays within 2.7% of one size, every
label meets its floor, and the largest label renders at 16.8px or less. The
inset figure is the 680-unit example with its 770px breakpoint.

| Viewport | Content box | Visible SVGs and their scales | Node title (16 or 14 units) | Node detail (14 or 12.5 units) |
| ---: | ---: | --- | --- | --- |
| 360 | 304 | narrow 1.013, single 0.910 | 14.19, 14.56px | 12.67, 12.74px |
| 390 | 334 | narrow 1.113, single 1.000 | 15.59, 16.00px | 13.92, 14.00px |
| 616 | 560 | narrow 1.200, single 1.048 | 16.80, 16.77px | 15.00, 14.67px |
| 768 | 712 | narrow 1.200, single 1.048 | 16.80, 16.77px | 15.00, 14.67px |
| 769 | 713 | narrow 1.200, single 1.048 | 16.80, 16.77px | 15.00, 14.67px |
| 770 | 714 | narrow 1.200, inset wide 1.050, single 1.048 | 16.80, 16.80, 16.77px | 15.00, 14.70, 14.67px |
| 1103 | 1047 | narrow 1.200, inset wide 1.050, single 1.048 | 16.80, 16.80, 16.77px | 15.00, 14.70, 14.67px |
| 1104 | 1008 | wide 1.050, inset wide 1.050, single 1.048 | 16.80, 16.80, 16.77px | 14.70, 14.70, 14.67px |
| 1440 | 1024 | wide 1.050, inset wide 1.050, single 1.048 | 16.80, 16.80, 16.77px | 14.70, 14.70, 14.67px |

Breakpoint CSS for a 960 wide `viewBox` and a 1104px page breakpoint, with
one figure whose own breakpoint is 770px. Scope every breakpoint query to
`screen`, because a print page can be narrower than a breakpoint, so that the
print rules in
[Motion, print and no-JavaScript CSS](#motion-print-and-no-javascript-css)
decide the printed layout. Each SVG carries its own cap, as in
`<svg class="narrow" data-layout="narrow" viewBox="0 0 300 780" style="max-width:360px" …>`:

```css
figure { margin-inline: 0; }
figure svg { display: block; width: 100%; height: auto; margin-inline: auto; }
.narrow { display: none; }
@media screen and (width < 1104px) {
  .wide { display: none; }
  .narrow { display: block; }
}
@media screen and (width >= 770px) {
  figure[data-breakpoint="770"] .wide { display: block; }
  figure[data-breakpoint="770"] .narrow { display: none; }
}
@media screen and (width < 770px) {
  figure[data-breakpoint="770"] .wide { display: none; }
  figure[data-breakpoint="770"] .narrow { display: block; }
}
```

**Starting point:** these reflow patterns from the wide to the narrow layout:

| Wide layout | Narrow layout |
| --- | --- |
| Horizontal pipeline | Vertical stack with downward arrows |
| Swimlanes | One stacked group per lane, with the lane name as its header |
| Side-by-side comparison | Stacked cards that each repeat the row labels |
| Matrix or grid | One card per row |
| Horizontal timeline | Vertical timeline with the axis on the start side |
| Hub and spokes | Hub on top, spokes listed below it with short connectors |
| Nested containers | The same nesting, stacked, with narrow padding |
| Wide tree | Top-down indented tree |
| Schematic with callouts | The schematic, with the callouts numbered and listed below it |

## Motion, print and no-JavaScript CSS

- Never hide content in static CSS with `opacity: 0`, `visibility: hidden` or
  an off-screen transform waiting for a script. Prefer no script at all. If a
  script adds a reveal effect, it first adds a `js` class to `<html>`, and only
  rules under `.js`, such as `.js .reveal`, may hide content before the effect
  runs.
- Remove nonessential motion under reduced motion, and show any content that a
  `.js` rule hides:

  ```css
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation: none !important;
      transition: none !important;
      scroll-behavior: auto !important;
    }
    .js .reveal { opacity: 1 !important; transform: none !important; }
  }
  ```
- Print the wide layout with the full light token set on white paper, so that a
  dark-mode page prints legibly, and keep figures whole. Put this block after
  any dark-mode block, because a print page can still report a dark color
  scheme. Replace the starting-point values in it with the page's own:

  ```css
  @media print {
    :root {
      --paper: #FFFFFF; --card: #FFFFFF; --ink: #161D2B; --ink-2: #353E50;
      --muted: #5B6474; --accent: #3446A6; --accent-tint: #EBECF6;
      /* starting-point values: */
      --line: #8A8F99; --hairline: #D8D4CA; --region: #F2F0EA;
      --ok: #1F7A6A; --warn: #8F6110; --risk: #B0442B; --ext: #5F6B7A;
      --ok-tint: #E9F2F0; --warn-tint: #F4EFE7; --risk-tint: #F7ECEA;
      --ext-tint: #EFF0F2;
    }
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .wide { display: block; }
    .narrow { display: none; }
    section, figure { break-inside: avoid; }
  }
  ```
