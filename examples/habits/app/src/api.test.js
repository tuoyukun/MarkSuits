import assert from "node:assert/strict";
import { test } from "node:test";

import { makeApi, week } from "./api.js";

test("week ends today and crosses month boundaries", () => {
  assert.deepEqual(week("2026-03-02"), [
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02",
  ]);
});

test("api calls the backend and surfaces its errors", async () => {
  const calls = [];
  const fake = async (url, init) => {
    calls.push([url, init.method, init.body]);
    const ok = !url.endsWith("/9/toggle");
    return { ok, status: ok ? 200 : 404, json: async () => (ok ? { id: 1 } : { error: "no such habit" }) };
  };
  const api = makeApi("http://x", fake);
  assert.deepEqual(await api.add("Read"), { id: 1 });
  await assert.rejects(api.toggle(9, "2026-03-02"), /no such habit/);
  assert.deepEqual(calls, [
    ["http://x/api/habits", "POST", '{"name":"Read"}'],
    ["http://x/api/habits/9/toggle", "POST", '{"date":"2026-03-02"}'],
  ]);
});
