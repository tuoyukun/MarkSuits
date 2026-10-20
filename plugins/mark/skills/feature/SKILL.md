---
description: Start or continue a Mark feature ticket (designer, coder-plan, coder-impl, tester; human review after design and after plan). Use when the human asks to build a feature or to continue a feature ticket.
argument-hint: <ticket-id | feature description>
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

Review it with the human **before** anything is created. The review gates check the
output; this step checks the input.

1. **Understand it.** Read what the request touches: the project's `CLAUDE.md` (stack,
   module boundaries, red lines), related docs and code.
2. **Challenge it.** Is it one feature, several, or really a bug? Does it conflict with a
   module boundary or the stack? Is there a clearly simpler way?
3. **List what is unclear**, one question per line, each answerable in a sentence.
4. **Discuss and wait.** Present 2 and 3 to the human. Create nothing until they confirm.
5. **Open the ticket.** `mark claim feature "<one-line description>" --slug <2-4-word-kebab-slug>` prints
   `TICKET-ID: <id>`.
   Write `.mark/features/<id>/requirement.md` with what you agreed, including numbered
   acceptance criteria, then `mark commit <id>`.
6. **First step.** `mark next <id>`, dispatch the designer, record, report, stop.
