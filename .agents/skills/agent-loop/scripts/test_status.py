#!/usr/bin/env python3
"""Tests for the read-only `loop_hook.py status` command.

Each case runs the command as a subprocess against a temporary workspace.
Python 3.8 or later, standard library only.
"""
import os
import subprocess
import sys

import test_loop_hook as hook_tests

HEADER = """# Agent loop

goal: Ship the export feature — done when: CI is green
owner: sess-owner
stop:
async gates: design choice
budget: 50
{extra}
## Queue
{items}

## Log
{log}"""


def ready(ident, rest=""):
    return "- [ready] %s Work — done when: tests pass%s" % (ident, rest)


def closure(ident):
    return "- 2026-11-01T10:00Z %s closed — tests pass\n" % ident


class StatusBase(hook_tests.Base):
    def status(self, *args, cwd=None):
        """Run status; return (exit code, stdout, stderr)."""
        proc = subprocess.run([sys.executable, hook_tests.HOOK, "status"] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", env=hook_tests.clean_env(),
                              cwd=cwd or self.root, timeout=20)
        return proc.returncode, proc.stdout, proc.stderr

    def report(self, *args, cwd=None):
        code, out, err = self.status(*args, cwd=cwd)
        self.assertEqual((code, err), (0, ""), err)
        self.assertTrue(out.startswith("state: "), out)
        return out

    def write(self, items, extra="", log=""):
        self.write_state(text=HEADER.format(extra=extra, items="\n".join(items), log=log))

    def section(self, out, title):
        """The lines from a section title up to the next unindented line."""
        lines = out.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith(title))
        body = [lines[start]]
        for line in lines[start + 1:]:
            if not line.startswith("  "):
                break
            body.append(line)
        return body

    def problems(self, out):
        return "\n".join(self.section(out, "problems:"))


class ReportTest(StatusBase):
    def test_sections_in_order_for_a_clean_file(self):
        self.write([ready("T1"), "- [doing] T2 Fix — done when: green; next: rerun",
                    "- [waiting] T3 CI — done when: passes; wake: CI ends; check: ci status",
                    "- [user] T4 Push — done when: pushed; ask: push?; asked: 2026-11-01"],
                   log=closure("T0"))
        out = self.report()
        lines = out.splitlines()
        self.assertEqual(lines[:8], [
            "state: %s" % self.state,
            "goal: Ship the export feature — done when: CI is green",
            "owner: sess-owner", "stop: (none)", "async gates: design choice",
            "budget: 50", "parallel: 1 (default)",
            "counts: 1 doing, 1 ready, 0 ready but blocked, 1 waiting, 1 need you, 1 closed"])
        titles = [line.split(":")[0] for line in lines[8:] if not line.startswith("  ")]
        self.assertEqual(titles, ["doing", "next", "waiting", "need you", "problems"])
        self.assertEqual(lines[-1], "problems: none")
        self.assertNotIn("wave:", out)

    def test_found_by_walking_up_and_by_flag(self):
        self.write([ready("T1")])
        sub = os.path.join(self.root, "src", "pkg")
        os.makedirs(sub)
        self.assertIn("state: %s" % self.state, self.report(cwd=sub))
        self.assertIn("state: %s" % self.state,
                      self.report("--state", self.state, cwd=self.elsewhere))

    def test_dependencies_met_unmet_and_unknown(self):
        self.write([ready("T1", "; after: T0"), ready("T2", "; after: T1"),
                    ready("T3", "; after: GHOST"), ready("T4", "; after: T0, T1")],
                   log=closure("T0"))
        out = self.report()
        self.assertIn("1 ready, 3 ready but blocked", out)
        self.assertEqual(self.section(out, "next:"),
                         ["next:", "  " + ready("T1", "; after: T0")])
        self.assertIn("line 12: T3 after: GHOST: neither an open item nor closed in Log",
                      out)
        self.assertNotIn("after: T1:", out)

    def test_blocked_doing_item_names_its_blockers(self):
        self.write(["- [doing] T1 Fix — done when: green; after: T2, GHOST", ready("T2")])
        doing = self.section(self.report(), "doing:")
        self.assertTrue(doing[1].endswith("(blocked: T2 open, GHOST unknown)"), doing)

    def test_limit_caps_every_list(self):
        items = ["- [doing] D%d Work — done when: x" % n for n in range(4)]
        items += [ready("R%d" % n) for n in range(4)]
        items += ["- [waiting] W%d Wait — done when: x; wake: e; check: c" % n for n in range(4)]
        items += ["- [user] U%d Ask — done when: x; ask: q?" % n for n in range(4)]
        items += [ready("B%d" % n, "; after: GHOST%d" % n) for n in range(4)]
        self.write(items)
        out = self.report("--limit", "2")
        for title in ("doing:", "next:", "waiting:", "need you:", "problems:"):
            with self.subTest(title=title):
                body = self.section(out, title)
                self.assertEqual(len(body), 4, body)
                self.assertEqual(body[-1], "  +2 more")
        self.assertEqual(len(self.section(self.report(), "next:")), 5)

    def test_bad_limit_and_arguments_exit_2(self):
        self.write([ready("T1")])
        for args in (["--limit", "0"], ["--limit", "x"], ["--limit"], ["--bogus"],
                     ["--state", self.state, "--state", self.state]):
            with self.subTest(args=args):
                code, out, err = self.status(*args)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("loop_hook.py status: "), err)
                self.assertIn("Expected", err)


class RevisionTest(StatusBase):
    def test_every_after_field_counts(self):
        user = "- [user] T1 U — done when: x; ask: q?"
        for item in (ready("T2", "; after: T0; after: T1"),
                     ready("T2", "; after: ; next: go after: T1")):
            with self.subTest(item=item):
                self.write([user, item], log=closure("T0"))
                out = self.report()
                self.assertIn("next: none", out)
                self.assertIn("0 ready, 1 ready but blocked", out)

    def test_evidence_naming_a_closure_closes_nothing(self):
        self.write([ready("T1"), ready("T2", "; after: T1")],
                   log="- 2026-11-01T10:00Z T9 reopened — the T1 closed earlier was wrong\n"
                       "- 2026-11-01T10:05Z T0 closed — PR closed after merge\n")
        out = self.report()
        self.assertNotIn("open in Queue and closed in Log", out)
        self.assertIn("1 closed", out)

    def test_long_log_token_stays_fast(self):
        self.write([ready("T1")], log="- " + "x" * 40000 + "\n")
        proc = subprocess.run([sys.executable, hook_tests.HOOK, "status"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", env=hook_tests.clean_env(), cwd=self.root,
                              timeout=3)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_huge_numbers_are_values_not_crashes(self):
        huge = "9" * 5000
        text = HEADER.format(extra="parallel: %s\n" % huge, items=ready("T1", "; tries: " + huge),
                             log="")
        self.write_state(text=text.replace("budget: 50", "budget: " + huge))
        out = self.report("--limit", huge)
        self.assertIn("T1 has tries: 1000000000", out)
        self.assertIn("wave: none", out)

    def test_tries_that_is_not_a_whole_number_counts_as_zero(self):
        self.write([ready("T1", "; tries: many"), ready("T2", "; tries: 3.5")])
        self.assertIn("problems: none", self.report())

    def test_unwritable_stdout_exits_2_without_traceback(self):
        self.write([ready("T1")])
        read_end, write_end = os.pipe()
        os.close(read_end)
        targets = [write_end]
        if os.path.exists("/dev/full"):
            targets.append(os.open("/dev/full", os.O_WRONLY))
        for target in targets:
            with self.subTest(target=target):
                proc = subprocess.run([sys.executable, hook_tests.HOOK, "status"],
                                      stdout=target, stderr=subprocess.PIPE,
                                      encoding="utf-8", env=hook_tests.clean_env(),
                                      cwd=self.root, timeout=20)
                os.close(target)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("cannot write the report", proc.stderr)

    def test_limit_caps_cycle_members_and_blockers(self):
        self.write([ready("T1", "; after: T3"), ready("T2", "; after: T1"),
                    ready("T3", "; after: T2"),
                    "- [doing] T4 D — done when: x; after: T1, T2, G1, G2"])
        out = self.report("--limit", "1")
        self.assertIn("dependency cycle among T1, +2 more", out)
        self.assertIn("(blocked: T1 open, +3 more)", out)

    def test_unknown_ids_are_one_problem_per_item(self):
        self.write([ready("T1"), ready("T2", "; after: T1 — needs api")])
        problems = self.section(self.report(), "problems:")
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("T2 after: —, needs, api: neither", problems[1])

    def test_crlf_line_endings(self):
        text = HEADER.format(extra="", items=ready("T1", "; after: T0"), log=closure("T0"))
        with open(self.state, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace("\n", "\r\n"))
        out = self.report()
        self.assertIn("counts: 0 doing, 1 ready, 0 ready but blocked", out)
        self.assertIn("problems: none", out)


class NoFileTest(StatusBase):
    def test_no_state_file_exits_2_with_guidance(self):
        code, out, err = self.status()
        self.assertEqual((code, out), (2, ""))
        for text in ("no .agent-loop.md found", "Expected a state file", "--state PATH"):
            self.assertIn(text, err)
        self.assertFalse(os.path.exists(self.sidecar))

    def test_missing_state_flag_path_exits_2(self):
        code, out, err = self.status("--state", os.path.join(self.root, "missing.md"))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no state file at", err)
        self.assertIn("Try", err)

    def test_unreadable_file_exits_2(self):
        with open(self.state, "wb") as handle:
            handle.write(b"## Queue\n- [ready] T1 \xff\xfe\n")
        code, out, err = self.status()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("cannot read", err)
        self.assertIn("UTF-8", err)


class ReadOnlyTest(StatusBase):
    def snapshot(self):
        result = {}
        for name in sorted(os.listdir(self.root)):
            path = os.path.join(self.root, name)
            if os.path.isfile(path):
                info = os.stat(path)
                with open(path, "rb") as handle:
                    result[name] = (handle.read(), info.st_mtime_ns, info.st_size)
            else:
                result[name] = None
        return result

    def test_status_writes_nothing(self):
        self.write([ready("T1"), ready("T2", "; after: T1; writes: a/*"),
                    "- [waiting] T3 W — done when: x", "not an item", "- broken"],
                   extra="parallel: 2\n", log=closure("T0"))
        self.write_sidecar('{"goal": null, "turns": 3, "key": null, "strikes": 1}')
        before = self.snapshot()
        self.report()
        self.report("--state", self.state, "--limit", "1")
        self.assertEqual(self.snapshot(), before)

    def test_no_sidecar_appears(self):
        self.write([ready("T1")])
        before = self.snapshot()
        self.report()
        self.assertFalse(os.path.exists(self.sidecar))
        self.assertEqual(self.snapshot(), before)


class BoundTest(StatusBase):
    def queue(self, count):
        kinds = ("- [doing] D%03d Work — done when: x; writes: d%03d/*",
                 "- [ready] R%03d Work — done when: x; writes: r%03d/*",
                 "- [waiting] W%03d Wait — done when: x; wake: e; check: c%03d",
                 "- [user] U%03d Ask — done when: x; ask: q%03d?",
                 "- [ready] B%03d Work — done when: x; after: GHOST%03d")
        items = [kinds[n % len(kinds)] % (n, n) for n in range(count)]
        self.write(items, extra="parallel: 4\n",
                   log="".join(closure("C%03d" % n) for n in range(count)))
        return self.report("--limit", "3")

    def test_output_does_not_grow_with_items(self):
        small, large = self.queue(50), self.queue(500)
        self.assertLessEqual(len(large), len(small) + 40)
        self.assertLessEqual(len(large.splitlines()), len(small.splitlines()))


class ProblemTest(StatusBase):
    def assert_problem(self, out, *fragments):
        text = self.problems(out)
        for fragment in fragments:
            self.assertIn(fragment, text)

    def test_no_queue_section(self):
        self.write_state(text="goal: g\nowner: o\n\n## Work\n- [ready] T1 x\n")
        out = self.report()
        self.assert_problem(out, "file: no ## Queue section; add a `## Queue` heading")

    def test_duplicate_header_key(self):
        self.write([ready("T1")], extra="stop: paused\n")
        out = self.report()
        self.assert_problem(out, "line 8: duplicate header key `stop`")
        self.assertIn("stop: (none)", out)

    def test_bad_budget_and_parallel(self):
        text = HEADER.format(extra="parallel: 0\n", items=ready("T1"), log="")
        self.write_state(text=text.replace("budget: 50", "budget: fifty"))
        out = self.report()
        self.assert_problem(out, "line 7: bad budget `fifty`", "line 8: bad parallel `0`")
        self.assertNotIn("wave:", out)

    def test_unknown_status_and_non_item_line(self):
        self.write([ready("T1"), "- [done] T2 Old — done when: x", "- loose note",
                    "* [ready]", "plain prose is ignored"])
        out = self.report()
        self.assert_problem(out, "line 11: unknown status [done]",
                            "line 12: queue line is not an item",
                            "line 13: queue line is not an item")
        self.assertNotIn("line 14", out)

    def test_duplicate_and_open_and_closed_ids(self):
        self.write([ready("T1"), ready("T1"), ready("T0")], log=closure("T0"))
        self.assert_problem(self.report(), "line 11: duplicate item ID T1",
                            "line 12: T0 is open in Queue and closed in Log")

    def test_cycle(self):
        self.write([ready("T1", "; after: T3"), ready("T2", "; after: T1"),
                    ready("T3", "; after: T2"), ready("T4", "; after: T4"),
                    ready("T5", "; after: T1"), ready("T6")])
        out = self.report()
        self.assert_problem(out, "line 10: dependency cycle among T1, T2, T3",
                            "line 13: dependency cycle among T4")
        self.assertNotIn("among T1, T2, T3, T5", out)
        self.assertNotIn("every open item", out)

    def test_waiting_user_and_tries(self):
        self.write(["- [waiting] T1 W — done when: x; wake: CI ends",
                    "- [waiting] T2 W — done when: x; check: ci status",
                    "- [waiting] T3 W — done when: x; wake: e; check: c",
                    "- [user] T4 U — done when: x; asked: 2026-11-01",
                    "- [user] T5 U — done when: x; ask: q?; tries: 4",
                    ready("T6", "; tries: 3"), ready("T7", "; tries: 2")])
        out = self.report("--limit", "10")
        self.assert_problem(out, "line 10: waiting item T1 lacks wake: or check:",
                            "line 11: waiting item T2 lacks wake: or check:",
                            "line 13: user item T4 lacks ask:",
                            "line 15: T6 has tries: 3; mark it user with an ask:")
        for absent in ("line 12", "line 14", "line 16"):
            self.assertNotIn(absent, self.problems(out))

    def test_every_open_item_blocked(self):
        self.write([ready("T1", "; after: T2"), "- [doing] T2 X — done when: x; after: GONE"])
        self.assert_problem(self.report(), "line 10: every open item is blocked")
        self.write([ready("T1", "; after: T2"),
                    "- [waiting] T2 W — done when: x; wake: e; check: c"])
        self.assertIn("problems: none", self.report())


class WaveTest(StatusBase):
    def wave(self, items, parallel=3):
        self.write(items, extra="parallel: %d\n" % parallel)
        out = self.report()
        return next(line for line in out.splitlines() if line.startswith("wave:"))

    def test_disjoint_scopes_fill_free_slots(self):
        line = self.wave([ready("T1", "; writes: api/*"), ready("T2", "; writes: web/a.ts"),
                          ready("T3", "; writes: docs/*"), ready("T4", "; writes: cli/*")])
        self.assertEqual(line, "wave: T1, T2, T3 (3 free slots)")

    def test_overlap_by_static_prefix(self):
        line = self.wave([ready("T1", "; writes: src/api/*.py"),
                          ready("T2", "; writes: src/api/v2/x.py"),
                          ready("T3", "; writes: src/*"),
                          ready("T4", "; writes: tests/web_[ab].py, ./src/api"),
                          ready("T5", "; writes: tests/w*")])
        self.assertEqual(line, "wave: T1, T5 (3 free slots)")
        line = self.wave([ready("T1", "; writes: lib/a*"), ready("T2", "; writes: lib/b?"),
                          ready("T3", "; writes: *.md")])
        self.assertEqual(line, "wave: T1, T2 (3 free slots)")

    def test_item_without_writes_and_blocked_item_excluded(self):
        line = self.wave([ready("T1"), ready("T2", "; writes:"),
                          ready("T3", "; writes: a/*; after: T1"), ready("T4", "; writes: b/*")])
        self.assertEqual(line, "wave: T4 (3 free slots)")

    def test_open_doing_and_waiting_scopes_and_slots(self):
        line = self.wave(["- [doing] T1 D — done when: x; writes: api/*",
                          "- [waiting] T2 W — done when: x; wake: worker w; check: c; "
                          "writes: web/*",
                          "- [doing] T3 D — done when: x",
                          ready("T4", "; writes: api/v2/*"), ready("T5", "; writes: web/x"),
                          ready("T6", "; writes: docs/*"), ready("T7", "; writes: cli/*")],
                         parallel=3)
        self.assertEqual(line, "wave: T6 (1 free slot)")
        line = self.wave(["- [doing] T1 D — done when: x; writes: api/*",
                          ready("T2", "; writes: b")], parallel=2)
        self.assertEqual(line, "wave: T2 (1 free slot)")

    def test_no_free_slot(self):
        line = self.wave(["- [doing] T1 D — done when: x; writes: a/*",
                          "- [doing] T2 D — done when: x; writes: b/*",
                          ready("T3", "; writes: c/*")], parallel=2)
        self.assertEqual(line, "wave: none (0 free slots)")


if __name__ == "__main__":
    import unittest
    unittest.main()


class NumberAndIdFormTest(StatusBase):
    def test_zero_padded_numbers_keep_their_value(self):
        self.write([ready("T1", "; tries: 0000000002; writes: a/*"),
                    ready("T2", "; writes: b/*"), ready("T3", "; writes: c/*")],
                   extra="parallel: 0000000002\n")
        out = self.report()
        self.assertIn("wave: T1, T2 (2 free slots)", out)
        self.assertIn("problems: none", out)
        self.assertIn("+2 more", "\n".join(self.section(self.report("--limit", "00000000001"),
                                                        "next:")))

    def test_zero_parallel_written_with_many_zeros_is_a_problem(self):
        self.write([ready("T1")], extra="parallel: 0000000000\n")
        self.assertIn("parallel", "\n".join(self.section(self.report(), "problems:")))

    def test_dotted_ids_in_dependencies_closures_and_wave(self):
        self.write([ready("T4.2", "; after: T4.1; writes: a/*"),
                    ready("T4.2.1", "; after: T4.2, T4.1; writes: b/*"),
                    ready("T4.3", "; after: T4.1; writes: c/*")],
                   extra="parallel: 3\n", log=closure("T4.1"))
        out = self.report()
        self.assertIn("wave: T4.2, T4.3", out)
        self.assertIn("problems: none", out)

    def test_note_before_a_hyphen_names_no_closure(self):
        self.write([ready("T2", "; after: T1")],
                   log="- 2026-11-01 note - T1 closed by mistake\n")
        out = self.report()
        self.assertIn("0 closed", out)
        self.assertIn("T1", "\n".join(self.section(out, "problems:")))

    def test_closure_line_with_hyphen_dash_still_counts(self):
        self.write([ready("T2", "; after: T1")], log="- 2026-11-01 10:00 T1 closed - tests pass\n")
        self.assertIn("1 closed", self.report())

    def test_path_that_is_not_utf8_prints_without_a_traceback(self):
        if os.name != "posix":
            self.skipTest("needs a byte-named directory")
        odd = os.fsdecode(os.path.join(os.fsencode(self.root), b"bad\xff"))
        os.mkdir(odd)
        self.write([ready("T1")])
        os.replace(os.path.join(self.root, ".agent-loop.md"), os.path.join(odd, ".agent-loop.md"))
        proc = subprocess.run([sys.executable, hook_tests.HOOK, "status"], cwd=odd,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=hook_tests.clean_env(), timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(b"Traceback", proc.stderr)

    def test_closed_standard_output_exits_2_without_a_traceback(self):
        if os.name != "posix":
            self.skipTest("needs a shell that can close a descriptor")
        self.write([ready("T1")])
        proc = subprocess.run('"%s" "%s" status >&-' % (sys.executable, hook_tests.HOOK),
                              shell=True, cwd=self.root, stderr=subprocess.PIPE,
                              env=hook_tests.clean_env(), timeout=20)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn(b"Traceback", proc.stderr)


class OpenWaveHookTest(StatusBase):
    HELD = ("- [waiting] W%d Work — done when: tests pass; writes: w%d/*; "
            "wake: worker w%d; check: test -f out/w%d")

    def held(self, *numbers):
        return [self.HELD % (n, n, n, n) for n in numbers]

    def running(self):
        return hook_tests.event(self.root, background_tasks=[{"id": "w"}])

    def test_full_wave_gives_no_turn_for_ready_items(self):
        self.write(self.held(1, 2) + [ready("T7", "; writes: t7/*"), ready("T8")],
                   extra="parallel: 2\n")
        self.assert_stop(self.hook(self.running()))

    def test_free_slot_gives_a_turn_for_a_wave_item_only(self):
        self.write(self.held(1) + [ready("T8"), ready("T7", "; writes: t7/*")],
                   extra="parallel: 2\n")
        self.assert_block(self.hook(self.running()), "1 actionable", "(now T7)")

    def test_overlapping_ready_item_is_not_actionable_while_a_worker_holds_its_scope(self):
        self.write(self.held(1) + [ready("T7", "; writes: w1/a.py")], extra="parallel: 3\n")
        self.assert_stop(self.hook(self.running()))

    def test_sequential_file_keeps_ready_items_actionable_beside_a_wait(self):
        self.write(self.held(1) + [ready("T8")])
        self.assert_block(self.hook(self.running()), "1 actionable", "(now T8)")
