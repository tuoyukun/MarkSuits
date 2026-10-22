import assert from "node:assert/strict";
import { test } from "node:test";
import { add, load, parseAmount, remove, save, totalCents } from "./store.js";

function memory() {
  const data = new Map();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)) };
}

test("save and load round-trip", () => {
  const storage = memory();
  save(storage, add([], "Lunch", 12));
  assert.deepEqual(load(storage), [{ id: 1, label: "Lunch", amount: 12 }]);
});

test("load survives missing or broken data", () => {
  const storage = memory();
  assert.deepEqual(load(storage), []);
  storage.setItem("expenses", "{not json");
  assert.deepEqual(load(storage), []);
});

test("ids are never reused after a delete", () => {
  const items = add(add([], "a", 1), "b", 2);
  assert.equal(add(remove(items, 2), "c", 3).at(-1).id, 2);  // highest left is 1
  assert.equal(add(remove(items, 1), "c", 3).at(-1).id, 3);
});

test("parseAmount rejects what is not a positive number", () => {
  for (const text of ["", "abc", "0", "-5"]) assert.equal(parseAmount(text), null, text);
  assert.equal(parseAmount("7"), 7);
});

test("totalCents adds whole amounts", () => {
  assert.equal(totalCents([{ amount: 12 }, { amount: 30 }]), 4200);
});
