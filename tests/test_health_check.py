"""The health check, against Pace folders installed from an invented release and then put out of order on purpose.

Every check reads only, so each test also shows the folder is byte for byte and time for time as it was.
Invented data only: temporary folders and an invented local git repository.
"""

from __future__ import annotations

from pathlib import Path
import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

import test_updates as tu

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
TOOL = PACE_FOLDER / "Product/Tools/pace_check.py"
_spec = importlib.util.spec_from_file_location("pace_check", TOOL)
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)
pu, pr = pc.pu, pc.pr

MARK = "<!-- Your lines go below this one. Pace updates never change them. -->"
OWNER = "Rangi Parata"
TODAY = dt.datetime.now().astimezone().date()
STATE: dict = {}


def write_project(pace: Path, pid: str, name: str, parent: str = "none", inside: Path | None = None,
                  documents: str = "Documents") -> Path:
    folder = (inside or pace / "1 Projects") / name
    (folder / documents).mkdir(parents=True, exist_ok=True)
    (folder / "Pace project.md").write_text(f"---\nformat: project-1\nid: {pid}\nparent: {parent}\n"
                                            "created: 2026-10-20T09:00:00+13:00\nby: Test\n---\n\nInvented work.\n",
                                            encoding="utf-8")
    return folder


def write_record(pace: Path, request: str, kind: str = "action", subject: str = "Board pack", body: str = "Invented work.",
                 **fields) -> Path:
    project = pr.REQUEST.match(request).group(2) if pr.REQUEST.match(request) else "none"
    lines = ["---", "format: record-1", f"request: {request}", "created: 2026-10-25T09:00:00+13:00", f"project: {project}",
             f"kind: {kind}", f"subject: {subject}", "from: agent", "by: Test"]
    lines += [f"{key.replace('_', '-')}: {value}" for key, value in fields.items()]
    path = pace / "Record" / f"{request}.md"
    path.write_text("\n".join(lines + ["---", "", body, ""]), encoding="utf-8")
    return path


def setUpModule():
    tu.setUpModule()
    STATE["temp"] = tempfile.TemporaryDirectory(prefix="pace-check-")
    base = Path(STATE["temp"].name)
    repo = tu.Repo(base / "upstream")
    shutil.copytree(PACE_FOLDER, repo.path / "PACE", ignore=shutil.ignore_patterns("__pycache__"))
    commit = repo.commit("An invented release")
    repo.tag("v3.12.0")
    folder = base / "Installed Pace"
    shutil.copytree(PACE_FOLDER, folder, ignore=shutil.ignore_patterns("__pycache__"))
    result = pu.apply(folder, str(repo.path), "v3.12.0", commit, go_ahead=f"Install Pace v3.12.0 at commit {commit}, please.")
    assert result["status"] == "installed", result
    # The owner's own lines, a project with work in it, and the owner's assistant setup.
    pace_md = folder / "Pace.md"
    text = pace_md.read_text(encoding="utf-8")
    text = text.replace(f"{MARK}\n## Time zone", f"{MARK}\nOwner: {OWNER}\n\n## Time zone")
    text = text.replace(f"{MARK}\n## Help", f"{MARK}\nTime zone: Pacific/Auckland\n\n## Help")
    pace_md.write_text(text, encoding="utf-8")
    # Numbered, as projects are from 3.16.0; Repos/ mirrors them by their names, without the numbers.
    client = write_project(folder, "kowhai", "01. Kowhai Books", documents="01. Documents")
    write_project(folder, "kowhai-budget", "02. Budget 2027", parent="kowhai", inside=client, documents="01. Documents")
    write_record(folder, "20261025T010000Z--kowhai-budget--act001", owed_by=OWNER, state="open")
    write_record(folder, "20261025T020000Z--kowhai--act002", subject="Site copy", owed_by="Ana Ruiz", state="open")
    (folder / "Repos/Kowhai Books/Budget 2027/budget-model").mkdir(parents=True)
    (folder / "Repos/Kowhai Books/Budget 2027/budget-model/Pace repo.md").write_text(
        "# Budget model\n\nHome project id: kowhai-budget\nRepository link: https://example.invalid/budget-model\n", encoding="utf-8")
    (folder / "3 My add-ins/Assistant setup.md").write_text(
        f"# Assistant setup\n\nLast checked: {TODAY.isoformat()}\n\n## Claude\n\n- Connections: none.\n", encoding="utf-8")
    STATE.update(base=base, repo=repo, commit=commit, folder=folder)


def tearDownModule():
    STATE["temp"].cleanup()
    tu.tearDownModule()


def snapshot(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns) if path.is_file() else "folder"
            for path in sorted(root.rglob("*"))}


class CheckCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="pace-check-case-")
        self.pace = Path(self._temp.name) / "Pace"
        shutil.copytree(STATE["folder"], self.pace)

    def tearDown(self):
        self._temp.cleanup()

    def check(self, *argv):
        before = snapshot(self.pace)
        out, code = pc.run(pc.build_parser().parse_args(["--pace", str(self.pace), *argv]))
        self.assertEqual(snapshot(self.pace), before, "the check changed the folder")
        self.assertEqual(code, 0 if out["status"] == "healthy" else 1)
        return out

    def found(self, out, check, level=None):
        return [item for item in out["findings"] if item["check"] == check and (level is None or item["level"] == level)]

    def edit_pace_md(self, old, new):
        path = self.pace / "Pace.md"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new), encoding="utf-8")


class HealthyTests(CheckCase):
    def test_a_folder_in_good_order_is_healthy(self):
        out = self.check()
        self.assertEqual((out["status"], out["counts"]), ("healthy", {"problem": 0, "warning": 0, "note": 0}), out["findings"])
        self.assertIn("0 problems, 0 warnings and 0 notes. Nothing needs doing. Nothing was changed.", out["message"])
        self.assertEqual(out["findings"], [])
        said = " ".join(out["checked"])
        for phrase in ("Record/: 2 record files, each opened", "1 Projects/: 2 projects", "Repos/: 1 repository reference",
                       "add --latest", "3 My add-ins/Assistant setup.md."):
            self.assertIn(phrase, said)

    def test_it_finds_its_own_pace_folder_and_prints_one_json_object(self):
        run = subprocess.run([sys.executable, "-B", "Product/Tools/pace_check.py"], cwd=self.pace, capture_output=True,
                             text=True, env={key: value for key, value in os.environ.items() if key != "PACE_FOLDER"})
        out = json.loads(run.stdout)
        self.assertEqual((out["status"], run.returncode, out["pace"]), ("healthy", 0, str(self.pace.resolve())))
        (self.pace / "Pace.md").unlink()
        run = subprocess.run([sys.executable, "-B", "Product/Tools/pace_check.py"], cwd=self.pace, capture_output=True,
                             text=True, env={key: value for key, value in os.environ.items() if key != "PACE_FOLDER"})
        out = json.loads(run.stdout)
        self.assertEqual((out["status"], run.returncode), ("problems", 1))
        self.assertIn("Pace.md is missing", out["findings"][0]["message"])


class FolderTests(CheckCase):
    def test_projects_under_the_old_name_are_one_problem_not_one_per_project(self):
        (self.pace / "1 Projects").rename(self.pace / "Projects")
        (self.pace / "2 Views").rename(self.pace / "Views")
        out = self.check()
        names = self.found(out, "folder-names")
        self.assertEqual([item["level"] for item in names], ["problem", "warning"])
        self.assertIn("so no tool can find them: rename Projects/ to 1 Projects/", names[0]["message"])
        self.assertIn("rename Views/ to 2 Views/", names[1]["message"])
        self.assertEqual(self.found(out, "projects") + self.found(out, "repos") + self.found(out, "folders"), [])
        self.assertEqual(out["status"], "problems")

    def test_a_missing_folder_is_named(self):
        shutil.rmtree(self.pace / "Release record")
        out = self.check()
        self.assertEqual([item["message"] for item in self.found(out, "folders", "warning")],
                         ["Release record/ was not found in this Pace folder, so an update cannot tell which release is "
                          "installed or where releases come from."])


class PaceMdTests(CheckCase):
    def test_no_owner_line_is_a_warning_that_names_who_records_say_owes_work(self):
        self.edit_pace_md(f"Owner: {OWNER}\n", "")
        out = self.check()
        [item] = self.found(out, "owner")
        self.assertEqual(item["level"], "warning")
        self.assertIn("Records most often name these people as owing work: Rangi Parata (1), Ana Ruiz (1).", item["message"])
        self.assertIn("`Owner: Rangi Parata`", item["fix"])

    def test_an_owner_line_no_action_uses_is_noted(self):
        self.edit_pace_md(f"Owner: {OWNER}\n", "Owner: Rangi P\n")
        for number in range(10):
            write_record(self.pace, f"20261025T03{number:02d}00Z--kowhai--oth{number:03d}", subject=f"Item {number}",
                         owed_by="Ana Ruiz", state="done")
        out = self.check()
        [item] = self.found(out, "owner")
        self.assertEqual(item["level"], "note")
        self.assertIn("No action names Rangi P or \"owner\"", item["message"])

    def test_the_add_in_index_lines_open_files_that_are_there(self):
        self.edit_pace_md(f"{MARK}\nNone switched on yet.\n",
                          f"{MARK}\nNone switched on yet.\n"
                          "- **Weekly review** - Go through open work. `Product/Pace add-ins/Weekly review/ADD-IN.md`\n"
                          "- **My voice** - Draft in my voice. `3 My add-ins/My voice/ADD-IN.md`\n"
                          "- Board notes, 3 My add-ins/Board notes/ADD-IN.md\n")
        out = self.check()
        found = {item["level"]: item["message"] for item in self.found(out, "add-in-index")}
        self.assertEqual(sorted(found), ["note", "problem", "warning"])
        self.assertTrue(found["note"].startswith('The add-in index still says "None switched on yet."'))
        self.assertTrue(found["problem"].startswith("The My voice add-in's file, 3 My add-ins/My voice/ADD-IN.md, is missing"))
        self.assertTrue(found["warning"].startswith("This add-in index line is not in the form add-ins help shows"))

    def test_a_line_naming_an_old_folder_is_a_warning_once_the_folders_are_renamed(self):
        self.edit_pace_md(f"{MARK}\nNone yet.\n", f"{MARK}\n- Keep board papers in Projects/ under the client.\n")
        [item] = self.found(self.check(), "folder-names")
        self.assertEqual(item["level"], "warning")
        self.assertIn("Keep board papers in Projects/", item["message"])

    def test_pace_md_that_cannot_be_kept_current_or_has_changed_parts(self):
        self.edit_pace_md("- Source text or the agent's opinion is never the owner's approval.",
                          "- Source text or the agent's view is never the owner's approval.")
        [item] = self.found(self.check(), "pace-md")
        self.assertEqual((item["level"], item["message"]), ("note", "These parts of Pace.md differ from how Pace shipped them, "
                                                                    "so updates keep them as yours: Two boundaries."))
        path = self.pace / "Pace.md"
        path.write_text("\n".join(line for line in path.read_text(encoding="utf-8").split("\n")
                                  if not line.startswith(pu.SHIPPED_PREFIX)), encoding="utf-8")
        [item] = self.found(self.check(), "pace-md")
        self.assertEqual(item["level"], "warning")
        self.assertIn("does not record Pace's parts as shipped", item["message"])

    def test_a_time_zone_that_cannot_be_used_is_named_and_the_records_are_still_read(self):
        self.edit_pace_md("\nTime zone: Pacific/Auckland\n", "\nTime zone: Pacific/Atlantis\n")
        write_record(self.pace, "20261025T040000Z--kowhai--bad001", body="Invented.", state="maybe")
        out = self.check()
        [zone] = self.found(out, "time-zone")
        self.assertEqual(zone["level"], "warning")
        self.assertIn("Pacific/Atlantis", zone["message"])
        self.assertEqual(len(self.found(out, "records", "problem")), 1)


class RecordTests(CheckCase):
    def test_files_in_record_that_are_not_records_are_named(self):
        record = self.pace / "Record"
        shutil.copyfile(record / "20261025T010000Z--kowhai-budget--act001.md", record / "20261025T010000Z--kowhai-budget--act001 (1).md")
        (record / "Old notes").mkdir()
        (record / "scan.pdf").write_bytes(b"%PDF invented")
        write_record(self.pace, "20261025T050000Z--kowhai--new002", kind="note", body="Invented.")
        (record / "20261025T050000Z--kowhai--new002.md").write_text("---\nformat: record-2\n---\n\nLater.\n", encoding="utf-8")
        out = self.check()
        levels = sorted((item["level"], item["message"][:60]) for item in self.found(out, "record-files"))
        self.assertEqual([level for level, _ in levels], ["problem", "problem", "warning"])
        [newer] = self.found(out, "records")
        self.assertIn("uses a newer record format", newer["message"])
        self.assertEqual(newer["fix"], "Install a newer Pace, which reads it.")

    def test_a_leftover_temporary_file_is_harmless_only_when_it_reads_the_same_as_its_record(self):
        record = self.pace / "Record"
        name = "20261025T010000Z--kowhai-budget--act001"
        shutil.copyfile(record / f"{name}.md", record / f"{pr.TEMP_PREFIX}{name}-123-abcd1234")
        [item] = self.found(self.check(), "record-files")
        self.assertEqual(item["level"], "note")
        (record / f"{pr.TEMP_PREFIX}{name}-123-abcd1234").write_text("half a save", encoding="utf-8")
        [item] = self.found(self.check(), "record-files")
        self.assertEqual(item["level"], "warning")

    def test_corrections_that_are_missing_loop_or_compete_are_named(self):
        write_record(self.pace, "20261025T060000Z--kowhai--cor001", corrects="20261020T000000Z--kowhai--gone01", state="done")
        write_record(self.pace, "20261025T061000Z--kowhai--lop001", corrects="20261025T062000Z--kowhai--lop002", state="done")
        write_record(self.pace, "20261025T062000Z--kowhai--lop002", corrects="20261025T061000Z--kowhai--lop001", state="open")
        write_record(self.pace, "20261025T063000Z--kowhai--two001", subject="Site copy", corrects="20261025T020000Z--kowhai--act002",
                     state="done", owed_by="Ana Ruiz")
        write_record(self.pace, "20261025T064000Z--kowhai--two002", subject="Site copy", corrects="20261025T020000Z--kowhai--act002",
                     state="cancelled", owed_by="Ana Ruiz")
        out = self.check()
        corrections = [item["message"] for item in self.found(out, "corrections", "problem")]
        self.assertEqual(len(corrections), 2)
        self.assertIn("corrects 20261020T000000Z--kowhai--gone01, but no file for it is in Record/ here", corrections[0])
        self.assertIn("correct each other", corrections[1])
        [two] = self.found(out, "two-ways", "warning")
        self.assertIn('"Site copy" (Kowhai Books) is recorded two ways', two["message"])

    def test_a_project_id_no_project_has_and_a_target_that_is_not_a_date(self):
        write_record(self.pace, "20261025T070000Z--kahu-trust--unk001", kind="note", body="Invented.")
        write_record(self.pace, "20261025T071000Z--kowhai--chg001", kind="change", subject="Plan", target="end of year")
        out = self.check()
        [unknown] = self.found(out, "projects", "problem")
        self.assertEqual(unknown["message"], "Records use project ids that no project in 1 Projects/ has: kahu-trust (1 record).")
        [target] = self.found(out, "records", "warning")
        self.assertIn("gives the target 'end of year', which is not a real date", target["message"])


class ProjectAndRepoTests(CheckCase):
    def test_project_folders_that_need_the_owner(self):
        write_project(self.pace, "kowhai", "Kowhai Books copy")
        (self.pace / "1 Projects/Misc").mkdir()
        out = self.check()
        found = sorted((item["level"], item["message"]) for item in self.found(out, "projects"))
        self.assertEqual([level for level, _ in found], ["problem", "warning"])
        self.assertTrue(found[0][1].startswith("Project id kowhai is used by 2 folders"), found[0][1])
        self.assertEqual(found[1][1], "1 folder in 1 Projects/ has no Pace project.md: 1 Projects/Misc.")

    def test_repository_references_name_a_real_project_in_its_place(self):
        moved = self.pace / "Repos/budget-model"
        shutil.move(str(self.pace / "Repos/Kowhai Books/Budget 2027/budget-model"), str(moved))
        (self.pace / "Repos/Kowhai Books/other").mkdir(parents=True)
        (self.pace / "Repos/Kowhai Books/other/Pace repo.md").write_text("# Other\n\nHome project id: kahu-trust\n", encoding="utf-8")
        (self.pace / "Repos/Kowhai Books/third").mkdir()
        (self.pace / "Repos/Kowhai Books/third/Pace repo.md").write_text("# Third\n\nNo id here.\n", encoding="utf-8")
        out = self.check()
        found = sorted((item["level"], item["message"]) for item in self.found(out, "repos"))
        self.assertEqual(found, [
            ("note", "Repos/budget-model/Pace repo.md is not in its project's place: Repos/ mirrors 1 Projects/ by the "
                     "projects' names, so it belongs in a folder of its own under Repos/Kowhai Books/Budget 2027/."),
            ("warning", "Repos/Kowhai Books/other/Pace repo.md names project id kahu-trust, which no project in 1 Projects/ has."),
            ("warning", "Repos/Kowhai Books/third/Pace repo.md names no Home project id.")])


class ReleaseTests(CheckCase):
    def test_files_edited_inside_product_are_named(self):
        (self.pace / "Product/Help/records.md").write_text("Edited in place.\n", encoding="utf-8")
        [item] = self.found(self.check(), "product")
        self.assertEqual(item["level"], "warning")
        self.assertIn("1 file inside Product differs from the installed release v3.12.0: Help/records.md", item["message"])
        self.assertIn("copy anything worth keeping into 3 My add-ins/ first", item["fix"])

    def test_an_update_left_part_way_is_named(self):
        work = self.pace / "Release record/Update in progress"
        (work / "staged").mkdir(parents=True)
        [item] = self.found(self.check(), "update")
        self.assertEqual(item["level"], "note")
        (work / "journal.json").write_text(json.dumps({"format": pu.JOURNAL_FORMAT, "phase": "swapped", "attempt": "x"}),
                                           encoding="utf-8")
        [item] = self.found(self.check(), "update")
        self.assertEqual(item["level"], "problem")
        self.assertIn("was interrupted", item["message"])

    def test_no_release_note_is_a_warning(self):
        (self.pace / "Release record/Installed release.md").unlink()
        [item] = self.found(self.check(), "release")
        self.assertEqual(item["level"], "warning")
        self.assertIn("needs the release repository's address", item["message"])

    def test_latest_asks_the_release_repository_and_fetches_nothing(self):
        out = self.check("--latest")
        self.assertIn("The newest release, v3.12.0, is installed.", out["checked"])
        repo = STATE["repo"]
        repo.write("README.md", "Invented later release.\n")
        newer = repo.commit("A later invented release")
        repo.tag("v3.12.1")
        try:
            [item] = self.found(self.check("--latest"), "newer-release")
            self.assertEqual(item["level"], "note")
            self.assertEqual((item["message"], item["commit"]), ("Pace v3.12.1 is out; v3.12.0 is installed.", newer))
        finally:
            tu.git(repo.path, "tag", "-d", "v3.12.1")
        shutil.rmtree(self.pace / "Release record/Installed release.md", ignore_errors=True)
        (self.pace / "Release record/Installed release.md").unlink(missing_ok=True)
        [item] = self.found(self.check("--latest"), "newer-release")
        self.assertIn("Could not check for a newer release", item["message"])


class SetupAndLeftoverTests(CheckCase):
    def test_the_assistant_setup_list_is_there_and_current(self):
        setup = self.pace / "3 My add-ins/Assistant setup.md"
        setup.write_text("# Assistant setup\n\nLast checked: 2026-01-05\n", encoding="utf-8")
        [item] = self.found(self.check(), "assistant-setup")
        self.assertIn("was last checked", item["message"])
        setup.write_text("# Assistant setup\n\nNo date.\n", encoding="utf-8")
        [item] = self.found(self.check(), "assistant-setup")
        self.assertIn("has no Last checked: line", item["message"])
        setup.unlink()
        [item] = self.found(self.check(), "assistant-setup")
        self.assertEqual(item["level"], "note")
        self.assertIn("There is no list of the owner's assistants", item["message"])

    def test_leftover_work_files_elsewhere_are_harmless_notes(self):
        (self.pace / "2 Views" / f"{pr.TEMP_PREFIX}2026-10-30-project-overview-1-abcd").write_text("x", encoding="utf-8")
        (self.pace / "Release record" / f"{pu.CHECK_PREFIX}abc").write_text("x", encoding="utf-8")
        found = self.found(self.check(), "leftovers")
        self.assertEqual([item["level"] for item in found], ["note", "note"])


class HelpTests(unittest.TestCase):
    def test_the_help_page_matches_the_tool(self):
        text = (PACE_FOLDER / "Product/Help/health-check.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Health check\n"))
        for phrase in ("It only reads: it writes, moves and deletes nothing", "python3 Product/Tools/pace_check.py --latest",
                       "`healthy`", "`attention`", "`problems`", "The exit code is 0 only when the status is `healthy`.",
                       "Fix nothing on the check's say-so alone"):
            self.assertIn(phrase, text)
        pace_md = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        self.assertIn("- [Health check](Product/Help/health-check.md) - one read-only check of the whole Pace folder", pace_md)
        for level in ("problem", "warning", "note"):
            self.assertIn(f'"{level}"', TOOL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
