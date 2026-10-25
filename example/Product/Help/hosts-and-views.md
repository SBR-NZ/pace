# Assistants and dated views

## What assistants can do

Any assistant that can read your Pace folder can open `Pace.md`, then follow a link to the one help page or enabled add-in needed for a request. What it can **save** depends on its actual connection and permissions. Ask it to open the destination again before it calls something saved. A creation receipt alone is not read-back. A conversation or a downloaded file is not a cloud save.

- **Claude Code or another assistant with file replacement access on your computer:** can read, create and replace files as its permissions allow. It can run the local record and update tools if Python and (for updates) git are available. An installed local update is not proof that OneDrive has synced it.
- **Copilot through its OneDrive connection:** can read and create files, but cannot replace existing files there. It cannot install Product updates. If a task needs replacement, have someone with replacement access or client IT do it. Access to a private repository through Copilot is unverified; do not promise a pull from it.
- **ChatGPT:** file access and replacement depend on the particular connected tools and permissions. Direct private-repository access is unverified. Do not claim a save or install without a read-back from the intended destination.
- **Client IT:** may keep a central Product copy using its own change process. A central install needs its change reference, not a person's local go-ahead. Delivery to each user's device remains separate.

A host pointer (such as `AGENTS.md` or the Copilot pointer) only points to `Pace.md`. An optional add-in launcher does not switch an add-in on or grant a new connection, schedule or permission. The repository's instructions, not Pace, guide work inside a linked code repository.

## The owner's assistants

`3 My add-ins/Assistant setup.md` lists the assistants the owner uses and what each can reach: where it runs, how it reaches the Pace folder, its skills or plugins, its connections to other apps, any scheduled tasks, and what it cannot do. Read it when choosing how to do a task, for example which assistant has the Xero connection or can replace files, and when the owner asks what is set up. It is the owner's file, so updates never change it. Never put passwords, keys, tokens or account numbers in it.

To start it, or bring it up to date, an assistant writes down only what it can see of its own setup, such as the skills and connections it can use in this chat; it never guesses another assistant's. It shows the owner the lines it would add or change, and writes them only on the owner's yes, then reads the file back. It sets `Last checked:` to that day. An assistant that cannot replace files, such as Copilot through OneDrive, shows the owner the lines to paste instead. The health check notes when the file is missing or was last checked more than 90 days ago.

```text
# Assistant setup

What each assistant the owner uses can reach. Kept by the owner; Pace updates never change it. No passwords, keys, tokens or account numbers.

Last checked: 2026-10-26

## Claude

- Where it runs: claude.ai, the desktop app and the phone app.
- Reaches the Pace folder: through the desktop app, which can read and replace files.
- Skills and plugins: (one line each, with what it is for)
- Connections: (one line each, with what it can read or change)
- Scheduled tasks: (each one, with when it runs)
- Cannot: (anything the owner might expect it to do)

## Microsoft 365 Copilot

- Reaches the Pace folder: through OneDrive; can read and create files, but cannot replace them.
- Connections: (one line each)
```

## Optional dated views

Ask for a page when you want one. Keep it under `2 Views/`, for example `2 Views/2026-10-23-open-work.md` or `2 Views/2026-10-23-year-2026.md`. Give each page the date made, question and scope (including the year/date basis for a yearly list), record paths or request ids used, and a statement of what was actually searched. If the search was paged, follow every page for a full list; if a file could not be opened, a page was missed or cloud completeness was not established, label the view partial. For open work, follow corrections and show competing accounts rather than guessing a current state. The optional Open work add-in, when enabled, gives the steps for an exhaustive list. The line for it in the `Pace.md` index decides which file is used, which may be the owner's customised copy; see [Add-ins](add-ins.md).

The optional Project overview add-in, when enabled, makes its page as one self-contained HTML file from the template beside the file its index line names, for example `2 Views/2026-10-23-project-overview.html`. The same rules apply, except that its Searched line, which covers every record file, stands in for a request id on each item; the tool's result still gives the request ids of what needs attention and of anything recorded two ways. An assistant that can run Python makes it with the overview tool below; any other assistant that can create a file fills in the template by hand. The page needs no script or network; its only links jump to rows on the same page. An assistant that cannot create a file gives the overview in chat instead.

A view is a dated **snapshot of records**, never the place to change a job's state or store an owner decision. Make a new dated page next time; fix the underlying account through a new `Record/` correction. A saved page needs its own read-back. An old page may be out of date even when it was complete when made. Do not call a partial search a complete year or claim unseen files never existed. `2 Views/` is owner-controlled and outside Product, so installing a new release cannot replace it.

## The overview tool

`Product/Tools/pace_overview.py` makes the Project overview page, and the Weekly review add-in's list, from the records, with Python 3.9 or later and nothing else. Run it from the Pace folder. It reads every record and project with the record tool's own readers, follows corrections and withdrawals to each item's current account, works out the counts and order from the dates in the owner's time zone (from the `Time zone:` line in `Pace.md`, or this computer's when there is none), escapes every piece of record text and fills in the add-in's template. It changes no record. With `--save` it creates only a new page in `2 Views/`, never replacing a file, and reads it back.

```text
python3 Product/Tools/pace_overview.py --asked "<the owner's question>" --save
python3 Product/Tools/pace_overview.py --project <project id> --save
python3 Product/Tools/pace_overview.py --by-person --save
python3 Product/Tools/pace_overview.py --review
```

The first makes the every-project page, the second the page for one project and the projects inside it, and the third the by-person page. The owner's names come from the `Owner:` lines in `Pace.md`, as the records write them in `owed-by` and `for`; the words `owner` and `the owner` always count as the owner too. `--owner` adds another spelling for one run. With no `Owner:` line and no `--owner`, the result says that only work owed by `owner` counted as the owner's.

For a page, when the `Pace.md` index names a customised copy of the add-in, add `--template` with the path to that copy's `overview-template.html`. The tool takes only the style block, wordmark and footer from it: the sections, wording and 7-day window are always the add-in's own, so a copy that changes those is filled in by hand. A customised copy keeps its own style block through updates, so after one, compare it with the shipped template and carry over any new styles. When a copy's style block is from before the current page design and would leave the page unstyled, the tool uses the shipped template's styles and its result says so. Without `--save`, nothing is saved.

The fourth command gives the Weekly review add-in's list and saves nothing; add `--project <project id>` to review one project and the projects inside it. Its `groups` hold the items in the add-in's order, numbered from 1 across the list, each with a ready `line` for the chat, its current account's request id (`request`), its project, subject, text, who owes it, who it is for, its due date or how many days it has been open. Work recorded two ways comes first, with each account. `counts` gives the number in each group and `due_later` the number due after the next 7 days, which are left out of the list. It never takes `--save` or `--by-person`, and has no page, so `--template` makes no difference to it.

For a page, it prints one JSON object. `status` is `saved` only when the page was saved and read back; `placed-not-confirmed` means a file was created but may be incomplete or could not be read back as written, and `not-saved` or `not-made` means there is no page, with `message` saying why. It also gives the counts, what was new, done, cancelled or given a different due date in the last 7 days, what needs attention, anything recorded two ways, what was searched, anything that could not be read, any leftover copies of saved records under `housekeeping`, and any folders in `1 Projects/` with no `Pace project.md`.
