# Assistants and dated views

## What assistants can do

Any assistant that can read your Pace folder can open `Pace.md`, then follow a link to the one help page or enabled add-in needed for a request. What it can **save** depends on its actual connection and permissions. Ask it to open the destination again before it calls something saved. A creation receipt alone is not read-back. A conversation or a downloaded file is not a cloud save.

- **Claude Code or another assistant with file replacement access on your computer:** can read, create and replace files as its permissions allow. It can run the local record and update tools if Python and (for updates) git are available. An installed local update is not proof that OneDrive has synced it.
- **Copilot through its OneDrive connection:** can read and create files, but cannot replace existing files there. It cannot install Product updates. If a task needs replacement, have someone with replacement access or client IT do it. Access to a private repository through Copilot is unverified; do not promise a pull from it.
- **ChatGPT:** file access and replacement depend on the particular connected tools and permissions. Direct private-repository access is unverified. Do not claim a save or install without a read-back from the intended destination.
- **Client IT:** may keep a central Product copy using its own change process. A central install needs its change reference, not a person's local go-ahead. Delivery to each user's device remains separate.

A host pointer (such as `AGENTS.md` or the Copilot pointer) only points to `Pace.md`. An optional add-in launcher does not switch an add-in on or grant a new connection, schedule or permission. The repository's instructions, not Pace, guide work inside a linked code repository.

## Optional dated views

Ask for a page when you want one. Keep it under `Views/`, for example `Views/2026-10-23-open-work.md` or `Views/2026-10-23-year-2026.md`. Give each page the date made, question and scope (including the year/date basis for a yearly list), record paths or request ids used, and a statement of what was actually searched. If the search was paged, follow every page for a full list; if a file could not be opened, a page was missed or cloud completeness was not established, label the view partial. For open work, follow corrections and show competing accounts rather than guessing a current state. The optional Open work add-in, when enabled, gives the steps for an exhaustive list. The line for it in the `Pace.md` index decides which file is used, which may be the owner's customised copy; see [Add-ins](add-ins.md).

The optional Project overview add-in, when enabled, makes its page as one self-contained HTML file from the template beside the file its index line names, for example `Views/2026-10-23-project-overview.html`. The same rules apply. It needs no tool, script or network, so any assistant that can create a file can make one; an assistant that cannot gives the overview in chat instead.

A view is a dated **snapshot of records**, never the place to change a job's state or store an owner decision. Make a new dated page next time; fix the underlying account through a new `Record/` correction. A saved page needs its own read-back. An old page may be out of date even when it was complete when made. Do not call a partial search a complete year or claim unseen files never existed. `Views/` is owner-controlled and outside Product, so installing a new release cannot replace it.
