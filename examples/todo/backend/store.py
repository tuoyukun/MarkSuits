"""In-memory todo store. One process, one list; restarting the server empties it."""
from __future__ import annotations

import itertools
import threading

MAX_TITLE = 200


class NotFound(KeyError):
    pass


class Invalid(ValueError):
    pass


def clean_title(value: object) -> str:
    if not isinstance(value, str):
        raise Invalid("title must be a string")
    title = " ".join(value.split())
    if not title:
        raise Invalid("title must not be empty")
    if len(title) > MAX_TITLE:
        raise Invalid(f"title must be at most {MAX_TITLE} characters")
    return title


class TodoStore:
    def __init__(self) -> None:
        self._items: dict[int, dict] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def _get(self, todo_id: int) -> dict:
        try:
            return dict(self._items[todo_id])
        except KeyError:
            raise NotFound(todo_id) from None

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(t) for t in self._items.values()]

    def add(self, title: object) -> dict:
        todo = {"title": clean_title(title), "done": False}
        with self._lock:
            todo["id"] = next(self._ids)
            self._items[todo["id"]] = todo
            return dict(todo)

    def update(self, todo_id: int, changes: dict) -> dict:
        with self._lock:
            todo = self._get(todo_id)
            if "done" in changes:
                if not isinstance(changes["done"], bool):
                    raise Invalid("done must be true or false")
                todo["done"] = changes["done"]
            if "title" in changes:
                todo["title"] = clean_title(changes["title"])
                self._items[todo_id] = todo
            return dict(todo)

    def delete(self, todo_id: int) -> None:
        with self._lock:
            self._get(todo_id)
            del self._items[todo_id]
