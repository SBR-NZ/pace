# Health check

The health check looks over the whole Pace folder at once and says what, if anything, needs doing. It only reads: it writes, moves and deletes nothing, so it is safe to run at any time, for example when something seems wrong, after an update, or before Pace is set up for someone else.

## Running it

An assistant that can run Python 3.9 or later runs it from the Pace folder:

```text
python3 Product/Tools/pace_check.py
python3 Product/Tools/pace_check.py --latest
```

The second also asks the release repository named in `Release record/Installed release.md`, with git, which release is newest. Nothing is fetched or installed; installing still needs the owner's go-ahead, as [Product updates](updates.md) describes.

It prints one JSON object. `status` is `healthy` when nothing needs doing, `attention` when something should be fixed soon and `problems` when something needs fixing; `message` says it in plain words. `findings` lists each thing found, problems first, each with its level, what was found and what to do (`fix`). `checked` says what was looked at. It checks this computer's copy only, not whether OneDrive or another cloud copy has every file. The exit code is 0 only when the status is `healthy`.

## What it checks

- **Folders:** `Record/`, `1 Projects/`, `Product/` and `Release record/` are there, and no folder still has its name from before release 3.11.0.
- **Pace.md:** that it can be read and records Pace's parts as shipped, which parts the owner has changed, the `Owner:` and `Time zone:` lines, that every add-in index line opens a file that is there, and any line naming a folder by its old name.
- **Records:** every file in `Record/` is opened. It names second copies, files that are not records, records that do not follow [the record format](record-format.md), corrections of records that are missing, corrections that loop, items recorded two ways, targets that are not real dates, and project ids that no project has. A save's leftover temporary file is named as harmless when it reads the same as its record. From 4,000 items it notes how close `Record/` is to 5,000, past which OneDrive's web pages show a folder slowly or with errors. It is only a note: syncing and Pace's tools work the same at any size.
- **Projects and repository references:** a `Pace project.md` that cannot be read, two folders with one id, projects in the wrong parent, folders in `1 Projects/` with no `Pace project.md`, and references in `Repos/` whose project id no project has or that are not in their project's place.
- **The release and Product:** that the release note can be read, whether an update was left part-way, and whether files inside `Product/` differ from the installed release, which the next update would replace.
- **The owner's assistant setup:** whether `3 My add-ins/Assistant setup.md` is there, and whether it was checked in the last 90 days.
- **A new folder:** one whose `Record/` and `1 Projects/` are both empty is pointed to the Getting started add-in. A folder that could not be read in full is never called new.

## Acting on what it finds

Show the owner the findings, problems first, with what to do about each. Fix nothing on the check's say-so alone: renaming or moving a folder, changing `Pace.md`, settling an item recorded two ways or deleting a leftover file each needs the owner's yes, and a saved record is never edited, only corrected, as [Records and source evidence](records.md) describes. A note needs no action unless the owner wants it.

An assistant that cannot run Python can make the same checks by hand from this page, one at a time, and says which it could not make.
