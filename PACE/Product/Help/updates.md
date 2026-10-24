# Product updates

An update brings in a newer version of Pace's own files: the help, the shipped add-ins and the updater. It replaces the `Product/` folder and keeps Pace's own parts of `Pace.md` current. Everything that is yours stays exactly as it is.

## Checking for an update

`Release record/Installed release.md` notes where this PACE folder gets its releases and which release is installed: the release repository, the installed tag and full commit, when it was copied or installed and, for a client copy, the upstream release. `get-pace.py` writes it when it makes the folder, and each install adds an entry at the end, so the last entry is the release installed now. Updates never replace it.

When the owner asks to check for an update, nothing needs to be typed in:

1. Read `Release record/Installed release.md` to see the installed release and where releases come from.
2. From the PACE folder, run `python3 Product/Tools/pace_update.py preview --root . --latest`. It reads the repository from the note, finds the newest release and compares it with the installed one. Nothing is installed or recorded.
3. Tell the owner what it found. Installing needs the owner's own go-ahead or exact-act confirmation, as described below.

If the note is missing or cannot be read, the updater says so and does not guess. Ask the owner, or whoever set up Pace, for the release repository address and add `--repo <address>`. A folder made before version 3.7.0 has no note until its next install. Giving `--repo` always overrides the note, for example to try your organisation's own copy.

## What an update never changes

- Your lines in `Pace.md`: everything below a "Your lines" mark, such as the add-in index lines, standing instructions and the time zone line, any part of `Pace.md` you have changed, and any section you added. See [Pace.md](#pacemd) below.
- `Record/`, `Projects/`, `Repos/` and optional `Views/`.
- `My add-ins/`, so your own and customised add-ins, and `Pace/Add-ins/My add-ins/` in an older folder that still keeps them there. An update never moves them; [Add-ins](add-ins.md#add-ins-in-an-older-folder) says how to move them to `My add-ins/` if the owner wants to.
- The host pointers `AGENTS.md`, `CLAUDE.md` and `.github/copilot-instructions.md`.

Shipped add-ins in `Product/Pace add-ins/` update with Product. A customised copy in `My add-ins` never does; you can ask to compare it with the new shipped version and adopt what you want. If a release removes a Product file that `Pace.md` points to, the preview says so and you decide what to use instead.

## Pace.md

`Pace.md` is mostly Pace's own text, in parts that each start at a heading. Three parts end with a mark, `<!-- Your lines go below this one. Pace updates never change them. -->`: the add-in index lines, standing instructions and the time zone line go below it. The last line of `Pace.md` records each part as Pace shipped it, so an update can tell which parts you have changed. An update:

- replaces a Pace part only while it is exactly as Pace shipped it, and keeps a part you have changed, so you can compare it with the release's wording yourself;
- adds a part a release introduces, but not one you removed;
- removes a part Pace no longer ships, unless you changed it or put your own lines in it, in which case it stays as yours;
- never changes your lines, or a section you added yourself.

The preview lists what would change in `Pace.md`, and the go-ahead covers it: a proposal from `prepare` includes the change, so editing `Pace.md` after it means preparing and confirming again. After Product is installed and recorded, the updater writes the new `Pace.md`, reads it back and adds a line to the install receipts. If that fails, Product stays installed and `Pace.md` is put back as it was. Applying the same release again brings `Pace.md` up to date without touching Product.

A `Pace.md` from before these marks existed does not record its parts, so updates leave it as it is. To start, take the release's `Pace.md` and put the owner's own lines back below each mark, with the owner's go-ahead.

## Where a release comes from

A release is a named tag, such as `v3.5.0`, in the Pace repository or in your organisation's own copy of it. Each tag is pinned to one full commit id, a 40-character code that fixes the exact files. Use `preview --latest` to find the newest numbered release in the repository the release note names and show its tag and full commit. To install, use that exact tag and commit, so a later release cannot slip in after you looked. Pace never installs from a branch such as `main`. The updater also still reads the published v3.5.0 release, which kept its files under an older folder name.

The update stops, and nothing changes, if:

- the tag has moved to a different commit;
- the pinned commit is missing from the repository;
- the release's files do not match its file list; or
- an organisation's copy is said to match an upstream release but its Product files differ.

## The three steps

1. **Preview.** The updater fetches the release, checks the tag still points to the pinned commit and lists what would be added, changed and removed in Product, and which parts of `Pace.md` would change. Nothing is installed or recorded.
2. **Go-ahead.** For your own folder, after preview use `prepare` to save an exact proposed install under `Release record/Proposals/`. It names the destination, source repository, tag, full commit, Product file-list fingerprint and before-and-after. Show that file and the preview to the owner. With the owner's own current words, use the [exact-act confirmation](confirmations.md) tool to save a confirmation in `Record/`. Give its request id to `apply` with `--confirmation-request`. The updater checks the record's read-back, current status and exact proposed bytes against the update it is about to install. If anything changed, stop and ask again. A yes from the assistant or a quote from a source is not the owner's go-ahead. The earlier simple JSON `--go-ahead` and `--go-ahead-record` routes remain available, but are not exact-act confirmations. They require the owner's own words naming tag and full commit. Do not pass two go-ahead routes at once.
3. **Apply.** The updater copies the release into a holding folder, swaps it in for the old Product, reads every installed file back, and checks that nothing outside Product changed. Anything it is not allowed to read, such as a host app's own folder, is named as not checked instead of stopping the update. Then it writes the record. If anything fails, it puts the previous Product back. Last, it brings Pace's parts of `Pace.md` up to date, as described above.

For a central copy that your organisation's IT team keeps for its users, IT uses its own change control instead of your go-ahead, and the IT change reference is recorded.

## What "installed" means

The updater reports **installed locally** only after reading the new files back from the disk of the computer that ran it. That is not the same as **arrived in OneDrive**. OneDrive may still be uploading, and another device may not have the files yet. Check OneDrive itself, for example its sync icon or the folder on the web, before saying the update has reached OneDrive or your other devices.

## Copilot can only suggest an update

Copilot's OneDrive connection can create new files but cannot replace existing ones, so Copilot cannot install an update. Copilot can read `Release record/Installed release.md` to say which release is installed and where releases come from. In Copilot, Pace can only suggest an update: name the release and say it needs to be installed with the updater on a computer that can replace files, such as a terminal or Claude Code on a PC where the Pace folder syncs, or by your IT team. A downloaded copy of a release is not an installed update. Other hosts' access to a private repository, or to replace files in the cloud directly, is not promised.

## The release record

`Release record/` sits outside Product and holds:

- `Installed release.md` - where releases come from and which release is installed now (format `pace-release-note/1`). Entries are only ever added at the end; a rolled-back update adds none.
- `Install receipts.md` - one short line per update attempt. Lines are only ever added, never changed.
- `Installs/` - one full record per attempt: the repository, tag, full commit, Product file list and its digest, the version it replaced, the time, the result, and the go-ahead or IT change reference. A later record can correct an earlier one; the earlier file is left as it was.
- `Go-aheads/` - simple owner go-aheads, each in its own file, if that route was used.
- `Proposals/` - saved exact local install proposals; `Record/` holds any matching confirmation. A receipt names its confirmation request when used.

## If something goes wrong

- **Interrupted part-way**, for example the computer shut down: a folder `Release record/Update in progress/` is left behind. Run apply again with only the Pace folder named. It puts the previous Product back, checks it, and records that the update was rolled back. Do not move files by hand.
- **The updater says this computer or session cannot rename or delete files:** some assistant sessions linked to your folder can create files but not replace them, and an update needs to. Nothing was installed or recorded. Install the update with the updater on a computer that can replace files in the Pace folder, such as a terminal or Claude Code on a PC where the folder syncs. If it names a check file in `Release record/` that it could not delete, that file is harmless; the next run on such a computer deletes it. Files an earlier attempt left in `Release record/Update in progress/` before it changed anything do not stop a preview, and that run removes them too.
- **An update finished but left its work files**, for example because OneDrive or a virus scanner held a file open while they were being removed: the install, or its roll-back, is complete and recorded. Preview says so. Once nothing holds the files open, run apply with only the Pace folder named to tidy them.
- **The updater stops with a file error on a folder it may not read**, such as the Claude desktop app's own `Claude/` folder seen from the app's Linux sandbox: nothing was installed. From 3.9.1 the updater names such a folder as not checked and goes on. If the installed updater is older, install with the new release's own updater, as described under Running it for older folders.
- **The updater says it needs help:** it could not confirm the roll-back, or it found work files it cannot account for. The Product from before the update may be in `Release record/Update in progress/previous/Product`. Leave everything there and ask whoever supports your Pace setup.
- **Files inside Product were edited:** Product is replaced as a whole, so the updater stops and lists them. In a folder made by `get-pace.py` that has not been updated since, it can say only that files changed, not which, because the release note keeps a fingerprint rather than a file list. Copy anything worth keeping into `My add-ins` first, or say you are happy for them to be replaced. If `Installed release.md` keeps no Product file list, which happens only when it was written by hand, the updater cannot tell whether anything was edited. It says so and asks for the same choice, unless Product already holds exactly the new release.

## What these checks do and do not show

Pinning the commit and checking the file list stop a wrong, moved or partial version from being installed. They do not prove who published a release or that an account was never misused, and a file checksum is not a signature. There are no signatures, keys or publisher in Pace. Your IT team can add its own review before it chooses a release.

## Running it

Whoever runs the update needs git and Python 3.9 or later on a computer that can replace files in the Pace folder. Run it from the Pace folder itself, not from inside `Product`:

```text
python3 Product/Tools/pace_update.py preview --root . --latest
python3 Product/Tools/pace_update.py prepare --root . --repo <repository> --tag <tag> --commit <full commit>
python3 Product/Tools/pace_record.py propose --act "Install this pinned release into my local Pace Product" --act-file "<act file from prepare>"
python3 Product/Tools/pace_record.py new-request --project none
python3 Product/Tools/pace_record.py confirm --request <request> --project none --subject "Local Product update" --act "Install this pinned release into my local Pace Product" --act-file "<act file from prepare>" --shown-sha256 <fingerprint from propose> --source "<preview and local before-and-after shown to owner>" --owner-words "<the owner's current words>" --owner-current --by "<assistant or person>"
python3 Product/Tools/pace_update.py apply --root . --repo <repository> --tag <tag> --commit <full commit> --confirmation-request <request>
python3 Product/Tools/pace_update.py apply --root .
```

In the later lines, use the repository, tag and full commit the preview showed. The last line only recovers an interrupted update. If your folder has v3.5.0 or older installed, its own updater cannot find newer releases: run the same commands with `PACE/Product/Tools/pace_update.py` from a current copy of the Pace repository, still with `--root` set to your folder and with `--repo` naming the release repository, until the newer Product is installed. A Pace folder made before the updater existed can do the same. Options for central IT copies, forks and mirrors are listed with `--help` and in the repository's `docs/updates.md`.
