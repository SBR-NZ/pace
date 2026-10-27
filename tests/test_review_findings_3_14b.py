"""Release 3.14.0's second review, of the fixes in afaf170: each finding has a test here that fails on that commit.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

import test_updates as tu
from test_archive import AS_AT, MOVING, OWNER, FolderCase, HELP, TOOLS, pa, po, pr, read, run, write_project, write_record
from test_review_findings_3_14 import LONG, health

HAND = "20260915T010000Z--kowhai--hand01"


def setUpModule():
    tu.setUpModule()


def tearDownModule():
    tu.tearDownModule()


def stop_on_move(number: int):
    """apply stops with a file error at the given move, before anything of that one moves."""
    real, calls = pa.move_one, []

    def move_one(record_dir, move):
        calls.append(move)
        return "an invented failure" if len(calls) == number else real(record_dir, move)

    return mock.patch.object(pa, "move_one", move_one)


class MalformedCorrectsTests(FolderCase):
    """Finding 1: a hand-made correction that names its earlier record by something other than a request id."""

    def test_every_tool_still_answers(self):
        write_record(self.pace, HAND, state="done", corrects="Record/20260902T010000Z--kowhai--act003.md")
        check = health(self.pace)
        self.assertNotEqual(check["status"], "not-checked", check["message"])
        self.assertTrue(any(HAND in item["message"] for item in check["findings"]))
        for extra in ([], ["--review"]):
            with self.subTest(view=extra):
                out, code = run(po, "--pace", str(self.pace), "--as-at", AS_AT, *extra)
                self.assertEqual(out["status"], "made", out)
        out, code = self.preview()
        self.assertIn(out["status"], ("ready", "not-ready"), out)
        history, _ = run(pr, "--pace", str(self.pace), "history", "--request", HAND)
        self.assertEqual(history["status"], "incomplete", history)


class UnreadArchiveRecordTests(FolderCase):
    """Finding 2: when the record of an archive cannot be read, its records are not each called moved there by hand."""

    def test_records_whose_archive_could_not_be_read_are_not_judged(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        (self.record / f"{out['record']}.md").write_bytes(b"\xff\xfe damaged while syncing")
        check = health(self.pace)
        by_hand = [item for item in check["findings"] if "moved there by hand" in item["message"]]
        self.assertEqual(by_hand, [])
        [waiting] = [item for item in check["findings"] if item["check"] == "archive"]
        self.assertEqual(waiting["level"], "note")
        self.assertIn("5 records in month folders", waiting["message"])
        self.assertIn("could not be read", waiting["message"])


class PartWayTests(FolderCase):
    """Finding 3: a record still directly in Record/ after a part-way stop still counts towards its month's digest."""

    def stopped(self):
        out, _ = self.preview()
        with stop_on_move(2):  # 2026/09 first: two of its four records... the first moves, the second stops it
            result, code = run(pa, "apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", out["plan"],
                               "--go-ahead", "Yes.", "--by", "Test")
        self.assertEqual((result["status"], result["moved"]), ("partly-archived", 1), result)
        return result

    def test_an_edit_to_a_moved_record_is_still_found(self):
        self.stopped()
        moved = next(path for path in (self.record / "2026/09").glob("*.md"))
        moved.write_text(read(moved).replace("Invented work.", "Edited."), encoding="utf-8")
        found = [item for item in health(self.pace)["findings"] if item["check"] == "archive"]
        self.assertTrue(any("has changed since" in item["message"] for item in found), found)

    def test_a_copy_of_a_waiting_record_in_its_month_folder_is_vouched_for(self):
        self.stopped()
        waiting = next(request for request in MOVING if (self.record / f"{request}.md").exists()
                       and pr.archive_folder(request) == "2026/09")
        (self.record / "2026/09" / f"{waiting}.md").write_bytes((self.record / f"{waiting}.md").read_bytes())
        [item] = [item for item in health(self.pace)["findings"] if "two places" in item["message"]]
        self.assertNotIn("No archive lists it there", item["fix"])
        self.assertIn("is the one archiving moved", item["fix"])


class RetryTests(FolderCase):
    """Finding 4: after a stop that moved nothing, the same plan and words can be applied again."""

    def test_a_retry_with_the_same_words_goes_ahead(self):
        out, _ = self.preview()
        args = ["apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", out["plan"], "--go-ahead", "Yes.",
                "--by", "Test"]
        with stop_on_move(1):
            first, code = run(pa, *args)
        self.assertEqual((first["status"], code, first["moved"]), ("not-archived", 1, 0), first)
        self.assertIn("Nothing was moved", first["message"])
        again, code = run(pa, *args)
        self.assertEqual((again["status"], code), ("archived", 0), again)


class LongStoryTests(FolderCase):
    """Finding 5: a story too long for one archive's record stays, and never holds up the rest."""

    def test_a_story_too_long_for_one_archive_stays(self):
        write_project(self.pace, LONG, "Statements")
        previous = None
        for number in range(1100):
            request = f"202607{1 + number // 100:02d}T{number % 24:02d}{number % 60:02d}00Z--{LONG}--s{number:05d}"
            fields = {"corrects": previous} if previous else {}
            write_record(self.pace, request, kind="note", subject="Long story", **fields)
            previous = request
        plan = self.plan()
        self.assertEqual(plan["stays"]["too_long"], 1)
        self.assertEqual(sorted(move["request"] for move in plan["moves"]), sorted(MOVING))
        out, code = self.archive()
        self.assertEqual((out["status"], code), ("archived", 0), out)


class UnreadableArchivedTests(FolderCase):
    """Finding 6: an archived record that is there but cannot be opened is not called missing."""

    def test_present_but_unreadable_is_not_missing(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        target = str(self.record / "2026/09" / f"{MOVING[2]}.md")
        real = pathlib.Path.read_bytes

        def read_bytes(path):
            if str(path) == target:
                raise PermissionError(13, "Permission denied", target)
            return real(path)

        with mock.patch.object(pathlib.Path, "read_bytes", read_bytes):
            found = [item for item in health(self.pace)["findings"] if MOVING[2] in item["message"]]
        self.assertTrue(found)
        self.assertFalse(any("is not in Record/2026/09/" in item["message"] for item in found), found)


class NoCtypesTests(unittest.TestCase):
    """Finding 7: a Python without ctypes still previews and archives."""

    def test_preview_runs_without_ctypes(self):
        code = ("import sys; sys.modules['ctypes'] = None; sys.argv = ['pace_archive.py', 'preview', '--pace', "
                f"{str(Path(__file__).resolve().parents[1] / 'example')!r}]; import runpy; "
                f"runpy.run_path({str(TOOLS / 'pace_archive.py')!r}, run_name='__main__')")
        done = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
        self.assertIn('"status": "nothing-to-archive"', done.stdout, done.stderr)


class WordingTests(FolderCase):
    """Finding 9."""

    def test_a_confirmation_is_named_where_it_is(self):
        act = self.pace / "1 Projects/Kowhai Books/Documents/Close.txt"
        act.write_text("September close: accepted.\n", encoding="utf-8")
        request = "20260801T010000Z--kowhai--conf03"
        write_record(self.pace, request, kind="confirmation", subject="September close", from_="owner",
                     words="Yes, that close is right.", source="The close file, shown in chat", act="Accept the close",
                     act_file="1 Projects/Kowhai Books/Documents/Close.txt", act_sha256=pr.sha256(act.read_bytes()),
                     place="2026/08")
        out, _ = pr.confirmation_state(self.pace, request)
        self.assertIn(f"Record/2026/08/{request}.md was read back", out["message"])

    def test_the_help_says_how_many_one_archive_moves(self):
        text = read(HELP / "records.md")
        self.assertNotIn("fewer when their project ids are long", text)
        self.assertIn("as many as the record of the archive can list", text)


if __name__ == "__main__":
    unittest.main()
