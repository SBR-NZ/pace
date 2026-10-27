"""Archiving finished work (3.14.0): records moved, unchanged, into Record/<year>/<month>/ on the owner's yes, and every
tool reading them wherever they are.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

import test_updates as tu

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
EXAMPLE = ROOT / "example"
TOOLS = PACE_FOLDER / "Product/Tools"
HELP = PACE_FOLDER / "Product/Help"
ADD_INS = PACE_FOLDER / "Product/Pace add-ins"


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_for_archive_tests", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pa = load_tool("pace_archive")
po, pr = pa.po, pa.pr
pc = load_tool("pace_check")
pu = pc.pu

# As at 26 January 2027 in Auckland, which is 25 January in UTC: finished work from before 25 October 2026 can move.
AS_AT = "2027-01-26T09:00:00+13:00"
MOMENT = pr.parse_time(AS_AT)
LATER = MOMENT + dt.timedelta(minutes=1)


def clock():
    """Now is just after AS_AT, so archiving as at AS_AT judges from a moment that has come."""
    return mock.patch.object(pa, "now", return_value=LATER, create=True)
OWNER = "Rangi Parata"
RECORD_CHECKS = ("archive", "record-files", "records", "corrections")
MOVING = ["20260901T010000Z--kowhai--act001", "20261005T010000Z--kowhai--act002",
          "20260903T010000Z--kowhai-budget--dec001", "20260907T010000Z--kowhai-budget--not001",
          "20260908T010000Z--kowhai-budget--not002"]


def setUpModule():
    tu.setUpModule()  # git for the invented release repository


def tearDownModule():
    tu.tearDownModule()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_record(pace: Path, request: str, kind: str = "action", subject: str = "Board pack", body: str = "Invented work.",
                 place: str = "", **fields) -> Path:
    match = pr.REQUEST.match(request)
    moment = pr.request_time(request)
    lines = ["---", "format: record-1", f"request: {request}", f"created: {moment.isoformat()}",
             f"project: {match.group(2)}", f"kind: {kind}", f"subject: {subject}"]
    if "from_" not in fields:
        lines.append("from: agent")
    lines += [f"{'from' if key == 'from_' else key.replace('_', '-')}: {value}" for key, value in fields.items()]
    lines.append("by: Test")
    path = pace / "Record" / place / f"{request}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines + ["---", "", body, ""]), encoding="utf-8")
    return path


def write_project(pace: Path, pid: str, folder: str, parent: str = "none") -> None:
    (pace / "1 Projects" / folder / "Documents").mkdir(parents=True, exist_ok=True)
    (pace / "1 Projects" / folder / "Pace project.md").write_text(
        f"---\nformat: project-1\nid: {pid}\nparent: {parent}\ncreated: 2026-08-01T09:00:00+12:00\nby: Test\n---\n\n"
        "Invented work.\n", encoding="utf-8")


def make_folder(base: Path) -> Path:
    """A Pace folder with eight invented stories; five records in three of them are ready to archive as at AS_AT."""
    pace = base / "PACE"
    shutil.copytree(PACE_FOLDER, pace, ignore=shutil.ignore_patterns("__pycache__"))
    text = read(pace / "Pace.md")
    mark = "<!-- Your lines go below this one. Pace updates never change them. -->"
    text = text.replace(f"{mark}\n## Time zone", f"{mark}\nOwner: {OWNER}\n\n## Time zone")
    text = text.replace(f"{mark}\n## Help", f"{mark}\nTime zone: Pacific/Auckland\n\n## Help")
    (pace / "Pace.md").write_text(text, encoding="utf-8")
    write_project(pace, "kowhai", "Kowhai Books")
    write_project(pace, "kowhai-budget", "Kowhai Books/Budget 2027", parent="kowhai")
    # A: done, its whole story old: moves, each record to its own month folder.
    write_record(pace, MOVING[0], owed_by=OWNER, state="open", due="2026-09-20")
    write_record(pace, MOVING[1], owed_by=OWNER, state="done", due="2026-09-20", corrects=MOVING[0])
    # B: open work, however old, stays.
    write_record(pace, "20260902T010000Z--kowhai--act003", subject="Supplier call", owed_by="Ana Ruiz", state="open")
    # C: a decision: moves.
    write_record(pace, MOVING[2], kind="decision", subject="Budget basis", from_="owner", words="Use last year's actuals.")
    # D: a project change stays: it holds the project's status.
    write_record(pace, "20260904T010000Z--kowhai-budget--chg001", kind="change", subject="Budget 2027", status="On track")
    # E: done, but its last record is recent: stays.
    write_record(pace, "20260905T010000Z--kowhai--act004", subject="Site copy", owed_by=OWNER, state="open")
    write_record(pace, "20261101T010000Z--kowhai--act005", subject="Site copy", owed_by=OWNER, state="done",
                 corrects="20260905T010000Z--kowhai--act004")
    # F: recorded two ways: stays.
    write_record(pace, "20260906T010000Z--kowhai--act006", subject="Logo", owed_by=OWNER, state="open")
    write_record(pace, "20260906T020000Z--kowhai--act007", subject="Logo", owed_by=OWNER, state="done",
                 corrects="20260906T010000Z--kowhai--act006")
    write_record(pace, "20260906T030000Z--kowhai--act008", subject="Logo", owed_by=OWNER, state="cancelled",
                 corrects="20260906T010000Z--kowhai--act006")
    # G: withdrawn: moves.
    write_record(pace, MOVING[3], kind="note", subject="Venue")
    write_record(pace, MOVING[4], kind="withdrawal", subject="Venue", corrects=MOVING[3], body="Not so after all.")
    # H: a recent note stays.
    write_record(pace, "20261201T010000Z--kowhai--not003", kind="note", subject="Holiday hours")
    return pace


def snapshot(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns) if path.is_file() else "folder"
            for path in sorted(root.rglob("*"))}


def run(module, *argv) -> tuple:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = module.main(list(argv))
    return json.loads(output.getvalue()), code


class FolderCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-archive-")
        self.base = Path(self._temp.name)
        self.pace = make_folder(self.base)
        self.record = self.pace / "Record"
        self._clock = clock()
        self._clock.start()

    def tearDown(self):
        self._clock.stop()
        self._temp.cleanup()

    def folder(self):
        return po.Folder(self.pace, [OWNER], None, zone_problem_ok=True)

    def plan(self, moment=MOMENT):
        return self.folder().archive_plan(moment)

    def preview(self, *extra):
        return run(pa, "preview", "--pace", str(self.pace), "--as-at", AS_AT, *extra)

    def archive(self, words="Yes, archive those."):
        out, code = self.preview()
        self.assertEqual((out["status"], code), ("ready", 0), out)
        return run(pa, "apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", out["plan"], "--go-ahead", words,
                   "--by", "Test")


class PlanTests(FolderCase):
    def test_finished_stories_move_whole_and_the_rest_stays_with_its_reason(self):
        plan = self.plan()
        self.assertEqual(sorted(move["request"] for move in plan["moves"]), sorted(MOVING))
        for move in plan["moves"]:
            stamp = move["request"][:6]
            self.assertEqual((move["from"], move["to"]), (f"{move['request']}.md",
                                                          f"{stamp[:4]}/{stamp[4:]}/{move['request']}.md"))
            self.assertEqual(move["sha256"], pr.sha256((self.record / move["from"]).read_bytes()))
        self.assertEqual((plan["stories"], plan["more"], plan["cutoff"]), (3, 0, dt.date(2026, 10, 25)))
        self.assertEqual(plan["stays"], {"open": 1, "two_ways": 1, "project_changes": 1, "unsettled": 0, "recent": 2,
                                         "too_long": 0})

    def test_three_months_count_from_the_newest_record_in_a_story(self):
        later = dt.datetime(2027, 2, 2, tzinfo=dt.timezone.utc)  # three months after act005, made on 1 November 2026
        moving = {move["request"] for move in self.plan(later)["moves"]}
        self.assertIn("20260905T010000Z--kowhai--act004", moving)
        self.assertIn("20261101T010000Z--kowhai--act005", moving)
        self.assertNotIn("20260905T010000Z--kowhai--act004", {move["request"] for move in self.plan()["moves"]})

    def test_the_cutoff_is_the_same_day_three_months_back_in_utc(self):
        self.assertEqual(po.months_before(dt.date(2026, 5, 31), 3), dt.date(2026, 2, 28))
        self.assertEqual(po.months_before(dt.date(2024, 5, 31), 3), dt.date(2024, 2, 29))
        self.assertEqual(po.months_before(dt.date(2027, 1, 25), 3), dt.date(2026, 10, 25))
        write_record(self.pace, "20261024T235959Z--kowhai--edge01", kind="note", subject="Just old enough")
        write_record(self.pace, "20261025T000000Z--kowhai--edge02", kind="note", subject="Just too new")
        moving = {move["request"] for move in self.plan()["moves"]}
        self.assertIn("20261024T235959Z--kowhai--edge01", moving)
        self.assertNotIn("20261025T000000Z--kowhai--edge02", moving)

    def test_a_project_with_a_file_that_cannot_be_relied_on_keeps_all_its_work(self):
        """Such a file could be a correction of any item in its project, so none of them is settled."""
        cases = {
            "an unreadable record": lambda: (self.record / "20260920T010000Z--kowhai--bad001.md")
            .write_bytes(b"\xff\xfe not text"),
            "a second copy": lambda: shutil.copy(self.record / f"{MOVING[0]}.md", self.record / f"{MOVING[0]} (1).md"),
        }
        for case, make in cases.items():
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                make()
                plan = self.plan()
                self.assertEqual(sorted(move["request"] for move in plan["moves"]), sorted(MOVING[2:]), case)
                self.assertEqual(plan["stays"]["unsettled"], 5)  # every item in kowhai: A, B, E, F and H

    def test_a_story_with_a_missing_record_stays(self):
        write_record(self.pace, "20260910T010000Z--kowhai--act009", state="done",
                     corrects="20260801T010000Z--kowhai--gone01")
        plan = self.plan()
        self.assertEqual(sorted(move["request"] for move in plan["moves"]), sorted(MOVING))
        self.assertEqual(plan["stays"]["unsettled"], 1)

    def test_corrections_that_loop_stay(self):
        write_record(self.pace, "20260911T010000Z--kowhai-budget--loop01", kind="note", subject="Loop",
                     corrects="20260911T020000Z--kowhai-budget--loop02")
        write_record(self.pace, "20260911T020000Z--kowhai-budget--loop02", kind="note", subject="Loop",
                     corrects="20260911T010000Z--kowhai-budget--loop01")
        plan = self.plan()
        self.assertNotIn("20260911T010000Z--kowhai-budget--loop01", {move["request"] for move in plan["moves"]})
        self.assertEqual(plan["stays"]["unsettled"], 1)

    def test_one_archive_moves_whole_stories_oldest_first_up_to_its_limit(self):
        with mock.patch.object(po, "ARCHIVE_BATCH", 2):
            plan = self.plan()
        # The decision (3 September) fits; the withdrawn note's story (to 8 September) would not, so it and the
        # done action's story (to 5 October) wait for the next archive.
        self.assertEqual([move["request"] for move in plan["moves"]], [MOVING[2]])
        self.assertEqual((plan["stories"], plan["more"]), (1, 4))


class ArchiveToolTests(FolderCase):
    def test_preview_changes_nothing_and_says_what_would_move(self):
        before = snapshot(self.pace)
        out, code = self.preview()
        self.assertEqual(snapshot(self.pace), before)
        self.assertEqual((out["status"], code, out["moves"], out["stories"]), ("ready", 0, 5, 3))
        self.assertEqual(out["months"], {"2026/09": 4, "2026/10": 1})
        self.assertRegex(out["plan"], r"^[0-9a-f]{64}$")
        for phrase in ("Archiving would move 5 records, the stories of 3 items of finished work with all their records "
                       "from before 25 October 2026", "Record/2026/09/ (4), Record/2026/10/ (1)",
                       "Record/ itself would go from 13 to 8 records",
                       "Staying in Record/: 1 open, 1 recorded two ways, 1 project change and 2 with a record from the "
                       "last 3 months", "Nothing was moved.", "on their yes in their own words, run apply"):
            self.assertIn(phrase, out["message"])

    def test_apply_moves_exactly_the_plan_unchanged_and_keeps_a_record_of_it(self):
        moving = {request: (self.record / f"{request}.md").read_bytes() for request in MOVING}
        staying = {path.name: path.read_bytes() for path in self.record.glob("*.md") if path.stem not in moving}
        out, code = self.archive("Yes, archive those five.")
        self.assertEqual((out["status"], code, out["moved"], out["planned"]), ("archived", 0, 5, 5), out)
        for request, data in moving.items():
            self.assertFalse((self.record / f"{request}.md").exists())
            self.assertEqual((self.record / pr.archive_folder(request) / f"{request}.md").read_bytes(), data)
        for name, data in staying.items():
            self.assertEqual((self.record / name).read_bytes(), data)
        # The record of it: a note from the owner, with their words, saved directly in Record/ and read back.
        record = self.record / f"{out['record']}.md"
        self.assertEqual(out["file"], f"Record/{out['record']}.md")
        fields, body, _ = pr.parse(record.read_bytes())
        self.assertEqual([pr.one(fields, key) for key in ("project", "kind", "subject", "from", "words", "by")],
                         ["none", "note", "Records archived", "owner", "Yes, archive those five.", "Test"])
        lists = po.archive_lists(fields, body)
        self.assertEqual([(month, sorted(requests)) for month, requests, _ in lists],
                         [("2026/09", sorted(MOVING[:1] + MOVING[2:])), ("2026/10", MOVING[1:2])])
        for month, requests, digest in lists:
            lines = [(request, pr.sha256(moving[request])) for request in requests]
            self.assertEqual(digest, pr.sha256("".join(f"{r} {d}\n" for r, d in lines).encode("utf-8")))
        self.assertIn("Anyone can work it out again to check that nothing has changed.", body)
        # Nothing more is ready, and the health check finds the folder healthy, every archived record checked.
        again, _ = self.preview()
        self.assertEqual(again["status"], "nothing-to-archive")
        check, code = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        self.assertEqual([item for item in check["findings"] if item["check"] in RECORD_CHECKS], [])
        self.assertIn("Archived records: 5 records checked against the records of the archives that moved them.",
                      check["checked"])

    def test_apply_needs_the_previewed_plan_and_the_owners_words(self):
        out, _ = self.preview()
        before = snapshot(self.pace)
        args = ["apply", "--pace", str(self.pace), "--as-at", AS_AT, "--by", "Test"]
        wrong, code = run(pa, *args, "--plan", "0" * 64, "--go-ahead", "Yes.")
        self.assertEqual((wrong["status"], code), ("plan-changed", 1))
        silent, code = run(pa, *args, "--plan", out["plan"], "--go-ahead", "  ")
        self.assertEqual((silent["status"], code), ("not-archived", 1))
        self.assertEqual(snapshot(self.pace), before)
        # A record saved after the preview changes the plan, so nothing moves on the old one.
        write_record(self.pace, "20260912T010000Z--kowhai--act010", subject="Late arrival", state="done")
        changed, code = run(pa, *args, "--plan", out["plan"], "--go-ahead", "Yes.")
        self.assertEqual((changed["status"], code), ("plan-changed", 1))
        self.assertIn("Nothing was moved", changed["message"])
        self.assertTrue((self.record / f"{MOVING[0]}.md").is_file())

    def test_a_failed_move_stops_with_every_record_whole_and_in_one_place(self):
        out, _ = self.preview()
        data = {request: (self.record / f"{request}.md").read_bytes() for request in MOVING}
        real = getattr(pa, "_rename_no_replace", os.rename)
        calls = []

        def rename(source, target):
            calls.append(source)
            if len(calls) == 3:
                raise PermissionError(13, "Permission denied", str(source))
            return real(source, target)

        moves = (mock.patch.object(pa, "_rename_no_replace", rename) if hasattr(pa, "_rename_no_replace") else
                 mock.patch.object(pa.os, "rename", rename))
        with moves:
            result, code = run(pa, "apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", out["plan"],
                               "--go-ahead", "Yes.", "--by", "Test")
        self.assertEqual((result["status"], code, result["moved"]), ("partly-archived", 1, 2), result)
        self.assertIn("could not be moved", result["message"])
        self.assertIn("Preview again to archive the rest", result["message"])
        for request, content in data.items():
            places = [self.record / f"{request}.md", self.record / pr.archive_folder(request) / f"{request}.md"]
            there = [place for place in places if place.exists()]
            self.assertEqual(len(there), 1, request)
            self.assertEqual(there[0].read_bytes(), content)
        # The record of the archive was saved before anything moved, so it lists all five.
        fields, body, _ = pr.parse((self.record / f"{result['record']}.md").read_bytes())
        self.assertEqual(sum(len(requests) for _, requests, _ in po.archive_lists(fields, body)), 5)
        rest, _ = self.preview()
        self.assertEqual((rest["status"], rest["moves"]), ("ready", 3))

    def test_a_file_already_in_the_month_folder_is_never_replaced(self):
        move = next(move for move in self.plan()["moves"] if move["request"] == MOVING[2])
        target = self.record / move["to"]
        target.parent.mkdir(parents=True)
        target.write_text("Something else.\n", encoding="utf-8")
        before = (self.record / move["from"]).read_bytes()
        self.assertIn("is already there", pa.move_one(self.record, move))
        self.assertEqual(((self.record / move["from"]).read_bytes(), target.read_text(encoding="utf-8")),
                         (before, "Something else.\n"))

    def test_nothing_moves_while_a_month_folder_has_a_problem(self):
        write_record(self.pace, "20260801T010000Z--kowhai--lost01", kind="note", subject="Moved by hand", place="2026/09")
        out, code = self.preview()
        self.assertEqual((out["status"], code), ("not-ready", 1))
        self.assertIn("is not in the folder for the year and month in its request id, Record/2026/08/", out["message"])
        result, code = run(pa, "apply", "--pace", str(self.pace), "--as-at", AS_AT, "--plan", "0" * 64, "--go-ahead",
                           "Yes.", "--by", "Test")
        self.assertEqual((result["status"], code), ("not-archived", 1))
        self.assertTrue((self.record / f"{MOVING[0]}.md").is_file())


class SameAnswersTests(FolderCase):
    """Archiving changes where records are, never what the tools say about them."""

    def answers(self, pace: Path) -> dict:
        out = {}
        for name, extra in (("every", []), ("person", ["--by-person"]), ("project", ["--project", "kowhai"]),
                            ("review", ["--review"])):
            result, _ = run(po, "--pace", str(pace), "--as-at", AS_AT, *extra)
            out[name] = {key: value for key, value in result.items()
                         if key not in ("searched", "archive_ready", "archive_suggested", "message")}
        found, _ = run(pr, "--pace", str(pace), "find", "--subject", "Board pack")
        out["find"] = sorted(record["request"] for record in found["records"])
        history, _ = run(pr, "--pace", str(pace), "history", "--request", MOVING[0])
        out["history"] = (history["status"], history["current"], sorted(history["corrections"]))
        return out

    def test_every_view_says_the_same_after_archiving(self):
        before = self.answers(self.pace)
        out, code = self.archive()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.answers(self.pace), before)

    def test_the_page_differs_only_in_what_was_searched(self):
        other = self.base / "other"
        shutil.copytree(self.pace, other)
        self.archive()
        pages = []
        for pace in (other, self.pace):
            result, code = run(po, "--pace", str(pace), "--as-at", AS_AT, "--save")
            self.assertEqual((result["status"], code), ("saved", 0), result)
            pages.append(read(pace / result["page"]).splitlines())
        differ = [(a, b) for a, b in zip(*pages) if a != b]
        self.assertEqual(len(pages[0]), len(pages[1]))
        self.assertEqual(len(differ), 1, differ)
        self.assertIn("All 13 record files in Record/, each opened", differ[0][0])
        self.assertIn("All 14 record files in Record/ and its year and month folders, each opened", differ[0][1])


class RecordToolTests(FolderCase):
    def setUp(self):
        super().setUp()
        out, code = self.archive()
        self.assertEqual(code, 0, out)

    def tool(self, *argv):
        return run(pr, "--pace", str(self.pace), *argv)

    def test_an_archived_record_is_read_from_its_month_folder(self):
        out, code = self.tool("read", "--request", MOVING[2])
        self.assertEqual((out["status"], code, out["record"]["file"]),
                         ("found", 0, f"Record/2026/09/{MOVING[2]}.md"))
        self.assertEqual(out["record"]["request"], MOVING[2])
        out, _ = self.tool("history", "--request", MOVING[0])
        self.assertEqual((out["status"], out["current"]), ("found", [MOVING[1]]))
        self.assertEqual([version["file"] for version in out["versions"]],
                         [f"Record/2026/09/{MOVING[0]}.md", f"Record/2026/10/{MOVING[1]}.md"])

    def test_a_correction_of_an_archived_record_is_saved_directly_in_record(self):
        request = "20270126T010000Z--kowhai--act011"
        out, code = self.tool("create", "--request", request, "--project", "kowhai", "--kind", "action", "--subject", "Board pack",
                              "--from", "owner", "--words", "Open it again.", "--by", "Test", "--state", "open",
                              "--owed-by", OWNER, "--corrects", MOVING[1], "--body", "Reopened.")
        self.assertEqual((out["status"], code, out["file"]), ("saved", 0, f"Record/{request}.md"), out)
        # The archived account is no longer current, so it cannot be corrected again; the new one can.
        again, code = self.tool("create", "--request", "20270126T020000Z--kowhai--act012", "--project", "kowhai", "--kind", "action",
                                "--subject", "Board pack", "--from", "owner", "--words", "Done after all.", "--by", "Test",
                                "--state", "done", "--corrects", MOVING[1], "--body", "Done.")
        self.assertEqual((again["status"], code), ("not-saved", 1))
        self.assertIn(f"was already corrected by {request}", again["message"])
        update, code = self.tool("update-action", "--request", "20270126T030000Z--kowhai--act013", "--corrects", request,
                                 "--state", "done", "--from", "owner", "--words", "Done now.", "--by", "Test")
        self.assertEqual((update["status"], code), ("saved", 0), update)
        history, _ = self.tool("history", "--request", MOVING[0])
        self.assertEqual(history["current"], ["20270126T030000Z--kowhai--act013"])

    def test_a_retry_of_a_save_since_archived_is_already_saved(self):
        out, code = self.tool("create", "--request", MOVING[2], "--project", "kowhai-budget", "--kind", "decision",
                              "--subject", "Budget basis",
                              "--from", "owner", "--words", "Use last year's actuals.", "--by", "Test",
                              "--body", "Invented work.")
        self.assertEqual((out["status"], code), ("already-saved", 0), out)
        self.assertEqual(out["file"], f"Record/2026/09/{MOVING[2]}.md")
        self.assertFalse((self.record / f"{MOVING[2]}.md").exists())

    def test_find_and_a_kept_listing_cover_the_month_folders(self):
        out, _ = self.tool("find", "--project", "kowhai-budget")
        self.assertEqual({record["file"] for record in out["records"]} & {f"Record/2026/09/{MOVING[2]}.md"},
                         {f"Record/2026/09/{MOVING[2]}.md"})
        self.assertTrue(out["coverage"]["complete"])
        listing = self.base / "listing.json"
        other = self.base / "before"
        shutil.copytree(self.pace, other)
        for request in MOVING:  # the folder as it was before the archive
            (other / "Record" / pr.archive_folder(request) / f"{request}.md").rename(other / "Record" / f"{request}.md")
        saved, _ = run(pr, "--pace", str(other), "listing", "--save", str(listing))
        self.assertEqual(saved["status"], "saved")
        compared, code = self.tool("listing", "--compare", str(listing))
        self.assertEqual((compared["status"], code, compared["missing"], compared["changed"]), ("matches", 0, [], []))
        self.assertEqual(compared["archived"], sorted(f"{request}.md" for request in MOVING))
        self.assertIn("5 file(s) are now in their year and month folders, moved there by archiving.", compared["message"])

    def test_an_archived_confirmation_still_confirms_its_act(self):
        act = self.pace / "1 Projects/Kowhai Books/Documents/Close.txt"
        act.write_text("September close: accepted.\n", encoding="utf-8")
        request = "20260801T010000Z--kowhai--conf01"
        write_record(self.pace, request, kind="confirmation", subject="September close", from_="owner",
                     words="Yes, that close is right.", source="The close file, shown in chat", act="Accept the close",
                     act_file="1 Projects/Kowhai Books/Documents/Close.txt",
                     act_sha256=pr.sha256(act.read_bytes()), place="2026/08")
        out, code = pr.confirmation_state(self.pace, request)
        self.assertEqual((out["status"], code), ("confirmed", 0), out)


class ScanTests(FolderCase):
    def test_what_does_not_belong_in_the_month_folders_is_named_and_not_read(self):
        (self.record / "2026/09").mkdir(parents=True)
        write_record(self.pace, "20260801T010000Z--kowhai--lost01", kind="note", subject="Moved", place="2026/09")
        write_record(self.pace, "20260801T020000Z--kowhai--lost02", kind="note", subject="Loose", place="2026")
        (self.record / "2026/notes").mkdir()
        (self.record / "2026/09/inner").mkdir()
        (self.record / "Old").mkdir()
        names, copies, issues = pr.scan_record_names(self.record)
        self.assertNotIn("20260801T010000Z--kowhai--lost01", names)
        found = {issue["file"]: issue for issue in issues}
        self.assertEqual(found["2026/09/20260801T010000Z--kowhai--lost01.md"]["type"], "misplaced-record")
        self.assertEqual(found["2026/20260801T020000Z--kowhai--lost02.md"]["type"], "misplaced-record")
        self.assertIn("Record/2026/08/, so it was not read", found["2026/20260801T020000Z--kowhai--lost02.md"]["message"])
        self.assertIn("is a folder that is not a month folder from archiving", found["2026/notes"]["message"])
        self.assertIn("is a folder inside a month folder", found["2026/09/inner"]["message"])
        self.assertIn("is a folder that is not a year folder from archiving", found["Old"]["message"])
        check, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        [misplaced] = [item for item in check["findings"] if "lost01" in item["message"]]
        self.assertEqual(misplaced["level"], "problem")
        self.assertIn("move it to Record/2026/08/, changing nothing in it", misplaced["fix"])

    def test_one_record_in_two_places_is_named_and_left_where_it_is(self):
        self.archive()
        shutil.copy(self.record / pr.archive_folder(MOVING[2]) / f"{MOVING[2]}.md", self.record / f"{MOVING[2]}.md")
        names, copies, _ = pr.scan_record_names(self.record)
        self.assertEqual(names[MOVING[2]], f"{MOVING[2]}.md")
        self.assertEqual(copies, [(MOVING[2], f"2026/09/{MOVING[2]}.md")])
        self.assertIn("are one record in two places", pr.copy_issue(*copies[0])["message"])
        check, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        [twice] = [item for item in check["findings"] if "two places" in item["message"]]
        self.assertEqual(twice["level"], "problem")
        self.assertIn(f"move Record/{MOVING[2]}.md out of Record/. Record/2026/09/{MOVING[2]}.md is the one archiving "
                      "moved", twice["fix"])
        self.assertEqual(self.plan()["stays"]["unsettled"] > 0, True)

    def test_a_month_folder_that_cannot_be_listed_makes_every_answer_partial(self):
        self.archive()
        real, target = os.scandir, str(self.record / "2026/09")

        def scandir(path="."):
            if str(path) == target:
                raise PermissionError(13, "Permission denied", target)
            return real(path)

        with mock.patch.object(os, "scandir", scandir):
            names, _, issues = pr.scan_record_names(self.record)
            found, _ = run(pr, "--pace", str(self.pace), "find")
            folder = self.folder()
        self.assertNotIn(MOVING[2], names)
        self.assertEqual([(issue["type"], issue["file"]) for issue in issues], [("unreadable", "2026/09/")])
        self.assertFalse(found["coverage"]["complete"])
        self.assertTrue(any("Record/2026/09/ could not be listed" in problem for problem in folder.problems))


class HealthCheckTests(FolderCase):
    def check(self):
        """The health check judges 3 months from today; here, from AS_AT."""
        judge = pc.po.Folder.archive_plan
        with mock.patch.object(pc.po.Folder, "archive_plan", lambda folder, moment=None: judge(folder, MOMENT)):
            out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        return out

    def test_archiving_is_suggested_once_it_is_worth_it(self):
        self.assertEqual([item for item in self.check()["findings"] if item["check"] == "archive"], [])
        review, _ = run(po, "--pace", str(self.pace), "--review", "--as-at", AS_AT)
        self.assertEqual((review["archive_suggested"], review["archive_ready"]), (False, 5))
        self.assertNotIn("could be archived", review["message"])
        with mock.patch.object(pc.po, "ARCHIVE_SUGGEST_FILES", 13), mock.patch.object(pc.po, "ARCHIVE_SUGGEST_RECORDS", 5):
            [item] = [item for item in self.check()["findings"] if item["check"] == "archive"]
        with mock.patch.object(po, "ARCHIVE_SUGGEST_FILES", 13), mock.patch.object(po, "ARCHIVE_SUGGEST_RECORDS", 5):
            review, _ = run(po, "--pace", str(self.pace), "--review", "--as-at", AS_AT)
        self.assertEqual(item["level"], "note")
        self.assertIn("5 records of finished work are more than 3 months old and could be archived", item["message"])
        self.assertIn("Ask the assistant to preview archiving", item["fix"])
        self.assertEqual((review["archive_suggested"], review["archive_ready"]), (True, 5))
        self.assertIn("5 records of finished work are more than 3 months old and could be archived", review["message"])

    def test_a_large_record_folder_points_to_archiving_when_finished_work_could_move(self):
        with mock.patch.object(pc, "RECORD_FOLDER_NOTE", 10), mock.patch.object(pc, "RECORD_FOLDER_LIMIT", 12):
            [item] = [item for item in self.check()["findings"] if " holds " in item["message"]]
            self.assertEqual(item["level"], "warning")
            self.assertIn("Archive finished work: 5 records of it are more than 3 months old", item["fix"])
            self.archive()
            [item] = [item for item in self.check()["findings"] if " holds " in item["message"]]
        self.assertEqual(item["level"], "note")
        self.assertIn("Never move or rename a record by hand: only archiving moves records", item["fix"])

    def test_every_archived_record_is_where_its_archive_put_it_and_unchanged(self):
        self.archive()
        self.assertEqual([item for item in self.check()["findings"] if item["check"] == "archive"], [])
        changed = self.record / pr.archive_folder(MOVING[2]) / f"{MOVING[2]}.md"
        changed.write_text(read(changed).replace("Invented work.", "Invented work, edited."), encoding="utf-8")
        (self.record / pr.archive_folder(MOVING[1]) / f"{MOVING[1]}.md").rename(self.record / f"{MOVING[1]}.md")
        found = [item for item in self.check()["findings"] if item["check"] == "archive"]
        self.assertEqual([item["level"] for item in found], ["problem", "note"])
        said = " ".join(item["message"] for item in found)
        self.assertIn("has changed since: their digest no longer matches", said)
        # Found directly in Record/, it is where an archive that stopped part-way leaves a record: nothing is lost.
        self.assertIn(f"{MOVING[1]} is still directly in Record/, whole", said)
        (self.record / f"{MOVING[1]}.md").unlink()
        [gone] = [item for item in self.check()["findings"] if MOVING[1] in item["message"]]
        self.assertEqual(gone["level"], "problem")
        self.assertIn(f"{MOVING[1]} is not in Record/2026/10/, where", gone["message"])

    def test_a_folder_with_archives_is_healthy(self):
        self.archive()
        out = self.check()
        self.assertEqual([item for item in out["findings"] if item["check"] in RECORD_CHECKS], [])
        self.assertIn("Record/: 14 record files, 5 of them archived in its year and month folders, each opened, with "
                      "corrections followed to the current account.", out["checked"])


class UpdaterTests(unittest.TestCase):
    def test_a_release_that_cannot_read_archived_records_is_not_installed_over_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            pace = make_folder(Path(tmp))
            reader = {"tag": "v3.14.0", "files": {"Tools/pace_record.py": b"def archive_folder(request): ..."}}
            older = {"tag": "v3.13.0", "files": {"Tools/pace_record.py": b"def load(record_dir, name): ..."}}
            self.assertEqual(pu.archive_stop(pace, older), "")  # nothing archived yet
            out, code = self_archive(pace)
            self.assertEqual(code, 0, out)
            self.assertEqual(pu.archive_stop(pace, reader), "")
            self.assertIn("which Pace v3.13.0 cannot read, so its tools would miss them. Install Pace 3.14.0 or later",
                          pu.archive_stop(pace, older))

    def test_the_updater_stops_before_installing_an_older_release(self):
        if True:
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repo = tu.Repo(base / "upstream")
                shutil.copytree(PACE_FOLDER, repo.path / "PACE", ignore=shutil.ignore_patterns("__pycache__"))
                tool = repo.path / "PACE/Product/Tools/pace_record.py"
                tool.write_text(read(tool).replace("def archive_folder(", "def month_of("), encoding="utf-8")
                commit = repo.commit("An invented release that cannot read archives")
                repo.tag("v3.13.9")
                pace = make_folder(base)
                out, code = self_archive(pace)
                self.assertEqual(code, 0, out)
                before = snapshot(pace)
                shown = pu.preview(pace, str(repo.path), "v3.13.9", commit)
                self.assertEqual(shown["status"], "cannot install")
                self.assertIn("Install Pace 3.14.0 or later instead", shown["message"])
                with self.assertRaises(pu.Stop) as stopped:
                    pu.apply(pace, str(repo.path), "v3.13.9", commit, go_ahead=f"Install Pace v3.13.9 at commit {commit}.")
                self.assertIn("Nothing was installed.", str(stopped.exception))
                self.assertEqual(snapshot(pace), before)


def self_archive(pace: Path) -> tuple:
    with clock():
        out, _ = run(pa, "preview", "--pace", str(pace), "--as-at", AS_AT)
        return run(pa, "apply", "--pace", str(pace), "--as-at", AS_AT, "--plan", out["plan"], "--go-ahead", "Yes.",
                   "--by", "Test")


class HelpTests(unittest.TestCase):
    def test_records_help_says_what_moves_what_stays_and_how(self):
        text = read(HELP / "records.md")
        part = text[text.index("## Archiving finished work\n"):text.index("## Exact-act confirmations\n")]
        for phrase in ("into a folder inside `Record/` for the year and month in each record's request id",
                       "Each record keeps its name and every byte", "once its work is finished and every record in it is "
                       "more than 3 months old", "**What stays directly in `Record/`:** open work, work recorded two ways, "
                       "project changes", "and everything from the last 3 months",
                       "**New records are always saved directly in `Record/`**, a correction of an archived record too",
                       "Only archiving moves a record; never move one by hand",
                       "once `Record/` itself holds 2,000 records and at least 500 could move",
                       "Nothing moves until the owner has seen what would move and said yes in their own words",
                       "python3 Product/Tools/pace_archive.py preview", "--go-ahead \"<the owner's words>\"",
                       "If what would move has changed since the preview", "as many as the record of the archive can list: up to 1,500 records",
                       "never copied or rewritten", "with a digest for each folder", "`status` is `archived` only when",
                       "every record is still whole and in one place", "never archives"):
            self.assertIn(phrase, part)
        self.assertIn("only archiving ever moves one, unchanged and under its own name", text)
        self.assertEqual((po.ARCHIVE_AFTER_MONTHS, po.ARCHIVE_SUGGEST_FILES, po.ARCHIVE_SUGGEST_RECORDS,
                          po.ARCHIVE_BATCH), (3, 2000, 500, 1500))

    def test_every_reader_by_hand_is_told_where_archived_records_are(self):
        fmt = read(HELP / "record-format.md")
        for phrase in ("Each record is saved as one new text file directly in `Record/`, never in a subfolder.",
                       "`Record/2026/10/20261022T221500Z--kowhai-budget--k3f9q2.md`. Nothing else moves a record.",
                       "Open work, project changes and everything from the last 3 months are always directly in `Record/`.",
                       "say which folders were listed", "in the folder for the year and month in its request id."):
            self.assertIn(phrase, fmt)
        hosts = read(HELP / "hosts-and-views.md")
        self.assertIn("Finished work more than 3 months old may be archived in the year and month folders inside "
                      "`Record/`; list the ones the question needs, and say which were listed.", hosts)
        self.assertIn("only Pace's archive tool, on a computer, moves a record.", hosts)
        self.assertIn("`archive_suggested` is true, `archive_ready` gives how many records could move", hosts)
        for root in (PACE_FOLDER, EXAMPLE):
            self.assertIn("- `Record/` - the owner's memory: decisions, actions, notes and figures. Open work, project "
                          "changes and the last 3 months are always directly in it; finished work from before then may be "
                          "archived in its year and month folders, such as `Record/2026/07/`.", read(root / "Pace.md"))
        self.assertIn("includes the year and month folders inside `Record/`, where archiving keeps finished work.",
                      read(ADD_INS / "Open work/ADD-IN.md"))
        self.assertIn("If the review list says finished work could be archived, say so in one line and offer it",
                      read(ADD_INS / "Weekly review/ADD-IN.md"))
        self.assertIn("nor in the folder for the year and month in its request id",
                      read(ADD_INS / "Project overview/ADD-IN.md"))
        check = read(HELP / "health-check.md")
        self.assertIn("- **Archiving:** once `Record/` itself holds 2,000 records and at least 500 could be archived", check)
        self.assertIn("in its month folder and, by the folder's digest, unchanged", check)
        self.assertIn("so once a folder has some, the updater will not install an earlier release", read(HELP / "updates.md"))
        layout = read(ROOT / "docs/layout.md")
        self.assertIn("health check and archive tool", layout)
        self.assertIn("into year and month folders such as `Record/2026/07/`", layout)

    def test_the_example_keeps_a_small_archive_that_checks(self):
        archived = sorted(path.relative_to(EXAMPLE / "Record").as_posix() for path in (EXAMPLE / "Record").rglob("*.md")
                          if path.parent != EXAMPLE / "Record")
        self.assertEqual(archived, ["2025/11/20251104T200000Z--none--ins001.md", "2025/11/20251112T030000Z--none--ins002.md",
                                    "2025/12/20251203T010000Z--none--bkp001.md"])
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "example"
            shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("__pycache__"))
            out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(copy)]))
        self.assertEqual([item for item in out["findings"] if item["check"] in ("archive", "record-files", "records")], [])
        self.assertIn("Archived records: 3 records checked against the records of the archives that moved them.",
                      out["checked"])


if __name__ == "__main__":
    unittest.main()
