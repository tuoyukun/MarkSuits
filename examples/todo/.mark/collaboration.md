# How todo is built with Mark

One orchestrator (the main Claude Code session) moves tickets forward one step at a time.
Each step is done by a fresh **role agent** that reads files, writes files, and ends. The
human opens tickets, approves or rejects at two review gates, and merges.

## Commands

| You type | What happens |
|---|---|
| `/mark:feature <description>` | The orchestrator reviews the request with you, opens a ticket once you agree, and runs the first step |
| `/mark:feature <id>` | One more step of that feature |
| `/mark:fix <description or id>` | Opens or continues a bug and runs it to `pending-merge` (no review gates) |
| `/mark:approve <id>` | Approves the opening of a ticket, the design, the plan, or a blocked ticket's way back; then continues |
| `/mark:reject <id> <comments>` | Sends a design, plan or finished branch back with your comments; then continues |
| `/mark:status` | The board: what waits on you, what is in progress |

Approvals count only when a person types them. An agent cannot approve anything.

## The chains

```
feature: designing → review-design → planning → review-plan → developing
         → (design-qa) → testing → pending-merge → passed
bug:     planning → developing → testing → pending-merge → passed
```

| Status | Who acts | Artifact |
|---|---|---|
| `designing` | designer | `design.md` + UI components + preview |
| `review-design` | **you** | approve, or reject with comments |
| `planning` | coder-plan (feature) / fix-plan (bug) | `tech-plan.md` / `fix-plan.md` |
| `review-plan` | **you** | approve, or reject with comments |
| `developing` | coder-impl | code, unit tests, `handoff.md` |
| `design-qa` | designer | `design-qa.md` (real app vs design; only when UI changed) |
| `testing` | tester | end-to-end tests, `verdict.md` |
| `failed-impl` | coder-impl | fixes for `FAIL-N` / `D-N` / your merge comments |
| `pending-merge` | **you** | merge the branch into main, or reject |
| `blocked-*` | **you** | read the reason; `/mark:approve` sends it back the way it came |

## Where things live

- `.mark/features/<id>/`, `.mark/bugs/<id>/` on main: `status.md`, `requirement.md` or
  `bug.md`, your reviews (`review-*.md`), `log.md`.
- Each ticket has a branch `feature/<id>` or `bug/<id>` and a worktree under
  `.claude/worktrees/`. Role agents write only there; their artifacts sit in the same
  ticket path inside the worktree.
- Formats of every artifact: `.mark/formats/`. Dispatch prompts: `.mark/prompts/`. Role
  definitions: `.claude/agents/`.

## Ids

| Id | Where | Meaning |
|---|---|---|
| `AC-N` | requirement / fix plan | acceptance criterion |
| `S-N` | design | a UI state |
| `T-N`, `SD-N` | tech plan | task, sequence diagram |
| `R-N` | review files | one of your review comments (numbered across rounds) |
| `D-N` | design QA | a defect between the real app and the design |
| `FAIL-N` | verdict | a test failure |

Ids are never reused, so a comment like "R-4 withdraws R-1" stays unambiguous.

## Merging

At `pending-merge` the branch has passed its tests against the latest main. Review it,
merge it into main and push, then tell the orchestrator `mark set <id> passed`. To send it
back instead: `/mark:reject <id> <comments>`.

## Rules everyone works by

1. Agents never talk to each other; files on disk are the only channel.
2. Information flows downstream: requirement → design → plan → code → tests.
3. Opening a ticket, passing a review gate and lowering an acceptance criterion are human
   decisions.
4. Enforcement comes from hooks that block (exit 2). A rule that is only written down is a
   wish.

