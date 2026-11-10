"""What this machine needs for Mark, and the fixed commands the board may run to fix it.

The home page lists the checks that fail. A fix runs one of the commands in `fix_command`: the
page sends only a check id, never a command or an argument. One fix runs at a time, in the
background; its output goes to MARK_HOME/deps.log. Signing in to Claude needs a browser and a
terminal, so the page shows that command instead of running it; a model of its own (a custom
endpoint picked in the board's model menu) needs no sign-in.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path

from . import app, home, model, runner

INSTALL_CLAUDE = "curl -fsSL https://claude.ai/install.sh | bash"
MARKETPLACE = "tuoyukun/MarkSuits"
BLOCKING = ("python", "git", "claude", "model", "plugin")  # a new project needs all of these

_lock = threading.Lock()
_job: dict = {}


def _run(cmd: list[str], timeout: float = 20) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              env=env())
    except (OSError, subprocess.SubprocessError):
        return None


def env() -> dict[str, str]:
    """A session-free environment, with where installers put their commands on PATH."""
    e = runner.clean_env()
    extra = [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    e["PATH"] = os.pathsep.join([*extra, *(p for p in e.get("PATH", "").split(os.pathsep) if p and p not in extra)])
    return e


def _first_line(res: subprocess.CompletedProcess | None) -> str:
    return (res.stdout or "").strip().splitlines()[0] if res and res.returncode == 0 and (res.stdout or "").strip() else ""


def checks(run=_run, darwin: bool = sys.platform == "darwin") -> list[dict]:
    """[{id, ok, detail, fix, blocks}] in the order to fix them; `fix` says the board can run one."""
    out: list[dict] = []

    def add(cid: str, ok: bool, detail: str = "", fix: bool = False) -> None:
        out.append({"id": cid, "ok": ok, "detail": detail, "fix": fix and not ok, "blocks": cid in BLOCKING})

    py = _first_line(run(["python3", "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"]))
    add("python", bool(py) and tuple(int(x) for x in py.split(".")[:2]) >= (3, 11), py)
    # without the command line tools, macOS's /usr/bin/git is a stub that opens an install dialog
    sel = run(["xcode-select", "-p"]) if darwin else None
    tools = not darwin or bool(sel and sel.returncode == 0)
    git = _first_line(run(["git", "--version"])) if tools else ""
    add("git", bool(git), git.removeprefix("git version "), fix=darwin)
    claude = runner.find_claude()
    add("claude", bool(claude), _first_line(run([claude, "--version"])).split(" ")[0] if claude else "", fix=True)
    s = model.store(None)
    active = next(p for p in s["profiles"] if p["name"] == s["active"])
    if active.get("provider") == "custom":
        add("model", True, active["name"])
    else:  # the CLI's own login: claude.ai, an API key, a cloud provider
        res = run([claude, "auth", "status"]) if claude else None
        try:
            method = str(json.loads(res.stdout).get("authMethod") or "") if res and res.returncode == 0 else ""
        except (ValueError, AttributeError):
            method = ""
        add("model", bool(res and res.returncode == 0), method)
    found = app.plugin_entry()
    user = bool(found and found[1].get("scope") == "user")
    add("plugin", user, str(found[1].get("version") or "") if user else "", fix=bool(claude))
    if darwin:
        add("app", app.app_path().is_dir(), "", fix=True)
    return out


def fix_command(cid: object) -> list[str] | None:
    """The fixed command for a check, or None when the board does not fix it."""
    claude = runner.find_claude()
    if cid == "git" and sys.platform == "darwin":
        return ["xcode-select", "--install"]
    if cid == "claude":
        return ["bash", "-c", INSTALL_CLAUDE]
    if cid == "plugin" and claude:
        c = shlex.quote(claude)
        return ["bash", "-c", f"{c} plugin marketplace add {MARKETPLACE} --scope user && "
                              f"{c} plugin install mark@marksuits --scope user"]
    if cid == "app" and sys.platform == "darwin":
        return [sys.executable, str(app.PLUGIN / "bin" / "mark"), "app", "install"]
    return None


def log_path() -> Path:
    return home.root() / "deps.log"


def start(cid: object, popen=subprocess.Popen) -> tuple[bool, str]:
    """Run a check's fix in the background: (started, why not)."""
    cmd = fix_command(cid)
    if cmd is None:
        return False, "bad request"
    with _lock:
        if _job.get("running"):
            return False, "deps.busy"
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        log = path.open("w", encoding="utf-8")
        try:
            proc = popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env(),
                         cwd=str(Path.home()), start_new_session=True)
        except OSError as exc:
            log.close()
            return False, str(exc)
        _job.clear()
        _job.update({"id": cid, "running": True, "code": None})

    def wait() -> None:
        code = proc.wait()
        log.close()
        with _lock:
            _job.update({"running": False, "code": code})

    threading.Thread(target=wait, daemon=True).start()
    return True, ""


def job() -> dict | None:
    """The current or last fix: {id, running, code, tail}."""
    with _lock:
        if not _job:
            return None
        state = dict(_job)
    try:
        state["tail"] = "\n".join(log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-15:])
    except OSError:
        state["tail"] = ""
    return state
