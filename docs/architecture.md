# Mark architecture

## 1. Topology

```
Human ──/mark:feature /mark:fix /mark:approve /mark:reject──▶ orchestrator (main thread)
                                                   │ reads status.md, dispatches ONE step
        ┌───────────┬────────────┬─────────────┬───┴──────┐
     designer   coder-plan   coder-impl      tester    fix-plan     stateless subagents
        └───────────┴────────────┴─────────────┴──────────┘
                                   ▼
                    .mark/{features,bugs}/<id>/          the only channel between agents
```

Invariants:

1. Subagents never talk to each other; artifacts on disk are the only medium.
2. Subagents are stateless; every dispatch carries all paths it needs (from a prompt template).
3. Information flows downstream only: requirement → design → plan → code → test.
4. Opening a ticket is a human decision (`<id>.ticket-approved` gate).
5. Only an `exit 2` counts as enforcement. Documentation alone is a wish.

## 2. Three layers

| Layer | Contents | Owner | Upgrade |
|---|---|---|---|
| **Engine** (`plugins/mark`) | hooks, orchestration skills, CLI (`bin/`), shared role rules (`skills/role-rules`), `lib/mark` | Mark | plugin version bump → `claude plugin update` |
| **Scaffold** (`template/`) | `CLAUDE.md`, `.mark/collaboration.md`, role agents, prompt templates, artifact formats, `.mark/config.toml` | the project, after generation | `copier update` (3-way merge) |
| **Project content** | module boundaries, contracts, write-scope exceptions, domain scripts | the project | — |

Why role agents live in the scaffold, not the plugin: plugin agents are namespaced
(`mark:coder-impl`), ignore `permissionMode`/`hooks`/`mcpServers` frontmatter, and role
prompts always contain project facts (stack, paths). The engine normalizes role names, so
either location works for enforcement.

## 3. Engine ↔ project contract

`.mark/config.toml` is the only interface:

- `mark_schema` — integer; the engine refuses unknown versions (exit 2 with a migration hint).
- `locale` — `zh-CN` | `en`; selects hook message language and tells the orchestrator which
  language to use with humans and in artifacts.
- `[paths]`, `[gates]`, `[[write_rules]]`, `[[doc_budget]]`, `[worktree]` — everything that used to be hardcoded.

Hooks locate the project by walking up from the payload `cwd` to `.mark/config.toml`; no
config means "not a Mark project" → exit 0. This matters because plugin hooks fire in every
session where the plugin is enabled.

Hooks recognize artifact sections by anchors (`<!-- mark:ac-table -->`), never by heading
text, so templates can be localized freely.

## 4. Ticket lifecycle (feature chain)

| status | action | role | gate required |
|---|---|---|---|
| designing | design | designer | — |
| review-design | stop, wait for human | — | — |
| planning | tech plan | coder-plan | design-approved |
| review-plan | stop, wait for human | — | — |
| developing | implement | coder-impl | plan-approved |
| design-qa | integration design check (UI changes only) | designer | — |
| testing | verify | tester | plan-approved |
| pending-merge | automated merge (regression → ff-only → push) | — | — |
| passed | done | — | — |

Bug chain: fix-plan → coder-impl → tester, no review gates. General mode: no subagents,
non-code changes only, on a throwaway lane (see General mode below).

Failure routing is decided by the orchestrator from the tester's `failureType`
(`impl-bug` → coder-impl, `design-flaw` → designer via human, `unclear` → human).

### Tickets and the `mark` CLI

- One directory per ticket: `.mark/features/<NNNN-slug>/`, `.mark/bugs/b<NNNN-slug>/`.
  The directory is the index; there is no global board (a shared board conflicts on every
  concurrent change). Id and kind come from the path, never from file content.
- `status.md` frontmatter: `status`, `owner`, `updated`, `updater`, `desc` (≤200 chars),
  optional `merge-after: [0012, b0007]`, and `leftover: <N>` from `pending-merge` on.
  The note below it is ≤240 chars; process details go in `log.md`.
- `mark claim <feature|bug> "<desc>" [--slug s]` reserves a number with an `O_EXCL` marker
  file under `.numbers/` (gitignored), so concurrent sessions never share a number. A failure
  after reservation releases the number.
- `mark status [--active|--json|--check]` renders the view on demand; nothing is stored.
- Both commands resolve the **main checkout** via `git rev-parse --git-common-dir`, so they
  give the same answer from any worktree.
- Legal moves live in `lib/mark/states.py` (`TRANSITIONS`), used by the status guard in M2.

### Guards (v0.3)

All hooks go through one entry, `hooks/mark_hook.py <group>`; guards are pure functions in
`lib/mark/guards/` returning a message or None. A crashing guard fails open and says so.

| group | event / matcher | guards, in order |
|---|---|---|
| `pre-write` | PreToolUse `Edit\|Write\|MultiEdit\|NotebookEdit` | **scope** (engine rules, then `[[write_rules]]`, first match wins) · **worktree** (roles never write in the main checkout; the main checkout only takes ticket dirs, gates, locks and `main_writable`) · **ticket** (no artifact without `<id>.ticket-approved`) · **status** (main checkout on the main branch, valid fields, legal move) · **budget** (`[[doc_budget]]`, see Doc budget) |
| `pre-dispatch` | PreToolUse `Agent\|Task` | **target** (exactly one existing ticket, via `mark:ticket` anchor or ticket path) · **gate** (feature roles need `[gates]`; `<gate>.waived` counts) · **branch** (worktree on `<kind>/<id>`, cut from main unless `base-branch` is declared, pushed to origin) · **status-commit** (ticket state committed and main pushed) · **dedup** (one live agent per ticket+role; creates the lock) |
| `pre-bash` | PreToolUse `Bash` | nobody touches human tokens; subagents never run state-changing `mark` commands, never commit or push on main; nobody checks out a ticket branch in the main checkout |
| `post-dispatch` | PostToolUse `Agent\|Task` | binds the agent id to the lock |
| `post-write` | PostToolUse writes | reminds to commit ticket state on main (feedback only) |
| `user-prompt` | UserPromptSubmit | records a token when a human types `/mark:approve`, `/mark:reject`, `/mark:feature` or `/mark:fix` (never blocks) |
| `subagent-stop` | SubagentStop | required outputs (`[outputs]`, or `mark:outputs` in the prompt) must exist in the ticket dir of some checkout; otherwise the subagent keeps running. Result goes to `.mark/locks/<id>.<role>.result.json`, with the agent's final report (`conclusion`, the default `--prev` of the next dispatch) |

Engine-fixed rules (no config can loosen them): `.claude/**`, `.mark/config.toml`, gates, locks,
ticket `status.md` and `review-*.md` are main-thread only; `locks/human/**` is writable by nobody. Locks bound to a live agent are never
reclaimed by age; a human releases a dead one with `mark unlock <id> <role>`.
Set `MARK_DEBUG_LOG=<file>` to record raw hook payloads.

### Orchestration (v0.4)

The orchestrator is the main thread, driven by plugin skills. The skills stay thin: every
decision that can be computed is computed by the `mark` CLI and tested.

| skill | does | continues until |
|---|---|---|
| `/mark:feature <id \| text>` | new: pre-start review with the human, `mark claim`, `requirement.md`; existing: one step | one step |
| `/mark:fix <id \| text>` | same for bugs (`bug.md`) | `pending-merge` or a stop (no review gates) |
| `/mark:approve <id>` | `mark approve`, then continues | next human gate or stop |
| `/mark:reject <id> <text>` | splits comments into items, `mark reject`, dispatches the rework | next human gate or stop |
| `/mark:status` | board summary | — |
| `/mark:general <text>` | no-ticket docs/config change on a throwaway lane, then `mark general merge` | landed or a stop |

Each skill injects `mark rules` (the shared orchestrator rulebook, `plugins/mark/rules/orchestrator.md`)
and the live board with `!` commands. `approve` and `reject` set `disable-model-invocation`.

The loop: `mark next <id>` returns one of dispatch · wait · record · stop · done.

- **dispatch**: `mark dispatch <id> [--prev "<conclusion>"]` creates or reuses the branch, worktree and
  remote branch (refusing while the worktree has uncommitted work), then prints `subagent_type` and
  a prompt: the `mark:ticket` anchor, `mark:outputs` when the template overrides outputs, and the
  project's template for the scenario filled with verified facts (worktree, branch, artifacts in the
  worktree and on main, required outputs, trigger, previous conclusion, open review rounds).
- **wait**: a dispatch lock exists for the ticket.
- **record**: a SubagentStop result newer than `status.md` exists; the orchestrator runs
  `mark set <id> <status>`, choosing among the legal moves listed.

Scenario (template) selection, from status plus artifacts: `designing` → `designer-initial`, or
`designer-review-rework` (pending rounds in `review-design.md`), or `designer-rework` (after a
verdict or design QA) · `planning` → `coder-plan` / `coder-plan-rework`, bugs `fix-plan-initial` /
`fix-plan-rework` · `developing` → `coder-impl` · `design-qa` → `designer-integration-qa` · `testing`
→ `tester-initial` / `tester-reverify` · `failed-impl` → `coder-impl-fix` / `coder-impl-merge-rework`.
Templates live in `[paths] prompts` (default `.mark/prompts/<scenario>.md`), declare `role:` (checked)
and optional `outputs:`, and use `{{placeholders}}`; unknown placeholders are an error.

Moves (`mark set`, `approve`, `reject`) validate, write `status.md` (owner derived from status), then
commit the ticket dir and its gates on main and push. `mark set` additionally refuses:
leaving `review-design`/`review-plan` (human gates) · `testing` for a feature whose design exists and
whose branch touches `[design_qa] paths`, until `design-qa.md` carries `<!-- mark:qa passed -->` ·
`passed` while the ticket branch has commits not on main.

**Human tokens.** `mark approve`, `mark reject` and the opening approval in `mark claim` consume a token
written by the `user-prompt` hook when a person typed the matching command (12 h TTL, ticket id must
match). Models cannot fire UserPromptSubmit, so an orchestrator cannot approve on its own. `mark claim`
without a token creates the ticket unapproved; `/mark:approve <id>` approves the opening.

Review files: each round is `## Round N · <time> · pending <!-- mark:round N pending -->` followed by
`- R-K: …` items; ids run across rounds; approve flips pending rounds to done; text is never edited.

### Merge (v0.7)

`mark merge <id>` (`lib/mark/merge.py`) takes `pending-merge` to `passed`; `mark next` answers
`merge` there. Checks: status, `<!-- mark:verdict PASSED -->` in `verdict.md`, every `merge-after`
ticket `passed`, clean worktree, main checkout on main. Then, in the worktree, merge the latest
main into the branch (conflict: abort), refuse docs grown past `[[doc_budget]]` (v0.10), and
run the **regression contract**: `[merge] regression`,
one shell command, exit 0 = green, empty = skipped (log in `locks/<id>.merge.log`). Main moves
only by `--ff-only` and is pushed (a failed push undoes the local fast-forward), so every
failure before that lands nothing. Then `passed` is committed and pushed, and the remote
branch, worktree and local branch are removed (cleanup problems are notes, not failures).
A failure is recorded as `locks/<id>.merge.result.json`; while it is newer than `status.md`,
`mark next` stops for the human. Concurrent merges serialize on the fast-forward: the loser
fails with `merge.ff_failed` and is run again.

**Merge order (v0.8).** `merge-after: [0012, b0007]` lists tickets that must land first; `passed`
and `superseded` both satisfy it (otherwise folding one ticket into another deadlocks). One check,
`flow.merge_blockers`, serves every entry point: `mark next` (stop, naming the tickets),
`mark merge`, `mark set … passed`, and the status guard for hand edits. Order:
a cycle among unfinished tickets is reported first, with its path (`0001 -> 0002 -> 0001`);
then each unmet entry with its status; an unknown or ambiguous reference blocks and is never
guessed. Order refusals are not recorded as merge failures, so the ticket proceeds by itself
once its dependencies land. Adding entries is free (`mark set --merge-after`, coder-plan
reports them); removing one is a human edit (the status guard refuses it from Claude). The
bash guard refuses `git merge feature/…|bug/…` on main in the main checkout: tickets land only
through `mark merge`.

### General mode (v0.9)

A change that belongs to no ticket (docs, prompts, role files, config) runs through
`/mark:general` (`lib/mark/general.py`). `mark general new` cuts `chore/general-<stamp>` from
the latest main with a worktree at `<worktree dir>/general-<stamp>`; the main thread edits and
commits there; `mark general merge <branch>` reuses the ticket merge steps (`merge.land`:
merge main in, `[merge] regression`, `--ff-only`, push; then `merge.cleanup`). It refuses a
branch without the prefix, a lane without a worktree, uncommitted work, and a lane with no
commits. There is no ticket, status or result file; a failed merge keeps the lane and says why.

"Non-code only" needs no new guard: `[[write_rules]]` already keep code, tests and UI paths
to their roles, and the main thread is `main`. The worktree guard's refusal on the main
checkout points to `mark general new`, and the bash guard refuses `git merge chore/general-…`
on main, so a lane lands only through `mark general merge`.

### Doc budget (v0.10)

Every rule appended after an incident looks harmless; together they make each cold start
slower, because every role loads `CLAUDE.md`, its role file, its prompt and the formats on
every dispatch. A byte budget turns "add one more line" into a trade-off.

`[[doc_budget]]` entries map a `glob` (relative to the checkout, so worktrees match too) to
`max_bytes`; first match wins and `max_bytes = 0` exempts a path from a broader entry. The
section is optional (no entries: no budgets), so `mark_schema` stays 1. Bytes, not lines:
they track context cost and treat both locales the same.

- **budget** guard (`pre-write`, every writer, `lib/mark/budget.py`): refuses a write that
  leaves the file over budget *and* larger than before, so an oversized doc (e.g. after the
  budget was lowered) can always be trimmed. The message gives the size, the limit, how many
  bytes to cut and the three longest lines.
- **merge check** (`merge.land`, tickets and general lanes): after merging main in, files the
  branch added or changed that end over budget and larger than on main fail with
  `merge.budget`, before the regression. Writes through Bash never reach the guard.

What gets a budget: docs whose length follows process complexity (`CLAUDE.md`,
`collaboration.md`, role files, prompts, formats) and one-shot artifacts that are thin by
definition (`fix-plan.md`). Not docs whose length follows delivered work (module notes,
indexes, logs, design or test artifacts, review rounds): a byte wall there can only be passed
by deleting someone else's verified record. The template ships defaults with room above its
own docs in both locales; `tests/test_template.py` checks they fit. Raising a budget is a config
change: roles cannot make it (`.mark/config.toml` is main-thread only), and the orchestrator
leaves it to the human.

### Worktree provisioning (v0.11)

`git worktree add` brings only tracked files: no dependencies, no `.env`, no local config, so
an agent in a fresh worktree cannot run the project's tests. What a worktree needs is project
knowledge, so the engine runs one project command and checks the result; it knows no file names.

`[worktree] setup` is a shell command; `setup_timeout` (seconds, default 300) bounds it. Both are
optional (no command: no setup), so `mark_schema` stays 1. One function, `flow.provision`,
serves both places that create a worktree: `mark dispatch` (`ensure_isolation`) and
`mark general new`. It runs only when the worktree was just created, with the worktree as
cwd, `MARK_MAIN_CHECKOUT` and `MARK_BRANCH` in the environment (a lane can tell itself apart by
the `chore/general-` prefix), and output in `locks/<id>.setup.log`. Ready means exit 0 within
the timeout **and** `git status` clean: whatever setup creates (copies, symlinks, installs)
must be gitignored, or the next dispatch would refuse the worktree as uncommitted work and a
role might commit it. Symlinks are the usual trap: git sees a link as a file, so `name/` does not
ignore it; the message says so.

A failure removes the new worktree (`git worktree remove --force`; the branch and its commits
stay) and refuses the dispatch with the exit code or timeout and the last log lines. So a
worktree that exists was provisioned, an agent never starts in a half-provisioned one, and the
next dispatch simply starts over; `mark general new` also deletes the just-cut branch. A
reused worktree is not set up again: refreshing a long-lived worktree (e.g. a `.env` changed on
main) is left to the project. Merge cleanup needs nothing new: `git worktree remove` ignores
ignored files and removes symlinks without following them. The CLI runs setup, not a tool call,
so no write guard sees it; the orchestrator rules ask for a Bash timeout above `setup_timeout`.

### Project template (v0.5)

`copier.yml` sits at the repo root (Copier only looks there) with `_subdirectory: template/project`.
Answers are recorded in `.mark/.copier-answers.yml`, so upgrades run
`copier update -a .mark/.copier-answers.yml`.

| generated path | what | read by |
|---|---|---|
| `.claude/agents/<role>.md` | role definition: what it owns, rules, self-check, outcomes | the role (system prompt) |
| `.mark/prompts/<scenario>.md` | one dispatch template per entry of `flow.SCENARIOS` (13) | `mark dispatch` |
| `.mark/formats/<artifact>.md` | artifact formats: requirement, bug, design, design-qa, tech-plan, fix-plan, handoff, verdict | the producing and consuming roles |
| `.mark/collaboration.md`, `CLAUDE.md` | workflow for humans; project facts and commands for every role | humans, every role |

Three layers of instructions reach a role, from durable to specific:

1. **Role rules** (engine): `skills/role-rules/SKILL.md`, preloaded into every role agent through
   `skills: [mark:role-rules]` in its frontmatter (`mark rules role` prints it as a fallback). Brief
   trust, worktree anchoring, what roles never do, inline-fix criteria, finish (commit, push the
   ticket branch, clean worktree), report shape. Upgrades with the plugin.
2. **Role file** (template): durable, project-shaped rules for one role, with project paths filled in
   at generation.
3. **Scenario template** (template): why this dispatch happens, done-when, what to read, what to write.
   Only `{{placeholders}}` from `brief.PLACEHOLDERS`; never how to do the work.

**Locales.** Every localized set exists once per locale under a directory whose name renders empty
for the other locale, e.g. `.mark/{% if locale == 'en' %}prompts{% endif %}/`. Files without the
`.jinja` suffix are copied verbatim, which keeps the prompts' `{{placeholders}}` away from Jinja.
Short shared docs (`CLAUDE.md`, `.mark/README.md`, `.mark/collaboration.md`) switch on `locale`
inside the file. English is written first; `zh-CN` is its translation.

**Anchors in artifacts** (language-neutral, so formats can be localized):

| artifact | anchors | used by |
|---|---|---|
| `requirement.md`, `fix-plan.md` | `<!-- mark:ac -->` + `AC-N` | tester, coder-impl self-check |
| `design.md` | `<!-- mark:states -->` + `S-N` | coder-impl, tester, design QA |
| `tech-plan.md` | `<!-- mark:tasks -->` + `T-N`, `SD-N` | coder-impl |
| `handoff.md` | `<!-- mark:ac-table -->`, `<!-- mark:blocked -->` | tester, designer |
| `design-qa.md` | `<!-- mark:qa-round N -->`, `<!-- mark:qa passed\|blocked -->`, `D-N` | engine (`mark set testing`, triggers) |
| `verdict.md` | `<!-- mark:verdict PASSED\|FAILED -->`, `FAIL-N`, `failureType:`, `routeTo:` | engine (triggers), orchestrator |
| all | `<!-- mark:open-questions -->` | blocked outcomes |

`verdict.md` and `design-qa.md` are rewritten per run; ids continue from the previous highest and
are never reused, and only open items carry ids, because the engine hands every `FAIL-N` / `D-N`
it finds to the next role.

**Tests.** `tests/test_template.py` checks the sources (every scenario in every locale, role
declared, placeholders known, anchors present, locales ship the same files) and, when Copier is
available (`MARK_COPIER` or PATH; always in CI), generates a project per locale and renders every
scenario through `brief.render`.

## 5. Distribution and versioning

- This repo is the marketplace (`.claude-plugin/marketplace.json`, name `marksuits`).
- Plugin releases use explicit semver in `plugin.json` plus a git tag `mark--v<version>`.
  Users only receive an update when the version string changes.
- Recommended install scope for teams: `project` (committed `.claude/settings.json`).
- Breaking changes to config or artifact formats bump `mark_schema` and ship a migration note.

## 6. Roadmap

**Phase 1 — core chain (web full-stack profile)**
config loader ✅ · hook plumbing ✅ · ticket claim + `status` CLI ✅ (v0.2) · guards ✅ (v0.3: scope · worktree · ticket · status ·
target · gate · branch · status-commit · dedup/output · git-in-bash) ·
orchestration ✅ (v0.4: `/mark:feature` `/mark:fix` `/mark:approve` `/mark:reject` `/mark:status`,
`mark next|dispatch|set|approve|reject|commit`, human tokens) · project template ✅ (v0.5: role
agents, role rules, 13 prompt templates, artifact formats, en + zh-CN, CI) · example project ✅ (v0.6:
`examples/todo`, sandbox script, feature + bug chains run live, recorded in `examples/README.md`).

**Phase 2 — merge and hygiene**
auto-merge with pluggable regression contract ✅ (v0.7: `mark merge`, `merge-after` checked) · merge-order ✅ (v0.8: cycles, superseded, guards) · general-mode lane ✅ (v0.9: `/mark:general`,
`mark general new|merge`) · doc-budget ✅ (v0.10: `[[doc_budget]]`, pre-write guard, merge check) ·
worktree env provisioning ✅ (v0.11: `[worktree] setup`, dispatch and general lanes).

**Phase 3 — optional plugins**
`mark-web-e2e` (interaction floor, verdict criteria registry) · `mark-design-system`
(token guards) · `mark-ios`.
