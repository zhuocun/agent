# Repository workflow

Apply this reference only to maintenance or distribution work in the `agent-skills`, `agent` and `pulse` repositories. Follow each checkout's applicable `AGENTS.md` and the user's task scope. Use commit, pull request and publication steps when the task authorizes them; loading this reference supplies procedures, not additional authorization.

## Canonical files and distribution

- Make canonical skill changes in `agent-skills/.agents/skills/<name>/SKILL.md` and its supporting files. Keep `agent-skills/.claude/skills` as a symlink resolving to `.agents/skills`.
- Use `agent-skills/README.md` for exact local clone-and-link instructions. Symlinked consumers receive changes after pulling the canonical repository.
- Treat `agent/.agents/skills/` and `pulse/.agents/skills/` as copies, not symlinks. Copy canonical changes into them when synchronization is in scope; a canonical merge alone does not update these copies. Their weekly `skills-drift` checks compare the skills they hold against canonical `main`.
- When editing `.agents/skills/communicate/SKILL.md`, update `.claude/output-styles/baseline.md` in the same repository. Preserve the output style's own frontmatter and H1; make its remaining body equal the source body after removing the frontmatter, H1 and one following blank line, including trailing blank lines. When syncing `agent` and `pulse`, verify their baseline bodies too: `skills-drift` does not check this mirror. In the canonical repository, `.claude/settings.json` selects the `Baseline` output style.

## Validation

Run `python3 scripts/validate_skills.py` from `agent-skills` before pushing. It requires PyYAML and checks skill presence, YAML mapping and required fields, the description length cap, directory/name agreement, opening H1, `## Self-check`, the `.claude/skills` symlink and the output-style mirror. Inspect routing, instruction quality and behavioral preservation separately; the validator does not establish them.

The canonical `.github/workflows/validate-skills.yml` runs on pull requests and pushes to `main`; a branch push without an open pull request does not trigger it. Check current local instructions and workflows for additional gates in each repository. For copied distributions, verify the intended file inventory, contents and modes against the canonical source as well as the baseline mirror.

## Commits, review and merge

- Keep one concern per pull request; use a larger pull request only when its commits share one integration story, with one logical commit per concern. Write an imperative commit subject and a concise body explaining why. Omit AI model identifiers from commits, pull request titles and bodies, and code comments.
- Run normal hooks. Do not use `--no-verify` or `--no-gpg-sign`. If a pre-commit or commit-msg hook fails, fix the cause and make a new commit instead of amending past the failure.
- After opening a pull request, monitor its checks. Fix failing CI and confirm all required checks are green before squash-merging. Confirm success from current check results; an absence of failure notifications does not establish success.
- Treat merging canonical `main` as publication. Complete the distribution work required by the task and verify the resulting copies against the intended canonical revision.
