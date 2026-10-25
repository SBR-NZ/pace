# Projects and repository references

Projects keep the owner's work in order. A project can sit inside a **parent project**, usually a client, or stand on its own, and a project can have projects of its own. Each has a **stable id** that records use to say which project they belong to.

## How projects are laid out

```text
1 Projects/
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
- a folder that cannot be read, or one with no `Pace project.md` that holds more than 500 folders, which is named rather than taken as empty. So that every command stays quick, no more than 5,000 folders with no `Pace project.md` are looked into in all, and nothing more than 40 levels below `1 Projects/`; anything past either is named too. A new project's folder name cannot start with a dot, since that hides the folder on some computers.

A record whose project id has no matching folder is still shown, with that gap named.

## Repository references

`Repos/` uses the same project names and stable ids, with one home per repository and explicit links from any other project that uses it. Prefer links over checkouts. [Repository references and coding sessions](repositories.md) shows the format and how to keep a job's status, branch or link and outcome in the project's records. The repository's own instructions govern coding.
