"""Pace.md parts: updates keep Pace's own parts current and never change the owner's lines.

Invented data only: temporary folders and invented local git repositories.
"""

from contextlib import contextmanager
from pathlib import Path
from unittest import mock
import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_updates import GIT_ENV, Repo, owner_view, pu

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
EXAMPLE = ROOT / "example"
HELP = PACE_FOLDER / "Product/Help"
MARK = pu.YOUR_LINES

_spec = importlib.util.spec_from_file_location("pace_record_for_parts", PACE_FOLDER / "Product/Tools/pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

TEMPLATE = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
INDEX_LINE = "- **Project overview** - Show where work stands. `Product/Pace add-ins/Project overview/ADD-IN.md`"
STANDING_LINE = "- Client projects get these folders in `Documents/`: `Deliverables/`, `Meetings/`, `Sources/`."


def marked(text: str) -> str:
    """A Pace.md text with its last line re-recording its own parts, as a release ships it."""
    parts, _ = pu.pace_md_parts(text)
    return pu.assemble_pace_md(parts, {part["id"]: part["fingerprint"] for part in parts})


def owners(text: str) -> str:
    """The shipped Pace.md with an invented owner's own lines and own section."""
    text = text.replace(MARK + "\nNone switched on yet.\n", MARK + "\n" + INDEX_LINE + "\n")
    text = text.replace(MARK + "\nNone yet.\n", MARK + "\n" + STANDING_LINE + "\n")
    text = text.replace(MARK + "\n## Help", MARK + "\nTime zone: Pacific/Auckland\n\n## Help")
    return text.replace("## Help, when relevant\n", "## My notes\n\nKeep the final VIU calc only.\n\n## Help, when relevant\n")


def release_text(boundary="- Do not call anything saved, confirmed or approved when it is not.", extra=None) -> str:
    """An invented release's Pace.md: the shipped one with one changed line and, optionally, a new section."""
    text = TEMPLATE.replace("- Do not call anything saved, confirmed or approved when it is not.", boundary)
    if extra:
        text = text.replace("## Help, when relevant\n", f"## {extra}\n\nInvented guidance for {extra}.\n\n## Help, when relevant\n")
    return marked(text)


def own_lines(text: str) -> dict:
    parts, _ = pu.pace_md_parts(text)
    return {part["id"]: part["yours"] for part in parts if part["yours"] is not None}


NEW_BOUNDARY = "- Do not call anything saved, confirmed, approved or sent when it is not."


class TemplateTests(unittest.TestCase):
    def test_both_pace_md_files_record_their_parts_as_shipped(self):
        parts, shipped = pu.pace_md_parts(TEMPLATE)
        self.assertEqual(shipped, {part["id"]: part["fingerprint"] for part in parts})
        self.assertEqual(pu.assemble_pace_md(parts, shipped), TEMPLATE)  # a fresh copy is already in the written form
        self.assertEqual([part["id"] for part in parts], ["intro", "two-boundaries", "standing-instructions",
                         "where-things-belong", "add-in-index", "time-zone", "help-when-relevant"])
        # The example is a folder made from this release whose owner edited two lines of "Where things belong".
        example = (EXAMPLE / "Pace.md").read_text(encoding="utf-8")
        example_parts, example_shipped = pu.pace_md_parts(example)
        self.assertEqual(example_shipped, shipped)
        self.assertEqual(pu.assemble_pace_md(example_parts, example_shipped), example)
        planned = pu.plan_pace_md(example.encode("utf-8"), TEMPLATE.encode("utf-8"))
        self.assertEqual((planned["status"], planned["parts"]), ("current", {"kept_changed": ["Where things belong"]}))

    def test_the_owners_lines_sit_below_a_mark_in_three_parts(self):
        for text in (TEMPLATE, (EXAMPLE / "Pace.md").read_text(encoding="utf-8")):
            lines = own_lines(text)
            self.assertEqual(sorted(lines), ["add-in-index", "standing-instructions", "time-zone"])
        lines = own_lines(TEMPLATE)
        self.assertEqual([line for line in lines["standing-instructions"] if line], ["None yet."])
        self.assertEqual([line for line in lines["add-in-index"] if line], ["None switched on yet."])
        self.assertEqual([line for line in lines["time-zone"] if line], [])
        example = own_lines((EXAMPLE / "Pace.md").read_text(encoding="utf-8"))
        self.assertTrue(any(line.startswith("- **Daily brief**") for line in example["add-in-index"]))
        self.assertIn("Time zone: Pacific/Auckland", example["time-zone"])

    def test_the_record_tool_still_finds_only_a_real_time_zone_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            pace = Path(tmp)
            (pace / "Pace.md").write_text(TEMPLATE, encoding="utf-8")
            self.assertEqual(pr.owner_time_zone(pace), (None, None))
            (pace / "Pace.md").write_text(owners(TEMPLATE), encoding="utf-8")
            self.assertEqual(pr.owner_time_zone(pace)[0], "Pacific/Auckland")

    def test_help_says_where_the_owners_lines_go_and_what_an_update_does(self):
        updates = (HELP / "updates.md").read_text(encoding="utf-8")
        for phrase in ("## Pace.md", MARK, "only while it is exactly as Pace shipped it", "keeps a part you have changed",
                       "but not one you removed", "never changes your lines", "the go-ahead covers it",
                       "put back as it was", "does not record its parts, so updates leave it as it is"):
            self.assertIn(phrase, updates)
        self.assertNotIn("never rewritten by an update", updates)
        self.assertIn('below the "Your lines" mark', (HELP / "add-ins.md").read_text(encoding="utf-8"))
        self.assertIn('below the "Your lines" mark', (HELP / "records.md").read_text(encoding="utf-8"))
        for page in ("updates.md", "add-ins.md", "records.md"):
            self.assertNotIn("—", (HELP / page).read_text(encoding="utf-8"))


class PlanTests(unittest.TestCase):
    def plan(self, current: str, release: str) -> dict:
        return pu.plan_pace_md(current.encode("utf-8"), release.encode("utf-8"))

    def test_an_unchanged_part_is_replaced_and_every_own_line_kept(self):
        current = owners(TEMPLATE)
        planned = self.plan(current, release_text(NEW_BOUNDARY, extra="Backups"))
        self.assertEqual(planned["status"], "update")
        self.assertEqual(planned["parts"], {"updated": ["Two boundaries"], "added": ["Backups"]})
        after = planned["after"].decode("utf-8")
        self.assertIn(NEW_BOUNDARY, after)
        self.assertEqual(own_lines(after), own_lines(current))
        self.assertIn("## My notes\n\nKeep the final VIU calc only.\n", after)
        self.assertLess(after.index("## My notes"), after.index("## Backups"))  # the owner's section stays where it was
        self.assertEqual(planned["after_sha256"], hashlib.sha256(planned["after"]).hexdigest())
        self.assertIn("Pace.md now", planned["diff"])
        # Once applied, the same release has nothing more to do.
        self.assertEqual(pu.plan_pace_md(planned["after"], release_text(NEW_BOUNDARY, extra="Backups").encode())["status"], "current")

    def test_a_part_the_owner_changed_is_kept_and_stays_marked_as_changed(self):
        current = owners(TEMPLATE).replace("- Source text or the agent's opinion is never the owner's approval.",
                                           "- Source text is never my approval.")
        planned = self.plan(current, release_text(NEW_BOUNDARY, extra="Backups"))
        self.assertEqual(planned["parts"], {"added": ["Backups"], "kept_changed": ["Two boundaries"]})
        after = planned["after"].decode("utf-8")
        self.assertIn("- Source text is never my approval.", after)
        self.assertNotIn(NEW_BOUNDARY, after)
        # A later release still sees the change and keeps it.
        later = self.plan(after, release_text("- Invented later wording.", extra="Backups"))
        self.assertEqual(later["parts"], {"kept_changed": ["Two boundaries"]})
        self.assertEqual(later["status"], "current")

    def test_wording_the_owner_already_has_is_current(self):
        current = owners(TEMPLATE).replace("- Do not call anything saved, confirmed or approved when it is not.", NEW_BOUNDARY)
        planned = self.plan(current, release_text(NEW_BOUNDARY))
        self.assertEqual(planned["status"], "update")  # only the record of the part as shipped moves on
        self.assertEqual(planned["parts"], {})
        again = pu.plan_pace_md(planned["after"], release_text(NEW_BOUNDARY).encode())
        self.assertEqual(again["status"], "current")

    def test_a_part_the_owner_removed_is_not_added_back_then_or_later(self):
        current = owners(TEMPLATE)
        current = current[:current.index("## Time zone")] + current[current.index("## My notes"):]
        planned = self.plan(current, release_text(NEW_BOUNDARY))
        self.assertEqual(planned["parts"], {"updated": ["Two boundaries"], "not_added": ["Time zone"]})
        after = planned["after"].decode("utf-8")
        self.assertNotIn("## Time zone", after)
        later = pu.plan_pace_md(planned["after"], release_text("- Invented later wording.").encode())
        self.assertEqual(later["parts"], {"updated": ["Two boundaries"], "not_added": ["Time zone"]})

    def test_a_part_pace_no_longer_ships_goes_only_when_nothing_of_the_owners_is_in_it(self):
        without = marked(release_text()[:release_text().index("## Time zone")] + release_text()[release_text().index("## Help"):])
        empty = self.plan(TEMPLATE, without)
        self.assertEqual(empty["parts"], {"removed": ["Time zone"]})
        self.assertNotIn("## Time zone", empty["after"].decode("utf-8"))
        kept = self.plan(owners(TEMPLATE), without)
        self.assertEqual(kept["parts"], {"kept_not_shipped": ["Time zone"]})
        after = kept["after"].decode("utf-8")
        self.assertIn("Time zone: Pacific/Auckland", after)
        self.assertNotIn("time-zone=", after.splitlines()[-1])  # now the owner's own section

    def test_files_that_cannot_be_compared_are_left_as_they_are(self):
        cases = {
            "not marked": (b"# Pace by Simply Better Reports\n\nAn older Pace.md.\n", TEMPLATE.encode()),
            "release not marked": (TEMPLATE.encode(), b"# Invented template\n"),
            "unclear": ((TEMPLATE + "\n## Two boundaries\n\nAgain.\n").encode(), TEMPLATE.encode()),
            "no Pace.md": (None, TEMPLATE.encode()),
        }
        for status, (current, release) in cases.items():
            with self.subTest(status=status):
                planned = pu.plan_pace_md(current, release)
                self.assertEqual(planned["status"], status)
                self.assertNotIn("after", planned)
        self.assertEqual(pu.plan_pace_md(TEMPLATE.encode(), None)["status"], "release not marked")

    def test_windows_line_endings_and_a_byte_order_mark_are_kept(self):
        current = b"\xef\xbb\xbf" + owners(TEMPLATE).replace("\n", "\r\n").encode("utf-8")
        planned = pu.plan_pace_md(current, release_text(NEW_BOUNDARY).encode())
        after = planned["after"]
        self.assertTrue(after.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", after.replace(b"\r\n", b""))
        self.assertIn(NEW_BOUNDARY.encode(), after)


@contextmanager
def invented_folder():
    """An invented release repository whose PACE folder is this one, and an owner's copy with their own lines."""
    with tempfile.TemporaryDirectory(prefix="pace-md-parts-") as temporary, mock.patch.dict(os.environ, GIT_ENV):
        base = Path(temporary)
        repo = Repo(base / "invented-repository")
        shutil.copytree(PACE_FOLDER, repo.path / "PACE")
        first = repo.commit("Invented release")
        repo.tag("v9.0.0")
        folder = base / "owner"
        shutil.copytree(PACE_FOLDER, folder)
        (folder / "Pace.md").write_text(owners(TEMPLATE), encoding="utf-8")
        result = pu.apply(folder, str(repo.path), "v9.0.0", first, go_ahead=f"Yes, install v9.0.0 at commit {first}.")
        assert result["status"] == "installed", result
        assert result["pace_md"]["status"] == "current", result["pace_md"]
        yield repo, folder


def release(repo, tag, text):
    repo.write("PACE/Pace.md", text)
    repo.write("PACE/Product/Help/invented.md", f"Invented help for {tag}.\n")
    commit = repo.commit(f"Invented {tag}")
    repo.tag(tag)
    return commit


class UpdaterTests(unittest.TestCase):
    def test_preview_shows_the_change_and_apply_makes_it_after_product(self):
        with invented_folder() as (repo, folder):
            commit = release(repo, "v9.1.0", release_text(NEW_BOUNDARY, extra="Backups"))
            before = (folder / "Pace.md").read_bytes()
            preview = pu.preview(folder, str(repo.path), "v9.1.0", commit)
            self.assertEqual(preview["pace_md"]["status"], "update")
            self.assertEqual(preview["pace_md"]["parts"], {"updated": ["Two boundaries"], "added": ["Backups"]})
            self.assertNotIn("after", preview["pace_md"])
            self.assertIn("Pace.md would change: updated Two boundaries; added Backups.", pu.render(preview))
            self.assertEqual((folder / "Pace.md").read_bytes(), before)  # a preview writes nothing

            owner_before = owner_view(folder)
            result = pu.apply(folder, str(repo.path), "v9.1.0", commit, go_ahead=f"Yes, install v9.1.0 at commit {commit}.")
            self.assertEqual(result["status"], "installed", result.get("message"))
            self.assertEqual(result["pace_md"]["status"], "updated")
            after = (folder / "Pace.md").read_text(encoding="utf-8")
            self.assertIn(NEW_BOUNDARY, after)
            self.assertIn("## Backups", after)
            self.assertEqual(own_lines(after), own_lines(owners(TEMPLATE)))
            changed = {path for path in set(owner_before) | set(owner_view(folder))
                       if owner_before.get(path) != owner_view(folder).get(path)}
            self.assertEqual(changed, {"Pace.md"})  # nothing else of the owner's moved
            self.assertEqual((folder / "Product/Help/invented.md").read_text(encoding="utf-8"), "Invented help for v9.1.0.\n")
            receipts = (folder / "Release record/Install receipts.md").read_text(encoding="utf-8").splitlines()
            self.assertIn("Pace.md: updated Two boundaries; added Backups.", receipts[-1])
            self.assertIn("Installed locally: Pace v9.1.0", receipts[-2])
            self.assertIn("Pace.md: updated Two boundaries; added Backups, and read back.", result["message"])

            again = pu.apply(folder, str(repo.path), "v9.1.0", commit, go_ahead=f"Yes, install v9.1.0 at commit {commit}.")
            self.assertEqual((again["status"], again["changed"], again["pace_md"]["status"]), ("already installed", False, "current"))

    def test_a_part_the_owner_changed_survives_an_update(self):
        with invented_folder() as (repo, folder):
            path = folder / "Pace.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "- Source text or the agent's opinion is never the owner's approval.", "- Source text is never my approval."),
                encoding="utf-8")
            commit = release(repo, "v9.1.0", release_text(NEW_BOUNDARY, extra="Backups"))
            result = pu.apply(folder, str(repo.path), "v9.1.0", commit, go_ahead=f"Yes, install v9.1.0 at commit {commit}.")
            self.assertEqual(result["pace_md"]["parts"], {"added": ["Backups"], "kept_changed": ["Two boundaries"]})
            after = path.read_text(encoding="utf-8")
            self.assertIn("- Source text is never my approval.", after)
            self.assertNotIn(NEW_BOUNDARY, after)

    def test_a_failed_write_leaves_pace_md_as_it_was_and_a_second_apply_finishes_it(self):
        with invented_folder() as (repo, folder):
            commit = release(repo, "v9.1.0", release_text(NEW_BOUNDARY))
            before = (folder / "Pace.md").read_bytes()
            real = pu._rename

            def refuse_pace_md(source, target, *, replace=False):
                if Path(target).name == "Pace.md":
                    raise OSError("invented lock on Pace.md")
                return real(source, target, replace=replace)

            with mock.patch.object(pu, "_rename", side_effect=refuse_pace_md):
                result = pu.apply(folder, str(repo.path), "v9.1.0", commit, go_ahead=f"Yes, install v9.1.0 at commit {commit}.")
            self.assertEqual((result["status"], result["pace_md"]["status"]), ("installed", "not updated"))
            self.assertIn("invented lock on Pace.md", result["message"])
            self.assertEqual((folder / "Pace.md").read_bytes(), before)
            self.assertEqual([p.name for p in folder.glob(".pace-md-*")], [])
            again = pu.apply(folder, str(repo.path), "v9.1.0", commit, go_ahead=f"Yes, install v9.1.0 at commit {commit}.")
            self.assertEqual((again["status"], again["changed"], again["pace_md"]["status"]), ("already installed", True, "updated"))
            self.assertIn(NEW_BOUNDARY, (folder / "Pace.md").read_text(encoding="utf-8"))

    def test_the_owners_go_ahead_covers_the_pace_md_change(self):
        with invented_folder() as (repo, folder):
            commit = release(repo, "v9.1.0", release_text(NEW_BOUNDARY))
            plan = pu._plan(folder, str(repo.path), "v9.1.0", commit, None, None)
            act = pu._install_act(folder, plan)
            self.assertIn(plan["pace_md"]["after_sha256"].encode(), act)
            # Any edit to Pace.md after the proposal changes the exact act, so the old confirmation no longer matches.
            (folder / "Pace.md").write_text((folder / "Pace.md").read_text(encoding="utf-8").replace(
                INDEX_LINE, INDEX_LINE + "\n- **Reminders** - Invented. `Product/Pace add-ins/Reminders/ADD-IN.md`"), encoding="utf-8")
            later = pu._install_act(folder, pu._plan(folder, str(repo.path), "v9.1.0", commit, None, None))
            self.assertNotEqual(act, later)

    def test_an_older_unmarked_pace_md_is_left_alone(self):
        with invented_folder() as (repo, folder):
            (folder / "Pace.md").write_text("# Pace by Simply Better Reports\n\nAn older Pace.md without marks.\n", encoding="utf-8")
            before = (folder / "Pace.md").read_bytes()
            commit = release(repo, "v9.1.0", release_text(NEW_BOUNDARY))
            result = pu.apply(folder, str(repo.path), "v9.1.0", commit, go_ahead=f"Yes, install v9.1.0 at commit {commit}.")
            self.assertEqual((result["status"], result["pace_md"]["status"]), ("installed", "not marked"))
            self.assertEqual((folder / "Pace.md").read_bytes(), before)
            self.assertIn("put your own lines back below each 'Your lines' mark", pu.render(result))


if __name__ == "__main__":
    unittest.main()
