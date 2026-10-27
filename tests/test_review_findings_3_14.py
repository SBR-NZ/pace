"""Release 3.14.0's independent review: each finding has a test here that fails on the reviewed commit (64fc649).

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import datetime as dt
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

import test_updates as tu
from test_archive import (AS_AT, MOMENT, MOVING, OWNER, FolderCase, HELP, ADD_INS, clock, make_folder, pa, pc, po, pr,
                          pu, read, run, snapshot, write_record, write_project)

LONG = "kowhai-books-annual-financial-statements"  # 40 characters, the longest a project id can be


def setUpModule():
    tu.setUpModule()


def tearDownModule():
    tu.tearDownModule()


def health(pace: Path) -> dict:
    """The health check, judging 3 months from AS_AT."""
    judge = pc.po.Folder.archive_plan
    with mock.patch.object(pc.po.Folder, "archive_plan", lambda folder, moment=None: judge(folder, MOMENT)):
        out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(pace)]))
    return out


class FullBatchTests(unittest.TestCase):
    """Finding 1: a full batch must fit in the record of the archive, so the record is always saved."""

    def test_a_batch_of_long_project_ids_is_kept_to_what_one_record_can_list(self):
        self.assertEqual(len(LONG), pr.MAX_ID)
        with tempfile.TemporaryDirectory() as tmp, clock():
            pace = make_folder(Path(tmp))
            write_project(pace, LONG, "Statements")
            start = dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc)
            for number in range(1600):
                moment = start + dt.timedelta(minutes=number * 97)
                write_record(pace, f"{moment:%Y%m%dT%H%M%SZ}--{LONG}--n{number:05d}", kind="note", subject="Statement")
            preview, _ = run(pa, "preview", "--pace", str(pace), "--as-at", AS_AT)
            self.assertEqual(preview["status"], "ready", preview)
            self.assertGreater(preview["more"], 0)
            out, code = run(pa, "apply", "--pace", str(pace), "--as-at", AS_AT, "--plan", preview["plan"],
                            "--go-ahead", "Yes, archive them.", "--by", "Test")
            self.assertEqual((out["status"], code), ("archived", 0), {key: out[key] for key in ("status", "message")})
            record = pace / "Record" / f"{out['record']}.md"
            self.assertLessEqual(len(record.read_bytes()), pr.MAX_RECORD_BYTES)
            fields, body, _ = pr.parse(record.read_bytes())
            listed = sum(len(requests) for _, requests, _ in po.archive_lists(fields, body))
            self.assertEqual(listed, out["moved"])


class ImpossibleTimeTests(FolderCase):
    """Finding 2: one hand-made record whose request time is not a real date stops nothing; it is named and not read."""

    BAD = "20260931T221500Z--kowhai--bad001"

    def setUp(self):
        super().setUp()
        write_record(self.pace, "20260901T010000Z--kowhai--good01", kind="note", subject="Fine")
        path = self.record / f"{self.BAD}.md"
        (self.record / "20260901T010000Z--kowhai--good01.md").rename(path)
        path.write_text(read(path).replace("20260901T010000Z--kowhai--good01", self.BAD), encoding="utf-8")

    def test_every_tool_still_answers_and_names_the_file(self):
        check = health(self.pace)
        self.assertNotEqual(check["status"], "not-checked", check["message"])
        self.assertTrue(any(self.BAD in item["message"] and "not a real date and time" in item["message"]
                            for item in check["findings"]), check["findings"])
        review, code = run(po, "--pace", str(self.pace), "--review", "--as-at", AS_AT)
        self.assertEqual(review["status"], "made")
        preview, _ = self.preview()
        self.assertIn(preview["status"], ("ready", "not-ready"))
        found, _ = run(pr, "--pace", str(self.pace), "find")
        self.assertEqual(found["status"], "found")
        for command in ("read", "history"):
            with self.subTest(command=command):
                out, code = run(pr, "--pace", str(self.pace), command, "--request", self.BAD)
                self.assertEqual((out["status"], code), ("not-read", 1))
                self.assertIn("not a request id", out["message"])
        self.assertIn("the time in request is not a real date and time",
                      pr.record_problems(*pr.parse((self.record / f"{self.BAD}.md").read_bytes())[:2], self.BAD))

    def test_an_error_part_way_still_gives_one_answer_and_loses_nothing(self):
        out, _ = self.preview()
        real, calls = pa.move_one, []

        def move_one(record_dir, move):
            calls.append(move)
            if len(calls) == 2:
                raise RuntimeError("invented failure")
            return real(record_dir, move)

        with mock.patch.object(pa, "move_one", move_one):
            result, code = run(pa, "apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", out["plan"],
                               "--go-ahead", "Yes.", "--by", "Test")
        self.assertEqual(code, 1)
        self.assertIn("invented failure", result["message"])
        # Every record is whole and in one place, and the record of the archive was saved before anything moved.
        for request in MOVING:
            places = [self.record / f"{request}.md", self.record / pr.archive_folder(request) / f"{request}.md"]
            self.assertEqual(sum(place.exists() for place in places), 1, request)
        archives = [path for path in self.record.glob("*.md") if "Records archived" in read(path)]
        self.assertEqual(len(archives), 1)
        check = health(self.pace)
        self.assertEqual([item for item in check["findings"] if item["level"] == "problem" and self.BAD not in
                          item["message"] and item["check"] in ("archive", "record-files", "records")], [])
        [waiting] = [item for item in check["findings"] if item["check"] == "archive"]
        self.assertEqual(waiting["level"], "note")
        self.assertIn("still directly in Record/", waiting["message"])


class UnlistedTests(FolderCase):
    """Finding 3: a record in a month folder that no archive lists, and a list that no longer adds up, are named."""

    def test_a_record_moved_into_a_month_folder_by_hand_is_named(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        open_one = "20260902T010000Z--kowhai--act003"
        target = self.record / pr.archive_folder(open_one)
        target.mkdir(parents=True, exist_ok=True)
        (self.record / f"{open_one}.md").rename(target / f"{open_one}.md")
        found = [item for item in health(self.pace)["findings"] if open_one in item["message"]]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["level"], "problem")
        self.assertIn("no archive lists it", found[0]["message"])
        self.assertIn("move it back directly into Record/, changing nothing in it", found[0]["fix"])

    def test_a_list_that_no_longer_adds_up_is_named(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        record = self.record / f"{out['record']}.md"
        record.write_text(read(record).replace("Record/2026/09/ - 4 records", "Record/2026/09/ - 5 records"),
                          encoding="utf-8")
        found = [item for item in health(self.pace)["findings"] if item["check"] == "archive"]
        self.assertTrue(any("does not add up" in item["message"] for item in found), found)


class TwoPlacesTests(FolderCase):
    """Finding 4: one record in two places gets one finding, and the fix keeps the copy the archive vouches for."""

    def test_the_same_record_in_two_places(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        archived = self.record / pr.archive_folder(MOVING[2]) / f"{MOVING[2]}.md"
        shutil.copy(archived, self.record / f"{MOVING[2]}.md")
        found = [item for item in health(self.pace)["findings"] if MOVING[2] in item["message"]]
        self.assertEqual(len(found), 1, found)
        self.assertIn("one record in two places", found[0]["message"])
        self.assertIn(f"move Record/{MOVING[2]}.md out of Record/", found[0]["fix"])
        self.assertIn("is the one archiving moved", found[0]["fix"])

    def test_two_different_copies_say_which_one_the_archive_vouches_for(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        archived = self.record / pr.archive_folder(MOVING[2]) / f"{MOVING[2]}.md"
        (self.record / f"{MOVING[2]}.md").write_text(read(archived).replace("Invented work.", "Other words."),
                                                     encoding="utf-8")
        [item] = [item for item in health(self.pace)["findings"] if MOVING[2] in item["message"]]
        self.assertIn(f"Record/{pr.archive_folder(MOVING[2])}/{MOVING[2]}.md matches the record of the archive that "
                      "moved it", item["fix"])


class LeftoverTests(FolderCase):
    """Finding 5: a save's leftover copy of a record that has since been archived stays housekeeping."""

    def test_a_leftover_copy_of_an_archived_record_is_still_housekeeping(self):
        shutil.copy(self.record / f"{MOVING[2]}.md", self.record / f".pace-tmp-{MOVING[2]}-4242-0a1b2c3d")
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        review, _ = run(po, "--pace", str(self.pace), "--review", "--as-at", AS_AT)
        self.assertTrue(review["complete"], review["could_not_read"])
        [leftover] = [item for item in health(self.pace)["findings"] if ".pace-tmp-" in item["message"]]
        self.assertEqual(leftover["level"], "note")
        self.assertIn("whose record is beside it, or in its month folder once archived,",
                      read(ADD_INS / "Project overview/ADD-IN.md"))


class NotReadTests(FolderCase):
    """Finding 6: anything in Record/ that was not read makes every answer that could depend on it unsettled."""

    def test_a_folder_of_their_own_in_record(self):
        # Record/Old/ holds a correction that opens the done action again.
        write_record(self.pace, "20261110T010000Z--kowhai--act020", state="open", corrects=MOVING[1], place="Old")
        preview, code = self.preview()
        self.assertEqual((preview["status"], code), ("not-ready", 1))
        self.assertIn("Record/Old", preview["message"])
        history, _ = run(pr, "--pace", str(self.pace), "history", "--request", MOVING[0])
        self.assertEqual(history["status"], "incomplete")
        found, _ = run(pr, "--pace", str(self.pace), "find")
        self.assertFalse(found["coverage"]["complete"])
        update, code = run(pr, "--pace", str(self.pace), "update-action", "--request", "20270126T010000Z--kowhai--act021",
                           "--corrects", "20260902T010000Z--kowhai--act003", "--state", "done", "--from", "owner",
                           "--words", "Done.", "--by", "Test")
        self.assertEqual((update["status"], code), ("not-saved", 1))
        self.assertIn("Record/Old/", update["message"])

    def test_a_record_out_of_its_month_folder(self):
        write_record(self.pace, "20260815T010000Z--kowhai--act022", state="open", corrects=MOVING[1], place="2026/09")
        history, _ = run(pr, "--pace", str(self.pace), "history", "--request", MOVING[0])
        self.assertEqual(history["status"], "incomplete")
        update, code = run(pr, "--pace", str(self.pace), "update-action", "--request", "20270126T010000Z--kowhai--act023",
                           "--corrects", "20260902T010000Z--kowhai--act003", "--state", "done", "--from", "owner",
                           "--words", "Done.", "--by", "Test")
        self.assertEqual((update["status"], code), ("not-saved", 1))

    def test_a_month_folder_that_refuses_access(self):
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        month = str(self.record / "2026/09")
        real_exists, real_read = pathlib.Path.exists, pathlib.Path.read_bytes

        def refused(real):
            def check(path, *args, **kwargs):
                if str(path).startswith(month):
                    raise PermissionError(13, "Permission denied", str(path))
                return real(path, *args, **kwargs)
            return check

        with mock.patch.object(pathlib.Path, "exists", refused(real_exists)), \
                mock.patch.object(pathlib.Path, "read_bytes", refused(real_read)):
            for command in ("read", "history"):
                with self.subTest(command=command):
                    result, code = run(pr, "--pace", str(self.pace), command, "--request", MOVING[2])
                    self.assertEqual((result["status"], code), ("unreadable", 1), result)
                    self.assertIn("could not be opened", result["message"])


class CrossProjectTests(FolderCase):
    """Finding 7: a story with a record that cannot be relied on stays, whichever project it is in."""

    def test_a_correction_saved_in_another_project_keeps_its_story_in_record(self):
        stray = "20260903T020000Z--kowhai--wrong1"
        write_record(self.pace, stray, kind="decision", subject="Budget basis", from_="owner", words="No, this year's.",
                     corrects=MOVING[2])
        moving = {move["request"] for move in self.plan()["moves"]}
        self.assertNotIn(MOVING[2], moving)
        self.assertNotIn(stray, moving)


class RenameTests(FolderCase):
    """Finding 8: a file that appears in the month folder at the last moment is never replaced."""

    def test_a_late_arrival_in_the_month_folder_is_never_replaced(self):
        move = next(move for move in self.plan()["moves"] if move["request"] == MOVING[2])
        target = self.record / move["to"]
        target.parent.mkdir(parents=True)
        target.write_text("A copy that arrived at the last moment.\n", encoding="utf-8")
        before = (self.record / move["from"]).read_bytes()
        real_exists, real_lexists = pathlib.Path.exists, os.path.lexists
        with mock.patch.object(pathlib.Path, "exists", lambda path, *a, **k: False if path == target else
                               real_exists(path, *a, **k)), \
                mock.patch.object(pathlib.Path, "is_symlink", lambda path: False), \
                mock.patch.object(os.path, "lexists", lambda path: False if str(path) == str(target) else
                                  real_lexists(path)):
            problem = pa.move_one(self.record, move)
        self.assertTrue(problem)
        self.assertEqual(target.read_text(encoding="utf-8"), "A copy that arrived at the last moment.\n")
        self.assertEqual((self.record / move["from"]).read_bytes(), before)


class FutureTests(FolderCase):
    """Finding 9: apply judges 3 months from now at the latest, never from a moment still to come."""

    def test_apply_refuses_a_moment_still_to_come(self):
        out, _ = self.preview()
        before = snapshot(self.pace)
        with mock.patch.object(pa, "now", return_value=MOMENT - dt.timedelta(days=30), create=True):
            result, code = run(pa, "apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", out["plan"],
                               "--go-ahead", "Yes.", "--by", "Test")
        self.assertEqual((result["status"], code), ("not-archived", 1))
        self.assertIn("is still to come", result["message"])
        self.assertEqual(snapshot(self.pace), before)


class WordingTests(FolderCase):
    """Finding 10: the smaller gaps."""

    def test_the_help_lists_every_kind_of_finished_work_and_says_when_apply_refuses(self):
        text = read(HELP / "records.md")
        self.assertIn("or any other kind of record but a project change, such as a decision, a note, a result, a figure "
                      "or a confirmation", text)
        self.assertNotIn("or a day passing", text)
        self.assertIn("If what would move has changed since the preview", text)
        self.assertIn("including the year and month folders inside `Record/`",
                      read(ADD_INS / "Key numbers and changes/ADD-IN.md"))
        self.assertIn("including the year and month folders inside `Record/`", read(ADD_INS / "What was reported/ADD-IN.md"))

    def test_one_record_is_said_as_one(self):
        for request in MOVING[:2] + MOVING[3:]:
            (self.record / f"{request}.md").unlink()
        out, _ = self.preview()
        self.assertIn("Archiving would move 1 record, the story of 1 item of finished work", out["message"])

    def test_the_updater_names_an_archived_confirmation_where_it_is(self):
        proposal = self.pace / "Release record/Proposals/2026-08-01-v3.14.0.json"
        proposal.parent.mkdir(parents=True, exist_ok=True)
        proposal.write_bytes(b'{"invented": "install act"}\n')
        request = "20260801T010000Z--none--conf02"
        write_record(self.pace, request, kind="confirmation", subject="Install", from_="owner", words="Yes, install it.",
                     source="The preview, shown in chat", act="Install this pinned release",
                     act_file="Release record/Proposals/2026-08-01-v3.14.0.json", act_sha256=pr.sha256(proposal.read_bytes()),
                     place="2026/08")
        self.assertEqual(pu._check_confirmation(self.pace, request, proposal.read_bytes()), f"Record/2026/08/{request}.md")

    def test_the_updater_finds_the_marker_it_relies_on(self):
        self.assertIn(pu.ARCHIVE_READER, (pr.__file__ and Path(pr.__file__).read_bytes()))


if __name__ == "__main__":
    unittest.main()
