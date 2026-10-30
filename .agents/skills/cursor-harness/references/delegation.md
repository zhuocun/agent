# Delegation

Use this reference to dispatch subagents and external agent CLIs inside Cursor and verify their results. Run each delegate on a top-tier model suited to its role: never a mini or distilled variant, and never an oversized premium tier whose cost outruns its value for delegated work. Set effort and every other exposed parameter explicitly. Before launching an external CLI, confirm it is installed and authorized, read its `--help` for the non-interactive mode, and pick the model from its current model list.

## Task-tool subagents (documented)

- **Write a self-contained prompt.** A subagent sees neither the user's messages nor your earlier steps. Give it the goal, files and paths, constraints, what not to touch, exact deliverable, and final-message format. Put long or reusable briefs in a file and point the subagent to it.
- **Background Task:** use `run_in_background: true` for the background vehicle in [background-work.md](background-work.md#choosing-the-vehicle). You cannot poll or await a background subagent. Its result arrives after your turn ends. Keep working or end the turn.
- **Parallel launch:** put independent Task calls in one message.
- **Resume:** use a finished subagent's agent id for a follow-up, such as sending reviewer issues to the worker verbatim. Resuming a running subagent fails. Wait for its result first.
- **Model:** pass a slug from the available model list that meets the rule above. An invalid slug fails the call. Use `inherit` only when the user asks for it.
- **Cloud subagents:** `environment: cloud` gives each subagent its own VM and branch. Use cloud only when the user asks for it. Follow the user's instruction on whether to merge, check out, or ignore that branch.
- **Descriptions:** give each subagent a concrete, distinct visible name, such as "Review T3 patch r2". Reuse the name in the ledger.

## External agent CLIs (Codex, Devin, Cursor CLI, Claude Code)

External agent CLIs can run for many minutes and outlast your turn.

- Follow [tmux launch, environment, waiter, and artifact checks](background-work.md#tmux-run-plus-waiter-verified-2026-10-12).
- A non-empty "last message" file proves output. Completion requires an end marker or another exit signal.

## Verifying delegated results

- Treat a subagent or CLI report as a claim. Check the diff, run the test, or open the artifact before marking the ledger entry done.
- When a reviewer subagent checks a worker's result, pass its issues to the worker verbatim and record the round in the ledger; do not silently fix issues and claim the worker's result.
- Record each delegate's kind, name, model, effort, any other parameter you set, and brief path in its ledger entry's owner and evidence cells so a later turn can resume or audit it.

## Keeping the overview

- Keep the ledger and acceptance records yourself even when delegates do the work.
- Register the whole wave using [ledger registration](task-ledger.md#registration) before the first launch, then confirm each delegate started.
- Process results as they arrive, even out of order. Wait for the whole wave only when the next step needs all results.
