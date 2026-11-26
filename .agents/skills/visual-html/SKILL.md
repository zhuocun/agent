---
name: visual-html
description: >-
  Create, edit and review HTML pages in which illustrations carry the
  explanation: inline SVG diagrams of architecture and system overviews,
  workflows, process and data flows, timelines and roadmaps, comparisons,
  explainers and visual one-pagers, in any human language. Use when asked to
  visualize, illustrate or diagram a system, plan, process or concept as an
  HTML page, turn notes or a document into a visual page, or redesign, polish
  or critique such a page for aesthetics, design taste, minimalism, clarity or
  readability. Do not use for multi-route web apps, single-page applications
  or UI component implementation; visual regression audits of a running web
  app; data charts, plots or dashboards drawn from datasets; editable files in
  a diagramming tool's native format; slide decks; or prose-only documents.
---

# Visual HTML

Act as the designer, builder and reviewer of HTML pages, in any human language, in which figures (illustrations drawn in inline SVG) carry the explanation.

**Priority order**, highest first: **highest aesthetics, highest design taste and minimalism → maximum clarity → illustration over text and minimal text → maximum readability**. When two rules conflict, follow the higher one.

## Standing rules

- **Highest aesthetics.** Make every page beautiful: a cohesive palette chosen for the subject and set on the page background, a refined type scale, balanced composition, and a precise, consistent finish on every line, shape and label.
- **Highest design taste.** Make each choice as a leading information designer would: restraint before decoration, one coherent visual language across the page, and every color, weight, shape and effect present because it serves the content.
- **Minimalism.** Strip every figure down to what carries meaning: generous open space, clean uncluttered structure, light or implicit framing instead of stacked borders and boxes, and restrained visual elements with no filler.
- **Maximum clarity.** Give each figure one message and an unmistakable visual hierarchy, so that the focal elements stand out at first glance and supporting context recedes. Fit each figure's form and proportions to the natural shape of its content, such as a timeline drawn horizontally or a hierarchy drawn as a tree. Lay the page out cleanly, with aligned elements, consistent spacing and one name for each concept.
- **Illustration over text.** Let figures carry the explanation: draw structure, flow, sequence, hierarchy and comparison instead of describing them.
- **Minimal text.** Limit the text outside and inside the figures to a short heading per section, at most one framing sentence per section, the shortest label that names each element, and the few statements that no figure can show.
- **Maximum readability.** Make every word readable at a glance at every width the page is viewed at, from desktop to phone: type large enough to read without zooming, strong contrast with its background, and no clipped, overflowing or overlapping text. Route no line through a label or a shape it does not connect.
- **Warm white background.** Use warm white `#FAF9F6` as the page and figure background unless the user asks for another.

## 1. Frame

1. Identify the audience, the page language and the message of the page.
2. Read the material the page must show, and choose for each section the figure form that shows its message most clearly.
3. Outline the page, or in a review identify its outline: each section's heading, its framing sentence if it needs one, and its figure.

## 2. Craft

In a review, skip this pass.

1. Define the visual language once: palette, type scale, shapes, line styles and spacing.
2. Build the page as HTML with each figure drawn in inline SVG, applying the visual language and every standing rule to every figure.
3. When editing a page, keep what already meets the standing rules and change the rest.

## 3. Look and refine

1. Render the page and look at it at a desktop width and at a phone width.
2. Judge every figure and the whole page against each standing rule.
3. When creating or editing, fix each shortfall and repeat steps 1–2 until the page meets every standing rule. In a review, report each shortfall with its fix, ranked by the priority order, and edit no file.
4. If you cannot render the page, say so in your reply and report the visual check as not done.

## Self-check

Before declaring the task done, confirm that each rule or pass named below holds as its section states it:

- [ ] **Highest aesthetics**: cohesive palette on the page background, type scale, composition and finish.
- [ ] **Highest design taste**: restraint, one visual language and purposeful choices.
- [ ] **Minimalism**: generous open space, uncluttered structure, light or implicit framing instead of stacked borders and boxes, and no filler.
- [ ] **Maximum clarity**: one message per figure, unmistakable hierarchy, natural form and proportions, clean layout and one name per concept.
- [ ] **Illustration over text**: figures carry the explanation, with structure, flow, sequence, hierarchy and comparison drawn.
- [ ] **Minimal text**: a short heading and at most one framing sentence per section, the shortest label for each element, and only the statements that no figure can show.
- [ ] **Maximum readability**: every word readable at a glance at every width, type readable without zooming, strong contrast, no clipped, overflowing or overlapping text, and no line through a label or shape it does not connect.
- [ ] **Warm white background**: `#FAF9F6` as the page and figure background unless the user asks for another.
- [ ] Pass 1: audience, language and message identified, material read, figure forms chosen, and an outline drafted or, in a review, identified.
- [ ] Pass 2: skipped in a review; otherwise one visual language, HTML with inline SVG, and edits that keep what meets the standing rules.
- [ ] Pass 3: both widths rendered, every rule judged, and shortfalls fixed or, in a review, reported with fixes by priority and no file edited; a page you could not render stated in your reply, with the visual check reported as not done.
