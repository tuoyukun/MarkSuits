"""Web board: history from git, files from main + worktree, the HTTP surface, start/stop."""
from __future__ import annotations

import http.client
import io
import json
import socket
import threading
import unittest

from tests._support import add_ticket, add_worktree, make_repo, sh, status_text

from mark import board, cli
from mark.config import load_config


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def move(root, ticket_id, status, note="", **fields):
    d = root / ".mark" / "features" / ticket_id
    (d / "status.md").write_text(status_text(status, **fields) + (f"\n{note}\n" if note else ""), encoding="utf-8")
    sh(root, "git", "add", "-A")
    sh(root, "git", "commit", "-q", "-m", f"{ticket_id}: {status}")


class HistoryTest(unittest.TestCase):
    def test_every_status_commit_is_a_move_and_unchanged_fields_carry_over(self):
        root = make_repo()
        add_ticket(root, "feature", "0001-a", "drafting", owner="orchestrator")
        move(root, "0001-a", "drafting", "only the note changed", owner="orchestrator")
        move(root, "0001-a", "review-requirement", "ready", owner="human")
        move(root, "0001-a", "designing", owner="designer")  # note removed
        cfg = load_config(root)
        snap = board.snapshot(cfg, board.History(cfg))
        hist = snap["tickets"][0]["history"]
        self.assertEqual([h["status"] for h in hist], ["drafting", "review-requirement", "designing"])
        self.assertEqual([h["owner"] for h in hist], ["orchestrator", "human", "designer"])
        self.assertEqual({h["updater"] for h in hist}, {"orchestrator"})  # set once, never changed
        self.assertEqual([h["note"] for h in hist], ["", "ready", ""])
        self.assertTrue(all(len(h["sha"]) == 7 for h in hist))

    def test_an_uncommitted_move_shows_without_a_commit(self):
        root = make_repo()
        add_ticket(root, "feature", "0001-a", "drafting")
        (root / ".mark/features/0001-a/status.md").write_text(status_text("review-requirement"), encoding="utf-8")
        cfg = load_config(root)
        hist = board.snapshot(cfg, board.History(cfg))["tickets"][0]["history"]
        self.assertEqual([(h["status"], bool(h["sha"])) for h in hist], [("drafting", True), ("review-requirement", False)])

    def test_history_outside_git_is_the_current_status(self):
        from tests._support import FULL_CONFIG, make_project
        root = make_project(FULL_CONFIG)
        add_ticket(root, "feature", "0001-a", "planning", commit=False)
        cfg = load_config(root)
        hist = board.snapshot(cfg, board.History(cfg))["tickets"][0]["history"]
        self.assertEqual([h["status"] for h in hist], ["planning"])


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        d = add_ticket(self.root, "feature", "0001-a", "designing", gates=["requirement-approved"])
        (d / "requirement.md").write_text("# R\n", encoding="utf-8")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "-m", "req")
        self.wt = add_worktree(self.root, "feature", "0001-a") / ".mark/features/0001-a"
        (self.wt / "design.md").write_text("# D\n", encoding="utf-8")
        self.cfg = load_config(self.root)

    def test_worktree_drafts_join_main_files(self):
        t = board.snapshot(self.cfg, board.History(self.cfg))["tickets"][0]
        files = {f["name"]: (f["src"], f["draft"]) for f in t["files"]}
        self.assertEqual(files, {"design.md": ("worktree", True), "requirement.md": ("main", False)})
        self.assertTrue(t["worktree"])
        self.assertEqual([g["name"] for g in t["gates"]], ["requirement-approved"])

    def test_resolve_file_stays_inside_the_ticket_dir(self):
        ok = board.resolve_file(self.cfg, ["features", "0001-a", "worktree", "design.md"])
        self.assertEqual(ok, (self.wt / "design.md").resolve())
        for parts in (["features", "0001-a", "main", "..", "..", "config.toml"],
                      ["features", "0001-a", "elsewhere", "design.md"],
                      ["features", "9999-x", "main", "requirement.md"],
                      ["gates", "0001-a", "main", "x"]):
            self.assertIsNone(board.resolve_file(self.cfg, parts), parts)

    def test_signature_changes_when_a_draft_is_written(self):
        before = board.signature(self.cfg)
        (self.wt / "tech-plan.md").write_text("# P\n", encoding="utf-8")
        self.assertNotEqual(board.signature(self.cfg), before)


class ServerTest(unittest.TestCase):
    def setUp(self):
        root = make_repo()
        d = add_ticket(root, "feature", "0001-a", "planning")
        (d / "requirement.md").write_text("# R\n", encoding="utf-8")
        self.cfg = load_config(root)
        self.server = board.bind(free_port())
        self.board = board.Board(self.cfg)
        self.server.RequestHandlerClass = board.make_handler(self.board)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.board.stop.set()
        with self.board.cond:
            self.board.cond.notify_all()
        self.server.shutdown()
        self.server.server_close()

    def get(self, path, host="127.0.0.1"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": f"{host}:{self.port}"})
        r = c.getresponse()
        return r.status, r.read()

    def test_routes(self):
        code, body = self.get("/api/board")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["tickets"][0]["id"], "0001-a")
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get("/f/features/0001-a/main/requirement.md"), (200, b"# R\n"))
        self.assertEqual(self.get("/f/features/0001-a/main/..%2F..%2Fconfig.toml")[0], 404)
        self.assertEqual(self.get("/nope")[0], 404)

    def test_other_hosts_are_refused(self):  # DNS rebinding
        self.assertEqual(self.get("/api/board", host="evil.example")[0], 403)

    def test_events_push_a_new_version(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/events", headers={"Host": "localhost"})
        r = c.getresponse()
        self.assertEqual(r.readline(), b"data: 0\n")
        r.readline()
        with self.board.cond:
            self.board.version += 1
            self.board.cond.notify_all()
        self.assertEqual(r.readline(), b"data: 1\n")
        c.close()


class PortsTest(unittest.TestCase):
    def test_bind_skips_a_busy_port(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            server = board.bind(port)
            try:
                self.assertNotEqual(server.server_address[1], port)
            finally:
                server.server_close()


class CliTest(unittest.TestCase):
    def test_start_reuse_stop(self):
        root = make_repo()
        port = str(free_port())
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["board", "--port", port], cwd=root, out=out, err=err), 0, err.getvalue())
        try:
            self.assertIn("http://127.0.0.1:", out.getvalue())
            out2 = io.StringIO()
            self.assertEqual(cli.main(["board", "--port", port], cwd=root, out=out2, err=err), 0)
            self.assertIn("already running", out2.getvalue())
            self.assertEqual(out.getvalue().split()[1], out2.getvalue().split()[-1])
        finally:
            out3 = io.StringIO()
            cli.main(["board", "--stop"], cwd=root, out=out3, err=err)
        self.assertIn("stopped", out3.getvalue())
        self.assertIsNone(board.running(load_config(root)))

    def test_bad_port_is_a_usage_error(self):
        root = make_repo()
        self.assertEqual(cli.main(["board", "--port", "x"], cwd=root, out=io.StringIO(), err=io.StringIO()), 2)


if __name__ == "__main__":
    unittest.main()
