"""The Weekly review: its list from the overview tool, the record tool's update-action, and the add-in's own words.

Invented data only, in temporary Pace folders made fresh for each test.
"""

from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_overview_tool import AS_AT, OWNER, Folder, OverviewCase, po
from test_records import BUDGET, CLIENT, PaceFolder, at, pr
from test_addins import PACE_FOLDER, SHIPPED, section

MARK = "<!-- Your lines go below this one. Pace updates never change them. -->"
ADD_IN = PACE_FOLDER / SHIPPED / "Weekly review/ADD-IN.md"


def with_owner_line(folder: Folder, *names) -> None:
    pace_md = folder.root / "Pace.md"
    lines = "".join(f"Owner: {name}\n" for name in names)
    pace_md.write_text(pace_md.read_text(encoding="utf-8").replace(f"{MARK}\n## Time zone", f"{MARK}\n{lines}\n## Time zone"),
                       encoding="utf-8")


def files_in(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


class ReviewListTests(OverviewCase):
    def setUp(self):
        super().setUp()
        f = self.f
        with_owner_line(f, OWNER)
        self.late = f.action(self.budget, "Board pack", due="2026-10-28", owed_by=OWNER)
        self.late_other = f.action(self.site, "Site copy", due="2026-11-01", owed_by="Ana Ruiz")
        self.today = f.action(self.solo, "Trust minutes", due="2026-11-02")
        self.soon = f.action(self.site, "Launch note", due="2026-11-09", owed_by=OWNER)
        self.later = f.action(self.site, "Domain renewal", due="2026-11-10", owed_by=OWNER)
        self.waiting = f.action(self.budget, "Supplier quote", owed_by="Sam Lee", created="2026-10-20T09:00:00+13:00")
        self.mine_old = f.action(self.budget, "Fix the forecast tab", owed_by=OWNER, created="2026-10-10T09:00:00+13:00")
        self.nobody = f.action(self.solo, "Trust deed copy", created="2026-10-15T09:00:00+13:00")
        f.action(self.solo, "Already done", state="done")
        f.record(self.solo, "decision", "Trust meets monthly", "Invented decision.")
        first = f.action(self.client, "Insurance renewal", due="2026-11-20", owed_by=OWNER)
        self.two = [f.action(self.client, "Insurance renewal", due="2026-11-21", owed_by=OWNER, corrects=first),
                    f.action(self.client, "Insurance renewal", state="done", owed_by=OWNER, corrects=first)]

    def review(self, *argv, owner=False):
        out, code = self.f.run("--review", *argv, owner=owner)
        self.assertEqual((out["status"], code), ("made", 0), out)
        return out

    def test_the_list_is_grouped_in_the_add_ins_order_and_numbered_across_it(self):
        out = self.review()
        groups = [(group["group"], [item.get("request") or [a["request"] for a in item["accounts"]] for item in group["items"]])
                  for group in out["groups"]]
        self.assertEqual(groups, [
            ("two-ways", [sorted(self.two)]),
            ("overdue", [self.late, self.late_other]),
            ("due-soon", [self.today, self.soon]),
            ("waiting", [self.waiting]),
            ("no-due-date", [self.mine_old, self.nobody]),
        ])
        numbers = [item["number"] for group in out["groups"] for item in group["items"]]
        self.assertEqual(numbers, list(range(1, 9)))
        self.assertEqual(out["counts"], {"two-ways": 1, "overdue": 2, "due-soon": 2, "waiting": 1, "no-due-date": 2,
                                         "due_later": 1})
        self.assertIn("8 to go through: 1 recorded two ways, 2 overdue, 2 due today or in the next 7 days, 1 waiting on "
                      "others with no due date and 2 with no due date. 1 more is due later, from 2026-11-10, and not in the "
                      "list. Nothing was saved or changed.", out["message"])
        self.assertNotIn(self.later, str(out["groups"]))

    def test_each_item_has_a_line_for_the_chat_and_its_current_account(self):
        items = {item["number"]: item for group in self.review()["groups"] for item in group["items"]}
        self.assertEqual(items[2]["line"], "2. 5 days late - Board pack - Kowhai Books > Budget 2027")
        self.assertEqual(items[3]["line"], "3. 1 day late - Site copy - Kowhai Books > Website - owed by Ana Ruiz")
        self.assertEqual(items[4]["line"], "4. Due today - Trust minutes - Pohutu Trust - no person named")
        self.assertEqual(items[5]["line"], "5. Due in 7 days - Launch note - Kowhai Books > Website")
        self.assertEqual(items[6]["line"], "6. Waiting 13 days - Supplier quote - Kowhai Books > Budget 2027 - owed by Sam Lee")
        self.assertEqual(items[7]["line"], "7. Open 23 days - Fix the forecast tab - Kowhai Books > Budget 2027")
        self.assertEqual(items[1]["line"], "1. Recorded two ways - Insurance renewal - Kowhai Books")
        self.assertEqual([account["state"] for account in items[1]["accounts"]], ["open", "done"])
        self.assertEqual((items[7]["request"], items[7]["open_days"], items[7]["first_recorded"], items[7]["due"]),
                         (self.mine_old, 23, "2026-10-10", None))
        self.assertEqual((items[2]["due"], items[2]["when"], items[2]["owed_by"]), ("2026-10-28", "5 days late", OWNER))

    def test_a_corrected_item_is_listed_by_its_current_account_in_its_first_place(self):
        moved = self.f.action(self.budget, "Fix the forecast tab", owed_by=OWNER, corrects=self.mine_old,
                              created="2026-10-30T09:00:00+13:00")
        items = {item["subject"]: item for group in self.review()["groups"] for item in group["items"]}
        self.assertEqual(items["Fix the forecast tab"]["request"], moved)
        self.assertEqual(items["Fix the forecast tab"]["open_days"], 23)  # counted from when it was first recorded

    def test_one_project_reviews_it_and_the_projects_inside_it(self):
        out = self.review("--project", self.client)
        subjects = [item["subject"] for group in out["groups"] for item in group["items"]]
        self.assertEqual(subjects, ["Insurance renewal", "Board pack", "Site copy", "Launch note", "Supplier quote",
                                    "Fix the forecast tab"])
        self.assertIn("Review list for Kowhai Books and the projects inside it", out["message"])

    def test_the_owners_work_is_told_apart_by_the_owner_line(self):
        # Without the line, the owner's own undated work would look like someone else's.
        pace_md = self.f.root / "Pace.md"
        pace_md.write_text(pace_md.read_text(encoding="utf-8").replace(f"Owner: {OWNER}\n", ""), encoding="utf-8")
        out = self.review()
        waiting = [item["subject"] for group in out["groups"] if group["group"] == "waiting" for item in group["items"]]
        self.assertEqual(waiting, ["Supplier quote", "Fix the forecast tab"])
        self.assertIn("Pace.md has no Owner: line and no --owner was given", out["message"])
        self.assertEqual(out["owner_names"], [])
        out = self.review(owner=True)  # --owner still works for one run
        waiting = [item["subject"] for group in out["groups"] if group["group"] == "waiting" for item in group["items"]]
        self.assertEqual(waiting, ["Supplier quote"])
        self.assertNotIn("no Owner: line", out["message"])

    def test_the_review_list_saves_nothing_and_refuses_what_it_cannot_do(self):
        before = files_in(self.f.root)
        self.review()
        self.assertEqual(files_in(self.f.root), before)
        for argv, said in ((("--save",), "never saved as a page"), (("--by-person",), "leave out --by-person"),
                           (("--project", "no-such-project"), "No project with id 'no-such-project'")):
            with self.subTest(argv=argv):
                out, code = self.f.run("--review", *argv, owner=False)
                self.assertEqual((out["status"], code), ("not-made", 1), out)
                self.assertIn(said, out["message"])
        self.assertEqual(files_in(self.f.root), before)

    def test_a_partial_read_is_said_first(self):
        (self.f.root / "Record" / "20261025T090000Z--pohutu--brk001.md").write_text("not a record\n", encoding="utf-8")
        out = self.review()
        self.assertFalse(out["complete"])
        self.assertIn("Partial: something could not be read", out["message"])
        self.assertTrue(out["could_not_read"].startswith("Partial: "))


class UpdateActionTests(PaceFolder):
    def setUp(self):
        super().setUp()
        self.action, out, _ = self.save(kind="action", subjects=("Board pack", "October close"), origin="owner",
                                        words="Send the board pack by the 5th.", body="Send the board pack to the board.",
                                        extra=("--due", "2026-11-05", "--owed-by", "Sam Lee", "--for", "owner",
                                               "--state", "open"))
        self.assertEqual(out["status"], "saved", out)

    def update(self, corrects, *options, request=None, project=BUDGET, words="3 done"):
        request = request or self.new_request(project, at(day=30))
        args = ["update-action", "--request", request, "--corrects", corrects, *options, "--by", "Test agent"]
        if words is not None:
            args += ["--from", "owner", "--words", words]
        else:
            args += ["--from", "agent"]
        out, code = self.run_tool(*args)
        return request, out, code

    def fields(self, request):
        out, _ = self.run_tool("read", "--request", request)
        return out["record"]

    def test_done_carries_the_rest_of_the_action_over_and_says_the_change(self):
        request, out, code = self.update(self.action, "--state", "done")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertEqual(out["corrects"], self.action)
        self.assertEqual(out["changes"], ["Done."])
        self.assertIn(f"It corrects {self.action}: Done.", out["message"])
        record = self.fields(request)
        self.assertEqual((record["kind"], record["subjects"], record["due"], record["owed-by"], record["for"], record["state"],
                          record["corrects"], record["words"]),
                         ("action", ["Board pack", "October close"], "2026-11-05", "Sam Lee", "owner", "done", self.action,
                          "3 done"))
        text = (self.record / f"{request}.md").read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n---\n\nSend the board pack to the board.\n\nDone.\n"), text)
        story, _ = self.run_tool("history", "--request", self.action)
        self.assertEqual(story["current"], [request])

    def test_a_new_due_day_and_people_change_in_plain_words(self):
        first, out, _ = self.update(self.action, "--due", "2026-11-12", "--owed-by", "Ana Ruiz", words="Move it to the 12th")
        self.assertEqual(out["changes"], ["Due 12 November 2026 (was 5 November 2026).", "Now owed by Ana Ruiz (was Sam Lee)."])
        record = self.fields(first)
        self.assertEqual((record["due"], record["owed-by"], record["state"]), ("2026-11-12", "Ana Ruiz", "open"))
        second, out, _ = self.update(first, "--due", "none", "--for", "none", "--note", "Waiting on the auditor first.",
                                     words="No date for now")
        self.assertEqual(out["status"], "saved", out)
        self.assertEqual(out["changes"], ["No due date now (was 12 November 2026).", "No longer for owner."])
        record = self.fields(second)
        self.assertNotIn("due", record)
        self.assertNotIn("for", record)
        text = (self.record / f"{second}.md").read_text(encoding="utf-8")
        self.assertIn("Send the board pack to the board.\n\nDue 12 November 2026 (was 5 November 2026). Now owed by Ana Ruiz "
                      "(was Sam Lee).\n\nNo due date now (was 12 November 2026). No longer for owner.\n\nWaiting on the "
                      "auditor first.\n", text)

    def test_the_whole_text_can_be_given_instead(self):
        request, out, _ = self.update(self.action, "--state", "cancelled", "--body", "The board met without it.")
        self.assertEqual(out["status"], "saved", out)
        self.assertTrue((self.record / f"{request}.md").read_text(encoding="utf-8").endswith("\n\nThe board met without it.\n"))

    def test_a_retry_with_the_same_request_is_already_saved(self):
        request, out, _ = self.update(self.action, "--state", "done")
        self.assertEqual(out["status"], "saved", out)
        files = self.record_files()
        _, again, code = self.update(self.action, "--state", "done", request=request)
        self.assertEqual((again["status"], code), ("already-saved", 0), again)
        self.assertEqual(self.record_files(), files)

    def test_only_the_current_account_of_an_action_is_updated(self):
        request, out, _ = self.update(self.action, "--state", "done")
        self.assertEqual(out["status"], "saved", out)
        _, out, code = self.update(self.action, "--state", "cancelled")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn(f"{self.action} is not the current account; {request} is", out["message"])
        decision, saved, _ = self.save(subjects=("Close date",))
        self.assertEqual(saved["status"], "saved", saved)
        _, out, _ = self.update(decision, "--state", "done")
        self.assertIn("is a decision, not an action", out["message"])

    def test_an_action_recorded_two_ways_is_settled_first(self):
        for name, state in (("aaa001", "open"), ("aaa002", "done")):
            request = f"20261024T000000Z--{BUDGET}--{name}"
            self.write_raw(f"{request}.md", self.raw_record(request, "Invented account.", corrects=self.action, kind="action",
                                                            extra=f"state: {state}"))
        _, out, code = self.update(f"20261024T000000Z--{BUDGET}--aaa001", "--state", "done")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("this item is recorded two ways", out["message"])
        self.assertIn("Save a withdrawal of the other", out["message"])

    def test_what_it_refuses(self):
        cases = [
            ((self.action, "--state", "open"), {}, "nothing would change"),
            ((self.action, "--due", "next Friday"), {}, "due must be a real date"),
            ((self.action, "--state", "done"), {"project": CLIENT}, f"Make the request with new-request --project {BUDGET}"),
            ((f"20261001T000000Z--{BUDGET}--zzz999", "--state", "done"), {}, "was not found"),
            (("not-a-request", "--state", "done"), {}, "--corrects needs the request id"),
            ((self.action, "--state", "done"), {"words": ""}, "from owner needs their words"),
        ]
        for argv, options, said in cases:
            with self.subTest(said=said):
                files = self.record_files()
                _, out, code = self.update(*argv, **options)
                self.assertEqual((out["status"], code), ("not-saved", 1), out)
                self.assertIn(said, out["message"])
                self.assertEqual(self.record_files(), files)

    def test_the_records_help_describes_the_command_as_the_tool_has_it(self):
        text = (PACE_FOLDER / "Product/Help/records.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| `update-action"))
        options = set(re.findall(r"`(--[a-z-]+)`", row))
        parser = pr.build_parser()
        known = set(parser._subparsers._group_actions[0].choices["update-action"]._option_string_actions)
        self.assertEqual(options - known, set())
        self.assertGreaterEqual(options, {"--state", "--due", "--owed-by", "--for", "--note"})
        self.assertIn("The record tool's `update-action` does this in one step.", text)


class AddInTests(unittest.TestCase):
    def test_the_add_in_keeps_the_owner_in_charge_of_every_change(self):
        text = ADD_IN.read_text(encoding="utf-8")
        steps, limits = section(text, "Steps"), section(text, "Limits")
        for phrase in ("Number the items from 1 across the whole list", "**Recorded two ways**", "**Overdue**",
                       "**Due today and in the next 7 days**", "**Waiting on others, with no due date**", "**No due date**",
                       "no more than 15 items at once", "never mark work done because it looks finished, is old or was skipped",
                       "show the changes as one list", "On the owner's yes in their own words", "Read each one back",
                       "withdraw the other, then make any change the owner gave to the one that stands",
                       "the overview tool's review list"):
            self.assertIn(phrase, steps)
        for phrase in ("Nothing is saved without the owner's yes in their own words",
                       "make the list and stop: save nothing, mark nothing done and send nothing",
                       "It sends nothing to anyone."):
            self.assertIn(phrase, limits)
        self.assertIn("`Owner:` lines in `Pace.md`", section(text, "What it needs"))
        self.assertNotIn("python3", text)


if __name__ == "__main__":
    unittest.main()
