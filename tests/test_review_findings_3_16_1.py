"""Three independent reviews of 3.16.1. The first two, at 167950f and 78fb842, were of an attempt to follow folders
renumbered by hand, which 3.16.1 replaced by following a record's path only to a folder of the same kind; the third
was at 1fa15df. Each finding has a test here that fails on the commit it was found in, except where a class says
otherwise.

Invented data only, in temporary folders.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import unicodedata
import unittest
from unittest import mock

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_archive import read
from test_folder_numbers import Case, pr

HELP = Path(pr.__file__).resolve().parent.parent / "Help"
CHANGELOG = HELP.parent.parent.parent / "CHANGELOG.md"
INVITATION = b"Invented invitation, not filled in yet.\n"
CHRISTMAS = "1 Projects/24. Dezember Feier/01. Documents/Einladung.txt"


def project(pace: Path, pid: str, folder: str, parent: str = "none", documents: str = "01. Documents") -> Path:
    """A project folder made by hand, as the owner may, with any name."""
    where = pace / "1 Projects" / folder
    (where / documents).mkdir(parents=True, exist_ok=True)
    (where / pr.PROJECT_FILE).write_text(f"---\nformat: project-1\nid: {pid}\nparent: {parent}\n"
                                         "created: 2026-08-01T09:00:00+12:00\nby: Test\n---\n\nInvented work.\n",
                                         encoding="utf-8")
    return where


def act(recorded: str, data: bytes, project_id: str = "none") -> dict:
    return {"act-file": [recorded], "act-sha256": [pr.sha256(data)], "project": [project_id]}


def flat(path: Path) -> str:
    return " ".join(read(path).split())


class ConfirmCase(Case):
    def assert_not_checked(self, fields: dict) -> None:
        problem = pr.check_act(self.pace, fields)
        self.assertIsNotNone(problem, "the act read as current")
        self.assertIn("could not be checked", problem)

    def confirm(self, request: str, project_id: str, where: str) -> None:
        proposed, _ = self.tool("propose", "--act", "Send the invitation", "--act-file", where)
        out, code = self.tool("confirm", "--request", request, "--project", project_id, "--subject", "Invitation",
                              "--act", "Send the invitation", "--act-file", where, "--shown-sha256", proposed["act_sha256"],
                              "--source", "Invitation shown", "--owner-words", "Yes, send the invitation you showed me.",
                              "--owner-current", "--by", "Test")
        self.assertEqual((out["status"], code), ("confirmed", 0), out)

    def status(self, request: str) -> tuple:
        out, code = self.tool("confirmation-status", "--request", request)
        return out["status"], code

    def two_parties(self) -> tuple:
        christmas = project(self.pace, "weihnachten-2026", "24. Dezember Feier")
        new_year = project(self.pace, "silvester-2026", "31. Dezember Feier")
        for folder in (christmas, new_year):
            (folder / "01. Documents/Einladung.txt").write_bytes(INVITATION)  # the same template in each
        return christmas, new_year

    def as_written(self, recorded: str) -> Path:
        return (self.pace / recorded).resolve()


# ------------------------------------------------------------------ the first review, of 167950f

class SameNameTests(ConfirmCase):
    """First review, 1 (high): two folders whose names match once their numbers are off were taken for one folder
    renumbered, so a record was followed into the other, even another project's copy of the same template."""

    def test_a_file_deleted_from_a_folder_still_there_is_not_looked_for_in_another(self):
        self.new("kowhai", "Kowhai Books")
        client = self.pace / "1 Projects/01. Kowhai Books"
        recorded = "1 Projects/01. Kowhai Books/07. Documents/Old letter.txt"
        for left in ("other files", "nothing"):
            with self.subTest(left=left):
                for name in ("07. Documents", "08. Documents"):
                    shutil.rmtree(client / name, ignore_errors=True)
                    (client / name).mkdir()
                    (client / name / "Old letter.txt").write_bytes(f"Invented letter kept in {name}.\n".encode())
                if left == "other files":
                    (client / "07. Documents/Notes.txt").write_bytes(b"Invented notes.\n")
                (client / "07. Documents/Old letter.txt").unlink()
                self.assertEqual(pr.recorded_path(self.pace, recorded), self.as_written(recorded))
                self.assert_not_checked(act(recorded, b"Invented letter kept in 07. Documents.\n", "kowhai"))

    def test_another_project_of_the_same_name_is_never_taken_for_the_one_recorded(self):
        for change in ("file deleted", "renamed as the help advises", "moved into the owner's 99. Archive",
                       "renumbered by hand beside the other"):
            with self.subTest(change=change):
                shutil.rmtree(self.pace / "1 Projects", ignore_errors=True)
                (self.pace / "1 Projects").mkdir()
                christmas, _ = self.two_parties()
                if change == "file deleted":
                    (christmas / "01. Documents/Einladung.txt").unlink()
                elif change.startswith("renamed"):
                    christmas.rename(self.pace / "1 Projects/24 Dezember Feier")
                elif change.startswith("moved"):
                    (self.pace / "1 Projects/99. Archive").mkdir()
                    christmas.rename(self.pace / "1 Projects/99. Archive/24. Dezember Feier")
                else:
                    christmas.rename(self.pace / "1 Projects/05. Dezember Feier")
                self.assertEqual(pr.recorded_path(self.pace, CHRISTMAS), self.as_written(CHRISTMAS))
                self.assert_not_checked(act(CHRISTMAS, INVITATION, "weihnachten-2026"))

    def test_a_confirmation_is_not_current_once_its_project_folder_is_renamed(self):
        christmas, _ = self.two_parties()
        request = "20261029T010000Z--weihnachten-2026--inv001"
        self.confirm(request, "weihnachten-2026", CHRISTMAS)
        christmas.rename(self.pace / "1 Projects/24 Dezember Feier")
        self.assertEqual(self.status(request), ("pending", 1))


class KindTests(Case):
    """First review, 2 (medium): no test held a project's Documents folder and a folder of the owner's own named
    Documents apart when only one of them was there. This fails on 3.16.0, whose path could lead from one to the other,
    and on the review's mutant of 167950f, not on 167950f itself."""

    def test_neither_kind_stands_in_for_the_other(self):
        client = project(self.pace, "kowhai", "Kowhai Books", documents="Documents")  # made before 3.16.0
        (client / "07. Documents").mkdir()
        (client / "07. Documents/Letter.txt").write_text("Invented letter in the owner's own folder.\n", encoding="utf-8")
        (client / "Documents").rmdir()
        recorded = "1 Projects/Kowhai Books/Documents/Letter.txt"
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())
        numbered = project(self.pace, "lodge", "01. Lodge")
        (numbered / "01. Documents/Letter.txt").write_text("Invented letter in the project's own folder.\n", encoding="utf-8")
        recorded = "1 Projects/01. Lodge/07. Documents/Letter.txt"  # its 07. Documents/ since removed
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())


class NumberInNameTests(ConfirmCase):
    """First review, 3 (low): the number was always taken off the name a record wrote, so 24. Dezember Feier numbered
    in front by hand, as 03. 24. Dezember Feier, was no longer found."""

    def test_a_name_that_keeps_its_own_number_is_found_when_numbered_in_front(self):
        christmas, _ = self.two_parties()
        christmas.rename(self.pace / "1 Projects/03. 24. Dezember Feier")
        self.assertEqual(pr.recorded_path(self.pace, CHRISTMAS),
                         (self.pace / "1 Projects/03. 24. Dezember Feier/01. Documents/Einladung.txt").resolve())


class DocumentsByPlaceTests(Case):
    """First review, 4 (low): whether a folder was a project's Documents folder was decided by its name alone, so a
    folder of the owner's own named Documents, outside a project's own place, was no longer followed once numbered."""

    def test_a_folder_of_the_owner_s_own_named_documents_is_followed_when_numbered(self):
        self.new("kowhai", "Kowhai Books")
        inner = self.pace / "1 Projects/01. Kowhai Books/01. Documents/Sources/Documents"
        inner.mkdir(parents=True)
        (inner / "Scan.txt").write_text("Invented scan.\n", encoding="utf-8")
        inner.rename(inner.with_name("02. Documents"))
        own = self.pace / "1 Projects/Documents"
        own.mkdir()
        (own / "Templates.txt").write_text("Invented templates.\n", encoding="utf-8")
        own.rename(self.pace / "1 Projects/98. Documents")
        for recorded, found in (("1 Projects/01. Kowhai Books/01. Documents/Sources/Documents/Scan.txt",
                                 "1 Projects/01. Kowhai Books/01. Documents/Sources/02. Documents/Scan.txt"),
                                ("1 Projects/Documents/Templates.txt", "1 Projects/98. Documents/Templates.txt")):
            with self.subTest(recorded=recorded):
                self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / found).resolve())


# ------------------------------------------------------------------ the second review, of 78fb842

class CrossProjectTests(ConfirmCase):
    """Second review, 1 (high): a record of one project naming another project's file was taken, once that folder was
    renamed or deleted, into the record's own project's folder of the same name, by its id, and read as current."""

    def test_a_record_naming_another_project_s_file_is_never_taken_into_its_own(self):
        for change in ("renamed as the help advises", "renamed keeping its number", "deleted"):
            with self.subTest(change=change):
                shutil.rmtree(self.pace / "1 Projects", ignore_errors=True)
                shutil.rmtree(self.pace / "Record", ignore_errors=True)
                (self.pace / "1 Projects").mkdir()
                (self.pace / "Record").mkdir()
                christmas, _ = self.two_parties()
                request = "20261029T020000Z--silvester-2026--inv002"
                self.confirm(request, "silvester-2026", CHRISTMAS)  # New Year's Eve uses the Christmas invitation
                if change == "deleted":
                    shutil.rmtree(christmas)
                else:
                    christmas.rename(self.pace / "1 Projects" / ("24 Dezember Feier" if "advises" in change
                                                                 else "24. Weihnachtsfeier"))
                self.assertEqual(self.status(request), ("pending", 1))

    def test_a_copy_of_the_record_s_own_project_is_not_taken_for_it(self):
        christmas = project(self.pace, "weihnachten-2026", "24. Dezember Feier")
        (christmas / "01. Documents/Einladung.txt").write_bytes(INVITATION)
        shutil.copytree(christmas, self.pace / "1 Projects/25. Dezember Feier")  # to start next year's
        shutil.rmtree(christmas)
        self.assert_not_checked(act(CHRISTMAS, INVITATION, "weihnachten-2026"))


class NumberedSinceTests(ConfirmCase):
    """Second review, 2 (medium): a path a record wrote before numbering, into a folder of a project other than its
    own, stopped being followed once the folders tool numbered the folders, though 3.16.0 followed it."""

    def test_every_record_finds_its_file_after_the_folders_tool_numbers_the_folders(self):
        project(self.pace, "kowhai", "Kowhai Books", documents="Documents")  # made before 3.16.0
        project(self.pace, "kowhai-budget", "Kowhai Books/Budget 2027", parent="kowhai", documents="Documents")
        project(self.pace, "kowhai-web", "Kowhai Books/Website", parent="kowhai", documents="Documents")
        project(self.pace, "kowhai-web-2019", "Kowhai Books/Old work/Website", parent="kowhai", documents="Documents")
        project(self.pace, "garden", "Garden plans", documents="Documents")
        budget = "1 Projects/Kowhai Books/Budget 2027/Documents/Budget.txt"
        (self.pace / budget).write_bytes(b"Invented budget.\n")
        page = "1 Projects/Kowhai Books/Website/Documents/Home page.txt"
        (self.pace / page).write_bytes(b"Invented home page.\n")
        requests = {f"20261001T0{number}0000Z--{pid}--bud00{number}": (pid, budget) for number, pid in
                    enumerate(("kowhai", "kowhai-web", "garden", "none", "kowhai-budget"))}
        requests["20261001T060000Z--kowhai-web--web001"] = ("kowhai-web", page)
        for request, (pid, where) in requests.items():
            self.confirm(request, pid, where)
        plan, _ = self.preview()
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        self.assertFalse((self.pace / budget).exists())
        for request in requests:
            with self.subTest(request=request):
                self.assertEqual(self.status(request), ("confirmed", 0))


class NumbersSwappedTests(Case):
    """Second review, 3 (medium): the help said records still find their files after project folders are put in
    another order by hand, but a record finds whichever folder now has the name and number it wrote, so two projects
    of one name swapping numbers swapped what their records found. The help now says not to do that."""

    def test_the_help_says_a_number_never_goes_to_another_folder_of_the_same_name(self):
        projects = flat(HELP / "projects.md")
        self.assertIn("A record finds whichever folder now has the name and number it wrote", projects)
        self.assertIn("never give a number to another folder of the same name.", projects)
        self.assertIn("Records do not follow a number changed or taken off by hand, since nothing says which folder was "
                      "meant: a confirmation of a file in such a folder then reads as not checked and needs the owner's "
                      "words again.", projects)
        self.assertNotIn("since the tools check the id", projects)


class StaleDocumentsTests(ConfirmCase):
    """Second review, 4 (low): a path into a project's 01. Documents/ was followed back into a Documents/ OneDrive had
    made again beside it, holding a stale copy, and read as current against it."""

    def test_a_path_into_01_documents_is_never_followed_into_a_documents_folder_beside_it(self):
        self.new("kowhai", "Kowhai Books")
        client = self.pace / "1 Projects/01. Kowhai Books"
        where = "1 Projects/01. Kowhai Books/01. Documents/Budget.txt"
        (self.pace / where).write_bytes(b"Invented budget.\n")
        request = "20261029T030000Z--kowhai--bud001"
        self.confirm(request, "kowhai", where)
        (client / "Documents").mkdir()
        (client / "Documents/Budget.txt").write_bytes(b"Invented budget.\n")  # OneDrive's copy under the old name
        (self.pace / where).rename(client / "01. Documents/Budget draft.txt")
        self.assertEqual(self.status(request), ("pending", 1))


class GuardTests(ConfirmCase):
    """Second review, 5 (medium): guards could be removed with every test still passing. These hold each guard of the
    rule that replaces them, and the paths a caller supplies and client approval references, which are checked the same
    way. Each fails once its guard is taken out of the tool, rather than on 78fb842."""

    def test_a_folder_of_the_owner_s_own_still_there_is_never_passed_over(self):
        self.new("kowhai", "Kowhai Books")
        documents = self.pace / "1 Projects/01. Kowhai Books/01. Documents"
        (documents / "Sources").mkdir()
        (documents / "02. Sources").mkdir()
        (documents / "02. Sources/Letter.txt").write_text("Invented letter.\n", encoding="utf-8")
        recorded = "1 Projects/01. Kowhai Books/01. Documents/Sources/Letter.txt"
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())
        (documents / "Sources").rmdir()  # once it is gone, the folder numbered since is the one
        self.assertEqual(pr.recorded_path(self.pace, recorded), (documents / "02. Sources/Letter.txt").resolve())

    def test_a_project_folder_still_there_is_never_passed_over(self):
        christmas = project(self.pace, "weihnachten-2026", "Dezember Feier", documents="Documents")
        recorded = "1 Projects/Dezember Feier/Documents/Einladung.txt"
        other = project(self.pace, "silvester-2026", "31. Dezember Feier", documents="Documents")
        (other / "Documents/Einladung.txt").write_bytes(INVITATION)
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())
        (christmas / pr.PROJECT_FILE).unlink()  # an empty folder of the old name, as OneDrive can make, is passed over
        shutil.rmtree(christmas / "Documents")
        self.assertEqual(pr.recorded_path(self.pace, recorded), (other / "Documents/Einladung.txt").resolve())

    def test_two_folders_numbered_since_are_never_chosen_between(self):
        for pid, number in (("kowhai", 1), ("kowhai-two", 2)):
            folder = project(self.pace, pid, f"0{number}. Kowhai Books")
            (folder / "01. Documents/Letter.txt").write_text("Invented letter.\n", encoding="utf-8")
        recorded = "1 Projects/Kowhai Books/Documents/Letter.txt"
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())

    def test_a_supplied_path_and_a_client_reference_are_followed_the_same_way(self):
        project(self.pace, "kowhai", "Kowhai Books", documents="Documents")  # made before 3.16.0
        where = "1 Projects/Kowhai Books/Documents/Letter.txt"
        (self.pace / where).write_bytes(b"Invented letter.\n")
        request = "20261029T040000Z--kowhai--let001"
        self.confirm(request, "kowhai", where)
        reference = "20261029T050000Z--kowhai--ref001"
        out, code = self.tool("approval-reference", "--request", reference, "--project", "kowhai",
                              "--confirmation-request", request, "--subject", "Letter", "--available",
                              "--system", "teams", "--decision", "accepted", "--decision-time", "2026-10-29T18:00:00+13:00",
                              "--approver", "Invented approver", "--reference", "INV-1",
                              "--source", "Invented approval message", "--by", "Test")
        self.assertEqual(code, 0, out)
        plan, _ = self.preview()
        self.assertEqual(self.apply(plan["plan"])[0]["status"], "numbered")
        out, code = self.tool("confirmation-status", "--request", request, "--act-file", where)
        self.assertEqual((out["status"], code), ("confirmed", 0), out)
        out, code = self.tool("confirmation-status", "--request", request, "--reference-request", reference)
        self.assertEqual((out["client_approval_reference"]["status"], code), ("reference-recorded", 0), out)


class QuickTests(Case):
    """Second review, 6 (low): each path followed read every project in the Pace folder, again for each path."""

    def test_following_a_path_reads_no_project_list(self):
        project(self.pace, "kowhai", "Kowhai Books", documents="Documents")
        (self.pace / "1 Projects/Kowhai Books/Documents/Letter.txt").write_bytes(b"Invented letter.\n")
        plan, _ = self.preview()
        self.apply(plan["plan"])
        with mock.patch.object(pr, "scan_projects", side_effect=AssertionError("the project list was read")):
            self.assertEqual(pr.recorded_path(self.pace, "1 Projects/Kowhai Books/Documents/Letter.txt"),
                             (self.pace / "1 Projects/01. Kowhai Books/01. Documents/Letter.txt").resolve())


class TextTests(ConfirmCase):
    """Both reviews, 5 and 7 (low): the help, the changelog and the code said more than the code did."""

    def test_the_help_and_the_changelog_say_what_is_followed(self):
        projects = flat(HELP / "projects.md")
        for phrase in ("rename it first, such as to `24 Dezember Feier`. A record saved before the rename that names a file "
                       "in it does not find that file afterwards.",
                       "so keep its `01.`: renumbered, it is no longer the project's Documents folder, records do not find "
                       "their files in it, and the record tool makes a new `01. Documents/`.",
                       "The tools still find each file through folders numbered since, by each folder's name after its "
                       "number, and only as the same kind of folder: a project's `Documents/` only as its own "
                       "`01. Documents/`."):
            self.assertIn(phrase, projects)
        self.assertNotIn("records still find their files in them.", projects)
        changelog = flat(CHANGELOG).split("## 3.16.0 - ")[0]
        self.assertIn("**A number changed or taken off by hand is not followed**, as before", changelog)
        for promise in ("as long as only one folder could be meant", "which are left alone", "is never taken for it"):
            self.assertNotIn(promise, changelog)
        doc = " ".join(pr.numbered_path.__doc__.split())
        self.assertIn("A number changed or taken off by hand is not followed", doc)
        self.assertNotIn("Pace project.md is", doc)

    def test_a_project_s_documents_folder_renumbered_is_not_followed_as_the_help_says(self):
        self.new("kowhai", "Kowhai Books")
        client = self.pace / "1 Projects/01. Kowhai Books"
        (client / "01. Documents/Letter.txt").write_bytes(b"Invented letter.\n")
        recorded = "1 Projects/01. Kowhai Books/01. Documents/Letter.txt"
        (client / "01. Documents").rename(client / "99. Documents")
        self.assert_not_checked(act(recorded, b"Invented letter.\n", "kowhai"))
        self.assertEqual(pr.working_dir(client).name, "01. Documents")


# ------------------------------------------------------------------ the third review, of 1fa15df

class OwnFolderStillThereTests(ConfirmCase):
    """Third review, 3 (medium): a folder of the owner's own still there under the name as written was passed over for
    a project folder of the same name, so a record of the owner's drafts was taken into the project's own file."""

    def test_a_folder_of_the_owner_s_own_that_holds_anything_is_never_passed_over(self):
        self.new("kowhai", "Kowhai Books")
        self.new("kowhai-web", "Website", "kowhai")
        client = self.pace / "1 Projects/01. Kowhai Books"
        (client / "02. Website/01. Documents/Brief.txt").write_bytes(INVITATION)  # the project's own brief
        drafts = client / "Website/Documents"
        drafts.mkdir(parents=True)  # the owner's own drafts, beside the project
        recorded = "1 Projects/01. Kowhai Books/Website/Documents/Brief.txt"
        for layout in ("its file deleted", "numbered by hand inside, with Documents made again empty"):
            with self.subTest(layout=layout):
                if layout.startswith("numbered"):
                    (client / "Website/02. Documents").mkdir()
                    (client / "Website/02. Documents/Brief.txt").write_bytes(INVITATION)
                self.assertNotEqual(pr.recorded_path(self.pace, recorded),
                                    (client / "02. Website/01. Documents/Brief.txt").resolve())
                self.assert_not_checked(act(recorded, INVITATION, "kowhai-web"))

    def test_a_record_written_before_numbering_finds_the_owner_s_drafts_not_the_project_s_file(self):
        self.new("kowhai", "Kowhai Books")
        self.new("kowhai-web", "Website", "kowhai")
        client = self.pace / "1 Projects/01. Kowhai Books"
        (client / "02. Website/01. Documents/Brief.txt").write_bytes(b"Invented brief of the project.\n")
        (client / "Website/Documents").mkdir(parents=True)
        (client / "Website/Documents/Brief.txt").write_bytes(b"Invented draft of the owner's.\n")
        client.rename(client.with_name("04. Kowhai Books"))  # renumbered: a path written before numbering finds it
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/Kowhai Books/Website/Documents/Brief.txt"),
                         (self.pace / "1 Projects/04. Kowhai Books/Website/Documents/Brief.txt").resolve())


class NameFormTests(Case):
    """Third review, 6 (low): the folder as written was looked for byte for byte while names are matched in any case
    and Unicode form, so a project's own folder kept in the other form was passed over for another of the same name."""

    def test_a_folder_still_there_in_another_form_is_the_one_written(self):
        decomposed = unicodedata.normalize("NFD", "Café Noël")
        composed = unicodedata.normalize("NFC", "Café Noël")
        own = project(self.pace, "cafe-2025", decomposed, documents="Documents")
        (own / "Documents/Menu.txt").write_bytes(b"Invented menu of 2025.\n")
        other = project(self.pace, "cafe-2026", f"02. {composed}")
        (other / "01. Documents/Menu.txt").write_bytes(b"Invented menu of 2026.\n")
        recorded = f"1 Projects/{composed}/Documents/Menu.txt"
        self.assertEqual(pr.recorded_path(self.pace, recorded).read_bytes(), b"Invented menu of 2025.\n")


class ThirdGuardTests(Case):
    """Third review, 4 (medium): four changes to the rule passed every test. Each test here fails once its guard is
    taken out, rather than on 1fa15df."""

    def test_the_folder_still_there_is_tried_first(self):
        client = project(self.pace, "kowhai", "Kowhai Books", documents="Documents")
        (client / "Documents/02. Old").mkdir(parents=True)  # OneDrive's Documents/ again, its Old/ numbered by hand
        (client / "Documents/02. Old/Letter.txt").write_bytes(b"Invented letter in Documents.\n")
        (client / "01. Documents/Old").mkdir(parents=True)
        (client / "01. Documents/Old/Letter.txt").write_bytes(b"Invented letter in 01. Documents.\n")
        found = pr.recorded_path(self.pace, "1 Projects/Kowhai Books/Documents/Old/Letter.txt")
        self.assertEqual(found, (client / "Documents/02. Old/Letter.txt").resolve())

    def test_a_file_is_never_followed_to_a_file_numbered_beside_it(self):
        self.new("kowhai", "Kowhai Books")
        documents = self.pace / "1 Projects/01. Kowhai Books/01. Documents"
        (documents / "02. Agenda.txt").write_bytes(b"Invented agenda.\n")
        recorded = "1 Projects/01. Kowhai Books/01. Documents/Agenda.txt"
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())

    def test_a_folder_of_the_owner_s_own_named_documents_is_its_own_kind_wherever_it_is(self):
        self.new("kowhai", "Kowhai Books")
        sources = self.pace / "1 Projects/01. Kowhai Books/01. Documents/Sources"
        (sources / "01. Documents").mkdir(parents=True)
        (sources / "01. Documents/Scan.txt").write_bytes(b"Invented scan.\n")
        recorded = "1 Projects/01. Kowhai Books/01. Documents/Sources/Documents/Scan.txt"
        self.assertEqual(pr.recorded_path(self.pace, recorded), (sources / "01. Documents/Scan.txt").resolve())
        (sources / "02. Documents").mkdir()
        (sources / "02. Documents/Scan.txt").write_bytes(b"Invented scan.\n")
        self.assertEqual(pr.recorded_path(self.pace, recorded), (self.pace / recorded).resolve())  # two could be meant

    def test_a_file_where_a_folder_of_the_owner_s_own_was_does_not_stop_the_path(self):
        self.new("kowhai", "Kowhai Books")
        documents = self.pace / "1 Projects/01. Kowhai Books/01. Documents"
        (documents / "02. Sources").mkdir()
        (documents / "02. Sources/Letter.txt").write_bytes(b"Invented letter.\n")
        (documents / "Sources").write_bytes(b"Invented file where the folder was.\n")
        self.assertEqual(pr.recorded_path(self.pace, "1 Projects/01. Kowhai Books/01. Documents/Sources/Letter.txt"),
                         (documents / "02. Sources/Letter.txt").resolve())


class LimitTests(Case):
    """Third review, 1 and 2 (medium): the changelog said a path leads only to a folder that must be the one it named,
    and the help told the owner never to give a number to another folder of the same name, though the tools can: a
    path holds only names, so a path written before numbering can lead to another project of the same name made since,
    and a new project can take the name and number of one moved away. The help and changelog now say so."""

    def test_the_help_and_the_changelog_say_what_a_path_cannot_tell_apart(self):
        projects = flat(HELP / "projects.md")
        self.assertIn("A record finds whichever folder now has the name and number it wrote, even one made since, such as a "
                      "new project given the name and number of one moved away or deleted: so give a new project a name "
                      "no project there has had before, and never give a number to another folder of the same name.",
                      projects)
        self.assertIn("A path written before numbering holds no numbers, so where its project has since been renamed, moved "
                      "or deleted and another of the same name made, it can lead to the other.", projects)
        changelog = flat(CHANGELOG).split("## 3.16.0 - ")[0]
        self.assertNotIn("must be the one it named", changelog)
        self.assertNotIn("lead only to the folder they named", changelog)
        self.assertIn("## 3.16.1 - Safer record paths through numbered folders", flat(CHANGELOG))
        self.assertIn("A path written before numbering holds no numbers, so it can still lead to another project of the "
                      "same name made since its own was renamed, moved or deleted, as in 3.16.0.", changelog)
        doc = " ".join(pr.numbered_path.__doc__.split())
        self.assertIn("cannot tell apart two folders that have had the same name", doc)


if __name__ == "__main__":
    unittest.main()
