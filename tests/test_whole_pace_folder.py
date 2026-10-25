"""One deterministic integration check: invented PACE folder, example, record and update."""

from pathlib import Path
from unittest import mock
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote

from test_updates import GIT_ENV, Repo, owner_view, pu

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
EXAMPLE = ROOT / "example"
RECORD_TOOL = PACE_FOLDER / "Product/Tools/pace_record.py"


class WholePaceFolderTest(unittest.TestCase):
    def test_standing_instructions_section_is_empty_and_identical(self):
        # Both Pace.md files carry the same short, empty section directly after "Two boundaries".
        sections = []
        for root in (PACE_FOLDER, EXAMPLE):
            text = (root / "Pace.md").read_text(encoding="utf-8")
            match = re.search(r"^## Standing instructions\n.*?(?=^## |\Z)", text, re.S | re.M)
            self.assertIsNotNone(match, f"{root.name}/Pace.md has no Standing instructions section")
            section = match.group(0)
            self.assertTrue(section.rstrip().endswith("\nNone yet."), f"{root.name}/Pace.md section is not empty")
            self.assertEqual(section.count("None yet."), 1)
            headings = re.findall(r"^## .*$", text, re.M)
            self.assertEqual(headings[headings.index("## Two boundaries") + 1], "## Standing instructions")
            sections.append(section)
        self.assertEqual(sections[0], sections[1])
        # The section links to the help page holding the detail, and that page has the matching heading.
        self.assertIn("(Product/Help/records.md#standing-instructions)", sections[0])
        self.assertIn("\n## Standing instructions\n", (PACE_FOLDER / "Product/Help/records.md").read_text(encoding="utf-8"))

    def test_invented_start_to_finish(self):
        # A new copy starts with exactly one content entry point and nothing enabled.
        pace = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        self.assertEqual({p.name for p in PACE_FOLDER.glob("*.md")} - {"AGENTS.md", "CLAUDE.md"}, {"Pace.md"})
        self.assertIn("None switched on yet.", pace)
        self.assertNotRegex(pace.split("## Add-in index")[1].split("## Help")[0], r"(?m)^- \*\*")
        for pointer in ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"):
            self.assertEqual((PACE_FOLDER / pointer).read_text(encoding="utf-8"), "Read Pace.md in this PACE folder.\n")
        # Every Markdown help link, including the front door and client notes, resolves.
        broken = []
        pages = [ROOT / "README.md", *ROOT.glob("docs/*.md"),
                 *PACE_FOLDER.rglob("*.md"), *EXAMPLE.rglob("*.md")]
        for page in pages:
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
                target = unquote(target.split("#")[0].strip("<>"))
                if target and not re.match(r"^[a-z]+://", target) and not (page.parent / target).is_file():
                    broken.append((page.relative_to(ROOT).as_posix(), target))
        self.assertEqual(broken, [])
        # Projects live in 1 Projects/, each with its files in Documents/; the older names appear nowhere in either folder.
        for root in (PACE_FOLDER, EXAMPLE):
            self.assertTrue((root / "1 Projects").is_dir())
            self.assertFalse((root / "Project files").exists())
            self.assertIn("- `1 Projects/` - projects, each with its files in `Documents/`.", (root / "Pace.md").read_text(encoding="utf-8"))
            stale = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                           if p.is_file() and "__pycache__" not in p.parts
                           and re.search(rb"(?i)project files|working files", p.read_bytes()))
            self.assertEqual(stale, [])
        for root in (PACE_FOLDER, EXAMPLE):
            index = (root / "Pace.md").read_text(encoding="utf-8").split("## Add-in index")[1].split("## Help")[0]
            for path in re.findall(r"(?m)^- \*\*[^\n]+`([^`]+/ADD-IN\.md)`", index):
                self.assertTrue((root / path).is_file(), path)
            # The catalogue's copyable index lines also all resolve.
            catalogue = (root / "Product/Help/add-ins.md").read_text(encoding="utf-8")
            for path in re.findall(r"(?m)^- \*\*[^\n]+`([^`]+/ADD-IN\.md)`", catalogue):
                self.assertTrue((root / path).is_file(), path)
            # No signing/publishing mechanism or credential artifacts in either folder.
            for item in root.rglob("*"):
                rel = item.relative_to(root).as_posix().lower()
                self.assertNotRegex(rel, r"(^|/)(?:publisher|keys?|signatures?|secrets?|tokens?|\.git)(?:/|\.|$)")
                if item.is_file():
                    self.assertNotIn(item.suffix.lower(), (".pem", ".pfx", ".p12", ".key", ".asc"))
                    self.assertNotIn(b"-----BEGIN PRIVATE KEY-----", item.read_bytes())

        # Neither Pace.md describes its folders as an "empty template": that wording is wrong once an owner's folders fill up.
        for root in (PACE_FOLDER, EXAMPLE):
            self.assertNotIn("empty template", (root / "Pace.md").read_text(encoding="utf-8").lower(), f"{root.name}/Pace.md")
        # Owner add-ins sit in a top-level 3 My add-ins/ beside Product/; the older place is named only where help explains it.
        for root in (PACE_FOLDER, EXAMPLE):
            self.assertIn("- `3 My add-ins/` - owner-made or customised add-ins", (root / "Pace.md").read_text(encoding="utf-8"))
            self.assertEqual((root / "3 My add-ins/.gitkeep").read_bytes(), b"")
            self.assertFalse((root / "Pace").exists())
            mentions = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                              if p.is_file() and b"Pace/Add-ins" in p.read_bytes())
            self.assertEqual(mentions, ["Product/Help/add-ins.md", "Product/Help/updates.md", "Product/Tools/pace_update.py"])

        # The invented copy has a live index line and one shared repo home with an explicit link.
        example_index = (EXAMPLE / "Pace.md").read_text(encoding="utf-8")
        self.assertIn("**Daily brief**", example_index)
        self.assertIn("Home project id: maple-website", (EXAMPLE / "Repos/Maple Lantern/Website/website-code/Pace repo.md").read_text())
        self.assertIn("Using project id: maple-campaign", (EXAMPLE / "Repos/Maple Lantern/Campaign/website-code/Pace repo link.md").read_text())
        release_note = (EXAMPLE / "Release record/Invented release record.md").read_text(encoding="utf-8")
        self.assertIn(pu.file_list_digest(pu.read_tree(EXAMPLE / "Product")), release_note)
        self.assertIn("proposed, not installed", release_note)
        self.assertTrue((EXAMPLE / "2 Views/2026-10-23-open-work.md").is_file())
        self.assertIn("record creation", (EXAMPLE / "2 Views/2026-10-23-year-2026.md").read_text())

        def record(*args):
            done = subprocess.run([sys.executable, str(RECORD_TOOL), "--pace", str(EXAMPLE), *args],
                                  capture_output=True, text=True)
            return done.returncode, json.loads(done.stdout)

        code, projects = record("projects")
        self.assertEqual(code, 0, projects)
        self.assertEqual({p["id"] for p in projects["projects"]}, {"maple-lantern", "maple-website", "maple-campaign", "maple-budget"})
        code, found = record("find", "--project", "maple-website")
        self.assertEqual(code, 0, found)
        self.assertTrue(found["coverage"]["complete"])
        self.assertEqual(len(found["records"]), 4)
        code, confirmation = record("confirmation-status", "--request", "20261023T113000Z--maple-website--yes001")
        self.assertEqual((code, confirmation["status"]), (0, "confirmed"), confirmation)

        # Pull an invented release against a disposable copy, not the example or any live folder.
        with tempfile.TemporaryDirectory(prefix="pace-whole-PACE-") as temporary, mock.patch.dict(os.environ, GIT_ENV):
            base = Path(temporary)
            repo = Repo(base / "invented-repository")
            shutil.copytree(PACE_FOLDER, repo.path / "PACE")
            (repo.path / "PACE/Product/Help/records.md").write_text("# Invented revised help\n", encoding="utf-8")
            commit = repo.commit("Invented Product release")
            repo.tag("v3.6.0")
            folder = base / "owner-copy"
            shutil.copytree(EXAMPLE, folder)
            protected_before = owner_view(folder)
            result = pu.apply(folder, str(repo.path), "v3.6.0", commit,
                              go_ahead=f"Yes, install invented v3.6.0 at commit {commit}.")
            self.assertEqual(result["status"], "installed", result.get("message"))
            self.assertEqual(owner_view(folder), protected_before)
            self.assertEqual((folder / "Product/Help/records.md").read_text(encoding="utf-8"), "# Invented revised help\n")
            self.assertTrue((folder / "Release record/Installs").is_dir())


if __name__ == "__main__":
    unittest.main()
