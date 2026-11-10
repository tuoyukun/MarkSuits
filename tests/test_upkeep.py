"""The board's own updates: the plugin (Updater), upgrade lanes per project, merging them."""
from __future__ import annotations

import json
import os
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests._support import fresh_home, make_repo, sh

from mark import board, home, scaffold, upkeep
from mark.config import load_config
from mark.flow import FlowError


def wait_for(cond, timeout=5.0):
    ev = threading.Event()
    for _ in range(int(timeout / 0.02)):
        if cond():
            return True
        ev.wait(0.02)
    return False


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.touched = 0
        self.u = upkeep.Updater(self.touch)

    def touch(self):
        self.touched += 1

    def plugin(self, version):
        root = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        (root / "bin").mkdir()
        (root / "bin" / "mark").write_text("", encoding="utf-8")
        return ("mark@m", {"version": version, "installPath": str(root)}), root

    def test_poll_reports_a_published_version_once(self):
        stop = threading.Event()
        stop.set()  # one round
        self.u.poll(stop, check=lambda every: ("m", "9.9.9"))
        self.assertEqual((self.u.view()["latest"], self.touched), ("9.9.9", 1))
        self.u.poll(stop, check=lambda every: ("m", "9.9.9"))
        self.assertEqual(self.touched, 1)

    def test_start_refuses_while_busy_or_running(self):
        self.assertEqual(self.u.start(True, lambda: None, run=lambda s: None), (False, "update.busy"))
        self.assertEqual(self.u.start(False, lambda: None, run=lambda s: None), (True, ""))
        self.assertEqual(self.u.start(False, lambda: None, run=lambda s: None), (False, "update.running"))

    def test_a_newer_install_restarts_the_board_on_it(self):
        entry, root = self.plugin("999.0.0")
        down = []
        with mock.patch.object(upkeep.app, "plugin_entry", return_value=entry), \
                mock.patch.object(upkeep.app, "app_path", return_value=root / "none.app"):
            self.u.run(lambda: down.append(1), update=lambda: ("app.updated", {"old": "1", "new": "999.0.0"}))
        self.assertEqual((self.u.restart, down), (root / "bin" / "mark", [1]))

    def test_no_newer_install_fails_without_restarting(self):
        entry, _ = self.plugin(scaffold.version())
        down = []
        with mock.patch.object(upkeep.app, "plugin_entry", return_value=entry):
            self.u.run(lambda: down.append(1), update=lambda: ("app.update_failed", {"error": "boom"}))
        self.assertEqual((self.u.restart, down, self.u.state), (None, [], "failed"))
        self.assertIn("boom", self.u.error)


def upgrade_lane(root: Path, stamp="20260101-120000", conflict=False) -> str:
    branch = f"chore/general-{stamp}"
    sh(root, "git", "checkout", "-q", "-b", branch)
    (root / "CLAUDE.md").write_text("<<<<<<< project\na\n=======\nb\n>>>>>>> template\n" if conflict else "new\n", encoding="utf-8")
    sh(root, "git", "add", "-A")
    sh(root, "git", "commit", "-q", "-m", "chore: upgrade Mark v0.1.0 -> v0.2.0")
    sh(root, "git", "checkout", "-q", "main")
    return branch


class LaneTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        self.root = make_repo()
        self.cfg = load_config(self.root)

    def test_an_upgrade_lane_is_flagged_with_its_conflicts(self):
        upgrade_lane(self.root, conflict=True)
        lane = board.general_lanes(self.cfg)[0]
        self.assertEqual((lane["upgrade"], lane["conflicts"], lane["side"]), (True, ["CLAUDE.md"], "human"))

    def test_a_plain_general_lane_is_not_an_upgrade(self):
        sh(self.root, "git", "checkout", "-q", "-b", "chore/general-20260101-130000")
        (self.root / "notes.md").write_text("x\n", encoding="utf-8")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "-m", "Tidy")
        sh(self.root, "git", "checkout", "-q", "main")
        self.assertNotIn("upgrade", board.general_lanes(self.cfg)[0])
        ok, _ = upkeep.lane_action(self.cfg, {"branch": "chore/general-20260101-130000", "verb": "drop"},
                                   board.general_lanes, lambda: None)
        self.assertFalse(ok)  # the board only lands upgrade lanes

    def test_drop_removes_the_lane(self):
        branch = upgrade_lane(self.root)
        self.assertEqual(upkeep.lane_action(self.cfg, {"branch": branch, "verb": "drop"}, board.general_lanes, lambda: None), (True, ""))
        self.assertEqual(board.general_lanes(self.cfg), [])

    def test_a_failed_merge_is_kept_for_the_page(self):
        branch = upgrade_lane(self.root, stamp="20260101-140000")
        def merge(cfg, b):
            raise FlowError("general.empty", branch=b)
        ok, _ = upkeep.lane_action(self.cfg, {"branch": branch, "verb": "merge"}, board.general_lanes, lambda: None, merge=merge)
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: (upkeep.job(self.cfg, branch) or {}).get("state") == "failed"))
        self.assertIn(branch, upkeep.job(self.cfg, branch)["error"])


class OpenLanesTest(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home(self)
        self.root = make_repo()
        home.add(self.root)
        self.runs = []
        self.enterContext(mock.patch.object(upkeep.upgrade, "stale", return_value="0.1.0"))
        self.enterContext(mock.patch.object(upkeep.upgrade, "run", side_effect=lambda cfg: self.runs.append(cfg.root)))

    def test_once_per_version(self):
        upkeep.open_lanes(lambda: None, lambda cfg: [])
        upkeep.open_lanes(lambda: None, lambda cfg: [])
        self.assertEqual(self.runs, [self.root])
        done = json.loads((self.home / upkeep.LANES_FILE).read_text())
        self.assertEqual(list(done.values()), [scaffold.version()])

    def test_an_open_upgrade_lane_blocks_another(self):
        upkeep.open_lanes(lambda: None, lambda cfg: [{"upgrade": True}])
        self.assertEqual(self.runs, [])


class SecretTest(unittest.TestCase):
    def test_a_restart_hands_the_secret_over_a_pipe(self):
        r, w = os.pipe()
        os.write(w, b"s3cret")
        os.close(w)
        with mock.patch.dict(os.environ, {board.SECRET_FD_ENV: str(r)}):
            self.assertEqual(board._handed_secret(), "s3cret")
            self.assertNotIn(board.SECRET_FD_ENV, os.environ)
        self.assertEqual(board._handed_secret(), "")


if __name__ == "__main__":
    unittest.main()
