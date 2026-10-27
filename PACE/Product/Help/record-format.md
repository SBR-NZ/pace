# Record format: record-1

This page describes exactly what a record file looks like, so any assistant can make or read one by hand, even one that cannot run the record tool. [Records and source evidence](records.md) explains when to keep a record and what each outcome means. An assistant that reaches the Pace folder only through a OneDrive connection also follows [Assistants and dated views](hosts-and-views.md), under Through a OneDrive connection.

## Where a record goes and its name

Each record is saved as one new text file directly in `Record/`, never in a subfolder. Its name is its request id followed by `.md`:

```text
Record/20261022T221500Z--kowhai-budget--k3f9q2.md
```

Once its work is finished and more than 3 months old, archiving may move it, unchanged and under the same name, into the folder for the year and month in its request id, such as `Record/2026/10/20261022T221500Z--kowhai-budget--k3f9q2.md`. Nothing else moves a record. [Records and source evidence](records.md) describes archiving.

The request id has three parts joined by two hyphens:

1. **The time the request was started, in UTC**, written `YYYYMMDDTHHMMSSZ`. New Zealand time is UTC plus 13 hours in summer and plus 12 in winter, so 11:15 am on 23 October 2026 in Auckland is `20261022T221500Z`.
2. **The project id**, or `none` when the record belongs to no project. See [Projects and repository references](projects.md).
3. **Six random lowercase letters or digits**, so two records started in the same second never share a name.

Choose the request id **before** saving and keep it. If a save has to be tried again, use the same request id: that is how a repeat is recognised instead of becoming a second copy.

## What is inside

A record starts with a header between two lines of three hyphens, then the record's text in plain words:

```text
---
format: record-1
request: 20261022T221500Z--kowhai-budget--k3f9q2
created: 2026-10-23T11:15:00+13:00
project: kowhai-budget
kind: decision
subject: October month close
from: owner
words: Let's close October on the 5th, not the 3rd.
by: Claude Code
captured: as-we-go
---

The October month close for the budget project moves from 3 November to 5 November.
```

Each header line is `name: value`. A value that runs over several lines continues on lines that start with two spaces; blank lines inside a value are dropped. A continuation line can never be just `---`, because that line ends the header and the rest would be misread; write it another way or put it in the text below the header. The record tool refuses such a value, and calls a record saved only when it reads back with the same fields and text. Names are lowercase. `subject` and `source` may appear more than once; every other name appears once.

| Field | Needed | What it holds |
| --- | --- | --- |
| `format` | Always | `record-1`. |
| `request` | Always | The request id, exactly the file name without `.md`. |
| `created` | Always | When the record was made, with its UTC offset, such as `2026-10-23T11:15:00+13:00`. |
| `project` | Always | The project id, or `none`. It must match the project part of the request id. |
| `kind` | Always | One of the kinds below. |
| `subject` | At least one | A short label for what the record is about: a topic, a person, a figure's name. Reuse the same label for the same subject so it can be found again. |
| `from` | Always | Whose words or which source: `owner`, `person`, `source` or `agent` (see below). |
| `who` | When `from` is `person` | The person's name, and their role if it helps. |
| `words` | When `from` is `owner` or `person` | Their words, as said. |
| `source` | When `from` is `source`, or for a figure not given in someone's words | Where it came from: a file's place in the Pace folder with its fingerprint, a link, or a connection and the question asked of it. |
| `by` | Always | The assistant or person who wrote the record, such as `Claude Code` or `Microsoft 365 Copilot`. |
| `captured` | Optional | `as-we-go` (kept during the conversation) or `at-end` (kept when it wrapped up). |
| `corrects` | For a correction or withdrawal | The request id of the record it corrects. |
| `separate-from` | Optional | The request ids, separated by spaces, of earlier records that say the same thing but that the owner says are separate. The record tool writes it when a save is repeated with `--not-a-duplicate`, and searches then stop flagging those records as possible duplicates of this one. |
| `due`, `owed-by`, `for`, `state` | Optional, for an action | The due day, a real calendar date such as `2026-11-05`, who owes it, who it is for, and `open`, `done` or `cancelled`. |
| `owner`, `target`, `status` | Optional, for a change | For the record's project: who leads it now, its target date (a real calendar date such as `2026-11-27`) and a short status in words. `none` clears one. For each, the latest current `change` that sets it stands, as [Projects and repository references](projects.md) describes. |
| `value`, `unit`, `period`, `definition` | For a figure | The figure as reported, its unit, the period it covers and what it means. A figure needs `value`, `period` and `definition`. |
| `act`, `act-file`, `act-sha256` | For a confirmation | The exact act, its content file and SHA-256 of that file's exact bytes. |
| `confirmation-request` | For a client reference | The request id of the linked owner confirmation. |
| `approval-system`, `approval-approver`, `approval-decision`, `approval-time`, `approval-reference` | For a client reference | The client-supplied Teams or Power Automate decision details, separate from the owner's words. |

The text below the header must not be empty. Keep records short; long material belongs in a project's `Documents/` folder, referred to from the record.

### Kinds

| Kind | Use it for |
| --- | --- |
| `note` | Something worth keeping that fits no other kind. |
| `decision` | A decision the owner made. |
| `action` | A dated action or follow-up. |
| `person-note` | A note about a named person. |
| `figure` | A reported figure with its definition and source. |
| `result` | The result of a piece of work. |
| `change` | A change to a project. |
| `withdrawal` | An earlier record no longer stands. Needs `corrects`. |
| `confirmation` | An exact act with current owner words and a checked content fingerprint. See [confirmations](confirmations.md). |
| `approval-reference` | Separate client-supplied Microsoft 365 decision reference, not a Pace owner confirmation. See [confirmations](confirmations.md). |

### Whose words: `from`

| Value | Means |
| --- | --- |
| `owner` | The owner's own words in the conversation. Needs `words`. |
| `person` | Someone else's words, such as a client or colleague. Needs `who` and `words`. |
| `source` | A document, file, email, report or connection result. Needs `source`. |
| `agent` | The assistant's own observation, summary or opinion. |

A record made from a source, another person's words or the assistant's opinion is never the owner's approval, whatever it says.

### Room for later formats

A record may carry extra header lines with other lowercase names. A record-1 reader keeps them and shows them, but gives them no meaning; the one exception is `owner`, `target` and `status` on a `change` record, described above. The record tool saves those three only on a change for a real project, but never calls an earlier record wrong for carrying them. [Exact-act confirmations](confirmations.md) extend record-1 with `kind: confirmation`, the act, its exact file and SHA-256 fingerprint, source references and the owner's current words. `kind: approval-reference` holds a separate client-supplied decision linked to that same fingerprint. These kinds require additional read-back and content checks; an ordinary record is not a confirmation. The undeclared kind `approval` still has no meaning here. A file whose `format` is a later version (`record-2` and so on) is reported as not readable by record-1, not guessed at.

## Making a record by hand

1. Pick the request id as described above and write it down before anything else.
2. Write the file content: the header, a blank line, then the text.
3. Create **a new file** in `Record/` named `<request id>.md`. Never replace or edit an existing file. If a file with that name is already there, do not overwrite it and do not rename yours: open the existing one and compare. If it says the same, the record was already saved. If it differs, it is a conflict; tell the owner.
4. Open the file again from `Record/` and check it says exactly what you wrote. Only then call it saved. If the host can only report that it created a file and cannot open it again, say it was **placed but not confirmed**.

## Reading records by hand

1. List the names in `Record/` without opening the files. The names alone show when each record was started and its project, so pick only the ones the question needs, newest first. Open work, project changes and everything from the last 3 months are always directly in `Record/`. Finished work from before then may be archived in the year and month folders inside it, such as `Record/2026/07/`: list those too when the question reaches back that far, and say which folders were listed.
2. Open just those files. A record whose `corrects` names an earlier record replaces that earlier one, which stays readable as history; one that is not directly in `Record/` may be archived, in the folder for the year and month in its request id. A `withdrawal` means the earlier record no longer stands. Two records correcting the same earlier record are competing accounts: show both. To settle them, correct the one that stands and withdraw the other.
3. A name that looks like a record's name with something added, such as `... (1).md` or `...-LAPTOP.md`, is a second copy, often made by file syncing. Neither copy is assumed right.
4. Say what you looked at. Do not say a list is complete when only part of `Record/` was read.
