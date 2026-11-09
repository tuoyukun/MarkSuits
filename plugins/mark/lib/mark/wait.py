"""`mark wait <id>`: block until the human decides on a ticket, then exit.

The orchestrator starts it in the background at a human gate and ends its turn. When the human
approves or rejects (on the board or in the terminal) the ticket stops waiting on them, this
exits, and the finished background task wakes the session to carry on. Being woken is not
consent: the decision was already recorded by `mark approve|reject`.

One waiter per ticket: `<state>/locks/<id>.wait.json` holds its pid. A new waiter for the same
ticket replaces the old one, so only one session wakes. A waiter whose parent shell is gone
(the session closed) exits by itself, so a live file means a live session.
"""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Callable

from . import board, flow
from .config import MarkConfig

POLL_SECONDS = 1.0


def path(cfg: MarkConfig, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"{ticket_id}.wait.json"


def waiter(cfg: MarkConfig, ticket_id: str) -> int | None:
    """Pid of the live waiter for this ticket, or None."""
    try:
        pid = json.loads(path(cfg, ticket_id).read_text()).get("pid")
    except (OSError, ValueError, AttributeError):
        return None
    return pid if board._alive(pid) else None


def state(cfg: MarkConfig, ticket_id: str) -> tuple[str, object] | None:
    """(status, what the human may decide) — changes when the human decides. None: ticket gone."""
    try:
        tk = flow.load(cfg, ticket_id).ticket
    except flow.FlowError:
        return None
    return tk.status, board.waits_on(cfg, tk)


def stop(cfg: MarkConfig, ticket_id: str) -> bool:
    pid = waiter(cfg, ticket_id)
    if pid is None:
        return False
    os.kill(pid, signal.SIGTERM)
    return True


def run(cfg: MarkConfig, ticket_id: str, poll: float = POLL_SECONDS,
        parent: Callable[[], int] = os.getppid) -> tuple[str, dict]:
    """Wait; return the message key and params to print when done."""
    start = state(cfg, ticket_id)
    if start is None or start[1] is None:
        return "wait.not_waiting", {"id": ticket_id, "status": start[0] if start else "-"}
    stop(cfg, ticket_id)  # the newest session waits; the replaced one is told to do nothing
    p = path(cfg, ticket_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}) + "\n")
    replaced = []
    old = signal.signal(signal.SIGTERM, lambda *_: replaced.append(True))
    ppid = parent()
    try:
        while not replaced:
            now = state(cfg, ticket_id)
            if now != start:
                new = now[0] if now else "-"
                if now and now[0] == start[0]:
                    new = "opening approved"
                return "wait.moved", {"id": ticket_id, "old": start[0], "new": new}
            if parent() != ppid:
                return "wait.orphaned", {"id": ticket_id}
            time.sleep(poll)
        return "wait.replaced", {"id": ticket_id}
    finally:
        signal.signal(signal.SIGTERM, old)
        try:
            if json.loads(p.read_text()).get("pid") == os.getpid():
                p.unlink()
        except (OSError, ValueError):
            pass
