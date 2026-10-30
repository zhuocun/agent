# Field notes

Keep small, dated Cursor Harness facts here when no topic reference fits. Follow [maintenance](../SKILL.md#maintenance) when related notes accumulate.

Entry format:

```markdown
### <short imperative title>
- **Status:** verified YYYY-MM-DD | documented | unverified
- **Fact:** describe the behavior and the conditions in which it applies.
- **Do:** the rule to follow.
```

### Quote tmux exact-match targets in zsh
- **Status:** verified 2026-10-12
- **Fact:** zsh expands an unquoted leading `=word` into a command path. An unquoted tmux exact-match target fails with `name not found`.
- **Do:** Write `-t '=name'` or `-t "=$S"`. Check the shell with `echo $0` first. Bash does not perform this expansion.

### Do not split command strings through variables in zsh
- **Status:** verified 2026-10-12
- **Fact:** zsh does not word-split unquoted `$VAR`. The command `CMD="tool --flag"; $CMD` tries to run a program literally named `tool --flag`.
- **Do:** Use an array (`CMD=(tool --flag); "${CMD[@]}"`) or call the tool directly.

### Use printf to pipe captured JSON in zsh
- **Status:** verified 2026-10-12
- **Fact:** zsh's builtin `echo` interprets backslash escapes. The command `echo "$out" | node ...` turns `\n` inside JSON strings into raw newlines, and `JSON.parse` fails with "Bad control character".
- **Do:** Pipe with `printf '%s' "$out"`, or pipe the command directly without a variable.

### Quote heredoc delimiters when the body has backticks or `$`
- **Status:** verified (before 2026-10-12)
- **Fact:** With an unquoted delimiter (`<<EOF`), backticks and `$()` in the body run as commands.
- **Do:** Use `<<'EOF'` for literal text.

### Expect a Codex workspace-write sandbox to keep `.agents` read-only
- **Status:** verified 2026-10-12
- **Fact:** A Codex CLI run with `--sandbox workspace-write` and approvals disabled could not write files under the workspace's `.agents/` directory ("writing outside of the project"), even though the directory was inside the working directory.
- **Do:** For edits under `.agents/`, have the agent deliver a patch and apply it yourself, or grant a sandbox that permits the write. Smoke-check that the first edit landed.
