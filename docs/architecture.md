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
| **Engine** (`plugins/mark`) | hooks, orchestration skills, CLI (`bin/`), shared agent rules, `lib/mark` | Mark | plugin version bump → `claude plugin update` |
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
- `[paths]`, `[gates]`, `[[write_rules]]` — everything that used to be hardcoded.

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
non-code changes only, on a throwaway branch.

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
| `pre-write` | PreToolUse `Edit\|Write\|MultiEdit\|NotebookEdit` | **scope** (engine rules, then `[[write_rules]]`, first match wins) · **worktree** (roles never write in the main checkout; the main checkout only takes ticket dirs, gates, locks and `main_writable`) · **ticket** (no artifact without `<id>.ticket-approved`) · **status** (main checkout on the main branch, valid fields, legal move) |
| `pre-dispatch` | PreToolUse `Agent\|Task` | **target** (exactly one existing ticket, via `mark:ticket` anchor or ticket path) · **gate** (feature roles need `[gates]`; `<gate>.waived` counts) · **branch** (worktree on `<kind>/<id>`, cut from main unless `base-branch` is declared, pushed to origin) · **status-commit** (ticket state committed and main pushed) · **dedup** (one live agent per ticket+role; creates the lock) |
| `pre-bash` | PreToolUse `Bash` | nobody touches human tokens; subagents never run state-changing `mark` commands, never commit or push on main; nobody checks out a ticket branch in the main checkout |
| `post-dispatch` | PostToolUse `Agent\|Task` | binds the agent id to the lock |
| `post-write` | PostToolUse writes | reminds to commit ticket state on main (feedback only) |
| `user-prompt` | UserPromptSubmit | records a token when a human types `/mark:approve`, `/mark:reject`, `/mark:feature` or `/mark:fix` (never blocks) |
| `subagent-stop` | SubagentStop | required outputs (`[outputs]`, or `mark:outputs` in the prompt) must exist in the ticket dir of some checkout; otherwise the subagent keeps running. Result goes to `.mark/locks/<id>.<role>.result.json` |

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

Each skill injects `mark rules` (the shared orchestrator rulebook, `plugins/mark/rules/orchestrator.md`)
and the live board with `!` commands. `approve` and `reject` set `disable-model-invocation`.

The loop: `mark next <id>` returns one of dispatch · wait · record · stop · done.

- **dispatch**: `mark dispatch <id> --prev "<conclusion>"` creates or reuses the branch, worktree and
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

Merging is manual in this version: at `pending-merge` the human merges and pushes, then
`mark set <id> passed` (Phase 2 automates it).

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
`mark next|dispatch|set|approve|reject|commit`, human tokens) · role agents + prompt templates
(zh-CN, en) · example project walkthrough.

**Phase 2 — merge and hygiene**
auto-merge with pluggable regression contract · merge-order · doc-budget · general-mode lane ·
worktree env provisioning interface.

**Phase 3 — optional plugins**
`mark-web-e2e` (interaction floor, verdict criteria registry) · `mark-design-system`
(token guards) · `mark-ios`.
