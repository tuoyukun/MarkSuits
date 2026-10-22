"""In-memory habit store. One process, one dict; restarting the backend empties it."""
from __future__ import annotations

import os
import threading
from datetime import date, timedelta

MAX_NAME = 60
WINDOW = 7          # a check-in may be set or cleared for today and the 6 days before
ONE_DAY = timedelta(days=1)


class NotFound(KeyError):
    pass


class Invalid(ValueError):
    pass


def today() -> date:
    """HABITS_TODAY (YYYY-MM-DD) pins the date, for demos and end-to-end runs."""
    pinned = os.environ.get("HABITS_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def clean_name(value: object) -> str:
    if not isinstance(value, str):
        raise Invalid("name must be a string")
    name = value.strip()
    if not name:
        raise Invalid("name must not be empty")
    if len(name) > MAX_NAME:
        raise Invalid(f"name must be at most {MAX_NAME} characters")
    return name


def parse_day(value: object, now: date) -> date:
    try:
        day = date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        day = None
    if day is None:
        raise Invalid("date must be YYYY-MM-DD")
    if not now - (WINDOW - 1) * ONE_DAY <= day <= now:
        raise Invalid(f"date must be within the last {WINDOW} days")
    return day


def streak(days: set[date], now: date) -> int:
    """Consecutive checked-in days ending today, or yesterday while today is still open."""
    run, prev = 0, None
    for day in sorted(days, reverse=True):
        if prev is None:
            if day < now - ONE_DAY:
                return 0
        elif prev.day - day.day != 1:
            break
        run, prev = run + 1, day
    return run


class HabitStore:
    def __init__(self) -> None:
        self._items: dict[int, dict] = {}
        self._next = 1
        self._lock = threading.Lock()

    def _view(self, habit: dict, now: date) -> dict:
        return {"id": habit["id"], "name": habit["name"],
                "days": sorted(d.isoformat() for d in habit["days"]),
                "streak": streak(habit["days"], now)}

    def list(self) -> dict:
        now = today()
        with self._lock:
            return {"today": now.isoformat(), "habits": [self._view(h, now) for h in self._items.values()]}

    def add(self, name: object) -> dict:
        habit = {"name": clean_name(name), "days": set()}
        with self._lock:
            habit["id"], self._next = self._next, self._next + 1
            self._items[habit["id"]] = habit
            return self._view(habit, today())

    def toggle(self, habit_id: int, value: object) -> dict:
        now = today()
        day = parse_day(value, now)
        with self._lock:
            habit = self._items.get(habit_id)
            if habit is None:
                raise NotFound(habit_id)
            habit["days"] ^= {day}
            return self._view(habit, now)
