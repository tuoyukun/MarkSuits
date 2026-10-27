# Format: design.md

Written by the designer; read by coder-plan, coder-impl and the tester.

```markdown
# <id> · Design

## States
<!-- mark:states -->
| id | component | state | how it looks | entered when (container decides) | reach |
|---|---|---|---|---|---|
| S-1 | ProjectCard | default | … | project loaded | e2e |
| S-2 | ProjectCard | empty | … | project has no tasks | e2e |
| S-3 | ProjectCard | error | … | load failed | qa-only |

## Design intent
<why it looks and behaves this way; alternatives rejected and why>

### Visual check
- rounds: <N>
- changed: <what you changed after looking at screenshots>
- kept on purpose: <what looks imperfect but stays, and why>

## Props contract
<!-- mark:props-contract -->
<per component: each prop, its meaning, which props the container controls>

## Integration contract
<!-- mark:integration-contract -->
1. Props that need a stable identity: <list, or "none">
2. CSS the container must provide: <overflow, positioning, size …, or "none">
3. z-index ranges used: <ranges, or "none">

## Responsive behaviour
<breakpoints and what changes>

## Preview
<how to run the live preview in the project; `preview.html` next to this file is the built
copy the human reviews>

## Review responses
| review id | change | or objection |
|---|---|---|

## Inline fixes
- none

## Open questions
<!-- mark:open-questions -->
- none
```

Rules:

- `S-N` ids are never reused; the preview renders exactly the states listed here.
- Error, empty, loading and edge states are listed, not just the happy path.
- `reach`: `e2e` when a user action in the project's test environment gets there and it stays
  long enough to assert; `qa-only` when it does not (a flash, a state that environment cannot
  produce). The tester does not fail `qa-only` states; design QA checks them.
- The three integration-contract items are always present; "none" is an answer, a missing
  item is not.
