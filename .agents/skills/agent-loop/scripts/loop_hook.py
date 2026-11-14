#!/usr/bin/env python3
"""Turn-end hook and read-only status command for the agent loop.

Usage:
  loop_hook.py [--host HOST] [--state PATH]
  loop_hook.py status [--state PATH] [--limit K]

Hook: HOST is claude (the default), codex, cursor, antigravity or devin. Reads
one turn-end event as JSON on stdin and prints one JSON object on stdout. It
always exits 0. It asks the host to continue only when the event comes from
the main session that owns the state file, the loop has no stop reason, an
item is actionable (or a waiting item has no waiter running), and the budget
and progress guards pass. An item is actionable when it is doing or ready and
every ID in its after: list has a closure line in Log and is not open in
Queue. With --host devin, a SessionStart event tells the session its ID
instead. After successful argument parsing, Antigravity no-continuation output
is {"decision": "stop"}; other hosts use {}. Argument-parse failures before
host resolution use {}.

Status: prints a plain-text summary of the state file found from --state or by
walking up from the current directory: header values, counts, doing items, the
next K ready items whose dependencies are met, the parallel wave when
parallel is above 1, waiting and user items, and every problem found, each
list capped at K (default 5). It never writes a file. Exit 0 when the file
was read, 2 when no state file is found, it cannot be read or the arguments
are wrong, with the reason on stderr.

Python 3.8 or later, standard library only.
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
DEFAULT_PARALLEL = 1
DEFAULT_LIMIT = 5
TRIES_LIMIT = 3
NO_PROGRESS_LIMIT = 3
STATUSES = ("ready", "doing", "waiting", "user")
OPEN_WORK = ("doing", "ready")
ITEM = re.compile(r"^[-*]\s+\[([^\]]*)\]\s+(\S+)(.*)$")
LOG_LINE = re.compile(r"^[-*]\s+\S")
CLOSURE = re.compile(r"(?<!\S)(\S+)\s+closed\b")
EVIDENCE_DASH = re.compile(r"\s[—–-]\s")
FIELD_NAMES = ("after", "writes", "tries", "wake", "check", "ask")
FIELDS = {name: re.compile(r"(?:^|[\s;])%s:\s*([^;]*)" % name) for name in FIELD_NAMES}
WHOLE = re.compile(r"^\d+$")
WHOLE_CAP = 10 ** 9
GLOB_START = re.compile(r"[*?\[]")
USAGE = "loop_hook.py status [--state PATH] [--limit K]"


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


def problem(state, line, reason, fix, fatal=False):
    """Record a problem; a fatal one makes the hook fail closed."""
    state["problems"].append({"line": line, "reason": reason, "fix": fix, "fatal": fatal})


def field(rest, name):
    """The text of an item's first `name:` field, or None when the item has none."""
    match = FIELDS[name].search(rest)
    return match.group(1).strip() if match else None


def fields(rest, name):
    """The texts of every `name:` field of an item, in order."""
    return [value.strip() for value in FIELDS[name].findall(rest)]


def whole(text):
    """A whole number from its digits, capped so huge values never fail to convert."""
    digits = text.lstrip("0") or "0"
    return int(digits) if len(digits) <= 9 else WHOLE_CAP


def id_list(values):
    """IDs separated by commas or whitespace across every after: field."""
    return [part for value in values for part in re.split(r"[\s,]+", value) if part]


def scope_list(values):
    """Path or glob scopes separated by commas across every writes: field; None when absent."""
    if not values:
        return None
    return [part.strip() for value in values for part in value.split(",") if part.strip()]


def parse_item(state, number, line, match):
    """Append one queue item with its fields and the problems of its line."""
    status, rest = match.group(1).strip().lower(), match.group(3)
    if status not in STATUSES:
        problem(state, number, "unknown status [%s]" % status,
                "use one of ready, doing, waiting, user", fatal=True)
    tries = field(rest, "tries")
    item = {"id": match.group(2), "status": status, "line": number, "text": line,
            "after": id_list(fields(rest, "after")), "writes": scope_list(fields(rest, "writes")),
            "tries": whole(tries) if tries is not None and WHOLE.match(tries) else 0}
    for name in ("wake", "check", "ask"):
        item[name] = field(rest, name) is not None
    state["items"].append(item)


def parse_header(state, number, line):
    """Record one `key: value` header line; a repeated key is fatal."""
    key, sep, value = line.partition(":")
    key = key.strip().lower()
    if not (sep and key):
        return
    if key in state["header"]:
        problem(state, number, "duplicate header key `%s`" % key,
                "keep one `%s:` line above ## Queue" % key, fatal=True)
        return
    state["header"][key] = value.strip()
    state["header_lines"][key] = number


def parse_log(state, line):
    """Count one Log entry and record the ID its closure line names.

    Only the text before the first dash that opens the evidence can name the
    closed ID, so evidence that mentions another closure names nothing.
    """
    if not LOG_LINE.match(line):
        return
    state["log_lines"] += 1
    match = CLOSURE.search(EVIDENCE_DASH.split(line.lstrip()[1:], 1)[0])
    if match:
        state["closed"].add(match.group(1))
        state["closures"] += 1


def whole_header(state, key, default, minimum):
    """The header value as a whole number >= minimum; default when absent; None when bad."""
    value = state["header"].get(key)
    if value is None:
        return default
    if WHOLE.match(value) and whole(value) >= minimum:
        return whole(value)
    problem(state, state["header_lines"][key], "bad %s `%s`" % (key, value),
            "set `%s:` to a whole number of at least %d or remove it" % (key, minimum),
            fatal=True)
    return None


def read_state(text, limit=DEFAULT_LIMIT):
    """Tolerant parse: header, items, closed IDs, log count and the problems found.

    limit caps the IDs listed inside one problem.
    """
    state = {"header": {}, "header_lines": {}, "items": [], "closed": set(), "log_lines": 0,
             "closures": 0, "problems": [], "limit": limit}
    section, has_queue = None, False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            has_queue = has_queue or section == "queue"
        elif section is None:
            if line and not line.startswith("#"):
                parse_header(state, number, line)
        elif section == "queue":
            match = ITEM.match(line)
            if match:
                parse_item(state, number, line, match)
            elif line.startswith(("-", "*")):
                problem(state, number, "queue line is not an item",
                        "write it as `- [status] ID title — done when: ...` or move it out "
                        "of ## Queue")
        elif section == "log":
            parse_log(state, line)
    if not has_queue:
        problem(state, 0, "no ## Queue section",
                "add a `## Queue` heading above the items", fatal=True)
    state["budget"] = whole_header(state, "budget", DEFAULT_BUDGET, 0)
    state["parallel"] = whole_header(state, "parallel", DEFAULT_PARALLEL, 1)
    check_dependencies(state)
    check_items(state)
    check_cycles(state)
    if state["items"] and all(item["blocked"] for item in state["items"]):
        problem(state, state["items"][0]["line"], "every open item is blocked by a dependency",
                "close or reconcile a dependency, or correct the after: fields")
    state["problems"].sort(key=lambda entry: entry["line"])
    return state


def check_dependencies(state):
    """Mark each item blocked by unmet or unknown dependencies; report unknown IDs.

    A dependency is met when its ID has a closure line in Log and is not open
    in Queue, unmet when it is open, and unknown otherwise.
    """
    open_ids = {item["id"] for item in state["items"]}
    for item in state["items"]:
        item["unmet"] = [dep for dep in item["after"] if dep in open_ids]
        item["unknown"] = [dep for dep in item["after"]
                           if dep not in open_ids and dep not in state["closed"]]
        item["blocked"] = bool(item["unmet"] or item["unknown"])
        if item["unknown"]:
            problem(state, item["line"],
                    "%s after: %s: neither an open item nor closed in Log"
                    % (item["id"], capped(item["unknown"], state["limit"])),
                    "correct the IDs, add the missing items, or record their closures in Log")


def check_items(state):
    """Report duplicate IDs, open-and-closed IDs, missing fields and exhausted tries."""
    seen = set()
    for item in state["items"]:
        ident, number, status = item["id"], item["line"], item["status"]
        if ident in seen:
            problem(state, number, "duplicate item ID %s" % ident,
                    "give each item its own ID; never reuse one")
        seen.add(ident)
        if ident in state["closed"]:
            problem(state, number, "%s is open in Queue and closed in Log" % ident,
                    "remove the queue line if the closure holds, or give the new work a new ID")
        if status == "waiting" and not (item["wake"] and item["check"]):
            problem(state, number, "waiting item %s lacks wake: or check:" % ident,
                    "add the event it waits for as wake: and the command that shows it as check:")
        if status == "user" and not item["ask"]:
            problem(state, number, "user item %s lacks ask:" % ident,
                    "record the question for the user as ask:")
        if status != "user" and item["tries"] >= TRIES_LIMIT:
            problem(state, number, "%s has tries: %d" % (ident, item["tries"]),
                    "mark it user with an ask: and continue with other items")


def check_cycles(state):
    """Report each dependency cycle among open items, at its first item's line."""
    graph, lines = {}, {}
    for item in state["items"]:
        graph.setdefault(item["id"], set()).update(item["unmet"])
        lines.setdefault(item["id"], item["line"])
    for component in strongly_connected(graph):
        if len(component) > 1 or component[0] in graph[component[0]]:
            members = sorted(component, key=lambda ident: lines[ident])
            problem(state, lines[members[0]],
                    "dependency cycle among %s" % capped(members, state["limit"]),
                    "remove one after: field in the cycle or split the work")


def strongly_connected(graph):
    """Tarjan's strongly connected components, iterative, in graph order."""
    index, low, stack, on_stack, components = {}, {}, [], set(), []
    for root in graph:
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is not None:
                if child not in index:
                    index[child] = low[child] = len(index)
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph[child]))))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
    return components


def capped(values, limit):
    """Join at most limit values with commas, ending with `+N more` when capped."""
    shown = ", ".join(values[:limit])
    extra = len(values) - limit
    return shown + (", +%d more" % extra if extra > 0 else "")


def parse_state(text):
    """Hook view: headers, queue items and log count; raise on any fatal problem."""
    state = read_state(text)
    fatal = [entry["reason"] for entry in state["problems"] if entry["fatal"]]
    if fatal:
        raise ValueError(fatal[0])
    header = dict(state["header"], budget=state["budget"], parallel=state["parallel"])
    return header, state["items"], state["log_lines"]


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

    actionable = [
        item for item in items
        if item["status"] in OPEN_WORK and not item["blocked"]
    ]
    if header["parallel"] > 1 and any(
            item["status"] == "waiting" and item["writes"] is not None for item in items):
        open_wave = wave({"items": items, "parallel": header["parallel"]})[0]
        actionable = [item for item in actionable
                      if item["status"] == "doing" or item["id"] in open_wave]
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
        [[[item["id"], item["status"]] for item in items], log_lines]))
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
            "task is running. Re-read the state and run each waiting item's check. "
            "If its event has not happened, follow pass 5's Waiter rule for this "
            "host and mode: complete required blocking collection, use a supported "
            "wake route within its lifetime, or record collection for the next "
            "user message or explicit resume. Reconcile an item that needs no "
            "external event. Complete required coverage before ending your turn. "
            "Do not start an unsupported waiter or scheduled queue execution."
            % (TAG, path, turn, budget, waiting)
        )
    else:
        message = (
            "%s Loop active in %s: turn %d/%d, %d actionable, %d waiting, %d need "
            "the user. Run the next iteration: read the state, reconcile it with "
            "evidence, take the next actionable item (now %s), handle its gate "
            "first if it needs one, act, verify against its done criterion, update "
            "the file, then continue, fix or stop. Include the loop facts in your "
            "final message under pass 7's applicable form rule. For a state file too "
            "long to read whole, python3 \"%s\" status --state \"%s\" lists the "
            "next items and any problems."
            % (TAG, path, turn, budget, len(actionable), waiting, user, pick["id"],
               os.path.abspath(__file__), path)
        )
    if side["strikes"]:
        remaining = NO_PROGRESS_LIMIT - side["strikes"]
        message += (
            " The hook's no-progress key did not change during the last automatic "
            "turn. Record evidenced progress or the blocker; %s with the same key "
            "end%s automatic continuation."
            % (("another turn", "s") if remaining == 1 else ("%d more turns" % remaining, ""))
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


class StatusError(Exception):
    """A status failure: what went wrong, what was expected and what to try."""


def status_args(argv):
    """Return (--state path or None, limit) for the status command."""
    options = {}
    args = iter(argv)
    for arg in args:
        if arg not in ("--state", "--limit") or arg in options:
            raise StatusError("unknown or repeated argument `%s`. Expected: %s. Try the "
                              "command without it." % (arg, USAGE))
        value = next(args, None)
        if value is None:
            raise StatusError("%s needs a value. Expected: %s." % (arg, USAGE))
        options[arg] = value
    limit = options.get("--limit", str(DEFAULT_LIMIT))
    if not WHOLE.match(limit) or whole(limit) < 1:
        raise StatusError("bad --limit `%s`. Expected a whole number of at least 1. "
                          "Try --limit %d." % (limit, DEFAULT_LIMIT))
    return options.get("--state"), whole(limit)


def status_path(state_arg):
    """The state file from --state, else found by walking up from the current directory."""
    if state_arg is not None:
        if not os.path.isfile(state_arg):
            raise StatusError("no state file at %s. Expected an existing %s file. Try the "
                              "path of the loop's state file, or omit --state to search "
                              "from the current directory." % (state_arg, STATE_NAME))
        return os.path.abspath(state_arg)
    path = find_state([os.getcwd()])
    if path is None:
        raise StatusError("no %s found from %s up to the repository top. Expected a state "
                          "file at the workspace root. Try running from inside the "
                          "workspace, or pass --state PATH." % (STATE_NAME, os.getcwd()))
    return os.path.abspath(path)


def read_text(path):
    """The state file's text; StatusError when it cannot be read as UTF-8."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise StatusError("cannot read %s (%s). Expected a readable UTF-8 text file. Try "
                          "checking its permissions and encoding." % (path, error))


def static_prefix(scope):
    """The text of a scope before its first glob character, without a leading ./."""
    prefix = GLOB_START.split(scope, 1)[0]
    while prefix.startswith("./"):
        prefix = prefix[2:]
    return prefix


def overlap(first, second):
    """Two scopes overlap when one static prefix is a prefix of the other."""
    a, b = static_prefix(first), static_prefix(second)
    return a.startswith(b) or b.startswith(a)


def wave(state):
    """The ready, unblocked items with disjoint writes: scopes that fit the free slots."""
    held = [item for item in state["items"]
            if item["status"] in ("doing", "waiting") and item["writes"] is not None]
    slots = state["parallel"] - len(held)
    scopes = [scope for item in held for scope in item["writes"]]
    taken = []
    for item in state["items"]:
        if len(taken) >= slots:
            break
        if item["status"] != "ready" or item["blocked"] or not item["writes"]:
            continue
        if any(overlap(mine, other) for mine in item["writes"] for other in scopes):
            continue
        taken.append(item["id"])
        scopes.extend(item["writes"])
    return taken, max(slots, 0)


def describe(item, limit):
    """An item's full line, with the reason when a dependency blocks it."""
    reasons = ["%s open" % dep for dep in item["unmet"]]
    reasons += ["%s unknown" % dep for dep in item["unknown"]]
    if not reasons:
        return item["text"]
    return "%s  (blocked: %s)" % (item["text"], capped(reasons, limit))


def listing(title, values, limit):
    """A titled, capped list of lines; `title none` when empty."""
    if not values:
        return ["%s none" % title]
    lines = [title] + ["  " + value for value in values[:limit]]
    if len(values) > limit:
        lines.append("  +%d more" % (len(values) - limit))
    return lines


def header_lines(path, state):
    """Section 1: the path and the header values the loop runs on."""
    header = state["header"]
    lines = ["state: %s" % path]
    for key in ("goal", "owner", "stop", "async gates"):
        lines.append("%s: %s" % (key, header.get(key) or "(none)"))
    for key, default in (("budget", DEFAULT_BUDGET), ("parallel", DEFAULT_PARALLEL)):
        value = header.get(key)
        lines.append("%s: %s" % (key, "%d (default)" % default if value is None else value))
    return lines


def matching(state, status, blocked=None):
    """The items with a status, optionally only the blocked or only the unblocked ones."""
    return [item for item in state["items"] if item["status"] == status
            and (blocked is None or item["blocked"] == blocked)]


def count_line(state):
    """Section 2: counts by status, with ready split by its dependencies."""
    counts = [len(matching(state, "doing")), len(matching(state, "ready", False)),
              len(matching(state, "ready", True)), len(matching(state, "waiting")),
              len(matching(state, "user")), state["closures"]]
    return ("counts: %d doing, %d ready, %d ready but blocked, %d waiting, %d need you, "
            "%d closed" % tuple(counts))


def problem_lines(state, limit):
    """Section 7: every problem with its line number, reason and fix."""
    values = ["%s: %s; %s" % ("line %d" % entry["line"] if entry["line"] else "file",
                              entry["reason"], entry["fix"])
              for entry in state["problems"]]
    return listing("problems:", values, limit)


def status_report(path, text, limit):
    """The plain-text status of one state file; its size does not grow with the queue."""
    state = read_state(text, limit)

    def lines_of(status, blocked=None):
        return [describe(item, limit) for item in matching(state, status, blocked)]

    lines = header_lines(path, state) + [count_line(state)]
    lines += listing("doing:", lines_of("doing"), limit)
    lines += listing("next:", lines_of("ready", False), limit)
    if state["parallel"] is not None and state["parallel"] > 1:
        taken, slots = wave(state)
        lines.append("wave: %s (%d free slot%s)" % (
            capped(taken, limit) if taken else "none", slots, "" if slots == 1 else "s"))
    lines += listing("waiting:", lines_of("waiting"), limit)
    lines += listing("need you:", lines_of("user"), limit)
    lines += problem_lines(state, limit)
    return "\n".join(lines) + "\n"


def status_main(argv):
    """Run the read-only status command; return its exit code."""
    try:
        state_arg, limit = status_args(argv)
        path = status_path(state_arg)
        report = status_report(path, read_text(path), limit)
    except StatusError as error:
        sys.stderr.write("loop_hook.py status: %s\n" % error)
        return 2
    try:
        sys.stdout.buffer.write(report.encode("utf-8", "surrogateescape"))
        sys.stdout.buffer.flush()
    except (OSError, AttributeError, ValueError) as error:
        silence_stdout()
        try:
            sys.stderr.write("loop_hook.py status: cannot write the report (%s). Expected a "
                             "writable standard output. Try running it without a closed "
                             "pipe or a full disk.\n" % error)
        except OSError:
            pass
        return 2
    return 0


def silence_stdout():
    """Point standard output at the null device so the exit flush cannot fail again."""
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, sys.stdout.fileno())
        os.close(null)
    except (OSError, ValueError, AttributeError):
        pass


def main():
    if sys.argv[1:2] == ["status"]:
        return status_main(sys.argv[2:])
    output = {}
    host = "claude"
    try:
        host, state_arg = parse_args(sys.argv[1:])
        event = json.loads(sys.stdin.read() or "null")
        if isinstance(event, dict):
            output = respond(event, host, state_arg)
    except Exception:
        output = {}
    if host == "antigravity" and not output:
        output = {"decision": "stop"}
    try:
        sys.stdout.write(json.dumps(output) + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
