#!/usr/bin/env python3
"""Pace archive: move finished work, unchanged, into the year and month folders inside Record/, on the owner's yes.

Finished work is an item whose current account is not open work, not a project change and not recorded two ways:
an action done or cancelled, a withdrawn item, a decision, a note, a result, a figure or a confirmation. Its story
moves once every record in it is more than 3 months old. Each record keeps its name and every byte, and goes into
the folder for the year and month in its request id, such as Record/2026/07/, so it can always be found from its id.
Open work, work recorded two ways, project changes and everything from the last 3 months stay directly in Record/.
Nothing else ever moves a record, and every new record, a correction of an archived one too, is saved directly in
Record/.

preview shows what would move and why the rest stays, and changes nothing. apply moves exactly what the preview
showed, on the owner's go-ahead in their own words, checks that each record reads back the same in its new place,
and saves a record of what moved, with a digest for each month folder, so the move can be checked again at any
time. Every command prints one JSON object: "status" is the honest outcome and "message" says it in plain words.

Standard library only; Python 3.9 or later. Help: Product/Help/records.md, under Archiving finished work.
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import importlib.util
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep Product/ free of cache files

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pace_overview_for_archive", HERE / "pace_overview.py")
po = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(po)
pr = po.pr


class Stop(Exception):
    """Archiving cannot go ahead; the message says why in plain words."""


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def plural(count: int, word: str, words: str = "") -> str:
    return f"{count:,} {word if count == 1 else (words or word + 's')}"


def plan_id(moves: list) -> str:
    """One fingerprint for exactly what would move: each record's place now, its SHA-256 and its place after."""
    return pr.sha256("".join(f"{move['from']} {move['sha256']} {move['to']}\n" for move in moves).encode("utf-8"))


def by_month(moves: list) -> dict:
    months: dict = {}
    for move in moves:
        months.setdefault(move["to"].rsplit("/", 1)[0], []).append(move)
    return months


def archive_record_text(moves: list) -> str:
    """The text of the record an archive saves before it moves anything: what it moves, where, and a digest for each
    month folder."""
    parts = [f"On the owner's yes, Pace's archive tool moves these {plural(len(moves), 'record')} of finished work, "
             "unchanged and under the same names, from Record/ into the folders for the year and month in their request "
             "ids. Each is checked to read back the same in its new place. If the archive stops part-way, the rest stay "
             "directly in Record/, whole, and a later archive moves them.",
             "For each folder, the digest is the SHA-256 of one line for each record listed under it, in order: its "
             "request id, a space, the SHA-256 of its file, and a new line. Anyone can work it out again to check that "
             "nothing has changed."]
    for month, entries in sorted(by_month(moves).items()):
        digest = po.month_digest([(move["request"], move["sha256"]) for move in entries])
        count = f"{len(entries)} {'record' if len(entries) == 1 else 'records'}"  # no thousands comma: it is read back
        parts.append("\n".join([f"Record/{month}/ - {count} - digest {digest}"] +
                               [move["request"] for move in entries]))
    return "\n\n".join(parts)


def months_text(moves: list) -> str:
    return ", ".join(f"Record/{month}/ ({len(entries)})" for month, entries in sorted(by_month(moves).items()))


def stays_text(stays: dict) -> str:
    said = [f"{stays['open']} open", f"{stays['two_ways']} recorded two ways",
            plural(stays["project_changes"], "project change")]
    if stays["unsettled"]:
        said.append(f"{stays['unsettled']} not settled, such as an item with a record that cannot be read (the health "
                    "check names them)")
    if stays.get("too_long"):
        said.append(f"{stays['too_long']} too long for one archive's record, with more records than it can list")
    said.append(f"{stays['recent']} with a record from the last {po.ARCHIVE_AFTER_MONTHS} months")
    return ", ".join(said[:-1]) + " and " + said[-1]


def make_plan(pace: Path, moment: dt.datetime) -> tuple:
    folder = po.Folder(pace, pr.owner_names(pace), None, zone_problem_ok=True)
    plan = folder.archive_plan(moment)
    # Nothing moves while a folder in Record/ was not read, since it could hold a correction of work that would move,
    # nor while anything inside the year and month folders needs sorting out first. A file that was not read but whose
    # name says its project keeps only that project's work in Record/.
    blocked = [issue["message"] for issue in folder.name_issues
               if (issue in pr.unread_parts(folder.name_issues) and not issue.get("request")) or "/" in issue.get("file", "")]
    return folder, plan, blocked


def moment_from(args, applying: bool = False) -> dt.datetime:
    if not args.as_at:
        return now()
    moment = pr.parse_time(args.as_at)
    if moment is None:
        raise Stop(f"--as-at needs a date and time with its offset, such as 2027-01-26T09:00:00+13:00, not {args.as_at!r}.")
    if applying and moment > now():
        raise Stop(f"{args.as_at} is still to come, so nothing was moved: work is archived only once it is more than "
                   f"{po.ARCHIVE_AFTER_MONTHS} months old. Leave out --as-at.")
    return moment


def preview(args) -> tuple:
    pace = pr.pace_folder(args.pace)
    folder, plan, blocked = make_plan(pace, moment_from(args))
    moves, cutoff = plan["moves"], pr.day_words(plan["cutoff"])
    details = {"cutoff": plan["cutoff"].isoformat(), "stays": plan["stays"], "in_record": plan["in_record"],
               "could_not_read": folder.problems}
    if blocked:
        return pr.result("not-ready", "Nothing can be archived until this is sorted out: " + " ".join(blocked) + " Run the "
                         "health check, which says what to do. Nothing was moved.", False, problems=blocked, **details)
    stays = stays_text(plan["stays"])
    if not moves:
        return pr.result("nothing-to-archive", f"Nothing to archive: no finished work has all its records from before "
                         f"{cutoff}, {po.ARCHIVE_AFTER_MONTHS} months ago. Staying in Record/: {stays}. Nothing was "
                         "moved.", True, moves=0, **details)
    more = (f" {plural(plan['more'], 'more record is', 'more records are')} ready too; archive again after this for "
            f"{'it' if plan['more'] == 1 else 'them'}, oldest first." if plan["more"] else "")
    stories = plural(plan["stories"], "item")
    return pr.result("ready", f"Archiving would move {plural(len(moves), 'record')}, the "
                     f"{'story' if plan['stories'] == 1 else 'stories'} of {stories} of finished work with all "
                     f"{'its' if plan['stories'] == 1 else 'their'} records from before {cutoff}, unchanged and under the "
                     "same names, from Record/ into the folders for the year and month in their request ids: "
                     f"{months_text(moves)}. Record/ itself would go from {plan['in_record']} to "
                     f"{plan['in_record'] - len(moves)} records. Staying in Record/: {stays}.{more} Nothing was moved. "
                     "To archive them, show the owner this and, on their yes in their own words, run apply with this "
                     "plan and their words.", True,
                     plan=plan_id(moves), moves=len(moves), stories=plan["stories"], more=plan["more"],
                     months={month: len(entries) for month, entries in sorted(by_month(moves).items())}, **details)


def _rename_no_replace(source: Path, target: Path) -> None:
    """Rename, refusing to replace a file already at the target. Windows always refuses; on Linux the kernel is asked
    to refuse; elsewhere, or where a folder cannot do that, the target is looked for just before."""
    if os.name != "nt" and sys.platform.startswith("linux"):
        try:
            import ctypes  # some Python builds have no ctypes; then the target is looked for just before
            renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
        except (ImportError, OSError, AttributeError):
            renameat2 = None
        if renameat2 is not None:
            renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            renameat2.restype = ctypes.c_int
            here = -100  # AT_FDCWD
            if renameat2(here, os.fsencode(str(source)), here, os.fsencode(str(target)), 1) == 0:  # RENAME_NOREPLACE
                return
            failed = ctypes.get_errno()
            if failed not in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP):
                raise OSError(failed, os.strerror(failed), str(target))
    if os.name != "nt" and os.path.lexists(target):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target))
    os.rename(source, target)  # on Windows this refuses an existing target itself


def move_one(record_dir: Path, move: dict) -> str:
    """Move one record to its month folder, never replacing a file. Returns "" or what went wrong."""
    source, target = record_dir / move["from"], record_dir / move["to"]
    try:
        if pr.sha256(source.read_bytes()) != move["sha256"]:
            return f"{pr.RECORD_DIR}/{move['from']} changed after the plan was made, so it was not moved"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            return f"{pr.RECORD_DIR}/{move['to']} is already there, so {pr.RECORD_DIR}/{move['from']} was not moved"
        _rename_no_replace(source, target)  # a rename: the same file, every byte as it was
    except FileExistsError:
        return f"{pr.RECORD_DIR}/{move['to']} is already there, so {pr.RECORD_DIR}/{move['from']} was not moved"
    except OSError as error:
        return f"{pr.RECORD_DIR}/{move['from']} could not be moved ({error})"
    return ""


def moved_ok(record_dir: Path, move: dict) -> str:
    """Check a moved record reads back the same in its new place and is gone from the old. Returns "" or the problem."""
    try:
        same = pr.sha256((record_dir / move["to"]).read_bytes()) == move["sha256"]
        still = (record_dir / move["from"]).exists()
    except OSError as error:
        return f"{pr.RECORD_DIR}/{move['to']} could not be read back after the move ({error})"
    if not same:
        return f"{pr.RECORD_DIR}/{move['to']} does not read back the same after the move"
    if still:
        return f"{pr.RECORD_DIR}/{move['from']} is still there after the move"
    return ""


def archive_record(moves: list, words: str, by: str) -> tuple:
    """The record of an archive, as (fields, text), and what would stop it being saved, before anything moves."""
    request = pr.make_request(pr.NO_PROJECT)
    fields = {"format": [pr.RECORD_FORMAT], "request": [request], "created": [pr.local_text(pr.request_time(request))],
              "project": [pr.NO_PROJECT], "kind": ["note"], "subject": [po.ARCHIVE_SUBJECT], "from": ["owner"],
              "words": [words], "by": [by]}
    text = archive_record_text(moves)
    data = pr.render(fields, text, pr.RECORD_ORDER)
    problems = pr.record_problems(fields, text, request) + pr.read_back_problems(data, fields, text)
    if len(data) > pr.MAX_RECORD_BYTES:
        problems.append(f"it would be {len(data):,} bytes, more than a record may be ({pr.MAX_RECORD_BYTES:,}); give the "
                        "owner's go-ahead in fewer words")
    return fields, text, problems


def apply(args) -> tuple:
    pace = pr.pace_folder(args.pace)
    words, by = pr.tidy_value(args.go_ahead or ""), pr.tidy_value(args.by or "")
    if not words:
        return pr.result("not-archived", "The owner's go-ahead in their own words is needed, given after they have seen "
                         "the preview. Nothing was moved.", False)
    if not by:
        return pr.result("not-archived", "Say who is running the archive with --by, such as \"Claude Code\". Nothing was "
                         "moved.", False)
    folder, plan, blocked = make_plan(pace, moment_from(args, applying=True))
    if blocked:
        return pr.result("not-archived", "Nothing was moved: " + " ".join(blocked) + " Run the health check, which says "
                         "what to do.", False, problems=blocked)
    moves = plan["moves"]
    if not moves:
        return pr.result("nothing-to-archive", "Nothing was moved: nothing is ready to archive now. Preview again.", False)
    if args.plan != plan_id(moves):
        return pr.result("plan-changed", "Nothing was moved: what would move is not what that preview showed, for "
                         "example because a record was saved or corrected since, or more work has become ready. Preview "
                         "again and show the owner the new plan.", False, plan=plan_id(moves))
    # The record of the archive is saved, and read back, before anything moves, so every record an archive moves is
    # listed, whatever stops it part-way.
    fields, text, problems = archive_record(moves, words, by)
    if problems:
        return pr.result("not-archived", "Nothing was moved: the record of this archive could not be made (" +
                         "; ".join(problems) + ").", False)
    # A retry after a stop that moved nothing says the same thing again, and is saved as its own record.
    options = argparse.Namespace(not_a_duplicate=True, allow_unknown_project=True, pace_path=pace)
    saved, _ = pr.save_record(pace, options, dict(fields), text)
    if saved.get("status") != "saved":
        return pr.result("not-archived", f"Nothing was moved: the record of this archive was not saved ({saved.get('message')}).",
                         False, record=saved.get("request"))
    record_dir = pace / pr.RECORD_DIR
    moved, problem = [], ""
    for move in moves:
        problem = move_one(record_dir, move)
        if problem:
            break
        problem = moved_ok(record_dir, move)
        if problem:
            problem += "; compare it with OneDrive's version history before anything else"
            break
        moved.append(move)
    counts = {"moved": len(moved), "planned": len(moves), "record": saved.get("request"), "file": saved.get("file"),
              "months": {month: len(entries) for month, entries in sorted(by_month(moved).items())}}
    told = f"The record of this archive was saved and read back first: {saved.get('file')}."
    if problem and not moved:
        return pr.result("not-archived", f"Nothing was moved: {problem}. {told} It lists them as moving, and they stay "
                         "directly in Record/, whole, for a later archive. Preview again once that is sorted out.", False,
                         **counts)
    if problem:
        return pr.result("partly-archived", f"Stopped part-way: {problem}. "
                         f"{plural(len(moved), 'record was', 'records were')} moved before it. {told} Every record is whole "
                         "and in one place: in its month folder if it moved, otherwise directly in Record/. Preview again "
                         "to archive the rest.", False, **counts)
    return pr.result("archived", f"{plural(len(moved), 'record was', 'records were')} moved, unchanged and under the same "
                     f"names, into their year and month folders: {months_text(moved)}. Each read back the same in its "
                     f"new place. {told} {pr.CLOUD_NOTE}", True, **counts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pace_archive.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, run, text in (("preview", preview, "show what would move and why the rest stays; changes nothing"),
                            ("apply", apply, "move what the preview showed, on the owner's go-ahead")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--pace", help="the Pace folder (found by itself when this file is in its Product/Tools/)")
        command.add_argument("--as-at", help="the moment to judge 3 months from, with its offset; now when left out")
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
    except (Stop, po.Stop, pr.NoPaceFolder) as error:
        out, code = {"status": "not-archived" if args.command == "apply" else "not-ready", "message": str(error)}, 1
    except Exception as error:  # whatever stops it, the answer is one JSON object and every record is whole
        out, code = {"status": "stopped", "message": f"Stopped on an unexpected error ({type(error).__name__}: {error}). "
                     "Every record is whole and in one place: in its month folder if it moved, otherwise directly in "
                     "Record/. Run the health check, then preview again."}, 1
    pr.print_result(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
