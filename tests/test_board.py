"""Web board: history from git, files from main + worktree, the HTTP surface, start/stop."""
from __future__ import annotations

import http.client
import io
import json
import os
import re
import socket
import subprocess
import threading
import unittest
from unittest import mock

from tests._support import add_ticket, add_worktree, fresh_home, make_repo, sh, status_text

from mark import board, cli, flow, home, human, reviews, runner, tickets, wait
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


class GeneralLaneTest(unittest.TestCase):
    def test_an_open_general_lane_shows_and_changes_the_signature(self):
        root = make_repo()
        cfg = load_config(root)
        before = board.signature(cfg)
        sh(root, "git", "branch", "chore/general-20260101-120000")
        self.assertNotEqual(board.signature(cfg), before)
        sh(root, "git", "checkout", "-q", "chore/general-20260101-120000")
        (root / "notes.md").write_text("x\n", encoding="utf-8")
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-q", "-m", "Tidy the notes")
        sh(root, "git", "checkout", "-q", "main")
        lanes = [t for t in board.snapshot(cfg, board.History(cfg))["tickets"] if t["kind"] == "general"]
        self.assertEqual(len(lanes), 1)
        lane = lanes[0]
        self.assertEqual((lane["id"], lane["desc"], lane["status"]), ("general-20260101-120000", "Tidy the notes", "developing"))
        self.assertTrue(lane["history"][0]["at"].startswith("2026-01-01T12:00:00"))


class ServerTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        root = make_repo().resolve()
        d = add_ticket(root, "feature", "0001-a", "planning")
        (d / "requirement.md").write_text("# R\n", encoding="utf-8")
        self.cfg = load_config(root)
        self.p = f"/p/{home.add(root)}"
        self.server = board.bind(free_port())
        self.board = board.Board()
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
        code, body = self.get(self.p + "/api/board")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["tickets"][0]["id"], "0001-a")
        self.assertEqual(self.get("/")[0], 200)
        self.assertEqual(self.get(self.p + "/f/features/0001-a/main/requirement.md"), (200, b"# R\n"))
        self.assertEqual(self.get(self.p + "/f/features/0001-a/main/..%2F..%2Fconfig.toml")[0], 404)
        self.assertEqual(self.get("/nope")[0], 404)
        self.assertEqual(self.get(self.p)[0], 301)  # the page reads its API relative to /p/<id>/
        self.assertEqual(self.get(self.p + "/")[0], 200)
        self.assertEqual(self.get("/p/0123456789/api/board")[0], 404)  # not registered
        cards = json.loads(self.get("/api/projects")[1])["projects"]
        self.assertEqual([(c["name"], c["total"]) for c in cards], [(self.cfg.root.name, 1)])

    def test_other_hosts_are_refused(self):  # DNS rebinding
        self.assertEqual(self.get(self.p + "/api/board", host="evil.example")[0], 403)

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


class DecideTest(unittest.TestCase):
    """Deciding on the board: only the browser `mark board` opened may, and it runs the CLI's checks."""

    def setUp(self):
        fresh_home(self)
        self.root = make_repo().resolve()
        add_ticket(self.root, "feature", "0001-a", "review-plan", gates=("ticket-approved",))
        add_ticket(self.root, "feature", "0002-b", "blocked-unclear", gates=("ticket-approved",))
        add_ticket(self.root, "feature", "0003-c", "drafting")
        self.cfg = load_config(self.root)
        self.p = f"/p/{home.add(self.root)}"
        self.server = board.bind(free_port())
        self.board = board.Board()
        self.server.RequestHandlerClass = board.make_handler(self.board)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        patcher = mock.patch.object(runner, "start", return_value=(True, ""))  # never a real claude here
        self.run_start = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.board.stop.set()
        self.server.shutdown()
        self.server.server_close()

    def post(self, path, data, origin=None, cookie=""):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if origin is not False:
            headers["Origin"] = origin or self.origin
        if cookie:
            headers["Cookie"] = cookie
        c.request("POST", path, body=json.dumps(data), headers=headers)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}"), r.getheader("Set-Cookie") or ""

    def login(self):
        self.board.open_browser(self.port)
        code, _, cookie = self.post("/api/login", {"k": self.board.keys[-1]})
        self.assertEqual(code, 200)
        self.assertIn("HttpOnly", cookie)
        return cookie.split(";")[0]

    def status(self, tid):
        return flow.load(load_config(self.root), tid).ticket.status

    def no_tokens_left(self):
        d = human.token_dir(self.cfg)
        self.assertEqual(list(d.iterdir()) if d.is_dir() else [], [])

    def test_snapshot_says_what_waits_on_the_human(self):
        waits = {t["id"]: t["wait"] for t in board.snapshot(self.cfg, board.History(self.cfg))["tickets"]}
        self.assertEqual(waits["0001-a"], {"kind": "review"})
        self.assertEqual(waits["0002-b"]["kind"], "blocked")
        self.assertTrue(waits["0002-b"]["answer"])
        self.assertIn(waits["0002-b"]["default"], waits["0002-b"]["targets"])
        self.assertEqual(waits["0003-c"], {"kind": "opening"})

    def test_without_the_cookie_nothing_is_decided(self):
        code, _, _ = self.post(self.p + "/api/decide", {"ticket": "0001-a", "verb": "approve"})
        self.assertEqual(code, 403)
        self.assertEqual(self.status("0001-a"), "review-plan")
        self.assertEqual(self.post("/api/login", {"k": "guess"})[0], 403)
        self.no_tokens_left()

    def test_a_key_works_once_and_only_from_the_board_page(self):
        self.board.open_browser(self.port)
        key = self.board.keys[-1]
        self.assertEqual(self.post("/api/login", {"k": key}, origin="http://evil.example")[0], 403)
        self.assertEqual(self.post("/api/login", {"k": key})[0], 200)
        self.assertEqual(self.post("/api/login", {"k": key})[0], 403)

    def test_another_origin_cannot_use_the_cookie(self):
        cookie = self.login()
        code, _, _ = self.post(self.p + "/api/decide", {"ticket": "0001-a", "verb": "approve"},
                               origin="http://evil.example", cookie=cookie)
        self.assertEqual(code, 403)
        self.assertEqual(self.status("0001-a"), "review-plan")

    def test_mode_in_the_snapshot(self):
        get = lambda cookie="": json.loads(self._get(self.p + "/api/board", cookie))["decide"]
        self.assertEqual(get(), "login")
        self.assertEqual(get(self.login()), "on")

    def _get(self, path, cookie=""):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}", "Cookie": cookie})
        return c.getresponse().read()

    def test_approve_moves_the_ticket_writes_the_gate_and_commits(self):
        code, res, _ = self.post(self.p + "/api/decide", {"ticket": "0001-a", "verb": "approve"}, cookie=self.login())
        self.assertEqual(code, 200, res)
        self.assertEqual(self.status("0001-a"), "developing")
        self.assertTrue((self.root / ".mark" / "gates" / "0001-a.plan-approved").is_file())
        self.assertIn("0001-a: approved review-plan -> developing", sh(self.root, "git", "log", "-1", "--format=%s"))
        self.no_tokens_left()

    def test_after_a_decision_a_waiting_session_carries_on_else_a_runner_starts(self):
        cookie = self.login()
        wait.path(self.cfg, "0001-a").parent.mkdir(parents=True, exist_ok=True)
        wait.path(self.cfg, "0001-a").write_text(json.dumps({"pid": os.getpid()}))
        code, res, _ = self.post(self.p + "/api/decide", {"ticket": "0001-a", "verb": "approve"}, cookie=cookie)
        self.assertEqual((code, res["note"]), (200, "run.session"))
        self.run_start.assert_not_called()
        code, res, _ = self.post(self.p + "/api/decide", {"ticket": "0002-b", "verb": "approve", "to": "planning",
                                                 "answer": "Yes."}, cookie=cookie)
        self.assertEqual((code, res["note"]), (200, "run.started"))
        self.run_start.assert_called_once_with(self.cfg, "0002-b")
        self.assertEqual(self.post(self.p + "/api/stop", {})[0], 403)

    def test_reject_records_each_line_as_an_item(self):
        code, res, _ = self.post(self.p + "/api/decide", {"ticket": "0001-a", "verb": "reject", "items": ["too big", "split it"]},
                                 cookie=self.login())
        self.assertEqual(code, 200, res)
        self.assertEqual(self.status("0001-a"), "planning")
        review = (self.root / ".mark" / "features" / "0001-a" / reviews.filename("plan")).read_text(encoding="utf-8")
        self.assertIn("too big", review)
        self.assertIn("split it", review)

    def test_a_refusal_comes_back_and_leaves_no_token(self):
        cookie = self.login()
        code, res, _ = self.post(self.p + "/api/decide", {"ticket": "0002-b", "verb": "approve", "to": "planning"}, cookie=cookie)
        self.assertEqual(code, 409)
        self.assertTrue(res["text"])
        self.assertEqual(self.status("0002-b"), "blocked-unclear")
        self.no_tokens_left()
        code, res, _ = self.post(self.p + "/api/decide", {"ticket": "0002-b", "verb": "approve", "to": "planning",
                                                 "answer": "Use the email as the key."}, cookie=cookie)
        self.assertEqual(code, 200, res)
        self.assertEqual(self.status("0002-b"), "planning")
        self.assertIn("Use the email as the key.", res["text"])

    def test_bad_requests_are_refused(self):
        cookie = self.login()
        for body in ({"ticket": "../x", "verb": "approve"}, {"ticket": "0001-a", "verb": "merge"},
                     {"ticket": "0001-a", "verb": "reject", "items": "one"}):
            self.assertEqual(self.post(self.p + "/api/decide", body, cookie=cookie)[0], 409, body)
        self.assertEqual(self.status("0001-a"), "review-plan")

    def test_new_ticket_opens_approved_and_starts_the_chat(self):
        cookie = self.login()
        with mock.patch.object(board.chat, "start", return_value=(True, "")) as start:
            code, res, _ = self.post(self.p + "/api/new", {"kind": "feature", "text": "Due dates\nOverdue ones in red.",
                                                  "slug": "due-dates"}, cookie=cookie)
        self.assertEqual((code, res["ok"]), (200, True), res)
        tid = res["id"]
        self.assertTrue(tid.endswith("-due-dates"))
        self.assertEqual(self.status(tid), "drafting")
        self.assertTrue((self.root / ".mark" / "gates" / f"{tid}.ticket-approved").is_file())
        self.assertEqual(flow.load(self.cfg, tid).ticket.get("desc"), "Due dates")
        start.assert_called_once_with(self.cfg, "feature", tid, "Due dates\nOverdue ones in red.")
        self.no_tokens_left()

    def test_new_ticket_and_chat_need_the_cookie_and_a_good_request(self):
        with mock.patch.object(board.chat, "start", return_value=(True, "")) as start:
            self.assertEqual(self.post(self.p + "/api/new", {"kind": "bug", "text": "Crash"})[0], 403)
            self.assertEqual(self.post(self.p + "/api/chat", {"ticket": "0003-c", "text": "hi"})[0], 403)
            cookie = self.login()
            for body in ({"kind": "chore", "text": "x"}, {"kind": "bug", "text": "  "}, {"kind": "bug", "text": 1},
                         {"kind": "bug", "text": "x" * 20001}):
                self.assertEqual(self.post(self.p + "/api/new", body, cookie=cookie)[0], 409, body)
            for body in ({"ticket": "../x", "text": "hi"}, {"ticket": "0003-c", "text": ""}):
                self.assertEqual(self.post(self.p + "/api/chat", body, cookie=cookie)[0], 409, body)
            start.assert_not_called()
            code, res, _ = self.post(self.p + "/api/chat", {"ticket": "0003-c", "text": " ISO dates. "}, cookie=cookie)
            self.assertEqual(code, 200, res)
            start.assert_called_once_with(self.cfg, "feature", "0003-c", "ISO dates.")
        self.assertEqual(len(tickets.ticket_dirs(self.cfg, "feature")), 3)  # nothing was claimed
        self.no_tokens_left()

    def test_the_model_is_set_with_the_cookie_and_its_key_never_shown(self):
        body = {"provider": "custom", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/anthropic",
                "api_key": "sk-secret"}
        self.assertEqual(self.post("/api/model", body)[0], 403)
        cookie = self.login()
        self.assertEqual(self.post("/api/model", {**body, "base_url": "nope"}, cookie=cookie)[0], 409)
        self.assertEqual(self.post("/api/model", body, cookie=cookie)[0], 200)
        raw = self._get(self.p + "/api/board").decode()
        self.assertNotIn("sk-secret", raw)
        self.assertEqual(json.loads(raw)["model"]["label"], "deepseek-chat @ api.deepseek.com")

    def test_a_busy_chat_comes_back(self):
        with mock.patch.object(board.chat, "start", return_value=(False, "busy")):
            code, res, _ = self.post(self.p + "/api/chat", {"ticket": "0003-c", "text": "hi"}, cookie=self.login())
        self.assertEqual((code, res["text"]), (409, "chat.busy"))

    def test_the_chat_view_and_stop(self):
        self.assertEqual(json.loads(self._get(self.p + "/api/chat/0003-c")), {"running": False, "messages": [], "ask": None, "model": ""})
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", self.p + "/api/chat/nope", headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(c.getresponse().status, 404)
        with mock.patch.object(board.chat, "stop", return_value=True) as stop:
            code, res, _ = self.post(self.p + "/api/stop", {"ticket": "0003-c"}, cookie=self.login())
        self.assertEqual((code, res["ok"]), (200, True))
        stop.assert_called_once_with(self.cfg, "0003-c")

    def test_board_decide_off(self):
        cfg_path = self.root / ".mark" / "config.toml"
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8") + "\n[board]\ndecide = false\n", encoding="utf-8")
        code, _, _ = self.post(self.p + "/api/decide", {"ticket": "0001-a", "verb": "approve"}, cookie=self.login())
        self.assertEqual(code, 403)
        self.assertEqual(self.status("0001-a"), "review-plan")


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


class HomeTest(unittest.TestCase):
    """The registry, and the home page's add / remove / cards."""

    def setUp(self):
        fresh_home(self)

    def test_add_once_find_remove_and_nothing_on_disk_is_touched(self):
        root = make_repo()
        pid = home.add(root)
        self.assertEqual(home.add(root.resolve()), pid)  # one entry per project, however spelled
        self.assertEqual([p["id"] for p in home.projects()], [pid])
        self.assertEqual(home.find(pid), root.resolve())
        self.assertTrue(home.remove(pid))
        self.assertFalse(home.remove(pid))
        self.assertEqual(home.projects(), [])
        self.assertTrue((root / ".mark" / "config.toml").is_file())

    def test_a_gone_or_broken_project_shows_an_error_card(self):
        gone, broken = make_repo(), make_repo()
        home.add(gone)
        home.add(broken)
        (broken / ".mark" / "config.toml").write_text("mark_schema = 999\n")
        sh(gone, "rm", "-rf", str(gone))
        cards = board.Board().home_view()
        self.assertEqual(cards[0]["error"], "home.gone")
        self.assertIn("mark_schema=999", cards[1]["error"])

    def test_add_project_needs_an_absolute_mark_project(self):
        root = make_repo()
        self.assertEqual(board.add_project({"dir": "rel/path"})[:2], (False, "home.absolute"))
        self.assertEqual(board.add_project({"dir": str(root / "nope")})[:2], (False, "home.notMark"))
        self.assertEqual(board.add_project({"dir": 1})[:2], (False, "bad request"))
        ok, _, pid = board.add_project({"dir": str(root / ".mark")})  # inside the project: its root
        self.assertTrue(ok)
        self.assertEqual(home.find(pid), root.resolve())
        self.assertEqual(board.add_project({"dir": str(root)})[:2], (False, "home.already"))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home(self)

    def tearDown(self):
        board.stop()

    def test_start_reuse_stop_one_server_for_every_project(self):
        a, b = make_repo(), make_repo()
        port = str(free_port())
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["board", "--port", port], cwd=a, out=out, err=err), 0, err.getvalue())
        self.assertIn(f"/p/{home.project_id(a)}/", out.getvalue())
        out2 = io.StringIO()
        self.assertEqual(cli.main(["board", "--port", port], cwd=b, out=out2, err=err), 0)
        self.assertIn("already running", out2.getvalue())
        url = re.compile(r"http://127\.0\.0\.1:\d+")
        self.assertEqual(url.search(out.getvalue())[0], url.search(out2.getvalue())[0])
        self.assertEqual({p["id"] for p in home.projects()}, {home.project_id(a), home.project_id(b)})
        out3 = io.StringIO()
        self.assertEqual(cli.main(["board"], cwd=self.home, out=out3, err=err), 0)  # outside a project: home
        self.assertRegex(out3.getvalue(), r"http://127\.0\.0\.1:\d+/\n")
        out4 = io.StringIO()
        cli.main(["board", "--stop"], cwd=a, out=out4, err=err)
        self.assertIn("stopped", out4.getvalue())
        self.assertIsNone(board.running())

    def test_a_board_from_another_install_is_replaced(self):
        port = free_port()
        self.assertEqual(cli.main(["board", "--port", str(port)], cwd=make_repo(), out=io.StringIO(), err=io.StringIO()), 0)
        old = board.read_state()
        board.state_path().write_text(json.dumps({**old, "page": "/old/install/board.html"}))
        live, reused = board.start(port)
        self.assertFalse(reused)
        self.assertNotEqual(board.read_state()["pid"], old["pid"])
        self.assertEqual(board.read_state()["page"], str(board.PAGE))

    def test_a_service_board_is_reused_and_not_stopped(self):
        port = free_port()
        with mock.patch.dict(os.environ, {board.SERVICE_ENV: "app"}):
            self.assertEqual(cli.main(["board", "--port", str(port)], cwd=make_repo(), out=io.StringIO(), err=io.StringIO()), 0)
        st = board.read_state()
        self.assertEqual((st["service"], board.service()), ("app", "app"))
        board.state_path().write_text(json.dumps({**st, "page": "/Cellar/marksuits/0.1.0/board.html"}))
        self.assertEqual(board.start(port), (st["port"], True))
        cli.restart_board(load_config(make_repo()), io.StringIO())
        self.assertEqual(cli.main(["board", "--stop"], cwd=make_repo(), out=io.StringIO(), err=(err := io.StringIO())), 1)
        self.assertIn("menu bar", err.getvalue())
        self.assertEqual(board.read_state()["pid"], st["pid"])
        board.state_path().write_text(json.dumps(st))  # tearDown stops it

    def test_upgrade_restarts_a_board_from_another_install(self):
        cfg = load_config(make_repo())
        port = free_port()
        self.assertEqual(cli.main(["board", "--port", str(port)], cwd=cfg.root, out=io.StringIO(), err=io.StringIO()), 0)
        current = board.read_state()
        cli.restart_board(cfg, out := io.StringIO())
        self.assertEqual(board.read_state()["pid"], current["pid"])  # current board: left alone
        self.assertEqual(out.getvalue(), "")
        board.state_path().write_text(json.dumps({**current, "page": "/old/install/board.html"}))
        cli.restart_board(cfg, out)
        self.assertIn("restarted", out.getvalue())
        self.assertNotEqual(board.read_state()["pid"], current["pid"])
        self.assertEqual(board.read_state()["port"], current["port"])

    def test_a_projects_own_board_from_before_is_stopped(self):
        root = make_repo()
        legacy = load_config(root).state_dir / "locks" / "board.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        sleeper = subprocess.Popen(["sleep", "30"])
        self.addCleanup(sleeper.kill)
        legacy.write_text(json.dumps({"pid": sleeper.pid, "port": 1}))
        self.assertEqual(cli.main(["board", "--port", str(free_port())], cwd=root, out=io.StringIO(), err=io.StringIO()), 0)
        self.assertEqual(sleeper.wait(timeout=5), -15)
        self.assertFalse(legacy.exists())

    def test_bad_port_is_a_usage_error(self):
        root = make_repo()
        self.assertEqual(cli.main(["board", "--port", "x"], cwd=root, out=io.StringIO(), err=io.StringIO()), 2)


if __name__ == "__main__":
    unittest.main()
