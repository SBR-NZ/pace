# Records and source evidence

The record is the owner's history: decisions, actions, notes and figures kept as plain files in `Record/`. This page explains what goes in, how a save is checked, and how to search it honestly. [Record format: record-1](record-format.md) gives the exact file layout for making or reading a record by hand.

## A record is never edited

Each record is **one new file**. A saved record is never edited, renamed or replaced. To fix one, save a new record that names it in `corrects`; the earlier one stays readable as history. To say one no longer stands, save a `withdrawal` that names it. Pace never deletes a record. If the owner removes a file themselves, anything that pointed to it is reported as missing.

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

A check made on this computer's copy of `Record/` does not show that a cloud copy (such as OneDrive) has received the file. A draft in a scratch area or in chat is not a save.

Some folders let files be created but not deleted. There a save can leave one hidden temporary file, whose name starts with `.pace-tmp-`, because it was not allowed to delete it; the save's result names the file. It is harmless and is not a record, and someone with delete rights can delete it. While it is there, later saves in that folder write each record straight to its own file, so they leave no more. Searches name any such file in `Record/`.

## Corrections and follow-ups

A correction stays in the same project as the record it corrects. Correct the latest version: if a record was already corrected, correct that correction. A follow-up that is done, moved to another day or cancelled gets a new `action` record that corrects it, with the new `state` or `due` day. Two corrections of the same record are competing accounts; neither is assumed to be right, and the record tool will not add a third. To settle competing accounts, correct the one that stands and withdraw the other. Once the owner says which stands, save a record that corrects that one, in the owner's words, and a `withdrawal` that names the other. `history` then shows one current account.

## Reading history

Search in place and read only what the question needs. Narrow by project and dates first; record names show both without opening a file. Follow corrections to the latest version, and show the earlier ones only when the history matters.

Always say what the search covered. Show competing accounts side by side. Name anything missing (a record pointed to but not found), unreadable, or present twice. Never say a list is complete after reading only part of `Record/`. A question that truly needs completeness, such as "everything recorded this year", needs every page read; to show nothing has gone missing since an earlier date, compare with a listing kept from that date. Download or copy only files the task really has to work on. A dated page or list made from records is a view, not another record.

## The record tool

An assistant that can run `python3` can use `Product/Tools/pace_record.py`. It prints a plain result for each command, with `status` and `message`. Give it the Pace folder with `--pace <folder>`, before or after the command, such as `python3 pace_record.py --pace <folder> find --project <id>`; the copy inside a Pace folder's own `Product/Tools/` finds that folder by itself. A relative file path, such as for `--source-file` or `--act-file`, starts from the Pace folder, wherever the command is run from.

| Command | What it does |
| --- | --- |
| `new-request --project <id or none>` | Makes a fresh request id. Nothing is written. |
| `create --request <id> ...` | Saves one record and reads it back. Fields are given as options (`--kind`, `--subject`, `--from`, `--words`, `--source`, `--source-file`, `--by`, `--corrects`, `--body` and so on) or in a file with `--spec`. Repeat the same command to retry. |
| `read --request <id>` | Reads one record back, for example to confirm a save that was placed but not confirmed. |
| `find` | Searches newest first, one page at a time (`--project`, `--kind`, `--subject`, `--text`, `--from`, `--since` and `--until` with a real date such as `2026-10-01`, `--limit`). Continue with `--cursor`. Each page says what it covered, including the time zone its dates were compared in (see below). |
| `history --request <id>` | One record's earlier and later versions, its current account, competing corrections and anything missing. If a record it needs is missing, or a file in the project could not be read or has a second copy, the result is `incomplete`, not `found` or `withdrawn`: that file might be a later correction. |
| `listing` | Lists the names in `Record/` (`--digests` adds each file's fingerprint). `--save` keeps a listing with every file's fingerprint outside `Record/`, and `--compare` checks a kept listing for missing or changed files. A kept listing with no fingerprints, made by an earlier version of the tool, can show only what is missing: its result is `unchecked`, never `matches`. |
| `project-new`, `projects` | Create a project with its id, and list projects. See [Projects and repository references](projects.md). |
| `propose`, `confirm`, `confirmation-status`, `approval-reference` | Show and fingerprint an exact act, record current owner words, check the content and corrections, or keep a separate client-supplied decision reference. See [Exact-act confirmations](confirmations.md). |

**Dates and the owner's time zone.** A record's `created` time is written with the offset of the computer that saved it, and a cloud assistant usually runs on UTC: 9 am on 23 October in Auckland is written as 22 October in UTC. To have `--since` and `--until` compare dates in the owner's time zone, add one line to `Pace.md` naming it, such as `Time zone: Pacific/Auckland`. Each record's moment is then turned into that zone's date; no record is rewritten. With no such line, each record's own written date is used, and the search says so. If the named zone cannot be used here (an unknown name, Python 3.8, or Windows without Python's `tzdata` package), a date search stops and says so rather than guess.

## Exact-act confirmations

An ordinary decision or source record is not a confirmation. For an owner's explicit go-ahead on exact content, read [exact-act confirmations](confirmations.md): a special record-1 kind keeps the act, fingerprint, sources and the owner's current words, then checks both record and act. A separate optional client approval reference records a client-supplied decision, not an automatic account check. Neither a source's quoted yes nor an unchecked save counts.
