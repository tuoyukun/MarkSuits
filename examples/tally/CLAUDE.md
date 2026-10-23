# CLAUDE.md — tally

> This file explains **what the project is and how to build it**: stack, layout, module
> boundaries, commands, docs and commit conventions. Every Mark role agent reads it first.
> How the agents collaborate: `mark rules collaboration`, not here.

## 1. Overview

A tally counter for one person: name a few counters (glasses of water, pages read) and step
them up and down; they stay on the phone. Mark's mobile example: an Expo app with no backend,
data in AsyncStorage, tested end to end on the iOS simulator with Maestro.

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Mobile app (`app/`) | Expo SDK 58 (React Native, plain JS), AsyncStorage | iOS simulator in Expo Go; no native build |
| APIs the app calls (none, or third-party) | none | |
| End-to-end tests (`e2e/`) | Maestro flows | black-box: only the app on the simulator; `regression.sh` starts its own dev server |

## 3. Layout

Each module is self-contained: its dependencies, config and scripts live in its own
directory, and it installs, runs and tests from there. The repository root holds only what
this table lists. A path no write rule assigns (`[[write_rules]]` in `.mark/config.toml`) is
written by the main thread only, so a new top-level path needs a row here and a write rule.

| Path | What | Written by |
|---|---|---|
| `app/` | mobile app, with its own dependencies and config (native projects included) | coder-impl (`app/src/ui/`: designer) |
| `e2e/` | end-to-end flows, one per journey; shared steps in `subflows/`; `JOURNEYS.md` lists them | tester |
| `docs/adr/` | architecture decision records | coder-plan |
| `CLAUDE.md` | this file | main thread, coder-plan, coder-impl |
| `scripts/` | the entry points below; shipped by Mark, never edited by a ticket | main thread |
| `README.md`, `.gitignore`, `.mark/`, `.claude/` | project docs and workflow files | main thread |

`scripts/` only calls each module's own entry point, run from inside the module with the
checkout's `.env` exported (each worktree's own ports among them):

| Entry point | Who provides it | Does |
|---|---|---|
| `selftest.sh` | `app/` (required once it exists) | white-box self-test: the module's lint, type check, unit tests |
| `regression.sh` | `e2e/` (required once it exists) | black-box regression: the whole end-to-end suite on a simulator, under the device lock |
| `start.sh`, `stop.sh` | `app/`, for its dev server (bundler) | start it in the background on its port from `.env` and return once it answers; stop it |

## 4. Module boundaries

| Module | Owns | May depend on | Must not |
|---|---|---|---|
| `app/src/ui` | Presentational components and their preview (designer only) | design tokens, props types | requests, navigation, global state |
| rest of `app` | API calls, state, navigation, native config, wiring the UI components (coder-impl) | `app/src/ui` through its props | changing `app/src/ui` props types |

## 5. Mobile specifics

- **APIs the app calls** are not ours to run. The app reads each API's base URL from `.env`
  when it is bundled or built; never hard-code it. End-to-end tests never call a real
  third-party API and never stub the network inside the app: they run a fake of that API
  from `e2e/` (tester) and point the URL at it.
- **Data on the device.** Every end-to-end run starts from empty app data (a fresh storage
  namespace per run, or clearing the app's state), so runs and worktrees never see each
  other's data. How: `e2e/regression.sh` bundles the app with a fresh
  `EXPO_PUBLIC_STORAGE_KEY` per run; flows in one run share it, so each flow names its own
  counters.
- **Testable UI.** Every element a flow taps or checks has a stable accessibility id (React
  Native `testID`, Flutter `Semantics`, iOS `accessibilityIdentifier`...). Flows find
  elements by it or by visible text, never by coordinates.
- **One device, one run.** A simulator or emulator shows one app at a time: every
  end-to-end run takes the device lock (command below), so worktrees queue for it instead
  of fighting over the screen.
- **Design preview.** `preview.html` is the web build of `app/src/ui/Preview.js` (every
  `S-N` with mock props), inlined into one file by `app/preview.sh`. It is close to the
  device, not the same: design QA on the simulator decides.
- **End-to-end flows.** One Maestro flow per journey; its `name:` is the title in
  `JOURNEYS.md`. Steps that several flows share live in `e2e/subflows/` and run
  through `runFlow`.

## 6. Commands

Role agents run exactly these. Keep them working from a fresh worktree.

| Purpose | Command |
|---|---|
| Install dependencies | `cd app && npm ci` (flows: none; Maestro and Xcode on the machine) |
| Start / stop / restart the app's dev server | `bash scripts/start.sh` / `bash scripts/stop.sh` / `bash scripts/restart.sh` |
| Open the app on the simulator | `bash scripts/start.sh`, then `xcrun simctl openurl booted "exp://127.0.0.1:$METRO_PORT"` (Expo Go; first time: `cd app && npx expo start --ios`) |
| Build the UI preview (`preview.html`) | `cd app && bash preview.sh <ticket dir>/preview.html` |
| Self-test (white-box, every module) | `bash scripts/selftest.sh` |
| End-to-end tests (selected flows, under the device lock) | `cd e2e && bash regression.sh <flow>.yaml` (the script takes the lock) |
| Full regression (what a merge must pass, `[merge] regression`) | `bash scripts/selftest.sh && bash scripts/regression.sh` |

## 7. Red lines

1. No architecture-level decision without an ADR (`docs/adr/`).
2. No reaching across module boundaries outside defined contracts.
3. Changing a module requires updating its `CONTEXT.md`.
4. Nothing at the repository root that the Layout table does not list: no shared
   dependencies, tool config or scripts there. A module's commands go in its own entry
   points, never in `scripts/`.

## 8. Commit format

```
type(module): what changed

Why:
How:
Rejected:
Refs: <ticket id> <R-N / FAIL-N / D-N>
```
