# CLI dispatch hygiene

Use this reference when running a headless CLI as a subagent. `SKILL.md` assigns
the source, model family, effort and Fast scope; this file carries that
assignment into the invocation and checks the result. Apply the common guards
and the selected source's guidance on every dispatch.

Discover capabilities in the dispatch environment before using the source
guidance below. Confirm the installed product, its supported platform and
provider, current help/configuration schema, and a fresh applicable model
catalog. Use a flag, setting, output field or sandbox mechanism only when that
build and host support it. These are dispatch mechanisms, not requirements to
install a CLI or change persistent configuration. A catalog or configuration
records availability or selection; it does not prove which model or serving
tier handled a turn.

Shell commands below are **POSIX illustrations**, not universal command lines.
Replace placeholders and quote literal prompts, paths and JSON/TOML values for
the actual shell. Prefer an argument-vector process API when available. In
other shells or launchers, use their executable lookup, child environment and
stdin-close/null-input equivalents. Do not paste POSIX redirection or variable
assignment into a different shell unchanged.

## Rules for every CLI

- **Availability**: resolve and identify the executable in the child's runtime
  (`command -v` in a POSIX shell), then check platform support and a supported
  credential route using that invocation's environment, provider and settings.
  A binary on the parent machine does not establish access in a remote host,
  container or other runtime. Saved-login status alone does not validate or rule
  out per-run credentials. Diagnose credential and transport failures separately.
  Retry a failed catalog request through an already authorized network or proxy
  route where available, and disclose unresolved availability before falling
  back. Treat a family as absent only when a successfully retrieved applicable
  catalog contains no required top-tier model. Skip unavailable sources in the
  family's order; never substitute a forbidden tier.
- **Prompt and EOF**: pass literal prompt text as one argument and close unused
  stdin with the launcher's supported mechanism (`< /dev/null` in POSIX).
  Do not interpolate a brief as shell code. An open pipe can leave the child
  waiting for EOF. For a long brief, use the source's supported file/stdin route
  below and close that stream after the input. Put the prompt directly after the
  print flag, after `--`, or before any multi-value flag; Claude's
  `--allowedTools` and `--disallowedTools` can swallow a following prompt.
- **Configuration and environment**: discover the effective configuration roots,
  profiles, project settings, managed restrictions and precedence from supported
  flags, environment variables and documentation. A default home path is an
  example, not the active path on every machine. Prefer supported invocation-scoped
  overrides for the assignment. Preserve the already authorized credential,
  provider and network/proxy route needed by the child without exposing secrets.
  Check what a launcher actually forwards; do not assume parent environment or
  host settings reach a remote child. Reuse existing or already-authorized setup.
  Examples do not imply authorization for new login, proxy or persistent settings
  setup, and do not require such changes.
- **Model and effort**: pass them on every dispatch, using the newest required
  family in the source's current model list. Never rely on defaults or a router
  such as Cursor Auto or Devin `adaptive`/`fusion`. Use an alias only when its
  verified mapping selects the required version and tier; a bare family or
  partial name such as `gpt` does not guarantee tier, effort or speed. Spell
  effort exactly and check the selected model's support. A missing assigned
  level is a parameter gap: use the highest supported level at or below it and
  disclose the gap. If an ID is rejected, select the next-newest listed ID of
  the same family and tell the user; never let the CLI choose its default.
- **Fast**: enable it only inside the user's named scope. Explicitly select
  standard elsewhere, and use standard with disclosure when the assigned model
  has no Fast option on the selected source. Saved settings and defaults can
  affect headless runs. Keep the assigned family and effort. Report the
  established requested tier; claim actual serving only from authoritative run
  evidence. Without it, report “Fast requested, actual serving unconfirmed” or
  “Standard requested, actual serving unconfirmed”, matching the request.
- **Output and completion**: capture the final answer and check the exit status,
  stderr and terminal outcome; ordinary-looking text can describe a failed run.
  Allow multi-minute execution with a generous timeout or background execution
  and completion notification. A partial stream or truncated answer is not a
  completed deliverable.
- **Permissions**: select supported permission, trust and sandbox settings for
  the task and check the host's enforcement prerequisites. A named mode does not
  establish an operational sandbox on every OS, container or remote runtime.
  Unattended approval can deny, fail or wait, depending on the host. Grant only
  authorized access; use a bypass mode only in an isolated runner. If required
  isolation or tools are unavailable, disclose the limitation and use another
  authorized source or runtime rather than silently removing protection.
- **Reviewers running code**: give a reviewer or verifier its own disposable
  `git worktree` or artifact copy and the access needed for tests, builds or
  reproductions. Where supported and authorized, use Codex workspace-write with
  required network access, Cursor allow rules or force, or Claude acceptEdits
  plus shell allow rules. Verify the host's effective enforcement. The brief
  prohibits editing the deliverable; never grant write access to the shared tree.
  If it cannot execute, its verdict is low confidence.
- **Leaf delegates**: a non-bare child can load home and project instructions,
  skills and subagents, including burst/proxy. Every brief prohibits further
  delegation unless expressly permitted. Removing Claude's native `Agent` and
  `Workflow` tools does not prevent Bash/CLI delegation; the brief must cover
  every route.
- **Rework**: check the installed resume interface, then resume the worker's own
  session with the reviewer's issues verbatim and repeat the same model, effort,
  tier, permissions and output settings.
  Claude uses `--resume <session_id>` from JSON `.session_id`; Codex uses
  `codex exec [exec-level options] resume <SESSION_ID> "<issues>"`, with the ID
  from `thread.started.thread_id` (capture `--json` when rework is possible).
  Put exec-level options such as `--sandbox` before `resume` when its subcommand
  lacks them. Cursor's supported `--resume <chatId>` uses output `session_id`;
  Devin's supported resume form is `-r <SESSION_ID>`. Check print-mode resume
  support on the installed build: try once, then dispatch fresh if it errors or
  ignores print mode. If any resume
  fails or no ID was captured, provide the original brief, current artifact and
  issues to a fresh worker; never send the issues alone.

## Claude Code: `claude -p`

Read the [headless](https://code.claude.com/docs/en/headless),
[model](https://code.claude.com/docs/en/model-config),
[effort](https://code.claude.com/docs/en/effort) and
[subagent](https://code.claude.com/docs/en/sub-agents) references when checking
a new build or provider. Discover settings through the
[settings reference](https://code.claude.com/docs/en/settings), including a
supported `CLAUDE_CONFIG_DIR` override rather than assuming a home location.

- **Invocation**: where those options are supported, use
  `claude -p "<prompt>" --model <model-id> --effort <level>
  --output-format json < /dev/null`. For a long brief, use
  `claude -p "<instruction>" < brief.md`; piped stdin adds input beside the
  argument. Keep the prompt before multi-value tool flags.
- **Model**: `opus` selects the Opus version recommended by the installed build,
  subject to environment overrides and restrictions. Verify it is the newest
  required Opus; otherwise pin the full supported ID from `/model` or the model
  configuration reference. `ANTHROPIC_DEFAULT_OPUS_MODEL` repoints the alias;
  cloud providers can map it differently, so pin their full Opus ID. Do not use
  `best`, `default`, `opusplan`, `sonnet`, `haiku` or `fable` for delegated roles.
- **Effort**: where exposed, pass `--effort <level>` and unset
  `CLAUDE_CODE_EFFORT_LEVEL` for the child or set it to the same level, because
  it overrides the flag. Check stderr and effective settings: builds can ignore
  an unknown flag value, emit `Unknown --effort value`, and still exit 0 while
  environment/settings/default effort remains in effect.
  Unsupported levels use the highest supported at or below the request.
  Inspect the effective cap: settings and organization limits take the lowest
  applicable cap across scopes, with `modelSettings.<model>.maxEffortLevel`
  replacing the same file's top-level cap for that model. Caps constrain flag,
  environment and frontmatter routes. Organization-cap warnings are suppressed
  in JSON output. Disclose any lower effective level as a parameter gap.
  `ultracode` is a separate mode, not an effort level.
- **Auth**: `claude auth status` returns 0 for a login and 1 otherwise; JSON
  `authMethod` identifies the method. `ANTHROPIC_API_KEY` takes precedence over
  subscription login in `-p`; `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`
  can replace browser login. `--bare` ignores OAuth/subscription credentials and
  skips automatic CLAUDE.md, skill, hook and subagent discovery. Supply an
  Anthropic API key through `ANTHROPIC_API_KEY` or an `apiKeyHelper` in
  `--settings`; Bedrock, Vertex and Foundry retain provider authentication.
  Select bare mode only when intended and supported credentials exist. It is
  not the current default. If status passes but the child reports missing auth,
  check its bare/SIMPLE mode, provider and credential selection; resolve the
  mismatch or treat this invocation as unavailable.
- **Permissions**: pass a mode explicitly. Use `--permission-mode acceptEdits`
  for an editing worker with `--allowedTools` for required shell commands, such
  as `--allowedTools "Bash(git *)"`. Use `dontAsk` plus allow rules to deny calls
  that would need approval while allowing actions requiring none. Without a
  permission host, unresolved `-p` prompts are denied; an Agent SDK host or
  `--permission-prompt-tool` can instead wait. Where available, pass
  `--permission-prompts none` for unattended runs; it also removes
  person-dependent tools such as
  `AskUserQuestion`, and denied tools can still prevent completion. Reserve
  `--dangerously-skip-permissions`/`bypassPermissions` for an isolated container
  or VM as a non-root user. A leaf also needs `--disallowedTools Agent Workflow`
  after the prompt, plus the brief's prohibition on all delegation routes.
- **Fast selection**: there is no dedicated flag or Fast model ID. Request it
  for one run with `--settings '{"fastMode": true}'`, and unset
  `CLAUDE_CODE_DISABLE_FAST_MODE` for that child. This session setting is not
  saved. Request standard with `CLAUDE_CODE_DISABLE_FAST_MODE=1`; no settings
  key overrides that switch. `--settings '{"fastMode": false}'` is a weaker
  session-only off setting. Fast is offered only for supported Opus models via
  Anthropic API/subscription, not cloud providers; organizations can block it.
  Managed `fastModePerSessionOptIn: true` blocks it in `-p` even with settings.
  Interactive `/fast` saves a home setting. An ordinary local non-interactive
  run outside a cloud session requires its own settings opt-in, but use the off
  switch on every out-of-scope run rather than depending on that gate.
- **Native Fast dispatch**: custom frontmatter, `--agents` JSON and `Workflow`
  options have no per-agent Fast field. Children copy the session Fast flag.
  Use `claude -p` with Fast on for in-scope roles, and with the off switch for
  out-of-scope roles when the parent is fast, as `SKILL.md` requires.
- **Output and verification**: plain `-p` prints final text; JSON puts it in
  `.result`. Check exit status before accepting it. For current-invocation
  model evidence, capture `--output-format stream-json --verbose` and read
  `.message.model` on assistant records whose `parent_tool_use_id` is null.
  `.modelUsage` is cumulative on resume and does not alone prove which model
  ran this invocation; compare prior totals. A small Haiku usage entry can be
  auxiliary and does not alone establish a delegated Haiku run. Print mode can
  wait for background subagents/workflows up to
  `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`.

  Check `fast_mode_state` (`on`, `off`, `cooldown`) and
  `fast_mode_disabled_reason` on init/result events, then each main-loop
  request's `usage.speed` (`fast`, `standard`, null). State `on` alone is
  insufficient: exhausted credits can leave it on while requests use standard;
  rate limits can also cause standard requests during cooldown. Unsupported
  models and fallback retries can run standard, and enabling Fast from an
  unsupported model can switch to the default Fast Opus. Check the main-loop
  model as well as request speed. Report partial Fast service when the records
  show a mixture; if the build lacks these fields, report only the request.

## Codex: `codex exec`

Use the [configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[precedence](https://learn.chatgpt.com/docs/config-file/config-basic),
[environment](https://learn.chatgpt.com/docs/config-file/environment-variables),
[non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode),
[subagent](https://learn.chatgpt.com/docs/agent-configuration/subagents) and
[API Fast](https://developers.openai.com/api/docs/guides/fast-mode) references
alongside the installed CLI's help. Resolve the active state/configuration root,
including a supported `CODEX_HOME` override. Check
[platform sandbox prerequisites](https://learn.chatgpt.com/docs/agent-approvals-security)
before relying on a sandbox mode.

- **Invocation**: `codex exec -m <model-id>
  -c model_reasoning_effort=<level> -o <file> "<prompt>" < /dev/null`. A prompt
  argument with nonterminal stdin still reads to EOF and appends that input;
  always close stdin. For a long brief, use `codex exec - < brief.md` with the
  other assignment flags. Outside a Git repository, pass
  `--skip-git-repo-check`.
- **Model**: always pass `-m` because omission uses effective configuration and
  built-in defaults. Pin the newest full Sol ID from the current launcher,
  interactive `/model` picker or fresh applicable account catalog; no family
  alias is documented. `codex debug models --bundled` and the documentation's
  Models page describe capabilities, not account access. Never pick Astra,
  Luna or `-mini`. A failed fetch or bundled fallback does not prove account
  unavailability; only a successful applicable catalog lacking Sol establishes
  that the family is absent.
- **Effort**: use `-c model_reasoning_effort=<level>`; there is no dedicated
  effort flag. Check the model's advertised levels in `/model` or the catalog.
  Supported models/clients can offer `ultra`, including proactive delegation
  in applicable interfaces; retain the table's assigned `max` when it asks for
  `max`. Configuration-layer acceptance of an effort string does not prove
  backend acceptance or clamping. Do not invent a level or assume
  unsupported-level behavior. Omission can select an effort as low as
  `low`; explicitly set the assigned supported level.
- **Auth**: `codex login status` returns 0 when saved credentials are present.
  Exec reuses them; `CODEX_API_KEY=<key> codex exec ...` supplies an API key for
  one run. Apply the common availability check to the selected credential route.
- **Permissions**: pass `--sandbox read-only` for research that must not write
  or `--sandbox workspace-write` for authorized edits and disposable test runs.
  The documented built-in exec default is read-only, but configuration can
  override it. Where `--approve-for-me` is exposed with automatic approval review
  and workspace-write, do not combine it with a read-only option expecting
  read-only precedence. When human approval cannot be surfaced, an action can
  fail. Network depends on effective configuration and managed policy;
  `-c sandbox_workspace_write.network_access=true` requests outbound command
  access where allowed. Reserve `danger-full-access` and
  `--dangerously-bypass-approvals-and-sandbox`/`--yolo` for isolated runners.
  Follow installed help for flag placement: where approval is a global option,
  put `-a`/`--ask-for-approval` before `exec`; where sandbox is exec-level only,
  put `--sandbox` before `resume`. Do not require the retired `--full-auto`
  compatibility flag or assume another build accepts it.
- **Fast selection**: keep the same model ID. Where the installed schema and
  selected provider support these keys, request Fast per run with
  `-c service_tier=fast -c features.fast_mode=true`; request standard with
  `-c service_tier=default`. If the supported interface differs, use its verified
  equivalent or report the gap. Never use `ultrafast` or `flex` under this policy.
  Check effective settings, profiles, feature gates, managed restrictions and
  the model's advertised tiers; explicitly select the required tier on new and
  resumed runs. Do not rely on interactive `/fast` storage or TUI defaults to
  configure exec. An omitted service tier can inherit Project Fast.
- **Native Fast dispatch**: use native dispatch only when an explicit request
  setting, host request contract or verified inheritance establishes the role's
  assigned requested tier. Set exposed model and effort parameters and inspect
  fork restrictions. Capability advertising alone is insufficient. Verified
  inheritance that matches the assignment can carry it without a separate
  tier selector. Otherwise use exec with explicit tier settings and disclose
  the route; independently request standard for an out-of-scope role if native
  dispatch would select Fast. Verify the current host rather than assuming
  root-tier inheritance or overwrite behavior.
- **Output and verification**: progress goes to stderr; stdout and
  `-o`/`--output-last-message` contain the final message. `--json` emits JSONL;
  `--output-schema <file>` requests a final answer matching a JSON Schema.
  Treat nonzero exit or a failed terminal JSONL outcome as failure. Do not depend
  on one build's exact exit-code number. The exec header and usage events do not
  positively confirm the serving tier. Without an authoritative serving receipt, report
  the established requested tier and actual serving as unconfirmed, for both
  Fast and standard assignments. Do not promise an unsupported-tier warning
  or fallback without build-specific evidence. API Fast accepts `fast` and
  `priority`, but API-key auth alone does not establish how this build transmits
  its configured tier. Claim standard processing only from serving evidence.

## Cursor: `agent -p`

Check the [permissions](https://cursor.com/docs/cli/reference/permissions) and
[headless](https://cursor.com/docs/cli/headless) references against the installed
build. Their current descriptions conflict about behavior without `--force`;
omission is not a read-only guarantee.
Use the [configuration reference](https://cursor.com/docs/cli/reference/configuration)
to discover active global and project settings, including supported
`CURSOR_CONFIG_DIR` or platform-specific `XDG_CONFIG_HOME` overrides.

- **Invocation**: `agent -p "<prompt>" --model <model-id>
  --output-format stream-json --trust < /dev/null`. Probe `agent` and its legacy
  name `cursor-agent`; identify a generic `agent` binary from its product help
  or version output before using Cursor commands. Prompt stdin is undocumented,
  so use an argument and close stdin.
- **Model**: copy the newest required variant from `agent models` or
  `agent --list-models` and pass `--model` every time; fresh installs default to
  Auto. Builds that match exact catalog variants reject unmatched IDs with
  `Cannot use this model` and reject admin-blocked models rather than using
  the native subagent documentation's fallback behavior. A saved config model
  can be replaced by an allowed model, so explicit selection matters. Check
  the init event's display name against the requested family/version, then
  check serving evidence as described below.
- **Effort**: select an exact listed effort variant when the CLI exposes no
  separate effort flag; its ID carries effort and Max Mode. Some help versions
  advertise bracket parameters for context, effort and Fast. In builds that
  match the whole string to catalog variants, help syntax does not establish
  arbitrary bracket parsing. Do not compose an assumed variant: catalog strings
  need not all appear in the printed model list, so treat an unlisted bracket
  form as unconfirmed until validated by the supported interface. A mismatch
  can fail with `Cannot use this model`. In supported native subagent
  frontmatter, effort is a bracket parameter: `<model-id>[effort=high]`.
- **Auth**: `agent status --format json` (`whoami`) reports login. Scripts can
  use `CURSOR_API_KEY` or `--api-key`; otherwise saved `agent login` credentials
  apply. An unauthenticated run fails with `Not authenticated`.
- **Permissions**: an untrusted workspace needs `--trust` or `--force`.
  Print mode has write and shell tools. Grant required operations through allow
  rules or `-f`/`--force` (`--yolo`) as appropriate; omission of force does not
  prevent writes. Force automatically allows commands unless denied and
  approves trust and MCP prompts. Narrow rules use the active project or global
  configuration; `.cursor/cli.json` and `~/.cursor/cli-config.json` are documented
  default examples, subject to platform and root overrides. Deny wins. Web fetch
  needs a domain grant
  such as `WebFetch(<domain>)` or force. `--approve-mcps` approves MCP servers;
  where supported, `--sandbox enabled|disabled` selects sandboxing. Check its
  platform prerequisites and effective enforcement. The permissions page permits
  narrower grants while the headless page describes proposal-only behavior
  without force. Check the actual build and use an OS sandbox when writes must
  be prevented.
- **Fast selection**: Fast is a per-model parameter or listed variant; there is
  no dedicated CLI flag, environment variable or direct user config key. Copy
  an exact catalog Fast variant for in-scope runs and an exact standard variant
  outside scope. A listed `-fast` ID or accepted bracket variant can carry Fast;
  In builds that match whole strings to catalog variants, `fast=false` must also
  match one; otherwise use the installed interface's verified Fast-off form.
  Do not strip a
  suffix to derive standard unless that exact ID is listed as standard. Bare
  parameterized IDs can reuse saved per-model choices or server defaults,
  including Fast. Headless model selection can also update CLI configuration.
  If the Fast variant is unavailable, explicitly select standard and disclose.
- **Native Fast dispatch**: frontmatter documents `<model-id>[fast=false]` and
  `<model-id>[]` for standard. `<model-id>[fast=true]` follows SDK parameters
  but remains untested in a subagent file; a parent can name a model at launch.
  Do not use `inherit` or the undocumented `model: fast` form. Set each role's
  variant explicitly and inspect its task card because a saved/default or
  parent-selected Fast variant can differ from the intended setting.
- **Output and verification**: text is final text; JSON `.result` holds the
  answer but no model field. Stream JSON adds the init display name and terminal
  `result`. Reject nonzero exit or a stream lacking that terminal event. Runs
  wait for their own subagents before exit. Init `model` is built from the
  outgoing selection, and result `usage` holds token counts, not served model,
  variant or cost. Use the usage dashboard and native task card to check which
  variant ran. Until then, report the request rather than confirmed service;
  exact local ID matching alone does not prove backend identity.

## Devin: `devin -p`

Check [models](https://docs.devin.ai/cli/models),
[configuration](https://docs.devin.ai/cli/reference/configuration/config-file)
and [permissions](https://docs.devin.ai/cli/reference/permissions) when checking
a new account or build.

- **Invocation**: `devin --model <model-uid> --permission-mode <mode>
  --respect-workspace-trust false -p -- "<prompt>" < /dev/null`, under a timeout.
  Print mode runs one turn and prints the response; that alone does not prove
  useful completion. `--` separates the prompt from subcommands. For a long
  brief, use `--prompt-file <file>`. Prompt stdin is undocumented.
- **Model and effort**: fetch `devin models list --format json` with the planned
  account and copy the full UID for the newest required model and assigned
  effort. `--model` also accepts loose aliases, family slugs and partial names;
  do not use them. A latest-family alias can lag the catalog's newest version
  and leaves effort/speed ambiguous. Effort is encoded in the UID; no dedicated
  effort flag, environment variable or config key is exposed. Select a listed
  supported effort, never synthesize `<model>-<level>` from naming patterns.
  Interactive `Alt+T`, `/model` and `/fusion` controls do not set headless effort.
  Never use `adaptive` or `fusion` routers.
- **Defaults and resume**: pass the exact UID on new runs and resumes.
  `DEVIN_MODEL` or effective user/organization `agent.model` can select a
  default; the documented built-in default is a fast Cognition SWE model. A
  resume without `--model` keeps its saved model. Do not depend on unverified
  family-preference reuse. `/fast` switches to a fast Cognition model instead
  of selecting the current assigned model's Fast variant. `-c` is `--continue`,
  not a Codex-style configuration override.
- **Auth**: check the supported `devin auth status` with the child's effective
  configuration and existing credentials. No API-key environment route is
  documented for `-p`;
  `WINDSURF_API_KEY` is documented for ACP. Successful login can coexist with
  `CLI access is disabled for this user`; treat that invocation as unavailable.
- **Permissions**: print mode cannot show a workspace-trust prompt, so pass
  `--respect-workspace-trust false`. Headless approval behavior is not
  established; choose the narrowest applicable mode, such as `accept-edits`
  for edits or `normal` for read-only work. `dangerous` (`bypass`, `yolo`)
  auto-approves tools and belongs in an isolated runner. `autonomous` requires
  a sandbox and still prompts for edits. Organization deny/ask rules apply in
  every mode, including dangerous; set a timeout and treat a stall as failure.
- **Fast selection**: choose the exact catalog variant labelled Fast for the
  assigned model and effort, and its exact standard counterpart outside scope.
  There is no dedicated Fast flag/environment/config key. Suffixes are not the
  contract: a catalog can label either a `-fast` or `-priority` variant Fast.
  Copy the current catalog's exact UID and label instead of deriving or rejecting
  a UID from its suffix. An unlabelled speed variant, including
  an unverified `-ultrafast` UID, is unconfirmed. If no Fast counterpart exists,
  use standard and disclose. Treat rejection or fallback from the requested
  Fast UID as failure to carry that assignment, rather than assuming its tier.
- **Native Fast dispatch**: custom-subagent `model` uses the same UID as
  `--model`; a skill's model overrides the profile. Give each role a custom
  definition naming its exact variant. `subagent_general` inherits the parent
  model and does not independently establish the role's speed. Fast UIDs in
  custom frontmatter remain untested; inspect run evidence before claiming
  actual Fast service.
- **Output and verification**: print mode outputs the response, with no JSON
  response mode. `--export <path>` writes ATIF conversation data after each
  turn; whether it establishes served-model identity remains unconfirmed.
  Treat an output-limit warning or truncated response as incomplete and check
  exit status; no full exit-code contract is documented. Catalog UID/label
  establishes the offered variant, not actual serving; do not require a Fast
  boolean when the catalog identifies Fast through its label. Print output has
  no documented serving receipt.
  `/session-stats` reports billed-turn models in interactive/ACP hosts, not a
  documented print-mode receipt. Until authoritative run evidence exists,
  report model effort and tier as requested rather than confirmed.
