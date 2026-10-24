"""Record and project checks, using invented data in temporary Pace folders only.

The tool under test is PACE/Product/Tools/pace_record.py. Each test builds a
fresh folder with Record/ and Projects/ and plays one situation through:
ordinary, repeated, clashing, simultaneous, missing and unconfirmed saves, and
the searches that must report them honestly.
"""

from contextlib import redirect_stdout
import contextlib
from pathlib import Path
from unittest import mock
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
TOOL = PACE_FOLDER / "Product/Tools/pace_record.py"
HELP = PACE_FOLDER / "Product/Help"
EXAMPLE = ROOT / "example"

_spec = importlib.util.spec_from_file_location("pace_record", TOOL)
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

CLIENT = "kowhai-books"
BUDGET = "kowhai-budget"
GARDEN = "garden-plans"
NZ = "+13:00"


def at(day=23, hour=11, minute=15, month=10):
    return f"2026-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00{NZ}"


class PaceFolder(unittest.TestCase):
    """A temporary, invented Pace folder with a client, one project inside it and one on its own."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pace = Path(self._tmp.name) / "Invented Pace"
        (self.pace / "Record").mkdir(parents=True)
        (self.pace / "Projects").mkdir()
        self.record = self.pace / "Record"
        for args in (
            ("--id", CLIENT, "--name", "Kowhai Books"),
            ("--id", BUDGET, "--name", "Budget 2027", "--parent", CLIENT),
            ("--id", GARDEN, "--name", "Garden plans"),
        ):
            out, code = self.run_tool("project-new", *args, "--by", "Test agent")
            self.assertEqual(out["status"], "saved", out)

    def tearDown(self):
        self._tmp.cleanup()

    def run_tool(self, *args):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = pr.main(["--pace", str(self.pace), *args])
        return json.loads(buffer.getvalue()), code

    def new_request(self, project=BUDGET, when=None):
        out, code = self.run_tool("new-request", "--project", project, *(("--at", when) if when else ()))
        self.assertEqual(code, 0, out)
        return out["request"]

    def save(self, request=None, when=None, project=BUDGET, kind="decision", subjects=("October close",),
             origin="owner", words="Let's close October on the 5th.", body="October close moves to 5 November.",
             extra=()):
        when = when or at()
        request = request or self.new_request(project, when)
        args = ["create", "--request", request, "--created", when, "--project", project, "--kind", kind,
                "--from", origin, "--by", "Test agent", "--body", body]
        for subject in subjects:
            args += ["--subject", subject]
        if words is not None:
            args += ["--words", words]
        args += list(extra)
        out, code = self.run_tool(*args)
        return request, out, code

    def write_raw(self, name, text, encoding="utf-8"):
        path = self.record / name
        path.write_bytes(text.encode(encoding))
        return path

    def raw_record(self, request, body, corrects=None, kind="decision", fmt="record-1", extra=""):
        project = pr.REQUEST.match(request).group(2) if pr.REQUEST.match(request) else BUDGET
        lines = ["---", f"format: {fmt}", f"request: {request}", f"created: {at()}", f"project: {project}",
                 f"kind: {kind}", "subject: October close", "from: agent", "by: Hand-written test"]
        if corrects:
            lines.append(f"corrects: {corrects}")
        if extra:
            lines.append(extra)
        return "\n".join(lines + ["---", "", body, ""])

    def record_files(self):
        return sorted(p.name for p in self.record.iterdir())

    def failing_read(self, request, outcome):
        """Make reading one record file fail (or give other bytes); every other read works."""
        real = pr.read_back

        def read(path):
            if path.name == f"{request}.md" and path.parent == self.record:
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
            return real(path)
        return mock.patch.object(pr, "read_back", side_effect=read)


class SavingTests(PaceFolder):
    def test_saved_and_read_back(self):
        request, out, code = self.save()
        self.assertEqual((out["status"], code), ("saved", 0))
        self.assertIn("read back", out["message"])
        self.assertIn("cloud", out["message"])  # local read-back is not a cloud arrival claim
        path = self.record / f"{request}.md"
        self.assertEqual(self.record_files(), [path.name])
        self.assertEqual(out["sha256"], pr.sha256(path.read_bytes()))
        read, code = self.run_tool("read", "--request", request)
        self.assertEqual((read["status"], code), ("found", 0))
        record = read["record"]
        self.assertEqual(record["words"], "Let's close October on the 5th.")
        self.assertEqual(record["from"], "owner")
        self.assertEqual(record["project"], BUDGET)
        self.assertNotIn("problems", record)

    def test_retry_with_the_same_request_writes_nothing_new(self):
        request, first, _ = self.save()
        before = (self.record / f"{request}.md").read_bytes()
        _, again, code = self.save(request=request)
        self.assertEqual((again["status"], code), ("already-saved", 0))
        self.assertIn("Nothing new was written", again["message"])
        self.assertEqual(self.record_files(), [f"{request}.md"])
        self.assertEqual((self.record / f"{request}.md").read_bytes(), before)

    def test_retry_written_in_another_time_zone_is_the_same_save(self):
        request, _, _ = self.save(when="2026-10-22T22:15:00Z")
        _, again, code = self.save(request=request, when="2026-10-23T11:15:00+13:00")
        self.assertEqual((again["status"], code), ("already-saved", 0))

    def test_reused_request_with_different_content_is_a_conflict_and_nothing_moves(self):
        request, _, _ = self.save()
        before = (self.record / f"{request}.md").read_bytes()
        _, clash, code = self.save(request=request, words="Close on the 6th.", body="October close moves to 6 November.")
        self.assertEqual((clash["status"], code), ("conflict", 1))
        self.assertIn("Nothing was overwritten or renamed", clash["message"])
        self.assertEqual(set(clash["differs"]), {"words", "text"})
        self.assertEqual(self.record_files(), [f"{request}.md"])
        self.assertEqual((self.record / f"{request}.md").read_bytes(), before)

    def test_a_request_is_needed_before_saving(self):
        out, code = self.run_tool("create", "--project", BUDGET, "--kind", "note", "--subject", "x", "--from",
                                  "agent", "--by", "Test agent", "--body", "No request id given.")
        self.assertEqual((out["status"], code), ("not-saved", 1))
        self.assertEqual(self.record_files(), [])

    def test_provenance_and_required_fields_are_enforced(self):
        cases = {
            "owner without words": dict(words=None),
            "person without who": dict(origin="person"),
            "source without a source": dict(origin="source", words=None),
            "figure without a definition": dict(kind="figure", extra=("--value", "41200", "--period", "2026-09")),
            "empty text": dict(body="   "),
            "no subject": dict(subjects=()),
            "state on a non-action": dict(extra=("--state", "done")),
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                _, out, code = self.save(**overrides)
                self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertEqual(self.record_files(), [])

    def test_a_value_line_of_three_hyphens_is_not_saved_rather_than_misread(self):
        # Such a line would end the header early: the save used to say saved, then read back invalid.
        _, out, code = self.save(words="Agenda\n---\nItem two")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("words has a line that is just '---'", out["message"])
        self.assertEqual(self.record_files(), [])
        # The same lines in the text below the header save and read back unchanged and valid.
        request, out, code = self.save(body="Agenda\n---\nItem two")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        read, code = self.run_tool("read", "--request", request)
        self.assertEqual((read["status"], code), ("found", 0), read)
        self.assertEqual(read["record"]["body"], "Agenda\n---\nItem two")

    def test_ordinary_create_cannot_make_a_confirmation_or_approval(self):
        for kind in ("confirmation", "approval"):
            with self.subTest(kind):
                _, out, _ = self.save(kind=kind)
                self.assertEqual(out["status"], "not-saved")
                self.assertIn("confirm" if kind == "confirmation" else "later help", out["message"])
        self.assertEqual(self.record_files(), [])

    def test_unknown_project_is_refused_unless_allowed(self):
        _, out, _ = self.save(project="no-such-project")
        self.assertEqual(out["status"], "not-saved")
        self.assertIn("not defined", out["message"])
        _, out, code = self.save(project="no-such-project", extra=("--allow-unknown-project",))
        self.assertEqual((out["status"], code), ("saved", 0))
        found, _ = self.run_tool("find", "--project", "no-such-project")
        self.assertIn("unknown-project", {issue["type"] for issue in found["issues"]})

    def test_a_record_without_a_project(self):
        _, out, code = self.save(project="none", subjects=("Reading list",), body="Owner wants to read about forecasting.")
        self.assertEqual((out["status"], code), ("saved", 0))

    def test_missing_record_folder_is_not_saved(self):
        shutil.rmtree(self.record)
        _, out, code = self.save(request=f"20261022T221500Z--{BUDGET}--abc123")
        self.assertEqual((out["status"], code), ("not-saved", 1))
        self.assertIn("Record/ was not found", out["message"])
        self.assertFalse(self.record.exists())

    def test_write_failure_is_not_saved(self):
        with mock.patch.object(pr, "place_new", side_effect=PermissionError("access denied")):
            _, out, code = self.save()
        self.assertEqual((out["status"], code), ("not-saved", 1))
        self.assertEqual(self.record_files(), [])

    def test_extra_fields_and_source_files_are_kept(self):
        source = self.pace / "Projects/Kowhai Books/Budget 2027/Documents/September pack.txt"
        source.write_text("Invented September pack: sales 41,200.\n", encoding="utf-8")
        request, out, _ = self.save(kind="figure", origin="source", words=None, subjects=("Sales",),
                                    body="Sales for September as shown in the pack.",
                                    extra=("--source-file", str(source), "--value", "41200", "--unit", "NZD",
                                           "--period", "2026-09", "--definition", "Invented sales total",
                                           "--field", "later-field=kept as is"))
        self.assertEqual(out["status"], "saved", out)
        read, _ = self.run_tool("read", "--request", request)
        fields = read["record"]["fields"]
        self.assertEqual(fields["later-field"], ["kept as is"])
        expected = f"Projects/Kowhai Books/Budget 2027/Documents/September pack.txt sha256:{pr.sha256(source.read_bytes())}"
        self.assertEqual(fields["source"], [expected])

    def test_spec_file_gives_the_same_record(self):
        request = self.new_request(when=at())
        spec = Path(self._tmp.name) / "spec.json"
        spec.write_text(json.dumps({
            "request": request, "created": at(), "project": BUDGET, "kind": "action",
            "subject": ["Send draft budget"], "from": "owner", "words": "Remind me to send Aroha the draft.",
            "by": "Test agent", "due": "2026-11-05", "owed-by": "Owner", "for": "Aroha (invented)",
            "body": "Send the draft budget to Aroha.\nInclude the invented staffing tab.",
        }), encoding="utf-8")
        out, code = self.run_tool("create", "--spec", str(spec))
        self.assertEqual((out["status"], code), ("saved", 0), out)
        again, code = self.run_tool("create", "--spec", str(spec))
        self.assertEqual((again["status"], code), ("already-saved", 0))


class UnconfirmedTests(PaceFolder):
    def test_read_back_failure_is_placed_but_not_confirmed(self):
        request = self.new_request(when=at())
        with self.failing_read(request, OSError("file is offline")):
            _, out, code = self.save(request=request)
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertIn("not confirmed", out["message"])
        self.assertNotIn("Saved", out["message"])
        # Later, a read confirms it, and a retry recognises it rather than duplicating it.
        read, code = self.run_tool("read", "--request", request)
        self.assertEqual((read["status"], code), ("found", 0))
        _, again, code = self.save(request=request)
        self.assertEqual((again["status"], code), ("already-saved", 0))
        self.assertEqual(self.record_files(), [f"{request}.md"])

    def test_read_back_that_differs_is_not_confirmed(self):
        request = self.new_request(when=at())
        with self.failing_read(request, b"---\nsomething else\n---\n"):
            _, out, code = self.save(request=request)
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))

    def test_interrupted_write_is_not_confirmed_and_retry_does_not_overwrite(self):
        request = self.new_request(when=at())
        partial = b"---\nformat: record-1\nrequest: " + request.encode()

        def interrupted(path, data):
            path.write_bytes(partial)
            raise pr.PartialPlacement("disk full")

        with mock.patch.object(pr, "place_new", side_effect=interrupted):
            _, out, code = self.save(request=request)
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertIn("may be incomplete", out["message"])
        _, again, code = self.save(request=request)
        self.assertEqual((again["status"], code), ("conflict", 1))
        self.assertEqual((self.record / f"{request}.md").read_bytes(), partial)
        found, _ = self.run_tool("find", "--project", BUDGET)
        self.assertIn("damaged", {issue["type"] for issue in found["issues"]})
        self.assertFalse(found["coverage"]["complete"])

    def test_existing_file_that_cannot_be_read_is_not_confirmed(self):
        request, _, _ = self.save()
        with self.failing_read(request, OSError("not downloaded")):
            _, out, code = self.save(request=request)
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertIn("Nothing was overwritten", out["message"])

    def test_a_direct_write_that_fails_part_way_is_never_called_saved(self):
        self.write_raw(".pace-tmp-from-an-earlier-save", "kept")  # so this save writes the record directly
        with mock.patch("os.fsync", side_effect=OSError(28, "No space left on device")):
            request, out, code = self.save()
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertIn("may be incomplete", out["message"])
        self.assertEqual(self.record_files(), [".pace-tmp-from-an-earlier-save", f"{request}.md"])

    def test_a_hand_placed_record_can_be_confirmed_later(self):
        request = f"20261022T221500Z--{BUDGET}--hand01"
        self.write_raw(f"{request}.md", self.raw_record(request, "Placed by a host with only a create receipt."))
        read, code = self.run_tool("read", "--request", request)
        self.assertEqual((read["status"], code), ("found", 0))


class CreateOnlyHostTests(PaceFolder):
    """A folder that lets files be created but not deleted, as some hosts allow."""

    def no_delete(self):
        def refuse(path, *args, **kwargs):
            raise PermissionError(13, "Deleting is not allowed here", str(path))
        return mock.patch("os.unlink", side_effect=refuse)

    def temp_files(self, folder=None):
        return sorted(p.name for p in (folder or self.record).iterdir() if p.name.startswith(pr.TEMP_PREFIX))

    def test_a_normal_host_keeps_no_temporary_file_and_says_nothing_of_one(self):
        request, out, code = self.save()
        self.assertEqual((out["status"], code), ("saved", 0))
        self.assertNotIn("kept_temp_files", out)
        self.assertNotIn("temporary", out["message"])
        self.assertEqual(self.record_files(), [f"{request}.md"])

    def test_a_temporary_file_that_cannot_be_deleted_is_reported_and_later_saves_make_none(self):
        notes = (("First invented note.", "October close"), ("Second invented note.", "November close"))
        saved = []
        with self.no_delete():
            for body, subject in notes:
                request, out, code = self.save(body=body, subjects=(subject,))
                self.assertEqual((out["status"], code), ("saved", 0), out)
                saved.append((request, out))
                kept = self.temp_files()
                self.assertEqual(len(kept), 1, kept)  # the second save made no temporary file
        first, second = saved[0][1], saved[1][1]
        self.assertEqual(first["kept_temp_files"], [f"Record/{kept[0]}"])
        self.assertIn(f"Record/{kept[0]}", first["message"])
        self.assertIn("harmless", first["message"])
        self.assertIn("someone with delete rights can delete it", first["message"])
        self.assertNotIn("kept_temp_files", second)
        for (request, out), (body, _) in zip(saved, notes):
            read, code = self.run_tool("read", "--request", request)
            self.assertEqual((read["status"], code), ("found", 0))
            self.assertEqual(read["record"]["body"], body)
            self.assertEqual(out["sha256"], pr.sha256((self.record / f"{request}.md").read_bytes()))
        found, _ = self.run_tool("find", "--project", BUDGET)
        issue = [i for i in found["issues"] if i["type"] == "unfinished-save"]
        self.assertEqual([i["file"] for i in issue], kept)
        self.assertIn("someone with delete rights can delete it", issue[0]["message"])

    def test_a_new_project_there_makes_no_temporary_file(self):
        with self.no_delete():
            self.save()  # keeps one temporary file in Record/
            out, code = self.run_tool("project-new", "--id", "harbour-walk", "--name", "Harbour walk", "--by", "Test agent")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertNotIn("kept_temp_files", out)
        self.assertEqual(self.temp_files(self.pace / "Projects/Harbour walk"), [])

    def test_a_failed_save_still_names_the_temporary_file_it_could_not_delete(self):
        with self.no_delete(), mock.patch("os.fsync", side_effect=OSError(28, "No space left on device")):
            _, out, code = self.save()
        self.assertEqual((out["status"], code), ("not-saved", 1))
        kept = self.temp_files()
        self.assertEqual(self.record_files(), kept)
        self.assertEqual(out["kept_temp_files"], [f"Record/{kept[0]}"])


class SimultaneousTests(PaceFolder):
    def launch(self, argument_lists):
        env = {k: v for k, v in os.environ.items() if k != "PACE_FOLDER"}
        procs = [subprocess.Popen([sys.executable, str(TOOL), "--pace", str(self.pace), *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
                 for args in argument_lists]
        results = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=60)
            self.assertEqual(stderr, "")
            results.append((json.loads(stdout), proc.returncode))
        return results

    def create_args(self, request, body, words="Invented words."):
        return ["create", "--request", request, "--project", BUDGET, "--kind", "note", "--subject", "Load test",
                "--from", "owner", "--words", words, "--by", "Test agent", "--body", body]

    def test_simultaneous_different_records_are_all_saved(self):
        requests = [self.new_request() for _ in range(12)]
        results = self.launch([self.create_args(r, f"Invented note number {i}.") for i, r in enumerate(requests)])
        self.assertEqual([out["status"] for out, _ in results], ["saved"] * 12)
        self.assertEqual(self.record_files(), sorted(f"{r}.md" for r in requests))
        found, _ = self.run_tool("find", "--project", BUDGET, "--limit", "50")
        self.assertEqual(len(found["records"]), 12)
        self.assertEqual(found["issues"], [])
        self.assertTrue(found["coverage"]["complete"])

    def test_simultaneous_retries_of_one_request_leave_one_file(self):
        request = self.new_request()
        results = self.launch([self.create_args(request, "The same invented note.")] * 8)
        statuses = sorted(out["status"] for out, _ in results)
        self.assertEqual(statuses, ["already-saved"] * 7 + ["saved"])
        self.assertTrue(all(code == 0 for _, code in results))
        self.assertEqual(self.record_files(), [f"{request}.md"])

    def test_simultaneous_different_content_for_one_request_never_overwrites(self):
        request = self.new_request()
        bodies = [f"Competing invented version {i}." for i in range(6)]
        results = self.launch([self.create_args(request, body) for body in bodies])
        statuses = [out["status"] for out, _ in results]
        self.assertEqual(sorted(statuses), ["conflict"] * 5 + ["saved"])
        winner = bodies[statuses.index("saved")]
        self.assertEqual(self.record_files(), [f"{request}.md"])
        self.assertIn(winner, (self.record / f"{request}.md").read_text(encoding="utf-8"))
        for (out, code), status in zip(results, statuses):
            if status == "conflict":
                self.assertEqual(code, 1)

    def test_same_content_saved_twice_at_once_is_reported(self):
        first = self.new_request()
        second = self.new_request()
        original = pr.place_new

        def race(path, data):
            # The other save lands just before ours, after both checked for duplicates.
            other = data.decode().replace(first, second).encode()
            (path.parent / f"{second}.md").write_bytes(other)
            return original(path, data)

        with mock.patch.object(pr, "place_new", side_effect=race):
            _, out, code = self.save(request=first)
        self.assertEqual((out["status"], code), ("saved", 0))
        self.assertEqual(out["duplicates"], [second])
        self.assertIn("Ask the owner which to keep", out["message"])
        found, _ = self.run_tool("find", "--project", BUDGET)
        duplicate = [i for i in found["issues"] if i["type"] == "possible-duplicate"]
        self.assertEqual(duplicate[0]["requests"], sorted([first, second]))


class DuplicateTests(PaceFolder):
    def test_same_content_under_a_new_request_is_held_back(self):
        first, _, _ = self.save(when=at(day=20))
        _, out, code = self.save(when=at(day=23))
        self.assertEqual((out["status"], code), ("possible-duplicate", 1))
        self.assertEqual(out["duplicates"], [first])
        self.assertEqual(self.record_files(), [f"{first}.md"])
        _, out, code = self.save(when=at(day=23), extra=("--not-a-duplicate",))
        self.assertEqual((out["status"], code), ("saved", 0))
        self.assertEqual(len(self.record_files()), 2)

    def test_records_the_owner_says_are_separate_are_no_longer_flagged(self):
        # --not-a-duplicate used to be kept nowhere, so every later search asked the owner again.
        first, _, _ = self.save()
        second, held, _ = self.save()
        self.assertEqual(held["status"], "possible-duplicate", held)
        _, out, code = self.save(request=second, extra=("--not-a-duplicate",))
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertEqual(self.run_tool("read", "--request", second)[0]["record"]["fields"].get("separate-from"), [first])
        found, _ = self.run_tool("find", "--project", BUDGET)
        self.assertNotIn("possible-duplicate", {issue["type"] for issue in found["issues"]})
        # A third is held back against both, then kept separate from both.
        third, held, _ = self.save()
        self.assertEqual(held["duplicates"], sorted([first, second]))
        _, out, code = self.save(request=third, extra=("--not-a-duplicate",))
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertEqual(self.run_tool("read", "--request", third)[0]["record"]["fields"]["separate-from"],
                         [" ".join(sorted([first, second]))])
        found, _ = self.run_tool("find", "--project", BUDGET)
        self.assertNotIn("possible-duplicate", {issue["type"] for issue in found["issues"]})
        # A copy nobody said was separate is still flagged with each of them.
        copy = f"20261022T230000Z--{BUDGET}--hand01"
        self.write_raw(f"{copy}.md", (self.record / f"{first}.md").read_text(encoding="utf-8").replace(first, copy))
        found, _ = self.run_tool("find", "--project", BUDGET)
        flagged = [issue["requests"] for issue in found["issues"] if issue["type"] == "possible-duplicate"]
        self.assertEqual(flagged, [sorted([first, second, third, copy])])

    def test_same_words_weeks_apart_are_separate_records(self):
        self.save(when=at(day=1))
        _, out, _ = self.save(when=at(day=23))
        self.assertEqual(out["status"], "saved")

    def test_same_content_in_another_project_is_not_a_duplicate(self):
        self.save(project=BUDGET)
        _, out, _ = self.save(project=GARDEN)
        self.assertEqual(out["status"], "saved")


class MissingTests(PaceFolder):
    def test_unknown_request_is_not_found_without_claiming_it_never_existed(self):
        out, code = self.run_tool("read", "--request", f"20261022T221500Z--{BUDGET}--zzzzzz")
        self.assertEqual((out["status"], code), ("not-found", 1))
        self.assertIn("does not show it was never saved", out["message"])

    def test_correction_of_a_missing_record_is_refused(self):
        _, out, code = self.save(kind="withdrawal", extra=("--corrects", f"20261001T000000Z--{BUDGET}--gone00"))
        self.assertEqual((out["status"], code), ("not-saved", 1))
        self.assertIn("was not found", out["message"])

    def test_history_names_a_missing_earlier_record(self):
        gone = f"20261020T000000Z--{BUDGET}--gone00"
        later = f"20261022T000000Z--{BUDGET}--later1"
        self.write_raw(f"{later}.md", self.raw_record(later, "Fixes a record that is no longer here.", corrects=gone))
        out, code = self.run_tool("history", "--request", later)
        self.assertEqual((out["status"], code), ("incomplete", 1))
        self.assertEqual(out["missing"], [gone])
        self.assertIn("incomplete", out["coverage"])

    def test_history_is_incomplete_when_an_unreadable_file_might_be_a_correction(self):
        # It used to give found (exit 0) with a named current account, while a damaged file sat in the project.
        request, _, _ = self.save(when=at(day=20))
        self.write_raw(f"20261021T000000Z--{BUDGET}--broken.md", "No header at all.\n")
        out, code = self.run_tool("history", "--request", request)
        self.assertEqual((out["status"], code), ("incomplete", 1), out)
        self.assertEqual(out["current"], [request])
        self.assertIn("might be a later correction", out["message"])
        # A withdrawal is no more settled while that file is there, and nor is a second copy.
        withdrawal, saved, _ = self.save(when=at(day=22), kind="withdrawal", body="The October close decision no longer stands.",
                                         extra=("--corrects", request))
        self.assertEqual(saved["status"], "saved", saved)
        out, code = self.run_tool("history", "--request", request)
        self.assertEqual((out["status"], code, out["withdrawn_by"]), ("incomplete", 1, [withdrawal]), out)
        (self.record / f"20261021T000000Z--{BUDGET}--broken.md").unlink()
        self.assertEqual(self.run_tool("history", "--request", request)[0]["status"], "withdrawn")
        shutil.copy(self.record / f"{withdrawal}.md", self.record / f"{withdrawal} (1).md")
        out, code = self.run_tool("history", "--request", request)
        self.assertEqual((out["status"], code), ("incomplete", 1), out)

    def test_kept_listing_shows_a_removed_or_changed_record(self):
        kept, _, _ = self.save(subjects=("Kept",), body="This one stays.")
        removed, _, _ = self.save(subjects=("Removed",), body="This one will be removed by hand.")
        changed, _, _ = self.save(subjects=("Changed",), body="This one will be edited by hand.")
        listing = Path(self._tmp.name) / "listing.json"
        out, code = self.run_tool("listing", "--digests", "--save", str(listing))
        self.assertEqual((out["status"], code), ("saved", 0))
        (self.record / f"{removed}.md").unlink()
        path = self.record / f"{changed}.md"
        path.write_text(path.read_text(encoding="utf-8") + "Edited.\n", encoding="utf-8")
        out, code = self.run_tool("listing", "--compare", str(listing))
        self.assertEqual((out["status"], code), ("differs", 1))
        self.assertEqual(out["missing"], [f"{removed}.md"])
        self.assertEqual(out["changed"], [f"{changed}.md"])
        self.assertNotIn(f"{kept}.md", out["missing"] + out["changed"])

    def test_a_kept_listing_always_has_fingerprints_so_an_edit_shows(self):
        # Without --digests a kept listing used to hold sizes only, and compare called an edited record unchanged.
        request, _, _ = self.save()
        listing = Path(self._tmp.name) / "listing.json"
        out, code = self.run_tool("listing", "--save", str(listing))
        self.assertEqual((out["status"], code), ("saved", 0), out)
        path = self.record / f"{request}.md"
        path.write_text(path.read_text(encoding="utf-8") + "Edited.\n", encoding="utf-8")
        out, code = self.run_tool("listing", "--compare", str(listing))
        self.assertEqual((out["status"], code), ("differs", 1), out)
        self.assertEqual(out["changed"], [f"{request}.md"])

    def test_an_older_listing_without_fingerprints_is_never_called_unchanged(self):
        request, _, _ = self.save()
        older = Path(self._tmp.name) / "older-listing.json"
        older.write_text(json.dumps({"format": "record-listing-1", "made": at(),
                                     "files": {f"{request}.md": {"size": 1}}}), encoding="utf-8")
        out, code = self.run_tool("listing", "--compare", str(older))
        self.assertEqual((out["status"], code), ("unchecked", 1), out)
        self.assertEqual(out["unchecked"], [f"{request}.md"])
        self.assertNotIn("unchanged", out["message"])
        self.assertIn("only their presence was checked", out["message"])

    def test_a_listing_is_not_saved_inside_record(self):
        out, _ = self.run_tool("listing", "--save", str(self.record / "listing.json"))
        self.assertEqual(out["status"], "not-saved")
        self.assertEqual(self.record_files(), [])


class ConflictingTests(PaceFolder):
    def test_competing_corrections_are_both_shown(self):
        original, _, _ = self.save(when=at(day=20))
        fix_one, out, _ = self.save(when=at(day=21), words="Make it the 6th.", body="Close moves to 6 November.",
                                    extra=("--corrects", original))
        self.assertEqual(out["status"], "saved")
        # A second device wrote another correction of the same original before syncing.
        fix_two = f"20261021T010000Z--{BUDGET}--devic2"
        self.write_raw(f"{fix_two}.md", self.raw_record(fix_two, "Close moves to 7 November.", corrects=original))
        out, code = self.run_tool("history", "--request", original)
        self.assertEqual((out["status"], code), ("conflict", 1))
        self.assertEqual(sorted(out["current"]), sorted([fix_one, fix_two]))
        self.assertIn("competing-corrections", {issue["type"] for issue in out["issues"]})
        # The tool will not add a third branch by correcting the original again.
        _, refused, _ = self.save(when=at(day=22), words="The 8th.", body="Close moves to 8 November.",
                                  extra=("--corrects", original))
        self.assertEqual(refused["status"], "not-saved")
        self.assertEqual(sorted(refused["corrected_by"]), sorted([fix_one, fix_two]))

    def test_sync_conflict_copies_are_reported(self):
        request, _, _ = self.save()
        shutil.copy(self.record / f"{request}.md", self.record / f"{request} (1).md")
        shutil.copy(self.record / f"{request}.md", self.record / f"{request}-LAPTOP.md")
        out, code = self.run_tool("read", "--request", request)
        self.assertEqual((out["status"], code), ("conflict", 1))
        self.assertEqual(len(out["issues"]), 2)
        found, _ = self.run_tool("find", "--project", BUDGET)
        copies = [i for i in found["issues"] if i["type"] == "conflict-copy"]
        self.assertEqual(len(copies), 2)
        self.assertFalse(found["coverage"]["complete"])

    def test_damaged_mismatched_newer_and_stray_files_are_named(self):
        self.save(body="A sound record.")
        self.write_raw(f"20261022T000000Z--{BUDGET}--broken.md", "No header at all.\n")
        named_wrong = f"20261022T000001Z--{BUDGET}--wrong1"
        self.write_raw(f"{named_wrong}.md", self.raw_record(f"20261022T000001Z--{BUDGET}--other1", "Name and request differ."))
        newer = f"20261022T000002Z--{BUDGET}--newer1"
        self.write_raw(f"{newer}.md", self.raw_record(newer, "From a later format.", fmt="record-2"))
        self.write_raw("notes.txt", "A stray file.\n")
        self.write_raw(".pace-tmp-leftover", "half")
        found, _ = self.run_tool("find", "--project", BUDGET)
        types = {issue["type"] for issue in found["issues"]}
        self.assertTrue({"damaged", "invalid", "newer-format", "unrecognised-file", "unfinished-save"} <= types, types)
        self.assertFalse(found["coverage"]["complete"])
        self.assertIn("not a complete answer", found["coverage"]["statement"])

    def test_a_hand_written_confirmation_without_exact_act_is_not_one(self):
        request = f"20261022T221500Z--{BUDGET}--conf01"
        self.write_raw(f"{request}.md", self.raw_record(request, "Owner approved the close.", kind="confirmation"))
        out, code = self.run_tool("read", "--request", request)
        self.assertEqual((out["status"], code), ("invalid", 1))
        self.assertIn("confirmation needs act", out["message"])
        found, _ = self.run_tool("find", "--project", BUDGET, "--full")
        self.assertIn("confirmation needs act", " ".join(found["records"][0]["problems"]))


class CorrectionTests(PaceFolder):
    def test_a_chain_of_corrections_has_one_current_account(self):
        first, _, _ = self.save(when=at(day=20))
        second, _, _ = self.save(when=at(day=21), body="Close moves to 6 November.", extra=("--corrects", first))
        third, out, _ = self.save(when=at(day=22), body="Close moves to 7 November.", extra=("--corrects", second))
        self.assertEqual(out["status"], "saved")
        for start in (first, second, third):
            with self.subTest(start=start):
                history, code = self.run_tool("history", "--request", start)
                self.assertEqual((history["status"], code), ("found", 0))
                self.assertEqual(history["current"], [third])
                self.assertEqual(len(history["versions"]), 3)
        _, refused, _ = self.save(when=at(day=23), body="Close moves to 9 November.", extra=("--corrects", first))
        self.assertEqual(refused["corrected_by"], [second])
        found, _ = self.run_tool("find", "--project", BUDGET)
        by_request = {r["request"]: r for r in found["records"]}
        self.assertEqual(by_request[first]["corrected_by_seen"], [second])

    def test_withdrawal_leaves_nothing_current(self):
        first, _, _ = self.save(when=at(day=20))
        withdrawal, out, _ = self.save(when=at(day=21), kind="withdrawal", body="Owner says this no longer stands.",
                                       extra=("--corrects", first))
        self.assertEqual(out["status"], "saved")
        history, code = self.run_tool("history", "--request", first)
        self.assertEqual((history["status"], code), ("withdrawn", 0))
        self.assertEqual(history["current"], [])
        self.assertEqual(history["withdrawn_by"], [withdrawal])

    def test_a_follow_up_marked_done(self):
        action, _, _ = self.save(when=at(day=20), kind="action", subjects=("Send draft budget",),
                                 body="Send the invented draft budget.", extra=("--due", "2026-11-05", "--state", "open"))
        done, out, _ = self.save(when=at(day=22), kind="action", subjects=("Send draft budget",),
                                 words="Sent it this morning.", body="Draft budget sent.",
                                 extra=("--corrects", action, "--state", "done", "--due", "2026-11-05"))
        self.assertEqual(out["status"], "saved", out)
        history, _ = self.run_tool("history", "--request", action)
        self.assertEqual(history["current"], [done])
        current = [v for v in history["versions"] if v["request"] == done][0]
        self.assertEqual(current["state"], "done")

    def test_a_correction_stays_in_its_project(self):
        first, _, _ = self.save(project=BUDGET)
        _, out, _ = self.save(project=GARDEN, body="Moved to the garden project.", extra=("--corrects", first))
        self.assertEqual(out["status"], "not-saved")
        self.assertIn("same project", out["message"])


class FindTests(PaceFolder):
    def fill(self, count, project=BUDGET, kind_every=None):
        made = []
        for i in range(count):
            kind = "action" if kind_every and i % kind_every == 0 else "note"
            request, out, _ = self.save(when=at(day=1 + i // 60, hour=9, minute=i % 60), project=project, kind=kind,
                                        subjects=(f"Item {i}",), body=f"Invented item {i} for {project}.")
            self.assertEqual(out["status"], "saved", out)
            made.append(request)
        return made

    def test_pages_cover_everything_once_newest_first(self):
        made = self.fill(45)
        seen, cursor, pages = [], None, []
        while True:
            args = ["find", "--project", BUDGET, "--limit", "20"] + (["--cursor", cursor] if cursor else [])
            page, code = self.run_tool(*args)
            self.assertEqual(code, 0)
            pages.append(page)
            seen += [r["request"] for r in page["records"]]
            cursor = page["next_cursor"]
            if len(pages) == 1:
                # A record saved while paging does not disturb the older pages.
                self.save(when=at(day=30), subjects=("Late arrival",), body="Saved while paging.")
            if not cursor:
                break
        self.assertEqual([len(p["records"]) for p in pages], [20, 20, 5])
        self.assertEqual([p["status"] for p in pages], ["partial", "partial", "found"])
        self.assertEqual(seen, sorted(made, reverse=True))
        self.assertIn("Partial", pages[0]["coverage"]["statement"])
        self.assertFalse(pages[0]["coverage"]["complete"])
        self.assertTrue(pages[-1]["coverage"]["complete"])

    def test_project_search_opens_only_that_project(self):
        self.fill(5, project=BUDGET)
        self.fill(7, project=GARDEN)
        page, _ = self.run_tool("find", "--project", BUDGET)
        self.assertEqual(len(page["records"]), 5)
        self.assertEqual(page["coverage"]["opened"], 5)
        self.assertEqual(page["coverage"]["files_in_record"], 12)

    def test_a_bounded_search_says_it_is_partial_until_finished(self):
        self.fill(30, kind_every=10)
        found, cursor, pages = [], None, 0
        while True:
            args = ["find", "--project", BUDGET, "--kind", "action", "--max-open", "10"]
            page, _ = self.run_tool(*args + (["--cursor", cursor] if cursor else []))
            pages += 1
            self.assertLessEqual(page["coverage"]["opened"], 10)
            found += [r["request"] for r in page["records"]]
            cursor = page["next_cursor"]
            if not cursor:
                break
            self.assertEqual(page["status"], "partial")
        self.assertEqual(len(found), 3)
        self.assertGreaterEqual(pages, 3)

    def test_filters(self):
        self.save(when=at(day=2), subjects=("Staffing",), body="Hire one invented analyst.", words="Hire one.")
        self.save(when=at(day=15), subjects=("Rent",), body="Rent review in December.", words="Review rent.")
        self.save(when=at(day=28), kind="action", subjects=("Rent",), body="Call the invented landlord.",
                  words="Call them.", extra=("--due", "2026-11-02"))
        cases = {
            ("--subject", "rent"): 2,
            ("--text", "landlord"): 1,
            ("--kind", "action"): 1,
            ("--since", "2026-10-10"): 2,
            ("--until", "2026-10-10"): 1,
            ("--since", "2026-10-10", "--until", "2026-10-20"): 1,
            ("--from", "agent"): 0,
        }
        for args, count in cases.items():
            with self.subTest(args=args):
                page, _ = self.run_tool("find", "--project", BUDGET, *args)
                self.assertEqual(len(page["records"]), count)
        page, _ = self.run_tool("find", "--project", BUDGET, "--from", "agent")
        self.assertEqual(page["status"], "none-found")
        self.assertTrue(page["coverage"]["complete"])

    def test_impossible_dates_are_refused_plainly(self):
        # find --since 2026-02-30 used to crash with no result, and a due day of 2026-13-45 was saved.
        for args in (("--since", "2026-02-30"), ("--until", "2026-13-01")):
            with self.subTest(args=args):
                out, code = self.run_tool("find", "--project", BUDGET, *args)
                self.assertEqual((out["status"], code), ("not-read", 1), out)
                self.assertIn("real date", out["message"])
        _, out, code = self.save(kind="action", extra=("--due", "2026-13-45"))
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("due must be a real date", out["message"])
        self.assertEqual(self.record_files(), [])

    def test_hand_written_variations_are_read(self):
        request = f"20261022T221500Z--{BUDGET}--crlf01"
        text = self.raw_record(request, "Written on Windows with a byte order mark.", extra="words: First line\n  second line")
        self.write_raw(f"{request}.md", "﻿" + text.replace("\n", "\r\n"))
        out, code = self.run_tool("read", "--request", request)
        self.assertEqual((out["status"], code), ("found", 0), out)
        self.assertEqual(out["record"]["words"], "First line\nsecond line")


class TimeZoneTests(PaceFolder):
    UTC_MORNING = "2026-10-22T20:00:00+00:00"  # 09:00 on 23 October in Auckland, written by an assistant on UTC

    def setUp(self):
        super().setUp()
        self.cloud, out, _ = self.save(when=self.UTC_MORNING, subjects=("Cloud note",), body="Written on UTC.")
        self.assertEqual(out["status"], "saved", out)

    def pace_md(self, *lines):
        (self.pace / "Pace.md").write_text("# Invented Pace\n\n" + "\n".join(lines) + "\n", encoding="utf-8")

    def found(self, *args):
        page, code = self.run_tool("find", "--project", BUDGET, *args)
        self.assertEqual(code, 0, page)
        return [record["request"] for record in page["records"]], page

    def test_dates_are_compared_in_the_owners_time_zone(self):
        # A record made at 09:00 on 23 October in Auckland by an assistant on UTC was missed by --since 2026-10-23.
        self.pace_md("Time zone: Pacific/Auckland")
        found, page = self.found("--since", "2026-10-23")
        self.assertEqual(found, [self.cloud])
        self.assertEqual(page["time_zone"], "Pacific/Auckland")
        self.assertIn("Pacific/Auckland", page["coverage"]["statement"])
        self.assertEqual(self.found("--until", "2026-10-22")[0], [])
        # The same moment written by an assistant on New Zealand time gives the same answer.
        local, out, _ = self.save(when="2026-10-23T09:00:00+13:00", subjects=("Local note",), body="Written in NZ.")
        self.assertEqual(out["status"], "saved", out)
        self.assertEqual(sorted(self.found("--since", "2026-10-23", "--until", "2026-10-23")[0]), sorted([self.cloud, local]))

    def test_without_a_time_zone_line_each_records_own_date_is_used_and_said(self):
        self.pace_md("No time zone named here.")
        found, page = self.found("--since", "2026-10-23")
        self.assertEqual(found, [])
        self.assertIsNone(page["time_zone"])
        self.assertIn("own written date", page["coverage"]["statement"])
        self.assertEqual(self.found("--until", "2026-10-22")[0], [self.cloud])

    def test_a_time_zone_that_cannot_be_used_is_never_guessed(self):
        def missing_zone(name):
            raise KeyError(name)  # as zoneinfo does on Windows without the tzdata package
        cases = {
            "unknown name": ("Time zone: Mars/Olympus", None),
            "Python 3.8": ("Time zone: Pacific/Auckland", mock.patch.object(pr, "ZoneInfo", None)),
            "no time zone data": ("Time zone: Pacific/Auckland", mock.patch.object(pr, "ZoneInfo", side_effect=missing_zone)),
            "two zones": ("Time zone: Pacific/Auckland\nTime zone: Europe/London", None),
        }
        for label, (line, patch) in cases.items():
            with self.subTest(label):
                self.pace_md(line)
                with patch or contextlib.nullcontext():
                    page, code = self.run_tool("find", "--project", BUDGET, "--since", "2026-10-23")
                    self.assertEqual((page["status"], code), ("not-read", 1), page)
                    self.assertIn("Could not use your time zone", page["message"])
                    # A search with no dates does not need the zone.
                    self.assertEqual(self.run_tool("find", "--project", BUDGET)[0]["status"], "found")


class ProjectTests(PaceFolder):
    def test_parent_and_project_with_stable_ids(self):
        out, code = self.run_tool("projects")
        self.assertEqual((out["status"], code), ("listed", 0))
        by_id = {p["id"]: p for p in out["projects"]}
        self.assertEqual(by_id[BUDGET]["parent"], CLIENT)
        self.assertEqual(by_id[BUDGET]["folder"], "Projects/Kowhai Books/Budget 2027")
        self.assertEqual(by_id[GARDEN]["parent"], "none")
        for project in by_id.values():
            self.assertTrue((self.pace / project["folder"] / "Documents").is_dir())

    def test_retry_and_refusals(self):
        out, code = self.run_tool("project-new", "--id", BUDGET, "--name", "Budget 2027", "--parent", CLIENT, "--by", "Test agent")
        self.assertEqual((out["status"], code), ("already-saved", 0))
        cases = {
            "id already used": ("--id", BUDGET, "--name", "Another budget", "--parent", CLIENT),
            "parent unknown": ("--id", "orphan", "--name", "Orphan", "--parent", "nobody"),
            "bad id": ("--id", "Not An Id", "--name", "Bad"),
            "reserved id": ("--id", "none", "--name", "Nothing"),
            "bad folder name": ("--id", "slashed", "--name", "a/b"),
        }
        for label, args in cases.items():
            with self.subTest(label):
                out, code = self.run_tool("project-new", *args, "--by", "Test agent")
                self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertFalse((self.pace / "Projects/Kowhai Books/Another budget").exists())

    def test_projects_can_sit_inside_projects_at_any_depth(self):
        out, code = self.run_tool("project-new", "--id", "kowhai-board-pack", "--name", "Board pack", "--parent", BUDGET,
                                  "--by", "Test agent")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertEqual(out["folder"], "Projects/Kowhai Books/Budget 2027/Board pack")
        out, code = self.run_tool("project-new", "--id", "kowhai-slides", "--name", "Slides", "--parent", "kowhai-board-pack",
                                  "--by", "Test agent")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        listed, code = self.run_tool("projects")
        self.assertEqual((listed["status"], code), ("listed", 0), listed)
        by_id = {p["id"]: p for p in listed["projects"]}
        self.assertEqual(by_id["kowhai-slides"]["parent"], "kowhai-board-pack")
        self.assertEqual(by_id["kowhai-slides"]["folder"], "Projects/Kowhai Books/Budget 2027/Board pack/Slides")
        self.assertTrue((self.pace / by_id["kowhai-slides"]["folder"] / "Documents").is_dir())
        self.assertEqual(listed["folders_without_id"], [])
        # A retry at depth is already saved, and records for the deepest project save like any other.
        again, code = self.run_tool("project-new", "--id", "kowhai-slides", "--name", "Slides", "--parent", "kowhai-board-pack",
                                    "--by", "Test agent")
        self.assertEqual((again["status"], code), ("already-saved", 0), again)
        _, out, code = self.save(project="kowhai-slides")
        self.assertEqual((out["status"], code), ("saved", 0), out)

    def test_a_long_path_is_warned_about_and_the_project_still_made(self):
        name = "A very long project name that goes on and on for quite a while"
        out, code = self.run_tool("project-new", "--id", "long-one", "--name", name, "--parent", BUDGET, "--by", "Test agent")
        self.assertEqual((out["status"], code), ("saved", 0), out)
        self.assertLess(out["path_room"], pr.ROOM_FOR_FILES)
        self.assertIn("Long path:", out["message"])
        self.assertIn("218-character path limit", out["message"])
        self.assertTrue((self.pace / "Projects/Kowhai Books/Budget 2027" / name / "Documents").is_dir())
        short, _ = self.run_tool("project-new", "--id", "short-one", "--name", "Short", "--by", "Test agent")
        self.assertGreaterEqual(short["path_room"], pr.ROOM_FOR_FILES)
        self.assertNotIn("Long path:", short["message"])
        # The Pace folder's own place counts as at least a typical OneDrive place, wherever the tool runs:
        # 218 - 100 for the place - 24 for Projects/Short/Documents - 1 for the separator.
        with mock.patch.object(pr, "TYPICAL_ROOT", 100):
            self.assertEqual(pr.path_room(self.pace, self.pace / "Projects/Short"), 93)

    def test_a_project_named_documents_in_any_case_is_refused(self):
        for name in ("Documents", "documents", "DOCUMENTS"):
            with self.subTest(name):
                out, code = self.run_tool("project-new", "--id", "doc-like", "--name", name, "--parent", CLIENT, "--by", "Test agent")
                self.assertEqual((out["status"], code), ("not-saved", 1), out)

    def test_folders_deep_down_are_read_and_raised(self):
        loose = self.pace / "Projects/Kowhai Books/Budget 2027/Loose notes"
        (loose / "Inside loose").mkdir(parents=True)
        inner = self.pace / "Projects/Kowhai Books/Budget 2027/Holder/Inner"
        inner.mkdir(parents=True)
        (self.pace / "Projects/Kowhai Books/Budget 2027/Holder/Beside").mkdir()
        (self.pace / "Projects/Kowhai Books/Budget 2027/.hidden").mkdir()
        (self.pace / "Projects/Kowhai Books/Budget 2027/documents/kept").mkdir(parents=True)
        (inner / "Pace project.md").write_text(
            "---\nformat: project-1\nid: inner\nparent: kowhai-budget\ncreated: 2026-10-23T11:20:00+13:00\nby: Hand\n---\n",
            encoding="utf-8")
        out, code = self.run_tool("projects")
        self.assertEqual((out["status"], code), ("issues", 1))
        # Named: a folder with no id that holds no project, and one beside a project inside a folder with no id.
        # Not named: what is inside a named folder, a folder that holds a project, dot folders and Documents/ in any case.
        self.assertEqual(sorted(out["folders_without_id"]), ["Projects/Kowhai Books/Budget 2027/Holder/Beside",
                                                             "Projects/Kowhai Books/Budget 2027/Loose notes"])
        found = next(p for p in out["projects"] if p["id"] == "inner")
        self.assertEqual(found["folder"], "Projects/Kowhai Books/Budget 2027/Holder/Inner")
        mismatch = [i["message"] for i in out["issues"] if i.get("id") == "inner"]
        self.assertEqual(mismatch, ["Project inner sits inside Holder, which has no Pace project id."])

    def test_a_folder_that_cannot_be_read_is_named_and_stops_nothing(self):
        locked = self.pace / "Projects/Kowhai Books/Budget 2027/Claude/locked"
        locked.mkdir(parents=True)
        unlisted = self.pace / "Projects/Garden plans/Shut"
        unlisted.mkdir()
        real_exists, real_scandir = Path.exists, os.scandir

        def exists(path, *args, **kwargs):
            if path == locked / pr.PROJECT_FILE:
                raise PermissionError(13, "Permission denied", str(path))
            return real_exists(path, *args, **kwargs)

        def scandir(path="."):
            if Path(path) == unlisted:
                raise PermissionError(13, "Permission denied", str(path))
            return real_scandir(path)

        with mock.patch.object(Path, "exists", exists), mock.patch.object(pr.os, "scandir", scandir):
            out, code = self.run_tool("projects")
            self.assertEqual((out["status"], code), ("issues", 1), out)
            self.assertEqual(sorted(p["id"] for p in out["projects"]), sorted([CLIENT, BUDGET, GARDEN]))
            unreadable = sorted(i["folder"] for i in out["issues"] if i["type"] == "unreadable")
            self.assertEqual(unreadable, ["Projects/Garden plans/Shut", "Projects/Kowhai Books/Budget 2027/Claude/locked"])
            self.assertNotIn("Projects/Garden plans/Shut", out["folders_without_id"])  # it may hold a project
            _, saved, code = self.save()
            self.assertEqual((saved["status"], code), ("saved", 0), saved)

    def test_a_project_behind_folders_with_no_id_is_found_so_its_id_is_not_reused(self):
        old = self.pace / "Projects/Archive/2025/Old client"
        old.mkdir(parents=True)
        (old / "Pace project.md").write_text(
            "---\nformat: project-1\nid: old-client\nparent: none\ncreated: 2026-10-23T11:20:00+13:00\nby: Hand\n---\n",
            encoding="utf-8")
        (self.pace / "Projects/Archive/2024").mkdir()
        out, _ = self.run_tool("projects")
        self.assertEqual(next(p for p in out["projects"] if p["id"] == "old-client")["folder"], "Projects/Archive/2025/Old client")
        self.assertNotIn("Projects/Archive", out["folders_without_id"])
        again, code = self.run_tool("project-new", "--id", "old-client", "--name", "Old client", "--by", "Test agent")
        self.assertEqual((again["status"], code), ("not-saved", 1), again)
        self.assertIn("already used", again["message"])

    def test_a_big_folder_with_no_id_does_not_hide_the_projects_after_it(self):
        out, _ = self.run_tool("project-new", "--id", "aardvark", "--name", "Aardvark", "--by", "Test agent")
        self.assertEqual(out["status"], "saved", out)
        code = self.pace / "Projects/Aardvark/Code"
        for outer in range(30):
            for inner in range(20):
                (code / f"pkg{outer:02d}" / f"mod{inner:02d}").mkdir(parents=True)
        out, code_ = self.run_tool("projects")
        self.assertEqual(sorted(p["id"] for p in out["projects"]), sorted(["aardvark", CLIENT, BUDGET, GARDEN]))
        capped = [i for i in out["issues"] if i["type"] == "too-many-folders"]
        self.assertEqual([i["folder"] for i in capped], ["Projects/Aardvark/Code"])
        self.assertNotIn("Projects/Aardvark/Code", out["folders_without_id"])  # not all of it was checked
        _, saved, status = self.save()
        self.assertEqual((saved["status"], status), ("saved", 0), saved)
        again, status = self.run_tool("project-new", "--id", BUDGET, "--name", "Another budget", "--by", "Test agent")
        self.assertEqual((again["status"], status), ("not-saved", 1), again)

    def test_folders_too_far_down_are_named_not_followed(self):
        chain = self.pace / "Projects/Garden plans" / "/".join(["deep"] * 6)
        chain.mkdir(parents=True)
        with mock.patch.object(pr, "MAX_PROJECT_DEPTH", 4):
            out, code = self.run_tool("projects")
        self.assertIn("too-deep", {i["type"] for i in out["issues"]})
        self.assertEqual(sorted(p["id"] for p in out["projects"]), sorted([CLIENT, BUDGET, GARDEN]))

    def test_a_project_in_a_dot_folder_is_read_and_a_new_one_cannot_start_with_a_dot(self):
        dotted = self.pace / "Projects/.NET upgrade"
        dotted.mkdir()
        (dotted / "Pace project.md").write_text(
            "---\nformat: project-1\nid: net-old\nparent: none\ncreated: 2026-10-23T11:20:00+13:00\nby: Hand\n---\n",
            encoding="utf-8")
        (self.pace / "Projects/Kowhai Books/.git/objects").mkdir(parents=True)  # a system folder, left out
        out, _ = self.run_tool("projects")
        self.assertIn("net-old", {p["id"] for p in out["projects"]})
        self.assertEqual(out["folders_without_id"], [])
        again, code = self.run_tool("project-new", "--id", "net-old", "--name", "Reused", "--by", "Test agent")
        self.assertEqual((again["status"], code), ("not-saved", 1), again)
        dot, code = self.run_tool("project-new", "--id", "dotnet", "--name", ".NET migration", "--parent", CLIENT, "--by", "Test agent")
        self.assertEqual((dot["status"], code), ("not-saved", 1), dot)

    def test_all_the_folders_with_no_id_together_are_limited_too(self):
        for project in ("Projects/Kowhai Books", "Projects/Garden plans"):
            for number in range(4):
                (self.pace / project / f"Loose {number}").mkdir()
        with mock.patch.object(pr, "MAX_UNNAMED_FOLDERS", 5):
            out, _ = self.run_tool("projects")
        self.assertEqual(sorted(p["id"] for p in out["projects"]), sorted([CLIENT, BUDGET, GARDEN]))
        self.assertEqual(len(out["folders_without_id"]), 5)
        self.assertEqual([i["type"] for i in out["issues"]], ["too-many-folders"])

    def test_a_link_back_up_is_stopped_and_a_link_across_shows_the_project_twice(self):
        budget = self.pace / "Projects/Kowhai Books/Budget 2027"
        try:
            (budget / "Up").symlink_to(self.pace / "Projects/Kowhai Books", target_is_directory=True)
            (self.pace / "Projects/Garden plans/Across").symlink_to(budget, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("folder links cannot be made here")
        out, _ = self.run_tool("projects")
        types = {i["type"] for i in out["issues"]}
        self.assertIn("folder-loop", types)
        self.assertIn("duplicate-id", types)  # Budget 2027 is reached at its own place and through the link
        self.assertEqual(sorted(p["folder"] for p in out["projects"] if p["id"] == BUDGET),
                         ["Projects/Garden plans/Across", "Projects/Kowhai Books/Budget 2027"])

    def test_a_project_value_line_of_three_hyphens_is_not_saved(self):
        # It used to save a Pace project.md whose header ended early, so by and the purpose read back wrong.
        out, code = self.run_tool("project-new", "--id", "agenda", "--name", "Agenda", "--purpose", "Invented agenda.",
                                  "--by", "Test agent\n---\nSecond line")
        self.assertEqual((out["status"], code), ("not-saved", 1), out)
        self.assertIn("by has a line that is just '---'", out["message"])
        self.assertFalse((self.pace / "Projects/Agenda").exists())

    def test_renaming_a_folder_keeps_the_id_and_its_records(self):
        request, _, _ = self.save()
        (self.pace / "Projects/Kowhai Books/Budget 2027").rename(self.pace / "Projects/Kowhai Books/Budget FY27")
        out, _ = self.run_tool("projects")
        names = {p["id"]: p["name"] for p in out["projects"]}
        self.assertEqual(names[BUDGET], "Budget FY27")
        found, _ = self.run_tool("find", "--project", BUDGET)
        self.assertEqual([r["request"] for r in found["records"]], [request])
        self.assertNotIn("unknown-project", {i["type"] for i in found["issues"]})

    def test_hand_made_mistakes_are_reported(self):
        clash = self.pace / "Projects/Garden copy"
        clash.mkdir()
        shutil.copy(self.pace / "Projects/Garden plans/Pace project.md", clash / "Pace project.md")
        stray = self.pace / "Projects/Garden plans/Misfiled"
        stray.mkdir()
        (stray / "Pace project.md").write_text(
            "---\nformat: project-1\nid: misfiled\nparent: kowhai-books\ncreated: 2026-10-23T11:20:00+13:00\nby: Hand\n---\n",
            encoding="utf-8")
        (self.pace / "Projects/Loose folder").mkdir()
        out, code = self.run_tool("projects")
        self.assertEqual((out["status"], code), ("issues", 1))
        types = {issue["type"] for issue in out["issues"]}
        self.assertEqual(types, {"duplicate-id", "parent-mismatch"})
        self.assertIn("Projects/Loose folder", out["folders_without_id"])
        out, _ = self.run_tool("project-new", "--id", "new-one", "--name", "Inside garden", "--parent", GARDEN, "--by", "Test agent")
        self.assertEqual(out["status"], "not-saved")  # the parent's id is now ambiguous


class ProjectFieldTests(PaceFolder):
    def test_a_change_can_set_owner_target_and_status(self):
        request, out, code = self.save(kind="change", subjects=("Budget 2027",), words="Ana leads it now.",
                                       body="Ana Ruiz leads the 2027 budget.",
                                       extra=("--owner", "Ana Ruiz", "--target", "2026-11-27", "--status", "Waiting on the sign-off"))
        self.assertEqual((out["status"], code), ("saved", 0), out)
        read, _ = self.run_tool("read", "--request", request)
        record = read["record"]
        self.assertEqual((record["owner"], record["target"], record["status"]),
                         ("Ana Ruiz", "2026-11-27", "Waiting on the sign-off"))
        text = (self.record / f"{request}.md").read_text(encoding="utf-8")
        self.assertLess(text.index("\nowner: "), text.index("\ntarget: "))
        self.assertLess(text.index("\ntarget: "), text.index("\nstatus: "))

    def test_owner_target_and_status_are_checked(self):
        cases = {
            "not on a change": (BUDGET, "note", ("--owner", "Ana Ruiz")),
            "target not a date": (BUDGET, "change", ("--target", "27 November")),
            "for no project": ("none", "change", ("--status", "Fine")),
        }
        for label, (project, kind, extra) in cases.items():
            with self.subTest(label):
                _, out, code = self.save(project=project, kind=kind, extra=extra)
                self.assertEqual((out["status"], code), ("not-saved", 1), out)
        _, out, code = self.save(kind="change", extra=("--target", "none", "--owner", "none"))  # none clears one
        self.assertEqual((out["status"], code), ("saved", 0), out)
        _, out, code = self.save(kind="note", extra=("--field", "status=sent"))  # also through --field
        self.assertEqual((out["status"], code), ("not-saved", 1), out)

    def test_records_saved_before_keep_reading_as_they_did(self):
        # Before these fields had a meaning, any record could carry them as extra lines; such a record is still fine.
        cases = {"result with a status": ("result", "status: sent"), "note with an owner": ("note", "owner: Ana Ruiz"),
                 "change with a target in words": ("change", "target: end of November")}
        for label, (kind, extra) in cases.items():
            with self.subTest(label):
                request = self.new_request()
                self.write_raw(f"{request}.md", self.raw_record(request, "An earlier record.", kind=kind, extra=extra))
                out, code = self.run_tool("read", "--request", request)
                self.assertEqual((out["status"], code), ("found", 0), out)

    def test_the_help_command_for_owner_target_and_status_saves_what_it_says(self):
        text = (HELP / "projects.md").read_text(encoding="utf-8")
        section = text[text.index("## Owner, target and status"):text.index("## When something does not fit")]
        line = re.search(r"`(python3 Product/Tools/pace_record\.py create [^`]*--owner[^`]*)`", section).group(1)
        args = [self.new_request() if arg == "<request>" else arg for arg in shlex.split(line)[2:]]
        out, code = self.run_tool(*args)
        self.assertEqual((out["status"], code), ("saved", 0), out)
        record = self.run_tool("read", "--request", out["request"])[0]["record"]
        self.assertEqual((record["kind"], record["owner"], record["target"]), ("change", "Ana Ruiz", "2026-11-27"))
        self.assertTrue(record["status"])
        for field in pr.PROJECT_FIELDS:
            self.assertIn(f"`{field}`", section)


class HelpAndToolAgreeTests(unittest.TestCase):
    def test_record_format_help_matches_the_tool(self):
        text = (HELP / "record-format.md").read_text(encoding="utf-8")
        self.assertIn("# Record format: record-1", text)
        for kind in pr.KINDS:
            self.assertIn(f"| `{kind}` |", text)
        for origin in pr.ORIGINS:
            self.assertIn(f"| `{origin}` |", text)
        for field in pr.RECORD_ORDER:
            self.assertIn(f"`{field}`", text)
        example = re.search(r"```text\n(---\nformat: record-1\n.*?)```", text, re.S).group(1)
        fields, body, problems = pr.parse(example.encode("utf-8"))
        request = pr.one(fields, "request")
        self.assertEqual(problems + pr.record_problems(fields, body, request), [])
        self.assertIn(f"Record/{request}.md", text)
        # The worked time example is right: 11:15 in Auckland in October is 22:15 UTC the day before.
        self.assertEqual(pr.parse_time(pr.one(fields, "created")), pr.request_time(request))

    def test_project_help_example_is_a_project_1_file(self):
        text = (HELP / "projects.md").read_text(encoding="utf-8")
        example = re.search(r"```text\n(---\nformat: project-1\n.*?)```", text, re.S).group(1)
        fields, _, problems = pr.parse(example.encode("utf-8"))
        self.assertEqual(problems, [])
        self.assertTrue(pr.valid_project_id(pr.one(fields, "id")))
        self.assertIn(pr.PROJECT_FILE, text)

    def test_help_examples_make_the_project_before_its_records(self):
        # projects.md used to make kowhai-budget at 11:20, after other pages' examples saved records for it at 11:15.
        text = (HELP / "projects.md").read_text(encoding="utf-8")
        project, _, _ = pr.parse(re.search(r"```text\n(---\nformat: project-1\n.*?)```", text, re.S).group(1).encode("utf-8"))
        made = pr.parse_time(pr.one(project, "created"))
        seen = 0
        for page in ("record-format.md", "confirmations.md"):
            for example in re.findall(r"```text\n(---\nformat: record-1\n.*?)```", (HELP / page).read_text(encoding="utf-8"), re.S):
                fields, _, _ = pr.parse(example.encode("utf-8"))
                if pr.one(fields, "project") != pr.one(project, "id"):
                    continue
                seen += 1
                with self.subTest(page=page, request=pr.one(fields, "request")):
                    self.assertLessEqual(made, pr.request_time(pr.one(fields, "request")))
                    self.assertLessEqual(made, pr.parse_time(pr.one(fields, "created")))
        self.assertEqual(seen, 3)

    def test_records_help_covers_timing_off_the_record_and_honest_outcomes(self):
        text = (HELP / "records.md").read_text(encoding="utf-8")
        for phrase in ("as the conversation goes", "Off the record", "Placed but not confirmed", "Conflict",
                       "Already saved", "Possible duplicate", "never the owner's approval", "never edited",
                       "Never say a list is complete", "record-format.md", "`.pace-tmp-`", "someone with delete rights"):
            self.assertIn(phrase, text)
        for path in ("records.md", "record-format.md", "projects.md"):
            content = (HELP / path).read_text(encoding="utf-8")
            self.assertNotIn("—", content)
            self.assertNotIn("not built yet", content)
            for link in re.findall(r"\]\(([^)\s]+)\)", content):
                self.assertTrue((HELP / link).is_file(), link)

    def test_pace_md_points_to_record_help_without_new_rules(self):
        text = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("- [Records and source evidence]"))
        self.assertNotIn("placeholder", line)
        self.assertIn("Product/Help/projects.md", line)

    def test_the_pace_folder_can_be_given_after_the_command(self):
        # find --pace <folder> used to stop with a usage error instead of a result.
        with tempfile.TemporaryDirectory() as tmp:
            pace = Path(tmp) / "Invented Pace"
            (pace / "Record").mkdir(parents=True)
            (pace / "Projects").mkdir()

            def run(*args):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = pr.main(list(args))
                return json.loads(buffer.getvalue()), code

            out, code = run("project-new", "--pace", str(pace), "--id", GARDEN, "--name", "Garden plans", "--by", "Test agent")
            self.assertEqual((out["status"], code), ("saved", 0), out)
            request = run("new-request", "--project", GARDEN)[0]["request"]
            out, code = run("create", "--request", request, "--project", GARDEN, "--kind", "note", "--subject", "Seeds",
                            "--from", "agent", "--by", "Test agent", "--body", "Invented seed order.", "--pace", str(pace))
            self.assertEqual((out["status"], code), ("saved", 0), out)
            for args in (("find", "--pace", str(pace)), ("read", "--request", request, "--pace", str(pace)),
                         ("history", "--pace", str(pace), "--request", request), ("projects", "--pace", str(pace)),
                         ("--pace", str(pace), "find")):
                with self.subTest(args=args):
                    out, code = run(*args)
                    self.assertEqual(code, 0, out)
            # Given after the command, it is used instead of one given before it.
            out, _ = run("--pace", str(Path(tmp) / "elsewhere"), "find", "--pace", str(pace))
            self.assertEqual(out["status"], "found", out)
        # Every command takes it.
        commands = next(a for a in pr.build_parser()._actions if a.dest == "command").choices
        for name, command in commands.items():
            with self.subTest(command=name):
                self.assertIn("--pace", command._option_string_actions)

    def test_the_tool_finds_its_own_pace_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "Copied Pace"
            shutil.copytree(PACE_FOLDER, copy, ignore=shutil.ignore_patterns("__pycache__"))
            env = {k: v for k, v in os.environ.items() if k != "PACE_FOLDER"}
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            command = [sys.executable, str(copy / "Product/Tools/pace_record.py")]
            run = subprocess.run(command + ["project-new", "--id", "first", "--name", "First project", "--by", "Test agent"],
                                 capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual(json.loads(run.stdout)["status"], "saved", run.stdout + run.stderr)
            self.assertTrue((copy / "Projects/First project/Pace project.md").is_file())
            request = json.loads(subprocess.run(command + ["new-request", "--project", "first"], capture_output=True,
                                                text=True, cwd=tmp, env=env).stdout)["request"]
            run = subprocess.run(command + ["create", "--request", request, "--project", "first", "--kind", "note",
                                            "--subject", "Start", "--from", "agent", "--by", "Test agent",
                                            "--body", "First invented record."], capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual((json.loads(run.stdout)["status"], run.returncode), ("saved", 0))
            self.assertTrue((copy / "Record" / f"{request}.md").is_file())
            # Outside any Pace folder and with no folder named, it asks rather than guessing.
            loose = Path(tmp) / "loose.py"
            shutil.copy(TOOL, loose)
            run = subprocess.run([sys.executable, str(loose), "projects"], capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual((json.loads(run.stdout)["status"], run.returncode), ("not-run", 1))


class ExampleFolderTests(unittest.TestCase):
    def test_example_records_are_made_after_their_request_and_their_project(self):
        # Four example records used to say they were made an hour or more before their own request.
        projects = {}
        for path in (EXAMPLE / "Projects").rglob(pr.PROJECT_FILE):
            fields, _, _ = pr.parse(path.read_bytes())
            projects[pr.one(fields, "id")] = pr.parse_time(pr.one(fields, "created"))
        records = sorted((EXAMPLE / "Record").glob("*.md"))
        self.assertTrue(records)
        for path in records:
            with self.subTest(record=path.name):
                fields, body, problems = pr.parse(path.read_bytes())
                self.assertEqual(problems + pr.record_problems(fields, body, path.stem), [])
                created = pr.parse_time(pr.one(fields, "created"))
                self.assertGreaterEqual(created, pr.request_time(path.stem))
                self.assertLessEqual(projects[pr.one(fields, "project")], created)


    def test_file_sources_carry_their_fingerprint(self):
        # Records help says to name a source file with its fingerprint; the examples used to leave it out.
        checked = 0
        for path in sorted((EXAMPLE / "Record").glob("*.md")):
            fields, _, _ = pr.parse(path.read_bytes())
            for source in fields.get("source", []):
                where, _, digest = source.rpartition(" sha256:")
                with self.subTest(record=path.name, source=source):
                    self.assertTrue(where, "a source file named without its fingerprint")
                    self.assertEqual(digest, pr.sha256((EXAMPLE / where).read_bytes()))
                    checked += 1
        self.assertEqual(checked, 5)
        text = (HELP / "confirmations.md").read_text(encoding="utf-8")
        for example in re.findall(r"```text\n(---\nformat: record-1\n.*?)```", text, re.S):
            fields, _, _ = pr.parse(example.encode("utf-8"))
            for source in fields.get("source", []):
                if source.startswith("Projects/"):
                    with self.subTest(help_source=source):
                        self.assertRegex(source, r" sha256:[0-9a-f]{64}$")


    def test_competing_accounts_in_the_example_settle_as_the_help_says(self):
        # The help said to correct the latest version, which the tool refuses for two competing accounts,
        # and correcting one account alone left the other standing.
        settle = "To settle competing accounts, correct the one that stands and withdraw the other."
        self.assertTrue(settle in (HELP / "records.md").read_text(encoding="utf-8"), "records help")
        for add_in in ("Daily brief", "Project overview"):
            text = (PACE_FOLDER / "Product/Pace add-ins" / add_in / "ADD-IN.md").read_text(encoding="utf-8")
            self.assertTrue("correct the one that stands and withdraw the other" in text, add_in)
        original, ana, sam = (f"{stem}--maple-budget--{tail}" for stem, tail in (
            ("20261025T210000Z", "brd001"), ("20261027T020000Z", "brd002"), ("20261027T220000Z", "brd003")))
        with tempfile.TemporaryDirectory() as tmp:
            pace = Path(tmp) / "Example copy"
            shutil.copytree(EXAMPLE, pace, ignore=shutil.ignore_patterns("__pycache__"))

            def run(*args):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = pr.main(["--pace", str(pace), *args])
                return json.loads(buffer.getvalue()), code

            def create(when, corrects, kind, words, body, *extra):
                request = run("new-request", "--project", "maple-budget", "--at", when)[0]["request"]
                return run("create", "--request", request, "--project", "maple-budget", "--kind", kind,
                           "--subject", "Board pack draft", "--from", "owner", "--words", words, "--by", "Test agent",
                           "--corrects", corrects, "--body", body, *extra)

            self.assertEqual(run("history", "--request", original)[0]["status"], "conflict")
            refused, code = create("2026-10-28T01:00:00Z", original, "action", "The 20th.", "Draft due 20 November.")
            self.assertEqual((refused["status"], code), ("not-saved", 1), refused)
            self.assertIn(settle, refused["message"])
            # The owner says Sam's date stands: correct that account in the owner's words and withdraw Ana's.
            stands, code = create("2026-10-28T01:01:00Z", sam, "action", "Sam's right, the draft is due on the 16th.",
                                  "Board pack draft due 16 November, in the owner's words.",
                                  "--due", "2026-11-16", "--owed-by", "Ana Ruiz", "--for", "owner", "--state", "open")
            self.assertEqual((stands["status"], code), ("saved", 0), stands)
            withdrawn, code = create("2026-10-28T01:02:00Z", ana, "withdrawal", "The 12th no longer stands.",
                                     "Ana's 12 November date no longer stands; the owner settled on Sam's account.")
            self.assertEqual((withdrawn["status"], code), ("saved", 0), withdrawn)
            out, code = run("history", "--request", original)
            self.assertEqual((out["status"], code), ("found", 0), out)
            self.assertEqual(out["current"], [stands["request"]])
            self.assertEqual(out["withdrawn_by"], [withdrawn["request"]])
            self.assertNotIn("competing-corrections", {issue["type"] for issue in out["issues"]})


if __name__ == "__main__":
    unittest.main()
