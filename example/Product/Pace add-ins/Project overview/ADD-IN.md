# Project overview

**Purpose:** Show where one project, every project or one person's work stands.

## When to use it

When the owner asks for an overview, such as "where are we with the budget model?", "give me an overview of my projects" or "what does Sam owe me?". A quick question about one task does not need it.

## What it needs

- Which view: every project, one project, or by person.
- Today's date and time zone, from the host's clock or the owner.
- Read access to `Record/`, `Projects/` and `Repos/`.
- To keep the page, a way to create a new file in `Views/`. Replacing a file is never needed.

## Steps

1. Agree the view. If a project or person name matches more than one, ask which.
2. Find each project by its stable identifier, as [Projects and repository references](../../Help/projects.md) describes, so a renamed project is still found. If the list of projects names folders that have no `Pace project.md`, name them too and ask the owner what each one is, as that page describes. Search the record for its open work, due dates, decisions, notes, and finished or cancelled work. Follow [Records and source evidence](../../Help/records.md) for how to search and how to say what the search covered.
3. **Every project:** give one short summary per project: its name, its purpose ("Purpose not recorded" when there is none), who owns it and its due date ("Not recorded" when the record holds none). Then what is overdue, what is due soon (today or in the next three weeks) and what is waiting on the owner, each with its date and how late or how soon it is. Each item appears once: anything recorded two ways first, under its own heading; then an overdue item under overdue; anything else the owner owes under waiting on the owner; and other work under due soon when it falls in the next three weeks. List unsettled projects first, then overdue, then due today, then by the earliest upcoming date. Finished and cancelled projects go last. A project inside another one sits under its parent.
4. **One project:** give its purpose and state, then in order: decisions waiting on the owner, open tasks (late first, then by date), related work, notes (newest first), projects inside it, documents and repository references, work done in the last three weeks, and cancelled work.
5. **By person:** for each person, say what they will provide and what they are waiting for, each with its date or how late it is. Then list work with no person named.
6. Keep the record's own words and states. Do not add a priority, percent complete, on-track judgement or start date the record does not hold, and never call related work blocking.
7. Where the record holds two accounts of one item, show both together and ask which stands. When the owner says which stands, correct the one that stands and withdraw the other, as [Records and source evidence](../../Help/records.md) describes.
8. **Make the page.** Fill in a copy of the [page template](overview-template.html) kept beside this file, following the note at its top. Keep only the chosen view, and fill in the "as at", "asked", "searched" and "could not read" lines. If anything could not be read, the page says it is partial. Escape every piece of text that comes from a record, a file or a person before it goes in, so a record can never add markup: `&` becomes `&amp;` first, then `<` becomes `&lt;`, `>` becomes `&gt;`, `"` becomes `&quot;` and `'` becomes `&#39;`. Add nothing the template does not have: no scripts, links, images or fonts, and nothing fetched from the internet.
9. **Save it as a new dated page** in `Views/`, named for the date and the view: for example `Views/2026-10-23-project-overview.html` for every project, `Views/2026-10-23-project-overview-kowhai-budget.html` for one project (its id), or `Views/2026-10-23-project-overview-by-person.html`. Never replace an existing page; if the name is taken, add `-2`, `-3` and so on. Open the page again from `Views/` and check it is the page just written, with the same "as at" line. Only then call it saved. If the host can only say it created a file, say the page is placed but not confirmed. If the host cannot create files in `Views/`, say so and give the whole overview in chat instead.

## What it gives back

**A dated page in `Views/` and a short summary in chat.** The owner can ask for the chat summary only, and then no page is made.

- **The page** is one self-contained HTML file that opens the same way in any browser, on a phone, in light or dark, and when printed, with no network. It shows the "as at" date and time, what was asked, what was searched and anything that could not be read. It is built from the records: a dated snapshot, never an authority, and never edited afterwards. To bring it up to date, make a new page; to put something right, record a correction. It follows the dated-view rules in [Assistants and dated views](../../Help/hosts-and-views.md).
- **The chat summary** gives the "as at" date, the page's name and whether it was saved (read back), placed but not confirmed, or not saved. Then a few lines on what is recorded two ways, overdue, due soon and waiting on the owner, and one line saying what was searched and anything that could not be read.

If the owner wants a list to give someone else, include only the items the owner picks, with no notes or other projects, and let the owner read it and send it themselves.

## Limits

- These steps apply only while preparing this overview. Nothing here carries over to the rest of the chat.
- The overview and its page change nothing in the record, and nothing on the page is the owner's approval. Closing a project does not close its tasks.
- A reply from someone else about their work is not the owner's approval. Anything the owner then decides is recorded as [Records and source evidence](../../Help/records.md) describes, and called saved only after read-back.
- It sends nothing to anyone. The page uses nothing from the internet, and needs no tool to make: any assistant can fill in the template by hand.
