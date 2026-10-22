# How a Mark project is built

One orchestrator (the main Claude Code session) moves tickets forward one step at a time.
Each step is done by a fresh **role agent** that reads files, writes files, and ends. The
human opens tickets and approves or rejects at two review gates; merging is automatic.

## Commands

| You type | What happens |
|---|---|
| `/mark:feature <description>` | The orchestrator reviews the request with you, opens a ticket once you agree, and runs the first step |
| `/mark:feature <id>` | One more step of that feature |
| `/mark:fix <description or id>` | Opens or continues a bug and runs it to `passed` (no review gates) |
| `/mark:approve <id> [<status>]` | Approves the opening of a ticket, the design, the plan, or where a blocked ticket goes next; then continues |
| `/mark:reject <id> <comments>` | Sends a design, plan or finished branch back with your comments; then continues |
| `/mark:status` | The board: what waits on you, what is in progress |
| `/mark:general <change>` | A docs/config change that belongs to no ticket: the orchestrator edits it on a throwaway lane and lands it through the regression. Code never goes this way |

Approvals count only when a person types them, with the ticket id (`/mark:approve 0012`). An agent
cannot approve anything. A `/mark:feature` or `/mark:fix` approves opening a ticket for 2 hours.

## The chains

```
feature: designing → review-design → planning → review-plan → developing
         → (design-qa) → testing → pending-merge → passed
bug:     planning → developing → testing → pending-merge → passed
```

A project without a UI (`profile = "service"`) has no designer: its features start at
`planning`, with no design review and no design QA.

| Status | Who acts | Artifact |
|---|---|---|
| `designing` | designer | `design.md` + UI components + preview + `preview.html` (what the human reviews) |
| `review-design` | **you** | approve, or reject with comments |
| `planning` | coder-plan (feature) / fix-plan (bug) | `tech-plan.md` / `fix-plan.md` |
| `review-plan` | **you** | approve, or reject with comments |
| `developing` | coder-impl | code, unit tests, `handoff.md` |
| `design-qa` | designer | `design-qa.md` (real app vs design; only when UI changed) |
| `testing` | tester | end-to-end tests, `verdict.md` |
| `failed-impl` | coder-impl | fixes for `FAIL-N` / `D-N` / your merge comments |
| `pending-merge` | orchestrator | `mark merge`; if it fails, **you** decide (retry or reject) |
| `blocked-*` | **you** | read the reason; `/mark:approve <id>` sends it back the way it came, `/mark:approve <id> developing` goes on as it is; `blocked-unclear` always needs the status (`designing`, `planning` or `developing`) |

## Where things live

- `.mark/features/<id>/`, `.mark/bugs/<id>/` on main: `status.md`, `requirement.md` or
  `bug.md`, your reviews (`review-*.md`), `log.md`.
- Each ticket has a branch `feature/<id>` or `bug/<id>` and a worktree under
  `.claude/worktrees/`. Role agents write only there; their artifacts sit in the same
  ticket path inside the worktree.
- Role agents, dispatch prompts and artifact formats ship with the Mark plugin and update
  with it (`mark format <name>` prints a format). To change one for this project, add a file
  with the same name: `.claude/agents/<role>.md`, `.mark/prompts/<scenario>.md` or
  `.mark/formats/<name>.md`. The project's file then wins.

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

At `pending-merge` the orchestrator runs `mark merge <id>`: it merges the latest main into the
ticket branch, runs the `[merge] regression` command from `.mark/config.toml` in the worktree,
fast-forwards main, pushes, marks the ticket `passed` and removes its worktree and branch.
If anything fails (conflict, red regression, push), main is left untouched and the
orchestrator stops for you: fix the cause and ask it to merge again, or
`/mark:reject <id> <comments>`.

Docs every role loads (CLAUDE.md, this file, role files, prompts, formats, fix plans) have
byte budgets in `[[doc_budget]]` of `.mark/config.toml`. A write that leaves one over budget
is refused, and so is a merge that grew one: make room instead of appending. Raising a budget
is your call.

## Rules everyone works by

1. Agents never talk to each other; files on disk are the only channel.
2. Information flows downstream: requirement → design → plan → code → tests.
3. Opening a ticket, passing a review gate and lowering an acceptance criterion are human
   decisions.
4. Enforcement comes from hooks that block (exit 2). A rule that is only written down is a
   wish.
