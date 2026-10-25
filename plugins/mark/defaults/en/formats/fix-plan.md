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

## End-to-end coverage
<!-- mark:e2e-plan -->
| AC | action | test | steps to add / why no existing test fits |
|---|---|---|---|
| AC-1 | extend | <exact title from JOURNEYS.md> | <steps to add, and after which existing step> |
| AC-2 | new | <title of the new test> | closest: <existing title>; <why adding steps to it cannot cover this> |
| AC-3 | unit | - | <covered by a unit test (coder-impl)> |

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
- **End-to-end coverage:** read `<tests>/JOURNEYS.md` first. Every `AC-N` gets one row. The
  default is `extend`: add steps to the existing test whose path already passes through this
  state. Write `new` only when no existing test can reach it by adding steps, and name the
  closest one and why. The tester may add no test this table does not name as new.
  `extend`, `new` and `unit` are literal in every language.
- Tag a fix item `[ui]` when it changes the UI directory: the designer does it before coder-impl,
  and your outcome is `designing`. `inline` and `ui` are literal in every language.
- If the fix needs a data model, cross-module contract or framework change, it is not a bug
  fix: say so in open questions.
