# Format: handoff.md

Written by coder-impl; read by the designer (design QA) and the tester.

```markdown
# <id> · Handoff

## Summary
<what was implemented, by task (T-N) or fix item>

## Acceptance self-check
<!-- mark:ac-table -->
| AC | status | evidence |
|---|---|---|
| AC-1 | implemented | src/projects.test.js::summary |
| AC-2 | implemented | frontend/src/pages/Project.tsx (end-to-end) |
| AC-3 | not implemented | see Blocked |

## States
| S-N | where it is reached in the real app |
|---|---|

## How to verify
- start: <command from CLAUDE.md>
- entry point: <URL / route / account / seed data that opens directly>

## Fix rounds
- <trigger id (FAIL-N / D-N / R-N)> · <what changed>

## Inline fixes
- none

## Blocked
<!-- mark:blocked -->
- none
```

Rules:

- Status is `implemented` or `not implemented`, nothing else.
- Evidence that names a test file names a file that exists.
- Any `not implemented` comes with a "Blocked" entry: what is missing, which `AC-N` it
  blocks, and why it cannot be done within the plan.
- The States table is required when the ticket has `design.md`; "How to verify" when it
  changes UI.
