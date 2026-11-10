"""Web board: every project's tickets, their documents and status history, live; the human decides gates on it.

One server per user (since v0.58), on 127.0.0.1, first free port from 6275 up, recorded in
`MARK_HOME/board.json` (`home.py`) so `mark board` reuses it (unless the plugin was updated since:
then it is replaced). It shows the projects in `MARK_HOME/projects.json`; `mark board` in a
project adds it there. The page (`board.html`) is one file with two views:

    /                                  home: every project, what waits on the human
    /api/projects                      the home's cards (JSON)
    /api/deps                          what this machine lacks for Mark, and the running fix (`deps.py`)
    POST /api/deps/fix {id}            run that check's fixed command (with the cookie)
    /events                            server-sent events: a number that grows on any change
    POST /api/open {path}              open the home or a project in the human's browser (what `mark board` calls)
    POST /api/login                    trade a one-time key from that URL for the session cookie
    POST /api/model                    set the model headless sessions use (`model.py`, with the cookie)
    POST /api/projects/add {dir}       register an existing Mark project (with the cookie)
    POST /api/projects/remove {id}     forget one; nothing on disk is touched (with the cookie)
    POST /api/wizard {dir, profile, text}  set up a new project: `/mark:init` in the board chat (`wizard.py`, with the cookie)
    POST /api/pickdir                  the Mac's folder dialog: {ok, path} (with the cookie)
    POST /api/update                   update the plugin and restart on it (`upkeep.py`, with the cookie)
    /api/wizard/<wid>                  a wizard's chat; POST {text} the next message, POST .../stop, .../discard (with the cookie)

    /p/<id>/                           one project's board; under it, relative to it:
      api/board                        snapshot of every ticket (JSON)
      events                           server-sent events for this project only
      f/<features|bugs>/<id>/<main|worktree>/<path>   a file from the ticket dir
      api/chat/<ticket>                a ticket's chat (`chat.py`)
      POST api/decide                  approve or reject, with the cookie
      POST api/void {ticket, reason}   void an unfinished ticket for the human (with the cookie)
      POST api/stop                    stop the headless session, or with {"ticket"} its chat turn (with the cookie)
      POST api/new                     open a ticket and start talking it through (with the cookie)
      POST api/chat                    send the next message in a ticket's chat (with the cookie)
      POST api/lane {branch, verb}     merge or drop an upgrade lane (`upkeep.py`, with the cookie)

Deciding: the server holds a random session secret in memory only. It opens the browser itself
with a one-time key in the URL (`#k=`); the page trades it for an HttpOnly cookie. The model can
run `mark board` and curl the API but never sees a key or the secret, so it cannot decide.
A project with `[board] decide = false` stays read-only even with the cookie.

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
import re
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

from . import chat, deps, flow, general, home, human, model, propose, runner, scaffold, states, tickets, upkeep, wizard
from .config import ConfigError, MarkConfig, find_project_root, load_config
from .gitutil import git, worktrees
from .i18n import t
from .ports import in_use

DEFAULT_PORT = 6275  # "MARK" on a phone keypad; no well-known dev server uses it
PORT_TRIES = 100
POLL_SECONDS = 1.0
PING_SECONDS = 15
STATE_FILE = "board.json"
KEYS_KEPT = 10  # one-time keys not yet traded; older ones lapse
BODY_MAX = 131072  # a chat message of chat.TEXT_MAX characters, UTF-8
NO_BROWSER_ENV = "MARK_BOARD_NO_BROWSER"  # tests: never open a browser
SECRET_FD_ENV = "MARK_BOARD_SECRET_FD"  # a restart hands the session secret over a pipe: logins survive it
SERVICE_ENV = "MARK_SERVICE"  # set by the menu bar app (macos/Mark.swift): `mark board` never replaces or stops that board
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
            "tickets": items + general_lanes(cfg), "run": runner.view(cfg), "model": model.public(model.store(cfg))}


def waits_on(cfg: MarkConfig, tk: tickets.Ticket) -> dict[str, object] | None:
    """What the human can decide on this ticket from the board, or None."""
    if tk.side in ("terminal", "unknown"):
        return None
    ctx = flow.Ctx(cfg, tk)
    if not ctx.has_gate(flow.TICKET_GATE):
        return {"kind": "opening"}
    if tk.status not in flow.APPROVE:
        return None
    extra = {"proposal": p} if (p := propose.load(cfg, tk.id, tk.status)) else {}
    if flow.APPROVE[tk.status][0]:
        return {"kind": "review", **extra}
    targets = flow.approve_targets(ctx)
    default = flow.APPROVE[tk.status][2]
    return {"kind": "blocked", "targets": targets, "answer": tk.status == "blocked-unclear",
            "default": default if default in targets else (targets[0] if targets else ""), **extra}


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
        extra: dict[str, object] = {}
        first = git(["log", "--reverse", "--format=%s", f"{cfg.main_branch}..{branch}"], cfg.root)[1].split("\n", 1)[0]
        if first.startswith(upkeep.SUBJECT):  # the first commit: resolving a conflict adds another
            job = upkeep.job(cfg, branch)
            extra = {"upgrade": True, "conflicts": general._conflict_markers(cfg, branch), "job": job,
                     "side": "agent" if job and job["state"] == "running" else "human"}
        items.append({"kind": "general", "id": f"general-{stamp}", "status": "developing", "desc": subject or branch,
                      "owner": "orchestrator", "updater": "orchestrator", "note": note, "dir": "", "side": "",
                      "branch": branch, "worktree": os.path.relpath(wt, cfg.root) if wt else "",
                      "files": [], "gates": [], **extra, "history": [{"sha": "", "at": at, "status": "developing",
                                                              "owner": "orchestrator", "updater": "orchestrator", "note": note}]})
    return items


def signature(cfg: MarkConfig) -> tuple:
    """Cheap fingerprint of everything the snapshot reads; changes when any of it does."""
    sig: list[object] = [git(["rev-parse", "HEAD"], cfg.root)[1],
                         git(["for-each-ref", f"refs/heads/{general.PREFIX}*"], cfg.root)[1]]
    roots = [cfg.state_dir / "gates", cfg.state_dir / "locks"]  # locks: the runner's log grows there
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


def _known(cfg: MarkConfig, ticket: object) -> str | None:
    """The ticket's kind, or None if no such ticket."""
    if not isinstance(ticket, str):
        return None
    return next((k for k in states.KINDS if ticket in tickets.ticket_dirs(cfg, k)), None)


def new_ticket(cfg: MarkConfig, req: dict) -> tuple[bool, str, str]:
    """Open a ticket for the human, as their `/mark:feature` or `/mark:fix` would (a token for the
    opening, then `claim`), and send their text as the first chat message. (ok, text, id)."""
    kind, text, slug = req.get("kind"), req.get("text"), req.get("slug") or None
    if kind not in states.KINDS or not isinstance(text, str) or not text.strip() or len(text) > chat.TEXT_MAX \
            or not (slug is None or isinstance(slug, str)):
        return False, "bad request", ""
    desc = next(line.strip() for line in text.splitlines() if line.strip())[:tickets.DESC_MAX]
    verb = "feature" if kind == states.FEATURE else "fix"
    token = human.grant(cfg, verb, "", [], desc, source="board")
    try:
        ticket, _ = flow.open_ticket(cfg, kind, desc, slug=slug)
    except tickets.ClaimError as exc:
        return False, t(cfg.locale, exc.key, **exc.params), ""
    except OSError as exc:
        return False, str(exc), ""
    finally:
        token.unlink(missing_ok=True)
    started, why = chat.start(cfg, kind, ticket.id, text.strip())
    return True, "" if started else f"chat.{why}", ticket.id


def send(cfg: MarkConfig, req: dict) -> tuple[bool, str]:
    """The human's next chat message on a ticket: (started, why not)."""
    ticket, text = req.get("ticket"), req.get("text")
    kind = _known(cfg, ticket)
    if kind is None or not isinstance(text, str) or not text.strip() or len(text) > chat.TEXT_MAX:
        return False, "bad request"
    started, why = chat.start(cfg, kind, ticket, text.strip())
    return started, "" if started else f"chat.{why}"


def decide(cfg: MarkConfig, req: dict) -> tuple[bool, str]:
    """Approve or reject for the human, through the same CLI code as `/mark:approve` and
    `/mark:reject`: a token for this decision, then `mark approve|reject`. Returns (ok, output)."""
    from . import cli  # cli imports this module

    ticket, verb, to = req.get("ticket"), req.get("verb"), req.get("to") or None
    answer, items = req.get("answer") or "", req.get("items") or []
    if _known(cfg, ticket) is None or verb not in ("approve", "reject") or not (to is None or isinstance(to, str)) \
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


def void(cfg: MarkConfig, req: dict) -> tuple[bool, str]:
    """The human's Void button: stop what runs on the ticket, then `mark void` with a token."""
    from . import cli  # cli imports this module

    ticket, reason = req.get("ticket"), req.get("reason") or ""
    if _known(cfg, ticket) is None or not isinstance(reason, str) or len(reason) > human.TEXT_MAX:
        return False, "bad request"
    chat.stop(cfg, ticket)
    if (runner.running(cfg) or {}).get("ticket") == ticket:
        runner.stop(cfg)
    token = human.grant(cfg, "void", ticket, [], reason, source="board")
    out = io.StringIO()
    try:
        code = cli.main(["void", ticket] + (["--note", reason.strip()] if reason.strip() else []),
                        cwd=cfg.root, out=out, err=out)
    finally:
        token.unlink(missing_ok=True)
    return code == 0, out.getvalue().strip()


RUN_AFTER = ("review", "blocked")  # opening and drafting need the human in the conversation


def carry_on(cfg: MarkConfig, ticket: str, before: dict | None, had_waiter: bool) -> str:
    """After a board decision: a session waiting on the ticket wakes by itself; else start a
    headless one (`[board] run`). Returns a note for the page."""
    if had_waiter or chat.running(cfg, ticket):
        return "run.session"
    if not cfg.board_run or not before or before.get("kind") not in RUN_AFTER:
        return "run.terminal"
    try:
        if flow.load(cfg, ticket).ticket.status == states.DRAFTING:
            return "run.terminal"
    except flow.FlowError:
        return "run.terminal"
    started, why = runner.start(cfg, ticket)
    return "run.started" if started else f"run.{why}"


def summary(cfg: MarkConfig) -> dict[str, object]:
    """A project's card on the home page: counts only, no git history."""
    tks = tickets.all_tickets(cfg)
    live = [tk for tk in tks if tk.side != "terminal"]
    times = [tk.path.stat().st_mtime for tk in tks if tk.exists]
    return {"name": cfg.root.name, "locale": cfg.locale, "total": len(tks),
            "human": sum(tk.side == "human" for tk in tks), "agent": sum(tk.side == "agent" for tk in tks),
            "done": len(tks) - len(live),
            "running": runner.running(cfg) is not None or any(chat.running(cfg, tk.id) for tk in live),
            "at": _dt.datetime.fromtimestamp(max(times)).astimezone().isoformat(timespec="seconds") if times else ""}


def add_project(req: dict) -> tuple[bool, str, str]:
    """Register an existing Mark project from the home page: (ok, why not, id)."""
    d = req.get("dir")
    if not isinstance(d, str) or not d.strip() or len(d) > 4096:
        return False, "bad request", ""
    path = Path(d.strip()).expanduser()
    if not path.is_absolute():
        return False, "home.absolute", ""
    found = find_project_root(path) if path.is_dir() else None
    if found is None:
        return False, "home.notMark", ""
    try:
        cfg = load_config(tickets.main_root(found))
    except ConfigError as exc:
        return False, str(exc), ""
    if home.find(home.project_id(cfg.root)):
        return False, "home.already", ""
    return True, "", home.add(cfg.root)


class Project:
    """A registered project as the server holds it: its config, reloaded when the file changes."""

    def __init__(self, cfg: MarkConfig, mtime: int, version: int = 0):
        self.cfg, self.mtime, self.version, self.history = cfg, mtime, version, History(cfg)


class Board:
    """The one board server: every registered project (`home.py`), one login for all of them."""

    def __init__(self):
        self.version, self.cond, self.stop = 0, threading.Condition(), threading.Event()
        self.secret, self.keys, self.lock = _handed_secret() or secrets.token_urlsafe(32), [], threading.Lock()
        self.updater = upkeep.Updater(self.touch)
        self.projects: dict[str, Project] = {}
        self.errors: dict[str, str] = {}
        self.plock = threading.Lock()  # not self.lock: a long decision must not stall page loads

    def touch(self) -> None:
        """Every open page reloads: for state outside the files `watch` looks at."""
        with self.cond:
            for p in list(self.projects.values()):
                p.version += 1
            self.version += 1
            self.cond.notify_all()

    def busy(self) -> bool:
        return upkeep.busy() or any(c.get("running") for c in self.home_view()) or \
            any(w.get("running") for w in wizard.cards())

    def project(self, pid: object) -> Project | None:
        """The registered project with this id, or None (unknown, gone, or a broken config: see errors)."""
        root = home.find(pid)
        if root is None:
            return None
        try:
            mtime = (root / ".mark" / "config.toml").stat().st_mtime_ns
            with self.plock:
                p = self.projects.get(pid)
                if p is None or p.mtime != mtime:
                    p = self.projects[pid] = Project(load_config(root), mtime, p.version if p else 0)
                self.errors.pop(pid, None)
                return p
        except FileNotFoundError:
            self.errors[pid] = "home.gone"
        except (OSError, ConfigError) as exc:
            self.errors[pid] = str(exc)
        return None

    def open_browser(self, port: int, path: str = "/") -> None:
        key = secrets.token_urlsafe(24)
        with self.lock:
            self.keys = self.keys[-(KEYS_KEPT - 1):] + [key]
        if os.environ.get(NO_BROWSER_ENV) != "1":
            webbrowser.open(f"http://127.0.0.1:{port}{path}#k={key}")

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

    def mode(self, cookie_header: str | None, port: int, cfg: MarkConfig | None = None) -> str:
        """"on": this browser may decide; "login": it may not yet; "off": the project's `[board] decide = false`."""
        if cfg is not None and not cfg.board_decide:
            return "off"
        return "on" if self.authorized(cookie_header, port) else "login"

    def home_view(self) -> list[dict[str, object]]:
        out = []
        for reg in home.projects():
            p = self.project(reg["id"])
            card: dict[str, object] = {"id": reg["id"], "root": reg["root"], "path": home.short(Path(reg["root"])),
                                       "name": Path(reg["root"]).name}
            if p is None:
                card["error"] = self.errors.get(reg["id"], "home.gone")
            else:
                try:
                    card |= summary(p.cfg)
                except OSError as exc:
                    card["error"] = str(exc)
            out.append(card)
        return out

    def watch(self) -> None:
        """Bump a project's version when its signature or config changes, and the home's version
        when any project does or the registry changes. shortcut: polls every registered project each
        second; watch only those with an open page if people register dozens."""
        last: dict[str, tuple] = {}
        ids: tuple = ()
        while not self.stop.wait(POLL_SECONDS):
            reg = (tuple(p["id"] for p in home.projects()), wizard.signature())
            changed, ids = reg != ids, reg
            for pid in reg[0]:
                p = self.project(pid)
                if p is None:
                    continue
                try:
                    key = (p.mtime, signature(p.cfg))
                except OSError:
                    continue
                if last.get(pid) != key:
                    if pid in last:
                        p.version += 1
                        changed = True
                    last[pid] = key
            if changed:
                with self.cond:
                    self.version += 1
                    self.cond.notify_all()


def cookie_name(port: int) -> str:
    return f"mark_board_{port}"  # cookies ignore the port: a test server on another port must not share one


PROJECT_PATH = re.compile(r"^/p/([0-9a-f]{10})(/.*)?$")
WIZARD_PATH = re.compile(r"^/api/wizard/([0-9a-f]{10})(?:/(stop|discard))?$")


def make_handler(board: Board) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str, cookie: str = "", headers: dict | None = None) -> None:
            self.send_response(code)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
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

        def _route(self) -> tuple[Project | None, str, bool]:
            """(project, path inside it, ok): /p/<id>/x -> (that project, "/x"); "/x" -> (None, "/x").
            ok is False (a 404 already sent) for an unknown or broken project."""
            path = self.path.split("?", 1)[0]
            m = PROJECT_PATH.match(path)
            if not m:
                return None, path, True
            p = board.project(m.group(1))
            if p is None:
                self._send(404, b"not found", "text/plain")
                return None, "", False
            return p, m.group(2) or "", True

        def do_POST(self) -> None:
            try:
                raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), BODY_MAX))
            except ValueError:
                raw = b""
            if not self._local():
                return
            proj, path, ok = self._route()
            if not ok:
                return
            port = self.server.server_address[1]
            origin = self.headers.get("Origin")
            same = origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = None
            if proj is None and path == "/api/open" and (origin is None or same):  # no Origin: `mark board`, not a web page
                target = body.get("path") if isinstance(body, dict) else None
                m = PROJECT_PATH.match(target) if isinstance(target, str) else None
                if target not in (None, "/") and not (m and m.group(2) == "/" and home.find(m.group(1))):
                    self._json(404, {"ok": False, "text": "not found"})
                    return
                board.open_browser(port, target or "/")
                self._json(200, {"ok": True})
                return
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            cookie = self.headers.get("Cookie")
            if not same or ctype != "application/json" or not isinstance(body, dict):
                self._json(403, {"ok": False, "text": "forbidden"})
            elif proj is None and path == "/api/login":
                if board.redeem(body.get("k")):
                    self._json(200, {"ok": True},
                               f"{cookie_name(port)}={board.secret}; HttpOnly; SameSite=Strict; Path=/")
                else:
                    self._json(403, {"ok": False, "text": "expired key"})
            elif board.mode(cookie, port, proj.cfg if proj else None) != "on":
                self._json(403, {"ok": False, "text": "read-only"})
            elif proj is None:
                self._post_home(path, body)
            else:
                self._post_project(proj.cfg, path, body)

        def _post_home(self, path: str, body: dict) -> None:
            if path == "/api/model":
                with board.lock:
                    ok, text = model.save(None, body)
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            elif path == "/api/projects/add":
                ok, text, pid = add_project(body)
                self._json(200 if ok else 409, {"ok": ok, "text": text, "id": pid})
            elif path == "/api/projects/remove":
                root = home.find(body.get("id"))
                ok = home.remove(body.get("id"))
                if ok:
                    wizard.forget(root)
                self._json(200 if ok else 409, {"ok": ok, "text": "" if ok else "bad request"})
            elif path == "/api/deps/fix":
                ok, text = deps.start(body.get("id"))
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            elif path == "/api/pickdir":
                d = wizard.pick_dir()  # no lock: the dialog waits on the human
                self._json(200, {"ok": bool(d), "path": d})
            elif path == "/api/update":
                ok, text = board.updater.start(board.busy(), lambda: threading.Thread(target=self.server.shutdown).start())
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            elif path == "/api/wizard":
                with board.lock:
                    ok, text, wid = wizard.start(body)
                self._json(200 if ok else 409, {"ok": ok, "text": text, "id": wid})
            elif m := WIZARD_PATH.match(path):
                wid, act = m.group(1), m.group(2)
                with board.lock:
                    if act == "stop":
                        ok, text = wizard.stop(wid), ""
                    elif act == "discard":
                        ok, text = wizard.discard(wid), ""
                    else:
                        ok, text = wizard.send(wid, body.get("text"))
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            else:
                self._json(404, {"ok": False, "text": "not found"})

        def _post_project(self, cfg: MarkConfig, path: str, body: dict) -> None:
            if path == "/api/decide":
                from . import wait  # wait imports this module
                tid = body.get("ticket")
                with board.lock:  # one decision at a time
                    before = wait.state(cfg, tid) if isinstance(tid, str) else None
                    had_waiter = isinstance(tid, str) and wait.waiter(cfg, tid) is not None
                    ok, text = decide(cfg, body)
                    note = carry_on(cfg, tid, before[1] if before else None, had_waiter) if ok else ""
                self._json(200 if ok else 409, {"ok": ok, "text": text, "note": note})
            elif path == "/api/void":
                with board.lock:
                    ok, text = void(cfg, body)
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            elif path == "/api/stop":
                tid = body.get("ticket")
                self._json(200, {"ok": chat.stop(cfg, tid) if isinstance(tid, str) else runner.stop(cfg)})
            elif path == "/api/new":
                with board.lock:
                    ok, text, tid = new_ticket(cfg, body)
                self._json(200 if ok else 409, {"ok": ok, "text": text, "id": tid})
            elif path == "/api/chat":
                with board.lock:
                    ok, text = send(cfg, body)
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            elif path == "/api/lane":
                ok, text = upkeep.lane_action(cfg, body, general_lanes, board.touch)
                self._json(200 if ok else 409, {"ok": ok, "text": text})
            else:
                self._json(404, {"ok": False, "text": "not found"})

        def do_GET(self) -> None:
            if not self._local():
                return
            proj, path, ok = self._route()
            if not ok:
                return
            port = self.server.server_address[1]
            mode = board.mode(self.headers.get("Cookie"), port, proj.cfg if proj else None)
            if path == "/" or (proj is None and path == ""):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "":  # /p/<id>: the page reads its API relative to /p/<id>/
                self._send(301, b"", "text/plain", headers={"Location": self.path.split("?", 1)[0] + "/"})
            elif path == "/events":
                self._events(proj)
            elif proj is None:
                m = WIZARD_PATH.match(path)
                if path == "/api/projects":
                    self._json(200, {"projects": board.home_view(), "wizards": wizard.cards(), "decide": mode, "pick": wizard.PICKABLE,
                                     "update": board.updater.view(),
                                     "model": model.public(model.store(None))})
                elif path == "/api/deps":
                    self._json(200, {"checks": deps.checks(), "job": deps.job()})
                elif m and not m.group(2) and (v := wizard.view(m.group(1))) is not None:
                    self._json(200, v)
                else:
                    self._send(404, b"not found", "text/plain")
            elif path == "/api/board":
                self._json(200, {**snapshot(proj.cfg, proj.history), "decide": mode, "update": board.updater.view()})
            elif path.startswith("/api/chat/"):
                tid = unquote(path[len("/api/chat/"):])
                if _known(proj.cfg, tid) is None:
                    self._json(404, {"ok": False, "text": "not found"})
                else:
                    self._json(200, chat.view(proj.cfg, tid))
            elif path.startswith("/f/"):
                f = resolve_file(proj.cfg, [unquote(p) for p in path[3:].split("/")])
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

        def _events(self, proj: Project | None) -> None:
            """A number that grows on every change: of this project, or (the home page) of any."""
            def version() -> int:
                return proj.version if proj else board.version

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = -1
            try:
                while not board.stop.is_set():
                    with board.cond:
                        if version() == seen:
                            board.cond.wait(PING_SECONDS)
                        v = version()
                    msg = f"data: {v}\n\n" if v != seen else ": ping\n\n"
                    seen = v
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


def state_path() -> Path:
    return home.root() / STATE_FILE


def serve(start: int = DEFAULT_PORT) -> int:
    """Run the board in this process until SIGTERM / Ctrl-C."""
    server = bind(start)
    if server is None:
        return 1
    board = Board()
    server.RequestHandlerClass = make_handler(board)
    server.daemon_threads = True
    port = server.server_address[1]
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"pid": os.getpid(), "port": port, "page": str(PAGE)}
    if os.environ.get(SERVICE_ENV):
        state["service"] = os.environ[SERVICE_ENV]
    path.write_text(json.dumps(state) + "\n")
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    threading.Thread(target=board.watch, daemon=True).start()
    threading.Thread(target=board.updater.poll, args=(board.stop,), daemon=True).start()
    threading.Thread(target=upkeep.open_lanes, args=(board.touch, general_lanes), daemon=True).start()
    if os.environ.get(SERVICE_ENV):
        threading.Thread(target=_orphaned, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        board.stop.set()
        with board.cond:
            board.cond.notify_all()
        server.server_close()
        if read_state().get("pid") == os.getpid():
            path.unlink(missing_ok=True)
    if board.updater.restart:  # the plugin updated: the same process (and pid) runs the new code
        r, w = os.pipe()
        os.write(w, board.secret.encode())
        os.close(w)
        os.set_inheritable(r, True)
        os.environ[SECRET_FD_ENV] = str(r)
        os.execv(sys.executable, [sys.executable, str(board.updater.restart), "board", "--serve", "--port", str(port)])
    return 0


def _handed_secret() -> str:
    """The session secret the board this one replaced passed on (`serve`), else ""."""
    fd = os.environ.pop(SECRET_FD_ENV, "")
    if not fd.isdigit():
        return ""
    try:
        with os.fdopen(int(fd), "rb") as fh:
            return fh.read(256).decode().strip()
    except (OSError, ValueError, UnicodeDecodeError):
        return ""


def _orphaned(server: ThreadingHTTPServer) -> None:
    """A service board lives as long as the app that runs it, even when the app is killed."""
    parent = os.getppid()
    while os.getppid() == parent:
        time.sleep(2)
    server.shutdown()


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text())
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


def running() -> int | None:
    """Port of the live board, or None."""
    st = read_state()
    port = st.get("port")
    return port if _alive(st.get("pid")) and isinstance(port, int) and in_use(port) else None


def service() -> str | None:
    """What runs the live board as a service ("app": the menu bar app), or None."""
    return read_state().get("service") if running() else None


def start(port: int = DEFAULT_PORT, wait: float = 5.0) -> tuple[int | None, bool]:
    """(port, reused): reuse the live board, else start one in the background. A board started
    from another plugin install serves that install's code, so it is replaced; unless a service
    runs it (it would restart it at once; it restarts it itself when the plugin updates)."""
    live = running()
    if live:
        if read_state().get("page") == str(PAGE) or read_state().get("service"):
            return live, True
        stop()
    state_path().unlink(missing_ok=True)
    log = home.root() / "board.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    mark = Path(__file__).resolve().parents[2] / "bin" / "mark"
    with open(log, "w") as fh:
        # cwd MARK_HOME: outside any project, so `mark board --serve` loads no project config
        child = subprocess.Popen([sys.executable, str(mark), "board", "--serve", "--port", str(port)],
                                 cwd=home.root(), stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
                                 start_new_session=True)  # outlives the Bash call that started it
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and child.poll() is None:
        st = read_state()
        if st.get("pid") == child.pid:
            return st.get("port"), False
        time.sleep(0.1)
    return None, False


def reopen(port: int, path: str = "/") -> bool:
    """Ask the live board to open a page (the home, or `/p/<id>/`) in the human's browser."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/open", data=json.dumps({"path": path}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except OSError:
        return False


def _kill(state: Path) -> bool:
    try:
        pid = json.loads(state.read_text()).get("pid")
    except (OSError, ValueError, AttributeError):
        pid = None
    if not _alive(pid):
        state.unlink(missing_ok=True)
        return False
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _alive(pid):
            break
        time.sleep(0.1)
    state.unlink(missing_ok=True)
    return True


def stop() -> bool:
    return _kill(state_path())


def stop_legacy(cfg: MarkConfig) -> bool:
    """Stop this project's own board from before v0.58 (one server per project)."""
    return _kill(cfg.state_dir / "locks" / STATE_FILE)
