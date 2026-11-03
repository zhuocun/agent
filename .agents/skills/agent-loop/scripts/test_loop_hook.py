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
WAITING = "- [waiting] T3 CI run — wake: CI finishes; check: ci status"
USER = "- [user] T4 Push — ask: push to main?; asked: 2026-11-01"
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
    "stop. Begin your final message with the loop status line."
)
NO_PROGRESS = "The queue did not change during the last automatic turn"
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

    def test_after_blocks_ready_item_while_dependency_open(self):
        items = "\n".join([WAITING, "- [ready] T5 Deploy — done when: live; after: T3"])
        self.write_state(items=items)
        running = event(self.root, background_tasks=[{"id": "b1"}])
        self.assert_stop(self.hook(running))
        self.write_state(items="- [ready] T5 Deploy — done when: live; after: T3")
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
                "background task is running. For each waiting item that needs an "
                "external event, run its check; if the event has not happened, start "
                "its waiter as a background command. If an item waits for nothing "
                "external, change its status. Then end your turn." % self.state)
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
        for args in (["--host", "claude"], ["--max-streak", "3"], ["--state"], ["extra"]):
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


if __name__ == "__main__":
    unittest.main()
