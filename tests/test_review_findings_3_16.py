"""The independent review of 3.16.0 (144461d): each finding has a test here that fails on that commit.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile
import time
import unicodedata
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

import test_updates as tu
from test_archive import PACE_FOLDER, read, run, snapshot, write_project
from test_folder_numbers import Case, files, old_layout, pc, pf, pr

pu = pc.pu
HELP = PACE_FOLDER / "Product/Help"


def setUpModule():
    tu.setUpModule()  # git for the invented releases


def tearDownModule():
    tu.tearDownModule()


def renames_of(plan: dict) -> dict:
    return {rename["from"]: rename["to"] for rename in plan["renames"]}


class LeadingDigitsTests(Case):
    """H1: a name made before 3.16.0 that starts with digits and a space, such as 2026 Tax return, was read as a number,
    so numbering went on from 2027 and pages showed only Tax return."""

    def test_a_year_at_the_start_of_a_name_is_part_of_the_name(self):
        write_project(self.pace, "tax-2025", "2025 Tax return")
        write_project(self.pace, "tax-2026", "2026 Tax return")
        write_project(self.pace, "kowhai", "Kowhai Books")
        listed, _ = self.tool("projects")
        self.assertEqual(sorted((entry["name"], entry["number"]) for entry in listed["projects"]),
                         [("2025 Tax return", None), ("2026 Tax return", None), ("Kowhai Books", None)])
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {"1 Projects/2025 Tax return": "01. 2025 Tax return", "1 Projects/2026 Tax return": "02. 2026 Tax return",
                          "1 Projects/Kowhai Books": "03. Kowhai Books"})

    def test_a_folder_of_the_owners_own_starting_with_a_year_sets_no_number(self):
        (self.pace / "1 Projects/2019 Old clients").mkdir()
        self.assertEqual(self.new("kowhai", "Kowhai Books")[0]["folder"], "1 Projects/01. Kowhai Books")
        self.assertEqual(pr.folder_number("２０２４ Plans"), (None, "２０２４ Plans"))
        self.assertEqual(pr.folder_number("２０ Plans"), (None, "２０ Plans"))

    def test_making_a_project_of_a_folder_named_with_a_year_uses_that_folder(self):
        (self.pace / "1 Projects/2027 Budget").mkdir()
        out, code = self.new("budget", "2027 Budget")
        self.assertEqual((out["status"], code, out["folder"]), ("saved", 0, "1 Projects/2027 Budget"), out)

    def test_repeating_the_command_for_a_project_named_with_two_digits_still_finds_it(self):
        write_project(self.pace, "fitness", "24 Hour Fitness")  # made before 3.16.0
        out, code = self.new("fitness", "24 Hour Fitness")
        self.assertEqual((out["status"], code, out["folder"]), ("already-saved", 0, "1 Projects/24 Hour Fitness"), out)

    def test_the_health_check_notes_a_name_starting_with_a_year_as_not_numbered(self):
        write_project(self.pace, "tax-2026", "2026 Tax return")
        out, _ = run(pc, "--pace", str(self.pace))
        noted = [item for item in out["findings"] if item["check"] == "folder-numbers"]
        self.assertEqual(len(noted), 1, out["findings"])
        self.assertEqual(noted[0]["files"], ["1 Projects/2026 Tax return", "1 Projects/2026 Tax return/Documents"])


class DocumentsTests(Case):
    """H2: any folder named a number and Documents, such as 2024 Documents, was taken as the project's Documents/,
    hiding a project inside it and leading the health check to say to move the working files into it."""

    def setUp(self):
        super().setUp()
        write_project(self.pace, "kowhai", "Kowhai Books")  # made before 3.16.0, with Documents/
        self.client = self.pace / "1 Projects/Kowhai Books"
        (self.client / "Documents/Budget 2027.xlsx").write_text("Invented workbook.", encoding="utf-8")
        audit = self.client / "2024 Documents/Audit"
        audit.mkdir(parents=True)
        (audit / "Pace project.md").write_text("---\nformat: project-1\nid: audit-2024\nparent: none\ncreated: "
                                               "2026-08-01T09:00:00+12:00\nby: Test\n---\n\nInvented audit.\n", encoding="utf-8")

    def test_a_folder_named_a_year_and_documents_is_an_ordinary_folder(self):
        listed, _ = self.tool("projects")
        self.assertIn("audit-2024", {entry["id"] for entry in listed["projects"]})
        self.assertEqual(pr.working_dir(self.client), self.client / "Documents")
        out, _ = self.tool("project-new", "--id", "kowhai", "--name", "Kowhai Books", "--folder", "Sources", "--by", "Test")
        self.assertEqual(out["status"], "already-saved", out)
        self.assertTrue((self.client / "Documents/Sources").is_dir())
        checked, _ = run(pc, "--pace", str(self.pace))
        self.assertFalse([item for item in checked["findings"] if "Documents folders" in item["message"]], checked["findings"])

    def test_two_documents_folders_are_merged_file_by_file_never_over_one_another(self):
        (self.client / "01. Documents").mkdir()
        checked, _ = run(pc, "--pace", str(self.pace))
        warned = [item for item in checked["findings"] if "Documents folders" in item["message"]]
        self.assertEqual(len(warned), 1, checked["findings"])
        self.assertIn("never over a file of the same name: where both folders hold one, ask the owner which to keep",
                      warned[0]["fix"])


class LinkTests(Case):
    """M1: renames went through folder links and junctions, renaming one folder twice over and folders outside Pace."""

    def setUp(self):
        super().setUp()
        old_layout(self.pace)

    def link(self, link: Path, target: Path):
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("folder links cannot be made here")

    def test_a_folder_reached_through_a_link_is_numbered_only_where_it_really_is(self):
        self.link(self.pace / "1 Projects/SBR/Budget link", self.pace / "1 Projects/Kowhai Books/Budget 2027")
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)
        self.assertFalse([path for path in renames_of(plan) if "Budget link" in path])
        self.assertIn("1 Projects/SBR/Budget link/ is reached through a link or junction to a folder in 1 Projects/", plan["message"])
        self.assertIn("make the link again afterwards", plan["message"])
        out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code), ("numbered", 0), out)
        self.assertTrue((self.pace / "1 Projects/01. Kowhai Books/02. Budget 2027/01. Documents").is_dir())

    def test_nothing_outside_the_pace_folder_is_renamed(self):
        outside = Path(self._temp.name) / "Shared drive/Client X"
        (outside / "Documents").mkdir(parents=True)
        (outside / "Pace project.md").write_text("---\nformat: project-1\nid: client-x\nparent: none\ncreated: "
                                                 "2026-08-01T09:00:00+12:00\nby: Test\n---\n\nInvented.\n", encoding="utf-8")
        self.link(self.pace / "1 Projects/Client X", outside)
        before = snapshot(outside)
        plan, _ = self.preview()
        self.assertFalse([path for path in renames_of(plan) if "Client X" in path], plan["renames"])
        self.assertIn("1 Projects/Client X/ keeps its name, and so does everything in it, as it is reached through a link "
                      "or junction to a folder outside the Pace folder", plan["message"])
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertEqual(snapshot(outside), before)
        self.assertTrue((self.pace / "1 Projects/Client X").is_symlink())


class PathLengthSpeedTests(Case):
    """M2: the preview's path-length check took time in proportion to folders times renames, so a large Pace folder
    never showed a plan."""

    def test_the_path_length_check_takes_one_pass(self):
        documents = self.pace / "1 Projects/Big/Documents"
        for outer in range(40):
            for inner in range(50):
                (documents / f"area {outer:02d}" / f"folder {inner:02d}").mkdir(parents=True)
        renames = [{"from": f"1 Projects/Project {number:03d}", "to": f"01. Project {number:03d}"} for number in range(299)]
        renames.append({"from": "1 Projects/Big", "to": "01. Big"})
        started = time.monotonic()
        past_windows, past_excel, every = pf.too_long(self.pace, renames)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual((past_windows, past_excel, every), ([], [], True))


class LetterCaseTests(Case):
    """M3: making a project of a folder already there matched its name exactly, so a folder in another letter case or
    with its accents written the other way was not used, and a second folder was made."""

    def test_a_folder_in_another_case_or_unicode_form_is_used(self):
        (self.pace / "1 Projects/garden plans").mkdir()
        out, _ = self.new("garden", "Garden plans")
        self.assertEqual(out["folder"], "1 Projects/garden plans")
        decomposed = unicodedata.normalize("NFD", "Ōtaki pool")
        (self.pace / "1 Projects" / decomposed).mkdir()
        out, _ = self.new("otaki", unicodedata.normalize("NFC", "Ōtaki pool"))
        self.assertEqual(out["folder"], f"1 Projects/{decomposed}")
        self.assertEqual(sorted(path.name for path in (self.pace / "1 Projects").iterdir() if path.is_dir()),
                         sorted(["garden plans", decomposed]))


class LowFindingTests(Case):
    def test_l1_one_large_folder_does_not_stop_the_rest_being_numbered(self):
        old_layout(self.pace)
        checkout = self.pace / "1 Projects/SBR/Pace/Code"
        for number in range(6):
            (checkout / f"package {number}").mkdir(parents=True)
        with mock.patch.object(pr, "MAX_FOLDERS_INSIDE_UNNAMED", 3):
            plan, code = self.preview()
            self.assertEqual((plan["status"], code), ("ready", 0), plan)
            self.assertIn("Not every folder was looked into, so any project inside these keeps its name", plan["message"])
            self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertTrue((self.pace / "1 Projects/02. SBR/02. Pace/Code/package 5").is_dir())

    def test_l2_a_folder_that_keeps_failing_to_rename_does_not_stop_the_rest(self):
        old_layout(self.pace)
        plan, _ = self.preview()
        stuck = self.pace / "1 Projects/Kowhai Books/Budget 2027/Documents"
        real = pr.rename_no_replace

        def rename(source, target):
            if Path(source) == stuck:
                raise PermissionError(13, "Access is denied", str(source))
            real(source, target)

        with mock.patch.object(pr, "rename_no_replace", rename):
            out, _ = self.apply(plan["plan"])
        self.assertEqual((out["status"], out["renamed"]), ("partly-numbered", 9), out)
        self.assertTrue((self.pace / "1 Projects/02. SBR/02. Pace/01. Documents").is_dir())

    def test_l3_a_folder_that_would_share_a_name_once_numbered_is_left_for_the_owner(self):
        write_project(self.pace, "web", "Website")
        (self.pace / "1 Projects/03. Website").mkdir()  # the owner's own, not a project
        plan, _ = self.preview()
        self.assertNotIn("1 Projects/Website", renames_of(plan))
        self.assertIn("1 Projects/Website/ keeps its name, as 03. Website/ beside it has the same name once numbered", plan["message"])
        self.assertIn("Records still find their files either way.", read(HELP / "updates.md"))

    def test_l4_numbers_are_not_said_never_to_be_used_again_and_documents_sharing_01_is_named(self):
        self.assertNotIn("never changed or used again", read(HELP / "projects.md"))
        write_project(self.pace, "kowhai", "Kowhai Books")
        (self.pace / "1 Projects/Kowhai Books/01. Admin").mkdir()
        plan, _ = self.preview()
        self.assertEqual(renames_of(plan)["1 Projects/Kowhai Books/Documents"], "01. Documents")
        self.assertIn("1 Projects/Kowhai Books/Documents/ becomes 01. Documents/, which 01. Admin/ beside it starts with too",
                      plan["message"])
        (self.pace / "1 Projects/99. Archive").mkdir()
        self.assertEqual(self.new("garden", "Garden plans")[0]["folder"], "1 Projects/01. Garden plans")

    def test_l5_numbers_keep_the_browsers_order_however_many_runs_it_takes(self):
        for name in ("apple", "Banana", "Item 9", "Item 10"):
            write_project(self.pace, name.lower().replace(" ", "-"), name)
            shutil.rmtree(self.pace / "1 Projects" / name / "Documents")
        with mock.patch.object(pf, "BATCH", 2):
            while True:
                plan, _ = self.preview()
                if plan["status"] == "nothing-to-number":
                    break
                self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertEqual(sorted(path.name for path in (self.pace / "1 Projects").iterdir() if path.is_dir()),
                         ["01. apple", "02. Banana", "03. Item 9", "04. Item 10"])

    def test_l6_accented_names_keep_their_place_and_the_help_says_where_other_folders_go(self):
        for pid, name in (("otaki", "Ōtaki pool"), ("zealandia", "Zealandia"), ("apple", "Apple")):
            write_project(self.pace, pid, name)
        plan, _ = self.preview()
        top = {key: value for key, value in renames_of(plan).items() if key.count("/") == 1}
        self.assertEqual(top, {"1 Projects/Apple": "01. Apple", "1 Projects/Ōtaki pool": "02. Ōtaki pool",
                               "1 Projects/Zealandia": "03. Zealandia"})
        self.assertNotIn("nothing moves but each `Documents/`", read(HELP / "projects.md"))
        self.assertIn("so those without a number come after the numbered ones", read(HELP / "projects.md"))

    def test_l7_a_name_with_a_superscript_digit_does_not_stop_the_preview(self):
        write_project(self.pace, "model", "Model 3²")
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)
        self.assertEqual(renames_of(plan)["1 Projects/Model 3²"], "01. Model 3²")

    def test_l8_a_repository_reference_under_a_name_starting_with_digits_is_in_its_place(self):
        out, _ = self.new("fitness", "24 Hour Fitness")
        self.assertEqual(out["folder"], "1 Projects/01. 24 Hour Fitness")
        reference = self.pace / "Repos/24 Hour Fitness/booking-site/Pace repo.md"
        reference.parent.mkdir(parents=True)
        reference.write_text("# Booking site\n\nHome project id: fitness\n", encoding="utf-8")
        checked, _ = run(pc, "--pace", str(self.pace))
        self.assertEqual([item for item in checked["findings"] if item["check"] == "repos"], [])

    def test_l9_a_run_that_renames_nothing_says_so_in_a_correction(self):
        old_layout(self.pace)
        before = snapshot(self.pace / "1 Projects")
        plan, _ = self.preview()
        with mock.patch.object(pr, "rename_no_replace", lambda source, target: (_ for _ in ()).throw(
                PermissionError(13, "Access is denied", str(source)))):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code, out["renamed"]), ("not-numbered", 1, 0), out)
        first, correction = read(self.pace / out["file"]), read(self.pace / "Record" / f"{out['correction']}.md")
        self.assertIn("subject: Numbering folders", first)
        self.assertIn(f"corrects: {out['record']}", correction)
        self.assertIn("none was renamed and checked, and 10 kept their names", " ".join(correction.split()))
        self.assertEqual(snapshot(self.pace / "1 Projects"), before)

    def test_l10_pace_md_says_where_a_projects_files_are_before_it_is_numbered(self):
        for root in (PACE_FOLDER, PACE_FOLDER.parent / "example"):
            self.assertIn("with its files in `01. Documents/` (`Documents/` in a project not numbered yet)",
                          read(root / "Pace.md"))


class DowngradeTests(unittest.TestCase):
    """L11: nothing stopped a release from before 3.16.0 being installed over numbered folders, whose tools would show
    the numbers in project names and take each 01. Documents/ for a folder to sort out."""

    def test_a_release_that_does_not_know_numbers_is_not_installed_over_them(self):
        knows = {"tag": "v3.16.0", "files": {"Tools/pace_record.py": b"def plain_name(name): ..."}}
        older = {"tag": "v3.15.0", "files": {"Tools/pace_record.py": b"def archive_folder(request): ..."}}
        with tempfile.TemporaryDirectory() as temp:
            pace = Path(temp)
            write_project(pace, "kowhai", "Kowhai Books")
            self.assertEqual(pu.numbers_stop(pace, older), "")  # not numbered yet
            (pace / "1 Projects/Kowhai Books/Documents").rename(pace / "1 Projects/Kowhai Books/01. Documents")
            self.assertIn("Install Pace 3.16.0 or later instead", pu.numbers_stop(pace, older))
            self.assertEqual(pu.numbers_stop(pace, knows), "")
            (pace / "1 Projects/Kowhai Books").rename(pace / "1 Projects/01. Kowhai Books")
            self.assertIn("which Pace v3.15.0's tools do not know", pu.numbers_stop(pace, older))

    def test_the_updater_stops_before_installing_such_a_release(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = tu.Repo(base / "upstream")
            shutil.copytree(PACE_FOLDER, repo.path / "PACE", ignore=shutil.ignore_patterns("__pycache__"))
            tool = repo.path / "PACE/Product/Tools/pace_record.py"
            tool.write_text(read(tool).replace("def plain_name(", "def bare_name("), encoding="utf-8")
            commit = repo.commit("An invented release that does not know folder numbers")
            repo.tag("v3.15.9")
            pace = base / "PACE"
            shutil.copytree(PACE_FOLDER, pace, ignore=shutil.ignore_patterns("__pycache__"))
            write_project(pace, "kowhai", "01. Kowhai Books")
            before = snapshot(pace)
            shown = pu.preview(pace, str(repo.path), "v3.15.9", commit)
            self.assertEqual(shown["status"], "cannot install", shown)
            self.assertIn("Install Pace 3.16.0 or later instead", shown["message"])
            with self.assertRaises(pu.Stop) as stopped:
                pu.apply(pace, str(repo.path), "v3.15.9", commit, go_ahead=f"Install Pace v3.15.9 at commit {commit}.")
            self.assertIn("Nothing was installed.", str(stopped.exception))
            self.assertEqual(snapshot(pace), before)


if __name__ == "__main__":
    unittest.main()
