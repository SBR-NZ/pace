#!/usr/bin/env python3
"""Copy the newest released PACE folder into a chosen location (Python and git only)."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True

TOOL = Path(__file__).resolve().parent / "PACE/Product/Tools/pace_update.py"
spec = importlib.util.spec_from_file_location("pace_update_for_download", TOOL)
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


def get_pace(to: Path, repo: str) -> tuple[str, str]:
    """Create only to/PACE, with a release note of where it came from; leave existing folders untouched."""
    parent = to.expanduser().resolve()
    if not parent.is_dir():
        raise update.Stop(f"{parent} is not a folder. Create it first, then try again.")
    destination = parent / "PACE"
    if destination.exists() or destination.is_symlink():
        raise update.Stop(f"{destination} already exists. Do not copy over it. Use its Product updater to preview an update instead.")
    tag, commit = update.latest_release(repo)
    release = update.fetch_release(repo, tag, commit, folder="PACE", legacy_folder="starter")
    # An exclusive create prevents a second download from replacing an existing copy.
    try:
        destination.mkdir()
    except FileExistsError:
        raise update.Stop(f"{destination} already exists. Use its Product updater instead.") from None
    try:
        for name, data in release["files"].items():
            update._write_new(destination / name, data)
        if update.read_tree(destination) != release["entries"]:
            raise update.Stop("The copied files did not read back as the release's files.")
        update.note_first_copy(destination, repo, tag, commit)
    except BaseException:
        update._remove_tree(destination)
        raise
    return tag, commit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Get the newest released PACE folder without touching an existing copy.")
    parser.add_argument("--to", required=True, help="existing destination folder that will receive PACE/")
    parser.add_argument("--repo", default=update.DEFAULT_REPO, help="release repository (default: the Pace repository)")
    args = parser.parse_args(argv)
    try:
        tag, commit = get_pace(Path(args.to), args.repo)
    except (update.Stop, OSError) as error:
        print(f"Not copied: {error}")
        return 1
    print(f"Copied PACE from release {tag}, full commit {commit}, into {Path(args.to).expanduser().resolve() / 'PACE'}.")
    print(f"Where it came from and which release it is are noted in PACE/{update.RELEASE_RECORD}/{update.NOTE}.")
    print("Open PACE/Pace.md to begin, and in your first chat ask your assistant to set up Pace with the Getting started "
          "add-in. To check for a later release, run from the PACE folder: "
          "python3 Product/Tools/pace_update.py preview --root . --latest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
