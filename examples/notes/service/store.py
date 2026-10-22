"""In-memory note store. One process, one list; restarting the service empties it."""
from __future__ import annotations

import threading

MAX_TEXT = 1000


class NotFound(KeyError):
    pass


class Invalid(ValueError):
    pass


def clean_text(value: object) -> str:
    if not isinstance(value, str):
        raise Invalid("text must be a string")
    text = value.strip()
    if not text:
        raise Invalid("text must not be empty")
    if len(text) > MAX_TEXT:
        raise Invalid(f"text must be at most {MAX_TEXT} characters")
    return text


class NoteStore:
    def __init__(self) -> None:
        self._items: dict[int, dict] = {}
        self._lock = threading.Lock()

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(n) for n in self._items.values()]

    def get(self, note_id: int) -> dict:
        with self._lock:
            try:
                return dict(self._items[note_id])
            except KeyError:
                raise NotFound(note_id) from None

    def add(self, text: object) -> dict:
        note = {"text": clean_text(text)}
        with self._lock:
            note["id"] = len(self._items) + 1
            self._items[note["id"]] = note
            return dict(note)

    def delete(self, note_id: int) -> None:
        with self._lock:
            if note_id not in self._items:
                raise NotFound(note_id)
            del self._items[note_id]
