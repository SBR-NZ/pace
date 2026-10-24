# Project overview

**Purpose:** Show where one project, every project or one person's work stands.

## When to use it

When the owner asks for an overview, such as "where are we with the budget model?", "give me an overview of my projects" or "what does Sam owe me?". A quick question about one task does not need it.

## What it needs

- Which view: every project (the usual one), one project with the projects inside it, or by person.
- The owner's name as the records write it in `owed-by` and `for`, such as `Daniel Kelly`. The words `owner` and `the owner` always count as the owner.
- Today's date and time zone, from the host's clock and the `Time zone:` line in `Pace.md`.
- Read access to `Record/`, `Projects/` and `Repos/`.
- To keep the page, a way to create a new file in `Views/`. Replacing a file is never needed.

## Steps

1. Agree the view. If a project or person name matches more than one, ask which.
2. **If you can run Python**, make the page with the overview tool, following "The overview tool" in [Assistants and dated views](../../Help/hosts-and-views.md). It reads every record and project, follows each item to its current account, fills in the [page template](overview-template.html) kept beside this file, saves the page as a new file in `Views/` and reads it back. The tool takes only the style, wordmark and footer from the template it is given and always makes the page this add-in describes. So for a customised copy that changes only the page's look, give the tool the copy's template; for one that changes what the page shows, fill in the copy's template by hand instead. Report the result as the tool states it: `saved` means saved and read back, and anything else is not saved. If it lists folders that have no `Pace project.md`, ask the owner what each one is, as [Projects and repository references](../../Help/projects.md) describes. Then give the chat summary below.
3. **Otherwise, fill in the template by hand**, following the note at its top. Find each project by its stable identifier, as [Projects and repository references](../../Help/projects.md) describes, so a renamed project is still found. If the list of projects names folders that have no `Pace project.md`, name them too and ask the owner what each one is, as that page describes. Search the record as [Records and source evidence](../../Help/records.md) describes. Fill in the "as at", "asked", "searched" and "could not read" lines; if anything could not be read, the page says it is partial.
   - **Open work** is an `action` whose current account, its latest correction that is not withdrawn, is not `done` or `cancelled`. One with no `state` is open work too, shown with its state not recorded.
   - Name in the "could not read" line, and call the page partial, any record that a correction points to but that is not in `Record/`, and any corrections that point to each other in a loop. The corrections of a missing record are still one item; accounts in a loop are shown as recorded two ways.
   - An item with two current accounts is **recorded two ways**: show both together and ask which stands. It is not counted anywhere else. When the owner says which stands, correct the one that stands and withdraw the other.
   - **Overdue** is due before today. Overdue, due today and due in the next 7 days together make **Needs attention**, across the whole view.
   - **Waiting on you** is open work the owner owes, **waiting on others** is open work someone else owes, and **no person named** is open work with no `owed-by`.
   - A project's **owner**, **target** and **status** come from its `change` records: for each, the change first recorded latest that sets it stands, so correcting a change does not make it the newest, and `none` clears it. When a change is recorded two ways and its accounts give different values, show "Recorded two ways". A target that is not a real date is not used; name it in the "could not read" line. Show the status in its own words with its record's date; never turn it into a rating.
   - Every list runs in the same order: overdue first, the longest late first, then due today, then by due date, then work with no due date, in the order it was first recorded.
   - **Every project:** the six counts, anything recorded two ways, Needs attention, and a table of each project with open work, a target or a status. The table groups projects under the project at the top of their folders, at any depth, and runs the most pressing first (the most overdue, then the earliest due date, then the most open work), judged by the most pressing work anywhere in the group; each project comes before the projects inside it, and projects side by side run most pressing first in the same way. It gives each project's name after the projects above it, its status under its name, its owner and target (each column only when some project in the table has one), its open and overdue counts, its earliest due date, overdue or not, and the date of its newest record. Then one line naming the projects with no open work, target or status in them or in any project inside them, leaving out any with work recorded two ways, and each project's open work in its three groups.
   - **One project:** its purpose, owner, target and status, the projects above it, every project inside it at any depth and its newest record; the same counts, recorded two ways and Needs attention for it and the projects inside it; the same table of projects when a project inside it has open work, a target or a status; its open work; then what was decided, changed, done and cancelled in the last three weeks, its notes from the last three weeks, and its documents and repository references.
   - **By person:** anything recorded two ways, then a card for each person, the owner first: what they owe, naming who it is for only when the record does, and what they are waiting for. Then open work with no person named.

   Needs attention repeats the most urgent items at the top; each project's own list still holds all of its open work.
4. Keep the record's own words and states. Do not add a priority, percent complete, on-track or health judgement, or a start date the record does not hold, and never call related work blocking. The counts and how late or how soon something is come from the dates; nothing else is worked out.
5. Escape every piece of text that comes from a record, a file or a person before it goes in, so a record can never add markup: `&` becomes `&amp;` first, then `<` becomes `&lt;`, `>` becomes `&gt;`, `"` becomes `&quot;` and `'` becomes `&#39;`. Add nothing the template does not have: no scripts, links, images or fonts, and nothing fetched from the internet. Keep the style block and the SBR wordmark exactly as they are.
6. **Save it as a new dated page** in `Views/`, named for the date and the view: for example `Views/2026-10-23-project-overview.html` for every project, `Views/2026-10-23-project-overview-kowhai-budget.html` for one project (its id), or `Views/2026-10-23-project-overview-by-person.html`. Never replace an existing page; if the name is taken, add `-2`, `-3` and so on. Open the page again from `Views/` and check it is the page just written, with the same "as at" line. Only then call it saved. If the host can only say it created a file, say the page is placed but not confirmed. If the host cannot create files in `Views/`, say so and give the whole overview in chat instead.

## What it gives back

**A dated page in `Views/` and a short summary in chat.** The owner can ask for the chat summary only, and then no page is saved.

- **The page** is one self-contained HTML file in SBR's brand that opens the same way in any browser, on a phone, in light or dark, and when printed, with no network. It shows the "as at" date and time, what was asked, what was searched and anything that could not be read. It is built from the records: a dated snapshot, never an authority, and never edited afterwards. To bring it up to date, make a new page; to put something right, record a correction. It follows the dated-view rules in [Assistants and dated views](../../Help/hosts-and-views.md).
- **The chat summary** gives the "as at" date, the page's name and whether it was saved (read back), placed but not confirmed, or not saved. Then a few lines on what is recorded two ways, overdue, due today or in the next 7 days, and waiting on the owner, and one line saying what was searched and anything that could not be read.

If the owner wants a list to give someone else, include only the items the owner picks, with no notes or other projects, and let the owner read it and send it themselves.

## Limits

- These steps apply only while preparing this overview. Nothing here carries over to the rest of the chat.
- The overview and its page change nothing in the record, and nothing on the page is the owner's approval. Closing a project does not close its tasks.
- A reply from someone else about their work is not the owner's approval. Anything the owner then decides is recorded as [Records and source evidence](../../Help/records.md) describes, and called saved only after read-back.
- It sends nothing to anyone, and the page uses nothing from the internet. The tool is a convenience: any assistant that can create a file can fill in the template by hand.
