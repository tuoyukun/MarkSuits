# CLAUDE.md — MarkSuits

Guidance for anyone (human or agent) working **on this repository**. This file is
not shipped to Mark users: plugins do not load a CLAUDE.md, and generated
projects get their own from `template/`.

## What this repo is

MarkSuits builds **Mark**, a Claude Code plugin plus a project template that set up a
multi-agent development workflow: a main-thread orchestrator, stateless role
subagents (designer / coder-plan / coder-impl / tester / fix-plan), per-ticket
artifacts, human review gates, and hooks that enforce all of it with exit 2.
Design: `docs/architecture.md`.

## Layout

| Path | What | Ships as |
|---|---|---|
| `.claude-plugin/marketplace.json` | Marketplace catalog (repo root = marketplace) | marketplace |
| `plugins/mark/` | The engine plugin: hooks, skills, CLI, `lib/mark/` | plugin (upgradable) |
| `copier.yml`, `template/project/` | Copier template: roles, prompts, artifact formats, `.mark/config.toml`; localized dirs are named `{% if locale == '<loc>' %}<name>{% endif %}` | generated once, owned by the project |
| `tests/` | Engine and template tests (`unittest`, stdlib; template generation needs Copier) | dev only |
| `.github/workflows/` | CI: tests on 3.11/3.13, template per locale, manifests, sensitive scan | dev only |
| `tools/` | Repo tooling (sensitive-data check, git hooks) | dev only |
| `docs/` | Architecture and decisions | dev only |

## Rules

1. **Engine code is Python 3.11+ standard library only.** No third-party imports in `plugins/`.
2. **Hooks are silent outside Mark projects.** Every hook goes through `mark.hookio.run`,
   which exits 0 when no `.mark/config.toml` is found.
3. **Block with exit 2 only.** Never exit 1 to "warn"; it does not block.
4. **No project-specific content in the plugin.** Paths, roles, gates and write scopes come
   from the project's `.mark/config.toml`. If you need a new knob, add it to the config schema.
5. **Never write state under `${CLAUDE_PLUGIN_ROOT}`** (it changes on every update).
   Project state goes in `.mark/`; caches go in `${CLAUDE_PLUGIN_DATA}`.
6. **Match role names after stripping the plugin prefix** (`mark.hookio.normalize_agent_type`).
7. **Hooks match language-neutral anchors** (e.g. `<!-- mark:ac-table -->`), never
   localized headings. Templates ship in `zh-CN` and `en`; engine code and docs are English.
8. **Breaking config changes bump `mark_schema`** and come with a migration note.
9. **Every guard ships with tests.** Run them before committing.

## Commands

```bash
python3 -m unittest discover -s tests -t .     # engine tests
MARK_COPIER=copier python3 -m unittest tests.test_template   # + generate the template per locale
claude plugin validate .                       # marketplace + plugin manifests
claude --plugin-dir ./plugins/mark             # load the plugin for one session
python3 tools/check_sensitive.py               # sensitive-data scan
MARK_DEBUG_LOG=/tmp/mark.log claude --plugin-dir ./plugins/mark   # record raw hook payloads
```

## This repository is public

Never commit secrets, machine paths, personal emails, or names/details of private
projects. Install the pre-commit check once: `git config core.hooksPath tools/git-hooks`.
Private terms to block go in `.sensitive-words`; private notes for agents go in
`CLAUDE.local.md`. Both are gitignored.
