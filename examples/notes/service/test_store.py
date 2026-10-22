"""Unit tests for the store and the routes (real server on a free port)."""
import json
import threading
import unittest
import urllib.error
import urllib.request

from server import make_server
from store import Invalid, NotFound, NoteStore, clean_text


class StoreTest(unittest.TestCase):
    def test_add_list_get_delete(self):
        s = NoteStore()
        a = s.add("  first  ")
        self.assertEqual(a, {"id": 1, "text": "first"})
        self.assertEqual(s.get(1), a)
        self.assertEqual(s.list(), [a])
        s.delete(1)
        self.assertEqual(s.list(), [])
        with self.assertRaises(NotFound):
            s.get(1)

    def test_text_is_validated(self):
        for bad in (None, 3, "", "   ", "x" * 1001):
            with self.assertRaises(Invalid):
                clean_text(bad)


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            with err:
                return err.code, json.loads(err.read())

    def test_create_and_errors(self):
        self.assertEqual(self.call("POST", "/api/notes", {"text": "hi"}), (201, {"id": 1, "text": "hi"}))
        self.assertEqual(self.call("POST", "/api/notes", {"text": " "})[0], 400)
        self.assertEqual(self.call("GET", "/api/notes/9")[0], 404)
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)
        self.assertEqual(self.call("DELETE", "/api/notes/1"), (204, None))


if __name__ == "__main__":
    unittest.main()
