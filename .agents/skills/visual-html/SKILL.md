---
name: visual-html
description: >-
  Create, edit and review single-file, offline HTML pages in which inline SVG
  diagrams carry the explanation: architecture and system overviews,
  workflows, process and data flows, timelines and roadmaps, comparisons,
  explainers and visual reports, in any human language. Use when asked to
  visualize, illustrate or diagram a system, plan, process or concept as an
  HTML page, turn notes or a document into a visual one-pager, redesign or fix
  such a page or its generator script, or audit one for clarity, readability,
  accessibility or factual grounding. Do not use for multi-route web apps,
  single-page applications or UI component implementation; visual regression
  audits of an existing runnable web app; data charts, plots or dashboards
  drawn from datasets; editable files in a diagramming tool's native format;
  slide decks; or prose-only documents without HTML visuals.
---

# Visual HTML

Act as the designer, engineer and verifier of a single self-contained HTML page whose inline SVG
diagrams carry the explanation while the page text only frames them. The page can be in any human
language and script. Explicit user and project requirements override this skill's fixed values and
starting points. They override a floor only where that floor names such a requirement as its
exception, and they never override **Grounded truth**.

Priority, highest first: **Grounded truth → Illustration over text → Maximum clarity → Maximum
readability → Editorial aesthetics** (which covers **Lines and emphasis**) **→ reproducible
verification**, where reproducible verification covers **Generator first**, **Offline single
file**, **Browser verification**, **Automated guardrails** and **Export and embed hygiene**. When
two goals conflict, the higher one wins.

## Standing rules

- **Modes.** Classify each request as one mode and keep to it until the user changes it:
  - **Create:** build a new page and its generator.
  - **Edit:** change an existing page through its generator. If the page has no generator, first
    write one that reproduces the page, confirm that the regenerated page renders the same as the
    original at the verification viewports of pass 4, then make the change.
  - **Review:** audit only, ending in the **Review report**. Edit no project file until the user
    asks for fixes; agreement that a finding is real is not such a request.
  - **Output paths:** in Review, keep screenshots and exports outside the project unless the user
    names an output path. In Create and Edit, write deliverables to the output paths that pass 1
    records, and write working screenshots outside the project.
- **Fixed values, floors and starting points.** Every value and rule in this skill has one of three
  levels:
  - **Fixed values:** the colors that **Editorial aesthetics** lists and, in a dark mode, their
    dark values in `references/visual-system.md`. They are the only fixed stylistic values; use
    them as given.
  - **Floors:** the rules in this file and in the reference files, which protect truth, clarity,
    readability, accessibility and reproducible output, apart from what they mark as starting
    points. Meet every floor.
  - **Starting points:** the values and patterns marked as starting points, such as type sizes,
    font stacks, radii, stroke widths, tints, spacing, page order, figure widths, budgets, figure
    forms and primitives. A starting point is one workable answer, given so that you do not start
    from nothing. Depart from it whenever another choice gives a better design for the content:
    where it states a reason, when that reason does not apply to the content or another choice
    serves the reason better. Such departures are expected.
  Every value that is neither a fixed value nor a floor is your own design decision for the
  content at hand.
- **Design standard.** Hold every page to three design requirements, each at the level of the best
  editorial information design: the highest clarity (**Maximum clarity**), the highest readability
  (**Maximum readability**) and the highest aesthetic standard (**Editorial aesthetics**, **Lines
  and emphasis**). They rank as those rules rank.
- **Grounded truth.** Take every name, number, status, date and relationship from a source read in
  this task. Never invent a metric, percentage, count, date or quotation, even when asked to fill
  one in; show a labelled placeholder or leave it out, and name it in the report. Draw a mark to
  scale only from a sourced fact. Mark inferred, planned, proposed and estimated content visibly,
  with a status badge or a status line style. Link each source that has a location.
- **Illustration over text.** Let diagrams carry structure, flow, hierarchy, contrast and
  boundaries. Outside figures, a section holds only its number, its heading, one framing lead
  sentence, an optional status badge and optional source links, in at most 65 words, or at most 220
  non-whitespace characters when CJK characters make up at least a quarter of its letters. A
  `<figcaption>` is one noun phrase or one sentence. Write diagram labels as noun phrases or short
  verb phrases. Inside a diagram SVG, the only sentence-length text is an annotation: one short
  sentence tied to one mark by a leader line. A section without a figure holds only a source list,
  a glossary or a table that the figures need.
- **Maximum clarity.** Give each diagram one thesis. Split a figure that carries two theses or
  cannot meet the font floors with its labels clear of each other in its narrow layout or, for a
  single-layout figure, at 360px wide. Give each figure exactly one focal group, and make it the
  strongest visual mass of its figure. Use one stable term per concept across the page and its
  companion documents. Keep the terms, colors and positions of elements shared by split figures
  identical.
- **Maximum readability.** Give each diagram either one single-layout SVG or a purpose-built wide
  SVG and a purpose-built narrow SVG swapped at a CSS breakpoint. Hold wide SVG text to at least
  14px and narrow SVG text to at least 12.5px, both as authored in SVG user units and as rendered in
  CSS pixels. A single-layout SVG meets the wide floor (≥14px) as authored, the narrow floor
  (≥12.5px) as rendered at viewport widths up to 390px, and the wide floor as rendered above 390px;
  give a diagram two layouts when one SVG cannot meet these floors. Render all text in a figure SVG
  smaller than the lead sentence of the figure's section, except display text: a key number or a
  figure title set larger on purpose. Render each kind of text, such as node titles, node details
  and edge labels, at one size across the figures visible at a viewport, display text apart: its
  largest rendered size is at most 5% above its smallest. Hold these size rules at every viewport
  width from 360px up, which the verification viewports of pass 4 sample.
  `references/visual-system.md` holds the starting-point scale method that meets them. Draw all
  text as real `<text>` elements and use no `<foreignObject>`.
  Size every text box from a CJK- and Latin-aware width estimate plus inner padding. In CJK text,
  use no italic, no weight below 400, no letter spacing and no uppercase, use a line height of 1.45
  inside SVG and 1.75 in the lead sentence, and keep closing punctuation off the start of a line
  and opening brackets off its end. Limit the lead sentence's line length to about 75 Latin or 40
  CJK characters. Give each SVG figure `role="img"` and an `aria-label` that states its content
  without layout words such as "left" or "above", identical across a figure's two layouts. Use no
  motion by default. Add motion only when it explains a sequence, and make its final visible state
  the resting state, so that removing the motion leaves the content complete. Remove nonessential
  motion under `prefers-reduced-motion: reduce`. Keep all content visible with JavaScript disabled.
- **Editorial aesthetics.** Use these fixed colors: page `#FAF9F6`, card or panel `#FFFFFF`, ink
  `#161D2B`, second ink `#353E50`, muted text `#5B6474`, and one accent `#3446A6` with its tint
  `#EBECF6`. Choose the semantic and category hues for the content, and never distinguish two
  categories in one figure by red against green alone. Use a dark mode or a brand palette only when
  the user or a project requirement asks for it, and keep the same contrast floors and the ban on
  red against green alone in it. Hold text to 4.5:1 contrast and strokes and fills that carry
  meaning to 3:1 against their backgrounds. Use no decorative gradients, heavy or text shadows,
  glows or rainbow palettes. Define every color, line style and marker once as a theme token or
  shared def. Explain each encoding the page uses exactly once, and list none it does not use. In
  the figures and the legend, give each hue, line style and marker that carries meaning one meaning
  across the whole page, and encode each meaning with the same combination of hue, line style,
  marker and label in every figure. Never encode meaning by color alone: pair each hue with a
  shape, line style, icon or text label, so that every status and category stays distinct in a
  grayscale render.
- **Lines and emphasis.** Draw the lines that carry the diagram (node and region borders, arrows,
  axes) in the active palette's second ink, so that relations and structure read first. Draw the
  focal group in the accent, with a heavier stroke and, where it helps, a filled mass; use the
  accent only for the focal group and for links outside the figures. Draw a semantic role in its
  hue, with that hue's own tint as fill. Let secondary or reference elements recede with a lighter,
  thinner line that still meets 3:1 when it carries meaning; planned, proposed and future elements
  are secondary elements. When a line could take more than one of these styles, the focal style
  wins, then the semantic hue, then the receding style. Use light gray hairlines only for
  separators and rules that carry no meaning, such as those inside cards, under legends and in
  footers; they are decoration and exempt from 3:1. Reserve dash and dot patterns and every other
  status line style for status. Give each arrowhead its line's color. Route no line through a
  node it does not connect to. Set each label that sits on a line on an opaque plate of the color
  behind it, so that the line stops at the plate and never crosses the label. Never let two
  parallel lines merge into one double line: leave a gap or drop one stroke. Set cards in the card
  color on the page color, and fill regions with a pale neutral.
- **Generator first.** Keep a generator script as the single source of truth for the page. Edit the
  generator and regenerate; never hand-edit generated HTML. Make generation deterministic, so that
  two runs on the same input produce byte-identical output.
- **Offline single file.** Deliver one HTML file with inline CSS and inline SVG. It loads no
  stylesheet, script, font, image, `@import` or `url(...)` resource from the network or from
  another file; `<a href>` links, `data:` URIs and `#fragment` references are allowed. Load an
  outside asset only when the user or a project requirement calls for one.
- **Browser verification.** Before calling a created or edited page done, render it in a headless
  browser and pass every check of pass 4. If no headless browser can run here, report browser
  verification as not done and never call the page verified.
- **Automated guardrails.** Run the structural checker, this skill's `scripts/check_visual_html.py`,
  on every HTML file the task generates or reviews. Change a threshold or pass an allow flag only
  when the user or a project requirement calls for it, and name the change in the report.
- **Export and embed hygiene.** When the deliverables include PNGs, export them at 2× device scale
  only after disabling transitions and animations and confirming that each exported SVG and its
  ancestors have computed opacity `'1'`. When they include embed blocks, make each one a standalone
  iframe document that holds its own shared SVG defs and every SVG of its figure: both layouts of a
  two-layout figure, or the one SVG of a single-layout figure.

## Reference files

Read each file below in full when its condition first holds, before applying its rules, and read it
again after a compaction:

- `references/visual-system.md`: when designing, revising or reviewing the palette, typography,
  legend, spacing, arrow routing, two-layout breakpoints, or print and reduced-motion CSS.
- `references/svg-engineering.md`: when writing, editing or reviewing an HTML/SVG generator script,
  estimating text widths, building reusable SVG primitives, writing `aria-label` text, or adding
  semantic `data-*` hooks.
- `references/verification-and-export.md`: before browser verification, before running the
  structural checker, and before exporting 2× PNGs or extracting standalone embed blocks.

## 1. Frame scope, thesis, and truth

1. Set the mode under **Modes**. Record the audience, the page language or languages, the
   deliverables and the output paths.
2. Find the sources and any existing generator, starting from the page's generator comment; never
   treat the HTML as the source.
3. Build a fact table: each claim the page will show, its source and its status. Keep the table as
   data in the generator, so that each status drives its visual mark. In Review, build it in working
   notes and compare each claim on the page against it.
4. Write the page thesis, one thesis per section, and the term list.
5. Outline the sections in order: number, heading, lead sentence, figure thesis and figure form.

## 2. Design visual grammar and information architecture

1. Choose the form of each figure from its thesis. Node-link forms (flow, hierarchy, containment,
   comparison, sequence over time, state) are the starting point for structure. When another form
   shows the thesis more directly, draw that form: a schematic of the subject with callouts, a
   quantity drawn to scale, one concrete instance traced through the system, a bare label where
   position carries the meaning, or annotations tied to marks. A plot of a dataset is a data
   chart, which this skill does not draw.
2. Define the visual grammar once for the page: color roles, a line style for each status, shapes,
   line kinds, focal and receding styles, and where each encoding is explained.
3. Plan the narrow layout of each two-layout figure as a reflow, not as a scaled copy.
4. Check each figure against the starting-point budgets in `references/visual-system.md`, and split
   a figure that exceeds one when the split figures read more clearly than the whole figure.
5. In Review, audit each figure against the grammar, the encoding explanations and the budgets
   instead of designing the figures.

## 3. Build deterministic generator and two-layout SVGs

1. Structure the generator as data, theme tokens, primitives, figure builders that return each
   layout's SVG, page assembly, and one write to the output path.
2. Size and wrap text from width estimates, draw every mark with shared primitives, write each
   `aria-label` from the figure's data, add the semantic `data-*` hooks, escape all text, prefix
   every SVG `id` by figure and layout, and define shared markers once.
3. Generate twice and compare the output hashes. Remove the cause of any difference before
   verification.
4. In Review, check the generator against steps 1–2 instead of editing it, and run it only with
   output outside the project.

## 4. Verify rendered geometry, visuals and structure

1. Render the page at the desktop (1440 wide), tablet (768 wide), above-phone (391 wide), phone (390
   wide) and small phone (360 wide) viewports and on both sides of each breakpoint the page uses.
2. At each viewport, run the DOM checks: no horizontal page overflow, only the expected layout
   visible in each two-layout figure, rendered SVG text at or above its floor and, apart from
   display text, below the lead sentence of its section, one rendered size for each kind of text
   across figures, every label visible and inside its shape and its SVG, no overlapping labels, no
   console errors, and no network request beyond the page and any user-required asset.
3. Take a full-page screenshot at each viewport, open it, and review it against the visual review
   checklist. Also render and review the page with reduced motion, with JavaScript disabled and in
   grayscale.
4. Run the structural checker on each HTML file, with one `--forbid` value for each term the page
   must not show.
5. In Create and Edit, fix each failure in the generator, regenerate, and repeat steps 1–5 until
   every check passes. In Review, record each failure as a finding.
6. **Design review.** If no browser can run, report in the **Not done** field of the Delivery
   report or the **Coverage** field of the Review report that this review was not done and what it
   could not see. Otherwise, once steps 1–5 are done, with every check passing in Create and Edit,
   review the rendered result once against the three design requirements in **Design standard**,
   and keep its screenshots in a directory of their own for comparison. In Create and Edit, make
   each improvement in the generator, regenerate, and repeat steps 1–5 with the screenshots written
   to a new directory. Keep the change only if every check passes and the page after it is at least
   as clear, as readable and as good aesthetically as before it, and then keep its screenshots for
   the next comparison; otherwise, including when the change cannot pass every check, revert it in
   the generator and regenerate. The review ends when each improvement it found is kept or
   reverted. In Review, report each improvement as a finding instead of making it.

## 5. Export, embed, and report

1. Export the requested PNGs and extract the requested embed blocks under **Export and embed
   hygiene**, and open each output to confirm it is complete.
2. Deliver the report for the mode. Use these forms unless the user or a project requirement
   prescribes another:
   - **Delivery report** (Create, Edit):
     - Output files: the generator, the HTML, the PNGs and the embed blocks, each with its path.
     - Checks: the structural checker command and its result, each failure's `Problem:` line that
       the final run prints, quoted as printed, each changed threshold or allow flag with the
       requirement it serves, the viewports and the browser used, and the determinism comparison.
     - Grounding: each inferred, planned, proposed, estimated or placeholder item the page shows,
       and each requested item left out for lack of a source.
     - Not done: each skipped or failed check with its reason.
   - **Review report** (Review):
     - Findings, ranked by the priority order, each with its severity (blocks understanding,
       degrades understanding, or cosmetic), section and figure, viewport, evidence (screenshot
       path, DOM measurement or quoted checker output) and the proposed fix in the generator.
     - Coverage: the viewports, checks and sources examined; each failure's `Problem:` line that
       the final run prints, quoted as printed; each changed threshold or allow flag with the
       requirement it serves; and each check not run with its reason.

## Self-check

Before declaring the task done, confirm that each rule or pass named below holds as its section
states it, with its exceptions and mode variants:

- [ ] **Modes**, including the Edit path without a generator and the output paths.
- [ ] **Fixed values, floors and starting points**: each fixed value used as given, each floor met,
  and each starting point kept only where no other choice gives a better design for the content.
- [ ] **Design standard**: the page meets the three design requirements at the level that rule
  sets.
- [ ] **Grounded truth**, including placeholders, omissions, marks drawn to scale, status marks
  and source links.
- [ ] **Illustration over text**, for every section and its word or character limit, figcaption,
  label and annotation.
- [ ] **Maximum clarity**: theses, splits, the focal group, terms and elements shared by split
  figures.
- [ ] **Maximum readability**: layouts; the wide, narrow and single-layout font floors, text below
  each section's lead sentence apart from display text, and one rendered size for each kind of
  text across figures, all at every viewport width from 360px up; real text, text boxes, CJK text,
  lead line length, `aria-label` text, motion by default and under reduced motion, and visibility
  without JavaScript.
- [ ] **Editorial aesthetics**: fixed colors, chosen hues with no red against green alone, dark and
  brand palettes only on request with the same floors, contrast, banned effects, tokens and defs,
  encoding explanations, one meaning for each hue, line style and marker that carries meaning and
  one combination of encodings for each meaning, across the figures and the legend, and a second
  encoding for each hue that holds in grayscale.
- [ ] **Lines and emphasis**: diagram lines in the second ink, the focal group and the accent's
  uses, semantic roles, receding lines and secondary elements, precedence among line styles,
  hairlines, status line styles, arrowheads, routing past nodes, label plates, parallel lines, and
  card and region fills.
- [ ] **Generator first**, including the two-run comparison.
- [ ] **Offline single file**: one file, inline CSS and SVG, and no external or out-of-file asset
  beyond one the user or a project requirement called for.
- [ ] **Browser verification**, or a report that it was not done.
- [ ] **Automated guardrails**, including each reported threshold or flag change.
- [ ] **Export and embed hygiene** for each PNG and embed block, including opacity `'1'` on each
  exported SVG and its ancestors and every SVG of each embedded figure.
- [ ] **Reference files**, each read as that section directs.
- [ ] **Pass 1**, with the fact table in working notes in Review.
- [ ] **Pass 2**, with the figure audit in Review.
- [ ] **Pass 3**, with the Review variant.
- [ ] **Pass 4** steps 1–5, including the tablet and small phone viewports, both sides of each
  breakpoint, the reduced-motion, no-JavaScript and grayscale renders, and the structural checker.
- [ ] **Design review** (pass 4 step 6): when no browser ran, the report that it was not done and
  what it could not see; otherwise one review of the rendered result with its screenshots kept,
  steps 1–5 repeated after each change, each change kept only if it passes every check and leaves
  the page at least as clear, as readable and as good aesthetically and each other change
  reverted, and findings instead of edits in Review.
- [ ] **Pass 5**, including every field of the mode's report.
