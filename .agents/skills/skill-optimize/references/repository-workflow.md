# Repository workflow

Apply this reference only to maintenance or distribution work in the `agent-skills`, `agent` and `pulse` repositories. Follow each checkout's applicable `AGENTS.md` and the user's task scope. Use commit, pull request and publication steps when the task authorizes them; loading this reference supplies procedures, not additional authorization.

## Canonical files and distribution

- Make canonical skill changes in `agent-skills/.agents/skills/<name>/SKILL.md` and its supporting files. Keep `agent-skills/.claude/skills` as a symlink resolving to `.agents/skills`.
- Use `agent-skills/README.md` for exact local clone-and-link instructions. Symlinked consumers receive changes after pulling the canonical repository.
- Treat `agent/.agents/skills/` and `pulse/.agents/skills/` as copies, not symlinks. Copy canonical changes into them when synchronization is in scope; a canonical merge alone does not update these copies. Their weekly `skills-drift` checks compare the skills they hold against canonical `main`.
- Treat `.claude/output-styles/baseline.md` as compiled output; do not edit its body by hand. After editing any file in `.agents/skills/communicate/`, run `python3 scripts/sync_output_styles.py` from `agent-skills`. It keeps the output style's own frontmatter and `# Baseline` H1, compiles the body from `communicate/SKILL.md` and `communicate/references/asd-ste100.md`, strips the skill-only `Reload after truncation` rule, and inlines the reference file's rules and its check, so the output style holds no relative link and no `references/` path. Run it with `--check` to report drift without writing; the check exits non-zero when `baseline.md` is stale. When syncing `agent` and `pulse`, copy the whole `communicate/` directory, then copy the compiled `baseline.md` or run the script with `--root <checkout>`, and verify the result with `--check`: `skills-drift` does not check `baseline.md`. In the canonical repository, `.claude/settings.json` selects the `Baseline` output style.

## Validation

Run `python3 scripts/validate_skills.py` from `agent-skills` before pushing. It requires PyYAML and checks only these: each skill directory has a `SKILL.md` of at most 500 lines; the frontmatter parses as a YAML mapping with non-empty string `name` and `description`; the description is at most 1024 characters and contains no `<` or `>`; `name` equals the directory name and is 1–64 lowercase ASCII letters, digits and single hyphens, not starting or ending with a hyphen; `compatibility`, if present, is 1–500 characters; the body opens with an H1 and its last `## ` heading outside fenced code is `## Self-check`; relative path portions of inline-link and reference-definition targets recognized by its regexes in a skill's `.md` files exist, excluding recognized fenced code and inline code spans and without complete Markdown parsing, file-type checks or `#` anchor validation (relative links must still resolve to existing files; verify uncovered requirements by source review); every file under `references/` is linked, or named by its `references/` path in inline code, from `SKILL.md`; every reference `.md` file longer than 100 lines lists a link to each `## ` heading's anchor before its first `## ` heading outside fenced code; `.claude/skills` resolves to `.agents/skills`; and the `output-style-mirror` check holds.

The `output-style-mirror` check requires the following:

- If `.claude/settings.json` exists, it parses as a JSON object, and any `outputStyle` value is a non-empty string without surrounding whitespace.
- Both `communicate/` source files exist as valid UTF-8 with the anchors `scripts/sync_output_styles.py` requires to compile the mirrored body.
- `baseline.md`'s YAML frontmatter is a mapping with a non-empty `name` without surrounding whitespace (equal to that `outputStyle` when one is set), a non-empty `description`, and `keep-coding-instructions` set to boolean `true`.
- `baseline.md`'s body opens with a matching `# <name>` H1, and below that H1 (skipping one blank line if present) equals the compiled body.
- Outside fenced code, `baseline.md`'s frontmatter and body contain no `references/` path or `SKILL.md` mention, and, outside inline code spans as well, no relative Markdown link.
- The one bold label named by the `Reload after truncation` rule in `communicate/SKILL.md` equals the bold label of that file's final `## Self-check` item.

The validator does not count tokens: measure each edited body, below the frontmatter, with `tiktoken`'s `o200k_base` encoding. Inspect routing, instruction quality and behavioral preservation separately; the validator does not establish them.

Also run `python3 -m unittest discover -s scripts -p "test_*.py"` from `agent-skills` for the repository's own scripts, and `python3 -m unittest discover` in each `.agents/skills/*/scripts/` directory that holds `test_*.py` files. On pull requests and pushes to `main`, the canonical `.github/workflows/validate-skills.yml` first runs the skill script tests and then the repository script tests with the standard library only, then installs PyYAML, runs the repository script tests again and runs the validator, failing if any test run executes no tests; a branch push without an open pull request does not trigger it. Check current local instructions and workflows for additional gates in each repository. For copied distributions, verify the intended file inventory, contents and modes against the canonical source as well as the compiled `baseline.md`.

## Commits, review and merge

- Keep one concern per pull request; use a larger pull request only when its commits share one integration story, with one logical commit per concern. Write an imperative commit subject and a concise body explaining why. Omit AI model identifiers from commits, pull request titles and bodies, and code comments.
- Run normal hooks. Do not use `--no-verify` or `--no-gpg-sign`. If a pre-commit or commit-msg hook fails, fix the cause and make a new commit instead of amending past the failure.
- After opening a pull request, monitor its checks. Fix failing CI and confirm all required checks are green before squash-merging. Confirm success from current check results; an absence of failure notifications does not establish success.
- Treat merging canonical `main` as publication. Complete the distribution work required by the task and verify the resulting copies against the intended canonical revision.
