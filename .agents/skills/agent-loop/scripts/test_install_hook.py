#!/usr/bin/env python3
"""Fixture tests for install_hook.py.

Each case runs the installer as a subprocess with a temporary HOME, CODEX_HOME
and workspace, so no real configuration is read or written. Run from anywhere;
the scripts are located relative to this file.
"""
import copy
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.join(SCRIPTS, "install_hook.py")
HOOK = os.path.realpath(os.path.join(SCRIPTS, "loop_hook.py"))
HOSTS = ("codex", "cursor", "antigravity", "devin")
SCOPES = ("user", "project")
CASES = [(host, scope) for host in HOSTS for scope in SCOPES]
STRIP_ENV = ("CODEX_HOME", "CLAUDE_PROJECT_DIR", "CURSOR_PROJECT_DIR", "DEVIN_PROJECT_DIR",
             "CLAUDE_PLUGIN_ROOT", "CLAUDE_SKILL_DIR")
OTHER = {"type": "command", "command": "echo other", "timeout": 5}
WRITTEN = "Removed the agent-loop hook from %s and wrote the file.\n"
DELETED = "Removed the agent-loop hook from %s and deleted the file, which held nothing else.\n"
NOTHING = "No agent-loop hook for %s found in %s; nothing changed.\n"
ACTIVATION = {
    "codex": "Approve the hook in Codex with /hooks (select it, press t); project hooks "
             "also need a trusted project.",
    "cursor": "Cursor runs stop hooks in its interactive CLI; print mode (agent -p) is not "
              "established to run them. The workspace must be trusted.",
    "antigravity": "If the CLI asks whether to trust the workspace, choose \"Yes, I trust this folder\".",
    "devin": "The workspace must be trusted; the SessionStart hook tells each new session "
             "its ID.",
}


def command(host, hook=HOOK):
    return "python3 %s --host %s" % (shlex.quote(hook), host)


def ours(host, hook=HOOK):
    entry = {"type": "command", "command": command(host, hook), "timeout": 30}
    if host == "cursor":
        entry["loop_limit"] = None
    return entry


def old_entry(host):
    """A stale entry of ours: another install path and a different timeout."""
    return {"type": "command", "timeout": 5,
            "command": "python3 /old/agent-loop/scripts/loop_hook.py --host %s" % host}


def shape(host, scope, handlers):
    """The host's configuration with handlers in our single event list or group."""
    if host == "codex":
        return {"hooks": {"Stop": [{"hooks": handlers}]}}
    if host == "cursor":
        return {"version": 1, "hooks": {"stop": handlers}}
    if host == "antigravity":
        return {"agent-loop": {"Stop": handlers}}
    events = {"Stop": [{"matcher": "", "hooks": handlers}],
              "SessionStart": [{"matcher": "", "hooks": copy.deepcopy(handlers)}]}
    return {"hooks": events} if scope == "user" else events


def render(data):
    return json.dumps(data, indent=2) + "\n"


def stop_event(host, workspace):
    """A minimal turn-end event the host's adapter accepts."""
    if host == "cursor":
        return {"hook_event_name": "stop", "conversation_id": "s1", "status": "completed",
                "loop_count": 0, "workspace_roots": [workspace]}
    if host == "antigravity":
        return {"conversationId": "s1", "workspacePaths": [workspace]}
    return {"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False,
            "cwd": workspace}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = os.path.realpath(self._tmp.name)
        self.home = os.path.join(base, "home")
        self.codex_home = os.path.join(base, "codex-home")
        self.workspace = os.path.join(base, "work")
        os.makedirs(self.home)
        os.makedirs(self.workspace)

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, codex_home=True):
        env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
        env["HOME"] = self.home
        # Keep git discovery inside this test's directory even when TMPDIR is in a checkout.
        env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(self.workspace)
        if codex_home:
            env["CODEX_HOME"] = self.codex_home
        return env

    def run_installer(self, *args, env=None, cwd=None, installer=INSTALLER):
        return subprocess.run([sys.executable, installer] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, env=env or self.env(),
                              cwd=cwd or self.workspace, timeout=30)

    def install(self, host, scope, *extra):
        proc = self.run_installer("--host", host, "--scope", scope,
                                  "--workspace", self.workspace, *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        return proc

    def path(self, host, scope):
        if scope == "project":
            return os.path.join(self.workspace, {
                "codex": ".codex/hooks.json", "cursor": ".cursor/hooks.json",
                "antigravity": ".agents/hooks.json", "devin": ".devin/hooks.v1.json"}[host])
        return {"codex": os.path.join(self.codex_home, "hooks.json"),
                "cursor": os.path.join(self.home, ".cursor", "hooks.json"),
                "antigravity": os.path.join(self.home, ".gemini", "config", "hooks.json"),
                "devin": os.path.join(self.home, ".config", "devin", "config.json")}[host]

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()


class InstallTest(Base):
    def test_creates_file_with_exact_shape(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                proc = self.install(host, scope)
                path = self.path(host, scope)
                self.assertEqual(self.read(path), render(shape(host, scope, [ours(host)])))
                self.assertEqual(proc.stdout, "Wrote %s\n%s\n" % (path, ACTIVATION[host]))

    def test_preserves_other_keys_and_entries(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                original = shape(host, scope, [OTHER])
                if host == "antigravity":
                    original["lint"] = {"PreToolUse": [OTHER]}
                    original["agent-loop"]["SessionStart"] = [OTHER]
                else:
                    events = original if host == "devin" and scope == "project" else original["hooks"]
                    events["PreToolUse"] = [{"matcher": "Bash", "hooks": [OTHER]}]
                    if not (host == "devin" and scope == "project"):
                        original["model"] = "example"
                path = self.path(host, scope)
                self.write(path, json.dumps(original))
                self.install(host, scope)
                expected = copy.deepcopy(original)
                if host in ("cursor", "antigravity"):
                    key = "stop" if host == "cursor" else "Stop"
                    group = expected["hooks"] if host == "cursor" else expected["agent-loop"]
                    group[key].append(ours(host))
                else:
                    events = expected if host == "devin" and scope == "project" else expected["hooks"]
                    names = ("Stop",) if host == "codex" else ("Stop", "SessionStart")
                    for name in names:
                        group = {"hooks": [ours(host)]} if host == "codex" else \
                            {"matcher": "", "hooks": [ours(host)]}
                        events[name].append(group)
                self.assertEqual(json.loads(self.read(path)), expected)
                self.assertEqual(list(json.loads(self.read(path))), list(expected))

    def test_replaces_stale_entry_in_place_and_is_idempotent(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                foreign = "python3 /x/loop_hook.py --host %s" % (
                    "cursor" if host != "cursor" else "codex")
                other_host = {"type": "command", "command": foreign}
                path = self.path(host, scope)
                self.write(path, json.dumps(
                    shape(host, scope, [OTHER, old_entry(host), other_host, old_entry(host)])))
                self.install(host, scope)
                first = self.read(path)
                self.assertEqual(first, render(shape(host, scope, [OTHER, ours(host), other_host])))
                self.install(host, scope)
                self.assertEqual(self.read(path), first)

    def test_second_run_on_fresh_file_is_byte_identical(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                self.install(host, scope)
                first = self.read(self.path(host, scope))
                self.install(host, scope)
                self.assertEqual(self.read(self.path(host, scope)), first)

    def test_keeps_permission_bits(self):
        path = self.path("cursor", "project")
        self.write(path, "{}")
        os.chmod(path, 0o640)
        self.install("cursor", "project")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o640)
        self.assertEqual(sorted(os.listdir(os.path.dirname(path))), ["hooks.json"])


class UninstallTest(Base):
    def test_removes_only_our_entries(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                foreign = {"type": "command",
                           "command": "python3 /x/loop_hook.py --host %s" % (
                               "cursor" if host != "cursor" else "codex")}
                path = self.path(host, scope)
                self.write(path, json.dumps(shape(host, scope, [OTHER, old_entry(host), foreign])))
                self.install(host, scope, "--uninstall")
                self.assertEqual(json.loads(self.read(path)), shape(host, scope, [OTHER, foreign]))

    def test_install_then_uninstall_on_missing_file(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                path = self.path(host, scope)
                self.install(host, scope)
                proc = self.install(host, scope, "--uninstall")
                if host == "cursor":
                    self.assertEqual(proc.stdout, WRITTEN % path)
                    self.assertEqual(self.read(path), render({"version": 1}))
                else:
                    self.assertEqual(proc.stdout, DELETED % path)
                    self.assertFalse(os.path.exists(path))

    def test_restores_unrelated_keys_and_drops_created_containers(self):
        unrelated = {"codex": {"model": "example"},
                     "cursor": {"version": 1, "model": "example"},
                     "antigravity": {"lint": {"PreToolUse": [OTHER]}}}
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                if host == "devin":
                    original = {"model": "example"} if scope == "user" else \
                        {"PreToolUse": [{"matcher": "Bash", "hooks": [OTHER]}]}
                else:
                    original = unrelated[host]
                path = self.path(host, scope)
                self.write(path, render(original))
                self.install(host, scope)
                proc = self.install(host, scope, "--uninstall")
                self.assertEqual(proc.stdout, WRITTEN % path)
                self.assertEqual(self.read(path), render(original))

    def test_keeps_existing_hooks_object_with_other_events(self):
        for host, scope in CASES:
            if host == "antigravity" or (host == "devin" and scope == "project"):
                continue
            with self.subTest(host=host, scope=scope):
                handlers = [OTHER] if host == "cursor" else [{"matcher": "Bash", "hooks": [OTHER]}]
                original = {"hooks": {"PreToolUse": handlers}}
                if host == "cursor":
                    original = {"version": 1, "hooks": {"preToolUse": handlers}}
                path = self.path(host, scope)
                self.write(path, render(original))
                self.install(host, scope)
                self.install(host, scope, "--uninstall")
                self.assertEqual(self.read(path), render(original))

    def test_cursor_version_keeps_file(self):
        for version in (1, 2, "1", 1.0, True):
            for scope in SCOPES:
                with self.subTest(version=version, scope=scope):
                    path = self.path("cursor", scope)
                    self.write(path, render({"version": version}))
                    self.install("cursor", scope)
                    proc = self.install("cursor", scope, "--uninstall")
                    self.assertEqual(proc.stdout, WRITTEN % path)
                    self.assertEqual(self.read(path), render({"version": version}))

    def test_no_match_reports_and_leaves_file_byte_identical(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                edited = dict(ours(host), command="python3 /x/loop_hook.py --host %s-edited" % host)
                path = self.path(host, scope)
                text = json.dumps(shape(host, scope, [OTHER, edited]))
                self.write(path, text)
                proc = self.install(host, scope, "--uninstall")
                self.assertEqual(proc.stdout, NOTHING % (host, path))
                self.assertEqual(self.read(path), text)

    def test_unrelated_file_left_byte_identical(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                path = self.path(host, scope)
                text = '{"keep":   [1, 2],\n "hooks": {"Stop": []}}'
                if host == "antigravity" or (host == "devin" and scope == "project"):
                    text = '{"keep":   [1, 2],\n "Stop": []}'
                self.write(path, text)
                self.install(host, scope, "--uninstall")
                self.assertEqual(self.read(path), text)

    def test_missing_file_is_not_created(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                proc = self.install(host, scope, "--uninstall")
                self.assertEqual(proc.stdout, NOTHING % (host, self.path(host, scope)))
                self.assertFalse(os.path.exists(self.path(host, scope)))


class RefuseTest(Base):
    def test_refuses_jsonc_and_non_objects(self):
        for host, scope in CASES:
            for text in ('// hooks\n{"hooks": {}}\n', '{"hooks": {} /* c */}', "[]", '"x"', ""):
                with self.subTest(host=host, scope=scope, text=text):
                    path = self.path(host, scope)
                    self.write(path, text)
                    for extra in ([], ["--uninstall"], ["--dry-run"]):
                        proc = self.run_installer("--host", host, "--scope", scope,
                                                  "--workspace", self.workspace, *extra)
                        self.assertEqual(proc.returncode, 1, proc.stdout)
                        self.assertIn(path, proc.stderr)
                        self.assertEqual(proc.stdout, "")
                        self.assertEqual(self.read(path), text)

    def test_refuses_wrong_nested_types(self):
        cases = [("codex", '{"hooks": []}'), ("codex", '{"hooks": {"Stop": {}}}'),
                 ("cursor", '{"hooks": {"stop": {}}}'), ("antigravity", '{"agent-loop": []}'),
                 ("devin", '{"hooks": {"SessionStart": "x"}}')]
        for host, text in cases:
            with self.subTest(host=host, text=text):
                path = self.path(host, "user")
                self.write(path, text)
                proc = self.run_installer("--host", host, "--scope", "user")
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(self.read(path), text)

    def test_claude_refused(self):
        for scope in SCOPES:
            with self.subTest(scope=scope):
                proc = self.run_installer("--host", "claude", "--scope", scope,
                                          "--workspace", self.workspace)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("frontmatter", proc.stderr)
                self.assertEqual(os.listdir(self.home), [])
                self.assertEqual(os.listdir(self.workspace), [])

    def test_usage_errors(self):
        self.install("codex", "project", "--dry-run")
        for args in ([], ["--host", "codex"], ["--scope", "user"],
                     ["--host", "gemini", "--scope", "user"],
                     ["--host", "codex", "--scope", "global"],
                     ["--host", "codex", "--scope", "project", "--workspace",
                      os.path.join(self.workspace, "missing")]):
            with self.subTest(args=args):
                self.assertEqual(self.run_installer(*args).returncode, 2)
        self.assertEqual(os.listdir(self.workspace), [])


class DryRunTest(Base):
    def test_dry_run_writes_nothing(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                path = self.path(host, scope)
                proc = self.install(host, scope, "--dry-run")
                self.assertEqual(proc.stdout, "path: %s\n%s" % (
                    path, render(shape(host, scope, [ours(host)]))))
                self.assertFalse(os.path.exists(path))
                self.assertFalse(os.path.exists(os.path.dirname(path)))

    def test_dry_run_on_existing_file(self):
        path = self.path("codex", "user")
        text = '{"hooks": {"Stop": [{"hooks": [%s]}]}}' % json.dumps(old_entry("codex"))
        self.write(path, text)
        proc = self.install("codex", "user", "--dry-run")
        self.assertEqual(proc.stdout, "path: %s\n%s" % (
            path, render(shape("codex", "user", [ours("codex")]))))
        proc = self.install("codex", "user", "--dry-run", "--uninstall")
        self.assertEqual(proc.stdout, "path: %s\ndelete\n" % path)
        self.assertEqual(self.read(path), text)

    def test_dry_run_uninstall_deletion_and_rewrite(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                path = self.path(host, scope)
                self.install(host, scope)
                text = self.read(path)
                proc = self.install(host, scope, "--dry-run", "--uninstall")
                result = render({"version": 1}) if host == "cursor" else "delete\n"
                self.assertEqual(proc.stdout, "path: %s\n%s" % (path, result))
                self.assertEqual(self.read(path), text)
                kept = shape(host, scope, [OTHER, ours(host)])
                self.write(path, json.dumps(kept))
                proc = self.install(host, scope, "--dry-run", "--uninstall")
                self.assertEqual(proc.stdout, "path: %s\n%s" % (
                    path, render(shape(host, scope, [OTHER]))))
                self.assertEqual(self.read(path), json.dumps(kept))


class LocationTest(Base):
    def test_codex_home_defaults_to_home(self):
        proc = self.run_installer("--host", "codex", "--scope", "user",
                                  env=self.env(codex_home=False))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = os.path.join(self.home, ".codex", "hooks.json")
        self.assertEqual(self.read(path), render(shape("codex", "user", [ours("codex")])))

    @unittest.skipIf(shutil.which("git") is None, "git is not installed")
    def test_workspace_defaults_to_git_top_level_else_cwd(self):
        sub = os.path.join(self.workspace, "src", "pkg")
        os.makedirs(sub)
        proc = self.run_installer("--host", "cursor", "--scope", "project", cwd=sub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(sub, ".cursor", "hooks.json")))
        subprocess.run(["git", "init", "-q", self.workspace], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc = self.run_installer("--host", "devin", "--scope", "project", cwd=sub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.workspace, ".devin", "hooks.v1.json")))


class CommandTest(Base):
    def run_command(self, host, cmd):
        proc = subprocess.run(["sh", "-c", cmd], input=json.dumps(stop_event(host, self.workspace)),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, env=self.env(), cwd=self.workspace,
                              timeout=20)
        neutral = '{"decision": "stop"}\n' if host == "antigravity" else "{}\n"
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, neutral, ""))

    def test_command_is_absolute_and_runs(self):
        for host, scope in CASES:
            with self.subTest(host=host, scope=scope):
                self.install(host, scope)
                data = json.loads(self.read(self.path(host, scope)))
                expected = shape(host, scope, [ours(host)])
                self.assertEqual(data, expected)
                cmd = ours(host)["command"]
                self.assertTrue(os.path.isabs(shlex.split(cmd)[1]))
                self.assertEqual(shlex.split(cmd)[1], HOOK)
                self.run_command(host, cmd)

    def test_path_with_spaces_is_quoted(self):
        target = os.path.join(self.home, "skill dir's", "scripts")
        os.makedirs(target)
        for name in ("install_hook.py", "loop_hook.py"):
            shutil.copy(os.path.join(SCRIPTS, name), target)
        proc = self.run_installer("--host", "codex", "--scope", "user",
                                  installer=os.path.join(target, "install_hook.py"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(self.read(self.path("codex", "user")))
        cmd = data["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertEqual(cmd, command("codex", os.path.join(target, "loop_hook.py")))
        self.run_command("codex", cmd)


if __name__ == "__main__":
    unittest.main()
