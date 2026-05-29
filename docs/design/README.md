# Design Principles

This directory holds the design-principle canon for the product. It defines the *why* behind every surface: the four pillars the product is built on, the lineages those pillars descend from, and the governing rules that resolve the conflicts between them when a real design decision is on the table. It is short, opinionated, and meant to be re-read — not skimmed once and forgotten.

## What this is and isn't

This is a direction-setting document set. It tells reviewers what the product should feel like, what tradition each design move descends from, and how to choose when the easy answer is to add more. It is not an implementation spec. It does not list tokens, components, or acceptance criteria. It does not replace any PRD. When a reviewer asks "is this the right move?" the answer lives here; when an engineer asks "what is the radius of a sheet?" the answer lives in `docs/prd/06-design-system-visual-spec.md`.

Two further things this set is not. It is not a brand guideline — there is no logo lockup, no voice-and-tone matrix, no marketing-site language. And it is not a research dossier — the lineages cited inside are named for orientation, not for completeness. The point of every section is to give a designer, an engineer, or a PM a sharper lens for the next decision they make.

## Canonical position

These docs sit *above* the design-system PRD. Principles set direction; the PRD encodes that direction as tokens, components, and acceptance criteria. The relationship is one-way: principles inform the PRD, the PRD does not inform the principles.

- `docs/prd/06-design-system-visual-spec.md` — the authoritative implementation contract. Owns color tokens, type stack, spacing scale, motion tokens, the component inventory, and the live-region announce model. Referenced throughout this doc set as "PRD 06."
- `docs/prd/01-core-chat-experience.md` — owns the chat renderer, streaming model, message-part schema, keyboard and accessibility baseline. Referenced as "PRD 01."
- `docs/prd/07-transparency-contract.md` — owns the transparency surfaces: which model answered, what it cost, when the served model differed from the requested one. Referenced as "PRD 07."

When this doc set and a PRD appear to disagree:

- For concrete values — token names, contrast ratios, component states, acceptance criteria — the PRD wins. File a rationale entry in `04-rationale.md` if a principle change is genuinely needed and amend the PRD in the same change.
- For direction — what restraint means here, where ornament is forbidden, what counts as warmth in this codebase — these docs win. The PRD is expected to follow.

The live implementation in `web/src/app/globals.css` is downstream of PRD 06. It is the source of truth for what is actually on screen today; it is not the source of truth for what the product is *for*. Token values, easing curves, and elevation tiers change as the system matures; the pillars are intended to outlast them.

## Document map

- `README.md` — this file. Orientation, canonical position, and how to use the set.
- `00-principles.md` — the four pillars, their lineages, and the five tensions with governing rules.
- `01-foundations.md` — how the pillars apply to the foundational layers: color, typography, spacing, motion, iconography. Translates principle into foundational vocabulary; defers token values to PRD 06.
- `02-patterns.md` — how the pillars apply at the surface and component level: chat surface, composer, transparency chrome, empty states, transitions.
- `03-anti-patterns.md` — failure modes. Things that violate the pillars in ways that are easy to ship and hard to walk back.
- `04-rationale.md` — recorded design decisions. Each entry names a choice, the alternatives considered, the principle that decided it, and the date.

Read the set in order the first time. After that, the pieces stand alone: a reviewer can jump straight to `02-patterns.md` for a composer question or `03-anti-patterns.md` to check an instinct, and trust that the principles behind them are stable.

## How to use these docs

- Before adding a new component or surface, read `00-principles.md` and the relevant section of `02-patterns.md`. If the move under consideration is not directly supported by an existing pattern, it probably needs a rationale entry before it ships.
- Before introducing a new accent, color, decorative element, or motion curve, read `04-rationale.md` to see what was already considered and rejected. Then read the tensions section of `00-principles.md`.
- If the proposal involves ornament — a flourish, a gradient that exists for its own sake, an icon that is decorative rather than functional, a motion that exists to be noticed — read `03-anti-patterns.md` first. The instinct is almost always wrong here, and the doc explains why.
- When reviewing a PR with visual or interaction changes, the four-pillar articulation in `00-principles.md` is the rubric and the tensions section is how disagreements get resolved. Cite the pillar or tension in the review comment so the reasoning is recoverable later.
- When writing or amending a PRD section that touches visual or interaction design, link back to the principle that motivates it. Principle without enforcement drifts; enforcement without principle ossifies.

## Audience

Design, engineering, and product. The pillars are written so a designer can use them to defend a decision in review, an engineer can use them to spot when a proposed change crosses a line, and a PM can use them to scope what is and isn't worth building. None of the four roles can ignore this document and still ship work that fits the product.

## Change protocol

These docs evolve through pull request, like any other code artifact. A new pillar, a renamed tension, or a reversed governing rule requires a corresponding entry in `04-rationale.md` naming the alternatives considered and the reason the change was accepted. The four pillars themselves are intended to be stable across the product's lifetime; if they move often, something is wrong with how they were articulated. When a change to these docs implies a change to PRD 06, both changes ship in the same PR.

When in doubt, subtract.
