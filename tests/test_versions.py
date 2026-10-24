"""Documents and versions: Pace.md and projects help agree, and the help's own example works.

Invented data only, in temporary Pace folders.
"""

from datetime import date
from pathlib import Path
import hashlib
import re
import shlex
import sys
import unittest

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

from test_records import BUDGET, EXAMPLE, HELP, PACE_FOLDER, PaceFolder, at, pr

PROJECTS_HELP = HELP / "projects.md"
HEADING = "## Documents and versions"
LINK = "[Documents and versions](Product/Help/projects.md#documents-and-versions)"
COPY_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (.+) v([1-9][0-9]*)\.([A-Za-z0-9]+)$")


def versions_section():
    text = PROJECTS_HELP.read_text(encoding="utf-8")
    match = re.search(rf"^{HEADING}\n.*?(?=^## |\Z)", text, re.S | re.M)
    return match.group(0) if match else ""


def pace_md_rule(root):
    """The working-file sentence on the Projects line of a Pace.md."""
    text = (root / "Pace.md").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("- `Projects/` - projects"))
    return line[line.index("In `Documents/`"):]


class RuleTests(unittest.TestCase):
    def test_both_pace_md_files_carry_the_same_rule_and_link(self):
        # Only Pace.md is read at the start of a chat, so it says where the working file is and when a version is kept.
        rules = [pace_md_rule(root) for root in (PACE_FOLDER, EXAMPLE)]
        self.assertEqual(rules[0], rules[1])
        for phrase in ("one working file", "under the same name at the top of its folder",
                       "sent, presented, filed or signed off", "keep a dated copy in `Archive/` beside it"):
            self.assertIn(phrase, rules[0])
        self.assertTrue(rules[0].endswith(f"The detail is in {LINK}."))
        self.assertIn(f"\n{HEADING}\n", PROJECTS_HELP.read_text(encoding="utf-8"))

    def test_help_holds_each_rule_pace_md_points_to(self):
        section = versions_section()
        self.assertTrue(section, "projects help has no Documents and versions section")
        for phrase in (
            "sent, presented, filed or signed off",  # the same moments Pace.md names
            "`Archive/` folder beside the working file",
            "`YYYY-MM-DD <name> v<N>.<extension>`",
            "never a copy in `Archive/`",
            "Saving as you work does not make a version",
            "Never overwrite",
            "Open the copy again",
            "never edited, renamed, moved or replaced",
            "a `result` record",
            "`--source-file`",
            "out of file names",
            "(confirmations.md)",
            "Do not keep a list of which file is current",
            "cannot update a working file",
            "versions in git",
            "(repositories.md)",
        ):
            self.assertIn(phrase, section)

    def test_the_layout_example_follows_the_naming_rule(self):
        block = re.search(r"```text\n(Documents/\n.*?)```", versions_section(), re.S).group(1)
        lines = [line.split("<-")[0].rstrip() for line in block.splitlines()[1:]]
        working = [line.strip() for line in lines if re.match(r"^  \S", line) and not line.endswith("/")]
        copies = [line.strip() for line in lines if line.startswith("    ")]
        self.assertEqual(working, ["Budget 2027.xlsx"])
        self.assertIn("  Archive/", lines)
        numbers_by_day = {}
        for name in copies:
            match = COPY_NAME.match(name)
            self.assertIsNotNone(match, name)
            day, work, number, _ = match.groups()
            date.fromisoformat(day)
            self.assertEqual(work, Path(working[0]).stem, name)
            numbers_by_day.setdefault(day, set()).add(int(number))
        # Files that went out together share a date and a number; later days get higher numbers, from v1.
        self.assertTrue(all(len(numbers) == 1 for numbers in numbers_by_day.values()), numbers_by_day)
        numbers = [min(numbers_by_day[day]) for day in sorted(numbers_by_day)]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))


class HelpCommandTests(PaceFolder):
    def help_commands(self):
        block = re.search(r"```text\n(python3 Product/Tools/pace_record\.py create .*?)```", versions_section(), re.S).group(1)
        return [shlex.split(line)[2:] for line in block.strip().splitlines()]

    def test_the_help_commands_keep_each_version_and_find_them(self):
        create, find = self.help_commands()
        self.assertEqual((create[0], find[0]), ("create", "find"))
        place = create[create.index("--source-file") + 1]
        first_copy = self.pace / place
        # The help's copy sits in Archive/ inside this invented project's Documents/, named as the rule says.
        self.assertEqual((first_copy.parent.name, first_copy.parent.parent.name), ("Archive", pr.WORKING_DIR), place)
        self.assertTrue(first_copy.parent.parent.is_dir(), place)
        self.assertIsNotNone(COPY_NAME.match(first_copy.name), place)
        first_copy.parent.mkdir()
        first_copy.write_bytes(b"Invented budget workbook, version 1.")
        first = self.new_request(BUDGET, at(day=4, month=11, hour=10, minute=0))
        out, code = self.run_tool(*[first if part == "<request>" else part for part in create])
        self.assertEqual((out["status"], code), ("saved", 0), out)

        # The record names the copy by its place in the Pace folder, spaces and all, with its fingerprint.
        fields, _, problems = pr.parse((self.record / f"{first}.md").read_bytes())
        self.assertEqual(problems, [])
        fingerprint = hashlib.sha256(first_copy.read_bytes()).hexdigest()
        self.assertEqual(fields["source"], [f"{place} sha256:{fingerprint}"])
        self.assertEqual((pr.one(fields, "kind"), fields["subject"]), ("result", ["Budget 2027"]))

        # A later version under the same subject: the help's find lists both, newest first.
        second_copy = first_copy.with_name("2026-11-18 Budget 2027 v2.xlsx")
        second_copy.write_bytes(b"Invented budget workbook, version 2.")
        second = self.new_request(BUDGET, at(day=18, month=11, hour=10, minute=0))
        later = [second if part == "<request>" else part for part in create]
        later[later.index("--source-file") + 1] = second_copy.relative_to(self.pace).as_posix()
        later[later.index("--words") + 1] = "Version 2 went to the board today."
        later[later.index("--body") + 1] = "Version 2 of the 2027 budget went to the board on 18 November."
        out, code = self.run_tool(*later)
        self.assertEqual((out["status"], code), ("saved", 0), out)
        out, code = self.run_tool(*find)
        self.assertEqual(code, 0, out)
        self.assertEqual([found["request"] for found in out["records"]], [second, first])
        self.assertTrue(out["coverage"]["complete"])

        # An edit to a kept copy shows: its fingerprint no longer matches the one in its record.
        first_copy.write_bytes(b"Invented budget workbook, edited after it went out.")
        self.assertNotEqual(f"{place} sha256:{hashlib.sha256(first_copy.read_bytes()).hexdigest()}", fields["source"][0])


if __name__ == "__main__":
    unittest.main()
