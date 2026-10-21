# Format: requirement.md

Written by the orchestrator with the human before the ticket opens; read only for every
role. Lives in the ticket dir on main.

```markdown
# <id> · <title>

## Goal
<one paragraph: who needs what, and why>

## User stories
- US-1: As a <user>, I want <action>, so that <outcome>.

## Acceptance criteria
<!-- mark:ac -->
- AC-1: <decidable statement about observable behaviour>
- AC-2: …

## Out of scope
- <what this ticket deliberately does not do>

## Dependencies
- <libraries, services or other tickets this relies on, or "none">

## Open questions
<!-- mark:open-questions -->
- none
```

Rules:

- Every `AC-N` can be decided true or false by someone who did not write it.
- An `AC-N` is behavior a user or caller can observe. "There is an end-to-end test for X" is
  not one: the tester writes those for every criterion anyway.
- Criteria are verified end to end by default. Tag one `[unit]` when no user action can reach
  it (a pure function, an algorithm, a backend contract or error code): coder-impl covers it
  with a unit test, and the tester accepts that test.
- Ids are never reused or renumbered; a dropped criterion stays, struck through, with the
  reason.
