# frontend/src/ui

Presentational only: components take props and report user actions through callbacks.

| Component | Props |
|---|---|
| `ExpenseForm` | `onAdd(label, amountText) → boolean`; false keeps the input and shows the error |
| `ExpenseList` | `items`, `onDelete(id)`; renders the empty message when `items` is empty |
| `Total` | `cents` |

- `dom.js`: `h(tag, props, ...children)`; `on*` props become listeners.
- `styles.css`: tokens as CSS custom properties on `:root`, then component classes.
- `preview.html` / `preview.js`: one labelled case per state, mock props.
- Test hooks: `data-testid` on every interactive element and on list rows
  (`expense-item` also carries `data-id`).
