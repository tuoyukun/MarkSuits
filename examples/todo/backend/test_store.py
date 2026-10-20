import json
import threading
import unittest
import urllib.error
import urllib.request

from store import Invalid, NotFound, TodoStore, clean_title
from server import make_server


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = TodoStore()

    def test_add_assigns_ids_and_starts_active(self):
        a = self.store.add("Buy milk")
        b = self.store.add("Walk dog")
        self.assertEqual((a["id"], b["id"]), (1, 2))
        self.assertFalse(a["done"])
        self.assertEqual([t["title"] for t in self.store.list()], ["Buy milk", "Walk dog"])

    def test_title_is_trimmed_and_validated(self):
        self.assertEqual(clean_title("  a   b "), "a b")
        for bad in ("", "   ", None, 3, "x" * 201):
            with self.assertRaises(Invalid):
                clean_title(bad)

    def test_rename(self):
        todo = self.store.add("Buy milk")
        self.store.update(todo["id"], {"title": "Buy oat milk"})
        self.assertEqual(self.store.list()[0]["title"], "Buy oat milk")

    def test_update_rejects_non_bool_done(self):
        todo = self.store.add("x")
        with self.assertRaises(Invalid):
            self.store.update(todo["id"], {"done": "yes"})

    def test_delete_and_missing(self):
        todo = self.store.add("x")
        self.store.delete(todo["id"])
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(NotFound):
            self.store.delete(todo["id"])

    def test_list_returns_copies(self):
        self.store.add("x")
        self.store.list()[0]["title"] = "changed"
        self.assertEqual(self.store.list()[0]["title"], "x")


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_crud(self):
        status, todo = self.call("POST", "/api/todos", {"title": "Buy milk"})
        self.assertEqual((status, todo["title"]), (201, "Buy milk"))
        self.assertEqual(self.call("GET", "/api/todos")[1], [todo])
        self.assertEqual(self.call("DELETE", f"/api/todos/{todo['id']}"), (204, None))
        self.assertEqual(self.call("GET", "/api/todos")[1], [])

    def test_errors(self):
        self.assertEqual(self.call("POST", "/api/todos", {"title": " "})[0], 400)
        self.assertEqual(self.call("PATCH", "/api/todos/99", {"done": True})[0], 404)
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)

    def test_serves_frontend(self):
        with urllib.request.urlopen(self.base + "/") as resp:
            self.assertIn(b"<title>Todo</title>", resp.read())


if __name__ == "__main__":
    unittest.main()
