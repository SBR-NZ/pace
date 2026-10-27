# Key numbers and changes

**Purpose:** Read agreed key numbers from handed-over files and compare two versions, like with like.

## When to use it

When the owner hands over a new pack, forecast or export and asks what changed, or asks for agreed key numbers to be read from a file. For a figure from a live connection, use the Power BI or Xero add-in. For what was told to an audience, use the What was reported add-in.

## What it needs

- The files to read or compare, named by the owner. File dates and file names never choose them.
- For each key number, its definition: what it means, where it sits in the file (sheet and cell, or row and column), its period, whether it is an actual, a budget or a forecast, and its currency, unit, scale and sign. Use a definition already in the record. If there is none, agree one with the owner and record it as [Records and source evidence](../../Help/records.md) describes.

## Steps

1. Confirm the files and the key numbers with the owner.
2. Keep each handed-over file as source evidence before reading it, as [Records and source evidence](../../Help/records.md) describes, so every figure can point to the exact file it came from.
3. Read each number only from its agreed place. Do not run macros, refresh connections or recalculate. A formula cell shows its value as last saved; say so when it matters. A blank is missing, never zero. If a sheet or heading has moved, or the place holds more than one number, say the number is missing or unclear. Never look in nearby cells for a likely match.
4. A PDF or picture can be read, but a figure typed from it is a transcription. Show it to the owner to confirm before using it.
5. Compare two figures only when they match on meaning, scope, period, actual, budget or forecast, currency, unit, scale and sign. Otherwise say "not comparable" and name what differs. Do not convert between thousands and units, or between currencies, unless the owner asks and agrees how.
6. Group the changes so their meaning is clear:
   - a forecast replaced by a newer forecast: normal movement;
   - an actual that was already reported has changed: check with the What was reported add-in if it is switched on, or search the record, including the year and month folders inside `Record/` for anything reported more than 3 months ago;
   - a budget the owner accepted has changed;
   - any other change.
7. Show a table of each number with its period, the before and after values, the change, and where each value came from (file and place).
8. If the owner wants the figures kept, record each one with its definition and source as [Records and source evidence](../../Help/records.md) describes. Call them saved only after read-back.

## What it gives back

The comparison table and its groups, plus a list of every number that was missing, unclear or not comparable, each with its reason.

## Limits

- These steps apply only while reading and comparing these files. Nothing here carries over to the rest of the chat.
- Reading or saving a figure is not accepting it. A label in the file such as "Final" or "Approved" is not the owner's acceptance either. Acceptance is the owner's own confirmation of that exact figure: see [Exact-act confirmations](../../Help/confirmations.md).
- It never changes the handed-over files, and it sends nothing to anyone.
