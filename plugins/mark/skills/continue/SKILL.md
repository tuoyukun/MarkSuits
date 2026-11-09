---
description: Carry a Mark ticket on to its next human gate or stop, after the human decided (the web board starts this in a headless session; a human may also type it). Never approves or rejects anything.
argument-hint: <ticket-id>
disable-model-invocation: true
allowed-tools: Bash(mark:*)
---

!`mark rules`

## /mark:continue

Argument: `$ARGUMENTS`

1. If `$ARGUMENTS` has no ticket id, say so and stop.
2. Loop as after `/mark:approve` (`mark next`, dispatch, record, merge) until the next human
   gate, a stop, or `passed`, reporting each step in one line. The human's decision, if any, is
   already recorded; this command carries no approval of its own. If `mark next` asks for a
   human decision, report it and stop.
3. Run every agent and `mark merge` in the **foreground**: wait for each to finish before the
   next step. A headless session ends when you stop, and anything still running in the
   background ends with it.
4. Do not start `mark wait` at the gate: the board shows the ticket waiting, and the next
   decision starts a new session.
5. If a command is refused for lack of permission, do not try another way: report which
   command needed approval and stop.
6. End with one short paragraph: where the ticket stands and what the human decides next.
