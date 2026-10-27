"""The numbered folder names from release 3.11.0: what ships, older records, hints, and updates over old names.

Invented data only: temporary folders and invented local git repositories.
"""

from pathlib import Path
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from contextlib import redirect_stdout

from test_updates import PACE_FOLDER, Repo, owner_view, pu, setUpModule, tearDownModule  # noqa: F401 (module setup)
from test_records import PaceFolder, BUDGET, BUDGET_DIR, DOCS
from test_overview_tool import Folder

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example"
_spec = importlib.util.spec_from_file_location("pace_record_for_names", PACE_FOLDER / "Product/Tools/pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)
_spec = importlib.util.spec_from_file_location("pace_overview_for_names", PACE_FOLDER / "Product/Tools/pace_overview.py")
po = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(po)

NUMBERED = {"Projects": "1 Projects", "Views": "2 Views", "My add-ins": "3 My add-ins"}
OLD = r"(?:Projects|Views|My add-ins)"
# An old folder as the start of a path ("in Projects/", `My add-ins/x`), named alone in backticks, or as "the Views
# folder"; never a numbered name such as 1 Projects/ or the older Pace/Add-ins/My add-ins/.
OLD_PATH = re.compile(rf"(?<![\w/.-])(?<!\d ){OLD}/|`{OLD}`|\b[Tt]he {OLD} folder")
# Lines that name an old folder on purpose: how to rename it, how older records read, and an older add-in place.
ON_PURPOSE = ("3.11.0", "Rename `Projects` to `1 Projects`", "names an old folder", "named as before", "Pace/Add-ins/My add-ins", "such as Projects/")


def shipped_text():
    for top in ("PACE", "example", "docs"):
        for path in sorted((ROOT / top).rglob("*")):
            # Records keep the folder names they were saved with, so the example's are as written.
            if (path.is_file() and path.suffix in (".md", ".py", ".html", ".txt", ".json") and "__pycache__" not in path.parts
                    and "Record" not in path.relative_to(ROOT).parts):
                yield path
    yield ROOT / "README.md"
    yield ROOT / "get-pace.py"


class ShippedNamesTests(unittest.TestCase):
    def test_the_folders_people_open_are_numbered_so_they_sort_first(self):
        for root in (PACE_FOLDER, EXAMPLE):
            with self.subTest(root=root.name):
                folders = sorted((path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")),
                                 key=str.casefold)
                self.assertEqual(folders[:3], ["1 Projects", "2 Views", "3 My add-ins"])
                for old in NUMBERED:
                    self.assertFalse((root / old).exists(), old)
        self.assertEqual(pr.PROJECTS_DIR, "1 Projects")
        self.assertEqual(po.VIEWS_DIR, "2 Views")
        self.assertEqual(pu.OWNER_ADDINS, "3 My add-ins")
        self.assertEqual(pr.RENAMED_FOLDERS, NUMBERED)
        self.assertEqual(pu.RENAMED_FOLDERS, NUMBERED)

    def test_nothing_shipped_names_an_old_folder_except_to_explain_the_rename(self):
        found = [f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}"
                 for path in shipped_text()
                 for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if OLD_PATH.search(line) and not any(reason in line for reason in ON_PURPOSE)]
        self.assertEqual(found, [])

    def test_pace_md_says_which_folders_people_open(self):
        for root in (PACE_FOLDER, EXAMPLE):
            text = (root / "Pace.md").read_text(encoding="utf-8")
            part = text[text.index("## Where things belong"):text.index("## Rounding up")]
            self.assertIn("The numbered folders are the ones people open, so they sort above Pace's other folders.", part)
            order = [part.index(f"- `{name}/`") for name in ("1 Projects", "2 Views", "3 My add-ins", "Record", "Repos", "Product")]
            self.assertEqual(order, sorted(order))

    def test_updates_help_gives_the_rename_steps(self):
        text = (PACE_FOLDER / "Product/Help/updates.md").read_text(encoding="utf-8")
        section = text[text.index("## Folder names from 3.11.0"):text.index("## Pace.md")]
        for phrase in ("Rename `Projects` to `1 Projects`, `Views` to `2 Views` and `My add-ins` to `3 My add-ins`",
                       "An update never moves your folders", "both `prepare` and the install stop before changing anything",
                       "move what is in the old folder into it", "An updater from before 3.11.0 does not know",
                       "the record tool still finds in the numbered folders"):
            self.assertIn(phrase, section)


class OlderFolderTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-names-")
        self.pace = Path(self._temp.name) / "PACE"
        self.pace.mkdir()

    def tearDown(self):
        self._temp.cleanup()

    def test_a_path_an_older_record_wrote_finds_its_file_in_the_numbered_folder(self):
        file = self.pace / "1 Projects/Kowhai Books/Documents/Board pack.txt"
        file.parent.mkdir(parents=True)
        file.write_text("Invented.", encoding="utf-8")
        self.assertEqual(pr.recorded_path(self.pace, "Projects/Kowhai Books/Documents/Board pack.txt"), file.resolve())
        self.assertEqual(pr.confirmation_file(self.pace, "Projects/Kowhai Books/Documents/Board pack.txt"), file.resolve())
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/Kowhai Books/Documents/Board pack.txt"), file.resolve())
        # A folder still under its old name is used as it is.
        old = self.pace / "Views/2026-10-01-open-work.md"
        old.parent.mkdir()
        old.write_text("Invented.", encoding="utf-8")
        self.assertEqual(pr.recorded_path(self.pace, "Views/2026-10-01-open-work.md"), old.resolve())

    def test_a_folder_with_the_old_names_is_told_how_to_rename_them(self):
        (self.pace / "Projects").mkdir()
        (self.pace / "Views").mkdir()
        (self.pace / "Record").mkdir()
        _, issues, _ = pr.scan_projects(self.pace)
        self.assertEqual(len(issues), 1)
        self.assertIn("1 Projects/ was not found", issues[0]["message"])
        self.assertIn("rename Projects/ to 1 Projects/; rename Views/ to 2 Views/.", issues[0]["message"])
        (self.pace / "1 Projects").mkdir()
        self.assertEqual(pr.old_folder_names(self.pace), " This Pace folder still has folders named as before release 3.11.0: "
                                                         "rename Views/ to 2 Views/. Updates help, under Folder names from "
                                                         "3.11.0, gives the steps.")

    def test_both_names_or_a_file_in_the_way_get_their_own_steps(self):
        # The review found a folder with both names, or a file with the new name, was not mentioned at all.
        for name in ("Projects", "1 Projects", "Views", "2 Views", "My add-ins", "Record"):
            (self.pace / name).mkdir()
        (self.pace / "Views/2026-10-01-open-work.html").write_text("Invented.", encoding="utf-8")
        (self.pace / "My add-ins/.gitkeep").write_text("", encoding="utf-8")
        (self.pace / "3 My add-ins").write_text("Invented file in the way.", encoding="utf-8")
        self.assertEqual(pr.old_folder_steps(self.pace), [
            "move what is in Views/ into 2 Views/, then remove the empty Views/",
            "3 My add-ins is a file, not a folder: move it aside, then rename My add-ins/ to 3 My add-ins/"])
        # An empty Projects/ beside 1 Projects/ is harmless and not mentioned.
        self.assertNotIn("Projects/ into", pr.old_folder_names(self.pace))


class UpdateOverOldNamesTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-names-update-")
        self.base = Path(self._temp.name)
        self.repo = Repo(self.base / "upstream")
        shutil.copytree(PACE_FOLDER, self.repo.path / "PACE", ignore=shutil.ignore_patterns("__pycache__"))
        self.commit = self.repo.commit("Invented release with the numbered folders")
        self.repo.tag("v3.11.0")
        # The owner's folder as release 3.10.0 left it: the same layout under the old names.
        self.folder = self.base / "Owner Pace"
        shutil.copytree(PACE_FOLDER, self.folder, ignore=shutil.ignore_patterns("__pycache__"))
        for old, new in NUMBERED.items():
            (self.folder / new).rename(self.folder / old)
        (self.folder / "Projects/Kowhai Books").mkdir()
        self.words = f"Install Pace v3.11.0 at commit {self.commit}, please."

    def tearDown(self):
        self._temp.cleanup()

    def test_the_preview_lists_the_folders_to_rename(self):
        result = pu.preview(self.folder, str(self.repo.path), "v3.11.0", self.commit)
        self.assertEqual(result["folders_to_rename"], [{"from": old, "to": new, "do": f"rename {old}/ to {new}/"}
                                                       for old, new in NUMBERED.items()])
        # The steps are in the message itself, since the installed help can be older than the release.
        self.assertIn("then in the Pace folder: rename Projects/ to 1 Projects/; rename Views/ to 2 Views/; "
                      "rename My add-ins/ to 3 My add-ins/. Then preview again.", result["message"])
        self.assertIn("close any file open from them", result["message"])
        self.assertIn("Paths inside the renamed folders get 2 characters longer.", result["message"])

    def test_prepare_saves_no_proposal_until_they_are_renamed(self):
        # The review found prepare saved a proposal the install would then refuse.
        with self.assertRaises(pu.Stop) as stopped:
            pu.prepare(self.folder, str(self.repo.path), "v3.11.0", self.commit)
        self.assertIn("No proposal was saved.", str(stopped.exception))
        self.assertFalse((self.folder / "Release record/Proposals").exists()
                         and any((self.folder / "Release record/Proposals").iterdir()))

    def test_a_folder_with_both_names_stops_the_install_too(self):
        (self.folder / "1 Projects").mkdir()
        result = pu.preview(self.folder, str(self.repo.path), "v3.11.0", self.commit)
        self.assertEqual(result["folders_to_rename"][0]["do"],
                         "move what is in Projects/ into 1 Projects/, then remove the empty Projects/")
        with self.assertRaises(pu.Stop):
            pu.apply(self.folder, str(self.repo.path), "v3.11.0", self.commit, go_ahead=self.words)
        (self.folder / "1 Projects").rmdir()
        (self.folder / "2 Views").write_text("Invented file in the way.", encoding="utf-8")
        result = pu.preview(self.folder, str(self.repo.path), "v3.11.0", self.commit)
        self.assertIn("2 Views is a file, not a folder: move it aside, then rename Views/ to 2 Views/",
                      [step["do"] for step in result["folders_to_rename"]])

    def test_lines_of_the_owners_that_name_an_old_folder_are_listed(self):
        pace_md = self.folder / "Pace.md"
        line = "- **My voice** - Draft in the owner's voice. `My add-ins/My voice/ADD-IN.md`"
        pace_md.write_text(pace_md.read_text(encoding="utf-8").replace(
            "None switched on yet.", line), encoding="utf-8")
        result = pu.preview(self.folder, str(self.repo.path), "v3.11.0", self.commit)
        self.assertIn(f'Then: Pace.md still names folders as they were named before 3.11.0 in these lines, so change each '
                      f'to the numbered name, such as 3 My add-ins/ for My add-ins/: "{line}".', result["message"])
        for old, new in NUMBERED.items():
            (self.folder / old).rename(self.folder / new)
        result = pu.preview(self.folder, str(self.repo.path), "v3.11.0", self.commit)
        self.assertNotIn("folders_to_rename", result)
        self.assertEqual(result["pace_md_old_folder_lines"], [line])
        result = pu.apply(self.folder, str(self.repo.path), "v3.11.0", self.commit, go_ahead=self.words)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertEqual(result["pace_md_old_folder_lines"], [line])
        self.assertIn(line, result["warning"])
        self.assertIn(line, pace_md.read_text(encoding="utf-8"))  # the owner's line is theirs to change

    def test_going_back_to_an_earlier_release_asks_for_the_old_names_back(self):
        # The review found an earlier release went in over the numbered folders, and its tools then found no projects.
        for old, new in NUMBERED.items():
            (self.folder / old).rename(self.folder / new)
            (self.repo.path / "PACE" / new).rename(self.repo.path / "PACE" / old)
        commit = self.repo.commit("An invented release from before the numbered names")
        self.repo.tag("v3.10.9")
        words = f"Install Pace v3.10.9 at commit {commit}, please."
        result = pu.preview(self.folder, str(self.repo.path), "v3.10.9", commit)
        self.assertEqual([step["do"] for step in result["folders_to_rename"]],
                         [f"rename {new}/ to {old}/" for old, new in NUMBERED.items()])
        self.assertIn("This release is from before 3.11.0, and its tools look for the folder names from then.",
                      result["message"])
        before = owner_view(self.folder)
        with self.assertRaises(pu.Stop):
            pu.apply(self.folder, str(self.repo.path), "v3.10.9", commit, go_ahead=words)
        self.assertEqual(owner_view(self.folder), before)

    def test_the_install_stops_until_they_are_renamed_and_then_goes_ahead(self):
        before = owner_view(self.folder)
        product = sorted(p.relative_to(self.folder).as_posix() for p in (self.folder / "Product").rglob("*"))
        with self.assertRaises(pu.Stop) as stopped:
            pu.apply(self.folder, str(self.repo.path), "v3.11.0", self.commit, go_ahead=self.words)
        self.assertIn("Nothing was installed.", str(stopped.exception))
        self.assertEqual(owner_view(self.folder), before)
        self.assertEqual(sorted(p.relative_to(self.folder).as_posix() for p in (self.folder / "Product").rglob("*")), product)
        for old, new in NUMBERED.items():
            (self.folder / old).rename(self.folder / new)
        result = pu.apply(self.folder, str(self.repo.path), "v3.11.0", self.commit, go_ahead=self.words)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertTrue((self.folder / "1 Projects/Kowhai Books").is_dir())  # the owner's work is where they put it

    def test_a_release_without_the_numbered_names_needs_no_rename(self):
        for new in NUMBERED.values():
            shutil.rmtree(self.repo.path / "PACE" / new)
        commit = self.repo.commit("An invented older-style release")
        self.repo.tag("v3.10.9")
        result = pu.preview(self.folder, str(self.repo.path), "v3.10.9", commit)
        self.assertNotIn("folders_to_rename", result)


class RecordToolHintTests(PaceFolder):
    """While a folder still has an old name, the record tool says so wherever a project could seem to be missing."""

    def old_projects(self):
        old = self.pace / "Projects/Harakeke Trust"
        (old / "Documents").mkdir(parents=True)
        (old / "Pace project.md").write_text("---\nformat: project-1\nid: harakeke-trust\nparent: none\n"
                                             "created: 2026-10-20T09:00:00+13:00\nby: Test\n---\n\nInvented.\n",
                                             encoding="utf-8")

    def test_listing_projects_names_a_projects_folder_kept_under_its_old_name(self):
        # The review found such a project was silently left out, so its id could be taken by a new one.
        self.old_projects()
        out, _ = self.run_tool("projects")
        messages = [issue["message"] for issue in out["issues"]]
        self.assertIn("Not every folder was read. This Pace folder still has folders named as before release 3.11.0: "
                      "move what is in Projects/ into 1 Projects/, then remove the empty Projects/. Updates help, under "
                      "Folder names from 3.11.0, gives the steps.", messages)

    def test_no_project_is_made_while_old_projects_hold_anything(self):
        self.old_projects()
        out, code = self.run_tool("project-new", "--id", "harakeke-trust", "--name", "Harakeke Trust", "--by", "Test agent")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("move what is in Projects/ into 1 Projects/", out["message"])
        self.assertFalse((self.pace / "1 Projects/Harakeke Trust").exists())

    def test_saving_for_a_project_that_is_not_found_names_the_old_folder(self):
        self.old_projects()
        request = self.new_request(project="none")
        request = request.replace("--none--", "--harakeke-trust--")
        out, code = self.run_tool("create", "--request", request, "--project", "harakeke-trust", "--kind", "note",
                                  "--subject", "Invented", "--from", "agent", "--by", "Test agent", "--body", "Invented.")
        self.assertEqual(out["status"], "not-saved", out)
        self.assertIn("move what is in Projects/ into 1 Projects/", out["message"])

    def test_an_exact_act_named_by_its_older_path_is_still_the_same_file(self):
        # The review found the record tool mapped a recorded old path but not one given on the command line.
        act = self.pace / BUDGET_DIR / DOCS / "close.txt"
        act.write_bytes(b"Invented October close.\n")
        relative = f"{BUDGET_DIR}/{DOCS}/close.txt"
        shown = self.run_tool("propose", "--act", "Accept October close", "--act-file", relative)[0]["act_sha256"]
        request = self.new_request()
        out, _ = self.run_tool("confirm", "--request", request, "--project", BUDGET, "--subject", "October close",
                               "--act", "Accept October close", "--act-file", relative, "--shown-sha256", shown,
                               "--source", "Invented close statement", "--owner-words", "Yes, accept it.",
                               "--owner-current", "--by", "Test agent")
        self.assertEqual(out["status"], "confirmed", out)
        # As a record saved before 3.11.0 would have it, before its folders were numbered too.
        saved = self.pace / "Record" / f"{request}.md"
        saved.write_text(saved.read_text(encoding="utf-8").replace(f"act-file: {relative}",
                                                                   "act-file: Projects/Kowhai Books/Budget 2027/Documents/close.txt"),
                         encoding="utf-8")
        self.assertIn("act-file: Projects/Kowhai Books/Budget 2027/Documents/close.txt", saved.read_text(encoding="utf-8"))
        for given in ("Projects/Kowhai Books/Budget 2027/Documents/close.txt",
                      "1 Projects/Kowhai Books/Budget 2027/Documents/close.txt", relative, str(act)):
            with self.subTest(given=given):
                out, code = self.run_tool("confirmation-status", "--request", request, "--act-file", given)
                self.assertEqual((out["status"], code), ("confirmed", 0), out)


class OverviewHintTests(unittest.TestCase):
    def test_an_unknown_project_names_the_folders_still_under_old_names(self):
        with tempfile.TemporaryDirectory(prefix="pace-names-overview-") as base:
            folder = Folder(Path(base))
            folder.project("kowhai-books", "Kowhai Books")
            (folder.root / "1 Projects").rename(folder.root / "Projects")
            (folder.root / "1 Projects").mkdir()
            out, code = folder.run("--project", "kowhai-books")
            self.assertEqual((out["status"], code), ("not-made", 1), out)
            self.assertIn("move what is in Projects/ into 1 Projects/", out["message"])


if __name__ == "__main__":
    unittest.main()
