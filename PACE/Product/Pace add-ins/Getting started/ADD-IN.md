# Getting started

**Purpose:** Set up a new Pace folder with its owner: their name, time zone, first projects, add-ins and assistants.

## When to use it

When the owner asks to set up Pace, or to go through the set-up again, for example after starting to use another assistant. In a new Pace folder, or when the health check says a folder looks new, offer it, and start only on the owner's yes. A question about one setting does not need it.

## What it needs

- The owner, there to answer, one question at a time.
- A way to change `Pace.md` and make folders. An assistant that can only create files gives the owner the exact lines to paste instead. Read `Pace.md` fresh before each change to it, never from earlier in the chat, make only the change the owner agreed, and read it back. Through a OneDrive connection, follow [Assistants and dated views](../../Help/hosts-and-views.md), under Through a OneDrive connection.
- Nothing else: this add-in sets up no account, password or connection.

## Steps

1. Find out what is already set up. If you can run Python, run the health check, following [Health check](../../Help/health-check.md); otherwise look at `Pace.md`, `1 Projects/` and `3 My add-ins/` by hand. Skip any step below that is already done, and say which ones were skipped.
2. **The owner's name.** Ask how records should name them in who owes work and who it is for. Show the line, such as `Owner: Rangi Parata`, and on their yes add it below the mark in the part The owner's name in `Pace.md`, with one more line for each other spelling they use. Read `Pace.md` back.
3. **Time zone.** Ask where they work. Do not take it from the host's clock alone, which for a cloud assistant is usually UTC. Show the line, such as `Time zone: Pacific/Auckland`, add it below the mark in the part Time zone on their yes, and read it back. If the health check then says the zone cannot be read here, as on Windows until Python's `tzdata` package is installed, say so, and install it only on the owner's yes, with the Python the tools run in, such as `python -m pip install tzdata`.
4. **Projects.** Ask what they work on: clients, their own business, other work and personal matters. Propose a short list of projects, each with a short name and a stable id (the record tool numbers each folder), with a project that belongs to another, such as one client's report, placed inside it. Make only the ones the owner agrees, as [Projects and repository references](../../Help/projects.md) describes, including the folders it suggests for each project's `Documents/`. A few broad projects are easier to keep up than many small ones.
5. **Add-ins.** Show the shipped add-ins with their one-line purposes, as [Add-ins](../../Help/add-ins.md) lists them. Suggest Weekly review and Project overview to start with, and Daily brief for an owner who wants a morning summary. Switch on only the ones the owner picks, show the changed index lines and read `Pace.md` back: an add-in is on only once `Pace.md` shows its line.
6. **Assistants.** Ask which assistants the owner uses, such as Claude, Copilot or ChatGPT. On their yes, start `3 My add-ins/Assistant setup.md` with this assistant's own part, as [Assistants and dated views](../../Help/hosts-and-views.md) describes. For each other assistant, say how it can reach Pace, such as a Claude project instruction that names the folder, and that the owner can ask it to add its own part, which it writes only on their yes.
7. **A regular review.** Only if Weekly review is switched on, suggest going through open work with it once a week. Where the host can set a reminder or scheduled task that can open this Pace folder when it goes off, offer to set one, and call it set only once the host confirms it. Its instruction names the Pace folder and the review, and copies no names, figures or other private details into the host's app. On a schedule the review only makes its list; the owner goes through it in a chat.
8. **Backups.** Say plainly that Pace keeps the owner's records in this folder only. OneDrive keeps earlier versions and a recycle bin. A separate backup is the owner's choice, and nothing is set up unless they ask.
9. Check again, with the health check or by hand, and give the owner a short list of what is now set up and anything left, with what to do about each.

## What it gives back

A short list in chat of what was set up, what was skipped because it was already there, and anything left to do. Anything decided along the way, such as a standard set of folders for client projects, is kept as [Records and source evidence](../../Help/records.md) describes, and called saved only after read-back.

## Limits

- These steps apply only while setting up Pace. Nothing here carries over to the rest of the chat.
- Every change to `Pace.md`, every new folder and every add-in switched on needs the owner's yes in their own words. Nothing is changed because it is usual or recommended.
- It sets up no account, connection, password or payment, and never asks for a password or key.
- It sends nothing to anyone.
