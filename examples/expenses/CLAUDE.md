# CLAUDE.md — expenses

> This file explains **what the project is and how to build it**: stack, layout, module
> boundaries, commands, docs and commit conventions. Every Mark role agent reads it first.
> How the agents collaborate: `mark rules collaboration`, not here.

## 1. Overview

A single-page expense tracker: add an expense (label and amount), delete one, see the total.
It is the Mark example for the `web-frontend` profile: a browser app with no backend of its
own. Data lives in the browser's localStorage, so it survives a reload but not a new browser
profile.

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend (`frontend/`) | Vanilla JavaScript ES modules, plain CSS, no build step | served as static files (`python3 -m http.server`) |
| APIs the app calls (none, or third-party) | none | data in localStorage |
| End-to-end tests (`tests/`) | Playwright (`@playwright/test`, Chromium) | serves the app itself on a per-checkout port |

## 3. Layout

Each module is self-contained: its dependencies, config and scripts live in its own
directory. The repository root holds only what this table lists. A path no write rule
assigns (`[[write_rules]]` in `.mark/config.toml`) is written by the main thread only.

| Path | What | Written by |
|---|---|---|
| `frontend/` | the browser app, no build step; `selftest.sh`, `start.sh`, `stop.sh` | coder-impl (`frontend/src/ui/`: designer) |
| `tests/` | end-to-end specs, Playwright config, `package.json`; `regression.sh`; `JOURNEYS.md` (every test and its path) | tester |
| `docs/adr/` | architecture decision records | coder-plan |
| `CLAUDE.md` | this file | main thread, coder-plan, coder-impl |
| `scripts/` | entry points shipped by Mark; they call each module's own | main thread |
| `README.md`, `.gitignore`, `.mark/`, `.claude/` | project docs and workflow files | main thread |

`bash scripts/selftest.sh` runs `frontend/selftest.sh` (white-box); `bash scripts/regression.sh`
runs `tests/regression.sh` (black-box, the whole end-to-end suite); `bash scripts/start.sh` /
`stop.sh` / `restart.sh` run `frontend/start.sh` / `stop.sh`. Each runs inside its module with
the checkout's `.env` exported.

## 4. Module boundaries

| Module | Owns | May depend on | Must not |
|---|---|---|---|
| `frontend/src/ui` | Presentational components (`components.js`), `dom.js`, styles, and the preview (designer only) | `dom.js`, CSS custom properties in `styles.css` | storage, global state, `app.js`, `store.js` |
| `frontend/src` (outside `ui/`) | `app.js` (state, wiring, which UI state is shown) and `store.js` (expense rules and localStorage) | `ui/components.js` through their props | build DOM by hand, style components, change `ui/` props types |
| `tests` | end-to-end specs in `tests/e2e/` | the app through the browser | import application code, stub the network |

The app calls no API. If a feature adds one, end-to-end tests never call the real
third-party API and never stub the network in the browser: the app reads the API's base URL
from `.env`, and the tests run a fake of that API from `tests/` (tester) and point the URL at it.

Each module has a `CONTEXT.md` that describes its current shape.

## 5. Commands

Role agents run exactly these, from the root of their worktree. Every new worktree gets
`npm --prefix tests ci` before an agent starts (`[worktree] setup`); install the browser
once per machine.

| Purpose | Command |
|---|---|
| Install dependencies | `npm --prefix tests ci && npm --prefix tests exec playwright install chromium` |
| Start / stop / restart the app | `bash scripts/start.sh` / `bash scripts/stop.sh` / `bash scripts/restart.sh` (port: `FRONTEND_PORT` in `.env`, default 8000) |
| Open the UI preview | start the app, then `http://127.0.0.1:<port>/src/ui/preview.html` |
| Screenshot a page | `npm --prefix tests exec -- playwright screenshot --viewport-size "1280, 800" --full-page <url> <file.png>` (mobile: `"390, 844"`) |
| Self-test (white-box) | `bash scripts/selftest.sh` (JS syntax check; `node --test`, `frontend/src/*.test.js`) |
| End-to-end tests (selected specs) | `cd tests && npx playwright test e2e/<spec>.spec.js` |
| Full regression (what a merge must pass, `[merge] regression`) | `bash scripts/selftest.sh && bash scripts/regression.sh` |

End-to-end tests pick a port from the checkout path, so several worktrees can run them at
once; set `PORT=<n>` to override. Failure traces and screenshots land in `tests/test-results/`.

## 6. Red lines

1. No architecture-level decision without an ADR (`docs/adr/`).
2. No reaching across module boundaries outside defined contracts.
3. Changing a module requires updating its `CONTEXT.md`.
4. Nothing at the repository root that the Layout table does not list.
5. No new runtime dependencies, and no backend: the frontend stays build-free.

## 7. Commit format

```
type(module): what changed

Why:
How:
Rejected:
Refs: <ticket id> <R-N / FAIL-N / D-N>
```
