# Repository references and coding sessions

A repository is a place for code. `Repos/` holds **references**, not copied code or passwords. Keep the actual checkout outside a synced Pace folder. A repository has exactly one home project, identified by its stable id in `Projects/`; its folder name can change without changing that association.

## One home per repository

For a project inside a parent (often a client), use `Repos/<parent>/<project>/<repo>/Pace repo.md`. For a standalone project use `Repos/<project>/<repo>/Pace repo.md`. Match the parent and project folder names in `Projects/`. For example:

```text
Repos/Imaginary Orchard/Website/website-code/Pace repo.md
```

Write a small portable text reference, for example:

```text
# Website code

Home project id: imaginary-website
Repository link: https://example.invalid/imaginary/website-code
Purpose: Invented website work.
```

Use a repository URL or a link the owner can open. A local checkout path may be included if it helps the owner, but it is machine-specific and is not the home or a second source. Do not put credentials, access tokens, a `.git` folder or a checkout in `Repos/`. Check the project id against `Pace project.md` and ask if an id is missing, repeated or ambiguous. If a project is renamed, move the reference folder alongside it but keep the id unchanged. These references are owner files and Product updates do not change them.

For a repository used by several projects, choose **one** home and keep its `Pace repo.md` there. Under each other project's matching `Repos/` path, put a short `Pace repo link.md` that names that project's id, the home project's id and the home reference path. This is a cross-project link, **not another repo home**:

```text
# Website code - used here

Using project id: imaginary-campaign
Home project id: imaginary-website
Home reference: Repos/Imaginary Orchard/Website/website-code/Pace repo.md
```

Update these explicit links when a folder is renamed. Do not make two copies of the checkout or silently switch the home id. One project can refer to several repositories; each repository still has one home.

## A coding session

1. Open the link, then work in the linked repository with that repository's own instructions and permissions. Pace does not tell the coding assistant how to write or review code. If the link does not open or access is uncertain, say so; do not claim the work was done.
2. Keep a brief job trail in `Record/` **for the project being helped**: an `action` for the job and its open/done/cancelled state, and a `result` for the outcome if work was done. Include the repository reference as a source and the branch name or working link in the record text. A later status change is a new record with `corrects` pointing to the earlier one, not an edit. The stable project id keeps the trail together even when the job uses a shared repo whose home is another project.
3. Say whether the branch is only local, pushed, reviewed or merged, as actually known. A branch name is not proof of a push or merge. A code change is not an owner's approval to publish or install anything.

See [Projects](projects.md) for ids and [Records](records.md) for making and reading the job records. `Pace project.md` is the project's stable identity file, not a running log; do not overwrite it to track job progress.
