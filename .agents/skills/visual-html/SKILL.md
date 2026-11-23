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
language and script. Explicit user and project requirements override this skill's defaults, but
never override **Grounded truth**.

Priority, highest first: **Grounded truth → Illustration over text → Maximum clarity → Maximum
readability → Editorial aesthetics → reproducible verification**, where reproducible verification
covers **Generator first**, **Offline single file**, **Browser verification**, **Automated
guardrails** and **Export and embed hygiene**. When two goals conflict, the higher one wins.

## Standing rules

- **Modes.** Classify each request as one mode and keep to it until the user changes it:
  - **Create:** build a new page and its generator.
  - **Edit:** change an existing page through its generator. If the page has no generator, first
    write one that reproduces the page, confirm that the regenerated page renders the same as the
    original at the three viewports, then make the change.
  - **Review:** audit only, ending in the **Review report**. Edit no project file until the user
    asks for fixes; agreement that a finding is real is not such a request.
  - **Output paths:** in Review, keep screenshots and exports outside the project unless the user
    names an output path. In Create and Edit, write deliverables to the output paths that pass 1
    records, and write working screenshots outside the project.
- **Grounded truth.** Take every name, number, status, date and relationship from a source read in
  this task. Never invent a metric, percentage, count, date or quotation, even when asked to fill
  one in; show a labelled placeholder or leave it out, and name it in the report. Mark inferred,
  planned, proposed and estimated content visibly, with a status badge or the legend's status line
  style. Link each source that has a location.
- **Illustration over text.** Let diagrams carry structure, flow, hierarchy, contrast and
  boundaries. Outside figures, a section holds only its number, its heading, one framing lead
  sentence, an optional status badge and optional source links. A `<figcaption>` is one noun phrase
  or one sentence. Write diagram labels as noun phrases or short verb phrases, never as prose
  paragraphs. A section without a figure holds only a source list, a glossary or a table that the
  figures need.
- **Maximum clarity.** Give each diagram one thesis. Split a figure that carries two theses or
  cannot meet the font floors and spacing rules in its narrow layout or, for a single-layout
  figure, at the phone viewport. Give each figure one unambiguous focal hierarchy: current or
  primary elements in full ink or the accent, future or secondary elements visibly muted. Use one
  stable term per concept across the page and its companion documents.
- **Maximum readability.** Give each diagram either one single-layout SVG or a purpose-built wide
  SVG and a purpose-built narrow SVG swapped at a CSS breakpoint. Hold wide SVG text to at least
  14px and narrow SVG text to at least 12.5px, both as authored in SVG user units and as rendered in
  CSS pixels at every viewport that shows the layout. A single-layout SVG meets the wide floor
  (≥14px) as authored and the narrow floor (≥12.5px) as rendered at the phone viewport (390×844),
  and the wide floor as rendered at the other viewports; give a diagram two layouts when one SVG
  cannot meet these floors. Size every text box from a CJK- and Latin-aware width estimate plus
  inner padding. Give each SVG figure `role="img"` and an `aria-label` that states its content
  without layout words such as "left" or "above", identical across a figure's two layouts. Remove
  nonessential motion under `prefers-reduced-motion: reduce`. Keep all content visible with
  JavaScript disabled.
- **Editorial aesthetics.** Default to the warm paper palette: page `#FAF9F6`, panels `#FFFFFF`, ink
  from `#161D2B` to `#353E50`, one primary accent and at most four muted semantic hues. Use a dark
  mode or a brand palette only when the user or a project requirement asks for it, and keep the
  same contrast floors, restraint and colorblind-safe pairing in it. Hold text to 4.5:1 contrast
  and meaningful strokes and fills to 3:1 against their backgrounds. Use no decorative gradients,
  heavy drop shadows, glows or rainbow palettes. Define every color, line style and marker once as
  a theme token or shared def, and explain each one in one shared page legend. Never encode meaning
  by color alone: pair each hue with a shape, line style, icon or text label.
- **Generator first.** Keep a generator script as the single source of truth for the page. Edit the
  generator and regenerate; never hand-edit generated HTML. Make generation deterministic, so that
  two runs on the same input produce byte-identical output.
- **Offline single file.** Deliver one HTML file with inline CSS, inline SVG and system font stacks.
  It loads no stylesheet, script, font, image, `@import` or `url(...)` resource from the network or
  from another file; `<a href>` links, `data:` URIs and `#fragment` references are allowed. Load an
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
5. Outline the sections in order: number, heading, lead sentence, figure thesis and figure type.

## 2. Design visual grammar and information architecture

1. Choose one figure type per thesis from the shape of the content: flow, hierarchy, containment,
   comparison, sequence over time or state.
2. Define the visual grammar once for the page: color roles, a line style for each status, node and
   container shapes, arrow kinds, focal and muted styles, and the legend that names them all.
3. Plan the narrow layout of each two-layout figure as a reflow, not as a scaled copy.
4. Check each figure against the node, label and crossing budgets in `references/visual-system.md`,
   and split each figure that exceeds them.
5. In Review, audit each figure against the grammar, the legend and the budgets instead of designing
   the figures.

## 3. Build deterministic generator and two-layout SVGs

1. Structure the generator as data, theme tokens, primitives, figure builders that return each
   layout's SVG, page assembly, and one write to the output path.
2. Size and wrap text from width estimates, draw shapes and arrows with shared primitives, write
   each `aria-label` from the figure's data, add the semantic `data-*` hooks, escape all text,
   prefix every SVG `id` by figure and layout, and define shared markers once.
3. Generate twice and compare the output hashes. Remove the cause of any difference before
   verification.
4. In Review, check the generator against steps 1–2 instead of editing it, and run it only with
   output outside the project.

## 4. Verify rendered geometry and visuals in a real browser

1. Render the page at the desktop, breakpoint and phone viewports.
2. At each viewport, run the DOM checks: no horizontal page overflow, only the expected layout
   visible in each two-layout figure, rendered SVG text at or above its floor, every label visible
   and inside its shape and its SVG, no overlapping labels, no console errors, and no network
   request beyond the page and any user-required asset.
3. Take a full-page screenshot at each viewport, open it, and review it against the visual review
   checklist. Also render and review the page with reduced motion, with JavaScript disabled and in
   grayscale.
4. In Create and Edit, fix each failure in the generator, regenerate, and repeat this pass until
   every check passes. In Review, record each failure as a finding.

## 5. Run automated guardrails, export, and embed

1. Run the structural checker on each HTML file, with one `--forbid` value for each term the page
   must not show. Fix or record each failure as pass 4 step 4 directs, and after a fix repeat pass 4
   and this step.
2. Export the requested PNGs and extract the requested embed blocks under **Export and embed
   hygiene**, and open each output to confirm it is complete.
3. Deliver the report for the mode. Use these forms unless the user or a project requirement
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
- [ ] **Grounded truth**, including placeholders, omissions, status marks and source links.
- [ ] **Illustration over text**, for every section, figcaption and label.
- [ ] **Maximum clarity**: theses, splits, focal hierarchy and terms.
- [ ] **Maximum readability**: layouts, the wide, narrow and single-layout font floors, text boxes,
  `aria-label` text, motion, and visibility without JavaScript.
- [ ] **Editorial aesthetics**: palette, contrast, banned effects, tokens, legend and color pairing.
- [ ] **Generator first**, including the two-run comparison.
- [ ] **Offline single file**: one file, inline CSS and SVG, system fonts, and no external or
  out-of-file asset beyond one the user or a project requirement called for.
- [ ] **Browser verification**, or a report that it was not done.
- [ ] **Automated guardrails**, including each reported threshold or flag change.
- [ ] **Export and embed hygiene** for each PNG and embed block, including opacity `'1'` on each
  exported SVG and its ancestors and every SVG of each embedded figure.
- [ ] **Reference files**, each read as that section directs.
- [ ] **Pass 1**, with the fact table in working notes in Review.
- [ ] **Pass 2**, with the figure audit in Review.
- [ ] **Pass 3**, with the Review variant.
- [ ] **Pass 4**, including the reduced-motion, no-JavaScript and grayscale renders.
- [ ] **Pass 5**, including every field of the mode's report.
