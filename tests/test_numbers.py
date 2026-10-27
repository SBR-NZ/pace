"""Numbered items on the Project overview (3.15.0): each open item, and each item recorded two ways, has one number
on its page, so the owner can name it in chat, and the page keeps each number's request id to find it again.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import PACE_FOLDER, OWNER, po, read, run, write_project, write_record

AS_AT = "2026-10-30T09:00:00+13:00"
ADD_IN = PACE_FOLDER / "Product/Pace add-ins/Project overview"
TWO_WAYS = ["20261025T010000Z--kowhai--num007", "20261025T020000Z--kowhai--num008"]
EXPECTED = {  # number: the request id of the item's current account
    2: "20261020T010000Z--kowhai-budget--num001",  # overdue
    3: "20261021T010000Z--kowhai--num002",         # due today, owed by Ana Ruiz
    4: "20261019T010000Z--kowhai-budget--num009",  # due in 3 days, owed by Sam Lee for the owner
    5: "20261029T010000Z--kowhai--num010",         # new this week, no due date
    6: "20261022T010000Z--kowhai-budget--num003",  # no due date
}


def make_folder(base: Path) -> Path:
    pace = base / "PACE"
    shutil.copytree(PACE_FOLDER, pace, ignore=shutil.ignore_patterns("__pycache__"))
    mark = "<!-- Your lines go below this one. Pace updates never change them. -->"
    text = read(pace / "Pace.md").replace(f"{mark}\n## Time zone", f"{mark}\nOwner: {OWNER}\n\n## Time zone")
    (pace / "Pace.md").write_text(text.replace(f"{mark}\n## Help", f"{mark}\nTime zone: Pacific/Auckland\n\n## Help"),
                                  encoding="utf-8")
    write_project(pace, "kowhai", "Kowhai Books")
    write_project(pace, "kowhai-budget", "Kowhai Books/Budget 2027", parent="kowhai")
    write_record(pace, EXPECTED[2], subject="Board pack", owed_by=OWNER, state="open", due="2026-10-28")
    write_record(pace, EXPECTED[3], subject="Site copy", owed_by="Ana Ruiz", state="open", due="2026-10-30")
    write_record(pace, EXPECTED[6], subject="Wage assumptions", owed_by=OWNER, state="open")
    write_record(pace, "20261023T010000Z--kowhai--num004", subject="Logo", owed_by=OWNER, state="open")
    write_record(pace, "20261028T010000Z--kowhai--num005", subject="Logo", owed_by=OWNER, state="done",
                 corrects="20261023T010000Z--kowhai--num004")
    write_record(pace, "20261024T010000Z--kowhai--num006", subject="Venue", owed_by=OWNER, state="open")
    write_record(pace, TWO_WAYS[0], subject="Venue", owed_by=OWNER, state="open", due="2026-11-20",
                 corrects="20261024T010000Z--kowhai--num006")
    write_record(pace, TWO_WAYS[1], subject="Venue", owed_by=OWNER, state="cancelled",
                 corrects="20261024T010000Z--kowhai--num006")
    write_record(pace, EXPECTED[4], subject="Cost centre list", owed_by="Sam Lee", state="open", due="2026-11-02",
                 **{"for": OWNER})
    write_record(pace, EXPECTED[5], subject="Holiday hours", owed_by=OWNER, state="open")
    return pace


def old_style(text: str) -> str:
    """The template as a customised copy made before numbers would have it: no number column in its styles."""
    for new, old in (("grid-template-columns: 1.75rem 7rem minmax(0, 1fr) auto;", "grid-template-columns: 7rem minmax(0, 1fr) auto;"),
                     (".more { padding: 0.25rem 0.25rem 0.75rem 11rem;", ".more { padding: 0.25rem 0.25rem 0.75rem 8.25rem;"),
                     ("\n.no { color: var(--muted); font-size: 0.9rem; font-variant-numeric: tabular-nums; text-align: right; }", ""),
                     ("\n.pair .no { display: inline-block; min-width: 1.75rem; margin-right: 0.25rem; }", ""),
                     (".row > summary { grid-template-columns: 1.5rem 5.5rem minmax(0, 1fr); }",
                      ".row > summary { grid-template-columns: 5.5rem minmax(0, 1fr); }"),
                     (".side { grid-column: 3;", ".side { grid-column: 2;")):
        assert text.count(new) == 1, new
        text = text.replace(new, old)
    return text


def numbered(html: str) -> list:
    """Each numbered line in page order, as (number, request ids, what the line shows as its number)."""
    found = []
    for match in re.finditer(r'<li class="(?:item|pair)" data-no="(\d+)" data-requests?="([^"]+)">\s*(?:<details class="row">\s*'
                             r'<summary>)?(?:<p>)?<span class="no">([^<]*)</span>', html):
        found.append((int(match.group(1)), match.group(2).split(), match.group(3)))
    return found


class NumberCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-numbers-")
        self.pace = make_folder(Path(self._temp.name))

    def tearDown(self):
        self._temp.cleanup()

    def page(self, *extra) -> tuple:
        out, code = run(po, "--pace", str(self.pace), "--as-at", AS_AT, "--save", *extra)
        self.assertEqual((out["status"], code), ("saved", 0), out)
        return out, read(self.pace / out["page"])


class EveryProjectTests(NumberCase):
    def test_numbers_run_two_ways_then_needs_attention_then_the_rows(self):
        out, html = self.page()
        view = html[html.index('<section class="part two-ways">'):]  # after the last 7 days
        firsts = []
        for number, _, _ in numbered(view):
            if number not in firsts:
                firsts.append(number)
        self.assertEqual(firsts, [1, 2, 3, 4, 5, 6])
        self.assertEqual([entry["number"] for entry in out["numbers"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(out["numbers"][0]["requests"], TWO_WAYS)
        self.assertIsNone(out["numbers"][0]["request"])
        self.assertEqual({entry["number"]: entry["request"] for entry in out["numbers"][1:]}, EXPECTED)
        self.assertEqual([(entry["number"], entry["subject"]) for entry in out["needs_attention"]],
                         [(2, "Board pack"), (3, "Site copy"), (4, "Cost centre list")])
        self.assertEqual({entry["number"] for group in out["recorded_two_ways"] for entry in group}, {1})

    def test_an_item_keeps_its_number_wherever_it_appears(self):
        _, html = self.page()
        seen: dict = {}
        for number, requests, shown in numbered(html):
            self.assertEqual(shown, f"{number}.")
            seen.setdefault(number, set()).add(tuple(requests))
        self.assertEqual({number: len(requests) for number, requests in seen.items()}, {n: 1 for n in range(1, 7)})
        lines = [number for number, _, _ in numbered(html)]
        self.assertEqual(lines.count(2), 2)  # in Needs attention and in its project's row
        self.assertEqual(lines.count(5), 2)  # new in the last 7 days and in its project's row
        self.assertEqual(lines.count(6), 1)

    def test_done_and_cancelled_lines_have_no_number(self):
        _, html = self.page()
        start = html.index('<details class="week">')
        week = html[start:html.index("</details>\n<section", start)]
        done = week[week.index('<p class="group">Done</p>'):]
        self.assertIn('<li class="item"><details class="row">\n<summary><span class="no"></span> <span class="tag">Done</span>',
                      done)
        self.assertNotIn("data-no", done)


class OtherViewTests(NumberCase):
    def test_by_person_gives_one_number_to_work_two_people_share(self):
        out, html = self.page("--by-person")
        sam = [number for number, requests, _ in numbered(html) if requests == [EXPECTED[4]]]
        self.assertGreaterEqual(len(sam), 2)  # waited for by the owner, owed by Sam Lee, and in Needs attention
        self.assertEqual(len(set(sam)), 1)
        self.assertEqual(sorted(entry["number"] for entry in out["numbers"]), list(range(1, len(out["numbers"]) + 1)))

    def test_one_project_numbers_its_own_page_afresh(self):
        write_record(self.pace, "20261026T010000Z--kowhai-budget--num011", kind="decision", subject="Budget basis",
                     from_="owner", words="Use last year's actuals.")
        out, html = self.page("--project", "kowhai-budget")
        # Board pack is 2 on the page for every project, and 1 here.
        self.assertEqual([(entry["number"], entry["request"]) for entry in out["numbers"]],
                         [(1, EXPECTED[2]), (2, EXPECTED[4]), (3, EXPECTED[6])])
        self.assertEqual([(number, requests) for number, requests, _ in numbered(html)],
                         [(1, [EXPECTED[2]]), (2, [EXPECTED[4]]), (1, [EXPECTED[2]]), (3, [EXPECTED[6]]), (2, [EXPECTED[4]])])
        recent = html[html.index("<h2>Last three weeks"):]
        self.assertIn('<li class="item"><details class="row">\n<summary><span class="no"></span> <span class="tag">Decided</span> '
                      '<span class="subj">Budget basis</span>', recent)
        self.assertNotIn("data-no", recent)

    def test_a_template_from_before_numbers_shows_them_at_the_start_of_the_subject(self):
        copy = self.pace / "3 My add-ins/Project overview - mine"
        shutil.copytree(ADD_IN, copy)
        template = copy / "overview-template.html"
        template.write_text(old_style(read(template)), encoding="utf-8")
        out, html = self.page("--template", str(template))
        self.assertNotIn("styles were used", out["message"])  # its own styles are kept
        self.assertNotIn('<summary><span class="no">', html)
        self.assertIn('<li class="item" data-no="2" data-request="20261020T010000Z--kowhai-budget--num001"><details class="row">\n'
                      '<summary><span class="tag late">2 days late</span> <span class="subj"><span class="no">2.</span> Board pack'
                      '</span>', html)
        self.assertIn('<li class="pair" data-no="1" data-requests="' + " ".join(TWO_WAYS) + '">\n'
                      '<p><span class="no">1.</span> <strong>Venue</strong>', html)
        self.assertIn('<summary><span class="tag">Done</span> <span class="subj">Logo</span>', html)
        self.assertEqual([entry["number"] for entry in out["numbers"]], [1, 2, 3, 4, 5, 6])


def lines_with_numbers(html: str) -> list:
    """Each numbered line in page order as (number, request ids), whichever way the template shows the number."""
    return [(int(match.group(1)), match.group(2).split())
            for match in re.finditer(r'<li class="(?:item|pair)" data-no="(\d+)" data-requests?="([^"]+)">', html)]


def without_week(html: str) -> tuple:
    """The page without its Last 7 days part, and that part."""
    start = html.index('<details class="week">')
    end = html.index("</details>\n<section", start) + len("</details>")
    return html[:start] + html[end:], html[start:end]


MOVED = "20261027T010000Z--kowhai-budget--num013"  # Wage assumptions, given a due date in the last 7 days


class MoreRuleTests(NumberCase):
    """Rules the first tests did not pin down: a corrected item, each view's order and the last 7 days, the summary
    without a page, three accounts at once, and both ways a template can show the numbers."""

    def correct_wage_assumptions(self):
        write_record(self.pace, MOVED, subject="Wage assumptions", owed_by=OWNER, state="open", due="2026-11-05",
                     corrects=EXPECTED[6])

    def test_a_corrected_item_is_found_by_its_current_account(self):
        self.correct_wage_assumptions()
        out, html = self.page()
        lines = [requests for number, requests in lines_with_numbers(html) if MOVED in requests or EXPECTED[6] in requests]
        self.assertGreaterEqual(len(lines), 3)  # due date changed, Needs attention and its row
        self.assertEqual({tuple(requests) for requests in lines}, {(MOVED,)})
        entry = next(entry for entry in out["numbers"] if entry["subject"] == "Wage assumptions")
        self.assertEqual((entry["request"], entry["requests"]), (MOVED, [MOVED]))
        self.assertIn(MOVED, [item["request"] for item in out["needs_attention"]])

    def test_by_person_numbers_needs_attention_before_the_people(self):
        out, html = self.page("--by-person")
        self.assertEqual([(entry["number"], entry["request"]) for entry in out["numbers"]],
                         [(1, None), (2, EXPECTED[2]), (3, EXPECTED[3]), (4, EXPECTED[4]), (5, EXPECTED[6]),
                          (6, EXPECTED[5])])
        rest, _ = without_week(html)
        self.assertEqual([number for number, _ in lines_with_numbers(rest)], [1, 2, 3, 4, 2, 5, 6, 4, 3, 4])

    def test_the_last_7_days_only_show_numbers_given_below_them_in_every_view(self):
        self.correct_wage_assumptions()
        for view in ((), ("--project", "kowhai-budget"), ("--by-person",)):
            with self.subTest(view=view):
                out, html = self.page(*view)
                rest, week = without_week(html)
                self.assertIn('<p class="group">Due date changed</p>', week)
                below = {}
                for number, requests in lines_with_numbers(rest):
                    below.setdefault(number, requests)
                self.assertEqual(sorted(below), list(range(1, len(below) + 1)))
                firsts = list(dict.fromkeys(number for number, _ in lines_with_numbers(rest)))
                self.assertEqual(firsts, sorted(firsts))
                shown = lines_with_numbers(week)
                self.assertTrue(shown)
                for number, requests in shown:
                    self.assertEqual(below.get(number), requests)
                self.assertEqual([entry["number"] for entry in out["numbers"]], sorted(below))

    def test_a_summary_without_a_page_gives_the_same_numbers(self):
        unsaved, code = run(po, "--pace", str(self.pace), "--as-at", AS_AT)
        self.assertEqual((unsaved["status"], code, unsaved["page"]), ("made", 0, None))
        saved, _ = self.page()
        self.assertEqual(unsaved["numbers"], saved["numbers"])
        self.assertEqual(len(unsaved["numbers"]), 6)

    def test_an_item_with_three_accounts_keeps_every_id(self):
        third = "20261025T030000Z--kowhai--num014"
        write_record(self.pace, third, subject="Venue", owed_by=OWNER, state="open", due="2026-11-27",
                     corrects="20261024T010000Z--kowhai--num006")
        out, html = self.page()
        self.assertIn(f'<li class="pair" data-no="1" data-requests="{" ".join(TWO_WAYS + [third])}">', html)
        self.assertEqual((out["numbers"][0]["requests"], out["numbers"][0]["request"]), (TWO_WAYS + [third], None))
        self.assertEqual([entry["number"] for entry in out["recorded_two_ways"][0]], [1, 1, 1])

    def test_the_accounts_of_an_item_recorded_two_ways_are_lettered(self):
        # Numbered accounts, 1. and 2., sat beside item 1 and item 2, so "2 is done" could mean either.
        _, html = self.page()
        self.assertIn('<ol class="accounts" type="a">', html)
        self.assertNotIn('<ol class="accounts">', html)
        template = read(ADD_IN / "overview-template.html")
        self.assertEqual(template.count('<ol class="accounts" type="a">'), 3)
        self.assertNotIn('<ol class="accounts">', template)
        self.assertIn("Its accounts are lettered a, b and so on, never numbered, so no number on the page means two things.",
                      " ".join(template.split("-->", 1)[0].split()))
        self.assertIn("The accounts of an item recorded two ways are lettered a, b and so on, so no number on the page means "
                      "two things.", read(ADD_IN / "ADD-IN.md"))

    def test_a_template_from_before_this_design_gets_the_shipped_styles_and_the_column(self):
        copy = self.pace / "3 My add-ins/Project overview - old design"
        shutil.copytree(ADD_IN, copy)
        template = copy / "overview-template.html"
        text = read(template)
        template.write_text(re.sub(r"<style>.*?</style>", "<style>\nbody { margin: 0; }\n</style>", text, flags=re.S),
                            encoding="utf-8")
        out, html = self.page("--template", str(template))
        self.assertIn("the shipped template's styles were used", out["message"])
        self.assertIn('<summary><span class="no">2.</span> <span class="tag late">2 days late</span> <span class="subj">Board pack',
                      html)

    def test_the_number_starts_the_subject_in_every_view_of_an_older_template(self):
        copy = self.pace / "3 My add-ins/Project overview - mine"
        shutil.copytree(ADD_IN, copy)
        template = copy / "overview-template.html"
        template.write_text(old_style(read(template)), encoding="utf-8")
        for view in (("--by-person",), ("--project", "kowhai-budget")):
            with self.subTest(view=view):
                out, html = self.page("--template", str(template), *view)
                self.assertNotIn('<summary><span class="no">', html)
                inline = re.findall(r'<li class="item" data-no="(\d+)" data-request="[^"]+"><details class="row">\n<summary>'
                                    r'<span class="tag[^"]*">[^<]*</span> <span class="subj"><span class="no">(\d+)\.</span> ', html)
                self.assertTrue(inline)
                self.assertTrue(all(number == shown for number, shown in inline))
                self.assertEqual(len(inline), len([line for line in lines_with_numbers(html) if len(line[1]) == 1]))


class HelpTests(unittest.TestCase):
    def test_the_add_in_says_how_a_number_is_used(self):
        text = read(ADD_IN / "ADD-IN.md")
        for phrase in ("Also when the owner names items by their numbers on an overview page, such as \"3 is done\".",
                       "**Numbers:** each open item, and each item recorded two ways, has a number from 1",
                       "An item keeps its one number wherever else it appears on the page",
                       "If only the page's text can be read, find the item by its subject and project among the open "
                       "actions, and ask if more than one matches.",
                       "Never take a number from memory or from another page or list.",
                       "Show each one back with its subject and the change, such as \"3. Board pack draft: done\"",
                       "On the owner's yes in their own words, save each change as a correction of the item's current "
                       "account", "If an item has changed since the page was made, say how it stands now before saving",
                       "each with its number,",
                       "A change the owner gives by number is saved only on their yes in their own words"):
            self.assertIn(phrase, text)
        self.assertIn("These numbers belong to this list; an overview page has its own.",
                      read(PACE_FOLDER / "Product/Pace add-ins/Weekly review/ADD-IN.md"))
        hosts = read(PACE_FOLDER / "Product/Help/hosts-and-views.md")
        self.assertIn("The tool's result lists them under `numbers`, each with its `number`, `subject` and `project`, "
                      "`request`, the request id of its current account, and `requests`, the ids of all its current "
                      "accounts; an item recorded two ways has each account's id there, and its `request` is null.", hosts)
        self.assertIn("Numbers belong to one page; a new page numbers afresh.", hosts)

    def test_the_template_says_how_to_number_by_hand(self):
        text = read(ADD_IN / "overview-template.html")
        note = text[:text.index("-->")]
        for phrase in ("Number each open item, and each item recorded two ways, from 1 in the",
                       "done and cancelled", "<span class=\"no\">3.</span>", "data-request with the request id of the "
                       "item's current account"):
            self.assertIn(phrase, note)
        body = text[text.index("<body>"):]
        self.assertGreater(body.count('data-no="{{its number}}"'), 10)
        self.assertIn('<summary><span class="no"></span> <span class="tag">{{Decided, Changed, Done, Cancelled or Note}}</span>',
                      body)


if __name__ == "__main__":
    unittest.main()
