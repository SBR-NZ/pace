# Product updates: technical notes

For client IT and whoever maintains a Pace copy. The owner's explanation is `PACE/Product/Help/updates.md`; the updater is `PACE/Product/Tools/pace_update.py` (Python standard library and the `git` command only).

## Publishing a release

Tag the release commit (an annotated, protected tag is best) and publish the tag name and its full commit id together, for example in the release notes. Never move a published tag: every pinned update of it will then stop. From 3.6.0, the Product of a release is `PACE/Product/` at that commit; the published v3.5.0 tag uses `starter/Product/`. The updater reads that older path only for v3.5.0. Nothing else in the commit is installed. First copies use `get-pace.py --to <place>`; it copies the whole released PACE folder into `<place>/PACE` (and can read the older v3.5.0 folder), then starts its release note.

## Commands

| Option | Meaning |
| --- | --- |
| `preview` / `prepare` / `apply` | Show what a release would change / save and read back a local exact-act proposal / install it. Preview writes nothing to the Pace folder. |
| `--root` | The Pace folder, or central copy, that holds `Product/`. |
| `--repo`, `--tag`, `--commit` | Where to pull from, the release tag, and the full commit (40 or 64 hex characters) the tag must point to. `--commit` is optional for preview only, which then reports the tag's current commit as not pinned. |
| `preview --latest` | Find the highest numbered stable release tag, pin its full commit, compare it with the installed release and show what would change. The repository is `--repo` if given, otherwise the last entry of the release note. With neither, it stops and asks for the repository; it never falls back to a default. For install, use the tag and commit shown, not `--latest`; a later release must not silently change the approved target. |
| `--confirmation-request` / `--go-ahead` / `--go-ahead-record` | For a person's own folder: the request id of a current record-1 confirmation for a prepared exact-act proposal; or the owner's own words naming the tag and full commit; or a matching earlier simple go-ahead file. Give exactly one. |
| `--central`, `--it-change` | A central IT copy installed under the client's change control. `--central` is refused when the folder has a `Pace.md`. `--it-change` may also be recorded on a local install. |
| `--upstream-repo`, `--upstream-tag`, `--upstream-commit` | For a fork or mirror: the upstream release this commit is said to carry. |
| `--file-list-digest` | Stop unless the release's Product file list has this digest, for example the one IT reviewed. |
| `--replace-changed-product` | Replace Product even though files inside it changed since the recorded install, or cannot be checked against it. |
| `--json` | Print the full result as JSON. |

`prepare` requires a pinned commit and creates a new file under the person's `Release record/Proposals/` with this folder's Product before/after, release source and file-list digest. After showing it to the owner, use `pace_record.py propose` and `confirm` on that file; `apply --confirmation-request <request>` reads back the current confirmation and rejects a changed proposal, old Product, destination or release. Central copies still use IT change control without a personal confirmation. `apply --root <folder>` on its own only recovers an interrupted update. Exit code 0 means previewed, installed, already installed, or (for a recovery-only run) recovered; 1 means stopped, rolled back, refused or needs help; 2 means wrong options.

## Central copies, forks and mirrors

A central copy is a folder IT keeps with `Product/` and `Release record/` and no person's files. A client fork or mirror is pulled like the upstream repository, using the client's own tag and commit. When `--upstream-*` options are given, both releases are fetched and checked, and their Product file lists must be identical; the record then maps the client commit to the upstream tag and commit. Any difference stops the update, so a client commit is never recorded as an upstream release it does not match. Without those options only the client commit is recorded. The release note then names the fork or mirror as the release repository, plus the upstream repository, tag and commit when they were checked, so a later `preview --latest` looks in the fork or mirror and finds only the numbered tags (such as `v3.7.0`) published there.

## Release note

`Release record/Installed release.md` (format `pace-release-note/1`) says where a PACE folder gets its releases and which release is installed. It is plain Markdown: a short header with a `Format:` line, then one entry per first copy or install, each a `## <time> UTC - <event>` heading followed by `- Label: value` lines:

| Label | Meaning |
| --- | --- |
| `Release repository` | Where releases come from, with any user name or password removed (an ssh user name such as `git@` is kept) and a local folder as its full path. |
| `Installed release` / `Full commit` | The installed tag and its full commit. |
| `Product file list` | The `sha256:` digest of the installed Product file list. Without it, edits inside Product cannot be checked, so `apply` needs `--replace-changed-product` unless Product already matches the release being installed. |
| `Upstream repository` / `Upstream release` / `Upstream full commit` | Optional: the upstream release a fork or mirror was checked against. |
| `Install record` | The matching file in `Installs/`; absent for a first copy. |

`get-pace.py` creates the note. After an install is recorded, `apply` adds an entry at the end and reads it back; a rolled-back install adds none, and recovery after a hard stop adds a missing entry once. Earlier text is never changed. The last entry is the release installed now: a reader uses it unless the latest `Installs/` record is newer. If the last entry is incomplete, or the file is not a release note, `preview --latest` without `--repo` stops and says so; an install leaves a file that is not a release note as it is and warns. Unknown labels are ignored, so later versions can add fields.

## What apply does, in order

1. Recovers any interrupted update in this folder, then stops.
2. Checks the chosen local go-ahead route or the central copy's IT change reference. For a confirmation, it reads the record-1 confirmation and compares its saved exact proposal against this update before swapping Product.
3. Fetches only `refs/tags/<tag>` into a throwaway store, checks the tag's commit equals the pinned commit, reads every `PACE/Product` file (or `starter/Product` for v3.5.0 only) and checks it against the commit's object ids. It refuses links, submodules, and names Windows or OneDrive cannot hold side by side.
4. Compares the installed Product with the release, and with the last recorded install.
5. Checks that the folder lets files be renamed and deleted (see Limits), then records the owner's go-ahead, if given as words.
6. Stages the release in `Release record/Update in progress/staged/Product` and reads it back. Rechecks a confirmation and the pre-install Product before swapping.
7. Writes a journal, renames the old Product to `previous/`, and renames the staged Product into place.
8. Reads the installed Product back against the release's file list, and checks nothing outside `Product/` and `Release record/` changed.
9. Writes the `Installs/` record, appends the receipt line, and reads both back.
10. Adds the new release to the end of the release note and reads it back. A problem here is reported as a warning; the install record stays correct.
11. Removes the work area, its journal last. If something there cannot be removed, such as a file a sync client holds open, the install still stands and the result warns. The journal stays, so a later `apply --root` sees a finished install and only tidies.

A failure in steps 6 to 9 restores the previous Product, checks it against its earlier file list, records a roll-back and then removes the work area the same way. After a hard stop, the next apply uses the journal to do the same; a roll-back already recorded for that attempt is not recorded again. A roll-back that cannot be confirmed keeps the work area and reports that it needs help. A work area with no journal, as an earlier updater could leave after a failed tidy-up, is removed only when the installed Product matches the release recorded as installed; otherwise the updater reports that it needs help.

## Product file list

Format `pace-product-file-list/1`: a JSON array of `{"path", "size", "sha256"}` for every file under Product, with paths relative to Product using `/`, sorted by path, serialised with sorted keys, no spaces and UTF-8. The digest is `sha256:` followed by the SHA-256 of those bytes. File modes are ignored, because Windows and WSL mounts report them differently.

## The check outside Product

Everything outside `Product/` and `Release record/` is compared before and after by name, size and modification time, and `Pace.md` and the host pointers also by their bytes. Other owner files are not opened, so OneDrive does not download cloud-only files during an update. A file or folder the updater is not allowed to read, such as the Claude desktop app's own `Claude/` folder seen from its Linux sandbox, is listed as unreadable and not walked into. It is compared only as unreadable, so it is not checked, and the install record (`not_checked`) and the result name it. During the install the updater never writes outside `Product/` and `Release record/`; a change found there was made by something else, and is left as it is while Product rolls back. Only after the install is recorded does it write `Pace.md`, once, replacing just the Pace parts that still match the fingerprints in its last line (see Product updates help), then reading it back.

## Records

- `Release record/Installs/<time>-<tag>-<commit>.json` (`pace-install-record/1`): attempt id, start and finish time, result (`installed` or `rolled back`), kind (`local install` or `central copy`), repository (any user name or password removed), tag, commit, Product file list with every entry and its digest, upstream mapping, prior tag, commit and digest, changes, owner go-ahead file, IT change reference, the outside-Product check, and the OneDrive status, always "Not checked". A later record that corrects an earlier one names it in `corrects`.
- `Release record/Go-aheads/<time>-<tag>-<commit>.json` (`pace-update-go-ahead/1`): time, repository, tag, commit and the owner's words (simple go-ahead route only).
- `Release record/Proposals/<time>-<tag>.json` (`pace-local-install-act/1`): exact local proposal read back before a separate confirmation in `Record/`; the install and rollback records name its confirmation request when used.
- `Release record/Install receipts.md`: one appended line per attempt.
- `Release record/Installed release.md` (`pace-release-note/1`): the release note described above.
- `Release record/Update in progress/journal.json` (`pace-update-journal/1`): a work file that exists only during an update or after an interruption.

## Limits

- Run one update at a time per folder. A second apply treats the first's work area as an interrupted update.
- Some assistant sessions linked to a folder can create files there but not rename or delete them. Before writing anything else, `apply` (and `apply --root` before it moves or removes anything) creates, renames and deletes one small check file, `Release record/.pace-update-check-<id>`. Where that is refused, it stops and says an update needs a computer that can replace files. A check file it could not delete stays, harmless and named in the result; later runs try to delete it instead of making another. A work area with no journal and nothing moved, as an earlier updater could leave in such a session, does not stop `preview` or `prepare`.
- On Windows, run from outside `Product/` and close windows open on it. Renames, including each journal update, are retried briefly when a sync client holds a file.
- git uses the computer's own credentials and never prompts for a password. Network access, private repositories and cloud replacement in particular hosts are not tested here.
- There are no signatures, keys or publisher. The pinned commit and file list guard against a wrong, moved or partial version; they do not prove who published it.

Tests in `tests/test_updates.py` use only invented local git repositories.
