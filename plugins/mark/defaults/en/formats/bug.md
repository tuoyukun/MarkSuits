# Format: bug.md

Written by the orchestrator with the human when the ticket opens and during the discussion;
read only for every role (fix-plan records what it finds in `fix-plan.md`). Lives in the
ticket dir on main.

```markdown
# <id> · <title>

## Report
<the human's words, verbatim>

## Reproduction
1. <step>
2. <step>

## Expected
<what should happen instead>

## Impact
<who is affected, how often, how badly>

## Investigation
<what was already checked and found before the ticket opened or during the discussion:
the evidence (error output, `file:line`, commits), the suspected or confirmed root cause,
and what was ruled out. "unknown" if nobody has investigated yet.>
```

Unknown parts say "unknown"; fix-plan establishes them. The investigation is prior evidence,
not a verdict: fix-plan confirms or corrects it.
