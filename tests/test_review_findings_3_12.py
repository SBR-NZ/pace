"""The independent review of the 3.12.0 build: each finding, as a test that fails on the reviewed commit (c2095f4).

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_records import BUDGET, BUDGET_DIR, CLIENT, PaceFolder, at, pr
from test_overview_tool import AS_AT, Folder, OverviewCase
from test_health_check import CheckCase, MARK, OWNER, STATE, pc, pu, setUpModule, tearDownModule, write_project, write_record  # noqa: F401
from test_addins import PACE_FOLDER

ROOT = Path(__file__).resolve().parents[1]


class UpdateActionFindings(PaceFolder):
    def action(self, *extra, subjects=("Board pack",)):
        request, out, _ = self.save(kind="action", subjects=subjects, origin="owner", words="Send it by the 5th.",
                                    body="Send the board pack.", extra=("--state", "open", "--owed-by", "Sam Lee", *extra))
        self.assertEqual(out["status"], "saved", out)
        return request

    def update(self, corrects, *options, project=BUDGET, when=None):
        request = self.new_request(project, when or at(day=30))
        out, code = self.run_tool("update-action", "--request", request, "--corrects", corrects, *options,
                                  "--from", "owner", "--words", "Done now", "--by", "Test agent")
        return request, out, code

    def header(self, request):
        fields, _, _ = pr.parse((self.record / f"{request}.md").read_bytes())
        return fields

    def test_m1_every_other_line_of_the_current_account_is_carried_over(self):
        earlier = self.action("--source", "Email from Sam, 26 Oct", "--field", "next-step=Call Kahu's lawyer",
                              "--field", "priority=high")
        request, out, _ = self.update(earlier, "--state", "done", "--source", "Board minutes, 30 Oct")
        self.assertEqual(out["status"], "saved", out)
        fields = self.header(request)
        self.assertEqual(fields["source"], ["Email from Sam, 26 Oct", "Board minutes, 30 Oct"])
        self.assertEqual((fields["next-step"], fields["priority"]), (["Call Kahu's lawyer"], ["high"]))
        self.assertEqual((fields["from"], fields["words"], fields["by"]), (["owner"], ["Done now"], ["Test agent"]))

    def test_l2_a_correction_with_an_earlier_request_id_is_still_the_current_account(self):
        earlier = self.action()
        older = self.new_request(BUDGET, at(day=20))  # a computer with a wrong clock
        out, _ = self.run_tool("create", "--request", older, "--project", BUDGET, "--kind", "action", "--subject", "Board pack",
                               "--from", "owner", "--words", "Moved", "--by", "Test agent", "--corrects", earlier,
                               "--state", "open", "--due", "2026-11-12", "--body", "Send the board pack.")
        self.assertEqual(out["status"], "saved", out)
        _, refused, code = self.update(earlier, "--state", "done")
        self.assertEqual((refused["status"], code), ("not-saved", 1), refused)
        self.assertIn(f"{older} is", refused["message"])
        _, out, _ = self.update(older, "--state", "done")
        self.assertEqual(out["status"], "saved", out)
        story, _ = self.run_tool("history", "--request", earlier)
        self.assertEqual(len(story["current"]), 1)
        # create sees it too, so it never adds a second correction of the same record.
        again, _ = self.run_tool("create", "--request", self.new_request(BUDGET, at(day=30)), "--project", BUDGET, "--kind",
                                 "action", "--subject", "Board pack", "--from", "agent", "--by", "Test agent", "--corrects",
                                 earlier, "--state", "cancelled", "--body", "Send the board pack.")
        self.assertEqual(again["status"], "not-saved", again)

    def test_l3_a_second_copy_of_another_record_does_not_block_an_update(self):
        earlier = self.action()
        other, _, _ = self.save(kind="note", subjects=("January note",), body="An invented January note.",
                                when=at(day=5, month=1))
        shutil.copyfile(self.record / f"{other}.md", self.record / f"{other} (1).md")
        _, out, _ = self.update(earlier, "--state", "done")
        self.assertEqual(out["status"], "saved", out)
        # A second copy of a record in the item's own story still stops it.
        later = self.action(subjects=("Supplier call",))
        shutil.copyfile(self.record / f"{later}.md", self.record / f"{later}-LAPTOP.md")
        _, out, _ = self.update(later, "--state", "done")
        self.assertEqual(out["status"], "not-saved", out)
        self.assertIn(f"{later}-LAPTOP.md could be part of this item's story", out["message"])

    def test_l4_an_item_whose_project_folder_is_missing_can_still_be_updated(self):
        earlier = self.action()
        shutil.rmtree(self.pace / BUDGET_DIR)
        _, out, _ = self.update(earlier, "--state", "done")
        self.assertEqual(out["status"], "saved", out)

    def test_l5_two_ways_says_to_withdraw_the_other_first_and_that_works(self):
        earlier = self.action()
        first = self.new_request(BUDGET, at(day=24))
        second = self.new_request(BUDGET, at(day=25))
        for request, due in ((first, "2026-11-10"), (second, "2026-11-11")):
            self.write_raw(f"{request}.md", self.raw_record(request, "Send the board pack.", corrects=earlier, kind="action",
                                                            extra=f"due: {due}"))
        _, out, _ = self.update(first, "--state", "done")
        self.assertEqual(out["status"], "not-saved", out)
        self.assertIn(f"Save a withdrawal of the other (create --kind withdrawal --corrects {second}), then update the one "
                      "that stands.", out["message"])
        withdrawn, _ = self.run_tool("create", "--request", self.new_request(BUDGET, at(day=29)), "--project", BUDGET, "--kind",
                                     "withdrawal", "--subject", "Board pack", "--from", "owner", "--words", "The 10th stands",
                                     "--by", "Test agent", "--corrects", second, "--body", "Recorded by mistake.")
        self.assertEqual(withdrawn["status"], "saved", withdrawn)
        _, out, _ = self.update(first, "--state", "done")
        self.assertEqual(out["status"], "saved", out)


class OwnerLineFindings(unittest.TestCase):
    def names(self, owner_lines: str, elsewhere: str = "") -> list:
        text = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        text = text.replace(f"{MARK}\nNone yet.\n", f"{MARK}\n{elsewhere}None yet.\n")
        text = text.replace(f"{MARK}\n## Time zone", f"{MARK}\n{owner_lines}\n## Time zone")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Pace.md").write_text(text, encoding="utf-8")
            return pr.owner_names(Path(tmp))

    def test_l6_owner_lines_count_only_in_their_own_part(self):
        self.assertEqual(self.names("", elsewhere="- Owner: approve every invoice over $500 before it goes.\n"), [])

    def test_l6_owner_lines_in_the_forms_people_write_them(self):
        lines = "`Owner: Rangi Parata`\n- **Owner:** Rangi\nOwner : \"R. Parata\"\n"
        self.assertEqual(self.names(lines), ["Rangi Parata", "Rangi", "R. Parata"])


class ReviewLineFindings(OverviewCase):
    def test_l7_a_first_day_after_today_here_is_given_not_called_unknown(self):
        f = self.f
        f.no_time_zone()
        f.action(self.budget, "Payroll query", created="2026-10-26T08:00:00+13:00")
        out, _ = f.run("--review", owner=False, as_at="2026-10-25T21:00:00+00:00")
        line = out["groups"][0]["items"][0]["line"]
        self.assertNotIn("not known", line)
        self.assertTrue(line.startswith("1. Recorded 26 Oct 2026 - Payroll query"), line)


class HealthCheckFindings(CheckCase):
    def test_m2_unknown_projects_are_said_once_and_never_remade_while_folders_are_unreadable(self):
        write_record(self.pace, "20261025T070000Z--kahu-trust--unk001", kind="note", body="Invented.")
        write_record(self.pace, "20261025T071000Z--kahu-deed--unk002", kind="note", body="Invented.")
        out = self.check()
        [found] = [item for item in self.found(out, "projects") if "Records use project ids" in item["message"]]
        self.assertEqual(found["level"], "problem")
        self.assertIn("kahu-deed (1 record), kahu-trust (1 record)", found["message"])
        self.assertIn("Only if a project is truly gone", found["fix"])
        # Make one project's identity file unreadable: its records' id is then not known to be missing.
        (self.pace / "1 Projects/01. Kowhai Books/02. Budget 2027/Pace project.md").write_bytes(b"\xff\xfe not a project file")
        out = self.check()
        [found] = [item for item in self.found(out, "projects") if "Records use project ids" in item["message"]]
        self.assertEqual(found["level"], "warning")
        self.assertIn("kowhai-budget (1 record)", found["message"])
        self.assertIn("Do not make these projects again", found["fix"])
        self.assertNotIn("make the project again", json.dumps(out))
        # 1 Projects/ itself cannot be listed: that is a problem, and no project id is called missing.
        real = os.scandir
        base = self.pace / "1 Projects"

        def scandir(path="."):
            if Path(path) == base:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path)

        with mock.patch.object(pc.os, "scandir", scandir):
            out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        listed = [item for item in self.found(out, "projects") if "1 Projects/ could not be listed" in item["message"]]
        self.assertEqual([item["level"] for item in listed], ["problem"])
        [found] = [item for item in self.found(out, "projects") if "Records use project ids" in item["message"]]
        self.assertEqual(found["level"], "warning")

    def test_m3_a_reference_directly_in_repos_is_named_not_a_crash(self):
        (self.pace / "Repos/Pace repo.md").write_text("# Budget model\n\nHome project id: kowhai-budget\n", encoding="utf-8")
        run = subprocess.run([sys.executable, "-B", str(self.pace / "Product/Tools/pace_check.py"), "--pace", str(self.pace)],
                             capture_output=True, text=True)
        out = json.loads(run.stdout)
        [note] = [item for item in out["findings"] if item["check"] == "repos"]
        self.assertIn("Repos/Pace repo.md is not in its project's place", note["message"])

    def test_m4_a_second_copy_never_replaces_the_saved_record(self):
        record = self.pace / "Record"
        name = "20261025T010000Z--kowhai-budget--act001"
        shutil.copyfile(record / f"{name}.md", record / f"{name}-LAPTOP.md")
        [same] = self.found(self.check(), "record-files")
        self.assertIn("reads the same as it", same["message"])
        (record / f"{name}-LAPTOP.md").write_text((record / f"{name}.md").read_text(encoding="utf-8").replace(
            "Invented work.", "Invented work, differently."), encoding="utf-8")
        [differs] = self.found(self.check(), "record-files")
        self.assertIn("The record itself is never replaced", differs["fix"])
        self.assertNotIn("keep that one as the record", differs["fix"])

    def test_l1_advice_the_record_tool_can_follow(self):
        (self.pace / "Record/20261025T080000Z--kowhai--dmg001.md").write_text("no header at all\n", encoding="utf-8")
        write_record(self.pace, "20261025T061000Z--kowhai--lop001", corrects="20261025T062000Z--kowhai--lop002", state="done")
        write_record(self.pace, "20261025T062000Z--kowhai--lop002", corrects="20261025T061000Z--kowhai--lop001", state="open")
        out = self.check()
        [damaged] = self.found(out, "records", "problem")
        self.assertIn("The record tool cannot correct a file it cannot read", damaged["fix"])
        [loop] = self.found(out, "corrections")
        self.assertIn("save it as a new record, not a correction", loop["fix"])

    def test_l8_finder_and_explorer_files_in_product_are_not_edits(self):
        (self.pace / "Product/.DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
        (self.pace / "Product/Help/desktop.ini").write_text("[.ShellClassInfo]\n", encoding="utf-8")
        out = self.check()
        self.assertEqual(out["status"], "healthy", out["findings"])
        [note] = self.found(out, "product")
        self.assertIn(".DS_Store", note["message"])
        prior = pu.installed_release(self.pace)
        self.assertIsNone(pu.product_changes(prior, pu.read_tree(self.pace / "Product")))

    def test_l9_a_link_under_the_old_name_to_the_numbered_folder_needs_nothing(self):
        os.symlink("1 Projects", self.pace / "Projects")
        out = self.check()
        self.assertEqual(self.found(out, "folder-names"), [])
        self.assertEqual(pr.old_folder_names(self.pace), "")
        self.assertEqual(pu.folder_renames(self.pace, {"pace_folders": ["1 Projects", "2 Views", "3 My add-ins"]}), [])
        self.assertIn("1 Projects/: 2 projects.", out["checked"])

    def test_l10_a_folder_reached_twice_in_repos_is_read_once(self):
        os.symlink("Budget 2027", self.pace / "Repos/Kowhai Books/Budget again")
        out = self.check()
        self.assertIn("Repos/: 1 repository reference.", out["checked"])
        self.assertEqual(self.found(out, "repos"), [])
        # A second way into one folder that is not a link, as a Windows junction is; here, a bind mount.
        mirror = self.pace / "Repos/Kowhai Books/Mirror"
        mirror.mkdir()
        mounted = subprocess.run(["mount", "--bind", str(self.pace / "Repos/Kowhai Books/Budget 2027"), str(mirror)],
                                 capture_output=True).returncode == 0
        if not mounted:
            self.skipTest("a second way into a folder cannot be made here")
        try:
            out = self.check()
            self.assertIn("Repos/: 1 repository reference.", out["checked"])
            self.assertEqual(self.found(out, "repos"), [])
        finally:
            subprocess.run(["umount", str(mirror)], capture_output=True)

    def test_l10_a_folder_in_repos_that_cannot_be_listed_is_named(self):
        real = os.scandir
        blocked = self.pace / "Repos/Kowhai Books/Budget 2027"

        def scandir(path="."):
            if Path(path) == blocked:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path)

        with mock.patch.object(pc.os, "scandir", scandir):
            out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        [item] = self.found(out, "repos")
        self.assertEqual(item["level"], "warning")
        self.assertIn("Repos/Kowhai Books/Budget 2027/ could not be listed", item["message"])

    def test_l1_a_record_this_computer_may_not_read_is_an_access_question(self):
        real = pc.pr.read_back
        name = "20261025T010000Z--kowhai-budget--act001.md"

        def read_back(path):
            if Path(path).name == name:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path)

        with mock.patch.object(pc.pr, "read_back", read_back):
            out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        [item] = [found for found in self.found(out, "records") if name in found["message"]]
        self.assertIn("finished syncing and that this computer may read it", item["fix"])

    def test_l11_the_owner_hint_names_people_not_the_word_owner(self):
        self.edit_pace_md(f"Owner: {OWNER}\n", "")
        write_record(self.pace, "20261025T090000Z--kowhai--own001", subject="Note", owed_by="owner", state="open")
        write_record(self.pace, "20261025T091000Z--kowhai--own002", subject="Note two", owed_by="owner", state="open")
        [item] = self.found(self.check(), "owner")
        self.assertNotIn("owner (", item["message"])

    def test_l11_a_file_name_that_is_not_text_still_gives_one_json_object(self):
        try:
            name = os.fsdecode(b"\xff\xfe-notes.md")  # Windows cannot spell such a name at all
            (self.pace / "Record" / name).write_text("x", encoding="utf-8")
        except (OSError, UnicodeError):
            self.skipTest("this file system cannot hold such a name")
        for command in ([str(self.pace / "Product/Tools/pace_check.py"), "--pace", str(self.pace)],
                        [str(self.pace / "Product/Tools/pace_record.py"), "--pace", str(self.pace), "find"]):
            with self.subTest(command=command[0]):
                run = subprocess.run([sys.executable, "-B", *command], capture_output=True)
                self.assertIsInstance(json.loads(run.stdout.decode("utf-8")), dict, run.stderr[-500:])


class HelpFindings(unittest.TestCase):
    def test_l11_the_help_says_what_the_tools_do(self):
        add_ins = (PACE_FOLDER / "Product/Help/add-ins.md").read_text(encoding="utf-8")
        self.assertIn("Project overview is the only add-in that makes a page. Its page template", add_ins)
        hosts = (PACE_FOLDER / "Product/Help/hosts-and-views.md").read_text(encoding="utf-8")
        review = next(part for part in hosts.split("\n\n") if part.startswith("The fourth command gives"))
        self.assertNotIn("Without `--save`, nothing is saved.", review)
        self.assertLess(hosts.index("For a page, when the `Pace.md` index names a customised copy"), hosts.index(review))
        steps = (PACE_FOLDER / "Product/Pace add-ins/Weekly review/ADD-IN.md").read_text(encoding="utf-8")
        self.assertIn("withdraw the other, then make any change the owner gave to the one that stands", steps)


if __name__ == "__main__":
    unittest.main()
