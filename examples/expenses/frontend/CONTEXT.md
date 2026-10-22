# frontend

- `index.html`: page shell with three slots: `#form`, `#list`, `#total`.
- `src/app.js`: container. Loads the expenses from localStorage, saves after every change,
  re-renders the list and total. The form is mounted once so typing is never interrupted.
- `src/store.js`: pure functions over the expense list (`parseAmount`, `add`, `remove`,
  `totalCents`) plus `load` / `save` against a `Storage`; unit tests in `src/store.test.js`.
- `src/ui/`: presentational components, designer-owned (see its `CONTEXT.md`).
- `start.sh` / `stop.sh`: serve this directory with `python3 -m http.server`.
