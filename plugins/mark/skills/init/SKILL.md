---
description: Set up Mark in the current repository, new or existing - check the stack fits, propose the answers, write the project files, then fill in CLAUDE.md. Use when the human asks to set up, install or initialize Mark in a project.
argument-hint: [anything the human already said about the project]
allowed-tools: Bash(mark:*)
---

## /mark:init

Argument: `$ARGUMENTS`

`mark init` writes Mark's project files (role agents, prompts, formats, `.mark/config.toml`)
and commits them on main. You decide the answers with the human; the command does the rest.
Speak the human's language.

1. **Check the target.** Run `mark init --dry-run`. If it refuses (already a Mark project,
   uncommitted changes, wrong branch, files that would be overwritten, no git identity),
   tell the human what it said and how to fix it, and stop.

2. **New or existing?** It is **new** when the repository has no source code yet (at most a
   README, a LICENSE, a .gitignore). Otherwise it is **existing**.

3. **Check the stack fits.** Mark ships one role pack today, `web-fullstack`: a browser
   frontend, a backend service, and browser end-to-end tests, in one repository.
   - Existing: read the manifests (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`,
     `Makefile`...), the CI config, the top-level layout and any existing `CLAUDE.md`.
   - New: ask the human what they are building and on what stack.

   If it is not a web app with a frontend and a backend (a CLI, a library, a mobile app, a
   backend-only service, a data pipeline...), **stop**: say Mark only supports web full-stack
   projects for now, more templates will follow, and write nothing.

4. **Propose the answers** as one table and wait for the human to confirm or correct it:

   | answer | new project | existing project |
   |---|---|---|
   | `--locale` | the human's language: `en` or `zh-CN` | same |
   | `--project-name` | ask | from the manifest or the directory name |
   | `--main-branch` | `main` | the branch the dry run shows |
   | `--frontend-dir`, `--backend-dir` | planned directories | where that code is now |
   | `--ui-dir` | `<frontend>/src/ui` | the presentational components (only the designer writes there) |
   | `--tests-dir` | planned end-to-end test directory | where the end-to-end tests are |
   | `--regression-cmd` | empty (no tests yet) | the command CI runs for the full suite |
   | `--worktree-setup` | empty | the install step a fresh checkout needs, like `npm ci` |

   Also say which existing files it keeps (`CLAUDE.md`) or extends (`.gitignore`); the dry run
   lists them.

5. **Apply.** Run `mark init` with the confirmed answers, each as `--<answer> "<value>"`.
   Report the result in two lines.

6. **Fill in CLAUDE.md.** Every role reads it first: stack, module boundaries, and the exact
   commands (install, dev server, UI preview, unit tests, lint, end-to-end, full regression).
   The main checkout is now a Mark project, so edit it in a general lane, as in /mark:general:
   `mark general new`, edit `<worktree>/CLAUDE.md`, commit in the lane, `mark general merge <branch>`.
   - Existing project with its own `CLAUDE.md`: keep everything there and add only what is
     missing from the list above, as new sections. If it gets long, say so; do not cut the
     human's text.
   - Existing project without one: fill in every TODO from what you read; leave a TODO only
     where you could not tell, and name it in your report.
   - New project: skip this step; there is nothing to describe yet.

7. **Next step.**
   - If `mark init` said to restart, say that first: this session cannot dispatch the role
     agents until the human restarts Claude Code (`/exit`, then `claude -c`). Do not start a
     ticket in this session.
   - Existing: work starts with `/mark:feature` or `/mark:fix`.
   - New: suggest the first ticket, `/mark:feature` for the project skeleton (framework,
     layout, first test, the commands in `CLAUDE.md`). It has no UI to design, so the human
     may waive design review with `.mark/gates/<id>.design-approved.waived`; the stack choice is
     reviewed at plan review. Once it lands, set `[merge] regression` and `[worktree] setup`
     with `/mark:general`.
