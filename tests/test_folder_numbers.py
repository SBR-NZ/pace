"""Numbered project folders (3.16.0): new projects numbered by the record tool, names shown without numbers, older
paths still found, the folders tool numbering the folders a Pace folder already has on the owner's yes, and the
health check.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import EXAMPLE, PACE_FOLDER, OWNER, po, read, run, snapshot, write_project, write_record

TOOLS = PACE_FOLDER / "Product/Tools"
HELP = PACE_FOLDER / "Product/Help"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_for_folder_numbers", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = load("pace_folders")
pr = pf.pr
pc = load("pace_check")


def make_pace(base: Path) -> Path:
    pace = base / "PACE"
    shutil.copytree(PACE_FOLDER, pace, ignore=shutil.ignore_patterns("__pycache__"))
    mark = "<!-- Your lines go below this one. Pace updates never change them. -->"
    text = read(pace / "Pace.md").replace(f"{mark}\n## Time zone", f"{mark}\nOwner: {OWNER}\n\n## Time zone")
    (pace / "Pace.md").write_text(text.replace(f"{mark}\n## Help", f"{mark}\nTime zone: Pacific/Auckland\n\n## Help"),
                                  encoding="utf-8")
    return pace


def old_layout(pace: Path) -> None:
    """Projects as a Pace folder made before 3.16.0 has them: no numbers, each with Documents/."""
    write_project(pace, "kowhai", "Kowhai Books")
    write_project(pace, "kowhai-budget", "Kowhai Books/Budget 2027", parent="kowhai")
    write_project(pace, "kowhai-web", "Kowhai Books/Website", parent="kowhai")
    write_project(pace, "sbr", "SBR")
    write_project(pace, "sbr-pace", "SBR/Pace", parent="sbr")
    (pace / "1 Projects/SBR/Pace/Documents/Brief.txt").write_text("Invented brief.\n", encoding="utf-8")
    (pace / "1 Projects/SBR/Pace/Documents/Sources").mkdir()
    (pace / "1 Projects/Kowhai Books/Notes").mkdir()  # not a project


def files(root: Path) -> dict:
    """Every file under a folder by its content, so a rename that loses or changes a file shows."""
    return sorted((path.name, path.read_bytes()) for path in root.rglob("*") if path.is_file())


class Case(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-folder-numbers-")
        self.pace = make_pace(Path(self._temp.name))

    def tearDown(self):
        self._temp.cleanup()

    def tool(self, *argv):
        return run(pr, "--pace", str(self.pace), *argv)

    def new(self, pid, name, parent=None, *extra):
        out, code = self.tool("project-new", "--id", pid, "--name", name, *(("--parent", parent) if parent else ()),
                              "--by", "Test", *extra)
        return out, code

    def preview(self):
        return run(pf, "preview", "--pace", str(self.pace))

    def apply(self, plan, words="Yes, number the folders.", by="Test"):
        return run(pf, "apply", "--pace", str(self.pace), "--plan", plan, "--go-ahead", words, "--by", by)


class NewProjectTests(Case):
    def test_new_projects_are_numbered_after_the_folders_beside_them(self):
        out, code = self.new("kowhai", "Kowhai Books")
        self.assertEqual((out["status"], code, out["folder"]), ("saved", 0, "1 Projects/01. Kowhai Books"), out)
        self.assertIn("(with 01. Documents/)", out["message"])
        self.assertTrue((self.pace / "1 Projects/01. Kowhai Books/01. Documents").is_dir())
        self.assertEqual(self.new("kowhai-budget", "Budget 2027", "kowhai")[0]["folder"], "1 Projects/01. Kowhai Books/02. Budget 2027")
        self.assertEqual(self.new("kowhai-web", "Website", "kowhai")[0]["folder"], "1 Projects/01. Kowhai Books/03. Website")
        self.assertEqual(self.new("garden", "Garden plans")[0]["folder"], "1 Projects/02. Garden plans")
        listed, _ = self.tool("projects")
        self.assertEqual({entry["id"]: (entry["name"], entry["number"]) for entry in listed["projects"]},
                         {"kowhai": ("Kowhai Books", 1), "kowhai-budget": ("Budget 2027", 2), "kowhai-web": ("Website", 3),
                          "garden": ("Garden plans", 2)})

    def test_a_repeat_finds_the_same_project_and_makes_any_folder_still_missing(self):
        self.new("kowhai", "Kowhai Books")
        out, code = self.new("kowhai", "Kowhai Books", None, "--folder", "Sources")
        self.assertEqual((out["status"], code, out["folder"]), ("already-saved", 0, "1 Projects/01. Kowhai Books"), out)
        self.assertTrue((self.pace / "1 Projects/01. Kowhai Books/01. Documents/Sources").is_dir())
        self.assertEqual(sorted(path.name for path in (self.pace / "1 Projects").iterdir() if path.is_dir()), ["01. Kowhai Books"])

    def test_a_folder_already_there_with_the_name_is_made_the_project(self):
        write_project(self.pace, "kowhai", "Kowhai Books")  # made before 3.16.0, not yet numbered
        (self.pace / "1 Projects/Garden plans").mkdir()     # the owner's own folder, to be made a project
        (self.pace / "1 Projects/05. Harbour walk").mkdir()  # already numbered by hand
        self.assertEqual(self.new("garden", "Garden plans")[0]["folder"], "1 Projects/Garden plans")
        self.assertTrue((self.pace / "1 Projects/Garden plans/01. Documents").is_dir())
        self.assertEqual(self.new("harbour", "Harbour walk")[0]["folder"], "1 Projects/05. Harbour walk")
        out, _ = self.new("kowhai-budget", "Budget 2027", "kowhai")
        self.assertEqual(out["folder"], "1 Projects/Kowhai Books/02. Budget 2027")  # Documents/ is 1, even unnumbered
        self.assertEqual(self.new("orchard", "Orchard")[0]["folder"], "1 Projects/06. Orchard")

    def test_two_folders_with_the_name_are_left_for_the_owner(self):
        (self.pace / "1 Projects/Website").mkdir()
        (self.pace / "1 Projects/03. Website").mkdir()
        out, code = self.new("web", "Website")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("already has 2 folders named Website: 03. Website, Website", out["message"])
        self.assertFalse(list((self.pace / "1 Projects").rglob("Pace project.md")))

    def test_a_name_that_starts_with_a_number_keeps_it_after_the_folders_number(self):
        (self.pace / "1 Projects/02. Notes").mkdir()
        out, _ = self.new("fitness", "24 Hour Fitness")
        self.assertEqual(out["folder"], "1 Projects/01. 24 Hour Fitness")
        listed, _ = self.tool("projects")
        self.assertEqual([(entry["name"], entry["number"]) for entry in listed["projects"]], [("24 Hour Fitness", 1)])
        out, _ = self.new("fit-two", "Fitness two")
        self.assertEqual(out["folder"], "1 Projects/03. Fitness two")  # 02 is the owner's own

    def test_a_folder_of_the_owners_own_numbered_99_holds_no_one_back_and_99_is_the_last(self):
        (self.pace / "1 Projects/99. Archive").mkdir()
        self.assertEqual(self.new("first", "First")[0]["folder"], "1 Projects/01. First")
        for number in range(2, 99):
            (self.pace / f"1 Projects/{number:02d}. Taken").mkdir()
        out, code = self.new("one-more", "One more")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("every number from 01 to 99 is taken in 1 Projects/", out["message"])
        self.assertFalse(list((self.pace / "1 Projects").glob("*One more")))

    def test_documents_cannot_be_a_projects_name_numbered_or_not(self):
        for name in ("Documents", "documents", "01. Documents", "04. DOCUMENTS"):
            with self.subTest(name=name):
                out, code = self.new("docs", name)
                self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertEqual(list((self.pace / "1 Projects").iterdir()), [self.pace / "1 Projects/.gitkeep"])

    def test_a_name_given_with_a_folder_number_is_refused(self):
        out, code = self.new("budget", "02. Budget 2027")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("'02. Budget 2027' starts as a numbered folder does, with two digits, a full stop and a space, so "
                      "they would be read as its number. Give the name without a number, such as 'Budget 2027': the folder "
                      "is numbered for it.", out["message"])
        self.assertEqual(list((self.pace / "1 Projects").iterdir()), [self.pace / "1 Projects/.gitkeep"])
        (self.pace / "1 Projects/02. Budget 2027").mkdir()  # by hand: the name without its number finds it
        self.assertEqual(self.new("budget", "Budget 2027")[0]["folder"], "1 Projects/02. Budget 2027")


class NameTests(unittest.TestCase):
    def test_a_folders_number_and_name(self):
        for name, expected in (("02. Budget 2027", (2, "Budget 2027")), ("01. Documents", (1, "Documents")),
                               ("Budget 2027", (None, "Budget 2027")), ("2 Views", (None, "2 Views")),
                               ("02 Budget 2027", (None, "02 Budget 2027")), ("24 Hour Fitness", (None, "24 Hour Fitness")),
                               ("2027 Plans", (None, "2027 Plans")), ("100. Next", (None, "100. Next")),
                               ("\uff12\uff10. Plans", (None, "\uff12\uff10. Plans")), ("03. 24 Hour Fitness", (3, "24 Hour Fitness")),
                               ("07.  Double space", (7, " Double space")), ("08.", (None, "08.")), ("08.x", (None, "08.x"))):
            with self.subTest(name=name):
                self.assertEqual(pr.folder_number(name), expected)
                self.assertEqual(pr.plain_name(name), expected[1])
        self.assertEqual(pr.numbered_name(4, "Website"), "04. Website")
        self.assertTrue(all(pr.is_working_dir(name) for name in ("Documents", "documents", "01. Documents", "01. DOCUMENTS")))
        self.assertFalse(any(pr.is_working_dir(name) for name in ("Documents old", "My Documents", "01. Documents/",
                                                                  "12. Documents", "01 Documents", "2024 Documents")))


class ReadingTests(Case):
    def test_pages_and_results_show_names_without_numbers(self):
        write_project(self.pace, "kowhai", "01. Kowhai Books")  # numbered by hand, so this holds whatever made them
        write_project(self.pace, "kowhai-budget", "01. Kowhai Books/02. Budget 2027", parent="kowhai")
        write_record(self.pace, "20261020T010000Z--kowhai-budget--num001", subject="Board pack", owed_by=OWNER, state="open",
                     due="2026-10-28")
        out, code = run(po, "--pace", str(self.pace), "--as-at", "2026-10-30T09:00:00+13:00", "--save")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        page = read(self.pace / out["page"])
        self.assertIn('<span class="side">Kowhai Books &rsaquo; Budget 2027</span>', page)
        self.assertEqual(out["needs_attention"][0]["project"], "Kowhai Books > Budget 2027")
        self.assertNotIn("02. Budget", page.split("<body>")[1])

    def test_one_projects_page_lists_its_numbered_documents(self):
        self.new("kowhai", "Kowhai Books")
        (self.pace / "1 Projects/01. Kowhai Books/01. Documents/Board pack.xlsx").write_text("Invented.", encoding="utf-8")
        out, _ = run(po, "--pace", str(self.pace), "--as-at", "2026-10-30T09:00:00+13:00", "--project", "kowhai", "--save")
        self.assertIn("<li>1 Projects/01. Kowhai Books/01. Documents/Board pack.xlsx</li>", read(self.pace / out["page"]))

    def test_an_older_path_finds_its_file_through_numbered_folders(self):
        old_layout(self.pace)
        plan, _ = self.preview()
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        brief = (self.pace / "1 Projects/02. SBR/02. Pace/01. Documents/Brief.txt").resolve()
        for recorded in ("1 Projects/SBR/Pace/Documents/Brief.txt", "Projects/SBR/Pace/Documents/Brief.txt",
                         "1 Projects/02. SBR/Pace/Documents/Brief.txt", "1 Projects/02. SBR/02. Pace/01. Documents/Brief.txt"):
            with self.subTest(recorded=recorded):
                self.assertEqual(pr.recorded_path(self.pace, recorded), brief)
        # A project folder comes before an ordinary folder of the same name; a path that leads nowhere, or to two
        # projects of one name, is left as it was written.
        (self.pace / "1 Projects/07. SBR").mkdir()
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/SBR/Pace/Documents/Brief.txt"), brief)
        (self.pace / "1 Projects/07. SBR/Pace project.md").write_text("---\nformat: project-1\nid: sbr-two\nparent: none\n"
                                                                      "created: 2026-08-01T09:00:00+12:00\nby: Test\n---\n",
                                                                      encoding="utf-8")
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/SBR/Pace/Documents/Brief.txt"),
                         (self.pace / "1 Projects/SBR/Pace/Documents/Brief.txt").resolve())
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/02. SBR/Gone/Brief.txt"),
                         (self.pace / "1 Projects/02. SBR/Gone/Brief.txt").resolve())


class FoldersToolTests(Case):
    def setUp(self):
        super().setUp()
        old_layout(self.pace)

    def test_preview_shows_each_new_name_and_changes_nothing(self):
        before = snapshot(self.pace)
        out, code = self.preview()
        self.assertEqual((out["status"], code), ("ready", 0), out)
        self.assertEqual(snapshot(self.pace), before)
        self.assertEqual([(rename["from"], rename["to"]) for rename in out["renames"]], [
            ("1 Projects/Kowhai Books/Budget 2027/Documents", "01. Documents"),
            ("1 Projects/Kowhai Books/Website/Documents", "01. Documents"),
            ("1 Projects/SBR/Pace/Documents", "01. Documents"),
            ("1 Projects/Kowhai Books/Documents", "01. Documents"),
            ("1 Projects/Kowhai Books/Budget 2027", "02. Budget 2027"),
            ("1 Projects/Kowhai Books/Website", "03. Website"),
            ("1 Projects/SBR/Documents", "01. Documents"),
            ("1 Projects/SBR/Pace", "02. Pace"),
            ("1 Projects/Kowhai Books", "01. Kowhai Books"),
            ("1 Projects/SBR", "02. SBR")])
        self.assertEqual(out["not_projects"], ["1 Projects/Kowhai Books/Notes"])
        for phrase in ("Numbering would rename 10 folders in 1 Projects/", "links between Excel workbooks",
                       "Power Query and Power BI file sources", "Close any file open from these folders",
                       "Not numbered, as they are not projects, and so listed after the numbered folders: "
                       "1 Projects/Kowhai Books/Notes/.", "Nothing was renamed."):
            self.assertIn(phrase, out["message"])
        self.assertEqual(out["plan"], pf.plan_id(out["renames"]))

    def test_apply_saves_its_record_first_then_numbers_every_folder_whole(self):
        before = files(self.pace / "1 Projects")
        plan, _ = self.preview()
        saved_first = []
        real = pr.rename_no_replace

        def rename(source, target):
            saved_first.append(bool(list((self.pace / "Record").glob("*--none--*.md"))))
            real(source, target)

        with mock.patch.object(pr, "rename_no_replace", rename):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code, out["renamed"]), ("numbered", 0, 10), out)
        self.assertEqual(set(saved_first), {True})
        self.assertEqual(files(self.pace / "1 Projects"), before)
        self.assertTrue((self.pace / "1 Projects/02. SBR/02. Pace/01. Documents/Sources").is_dir())
        self.assertTrue((self.pace / "1 Projects/01. Kowhai Books/Notes").is_dir())
        record = read(self.pace / out["file"])
        for line in ("kind: note", "subject: Numbering folders", "from: owner", "words: Yes, number the folders.", "by: Test",
                     "project: none", "1 Projects/SBR/Pace/Documents/ -> 01. Documents/", "1 Projects/SBR/ -> 02. SBR/"):
            self.assertIn(line, record)
        listed, _ = self.tool("projects")
        self.assertEqual(sorted((entry["name"], entry["number"]) for entry in listed["projects"]),
                         [("Budget 2027", 2), ("Kowhai Books", 1), ("Pace", 2), ("SBR", 2), ("Website", 3)])
        again, code = self.preview()
        self.assertEqual((again["status"], code), ("nothing-to-number", 0), again)

    def test_nothing_is_renamed_without_the_owners_words_the_plan_and_who(self):
        before = snapshot(self.pace)
        plan, _ = self.preview()
        for argv, status in ((["--plan", plan["plan"], "--go-ahead", " ", "--by", "Test"], "not-numbered"),
                             (["--plan", plan["plan"], "--go-ahead", "Yes.", "--by", " "], "not-numbered"),
                             (["--plan", "0" * 64, "--go-ahead", "Yes.", "--by", "Test"], "plan-changed")):
            with self.subTest(argv=argv):
                out, code = run(pf, "apply", "--pace", str(self.pace), *argv)
                self.assertEqual((out["status"], code), (status, 1), out)
                self.assertEqual(snapshot(self.pace), before)
        # A project made after the preview changes the plan, so the owner sees the new one first.
        self.new("orchard", "Orchard")
        out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code), ("plan-changed", 1), out)
        self.assertTrue((self.pace / "1 Projects/SBR").is_dir())

    def test_a_folder_already_numbered_keeps_its_number_and_the_rest_take_the_lowest_free(self):
        (self.pace / "1 Projects/Kowhai Books/Website").rename(self.pace / "1 Projects/Kowhai Books/05. Website")
        write_project(self.pace, "kowhai-zeta", "Kowhai Books/Zeta", parent="kowhai")
        plan, _ = self.preview()
        renames = dict((rename["from"], rename["to"]) for rename in plan["renames"])
        self.assertEqual(renames["1 Projects/Kowhai Books/Budget 2027"], "02. Budget 2027")
        self.assertEqual(renames["1 Projects/Kowhai Books/Zeta"], "03. Zeta")  # the lowest free, so before 05. Website
        self.assertNotIn("1 Projects/Kowhai Books/05. Website", renames)
        self.assertIn("1 Projects/Kowhai Books/05. Website/Documents", renames)
        self.assertIn("1 project folder already starts with a number and keeps it: 1 Projects/Kowhai Books/05. Website/, "
                      "shown as Website.", plan["message"])

    def test_a_project_with_two_documents_folders_is_left_for_the_owner(self):
        (self.pace / "1 Projects/SBR/Pace/01. Documents").mkdir()
        plan, _ = self.preview()
        self.assertNotIn("1 Projects/SBR/Pace/Documents", [rename["from"] for rename in plan["renames"]])
        self.assertTrue(any("has more than one Documents folder" in clash for clash in plan["clashes"]))
        out, _ = run(pc, "--pace", str(self.pace))
        warned = [item for item in out["findings"] if item["level"] == "warning" and "Documents folders" in item["message"]]
        self.assertEqual(len(warned), 1, out["findings"])
        self.assertIn("1 Projects/SBR/Pace/ has 2 Documents folders: 01. Documents/, Documents/", warned[0]["message"])
        self.assertIn("move each file into 01. Documents/, the one the tools use, never over a file of the same name: "
                      "where both folders hold one, ask the owner which to keep.", warned[0]["fix"])

    def test_a_folder_that_cannot_be_renamed_keeps_its_name_and_the_rest_are_numbered(self):
        before = files(self.pace / "1 Projects")
        plan, _ = self.preview()
        real = pr.rename_no_replace
        stuck = self.pace / "1 Projects/Kowhai Books/Budget 2027/Documents"

        def rename(source, target):
            if Path(source) == stuck:
                raise PermissionError(13, "The process cannot access the file", str(source))
            real(source, target)

        with mock.patch.object(pr, "rename_no_replace", rename):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code, out["renamed"], out["planned"]), ("partly-numbered", 1, 9, 10), out)
        self.assertEqual(len(out["not_renamed"]), 1)
        self.assertIn("1 Projects/Kowhai Books/Budget 2027/Documents/: could not be renamed", out["message"])
        self.assertIn("no right to rename it, or a new path too long for Windows", out["message"])
        self.assertEqual(files(self.pace / "1 Projects"), before)
        self.assertTrue((self.pace / "1 Projects/01. Kowhai Books/02. Budget 2027/Documents").is_dir())
        correction = read(self.pace / "Record" / f"{out['correction']}.md")
        for line in (f"corrects: {out['record']}", "from: agent", "Of the 10 folders this numbering set out to rename, 9 "
                     "were renamed and checked, and 1 kept its name", "1 Projects/Kowhai Books/Budget 2027/Documents/: could "
                     "not be renamed", "Renamed and checked:", "1 Projects/SBR/Pace/Documents/ -> 01. Documents/"):
            self.assertIn(line, " ".join(correction.split()))
        # It keeps failing in the same place: each run numbers what it can, and says which still has its name.
        with mock.patch.object(pr, "rename_no_replace", lambda source, target: (_ for _ in ()).throw(
                PermissionError(13, "Denied", str(source)))):
            later, _ = self.preview()
            self.assertEqual([rename["from"] for rename in later["renames"]], ["1 Projects/01. Kowhai Books/02. Budget 2027/Documents"])
            again, code = self.apply(later["plan"])
        self.assertEqual((again["status"], code, again["renamed"]), ("not-numbered", 1, 0), again)
        self.assertIn("Nothing was renamed; 1 folder kept its name: 1 Projects/01. Kowhai Books/02. Budget 2027/Documents/: "
                      "could not be renamed (Denied).", again["message"])
        later, _ = self.preview()
        self.assertEqual(self.apply(later["plan"])[0]["status"], "numbered")
        self.assertEqual(files(self.pace / "1 Projects"), before)
        self.assertEqual(len(list((self.pace / "Record").glob("*--none--*.md"))), 5)  # 3 runs, 2 with a correction

    def test_a_folder_that_cannot_be_read_keeps_its_name_and_the_rest_are_numbered(self):
        shut, real = self.pace / "1 Projects/SBR", os.scandir

        def scandir(path="."):
            if Path(path) == shut:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path)

        with mock.patch.object(pr.os, "scandir", scandir):
            out, code = self.preview()
            self.assertEqual((out["status"], code), ("ready", 0), out)
            self.assertIn("1 Projects/SBR/ keeps its name, and so does everything in it, as it could not be read", out["message"])
            self.assertFalse([rename for rename in out["renames"] if rename["from"].startswith("1 Projects/SBR")])
            applied, code = self.apply(out["plan"])
            self.assertEqual((applied["status"], code), ("numbered", 0), applied)
        self.assertEqual(sorted(path.name for path in (self.pace / "1 Projects").iterdir() if path.is_dir()),
                         ["01. Kowhai Books", "SBR"])
        self.assertTrue((self.pace / "1 Projects/SBR/Pace/Documents/Brief.txt").is_file())

    def test_a_project_that_cannot_be_read_leaves_everything_in_it_as_it_is(self):
        (self.pace / "1 Projects/Kowhai Books/Pace project.md").write_text("Not a project file.\n", encoding="utf-8")
        out, code = self.preview()
        self.assertEqual((out["status"], code), ("ready", 0), out)
        self.assertIn("1 Projects/Kowhai Books/ keeps its name, and so does everything in it, as its Pace project.md could "
                      "not be read", out["message"])
        self.assertNotIn("has no Pace project.md", out["message"])  # its own projects are not taken for a checkout's
        self.assertFalse([rename for rename in out["renames"] if rename["from"].startswith("1 Projects/Kowhai Books")])
        self.assertIn("1 Projects/SBR/Pace", [rename["from"] for rename in out["renames"]])

    def test_a_documents_folder_reached_through_a_link_keeps_its_name(self):
        documents = self.pace / "1 Projects/SBR/Pace/Documents"
        elsewhere = Path(self._temp.name) / "Documents kept elsewhere"
        shutil.move(str(documents), str(elsewhere))
        try:
            documents.symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("folder links cannot be made here")
        plan, _ = self.preview()
        self.assertNotIn("1 Projects/SBR/Pace/Documents", [rename["from"] for rename in plan["renames"]])
        self.assertIn("1 Projects/SBR/Pace/Documents/ keeps its name, as it is reached through a link or junction",
                      plan["message"])
        out, _ = self.apply(plan["plan"])
        self.assertEqual((out["status"], out["renamed"]), ("numbered", 9), out)
        self.assertTrue((self.pace / "1 Projects/02. SBR/02. Pace/Documents").is_symlink())
        self.assertTrue((elsewhere / "Brief.txt").is_file())

    def test_a_runs_list_of_renames_is_kept_small_enough_for_its_record(self):
        with mock.patch.object(pf, "LIST_ROOM", 420):
            first, _ = self.preview()
        self.assertEqual((len(first["renames"]), first["more"]), (8, 2))  # all but 1 Projects/ itself
        self.assertLessEqual(len(pf.rename_lines(first["renames"]).encode("utf-8")), 420)
        with mock.patch.object(pf, "LIST_ROOM", 10):
            alone, _ = self.preview()
        self.assertEqual((len(alone["renames"]), alone["more"]), (1, 9))  # a folder too large for it still goes alone

    def test_a_record_of_the_renames_too_large_or_not_confirmed_renames_nothing(self):
        before = snapshot(self.pace / "1 Projects")
        plan, _ = self.preview()
        out, code = self.apply(plan["plan"], words="Yes. " * 14000)
        self.assertEqual((out["status"], code, out["record"]), ("not-numbered", 1, None), out)
        self.assertIn("more than a record may be (65,536); give the owner's go-ahead in fewer words", out["message"])
        real = pf.pr.save_record

        def save_record(pace, options, fields, body):
            saved, code = real(pace, options, fields, body)
            return pr.result("placed-not-confirmed", f"Placed {saved['file']} but could not read it back (invented).", False,
                             request=saved["request"], file=saved["file"])

        with mock.patch.object(pf.pr, "save_record", save_record):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code), ("not-numbered", 1), out)
        self.assertIn(f"{out['record']}.md may hold it although nothing was renamed, so tell the owner not to rely on it.",
                      out["message"])
        self.assertEqual(snapshot(self.pace / "1 Projects"), before)

    def test_what_waits_on_the_owner_is_named_in_the_preview_and_the_health_check(self):
        (self.pace / "1 Projects/02. SBR").write_text("A file where SBR/ would go once numbered.\n", encoding="utf-8")
        for number in range(3, 100):
            (self.pace / "1 Projects/Kowhai Books" / pr.numbered_name(number, "Taken")).mkdir()
        plan, _ = self.preview()
        renames = [rename["from"] for rename in plan["renames"]]
        self.assertNotIn("1 Projects/SBR", renames)
        self.assertIn("1 Projects/02. SBR/ is already there, so 1 Projects/SBR/ keeps its name", plan["message"])
        self.assertEqual([path for path in renames if path.startswith("1 Projects/Kowhai Books/")],
                         ["1 Projects/Kowhai Books/Budget 2027/Documents", "1 Projects/Kowhai Books/Website/Documents",
                          "1 Projects/Kowhai Books/Documents", "1 Projects/Kowhai Books/Budget 2027"])
        self.assertIn("1 Projects/Kowhai Books/Website/ keeps its name, as every number from 01 to 99 is taken in "
                      "1 Projects/Kowhai Books/", plan["message"])
        out, _ = run(pc, "--pace", str(self.pace))
        held = [item for item in out["findings"] if "cannot be numbered until the owner sorts" in item["message"]]
        self.assertEqual(held[0]["files"], ["1 Projects/Kowhai Books/Website", "1 Projects/SBR"], out["findings"])
        for phrase in ("where a folder beside it would have the same name once numbered, or one is already there under its "
                       "new name, rename one of them", "; and where every number from 01 to 99 is taken, free one by hand"):
            self.assertIn(phrase, held[0]["fix"])

    def test_a_folder_gone_by_the_time_it_is_renamed_is_said_to_be_gone(self):
        plan, _ = self.preview()
        real, moved = pr.rename_no_replace, Path(self._temp.name) / "Moved away"

        def rename(source, target):
            real(source, target)
            if Path(source) == self.pace / "1 Projects/SBR/Documents":  # someone moves SBR/Pace/ away meanwhile
                shutil.move(str(self.pace / "1 Projects/SBR/Pace"), str(moved))

        with mock.patch.object(pr, "rename_no_replace", rename):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code, out["renamed"]), ("partly-numbered", 1, 9), out)
        self.assertEqual(out["not_renamed"], ["1 Projects/SBR/Pace/: no longer there as it was"])
        self.assertTrue((moved / "01. Documents/Brief.txt").is_file())

    def test_a_correction_without_reasons_still_says_what_happened_to_each(self):
        plan, _ = self.preview()
        renames = plan["renames"]
        outcomes = [(renames[0], "not-renamed", f"{renames[0]['from']}/: could not be renamed (Access is denied)"),
                    (renames[1], "unchecked", f"{renames[1]['from']}/ -> {renames[1]['to']}/: renamed, but did not read back")]
        outcomes += [(rename, "renamed", "") for rename in renames[2:]]
        text = " ".join(pf.outcome_text(len(renames), outcomes, reasons=False).split())
        for phrase in ("Of the 10 folders this numbering set out to rename, 8 were renamed and checked, 1 was renamed but "
                       "not checked afterwards, and 1 kept its name, for a later run to number.",
                       "Kept its name: 1 Projects/Kowhai Books/Budget 2027/Documents/ The reasons Windows gave were too long",
                       "Renamed, but not checked afterwards; look at each by hand: 1 Projects/Kowhai Books/Website/Documents/ "
                       "-> 01. Documents/", "Every other folder that record lists was renamed and checked."):
            self.assertIn(phrase, text)
        self.assertNotIn("Access is denied", text)

    def test_the_health_check_counts_every_folder_waiting_and_changes_nothing(self):
        before = snapshot(self.pace)
        with mock.patch.object(pc.pf, "BATCH", 4):  # the health check's own copy of the folders tool
            out, _ = run(pc, "--pace", str(self.pace))
        self.assertEqual(snapshot(self.pace), before)
        noted = [item["message"] for item in out["findings"] if item["check"] == "folder-numbers"]
        self.assertEqual(len(noted), 1, out["findings"])
        self.assertIn("10 folders in 1 Projects/ are not numbered yet", noted[0])
        self.assertIn(" and 7 more.", noted[0])

    def test_an_older_path_is_found_past_a_file_under_the_old_name(self):
        plan, _ = self.preview()
        self.apply(plan["plan"])
        (self.pace / "1 Projects/SBR").write_text("A file now where the folder was.\n", encoding="utf-8")
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/SBR/Pace/Documents/Brief.txt"),
                         (self.pace / "1 Projects/02. SBR/02. Pace/01. Documents/Brief.txt").resolve())

    def test_folders_under_their_names_from_before_3_11_stop_numbering(self):
        (self.pace / "1 Projects").rename(self.pace / "Projects")
        out, code = self.preview()
        self.assertEqual((out["status"], code), ("not-ready", 1), out)
        self.assertIn("rename Projects/", out["message"])

    def test_a_file_that_would_pass_excels_limit_is_named(self):
        deep = self.pace / "1 Projects/SBR/Pace/Documents/Sources"
        room = pr.EXCEL_PATH_LIMIT - max(len(str(self.pace.resolve())) + 1, pr.TYPICAL_ROOT) - len(str(deep.relative_to(self.pace))) - 1
        name = "x" * (room - 4) + ".txt"  # just inside the limit now; numbering adds 3 for SBR, 3 for Pace and 3 for Documents
        (deep / name).write_text("Invented.", encoding="utf-8")
        out, _ = self.preview()
        self.assertEqual(out["too_long_after"], [f"1 Projects/SBR/Pace/Documents/Sources/{name}"])
        self.assertIn("1 file would have a path longer than Excel's 218-character limit once numbered", out["message"])

    def test_a_large_folder_is_numbered_over_more_than_one_run_in_the_same_order(self):
        with mock.patch.object(pf, "BATCH", 4):
            first, _ = self.preview()
            # Whole folders at a time, the deepest first: the three Documents folders deepest down, then no more fit.
            self.assertEqual((len(first["renames"]), first["more"]), (3, 7))
            self.assertIn("7 more folders can be numbered by a later run.", first["message"])
            out, _ = self.apply(first["plan"])
            self.assertEqual((out["status"], out["renamed"]), ("numbered", 3))
            self.assertIn("7 more folders can be numbered by another run: preview again.", out["message"])
            runs = 1
            while True:
                plan, _ = self.preview()
                if plan["status"] == "nothing-to-number":
                    break
                self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
                runs += 1
        self.assertGreater(runs, 2)
        tree = sorted(path.relative_to(self.pace / "1 Projects").as_posix() for path in (self.pace / "1 Projects").rglob("*")
                      if path.is_dir())
        self.assertEqual(tree, ["01. Kowhai Books", "01. Kowhai Books/01. Documents", "01. Kowhai Books/02. Budget 2027",
                                "01. Kowhai Books/02. Budget 2027/01. Documents", "01. Kowhai Books/03. Website",
                                "01. Kowhai Books/03. Website/01. Documents", "01. Kowhai Books/Notes", "02. SBR",
                                "02. SBR/01. Documents", "02. SBR/02. Pace", "02. SBR/02. Pace/01. Documents",
                                "02. SBR/02. Pace/01. Documents/Sources"])


class HealthCheckTests(Case):
    def test_folders_not_numbered_yet_are_noted_until_they_are(self):
        old_layout(self.pace)
        out, _ = run(pc, "--pace", str(self.pace))
        noted = [item for item in out["findings"] if item["check"] == "folder-numbers"]
        self.assertEqual(len(noted), 1, out["findings"])
        self.assertEqual(noted[0]["level"], "note")
        self.assertIn("10 folders in 1 Projects/ are not numbered yet, so new projects, which are, sort above them", noted[0]["message"])
        self.assertIn("folders tool", noted[0]["fix"])
        plan, _ = self.preview()
        self.apply(plan["plan"])
        out, _ = run(pc, "--pace", str(self.pace))
        self.assertEqual([item for item in out["findings"] if item["check"] == "folder-numbers"], [])

    def test_what_numbering_leaves_as_it_is_is_not_waited_for(self):
        old_layout(self.pace)
        lantern = self.pace / "1 Projects/SBR/Pace/Code/pace/example/1 Projects/Maple Lantern"  # a repository checkout
        (lantern / "Documents").mkdir(parents=True)
        (lantern / "Pace project.md").write_text("---\nformat: project-1\nid: maple-lantern\nparent: none\ncreated: "
                                                 "2026-08-01T09:00:00+12:00\nby: Test\n---\n\nInvented.\n", encoding="utf-8")
        plan, _ = self.preview()
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertTrue((self.pace / "1 Projects/02. SBR/02. Pace/Code/pace/example/1 Projects/Maple Lantern").is_dir())
        out, _ = run(pc, "--pace", str(self.pace))
        self.assertEqual([item for item in out["findings"] if item["check"] == "folder-numbers"], [])

    def test_repository_references_keep_their_places_by_name(self):
        self.new("kowhai", "Kowhai Books")
        self.new("kowhai-budget", "Budget 2027", "kowhai")
        reference = self.pace / "Repos/Kowhai Books/Budget 2027/budget-model/Pace repo.md"
        reference.parent.mkdir(parents=True)
        reference.write_text("# Budget model\n\nHome project id: kowhai-budget\n", encoding="utf-8")
        out, _ = run(pc, "--pace", str(self.pace))
        self.assertEqual([item for item in out["findings"] if item["check"] == "repos"], [])
        numbered = self.pace / "Repos/01. Kowhai Books/02. Budget 2027/budget-model"
        numbered.parent.mkdir(parents=True)
        shutil.move(str(reference.parent), str(numbered))
        out, _ = run(pc, "--pace", str(self.pace))
        self.assertEqual([item for item in out["findings"] if item["check"] == "repos"], [])


class ExampleAndHelpTests(unittest.TestCase):
    def test_the_example_is_numbered_throughout(self):
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "example"
            shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("__pycache__"))
            out, code = run(pf, "preview", "--pace", str(copy))
        self.assertEqual((out["status"], code), ("nothing-to-number", 0), out)

    def test_the_help_says_how_folders_are_numbered(self):
        projects = " ".join(read(HELP / "projects.md").split())
        for phrase in ("Each project folder in `1 Projects/` starts with its number, a full stop and a space, such as "
                       "`02. Budget 2027`, so it keeps its place as more are added",
                       "at the top from `01.`, and inside a project from `02.`, after the project's `01. Documents/`",
                       "**Two digits, `01` to `99`**, so folders list in order even where names are sorted as plain text",
                       "Pages and chat show a project's name without its number: `Budget 2027`, not `02. Budget 2027`.",
                       "A name that starts with digits but no full stop, such as `24 Hour Fitness` or `2026 Tax return`, has "
                       "no number", "as `03. 24 Hour Fitness`", "the other project folders take the lowest numbers no "
                       "folder beside them starts with, in the order a file browser lists them now, as Windows File Explorer "
                       "does near enough (ignoring case, accents, hyphens and apostrophes)",
                       "so those without a number come after the numbered ones",
                       "Any other number before Documents makes an ordinary folder",
                       "a folder reached through a link or junction", "a correction of the record says what happened to each",
                       "links between Excel workbooks in different folders, Power Query "
                       "and Power BI file sources", "`apply` saves a record of the renames and reads it back",
                       "Records keep the paths they were saved with."):
            self.assertIn(phrase, projects)
        commands = re.findall(r"^python3 Product/Tools/pace_folders\.py (\w+)", read(HELP / "projects.md"), re.M)
        self.assertEqual(commands, ["preview", "apply"])
        self.assertIn("each folder numbered so it keeps its place, with its files in `01. Documents/`",
                      read(PACE_FOLDER / "Pace.md"))
        self.assertIn("## Numbered project folders from 3.16.0", read(HELP / "updates.md"))
        self.assertIn("An update never renames a folder of yours.", read(HELP / "updates.md"))
        self.assertIn("without their numbers", read(HELP / "repositories.md"))
        self.assertIn("folders the folders tool would number that are not numbered yet", read(HELP / "health-check.md"))
        self.assertIn("a record saved before its project folders were numbered", read(HELP / "records.md"))
        self.assertNotIn("1 Projects/Kowhai Books/", read(HELP / "confirmations.md"))


if __name__ == "__main__":
    unittest.main()
