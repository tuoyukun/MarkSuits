// HTTP client for the backend API (see backend/server.py for the contract).

async function call(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `${method} ${path} failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  list: () => call("GET", "/api/todos"),
  add: (title) => call("POST", "/api/todos", { title }),
  update: (id, changes) => call("PATCH", `/api/todos/${id}`, changes),
  remove: (id) => call("DELETE", `/api/todos/${id}`),
};
