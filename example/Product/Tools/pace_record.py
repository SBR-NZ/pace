#!/usr/bin/env python3
"""Pace records and projects: create, read back and search.

Formats: record-1 (files in Record/) and project-1 (the "Pace project.md" file
in a project folder). Standard library only; any python3 from 3.8 on.

Plain help, including how to do all of this by hand:
Product/Help/records.md, Product/Help/record-format.md, Product/Help/projects.md,
Product/Help/confirmations.md.

Every command prints one JSON object. "status" is the honest outcome and
"message" says it in plain words. Exit code 0 means the command did what it
was asked and the result is confirmed; 1 means anything else.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import string
import sys
import time
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 cannot read time zones
    ZoneInfo = None

RECORD_FORMAT = "record-1"
PROJECT_FORMAT = "project-1"
RECORD_DIR = "Record"
PROJECTS_DIR = "Projects"
WORKING_DIR = "Documents"
ARCHIVE_DIR = "Archive"  # made beside a working file when a first version goes out, never with a project
PROJECT_FILE = "Pace project.md"

ID = r"[a-z0-9]+(?:-[a-z0-9]+)*"
PROJECT_ID = re.compile(rf"^{ID}$")
REQUEST = re.compile(rf"^(\d{{8}}T\d{{6}}Z)--({ID})--([a-z0-9]{{6}})$")
REQUEST_START = re.compile(rf"^(\d{{8}}T\d{{6}}Z)--({ID})--([a-z0-9]{{6}})")
KEY_LINE = re.compile(r"^([a-z][a-z0-9-]*):(.*)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_ZONE_LINE = re.compile(r"^\s*(?:[-*]\s+)?time zone:(.*)$", re.I)
MAX_ID = 40
MAX_RECORD_BYTES = 64 * 1024
DUPLICATE_WINDOW = dt.timedelta(days=7)
NO_PROJECT = "none"

KINDS = (
    "note",         # something worth keeping that fits no other kind
    "decision",     # an owner decision
    "action",       # a dated action or follow-up
    "person-note",  # a note about a named person
    "figure",       # a reported figure with its definition and source
    "result",       # a work result
    "change",       # a project change
    "withdrawal",   # an earlier record no longer stands
)
SPECIAL_KINDS = ("confirmation", "approval-reference")
LATER_KINDS = ("approval",)  # Old undeclared kind; never means confirmation.
ORIGINS = ("owner", "person", "source", "agent")
CAPTURED = ("as-we-go", "at-end")
ACTION_STATES = ("open", "done", "cancelled")
REPEATABLE = ("subject", "source")
RECORD_ORDER = (
    "format", "request", "created", "project", "kind", "subject", "from",
    "who", "words", "source", "by", "captured", "corrects", "separate-from", "due", "owed-by",
    "for", "state", "value", "unit", "period", "definition",
    "act", "act-file", "act-sha256", "confirmation-request",
    "approval-system", "approval-approver", "approval-decision", "approval-time", "approval-reference",
)
PROJECT_ORDER = ("format", "id", "parent", "created", "by")
IGNORED_NAMES = {".gitkeep", "desktop.ini", ".ds_store", "thumbs.db"}
TEMP_PREFIX = ".pace-tmp-"
UTC = dt.timezone.utc
ALPHABET = string.ascii_lowercase + string.digits

CLOUD_NOTE = "Checked on this computer's copy; arrival in any cloud copy is a separate check."
TEMP_NOTE = "It is harmless and Pace does not use it; someone with delete rights can delete it."


class PartialPlacement(OSError):
    """The destination was created but writing its content failed."""


class NoPaceFolder(Exception):
    """No Pace folder was given or found."""


# ---------------------------------------------------------------- basics

def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def parse_time(text: str):
    value = (text or "").strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def parse_date(text: str):
    """A real calendar day written like 2026-11-05, or None."""
    if not DATE.match(text or ""):
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def request_time(request: str) -> dt.datetime:
    match = REQUEST.match(request) or REQUEST_START.match(request)
    return dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def local_text(moment: dt.datetime) -> str:
    return moment.astimezone().replace(microsecond=0).isoformat()


def valid_project_id(value: str) -> bool:
    return bool(PROJECT_ID.match(value or "")) and len(value) <= MAX_ID and value != NO_PROJECT


def make_request(project: str, at: dt.datetime | None = None) -> str:
    moment = (at or now_utc()).astimezone(UTC)
    tail = "".join(secrets.choice(ALPHABET) for _ in range(6))
    return f"{moment:%Y%m%dT%H%M%SZ}--{project}--{tail}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tidy_value(value: str) -> str:
    """One canonical form for a header value: trimmed lines, no blank lines."""
    lines = [line.strip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def tidy_body(body: str) -> str:
    lines = [line.rstrip() for line in str(body).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


# ---------------------------------------------------------------- the file shape

def render(fields: dict, body: str, order) -> bytes:
    lines = ["---"]
    keys = [key for key in order if key in fields] + sorted(key for key in fields if key not in order)
    for key in keys:
        for value in fields[key]:
            parts = value.split("\n")
            lines.append(f"{key}: {parts[0]}")
            lines.extend("  " + part for part in parts[1:])
    lines.append("---")
    text = "\n".join(lines) + "\n"
    if body:
        text += "\n" + body + "\n"
    return text.encode("utf-8")


def parse(data: bytes):
    """Return (fields, body, problems). fields maps key -> list of values."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "", ["not readable as UTF-8 text"]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return None, "", ["does not start with a '---' header line"]
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None, "", ["header has no closing '---' line"]
    fields: dict = {}
    problems = []
    last = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line[:1] in (" ", "\t"):
            if last is None:
                problems.append("continuation line before any field")
            else:
                fields[last][-1] += "\n" + line
            continue
        match = KEY_LINE.match(line)
        if not match:
            problems.append(f"unrecognised header line: {line[:60]!r}")
            last = None
            continue
        last = match.group(1)
        fields.setdefault(last, []).append(match.group(2))
    fields = {key: [tidy_value(v) for v in values] for key, values in fields.items()}
    body = tidy_body("\n".join(lines[end + 1:]))
    return fields, body, problems


def one(fields: dict, key: str) -> str:
    values = fields.get(key) or []
    return values[0] if values else ""


def header_problems(fields: dict) -> list:
    """Values that would break the header: a continuation line of just '---' ends it early."""
    return [f"{key} has a line that is just '---', which would end the header early; "
            "write that line another way or put it in the text below the header"
            for key in sorted(fields)
            if any(part.strip() == "---" for value in fields[key] for part in value.split("\n")[1:])]


def read_back_problems(data: bytes, fields: dict, body: str) -> list:
    """Why these bytes would not read back as exactly these fields and text. Empty means they do."""
    parsed, parsed_body, problems = parse(data)
    if parsed is None:
        return problems
    differ = sorted(key for key in set(parsed) | set(fields) if parsed.get(key) != fields.get(key))
    if differ:
        problems.append(f"{', '.join(differ)} would read back differently")
    if parsed_body != body:
        problems.append("the text would read back differently")
    return problems


# ---------------------------------------------------------------- record rules

def record_problems(fields: dict, body: str, stem: str | None = None) -> list:
    """Everything wrong with a record-1 record. Empty means it follows record-1."""
    out = []
    fmt = one(fields, "format")
    if fmt != RECORD_FORMAT:
        out.append(f"format is {fmt!r}, not {RECORD_FORMAT!r}")
        return out
    out.extend(header_problems(fields))
    for key, values in fields.items():
        if key not in REPEATABLE and len(values) > 1:
            out.append(f"{key} appears more than once")
    request = one(fields, "request")
    match = REQUEST.match(request)
    if not match:
        out.append("request is missing or not in the form <time>--<project>--<6 letters or digits>")
    elif stem is not None and request != stem:
        out.append(f"request {request!r} does not match the file name {stem!r}")
    created = one(fields, "created")
    if not created:
        out.append("created is missing")
    elif parse_time(created) is None:
        out.append("created is not a date and time with a UTC offset")
    project = one(fields, "project")
    if project != NO_PROJECT and not valid_project_id(project):
        out.append("project is missing or not a project id (or 'none')")
    elif match and match.group(2) != project:
        out.append(f"project {project!r} does not match the request's project {match.group(2)!r}")
    subjects = [s for s in fields.get("subject", []) if s]
    if not subjects:
        out.append("at least one subject is needed")
    kind = one(fields, "kind")
    if kind in LATER_KINDS:
        out.append(f"kind {kind!r} is not part of record-1; it is defined by later help")
    elif kind not in KINDS + SPECIAL_KINDS:
        out.append(f"kind {kind!r} is not one of: {', '.join(KINDS)}")
    origin = one(fields, "from")
    if origin not in ORIGINS:
        out.append(f"from must be one of: {', '.join(ORIGINS)}")
    if origin in ("owner", "person") and not one(fields, "words"):
        out.append(f"from {origin} needs their words")
    if origin == "person" and not one(fields, "who"):
        out.append("from person needs who said it")
    if origin == "source" and not fields.get("source"):
        out.append("from source needs at least one source")
    if not one(fields, "by"):
        out.append("by (the agent or person who wrote the record) is missing")
    captured = one(fields, "captured")
    if captured and captured not in CAPTURED:
        out.append(f"captured must be one of: {', '.join(CAPTURED)}")
    corrects = one(fields, "corrects")
    if corrects:
        corrected = REQUEST.match(corrects)
        if not corrected:
            out.append("corrects is not a request id")
        elif corrects == request:
            out.append("a record cannot correct itself")
        elif match and corrected.group(2) != match.group(2):
            out.append("a correction must stay in the same project as the record it corrects")
    if kind == "withdrawal" and not corrects:
        out.append("a withdrawal needs corrects (the record it withdraws)")
    due = one(fields, "due")
    if due and parse_date(due) is None:
        out.append(f"due must be a real date like 2026-11-05, not {due!r}")
    state = one(fields, "state")
    if state and kind != "action":
        out.append("state belongs only on an action")
    elif state and state not in ACTION_STATES:
        out.append(f"state must be one of: {', '.join(ACTION_STATES)}")
    if kind in SPECIAL_KINDS:
        for key in ("act", "act-file", "act-sha256"):
            if not one(fields, key):
                out.append(f"{kind} needs {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", one(fields, "act-sha256")):
            out.append("act-sha256 must be a SHA-256 fingerprint")
        if not fields.get("source"):
            out.append(f"{kind} needs a source reference")
        if kind == "confirmation" and (origin != "owner" or not one(fields, "words")):
            out.append("confirmation needs the owner's own current words")
        if kind == "approval-reference":
            for key in ("confirmation-request", "approval-system", "approval-approver",
                        "approval-decision", "approval-time", "approval-reference"):
                if not one(fields, key):
                    out.append(f"approval-reference needs {key}")
            if one(fields, "approval-system") not in ("teams", "power-automate"):
                out.append("approval-system must be teams or power-automate")
            if one(fields, "approval-decision") not in ("accepted", "declined"):
                out.append("approval-decision must be accepted or declined")
            if not REQUEST.match(one(fields, "confirmation-request")):
                out.append("confirmation-request must be a request id")
            if parse_time(one(fields, "approval-time")) is None:
                out.append("approval-time needs a date and time with a UTC offset")
    if kind == "figure":
        for key in ("value", "period", "definition"):
            if not one(fields, key):
                out.append(f"a figure needs {key}")
        if not fields.get("source") and origin not in ("owner", "person"):
            out.append("a figure needs a source, or the words of whoever reported it")
    if not body:
        out.append("the record has no text below the header")
    return out


def is_newer_format(fields) -> bool:
    fmt = one(fields or {}, "format")
    match = re.match(r"^record-(\d+)$", fmt)
    return bool(match) and int(match.group(1)) > 1


def content_key(fields: dict, body: str, keep_identity: bool):
    """What a record says. Identity keys are compared separately or not at all."""
    skip = {"created"} if keep_identity else {"created", "request", "by", "captured", "separate-from"}
    items = tuple(sorted((key, tuple(values)) for key, values in fields.items() if key not in skip))
    return items, body


# ---------------------------------------------------------------- placing and reading

def read_back(path: Path) -> bytes:
    return path.read_bytes()


# Temporary files this command could not delete; main() names them in the result.
KEPT_TEMP_FILES: list = []


def holds_temp_file(folder: Path) -> bool:
    """True when folder holds a temporary file that a save did not remove."""
    try:
        with os.scandir(folder) as entries:
            return any(entry.name.startswith(TEMP_PREFIX) for entry in entries)
    except OSError:
        return False


def place_new(path: Path, data: bytes, direct: bool = False) -> str:
    """Create path holding data, only if nothing is there. Returns 'placed' or 'exists'.

    Uses a temporary file linked into place, so a reader never sees half a file.
    If linking is not supported, falls back to an exclusive create.

    A folder may let files be created but not deleted, and then every temporary
    file stays. So when the folder already holds one (or direct is asked for),
    the file is created directly with no temporary file; the caller's read-back
    still checks it. A temporary file that cannot be deleted goes in KEPT_TEMP_FILES.
    """
    if direct or holds_temp_file(path.parent):
        return _place_exclusive(path, data)
    tmp = path.with_name(f"{TEMP_PREFIX}{path.stem}-{os.getpid()}-{secrets.token_hex(4)}")
    try:
        with open(tmp, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
            return "placed"
        except FileExistsError:
            return "exists"
        except (NotImplementedError, OSError):
            if path.exists():
                return "exists"
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            if tmp.exists():
                KEPT_TEMP_FILES.append(tmp)
    return _place_exclusive(path, data)


def _place_exclusive(path: Path, data: bytes) -> str:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    except FileExistsError:
        return "exists"
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise PartialPlacement(str(error)) from error
    return "placed"


def pace_folder(given: str | None) -> Path:
    if given:
        return Path(given).expanduser().resolve()
    env = os.environ.get("PACE_FOLDER")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve().parents[2]
    if (here / "Pace.md").is_file() and (here / RECORD_DIR).is_dir():
        return here
    raise NoPaceFolder("Say which Pace folder to use with --pace <folder> (or set PACE_FOLDER).")


def given_file(pace: Path, given) -> Path:
    """A file named on the command line. A relative path starts from the Pace folder, as the help shows."""
    path = Path(given).expanduser()
    return (path if path.is_absolute() else pace / path).resolve()


def owner_time_zone(pace: Path) -> tuple:
    """The time zone a "Time zone:" line in Pace.md names, as (name, zone), or (None, None) when none is named.

    Raises ValueError, in plain words, when a zone is named but cannot be used here; it is never guessed.
    """
    try:
        text = (pace / "Pace.md").read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Pace.md could not be read to find it ({error})") from None
    names = sorted({match.group(1).strip().strip("`").strip() for match in map(TIME_ZONE_LINE.match, text.splitlines()) if match})
    if not names:
        return None, None
    if len(names) > 1:
        raise ValueError(f"Pace.md names more than one ({', '.join(names)}); keep one Time zone line")
    name = names[0]
    if ZoneInfo is None:
        raise ValueError(f"Pace.md names {name}, but Python {sys.version_info[0]}.{sys.version_info[1]} cannot read time zones; "
                         "Python 3.9 or later is needed")
    try:
        return name, ZoneInfo(name)
    except (KeyError, ValueError, OSError):
        raise ValueError(f"Pace.md names {name!r}, which this computer does not know as a time zone; use a name such as "
                         "Pacific/Auckland, and on Windows install Python's tzdata package") from None


def rel(pace: Path, path: Path) -> str:
    try:
        return path.relative_to(pace).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- listing Record/

def scan_record_names(record_dir: Path):
    """List Record/ by name only (no file is opened).

    Returns (records, copies, issues): records maps request -> file name,
    copies is a list of (request, file name) for conflict copies.
    """
    records, copies, issues = {}, [], []
    for entry in os.scandir(record_dir):
        name = entry.name
        if name.lower() in IGNORED_NAMES:
            continue
        if entry.is_dir():
            issues.append({"type": "unexpected-folder", "file": name,
                           "message": f"Record/{name} is a folder; records are files directly in Record/ and this folder was not read."})
            continue
        if name.startswith(TEMP_PREFIX):
            issues.append({"type": "unfinished-save", "file": name,
                           "message": (f"Record/{name} is not a record: it is a temporary file from a save that is in progress, "
                                       f"was interrupted, or was not allowed to delete it. {TEMP_NOTE}")})
            continue
        stem, ext = os.path.splitext(name)
        if ext != ".md":
            issues.append({"type": "unrecognised-file", "file": name,
                           "message": f"Record/{name} is not a record file and was not read."})
            continue
        if REQUEST.match(stem):
            records[stem] = name
            continue
        start = REQUEST_START.match(stem)
        if start:
            copies.append((start.group(0), name))
            continue
        issues.append({"type": "unrecognised-file", "file": name,
                       "message": f"Record/{name} does not have a record name and was not read."})
    return records, copies, issues


def copy_issue(request: str, name: str) -> dict:
    return {"type": "conflict-copy", "file": name, "request": request,
            "message": (f"Record/{name} looks like a second copy of record {request} (for example a sync "
                        "conflict copy). Neither copy is assumed right; compare them and ask the owner.")}


def load(record_dir: Path, name: str):
    """Open one record file. Returns a dict describing what was found."""
    path = record_dir / name
    stem = os.path.splitext(name)[0]
    try:
        data = read_back(path)
    except FileNotFoundError:
        return {"state": "missing", "file": name}
    except OSError as error:
        return {"state": "unreadable", "file": name, "problems": [str(error)]}
    fields, body, problems = parse(data)
    if fields is None:
        return {"state": "damaged", "file": name, "problems": problems, "sha256": sha256(data)}
    if is_newer_format(fields):
        return {"state": "newer-format", "file": name, "fields": fields, "body": body, "sha256": sha256(data),
                "problems": [f"written in {one(fields, 'format')}, which this tool does not read"]}
    problems = problems + record_problems(fields, body, stem)
    state = "readable" if not problems else ("damaged" if one(fields, "format") != RECORD_FORMAT else "invalid")
    return {"state": state, "file": name, "fields": fields, "body": body, "problems": problems,
            "sha256": sha256(data), "data": data}


def problem_issue(item: dict) -> dict:
    state = item["state"]
    words = {
        "damaged": "could not be read as a record",
        "invalid": "does not follow record-1",
        "unreadable": "could not be opened",
        "newer-format": "uses a newer record format",
    }[state]
    return {"type": state, "file": item["file"],
            "message": f"Record/{item['file']} {words}: {'; '.join(item.get('problems') or [])}"}


def summary(item: dict, full: bool) -> dict:
    fields = item.get("fields") or {}
    body = item.get("body") or ""
    out = {
        "request": os.path.splitext(item["file"])[0],
        "file": f"{RECORD_DIR}/{item['file']}",
        "created": one(fields, "created"),
        "project": one(fields, "project"),
        "kind": one(fields, "kind"),
        "subjects": fields.get("subject", []),
        "from": one(fields, "from"),
    }
    for key in ("who", "words", "corrects", "due", "owed-by", "for", "state", "value", "unit", "period", "act", "act-file", "act-sha256", "confirmation-request", "approval-system", "approval-approver", "approval-decision", "approval-time", "approval-reference"):
        if one(fields, key):
            out[key] = one(fields, key)
    if fields.get("source"):
        out["sources"] = fields["source"]
    first = body.split("\n", 1)[0]
    out["summary"] = first if len(first) <= 160 else first[:157] + "..."
    if item.get("problems"):
        out["problems"] = item["problems"]
    if full:
        out["fields"] = fields
        out["body"] = body
        out["sha256"] = item.get("sha256")
    return out


# ---------------------------------------------------------------- projects

def scan_projects(pace: Path):
    """Read project identity files two levels deep under Projects/."""
    base = pace / PROJECTS_DIR
    projects, issues, unlabelled = [], [], []
    if not base.is_dir():
        return projects, [{"type": "missing-folder", "message": f"{PROJECTS_DIR}/ was not found in this Pace folder."}], unlabelled

    def read_one(folder: Path, depth: int, parent_id):
        path = folder / PROJECT_FILE
        if not path.is_file():
            return None
        where = rel(pace, folder)
        try:
            fields, body, problems = parse(read_back(path))
        except OSError as error:
            issues.append({"type": "unreadable", "folder": where, "message": f"{where}/{PROJECT_FILE} could not be opened: {error}"})
            return None
        if fields is None or one(fields, "format") != PROJECT_FORMAT:
            issues.append({"type": "damaged", "folder": where,
                           "message": f"{where}/{PROJECT_FILE} is not a {PROJECT_FORMAT} file: {'; '.join(problems) or 'wrong format'}"})
            return None
        pid, parent = one(fields, "id"), one(fields, "parent")
        if not valid_project_id(pid):
            issues.append({"type": "damaged", "folder": where, "message": f"{where}/{PROJECT_FILE} has no valid id."})
            return None
        entry = {"id": pid, "name": folder.name, "parent": parent or "", "folder": where,
                 "created": one(fields, "created"), "purpose": body}
        if depth == 1 and parent != NO_PROJECT:
            issues.append({"type": "parent-mismatch", "id": pid, "folder": where,
                           "message": f"Project {pid} sits at the top of {PROJECTS_DIR}/ but names parent {parent!r}."})
        if depth == 2:
            if parent_id is None:
                issues.append({"type": "parent-mismatch", "id": pid, "folder": where,
                               "message": f"Project {pid} sits inside {folder.parent.name}, which has no Pace project id."})
            elif parent != parent_id:
                issues.append({"type": "parent-mismatch", "id": pid, "folder": where,
                               "message": f"Project {pid} sits inside {parent_id} but names parent {parent!r}."})
        projects.append(entry)
        return entry

    for top in sorted(p for p in base.iterdir() if p.is_dir()):
        first = read_one(top, 1, None)
        found_child = False
        for child in sorted(p for p in top.iterdir() if p.is_dir() and p.name != WORKING_DIR):
            if read_one(child, 2, first["id"] if first else None):
                found_child = True
            elif not (child / PROJECT_FILE).exists():
                unlabelled.append(rel(pace, child))
        if not first and not found_child and not (top / PROJECT_FILE).exists():
            unlabelled.append(rel(pace, top))
    seen: dict = {}
    for entry in projects:
        seen.setdefault(entry["id"], []).append(entry["folder"])
    for pid, folders in seen.items():
        if len(folders) > 1:
            issues.append({"type": "duplicate-id", "id": pid, "folders": folders,
                           "message": f"Project id {pid} is used by {len(folders)} folders: {', '.join(folders)}. Ask the owner which one it is."})
    return projects, issues, unlabelled


def project_ids(pace: Path) -> set:
    return {entry["id"] for entry in scan_projects(pace)[0]}


def unknown_project_issues(pace: Path, records: list) -> list:
    """Name every project id used by these records that has no project folder."""
    known = project_ids(pace)
    missing: dict = {}
    for record in records:
        project = record.get("project")
        if project and project != NO_PROJECT and project not in known:
            missing.setdefault(project, []).append(record["request"])
    return [{"type": "unknown-project", "project": project, "requests": sorted(requests),
             "message": f"Project {project} is used by {len(requests)} record(s) here but has no folder with that id under {PROJECTS_DIR}/."}
            for project, requests in sorted(missing.items())]


# ---------------------------------------------------------------- record commands

def result(status: str, message: str, ok: bool, **extra) -> tuple:
    out = {"status": status, "message": message}
    out.update(extra)
    return out, (0 if ok else 1)


def fields_from_args(args) -> tuple:
    spec = {}
    if args.spec:
        raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text(encoding="utf-8")
        spec = json.loads(raw)
        if not isinstance(spec, dict):
            raise ValueError("the spec must be a JSON object")
    flag_map = {
        "request": args.request, "created": args.created, "project": args.project, "kind": args.kind,
        "subject": args.subject, "from": args.origin, "who": args.who, "words": args.words,
        "source": args.source, "by": args.by, "captured": args.captured, "corrects": args.corrects,
        "due": args.due, "owed-by": args.owed_by, "for": args.owed_to, "state": args.state,
        "value": args.value, "unit": args.unit, "period": args.period, "definition": args.definition,
    }
    merged = {key: value for key, value in spec.items() if key not in ("body", "fields", "body_file")}
    for key, value in flag_map.items():
        if value not in (None, []):
            merged[key] = value
    extra = dict(spec.get("fields") or {})
    for item in args.field or []:
        if "=" not in item:
            raise ValueError(f"--field needs key=value, got {item!r}")
        key, value = item.split("=", 1)
        extra[key.strip()] = value
    sources = list(merged.get("source") or [])
    if isinstance(merged.get("source"), str):
        sources = [merged["source"]]
    for item in args.source_file or []:
        sources.append(source_line(args.pace_path, Path(item)))
    if sources:
        merged["source"] = sources
    body = spec.get("body", "")
    if args.body is not None:
        body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    fields: dict = {}
    for key, value in list(merged.items()) + list(extra.items()):
        if not re.match(r"^[a-z][a-z0-9-]*$", str(key)):
            raise ValueError(f"field name {key!r} must be lowercase letters, digits and hyphens")
        values = value if isinstance(value, list) else [value]
        values = [tidy_value(v) for v in values if v is not None]
        values = [v for v in values if v]
        if values:
            fields[key] = values
    return fields, tidy_body(body)


def source_line(pace: Path, path: Path) -> str:
    """A source reference for a file: its place (inside the Pace folder if it is there) and fingerprint."""
    path = given_file(pace, path)
    data = path.read_bytes()
    where = rel(pace, path)
    return f"{where} sha256:{sha256(data)}"


def same_record(existing: bytes, fields: dict, body: str):
    """Compare an existing file with what we meant to save. Returns differing field names, or None if the same."""
    old_fields, old_body, problems = parse(existing)
    if old_fields is None:
        return ["(the existing file is not readable as a record)"]
    differ = []
    keys = (set(old_fields) | set(fields)) - {"created"}
    for key in sorted(keys):
        if old_fields.get(key) != fields.get(key):
            differ.append(key)
    old_time, new_time = parse_time(one(old_fields, "created")), parse_time(one(fields, "created"))
    if old_time is None or new_time is None or old_time != new_time:
        differ.append("created")
    if old_body != body:
        differ.append("text")
    return differ or None


def find_duplicates(record_dir: Path, fields: dict, body: str, request: str) -> list:
    """Records in the same project, made close to this request, saying the same thing."""
    project = one(fields, "project")
    when = request_time(request)
    target = content_key(fields, body, keep_identity=False)
    names, _, _ = scan_record_names(record_dir)
    found = []
    for stem, name in names.items():
        match = REQUEST.match(stem)
        if stem == request or match.group(2) != project:
            continue
        if abs(request_time(stem) - when) > DUPLICATE_WINDOW:
            continue
        item = load(record_dir, name)
        if item.get("fields") and content_key(item["fields"], item["body"], keep_identity=False) == target:
            found.append(stem)
    return sorted(found)


def corrections_of(record_dir: Path, request: str, project: str, all_projects=False):
    """Scan records in the project made from a day before `request` on. Returns (map corrects->list, opened, issues)."""
    names, copies, issues = scan_record_names(record_dir)
    start = request_time(request) - dt.timedelta(days=1)
    by_predecessor: dict = {}
    opened = 0
    for stem, name in sorted(names.items()):
        match = REQUEST.match(stem)
        if not all_projects and match.group(2) != project:
            continue
        if request_time(stem) < start:
            continue
        item = load(record_dir, name)
        opened += 1
        if item["state"] not in ("readable", "invalid"):
            if item["state"] != "missing":
                issues.append(problem_issue(item))
            continue
        corrects = one(item["fields"], "corrects")
        if corrects:
            by_predecessor.setdefault(corrects, []).append(stem)
    for request_id, name in copies:
        if all_projects or REQUEST_START.match(name).group(2) == project:
            issues.append(copy_issue(request_id, name))
    return by_predecessor, opened, issues


def cmd_new_request(args) -> tuple:
    project = args.project
    if project != NO_PROJECT and not valid_project_id(project):
        return result("not-made", f"{project!r} is not a project id. Use lowercase letters, digits and single hyphens, or 'none'.", False)
    at = None
    if args.at:
        at = parse_time(args.at)
        if at is None:
            return result("not-made", "--at needs a date and time with a UTC offset.", False)
    request = make_request(project, at)
    return result("made", f"Use request {request} for this record, and the same request again if the save has to be retried.",
                  True, request=request, file=f"{RECORD_DIR}/{request}.md")


def cmd_create(args) -> tuple:
    pace = pace_folder(args.pace)
    args.pace_path = pace
    try:
        fields, body = fields_from_args(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return result("not-saved", f"Not saved: {error}", False)
    if one(fields, "kind") in SPECIAL_KINDS:
        return result("not-saved", "Use confirm or approval-reference for this kind; ordinary create cannot confirm an act.", False)
    return save_record(pace, args, fields, body)


def save_record(pace: Path, args, fields: dict, body: str) -> tuple:
    record_dir = pace / RECORD_DIR
    fields["format"] = [RECORD_FORMAT]
    request = one(fields, "request")
    if not REQUEST.match(request):
        return result("not-saved", "Not saved: a request id is needed first (use new-request), so a retry can be recognised.", False)
    if "created" not in fields:
        fields["created"] = [local_text(request_time(request))]
    if args.not_a_duplicate and "separate-from" not in fields and record_dir.is_dir():
        # Keep the owner's answer, so later searches stop asking about the same records.
        separate = find_duplicates(record_dir, fields, body, request)
        if separate:
            fields["separate-from"] = [" ".join(separate)]
    problems = record_problems(fields, body, request)
    if problems:
        return result("not-saved", "Not saved: " + "; ".join(problems) + ".", False, request=request, problems=problems)
    data = render(fields, body, RECORD_ORDER)
    unreadable = read_back_problems(data, fields, body)
    if unreadable:
        return result("not-saved", "Not saved: it would not read back as written (" + "; ".join(unreadable) + "). Nothing was written.",
                      False, request=request, problems=unreadable)
    if len(data) > MAX_RECORD_BYTES:
        return result("not-saved", "Not saved: the record is too long. Keep long material in a project's Documents folder and refer to it.", False, request=request)
    if not record_dir.is_dir():
        return result("not-saved", f"Not saved: {RECORD_DIR}/ was not found in {pace}. Check the Pace folder and that it is available here.", False, request=request)
    project = one(fields, "project")
    if project != NO_PROJECT and not args.allow_unknown_project and project not in project_ids(pace):
        return result("not-saved", f"Not saved: project {project} is not defined under {PROJECTS_DIR}/. Create the project first, use 'none', or check the id.", False, request=request)

    path = record_dir / f"{request}.md"
    file_rel = f"{RECORD_DIR}/{request}.md"

    def existing_outcome(retries: int = 3) -> tuple:
        differ = None
        for attempt in range(retries):
            try:
                existing = read_back(path)
            except OSError as error:
                return result("placed-not-confirmed",
                              f"Not confirmed: {file_rel} exists but could not be read back ({error}). Nothing was overwritten.",
                              False, request=request, file=file_rel)
            differ = same_record(existing, fields, body)
            if differ is None:
                return result("already-saved",
                              f"Already saved: {file_rel} holds this record from an earlier attempt and was read back. Nothing new was written. {CLOUD_NOTE}",
                              True, request=request, file=file_rel, sha256=sha256(existing))
            if attempt + 1 < retries:
                time.sleep(0.1 * (attempt + 1))
        return result("conflict",
                      (f"Conflict: {file_rel} already holds different content for this request ({', '.join(differ)}). "
                       "Nothing was overwritten or renamed. If this is a different record, save it under a new request; "
                       "if it fixes the saved one, save a new record that corrects it."),
                      False, request=request, file=file_rel, differs=differ)

    if path.exists():
        return existing_outcome()

    corrects = one(fields, "corrects")
    if corrects:
        before = load(record_dir, f"{corrects}.md")
        if before["state"] == "missing":
            return result("not-saved", f"Not saved: the record it corrects ({corrects}) was not found in {RECORD_DIR}/ here.", False, request=request)
        if before["state"] not in ("readable", "invalid"):
            return result("not-saved",
                          f"Not saved: the record it corrects ({corrects}) cannot be relied on ({'; '.join(before.get('problems') or [])}).",
                          False, request=request)
        if one(before["fields"], "project") != project:
            return result("not-saved", f"Not saved: {corrects} belongs to project {one(before['fields'], 'project')}; a correction stays in the same project.", False, request=request)
        later, _, _ = corrections_of(record_dir, corrects, project)
        if later.get(corrects):
            newer = sorted(later[corrects])
            if len(newer) > 1:
                advice = (f"{', '.join(newer)} are competing accounts; ask the owner which stands. "
                          "To settle competing accounts, correct the one that stands and withdraw the other.")
            else:
                advice = f"Correct the latest version instead; history --request {corrects} shows it."
            return result("not-saved", f"Not saved: {corrects} was already corrected by {', '.join(newer)}. {advice}",
                          False, request=request, corrected_by=newer)

    if not args.not_a_duplicate:
        duplicates = find_duplicates(record_dir, fields, body, request)
        if duplicates:
            return result("possible-duplicate",
                          (f"Not saved: {', '.join(duplicates)} already says the same thing for this project. "
                           "Ask whether this is a separate record; if it is, save again with --not-a-duplicate."),
                          False, request=request, duplicates=duplicates)

    try:
        outcome = place_new(path, data)
    except PartialPlacement as error:
        return result("placed-not-confirmed",
                      f"Not confirmed: {file_rel} was created but writing it failed ({error}). It may be incomplete; nothing was overwritten.",
                      False, request=request, file=file_rel)
    except OSError as error:
        return result("not-saved", f"Not saved: could not write in {RECORD_DIR}/ ({error}).", False, request=request)
    if outcome == "exists":
        return existing_outcome()

    try:
        back = read_back(path)
    except OSError as error:
        return result("placed-not-confirmed",
                      f"Placed {file_rel} but could not read it back ({error}), so it is not confirmed saved.",
                      False, request=request, file=file_rel)
    if back != data or read_back_problems(back, fields, body):
        return result("placed-not-confirmed",
                      f"Placed {file_rel} but what reads back is not what was written, so it is not confirmed saved.",
                      False, request=request, file=file_rel)
    extra = {}
    message = f"Saved and read back: {file_rel}. {CLOUD_NOTE}"
    if not args.not_a_duplicate:
        late = find_duplicates(record_dir, fields, body, request)
        if late:
            extra["duplicates"] = late
            message += f" Another save of the same content appeared at the same time: {', '.join(late)}. Ask the owner which to keep."
    return result("saved", message, True, request=request, file=file_rel, sha256=sha256(data), **extra)


def cmd_read(args) -> tuple:
    pace = pace_folder(args.pace)
    record_dir = pace / RECORD_DIR
    request = args.request
    if not REQUEST.match(request or ""):
        return result("not-read", "That is not a request id.", False)
    if not record_dir.is_dir():
        return result("not-read", f"{RECORD_DIR}/ was not found in {pace}. Check the Pace folder and that it is available here.", False)
    item = load(record_dir, f"{request}.md")
    copies = []
    if record_dir.is_dir():
        _, all_copies, _ = scan_record_names(record_dir)
        copies = [copy_issue(r, n) for r, n in all_copies if r == request]
    if item["state"] == "missing":
        return result("not-found",
                      (f"No file for {request} in {RECORD_DIR}/ as it can be seen here now. That does not show it was never saved: "
                       "it may not have arrived on this computer yet, or it may have been moved or removed."),
                      False, request=request, issues=copies)
    if item["state"] != "readable":
        return result(item["state"], problem_issue(item)["message"], False, request=request, issues=copies)
    record = summary(item, full=True)
    status, message = "found", f"Found and read back: {record['file']}."
    if copies:
        status, message = "conflict", f"Found {record['file']}, but another copy of it is also there. Compare them before relying on either."
    return result(status, message, status == "found", record=record, issues=copies)


def name_filter(stem: str, args) -> bool:
    match = REQUEST.match(stem)
    if args.project and match.group(2) != args.project:
        return False
    when = request_time(stem).date()
    if args.since and when < args.since_date - dt.timedelta(days=1):
        return False
    if args.until and when > args.until_date + dt.timedelta(days=1):
        return False
    return True


def content_filter(item: dict, args) -> bool:
    fields, body = item["fields"], item["body"]
    if args.kind and one(fields, "kind") not in args.kind:
        return False
    if args.origin and one(fields, "from") != args.origin:
        return False
    if args.subject:
        wanted = args.subject.lower()
        if not any(wanted in subject.lower() for subject in fields.get("subject", [])):
            return False
    created = parse_time(one(fields, "created"))
    # The day the record was made: in the owner's time zone when Pace.md names one, else as the record wrote it.
    day = None if created is None else (created.astimezone(args.zone) if args.zone else created).date()
    if args.since and (day is None or day < args.since_date):
        return False
    if args.until and (day is None or day > args.until_date):
        return False
    if args.text:
        haystack = "\n".join([body] + [v for values in fields.values() for v in values]).lower()
        if args.text.lower() not in haystack:
            return False
    return True


def cmd_find(args) -> tuple:
    pace = pace_folder(args.pace)
    record_dir = pace / RECORD_DIR
    if not record_dir.is_dir():
        return result("not-read", f"{RECORD_DIR}/ was not found in {pace}.", False)
    for key in ("since", "until"):
        value = getattr(args, key)
        day = parse_date(value) if value else None
        if value and day is None:
            return result("not-read", f"--{key} needs a real date like 2026-10-01, not {value!r}.", False)
        setattr(args, f"{key}_date", day)
    args.zone, zone_name = None, None
    if args.since or args.until:
        try:
            zone_name, args.zone = owner_time_zone(pace)
        except ValueError as error:
            return result("not-read", f"Could not use your time zone: {error}. No dates were compared, and no time zone was guessed.", False)
    if args.cursor and not REQUEST.match(args.cursor):
        return result("not-read", "That cursor is not one this tool gave out.", False)
    names, copies, issues = scan_record_names(record_dir)
    candidates = sorted((stem for stem in names if name_filter(stem, args)), reverse=True)
    if args.cursor:
        candidates = [stem for stem in candidates if stem < args.cursor]
    found, opened, stopped_at = [], 0, None
    corrected_by: dict = {}
    content_issues = []
    keys: dict = {}
    separate: dict = {}
    for index, stem in enumerate(candidates):
        if len(found) >= args.limit or opened >= args.max_open:
            stopped_at = candidates[index - 1] if index else None
            break
        item = load(record_dir, names[stem])
        opened += 1
        if item["state"] in ("damaged", "unreadable", "newer-format"):
            content_issues.append(problem_issue(item))
            continue
        if item["state"] == "missing":
            content_issues.append({"type": "vanished", "file": names[stem],
                                   "message": f"{RECORD_DIR}/{names[stem]} was listed but had gone when opened."})
            continue
        if item["state"] == "invalid":
            content_issues.append(problem_issue(item))
        corrects = one(item["fields"], "corrects")
        if corrects:
            corrected_by.setdefault(corrects, []).append(stem)
        key = content_key(item["fields"], item["body"], keep_identity=False)
        keys.setdefault(key, []).append(stem)
        separate[stem] = set(" ".join(item["fields"].get("separate-from", [])).split())
        if content_filter(item, args):
            found.append(summary(item, args.full))
    for record in found:
        later = corrected_by.get(record["request"])
        if later:
            record["corrected_by_seen"] = sorted(later)
    for stems in keys.values():
        stems = sorted(stems)
        # A pair the owner said is separate (separate-from in either record) is not flagged again.
        close = sorted({s for i, a in enumerate(stems) for b in stems[i + 1:]
                        if request_time(b) - request_time(a) <= DUPLICATE_WINDOW
                        and b not in separate[a] and a not in separate[b] for s in (a, b)})
        if close:
            content_issues.append({"type": "possible-duplicate", "requests": close,
                                   "message": f"These records say the same thing within a week: {', '.join(close)}. Ask the owner which to keep."})
    for request_id, name in copies:
        if name_filter(request_id, args):
            content_issues.append(copy_issue(request_id, name))
    next_cursor = stopped_at
    problems = [i for i in content_issues if i["type"] in ("damaged", "unreadable", "vanished", "newer-format", "conflict-copy")]
    scope = describe_scope(args)
    if next_cursor:
        coverage = (f"Partial: checked {opened} of {len(candidates)} record files {scope}, newest first. "
                    f"More may match; continue with --cursor {next_cursor}.")
    elif problems:
        coverage = (f"Checked every record file {scope} that is visible here ({opened} opened), "
                    f"but {len(problems)} could not be relied on (see issues), so this is not a complete answer.")
    else:
        coverage = (f"Checked every record file {scope} that is visible here ({opened} opened). "
                    "Files not yet on this computer, or removed, are not included.")
    if args.since or args.until:
        coverage += (f" Dates are compared in {zone_name} time, from Pace.md." if zone_name else
                     " Dates are each record's own written date, because Pace.md names no time zone.")
    if found:
        coverage += " Corrections are shown only where seen in this read; use history for one record's full story."
    status = "partial" if next_cursor else ("found" if found else "none-found")
    message = f"{len(found)} record(s) on this page. {coverage}"
    return result(status, message, True, records=found, next_cursor=next_cursor, time_zone=zone_name,
                  coverage={"files_in_record": len(names), "candidates": len(candidates), "opened": opened,
                            "complete": not next_cursor and not problems, "statement": coverage},
                  issues=issues + content_issues + unknown_project_issues(pace, found))


def describe_scope(args) -> str:
    parts = []
    if args.project:
        parts.append(f"for project {args.project}")
    if args.since:
        parts.append(f"from {args.since}")
    if args.until:
        parts.append(f"to {args.until}")
    return " ".join(parts) if parts else "in Record/"


def cmd_history(args) -> tuple:
    pace = pace_folder(args.pace)
    record_dir = pace / RECORD_DIR
    request = args.request
    if not REQUEST.match(request or ""):
        return result("not-read", "That is not a request id.", False)
    start = load(record_dir, f"{request}.md")
    if start["state"] == "missing":
        return result("not-found", f"No file for {request} in {RECORD_DIR}/ as it can be seen here now. It may not have arrived on this computer, or it may have been moved or removed.", False, request=request)
    if start["state"] not in ("readable", "invalid"):
        return result(start["state"], problem_issue(start)["message"], False, request=request)
    project = one(start["fields"], "project")
    issues, missing = [], []
    records = {request: start}
    # Earlier versions: follow corrects back by direct lookups.
    root, cursor, seen = request, start, {request}
    while one(cursor["fields"], "corrects"):
        before = one(cursor["fields"], "corrects")
        if before in seen:
            issues.append({"type": "loop", "message": f"The corrections loop back to {before}."})
            break
        seen.add(before)
        item = load(record_dir, f"{before}.md")
        if item["state"] == "missing":
            missing.append(before)
            issues.append({"type": "missing", "request": before,
                           "message": f"{root} corrects {before}, but no file for {before} is in {RECORD_DIR}/ here."})
            break
        if item["state"] not in ("readable", "invalid"):
            issues.append(problem_issue(item))
            break
        records[before] = item
        root, cursor = before, item
    # Later versions: scan the project from the earliest version on.
    later, opened, scan_issues = corrections_of(record_dir, root, project, all_projects=args.all_projects)
    issues.extend(scan_issues)
    queue = [root]
    tree: dict = {}
    while queue:
        node = queue.pop(0)
        children = sorted(later.get(node, []))
        tree[node] = children
        for child in children:
            if child not in records:
                item = load(record_dir, f"{child}.md")
                if item["state"] in ("readable", "invalid"):
                    records[child] = item
            if child not in tree:
                queue.append(child)
    def stands(node, path=()) -> bool:
        """True while an account at or after node still stands (or could not be read)."""
        children = [child for child in tree.get(node, []) if child not in path]
        if not children:
            return node not in records or one(records[node]["fields"], "kind") != "withdrawal"
        return any(stands(child, path + (node,)) for child in children)

    # Competing corrections are settled once every branch but one ends in a withdrawal.
    for node, children in tree.items():
        standing = [child for child in children if stands(child)]
        if len(standing) > 1:
            issues.append({"type": "competing-corrections", "request": node, "requests": standing,
                           "message": (f"{node} has {len(standing)} competing corrections ({', '.join(standing)}). "
                                       "Neither is assumed to be the current account; ask the owner which stands, then "
                                       "correct the one that stands and withdraw the other.")})
    leaves = [node for node, children in tree.items() if not children]
    current = [node for node in leaves if node in records and one(records[node]["fields"], "kind") != "withdrawal"]
    withdrawn = [node for node in leaves if node in records and one(records[node]["fields"], "kind") == "withdrawal"]
    versions = [summary(records[node], args.full) for node in sorted(records)]
    issues.extend(unknown_project_issues(pace, versions[:1]))
    scope = "every project" if args.all_projects else f"project {project}"
    coverage = (f"Looked for corrections among {opened} record files in {scope} made from a day before "
                f"{root} on, as visible here. A correction not yet on this computer would not be seen.")
    # A file that could not be relied on might itself be a correction, so nothing is settled.
    unreliable = [i for i in issues if i["type"] in ("damaged", "unreadable", "newer-format", "conflict-copy", "loop")]
    if missing or unreliable:
        coverage += " Some material is missing or unreliable (see issues), so this history is incomplete."
    if len(current) > 1:
        status, message = "conflict", f"Competing current accounts: {', '.join(current)}. Show both; neither is assumed right."
    elif current:
        status, message = "found", f"Current account: {current[0]}."
    elif withdrawn:
        status, message = "withdrawn", f"Withdrawn by {', '.join(withdrawn)}; nothing replaces it."
    else:
        status, message = "found", "No current account could be identified."
    if (missing or unreliable) and status in ("found", "withdrawn"):
        status = "incomplete"
    if missing:
        message += f" Missing earlier record(s): {', '.join(missing)}."
    if unreliable:
        message += " Some files could not be relied on (see issues); any of them might be a later correction, so this is not settled."
    return result(status, message + " " + coverage, status in ("found", "withdrawn"),
                  request=request, current=current, withdrawn_by=withdrawn, versions=versions,
                  corrections=tree, missing=missing, coverage=coverage, issues=issues)


def cmd_listing(args) -> tuple:
    pace = pace_folder(args.pace)
    record_dir = pace / RECORD_DIR
    if not record_dir.is_dir():
        return result("not-read", f"{RECORD_DIR}/ was not found in {pace}.", False)
    names, copies, issues = scan_record_names(record_dir)
    files = {}
    for stem, name in sorted(names.items()):
        entry = {"size": (record_dir / name).stat().st_size}
        # A kept listing always has fingerprints, so a later compare can see an edit.
        if args.digests or args.compare or args.save:
            try:
                entry["sha256"] = sha256(read_back(record_dir / name))
            except OSError:
                entry["sha256"] = None
        files[name] = entry
    listing = {"format": "record-listing-1", "made": local_text(now_utc()), "files": files}
    if args.compare:
        earlier = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        old = earlier.get("files") or {}
        gone = sorted(set(old) - set(files))
        new = sorted(set(files) - set(old))
        changed = sorted(n for n in set(old) & set(files)
                         if old[n].get("sha256") and old[n].get("sha256") != files[n].get("sha256"))
        unchecked = sorted(n for n in set(old) & set(files) if not old[n].get("sha256"))
        parts = []
        if gone:
            parts.append(f"{len(gone)} file(s) in the earlier listing are not here now (removed, moved or not on this computer)")
        if changed:
            parts.append(f"{len(changed)} file(s) changed since the earlier listing, although records are never edited")
        status = "differs" if gone or changed else ("unchecked" if unchecked else "matches")
        made = earlier.get("made", "undated")
        if parts:
            message = "; ".join(parts) + "."
        elif unchecked:
            message = f"Every file in the earlier listing ({made}) is still here."
        else:
            message = f"Every file in the earlier listing ({made}) is still here unchanged."
        if unchecked:
            message += (f" {len(unchecked)} file(s) had no fingerprint in the earlier listing, so only their presence was checked, "
                        "not whether they changed. Save a new listing to check for changes from now on.")
        if new:
            message += f" {len(new)} file(s) are new since then."
        return result(status, message, status == "matches", missing=gone, changed=changed, new=new,
                      unchecked=unchecked, issues=issues + [copy_issue(r, n) for r, n in copies])
    if args.save:
        target = Path(args.save).expanduser().resolve()
        if record_dir.resolve() in target.parents:
            return result("not-saved", "A listing is not a record; save it outside Record/.", False)
        data = (json.dumps(listing, indent=1, sort_keys=True) + "\n").encode("utf-8")
        try:
            outcome = place_new(target, data)
        except OSError as error:
            return result("not-saved", f"Listing not saved: {error}", False)
        if outcome == "exists":
            return result("not-saved", f"Listing not saved: {target} already exists and was not overwritten.", False)
        if read_back(target) != data:
            return result("placed-not-confirmed", f"Listing placed at {target} but did not read back the same.", False)
        message = f"Listing of {len(files)} record file(s), with their fingerprints, saved and read back at {target}. Keep it somewhere separate to compare later."
        unopened = sorted(name for name, entry in files.items() if entry.get("sha256") is None)
        if unopened:
            message += f" {len(unopened)} file(s) could not be opened, so they have no fingerprint and a later compare checks only that they are there."
        return result("saved", message, True, file=str(target), count=len(files), unopened=unopened)
    return result("listed", f"{len(files)} record file(s) visible here now.", True, listing=listing,
                  issues=issues + [copy_issue(r, n) for r, n in copies])


# ---------------------------------------------------------------- exact-act confirmations

def act_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if not data:
        raise ValueError("the exact act file is empty")
    return data


def act_location(pace: Path, path: str) -> str:
    return rel(pace, given_file(pace, path))


def confirmation_file(pace: Path, recorded: str) -> Path:
    # A recorded relative path always starts from the Pace folder.
    return (pace / recorded).resolve()


def check_act(pace: Path, fields: dict, path: str | None = None) -> str | None:
    recorded = one(fields, "act-file")
    expected = confirmation_file(pace, recorded)
    if path and given_file(pace, path) != expected:
        return "The supplied act file is not the one named in the record."
    try:
        current = sha256(act_bytes(expected))
    except (OSError, ValueError) as error:
        return f"The exact act file could not be checked: {error}."
    if current != one(fields, "act-sha256"):
        return "The exact act content has changed since it was shown and recorded. Obtain new words for the changed act."
    return None


def cmd_propose(args) -> tuple:
    pace = pace_folder(args.pace)
    try:
        digest = sha256(act_bytes(given_file(pace, args.act_file)))
    except (OSError, ValueError) as error:
        return result("pending", f"Could not show the proposed act: {error}", False)
    return result("proposed", "Proposed only. Show the exact file and its source or before-and-after to the owner; no confirmation has been recorded.",
                  True, act=args.act, act_file=act_location(pace, args.act_file), act_sha256=digest)


def cmd_confirm(args) -> tuple:
    pace = pace_folder(args.pace)
    if not args.owner_current or not tidy_value(args.owner_words or ""):
        return result("proposed", "No current, explicit owner words for this exact act. A source quote or a guessed yes is not a confirmation.", False)
    if not args.source:
        return result("proposed", "Show and name at least one source or before-and-after for this act before requesting confirmation.", False)
    if not re.fullmatch(r"[0-9a-f]{64}", args.shown_sha256 or ""):
        return result("proposed", "The fingerprint of the exact content shown to the owner is needed.", False)
    location = act_location(pace, args.act_file)
    try:
        digest = sha256(act_bytes(given_file(pace, args.act_file)))
    except (OSError, ValueError) as error:
        return result("pending", f"Cannot check the act now: {error}", False)
    if digest != args.shown_sha256:
        return result("proposed", "The act has changed since it was shown. Show the new act and obtain new owner words.", False)
    fields = {"request": [args.request], "project": [args.project], "kind": ["confirmation"],
              "subject": [tidy_value(args.subject)], "from": ["owner"],
              "words": [tidy_value(args.owner_words)], "source": [tidy_value(s) for s in args.source],
              "by": [tidy_value(args.by)], "act": [tidy_value(args.act)],
              "act-file": [location], "act-sha256": [digest]}
    if args.corrects:
        fields["corrects"] = [args.corrects]
    out, code = save_record(pace, args, fields, "Owner's current words above confirm the exact act named here, not any later changed content.")
    if code or out["status"] not in ("saved", "already-saved"):
        out["confirmation_state"] = "pending"
        return out, 1
    # A file could change during the save. Do not return confirmed until the act and record read back together.
    checked, check_code = confirmation_state(pace, args.request, args.act_file)
    if check_code or checked["status"] != "confirmed":
        checked["save_status"] = out["status"]
        return checked, 1
    checked["save_status"] = out["status"]
    return checked, 0


def confirmation_state(pace: Path, request: str, path: str | None = None) -> tuple:
    if not REQUEST.match(request or ""):
        return result("pending", "Not a record request id.", False)
    record_dir = pace / RECORD_DIR
    if not record_dir.is_dir():
        return result("pending", "Record/ is not available for read-back.", False)
    item = load(record_dir, f"{request}.md")
    if item["state"] != "readable" or one(item.get("fields") or {}, "kind") != "confirmation":
        return result("pending", "No readable exact-act confirmation record for this request. A create receipt alone is not confirmation.", False)
    names, copies, _ = scan_record_names(record_dir)
    if any(r == request for r, _ in copies):
        return result("pending", "A competing copy exists for this record; compare it before relying on either.", False)
    fields = item["fields"]
    later, _, issues = corrections_of(record_dir, request, one(fields, "project"))
    # Damaged or unreadable files in the scanned project could hide a correction.
    if any(i.get("type") in ("damaged", "unreadable", "newer-format", "conflict-copy") for i in issues):
        return result("pending", "The correction search has unreadable or competing files; no current confirmation can be established here.", False, issues=issues)
    if later.get(request):
        return result("superseded", "This confirmation has a later correction or withdrawal. Read the later record and obtain fresh words if the act changed.",
                      False, corrected_by=sorted(later[request]))
    problem = check_act(pace, fields, path)
    if problem:
        return result("pending", problem, False, request=request)
    return result("confirmed", f"Confirmed (recorded): Record/{request}.md was read back and the exact act still matches. {CLOUD_NOTE}",
                  True, request=request, act_sha256=one(fields, "act-sha256"))


def cmd_confirmation_status(args) -> tuple:
    pace = pace_folder(args.pace)
    out, code = confirmation_state(pace, args.request, args.act_file)
    if args.reference_request:
        reference, ref_code = approval_reference_state(pace, args.reference_request, args.request)
        out["client_approval_reference"] = reference
        if ref_code:
            return result("pending", "The client approval reference could not be checked; do not claim a client decision for this act.",
                          False, owner_confirmation=out, client_approval_reference=reference)
    return out, code


def approval_reference_state(pace: Path, request: str, linked: str) -> tuple:
    if not REQUEST.match(request or ""):
        return result("pending", "Not a record request id.", False)
    item = load(pace / RECORD_DIR, f"{request}.md")
    fields = item.get("fields") or {}
    if item["state"] != "readable" or one(fields, "kind") != "approval-reference" or one(fields, "confirmation-request") != linked:
        return result("pending", "No readable client approval reference linked to this confirmation.", False)
    current, current_code = confirmation_state(pace, linked)
    if current_code:
        return result("pending", "The linked owner confirmation is not current or its exact content cannot be checked.", False)
    confirmed = load(pace / RECORD_DIR, f"{linked}.md")
    if confirmed["state"] != "readable" or one(confirmed["fields"], "kind") != "confirmation":
        return result("pending", "The linked confirmation could not be read back.", False)
    if (one(fields, "act-sha256") != one(confirmed["fields"], "act-sha256") or
            one(fields, "act-file") != one(confirmed["fields"], "act-file") or
            one(fields, "act") != one(confirmed["fields"], "act")):
        return result("pending", "Client reference and confirmation name different acts or fingerprints.", False)
    if check_act(pace, fields):
        return result("pending", "The exact content no longer matches the client's recorded reference.", False)
    names, copies, _ = scan_record_names(pace / RECORD_DIR)
    if any(r == request for r, _ in copies):
        return result("pending", "The client reference has a competing copy.", False)
    later, _, issues = corrections_of(pace / RECORD_DIR, request, one(fields, "project"))
    if later.get(request) or any(i.get("type") in ("damaged", "unreadable", "newer-format", "conflict-copy") for i in issues):
        return result("pending", "The client reference was corrected or its history cannot be checked.", False)
    decision = one(fields, "approval-decision")
    return result("reference-recorded", f"Client {decision} decision reference recorded and content checked locally. This tool has not contacted the client's approval system or verified the account.",
                  True, decision=decision, approver=one(fields, "approval-approver"), reference=one(fields, "approval-reference"))


def cmd_approval_reference(args) -> tuple:
    pace = pace_folder(args.pace)
    if not args.available:
        return result("pending", "Client approval result unavailable. No client reference was saved or inferred.", False)
    if args.decision not in ("accepted", "declined") or args.system not in ("teams", "power-automate") or not parse_time(args.decision_time):
        return result("pending", "A client system, accepted or declined decision, and decision time with UTC offset are needed.", False)
    owner, code = confirmation_state(pace, args.confirmation_request)
    if code:
        return result("pending", "The linked exact act is not currently confirmed; do not attach a client decision to changed content.", False, owner_confirmation=owner)
    original = load(pace / RECORD_DIR, f"{args.confirmation_request}.md")["fields"]
    if args.project != one(original, "project"):
        return result("pending", "Client reference must stay in the confirmation's project.", False)
    fields = {"request": [args.request], "project": [args.project], "kind": ["approval-reference"],
              "subject": [tidy_value(args.subject)], "from": ["agent"], "by": [tidy_value(args.by)],
              "source": [tidy_value(args.source)], "act": [one(original, "act")],
              "act-file": [one(original, "act-file")], "act-sha256": [one(original, "act-sha256")],
              "confirmation-request": [args.confirmation_request], "approval-system": [args.system],
              "approval-approver": [tidy_value(args.approver)], "approval-decision": [args.decision],
              "approval-time": [args.decision_time], "approval-reference": [tidy_value(args.reference)]}
    out, code = save_record(pace, args, fields, "Reference supplied from the client's approval system; no live account or integration was checked by Pace.")
    if code:
        out["confirmation_state"] = "pending"
        return out, 1
    checked, check_code = approval_reference_state(pace, args.request, args.confirmation_request)
    return checked, check_code


# ---------------------------------------------------------------- project commands

BAD_FOLDER = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def cmd_project_new(args) -> tuple:
    pace = pace_folder(args.pace)
    pid, parent, name = args.id, args.parent or NO_PROJECT, (args.name or "").strip()
    if not valid_project_id(pid):
        return result("not-saved", f"Not saved: {pid!r} is not a usable project id (lowercase letters, digits and single hyphens, up to {MAX_ID} characters, not 'none').", False)
    if not name or BAD_FOLDER.search(name) or name.endswith((".", " ")) or name in (WORKING_DIR,):
        return result("not-saved", f"Not saved: {name!r} cannot be used as a folder name.", False)
    if not args.by:
        return result("not-saved", "Not saved: --by (who is creating the project) is needed.", False)
    folders, seen = [], set()
    for given in args.folder or []:
        folder_name = (given or "").strip()
        if not folder_name or BAD_FOLDER.search(folder_name) or folder_name.endswith((".", " ")) or folder_name in (".", ".."):
            return result("not-saved", f"Not saved: {folder_name!r} cannot be used as a folder name inside {WORKING_DIR}/. Nothing was created.", False)
        if folder_name.casefold() == ARCHIVE_DIR.casefold():
            return result("not-saved", f"Not saved: {ARCHIVE_DIR}/ is not made with a project. It appears beside a working file when its "
                                       "first version goes out. Nothing was created.", False)
        if folder_name.casefold() in seen:
            return result("not-saved", f"Not saved: the folder {folder_name!r} is named twice. Nothing was created.", False)
        seen.add(folder_name.casefold())
        folders.append(folder_name)
    base = pace / PROJECTS_DIR
    if not base.is_dir():
        return result("not-saved", f"Not saved: {PROJECTS_DIR}/ was not found in {pace}.", False)
    projects, issues, _ = scan_projects(pace)
    by_id = {}
    for entry in projects:
        by_id.setdefault(entry["id"], []).append(entry)
    if parent == NO_PROJECT:
        folder = base / name
    else:
        parents = by_id.get(parent, [])
        if len(parents) != 1:
            return result("not-saved", f"Not saved: parent {parent} {'is not defined' if not parents else 'is defined more than once'} under {PROJECTS_DIR}/.", False)
        if parents[0]["parent"] != NO_PROJECT or parents[0]["folder"].count("/") != 1:
            return result("not-saved", f"Not saved: {parent} is itself inside another project; a project can only be one level below a parent.", False)
        folder = pace / parents[0]["folder"] / name
    where = rel(pace, folder)
    id_path = folder / PROJECT_FILE
    if id_path.exists():
        try:
            fields, _, _ = parse(read_back(id_path))
        except OSError as error:
            return result("placed-not-confirmed", f"Not confirmed: {where}/{PROJECT_FILE} exists but could not be read ({error}).", False)
        if fields and one(fields, "format") == PROJECT_FORMAT and one(fields, "id") == pid and one(fields, "parent") == parent:
            if not folders:
                return result("already-saved", f"Already saved: {where} is project {pid}. Nothing new was written.", True, id=pid, folder=where)
            made, missed = make_project_folders(folder, folders)
            return result("already-saved", f"Already saved: {where} is project {pid}; its project file was not written again. "
                          + folders_message(where, made, missed), not missed, id=pid, folder=where, folders=made,
                          **({"folders_not_made": missed} if missed else {}))
        return result("conflict", f"Conflict: {where} already has a different project identity. Nothing was overwritten.", False, folder=where)
    if pid in by_id:
        used = ", ".join(entry["folder"] for entry in by_id[pid])
        return result("not-saved", f"Not saved: project id {pid} is already used by {used}.", False, id=pid)
    fields = {"format": [PROJECT_FORMAT], "id": [pid], "parent": [parent],
              "created": [local_text(now_utc())], "by": [tidy_value(args.by)]}
    purpose = tidy_body(args.purpose or "")
    data = render(fields, purpose, PROJECT_ORDER)
    unreadable = header_problems(fields) or read_back_problems(data, fields, purpose)
    if unreadable:
        return result("not-saved", f"Not saved: {where}/{PROJECT_FILE} would not read back as written ({'; '.join(unreadable)}). Nothing was created.",
                      False, problems=unreadable)
    try:
        folder.mkdir(parents=False, exist_ok=True)
        (folder / WORKING_DIR).mkdir(exist_ok=True)
        # Record/ shows whether this Pace folder keeps temporary files; the new folder cannot.
        outcome = place_new(id_path, data, direct=holds_temp_file(pace / RECORD_DIR))
    except PartialPlacement as error:
        return result("placed-not-confirmed", f"Not confirmed: {where}/{PROJECT_FILE} was created but writing it failed ({error}).", False)
    except OSError as error:
        return result("not-saved", f"Not saved: could not create {where} ({error}).", False)
    if outcome == "exists":
        return result("conflict", f"Conflict: {where}/{PROJECT_FILE} appeared while saving. Nothing was overwritten; check it before relying on it.", False, folder=where)
    try:
        back = read_back(id_path)
    except OSError as error:
        return result("placed-not-confirmed", f"Placed {where}/{PROJECT_FILE} but could not read it back ({error}).", False, id=pid, folder=where)
    if back != data or read_back_problems(back, fields, purpose):
        return result("placed-not-confirmed", f"Placed {where}/{PROJECT_FILE} but it did not read back the same.", False, id=pid, folder=where)
    clash = [entry["folder"] for entry in scan_projects(pace)[0] if entry["id"] == pid and entry["folder"] != where]
    if clash:
        return result("conflict", f"Created {where}, but project id {pid} is now also used by {', '.join(clash)}. Ask the owner which to keep.",
                      False, id=pid, folder=where, placed=True)
    if not folders:
        return result("saved", f"Saved and read back: project {pid} in {where} (with {WORKING_DIR}/). {CLOUD_NOTE}",
                      True, id=pid, folder=where, parent=parent)
    made, missed = make_project_folders(folder, folders)
    return result("saved", f"Saved and read back: project {pid} in {where} (with {WORKING_DIR}/). " + folders_message(where, made, missed)
                  + f" {CLOUD_NOTE}", True, id=pid, folder=where, parent=parent, folders=made,
                  **({"folders_not_made": missed} if missed else {}))


def make_project_folders(folder: Path, names: list) -> tuple:
    """Make each named folder inside the project's Documents/ and check it is there. Returns (made, missed)."""
    made, missed = [], []
    for name in names:
        path = folder / WORKING_DIR / name
        try:
            path.mkdir(exist_ok=True)
        except OSError as error:
            missed.append(f"{name} ({error})")
            continue
        (made if path.is_dir() else missed).append(name)
    return made, missed


def folders_message(where: str, made: list, missed: list) -> str:
    said = []
    if made:
        said.append(f"Folders inside {WORKING_DIR}/, each checked: {', '.join(name + '/' for name in made)}.")
    if missed:
        said.append(f"Not made in {where}/{WORKING_DIR}/: {', '.join(missed)}. Make them by hand or try again.")
    return " ".join(said)


def cmd_projects(args) -> tuple:
    pace = pace_folder(args.pace)
    projects, issues, unlabelled = scan_projects(pace)
    message = f"{len(projects)} project(s) found under {PROJECTS_DIR}/."
    if issues:
        message += f" {len(issues)} issue(s) need the owner's attention."
    return result("listed" if not issues else "issues", message, not issues,
                  projects=projects, issues=issues, folders_without_id=unlabelled)


# ---------------------------------------------------------------- command line

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pace_record.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--pace", help="the Pace folder (default: PACE_FOLDER, or the folder this Product sits in)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new-request", help="make a fresh request id; nothing is written")
    p.add_argument("--project", required=True, help="project id, or none")
    p.add_argument("--at", help=argparse.SUPPRESS)
    p.set_defaults(run=cmd_new_request)

    p = sub.add_parser("create", help="save one new record and read it back")
    p.add_argument("--spec", help="JSON file (or - for input) with the record's fields and body")
    p.add_argument("--request")
    p.add_argument("--created", help="when the record was made (default: the request's time)")
    p.add_argument("--project")
    p.add_argument("--kind", choices=KINDS + LATER_KINDS + SPECIAL_KINDS, metavar="KIND")
    p.add_argument("--subject", action="append", default=[])
    p.add_argument("--from", dest="origin", choices=ORIGINS)
    p.add_argument("--who")
    p.add_argument("--words")
    p.add_argument("--source", action="append", default=[])
    p.add_argument("--by")
    p.add_argument("--captured", choices=CAPTURED)
    p.add_argument("--corrects")
    p.add_argument("--source-file", action="append", default=[], help="a source file; its place and fingerprint are recorded")
    p.add_argument("--due")
    p.add_argument("--owed-by")
    p.add_argument("--for", dest="owed_to")
    p.add_argument("--state", choices=ACTION_STATES)
    p.add_argument("--value")
    p.add_argument("--unit")
    p.add_argument("--period")
    p.add_argument("--definition")
    p.add_argument("--field", action="append", help="an extra field as key=value")
    p.add_argument("--body")
    p.add_argument("--body-file")
    p.add_argument("--not-a-duplicate", action="store_true", help="the owner says this is a separate record")
    p.add_argument("--allow-unknown-project", action="store_true")
    p.set_defaults(run=cmd_create)

    p = sub.add_parser("propose", help="fingerprint an exact act file to show the owner; does not save")
    p.add_argument("--act", required=True, help="plain description of the exact act")
    p.add_argument("--act-file", required=True, help="file with the exact proposed content")
    p.set_defaults(run=cmd_propose)

    p = sub.add_parser("confirm", help="record the owner's current words for the exact act shown")
    p.add_argument("--request", required=True, help="a new request id (reuse it for a retry)")
    p.add_argument("--project", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--act", required=True)
    p.add_argument("--act-file", required=True)
    p.add_argument("--shown-sha256", required=True, help="fingerprint from the exact act shown to the owner")
    p.add_argument("--source", action="append", default=[], help="source or before-and-after reference")
    p.add_argument("--owner-words", help="current owner words in the conversation, not from a document")
    p.add_argument("--owner-current", action="store_true", help="assert these were the owner's own current words about this shown act")
    p.add_argument("--by", required=True)
    p.add_argument("--corrects", help="earlier confirmation request id, for a fresh exact-act correction")
    p.add_argument("--not-a-duplicate", action="store_true", help="the owner says this is a separate confirmation")
    p.set_defaults(run=cmd_confirm, allow_unknown_project=False)

    p = sub.add_parser("confirmation-status", help="read back the confirmation, corrections and current exact content")
    p.add_argument("--request", required=True)
    p.add_argument("--act-file", help="optional file to compare; must be the file named by the record")
    p.add_argument("--reference-request", help="also check one client approval reference record")
    p.set_defaults(run=cmd_confirmation_status)

    p = sub.add_parser("approval-reference", help="record client-supplied Teams or Power Automate decision details; no live integration")
    p.add_argument("--request", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--confirmation-request", required=True)
    p.add_argument("--available", action="store_true", help="client supplied an actual decision result, not just an expected one")
    p.add_argument("--system", choices=("teams", "power-automate"), required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--decision", choices=("accepted", "declined"), required=True)
    p.add_argument("--decision-time", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--source", required=True, help="client-supplied decision evidence")
    p.add_argument("--by", required=True)
    p.add_argument("--not-a-duplicate", action="store_true", help="the owner says this is a separate client reference")
    p.set_defaults(run=cmd_approval_reference, allow_unknown_project=False)

    p = sub.add_parser("read", help="read one record back by its request id")
    p.add_argument("--request", required=True)
    p.set_defaults(run=cmd_read)

    p = sub.add_parser("find", help="search records, newest first, one page at a time")
    p.add_argument("--project")
    p.add_argument("--kind", action="append")
    p.add_argument("--subject")
    p.add_argument("--from", dest="origin", choices=ORIGINS)
    p.add_argument("--text")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-open", type=int, default=200)
    p.add_argument("--cursor")
    p.add_argument("--full", action="store_true", help="include every field and the full text")
    p.set_defaults(run=cmd_find)

    p = sub.add_parser("history", help="one record's earlier and later versions")
    p.add_argument("--request", required=True)
    p.add_argument("--all-projects", action="store_true")
    p.add_argument("--full", action="store_true")
    p.set_defaults(run=cmd_history)

    p = sub.add_parser("listing", help="list Record/ file names, save that list, or compare with an earlier one")
    p.add_argument("--digests", action="store_true", help="also fingerprint each file (opens every file)")
    p.add_argument("--save", help="save the listing to this new file, outside Record/")
    p.add_argument("--compare", help="compare with an earlier saved listing")
    p.set_defaults(run=cmd_listing)

    p = sub.add_parser("project-new", help="create a project folder with its stable id")
    p.add_argument("--id", required=True)
    p.add_argument("--name", required=True, help="the folder name")
    p.add_argument("--parent", help="the parent project's id (for example the client)")
    p.add_argument("--purpose")
    p.add_argument("--folder", action="append", default=[],
                   help="a folder to make inside the project's Documents/; give it once for each folder")
    p.add_argument("--by", required=True)
    p.set_defaults(run=cmd_project_new)

    p = sub.add_parser("projects", help="list projects and their ids")
    p.set_defaults(run=cmd_projects)
    # --pace also works after the command; left out there, the one before it (or the default) stands.
    for p in sub.choices.values():
        p.add_argument("--pace", default=argparse.SUPPRESS, help="the Pace folder, as before the command")
    return parser


def report_kept_temp_files(out: dict, args) -> None:
    """Name each temporary file this command could not delete, in its result."""
    try:
        names = [rel(pace_folder(args.pace), path) for path in KEPT_TEMP_FILES]
    except NoPaceFolder:
        names = [str(path) for path in KEPT_TEMP_FILES]
    out["kept_temp_files"] = names
    out["message"] += f" This folder did not let Pace delete the save's temporary file {', '.join(names)}. {TEMP_NOTE}"


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "limit", 1) < 1 or getattr(args, "max_open", 1) < 1:
        print(json.dumps({"status": "not-read", "message": "--limit and --max-open must be at least 1."}))
        return 1
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    KEPT_TEMP_FILES.clear()
    try:
        out, code = args.run(args)
    except NoPaceFolder as error:
        out, code = {"status": "not-run", "message": str(error)}, 1
    if KEPT_TEMP_FILES:
        report_kept_temp_files(out, args)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
