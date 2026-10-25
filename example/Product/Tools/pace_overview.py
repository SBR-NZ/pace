#!/usr/bin/env python3
"""Pace project overview: a dated page made from the records, in the Project overview add-in's template.

Reads Record/ and 1 Projects/ with the record tool's own readers, follows corrections and withdrawals
to each item's current account, and works out what is open, overdue or due soon and whose move it
is. It changes no record. With --save it creates one new page in 2 Views/, never replacing a file,
and reads it back. Every command prints one JSON object: "status" is the honest outcome and
"message" says it in plain words.

Standard library only; Python 3.9 or later (3.8 cannot read time zones).
Help: Product/Help/hosts-and-views.md (The overview tool) and the Project overview add-in.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True  # keep Product/ free of cache files

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pace_record", HERE / "pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

TEMPLATE = Path("Product") / "Pace add-ins" / "Project overview" / "overview-template.html"
VIEWS_DIR = "2 Views"
PRODUCT_NAME = "Pace by SBR"
SOON_DAYS = 7
RECENT_DAYS = 21
WEEK_DAYS = 7  # the "Last 7 days" line, today included
AGE_DAYS = 14  # work with no due date shows how long it has been open from this many days
FOLD_AFTER = 10  # a person owing more than this many items has their undated work folded by client
OWNER_WORDS = {"owner", "the owner"}
ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;"))
DOT = " &middot; "
CHEVRON = " &rsaquo;"
TRAIL = CHEVRON + " "  # between the names of a project and the projects above it


class Stop(Exception):
    """The overview cannot be made; the message says why in plain words."""


def esc(text) -> str:
    """Plain text made safe for the page: & first, then < > " and '."""
    text = str(text)
    for raw, entity in ESCAPES:
        text = text.replace(raw, entity)
    return text


def plain(text: str) -> str:
    return " ".join((text or "").split())


def name_key(name: str) -> str:
    """A person's name as one key: accents in one form, single spaces and no case, so one person is one person."""
    return " ".join(unicodedata.normalize("NFC", name or "").split()).casefold()


# ---------------------------------------------------------------- dates

def long_moment(moment: dt.datetime) -> str:
    hour = moment.strftime("%I").lstrip("0") or "12"
    return f"{moment:%A} {moment.day} {moment:%B %Y}, {hour}:{moment:%M} {moment:%p}".replace("AM", "am").replace("PM", "pm") + f" {moment.tzname()}"


def short_date(day: dt.date) -> str:
    return f"{day.day} {day:%b %Y}"


def days_word(count: int) -> str:
    return f"{count} day" + ("" if count == 1 else "s")


def how_soon(due: dt.date, today: dt.date) -> str:
    gap = (due - today).days
    if gap == 0:
        return "today"
    if gap < 0:
        return f"{days_word(-gap)} late"
    return "tomorrow" if gap == 1 else f"in {days_word(gap)}"


def how_long_ago(day: dt.date, today: dt.date) -> str:
    gap = (today - day).days
    if gap <= 0:
        return "today"
    return "yesterday" if gap == 1 else f"{days_word(gap)} ago"


def day_and_age(day: dt.date | None, today: dt.date) -> str:
    """A record's date and how long ago it was. With no Time zone line a record keeps the date it was written with,
    which can be after this computer's today; that date is shown alone rather than called today."""
    if day is None:
        return "Not recorded"
    return short_date(day) if day > today else f"{short_date(day)}, {how_long_ago(day, today)}"


# ---------------------------------------------------------------- reading the folder

class Folder:
    """Everything the overview needs from one Pace folder, read once."""

    def __init__(self, pace: Path, owners, as_at: str | None):
        self.pace = pace
        try:
            self.zone_name, zone = pr.owner_time_zone(pace)
        except ValueError as error:
            raise Stop(f"Could not use your time zone: {error}. No page was made, and no time zone was guessed.") from None
        if as_at:
            moment = pr.parse_time(as_at)
            if moment is None:
                raise Stop(f"--as-at needs a date and time with its offset, such as 2026-10-30T09:00:00+13:00, not {as_at!r}.")
        else:
            moment = dt.datetime.now(dt.timezone.utc)
        # A page made as at an earlier moment leaves out records made after it, so it shows what stood then.
        self.cutoff = moment if as_at else None
        # With no Time zone line, today is this computer's date and each record keeps the date it was written with.
        self.zone = zone or dt.datetime.now().astimezone().tzinfo
        self.now = moment.astimezone(self.zone)
        self.today = self.now.date()
        self.owners = {name_key(name) for name in owners if name.strip()} | OWNER_WORDS

        projects, project_issues, self.unlabelled = pr.scan_projects(pace)
        self.projects = {entry["id"]: entry for entry in projects}
        record_dir = pace / pr.RECORD_DIR
        if not record_dir.is_dir():
            raise Stop(f"{pr.RECORD_DIR}/ was not found in {pace}, so there is nothing to make an overview from.")
        try:
            names, copies, name_issues = pr.scan_record_names(record_dir)
        except OSError as error:
            raise Stop(f"{pr.RECORD_DIR}/ could not be listed ({error}), so no overview was made.") from None
        self.names = names
        self.items, self.problems, self.notes, self.left_out = {}, [], [], 0
        for issue in project_issues + name_issues:
            note = self._leftover_copy(record_dir, issue)
            if note:
                self.notes.append(note)  # nothing is missing, so the page is not partial
            else:
                self.problems.append(issue["message"])
        for stem, name in sorted(names.items()):
            item = pr.load(record_dir, name)
            if item["state"] in ("readable", "invalid"):
                if self.cutoff and self.made_after(stem, item):
                    self.left_out += 1
                    continue
                self.items[stem] = item
                if item["state"] == "invalid":
                    self.problems.append(pr.problem_issue(item)["message"])
            elif item["state"] == "missing":
                self.problems.append(f"{pr.RECORD_DIR}/{name} was listed but had gone when opened.")
            else:
                self.problems.append(pr.problem_issue(item)["message"])
        for request, name in copies:
            self.problems.append(pr.copy_issue(request, name)["message"])
        self.files_in_record = len(names)  # second copies are named in problems, never opened as records
        self.chains = self._chains()
        self._facts = self._project_facts()  # read once, so every view names the same problems

    @staticmethod
    def _leftover_copy(record_dir: Path, issue: dict) -> str:
        """A note when a save's temporary file is a leftover copy of a record that saved and reads the same, else "".

        Such a file holds nothing the record does not, so it is housekeeping rather than something not read. A temporary
        file with no saved record beside it, or one that differs, may be a save that did not finish, so it stays a problem."""
        if issue.get("type") != "unfinished-save":
            return ""
        name = issue.get("file", "")
        parts = name[len(pr.TEMP_PREFIX):].rsplit("-", 2)
        if not name.startswith(pr.TEMP_PREFIX) or len(parts) != 3 or not pr.REQUEST.match(parts[0]):
            return ""
        saved = record_dir / f"{parts[0]}.md"
        try:
            same = saved.is_file() and saved.read_bytes() == (record_dir / name).read_bytes()
        except OSError:
            return ""
        if not same:
            return ""
        return (f"{pr.RECORD_DIR}/{name} is a leftover copy of {pr.RECORD_DIR}/{parts[0]}.md from a save that finished; the "
                f"record reads the same. {pr.TEMP_NOTE}")

    def made_after(self, stem: str, item: dict) -> bool:
        moment = pr.parse_time(pr.one(item["fields"], "created")) or pr.request_time(stem)
        return moment > self.cutoff

    # Records and their corrections

    def field(self, stem: str, key: str) -> str:
        return pr.one(self.items[stem]["fields"], key)

    def day(self, stem: str) -> dt.date | None:
        moment = pr.parse_time(self.field(stem, "created"))
        if moment is None:
            return None
        if not self.zone_name:
            return moment.date()
        try:
            return moment.astimezone(self.zone).date()
        except (OverflowError, ValueError):  # a moment at the very edge of the calendar
            return moment.date()

    def _chains(self) -> list:
        """Each item's story: the record it starts from and the accounts that stand now.

        More than one account standing is "recorded two ways". A story whose first record is missing or could
        not be read here is still one item, and the missing record is named. Corrections that loop are named,
        and the accounts in the loop are shown as competing, since none of them can be taken as current."""
        later: dict = {}
        for stem in self.items:
            earlier = self.field(stem, "corrects")
            if earlier:
                later.setdefault(earlier, []).append(stem)
        groups: dict = {}
        loops: dict = {}
        missing: dict = {}
        for stem in sorted(self.items):
            path, node = [stem], stem
            while True:
                earlier = self.field(node, "corrects")
                if not earlier:
                    root = node
                    break
                if earlier in path:
                    cycle = path[path.index(earlier):]
                    root = min(cycle)
                    loops.setdefault(root, set()).update(cycle)
                    break
                if earlier not in self.items:
                    root = earlier
                    if earlier not in self.names:
                        missing.setdefault(earlier, set()).add(node)
                    break
                path.append(earlier)
                node = earlier
            groups.setdefault(root, set()).add(stem)
        for earlier, pointers in sorted(missing.items()):
            self.problems.append(f"{pr.RECORD_DIR}/{', '.join(f'{p}.md' for p in sorted(pointers))} "
                                 f"{'corrects' if len(pointers) == 1 else 'correct'} {earlier}, but no file for it is in "
                                 f"{pr.RECORD_DIR}/ here.")
        for root, cycle in sorted(loops.items()):
            if len(cycle) > 1:
                self.problems.append(f"The corrections in {pr.RECORD_DIR}/ loop: {', '.join(sorted(cycle))} correct each other, "
                                     "so none of them can be taken as the current account.")
        chains = []
        for root, members in sorted(groups.items()):
            leaves = [node for node in sorted(members) if not any(child in members for child in later.get(node, []))]
            if not leaves:  # every account is in the loop
                leaves = sorted(loops.get(root, members))
            current = [node for node in leaves if self.field(node, "kind") != "withdrawal"]
            chains.append({"first": root, "current": current})
        return chains

    # Projects

    def project_of(self, stem: str) -> str:
        return self.field(stem, "project") or pr.NO_PROJECT

    def parent_of(self, pid: str) -> str:
        parent = (self.projects.get(pid) or {}).get("parent") or ""
        return "" if parent in ("", pr.NO_PROJECT) else parent

    def ancestors(self, pid: str) -> list:
        """The projects above this one, nearest first, at any depth. Stops at an unknown parent or a loop."""
        chain, seen = [], {pid}
        parent = self.parent_of(pid)
        while parent and parent not in seen:
            chain.append(parent)
            seen.add(parent)
            parent = self.parent_of(parent)
        return chain

    def name_of(self, pid: str) -> str:
        if pid in self.projects:
            return self.projects[pid]["name"]
        return "No project" if pid == pr.NO_PROJECT else f"{pid} (no project folder)"

    def label(self, pid: str) -> str:
        """A project's name after the names of the projects above it, as plain text: Kowhai Books > Budget 2027."""
        return " > ".join([self.name_of(above) for above in reversed(self.ancestors(pid))] + [self.name_of(pid)])

    def trail_html(self, pids) -> str:
        return TRAIL.join(esc(self.name_of(pid)) for pid in pids)

    def ref_label(self, pid: str) -> str:
        return self.trail_html(list(reversed(self.ancestors(pid))) + [pid])

    def children_of(self, pid: str) -> list:
        return sorted((child for child in self.projects if self.parent_of(child) == pid), key=self.name_of)

    def family(self, pid: str) -> list:
        """The project and every project inside it, at any depth, each before the projects inside it."""
        out, seen = [], set()

        def visit(node):
            if node in seen:
                return
            seen.add(node)
            out.append(node)
            for child in self.children_of(node):
                visit(child)

        visit(pid)
        return out

    def facts(self) -> dict:
        return self._facts

    def _project_facts(self) -> dict:
        """Each project's owner, target and status, from its change records.

        For each, the latest change that sets it stands, by when its story began, so correcting an earlier
        change fixes that change without making it the newest. "none" clears one. When a change is recorded
        two ways and its accounts give different values, that value is "recorded two ways" until the owner
        says which stands. A target that is not a real date is not used, and is named as a problem."""
        facts: dict = {}
        for chain in sorted(self.chains, key=lambda chain: chain["first"]):
            current = chain["current"]
            kinds = [self.field(stem, "kind") for stem in current]
            if "change" not in kinds:
                continue
            pid = self.project_of(current[0])
            if pid == pr.NO_PROJECT:
                continue
            for key in pr.PROJECT_FIELDS:
                values = []
                for stem, kind in zip(current, kinds):
                    value = self.field(stem, key) if kind == "change" else ""
                    if key == "target" and value and value != pr.NO_PROJECT and not pr.parse_date(value):
                        self.problems.append(f"{pr.RECORD_DIR}/{stem}.md gives the target {value!r}, which is not a real "
                                             "date, so it was not used.")
                        value = ""
                    values.append(value)
                if not any(values):
                    continue
                if len(set(values)) > 1:
                    facts.setdefault(pid, {})[key] = {"two_ways": True}
                elif values[0] == pr.NO_PROJECT:
                    facts.setdefault(pid, {})[key] = None
                else:
                    facts.setdefault(pid, {})[key] = {"value": values[0], "day": self.day(current[0]), "request": current[0]}
        return {pid: {key: fact for key, fact in found.items() if fact} for pid, found in facts.items()}

    def last_recorded(self, pids) -> dt.date | None:
        days = [self.day(stem) for stem in self.items if self.project_of(stem) in pids]
        days = [day for day in days if day]
        return max(days) if days else None

    # Work

    def is_owner(self, name: str) -> bool:
        return name_key(name) in self.owners

    def entry(self, stem: str) -> dict:
        due = pr.parse_date(self.field(stem, "due"))
        subjects = self.items[stem]["fields"].get("subject") or []
        return {"request": stem, "project": self.project_of(stem), "subject": subjects[0] if subjects else "Subject not recorded",
                "text": plain(self.items[stem]["body"]), "due": due, "owed": self.field(stem, "owed-by"),
                "for": self.field(stem, "for"), "state": self.field(stem, "state"), "kind": self.field(stem, "kind"),
                "from": self.field(stem, "from"), "who": self.field(stem, "who"), "day": self.day(stem)}

    def work(self, pids=None) -> dict:
        """Open work, recorded-two-ways items and recent records for these projects (all when None)."""
        wanted = (lambda pid: True) if pids is None else (lambda pid: pid in pids)
        out = {"open": [], "two_ways": [], "done": [], "cancelled": [], "decisions": [], "changes": [], "notes": []}
        since = self.today - dt.timedelta(days=RECENT_DAYS)
        for chain in self.chains:
            current = [stem for stem in chain["current"] if wanted(self.project_of(stem))]
            if not current:
                continue
            if len(chain["current"]) > 1:
                out["two_ways"].append([self.entry(stem) for stem in chain["current"]])
                continue
            item = self.entry(current[0])
            item["first"] = chain["first"]
            recent = item["day"] is not None and item["day"] >= since
            if item["kind"] == "action" and item["state"] not in ("done", "cancelled"):
                out["open"].append(item)
            elif item["kind"] == "action" and recent:
                out[item["state"]].append(item)
            elif item["kind"] == "decision" and recent:
                out["decisions"].append(item)
            elif item["kind"] == "change" and recent:
                out["changes"].append(item)
            elif item["kind"] in ("note", "person-note") and recent:
                out["notes"].append(item)
        for key in ("done", "cancelled", "decisions", "changes", "notes"):
            out[key].sort(key=lambda item: item["request"], reverse=True)
        out["open"].sort(key=self.order)
        return out

    def order(self, item: dict):
        """Overdue first, the longest late first; then due today; then by due date; then no due date, oldest first.

        Oldest means first recorded: an item keeps its place when it is corrected."""
        first = item.get("first") or item["request"]
        if item["due"] is None:
            return (2, dt.date.max, first, item["request"])
        return (0 if item["due"] <= self.today else 1, item["due"], first, item["request"])

    def counts(self, items: list, two_ways: list) -> dict:
        today, soon = self.today, self.today + dt.timedelta(days=SOON_DAYS)
        return {
            "overdue": sum(1 for item in items if item["due"] and item["due"] < today),
            "due_today": sum(1 for item in items if item["due"] == today),
            "due_next_7_days": sum(1 for item in items if item["due"] and today < item["due"] <= soon),
            "waiting_on_you": sum(1 for item in items if self.is_owner(item["owed"])),
            "waiting_on_others": sum(1 for item in items if item["owed"] and not self.is_owner(item["owed"])),
            "no_person_named": sum(1 for item in items if not item["owed"]),
            "no_due_date": sum(1 for item in items if item["due"] is None),
            "open": len(items),
            "recorded_two_ways": len(two_ways),
        }

    def needs_attention(self, items: list) -> list:
        soon = self.today + dt.timedelta(days=SOON_DAYS)
        return [item for item in items if item["due"] and item["due"] <= soon]

    def age(self, item: dict) -> int | None:
        """Whole days since the item was first recorded, or None when that day is not known or is after today."""
        first = item.get("first") or item["request"]
        day = self.day(first) if first in self.items else item["day"]
        return (self.today - day).days if day and day <= self.today else None

    def week(self, pids=None) -> dict:
        """Actions in the last 7 days, today included: first recorded, done, cancelled, or with a different due date.

        Each item's current account is compared with how it stood before the 7 days, its latest account saved before
        them: it is done (or cancelled) in them when it is so now and was not then, and its due date changed when it
        differs now from then. An item first recorded in them is new. Work recorded two ways is left out."""
        wanted = (lambda pid: True) if pids is None else (lambda pid: pid in pids)
        since = self.today - dt.timedelta(days=WEEK_DAYS - 1)
        out = {"new": [], "done": [], "cancelled": [], "moved": []}
        for chain in self.chains:
            if len(chain["current"]) != 1:
                continue
            stem = chain["current"][0]
            if not wanted(self.project_of(stem)) or self.field(stem, "kind") != "action":
                continue
            path, node = [stem], stem  # the accounts from the current one back, newest first
            while True:
                earlier = self.field(node, "corrects")
                if not earlier or earlier not in self.items or earlier in path:
                    break
                path.append(earlier)
                node = earlier
            days = {account: self.day(account) for account in path}
            if not any(day and since <= day <= self.today for day in days.values()):
                continue  # nothing about it was saved in the 7 days
            before = next((account for account in path if days[account] and days[account] < since), None)
            item = self.entry(stem)
            item["first"] = chain["first"]
            first_day = self.day(chain["first"]) if chain["first"] in self.items else None
            if first_day and since <= first_day <= self.today:
                out["new"].append(item)
            then = self.field(before, "state") if before else ""
            if item["state"] in ("done", "cancelled"):
                if then != item["state"]:
                    out[item["state"]].append(item)
                continue
            if before and pr.parse_date(self.field(before, "due")) != item["due"]:
                item["was"] = pr.parse_date(self.field(before, "due"))
                out["moved"].append(item)
        for key in out:
            out[key].sort(key=self.order)
        return out


# ---------------------------------------------------------------- page parts
#
# Every list on the page is one line per item: when it is due (or how long it has waited), what it is, and where. Opening
# a line shows the record's own words. Projects are rows that open: a project with projects inside it is open on the
# page, so every project's row shows, and each row opens to its own work. Nothing here adds a judgement the records do
# not hold; how late, how soon and how long are worked out from the dates.

def plural(count: int, word: str, words: str = "") -> str:
    return f"{count} {word if count == 1 else (words or word + 's')}"


def short_day(day: dt.date, today: dt.date) -> str:
    """A date for a narrow column: 4 Nov, with the year when it is not this year's."""
    return f"{day.day} {day:%b}" + ("" if day.year == today.year else f" {day.year}")


def someone_else(folder: Folder, name: str) -> bool:
    return bool(name) and not folder.is_owner(name)


def person(folder: Folder, name: str) -> str:
    return "you" if folder.is_owner(name) else esc(name)


def due_tag(folder: Folder, due: dt.date) -> str:
    today = folder.today
    if due < today:
        return f'<span class="tag late">{how_soon(due, today)}</span>'
    if due == today:
        return '<span class="tag today">Today</span>'
    if (due - today).days <= SOON_DAYS:
        return f'<span class="tag soon">{how_soon(due, today).capitalize()}</span>'
    return f'<span class="tag">{short_day(due, today)}</span>'


def tag(folder: Folder, item: dict) -> str:
    """The line's first column: done or cancelled, how late or soon it is due, or how long undated work has waited."""
    if item["state"] in ("done", "cancelled"):
        return f'<span class="tag">{item["state"].capitalize()}</span>'
    if item["due"]:
        return due_tag(folder, item["due"])
    age = folder.age(item)
    if age is not None and age >= AGE_DAYS:
        word = "Waiting" if someone_else(folder, item["owed"]) else "Open"
        return f'<span class="tag age">{word} {days_word(age)}</span>'
    return '<span class="tag"></span>'


def meta_text(folder: Folder, item: dict) -> str:
    parts = [f"Owed by {person(folder, item['owed'])}" if item["owed"] else "No person named"]
    if item["for"]:
        parts.append(f"for {person(folder, item['for'])}")
    parts.append(f"due {short_date(item['due'])}" if item["due"] else "no due date")
    parts.append(esc(item["state"] or "state not recorded"))
    return DOT.join(parts)


def item_row(folder: Folder, item: dict, side: str = "", by: bool = True, jump: str = "") -> list:
    """One open item as one line, its record's own words and who, when and its state inside.

    `jump`, when given, is the id of its project's row; the link to it sits inside the opened line, never in the line
    itself, which is already a control that opens and closes."""
    owed = f'<span class="by">{DOT}{esc(item["owed"])}</span>' if by and someone_else(folder, item["owed"]) else ""
    text = f'<p class="text">{esc(item["text"])}</p>' if item["text"] else ""
    go = f'<p class="go"><a class="jump" href="#{jump}">Go to {side or "its row"}</a></p>' if jump else ""
    return ['<li class="item"><details class="row">',
            f'<summary>{tag(folder, item)}<span class="subj">{esc(item["subject"])}{owed}</span><span class="side">{side}</span></summary>',
            f'<div class="more">{text}<p class="meta">{meta_text(folder, item)}</p>{go}</div>',
            "</details></li>"]


def record_row(label: str, item: dict, side: str, meta: str) -> list:
    text = f'<p class="text">{esc(item["text"])}</p>' if item["text"] else ""
    return ['<li class="item"><details class="row">',
            f'<summary><span class="tag">{label}</span><span class="subj">{esc(item["subject"])}</span><span class="side">{side}</span></summary>',
            f'<div class="more">{text}<p class="meta">{meta}</p></div>',
            "</details></li>"]


def rows(lines: list) -> list:
    return ['<ul class="rows">'] + lines + ["</ul>"]


def trail(folder: Folder, pid: str, below: str = "") -> str:
    """A project's name after the projects above it, starting below `below` when that is one of them."""
    chain = list(reversed(folder.ancestors(pid))) + [pid]
    if below in chain:
        chain = chain[chain.index(below) + 1:] or [pid]
    return folder.trail_html(chain)


def anchor(pid: str, own: bool = False) -> str:
    """The id of a project's row on the page; a project id never holds two hyphens together, so these never clash."""
    return f"p-{pid}--own" if own else f"p-{pid}"


def by_owner(folder: Folder, items: list) -> list:
    """Open items split into you, each other person by name (as first written), and no person named, each in order."""
    groups: dict = {}
    for item in items:
        if folder.is_owner(item["owed"]):
            key, heading = ("0", ""), "With you"
        elif item["owed"]:
            key, heading = ("1", name_key(item["owed"])), f"With {esc(plain(item['owed']))}"
        else:
            key, heading = ("2", ""), "No person named"
        groups.setdefault(key, [heading, []])[1].append(item)
    return [groups[key] for key in sorted(groups)]


def work_lines(folder: Folder, items: list, side=lambda item: "") -> list:
    """A project's own open work, under who owes it when that is anyone but the owner alone."""
    groups = by_owner(folder, items)
    if not groups:
        return ['<p class="none">No open work recorded.</p>']
    lines = []
    for heading, chosen in groups:
        if len(groups) > 1 or heading != "With you":
            lines.append(f'<p class="group">{heading}</p>')
        rows_ = []
        for item in chosen:
            rows_ += item_row(folder, item, side(item), by=False)
        lines += rows(rows_)
    return lines


def summary_lines(folder: Folder, counts: dict, projects: int) -> list:
    """Three counts that say how urgent things are, then one line for the rest."""
    lines = ['<div class="summary">']
    for key, words in (("overdue", "overdue"), ("due_today", "due today"), ("due_next_7_days", f"due in the next {SOON_DAYS} days")):
        number = counts[key]
        kind = "stat" + (" hot" if key == "overdue" and number else "") + ("" if number else " zero")
        lines.append(f'<p class="{kind}"><strong>{number}</strong> {words}</p>')
    lines.append("</div>")
    if counts["open"]:
        who = f"{counts['waiting_on_you']} with you, {counts['waiting_on_others']} with others"
        if counts["no_person_named"]:
            who += f", {counts['no_person_named']} with no one named"
        line = (f"{counts['open']} open in {plural(projects, 'project')}{DOT}{who}{DOT}"
                f"{counts['no_due_date']} with no due date")
    else:
        line = "No open work recorded."
    if counts["recorded_two_ways"]:
        line += f"{DOT}{counts['recorded_two_ways']} recorded two ways"
    return lines + [f'<p class="sub">{line}</p>']


WEEK_PARTS = (("new", "new", "new", "New"), ("done", "done", "done", "Done"), ("cancelled", "cancelled", "cancelled", "Cancelled"),
              ("moved", "due date changed", "due dates changed", "Due date changed"))


def week_lines(folder: Folder, week: dict, below: str = "") -> list:
    """What happened in the last 7 days, as one line that opens to the items."""
    shown = [(key, one, many, heading) for key, one, many, heading in WEEK_PARTS if week[key]]
    if not shown:
        return [f'<p class="week">Last {WEEK_DAYS} days: nothing new, done, cancelled or with a changed due date.</p>']
    said = DOT.join(f"<strong>{len(week[key])}</strong> {one if len(week[key]) == 1 else many}" for key, one, many, _ in shown)
    lines = ['<details class="week">', f"<summary>Last {WEEK_DAYS} days: {said}</summary>", '<div class="body">']
    for key, _, _, heading in shown:
        found = []
        for item in week[key]:
            side = trail(folder, item["project"], below)
            if key == "moved":
                side += f"{DOT}was {short_day(item['was'], folder.today) if item['was'] else 'no date'}"
            found += item_row(folder, item, side)
        lines += [f'<p class="group">{heading}</p>'] + rows(found)
    return lines + ["</div>", "</details>"]


def two_ways_lines(folder: Folder, groups: list, below: str = "") -> list:
    if not groups:
        return []
    lines = ['<section class="part two-ways">', f'<h2>Recorded two ways <span class="n">{len(groups)}</span></h2>',
             '<p class="lede">Each of these has two current accounts. Ask the owner which stands.</p>', '<ul class="rows">']
    for accounts in groups:
        first = accounts[0]
        lines += ['<li class="pair">', f'<p><strong>{esc(first["subject"])}</strong> <span class="side">{trail(folder, first["project"], below)}</span></p>',
                  '<ol class="accounts">']
        for item in accounts:
            lines += ['<li class="item">', f'<p class="text">{esc(item["text"])}</p>', f'<p class="meta">{meta_text(folder, item)}</p>', "</li>"]
        lines += ["</ol>", "</li>"]
    return lines + ["</ul>", "</section>"]


def attention_lines(folder: Folder, items: list, below: str = "", targets: dict | None = None) -> list:
    """Overdue, due today and due in the next 7 days, each line naming its project, which jumps to its row when shown."""
    chosen, found = folder.needs_attention(items), []
    for item in chosen:
        where = "" if below and item["project"] == below else trail(folder, item["project"], below)
        found += item_row(folder, item, where, jump=(targets or {}).get(item["project"], ""))
    lines = ['<section class="part">', f'<h2>Needs attention <span class="n">{len(chosen)}</span></h2>']
    if chosen:
        return lines + rows(found) + ["</section>"]
    return lines + [f'<p class="none">Nothing is overdue or due in the next {SOON_DAYS} days.</p>', "</section>"]


def pressing(folder: Folder, items: list, pid: str):
    mine = [item for item in items if item["project"] == pid]
    dated = [item["due"] for item in mine if item["due"]]
    overdue = sum(1 for day in dated if day < folder.today)
    return (-overdue, min(dated) if dated else dt.date.max, -len(mine), folder.name_of(pid).casefold())


def project_tree(folder: Folder, items: list, extra=()) -> tuple:
    """The projects to show and how they nest, at any depth.

    Shown: each project with open work, each in `extra` (a target or status with no open work), and every project
    above one of them. Returns (tops, kids, tree, listed): the projects at the top, most pressing first; each shown
    project's projects inside it, most pressing first; every project shown; and those with work, a target or a status.
    Most pressing means the most overdue, then the earliest due date, then the most open work, judged by the work
    anywhere inside a project; ties go by name, then id. Projects whose parents loop are shown at the top rather than
    lost."""
    listed = set(item["project"] for item in items) | set(extra)
    tree = set(listed)
    for pid in sorted(listed):
        tree.update(folder.ancestors(pid))
    top = None  # never a project id
    inside: dict = {}
    for pid in sorted(tree):
        parent = folder.parent_of(pid)
        inside.setdefault(parent if parent in tree and parent != pid else top, []).append(pid)
    reached: set = set()

    def reach(pid):
        if pid not in reached:
            reached.add(pid)
            for child in inside.get(pid, []):
                reach(child)

    for pid in inside.get(top, []):
        reach(pid)
    for pid in sorted(tree):
        if pid not in reached:  # its parents loop, so no top leads to it
            inside.setdefault(top, []).append(pid)
            reach(pid)
    best: dict = {}

    def most_pressing(pid, path=frozenset()):
        if pid not in best:
            children = [child for child in inside.get(pid, []) if child not in path and child != pid]
            best[pid] = min([pressing(folder, items, pid)] + [most_pressing(child, path | {pid}) for child in children])
        return best[pid]

    def side_by_side(pid):
        return (most_pressing(pid), folder.label(pid).casefold(), pid)

    kids, seen = {}, set()

    def place(pid):
        if pid in seen:
            return
        seen.add(pid)
        kids[pid] = [child for child in sorted(inside.get(pid, []), key=side_by_side) if child not in seen and child != pid]
        for child in kids[pid]:
            place(child)
        kids[pid] = [child for child in kids[pid] if kids.get(child) is not None]

    tops = sorted(inside.get(top, []), key=side_by_side)
    for pid in tops:
        place(pid)
    return tops, kids, tree, listed


def inside_of(pid: str, kids: dict) -> list:
    """The project and every shown project inside it, each before the projects inside it."""
    out, stack = [], [pid]
    while stack:
        node = stack.pop()
        if node in out:
            continue
        out.append(node)
        stack.extend(reversed(kids.get(node, [])))
    return out


def fact_text(folder: Folder, key: str, fact) -> str:
    if not fact:
        return "Not recorded"
    if fact.get("two_ways"):
        return "Recorded two ways"
    if key == "owner":
        return "You" if folder.is_owner(fact["value"]) else esc(fact["value"])
    if key == "target":
        day = pr.parse_date(fact["value"])
        return f"{short_date(day)}, {how_soon(day, folder.today)}" if day else esc(fact["value"])
    when = f"{DOT}{short_date(fact['day'])}" if fact.get("day") else ""
    return f"{esc(fact['value'])}{when}"


def target_late(folder: Folder, fact) -> bool:
    day = pr.parse_date(fact["value"]) if fact and not fact.get("two_ways") else None
    return bool(day and day < folder.today)


def last_text(folder: Folder, pids) -> str:
    day = folder.last_recorded(set(pids))
    if day is None:
        return "Not recorded"
    return short_day(day, folder.today) if day > folder.today else how_long_ago(day, folder.today).capitalize()


def lead_text(folder: Folder, mine: list, pid: str) -> str:
    """The row's second line: its most pressing open item, where it is and who owes it when not the owner."""
    if not mine:
        return "No open work recorded"
    first = mine[0]
    parts = [esc(first["subject"])]
    if first["project"] != pid:
        parts.append(trail(folder, first["project"], pid))
    if someone_else(folder, first["owed"]):
        parts.append(esc(first["owed"]))
    if not first["due"]:
        age = folder.age(first)
        if age is not None and age >= AGE_DAYS:
            parts.append(f"open {days_word(age)}")
    return ("Next: " if first["due"] else "Oldest open: ") + DOT.join(parts)


def node_summary(folder: Folder, pid: str, label: str, mine: list, pids: list, own: bool = False) -> str:
    """A row's line: the project, its status, owner and target, what is next, its open count, next due date and last record.
    The row of a project's own work (`own`) leaves out the project's facts, which its parent row gives."""
    facts = {} if own else folder.facts().get(pid, {})
    bits = [f'<span class="pname">{label}</span>']
    if facts.get("status"):
        bits.append(f'<span class="status">{fact_text(folder, "status", facts["status"])}</span>')
    known = []
    if facts.get("owner"):
        known.append(f"Owner {fact_text(folder, 'owner', facts['owner'])}")
    if facts.get("target"):
        late = ' class="late"' if target_late(folder, facts["target"]) else ""
        known.append(f"Target <span{late}>{fact_text(folder, 'target', facts['target'])}</span>")
    if known:
        bits.append(f'<span class="fact">{DOT.join(known)}</span>')
    bits.append(f'<span class="next">{lead_text(folder, mine, pid)}</span>')
    dated = [item["due"] for item in mine if item["due"]]
    due = due_tag(folder, min(dated)) if dated else f'<span class="tag empty">{"No date" if mine else "None"}</span>'
    return (f'<summary><span class="label">{"".join(bits)}</span><span class="num">{len(mine)}</span>'
            f'<span class="due">{due}</span><span class="last">{last_text(folder, pids)}</span></summary>')


def node_lines(folder: Folder, pid: str, items: list, kids: dict) -> list:
    """A project as a row that opens. One with projects inside it is open, so their rows show; its own work is a row of
    its own, named after it; every other row opens to its own work."""
    children = kids.get(pid, [])
    pids = inside_of(pid, kids)
    mine = sorted((item for item in items if item["project"] in pids), key=folder.order)
    own = [item for item in mine if item["project"] == pid]
    ident = f' id="{anchor(pid)}"' if pr.PROJECT_ID.match(pid) else ""
    if not children:
        return ([f'<details class="node"{ident}>', node_summary(folder, pid, esc(folder.name_of(pid)), mine, folder.family(pid)),
                 '<div class="body">'] + work_lines(folder, own) + ["</div>", "</details>"])
    lines = [f'<details class="node parent"{ident} open>', node_summary(folder, pid, esc(folder.name_of(pid)), mine, folder.family(pid)),
             '<div class="body">']
    if own:
        own_ident = f' id="{anchor(pid, own=True)}"' if pr.PROJECT_ID.match(pid) else ""
        name = f'{esc(folder.name_of(pid))} <span class="itself">itself</span>'
        lines += ([f'<details class="node own"{own_ident}>', node_summary(folder, pid, name, own, [pid], own=True), '<div class="body">']
                  + work_lines(folder, own) + ["</div>", "</details>"])
    for child in children:
        lines += node_lines(folder, child, items, kids)
    return lines + ["</div>", "</details>"]


def jump_targets(items: list, kids: dict, shown) -> dict:
    """Where a Needs attention line jumps: its project's row, or the row of the project's own work when it has projects inside."""
    targets = {}
    for pid in set(item["project"] for item in items) & set(shown):
        if pr.PROJECT_ID.match(pid):
            targets[pid] = anchor(pid, own=bool(kids.get(pid)))
    return targets


HEADS = ('<div class="heads"><span></span><span>{first}</span><span class="num">{count}</span><span>Next due</span>'
         '<span>{last}</span></div>')


def every_project_view(folder: Folder) -> dict:
    work = folder.work()
    items, counts = work["open"], folder.counts(work["open"], work["two_ways"])
    tracked = [pid for pid, found in folder.facts().items() if found.get("target") or found.get("status")]
    tops, kids, tree, listed = project_tree(folder, items, tracked)
    # A project above one shown is shown, and work recorded two ways is in that section, so none of them, nor the
    # projects above work recorded two ways, is listed as having no open work.
    disputed = set()
    for accounts in work["two_ways"]:
        if any(item["kind"] == "action" for item in accounts):
            for item in accounts:
                disputed |= {item["project"], *folder.ancestors(item["project"])}
    idle = sorted((pid for pid in folder.projects if pid not in tree and pid not in disputed),
                  key=lambda pid: folder.label(pid).casefold())

    lines = ["<!-- start: every project view -->", '<section class="view">']
    lines += summary_lines(folder, counts, len(set(item["project"] for item in items)))
    week = folder.week()
    lines += week_lines(folder, week)
    lines += two_ways_lines(folder, work["two_ways"])
    lines += attention_lines(folder, items, targets=jump_targets(items, kids, tree))
    lines += ['<section class="part">', f'<h2>Projects <span class="n">{len(listed)} with open work, a target or a status</span></h2>']
    if tops:
        lines.append(HEADS.format(first="Project and what is next", count="Open", last="Last activity"))
        for pid in tops:
            lines += node_lines(folder, pid, items, kids)
    else:
        lines.append('<p class="none">No project has open work recorded.</p>')
    if idle:
        lines.append(f'<p class="quiet">No open work recorded: {", ".join(folder.ref_label(pid) for pid in idle)}.</p>')
    if folder.unlabelled:
        lines.append(f'<p class="quiet">Folders with no Pace project.md: {esc(", ".join(folder.unlabelled))}. '
                     "Ask the owner what each one is.</p>")
    lines += ["</section>", "</section>", "<!-- end: every project view -->"]
    return {"head": [], "lines": lines, "work": work, "counts": counts, "week": week, "heading": "All projects",
            "title": "Project overview", "suffix": ""}


def one_project_view(folder: Folder, pid: str) -> dict:
    if pid not in folder.projects:
        raise Stop(f"No project with id {pid!r} is in {pr.PROJECTS_DIR}/. List them with the record tool's projects command."
                   f"{pr.old_folder_names(folder.pace)}")
    family = folder.family(pid)
    work = folder.work(set(family))
    items, counts = work["open"], folder.counts(work["open"], work["two_ways"])
    entry = folder.projects[pid]
    above = list(reversed(folder.ancestors(pid)))
    found = folder.facts().get(pid, {})
    facts = []
    if above:
        facts.append(f"Part of <strong>{folder.trail_html(above)}</strong>")
    for key, word in (("owner", "Owner"), ("target", "Target"), ("status", "Status")):
        if found.get(key):
            late = ' class="late"' if key == "target" and target_late(folder, found[key]) else ""
            facts.append(f"{word} <strong{late}>{fact_text(folder, key, found[key])}</strong>")
    facts.append(f"Last recorded <strong>{day_and_age(folder.last_recorded(set(family)), folder.today)}</strong>")
    head = [f'<p class="lead">{esc(plain(entry.get("purpose", "")) or "Purpose not recorded")}</p>',
            '<p class="known">' + "".join(f"<span>{fact}</span>" for fact in facts) + "</p>"]

    # The rows show when a project inside this one has open work, a target or a status.
    tracked = [child for child in family if folder.facts().get(child, {}).get("target") or folder.facts().get(child, {}).get("status")]
    _, kids, tree, listed = project_tree(folder, items, tracked)
    shown = set(inside_of(pid, kids)) if pid in tree else {pid}
    disputed = set()
    for accounts in work["two_ways"]:
        if any(item["kind"] == "action" for item in accounts):
            for item in accounts:
                disputed |= {item["project"], *folder.ancestors(item["project"])}
    lines = ["<!-- start: one project view -->", '<section class="view">']
    lines += summary_lines(folder, counts, len(set(item["project"] for item in items)))
    week = folder.week(set(family))
    lines += week_lines(folder, week, pid)
    lines += two_ways_lines(folder, work["two_ways"], pid)
    if kids.get(pid):
        targets = jump_targets(items, kids, shown)
        lines += attention_lines(folder, items, pid, targets)
        idle = [child for child in family[1:] if child not in shown and child not in disputed]
        inside = len((set(listed) & set(family)) - {pid})
        lines += ['<section class="part">', f'<h2>Projects <span class="n">{inside} inside with open work, a target or a status</span></h2>',
                  HEADS.format(first="Project and what is next", count="Open", last="Last activity")]
        own = sorted((item for item in items if item["project"] == pid), key=folder.order)
        if own:
            name = f'{esc(folder.name_of(pid))} <span class="itself">itself</span>'
            lines += ([f'<details class="node own" id="{anchor(pid, own=True)}">', node_summary(folder, pid, name, own, [pid], own=True),
                       '<div class="body">'] + work_lines(folder, own) + ["</div>", "</details>"])
        for child in kids[pid]:
            lines += node_lines(folder, child, items, kids)
        if idle:
            lines.append(f'<p class="quiet">No open work recorded: {", ".join(trail(folder, child, pid) for child in idle)}.</p>')
        lines.append("</section>")
    else:
        lines += attention_lines(folder, items, pid)
        idle = [child for child in family[1:] if child not in disputed]
        lines += ['<section class="part">', f'<h2>Open work <span class="n">{len(items)}</span></h2>']
        lines += work_lines(folder, items, lambda item: trail(folder, item["project"], pid) if item["project"] != pid else "")
        if idle:
            lines.append(f'<p class="quiet">No open work recorded: {", ".join(trail(folder, child, pid) for child in idle)}.</p>')
        lines.append("</section>")

    def source(item):
        if item["from"] == "owner":
            return "From you"
        return f"From {esc(item['who'])}" if item["who"] else f"From: {esc(item['from'] or 'not recorded')}"

    recent = []
    for key, label in (("decisions", "Decided"), ("changes", "Changed"), ("done", "Done"), ("cancelled", "Cancelled"),
                       ("notes", "Note")):
        recent += [(item["request"], label, item) for item in work[key]]
    if recent:
        lines += ['<section class="part">', f'<h2>Last three weeks <span class="n">{len(recent)}</span></h2>']
        found_rows = []
        for _, label, item in sorted(recent, key=lambda entry: entry[0], reverse=True):
            when = short_date(item["day"]) if item["day"] else "Date not recorded"
            side = (trail(folder, item["project"], pid) + DOT if item["project"] != pid else "") + (
                short_day(item["day"], folder.today) if item["day"] else "")
            if label in ("Decided", "Changed"):
                meta = when + DOT + source(item)
            elif label in ("Done", "Cancelled"):
                meta = when + DOT + esc(item["state"])
            else:
                meta = when
            found_rows += record_row(label, item, side, meta)
        lines += rows(found_rows) + ["</section>"]
    places = []
    documents = folder.pace / entry["folder"] / pr.WORKING_DIR
    try:
        if documents.is_dir():
            places += sorted(pr.rel(folder.pace, path) for path in documents.iterdir() if path.name.lower() not in pr.IGNORED_NAMES)
    except OSError as error:
        folder.problems.append(f"{pr.rel(folder.pace, documents)} could not be listed ({error}).")
    # A project's own repository reference names it as the home; a link file names the project that uses it.
    repos = folder.pace / "Repos"
    if repos.is_dir():
        references = [(path, "Home") for path in repos.rglob("Pace repo.md")]
        references += [(path, "Using") for path in repos.rglob("Pace repo link.md")]
        for path, role in sorted(references):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as error:
                folder.problems.append(f"{pr.rel(folder.pace, path)} could not be read ({error}), so it may be a "
                                       "repository reference for this project that is not listed.")
                continue
            if re.search(rf"^{role} project id:\s*{re.escape(pid)}\s*$", text, re.M):
                places.append(pr.rel(folder.pace, path))
    lines += ['<section class="part refs">']
    if places:
        lines += ['<details class="files">', f'<summary>Documents and repository references <span class="n">{len(places)}</span></summary>',
                  '<ul class="files">'] + [f"<li>{esc(place)}</li>" for place in places] + ["</ul>", "</details>"]
    else:
        lines.append('<p class="quiet">Documents and repository references: none.</p>')
    lines += ["</section>", "</section>", "<!-- end: one project view -->"]
    return {"head": head, "lines": lines, "work": work, "counts": counts, "week": week, "heading": folder.name_of(pid),
            "title": folder.name_of(pid), "suffix": f"-{pid}"}


def by_person_view(folder: Folder) -> dict:
    work = folder.work()
    items, counts = work["open"], folder.counts(work["open"], work["two_ways"])
    people: dict = {}
    for item in items:
        for role, name in (("owes", item["owed"]), ("waits", item["for"])):
            if name:
                key = "you" if folder.is_owner(name) else name_key(name)
                people.setdefault(key, {"name": "You" if key == "you" else name.strip(), "owes": [], "waits": []})[role].append(item)
    order = sorted(people, key=lambda key: (key != "you", people[key]["name"].casefold()))
    anyone_waits = any(people[key]["waits"] for key in order)

    def for_side(item, below=""):
        where = trail(folder, item["project"], below) if item["project"] != below else ""
        if item["for"]:
            where += (DOT if where else "") + f"for {person(folder, item['for'])}"
        return where

    lines = ["<!-- start: by person view -->", '<section class="view">']
    lines += summary_lines(folder, counts, len(set(item["project"] for item in items)))
    week = folder.week()
    lines += week_lines(folder, week)
    lines += two_ways_lines(folder, work["two_ways"])
    lines += attention_lines(folder, items)
    lines += ['<section class="part">', f'<h2>People <span class="n">{len(order)}</span></h2>']
    if order:
        lines.append(HEADS.format(first="Person and what is next", count="Owes", last="Waiting for" if anyone_waits else ""))
    for key in order:
        found = people[key]
        owes = sorted(found["owes"], key=folder.order)
        waits = sorted(found["waits"], key=folder.order)
        dated = [item["due"] for item in owes if item["due"]]
        if owes:
            first = owes[0]
            parts = [esc(first["subject"]), trail(folder, first["project"])]
            lead = ("Next: " if first["due"] else "Oldest open: ") + DOT.join(parts)
        else:
            lead = "Owes nothing recorded"
        due = due_tag(folder, min(dated)) if dated else f'<span class="tag empty">{"No date" if owes else "None"}</span>'
        lines += [f'<details class="node person"{" open" if key == "you" else ""}>',
                  f'<summary><span class="label"><span class="pname">{esc(found["name"])}</span><span class="next">{lead}</span></span>'
                  f'<span class="num">{len(owes)}</span><span class="due">{due}</span><span class="last">{len(waits) or ""}</span></summary>',
                  '<div class="body">']
        owes_word = "You owe" if key == "you" else "Owes"
        with_dates = [item for item in owes if item["due"]]
        undated = [item for item in owes if not item["due"]]
        if with_dates:
            lines.append(f'<p class="group">{owes_word}, with a due date</p>')
            lines += rows([line for item in with_dates for line in item_row(folder, item, for_side(item), by=False)])
        if undated and len(owes) > FOLD_AFTER:
            # A long list folds its undated work by the project at the top of each item's folders.
            tops: dict = {}
            for item in undated:
                top = (list(reversed(folder.ancestors(item["project"]))) or [item["project"]])[0]
                tops.setdefault(top, []).append(item)
            for top, chosen in tops.items():
                lines += ['<details class="fold">', f'<summary>{owes_word}, with no due date: {esc(folder.name_of(top))} '
                          f'<span class="n">{len(chosen)}</span></summary>']
                lines += rows([line for item in chosen for line in item_row(folder, item, for_side(item, top), by=False)])
                lines.append("</details>")
        elif undated:
            lines.append(f'<p class="group">{owes_word}, with no due date</p>')
            lines += rows([line for item in undated for line in item_row(folder, item, for_side(item), by=False)])
        if waits:
            lines.append(f'<p class="group">{"You are waiting for" if key == "you" else "Waiting for"}</p>')
            lines += rows([line for item in waits for line in item_row(
                folder, item, trail(folder, item["project"]) + DOT + (f"from {person(folder, item['owed'])}" if item["owed"] else "no one named"),
                by=False)])
        lines += ["</div>", "</details>"]
    nobody = sorted((item for item in items if not item["owed"]), key=folder.order)
    if nobody:
        lines += ['<details class="node person">',
                  '<summary><span class="label"><span class="pname">No person named</span><span class="next">Open work that names no one who owes it</span></span>'
                  f'<span class="num">{len(nobody)}</span><span class="due"></span><span class="last"></span></summary>', '<div class="body">']
        lines += rows([line for item in nobody for line in item_row(folder, item, trail(folder, item["project"]))])
        lines += ["</div>", "</details>"]
    if not order and not nobody:
        lines.append('<p class="none">No open work recorded.</p>')
    lines += ["</section>", "</section>", "<!-- end: by person view -->"]
    return {"head": [], "lines": lines, "work": work, "counts": counts, "week": week, "heading": "By person",
            "title": "Project overview by person", "suffix": "-by-person"}


# ---------------------------------------------------------------- the page

def template_parts(text: str) -> dict:
    parts = {}
    for key, pattern in (("style", r"<style>.*?</style>"), ("wordmark", r'<svg class="wordmark".*?</svg>'),
                         ("footer", r'<footer class="foot">.*?</footer>')):
        match = re.search(pattern, text, re.S)
        if not match:
            raise Stop(f"The page template has no {key}, so it is not the Project overview template. No page was made.")
        parts[key] = match.group(0)
    return parts


# The styles a page of this design needs; a customised template whose style block has none of them predates it.
CURRENT_STYLES = (".node", ".row", ".tag", ".summary")


def build_page(folder: Folder, parts: dict, view: dict, title: str, asked: str, searched: str, could_not_read: str) -> str:
    """The page: the header with the as-at moment, the view, then what was asked and searched, then the template's footer."""
    lines = ["<!DOCTYPE html>", '<html lang="en-NZ">', "<head>", '<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta name="color-scheme" content="light dark">', f"<title>{esc(title)} - {PRODUCT_NAME}</title>",
             parts["style"], "</head>", "<body>", '<main class="page">', "", "<header>", '<div class="brand">',
             f'<p class="product">{PRODUCT_NAME}</p>', parts["wordmark"], "</div>", '<div class="title">',
             f"<h1>{esc(view['heading'])}</h1>", f'<p class="asat">As at {esc(long_moment(folder.now))}</p>', "</div>"]
    lines += view["head"]
    if folder.problems:
        lines.append('<p class="partial">Partial: some files could not be read. They are named under Could not read at the '
                     "end of this page.</p>")
    lines += ["</header>", ""] + view["lines"] + ["", '<section class="about">', '<dl class="facts">',
              "<dt>Asked</dt>", f"<dd>{esc(asked)}</dd>", "<dt>Searched</dt>", f"<dd>{esc(searched)}</dd>",
              "<dt>Could not read</dt>", f"<dd>{esc(could_not_read)}</dd>"]
    if folder.notes:
        lines += ["<dt>Housekeeping</dt>", f"<dd>{esc(' '.join(folder.notes))}</dd>"]
    lines += ["</dl>", "</section>", "", parts["footer"], "", "</main>", "</body>", "</html>", ""]
    return "\n".join(lines)


def save_page(folder: Folder, name: str, page: str) -> tuple:
    views = folder.pace / VIEWS_DIR
    if not views.is_dir():
        return "not-saved", None, (f"{VIEWS_DIR}/ was not found in {folder.pace}, so the page was not saved."
                                   f"{pr.old_folder_names(folder.pace)}")
    data = page.encode("utf-8")
    for number in range(1, 100):
        path = views / (f"{name}.html" if number == 1 else f"{name}-{number}.html")
        try:
            placed = pr.place_new(path, data)
        except pr.PartialPlacement as error:
            return "placed-not-confirmed", path, (f"{pr.rel(folder.pace, path)} was created but writing it failed ({error}), "
                                                  "so it may be incomplete. Nothing was replaced.")
        except OSError as error:
            return "not-saved", None, f"The page could not be written to {pr.rel(folder.pace, path)}: {error}."
        if placed == "exists":
            continue
        try:
            back = pr.read_back(path)
        except OSError as error:
            return "placed-not-confirmed", path, f"{pr.rel(folder.pace, path)} was created but could not be read back: {error}."
        if back != data:
            return "placed-not-confirmed", path, f"{pr.rel(folder.pace, path)} was created but did not read back as written."
        return "saved", path, f"Saved and read back: {pr.rel(folder.pace, path)}."
    return "not-saved", None, f"{VIEWS_DIR}/ already holds 99 pages named {name}; nothing was replaced."


def _run(args) -> tuple:
    pace = pr.pace_folder(args.pace)
    folder = Folder(pace, args.owner or [], args.as_at)
    template = Path(args.template).expanduser() if args.template else pace / TEMPLATE
    if not template.is_absolute():
        template = pace / template
    try:
        parts = template_parts(template.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise Stop(f"The page template could not be read ({error}). No page was made.") from None
    style_note = ""
    if not all(name in parts["style"] for name in CURRENT_STYLES):
        # A customised template from before this page design: its styles would leave the page unstyled, so the
        # shipped styles are used, and the result says so.
        shipped = HERE.parent / "Pace add-ins" / "Project overview" / "overview-template.html"
        try:
            current = template_parts(shipped.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, Stop):
            current = None
        if current and all(name in current["style"] for name in CURRENT_STYLES):
            parts["style"] = current["style"]
            style_note = (" The template's style block was made for an earlier page design, so the shipped template's "
                          "styles were used; compare the customised copy with the shipped template and carry over its styles.")
        else:
            style_note = (" The template's style block was made for an earlier page design and the shipped template's "
                          "styles could not be read, so the page may look unstyled; compare the customised copy with the "
                          "shipped template and carry over its styles.")

    if args.project:
        kind = "one project"
        view = one_project_view(folder, args.project)
        default_asked = f"Where does {folder.name_of(args.project)} stand? It and the projects inside it."
    elif args.by_person:
        kind = "by person"
        view = by_person_view(folder)
        default_asked = "What does each person owe, and what are they waiting for? Every project in 1 Projects/."
    else:
        kind = "every project"
        view = every_project_view(folder)
        default_asked = "Where does every project stand? Every project in 1 Projects/."
    work, counts, suffix = view["work"], view["counts"], view["suffix"]

    files, projects = folder.files_in_record, len(folder.projects)
    records = (f"All {files} record files in {pr.RECORD_DIR}/, each opened" if files > 1 else
               f"The one record file in {pr.RECORD_DIR}/, opened" if files == 1 else f"{pr.RECORD_DIR}/, which holds no record files")
    if folder.left_out:
        records += (f"; {folder.left_out} made after this page's as-at moment {'was' if folder.left_out == 1 else 'were'} "
                    "left out")
    searched = (f"{records}, with corrections and withdrawals followed to the current account; and "
                f"{'the one project' if projects == 1 else f'the {projects} projects'} in {pr.PROJECTS_DIR}/. "
                "This computer's copy only; no cloud copy was checked.")
    could_not_read = ("Partial: " + " ".join(folder.problems)) if folder.problems else "Nothing: every file listed was opened."
    title = f"{view['title']}, {short_date(folder.today)}"
    page = build_page(folder, parts, view, title, args.asked or default_asked, searched, could_not_read)

    attention = [{"project": folder.label(item["project"]), "subject": item["subject"], "owed_by": item["owed"] or None,
                  "due": item["due"].isoformat(), "when": how_soon(item["due"], folder.today), "request": item["request"]}
                 for item in folder.needs_attention(work["open"])]
    two_ways = [[{"project": folder.label(item["project"]), "subject": item["subject"], "request": item["request"]}
                 for item in accounts] for accounts in work["two_ways"]]
    zone_note = (f"Dates are compared in {folder.zone_name} time, from Pace.md." if folder.zone_name else
                 f"Pace.md names no time zone, so today is this computer's date ({folder.now.tzname()}) and each record "
                 "keeps the date it was written with.")
    week = {"new": len(view["week"]["new"]), "done": len(view["week"]["done"]), "cancelled": len(view["week"]["cancelled"]),
            "due_date_changed": len(view["week"]["moved"])}
    summary = {"view": kind, "as_at": long_moment(folder.now), "counts": counts, "last_7_days": week,
               "needs_attention": attention, "recorded_two_ways": two_ways, "searched": searched,
               "could_not_read": could_not_read, "complete": not folder.problems, "housekeeping": folder.notes,
               "time_zone": folder.zone_name, "folders_without_id": folder.unlabelled}
    glance = (f"{counts['open']} open: {counts['overdue']} overdue, {counts['due_today']} due today, "
              f"{counts['due_next_7_days']} due in the next {SOON_DAYS} days, {counts['waiting_on_you']} waiting on you, "
              f"{counts['waiting_on_others']} waiting on others and {counts['recorded_two_ways']} recorded two ways.")
    if not args.save:
        return pr.result("made", f"Overview made, not saved (no --save). As at {summary['as_at']}. {glance} {zone_note}{style_note}",
                         True, page=None, **summary)
    name = f"{folder.today.isoformat()}-project-overview{suffix}"
    status, path, said = save_page(folder, name, page)
    return pr.result(status, f"{said} As at {summary['as_at']}. {glance} {zone_note}{style_note}", status == "saved",
                     page=pr.rel(pace, path) if path else None, **summary)


def run(args) -> tuple:
    """Make the overview, and save it with --save. Returns (result, exit code); a stop is a not-made result."""
    try:
        return _run(args)
    except (Stop, pr.NoPaceFolder) as error:
        return {"status": "not-made", "message": str(error)}, 1
    except OSError as error:
        return {"status": "not-made", "message": f"A file or folder could not be read ({error}), so no overview was made."}, 1
    except RecursionError:
        return {"status": "not-made", "message": "The projects' parent lines nest too deep to show (hundreds of levels), so no "
                                                 "overview was made. Check the parent lines in 1 Projects/."}, 1
    except OverflowError:
        return {"status": "not-made", "message": "A date is too near the start or end of the calendar to work with, so no "
                                                 "overview was made."}, 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pace_overview.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--pace", help="the Pace folder (found by itself when this file is in its Product/Tools/)")
    view = parser.add_mutually_exclusive_group()
    view.add_argument("--project", help="one project, by its id, with the projects inside it")
    view.add_argument("--by-person", action="store_true", help="what each person owes and waits for")
    parser.add_argument("--owner", action="append", help="the owner's name as records write it in owed-by and for; repeat for each spelling ('owner' always counts)")
    parser.add_argument("--asked", help="the owner's question, for the page's Asked line")
    parser.add_argument("--as-at", help="the moment to make the overview for, with its offset (default: now)")
    parser.add_argument("--template", help="a customised copy of the page template (default: the shipped one)")
    parser.add_argument("--save", action="store_true", help="save the page as a new file in 2 Views/ and read it back")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    pr.KEPT_TEMP_FILES.clear()
    out, code = run(args)
    if pr.KEPT_TEMP_FILES:
        out["kept_temp_files"] = [pr.rel(Path(args.pace or "."), path) for path in pr.KEPT_TEMP_FILES]
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
