# Power BI

**Purpose:** Read figures from a Power BI report or model, only through a read-only connection this host actually has.

## When to use it

When the owner asks for a figure or an answer from a named Power BI report or semantic model.

## What it needs

- Which report or model, and its workspace if the name is not unique.
- The period the owner wants.
- A read-only Power BI connection in this host, signed in with the owner's own work account. Do not assume one exists.
- For a key number the owner wants kept: the query they agreed for it.

## Steps

1. **Check the connection first.** Before anything else, check whether this host has a Power BI connection that is switched on, signed in with the owner's own account, read-only, and able to reach the named report or model. A tool called "Power BI" or "Fabric" is not proof on its own: check what it can actually read. Never use a tool that can change models or reports.
2. **If there is no such connection, say so plainly**, for example "I don't have a working Power BI connection here, so I can't read that report." Do not guess, estimate, or give a figure from memory or an old file as if it were current. Offer the two ways forward: the owner, with their IT team if needed, sets up this host's read-only Power BI connection with their own sign-in; or they hand over an export to read with the Key numbers and changes add-in. Never ask for a password or token. Stop here until a connection exists.
3. With a connection, find the intended report or model and only read from it. It uses the owner's own permissions. If access is refused, say what was refused and stop.
4. For an ordinary question, answer it and label the answer "Free question - not a reported figure", naming the model and when the query ran.
5. For a key number the owner wants kept, use the query they agreed for it, with only the period filled in. If there is no agreed query yet, draft one and show it. It is agreed only when the owner says so in their own words, and that agreement is recorded as [Records and source evidence](../../Help/records.md) describes. Run the agreed query unchanged.
6. Keep the result exactly as it came back, as source evidence. A blank result is missing, never zero. If the query is refused, or only part of a table comes back, keep nothing: say what happened, and never rewrite the query to make it run.
7. With every figure, say that the assistant passed it on, through which connection, from which model and when. The host cannot prove which query the connection actually ran.
8. If the owner wants the figure kept, record it with that source as [Records and source evidence](../../Help/records.md) describes, and call it saved only after read-back.

## What it gives back

The figure or answer with its label, model, connection and time, or one plain line saying why it could not be read.

## Limits

- These steps apply only while reading from Power BI for this request. Nothing here carries over to the rest of the chat.
- It only reads. It never changes a model, report, access setting or tenant setting.
- A kept figure is not an accepted figure. Acceptance is the owner's own confirmation: see [Exact-act confirmations](../../Help/confirmations.md).
- Results and model details read through the connection may reach the assistant's provider, so read only what the request needs.
