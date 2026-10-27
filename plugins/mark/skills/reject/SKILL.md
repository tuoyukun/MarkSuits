---
description: Human rejection at a Mark review gate; records the comments as a numbered review round and sends the ticket back for rework. Only a human runs this.
argument-hint: <ticket-id> <comments>
disable-model-invocation: true
allowed-tools: Bash(mark:*)
---

!`mark rules`

## /mark:reject

Arguments: `$ARGUMENTS` (ticket id, then the human's comments)

1. Split the comments into separate items, one issue each. Keep the human's meaning
   exactly: tidy the wording if needed, but add no reasons, requirements or fixes of your
   own. If the human withdraws or overrides an earlier comment ("drop R-1"), write that as
   a new item that names it; never edit earlier rounds.
2. At `pending-merge` only: if the comments clearly say the approach itself is wrong, add
   `--to planning`; otherwise the ticket goes back to implementation. If unsure, use the
   default and say which you chose.
3. Run `mark reject <id> --item "<first>" --item "<second>" …`. It appends a pending round
   to the review file, moves the status and pushes.
4. If it refuses, tell the human why and stop.
5. Then dispatch the rework (`mark next`, `mark dispatch`) and keep looping (dispatch, record,
   merge) until the next human gate or a stop. The brief tells the agent which round is open.
   Unless `[gates] rework_review = true`, the reworked design or plan does not come back for
   review: `mark set` passes it and the loop goes on; tell the human so.
