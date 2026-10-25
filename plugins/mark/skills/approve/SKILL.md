---
description: Human approval at a Mark gate (design review, plan review, opening a ticket, or sending a blocked ticket back). Only a human runs this.
argument-hint: <ticket-id>
disable-model-invocation: true
allowed-tools: Bash(mark:*)
---

!`mark rules`

## Waiting on the human

!`mark status --active`

## /mark:approve

Argument: `$ARGUMENTS`

1. The approval counts only for the ticket the human named. If `$ARGUMENTS` has no ticket id,
   list the tickets that wait on the human and ask them to type `/mark:approve <id>`; stop.
2. Run `mark approve <id>`, adding `--to <status>` when the human typed a status after the id
   (`/mark:approve 0012 developing`). It writes the gate, marks open review rounds settled,
   moves the status and pushes. What it approves depends on the status:
   - opening not yet approved: approves opening the ticket;
   - `review-design` → `planning`; `review-plan` → `developing`;
   - `blocked-spec` → back to `designing`, or `developing` if the human typed it;
   - `blocked-plan` → back to `planning`, or `developing` if the human typed it;
   - `blocked-unclear` → only where the human typed (`designing`, `planning` or `developing`).
   Never add a status the human did not type.
3. If it refuses, tell the human why in plain words and stop. Do not retry another way.
4. Then keep looping (`mark next`, dispatch, record, merge) until the next human gate or a stop,
   reporting after each step. `pending-merge` is not a human gate: run `mark merge` without
   asking again.
