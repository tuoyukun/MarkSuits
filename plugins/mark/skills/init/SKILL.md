---
description: Set up Mark in the current repository, new or existing - check the stack fits, propose the answers, write the project files, then fill in CLAUDE.md. Use when the human asks to set up, install or initialize Mark in a project.
argument-hint: [anything the human already said about the project]
allowed-tools: Bash(mark:*)
---

## /mark:init

Argument: `$ARGUMENTS`

`mark init` writes the project's Mark files (`.mark/config.toml`, `CLAUDE.md`, `.gitignore`; role agents, prompts and formats ship with the plugin)
and commits them on main. You decide the answers with the human; the command does the rest.
Speak the human's language.

1. **Check the target.** Run `mark init --dry-run`. If it refuses (already a Mark project,
   uncommitted changes, wrong branch, files that would be overwritten, no git identity),
   tell the human what it said and how to fix it, and stop.

2. **New or existing?** It is **new** when the repository has no source code yet (at most a
   README, a LICENSE, a .gitignore). Otherwise it is **existing**.

3. **Pick the profile.** Mark ships these profiles (`--profile`):
   - `web-fullstack`: a browser frontend, a backend service and browser end-to-end tests, in
     one repository. Features go through the designer and a design review.
   - `web-frontend`: a browser frontend with no backend of its own (a static site, or an app
     on third-party APIs or localStorage) and browser end-to-end tests. Designer and design
     review as in `web-fullstack`.
   - `service`: a backend service or API with no UI of its own; end-to-end tests call the
     running service over its public interface (HTTP, say). No designer: features start at
     planning.
   - `mobile-fullstack`: a mobile app (React Native, Flutter, native...) and its backend
     service, in one repository; end-to-end tests drive the app on a simulator with Maestro.
     Designer and design review as in `web-fullstack`.
   - `mobile`: a mobile app with no backend of its own (data on the device, or third-party
     APIs); Maestro end-to-end tests on a simulator as in `mobile-fullstack`.

   - Existing: read the manifests (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`,
     `Makefile`...), the CI config, the top-level layout and any existing `CLAUDE.md`.
   - New: ask the human what they are building and on what stack.

   If no profile fits (a CLI, a library, a data pipeline...), **stop**: say Mark does not support that kind of project yet, more profiles
   will follow, and write nothing.

4. **Propose the answers** as one table and wait for the human to confirm or correct it:

   | answer | new project | existing project |
   |---|---|---|
   | `--profile` | from step 3 | same |
   | `--locale` | the human's language: `en` or `zh-CN` | same |
   | `--project-name` | ask | from the manifest or the directory name |
   | `--main-branch` | `main` | the branch the dry run shows |
   | `--frontend-dir` (web-*), `--backend-dir` (web-fullstack) | planned directories | where that code is now |
   | `--app-dir` (mobile*), `--backend-dir` (mobile-fullstack) | `app`, `backend` | where that code is now |
   | `--ui-dir` (web-*, mobile*) | `<frontend or app>/src/ui` | the presentational components (only the designer writes there) |
   | `--service-dir` (service) | `service` | where the service code is now |
   | `--tests-dir` | planned end-to-end test directory | where the end-to-end tests are |
   | `--worktree-setup` | empty | the install step a fresh checkout needs, like `npm ci` |

   If the end-to-end framework is not the profile's (Playwright for web-*, Maestro for
   mobile*), also say that `[tests] profile` will be set in the CLAUDE.md lane
   (step 6) to the one it uses (`"playwright"`, `"maestro"`), or to `"none"` for any other
   framework: the hook then checks only that tests stay out of production code.

   Also say which existing files it keeps (`CLAUDE.md`) or extends (`.gitignore`); the dry run
   lists them.

   In the same message, propose the **layout**: every top-level path and the role that
   writes it. A role may write only paths a write rule assigns to it; everything else is the
   main thread's.
   - New: each code module and the end-to-end tests are self-contained (own dependencies,
     config and scripts); the root holds only `CLAUDE.md`, `README.md`, `.gitignore`, `.mark/`,
     `.claude/` and the `scripts/` Mark ships. No shared package manifest or tool config at the root.
   - Existing: list the top-level paths that are not a code module, the tests or
     `docs/adr/`, and propose an owner for each (a `[[write_rules]]` entry), or say it stays
     with the main thread.

5. **Apply.** Run `mark init` with the confirmed answers, each as `--<answer> "<value>"`.
   Report the result in two lines.

6. **Fill in CLAUDE.md.** Every role reads it first: stack, layout, module boundaries, and the
   exact commands (install, dev server, UI preview if any, unit tests, lint, end-to-end, full
   regression). Write the confirmed layout into its Layout section, and add the write rules
   the human agreed to `.mark/config.toml` in the same lane.
   The merge check is fixed: `bash scripts/selftest.sh && bash scripts/regression.sh`. Those
   scripts call each module's own entry points, so an existing project needs them before the
   lane can land: in the same lane, write `selftest.sh` in each code module (its
   lint, type check, unit tests, build), `regression.sh` in the test directory (the whole
   end-to-end suite), and `start.sh` / `stop.sh` in each module that runs a server, each
   wrapping the commands the project already uses. Run them once in the lane; the human
   reviews them with the rest.
   With `[tests] profile = "playwright"` or `"maestro"`, `mark merge` also needs `JOURNEYS.md` in the test
   directory to list every end-to-end test: run `mark journeys <worktree>`, write the rows it
   prints with the path column filled in from reading each test, and commit it in the lane.
   The main checkout is now a Mark project, so edit it in a general lane, as in /mark:general:
   `mark general new`, edit `<worktree>/CLAUDE.md`, commit in the lane, `mark general merge <branch>`.
   - Existing project with its own `CLAUDE.md`: keep everything there and add only what is
     missing from the list above, as new sections. If it gets long, say so; do not cut the
     human's text.
   - Existing project without one: fill in every TODO from what you read; leave a TODO only
     where you could not tell, and name it in your report.
   - New project: fill in the overview, the stack the human chose and the Layout section;
     leave the commands as TODO for the skeleton ticket.

7. **Next step.**
   - Existing: work starts with `/mark:feature` or `/mark:fix`.
   - New: suggest the first ticket, `/mark:feature` for the project skeleton (framework,
     each module set up in its own directory as the Layout section says, the commands in
     `CLAUDE.md`). Its acceptance criteria describe what works, such as "the home page lists
     the posts"; the tester writes the end-to-end tests. In the web profiles it has no UI to
     design, so the human may waive design review with `.mark/gates/<id>.design-approved.waived`; the stack choice is
     reviewed at plan review. Its plan creates each module's entry points, so its own merge
     already runs the full regression. Once it lands, set `[worktree] setup` and, if it runs
     servers, `[worktree] ports` (read by the module start scripts and test configs) with
     `/mark:general`.
