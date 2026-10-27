"""The fifth independent review of 3.16.0 (f289f33): each finding has a test here that fails on that commit.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import read, run, write_project
from test_folder_numbers import Case, pc, pf, pr

HELP = Path(pr.__file__).resolve().parent.parent / "Help"
CHANGELOG = HELP.parent.parent.parent / "CHANGELOG.md"


def flat(path: Path) -> str:
    return " ".join(read(path).split())


def held_notes(pace: Path) -> list:
    out, _ = run(pc, "--pace", str(pace))
    return [item for item in out["findings"] if "cannot be numbered until the owner sorts" in item["message"]]


class RetryPromiseTests(Case):
    """1 (low): the help promised a folder that kept its name the number planned for it unless a new project took that
    number, though each run gives the lowest numbers then free, so any folder made, removed or renamed beside it can
    move it."""

    def test_the_promise_says_what_can_move_a_number(self):
        promise = ("a later run gives the folders still waiting the lowest numbers then free, in the same order, so each "
                   "gets the number planned for it unless a folder beside it has been made, removed or renamed since")
        self.assertIn(promise, flat(HELP / "projects.md"))
        self.assertIn(promise, flat(CHANGELOG))
        self.assertIn("unless a folder beside them has been made, removed or renamed since", " ".join(pf.numbers_for.__doc__.split()))

    def test_folders_that_kept_their_names_in_a_project_get_their_numbers_when_nothing_changed(self):
        write_project(self.pace, "kowhai", "Kowhai Books")
        for name in ("Apple", "Budget", "Cherry", "Damson"):
            write_project(self.pace, f"kowhai-{name.lower()}", f"Kowhai Books/{name}", parent="kowhai")
        plan, _ = self.preview()
        first = {key: value for key, value in ((rename["from"], rename["to"]) for rename in plan["renames"])}
        stuck = [self.pace / "1 Projects/Kowhai Books/Budget", self.pace / "1 Projects/Kowhai Books/Damson"]
        real = pr.rename_no_replace

        def rename(source, target):
            if Path(source) in stuck:
                raise PermissionError(13, "Access is denied", str(source))
            real(source, target)

        with mock.patch.object(pr, "rename_no_replace", rename):
            self.assertEqual(self.apply(plan["plan"])[0]["status"], "partly-numbered")
        later, _ = self.preview()
        self.assertEqual({rename["from"]: rename["to"] for rename in later["renames"]},
                         {"1 Projects/01. Kowhai Books/Budget": first["1 Projects/Kowhai Books/Budget"],
                          "1 Projects/01. Kowhai Books/Damson": first["1 Projects/Kowhai Books/Damson"]})
        self.assertEqual((first["1 Projects/Kowhai Books/Budget"], first["1 Projects/Kowhai Books/Damson"]),
                         ("03. Budget", "05. Damson"))


class AdminExampleTests(Case):
    """2 (low): the help said a folder already numbered higher, such as 05. Admin, comes after the folders newly
    numbered, which holds only while four or fewer are waiting."""

    def test_a_numbered_folder_keeps_its_place_among_them_by_its_number(self):
        (self.pace / "1 Projects/05. Admin").mkdir()
        names = ("Apple", "Budget", "Cherry", "Damson", "Estate", "Farm", "Garden")
        for name in names:
            write_project(self.pace, name.lower(), name)
        plan, _ = self.preview()
        self.apply(plan["plan"])
        self.assertEqual(sorted(path.name for path in (self.pace / "1 Projects").iterdir() if path.is_dir()),
                         ["01. Apple", "02. Budget", "03. Cherry", "04. Damson", "05. Admin", "06. Estate", "07. Farm",
                          "08. Garden"])
        self.assertIn("a folder already numbered, such as the owner's own `05. Admin`, keeps its place among them by its "
                      "number", flat(HELP / "projects.md"))
        self.assertNotIn("comes after them", flat(HELP / "projects.md"))


class LineBreakNameTests(Case):
    """3 (low): a project folder whose name holds a line break or a carriage return passed as one a record can hold, so
    the preview was ready but every apply refused, without saying which folder."""

    def test_such_a_folder_keeps_its_name_and_the_rest_are_numbered(self):
        try:
            write_project(self.pace, "old", "Old\rName")
        except (OSError, ValueError):
            self.skipTest("a folder name with a carriage return cannot be made here")
        write_project(self.pace, "apple", "Apple")
        plan, code = self.preview()
        self.assertEqual((plan["status"], code), ("ready", 0), plan)
        self.assertIn("1 Projects/Old\\rName/ keeps its name, and so does everything in it, as its name is not valid text or "
                      "holds a line break or another control character", plan["message"])
        out, code = self.apply(plan["plan"])
        self.assertEqual((out["status"], code), ("numbered", 0), out)
        self.assertTrue((self.pace / "1 Projects/Old\rName/Documents").is_dir())
        self.assertFalse(pf.writable("Two \nlines") or pf.writable("Tab\there") or pf.writable("Line break"))
        self.assertTrue(pf.writable("Café accounts"))


class NotTextNamedInCheckTests(Case):
    """4 (low): the health check said nothing of a project folder left as it is because a record could not hold its
    name, though the help says it names what waits on the owner."""

    def test_the_health_check_names_it_with_what_to_do(self):
        try:
            write_project(self.pace, "old", "Old\nName")
        except (OSError, ValueError):
            self.skipTest("a folder name with a line break cannot be made here")
        held = held_notes(self.pace)
        self.assertEqual(len(held), 1, held)
        self.assertEqual(held[0]["files"], ["1 Projects/Old\\nName"])
        self.assertIn("where a folder's name is not valid text or holds a line break or another control character, rename "
                      "it", held[0]["fix"])
        self.assertIn("a project that could not be read, or whose name is not valid text or holds a line break, and "
                      "everything in it", flat(HELP / "projects.md"))
        self.assertIn("a project that cannot be read, or whose name is not valid text or holds a line break, and "
                      "everything in it", flat(CHANGELOG))


class FullLevelAdviceTests(Case):
    """5 (low): where every number from 01 to 99 was taken, the advice was to put projects together inside a parent
    project, which for projects already made leaves each with a parent its Pace project.md does not name."""

    def test_the_advice_can_be_followed(self):
        for number in range(1, 100):
            (self.pace / "1 Projects" / pr.numbered_name(number, "Taken")).mkdir()
        write_project(self.pace, "zeta", "Zeta")
        held = held_notes(self.pace)
        self.assertEqual(len(held), 1, held)
        self.assertIn("where every number from 01 to 99 is taken, free one by hand, such as by taking the number off a "
                      "folder of the owner's own that is not a project, or leave the folder as it is", held[0]["fix"])
        out, code = self.new("next", "Next")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("Ask the owner which project this one belongs inside, and make it there with --parent", out["message"])
        for text in (flat(HELP / "projects.md"), held[0]["fix"], out["message"]):
            self.assertNotIn("together inside a parent project", text)


class WindowsLimitWordingTests(unittest.TestCase):
    """6 (low): the help and the changelog still said files past 260 characters were named, where the preview names a
    path of 260 characters or more."""

    def test_the_wording_says_reach(self):
        self.assertIn("or reach the 260 characters at which other Office and Windows tools stop", flat(HELP / "projects.md"))
        self.assertIn("or reach Windows' usual 260 characters", flat(CHANGELOG))


if __name__ == "__main__":
    unittest.main()
