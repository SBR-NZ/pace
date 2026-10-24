#!/usr/bin/env python3
"""Pace project overview: a dated page made from the records, in the Project overview add-in's template.

Reads Record/ and Projects/ with the record tool's own readers, follows corrections and withdrawals
to each item's current account, and works out what is open, overdue or due soon and whose move it
is. It changes no record. With --save it creates one new page in Views/, never replacing a file,
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
from pathlib import Path

sys.dont_write_bytecode = True  # keep Product/ free of cache files

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pace_record", HERE / "pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

TEMPLATE = Path("Product") / "Pace add-ins" / "Project overview" / "overview-template.html"
VIEWS_DIR = "Views"
PRODUCT_NAME = "Pace by SBR"
SOON_DAYS = 7
RECENT_DAYS = 21
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
        self.owners = {name.casefold().strip() for name in owners if name.strip()} | OWNER_WORDS

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
        self.items, self.problems, self.left_out = {}, [], 0
        for issue in project_issues + name_issues:
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

    def label_html(self, pid: str) -> str:
        above = list(reversed(self.ancestors(pid)))
        if not above:
            return esc(self.name_of(pid))
        return f'<span class="parent">{self.trail_html(above)}{CHEVRON}</span> {esc(self.name_of(pid))}'

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
        return (name or "").casefold().strip() in self.owners

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


# ---------------------------------------------------------------- page parts

def tiles(counts: dict) -> list:
    shown = (("overdue", "overdue"), ("due_today", "due today"), ("due_next_7_days", "due in the next 7 days"),
             ("waiting_on_you", "waiting on you"), ("waiting_on_others", "waiting on others"), ("no_due_date", "with no due date"))
    lines = ['<ul class="tiles">']
    for key, words in shown:
        kind = "tile key" if key == "overdue" and counts["overdue"] else "tile"
        lines.append(f'<li class="{kind}"><span class="count">{counts[key]}</span> {words}</li>')
    lines.append("</ul>")
    return lines


def owed_text(folder: Folder, item: dict) -> str:
    if not item["owed"]:
        return "Owed by: not recorded"
    return "Owed by you" if folder.is_owner(item["owed"]) else f"Owed by {esc(item['owed'])}"


def for_text(folder: Folder, item: dict) -> str:
    if not item["for"]:
        return ""
    return "For you" if folder.is_owner(item["for"]) else f"For {esc(item['for'])}"


def item_lines(folder: Folder, item: dict, who: str, where: str = "") -> list:
    """One open item: its project when the list mixes projects, the record's own words, then who, when and its state.

    The page leaves out record references; the tool's result gives them for the items that need a reply."""
    kind = "item"
    parts = [who] if who else []
    if item["due"]:
        if item["due"] < folder.today:
            kind = "item late"
        elif item["due"] == folder.today:
            kind = "item today"
        parts += [f"due {short_date(item['due'])}", f'<span class="when">{how_soon(item["due"], folder.today)}</span>']
    else:
        parts.append("no due date")
    parts.append(esc(item["state"] or "state not recorded"))
    return ([f'<li class="{kind}">'] + ([f'<p class="where">{where}</p>'] if where else [])
            + [f'<p class="what"><strong>{esc(item["subject"])}</strong> {esc(item["text"])}</p>',
               f'<p class="meta">{DOT.join(parts)}</p>', "</li>"])


def record_lines(item: dict, meta: str) -> list:
    return ['<li class="item">',
            f'<p class="what"><strong>{esc(item["subject"])}</strong> {esc(item["text"])}</p>',
            f'<p class="meta">{meta}</p>',
            "</li>"]


def listed(lines: list) -> list:
    return ['<ul class="items">'] + lines + ["</ul>"] if lines else ['<p class="none">None.</p>']


def two_ways_part(folder: Folder, groups: list) -> list:
    if not groups:
        return []
    lines = ['<section class="part two-ways">', "<h2>Recorded two ways</h2>",
             '<p class="lede">Each of these has two current accounts. Ask the owner which stands.</p>', '<ul class="items">']
    for accounts in groups:
        first = accounts[0]
        lines += ["<li>", f'<p><strong>{esc(first["subject"])}</strong> <span class="parent">{folder.ref_label(first["project"])}</span></p>',
                  '<ol class="accounts">']
        for item in accounts:
            due = f"due {short_date(item['due'])}" if item["due"] else "no due date"
            lines += ['<li class="item">', f'<p class="what">{esc(item["text"])}</p>',
                      f'<p class="meta">{owed_text(folder, item)}{DOT}{due}{DOT}{esc(item["state"] or "state not recorded")}</p>',
                      "</li>"]
        lines += ["</ol>", "</li>"]
    return lines + ["</ul>", "</section>"]


def attention_part(folder: Folder, items: list, scope: str) -> list:
    lines = []
    for item in folder.needs_attention(items):
        lines += item_lines(folder, item, owed_text(folder, item), folder.ref_label(item["project"]))
    return (['<section class="part">', "<h2>Needs attention</h2>",
             f'<p class="lede">Overdue, due today and due in the next {SOON_DAYS} days, {scope}.</p>']
            + listed(lines) + ["</section>"])


def groups_lines(folder: Folder, items: list, show_project) -> list:
    """Open items split into Waiting on you, Waiting on others and No person named, each in the same order."""
    groups = (("Waiting on you", lambda item: folder.is_owner(item["owed"])),
              ("Waiting on others", lambda item: item["owed"] and not folder.is_owner(item["owed"])),
              ("No person named", lambda item: not item["owed"]))
    lines = []
    for heading, belongs in groups:
        chosen = [item for item in items if belongs(item)]
        if not chosen:
            continue
        lines += [f'<h3 class="group">{heading}</h3>', '<ul class="items">']
        for item in chosen:
            lines += item_lines(folder, item, owed_text(folder, item) if item["owed"] else "",
                                folder.ref_label(item["project"]) if show_project(item) else "")
        lines.append("</ul>")
    return lines or ['<p class="none">None.</p>']


def pressing(folder: Folder, items: list, pid: str):
    mine = [item for item in items if item["project"] == pid]
    dated = [item["due"] for item in mine if item["due"]]
    overdue = sum(1 for day in dated if day < folder.today)
    return (-overdue, min(dated) if dated else dt.date.max, -len(mine), folder.name_of(pid).casefold())


def project_order(folder: Folder, items: list, extra=()) -> tuple:
    """The projects to list and their order, at any depth.

    Listed: each project with open work, and each in `extra` (a target or status with no open work). They are
    grouped under their top project, the most pressing group first. In a group each project comes before the
    projects inside it, and projects side by side run most pressing first, judged by the most pressing work
    anywhere inside them; ties go by name, then id. Projects whose parents loop are shown at the top rather
    than lost. Returns the order and every project shown or above one shown."""
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

    order: list = []
    visited: set = set()

    def visit(pid):
        if pid in visited:
            return
        visited.add(pid)
        if pid in listed:
            order.append(pid)
        for child in sorted(inside.get(pid, []), key=side_by_side):
            visit(child)

    for pid in sorted(inside.get(top, []), key=side_by_side):
        visit(pid)
    return order, tree


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


def projects_table(folder: Folder, items: list, ordered: list) -> list:
    """One row per project: who leads it and its target when any project here has one; its open and overdue counts,
    its earliest due date (late or not) and its newest record; and its status, with its date, under its name."""
    facts = folder.facts()
    columns = [key for key in ("owner", "target") if any(facts.get(pid, {}).get(key) for pid in ordered)]
    rows = []
    for pid in ordered:
        mine = [item for item in items if item["project"] == pid]
        found = facts.get(pid, {})
        overdue = sum(1 for item in mine if item["due"] and item["due"] < folder.today)
        dated = sorted(item["due"] for item in mine if item["due"])
        if dated:
            late = " late" if dated[0] < folder.today else ""
            due = f'<td class="due{late}">{short_date(dated[0])}, {how_soon(dated[0], folder.today)}</td>'
        else:
            due = '<td class="due">No due date</td>'
        status = (f'<span class="status"> {fact_text(folder, "status", found["status"])}</span>'
                  if found.get("status") else "")
        cells = ""
        if "owner" in columns:
            cells += f'<td class="owner">{fact_text(folder, "owner", found.get("owner"))}</td>'
        if "target" in columns:
            late = " late" if target_late(folder, found.get("target")) else ""
            cells += f'<td class="target{late}">{fact_text(folder, "target", found.get("target"))}</td>'
        last_text = day_and_age(folder.last_recorded({pid}), folder.today)
        rows.append(f'<tr><th>{folder.label_html(pid)}{status}</th>{cells}<td class="num open">{len(mine)}</td>'
                    f'<td class="num overdue{" late" if overdue else ""}">{overdue}</td>{due}<td class="last">{last_text}</td></tr>')
    heads = "".join({"owner": "<th>Owner</th>", "target": "<th>Target</th>"}[key] for key in columns)
    return (['<div class="table-wrap">', '<table class="projects">', "<thead>",
             f'<tr><th>Project</th>{heads}<th class="num">Open</th><th class="num">Overdue</th><th>Earliest due</th>'
             "<th>Last recorded</th></tr>",
             "</thead>", "<tbody>"] + rows + ["</tbody>", "</table>", "</div>"])


def every_project_view(folder: Folder) -> tuple:
    work = folder.work()
    items, counts = work["open"], folder.counts(work["open"], work["two_ways"])
    tracked = [pid for pid, found in folder.facts().items() if found.get("target") or found.get("status")]
    ordered, tree = project_order(folder, items, tracked)
    # A project above one in the table is in the table's tree, and work recorded two ways is in that section, so
    # none of them, nor the projects above work recorded two ways, is listed as having no open work.
    disputed = set()
    for accounts in work["two_ways"]:
        if any(item["kind"] == "action" for item in accounts):
            for item in accounts:
                disputed |= {item["project"], *folder.ancestors(item["project"])}
    idle = sorted((pid for pid in folder.projects if pid not in tree and pid not in disputed),
                  key=lambda pid: folder.label(pid).casefold())

    lines = ["<!-- start: every project view -->", '<section class="view">'] + tiles(counts)
    lines += two_ways_part(folder, work["two_ways"])
    lines += attention_part(folder, items, "across every project")
    lines += ['<section class="part">', "<h2>Projects</h2>",
              '<p class="lede">Each project with open work, a target or a status, grouped under its parent, the most pressing '
              "first.</p>"]
    if ordered:
        lines += projects_table(folder, items, ordered)
    else:
        lines.append('<p class="none">No project has open work recorded.</p>')
    if idle:
        lines.append(f'<p class="quiet">No open work recorded: {", ".join(folder.ref_label(pid) for pid in idle)}.</p>')
    if folder.unlabelled:
        lines.append(f'<p class="quiet">Folders with no Pace project.md: {esc(", ".join(folder.unlabelled))}. '
                     "Ask the owner what each one is.</p>")
    lines.append("</section>")
    if items:
        lines += ['<section class="part">', "<h2>Open work by project</h2>"]
        for pid in [pid for pid in ordered if any(item["project"] == pid for item in items)]:
            mine = [item for item in items if item["project"] == pid]
            overdue = sum(1 for item in mine if item["due"] and item["due"] < folder.today)
            purpose = plain((folder.projects.get(pid) or {}).get("purpose", "")) or "Purpose not recorded"
            lines += ['<details class="project" open>',
                      f'<summary>{folder.label_html(pid)} <span class="counts">{len(mine)} open{DOT}{overdue} overdue</span></summary>',
                      f'<p class="purpose">{esc(purpose)}</p>']
            lines += groups_lines(folder, mine, lambda item: False)
            lines.append("</details>")
        lines.append("</section>")
    lines += ["</section>", "<!-- end: every project view -->"]
    return lines, work, counts, "Project overview", ""


def one_project_view(folder: Folder, pid: str) -> tuple:
    if pid not in folder.projects:
        raise Stop(f"No project with id {pid!r} is in {pr.PROJECTS_DIR}/. List them with the record tool's projects command.")
    family = folder.family(pid)
    work = folder.work(set(family))
    items, counts = work["open"], folder.counts(work["open"], work["two_ways"])
    entry = folder.projects[pid]
    above = list(reversed(folder.ancestors(pid)))
    inside = [folder.trail_html(list(reversed(folder.ancestors(child)))[len(above) + 1:] + [child]) for child in family[1:]]
    last = folder.last_recorded(set(family))
    facts = folder.facts()
    found = facts.get(pid, {})
    lines = ["<!-- start: one project view -->", '<section class="view">', '<dl class="facts">',
             "<dt>Purpose</dt>", f"<dd>{esc(plain(entry.get('purpose', '')) or 'Purpose not recorded')}</dd>",
             "<dt>Owner</dt>", f"<dd>{fact_text(folder, 'owner', found.get('owner'))}</dd>",
             "<dt>Target</dt>", f"<dd>{fact_text(folder, 'target', found.get('target'))}</dd>",
             "<dt>Status</dt>", f"<dd>{fact_text(folder, 'status', found.get('status'))}</dd>",
             "<dt>Part of</dt>", f"<dd>{folder.trail_html(above) if above else 'Not part of another project'}</dd>",
             "<dt>Projects inside it</dt>", f"<dd>{', '.join(inside) if inside else 'None'}</dd>",
             "<dt>Last recorded</dt>", f"<dd>{day_and_age(last, folder.today)}</dd>",
             "</dl>"] + tiles(counts)
    lines += two_ways_part(folder, work["two_ways"])
    lines += attention_part(folder, items, "in this project and the projects inside it")
    # The table shows when a project inside this one has open work, a target or a status.
    tracked = [child for child in family if facts.get(child, {}).get("target") or facts.get(child, {}).get("status")]
    if any(item["project"] != pid for item in items) or [child for child in tracked if child != pid]:
        ordered, _ = project_order(folder, items, tracked)
        lines += ['<section class="part">', "<h2>Projects</h2>",
                  '<p class="lede">This project and the projects inside it that have open work, a target or a status, '
                  "the most pressing first.</p>"]
        lines += projects_table(folder, items, ordered) + ["</section>"]
    lines += ['<section class="part">', "<h2>Open work</h2>"]
    lines += groups_lines(folder, items, lambda item: item["project"] != pid)
    lines.append("</section>")

    def recent(heading, key, meta):
        chosen = []
        for item in work[key]:
            chosen += record_lines(item, meta(item))
        return ['<section class="part">', f"<h2>{heading}</h2>"] + listed(chosen) + ["</section>"]

    def when(item):
        return short_date(item["day"]) if item["day"] else "Date not recorded"

    def source(item):
        if item["from"] == "owner":
            return "From you"
        return f"From {esc(item['who'])}" if item["who"] else f"From: {esc(item['from'] or 'not recorded')}"

    lines += recent("Decided in the last three weeks", "decisions", lambda item: f"{when(item)}{DOT}{source(item)}")
    lines += recent("Changed in the last three weeks", "changes", lambda item: f"{when(item)}{DOT}{source(item)}")
    lines += recent("Done in the last three weeks", "done", lambda item: f"{when(item)}{DOT}{esc(item['state'])}")
    lines += recent("Cancelled in the last three weeks", "cancelled", lambda item: f"{when(item)}{DOT}{esc(item['state'])}")
    lines += recent("Notes from the last three weeks", "notes", when)
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
    lines += ['<section class="part">', "<h2>Documents and repository references</h2>"]
    lines += (['<ul class="files">'] + [f"<li>{esc(place)}</li>" for place in places] + ["</ul>"]) if places else ['<p class="none">None.</p>']
    lines += ["</section>", "</section>", "<!-- end: one project view -->"]
    return lines, work, counts, folder.name_of(pid), f"-{pid}"


def by_person_view(folder: Folder) -> tuple:
    work = folder.work()
    items, counts = work["open"], folder.counts(work["open"], work["two_ways"])
    people: dict = {}
    for item in items:
        for role, name in (("owes", item["owed"]), ("waits", item["for"])):
            if name:
                key = "you" if folder.is_owner(name) else name.casefold().strip()
                people.setdefault(key, {"name": "You" if key == "you" else name.strip(), "owes": [], "waits": []})[role].append(item)
    order = sorted(people, key=lambda key: (key != "you", people[key]["name"].casefold()))
    lines = ["<!-- start: by person view -->", '<section class="view">'] + two_ways_part(folder, work["two_ways"])
    lines.append('<div class="cards">')
    for key in order:
        person = people[key]
        owes, waits = [], []
        for item in person["owes"]:
            owes += item_lines(folder, item, for_text(folder, item), folder.ref_label(item["project"]))
        for item in person["waits"]:
            waits += item_lines(folder, item, owed_text(folder, item), folder.ref_label(item["project"]))
        lines += ['<article class="card">', f"<h2>{esc(person['name'])}</h2>", '<h3 class="group">Owes</h3>'] + listed(owes)
        lines += ['<h3 class="group">Waiting for</h3>'] + listed(waits) + ["</article>"]
    nobody = []
    for item in items:
        if not item["owed"]:
            nobody += item_lines(folder, item, "", folder.ref_label(item["project"]))
    if nobody:
        lines += ['<article class="card">', "<h2>No person named</h2>"] + listed(nobody) + ["</article>"]
    if not order and not nobody:
        lines.append('<p class="none">No open work is recorded.</p>')
    lines += ["</div>", "</section>", "<!-- end: by person view -->"]
    return lines, work, counts, "Work by person", "-by-person"


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


def build_page(folder: Folder, parts: dict, view_lines: list, heading: str, title: str, asked: str,
               searched: str, could_not_read: str) -> str:
    lines = ["<!DOCTYPE html>", '<html lang="en-NZ">', "<head>", '<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta name="color-scheme" content="light dark">', f"<title>{esc(title)} - {PRODUCT_NAME}</title>",
             parts["style"], "</head>", "<body>", '<main class="page">', "", "<header>", '<div class="brand">',
             f'<p class="product">{PRODUCT_NAME}</p>', parts["wordmark"], "</div>", f"<h1>{esc(heading)}</h1>",
             '<dl class="facts">', "<dt>As at</dt>", f"<dd>{esc(long_moment(folder.now))}</dd>",
             "<dt>Asked</dt>", f"<dd>{esc(asked)}</dd>", "<dt>Searched</dt>", f"<dd>{esc(searched)}</dd>",
             "<dt>Could not read</dt>", f"<dd>{esc(could_not_read)}</dd>", "</dl>", "</header>", ""]
    lines += view_lines + ["", parts["footer"], "", "</main>", "</body>", "</html>", ""]
    return "\n".join(lines)


def save_page(folder: Folder, name: str, page: str) -> tuple:
    views = folder.pace / VIEWS_DIR
    if not views.is_dir():
        return "not-saved", None, f"{VIEWS_DIR}/ was not found in {folder.pace}, so the page was not saved."
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

    if args.project:
        view = "one project"
        view_lines, work, counts, heading, suffix = one_project_view(folder, args.project)
        default_asked = f"Where does {folder.name_of(args.project)} stand? It and the projects inside it."
    elif args.by_person:
        view = "by person"
        view_lines, work, counts, heading, suffix = by_person_view(folder)
        default_asked = "What does each person owe, and what are they waiting for? Every project in Projects/."
    else:
        view = "every project"
        view_lines, work, counts, heading, suffix = every_project_view(folder)
        default_asked = "Where does every project stand? Every project in Projects/."

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
    title = f"{heading}, {short_date(folder.today)}"
    page = build_page(folder, parts, view_lines, heading, title, args.asked or default_asked, searched, could_not_read)

    attention = [{"project": folder.label(item["project"]), "subject": item["subject"], "owed_by": item["owed"] or None,
                  "due": item["due"].isoformat(), "when": how_soon(item["due"], folder.today), "request": item["request"]}
                 for item in folder.needs_attention(work["open"])]
    two_ways = [[{"project": folder.label(item["project"]), "subject": item["subject"], "request": item["request"]}
                 for item in accounts] for accounts in work["two_ways"]]
    zone_note = (f"Dates are compared in {folder.zone_name} time, from Pace.md." if folder.zone_name else
                 f"Pace.md names no time zone, so today is this computer's date ({folder.now.tzname()}) and each record "
                 "keeps the date it was written with.")
    summary = {"view": view, "as_at": long_moment(folder.now), "counts": counts, "needs_attention": attention,
               "recorded_two_ways": two_ways, "searched": searched, "could_not_read": could_not_read,
               "complete": not folder.problems, "time_zone": folder.zone_name, "folders_without_id": folder.unlabelled}
    glance = (f"{counts['open']} open: {counts['overdue']} overdue, {counts['due_today']} due today, "
              f"{counts['due_next_7_days']} due in the next {SOON_DAYS} days, {counts['waiting_on_you']} waiting on you, "
              f"{counts['waiting_on_others']} waiting on others and {counts['recorded_two_ways']} recorded two ways.")
    if not args.save:
        return pr.result("made", f"Overview made, not saved (no --save). As at {summary['as_at']}. {glance} {zone_note}",
                         True, page=None, **summary)
    name = f"{folder.today.isoformat()}-project-overview{suffix}"
    status, path, said = save_page(folder, name, page)
    return pr.result(status, f"{said} As at {summary['as_at']}. {glance} {zone_note}", status == "saved",
                     page=pr.rel(pace, path) if path else None, **summary)


def run(args) -> tuple:
    """Make the overview, and save it with --save. Returns (result, exit code); a stop is a not-made result."""
    try:
        return _run(args)
    except (Stop, pr.NoPaceFolder) as error:
        return {"status": "not-made", "message": str(error)}, 1
    except OSError as error:
        return {"status": "not-made", "message": f"A file or folder could not be read ({error}), so no overview was made."}, 1


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
    parser.add_argument("--save", action="store_true", help="save the page as a new file in Views/ and read it back")
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
