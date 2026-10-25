"""Invented exact-act confirmation and client-reference scenarios; no live accounts."""

from pathlib import Path
from unittest import mock
import json
import os
import re

from test_records import PaceFolder, BUDGET, HELP, pr


class ConfirmationTests(PaceFolder):
    def setUp(self):
        super().setUp()
        self.act = self.pace / "1 Projects/Kowhai Books/Budget 2027/Documents/close.txt"
        self.act.write_bytes(b"Invented October close: accept version A.\n")
        self.words = "Yes, accept the October close statement you just showed me."

    def propose(self):
        out, code = self.run_tool("propose", "--act", "Accept October close", "--act-file", str(self.act))
        self.assertEqual((out["status"], code), ("proposed", 0))
        return out["act_sha256"]

    def confirm(self, request=None, shown=None, words=None, more=()):
        request = request or self.new_request()
        shown = shown or self.propose()
        args = ("confirm", "--request", request, "--project", BUDGET, "--subject", "October close",
                "--act", "Accept October close", "--act-file", str(self.act), "--shown-sha256", shown,
                "--source", "Invented close statement and comparison", "--by", "Test agent",
                "--owner-words", self.words if words is None else words, "--owner-current", *more)
        out, code = self.run_tool(*args)
        return request, out, code

    def test_current_owner_words_and_same_act_confirm_only_after_read_back(self):
        request, out, code = self.confirm()
        self.assertEqual((out["status"], code), ("confirmed", 0), out)
        self.assertEqual(out["save_status"], "saved")
        fields = self.run_tool("read", "--request", request)[0]["record"]["fields"]
        self.assertEqual(fields["words"], [self.words])
        self.assertEqual(fields["act-sha256"], [pr.sha256(self.act.read_bytes())])
        self.assertEqual(fields["source"], ["Invented close statement and comparison"])
        self.assertEqual(self.run_tool("confirmation-status", "--request", request)[0]["status"], "confirmed")
        _, retry, code = self.confirm(request=request)
        self.assertEqual((retry["status"], retry["save_status"], code), ("confirmed", "already-saved", 0))
        self.assertEqual(len(self.record_files()), 1)

    def test_relative_files_start_from_the_pace_folder(self):
        # They used to start from the current folder, so the paths the help shows failed from anywhere else.
        elsewhere = Path(self._tmp.name) / "elsewhere"
        elsewhere.mkdir()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(elsewhere)
        relative = "1 Projects/Kowhai Books/Budget 2027/Documents/close.txt"
        out, code = self.run_tool("propose", "--act", "Accept October close", "--act-file", relative)
        self.assertEqual((out["status"], code), ("proposed", 0), out)
        self.assertEqual(out["act_file"], relative)
        request = self.new_request()
        out, code = self.run_tool("confirm", "--request", request, "--project", BUDGET, "--subject", "October close",
                                  "--act", "Accept October close", "--act-file", relative, "--shown-sha256", out["act_sha256"],
                                  "--source", "Invented close statement", "--owner-words", self.words, "--owner-current",
                                  "--by", "Test agent")
        self.assertEqual((out["status"], code), ("confirmed", 0), out)
        out, code = self.run_tool("confirmation-status", "--request", request, "--act-file", relative)
        self.assertEqual((out["status"], code), ("confirmed", 0), out)
        note, saved, _ = self.save(kind="note", origin="source", words=None, subjects=("Close statement",),
                                   body="The invented close statement as filed.", extra=("--source-file", relative))
        self.assertEqual(saved["status"], "saved", saved)
        fields = self.run_tool("read", "--request", note)[0]["record"]["fields"]
        self.assertEqual(fields["source"], [f"{relative} sha256:{pr.sha256(self.act.read_bytes())}"])

    def test_changed_act_never_confirms_old_or_new_words(self):
        old = self.propose()
        self.act.write_bytes(b"Invented October close: accept version B.\n")
        _, out, code = self.confirm(shown=old)
        self.assertEqual((out["status"], code), ("proposed", 1))
        self.assertEqual(self.record_files(), [])
        request, out, code = self.confirm()
        self.assertEqual((out["status"], code), ("confirmed", 0))
        self.act.write_bytes(b"Invented October close: accept version C.\n")
        checked, code = self.run_tool("confirmation-status", "--request", request)
        self.assertEqual((checked["status"], code), ("pending", 1))
        self.assertIn("changed", checked["message"])
        _, clash, code = self.confirm(request=request)
        self.assertNotEqual(clash["status"], "confirmed")

    def test_quoted_yes_and_guessed_yes_are_not_owner_words(self):
        request = self.new_request()
        shown = self.propose()
        for args in (
            ("--source", 'Invented file says "yes"'),
            ("--source", 'Invented file says "yes"', "--owner-words", "yes"),
        ):
            out, code = self.run_tool("confirm", "--request", request, "--project", BUDGET,
                                      "--subject", "October close", "--act", "Accept October close",
                                      "--act-file", str(self.act), "--shown-sha256", shown,
                                      "--by", "Test agent", *args)
            self.assertEqual((out["status"], code), ("proposed", 1))
        self.assertEqual(self.record_files(), [])
        # Ordinary create and a hand-written quoted yes without current words do not elevate a source.
        out, code = self.run_tool("create", "--request", request, "--project", BUDGET,
                                  "--kind", "confirmation", "--subject", "October close",
                                  "--from", "source", "--source", 'Invented file says "yes"',
                                  "--by", "Test agent", "--body", "Owner said yes.")
        self.assertEqual((out["status"], code), ("not-saved", 1))
        raw = self.raw_record(request, "A quoted yes is not a confirmation.", kind="confirmation",
                              extra="source: Invented file says yes")
        self.write_raw(f"{request}.md", raw)
        out, code = self.run_tool("confirmation-status", "--request", request)
        self.assertEqual((out["status"], code), ("pending", 1))

    def test_missing_or_wrong_read_back_and_mid_save_change_are_pending(self):
        request = self.new_request()
        with self.failing_read(request, OSError("offline")):
            _, out, code = self.confirm(request=request)
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertEqual(out["confirmation_state"], "pending")
        self.assertEqual(self.run_tool("confirmation-status", "--request", request)[0]["status"], "confirmed")
        other = self.pace / "other.txt"
        other.write_bytes(self.act.read_bytes())
        out, code = self.run_tool("confirmation-status", "--request", request, "--act-file", str(other))
        self.assertEqual((out["status"], code), ("pending", 1))
        fresh = self.new_request()
        self.act.write_bytes(b"Invented new proposal before second save.\n")
        original = pr.place_new
        def change_during_save(path, data):
            result = original(path, data)
            self.act.write_bytes(b"Invented close has changed during save.\n")
            return result
        with mock.patch.object(pr, "place_new", side_effect=change_during_save):
            _, out, code = self.confirm(request=fresh)
        self.assertEqual((out["status"], code), ("pending", 1))

    def test_correction_and_withdrawal_supersede_without_rewriting_history(self):
        first, _, _ = self.confirm()
        second = self.new_request()
        _, fixed, code = self.confirm(request=second, more=("--corrects", first))
        self.assertEqual((fixed["status"], code), ("confirmed", 0), fixed)
        out, code = self.run_tool("confirmation-status", "--request", first)
        self.assertEqual((out["status"], code), ("superseded", 1))
        self.assertEqual(out["corrected_by"], [second])
        withdrawal = self.new_request()
        out, code = self.run_tool("create", "--request", withdrawal, "--project", BUDGET,
                                  "--kind", "withdrawal", "--subject", "October close", "--from", "owner",
                                  "--words", "Withdraw my October close confirmation.", "--by", "Test agent",
                                  "--corrects", second, "--body", "The earlier close does not stand.")
        self.assertEqual((out["status"], code), ("saved", 0))
        self.assertEqual(self.run_tool("confirmation-status", "--request", second)[0]["status"], "superseded")

    def reference(self, confirmed, available=True, decision="accepted", request=None, more=()):
        request = request or self.new_request()
        args = ("approval-reference", "--request", request, "--project", BUDGET,
                "--subject", "October close", "--confirmation-request", confirmed,
                "--system", "teams", "--approver", "Invented Reviewer", "--decision", decision,
                "--decision-time", "2026-10-23T11:29:00+13:00", "--reference", "AC-042",
                "--source", "Invented client approval result AC-042", "--by", "Test agent")
        return request, *self.run_tool(*args, *(("--available",) if available else ()), *more)

    def test_a_separate_confirmation_or_reference_can_be_kept_as_the_message_says(self):
        # Both commands said "save again with --not-a-duplicate" but refused that option.
        first, out, _ = self.confirm()
        self.assertEqual(out["status"], "confirmed", out)
        again, out, code = self.confirm()
        self.assertEqual((out["status"], code), ("possible-duplicate", 1), out)
        self.assertIn("--not-a-duplicate", out["message"])
        _, out, code = self.confirm(request=again, more=("--not-a-duplicate",))
        self.assertEqual((out["status"], code), ("confirmed", 0), out)
        _, out, _ = self.reference(first)
        self.assertEqual(out["status"], "reference-recorded", out)
        repeat, out, code = self.reference(first)
        self.assertEqual((out["status"], code), ("possible-duplicate", 1), out)
        self.assertIn("--not-a-duplicate", out["message"])
        _, out, code = self.reference(first, request=repeat, more=("--not-a-duplicate",))
        self.assertEqual((out["status"], code), ("reference-recorded", 0), out)
        self.assertEqual(len(self.record_files()), 4)

    def test_unavailable_client_approval_never_claims_decision(self):
        confirmed, _, _ = self.confirm()
        request, out, code = self.reference(confirmed, available=False)
        self.assertEqual((out["status"], code), ("pending", 1))
        self.assertNotIn(f"{request}.md", self.record_files())
        out, code = self.run_tool("confirmation-status", "--request", confirmed,
                                  "--reference-request", request)
        self.assertEqual((out["status"], code), ("pending", 1))
        self.assertEqual(out["owner_confirmation"]["status"], "confirmed")

    def test_client_reference_is_separate_and_only_matches_same_fingerprint(self):
        confirmed, _, _ = self.confirm()
        request, out, code = self.reference(confirmed)
        self.assertEqual((out["status"], out["decision"], code), ("reference-recorded", "accepted", 0), out)
        checked, code = self.run_tool("confirmation-status", "--request", confirmed, "--reference-request", request)
        self.assertEqual((checked["status"], checked["client_approval_reference"]["status"], code),
                         ("confirmed", "reference-recorded", 0))
        fields = self.run_tool("read", "--request", request)[0]["record"]["fields"]
        self.assertEqual(fields["confirmation-request"], [confirmed])
        self.assertEqual(fields["act-sha256"], [pr.sha256(self.act.read_bytes())])
        self.act.write_bytes(b"Invented version B.\n")
        checked, code = self.run_tool("confirmation-status", "--request", confirmed, "--reference-request", request)
        self.assertEqual((checked["status"], code), ("pending", 1))
        self.assertEqual(checked["client_approval_reference"]["status"], "pending")

    def test_client_reference_requires_read_back_and_same_linked_act(self):
        confirmed, _, _ = self.confirm()
        request = self.new_request()
        with self.failing_read(request, OSError("client reference not downloaded")):
            _, out, code = self.reference(confirmed, request=request)
        self.assertEqual((out["status"], code), ("placed-not-confirmed", 1))
        self.assertEqual(out["confirmation_state"], "pending")
        # Even a readable but altered record is not linked to the confirmed act.
        file = self.record / f"{request}.md"
        text = file.read_text(encoding="utf-8")
        file.write_text(text.replace(pr.sha256(self.act.read_bytes()), "f" * 64), encoding="utf-8")
        checked, code = self.run_tool("confirmation-status", "--request", confirmed,
                                      "--reference-request", request)
        self.assertEqual((checked["status"], code), ("pending", 1))
        self.assertEqual(checked["client_approval_reference"]["status"], "pending")

    def test_declined_client_decision_is_not_turned_into_acceptance(self):
        confirmed, _, _ = self.confirm()
        request, out, code = self.reference(confirmed, decision="declined")
        self.assertEqual((out["decision"], code), ("declined", 0))
        self.assertNotIn("approved", out["message"])

    def test_same_shape_for_figures_forecasts_and_local_product_go_ahead(self):
        for subject, content in (
            ("Accepted figures", b"Invented total 42, unit items, period October, source Example.\n"),
            ("Forecast acceptance", b"Invented forecast version 2, source Example.\n"),
            ("Local Product go-ahead", b"Invented version 3.4.0, full commit a1, Product digest b2; replace local Product.\n"),
        ):
            with self.subTest(subject=subject):
                self.act.write_bytes(content)
                request = self.new_request()
                shown = self.propose()
                out, code = self.run_tool("confirm", "--request", request, "--project", BUDGET,
                                          "--subject", subject, "--act", subject, "--act-file", str(self.act),
                                          "--shown-sha256", shown, "--source", "Invented proposed content and before-after",
                                          "--owner-words", f"Yes, {subject} as shown.", "--owner-current", "--by", "Test agent")
                self.assertEqual((out["status"], code), ("confirmed", 0), out)

    def test_simple_release_go_ahead_does_not_turn_into_confirmation(self):
        simple = self.pace / "Release record/Go-aheads/example.json"
        simple.parent.mkdir(parents=True)
        simple.write_text(json.dumps({
            "format": "pace-update-go-ahead/1", "time": "2026-10-23T11:29:00+13:00",
            "release": {"tag": "v3.4.0", "commit": "a" * 40},
            "owner_words": 'Yes, install v3.4.0 at ' + "a" * 40,
        }), encoding="utf-8")
        missing = self.new_request()
        out, code = self.run_tool("confirmation-status", "--request", missing)
        self.assertEqual((out["status"], code), ("pending", 1))
        # The owner must currently confirm the exact shown content in a separate new record.
        self.act.write_bytes(b"Invented v3.4.0, commit " + b"a" * 40 + b", file list digest b2.\n")
        shown = self.propose()
        request = self.new_request()
        out, code = self.run_tool("confirm", "--request", request, "--project", BUDGET,
                                  "--subject", "Local update", "--act", "Install v3.4.0 locally",
                                  "--act-file", str(self.act), "--shown-sha256", shown,
                                  "--source", "Release record/Go-aheads/example.json (separate earlier go-ahead)",
                                  "--owner-words", "Yes, install this exact update now.", "--owner-current",
                                  "--by", "Test agent")
        self.assertEqual((out["status"], code), ("confirmed", 0))
        self.assertEqual(len(self.record_files()), 1)
        self.assertTrue(simple.is_file())

    def test_help_describes_record_and_state_words(self):
        text = (HELP / "confirmations.md").read_text(encoding="utf-8")
        for phrase in ("Proposed", "Pending", "Confirmed", "Superseded", "OneDrive", "month close",
                       "forecast", "local", "record-1", "approval-reference", "--owner-current"):
            self.assertIn(phrase, text)
        examples = re.findall(r"```text\n(---\nformat: record-1\n.*?)```", text, re.S)
        self.assertEqual(len(examples), 2)
        for example in examples:
            fields, body, problems = pr.parse(example.encode())
            request = pr.one(fields, "request")
            self.assertEqual(problems + pr.record_problems(fields, body, request), [])
