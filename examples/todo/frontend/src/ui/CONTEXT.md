# frontend/src/ui

Presentational only: components take props and report user actions through callbacks.

| Component | Props |
|---|---|
| `TodoForm` | `disabled?`, `onAdd(title)` |
| `TodoList` | `todos`, `onToggle(id, done)`, `onDelete(id)`; renders the empty message when `todos` is empty |
| `TodoItem` | `todo`, `onToggle`, `onDelete` |
| `Notice` | `kind: "loading" \| "error"`, `message?`, `onRetry?` |

- `dom.js`: `h(tag, props, ...children)`; `on*` props become listeners.
- `styles.css`: tokens as CSS custom properties on `:root`, then component classes (BEM-ish:
  `block__element--modifier`).
- `preview.html` / `preview.js`: one labelled case per state, mock props, no network.
- Test hooks: `data-testid` on every interactive element and on list rows
  (`todo-item` also carries `data-id` and `data-done`).
