// Container: owns state, talks to the API, decides which UI state to show.
import { api } from "./api.js";
import { Notice, TodoForm, TodoList } from "./ui/components.js";

const state = { todos: [], loading: true, error: null };

const formSlot = document.querySelector("#form");
const noticeSlot = document.querySelector("#notice");
const listSlot = document.querySelector("#list");

function fail(message) {
  state.error = message;
  render();
}

async function load() {
  state.loading = true;
  state.error = null;
  render();
  try {
    state.todos = await api.list();
  } catch (err) {
    state.error = `Could not load todos. ${err.message}`;
  } finally {
    state.loading = false;
    render();
  }
}

async function onAdd(title) {
  try {
    state.todos = [...state.todos, await api.add(title)];
    state.error = null;
    render();
  } catch (err) {
    fail(`Could not add the todo. ${err.message}`);
  }
}

async function onToggle(id, done) {
  const before = state.todos;
  state.todos = before.map((t) => (t.id === id ? { ...t, done } : t));
  render();
  try {
    await api.update(id, { done });
  } catch (err) {
    state.todos = before;
    fail(`Could not update the todo. ${err.message}`);
  }
}

async function onDelete(id) {
  try {
    await api.remove(id);
    state.todos = state.todos.filter((t) => t.id !== id);
    render();
  } catch (err) {
    fail(`Could not delete the todo. ${err.message}`);
  }
}

function render() {
  noticeSlot.replaceChildren(
    ...(state.loading ? [Notice({ kind: "loading" })] : []),
    ...(state.error ? [Notice({ kind: "error", message: state.error, onRetry: load })] : []),
  );
  listSlot.replaceChildren(state.loading ? "" : TodoList({ todos: state.todos, onToggle, onDelete }));
}

// The form is mounted once so typing is never interrupted by re-renders.
formSlot.replaceChildren(TodoForm({ onAdd }));
load();
