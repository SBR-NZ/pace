#!/usr/bin/env python3
"""Pace by SBR - Product updater.

Two commands:

  preview  Fetch one release tag from a git repository, check it still points
           to the pinned full commit, and show what would change in Product.
           Writes nothing to the Pace folder.
  apply    Do the same checks, then replace only the installed Product folder,
           read the installed files back, check that everything outside
           Product is untouched, and record the result in "Release record/".
           A failure or interruption puts the previous Product back.

"Release record/Installed release.md" notes where this folder's releases come
from and which release is installed. get-pace.py writes it, each install adds
an entry at its end, and `preview --latest` without --repo reads it.

Python standard library and the git command only. There are no signatures,
keys or publisher: the pinned commit and the Product file list are what is
checked. Run `python3 pace_update.py preview --help` for the options; the plain
explanation is in Product/Help/updates.md.
"""

from __future__ import annotations

import sys

# Never leave cache files inside an installed Product.
sys.dont_write_bytecode = True

import argparse  # noqa: E402
import difflib  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from urllib.parse import unquote, urlsplit, urlunsplit  # noqa: E402

FILE_LIST_FORMAT = "pace-product-file-list/1"
RECORD_FORMAT = "pace-install-record/1"
GO_AHEAD_FORMAT = "pace-update-go-ahead/1"
ACT_FORMAT = "pace-local-install-act/1"
JOURNAL_FORMAT = "pace-update-journal/1"
NOTE_FORMAT = "pace-release-note/1"

PRODUCT = "Product"
PRODUCT_IN_REPO = "PACE/Product"
LEGACY_PRODUCT_IN_REPO = "starter/Product"  # v3.5.0 only
DEFAULT_REPO = "https://github.com/SBR-NZ/pace.git"  # get-pace.py's default; the updater never assumes it
RELEASE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
RELEASE_RECORD = "Release record"
INSTALLS = "Installs"
GO_AHEADS = "Go-aheads"
PROPOSALS = "Proposals"
RECEIPTS = "Install receipts.md"
NOTE = "Installed release.md"
WORK = "Update in progress"
CHECK_PREFIX = ".pace-update-check-"
CHECK_NOTE = (b"Pace Product updater check: this folder lets files be renamed and deleted. This file is harmless\n"
              b"and Pace does not use it. Anyone with delete rights can delete it.\n")
SHIPPED_ADDINS = "Pace add-ins/"
OWNER_ADDINS = "3 My add-ins"
# Release 3.11.0 numbered the folders people open. The updater never moves an owner's folders, so before it installs a
# release that has the numbered names, the owner renames the old ones, as updates help describes.
RENAMED_FOLDERS = {"Projects": "1 Projects", "Views": "2 Views", "My add-ins": OWNER_ADDINS}
OLDER_OWNER_ADDINS = "Pace/Add-ins/My add-ins"  # where older folders keep them; still listed and protected
HOST_POINTERS = ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md")
PROTECTED = ("Pace.md", "Record/", "1 Projects/", "Repos/", "2 Views/", OWNER_ADDINS + "/", OLDER_OWNER_ADDINS + "/") + HOST_POINTERS
# Small owner files whose bytes are compared, not just their size and time.
HASHED_OWNER_FILES = ("Pace.md",) + HOST_POINTERS

RECEIPTS_HEADER = (
    "# Install receipts\n\n"
    "One line per update attempt, newest last. Lines are only ever added, never changed.\n"
    "Each line names its full record in `Installs/`. \"Installed locally\" means the files\n"
    "were read back on the computer that ran the update; arrival in OneDrive is a separate claim.\n\n"
)

COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
WINDOWS_BAD_CHARS = set('<>:"\\|?*')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)}


class Stop(Exception):
    """The update stopped before anything in the Pace folder changed."""


class NeedsHelp(Exception):
    """An automatic roll-back could not be confirmed; the work area is kept."""


class CannotReplace(Stop):
    """This folder lets files be created but not renamed or deleted, so no update can be made from here."""

    def __init__(self, message: str, kept: list):
        super().__init__(message)
        self.kept = kept  # check files that could not be deleted, relative to the Pace folder


def _checkpoint(stage: str) -> None:
    """No-op marker between install stages. Tests replace it to simulate a crash."""


# ---------------------------------------------------------------- small helpers

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain_time(iso: str) -> str:
    return iso.replace("T", " ").replace("Z", " UTC")


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S.%fZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _pretty(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.") or "release"


def redact(repo: str) -> str:
    """Drop any user name or password from a repository address before it is shown or recorded.

    An ssh user name on its own (such as git@) is kept: it is not a secret, and the address
    does not work without it.
    """
    try:
        parts = urlsplit(repo)
    except ValueError:
        return repo
    if parts.scheme and "@" in parts.netloc:
        user = parts.netloc.rsplit("@", 1)[0]
        if parts.scheme in ("ssh", "git+ssh", "ssh+git") and ":" not in user:
            return repo
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return repo


def _local_folder(repo: str) -> str:
    """A repository given as a local folder, as its full path; any other address unchanged."""
    if "://" not in repo:
        local = Path(repo).expanduser()
        if local.is_dir():
            return str(local.resolve())
    return repo


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(os.path, "isjunction", lambda _p: False)(path))


def _remove_tree(path: Path) -> None:
    """Remove a folder of the updater's own and everything in it: its throwaway copy of a release, the update's work
    area, or a partly made Pace folder. Anything already gone, the folder itself or a file in it, needs nothing more;
    anything that cannot be removed stops it, so a folder still being written to is never called removed."""
    def clear_read_only(func, target, error):
        # Windows will not delete a read-only file: clear that flag and try once more. Other
        # permission bits are kept, so a folder that still cannot be removed stays readable.
        # Something already gone, such as a lock file another program removed, needs nothing more.
        problem = error[1] if isinstance(error, tuple) else error
        if isinstance(problem, FileNotFoundError):
            return
        if func not in (os.unlink, os.remove, os.rmdir) or not isinstance(problem, PermissionError):
            raise problem
        os.chmod(target, stat.S_IMODE(os.lstat(target).st_mode) | stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear_read_only)
    else:  # pragma: no cover - older Python
        shutil.rmtree(path, onerror=clear_read_only)


def _retrying(action, *paths) -> None:
    """Run a rename or delete, retrying briefly when a sync client or scanner holds a file open."""
    for attempt in range(5):
        try:
            action(*paths)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.4)


def _rename(source: Path, target: Path, *, replace: bool = False) -> None:
    """Rename, or replace an existing target, retrying briefly when a sync client or scanner holds a file open."""
    _retrying(os.replace if replace else os.rename, source, target)


def check_can_replace(root: Path) -> None:
    """Stop before anything else is written when this folder lets files be created but not renamed or deleted.

    An update renames Product and deletes its work files, and some linked assistant sessions can only
    create files. The check renames and deletes one small file in Release record/. Where that is
    refused, the file stays (named in the message), and later runs try to delete it rather than make another.
    """
    folder = root / RELEASE_RECORD
    kept = []
    for earlier in sorted(folder.glob(CHECK_PREFIX + "*")) if folder.is_dir() else []:
        try:
            _retrying(os.unlink, earlier)
        except OSError:
            kept.append(earlier)
    if kept:
        raise _cannot_replace(root, kept, None)
    folder.mkdir(exist_ok=True)
    made = folder / f"{CHECK_PREFIX}{uuid.uuid4().hex[:12]}"
    renamed = made.with_name(made.name + "-renamed")
    try:
        with open(made, "xb") as handle:
            handle.write(CHECK_NOTE)
        _rename(made, renamed)
        _retrying(os.unlink, renamed)
    except OSError as error:
        for path in (made, renamed):
            try:
                os.unlink(path)
            except OSError:
                pass
        raise _cannot_replace(root, [path for path in (made, renamed) if path.exists()], error) from None


def _cannot_replace(root: Path, kept: list, error) -> CannotReplace:
    names = [path.relative_to(root).as_posix() for path in kept]
    message = (f"This computer or session can create files in the Pace folder but not rename or delete them"
               f"{f' ({error})' if error else ''}, so it cannot install an update or tidy one up. Install it with "
               "the updater on a computer that can replace files in the Pace folder, as Product updates in the help "
               "explains. If a sync client or virus scanner was holding a file, try again in a moment.")
    if names:
        message += (f" The updater's check file {', '.join(names)} could not be deleted. It is harmless and Pace "
                    "does not use it; anyone with delete rights can delete it, and the next run on a computer that "
                    "can replace files does.")
    return CannotReplace(message, names)


def _write_new(path: Path, data: bytes) -> None:
    """Create a new file (never overwrite), flush it to disk and read it back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != data:
        raise OSError(f"{path.name} did not read back as written")


def _new_file_path(folder: Path, stem: str, suffix: str) -> Path:
    candidate = folder / f"{stem}{suffix}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{number}{suffix}"
        number += 1
    return candidate


# ------------------------------------------------------------- Product file lists

def file_list(entries: dict) -> list:
    """The Product file list: every file's path, size and SHA-256, sorted by path."""
    return [{"path": path, "size": size, "sha256": digest} for path, (size, digest) in sorted(entries.items())]


def file_list_digest(entries: dict) -> str:
    return "sha256:" + _sha256(_canonical(file_list(entries)))


def _summary(entries: dict) -> dict:
    return {
        "format": FILE_LIST_FORMAT,
        "files": len(entries),
        "bytes": sum(size for size, _ in entries.values()),
        "digest": file_list_digest(entries),
    }


def read_tree(folder: Path) -> dict:
    """Read every file under a folder from disk: {relative posix path: (size, sha256)}."""
    found = {}
    for current, dirs, files in os.walk(folder, followlinks=False):
        here = Path(current)
        for name in list(dirs) + files:
            if _is_link(here / name):
                rel = (here / name).relative_to(folder).as_posix()
                raise Stop(f"{folder.name}/{rel} is a link. The updater only handles ordinary files and folders.")
        for name in files:
            path = here / name
            data = path.read_bytes()
            found[path.relative_to(folder).as_posix()] = (len(data), _sha256(data))
    return found


def _check_paths(paths) -> None:
    """Refuse paths that are unsafe or that Windows and OneDrive cannot hold side by side."""
    seen = {}
    for path in paths:
        parts = path.split("/")
        for part in parts:
            if part in ("", ".", "..") or any(ch in WINDOWS_BAD_CHARS or ord(ch) < 32 for ch in part):
                raise Stop(f"The release contains an unusable file name: {path!r}.")
            if part.endswith((".", " ")) or part.split(".")[0].upper() in WINDOWS_RESERVED:
                raise Stop(f"The release contains a file name Windows cannot hold: {path!r}.")
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            folded = prefix.casefold()
            if seen.setdefault(folded, prefix) != prefix:
                raise Stop(f"The release has two names that differ only by capitals: {seen[folded]!r} and {prefix!r}.")


# --------------------------------------------------------------------- git source

# Newer git tidies a repository in the background after a fetch, writing into it after the fetch returns, while the
# updater removes its throwaway store: so no git command it runs starts that tidying.
GIT_SETTINGS = ("-c", "maintenance.auto=false", "-c", "gc.auto=0")


def _git(args, *, data: bytes | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # fail instead of waiting for a password prompt
    try:
        return subprocess.run(["git", *GIT_SETTINGS, *args], input=data, capture_output=True, env=env, check=False)
    except FileNotFoundError:
        raise Stop("git is not installed or not on the PATH. The updater needs git to read the release.") from None


def _git_out(args) -> str:
    result = _git(args)
    return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else ""


def _git_error(result: subprocess.CompletedProcess, repo: str) -> str:
    lines = [line for line in result.stderr.decode("utf-8", "replace").splitlines() if line.strip()]
    text = lines[-1].strip() if lines else f"git exited with code {result.returncode}"
    return text.replace(repo, redact(repo))


def check_tag_name(tag: str) -> None:
    if not tag or tag.startswith("-") or _git(["check-ref-format", f"refs/tags/{tag}"]).returncode != 0:
        raise Stop(f"{tag!r} is not a usable release tag name.")


def check_commit_id(commit: str) -> str:
    value = (commit or "").strip().lower()
    if not COMMIT_RE.match(value):
        raise Stop(
            "The pinned commit must be the full commit id (40 or 64 hexadecimal characters), "
            "not a short id, branch or tag."
        )
    return value


def latest_release(repo: str) -> tuple[str, str]:
    """Find the highest numbered stable release tag and its advertised full commit."""
    if not repo or repo.startswith("-"):
        raise Stop("Give a repository address or folder with --repo.")
    result = _git(["ls-remote", "--tags", "--", repo])
    if result.returncode:
        raise Stop(f"Could not list releases in {redact(repo)}: {_git_error(result, repo)}")
    tags = {}
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        oid, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        peeled = name.endswith("^{}")
        if peeled:
            name = name[:-3]
        match = RELEASE_TAG_RE.fullmatch(name)
        if match and COMMIT_RE.fullmatch(oid.lower()):
            if peeled or name not in tags:
                tags[name] = (tuple(map(int, match.groups())), oid.lower())
    if not tags:
        raise Stop(f"No numbered release tags (such as v3.5.0) were found in {redact(repo)}.")
    tag = max(tags, key=lambda name: tags[name][0])
    return tag, tags[tag][1]


def fetch_release(repo: str, tag: str, commit: str | None, *, folder: str = PRODUCT_IN_REPO,
                  legacy_folder: str = LEGACY_PRODUCT_IN_REPO) -> dict:
    """Fetch one tag into a throwaway store, check it against the pinned commit and read its folder.

    With no pinned commit (preview only), report the commit the tag points to now.
    """
    if not repo or repo.startswith("-"):
        raise Stop("Give the repository address or folder with --repo.")
    check_tag_name(tag)
    pinned = check_commit_id(commit) if commit is not None else None
    shown = redact(repo)
    store_parent = Path(tempfile.mkdtemp(prefix="pace-update-"))
    try:
        store = store_parent / "source.git"
        made = _git(["init", "--bare", "--quiet", str(store)])
        if made.returncode != 0:
            raise Stop("git could not create a temporary store: " + _git_error(made, repo))
        git = ["-C", str(store)]
        source_repo = _local_folder(repo)  # git runs inside the store, so a relative folder needs its full path
        fetched = _git(git + ["fetch", "--quiet", "--no-tags", "--", source_repo, f"+refs/tags/{tag}:refs/tags/{tag}"])
        if fetched.returncode != 0:
            detail = _git_error(fetched, repo)
            if "couldn't find remote ref" in detail:
                raise Stop(
                    f"{shown} has no tag named {tag}. Updates install only from a release tag pinned to "
                    "its commit, never from a branch such as main."
                )
            raise Stop(f"Could not read {shown}: {detail}")
        tag_commit = _git_out(git + ["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"]).lower()
        if not tag_commit:
            raise Stop(f"The tag {tag} in {shown} does not point to a commit.")
        if pinned is not None and tag_commit != pinned:
            exists = _git(git + ["fetch", "--quiet", "--no-tags", "--", source_repo, pinned]).returncode == 0
            if exists:
                raise Stop(
                    f"The tag {tag} has moved: it now points to commit {tag_commit}, not the pinned commit "
                    f"{pinned}. Nothing was installed. Check the release with whoever published it."
                )
            raise Stop(
                f"The pinned commit {pinned} is not in {shown}, and the tag {tag} points to {tag_commit}. "
                "Nothing was installed."
            )
        target = pinned or tag_commit
        if _git_out(git + ["cat-file", "-t", target]) != "commit":
            raise Stop(f"The commit {target} is missing from {shown}.")
        source = folder
        tree = _git_out(git + ["rev-parse", "--verify", "--quiet", f"{target}:{source}"])
        if (not tree or _git_out(git + ["cat-file", "-t", tree]) != "tree") and tag == "v3.5.0":
            source = legacy_folder
            tree = _git_out(git + ["rev-parse", "--verify", "--quiet", f"{target}:{source}"])
        if not tree or _git_out(git + ["cat-file", "-t", tree]) != "tree":
            raise Stop(f"The commit {target} has no {folder} folder, so it is not a Pace release.")
        label = folder.rsplit("/", 1)[-1]
        listing = _git(git + ["ls-tree", "-r", "-z", tree])
        if listing.returncode != 0:
            raise Stop(f"Could not list the release's {label} files: " + _git_error(listing, repo))
        wanted = []
        for raw in listing.stdout.split(b"\0"):
            if not raw:
                continue
            meta, _, raw_path = raw.partition(b"\t")
            mode, kind, oid = meta.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
            if kind == "commit":
                raise Stop(f"{label}/{path} is a submodule. A release {label} must hold ordinary files only.")
            if mode == "120000":
                raise Stop(f"{label}/{path} is a link. A release {label} must hold ordinary files only.")
            if kind != "blob":
                raise Stop(f"{label}/{path} is not an ordinary file.")
            wanted.append((path, oid))
        if not wanted:
            raise Stop(f"The release's {source} folder is empty.")
        _check_paths(path for path, _ in wanted)
        files = _read_blobs(git, wanted, repo)
        pace_md = None
        pace_folders: list = []
        if source == PRODUCT_IN_REPO:
            oid = _git_out(git + ["rev-parse", "--verify", "--quiet", f"{target}:{PACE_MD_TEMPLATE}"])
            if oid and _git_out(git + ["cat-file", "-t", oid]) == "blob":
                pace_md = _read_blobs(git, [(PACE_MD_TEMPLATE, oid)], repo)[PACE_MD_TEMPLATE]
            top = _git(git + ["ls-tree", "-z", target, "PACE/"])
            if top.returncode == 0:
                for raw in top.stdout.split(b"\0"):
                    meta, _, raw_path = raw.partition(b"\t")
                    if b" tree " in meta:
                        pace_folders.append(raw_path.decode("utf-8").rsplit("/", 1)[-1])
    finally:
        _remove_tree(store_parent)
    entries = {path: (len(data), _sha256(data)) for path, data in files.items()}
    return {
        "repository": shown,
        "tag": tag,
        "commit": target,
        "source_folder": source,
        "pinned": pinned is not None,
        "files": files,
        "entries": entries,
        "pace_md": pace_md,
        "pace_folders": sorted(pace_folders),
    }


# A folder named as before 3.11.0 at the start of a path, as in `My add-ins/My voice/ADD-IN.md` or "in Projects/",
# but not a numbered name such as 1 Projects/ or the older Pace/Add-ins/My add-ins/.
OLD_FOLDER_PATH = re.compile(r"(?<![\w/.-])(?<!\d )(?:Projects|Views|My add-ins)/")
LEFT_BEHIND = {".gitkeep", "desktop.ini", ".ds_store", "thumbs.db"}  # files systems leave in an emptied folder
# Files Finder and Windows Explorer add to a folder someone only looked at. They are not edits to Product.
SYSTEM_FILES = {"desktop.ini", ".ds_store", "thumbs.db"}


def _same_folder(one: Path, other: Path) -> bool:
    try:
        return os.path.samefile(one, other)
    except OSError:
        return False


def _without_system_files(entries: dict) -> dict:
    """A Product file list without the files Finder or Windows Explorer leave behind in any folder."""
    return {path: value for path, value in entries.items() if path.rsplit("/", 1)[-1].lower() not in SYSTEM_FILES}


def _has_content(folder: Path) -> bool:
    """True when a folder holds anything but the files systems leave behind; one that cannot be listed counts as full."""
    try:
        with os.scandir(folder) as entries:
            return any(entry.name.lower() not in LEFT_BEHIND for entry in entries)
    except OSError:
        return True


# From 3.14.0 the record tool reads records that archiving moved into Record/'s year and month folders.
ARCHIVE_READER = b"def archive_folder("


def archive_stop(root: Path, release: dict) -> str:
    """Why this release cannot be installed here, or "": one whose tools cannot read archived records would miss them."""
    record = root / "Record"
    try:
        with os.scandir(record) as entries:
            years = [entry.name for entry in entries if entry.is_dir() and re.fullmatch(r"\d{4}", entry.name)]
    except OSError:
        return ""
    if not any(_has_content(record / year) for year in years):
        return ""
    if ARCHIVE_READER in (release.get("files") or {}).get("Tools/pace_record.py", b""):
        return ""
    return (f"This Pace folder has records archived in Record/'s year and month folders, which Pace {release['tag']} "
            "cannot read, so its tools would miss them. Install Pace 3.14.0 or later instead.")


NUMBERS_READER = b"def plain_name("
NUMBERED_FOLDER = re.compile(r"[0-9]{2}\. .+", re.S)
NUMBERED_DOCUMENTS = "01. documents"


def _numbered(base: Path, depth: int = 40) -> bool:
    """True when a project folder in 1 Projects/ is numbered: it starts with its number, such as 02. Budget 2027, or
    holds 01. Documents/. Only project folders are looked into, as Pace numbers no other folder, so a repository
    checkout or a folder of the owner's own is never taken for one. Links are not followed, and a folder reached again,
    as through a junction, is not looked into twice."""
    stack, seen = [(base, 0)], set()
    while stack:
        folder, level = stack.pop()
        try:
            real = os.path.normcase(os.path.realpath(folder))
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        try:
            with os.scandir(folder) as entries:
                names = [entry.name for entry in entries if entry.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        for name in names:
            if level and name.casefold() == NUMBERED_DOCUMENTS:
                return True
            try:
                project = (folder / name / "Pace project.md").is_file()
            except OSError:
                continue
            if project and NUMBERED_FOLDER.fullmatch(name):
                return True
            if project and level + 1 < depth:
                stack.append((folder / name, level + 1))
    return False


def numbers_stop(root: Path, release: dict) -> str:
    """Why this release cannot be installed here, or "": once project folders are numbered, a release whose tools do not
    know folder numbers would show each number in its project's name and take each 01. Documents/ for a folder to sort
    out."""
    if NUMBERS_READER in (release.get("files") or {}).get("Tools/pace_record.py", b""):
        return ""
    if not _numbered(root / "1 Projects"):
        return ""
    return (f"This Pace folder's project folders are numbered, which Pace {release['tag']}'s tools do not know: they "
            "would show each number in its project's name and take each 01. Documents/ for a folder to sort out. Install "
            "Pace 3.16.0 or later instead.")


def folder_renames(root: Path, release: dict) -> list:
    """The owner's folders to sort out before this release is installed, each as {"from", "to", "do"}.

    A release with the numbered folder names (3.11.0 or later) needs any folder still named as before renamed, or
    its contents moved when both names exist. An earlier release needs the numbered folders named back, because its
    tools look for the older names. An empty folder left under the other name is harmless and not listed."""
    shipped = set(release.get("pace_folders") or ())
    steps = []
    for old, new in RENAMED_FOLDERS.items():
        if new in shipped:
            have, want = old, new
        elif old in shipped:
            have, want = new, old
        else:
            continue
        source, target = root / have, root / want
        if not source.is_dir() or (target.is_dir() and _same_folder(source, target)):
            continue  # nothing there, or a link under one name that leads to the folder under the other
        if not target.exists() and not target.is_symlink():
            step = f"rename {have}/ to {want}/"
        elif not target.is_dir():
            step = f"{want} is a file, not a folder: move it aside, then rename {have}/ to {want}/"
        elif _has_content(source):
            step = f"move what is in {have}/ into {want}/, then remove the empty {have}/"
        else:
            continue
        steps.append({"from": have, "to": want, "do": step})
    return steps


def old_folder_lines(root: Path, plan: dict) -> list:
    """Lines Pace.md would still have after this install that name a folder as it was named before 3.11.0, such as
    an add-in index line for a customised copy. Only a release with the numbered names makes them out of date."""
    if not set(RENAMED_FOLDERS.values()) & set(plan["release"].get("pace_folders") or ()):
        return []
    data = plan["pace_md"].get("after")
    try:
        if data is None:
            data = (root / "Pace.md").read_bytes()
        text = data.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    return [line.strip() for line in text.splitlines() if OLD_FOLDER_PATH.search(line)]


def old_lines_message(lines: list) -> str:
    said = "; ".join(f'"{line}"' for line in lines)
    return f"Pace.md still names folders as they were named before 3.11.0 in these lines, so change each to the numbered name, such as 3 My add-ins/ for My add-ins/: {said}."


def renames_message(steps: list, lines: list) -> str:
    """What to do, in full, before a release can be installed over folders with the other names. The steps are given
    here because the installed help may be older than the release that needs them."""
    said = "; ".join(step["do"] for step in steps)
    if steps[0]["to"] in RENAMED_FOLDERS.values():
        start = ("This release numbers the folders people open, and an update never moves your folders. Before it is "
                 "installed, close any file open from them, let OneDrive or your sync finish, then in the Pace folder: ")
        end = (" Nothing else changes: projects keep their ids, and records saved before keep working. Paths inside "
               "the renamed folders get 2 characters longer. The release's help, under Folder names from 3.11.0, "
               "says more.")
    else:
        start = ("This release is from before 3.11.0, and its tools look for the folder names from then. An update "
                 "never moves your folders, so before it is installed, close any file open from them, let OneDrive or "
                 "your sync finish, then in the Pace folder: ")
        end = ""
    then = f" Then: {old_lines_message(lines)}" if lines else ""
    return start + said + "." + then + " Then preview again." + end


def _read_blobs(git: list, wanted: list, repo: str) -> dict:
    """Read each file's bytes and check them against the commit's own object ids."""
    batch = _git(git + ["cat-file", "--batch"], data=b"".join(oid.encode() + b"\n" for _, oid in wanted))
    if batch.returncode != 0:
        raise Stop("Could not read the release files: " + _git_error(batch, repo))
    out, position, files = batch.stdout, 0, {}
    for path, oid in wanted:
        end = out.index(b"\n", position)
        header = out[position:end].decode("ascii").split(" ")
        if len(header) != 3 or header[0] != oid or header[1] != "blob":
            raise Stop(f"The release file Product/{path} could not be read from the commit.")
        size = int(header[2])
        data = out[end + 1:end + 1 + size]
        position = end + 1 + size + 1
        algorithm = hashlib.sha1 if len(oid) == 40 else hashlib.sha256
        if len(data) != size or algorithm(b"blob %d\0" % size + data).hexdigest() != oid:
            raise Stop(f"The release file Product/{path} does not match the commit's file list.")
        files[path] = data
    return files


# ------------------------------------------------------------ the Pace folder

def _root(root) -> Path:
    folder = Path(root).expanduser().resolve()
    if not folder.is_dir():
        raise Stop(f"{folder} is not a folder.")
    if _work_area(folder).is_dir() and not _is_link(folder / RELEASE_RECORD):
        return folder  # an interrupted update: Product may be missing until it is recovered
    product = folder / PRODUCT
    if _is_link(product) or not product.is_dir():
        raise Stop(f"{folder} has no ordinary Product folder, so it is not an installed Pace folder.")
    record = folder / RELEASE_RECORD
    if record.exists() and (_is_link(record) or not record.is_dir()):
        raise Stop(f"{RELEASE_RECORD}/ in {folder} is not an ordinary folder.")
    return folder


UNREADABLE = ("unreadable",)


def snapshot_outside_product(root: Path) -> dict:
    """Everything outside Product/ and Release record/, by name, size and modification time.

    File contents are not opened (so OneDrive does not download cloud-only files),
    except the small owner files in HASHED_OWNER_FILES, whose bytes are compared too.
    Something the updater is not allowed to read, such as a host app's own folder seen
    from a sandbox, is listed as unreadable and not walked into, instead of stopping the
    update. It cannot be checked, and the updater never writes there.
    """
    view = {}

    def cannot_list(error: OSError) -> None:
        top = Path(os.path.abspath(root))
        where = Path(os.path.abspath(error.filename)) if error.filename else top
        if where == top:
            raise error
        view[where.relative_to(top).as_posix()] = UNREADABLE

    for current, dirs, files in os.walk(root, followlinks=False, onerror=cannot_list):
        here = Path(current)
        if here == root:
            dirs[:] = [d for d in dirs if d not in (PRODUCT, RELEASE_RECORD)]
            files = [f for f in files if f not in (PRODUCT, RELEASE_RECORD)]
        for name in list(dirs):
            path = here / name
            rel = path.relative_to(root).as_posix()
            try:
                if _is_link(path):
                    view[rel] = ("link", os.readlink(path) if path.is_symlink() else "junction")
                    dirs.remove(name)
                else:
                    view[rel] = ("folder",)
            except PermissionError:
                view[rel] = UNREADABLE
                dirs.remove(name)
        for name in files:
            path = here / name
            rel = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    view[rel] = ("link", os.readlink(path))
                    continue
                info = path.stat()
                entry = ("file", info.st_size, info.st_mtime_ns)
                if rel in HASHED_OWNER_FILES:
                    entry += (_sha256(path.read_bytes()),)
            except PermissionError:
                entry = UNREADABLE
            view[rel] = entry
    return view


def not_checked(view: dict) -> list:
    """The paths a snapshot outside Product could not read, so could not check."""
    return sorted(path for path, entry in view.items() if entry == UNREADABLE)


def _differences(before: dict, after: dict) -> list:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def _install_records(root: Path) -> list:
    """Readable install records, oldest first, leaving out any a later record corrects."""
    folder = root / RELEASE_RECORD / INSTALLS
    records = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("format") == RECORD_FORMAT:
            records.append((path.name, data))
    corrected = {data.get("corrects") for _, data in records}
    return [(name, data) for name, data in records if name not in corrected]


def last_install(root: Path) -> dict | None:
    for name, data in reversed(_install_records(root)):
        if data.get("result") == "installed":
            return {"record": f"{INSTALLS}/{name}", **data}
    return None


def _entries_from_record(record: dict) -> dict:
    listed = record.get("product_file_list", {}).get("entries", [])
    return {item["path"]: (item["size"], item["sha256"]) for item in listed}


def _compare(old: dict, new: dict) -> dict:
    return {
        "added": sorted(set(new) - set(old)),
        "changed": sorted(p for p in set(new) & set(old) if new[p] != old[p]),
        "removed": sorted(set(old) - set(new)),
        "unchanged": sum(1 for p in set(new) & set(old) if new[p] == old[p]),
    }


def _shipped_addins(old: dict, new: dict) -> dict:
    def names(entries):
        return {p[len(SHIPPED_ADDINS):].split("/")[0] for p in entries if p.startswith(SHIPPED_ADDINS) and p.count("/") >= 2}

    def files_of(entries, name):
        prefix = f"{SHIPPED_ADDINS}{name}/"
        return {p: v for p, v in entries.items() if p.startswith(prefix)}

    before, after = names(old), names(new)
    both = before & after
    return {
        "added": sorted(after - before),
        "removed": sorted(before - after),
        "changed": sorted(n for n in both if files_of(old, n) != files_of(new, n)),
        "unchanged": sorted(n for n in both if files_of(old, n) == files_of(new, n)),
    }


def _owner_addins(root: Path) -> list:
    """The owner's add-ins by folder name; one still in the older place is named by its full path.

    Both places are only read; the updater never moves anything between them.
    """
    found = []
    for place, prefix in ((OWNER_ADDINS, ""), (OLDER_OWNER_ADDINS, OLDER_OWNER_ADDINS + "/")):
        folder = root / place
        if folder.is_dir():
            # An add-in is a folder; a file beside them, such as the owner's Assistant setup.md, is not one.
            found += sorted(prefix + p.name for p in folder.iterdir() if p.is_dir())
    return found


def _pace_md_links_removed(root: Path, old: dict, new: dict) -> list:
    """Product paths that Pace.md mentions, which exist now but this release removes.

    Pace.md is only read here; its own parts are planned separately (see plan_pace_md).
    """
    pace = root / "Pace.md"
    if not pace.is_file():
        return []
    text = pace.read_text(encoding="utf-8", errors="replace")
    found = re.findall(r"`(Product/[^`]+)`|\]\(<(Product/[^>]+)>\)|\]\((Product/[^)\s]+)\)", text)
    gone = set()
    for groups in found:
        path = unquote(next(g for g in groups if g)).split("#")[0].rstrip("/")[len(PRODUCT) + 1:]
        exists_now = path in old or any(p.startswith(path + "/") for p in old)
        exists_after = path in new or any(p.startswith(path + "/") for p in new)
        if path and exists_now and not exists_after:
            gone.add(f"{PRODUCT}/{path}")
    return sorted(gone)


# ----------------------------------------------------------------- Pace.md parts
#
# Pace.md is mostly Pace's own text, in parts that each start at a "## " heading (the opening lines before
# the first heading are a part too). A part can end with a "Your lines" mark: everything after the mark, up
# to the next heading, is the owner's and is never changed. The last line of Pace.md records each part's
# fingerprint as Pace shipped it, so an update can tell which parts the owner has changed: it replaces only
# a part that still matches, adds a part a release introduces, and leaves everything else as it is.

PACE_MD_TEMPLATE = "PACE/Pace.md"
YOUR_LINES = "<!-- Your lines go below this one. Pace updates never change them. -->"
SHIPPED_PREFIX = "<!-- Pace parts as shipped, so an update can tell which ones you have changed: "
SHIPPED_RE = re.compile(r"^" + re.escape(SHIPPED_PREFIX)
                        + r"((?:[a-z0-9-]+=[0-9a-f]{12})(?: [a-z0-9-]+=[0-9a-f]{12})*) -->$")
PACE_MD_REPORT = (("updated", "updated"), ("added", "added"), ("removed", "removed, as Pace no longer ships it"),
                  ("kept_changed", "kept as you changed it"), ("kept_not_shipped", "kept as yours, as Pace no longer ships it"),
                  ("not_added", "not added back, as you removed it"))


def _part_id(heading: str) -> str:
    """A part's id from its heading: lower-case letters and digits joined by single hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or "part"


def _part_fingerprint(lines: list) -> str:
    text = "\n".join(line.rstrip() for line in lines).strip("\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def pace_md_parts(text: str) -> tuple:
    """Split Pace.md text (with \\n newlines) into its parts, and read the line recording them as shipped.

    Returns (parts, shipped). Each part has an id, a title, Pace's lines, the owner's lines after a
    "Your lines" mark (None when the part has no mark) and the fingerprint of Pace's lines. shipped maps
    part ids to fingerprints, or is None when the line is missing or appears more than once.
    """
    shipped, found, kept = None, 0, []
    for line in text.split("\n"):
        match = SHIPPED_RE.match(line.strip())
        if match:
            found += 1
            shipped = dict(pair.split("=", 1) for pair in match.group(1).split(" "))
            continue
        kept.append(line)
    if found != 1:
        shipped = None
    blocks, current = [], ("intro", "the opening lines", [])
    for line in kept:
        if line.startswith("## "):
            blocks.append(current)
            current = (_part_id(line[3:]), line[3:].strip(), [line])
        else:
            current[2].append(line)
    blocks.append(current)
    parts = []
    for part_id, title, lines in blocks:
        marks = [index for index, line in enumerate(lines) if line.strip() == YOUR_LINES]
        pace, yours = (lines[:marks[0]], lines[marks[0] + 1:]) if marks else (lines, None)
        parts.append({"id": part_id, "title": title, "pace": pace, "yours": yours,
                      "fingerprint": _part_fingerprint(pace)})
    return parts, shipped


def assemble_pace_md(parts: list, shipped: dict) -> str:
    """Pace.md text from its parts, ending with the line that records Pace's parts as shipped."""
    lines = []
    for part in parts:
        lines += part["pace"]
        if part["yours"] is not None:
            lines += [YOUR_LINES] + part["yours"]
    body = "\n".join(lines).rstrip("\n")
    return body + "\n" + SHIPPED_PREFIX + " ".join(f"{key}={value}" for key, value in shipped.items()) + " -->\n"


def _has_own_lines(part: dict) -> bool:
    return any(line.strip() for line in part["yours"] or [])


def _pace_md_summary(parts: dict) -> str:
    said = [f"{label} {_list(parts[key])}" for key, label in PACE_MD_REPORT if parts.get(key)]
    return "; ".join(said) or "only its last line, the record of Pace's parts as shipped, brought up to date"


def plan_pace_md(current, template) -> dict:
    """What an update would do to Pace.md: change only Pace's own parts, and only those the owner left as shipped.

    current is the owner's Pace.md bytes (None when there is none) and template the release's Pace.md bytes
    (None when the release has none). The result's status is "update" (with the new bytes in "after"),
    "current", or a reason the file is left as it is. It never changes the owner's lines.
    """
    def leave(status: str, message: str) -> dict:
        return {"status": status, "message": message}

    if current is None:
        return leave("no Pace.md", "There is no Pace.md here, so there is nothing to keep current.")
    if template is None:
        return leave("release not marked", "This release has no marked Pace.md, so yours is left as it is.")
    try:
        new_text = template.decode("utf-8").replace("\r\n", "\n")
        bom = current.startswith(b"\xef\xbb\xbf")
        old_text = (current[3:] if bom else current).decode("utf-8")
    except UnicodeDecodeError:
        return leave("unreadable", "Pace.md or the release's Pace.md is not plain UTF-8 text, so Pace.md is left as it is.")
    crlf = "\r\n" in old_text
    old_text = old_text.replace("\r\n", "\n")
    new_parts, new_shipped = pace_md_parts(new_text)
    new_ids = [part["id"] for part in new_parts]
    if new_shipped != {part["id"]: part["fingerprint"] for part in new_parts} or len(set(new_ids)) != len(new_ids):
        return leave("release not marked", "This release's Pace.md does not record its parts as shipped, so yours is left as it is.")
    old_parts, old_shipped = pace_md_parts(old_text)
    if old_shipped is None:
        return leave("not marked", (
            "Pace.md does not record Pace's parts as shipped, so the update leaves it as it is. To let updates keep "
            "it current, start from the release's Pace.md and put your own lines back below each 'Your lines' mark, "
            "as Product updates help explains."))
    old_ids = [part["id"] for part in old_parts]
    if len(set(old_ids)) != len(old_ids):
        return leave("unclear", "Two parts of Pace.md have the same heading, so the update leaves it as it is.")

    by_id = {part["id"]: part for part in old_parts}
    followers, anchor = {}, None  # parts only the owner's file has, kept after the part they follow there
    for part in old_parts:
        if part["id"] in new_ids:
            anchor = part["id"]
        else:
            followers.setdefault(anchor, []).append(part)
    out, shipped = [], {}
    report = {key: [] for key, _ in PACE_MD_REPORT}

    def keep_followers(key):
        for part in followers.get(key, []):
            if part["id"] in old_shipped and part["fingerprint"] == old_shipped[part["id"]] and not _has_own_lines(part):
                report["removed"].append(part["title"])
                continue
            if part["id"] in old_shipped:
                report["kept_not_shipped"].append(part["title"])
            out.append(part)

    keep_followers(None)
    for new in new_parts:
        old = by_id.get(new["id"])
        if old is None:
            if new["id"] in old_shipped:
                shipped[new["id"]] = old_shipped[new["id"]]  # remembered, so a later update does not add it back
                report["not_added"].append(new["title"])
            else:
                out.append(new)
                shipped[new["id"]] = new["fingerprint"]
                report["added"].append(new["title"])
            continue
        recorded = old_shipped.get(new["id"])
        if recorded is not None and old["fingerprint"] == recorded:
            out.append({**new, "yours": old["yours"] if old["yours"] is not None else new["yours"]})
            shipped[new["id"]] = new["fingerprint"]
            if new["fingerprint"] != recorded:
                report["updated"].append(new["title"])
        elif old["fingerprint"] == new["fingerprint"]:
            out.append(old)  # the owner already has this release's wording
            shipped[new["id"]] = new["fingerprint"]
        else:
            out.append(old)
            if recorded is not None:
                shipped[new["id"]] = recorded
            report["kept_changed"].append(new["title"])
        keep_followers(new["id"])

    parts = {key: names for key, names in report.items() if names}
    changed = bool(report["updated"] or report["added"] or report["removed"]) or shipped != old_shipped
    if not changed:
        note = f" Parts you changed are kept as they are: {_list(report['kept_changed'])}." if report["kept_changed"] else ""
        return {"status": "current", "before_sha256": _sha256(current), "after_sha256": _sha256(current),
                "parts": parts, "message": "Pace's parts of Pace.md are already current." + note}
    after_text = assemble_pace_md(out, shipped)
    after = (b"\xef\xbb\xbf" if bom else b"") + after_text.replace("\n", "\r\n" if crlf else "\n").encode("utf-8")
    diff = "\n".join(difflib.unified_diff(old_text.split("\n"), after_text.split("\n"),
                                          "Pace.md now", "Pace.md after the update", lineterm=""))
    return {"status": "update", "before_sha256": _sha256(current), "after_sha256": _sha256(after),
            "parts": parts, "diff": diff, "after": after,
            "message": f"Pace.md: {_pace_md_summary(parts)}. Your own lines stay as they are."}


def _pace_md_public(planned: dict) -> dict:
    return {key: value for key, value in planned.items() if key != "after"}


def _put_back(path: Path, data: bytes) -> bool:
    """Write a file's earlier bytes back in place; True when it then reads back as them."""
    temp = path.with_name(f".pace-md-{uuid.uuid4().hex[:12]}.tmp")
    try:
        _write_new(temp, data)
        _rename(temp, path, replace=True)
        return path.read_bytes() == data
    except OSError:
        try:
            os.unlink(temp)
        except OSError:
            pass
        return False


def update_pace_md(root: Path, planned: dict) -> dict:
    """Write the planned Pace.md in place and read it back; put the earlier text back if that fails."""
    public = _pace_md_public(planned)
    if planned.get("status") != "update":
        return public
    path = root / "Pace.md"
    try:
        current = path.read_bytes()
    except OSError as error:
        return {**public, "status": "not updated", "message": f"Pace.md could not be read again ({error}), so it was left as it is."}
    if _sha256(current) != planned["before_sha256"]:
        return {**public, "status": "not updated", "message": (
            "Pace.md changed after the update was planned, so it was left as it is. Preview again to see what would change.")}
    temp = path.with_name(f".pace-md-{uuid.uuid4().hex[:12]}.tmp")
    try:
        _write_new(temp, planned["after"])
        _rename(temp, path, replace=True)
        if path.read_bytes() != planned["after"]:
            raise OSError("it did not read back as planned")
    except OSError as error:
        try:
            os.unlink(temp)
        except OSError:
            pass
        back = _put_back(path, current) if path.exists() and path.read_bytes() != current else True
        return {**public, "status": "not updated", "message": (
            f"Pace.md was not updated: {error}. " + ("It is as it was before." if back else
                                                    "Check it: it may not be as it was before."))}
    summary = _pace_md_summary(planned["parts"])
    warning = None
    try:
        _append_receipt(root, f"- {_plain_time(_iso(_now()))} - Pace.md: {summary}. Your own lines were left as they "
                              "were, and the file was read back.")
    except OSError as error:
        warning = f"Pace.md was updated, but the install receipts could not be added to ({error})."
    result = {**public, "status": "updated", "message": f"Pace.md: {summary}, and read back. Your own lines stay as they are."}
    if warning:
        result["warning"] = warning
    return result


# ------------------------------------------------------------- the release note

NOTE_HEADER = (
    "# Installed release\n\n"
    "Where this PACE folder gets its Pace releases, and which release is installed. To check for an\n"
    "update, the Product updater reads the release repository from the last entry below. Entries are\n"
    "only ever added at the end and earlier ones are never changed, so the last entry is the release\n"
    "installed now. Product updates never replace this file.\n\n"
    f"Format: {NOTE_FORMAT}\n"
)
NOTE_FIELDS = (
    ("repository", "Release repository"),
    ("tag", "Installed release"),
    ("commit", "Full commit"),
    ("digest", "Product file list"),
    ("upstream_repository", "Upstream repository"),
    ("upstream_tag", "Upstream release"),
    ("upstream_commit", "Upstream full commit"),
    ("record", "Install record"),
)
NOTE_HEADING_RE = re.compile(r"^## (\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) UTC - (\S.*)$")
NOTE_LINE_RE = re.compile(r"^- ([^:]+): (.*)$")
NOTE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _note_where() -> str:
    return f"{RELEASE_RECORD}/{NOTE}"


def note_repository(repo: str) -> str:
    """The address to write in the note: no password or token, and a local folder as a full path."""
    return _local_folder(redact(repo))


def _note_entry(event: str, moment: str, fields: dict) -> str:
    lines = [f"## {_plain_time(moment)} - {event}", ""]
    for key, label in NOTE_FIELDS:
        value = str(fields.get(key) or "").strip()
        if any(ord(ch) < 32 for ch in value):
            raise Stop(f"The {label.lower()} cannot be written in the release note because it has a line break or control character.")
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines) + "\n"


def _parse_note_entry(block: str):
    """One entry as a dict, or a plain reason it cannot be used."""
    lines = block.splitlines()
    heading = NOTE_HEADING_RE.match(lines[0].strip()) if lines else None
    if not heading:
        return "its heading does not start with a date and time"
    entry = {"time": f"{heading[1]}T{heading[2]}Z", "event": heading[3].strip()}
    labels = {label: key for key, label in NOTE_FIELDS}
    for line in lines[1:]:
        found = NOTE_LINE_RE.match(line.strip())
        if found and found[1] in labels:
            entry[labels[found[1]]] = found[2].strip()
    repository = entry.get("repository", "")
    if not repository or repository.startswith("-"):
        return "it does not name the release repository"
    if redact(repository) != repository:
        return "its release repository includes sign-in details (a user name, password or token), which the note must never hold"
    if not NOTE_TAG_RE.match(entry.get("tag", "")):
        return "it does not name the installed release tag"
    for key in ("commit", "upstream_commit"):
        if key in entry:
            entry[key] = entry[key].lower()
            if not COMMIT_RE.match(entry[key]):
                return "it does not give a full commit (40 or 64 characters)"
    if "commit" not in entry:
        return "it does not give the full commit"
    if "digest" in entry and not DIGEST_RE.match(entry["digest"]):
        return "its Product file list is not a sha256 fingerprint"
    return entry


def read_release_note(root: Path) -> dict:
    """The note's state ("missing", "unreadable" or "readable") and, when readable, its last entry."""
    path = root / RELEASE_RECORD / NOTE
    where = _note_where()
    if _is_link(path) or (path.exists() and not path.is_file()):
        return {"state": "unreadable", "is_note": False, "message": f"{where} is not an ordinary file."}
    if not path.exists():
        return {"state": "missing", "is_note": False, "message": f"This folder has no {where}."}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return {"state": "unreadable", "is_note": False, "message": f"{where} could not be read ({error})."}
    if not re.search(r"(?m)^Format: " + re.escape(NOTE_FORMAT) + r"[ \t]*$", text):
        return {"state": "unreadable", "is_note": False,
                "message": f"{where} does not say it is a Pace release note (Format: {NOTE_FORMAT})."}
    blocks = re.split(r"(?m)^(?=## )", text)[1:]
    if not blocks:
        return {"state": "unreadable", "is_note": True, "message": f"{where} has no entries yet."}
    last = _parse_note_entry(blocks[-1])
    if isinstance(last, str):
        return {"state": "unreadable", "is_note": True,
                "message": f"The last entry in {where} cannot be used: {last}."}
    return {"state": "readable", "is_note": True, "entry": last, "entries": len(blocks)}


def add_release_note_entry(root: Path, event: str, moment: str, fields: dict) -> None:
    """Add one entry at the end of the release note, creating it if needed. Earlier text is never changed."""
    path = root / RELEASE_RECORD / NOTE
    entry = _note_entry(event, moment, fields)
    if not path.exists() and not _is_link(path):
        _write_new(path, (NOTE_HEADER + "\n" + entry).encode("utf-8"))
        return
    if not read_release_note(root)["is_note"]:
        raise Stop(f"{_note_where()} is not a Pace release note this updater can add to, so it was left as it is.")
    before = path.read_bytes()
    gap = "" if before.endswith(b"\n\n") else "\n" if before.endswith(b"\n") else "\n\n"
    addition = (gap + entry).encode("utf-8")
    with open(path, "ab") as handle:
        handle.write(addition)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != before + addition:
        raise OSError(f"{_note_where()} did not read back as written")


def note_first_copy(root: Path, repo: str, tag: str, commit: str) -> None:
    """Start the release note of a newly copied PACE folder (used by get-pace.py)."""
    add_release_note_entry(root, "Copied with get-pace.py", _iso(_now()), {
        "repository": note_repository(repo),
        "tag": tag,
        "commit": commit,
        "digest": file_list_digest(read_tree(root / PRODUCT)),
    })


def release_source(root: Path) -> dict:
    """The note's last entry, for `preview --latest` without --repo. Never guesses a repository."""
    note = read_release_note(root)
    ask = ("The updater will not guess where releases come from. Ask the owner, or whoever set up Pace, for "
           "the release repository address, then run preview again with --repo <address>.")
    if note["state"] == "missing":
        raise Stop(f"This PACE folder has no release note ({_note_where()}). {ask} The next install writes the note.")
    if note["state"] != "readable":
        raise Stop(f"{note['message']} {ask}")
    return note["entry"]


def installed_release(root: Path) -> dict | None:
    """The release installed now: the note's last entry, or the last install record if that is newer.

    An install record that matches the note's last entry is used for its full file list.
    """
    record = last_install(root)
    note = read_release_note(root)
    if note["state"] != "readable":
        return record
    entry = note["entry"]
    if record and (record.get("time", "") > entry["time"] or (
            record.get("commit") == entry["commit"]
            and record.get("product_file_list", {}).get("digest") == entry.get("digest"))):
        return record
    return {"record": NOTE, "tag": entry["tag"], "commit": entry["commit"], "repository": entry["repository"],
            "product_file_list": {"digest": entry.get("digest")}}


def _note_install(root: Path, journal: dict) -> str | None:
    """Add a finished install to the release note once. Returns a warning if that was not possible."""
    record = f"{INSTALLS}/{journal['record_file']}"
    upstream = journal.get("upstream") or {}
    try:
        note = read_release_note(root)
        if note["state"] == "readable" and note["entry"].get("record") == record:
            return None
        event = ("Installed in this central copy with the Product updater" if journal["kind"] == "central copy"
                 else "Installed with the Product updater")
        add_release_note_entry(root, event, journal.get("recorded") or _iso(_now()), {
            "repository": journal.get("source") or journal["repository"],
            "tag": journal["tag"],
            "commit": journal["commit"],
            "digest": journal["new_digest"],
            "upstream_repository": upstream.get("repository"),
            "upstream_tag": upstream.get("tag"),
            "upstream_commit": upstream.get("commit"),
            "record": record,
        })
    except (OSError, Stop) as error:
        return (f"The install is complete and recorded in {RELEASE_RECORD}/{record}, but {_note_where()} could "
                f"not be updated ({error}). Until the next install, give --repo when you preview.")
    return None


def _release_number(tag):
    found = RELEASE_TAG_RE.fullmatch(tag or "")
    return tuple(map(int, found.groups())) if found else None


def compare_with_installed(installed: dict, tag: str, commit: str) -> str:
    """How a release compares with the installed one: same, newer, older, moved, unknown or not comparable."""
    if not installed.get("tag"):
        return "unknown"
    if installed.get("commit") == commit:
        return "same"
    if installed["tag"] == tag:
        return "moved"
    now, new = _release_number(installed["tag"]), _release_number(tag)
    if now is None or new is None:
        return "not comparable"
    return "newer" if new > now else "older"


# ------------------------------------------------------------------- planning

def _plan(root: Path, repo: str, tag: str, commit: str | None, upstream: dict | None,
          expect_digest: str | None) -> dict:
    release = fetch_release(repo, tag, commit)
    new = release["entries"]
    new_summary = _summary(new)
    if expect_digest and expect_digest.strip() != new_summary["digest"]:
        raise Stop(
            f"The release's Product file list ({new_summary['digest']}) does not match the expected "
            f"file list {expect_digest.strip()}. Nothing was installed."
        )
    mapping = None
    if upstream:
        source = fetch_release(upstream["repo"], upstream["tag"], upstream["commit"])
        same = source["entries"] == new
        if not same:
            differ = _compare(source["entries"], new)
            count = len(differ["added"]) + len(differ["changed"]) + len(differ["removed"])
            raise Stop(
                f"This commit's Product differs from upstream {source['tag']} (commit {source['commit']}) in "
                f"{count} file(s), so it cannot be recorded as that upstream release. Nothing was installed."
            )
        mapping = {
            "repository": source["repository"],
            "tag": source["tag"],
            "commit": source["commit"],
            "product_file_list_digest": _summary(source["entries"])["digest"],
            "same_product_file_list": True,
        }
    old = read_tree(root / PRODUCT)
    prior = installed_release(root)
    changed_since = product_changes(prior, old)
    already = bool(prior and prior.get("commit") == release["commit"] and _without_system_files(old) == new)
    return {
        "release": release,
        "new": new,
        "old": old,
        "new_summary": new_summary,
        "old_summary": _summary(old),
        "upstream": mapping,
        "prior": prior,
        "changed_since_record": changed_since,
        "already_installed": already,
        "changes": _compare(old, new),
        "shipped_addins": _shipped_addins(old, new),
        "owner_addins": _owner_addins(root),
        "pace_md_links_removed": _pace_md_links_removed(root, old, new),
        "pace_md": plan_pace_md((root / "Pace.md").read_bytes() if (root / "Pace.md").is_file() else None,
                                release.get("pace_md")),
    }


def product_changes(prior: dict | None, old: dict) -> dict | None:
    """How the Product on disk (old) differs from the release recorded as installed (prior), or None when it does not.

    Only reads: the updater uses it before an install, and the health check to say whether Product was edited."""
    if not prior:
        return None
    # A file Finder or Explorer added, such as .DS_Store, is not an edit, so it never stops an update.
    old = _without_system_files(old)
    recorded = _entries_from_record(prior)
    if recorded:
        recorded = _without_system_files(recorded)
    noted = prior.get("product_file_list", {}).get("digest")
    if recorded and recorded != old:
        return _compare(recorded, old)
    if not recorded and noted and noted != file_list_digest(old):
        # The release note keeps a fingerprint, not a file list, so the files cannot be named.
        return {"added": [], "changed": [], "removed": [], "not_listed": True}
    if not recorded and not noted:
        # Nothing was kept to compare with (a hand-written release note), so edits cannot be ruled out.
        return {"added": [], "changed": [], "removed": [], "not_checked": True}
    return None


def _kept_by(prior: dict) -> str:
    """Where the installed release is recorded, as a path inside the Pace folder."""
    return _note_where() if prior.get("record") == NOTE else f"{RELEASE_RECORD}/{prior.get('record')}"


def _prior_view(plan: dict) -> dict:
    prior = plan["prior"]
    changed = plan["changed_since_record"]
    return {
        "tag": prior.get("tag") if prior else None,
        "commit": prior.get("commit") if prior else None,
        "record": prior.get("record") if prior else None,
        "product_file_list_digest": plan["old_summary"]["digest"],
        # None when there is no earlier install, or nothing was kept to check it against.
        "matches_record": (changed is None) if prior and not (changed or {}).get("not_checked") else None,
    }


def _public(plan: dict) -> dict:
    release = plan["release"]
    return {
        "repository": release["repository"],
        "tag": release["tag"],
        "commit": release["commit"],
        "commit_pinned": release["pinned"],
        "product_file_list": plan["new_summary"],
        "upstream": plan["upstream"],
        "installed_now": _prior_view(plan),
        "changed_since_record": plan["changed_since_record"],
        "changes": plan["changes"],
        "shipped_addins": plan["shipped_addins"],
        "owner_addins_never_updated": plan["owner_addins"],
        "pace_md_links_removed": plan["pace_md_links_removed"],
        "pace_md": _pace_md_public(plan["pace_md"]),
        "protected": list(PROTECTED),
    }


def _work_area(root: Path) -> Path:
    return root / RELEASE_RECORD / WORK


def preview(root, repo: str, tag: str, commit: str | None = None, *, upstream: dict | None = None,
            expect_digest: str | None = None, central: bool = False) -> dict:
    """Check a release and show what would change. Writes nothing to the Pace folder."""
    folder = _root(root)
    leftover = _leftover(folder)[0] if _work_area(folder).exists() else None
    if leftover not in (None, "staging"):
        return {"command": "preview", "status": "interrupted", "installed": False, "changed": False,
                "message": _leftover_message(leftover, "preview the release")}
    plan = _plan(folder, repo, tag, commit, upstream, expect_digest)
    release = plan["release"]
    result = {"command": "preview", "status": "ready", "installed": False, "changed": False, **_public(plan)}
    if leftover:
        result["warning"] = STAGING_LEFTOVER
    if plan["already_installed"]:
        result["status"] = "already installed"
        result["message"] = f"Pace {release['tag']} (commit {release['commit']}) is already installed here."
        return result
    if not release["pinned"]:
        result["status"] = "not pinned"
    result["go_ahead_needed"] = (
        f"An IT change reference for Pace {release['tag']} at commit {release['commit']}."
        if central else
        f"The owner's exact-act confirmation for Pace {release['tag']} at commit {release['commit']} "
        "(use prepare, then confirm), or their own words naming both."
    )
    result["message"] = "This is a preview. Nothing has been installed or recorded."
    renames = folder_renames(folder, release)
    lines = old_folder_lines(folder, plan)
    archive = archive_stop(folder, release) or numbers_stop(folder, release)
    if archive:
        result["status"] = "cannot install"
        result["message"] += " " + archive
    if renames:
        result["folders_to_rename"] = renames
        result["message"] += " " + renames_message(renames, lines) + " The install stops until then."
    elif lines:
        result["pace_md_old_folder_lines"] = lines
        result["message"] += " After the install: " + old_lines_message(lines)
    if not release["pinned"]:
        result["message"] += (" The commit was not pinned: confirm it with whoever published the release, "
                              "then give it with --commit.")
    return result


# -------------------------------------------------------------------- go-ahead

def _install_act(root: Path, plan: dict) -> bytes:
    """One reproducible exact act: destination, source, old and new Product, and changes."""
    release = plan["release"]
    return _pretty({
        "format": ACT_FORMAT,
        "act": "Install this pinned release into this person's local Pace Product folder",
        "pace_folder": str(root),
        "repository": release["repository"],
        "tag": release["tag"],
        "commit": release["commit"],
        "product_file_list_digest": plan["new_summary"]["digest"],
        "before_product_file_list_digest": plan["old_summary"]["digest"],
        "changes": plan["changes"],
        "upstream": plan["upstream"],
        "pace_md": {key: plan["pace_md"].get(key) for key in ("status", "before_sha256", "after_sha256", "parts")},
    })


def prepare(root, repo: str, tag: str, commit: str, *, upstream: dict | None = None,
            expect_digest: str | None = None) -> dict:
    """Save and read back a proposed local install for the owner to inspect and confirm."""
    folder = _root(root)
    leftover = _leftover(folder)[0] if _work_area(folder).exists() else None
    if leftover not in (None, "staging"):
        raise Stop(_leftover_message(leftover, "prepare the proposal"))
    if not (folder / "Pace.md").is_file():
        raise Stop("A local proposal needs a person's Pace.md; central copies use IT change control.")
    plan = _plan(folder, repo, tag, check_commit_id(commit), upstream, expect_digest)
    archive = archive_stop(folder, plan["release"]) or numbers_stop(folder, plan["release"])
    if archive:
        raise Stop(archive + " No proposal was saved.")
    renames = folder_renames(folder, plan["release"])
    if renames:
        raise Stop(renames_message(renames, old_folder_lines(folder, plan)) + " No proposal was saved.")
    content = _install_act(folder, plan)
    location = folder / RELEASE_RECORD / PROPOSALS
    path = _new_file_path(location, f"{_stamp(_now())}-{_safe_name(tag)}", ".json")
    _write_new(path, content)
    return {"command": "prepare", "status": "proposed", "installed": False,
            "act_file": str(path), "act_sha256": _sha256(content),
            "message": "The proposed local install was saved and read back. Show the file and the preview to the owner; no update is installed or confirmed."}


def _check_confirmation(root: Path, request: str, expected: bytes) -> str:
    """Use the record tool's current-state check, then compare the full proposed act."""
    tool = Path(__file__).with_name("pace_record.py")
    if not tool.is_file():
        raise Stop("The record tool is missing; the exact-act confirmation cannot be checked.")
    spec = importlib.util.spec_from_file_location("pace_record_for_update", tool)
    record = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(record)
    if not record.REQUEST.fullmatch(request or ""):
        raise Stop("Give a valid exact-act confirmation request id from Record/.")
    reader = getattr(record, "record_name", None)  # finds a confirmation archived into its month folder
    name = reader(root / "Record", request) if reader else f"{request}.md"
    item = record.load(root / "Record", name)
    fields = item.get("fields") or {}
    if item["state"] != "readable" or record.one(fields, "kind") != "confirmation":
        raise Stop("The exact-act confirmation is not a readable confirmation record in Record/.")
    act_path = record.confirmation_file(root, record.one(fields, "act-file"))
    # The proposal belongs to this person's folder. Do not follow a reference to an outside file.
    if not act_path.is_relative_to(root / RELEASE_RECORD / PROPOSALS):
        raise Stop("The confirmation must name a proposal inside this Pace folder's Release record/Proposals/.")
    state, code = record.confirmation_state(root, request, str(act_path))
    if code or state["status"] != "confirmed":
        raise Stop(f"The exact-act confirmation is not current: {state['message']}")
    if act_path.read_bytes() != expected:
        raise Stop("The confirmed proposal does not match this install's source, destination or before-and-after. Prepare a new proposal and ask the owner again.")
    return f"Record/{name}"


def _names_release(words: str, tag: str, commit: str) -> bool:
    tag_ok = re.search(r"(?<![\w.-])" + re.escape(tag) + r"(?![\w-]|\.\w)", words) is not None
    commit_ok = re.search(r"(?<![0-9a-f])" + commit + r"(?![0-9a-f])", words.lower()) is not None
    return tag_ok and commit_ok


def _check_go_ahead_words(words: str, tag: str, commit: str) -> str:
    words = (words or "").strip()
    if not words:
        raise Stop("The owner's go-ahead is empty.")
    if not _names_release(words, tag, commit):
        raise Stop(
            f"The owner's go-ahead must name the exact tag {tag} and the full commit {commit}. "
            "Ask the owner; a tag alone, a short commit or a general yes is not enough."
        )
    return words


def _check_go_ahead_record(root: Path, path: str, tag: str, commit: str) -> str:
    folder = (root / RELEASE_RECORD).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = folder / candidate
    candidate = candidate.resolve()
    if folder not in candidate.parents or not candidate.is_file():
        raise Stop(f"The go-ahead record must be a file inside this folder's {RELEASE_RECORD}/.")
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Stop("The go-ahead record could not be read.") from None
    release = data.get("release", {}) if isinstance(data, dict) else {}
    if (data.get("format") != GO_AHEAD_FORMAT or release.get("tag") != tag
            or str(release.get("commit", "")).lower() != commit
            or not _names_release(str(data.get("owner_words", "")), tag, commit)):
        raise Stop(f"The go-ahead record does not name the exact tag {tag} and commit {commit}.")
    return candidate.relative_to(folder).as_posix()


def _record_go_ahead(root: Path, words: str, release: dict, moment: datetime) -> str:
    folder = root / RELEASE_RECORD / GO_AHEADS
    folder.mkdir(parents=True, exist_ok=True)
    path = _new_file_path(folder, f"{_stamp(moment)}-{_safe_name(release['tag'])}-{release['commit'][:12]}", ".json")
    _write_new(path, _pretty({
        "format": GO_AHEAD_FORMAT,
        "time": _iso(moment),
        "release": {"repository": release["repository"], "tag": release["tag"], "commit": release["commit"]},
        "owner_words": words,
        "note": (
            "The owner's own words, recorded before a local install of this exact tag and commit. "
            "This is a recorded go-ahead, not a signature or an identity check."
        ),
    }))
    return path.relative_to(root / RELEASE_RECORD).as_posix()


# ------------------------------------------------------------------- recording

def _describe(tag, commit) -> str:
    return f"Pace {tag} (commit {commit})" if tag else "a Product with no earlier install recorded here"


def _append_receipt(root: Path, line: str) -> None:
    """Add one line to the install receipts. Earlier lines are never changed."""
    path = root / RELEASE_RECORD / RECEIPTS
    before = path.read_bytes() if path.exists() else None
    if before is None:
        addition = (RECEIPTS_HEADER + line + "\n").encode("utf-8")
    else:
        addition = (("" if not before or before.endswith(b"\n") else "\n") + line + "\n").encode("utf-8")
    with open(path, "ab") as handle:
        handle.write(addition)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != (before or b"") + addition:
        raise OSError("The install receipts did not read back as written")


def _write_record(root: Path, record: dict, name: str) -> str:
    _write_new(root / RELEASE_RECORD / INSTALLS / name, _pretty(record))
    return f"{INSTALLS}/{name}"


# ---------------------------------------------------------------- the install

def _write_journal(work: Path, journal: dict) -> None:
    temp = work / "journal.json.tmp"
    with open(temp, "wb") as handle:
        handle.write(_pretty(journal))
        handle.flush()
        os.fsync(handle.fileno())
    _rename(temp, work / "journal.json", replace=True)


def _put_back_previous(root: Path, work: Path, old_digest: str | None) -> bool:
    """Put the previous Product back from the work area, if it is there, and check it.

    Returns whether anything was moved. The work area is left for the caller to remove.
    """
    product, previous = root / PRODUCT, work / "previous" / PRODUCT
    moved = previous.exists()
    try:
        if moved:
            if product.exists() or _is_link(product):
                (work / "discarded").mkdir(exist_ok=True)
                _rename(product, work / "discarded" / PRODUCT)
            _rename(previous, product)
    except OSError as error:
        raise NeedsHelp(
            f"The previous Product could not be moved back ({error}). The work files are kept in "
            f"{RELEASE_RECORD}/{WORK}/; see Product updates in the help before changing anything."
        ) from None
    if not product.is_dir():
        raise NeedsHelp(
            f"The previous Product could not be found. The work files are kept in "
            f"{RELEASE_RECORD}/{WORK}/; see Product updates in the help before changing anything."
        )
    if old_digest is not None and file_list_digest(read_tree(product)) != old_digest:
        raise NeedsHelp(
            f"The restored Product does not match the one that was installed before. The work files are kept "
            f"in {RELEASE_RECORD}/{WORK}/; see Product updates in the help before changing anything."
        )
    return moved


def _remove_file(path: Path) -> None:
    try:
        os.unlink(path)
    except PermissionError:
        if _is_link(path):
            raise
        os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IWRITE)  # Windows: clear read-only
        os.unlink(path)


def _clear_work_area(work: Path) -> None:
    """Remove the work area, its journal last.

    If a file cannot be removed (held open by a sync client or virus scanner, say), the journal
    is still there, so the next run knows what the leftover files belong to.
    """
    journal = work / "journal.json"
    for item in sorted(work.iterdir()):
        if item.name == journal.name:
            continue
        if item.is_dir() and not _is_link(item):
            _remove_tree(item)
        else:
            _remove_file(item)
    if journal.exists() or _is_link(journal):
        _remove_file(journal)
    work.rmdir()


def _tidy(work: Path) -> str | None:
    """Remove the work area once nothing in it is needed. Returns a warning if that was not possible."""
    try:
        _clear_work_area(work)
    except OSError as error:
        return (f"The leftover work files in {RELEASE_RECORD}/{WORK}/ could not be removed ({error}). Nothing "
                "depends on them; once nothing holds them open, run apply with only --root to tidy them.")
    return None


def _join(*warnings) -> str | None:
    return " ".join(filter(None, warnings)) or None


def _rollback_record(journal: dict, reason: str, moment: datetime, corrects: str | None) -> dict:
    record = {
        "format": RECORD_FORMAT,
        "attempt": journal["attempt"],
        "time": _iso(moment),
        "result": "rolled back",
        "reason": reason,
        "kind": journal["kind"],
        "repository": journal["repository"],
        "tag": journal["tag"],
        "commit": journal["commit"],
        "product_file_list": {"format": FILE_LIST_FORMAT, "digest": journal["new_digest"]},
        "upstream": journal.get("upstream"),
        "prior": journal["prior"],
        "restored_product_file_list_digest": journal["old_digest"],
        "owner_go_ahead": journal.get("owner_go_ahead"),
        "confirmation": journal.get("confirmation"),
        "it_change": journal.get("it_change"),
    }
    if corrects:
        record["corrects"] = corrects
    return record


def _record_rollback(root: Path, journal: dict, reason: str) -> str | None:
    """Record a roll-back. Returns a warning if the record could not be written."""
    moment = _now()
    planned = journal.get("record_file")
    corrects = planned if planned and (root / RELEASE_RECORD / INSTALLS / planned).exists() else None
    name = _new_file_path(root / RELEASE_RECORD / INSTALLS,
                          f"{_stamp(moment)}-{_safe_name(journal['tag'])}-{journal['commit'][:12]}", ".json").name
    after = ("Product was not touched." if journal.get("phase") == "staging"
             else "The previous Product was put back and read back.")
    try:
        written = _write_record(root, _rollback_record(journal, reason, moment, corrects), name)
        _append_receipt(root, (
            f"- {_plain_time(_iso(moment))} - Not installed: Pace {journal['tag']} (commit {journal['commit']}). {reason} "
            f"{after} Details: {written}"
        ))
    except OSError as error:
        return f"The roll-back worked but could not be recorded in {RELEASE_RECORD}/: {error}"
    return None


def _rollback_recorded(root: Path, attempt) -> bool:
    return bool(attempt) and any(data.get("attempt") == attempt and data.get("result") == "rolled back"
                                 for _, data in _install_records(root))


def _matches_installed(root: Path) -> bool:
    """True when Product is exactly the release recorded as installed here, by its file-list fingerprint."""
    prior = installed_release(root) or {}
    digest = prior.get("product_file_list", {}).get("digest")
    product = root / PRODUCT
    if not digest or _is_link(product) or not product.is_dir():
        return False
    try:
        return file_list_digest(_without_system_files(read_tree(product))) == digest
    except (OSError, Stop):
        return False


def _leftover(root: Path) -> tuple:
    """What an earlier update left in the work area, and its journal if it has a readable one.

    "finished": the install is complete and recorded; only tidying is left.
    "rolled back": the roll-back is complete and recorded; only tidying is left.
    "staging": there is no journal and Product was never moved.
    "interrupted": the journal shows an update that stopped part-way.
    "unreadable": the journal cannot be read.
    "unclear": there is no journal, Product may have been moved, and it is not the recorded release.
    """
    work = _work_area(root)
    journal_path = work / "journal.json"
    if journal_path.is_file():
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if not isinstance(journal, dict) or journal.get("format") != JOURNAL_FORMAT:
                raise ValueError
        except (OSError, ValueError):
            return "unreadable", None
        if journal.get("phase") == "recorded":
            return "finished", journal
        if _rollback_recorded(root, journal.get("attempt")):
            return "rolled back", journal
        return "interrupted", journal
    if not any((work / name).exists() for name in ("previous", "discarded")):
        return "staging", None
    # An earlier updater could remove the journal and then fail to remove the rest. When
    # Product is the release recorded as installed, what is left is no longer needed.
    if _matches_installed(root):
        return "finished", None
    return "unclear", None


STAGING_LEFTOVER = (f"{RELEASE_RECORD}/{WORK}/ holds files an earlier update left before it changed anything; "
                    "Product was not touched. The next apply on a computer that can replace files removes them.")


def _leftover_message(state: str, then: str) -> str:
    if state == "finished":
        first = "The last install finished but left its work files. Run apply with only --root to tidy them"
    elif state == "rolled back":
        first = "An earlier update was rolled back but left its work files. Run apply with only --root to tidy them"
    else:
        first = "An earlier update was interrupted. Run apply with only --root to put the previous Product back"
    return f"{first}, then {then}."


def recover(root) -> dict | None:
    """Finish, undo or tidy up an earlier apply. Returns None when there is nothing to recover."""
    folder = Path(root).expanduser().resolve()
    work = _work_area(folder)
    if not work.exists():
        return None
    state, journal = _leftover(folder)
    if state == "unreadable":
        raise NeedsHelp(
            f"The journal in {RELEASE_RECORD}/{WORK}/ cannot be read. Nothing was changed; "
            "see Product updates in the help before moving anything."
        )
    if state == "unclear":
        raise NeedsHelp(
            f"{RELEASE_RECORD}/{WORK}/ holds a previous Product but no journal. Nothing was changed; "
            "see Product updates in the help before moving anything."
        )
    check_can_replace(folder)  # before anything is moved or removed
    if state == "staging":
        _clear_work_area(work)
        return {"command": "apply", "status": "recovered", "installed": False, "changed": False,
                "message": "Removed an unfinished update's staging files. Product was not touched."}
    if state == "finished" and journal is None:
        prior = installed_release(folder)
        result = {"command": "apply", "status": "recovered", "installed": True, "changed": False,
                  "tag": prior.get("tag"), "commit": prior.get("commit"),
                  "message": (f"Pace {prior.get('tag')} (commit {prior.get('commit')}) is in place as recorded in "
                              f"{_kept_by(prior)}, so the work files an earlier update left were removed.")}
        warning = _tidy(work)
    elif state == "finished":
        if file_list_digest(read_tree(folder / PRODUCT)) != journal["new_digest"]:
            raise NeedsHelp("The installed Product no longer matches its install record. The work files are kept.")
        result = {"command": "apply", "status": "recovered", "installed": True, "changed": False,
                  "tag": journal["tag"], "commit": journal["commit"],
                  "message": f"The earlier install of Pace {journal['tag']} had finished; its leftover work files were removed."}
        warning = _join(_note_install(folder, journal), _tidy(work))
    else:
        moved = _put_back_previous(folder, work, journal["old_digest"])
        if state == "rolled back":
            recorded = None  # recorded when it was rolled back; never twice
            message = (f"The earlier update to Pace {journal['tag']} had already been rolled back and recorded; "
                       "its leftover work files were removed.")
        else:
            recorded = _record_rollback(folder, journal, "An earlier update was interrupted and has been rolled back.")
            message = (f"An interrupted update to Pace {journal['tag']} was rolled back. The previous Product "
                       "is back and was read back. Nothing new was installed.")
        result = {"command": "apply", "status": "recovered", "installed": False, "changed": moved,
                  "tag": journal["tag"], "commit": journal["commit"], "message": message}
        warning = _join(recorded, _tidy(work))
    if warning:
        result["warning"] = warning
    return result


def apply(root, repo: str, tag: str, commit: str, *, upstream: dict | None = None,
          expect_digest: str | None = None, central: bool = False, it_change: str | None = None,
          go_ahead: str | None = None, go_ahead_record: str | None = None,
          confirmation_request: str | None = None, replace_changed_product: bool = False) -> dict:
    """Install one pinned release into this Pace folder's Product and record the result."""
    folder = _root(root)
    recovered = recover(folder)
    if recovered is not None:
        recovered["message"] += " Run apply again to install a release."
        return recovered
    commit = check_commit_id(commit)
    check_tag_name(tag)
    it_change = (it_change or "").strip() or None
    go_ahead_ref = None
    confirmation_ref = None
    if central:
        if go_ahead or go_ahead_record or confirmation_request:
            raise Stop("A central copy is installed under client IT change control, not an owner go-ahead.")
        if not it_change:
            raise Stop("A central install needs the client IT change reference (--it-change).")
        if (folder / "Pace.md").exists():
            raise Stop("This folder has a Pace.md, so it is a person's own Pace folder, not a central copy. "
                       "A local install needs the owner's go-ahead.")
    else:
        if sum(bool(value) for value in (go_ahead, go_ahead_record, confirmation_request)) != 1:
            raise Stop(
                f"A local install needs the owner's go-ahead for Pace {tag} and commit {commit}: give "
                "--confirmation-request, --go-ahead, or --go-ahead-record (one only)."
            )
        if go_ahead:
            go_ahead = _check_go_ahead_words(go_ahead, tag, commit)
        elif go_ahead_record:
            go_ahead_ref = _check_go_ahead_record(folder, go_ahead_record, tag, commit)

    plan = _plan(folder, repo, tag, commit, upstream, expect_digest)
    release = plan["release"]
    archive = archive_stop(folder, release) or numbers_stop(folder, release)
    if archive:
        raise Stop(archive + " Nothing was installed.")
    renames = folder_renames(folder, release)
    if renames:
        raise Stop(renames_message(renames, old_folder_lines(folder, plan)) + " Nothing was installed.")
    if confirmation_request:
        confirmation_ref = _check_confirmation(folder, confirmation_request, _install_act(folder, plan))
    if plan["already_installed"]:
        result = {"command": "apply", "status": "already installed", "installed": True, "changed": False,
                  **_public(plan),
                  "message": f"Pace {tag} (commit {commit}) is already installed here. Nothing was changed."}
        if plan["pace_md"].get("status") == "update":
            try:
                check_can_replace(folder)
                pace_md = update_pace_md(folder, plan["pace_md"])
            except CannotReplace as error:
                pace_md = {**_pace_md_public(plan["pace_md"]), "status": "not updated",
                           "message": f"Pace.md was not updated: {error}"}
            result["pace_md"] = pace_md
            result["changed"] = pace_md["status"] == "updated"
            result["message"] = (f"Pace {tag} (commit {commit}) is already installed here, so Product was not changed. "
                                 + pace_md["message"])
            if pace_md.get("warning"):
                result["warning"] = pace_md["warning"]
        return result
    moved = plan["changed_since_record"]
    # With nothing to check against, an install that changes no file loses nothing.
    if moved and not replace_changed_product and not (moved.get("not_checked") and plan["old"] == plan["new"]):
        files = moved["added"] + moved["changed"] + moved["removed"]
        if moved.get("not_checked"):
            what = ("Whether files inside the installed Product were edited cannot be checked, because "
                    f"{_kept_by(plan['prior'])} keeps no Product file list for the installed release")
        elif moved.get("not_listed"):
            what = f"Files inside the installed Product differ from the release noted in {_note_where()}"
        else:
            what = (f"{len(files)} file(s) inside the installed Product differ from the recorded install "
                    f"({', '.join(files[:5])}{'...' if len(files) > 5 else ''})")
        raise Stop(
            f"{what}. Product is replaced as a whole, so move anything you want to keep to {OWNER_ADDINS}/ "
            "first, or pass --replace-changed-product."
        )

    check_can_replace(folder)  # before the first write, so a folder that only allows new files is left as it was
    moment = _now()
    if go_ahead:
        go_ahead_ref = _record_go_ahead(folder, go_ahead, release, moment)
    kind = "central copy" if central else "local install"
    before = snapshot_outside_product(folder)
    installs = folder / RELEASE_RECORD / INSTALLS
    installs.mkdir(parents=True, exist_ok=True)
    record_name = _new_file_path(installs, f"{_stamp(moment)}-{_safe_name(tag)}-{commit[:12]}", ".json").name
    journal = {
        "format": JOURNAL_FORMAT,
        "phase": "staging",
        "attempt": str(uuid.uuid4()),
        "started": _iso(moment),
        "kind": kind,
        "repository": release["repository"],
        "source": note_repository(repo),
        "tag": tag,
        "commit": commit,
        "old_digest": plan["old_summary"]["digest"],
        "new_digest": plan["new_summary"]["digest"],
        "prior": _prior_view(plan),
        "upstream": plan["upstream"],
        "owner_go_ahead": None if central else go_ahead_ref,
        "confirmation": confirmation_ref,
        "it_change": it_change,
        "record_file": record_name,
    }
    work = _work_area(folder)
    work.mkdir()
    try:
        _write_journal(work, journal)
        staged = work / "staged" / PRODUCT
        for path, data in release["files"].items():
            _write_new(staged / path, data)
        if read_tree(staged) != plan["new"]:
            raise Stop("The staged Product does not match the release's file list.")
        _checkpoint("staged")
        if confirmation_request:
            _check_confirmation(folder, confirmation_request, _install_act(folder, plan))
        if read_tree(folder / PRODUCT) != plan["old"]:
            raise Stop("The installed Product changed after the proposal. Prepare and confirm a new proposal.")

        journal["phase"] = "swapping"
        _write_journal(work, journal)
        (work / "previous").mkdir()
        _rename(folder / PRODUCT, work / "previous" / PRODUCT)
        _checkpoint("old-moved")
        _rename(staged, folder / PRODUCT)
        _checkpoint("new-in-place")

        if read_tree(folder / PRODUCT) != plan["new"]:
            raise RuntimeError("The installed Product files did not read back as the release's file list.")
        changed_outside = _differences(before, snapshot_outside_product(folder))
        if changed_outside:
            shown = ", ".join(changed_outside[:5]) + ("..." if len(changed_outside) > 5 else "")
            raise RuntimeError(
                f"Files outside Product changed during the update ({shown}). They were left as they are; "
                "the updater never rewrites them."
            )
        unread = not_checked(before)
        journal["phase"] = "installed"
        _write_journal(work, journal)
        _checkpoint("read-back")

        claim = ("Installed locally: the Product files on this computer were read back and match the release."
                 if not central else
                 "Installed in this central copy: its Product files were read back and match the release.")
        record = {
            "format": RECORD_FORMAT,
            "attempt": journal["attempt"],
            "started": journal["started"],
            "time": _iso(_now()),
            "result": "installed",
            "kind": kind,
            "claim": claim,
            "onedrive": "Not checked. Arrival in OneDrive, or in users' copies, is a separate claim.",
            "repository": release["repository"],
            "tag": tag,
            "commit": commit,
            "product_file_list": {**plan["new_summary"], "entries": file_list(plan["new"])},
            "upstream": plan["upstream"],
            "prior": journal["prior"],
            "changes": plan["changes"],
            "shipped_addins": plan["shipped_addins"],
            "owner_go_ahead": journal["owner_go_ahead"],
            "confirmation": journal["confirmation"],
            "it_change": it_change,
            "outside_product": {
                "unchanged": True,
                "checked": ("Names, sizes and modification times of everything outside Product/ and "
                            f"{RELEASE_RECORD}/, and the bytes of " + ", ".join(HASHED_OWNER_FILES) + "."),
                **({"not_checked": unread,
                    "why_not_checked": "The updater is not allowed to read these, and it never writes there."}
                   if unread else {}),
            },
        }
        written = _write_record(folder, record, record_name)
        _checkpoint("record-written")
        if central:
            authority = f"under IT change {it_change}"
        else:
            authority = (f"with the owner's recorded confirmation in {confirmation_ref}" if confirmation_ref
                         else f"with the owner's go-ahead in {go_ahead_ref}")
            if it_change:
                authority += f" and IT change {it_change}"
        where = "Installed locally" if not central else "Installed in this central copy"
        _append_receipt(folder, (
            f"- {_plain_time(record['time'])} - {where}: Pace {tag} (commit {commit}), replacing "
            f"{_describe(journal['prior']['tag'], journal['prior']['commit'])}, {authority}. The installed files "
            f"were read back and match the release. Arrival in OneDrive is not checked. Details: {written}"
        ))
        journal["phase"] = "recorded"
        journal["recorded"] = record["time"]
        _write_journal(work, journal)
    except Exception as error:  # anything that went wrong: put the old Product back
        touched = journal["phase"] != "staging"
        _put_back_previous(folder, work, journal["old_digest"])
        # Record the roll-back before tidying, so a file that cannot be removed never loses the record.
        warning = _join(_record_rollback(folder, journal, f"The update stopped: {error}"), _tidy(work))
        after = "The previous Product was put back and read back." if touched else "Product was not touched."
        result = {"command": "apply", "status": "rolled back", "installed": False, "changed": touched,
                  **_public(plan), "reason": str(error),
                  "message": f"Pace {tag} was not installed: {error} {after}"}
        if warning:
            result["warning"] = warning
        return result
    except BaseException:  # Ctrl-C and similar: put the old Product back, then stop
        _put_back_previous(folder, work, journal["old_digest"])
        _record_rollback(folder, journal, "The update was cancelled.")
        _tidy(work)
        raise
    # The install is complete and recorded. Noting it in the release note and clearing
    # the work area follow; if they stop, the next run sees the "recorded" journal and finishes them.
    _checkpoint("recorded")
    note_warning = _note_install(folder, journal)
    _checkpoint("noted")
    pace_md = update_pace_md(folder, plan["pace_md"])
    lines = old_folder_lines(folder, plan) if pace_md.get("status") != "not updated" else []
    result = {"command": "apply", "status": "installed", "installed": True, "changed": True,
              **_public(plan), "record": f"{RELEASE_RECORD}/{written}",
              "owner_go_ahead": journal["owner_go_ahead"], "confirmation": confirmation_ref,
              "it_change": it_change,
              "onedrive": "not checked",
              "message": (f"{claim} Pace {tag} (commit {commit}) is in place. Whether OneDrive has received "
                          "it is a separate check.")}
    if unread:
        result["not_checked"] = unread
        result["message"] += f" Not checked, because the updater may not read them: {_list(unread)}."
    result["pace_md"] = pace_md
    if pace_md.get("status") in ("updated", "not updated"):
        result["message"] += " " + pace_md["message"]
    if lines:
        result["pace_md_old_folder_lines"] = lines
    warning = _join(note_warning, pace_md.get("warning"), _tidy(work), old_lines_message(lines) if lines else None)
    if warning:
        result["warning"] = warning
    return result


# ------------------------------------------------------------------- reporting

def _list(paths, limit: int = 12) -> str:
    shown = ", ".join(paths[:limit])
    return shown + (f" and {len(paths) - limit} more" if len(paths) > limit else "")


def _shell_word(value: str, windows: bool | None = None) -> str:
    """A value quoted so that, pasted into a terminal, it stays one option value.

    A OneDrive folder such as "OneDrive - Company" has spaces. Windows terminals take
    double quotes; other systems take single quotes.
    """
    if (os.name == "nt") if windows is None else windows:
        if re.fullmatch(r"[\w@+=:./\\~-]+", value, re.ASCII):
            return value
        # A backslash just before the closing quote would escape it, so double any at the end.
        trailing = len(value) - len(value.rstrip("\\"))
        return f'"{value}{chr(92) * trailing}"'
    return shlex.quote(value)


def render(result: dict) -> str:
    """Plain-language report for the person running the update."""
    lines = []
    if result.get("release_source"):
        source = result["release_source"]
        copy_of = f" (a client copy of {source['upstream_repository']})" if source.get("upstream_repository") else ""
        lines.append(f"Release source: {source['repository']}{copy_of}, read from {_note_where()}.")
    if "tag" in result and "product_file_list" in result:
        lines.append(f"Release: Pace {result['tag']} from {result['repository']}")
        pin = "the tag still points to this pinned commit" if result.get("commit_pinned") else \
            "the tag points here now; pin this full commit for apply"
        lines.append(f"Commit: {result['commit']} ({pin})")
        summary = result["product_file_list"]
        lines.append(f"Product files in the release: {summary['files']} files, file list {summary['digest']}")
        if result.get("upstream"):
            up = result["upstream"]
            lines.append(f"Same Product file list as upstream Pace {up['tag']} (commit {up['commit']}) from {up['repository']}")
        now = result["installed_now"]
        moved = result.get("changed_since_record") or {}
        if now["tag"]:
            state = ("whether the installed files were edited since then cannot be checked, because it keeps no "
                     "Product file list" if moved.get("not_checked") else
                     "the installed files still match that record" if now["matches_record"] else
                     "some installed files differ from that record")
            lines.append(f"Installed now: Pace {now['tag']} (commit {now['commit']}), recorded in "
                         f"{RELEASE_RECORD}/{now['record']}; {state}.")
        else:
            lines.append("Installed now: no earlier install is recorded in this folder.")
        if moved and not moved.get("not_checked"):
            lines.append("  Changed inside Product since that install: " + (
                "files not named, because the release note keeps a fingerprint rather than a file list"
                if moved.get("not_listed") else _list(moved["added"] + moved["changed"] + moved["removed"])))
        compared = result.get("compared_with_installed")
        if compared == "newer":
            lines.append(f"Update available: Pace {result['tag']} is newer than the installed {now['tag']}.")
        elif compared == "older":
            lines.append(f"The newest release here, Pace {result['tag']}, is older than the installed {now['tag']}. "
                         "Do not install it unless the owner wants to go back.")
        elif compared == "moved":
            lines.append(f"The tag {result['tag']} now points to a different commit from the one installed. "
                         "Check with whoever published it before installing anything.")
        changes = result["changes"]
        if result["status"] not in ("already installed", "installed"):
            lines.append("What would change in Product:")
        else:
            lines.append("Changes in Product:")
        for label in ("added", "changed", "removed"):
            if changes[label]:
                lines.append(f"  {label} ({len(changes[label])}): {_list(changes[label])}")
        lines.append(f"  unchanged: {changes['unchanged']} files")
        addins = result["shipped_addins"]
        parts = [f"{label} {_list(addins[label])}" for label in ("added", "changed", "removed") if addins[label]]
        if parts:
            lines.append("Shipped add-ins (they update with Product): " + "; ".join(parts))
        lines.append("Never changed by an update: " + ", ".join(p for p in PROTECTED if p != "Pace.md")
                     + ", and your own lines in Pace.md.")
        pace_md = result.get("pace_md") or {}
        if pace_md.get("status") == "update":
            lines.append("Pace.md would change: " + _pace_md_summary(pace_md["parts"]) + ". Your own lines stay as they are.")
        elif pace_md.get("status") not in (None, "no Pace.md") and pace_md.get("message"):
            lines.append(pace_md["message"])
        if result["owner_addins_never_updated"]:
            lines.append(f"Your own add-ins stay as they are: {_list(result['owner_addins_never_updated'])}")
        if result["pace_md_links_removed"]:
            lines.append("Pace.md mentions Product files this release removes: "
                         + _list(result["pace_md_links_removed"]) + ". Ask the owner what to use instead.")
        if result.get("go_ahead_needed") and result["status"] == "ready":
            lines.append("Needed before apply: " + result["go_ahead_needed"])
        if result.get("latest") and result["status"] == "ready":
            lines.append(f"This is the newest release. To install it, use exactly --repo {_shell_word(result['repository'])} "
                         f"--tag {_shell_word(result['tag'])} --commit {_shell_word(result['commit'])}.")
    if result.get("act_file"):
        lines.append(f"Proposal: {result['act_file']} (sha256:{result['act_sha256']}).")
    if result.get("record"):
        lines.append(f"Recorded in {result['record']}.")
    lines.append(result.get("message", ""))
    if result.get("warning"):
        lines.append("Warning: " + result["warning"])
    return "\n".join(line for line in lines if line) + "\n"


# ------------------------------------------------------------------------ CLI

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pace_update.py",
        description="Preview or apply a Pace Product update from a release tag pinned to its full commit.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "prepare", "apply"):
        sub = commands.add_parser(name, help=("show what a release would change" if name == "preview"
                                              else "save a local proposal" if name == "prepare"
                                              else "install a release into Product"))
        sub.add_argument("--root", required=True, help="the Pace folder (or central copy) that holds Product/")
        sub.add_argument("--repo", help="the git repository address or folder to pull from (overrides the release note)")
        sub.add_argument("--tag", help="the release tag, for example v3.5.0")
        if name == "preview":
            sub.add_argument("--latest", action="store_true",
                             help="find the newest numbered release and show its full commit; without --repo, "
                                  "the repository is read from Release record/Installed release.md")
        sub.add_argument("--commit", help="the full commit id the tag must point to"
                         + (" (optional for preview)" if name == "preview" else ""))
        sub.add_argument("--upstream-repo", help="for a fork or mirror: the upstream repository")
        sub.add_argument("--upstream-tag", help="for a fork or mirror: the upstream release tag")
        sub.add_argument("--upstream-commit", help="for a fork or mirror: the upstream full commit")
        sub.add_argument("--file-list-digest", help="stop unless the release's Product file list has this digest")
        sub.add_argument("--central", action="store_true", help="this is a central client IT copy, not a person's folder")
        sub.add_argument("--json", action="store_true", help="print the result as JSON")
        if name == "apply":
            sub.add_argument("--go-ahead", help="the owner's own words naming the exact tag and full commit")
            sub.add_argument("--go-ahead-record", help="an earlier go-ahead record in Release record/")
            sub.add_argument("--confirmation-request", help="current exact-act confirmation request in Record/ for a prepared local proposal")
            sub.add_argument("--it-change", help="the client IT change reference")
            sub.add_argument("--replace-changed-product", action="store_true",
                             help="replace Product even though files inside it changed since the recorded install")
    return parser


def _upstream(args) -> dict | None:
    given = [args.upstream_repo, args.upstream_tag, args.upstream_commit]
    if not any(given):
        return None
    if not all(given):
        raise Stop("For a fork or mirror, give all three of --upstream-repo, --upstream-tag and --upstream-commit.")
    return {"repo": args.upstream_repo, "tag": args.upstream_tag, "commit": args.upstream_commit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    noted = None
    try:
        if Path.cwd().resolve().is_relative_to(Path(args.root).expanduser().resolve() / PRODUCT):
            raise Stop("Run the updater from outside the Product folder; a folder in use cannot be replaced.")
        if args.command == "preview" and args.latest:
            if args.tag or args.commit:
                raise Stop("Use --latest by itself, or give --tag and --commit for a chosen release.")
            if any((args.upstream_repo, args.upstream_tag, args.upstream_commit)):
                raise Stop("For a fork or mirror, give the chosen tag and commit explicitly.")
            if not args.repo:  # an explicit --repo always overrides the release note
                noted = release_source(_root(args.root))
                args.repo = noted["repository"]
            args.tag, args.commit = latest_release(args.repo)
        if args.command == "apply" and not (args.repo or args.tag or args.commit):
            result = recover(_root(args.root)) or {
                "command": "apply", "status": "stopped", "installed": False, "changed": False,
                "message": "Nothing to recover. To install, give --repo, --tag and --commit."}
        else:
            if not (args.repo and args.tag) or (args.command != "preview" and not args.commit):
                raise Stop("Give --repo and --tag" + (" and the full --commit." if args.command != "preview" else "."))
            common = dict(upstream=_upstream(args), expect_digest=args.file_list_digest)
            if args.command == "preview":
                result = preview(args.root, args.repo, args.tag, args.commit, central=args.central, **common)
                if args.latest:
                    result["latest"] = True
                    if noted:
                        result["release_source"] = {key: noted[key] for key in ("repository", "upstream_repository")
                                                    if noted.get(key)}
                    if "installed_now" in result:
                        result["compared_with_installed"] = compare_with_installed(
                            result["installed_now"], result["tag"], result["commit"])
                    if result["status"] == "already installed":
                        result["message"] += (f" It is the newest release in {result['repository']}, "
                                              "so there is nothing to update.")
            elif args.command == "prepare":
                if args.central:
                    raise Stop("A central copy uses client IT change control, not a local owner proposal.")
                result = prepare(args.root, args.repo, args.tag, args.commit, **common)
            else:
                result = apply(args.root, args.repo, args.tag, args.commit, central=args.central, **common,
                               it_change=args.it_change, go_ahead=args.go_ahead,
                               go_ahead_record=args.go_ahead_record,
                               confirmation_request=args.confirmation_request,
                               replace_changed_product=args.replace_changed_product)
    except Stop as stop:
        kept = getattr(stop, "kept", None)
        result = {"command": args.command, "status": "stopped", "installed": False, "changed": False,
                  "message": f"{stop} Nothing {'else ' if kept else ''}in the Pace folder was changed."}
        if kept:
            result["kept_check_files"] = kept
    except NeedsHelp as problem:
        result = {"command": args.command, "status": "needs help", "installed": False, "changed": True,
                  "message": str(problem)}
    except OSError as error:
        result = {"command": args.command, "status": "stopped", "installed": False, "changed": None,
                  "message": f"The updater stopped on a file error: {error}. Run preview to see the current state."}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render(result), end="")
    good = result["status"] in ("ready", "not pinned", "proposed", "installed", "already installed") or (
        result["status"] == "recovered" and not (args.repo or args.tag or args.commit))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
