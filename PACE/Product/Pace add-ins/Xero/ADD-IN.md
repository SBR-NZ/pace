# Xero

**Purpose:** Read figures from Xero reports, only through the owner's own Xero connection when this host has one.

## When to use it

When the owner asks for a figure from Xero, such as revenue, cash at bank or debtor days for a period.

## What it needs

- The Xero organisation, the report and the period.
- A Xero connection in this host that the owner set up and signed in to themselves. Pace never sees or keeps the sign-in. Do not assume one exists.
- For a key number the owner wants kept: the query they agreed for it.

## Steps

1. **Check the connection first.** Before anything else, check whether this host has a Xero connection, signed in by the owner, that can reach the named organisation. If it reaches several organisations, use the one the owner named; never pick one yourself.
2. **If there is no such connection, say so plainly**, for example "I don't have a Xero connection here, so I can't read Xero." Do not guess, estimate, or give a figure from memory or an old file as if it were current. Offer the two ways forward: the owner sets up this host's Xero connection and signs in themselves; or they hand over a Xero report export to read with the Key numbers and changes add-in. Never ask for a password or token. Stop here until a connection exists.
3. Ask Xero for the report in Xero's own standard layout rather than the organisation's edited layout, for the exact period, with the options agreed, such as cash or accrual basis. The reports most often used are Profit and Loss (for a period), Balance Sheet (as at one day), Executive Summary (one month) and Bank Summary (for a period).
4. Before using any figure, check the reply: the right organisation, the right report, the right period as Xero's own title shows it, and section totals that add up. If any check fails, use nothing from it and say what did not match.
5. Read the figure from the exact section and row agreed, matched exactly, spaces included. Never choose a similar heading. No such row, or a blank value, is missing, never zero. The same label twice is unclear. A percentage stays a percentage.
6. For an ordinary question, answer it and label the answer "Free question - not a reported figure", naming the organisation and when it ran.
7. For a key number the owner wants kept, use the query they agreed for it: the report, its options, and the section, row and column to read. If there is none yet, draft one and show it. It is agreed only when the owner says so in their own words, and that agreement is recorded as [Records and source evidence](../../Help/records.md) describes. Keep Xero's reply exactly as it came back, as source evidence.
8. Some figures are not a single Xero report row: EBITDA needs a mapping of accounts, budget variance and forecasts are not held as one figure, and headcount needs payroll permission. Say so rather than quietly building one.
9. With every figure, say that the assistant passed it on through its Xero connection, and when. If the owner wants it kept, record it with that source as [Records and source evidence](../../Help/records.md) describes, and call it saved only after read-back.

## What it gives back

The figure or answer with its label, organisation, report, period and time, or one plain line saying why it could not be read.

## Limits

- These steps apply only while reading from Xero for this request. Nothing here carries over to the rest of the chat.
- It only reads. It never sends, approves, files, pays or changes anything in Xero.
- The assistant passes Xero's reply on, so Pace cannot prove it was copied unchanged. The section-total check catches most copying mistakes, but not all.
- A kept figure is not an accepted figure. Acceptance is the owner's own confirmation: see [Exact-act confirmations](../../Help/confirmations.md).
