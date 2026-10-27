"""Release 3.13.0: the OneDrive connection route, the Getting started add-in, and the health check's new findings.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_addins import PACE_FOLDER, SHIPPED, section
from test_health_check import CheckCase, STATE, pc, pr, setUpModule, tearDownModule  # noqa: F401 (module setup)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example"
HOSTS = PACE_FOLDER / "Product/Help/hosts-and-views.md"
ADD_IN = PACE_FOLDER / SHIPPED / "Getting started/ADD-IN.md"


def hosts_section(heading: str) -> str:
    text = HOSTS.read_text(encoding="utf-8")
    return text[text.index(f"## {heading}\n"):].split("\n## ", 1)[0]


class OneDriveRouteTests(unittest.TestCase):
    def test_the_steps_stand_in_for_the_checks_the_tools_make(self):
        steps = hosts_section("Through a OneDrive connection")
        for phrase in ("**Open `Pace.md` by its place**", "not by searching for it: a search can find an older copy",
                       "**List `Record/` by reading the folder itself**, every page of it",
                       "a list made from search results is partial and is called so",
                       "Choose the request id first", "the setting that refuses a name already in use",
                       "Never let it replace the file or give it another name", "open the file that is there and compare",
                       "**Read the record back**", "Only then call it saved", "placed but not confirmed",
                       "**Never replace, rename, move or delete what Pace keeps as it is:**", "a fix is a new record that corrects the earlier one",
                       "**Change `Pace.md` only on the owner's yes**", "Read it fresh", "the one change shown to the owner",
                       "shows the owner the exact line to paste instead", "**Do by hand what the tools would do, where the help gives a way.**",
                       "**Name the host in `by`**"):
            self.assertIn(phrase, steps)
        numbers = re.findall(r"(?m)^(\d+)\. ", steps)
        self.assertEqual(numbers, [str(n) for n in range(1, len(numbers) + 1)])
        self.assertIn("(record-format.md)", steps)

    def test_each_connected_host_points_to_the_steps(self):
        hosts = hosts_section("What assistants can do")
        claude = next(line for line in hosts.splitlines() if line.startswith("- **Claude on the web or phone"))
        self.assertIn("can list folders, read files, create new files, and replace, rename, move or delete existing ones",
                      claude)
        self.assertIn("cannot run Pace's tools on the folder", claude)
        self.assertIn("(#through-a-onedrive-connection)", claude)
        copilot = next(line for line in hosts.splitlines() if line.startswith("- **Copilot through its OneDrive connection"))
        self.assertIn("cannot replace existing files there", copilot)
        self.assertIn("follows the same steps below", copilot)

    def test_the_record_format_still_gives_the_by_hand_steps_the_route_relies_on(self):
        text = (PACE_FOLDER / "Product/Help/record-format.md").read_text(encoding="utf-8")
        for phrase in ("## Making a record by hand", "If a file with that name is already there, do not overwrite it and do "
                       "not rename yours", "**placed but not confirmed**", "## Reading records by hand"):
            self.assertIn(phrase, text)


class GettingStartedTests(unittest.TestCase):
    def test_the_add_in_sets_up_only_what_the_owner_agrees(self):
        text = ADD_IN.read_text(encoding="utf-8")
        steps, limits = section(text, "Steps"), section(text, "Limits")
        for phrase in ("run the health check", "Skip any step below that is already done", "**The owner's name.**",
                       "below the mark in the part The owner's name", "**Time zone.**", "**Projects.**",
                       "Make only the ones the owner agrees", "**Add-ins.**", "Switch on only the ones the owner picks",
                       "**Assistants.**", "`3 My add-ins/Assistant setup.md`", "**A regular review.**",
                       "call it set only once the host confirms it", "**Backups.**", "nothing is set up unless they ask",
                       "Check again"):
            self.assertIn(phrase, steps)
        for phrase in ("needs the owner's yes in their own words", "sets up no account, connection, password or payment",
                       "never asks for a password or key", "It sends nothing to anyone."):
            self.assertIn(phrase, limits)
        # Each step names the help it follows, so the add-in itself stays in plain words.
        for page in ("health-check.md", "projects.md", "add-ins.md", "hosts-and-views.md", "records.md"):
            self.assertIn(f"../../Help/{page})", text)

    def test_a_new_owner_is_pointed_to_it(self):
        for root in (PACE_FOLDER, EXAMPLE):
            text = (root / "Pace.md").read_text(encoding="utf-8")
            index = text[text.index("## Add-in index"):text.index("## The owner's name")]
            self.assertIn("When the owner asks to set up Pace, offer Getting started.", index)
        self.assertIn("the Getting started add-in takes you through your name, time zone, first projects, add-ins and "
                      "assistants", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("ask your assistant to set up Pace with the Getting started", (ROOT / "get-pace.py").read_text(encoding="utf-8"))
        # It ships off, like every add-in: the shipped index still has none switched on.
        index = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8").split("## Add-in index")[1].split("## The owner's name")[0]
        self.assertIn("None switched on yet.", index)


class HealthCheckTests(CheckCase):
    def test_a_new_folder_is_pointed_to_getting_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "PACE"
            shutil.copytree(PACE_FOLDER, fresh, ignore=shutil.ignore_patterns("__pycache__"))
            out, _ = pc.run(pc.build_parser().parse_args(["--pace", str(fresh)]))
        [item] = [found for found in out["findings"] if found["check"] == "new-folder"]
        self.assertEqual(item["level"], "note")
        self.assertIn("Switch on Getting started", item["fix"])
        # A folder in use is not called new.
        self.assertEqual(self.found(self.check(), "new-folder"), [])

    def test_record_folder_size_is_noted_as_it_nears_five_thousand(self):
        items = len(os.listdir(self.pace / "Record"))
        with mock.patch.object(pc, "RECORD_FOLDER_NOTE", items):
            [item] = [found for found in self.found(self.check(), "record-files") if " holds " in found["message"]]
        self.assertEqual(item["level"], "note")
        self.assertEqual(item["message"], f"Record/ holds {items} items. Past 5,000 items in one folder, OneDrive's web "
                         "pages show it slowly or with errors, and a OneDrive connection lists it more slowly.")
        self.assertEqual([found for found in self.found(self.check(), "record-files") if " holds " in found["message"]], [])
        self.assertEqual((pc.RECORD_FOLDER_NOTE, pc.RECORD_FOLDER_LIMIT), (4000, 5000))

    def test_the_help_page_names_both(self):
        text = (PACE_FOLDER / "Product/Help/health-check.md").read_text(encoding="utf-8")
        self.assertIn("From 4,000 items it notes how close `Record/`, or one of its month folders, is to 5,000", text)
        self.assertIn("- **A new folder:** one whose `Record/` and `1 Projects/` are both empty is pointed to the Getting "
                      "started add-in.", text)


class GetPaceTests(unittest.TestCase):
    def test_get_pace_says_to_start_with_getting_started(self):
        sys.path.insert(0, str(ROOT))
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("get_pace_for_start", ROOT / "get-pace.py")
            get = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(get)
        finally:
            sys.path.remove(str(ROOT))
        output = io.StringIO()
        with mock.patch.object(get, "get_pace", return_value=("v3.13.0", "a" * 40)), contextlib.redirect_stdout(output):
            code = get.main(["--to", str(ROOT)])
        self.assertEqual(code, 0)
        self.assertIn("in your first chat ask your assistant to set up Pace with the Getting started add-in", output.getvalue())


if __name__ == "__main__":
    unittest.main()
