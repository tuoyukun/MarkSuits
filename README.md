# MarkSuits

**Mark** is a multi-agent development workflow for [Claude Code](https://code.claude.com),
packaged as one plugin that also writes the project files — a "starter" for teams that want several
specialized agents to build software together without stepping on each other.

> Status: v0.13.0. The engine, the project template (`en` and `zh-CN`) and an example
> project are complete, and both chains (bug and feature) have run end to end on the
> example: see [examples/](examples/). Tickets now merge automatically (`mark merge`), docs/config changes outside any ticket go through `/mark:general`, the docs every role loads stay within byte budgets (`[[doc_budget]]`), and each new worktree is provisioned by the project's `[worktree] setup` before an agent works there. `/mark:init` sets Mark up in a new or existing repository. Not ready for production use yet.

[中文说明](README.zh-CN.md)

## What you get

- **One orchestrator, stateless role agents.** The main thread dispatches one step at a time;
  designer / coder-plan / coder-impl / tester / fix-plan run fresh and talk only through files.
- **Tickets as directories.** Each feature or bug has its own folder of artifacts
  (requirement → design → tech plan → handoff → verdict) and a `status.md`.
- **Human review gates.** `/mark:approve` writes a gate file; agents cannot be dispatched past
  a gate that does not exist.
- **Enforced, not suggested.** Hooks block (exit 2) writes outside a role's scope, skipped gates,
  duplicate dispatch, work on the wrong branch, and docs that outgrow their budget.
- **Isolation.** One branch + git worktree per ticket; code reaches main through a single merge path.

## Layout

```
.claude-plugin/marketplace.json   marketplace catalog (this repo)
plugins/mark/                     the engine plugin (upgradable)
plugins/mark/template/            project files `mark init` writes (en, zh-CN)
examples/todo/, examples/sandbox.py   example project and a script to run it in a sandbox
docs/architecture.md              design
```

A generated project gets:

```
CLAUDE.md                         stack, module boundaries, commands (fill in the TODOs)
.claude/agents/                   designer, coder-plan, coder-impl, tester, fix-plan
.mark/config.toml                 roles, gates, write scopes, paths
.mark/collaboration.md            how humans and agents work together
.mark/prompts/                    one dispatch template per scenario (13)
.mark/formats/                    artifact formats with language-neutral anchors
```

## Install

```bash
claude plugin marketplace add tuoyukun/MarkSuits --scope project
claude plugin install mark@marksuits --scope project
```

Then, inside Claude Code in your repository, run `/mark:init`. It reads the project (new or
existing), checks it is a web full-stack app (the only role pack so far), proposes the
answers (language, directories, test and install commands) and, once you confirm, writes
the project files in one commit on main. An existing `CLAUDE.md` is kept and extended; an
existing `.gitignore` only gains the lines Mark needs. The same step without the agent:
`mark init --dry-run`, then `mark init --<answer> <value>...`.

Claude Code does not update plugins from this marketplace on its own. Turn that on once in
`/plugin` > Marketplaces > marksuits > Enable auto-update, or update by hand with
`claude plugin update mark@marksuits` and restart. `mark status` and `mark next` look up the
published version once a day and say when a newer one is out (`MARK_NO_UPDATE_CHECK=1` turns
that off). They also say when the project files are older than the plugin; `/mark:upgrade` merges the new template into them
(3-way, keeping your edits) on a general lane, and lands it only when you say so.

## Development

```bash
python3 -m unittest discover -s tests -t .
python3 tools/sync_example.py               # after a template change
claude plugin validate .
claude --plugin-dir ./plugins/mark
git config core.hooksPath tools/git-hooks   # sensitive-data pre-commit check
```

## License

[MIT](LICENSE)
