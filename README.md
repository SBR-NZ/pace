# Pace by SBR

Pace is made by SBR (Simply Better Reports). PACE is one folder that keeps your projects, records, Pace help and optional add-ins together. You keep your own copy of it in a place you choose, outside this repository. Each published release is a numbered tag, such as `v3.5.0`, and the steps below always find the newest one.

## Get PACE

You need Python 3, git and a copy of this repository on your computer (`git clone https://github.com/SBR-NZ/pace.git`). From the repository folder, run one command, replacing `<place>` with an existing folder you choose:

```text
python3 get-pace.py --to <place>
```

It finds the newest release, shows its tag and full commit, and creates `<place>/PACE` holding only the PACE folder. It also writes `PACE/Release record/Installed release.md`, which notes where the release came from and which release it is, so a later update check needs nothing typed in. If `<place>` already has a PACE folder, it stops and changes nothing; update that folder instead. Open `PACE/Pace.md` when you start a chat; it links to the rest of the help.

## Update PACE

From your PACE folder, check for a newer release:

```text
python3 Product/Tools/pace_update.py preview --root . --latest
```

It reads where releases come from in `Release record/Installed release.md`, finds the newest release and compares it with the one installed. A preview installs nothing. It shows the release tag, its full commit and what would change. To install, the owner gives their own go-ahead naming that exact tag and commit (an assistant cannot give it for them), then run:

```text
python3 Product/Tools/pace_update.py apply --root . --repo https://github.com/SBR-NZ/pace.git --tag <tag> --commit <full commit> --go-ahead "<the owner's own words naming the tag and full commit>"
```

An update replaces only `Product/`, then adds the new release to the end of `Release record/Installed release.md`. It keeps Pace's own parts of `Pace.md` current, but never changes your lines there, your projects, records or add-in choices, and it stops if the release has moved. A folder made before version 3.7.0 has no such note until an install by the 3.7.0 or later updater writes it; until then, if the preview asks for the repository, add `--repo https://github.com/SBR-NZ/pace.git`. If your folder has v3.5.0 or older, its own updater cannot find newer releases: run both commands with `PACE/Product/Tools/pace_update.py` from this repository instead, still from your folder with `--root .` and with that `--repo`, until the update is installed. [Product update help](PACE/Product/Help/updates.md) explains the exact-act confirmation route; client IT and mirrors are covered in the [technical update notes](docs/updates.md).

## Also in this repository

`example/` is a fully invented PACE folder for illustration; never use it as your own. The [folder map](docs/layout.md) explains what each folder is for. `VERSION` and `CHANGELOG.md` describe this source, not a release or an installation. The invented-data checks run with `python3 -m unittest discover -s tests`.

## Licence

Pace is licensed under the [PolyForm Shield License 1.0.0](LICENSE). In short: you may use Pace, change it and share it, including in your own business, but not to provide anything that competes with Pace or with what SBR provides using Pace, such as selling or rebranding Pace, or offering to set it up for others. Anyone you pass a copy to must get the licence and its `Required Notice:` line, which every Pace folder carries in `Product/LICENSE.md`. This is a summary; the licence text is what applies. Copyright 2026 Simply Better Reports Limited, trading as SBR.
