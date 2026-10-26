---
description: Start or continue a Mark feature ticket (designer, coder-plan, coder-impl, tester; human review of the requirement, the design and the plan; projects without a UI skip the design). Use when the human asks to build a feature or to continue a feature ticket.
argument-hint: <ticket-id | [--discuss] feature description>
allowed-tools: Bash(mark:*)
---

!`mark rules`

## Board

!`mark status --active`

## /mark:feature

Argument: `$ARGUMENTS`

### A. The argument is an existing ticket id (`0012`, `0012-login`)

Run `mark next <id>` and do **one step** of the loop: dispatch, wait for the agent, record
its outcome, report, stop. If `next` says wait, stop or done, report that and stop.

### B. Anything else is a new feature request

Agree on the requirement with the human **before** anything is built. A one-line request is
never enough to start: what you guess wrong here, every later role builds on.

1. **Understand it.** Read what the request touches: the project's `CLAUDE.md` (stack,
   module boundaries, red lines), related docs and code.
2. **Size it.** The ticket is **large** if `$ARGUMENTS` starts with `--discuss` (drop the flag
   from the description), or if any of these holds: it touches more than one module, adds a
   dependency, storage or external service, changes the data model, needs more than about five
   acceptance criteria, or the request is too thin to tell. Otherwise it is **small**. Tell the
   human which and why in one line; they may overrule you.
3. **Challenge it.** Is it one feature, several, or really a bug? Does it conflict with a
   module boundary or the stack? Is there a clearly simpler way?
4. **Discuss and wait.** Create nothing until the human confirms.
   - **Small:** present 3 and the unclear points, one question per line, each answerable in a
     sentence. One round is usually enough.
   - **Large:** one topic per round, in this order, and wait for the human after each:
     1. **Scope:** who it is for, the problem it solves, what the first version includes, what
        it explicitly does not do.
     2. **Technical choices:** only the ones that change cost or scope (a new library, how data
        is stored, an external service). For each, 2-3 options with trade-offs and your
        recommendation, asked as a choice, not an essay question.
     3. **Architecture:** modules touched, the rough data model, the boundaries between modules,
        the main risks. Direction only; coder-plan works out the details.

     End each round with a short summary of what was decided and get it confirmed before the
     next. Skip a topic only when there is nothing to decide, and say so.
5. **Open the ticket.** `mark claim feature "<one-line description>" --slug <2-4-word-kebab-slug>` prints
   `TICKET-ID: <id>`; the ticket starts at `drafting`.
6. **Write the requirement.** `.mark/features/<id>/requirement.md` (`mark format requirement.md`)
   with what you agreed: numbered acceptance criteria, and every decision from step 4 as a
   `DEC-N` (choice, why, options rejected). Open questions must be `none`: anything still open
   goes back to the human first. Then `mark set <id> review-requirement` (it refuses a
   requirement without criteria or with open questions).
7. **Stop for review.** Give the human the path of `requirement.md` and list the `DEC-N` in one
   line each. They may edit the file, then `/mark:approve <id>` (the design or the plan comes
   next) or `/mark:reject <id> <comments>` (back to `drafting`: address each comment, then
   step 6 again).
