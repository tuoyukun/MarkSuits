"""Web board: every ticket, its documents and its status history, live; the human decides gates on it.

`mark board` starts one server per project on 127.0.0.1, first free port from 6275 up,
and records it in `<state>/locks/board.json` so a second call reuses it (unless the
plugin was updated since: then the old server is replaced). The page
(`board.html`) reads three endpoints:

    /api/board                         snapshot of every ticket (JSON)
    /events                            server-sent events: a number that grows on every change
    /f/<features|bugs>/<id>/<main|worktree>/<path>   a file from the ticket dir
    POST /api/open                     open the board in the human's browser (what `mark board` calls)
    POST /api/login                    trade a one-time key from that URL for the session cookie
    POST /api/decide                   approve or reject, with the cookie

Deciding: the server holds a random session secret in memory only. It opens the browser itself
with a one-time key in the URL (`#k=`); the page trades it for an HttpOnly cookie. The model can
run `mark board` and curl the API but never sees a key or the secret, so it cannot decide.

Sources: the main checkout's ticket dirs (status, requirement, reviews, log), the
ticket's worktree (role artifacts before they merge), `<state>/gates/<id>.*`, and
`git log -p` of the status files on main: every status commit is one move.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import mimetypes
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import flow, general, human, states, tickets
from .config import MarkConfig
from .gitutil import git, worktrees
from .ports import in_use

DEFAULT_PORT = 6275  # "MARK" on a phone keypad; no well-known dev server uses it
PORT_TRIES = 100
POLL_SECONDS = 1.0
PING_SECONDS = 15
STATE_FILE = "board.json"
KEYS_KEPT = 10  # one-time keys not yet traded; older ones lapse
BODY_MAX = 65536
NO_BROWSER_ENV = "MARK_BOARD_NO_BROWSER"  # tests: never open a browser
PAGE = Path(__file__).with_name("board.html")
SOURCES = ("main", "worktree")


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------

def ticket_dirs(cfg: MarkConfig, kind: str, ticket_id: str) -> dict[str, Path]:
    rel = f"{cfg.state_rel}/{states.KIND_DIRS[kind]}/{ticket_id}"
    return {"main": cfg.root / rel, "worktree": cfg.root / cfg.worktree_for(kind, ticket_id) / rel}


def _files(dirs: dict[str, Path]) -> list[dict[str, object]]:
    """Top-level files; a name in both places shows the newer copy (a role's draft in the
    worktree, or the main checkout's later edit of a file the worktree only inherited).
    A worktree copy is a draft: not on main yet."""
    found: dict[str, dict[str, tuple[Path, os.stat_result]]] = {}
    for src, d in dirs.items():
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            if e.is_file() and not e.name.startswith(".") and e.name != tickets.STATUS_FILENAME:
                found.setdefault(e.name, {})[src] = (Path(e.path), e.stat())
    out = []
    for name in sorted(found):
        copies = found[name]
        same = len(copies) == 2 and copies["main"][0].read_bytes() == copies["worktree"][0].read_bytes()
        src = "main" if same else max(copies, key=lambda s: (copies[s][1].st_mtime_ns, s == "main"))
        out.append({"name": name, "src": src, "draft": src == "worktree", "mtime": int(copies[src][1].st_mtime)})
    return out


def _gates(cfg: MarkConfig, ticket_id: str) -> list[dict[str, str]]:
    out = []
    for p in sorted((cfg.state_dir / "gates").glob(f"{ticket_id}.*")):
        fields, _ = tickets.parse_status("---\n" + p.read_text(encoding="utf-8", errors="replace") + "\n---")
        out.append({"name": p.name[len(ticket_id) + 1:], "at": fields.get("approved_at", ""),
                    "by": fields.get("approved_by", "")})
    return out


def parse_history(log: str, state_rel: str) -> dict[str, list[dict[str, str]]]:
    """`git log --reverse -p -U0` of the status files -> {"features/<id>": [move, ...]}.

    A commit whose diff sets `status:` is a move; a commit that only edits the note is not.
    `-U0` shows changed lines only, so a field a commit leaves alone keeps its earlier value.
    """
    out: dict[str, list[dict[str, str]]] = {}
    known: dict[str, dict[str, str]] = {}  # latest field values per ticket, moves or not
    prefix = state_rel.split("/")
    for chunk in filter(str.strip, log.split("\x1e")):  # git() strips output, and \x1e counts as whitespace
        head, _, diff = chunk.partition("\n")
        sha, _, at = head.partition("\x1f")
        key, cur = None, {}

        def flush() -> None:
            if not key:
                return
            moved = "status" in cur
            known[key] = fields = {**known.get(key, {}), **cur}
            if moved:
                out.setdefault(key, []).append({"sha": sha[:7], "at": at.strip(), "owner": "", "updater": "",
                                                "note": "", **fields})

        for line in diff.splitlines():
            if line.startswith("diff --git"):
                flush()
                key, cur = None, {}
            elif line.startswith("+++ "):
                parts = line[4:].removeprefix("b/").split("/")
                ok = line.startswith("+++ b/") and parts[:len(prefix)] == prefix and len(parts) == len(prefix) + 3
                key = "/".join(parts[len(prefix):len(prefix) + 2]) if ok else None
            elif line[:1] in "+-" and not line.startswith("--- ") and key:
                text = line[1:].strip()
                m = tickets._FIELD_RE.match(text)
                if line[0] == "+" and m and m.group(1) in ("status", "owner", "updater"):
                    cur[m.group(1)] = m.group(2).strip()
                elif text and text != "---" and not m:
                    cur["note"] = text if line[0] == "+" else cur.get("note", "")
        flush()
    return out


class History:
    """Status moves from git, recomputed only when main's HEAD changes."""

    def __init__(self, cfg: MarkConfig):
        self.cfg, self.head, self.moves = cfg, None, {}

    def get(self) -> dict[str, list[dict[str, str]]]:
        code, head = git(["rev-parse", "HEAD"], self.cfg.root)
        head = head if code == 0 else None
        if head != self.head:
            spec = f":(glob){self.cfg.state_rel}/*/*/{tickets.STATUS_FILENAME}"
            code, log = git(["log", self.cfg.main_branch, "--reverse", "--no-renames", "-p", "-U0",
                             "--format=%x1e%H%x1f%aI", "--", spec], self.cfg.root)
            self.moves = parse_history(log, self.cfg.state_rel) if code == 0 else {}
            self.head = head
        return self.moves


def snapshot(cfg: MarkConfig, history: History) -> dict[str, object]:
    moves = history.get()
    items = []
    for tk in tickets.all_tickets(cfg):
        dirs = ticket_dirs(cfg, tk.kind, tk.id)
        hist = list(moves.get(f"{states.KIND_DIRS[tk.kind]}/{tk.id}", []))
        if not hist or hist[-1]["status"] != tk.status:  # moved but not committed yet
            mtime = _dt.datetime.fromtimestamp(tk.path.stat().st_mtime).astimezone().isoformat(timespec="seconds") if tk.exists else ""
            hist.append({"sha": "", "at": mtime, "status": tk.status, "owner": tk.get("owner"),
                         "updater": tk.get("updater"), "note": tk.note})
        items.append({**tk.as_dict(), "dir": states.KIND_DIRS[tk.kind], "side": tk.side,
                      "branch": cfg.branch_for(tk.kind, tk.id),
                      "worktree": cfg.worktree_for(tk.kind, tk.id) if dirs["worktree"].is_dir() else "",
                      "files": _files(dirs), "gates": _gates(cfg, tk.id), "history": hist, "wait": waits_on(cfg, tk)})
    return {"project": cfg.root.name, "locale": cfg.locale, "branch": cfg.main_branch,
            "tickets": items + general_lanes(cfg)}


def waits_on(cfg: MarkConfig, tk: tickets.Ticket) -> dict[str, object] | None:
    """What the human can decide on this ticket from the board, or None."""
    if tk.side in ("terminal", "unknown"):
        return None
    ctx = flow.Ctx(cfg, tk)
    if not ctx.has_gate(flow.TICKET_GATE):
        return {"kind": "opening"}
    if tk.status not in flow.APPROVE:
        return None
    if flow.APPROVE[tk.status][0]:
        return {"kind": "review"}
    targets = flow.approve_targets(ctx)
    default = flow.APPROVE[tk.status][2]
    return {"kind": "blocked", "targets": targets, "answer": tk.status == "blocked-unclear",
            "default": default if default in targets else (targets[0] if targets else "")}


def general_lanes(cfg: MarkConfig) -> list[dict[str, object]]:
    """Open `chore/general-*` lanes as cards. A landed lane fast-forwards onto main and is
    deleted, leaving no record, so only open lanes show."""
    code, out = git(["for-each-ref", "--format=%(refname:short)", f"refs/heads/{general.PREFIX}*"], cfg.root)
    if code != 0:
        return []
    wts = {b: p for p, b in worktrees(cfg.root)}
    items = []
    for branch in out.splitlines():
        stamp = branch.removeprefix(general.PREFIX)
        try:
            at = _dt.datetime.strptime(stamp, "%Y%m%d-%H%M%S").astimezone().isoformat(timespec="seconds")
        except ValueError:
            at = ""
        subject = git(["log", "-1", "--format=%s", f"{cfg.main_branch}..{branch}"], cfg.root)[1]
        commits = git(["rev-list", "--count", f"{cfg.main_branch}..{branch}"], cfg.root)[1] or "0"
        note = f"{commits} commit(s) ahead of {cfg.main_branch}"
        wt = wts.get(branch)
        items.append({"kind": "general", "id": f"general-{stamp}", "status": "developing", "desc": subject or branch,
                      "owner": "orchestrator", "updater": "orchestrator", "note": note, "dir": "", "side": "",
                      "branch": branch, "worktree": os.path.relpath(wt, cfg.root) if wt else "",
                      "files": [], "gates": [], "history": [{"sha": "", "at": at, "status": "developing",
                                                              "owner": "orchestrator", "updater": "orchestrator", "note": note}]})
    return items


def signature(cfg: MarkConfig) -> tuple:
    """Cheap fingerprint of everything the snapshot reads; changes when any of it does."""
    sig: list[object] = [git(["rev-parse", "HEAD"], cfg.root)[1],
                         git(["for-each-ref", f"refs/heads/{general.PREFIX}*"], cfg.root)[1]]
    roots = [cfg.state_dir / "gates"]
    for kind in states.KINDS:
        roots.append(tickets.kind_dir(cfg, kind))
        for tid in tickets.ticket_dirs(cfg, kind):
            roots += ticket_dirs(cfg, kind, tid).values()
    for d in roots:
        try:
            sig += [(e.path, st.st_mtime_ns, st.st_size) for e in os.scandir(d) for st in [e.stat()]]
        except OSError:
            sig.append((str(d), None))
    return tuple(sig)


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------

def resolve_file(cfg: MarkConfig, parts: list[str]) -> Path | None:
    """`[features, <id>, main|worktree, *path]` -> the file, only if it is inside that ticket dir."""
    if len(parts) < 4 or parts[2] not in SOURCES:
        return None
    kind = next((k for k, d in states.KIND_DIRS.items() if d == parts[0]), None)
    if kind is None or parts[1] not in tickets.ticket_dirs(cfg, kind):
        return None
    base = ticket_dirs(cfg, kind, parts[1])[parts[2]].resolve()
    target = base.joinpath(*parts[3:]).resolve()
    return target if target.is_relative_to(base) and target.is_file() else None


def decide(cfg: MarkConfig, req: dict) -> tuple[bool, str]:
    """Approve or reject for the human, through the same CLI code as `/mark:approve` and
    `/mark:reject`: a token for this decision, then `mark approve|reject`. Returns (ok, output)."""
    from . import cli  # cli imports this module

    ticket, verb, to = req.get("ticket"), req.get("verb"), req.get("to") or None
    answer, items = req.get("answer") or "", req.get("items") or []
    known = any(ticket in tickets.ticket_dirs(cfg, k) for k in states.KINDS) if isinstance(ticket, str) else False
    if not known or verb not in ("approve", "reject") or not (to is None or isinstance(to, str)) \
            or not isinstance(answer, str) or not (isinstance(items, list) and all(isinstance(i, str) for i in items)):
        return False, "bad request"
    if verb == "approve":
        argv = ["approve", ticket] + (["--to", to] if to else [])
        rest, text = [to] if to else [], f"{to or ''} {answer}".strip()[:human.TEXT_MAX]
    else:
        argv = ["reject", ticket] + [a for i in items for a in ("--item", i)] + (["--to", to] if to else [])
        rest, text = [], ""
    token = human.grant(cfg, verb, ticket, rest, text, source="board")
    out = io.StringIO()
    try:
        code = cli.main(argv, cwd=cfg.root, out=out, err=out)
    finally:
        token.unlink(missing_ok=True)  # a refused decision leaves nothing a later command could use
    return code == 0, out.getvalue().strip()


class Board:
    def __init__(self, cfg: MarkConfig):
        self.cfg, self.history = cfg, History(cfg)
        self.version, self.cond, self.stop = 0, threading.Condition(), threading.Event()
        self.secret, self.keys, self.lock = secrets.token_urlsafe(32), [], threading.Lock()

    def open_browser(self, port: int) -> None:
        key = secrets.token_urlsafe(24)
        with self.lock:
            self.keys = self.keys[-(KEYS_KEPT - 1):] + [key]
        if os.environ.get(NO_BROWSER_ENV) != "1":
            webbrowser.open(f"http://127.0.0.1:{port}/#k={key}")

    def redeem(self, key: object) -> bool:
        with self.lock:
            if isinstance(key, str) and key in self.keys:
                self.keys.remove(key)
                return True
        return False

    def authorized(self, cookie_header: str | None, port: int) -> bool:
        try:
            morsel = SimpleCookie(cookie_header or "").get(cookie_name(port))
        except CookieError:
            return False
        return morsel is not None and secrets.compare_digest(morsel.value, self.secret)

    def mode(self, cookie_header: str | None, port: int) -> str:
        """"on": this browser may decide; "login": it may not yet; "off": `[board] decide = false`."""
        if not self.cfg.board_decide:
            return "off"
        return "on" if self.authorized(cookie_header, port) else "login"

    def watch(self) -> None:
        last = signature(self.cfg)
        while not self.stop.wait(POLL_SECONDS):
            sig = signature(self.cfg)
            if sig != last:
                last = sig
                with self.cond:
                    self.version += 1
                    self.cond.notify_all()


def cookie_name(port: int) -> str:
    return f"mark_board_{port}"  # cookies ignore the port: two projects' boards must not share one


def make_handler(board: Board) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str, cookie: str = "") -> None:
            self.send_response(code)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: dict, cookie: str = "") -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", cookie)

        def _local(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):  # DNS rebinding: another site must not reach the board
                self._send(403, b"forbidden", "text/plain")
                return False
            return True

        def do_POST(self) -> None:
            try:
                raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), BODY_MAX))
            except ValueError:
                raw = b""
            if not self._local():
                return
            port = self.server.server_address[1]
            path, origin = self.path.split("?", 1)[0], self.headers.get("Origin")
            same = origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
            if path == "/api/open" and (origin is None or same):  # no Origin: `mark board`, not a web page
                board.open_browser(port)
                self._json(200, {"ok": True})
                return
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = None
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if not same or ctype != "application/json" or not isinstance(body, dict):
                self._json(403, {"ok": False, "text": "forbidden"})
            elif path == "/api/login":
                if board.redeem(body.get("k")):
                    self._json(200, {"ok": True},
                               f"{cookie_name(port)}={board.secret}; HttpOnly; SameSite=Strict; Path=/")
                else:
                    self._json(403, {"ok": False, "text": "expired key"})
            elif path == "/api/decide":
                if board.mode(self.headers.get("Cookie"), port) != "on":
                    self._json(403, {"ok": False, "text": "read-only"})
                    return
                with board.lock:  # one decision at a time
                    ok, text = decide(board.cfg, body)
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            else:
                self._json(404, {"ok": False, "text": "not found"})

        def do_GET(self) -> None:
            if not self._local():
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/board":
                port = self.server.server_address[1]
                self._json(200, {**snapshot(board.cfg, board.history),
                                 "decide": board.mode(self.headers.get("Cookie"), port)})
            elif path == "/events":
                self._events()
            elif path.startswith("/f/"):
                f = resolve_file(board.cfg, [unquote(p) for p in path[3:].split("/")])
                if f is None:
                    self._send(404, b"not found", "text/plain")
                    return
                ctype = mimetypes.guess_type(f.name)[0] or "text/plain"
                if ctype == "text/markdown":
                    ctype = "text/plain"
                if ctype.startswith("text/"):
                    ctype += "; charset=utf-8"
                self._send(200, f.read_bytes(), ctype)
            else:
                self._send(404, b"not found", "text/plain")

        def _events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = -1
            try:
                while not board.stop.is_set():
                    with board.cond:
                        if board.version == seen:
                            board.cond.wait(PING_SECONDS)
                        version = board.version
                    msg = f"data: {version}\n\n" if version != seen else ": ping\n\n"
                    seen = version
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
            except OSError:
                pass  # the browser went away

    return Handler


def bind(start: int) -> ThreadingHTTPServer | None:
    """First port from `start` that nothing listens on and that binds. The listener check comes
    first because SO_REUSEADDR (which lets a restart reuse a port in TIME_WAIT) would let macOS
    bind 127.0.0.1 under another server's 0.0.0.0 listener."""
    for port in range(start, start + PORT_TRIES):
        if in_use(port):
            continue
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
        except OSError:
            continue
    return None


def state_path(cfg: MarkConfig) -> Path:
    return cfg.state_dir / "locks" / STATE_FILE


def serve(cfg: MarkConfig, start: int = DEFAULT_PORT) -> int:
    """Run the board in this process until SIGTERM / Ctrl-C."""
    server = bind(start)
    if server is None:
        return 1
    board = Board(cfg)
    server.RequestHandlerClass = make_handler(board)
    server.daemon_threads = True
    port = server.server_address[1]
    path = state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": os.getpid(), "port": port, "root": str(cfg.root), "page": str(PAGE)}) + "\n")
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    threading.Thread(target=board.watch, daemon=True).start()
    board.open_browser(port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        board.stop.set()
        with board.cond:
            board.cond.notify_all()
        server.server_close()
        if read_state(cfg).get("pid") == os.getpid():
            path.unlink(missing_ok=True)
    return 0


def read_state(cfg: MarkConfig) -> dict:
    try:
        return json.loads(state_path(cfg).read_text())
    except (OSError, ValueError):
        return {}


def _alive(pid: object) -> bool:
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running(cfg: MarkConfig) -> int | None:
    """Port of this project's live board, or None."""
    st = read_state(cfg)
    port = st.get("port")
    return port if _alive(st.get("pid")) and isinstance(port, int) and in_use(port) else None


def start(cfg: MarkConfig, port: int = DEFAULT_PORT, wait: float = 5.0) -> tuple[int | None, bool]:
    """(port, reused): reuse this project's board, else start one in the background. A board
    started from another plugin install serves that install's page, so it is replaced."""
    live = running(cfg)
    if live:
        if read_state(cfg).get("page") == str(PAGE):
            return live, True
        stop(cfg)
    state_path(cfg).unlink(missing_ok=True)
    log = cfg.state_dir / "locks" / "board.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    mark = Path(__file__).resolve().parents[2] / "bin" / "mark"
    with open(log, "w") as fh:
        child = subprocess.Popen([sys.executable, str(mark), "board", "--serve", "--port", str(port)],
                                 cwd=cfg.root, stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
                                 start_new_session=True)  # outlives the Bash call that started it
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and child.poll() is None:
        st = read_state(cfg)
        if st.get("pid") == child.pid:
            return st.get("port"), False
        time.sleep(0.1)
    return None, False


def reopen(port: int) -> bool:
    """Ask a live board to open itself in the human's browser again."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/open", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except OSError:
        return False


def stop(cfg: MarkConfig) -> bool:
    pid = read_state(cfg).get("pid")
    if not _alive(pid):
        state_path(cfg).unlink(missing_ok=True)
        return False
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _alive(pid):
            break
        time.sleep(0.1)
    state_path(cfg).unlink(missing_ok=True)
    return True
