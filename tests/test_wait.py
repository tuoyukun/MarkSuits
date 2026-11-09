"""`mark wait`: exits when the human decides, when replaced, or when its session is gone."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest

from tests._support import PLUGIN_ROOT, add_ticket, make_repo

from mark import board, cli, wait
from mark.config import load_config


def later(seconds, fn):
    threading.Timer(seconds, fn).start()


class WaitTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "review-plan", gates=("ticket-approved",))
        add_ticket(self.root, "feature", "0002-b", "drafting")
        add_ticket(self.root, "feature", "0003-c", "developing", gates=("ticket-approved",))
        self.cfg = load_config(self.root)

    def decide(self, body):
        ok, text = board.decide(self.cfg, body)
        self.assertTrue(ok, text)

    def test_a_decision_ends_the_wait(self):
        later(0.3, lambda: self.decide({"ticket": "0001-a", "verb": "approve"}))
        key, params = wait.run(self.cfg, "0001-a", poll=0.05)
        self.assertEqual((key, params["old"], params["new"]), ("wait.moved", "review-plan", "developing"))
        self.assertFalse(wait.path(self.cfg, "0001-a").exists())

    def test_approving_the_opening_ends_the_wait(self):
        later(0.3, lambda: self.decide({"ticket": "0002-b", "verb": "approve"}))
        key, params = wait.run(self.cfg, "0002-b", poll=0.05)
        self.assertEqual((key, params["new"]), ("wait.moved", "opening approved"))

    def test_a_ticket_that_does_not_wait_returns_at_once(self):
        self.assertEqual(wait.run(self.cfg, "0003-c", poll=0.05)[0], "wait.not_waiting")
        self.assertEqual(wait.run(self.cfg, "9999", poll=0.05)[0], "wait.not_waiting")

    def test_a_gone_session_ends_the_wait(self):
        ppids = iter([100, 100, 1])
        key, _ = wait.run(self.cfg, "0001-a", poll=0.01, parent=lambda: next(ppids, 1))
        self.assertEqual(key, "wait.orphaned")
        self.assertFalse(wait.path(self.cfg, "0001-a").exists())

    def test_a_new_waiter_replaces_the_old_one(self):
        mark = PLUGIN_ROOT / "bin" / "mark"
        first = subprocess.Popen([sys.executable, str(mark), "wait", "0001-a"], cwd=self.root,
                                 stdout=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if wait.waiter(self.cfg, "0001-a") == first.pid:
                    break
                time.sleep(0.05)
            self.assertEqual(wait.waiter(self.cfg, "0001-a"), first.pid)
            later(0.5, lambda: self.decide({"ticket": "0001-a", "verb": "approve"}))
            out = io.StringIO()
            self.assertEqual(cli.main(["wait", "0001-a"], cwd=self.root, out=out, err=io.StringIO()), 0)
            self.assertIn("review-plan -> developing", out.getvalue())
            self.assertIn("another session", first.communicate(timeout=10)[0])
        finally:
            if first.poll() is None:
                first.kill()
                first.wait()

    def test_stop(self):
        out = io.StringIO()
        cli.main(["wait", "0001-a", "--stop"], cwd=self.root, out=out, err=io.StringIO())
        self.assertIn("Nothing waits", out.getvalue())
        wait.path(self.cfg, "0001-a").parent.mkdir(parents=True, exist_ok=True)
        wait.path(self.cfg, "0001-a").write_text(json.dumps({"pid": os.getpid()}))
        self.assertEqual(wait.waiter(self.cfg, "0001-a"), os.getpid())


if __name__ == "__main__":
    unittest.main()
