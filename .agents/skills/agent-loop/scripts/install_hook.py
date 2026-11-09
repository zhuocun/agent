#!/usr/bin/env python3
"""Register or remove the agent-loop turn-end hook in a host's configuration.

Usage: install_hook.py --host HOST --scope user|project [--workspace DIR]
                       [--dry-run] [--uninstall]

HOST is codex, cursor, antigravity or devin. The hook command is
python3 <absolute path of the loop_hook.py beside this file> --host HOST.
Install replaces this hook's existing entries in place and keeps every other
key and entry; uninstall removes only this hook's entries and the containers
that removal leaves empty, and deletes a file that removal leaves an empty
object. A file that is not a JSON object is refused and left untouched.
Exit codes: 0 success, 1 refused configuration or filesystem-operation failure,
2 usage, invalid workspace or --host claude. Python 3.8 or later, standard
library only.
"""
import argparse
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile

HOSTS = ("codex", "cursor", "antigravity", "devin")
GROUP_NAME = "agent-loop"
TIMEOUT = 30
ACTIVATION = {
    "codex": "Approve the hook in Codex with /hooks (select it, press t); project hooks "
             "also need a trusted project.",
    "cursor": "Cursor runs stop hooks in its interactive CLI; print mode (agent -p) is not "
              "established to run them. The workspace must be trusted.",
    "antigravity": "If the CLI asks whether to trust the workspace, choose \"Yes, I trust this folder\".",
    "devin": "The workspace must be trusted; the SessionStart hook tells each new session "
             "its ID.",
}


class Refused(Exception):
    """The target file exists but cannot be merged safely."""


def parse_args(argv):
    """Parse the command line; argparse exits 2 on a usage error."""
    parser = argparse.ArgumentParser(
        prog="install_hook.py",
        description="Register or remove the agent-loop turn-end hook for a host.")
    parser.add_argument("--host", required=True, choices=("claude",) + HOSTS)
    parser.add_argument("--scope", required=True, choices=("user", "project"))
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    return parser.parse_args(argv)


def hook_command(host):
    """python3 plus the quoted resolved path of the loop_hook.py beside this file."""
    script = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "loop_hook.py"))
    return "python3 %s --host %s" % (shlex.quote(script), host)


def is_ours(entry, host):
    """A handler whose command names loop_hook.py and --host HOST."""
    command = entry.get("command") if isinstance(entry, dict) else None
    return (isinstance(command, str) and "loop_hook.py" in command
            and re.search(r"--host\s+%s(?:\s|$)" % re.escape(host), command) is not None)


def default_workspace():
    """The current directory's git top level, else the current directory."""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             universal_newlines=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return os.getcwd()
    path = top.stdout.strip()
    return path if top.returncode == 0 and path else os.getcwd()


def target_path(host, scope, workspace):
    """The absolute configuration file for the host and scope."""
    home = os.path.expanduser("~")
    if scope == "user":
        if host == "codex":
            base = os.environ.get("CODEX_HOME") or os.path.join(home, ".codex")
            path = os.path.join(base, "hooks.json")
        else:
            path = {
                "cursor": os.path.join(home, ".cursor", "hooks.json"),
                "antigravity": os.path.join(home, ".gemini", "config", "hooks.json"),
                "devin": os.path.join(home, ".config", "devin", "config.json"),
            }[host]
    else:
        path = os.path.join(workspace or default_workspace(), {
            "codex": os.path.join(".codex", "hooks.json"),
            "cursor": os.path.join(".cursor", "hooks.json"),
            "antigravity": os.path.join(".agents", "hooks.json"),
            "devin": os.path.join(".devin", "hooks.v1.json"),
        }[host])
    return os.path.abspath(path)


def load(path):
    """The file's JSON object, {} when missing; raise Refused for anything else."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise Refused("%s is not a plain JSON object (%s)" % (path, error))
    if not isinstance(data, dict):
        raise Refused("%s is not a JSON object" % path)
    return data


def child(parent, key, kind, create):
    """parent[key], created empty when absent and create is true, else None.

    Raise Refused when the value has the wrong JSON type.
    """
    if key not in parent:
        if not create:
            return None
        parent[key] = kind()
    value = parent[key]
    if not isinstance(value, kind):
        raise Refused("%r is not a JSON %s" % (key, "list" if kind is list else "object"))
    return value


def merge_handlers(handlers, host, entry):
    """Put entry where our first handler was and drop the rest of ours.

    entry None removes all of ours. Return whether any handler was ours.
    """
    positions = [index for index, item in enumerate(handlers) if is_ours(item, host)]
    for index in reversed(positions):
        del handlers[index]
    if positions and entry is not None:
        handlers.insert(positions[0], entry)
    return bool(positions)


def edit_flat(events, event, host, entry):
    """Cursor and Antigravity: an event holds a flat list of handlers.

    Return whether the list held one of ours.
    """
    handlers = child(events, event, list, entry is not None)
    if handlers is None:
        return False
    found = merge_handlers(handlers, host, entry)
    if entry is not None and not found:
        handlers.append(entry)
    if found and not handlers:
        del events[event]
    return found


def edit_grouped(events, event, host, entry, matcher):
    """Codex and Devin: an event holds matcher groups, each with a hooks list.

    Return whether a group held one of ours.
    """
    groups = child(events, event, list, entry is not None)
    if groups is None:
        return False
    kept, found = [], False
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            had = merge_handlers(group["hooks"], host, None if found else entry)
            found = found or had
            if had and not group["hooks"]:
                continue
        kept.append(group)
    if entry is not None and not found:
        group = {"matcher": ""} if matcher else {}
        group["hooks"] = [entry]
        kept.append(group)
    groups[:] = kept
    if found and not groups:
        del events[event]
    return found


def edit_antigravity(data, host, entry):
    """Named groups of event lists; a new entry goes into the agent-loop group.

    Return whether a group held one of ours.
    """
    found = False
    for name in list(data):
        group = data[name]
        if not isinstance(group, dict) or not isinstance(group.get("Stop"), list):
            continue
        had = merge_handlers(group["Stop"], host, None if found else entry)
        found = found or had
        if had and not group["Stop"]:
            del group["Stop"]
            if not group:
                del data[name]
    if entry is not None and not found:
        edit_flat(child(data, GROUP_NAME, dict, True), "Stop", host, entry)
    return found


def edit(data, host, scope, entry):
    """Apply the install (entry) or uninstall (entry None) to the loaded file.

    Return whether the file held one of our handlers.
    """
    create = entry is not None
    if host == "antigravity":
        return edit_antigravity(data, host, entry)
    if host == "cursor" and create:
        data.setdefault("version", 1)
    nested = not (host == "devin" and scope == "project")
    events = child(data, "hooks", dict, create) if nested else data
    if events is None:
        return False
    if host == "codex":
        found = edit_grouped(events, "Stop", host, entry, False)
    elif host == "cursor":
        found = edit_flat(events, "stop", host, entry)
    else:
        found = False
        for event in ("Stop", "SessionStart"):
            found = edit_grouped(events, event, host, entry, True) or found
    if found and not create and nested and not events:
        del data["hooks"]
    return found


def handler(host):
    """Our hook entry in the host's handler shape."""
    entry = {"type": "command", "command": hook_command(host), "timeout": TIMEOUT}
    if host == "cursor":
        entry["loop_limit"] = None
    return entry


def render(data):
    return json.dumps(data, indent=2) + "\n"


def write_atomic(path, content):
    """A temporary file in the same directory, then os.replace; keep the mode bits."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    if os.path.exists(path):
        mode = stat.S_IMODE(os.stat(path).st_mode)
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(prefix=".agent-loop.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def run(options):
    """Return the exit code for parsed options."""
    if options.host == "claude":
        sys.stderr.write("Claude Code registers the agent-loop hook from the skill's "
                         "frontmatter; there is nothing to install.\n")
        return 2
    if options.workspace is not None and not os.path.isdir(options.workspace):
        sys.stderr.write(
            "--workspace %s is not a directory. Expected an existing workspace "
            "directory; correct --workspace and retry with --dry-run.\n"
            % options.workspace
        )
        return 2
    path = target_path(options.host, options.scope, options.workspace)
    try:
        data = load(path)
        before = render(data)
        entry = None if options.uninstall else handler(options.host)
        found = edit(data, options.host, options.scope, entry)
        content = render(data)
    except Refused as error:
        sys.stderr.write(
            "Refused: %s; the file was left untouched. Expected readable plain "
            "JSON with the host's supported object and list containers. Check "
            "the selected path and permissions; back up and repair malformed "
            "configuration, then retry with --dry-run.\n" % error
        )
        return 1
    delete = options.uninstall and found and not data
    if options.dry_run:
        sys.stdout.write("path: %s\n%s" % (path, "delete\n" if delete else content))
        return 0
    if options.uninstall:
        if not found:
            sys.stdout.write("No agent-loop hook for %s found in %s; nothing changed.\n"
                             % (options.host, path))
        elif delete:
            os.unlink(path)
            sys.stdout.write("Removed the agent-loop hook from %s and deleted the file, "
                             "which held nothing else.\n" % path)
        else:
            write_atomic(path, content)
            sys.stdout.write("Removed the agent-loop hook from %s and wrote the file.\n" % path)
        return 0
    if not os.path.exists(path) or content != before:
        write_atomic(path, content)
    sys.stdout.write("Wrote %s\n%s\n" % (path, ACTIVATION[options.host]))
    return 0


def main():
    try:
        return run(parse_args(sys.argv[1:]))
    except OSError as error:
        sys.stderr.write(
            "Hook configuration operation failed: %s. Expected a readable "
            "configuration and writable target directory. Inspect the target "
            "before retrying; check scope, path and permissions, then use "
            "--dry-run before installing or uninstalling.\n" % error
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
