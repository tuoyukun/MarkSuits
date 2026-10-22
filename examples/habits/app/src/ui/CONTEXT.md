# app/src/ui

Presentational only: components take props and report user actions through callbacks.

| Component | Props |
|---|---|
| `HabitForm` | `onAdd(name)`, `busy`; Add is disabled while the trimmed name is empty or busy |
| `HabitList` | `habits`, `days` (YYYY-MM-DD, oldest first), `loading`, `error`, `onToggle(id, day)` |
| `HabitCard` | `habit` `{id, name, days, streak}`, `days`, `onToggle(id, day)` |

- `theme.js`: colours and the shared `StyleSheet`.
- `Preview.js`: one labelled case per `S-N`, mock props; `../../preview.sh` bundles it.
- Test hooks (`testID`, Maestro `id`): `new-habit`, `add-habit`, `habit-<name>`,
  `streak-<name>`, `day-<name>-<YYYY-MM-DD>`, `empty`, `error`.
