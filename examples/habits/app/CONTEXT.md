# app

Expo (React Native) app; runs in Expo Go on the simulator, no native build.

- `index.js`: entry; registers `App`, or `src/ui/Preview` when `EXPO_PUBLIC_PREVIEW` is set.
- `App.js`: container, drawn inside the safe area (status bar, notch, hinge). Loads
  `{today, habits}` from the backend, adds habits, toggles check-ins,
  reloads after each change; shows the error from a failed call.
- `src/api.js`: `makeApi(base, fetch)` (list / add / toggle) and `week(today)`, the 7 days
  ending on the backend's today; unit tests in `src/api.test.js` (`node --test`).
- `src/ui/`: presentational components, designer-owned (see its `CONTEXT.md`).
- `start.sh` / `stop.sh`: Metro on `METRO_PORT`, app pointed at `BACKEND_PORT`.
- `preview.sh <out.html>`: the UI preview as one self-contained HTML file (web build).
