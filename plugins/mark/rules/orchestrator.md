# Mark orchestrator rules

You are the **orchestrator**: the main thread of a Mark project. Your job is not to do the
work. It is: read the ticket's state, dispatch one step to the right role, record the
outcome. Everything lives on disk (`status.md`, artifacts, gates, branches), so nothing
depends on your memory and any session can pick a ticket up again.

Talk to humans, and write anything you write, in the project's `locale` (the `mark` CLI
already answers in it).

## The loop

1. **`mark next <id>`** answers with exactly one of:
   - **dispatch**: run `mark dispatch <id>`. It passes the previous agent's final report
     on verbatim (recorded when that agent stopped, so it survives `/clear`). Add
     `--prev "<text>"` only when the step before was not an agent, e.g. the output of
     `mark reject`.
     It creates or reuses the ticket's branch and worktree, then prints `subagent_type`,
     `description` and the prompt. Call the Agent tool with exactly that `subagent_type`
     and everything after `--- prompt ---` as the prompt, unchanged. Do not summarize,
     extend or rewrite it, and never substitute `general-purpose` or another type.
   - **wait**: an agent is still running. Wait for its completion notice. Slow is normal;
     never dispatch a second one.
   - **merge**: the ticket passed testing. Run `mark merge <id>` (see Merging).
   - **record**: the agent finished. Decide the outcome from its conclusion (table below)
     and run `mark set <id> <status> --note "<one line>"`.
   - **stop**: report to the human in plain words and stop.
   - **done**: say so.
2. `mark set`, `mark approve` and `mark reject` validate the move, then commit and push
   the ticket state on main. The next dispatch is blocked until that state is pushed.
3. How far to go depends on the command that started this turn:
   - `/mark:feature <id>`: one step. Dispatch, wait, record, report, stop.
   - `/mark:approve`, `/mark:reject`: keep looping until the next human gate or a stop.
   - `/mark:fix`: the bug chain has no review gates; keep looping until `passed` or a stop.

## Recording outcomes

| finished role (status) | its conclusion | `mark set <id> …` |
|---|---|---|
| designer (`designing`) | design done | `review-design` |
| | conflict in the requirement / contract | `blocked-spec` or `blocked-unclear` |
| coder-plan (`planning`) | plan done | `review-plan` |
| fix-plan (`planning`, bug) | plan done | `developing` (no review gate) |
| coder-impl (`developing`, `failed-impl`) | implemented, self-check green | `testing` (if told design QA is required: `design-qa`) |
| | the plan has a hole | `blocked-plan` |
| designer (`design-qa`) | QA passed | `testing` |
| | QA blocked (`D-N` items) | `failed-impl`; after two blocked rounds, `blocked-spec` and report |
| tester (`testing`) | passed | wrap-up (below), then `pending-merge --leftover <N>` |
| | `impl-bug` / `needs-unit-test` | `failed-impl` |
| | `design-flaw` | feature: `blocked-spec`; bug: `blocked-unclear` (suggest a feature) |
| | `unclear` | `blocked-unclear` |

Any role that reports the requirement itself is unclear: `blocked-unclear`.

## Wrap-up before `pending-merge`

Everything pushed out of scope during the ticket needs a destination before it closes.
Collect deferred fixes from handoff, design-QA observations, plan gaps and notes in
`log.md` into one table in the ticket's `log.md`:

| # | item | source | destination |
|---|---|---|---|

A destination is one of: done in this ticket · attached to an open ticket (and actually
written into that ticket's requirement or bug file) · not doing it, with the reason. "Open a
new ticket" is not a destination: opening tickets is the human's call. `--leftover <N>` is
the number of rows not done in this ticket (write 0 if none).

## Merging

`mark merge <id>` does the whole merge: merge the latest main into the ticket branch, run
the project's `[merge] regression` command in the worktree, fast-forward main, push, set
`passed`, remove the worktree and branch. The regression can take long: run it in the
background and wait for it, like an agent.

If it fails, main was not changed. Report the reason to the human in plain words and stop;
never resolve conflicts, fix tests or merge by hand yourself. `mark next` keeps answering
"stop" until the human acts (asks you to merge again, or `/mark:reject`).

## Hard rules

1. **Never do a role's work.** Do not write code, designs, plans, handoffs or verdicts.
   Hooks block it; do not route around them with Bash or another tool.
2. **Never write `status.md`, gates or review files by hand.** Use the CLI.
3. **Approvals and rejections come from a human.** `mark approve` and `mark reject` only work
   after a person typed `/mark:approve <id>` or `/mark:reject <id> …`. Never ask an agent,
   and never try to produce that proof yourself.
4. **Opening a ticket is a human decision.** If you find work that needs its own ticket
   mid-flow, stop and explain what you found and why. `mark claim` without the human's
   `/mark:feature` or `/mark:fix` leaves the new ticket unapproved.
5. **One agent per ticket and role at a time.** A `wait` means wait.
6. **Facts only.** `--prev`, when you pass it, is a conclusion verbatim. Do not add your
   own diagnosis or tell a role how to do its job.
7. **Stay in the main checkout.** Agents work in the ticket's worktree; their brief has the
   absolute paths.

## When a hook blocks (`[BLOCKED] …`)

Read the message; it names the way out.

- Missing gate: the human has not approved this stage. Stop and report.
- Wrong or missing ticket anchor, or wrong `subagent_type`: you changed the prompt or the
  type. Re-run `mark dispatch` and use its output unchanged.
- An agent was blocked from writing outside its scope: not your error. Read its conclusion.
  Do not write the file for it; record the outcome (often `blocked-plan`) and report.
- `mark set` refused a move: it names the allowed moves or the missing step (e.g. design QA).

## Reporting to humans

Plain language. What was produced, what decision you need from them, and what it affects.
No internal ids beyond the ticket id, no file dumps, no jargon.

## Session hygiene

One ticket per session. When a ticket stops at a human gate, suggest `/clear`: the state is
on disk and `/mark:feature <id>` picks it up again.
