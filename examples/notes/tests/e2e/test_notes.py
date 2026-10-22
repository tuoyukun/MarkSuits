"""Notes API journeys, driven over HTTP like any client."""
import unittest

from e2e.client import call, clear


class NotesTest(unittest.TestCase):
    def setUp(self):
        clear()

    def test_create_read_and_list_a_note(self):
        # covers: baseline/create
        status, note = call("POST", "/api/notes", {"text": "  buy milk  "})
        self.assertEqual(status, 201)
        self.assertEqual(note["text"], "buy milk")
        self.assertEqual(call("GET", f"/api/notes/{note['id']}"), (200, note))
        self.assertEqual(call("GET", "/api/notes"), (200, [note]))

    def test_blank_text_is_refused(self):
        # covers: baseline/blank
        status, body = call("POST", "/api/notes", {"text": "   "})
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(call("GET", "/api/notes"), (200, []))

    def test_delete_removes_a_note(self):
        # covers: baseline/delete
        _, first = call("POST", "/api/notes", {"text": "one"})
        _, second = call("POST", "/api/notes", {"text": "two"})
        self.assertEqual(call("DELETE", f"/api/notes/{first['id']}"), (204, None))
        self.assertEqual(call("GET", f"/api/notes/{first['id']}")[0], 404)
        self.assertEqual(call("GET", "/api/notes"), (200, [second]))
