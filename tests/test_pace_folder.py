"""Foundation checks against the empty, invented PACE only."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
OWNER_FOLDERS = (
    "Record",
    "Projects",
    "Repos",
    "Views",
    "My add-ins",
    "Release record",
)
POINTERS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".github/copilot-instructions.md",
)


class PaceFolderTests(unittest.TestCase):
    def test_startup_is_pace_md_alone_with_no_owner_data_or_keys(self):
        pace = PACE_FOLDER / "Pace.md"
        self.assertTrue(pace.is_file())
        self.assertEqual(
            {path.name for path in PACE_FOLDER.glob("*.md")} - {"AGENTS.md", "CLAUDE.md"},
            {"Pace.md"},
        )
        text = pace.read_text(encoding="utf-8")
        self.assertIn("this is the only content file needed", text)
        self.assertIn("Open linked help for a relevant task, not as a startup requirement", text)
        for pointer in POINTERS:
            with self.subTest(pointer=pointer):
                self.assertEqual(
                    (PACE_FOLDER / pointer).read_text(encoding="utf-8"),
                    "Read Pace.md in this PACE folder.\n",
                )
        self.assertIn("## Add-in index", text)
        # Owner folders start empty and cannot be mistaken for preloaded data.
        for folder in OWNER_FOLDERS:
            with self.subTest(folder=folder):
                contents = list((PACE_FOLDER / folder).iterdir())
                self.assertEqual([path.name for path in contents], [".gitkeep"])
                self.assertEqual(contents[0].read_bytes(), b"")

        # The template must not ship a signing or approval secret.
        forbidden_name = re.compile(r"(^|[-_. ])(publisher|approval[-_ ]?keys?|private[-_ ]?keys?|secrets?|tokens?)([-_. ]|$)", re.I)
        forbidden_suffixes = {".pem", ".pfx", ".p12", ".key", ".asc", ".kdbx"}
        for path in PACE_FOLDER.rglob("*"):
            with self.subTest(path=path.relative_to(PACE_FOLDER)):
                self.assertIsNone(forbidden_name.search(path.name))
                if path.is_file():
                    self.assertNotIn(path.suffix.lower(), forbidden_suffixes)
                    self.assertIsNone(re.search(
                        rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
                        path.read_bytes(),
                    ))

    def test_semantic_version(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8")
        self.assertRegex(version, r"^3\.\d+\.\d+\n$")
        self.assertIn(f"## {version.strip()}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
