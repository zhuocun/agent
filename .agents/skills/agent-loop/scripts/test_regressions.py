#!/usr/bin/env python3
"""Corrected-contract regressions; Python 3.8+, standard library only.

Run with unittest discovery. All subprocesses and mutations use disposable
workspaces; filesystem faults are injected without changing host configuration.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

import test_install_hook as installer_tests
import test_loop_hook as hook_tests


def module(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(__file__), filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


installer = module("installer_under_test", "install_hook.py")
hook = module("hook_under_test", "loop_hook.py")


class DependencyTest(hook_tests.Base):
    def test_unknown_and_open_dependencies_block_ready_and_doing(self):
        for status in ("ready", "doing"):
            for dependency in ("NEVER", "T3"):
                with self.subTest(status=status, dependency=dependency):
                    item = ("- [%s] T1 Deploy — done when: live; next: verify; after: %s"
                            % (status, dependency))
                    self.write_state(items=item + "\n" + hook_tests.WAITING)
                    ev = hook_tests.event(self.root, background_tasks=[{"id": "waiter"}])
                    self.assert_stop(self.hook(ev))
                    self.assertFalse(os.path.exists(self.sidecar))

    def test_closed_dependency_is_met_without_editing_the_dependant(self):
        for status in ("ready", "doing"):
            with self.subTest(status=status):
                item = "- [%s] T1 Deploy — done when: live; next: verify; after: T0" % status
                self.write_state(items=item)
                with open(self.state, "a", encoding="utf-8") as handle:
                    handle.write("- 2026-11-01T10:00Z T0 closed — required CI passes\n")
                with open(self.state, encoding="utf-8") as handle:
                    before = handle.read()
                self.assert_block(self.hook(hook_tests.event(self.root)), "now T1",
                                  "1 actionable")
                with open(self.state, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), before)
                reconciled = before.replace("; after: T0", "")
                self.write_state(text=reconciled)
                self.assert_block(self.hook(hook_tests.event(self.root)), "now T1")
                with open(self.state, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), reconciled)

    def test_blocked_doing_does_not_preempt_dependency_free_ready(self):
        self.write_state(items=hook_tests.DOING + "; after: NEVER\n"
                         "- [ready] T2 Docs — done when: published")
        self.assert_block(self.hook(hook_tests.event(self.root)), "now T2", "1 actionable")


class AdapterRepairTest(hook_tests.HostBase):
    def test_only_explicit_no_background_signal_repairs_with_scoped_guidance(self):
        events = {
            "claude": hook_tests.event(self.root),
            "codex": hook_tests.codex_event(self.root),
            "cursor": hook_tests.cursor_event(self.root),
            "antigravity": hook_tests.antigravity_event(self.root),
            "devin": hook_tests.devin_event(),
        }
        for host, ev in events.items():
            with self.subTest(host=host):
                self.write_state(items=hook_tests.WAITING)
                out = self.run_host(host, ev, args=("--state", self.state))
                if host in ("claude", "antigravity"):
                    self.assertEqual(out["decision"], "continue" if host == "antigravity"
                                     else "block")
                    for text in ("pass 5's Waiter rule", "host and mode", "blocking collection",
                                 "within its lifetime", "Complete required coverage",
                                 "Do not start an unsupported waiter or scheduled queue execution"):
                        self.assertIn(text, out["reason"])
                    self.assertNotIn("Then end your turn", out["reason"])
                else:
                    self.assertEqual(out, {})
                    self.assertFalse(os.path.exists(self.sidecar))

    def test_continuation_obeys_applicable_message_form(self):
        self.write_state()
        text = self.reason(self.hook(hook_tests.event(self.root)))
        self.assertIn("pass 7's applicable form rule", text)
        self.assertNotIn("Begin your final message", text)


class FingerprintTest(hook_tests.Base):
    def test_key_is_ordered_id_status_and_log_count(self):
        self.write_state(items=hook_tests.DOING)
        self.log(1)
        self.hook(hook_tests.event(self.root))
        expected = hashlib.sha256(json.dumps(
            [[["T1", "doing"]], 1]).encode("utf-8")).hexdigest()
        self.assertEqual(self.sidecar_data()["key"], expected)

    def test_criterion_dependency_and_same_count_evidence_edits_are_not_progress(self):
        for change in ("criterion", "dependency", "log evidence"):
            with self.subTest(change=change):
                self.write_state(items=hook_tests.DOING + "\n" +
                                 "- [ready] T2 Later — done when: live; after: NEVER")
                self.log(1)
                self.hook(hook_tests.event(self.root))
                with open(self.state, encoding="utf-8") as handle:
                    text = handle.read()
                if change == "criterion":
                    text = text.replace("tests pass", "all tests pass")
                elif change == "dependency":
                    text = text.replace("after: NEVER", "after: UNKNOWN")
                else:
                    text = text.replace("T11 closed — tests pass", "T11 closed — review passes")
                self.write_state(text=text, keep_sidecar=True)
                out = self.hook(hook_tests.event(self.root, continued=True))
                self.assertEqual(self.sidecar_data()["strikes"], 1)
                self.assertIn("no-progress key did not change", self.reason(out))

    def test_parser_remains_lenient_with_default_budget(self):
        header, items, count = hook.parse_state(
            "owner: x\n## Queue\n- [ready] A work; after: NEVER\n"
            "unmatched queue prose\n- [ready] A duplicate\n")
        self.assertEqual(header["budget"], 50)
        self.assertEqual([item["id"] for item in items], ["A", "A"])
        self.assertEqual(count, 0)


class NeutralStdoutTest(hook_tests.HostBase):
    def test_normal_rejected_and_error_stdout_after_host_resolution(self):
        for host in ("claude", "codex", "cursor", "antigravity", "devin"):
            for case in ("paused", "unaccepted", "malformed", "non-object", "state error"):
                with self.subTest(host=host, case=case):
                    self.write_state(stop="paused: user request" if case == "paused" else "")
                    events = {"claude": hook_tests.event(self.root),
                              "codex": hook_tests.codex_event(self.root),
                              "cursor": hook_tests.cursor_event(self.root),
                              "antigravity": hook_tests.antigravity_event(self.root),
                              "devin": hook_tests.devin_event()}
                    ev = events[host]
                    if case == "unaccepted":
                        ev = {"hook_event_name": "Other", "hookEventName": "Other"}
                    if case == "state error":
                        self.write_state(text="owner: x\n## Not Queue\n")
                    stdin = "{" if case == "malformed" else "[]" if case == "non-object" \
                        else json.dumps(ev)
                    out = self.run_raw(stdin, ("--host", host, "--state", self.state))
                    self.assertEqual(out, {"decision": "stop"} if host == "antigravity" else {})

    def test_argument_failure_before_host_resolution_keeps_default(self):
        for args in (("--host", "antigravity", "--state"),
                     ("--host", "antigravity", "--host", "antigravity")):
            self.assertEqual(self.run_raw("{", args), {})


class InstallerFailureTest(installer_tests.Base):
    def call_main(self, *extra):
        args = ["install_hook.py", "--host", "codex", "--scope", "project",
                "--workspace", self.workspace] + list(extra)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = installer.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_failure(self, result):
        code, stdout, stderr = result
        self.assertEqual((code, stdout), (1, ""))
        for text in ("operation failed", "Inspect the target", "permissions", "--dry-run"):
            self.assertIn(text, stderr)
        self.assertNotIn("left untouched", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_atomic_failures_preserve_target_and_clean_temporary_file(self):
        path = self.path("codex", "project")
        for operation in ("makedirs", "mkstemp", "fdopen", "chmod", "replace"):
            with self.subTest(operation=operation):
                self.write(path, '{"keep": true}\n')
                original_fdopen = installer.os.fdopen

                def fail_fdopen(fd, *args, **kwargs):
                    os.close(fd)
                    raise OSError("injected fdopen failure")

                target = installer.tempfile if operation == "mkstemp" else installer.os
                effect = fail_fdopen if operation == "fdopen" else OSError("injected failure")
                with mock.patch.object(target, operation, side_effect=effect):
                    self.assert_failure(self.call_main())
                self.assertEqual(self.read(path), '{"keep": true}\n')
                self.assertEqual(os.listdir(os.path.dirname(path)), ["hooks.json"])
                self.assertIs(installer.os.fdopen, original_fdopen)

    def test_stat_failure_during_atomic_write_preserves_target(self):
        path = self.path("codex", "project")
        self.write(path, '{"keep": true}\n')
        write = installer.write_atomic

        def fail_stat(*args):
            with mock.patch.object(installer.os.path, "exists", return_value=True), \
                    mock.patch.object(installer.os, "stat", side_effect=OSError("stat failed")):
                write(*args)

        with mock.patch.object(installer, "write_atomic", side_effect=fail_stat):
            self.assert_failure(self.call_main())
        self.assertEqual(self.read(path), '{"keep": true}\n')
        self.assertEqual(os.listdir(os.path.dirname(path)), ["hooks.json"])

    def test_cleanup_failure_reports_error_and_residual_temp_requires_inspection(self):
        path = self.path("codex", "project")
        self.write(path, '{"keep": true}\n')
        with mock.patch.object(installer.os, "replace", side_effect=OSError("replace failed")), \
                mock.patch.object(installer.os, "unlink", side_effect=OSError("cleanup failed")):
            result = self.call_main()
        self.assert_failure(result)
        self.assertIn("cleanup failed", result[2])
        self.assertEqual(self.read(path), '{"keep": true}\n')
        temporary = [name for name in os.listdir(os.path.dirname(path))
                     if name.startswith(".agent-loop.")]
        self.assertEqual(len(temporary), 1)
        os.unlink(os.path.join(os.path.dirname(path), temporary[0]))

    def test_write_failure_preserves_target_and_cleans_temp(self):
        path = self.path("codex", "project")
        self.write(path, '{"keep": true}\n')
        fdopen = installer.os.fdopen

        @contextlib.contextmanager
        def failing_writer(fd, *args, **kwargs):
            with fdopen(fd, *args, **kwargs) as handle:
                with mock.patch.object(handle, "write", side_effect=OSError("write failed")):
                    yield handle

        with mock.patch.object(installer.os, "fdopen", side_effect=failing_writer):
            self.assert_failure(self.call_main())
        self.assertEqual(self.read(path), '{"keep": true}\n')
        self.assertEqual(os.listdir(os.path.dirname(path)), ["hooks.json"])

    def test_uninstall_unlink_failure_preserves_target(self):
        path = self.path("codex", "project")
        self.install("codex", "project")
        before = self.read(path)
        with mock.patch.object(installer.os, "unlink", side_effect=OSError("unlink failed")):
            self.assert_failure(self.call_main("--uninstall"))
        self.assertEqual(self.read(path), before)

    def test_error_after_mutation_makes_no_untouched_promise(self):
        path = self.path("codex", "project")
        write = installer.write_atomic

        def write_then_fail(*args):
            write(*args)
            raise OSError("after replacement")

        with mock.patch.object(installer, "write_atomic", side_effect=write_then_fail):
            self.assert_failure(self.call_main())
        self.assertIn("hooks", json.loads(self.read(path)))

    def test_refusal_and_workspace_diagnostics_are_actionable(self):
        path = self.path("codex", "project")
        self.write(path, "[]")
        code, stdout, stderr = self.call_main()
        self.assertEqual((code, stdout), (1, ""))
        for text in ("left untouched", "Expected readable plain JSON", "--dry-run"):
            self.assertIn(text, stderr)
        self.assertEqual(self.read(path), "[]")
        with mock.patch.object(installer.os.path, "isdir", return_value=False):
            code, stdout, stderr = self.call_main()
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("Expected an existing workspace", stderr)
        self.assertIn("--dry-run", stderr)

    def test_real_parent_path_failure_has_controlled_subprocess_diagnostic(self):
        with open(os.path.join(self.workspace, ".codex"), "w", encoding="utf-8") as handle:
            handle.write("not a directory")
        proc = self.run_installer("--host", "codex", "--scope", "project",
                                  "--workspace", self.workspace)
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))
        self.assertIn("operation failed", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
