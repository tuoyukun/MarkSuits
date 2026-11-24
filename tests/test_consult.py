"""Board consult: free talk, read-only, in a disposable worktree; one conversation, kept until a
new one starts."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import fresh_home, make_project, make_repo

from mark import chat, consult, runner
from mark.config import load_config
from mark.gitutil import git

FAKE = """#!{py}
import json, os, sys, time
calls = os.environ["FAKE_ARGS"]
with open(calls, "a") as fh:
    fh.write(json.dumps({{"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(),
                         "consult_root": os.environ.get("MARK_CONSULT_ROOT")}}) + "\\n")
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s-1"}}), flush=True)
if os.environ.get("FAKE_CLAUDE") == "sleep":
    time.sleep(30)
print(json.dumps({{"type": "assistant", "message": {{"content": [
    {{"type": "text", "text": "It reads the ticket state, then the plans."}}]}}}}), flush=True)
print(json.dumps({{"type": "result", "is_error": False, "result": "It reads the ticket state.", "session_id": "s-1",
                  "usage": {{"input_tokens": 1200, "cache_read_input_tokens": 300}}}}))
"""


class ConsultTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        self.root = make_repo()
        self.cfg = load_config(self.root)
        bindir = Path(tempfile.mkdtemp(prefix="mark-fake-"))
        self.claude = bindir / "claude"
        self.claude.write_text(FAKE.format(py=sys.executable))
        self.claude.chmod(0o755)
        self.calls = bindir / "calls.jsonl"
        env = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_ARGS": str(self.calls)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(consult.discard, self.cfg)

    def turn(self, text, mode="reply"):
        os.environ["FAKE_CLAUDE"] = mode
        self.assertEqual(consult.send(self.cfg, text), (True, ""))
        self.wait_dead()
        return [json.loads(line) for line in self.calls.read_text().splitlines()][-1]

    def wait_dead(self):
        deadline = time.monotonic() + 10
        while chat.running(self.cfg, consult.ID) and time.monotonic() < deadline:
            time.sleep(0.05)

    def opts(self, call, name):
        argv = call["argv"]
        return argv[argv.index(name) + 1]

    def test_a_visit_gets_a_read_only_sandbox_and_a_fresh_session(self):
        self.assertTrue(consult.reset(self.cfg)["sandbox"])
        wt = consult.worktree(self.cfg)
        self.assertTrue((wt / ".mark" / "config.toml").is_file())
        call = self.turn("How does the flow work?")
        self.assertEqual(call["stdin"], "How does the flow work?")  # raw text, not a /mark: skill
        self.assertNotIn("--resume", call["argv"])
        self.assertEqual(self.opts(call, "--tools"), "Read,Grep,Glob,Bash")
        self.assertEqual(self.opts(call, "--permission-mode"), "bypassPermissions")
        self.assertEqual(self.opts(call, "--mcp-config"), consult.NO_MCP)
        self.assertIn("--strict-mcp-config", call["argv"])
        self.assertEqual(call["cwd"], str(wt))
        self.assertEqual(call["consult_root"], str(wt))
        note = self.opts(call, "--append-system-prompt")
        self.assertIn("read-only consultation", note)
        self.assertIn("disposable copy", note)

    def test_the_visit_carries_on_in_one_session(self):
        consult.reset(self.cfg)
        self.turn("First question.")
        call = self.turn("And then?")
        self.assertEqual(self.opts(call, "--resume"), "s-1")
        self.assertEqual(call["stdin"], "And then?")

    def test_entering_again_keeps_the_conversation_and_the_sandbox(self):
        consult.reset(self.cfg)
        self.turn("First question.")
        log = chat.log_path(self.cfg, consult.ID).read_text()
        pinned = chat.settings_path(self.cfg, consult.ID).read_text()
        wt = consult.worktree(self.cfg)
        (wt / "scratch.txt").write_text("x")
        self.assertTrue(consult.prepare(self.cfg)["sandbox"])
        self.assertEqual(chat.log_path(self.cfg, consult.ID).read_text(), log)
        self.assertEqual(chat.settings_path(self.cfg, consult.ID).read_text(), pinned)
        self.assertEqual((wt / "scratch.txt").read_text(), "x")  # the same sandbox, not a new one
        call = self.turn("And then?")
        self.assertEqual(self.opts(call, "--resume"), "s-1")

    def test_prepare_cuts_the_first_sandbox_and_leaves_the_conversation_empty(self):
        self.assertTrue(consult.prepare(self.cfg)["sandbox"])
        self.assertTrue(consult.worktree(self.cfg).is_dir())
        self.assertFalse(chat.log_path(self.cfg, consult.ID).exists())
        call = self.turn("How does the flow work?")
        self.assertNotIn("--resume", call["argv"])

    def test_prepare_recuts_a_missing_sandbox_and_keeps_the_conversation(self):
        consult.reset(self.cfg)
        self.turn("First question.")
        consult._remove(self.cfg)  # the sandbox is gone; the conversation is not
        self.assertFalse(consult.worktree(self.cfg).exists())
        self.assertTrue(consult.prepare(self.cfg)["sandbox"])
        self.assertTrue(consult.worktree(self.cfg).is_dir())
        call = self.turn("And then?")
        self.assertEqual(self.opts(call, "--resume"), "s-1")

    def test_reset_drops_the_conversation_the_model_and_the_sandbox(self):
        consult.reset(self.cfg)
        self.turn("First question.")
        wt = consult.worktree(self.cfg)
        (wt / "scratch.txt").write_text("x")
        self.assertFalse((self.root / "scratch.txt").exists())  # the real checkout is untouched
        self.assertTrue(chat.settings_path(self.cfg, consult.ID).is_file())
        self.assertTrue(consult.reset(self.cfg)["sandbox"])
        self.assertFalse(chat.log_path(self.cfg, consult.ID).exists())
        self.assertFalse(chat.settings_path(self.cfg, consult.ID).exists())
        self.assertFalse((wt / "scratch.txt").exists())  # a fresh worktree, not the old one
        call = self.turn("A new question.")
        self.assertNotIn("--resume", call["argv"])

    def test_reset_stops_a_running_turn(self):
        consult.reset(self.cfg)
        os.environ["FAKE_CLAUDE"] = "sleep"
        self.assertEqual(consult.send(self.cfg, "Think slowly."), (True, ""))
        pid = chat.running(self.cfg, consult.ID)
        self.assertIsNotNone(pid)
        consult.reset(self.cfg)
        self.assertIsNone(chat.running(self.cfg, consult.ID))
        deadline = time.monotonic() + 10
        while runner._alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(runner._alive(pid))

    def test_one_turn_at_a_time(self):
        consult.reset(self.cfg)
        os.environ["FAKE_CLAUDE"] = "sleep"
        self.assertEqual(consult.send(self.cfg, "Think slowly."), (True, ""))
        self.assertEqual(consult.send(self.cfg, "Again."), (False, "chat.busy"))
        pid = chat.running(self.cfg, consult.ID)
        self.assertTrue(consult.stop(self.cfg))
        deadline = time.monotonic() + 10
        while runner._alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)

    def test_the_view_is_the_conversation_and_its_context(self):
        consult.reset(self.cfg)
        self.turn("How does the flow work?")
        view = consult.view(self.cfg)
        self.assertTrue(view["sandbox"])
        self.assertFalse(view["running"])
        self.assertEqual(view["tokens"], 1500)
        self.assertEqual([m["who"] for m in view["messages"]], ["human", "claude"])
        self.assertIn("ticket state", view["messages"][1]["text"])
        self.assertTrue(view["model"])

    def test_bad_text(self):
        consult.reset(self.cfg)
        self.assertEqual(consult.send(self.cfg, "   "), (False, "bad request"))
        self.assertEqual(consult.send(self.cfg, "x" * (chat.TEXT_MAX + 1)), (False, "bad request"))
        self.assertEqual(consult.send(self.cfg, None), (False, "bad request"))

    def test_no_claude(self):
        consult.reset(self.cfg)
        with mock.patch("mark.runner.find_claude", return_value=None):
            self.assertEqual(consult.send(self.cfg, "hi"), (False, "chat.no-claude"))

    def test_a_repository_with_no_commit_falls_back_to_read_only_tools(self):
        root = make_project()
        cfg = load_config(root)
        self.addCleanup(consult.discard, cfg)
        self.assertFalse(consult.reset(cfg)["sandbox"])
        os.environ["FAKE_CLAUDE"] = "reply"
        self.assertEqual(consult.send(cfg, "How is it structured?"), (True, ""))
        deadline = time.monotonic() + 10
        while chat.running(cfg, consult.ID) and time.monotonic() < deadline:
            time.sleep(0.05)
        call = [json.loads(line) for line in self.calls.read_text().splitlines()][-1]
        self.assertEqual(self.opts(call, "--tools"), "Read,Grep,Glob")
        self.assertEqual(self.opts(call, "--permission-mode"), "dontAsk")
        self.assertEqual(call["cwd"], str(cfg.root.resolve()))
        self.assertIsNone(call["consult_root"])
        self.assertIn("no shell", self.opts(call, "--append-system-prompt"))

    def test_the_sandbox_is_a_worktree_at_head(self):
        consult.reset(self.cfg)
        wt = consult.worktree(self.cfg)
        self.assertEqual(git(["rev-parse", "HEAD"], wt)[0], 0)
        listed = git(["worktree", "list", "--porcelain"], self.root)[1]
        self.assertIn(str(wt), listed)
        consult.discard(self.cfg)
        self.assertFalse(wt.exists())
        self.assertNotIn(str(wt), git(["worktree", "list", "--porcelain"], self.root)[1])
