# app/src/ui

Presentational only: components take props and report user actions through callbacks.

| Component | Props |
|---|---|
| `CounterForm` | `onAdd(name)`, `busy`; Add is disabled while the trimmed name is empty or busy |
| `CounterList` | `counters`, `loading`, `error`, `onBump(id, delta)` |
| `CounterCard` | `counter` `{id, name, count}`, `onBump(id, delta)`; − is disabled at zero |

- `theme.js`: colours and the shared `StyleSheet`.
- `Preview.js`: one labelled case per `S-N`, mock props; `../../preview.sh` bundles it.
- Test hooks (`testID`, Maestro `id`): `new-counter`, `add-counter`, `counter-<name>`,
  `count-<name>`, `plus-<name>`, `minus-<name>`, `empty`, `error`.
