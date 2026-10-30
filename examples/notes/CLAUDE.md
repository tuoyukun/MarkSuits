# CLAUDE.md — notes

> This file explains **what the project is and how to build it**: stack, layout, module
> boundaries, commands, docs and commit conventions. Every Mark role agent reads it first.
> How the agents collaborate: `mark rules collaboration`, not here.

## 1. Overview

A small notes service: a JSON API to create, read, list and delete text notes. It is the
example project for Mark's `service` profile: no UI, so features go straight to planning,
and the end-to-end tests reach the service only over HTTP. Data lives in memory;
restarting the service empties it.

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Service (`service/`) | Python 3.11+ standard library (`http.server`) | JSON API under `/api`, contract in the `server.py` docstring |
| Storage | in memory (`store.py`) | no persistence |
| End-to-end tests (`e2e/`) | Python `unittest` + `urllib` | black-box: only the HTTP API; `regression.sh` starts its own service |

## 3. Layout

Each module is self-contained: its dependencies, config and scripts live in its own
directory. The repository root holds only what this table lists. A path no write rule
assigns (`[[write_rules]]` in `.mark/config.toml`) is written by the main thread only.

| Path | What | Written by |
|---|---|---|
| `service/` | the HTTP service and its unit tests; `selftest.sh`, `start.sh`, `stop.sh` | coder-impl |
| `e2e/` | regression tests in `regression/`, each ticket's acceptance tests in `tickets/<id>/`, their HTTP client; `regression.sh`; `regression/JOURNEYS.md` (the regression journeys and their paths) | tester |
| `docs/adr/` | architecture decision records | coder-plan |
| `CLAUDE.md` | this file | main thread, coder-plan, coder-impl |
| `scripts/` | entry points shipped by Mark; they call each module's own | main thread |
| `README.md`, `.gitignore`, `.mark/`, `.claude/` | project docs and workflow files | main thread |

`bash scripts/selftest.sh` runs `service/selftest.sh` (white-box); `bash scripts/regression.sh`
runs `e2e/regression.sh` (black-box, the core-flow regression journeys); `bash scripts/start.sh` /
`stop.sh` / `restart.sh` run `service/start.sh` / `stop.sh`. Each runs inside its module with
the checkout's `.env` exported.

## 4. Module boundaries and contracts

The public interface is the API in the `service/server.py` docstring: every route, its
status codes, and the error shape `{"error": "..."}`. The end-to-end tests check exactly that.

| Module | Owns | May depend on | Must not |
|---|---|---|---|
| `service` | `server.py` (routes, HTTP errors) and `store.py` (data and validation) | standard library only | serve anything outside `/api` |
| `e2e` | regression tests in `e2e/regression/` (client beside them), ticket acceptance tests in `e2e/tickets/<id>/` | the running service over HTTP | import service code or read its files |

Each module has a `CONTEXT.md` that describes its current shape.

## 5. Commands

Role agents run exactly these, from the root of their worktree. Nothing needs installing.

| Purpose | Command |
|---|---|
| Install dependencies | none (standard library only) |
| Start / stop / restart the service | `bash scripts/start.sh` / `bash scripts/stop.sh` / `bash scripts/restart.sh` (port: `SERVICE_PORT` in `.env`, default 8000) |
| Self-test (white-box) | `bash scripts/selftest.sh` (Python compile and `unittest`, `service/test_*.py`) |
| End-to-end tests (selected cases) | `cd e2e && bash regression.sh -k <name>` |
| Full regression (what a merge must pass, `[merge] regression`) | `bash scripts/selftest.sh && bash scripts/regression.sh` |

End-to-end tests start the service on a port picked from the checkout path, so several
worktrees can run them at once; set `PORT=<n>` to override. Each test empties the service
through the API first.

## 6. Red lines

1. No architecture-level decision without an ADR (`docs/adr/`).
2. No change to the public interface without a plan that says so; a breaking change needs an ADR.
3. Changing a module requires updating its `CONTEXT.md`.
4. Nothing at the repository root that the Layout table does not list.
5. No runtime dependencies: the service and the tests stay on the standard library.

## 7. Commit format

```
type(module): what changed

Why:
How:
Rejected:
Refs: <ticket id> <R-N / FAIL-N>
```
