// Backend client. The base URL comes from .env at bundle time (EXPO_PUBLIC_API_BASE).

export function makeApi(base, fetchFn = fetch) {
  async function call(method, path, body) {
    const res = await fetchFn(base + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }
  return {
    list: () => call("GET", "/api/habits"),
    add: (name) => call("POST", "/api/habits", { name }),
    toggle: (id, date) => call("POST", `/api/habits/${id}/toggle`, { date }),
  };
}

// The 7 days a check-in can be set for, oldest first, ending on `today` (YYYY-MM-DD).
export function week(today) {
  const end = new Date(today + "T00:00:00Z");
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(end);
    d.setUTCDate(end.getUTCDate() - 6 + i);
    return d.toISOString().slice(0, 10);
  });
}
