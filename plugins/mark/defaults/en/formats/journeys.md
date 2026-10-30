# Format: JOURNEYS.md

`<tests>/regression/JOURNEYS.md` (the end-to-end suite root is `[paths] tests`). Written by
the tester; read before adding a regression test, so an existing journey is extended instead.
One row per regression test. Acceptance tests live in `<tests>/tickets/<id>/` and are not
listed here.

```markdown
# Regression journeys

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| <exact test title> | regression/<file> | <entry> → <key steps> → <outcome> | <ticket>/AC-1, baseline/<flow> |
```

Rules:

- Only tests under `<tests>/regression/` belong here: the few core flows `mark merge` runs.
  Acceptance tests are the ticket's own evidence and are never copied into regression.
- `test` is the exact title in the spec; `mark merge` refuses a branch where a test has no row
  or a row has no test. `mark journeys <worktree>` prints the rows to add and to remove; it
  fills in file and covers, so write the path.
- `path` is what makes reuse possible: where the test starts, the states it passes through,
  where it ends. When you extend a test, update its path and covers.
- Keep the title when you change a test: a new title is a new test.
- A core flow that changed but has no journey yet gets one; a ticket that touches no core
  flow adds nothing here.
