---
description: Open the Mark web board - every ticket by status, its documents (requirement, design, preview, tech plan, verdict) and its status history, updating live; the human can approve or reject gates there. Use when the human asks for the board, the kanban or a web view of the tickets.
allowed-tools: Bash(mark:*)
---

## Board

!`mark board`

Tell the human, in the project's locale, that the board opened in their browser (the URL is
above). Decisions work only in the window `mark board` opened; a URL typed or pasted by hand is
read-only. A decision made on the board is the human's; you never decide for them there.
`mark board --stop` stops it. Change nothing else.
