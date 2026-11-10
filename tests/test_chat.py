"""Board chat: one headless turn per message, resuming one session; what the board shows of it."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import add_ticket, fresh_home, make_repo

from mark import chat, model, runner
from mark.config import load_config

FAKE = """#!{py}
import json, os, sys, time
calls = os.environ["FAKE_ARGS"]
with open(calls, "a") as fh:
    fh.write(json.dumps({{"argv": sys.argv[1:], "stdin": sys.stdin.read(), "nested": os.environ.get("CLAUDECODE"),
                         "base": os.environ.get("ANTHROPIC_BASE_URL")}}) + "\\n")
mode = os.environ.get("FAKE_CLAUDE", "reply")
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s-1"}}), flush=True)
if mode == "die":
    sys.exit(1)
print(json.dumps({{"type": "assistant", "message": {{"content": [
    {{"type": "text", "text": "Which date format?"}},
    {{"type": "tool_use", "name": "Bash", "input": {{"command": "mark next 0001-a"}}}}]}}}}), flush=True)
if mode == "sleep":
    time.sleep(30)
print(json.dumps({{"type": "result", "is_error": False, "result": "Which date format?", "session_id": "s-1"}}))
"""


class ChatTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "drafting", gates=("ticket-approved",))
        self.cfg = load_config(self.root)
        bindir = Path(tempfile.mkdtemp(prefix="mark-fake-"))
        self.claude = bindir / "claude"
        self.claude.write_text(FAKE.format(py=sys.executable))
        self.claude.chmod(0o755)
        self.calls = bindir / "calls.jsonl"
        env = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_ARGS": str(self.calls), "CLAUDECODE": "1"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(chat.stop, self.cfg, "0001-a")

    def turn(self, text, mode="reply"):
        os.environ["FAKE_CLAUDE"] = mode
        self.assertEqual(chat.start(self.cfg, "feature", "0001-a", text), (True, ""))
        deadline = time.monotonic() + 10
        while chat.running(self.cfg, "0001-a") and time.monotonic() < deadline:
            time.sleep(0.05)
        return [json.loads(line) for line in self.calls.read_text().splitlines()][-1]

    def test_the_first_turn_opens_the_skill_and_later_ones_resume_it(self):
        first = self.turn("Due dates on todos.\n--not an option")
        self.assertEqual(first["stdin"], "/mark:feature 0001-a\n\nDue dates on todos.\n--not an option")
        self.assertNotIn("--resume", first["argv"])
        self.assertIn("--append-system-prompt", first["argv"])
        self.assertIsNone(first["nested"])  # a session of its own, not nested in the board's
        second = self.turn("ISO dates.")
        self.assertEqual(second["stdin"], "ISO dates.")
        self.assertEqual(second["argv"][second["argv"].index("--resume") + 1], "s-1")

    def test_a_chat_keeps_the_model_it_started_with(self):
        first = self.turn("Due dates.")
        self.assertIn("--model=opus", first["argv"])
        model.save(self.cfg, {"provider": "custom", "model": "deepseek-chat",
                              "base_url": "https://api.deepseek.com/anthropic", "api_key": "k"})
        second = self.turn("ISO dates.")  # resumes the conversation in progress
        self.assertIn("--model=opus", second["argv"])
        self.assertIsNone(second["base"])
        self.assertEqual(chat.view(self.cfg, "0001-a")["model"], "opus")
        add_ticket(self.root, "feature", "0002-b", "drafting", gates=("ticket-approved",))
        os.environ["FAKE_CLAUDE"] = "reply"
        self.assertEqual(chat.start(self.cfg, "feature", "0002-b", "Tags."), (True, ""))
        deadline = time.monotonic() + 10
        while chat.running(self.cfg, "0002-b") and time.monotonic() < deadline:
            time.sleep(0.05)
        new = [json.loads(line) for line in self.calls.read_text().splitlines()][-1]
        self.assertIn("--model=deepseek-chat", new["argv"])
        self.assertEqual(new["base"], "https://api.deepseek.com/anthropic")

    def test_the_view_is_the_conversation(self):
        self.turn("Due dates.")
        v = chat.view(self.cfg, "0001-a")
        self.assertFalse(v["running"])
        self.assertEqual(v["messages"], [{"who": "human", "text": "Due dates."},
                                         {"who": "claude", "text": "Which date format?"},
                                         {"who": "step", "text": "$ mark next 0001-a"}])

    def test_the_unknown_model_warning_is_not_an_error(self):
        self.turn("Due dates.")
        log = chat.log_path(self.cfg, "0001-a")
        log.write_text('[claude-code:unrecognized_model] {"model":"deepseek-flash[1m]"}\nboom\n' + log.read_text())
        errors = [m["text"] for m in chat.view(self.cfg, "0001-a")["messages"] if m["who"] == "error"]
        self.assertEqual(errors, ["boom"])

    def test_a_turn_that_dies_says_so(self):
        self.turn("Due dates.", mode="die")
        self.assertEqual(chat.view(self.cfg, "0001-a")["messages"][-1]["who"], "error")

    def test_one_turn_at_a_time_and_stop(self):
        os.environ["FAKE_CLAUDE"] = "sleep"
        self.assertTrue(chat.start(self.cfg, "feature", "0001-a", "one")[0])
        self.assertEqual(chat.start(self.cfg, "feature", "0001-a", "two"), (False, "busy"))
        self.assertTrue(chat.view(self.cfg, "0001-a")["running"])
        self.assertTrue(chat.stop(self.cfg, "0001-a"))

    def test_not_while_the_runner_carries_the_ticket_on(self):
        with mock.patch.object(runner, "running", return_value={"ticket": "0001-a"}):
            self.assertEqual(chat.start(self.cfg, "feature", "0001-a", "hi"), (False, "busy"))

    def test_bugs_open_the_fix_skill(self):
        self.assertTrue(chat.prompt("bug", "b0001-x", "Crash.", first=True).startswith("/mark:fix b0001-x\n\n"))

    def test_no_claude(self):
        with mock.patch("mark.runner.find_claude", return_value=None):
            self.assertEqual(chat.start(self.cfg, "feature", "0001-a", "hi"), (False, "no-claude"))


if __name__ == "__main__":
    unittest.main()
