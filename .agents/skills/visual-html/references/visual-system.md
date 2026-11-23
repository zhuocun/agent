# Visual system

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

| Token | Value | Role | Contrast on paper |
| --- | --- | --- | --- |
| `--paper` | `#FAF9F6` | page background, figure background | — |
| `--card` | `#FFFFFF` | panels, node fill | — |
| `--ink` | `#161D2B` | headings, primary labels, primary strokes | 16.0:1 |
| `--ink-2` | `#353E50` | body text, secondary labels | 10.2:1 |
| `--muted` | `#5B6474` | planned or future labels, metadata | 5.7:1 |
| `--line` | `#8A8F99` | meaningful strokes: borders, containers, arrows | 3.1:1 |
| `--hairline` | `#D8D4CA` | decorative separators only, never meaning | 1.4:1 |
| `--accent` | `#2456C4` | the focal element of each figure, links | 6.2:1 |
| `--ok` | `#1F7A6A` | done, healthy, passing | 4.9:1 |
| `--warn` | `#8F6110` | pending, caution, partial | 5.1:1 |
| `--risk` | `#B0442B` | blocked, failing, risk | 5.4:1 |
| `--ext` | `#5F6B7A` | external system, out of scope | 5.2:1 |

- Each hue token also has a tint for fills: 10% of the hue mixed into
  `#FFFFFF`, for example `--accent-tint: #E9EEF9`. Every hue keeps at least
  4.5:1 against its own tint, and `--ink` keeps more than 13:1 on every tint.
- A tint fill is decoration. The stroke or the marker carries the boundary,
  because a tint against paper is only about 1.1:1.
- Use only the semantic hues a page needs, and express any further category
  with a shape, a line style or a text label.
- Keep the accent for one job: the focal element of each figure, plus links.
  Do not also use it as a category color.
- Pair hues for colorblind safety. In one figure, never distinguish two
  categories by red against green alone. Prefer pairs on the blue–orange axis
  or pairs with a clear luminance difference, and always add a second encoding
  from [Diagram grammar and focal hierarchy](#diagram-grammar-and-focal-hierarchy).
- Compute the contrast of every new color pair with the WCAG relative-luminance
  formula before using it, against the color beside it, and compare the result
  with the contrast floors of the **Editorial aesthetics** rule in `SKILL.md`.
- Besides the effects that the **Editorial aesthetics** rule in `SKILL.md` bans,
  use no patterned fills or text shadows. The heaviest permitted shadow is
  `box-shadow: 0 1px 2px rgba(22, 29, 43, 0.06)` on an HTML card; SVG shapes
  carry none.

## Dark mode and brand palettes

Keep the token names and the roles in
[Palette and color roles](#palette-and-color-roles), and change only the
values.

Dark tokens, with contrast against `#15181E`:

| Token | Value | Contrast |
| --- | --- | --- |
| `--paper` | `#15181E` | — |
| `--card` | `#1D2129` | — |
| `--ink` | `#ECEAE4` | 14.8:1 |
| `--ink-2` | `#C9CDD4` | 11.1:1 |
| `--muted` | `#A3AAB5` | 7.6:1 |
| `--line` | `#7A8290` | 4.6:1 |
| `--hairline` | `#3A404B` | 1.7:1 |
| `--accent` | `#7FA6F5` | 7.3:1 |
| `--ok` | `#5FC2AE` | 8.3:1 |
| `--warn` | `#E0B062` | 8.9:1 |
| `--risk` | `#EE8A70` | 7.2:1 |
| `--ext` | `#9AA3B0` | 7.0:1 |

- Make dark tints by mixing 16% of the hue into `--card`. `--ink` keeps more
  than 8:1 on each of them.
- Serve dark values under `@media (prefers-color-scheme: dark)` when the user
  asks for automatic switching, or as the only palette when the user asks for a
  dark page. Verify and export each palette the page ships.
- For a brand palette, map the brand primary to `--accent` only. If the brand
  color is below 4.5:1 as text, use it for strokes and fills at 3:1 or more and
  derive a darker text variant. Keep the semantic hues muted, and recompute
  every contrast pair.

## Typography

Use system font stacks only. Put the Latin stack first and the stack for the
page language after it, and set `lang` on `<html>` to the page language.

| Script | Stack after the Latin stack |
| --- | --- |
| Latin | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` |
| Simplified Chinese | `"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif` |
| Traditional Chinese | `"PingFang TC", "Microsoft JhengHei", "Noto Sans CJK TC", sans-serif` |
| Japanese | `"Hiragino Sans", "Yu Gothic", Meiryo, "Noto Sans CJK JP", sans-serif` |
| Korean | `"Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", sans-serif` |
| Code | `ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace` |

HTML type scale, in CSS pixels:

| Element | Size | Weight | Line height |
| --- | --- | --- | --- |
| Page title | 34–40 | 700 | 1.2 |
| Section heading | 24–26 | 650 | 1.25 |
| Section number | 14–15 | 600, tabular numerals | 1.2 |
| Lead sentence | 17–18 | 400 | 1.6 Latin, 1.75 CJK |
| Badge, source link | 13–14 | 500–600 | 1.2 |

SVG type scale, in SVG user units:

| Text | Wide | Narrow |
| --- | --- | --- |
| Node title | 16, weight 600 | 14, weight 600 |
| Node detail, container label | 14 | 12.5 |
| Edge label, axis label, badge | 14 | 12.5 |

- Give a single-layout SVG the wide sizes.
- Use line heights of 1.3 for Latin and 1.45 for CJK inside SVG.
- Use no weight below 400 and no italic for CJK. Do not set letter spacing or
  uppercase on CJK text. Latin badges may use uppercase with `0.04em` letter
  spacing.
- Limit the lead sentence line length to about 75 Latin characters or 40 CJK
  characters by the column width.

## Page anatomy and spacing

Use this page structure, top to bottom:

```text
header    page title · one-sentence page thesis · status badge · date of the sources
legend    the shared legend
section   number · heading · lead sentence · badge? · source links? · figure
section   ...
sources   source list (and glossary, when the terms need one)
```

- Center a content column of at most 1120px. Use 32px side padding at the
  wide layout and 16px at the narrow layout.
- Space on an 8-unit grid, with 4 units for fine adjustment. Separate sections
  by 64–80px at the wide layout and 40–48px at the narrow layout.
- Give each figure 16px inner padding at the wide layout and 12px at the
  narrow layout.
- Inside SVG nodes, use at least 16 horizontal and 10 vertical units of
  padding in the wide layout, and 12 and 8 in the narrow layout.
- Separate nodes by at least 32 units along the flow and 24 across it in the
  wide layout, and by 20 and 16 in the narrow layout.
- Give containers 20 units of inner padding in the wide layout and 14 in the
  narrow layout, with the container label inside the top edge.
- Use corner radius 6–8 for nodes and 10–12 for containers. Use stroke widths
  of 2 for the focal element, 1.25–1.5 for normal strokes and 1 for
  hairlines.

## Legend

- Place the legend after the page header and before the first section.
- Give each entry a sample glyph drawn with the same primitive the figures use
  and a noun-phrase label in the page language.
- List every encoding the page uses, in this order: focal element, statuses,
  semantic hues, markers and arrow kinds. List nothing the page does not use.
- At the narrow layout, let the entries wrap into one or two columns.

## Diagram grammar and focal hierarchy

| Meaning | Stroke | Fill | Label | Second encoding |
| --- | --- | --- | --- | --- |
| Focal: current or primary | `--accent`, 2, solid | `--accent-tint` | `--ink`, 600 | heavier stroke |
| Normal: present and secondary | `--line`, 1.5, solid | `--card` | `--ink-2` | — |
| Planned, proposed or future | `--muted`, 1.5, dashed `6 4` | `--paper` | `--muted` | "planned" badge |
| Inferred | `--line`, 1.5, dotted `2 3` | `--card` | `--ink-2` | "inferred" badge |
| Estimated value | as its node | as its node | `≈` before the value | "estimate" badge |
| Placeholder for a missing source | `--muted`, 1.5, dashed `6 4` | `--paper` | "source needed" | placeholder badge |
| Boundary or container | `--line`, 1, solid | none or `--paper` | `--ink-2`, label inside the top edge | — |
| External system | `--ext`, 1.5, solid | `--card` | `--ink-2` | double left edge or a named tag |
| Done or healthy | `--ok` | `--ok-tint` | `--ink` | check mark |
| Pending or caution | `--warn` | `--warn-tint` | `--ink` | clock or triangle marker |
| Blocked or risk | `--risk` | `--risk-tint` | `--ink` | exclamation marker |

- Give each figure exactly one focal group, and draw every other element in
  the normal, planned or inferred style.
- Keep the badge words in the page language and use the same words in the
  legend.
- Use a status line style for status only. Do not reuse dashes or dots for
  any other meaning.

## Arrow routing

- Define one filled arrowhead marker for `--line` and one for `--accent` in
  the shared defs, with `markerUnits="userSpaceOnUse"` so that heads keep one
  size.
- Route edges orthogonally, with horizontal and vertical segments and corner
  radius 6. Use a straight line when the ends align. Use one arc style only for
  feedback loops.
- Attach each edge to the midpoint of a node side, or to evenly spaced ports
  when one side has several edges. Leave a 3-unit gap between the arrowhead
  tip and the node, and make the last segment at least 12 units long.
- Follow the reading direction: left to right in the wide layout and top to
  bottom in the narrow layout. On a right-to-left page (`dir="rtl"`), mirror
  the horizontal flows.
- Never route an edge through a node or a label. Allow at most two crossings
  per figure, at right angles. Keep parallel edges at least 12 units apart.
- Put an edge label at a segment midpoint on a `--paper` background rectangle
  with 3–4 units of padding, so that no line runs through its text.
- Draw two separate arrows instead of one double-headed arrow when the two
  directions carry different things.

## Figure budgets and splitting

| Budget | Limit |
| --- | --- |
| Nodes per figure | 12 |
| Nesting depth of containers | 3 |
| Edge crossings | 2 |
| Focal groups | 1 |
| Lines per node label | 2 |
| Characters per label line | about 24 Latin or 12 CJK |
| Words per edge label | 3 Latin words or 6 CJK characters |
| Height of a narrow figure | about 1400 CSS px, two phone screens |

- Split a figure that exceeds a budget or carries two theses. Use one of
  these patterns:
  - an overview figure, then one detail figure per part;
  - one figure per stage of a long flow;
  - a before figure and an after figure instead of one mixed figure;
  - one figure per audience question.
- Keep the terms, colors and positions of shared elements identical across
  the split figures, so that the reader can connect them.

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

- Give all wide SVGs one `viewBox` width and all narrow SVGs another. With the
  paddings in [Page anatomy and spacing](#page-anatomy-and-spacing), 960 for
  wide and 330 for narrow work well.
- Set the breakpoint at the viewport width where the figure content box equals
  the wide `viewBox` width: 960 + 2 × 32 page padding + 2 × 16 figure padding
  = 1056px, plus twice any figure border width. At and above the breakpoint
  the wide layout shows, and its rendered scale is never below 1.
- Make the narrow `viewBox` width no larger than the figure content box at the
  390px phone viewport: 390 − 2 × 16 − 2 × 12 = 334. Then the narrow layout
  renders at a scale of at least 1 on the phone.
- Cap the narrow SVG at `max-width: 560px` and center it, so that it does not
  grow large on tablets.
- Give a single-layout SVG 14-unit text or larger and a `viewBox` width of at
  most 374. At the phone viewport its scale is then at least 334 ÷ 374 ≈
  0.893, so 14-unit text renders at 12.5px or more. Cap it at
  `max-width: 560px` and keep that cap at least as wide as its `viewBox`, so
  that it renders at a scale of at least 1, and its text at 14px or more, at
  the desktop and breakpoint viewports.

Breakpoint CSS for a 960 wide `viewBox`, a 1056px breakpoint and a 560px cap:

```css
figure svg { display: block; width: 100%; height: auto; }
figure svg[data-layout="single"] { max-width: 560px; margin-inline: auto; }
.narrow { display: none; }
@media (max-width: 1055.98px) {
  .wide { display: none; }
  .narrow { display: block; max-width: 560px; margin-inline: auto; }
}
```

Reflow patterns from the wide to the narrow layout:

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

## Motion, print and no-JavaScript CSS

- Default to no motion. Add motion only when it explains a sequence, and make
  the final visible state the resting state, so that removing the motion
  leaves the content complete.
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
  the breakpoint block and any dark-mode block, because a print page can be
  narrower than the breakpoint and can still report a dark color scheme:

  ```css
  @media print {
    :root {
      --paper: #FFFFFF; --card: #FFFFFF; --ink: #161D2B; --ink-2: #353E50;
      --muted: #5B6474; --line: #8A8F99; --hairline: #D8D4CA;
      --accent: #2456C4; --ok: #1F7A6A; --warn: #8F6110; --risk: #B0442B;
      --ext: #5F6B7A; --accent-tint: #E9EEF9; --ok-tint: #E9F2F0;
      --warn-tint: #F4EFE7; --risk-tint: #F7ECEA; --ext-tint: #EFF0F2;
    }
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .wide { display: block; }
    .narrow { display: none; }
    section, figure { break-inside: avoid; }
  }
  ```
