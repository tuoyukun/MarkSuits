---
description: Show the Mark ticket board, what waits on the human, and what each active ticket does next.
allowed-tools: Bash(mark:*)
---

## Board

!`mark status --active`

Summarize for the human in the project's locale: first what waits on them and the decision
each one needs, then what is in progress. For a ticket they ask about, `mark next <id>`
says what happens next. Change nothing.
