"""The checks build invented git repositories; they must never touch a real one.

Git tells the commands it runs where its repository is: for example it sets GIT_DIR for a hook,
or for `git rebase --exec` in a linked worktree. Checks that passed that on to their own git
commands would put their invented commits, tags and settings into the surrounding repository.
"""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from test_updates import GIT_ENV

TESTS = Path(__file__).resolve().parent
# Checks that make, commit, tag, clone and fetch invented repositories, and run the updater and get-pace.py.
SAMPLE = (
    "test_updates.ApplyTests.test_apply_replaces_only_product_reads_back_and_records",
    "test_updates.SourceTests.test_fork_with_different_product_stops_and_mirror_with_same_product_is_recorded",
    "test_updates.InterruptedInstallTests.test_hard_stop_mid_install_is_rolled_back_on_the_next_apply",
    "test_get_pace",
    "test_release_note.ForkOrMirror",
    "test_whole_pace_folder",
)


def outside_env() -> dict:
    """This process's environment without any git variable, for setting up the decoy."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_ENV)
    return env


def state(repo: Path) -> tuple:
    def run(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              env=outside_env(), check=True).stdout
    return ((repo / ".git/config").read_bytes(), run("rev-parse", "HEAD"), run("for-each-ref"),
            run("status", "--porcelain", "--untracked-files=all"))


class GitIsolationTests(unittest.TestCase):
    def test_checks_never_use_a_repository_named_by_their_surroundings(self):
        # A run under `git rebase --exec` in a linked worktree once set the shared repository to bare,
        # and added invented commits and tags to it, because GIT_DIR reached the checks' git commands.
        with tempfile.TemporaryDirectory(prefix="pace-git-decoy-") as tmp:
            decoy = Path(tmp) / "decoy"
            subprocess.run(["git", "init", "--quiet", str(decoy)], env=outside_env(), check=True)
            (decoy / "kept.txt").write_text("Invented decoy file.\n", encoding="utf-8")
            for args in (("add", "kept.txt"), ("commit", "--quiet", "-m", "Invented decoy")):
                subprocess.run(["git", "-C", str(decoy), *args], env=outside_env(), check=True)
            before = state(decoy)
            env = outside_env()
            env.update(GIT_DIR=str(decoy / ".git"), PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH=os.pathsep.join(filter(None, [str(TESTS), os.environ.get("PYTHONPATH")])))
            run = subprocess.run([sys.executable, "-m", "unittest", *SAMPLE], cwd=tmp, env=env,
                                 capture_output=True, text=True, timeout=600)
            self.assertEqual(state(decoy), before, "the checks changed the repository named by GIT_DIR")
            self.assertEqual(run.returncode, 0, run.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
