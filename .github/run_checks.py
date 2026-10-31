"""Run the checks in tests/ for GitHub Actions, and note on the pull request each one that does not pass.

The notes show beside the pull request, so a check that fails on Windows or macOS can be read without opening the
run's log. By hand, run the checks from tests/ with: python3 -B -m unittest discover -s . -p "test_*.py"

Standard library only; Python 3.9 or later.
"""

from __future__ import annotations

import os
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # keep PACE's Product folder free of cache files

TESTS = Path(__file__).resolve().parent.parent / "tests"
ROOM = 4000   # GitHub keeps the first 4096 characters of a note
NOTES = 10    # and 10 notes of each level for each step


def escaped(text: str, in_title: bool = False) -> str:
    """Text for a GitHub workflow command, which reads %, line breaks and, in a title, : and , as its own."""
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if in_title else text


def note(level: str, title: str, message: str) -> None:
    print(f"::{level} title={escaped(title, True)}::{escaped(message)}", flush=True)


def notes(level: str, title: str, lines: list, most: int = NOTES) -> None:
    """Lines in as few notes as hold them, each within GitHub's room, numbered when there are several. Where more than
    `most` notes would be needed, the last one says how many lines are left out, all of which the summary page lists."""
    room = ROOM - 100  # kept for the line saying what was left out
    parts: list = [[]]
    for line in lines:
        line = line[:room]
        if parts[-1] and len("\n".join(parts[-1] + [line])) > room:
            parts.append([])
        parts[-1].append(line)
    shown, left = parts[:most], sum(len(part) for part in parts[most:])
    if left:
        shown[-1] = shown[-1] + [f"... and {left} more, all listed on this run's summary page."]
    for number, part in enumerate(shown, 1):
        more = f" ({number} of {len(shown)})" if len(shown) > 1 else ""
        note(level, title + more, "\n".join(part))


def checks(count: int) -> str:
    return f"{count} check" if count == 1 else f"{count} checks"


def ends_with(text: str) -> str:
    """What a traceback ends with: the last exception it names, as `KeyError: 'counts'`, before any comparison."""
    raised = [line for line in text.splitlines() if re.match(r"[A-Za-z_][\w.]*(Error|Exception|Exit|Stop)\b", line)]
    return raised[-1].strip()[:300] if raised else "no traceback"


def setting() -> list:
    """What these checks ran on, so a failure on one system can be read against it."""
    lines = [f"Python {platform.python_version()} ({sys.executable}) on {platform.platform()}"]
    try:
        done = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
        lines.append(done.stdout.strip() or done.stderr.strip())
    except OSError as error:
        lines.append(f"git could not be run: {error}")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Pacific/Auckland")
        lines.append("Time zones can be read.")
    except Exception as error:  # noqa: BLE001 - any failure is the answer
        lines.append(f"Time zones cannot be read: {type(error).__name__}: {error}")
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, "Case").mkdir()
        lines.append(f"Temporary folders are in {folder}; names there "
                     f"{'ignore' if Path(folder, 'CASE').exists() else 'keep'} letter case.")
    lines.append(f"Output is written as {sys.stdout.encoding}; files open as {sys.getfilesystemencoding()} names.")
    return lines


def summary(lines: list) -> None:
    """Add to the run's summary page, when there is one."""
    page = os.environ.get("GITHUB_STEP_SUMMARY")
    if page:
        with open(page, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    here = setting()
    os.chdir(TESTS)
    suite = unittest.defaultTestLoader.discover(str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS))
    # GitHub reads a line starting :: in a step's output as a command, so nothing the checks print is read while they
    # run: the token that turns commands back on is one they cannot know.
    resume = secrets.token_hex(16)
    print(f"::stop-commands::{resume}", flush=True)
    try:
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        sys.stderr.flush()
        print(f"::{resume}::", flush=True)
    where = f"Python {platform.python_version()} on {platform.system()}"
    problems = ([("error", test, text) for test, text in result.errors] +
                [("failed", test, text) for test, text in result.failures] +
                [("passed though expected to fail", test, "") for test in result.unexpectedSuccesses])
    skipped = [f"{test.id()}: {reason}" for test, reason in result.skipped]
    lines = [f"### {here[0]}", "", *[f"- {line}" for line in here[1:]], "",
             f"{checks(result.testsRun)} ran: {len(problems)} did not pass and {len(skipped)} skipped.", ""]
    notes("notice", f"Ran on {where}", here, most=1)
    if problems:
        kinds: dict = {}
        for _, test, text in problems:
            kinds.setdefault(ends_with(text), []).append(test.id())
        grouped = [f"{len(names)} x {end}  (first: {names[0]})" for end, names in
                   sorted(kinds.items(), key=lambda item: -len(item[1]))]
        notes("error", f"{len(problems)} of {checks(result.testsRun)} did not pass on {where}, by what each ended with",
              grouped, most=1)
        for kind, test, text in problems[:NOTES - 1]:
            note("error", f"{kind}: {test.id()}", text[-ROOM:] or kind)
        notes("warning", f"Every check that did not pass on {where}", [f"{kind}: {test.id()}" for kind, test, _ in problems])
        for kind, test, text in problems:
            lines += [f"<details><summary>{kind}: {test.id()}</summary>", "", "```text", text.rstrip(), "```", "", "</details>"]
    else:
        note("notice", f"All {checks(result.testsRun)} passed on {where}", f"{len(skipped)} skipped.")
    if skipped:
        notes("notice", f"{checks(len(skipped))} skipped on {where}", skipped, most=NOTES - 2)
        lines += ["", "Skipped:", ""] + [f"- {line}" for line in skipped]
    summary(lines)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
