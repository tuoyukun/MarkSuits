"""Headless runner: after a board decision with no session waiting, carry the ticket on.

The board server starts `claude -p "/mark:continue <id>"` in the main checkout and records it in
`<state>/locks/runner.json` `{pid, ticket, log, started}`: one runner per project. The session's
stream-json goes to `<state>/locks/run-<id>-<time>.jsonl` (gitignored). Its last `result` event
says how it ended: permission denials (a command needed approval), an error, or a clean stop at
the next gate. Nothing here approves anything: the decision was made before the runner starts.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import model
from .config import MarkConfig

STATE_FILE = "runner.json"
WAIT_RE = re.compile(r"(^|[\s;&|/])mark\s+wait\b")
TAIL_BYTES = 256 * 1024
LINES_KEPT = 40
SESSION_MARKERS = frozenset({"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_SSE_PORT"})


def state_path(cfg: MarkConfig) -> Path:
    return cfg.state_dir / "locks" / STATE_FILE


def read(cfg: MarkConfig) -> dict:
    try:
        data = json.loads(state_path(cfg).read_text())
        return data if isinstance(data, dict) else {}
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


def running(cfg: MarkConfig) -> dict | None:
    st = read(cfg)
    return st if _alive(st.get("pid")) else None


def clean_env(environ=os.environ) -> dict[str, str]:
    """The board may have been started from inside a Claude session: drop its markers and its
    plugin paths so the runner is a session of its own, not one nested in it."""
    env = {k: v for k, v in environ.items() if k not in SESSION_MARKERS}  # keeps auth such as CLAUDE_CODE_OAUTH_TOKEN
    if "PATH" in env:  # that session's plugin bin/ may be an older install; claude adds the current one
        env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if "/.claude/plugins/" not in p)
    return env


def find_claude() -> str | None:
    """`claude` on PATH, else where its installers put it: a service (Homebrew) starts with a bare PATH."""
    for c in (shutil.which("claude"), Path.home() / ".local" / "bin" / "claude", Path.home() / ".claude" / "local" / "claude"):
        if c and os.access(c, os.X_OK):
            return str(c)
    return None


def command(cfg: MarkConfig, ticket_id: str, claude: str, extra: list[str] = ()) -> list[str]:
    return [claude, "-p", f"/mark:continue {ticket_id}", "--permission-mode", cfg.board_permission_mode,
            *extra, "--output-format", "stream-json", "--verbose"]


def start(cfg: MarkConfig, ticket_id: str, claude: str | None = None) -> tuple[bool, str]:
    """(started, why not). Never two runners in one project."""
    if running(cfg):
        return False, "busy"
    claude = claude or find_claude()
    if not claude:
        return False, "no-claude"
    locks = cfg.state_dir / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log = locks / f"run-{ticket_id}-{stamp}.jsonl"
    settings = model.load(cfg)  # read at start: a later change on the board waits for the next session
    extra, env = model.launch(settings, clean_env())
    with open(log, "w") as fh:
        proc = subprocess.Popen(command(cfg, ticket_id, claude, extra), cwd=cfg.root, env=env,
                                stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)  # its own group: stop ends the agents it started too
    state_path(cfg).write_text(json.dumps({"pid": proc.pid, "ticket": ticket_id, "log": log.name,
                                           "started": time.time(), "model": model.label(settings)}) + "\n")
    threading.Thread(target=proc.wait, daemon=True).start()  # reap it, so a finished run reads as dead
    return True, ""


def stop(cfg: MarkConfig) -> bool:
    st = running(cfg)
    if not st:
        return False
    try:
        os.killpg(st["pid"], signal.SIGTERM)
    except OSError:
        return False
    return True


def _describe(event: dict) -> list[str]:
    """One stream-json event -> the lines worth showing: what the session ran, and the end."""
    out = []
    if event.get("type") == "assistant":
        for c in (event.get("message") or {}).get("content") or []:
            if not isinstance(c, dict) or c.get("type") != "tool_use":
                continue
            inp = c.get("input") or {}
            if c.get("name") == "Bash":
                out.append(f"$ {inp.get('command', '')}")
            elif c.get("name") in ("Agent", "Task"):
                out.append(f"agent {inp.get('subagent_type', '')}: {inp.get('description', '')}")
            else:
                out.append(str(c.get("name")))
    elif event.get("type") == "system" and event.get("subtype") == "permission_denied":
        out.append("permission denied")
    return out


def outcome(result: dict | None, alive: bool) -> dict[str, object]:
    """How the run ended, from its last `result` event."""
    if alive:
        return {"kind": "running"}
    if result is None:
        return {"kind": "failed", "text": "the session ended without a result"}
    denials = [d.get("tool_input", {}).get("command") or d.get("tool_name", "")
               for d in result.get("permission_denials") or [] if isinstance(d, dict)]
    denials = [c for c in denials if not WAIT_RE.search(str(c))]  # refused on purpose (wait_guard), not by permissions
    if denials:
        return {"kind": "blocked", "commands": denials, "text": str(result.get("result") or "")}
    if result.get("is_error"):
        return {"kind": "failed", "text": str(result.get("result") or result.get("subtype") or "")}
    return {"kind": "done", "text": str(result.get("result") or "")}


def view(cfg: MarkConfig) -> dict[str, object] | None:
    """The last (or current) run for the board: ticket, start, trimmed log, outcome."""
    st = read(cfg)
    if not st.get("log"):
        return None
    lines, result = [], None
    try:
        with open(cfg.state_dir / "locks" / Path(st["log"]).name, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            raw = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        raw = []
    for line in raw:
        try:
            event = json.loads(line)
        except ValueError:
            if line.strip():
                lines.append(line.strip()[:300])  # stderr, e.g. a CLI error
            continue
        if isinstance(event, dict):
            lines += _describe(event)
            if event.get("type") == "result":
                result = event
    return {"ticket": st.get("ticket"), "started": st.get("started"), "log": st.get("log"), "model": st.get("model"),
            "lines": lines[-LINES_KEPT:], **outcome(result, _alive(st.get("pid")))}
