import assert from "node:assert/strict";
import { test } from "node:test";

import { addCounter, bump, makeStore } from "./tally.js";

test("new counters start at zero with the next id", () => {
  const list = addCounter(addCounter([], "Water"), "Push-ups");
  assert.deepEqual(list, [{ id: 1, name: "Water", count: 0 }, { id: 2, name: "Push-ups", count: 0 }]);
});

test("bump changes one counter and stops at zero", () => {
  const list = [{ id: 1, name: "Water", count: 1 }, { id: 2, name: "Tea", count: 4 }];
  assert.deepEqual(bump(list, 2, 1).map((c) => c.count), [1, 5]);
  assert.deepEqual(bump(bump(list, 1, -1), 1, -1).map((c) => c.count), [0, 4]);
});

test("the store round-trips the list under its key", async () => {
  const items = new Map();
  const storage = { getItem: async (k) => items.get(k) ?? null, setItem: async (k, v) => { items.set(k, v); } };
  const store = makeStore(storage, "run-1");
  assert.deepEqual(await store.load(), []);
  await store.save([{ id: 1, name: "Water", count: 2 }]);
  assert.deepEqual(await store.load(), [{ id: 1, name: "Water", count: 2 }]);
  assert.deepEqual(await makeStore(storage, "run-2").load(), []);
});
