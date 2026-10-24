# Contracts

**Purpose:** Set down in plain English how one workbook or recurring job must work, then read back what is built against it.

## When to use it

When the owner asks to set down a contract for one Excel workbook or one recurring job, to read something back against its contract, or to answer a question from a contract. Here a contract is a short working page, not a legal contract.

## What it needs

- The workbook or job, and the project it belongs to.
- For a job, whatever the owner points to, such as last month's checklist or pack.
- The owner's answers to the open questions.

## Steps

### Setting up a contract

1. Read the workbook as evidence: its sheet names, headings, typed inputs, formulas as written and values as last saved. Never run its macros, refresh its connections, recalculate it or save over it. If it cannot be read here without a risk of running or refreshing it, say so and ask the owner to walk through it instead.
2. Tell the owner what already looks settled under each heading below, then ask the open questions a few at a time. Their answers decide what the contract says; what is built is only evidence of what exists.
3. Draft the contract under these headings. For a workbook:
   - **Source**: which file or export starts each period, where it is kept and how the workbook picks it up.
   - **Inputs**: what people type in, such as rates and mappings, and where each one sits.
   - **Steps**: each calculation in words, in order, including rounding and what happens to a row that cannot be matched.
   - **What must tie**: each check that must agree, and where the workbook shows it.
   - **Outputs**: what the workbook hands on and the shape of each output.
   - **Boundary**: what it does not cover, and which other contract takes over.
   - **Version**: one line naming the workbook version it was written from and the date of the owner's answers.

   For a recurring job, use: what goes in, the steps, what comes out, what must tie, who accepts it, what is outside, and the same version line.
4. Where the owner has not settled something, write "Not settled yet" with the open question, never a guess. Say where an amount, rate or balance sits, never the value itself. Where a key number already has a definition in the record, point to it by name instead of restating it.
5. One contract covers one workbook or one job. When one feeds another, each gets its own contract and says where the next one takes over.
6. Show the draft to the owner. When they are happy with it, save it as an ordinary file in the project's `Documents/` folder, as [Projects and repository references](../../Help/projects.md) describes, for example in a `Contracts` folder there. Ask before making a new folder. Call it saved only after read-back.
7. The contract stays a draft until the owner accepts it in their own words. Their acceptance is recorded as [Exact-act confirmations](../../Help/confirmations.md) describes. Until then, say it is a draft whenever answering from it.

### Reading back against a contract

1. When the owner asks, compare what is built with the contract, heading by heading.
2. List each gap: where it is (sheet and cell, step or file), what the contract says, what is built, and a suggested fix. Where nothing differs under a heading, say so once.
3. Under What must tie, say whether the workbook shows each check where the contract says. Whether it ties today is for the owner to read, since the workbook is not recalculated.
4. Each gap the owner wants fixed can become a dated follow-up, recorded as [Records and source evidence](../../Help/records.md) describes. Listing a gap does not fix it.

## What it gives back

A draft contract to review, the saved contract file once the owner is happy with it, or a read-back in chat. A read-back the owner wants kept is saved beside the contract as an ordinary file.

## Limits

- These steps apply only while working on this contract. Nothing here carries over to the rest of the chat.
- It never writes a legal contract and never changes a workbook. Adding a contract sheet to a workbook is the owner's own edit.
- It never calls a check passed or failed, approves figures, closes a month or marks anything reported.
- It sends nothing to anyone.
