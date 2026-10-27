"""The overview tool, against invented Pace folders made fresh for each test.

It reads records and projects with the record tool's own readers, follows
corrections and withdrawals, counts and orders open work from its dates, fills
in the add-in's template, and saves only new files in 2 Views/.
"""

from pathlib import Path
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import shutil
import sys
import datetime as dt
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True

from test_overview_page import FORBIDDEN, Page

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
TOOL = PACE_FOLDER / "Product/Tools/pace_overview.py"
_spec = importlib.util.spec_from_file_location("pace_overview_tool", TOOL)
po = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(po)

AS_AT = "2026-11-02T09:00:00+13:00"  # Monday 2 November 2026 in Auckland; still 1 November in UTC
OWNER = "Rangi Parata"


class Folder:
    """An invented Pace folder: the shipped template folder plus projects and records written here."""

    def __init__(self, base: Path):
        self.root = base / "PACE"
        shutil.copytree(PACE_FOLDER, self.root, ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "Pace.md").write_text((self.root / "Pace.md").read_text(encoding="utf-8").replace(
            "<!-- Your lines go below this one. Pace updates never change them. -->\n## Help",
            "<!-- Your lines go below this one. Pace updates never change them. -->\nTime zone: Pacific/Auckland\n\n## Help"),
            encoding="utf-8")
        self.count = 0

    def project(self, pid, name, parent="none", purpose="Invented work."):
        self.folders = getattr(self, "folders", {})
        folder = (self.folders[parent] if parent != "none" else self.root / "1 Projects") / name
        (folder / "Documents").mkdir(parents=True, exist_ok=True)
        (folder / "Pace project.md").write_text(
            f"---\nformat: project-1\nid: {pid}\nparent: {parent}\ncreated: 2026-10-20T09:00:00+13:00\nby: Test\n---\n\n{purpose}\n",
            encoding="utf-8")
        self.names = getattr(self, "names", {})
        self.names[pid] = name
        self.folders[pid] = folder
        return pid

    def name_of(self, pid):
        return self.names[pid]

    def record(self, project, kind, subject, body, created="2026-10-25T09:00:00+13:00", **fields):
        self.count += 1
        stamp = f"20261025T{self.count:06d}Z"
        request = f"{stamp}--{project}--t{self.count:05d}"
        lines = ["---", "format: record-1", f"request: {request}", f"created: {created}", f"project: {project}",
                 f"kind: {kind}", f"subject: {subject}", "from: agent", "by: Test"]
        for key, value in fields.items():
            lines.append(f"{key.replace('_', '-')}: {value}")
        (self.root / "Record" / f"{request}.md").write_text("\n".join(lines + ["---", "", body, ""]), encoding="utf-8")
        return request

    def action(self, project, subject, body="Invented work.", **fields):
        fields.setdefault("state", "open")
        return self.record(project, "action", subject, body, **fields)

    def run(self, *argv, owner=True, as_at=AS_AT):
        args = ["--pace", str(self.root)] + (["--as-at", as_at] if as_at else []) + (["--owner", OWNER] if owner else [])
        return po.run(po.build_parser().parse_args(args + list(argv)))

    def next_request(self, project, ahead=1):
        """The request id the record written `ahead` from now will get."""
        number = self.count + ahead
        return f"20261025T{number:06d}Z--{project}--t{number:05d}"

    def no_time_zone(self):
        pace_md = self.root / "Pace.md"
        pace_md.write_text(pace_md.read_text(encoding="utf-8").replace("Time zone: Pacific/Auckland\n\n", ""), encoding="utf-8")


class OverviewCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-overview-tool-")
        self.f = Folder(Path(self._temp.name))
        self.client = self.f.project("kowhai", "Kowhai Books")
        self.budget = self.f.project("kowhai-budget", "Budget 2027", parent="kowhai", purpose="Invented budget model.")
        self.site = self.f.project("kowhai-site", "Website", parent="kowhai")
        self.solo = self.f.project("pohutu", "Pohutu Trust")

    def tearDown(self):
        self._temp.cleanup()

    def page(self, out):
        return (self.f.root / out["page"]).read_text(encoding="utf-8")

    def row(self, text, pid, own=False):
        """The line of a project's row: its name, facts, what is next, open count, next due date and last activity."""
        ident = f"p-{pid}--own" if own else f"p-{pid}"
        return re.search(rf'<details class="node[^"]*" id="{ident}"(?: open)?>\n<summary>(.*?)</summary>', text, re.S).group(1)

    def order(self, text, pids):
        """Where each project's row starts on the page, to compare their order."""
        return [text.index(f'id="p-{pid}"') for pid in pids]


class CountingTests(OverviewCase):
    def test_counts_come_from_the_dates_and_who_owes_the_work(self):
        f = self.f
        f.action(self.budget, "Late one", due="2026-10-28", owed_by=OWNER)
        f.action(self.budget, "Today one", due="2026-11-02", owed_by="Ana Ruiz")
        f.action(self.site, "Soon one", due="2026-11-09", owed_by="owner")
        f.action(self.site, "Later one", due="2026-11-10", owed_by=OWNER)
        f.action(self.solo, "Undated one")
        out, code = f.run()
        self.assertEqual((out["status"], code), ("made", 0), out)
        self.assertEqual(out["counts"], {"overdue": 1, "due_today": 1, "due_next_7_days": 1, "waiting_on_you": 3,
                                         "waiting_on_others": 1, "no_person_named": 1, "no_due_date": 1, "open": 5,
                                         "recorded_two_ways": 0})
        self.assertEqual([item["subject"] for item in out["needs_attention"]], ["Late one", "Today one", "Soon one"])
        self.assertEqual([item["when"] for item in out["needs_attention"]], ["5 days late", "today", "in 7 days"])
        self.assertEqual(out["time_zone"], "Pacific/Auckland")
        self.assertEqual(out["as_at"], "Monday 2 November 2026, 9:00 am NZDT")

    def test_the_owners_name_is_matched_without_case_and_owner_always_counts(self):
        f = self.f
        f.action(self.budget, "Mine by name", owed_by="rangi parata")
        f.action(self.budget, "Mine by word", owed_by="Owner")
        f.action(self.budget, "Someone else's", owed_by="Sam Lee")
        out, _ = f.run()
        self.assertEqual((out["counts"]["waiting_on_you"], out["counts"]["waiting_on_others"]), (2, 1))
        out, _ = f.run(owner=False)  # without --owner only the word owner is the owner's
        self.assertEqual((out["counts"]["waiting_on_you"], out["counts"]["waiting_on_others"]), (1, 2))

    def test_only_the_current_account_of_each_item_counts(self):
        f = self.f
        first = f.action(self.budget, "Corrected to done", due="2026-10-20")
        f.action(self.budget, "Corrected to done", corrects=first, state="done", body="Done now.")
        moved = f.action(self.budget, "Moved date", due="2026-10-20")
        f.action(self.budget, "Moved date", corrects=moved, due="2026-11-20", body="New date agreed.")
        dropped = f.action(self.budget, "Withdrawn")
        f.record(self.budget, "withdrawal", "Withdrawn", "No longer stands.", corrects=dropped)
        out, _ = f.run()
        self.assertEqual(out["counts"]["open"], 1)
        self.assertEqual(out["counts"]["overdue"], 0)
        page = self.page(f.run("--save")[0])
        self.assertIn("New date agreed.", page)
        self.assertNotIn("Invented work.", page)  # the earlier accounts of all three items
        self.assertNotIn("Done now.", page)

    def test_two_current_accounts_are_shown_together_and_counted_nowhere_else(self):
        f = self.f
        first = f.action(self.budget, "Board pack", due="2026-11-10", owed_by="Ana Ruiz")
        one = f.action(self.budget, "Board pack", corrects=first, due="2026-11-12", owed_by="Ana Ruiz", body="Ana says the 12th.")
        two = f.action(self.budget, "Board pack", corrects=first, due="2026-11-16", owed_by="Ana Ruiz", body="Sam says the 16th.")
        out, _ = f.run("--save")
        self.assertEqual(out["counts"]["recorded_two_ways"], 1)
        self.assertEqual(out["counts"]["open"], 0)
        self.assertEqual([item["request"] for item in out["recorded_two_ways"][0]], [one, two])
        page = self.page(out)
        start = page.index('<section class="part two-ways">')
        both = page[start:page.index("</section>", start)]
        self.assertIn("Ana says the 12th.", both)
        self.assertIn("Sam says the 16th.", both)
        self.assertEqual(page.count("Ana says the 12th."), 1)
        # Settled once the owner says which stands: the other is withdrawn.
        f.record(self.budget, "withdrawal", "Board pack", "Sam's date does not stand.", corrects=two)
        out, _ = f.run()
        self.assertEqual((out["counts"]["recorded_two_ways"], out["counts"]["open"]), (0, 1))

    def test_today_is_the_owners_day_not_utc(self):
        self.f.action(self.budget, "Due Monday", due="2026-11-02")
        out, _ = self.f.run()
        self.assertEqual(out["counts"]["due_today"], 1)  # in UTC it is still Sunday 1 November

    def test_a_record_dated_after_today_here_shows_its_date_alone(self):
        today = dt.date(2026, 10, 24)
        self.assertEqual(po.day_and_age(dt.date(2026, 10, 25), today), "25 Oct 2026")
        self.assertEqual(po.day_and_age(dt.date(2026, 10, 24), today), "24 Oct 2026, today")
        self.assertEqual(po.day_and_age(dt.date(2026, 10, 21), today), "21 Oct 2026, 3 days ago")
        self.assertEqual(po.day_and_age(None, today), "Not recorded")

    def test_without_as_at_today_comes_from_the_clock_in_the_owners_zone(self):
        out, _ = self.f.run(as_at=None)
        now = dt.datetime.now(po.pr.ZoneInfo("Pacific/Auckland"))
        self.assertTrue(out["as_at"].startswith(f"{now:%A} {now.day} {now:%B %Y}"), out["as_at"])
        self.assertTrue(out["as_at"].endswith(("NZDT", "NZST")), out["as_at"])

    def test_an_action_with_no_state_is_open_work(self):
        f = self.f
        f.record(self.budget, "action", "Reminder with no state", "Call the bank.", due="2026-11-04")
        first = f.action(self.site, "Moved", due="2026-10-20")
        f.record(self.site, "action", "Moved", "Moved to the 10th.", corrects=first, due="2026-11-10")
        out, _ = f.run("--save")
        self.assertEqual((out["counts"]["open"], out["counts"]["due_next_7_days"], out["counts"]["overdue"]), (2, 1, 0))
        text = self.page(out)
        self.assertIn("Call the bank.", text)
        self.assertIn("Moved to the 10th.", text)
        self.assertEqual(text.count("state not recorded"), 3)  # twice in Needs attention and open work, once more for the move

    def test_undated_work_keeps_its_first_place_when_corrected(self):
        f = self.f
        older = f.action(self.budget, "Older item")
        f.action(self.budget, "Newer item")
        f.action(self.budget, "Older item", corrects=older, body="Older, with more detail.")
        text = self.page(f.run("--save")[0])
        work = text[text.index('id="p-kowhai-budget"'):]
        self.assertLess(work.index("Older, with more detail."), work.index('<span class="subj">Newer item</span>'))


class StoryTests(OverviewCase):
    def test_corrections_of_a_missing_record_are_one_item_and_the_page_is_partial(self):
        f = self.f
        gone = f"20261020T000000Z--{self.budget}--gone00"
        one = f.action(self.budget, "Board pack", corrects=gone, body="Ana says the 12th.")
        two = f.action(self.budget, "Board pack", corrects=gone, body="Sam says the 16th.")
        out, _ = f.run("--save")
        self.assertEqual((out["counts"]["recorded_two_ways"], out["counts"]["open"]), (1, 0))
        self.assertEqual([item["request"] for item in out["recorded_two_ways"][0]], [one, two])
        self.assertFalse(out["complete"])
        self.assertIn(f"correct {gone}, but no file for it is in Record/ here.", out["could_not_read"])
        self.assertIn(gone, self.page(out))

    def test_corrections_that_loop_are_named_and_shown_two_ways(self):
        f = self.f
        b = f.next_request(self.budget, 2)
        a = f.action(self.budget, "Looped", corrects=b, body="Account A.")
        self.assertEqual(f.action(self.budget, "Looped", corrects=a, body="Account B."), b)
        out, _ = f.run("--save")
        self.assertEqual((out["counts"]["recorded_two_ways"], out["counts"]["open"]), (1, 0))
        self.assertFalse(out["complete"])
        self.assertIn(f"loop: {a}, {b} correct each other", out["could_not_read"])
        text = self.page(out)
        self.assertIn("Account A.", text)
        self.assertIn("Account B.", text)

    def test_work_recorded_two_ways_is_in_every_view_and_its_project_is_not_idle(self):
        f = self.f
        first = f.action(self.budget, "Board pack", owed_by="Ana Ruiz")
        f.action(self.budget, "Board pack", corrects=first, owed_by="Ana Ruiz", body="Ana says the 12th.")
        f.action(self.budget, "Board pack", corrects=first, owed_by="Ana Ruiz", body="Sam says the 16th.")
        every = self.page(f.run("--save")[0])
        self.assertIn('<h2>Recorded two ways <span class="n">1</span></h2>', every)
        # Neither the project nor its parent is called idle: their work is in the two-ways section.
        self.assertIn('<p class="quiet">No open work recorded: Kowhai Books &rsaquo; Website, Pohutu Trust.</p>', every)
        for view in (["--by-person"], ["--project", self.budget]):
            with self.subTest(view=view):
                text = self.page(f.run("--save", *view)[0])
                self.assertIn('<h2>Recorded two ways <span class="n">1</span></h2>', text)
                self.assertIn("Ana says the 12th.", text)
                self.assertIn("Sam says the 16th.", text)


    def test_a_project_whose_only_dispute_is_a_decision_is_still_listed_as_having_no_open_work(self):
        f = self.f
        first = f.record(self.solo, "decision", "Trust deed", "Use the 2025 deed.")
        f.record(self.solo, "decision", "Trust deed", "Use the 2024 deed.", corrects=first)
        f.record(self.solo, "decision", "Trust deed", "Use the 2026 deed.", corrects=first)
        f.action(self.budget, "Budget task")
        out, _ = f.run("--save")
        self.assertEqual(out["counts"]["recorded_two_ways"], 1)
        text = self.page(out)
        self.assertIn("Use the 2026 deed.", text)
        self.assertIn('<p class="quiet">No open work recorded: Kowhai Books &rsaquo; Website, Pohutu Trust.</p>', text)


class ProjectFactTests(OverviewCase):
    def test_owner_target_and_status_come_from_the_latest_change_that_sets_each(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Sam leads.", owner="Sam Lee", target="2026-11-20", status="Started")
        f.record(self.budget, "change", "Budget 2027", "Ana leads now.", owner="Ana Ruiz", status="Waiting on the wage sign-off",
                 created="2026-10-28T09:00:00+13:00")
        f.action(self.budget, "Budget task")
        row = self.row(self.page(f.run("--save")[0]), self.budget)
        self.assertIn('<span class="status">Waiting on the wage sign-off &middot; 28 Oct 2026</span>', row)
        self.assertIn('<span class="fact">Owner Ana Ruiz &middot; Target <span>20 Nov 2026, in 18 days</span></span>', row)
        self.assertNotIn("Started", row)
        # none clears one and the others stand.
        f.record(self.budget, "change", "Budget 2027", "No target for now.", target="none")
        row = self.row(self.page(f.run("--save")[0]), self.budget)
        self.assertIn('<span class="fact">Owner Ana Ruiz</span>', row)
        self.assertNotIn("Target", row)

    def test_a_change_recorded_two_ways_shows_as_that_until_the_owner_says_which_stands(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Kiri led it first.", owner="Kiri Hale", status="Started")
        first = f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz")
        f.record(self.budget, "change", "Budget 2027", "Sam leads.", owner="Sam Lee", corrects=first)
        f.record(self.budget, "change", "Budget 2027", "Rangi leads.", owner=OWNER, corrects=first)
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        row = self.row(text, self.budget)
        # The newest word on the owner is disputed, so the older owner is not shown as if it stood; the status stands.
        self.assertIn('<span class="fact">Owner Recorded two ways</span>', row)
        self.assertNotIn("Kiri Hale", row)
        self.assertIn("Started", row)
        self.assertIn("<h2>Recorded two ways", text)

    def test_accounts_that_agree_on_a_value_set_it_and_a_note_in_the_dispute_counts(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Kiri led it.", owner="Kiri Hale", status="Started")
        first = f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz")
        f.record(self.budget, "change", "Budget 2027", "Ana leads, from Sam.", owner="Ana Ruiz", corrects=first)
        f.record(self.budget, "change", "Budget 2027", "Ana leads, from Rangi.", owner="Ana Ruiz", status="Drafting",
                 corrects=first)
        f.action(self.budget, "Budget task")
        row = self.row(self.page(f.run("--save")[0]), self.budget)
        self.assertIn('<span class="fact">Owner Ana Ruiz</span>', row)  # both accounts say Ana
        self.assertIn('<span class="status">Recorded two ways</span>', row)  # one account gives a status, the other none
        # A note standing against a change still makes what the change sets disputed, not the older value.
        later = f.record(self.site, "change", "Website", "Mere leads.", owner="Mere Tane")
        f.record(self.site, "change", "Website", "Tom leads.", owner="Tom Ihaka", corrects=later)
        f.record(self.site, "note", "Website", "It is not decided.", corrects=later)
        f.action(self.site, "Site task")
        row = self.row(self.page(f.run("--save")[0]), self.site)
        self.assertIn('<span class="fact">Owner Recorded two ways</span>', row)

    def test_the_owner_leading_shows_as_you_and_a_passed_target_is_late(self):
        f = self.f
        f.record(self.site, "change", "Website", "Mine, and it was due last week.", owner="owner", target="2026-10-28")
        f.action(self.site, "Site task")
        row = self.row(self.page(f.run("--save")[0]), self.site)
        self.assertIn('<span class="fact">Owner You &middot; Target <span class="late">28 Oct 2026, 5 days late</span></span>', row)

    def test_owner_and_target_show_only_when_recorded(self):
        f = self.f
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        self.assertNotIn('class="fact"', text)
        f.record(self.site, "change", "Website", "Aiming for December.", target="2026-12-01")
        row = self.row(self.page(f.run("--save")[0]), self.site)
        self.assertIn('<span class="fact">Target <span>1 Dec 2026, in 29 days</span></span>', row)
        self.assertNotIn("Owner", row)

    def test_a_project_with_only_a_status_is_in_the_table_not_idle(self):
        f = self.f
        f.record(self.solo, "change", "Trust", "Paused.", status="On hold until January")
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        row = self.row(text, self.solo)
        self.assertIn("On hold until January", row)
        self.assertIn('<span class="num">0</span>', row)
        self.assertIn('<span class="next">No open work recorded</span>', row)
        self.assertNotIn("Pohutu Trust", text[text.index('<p class="quiet">No open work recorded'):].split("</p>")[0])

    def test_correcting_an_older_change_does_not_make_it_the_newest(self):
        f = self.f
        older = f.record(self.budget, "change", "Budget 2027", "Sam leads.", owner="Sam Lee", status="Started",
                         created="2026-10-19T09:00:00+13:00")
        f.record(self.budget, "change", "Budget 2027", "Ana leads now.", owner="Ana Ruiz", status="Waiting",
                 created="2026-10-24T09:00:00+13:00")
        f.record(self.budget, "change", "Budget 2027 kick-off", "Sam leads.", owner="Sam Lee", status="Started", corrects=older,
                 created="2026-10-28T09:00:00+13:00")  # only the subject is fixed
        f.action(self.budget, "Budget task")
        row = self.row(self.page(f.run("--save")[0]), self.budget)
        self.assertIn('<span class="fact">Owner Ana Ruiz</span>', row)
        self.assertIn('<span class="status">Waiting &middot; 24 Oct 2026</span>', row)

    def test_odd_change_records_never_stop_the_page(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Due at the end of November.", target="27 November")  # not a date
        f.action(self.budget, "Budget task")
        for view in ([], ["--project", self.budget], ["--by-person"]):
            with self.subTest(view=view):
                out, code = f.run("--save", *view)
                self.assertEqual((out["status"], code), ("saved", 0), out)
                self.assertNotIn("Target", self.page(out).split("<h2>Needs attention")[1].split('<section class="about">')[0])
                # The target was not used, and every view says why, so it does not vanish without trace.
                self.assertFalse(out["complete"])
                self.assertIn("gives the target '27 November', which is not a real date, so it was not used.", out["could_not_read"])

    def test_the_one_project_view_gives_its_owner_target_and_status(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz", target="2026-11-27", status="Drafting")
        text = self.page(f.run("--save", "--project", self.budget)[0])
        for line in ("<span>Owner <strong>Ana Ruiz</strong></span>", "<span>Target <strong>27 Nov 2026, in 25 days</strong></span>",
                     "<span>Status <strong>Drafting &middot; 25 Oct 2026</strong></span>",
                     "<span>Part of <strong>Kowhai Books</strong></span>"):
            self.assertIn(line, text)
        text = self.page(f.run("--save", "--project", self.site)[0])
        self.assertNotIn("Owner <strong>", text)  # only what is recorded is shown


class OddFolderTests(OverviewCase):
    def test_a_record_with_no_project_line_is_shown_with_work_that_names_no_project(self):
        lines = ["---", "format: record-1", "request: 20261025T120000Z--kowhai-budget--nopro1", "created: 2026-10-26T01:00:00+13:00",
                 "kind: action", "subject: Lost", "from: agent", "by: Hand", "state: open", "---", "", "No project line.", ""]
        (self.f.root / "Record/20261025T120000Z--kowhai-budget--nopro1.md").write_text("\n".join(lines), encoding="utf-8")
        out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["complete"]), ("saved", 0, False), out)
        self.assertIn("No project line.", self.page(out))

    def test_a_project_whose_parents_loop_is_still_shown(self):
        loop = self.f.root / "1 Projects/Loop"
        loop.mkdir()
        (loop / "Pace project.md").write_text(
            "---\nformat: project-1\nid: loop\nparent: loop\ncreated: 2026-10-20T09:00:00+13:00\nby: Hand\n---\n", encoding="utf-8")
        self.f.action("loop", "Looped work")
        out, _ = self.f.run("--save")
        text = self.page(out)
        self.assertIn('<span class="pname">Loop</span>', self.row(text, "loop"))
        self.assertIn("Looped work", text)
        self.assertFalse(out["complete"])  # the parent that does not match is named

    def test_the_order_is_the_same_on_every_run(self):
        f = self.f
        for client in ("Gamma", "Alpha", "Delta", "Beta"):
            pid = f.project(client.lower(), client)
            f.action(f.project(f"{client.lower()}-budget", "Budget 2027", parent=pid), "Undated budget work")
        orders = set()
        for seed in ("1", "2", "3"):  # a different order of sets in each run
            run = subprocess.run([sys.executable, "-B", str(TOOL), "--pace", str(f.root), "--as-at", AS_AT, "--save"],
                                 capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": seed})
            self.assertEqual(run.returncode, 0, run.stderr)
            text = (f.root / json.loads(run.stdout)["page"]).read_text(encoding="utf-8")
            orders.add(tuple(sorted(("alpha", "beta", "delta", "gamma"), key=lambda pid: text.index(f'id="p-{pid}"'))))
        self.assertEqual(orders, {("alpha", "beta", "delta", "gamma")})

    def test_a_template_styled_for_an_earlier_page_design_gets_the_shipped_styles(self):
        f = self.f
        f.action(self.budget, "Budget task")
        shipped = (f.root / "Product/Pace add-ins/Project overview/overview-template.html").read_text(encoding="utf-8")
        older = Path(self._temp.name) / "older-template.html"
        older.write_text(shipped.replace(".node", ".project").replace(".row", ".item-row"), encoding="utf-8")
        out, _ = f.run("--save", "--template", str(older))
        text = self.page(out)
        self.assertIn(".node > summary", text)  # the page is styled, not left bare
        self.assertIn("made for an earlier page design, so the shipped template's styles were used", out["message"])
        self.assertNotIn("earlier page design", f.run("--save")[0]["message"])


class DepthTests(OverviewCase):
    def setUp(self):
        super().setUp()
        self.board = self.f.project("kowhai-board", "Board pack", parent=self.budget)
        self.slides = self.f.project("kowhai-slides", "Slides", parent=self.board)

    def test_a_project_three_levels_down_is_named_after_all_above_it_and_ordered_in_its_tree(self):
        f = self.f
        f.action(self.slides, "Slides late", due="2026-10-30")
        f.action(self.site, "Site soon", due="2026-11-04")
        f.action(self.solo, "Trust undated")
        text = self.page(f.run("--save")[0])
        order = self.order(text, (self.client, self.budget, self.board, self.slides, self.site, self.solo))
        self.assertEqual(order, sorted(order))
        # The projects above Slides hold no work of their own, but none is idle: Slides is inside them.
        self.assertNotIn("No open work recorded", text)
        for parent in (self.client, self.budget, self.board):
            self.assertIn(f'<details class="node parent" id="p-{parent}" open>', text)
            self.assertNotIn(f'id="p-{parent}--own"', text)
        self.assertIn('<span class="next">Next: Slides late &middot; Budget 2027 &rsaquo; Board pack &rsaquo; Slides</span>',
                      self.row(text, self.client))
        self.assertIn('<a class="jump" href="#p-kowhai-slides">Go to Kowhai Books &rsaquo; Budget 2027 &rsaquo; Board pack &rsaquo; Slides</a>',
                      text[text.index("<h2>Needs attention"):])

    def test_projects_side_by_side_run_by_the_most_pressing_work_anywhere_inside_them(self):
        f = self.f
        f.action(self.site, "Site soon", due="2026-11-04")
        f.action(self.budget, "Budget undated")
        f.action(self.slides, "Slides late", due="2026-10-30")
        text = self.page(f.run("--save")[0])
        # Budget 2027's own work is undated, but Slides inside it is late, so its branch comes before Website.
        order = self.order(text, (self.budget, self.slides, self.site))
        self.assertEqual(order, sorted(order))
        self.assertLess(text.index(f'id="p-{self.budget}--own"'), text.index(f'id="p-{self.board}"'))  # its own work first

    def test_one_project_takes_in_every_project_inside_it_at_any_depth(self):
        f = self.f
        f.action(self.slides, "Slides task", due="2026-11-03")
        f.action(self.site, "Site task")
        out, _ = f.run("--save", "--project", self.client)
        self.assertEqual(out["counts"]["open"], 2)
        text = self.page(out)
        order = self.order(text, (self.budget, self.board, self.slides, self.site))
        self.assertEqual(order, sorted(order))
        self.assertIn('<a class="jump" href="#p-kowhai-slides">Go to Budget 2027 &rsaquo; Board pack &rsaquo; Slides</a>', text)
        deepest = self.page(f.run("--save", "--project", self.slides)[0])
        self.assertIn("<span>Part of <strong>Kowhai Books &rsaquo; Budget 2027 &rsaquo; Board pack</strong></span>", deepest)
        self.assertIn("<h1>Slides</h1>", deepest)


class PageTests(OverviewCase):
    def test_the_saved_page_is_well_formed_and_read_back(self):
        self.f.action(self.budget, "Late one", due="2026-10-28", owed_by=OWNER)
        out, code = self.f.run("--save", "--asked", "Where are we?")
        self.assertEqual((out["status"], code, out["page"]), ("saved", 0, "2 Views/2026-11-02-project-overview.html"), out)
        self.assertIn("Saved and read back: 2 Views/2026-11-02-project-overview.html.", out["message"])
        text = self.page(out)
        page = Page(text)
        self.assertEqual(page.problems, [])
        self.assertIsNone(FORBIDDEN.search(text))
        self.assertIn("<dd>Where are we?</dd>", text)
        self.assertIn('<p class="asat">As at Monday 2 November 2026, 9:00 am NZDT</p>', text)
        self.assertIn("<title>Project overview, 2 Nov 2026 - Pace by SBR</title>", text)
        self.assertIn("<h1>All projects</h1>", text)
        self.assertIn('<p class="stat hot"><strong>1</strong> overdue</p>', text)
        self.assertIn('<p class="stat zero"><strong>0</strong> due today</p>', text)
        self.assertIn('<span class="tag late">5 days late</span>', text)
        self.assertNotIn('class="partial"', text)
        self.assertNotRegex(text, r"\bRecord \d{8}T\d{6}Z")  # record references stay in the tool's result, not on the page
        self.assertEqual(out["needs_attention"][0]["request"][:9], "20261025T")

    def test_a_page_is_never_replaced(self):
        pages = [self.f.run("--save")[0] for _ in range(3)]
        self.assertEqual([out["page"] for out in pages], ["2 Views/2026-11-02-project-overview.html",
                                                          "2 Views/2026-11-02-project-overview-2.html",
                                                          "2 Views/2026-11-02-project-overview-3.html"])
        self.assertEqual(self.page(pages[0]), self.page(pages[2]))

    def test_projects_are_grouped_under_their_parent_most_pressing_first(self):
        f = self.f
        f.action(self.site, "Site soon", due="2026-11-04")
        f.action(self.budget, "Budget late", due="2026-10-30")
        f.action(self.solo, "Trust undated")
        f.action(self.client, "Client undated")
        text = self.page(f.run("--save")[0])
        # The Kowhai group is the most pressing; in it the parent's own work comes first, then its projects.
        order = [text.index(f'id="{ident}"') for ident in ("p-kowhai", "p-kowhai--own", "p-kowhai-budget", "p-kowhai-site", "p-pohutu")]
        self.assertEqual(order, sorted(order))
        # Next due is the earliest date of the project's open work, overdue or not, and a parent's takes in its projects.
        self.assertIn('<span class="num">3</span> <span class="due"><span class="tag late">3 days late</span></span>', self.row(text, self.client))
        self.assertIn('<span class="due"><span class="tag late">3 days late</span></span>', self.row(text, self.budget))
        self.assertIn('<span class="due"><span class="tag soon">In 2 days</span></span>', self.row(text, self.site))
        self.assertIn('<span class="num">1</span> <span class="due"><span class="tag empty">No date</span></span>', self.row(text, self.solo))
        self.assertIn('<span class="pname">Kowhai Books <span class="itself">itself</span></span>', self.row(text, self.client, own=True))
        self.assertNotIn("No open work recorded", text)

    def test_a_parent_whose_projects_have_open_work_is_not_listed_as_having_none(self):
        f = self.f
        f.project("kowhai-plans", "Plans", parent="kowhai")
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        self.assertIn('<p class="quiet">No open work recorded: Kowhai Books &rsaquo; Plans, Kowhai Books &rsaquo; Website, '
                      'Pohutu Trust.</p>', text)
        self.assertIn('<details class="node parent" id="p-kowhai" open>', text)
        self.assertNotIn('id="p-kowhai--own"', text)  # it has no open work of its own
        self.assertIn('id="p-kowhai-budget"', text)

    def test_record_text_cannot_add_markup(self):
        hostile = '<script>alert(1)</script> & "quotes" \'single\' </li></ul><h1>x</h1>'
        self.f.action(self.budget, "<b>Subject</b>", body=hostile, owed_by="<Sam & Co>", due="2026-11-03")
        text = self.page(self.f.run("--save")[0])
        page = Page(text)
        self.assertEqual(page.problems, [])
        self.assertIsNone(FORBIDDEN.search(text))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quotes&quot; &#39;single&#39;", text)
        self.assertIn("Owed by &lt;Sam &amp; Co&gt;", text)
        self.assertIn('<span class="by"> &middot; &lt;Sam &amp; Co&gt;</span>', text)
        self.assertNotIn("script", {tag for tag, _ in page.tags})

    def test_one_project_takes_in_the_projects_inside_it(self):
        f = self.f
        f.action(self.budget, "Budget task", due="2026-11-03")
        f.action(self.site, "Site task")
        f.action(self.solo, "Not this one")
        f.record(self.budget, "decision", "Chosen layout", "Use the two-page layout.", created="2026-10-30T09:00:00+13:00")
        f.record(self.budget, "decision", "Old decision", "Too old to show.", created="2026-09-01T09:00:00+13:00")
        f.record(self.budget, "change", "New owner", "Ana now owns the model.", created="2026-10-31T09:00:00+13:00")
        out, code = f.run("--project", "kowhai", "--save")
        self.assertEqual((out["status"], out["page"], out["view"]), ("saved", "2 Views/2026-11-02-project-overview-kowhai.html", "one project"))
        self.assertEqual(out["counts"]["open"], 2)
        text = self.page(out)
        self.assertEqual(Page(text).problems, [])
        self.assertIn("<h1>Kowhai Books</h1>", text)
        self.assertIn("<title>Kowhai Books, 2 Nov 2026 - Pace by SBR</title>", text)
        self.assertIn("Use the two-page layout.", text)
        self.assertIn("Ana now owns the model.", text)
        self.assertIn('<span class="tag">Decided</span> <span class="subj">Chosen layout</span>', text)
        self.assertNotIn("Too old to show.", text)
        self.assertNotIn("Not this one", text)
        self.assertIn("<!-- start: one project view -->", text)
        # A project inside it has open work, so the view has a row for each of them.
        order = self.order(text, (self.budget, self.site))
        self.assertEqual(order, sorted(order))
        self.assertIn('<span class="due"><span class="tag soon">Tomorrow</span></span>', self.row(text, self.budget))
        self.assertNotIn("Pohutu Trust", text)
        # A project with no projects inside it lists its open work.
        alone = self.page(f.run("--project", "kowhai-budget", "--save")[0])
        self.assertNotIn("<h2>Projects", alone)
        self.assertIn('<h2>Open work <span class="n">1</span></h2>', alone)

    def test_repository_references_go_to_their_own_project(self):
        f = self.f
        home = f.root / "Repos/Kowhai Books/Budget 2027/model-code/Pace repo.md"
        link = f.root / "Repos/Kowhai Books/Website/model-code/Pace repo link.md"
        for path, text in ((home, "Home project id: kowhai-budget\n"),
                           (link, "Using project id: kowhai-site\nHome project id: kowhai-budget\n"
                                  "Home reference: Repos/Kowhai Books/Budget 2027/model-code/Pace repo.md\n")):
            path.parent.mkdir(parents=True)
            path.write_text("# model-code\n\n" + text, encoding="utf-8")
        budget = self.page(f.run("--save", "--project", self.budget)[0])
        site = self.page(f.run("--save", "--project", self.site)[0])
        self.assertIn("<li>Repos/Kowhai Books/Budget 2027/model-code/Pace repo.md</li>", budget)
        self.assertNotIn("Pace repo link.md", budget)  # the link belongs to the project that uses the repository
        self.assertIn("<li>Repos/Kowhai Books/Website/model-code/Pace repo link.md</li>", site)
        self.assertNotIn("Pace repo.md</li>", site)

    def test_an_unreadable_repository_reference_makes_the_page_partial(self):
        f = self.f
        odd = f.root / "Repos/Pohutu Trust/trust-code/Pace repo.md"
        odd.parent.mkdir(parents=True)
        odd.write_bytes(b"Home project id: kowhai-budget \x96 saved in another encoding\n")
        out, _ = f.run("--save", "--project", self.budget)
        self.assertFalse(out["complete"])
        self.assertIn("Repos/Pohutu Trust/trust-code/Pace repo.md could not be read", out["could_not_read"])

    def test_a_customised_template_gives_the_page_its_look_only(self):
        f = self.f
        f.action(self.budget, "Due soon", due="2026-11-03")
        shipped = (f.root / "Product/Pace add-ins/Project overview/overview-template.html").read_text(encoding="utf-8")
        copy = f.root / "3 My add-ins/Project overview/overview-template.html"
        copy.parent.mkdir(parents=True)
        copy.write_text(shipped.replace(".lede { margin: 0.5rem 0;", ".lede { margin: 0.9rem 0;")
                        .replace("<h2>Needs attention", "<h2>Urgent"), encoding="utf-8")
        out, _ = f.run("--save", "--template", "3 My add-ins/Project overview/overview-template.html")
        text = self.page(out)
        self.assertIn(".lede { margin: 0.9rem 0;", text)
        self.assertIn("<h2>Needs attention", text)  # the sections and wording are always the add-in's own
        self.assertNotIn("Urgent", text)
        self.assertNotIn("earlier page design", out["message"])

    def test_no_text_from_records_or_folders_can_add_markup_in_any_view(self):
        f = self.f
        hostile = '<b>x</b> & "q" \'s\' </li></ul>'
        parent_name, child_name, idle_name = '<i>Evil<b> & "Co"', "<u>Kid's", "<q>Idle"  # folder names cannot hold "/"
        parent = f.project("evil", parent_name, purpose=hostile)
        child = f.project("evil-kid", child_name, parent="evil", purpose=hostile)
        f.project("idle", idle_name)
        (f.root / "1 Projects" / parent_name / "Documents" / '<b>doc & "q".txt').write_text("x", encoding="utf-8")
        f.action(parent, hostile, body=hostile, due="2026-11-03", owed_by=hostile, **{"for": hostile})
        f.action(child, "Second", body=hostile, owed_by="Sam <Lee>", **{"for": OWNER})
        (f.root / "Record/<i>odd & 'x'.md").write_text("x", encoding="utf-8")  # named on the Could not read line
        escaped = {"parent": "&lt;i&gt;Evil&lt;b&gt; &amp; &quot;Co&quot;", "child": "&lt;u&gt;Kid&#39;s",
                   "idle": "&lt;q&gt;Idle", "text": "&lt;b&gt;x&lt;/b&gt; &amp; &quot;q&quot; &#39;s&#39; &lt;/li&gt;&lt;/ul&gt;"}
        pages = {}
        for name, view in (("every", []), ("person", ["--by-person"]), ("parent", ["--project", parent]),
                           ("child", ["--project", child])):
            with self.subTest(view=name):
                text = pages[name] = self.page(f.run("--save", "--asked", hostile, *view)[0])
                page = Page(text)
                self.assertEqual(page.problems, [])
                self.assertIsNone(FORBIDDEN.search(text))
                self.assertFalse({"b", "i", "u", "q"} & {tag for tag, _ in page.tags})
                self.assertIn(escaped["text"], text)
        every = pages["every"]
        self.assertIn(f'<span class="pname">{escaped["parent"]}</span>', self.row(every, "evil"))
        self.assertIn(f'<span class="pname">{escaped["child"]}</span>', self.row(every, "evil-kid"))
        self.assertIn(f"No open work recorded: {escaped['idle']}, Kowhai Books, ", every)
        self.assertIn(f'<span class="side">{escaped["parent"]} &rsaquo; {escaped["child"]} &middot; for you</span>', pages["person"])
        self.assertIn(f"<h1>{escaped['parent']}</h1>", pages["parent"])
        self.assertIn(f'<span class="pname">{escaped["child"]}</span>', self.row(pages["parent"], "evil-kid"))
        self.assertIn(f'<p class="lead">{escaped["text"]}</p>', pages["parent"])
        self.assertIn("&lt;b&gt;doc &amp; &quot;q&quot;.txt", pages["parent"])
        self.assertIn(f"<h1>{escaped['child']}</h1>", pages["child"])
        self.assertIn(f"<span>Part of <strong>{escaped['parent']}</strong></span>", pages["child"])
        self.assertIn("&lt;i&gt;odd &amp; &#39;x&#39;.md", every)

    def test_an_unknown_project_makes_nothing(self):
        out, code = self.f.run("--project", "nope", "--save")
        self.assertEqual((out["status"], code), ("not-made", 1))
        self.assertEqual(list((self.f.root / "2 Views").glob("*.html")), [])

    def test_by_person_puts_the_owner_first(self):
        f = self.f
        f.action(self.budget, "Sam's list", owed_by="Sam Lee", **{"for": OWNER})
        f.action(self.budget, "My sign-off", owed_by=OWNER, **{"for": "Ana Ruiz"})
        f.action(self.site, "Nobody's")
        f.action(self.site, "Sam alone", owed_by="Sam Lee")
        out, _ = f.run("--by-person", "--save")
        text = self.page(out)
        self.assertEqual(Page(text).problems, [])
        rows = [text.index(f'<span class="pname">{name}</span>') for name in ("You", "Ana Ruiz", "Sam Lee", "No person named")]
        self.assertEqual(rows, sorted(rows))
        self.assertIn('<details class="node person" open>\n<summary><span class="label"><span class="pname">You</span>', text)
        self.assertIn("for Ana Ruiz", text)
        self.assertIn("for you", text)
        # Who an item is for is shown only when the record names someone.
        self.assertNotIn("for: not recorded", text.lower())
        self.assertIn('<p class="meta">Owed by Sam Lee &middot; no due date &middot; open</p>', text)
        self.assertIn('<p class="group">You are waiting for</p>', text)
        self.assertIn("Kowhai Books &rsaquo; Budget 2027 &middot; from Sam Lee", text)


class LineTests(OverviewCase):
    """Each item is one line; undated work shows how long it has waited; the last 7 days; jumps; leftover copies."""

    def test_undated_work_shows_how_long_it_has_been_open_from_14_days(self):
        f = self.f
        f.action(self.budget, "Old mine", created="2026-10-19T09:00:00+13:00")  # 14 days before 2 November
        f.action(self.site, "Old theirs", owed_by="Sam Lee", created="2026-10-12T09:00:00+13:00")
        f.action(self.budget, "Fresh", created="2026-10-20T09:00:00+13:00")  # 13 days
        dated = f.action(self.budget, "Dated", due="2026-11-20", created="2026-10-01T09:00:00+13:00")
        text = self.page(f.run("--save")[0])
        self.assertIn('<span class="tag age">Open 14 days</span> <span class="subj">Old mine</span>', text)
        self.assertIn('<span class="tag age">Waiting 21 days</span> <span class="subj">Old theirs</span>', text)
        self.assertIn('<span class="tag"></span> <span class="subj">Fresh</span>', text)
        self.assertIn('<span class="tag">20 Nov</span> <span class="subj">Dated</span>', text)  # a due date comes before age
        self.assertIn("Next: Dated", self.row(text, self.budget))
        self.assertIn("Oldest open: Old theirs &middot; Sam Lee &middot; open 21 days", self.row(text, self.site))
        # With nothing dated, a row's line is its oldest open item, with its age once that is 14 days or more.
        f.action(self.budget, "Dated", corrects=dated, state="done")
        self.assertIn("Oldest open: Old mine &middot; open 14 days", self.row(self.page(f.run("--save")[0]), self.budget))

    def test_the_last_7_days_counts_new_done_cancelled_and_changed_due_dates(self):
        f = self.f
        week = "2026-10-29T09:00:00+13:00"  # inside the 7 days to 2 November
        f.action(self.budget, "New this week", created=week)
        done = f.action(self.budget, "Done this week", created="2026-10-10T09:00:00+13:00")
        f.action(self.budget, "Done this week", corrects=done, state="done", created=week)
        dropped = f.action(self.site, "Cancelled this week", created="2026-10-10T09:00:00+13:00")
        f.action(self.site, "Cancelled this week", corrects=dropped, state="cancelled", created=week)
        moved = f.action(self.site, "Moved this week", due="2026-11-01", created="2026-10-10T09:00:00+13:00")
        f.action(self.site, "Moved this week", corrects=moved, due="2026-11-12", created=week, body="Pushed out.")
        f.action(self.site, "Old work", created="2026-10-10T09:00:00+13:00")
        out, _ = f.run("--save")
        self.assertEqual(out["last_7_days"], {"new": 1, "done": 1, "cancelled": 1, "due_date_changed": 1})
        text = self.page(out)
        week_part = text[text.index('<details class="week">'):text.index("<h2>Needs attention")]
        self.assertIn("<summary>Last 7 days: <strong>1</strong> new &middot; <strong>1</strong> done &middot; "
                      "<strong>1</strong> cancelled &middot; <strong>1</strong> due date changed</summary>", week_part)
        self.assertIn('<span class="tag">Done</span> <span class="subj">Done this week</span>', week_part)
        self.assertIn('<span class="tag">Cancelled</span> <span class="subj">Cancelled this week</span>', week_part)
        self.assertIn("Kowhai Books &rsaquo; Website &middot; was 1 Nov", week_part)
        self.assertNotIn("Old work", week_part)
        # One project's page counts only its own last 7 days; with nothing, it says so in one line.
        self.assertEqual(f.run("--project", self.solo)[0]["last_7_days"], {"new": 0, "done": 0, "cancelled": 0, "due_date_changed": 0})
        self.assertIn('<p class="week">Last 7 days: nothing new, done, cancelled or with a changed due date.</p>',
                      self.page(f.run("--save", "--project", self.solo)[0]))

    def test_work_recorded_two_ways_is_left_out_of_the_last_7_days(self):
        f = self.f
        first = f.action(self.budget, "Board pack", created="2026-10-29T09:00:00+13:00")
        f.action(self.budget, "Board pack", corrects=first, body="One way.", created="2026-10-30T09:00:00+13:00")
        f.action(self.budget, "Board pack", corrects=first, body="Another way.", created="2026-10-30T09:00:00+13:00")
        out, _ = f.run()
        self.assertEqual(out["last_7_days"]["new"], 0)

    def test_every_jump_lands_on_a_row_and_rows_have_one_id_each(self):
        f = self.f
        f.action(self.client, "Client late", due="2026-10-30")
        f.action(self.budget, "Budget today", due="2026-11-02")
        f.action(self.solo, "Trust soon", due="2026-11-05")
        for view in ([], ["--project", self.client]):
            with self.subTest(view=view):
                text = self.page(f.run("--save", *view)[0])
                page = Page(text)
                self.assertEqual(page.problems, [])  # no id twice, and no jump to a row that is not there
                self.assertGreaterEqual(len(page.jumps), 2)
                # A project with projects inside it jumps to the row of its own work.
                self.assertIn('<a class="jump" href="#p-kowhai--own">', text)
        person = self.page(f.run("--save", "--by-person")[0])
        self.assertNotIn('class="jump"', person)  # by person has no project rows to jump to

    def test_a_leftover_copy_of_a_saved_record_is_housekeeping_not_partial(self):
        f = self.f
        saved = f.action(self.budget, "Saved fine")
        record = f.root / "Record" / f"{saved}.md"
        leftover = f.root / "Record" / f".pace-tmp-{saved}-4242-a1b2c3d4"
        leftover.write_bytes(record.read_bytes())
        out, _ = f.run("--save")
        self.assertTrue(out["complete"], out["could_not_read"])
        self.assertEqual(len(out["housekeeping"]), 1)
        self.assertIn(f"is a leftover copy of Record/{saved}.md from a save that finished", out["housekeeping"][0])
        text = self.page(out)
        self.assertIn("<dt>Housekeeping</dt>", text)
        self.assertNotIn('class="partial"', text)
        # A temporary file that differs from its record, or has none beside it, may be a save that did not finish.
        leftover.write_text("half a record", encoding="utf-8")
        out, _ = f.run("--save")
        self.assertFalse(out["complete"])
        self.assertIn('<p class="partial">', self.page(out))
        leftover.unlink()
        (f.root / "Record" / f".pace-tmp-20261025T999999Z--{self.budget}--zzzzzz-1-ffffffff").write_text("x", encoding="utf-8")
        self.assertFalse(f.run()[0]["complete"])

    def test_a_long_list_folds_its_undated_work_by_the_top_project(self):
        f = self.f
        for number in range(11):
            f.action(self.budget if number % 2 else self.solo, f"Task {number}", owed_by=OWNER)
        f.action(self.site, "Dated task", owed_by=OWNER, due="2026-11-20")
        text = self.page(f.run("--save", "--by-person")[0])
        self.assertIn('<p class="group">You owe, with a due date</p>', text)
        self.assertIn('<summary>You owe, with no due date: Kowhai Books <span class="n">5</span></summary>', text)
        self.assertIn('<summary>You owe, with no due date: Pohutu Trust <span class="n">6</span></summary>', text)
        self.assertIn('<span class="side">Budget 2027</span>', text)  # inside a fold, only the projects below its top

    def test_a_short_list_is_not_folded(self):
        f = self.f
        for number in range(3):
            f.action(self.budget, f"Task {number}", owed_by=OWNER)
        text = self.page(f.run("--save", "--by-person")[0])
        self.assertIn('<p class="group">You owe, with no due date</p>', text)
        self.assertNotIn('<details class="fold">', text)


class ReviewTests(OverviewCase):
    """Cases an independent review found."""

    def test_the_one_project_facts_are_one_line_and_a_passed_target_stands_out(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz", target="2026-10-20", status="Drafting")
        text = self.page(f.run("--save", "--project", self.budget)[0])
        self.assertIn('<p class="known"><span>Part of <strong>Kowhai Books</strong></span>', text)
        self.assertIn('<span>Target <strong class="late">20 Oct 2026, 13 days late</strong></span>', text)
        self.assertNotIn('<p class="facts">', text)

    def test_work_done_long_ago_and_reworded_this_week_is_not_done_this_week(self):
        f = self.f
        first = f.action(self.budget, "Old invoice", created="2026-08-01T09:00:00+13:00")
        done = f.action(self.budget, "Old invoice", corrects=first, state="done", created="2026-08-10T09:00:00+13:00")
        f.action(self.budget, "Old invoice (spelling)", corrects=done, state="done", created="2026-11-01T09:00:00+13:00")
        self.assertEqual(f.run()[0]["last_7_days"]["done"], 0)

    def test_a_due_date_changed_this_week_still_counts_after_a_later_rewording(self):
        f = self.f
        first = f.action(self.budget, "Board pack", due="2026-11-05", created="2026-10-10T09:00:00+13:00")
        moved = f.action(self.budget, "Board pack", corrects=first, due="2026-11-20", created="2026-10-29T09:00:00+13:00")
        f.action(self.budget, "Board pack, reworded", corrects=moved, due="2026-11-20", created="2026-10-31T09:00:00+13:00")
        out, _ = f.run("--save")
        self.assertEqual(out["last_7_days"]["due_date_changed"], 1)
        self.assertIn("Kowhai Books &rsaquo; Budget 2027 &middot; was 5 Nov", self.page(out))

    def test_a_project_with_work_recorded_two_ways_is_not_called_idle_on_its_parents_page(self):
        f = self.f
        f.action(self.budget, "Budget task")
        first = f.action(self.site, "Site copy")
        f.action(self.site, "Site copy", corrects=first, body="One way.")
        f.action(self.site, "Site copy", corrects=first, body="Another way.")
        text = self.page(f.run("--save", "--project", self.client)[0])
        self.assertNotIn("No open work recorded: Website", text)
        self.assertIn("Another way.", text)

    def test_the_projects_heading_counts_only_projects_with_work_and_last_activity_takes_in_every_project_inside(self):
        f = self.f
        copy = f.project("kowhai-copy", "Copywriting", parent=self.site)
        f.action(copy, "Copy task", created="2026-10-20T09:00:00+13:00")
        archive = f.project("kowhai-archive", "Archive", parent=self.client)
        f.record(archive, "decision", "Keep the archive", "Keep it.", created="2026-11-01T09:00:00+13:00")
        text = self.page(f.run("--save", "--project", self.client)[0])
        self.assertIn('<h2>Projects <span class="n">1 inside with open work, a target or a status</span></h2>', text)
        every = self.page(f.run("--save")[0])
        self.assertIn('<span class="last">Yesterday</span>', self.row(every, self.client))  # the archive's decision

    def test_a_projects_own_work_on_its_own_page_names_no_project_and_jumps_to_its_row(self):
        f = self.f
        f.action(self.client, "Client late", due="2026-10-30")
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save", "--project", self.client)[0])
        attention = text[text.index("<h2>Needs attention"):text.index("<h2>Projects")]
        self.assertIn('<span class="subj">Client late</span> <span class="side"></span>', attention)
        self.assertIn('<a class="jump" href="#p-kowhai--own">Go to its row</a>', attention)
        self.assertEqual(Page(text).problems, [])

    def test_the_owners_name_matches_however_its_accents_and_spaces_are_written(self):
        f = self.f
        f.action(self.budget, "Mine", owed_by="Rangi  Pa\u0304rata")  # a combining macron and a doubled space
        out, _ = po.run(po.build_parser().parse_args(["--pace", str(f.root), "--as-at", AS_AT, "--owner", "Rangi P\u0101rata"]))
        self.assertEqual(out["counts"]["waiting_on_you"], 1)

    def test_input_too_deep_or_too_near_the_calendar_edge_gives_one_plain_result(self):
        f = self.f
        parent = "none"
        for number in range(1100):
            folder = f.root / "1 Projects" / f"Deep {number}"
            folder.mkdir()
            (folder / "Pace project.md").write_text(
                f"---\nformat: project-1\nid: deep-{number}\nparent: {parent}\ncreated: 2026-10-20T09:00:00+13:00\nby: Hand\n---\n",
                encoding="utf-8")
            parent = f"deep-{number}"
        f.action("deep-1099", "Deepest work")
        out, code = f.run()
        self.assertIn(out["status"], ("made", "not-made"))
        self.assertTrue(out["message"])
        edge, code = po.run(po.build_parser().parse_args(["--pace", str(f.root), "--as-at", "9999-12-31T23:30:00-13:00"]))
        self.assertEqual((edge["status"], code), ("not-made", 1))

    def test_a_customised_template_says_so_when_the_shipped_styles_cannot_stand_in(self):
        f = self.f
        shipped = (f.root / "Product/Pace add-ins/Project overview/overview-template.html").read_text(encoding="utf-8")
        older = Path(self._temp.name) / "older-template.html"
        older.write_text(shipped.replace(".node", ".project").replace(".row", ".item-row"), encoding="utf-8")
        real = Path.read_text

        def unreadable(path, *args, **kwargs):
            if path.name == "overview-template.html" and "Pace add-ins" in str(path) and path != older:
                raise PermissionError("Permission denied")
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", unreadable):
            out, _ = f.run("--template", str(older))
        self.assertIn("the shipped template's styles could not be read, so the page may look unstyled", out["message"])


class HonestyTests(OverviewCase):
    def test_a_file_that_cannot_be_read_makes_the_page_partial(self):
        self.f.action(self.budget, "Fine one")
        (self.f.root / "Record/20261025T999999Z--kowhai-budget--broken.md").write_text("not a record", encoding="utf-8")
        out, code = self.f.run("--save")
        self.assertEqual(out["status"], "saved")
        self.assertFalse(out["complete"])
        self.assertTrue(out["could_not_read"].startswith("Partial: "))
        self.assertIn("Partial: ", self.page(out))

    def test_missing_folders_stop_it_and_nothing_is_written(self):
        self.f.action(self.budget, "Any", due="2026-10-30")
        shutil.rmtree(self.f.root / "2 Views")
        out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["page"]), ("not-saved", 1, None))
        self.assertIn("2 Views/ was not found", out["message"])
        self.assertEqual(out["counts"]["overdue"], 1)  # the overview was made, so the chat can still give it
        shutil.rmtree(self.f.root / "Record")
        out, code = self.f.run()
        self.assertEqual((out["status"], code), ("not-made", 1))

    def test_a_half_written_page_is_placed_but_not_confirmed(self):
        with mock.patch.object(po.pr, "place_new", side_effect=po.pr.PartialPlacement("No space left on device")):
            out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["page"]), ("placed-not-confirmed", 1, "2 Views/2026-11-02-project-overview.html"))
        self.assertIn("may be incomplete", out["message"])

    def test_a_page_that_reads_back_differently_is_placed_but_not_confirmed(self):
        with mock.patch.object(po.pr, "read_back", return_value=b"something else"):
            out, code = self.f.run("--save")
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertIn("did not read back as written", out["message"])

    def test_a_page_that_cannot_be_written_is_not_saved(self):
        with mock.patch.object(po.pr, "place_new", side_effect=PermissionError("Permission denied")):
            out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["page"]), ("not-saved", 1, None))

    def test_a_page_as_at_an_earlier_moment_leaves_out_later_records(self):
        f = self.f
        late = f.action(self.budget, "Invoice", due="2026-10-30")
        f.action(self.budget, "Invoice", corrects=late, state="done", created="2026-11-05T09:00:00+13:00")
        out, _ = f.run("--save")
        self.assertEqual((out["counts"]["open"], out["counts"]["overdue"]), (1, 1))
        self.assertIn("1 made after this page's as-at moment was left out", out["searched"])
        self.assertNotIn("5 Nov 2026", self.page(out))

    def test_with_no_time_zone_line_each_record_keeps_its_written_date(self):
        f = self.f
        f.no_time_zone()
        f.record(self.budget, "decision", "Layout", "Two pages.", created="2026-10-31T09:00:00+13:00")  # 30 October in UTC
        out, _ = f.run("--save", "--project", self.budget)
        self.assertIsNone(out["time_zone"])
        self.assertIn("31 Oct 2026 &middot; ", self.page(out))
        self.assertIn("each record keeps the date it was written with", out["message"])

    def test_odd_but_valid_input_gives_one_plain_result(self):
        f = self.f
        f.action(self.budget, "Ancient", created="0001-01-01T09:00:00+13:00")
        out, code = f.run("--save")
        self.assertEqual((out["status"], code), ("saved", 0))
        bad = Path(self._temp.name) / "template.html"
        bad.write_bytes(b"\xff\xfe<style></style>")
        out, code = f.run("--template", str(bad))
        self.assertEqual((out["status"], code), ("not-made", 1))
        self.assertIn("template could not be read", out["message"])
        with mock.patch.object(po.pr, "scan_record_names", side_effect=PermissionError("Permission denied")):
            out, code = f.run()
        self.assertEqual((out["status"], code), ("not-made", 1))
        self.assertIn("could not be listed", out["message"])

    def test_without_save_nothing_is_written(self):
        self.f.action(self.budget, "Any")
        out, code = self.f.run()
        self.assertEqual((out["status"], code, out["page"]), ("made", 0, None))
        self.assertEqual(list((self.f.root / "2 Views").glob("*.html")), [])

    def test_the_command_line_prints_one_result_and_leaves_no_cache_files(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = po.main(["--pace", str(self.f.root), "--as-at", AS_AT, "--save"])
        out = json.loads(stdout.getvalue())
        self.assertEqual((code, out["status"]), (0, "saved"))
        self.assertEqual(list((self.f.root / "Product").rglob("__pycache__")), [])
        self.assertEqual(list((PACE_FOLDER / "Product").rglob("__pycache__")), [])


if __name__ == "__main__":
    unittest.main()
