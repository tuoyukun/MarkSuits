# Format: JOURNEYS.md

`<tests>/JOURNEYS.md` (the end-to-end test directory). Written by the tester; read by
coder-plan and fix-plan to decide which existing test a criterion extends. One row per
end-to-end test.

```markdown
# End-to-end journeys

<!-- mark:journeys -->
| test | file | suite | path | covers |
|---|---|---|---|---|
| <exact test title> | e2e/<file> | acceptance | <entry> → <key steps> → <outcome> | 0003/AC-1, 0007/AC-2 |
```

Rules:

- `suite` is `acceptance` (a ticket's short flow) or `regression` (one of the few full-path
  journeys the merge regression runs). A merged ticket's acceptance flow is frozen: do not
  extend it; extend a living regression journey or add a new acceptance flow.
- `test` is the exact title in the spec; `mark merge` refuses a branch where a test has no row
  or a row has no test. `mark journeys <worktree>` prints the rows to add and to remove; it
  fills in file and covers, so add the suite.
- `path` is what makes reuse possible: where the test starts, the states it passes through,
  where it ends. When you extend a test, update its path and covers.
- Keep the title when you change a test: a new title is a new test.
