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
| **Engine** (`plugins/mark`) | hooks, orchestration skills, CLI (`bin/`), shared role rules (`skills/role-rules`), `lib/mark`, and the built-ins: role agents (`agents/`), dispatch prompts, artifact formats and the collaboration guide (`defaults/<locale>/`), workflow config defaults (`config.py`) | Mark | plugin version bump → auto-update or `claude plugin update` |
| **Scaffold** (`plugins/mark/template/`) | `CLAUDE.md`, `.mark/README.md`, `.mark/config.toml` (project facts only), `.gitignore` | the project, after `mark init` | `mark upgrade` / `/mark:upgrade` (3-way merge on a general lane) |
| **Project content** | module boundaries, contracts, write-scope exceptions, domain scripts, and any override of a built-in | the project | — |

Up to v0.16 the role agents, prompts and formats were part of the scaffold. The next section
says why they moved.

### Built-ins and overrides (v0.17)

**Problem.** Claude Code auto-update (once the user turns it on) replaces the engine, but
the role agents, prompts and formats were copied into the project by `mark init`, so most
improvements never reach a project unless someone runs `/mark:upgrade`. The copied
`.claude/agents/` also does not exist when the init session starts, so that session cannot
dispatch any role.

**Rule.** The plugin ships every generic file; the project holds only its facts and the
files it deliberately changed. For each file the project copy wins if it exists, else the
built-in is used. Auto-update then upgrades everything the project did not override.

| What | Built-in (plugin) | Project override | Resolved by |
|---|---|---|---|
| Role agents | `plugins/mark/agents/<role>.md`, loaded as `mark:<role>` | `.claude/agents/<role>.md` | `mark dispatch` prints `subagent_type: <role>` when the project file exists, else `mark:<role>` |
| Dispatch prompts | `plugins/mark/defaults/<locale>/prompts/<scenario>.md` | `.mark/prompts/<scenario>.md` | `brief.load_template` |
| Artifact formats | `plugins/mark/defaults/<locale>/formats/<name>.md` | `.mark/formats/<name>.md` | `mark format <name>` prints the effective one; agents and prompts point there instead of a path |
| Collaboration guide | `plugins/mark/defaults/<locale>/collaboration.md` | none | `mark rules collaboration` |
| Workflow config: `roles`, `[gates]`, `[outputs]`, artifact write rules (`requirement.md` → main, `design.md` → designer …) and the shared-doc rules (`CLAUDE.md`, `**/CONTEXT.md`, `docs/adr/**`) | engine defaults in `config.py` | the same keys in `.mark/config.toml` | `load_config` fills every missing key from the defaults; inside `[gates]` and `[outputs]` per role (v0.24: a project key replaces only that role's default, `""` / `[]` turns it off) |

`mark init` writes only what is about this project: `.mark/config.toml` with `[project]`,
`[paths]`, `[merge]`, `[worktree]`, `[design_qa]`, `[[doc_budget]]` and the path write rules
(`frontend/**` → coder-impl …), plus `CLAUDE.md` and `.gitignore`. No `.claude/agents/`, so no
restart. A config key added in a later version gets its engine default, so new knobs never
need an upgrade.

**Hooks are unaffected.** Hooks in a plugin's `hooks/hooks.json` apply inside every subagent,
plugin subagents included ("Hooks from settings files, managed policy settings, and plugins
all apply inside subagents"). Only the per-agent `hooks:` frontmatter is ignored for plugin
agents, and Mark has never used it: all guards live in `hooks.json`. Hook payloads carry
`agent_type: mark:<role>`, which `hookio.normalize_agent_type` already reduces to `<role>`.
The first implementation step checks this live: a plugin designer writing outside its scope
must be blocked with exit 2.

**Agents carry no project facts.** Today they template only `project_name`, `ui_dir` and
`tests_dir`; the dispatch brief names the directories instead, and `CLAUDE.md` holds the
rest. A plugin cannot localize an agent per project, so built-in agents are written in
English; artifacts and replies stay in the project's `locale` (already a role rule), and
prompts and formats remain per locale.

**Upgrade shrinks to the scaffold.** `/mark:upgrade` still 3-way merges the few scaffold files.
An override belongs to the project: it does not follow later changes to the built-in it
replaced. Migration from v0.16 and earlier: one `/mark:upgrade` deletes every copied agent,
prompt, format and collaboration guide that still equals its `.base` (never edited), and the
3-way merge of `config.toml` drops the workflow keys the project never changed. Edited copies
stay and are reported as overrides. Old configs keep working unchanged in the meantime (their
keys simply override), so `mark_schema` stays 1.

## 3. Engine ↔ project contract

`.mark/config.toml` is the only interface:

- `mark_schema` — integer; the engine refuses unknown versions (exit 2 with a migration hint).
- `locale` — `zh-CN` | `en`; selects hook message language and tells the orchestrator which
  language to use with humans and in artifacts.
- `[paths]`, `[gates]`, `[[write_rules]]`, `[[doc_budget]]`, `[worktree]` — everything that used to be hardcoded.

Hooks locate the project by walking up from the payload `cwd` to `.mark/config.toml`; no
config means "not a Mark project" → exit 0. This matters because plugin hooks fire in every
session where the plugin is enabled. A config that does not load (bad TOML, unknown schema)
blocks dispatches, subagents and writes, but never the human's prompts, the main thread's
Bash, or the main thread's edit of `.mark/config.toml` itself (v0.24): otherwise one typo
locks the human out of Claude in that repository.

Hooks recognize artifact sections by anchors (`<!-- mark:ac-table -->`), never by heading
text, so templates can be localized freely.

## 4. Ticket lifecycle (feature chain)

| status | action | role | gate required |
|---|---|---|---|
| drafting | the orchestrator writes `requirement.md` with the human; `mark set … review-requirement` refuses it without an `AC-N` under `<!-- mark:ac -->` or with open questions other than `none` | — | — |
| review-requirement | stop, wait for human; approve → `designing` (`planning` without a designer), reject → `drafting` | — | — |
| designing | design | designer | requirement-approved |
| review-design | stop, wait for human | — | — |
| planning | tech plan | coder-plan | requirement-approved, design-approved |
| review-plan | stop, wait for human | — | — |
| developing | implement | coder-impl | plan-approved |
| design-qa | integration design check (UI changes only); after 2 blocked rounds `mark set` refuses `failed-impl`, the human decides via `blocked-spec` (`/mark:approve <id>` back to design, or `… developing`) | designer | — |
| testing | verify | tester | plan-approved |
| pending-merge | automated merge (regression → ff-only → push); owner `orchestrator`, a failed merge stops for the human | — | — |
| passed | done | — | — |

The requirement review (v0.33) checks the input as the other two check outputs. Before the claim the
orchestrator sizes the request: a large one (or `/mark:feature --discuss`) is discussed one topic
per round — scope, technical choices, architecture — and every agreement lands in the requirement
as a `DEC-N` under `<!-- mark:decisions -->`, which designer and coder-plan must follow (changing one
is `blocked-unclear`). `mark claim` marks new features `requirement-gate: yes`; the dispatch gate
guard requires `<id>.requirement-approved` for every role of such a ticket. Tickets opened before
v0.33 lack the field and skip that gate, so no migration is needed.

A failure only the UI directory can fix (the tester's `design-flaw`, or coder-impl finding one
while `developing` / `failed-impl`) goes to `blocked-spec`, and the human sends it back to the
designer (`designer-rework`); `mark next` spells out the failureType → status mapping when it asks
for the tester's outcome (v0.28.2).
When such a rework (`blocked-spec` → `designing` with the plan already approved) changes only the
UI directory and ticket artifacts, and leaves `design.md`'s props and integration contracts
(`<!-- mark:props-contract -->`, `<!-- mark:integration-contract -->`) word for word, approving
the design review keeps the approved plan: the ticket goes to `design-qa` (or `testing`) instead of
`planning`. `mark approve` records the branch head as `rework-base` in `status.md` when it sends
the ticket to design and drops it at the review (`flow.ui_only_rework`; v0.31). A design without
the anchors, or anything outside the UI, redoes the plan as before.

A plan may `extend` only end-to-end tests main already has; one an earlier round of the same
ticket added is `new` (`guards.write.plan_extend_guard`, v0.31), so `mark merge` no longer finds
it unplanned after the whole chain has run.

A profile without a UI (`profile = "service"`, v0.25) has no designer (`config.NO_UI_PROFILES`
drops it from the default `roles`, and with it the `design-approved` gate): a new feature starts
at `planning` (`states.initial`), and no move may enter a status whose role the project lacks
(`flow.no_role`; `blocked-spec` then goes back to `planning`).

Bug chain: fix-plan → coder-impl → tester, no review gates. When part of the fix is in the UI
directory, fix-plan tags those items `[ui]` and reports `designing`: the designer fixes the
components (`designer-bugfix`: no design, no preview, no required output), then goes to
`developing`, or straight to `testing` when `handoff.md` exists and nothing else is left. A UI
failure found later goes through `blocked-spec` and the human, as on features (v0.29). General mode: no subagents,
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
- Legal moves live in `lib/mark/states.py` (`TRANSITIONS`), used by `mark set`, `approve`, `reject` and `merge` (the only writers of `status.md`).

### Guards (v0.3)

All hooks go through one entry, `hooks/mark_hook.py <group>`; guards are pure functions in
`lib/mark/guards/` returning a message or None. A crashing guard fails open and says so.

| group | event / matcher | guards, in order |
|---|---|---|
| `pre-write` | PreToolUse `Edit\|Write\|MultiEdit\|NotebookEdit` | **scope** (engine rules, then `[[write_rules]]`, first match wins; a path no rule assigns is the main thread's, except a role's working files in a ticket dir — v0.19; CLI-only files are nobody's, see below) · **worktree** (roles never write in the main checkout; the main checkout only takes ticket dirs, gates, locks and `main_writable`) · **ticket** (no artifact without `<id>.ticket-approved`) · **budget** (`[[doc_budget]]`, see Doc budget) · **e2e** / **journey** (tester writes, v0.22–0.23) |
| `pre-dispatch` | PreToolUse `Agent\|Task` | **staffed** (a built-in role the project lacks, e.g. the designer in `service`, is refused, v0.30) · **target** (exactly one existing ticket, via `mark:ticket` anchor or ticket path) · **status** (the role is the one the ticket's status names; gates are never revoked, so a gate alone would start coder-impl while a reworked plan waits for review, v0.30) · **gate** (feature roles need `[gates]`, plus `requirement-approved` when the ticket says `requirement-gate: yes`, v0.33; `<gate>.waived` counts) · **branch** (worktree on `<kind>/<id>`, cut from main unless `base-branch` is declared, pushed to origin) · **status-commit** (ticket state committed and main pushed) · **dedup** (one live agent per ticket+role; creates the lock) |
| `pre-bash` | PreToolUse `Bash` | nobody touches human tokens; subagents never run state-changing `mark` commands, never commit on main or push to it (from any branch, e.g. `HEAD:main` in a worktree, v0.30); nobody checks out a ticket branch in the main checkout; nobody force-removes a worktree or branch holding uncommitted or unpushed work; subagent shell writes (`>`, `>>`, `tee`, `touch`, `sed`/`perl`/`ruby -i`, `cp`, `mv`) follow the scope and worktree rules, and the tester writes test code under the tests directory with Edit/Write only, so the end-to-end rules see it; the main thread's never reach a CLI-only file or a role's artifact in a ticket dir (`verdict.md`, `design-qa.md`… carry anchors the engine trusts, v0.30) (commands split at `&&`, `||`, `;`, `|` and newlines outside quotes; `$VAR` and `cd` are followed through the command's own assignments and the environment; unclear or quoted targets pass) |
| `post-dispatch` | PostToolUse `Agent\|Task` | binds the agent id to the lock; a foreground agent (`status: completed`) whose stop could not be matched is settled here instead, so no finished agent leaves a bound lock |
| `dispatch-failed` | PostToolUseFailure `Agent\|Task` | the agent never started: drops its unbound lock and tells Claude why (an unknown agent type means the session predates that agent: restart) |
| `post-write` | PostToolUse writes | reminds to commit ticket state on main (feedback only) |
| `user-prompt` | UserPromptSubmit | records a token when a human types `/mark:approve`, `/mark:reject`, `/mark:feature` or `/mark:fix` (never blocks) |
| `subagent-stop` | SubagentStop | finds the lock by agent id, else by the `mark:ticket` anchor in the agent's own transcript (`agent_transcript_path`), else the only unbound lock of the role. Required outputs (`[outputs]`, or `mark:outputs` in the prompt) must exist in the ticket dir of some checkout and at least one must have changed since the dispatch (a rework round finds last round's files); otherwise the subagent keeps running. Result goes to `.mark/locks/<id>.<role>.result.json`, with the agent's final report (`conclusion`, the default `--prev` of the next dispatch) |

Engine-fixed rules (no config can loosen them): `.claude/**`, `.mark/config.toml` and locks are
main-thread only. Gates, ticket `status.md`, `review-*.md`, `locks/human/**` and `.mark/.base/**`
are **CLI-only** (v0.24): no tool call writes them, the main thread's included, because they record
human decisions and ticket state. The `mark` CLI writes them as a Bash child process, which no hook
sees, so this works the same in the terminal and in Desktop sessions. Before v0.24 the main thread
could write a gate itself and approve its own work; the token check guarded only `mark approve`.
`mark general merge` also refuses a lane that changes any of them except `.base` (lanes carry no
decisions; this catches writes the Bash parser cannot see). Locks bound to a live agent are never
reclaimed by age; a human releases a dead one with `mark unlock <id> <role>`.
Set `MARK_DEBUG_LOG=<file>` to record raw hook payloads.

### Orchestration (v0.4)

The orchestrator is the main thread, driven by plugin skills. The skills stay thin: every
decision that can be computed is computed by the `mark` CLI and tested.

| skill | does | continues until |
|---|---|---|
| `/mark:feature <id \| [--discuss] text>` | new: size it, discuss with the human (large: scope, technical choices, architecture), `mark claim`, `requirement.md`, `mark set … review-requirement`; existing: one step | `review-requirement` / one step |
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
- **wait**: a dispatch lock exists for the ticket (an unbound lock older than 90 s is a dispatch
  that never started and does not count).
- **record**: a SubagentStop result newer than `status.md` exists; the orchestrator runs
  `mark set <id> <status>`, choosing among the legal moves listed.

Scenario (template) selection, from status plus artifacts: `designing` → `designer-initial`, or
`designer-review-rework` (pending rounds in `review-design.md`), or `designer-rework` (after a
verdict or design QA), bugs `designer-bugfix` · `planning` → `coder-plan` / `coder-plan-rework`, bugs `fix-plan-initial` /
`fix-plan-rework` · `developing` → `coder-impl` · `design-qa` → `designer-integration-qa` · `testing`
→ `tester-initial` / `tester-reverify` · `failed-impl` → `coder-impl-fix` / `coder-impl-merge-rework`.
Templates are built in (`defaults/<locale>/prompts/<scenario>.md`; a project overrides one in
`[paths] prompts`, default `.mark/prompts/`), declare `role:` (checked)
and optional `outputs:`, and use `{{placeholders}}`; unknown placeholders are an error.

Moves (`mark set`, `approve`, `reject`) validate, write `status.md` (owner derived from status), then
commit the ticket dir and its gates on main and push. `mark set` additionally refuses:
leaving a status that waits on the human (`review-*`, `blocked-*`; v0.24 also `pending-merge`, which
only `mark merge` takes to `passed`), except to `superseded` · `testing` from `design-qa` unless
`design-qa.md` carries `<!-- mark:qa passed -->` · `testing` for a feature whose design exists and
whose branch touches `[design_qa] paths`, until it does · `passed` while the ticket branch has commits
not on main · `pending-merge` from `testing` without a tester run that finished since (a PASSED verdict from an earlier round is on disk after a merge rework, v0.30). A blocked ticket moves on only through `mark approve`: the default way back
(`blocked-spec` → `designing`, `blocked-plan` → `planning`), or `--to <status>` among its legal moves
when the human typed that status (`/mark:approve 0012 developing`); `blocked-unclear` always needs
one. If the human named a status, `mark approve` without `--to` refuses instead of taking the default (v0.30). So gates are never revoked yet never reused unseen: every way back to work passes the human.

**Human tokens.** `mark approve`, `mark reject` and the opening approval in `mark claim` consume a token
written by the `user-prompt` hook when a person typed the matching command. An approve or reject token
must name the ticket (12 h TTL); it also records the words after the id, which `approve --to` must
match. `mark claim` takes any `/mark:feature` / `/mark:fix` token, since the number does not exist yet,
so those live 2 h. Models cannot fire UserPromptSubmit, and the gates the tokens lead to are CLI-only,
so an orchestrator cannot approve on its own. `mark claim` without a token creates the ticket
unapproved; `/mark:approve <id>` approves the opening.

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
branch, worktree and local branch are removed (cleanup problems are notes, not failures). Once
main has moved, cleanup forces the worktree out (files the regression left behind would otherwise
keep it) and runs even if recording `passed` fails (v0.32). `mark set <id> superseded` removes
the ticket's worktree, local and remote branch the same way (`merge.discard`, v0.32) and prints
the branch tip with the `git branch` command that brings it back.
A failure is recorded as `locks/<id>.merge.result.json`; while it is newer than `status.md`,
`mark next` stops for the human. Concurrent merges serialize on the fast-forward: the loser
fails with `merge.ff_failed` and is run again.

**Merge order (v0.8).** `merge-after: [0012, b0007]` lists tickets that must land first; `passed`
and `superseded` both satisfy it (otherwise folding one ticket into another deadlocks). One check,
`flow.merge_blockers`, serves every entry point: `mark next` (stop, naming the tickets),
`mark merge` and `mark set … passed` (no tool call writes `status.md`). Order:
a cycle among unfinished tickets is reported first, with its path (`0001 -> 0002 -> 0001`);
then each unmet entry with its status; an unknown or ambiguous reference blocks and is never
guessed. Order refusals are not recorded as merge failures, so the ticket proceeds by itself
once its dependencies land. Adding entries is free (`mark set --merge-after`, coder-plan
reports them); removing one is a human edit in an editor (no tool call writes `status.md`). The
bash guard refuses `git merge feature/…|bug/…` on main in the main checkout: tickets land only
through `mark merge`.

**Shipped entry points (v0.21).** An empty `[merge] regression` used to be the norm after
`mark init` of a new project: no tests existed yet, and the reminder to set it lived in the
init skill, which nobody reads again when the skeleton lands, so tickets merged on the
tester's word alone. The template now ships `scripts/` at the root and its merge check is
`bash scripts/selftest.sh && bash scripts/regression.sh` (a project can still empty
`[merge] regression`, and then merges on the tester's verdict alone). The scripts never change per
ticket: `scripts/each.sh` runs one entry point inside each module, with the checkout's `.env`
exported (its v0.20 ports). `selftest.sh` (frontend, backend) is the white-box self-test
coder-impl owns; `regression.sh` (test directory) is the black-box suite the tester owns;
`start.sh` / `stop.sh` are optional, for modules that run a server. A module directory that
does not exist yet is skipped, so before the skeleton the check is green and says nothing
ran; a module that exists without its required entry fails, so a check never passes by
running nothing. The skeleton's plan creates the entries, so its own merge, which runs in the
ticket's worktree, already runs the real suites. A new test joins the check by living in its
module. `scripts/` has no write rule (main thread only) and updates through `/mark:upgrade`;
an existing project writes its module entries in the init or upgrade lane before it lands.
The `regression_cmd` answer is gone; a recorded one is ignored.

**Black-box end-to-end tests (v0.22).** The tester's tests drive the app as a user; what only
code can reach is a unit test in its module (`needs-unit-test`). `guards.write.e2e_guard`
(rules in `lib/mark/e2e.py`) judges what a tester write adds under `[paths] tests`, never the
lines and test blocks already there, so a legacy suite is not held to rules it predates. Any
framework: no import of production code (a relative path out of the test directory, or a
module directory by name) and no reading its source (`readFileSync`, `open`, `grep` on a module
path); starting the app (`python3 ../backend/server.py`) is fine. `[tests] profile =
"playwright"` adds rules for each new or changed top-level `test(...)` block: a user action
(click, fill, press, check, select, drag, keyboard, mouse...), an assertion after it, no
skip / fixme, no `waitForTimeout` over 200 ms, no `route` / `fulfill` / `dispatchEvent`, no
page state set inside `evaluate`. A local helper whose body acts (or asserts), directly or
through another helper, counts as acting (or asserting); helpers are read from the spec and
the files it imports relatively, since suites often keep gestures in `helpers/`.
Comments and string contents are blanked before matching. Measured on a 602-block legacy
Playwright suite: no false positives besides real network stubs. `[tests] profile =
"maestro"` (v0.27) reads Maestro flows instead: a flow file (`*.yaml`, not under `subflows/`,
not `config.yaml`) is one test, titled by its `name:` or its file name; each new or changed
flow needs a user action (`tapOn`, `inputText`, `swipe`...) and an assertion after it, where
a `runFlow` counts as what the flow it runs does (`e2e.flow_problems`), and no `runFlow` /
`runScript` / `file:` path may leave the test directory. Journeys work as below.

**Extend before adding (v0.23).** Suites grow because the cheapest move for a tester is one
more test per criterion, and nothing pushes back; a cap on the count does not work either,
since how many journeys a product needs differs by orders of magnitude between projects. So
the decision moves to where a human already looks: the plan. `tech-plan.md` and `fix-plan.md`
carry "End-to-end coverage" (`<!-- mark:e2e-plan -->`), one row per criterion: `extend
<existing title>` with the steps to add, `new <title>` with the closest existing test and why
it cannot be extended, or `unit`. The planner reads `<tests>/JOURNEYS.md`
(`<!-- mark:journeys -->`, tester-owned: every test's title, file, path through the app and
covers), and the human sees each new journey at plan review; a bug has no review, but the
reason is on record. No separate test review: the human could not judge one. Enforcement,
with `[tests] profile = "playwright"` or `"maestro"`: the tester's write may add only tests titled as the
plan's `new` rows (`guards.write.journey_guard`; a title already present in another spec is a
move, not an addition; changing a test keeps its title); `mark merge` re-checks that the
branch adds no test beyond them against the merged base (`merge._journeys`; shell writes
cannot slip past) and that `JOURNEYS.md` lists exactly the tests there are. General lanes
have no plan and get only the index check. `mark journeys [<checkout>]` prints the rows to
add (file and `covers:` filled in) and to drop, which is also how an existing suite gets its
first index in the init or upgrade lane.

### General mode (v0.9)

A change that belongs to no ticket (docs, prompts, role files, config) runs through
`/mark:general` (`lib/mark/general.py`). `mark general new` cuts `chore/general-<stamp>` from
the latest main with a worktree at `<worktree dir>/general-<stamp>`; the main thread edits and
commits there; `mark general merge <branch>` reuses the ticket merge steps (`merge.land`:
merge main in, `[merge] regression`, `--ff-only`, push; then `merge.cleanup`, forced as for a ticket). It refuses a
branch without the prefix, a lane without a worktree, uncommitted work, and a lane with no
commits. There is no ticket, status or result file; a failed merge keeps the lane and says why.
`mark general drop <branch>` (v0.12) removes a lane that will not land (worktree, local and
remote branch, through `merge.cleanup`); it refuses while the lane holds uncommitted files or
commits not on main, unless `--force`, which the rules reserve for a human's explicit "discard".

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

What gets a budget: docs whose length follows process complexity (`CLAUDE.md`, role
files, prompts, formats: the project's overrides by glob, the built-ins by test) and one-shot artifacts that are thin by
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
main) is left to the project. Merge cleanup needs nothing new: it forces `git worktree remove`
(v0.32), which removes symlinks without following them. The CLI runs setup, not a tool call,
so no write guard sees it; the orchestrator rules ask for a Bash timeout above `setup_timeout`.

**Ports (v0.20).** A worktree is a separate checkout, not a separate network: two tickets that
start the dev server on its default port collide, and so does a ticket with any other program
on the machine. `[worktree] ports` maps env var names to the first port of a range
(`{ FRONTEND_PORT = 5200, BACKEND_PORT = 8200 }`); `port_slots` (default 100) is the range
length. After setup succeeds, `provision` (`lib/mark/ports.py`) gives the new worktree one slot
and writes `NAME=base+slot` into its `.env`, after setup so a setup that copies the main
`.env` does not overwrite it. The `.env` files of the other worktrees are the ledger (no second
record to drift; removing a worktree frees its slot), read and written under a `flock` on
`locks/ports.lock` so concurrent dispatches never share a slot. A slot is also skipped while
any of its ports accepts a connection on `localhost`, IPv4 or IPv6, which is how a server from
another repository is caught. The search starts at `crc32(worktree name) % port_slots`. No free
slot, or a `.env` git sees, removes the worktree like a failed setup. Each dispatch brief lists
the worktree's ports, since an agent that assumes the default port tests someone else's
branch. Optional (empty: nothing happens), so `mark_schema` stays 1; worktrees created before
it have no ports until they are recreated.

### Project template (v0.5; shipped in the plugin since v0.13)

The template lives in the plugin, `plugins/mark/template/`, and `mark init` (`lib/mark/scaffold.py`,
driven by the `/mark:init` skill) writes it into a project. There is no external generator: one
plugin install is the whole setup.

- **Answers** (`scaffold.keys(profile)`): project name, locale, profile, main branch, the profile's
  module directories (`scaffold.PROFILES`: `web-fullstack` frontend / backend / UI / tests,
  `web-frontend` frontend / UI / tests, `service` service / tests, `mobile-fullstack` app /
  backend / UI / tests, `mobile` app / UI / tests), worktree setup command. `mark init
  --<answer> <value>`; defaults fill the rest; `--dry-run` shows the plan and writes nothing.
- **Checks before writing**: a git repository (an empty directory is `git init`ed), on the main
  branch, clean tree, git identity set, not already a Mark project, and no template file already
  present except `CLAUDE.md` (kept as is: the project owns it) and `.gitignore` (gains the missing
  lines). Anything else is a conflict and nothing is written.
- **Result**: one commit on main, pushed when there is an `origin`. `.mark/template.toml` records
  the plugin version and the answers; `.mark/.base/<path>.base` keeps each written file exactly as
  written, the common ancestor for a later 3-way upgrade (the `.base` suffix keeps Claude Code and
  git from reading the copies as a live `CLAUDE.md`, agent or `.gitignore`). Both are write-protected
  by built-in rules.
- **The skill** decides what the command cannot: new vs existing project, which profile fits
  (none fits: it stops with nothing written), the answers
  (proposed from the manifests and CI config, confirmed by the human), and afterwards fills in
  `CLAUDE.md` in a general lane.

| path | what | read by |
|---|---|---|
| `agents/<role>.md` (built-in) | role definition: what it owns, rules, self-check, outcomes | the role (system prompt) |
| `defaults/<locale>/prompts/<scenario>.md` (built-in) | one dispatch template per entry of `flow.SCENARIOS` (13) | `mark dispatch` |
| `defaults/<locale>/formats/<artifact>.md` (built-in) | artifact formats: requirement, bug, design, design-qa, tech-plan, fix-plan, handoff, verdict | the producing and consuming roles (`mark format <name>`) |
| `defaults/<locale>/collaboration.md` (built-in) | workflow for humans | humans (`mark rules collaboration`) |
| `CLAUDE.md` (generated) | project facts and commands | every role |

Three layers of instructions reach a role, from durable to specific:

1. **Role rules** (engine): `skills/role-rules/SKILL.md`, preloaded into every role agent through
   `skills: [mark:role-rules]` in its frontmatter (`mark rules role` prints it as a fallback). Brief
   trust, worktree anchoring, what roles never do, inline-fix criteria, finish (commit, push the
   ticket branch, clean worktree), report shape. Upgrades with the plugin.
2. **Role file** (built-in agent, English): durable rules for one role; project paths come from
   `[paths]` in the config and `CLAUDE.md`, not from the file.
3. **Scenario template** (built-in, per locale): why this dispatch happens, done-when, what to read, what to write.
   Only `{{placeholders}}` from `brief.PLACEHOLDERS`; never how to do the work.

**Locales and profiles.** `template/common/` holds what is the same in every locale and profile
(`.gitignore`, `scripts/`, whose module lists come from the derived `{{ modules }}`);
`template/<locale>/` holds `.mark/README.md`; `template/profiles/<profile>/common/` the
profile's `.mark/config.toml` and `.../<locale>/` its `CLAUDE.md`. Built-in
prompts, formats and the collaboration guide have one full set per locale under `defaults/`;
built-in agents are English only (a plugin cannot localize them per project), and roles write
artifacts in the project's locale. A `*.tmpl` file has
each `{{ answer }}` filled in (TOML-escaped in `.toml` files) and loses the suffix; an unknown
name is an error. Other files are copied verbatim, which keeps the prompts' `{{placeholders}}` for
`mark dispatch`. English is written first; `zh-CN` is its translation.

**Anchors in artifacts** (language-neutral, so formats can be localized):

| artifact | anchors | used by |
|---|---|---|
| `requirement.md`, `fix-plan.md` | `<!-- mark:ac -->` + `AC-N` | tester, coder-impl self-check; `mark set … review-requirement` |
| `requirement.md` | `<!-- mark:open-questions -->` (only `none` / `无`), `<!-- mark:decisions -->` + `DEC-N` | `mark set … review-requirement`; designer, coder-plan |
| `design.md` | `<!-- mark:states -->` + `S-N` | coder-impl, tester, design QA |
| `preview.html` | none: the designer's preview built into one offline file (gitignored); `mark set`/`mark next` give its path at `review-design` | human design review |
| `tech-plan.md` | `<!-- mark:tasks -->` + `T-N`, `SD-N` | coder-impl |
| `handoff.md` | `<!-- mark:ac-table -->`, `<!-- mark:blocked -->` | tester, designer |
| `design-qa.md` | `<!-- mark:qa-round N -->`, `<!-- mark:qa passed\|blocked -->`, `D-N` | engine (`mark set testing`, triggers) |
| `verdict.md` | `<!-- mark:verdict PASSED\|FAILED -->`, `FAIL-N`, `failureType:`, `routeTo:` | engine (triggers), orchestrator |
| all | `<!-- mark:open-questions -->` | blocked outcomes |

`verdict.md` and `design-qa.md` are rewritten per run; ids continue from the previous highest and
are never reused, and only open items carry ids, because the engine hands every `FAIL-N` / `D-N`
it finds to the next role.

**Upgrade** (v0.14, `lib/mark/upgrade.py`, driven by `/mark:upgrade`). `mark status` and `mark next`
print a notice when `.mark/template.toml` records an older version than the plugin. `mark upgrade`
re-renders the template with the recorded answers (keys added since get their defaults) and, per
file, merges the template's change (base → new) into the project's file with `git merge-file`:
unchanged template → nothing; untouched project file → replaced; both changed → merged, or left
with conflict markers. A file the project deleted stays deleted; a file the template dropped is
removed only if the project never changed it. A pre-existing `CLAUDE.md` (no base) is never
touched; a pre-existing `.gitignore` only gains missing lines. Everything, including the new
`.base` copies and record, is one commit on a general lane cut from main; main changes only
when the human lands it with `mark general merge`, which refuses lines with conflict markers.
`--dry-run` prints the same rows from the main checkout and writes nothing.

**Tests.** `tests/test_template.py` checks the sources (every scenario in every locale, role
declared, placeholders known, anchors present, locales ship the same files), generates a project
per locale with `mark init` and renders every scenario through `brief.render`. `tests/test_scaffold.py`
covers init's checks and the existing-project cases; `tests/test_upgrade.py` covers the upgrade.

## 5. Distribution and versioning

- This repo is the marketplace (`.claude-plugin/marketplace.json`, name `marksuits`).
- Plugin releases use explicit semver in `plugin.json` plus a git tag `mark--v<version>`.
  Users only receive an update when the version string changes.
- Recommended install scope for teams: `project` (committed `.claude/settings.json`).
- Breaking changes to config or artifact formats bump `mark_schema` and ship a migration note.
- Migration note (v0.13): projects generated with Copier have `.mark/.copier-answers.yml`. Replace
  it with `.mark/template.toml` (same answers, TOML, plus `version`) and add `.mark/.base/` copies
  (`tools/sync_example.py` shows how); only the bundled example existed at the time.

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
`mark general new|merge`; `drop` in v0.12) · doc-budget ✅ (v0.10: `[[doc_budget]]`, pre-write guard, merge check) ·
worktree env provisioning ✅ (v0.11: `[worktree] setup`, dispatch and general lanes).

**Setup** (between Phase 2 and 3)
template in the plugin + `mark init` / `/mark:init` ✅ (v0.13: new and existing repositories,
no Copier) · `mark upgrade` / `/mark:upgrade` ✅ (v0.14: 3-way merge against `.mark/.base/`, in a
general lane; stale notice in `status` / `next`).
Versions stay below 1.0 until real end users have run Mark.

**Write scopes default to closed** (v0.19): a role writes only paths a rule assigns to it.
Before, unmatched paths were open to every role, which let a skeleton ticket put a shared
package manifest and tool config at the repository root. Migration: list every directory a
role works in under `[[write_rules]]`; the CLAUDE.md template gained a Layout section
(`mark upgrade` brings it in), and `/mark:init` agrees the layout with the human.

**Phase 3 — profiles** (re-planned 2026-10-22: one plugin, a profile per kind of project,
instead of optional plugins; the interaction floor of the planned `mark-web-e2e` landed in
v0.22–v0.23, its verdict criteria registry and `mark-design-system` token guards were dropped)
`service` ✅ (v0.25: designer optional, `[paths]` modules not hard-coded, `examples/notes`) ·
`web-frontend` ✅ (v0.26: web-fullstack without the backend; third-party APIs are faked from the
test directory, never stubbed in the browser; `examples/expenses`) · `mobile-fullstack` ✅
(v0.27: a mobile app and its backend; `[tests] profile = "maestro"`; the designer's preview is
the web build of the real components, or simulator screenshots when the stack has none;
`examples/habits`, Expo + Maestro) · `mobile` ✅ (v0.28: the app alone; data on the device, each
end-to-end run starts from empty app data; `examples/tally`, Expo + AsyncStorage + Maestro). `cli` (CLIs and libraries) was
dropped.
