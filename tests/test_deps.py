"""The home page's setup checks and the fixed commands the board runs to fix them."""
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests._support import fresh_home

from mark import board, deps, model


def done(code=0, out=""):
    return subprocess.CompletedProcess([], code, out, "")


def fake_run(answers):
    """run() that answers by the command's first two words; unknown commands are missing (None)."""
    def run(cmd, timeout=20):
        key = " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd[:2]))
        return answers.get(key)
    return run


GOOD = {"python3 -c": done(out="3.13.1\n"), "xcode-select -p": done(out="/Library/Developer\n"),
        "git --version": done(out="git version 2.50.0\n"), "claude --version": done(out="2.1.300 (Claude Code)\n"),
        "claude auth": done()}


class ChecksTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        for p in (mock.patch("mark.runner.find_claude", return_value="/x/claude"),
                  mock.patch("mark.app.plugin_entry", return_value=("mark@marksuits", {"scope": "user", "version": "0.61.0"})),
                  mock.patch("mark.app.app_path", return_value=mock.Mock(is_dir=lambda: True))):
            p.start()
            self.addCleanup(p.stop)

    def by_id(self, answers, darwin=True):
        return {c["id"]: c for c in deps.checks(fake_run(answers), darwin=darwin)}

    def test_all_good(self):
        got = self.by_id(GOOD)
        self.assertTrue(all(c["ok"] and not c["fix"] for c in got.values()), got)
        self.assertEqual((got["python"]["detail"], got["git"]["detail"], got["claude"]["detail"], got["plugin"]["detail"]),
                         ("3.13.1", "2.50.0", "2.1.300", "0.61.0"))
        self.assertFalse(got["app"]["blocks"])
        self.assertNotIn("app", self.by_id(GOOD, darwin=False))

    def test_what_fails(self):
        got = self.by_id({**GOOD, "python3 -c": done(out="3.9.6\n"), "claude auth": done(1)})
        self.assertEqual((got["python"]["ok"], got["python"]["fix"], got["model"]["ok"], got["model"]["fix"]),
                         (False, False, False, False))

    def test_a_model_of_its_own_needs_no_sign_in(self):
        signed_out = {**GOOD, "claude auth": done(1)}
        self.assertFalse(self.by_id(signed_out)["model"]["ok"])
        ok, _ = model.save(None, {"name": "DeepSeek", "provider": "custom", "model": "deepseek-chat",
                                  "base_url": "https://api.deepseek.com/anthropic", "api_key": "k"})
        self.assertTrue(ok)
        got = self.by_id(signed_out)["model"]
        self.assertEqual((got["ok"], got["detail"]), (True, "DeepSeek"))

    def test_signed_in_shows_how(self):
        got = self.by_id({**GOOD, "claude auth": done(out='{"loggedIn": true, "authMethod": "claude.ai"}')})
        self.assertEqual((got["model"]["ok"], got["model"]["detail"]), (True, "claude.ai"))

    def test_no_command_line_tools_never_runs_the_git_stub(self):
        answers = {**GOOD, "xcode-select -p": done(2)}
        got = self.by_id(answers)
        self.assertEqual((got["git"]["ok"], got["git"]["fix"]), (False, True))

    def test_no_claude_no_plugin(self):
        with mock.patch("mark.runner.find_claude", return_value=None), \
                mock.patch("mark.app.plugin_entry", return_value=("mark@marksuits", {"scope": "project", "version": "1"})):
            got = self.by_id(GOOD)
        self.assertEqual([(c["id"], c["fix"]) for c in got.values() if not c["ok"]],
                         [("claude", True), ("model", False), ("plugin", False)])  # the plugin waits for claude


class FixTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        deps._job.clear()
        self.addCleanup(deps._job.clear)

    def test_only_fixed_commands(self):
        with mock.patch("mark.runner.find_claude", return_value="/a b/claude"):
            self.assertEqual(deps.fix_command("claude"), ["bash", "-c", deps.INSTALL_CLAUDE])
            self.assertIn("'/a b/claude' plugin install mark@marksuits --scope user", deps.fix_command("plugin")[2])
        for bad in ("model", "python", "rm -rf /", None, ["claude"]):
            self.assertIsNone(deps.fix_command(bad), bad)
        self.assertEqual(deps.start("model"), (False, "bad request"))

    def test_one_at_a_time_and_output_kept(self):
        cmd = [sys.executable, "-c", "import time; print('hello'); time.sleep(0.5)"]
        with mock.patch.object(deps, "fix_command", return_value=cmd):
            self.assertEqual(deps.start("claude"), (True, ""))
            self.assertEqual(deps.start("plugin"), (False, "deps.busy"))
            self.assertTrue(deps.job()["running"])
            deadline = time.monotonic() + 10
            while deps.job()["running"] and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual({k: deps.job()[k] for k in ("id", "running", "code", "tail")},
                         {"id": "claude", "running": False, "code": 0, "tail": "hello"})


class RouteTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        from tests.test_board import DecideTest  # reuse its server plumbing

        self.t = DecideTest("test_bad_requests_are_refused")
        self.t.setUp()
        self.addCleanup(self.t.tearDown)
        self.addCleanup(self.t.doCleanups)

    def test_read_open_fix_needs_the_cookie(self):
        with mock.patch.object(board.deps, "checks", return_value=[{"id": "claude", "ok": False}]):
            self.assertEqual(json.loads(self.t._get("/api/deps")), {"checks": [{"id": "claude", "ok": False}], "job": None})
        with mock.patch.object(board.deps, "start", return_value=(True, "")) as start:
            self.assertEqual(self.t.post("/api/deps/fix", {"id": "claude"})[0], 403)
            start.assert_not_called()
            code, res, _ = self.t.post("/api/deps/fix", {"id": "claude"}, cookie=self.t.login())
            self.assertEqual((code, res["ok"]), (200, True))
            start.assert_called_once_with("claude")


if __name__ == "__main__":
    unittest.main()
