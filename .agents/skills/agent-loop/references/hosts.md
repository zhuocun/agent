# Host setup

Use the section for the current host and mode. Where continuation, the owner-ID route or completion wake is unverified, use the corresponding within-turn fallback in passes 2 and 5 until that capability is confirmed.

For Codex, Cursor, Antigravity and Devin, each live result below holds only for the CLI version, mode and flags it names, run with a fast model at low reasoning effort. Still unverified live: all IDE behavior; interactive-CLI continuation on Codex, Antigravity and Devin; host continuation caps above the observed consecutive counts, and every cap's configuration route and reset behavior; child-agent identity; custom IDs; and each further item a host section marks unverified.

- [Registration command](#registration-command)
- [Hook interface](#hook-interface)
- [Claude Code](#claude-code)
- [Codex](#codex)
- [Cursor](#cursor)
- [Antigravity](#antigravity)
- [Devin](#devin)

## Registration command

Use Python 3.8 or newer; the scripts need only the standard library. Set `SKILL_DIR` to the resolved absolute directory containing this skill's `SKILL.md`, `SCOPE` to the user or project scope chosen under pass 2's **Host** rule, and `WORKSPACE` to the workspace root.

The installer interface is:

```sh
python3 "$SKILL_DIR/scripts/install_hook.py" --host HOST --scope user|project [--workspace DIR] [--dry-run] [--uninstall]
```

Choose `codex`, `cursor`, `antigravity` or `devin` for `HOST`. If supplied, `--workspace` must name an existing directory; otherwise the project workspace defaults to the current directory's Git top level, or the current directory outside a repository. Use `--dry-run` to print `path: <absolute target path>` followed by the complete resulting JSON, indented by two spaces and ending with a newline, without writing; when an uninstall would delete the file, the line after the path is `delete`.

Use `--uninstall` to remove matching handlers, then every event list, matcher group, named group and `hooks` object left empty by that removal. If what remains is an empty object, uninstall deletes the file; otherwise, including a Cursor file left holding only `version`, it rewrites the file in the installer's two-space JSON formatting, so a file's original formatting does not survive install and uninstall. Before registering into a hand-formatted file, copy it if its exact bytes matter. When the file is missing or holds no matching handler, uninstall writes nothing, prints `No agent-loop hook for HOST found in PATH; nothing changed.` and exits 0.

The installer identifies its handlers by a command containing both `loop_hook.py` and a `--host HOST` argument followed by whitespace or the end of the command; a command edited or wrapped so that another character directly follows `HOST`, such as a closing quote, no longer matches. Installation replaces those handlers in place, preserves unrelated keys and entries, and is idempotent. It creates missing parent directories and writes atomically while retaining an existing file's permission bits. It refuses invalid or non-object JSON, including JSONC with comments, and incompatible container types it needs to edit, without changing the file. Exit codes are 0 for success, 1 for a refused file and 2 for usage errors, an invalid workspace or `--host claude`. Normal installation prints the target path and the host's activation guidance.

The registered command is `python3 <absolute path of scripts/loop_hook.py> --host HOST`, with the resolved path of the script beside the installer shell-quoted and a 30-second hook timeout.

## Hook interface

The hook interface is `scripts/loop_hook.py [--host HOST] [--state PATH]`. `HOST` accepts `claude` (the default), `codex`, `cursor`, `antigravity` or `devin`; `--state` overrides state-file discovery. Let the hook read one JSON event from stdin. It exits 0 and prints one JSON object followed by a newline. Errors, unknown hosts, unexpected, repeated or valueless arguments, and unaccepted events produce `{}`; an accepted Stop also produces `{}` when the queue guards do not grant continuation.

Without `--state`, discovery searches each host root in order, walking upward from each root through the first directory containing `.git`, inclusive, or to the filesystem root. It uses the first `.agent-loop.md` found:

| Host | Search roots, in order |
| --- | --- |
| Claude Code | Event `cwd`, then environment `CLAUDE_PROJECT_DIR` |
| Codex | Event `cwd` |
| Cursor | Strings in event `workspace_roots`, then environment `CURSOR_PROJECT_DIR` |
| Antigravity | Strings in event `workspacePaths` |
| Devin | Environment `DEVIN_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the hook process's current directory |

Continuation output carries the same `[agent-loop]` instruction in `reason` with `decision: "block"` for Claude Code, Codex and Devin; in `followup_message` for Cursor; or in `reason` with `decision: "continue"` for Antigravity. Devin's `SessionStart` response supplies identity context as its **Owner ID** rule describes, independently of any state file.

## Claude Code

- **Registration and activation:** use pass 2's frontmatter registration. There is no installer command for this host; the installer refuses `--host claude`.
- **Owner ID:** use `${CLAUDE_SESSION_ID}`. If that text appears unexpanded, read the environment variable `CLAUDE_CODE_SESSION_ID`.
- **Continuation limits:** apply the queue budget and pass 6's continuation-cap rule.
- **Completion wake:** use Bash with `run_in_background` for a waiter whose completion reports back to this session.

## Codex

Register with:

```sh
python3 "$SKILL_DIR/scripts/install_hook.py" --host codex --scope "$SCOPE" --workspace "$WORKSPACE"
```

- **Configuration:** expect `Stop` under `hooks` in `$CODEX_HOME/hooks.json` for user scope, defaulting to `~/.codex/hooks.json`, or in `<workspace>/.codex/hooks.json` for project scope. Skill frontmatter does not register Codex hooks.
- **Activation:** have the user open `/hooks`, select the handler, inspect it and press `t` to trust it. Project hooks also need a trusted project.
- **Modes and continuation:** in codex-cli 0.167.0, `codex exec` and `codex exec resume` fire the project Stop hook with `--dangerously-bypass-hook-trust` and project trust supplied through `-c`; under the same flags, an initial `codex exec` in a workspace without a project hook file fires the user Stop hook in `~/.codex/hooks.json`. On initial exec and exec resume, `decision: "block"` starts an automatic turn whose Stop has `stop_hook_active: true`, and each further grant started another, for two consecutive automatic turns from an initial exec and eight from one exec resume; `stop: done` returns `{}` with no automatic turn. The shared core supports interactive CLI continuation, but live interactive continuation and parity with exec remain unverified.
- **Trust side effect:** the `-c 'projects."<workspace>".trust_level="trusted"'` override is not transient. In 0.167.0, every `codex exec` and `codex exec resume` run with it persisted a `[projects."<workspace>"]` block with `trust_level = "trusted"` in `~/.codex/config.toml` and changed nothing else in that file. Tell the user before relying on this route; deleting exactly that block removes the persisted trust.
- **Owner ID:** read `CODEX_SESSION_ID` through a model-invoked shell command and use its value as `owner:`:

  ```sh
  printf '%s\n' "$CODEX_SESSION_ID"
  ```

  In the project exec configuration in **Modes and continuation**, the command's value equals Stop's `session_id`, which stays unchanged on exec resume. The 0.167.0 identity represents a shared session tree, not a unique concrete thread or fork; live child/fork behavior is unverified. Do not substitute `CODEX_THREAD_ID`.
- **Continuation limits:** let the hook budget govern; the 0.167.0 shared core has no numeric cap on consecutive Stop continuations. Live continuation beyond the eight consecutive automatic turns in **Modes and continuation** is unverified.
- **Completion wake:** do not rely on ordinary background `unified_exec` completion to wake an idle model. The 0.167.0 exit watcher emits a tool completion event but does not enqueue a model turn. In 0.167.0 `codex exec` and `codex exec resume`, the host terminates a still-running background `unified_exec` command when the turn completes, reporting exit code -1, and then exits; neither a background job nor a waiter outlives the turn, so wait for a result within the turn with a blocking command. Background-command lifetime in the interactive CLI and other client or daemon wake paths are unverified.

## Cursor

Register with:

```sh
python3 "$SKILL_DIR/scripts/install_hook.py" --host cursor --scope "$SCOPE" --workspace "$WORKSPACE"
```

- **Configuration:** expect `hooks.stop` in `~/.cursor/hooks.json` for user scope or `<workspace>/.cursor/hooks.json` for project scope. The installer supplies `version: 1` when that key is absent and preserves an existing value. The CLI skill loader does not register hooks from skill frontmatter.
- **Activation:** trust the workspace in the interactive CLI. Current IDE approval and trust procedures are unverified.
- **Modes and continuation:** in CLI 2026.11.05-86047df, the interactive CLI started with `--trust` runs the project `stop` hook, and the user `stop` hook in `~/.cursor/hooks.json` in a workspace without a project hook file. Its `followup_message` starts an automatic turn, including after the session's first prompted turn, and each further grant started another, with Stop's `loop_count` counting them: eight consecutive automatic turns, `loop_count` 1 to 8, with the installer's handler. `stop: done` returns `{}` with no automatic turn. Print mode (`agent -p`) never invoked the stop handler in the tested configurations: `--output-format stream-json`, initial runs and `--resume`, with and without `--force`. Run the loop in the interactive CLI; in print mode, run within turns. Current IDE end-to-end continuation is unverified.
- **Owner ID:** read `CURSOR_CONVERSATION_ID` through the agent's Shell tool:

  ```sh
  printf '%s\n' "$CURSOR_CONVERSATION_ID"
  ```

  Use this value for ordinary UUID CLI sessions: it equals Stop's raw `conversation_id` in the interactive project configuration in **Modes and continuation**, and its filesystem encoding leaves UUIDs unchanged. For custom IDs or IDE sessions, use only a value confirmed equal to that raw field. Equality is not guaranteed for custom IDs and is unverified in the current IDE; live resume and child-agent identity are also unverified. Do not use `generation_id`.
- **Continuation limits:** the installer sets the native stop handler's `loop_limit` to `null`, which removes that handler's native continuation limit. A host cap above the eight consecutive automatic turns in **Modes and continuation**, and behavior with a numeric or omitted `loop_limit`, are unverified.
- **Completion wake:** in the 2026.11.05 interactive CLI, when a command started with the Shell tool's background option (`block_until_ms: 0`) completes while the session is idle, the host injects a user-role message into the owning conversation and starts a new turn without human input. That turn's Stop has `loop_count: 0`, so the hook counts it as a non-automatic turn. The woken turn's Stop came about 11 seconds after completion; the turn's start latency is unmeasured. The implementation drops pending completions after a user-aborted turn; this is unverified live. An arbitrary detached process started with shell `&` has no established wake guarantee. Current IDE wake support is unverified.

## Antigravity

Register with:

```sh
python3 "$SKILL_DIR/scripts/install_hook.py" --host antigravity --scope "$SCOPE" --workspace "$WORKSPACE"
```

- **Configuration:** expect the named group `agent-loop` with a flat `Stop` handler array in `~/.gemini/config/hooks.json` for user scope or `<workspace>/.agents/hooks.json` for project scope. Use this configuration route; skill-frontmatter hook registration is unverified.
- **Activation:** if the CLI asks whether to trust the workspace, choose "Yes, I trust this folder". The print configuration in **Modes and continuation** loads project hooks without a pre-existing workspace entry in `trustedWorkspaces`; do not generalize that to other permission modes. In the IDE, inspect or toggle hooks through **... > Customizations > Hooks**; its exact project-trust approval procedure is unverified.
- **Modes and continuation:** in agy print mode (`-p --mode accept-edits`, with `--conversation` to resume), the project Stop hook fires on initial and resumed runs and `decision: "continue"` starts an automatic turn. In 1.5.2 this holds on resumed runs and on an initial run, where each further grant started another for two consecutive automatic turns. In 1.5.3, separate resumed runs produced eight and ten consecutive automatic turns, and on an initial run in a workspace without a project hook file the user Stop hook in `~/.gemini/config/hooks.json` fires, running with that configuration directory as its working directory, and its grant starts an automatic turn. With `stop: done`, Stop returns `{}` and no automatic turn follows. CLI interactive and IDE interactive hook support is documented, but live firing and parity with this print configuration remain unverified.
- **Owner ID:** in the CLI, read the command runner's injected `ANTIGRAVITY_CONVERSATION_ID`:

  ```sh
  printf '%s\n' "$ANTIGRAVITY_CONVERSATION_ID"
  ```

  In the print configuration in **Modes and continuation**, this value equals Stop's `conversationId`, and resumed Stops retain that ID. Reading the variable again after resume, child-agent identity, and the variable's availability and equality in IDE tool commands remain unverified live.
- **Automatic-turn tracking:** the hook uses the sidecar's optional `pending` marker because Stop has no established automatic-turn flag. A grant sets it to the conversation ID; a matching marker classifies the next Stop as automatic, and an owned Stop that permits ending clears it. The established print configuration includes this set-and-clear sequence. Known limit: when a host cap or user interruption suppresses a granted continuation without another Stop, as the 1.5.3 cap in **Continuation limits** does, the marker stays set and the next human turn can count once as automatic, so the no-progress guard can end continuation at most one turn early; send a further human message to reset that guard and resume.
- **Continuation limits:** in agy 1.5.3 print mode, the host ran ten consecutive Stop-hook continuations after a human turn and silently dropped the eleventh grant: no further turn ran, no limit message appeared, the process exited 0 with status `SUCCESS`, and the dropped grant still counted against the hook budget. The agent gets no turn after the drop, so pass 6's continuation-cap rule cannot run; the state recorded by the last iteration stands, and the user's next message resumes the loop. The CLI cap setting `maxStopHookContinuations` is present in the 1.3.3 implementation. The source and default of the observed value 10, the supported user-facing configuration route, reset behavior, the cap in 1.5.2 and the IDE's effective cap are unverified; do not invent a default or a flag to change it.
- **Completion wake:** in agy 1.5.3 print mode, a command started through `run_command` with a short `WaitMsBeforeAsync`, which the host runs as a background task, completed after the turn ended. The print process stayed alive, and the completion arrived as a system message that started a new model turn without human input; its first tool call came about 45 seconds after completion. A resume with `--conversation` displays a notice that background tasks were stopped, so do not expect a waiter to survive a resume; actual survival is untested. Wake in 1.5.2, in the interactive CLI and in the IDE is unverified. Stop's `fullyIdle` reports whether background work remains, not whether a particular queue waiter exists.

## Devin

Register with:

```sh
python3 "$SKILL_DIR/scripts/install_hook.py" --host devin --scope "$SCOPE" --workspace "$WORKSPACE"
```

- **Configuration:** expect both `Stop` and `SessionStart`, each using matcher groups with command hooks. User scope merges under `hooks` in `~/.config/devin/config.json`; project scope writes the hooks object directly to `<workspace>/.devin/hooks.v1.json`, without an outer `hooks` key. Use these hook files; skill-frontmatter registration is unverified.
- **Activation:** with workspace trust enabled, trust the directory interactively before using print mode; print mode cannot present the prompt and fails in an untrusted directory. `--respect-workspace-trust false` skips that check and is the explicit override used by the print configuration in **Modes and continuation**.
- **Modes and continuation:** in Devin 3000.12.17 print mode (`-p`, with `-r` to resume, and `--permission-mode accept-edits`), project hooks run with `--respect-workspace-trust false`, and so do the user hooks in `~/.config/devin/config.json` in a workspace without a project hook file. `Stop` fires on initial and resumed runs; on both, `decision: "block"` starts an automatic turn whose Stop has `stop_hook_active: true`, and each further grant started another, for two and four consecutive automatic turns from initial runs and eight from one resume. With `stop: done`, Stop returns `{}` with no automatic turn. `DEVIN_PROJECT_DIR` reaches the Stop hook and names the workspace, for project and user hooks. In the interactive CLI with `--permission-mode smart` and `--respect-workspace-trust false`, project `SessionStart` and `Stop` hooks fire; interactive continuation and parity with print mode remain unverified.
- **Permissions:** in 3000.12.17 print mode, `--permission-mode accept-edits` rejects every shell `exec` call, so the agent cannot run shell checks or start a waiter there. Use a permission mode that allows shell commands when items need them; in `smart` print mode, `exec` ran and the Stop hook fired, but continuation under `smart` is unverified.
- **Owner ID:** start a new session after registration and take the ID from the SessionStart context beginning `[agent-loop] This session's ID is <id>.` The registered hook returns that context through `hookSpecificOutput.additionalContext`; use the supplied ID for `owner:`. In the print configuration in **Modes and continuation**, the agent receives this ID and it equals later Stop events' `session_id`, including after `-r` resumes the same session. Child-agent identity remains unverified live. Do not substitute an inherited Claude session variable.
- **Continuation limits:** no numeric Stop-hook continuation cap is documented, and a cap above the eight consecutive automatic turns in **Modes and continuation** is unverified; do not assume unlimited continuation. Apply the hook budget and pass 6.
- **Completion wake:** Devin has no established shell wake route. In the 3000.12.17 interactive CLI in `smart` mode, a background `exec` command (`timeout: 0`) completed while the session was idle, and no Stop or model turn followed within about 130 seconds. In print mode the process exited before such a command completed, so print-mode wake is untested and the command's fate after exit is unknown. Background subagent completion notifies and resumes the parent through a separate mechanism; do not infer a shell-waiter wake from it.
