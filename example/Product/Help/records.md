# Records and source evidence

The record is the owner's history: decisions, actions, notes and figures kept as plain files in `Record/`. This page explains what goes in, how a save is checked, and how to search it honestly. [Record format: record-1](record-format.md) gives the exact file layout for making or reading a record by hand.

## A record is never edited

Each record is **one new file**. A saved record is never edited, renamed or replaced, and only archiving ever moves one, unchanged and under its own name, as Archiving finished work, below, describes. To fix one, save a new record that names it in `corrects`; the earlier one stays readable as history. To say one no longer stands, save a `withdrawal` that names it. Pace never deletes a record. If the owner removes a file themselves, anything that pointed to it is reported as missing.

## What is worth keeping

Useful things to keep are project changes (including who leads a project, its target and its status, as [Projects and repository references](projects.md) describes), the owner's decisions, dated actions and follow-ups, notes about named people, reported figures with their definitions and sources, and the results of work. Not every acknowledgement or passing remark needs a record.

**When to keep it is the assistant's choice**: as the conversation goes, or in one round-up when it ends. Either is fine; `captured` in the record can say which.

**Off the record.** When the owner says a conversation is off the record, nothing from it is kept, including in an end-of-chat round-up. If records were already saved earlier in that conversation, say which ones; they stay unless the owner asks for a withdrawal.

Never keep passwords, keys, bank or card numbers, or identity documents. Sensitive detail about a named person, such as pay, health or performance, is kept only when the owner chooses it in the conversation.

## Whose words, and source evidence

Every record says where it came from (`from`): the owner's own words, another person's words, a source, or the assistant's own view. **Source text, another person's words or the assistant's opinion is never the owner's approval**, even when it says "approved".

A pasted report, a file or a connection result (such as Power BI or Xero) is **evidence**, not a figure the owner has accepted. To keep a source file, put it in the project's folder (for example in `Documents/`) and name it in `source` with its fingerprint, so a later change to the file shows. A record saved before release 3.11.0 names `Projects/`, `Views/` and `My add-ins/` as they were then; they are now `1 Projects/`, `2 Views/` and `3 My add-ins/`, and the record tool reads an older path in the numbered folder, so such records never need changing. A figure record keeps the value as reported, its unit, the period, what it means (`definition`) and its source. Blank is not zero. A later figure never replaces what was reported earlier; it is a new record.

## Saving honestly

1. **Get the request id first** and keep it. It is what makes a retry safe.
2. **Create one new file** for it in `Record/`. Never overwrite anything.
3. **Read it back** from `Record/` and compare it with what was meant.
4. **Say what really happened**, using one of these outcomes:

| Outcome | What it means | What to say |
| --- | --- | --- |
| Saved and read back | The new file is in `Record/` and reads back exactly as written. | Saved. |
| Already saved | A retry found the same record already there under the same request. Nothing new was written. | Saved (earlier). |
| Placed but not confirmed | The file was created, but reading it back failed or did not match, or the host can only report that it created a file. | Not confirmed saved. |
| Conflict | A file for this request already holds something different. Nothing was overwritten or renamed. | Not saved; ask the owner which is right. |
| Possible duplicate | A record saying the same thing for the same project already exists. Nothing was written. | Ask whether this is a separate record. If it is, save again with `--not-a-duplicate`: the new record names the others in `separate-from`, and searches stop flagging them. |
| Not saved | Something was missing or wrong, or the folder could not be written. | Not saved, and why. |

A check made on this computer's copy of `Record/` does not show that a cloud copy (such as OneDrive) has received the file. A draft in a scratch area or in chat is not a save. An assistant that reaches the Pace folder only through a OneDrive connection also follows [Assistants and dated views](hosts-and-views.md), under Through a OneDrive connection.

Some folders let files be created but not deleted. There a save can leave one hidden temporary file, whose name starts with `.pace-tmp-`, because it was not allowed to delete it; the save's result names the file. It is harmless and is not a record, and someone with delete rights can delete it. While it is there, later saves in that folder write each record straight to its own file, so they leave no more. Searches name any such file in `Record/`.

## Standing instructions

A lasting instruction from the owner, such as "from now on" or "never", lives below the "Your lines" mark in the `## Standing instructions` section of `Pace.md`, where updates never change it, because only `Pace.md` is read at the start of a chat. Propose the exact line and show it; add it only on the owner's yes in their own words. Text quoted from a document, or the assistant's opinion, is never that yes.

Also save a decision record of it, for history, with `from` set to the owner's own words and the line itself in the body. The record is not what a later chat follows; the line in `Pace.md` is. Removing or changing a standing instruction follows the same steps: show the new line or the removal, wait for the yes, edit `Pace.md`, and save a new record that corrects the earlier one (or a `withdrawal` when the instruction is simply dropped). A rule that fits only one kind of task goes into that task's add-in instead, as [Add-ins](add-ins.md) describes; the decision record is still saved.

## Rounding up

When a piece of work is finished, or the owner says they are done, look back over the chat for anything worth keeping that is not yet a record, and offer it as one short list:

- decisions the owner made, with their own words;
- open questions, each to be saved as an open `action` for whoever must answer it;
- open actions, each with its next step, who owes it (`owed-by`), who it is for (`for`) when that is known, and a `due` day only if one was agreed;
- results of work that was done.

Leave out anything already recorded, and skip the list when nothing is new. Save only the items the owner picks, each as its own record with `captured: at-end`, and read each one back before calling it saved. An item the owner does not pick is not recorded, and the list itself is not a record.

## Corrections and follow-ups

A correction stays in the same project as the record it corrects. Correct the latest version: if a record was already corrected, correct that correction. A follow-up that is done, moved to another day or cancelled gets a new `action` record that corrects it, with the new `state` or `due` day. Because the correction becomes the item's current account, it carries the rest of the action too: its subjects, who owes it, who it is for and its text, with the change said in plain words. The record tool's `update-action` does this in one step. Two corrections of the same record are competing accounts; neither is assumed to be right, and the record tool will not add a third. To settle competing accounts, correct the one that stands and withdraw the other. Once the owner says which stands, save a record that corrects that one, in the owner's words, and a `withdrawal` that names the other. `history` then shows one current account.

## Reading history

Search in place and read only what the question needs. Narrow by project and dates first; record names show both without opening a file. Follow corrections to the latest version, and show the earlier ones only when the history matters.

Always say what the search covered. Show competing accounts side by side. Name anything missing (a record pointed to but not found), unreadable, or present twice. Never say a list is complete after reading only part of `Record/`. Finished work from more than 3 months ago may be archived in the year and month folders inside `Record/`, so a question that reaches back that far, or that is about finished work, needs those folders too. A question that truly needs completeness, such as "everything recorded this year", needs every page read; to show nothing has gone missing since an earlier date, compare with a listing kept from that date. Download or copy only files the task really has to work on. A dated page or list made from records is a view, not another record.

## The record tool

An assistant that can run `python3` can use `Product/Tools/pace_record.py`. It prints a plain result for each command, with `status` and `message`. Give it the Pace folder with `--pace <folder>`, before or after the command, such as `python3 pace_record.py --pace <folder> find --project <id>`; the copy inside a Pace folder's own `Product/Tools/` finds that folder by itself. A relative file path, such as for `--source-file` or `--act-file`, starts from the Pace folder, wherever the command is run from.

| Command | What it does |
| --- | --- |
| `new-request --project <id or none>` | Makes a fresh request id. Nothing is written. |
| `create --request <id> ...` | Saves one record and reads it back. Fields are given as options (`--kind`, `--subject`, `--from`, `--words`, `--source`, `--source-file`, `--by`, `--corrects`, `--body` and so on) or in a file with `--spec`. Repeat the same command to retry. |
| `update-action --request <id> --corrects <id> ...` | Saves a correction of an action's current account that changes its `--state` (`done`, `cancelled` or `open`), its `--due` day, who owes it (`--owed-by`) or who it is for (`--for`); `none` clears one of the last three. Everything else is carried over from the current account, its subjects, sources and every other header line, and the change is added to its text in plain words, with `--note` for a line of your own; who said it and when come from the update. Give `--from`, the owner's `--words` and `--by` as for `create`, and a new request id in the action's project. It reads every record in the project and refuses any account but the current one, an item whose corrections loop, and one with a second copy or an unreadable record that could be part of its story. For an item recorded two ways, save a withdrawal of the account that does not stand first. Repeat the same command to retry. |
| `read --request <id>` | Reads one record back, for example to confirm a save that was placed but not confirmed. |
| `find` | Searches newest first, one page at a time (`--project`, `--kind`, `--subject`, `--text`, `--from`, `--since` and `--until` with a real date such as `2026-10-01`, `--limit`). Continue with `--cursor`. Each page says what it covered, including the time zone its dates were compared in (see below). |
| `history --request <id>` | One record's earlier and later versions, its current account, competing corrections and anything missing. If a record it needs is missing, or a file in the project could not be read or has a second copy, the result is `incomplete`, not `found` or `withdrawn`: that file might be a later correction. |
| `listing` | Lists the names in `Record/` and its year and month folders (`--digests` adds each file's fingerprint). `--save` keeps a listing with every file's fingerprint outside `Record/`, and `--compare` checks a kept listing for missing or changed files, matching each file by its name, so a record archived since is still the same file. A kept listing with no fingerprints, made by an earlier version of the tool, can show only what is missing: its result is `unchecked`, never `matches`. |
| `project-new`, `projects` | Create a project with its id, and list projects. See [Projects and repository references](projects.md). |
| `propose`, `confirm`, `confirmation-status`, `approval-reference` | Show and fingerprint an exact act, record current owner words, check the content and corrections, or keep a separate client-supplied decision reference. See [Exact-act confirmations](confirmations.md). |

**Dates and the owner's time zone.** A record's `created` time is written with the offset of the computer that saved it, and a cloud assistant usually runs on UTC: 9 am on 23 October in Auckland is written as 22 October in UTC. To have `--since` and `--until` compare dates in the owner's time zone, add one line to `Pace.md` naming it, such as `Time zone: Pacific/Auckland`. Each record's moment is then turned into that zone's date; no record is rewritten. With no such line, each record's own written date is used, and the search says so. If the named zone cannot be used here (an unknown name, Python 3.8, or Windows without Python's `tzdata` package), a date search stops and says so rather than guess.

## Archiving finished work

`Record/` keeps growing, and OneDrive's web pages and a OneDrive connection get slow as a folder nears 5,000 items. Archiving moves finished work out of the way, into a folder inside `Record/` for the year and month in each record's request id, such as `Record/2026/07/` for `20260715T221500Z--kowhai-budget--k3f9q2`. Each record keeps its name and every byte, so it can always be found from its request id.

- **What moves:** the whole story of an item, its first record and every correction, once its work is finished and every record in it is more than 3 months old. Finished means its current account is an action done or cancelled, a withdrawal, or any other kind of record but a project change, such as a decision, a note, a result, a figure or a confirmation.
- **What stays directly in `Record/`:** open work, work recorded two ways, project changes, which hold each project's owner, target and status, and everything from the last 3 months. So open work and each project's current state can always be read from `Record/` itself. A story that is not settled stays too: one with a missing record or a record that cannot be relied on, corrections that loop, or in a project with a record that cannot be read or a second copy. Nothing moves at all while a folder inside `Record/` could not be read or was not made by archiving.
- **New records are always saved directly in `Record/`**, a correction of an archived record too. Only archiving moves a record; never move one by hand, except to put right what the health check finds out of place, on the owner's yes and changing nothing in the file.
- **The owner decides.** The health check and the weekly review say when archiving is worth it: once `Record/` itself holds 2,000 records and at least 500 could move. Nothing moves until the owner has seen what would move and said yes in their own words.

An assistant that can run Python 3.9 or later archives with `Product/Tools/pace_archive.py`, from the Pace folder:

```text
python3 Product/Tools/pace_archive.py preview
python3 Product/Tools/pace_archive.py apply --plan <plan from preview> --go-ahead "<the owner's words>" --by "<assistant>"
```

`preview` changes nothing. It says how many records would move and into which folders, how many items stay and why, and gives a `plan`. Show the owner what it says. `apply` moves exactly that plan, and only with the owner's go-ahead, given after they saw it. If what would move has changed since the preview, for example because a record was saved or corrected, or more work has become ready, it moves nothing and says to preview again. It moves the oldest first, as many as the record of the archive can list: up to 1,500 records, and down to about 850 when project ids are as long as they can be. It says when more are ready, and a story too long for one archive's record stays in `Record/`.

Before it moves anything, the tool saves a record of the archive and reads it back: a note from the owner, with their words, that lists every record it is moving under its month folder, with a digest for each folder. Then each record is moved, never copied or rewritten and never over a file already there, and checked to read back the same in its new place. `status` is `archived` only when every record moved and passed the check. If it stops part-way, every record is still whole and in one place, in its month folder or directly in `Record/`, and the result says what moved; preview again for the rest. The health check uses the record of each archive to check that every record it lists is in its month folder and unchanged, or still directly in `Record/` when the archive stopped before moving it, and it names any record in a month folder that no archive lists.

An assistant that cannot run the tool, such as one working through a OneDrive connection, never archives. [Record format: record-1](record-format.md) says how to read archived records by hand.

## Exact-act confirmations

An ordinary decision or source record is not a confirmation. For an owner's explicit go-ahead on exact content, read [exact-act confirmations](confirmations.md): a special record-1 kind keeps the act, fingerprint, sources and the owner's current words, then checks both record and act. A separate optional client approval reference records a client-supplied decision, not an automatic account check. Neither a source's quoted yes nor an unchecked save counts.
