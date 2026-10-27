"""Folders inside a project's Documents/: the help's rules, the record tool's --folder option, and new folders raised.

Invented data only, in temporary Pace folders.
"""

from pathlib import Path
import re
import shlex
import sys
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_records import CLIENT, CLIENT_DIR, DOCS, HELP, PACE_FOLDER, PaceFolder, pr

PLANS_DIR = f"{CLIENT_DIR}/03. Plans"  # after 02. Budget 2027

PROJECTS_HELP = HELP / "projects.md"
NEW = ["project-new", "--id", "kowhai-plans", "--name", "Plans", "--parent", CLIENT, "--by", "Test agent"]


def section(heading: str) -> str:
    text = PROJECTS_HELP.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(heading)}\n.*?(?=^## |^### |\Z)", text, re.S | re.M)
    return match.group(0) if match else ""


class FolderOptionTests(PaceFolder):
    def test_folders_are_made_inside_documents_and_listed(self):
        out, code = self.run_tool(*NEW, "--folder", "Deliverables", "--folder", "Meetings")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertEqual(out["folders"], ["Deliverables", "Meetings"])
        self.assertEqual(out["folder"], PLANS_DIR)
        documents = self.pace / PLANS_DIR / DOCS
        self.assertEqual(sorted(p.name for p in documents.iterdir()), ["Deliverables", "Meetings"])
        self.assertIn("Deliverables/, Meetings/", out["message"])

    def test_without_folders_the_result_is_as_before(self):
        out, code = self.run_tool(*NEW)
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertNotIn("folders", out)
        self.assertEqual(list((self.pace / PLANS_DIR / DOCS).iterdir()), [])
        self.assertRegex(out["message"], r"^Saved and read back: project kowhai-plans in 1 Projects/01\. Kowhai Books/03\. Plans \(with 01\. Documents/\)\. ")

    def test_bad_names_archive_and_repeats_are_refused_before_anything_is_made(self):
        cases = ((["Deliverables", "a/b"], "cannot be used"), (["archive"], "Archive/ is not made"),
                 (["Meetings", "meetings"], "named twice"), (["Notes."], "cannot be used"), ([" "], "cannot be used"))
        for folders, why in cases:
            with self.subTest(folders=folders):
                args = list(NEW)
                for name in folders:
                    args += ["--folder", name]
                out, code = self.run_tool(*args)
                self.assertEqual(out["status"], "not-saved", out)
                self.assertNotEqual(code, 0)
                self.assertIn(why, out["message"])
                self.assertIn("Nothing was created", out["message"])
                self.assertFalse(list((self.pace / CLIENT_DIR).glob("*Plans")))

    def test_a_retry_makes_any_folder_still_missing(self):
        self.assertEqual(self.run_tool(*NEW, "--folder", "Deliverables")[0]["status"], "saved")
        out, code = self.run_tool(*NEW, "--folder", "Deliverables", "--folder", "Sources")
        self.assertEqual((out["status"], code), ("already-saved", 0), out)
        self.assertEqual(out["folders"], ["Deliverables", "Sources"])
        self.assertTrue((self.pace / PLANS_DIR / DOCS / "Sources").is_dir())

    def test_the_help_command_makes_what_it_says(self):
        line = re.search(r"`(python3 Product/Tools/pace_record\.py project-new [^`]*--folder[^`]*)`",
                         section("### Folders inside Documents/")).group(1)
        args = shlex.split(line)[2:]
        named = [args[index + 1] for index, arg in enumerate(args) if arg == "--folder"]
        self.assertTrue(2 <= len(named) <= 4, named)  # the help's own example keeps the set small
        self.assertNotIn("Archive", named)
        out, code = self.run_tool(*args)
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertEqual(out["folders"], named)
        documents = pr.working_dir(self.pace / out["folder"])
        self.assertEqual(sorted(p.name for p in documents.iterdir()), sorted(named))


class HelpTests(unittest.TestCase):
    def test_the_help_holds_each_rule_for_folders_inside_documents(self):
        text = section("### Folders inside Documents/")
        self.assertTrue(text, "projects help has no Folders inside Documents/ section")
        for phrase in ("recommend a small set of folders", "chosen from what the project is", "two to four",
                       "Leave out a catch-all", "Do not make `Archive/`", "ask whether to change any or add any",
                       "should be the standard set for this type of project", "Use it, say so, and skip the next two steps",
                       "standing instruction below the mark", "save a decision record", "(records.md)",
                       "kept exactly as received and never edited", "`--folder` once for each folder",
                       "check it is there before calling it made"):
            self.assertIn(phrase, text)

    def test_folders_without_an_id_are_raised_with_the_owner(self):
        text = section("## When something does not fit")
        for phrase in ("Whenever projects are listed", "ask the owner what it is", "can be made a project, or left as it is",
                       "moved into its `Documents/`", "Make or move nothing without the owner's yes"):
            self.assertIn(phrase, text)
        for root in (PACE_FOLDER, PACE_FOLDER.parent / "example"):
            add_ins = root / "Product/Pace add-ins"
            self.assertIn("folders that have no `Pace project.md`", (add_ins / "Project overview/ADD-IN.md").read_text(encoding="utf-8"))
            self.assertIn("has no `Pace project.md` yet", (add_ins / "Daily brief/ADD-IN.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
