"""The owner's name in Pace.md: how it is read, what it changes, and how an update brings the part in.

Invented data only, in temporary folders.
"""

from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_pace_md_parts import TEMPLATE, EXAMPLE, marked, pu
from test_records import pr
from test_overview_tool import OWNER, OverviewCase
from test_weekly_review import with_owner_line

PART = "## The owner's name"


def without_owner_part(text: str) -> str:
    """Pace.md as a release before this part shipped it, re-recorded as shipped."""
    start = text.index(PART)
    end = text.index("## Time zone")
    return marked(text[:start] + text[end:])


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-owner-")
        self.pace = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def names(self, text, encoding="utf-8"):
        (self.pace / "Pace.md").write_bytes(text.encode(encoding))
        return pr.owner_names(self.pace)

    def test_each_owner_line_is_one_spelling_in_the_order_written(self):
        self.assertEqual(self.names(TEMPLATE), [])
        text = TEMPLATE.replace("<!-- Your lines go below this one. Pace updates never change them. -->\n## Time zone",
                                "<!-- Your lines go below this one. Pace updates never change them. -->\n"
                                "Owner: Rangi Parata\n- owner: `Rangi`\nOWNER:   Rangi   Parata  \nOwner:\n\n## Time zone")
        self.assertEqual(self.names(text), ["Rangi Parata", "Rangi"])
        # A heading written with a typographic apostrophe is the same part.
        self.assertEqual(self.names(text.replace("## The owner's name", "## The owner\u2019s name")), ["Rangi Parata", "Rangi"])

    def test_no_pace_md_or_one_that_is_not_text_gives_no_names(self):
        self.assertEqual(pr.owner_names(self.pace), [])
        self.assertEqual(self.names("Owner: Renée\n", encoding="utf-16"), [])

    def test_paces_own_words_name_no_owner(self):
        # Pace's own text in the part gives an example inside a sentence, which is never read as a name.
        for line in TEMPLATE.splitlines():
            self.assertEqual(pr.owner_line_name(line), "", line)


class PaceMdTests(unittest.TestCase):
    def test_the_part_sits_before_the_time_zone_in_both_pace_md_files(self):
        for text in (TEMPLATE, (EXAMPLE / "Pace.md").read_text(encoding="utf-8")):
            parts = [part["id"] for part in pu.pace_md_parts(text)[0]]
            self.assertEqual(parts.index("the-owner-s-name") + 1, parts.index("time-zone"))
            part = text[text.index(PART):text.index("## Time zone")]
            for phrase in ("So the tools know which work is the owner's", "as records write it in `owed-by` and `for`",
                           "`Owner: Rangi Parata`", "one more for each other spelling",
                           "With none, only work owed by `owner` counts as the owner's.",
                           "<!-- Your lines go below this one. Pace updates never change them. -->"):
                self.assertIn(phrase, part)
        self.assertEqual(pr.owner_names(EXAMPLE), ["Mere Walker"])

    def test_an_update_adds_the_part_and_keeps_the_owners_lines(self):
        older = without_owner_part(TEMPLATE)
        own = older.replace("<!-- Your lines go below this one. Pace updates never change them. -->\n## Help",
                            "<!-- Your lines go below this one. Pace updates never change them. -->\n"
                            "Time zone: Pacific/Auckland\n\n## Help")
        planned = pu.plan_pace_md(own.encode("utf-8"), TEMPLATE.encode("utf-8"))
        self.assertEqual(planned["status"], "update")
        self.assertEqual(planned["parts"], {"added": ["The owner's name"]})
        after = planned["after"].decode("utf-8")
        self.assertLess(after.index(PART), after.index("## Time zone"))
        self.assertIn("Time zone: Pacific/Auckland\n", after)
        # The owner then adds their line below the new mark, and later updates keep it.
        with_line = after.replace("<!-- Your lines go below this one. Pace updates never change them. -->\n## Time zone",
                                  "<!-- Your lines go below this one. Pace updates never change them. -->\nOwner: Rangi Parata\n\n"
                                  "## Time zone")
        again = pu.plan_pace_md(with_line.encode("utf-8"), TEMPLATE.encode("utf-8"))
        self.assertEqual(again["status"], "current")


class OverviewTests(OverviewCase):
    def test_the_owner_line_decides_whose_work_is_yours(self):
        f = self.f
        f.action(self.budget, "Mine", owed_by=OWNER)
        f.action(self.budget, "Also mine", owed_by="Rangi")
        f.action(self.budget, "Theirs", owed_by="Ana Ruiz")
        out, _ = f.run(owner=False)
        self.assertEqual((out["counts"]["waiting_on_you"], out["counts"]["waiting_on_others"]), (0, 3))
        self.assertIn("Pace.md has no Owner: line and no --owner was given", out["message"])
        with_owner_line(f, OWNER)
        out, _ = f.run(owner=False)
        self.assertEqual((out["counts"]["waiting_on_you"], out["counts"]["waiting_on_others"]), (1, 2))
        self.assertEqual(out["owner_names"], [OWNER])
        self.assertNotIn("no Owner: line", out["message"])
        # --owner adds a spelling for one run, beside the line.
        out, _ = f.run("--owner", "Rangi", owner=False)
        self.assertEqual((out["counts"]["waiting_on_you"], out["counts"]["waiting_on_others"]), (2, 1))
        self.assertEqual(out["owner_names"], ["Rangi", OWNER])

    def test_the_by_person_page_puts_the_owner_first_by_the_line(self):
        f = self.f
        with_owner_line(f, OWNER)
        f.action(self.budget, "Mine", owed_by=OWNER)
        f.action(self.budget, "Theirs", owed_by="Ana Ruiz")
        out, _ = f.run("--by-person", "--save", owner=False)
        page = self.page(out)
        self.assertLess(page.index(">You<"), page.index(">Ana Ruiz<"))
        self.assertNotIn(f">{OWNER}<", page)


class AddInTests(unittest.TestCase):
    def test_the_add_ins_that_need_the_name_read_it_from_pace_md(self):
        root = Path(__file__).resolve().parents[1] / "PACE/Product/Pace add-ins"
        for name in ("Project overview", "Daily brief", "Weekly review"):
            with self.subTest(add_in=name):
                text = (root / name / "ADD-IN.md").read_text(encoding="utf-8")
                self.assertIn("from the `Owner:` lines in `Pace.md`", text)
                self.assertNotIn("Daniel", text)


if __name__ == "__main__":
    unittest.main()
