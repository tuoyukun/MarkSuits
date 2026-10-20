// UI preview: every state of every component, rendered from mock props, offline.
// Open http://127.0.0.1:<port>/src/ui/preview.html while the dev server runs.
import { h } from "./dom.js";
import { Notice, TodoForm, TodoList } from "./components.js";

const log = (name) => (...args) => console.log(`[preview] ${name}`, ...args);
const handlers = { onAdd: log("onAdd"), onToggle: log("onToggle"), onDelete: log("onDelete") };

const todos = [
  { id: 1, title: "Buy milk", done: false },
  { id: 2, title: "Call the plumber about the kitchen sink", done: true },
  { id: 3, title: "Write the quarterly report", done: false },
];
const long = [{ id: 4, title: "A very long title ".repeat(12).trim(), done: false }];

// Each case: [label, render()]. Labels name the state; ticket designs add S-N ids.
const cases = [
  ["TodoForm · ready", () => TodoForm(handlers)],
  ["TodoForm · disabled", () => TodoForm({ ...handlers, disabled: true })],
  ["TodoList · empty", () => TodoList({ ...handlers, todos: [] })],
  ["TodoList · active and done items", () => TodoList({ ...handlers, todos })],
  ["TodoList · long title wraps", () => TodoList({ ...handlers, todos: long })],
  ["Notice · loading", () => Notice({ kind: "loading" })],
  ["Notice · error with retry", () => Notice({ kind: "error", message: "Could not load todos.", onRetry: log("onRetry") })],
];

document.querySelector("#preview").append(...cases.map(([label, render]) =>
  h("section", { class: "preview-case", "data-testid": "preview-case" },
    h("p", { class: "preview-case__label" }, label),
    h("div", { class: "card" }, render()),
  )));
