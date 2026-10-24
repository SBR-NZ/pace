"""Product updates against invented local git repositories only (no network, no real folders)."""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
TOOL = PACE_FOLDER / "Product/Tools/pace_update.py"
HELP = PACE_FOLDER / "Product/Help/updates.md"

_spec = importlib.util.spec_from_file_location("pace_update", TOOL)
pu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pu)

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Invented Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Invented Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
}
_saved_env = {}


def clean_git_env() -> dict:
    """The environment for a git command on an invented repository.

    Git tells the commands it runs where its repository is: GIT_DIR for a hook, or for
    `git rebase --exec` in a linked worktree. Passed on, that would send every invented
    repository's commands into the surrounding repository, so no inherited git variable is kept.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_ENV)
    return env


# The updater and get-pace.py run git with this process's environment, so drop inherited git variables here too.
for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]


def setUpModule():
    for key, value in GIT_ENV.items():
        _saved_env[key] = os.environ.get(key)
        os.environ[key] = value


def tearDownModule():
    for key, value in _saved_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def git(repo, *args) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=clean_git_env())
    return done.stdout.strip()


class Repo:
    """An invented release repository with the PACE layout."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True)
        git(path, "init", "--quiet", "--initial-branch", "main")

    def write(self, rel, text):
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)

    def remove(self, rel):
        (self.path / rel).unlink()

    def commit(self, message):
        git(self.path, "add", "--all")
        git(self.path, "commit", "--quiet", "--allow-empty", "-m", message)
        return git(self.path, "rev-parse", "HEAD")

    def tag(self, name, commit="HEAD", force=False):
        git(self.path, "tag", *(["--force"] if force else []), "-a", "-m", f"Release {name}", name, commit)

    def product(self, commit) -> dict:
        """The commit's Product bytes, read independently of the updater."""
        names = git(self.path, "ls-tree", "-r", "-z", "--name-only", commit, "--", "PACE/Product").split("\0")
        files = {}
        for name in filter(None, names):
            blob = subprocess.run(["git", "-C", str(self.path), "show", f"{commit}:{name}"],
                                  capture_output=True, check=True, env=clean_git_env()).stdout
            files[name[len("PACE/Product/"):]] = blob
        return files


def tree_bytes(folder: Path, *, skip=()) -> dict:
    """Every file's bytes and every folder under a path; skips top-level names in `skip`."""
    found = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if rel.split("/")[0] in skip:
            continue
        found[rel] = path.read_bytes() if path.is_file() else "folder"
    return found


def owner_view(root: Path) -> dict:
    return tree_bytes(root, skip=("Product", "Release record"))


class NameOrder:
    """An os.scandir listing in name order, as NTFS lists a folder."""

    def __init__(self, listing):
        with listing:
            self._entries = iter(sorted(listing, key=lambda entry: entry.name.casefold()))

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._entries)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


class Lab:
    """An invented upstream repository with three releases and an owner's Pace folder at the first."""

    def __init__(self, base: Path):
        self.base = base
        self.repo = Repo(base / "upstream")
        r = self.repo
        r.write("README.md", "Invented Pace repository.\n")
        r.write("PACE/Pace.md", "# Pace\n\nTemplate entry point v1.\n")
        r.write("PACE/AGENTS.md", "Read Pace.md in this PACE folder.\n")
        r.write("PACE/Record/.gitkeep", "")
        r.write("PACE/My add-ins/.gitkeep", "")
        r.write("PACE/Product/Help/updates.md", "# Product updates\n\nInvented help v1.\n")
        r.write("PACE/Product/Help/records.md", "# Records\n\nInvented help v1.\n")
        r.write("PACE/Product/Help/old.md", "# Old page\n\nRemoved later.\n")
        r.write("PACE/Product/Pace add-ins/Daily brief/ADD-IN.md", "# Daily brief\n\n**Purpose:** v1.\n")
        r.write("PACE/Product/Pace add-ins/Reminders/ADD-IN.md", "# Reminders\n\n**Purpose:** v1.\n")
        r.write("PACE/Product/Tools/pace_update.py", "# invented updater placeholder\n")
        self.c1 = r.commit("Release 3.1.0")
        r.tag("v3.1.0")

        r.write("PACE/Product/Help/updates.md", "# Product updates\n\nInvented help v2.\n")
        r.remove("PACE/Product/Help/old.md")
        r.write("PACE/Product/Pace add-ins/Daily brief/ADD-IN.md", "# Daily brief\n\n**Purpose:** v2.\n")
        r.write("PACE/Product/Pace add-ins/Open work/ADD-IN.md", "# Open work\n\n**Purpose:** v2.\n")
        # PaceFolder templates outside Product change too; an update must never install them.
        r.write("PACE/Pace.md", "# Pace\n\nTemplate entry point v2, would overwrite the owner.\n")
        r.write("PACE/AGENTS.md", "Template pointer v2.\n")
        r.write("PACE/My add-ins/Daily brief - mine/ADD-IN.md", "template copy\n")
        self.c2 = r.commit("Release 3.2.0")
        r.tag("v3.2.0")

        r.write("PACE/Product/Help/records.md", "# Records\n\nInvented help v3.\n")
        self.c3 = r.commit("Release 3.3.0")
        r.tag("v3.3.0")
        git(r.path, "commit", "--quiet", "--allow-empty", "-m", "Unreleased work on main")

        self.root = base / "Owner Pace"
        self.make_folder(self.root, self.c1, owner=True)

    def make_folder(self, root: Path, commit: str, *, owner: bool):
        for rel, data in self.repo.product(commit).items():
            (root / "Product" / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / "Product" / rel).write_bytes(data)
        (root / "Release record").mkdir(parents=True, exist_ok=True)
        if not owner:
            return
        files = {
            "Pace.md": ("# Pace by Simply Better Reports\n\nThe owner's own entry point.\n\n"
                        "- **Daily brief** - Mine. `My add-ins/Daily brief - mine/ADD-IN.md`\n"
                        "- See [old page](Product/Help/old.md) and [updates](Product/Help/updates.md).\n"),
            "AGENTS.md": "Read Pace.md in this PACE folder.\n",
            "CLAUDE.md": "Read Pace.md in this PACE folder.\n",
            ".github/copilot-instructions.md": "Read Pace.md in this PACE folder.\n",
            "Record/2026-10-01 0900 Invented Bakery decision.md": "Invented decision: move the stocktake.\n",
            "Projects/Invented Bakery/Forecast/Documents/model.xlsx": b"PK\x03\x04invented workbook",
            "Repos/Invented Bakery/Forecast/forecast-repo.md": "Link: https://example.invalid/forecast\n",
            "My add-ins/Daily brief - mine/ADD-IN.md": "# Daily brief - mine\n\n**Customised from:** Daily brief\n",
        }
        for rel, data in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)

    def go_ahead(self, tag, commit):
        return f"Yes, go ahead and install Pace {tag} at commit {commit}."

    def apply(self, tag, commit, root=None, **options):
        if "go_ahead" not in options and "go_ahead_record" not in options and "confirmation_request" not in options and not options.get("central"):
            options["go_ahead"] = self.go_ahead(tag, commit)
        return pu.apply(root or self.root, str(self.repo.path), tag, commit, **options)

    def preview(self, tag, commit=None, root=None, **options):
        return pu.preview(root or self.root, str(self.repo.path), tag, commit, **options)

    def receipts(self, root=None) -> str:
        path = (root or self.root) / "Release record" / "Install receipts.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def records(self, root=None) -> list:
        folder = (root or self.root) / "Release record" / "Installs"
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


class UpdateCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-update-test-")
        self.lab = Lab(Path(self._temp.name))

    def tearDown(self):
        self._temp.cleanup()

    def assert_product_is(self, commit, root=None):
        installed = tree_bytes((root or self.lab.root) / "Product")
        expected = self.lab.repo.product(commit)
        self.assertEqual({k: v for k, v in installed.items() if v != "folder"}, expected)

    def assert_no_work_area(self, root=None):
        self.assertFalse(((root or self.lab.root) / "Release record" / "Update in progress").exists())


class PreviewTests(UpdateCase):
    def test_preview_shows_changes_and_writes_nothing(self):
        before = tree_bytes(self.lab.root)
        result = self.lab.preview("v3.2.0", self.lab.c2)
        self.assertEqual(tree_bytes(self.lab.root), before)
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["installed"])
        self.assertEqual(result["commit"], self.lab.c2)
        self.assertTrue(result["commit_pinned"])
        self.assertEqual(result["changes"]["added"], ["Pace add-ins/Open work/ADD-IN.md"])
        self.assertEqual(result["changes"]["changed"], ["Help/updates.md", "Pace add-ins/Daily brief/ADD-IN.md"])
        self.assertEqual(result["changes"]["removed"], ["Help/old.md"])
        self.assertEqual(result["shipped_addins"]["added"], ["Open work"])
        self.assertEqual(result["shipped_addins"]["changed"], ["Daily brief"])
        self.assertEqual(result["shipped_addins"]["unchanged"], ["Reminders"])
        self.assertEqual(result["owner_addins_never_updated"], ["Daily brief - mine"])
        self.assertEqual(result["pace_md_links_removed"], ["Product/Help/old.md"])
        self.assertIsNone(result["installed_now"]["tag"])
        self.assertIn(self.lab.c2, result["go_ahead_needed"])
        self.assertIn("Nothing has been installed", result["message"])
        text = pu.render(result)
        self.assertIn("Pace.md mentions Product files this release removes: Product/Help/old.md", text)
        self.assertIn("Your own add-ins stay as they are: Daily brief - mine", text)

    def test_preview_without_a_pin_reports_the_tag_commit_but_is_not_pinned(self):
        result = self.lab.preview("v3.2.0")
        self.assertEqual(result["status"], "not pinned")
        self.assertEqual(result["commit"], self.lab.c2)
        self.assertIn("give it with --commit", result["message"])

    def test_file_list_digest_matches_the_commit_bytes(self):
        files = self.lab.repo.product(self.lab.c2)
        entries = {path: (len(data), pu._sha256(data)) for path, data in files.items()}
        result = self.lab.preview("v3.2.0", self.lab.c2)
        self.assertEqual(result["product_file_list"]["digest"], pu.file_list_digest(entries))
        self.assertEqual(result["product_file_list"]["files"], len(files))


class ApplyTests(UpdateCase):
    def test_apply_replaces_only_product_reads_back_and_records(self):
        owner_before = owner_view(self.lab.root)
        result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assert_product_is(self.lab.c2)
        self.assertEqual(owner_view(self.lab.root), owner_before)
        self.assert_no_work_area()
        # The release's own PACE Pace.md, pointer and template copy were not installed.
        self.assertIn("The owner's own entry point", (self.lab.root / "Pace.md").read_text(encoding="utf-8"))
        self.assertFalse((self.lab.root / "Product/Pace.md").exists())
        self.assertIn("Whether OneDrive has received it is a separate check", result["message"])

        [record] = self.lab.records()
        self.assertEqual(record["result"], "installed")
        self.assertEqual(record["kind"], "local install")
        self.assertEqual(record["repository"], str(self.lab.repo.path))
        self.assertEqual(record["tag"], "v3.2.0")
        self.assertEqual(record["commit"], self.lab.c2)
        self.assertEqual(record["product_file_list"]["digest"], result["product_file_list"]["digest"])
        self.assertIsNone(record["prior"]["tag"])
        self.assertTrue(record["prior"]["product_file_list_digest"].startswith("sha256:"))
        self.assertTrue(record["outside_product"]["unchanged"])
        self.assertIn("Not checked", record["onedrive"])
        self.assertIn("Installed locally", record["claim"])
        go_ahead = json.loads((self.lab.root / "Release record" / record["owner_go_ahead"]).read_text(encoding="utf-8"))
        self.assertEqual(go_ahead["release"]["commit"], self.lab.c2)
        self.assertEqual(go_ahead["owner_words"], self.lab.go_ahead("v3.2.0", self.lab.c2))
        self.assertNotIn("signature", json.dumps(record).lower())

        receipts = self.lab.receipts()
        self.assertEqual(len([l for l in receipts.splitlines() if l.startswith("- ")]), 1)
        self.assertIn(f"Installed locally: Pace v3.2.0 (commit {self.lab.c2})", receipts)
        self.assertIn("Arrival in OneDrive is not checked", receipts)

    def test_second_update_appends_and_names_the_prior_version(self):
        self.lab.apply("v3.2.0", self.lab.c2)
        first = (self.lab.root / "Release record/Install receipts.md").read_bytes()
        result = self.lab.apply("v3.3.0", self.lab.c3)
        self.assertEqual(result["status"], "installed")
        self.assert_product_is(self.lab.c3)
        after = (self.lab.root / "Release record/Install receipts.md").read_bytes()
        self.assertTrue(after.startswith(first))
        self.assertIn(f"replacing Pace v3.2.0 (commit {self.lab.c2})", after.decode("utf-8"))
        latest = self.lab.records()[-1]
        self.assertEqual((latest["prior"]["tag"], latest["prior"]["commit"]), ("v3.2.0", self.lab.c2))
        self.assertTrue(latest["prior"]["matches_record"])
        self.assertEqual(latest["changes"]["changed"], ["Help/records.md"])

    def test_shipped_add_ins_update_and_owner_copies_never_do(self):
        mine = self.lab.root / "My add-ins/Daily brief - mine/ADD-IN.md"
        before = mine.read_bytes()
        self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual((self.lab.root / "Product/Pace add-ins/Daily brief/ADD-IN.md").read_text(encoding="utf-8"),
                         "# Daily brief\n\n**Purpose:** v2.\n")
        self.assertTrue((self.lab.root / "Product/Pace add-ins/Open work/ADD-IN.md").is_file())
        self.assertEqual(mine.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in mine.parent.iterdir()), ["ADD-IN.md"])

    def test_same_release_again_changes_nothing(self):
        self.lab.apply("v3.2.0", self.lab.c2)
        before = tree_bytes(self.lab.root)
        result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "already installed")
        self.assertEqual(tree_bytes(self.lab.root), before)

    def test_first_install_of_the_real_pace_folder_layout(self):
        repo = Repo(self.lab.base / "real")
        shutil.copytree(PACE_FOLDER, repo.path / "PACE")
        commit = repo.commit("Invented release of the current PACE")
        repo.tag("v3.9.0")
        folder = self.lab.base / "Fresh Pace"
        shutil.copytree(PACE_FOLDER, folder)
        owner_before = owner_view(folder)
        words = f"Install Pace v3.9.0 at commit {commit}, please."
        result = pu.apply(folder, str(repo.path), "v3.9.0", commit, go_ahead=words)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertEqual(owner_view(folder), owner_before)
        self.assertIn("Contracts", result["shipped_addins"]["unchanged"])
        again = pu.apply(folder, str(repo.path), "v3.9.0", commit, go_ahead=words)
        self.assertEqual(again["status"], "already installed")


class OwnerAddInPlaceTests(UpdateCase):
    """Owner add-ins in `My add-ins/`, or in an older folder's `Pace/Add-ins/My add-ins/`, are listed, kept and never moved."""

    NEW = "My add-ins"
    OLDER = "Pace/Add-ins/My add-ins"

    def add_board_notes(self, place, help_link):
        """An invented owner-made add-in with a file beside it and a nested file."""
        folder = self.lab.root / place / "Board notes"
        (folder / "Notes").mkdir(parents=True)
        (folder / "ADD-IN.md").write_text(
            f"# Board notes\n\n**Purpose:** Invented owner add-in.\n\nSave as [records]({help_link}records.md) says.\n",
            encoding="utf-8")
        (folder / "page-template.html").write_bytes(b"<!doctype html><p>Invented page</p>\n")
        (folder / "Notes/kept.txt").write_bytes(b"Invented nested owner file.\r\n")
        (self.lab.root / place / ".gitkeep").write_bytes(b"")

    def move_to_the_older_place(self):
        """Turn the lab's owner folder into one made before `My add-ins/` moved to the top."""
        older = self.lab.root / self.OLDER
        older.parent.mkdir(parents=True)
        shutil.move(str(self.lab.root / self.NEW), str(older))
        pace = self.lab.root / "Pace.md"
        pace.write_text(pace.read_text(encoding="utf-8").replace(f"`{self.NEW}/", f"`{self.OLDER}/"), encoding="utf-8")
        self.add_board_notes(self.OLDER, "../../../../Product/Help/")

    def test_add_ins_in_my_add_ins_are_byte_identical_after_updates(self):
        self.add_board_notes(self.NEW, "../../Product/Help/")
        before = tree_bytes(self.lab.root / self.NEW)
        pace_before = (self.lab.root / "Pace.md").read_bytes()
        preview = self.lab.preview("v3.2.0", self.lab.c2)
        self.assertEqual(preview["owner_addins_never_updated"], ["Board notes", "Daily brief - mine"])
        self.assertIn("My add-ins/", preview["protected"])
        for tag, commit in (("v3.2.0", self.lab.c2), ("v3.3.0", self.lab.c3)):
            result = self.lab.apply(tag, commit)
            self.assertEqual(result["status"], "installed", result.get("message"))
            self.assertEqual(tree_bytes(self.lab.root / self.NEW), before)
        self.assertEqual((self.lab.root / "Pace.md").read_bytes(), pace_before)
        self.assertFalse((self.lab.root / "Pace").exists())

    def test_add_ins_in_the_older_place_update_cleanly_stay_byte_identical_and_are_listed(self):
        self.move_to_the_older_place()
        before = tree_bytes(self.lab.root / self.OLDER)
        owner_before = owner_view(self.lab.root)
        older_names = [f"{self.OLDER}/Board notes", f"{self.OLDER}/Daily brief - mine"]

        preview = self.lab.preview("v3.2.0", self.lab.c2)
        self.assertEqual(preview["status"], "ready")
        self.assertEqual(preview["owner_addins_never_updated"], older_names)
        self.assertIn(f"{self.OLDER}/", preview["protected"])
        text = pu.render(preview)
        self.assertIn(f"Your own add-ins stay as they are: {older_names[0]}, {older_names[1]}", text)
        self.assertIn(f"{self.OLDER}/", text.split("Never changed by an update: ")[1].splitlines()[0])

        result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertEqual(result["owner_addins_never_updated"], older_names)
        self.assert_product_is(self.lab.c2)
        self.assertTrue(self.lab.records()[-1]["outside_product"]["unchanged"])
        self.assertEqual(tree_bytes(self.lab.root / self.OLDER), before)
        self.assertEqual(owner_view(self.lab.root), owner_before)
        # Nothing was moved or made in the new place, though the release's own PACE has a My add-ins folder.
        self.assertFalse((self.lab.root / self.NEW).exists())
        # The owner's index line still names a file that is there.
        index_path = re.search(r"`([^`]+/ADD-IN\.md)`", (self.lab.root / "Pace.md").read_text(encoding="utf-8"))[1]
        self.assertEqual(index_path, f"{self.OLDER}/Daily brief - mine/ADD-IN.md")
        self.assertTrue((self.lab.root / index_path).is_file())

    def test_a_folder_with_both_places_lists_both(self):
        self.add_board_notes(self.OLDER, "../../../../Product/Help/")
        result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertEqual(result["owner_addins_never_updated"], ["Daily brief - mine", f"{self.OLDER}/Board notes"])

    def test_a_change_in_the_older_place_during_an_update_rolls_back(self):
        self.move_to_the_older_place()
        old_product = tree_bytes(self.lab.root / "Product")
        mine = self.lab.root / self.OLDER / "Board notes/ADD-IN.md"

        def owner_edits(stage):
            if stage == "new-in-place":
                mine.write_text("Owner wrote this mid-update, a little longer.\n", encoding="utf-8")

        with mock.patch.object(pu, "_checkpoint", side_effect=owner_edits):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "rolled back")
        self.assertIn(f"{self.OLDER}/Board notes/ADD-IN.md", result["reason"])
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
        self.assertEqual(mine.read_text(encoding="utf-8"), "Owner wrote this mid-update, a little longer.\n")

    def test_help_names_both_places_and_how_to_move(self):
        [bullet] = [line for line in HELP.read_text(encoding="utf-8").splitlines() if line.startswith("- `My add-ins/`")]
        self.assertIn(f"`{self.OLDER}/` in an older folder", bullet)
        self.assertIn("An update never moves them", bullet)
        link = re.search(r"\]\((add-ins\.md)#([a-z-]+)\)", bullet)
        self.assertIsNotNone(link)
        add_ins = (HELP.parent / link[1]).read_text(encoding="utf-8")
        headings = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in re.findall(r"(?m)^## (.+)$", add_ins)}
        self.assertIn(link[2], headings)
        self.assertEqual(pu.OWNER_ADDINS, self.NEW)
        self.assertEqual(pu.OLDER_OWNER_ADDINS, self.OLDER)


class SourceTests(UpdateCase):
    def assert_stopped_untouched(self, call, phrase):
        before = tree_bytes(self.lab.root)
        with self.assertRaises(pu.Stop) as stop:
            call()
        self.assertIn(phrase, str(stop.exception))
        self.assertEqual(tree_bytes(self.lab.root), before)

    def test_moved_tag_stops(self):
        self.lab.repo.tag("v3.2.0", self.lab.c3, force=True)
        self.assert_stopped_untouched(lambda: self.lab.apply("v3.2.0", self.lab.c2), "has moved")
        self.assert_stopped_untouched(lambda: self.lab.preview("v3.2.0", self.lab.c2), "has moved")

    def test_missing_commit_stops(self):
        self.assert_stopped_untouched(lambda: self.lab.apply("v3.2.0", "1" * 40), "is not in")

    def test_never_from_a_branch_or_short_commit(self):
        self.assert_stopped_untouched(lambda: self.lab.apply("main", self.lab.c3), "has no tag named main")
        self.assert_stopped_untouched(lambda: self.lab.apply("v3.2.0", self.lab.c2[:12]), "full commit id")
        self.assert_stopped_untouched(lambda: self.lab.apply("v3.2.0", "main"), "full commit id")
        self.assert_stopped_untouched(lambda: self.lab.apply("v9.9.9", self.lab.c2), "has no tag named v9.9.9")

    def test_expected_file_list_mismatch_stops(self):
        self.assert_stopped_untouched(
            lambda: self.lab.apply("v3.2.0", self.lab.c2, expect_digest="sha256:" + "0" * 64),
            "does not match the expected file list")

    def test_fork_with_different_product_stops_and_mirror_with_same_product_is_recorded(self):
        fork = self.lab.base / "client-fork"
        subprocess.run(["git", "clone", "--quiet", str(self.lab.repo.path), str(fork)], check=True, env=clean_git_env())
        git(fork, "checkout", "--quiet", self.lab.c2)
        (fork / "PACE/Product/Help/updates.md").write_text("Client-changed help.\n", encoding="utf-8")
        git(fork, "commit", "--quiet", "-am", "Client change")
        fork_commit = git(fork, "rev-parse", "HEAD")
        git(fork, "tag", "client-v3.2.0")
        upstream = {"repo": str(self.lab.repo.path), "tag": "v3.2.0", "commit": self.lab.c2}
        before = tree_bytes(self.lab.root)
        with self.assertRaises(pu.Stop) as stop:
            pu.apply(self.lab.root, str(fork), "client-v3.2.0", fork_commit, upstream=upstream,
                     go_ahead=self.lab.go_ahead("client-v3.2.0", fork_commit))
        self.assertIn("differs from upstream v3.2.0", str(stop.exception))
        self.assertEqual(tree_bytes(self.lab.root), before)

        mirror = self.lab.base / "client-mirror"
        subprocess.run(["git", "clone", "--quiet", str(self.lab.repo.path), str(mirror)], check=True, env=clean_git_env())
        git(mirror, "checkout", "--quiet", self.lab.c2)
        (mirror / "README.md").write_text("Client mirror readme.\n", encoding="utf-8")
        git(mirror, "commit", "--quiet", "-am", "Client readme only")
        mirror_commit = git(mirror, "rev-parse", "HEAD")
        git(mirror, "tag", "client-v3.2.0")
        self.assertNotEqual(mirror_commit, self.lab.c2)
        result = pu.apply(self.lab.root, str(mirror), "client-v3.2.0", mirror_commit, upstream=upstream,
                          go_ahead=self.lab.go_ahead("client-v3.2.0", mirror_commit))
        self.assertEqual(result["status"], "installed")
        record = self.lab.records()[-1]
        self.assertEqual(record["commit"], mirror_commit)
        self.assertEqual(record["upstream"]["commit"], self.lab.c2)
        self.assertTrue(record["upstream"]["same_product_file_list"])

    def test_upstream_with_moved_tag_stops(self):
        self.lab.repo.tag("v3.2.0", self.lab.c3, force=True)
        upstream = {"repo": str(self.lab.repo.path), "tag": "v3.2.0", "commit": self.lab.c2}
        self.lab.repo.tag("client-v3.2.0", self.lab.c2)
        self.assert_stopped_untouched(
            lambda: self.lab.apply("client-v3.2.0", self.lab.c2, upstream=upstream), "has moved")

    def test_links_and_unsafe_names_in_a_release_stop(self):
        os.symlink("../Help/updates.md", self.lab.repo.path / "PACE/Product/Tools/link.md")
        commit = self.lab.repo.commit("Release with a link")
        self.lab.repo.tag("v3.4.0")
        self.assert_stopped_untouched(lambda: self.lab.apply("v3.4.0", commit), "is a link")
        for paths, phrase in ((["Help/a.md", "help/b.md"], "differ only by capitals"),
                              (["Help/con.md"], "Windows cannot hold"),
                              (["Help/a:b.md"], "unusable file name"),
                              (["../escape.md"], "unusable file name")):
            with self.subTest(paths=paths), self.assertRaises(pu.Stop) as stop:
                pu._check_paths(paths)
            self.assertIn(phrase, str(stop.exception))

    def test_repository_passwords_are_never_recorded(self):
        self.assertEqual(pu.redact("https://user:token123@example.invalid/pace.git"),
                         "https://example.invalid/pace.git")
        self.assertEqual(pu.redact("/srv/git/pace"), "/srv/git/pace")


class GoAheadTests(UpdateCase):
    def assert_refused(self, phrase, **options):
        before = tree_bytes(self.lab.root)
        with self.assertRaises(pu.Stop) as stop:
            self.lab.apply("v3.2.0", self.lab.c2, **options)
        self.assertIn(phrase, str(stop.exception))
        self.assertEqual(tree_bytes(self.lab.root), before)

    def test_local_install_needs_the_owners_go_ahead_naming_tag_and_commit(self):
        c2 = self.lab.c2
        self.assert_refused("needs the owner's go-ahead", go_ahead=None)
        self.assert_refused("must name the exact tag", go_ahead="Yes, install the update.")
        self.assert_refused("must name the exact tag", go_ahead="Install v3.2.0 please.")
        self.assert_refused("must name the exact tag", go_ahead=f"Install v3.2.0 at {c2[:12]}.")
        self.assert_refused("must name the exact tag", go_ahead=f"Install v3.3.0 at {c2}.")
        self.assertFalse(pu._names_release(f"install v3.2.0 at {c2}", "v3.2", c2))
        self.assertTrue(pu._names_release(f"Install Pace v3.2.0 at commit {c2.upper()}.", "v3.2.0", c2))

    def test_an_earlier_go_ahead_record_can_be_checked(self):
        with mock.patch.object(pu, "_checkpoint", side_effect=self.fail_at("new-in-place")):
            self.assertEqual(self.lab.apply("v3.2.0", self.lab.c2)["status"], "rolled back")
        [name] = [p.name for p in (self.lab.root / "Release record/Go-aheads").iterdir()]
        result = self.lab.apply("v3.2.0", self.lab.c2, go_ahead_record=f"Go-aheads/{name}")
        self.assertEqual(result["status"], "installed")
        self.assertEqual(self.lab.records()[-1]["owner_go_ahead"], f"Go-aheads/{name}")
        with self.assertRaises(pu.Stop):
            self.lab.apply("v3.3.0", self.lab.c3, go_ahead_record=f"Go-aheads/{name}")
        outside = self.lab.base / "go-ahead.json"
        shutil.copy(self.lab.root / "Release record/Go-aheads" / name, outside)
        with self.assertRaises(pu.Stop) as stop:
            self.lab.apply("v3.3.0", self.lab.c3, go_ahead_record=str(outside))
        self.assertIn("inside this folder's Release record", str(stop.exception))

    def test_central_copy_uses_it_change_control(self):
        central = self.lab.base / "Central Product"
        self.lab.make_folder(central, self.lab.c1, owner=False)
        with self.assertRaises(pu.Stop):
            self.lab.apply("v3.2.0", self.lab.c2, root=central, central=True)
        with self.assertRaises(pu.Stop):
            self.lab.apply("v3.2.0", self.lab.c2, central=True, it_change="CHG-0042")  # has a Pace.md
        result = self.lab.apply("v3.2.0", self.lab.c2, root=central, central=True, it_change="CHG-0042")
        self.assertEqual(result["status"], "installed")
        self.assert_product_is(self.lab.c2, root=central)
        record = self.lab.records(central)[-1]
        self.assertEqual((record["kind"], record["it_change"], record["owner_go_ahead"]),
                         ("central copy", "CHG-0042", None))
        self.assertIn("Installed in this central copy", self.lab.receipts(central))
        self.assertIn("under IT change CHG-0042", self.lab.receipts(central))

    @staticmethod
    def fail_at(stage):
        def hook(name):
            if name == stage:
                raise RuntimeError("Invented disk failure.")
        return hook


class ExactActUpdateTests(UpdateCase):
    def prepare_and_confirm(self):
        proposed = pu.prepare(self.lab.root, str(self.lab.repo.path), "v3.2.0", self.lab.c2)
        file = Path(proposed["act_file"])
        self.assertEqual(pu._sha256(file.read_bytes()), proposed["act_sha256"])
        self.assertIn(self.lab.c2, file.read_text(encoding="utf-8"))
        request = "20261023T120000Z--none--upd001"
        command = [sys.executable, str(PACE_FOLDER / "Product/Tools/pace_record.py"),
                   "--pace", str(self.lab.root), "confirm", "--request", request, "--project", "none",
                   "--subject", "Local Product update", "--act", "Install pinned Product locally",
                   "--act-file", str(file), "--shown-sha256", proposed["act_sha256"],
                   "--source", "Invented preview and before-and-after", "--by", "Example assistant",
                   "--owner-words", "Yes, install this exact invented proposal.", "--owner-current"]
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "confirmed")
        return request, file

    def test_recorded_exact_act_installs_and_receipt_links_confirmation(self):
        request, file = self.prepare_and_confirm()
        before = owner_view(self.lab.root)
        result = self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertEqual(owner_view(self.lab.root), before)
        self.assertEqual(self.lab.records()[-1]["confirmation"], f"Record/{request}.md")
        self.assertIsNone(self.lab.records()[-1]["owner_go_ahead"])
        self.assertIn(f"Record/{request}.md", self.lab.receipts())
        self.assertTrue(file.is_file())

    def test_changed_proposal_product_or_release_stops_without_install(self):
        request, file = self.prepare_and_confirm()
        before = tree_bytes(self.lab.root)
        with self.assertRaisesRegex(pu.Stop, "does not match this install"):
            self.lab.apply("v3.3.0", self.lab.c3, confirmation_request=request)
        self.assertEqual(tree_bytes(self.lab.root), before)
        file.write_bytes(file.read_bytes() + b" ")
        with self.assertRaisesRegex(pu.Stop, "not current"):
            self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request)
        file.write_bytes(file.read_bytes()[:-1])
        (self.lab.root / "Product/Help/records.md").write_text("Invented local change.\n", encoding="utf-8")
        with self.assertRaisesRegex(pu.Stop, "does not match this install"):
            self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request)

    def test_unreadable_or_superseded_record_is_not_a_go_ahead(self):
        request, _ = self.prepare_and_confirm()
        confirmation = self.lab.root / "Record" / f"{request}.md"
        original = confirmation.read_bytes()
        confirmation.write_bytes(b"not a readable record\n")
        with self.assertRaisesRegex(pu.Stop, "not a readable confirmation"):
            self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request)
        confirmation.write_bytes(original)
        correction = subprocess.run([
            sys.executable, str(PACE_FOLDER / "Product/Tools/pace_record.py"),
            "--pace", str(self.lab.root), "create",
            "--request", "20261023T120500Z--none--upd002", "--project", "none",
            "--kind", "withdrawal", "--subject", "Local Product update",
            "--from", "owner", "--words", "I withdraw this invented go-ahead.",
            "--by", "Example assistant", "--corrects", request,
            "--body", "The earlier confirmation no longer stands."
        ], capture_output=True, text=True)
        self.assertEqual(correction.returncode, 0, correction.stdout + correction.stderr)
        with self.assertRaisesRegex(pu.Stop, "not current"):
            self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request)

    def test_changed_proposal_after_staging_rolls_back(self):
        request, file = self.prepare_and_confirm()
        old = tree_bytes(self.lab.root / "Product")
        def change(stage):
            if stage == "staged":
                file.write_bytes(file.read_bytes() + b"changed")
        with mock.patch.object(pu, "_checkpoint", side_effect=change):
            result = self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request)
        self.assertEqual(result["status"], "rolled back")
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old)
        self.assertEqual(self.lab.records()[-1]["confirmation"], f"Record/{request}.md")

    def test_old_simple_go_ahead_and_central_change_route_remain_separate(self):
        request, _ = self.prepare_and_confirm()
        with self.assertRaisesRegex(pu.Stop, "one only"):
            self.lab.apply("v3.2.0", self.lab.c2, confirmation_request=request,
                           go_ahead=self.lab.go_ahead("v3.2.0", self.lab.c2))
        central = self.lab.base / "Central"
        self.lab.make_folder(central, self.lab.c1, owner=False)
        with self.assertRaisesRegex(pu.Stop, "central copy"):
            self.lab.apply("v3.2.0", self.lab.c2, root=central, central=True,
                           it_change="CHG-0001", confirmation_request=request)
        self.assertEqual(self.lab.apply("v3.2.0", self.lab.c2, root=central, central=True,
                                        it_change="CHG-0001")["status"], "installed")


class SafetyTests(UpdateCase):
    def hook(self, stage, action):
        def run(name):
            if name == stage:
                action()
        return mock.patch.object(pu, "_checkpoint", side_effect=run)

    def test_protected_path_change_during_update_rolls_back(self):
        old_product = tree_bytes(self.lab.root / "Product")
        record = self.lab.root / "Record/2026-10-23 1000 Invented note.md"
        with self.hook("new-in-place", lambda: record.write_text("Owner wrote this mid-update.\n", encoding="utf-8")):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "rolled back")
        self.assertIn("Record/2026-10-23 1000 Invented note.md", result["reason"])
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
        self.assertEqual(record.read_text(encoding="utf-8"), "Owner wrote this mid-update.\n")  # never rewritten
        self.assert_no_work_area()
        [entry] = self.lab.records()
        self.assertEqual(entry["result"], "rolled back")
        self.assertIn("Not installed: Pace v3.2.0", self.lab.receipts())
        self.assertIn("The previous Product was put back and read back.", self.lab.receipts())

    def test_changed_pace_md_or_pointer_bytes_are_caught(self):
        pointer = self.lab.root / "AGENTS.md"
        info = pointer.stat()

        def same_size_same_time():
            pointer.write_text("Read Pace.md in this PACE fo1der.\n", encoding="utf-8")
            os.utime(pointer, ns=(info.st_atime_ns, info.st_mtime_ns))

        with self.hook("new-in-place", same_size_same_time):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "rolled back")
        self.assertIn("AGENTS.md", result["reason"])

    def test_failure_after_swap_rolls_back(self):
        old_product = tree_bytes(self.lab.root / "Product")
        owner_before = owner_view(self.lab.root)
        with mock.patch.object(pu, "read_tree", side_effect=self.read_tree_failing_on_installed()):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "rolled back")
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
        self.assertEqual(owner_view(self.lab.root), owner_before)
        self.assert_no_work_area()

    def read_tree_failing_on_installed(self):
        """Make the read-back of the newly installed Product come out wrong."""
        real = pu.read_tree

        def fake(folder):
            found = real(folder)
            if Path(folder) == self.lab.root.resolve() / "Product" and (
                    self.lab.root / "Release record/Update in progress/previous/Product").exists():
                found = dict(found)
                found["Help/extra.md"] = (1, "0" * 64)  # a read-back that does not match
            return found
        return fake

    def test_ctrl_c_puts_the_old_product_back(self):
        old_product = tree_bytes(self.lab.root / "Product")

        def interrupt():
            raise KeyboardInterrupt

        with self.hook("old-moved", interrupt), self.assertRaises(KeyboardInterrupt):
            self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
        self.assert_no_work_area()
        self.assertIn("The update was cancelled.", self.lab.receipts())

    def test_failed_tidy_up_keeps_a_recorded_install(self):
        real = pu._remove_tree

        def locked(path):
            if Path(path).name in ("Update in progress", "previous"):  # the earlier Product's files are held open
                raise PermissionError("Invented file lock.")
            real(path)

        with mock.patch.object(pu, "_remove_tree", side_effect=locked):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed")
        self.assertIn("could not be removed", result["warning"])
        self.assert_product_is(self.lab.c2)
        self.assertIn("last install finished", self.lab.preview("v3.3.0", self.lab.c3)["message"])
        tidy = pu.recover(self.lab.root)
        self.assertTrue(tidy["installed"])
        self.assert_no_work_area()
        self.assertEqual([r["result"] for r in self.lab.records()], ["installed"])

    def held_open(self, name, stage, *, fail=False):
        """From checkpoint `stage` on, files called `name` cannot be deleted, as when a sync client or
        virus scanner holds them open. Folders list in name order, as on NTFS, so journal.json comes
        before previous/. With fail, the update also fails at that checkpoint."""
        real_unlink, real_scandir = os.unlink, os.scandir
        held = []

        def unlink(path, *args, **kwargs):
            if held and os.path.basename(os.fsdecode(path)) == name:
                raise PermissionError(13, "Invented file held open", os.fsdecode(path))
            return real_unlink(path, *args, **kwargs)

        def checkpoint(reached):
            if reached == stage:
                held.append(stage)
                if fail:
                    raise RuntimeError("Invented failure.")

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(pu, "_checkpoint", side_effect=checkpoint))
        stack.enter_context(mock.patch.object(os, "unlink", unlink))
        stack.enter_context(mock.patch.object(os, "scandir", lambda *a, **k: NameOrder(real_scandir(*a, **k))))
        return stack

    def apply_root_only(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pu.main(["apply", "--root", str(self.lab.root), "--json"])
        return code, json.loads(out.getvalue())

    def test_a_file_held_open_during_tidy_up_does_not_block_later_updates(self):
        with self.held_open("old.md", "noted"):  # Help/old.md is only in the previous Product
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed")
        self.assertIn("could not be removed", result["warning"])
        self.assert_product_is(self.lab.c2)
        self.assertIn("last install finished", self.lab.preview("v3.3.0", self.lab.c3)["message"])
        code, tidy = self.apply_root_only()
        self.assertEqual((code, tidy["status"], tidy["installed"]), (0, "recovered", True), tidy)
        self.assert_no_work_area()
        self.assertEqual(self.lab.preview("v3.3.0", self.lab.c3)["status"], "ready")
        self.assertEqual(self.lab.apply("v3.3.0", self.lab.c3)["status"], "installed")
        self.assertEqual([r["result"] for r in self.lab.records()], ["installed", "installed"])
        receipts = [line for line in self.lab.receipts().splitlines() if line.startswith("- ")]
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all("Installed locally" in line for line in receipts), receipts)

    def test_a_file_held_open_while_rolling_back_still_records_the_roll_back(self):
        old_product = tree_bytes(self.lab.root / "Product")
        with self.held_open("ADD-IN.md", "new-in-place", fail=True):  # in the new Product being set aside
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "rolled back")
        self.assertIn("could not be removed", result["warning"])
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
        self.assertEqual([r["result"] for r in self.lab.records()], ["rolled back"])
        self.assertEqual(self.lab.receipts().count("Not installed: Pace v3.2.0"), 1)
        self.assertIn("rolled back but left its work files", self.lab.preview("v3.2.0", self.lab.c2)["message"])
        code, tidy = self.apply_root_only()
        self.assertEqual((code, tidy["status"], tidy["installed"]), (0, "recovered", False), tidy)
        self.assert_no_work_area()
        self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
        self.assertEqual(len(self.lab.records()), 1)  # the roll-back is recorded once
        self.assertEqual(self.lab.receipts().count("Not installed"), 1)
        self.assertEqual(self.lab.apply("v3.2.0", self.lab.c2)["status"], "installed")

    def test_work_files_left_without_a_journal_are_tidied_only_when_product_is_as_recorded(self):
        # An older updater removed the journal first, then could not remove a file in previous/.
        self.lab.apply("v3.2.0", self.lab.c2)
        leftover = self.lab.root / "Release record/Update in progress/previous/Product/Help"
        leftover.mkdir(parents=True)
        (leftover / "old.md").write_text("# Old page\n", encoding="utf-8")
        self.assertIn("last install finished", self.lab.preview("v3.3.0", self.lab.c3)["message"])
        code, tidy = self.apply_root_only()
        self.assertEqual((code, tidy["status"], tidy["installed"]), (0, "recovered", True), tidy)
        self.assert_no_work_area()
        # When Product is not the recorded release, previous/ may hold the only copy of the old one.
        leftover.mkdir(parents=True)
        (leftover / "old.md").write_text("# Old page\n", encoding="utf-8")
        (self.lab.root / "Product/Help/updates.md").write_text("Owner edited shipped help.\n", encoding="utf-8")
        with self.assertRaises(pu.NeedsHelp):
            pu.recover(self.lab.root)
        self.assertTrue((leftover / "old.md").is_file())

    def test_a_brief_lock_on_the_journal_is_retried(self):
        real = os.replace
        held = []

        def held_once(source, target, *args, **kwargs):
            if (Path(target).name == "journal.json" and not held
                    and b'"phase": "recorded"' in Path(source).read_bytes()):
                held.append(target)
                raise PermissionError(13, "Invented sync lock", str(target))
            return real(source, target, *args, **kwargs)

        with mock.patch.object(pu.os, "replace", held_once), mock.patch.object(pu.time, "sleep"):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertTrue(held)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assert_product_is(self.lab.c2)
        self.assert_no_work_area()
        self.assertEqual([r["result"] for r in self.lab.records()], ["installed"])
        self.assertNotIn("Not installed", self.lab.receipts())

    def test_local_changes_inside_product_need_an_explicit_choice(self):
        self.lab.apply("v3.2.0", self.lab.c2)
        edited = self.lab.root / "Product/Help/updates.md"
        edited.write_text("Owner edited shipped help in place.\n", encoding="utf-8")
        preview = self.lab.preview("v3.3.0", self.lab.c3)
        self.assertEqual(preview["changed_since_record"]["changed"], ["Help/updates.md"])
        self.assertFalse(preview["installed_now"]["matches_record"])
        with self.assertRaises(pu.Stop) as stop:
            self.lab.apply("v3.3.0", self.lab.c3)
        self.assertIn("Help/updates.md", str(stop.exception))
        result = self.lab.apply("v3.3.0", self.lab.c3, replace_changed_product=True)
        self.assertEqual(result["status"], "installed")
        self.assert_product_is(self.lab.c3)

    def write_note_without_file_list(self, tag, commit):
        (self.lab.root / "Release record/Installed release.md").write_text(
            pu.NOTE_HEADER + "\n## 2026-10-01 09:00:00 UTC - Written by hand\n\n"
            f"- Release repository: {self.lab.repo.path}\n- Installed release: {tag}\n- Full commit: {commit}\n",
            encoding="utf-8")

    def test_a_note_without_a_file_list_cannot_vouch_for_product(self):
        self.write_note_without_file_list("v3.1.0", self.lab.c1)
        (self.lab.root / "Product/Help/updates.md").write_text("Owner edited shipped help in place.\n", encoding="utf-8")
        preview = self.lab.preview("v3.2.0", self.lab.c2)
        self.assertIsNone(preview["installed_now"]["matches_record"])
        self.assertTrue(preview["changed_since_record"]["not_checked"])
        text = pu.render(preview)
        self.assertNotIn("still match", text)
        self.assertIn("cannot be checked", text)
        before = tree_bytes(self.lab.root)
        with self.assertRaises(pu.Stop) as stop:
            self.lab.apply("v3.2.0", self.lab.c2)
        self.assertIn("cannot be checked", str(stop.exception))
        self.assertIn("--replace-changed-product", str(stop.exception))
        self.assertEqual(tree_bytes(self.lab.root), before)
        result = self.lab.apply("v3.2.0", self.lab.c2, replace_changed_product=True)
        self.assertEqual(result["status"], "installed")
        self.assertIsNone(self.lab.records()[-1]["prior"]["matches_record"])

    def test_a_note_without_a_file_list_is_no_obstacle_when_product_already_matches(self):
        self.write_note_without_file_list("v3.1.0", self.lab.c1)
        shutil.rmtree(self.lab.root / "Product")
        self.lab.make_folder(self.lab.root, self.lab.c2, owner=False)  # Product already holds v3.2.0's files
        result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assert_product_is(self.lab.c2)


class UnreadableFolderTests(UpdateCase):
    """A folder the updater is not allowed to read, as the Claude desktop app's own folder is from its Linux sandbox."""

    LOCKED = ("Claude/Claude Tasks and Artifacts/Artifacts", "Claude/Claude Tasks and Artifacts/Scheduled")
    BESIDE = "Claude/Claude Tasks and Artifacts/Projects/XYZ"

    def setUp(self):
        super().setUp()
        for rel in self.LOCKED:
            (self.lab.root / rel).mkdir(parents=True)
            (self.lab.root / rel / "task.json").write_text("{}\n", encoding="utf-8")
        (self.lab.root / self.BESIDE).mkdir(parents=True)

    def locked(self, *rels, listing_only=False):
        """These paths and everything below them raise PermissionError, as the sandbox does: on looking at
        them (lstat, stat) and on listing them. With listing_only, they can be looked at but not listed."""
        prefixes = [os.path.abspath(self.lab.root / rel) for rel in rels]

        def deny(path):
            if isinstance(path, int):  # a folder opened by descriptor, as shutil.rmtree does when tidying up
                return
            text = os.path.abspath(os.fsdecode(path))
            if any(text == prefix or text.startswith(prefix + os.sep) for prefix in prefixes):
                raise PermissionError(errno.EACCES, "Permission denied", text)

        real_is_symlink, real_stat, real_scandir = Path.is_symlink, Path.stat, os.scandir

        def is_symlink(path):
            deny(path)
            return real_is_symlink(path)

        def stat(path, *args, **kwargs):
            deny(path)
            return real_stat(path, *args, **kwargs)

        def scandir(path=".", *args, **kwargs):
            deny(path)
            return real_scandir(path, *args, **kwargs)

        stack = contextlib.ExitStack()
        if not listing_only:
            stack.enter_context(mock.patch.object(Path, "is_symlink", is_symlink))
            stack.enter_context(mock.patch.object(Path, "stat", stat))
        stack.enter_context(mock.patch.object(os, "scandir", scandir))
        return stack

    def test_a_folder_it_may_not_read_is_named_and_not_walked_into(self):
        with self.locked(*self.LOCKED):
            view = pu.snapshot_outside_product(self.lab.root)
        for rel in self.LOCKED:
            self.assertEqual(view[rel], pu.UNREADABLE)
            self.assertEqual([path for path in view if path.startswith(rel + "/")], [])
        self.assertEqual(view[self.BESIDE], ("folder",))
        self.assertEqual(view["Pace.md"][0], "file")  # everything else is still looked at
        self.assertEqual(pu.not_checked(view), sorted(self.LOCKED))

    def test_a_folder_it_may_look_at_but_not_list_is_named_too(self):
        with self.locked(*self.LOCKED, listing_only=True):
            view = pu.snapshot_outside_product(self.lab.root)
        self.assertEqual(pu.not_checked(view), sorted(self.LOCKED))
        self.assertEqual([path for path in view if path.startswith(self.LOCKED[0] + "/")], [])

    def test_an_unreadable_file_is_named(self):
        rel = "Record/2026-10-01 0900 Invented Bakery decision.md"
        with self.locked(rel):
            view = pu.snapshot_outside_product(self.lab.root)
        self.assertEqual(pu.not_checked(view), [rel])

    def test_a_pace_folder_it_may_not_list_still_stops(self):
        with self.locked("."), self.assertRaises(PermissionError):
            pu.snapshot_outside_product(self.lab.root)

    def test_the_update_installs_and_names_what_was_not_checked(self):
        owner_before = owner_view(self.lab.root)
        with self.locked(*self.LOCKED):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assert_product_is(self.lab.c2)
        self.assertEqual(owner_view(self.lab.root), owner_before)
        self.assertEqual(result["not_checked"], sorted(self.LOCKED))
        self.assertIn("Not checked, because the updater may not read them: Claude/Claude Tasks and Artifacts/Artifacts, "
                      "Claude/Claude Tasks and Artifacts/Scheduled.", result["message"])
        outside = self.lab.records()[-1]["outside_product"]
        self.assertTrue(outside["unchanged"])
        self.assertEqual(outside["not_checked"], sorted(self.LOCKED))
        self.assertIn("never writes there", outside["why_not_checked"])

    def test_with_nothing_unreadable_nothing_is_named(self):
        result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertNotIn("not_checked", result)
        self.assertNotIn("Not checked, because", result["message"])
        self.assertNotIn("not_checked", self.lab.records()[-1]["outside_product"])

    def test_a_change_beside_an_unreadable_folder_is_still_caught(self):
        beside = self.lab.root / self.BESIDE / "task.json"

        def write_beside(stage):
            if stage == "new-in-place":
                beside.write_text("{}\n", encoding="utf-8")

        with self.locked(*self.LOCKED), mock.patch.object(pu, "_checkpoint", side_effect=write_beside):
            result = self.lab.apply("v3.2.0", self.lab.c2)
        self.assertEqual(result["status"], "rolled back")
        self.assertIn(f"{self.BESIDE}/task.json", result["reason"])

    def test_the_command_line_installs_instead_of_stopping_on_a_file_error(self):
        out = io.StringIO()
        with self.locked(*self.LOCKED), contextlib.redirect_stdout(out):
            code = pu.main(["apply", "--root", str(self.lab.root), "--repo", str(self.lab.repo.path), "--tag", "v3.2.0",
                            "--commit", self.lab.c2, "--go-ahead", self.lab.go_ahead("v3.2.0", self.lab.c2)])
        text = out.getvalue()
        self.assertEqual(code, 0, text)
        self.assertNotIn("file error", text)
        self.assertIn("Not checked, because the updater may not read them", text)
        self.assert_product_is(self.lab.c2)


class CreateOnlyFolderTests(UpdateCase):
    """Some linked assistant sessions can create files in the Pace folder but not rename or delete them."""

    @contextlib.contextmanager
    def create_only(self, *, after_fetch=True):
        """Refuse every rename and delete, from the start or once the release has been fetched."""
        real_fetch = pu.fetch_release
        refusing = [] if after_fetch else [True]

        def fetch(*args, **kwargs):
            release = real_fetch(*args, **kwargs)
            refusing.append(True)
            return release

        def refuse(real):
            def call(*args, **kwargs):
                if refusing:
                    raise PermissionError(errno.EPERM, "Operation not permitted", os.fsdecode(args[0]))
                return real(*args, **kwargs)
            return call

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pu, "fetch_release", side_effect=fetch))
            stack.enter_context(mock.patch.object(pu.time, "sleep"))
            for name in ("replace", "rename", "unlink", "remove", "rmdir"):
                stack.enter_context(mock.patch.object(os, name, refuse(getattr(os, name))))
            yield

    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pu.main([*args, "--root", str(self.lab.root), "--json"])
        return code, json.loads(out.getvalue())

    def full(self, tag, commit):
        return ["--repo", str(self.lab.repo.path), "--tag", tag, "--commit", commit]

    def apply_cli(self, tag, commit):
        return self.main("apply", *self.full(tag, commit), "--go-ahead", self.lab.go_ahead(tag, commit))

    def test_apply_stops_before_writing_and_a_later_run_is_not_blocked(self):
        before = tree_bytes(self.lab.root)
        with self.create_only():
            code, result = self.apply_cli("v3.2.0", self.lab.c2)
        self.assertEqual((code, result["status"]), (1, "stopped"), result)
        self.assertIn("computer that can replace files", result["message"])
        after = tree_bytes(self.lab.root)
        added = sorted(set(after) - set(before))
        # Only the check file stays: it explains itself and the result names it.
        self.assertEqual(len(added), 1, added)
        self.assertEqual({k: v for k, v in after.items() if k not in added}, before)
        self.assertTrue(added[0].startswith("Release record/.pace-update-check-"), added)
        self.assertEqual(result["kept_check_files"], added)
        self.assertIn("harmless", after[added[0]].decode("utf-8"))
        self.assertIn("Nothing else in the Pace folder was changed", result["message"])

        with self.create_only():  # trying again there adds nothing
            again = self.apply_cli("v3.2.0", self.lab.c2)[1]
        with self.create_only():
            self.assertEqual(self.main("preview", *self.full("v3.2.0", self.lab.c2))[1]["status"], "ready")
        self.assertEqual(again["status"], "stopped")
        self.assertIn("computer that can replace files", again["message"])
        self.assertEqual(tree_bytes(self.lab.root), after)

        code, installed = self.apply_cli("v3.2.0", self.lab.c2)  # on a computer that can replace files
        self.assertEqual((code, installed["status"]), (0, "installed"), installed)
        self.assertFalse(list((self.lab.root / "Release record").glob(".pace-update-check-*")))
        self.assertEqual([r["result"] for r in self.lab.records()], ["installed"])

    def test_files_an_earlier_attempt_left_there_do_not_block(self):
        # What an earlier updater left after its first journal write was refused.
        work = self.lab.root / "Release record/Update in progress"
        work.mkdir(parents=True)
        (work / "journal.json.tmp").write_text(json.dumps({"format": pu.JOURNAL_FORMAT, "phase": "staging"}),
                                               encoding="utf-8")
        with self.create_only():
            code, preview = self.main("preview", *self.full("v3.2.0", self.lab.c2))
            self.assertEqual((code, preview["status"]), (0, "ready"), preview)
            self.assertIn("Product was not touched", preview["warning"])
        with self.create_only():
            self.assertEqual(self.main("prepare", *self.full("v3.2.0", self.lab.c2))[1]["status"], "proposed")
        with self.create_only(after_fetch=False):
            code, recover = self.main("apply")
        self.assertEqual((code, recover["status"]), (1, "stopped"), recover)
        self.assertIn("computer that can replace files", recover["message"])
        self.assertTrue((work / "journal.json.tmp").is_file())

        code, recover = self.main("apply")  # on a computer that can replace files
        self.assertEqual((code, recover["status"]), (0, "recovered"), recover)
        self.assert_no_work_area()
        self.assertFalse(list((self.lab.root / "Release record").glob(".pace-update-check-*")))
        self.assertEqual(self.apply_cli("v3.2.0", self.lab.c2)[1]["status"], "installed")


DRIVER = textwrap.dedent("""
    import importlib.util, os, sys
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("pace_update", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stage = sys.argv[2]
    def crash(name):
        if name == stage:
            os._exit(137)  # a hard stop: no clean-up code runs
    mod._checkpoint = crash
    sys.exit(mod.main(sys.argv[3:]))
""")


class InterruptedInstallTests(UpdateCase):
    def run_cli(self, *args, crash_at="never"):
        return subprocess.run([sys.executable, "-c", DRIVER, str(TOOL), crash_at, *args],
                              capture_output=True, text=True, env=clean_git_env())

    def apply_args(self, tag, commit):
        return ["apply", "--root", str(self.lab.root), "--repo", str(self.lab.repo.path), "--tag", tag,
                "--commit", commit, "--go-ahead", self.lab.go_ahead(tag, commit)]

    def test_hard_stop_mid_install_is_rolled_back_on_the_next_apply(self):
        for stage in ("staged", "old-moved", "new-in-place", "read-back", "record-written"):
            with self.subTest(stage=stage):
                self.lab = Lab(Path(self._temp.name) / stage)
                old_product = tree_bytes(self.lab.root / "Product")
                owner_before = owner_view(self.lab.root)
                crashed = self.run_cli(*self.apply_args("v3.2.0", self.lab.c2), crash_at=stage)
                self.assertEqual(crashed.returncode, 137)
                self.assertTrue((self.lab.root / "Release record/Update in progress/journal.json").is_file())
                self.assertEqual(self.lab.preview("v3.2.0", self.lab.c2)["status"], "interrupted")

                recovered = self.run_cli("apply", "--root", str(self.lab.root), "--json")
                self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
                self.assertEqual(json.loads(recovered.stdout)["status"], "recovered")
                self.assertEqual(tree_bytes(self.lab.root / "Product"), old_product)
                self.assertEqual(owner_view(self.lab.root), owner_before)
                self.assert_no_work_area()
                self.assertIn("An earlier update was interrupted and has been rolled back.", self.lab.receipts())
                self.assertIsNone(pu.last_install(self.lab.root.resolve()))
                if stage == "record-written":
                    # The earlier record is corrected by a new one, never edited.
                    first, second = self.lab.records()
                    self.assertEqual((first["result"], second["result"]), ("installed", "rolled back"))
                    names = sorted(p.name for p in (self.lab.root / "Release record/Installs").glob("*.json"))
                    self.assertEqual(second["corrects"], names[0])

                again = self.run_cli(*self.apply_args("v3.2.0", self.lab.c2))
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assert_product_is(self.lab.c2)
                self.assertEqual(pu.last_install(self.lab.root.resolve())["commit"], self.lab.c2)

    def test_hard_stop_after_recording_keeps_the_install(self):
        crashed = self.run_cli(*self.apply_args("v3.2.0", self.lab.c2), crash_at="recorded")
        self.assertEqual(crashed.returncode, 137)
        recovered = self.run_cli("apply", "--root", str(self.lab.root), "--json")
        self.assertEqual(json.loads(recovered.stdout)["installed"], True)
        self.assert_product_is(self.lab.c2)
        self.assert_no_work_area()
        self.assertEqual([r["result"] for r in self.lab.records()], ["installed"])


class CommandLineTests(UpdateCase):
    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pu.main(list(args))
        return code, out.getvalue()

    def test_preview_and_stop_messages(self):
        base = ["--root", str(self.lab.root), "--repo", str(self.lab.repo.path)]
        code, text = self.main("preview", *base, "--tag", "v3.2.0", "--commit", self.lab.c2)
        self.assertEqual(code, 0)
        self.assertIn("This is a preview. Nothing has been installed or recorded.", text)
        self.assertIn("Never changed by an update: Record/", text)
        self.assertIn("and your own lines in Pace.md.", text)
        self.lab.repo.tag("v3.2.0", self.lab.c3, force=True)
        code, text = self.main("apply", *base, "--tag", "v3.2.0", "--commit", self.lab.c2,
                               "--go-ahead", self.lab.go_ahead("v3.2.0", self.lab.c2))
        self.assertEqual(code, 1)
        self.assertIn("has moved", text)
        self.assertIn("Nothing in the Pace folder was changed.", text)
        code, text = self.main("apply", "--root", str(self.lab.root))
        self.assertEqual(code, 1)
        self.assertIn("Nothing to recover", text)
        code, text = self.main("preview", *base, "--tag", "v3.3.0", "--upstream-repo", "x")
        self.assertEqual(code, 1)
        self.assertIn("give all three", text)

    def test_latest_install_line_keeps_a_repository_with_spaces_whole(self):
        spaced = self.lab.base / "OneDrive - Invented Co" / "pace releases"
        spaced.parent.mkdir(parents=True)
        os.rename(self.lab.repo.path, spaced)
        code, text = self.main("preview", "--root", str(self.lab.root), "--repo", str(spaced), "--latest")
        self.assertEqual(code, 0, text)
        [line] = [l for l in text.splitlines() if "use exactly" in l]
        pasted = line.split("use exactly ", 1)[1][:-1]  # without the closing full stop
        self.assertEqual(shlex.split(pasted), ["--repo", str(spaced), "--tag", "v3.3.0", "--commit", self.lab.c3])

    def test_shell_words_are_quoted_for_windows_and_posix(self):
        folder = r"C:\Users\Invented\OneDrive - Invented Co\pace releases"
        self.assertEqual(pu._shell_word(folder, windows=True), f'"{folder}"')
        self.assertEqual(pu._shell_word(folder + "\\", windows=True), f'"{folder}\\\\"')
        self.assertEqual(pu._shell_word("/srv/OneDrive - Invented Co/pace", windows=False),
                         "'/srv/OneDrive - Invented Co/pace'")
        for plain in ("https://example.invalid/pace.git", "git@example.invalid:team/pace.git", "v3.3.0"):
            self.assertEqual(pu._shell_word(plain, windows=True), plain)
            self.assertEqual(pu._shell_word(plain, windows=False), plain)

    def test_refuses_to_run_from_inside_product(self):
        here = os.getcwd()
        try:
            os.chdir(self.lab.root / "Product")
            code, text = self.main("preview", "--root", str(self.lab.root), "--repo", str(self.lab.repo.path),
                                   "--tag", "v3.2.0")
        finally:
            os.chdir(here)
        self.assertEqual(code, 1)
        self.assertIn("outside the Product folder", text)


class HelpTests(unittest.TestCase):
    def test_help_explains_copilot_cloud_claims_and_no_signing(self):
        text = HELP.read_text(encoding="utf-8")
        self.assertNotIn("not built yet", text)
        self.assertIn("Copilot", text)
        self.assertIn("cannot replace", text)
        self.assertIn("can only suggest", text)
        self.assertIn("installed locally", text.lower())
        self.assertIn("arrived in onedrive", text.lower())
        self.assertIn("go-ahead", text)
        self.assertNotIn("—", text)
        pace = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        self.assertIn("[Product updates](Product/Help/updates.md)", pace)
        self.assertNotIn("step 5 placeholder", pace)

    def test_help_on_edited_product_files_matches_what_a_fresh_copy_can_say(self):
        with tempfile.TemporaryDirectory(prefix="pace-update-test-") as temporary:
            lab = Lab(Path(temporary))
            # A folder made by get-pace.py holds only the release note's fingerprint until its first install.
            pu.note_first_copy(lab.root, str(lab.repo.path), "v3.1.0", lab.c1)
            (lab.root / "Product/Help/updates.md").write_text("Owner edited shipped help in place.\n", encoding="utf-8")
            with self.assertRaises(pu.Stop) as stop:
                lab.apply("v3.2.0", lab.c2)
        self.assertNotIn("Help/updates.md", str(stop.exception))
        [bullet] = [line for line in HELP.read_text(encoding="utf-8").splitlines()
                    if line.startswith("- **Files inside Product were edited")]
        self.assertIn("lists them", bullet)
        self.assertIn("get-pace.py", bullet)
        self.assertIn("not which", bullet)

    def test_updater_has_no_signing_keys_or_publisher(self):
        code = TOOL.read_text(encoding="utf-8").lower()
        for word in ("gpg", "verify-tag", "verify-commit", "ed25519", "private key", "publisher_", "import ssl"):
            self.assertNotIn(word, code)
        self.assertNotIn("import ", "\n".join(l for l in code.splitlines() if "cryptography" in l))


if __name__ == "__main__":
    unittest.main()
