#!/usr/bin/env python3
"""Claude Code Stop hook for the agent loop.

Usage: loop_hook.py [--state PATH]

Reads one Stop event as JSON on stdin and prints one JSON object on stdout.
It always exits 0. It asks Claude Code to continue only when the event comes
from the main session that owns the state file, the loop has no stop reason,
an item is actionable (or a waiting item has no waiter running), and the
budget and progress guards pass. Any error or unexpected input prints {} so
the turn may end. Python 3.8 or later, standard library only.
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
    """Return the --state path or None; raise on any other argument."""
    state = None
    args = iter(argv)
    for arg in args:
        if arg == "--state":
            state = next(args)
        else:
            raise ValueError("unknown argument")
    return state


def valid_event(event):
    """Step 1: a main-session Claude Code Stop event with a typed stop_hook_active."""
    if event.get("hook_event_name") != "Stop":
        return False
    if event.get("agent_id") is not None:
        return False
    session = event.get("session_id")
    if not isinstance(session, str) or not session:
        return False
    return isinstance(event.get("stop_hook_active"), bool)


def find_state(event):
    """Step 2: walk up from the event cwd, then CLAUDE_PROJECT_DIR, to the repository top."""
    roots = []
    if isinstance(event.get("cwd"), str) and event["cwd"]:
        roots.append(event["cwd"])
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        roots.append(os.environ["CLAUDE_PROJECT_DIR"])
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


def load_sidecar(path):
    """Step 6: a missing file is zero; anything unreadable or malformed raises."""
    if not os.path.exists(path):
        return {"goal": None, "turns": 0, "key": None, "strikes": 0}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("sidecar is not an object")
    return {
        "goal": data.get("goal"),
        "turns": counter(data.get("turns")),
        "key": data.get("key"),
        "strikes": counter(data.get("strikes")),
    }


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


def decide(event, state_arg):
    """Return the continuation message, or None to let the turn end."""
    if not valid_event(event):
        return None
    path = state_arg or find_state(event)
    if not path or not os.path.isfile(path):
        return None
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as handle:
        header, items, log_lines = parse_state(handle.read())

    if header.get("owner", "") != event["session_id"] or header.get("stop", ""):
        return None

    open_ids = {item["id"] for item in items}
    actionable = [
        item for item in items
        if item["status"] == "doing"
        or (item["status"] == "ready" and (item["after"] is None or item["after"] not in open_ids))
    ]
    waiting = sum(1 for item in items if item["status"] == "waiting")
    user = sum(1 for item in items if item["status"] == "user")
    hook_turn = event["stop_hook_active"]
    no_waiter = False
    if not actionable:
        tasks = event.get("background_tasks")
        if waiting and isinstance(tasks, list) and not tasks and not hook_turn:
            no_waiter = True
        else:
            return None

    sidecar_path = os.path.join(os.path.dirname(path), SIDECAR_NAME)
    side = load_sidecar(sidecar_path)
    goal = digest(header.get("goal", ""))
    if side["goal"] != goal:
        side = {"goal": goal, "turns": 0, "key": None, "strikes": 0}
    budget = header["budget"]
    if side["turns"] >= budget:
        return None

    key = digest(json.dumps(
        [[[item["id"], item["status"], item["next"]] for item in items], log_lines]))
    side["strikes"] = side["strikes"] + 1 if hook_turn and key == side["key"] else 0
    side["key"] = key
    if side["strikes"] >= NO_PROGRESS_LIMIT:
        write_sidecar(sidecar_path, side)
        return None
    side["turns"] += 1
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


def main():
    output = {}
    try:
        state_arg = parse_args(sys.argv[1:])
        event = json.loads(sys.stdin.read() or "null")
        if isinstance(event, dict):
            message = decide(event, state_arg)
            if message:
                output = {"decision": "block", "reason": message}
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
