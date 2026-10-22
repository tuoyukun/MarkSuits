import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from unittest import mock

from server import make_server
from store import HabitStore, Invalid, NotFound, streak

D = date.fromisoformat


class StreakTest(unittest.TestCase):
    def test_runs_end_today_or_yesterday(self):
        now = D("2026-06-10")
        self.assertEqual(streak({D("2026-06-10"), D("2026-06-09"), D("2026-06-08")}, now), 3)
        self.assertEqual(streak({D("2026-06-09"), D("2026-06-08")}, now), 2)
        self.assertEqual(streak({D("2026-06-08")}, now), 0)
        self.assertEqual(streak(set(), now), 0)

    def test_a_gap_ends_the_run(self):
        now = D("2026-06-10")
        self.assertEqual(streak({D("2026-06-10"), D("2026-06-08"), D("2026-06-07")}, now), 1)


@mock.patch.dict(os.environ, {"HABITS_TODAY": "2026-06-10"})
class StoreTest(unittest.TestCase):
    def test_add_and_toggle(self):
        store = HabitStore()
        habit = store.add("  Read ")
        self.assertEqual(habit, {"id": 1, "name": "Read", "days": [], "streak": 0})
        self.assertEqual(store.toggle(1, "2026-06-10")["streak"], 1)
        self.assertEqual(store.toggle(1, "2026-06-10")["days"], [])
        self.assertEqual(store.list()["today"], "2026-06-10")

    def test_invalid_input(self):
        store = HabitStore()
        for name in ("", "  ", 3, "x" * 61):
            with self.assertRaises(Invalid):
                store.add(name)
        store.add("Run")
        for day in ("2026-06-11", "2026-06-03", "June 1", None):
            with self.assertRaises(Invalid):
                store.toggle(1, day)
        with self.assertRaises(NotFound):
            store.toggle(9, "2026-06-10")


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_routes(self):
        self.assertEqual(self.call("POST", "/api/habits", {"name": "Read"})[0], 201)
        today = self.call("GET", "/api/habits")[1]["today"]
        status, habit = self.call("POST", "/api/habits/1/toggle", {"date": today})
        self.assertEqual((status, habit["streak"]), (200, 1))
        self.assertEqual(self.call("POST", "/api/habits", {"name": ""})[0], 400)
        self.assertEqual(self.call("POST", "/api/habits/7/toggle", {"date": today})[0], 404)
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
