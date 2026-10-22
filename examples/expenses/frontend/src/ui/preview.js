// UI preview: every state of every component, rendered from mock props, offline.
// Open http://127.0.0.1:<port>/src/ui/preview.html while the app is served.
import { h } from "./dom.js";
import { ExpenseForm, ExpenseList, Total } from "./components.js";

const log = (name, result) => (...args) => { console.log(`[preview] ${name}`, ...args); return result; };

const items = [
  { id: 1, label: "Lunch", amount: 12.5 },
  { id: 2, label: "Train ticket to the airport and back", amount: 38 },
  { id: 3, label: "Coffee", amount: 3.2 },
];

// Each case: [label, render()]. Labels name the state; ticket designs add S-N ids.
const cases = [
  ["ExpenseForm · ready (submit accepts)", () => ExpenseForm({ onAdd: log("onAdd", true) })],
  ["ExpenseForm · submit refuses the amount", () => ExpenseForm({ onAdd: log("onAdd", false) })],
  ["ExpenseList · empty", () => ExpenseList({ items: [], onDelete: log("onDelete") })],
  ["ExpenseList · items", () => ExpenseList({ items, onDelete: log("onDelete") })],
  ["Total · zero", () => Total({ cents: 0 })],
  ["Total · with cents", () => Total({ cents: 5370 })],
];

document.querySelector("#preview").append(...cases.map(([label, render]) =>
  h("section", { class: "preview-case", "data-testid": "preview-case" },
    h("p", { class: "preview-case__label" }, label),
    h("div", { class: "card" }, render()),
  )));
