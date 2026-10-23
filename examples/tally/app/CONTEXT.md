# app

Expo (React Native) app; runs in Expo Go on the simulator, no native build, no backend.

- `index.js`: entry; registers `App`, or `src/ui/Preview` when `EXPO_PUBLIC_PREVIEW` is set.
- `App.js`: container, drawn inside the safe area (status bar, notch, hinge). Loads the
  counters from AsyncStorage, adds counters, steps them up and down, saves after each
  change; shows the error from a failed load or save.
- `src/tally.js`: `addCounter`, `bump` (never below zero) and `makeStore(storage, key)`
  (load / save the list as JSON); unit tests in `src/tally.test.js` (`node --test`).
- Storage key: `EXPO_PUBLIC_STORAGE_KEY` at bundle time (default `tally`); the end-to-end
  run sets a fresh one, so it starts with no counters.
- `src/ui/`: presentational components, designer-owned (see its `CONTEXT.md`).
- `start.sh` / `stop.sh`: Metro on `METRO_PORT`.
- `preview.sh <out.html>`: the UI preview as one self-contained HTML file (web build).
