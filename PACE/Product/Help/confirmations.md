# Exact-act confirmations

A **confirmed (recorded)** act is the owner's own current words about one exact proposal, saved as a new record in `Record/`, read back, and checked against the same content. It is not a signature, identity check, permission to file or send anything, or proof that the underlying figures are correct. [Records](records.md) explains the append-only save and retry rules; [record-1 format](record-format.md) explains the file layout. Do not infer the owner's yes from a pasted email, a quoted document or the assistant's opinion.

## What to show and ask

1. Put the **exact proposed content** in a file that can be read again (for example, a close statement, a figure with period, unit, definition and source, a forecast version, or the Product version and local installation change). Name the act plainly. Keep the file where the owner can review it. Show its source or before-and-after; do not rely on a bare title. A file's fingerprint is the SHA-256 of its **exact bytes**, not a fingerprint of the filename or a summary. Changing even one byte requires a new proposal and new owner words.
2. Show the proposal to the owner. Ask for their own current, explicit words about this act. A simple yes is meaningful only in direct reply to this exact proposal. A document saying "yes", an absent reply or words guessed by an assistant do not count. The tool cannot tell who really spoke or whether the assistant copied the reply faithfully; the person operating it must check this.
3. Make one new confirmation record under a fresh request id. Give it the fingerprint of what was shown, the owner's words, its source references and the agent who recorded it. Open the saved record again and check the act file still has the same bytes. If a host can only report creation, say **pending**, not confirmed. Checking a local copy does not prove cloud arrival.
4. For a correction or withdrawal, leave the first record untouched. Use a new record with `corrects` pointing to the earlier request. Changed act content needs a new proposal and new owner words, not reuse of the earlier yes. Check the correction history before relying on an old confirmation; competing or unreadable copies need attention.

Use this for a month close, accepting named figures, accepting a particular forecast, and the owner's go-ahead before a **local** Product update. Acceptance is separate from actually closing the month, filing a return, sending a forecast, or installing Product. For an update, use `prepare` after preview to put the exact proposed installation in an act file: the pinned full commit, tag, Product file-list fingerprint, affected local Product copy and before-and-after. Show this to the owner and record the exact-act confirmation **before** applying. A central client rollout follows client IT's own change control.

For a local update, run `preview`, then `prepare` with the same repository, pinned tag and full commit. `prepare` writes the complete proposed act to `Release record/Proposals/` and reads it back. Show that file and the before-and-after preview. Use `propose` and `confirm` on the proposal file with the owner's current words, then pass its request id to the updater's `apply --confirmation-request`. Apply checks that the record is still current, the file still matches its fingerprint and the exact proposal matches the selected release and this folder's current Product. Its receipt names `Record/<request>.md`. A changed release, changed local Product or superseded confirmation stops the install; prepare and ask again. The older simple `--go-ahead` and `--go-ahead-record` routes remain available but are **not** exact-act confirmations. A simple JSON go-ahead alone does not become a confirmation. To confirm an older go-ahead, show the exact act again and ask for fresh current words; never backdate it. An installation receipt proves neither identity nor cloud arrival.

## The record, by hand

This invented example confirms an exact close statement in a file. The fingerprints below are illustrative only; replace them with the real computed SHA-256 of the file's exact bytes before use. A manually written record also needs a read-back and content comparison before calling the act confirmed.

```text
---
format: record-1
request: 20261022T221500Z--kowhai-budget--conf01
created: 2026-10-23T11:15:00+13:00
project: kowhai-budget
kind: confirmation
subject: October close
from: owner
words: Yes, close October using the statement you just showed me.
source: 1 Projects/Kowhai Books/Budget 2027/Documents/close.txt sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
by: Test agent
act: Accept the invented October close statement
act-file: 1 Projects/Kowhai Books/Budget 2027/Documents/close.txt
act-sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
---

Owner's current words above confirm the exact act named here, not any later changed content.
```

`act` names the act. `act-file` locates the exact content; `act-sha256` is its SHA-256 fingerprint. `source` may be repeated for each source or before-and-after reference; a source that is a file gives its place and fingerprint, as `--source-file` writes it. `words` must be the owner's current words; `from: owner` alone cannot make source text into owner words. `created` is the record time, `by` names its writer, and a later correction points back with `corrects`. Use the ordinary record-1 request id, filename, project, append-only and read-back rules. Do not use the old `approval` kind.

## Status words

| State | Honest wording |
| --- | --- |
| Proposed | "Proposed, not confirmed. Here is the exact act and its source; please review." No current owner words or no record yet. |
| Pending | "Pending. The record was not read back, a source is missing, content changed, or its history cannot be checked." A create receipt is not enough. |
| Confirmed | "Confirmed (recorded) for this exact content on this local copy." Only after the record and current act read back and match, with no known correction. |
| Superseded or corrected | "That confirmation was superseded or corrected; read the later record. A changed act needs a fresh confirmation." A competing correction is not a current yes. |

## Using the record tool

`python3 Product/Tools/pace_record.py` uses only the standard library. Pass `--pace <folder>` when working outside an installed Pace folder, before or after the command, such as `python3 pace_record.py --pace <folder> confirmation-status --request <request>`. Every command returns a plain `status` and `message` plus details. A relative `--act-file` path starts from the Pace folder, wherever the command is run from. For example, with invented temporary files:

```text
python3 Product/Tools/pace_record.py propose --act "Accept the October close statement" --act-file "1 Projects/Kowhai Books/Budget 2027/Documents/close.txt"
python3 Product/Tools/pace_record.py new-request --project kowhai-budget
python3 Product/Tools/pace_record.py confirm --request <request> --project kowhai-budget --subject "October close" --act "Accept the October close statement" --act-file "1 Projects/Kowhai Books/Budget 2027/Documents/close.txt" --shown-sha256 <fingerprint-from-propose> --source "Close statement and source notes shown to owner" --owner-words "Yes, close October using the statement you just showed me." --owner-current --by "Test agent"
python3 Product/Tools/pace_record.py confirmation-status --request <request>
```

`--owner-current` asserts that the words came from the owner **now**, replying to that shown act. Do not use it for a quotation, assumed intent or silence. Reuse the same request on retry; different content under the same request is a conflict and is never overwritten. If a save reports a possible duplicate and the owner says it is a separate confirmation, repeat the same command with `--not-a-duplicate`; `approval-reference` takes the same option. Ordinary `create` cannot make a confirmation. `read` and `history` can show the record and its correction chain, but `confirmation-status` additionally checks the content file. A local check cannot independently verify chat identity, copied words, the checker, a cloud save or that an unseen file was never removed.

## Optional client Microsoft 365 decision reference

A client may supply a decision result from **its own** Teams or Power Automate approval. This is a separate append-only `approval-reference` record, not an automatic integration or a Pace signing service. Pace has no account access here. The client supplies the approver, decision (`accepted` or `declined`), decision time with UTC offset, approval reference and evidence source. The record points to the existing confirmation request and copies the **same act, file and fingerprint**. If the client system is unavailable, no decision is inferred; keep the client decision pending. An unrelated Teams "yes" is not a reference to this exact act.

```text
---
format: record-1
request: 20261022T223000Z--kowhai-budget--ref001
created: 2026-10-23T11:30:00+13:00
project: kowhai-budget
kind: approval-reference
subject: October close
from: agent
source: Invented client approval result AC-042
by: Test agent
act: Accept the invented October close statement
act-file: 1 Projects/Kowhai Books/Budget 2027/Documents/close.txt
act-sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
confirmation-request: 20261022T221500Z--kowhai-budget--conf01
approval-system: teams
approval-approver: Invented Reviewer
approval-decision: accepted
approval-time: 2026-10-23T11:29:00+13:00
approval-reference: AC-042
---

Reference supplied from the client's approval system; no live account or integration was checked by Pace.
```

With an actual client-supplied result, use `approval-reference --request <new-request> --project <id> --subject <topic> --confirmation-request <confirmed-request> --available --system teams --approver <client-supplied-name> --decision accepted --decision-time <time> --reference <client-reference> --source <evidence> --by <agent>`. Then use `confirmation-status --request <confirmed-request> --reference-request <new-request>` to check that the linked fingerprint and currently readable bytes still match. A declined result stays declined; this tool says only "client decision reference recorded", not "identity approved". The client's system may provide account and audit evidence if its authentication and retention permit it; this local tool has **not** checked the client account or fetched its approval. A record of the decision cannot prove the underlying figures correct or cover changed content.

OneDrive or SharePoint version history is **separate evidence**: it may show file versions, account and edit time under the client's retention settings, but a version is not an explicit yes to the act. Link such history as a source if useful; never turn a version number or edit into an owner confirmation or a client approval reference.
