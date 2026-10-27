"""The second independent review of 3.16.0 (46ac9e4): each finding has a test here that fails on that commit.

Folder names are made with the tools' own numbered_name, so each test fails on that commit for the reason the review
gave, not for the form numbers took then. Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import stat
import sys
import tempfile
import types
import unicodedata
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import read, run, snapshot, write_project
from test_folder_numbers import Case, files, old_layout, pc, pf, pr

pu = pc.pu
HELP = Path(pr.__file__).resolve().parent.parent / "Help"
OLDER = {"tag": "v3.15.0", "files": {"Tools/pace_record.py": b"def archive_folder(request): ..."}}
# Windows' own words when a file in the folder is open, which a rename failure gives.
IN_USE = "The process cannot access the file because it is being used by another process"


def numbered(*parts) -> str:
    """A path in 1 Projects/ from (number, name) pairs and plain names, numbered as the tools number folders."""
    return "/".join(["1 Projects"] + [pr.numbered_name(*part) if isinstance(part, tuple) else part for part in parts])


def renames_of(plan: dict) -> dict:
    return {rename["from"]: rename["to"] for rename in plan["renames"]}


def failing(*stuck: Path, error: str = "Access is denied"):
    """A rename that fails for these folders, as Windows fails one with a file open in it, and works for the rest."""
    real = pr.rename_no_replace

    def rename(source, target):
        if not stuck or Path(source) in stuck:
            raise PermissionError(13, error, str(source), None, str(target))
        real(source, target)
    return mock.patch.object(pr, "rename_no_replace", rename)


class TwoDigitNameTests(Case):
    """1 (high): a name made before 3.16.0 that starts with two digits, such as 24 Hour Fitness, was still read as a
    number, so the folders beside it were numbered from 25, pages showed Hour Fitness, and 99 Bikes left no number."""

    def test_a_name_that_starts_with_two_digits_is_its_name(self):
        for name in ("24 Hour Fitness", "42 Below", "99 Bikes"):
            with self.subTest(name=name):
                self.assertEqual(pr.folder_number(name), (None, name))
                self.assertEqual(pr.plain_name(name), name)
        for pid, name in (("fitness", "24 Hour Fitness"), ("below", "42 Below"), ("bikes", "99 Bikes"),
                          ("orchard", "Apple Orchard"), ("kowhai", "Kowhai Books")):
            write_project(self.pace, pid, name)  # made before 3.16.0
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {f"1 Projects/{name}": pr.numbered_name(number, name) for number, name in enumerate(
                             ("24 Hour Fitness", "42 Below", "99 Bikes", "Apple Orchard", "Kowhai Books"), 1)})
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        listed, _ = self.tool("projects")
        self.assertEqual(sorted(entry["name"] for entry in listed["projects"]),
                         ["24 Hour Fitness", "42 Below", "99 Bikes", "Apple Orchard", "Kowhai Books"])
        self.assertEqual(self.new("garden", "Garden plans")[0]["folder"], numbered((6, "Garden plans")))

    def test_a_project_named_99_something_holds_no_new_project_back(self):
        write_project(self.pace, "bikes", "99 Bikes")  # made before 3.16.0
        out, code = self.new("garden", "Garden plans")
        self.assertEqual((out["status"], code, out["folder"]), ("saved", 0, numbered((1, "Garden plans"))), out)
        listed, _ = self.tool("projects")
        self.assertIn(("99 Bikes", None), [(entry["name"], entry["number"]) for entry in listed["projects"]])
        plan, _ = self.preview()
        self.assertEqual(renames_of(plan)["1 Projects/99 Bikes"], pr.numbered_name(2, "99 Bikes"))


class FreeNumberTests(Case):
    """2 (medium): a new number only ever came after the highest a project folder had, so projects numbered in tens,
    or the owner's own 99. Archive made a project, left 81 or 98 numbers free and still said every number was taken."""

    def test_numbers_in_tens_leave_the_ones_below_free(self):
        for number, name in enumerate(("Admin", "Clients", "Plans", "Money", "People", "Sites", "Events", "Grants",
                                       "Archive"), 1):
            write_project(self.pace, name.lower(), pr.numbered_name(number * 10, name))
        for count in range(1, 10):
            out, _ = self.new(f"extra-{count}", f"Extra {count}")
            self.assertEqual(out["folder"], numbered((90 + count, f"Extra {count}")), out)
        out, code = self.new("extra-10", "Extra 10")
        self.assertEqual((out["status"], code, out["folder"]), ("saved", 0, numbered((1, "Extra 10"))), out)
        self.assertEqual(self.new("extra-11", "Extra 11")[0]["folder"], numbered((2, "Extra 11")))
        # Only once all 99 are taken does it say so, and then it is true.
        taken = {pr.folder_number(path.name)[0] for path in (self.pace / "1 Projects").iterdir()}
        for number in sorted(set(range(1, 100)) - taken):
            (self.pace / "1 Projects" / pr.numbered_name(number, "Taken")).mkdir()
        out, code = self.new("one-more", "One more")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("every number from 01 to 99 is taken in 1 Projects/", out["message"])

    def test_the_owners_own_99_archive_made_a_project_holds_no_one_back(self):
        (self.pace / "1 Projects" / pr.numbered_name(99, "Archive")).mkdir()
        out, _ = self.new("archive", "Archive")
        self.assertEqual(out["folder"], numbered((99, "Archive")), out)
        out, code = self.new("garden", "Garden plans")
        self.assertEqual((out["status"], code, out["folder"]), ("saved", 0, numbered((1, "Garden plans"))), out)

    def test_the_folders_tool_uses_a_free_number_below_too(self):
        write_project(self.pace, "archive", pr.numbered_name(99, "Archive"))
        write_project(self.pace, "zeta", "Zeta")  # sorts after Archive, where no number is free
        plan, _ = self.preview()
        self.assertEqual(renames_of(plan)["1 Projects/Zeta"], pr.numbered_name(1, "Zeta"))

    def test_the_help_and_the_changelog_say_so(self):
        self.assertIn("Once those run out, it gets a free number below", read(HELP / "projects.md"))
        self.assertIn("takes a free one below when none is left above", read(HELP.parent.parent.parent / "CHANGELOG.md"))


class DocumentsBesideANumberedOneTests(Case):
    """3 (medium): renaming Documents/ beside an ordinary folder numbered like it, such as 07. Documents/, left two
    folders a recorded path could mean, so every path recorded into that Documents/ before numbering broke."""

    def setUp(self):
        super().setUp()
        write_project(self.pace, "kowhai", "Kowhai Books")  # made before 3.16.0
        self.client = self.pace / "1 Projects/Kowhai Books"
        self.letter = self.client / "Documents/Engagement letter.txt"
        self.letter.write_text("Invented engagement letter.\n", encoding="utf-8")
        older = self.client / pr.numbered_name(7, "Documents")
        older.mkdir()
        (older / "Old letter.txt").write_text("Invented older letter.\n", encoding="utf-8")
        self.act = {"act-file": ["1 Projects/Kowhai Books/Documents/Engagement letter.txt"],
                    "act-sha256": [pr.sha256(self.letter.read_bytes())]}

    def test_paths_recorded_before_numbering_still_find_their_files(self):
        self.assertIsNone(pr.check_act(self.pace, self.act))
        plan, _ = self.preview()
        self.assertEqual(renames_of(plan)["1 Projects/Kowhai Books/Documents"], pr.numbered_name(1, "Documents"))
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        client = self.pace / numbered((1, "Kowhai Books"))
        self.assertEqual(pr.recorded_path(self.pace, self.act["act-file"][0]),
                         (client / pr.numbered_name(1, "Documents") / "Engagement letter.txt").resolve())
        self.assertIsNone(pr.check_act(self.pace, self.act))
        older = f"1 Projects/Kowhai Books/{pr.numbered_name(7, 'Documents')}/Old letter.txt"
        self.assertEqual(pr.recorded_path(self.pace, older),
                         (client / pr.numbered_name(7, "Documents") / "Old letter.txt").resolve())


class CheckoutTests(Case):
    """4 (medium): projects inside a folder that is not a project, such as a repository checkout, were renamed, so a
    preview planned renames of folders that git tracks."""

    def setUp(self):
        super().setUp()
        old_layout(self.pace)
        self.code = self.pace / "1 Projects/SBR/Pace/Code"
        lantern = self.code / "pace/example/1 Projects/Maple Lantern"
        for folder, pid, parent in ((lantern, "maple-lantern", "none"), (lantern / "Campaign", "maple-campaign", "maple-lantern")):
            (folder / "Documents").mkdir(parents=True)
            (folder / "Pace project.md").write_text(f"---\nformat: project-1\nid: {pid}\nparent: {parent}\ncreated: "
                                                   "2026-08-01T09:00:00+12:00\nby: Test\n---\n\nInvented.\n", encoding="utf-8")

    def test_a_checkouts_projects_keep_their_names(self):
        before = snapshot(self.code)
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)
        self.assertFalse([path for path in renames_of(plan) if path.startswith("1 Projects/SBR/Pace/Code")], plan["renames"])
        self.assertIn("2 projects inside 1 Projects/SBR/Pace/Code/ keep their names, as 1 Projects/SBR/Pace/Code/ has no "
                      "Pace project.md: it may be a repository checkout", plan["message"])
        self.assertEqual(renames_of(plan)["1 Projects/SBR/Pace"], pr.numbered_name(2, "Pace"))
        out, _ = self.apply(plan["plan"])
        self.assertEqual(out["status"], "numbered", out)
        self.assertEqual(snapshot(self.pace / numbered((2, "SBR"), (2, "Pace"), "Code")), before)


class CorrectionTests(Case):
    """5 (low): the correction had no size limit, so a run of failed renames with Windows' messages could not be saved;
    it gave only counts, not which folders were renamed; and the result named it even when it was not saved."""

    def test_a_correction_for_a_whole_run_of_failures_is_saved_and_names_each_folder(self):
        for parent in range(1, 4):
            name = f"Client number {parent} with a long enough name"
            write_project(self.pace, f"client-{parent}", name)
            for child in range(1, 61):
                write_project(self.pace, f"client-{parent}-{child}", f"{name}/Engagement {child:02d} for the year ahead",
                              parent=f"client-{parent}")
        plan, _ = self.preview()
        self.assertGreater(len(plan["renames"]), 150)
        with failing(error=IN_USE):
            out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code, out["renamed"]), ("not-numbered", 1, 0), out)
        self.assertIsNotNone(out["correction"], out["message"])
        correction = " ".join(read(self.pace / "Record" / f"{out['correction']}.md").split())
        for rename in plan["renames"]:
            self.assertIn(f"{rename['from']}/: could not be renamed ({IN_USE})", correction)
        self.assertNotIn(str(self.pace), correction)

    def test_the_correction_is_the_current_account_and_says_which_were_renamed(self):
        old_layout(self.pace)
        plan, _ = self.preview()
        with failing(self.pace / "1 Projects/Kowhai Books/Budget 2027/Documents"):
            out, _ = self.apply(plan["plan"])
        self.assertEqual(out["status"], "partly-numbered", out)
        history, _ = self.tool("history", "--request", out["record"])
        self.assertEqual(history["current"], [out["correction"]], history)
        correction = " ".join(read(self.pace / "Record" / f"{out['correction']}.md").split())
        self.assertIn(f"Renamed and checked: 1 Projects/Kowhai Books/Website/Documents/ -> {pr.numbered_name(1, 'Documents')}/",
                      correction)
        for rename in out["renames"]:
            self.assertIn(f"{rename['from']}/ -> {rename['to']}/", correction)

    def test_a_correction_that_is_not_saved_is_not_named(self):
        old_layout(self.pace)
        plan, _ = self.preview()
        real = pf.pr.save_record

        def save_record(pace, options, fields, body):
            if fields.get("corrects"):
                return pr.result("not-saved", "Not saved: invented refusal.", False, request=fields["request"][0])
            return real(pace, options, fields, body)

        with failing(self.pace / "1 Projects/SBR/Pace/Documents"), mock.patch.object(pf.pr, "save_record", save_record):
            out, _ = self.apply(plan["plan"])
        self.assertIsNone(out["correction"], out)
        self.assertIn("could not be saved (Not saved: invented refusal.)", out["message"])
        self.assertEqual(len(list((self.pace / "Record").glob("*--none--*.md"))), 1)


class ReadBackTests(Case):
    """6 (low): a folder renamed whose check afterwards failed was recorded as keeping its name, though its files were
    already in the numbered folder."""

    def test_a_rename_that_does_not_read_back_is_said_to_be_renamed_and_not_checked(self):
        old_layout(self.pace)
        plan, _ = self.preview()
        real, top = pr.rename_no_replace, self.pace / "1 Projects/Kowhai Books"

        def rename(source, target):
            real(source, target)
            if Path(source) == top:
                top.mkdir()  # the old name appears again straight after, as OneDrive can make it

        with mock.patch.object(pr, "rename_no_replace", rename):
            out, code = self.apply(plan["plan"])
        correction = " ".join(read(self.pace / "Record" / f"{out['correction']}.md").split())
        self.assertIn("Renamed, but not checked afterwards; look at each by hand: 1 Projects/Kowhai Books/ -> "
                      f"{pr.numbered_name(1, 'Kowhai Books')}/: renamed, but did not read back as it should", correction)
        self.assertNotIn("Kept", correction)
        self.assertEqual((out["status"], code, out["not_renamed"]), ("partly-numbered", 1, []), out)
        self.assertEqual(len(out["not_checked"]), 1)
        self.assertTrue((self.pace / numbered((1, "Kowhai Books"), (2, "Budget 2027"), "Pace project.md")).is_file())


class OrderAfterAFailureTests(Case):
    """7 (low): a folder whose rename failed was numbered after the folders beside it on the next run, so it lost the
    place the owner knew it by."""

    def test_a_folder_that_kept_its_name_gets_its_place_next_time(self):
        for name in ("Apple", "Banana", "Cherry", "Damson"):
            write_project(self.pace, name.lower(), name)
        plan, _ = self.preview()
        with failing(self.pace / "1 Projects/Banana"):
            self.assertEqual(self.apply(plan["plan"])[0]["status"], "partly-numbered")
        later, _ = self.preview()
        self.assertEqual(renames_of(later), {"1 Projects/Banana": pr.numbered_name(2, "Banana")})
        self.assertEqual(self.apply(later["plan"])[0]["status"], "numbered")
        self.assertEqual(sorted(path.name for path in (self.pace / "1 Projects").iterdir() if path.is_dir()),
                         [pr.numbered_name(number, name) for number, name in enumerate(("Apple", "Banana", "Cherry", "Damson"), 1)])


class UpdaterGuardTests(Case):
    """8 (low): the updater's guard missed a numbered project inside one not numbered yet, and stopped a release from
    being installed over folders never numbered, such as one named 24 Hour Fitness."""

    def test_a_numbered_project_inside_one_not_numbered_yet_stops_an_older_release(self):
        write_project(self.pace, "kowhai", "Kowhai Books")  # made before 3.16.0
        self.assertEqual(pu.numbers_stop(self.pace, OLDER), "")
        out, _ = self.new("kowhai-budget", "Budget 2027", "kowhai")
        self.assertEqual(out["folder"], numbered("Kowhai Books", (2, "Budget 2027")), out)
        self.assertIn("Install Pace 3.16.0 or later instead", pu.numbers_stop(self.pace, OLDER))

    def test_folders_never_numbered_do_not_stop_an_older_release(self):
        write_project(self.pace, "fitness", "24 Hour Fitness")
        write_project(self.pace, "kowhai", "Kowhai Books")
        checkout = self.pace / "1 Projects/Kowhai Books/Code/pace/example/1 Projects" / pr.numbered_name(1, "Maple Lantern")
        (checkout / pr.numbered_name(1, "Documents")).mkdir(parents=True)
        (checkout / "Pace project.md").write_text("---\nformat: project-1\nid: maple-lantern\nparent: none\ncreated: "
                                                  "2026-08-01T09:00:00+12:00\nby: Test\n---\n\nInvented.\n", encoding="utf-8")
        self.assertEqual(pu.numbers_stop(self.pace, OLDER), "")


class LinkedProjectsFolderTests(Case):
    """9 (low): when 1 Projects/ itself was a link or junction, nothing was ever numbered, and the preview said each
    project would be numbered where it really is."""

    def test_a_projects_folder_that_is_a_link_is_numbered(self):
        old_layout(self.pace)
        real = Path(self._temp.name) / "Projects kept elsewhere"
        shutil.move(str(self.pace / "1 Projects"), str(real))
        try:
            (self.pace / "1 Projects").symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("folder links cannot be made here")
        before = files(real)
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)
        self.assertEqual(renames_of(plan)["1 Projects/Kowhai Books"], pr.numbered_name(1, "Kowhai Books"))
        self.assertNotIn("is numbered where it really is", plan["message"])
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertTrue((real / pr.numbered_name(1, "Kowhai Books") / pr.numbered_name(2, "Budget 2027")).is_dir())
        self.assertTrue((self.pace / "1 Projects").is_symlink())
        self.assertEqual(files(real), before)


class BrowserOrderTests(Case):
    """10 (low): a digit that is not 0 to 9, such as Ethiopic ፩, stopped the preview, and letters with no accent to take
    off, such as Æ, Ø and Ł, sorted after Z."""

    def test_no_digit_of_any_script_stops_the_preview(self):
        digits = [chr(code) for code in range(0x110000) if chr(code).isdigit() and chr(code) not in "0123456789"]
        self.assertGreater(len(digits), 60)
        for digit in digits:
            pf.browser_order(f"Item 1{digit}")  # nothing raised
        write_project(self.pace, "item", "Item 1፩")
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)

    def test_letters_with_no_accent_to_take_off_sort_where_a_browser_puts_them(self):
        names = ("Zebra", "Ørsted", "Æble", "Łódź", "Apple", "Oak", "Straße", "Strand")
        for count, name in enumerate(names):
            write_project(self.pace, f"place-{count}", name)
        plan, _ = self.preview()
        order = ("Æble", "Apple", "Łódź", "Oak", "Ørsted", "Strand", "Straße", "Zebra")
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {f"1 Projects/{name}": pr.numbered_name(number, name) for number, name in enumerate(order, 1)})


class LetterCaseTests(Case):
    """11 (low): names were matched with casefold, which makes Strasse and Straße one name where Windows keeps two, so
    project-new made a project of the owner's other folder."""

    def test_strasse_and_strasse_with_an_eszett_stay_two_names(self):
        self.assertNotEqual(pr.name_key("Hauptstrasse Apartments"), pr.name_key("Hauptstraße Apartments"))
        self.assertEqual(pr.name_key("HAUPTSTRASSE apartments"), pr.name_key("Hauptstrasse Apartments"))
        self.assertEqual(pr.name_key(unicodedata.normalize("NFD", "Café")), pr.name_key("Café"))
        (self.pace / "1 Projects/Hauptstraße Apartments").mkdir()  # the owner's own folder
        out, code = self.new("strasse", "Hauptstrasse Apartments")
        self.assertEqual((out["status"], code, out["folder"]), ("saved", 0, numbered((1, "Hauptstrasse Apartments"))), out)
        self.assertFalse((self.pace / "1 Projects/Hauptstraße Apartments/Pace project.md").exists())


class JunctionTests(Case):
    """12 (low, from reading the code): the path-length check followed Windows junctions, which os.walk takes for
    folders, so a junction that loops could take it to its limit. A junction is shown here by its reparse tag."""

    def test_the_path_length_check_does_not_walk_into_a_junction(self):
        write_project(self.pace, "kowhai", "Kowhai Books")
        documents = self.pace / "1 Projects/Kowhai Books/Documents"
        junction = documents / "Linked"
        junction.mkdir()
        root = max(len(str(self.pace.resolve())) + 1, pr.TYPICAL_ROOT)
        # Each file's path is 2 characters inside Excel's limit now, and past it once both folders are numbered.
        for folder in (documents, junction):
            rel = f"{folder.relative_to(self.pace).as_posix()}/"
            name = "n" * (pr.EXCEL_PATH_LIMIT - 2 - root - len(rel) - len(".txt")) + ".txt"
            (folder / name).write_text("Invented.", encoding="utf-8")
        plan, _ = self.preview()
        real_lstat = os.lstat

        def lstat(path, *args, **kwargs):
            st = real_lstat(path, *args, **kwargs)
            if Path(path) == junction:
                return types.SimpleNamespace(st_mode=st.st_mode, st_reparse_tag=0xA0000003)
            return st

        with mock.patch.object(os, "lstat", lstat):
            _, found, every_file = pf.too_long(self.pace, plan["renames"])
        self.assertTrue(stat.S_ISDIR(os.lstat(junction).st_mode))
        self.assertEqual([Path(path).parent.name for path in found], ["Documents"], found)
        self.assertTrue(every_file)


if __name__ == "__main__":
    unittest.main()
