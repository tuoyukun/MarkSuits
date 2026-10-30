# Format: verdict.md

Written by the tester; drives what the orchestrator does next. Rewrite it for every test
run: it describes the latest run only (earlier runs stay in git history).

```markdown
# <id> · Verdict
<!-- mark:verdict FAILED -->

Verdict: FAILED
Run: <command(s) run> · <result summary line>
Acceptance: main@<sha> · <this ticket's acceptance command> · exit 0     (PASSED runs only)
Regression impact: none

## Failures
### FAIL-3 · <short title>
- failureType: impl-bug
- routeTo: coder-impl
- criterion: AC-2
- seen: <what happened>
- reproduce: <steps or test case id>
- expected: <what should happen>
- evidence: <path to screenshot / trace / video>

## Inline fixes
- none
```

Rules:

- The verdict is `PASSED` or `FAILED`, in the anchor and on the `Verdict:` line, and they
  agree. No other values anywhere.
- `failureType` is one of `impl-bug`, `needs-unit-test`, `design-flaw`, `unclear`.
- `FAIL-N` ids are never reused: continue from the highest id of the previous verdict.
  Failures fixed since the previous run are not repeated; the orchestrator hands every
  `FAIL-N` in this file to the next role.
- Every verdict has a Regression impact line: `none`, or `extend <living journey>` and the
  steps added (the plan's regression row).
- A `PASSED` verdict has no Failures section and has the Acceptance line.
