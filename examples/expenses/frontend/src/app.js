// Container: owns the expense list, persists it, decides what the UI shows.
import * as store from "./store.js";
import { ExpenseForm, ExpenseList, Total } from "./ui/components.js";

let items = store.load(localStorage);

const formSlot = document.querySelector("#form");
const listSlot = document.querySelector("#list");
const totalSlot = document.querySelector("#total");

function update(next) {
  items = next;
  store.save(localStorage, items);
  render();
}

function onAdd(label, amountText) {
  const amount = store.parseAmount(amountText);
  if (amount === null) return false;  // the form keeps its input and shows the error
  update(store.add(items, label, amount));
  return true;
}

function onDelete(id) {
  update(store.remove(items, id));
}

function render() {
  listSlot.replaceChildren(ExpenseList({ items, onDelete }));
  totalSlot.replaceChildren(Total({ cents: store.totalCents(items) }));
}

// The form is mounted once so typing is never interrupted by re-renders.
formSlot.replaceChildren(ExpenseForm({ onAdd }));
render();
