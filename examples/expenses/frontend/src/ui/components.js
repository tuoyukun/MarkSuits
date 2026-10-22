// Presentational components. They render from props and report user actions through
// callbacks; they never store, fetch or route. Owned by the designer.
import { h } from "./dom.js";

/**
 * @typedef {{ id: number, label: string, amount: number }} Expense
 */

const money = (cents) => (cents / 100).toFixed(2);

/**
 * Label + amount + Add. `onAdd` returns false when the amount is invalid: the form then
 * keeps the input and shows an error; on true it clears itself. Blank labels are ignored.
 * @param {{ onAdd: (label: string, amountText: string) => boolean }} props
 */
export function ExpenseForm({ onAdd }) {
  const label = h("input", {
    class: "field", type: "text", name: "label", maxlength: 80, placeholder: "What for?",
    "aria-label": "Label", autocomplete: "off", "data-testid": "new-label",
  });
  const amount = h("input", {
    class: "field field--amount", type: "text", name: "amount", inputmode: "decimal",
    placeholder: "0.00", "aria-label": "Amount", autocomplete: "off", "data-testid": "new-amount",
  });
  const error = h("p", { class: "form-error", role: "alert", "data-testid": "form-error", hidden: true },
    "Enter an amount above zero.");
  return h("form", {
    class: "expense-form", "data-testid": "expense-form",
    onsubmit: (event) => {
      event.preventDefault();
      const text = label.value.trim();
      if (!text) return;
      const ok = onAdd(text, amount.value.trim());
      error.hidden = ok;
      if (!ok) return;
      label.value = "";
      amount.value = "";
      label.focus();
    },
  }, label, amount, h("button", { class: "button button--primary", type: "submit" }, "Add"), error);
}

/**
 * The list, or an empty message.
 * @param {{ items: Expense[], onDelete: (id: number) => void }} props
 */
export function ExpenseList({ items, onDelete }) {
  if (items.length === 0) {
    return h("p", { class: "empty", "data-testid": "empty" }, "No expenses yet.");
  }
  return h("ul", { class: "expense-list", "data-testid": "expense-list" },
    items.map((e) => h("li", { class: "expense", "data-testid": "expense-item", dataset: { id: e.id } },
      h("span", { class: "expense__label", "data-testid": "expense-label" }, e.label),
      h("span", { class: "expense__amount", "data-testid": "expense-amount" }, money(Math.round(e.amount * 100))),
      h("button", {
        class: "button button--ghost", type: "button", "aria-label": `Delete ${e.label}`,
        "data-testid": "expense-delete", onclick: () => onDelete(e.id),
      }, "×"),
    )));
}

/**
 * The running total.
 * @param {{ cents: number }} props
 */
export function Total({ cents }) {
  return h("p", { class: "total" }, "Total ", h("strong", { "data-testid": "total" }, money(cents)));
}
