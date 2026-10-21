# Format: design-qa.md

Written by the designer during integration QA (after coder-impl, before the tester).
The engine reads the result anchor: `mark set <id> testing` is refused for a ticket that
needs design QA until the latest anchor says `passed`.

```markdown
# <id> · Design QA
<!-- mark:qa-round 1 -->

## Environment
<entry point used, from handoff.md>

## State comparison
| S-N | reached in the real app | matches the preview | note |
|---|---|---|---|
| S-1 | yes | yes | |
| S-2 | yes | no → D-1 | |
| S-3 | cannot reach | — | no entry point for this state |

## Fixed in the UI layer
- S-4: <what was wrong in the components and what you changed>

## Defects for coder-impl
### D-1 · <short title>
- state: S-2
- seen: <what the real app shows>
- expected: <what the design says>
- cause: <what in the container causes it: assembly, data, timing, wrapping CSS …>

## Observations
| observation | whose scope | introduced by this ticket |
|---|---|---|

## Result
<!-- mark:qa passed -->
```

Rules:

- The comparison covers every `S-N` of `design.md`, one row each. "Cannot reach" is a
  finding, not a skip.
- A cause in the UI layer you fix yourself and list under "Fixed in the UI layer", without
  an id. A cause in the container becomes a `D-N` for coder-impl; you do not touch it.
  Only open defects carry `D-N` ids: the orchestrator hands every `D-N` in this file to
  coder-impl.
- Any `D-N` means `<!-- mark:qa blocked -->`. Exactly one result anchor.
- In a later round, rewrite the file for that round (`mark:qa-round 2`). Defects resolved
  since the last round are not repeated (git keeps the history); new ones continue from
  the previous highest `D-N`, so ids are never reused. States that no change could affect may be
  marked "not rechecked (unchanged)"; never in round 1.
- After two blocked rounds, stop iterating: the human decides.
