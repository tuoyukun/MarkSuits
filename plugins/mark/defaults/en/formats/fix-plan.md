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
- <component in the UI directory>: <what changes and why> [ui]

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
- End-to-end tests are the tester's: name no test title, suite or steps. The tester writes one
  acceptance test per AC and decides which core-flow regression journey to add or extend.
- Tag a fix item `[ui]` when it changes the UI directory: the designer does it before coder-impl,
  and your outcome is `designing`. `inline` and `ui` are literal in every language.
- If the fix needs a data model, cross-module contract or framework change, it is not a bug
  fix: say so in open questions.
