"""The overview tool, against invented Pace folders made fresh for each test.

It reads records and projects with the record tool's own readers, follows
corrections and withdrawals, counts and orders open work from its dates, fills
in the add-in's template, and saves only new files in Views/.
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
        folder = (self.folders[parent] if parent != "none" else self.root / "Projects") / name
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
        work = text[text.index("<h2>Open work by project</h2>"):]
        self.assertLess(work.index("Older, with more detail."), work.index("<strong>Newer item</strong>"))


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
        self.assertIn("<h2>Recorded two ways</h2>", every)
        # Neither the project nor its parent is called idle: their work is in the two-ways section.
        self.assertIn('<p class="quiet">No open work recorded: Kowhai Books &rsaquo; Website, Pohutu Trust.</p>', every)
        for view in (["--by-person"], ["--project", self.budget]):
            with self.subTest(view=view):
                text = self.page(f.run("--save", *view)[0])
                self.assertIn("<h2>Recorded two ways</h2>", text)
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
    def row(self, text, name):
        table = text[text.index("<tbody>"):text.index("</tbody>")]
        return next(row for row in table.split("</tr>") if f"{name}<" in row)

    def test_owner_target_and_status_come_from_the_latest_change_that_sets_each(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Sam leads.", owner="Sam Lee", target="2026-11-20", status="Started")
        f.record(self.budget, "change", "Budget 2027", "Ana leads now.", owner="Ana Ruiz", status="Waiting on the wage sign-off",
                 created="2026-10-28T09:00:00+13:00")
        f.action(self.budget, "Budget task")
        row = self.row(self.page(f.run("--save")[0]), "Budget 2027")
        self.assertIn('<span class="status"> Waiting on the wage sign-off &middot; 28 Oct 2026</span>', row)
        self.assertIn('<td class="owner">Ana Ruiz</td><td class="target">20 Nov 2026, in 18 days</td>', row)
        self.assertNotIn("Started", row)
        # none clears one and the others stand; with no target left anywhere, the Target column goes.
        f.record(self.budget, "change", "Budget 2027", "No target for now.", target="none")
        text = self.page(f.run("--save")[0])
        self.assertIn('<td class="owner">Ana Ruiz</td><td class="num open">', self.row(text, "Budget 2027"))
        self.assertNotIn("<th>Target</th>", text)

    def test_a_change_recorded_two_ways_shows_as_that_until_the_owner_says_which_stands(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Kiri led it first.", owner="Kiri Hale", status="Started")
        first = f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz")
        f.record(self.budget, "change", "Budget 2027", "Sam leads.", owner="Sam Lee", corrects=first)
        f.record(self.budget, "change", "Budget 2027", "Rangi leads.", owner=OWNER, corrects=first)
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        row = self.row(text, "Budget 2027")
        # The newest word on the owner is disputed, so the older owner is not shown as if it stood; the status stands.
        self.assertIn('<td class="owner">Recorded two ways</td>', row)
        self.assertNotIn("Kiri Hale", row)
        self.assertIn("Started", row)
        self.assertIn("<h2>Recorded two ways</h2>", text)

    def test_accounts_that_agree_on_a_value_set_it_and_a_note_in_the_dispute_counts(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Kiri led it.", owner="Kiri Hale", status="Started")
        first = f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz")
        f.record(self.budget, "change", "Budget 2027", "Ana leads, from Sam.", owner="Ana Ruiz", corrects=first)
        f.record(self.budget, "change", "Budget 2027", "Ana leads, from Rangi.", owner="Ana Ruiz", status="Drafting",
                 corrects=first)
        f.action(self.budget, "Budget task")
        row = self.row(self.page(f.run("--save")[0]), "Budget 2027")
        self.assertIn('<td class="owner">Ana Ruiz</td>', row)  # both accounts say Ana
        self.assertIn("> Recorded two ways</span>", row)  # one account gives a status, the other none
        # A note standing against a change still makes what the change sets disputed, not the older value.
        later = f.record(self.site, "change", "Website", "Mere leads.", owner="Mere Tane")
        f.record(self.site, "change", "Website", "Tom leads.", owner="Tom Ihaka", corrects=later)
        f.record(self.site, "note", "Website", "It is not decided.", corrects=later)
        f.action(self.site, "Site task")
        row = self.row(self.page(f.run("--save")[0]), "Website")
        self.assertIn('<td class="owner">Recorded two ways</td>', row)

    def test_the_owner_leading_shows_as_you_and_a_passed_target_is_late(self):
        f = self.f
        f.record(self.site, "change", "Website", "Mine, and it was due last week.", owner="owner", target="2026-10-28")
        f.action(self.site, "Site task")
        row = self.row(self.page(f.run("--save")[0]), "Website")
        self.assertIn('<td class="owner">You</td><td class="target late">28 Oct 2026, 5 days late</td>', row)

    def test_columns_show_only_when_a_project_has_one(self):
        f = self.f
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        self.assertIn("<tr><th>Project</th><th class=\"num\">Open</th>", text)
        f.record(self.site, "change", "Website", "Aiming for December.", target="2026-12-01")
        text = self.page(f.run("--save")[0])
        self.assertIn("<tr><th>Project</th><th>Target</th><th class=\"num\">Open</th>", text)
        self.assertNotIn("<th>Owner</th>", text)

    def test_a_project_with_only_a_status_is_in_the_table_not_idle(self):
        f = self.f
        f.record(self.solo, "change", "Trust", "Paused.", status="On hold until January")
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        row = self.row(text, "Pohutu Trust")
        self.assertIn("On hold until January", row)
        self.assertIn('<td class="num open">0</td>', row)
        self.assertNotIn("Pohutu Trust", text[text.index('<p class="quiet">No open work recorded'):].split("</p>")[0])
        self.assertNotIn("Pohutu Trust</summary>", text)  # no open work, so no section of its own

    def test_correcting_an_older_change_does_not_make_it_the_newest(self):
        f = self.f
        older = f.record(self.budget, "change", "Budget 2027", "Sam leads.", owner="Sam Lee", status="Started",
                         created="2026-10-19T09:00:00+13:00")
        f.record(self.budget, "change", "Budget 2027", "Ana leads now.", owner="Ana Ruiz", status="Waiting",
                 created="2026-10-24T09:00:00+13:00")
        f.record(self.budget, "change", "Budget 2027 kick-off", "Sam leads.", owner="Sam Lee", status="Started", corrects=older,
                 created="2026-10-28T09:00:00+13:00")  # only the subject is fixed
        f.action(self.budget, "Budget task")
        row = self.row(self.page(f.run("--save")[0]), "Budget 2027")
        self.assertIn('<td class="owner">Ana Ruiz</td>', row)
        self.assertIn("> Waiting &middot; 24 Oct 2026</span>", row)

    def test_odd_change_records_never_stop_the_page(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Due at the end of November.", target="27 November")  # not a date
        f.action(self.budget, "Budget task")
        for view in ([], ["--project", self.budget], ["--by-person"]):
            with self.subTest(view=view):
                out, code = f.run("--save", *view)
                self.assertEqual((out["status"], code), ("saved", 0), out)
                self.assertNotIn("27 November</td>", self.page(out))
                # The target was not used, and every view says why, so it does not vanish without trace.
                self.assertFalse(out["complete"])
                self.assertIn("gives the target '27 November', which is not a real date, so it was not used.", out["could_not_read"])

    def test_the_one_project_view_gives_its_owner_target_and_status(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Ana leads.", owner="Ana Ruiz", target="2026-11-27", status="Drafting")
        text = self.page(f.run("--save", "--project", self.budget)[0])
        for line in ("<dt>Owner</dt>\n<dd>Ana Ruiz</dd>", "<dt>Target</dt>\n<dd>27 Nov 2026, in 25 days</dd>",
                     "<dt>Status</dt>\n<dd>Drafting &middot; 25 Oct 2026</dd>"):
            self.assertIn(line, text)
        text = self.page(f.run("--save", "--project", self.site)[0])
        self.assertIn("<dt>Owner</dt>\n<dd>Not recorded</dd>", text)


class OddFolderTests(OverviewCase):
    def test_a_record_with_no_project_line_is_shown_with_work_that_names_no_project(self):
        lines = ["---", "format: record-1", "request: 20261025T120000Z--kowhai-budget--nopro1", "created: 2026-10-26T01:00:00+13:00",
                 "kind: action", "subject: Lost", "from: agent", "by: Hand", "state: open", "---", "", "No project line.", ""]
        (self.f.root / "Record/20261025T120000Z--kowhai-budget--nopro1.md").write_text("\n".join(lines), encoding="utf-8")
        out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["complete"]), ("saved", 0, False), out)
        self.assertIn("No project line.", self.page(out))

    def test_a_project_whose_parents_loop_is_still_shown(self):
        loop = self.f.root / "Projects/Loop"
        loop.mkdir()
        (loop / "Pace project.md").write_text(
            "---\nformat: project-1\nid: loop\nparent: loop\ncreated: 2026-10-20T09:00:00+13:00\nby: Hand\n---\n", encoding="utf-8")
        self.f.action("loop", "Looped work")
        out, _ = self.f.run("--save")
        text = self.page(out)
        self.assertIn("<tr><th>Loop</th>", text)
        self.assertIn("Loop <span class=\"counts\">", text)
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
            table = text[text.index("<tbody>"):text.index("</tbody>")]
            orders.add(tuple(sorted(("Alpha", "Beta", "Delta", "Gamma"), key=table.index)))
        self.assertEqual(orders, {("Alpha", "Beta", "Delta", "Gamma")})

    def test_a_status_still_reads_with_a_template_made_before_it(self):
        f = self.f
        f.record(self.budget, "change", "Budget 2027", "Paused.", status="Paused")
        shipped = (f.root / "Product/Pace add-ins/Project overview/overview-template.html").read_text(encoding="utf-8")
        older = Path(self._temp.name) / "older-template.html"
        older.write_text(re.sub(r"\.status \{[^}]*\}\n", "", shipped), encoding="utf-8")
        text = self.page(f.run("--save", "--template", str(older))[0])
        self.assertIn('Budget 2027<span class="status"> Paused', text)  # a space keeps it apart without the new style


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
        table = text[text.index("<tbody>"):text.index("</tbody>")]
        self.assertIn('<tr><th><span class="parent">Kowhai Books &rsaquo; Budget 2027 &rsaquo; Board pack &rsaquo;</span> Slides</th>',
                      table)
        order = [table.index(row) for row in ("Slides</th>", "Website</th>", "<tr><th>Pohutu Trust</th>")]
        self.assertEqual(order, sorted(order))
        # The projects above Slides hold no work of their own, but none is idle: Slides is inside them.
        self.assertNotIn("No open work recorded", text)
        self.assertIn(
            '<p class="where">Kowhai Books &rsaquo; Budget 2027 &rsaquo; Board pack &rsaquo; Slides</p>',
            text[text.index("<h2>Needs attention</h2>"):])

    def test_projects_side_by_side_run_by_the_most_pressing_work_anywhere_inside_them(self):
        f = self.f
        f.action(self.site, "Site soon", due="2026-11-04")
        f.action(self.budget, "Budget undated")
        f.action(self.slides, "Slides late", due="2026-10-30")
        table = self.page(f.run("--save")[0])
        table = table[table.index("<tbody>"):table.index("</tbody>")]
        # Budget 2027's own work is undated, but Slides inside it is late, so its branch comes before Website.
        order = [table.index(row) for row in ("Budget 2027</th>", "Slides</th>", "Website</th>")]
        self.assertEqual(order, sorted(order))

    def test_one_project_takes_in_every_project_inside_it_at_any_depth(self):
        f = self.f
        f.action(self.slides, "Slides task", due="2026-11-03")
        f.action(self.site, "Site task")
        out, _ = f.run("--save", "--project", self.client)
        self.assertEqual(out["counts"]["open"], 2)
        text = self.page(out)
        self.assertIn("<dd>Budget 2027, Budget 2027 &rsaquo; Board pack, Budget 2027 &rsaquo; Board pack &rsaquo; Slides, Website</dd>",
                      text)
        table = text[text.index("<h2>Projects</h2>"):text.index("</table>")]
        self.assertLess(table.index("Slides</th>"), table.index("Website</th>"))
        deepest = self.page(f.run("--save", "--project", self.slides)[0])
        self.assertIn("<dt>Part of</dt>\n<dd>Kowhai Books &rsaquo; Budget 2027 &rsaquo; Board pack</dd>", deepest)
        self.assertIn("<h1>Slides</h1>", deepest)


class PageTests(OverviewCase):
    def test_the_saved_page_is_well_formed_and_read_back(self):
        self.f.action(self.budget, "Late one", due="2026-10-28", owed_by=OWNER)
        out, code = self.f.run("--save", "--asked", "Where are we?")
        self.assertEqual((out["status"], code, out["page"]), ("saved", 0, "Views/2026-11-02-project-overview.html"), out)
        self.assertIn("Saved and read back: Views/2026-11-02-project-overview.html.", out["message"])
        text = self.page(out)
        page = Page(text)
        self.assertEqual(page.problems, [])
        self.assertIsNone(FORBIDDEN.search(text))
        self.assertIn("<dd>Where are we?</dd>", text)
        self.assertIn("<dd>Monday 2 November 2026, 9:00 am NZDT</dd>", text)
        self.assertIn("<title>Project overview, 2 Nov 2026 - Pace by SBR</title>", text)
        self.assertIn('<li class="tile key"><span class="count">1</span> overdue</li>', text)
        self.assertIn('<span class="when">5 days late</span>', text)
        self.assertNotRegex(text, r"\bRecord \d{8}T\d{6}Z")  # record references stay in the tool's result, not on the page
        self.assertEqual(out["needs_attention"][0]["request"][:9], "20261025T")

    def test_a_page_is_never_replaced(self):
        pages = [self.f.run("--save")[0] for _ in range(3)]
        self.assertEqual([out["page"] for out in pages], ["Views/2026-11-02-project-overview.html",
                                                          "Views/2026-11-02-project-overview-2.html",
                                                          "Views/2026-11-02-project-overview-3.html"])
        self.assertEqual(self.page(pages[0]), self.page(pages[2]))

    def test_projects_are_grouped_under_their_parent_most_pressing_first(self):
        f = self.f
        f.action(self.site, "Site soon", due="2026-11-04")
        f.action(self.budget, "Budget late", due="2026-10-30")
        f.action(self.solo, "Trust undated")
        f.action(self.client, "Client undated")
        text = self.page(f.run("--save")[0])
        table = text[text.index("<tbody>"):text.index("</tbody>")]
        # The Kowhai group is the most pressing; in it the parent's own row comes first, then its projects.
        rows = ["<tr><th>Kowhai Books</th>", "Budget 2027</th>", "Website</th>", "<tr><th>Pohutu Trust</th>"]
        order = [table.index(row) for row in rows]
        self.assertEqual(order, sorted(order))
        # Earliest due is the earliest date of the project's open work, overdue or not.
        self.assertIn('<td class="num overdue late">1</td><td class="due late">30 Oct 2026, 3 days late</td>', table)
        self.assertIn('<td class="num overdue">0</td><td class="due">4 Nov 2026, in 2 days</td>', table)
        self.assertIn('<td class="num open">1</td><td class="num overdue">0</td><td class="due">No due date</td>', table)
        self.assertNotIn("No open work recorded", text)
        details = text[text.index("<h2>Open work by project</h2>"):]
        self.assertLess(details.index("Budget 2027"), details.index("Pohutu Trust"))

    def test_a_parent_whose_projects_have_open_work_is_not_listed_as_having_none(self):
        f = self.f
        f.project("kowhai-plans", "Plans", parent="kowhai")
        f.action(self.budget, "Budget task")
        text = self.page(f.run("--save")[0])
        self.assertIn('<p class="quiet">No open work recorded: Kowhai Books &rsaquo; Plans, Kowhai Books &rsaquo; Website, '
                      'Pohutu Trust.</p>', text)
        table = text[text.index("<tbody>"):text.index("</tbody>")]
        self.assertNotIn("<tr><th>Kowhai Books</th>", table)
        self.assertIn("Budget 2027</th>", table)

    def test_record_text_cannot_add_markup(self):
        hostile = '<script>alert(1)</script> & "quotes" \'single\' </li></ul><h1>x</h1>'
        self.f.action(self.budget, "<b>Subject</b>", body=hostile, owed_by="<Sam & Co>")
        text = self.page(self.f.run("--save")[0])
        page = Page(text)
        self.assertEqual(page.problems, [])
        self.assertIsNone(FORBIDDEN.search(text))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quotes&quot; &#39;single&#39;", text)
        self.assertIn("Owed by &lt;Sam &amp; Co&gt;", text)
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
        self.assertEqual((out["status"], out["page"], out["view"]), ("saved", "Views/2026-11-02-project-overview-kowhai.html", "one project"))
        self.assertEqual(out["counts"]["open"], 2)
        text = self.page(out)
        self.assertEqual(Page(text).problems, [])
        self.assertIn("<h1>Kowhai Books</h1>", text)
        self.assertIn("<dd>Budget 2027, Website</dd>", text)
        self.assertIn("Use the two-page layout.", text)
        self.assertIn("Ana now owns the model.", text)
        self.assertNotIn("Too old to show.", text)
        self.assertNotIn("Not this one", text)
        self.assertIn("<!-- start: one project view -->", text)
        # A project inside it has open work, so the view has the projects table for it and them.
        table = text[text.index("<h2>Projects</h2>"):text.index("</table>")]
        self.assertLess(table.index("Budget 2027</th>"), table.index("Website</th>"))
        self.assertIn('<td class="due">3 Nov 2026, tomorrow</td>', table)
        self.assertNotIn("Pohutu Trust", table)
        # A project with no projects inside it has no table.
        alone, _ = f.run("--project", "kowhai-budget", "--save")
        self.assertNotIn("<h2>Projects</h2>", self.page(alone))

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
        copy = f.root / "My add-ins/Project overview/overview-template.html"
        copy.parent.mkdir(parents=True)
        copy.write_text(shipped.replace(".lede { margin-bottom: 0.75rem;", ".lede { margin-bottom: 0.9rem;")
                        .replace("<h2>Needs attention</h2>", "<h2>Urgent</h2>"), encoding="utf-8")
        out, _ = f.run("--save", "--template", "My add-ins/Project overview/overview-template.html")
        text = self.page(out)
        self.assertIn(".lede { margin-bottom: 0.9rem;", text)
        self.assertIn("<h2>Needs attention</h2>", text)  # the sections and wording are always the add-in's own
        self.assertNotIn("Urgent", text)

    def test_no_text_from_records_or_folders_can_add_markup_in_any_view(self):
        f = self.f
        hostile = '<b>x</b> & "q" \'s\' </li></ul>'
        parent_name, child_name, idle_name = '<i>Evil<b> & "Co"', "<u>Kid's", "<q>Idle"  # folder names cannot hold "/"
        parent = f.project("evil", parent_name, purpose=hostile)
        child = f.project("evil-kid", child_name, parent="evil", purpose=hostile)
        f.project("idle", idle_name)
        (f.root / "Projects" / parent_name / "Documents" / '<b>doc & "q".txt').write_text("x", encoding="utf-8")
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
        table = every[every.index("<tbody>"):every.index("</tbody>")]
        self.assertIn(f"<tr><th>{escaped['parent']}</th>", table)
        self.assertIn(f'<span class="parent">{escaped["parent"]} &rsaquo;</span> {escaped["child"]}</th>', table)
        self.assertIn(f"No open work recorded: {escaped['idle']}, Kowhai Books, ", every)
        self.assertIn(f'<p class="where">{escaped["parent"]} &rsaquo; {escaped["child"]}</p>', pages["person"])
        self.assertIn(f"<h1>{escaped['parent']}</h1>", pages["parent"])
        self.assertIn(f"<dt>Projects inside it</dt>\n<dd>{escaped['child']}</dd>", pages["parent"])
        self.assertIn("&lt;b&gt;doc &amp; &quot;q&quot;.txt", pages["parent"])
        self.assertIn(f"<h1>{escaped['child']}</h1>", pages["child"])
        self.assertIn(f"<dt>Part of</dt>\n<dd>{escaped['parent']}</dd>", pages["child"])
        self.assertIn("&lt;i&gt;odd &amp; &#39;x&#39;.md", every)

    def test_an_unknown_project_makes_nothing(self):
        out, code = self.f.run("--project", "nope", "--save")
        self.assertEqual((out["status"], code), ("not-made", 1))
        self.assertEqual(list((self.f.root / "Views").glob("*.html")), [])

    def test_by_person_puts_the_owner_first(self):
        f = self.f
        f.action(self.budget, "Sam's list", owed_by="Sam Lee", **{"for": OWNER})
        f.action(self.budget, "My sign-off", owed_by=OWNER, **{"for": "Ana Ruiz"})
        f.action(self.site, "Nobody's")
        f.action(self.site, "Sam alone", owed_by="Sam Lee")
        out, _ = f.run("--by-person", "--save")
        text = self.page(out)
        self.assertEqual(Page(text).problems, [])
        cards = [text.index(f"<h2>{name}</h2>") for name in ("You", "Ana Ruiz", "Sam Lee", "No person named")]
        self.assertEqual(cards, sorted(cards))
        self.assertIn("For Ana Ruiz", text)
        self.assertIn("For you", text)
        # Who an item is for is shown only when the record names someone.
        self.assertNotIn("For: not recorded", text)
        sam_alone = text[text.index("<strong>Sam alone</strong>"):]
        self.assertTrue(sam_alone[sam_alone.index('<p class="meta">'):].startswith('<p class="meta">no due date &middot; open</p>'))


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
        shutil.rmtree(self.f.root / "Views")
        out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["page"]), ("not-saved", 1, None))
        self.assertIn("Views/ was not found", out["message"])
        self.assertEqual(out["counts"]["overdue"], 1)  # the overview was made, so the chat can still give it
        shutil.rmtree(self.f.root / "Record")
        out, code = self.f.run()
        self.assertEqual((out["status"], code), ("not-made", 1))

    def test_a_half_written_page_is_placed_but_not_confirmed(self):
        with mock.patch.object(po.pr, "place_new", side_effect=po.pr.PartialPlacement("No space left on device")):
            out, code = self.f.run("--save")
        self.assertEqual((out["status"], code, out["page"]), ("placed-not-confirmed", 1, "Views/2026-11-02-project-overview.html"))
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
        self.assertEqual(list((self.f.root / "Views").glob("*.html")), [])

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
