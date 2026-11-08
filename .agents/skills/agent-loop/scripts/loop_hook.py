#!/usr/bin/env python3
"""Turn-end hook for the agent loop.

Usage: loop_hook.py [--host HOST] [--state PATH]

HOST is claude (the default), codex, cursor, antigravity or devin. Reads one
turn-end event as JSON on stdin and prints one JSON object on stdout. It
always exits 0. It asks the host to continue only when the event comes from
the main session that owns the state file, the loop has no stop reason, an
item is actionable (or a waiting item has no waiter running), and the budget
and progress guards pass. With --host devin, a SessionStart event tells the
session its ID instead. Any error or unexpected input prints {} so the turn
may end. Python 3.8 or later, standard library only.
"""
import hashlib
import json
import os
import re
import sys
import tempfile

STATE_NAME = ".agent-loop.md"
SIDECAR_NAME = ".agent-loop.hook.json"
TAG = "[agent-loop]"
DEFAULT_BUDGET = 50
NO_PROGRESS_LIMIT = 2
STATUSES = ("ready", "doing", "waiting", "user")
ITEM = re.compile(r"^[-*]\s+\[([^\]]*)\]\s+(\S+)(.*)$")
LOG_LINE = re.compile(r"^[-*]\s+\S")
NEXT = re.compile(r"(?:^|[\s;])next:\s*([^;]*)")
AFTER = re.compile(r"(?:^|[\s;])after:\s*([^\s;,]+)")
BUDGET = re.compile(r"^\d+$")


def parse_args(argv):
    """Return (host, --state path or None); raise on any other or repeated argument."""
    options = {}
    args = iter(argv)
    for arg in args:
        if arg not in ("--host", "--state") or arg in options:
            raise ValueError("unknown or repeated argument")
        options[arg] = next(args)
    host = options.get("--host", "claude")
    if host not in ADAPTERS:
        raise ValueError("unknown host")
    return host, options.get("--state")


def nonempty(value):
    """True for a non-empty string."""
    return isinstance(value, str) and bool(value)


def env_roots(*names):
    """The non-empty values of the named environment variables, in order."""
    return [os.environ[name] for name in names if os.environ.get(name)]


def string_list(value):
    """The non-empty strings of a list; [] for anything that is not a list."""
    return [item for item in value if nonempty(item)] if isinstance(value, list) else []


def turn_end(session, hook_turn, roots, waiters, failed=False):
    """Step 1 result: owner key, automatic-turn flag, search roots and waiter signal.

    hook_turn None means the sidecar's pending key decides it; waiters None
    means the host gives no signal about running background work. failed
    means the turn ended in an error: it never continues, but an owned stop
    still clears a matching pending.
    """
    return {"session": session, "hook_turn": hook_turn, "roots": roots,
            "waiters": waiters, "failed": failed}


def stop_hook_event(event, agent_key_rejects):
    """A main-session Stop event with a typed stop_hook_active (Claude Code format)."""
    if event.get("hook_event_name") != "Stop":
        return False
    if agent_key_rejects("agent_id"):
        return False
    return nonempty(event.get("session_id")) and isinstance(event.get("stop_hook_active"), bool)


def claude_event(event):
    """Claude Code: cwd, then CLAUDE_PROJECT_DIR; waiters from background_tasks."""
    if not stop_hook_event(event, lambda key: event.get(key) is not None):
        return None
    roots = [event["cwd"]] if nonempty(event.get("cwd")) else []
    tasks = event.get("background_tasks")
    waiters = bool(tasks) if isinstance(tasks, list) else None
    return turn_end(event["session_id"], event["stop_hook_active"],
                    roots + env_roots("CLAUDE_PROJECT_DIR"), waiters)


def codex_event(event):
    """Codex: a root Stop event carries no agent_id key; roots from cwd only."""
    if not stop_hook_event(event, lambda key: key in event):
        return None
    roots = [event["cwd"]] if nonempty(event.get("cwd")) else []
    return turn_end(event["session_id"], event["stop_hook_active"], roots, None)


def cursor_event(event):
    """Cursor: a completed stop; loop_count counts automatic follow-ups."""
    if event.get("hook_event_name") != "stop" or event.get("status") != "completed":
        return None
    count = event.get("loop_count")
    if not nonempty(event.get("conversation_id")) or type(count) is not int or count < 0:
        return None
    roots = string_list(event.get("workspace_roots")) + env_roots("CURSOR_PROJECT_DIR")
    return turn_end(event["conversation_id"], count > 0, roots, None)


def antigravity_event(event):
    """Antigravity: a Stop; one with an error is failed. fullyIdle is the waiter signal."""
    if not nonempty(event.get("conversationId")):
        return None
    for key in ("hook_event_name", "hookEventName"):
        if key in event and event[key] != "Stop":
            return None
    idle = event.get("fullyIdle")
    waiters = (not idle) if isinstance(idle, bool) else None
    return turn_end(event["conversationId"], None,
                    string_list(event.get("workspacePaths")), waiters,
                    failed="error" in event and event["error"] != "")


def devin_event(event):
    """Devin: Stop carries no cwd, so search the project variables, then the process cwd."""
    if not stop_hook_event(event, lambda key: key in event):
        return None
    roots = env_roots("DEVIN_PROJECT_DIR", "CLAUDE_PROJECT_DIR") + [os.getcwd()]
    return turn_end(event["session_id"], event["stop_hook_active"], roots, None)


ADAPTERS = {
    "claude": claude_event,
    "codex": codex_event,
    "cursor": cursor_event,
    "antigravity": antigravity_event,
    "devin": devin_event,
}


def find_state(roots):
    """Step 2: walk up from each root in order to the repository top."""
    for root in roots:
        directory = os.path.abspath(root)
        while True:
            candidate = os.path.join(directory, STATE_NAME)
            if os.path.isfile(candidate):
                return candidate
            parent = os.path.dirname(directory)
            if parent == directory or os.path.exists(os.path.join(directory, ".git")):
                break
            directory = parent
    return None


def parse_state(text):
    """Step 3: return (header, items, log line count); raise on any format violation."""
    header, items, log_lines, section, has_queue = {}, [], 0, None, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            has_queue = has_queue or section == "queue"
            continue
        if section is None:
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition(":")
            key = key.strip().lower()
            if sep and key:
                if key in header:
                    raise ValueError("duplicate header key")
                header[key] = value.strip()
        elif section == "queue":
            match = ITEM.match(line)
            if match:
                status = match.group(1).strip().lower()
                if status not in STATUSES:
                    raise ValueError("unknown status")
                rest = match.group(3)
                nxt = NEXT.search(rest)
                after = AFTER.search(rest)
                items.append({
                    "id": match.group(2),
                    "status": status,
                    "next": nxt.group(1).strip() if nxt else "",
                    "after": after.group(1) if after else None,
                })
        elif section == "log" and LOG_LINE.match(line):
            log_lines += 1
    if not has_queue:
        raise ValueError("no queue section")
    if "budget" in header:
        if not BUDGET.match(header["budget"]):
            raise ValueError("bad budget")
        header["budget"] = int(header["budget"])
    else:
        header["budget"] = DEFAULT_BUDGET
    return header, items, log_lines


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError("bad counter")
    return value


def fresh_sidecar(goal, pending):
    """Zero counters for a goal; pending is included only when the host tracks it."""
    side = {"goal": goal, "turns": 0, "key": None, "strikes": 0}
    if pending:
        side["pending"] = None
    return side


def load_sidecar(path, pending):
    """Step 6: a missing file is zero; anything unreadable or malformed raises.

    With pending true, also read the optional pending session (a string or null).
    """
    if not os.path.exists(path):
        return fresh_sidecar(None, pending)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("sidecar is not an object")
    side = {
        "goal": data.get("goal"),
        "turns": counter(data.get("turns")),
        "key": data.get("key"),
        "strikes": counter(data.get("strikes")),
    }
    if pending:
        side["pending"] = data.get("pending")
        if side["pending"] is not None and not isinstance(side["pending"], str):
            raise ValueError("bad pending")
    return side


def write_sidecar(path, data):
    """Atomic write: a temporary file in the same directory, then os.replace."""
    fd, tmp = tempfile.mkstemp(prefix=".agent-loop.", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def clear_pending(path, session):
    """Let an owned turn end: clear this session's pending; never create the sidecar."""
    if os.path.exists(path):
        side = load_sidecar(path, True)
        if side["pending"] == session:
            side["pending"] = None
            write_sidecar(path, side)
    return None


def decide(event, state_arg, host="claude"):
    """Return the continuation message, or None to let the turn end."""
    end = ADAPTERS[host](event)
    if end is None:
        return None
    path = state_arg or find_state(end["roots"])
    if not path or not os.path.isfile(path):
        return None
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as handle:
        header, items, log_lines = parse_state(handle.read())

    session = end["session"]
    if header.get("owner", "") != session:
        return None
    sidecar_path = os.path.join(os.path.dirname(path), SIDECAR_NAME)
    tracks_pending = end["hook_turn"] is None
    if end["failed"] or header.get("stop", ""):
        return clear_pending(sidecar_path, session) if tracks_pending else None

    open_ids = {item["id"] for item in items}
    actionable = [
        item for item in items
        if item["status"] == "doing"
        or (item["status"] == "ready" and (item["after"] is None or item["after"] not in open_ids))
    ]
    waiting = sum(1 for item in items if item["status"] == "waiting")
    user = sum(1 for item in items if item["status"] == "user")
    side = load_sidecar(sidecar_path, True) if tracks_pending else None
    hook_turn = side["pending"] == session if tracks_pending else end["hook_turn"]
    no_waiter = False
    if not actionable:
        if waiting and end["waiters"] is False and not hook_turn:
            no_waiter = True
        else:
            return clear_pending(sidecar_path, session) if tracks_pending else None

    if side is None:
        side = load_sidecar(sidecar_path, False)
    goal = digest(header.get("goal", ""))
    if side["goal"] != goal:
        side = fresh_sidecar(goal, tracks_pending)
    budget = header["budget"]
    if side["turns"] >= budget:
        return clear_pending(sidecar_path, session) if tracks_pending else None

    key = digest(json.dumps(
        [[[item["id"], item["status"], item["next"]] for item in items], log_lines]))
    side["strikes"] = side["strikes"] + 1 if hook_turn and key == side["key"] else 0
    side["key"] = key
    if side["strikes"] >= NO_PROGRESS_LIMIT:
        if tracks_pending:
            side["pending"] = None
        write_sidecar(sidecar_path, side)
        return None
    side["turns"] += 1
    if tracks_pending:
        side["pending"] = session
    write_sidecar(sidecar_path, side)
    turn = side["turns"]

    pick = next((item for item in actionable if item["status"] == "doing"),
                actionable[0] if actionable else None)
    if no_waiter:
        message = (
            "%s Loop idle in %s (turn %d/%d): %d waiting item(s) but no background "
            "task is running. For each waiting item that needs an external event, "
            "run its check; if the event has not happened, start its waiter as a "
            "background command. If an item waits for nothing external, change its "
            "status. Then end your turn." % (TAG, path, turn, budget, waiting)
        )
    else:
        message = (
            "%s Loop active in %s: turn %d/%d, %d actionable, %d waiting, %d need "
            "the user. Run the next iteration: re-read the file, reconcile it with "
            "evidence, take the next actionable item (now %s), handle its gate "
            "first if it needs one, act, verify against its done criterion, update "
            "the file, then continue, fix or stop. Begin your final message with "
            "the loop status line."
            % (TAG, path, turn, budget, len(actionable), waiting, user, pick["id"])
        )
    if side["strikes"] == 1:
        message += (
            " The queue did not change during the last automatic turn: record "
            "progress or the blocker; another unchanged turn ends automatic "
            "continuation."
        )
    if turn == budget:
        message += (
            " This is the last automatic turn the budget allows: checkpoint the "
            "current item, record state, set `stop: budget`, and end with a "
            "summary for the user."
        )
    return message


def continue_output(host, message):
    """Wrap the continuation message in the host's own output shape."""
    if host == "cursor":
        return {"followup_message": message}
    if host == "antigravity":
        return {"decision": "continue", "reason": message}
    return {"decision": "block", "reason": message}


def session_start_output(event):
    """Devin SessionStart: tell the new session its ID so it can set owner:."""
    if not nonempty(event.get("session_id")):
        return {}
    context = ("%s This session's ID is %s. Use it as the owner: value when you create "
               "or take over an agent-loop state file." % (TAG, event["session_id"]))
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": context}}


def respond(event, host, state_arg):
    """Return the JSON object to print for one event."""
    if host == "devin" and event.get("hook_event_name") == "SessionStart":
        return session_start_output(event)
    message = decide(event, state_arg, host)
    return continue_output(host, message) if message else {}


def main():
    output = {}
    try:
        host, state_arg = parse_args(sys.argv[1:])
        event = json.loads(sys.stdin.read() or "null")
        if isinstance(event, dict):
            output = respond(event, host, state_arg)
    except Exception:
        output = {}
    try:
        sys.stdout.write(json.dumps(output) + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
