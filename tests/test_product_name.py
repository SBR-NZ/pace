"""The product's name: Pace by SBR everywhere Pace names itself; the legal name only where the law needs it.

Invented data only.
"""

from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_pace_md_parts import TEMPLATE, marked, pu

ROOT = Path(__file__).resolve().parents[1]
NAME = "Pace by SBR"
OLD_NAME = "Pace by Simply Better Reports"
LEGAL_NAME = "Simply Better Reports Limited, trading as SBR"
SHIPPED = ("PACE", "example", "docs")


def shipped_text_files():
    for top in SHIPPED:
        for path in sorted((ROOT / top).rglob("*")):
            if path.is_file() and path.suffix in (".md", ".py", ".html", ".txt", ".json", ""):
                yield path
    yield ROOT / "README.md"


class ProductNameTests(unittest.TestCase):
    def test_pace_md_and_readme_open_with_the_name(self):
        for path in (ROOT / "PACE/Pace.md", ROOT / "example/Pace.md", ROOT / "README.md"):
            first = path.read_text(encoding="utf-8").split("\n", 1)[0]
            self.assertEqual(first, "# " + NAME, path)

    def test_the_readme_says_what_sbr_stands_for(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Pace is made by SBR (Simply Better Reports).", readme)

    def test_nothing_shipped_uses_the_old_name(self):
        for path in shipped_text_files():
            self.assertNotIn(OLD_NAME, path.read_text(encoding="utf-8", errors="replace"), path)

    def test_the_legal_name_stays_in_the_licence(self):
        for path in (ROOT / "LICENSE", ROOT / "PACE/Product/LICENSE.md", ROOT / "example/Product/LICENSE.md"):
            if path.exists():
                self.assertIn(LEGAL_NAME, path.read_text(encoding="utf-8").split("\n", 1)[0], path)

    def test_an_update_renames_a_pace_md_the_owner_left_as_shipped(self):
        older = marked(TEMPLATE.replace("# " + NAME, "# " + OLD_NAME, 1))
        own = older.replace(pu.YOUR_LINES + "\n", pu.YOUR_LINES + "\n- An invented line of the owner's.\n", 1)
        plan = pu.plan_pace_md(own.encode(), TEMPLATE.encode())
        self.assertEqual(plan["status"], "update")
        after = plan["after"].decode("utf-8")
        self.assertTrue(after.startswith("# " + NAME + "\n"), after[:80])
        self.assertIn("- An invented line of the owner's.", after)

    def test_an_update_keeps_a_title_the_owner_changed(self):
        older = marked(TEMPLATE.replace("# " + NAME, "# " + OLD_NAME, 1)).replace("# " + OLD_NAME, "# Our Pace", 1)
        plan = pu.plan_pace_md(older.encode(), TEMPLATE.encode())
        self.assertIn("the opening lines", plan["parts"].get("kept_changed", []))
        self.assertTrue((plan.get("after") or older.encode()).decode("utf-8").startswith("# Our Pace\n"))


if __name__ == "__main__":
    unittest.main()
