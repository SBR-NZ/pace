#!/usr/bin/env python3
"""Pace folders: number the folders in 1 Projects/, on the owner's yes, so each keeps its place as more are added.

From release 3.16.0 each project folder starts with a number, a full stop and a space: from 01. at the top of
1 Projects/, and from 02. inside a project, whose Documents/ is 01. Documents/. The record tool numbers each new
project itself. This tool numbers the folders a Pace folder already has: each project folder and each project's
Documents/. A folder that already starts with a number keeps it; the rest take the lowest numbers free, in the order a
file browser lists them now, after each Documents/. Only the names change: everything in each folder stays as it is.
Pages and chat show each project's name without its number, and records keep the paths they were saved with, which
the tools still find through the numbered folders.

preview shows each new name and changes nothing. apply renames exactly what the preview showed, on the owner's
go-ahead in their own words: it saves a record of the renames first and reads it back, then renames each folder, the
deepest first, never over a folder already there, and checks it. A folder that cannot be renamed keeps its name, and a
correction of the record says what happened to each. Every command prints one JSON object: "status" is the honest outcome and
"message" says it in plain words.

Standard library only; Python 3.9 or later. Help: Product/Help/projects.md, under Numbered folders.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import stat
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True  # keep Product/ free of cache files

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pace_record_for_folders", HERE / "pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

SUBJECT = "Numbering folders"
BATCH = 300                     # renames one run makes, in whole folders; a larger Pace folder takes more than one run
# Bytes of a run's list of renames, so its record fits in one, and so does a correction naming each folder that kept its
# name, even where Windows' reasons for each are left out to make it fit.
LIST_ROOM = 32 * 1024
MAX_LOOKED_AT = 200_000         # files and folders checked for path length, so a preview stays quick
# Without these, nothing is in place to number: 1 Projects/ is missing, or projects are still under a name from before
# 3.11.0. Anything else that stops a folder being read leaves only that folder, and what is inside it, as it is.
BLOCKING = ("missing-folder", "old-folder-names")
SKIP_FOR = {"unreadable": "it could not be read", "damaged": "its Pace project.md could not be read"}
STOPS_A_RENAME = ("A file open from the folder, OneDrive still syncing it, no right to rename it, or a new path too long "
                  "for Windows can each stop a rename.")
LINK_TAGS = (0xA0000003, 0xA000000C)  # Windows: a junction, a symbolic link
# Letters a file browser sorts with another, which have no accent to take off.
FOLD = str.maketrans({"Æ": "AE", "æ": "ae", "Ø": "O", "ø": "o", "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ð": "D",
                      "ð": "d", "Þ": "Th", "þ": "th", "ß": "ss", "Œ": "OE", "œ": "oe", "Ħ": "H", "ħ": "h", "Ŋ": "N",
                      "ŋ": "n", "Ŧ": "T", "ŧ": "t", "ı": "i", "ĸ": "k", "ŉ": "n"})
# Windows' sort passes over hyphens and apostrophes, so Co-op sorts as Coop and O'Brien as OBrien.
PASSED_OVER = set("-\u2010\u2011'\u2019\u00ad")


class Stop(Exception):
    """Numbering cannot go ahead; the message says why in plain words."""


def plural(count: int, word: str, words: str = "") -> str:
    return f"{count:,} {word if count == 1 else (words or word + 's')}"


def browser_order(name: str) -> list:
    """The order Windows File Explorer lists folders in, near enough: case and accents ignored, hyphens and apostrophes
    passed over, spaces and other punctuation before digits, each run of digits taken as one number, then letters."""
    plain = "".join(char for char in unicodedata.normalize("NFKD", name.translate(FOLD)) if not unicodedata.combining(char))
    order: list = []
    for part in re.split(r"([0-9]+)", plain):  # before passing over hyphens, so 2025-26 stays two numbers
        if re.fullmatch(r"[0-9]+", part):
            order.append((1, int(part)))
        else:
            order += [(2, char.casefold()) if char.isalpha() else (0, char) for char in part if char not in PASSED_OVER]
    return order


def plan_id(renames: list) -> str:
    """One fingerprint for exactly what would be renamed: each folder's place now and its new name."""
    return pr.sha256("".join(f"{rename['from']}\t{rename['to']}\n" for rename in renames).encode("utf-8"))


redirected = pr.redirected


def writable(text: str) -> bool:
    """True when a folder's place can be written in a record as one line of UTF-8 text. A name that is not valid text,
    as Linux or a damaged entry on Windows can hold, cannot be, nor one with a line break, a tab or another control
    character in it, as macOS and Linux allow."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return not any(unicodedata.category(char) in ("Cc", "Zl", "Zp") for char in text)


def is_link(path: Path) -> bool:
    """True for a symbolic link, or on Windows a junction, which a walk of the folders must not follow."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) in LINK_TAGS


def numbers_for(in_project: bool, here: list, waiting: list) -> tuple:
    """A number for each project folder waiting in this folder, as ([(folder, number)], [folders no number is left
    for]): the lowest numbers no folder here starts with, given in the order a file browser lists the folders waiting,
    so they keep their order among themselves. A folder already numbered keeps its number, wherever that falls among
    theirs. Each run gives the lowest numbers then free, so folders that kept their names in an earlier run get the
    numbers planned for them then, unless a folder beside them has been made, removed or renamed since. In a project
    01 is its Documents/."""
    used = {pr.folder_number(name)[0] for name, is_dir in here if is_dir} - {None}
    floor = pr.DOCUMENTS_NUMBER if in_project else 0
    free = [number for number in range(floor + 1, pr.HIGHEST_NUMBER + 1) if number not in used]
    return list(zip(waiting, free)), waiting[len(free):]


def make_plan(pace: Path) -> dict:
    """What would be renamed, whole folder by whole folder, the deepest first; and what stays as it is, with why."""
    projects, issues, unlabelled = pr.scan_projects(pace)
    base = pace / pr.PROJECTS_DIR
    # 1 Projects/ itself unreadable leaves nothing known to number.
    blocked = [issue["message"] for issue in issues if issue.get("type") in BLOCKING or
               issue.get("type") == "unreadable" and issue.get("folder") == pr.PROJECTS_DIR]
    not_all_seen = [issue["message"] for issue in issues if issue.get("type") in ("too-many-folders", "too-deep")]
    skipped: list = []
    unusable = set()
    for issue in issues:
        if issue.get("type") in SKIP_FOR and issue.get("folder"):
            unusable.add(issue["folder"])
            skipped.append(f"{issue['folder']}/ keeps its name, and so does everything in it, as {SKIP_FOR[issue['type']]}")
    try:
        inside = os.path.normcase(os.path.realpath(base)) + os.sep
    except OSError:
        inside = None
    every = {entry["folder"] for entry in projects}
    folders, left, behind, unwritable = set(), set(), {}, []
    for entry in sorted(projects, key=lambda entry: entry["folder"]):  # each folder before those inside it
        where = entry["folder"]
        folder = pace / where
        around = [parent.as_posix() for parent in Path(where).parents if parent.parts[1:]]
        if where in unusable or any(parent in unusable or parent in left for parent in around):
            continue  # said once, for the folder around it
        if not writable(where):
            left.add(where)
            shown = repr(where)[1:-1]  # with each character a record cannot hold written out, such as \r or \udce9
            unwritable.append(shown)
            skipped.append(f"{shown}/ keeps its name, and so does everything in it, as its name is not valid text or holds a "
                           "line break or another control character, so a record could not name it; rename it first")
            continue
        if redirected(pace, folder):
            left.add(where)
            try:
                real = os.path.normcase(os.path.realpath(folder))
            except OSError:
                real = ""
            if inside and real.startswith(inside):
                skipped.append(f"{where}/ is reached through a link or junction to a folder in {pr.PROJECTS_DIR}/, which "
                               "is numbered where it really is; once it is, the link no longer leads there, so make the "
                               "link again afterwards")
            else:
                skipped.append(f"{where}/ keeps its name, and so does everything in it, as it is reached through a link "
                               "or junction to a folder outside the Pace folder")
            continue
        # A project inside a folder that is not one, such as a repository checkout or a copy of a Pace folder, is not
        # one of the owner's own project folders, so it is left as it is.
        between = [parent for parent in around if parent not in every]
        if between:
            behind.setdefault(between[-1], []).append(where)
            continue
        folders.add(folder)
    for outer, inside_it in sorted(behind.items()):
        one = len(inside_it) == 1
        skipped.append(f"{plural(len(inside_it), 'project')} inside {outer}/ {'keeps its name' if one else 'keep their names'}, "
                       f"as {outer}/ has no Pace project.md: it may be a repository checkout or a copy of a Pace folder, "
                       "and the health check says what to do")
    levels: dict = {}
    for folder in folders:
        levels.setdefault(folder.parent, []).append(folder)
        levels.setdefault(folder, [])
    groups, kept, clashes, held, full = [], [], [], [], []
    for level in sorted(levels, key=lambda path: pr.rel(pace, path)):
        where = pr.rel(pace, level)
        if where in unusable or (level != base and level not in folders):
            continue
        try:
            with os.scandir(level) as entries:
                here = [(entry.name, entry.is_dir()) for entry in entries]
        except OSError as error:
            skipped.append(f"what is in {where}/ keeps its names, as it could not be listed ({error.strerror or error})")
            continue
        dirs = [name for name, is_dir in here if is_dir]
        in_project = level in folders
        renames = []
        if in_project:
            documents = sorted(name for name in dirs if pr.is_working_dir(name))
            if len(documents) > 1:
                clashes.append(f"{where}/ has more than one Documents folder ({', '.join(name + '/' for name in documents)}), "
                               "so they keep their names; the health check says what to do")
            elif documents and pr.folder_number(documents[0])[0] is None and redirected(pace, level / documents[0]):
                skipped.append(f"{where}/{documents[0]}/ keeps its name, as it is reached through a link or junction")
            elif documents and pr.folder_number(documents[0])[0] is None:
                others = [name for name in dirs if pr.folder_number(name)[0] == pr.DOCUMENTS_NUMBER]
                if others:
                    clashes.append(f"{where}/{documents[0]}/ becomes {pr.numbered_name(pr.DOCUMENTS_NUMBER, documents[0])}/, "
                                   f"which {', '.join(name + '/' for name in others)} beside it starts with too")
                renames.append((documents[0], pr.numbered_name(pr.DOCUMENTS_NUMBER, documents[0])))
        waiting = []
        for folder in sorted(levels[level], key=lambda folder: (browser_order(folder.name), folder.name)):
            if pr.folder_number(folder.name)[0] is not None:
                kept.append(f"{pr.rel(pace, folder)}/, shown as {pr.plain_name(folder.name)}")
                continue
            same = [name for name in dirs if name != folder.name and
                    pr.name_key(pr.plain_name(name)) == pr.name_key(folder.name)]
            if same:
                clashes.append(f"{pr.rel(pace, folder)}/ keeps its name, as {', '.join(name + '/' for name in same)} beside "
                               "it has the same name once numbered, and a record naming one could find the other; rename "
                               "one of them first")
                held.append(pr.rel(pace, folder))
                continue
            waiting.append(folder)
        given, none_left = numbers_for(in_project, here, waiting)
        for folder in none_left:
            clashes.append(f"{pr.rel(pace, folder)}/ keeps its name, as every number from 01 to {pr.HIGHEST_NUMBER} is "
                           f"taken in {where}/")
            held.append(pr.rel(pace, folder))
            full.append(pr.rel(pace, folder))
        renames += [(folder.name, pr.numbered_name(number, folder.name)) for folder, number in given]
        group = []
        for old, new in renames:
            if os.path.lexists(level / new):
                clashes.append(f"{where}/{new}/ is already there, so {where}/{old}/ keeps its name")
                held.append(f"{where}/{old}")
                continue
            group.append({"from": pr.rel(pace, level / old), "to": new})
        if group:
            groups.append({"level": where, "depth": len(level.relative_to(pace).parts), "renames": group})
    groups.sort(key=lambda group: (-group["depth"], group["level"]))
    batch, more, room = [], 0, 0
    for group in groups:
        size = len(rename_lines(group["renames"]).encode("utf-8"))
        if batch and (len(batch) + len(group["renames"]) > BATCH or room + size > LIST_ROOM):
            more += len(group["renames"])
            continue
        batch += group["renames"]
        room += size
    # held: what keeps its name until the owner sorts it out, which the health check names; full: those of them held
    # because every number is taken where they are; unwritable: those whose names a record cannot hold.
    return {"renames": batch, "more": more, "kept": sorted(kept), "clashes": clashes,
            "held": sorted(held + unwritable), "full": sorted(full), "unwritable": sorted(unwritable), "skipped": skipped,
            "not_all_seen": not_all_seen, "blocked": blocked, "not_projects": unlabelled, "projects": len(projects)}


def too_long(pace: Path, renames: list) -> tuple:
    """Files whose full path would pass a limit only once the folders around them are numbered, counting the Pace
    folder's own place as at least a typical OneDrive one: (those past Windows' usual limit, past which Office and other
    Windows tools stop; those past only Excel's; whether every file was looked at)."""
    if not renames:
        return [], [], True
    try:
        root = max(len(str(pace.resolve())) + 1, pr.TYPICAL_ROOT)
    except OSError:
        root = pr.TYPICAL_ROOT
    growth = {Path(rename["from"]): len(rename["to"]) - len(Path(rename["from"]).name) for rename in renames}
    extra_of: dict = {}
    windows, excel, looked = [], [], 0
    for current, dirs, files in os.walk(pace / pr.PROJECTS_DIR):
        dirs[:] = sorted(name for name in dirs if not is_link(Path(current) / name))  # nor junctions, on Windows
        where = Path(current).relative_to(pace)
        extra = extra_of.get(where.parent, 0) + growth.get(where, 0)
        extra_of[where] = extra
        looked += 1 + len(files)
        if looked > MAX_LOOKED_AT:
            return windows, excel, False
        if not extra:
            continue
        for name in sorted(files):
            now = root + len(str(where / name))
            if now < pr.WINDOWS_PATH_LIMIT <= now + extra:
                windows.append((where / name).as_posix())
            elif now <= pr.EXCEL_PATH_LIMIT < now + extra:
                excel.append((where / name).as_posix())
    return windows, excel, True


def rename_lines(renames: list) -> str:
    return "".join(f"{rename['from']}/ -> {rename['to']}/\n" for rename in renames)


def record_text(renames: list) -> str:
    parts = [f"On the owner's yes, Pace's folders tool numbers these {plural(len(renames), 'folder')} in "
             f"{pr.PROJECTS_DIR}/, so each keeps its place as more are added. Only their names change: everything in "
             "each folder stays as it is. Records keep the paths they were saved with, and Pace's tools still find each "
             "file through the numbered folders. A folder that cannot be renamed keeps its name, and a correction of "
             "this record then says what happened to each.",
             rename_lines(renames).rstrip("\n")]
    return "\n\n".join(parts)


def outcome_text(planned: int, outcomes: list, reasons: bool = True) -> str:
    """The correction's text, which becomes the record's current account: what happened to each folder it lists, from
    (rename, outcome, why) for each. Without reasons, for when Windows' own words would make it too long for a record,
    it names each folder that kept its name or was not checked, and says the rest were renamed and checked."""
    done = [rename for rename, outcome, _ in outcomes if outcome == "renamed"]
    unchecked = [(rename, why) for rename, outcome, why in outcomes if outcome == "unchecked"]
    failed = [(rename, why) for rename, outcome, why in outcomes if outcome == "not-renamed"]

    def were(count: int) -> str:
        return f"{count or 'none'} {'was' if count < 2 else 'were'}"

    said = [f"{were(len(done))} renamed and checked"]
    if unchecked:
        said.append(f"{were(len(unchecked))} renamed but not checked afterwards")
    if failed:
        said.append(f"{len(failed)} kept {'its name' if len(failed) == 1 else 'their names'}, for a later run to number")
    parts = [f"Of the {plural(planned, 'folder')} this numbering set out to rename, " +
             (", ".join(said[:-1]) + ", and " + said[-1] if len(said) > 1 else said[0]) + "."]
    if failed:
        lines = [why if reasons else f"{rename['from']}/" for rename, why in failed]
        parts.append(f"{'Kept its name' if len(failed) == 1 else 'Kept their names'}:\n" + "\n".join(lines) + "\n" +
                     ("" if reasons else "The reasons Windows gave were too long to keep in this record. ") + STOPS_A_RENAME)
    if unchecked:
        lines = [why if reasons else f"{rename['from']}/ -> {rename['to']}/" for rename, why in unchecked]
        parts.append("Renamed, but not checked afterwards; look at each by hand:\n" + "\n".join(lines))
    if done and reasons:
        parts.append("Renamed and checked:\n" + rename_lines(done).rstrip("\n"))
    elif done:
        parts.append("Every other folder that record lists was renamed and checked.")
    return "\n\n".join(parts)


def rename_one(pace: Path, rename: dict) -> tuple:
    """Rename one folder in place, never over another: ("renamed", ""), or ("not-renamed" or "unchecked", why)."""
    source = pace / rename["from"]
    target = source.parent / rename["to"]
    try:
        if not source.is_dir() or redirected(pace, source):
            return "not-renamed", f"{rename['from']}/: no longer there as it was"
        if os.path.lexists(target):
            return "not-renamed", f"{rename['from']}/: {rename['to']}/ is already there"
        pr.rename_no_replace(source, target)
    except FileExistsError:
        return "not-renamed", f"{rename['from']}/: {rename['to']}/ is already there"
    except OSError as error:
        return "not-renamed", f"{rename['from']}/: could not be renamed ({error.strerror or type(error).__name__})"
    try:
        if not target.is_dir() or os.path.lexists(source) and not pr.same_folder(source, target):
            return "unchecked", f"{rename['from']}/ -> {rename['to']}/: renamed, but did not read back as it should"
    except OSError as error:
        return "unchecked", f"{rename['from']}/ -> {rename['to']}/: renamed, but could not be checked ({error.strerror or error})"
    return "renamed", ""


def save(fields: dict, text: str, pace: Path) -> tuple:
    """Save one record and read it back: (the save's result, or None, and "" or why it was not saved)."""
    data = pr.render(fields, text, pr.RECORD_ORDER)
    problems = pr.record_problems(fields, text, fields["request"][0]) + pr.read_back_problems(data, fields, text)
    if len(data) > pr.MAX_RECORD_BYTES:
        problems.append(f"it would be {len(data):,} bytes, more than a record may be ({pr.MAX_RECORD_BYTES:,})")
    if problems:
        return None, "; ".join(problems)
    options = argparse.Namespace(not_a_duplicate=True, allow_unknown_project=True, pace_path=pace)
    saved, _ = pr.save_record(pace, options, dict(fields), text)
    return saved, "" if saved.get("status") == "saved" else saved.get("message", "not saved")


def new_fields(origin: str, by: str, words: str = "", corrects: str = "") -> dict:
    request = pr.make_request(pr.NO_PROJECT)
    fields = {"format": [pr.RECORD_FORMAT], "request": [request], "created": [pr.local_text(pr.request_time(request))],
              "project": [pr.NO_PROJECT], "kind": ["note"], "subject": [SUBJECT], "from": [origin]}
    if words:
        fields["words"] = [words]
    if corrects:
        fields["corrects"] = [corrects]
    fields["by"] = [by]
    return fields


def preview(args) -> tuple:
    pace = pr.pace_folder(args.pace)
    plan = make_plan(pace)
    renames = plan["renames"]
    details = {"kept": plan["kept"], "clashes": plan["clashes"], "skipped": plan["skipped"],
               "not_all_seen": plan["not_all_seen"], "not_projects": plan["not_projects"]}
    if plan["blocked"]:
        return pr.result("not-ready", "No folder can be numbered until this is sorted out: " + " ".join(plan["blocked"]) +
                         " Run the health check, which says what to do. Nothing was renamed.", False,
                         problems=plan["blocked"], **details)
    left = [f"{'; '.join(plan[key])}." for key in ("clashes", "skipped") if plan[key]]
    if plan["not_all_seen"]:
        left.append("Not every folder was looked into, so any project inside these keeps its name: " +
                    " ".join(plan["not_all_seen"]))
    left = [part[0].upper() + part[1:] for part in left]
    if not renames:
        return pr.result("nothing-to-number", f"Nothing to number: every project folder in {pr.PROJECTS_DIR}/ that can be "
                         "numbered, and every project's Documents/, already has its number. Nothing was renamed." +
                         "".join(" " + part for part in left), True, renames=[], **details)
    past_windows, long_paths, every_file = too_long(pace, renames)
    said = [f"Numbering would rename {plural(len(renames), 'folder')} in {pr.PROJECTS_DIR}/, keeping everything in "
            "each: " + "; ".join(f"{rename['from']}/ to {rename['to']}/" for rename in renames[:20]) +
            (f"; and {plural(len(renames) - 20, 'more')}" if len(renames) > 20 else "") + "."]
    if plan["kept"]:
        one = len(plan["kept"]) == 1
        said.append(f"{plural(len(plan['kept']), 'project folder')} already {'starts' if one else 'start'} with a number "
                    f"and {'keeps it' if one else 'keep them'}: {'; '.join(plan['kept'][:10])}"
                    f"{' and more' if len(plan['kept']) > 10 else ''}.")
    plain = [name for name in plan["not_projects"] if pr.folder_number(Path(name).name)[0] is None]
    if plain:
        said.append("Not numbered, as they are not projects, and so listed after the numbered folders: "
                    f"{', '.join(name + '/' for name in plain[:10])}{' and more' if len(plain) > 10 else ''}.")
    said += left
    if plan["more"]:
        said.append(f"{plural(plan['more'], 'more folder')} can be numbered by a later run.")
    if past_windows:
        one = len(past_windows) == 1
        said.append(f"{plural(len(past_windows), 'file')} would have a path of {pr.WINDOWS_PATH_LIMIT} characters or more "
                    f"once numbered, where Office and other Windows tools cannot open {'it' if one else 'them'}: "
                    f"{'; '.join(past_windows[:5])}{' and more' if len(past_windows) > 5 else ''}. Shorten a folder or "
                    "file name on the way first, or ask the owner.")
    if long_paths:
        said.append(f"{plural(len(long_paths), 'file')} would have a path longer than Excel's {pr.EXCEL_PATH_LIMIT}-character "
                    f"limit once numbered, so Excel could not open {'it' if len(long_paths) == 1 else 'them'}: "
                    f"{'; '.join(long_paths[:5])}{' and more' if len(long_paths) > 5 else ''}. Shorten a folder or file "
                    "name on the way first, or ask the owner.")
    if not every_file:
        said.append(f"Only the first {MAX_LOOKED_AT:,} files and folders were checked for path length.")
    said.append("Anything that finds a file in these folders by its path stops finding it: links between Excel workbooks "
                "in different folders, Power Query and Power BI file sources, shortcuts and pinned folders. Records and "
                "Pace's tools still find their files. Close any file open from these folders and let OneDrive finish "
                "syncing first. Nothing was renamed. To number them, show the owner this and, on their yes in their own "
                "words, run apply with this plan and their words.")
    return pr.result("ready", " ".join(said), True, plan=plan_id(renames), renames=renames, more=plan["more"],
                     too_long_after=long_paths[:50], past_windows_limit_after=past_windows[:50],
                     every_file_checked=every_file, **details)


def apply(args) -> tuple:
    pace = pr.pace_folder(args.pace)
    words, by = pr.tidy_value(args.go_ahead or ""), pr.tidy_value(args.by or "")
    if not words:
        return pr.result("not-numbered", "The owner's go-ahead in their own words is needed, given after they have seen the "
                         "preview. Nothing was renamed.", False)
    if not by:
        return pr.result("not-numbered", "Say who is numbering the folders with --by, such as \"Claude Code\". Nothing was "
                         "renamed.", False)
    plan = make_plan(pace)
    if plan["blocked"]:
        return pr.result("not-numbered", "Nothing was renamed: " + " ".join(plan["blocked"]) + " Run the health check, which "
                         "says what to do.", False, problems=plan["blocked"])
    renames = plan["renames"]
    if not renames:
        return pr.result("nothing-to-number", "Nothing was renamed: every folder that can be numbered already has its "
                         "number. Preview again.", False)
    if args.plan != plan_id(renames):
        return pr.result("plan-changed", "Nothing was renamed: what would be renamed is not what that preview showed, for "
                         "example because a project was made or a folder renamed since. Preview again and show the owner "
                         "the new plan.", False, plan=plan_id(renames))
    # The record of the renames is saved, and read back, before any folder is renamed, so every folder renamed is
    # listed, whatever stops it part-way.
    saved, problem = save(new_fields("owner", by, words=words), record_text(renames), pace)
    if problem:
        # A run's list of renames is kept small enough for its record, so a record too large means long words.
        why = f"{problem}; give the owner's go-ahead in fewer words" if "more than a record may be" in problem else problem
        placed = bool(saved) and saved.get("status") == "placed-not-confirmed"
        return pr.result("not-numbered", f"Nothing was renamed: the record of the renames could not be saved ({why})." +
                         (f" {saved.get('file')} may hold it although nothing was renamed, so tell the owner not to rely on "
                          "it." if placed else ""), False, record=saved.get("request") if placed else None)
    outcomes = []
    for rename in renames:
        # One that cannot be renamed keeps its name; the deepest are first, so the rest are still where the plan says.
        outcomes.append((rename, *rename_one(pace, rename)))
    done = [rename for rename, outcome, _ in outcomes if outcome == "renamed"]
    unchecked = [why for _, outcome, why in outcomes if outcome == "unchecked"]
    failed = [why for _, outcome, why in outcomes if outcome == "not-renamed"]
    counts = {"renamed": len(done), "planned": len(renames), "more": plan["more"], "record": saved.get("request"),
              "file": saved.get("file"), "renames": done, "not_checked": unchecked, "not_renamed": failed}
    told = f"The record of the renames was saved and read back first: {saved.get('file')}."
    if unchecked or failed:
        # The record listed every folder as being numbered, so a correction says what happened to each.
        fields = new_fields("agent", by, corrects=saved.get("request"))
        text = outcome_text(len(renames), outcomes)
        if len(pr.render(fields, text, pr.RECORD_ORDER)) > pr.MAX_RECORD_BYTES:
            text = outcome_text(len(renames), outcomes, reasons=False)
        correction, problem = save(fields, text, pace)
        counts["correction"] = correction.get("request") if correction and not problem else None
        told += (f" A correction saying what happened to each folder was saved and read back: {correction.get('file')}."
                 if counts["correction"] else f" A correction saying what happened to each folder could not be saved "
                 f"({problem}): tell the owner what happened to each, as renames, not_checked and not_renamed list.")
        if done:
            said = [f"{plural(len(done), 'folder was', 'folders were')} numbered, each checked"]
        else:
            said = ["No folder was both renamed and checked" if unchecked else "Nothing was renamed"]

        def first(lines: list) -> str:
            return lines[0] + (f"; and {len(lines) - 1} more" if len(lines) > 1 else "")

        if unchecked:
            said.append(f"{plural(len(unchecked), 'folder was', 'folders were')} renamed but not checked afterwards, so "
                        f"look at {'it' if len(unchecked) == 1 else 'each'} by hand: {first(unchecked)}")
        if failed:
            said.append(f"{plural(len(failed), 'folder')} kept {'its name' if len(failed) == 1 else 'their names'}: "
                        f"{first(failed)}")
        after = (f" {STOPS_A_RENAME} Close any file open from the folders that kept their names, let OneDrive finish "
                 "syncing, then preview again." if failed else " Then preview again.")
        status = "partly-numbered" if done or unchecked else "not-numbered"
        return pr.result(status, "; ".join(said) + f". {told}{after}", False, **counts)
    more = f" {plural(plan['more'], 'more folder')} can be numbered by another run: preview again." if plan["more"] else ""
    return pr.result("numbered", f"{plural(len(done), 'folder was', 'folders were')} numbered, each checked, with everything "
                     f"in it as it was. {told}{more} {pr.CLOUD_NOTE}", True, **counts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pace_folders.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, run, text in (("preview", preview, "show each folder's new name; changes nothing"),
                            ("apply", apply, "rename what the preview showed, on the owner's go-ahead")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--pace", help="the Pace folder (found by itself when this file is in its Product/Tools/)")
        command.set_defaults(run=run)
        if name == "apply":
            command.add_argument("--plan", required=True, help="the plan the preview gave")
            command.add_argument("--go-ahead", required=True, help="the owner's yes, in their own words")
            command.add_argument("--by", required=True, help="the assistant or person running it")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        out, code = args.run(args)
    except (Stop, pr.NoPaceFolder) as error:
        out, code = {"status": "not-numbered" if args.command == "apply" else "not-ready", "message": str(error)}, 1
    except Exception as error:  # whatever stops it, the answer is one JSON object and every folder is whole
        out, code = {"status": "stopped", "message": f"Stopped on an unexpected error ({type(error).__name__}: {error}). "
                     "Every folder is whole, under its old name or its new one. Run the health check, then preview "
                     "again."}, 1
    pr.print_result(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
