#!/usr/bin/env python3
"""Fixture tests for loop_hook.py and the SKILL.md hook command.

Each case runs the hook as a subprocess against a temporary workspace. Run from
the skill directory (python3 scripts/test_loop_hook.py) or from anywhere else;
the hook and SKILL.md are located relative to this file.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS)
HOOK = os.path.join(SCRIPTS, "loop_hook.py")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
OWNER = "sess-owner"
GOAL = "Ship the export feature — done when: CI is green"
READY = "- [ready] T1 Add the endpoint — done when: tests pass"
DOING = "- [doing] T1 Add the endpoint — done when: tests pass; next: empty result set"
WAITING = ("- [waiting] T3 CI run — done when: required CI passes; "
           "wake: CI finishes; check: ci status")
USER = "- [user] T4 Push — done when: remote updated; ask: push to main?; asked: 2026-11-01"
STATE = """# Agent loop

goal: {goal}
owner: {owner}
stop: {stop}
async gates: design choice
budget: {budget}

## Queue
{items}

## Log
"""
INSTRUCTION = (
    " Run the next iteration: re-read the file, reconcile it with evidence, take "
    "the next actionable item (now T1), handle its gate first if it needs one, act, "
    "verify against its done criterion, update the file, then continue, fix or "
    "stop. Include the loop facts in your final message under pass 7's applicable form rule."
)
NO_PROGRESS = "The hook's no-progress key did not change during the last automatic turn"
LAST_TURN = "This is the last automatic turn the budget allows"
HOOK_ENV_KEYS = ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "CLAUDE_SKILL_DIR")


def event(root, session=OWNER, continued=False, **extra):
    """A Claude Code Stop payload with the fields observed on the host."""
    ev = {"hook_event_name": "Stop", "session_id": session,
          "transcript_path": "/home/u/.claude/projects/p/%s.jsonl" % session,
          "cwd": root, "prompt_id": "prompt-2", "permission_mode": "default",
          "effort": "medium", "stop_hook_active": continued,
          "last_assistant_message": "Completed the current item.",
          "background_tasks": [], "session_crons": []}
    ev.update(extra)
    return ev


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in HOOK_ENV_KEYS}
    env.update(extra)
    return env


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._elsewhere = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.elsewhere = os.path.realpath(self._elsewhere.name)
        os.mkdir(os.path.join(self.root, ".git"))
        self.state = os.path.join(self.root, ".agent-loop.md")
        self.sidecar = os.path.join(self.root, ".agent-loop.hook.json")

    def tearDown(self):
        self._tmp.cleanup()
        self._elsewhere.cleanup()

    def write_state(self, items=READY, owner=OWNER, stop="", budget=50, goal=GOAL,
                    keep_sidecar=False, text=None):
        if not keep_sidecar and os.path.exists(self.sidecar):
            os.remove(self.sidecar)
        if text is None:
            text = STATE.format(goal=goal, owner=owner, stop=stop, budget=budget, items=items)
        with open(self.state, "w", encoding="utf-8") as handle:
            handle.write(text)

    def log(self, n):
        with open(self.state, "a", encoding="utf-8") as handle:
            handle.write("- 2026-11-01T10:0%dZ T%d closed — tests pass\n" % (n, n + 10))

    def write_sidecar(self, content):
        with open(self.sidecar, "w", encoding="utf-8") as handle:
            handle.write(content)

    def sidecar_data(self):
        with open(self.sidecar, encoding="utf-8") as handle:
            return json.load(handle)

    def check_output(self, proc):
        """Exit 0, no stderr, exactly one JSON object line."""
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertTrue(proc.stdout.endswith("\n"), proc.stdout)
        self.assertEqual(proc.stdout.count("\n"), 1, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertIsInstance(out, dict)
        return out

    def run_raw(self, stdin, args=(), env=None):
        proc = subprocess.run([sys.executable, HOOK] + list(args), input=stdin,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, env=env or clean_env(),
                              cwd=self.elsewhere, timeout=20)
        return self.check_output(proc)

    def hook(self, ev, *args):
        return self.run_raw(json.dumps(ev), args)

    def reason(self, out):
        self.assertEqual(sorted(out), ["decision", "reason"], out)
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("[agent-loop] "), out["reason"])
        return out["reason"]

    def assert_block(self, out, *fragments):
        text = self.reason(out)
        for fragment in fragments:
            self.assertIn(fragment, text)
        return text

    def assert_stop(self, out):
        self.assertEqual(out, {})


class ContinueTest(Base):
    def test_continue_with_ready_exact_output(self):
        self.write_state()
        text = ("[agent-loop] Loop active in %s: turn 1/50, 1 actionable, 0 waiting, "
                "0 need the user." % self.state) + INSTRUCTION
        self.assertEqual(self.hook(event(self.root)), {"decision": "block", "reason": text})
        data = self.sidecar_data()
        self.assertEqual(sorted(data), ["goal", "key", "strikes", "turns"])
        self.assertEqual((data["turns"], data["strikes"]), (1, 0))

    def test_continue_with_doing(self):
        self.write_state(items=DOING)
        self.assert_block(self.hook(event(self.root)), "turn 1/50, 1 actionable")

    def test_counts_waiting_and_user(self):
        self.write_state(items="\n".join([READY, WAITING, USER]))
        self.assert_block(self.hook(event(self.root)),
                          "1 actionable, 1 waiting, 1 need the user")

    def test_after_blocks_ready_until_owner_clears_edge(self):
        items = "\n".join([WAITING, "- [ready] T5 Deploy — done when: live; after: T3"])
        self.write_state(items=items)
        running = event(self.root, background_tasks=[{"id": "b1"}])
        self.assert_stop(self.hook(running))
        self.write_state(items="- [ready] T5 Deploy — done when: live")
        with open(self.state, "a", encoding="utf-8") as handle:
            handle.write("- 2026-11-01T10:00Z T3 closed — required CI passes\n")
        self.assert_block(self.hook(running), "1 actionable")

    def test_message_names_first_actionable_item_past_blocked_one(self):
        items = "\n".join(["- [ready] T1 Deploy — done when: live; after: T2",
                           "- [user] T2 Approve — ask: deploy?; asked: 2026-11-01",
                           "- [ready] T3 Docs — done when: page updated"])
        self.write_state(items=items)
        self.assert_block(self.hook(event(self.root)), "take the next actionable item (now T3)")

    def test_message_names_doing_item_before_earlier_ready_item(self):
        items = "\n".join(["- [ready] T1 Docs — done when: page updated",
                           "- [doing] T2 Fix — done when: tests pass; next: rerun"])
        self.write_state(items=items)
        self.assert_block(self.hook(event(self.root)), "take the next actionable item (now T2)")

    def test_state_found_from_subdirectory_and_project_dir_and_flag(self):
        sub = os.path.join(self.root, "src", "pkg")
        os.makedirs(sub)
        self.write_state()
        self.assert_block(self.hook(event(sub)), "turn 1/50")
        self.write_state()
        out = self.run_raw(json.dumps(event(self.elsewhere)),
                           env=clean_env(CLAUDE_PROJECT_DIR=self.root))
        self.assert_block(out, "turn 1/50")
        self.write_state()
        self.assert_block(self.hook(event(self.elsewhere), "--state", self.state), "turn 1/50")

    def test_walk_stops_at_repository_top(self):
        inner = os.path.join(self.root, "nested")
        os.makedirs(os.path.join(inner, ".git"))
        self.write_state()
        self.assert_stop(self.hook(event(inner)))

    def test_no_state_file(self):
        self.assert_stop(self.hook(event(self.root)))
        self.assert_stop(self.hook(event(self.root), "--state",
                                   os.path.join(self.root, "missing.md")))


class IdleTest(Base):
    def test_idle_with_running_waiter(self):
        self.write_state(items="\n".join([WAITING, USER]))
        self.assert_stop(self.hook(event(self.root, background_tasks=[{"id": "b1"}])))
        self.assertFalse(os.path.exists(self.sidecar))

    def test_only_user_items_is_idle(self):
        self.write_state(items=USER)
        self.assert_stop(self.hook(event(self.root)))

    def test_waiting_without_waiter_blocks_once(self):
        self.write_state(items="\n".join([WAITING, USER]))
        text = ("[agent-loop] Loop idle in %s (turn 1/50): 1 waiting item(s) but no "
                "background task is running. Re-read the state and run each waiting item's check. "
                "If its event has not happened, follow pass 5's Waiter rule for this "
                "host and mode: complete required blocking collection, use a supported "
                "wake route within its lifetime, or record collection for the next "
                "user message or explicit resume. Reconcile an item that needs no "
                "external event. Complete required coverage before ending your turn. "
                "Do not start an unsupported waiter or scheduled queue execution." % self.state)
        self.assertEqual(self.hook(event(self.root)), {"decision": "block", "reason": text})
        self.assert_stop(self.hook(event(self.root, continued=True)))

    def test_waiting_without_background_tasks_field_is_idle(self):
        self.write_state(items=WAITING)
        ev = event(self.root)
        del ev["background_tasks"]
        self.assert_stop(self.hook(ev))


class GuardTest(Base):
    def test_each_stop_value(self):
        for stop in ("done", "budget", "gate: approve the push?",
                     "blocked: no credentials; a token would unblock it", "paused"):
            with self.subTest(stop=stop):
                self.write_state(stop=stop)
                self.assert_stop(self.hook(event(self.root)))

    def test_non_owner_and_empty_owner(self):
        for owner in ("sess-other", "", "claim"):
            with self.subTest(owner=owner):
                self.write_state(owner=owner)
                self.assert_stop(self.hook(event(self.root)))
        self.write_state(text=STATE.format(goal=GOAL, owner=OWNER, stop="", budget=50,
                                           items=READY).replace("owner: %s\n" % OWNER, ""))
        self.assert_stop(self.hook(event(self.root)))

    def test_agent_id_present(self):
        self.write_state()
        self.assert_stop(self.hook(event(self.root, agent_id="agent-1")))
        self.write_state()
        self.assert_block(self.hook(event(self.root, agent_id=None)))

    def test_wrong_event(self):
        for name in ("stop", "SubagentStop", "PreToolUse", None):
            with self.subTest(name=name):
                self.write_state()
                self.assert_stop(self.hook(event(self.root, hook_event_name=name)))

    def test_stop_hook_active_must_be_bool(self):
        for value in ("true", 1, 0, None):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.hook(event(self.root, stop_hook_active=value)))
        self.write_state()
        ev = event(self.root)
        del ev["stop_hook_active"]
        self.assert_stop(self.hook(ev))

    def test_session_id_empty_or_not_string(self):
        for value in ("", None, 7, ["sess-owner"]):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.hook(event(self.root, session=value)))

    def test_duplicate_header_key(self):
        text = STATE.format(goal=GOAL, owner=OWNER, stop="", budget=50, items=READY)
        self.write_state(text=text.replace("stop: \n", "stop:\nstop: paused\n"))
        self.assert_stop(self.hook(event(self.root)))

    def test_invalid_budgets(self):
        for budget in ("50 invalid", "0", "-1", "", "5.0", "fifty"):
            with self.subTest(budget=budget):
                self.write_state(budget=budget)
                self.assert_stop(self.hook(event(self.root)))

    def test_budget_absent_defaults_to_50(self):
        text = STATE.format(goal=GOAL, owner=OWNER, stop="", budget=50, items=READY)
        self.write_state(text=text.replace("budget: 50\n", ""))
        self.assert_block(self.hook(event(self.root)), "turn 1/50")

    def test_unknown_status(self):
        for status in ("done", "x", "blocked", ""):
            with self.subTest(status=status):
                self.write_state(items=READY + "\n- [%s] T9 Other — done when: x" % status)
                self.assert_stop(self.hook(event(self.root)))

    def test_missing_queue(self):
        text = STATE.format(goal=GOAL, owner=OWNER, stop="", budget=50, items=READY)
        self.write_state(text=text.replace("## Queue", "## Work"))
        self.assert_stop(self.hook(event(self.root)))

    def test_corrupt_sidecar(self):
        for content in ("{not json", "[]", '"text"',
                        json.dumps({"goal": None, "turns": -1, "key": None, "strikes": 0}),
                        json.dumps({"goal": None, "turns": True, "key": None, "strikes": 0}),
                        json.dumps({"goal": None, "turns": 0, "key": None, "strikes": -1}),
                        json.dumps({"goal": None, "turns": 1.0, "key": None, "strikes": 0}),
                        json.dumps({"goal": None, "key": None, "strikes": 0})):
            with self.subTest(content=content):
                self.write_state()
                self.write_sidecar(content)
                self.assert_stop(self.hook(event(self.root)))
                with open(self.sidecar, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), content)


class AccountingTest(Base):
    def test_budget_exhaustion(self):
        self.write_state(budget=2)
        first = self.assert_block(self.hook(event(self.root)), "turn 1/2")
        self.assertNotIn(LAST_TURN, first)
        self.log(1)
        self.assert_block(self.hook(event(self.root, continued=True)), "turn 2/2", LAST_TURN)
        self.log(2)
        self.assert_stop(self.hook(event(self.root, continued=True)))
        self.assert_stop(self.hook(event(self.root)))
        self.assertEqual(self.sidecar_data()["turns"], 2)

    def test_raising_budget_resumes_only_after_stop_cleared(self):
        self.write_state(budget=1)
        self.assert_block(self.hook(event(self.root)), "turn 1/1", LAST_TURN)
        self.write_state(budget=2, stop="budget", keep_sidecar=True)
        self.assert_stop(self.hook(event(self.root)))
        self.write_state(budget=2, keep_sidecar=True)
        self.assert_block(self.hook(event(self.root)), "turn 2/2")

    def test_no_progress(self):
        self.write_state()
        self.assertNotIn(NO_PROGRESS, self.reason(self.hook(event(self.root))))
        self.assert_block(self.hook(event(self.root, continued=True)), "turn 2/50", NO_PROGRESS)
        self.assertEqual(self.sidecar_data()["strikes"], 1)
        self.assert_stop(self.hook(event(self.root, continued=True)))
        data = self.sidecar_data()
        self.assertEqual((data["turns"], data["strikes"]), (2, 2))

    def test_user_turn_resets_strikes(self):
        self.write_state()
        self.hook(event(self.root))
        self.hook(event(self.root, continued=True))
        text = self.reason(self.hook(event(self.root)))
        self.assertNotIn(NO_PROGRESS, text)
        self.assertEqual(self.sidecar_data()["strikes"], 0)

    def test_next_change_counts_as_progress(self):
        self.write_state(items=DOING)
        self.hook(event(self.root))
        self.write_state(items=DOING.replace("empty result set", "pagination"),
                         keep_sidecar=True)
        text = self.assert_block(self.hook(event(self.root, continued=True)), "turn 2/50")
        self.assertNotIn(NO_PROGRESS, text)

    def test_status_and_log_changes_count_as_progress(self):
        self.write_state(items=READY)
        self.hook(event(self.root))
        self.write_state(items=DOING, keep_sidecar=True)
        self.assertNotIn(NO_PROGRESS, self.reason(self.hook(event(self.root, continued=True))))
        self.log(1)
        self.assertNotIn(NO_PROGRESS, self.reason(self.hook(event(self.root, continued=True))))

    def test_text_outside_queue_items_is_not_progress(self):
        self.write_state(items=DOING)
        self.hook(event(self.root))
        self.write_state(items=DOING.replace("tests pass", "all tests pass"),
                         keep_sidecar=True)
        self.assert_block(self.hook(event(self.root, continued=True)), NO_PROGRESS)

    def test_changing_goal_resets_turns(self):
        self.write_state(budget=1)
        self.hook(event(self.root))
        self.assert_stop(self.hook(event(self.root)))
        self.write_state(budget=1, goal="Ship the import feature — done when: CI is green",
                         keep_sidecar=True)
        self.assert_block(self.hook(event(self.root)), "turn 1/1")


class OutputTest(Base):
    def test_non_json_and_odd_stdin(self):
        self.write_state()
        for stdin in ("", "not json", "[]", "null", "42", '{"hook_event_name": "Stop"',
                      "[" * 100000):
            with self.subTest(stdin=stdin[:20]):
                self.assert_stop(self.run_raw(stdin))

    def test_unknown_or_incomplete_arguments(self):
        self.write_state()
        for args in (["--host", "bogus"], ["--max-streak", "3"], ["--state"], ["extra"]):
            with self.subTest(args=args):
                self.assert_stop(self.hook(event(self.root), *args))


class FrontmatterCommandTest(Base):
    def command(self):
        with open(SKILL_MD, encoding="utf-8") as handle:
            text = handle.read()
        front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(front)
        block = re.search(r"^hooks:\n(?:[ \t].*\n?)*", front.group(1) + "\n", re.M)
        self.assertIsNotNone(block, "no hooks key in frontmatter")
        self.assertRegex(block.group(0), r"\n  Stop:\n    - hooks:\n        - type: command\n")
        match = re.search(r"^\s+command: '((?:[^']|'')*)'\s*$", block.group(0), re.M)
        self.assertIsNotNone(match, "no single-quoted command")
        return match.group(1).replace("''", "'")

    def run_command(self, env):
        self.write_state()
        proc = subprocess.run(["sh", "-c", self.command()], input=json.dumps(event(self.root)),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, env=env, cwd=self.root, timeout=20)
        return self.check_output(proc)

    def test_plugin_root_is_skill_dir(self):
        with tempfile.TemporaryDirectory() as home:
            out = self.run_command(clean_env(CLAUDE_PLUGIN_ROOT=SKILL_DIR, HOME=home))
        self.assert_block(out, "turn 1/50")

    def test_project_skill_symlink(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            skills = os.path.join(project, ".claude", "skills")
            os.makedirs(skills)
            os.symlink(SKILL_DIR, os.path.join(skills, "agent-loop"))
            out = self.run_command(clean_env(CLAUDE_PROJECT_DIR=project, HOME=home))
        self.assert_block(out, "turn 1/50")

    def test_plugin_root_with_unrelated_script_uses_nested_skill(self):
        with tempfile.TemporaryDirectory() as plugin, tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(plugin, "scripts"))
            with open(os.path.join(plugin, "scripts", "loop_hook.py"), "w") as handle:
                handle.write("print('{\"unrelated\": true}')\n")
            os.makedirs(os.path.join(plugin, "skills"))
            os.symlink(SKILL_DIR, os.path.join(plugin, "skills", "agent-loop"))
            out = self.run_command(clean_env(CLAUDE_PLUGIN_ROOT=plugin, HOME=home))
        self.assert_block(out, "turn 1/50")

    def test_failing_interpreter_or_script_prints_empty_object(self):
        with tempfile.TemporaryDirectory() as fake, tempfile.TemporaryDirectory() as home:
            skill = os.path.join(fake, "agent-loop")
            os.makedirs(os.path.join(skill, "scripts"))
            with open(os.path.join(skill, "SKILL.md"), "w") as handle:
                handle.write("---\nname: agent-loop\n---\n")
            with open(os.path.join(skill, "scripts", "loop_hook.py"), "w") as handle:
                handle.write("this is not python\n")
            out = self.run_command(clean_env(CLAUDE_PLUGIN_ROOT=skill, HOME=home))
            self.assert_stop(out)
            bindir = os.path.join(fake, "bin")
            os.makedirs(bindir)
            for tool in ("grep", "sh"):
                for prefix in ("/usr/bin", "/bin"):
                    if os.path.exists(os.path.join(prefix, tool)):
                        os.symlink(os.path.join(prefix, tool), os.path.join(bindir, tool))
                        break
            out = self.run_command(clean_env(CLAUDE_PLUGIN_ROOT=SKILL_DIR, HOME=home, PATH=bindir))
            self.assert_stop(out)

    def test_no_script_found(self):
        with tempfile.TemporaryDirectory() as home:
            out = self.run_command(clean_env(HOME=home))
        self.assert_stop(out)
        self.assertFalse(os.path.exists(self.sidecar))


HOST_ENV_KEYS = HOOK_ENV_KEYS + ("CURSOR_PROJECT_DIR", "DEVIN_PROJECT_DIR")


def host_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in HOST_ENV_KEYS}
    env.update(extra)
    return env


def codex_event(root, session=OWNER, continued=False, **extra):
    """A Codex root Stop payload: the nine fields of the host's input schema."""
    ev = {"session_id": session, "turn_id": "1", "transcript_path": None, "cwd": root,
          "hook_event_name": "Stop", "model": "example-model", "permission_mode": "default",
          "stop_hook_active": continued, "last_assistant_message": "Finished this pass."}
    ev.update(extra)
    return ev


def cursor_event(root, session=OWNER, loop_count=0, **extra):
    """A Cursor stop payload as the interactive client builds it."""
    ev = {"conversation_id": session, "session_id": session, "generation_id": "gen-1",
          "hook_event_name": "stop", "cursor_version": "2026.11.05",
          "workspace_roots": [root], "user_email": None, "transcript_path": None,
          "model": "example-model", "status": "completed", "loop_count": loop_count,
          "input_tokens": 100, "output_tokens": 10}
    ev.update(extra)
    return ev


def antigravity_event(root, session=OWNER, **extra):
    """An Antigravity Stop payload with its public fields."""
    ev = {"conversationId": session, "workspacePaths": [root],
          "transcriptPath": "/home/u/.gemini/brain/%s/transcript_full.jsonl" % session,
          "artifactDirectoryPath": "/home/u/.gemini/brain/%s" % session,
          "modelName": "auto", "executionNum": 0, "terminationReason": "NO_TOOL_CALL",
          "error": "", "fullyIdle": True}
    ev.update(extra)
    return ev


def devin_event(session=OWNER, continued=False, **extra):
    """A Devin Stop payload: no cwd, no agent_id, no background task list."""
    ev = {"hook_event_name": "Stop", "stop_hook_active": continued,
          "last_assistant_message": "The current item is complete.",
          "session_id": session, "prompt_id": "prompt-1"}
    ev.update(extra)
    return ev


def active_text(state, turn=1):
    return ("[agent-loop] Loop active in %s: turn %d/50, 1 actionable, 0 waiting, "
            "0 need the user." % (state, turn)) + INSTRUCTION


class HostBase(Base):
    def run_host(self, host, ev, env=None, cwd=None, args=()):
        proc = subprocess.run([sys.executable, HOOK, "--host", host] + list(args),
                              input=json.dumps(ev), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True,
                              env=env or host_env(), cwd=cwd or self.elsewhere, timeout=20)
        return self.check_output(proc)

    def message(self, out, key, decision=None):
        expected = [key] if decision is None else ["decision", key]
        self.assertEqual(sorted(out), sorted(expected), out)
        if decision is not None:
            self.assertEqual(out["decision"], decision)
        self.assertTrue(out[key].startswith("[agent-loop] "), out[key])
        return out[key]

    def accepted(self):
        """Control: the host's baseline event continues, so a rejection below is specific."""
        self.write_state()
        self.message(self.control_output(), *self.CONTINUE_KEY)

    def write_rival_state(self):
        """A valid state file in the other directory that another session owns."""
        with open(os.path.join(self.elsewhere, ".agent-loop.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(STATE.format(goal=GOAL, owner="sess-other", stop="", budget=50,
                                      items=READY))


class ArgumentTest(HostBase):
    def test_explicit_claude_host_matches_default(self):
        self.write_state()
        out = self.run_host("claude", event(self.root))
        self.assertEqual(out, {"decision": "block", "reason": active_text(self.state)})

    def test_unknown_repeated_or_valueless_host(self):
        self.write_state()
        for args in (["--host", "gemini"], ["--host", "Codex"], ["--host", ""], ["--host"],
                     ["--host", "claude", "--host", "claude"],
                     ["--state", self.state, "--state", self.state]):
            with self.subTest(args=args):
                self.assert_stop(self.hook(event(self.root), *args))


class CodexTest(HostBase):
    CONTINUE_KEY = ("reason", "block")

    def codex(self, ev, env=None):
        return self.run_host("codex", ev, env=env)

    def control_output(self):
        return self.codex(codex_event(self.root))

    def test_continue_exact_output(self):
        self.write_state()
        self.assertEqual(self.codex(codex_event(self.root)),
                         {"decision": "block", "reason": active_text(self.state)})

    def test_non_owner_and_stop_set(self):
        self.accepted()
        self.write_state(owner="sess-other")
        self.assert_stop(self.codex(codex_event(self.root)))
        self.write_state(stop="paused")
        self.assert_stop(self.codex(codex_event(self.root)))

    def test_wrong_event_name(self):
        self.accepted()
        for name in ("stop", "SubagentStop", "SessionEnd", None):
            with self.subTest(name=name):
                self.write_state()
                self.assert_stop(self.codex(codex_event(self.root, hook_event_name=name)))

    def test_agent_id_key_rejects_even_when_null(self):
        self.accepted()
        for value in ("agent-1", None):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.codex(codex_event(self.root, agent_id=value)))

    def test_stop_hook_active_must_be_bool(self):
        self.accepted()
        for value in ("true", 1, None):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.codex(codex_event(self.root, stop_hook_active=value)))

    def test_no_progress_across_automatic_turns(self):
        self.write_state()
        self.message(self.codex(codex_event(self.root)), "reason", "block")
        text = self.message(self.codex(codex_event(self.root, continued=True)), "reason", "block")
        self.assertIn(NO_PROGRESS, text)
        self.assert_stop(self.codex(codex_event(self.root, continued=True)))

    def test_roots_are_cwd_only_and_no_waiter_signal(self):
        self.accepted()
        self.write_state()
        out = self.codex(codex_event(self.elsewhere), env=host_env(CLAUDE_PROJECT_DIR=self.root))
        self.assert_stop(out)
        self.write_state(items=WAITING)
        self.assert_stop(self.codex(codex_event(self.root, background_tasks=[])))


class CursorTest(HostBase):
    CONTINUE_KEY = ("followup_message",)

    def cursor(self, ev, env=None):
        return self.run_host("cursor", ev, env=env)

    def control_output(self):
        return self.cursor(cursor_event(self.root))

    def test_continue_exact_output(self):
        self.write_state()
        self.assertEqual(self.cursor(cursor_event(self.root)),
                         {"followup_message": active_text(self.state)})

    def test_non_owner_and_stop_set(self):
        self.accepted()
        self.write_state(owner="sess-other")
        self.assert_stop(self.cursor(cursor_event(self.root)))
        self.write_state(stop="done")
        self.assert_stop(self.cursor(cursor_event(self.root)))

    def test_wrong_event_name(self):
        self.accepted()
        for name in ("Stop", "afterAgentResponse", "sessionEnd", None):
            with self.subTest(name=name):
                self.write_state()
                self.assert_stop(self.cursor(cursor_event(self.root, hook_event_name=name)))

    def test_subagent_stop_rejected(self):
        self.accepted()
        self.write_state()
        self.assert_stop(self.cursor(cursor_event(self.root, hook_event_name="subagentStop",
                                                  subagent_id="sub-1")))

    def test_non_completed_status(self):
        self.accepted()
        for status in ("aborted", "error", None):
            with self.subTest(status=status):
                self.write_state()
                self.assert_stop(self.cursor(cursor_event(self.root, status=status)))

    def test_bad_loop_count(self):
        self.accepted()
        for value in (-1, True, False, "0", 1.0, None):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.cursor(cursor_event(self.root, loop_count=value)))
        self.write_state()
        ev = cursor_event(self.root)
        del ev["loop_count"]
        self.assert_stop(self.cursor(ev))

    def test_conversation_id_required(self):
        self.accepted()
        for value in ("", None, 7):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.cursor(cursor_event(self.root, conversation_id=value)))

    def test_positive_loop_count_is_automatic_turn(self):
        self.write_state()
        self.cursor(cursor_event(self.root))
        text = self.message(self.cursor(cursor_event(self.root, loop_count=1)),
                            "followup_message")
        self.assertIn(NO_PROGRESS, text)
        self.assert_stop(self.cursor(cursor_event(self.root, loop_count=2)))
        self.assertNotIn(NO_PROGRESS, self.message(
            self.cursor(cursor_event(self.root, loop_count=0)), "followup_message"))

    def test_workspace_roots_then_project_dir(self):
        self.write_state()
        ev = cursor_event(self.root, workspace_roots=[7, self.elsewhere, os.path.join(self.root, "x")])
        os.mkdir(os.path.join(self.root, "x"))
        self.message(self.cursor(ev), "followup_message")
        self.write_state()
        ev = cursor_event(self.root, workspace_roots=[self.elsewhere])
        self.assert_stop(self.cursor(ev))
        self.message(self.cursor(ev, env=host_env(CURSOR_PROJECT_DIR=self.root)),
                     "followup_message")

    def test_two_valid_roots_choose_first(self):
        self.write_state()
        self.write_rival_state()
        ev = cursor_event(self.root, workspace_roots=[self.root, self.elsewhere])
        self.assertEqual(self.cursor(ev), {"followup_message": active_text(self.state)})
        self.write_state()
        ev = cursor_event(self.root, workspace_roots=[self.root])
        self.assertEqual(self.cursor(ev, env=host_env(CURSOR_PROJECT_DIR=self.elsewhere)),
                         {"followup_message": active_text(self.state)})

    def test_no_waiter_signal(self):
        self.accepted()
        self.write_state(items=WAITING)
        self.assert_stop(self.cursor(cursor_event(self.root, background_tasks=[])))


class AntigravityTest(HostBase):
    CONTINUE_KEY = ("reason", "continue")

    def assert_stop(self, out):
        self.assertEqual(out, {"decision": "stop"})

    def agy(self, ev):
        return self.run_host("antigravity", ev)

    def control_output(self):
        return self.agy(antigravity_event(self.root))

    def test_continue_exact_output_sets_pending(self):
        self.write_state()
        self.assertEqual(self.agy(antigravity_event(self.root)),
                         {"decision": "continue", "reason": active_text(self.state)})
        data = self.sidecar_data()
        self.assertEqual(sorted(data), ["goal", "key", "pending", "strikes", "turns"])
        self.assertEqual((data["turns"], data["pending"]), (1, OWNER))

    def test_non_owner_and_stop_set(self):
        self.accepted()
        self.write_state(owner="sess-other")
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.write_state(stop="paused")
        self.assert_stop(self.agy(antigravity_event(self.root)))

    def test_event_name_absent_or_stop(self):
        for key in ("hook_event_name", "hookEventName"):
            for name, accepted in (("Stop", True), ("stop", False), ("SubagentStop", False),
                                   (None, False)):
                with self.subTest(key=key, name=name):
                    self.write_state()
                    out = self.agy(antigravity_event(self.root, **{key: name}))
                    if accepted:
                        self.message(out, "reason", "continue")
                    else:
                        self.assert_stop(out)

    def test_error_set(self):
        for value in ("model error", None, 0):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.agy(antigravity_event(self.root, error=value)))
        self.write_state()
        ev = antigravity_event(self.root)
        del ev["error"]
        self.message(self.agy(ev), "reason", "continue")

    def test_conversation_id_required(self):
        self.accepted()
        for value in ("", None, 7):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.agy(antigravity_event(self.root, conversationId=value)))

    def test_pending_round_trip_and_no_progress(self):
        self.write_state()
        first = self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertNotIn(NO_PROGRESS, first)
        second = self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertIn(NO_PROGRESS, second)
        self.assertEqual((self.sidecar_data()["strikes"], self.sidecar_data()["pending"]),
                         (1, OWNER))
        self.assert_stop(self.agy(antigravity_event(self.root)))
        data = self.sidecar_data()
        self.assertEqual((data["turns"], data["strikes"], data["pending"]), (2, 2, None))
        third = self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertNotIn(NO_PROGRESS, third)
        self.assertEqual(self.sidecar_data()["strikes"], 0)

    def test_pending_for_another_session_is_not_automatic(self):
        self.write_state()
        self.agy(antigravity_event(self.root))
        data = self.sidecar_data()
        data["pending"] = "sess-other"
        self.write_sidecar(json.dumps(data))
        self.assertNotIn(NO_PROGRESS, self.message(self.agy(antigravity_event(self.root)),
                                                   "reason", "continue"))

    def test_budget_exhaustion_clears_pending(self):
        self.write_state(budget=1)
        self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertEqual(self.sidecar_data()["pending"], OWNER)
        self.log(1)
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.assertIsNone(self.sidecar_data()["pending"])

    def test_sidecar_without_pending_is_valid(self):
        self.write_state()
        self.write_sidecar(json.dumps({"goal": None, "turns": 0, "key": None, "strikes": 0}))
        self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertEqual(self.sidecar_data()["pending"], OWNER)

    def test_corrupt_pending(self):
        self.accepted()
        for pending in (5, True, ["sess-owner"], {"id": OWNER}):
            content = json.dumps({"goal": None, "turns": 0, "key": None, "strikes": 0,
                                  "pending": pending})
            with self.subTest(pending=pending):
                self.write_state()
                self.write_sidecar(content)
                self.assert_stop(self.agy(antigravity_event(self.root)))
                with open(self.sidecar, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), content)

    def test_other_hosts_ignore_pending(self):
        content = json.dumps({"goal": None, "turns": 0, "key": None, "strikes": 0,
                              "pending": 5})
        self.write_state()
        self.write_sidecar(content)
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.assert_block(self.hook(event(self.root)), "turn 1/50")
        self.write_state()
        self.write_sidecar(json.dumps({"goal": None, "turns": 0, "key": None, "strikes": 0,
                                       "pending": OWNER}))
        self.assertNotIn(NO_PROGRESS, self.reason(self.run_host(
            "codex", codex_event(self.root))))
        self.assertNotIn("pending", self.sidecar_data())

    def test_fully_idle_waiter_branch(self):
        self.write_state(items="\n".join([WAITING, USER]))
        self.assert_stop(self.agy(antigravity_event(self.root, fullyIdle=False)))
        self.assertFalse(os.path.exists(self.sidecar))
        ev = antigravity_event(self.root)
        del ev["fullyIdle"]
        self.assert_stop(self.agy(ev))
        self.assert_stop(self.agy(antigravity_event(self.root, fullyIdle="true")))
        text = self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertIn("1 waiting item(s) but no background task is running", text)
        self.assertEqual(self.sidecar_data()["pending"], OWNER)
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.assertIsNone(self.sidecar_data()["pending"])

    def test_workspace_paths_in_order(self):
        self.write_state()
        ev = antigravity_event(self.root, workspacePaths=[None, self.elsewhere, self.root])
        self.message(self.agy(ev), "reason", "continue")
        self.write_state()
        self.assert_stop(self.agy(antigravity_event(self.root, workspacePaths=self.root)))

    def test_two_valid_roots_choose_first(self):
        self.write_state()
        self.write_rival_state()
        ev = antigravity_event(self.root, workspacePaths=[self.root, self.elsewhere])
        self.assertEqual(self.agy(ev), {
            "decision": "continue", "reason": active_text(self.state)})

    def unchanged_automatic_turn(self):
        """Grant a continuation, then an unchanged automatic stop: strikes 1, pending set."""
        self.write_state()
        self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertIn(NO_PROGRESS, self.message(self.agy(antigravity_event(self.root)),
                                                "reason", "continue"))
        data = self.sidecar_data()
        self.assertEqual((data["strikes"], data["pending"]), (1, OWNER))

    def assert_human_turn_continues(self):
        """The next stop is a human turn: it continues with strikes reset to 0."""
        text = self.message(self.agy(antigravity_event(self.root)), "reason", "continue")
        self.assertNotIn(NO_PROGRESS, text)
        data = self.sidecar_data()
        self.assertEqual((data["strikes"], data["pending"]), (0, OWNER))

    def test_error_stop_clears_pending_before_human_turn(self):
        self.unchanged_automatic_turn()
        self.assert_stop(self.agy(antigravity_event(self.root, error="model error")))
        data = self.sidecar_data()
        self.assertEqual((data["strikes"], data["pending"]), (1, None))
        self.assert_human_turn_continues()

    def test_pause_and_resume_clears_pending(self):
        self.unchanged_automatic_turn()
        self.write_state(stop="paused", keep_sidecar=True)
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.assertIsNone(self.sidecar_data()["pending"])
        self.write_state(keep_sidecar=True)
        self.assert_human_turn_continues()

    def test_owned_rejection_never_creates_sidecar(self):
        self.write_state()
        self.assert_stop(self.agy(antigravity_event(self.root, error="model error")))
        self.write_state(stop="paused")
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.write_state(items=USER)
        self.assert_stop(self.agy(antigravity_event(self.root)))
        self.assertFalse(os.path.exists(self.sidecar))

    def test_cleanup_leaves_other_sessions_and_events_alone(self):
        content = json.dumps({"goal": None, "turns": 1, "key": None, "strikes": 0,
                              "pending": "sess-other"})
        for name, kwargs in (("error", {"error": "model error"}), ("idle", {})):
            with self.subTest(name=name):
                self.write_state(items=USER if name == "idle" else READY)
                self.write_sidecar(content)
                self.assert_stop(self.agy(antigravity_event(self.root, **kwargs)))
                with open(self.sidecar, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), content)
        content = json.dumps({"goal": None, "turns": 1, "key": None, "strikes": 0,
                              "pending": OWNER})
        for name, owner, kwargs in (
                ("non-owner", "sess-other", {}),
                ("other event", OWNER, {"hook_event_name": "SubagentStop"}),
                ("no conversation", OWNER, {"conversationId": "", "error": "model error"})):
            with self.subTest(name=name):
                self.write_state(owner=owner)
                self.write_sidecar(content)
                self.assert_stop(self.agy(antigravity_event(self.root, **kwargs)))
                with open(self.sidecar, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), content)


class DevinTest(HostBase):
    CONTINUE_KEY = ("reason", "block")

    def devin(self, ev, env=None, cwd=None):
        return self.run_host("devin", ev, env=env, cwd=cwd)

    def project_env(self):
        return host_env(DEVIN_PROJECT_DIR=self.root)

    def control_output(self):
        return self.devin(devin_event(), env=self.project_env())

    def test_continue_exact_output(self):
        self.write_state()
        self.assertEqual(self.devin(devin_event(), env=self.project_env()),
                         {"decision": "block", "reason": active_text(self.state)})

    def test_non_owner_and_stop_set(self):
        self.accepted()
        self.write_state(owner="sess-other")
        self.assert_stop(self.devin(devin_event(), env=self.project_env()))
        self.write_state(stop="done")
        self.assert_stop(self.devin(devin_event(), env=self.project_env()))

    def test_wrong_event_name(self):
        self.accepted()
        for name in ("stop", "SubagentStop", "SessionEnd", None):
            with self.subTest(name=name):
                self.write_state()
                self.assert_stop(self.devin(devin_event(hook_event_name=name),
                                            env=self.project_env()))

    def test_agent_id_key_rejects_even_when_null(self):
        self.accepted()
        for value in ("agent-1", None):
            with self.subTest(value=value):
                self.write_state()
                self.assert_stop(self.devin(devin_event(agent_id=value), env=self.project_env()))

    def test_roots_fall_back_from_env_to_process_cwd(self):
        sub = os.path.join(self.root, "src")
        os.mkdir(sub)
        self.write_state()
        out = self.devin(devin_event(), env=host_env(DEVIN_PROJECT_DIR=self.elsewhere,
                                                     CLAUDE_PROJECT_DIR=self.root))
        self.message(out, "reason", "block")
        self.write_state()
        self.message(self.devin(devin_event(), cwd=sub), "reason", "block")
        self.write_state()
        self.assert_stop(self.devin(devin_event(cwd=self.root)))

    def test_two_valid_roots_choose_first(self):
        self.write_state()
        self.write_rival_state()
        expected = {"decision": "block", "reason": active_text(self.state)}
        self.assertEqual(self.devin(devin_event(), env=host_env(
            DEVIN_PROJECT_DIR=self.root, CLAUDE_PROJECT_DIR=self.elsewhere)), expected)
        self.write_state()
        self.assertEqual(self.devin(devin_event(), env=host_env(
            CLAUDE_PROJECT_DIR=self.root)), expected)

    def test_session_start_output(self):
        expected = {"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[agent-loop] This session's ID is %s. Use it as the "
                                 "owner: value when you create or take over an agent-loop "
                                 "state file." % OWNER}}
        ev = {"hook_event_name": "SessionStart", "session_id": OWNER, "source": "startup"}
        self.assertEqual(self.devin(ev), expected)
        self.write_state(owner="sess-other", stop="done")
        self.assertEqual(self.devin(ev, env=self.project_env()), expected)
        for value in ("", None, 7):
            with self.subTest(value=value):
                self.assert_stop(self.devin(dict(ev, session_id=value)))

    def test_other_hosts_ignore_session_start(self):
        ev = {"hook_event_name": "SessionStart", "session_id": OWNER, "cwd": self.root}
        self.write_state()
        self.assertIn("hookSpecificOutput", self.devin(ev))
        for host in ("claude", "codex", "cursor", "antigravity"):
            with self.subTest(host=host):
                expected = {"decision": "stop"} if host == "antigravity" else {}
                self.assertEqual(self.run_host(host, ev), expected)


if __name__ == "__main__":
    unittest.main()
