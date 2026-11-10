"""Headless runner: started after a board decision only when no session waits; its outcome."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import add_ticket, make_repo

from mark import board, model, runner
from mark.config import load_config

FAKE = """#!{py}
import json, os, sys, time
open(os.environ["FAKE_ARGS"], "w").write(json.dumps({{"argv": sys.argv[1:], "nested": os.environ.get("CLAUDECODE"), "path": os.environ["PATH"]}}))
mode = os.environ.get("FAKE_CLAUDE", "done")
print(json.dumps({{"type": "assistant", "message": {{"content": [
    {{"type": "tool_use", "name": "Bash", "input": {{"command": "mark next 0001-a"}}}},
    {{"type": "tool_use", "name": "Agent", "input": {{"subagent_type": "mark:coder-impl", "description": "Implement 0001"}}}}]}}}}), flush=True)
if mode == "sleep":
    time.sleep(30)
res = {{"type": "result", "is_error": mode == "error", "result": "Stopped at review-plan."}}
if mode == "blocked":
    res["permission_denials"] = [{{"tool_name": "Bash", "tool_input": {{"command": "npm test"}}}}]
print(json.dumps(res))
"""


def wait_dead(cfg, seconds=10):
    deadline = time.monotonic() + seconds
    while runner.running(cfg) and time.monotonic() < deadline:
        time.sleep(0.05)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "review-plan", gates=("ticket-approved",))
        add_ticket(self.root, "feature", "0002-b", "drafting")
        self.cfg = load_config(self.root)
        bindir = Path(tempfile.mkdtemp(prefix="mark-fake-"))
        (bindir / "claude").write_text(FAKE.format(py=sys.executable))
        (bindir / "claude").chmod(0o755)
        self.args = bindir / "args.json"
        env = {"PATH": f"/x/.claude/plugins/cache/m/mark/0.1.0/bin{os.pathsep}{bindir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_ARGS": str(self.args), "CLAUDECODE": "1"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(runner.stop, self.cfg)

    def run_once(self, mode="done"):
        os.environ["FAKE_CLAUDE"] = mode
        self.assertEqual(runner.start(self.cfg, "0001-a"), (True, ""))
        wait_dead(self.cfg)
        return runner.view(self.cfg)

    def test_a_clean_run_stops_at_the_next_gate(self):
        v = self.run_once()
        self.assertEqual((v["kind"], v["ticket"]), ("done", "0001-a"))
        self.assertEqual(v["lines"], ["$ mark next 0001-a", "agent mark:coder-impl: Implement 0001"])
        args = json.loads(self.args.read_text())
        self.assertEqual(args["argv"][:4], ["-p", "/mark:continue 0001-a", "--permission-mode", "auto"])
        self.assertIsNone(args["nested"])  # not a session nested in the one that started the board
        self.assertNotIn("/.claude/plugins/", args["path"])  # nor running that session's (maybe older) mark

    def test_a_run_uses_the_model_set_when_it_starts(self):
        self.assertEqual(self.run_once()["model"], "opus")
        self.assertIn("--model=opus", json.loads(self.args.read_text())["argv"])
        model.save(self.cfg, {"provider": "anthropic", "model": "sonnet"})
        v = self.run_once()
        self.assertIn("--model=sonnet", json.loads(self.args.read_text())["argv"])
        self.assertEqual(v["model"], "sonnet")

    def test_denials_and_errors(self):
        v = self.run_once("blocked")
        self.assertEqual((v["kind"], v["commands"]), ("blocked", ["npm test"]))
        self.assertEqual(self.run_once("error")["kind"], "failed")
        self.assertEqual(runner.outcome(None, False)["kind"], "failed")
        waited = {"type": "result", "result": "Waiting.", "permission_denials": [
            {"tool_name": "Bash", "tool_input": {"command": "mark wait 0001-a"}}]}
        self.assertEqual(runner.outcome(waited, False)["kind"], "done")  # wait_guard's refusal is not a permission

    def test_one_runner_per_project_and_stop(self):
        os.environ["FAKE_CLAUDE"] = "sleep"
        self.assertTrue(runner.start(self.cfg, "0001-a")[0])
        self.assertEqual(runner.start(self.cfg, "0001-a"), (False, "busy"))
        self.assertEqual(runner.view(self.cfg)["kind"], "running")
        self.assertTrue(runner.stop(self.cfg))
        wait_dead(self.cfg)
        self.assertIsNone(runner.running(self.cfg))

    def test_no_claude(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(runner.start(self.cfg, "0001-a"), (False, "no-claude"))

    def test_carry_on_after_a_decision(self):
        review, opening = {"kind": "review"}, {"kind": "opening"}
        self.assertEqual(board.carry_on(self.cfg, "0001-a", review, had_waiter=True), "run.session")
        self.assertEqual(board.carry_on(self.cfg, "0002-b", opening, had_waiter=False), "run.terminal")
        os.environ["FAKE_CLAUDE"] = "done"
        self.assertEqual(board.carry_on(self.cfg, "0001-a", review, had_waiter=False), "run.started")
        wait_dead(self.cfg)

    def test_run_off(self):
        cfg_path = self.root / ".mark" / "config.toml"
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8") + '\n[board]\nrun = "off"\n', encoding="utf-8")
        cfg = load_config(self.root)
        self.assertEqual(board.carry_on(cfg, "0001-a", {"kind": "review"}, had_waiter=False), "run.terminal")
        self.assertIsNone(runner.read(cfg).get("pid"))



if __name__ == "__main__":
    unittest.main()
