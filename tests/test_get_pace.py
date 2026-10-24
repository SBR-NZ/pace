"""First copy and newest-release previews using invented local repositories only."""

import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from test_updates import GIT_ENV, Repo, git, pu, tree_bytes
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("get_pace", ROOT / "get-pace.py")
get = importlib.util.module_from_spec(spec)
spec.loader.exec_module(get)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pace-release-test-")
        self.env = mock.patch.dict("os.environ", GIT_ENV)
        self.env.start()
        self.base = Path(self.tmp.name)
        self.repo = Repo(self.base / "releases")
        self.repo.write("starter/Pace.md", "# Invented older copy\n")
        self.repo.write("starter/Product/Help/updates.md", "Old Product\n")
        self.old = self.repo.commit("Invented older release")
        self.repo.tag("v3.5.0")
        self.repo.write("PACE/Pace.md", "# Invented new copy\n")
        self.repo.write("PACE/Product/Help/updates.md", "New Product\n")
        self.repo.write("PACE/Record/.gitkeep", "")
        self.new = self.repo.commit("Invented newer release")
        self.repo.tag("v3.6.0")
        git(self.repo.path, "tag", "v3.4.0", self.old)  # lightweight tag
        git(self.repo.path, "tag", "v9.0.0-rc1", self.new)  # not a stable release
        self.repo.write("PACE/Pace.md", "# Unreleased work\n")
        self.repo.commit("Unreleased work")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_first_copy_gets_latest_release_only_and_refuses_overwrite(self):
        place = self.base / "chosen place"
        place.mkdir()
        self.assertEqual(get.get_pace(place, str(self.repo.path)), ("v3.6.0", self.new))
        self.assertEqual((place / "PACE/Pace.md").read_text(), "# Invented new copy\n")
        self.assertFalse((place / "PACE/README.md").exists())
        self.assertFalse((place / "PACE/starter").exists())
        before = tree_bytes(place)
        with self.assertRaisesRegex(get.update.Stop, "already exists"):
            get.get_pace(place, str(self.repo.path))
        self.assertEqual(tree_bytes(place), before)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = get.main(["--to", str(place), "--repo", str(self.repo.path)])
        self.assertEqual(code, 1)
        self.assertIn("updater", output.getvalue())

    def test_first_copy_of_older_release_becomes_a_PACE_folder(self):
        git(self.repo.path, "tag", "-d", "v3.6.0")
        place = self.base / "chosen place"
        place.mkdir()
        self.assertEqual(get.get_pace(place, str(self.repo.path)), ("v3.5.0", self.old))
        self.assertEqual((place / "PACE/Pace.md").read_text(), "# Invented older copy\n")
        self.assertEqual((place / "PACE/Product/Help/updates.md").read_text(), "Old Product\n")

    def test_installed_older_product_can_update_from_both_paths(self):
        root = self.base / "PACE"
        shutil.copytree(self.repo.path / "starter", root)
        preview_old = pu.preview(root, str(self.repo.path), "v3.5.0", self.old)
        self.assertEqual(preview_old["commit"], self.old)
        preview_new = pu.preview(root, str(self.repo.path), "v3.6.0", self.new)
        self.assertEqual(preview_new["changes"]["changed"], ["Help/updates.md"])
        with self.assertRaisesRegex(pu.Stop, "go-ahead"):
            pu.apply(root, str(self.repo.path), "v3.6.0", self.new)
        result = pu.apply(root, str(self.repo.path), "v3.6.0", self.new,
                          go_ahead=f"Install v3.6.0 at commit {self.new}.")
        self.assertEqual(result["status"], "installed")
        self.assertEqual((root / "Pace.md").read_text(), "# Invented older copy\n")
        self.assertEqual((root / "Product/Help/updates.md").read_text(), "New Product\n")
        self.assertEqual(pu.preview(root, str(self.repo.path), "v3.5.0", self.old)["commit"], self.old)

    def test_latest_preview_pins_full_commit_and_does_not_install(self):
        root = self.base / "PACE"
        shutil.copytree(self.repo.path / "starter", root)
        before = tree_bytes(root)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pu.main(["preview", "--root", str(root), "--repo", str(self.repo.path), "--latest"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("v3.6.0", out.getvalue())
        self.assertIn(self.new, out.getvalue())
        self.assertIn(f"use exactly --repo {self.repo.path} --tag v3.6.0 --commit {self.new}", out.getvalue())
        self.assertEqual(tree_bytes(root), before)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pu.main(["preview", "--root", str(root), "--repo", str(self.repo.path),
                                      "--latest", "--tag", "v3.5.0"]), 1)
        self.repo.tag("v3.6.0", self.old, force=True)
        with self.assertRaisesRegex(pu.Stop, "has moved"):
            pu.apply(root, str(self.repo.path), "v3.6.0", self.new,
                     go_ahead=f"Install v3.6.0 at commit {self.new}.")
        self.assertEqual(tree_bytes(root), before)

    def test_latest_compares_release_numbers_not_text(self):
        git(self.repo.path, "tag", "v3.10.0", self.new)
        git(self.repo.path, "tag", "v3.9.0", self.old)
        git(self.repo.path, "tag", "release-99", self.old)
        self.assertEqual(pu.latest_release(str(self.repo.path)), ("v3.10.0", self.new))

    def test_first_copy_of_this_repositorys_PACE_folder_is_exact(self):
        source = ROOT / "PACE"
        shutil.rmtree(self.repo.path / "PACE")
        shutil.copytree(source, self.repo.path / "PACE", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        commit = self.repo.commit("Invented release of this repository's PACE folder")
        self.repo.tag("v3.7.0")
        place = self.base / "chosen place"
        place.mkdir()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = get.main(["--to", str(place), "--repo", str(self.repo.path)])
        self.assertEqual(code, 0, output.getvalue())
        self.assertIn(f"release v3.7.0, full commit {commit}", output.getvalue())
        copied = tree_bytes(place / "PACE")
        note = copied.pop("Release record/Installed release.md")  # the one file get-pace.py adds
        self.assertEqual(copied, tree_bytes(self.repo.path / "PACE"))
        self.assertIn(f"- Full commit: {commit}\n".encode(), note)
        self.assertTrue((place / "PACE/.github/copilot-instructions.md").is_file())
        self.assertEqual(sorted(p.name for p in place.iterdir()), ["PACE"])

    def test_missing_new_path_never_uses_legacy_path_for_other_tags(self):
        self.repo.tag("v3.6.0", self.old, force=True)
        with self.assertRaisesRegex(pu.Stop, "no PACE/Product"):
            pu.fetch_release(str(self.repo.path), "v3.6.0", self.old)
        with self.assertRaisesRegex(pu.Stop, "no PACE folder"):
            pu.fetch_release(str(self.repo.path), "v3.6.0", self.old, folder="PACE", legacy_folder="starter")


if __name__ == "__main__":
    unittest.main()
