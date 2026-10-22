# Examples

| Example | What it is |
|---|---|
| [`todo/`](todo/) | A small todo app (vanilla JS frontend, Python standard-library backend, Playwright end-to-end tests), generated from the Mark template (`web-fullstack` profile) in `en` and filled in. It ships with one known bug so the bug chain has something to fix. |
| [`notes/`](notes/) | A notes JSON API with no UI (Python standard library; end-to-end tests over HTTP with `unittest`), from the `service` profile. No designer: features go straight to planning. It also ships with one known bug. See [the notes walkthrough](#the-notes-service-service-profile). |
| [`expenses/`](expenses/) | An expense tracker with no backend (vanilla JS, data in localStorage, Playwright end-to-end tests), from the `web-frontend` profile. Designer and design review as in `todo/`. One known bug. See [the expenses walkthrough](#the-expense-tracker-web-frontend-profile). |
| [`habits/`](habits/) | A habit tracker: an Expo (React Native) app and a Python standard-library backend, Maestro end-to-end tests on the iOS simulator, from the `mobile-fullstack` profile. Designer and design review as in `todo/`; the preview is the web build of the real components. One known bug. See [the habits walkthrough](#the-habit-tracker-mobile-fullstack-profile). |

The scaffold files in `todo/` (`.mark/`) are exactly what `mark init` writes (role agents,
prompts and formats come from the plugin); `tests/test_example.py` re-renders them and fails if they drift. Only `CLAUDE.md`
and `.gitignore` are edited by hand, as a real project would.

## Run it

Mark creates branches and worktrees and pushes to `origin`, so the example runs in its own
repository, never inside this one:

```bash
python3 examples/sandbox.py ~/mark-sandbox/todo      # copy + git init + local bare origin
cd ~/mark-sandbox/todo
npm --prefix tests ci                                # Node 18+, Python 3.11+
npm --prefix tests exec playwright install chromium
bash scripts/selftest.sh && bash scripts/regression.sh   # baseline: everything green
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
| verify | tester | an end-to-end test, `verdict.md` (`PASSED` after merging main and running the full regression) |

At `pending-merge` the orchestrator runs `mark merge b0001`: it merges the latest main into
the ticket branch, runs `bash scripts/selftest.sh && bash scripts/regression.sh` there (`[merge] regression`),
fast-forwards main, pushes, marks the ticket `passed` and removes its worktree and branch.
If the merge conflicts or the regression fails, main is untouched and the orchestrator stops and
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

## The notes service (`service` profile)

```bash
python3 examples/sandbox.py ~/mark-sandbox/notes --example notes
cd ~/mark-sandbox/notes
bash scripts/selftest.sh && bash scripts/regression.sh   # baseline: everything green, nothing to install
claude --plugin-dir <path to this repo>/plugins/mark
```

A bug: deleting a note and then adding one makes another note disappear.

```
/mark:fix After I delete a note and add a new one, a different note I had is gone from the list.
```

(The cause: `store.add` numbers a note `len(notes) + 1`, so it can reuse a live id and
overwrite that note.) The chain is the same as in the todo app: fix-plan, coder-impl, tester
(a new end-to-end test over HTTP), then `mark merge`.

A feature, with no design step:

```
/mark:feature Search notes: GET /api/notes?q=<text> returns only the notes whose text contains it, ignoring case.
```

After you confirm, the ticket opens at `planning` and the **coder-plan** goes first; the
only human review is the plan review (`/mark:approve <id>`). Then coder-impl and tester run
to `pending-merge`.

## The expense tracker (`web-frontend` profile)

```bash
python3 examples/sandbox.py ~/mark-sandbox/expenses --example expenses
cd ~/mark-sandbox/expenses
npm --prefix tests ci && npm --prefix tests exec playwright install chromium
bash scripts/selftest.sh && bash scripts/regression.sh   # baseline: everything green
claude --plugin-dir <path to this repo>/plugins/mark
```

A bug: amounts lose their cents.

```
/mark:fix I added a lunch for 12.50 and the list shows 12.00; the total is wrong too.
```

(The cause: `store.parseAmount` uses `parseInt`. The baseline tests only use whole amounts.)
The chain is the same as in the todo app.

A feature, with a design step:

```
/mark:feature Give each expense a category (Food, Transport, Other) and show a subtotal per category under the list.
```

The designer builds the category picker and the subtotals in `frontend/src/ui/` and stops at
design review; coder-plan plans the store and wiring; coder-impl, design QA and the tester follow.

## The habit tracker (`mobile-fullstack` profile)

Needs macOS with Xcode (an iOS simulator runtime), Node, and the Maestro CLI
(`brew tap mobile-dev-inc/tap && brew install mobile-dev-inc/tap/maestro`, Java 17+).

```bash
python3 examples/sandbox.py ~/mark-sandbox/habits --example habits
cd ~/mark-sandbox/habits
(cd app && npm ci && npx expo start --ios)   # once: installs Expo Go on the simulator; Ctrl-C when the app shows
bash scripts/selftest.sh && bash scripts/regression.sh   # baseline: everything green
claude --plugin-dir <path to this repo>/plugins/mark
```

The end-to-end run (`e2e/regression.sh`) takes a device lock, starts its own backend with
the date pinned to 2026-03-02 and its own dev server, and runs the Maestro flows in Expo Go.

A bug: streaks break at the start of a month.

```
/mark:fix I ticked Feb 28, Mar 1 and Mar 2 and the habit says 2-day streak instead of 3.
```

(The cause: `store.streak` compares day-of-month numbers instead of dates. The unit tests
and the baseline flows stay inside one month.)

A feature, with a design step:

```
/mark:feature Let me delete a habit: a long press on its card asks for confirmation, then removes it.
```

The designer builds the confirmation in `app/src/ui/` and stops at design review with a
`preview.html` built from the real components; coder-plan plans the backend route and the
wiring; coder-impl, design QA on the simulator and the tester follow.

## Updating the examples

When the template changes, re-render every example's scaffold in place from its `.mark/template.toml`:

```bash
python3 tools/sync_example.py    # leaves CLAUDE.md and .gitignore alone; merge those by hand if needed
```
