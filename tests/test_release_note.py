"""The release note in Release record/: written by get-pace.py, read by `preview --latest`, kept by updates.

Invented local git repositories and temporary folders only.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_updates import GIT_ENV, PACE_FOLDER, Repo, clean_git_env, git, owner_view, pu, tree_bytes

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("get_pace_for_note", ROOT / "get-pace.py")
get = importlib.util.module_from_spec(spec)
spec.loader.exec_module(get)

NOTE = Path("Release record/Installed release.md")
OWNER_FILES = {
    "Record/20261023T090000Z--invented-bakery--job001.md": "Invented record.\n",
    "1 Projects/Invented Bakery/Forecast/Pace project.md": "Project id: invented-forecast\n",
    "Repos/Invented Bakery/Forecast/forecast-code/Pace repo.md": "Link: https://example.invalid/forecast\n",
    "3 My add-ins/Daily brief - mine/ADD-IN.md": "# Daily brief - mine\n",
}


def release(repo: Repo, tag: str, help_text: str, extra: dict | None = None) -> str:
    """Commit and tag an invented release with the PACE layout."""
    repo.write("PACE/Pace.md", "# Invented Pace\n")
    repo.write("PACE/AGENTS.md", "Read Pace.md in this PACE folder.\n")
    repo.write("PACE/Record/.gitkeep", "")
    repo.write("PACE/Release record/.gitkeep", "")
    repo.write("PACE/Product/Help/updates.md", help_text)
    repo.write("PACE/Product/Tools/pace_update.py", "# invented updater placeholder\n")
    for rel, text in (extra or {}).items():
        repo.write(rel, text)
    commit = repo.commit(f"Invented release {tag}")
    repo.tag(tag)
    return commit


class NoteCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-note-test-")
        self.env = mock.patch.dict("os.environ", GIT_ENV)
        self.env.start()
        self.base = Path(self._temp.name)
        self.repo = Repo(self.base / "releases")
        self.c37 = release(self.repo, "v3.7.0", "Invented help 3.7.0\n")
        git(self.repo.path, "commit", "--quiet", "--allow-empty", "-m", "Unreleased work")

    def tearDown(self):
        self.env.stop()
        self._temp.cleanup()

    def new_folder(self, repo=None, name="place") -> Path:
        place = self.base / name
        place.mkdir()
        get.get_pace(place, str(repo or self.repo.path))
        folder = place / "PACE"
        for rel, text in OWNER_FILES.items():
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_text(text, encoding="utf-8")
        return folder

    def main(self, *args, cwd=None):
        out, here = io.StringIO(), os.getcwd()
        try:
            if cwd:
                os.chdir(cwd)
            with contextlib.redirect_stdout(out):
                code = pu.main(list(args))
        finally:
            os.chdir(here)
        return code, out.getvalue()

    def check(self, folder, *extra):
        """`preview --root . --latest` from inside the PACE folder, as the help tells an assistant."""
        return self.main("preview", "--root", ".", "--latest", *extra, cwd=folder)

    def note(self, folder) -> dict:
        return pu.read_release_note(folder.resolve())

    def go_ahead(self, tag, commit):
        return f"Yes, install Pace {tag} at commit {commit}."


class GetPaceWritesTheNote(NoteCase):
    def test_note_written_by_get_pace_names_repository_release_and_time(self):
        out = io.StringIO()
        place = self.base / "place"
        place.mkdir()
        with contextlib.redirect_stdout(out):
            self.assertEqual(get.main(["--to", str(place), "--repo", str(self.repo.path)]), 0)
        folder = place / "PACE"
        self.assertIn("Release record/Installed release.md", out.getvalue())
        self.assertIn("preview --root . --latest", out.getvalue())
        # Everything else is exactly the release's PACE folder.
        copied = tree_bytes(folder)
        text = copied.pop(NOTE.as_posix()).decode("utf-8")
        self.assertEqual(copied, tree_bytes(self.repo.path / "PACE"))
        self.assertIn("Format: pace-release-note/1", text)
        self.assertIn("so the last entry is the release\ninstalled now", text)
        self.assertNotIn("—", text)
        note = self.note(folder)
        self.assertEqual((note["state"], note["entries"]), ("readable", 1))
        entry = note["entry"]
        self.assertEqual(entry["event"], "Copied with get-pace.py")
        self.assertEqual(entry["repository"], str(self.repo.path.resolve()))
        self.assertEqual((entry["tag"], entry["commit"]), ("v3.7.0", self.c37))
        self.assertEqual(entry["digest"], pu.file_list_digest(pu.read_tree(folder / "Product")))
        self.assertRegex(entry["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn(f"- Full commit: {self.c37}\n", text)

    def test_note_holds_no_credentials_and_a_full_folder_path(self):
        self.assertEqual(pu.note_repository("https://someone:token123@example.invalid/pace.git"),
                         "https://example.invalid/pace.git")
        self.assertEqual(pu.note_repository("https://token123@example.invalid/pace.git"),
                         "https://example.invalid/pace.git")
        self.assertEqual(pu.note_repository("ssh://git@example.invalid/pace.git"), "ssh://git@example.invalid/pace.git")
        self.assertEqual(pu.note_repository("ssh://git:secret@example.invalid/pace.git"), "ssh://example.invalid/pace.git")
        self.assertEqual(pu.note_repository("git@example.invalid:sbr/pace.git"), "git@example.invalid:sbr/pace.git")
        place = self.base / "place"
        place.mkdir()
        here = os.getcwd()
        try:
            os.chdir(self.base)
            get.get_pace(place, "releases")  # a folder given relative to where it was run
        finally:
            os.chdir(here)
        self.assertEqual(self.note(place / "PACE")["entry"]["repository"], str(self.repo.path.resolve()))

    def test_a_failed_note_leaves_no_copy(self):
        place = self.base / "place"
        place.mkdir()
        with mock.patch.object(get.update, "note_first_copy", side_effect=OSError("Invented disk error")):
            with self.assertRaises(OSError):
                get.get_pace(place, str(self.repo.path))
        self.assertEqual(list(place.iterdir()), [])


class CheckForAnUpdate(NoteCase):
    def test_preview_latest_with_no_repository_argument_reads_the_note(self):
        folder = self.new_folder()
        before = tree_bytes(folder)
        code, text = self.check(folder)
        self.assertEqual(code, 0, text)
        self.assertIn(f"Release source: {self.repo.path.resolve()}, read from Release record/Installed release.md.", text)
        self.assertIn("already installed here. It is the newest release", text)
        self.assertIn("nothing to update", text)

        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n")
        code, text = self.check(folder)
        self.assertEqual(code, 0, text)
        self.assertIn(f"Installed now: Pace v3.7.0 (commit {self.c37}), recorded in Release record/Installed release.md; "
                      "the installed files still match that record.", text)
        self.assertIn("Update available: Pace v3.8.0 is newer than the installed v3.7.0.", text)
        self.assertIn(f"use exactly --repo {self.repo.path.resolve()} --tag v3.8.0 --commit {c38}", text)
        self.assertIn("This is a preview. Nothing has been installed or recorded.", text)
        self.assertEqual(tree_bytes(folder), before)  # a check writes nothing

        code, text = self.check(folder, "--json")
        result = json.loads(text)
        self.assertEqual((result["status"], result["compared_with_installed"]), ("ready", "newer"))
        self.assertEqual(result["release_source"], {"repository": str(self.repo.path.resolve())})
        self.assertEqual(result["installed_now"]["record"], "Installed release.md")

    def test_explicit_repository_overrides_the_note(self):
        folder = self.new_folder()
        other = Repo(self.base / "other releases")
        release(other, "v3.6.0", "Invented older help\n")
        code, text = self.check(folder, "--repo", str(other.path))
        self.assertEqual(code, 0, text)
        self.assertNotIn("Release source:", text)
        self.assertIn(f"Release: Pace v3.6.0 from {other.path}", text)
        self.assertIn("is older than the installed v3.7.0. Do not install it unless the owner wants to go back.", text)
        newer = release(other, "v4.0.0", "Invented newer help\n")
        code, text = self.check(folder, "--repo", str(other.path))
        self.assertIn(f"--tag v4.0.0 --commit {newer}", text)
        self.assertEqual(self.note(folder)["entry"]["repository"], str(self.repo.path.resolve()))


class MissingNote(NoteCase):
    def folder_without_note(self) -> Path:
        """A folder made before the note existed: the release's files only."""
        folder = self.base / "Older PACE"
        shutil.copytree(self.repo.path / "PACE", folder)  # main holds v3.7.0's files
        return folder

    def test_missing_note_says_so_and_asks_for_the_repository(self):
        folder = self.folder_without_note()
        before = tree_bytes(folder)
        with mock.patch.object(pu, "latest_release", side_effect=AssertionError("contacted a repository")):
            code, text = self.check(folder)
        self.assertEqual(code, 1, text)
        self.assertIn("This PACE folder has no release note (Release record/Installed release.md)", text)
        self.assertIn("will not guess", text)
        self.assertIn("Ask the owner, or whoever set up Pace, for the release repository address", text)
        self.assertIn("--repo <address>", text)
        self.assertNotIn("github.com", text)
        self.assertEqual(tree_bytes(folder), before)

        # The existing route still works: give the repository, and the next install writes the note.
        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n")
        code, text = self.check(folder, "--repo", str(self.repo.path))
        self.assertEqual(code, 0, text)
        self.assertIn(f"--tag v3.8.0 --commit {c38}", text)
        result = pu.apply(folder, str(self.repo.path), "v3.8.0", c38, go_ahead=self.go_ahead("v3.8.0", c38))
        self.assertEqual(result["status"], "installed", result.get("message"))
        note = self.note(folder)
        self.assertEqual((note["entries"], note["entry"]["tag"], note["entry"]["commit"]), (1, "v3.8.0", c38))
        self.assertEqual(note["entry"]["event"], "Installed with the Product updater")
        self.assertTrue((folder / "Release record" / note["entry"]["record"]).is_file())
        code, text = self.check(folder)
        self.assertEqual(code, 0, text)
        self.assertIn("nothing to update", text)

    def test_unusable_note_is_reported_plainly_and_never_guessed_around(self):
        folder = self.new_folder()
        path = folder / NOTE
        good = path.read_text(encoding="utf-8")
        cases = {
            "incomplete last entry": (good + "\n## 2026-10-24 09:00:00 UTC - Hand-written\n\n- Release repository: x\n",
                                      "The last entry in Release record/Installed release.md cannot be used: "
                                      "it does not name the installed release tag."),
            "not a release note": ("My own notes about Pace.\n", "does not say it is a Pace release note"),
            "password in the address": (good.replace(f"- Release repository: {self.repo.path.resolve()}",
                                                     "- Release repository: https://me:token123@example.invalid/pace.git"),
                                        "includes sign-in details"),
            "no entries": (good.split("\n## ")[0] + "\n", "has no entries yet"),
        }
        for label, (text, phrase) in cases.items():
            with self.subTest(label):
                path.write_text(text, encoding="utf-8")
                before = tree_bytes(folder)
                with mock.patch.object(pu, "latest_release", side_effect=AssertionError("contacted a repository")):
                    code, out = self.check(folder)
                self.assertEqual(code, 1, out)
                self.assertIn(phrase, out)
                self.assertIn("will not guess", out)
                self.assertEqual(tree_bytes(folder), before)

    def test_an_install_leaves_a_file_that_is_not_a_note_alone(self):
        folder = self.new_folder()
        (folder / NOTE).write_text("My own notes about Pace.\n", encoding="utf-8")
        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n")
        result = pu.apply(folder, str(self.repo.path), "v3.8.0", c38, go_ahead=self.go_ahead("v3.8.0", c38))
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertIn("could not be updated", result["warning"])
        self.assertIn("give --repo when you preview", result["warning"])
        self.assertEqual((folder / NOTE).read_text(encoding="utf-8"), "My own notes about Pace.\n")
        self.assertFalse((folder / "Release record/Update in progress").exists())

    def test_v350_folder_without_note_updates_by_the_existing_route(self):
        legacy = Repo(self.base / "legacy releases")
        legacy.write("starter/Pace.md", "# Invented older copy\n")
        legacy.write("starter/Product/Help/updates.md", "Invented help 3.5.0\n")
        old = legacy.commit("Invented 3.5.0")
        legacy.tag("v3.5.0")
        new = release(legacy, "v3.7.0", "Invented help 3.7.0\n")
        folder = self.base / "Legacy PACE"
        git(legacy.path, "checkout", "--quiet", old)
        shutil.copytree(legacy.path / "starter", folder)
        git(legacy.path, "checkout", "--quiet", "main")
        self.assertFalse((folder / "Release record").exists())
        code, text = self.check(folder)
        self.assertEqual(code, 1, text)
        self.assertIn("no release note", text)
        code, text = self.check(folder, "--repo", str(legacy.path))
        self.assertEqual(code, 0, text)
        self.assertIn("Installed now: no earlier install is recorded in this folder.", text)
        result = pu.apply(folder, str(legacy.path), "v3.7.0", new, go_ahead=self.go_ahead("v3.7.0", new))
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertEqual((folder / "Pace.md").read_text(encoding="utf-8"), "# Invented older copy\n")
        self.assertEqual(self.note(folder)["entry"]["tag"], "v3.7.0")
        code, text = self.check(folder)
        self.assertIn("nothing to update", text)


class ForkOrMirror(NoteCase):
    def test_mirror_is_the_release_source_and_upstream_details_are_noted(self):
        mirror = self.base / "client-mirror.git"
        subprocess.run(["git", "clone", "--quiet", "--mirror", str(self.repo.path), str(mirror)], check=True, env=clean_git_env())
        folder = self.new_folder(repo=mirror)
        self.assertEqual(self.note(folder)["entry"]["repository"], str(mirror.resolve()))

        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n")
        code, text = self.check(folder)
        self.assertIn("nothing to update", text)  # the mirror has not received v3.8.0 yet
        git(mirror, "fetch", "--quiet")  # client IT syncs its mirror
        code, text = self.check(folder)
        self.assertIn(f"Release source: {mirror.resolve()}, read from", text)
        self.assertIn("Update available: Pace v3.8.0", text)

        upstream = {"repo": str(self.repo.path), "tag": "v3.8.0", "commit": c38}
        result = pu.apply(folder, str(mirror), "v3.8.0", c38, upstream=upstream, go_ahead=self.go_ahead("v3.8.0", c38))
        self.assertEqual(result["status"], "installed", result.get("message"))
        entry = self.note(folder)["entry"]
        self.assertEqual(entry["repository"], str(mirror.resolve()))
        self.assertEqual((entry["upstream_repository"], entry["upstream_tag"], entry["upstream_commit"]),
                         (str(self.repo.path), "v3.8.0", c38))

        release(self.repo, "v3.9.0", "Invented help 3.9.0\n")  # upstream only
        code, text = self.check(folder)
        self.assertEqual(code, 0, text)
        self.assertIn(f"Release source: {mirror.resolve()} (a client copy of {self.repo.path}), read from", text)
        self.assertIn("nothing to update", text)
        self.assertNotIn("v3.9.0", text)

    def test_fork_with_changed_product_is_refused_and_the_note_is_unchanged(self):
        folder = self.new_folder()
        fork = self.base / "client-fork"
        subprocess.run(["git", "clone", "--quiet", str(self.repo.path), str(fork)], check=True, env=clean_git_env())
        (fork / "PACE/Product/Help/updates.md").write_text("Client-changed help.\n", encoding="utf-8")
        git(fork, "commit", "--quiet", "-am", "Client change")
        fork_commit = git(fork, "rev-parse", "HEAD")
        git(fork, "tag", "v3.7.1")
        code, text = self.check(folder, "--repo", str(fork))
        self.assertIn("Update available: Pace v3.7.1", text)
        note_before = (folder / NOTE).read_bytes()
        upstream = {"repo": str(self.repo.path), "tag": "v3.7.0", "commit": self.c37}
        with self.assertRaisesRegex(pu.Stop, "differs from upstream v3.7.0"):
            pu.apply(folder, str(fork), "v3.7.1", fork_commit, upstream=upstream,
                     go_ahead=self.go_ahead("v3.7.1", fork_commit))
        self.assertEqual((folder / NOTE).read_bytes(), note_before)


class NoteSurvivesUpdates(NoteCase):
    def test_note_survives_an_update_and_gains_the_new_release(self):
        folder = self.new_folder()
        note_before = (folder / NOTE).read_bytes()
        owner_before = owner_view(folder)
        # This release also ships a stray note and owner files; only Product is ever installed.
        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n", extra={
            "PACE/Release record/Installed release.md": "Template note that must never be installed.\n",
            "PACE/Pace.md": "# Template Pace.md that must never be installed\n",
        })
        result = pu.apply(folder, str(self.repo.path), "v3.8.0", c38, go_ahead=self.go_ahead("v3.8.0", c38))
        self.assertEqual(result["status"], "installed", result.get("message"))
        self.assertNotIn("warning", result)
        self.assertEqual(owner_view(folder), owner_before)
        self.assertEqual((folder / "Product/Help/updates.md").read_text(encoding="utf-8"), "Invented help 3.8.0\n")
        after = (folder / NOTE).read_bytes()
        self.assertTrue(after.startswith(note_before))  # earlier text is never changed
        self.assertNotIn(b"Template note", after)
        note = self.note(folder)
        self.assertEqual((note["entries"], note["entry"]["tag"], note["entry"]["commit"]), (2, "v3.8.0", c38))
        self.assertEqual(note["entry"]["digest"], result["product_file_list"]["digest"])
        self.assertEqual(f"Release record/{note['entry']['record']}", result["record"])
        self.assertIn(f"replacing Pace v3.7.0 (commit {self.c37})",
                      (folder / "Release record/Install receipts.md").read_text(encoding="utf-8"))
        code, text = self.check(folder)
        self.assertEqual(code, 0, text)
        self.assertIn("nothing to update", text)
        self.assertIn("recorded in Release record/Installs/", text)

    def test_rolled_back_or_interrupted_updates_keep_the_note_true(self):
        folder = self.new_folder()
        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n")
        note_before = (folder / NOTE).read_bytes()

        def owner_writes(stage):
            if stage == "new-in-place":
                (folder / "Record/20261024T090000Z--invented--mid001.md").write_text("Mid-update.\n", encoding="utf-8")

        with mock.patch.object(pu, "_checkpoint", side_effect=owner_writes):
            result = pu.apply(folder, str(self.repo.path), "v3.8.0", c38, go_ahead=self.go_ahead("v3.8.0", c38))
        self.assertEqual(result["status"], "rolled back")
        self.assertEqual((folder / NOTE).read_bytes(), note_before)

        # Stopped before the note was added (recover adds it) or just after (recover adds nothing).
        for stage, tag, entries in (("recorded", "v3.9.0", 2), ("noted", "v3.10.0", 3)):
            with self.subTest(stage=stage):
                commit = release(self.repo, tag, f"Invented help {tag}\n")

                def stop_at(name, stage=stage):
                    if name == stage:
                        raise KeyboardInterrupt  # a hard stop after the install was recorded

                with mock.patch.object(pu, "_checkpoint", side_effect=stop_at), self.assertRaises(KeyboardInterrupt):
                    pu.apply(folder, str(self.repo.path), tag, commit, go_ahead=self.go_ahead(tag, commit))
                self.assertTrue((folder / "Release record/Update in progress").is_dir())
                recovered = pu.recover(folder.resolve())
                self.assertTrue(recovered["installed"], recovered)
                note = self.note(folder)
                self.assertEqual((note["entry"]["tag"], note["entry"]["commit"]), (tag, commit))
                self.assertEqual(note["entries"], entries)
        text = (folder / NOTE).read_text(encoding="utf-8")
        self.assertEqual(text.count("- Installed release: v3.10.0"), 1)

    def test_changes_inside_a_copied_product_need_an_explicit_choice(self):
        folder = self.new_folder()
        c38 = release(self.repo, "v3.8.0", "Invented help 3.8.0\n")
        (folder / "Product/Help/updates.md").write_text("Owner edited shipped help.\n", encoding="utf-8")
        code, text = self.check(folder)
        self.assertIn("some installed files differ from that record", text)
        self.assertIn("files not named, because the release note keeps a fingerprint", text)
        with self.assertRaisesRegex(pu.Stop, "differ from the release noted in Release record/Installed release.md"):
            pu.apply(folder, str(self.repo.path), "v3.8.0", c38, go_ahead=self.go_ahead("v3.8.0", c38))
        result = pu.apply(folder, str(self.repo.path), "v3.8.0", c38, go_ahead=self.go_ahead("v3.8.0", c38),
                          replace_changed_product=True)
        self.assertEqual(result["status"], "installed", result.get("message"))


class HelpForAnAssistant(unittest.TestCase):
    def test_help_says_check_means_read_the_note_then_preview_latest(self):
        updates = (PACE_FOLDER / "Product/Help/updates.md").read_text(encoding="utf-8")
        section = updates.split("## Checking for an update")[1].split("\n## ")[0]
        self.assertIn("`Release record/Installed release.md`", section)
        self.assertIn("python3 Product/Tools/pace_update.py preview --root . --latest", section)
        self.assertIn("go-ahead", section)
        self.assertIn("--repo", section)
        pace = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        help_lines = pace.split("## Help, when relevant")[1]
        self.assertIn("`Release record/Installed release.md`", help_lines)
        self.assertIn("Release record/Installed release.md", (ROOT / "README.md").read_text(encoding="utf-8"))
        for text in (updates, pace):
            self.assertNotIn("—", text)


if __name__ == "__main__":
    unittest.main()
