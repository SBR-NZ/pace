"""What differs between Linux, Windows and macOS, found when the checks first ran on each: each test here fails on
3.16.1 (78fb842) on Linux as well as where the difference first showed, the store's removal with Python 3.9, as
Apple's python3 is, since newer Pythons pass over a file already gone themselves.

Invented data only, in temporary folders.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import ctypes  # loaded as this system is, before a test makes it look like macOS
except ImportError:  # some Python builds have no ctypes; the tools then look for the target just before
    ctypes = None

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

TOOLS = Path(__file__).resolve().parents[1] / "PACE/Product/Tools"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pr = load("pace_record")
pu = load("pace_update")


class FakeCall:
    """A C function as ctypes gives it, recording what it was called with."""

    def __init__(self, result: int):
        self.result, self.calls = result, []

    def __call__(self, *arguments):
        self.calls.append(arguments)
        return self.result


@unittest.skipIf(ctypes is None, "this Python has no ctypes, so the tools look for the target just before")
class MacRenameTests(unittest.TestCase):
    """macOS renamed over a file that arrived after Pace looked, as a sync client can put one there, where Linux and
    Windows refuse: the archive tool's check that a late arrival is never replaced failed there."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-platforms-")
        self.source = Path(self._temp.name, "20260901T010000Z--kowhai--act001.md")
        self.source.write_text("Invented record.\n", encoding="utf-8")
        self.target = Path(self._temp.name, "2026", "09", self.source.name)
        self.target.parent.mkdir(parents=True)

    def tearDown(self):
        self._temp.cleanup()

    @contextlib.contextmanager
    def on_a_mac(self, call: FakeCall, failed: int = 0):
        """This system made to look like macOS, whose renamex_np is call and whose errno after it is failed."""
        libc = mock.Mock(spec=["renamex_np"], renamex_np=call)
        with mock.patch.object(ctypes, "CDLL", return_value=libc) as loaded, \
                mock.patch.object(ctypes, "get_errno", return_value=failed), \
                mock.patch.object(pr.sys, "platform", "darwin"), mock.patch.object(pr.os, "name", "posix"):
            yield loaded

    def test_macos_is_asked_to_refuse_a_file_that_arrives_after_pace_looked(self):
        call = FakeCall(-1)  # macOS finds the late arrival and refuses
        with self.on_a_mac(call, errno.EEXIST) as loaded, self.assertRaises(FileExistsError):
            pr.rename_no_replace(self.source, self.target)
        self.assertEqual(call.calls, [(os.fsencode(str(self.source)), os.fsencode(str(self.target)), 4)])  # RENAME_EXCL
        loaded.assert_called_once_with(None, use_errno=True)  # else the refusal's reason is lost
        self.assertTrue(self.source.is_file())
        self.assertFalse(self.target.exists())

    def test_a_folder_that_cannot_refuse_is_looked_in_just_before(self):
        for there in (False, True):
            with self.subTest(something_at_the_target=there):
                if there:
                    self.target.write_text("A copy already there.\n", encoding="utf-8")
                call = FakeCall(-1)
                with self.on_a_mac(call, errno.ENOTSUP):
                    if there:
                        with self.assertRaises(FileExistsError):
                            pr.rename_no_replace(self.source, self.target)
                    else:
                        pr.rename_no_replace(self.source, self.target)
                self.assertEqual(len(call.calls), 1)
                if there:
                    self.assertEqual(self.target.read_text(encoding="utf-8"), "A copy already there.\n")
                    self.assertTrue(self.source.is_file())
                else:
                    self.assertEqual(self.target.read_text(encoding="utf-8"), "Invented record.\n")
                    self.target.rename(self.source)  # back for the next case


class GitTidyingTests(unittest.TestCase):
    """Newer git tidies a repository in the background after a fetch, so on macOS the updater's throwaway store still
    had git's maintenance.lock coming and going while the updater removed it, and the update stopped on a file
    error instead of saying why it stopped."""

    def test_no_git_command_the_updater_runs_starts_background_tidying(self):
        seen = []

        def run(command, **options):
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with mock.patch.object(pu.subprocess, "run", run):
            pu._git(["fetch", "--quiet", "--no-tags", "--", "invented", "+refs/tags/v3.16.1:refs/tags/v3.16.1"])
        self.assertEqual(seen[0][:5], ["git", "-c", "maintenance.auto=false", "-c", "gc.auto=0"])
        self.assertEqual(seen[0][5], "fetch")

    def test_a_file_another_program_removes_first_does_not_stop_the_store_being_removed(self):
        with tempfile.TemporaryDirectory(prefix="pace-platforms-") as base:
            store = Path(base, "pace-update-invented", "source.git")
            (store / "objects").mkdir(parents=True)
            (store / "maintenance.lock").write_text("", encoding="utf-8")
            (store / "config").write_text("[core]\n", encoding="utf-8")
            real_unlink = os.unlink

            def unlink(path, *arguments, **options):
                if os.fsdecode(path).endswith("maintenance.lock"):
                    real_unlink(path, *arguments, **options)  # git removes it just before Pace does
                    raise FileNotFoundError(errno.ENOENT, "No such file or directory", "maintenance.lock")
                return real_unlink(path, *arguments, **options)

            with mock.patch.object(os, "unlink", unlink):
                pu._remove_tree(store.parent)
            self.assertFalse(store.parent.exists())



class ChangelogTests(unittest.TestCase):
    """The changelog said macOS never replaces a late arrival, though a drive that cannot refuse is looked in just
    before, and that only the throwaway copy passes over a file already gone, though every folder the updater removes
    does."""

    def test_the_changelog_says_where_each_change_applies(self):
        text = " ".join((TOOLS.parents[2] / "CHANGELOG.md").read_text(encoding="utf-8").split())
        self.assertIn("wherever its file system can refuse", text)
        self.assertIn("On a drive or share that cannot refuse, such as exFAT or a network share, Pace still looks just "
                      "before, as before.", text)
        self.assertIn("When the updater removes a folder of its own, such as that copy, the update's work area or a partly "
                      "made Pace folder, a file already gone is passed over.", text)
        self.assertNotIn("never replaces a copy a sync client put there", text)


if __name__ == "__main__":
    unittest.main()
