// Expenses kept in the browser's localStorage under one key. No UI here: app.js renders.

const KEY = "expenses";

/** Parses what the user typed as an amount; null when it is not a positive number. */
export function parseAmount(text) {
  const value = Number.parseInt(text, 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** @param {Storage} storage */
export function load(storage) {
  try {
    const items = JSON.parse(storage.getItem(KEY) ?? "[]");
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

export function save(storage, items) {
  storage.setItem(KEY, JSON.stringify(items));
}

/** New list with an expense appended; ids grow and are never reused. */
export function add(items, label, amount) {
  const id = items.reduce((max, e) => Math.max(max, e.id), 0) + 1;
  return [...items, { id, label, amount }];
}

export function remove(items, id) {
  return items.filter((e) => e.id !== id);
}

/** Sum in cents, so 0.1 + 0.2 shows as 0.30. */
export function totalCents(items) {
  return items.reduce((sum, e) => sum + Math.round(e.amount * 100), 0);
}
