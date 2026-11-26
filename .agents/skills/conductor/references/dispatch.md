# Dispatch

Read this file in full before the first dispatch in a session and again after a compaction before the next dispatch. **Model selection** in `SKILL.md` says what each dispatch must carry. This file decides which source, route and workspace carry each dispatch, which model, effort and speed request it carries, and how to fill each slot of a role line (see **Role line** in `SKILL.md`).

- [Task types](#task-types)
- [Tiers and model IDs](#tiers-and-model-ids)
- [Fallbacks and effort limits](#fallbacks-and-effort-limits)
- [Speed modes](#speed-modes)
- [Subagent sources](#subagent-sources)
  - [Claude Code routes](#claude-code-routes)
  - [Codex routes](#codex-routes)
  - [Antigravity routes](#antigravity-routes)
- [Mapping to dispatch fields](#mapping-to-dispatch-fields)
- [Workspaces for concurrent writers](#workspaces-for-concurrent-writers)
- [Reporting](#reporting)
- [Dispatch check](#dispatch-check)

## Task types

Each delegated role runs the family and effort level of its row, neither lower nor higher, unless **Fallbacks** or **Effort limits** direct otherwise.

- The choice columns rank the row's families in priority order, each with its effort; **Fallbacks** decides which run. Includes lists what routes to the row.
- "Claude", "GPT" and "Gemini" mean each provider's top-tier line (see **Tiers.**).
- Backend architecture design and Brainstorming and discussion are two-family rows (rules 6 and 7); the other rows are single-family.

| Task type | First choice | Second choice | Third choice | Includes |
|---|---|---|---|---|
| Coding | Gemini `high` | Claude `high` | GPT `xhigh` | code of any size except new-UI frontend code: backend code; frontend code with no new UI, such as business logic, state management, API clients, data-fetching hooks, validation, routing, build and lint configuration, tests and non-visual bug fixes; CI, infrastructure and other repository config; comments and docstrings in source; a script delivered to the repo (rules 1 and 5) |
| Coding documentation | Claude `high` | Gemini `high` | GPT `xhigh` | authoring or revising coding-related specifications, implementation plans, proposals and briefs, and developer-facing technical documentation (such as setup, API usage, testing and maintenance guides) (rule 1); and the reviews, verifications and audits that rule 4 assigns to this row (rules 4 and 8) |
| Review | GPT `xhigh` | Gemini `high` | Claude `high` | reviewers, verifiers, and reviews or audits of existing work, security review included, and the correctness dimension of a two-dimension review (rules 3 and 4) |
| Backend architecture design | Gemini `high` | Claude `high` | GPT `xhigh` | server-side and full-stack system design: service boundaries, data models and schemas, API contracts, storage and integration choices, and the review, verification or audit of that work (rules 4, 6 and 8) |
| Visual design | Claude `high` | Gemini `high` | GPT `xhigh` | visual and interaction design of a product UI; new-UI frontend code (rule 1); visualizations that present information (diagrams, charts, HTML pages, slide decks) with the markup that draws them; design prototypes not meant to ship; and the review, verification or audit of that work (for new-UI frontend code, its visual and interaction dimension) (rule 4) |
| Documentation | Claude `high` | Gemini `high` | GPT `xhigh` | other prose documents, general agent operating instructions, UI strings and translations, in any language (rule 1); and the reviews, verifications and audits that rule 4 assigns to this row (rules 4 and 8) |
| Research | Gemini `high` | GPT `xhigh` | Claude `high` | sidecar explorers, exploration, data analysis, debugging or root-causing that reports a cause, reproducing a user-reported problem before any work exists |
| Brainstorming and discussion | Claude `high` | Gemini `high` | GPT `xhigh` | brainstorming (generating ideas, options, names, hypotheses, test-case ideas) and multi-agent discussion, where agents read and respond to each other (debate, critique panel, deliberation) (rule 7) |
| Other simple work | GPT `high` | Gemini `medium` | Claude `medium` | a single-step fact lookup, or any other task that is single-step, mechanical and verifiable in seconds (rule 2) |
| Other complex work | Gemini `high` | GPT `xhigh` | Claude `high` | client-only architecture decisions (frontend state, data fetching, a CLI's module structure), a small task that turns on judgment, anything no other row covers (rule 2) |

1. Classify each delegated role by the substance of its deliverable, independent of its recipient, filename, tools or intermediate steps.
   - **New-UI frontend code** is frontend implementation meant to ship, in a product or a shared UI package, that involves new UI: a new page, view, dialog, panel, component or layout, a visual redesign, a new visible section or control, or a new chart or other visualization component. It is Visual design, together with the logic, state, store, API client and wiring changes that the new UI requires.
   - Every other code deliverable is Coding (apart from findings-only scripts in Research), including a fix that follows the worker's own investigation and a copy, attribute or typo fix on existing UI.
   - A standalone visualization made to present information (such as a diagram, chart, HTML page or slide deck, including one embedded in a document) is Visual design, its markup included, and so is a design prototype not meant to ship; neither is new-UI frontend code. A script or chart made only to get findings is Research.
   - Authoring or revising prose that specifies or records code implementation or serves as developer-facing technical documentation is Coding documentation. Embedded code samples follow the prose's row.
   - Architecture and design decisions use their own rows, regardless of document title or format. A standalone client-only architecture decision is Other complex work.
2. Use Other simple work or Other complex work only when no other row matches. Other simple work needs all three of single-step, mechanical and verifiable in seconds; a single-step fact lookup is Other simple work, not Research; a sidecar explorer is Research whatever it looks up. Any other work that no other row matches is Other complex work.
3. Reviewers and verifiers (see **Reviewer** in `SKILL.md`) go to Review, and so does any subtask whose deliverable is a review or audit of existing work, security review included, except where rule 4 routes them differently.
4. Route each reviewer, verifier, review or audit of Visual design, Backend architecture design, Coding documentation or Documentation work, new-UI frontend code included, under **One-row review**, **Agent-read documents** or **Two-dimension review**. The reviewed work's row is the row the work was routed to or, for existing work, the row it would route to.
   - **One-row review.** A review, verification or audit of Backend architecture design (rule 6), or of Visual design work other than new-UI frontend code, runs wholly on the reviewed work's row. This includes a visualization in a document (rule 5).
   - **Agent-read documents.** Work on the Coding documentation or Documentation row is agent-read when its text, the request or its configured use shows that it was written to direct an agent's actions, such as a skill, a prompt, an agent definition, agent operating instructions, or a brief for an agent; it stays agent-read when it was written to direct both people and agents. All other work on those rows is written for human readers, including a specification or implementation plan written for maintainers that an agent later uses as a source of requirements. Each review, verification or audit of an agent-read document is one agent on Review, scoped to the document correctness that the table under **Two-dimension review** defines: a verifier for a separately scoped verification (see **Verifiers** in `review-and-evidence.md`), otherwise a reviewer.
   - **Two-dimension review.** The work this table lists is judged in two dimensions:

     | Reviewed work | Dimension on the reviewed work's row | Correctness dimension on Review |
     |---|---|---|
     | Work written for human readers on the Coding documentation or Documentation row | structure and wording: organization, reader flow, clarity, phrasing, style, register and tone | correctness: factual accuracy, source grounding, the accuracy of technical, code, contract and constraint content, completeness, internal consistency, and whether the document's claims and steps hold |
     | New-UI frontend code | visual and interaction quality: layout, visual hierarchy, styling, responsiveness, interaction states and usability | code correctness: runtime safety, state and hook behavior, data handling, security, and the soundness of accessibility, contracts and tests |

   - **Dimension scope.** These rules apply to the work **Two-dimension review** lists.
     - Unless an explicit applicable instruction narrows the gate, the required review of a worker's two-dimension deliverable is two independent reviewers on the same artifact, one per dimension; a one-dimension reviewer or verifier never satisfies this gate without such an instruction, and when such an instruction narrows it, a fresh reviewer still runs on the remaining dimension's row.
     - A separately scoped reviewer, verifier, review or audit of one dimension, such as a verifier of a document's factual, technical or code claims, runs only on that dimension's row.
     - Any other review, verification or audit of two-dimension work that names both dimensions or names neither runs as the same pair, regardless of whether the work is existing or a current worker's output.
     - Run each pair as **Fallbacks** runs a two-family pair, and combine its verdicts under rule 8.
5. Split a subtask that spans rows by deliverable.
   - A design runs on the row rule 1 gives it. Its implementation then runs against the accepted design, on the row rule 1 gives that code.
   - Split off from new-UI frontend code only independently deliverable work, such as backend code or separate non-UI engineering work, and route it by its own deliverable.
   - A document's prose runs on the row its substance calls for under rule 1: Coding documentation, Documentation, or the row for its architecture or design work. Each visualization in it runs as Visual design, drawing what the prose sets out. A slide deck is one visualization.
6. Backend architecture design runs, for design and review alike, the families **Fallbacks** selects for a two-family row. A design is one worker per selected family on the same brief. A review, verification or audit is one agent per selected family, each judging the same artifact independently (rule 8). Each design passes its own review; with two designs, the orchestrator then compares and synthesizes them. A backend or full-stack design stays on this row when agents discuss it.
7. Brainstorming and discussion runs the families **Fallbacks** selects for a two-family row, with at least one agent per selected family on the same brief, even when the request names a single agent. The orchestrator synthesizes the result. The row keeps only a deliverable of ideas, options, hypotheses or a recommendation from discussion: reviewers who each review without seeing the others route by rules 3 and 4, and the work that follows a brainstorm, such as writing the tests, the doc or the code, routes by its own deliverable.
8. When two reviewers judge one artifact, one per dimension (rule 4) or one per family on Backend architecture design (rule 6), wait for both verdicts and reconcile each (see **Orchestrator final gate** in `SKILL.md`) before acting on either.
   - The pair passes only when each verdict is a `pass` you accept or a `revise`/`redo` you reject.
   - For a review, verification or audit of existing work with no worker to send back, return the combined verdict and both reviewers' issues.
   - Otherwise, an accepted `revise` or `redo` from either reviewer makes the pair one failed review. If it is the subtask's second failed review, apply the two-failed-review stop before any further dispatch. If not, handle the strongest accepted verdict, `redo` over `revise`, once as **Reviewer** in `SKILL.md` directs, passing both reviewers' issues verbatim.

## Tiers and model IDs

**Tiers.** Delegated work runs on the top tier: each provider's standard full-capability line, including its newer versions and any successor the provider presents as replacing it at the same place in its lineup. Today that line is Opus on Anthropic, Sol on OpenAI and Gemini 4 Neon on Google. The rule covers sidecar explorers too: read-only scouts probing in parallel, off the integration path. Place every model a provider offers, whatever its brand, against that line by the provider's own model list and description. Delegated work may not use:

- **Too-cheap edge**: every model below the line, such as `*-mini`, `*-haiku`-class, Sonnet-class, GPT Luna, Gemini 4 Hydrogen and Gemini 3.8 Flash today.
- **Too-expensive edge**: every tier above the line, whose cost outruns its marginal value for delegated work, such as Fable and Mythos on Anthropic, Astra on OpenAI and Gemini 4 Carbon on Google today. A delegated role may be as strong as the orchestrator but is capped at the top tier, so this edge stays forbidden even when the orchestrator runs on it.
- **Unclear or superseded**: any model whose place stays unclear, or that the provider presents as superseded.
- **Gemini 4 Argon**: Google's efficient Gemini 4 frontier model beside Gemini 4 Neon, outside the Gemini line selected for delegated work.

An advisor is the exception: **Advisor model** in `advisor.md` sets its model, and the top-tier cap does not apply.

**Model ID.** Use the newest eligible version of the selected model line, read from the chosen source's own model list, never an ID remembered from earlier work or training. Use an alias that resolves to the latest version only when it cannot land on a forbidden tier; otherwise pin the full ID from the list. Never use a bare family alias such as `gpt`: it does not guarantee the required tier, effort or speed.

## Fallbacks and effort limits

**Fallbacks.** Choose the families that run a row as follows:

- A family qualifies when an available source in its order (see **Subagent sources**) can run its required top-tier model with its effective credentials. When a family does not qualify, skip to the next priority on the row, which runs at its own effort. Rank qualifying families in table order.
- When no available source can run the required top-tier model for any family on the row, rank distinct available model families by the strongest eligible model suited to the task type. Set effort by the task's type and complexity, taking the table's levels as the guide to how demanding each task type is. Keep to the tier edges and set every parameter explicitly.
- In either case, a single-family row runs the first qualifying family. A two-family row runs the first two qualifying distinct families (never three), or the sole qualifying family alone when only one qualifies. Run a two-family pair concurrently, or one after the other when a concurrency limit allows only one.

**Effort limits.** The assigned level is the effort of the selected priority on the row. Apply these cases:

- **Unavailable mechanism, source or runtime**: follow **Subagent sources** and **Fallbacks**, never the inherited-default case.
- **Missing parameter on the default tool**: set every parameter it exposes, such as model and agent type, and use a route in **Subagent sources** that carries the missing parameter per agent. For effort, use an in-product effort option, subject to `Workflow` opt-in, or the CLI's effort setting.
- **Unsupported assigned level**: when the source carries effort, stay on that source at its highest supported level below the assignment. A level gap is not a fallback and never changes the source.
- **No available source in the family's order carries the parameter**: only then inherit the default for that parameter alone, or, on a mode-only route, set the mode, which decides every parameter the route cannot carry.
- **Concurrent agents forbidden on the same model and effort level**: never change the model or its source. The first agent keeps its level; each later concurrent agent takes the highest level the platform allows below the previous agent's. An agent with no such level left waits until a running agent on that model finishes, then takes the level that agent freed.

## Speed modes

Standard, Fast and Ultrafast are serving-speed tiers of the same model, in increasing order of speed and cost where the source offers them. Fast and Ultrafast use a variant ID, a service tier or a settings switch, and depend on the model, source, host and account for availability. These modes change serving speed only, never the required model, family, source, effort, review independence or evidence obligations. The `ultra` reasoning effort is separate from Ultrafast serving. Fast and Ultrafast require explicit user opt-in as **Speed modes are off by default** in `SKILL.md` directs; once any speed instruction is active, or where a host might inherit an accelerated tier, these rules govern every role, including roles assigned Standard.

- **Scope.** An instruction enabling either mode names the mode and a scope: one model ("use Ultrafast for <model> for this task"), a set of models ("use Fast for all GPT models", or for one family or provider), or every model where a source offers it ("use Ultrafast for all models as long as it's available"). A request with no model scope, such as "use Ultrafast for this task", changes no speed instruction: ask the user once which scope they mean, giving those three forms as examples.
- **Persistence and precedence.** An enabled mode stays on for its scope across later tasks in the session until the user turns it off or changes it. A bound such as "for this task" ends with that bound. For overlapping scopes, the most recent applicable instruction still in force selects the mode, whatever its scope's breadth. Turning a mode off selects Standard for that scope and does not reactivate an older mode there. A later bounded instruction overrides earlier instructions only while its bound holds.
- **Matching and availability.** A model with no applicable speed instruction runs at Standard. Request exactly the selected mode where the chosen source supports it. If that mode is unavailable, request Standard and report the unavailable mode; use another accelerated mode only when the user explicitly authorizes that alternative for the same scope. Never automatically upgrade Fast to Ultrafast, infer a Fast fallback from Ultrafast, or switch model, family or source to obtain a speed tier.
- **Carrying the request.** Choose a route on the selected source that carries each role's speed request, Standard included. Verify supported controls and effective inheritance; a catalog advertising a tier does not establish that a dispatch requested it. If no route can establish an authorized speed request, report the limitation instead of silently accepting an unauthorized inherited tier. Each source carries the request as follows:
  - **Claude Code**: `Workflow` options, custom-subagent frontmatter and `--agents` JSON have no per-agent fast setting. The documentation does not say whether `Agent` and `Workflow` children copy the session's fast flag, so assume they do and run fast when their model supports it. Use `claude -p` with Fast on for a role assigned Fast, whether or not `Workflow` opt-in holds, and, when the parent session is fast, with Fast forced off for a role assigned Standard. These Fast controls do not select Ultrafast; request Ultrafast only through a separately verified control.
  - **Codex**: use native dispatch only when an explicit request setting, the host's request contract or verified inheritance that matches the assignment establishes the role's tier; otherwise use `codex exec` with the supported tier set explicitly. A launcher that exposes only model and effort does not establish the tier. Set the exposed model and effort parameters, inspect fork restrictions, and verify how the current host inherits or overrides the tier instead of assuming it. Give a role assigned Standard its own Standard request when native dispatch would select Fast or Ultrafast.
  - **Cursor and Devin**: select each role's verified speed variant explicitly. A Fast control or an invented `-ultrafast` suffix does not establish Ultrafast support.
    - **Cursor**: never use `inherit` or the undocumented `model: fast` form. Cursor documents `<model-id>[fast=false]` and `<model-id>[]` for standard subagent frontmatter, and a parent can name a model at launch; `<model-id>[fast=true]` follows the SDK's model parameters but is unconfirmed in subagent frontmatter. Inspect each role's task card, because a saved, default or parent-selected Fast variant can differ from the intended setting.
    - **Devin**: never use `subagent_general`, which inherits the parent model and does not independently establish the role's speed. Give each role a custom definition naming its exact variant: custom-subagent `model` takes the same UID as `--model`, and a skill that runs in a subagent can set `model:` in its frontmatter to override the profile's model. Devin documents no Fast form for custom-subagent `model`, so inspect run evidence to confirm the role ran its intended variant.
  - **Antigravity**: neither the in-product mechanisms nor `agy -p` exposes a Fast or Ultrafast serving control. Treat both as unavailable there and run Standard per **Matching and availability**.

## Subagent sources

Five sources can run a subagent when the host provides a supported in-product mechanism or headless CLI.

| Source | In-product mechanism | Headless CLI |
|---|---|---|
| Claude Code | the `Workflow` tool (`agent(prompt, {model, effort})` where the installed workflow API exposes those options), or a custom subagent whose frontmatter sets `model` and `effort`, dispatched through the `Agent` tool's `subagent_type`; a bare `Agent` call sets `model`, and `effort` only on builds that expose it | `claude -p` |
| Codex | native subagents with exposed `model` and `reasoning_effort`, or TOML custom agents with `model` and `model_reasoning_effort` | `codex exec` |
| Cursor | Cursor's Task-tool subagents (frontmatter `model`; effort and speed as bracket parameters, such as `<model-id>[effort=high,fast=false]`) | `agent -p` (legacy binary name `cursor-agent`) |
| Devin | Devin's subagents (custom-subagent frontmatter `model`; effort is encoded in the model ID) | `devin -p` |
| Antigravity | `swarm` (`add` with a `model` from `models`, where the model entry encodes effort), or `invoke_subagent` / `run_workflow` (`agent()`) under the `inherit` rule in **Antigravity routes** | `agy -p` |

**Source order.** Take the first available source in the family's order:

- **Claude-family models**: Claude Code → Cursor → Devin → Antigravity.
- **GPT-family models**: Codex → Devin.
- **Gemini-family models**: Antigravity → Cursor → Devin.

When the selected source is the one you are running in, prefer its available in-product mechanism. Use its CLI only when the native route is unavailable or cannot carry the assigned model, effort and speed setting. Reach other sources through available CLIs.

**Mode-only routes.** A mode-only route lets the caller pick a product mode that bundles model, effort and speed, but not a model or an effort; Devin child sessions are one. It is never a source's in-product mechanism. Use it only as the last resort: after applying **Fallbacks**, when no eligible route can select a model per agent. **Fallbacks** treats it as a source that cannot run any family's required top-tier model.

**Availability.** Apply these rules to every source and route:

- Resolve routes from the current host's exposed tools, permissions and installed CLI help. Tool names, arguments and commands in this skill describe supported routes, not capabilities every host provides. Check that the host exposes a selected tool and its fields before using them.
- Honor concurrency and fork limits. A host without shell execution cannot use a CLI route; one without writable configuration cannot create file-based custom definitions.
- Carry the brief and required files through the chosen route, and verify the child can access them instead of assuming a shared filesystem or inherited tools, credentials and network.
- Resolve the executable in the invocation's actual environment, including any configured wrapper, and verify its supported syntax.
- Check a supported credential route with that invocation's provider, configuration and transport. Saved-login status alone does not establish availability. Do not assume installed CLIs, credentials, internet access or a proxy from another machine.
- Use only already authorized setup and network routes: availability checks do not authorize installation, login or changes to provider, permission or proxy configuration. Diagnose credential and transport failures separately, and retry a failed catalog request through an already authorized network or proxy route where available.
- Check sources in family order until one can run the selected model with its effective credentials, and skip unavailable or unverified sources for that dispatch. A successfully retrieved, applicable catalog that lacks the required top-tier model (see **Tiers.**) rules out only its own source. Never substitute a forbidden tier.

**Custom definitions.** On Claude Code, Codex and Antigravity, create or alter a project definition only when that repository change is already authorized; otherwise use another available route. Each source's routes name its user scope for generated definitions.

**Leaf delegates.** In a leaf's brief, prohibit every delegation route, including native subagent and workflow tools, `swarm` and CLIs. On Claude Code and Antigravity, also disable the native delegation tools as their routes describe.

### Claude Code routes

- When a bare `Agent` call exposes model but no effort parameter, use an available `Workflow` tool whose installed `agent()` options carry effort, or an effort-setting custom subagent dispatched through `Agent`'s `subagent_type`. Check that `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, and any workflow-specific model override that the installed build documents, does not make the selected tool ignore the per-agent model.
- **`Workflow` opt-in. This skill requires explicit opt-in for `Workflow`, separately from the host's availability and permission checks.** Opt-in starts when the user invokes or names this skill (for example `/conductor`), asks for subagents or a workflow, or enables Claude Code's ultracode mode. It stays in force for later tasks in the session and covers a workflow of any size, a single agent included. Loading this skill yourself does not establish opt-in. Without opt-in, use a custom subagent, or `claude -p` when a custom subagent is unavailable or cannot carry the assignment.
- Write each generated definition to `agents/<name>.md` under the active user configuration directory, one file per model and effort pair. `CLAUDE_CONFIG_DIR` can relocate that directory; `~/.claude/agents/<name>.md` is the conventional default, not a fixed destination. Verify that the directory is writable and loaded by the session. You may select an existing project `.claude/agents/` definition. Verify scope and name precedence so the intended definition wins.
- Put the required `name` and `description`, plus `model` and `effort`, in the frontmatter, and pass the brief as the `Agent` prompt. For a leaf, deny the available native delegation tools through the supported tool restrictions (`disallowedTools: Agent, Workflow` on hosts with those tools).
- Before dispatch, check that the updated definition is discoverable. Claude Code watches existing user-scope and project agent directories and uses edits on the next delegation; restart when the directory did not exist at session start. Directories added by `--add-dir` or `/add-dir` are not watched, and `--disable-slash-commands` disables these watchers. Verify reload support for the running version; if a restart is unavailable, use another available route.

### Codex routes

- Inspect the current host's launcher schema and configuration format. Use exposed model and effort parameters (for example `model` and `reasoning_effort`), or supported TOML custom agents with `model` and `model_reasoning_effort`.
- Resolve custom-agent discovery against the active user configuration root and project scope, and include that version's required fields. Keep generated definitions in a writable user scope that the session loads. Hosts supporting the current standalone custom-agent discovery format require `name`, `description` and `developer_instructions` in each file; do not impose that manifest on a host using a different TOML role-config format.
- Fork controls vary by host. Use `fork_turns: "none"` or a positive history count only when the schema exposes those forms and requires them for overrides. A host requires them only where it specifies that full-history forks inherit the parent's settings and reject overrides. Do not translate them into an unsupported argument on another host.

### Antigravity routes

- When `swarm` is exposed and authorized, call it with `action: "models"` to inspect the available picker models and `action: "add"` with an explicit `model` entry, which encodes the model's effort level.
- `invoke_subagent` (`Model`), custom-agent files (`model`) and `run_workflow` (`agent(..., model=...)`) accept only coarse tier strings (such as `inherit`, `flash_lite`, `flash`, `pro`), not concrete model IDs or effort tokens; `define_subagent` exposes no model parameter. Use `inherit` only when the parent session already runs the role's exact assigned model, effort and speed, and never use a coarse tier token to approximate an assigned model.
- When no in-product route can carry the assignment, use `agy -p`.
- For a leaf, disable delegation tools where supported: `EnableSubagentTools: false` on `define_subagent`, or an explicit verified `tools` allowlist omitting delegation tools on custom agents.
- Keep generated custom-agent definitions in the writable user scope `~/.gemini/config/agents/`. Project definitions live in `.agents/agents/`.

## Mapping to dispatch fields

- Map each assignment to the platform's fields: `model`, `subagent_type`, `effort`, `reasoning_effort`, or an effort level encoded in the model ID.
- On a mode-only route (see **Subagent sources**), map a delegated role to the product mode by applying the tier edges to the product's own description of its modes: use the standard full-capability mode, never a light or cheap mode (too-cheap edge), a premium mode above it (too-expensive edge) or a mode whose place stays unclear. **Advisor model** in `advisor.md` sets an advisor's mode.
- Never use a mode that exists mainly for speed unless the user's explicit speed instruction authorizes its serving tier, with a scope covering every model or naming that mode (see **Speed modes**).

## Workspaces for concurrent writers

When concurrent writers would conflict in the shared tree or a shared build or environment lock limits parallel work, and a worktree costs less to set up than the parallelism it buys, give each writing strand its own `git worktree` and record where each one is. A worktree holds tracked content only, so dependencies and other ignored files do not come across. Otherwise, and for every strand that only reads, work in the shared tree, and run writers concurrently when their files do not overlap.

## Reporting

Fill each slot of the role line (see **Role line** in `SKILL.md`) with what the dispatch carried, or, in a role line written before the call, with what the prepared call carries. `Fast` or `Ultrafast` records a request, not proof of the serving tier. Report a difference between the serving and the request separately from the role line, and only when evidence establishes it.

- **Role**: a short label for what the subagent does, `Advisor` for an advisor.
- **Model**: the model's name with its version, not its ID or an alias. For a dispatch that carried a mode instead of a model, the product name and the mode, such as "Devin Normal", with no separate speed slot when the mode carried the speed request.
- **Effort**: the level the dispatch carried, an explicit override included, written Low, Medium, High, xHigh, Max or Ultra; left out when the dispatch carried none.
- **Fast or Ultrafast**: the mode the dispatch requested for that subagent; left out for Standard or an unestablished request.
- **Route**: left out when the call goes through the host's own in-product subagent mechanism, whatever the host calls it; otherwise "<source> CLI" for a headless command line, or the product name plus the kind of interface for any other interface, never a command, flag or internal tool identifier.
- **Tags**: comma-separated, only those that apply:
  - "fallback model": a skipped higher-priority family on the row would have taken this subagent's slot, and that family had at least one source present but no source able to run its required model.
  - "Fast unavailable" or "Ultrafast unavailable": the selected mode could not be requested for that subagent on the source carrying it.

For example: "Reviewer: <model> xHigh via <source> CLI", "Reviewer: <model> High (fallback model)", "Designer: <model> High", "Researcher: Devin Normal via Devin child session".

## Dispatch check

At the **Self-check** in `SKILL.md`, confirm for every dispatch of the task:

- [ ] Every delegated role ran the family and effort level **Task types** assigns it, and every advisor the model and effort **Advisor model** in `advisor.md` assigns it — or an authorized replacement (a fallback, an effort-limit level or inherited default, the choice when no available source can run the required top-tier model for any family on the row, a mode chosen by those rules, or an explicit instruction) — and every model-based assignment ran in the newest eligible version in its source's own model list.
- [ ] Every two-family row ran the families **Fallbacks** selects, with the concurrency **Fallbacks** sets.
- [ ] Every review, verification or audit that **Agent-read documents** in rule 4 covers followed that rule, unless an override in **Model selection** in `SKILL.md` applied.
- [ ] Every review, verification or audit that rule 4 requires to cover both dimensions ran as two independent reviewers judging the same artifact, one per dimension on that dimension's row, with the concurrency rule 4 sets, and their verdicts were combined under rule 8.
- [ ] Every delegated role and every advisor ran through the first available source in its family's order that can run the selected model (see **Subagent sources** and **Advisor model** in `advisor.md`): through that source's in-product mechanism when you run in that source and the mechanism can carry the assignment, otherwise through that source's CLI, and through a mode-only route only when no eligible model-carrying route was available.
- [ ] Every subagent call set every exposed parameter explicitly, the mode included on a mode-only route — no silent platform default, and no tier **Tiers.** forbids for that role unless instructed.
- [ ] Fast and Ultrafast requests followed explicit user opt-in, named scopes, persistence and precedence; unavailable modes used only authorized alternatives or Standard, and no unauthorized inherited tier was accepted (see **Speed modes**).
- [ ] Every role line filled its slots as **Reporting** directs; each serving difference that evidence established was reported separately from the role line, and no difference was reported without such evidence.
