#!/usr/bin/env python3
"""Pace health check: one read-only look over a whole Pace folder, with what to do about anything it finds.

It reads Pace.md, Record/, 1 Projects/, Repos/, 3 My add-ins/, Release record/ and Product/ with the record
tool's, the overview tool's and the updater's own readers, and changes nothing: it writes, moves and deletes
no file. With --latest it also asks the release repository, through git, which release is newest; nothing is
fetched or installed. It prints one JSON object: "status" is healthy, attention or problems, "message" says
it in plain words, and "findings" lists each thing found, its level (problem, warning or note) and what to do.

Standard library only; Python 3.9 or later. Help: Product/Help/health-check.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # keep Product/ free of cache files

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_for_check", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


po = _load("pace_overview")
pr = po.pr
pu = _load("pace_update")

LEVELS = ("problem", "warning", "note")
OWNER_ADDINS = pu.OWNER_ADDINS
SETUP_FILE = "Assistant setup.md"
SETUP_AGE_DAYS = 90  # an assistant setup list checked longer ago than this may be out of date
INDEX_LINE = re.compile(r"^- \*\*(?P<name>[^*]+)\*\* - (?P<purpose>[^`]+?) `(?P<path>[^`]+)`\s*$")
NO_ADDINS = "None switched on yet."
LAST_CHECKED = re.compile(r"^\s*Last checked:\s*`?([^`\s]+)`?\s*$", re.I | re.M)
REPO_ID = re.compile(r"^\s*(Home|Using) project id:\s*(\S+)\s*$", re.I | re.M)
LEFTOVER_PREFIXES = (pr.TEMP_PREFIX, pu.CHECK_PREFIX)
RENAME_HELP = "Updates help, under Folder names from 3.11.0, gives the steps."
# OneDrive for Business shows a folder of more than 5,000 items slowly, or with errors, on its web pages (SharePoint's
# list view threshold). Syncing and Pace's tools are not affected and there is nothing to do, so it is only a note.
RECORD_FOLDER_NOTE = 4000
RECORD_FOLDER_LIMIT = 5000
# Files an empty folder can still hold: Pace's own placeholder, and what Finder and Windows Explorer leave.
PLACEHOLDERS = {".gitkeep"} | set(pu.SYSTEM_FILES)
GETTING_STARTED = "Getting started"


class Findings:
    def __init__(self):
        self.items: list = []
        self.checked: list = []

    def add(self, level: str, check: str, message: str, fix: str = "", **extra) -> None:
        item = {"level": level, "check": check, "message": message}
        if fix:
            item["fix"] = fix
        item.update({key: value for key, value in extra.items() if value})
        self.items.append(item)

    def counts(self) -> dict:
        found = Counter(item["level"] for item in self.items)
        return {level: found.get(level, 0) for level in LEVELS}


def plural(count: int, word: str, words: str = "") -> str:
    return f"{count} {word if count == 1 else (words or word + 's')}"


def listed(names, limit: int = 8) -> str:
    names = list(names)
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


def pace_folder(given: str | None) -> Path:
    """The folder to check: --pace, then PACE_FOLDER, then the Pace folder this Product sits in. Unlike the other
    tools it does not need Pace.md or Record/ to be there, since saying that they are missing is its job."""
    if given:
        return Path(given).expanduser().resolve()
    if os.environ.get("PACE_FOLDER"):
        return Path(os.environ["PACE_FOLDER"]).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- folders

def projects_under_old_name(pace: Path) -> bool:
    """True while projects are kept in a Projects/ folder named as before 3.11.0, so the tools cannot read them."""
    old, numbered = pace / "Projects", pace / pr.PROJECTS_DIR
    if not old.is_dir() or pr.same_folder(old, numbered):
        return False
    return not numbered.is_dir() or pr.has_content(old)


def holds_nothing(folder: Path) -> bool:
    """True only when the folder could be listed and holds nothing but the files an empty folder can have. A folder
    that cannot be listed is never taken as empty."""
    try:
        with os.scandir(folder) as listing:
            return all(entry.is_file() and entry.name.lower() in PLACEHOLDERS for entry in listing)
    except OSError:
        return False


def check_folders(pace: Path, found: Findings) -> None:
    held = projects_under_old_name(pace)
    for name, level, why in (
        (pr.RECORD_DIR, "problem", "records cannot be read or saved"),
        (pr.PROJECTS_DIR, "problem", "no project can be found or made"),
        ("Product", "problem", "the help, add-ins and tools are not here"),
        (pu.RELEASE_RECORD, "warning", "an update cannot tell which release is installed or where releases come from"),
    ):
        if not (pace / name).is_dir() and not (name == pr.PROJECTS_DIR and held):
            found.add(level, "folders", f"{name}/ was not found in this Pace folder, so {why}.",
                      "Check that this is the Pace folder and that it is fully available on this computer, for example "
                      "that OneDrive has finished syncing it.")
    for step in pr.old_folder_steps(pace):
        if step.split("/", 1)[0].split()[-1] == "Projects" and held:
            # One cause, said once: until projects are under the numbered name, nothing that needs them can be checked.
            found.add("problem", "folder-names", f"Projects are kept under the folder name from before release 3.11.0, so no "
                      f"tool can find them: {step}. Until then, the projects records use and the Repos/ references were "
                      "not checked.", f"Close any file open from it and let OneDrive finish syncing, then {step}. "
                      f"{RENAME_HELP}")
            continue
        found.add("warning", "folder-names", f"This Pace folder still has a folder named as before release 3.11.0: {step}.",
                  f"Close any file open from it and let OneDrive finish syncing, then {step}. {RENAME_HELP}")
    found.checked.append("The top-level folders and their names.")


# ---------------------------------------------------------------- Pace.md

def read_pace_md(pace: Path, found: Findings) -> str | None:
    path = pace / "Pace.md"
    if not path.is_file():
        found.add("problem", "pace-md", "Pace.md is missing, so an assistant opening this folder has nothing to start from.",
                  "Put Pace.md back from OneDrive's version history or recycle bin; an update does not make a new one.")
        return None
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        found.add("problem", "pace-md", f"Pace.md could not be read as plain text ({error}).",
                  "Open it and save it again as UTF-8 text, or put back an earlier version from OneDrive.")
        return None
    return text.replace("\r\n", "\n")


def index_lines(text: str | None) -> list:
    """The add-in index lines below its mark, leaving out the placeholder line."""
    if text is None:
        return []
    parts, _ = pu.pace_md_parts(text)
    index = next((part for part in parts if part["id"] == "add-in-index"), None)
    lines = [line.strip() for line in (index["yours"] if index and index["yours"] else []) if line.strip()]
    return [line for line in lines if line != NO_ADDINS]


def switched_on(text: str | None) -> set:
    """The names of the add-ins the index switches on."""
    return {match["name"].strip() for match in map(INDEX_LINE.match, index_lines(text)) if match}


def check_pace_md(pace: Path, text: str, found: Findings, people: dict, steps: list) -> None:
    owed, named = people["owed"], people["named"]
    parts, shipped = pu.pace_md_parts(text)
    ids = [part["id"] for part in parts]
    if shipped is None:
        found.add("warning", "pace-md", "Pace.md does not record Pace's parts as shipped, so updates leave it as it is.",
                  "Updates help, under Pace.md, says how to start from the release's Pace.md and put your own lines back.")
    elif len(set(ids)) != len(ids):
        twice = sorted({part["title"] for part in parts if ids.count(part["id"]) > 1})
        found.add("warning", "pace-md", f"Two parts of Pace.md have the same heading ({listed(twice)}), so updates leave it as "
                  "it is.", "Give each heading once, keeping your lines below its mark.")
    else:
        changed = [part["title"] for part in parts if part["id"] in shipped and part["fingerprint"] != shipped[part["id"]]]
        if changed:
            found.add("note", "pace-md", f"These parts of Pace.md differ from how Pace shipped them, so updates keep them as "
                      f"yours: {listed(changed)}.", "Nothing to do, unless you want a release's wording: compare them with "
                      "that release's Pace.md.")

    # Whose work is the owner's.
    names = pr.owner_names(pace)
    if not names:
        hint = ""
        people_named = Counter({name: count for name, count in owed.items() if po.name_key(name) not in po.OWNER_WORDS})
        if people_named:
            hint = (" Records most often name these people as owing work: "
                    + ", ".join(f"{name} ({count})" for name, count in people_named.most_common(3)) + ".")
        found.add("warning", "owner", "Pace.md has no Owner: line, so the overview and the weekly review count only work owed "
                  f"by \"owner\" as yours.{hint}", "Add one line below the mark in the part The owner's name, with your name "
                  "as records write it, such as `Owner: Rangi Parata`, and one more line for each other spelling.")
    else:
        keys = {po.name_key(name) for name in names} | po.OWNER_WORDS
        if sum(named.values()) >= 10 and not any(po.name_key(name) in keys for name in named):
            found.add("note", "owner", f"No action names {listed(names)} or \"owner\" as owing it or as who it is for, while "
                      f"actions name {listed(name for name, _ in named.most_common(3))}.",
                      "Check that the Owner: line spells your name as records write it.")

    try:
        zone_name, _ = pr.owner_time_zone(pace)
    except ValueError as error:
        found.add("warning", "time-zone", f"Pace.md's time zone cannot be used here: {error}. Date searches and the overview "
                  "stop rather than guess.", "Keep one Time zone line, with a name such as Pacific/Auckland; on Windows, "
                  "install Python's tzdata package.")
    else:
        if not zone_name:
            found.add("note", "time-zone", "Pace.md names no time zone, so dates use each record's own written date, which "
                      "is often UTC when a cloud assistant saved it.", "Add one line below the mark in the part Time zone, "
                      "such as `Time zone: Pacific/Auckland`.")

    # The add-in index: every line names a file that is there.
    index = next((part for part in parts if part["id"] == "add-in-index"), None)
    lines = [line.strip() for line in (index["yours"] if index and index["yours"] else []) if line.strip()]
    entries = [line for line in lines if line != NO_ADDINS]
    for line in entries:
        match = INDEX_LINE.match(line)
        if not match:
            found.add("warning", "add-in-index", f"This add-in index line is not in the form add-ins help shows: \"{line}\".",
                      "Write it as - **Name** - its one-line purpose `path/ADD-IN.md`, or remove it.")
            continue
        target = pace / match["path"]
        if not target.is_file():
            found.add("problem", "add-in-index", f"The {match['name']} add-in's file, {match['path']}, is missing, so that add-in "
                      "cannot be opened.", "Point the line at the add-in's file (if its folder was renamed, use the new "
                      "name, such as 3 My add-ins/), or switch the add-in off by removing the line.")
    if entries and NO_ADDINS in lines:
        found.add("note", "add-in-index", f"The add-in index still says \"{NO_ADDINS}\" beside switched-on add-ins.",
                  "Remove that line.")

    # Lines naming a folder by its name before 3.11.0.
    old = [line.strip() for line in text.split("\n") if pu.OLD_FOLDER_PATH.search(line)]
    if old and steps:
        found.add("note", "folder-names", "Once the folders are renamed, change these lines in Pace.md to the numbered "
                  f"names: {'; '.join(chr(34) + line + chr(34) for line in old)}.", RENAME_HELP)
    elif old:
        for line in old:
            found.add("warning", "folder-names", f"Pace.md still names a folder as it was named before 3.11.0: \"{line}\".",
                      "Change it to the numbered name it has had since 3.11.0, such as 3 My add-ins/ for My add-ins/.")
    found.checked.append("Pace.md: its parts, its Owner and Time zone lines, the add-in index and the folders it names.")


# ---------------------------------------------------------------- records and projects

def check_records(pace: Path, found: Findings) -> tuple:
    """Every file in Record/, every record's story, and the projects records use.

    Returns (folder, people): people["owed"] counts who owes open work, and people["named"] every name an action
    gives in owed-by or for, so the Owner: line can be checked against them."""
    record_dir = pace / pr.RECORD_DIR
    people = {"owed": Counter(), "named": Counter()}
    owed = people["owed"]
    if not record_dir.is_dir():
        return None, people
    try:
        names, copies, issues = pr.scan_record_names(record_dir)
    except OSError as error:
        found.add("problem", "record-files", f"{pr.RECORD_DIR}/ could not be listed ({error}).",
                  "Check that the folder is available on this computer.")
        return None, people
    for issue in issues:
        kind = issue.get("type")
        if kind == "unfinished-save":
            if po.Folder._leftover_copy(record_dir, issue):
                found.add("note", "record-files", f"{pr.RECORD_DIR}/{issue['file']} is a leftover copy of a record that saved "
                          "and reads the same.", "It is harmless; someone with delete rights can delete it.",
                          files=[f"{pr.RECORD_DIR}/{issue['file']}"])
            else:
                found.add("warning", "record-files", issue["message"], "Compare it with the record it is named after, if "
                          "that is there; ask the owner before deleting it, since it may hold a save that did not finish.",
                          files=[f"{pr.RECORD_DIR}/{issue['file']}"])
        elif kind == "unexpected-folder":
            found.add("problem", "record-files", issue["message"], "Records belong directly in Record/. Ask the owner what "
                      "the folder holds before moving anything.", files=[f"{pr.RECORD_DIR}/{issue['file']}"])
        else:
            found.add("warning", "record-files", issue["message"], "Ask the owner what it is; nothing in Record/ but "
                      "records is read.", files=[f"{pr.RECORD_DIR}/{issue['file']}"])
    try:  # OneDrive counts every item in the folder, not only records
        with os.scandir(record_dir) as listing:
            items = sum(1 for _ in listing)
    except OSError:
        items = len(names) + len(copies)
    if items >= RECORD_FOLDER_NOTE:
        past = (f", more than the {RECORD_FOLDER_LIMIT:,} past which OneDrive's web pages show a folder slowly or with "
                "errors" if items > RECORD_FOLDER_LIMIT else f". Past {RECORD_FOLDER_LIMIT:,} items in one folder, "
                "OneDrive's web pages show it slowly or with errors")
        found.add("note", "record-files", f"{pr.RECORD_DIR}/ holds {items:,} items{past}, and a OneDrive connection lists "
                  "it more slowly.", "Nothing needs doing: syncing and Pace's tools work the same at any size. If OneDrive's "
                  "web pages are slow, open the folder on a computer instead. Never move or rename a record to make the "
                  f"folder smaller: Pace reads records only directly in {pr.RECORD_DIR}/.")
    for request, name in copies:
        try:
            same = (record_dir / name).read_bytes() == (record_dir / f"{request}.md").read_bytes()
        except OSError:
            same = False
        if same:
            message = (f"{pr.RECORD_DIR}/{name} is a second copy of record {request}, for example from file syncing, and "
                       "reads the same as it.")
            fix = ("It adds nothing: with the owner's yes, move the copy out of Record/. The record itself stays as it is.")
        else:
            message = pr.copy_issue(request, name)["message"]
            fix = ("Compare the two with the owner. The record itself is never replaced: if the copy holds what is right, "
                   "save a new record that corrects the record with it, as records help describes. Then, with the owner's "
                   "yes, move the copy out of Record/.")
        found.add("problem", "record-files", message, fix, files=[f"{pr.RECORD_DIR}/{name}", f"{pr.RECORD_DIR}/{request}.md"])
    for stem, name in sorted(names.items()):
        item = pr.load(record_dir, name)
        if item["state"] == "readable":
            continue
        if item["state"] == "missing":
            continue  # gone between listing and opening; the overview reader names it below
        fix = {
            "newer-format": "Install a newer Pace, which reads it.",
            "unreadable": "Check that the file has finished syncing and that this computer may read it, then run the check "
                          "again.",
            "invalid": "A saved record is never edited: save a new record that corrects it, as records help describes.",
        }.get(item["state"], "The record tool cannot correct a file it cannot read. Ask the owner what it should say, save "
                             "that as a new record that names this file in its text, and with the owner's yes move the "
                             "damaged file out of Record/.")
        found.add("problem", "records", pr.problem_issue(item)["message"], fix, files=[f"{pr.RECORD_DIR}/{name}"])

    try:
        folder = po.Folder(pace, pr.owner_names(pace), None, zone_problem_ok=True)
    except (po.Stop, OSError) as error:
        found.add("problem", "records", f"The records could not be read together ({error}).", "Run the check again; if it "
                  "stops the same way, ask whoever supports your Pace setup.")
        return None, people
    for earlier, pointers in folder.missing_corrected.items():
        found.add("problem", "corrections", f"{listed(f'{pr.RECORD_DIR}/{p}.md' for p in pointers)} "
                  f"{'corrects' if len(pointers) == 1 else 'correct'} {earlier}, but no file for it is in {pr.RECORD_DIR}/ here.",
                  "It may not have synced to this computer yet, or it was moved or removed: look for it in OneDrive, "
                  "including its recycle bin, before anything else.")
    for cycle in folder.correction_loops:
        found.add("problem", "corrections", f"The corrections {listed(cycle)} correct each other, so none of them is the "
                  "current account.", "Ask the owner which account stands, and save it as a new record, not a correction: the "
                  "record tool cannot correct records that correct each other.")
    looped = {stem for cycle in folder.correction_loops for stem in cycle}
    for chain in folder.chains:
        current = chain["current"]
        if len(current) > 1 and not set(current) <= looped:  # a loop is named above, once
            first = folder.entry(current[0])
            found.add("warning", "two-ways", f"\"{first['subject']}\" ({folder.label(first['project'])}) is recorded two ways: "
                      f"{listed(current)}.", "Ask the owner which stands, then withdraw the other and correct the one that "
                      "stands if it needs a change, as records help describes. The weekly review lists these first.")
        elif current:
            stem = current[0]
            if folder.field(stem, "kind") == "action":
                for key in ("owed-by", "for"):
                    name = " ".join(folder.field(stem, key).split())
                    if name:
                        people["named"][name] += 1
                        if key == "owed-by" and folder.field(stem, "state") not in ("done", "cancelled"):
                            owed[name] += 1
            target = folder.field(stem, "target")
            if folder.field(stem, "kind") == "change" and target and target != pr.NO_PROJECT and not pr.parse_date(target):
                found.add("warning", "records", f"{pr.RECORD_DIR}/{stem}.md gives the target {target!r}, which is not a real "
                          "date, so it is not used.", "Save a change that corrects it with a date such as 2026-11-27.")
    found.checked.append(f"{pr.RECORD_DIR}/: {plural(len(names), 'record file')}, each opened, with corrections followed to the "
                         "current account.")
    return folder, people


def check_projects(pace: Path, found: Findings, folder) -> list:
    """The project folders: ids, parents and folders with no id, and the project ids records use that no project has.
    Returns the projects found."""
    if not (pace / pr.PROJECTS_DIR).is_dir() or projects_under_old_name(pace):
        return []
    projects, issues, unlabelled = pr.scan_projects(pace)
    # Not every project could be read, so a project id records use may still be in a folder that was not read.
    partial = any(issue.get("type") in ("unreadable", "damaged", "too-many-folders", "too-deep", "folder-loop")
                  for issue in issues)
    for issue in issues:
        kind = issue.get("type")
        if kind in ("missing-folder", "old-folder-names"):
            continue  # named with the folders
        if kind == "unreadable" and issue.get("folder") == pr.PROJECTS_DIR:
            found.add("problem", "projects", issue["message"], "Check that this computer may read the folder and that it "
                      "has finished syncing, then run the check again.")
            continue
        if kind in ("damaged", "duplicate-id"):
            fix = ("Two folders with one id are two projects claiming one name: ask the owner which keeps it, and give the "
                   "other a new id with project-new." if kind == "duplicate-id" else
                   "Ask the owner; Pace project.md is a project's identity and is never rewritten to track work.")
            found.add("problem", "projects", issue["message"], fix)
        elif kind == "parent-mismatch":
            found.add("warning", "projects", issue["message"], "Move the folder to sit inside its parent's folder, or ask the "
                      "owner which parent is right.")
        else:
            found.add("warning", "projects", issue["message"], "Check the folder is available on this computer.")
    if unlabelled:
        found.add("warning", "projects", f"{plural(len(unlabelled), 'folder')} in {pr.PROJECTS_DIR}/ "
                  f"{'has' if len(unlabelled) == 1 else 'have'} no Pace project.md: {listed(unlabelled)}.",
                  "Ask the owner what each one is: make it a project, or move it into a project's Documents/, as projects "
                  "help describes.", files=unlabelled)
    if folder is not None:
        known = {entry["id"] for entry in projects}
        used: dict = {}
        for stem in folder.items:
            pid = folder.field(stem, "project")
            if pid and pid != pr.NO_PROJECT and pid not in known:
                used.setdefault(pid, []).append(stem)
        if used:
            said = listed(f"{pid} ({plural(len(stems), 'record')})" for pid, stems in sorted(used.items()))
            requests = sorted(stem for stems in used.values() for stem in stems)[:10]
            if partial:
                found.add("warning", "projects", f"Records use project ids that were not found: {said}. Not every project "
                          "folder could be read, so they may be in one of those.", "Fix the folders named above, then run "
                          "the check again. Do not make these projects again: a project may still be in a folder that was "
                          "not read, and two folders with one id is a problem of its own.", requests=requests)
            else:
                found.add("problem", "projects", f"Records use project ids that no project in {pr.PROJECTS_DIR}/ has: {said}.",
                          "Find each project's folder: it may have been moved out of 1 Projects/ or lost its Pace project.md, "
                          "which holds its id. Only if a project is truly gone, make it again with the same id, as projects "
                          "help describes.", requests=requests)
    found.checked.append(f"{pr.PROJECTS_DIR}/: {plural(len(projects), 'project')}.")
    return projects


REFERENCE_NAMES = ("Pace repo.md", "Pace repo link.md")


def reference_files(pace: Path, base: Path, found: Findings) -> list:
    """Every repository reference under Repos/. Each folder is read once, however it is reached (through a link or a
    junction too), no deeper than the record tool reads projects, and a folder that cannot be listed is named."""
    seen, files = set(), []

    def visit(folder: Path, depth: int) -> None:
        try:
            st = os.stat(folder)
            key = (st.st_dev, st.st_ino) if st.st_ino else str(folder.resolve())
        except OSError:
            key = str(folder.absolute())
        if key in seen or depth > pr.MAX_PROJECT_DEPTH:
            return
        seen.add(key)
        try:
            with os.scandir(folder) as listing:
                entries = sorted(listing, key=lambda entry: entry.name)
        except OSError as error:
            found.add("warning", "repos", f"{pr.rel(pace, folder)}/ could not be listed ({error}), so a reference inside it "
                      "was not checked.", "Check that this computer may read the folder, then run the check again.")
            return
        for entry in entries:
            path = folder / entry.name
            try:
                if entry.is_dir():
                    visit(path, depth + 1)
                elif entry.name in REFERENCE_NAMES and entry.is_file():
                    files.append(path)
            except OSError:
                continue

    visit(base, 0)
    return files


def check_repos(pace: Path, found: Findings, projects: list) -> None:
    base = pace / "Repos"
    if not base.is_dir() or projects_under_old_name(pace):
        return
    known = {entry["id"]: entry for entry in projects}
    count = 0
    for path in reference_files(pace, base, found):
        count += 1
        where = pr.rel(pace, path)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            found.add("warning", "repos", f"{where} could not be read ({error}).", "Open it and save it again as plain text.")
            continue
        ids = {label.lower(): pid for label, pid in REPO_ID.findall(text)}
        own = ids.get("using" if path.name == "Pace repo link.md" else "home")
        if not own:
            found.add("warning", "repos", f"{where} names no {'Using' if path.name == 'Pace repo link.md' else 'Home'} project "
                      "id.", "Add the line, with the id from the project's Pace project.md, as repositories help shows.")
            continue
        for label, pid in sorted(ids.items()):
            if pid not in known:
                found.add("warning", "repos", f"{where} names project id {pid}, which no project in {pr.PROJECTS_DIR}/ has.",
                          "Check the id against the project's Pace project.md.")
        entry = known.get(own)
        if entry:
            expected = Path(entry["folder"]).relative_to(pr.PROJECTS_DIR)
            try:
                place = path.parent.parent.relative_to(base) if path.parent != base else None
            except ValueError:
                place = None
            if place != expected:
                found.add("note", "repos", f"{where} is not in its project's place: Repos/ mirrors {pr.PROJECTS_DIR}/, so "
                          f"it belongs in a folder of its own under Repos/{expected.as_posix()}/.", "Move it there when the "
                          "owner agrees; the project id keeps it linked either way.")
    if count:
        found.checked.append(f"Repos/: {plural(count, 'repository reference')}.")


# ---------------------------------------------------------------- the release and Product

def check_release(pace: Path, found: Findings, latest: bool) -> None:
    if not (pace / pu.RELEASE_RECORD).is_dir():
        return
    note = pu.read_release_note(pace)
    if note["state"] == "missing":
        found.add("warning", "release", note["message"] + " So a check for an update needs the release repository's address.",
                  "Give --repo the first time you preview an update; the next install writes the note.")
    elif note["state"] != "readable":
        found.add("warning", "release", note["message"], "Updates help, under Checking for an update, says what the note "
                  "holds; ask whoever set up Pace before changing it.")
    if pu._work_area(pace).exists():
        state, _ = pu._leftover(pace)
        if state == "staging":
            found.add("note", "update", pu.STAGING_LEFTOVER, "Nothing to do now.")
        elif state in ("finished", "rolled back"):
            found.add("warning", "update", pu._leftover_message(state, "preview again"), "Run it on a computer that can "
                      "replace files in the Pace folder.")
        else:
            found.add("problem", "update", pu._leftover_message(state, "preview again"), "Do not move files by hand; updates "
                      "help, under If something goes wrong, says what to do.")
    prior = pu.installed_release(pace)
    if not prior:
        found.add("note", "product", "No install is recorded in this folder, so Product cannot be compared with a release.",
                  "Nothing to do; the next install records one.")
    elif (pace / pu.PRODUCT).is_dir():
        try:
            tree = pu.read_tree(pace / pu.PRODUCT)
            changed = pu.product_changes(prior, tree)
            system = sorted(path for path in tree if path.rsplit("/", 1)[-1].lower() in pu.SYSTEM_FILES)
            if system:
                found.add("note", "product", f"Product holds files that Finder or Windows Explorer leave in folders: "
                          f"{listed(system)}.", "They are harmless and are not edits; the next update replaces Product, "
                          "and them with it.", files=system[:20])
        except (pu.Stop, OSError) as error:
            changed = None
            found.add("warning", "product", f"Product could not be read to compare it with the installed release ({error}).",
                      "Check the folder is available on this computer.")
        if changed and changed.get("not_checked"):
            found.add("note", "product", "Release record/ keeps no Product file list, so whether Product was edited cannot be "
                      "checked.", "Nothing to do; the next install records one.")
        elif changed:
            files = changed["added"] + changed["changed"] + changed["removed"]
            what = (f"Files inside Product differ from the release noted as installed ({prior.get('tag')})" if not files else
                    f"{plural(len(files), 'file')} inside Product differ{'s' if len(files) == 1 else ''} from the installed "
                    f"release {prior.get('tag')}: {listed(files)}")
            found.add("warning", "product", what + ".", "Product is replaced as a whole by the next update, so copy anything "
                      "worth keeping into 3 My add-ins/ first, as updates help describes.", files=files[:20])
    if latest:
        try:
            source = pu.release_source(pace)
            tag, commit = pu.latest_release(source["repository"])
        except (pu.Stop, OSError) as error:
            found.add("note", "newer-release", f"Could not check for a newer release: {error}", "Check again later, or "
                      "preview an update as updates help describes.")
        else:
            installed = prior or {}
            how = pu.compare_with_installed(installed, tag, commit)
            if how == "newer":
                found.add("note", "newer-release", f"Pace {tag} is out; {installed.get('tag')} is installed.",
                          "Preview it as updates help describes; installing needs the owner's own go-ahead.",
                          tag=tag, commit=commit)
            elif how == "moved":
                found.add("warning", "newer-release", f"The tag {tag} now points to a different commit from the one installed.",
                          "Check with whoever published it before installing anything.", tag=tag, commit=commit)
            elif how == "same":
                found.checked.append(f"The newest release, {tag}, is installed.")
            elif how == "older":
                found.checked.append(f"The newest release in the repository, {tag}, is older than the installed "
                                     f"{installed.get('tag')}.")
            else:
                found.add("note", "newer-release", f"The newest release is {tag}, but the installed release is not known, so "
                          "they cannot be compared.", "Preview it as updates help describes.", tag=tag, commit=commit)
    else:
        found.checked.append("Whether a newer release is out was not checked; add --latest to ask the release repository.")
    found.checked.append("Release record/ and Product/: the installed release, any update left part-way, and Product's files.")


# ---------------------------------------------------------------- the rest

def check_assistant_setup(pace: Path, found: Findings, today: dt.date) -> None:
    path = pace / OWNER_ADDINS / SETUP_FILE
    where = f"{OWNER_ADDINS}/{SETUP_FILE}"
    if not path.is_file():
        found.add("note", "assistant-setup", f"There is no list of the owner's assistants and what each can reach ({where}).",
                  "Ask an assistant to start one, as the hosts help describes under The owner's assistants.")
        return
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        found.add("warning", "assistant-setup", f"{where} could not be read ({error}).", "Open it and save it again as plain text.")
        return
    match = LAST_CHECKED.search(text)
    day = pr.parse_date(match.group(1)) if match else None
    if not day:
        found.add("note", "assistant-setup", f"{where} has no Last checked: line with a date, so how current it is cannot be told.",
                  "Add one, such as `Last checked: 2026-10-26`, when it is next checked.")
    elif (today - day).days > SETUP_AGE_DAYS:
        found.add("note", "assistant-setup", f"{where} was last checked {(today - day).days} days ago.",
                  "Ask each assistant to check its own part against what it can see now, and update the date.")
    found.checked.append(f"{where}.")


def check_leftovers(pace: Path, found: Findings) -> None:
    for place in (po.VIEWS_DIR, pu.RELEASE_RECORD):
        folder = pace / place
        if not folder.is_dir():
            continue
        try:
            names = sorted(entry.name for entry in os.scandir(folder) if entry.is_file())
        except OSError:
            continue
        for name in names:
            if name.startswith(LEFTOVER_PREFIXES):
                found.add("note", "leftovers", f"{place}/{name} is a leftover work file from a save or an update check.",
                          "It is harmless; someone with delete rights can delete it.", files=[f"{place}/{name}"])


def run(args) -> tuple:
    pace = pace_folder(args.pace)
    found = Findings()
    if not pace.is_dir():
        return {"status": "not-checked", "message": f"{pace} is not a folder here, so nothing was checked."}, 1
    today = dt.datetime.now().astimezone().date()
    check_folders(pace, found)
    steps = pr.old_folder_steps(pace)
    folder, people = check_records(pace, found)
    text = read_pace_md(pace, found)
    if text is not None:
        check_pace_md(pace, text, found, people, steps)
    projects = check_projects(pace, found, folder)
    # New only when both folders were read in full and hold nothing: Getting started makes projects, and a project
    # made again beside one that could not be read would be two folders with one id.
    if not steps and not projects and holds_nothing(pace / pr.RECORD_DIR) and holds_nothing(pace / pr.PROJECTS_DIR):
        found.add("note", "new-folder", "This Pace folder looks new: it has no projects and no records yet.",
                  f"Ask the assistant to set up Pace with {GETTING_STARTED}." if GETTING_STARTED in switched_on(text) else
                  f"Switch on {GETTING_STARTED} and ask the assistant to set up Pace with it, as add-ins help describes.")
    check_repos(pace, found, projects)
    check_release(pace, found, args.latest)
    check_assistant_setup(pace, found, today)
    check_leftovers(pace, found)
    found.items.sort(key=lambda item: LEVELS.index(item["level"]))
    counts = found.counts()
    status = "problems" if counts["problem"] else "attention" if counts["warning"] else "healthy"
    said = (f"{plural(counts['problem'], 'problem')}, {plural(counts['warning'], 'warning')} and "
            f"{plural(counts['note'], 'note')}")
    lead = {"healthy": "Nothing needs doing.", "attention": "Something should be fixed soon; see findings.",
            "problems": "Something needs fixing; see findings, problems first."}[status]
    message = (f"Health check of {pace}: {said}. {lead} Nothing was changed. This computer's copy only; no cloud copy "
               "was checked.")
    out = {"status": status, "message": message, "pace": str(pace), "counts": counts, "findings": found.items,
           "checked": found.checked}
    return out, 0 if status == "healthy" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pace_check.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--pace", help="the Pace folder (found by itself when this file is in its Product/Tools/)")
    parser.add_argument("--latest", action="store_true", help="also ask the release repository, with git, which release is newest")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        out, code = run(args)
    except OSError as error:
        out, code = {"status": "not-checked", "message": f"The check stopped on a file error ({error}); nothing was changed."}, 1
    except Exception as error:  # a check that fails must still say so, as one JSON object
        out, code = {"status": "not-checked", "message": f"The check stopped on an unexpected error "
                     f"({type(error).__name__}: {error}); nothing was changed. Ask whoever supports your Pace setup."}, 1
    pr.print_result(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
