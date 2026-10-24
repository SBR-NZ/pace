# Changelog

Versions use `MAJOR.MINOR.PATCH`. This file describes repository changes, not an installation receipt or an owner's approval.

## 3.9.0 - Projects and Documents, kept versions, a current Pace.md and project folders

- `Pace.md` has a short, empty "Standing instructions" section after "Two boundaries", so a lasting instruction the owner gives is kept where the next chat will read it. Assistants propose the exact line, add it only on the owner's yes in their own words, and also save a decision record. A rule for one kind of task goes into that task's add-in instead (customising a shipped one first). Records help and Add-ins help hold the detail. No instructions are included; the section says `None yet.`
- `Pace.md` no longer calls the shipped folders an "empty template", which is wrong once an owner's folders fill up. `Record/` now has its own line saying it is the owner's memory, so an assistant asked what is in memory searches the Record rather than its own memory feature.
- The owner's add-ins now live in a top-level `My add-ins/` folder beside `Product/`, instead of `Pace/Add-ins/My add-ins/`, which was all the inner `Pace/` folder held. `Pace.md`, the add-ins and updates help and the folder map say so. A customised copy now sits two levels below the Pace folder, so its help links change from `../../Help/` to `../../Product/Help/`.
- An older folder that keeps its add-ins in `Pace/Add-ins/My add-ins/` keeps working as it is: its index lines still open them, and the updater lists and protects both places and never moves anything between them. Add-ins help has optional steps for moving them to `My add-ins/`, done only when the owner asks, which also fix their links and index paths.
- Tests check that an update leaves add-ins byte-identical in either place and still lists them as the owner's, that every link example in the add-ins help opens from `My add-ins/<name>/`, and that following the move steps keeps every copy working.
- The projects folder is now `Projects/` instead of `Project files/`, and each project keeps its files in `Documents/` instead of `Working files/`. The names are plainer, every path is 9 characters shorter, and `Documents/` no longer suggests drafts only. The record tool makes and lists projects under the new names, the updater protects `Projects/`, and `Pace.md`, help, add-ins, the Project overview template, the folder map and the invented example all use them. The `Pace.md` line now also says where a project's files go. There is no support for the older names: an owner folder that has them is renamed once, by hand, when this release is installed.
- A test checks that both folders have `Projects/`, that their `Pace.md` names `Documents/`, and that neither older name appears anywhere in them.
- Projects help has a new "Documents and versions" section, and the `Projects/` line in `Pace.md` gives its rule in one sentence and links to it. Each piece of work has one working file, under the same name at the top of its folder in `Documents/`. When a version is sent, presented, filed or signed off, a dated copy such as `Archive/2026-11-04 Budget 2027 v1.xlsx` is kept beside it, never changed, with a `result` record naming the copy and its fingerprint. File names carry no status words such as final or approved, no list of the current file is kept, and keeping a version only creates files, so it works where a host cannot replace or delete them. Files in a git repository keep their versions in git. The folder map says the same.
- Tests check that both `Pace.md` files carry the same sentence and link, that the help holds each rule, that its example names follow the rule, and that the help's own record-tool commands keep two versions with their fingerprints and find them newest first.
- Updates now keep Pace's own parts of `Pace.md` current. Standing instructions, Add-in index and Time zone each end with a "Your lines" mark; the owner's lines go below it and an update never changes them. The last line of `Pace.md` records each part as Pace shipped it, so an update replaces a part only while it still matches, adds a part a release introduces (but not one the owner removed), removes a part Pace no longer ships unless the owner changed it or wrote in it, and leaves sections the owner added alone. Preview lists the change, a `prepare` proposal includes it, and apply writes `Pace.md` after Product is installed and recorded, reads it back and adds a receipt line, or leaves it as it was if the write fails; applying the same release again finishes it. A `Pace.md` without the record is left as it is. Updates, add-ins and records help, the folder map, the technical notes and the README say so. The example's Product copy carries the same updater and updates help, with a new fingerprint in its invented release record.
- Tests cover each case of the plan, Windows line endings and a byte-order mark, preview and apply against invented releases, a failed write and its retry, the go-ahead covering the change, and an older unmarked `Pace.md`. The 40-line limit on `Pace.md` now counts only the lines a reader sees, not Pace's hidden marks.
- Making a project now recommends a small set of folders for its `Documents/`, two to four chosen from what the project is, never a catch-all such as `Other/` and never `Archive/`, which appears when a first version goes out. The assistant asks whether to change or add any, and whether the set should be the standard for that type of project; a confirmed standard is a standing instruction in `Pace.md` with a decision record, and is then used without asking. `Sources/` is named for what other people send, kept as received. The record tool's `project-new` takes `--folder` once for each folder, refuses an unusable name, `Archive` or a repeat before making anything, checks each folder it makes, and makes any still missing on a retry. Without `--folder` its result is as before.
- Whenever projects are listed, a folder with no `Pace project.md` is named and the owner is asked what it is: a project, a project inside its parent, a folder to move into `Documents/`, or one to leave. Nothing is made or moved without the owner's yes. Projects help says so, and the Project overview and Daily brief add-ins raise such folders.
- Tests cover the option, its refusals and retry, the help's own example command, and each rule in the help and the two add-ins.
- Releases are published at `https://github.com/SBR-NZ/pace`, which `get-pace.py` and the README now use; development stays in a separate private repository.
- A `LICENSE` file and the README say all rights are reserved until a licence for using Pace is published.

## 3.8.5 - records read back honestly and search in the owner's time zone

- A save now checks that the record will read back with exactly the fields and text meant, before writing and again on read-back. A header value with a line that is just `---` used to end the header early, so a save said "saved and read back" for a record that then read back invalid; such a value is now refused with a plain message, in records and in new project files. Record-format help states the rule.
- `listing --save` now always keeps each file's fingerprint, so a later `--compare` shows an edited record. Comparing with an older listing that has no fingerprints gives `unchecked`, never `matches`.
- `history` now says `incomplete` (not `found` or `withdrawn`) when a file in the project could not be read or has a second copy, since that file might be a later correction.
- `confirm` and `approval-reference` now accept the `--not-a-duplicate` option their possible-duplicate message suggests. When it is used, the new record keeps a `separate-from` line naming the records it would have duplicated, and `find` stops flagging that pair.
- `--pace` now works after the command as well as before it. A relative `--act-file` or `--source-file` path now starts from the Pace folder, wherever the command is run from.
- An impossible date, such as `find --since 2026-02-30` or a due day of `2026-13-45`, now gets a plain "not read" or "not saved" answer instead of a crash or a save.
- To settle two competing accounts, correct the one that stands and withdraw the other. Records help, the Daily brief and Project overview add-ins and the record tool's refusal now all say so, and `history` stops flagging competing corrections once every branch but one is withdrawn.
- An optional `Time zone:` line in `Pace.md`, such as `Time zone: Pacific/Auckland`, makes `find --since` and `--until` compare dates in the owner's time zone, so a record written by a cloud assistant on UTC is found on the owner's day. With no line each record's own written date is used, as before, and the search says which. A zone that cannot be used here is reported, never guessed. Existing records are not rewritten.
- The invented example and help examples are consistent: records are made at or after their request and their project, and file sources carry their fingerprint.
- The checks load on Python 3.8 and 3.9, and so does `get-pace.py`. The checks' invented git repositories can no longer touch the repository they are run from, even when git itself names it (as `git rebase --exec` does in a linked worktree).

## 3.8.4 - updates cope with locked files and create-only sessions

- A file held open by OneDrive or a virus scanner while an update tidied up used to make every later preview say the update was interrupted, and recovery ask for help every time. The updater now removes its journal last, so preview says the install (or roll-back) finished and `apply --root` tidies the rest. A roll-back is recorded even when its work files cannot be removed, and never twice. Work files an earlier updater left without a journal are tidied when Product matches the release recorded as installed. On Linux, a failed tidy-up no longer leaves folders that cannot be removed later.
- In an assistant session that can create files in the Pace folder but not rename or delete them, apply now stops before writing anything else and says an update needs a computer that can replace files. It leaves at most one small check file, which explains itself and is named in the result; later runs try to delete it instead of making another. Files an earlier attempt left there no longer stop preview or prepare.
- A brief lock on the update journal is now retried like other renames, so it no longer rolls back an install that was already recorded.
- With a hand-written release note that has no Product file list, preview now says edits inside Product cannot be checked, and apply needs `--replace-changed-product` unless Product already holds the new release.
- The "use exactly --repo ..." line from `preview --latest` now quotes a repository with spaces, such as a OneDrive folder, on Windows and other systems.
- Product updates help now says that a folder made by `get-pace.py` and not yet updated can say only that Product files changed, not which. Version 3.8.4 is not tagged or published here.

## 3.8.3 - customised add-ins keep their help links

- A copy of an add-in made under `Pace/Add-ins/My add-ins/` used to lose every help link, because it sits in a different place from the shipped file. The customising steps in the add-ins help now say to change `../../Help/` to `../../../../Product/Help/` in the copy, and to fix any other relative link that leaves its folder the same way.
- A test now copies each shipped add-in as the help describes, applies that change and checks that every link opens the right page. It also checks the copied Claude launcher still points to the index in `Pace.md` and that an index line naming the copy opens it.
- Version 3.8.3 is not tagged or published here.

## 3.8.2 - clearer add-in and help wording

- The Daily brief, Open work and Project overview add-ins now link to the dated-views page by its real title, "Assistants and dated views". A test now checks that every add-in link title matches the page it opens.
- Add-ins help now says what to do on a host that cannot replace `Pace.md`, such as Copilot through OneDrive: it says so and shows the owner the exact line to paste into the index, and the add-in is on only once `Pace.md` shows it.
- Add-ins help now says to remove the `None switched on yet.` placeholder when the first add-in is switched on, and to put it back when the last is switched off.
- The dated-views help no longer links straight to the shipped Open work and Project overview files; it says the index line in `Pace.md` decides which file is used, so a customised copy is respected.
- The invented example's `Pace.md` no longer calls folders that hold its invented work an empty template; a test checks that an "empty template" folder really holds nothing.
- Version 3.8.2 is not tagged or published here.

## 3.8.1 - saves leave no stray temporary files

- In a folder that lets files be created but not deleted, a save used to leave a hidden `.pace-tmp-` copy behind every time, without saying so. Now any temporary file a save cannot delete is named in that save's result as harmless, deletable by someone with delete rights.
- While such a file is there, later saves in that folder write each record or project file straight to its own name, so they leave no more. Every save is still read back before it counts as saved; elsewhere saves work as before.
- Searches describe a leftover temporary file in `Record/` as harmless, not a record, and deletable by someone with delete rights. Records help says the same.

## 3.8.0 - project overview as a page

- The Project overview add-in now also makes a dated HTML page in `Views/`, such as `Views/2026-10-23-project-overview.html`, and still gives a short summary in chat. The page is built from the records: a snapshot, never an authority. It is called saved only after its own read-back, and it never replaces an earlier page.
- Added `overview-template.html` beside the add-in. It is one self-contained HTML file with its styling inside: no script, link, image, font or network use. It reads well in light and dark, prints cleanly and fits a phone. Any assistant fills it in by hand, so Copilot, ChatGPT and Claude make the same page; there is no separate tool.
- The page keeps every view and honesty rule: every project, one project and by person; the record's own words and states; both accounts where they conflict; and "as at", "searched" and "could not read" lines. Record text is escaped so a record cannot add markup.
- In the every-project view each project now shows its owner and due date, then overdue, due soon (today or the next three weeks) and waiting on the owner, with anything recorded two ways first.
- Every add-in, Project overview included, is still off by default. The other add-ins still answer in chat.
- The invented example gains a Budget 2027 project with six records and `Views/2026-10-30-project-overview.html`, an every-project page filled in from the template.
- Add-in and dated-view help describe the page.

## 3.7.0 - check for an update with nothing typed in

- Added `Release record/Installed release.md`, a plain owner-side note (format `pace-release-note/1`) of where a PACE folder gets its releases and which release is installed: repository, tag, full commit, when it was copied or installed and, for a client fork or mirror, the upstream release. It sits outside Product, so updates never replace it.
- `get-pace.py` writes the note when it makes a PACE folder. Each install adds an entry at its end, so the last entry is the release installed now; earlier text is never changed and a rolled-back install adds nothing.
- `preview --latest` with no `--repo` reads the repository from the note and compares the newest release with the installed one. An explicit `--repo` still overrides it. A missing or unusable note is reported plainly with a request for the repository; the updater no longer assumes a default.
- A folder made before 3.7.0 keeps updating with `--repo`, and its next install writes the note.
- Product help now says that checking for an update means reading the note, then previewing the newest release; installing still needs the owner's go-ahead or exact-act confirmation.
- A repository given as a relative local folder now works, and an ssh user name such as `git@` is kept in recorded addresses.

## 3.6.0 - PACE folder and easy release access

- Renamed the copyable folder to `PACE/`, with `example/` still separate and wholly invented.
- Added one-command first copy of the newest release into a chosen place; an existing PACE folder is never overwritten.
- Added newest-release preview to the Product updater. It names the exact tag and full commit to install; installation still needs the owner's go-ahead or exact-act confirmation.
- The updater still reads the published v3.5.0 release. A folder with v3.5.0 installed updates using the newer updater from this repository, and keeps its own host pointer files.
- Rewrote the README as a short "Get PACE" and "Update PACE" front door.

## 3.5.0 - Pace 3.0 is ready to try

- Added portable project-linked repository references, optional dated views, owner guides and a fully invented example.
- Local Product installs can now use a recorded exact-act confirmation; client IT change control stays separate.
- Added an end-to-end invented-data check. Publishing a release or tag remains the owner's decision.

## 3.4.0 - recorded exact-act confirmations

- Added an append-only record-1 confirmation for the exact act, content fingerprint, source references, current owner words, time, agent and later corrections. Proposed, pending, confirmed (recorded) and superseded are distinct outcomes.
- The record tool now fingerprints the proposal, saves and reads back a confirmation, and checks its current content and correction history. Changed content, quoted source text and unconfirmed saves do not become a confirmation.
- Added an optional, separate reference for a client-supplied Teams or Power Automate decision, tied to the same act fingerprint. It does not access an account or treat OneDrive version history as consent.
- Documented how a local Product update go-ahead becomes an exact-act confirmation. The current updater still accepts its earlier go-ahead record; automated enforcement of the new record is separate work.

## 3.3.0 - repo-pull updates

- Added a Product updater with `preview` and `apply`: it pulls a release tag pinned to its full commit and stops on a moved tag, a missing commit or a mismatched file list.
- `apply` replaces only `Product/`, reads the installed files back, checks nothing outside Product changed, and puts the previous Product back after a failure or interruption.
- Installs are recorded outside Product in `Release record/`, with a short append-only receipt; "installed locally" and "arrived in OneDrive" are reported as separate claims.
- A person's own folder needs the owner's recorded go-ahead naming the exact tag and commit; a central IT copy records the IT change reference. No signatures, keys or publisher.
- Shipped add-ins update with Product; `Pace.md`, records, projects, repository references, owner add-ins and host pointers never do.
- Added update help, technical notes in `docs/updates.md` and tests on invented local repositories.

## 3.2.0 - records and projects

- Records: each is one new file in `Record/` in format record-1, with a request id that makes a retry safe, its time, project, subjects, whose words or which source, and the record it corrects. A saved record is never edited.
- Saving reads the record back and reports what really happened: saved, already saved, placed but not confirmed, conflict, possible duplicate or not saved. Nothing is overwritten or renamed.
- Searches read only what a question needs, one page at a time, and say what they covered; missing, damaged, duplicate and competing records are named, never hidden.
- Projects: a parent (such as a client) and the projects inside it, each with a stable id in a `Pace project.md` file and a `Working files/` folder.
- Added the record tool `Product/Tools/pace_record.py` and plain help for records, the record format and projects, so records can also be made and read by hand.

## 3.1.0 - add-ins

- Added the portable `ADD-IN.md` format and nine shipped add-ins, all off by default: Daily brief, Project overview, Key numbers and changes, What was reported, Reminders, Open work, Power BI, Xero and Contracts.
- `Pace.md`'s add-in index now lists switched-on add-ins one line each; none is opened at the start of a chat.
- A customised copy in `Pace/Add-ins/My add-ins/` named in the index is used in place of the shipped add-in and is never changed by a Product update.
- Added optional Claude skill launchers that only point to each add-in, and add-in help in `Product/Help/add-ins.md`.

## 3.0.0 - foundation (in progress)

- Added a copyable folder, a one-file chat entry point, folder ownership boundaries and thin host pointers.
- Added placeholder Product help, a layout guide and standard-library tests.
- Record handling, exact-act confirmations, shipped workflows and Product updates are not yet implemented.
