"""Mark's per-user home: the one board server and the projects it shows.

    MARK_HOME          $MARK_HOME, else ~/.mark on macOS, else ${XDG_DATA_HOME:-~/.local/share}/mark
      projects.json    {"projects": [{"root": "/abs/path", "added": "<iso time>"}]}  (mode 600)
      board.json       the running board server: {pid, port, page}
      board.log        its output
      model.json       the model board sessions run on (`model.py`)

Not under ${CLAUDE_PLUGIN_ROOT} or ${CLAUDE_PLUGIN_DATA}: it outlives plugin installs and
updates, and a process outside Claude Code (the board server) reads it. A project's own state
stays in its `.mark/`. Removing a project here only forgets it; nothing on disk is deleted.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

ENV = "MARK_HOME"
REGISTRY = "projects.json"


def root() -> Path:
    if os.environ.get(ENV):
        return Path(os.environ[ENV]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / ".mark"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "mark"


def project_id(project_root: Path) -> str:
    """Stable, URL-safe and the same for every spelling of the path."""
    return hashlib.sha1(str(Path(project_root).resolve()).encode()).hexdigest()[:10]


def short(path: Path) -> str:
    """A path for people: under the home directory as ~/..."""
    path = Path(path)
    return "~/" + str(path.relative_to(Path.home())) if path.is_relative_to(Path.home()) else str(path)


def projects() -> list[dict[str, str]]:
    """Registered projects in the order they were added: [{id, root, added}]."""
    try:
        data = json.loads((root() / REGISTRY).read_text())
    except (OSError, ValueError):
        return []
    items = data.get("projects") if isinstance(data, dict) else None
    return [{"id": project_id(Path(p["root"])), "root": p["root"], "added": str(p.get("added", ""))}
            for p in items or [] if isinstance(p, dict) and isinstance(p.get("root"), str)]


def _save(items: list[dict[str, str]]) -> None:
    from .model import write_private  # model imports this module

    write_private(root() / REGISTRY, {"projects": [{"root": p["root"], "added": p["added"]} for p in items]})


def add(project_root: Path) -> str:
    """Register a project (once); returns its id."""
    pid, items = project_id(project_root), projects()
    if not any(p["id"] == pid for p in items):
        now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
        _save(items + [{"root": str(Path(project_root).resolve()), "added": now}])
    return pid


def remove(pid: str) -> bool:
    items = projects()
    keep = [p for p in items if p["id"] != pid]
    if len(keep) == len(items):
        return False
    _save(keep)
    return True


def find(pid: object) -> Path | None:
    return next((Path(p["root"]) for p in projects() if p["id"] == pid), None)
