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

1. If no ticket id was given and exactly one ticket waits on the human, use it; if several
   do, ask which one.
2. Run `mark approve <id>`. It writes the gate, marks open review rounds settled, moves the
   status and pushes. What it approves depends on the status:
   - opening not yet approved: approves opening the ticket;
   - `review-design` → `planning`; `review-plan` → `developing`;
   - `blocked-spec` → back to `designing`; `blocked-plan` → back to `planning`.
3. If it refuses, tell the human why in plain words and stop. Do not retry another way.
4. Then keep looping (`mark next`, dispatch, record) until the next human gate or a stop,
   reporting after each step.
