"""The fourth independent review of 3.16.0 (aadebe4): each finding has a test here that fails on that commit.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import read, run, write_project
from test_folder_numbers import Case, make_pace, pc, pf, pr

HELP = Path(pr.__file__).resolve().parent.parent / "Help"
CHANGELOG = HELP.parent.parent.parent / "CHANGELOG.md"


def renames_of(plan: dict) -> dict:
    return {rename["from"]: rename["to"] for rename in plan["renames"]}


def failing(*stuck: Path):
    """A rename that fails for these folders, as Windows fails one with a file open in it, and works for the rest."""
    real = pr.rename_no_replace

    def rename(source, target):
        if Path(source) in stuck:
            raise PermissionError(13, "The process cannot access the file", str(source))
        real(source, target)
    return mock.patch.object(pr, "rename_no_replace", rename)


def preview(pace: Path) -> dict:
    return run(pf, "preview", "--pace", str(pace))[0]


def apply(pace: Path, plan: str) -> dict:
    return run(pf, "apply", "--pace", str(pace), "--plan", plan, "--go-ahead", "Yes, number them.", "--by", "Test")[0]


def new(pace: Path, pid: str, name: str, parent: str = "") -> dict:
    return run(pr, "--pace", str(pace), "project-new", "--id", pid, "--name", name, *(("--parent", parent) if parent else ()),
               "--by", "Test")[0]


def listed(folder: Path) -> list:
    return sorted(path.name for path in folder.iterdir() if path.is_dir())


# Layouts Pace can really produce: projects made before 3.16.0, projects project-new made since, and the owner's own
# numbered folders. Each is (folders of the owner's own, projects project-new made first, projects made before 3.16.0).
LAYOUTS = (((), (), ("Budget", "Lodge", "Smith")),
           (("05. Admin",), ("Estate", "Lodge"), ("Apple", "Cherry", "Garden", "Harbour", "Mango")),
           (("98. Archive",), (), ("Apple", "Budget", "Cherry", "Damson")),
           ((), ("Zeta", "Garden"), ("Apple", "Kowhai Books", "Mango")))


def build(base: Path, owners, made_first, older) -> Path:
    pace = make_pace(base)
    for name in owners:
        (pace / "1 Projects" / name).mkdir()
    for name in made_first:
        new(pace, name.lower().replace(" ", "-"), name)
    for name in older:
        write_project(pace, name.lower().replace(" ", "-"), name)
    return pace


class RetryTests(Case):
    """1 (medium): each run placed the folders waiting among a different set of numbered folders, so a folder that kept
    its name could get another number on the next run, though no new project had taken the one planned for it."""

    def test_a_project_made_between_runs_does_not_move_a_folder_that_kept_its_name(self):
        for name in ("Budget", "Lodge", "Smith"):
            write_project(self.pace, name.lower(), name)
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 1},
                         {"1 Projects/Budget": "01. Budget", "1 Projects/Lodge": "02. Lodge", "1 Projects/Smith": "03. Smith"})
        with failing(self.pace / "1 Projects/Lodge"):
            self.assertEqual(self.apply(plan["plan"])[0]["status"], "partly-numbered")
        self.assertEqual(self.new("cherry", "Cherry")[0]["folder"], "1 Projects/04. Cherry")
        later, _ = self.preview()
        self.assertEqual(renames_of(later), {"1 Projects/Lodge": "02. Lodge"})

    def test_every_folder_that_kept_its_name_gets_the_number_planned_for_it(self):
        for owners, made_first, older in LAYOUTS:
            for stuck in older:
                with self.subTest(layout=(owners, made_first, older), stuck=stuck), \
                        tempfile.TemporaryDirectory(prefix="pace-retry-") as temp:
                    pace = build(Path(temp), owners, made_first, older)
                    first = renames_of(preview(pace))
                    planned = [first[f"1 Projects/{name}"] for name in sorted(older, key=pf.browser_order)]
                    self.assertEqual(planned, sorted(planned))  # they keep their order among themselves
                    with failing(pace / "1 Projects" / stuck):
                        self.assertEqual(apply(pace, preview(pace)["plan"])["status"], "partly-numbered")
                    self.assertEqual(renames_of(preview(pace)), {f"1 Projects/{stuck}": first[f"1 Projects/{stuck}"]})


class HighNumberTests(Case):
    """2 (medium): the folders waiting after an owner's folder numbered in the 90s took the few numbers above it and
    the rest dropped to low ones, so they lost their order, and one could be put above everything."""

    def test_the_folders_waiting_keep_their_order_beside_a_high_number(self):
        (self.pace / "1 Projects/98. Archive").mkdir()
        for name in ("Apple", "Budget", "Cherry", "Damson"):
            write_project(self.pace, name.lower(), name)
        plan, _ = self.preview()
        self.apply(plan["plan"])
        self.assertEqual(listed(self.pace / "1 Projects"), ["01. Apple", "02. Budget", "03. Cherry", "04. Damson", "98. Archive"])

    def test_eleven_after_90_archive_keep_their_order(self):
        (self.pace / "1 Projects/90. Archive").mkdir()
        names = ("Budget", "Cafe", "Dairy", "Estate", "Farm", "Garden", "Harbour", "Iwi", "Kowhai", "Tui", "Zeta")
        for name in names:
            write_project(self.pace, name.lower(), name)
        plan, _ = self.preview()
        self.apply(plan["plan"])
        self.assertEqual(listed(self.pace / "1 Projects"),
                         [pr.numbered_name(number, name) for number, name in enumerate(names, 1)] + ["90. Archive"])

    def test_inside_a_project_too(self):
        write_project(self.pace, "kowhai", "Kowhai Books")
        (self.pace / "1 Projects/Kowhai Books/98. Old").mkdir()
        for name in ("Apple", "Budget", "Pear", "Zeta"):
            write_project(self.pace, name.lower(), f"Kowhai Books/{name}", parent="kowhai")
        plan, _ = self.preview()
        self.assertEqual({key: value for key, value in renames_of(plan).items() if key.count("/") == 2},
                         {"1 Projects/Kowhai Books/Apple": "02. Apple", "1 Projects/Kowhai Books/Budget": "03. Budget",
                          "1 Projects/Kowhai Books/Documents": "01. Documents", "1 Projects/Kowhai Books/Pear": "04. Pear",
                          "1 Projects/Kowhai Books/Zeta": "05. Zeta"})


class HyphenDigitsTests(Case):
    """3 (low): hyphens were passed over before runs of digits were taken, so 2025-26 read as the number 202526 and a
    financial year sorted after the next."""

    def test_digits_either_side_of_a_hyphen_are_two_numbers(self):
        for names in (("FY2025-26 Annual accounts", "FY2026-27 Annual accounts", "FY2027 Budget"),
                      ("2026-03-15 Site visit", "2026-10-01 Board", "2027 Plan"), ("Stage 9", "Stage 10-12", "Stage 13")):
            with self.subTest(names=names):
                self.assertEqual(sorted(reversed(names), key=pf.browser_order), list(names))
        for count, name in enumerate(("FY2027 Budget", "FY2026-27 Annual accounts", "FY2025-26 Annual accounts")):
            write_project(self.pace, f"year-{count}", name)
        plan, _ = self.preview()
        self.assertEqual(sorted(value for key, value in renames_of(plan).items() if key.count("/") == 1),
                         ["01. FY2025-26 Annual accounts", "02. FY2026-27 Annual accounts", "03. FY2027 Budget"])


class NameThatIsNotTextTests(Case):
    """4 (low): a project folder whose name is not valid text, as Linux can hold, stopped the whole health check, which
    now plans the numbering."""

    def test_such_a_folder_keeps_its_name_and_the_check_still_runs(self):
        try:
            odd = os.fsencode(str(self.pace / "1 Projects")) + b"/Caf\xe9 accounts"
            os.mkdir(odd)
            os.mkdir(odd + b"/Documents")
            with open(odd + b"/Pace project.md", "w", encoding="utf-8") as handle:
                handle.write("---\nformat: project-1\nid: cafe\nparent: none\ncreated: 2026-08-01T09:00:00+12:00\nby: Test\n"
                             "---\n\nInvented.\n")
        except (OSError, UnicodeError, ValueError):
            self.skipTest("a folder name that is not valid text cannot be made here")
        write_project(self.pace, "apple", "Apple")
        out, code = run(pc, "--pace", str(self.pace))
        self.assertNotEqual(out["status"], "not-checked", out)
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)
        self.assertIn("1 Projects/Caf\\udce9 accounts/ keeps its name, and so does everything in it, as its name is not "
                      "valid text", plan["message"])
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertIn("01. Apple", listed(self.pace / "1 Projects"))


class PathBoundaryTests(Case):
    """5 (low): a path that numbering took to exactly 260 characters was not named, though Windows' limit counts the null
    that ends a path, so 259 is the longest it opens."""

    def test_a_path_that_reaches_260_is_named_and_one_at_259_is_not(self):
        write_project(self.pace, "kowhai", "Kowhai Books")
        write_project(self.pace, "kowhai-budget", "Kowhai Books/Budget 2027", parent="kowhai")
        documents = self.pace / "1 Projects/Kowhai Books/Budget 2027/Documents"
        root = max(len(str(self.pace.resolve())) + 1, pr.TYPICAL_ROOT)
        rel = f"{documents.relative_to(self.pace).as_posix()}/"
        names = {}
        for length, stem in ((248, "a"), (247, "b")):  # numbering adds 12, 4 for each of three folders: 260 and 259
            names[length] = stem * (length - root - len(rel) - len(".docx")) + ".docx"
            (documents / names[length]).write_text("Invented.", encoding="utf-8")
        plan, _ = self.preview()
        self.assertEqual(plan["past_windows_limit_after"], [f"{rel}{names[248]}"])


class TextTests(Case):
    """6 (low): the help promised order the code did not keep, and the health check told the owner to rename a folder
    held back because every number from 01 to 99 was taken."""

    def test_the_help_says_how_numbers_are_given(self):
        projects = " ".join(read(HELP / "projects.md").split())
        for phrase in ("the other project folders take the lowest numbers no folder beside them starts with, in the order a "
                       "file browser lists them now", "So they keep their order among themselves, and a folder already "
                       "numbered, such as the owner's own `05. Admin`, keeps its place among them by its number.",
                       "a later run gives the folders still waiting the lowest numbers then free, in the same order"):
            self.assertIn(phrase, projects)
        changelog = " ".join(read(CHANGELOG).split())
        self.assertIn("the other project folders take the lowest numbers free, in the order a file browser lists them now",
                      changelog)
        self.assertIn("a later run gives the folders still waiting the lowest numbers then free, in the same order", changelog)

    def test_a_folder_held_because_every_number_is_taken_is_not_told_to_be_renamed(self):
        for number in range(1, 100):
            (self.pace / "1 Projects" / pr.numbered_name(number, "Taken")).mkdir()
        write_project(self.pace, "zeta", "Zeta")
        out, _ = run(pc, "--pace", str(self.pace))
        held = [item for item in out["findings"] if "cannot be numbered until the owner sorts" in item["message"]]
        self.assertEqual(len(held), 1, out["findings"])
        self.assertIn("where every number from 01 to 99 is taken, free one by hand", held[0]["fix"])
        self.assertNotIn("rename one of them", held[0]["fix"])


if __name__ == "__main__":
    unittest.main()
