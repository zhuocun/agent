<!--
PR conventions (see AGENTS.md → "Repo conventions"):
- One concern per PR; squash-merge for a clean `main` history. A multi-concern
  burst is OK only when the changes share one integration story — then use
  logical commits, one per concern (+ an optional cleanup commit).
- Imperative subject; concise body explaining WHY. Never name AI models in the
  title, body, commits, or code comments.
- Merging to `main` triggers the FE (Vercel) + BE (Fly) auto-deploy, so green
  CI is the merge gate.
-->

## What & why

<!-- One paragraph: what this changes and the motivation. Explain the WHY. -->

## Scope

- Surface(s) touched: <!-- web/ (FE) · api/ (BE) · docs/ · .github/ · other -->
- Single concern? <!-- yes / no — if no, describe the shared integration story -->

## Changes

<!-- Bullet the notable changes, one per line. -->
-

## Testing

<!-- Evidence the change works: commands run + results, screenshots/video for UI. -->
- API: `cd api && uv run ruff check . && uv run mypy app && env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY uv run pytest`
- Web: `cd web && pnpm lint && pnpm build`
- E2E: `cd web && pnpm test:e2e`

## Deploy / migrations

- [ ] No new Fly secret required — or it is staged **before** merge (`flyctl secrets set --stage KEY=value -a olune-agent-server`), since a missing secret can fail `assert_prod_safe()` on boot.
- [ ] No DB migration — or a new Alembic revision under `api/alembic/versions/` linearizes cleanly on the current head and runs via the Fly `[deploy] release_command`.

## Pre-merge checklist

- [ ] One concern (or a justified multi-concern burst with logical commits).
- [ ] Imperative subject; body explains the WHY; no AI-model identifiers anywhere.
- [ ] Required checks green: **api**, **web-e2e**, **web-coverage** (these gate the `deploy-api` job).
- [ ] Docs updated when behavior/config changed (AGENTS.md, README, `docs/**`).
- [ ] Ready to **squash-merge** once CI is green (watch checks; fix red rather than leave it stranded).
