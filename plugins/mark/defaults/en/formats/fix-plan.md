# Format: fix-plan.md

Written by fix-plan; goes straight to coder-impl (no review gate). Keep it short: it points
the way, it does not contain the implementation.

```markdown
# <id> · Fix plan

## Root cause
<what is wrong and why, with file and line references>

## Reproduction
1. <step>
→ <what happens>

## Fix
- <file or module>: <what changes and why> [inline]

## Acceptance points
<!-- mark:ac -->
- AC-1: <decidable check that the bug is gone>
- AC-2: regression: <what must keep working>

## Affected files
- <path>

## Rework
- <date> · <trigger (R-N or blocked-plan)> · <what changed>

## Risks and open questions
<!-- mark:open-questions -->
- none
```

Rules:

- At least one acceptance point is a regression check.
- Tag an acceptance point `[unit]` when no user action can reach it; coder-impl covers it with
  a unit test. Untagged points are verified end to end.
- If the fix needs a data model, cross-module contract or framework change, it is not a bug
  fix: say so in open questions.
