# CLAUDE.md — todo

> This file explains **what the project is and how to build it**: stack, layout, module
> boundaries, commands, docs and commit conventions. Every Mark role agent reads it first.
> How the agents collaborate lives in `.mark/collaboration.md`, not here.

## 1. Overview

A single-page todo list: add, complete, and delete todos. It is the example project for
Mark, small enough to read in a few minutes, with a real browser UI, an HTTP API and
end-to-end tests, so every Mark role has real work to do. Data lives in server memory;
restarting the server empties the list.

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend (`frontend/`) | Vanilla JavaScript ES modules, plain CSS, no build step | served as static files by the backend |
| Backend (`backend/`) | Python 3.11+ standard library (`http.server`) | JSON API under `/api`, contract in the `server.py` docstring |
| End-to-end tests (`tests/`) | Playwright (`@playwright/test`, Chromium) | starts its own server on a per-checkout port |

## 3. Module boundaries

| Module | Owns | May depend on | Must not |
|---|---|---|---|
| `frontend/src/ui` | Presentational components (`components.js`), `dom.js`, styles, and the preview (designer only) | `dom.js`, CSS custom properties in `styles.css` | fetch, global state, `app.js`, `api.js` |
| `frontend/src` (outside `ui/`) | `app.js` (state, wiring, which UI state is shown) and `api.js` (HTTP client) | `ui/components.js` through their props | build DOM by hand or style components |
| `backend` | `server.py` (routes, HTTP errors) and `store.py` (data and validation) | standard library only | serve anything outside `frontend/` |
| `tests` | end-to-end specs in `tests/e2e/` | the running app through the browser, the API for setup | import application code |

Each module has a `CONTEXT.md` that describes its current shape.

## 4. Commands

Role agents run exactly these, from the root of their worktree. Every new worktree gets
`npm ci` before an agent starts (`[worktree] setup`); install the browser once per machine.

| Purpose | Command |
|---|---|
| Install dependencies | `npm ci && npx playwright install chromium` |
| Start the app (dev) | `python3 backend/server.py --port <port>` (pick a free port; default 8000) |
| Open the UI preview | start the app, then `http://127.0.0.1:<port>/src/ui/preview.html` |
| Screenshot a page | `npx playwright screenshot --viewport-size "1280, 800" --full-page <url> <file.png>` (mobile: `"390, 844"`) |
| Unit tests | `npm run test:unit` (backend `unittest`, `backend/test_*.py`) |
| Type check and lint | `npm run check` (syntax check of every JS and Python file) |
| End-to-end tests (selected specs) | `npx playwright test tests/e2e/<spec>.spec.js` |
| Full regression (everything a merge must pass; also `[merge] regression` in `.mark/config.toml`) | `npm test` |

End-to-end tests pick a port from the checkout path, so several worktrees can run them at
once; set `PORT=<n>` to override. Failure traces and screenshots land in `test-results/`.

## 5. Red lines

1. No architecture-level decision without an ADR (`docs/adr/`).
2. No reaching across module boundaries outside defined contracts.
3. Changing a module requires updating its `CONTEXT.md`.
4. No new runtime dependencies. The backend stays on the standard library; the frontend
   stays build-free.

## 6. Commit format

```
type(module): what changed

Why:
How:
Rejected:
Refs: <ticket id> <R-N / FAIL-N / D-N>
```
