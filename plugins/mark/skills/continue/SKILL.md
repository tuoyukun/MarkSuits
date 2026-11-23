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
   human decision, report it and stop. `pending-merge` is not a human decision: when `mark next`
   says merge, run `mark merge <id>` yourself; never ask the human to merge.

   When `mark next` is about to dispatch and prints the human's answer from the last stop,
   apply it before dispatching: if it changes a criterion or a decision, update the `AC-N` or
   add the `DEC-N` in `requirement.md` on main and `mark commit <id> -m "<what changed>"` — the
   same as `/mark:approve` step 4.
3. Run every agent and `mark merge` in the **foreground**: pass `run_in_background: false`
   when the Agent tool has that field, and wait for each to finish before the next step (where
   the harness runs it asynchronously, wait for its completion notice). A headless session
   ends when you stop, and anything still running in the background is stopped ten minutes
   later.
4. Do not start `mark wait` at the gate: the board shows the ticket waiting, and the next
   decision starts a new session.
5. If a command is refused for lack of permission, do not try another way: report which
   command needed approval and stop.
6. End with one short paragraph: where the ticket stands and what the human decides next.
