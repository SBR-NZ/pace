"""The independent review of 3.15.0 (7e6e1a0): each finding has a test here that fails on that commit.

Invented data only, in temporary folders.
"""

from __future__ import annotations

import html as markup
from pathlib import Path
import re
import shutil
import sys
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import PACE_FOLDER, read, run
from test_numbers import ADD_IN, AS_AT, EXPECTED, NumberCase, old_style, po

ADD_IN_TEXT = ADD_IN / "ADD-IN.md"
TEMPLATE = ADD_IN / "overview-template.html"
LAUNCHER = ADD_IN / "Launchers/Claude/pace-project-overview/SKILL.md"
WEEKLY = PACE_FOLDER / "Product/Pace add-ins/Weekly review/ADD-IN.md"
HOSTS = PACE_FOLDER / "Product/Help/hosts-and-views.md"
ADD_INS = PACE_FOLDER / "Product/Help/add-ins.md"


def text_of(fragment: str) -> str:
    """A fragment as a host that reads only the page's text gets it: the tags dropped, nothing added between them."""
    return markup.unescape(re.sub(r"<[^>]+>", "", fragment))


def flat(text: str) -> str:
    return " ".join(text.split())


class PageTextTests(NumberCase):
    """Finding 1: the number ran into the tag in the page's text, so 1 and "2 days late" read as "12 days late"."""

    def test_a_numbered_line_reads_apart_as_text(self):
        _, page = self.page()
        lines = [text_of(line) for line in re.findall(r"<summary>(.*?)</summary>", page)]
        self.assertIn("2. 2 days late Board pack Kowhai Books › Budget 2027", lines)
        self.assertIn("4. In 3 days Cost centre list · Sam Lee Kowhai Books › Budget 2027", lines)
        self.assertIn(" Done Logo Kowhai Books", lines)  # no number, and the empty cell adds nothing to read
        self.assertIn("Budget 2027 Next: Board pack 3 2 days late 8 days ago", lines)  # a project's row
        heads = re.search(r'<div class="heads">(.*?)</div>', page).group(1)
        self.assertEqual(text_of(heads), " Project and what is next Open Next due Last activity")
        pair = re.search(r'<li class="pair"[^>]*>\n<p>(.*?)</p>', page).group(1)
        self.assertEqual(text_of(pair), "1. Venue Kowhai Books")

    def test_the_people_and_one_project_pages_read_apart_too(self):
        _, page = self.page("--by-person")
        lines = [text_of(line) for line in re.findall(r"<summary>(.*?)</summary>", page)]
        self.assertTrue(any(line.startswith("You Next: Board pack · Kowhai Books › Budget 2027 3 2 days late")
                            for line in lines), lines)
        _, page = self.page("--project", "kowhai-budget")
        known = re.search(r'<p class="known">(.*?)</p>', page).group(1)
        self.assertTrue(text_of(known).startswith("Part of Kowhai Books Last recorded"), text_of(known))


class WhichOverviewTests(unittest.TestCase):
    """Finding 2: step 7 sent a summary-only overview's numbers to an older page, left "newest" open on a day with two
    pages of one view, and took the page's numbers even when the chat had also given a weekly review list."""

    def test_step_7_says_which_overview_a_number_belongs_to(self):
        text = flat(read(ADD_IN_TEXT))
        for phrase in ("a number belongs to one overview",
                       "**Made in this chat:** use its page, or, when only a chat summary was given, the numbers given "
                       "with it (the tool's result lists them under `numbers`).",
                       "If this chat made more than one overview, or also gave a weekly review list, ask which the owner "
                       "means.",
                       "**Otherwise:** open the newest overview page in `2 Views/`, the latest date in its name, unless "
                       "the owner names another.",
                       "If that date has more than one overview page, ask which, naming each by its view and its As at "
                       "time."):
            self.assertIn(phrase, text)
        self.assertNotIn("the newest overview unless the owner names another", text)
        self.assertNotIn("if that day has more than one view, ask which", text)


class LaterChatTests(unittest.TestCase):
    """Finding 3: in a later chat, "3 is done" matched only the Weekly review's index line, and this add-in's limits
    said nothing in it carried over, even to its own step for numbers."""

    def test_pace_md_says_where_numbers_come_from(self):
        for path in (PACE_FOLDER / "Pace.md", PACE_FOLDER.parent / "example/Pace.md"):
            with self.subTest(path=path.parent.name):
                index = read(path).split("## Add-in index", 1)[1].split("<!--", 1)[0]
                self.assertIn("When the owner names items by number, such as \"3 is done\", the numbers belong to the list or "
                              "page they came from: a weekly review's list, which lasts only for its chat, or a Project "
                              "overview page in `2 Views/`; ask if it could be either.", index)

    def test_the_index_line_launcher_and_limits_name_numbers(self):
        purpose = "Show where one project, every project or one person's work stands, and act on items the owner names " \
                  "by their numbers on its page."
        self.assertIn(f"**Purpose:** {purpose}", read(ADD_IN_TEXT))
        self.assertIn(f"- **Project overview** - {purpose} `Product/Pace add-ins/Project overview/ADD-IN.md`", read(ADD_INS))
        self.assertIn("or names items by their numbers on an overview page, such as \"3 is done\".", read(LAUNCHER).split("---")[1])
        limits = read(ADD_IN_TEXT).split("## Limits", 1)[1]
        self.assertIn("These steps apply only while preparing this overview and acting on its numbers. Nothing else here "
                      "carries over to the rest of the chat.", limits)


class ResultTests(NumberCase):
    """Finding 4: the list of numbers, as long as the open work, came before whether the search was complete, and a
    partial page's message did not say so."""

    def test_numbers_come_last_and_a_partial_page_says_so(self):
        (self.pace / "Record" / "20261020T020000Z--kowhai--bad001.md").write_bytes(b"---\nformat: record-1\n\xff\xfe\n")
        for save in (("--save",), ()):
            with self.subTest(save=save):
                out, _ = run(po, "--pace", str(self.pace), "--as-at", AS_AT, *save)
                self.assertFalse(out["complete"])
                self.assertEqual(list(out)[-1], "numbers")
                self.assertLess(list(out).index("complete"), list(out).index("numbers"))
                self.assertIn("Partial: something could not be read; see could_not_read.", out["message"])

    def test_a_complete_page_says_nothing_of_partial(self):
        out, _ = self.page()
        self.assertTrue(out["complete"])
        self.assertNotIn("Partial", out["message"])
        self.assertEqual(list(out)[-1], "numbers")


class TwoWaysTests(unittest.TestCase):
    """Finding 5: step 7 saved the change before asking which account stands, which update-action refuses."""

    def test_two_ways_are_settled_before_a_change_is_saved(self):
        text = flat(read(ADD_IN_TEXT))
        self.assertIn("For an item recorded two ways, ask first which account stands, by its letter on the page. Once the owner says, save a "
                      "withdrawal of the other, then make the owner's change to the one that stands.", text)
        self.assertNotIn("once the owner says which account stands, withdraw the other", text)


class GridTests(NumberCase):
    """Finding 6: a customised template given the new number styles but not the new grid still got the number column,
    so each line spilled out of its three columns."""

    def test_new_number_styles_on_the_old_grid_number_inline(self):
        copy = self.pace / "3 My add-ins/Project overview - mine"
        shutil.copytree(ADD_IN, copy)
        template = copy / "overview-template.html"
        text = old_style(read(template))
        style_end = text.index("</style>")
        text = text[:style_end] + (".no { color: var(--muted); font-size: 0.9rem; }\n"
                                   ".pair .no { display: inline-block; min-width: 1.75rem; }\n") + text[style_end:]
        template.write_text(text, encoding="utf-8")
        _, page = self.page("--template", str(template))
        self.assertNotIn('<summary><span class="no">', page)
        self.assertIn('<span class="tag late">2 days late</span> <span class="subj"><span class="no">2.</span> Board pack', page)

    def test_the_columns_are_counted_from_the_line_grid(self):
        self.assertTrue(po.number_column(".row > summary {\n  display: grid;\n  grid-template-columns: 2rem 8rem minmax(0, 1fr) "
                                         "auto;\n}"))
        self.assertFalse(po.number_column(".row > summary { grid-template-columns: 7rem minmax(0, 1fr) auto; }\n.no { color: red; }"))
        self.assertFalse(po.number_column(".node { display: grid; }"))
        self.assertFalse(po.number_column(""))


class TextTests(unittest.TestCase):
    """Finding 7: words that did not match what the tool gives or what the page holds."""

    def test_the_chat_summary_promises_numbers_only_where_the_result_has_them(self):
        text = read(ADD_IN_TEXT)
        self.assertIn("Then a few lines on what is recorded two ways, overdue, and due today or in the next 7 days, each "
                      "with its number, and how much is waiting on the owner;", text)

    def test_three_accounts_are_spelled_out_for_a_page_made_by_hand(self):
        note = flat(read(TEMPLATE).split("-->", 1)[0])
        self.assertIn("an item recorded two ways gets data-requests with the request id of each account, a space between.",
                      note)
        self.assertIn("4. Every item is one line: its number, its tag, its subject and where it is, with a space between "
                      "each", note)
        body = read(TEMPLATE).split("<body>", 1)[1]
        self.assertNotIn("both accounts", body)
        self.assertIn('data-requests="{{the request id of each account, a space between}}"', body)
        self.assertIn("an item recorded two ways has each account's id there, and its `request` is null.", read(HOSTS))

    def test_the_weekly_review_says_what_a_line_holds_before_whose_numbers_they_are(self):
        self.assertIn("Number the items from 1 across the whole list, one line each: how late, how soon or how long open it "
                      "is, its subject, its project, and who owes it when that is not the owner. These numbers belong to this "
                      "list; an overview page has its own.", read(WEEKLY))

    def test_the_views_help_says_request_ids_are_in_the_page(self):
        text = read(HOSTS)
        self.assertIn("each item's request id is kept in the page, never shown: each numbered line holds its own, and the "
                      "Searched line, which covers every record file, stands in for the rest.", text)
        self.assertNotIn("stands in for a request id on each item", text)
        self.assertIn("carry over any new or changed styles", text)


if __name__ == "__main__":
    unittest.main()
