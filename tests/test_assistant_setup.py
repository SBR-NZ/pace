"""The owner's assistant setup: where it lives, what the help gives to start it, and that updates leave it alone."""

from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_updates import pu

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
EXAMPLE = ROOT / "example"
HOSTS = PACE_FOLDER / "Product/Help/hosts-and-views.md"
SECRET = re.compile(r"(?i)password:|api key:|token:|secret:|-----BEGIN")  # a value, not the rule against keeping one


class HelpTests(unittest.TestCase):
    def test_the_help_says_what_it_holds_and_how_it_is_kept(self):
        text = HOSTS.read_text(encoding="utf-8")
        part = text[text.index("## The owner's assistants\n"):text.index("## Optional dated views\n")]
        for phrase in ("`3 My add-ins/Assistant setup.md` lists the assistants the owner uses and what each can reach",
                       "Read it when choosing how to do a task", "It is the owner's file, so updates never change it.",
                       "Never put passwords, keys, tokens or account numbers in it.",
                       "writes down only what it can see of its own setup", "it never guesses another assistant's",
                       "writes them only on the owner's yes, then reads the file back", "`Last checked:`",
                       "shows the owner the lines to paste instead", "more than 90 days ago"):
            self.assertIn(phrase, part)
        template = re.search(r"```text\n(# Assistant setup\n.*?)```", part, re.S).group(1)
        self.assertRegex(template, r"(?m)^Last checked: \d{4}-\d{2}-\d{2}$")
        self.assertEqual(re.findall(r"(?m)^## (.+)$", template), ["Claude", "Microsoft 365 Copilot"])
        for line in ("- Skills and plugins:", "- Connections:", "- Scheduled tasks:", "- Cannot:", "- Reaches the Pace folder:"):
            self.assertIn(line, template)

    def test_pace_md_points_to_it_from_where_things_belong(self):
        for root in (PACE_FOLDER, EXAMPLE):
            text = (root / "Pace.md").read_text(encoding="utf-8")
            part = text[text.index("## Where things belong"):text.index("## Rounding up")]
            self.assertIn("and `Assistant setup.md`, which says what each of the owner's assistants can reach. Read it when "
                          "choosing which assistant or connection suits a task.", part)

    def test_the_example_keeps_one_in_the_help_form_with_no_secrets(self):
        text = (EXAMPLE / "3 My add-ins/Assistant setup.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Assistant setup\n"))
        self.assertRegex(text, r"(?m)^Last checked: \d{4}-\d{2}-\d{2}$")
        self.assertIsNone(SECRET.search(text))
        self.assertFalse((PACE_FOLDER / "3 My add-ins/Assistant setup.md").exists())  # an owner's file, never shipped


class UpdateTests(unittest.TestCase):
    def test_updates_list_only_add_in_folders_as_the_owners_add_ins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "3 My add-ins/Board notes").mkdir(parents=True)
            (root / "3 My add-ins/Assistant setup.md").write_text("# Assistant setup\n", encoding="utf-8")
            (root / "3 My add-ins/.gitkeep").write_text("", encoding="utf-8")
            self.assertEqual(pu._owner_addins(root), ["Board notes"])
            self.assertIn("3 My add-ins/", pu.PROTECTED)


if __name__ == "__main__":
    unittest.main()
