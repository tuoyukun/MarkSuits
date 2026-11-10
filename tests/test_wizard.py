"""New-project wizard: which directories it takes, `/mark:init` as the first turn, registration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._support import fresh_home, make_repo
from tests.test_chat import FAKE

from mark import board, chat, home, wizard


class WizardTest(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home(self)
        self.parent = Path(tempfile.mkdtemp(prefix="mark-wiz-")).resolve()
        bindir = Path(tempfile.mkdtemp(prefix="mark-fake-"))
        claude = bindir / "claude"
        claude.write_text(FAKE.format(py=sys.executable))
        claude.chmod(0o755)
        self.calls = bindir / "calls.jsonl"
        patcher = mock.patch.dict(os.environ, {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
                                               "FAKE_ARGS": str(self.calls), "FAKE_CLAUDE": "reply"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def wait(self, wid):
        deadline = time.monotonic() + 10
        while chat.running(wizard.spot(wid), wizard.TICKET) and time.monotonic() < deadline:
            time.sleep(0.05)
        return [json.loads(line) for line in self.calls.read_text().splitlines()][-1]

    def test_which_directories_it_takes(self):
        f = self.parent / "file"
        f.write_text("x")
        mark_project = make_repo()
        for d, why in (("rel/app", "home.absolute"), (str(f), "home.notDir"), (str(self.parent / "a" / "b"), "home.noParent"),
                       (str(mark_project), "home.isMark"), (1, "bad request"), ("  ", "bad request")):
            self.assertEqual(wizard.target(d), (None, why), d)
        self.assertEqual(wizard.target(str(self.parent / "new") + "/"), (self.parent / "new", ""))
        self.assertEqual(wizard.target(str(self.parent)), (self.parent, ""))  # an existing repo without Mark
        self.assertEqual(wizard.start({"dir": str(self.parent / "new"), "text": " "})[:2], (False, "bad request"))
        self.assertFalse((self.parent / "new").exists())

    def test_first_turn_is_mark_init_in_the_new_directory_then_it_resumes(self):
        target = self.parent / "shop"
        ok, why, wid = wizard.start({"dir": str(target), "text": "A shop.\n--not an option"})
        self.assertEqual((ok, why), (True, ""))
        self.assertTrue(target.is_dir())
        first = self.wait(wid)
        self.assertEqual(first["stdin"], "/mark:init A shop.\n--not an option")
        self.assertEqual(first["argv"][first["argv"].index("--append-system-prompt") + 1], wizard.NOTE)
        self.assertEqual(first["argv"][first["argv"].index("--permission-mode") + 1], "auto")
        self.assertEqual(wizard.start({"dir": str(target), "text": "Yes."}), (True, "", wid))  # same dir: same wizard
        second = self.wait(wid)
        self.assertEqual(second["stdin"], "Yes.")
        self.assertIn("--resume", second["argv"])
        v = wizard.view(wid)
        self.assertEqual((v["dir"], v["project"]), (str(target), ""))
        self.assertEqual([m["who"] for m in v["messages"]][:2], ["human", "claude"])
        self.assertEqual([c["id"] for c in wizard.cards()], [wid])

    def test_a_picked_profile_leads_the_first_message(self):
        for req in ({"profile": "nope", "text": "x"}, {"profile": 1, "text": "x"}, {"profile": "", "text": " "}):
            self.assertEqual(wizard.start({"dir": str(self.parent / "a"), **req})[:2], (False, "bad request"), req)
        _, _, wid = wizard.start({"dir": str(self.parent / "a"), "profile": "service"})
        self.assertEqual(self.wait(wid)["stdin"], "/mark:init Profile: service")
        _, _, wid = wizard.start({"dir": str(self.parent / "b"), "profile": "mobile", "text": " Flutter. "})
        self.assertEqual(self.wait(wid)["stdin"], "/mark:init Profile: mobile\n\nFlutter.")

    def test_pick_dir(self):
        ok = mock.Mock(return_value=mock.Mock(returncode=0, stdout="/tmp/x/app/\n"))
        cancel = mock.Mock(return_value=mock.Mock(returncode=1, stdout=""))
        with mock.patch.object(wizard, "PICKABLE", True):
            self.assertEqual(wizard.pick_dir(ok), "/tmp/x/app/")
            self.assertEqual(wizard.pick_dir(cancel), "")
        with mock.patch.object(wizard, "PICKABLE", False):
            self.assertEqual(wizard.pick_dir(ok), "")

    def test_once_set_up_it_is_registered_and_leaves_the_home_page(self):
        target = self.parent / "shop"
        _, _, wid = wizard.start({"dir": str(target), "text": "A shop."})
        self.wait(wid)
        (target / ".mark").mkdir()
        (target / ".mark" / "config.toml").write_text('mark_schema = 1\n')
        pid = wizard.view(wid)["project"]
        self.assertEqual(pid, home.project_id(target))
        self.assertEqual(home.find(pid), target)
        self.assertEqual(wizard.cards(), [])

    def test_discard_forgets_the_wizard_but_never_the_directory(self):
        target = self.parent / "shop"
        _, _, wid = wizard.start({"dir": str(target), "text": "A shop."})
        self.wait(wid)
        self.assertTrue(wizard.discard(wid))
        self.assertIsNone(wizard.view(wid))
        self.assertTrue(target.is_dir())
        self.assertFalse(wizard.discard(wid))
        self.assertFalse(wizard.discard("../x"))

    def test_no_claude_says_so(self):
        with mock.patch("mark.runner.find_claude", return_value=None):
            ok, why, wid = wizard.start({"dir": str(self.parent / "shop"), "text": "A shop."})
        self.assertEqual((ok, why), (False, "chat.no-claude"))
        self.assertTrue(wid)  # the wizard is there to retry from


class WizardRouteTest(unittest.TestCase):
    """The wizard's endpoints need the board's cookie like every other write."""

    def setUp(self):
        fresh_home(self)
        from tests.test_board import DecideTest  # reuse its server plumbing

        self.t = DecideTest("test_bad_requests_are_refused")
        self.t.setUp()
        self.addCleanup(self.t.tearDown)
        self.addCleanup(self.t.doCleanups)

    def test_cookie_needed_and_unknown_wizards_404(self):
        d = str(Path(tempfile.mkdtemp(prefix="mark-wiz-")) / "app")
        with mock.patch.object(board.wizard, "send", return_value=(True, "")) as send:
            self.assertEqual(self.t.post("/api/wizard", {"dir": d, "text": "x"})[0], 403)
            self.assertFalse(Path(d).exists())
            cookie = self.t.login()
            code, res, _ = self.t.post("/api/wizard", {"dir": d, "text": "x"}, cookie=cookie)
            self.assertEqual(code, 200, res)
            send.assert_called_once_with(res["id"], "x")
            self.assertEqual(self.t.post(f"/api/wizard/{res['id']}/discard", {}, cookie=cookie)[0], 200)
        self.assertEqual(self.t._get("/api/wizard/0123456789"), b"not found")


if __name__ == "__main__":
    unittest.main()
