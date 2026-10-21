# MarkSuits

**Mark** is a multi-agent development workflow for [Claude Code](https://code.claude.com),
packaged as a plugin plus a project template — a "starter" for teams that want several
specialized agents to build software together without stepping on each other.

> Status: v0.8.0. The engine, the project template (`en` and `zh-CN`) and an example
> project are complete, and both chains (bug and feature) have run end to end on the
> example: see [examples/](examples/). Tickets now merge automatically (`mark merge`). Not ready for production use yet.

[中文说明](README.zh-CN.md)

## What you get

- **One orchestrator, stateless role agents.** The main thread dispatches one step at a time;
  designer / coder-plan / coder-impl / tester / fix-plan run fresh and talk only through files.
- **Tickets as directories.** Each feature or bug has its own folder of artifacts
  (requirement → design → tech plan → handoff → verdict) and a `status.md`.
- **Human review gates.** `/mark:approve` writes a gate file; agents cannot be dispatched past
  a gate that does not exist.
- **Enforced, not suggested.** Hooks block (exit 2) writes outside a role's scope, skipped gates,
  duplicate dispatch, and work on the wrong branch.
- **Isolation.** One branch + git worktree per ticket; code reaches main through a single merge path.

## Layout

```
.claude-plugin/marketplace.json   marketplace catalog (this repo)
plugins/mark/                     the engine plugin (upgradable)
copier.yml, template/project/     Copier template for a Mark project (generated once)
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

## Install (once released)

```bash
# 1. Generate project files (roles, prompts, .mark/config.toml)
copier copy gh:<owner>/MarkSuits . --vcs-ref <tag>     # asks for locale: en | zh-CN

# 2. Enable the engine for everyone in the repo
claude plugin marketplace add <owner>/MarkSuits --scope project
claude plugin install mark@marksuits --scope project
```

Upgrade the engine with `claude plugin update mark@marksuits`; upgrade generated files with
`copier update -a .mark/.copier-answers.yml` (a 3-way merge that keeps your edits).

## Development

```bash
python3 -m unittest discover -s tests -t .
MARK_COPIER=copier python3 -m unittest tests.test_template   # also generate + render the template
claude plugin validate .
claude --plugin-dir ./plugins/mark
git config core.hooksPath tools/git-hooks   # sensitive-data pre-commit check
```

## License

[MIT](LICENSE)
