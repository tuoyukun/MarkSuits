# Examples

| Example | What it is |
|---|---|
| [`todo/`](todo/) | A small todo app (vanilla JS frontend, Python standard-library backend, Playwright end-to-end tests), generated from the Mark template in `en` and filled in. It ships with one known bug so the bug chain has something to fix. |

The scaffold files in `todo/` (`.claude/agents/`, `.mark/`) are exactly what `copier copy`
produces; `tests/test_example.py` regenerates them and fails if they drift. Only `CLAUDE.md`
and `.gitignore` are edited by hand, as a real project would.

## Run it

Mark creates branches and worktrees and pushes to `origin`, so the example runs in its own
repository, never inside this one:

```bash
python3 examples/sandbox.py ~/mark-sandbox/todo      # copy + git init + local bare origin
cd ~/mark-sandbox/todo
npm ci && npx playwright install chromium            # Node 18+, Python 3.11+
npm test                                             # baseline: everything green
claude --plugin-dir <path to this repo>/plugins/mark
```

Inside Claude Code, the walkthrough below takes the app through one bug and one feature.
Each block is what **you** type; agents do the rest. The recorded run below took about
25 minutes of agent time and roughly $6 of tokens.

## Walkthrough

### 1. A bug: ticking a todo does not survive a reload

```
/mark:fix When I tick a todo as done it shows as done, but after I reload the page it is unticked again.
```

The orchestrator reads the code, says whether this is a bug or a feature, lists what is
missing (reproduction, expectation, impact) and waits. Nothing is created yet.

```
Yes, that matches. Open the ticket and run the chain.
```

Now it opens `b0001-…`, writes `bug.md`, and runs the bug chain without stopping
(the bug chain has no review gates):

| step | role | produces (in the ticket's worktree) |
|---|---|---|
| plan the fix | fix-plan | `fix-plan.md`: root cause, `AC-N`, the change |
| implement | coder-impl | the fix, a unit test, `handoff.md` |
| verify | tester | an end-to-end test, `verdict.md` (`PASSED` after merging main and running `npm test`) |

At `pending-merge` the orchestrator runs `mark merge b0001`: it merges the latest main into
the ticket branch, runs `npm test` there (`[merge] regression` in `.mark/config.toml`),
fast-forwards main, pushes, marks the ticket `passed` and removes its worktree and branch.
If the merge conflicts or `npm test` fails, main is untouched and the orchestrator stops and
tells you why.

(`mark` is on PATH inside Claude Code; outside it, run `<repo>/plugins/mark/bin/mark`.)

### 2. A feature: items left and "Clear completed"

```
/mark:feature Show how many todos are still open ("3 items left") and add a "Clear completed" button that deletes every done todo.
```

Again a review before anything exists: the orchestrator challenges the request and asks
what is unclear (singular wording, whether the button hides or disables, whether clearing
needs a confirmation…). Answer, then confirm:

```
"1 item left" in the singular. Hide the button when nothing is done. No confirmation. Open it.
```

It opens `0001-…` with numbered acceptance criteria and dispatches the **designer**, which
writes `design.md` (every state as `S-N`) and builds the footer component and its preview in
`frontend/src/ui/`. Then it stops at **design review**: open the preview it names and read
`design.md`.

```
/mark:approve 0001
```

or, to send it back with comments (each line becomes an `R-N` item the designer must address):

```
/mark:reject 0001 The count should sit left, the button right, on one line.
```

After approval the **coder-plan** writes `tech-plan.md` (tasks `T-N`, sequence diagrams
`SD-N`, the new API) and it stops at **plan review**:

```
/mark:approve 0001
```

From here it runs to the end: **coder-impl** (backend endpoint, wiring, unit tests,
`handoff.md`) → **designer** design QA of the integrated app (`design-qa.md`; the change
touches `frontend/`) → **tester** (end-to-end tests, `verdict.md`) → `pending-merge`. Merge
it the same way as the bug, then `mark set 0001-… passed`.

## A recorded run (v0.6.0)

Mark v0.6.0, Claude Code 2.1, default model, the prompts above typed verbatim (plus one
`/mark:reject` to exercise design rework). No hook had to block anything: every agent stayed
in its write scope and every dispatch passed the gates.

| step | outcome |
|---|---|
| `/mark:fix …` | orchestrator found the cause by reading `store.py`, called it a bug, asked to confirm reproduction / expectation / impact |
| confirm | `b0001` opened; fix-plan reproduced it against the store (6 `AC-N`); coder-impl moved one line and added 4 unit tests; tester added a tick-reload-untick-reload browser test, checked it fails on the old code, merged main, `npm test` green → `pending-merge` with 1 leftover ("rename is only testable through the API") |
| merge, `mark set … passed` | 13 unit + 6 end-to-end tests green on main |
| `/mark:feature …` | six questions (singular, empty list, hide vs disable, confirmation, failure, one bulk call vs N deletes) |
| "Your defaults. Open it." | `0001` opened with 9 `AC-N`; designer: `TodoFooter`, 8 states `S-1…S-8`, preview, screenshots at 1280 and 390 px → design review |
| `/mark:reject 0001 … "Clear completed (2)"` | round 1 with `R-1`; designer reworked only that → design review |
| `/mark:approve 0001` | coder-plan: `DELETE /api/todos/completed`, ADR 0001, non-optimistic clear, 8 tasks → plan review |
| `/mark:approve 0001` | coder-impl → design QA (8/8 states match in the real app) → tester: 8 new browser tests incl. a forced 500 and the in-flight state, full regression green → `pending-merge` |
| merge, `mark set … passed` | 15 unit + 14 end-to-end tests green on main |

The feature's tester also found a bug that was already in the app: adding several todos
quickly can drop one (`onAdd` reads the list before awaiting the server). The orchestrator
did not open a ticket for it on its own; it put it in the wrap-up table in `log.md` and left
the decision to the human. Try it as a second `/mark:fix`.

### Things to try

- Ask the orchestrator to "just write the code": it refuses; hooks block it anyway.
- Type "approve it" instead of `/mark:approve`: approvals only count when a human types the
  command.
- `mark status` at any time; every ticket's state is in `.mark/{features,bugs}/<id>/`.

## Updating the example

When the template changes, regenerate the scaffold in place (requires Copier):

```bash
cd examples/todo
copier recopy --defaults --overwrite --vcs-ref HEAD -a .mark/.copier-answers.yml
git checkout -- CLAUDE.md .gitignore    # keep the project-owned files, then merge by hand if needed
```
