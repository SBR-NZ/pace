# Projects and repository references

Projects keep the owner's work in order. A project can sit inside a **parent project**, usually a client, or stand on its own. Each has a **stable id** that records use to say which project they belong to.

## How projects are laid out

```text
Projects/
  Kowhai Books/                 <- parent project (a client), id kowhai-books
    Pace project.md
    Budget 2027/                <- project inside it, id kowhai-budget
      Pace project.md
      Documents/                <- this project's files
  Garden plans/                 <- a project on its own, id garden-plans
    Pace project.md
    Documents/
```

- There are only two levels: a parent and the projects inside it. A project inside a parent cannot have projects of its own.
- A project on its own needs no client and can still have its own `Documents/`.
- The folder name is the project's name. The owner can rename a folder at any time; the id inside does not change.

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

With the record tool: `python3 Product/Tools/pace_record.py project-new --id kowhai-budget --name "Budget 2027" --parent kowhai-books --by "Claude Code"`. It refuses an id that is already used, creates the folder with `Documents/`, writes `Pace project.md` as a new file and reads it back. It reports the same outcomes as a record save. `projects` lists every project with its id, parent and folder.

By hand: check no other `Pace project.md` already uses the id, create the folder (inside its parent's folder when it has one), create `Pace project.md` as a new file, add a `Documents/` folder, and open the file again before calling it made.

## When something does not fit

Listing projects reports, rather than guesses:

- the same id in two folders (ask the owner which is right);
- a project whose `parent` does not match the folder it sits in;
- a `Pace project.md` that cannot be read;
- folders with no `Pace project.md`, which are simply not projects yet.

A record whose project id has no matching folder is still shown, with that gap named.

## Repository references

`Repos/` uses the same project names and stable ids, with one home per repository and explicit links from any other project that uses it. Prefer links over checkouts. [Repository references and coding sessions](repositories.md) shows the format and how to keep a job's status, branch or link and outcome in the project's records. The repository's own instructions govern coding.
