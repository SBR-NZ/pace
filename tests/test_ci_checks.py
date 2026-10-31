"""The runner that runs these checks on GitHub (.github/run_checks.py): it fails the run when a check does not pass,
says when a list of them is cut short, and keeps what the checks print from being read as GitHub's commands.

Invented checks only, in temporary folders.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

RUNNER = Path(__file__).resolve().parents[1] / ".github/run_checks.py"
WORKFLOW = RUNNER.parent / "workflows/checks.yml"
CHECKS = '''import unittest


class Invented(unittest.TestCase):
    def test_passes(self):
        pass
'''


def load():
    spec = importlib.util.spec_from_file_location("run_checks_under_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunnerTests(unittest.TestCase):
    def run_checks(self, body: str) -> tuple:
        """The runner over one invented module of checks: its exit code, what it printed and its summary page."""
        with tempfile.TemporaryDirectory(prefix="pace-ci-") as base:
            folder = Path(base, "tests")
            folder.mkdir()
            (folder / "test_invented_for_the_runner.py").write_text(CHECKS + body, encoding="utf-8")
            page = Path(base, "summary.md")
            runner, printed, previous = load(), io.StringIO(), os.getcwd()
            runner.TESTS = folder
            try:
                with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(page)}), \
                        contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
                    code = runner.main()
            finally:
                os.chdir(previous)  # before the folder is removed, which Windows refuses while it is the current one
                sys.path[:] = [entry for entry in sys.path if entry != str(folder)]
                sys.modules.pop("test_invented_for_the_runner", None)
            return code, printed.getvalue(), page.read_text(encoding="utf-8")

    def test_the_run_fails_only_when_a_check_does_not_pass(self):
        code, printed, _ = self.run_checks("")
        self.assertEqual(code, 0)
        self.assertIn("::notice title=All 1 check passed", printed)
        code, printed, page = self.run_checks("\n    def test_fails(self):\n        self.fail('Invented failure.')\n")
        self.assertEqual(code, 1)
        self.assertIn("::error title=failed%3A test_invented_for_the_runner.Invented.test_fails::", printed)
        self.assertIn("AssertionError: Invented failure.", page)

    def test_a_list_cut_short_says_how_many_are_left_out(self):
        failing = "".join(f"\n    def test_fails_{number:03d}(self):\n        self.fail('Invented failure {number:03d} "
                          f"{'x' * 150}')\n" for number in range(60))
        code, printed, page = self.run_checks(failing)
        self.assertEqual(code, 1)
        grouped = next(line for line in printed.splitlines() if "by what each ended with" in line)
        self.assertRegex(grouped, r"\.\.\. and \d+ more, all listed on this run's summary page\.")
        self.assertEqual(page.count("<summary>failed: "), 60)

    def test_nothing_the_checks_print_is_read_as_a_command(self):
        code, printed, _ = self.run_checks("\n    def test_prints(self):\n        print('::error::Invented, from a check.')\n")
        self.assertEqual(code, 0)
        lines = printed.splitlines()
        stop = next(index for index, line in enumerate(lines) if line.startswith("::stop-commands::"))
        token = lines[stop].split("::")[2]
        self.assertGreaterEqual(len(token), 32)
        resume = lines.index(f"::{token}::")
        inside = lines[stop + 1:resume]
        self.assertIn("::error::Invented, from a check.", inside)  # printed while commands were off
        self.assertTrue(all(not line.startswith("::") for line in lines[resume + 1:] if "Invented, from a check" in line))



class WorkflowTests(unittest.TestCase):
    """The workflow runs only where it is meant to, stops a stuck run soon, and installs only what it pinned."""

    def test_it_runs_only_in_the_development_repository_and_not_for_long(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("    if: github.repository == 'Daniel-SBRNZ/pace-dev'\n", text)
        self.assertIn("    timeout-minutes: 15", text)
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertRegex(text, r'echo "tzdata==\d{4}\.\d+ --hash=sha256:[0-9a-f]{64}"')
        self.assertIn("--require-hashes", text)
        for action in ("actions/checkout@", "actions/setup-python@"):
            self.assertRegex(text, action.replace(".", r"\.") + r"[0-9a-f]{40}  # v\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
