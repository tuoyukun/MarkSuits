---
description: Open or continue a Mark bug ticket and run its chain (fix-plan, designer when the fix is in the UI directory, coder-impl, tester) without review gates. Use when the human reports a bug to fix or asks to continue a bug ticket.
argument-hint: <bug-id | bug description>
allowed-tools: Bash(mark:*)
---

!`mark rules`

## Board

!`mark status --active`

## /mark:fix

Argument: `$ARGUMENTS`

The bug chain has no human review gates: once it starts, keep looping (dispatch, wait,
record, merge) until `passed`, a `blocked-*` status, or another stop. Report progress after
each step; do not wait for a command between steps.

### A. The argument is an existing bug id (`b0007`, `b0007-crash`)

Run `mark next <id>` and keep looping as above.

### B. Anything else is a new bug report

1. **Understand it.** Look at the code involved, so the fix-plan agent does not start from
   the description alone.
2. **Challenge it.** Is it really a bug, or a change request or new feature? Is the fix
   contained, or architectural? If it should be a feature, say so and stop; suggest
   `/mark:feature`.
3. **Open the ticket first.** `mark claim bug "<one-line description>" --slug <2-4-word-kebab-slug>`
   prints `TICKET-ID: <id>`. Open it before the discussion: the human's `/mark:fix` is the
   approval to open (valid for 2 hours), and `bug.md` is the only place the discussion can be
   written down, so a session end or `/clear` loses nothing. If `mark claim` says the opening is
   not approved, ask the human to run `/mark:approve <id>` and continue here once it succeeds.
4. **List what is missing** (reproduction steps, expected behaviour, impact), one line each, and
   **discuss and wait** for the human's confirmation. Before the first question, read `bug.md`
   if it exists (a resumed ticket) and do not re-ask what it records. Write
   `.mark/bugs/<id>/bug.md` as items are settled: the human's report verbatim, plus what you
   agreed on reproduction, expectation and impact.
5. **Run the chain** from `mark next <id>` after `mark commit <id>`.
