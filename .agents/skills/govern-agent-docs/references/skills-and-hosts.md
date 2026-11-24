# Skills and hosts

Apply pass 1 of `SKILL.md` before choosing a format.

## Skill or plain document

A skill is a packaging and loading method: in the Agent Skills format, a `SKILL.md` entry with optional reference files and scripts, loaded progressively. Which skills a host lists and when it loads their bodies depends on the host.

- Keep a rulebook, reusable runbook or method as a plain document, or package it as a skill when it needs invocation by task intent or joint distribution with its supporting materials.
- When the task only requires running a script, you may link directly to the script or its runbook.

## Where a skill lives

| Location | What it holds | Rule |
| --- | --- | --- |
| Repository level | Runbooks, rulebooks or methods versioned with this repository | The project chooses the canonical path and writes it into the entry routes. |
| Shared collection | Rules, methods and procedures reused across repositories | Keep the canonical source in the collection; consumers reference a fixed version. |
| User level | Personal workflows and preferences | It carries no project rule. On each host in use, check whether a user-level skill of the same name shadows a repository skill. |

When two skills share a name but differ in content, rename one or reference it explicitly, and treat the readable canonical source as authoritative.

## Copies and adapters

- Keep one canonical source per skill. Add no adapter when a host already reads it.
- When a host needs an adapter, use a supported import, a relative symbolic link within the repository, or a traceable distributed copy. Use a cross-repository symbolic link that resolves only on one machine for personal environments only.
- Mark outside each distributed copy its source repository, path and revision.
- Generate the copy from the chosen canonical revision at first distribution, upgrade or drift repair. Never edit a copy independently.
- For example, when a host session really needs to import the repository entry file, a `CLAUDE.md` may import it with `@AGENTS.md`. Other hosts read the same canonical source in the way each supports.

## Host configuration

- Host configuration holds and excludes what its row in **What each type holds** in [type-tables.md](type-tables.md) lists.

## Skill descriptions

- In the Agent Skills format, `description` must contain 1–1,024 characters. Aim for fewer than 500 lines in the main file and fewer than 5,000 tokens in its body.
- For Claude Code, account for the configurable skill-listing cap on the combined `description` and `when_to_use` text. The default is 1,536 characters.
- Put task action words, domain nouns and key rules first.
- Cover every language the team writes tasks in, and state the domain-level cases the skill covers and excludes.
