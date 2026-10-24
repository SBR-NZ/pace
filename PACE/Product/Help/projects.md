# Projects and repository references

Projects keep the owner's work in order. A project can sit inside a **parent project**, usually a client, or stand on its own, and a project can have projects of its own. Each has a **stable id** that records use to say which project they belong to.

## How projects are laid out

```text
Projects/
  Kowhai Books/                 <- parent project (a client), id kowhai-books
    Pace project.md
    Budget 2027/                <- project inside it, id kowhai-budget
      Pace project.md
      Documents/                <- this project's files
      Board pack/               <- a project inside that one, id kowhai-board-pack
        Pace project.md
        Documents/
  Garden plans/                 <- a project on its own, id garden-plans
    Pace project.md
    Documents/
```

- A project's own projects are folders beside its `Documents/`, as many levels down as the work needs. Two or three levels are usually enough, such as a client, a piece of work for it and one part of that, because every level makes the path of each file kept below it longer: see Long paths below.
- A project on its own needs no client and can still have its own `Documents/`.
- The folder name is the project's name. The owner can rename a folder at any time; the id inside does not change.

### Long paths

Each level adds its folder's name to the path of every file kept under it. Excel cannot open or save a file whose full path, from the drive letter, is longer than 218 characters, and other Office and Windows tools stop at about 260. A Pace folder kept in OneDrive already uses about 60 of them, such as `C:\Users\<name>\OneDrive - <Company>\PACE\`. So keep project folder names short, the lower down the shorter, and leave the rest of the room for the files. When the record tool makes a project, it reports how many characters are left inside its `Documents/` for folders and file names, counting the Pace folder's own place as at least that long, and warns when fewer than 100 are left. A project folder can be renamed at any time, since its id does not change.

## The project id

An id is short, lowercase letters, digits and single hyphens, up to 40 characters, such as `kowhai-books` or `kowhai-budget`. It is chosen once, never changed and never reused for another project. `none` is not an id: it is what a record uses when it belongs to no project.

The id lives in a small file, `Pace project.md`, in the project's folder. Like a record, it is created once and never edited:

```text
---
format: project-1
id: kowhai-budget
parent: kowhai-books
created: 2026-10-23T11:00:00+13:00
by: Claude Code
---

Budget for the 2027 year.
```

`parent` is the parent's id, or `none` for a project at the top. The line under the header is an optional purpose. Header lines follow the same rules as a record's, described in [Record format: record-1](record-format.md).

## Making a project

With the record tool: `python3 Product/Tools/pace_record.py project-new --id kowhai-budget --name "Budget 2027" --parent kowhai-books --by "Claude Code"`. The parent can be any project, at any level. It refuses an id that is already used, creates the folder with `Documents/` inside its parent's folder, writes `Pace project.md` as a new file and reads it back. It reports the same outcomes as a record save, with `path_room`, the characters left for paths inside `Documents/`, and a warning in its message when that is short. `projects` lists every project with its id, parent and folder.

By hand: check no other `Pace project.md` already uses the id, create the folder (inside its parent's folder when it has one), create `Pace project.md` as a new file, add a `Documents/` folder, and open the file again before calling it made. If the path to the new `Documents/` is long, as Long paths above describes, tell the owner and suggest a shorter name.

### Folders inside Documents/

When making a project, recommend a small set of folders for its `Documents/`, chosen from what the project is: two to four, each named for a kind of work. Leave out a catch-all such as `Other/`, which fills up and hides things. Do not make `Archive/`: it appears beside a working file when its first version goes out, as Documents and versions below describes.

1. If the owner has already confirmed a standard set for this type of project, it is a standing instruction in `Pace.md`. Use it, say so, and skip the next two steps.
2. Otherwise show the recommended set and ask whether to change any or add any.
3. Then ask whether this should be the standard set for this type of project. On the owner's yes in their own words, keep it as a standing instruction below the mark in the `## Standing instructions` section of `Pace.md`, and save a decision record of it, as [Records and source evidence](records.md) describes. For example: `- Client projects get these folders in Documents/: Deliverables/, Meetings/, Sources/.`

These are starting points, not rules. Client work might get `Deliverables/`, `Meetings/` and `Sources/`; an internal or personal project gets none until the owner asks. `Sources/` holds what other people send, kept exactly as received and never edited, so a client's marked-up copy goes there, never over the working file.

With the record tool, give `--folder` once for each folder: `python3 Product/Tools/pace_record.py project-new --id kowhai-plans --name "Plans" --parent kowhai-books --folder Deliverables --folder Meetings --folder Sources --by "Claude Code"`. It refuses a name it cannot use, `Archive` or the same name twice before it makes anything, and lists the folders it made and checked. By hand: make each folder inside `Documents/`, and check it is there before calling it made.

## Owner, target and status

Who leads a project, the date it is aiming for and where it stands change over time, so they are kept in records, never in `Pace project.md`. Save a `change` record for the project with any of these header lines:

- `owner`: who leads the project now, written as records write names in `owed-by`, such as `Ana Ruiz`, or `owner` for the owner;
- `target`: the date the project is aiming for, a real calendar date such as `2026-11-27`;
- `status`: a short line in words, such as `Waiting on the wage sign-off`. Say what is true; leave out on-track, at-risk or colour ratings. Its date is the record's own.

Each stands until a `change` record for the same project that was first recorded later sets it again, and `none` clears it. Only current accounts count, so corrections and withdrawals work as for any record, and correcting a change fixes that change without making it the newest. When a change is recorded two ways and its accounts give different values, that value shows as recorded two ways until the owner says which stands. A target that is not a real date is not used, and the Project overview says so. The text below the header says the same thing in a sentence, and `from` says whose words it is, as for any record.

With the record tool: `python3 Product/Tools/pace_record.py create --request <request> --project kowhai-budget --kind change --subject "Budget 2027" --from owner --words "Ana leads the budget now, and we are aiming for 27 November." --owner "Ana Ruiz" --target 2026-11-27 --status "Waiting on the wage sign-off" --by "Claude Code" --body "Ana Ruiz leads the 2027 budget; the target is 27 November, and it is waiting on the wage sign-off."`. The Project overview shows each project's owner, target and status.

## When something does not fit

Listing projects reports, rather than guesses:

- the same id in two folders (ask the owner which is right);
- a project whose `parent` does not match the folder it sits in;
- a `Pace project.md` that cannot be read;
- folders with no `Pace project.md`, which are simply not projects yet. One that holds a project somewhere inside is not listed itself, but the project inside is reported; a folder inside a listed one is not listed again. Folders whose names start with a dot, such as `.git`, are left out unless they hold a `Pace project.md`, and so is a project's `Documents/` folder, whatever the case of its name;
- a folder that cannot be read, or one with no `Pace project.md` that holds more than 500 folders, which is named rather than taken as empty. So that every command stays quick, no more than 5,000 folders with no `Pace project.md` are looked into in all, and nothing more than 40 levels below `Projects/`; anything past either is named too. A new project's folder name cannot start with a dot, since that hides the folder on some computers.

A record whose project id has no matching folder is still shown, with that gap named.

Whenever projects are listed, for example when making a project, in a project overview or in a daily brief, name any folder that has no `Pace project.md` and ask the owner what it is. A folder directly in `Projects/` can be made a project, or left as it is. A folder beside `Documents/` inside a project can be made a project inside it, or moved into its `Documents/`. Make or move nothing without the owner's yes.

## Documents and versions

A project's `Documents/` can be arranged in whatever folders suit the owner. Wherever a file sits, two rules keep the right file easy to find and keep every version that went out.

**One working file for each piece of work.** It sits at the top of its folder under a name that stays the same, with no version, date or status in it, so links to it from other files, reports and shortcuts keep working. To change a piece of work, open its working file, never a copy in `Archive/`.

**A dated copy of each version that goes out.** A version is the working file as it was when it was sent, presented, filed or signed off. Saving as you work does not make a version; storage such as OneDrive may keep its own history of saves, but Pace does not read it or rely on it. Each version is a copy in an `Archive/` folder beside the working file, named `YYYY-MM-DD <name> v<N>.<extension>`: the day it went out (in the owner's time zone when `Pace.md` names one), the working file's name and the version number. The date comes first, so the folder lists versions in the order they went out.

```text
Documents/
  Budget 2027.xlsx                    <- the working file
  Archive/
    2026-11-04 Budget 2027 v1.xlsx    <- the workbook sent to the board
    2026-11-04 Budget 2027 v1.pdf     <- the PDF of it that was sent too
    2026-11-18 Budget 2027 v2.xlsx
```

### Keeping a version

1. Make the copy when the work goes out, before anything else changes the working file. If the working file has already changed, copy what actually went out instead, such as the email attachment, and say so in the record.
2. Create `Archive/` beside the working file if it is not there. The version number is one more than the highest already there for this piece of work, or `v1` for the first. Each file that went out gets its own copy, with the same date and number.
3. Copy each file in as a new file. Never overwrite: if a file with that name is already there, stop and tell the owner.
4. Open the copy again and check it is what went out before calling the version kept.
5. Save a `result` record that names each copy in `source` with its fingerprint, as [Records and source evidence](records.md) describes. Use the piece of work's name as the subject every time, so a search by that subject finds every version. `from` is whoever said it went out, usually the owner in their own words.

With the record tool, `--source-file` adds the copy's place and fingerprint, and `find` lists the versions newest first:

```text
python3 Product/Tools/pace_record.py create --request <request> --project kowhai-budget --kind result --subject "Budget 2027" --from owner --words "The budget went to the board this morning." --source-file "Projects/Kowhai Books/Budget 2027/Documents/Archive/2026-11-04 Budget 2027 v1.xlsx" --by "Claude Code" --body "Version 1 of the 2027 budget went to the board on 4 November."
python3 Product/Tools/pace_record.py find --project kowhai-budget --kind result --subject "Budget 2027"
```

### What never changes

- A copy in `Archive/` is never edited, renamed, moved or replaced. If one turns out to be wrong, leave it and save a record that corrects that version's record, saying what is wrong.
- The fingerprint in the record shows whether a copy has changed since it was kept: compare it with the copy's SHA-256 now.
- Leave words such as final, approved or signed off out of file names. They stop being true, and a file name is never anyone's approval. Whether a version was approved belongs in a record; the owner's go-ahead on that exact file follows [Exact-act confirmations](confirmations.md).
- Do not keep a list of which file is current. The place says it: a file at the top of its folder is the working file, a file in `Archive/` is a version that went out, and the records hold the history.

### Hosts and repositories

Keeping a version only creates a folder, files and a record. Nothing is moved, renamed or deleted, so it works where a host can create files but not replace or delete them. Such a host cannot update a working file, though: it says so and gives the owner the new content to put in place, rather than saving a second working file beside the first.

Files kept in a git repository have their versions in git, so this section does not apply to them. See [Repository references and coding sessions](repositories.md).

## Repository references

`Repos/` uses the same project names and stable ids, with one home per repository and explicit links from any other project that uses it. Prefer links over checkouts. [Repository references and coding sessions](repositories.md) shows the format and how to keep a job's status, branch or link and outcome in the project's records. The repository's own instructions govern coding.
