# frontend

- `index.html`: page shell with three slots: `#notice`, `#form`, `#list`.
- `src/app.js`: container. Holds `{ todos, loading, error }`, calls the API, re-renders the
  notice and list slots. The form is mounted once so typing is never interrupted. Toggling
  is optimistic and rolls back on error.
- `src/api.js`: `api.list | add | update | remove`, throws `Error(message)` on non-2xx.
- `src/ui/`: presentational components, designer-owned (see its `CONTEXT.md`).
