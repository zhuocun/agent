# CLI dispatch hygiene

Mechanics for spawning Claude Code / Codex CLIs headlessly as subagents (**Subagent source** rule 2). A spawn that works in a terminal can hang or mis-parse when launched headless. Apply every guard on every dispatch:

- **Stdin**: an open, writer-less pipe makes both CLIs block waiting for EOF. Feed the prompt on stdin so it also delivers EOF (`echo "<prompt>" | claude -p`), or close stdin explicitly for Codex's positional prompt (`codex exec "<prompt>" < /dev/null`).
- **Claude variadic flags**: `--allowedTools` takes space-separated values (`--allowedTools Read Edit "Bash(git *)"`), so a trailing positional prompt is swallowed. Put the prompt first (`claude -p "<prompt>" --allowedTools Read Edit`) or deliver it on stdin.
- **Model slugs**: prefer aliases that auto-resolve to the latest — `claude --model opus`/`sonnet`; Codex reads `model` from `~/.codex/config.toml`, override with `codex exec -m <model>`. Pin a full slug only for a specific version; if one is rejected, fall back to the account's configured model and note the substitution.
- **Reasoning effort**: defaults are not high — set it explicitly. Claude: `claude --effort high` (levels `low`…`xhigh`/`max`, model-dependent). Codex: `codex exec -c model_reasoning_effort=high "<prompt>"`.
- **Output capture / timeouts**: capture just the final answer where supported — `codex exec --output-last-message <file>`, or `claude -p --output-format json` and read `.result` (plain `-p` already prints only the final text). Expect multi-minute runs; set generous timeouts or poll in the background.
