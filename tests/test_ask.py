"""`mark ask`: choice questions for the board chat. A help, never a failure: bad input saves nothing, exit 0."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from tests._support import add_ticket, hook, make_repo

from mark import ask, chat, cli
from mark.config import load_config

GOOD = {"questions": [
    {"question": "Which format?", "header": "Format", "multiSelect": False,
     "options": [{"label": "CSV", "description": "opens in Excel"}, {"label": "JSON"}]},
    {"question": "Which platforms?", "header": "Platforms", "multiSelect": True,
     "options": [{"label": "web"}, {"label": "ios"}, {"label": "android"}]},
]}


class Tty(io.StringIO):
    def isatty(self):
        return True


class AskTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "drafting", gates=("ticket-approved",))
        self.cfg = load_config(self.root)

    def run_cli(self, *argv, stdin=""):
        out = io.StringIO()
        inp = stdin if isinstance(stdin, io.StringIO) else io.StringIO(stdin)
        code = cli.main(list(argv), cwd=self.root, out=out, err=out, inp=inp)
        return code, out.getvalue()

    def test_anything_wrong_saves_nothing_and_exits_0(self):
        for stdin in ["not json {", "[1]", '{"questions": [{"question": "x?", "options": [{"label": "only"}]}]}',
                      '{"questions": [{"options": [{"label": "a"}, {"label": "b"}]}]}', Tty(json.dumps(GOOD))]:
            code, out = self.run_cli("ask", "0001-a", stdin=stdin)
            self.assertEqual(code, 0, out)
            self.assertIn("as text instead", out)
            self.assertIsNone(ask.load(self.cfg, "0001-a"))

    def test_saves_the_valid_questions_under_the_full_id(self):
        data = {"questions": [*GOOD["questions"], {"question": "bad"},
                              {"question": "Too many?", "multiSelect": "yes",
                               "options": [{"label": str(i)} for i in range(6)]}]}
        code, out = self.run_cli("ask", "0001", stdin=json.dumps(data))
        self.assertEqual(code, 0, out)
        self.assertIn("3 question(s) saved (1 dropped)", out)
        qs = ask.load(self.cfg, "0001-a")["questions"]
        self.assertEqual([q["header"] for q in qs], ["Format", "Platforms", ""])
        self.assertEqual(qs[0]["options"][1], {"label": "JSON", "description": ""})
        self.assertTrue(qs[1]["multiSelect"])
        self.assertFalse(qs[2]["multiSelect"])  # only a real true is a multi-select
        self.assertEqual(len(qs[2]["options"]), ask.MAX_OPTIONS)

    def test_reads_a_file_when_the_heredoc_is_refused(self):
        f = Path(tempfile.mkdtemp()) / "q.json"
        f.write_text(json.dumps(GOOD))
        code, out = self.run_cli("ask", "0001-a", str(f), stdin=Tty(""))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(ask.load(self.cfg, "0001-a")["questions"]), 2)

    def test_unknown_ticket_and_bad_usage(self):
        self.assertNotEqual(self.run_cli("ask", "9999", stdin=json.dumps(GOOD))[0], 0)
        self.assertEqual(self.run_cli("ask", stdin=json.dumps(GOOD))[0], 2)

    def test_the_chat_shows_it_until_the_next_message(self):
        self.run_cli("ask", "0001-a", stdin=json.dumps(GOOD))
        self.assertEqual(chat.view(self.cfg, "0001-a")["ask"]["questions"][0]["question"], "Which format?")
        chat.start(self.cfg, "feature", "0001-a", "Format? → CSV", claude="true")
        self.assertIsNone(ask.load(self.cfg, "0001-a"))
        self.assertIn("mark ask", chat.BOARD_NOTE)

    def test_only_the_orchestrator_asks(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.root),
                   "tool_input": {"command": "mark ask 0001-a <<'EOF'\n{\"questions\": []}\nEOF"}}
        self.assertEqual(hook("pre-bash", payload)[0], 0)
        self.assertEqual(hook("pre-bash", {**payload, "agent_type": "mark:coder-impl"})[0], 2)


if __name__ == "__main__":
    unittest.main()
