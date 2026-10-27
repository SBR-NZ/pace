"""The third independent review of 3.16.0 (14d283c): each finding has a test here that fails on that commit.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import read, run, write_project
from test_folder_numbers import Case, pc, pf, pr

HELP = Path(pr.__file__).resolve().parent.parent / "Help"
CHANGELOG = HELP.parent.parent.parent / "CHANGELOG.md"
# The Russian Windows' words when a file in the folder is open: 150 bytes, where English takes 79.
IN_USE_RU = "Процесс не может получить доступ к файлу, так как этот файл занят другим процессом"


def renames_of(plan: dict) -> dict:
    return {rename["from"]: rename["to"] for rename in plan["renames"]}


def failing(*stuck: Path, error: str = "Access is denied"):
    """A rename that fails for these folders, or for every folder when none is named, and works for the rest."""
    real = pr.rename_no_replace

    def rename(source, target):
        if not stuck or Path(source) in stuck:
            raise PermissionError(13, error, str(source))
        real(source, target)
    return mock.patch.object(pr, "rename_no_replace", rename)


def top_names(pace: Path) -> list:
    return sorted(path.name for path in (pace / "1 Projects").iterdir() if path.is_dir())


def folder_notes(pace: Path) -> list:
    out, _ = run(pc, "--pace", str(pace))
    return [item["message"] for item in out["findings"] if item["check"] == "folder-numbers"]


class OrderTests(Case):
    """1 (medium): the folders not numbered yet were placed by name between numbered folders whose numbers were not in
    name order, and fell back to after the highest project, or to the lowest free number, so a folder that kept its
    name lost its place on the next run, and a first run could put a folder above the rest."""

    def test_a_folder_that_kept_its_name_gets_its_place_beside_a_project_made_since(self):
        write_project(self.pace, "apple", "Apple")  # made before 3.16.0
        write_project(self.pace, "mango", "Mango")
        self.assertEqual(self.new("zeta", "Zeta")[0]["folder"], "1 Projects/01. Zeta")
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {"1 Projects/Apple": "02. Apple", "1 Projects/Mango": "03. Mango"})
        with failing(self.pace / "1 Projects/Apple"):
            self.assertEqual(self.apply(plan["plan"])[0]["status"], "partly-numbered")
        later, _ = self.preview()
        self.assertEqual(renames_of(later), {"1 Projects/Apple": "02. Apple"})

    def test_a_folder_that_kept_its_name_gets_its_place_beside_the_owners_99(self):
        (self.pace / "1 Projects/99. Archive").mkdir()  # the owner's own, not a project
        for name in ("Apple", "Banana", "Cherry", "Damson"):
            write_project(self.pace, name.lower(), name)
        plan, _ = self.preview()
        with failing(self.pace / "1 Projects/Banana"):
            self.assertEqual(self.apply(plan["plan"])[0]["status"], "partly-numbered")
        later, _ = self.preview()
        self.assertEqual(renames_of(later), {"1 Projects/Banana": "02. Banana"})
        self.apply(later["plan"])
        self.assertEqual(top_names(self.pace), ["01. Apple", "02. Banana", "03. Cherry", "04. Damson", "99. Archive"])

    def test_the_owners_numbered_folders_do_not_reorder_the_rest(self):
        for name in ("05. Admin", "99. Archive"):
            (self.pace / "1 Projects" / name).mkdir()  # the owner's own, not projects
        write_project(self.pace, "apple", "Apple")
        write_project(self.pace, "budget", "Budget")
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {"1 Projects/Apple": "01. Apple", "1 Projects/Budget": "02. Budget"})

    def test_projects_made_first_keep_their_numbers_and_the_rest_keep_their_order(self):
        for pid, name in (("apple", "Apple"), ("kowhai", "Kowhai Books"), ("mango", "Mango")):
            write_project(self.pace, pid, name)
        self.new("zeta", "Zeta")
        self.new("garden", "Garden")
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {"1 Projects/Apple": "03. Apple", "1 Projects/Kowhai Books": "04. Kowhai Books",
                          "1 Projects/Mango": "05. Mango"})
        with failing(self.pace / "1 Projects/Kowhai Books"):
            self.apply(plan["plan"])
        later, _ = self.preview()
        self.assertEqual(renames_of(later), {"1 Projects/Kowhai Books": "04. Kowhai Books"})


class RecordedPathTests(Case):
    """2 (medium): a recorded path took a folder under its old name whenever one was there, so an empty folder made
    again under that name, as OneDrive can, hid the numbered one and the file was not found."""

    def test_a_folder_under_the_old_name_does_not_hide_the_numbered_one(self):
        write_project(self.pace, "kowhai", "Kowhai Books")  # made before 3.16.0
        letter = self.pace / "1 Projects/Kowhai Books/Documents/Engagement letter.txt"
        letter.write_text("Invented engagement letter.\n", encoding="utf-8")
        act = {"act-file": ["1 Projects/Kowhai Books/Documents/Engagement letter.txt"],
               "act-sha256": [pr.sha256(letter.read_bytes())]}
        plan, _ = self.preview()
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        numbered = (self.pace / "1 Projects/01. Kowhai Books/01. Documents/Engagement letter.txt").resolve()
        (self.pace / "1 Projects/Kowhai Books").mkdir()  # made again, empty
        self.assertEqual(pr.recorded_path(self.pace, act["act-file"][0]), numbered)
        self.assertIsNone(pr.check_act(self.pace, act))
        (self.pace / "1 Projects/01. Kowhai Books/Documents").mkdir()  # and an empty Documents/ beside 01. Documents/
        self.assertEqual(pr.recorded_path(self.pace, act["act-file"][0]), numbered)
        self.assertIsNone(pr.check_act(self.pace, act))


class CorrectionSizeTests(Case):
    """3 (low): only the list of renames was kept small, and each failure also carried Windows' own words, so a whole run
    failing on a Windows that words them at length gave a correction too large to save."""

    def test_a_whole_run_failing_in_long_words_still_has_its_correction(self):
        for top in range(1, 5):
            write_project(self.pace, f"client-{top}", f"Client {top:02d}")
            for sub in range(1, 75):
                write_project(self.pace, f"client-{top}-{sub}", f"Client {top:02d}/Engagement {sub:02d} for the coming year",
                              parent=f"client-{top}")
        plan, _ = self.preview()
        self.assertEqual(len(plan["renames"]), 300)
        with failing(error=IN_USE_RU):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code, out["renamed"]), ("not-numbered", 1, 0), out)
        self.assertIsNotNone(out["correction"], out["message"])
        correction = " ".join(read(self.pace / "Record" / f"{out['correction']}.md").split())
        self.assertIn("none was renamed and checked, and 300 kept their names", correction)
        for rename in plan["renames"]:
            self.assertIn(f" {rename['from']}/ ", correction)
        self.assertIn("The reasons Windows gave were too long to keep in this record.", correction)
        self.assertIn(IN_USE_RU, out["not_renamed"][0])  # the result still gives them
        history, _ = self.tool("history", "--request", out["record"])
        self.assertEqual(history["current"], [out["correction"]])


class HealthCheckNoteTests(Case):
    """4 (low): the health check's note named folders the folders tool will not number until the owner acts, as if
    the tool would, and said nothing at all once any project file could not be read."""

    def test_a_folder_held_back_by_a_clash_is_named_for_the_owner_to_sort_out(self):
        (self.pace / "1 Projects/03. Website").mkdir()  # the owner's own
        write_project(self.pace, "web", "Website")
        plan, _ = self.preview()
        self.apply(plan["plan"])
        self.assertEqual(self.preview()[0]["status"], "nothing-to-number")
        self.assertEqual(folder_notes(self.pace),
                         ["1 folder in 1 Projects/ cannot be numbered until the owner sorts it out: 1 Projects/Website."])

    def test_a_project_file_that_cannot_be_read_does_not_hide_the_rest(self):
        for name in ("Apple", "Banana", "Cherry", "Damson"):
            write_project(self.pace, name.lower(), name)
        (self.pace / "1 Projects/Damson/Pace project.md").write_text("Not a project file.\n", encoding="utf-8")
        notes = folder_notes(self.pace)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("6 folders in 1 Projects/ are not numbered yet", notes[0])
        self.assertNotIn("Damson", notes[0])


class ExplorerOrderTests(Case):
    """5 (low): runs of digits sorted before punctuation, hyphens and apostrophes counted as characters, and Ð, Ħ, Ŋ, Ŧ
    and ı sorted after Z, where Windows File Explorer lists them otherwise."""

    def test_punctuation_hyphens_and_apostrophes_sort_as_explorer_sorts_them(self):
        for names, expected in ((("2026 Tax return", "_Admin", "Kowhai Books"), ["_Admin", "2026 Tax return", "Kowhai Books"]),
                                (("Co-op Bank", "Coffee Club", "Cola Account"), ["Coffee Club", "Cola Account", "Co-op Bank"]),
                                (("O'Brien Family", "Oak Lodge"), ["Oak Lodge", "O'Brien Family"]),
                                (("Smith-Jones", "Smithfield"), ["Smithfield", "Smith-Jones"])):
            with self.subTest(names=names):
                self.assertEqual(sorted(names, key=pf.browser_order), expected)
        for count, name in enumerate(("2026 Tax return", "_Admin", "Kowhai Books", "Co-op Bank", "Coffee Club")):
            write_project(self.pace, f"place-{count}", name)
        plan, _ = self.preview()
        self.assertEqual(sorted(value for key, value in renames_of(plan).items() if key.count("/") == 1),
                         ["01. _Admin", "02. 2026 Tax return", "03. Coffee Club", "04. Co-op Bank", "05. Kowhai Books"])

    def test_every_latin_letter_sorts_beside_its_own_letter(self):
        letters = [chr(code) for code in range(0x00C0, 0x0180) if chr(code).isalpha()]
        for letter in letters:
            with self.subTest(letter=letter):
                self.assertLess(pf.browser_order(f"{letter}x"), pf.browser_order("Zzz"))
        write_project(self.pace, "zebra", "Zebra")
        write_project(self.pace, "dordevic", "Ðorđević")
        plan, _ = self.preview()
        self.assertEqual(renames_of(plan)["1 Projects/Ðorđević"], "01. Ðorđević")


class WindowsPathLimitTests(Case):
    """6 (low): only files that crossed Excel's 218 characters were named, not one already past it that numbering took
    past the 260 at which other Office and Windows tools stop."""

    def test_a_file_numbering_takes_past_260_characters_is_named(self):
        write_project(self.pace, "kowhai", "Kowhai Books")
        write_project(self.pace, "kowhai-budget", "Kowhai Books/Budget 2027", parent="kowhai")
        documents = self.pace / "1 Projects/Kowhai Books/Budget 2027/Documents"
        root = max(len(str(self.pace.resolve())) + 1, pr.TYPICAL_ROOT)
        rel = f"{documents.relative_to(self.pace).as_posix()}/"
        name = "n" * (255 - root - len(rel) - len(".docx")) + ".docx"  # 255 now, 267 once three folders are numbered
        (documents / name).write_text("Invented.", encoding="utf-8")
        plan, _ = self.preview()
        self.assertEqual(plan["past_windows_limit_after"], [f"{rel}{name}"])
        self.assertIn("1 file would have a path of 260 characters or more once numbered, where Office and other "
                      "Windows tools cannot open it", plan["message"])


class UnreadableProjectsFolderTests(Case):
    """7 (low): when 1 Projects/ itself could not be listed, the preview said every folder already had its number."""

    def test_an_unreadable_projects_folder_stops_numbering(self):
        write_project(self.pace, "kowhai", "Kowhai Books")
        shut, real = self.pace / "1 Projects", os.scandir

        def scandir(path="."):
            if Path(path) == shut:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path)

        with mock.patch.object(pr.os, "scandir", scandir):
            out, code = self.preview()
        self.assertEqual((out["status"], code), ("not-ready", 1), out)
        self.assertIn("No folder can be numbered until this is sorted out: 1 Projects/ could not be listed", out["message"])


class FullStopNameTests(Case):
    """8 (low): a name made before 3.16.0 that starts with two digits, a full stop and a space, as German writes a date,
    counts as numbered, and nothing said so or how to keep the digits in a new project's name."""

    def test_a_name_like_a_date_with_a_full_stop_is_explained(self):
        projects = " ".join(read(HELP / "projects.md").split())
        self.assertIn("A folder already named with two digits, a full stop and a space, such as `24. Dezember Feier`, counts "
                      "as numbered, so if those digits are part of its name, rename it first, such as to "
                      "`24 Dezember Feier`.", projects)
        self.assertIn("such as `24. Dezember Feier`, counts as numbered", read(CHANGELOG))
        out, code = self.new("markt", "24. Dezember Markt")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("If the digits are part of the name, write it another way, such as '24 Dezember Markt'.", out["message"])


class TextTests(Case):
    """9 (low): the preview said a numbered folder that is not a project was listed after the numbered folders, and the
    help said a project with two Documents folders was left as it is, where only those two folders are."""

    def test_only_folders_without_a_number_are_said_to_come_after_the_numbered_ones(self):
        write_project(self.pace, "apple", "Apple")
        (self.pace / "1 Projects/03. Website").mkdir()
        (self.pace / "1 Projects/Notes").mkdir()
        plan, _ = self.preview()
        self.assertIn("Not numbered, as they are not projects, and so listed after the numbered folders: 1 Projects/Notes/.",
                      plan["message"])
        self.assertNotIn("03. Website", plan["message"])

    def test_the_help_says_only_the_two_documents_folders_keep_their_names(self):
        for text in (" ".join(read(HELP / "projects.md").split()), " ".join(read(CHANGELOG).split())):
            self.assertIn("both Documents folders of a project that has two", text)
            self.assertNotIn("and a project with two Documents folders", text)


if __name__ == "__main__":
    unittest.main()
