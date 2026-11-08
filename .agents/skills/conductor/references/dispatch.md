# Dispatch

Read this file in full before the first dispatch in a session and again after a compaction before the next dispatch. **Model selection** in `SKILL.md` says what each dispatch must carry; this file decides which source, route and workspace carry it, its model, effort and speed request, and its **Reporting** form.

- [Subagent sources](#subagent-sources)
  - [Claude Code routes](#claude-code-routes)
  - [Codex routes](#codex-routes)
- [Workspaces for concurrent writers](#workspaces-for-concurrent-writers)
- [Mapping to dispatch fields](#mapping-to-dispatch-fields)
- [Tiers and model IDs](#tiers-and-model-ids)
- [Task types](#task-types)
- [Fallbacks and effort limits](#fallbacks-and-effort-limits)
- [Speed modes](#speed-modes)
- [Reporting](#reporting)
- [Dispatch check](#dispatch-check)

## Subagent sources

Four sources can run a subagent when the host provides a supported in-product mechanism or headless CLI. **Task types**, **Fallbacks** and **Effort limits** decide each dispatch's model family and effort; this section decides which source carries it.

| Source | In-product mechanism | Headless CLI |
|---|---|---|
| Claude Code | the `Workflow` tool (`agent(prompt, {model, effort})` where the installed workflow API exposes those options), or a custom subagent whose frontmatter sets `model` and `effort`, dispatched through the `Agent` tool's `subagent_type`; a bare `Agent` call sets `model`, and `effort` only on builds that expose it | `claude -p` |
| Codex | native subagents with exposed `model` and `reasoning_effort`, or TOML custom agents with `model` and `model_reasoning_effort`; inspect launcher/fork restrictions | `codex exec` |
| Cursor | Cursor's Task-tool subagents (frontmatter `model`; effort and speed as bracket parameters, e.g. `<model-id>[effort=high,fast=false]`) | `agent -p` (legacy binary name `cursor-agent`) |
| Devin | Devin's subagents (custom-subagent frontmatter `model`; effort is encoded in the model ID) | `devin -p` |

Take the first available source in the family's order:

- **Claude-family models**: Claude Code → Devin → Cursor.
- **GPT-family models**: Codex → Devin → Cursor.

A mode-only route lets the caller pick a product mode that bundles model, effort and speed, but not a model or an effort; Devin child sessions are one. It is never a source's in-product mechanism, and it is the last resort: it ranks after every available route that carries the model per agent, the row's Fallback family included, and **Fallbacks** treats it as a source that offers no model of either family.

Resolve routes from the current host's exposed tools, permissions and installed CLI help. Tool names, arguments and commands in this skill describe supported routes, not capabilities every host provides. Honor concurrency and fork limits. A host without shell execution cannot use a CLI route; one without writable configuration cannot create file-based custom definitions. Carry the brief and required files through the chosen route, and verify the child can access them rather than assuming a shared filesystem or inherited tools, credentials and network.

When the source the family's order selects is the one you are running in, prefer its available in-product mechanism. Use that source's CLI only when the native route is unavailable or cannot carry the assigned model, effort and speed setting. Reach other sources through available CLIs. Resolve the executable in the invocation's actual environment, including any configured wrapper, and verify its supported syntax. Check a supported credential route with that invocation's provider, configuration and transport. Saved-login status alone does not establish availability. Do not assume installed CLIs, credentials, internet access or a proxy from another machine. Use only already authorized setup and network routes; availability checks do not authorize installation, login or changes to provider, permission or proxy configuration. Diagnose credential and transport failures separately; retry a failed catalog request through an already authorized network or proxy route where available. Treat a family as absent only when a successfully retrieved applicable catalog contains no required top-tier model (see **Tiers.**). Skip an unavailable source in the family's order; never substitute a forbidden tier.

### Claude Code routes

On Claude Code, when a bare `Agent` call exposes model but no effort parameter, use an available `Workflow` tool whose installed `agent()` options carry effort, or an effort-setting custom subagent dispatched through `Agent`'s `subagent_type`. Check that the host exposes the selected tool and fields before using them, and that neither `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` nor any workflow-specific model override the installed build documents makes the selected tool ignore the per-agent model.

**This skill requires explicit opt-in for `Workflow`, separately from the host's availability and permission checks. Opt-in starts when the user invokes or names this skill (for example `/conductor`), asks for subagents or a workflow, or enables Claude Code's ultracode mode. It stays in force for later tasks in the session and covers a workflow of any size, a single agent included. Loading this skill yourself does not establish opt-in. Without opt-in, use a custom subagent, or `claude -p` when a custom subagent is unavailable or cannot carry the assignment.**

Write each generated Claude custom definition under the active user configuration directory's `agents/<name>.md`, one file per model and effort pair. `CLAUDE_CONFIG_DIR` can relocate that directory; `~/.claude/agents/<name>.md` is the conventional default, not a fixed destination. Verify that the directory is writable and loaded by the session. Existing project `.claude/agents/` definitions may be selected, but write a project definition only when that repository change is already authorized. Otherwise use another available route. Verify scope and name precedence so the intended definition wins. Include required `name` and `description` plus `model` and `effort` in the frontmatter. Pass the brief as the `Agent` prompt. For a leaf, deny the available native delegation tools through the supported tool restrictions (`disallowedTools: Agent, Workflow` on hosts with those tools); also prohibit delegation through CLIs and other routes in the brief.

Check that the updated definition is discoverable before dispatch. Claude Code watches existing user-scope and project agent directories and uses edits on the next delegation. Restart when the directory did not exist at session start. Directories introduced by `--add-dir` or `/add-dir` are not watched, and `--disable-slash-commands` disables these watchers. Verify reload support for the running version; if a restart is unavailable, use another available route.

### Codex routes

On Codex, inspect the current host's launcher schema and configuration format. Use exposed model and effort parameters (for example `model` and `reasoning_effort`), or supported TOML custom agents with `model` and `model_reasoning_effort`. Resolve custom-agent discovery against the active user configuration root and project scope, and include that version's required fields. Keep generated definitions in a writable, loaded user scope; create or alter project definitions only when that repository change is already authorized. Otherwise use another available route. Hosts supporting the current standalone custom-agent discovery format require `name`, `description` and `developer_instructions` in each file; do not impose that manifest on a host using a different TOML role-config format. Fork controls vary by host: use `fork_turns: "none"` or a positive history count only when the schema exposes those forms and requires them for overrides. That requirement exists only where the host specifies that full-history forks inherit the parent's settings and reject overrides, so do not translate it into an unsupported argument on another host.

## Workspaces for concurrent writers

Where the shared environment caps parallelism and a worktree costs less to set up than the parallelism it buys, give each writing strand its own `git worktree` and record where each one is. A worktree holds tracked content only, so dependencies and other ignored files do not come across. Otherwise, and for every strand that only reads, work in the shared tree, and run writers concurrently when their files do not overlap.

## Mapping to dispatch fields

Map each assignment to the platform's fields: `model`, `subagent_type`, `effort`, `reasoning_effort`, or an effort level encoded in the model ID. On a mode-only route (see **Subagent sources**), map a delegated role to the product mode by applying the tier edges to the product's own description of its modes: use the standard full-capability mode, never a light or cheap mode (too-cheap edge), a premium mode above it (too-expensive edge) or a mode whose place stays unclear. **Advisor model** in `advisor.md` sets an advisor's mode. Never use a mode that exists mainly for speed unless the user's explicit speed instruction authorizes its serving tier, with a scope covering every model or naming that mode (see **Speed modes**). Setting every exposed parameter, refusing the platform default and the precedence of explicit instructions are stated under **Model selection** in `SKILL.md`.

## Tiers and model IDs

**Tiers.** Delegated work runs on the top tier: each provider's standard full-capability line, including its newer versions and any successor the provider presents as replacing it at the same place in its lineup, which today is Opus on Anthropic and Sol on OpenAI. The rule covers sidecar explorers too: read-only scouts probing in parallel, off the integration path. Place every model a provider offers, whatever its brand, against that line by the provider's own model list and description: the too-cheap edge is every model below it, such as `*-mini`, `*-haiku`-class, Sonnet-class and GPT Luna today; the too-expensive edge is every tier above it, oversized because its cost outruns its marginal value for delegated work, such as Fable and Mythos on Anthropic and Astra on OpenAI today; and a model whose place stays unclear is forbidden for delegated work. A role doing delegated work may be as strong as the orchestrator, capped at the top tier, so the too-expensive edge is forbidden for it even when the orchestrator runs on it. An advisor is the exception: **Advisor model** in `advisor.md` sets its model, and this cap does not apply. **Fallbacks** covers the case where no source offers a model of either family.

**Model ID.** Use the newest version of the family that the source offers, read from that source's own model list, never an ID remembered from earlier work or training. Use an alias that resolves to the latest version only when it cannot land on a forbidden tier; otherwise pin the full ID from the list. Never use a bare family alias such as `gpt`: it does not guarantee the required tier, effort or speed.

## Task types

**Task types.** Each delegated role runs the family and effort level of its row, neither lower nor higher, unless **Fallbacks** or **Effort limits** direct otherwise.

First choice is the family and effort to dispatch, Fallback the family and effort to dispatch when the first-choice family has no available source, and Includes, by example, what routes to the row; "Claude" and "GPT" mean each provider's top-tier line (see **Tiers.**).

| Task type | First choice | Fallback | Includes |
|---|---|---|---|
| Coding | Claude `medium` | GPT `xhigh` | any code deliverable, however small: writing or fixing code, tests, CI, infrastructure and other repository config, frontend implementation code with its styling, comments and docstrings in source, a script delivered to the repo |
| Coding documentation | Claude `high` | GPT `xhigh` | authoring or revising coding-related specifications, implementation plans, proposals and briefs, and developer-facing technical documentation such as setup, API usage, testing and maintenance guides (rule 1) |
| Review | GPT `xhigh` | Claude `high` | reviewers, verifiers, and reviews or audits of existing work, security review included (rules 3–4) |
| Backend architecture design | Claude `high` and GPT `xhigh`, both run (rule 6) | whichever one is available, alone | server-side and full-stack system design: service boundaries, data models and schemas, API contracts, storage and integration choices, and the review, verification or audit of that work (rules 4 and 6) |
| Visual design | Claude `high` | GPT `xhigh` | visual and interaction design of a product UI, visualizations that present information (diagrams, charts, HTML pages, slide decks) with the markup that draws them, design prototypes not meant to ship, and the review, verification or audit of that work (rule 4) |
| Documentation | GPT `xhigh` | Claude `high` | other prose documents, general agent operating instructions, UI strings and translations, in any language (rule 1) |
| Research | GPT `xhigh` | Claude `high` | sidecar explorers, exploration, data analysis, debugging or root-causing that reports a cause, reproducing a user-reported problem before any work exists |
| Brainstorming and discussion | Claude `high` and GPT `xhigh`, both run (rule 7) | whichever one is available, alone | brainstorming (generating ideas, options, names, hypotheses, test-case ideas) and multi-agent discussion, where agents read and respond to each other (debate, critique panel, deliberation) |
| Other simple work | GPT `high` | Claude `medium` | a single-step fact lookup, or any other task that is single-step, mechanical and verifiable in seconds (rule 2) |
| Other complex work | GPT `xhigh` | Claude `high` | client-only architecture (frontend state, data fetching, a CLI's module structure), a small task that turns on judgment, anything else no named row covers (rule 2) |

1. Classify each delegated role by the substance of its deliverable, independent of its recipient, filename, tools or intermediate steps. Code that ships in a product is Coding, including a fix that follows the worker's own investigation and a chart component. A visualization made to present information is Visual design, its markup included. A script or chart made only to get findings is Research. Authoring or revising prose that specifies or records code implementation or serves as developer-facing technical documentation is Coding documentation. Embedded code samples follow the prose's row. Architecture and design decisions use their own rows, including Other complex work for client-only architecture, regardless of document title or format.
2. Named rows win: Other simple work and Other complex work apply only when no named row matches. Other simple work needs all three of single-step, mechanical and verifiable in seconds; a single-step fact lookup is Other simple work, not Research; a sidecar explorer is Research whatever it looks up. Any other work no named row matches is Other complex work.
3. Reviewers and verifiers (see **Reviewer** in `SKILL.md`) go to Review, and so does any subtask whose deliverable is a review or audit of existing work, security review included.
4. A reviewer, verifier, review or audit of work on a design row stays on that row: Visual design, or Backend architecture design, which runs both families (rule 6). Key it on the row the reviewed work was routed to, or, for existing work, the row that work would route to. Every other review goes to Review (rule 3).
5. A subtask that spans rows is split by deliverable. A design runs on its design row, and its implementation then runs as Coding against the accepted design. A document's prose runs on the row its substance calls for under rule 1: Coding documentation, Documentation, or the row for its architecture or design work. Each visualization in it runs as Visual design, drawing what the prose sets out. A slide deck is one visualization.
6. Backend architecture design runs both families, Claude `high` and GPT `xhigh`, for design and review alike. A design is two workers, one per family, dispatched concurrently with the same brief; a review, verification or audit is two agents, one per family, judging the same artifact independently. The review passes only when both pass; a `revise` or `redo` from either sends the worker back with both reviewers' issues verbatim, and the pair counts as one review toward the two-failed-review stop. Each design passes its own review, then the orchestrator compares and synthesizes the designs. A backend or full-stack design stays on this row when agents discuss it.
7. Brainstorming and discussion runs both families: at least one agent per family on the same brief, even when the request names a single agent. Claude runs `high`, and GPT runs `xhigh`. The orchestrator synthesizes the result. The row keeps only a deliverable of ideas, options, hypotheses or a recommendation from discussion: reviewers who each review without seeing the others route by rules 3 and 4, and the work that follows a brainstorm, such as writing the tests, the doc or the code, routes by its own deliverable.

## Fallbacks and effort limits

**Fallbacks.** An unavailable source passes to the next source in its family's order (see **Subagent sources**). When the first-choice family has no available source, the row's Fallback family runs at its Fallback effort. When no source offers a model of either family, choose for each role the model and effort that best fit its task from what the available sources offer: the strongest model suited to the task type, with effort set by the task's type and complexity, taking the table's levels as the guide to how demanding each task type is. That choice keeps to the tier edges and sets every parameter explicitly. A both-run row then uses two different model families when the platform offers them, and otherwise one agent on one model.

**Effort limits.** The assigned level is the row's First choice effort, or its Fallback effort once the family has fallen back. Apply these cases:

- **Unavailable mechanism, source or runtime**: follow **Subagent sources** and **Fallbacks**, never the inherited-default case.
- **Missing parameter on the default tool**: set every parameter it exposes, such as model and agent type, and use a route in **Subagent sources** that carries the missing parameter per agent. For effort, use an in-product effort option, subject to the `Workflow` opt-in, or the CLI's effort setting.
- **Unsupported assigned level**: when the source carries effort, stay on that source at its highest supported level below the assignment. A level gap is not a fallback and never changes the source.
- **No available source in the family's order carries the parameter**: only then inherit the default for that parameter alone, or, on a mode-only route, set the mode, which decides every parameter the route cannot carry.
- **Concurrent agents forbidden on the same model and effort level**: keep the model. The first agent keeps its level; each later concurrent agent takes the highest level below the previous agent's that the platform allows, and an agent with no such level left waits until a running agent on that model finishes and then takes the level that agent freed, never changing the model or its source.

## Speed modes

**Speed modes.** Standard, Fast and Ultrafast are serving-speed tiers of the same model, in increasing order of speed and cost where the source offers them. Fast and Ultrafast can use a variant ID, a service tier or a settings switch. Availability depends on the model, source, host and account. These modes change serving speed only: they never change the required model, family, source, effort, review independence or evidence obligations. The `ultra` reasoning effort is separate from Ultrafast serving. **Speed modes are off by default** in `SKILL.md` decides whether the user enabled a mode at all; these rules apply once a mode is enabled.

- **Scope.** An enabling instruction names the mode and a scope: one model ("use Ultrafast for <model> for this task"), a set of models ("use Fast for all GPT models", or for one family or provider), or every model where a source offers it ("use Ultrafast for all models as long as it's available"). The same scope requirement applies to both modes. A request with no model scope, such as "use Ultrafast for this task", leaves the current speed instructions unchanged: ask the user once which scope they mean, giving those three forms as examples.
- **Persistence and precedence.** An enabled mode stays on for its scope across later tasks in the session until the user turns it off or changes it. A bound such as "for this task" ends with that bound. For overlapping scopes, the most recent applicable instruction still in force selects the mode, regardless of scope breadth. Turning a mode off selects Standard for that scope; it does not reactivate an older mode there. A later bounded instruction overrides earlier instructions only while its bound holds.
- **Matching and availability.** A model with no applicable speed instruction runs at Standard. Request exactly the selected mode where the chosen source supports it. If that mode is unavailable, request Standard and report the unavailable mode; use another accelerated mode only when the user explicitly authorizes that alternative for the same scope. Never automatically upgrade Fast to Ultrafast, infer a Fast fallback from Ultrafast, or switch model, family or source to obtain a speed tier.
- **Carrying it.** Choose a route on the selected source that carries each role's speed request, including Standard. Verify supported controls and effective inheritance; a catalog advertising a tier does not establish that a dispatch requested it. If no route can establish an authorized speed request, report the limitation instead of silently accepting an unauthorized inherited tier.

  On Claude Code, `Workflow` options, custom-subagent frontmatter and `--agents` JSON have no per-agent fast setting, and the documentation does not say whether `Agent` and `Workflow` children copy the session's fast flag, so assume they do and run fast when their model supports it. Use `claude -p` with Fast on for a role assigned Fast, whether or not `Workflow` opt-in holds, and, when the parent session is fast, with Fast forced off for a role assigned Standard. These Fast controls do not select Ultrafast; require a separately verified control before requesting it.

  On Codex, use native dispatch only when an explicit request setting, the host request contract or verified inheritance establishes the role's requested tier; set the exposed model and effort parameters and inspect fork restrictions. Verified inheritance that matches the assignment can carry the tier without a separate tier selector, but capability advertising alone is insufficient: a model list advertising Ultrafast and a launcher exposing only model and effort do not establish an Ultrafast request. Verify the current host rather than assuming root-tier inheritance or overwrite behavior. Otherwise use `codex exec` with the supported tier set explicitly. A role assigned Standard needs its own Standard request when native dispatch would select Fast or Ultrafast.

  On Cursor and Devin, explicitly select each role's verified speed variant, never Cursor's `inherit` or undocumented `model: fast` form, and never Devin's `subagent_general`, which inherits the parent model and does not independently establish the role's speed. Cursor documents `<model-id>[fast=false]` and `<model-id>[]` for standard subagent frontmatter, and a parent can name a model at launch; `<model-id>[fast=true]` follows the SDK's model parameters but is unconfirmed in subagent frontmatter. Inspect each role's task card, because a saved, default or parent-selected Fast variant can differ from the intended setting. Devin custom-subagent `model` takes the same UID as `--model`, and a skill that runs in a subagent can set `model:` in its frontmatter to override the profile's model. Give each role a custom definition naming its exact variant. Devin does not document a Fast form for custom-subagent `model`, so inspect run evidence to confirm the role ran its intended variant. Neither a Fast control nor an invented `-ultrafast` suffix establishes Ultrafast support. Read `cli-dispatch.md` for each source's CLI settings and checks.

## Reporting

**Reporting.** Use this one-line form as the whole announcement of a delegated agent and to name it in any report of it; what it returned is reported as **Communication** in `SKILL.md` directs. Describe only what the dispatch carried; `Fast` or `Ultrafast` records a request, not proof of the serving tier. Report observed serving differences separately when evidence establishes them:

```
<Role>: <model> <effort>[ Fast| Ultrafast][ via <route>][ (<tags>)]
```

- **Role**: a short label for what the agent does.
- **Model**: the model's name with its version, not its ID or an alias; when the dispatch carried a mode instead of a model, the product name and the mode, such as "Devin Normal", with no separate speed slot when the mode carried the speed request.
- **Effort**: the level the dispatch carried, including an explicit override, written Low, Medium, High, xHigh, Max or Ultra; left out when the dispatch carried none.
- **Fast or Ultrafast**: include only the one the dispatch requested for that agent; omit both for Standard or an unestablished request.
- **Route**: left out when the host's own in-product subagent mechanism launched the agent, whatever the host calls it; otherwise "<source> CLI" for a headless command line, or the product name plus the kind of interface for any other interface, never a command, flag or internal tool identifier.
- **Tags**: comma-separated, only those that apply. "fallback model": the row's Fallback family ran because a source for the first-choice family was present but could not run that family's required model; with no source for that family at all, the Fallback family is the normal case and takes no tag. "Fast unavailable" or "Ultrafast unavailable": the selected mode could not be requested for that agent on the source carrying it.
- **Both-run rows**: one line per agent that ran, or the lines joined with " + ".

For example: "Reviewer: <model> xHigh via <source> CLI", "Reviewer: <model> High (fallback model)", "Designer: <model> High", "Architect: <model> High + Architect: <model> xHigh via <source> CLI", "Researcher: Devin Normal via Devin child session".

## Dispatch check

**Dispatch check.** At the **Self-check** in `SKILL.md`, confirm for every dispatch of the task:

- [ ] Every delegated role ran the family and effort level **Task types** assigns it, and every advisor the model and effort **Advisor model** in `advisor.md` assigns it, or what those rules put in its place — a fallback, an effort-limit level or inherited default, the choice when no source offers either family, a mode chosen by those rules, or an explicit instruction — in the newest version in its source's own model list.
- [ ] Every delegated role and every advisor ran through the first available source in its family's order (for an advisor, the first that offers its model): through that source's in-product mechanism when you run in that source and the mechanism can carry the assignment, otherwise through that source's CLI, and through a mode-only route only when no route that carries the model was available.
- [ ] Every subagent call set every exposed parameter explicitly, the mode included on a mode-only route — no silent platform default, and no tier **Tiers.** forbids for that role unless instructed.
- [ ] Fast and Ultrafast requests followed explicit user opt-in, named scopes, persistence and precedence; unavailable modes used only authorized alternatives or Standard, and no unauthorized inherited tier was accepted (see **Speed modes**).
- [ ] Every announcement of a delegated agent, and its name in any report, was one line in the **Reporting** form, with no effort, Fast or Ultrafast the dispatch did not carry; observed serving differences were reported from evidence.
