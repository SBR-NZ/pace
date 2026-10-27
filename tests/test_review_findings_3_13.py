"""Release 3.13.0's independent review: each finding has a test here that fails on the reviewed commit (a1cfe82).

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_addins import PACE_FOLDER, SHIPPED, catalogue_lines, section
from test_health_check import CheckCase, STATE, pc, pr, setUpModule, tearDownModule  # noqa: F401 (module setup)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example"
HELP = PACE_FOLDER / "Product/Help"
HOSTS = HELP / "hosts-and-views.md"
GETTING_STARTED = PACE_FOLDER / SHIPPED / "Getting started"
PROJECT = ("---\nformat: project-1\nid: {pid}\nparent: none\ncreated: 2026-10-23T11:00:00+13:00\nby: Test\n---\n\n"
           "Invented work.\n")
# These pages link only to whole pages, so the steps are named after the link.
POINTER = "[Assistants and dated views](hosts-and-views.md), under Through a OneDrive connection"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def hosts_section(heading: str) -> str:
    text = read(HOSTS)
    return text[text.index(f"## {heading}\n"):].split("\n## ", 1)[0]


def host_line(start: str) -> str:
    return next(line for line in hosts_section("What assistants can do").splitlines() if line.startswith(start))


def step(text: str, number: int) -> str:
    return re.search(rf"(?m)^{number}\. (.*)$", text).group(1)


CONNECTION_STEPS = "Through a OneDrive connection"


class NewFolderTests(unittest.TestCase):
    """Finding 1: a folder is called new only when Record/ and 1 Projects/ were both read in full and hold nothing,
    since Getting started makes projects and a project made again beside one that was not read is a problem."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-new-folder-")
        self.pace = Path(self._temp.name) / "PACE"
        shutil.copytree(PACE_FOLDER, self.pace, ignore=shutil.ignore_patterns("__pycache__"))

    def tearDown(self):
        self._temp.cleanup()

    def new_folder(self) -> list:
        out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace)]))
        return [item for item in out["findings"] if item["check"] == "new-folder"]

    def project(self, place: str, pid: str) -> Path:
        folder = self.pace / place
        (folder / "Documents").mkdir(parents=True)
        (folder / "Pace project.md").write_text(PROJECT.format(pid=pid), encoding="utf-8")
        return folder

    def test_a_shipped_folder_is_new_even_with_files_the_system_leaves(self):
        (self.pace / "Record/desktop.ini").write_text("[.ShellClassInfo]\n", encoding="utf-8")
        (self.pace / "1 Projects/.DS_Store").write_bytes(b"\0\0\0\1Bud1")
        [item] = self.new_folder()
        self.assertEqual(item["level"], "note")

    def test_a_project_whose_file_cannot_be_read_is_not_a_new_folder(self):
        folder = self.project("1 Projects/Kowhai Books", "kowhai-books")
        (folder / "Pace project.md").write_text("<html>OneDrive placeholder</html>\n", encoding="utf-8")
        self.assertEqual(self.new_folder(), [])

    def test_projects_that_cannot_be_listed_are_not_a_new_folder(self):
        self.project("1 Projects/Kowhai Books", "kowhai-books")
        real, target = os.scandir, str(self.pace / "1 Projects")

        def scandir(path="."):
            if str(path) == target:
                raise PermissionError(13, "Permission denied", target)
            return real(path)

        with mock.patch.object(os, "scandir", scandir):
            self.assertEqual(self.new_folder(), [])

    def test_a_project_deeper_than_the_tools_read_is_not_a_new_folder(self):
        place = "1 Projects/" + "/".join(f"L{level}" for level in range(pr.MAX_PROJECT_DEPTH + 2))
        self.project(place, "deep-one")
        self.assertEqual(self.new_folder(), [])

    def test_projects_under_the_old_folder_name_are_not_a_new_folder(self):
        self.project("Projects/Kowhai Books", "kowhai-books")
        self.assertEqual(self.new_folder(), [])

    def test_a_record_kept_only_as_a_second_copy_is_not_a_new_folder(self):
        (self.pace / "Record/20261022T221500Z--none--k3f9q2 (1).md").write_text(
            "---\nformat: record-1\n---\n\nInvented.\n", encoding="utf-8")
        self.assertEqual(self.new_folder(), [])

    def test_with_getting_started_on_the_fix_does_not_say_to_switch_it_on(self):
        """Finding 8, last part."""
        [line] = [line for line in catalogue_lines() if line.startswith("- **Getting started** - ")]
        path = self.pace / "Pace.md"
        text = read(path)
        self.assertEqual(text.count("None switched on yet."), 1)
        path.write_text(text.replace("None switched on yet.", line), encoding="utf-8")
        [item] = self.new_folder()
        self.assertNotIn("Switch on", item["fix"])
        self.assertIn("Ask the assistant to set up Pace with Getting started.", item["fix"])


class RecordCountTests(CheckCase):
    """Finding 2: the size of Record/ is a note with nothing to do, so a large folder can still be healthy; it counts
    every item OneDrive counts, and says "more than" only past the limit."""

    def items(self) -> int:
        return len(os.listdir(self.pace / "Record"))

    def said(self, out) -> list:
        return [item for item in self.found(out, "record-files") if " holds " in item["message"]]

    def test_at_and_past_the_limit_it_is_a_note_and_the_folder_stays_healthy(self):
        items = self.items()
        for limit, past in ((items, False), (items - 1, True)):
            with self.subTest(limit=limit), mock.patch.object(pc, "RECORD_FOLDER_NOTE", 1), \
                    mock.patch.object(pc, "RECORD_FOLDER_LIMIT", limit):
                out = self.check()
                [item] = self.said(out)
                self.assertEqual((item["level"], out["status"]), ("note", "healthy"), out["findings"])
                self.assertTrue(item["message"].startswith(f"Record/ holds {items:,} items"), item["message"])
                self.assertEqual("more than" in item["message"], past, item["message"])
                self.assertIn(f"{limit:,}", item["message"])

    def test_every_item_in_the_folder_counts(self):
        (self.pace / "Record/notes.txt").write_text("Invented.\n", encoding="utf-8")
        items = self.items()
        with mock.patch.object(pc, "RECORD_FOLDER_NOTE", items), mock.patch.object(pc, "RECORD_FOLDER_LIMIT", items + 10):
            [item] = self.said(self.check())
        self.assertIn(f"Record/ holds {items:,} items.", item["message"])

    def test_the_fix_gives_no_route_pace_does_not_have(self):
        with mock.patch.object(pc, "RECORD_FOLDER_NOTE", 1):
            [item] = self.said(self.check())
        for gone in ("keep earlier years' records apart", "whoever supports"):
            self.assertNotIn(gone, item["fix"])
        # From 3.14.0 archiving is the one route, and only for finished work; with none to archive, nothing needs doing.
        for phrase in ("Nothing needs doing: syncing and Pace's tools work the same at any size.",
                       "Never move or rename a record by hand: only archiving moves records, and only finished work "
                       "more than 3 months old."):
            self.assertIn(phrase, item["fix"])
        text = read(HELP / "health-check.md")
        self.assertIn("From 4,000 items it notes how close `Record/`, or one of its month folders, is to 5,000", text)
        self.assertIn("Otherwise it is only a note: syncing and Pace's tools work the same at any size.", text)
        self.assertIn("A folder that could not be read in full is never called new.", text)


class ConnectionStepTests(unittest.TestCase):
    def test_nothing_pace_keeps_is_replaced_renamed_moved_or_deleted(self):
        """Finding 3: the connection can also rename, move and delete, and records are not the only files kept."""
        steps = hosts_section(CONNECTION_STEPS)
        rule = step(steps, 5)
        self.assertTrue(rule.startswith("**Never replace, rename, move or delete what Pace keeps as it is:**"), rule)
        for kept in ("a record", "a project's `Pace project.md`", "a file in `Sources/` or `Archive/`",
                     "a saved page in `2 Views/`", "anything in `Product/` or `Release record/`",
                     "Anything else is moved, renamed or deleted only on the owner's yes."):
            self.assertIn(kept, rule)
        self.assertIn("Make every other new file, such as a page in `2 Views/` or a copy in `Archive/`, the same way.",
                      step(steps, 3))
        self.assertNotIn("as reliable as on a computer", steps)
        self.assertIn("through a connection nothing refuses for the assistant, so it follows these steps", steps)
        claude = host_line("- **Claude on the web or phone")
        self.assertIn("can list folders, read files, create new files, and replace, rename, move or delete existing ones",
                      claude)

    def test_pace_md_is_read_fresh_before_each_change_and_checked_after(self):
        """Finding 4."""
        rule = step(hosts_section(CONNECTION_STEPS), 6)
        for phrase in ("Read it fresh straight before each change, never from earlier in the chat",
                       "check that it is that text with that one change and nothing else",
                       "The connection cannot tell whether `Pace.md` changed between the read and the replacement",
                       "OneDrive's version history keeps the version replaced",
                       "the change counts only once `Pace.md` shows it"):
            self.assertIn(phrase, rule)
        text = read(GETTING_STARTED / "ADD-IN.md")
        self.assertIn("Read `Pace.md` fresh before each change to it, never from earlier in the chat, make only the change "
                      "the owner agreed, and read it back", section(text, "What it needs"))
        add_ins = step(section(text, "Steps"), 5)
        self.assertIn("read `Pace.md` back: an add-in is on only once `Pace.md` shows its line", add_ins)

    def test_the_claude_line_and_updates_help_agree(self):
        """Finding 5."""
        self.assertIn("It cannot install Product updates.", host_line("- **Claude on the web or phone"))
        updates = read(HELP / "updates.md")
        self.assertNotIn("or to replace files in the cloud directly, is not promised", updates)
        self.assertIn("Claude on the web or phone can replace files through its Microsoft 365 connection but cannot run "
                      "the updater, so it cannot install one either.", updates)
        rule = step(hosts_section(CONNECTION_STEPS), 7)
        self.assertNotIn("give a route for each", rule)
        for phrase in ("**Do by hand what the tools would do, where the help gives a way.**",
                       "Installing an update needs a computer that can run the updater",
                       "a fingerprint is given only when the host can work out the SHA-256 of the file's exact bytes"):
            self.assertIn(phrase, rule)

    def test_the_steps_are_found_from_where_records_are_saved_and_add_ins_switched_on(self):
        """Finding 6."""
        for page in ("records.md", "record-format.md"):
            self.assertIn(f"only through a OneDrive connection also follows {POINTER}", read(HELP / page))
        self.assertIn(POINTER, section(read(HELP / "add-ins.md"), "Switching one on or off"))
        self.assertIn("[Assistants and dated views](../../Help/hosts-and-views.md), under Through a OneDrive connection",
                      section(read(GETTING_STARTED / "ADD-IN.md"), "What it needs"))
        for root in (PACE_FOLDER, EXAMPLE):
            part = read(root / "Pace.md").split("## Help, when relevant")[1]
            self.assertIn("the steps for an assistant that reaches this folder only through a OneDrive connection", part)

    def test_a_host_without_a_feature_the_steps_use_says_so_and_stays_safe(self):
        """Not verified for Copilot: listing every page, and refusing a name already in use."""
        steps = hosts_section(CONNECTION_STEPS)
        self.assertIn("as is one from a host that cannot list every page", step(steps, 2))
        self.assertIn("If the host has no such setting, first open that name in `Record/`, and create the file only when "
                      "nothing is there.", step(steps, 3))
        self.assertIn("A host that cannot do a step says which, and what that leaves undone.", steps)
        self.assertIn("It follows the same steps below as far as it can, says which steps it cannot do",
                      host_line("- **Copilot through its OneDrive connection"))


class GettingStartedTests(unittest.TestCase):
    def test_it_is_offered_and_never_started_unasked(self):
        """Finding 7."""
        for root in (PACE_FOLDER, EXAMPLE):
            index = read(root / "Pace.md").split("## Add-in index")[1].split("## The owner's name")[0]
            self.assertNotIn("start with Getting started", index)
            self.assertIn("When the owner asks to set up Pace, offer Getting started.", index)
        launcher = read(GETTING_STARTED / "Launchers/Claude/pace-getting-started/SKILL.md")
        self.assertIn("\ndescription: Launcher for the Getting started add-in in Pace by SBR. Use when the owner asks to set "
                      "up Pace or to go through the set-up again.\n", launcher)
        when = section(read(GETTING_STARTED / "ADD-IN.md"), "When to use it")
        self.assertNotIn("When the owner asks to set up Pace, in a new Pace folder", when)
        self.assertIn("When the owner asks to set up Pace, or to go through the set-up again", when)
        self.assertIn("offer it, and start only on the owner's yes", when)

    def test_its_steps_agree_with_the_rest_of_pace(self):
        """Finding 8."""
        steps = section(read(GETTING_STARTED / "ADD-IN.md"), "Steps")
        zone = step(steps, 3)
        self.assertNotIn("or take it from the host's clock and check it with them", zone)
        self.assertIn("Do not take it from the host's clock alone, which for a cloud assistant is usually UTC.", zone)
        assistants = step(steps, 6)
        self.assertNotIn("adds its own part when the owner next uses it", assistants)
        self.assertIn("the owner can ask it to add its own part, which it writes only on their yes", assistants)
        review = step(steps, 7)
        for phrase in ("Only if Weekly review is switched on", "can open this Pace folder when it goes off",
                       "copies no names, figures or other private details"):
            self.assertIn(phrase, review)


if __name__ == "__main__":
    unittest.main()
