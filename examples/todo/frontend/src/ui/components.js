// Presentational components. They render from props and report user actions through
// callbacks; they never fetch, store or route. Owned by the designer.
import { h } from "./dom.js";

/**
 * @typedef {{ id: number, title: string, done: boolean }} Todo
 */

/**
 * Input + Add button. Clears itself after a submit; ignores blank input.
 * @param {{ disabled?: boolean, onAdd: (title: string) => void }} props
 */
export function TodoForm({ disabled = false, onAdd }) {
  const input = h("input", {
    class: "todo-form__input", type: "text", name: "title", maxlength: 200,
    placeholder: "What needs doing?", "aria-label": "New todo", autocomplete: "off",
    "data-testid": "new-todo", disabled,
  });
  return h("form", {
    class: "todo-form", "data-testid": "todo-form",
    onsubmit: (event) => {
      event.preventDefault();
      const title = input.value.trim();
      if (!title) return;
      onAdd(title);
      input.value = "";
      input.focus();
    },
  }, input, h("button", { class: "button button--primary", type: "submit", disabled }, "Add"));
}

/**
 * One row: checkbox, title, delete.
 * @param {{ todo: Todo, onToggle: (id: number, done: boolean) => void, onDelete: (id: number) => void }} props
 */
export function TodoItem({ todo, onToggle, onDelete }) {
  const id = `todo-${todo.id}`;
  return h("li", {
    class: `todo${todo.done ? " todo--done" : ""}`, "data-testid": "todo-item",
    dataset: { id: todo.id, done: todo.done },
  },
    h("input", {
      class: "todo__check", type: "checkbox", id, checked: todo.done,
      "data-testid": "todo-toggle",
      onchange: (event) => onToggle(todo.id, event.target.checked),
    }),
    h("label", { class: "todo__title", for: id, "data-testid": "todo-title" }, todo.title),
    h("button", {
      class: "button button--ghost todo__delete", type: "button",
      "aria-label": `Delete ${todo.title}`, "data-testid": "todo-delete",
      onclick: () => onDelete(todo.id),
    }, "×"),
  );
}

/**
 * The list, or an empty message.
 * @param {{ todos: Todo[], onToggle: (id: number, done: boolean) => void, onDelete: (id: number) => void }} props
 */
export function TodoList({ todos, onToggle, onDelete }) {
  if (todos.length === 0) {
    return h("p", { class: "empty", "data-testid": "empty" }, "Nothing to do yet. Add something above.");
  }
  return h("ul", { class: "todo-list", "data-testid": "todo-list" },
    todos.map((todo) => TodoItem({ todo, onToggle, onDelete })));
}

/**
 * Loading or error line. `onRetry` shows a retry button on errors.
 * @param {{ kind: "loading" | "error", message?: string, onRetry?: () => void }} props
 */
export function Notice({ kind, message, onRetry }) {
  const text = message ?? (kind === "loading" ? "Loading…" : "Something went wrong.");
  return h("div", { class: `notice notice--${kind}`, role: kind === "error" ? "alert" : "status",
    "data-testid": `notice-${kind}` },
    h("span", {}, text),
    kind === "error" && onRetry
      ? h("button", { class: "button button--ghost", type: "button", onclick: onRetry }, "Retry")
      : null,
  );
}
